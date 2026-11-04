"""hrc-013 (DEC-SCOPE-391, spec docs/superpowers/specs/2026-11-04-hrc-013-candidate-bulk-import-design.md): the candidate file's rows --
check each one, match a known person, create a new one, report.

Functions only; nothing here commits -- the route owns the transaction. A row goes through `CandidateCreate`, so an import accepts exactly
what the manual form accepts (I3). A known mobile or email is matched and that candidate is never changed (I7). The same engine answers the
read-only preview (`commit=False`: nothing is written) and the commit (a savepoint per row). Logs and stored rows carry ids, counts and
reasons, never a name, mobile or email (I9)."""

import csv
import io
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.school_bulk import _safe_cell
from app.models import Candidate, CandidateImportBatch, CandidateImportRow, RecCandidateSource, User
from app.notifications.phone import normalise_phone
from app.schemas import CANDIDATE_FIELD_LABELS, CandidateCreate
from app.services import candidate_duplicates as duplicates
from app.services import candidate_ownership as ownership
from app.services import candidate_profile as profile
from app.services import candidates as svc
from app.services.permissions import user_has_grant
from app.services.tabular import TabularError, read_tabular

COLUMNS = (
    "name", "mobile", "email", "source_detail", "location", "country", "state", "city", "qualification", "college", "passing_year",
    "experience_months", "relevant_experience_months", "current_company", "notice_days", "preferred_role", "preferred_locations", "tools",
    "languages", "linkedin", "available_from", "willing_to_relocate",
)  # fmt: skip
REQUIRED = ("name",)
LISTS = ("preferred_locations", "tools", "languages")  # `;`-separated cells
WHOLE = ("passing_year", "experience_months", "relevant_experience_months", "notice_days")
YES_NO = {"yes": True, "y": True, "true": True, "1": True, "no": False, "n": False, "false": False, "0": False}
TYPE_MESSAGES = {"int": "must be a whole number", "date": "must be a date (YYYY-MM-DD)", "bool": "must be Yes or No"}
MAX_ROWS = 1000  # Q-13 (builder's call): AC1's size
MAX_BYTES = 1024 * 1024
NAME_LIMIT = 160  # how much of the file's name the preview echoes
MERGE_HOPS = 5
NO_IMPORT = "Your role cannot import candidates"
REPORT_COLUMNS = ("row_number", "status", "candidate_code", "name", "reason")


async def require_importer(db: AsyncSession, user: User) -> None:
    """I1: a candidate writer holding `candidates.import` (a grant never lets a reader role write)."""
    if user.role not in svc.WRITERS or not await user_has_grant(db, user, "candidates", "import"):
        raise HTTPException(403, NO_IMPORT)


def read_file(filename: str, raw: bytes) -> list[tuple[int, dict[str, str]]]:
    """I2: (file row, {column: text}) or the 413/415/422 that lists every header problem."""
    try:
        rows = read_tabular(filename, raw, required=REQUIRED, known=COLUMNS, max_rows=MAX_ROWS, max_bytes=MAX_BYTES)
    except TabularError as exc:
        raise HTTPException(exc.status_code, "; ".join(exc.messages)) from None
    if not rows:
        raise HTTPException(422, "The file has no candidate rows")  # browser QA-01
    return rows


def parse_row(cells: dict[str, str], source_id: UUID) -> CandidateCreate | str:
    """The validated create payload, or one sentence naming the field (the form's labels)."""
    values: dict = {"source_id": source_id}
    for field, value in cells.items():
        if not value:
            continue
        if field in LISTS:
            values[field] = [part.strip() for part in value.split(";") if part.strip()]
        elif field == "willing_to_relocate":
            values[field] = YES_NO.get(value.casefold(), value)
        elif field in WHOLE and value.isascii() and value.isdigit():
            values[field] = int(value)  # the schema's whole numbers are strict (the form sends numbers); anything else gets its message
        else:
            values[field] = value
    try:
        return CandidateCreate.model_validate(values)
    except ValidationError as exc:
        return row_error(exc)


def row_error(exc: ValidationError) -> str:
    """The first problem as the form would say it: our validators' messages already name the field ("Enter a valid email address",
    "Passing year must be ..."); a type error (a date, a number, yes/no) gets the column's label in front. Never the cell's value."""
    error = exc.errors()[0]
    field = next((str(part) for part in error["loc"] if not isinstance(part, int)), None)
    reason = error["msg"].removeprefix("Value error, ")
    if error["type"] == "value_error" or field is None:
        return reason
    label = CANDIDATE_FIELD_LABELS.get(field, field)
    if expected := TYPE_MESSAGES.get(error["type"].split("_", 1)[0]):  # browser QA-02: int_parsing, date_from_datetime_parsing, bool_parsing ...
        return f"{label} {expected}"
    return f"{label}: {reason[:1].lower()}{reason[1:]}"


async def _survivor(db: AsyncSession, candidate_id: UUID) -> Candidate:
    """A merged record leads to the candidate it was merged into (I7)."""
    candidate = await db.get(Candidate, candidate_id)
    for _ in range(MERGE_HOPS):
        if candidate.merged_into_id is None:
            break
        candidate = await db.get(Candidate, candidate.merged_into_id)
    return candidate


async def _known(db: AsyncSession, mobile_key: str | None, email: str | None) -> Candidate | None:
    with db.no_autoflush:
        matches = await svc.find_matches(db, mobile_key, email)
    return await _survivor(db, UUID(matches[0]["id"])) if matches else None


