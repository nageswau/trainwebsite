"""pob-006 (DEC-SCOPE-418 I1-I11, spec docs/superpowers/specs/2026-11-06-pob-006-company-import-merge-design.md): a file of companies and their contacts --
check each row, match a known company or contact, create a new one, report.

The hrc-013 shape. Functions only; nothing here commits -- the route owns the transaction. A row goes through `RecCompanyCreate` and `RecContactIn`, so an
import accepts what the forms accept. A known record is matched and never changed (I4/I5). The same engine answers the read-only preview (`batch_id=None`:
nothing is written) and the commit (a savepoint per row). Stored rows and logs carry ids, counts and reasons, never a name, mobile or email (I9)."""

import csv
import io
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.school_bulk import _safe_cell
from app.models import Company, CompanyContact, CrmImportBatch, CrmImportRow, RecCompanySize, RecContactRole, RecIndustry, RecLeadSource, User
from app.notifications.phone import normalise_phone
from app.schemas import REC_COMPANY_FIELDS, REC_CONTACT_MAX, REC_CONTEXT_LIST_LABELS, RecCompanyCreate, RecContactIn
from app.services import recruiter_companies as companies
from app.services import recruiter_contacts as contacts
from app.services.recruiter import ROLE
from app.services.tabular import TabularError, read_tabular

# column -> the create payload's field
COMPANY_COLUMNS = {
    "company_name": "name", "website": "website", "linkedin_url": "linkedin_url", "employee_count": "employee_count", "city": "city", "state": "state",
    "country": "country", "head_office": "head_office", "description": "description", "priority": "priority",
}  # fmt: skip
CONTACT_COLUMNS = {
    "contact_name": "name", "contact_designation": "designation", "contact_department": "department", "contact_mobile": "mobile", "contact_email": "email",
    "contact_linkedin": "linkedin_url", "contact_channel": "preferred_channel", "contact_source": "source", "contact_verified_on": "verified_on",
    "contact_decision_maker": "is_decision_maker", "contact_notes": "notes",
}  # fmt: skip
# column -> (catalogue, field, the word in its row error)
CATALOGUES = {
    "industry": (RecIndustry, "industry_id", "industry"), "company_size": (RecCompanySize, "company_size_id", "company size"),
    "lead_source": (RecLeadSource, "lead_source_id", "lead source"), "contact_role": (RecContactRole, "role_id", "contact role"),
}  # fmt: skip
COLUMNS = (
    "company_name", "website", "linkedin_url", "industry", "company_size", "employee_count", "city", "state", "country", "head_office", "description", "lead_source", "priority",
    "contact_name", "contact_designation", "contact_department", "contact_role", "contact_mobile", "contact_email", "contact_linkedin", "contact_channel", "contact_source",
    "contact_verified_on", "contact_decision_maker", "contact_notes",
)  # fmt: skip
CONTACT_ANY = tuple(c for c in COLUMNS if c.startswith("contact_"))
LOWERED = ("priority", "contact_channel")  # a closed list, so "HOT" means hot
YES_NO = {"yes": True, "y": True, "true": True, "1": True, "no": False, "n": False, "false": False, "0": False}
MAX_ROWS = 1000
MAX_BYTES = 1024 * 1024
NAME_LIMIT = 180  # how much of a cell the preview echoes
NO_IMPORT = "Your role cannot import companies"
REPORT_COLUMNS = ("row_number", "status", "company_code", "company_name", "contact_name", "reason")
CONTACT_WITHOUT_NAME = "contact_name is required when a row gives a contact's details"
OTHER_RECRUITER = "{code} belongs to another recruiter, so this contact was not added"
ARCHIVED = "{code} is archived, so this contact was not added. Restore it first"
AT_CAP = f"This company already has at most {REC_CONTACT_MAX} contacts"
ALSO_ELSEWHERE = "The same mobile or email is also a contact at another company"


async def require_importer(db: AsyncSession, user: User) -> None:
    await companies.require_crm(db, user, "import", NO_IMPORT)


def read_file(filename: str, raw: bytes) -> list[tuple[int, dict[str, str]]]:
    """I2: (file row, {column: text}) or the 413/415/422 that lists every header problem."""
    try:
        rows = read_tabular(filename, raw, required=("company_name",), known=COLUMNS, max_rows=MAX_ROWS, max_bytes=MAX_BYTES)
    except TabularError as exc:
        raise HTTPException(exc.status_code, "; ".join(exc.messages)) from None
    if not rows:
        raise HTTPException(422, "The file has no company rows")
    return rows


async def _catalogues(db: AsyncSession) -> dict[str, dict[str, UUID]]:
    """Each catalogue's active values by lower-cased name (one query each, not one per row)."""
    out = {}
    for column, (model, _, _) in CATALOGUES.items():
        out[column] = {name.casefold(): id_ for id_, name in (await db.execute(select(model.id, model.name).where(model.active.is_(True)))).all()}
    return out


def _problem(exc: ValidationError, columns: dict[str, str]) -> str:
    """The first problem as the form would say it; a type error gets the column's name in front. Never the cell's value."""
    error = exc.errors()[0]
    reason = error["msg"].removeprefix("Value error, ")
    if error["type"] == "value_error" or not error["loc"]:
        return reason
    column = next((c for c, f in columns.items() if f == str(error["loc"][0])), str(error["loc"][0]))
    return f"{column}: {reason[:1].lower()}{reason[1:]}"


def parse_row(cells: dict[str, str], catalogues: dict) -> tuple[RecCompanyCreate, RecContactIn | None] | str:
    """The validated payloads, or one sentence naming the column."""
    values: dict = {"company": {}, "contact": {}}
    for column, (_, target, word) in CATALOGUES.items():
        if cells.get(column):
            value = catalogues[column].get(cells[column].casefold())
            if value is None:
                return f"{column}: choose an active {word}"
            values["contact" if column == "contact_role" else "company"][target] = value
    for side, columns in (("company", COMPANY_COLUMNS), ("contact", CONTACT_COLUMNS)):
        for column, target in columns.items():
            value = cells.get(column)
            if not value:
                continue
            if column in LOWERED:
                value = value.casefold()
            elif column == "employee_count" and value.isascii() and value.isdigit():
                value = int(value)  # the schema's whole number is strict
            elif column == "contact_decision_maker":
                value = YES_NO.get(value.casefold(), value)
            elif column == "contact_source":
                value = value.strip().casefold().replace(" ", "_")
            values[side][target] = value
    if not cells.get("company_name"):
        return "company_name is required"
    try:
        company = RecCompanyCreate.model_validate(values["company"])
    except ValidationError as exc:
        return _problem(exc, COMPANY_COLUMNS)
    has_contact = any(cells.get(c) for c in CONTACT_ANY)
    if not has_contact:
        return company, None
    if not cells.get("contact_name"):
        return CONTACT_WITHOUT_NAME
    try:
        return company, RecContactIn.model_validate(values["contact"])
    except ValidationError as exc:
        return _problem(exc, CONTACT_COLUMNS)


def _contact_keys(mobile: str | None, email: str | None, name: str) -> tuple[list[str], list[str]]:
    """(what a row matches on, everything a stored contact answers to): mobile or email; the name only when the row has neither (I5)."""
    number = normalise_phone(mobile) if mobile else None
    strong = [k for k in (f"m:{number}" if number else None, f"e:{email.strip().lower()}" if email and email.strip() else None) if k]
    by_name = f"n:{companies.name_key(name)}"
    return strong or [by_name], [*strong, by_name]


@dataclass
class _Known:
    """A company the run has met: stored, or (in a preview, or until its row runs) only named by an earlier row."""

    first_row: int | None  # the file row that adds it; None when it was already stored
    id: UUID | None = None
    code: str | None = None
    name: str = ""
    archived: bool = False
    in_scope: bool = True
    locked: bool = False
    contacts: dict[str, tuple[UUID | None, str, int]] | None = None  # match key -> (contact id, name, the row that adds it)
    count: int = 0