async def _create(db: AsyncSession, user: User, row: CandidateCreate, sent: set[str], batch_id: UUID) -> Candidate:
    """I10: the manual create's steps (routes/recruiter_candidates.create_candidate) without salary or profile rows."""
    data = row.model_dump(exclude=set(profile.ROWS))
    candidate = Candidate(**data, mobile_normalized=normalise_phone(data["mobile"]), created_by_user_id=user.id)
    profile.sync(candidate, {kind: [] for kind in profile.ROWS}, sent)
    candidate.candidate_code = await svc.next_code(db)
    db.add(candidate)
    await db.flush()
    ownership.on_create(db, user, candidate)
    svc.audit(db, user, "create", candidate, {"fields": sorted(k for k in sent if k != "source_id"), "import_batch_id": str(batch_id)})
    await duplicates.detect(db, candidate.id)  # hrc-014 D2: probable duplicates are queued, never blocked
    return candidate


def _ref(candidate: Candidate | None) -> dict | None:
    return {"id": str(candidate.id), "candidate_code": candidate.candidate_code, "name": candidate.name} if candidate else None


async def run(db: AsyncSession, user: User, source_id: UUID, rows: list[tuple[int, dict[str, str]]], batch_id: UUID | None = None) -> list[dict]:
    """Each row's outcome in file order: {row_number, status, name, candidate, same_as_row, reason}. Without `batch_id` (the preview)
    nothing is written and a new row is `new`; with it each new row is created in its own savepoint (`created`)."""
    seen: dict[str, tuple[int, Candidate | None]] = {}  # match key -> (first row, its candidate)
    results = []
    for line, cells in rows:
        result = {"row_number": line, "status": "error", "name": cells.get("name", "")[:NAME_LIMIT], "candidate": None, "same_as_row": None, "reason": None}
        results.append(result)
        parsed = parse_row(cells, source_id)
        if isinstance(parsed, str):
            result["reason"] = parsed
            continue
        mobile_key = normalise_phone(parsed.mobile)
        keys = [k for k in (f"m:{mobile_key}" if mobile_key else None, f"e:{parsed.email}" if parsed.email else None) if k]
        earlier = next((seen[k] for k in keys if k in seen), None)
        if earlier:
            first_row, candidate = earlier
            result.update(status="matched", candidate=_ref(candidate), same_as_row=first_row, reason=f"Same person as row {first_row}")
        else:
            if batch_id is not None and parsed.email:
                # hrc-023 W5's lock: a website application of the same email waits for this import
                await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"candidate:email:{parsed.email}"})
            candidate = await _known(db, mobile_key, parsed.email)
            if candidate is not None:
                result.update(status="matched", candidate=_ref(candidate), reason="Already a candidate")
            elif batch_id is None:
                result["status"] = "new"
            else:
                try:
                    async with db.begin_nested():
                        candidate = await _create(db, user, parsed, parsed.model_fields_set, batch_id)  # the filled cells + source_id
                    result.update(status="created", candidate=_ref(candidate))
                except IntegrityError:  # a concurrent manual create took the mobile or email
                    candidate = await _known(db, mobile_key, parsed.email)
                    if candidate is None:
                        raise
                    result.update(status="matched", candidate=_ref(candidate), reason="Already a candidate")
            for key in keys:
                seen[key] = (line, candidate)
    return results


def counts(results: list[dict]) -> dict:
    tally = {status: sum(r["status"] == status for r in results) for status in ("new", "created", "matched", "error")}
    return {"total_rows": len(results), **{f"{status}_count": n for status, n in tally.items()}}


async def store(db: AsyncSession, batch: CandidateImportBatch, results: list[dict]) -> None:
    tally = counts(results)
    batch.total_rows, batch.created_count, batch.matched_count, batch.error_count = (tally[k] for k in ("total_rows", "created_count", "matched_count", "error_count"))
    db.add_all(
        CandidateImportRow(batch_id=batch.id, row_number=r["row_number"], status=r["status"], reason=r["reason"], candidate_id=UUID(r["candidate"]["id"]) if r["candidate"] else None)  # fmt: skip
        for r in results
    )
    await db.flush()


def summary(batch: CandidateImportBatch, uploader: User, source: RecCandidateSource) -> dict:
    return {
        "id": str(batch.id),
        "file_name": batch.file_name,
        "source": {"id": str(source.id), "name": source.name},
        "uploaded_by": {"id": str(uploader.id), "full_name": uploader.full_name},
        **{k: getattr(batch, k) for k in ("total_rows", "created_count", "matched_count", "error_count", "created_at")},
    }


async def report(db: AsyncSession, batch: CandidateImportBatch, *, replayed: bool = False) -> dict:
    """One shape for the commit, every replay and the history detail; created and matched rows name their candidate."""
    uploader = await db.get(User, batch.uploaded_by_user_id)
    source = await db.get(RecCandidateSource, batch.source_id)
    stmt = (select(CandidateImportRow, Candidate).outerjoin(Candidate, Candidate.id == CandidateImportRow.candidate_id)
            .where(CandidateImportRow.batch_id == batch.id).order_by(CandidateImportRow.row_number))  # fmt: skip
    rows = [{"row_number": row.row_number, "status": row.status, "candidate": _ref(candidate), "reason": row.reason} for row, candidate in (await db.execute(stmt)).all()]
    return {**summary(batch, uploader, source), "replayed": replayed, "rows": rows}


def report_csv(body: dict) -> str:
    """I11: every text cell formula-escaped -- names come from a file someone else filled in."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(REPORT_COLUMNS)
    for row in body["rows"]:
        candidate = row["candidate"] or {}
        writer.writerow([row["row_number"], row["status"], *(_safe_cell(v or "") for v in (candidate.get("candidate_code"), candidate.get("name"), row["reason"]))])
    return buffer.getvalue()