def _ref(known: _Known) -> dict | None:
    return {"id": str(known.id), "code": known.code, "name": known.name, "in_scope": known.in_scope} if known.id else None


async def _stored_companies(db: AsyncSession, user: User, keys: set[str]) -> dict[str, _Known]:
    """I4: the file's names in one query. A merged company answers as its survivor; of several same-key companies, an in-scope active one wins."""
    if not keys:
        return {}
    rows = (await db.scalars(select(Company).where(companies.NAME_KEY.in_(keys)).order_by(Company.company_code))).all()
    survivors = {c.id: c for c in rows}
    wanted = {c.merged_into_id for c in rows if c.merged_into_id} - set(survivors)
    if wanted:
        survivors |= {c.id: c for c in (await db.scalars(select(Company).where(Company.id.in_(wanted)))).all()}
    ids = list(survivors)
    in_scope = set((await db.scalars(select(Company.id).where(Company.id.in_(ids), *await companies.caller_scope(db, user)))).all()) if ids else set()
    best: dict[str, _Known] = {}
    for row in rows:
        target = survivors[row.merged_into_id] if row.merged_into_id else row
        key = companies.name_key(row.name)
        known = _Known(None, target.id, target.company_code, target.name, target.archived_at is not None, target.id in in_scope)
        current = best.get(key)
        if current is None or (known.in_scope, not known.archived) > (current.in_scope, not current.archived):
            best[key] = known
    return best


async def _load_contacts(db: AsyncSession, known: _Known) -> None:
    """I5: everything the company's contacts answer to; a merged-away one answers as its survivor (so a re-import cannot resurrect it)."""
    if known.contacts is not None:
        return
    known.contacts = {}
    if known.id is None:
        return
    rows = (await db.scalars(select(CompanyContact).where(CompanyContact.company_id == known.id))).all()
    by_id = {c.id: c for c in rows}
    known.count = sum(1 for c in rows if c.merged_into_id is None)
    for contact in rows:
        target = by_id.get(contact.merged_into_id, contact)
        for key in _contact_keys(contact.mobile, contact.email, contact.name)[1]:
            known.contacts.setdefault(key, (target.id, target.name, 0))


async def _elsewhere(db: AsyncSession, company_id: UUID | None, payload: RecContactIn) -> bool:
    """I5, pob-005 D8: the same person at another company is added and noted. Counted only: nothing about the other company is said."""
    number = normalise_phone(payload.mobile) if payload.mobile else None
    conditions = [c for c in (CompanyContact.mobile_normalized == number if number else None, CompanyContact.email == payload.email if payload.email else None) if c is not None]
    if not conditions:
        return False
    where = [CompanyContact.merged_into_id.is_(None), *([CompanyContact.company_id != company_id] if company_id else [])]
    return await db.scalar(select(func.count()).select_from(CompanyContact).where(or_(*conditions), *where)) > 0


async def _create_company(db: AsyncSession, user: User, payload: RecCompanyCreate, batch_id: UUID) -> Company:
    """`create_company`'s steps: the recruiter's own, else the unassigned queue (I7). The duplicate check is this engine's match."""
    values = payload.model_dump(include=set(REC_COMPANY_FIELDS))
    values.update({k: [] for k in REC_CONTEXT_LIST_LABELS if values[k] is None})
    company = Company(**values, created_by_user_id=user.id)
    if user.role == ROLE:
        company.assigned_recruiter_user_id = user.id
    db.add(company)
    await db.flush()
    companies.audit(db, user, "create", company.id, {"code": company.company_code, "fields": sorted(k for k, v in values.items() if v not in (None, [])), "import_batch_id": str(batch_id)})
    return company


async def run(db: AsyncSession, user: User, rows: list[tuple[int, dict[str, str]]], batch_id: UUID | None = None) -> list[dict]:
    """Each row's outcome in file order. Without `batch_id` (the preview) nothing is written and a new record is `new`; with it each row runs in its own savepoint."""
    catalogues = await _catalogues(db)
    parsed = [(line, cells, parse_row(cells, catalogues)) for line, cells in rows]
    known = await _stored_companies(db, user, {companies.name_key(p[0].name) for _, _, p in parsed if not isinstance(p, str)})
    results = []
    for line, cells, payload in parsed:
        result = {
            "row_number": line, "status": "error", "company_name": cells.get("company_name", "")[:NAME_LIMIT], "contact_name": cells.get("contact_name", "")[:NAME_LIMIT], "company": None,
            "contact": None, "company_outcome": None, "contact_outcome": None, "same_as_row": None, "reason": None,
        }  # fmt: skip
        results.append(result)
        if isinstance(payload, str):
            result["reason"] = payload
            continue
        try:
            if batch_id is None:
                await _apply(db, user, known, result, line, payload, None)
            else:
                async with db.begin_nested():
                    await _apply(db, user, known, result, line, payload, batch_id)
        except IntegrityError:  # a concurrent manual create took the name: match it, as a re-run would
            key = companies.name_key(payload[0].name)
            known.pop(key, None)
            known |= await _stored_companies(db, user, {key})
            if key not in known:
                raise
            async with db.begin_nested():
                await _apply(db, user, known, result, line, payload, batch_id)
        except HTTPException as exc:  # a rule the row broke once it ran (a role deactivated meanwhile): the savepoint undid the whole row
            if result["company_outcome"] == "created":
                known.pop(companies.name_key(payload[0].name), None)
            result.update(status="error", company=None, company_outcome=None, contact=None, contact_outcome=None, reason=str(exc.detail))
    return results


async def _apply(db: AsyncSession, user: User, known: dict[str, _Known], result: dict, line: int, payload: tuple, batch_id: UUID | None) -> None:
    company_in, contact_in = payload
    key = companies.name_key(company_in.name)
    entry = known.get(key)
    new_company = entry is None
    if new_company:
        entry = known[key] = _Known(line, name=" ".join(company_in.name.split()))
        result["company_outcome"] = "new"
        if batch_id is not None:
            company = await _create_company(db, user, company_in, batch_id)
            entry.id, entry.code, entry.name = company.id, company.company_code, company.name
            result["company_outcome"] = "created"
    else:
        result["company_outcome"] = "matched"
        result["same_as_row"] = entry.first_row
    result["company"] = _ref(entry)
    if contact_in is None:
        if new_company:
            result["status"] = "created" if batch_id is not None else "new"
        else:
            result["status"] = "matched"
            result["reason"] = (
                f"Same company as row {entry.first_row}" if entry.first_row else "Already a company" if entry.in_scope and not entry.archived
                else "Already a company (archived)" if entry.in_scope else "Already a company (another recruiter's)"
            )  # fmt: skip
        return
    if not entry.in_scope:
        result["reason"] = OTHER_RECRUITER.format(code=entry.code)
        return
    if entry.archived:
        result["reason"] = ARCHIVED.format(code=entry.code)
        return
    await _load_contacts(db, entry)
    matches, answers = _contact_keys(contact_in.mobile, contact_in.email, contact_in.name)
    found = next((entry.contacts[k] for k in matches if k in entry.contacts), None)
    if found:
        result["contact"] = {"id": str(found[0]), "name": found[1]} if found[0] else None
        result["contact_outcome"] = "matched"
        result["same_as_row"] = found[2] or result["same_as_row"]
        result["status"] = "matched"
        result["reason"] = f"Same contact as row {found[2]}" if found[2] else "Already a contact"
        return
    if entry.count >= REC_CONTACT_MAX:
        result["reason"] = AT_CAP
        return
    contact_id = None
    if batch_id is not None:
        company = await db.get(Company, entry.id) if new_company else await companies.load_scoped(db, user, entry.id, lock=True)  # each row: a failed row's savepoint gave the lock back
        contact = await contacts.add(db, user, company, contact_in)
        contact_id = contact.id
        result["contact"] = {"id": str(contact.id), "name": contact.name}
    entry.count += 1
    for answer in answers:
        entry.contacts.setdefault(answer, (contact_id, contact_in.name, line))
    result["contact_outcome"] = "created" if batch_id is not None else "new"
    result["status"] = "created" if batch_id is not None else "new"
    if await _elsewhere(db, entry.id, contact_in):
        result["reason"] = ALSO_ELSEWHERE


def counts(results: list[dict]) -> dict:
    tally = {status: sum(r["status"] == status for r in results) for status in ("new", "created", "matched", "error")}
    return {
        "total_rows": len(results), **{f"{status}_count": n for status, n in tally.items()},
        "companies_created": sum(r["company_outcome"] == "created" for r in results), "contacts_created": sum(r["contact_outcome"] == "created" for r in results),
    }  # fmt: skip


async def store(db: AsyncSession, batch: CrmImportBatch, results: list[dict]) -> None:
    tally = counts(results)
    for key in ("total_rows", "created_count", "matched_count", "error_count", "companies_created", "contacts_created"):
        setattr(batch, key, tally[key])
    db.add_all(
        CrmImportRow(
            batch_id=batch.id, row_number=r["row_number"], status=r["status"], reason=r["reason"], company_id=UUID(r["company"]["id"]) if r["company"] else None,
            contact_id=UUID(r["contact"]["id"]) if r["contact"] else None, company_created=r["company_outcome"] == "created", contact_created=r["contact_outcome"] == "created",
        )
        for r in results
    )  # fmt: skip
    await db.flush()


def summary(batch: CrmImportBatch, uploader: User) -> dict:
    return {
        "id": str(batch.id),
        "file_name": batch.file_name,
        "uploaded_by": {"id": str(uploader.id), "full_name": uploader.full_name},
        **{k: getattr(batch, k) for k in ("total_rows", "created_count", "matched_count", "error_count", "companies_created", "contacts_created", "created_at")},
    }


async def report(db: AsyncSession, user: User, batch: CrmImportBatch, *, replayed: bool = False) -> dict:
    """One shape for the commit, every replay and the history detail. Scope is read now: a company that left the caller's scope since is its code and name only (I10)."""
    uploader = await db.get(User, batch.uploaded_by_user_id)
    stmt = (select(CrmImportRow, Company, CompanyContact).outerjoin(Company, Company.id == CrmImportRow.company_id).outerjoin(CompanyContact, CompanyContact.id == CrmImportRow.contact_id)
            .where(CrmImportRow.batch_id == batch.id).order_by(CrmImportRow.row_number))  # fmt: skip
    found = (await db.execute(stmt)).all()
    ids = {company.id for _, company, _ in found if company}
    visible = set((await db.scalars(select(Company.id).where(Company.id.in_(ids), *await companies.caller_scope(db, user)))).all()) if ids else set()
    rows = []
    for row, company, contact in found:
        in_scope = company is not None and company.id in visible
        rows.append({
            "row_number": row.row_number, "status": row.status, "reason": row.reason, "company_outcome": "created" if row.company_created else ("matched" if company else None),
            "contact_outcome": "created" if row.contact_created else ("matched" if contact else None),
            "company": {"id": str(company.id), "code": company.company_code, "name": company.name, "in_scope": in_scope} if company else None,
            "contact": {"id": str(contact.id), "name": contact.name} if contact and in_scope else None,
        })  # fmt: skip
    return {**summary(batch, uploader), "replayed": replayed, "rows": rows}


def report_csv(body: dict) -> str:
    """I11: every text cell formula-escaped -- the names come from a file someone else filled in."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(REPORT_COLUMNS)
    for row in body["rows"]:
        company = row["company"] or {}
        contact = row["contact"] or {}
        writer.writerow([row["row_number"], row["status"], *(_safe_cell(v or "") for v in (company.get("code"), company.get("name"), contact.get("name"), row["reason"]))])
    return buffer.getvalue()
