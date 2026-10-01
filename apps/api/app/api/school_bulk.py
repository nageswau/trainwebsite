"""ENH-028 -- bulk data entry for Academic Results, Psychometric, Test Prep and Language records
(docs/superpowers/specs/2026-10-01-enh-028-bulk-data-entry-design.md, DEC-SCOPE-043).

One upload routine serves every module; a `BulkTarget` says what differs (role, row schema, duplicate key, tier service, how one
record is built). Each accepted row creates exactly what the module's single `POST` creates, so every reader is unaffected. Its
own router, like ENH-030's, so `schools.py` does not grow; it only imports from `schools.py`, never the reverse.
"""

import csv
import hashlib
import io
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import OUTSIDE_PORTFOLIO, TEST_PREP_SERVICE_KEYS, TIER_DENIED, _entitlement_denial, _notify_student_parents, _portfolio_school_ids, _today_ist
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import (
    AuditLog,
    School,
    SchoolAcademicResult,
    SchoolBulkUploadBatch,
    SchoolBulkUploadRow,
    SchoolLanguageRecord,
    SchoolPsychometricRecord,
    SchoolResultStatusHistory,
    SchoolStudent,
    SchoolTestPrepRecord,
    User,
)
from app.schemas import PSYCHOMETRIC_RESULT_KEYS, BulkLanguageRow, BulkPsychometricRow, BulkResultRow, BulkTestPrepRow, validation_message

router = APIRouter(prefix="/school", tags=["school-bulk"])
logger = get_logger("app.school.bulk")

MAX_FILE_BYTES = 1024 * 1024
MAX_ROWS = 500
LOCK_TIMEOUT = "5s"  # bounded wait for the key and student row locks (ENH-004/005/030 value); a bound parameter, never request input
KEY_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,120}")
STUDENT_COLUMNS = ("student_code", "student_name", "school_name")  # template columns; only student_code is read back

NOT_CSV = "The file must be a UTF-8 CSV"
KEY_REUSED = "Idempotency-Key was already used for a different file"
IN_PROGRESS = "This upload is still being processed; retry shortly"
STUDENTS_BUSY = "These students are being updated by another request; retry shortly"
UNKNOWN_CODE = "student_code does not match a student"


@dataclass(frozen=True)
class Created:
    record_id: UUID
    notice: tuple[str, str] | None = None  # (title, body) for the student's parents, sent after the batch commits


@dataclass(frozen=True)
class BulkTarget[RowT: BaseModel]:
    target_type: str
    role: str
    role_error: str  # the module's existing 403 message
    columns: tuple[str, ...]  # module columns, in template order
    required: tuple[str, ...]  # columns whose header must be present
    row_model: type[RowT]
    noun: str  # "a result", for the duplicate message
    key_fields: str  # "academic_year, term and subject"
    natural_key: Callable[[RowT], tuple]
    existing_keys: Callable[[AsyncSession, list[UUID]], Awaitable[set[tuple]]]  # {(student_id, *natural_key)}
    service_key: Callable[[RowT], str | None]  # tier service the row consumes; None = not tier-gated
    create: Callable[[AsyncSession, User, SchoolStudent, RowT, UUID], Awaitable[Created]]


# --- Results (SCH-006): always Draft, no tier gate, no parent notice (only Publish notifies) ----------------------------------


def _result_key(row: BulkResultRow) -> tuple:
    return (row.academic_year.casefold(), row.term.casefold(), row.subject.casefold())


async def _existing_results(db: AsyncSession, student_ids: list[UUID]) -> set[tuple]:
    rows = await db.execute(
        select(SchoolAcademicResult.school_student_id, SchoolAcademicResult.academic_year, SchoolAcademicResult.term, SchoolAcademicResult.subject).where(
            SchoolAcademicResult.school_student_id.in_(student_ids)
        )
    )
    return {(student_id, year.casefold(), term.casefold(), subject.casefold()) for student_id, year, term, subject in rows}


async def _create_result(db: AsyncSession, user: User, student: SchoolStudent, row: BulkResultRow, batch_id: UUID) -> Created:
    result = SchoolAcademicResult(
        school_student_id=student.id,
        academic_year=row.academic_year,
        term=row.term,
        subject=row.subject,
        max_marks=row.max_marks,
        marks_obtained=row.marks_obtained,
        grade=row.grade,
        teacher_remarks=row.teacher_remarks,
        status="draft",
        uploaded_by_user_id=user.id,
    )
    db.add(result)
    await db.flush()
    db.add(SchoolResultStatusHistory(result_id=result.id, from_status="none", to_status="draft", changed_by_user_id=user.id))
    db.add(
        AuditLog(user_id=user.id, action="school.result_create", entity_type="school_academic_result", entity_id=str(result.id), metadata_json={"subject": row.subject, "bulk_batch_id": str(batch_id)})
    )
    return Created(result.id)


RESULTS: BulkTarget[BulkResultRow] = BulkTarget(
    target_type="academic_result",
    role="academic_team",
    role_error="Academic Team role required",
    columns=("academic_year", "term", "subject", "max_marks", "marks_obtained", "grade", "teacher_remarks"),
    required=("academic_year", "term", "subject", "max_marks", "marks_obtained"),
    row_model=BulkResultRow,
    noun="a result",
    key_fields="academic_year, term and subject",
    natural_key=_result_key,
    existing_keys=_existing_results,
    service_key=lambda row: None,
    create=_create_result,
)


# --- Psychometric (SCH-005 + ENH-027 result fields): status by report_url, parents told it was assigned or is ready ------------


def _psychometric_key(row: BulkPsychometricRow) -> tuple:
    return (row.assessment_type.casefold(), row.test_date)


async def _existing_psychometric(db: AsyncSession, student_ids: list[UUID]) -> set[tuple]:
    rows = await db.execute(
        select(SchoolPsychometricRecord.school_student_id, SchoolPsychometricRecord.assessment_type, SchoolPsychometricRecord.test_date).where(
            SchoolPsychometricRecord.school_student_id.in_(student_ids)
        )
    )
    return {(student_id, assessment_type.casefold(), test_date) for student_id, assessment_type, test_date in rows}


async def _create_psychometric(db: AsyncSession, user: User, student: SchoolStudent, row: BulkPsychometricRow, batch_id: UUID) -> Created:
    record = SchoolPsychometricRecord(
        school_student_id=student.id,
        psychometric_team_user_id=user.id,
        assessment_type=row.assessment_type,
        report_url=row.report_url,
        status="completed" if row.report_url else "assigned",
        **{name: getattr(row, name) for name in PSYCHOMETRIC_RESULT_KEYS},
    )
    fields = sorted(name for name in PSYCHOMETRIC_RESULT_KEYS if getattr(row, name) is not None)  # names only, as the single create audits
    db.add(record)
    await db.flush()
    db.add(
        AuditLog(
            user_id=user.id,
            action="school.psychometric_record_create",
            entity_type="school_psychometric_record",
            entity_id=str(record.id),
            metadata_json={"assessment_type": row.assessment_type, "fields": fields, "bulk_batch_id": str(batch_id)},
        )
    )
    if record.status == "completed":
        notice = (f"Psychometric report ready for {student.full_name}", f"The {row.assessment_type} report for {student.full_name} is now available.")
    else:
        notice = (f"Psychometric assessment assigned to {student.full_name}", f"{student.full_name} has been assigned a {row.assessment_type}.")
    return Created(record.id, notice)


PSYCHOMETRIC: BulkTarget[BulkPsychometricRow] = BulkTarget(
    target_type="psychometric_record",
    role="psychometric_team",
    role_error="Psychometric Team role required",
    columns=("assessment_type", "report_url", *PSYCHOMETRIC_RESULT_KEYS),
    required=("assessment_type",),
    row_model=BulkPsychometricRow,
    noun="an assessment",
    key_fields="assessment_type and test_date",
    natural_key=_psychometric_key,
    existing_keys=_existing_psychometric,
    service_key=lambda row: "psychometric_test",
    create=_create_psychometric,
)


# --- Test Prep and Language (SCH-009): each row consumes its own tier service ---------------------------------------------------


async def _existing_test_prep(db: AsyncSession, student_ids: list[UUID]) -> set[tuple]:
    rows = await db.execute(select(SchoolTestPrepRecord.school_student_id, SchoolTestPrepRecord.test_type).where(SchoolTestPrepRecord.school_student_id.in_(student_ids)))
    return {(student_id, test_type) for student_id, test_type in rows}


async def _create_test_prep(db: AsyncSession, user: User, student: SchoolStudent, row: BulkTestPrepRow, batch_id: UUID) -> Created:
    record = SchoolTestPrepRecord(school_student_id=student.id, academic_team_user_id=user.id, test_type=row.test_type, target_score=row.target_score)
    db.add(record)
    await db.flush()
    db.add(
        AuditLog(
            user_id=user.id,
            action="school.test_prep_record_create",
            entity_type="school_test_prep_record",
            entity_id=str(record.id),
            metadata_json={"test_type": row.test_type, "bulk_batch_id": str(batch_id)},
        )
    )
    name, test = student.full_name, row.test_type.upper()
    return Created(record.id, (f"{test} preparation started for {name}", f"{name} has started {test} preparation."))


TEST_PREP: BulkTarget[BulkTestPrepRow] = BulkTarget(
    target_type="test_prep_record",
    role="academic_team",
    role_error="Academic Team role required",
    columns=("test_type", "target_score"),
    required=("test_type",),
    row_model=BulkTestPrepRow,
    noun="a test preparation record",
    key_fields="test_type",
    natural_key=lambda row: (row.test_type,),
    existing_keys=_existing_test_prep,
    service_key=lambda row: TEST_PREP_SERVICE_KEYS[row.test_type],
    create=_create_test_prep,
)


async def _existing_languages(db: AsyncSession, student_ids: list[UUID]) -> set[tuple]:
    rows = await db.execute(select(SchoolLanguageRecord.school_student_id, SchoolLanguageRecord.language).where(SchoolLanguageRecord.school_student_id.in_(student_ids)))
    return {(student_id, language.casefold()) for student_id, language in rows}


async def _create_language(db: AsyncSession, user: User, student: SchoolStudent, row: BulkLanguageRow, batch_id: UUID) -> Created:
    record = SchoolLanguageRecord(school_student_id=student.id, academic_team_user_id=user.id, language=row.language, level=row.level)
    db.add(record)
    await db.flush()
    db.add(
        AuditLog(
            user_id=user.id,
            action="school.language_record_create",
            entity_type="school_language_record",
            entity_id=str(record.id),
            metadata_json={"language": row.language, "bulk_batch_id": str(batch_id)},
        )
    )
    name = student.full_name
    return Created(record.id, (f"{row.language} classes started for {name}", f"{name} has started {row.language} classes."))


LANGUAGE: BulkTarget[BulkLanguageRow] = BulkTarget(
    target_type="language_record",
    role="academic_team",
    role_error="Academic Team role required",
    columns=("language", "level"),
    required=("language",),
    row_model=BulkLanguageRow,
    noun="a language record",
    key_fields="language",
    natural_key=lambda row: (row.language.casefold(),),
    existing_keys=_existing_languages,
    service_key=lambda row: "foreign_language_classes",
    create=_create_language,
)


# --- The upload routine (spec Â§7) ---------------------------------------------------------------------------------------------


def _file_error(target: BulkTarget, user: User, reason: str, message: str, status: int = 422) -> HTTPException:
    logger.info("bulk_upload_rejected_file", extra={"extra_fields": {"actor_id": str(user.id), "target_type": target.target_type, "reason": reason}})
    return HTTPException(status, message)


def _filled_rows(raw: bytes, target: BulkTarget, user: User) -> list[tuple[int, dict[str, str]]]:
    """(file line, {column: trimmed cell}) for every row with at least one module column filled. A template row the user left
    untouched (student columns only) is skipped, never reported."""
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _file_error(target, user, "encoding", NOT_CSV) from None
    if "\x00" in content:
        raise _file_error(target, user, "nul", NOT_CSV)
    reader = csv.reader(io.StringIO(content, newline=""), strict=True)
    try:
        header = [name.strip().lower() for name in next(reader, [])]
        missing = [name for name in ("student_code", *target.required) if name not in header]
        if missing:
            raise _file_error(target, user, "header", f"Missing required column: {missing[0]}")
        filled = []
        for cells in reader:
            row = {name: (cells[i] if i < len(cells) else "").strip() for i, name in enumerate(header) if name}
            if any(row.get(name) for name in target.columns):
                filled.append((reader.line_num, row))
    except csv.Error:
        raise _file_error(target, user, "malformed", NOT_CSV) from None
    if not filled:
        raise _file_error(target, user, "empty", "The file has no filled-in rows")
    if len(filled) > MAX_ROWS:
        raise _file_error(target, user, "too_many_rows", f"The file has more than {MAX_ROWS} filled-in rows")
    return filled


def _report(batch: SchoolBulkUploadBatch, rows: list[SchoolBulkUploadRow]) -> dict:
    return {
        "id": batch.id,
        "target_type": batch.target_type,
        "status": "completed",
        "total_rows": batch.total_rows,
        "accepted_count": batch.accepted_count,
        "rejected_count": batch.rejected_count,
        "rows": [{"row_number": r.row_number, "status": r.status, "error_message": r.error_message, "student_code": r.student_code, "created_record_id": r.created_record_id} for r in rows],
    }


def _lock_timed_out(exc: DBAPIError) -> bool:
    return getattr(exc.orig, "sqlstate", None) == "55P03"  # lock_not_available: the wait exceeded LOCK_TIMEOUT


async def _claim(db: AsyncSession, target: BulkTarget, user: User, key: str, digest: str) -> SchoolBulkUploadBatch | dict:
    """Insert the batch row; the unique (uploader, target, key) index decides between racing requests -- no select-then-insert.
    A request that loses waits for the winner's commit, then replays its report (same file) or refuses (different file)."""
    batch = SchoolBulkUploadBatch(target_type=target.target_type, uploaded_by_user_id=user.id, idempotency_key=key, file_sha256=digest, total_rows=0, accepted_count=0, rejected_count=0)
    try:
        async with db.begin_nested():
            db.add(batch)
            await db.flush()
        return batch
    except IntegrityError:
        pass
    except DBAPIError as exc:
        if _lock_timed_out(exc):
            logger.warning("bulk_upload_lock_timeout", extra={"extra_fields": {"actor_id": str(user.id), "target_type": target.target_type, "lock": "key"}})
            raise HTTPException(409, IN_PROGRESS) from exc
        raise
    existing = await db.scalar(
        select(SchoolBulkUploadBatch).where(SchoolBulkUploadBatch.uploaded_by_user_id == user.id, SchoolBulkUploadBatch.target_type == target.target_type, SchoolBulkUploadBatch.idempotency_key == key)
    )
    if existing is None or existing.file_sha256 != digest:
        raise HTTPException(422, KEY_REUSED)
    rows = (await db.scalars(select(SchoolBulkUploadRow).where(SchoolBulkUploadRow.batch_id == existing.id).order_by(SchoolBulkUploadRow.row_number))).all()
    logger.info("bulk_upload_replayed", extra={"extra_fields": {"actor_id": str(user.id), "target_type": target.target_type, "batch_id": str(existing.id)}})
    return _report(existing, list(rows))


async def _lock_students(db: AsyncSession, target: BulkTarget, user: User, codes: set[str]) -> dict[str, SchoolStudent]:
    """Lock every named student, ordered by id (the promotions pattern; student before result matches transfer approval's lock
    order, so no cycle). Two uploads of the same file under different keys serialize here, and the second sees the first's
    records as duplicates; a transfer racing the upload cannot change a student's school mid-batch."""
    if not codes:
        return {}
    try:
        students = (await db.scalars(select(SchoolStudent).where(SchoolStudent.student_code.in_(codes)).order_by(SchoolStudent.id).with_for_update())).all()
    except DBAPIError as exc:
        if _lock_timed_out(exc):
            logger.warning("bulk_upload_lock_timeout", extra={"extra_fields": {"actor_id": str(user.id), "target_type": target.target_type, "lock": "students"}})
            raise HTTPException(409, STUDENTS_BUSY) from exc
        raise
    return {s.student_code: s for s in students}


class _TierCheck:
    """`require_school_entitlement`'s rules without its commit-on-deny (which would commit half a batch): one decision per
    (school, service) per batch, and one denial audit row per denied pair, riding on the batch's own commit."""

    def __init__(self, db: AsyncSession, user: User):
        self.db, self.user = db, user
        self.decided: dict[tuple[UUID, str], str | None] = {}

    async def error(self, school_id: UUID, service_key: str | None) -> str | None:
        if service_key is None:
            return None
        if (school_id, service_key) not in self.decided:
            school = await self.db.get(School, school_id)
            denial = _entitlement_denial(school.tier if school else None, school.tier_valid_until if school else None, service_key, _today_ist())
            self.decided[(school_id, service_key)] = denial[1] if denial else None
            if denial:
                self.db.add(
                    AuditLog(
                        user_id=self.user.id,
                        action=TIER_DENIED,
                        entity_type="school",
                        entity_id=str(school_id),
                        outcome="denied",
                        metadata_json={"service_key": service_key, "reason": denial[0], "tier": school.tier if school else None},
                    )
                )
                logger.warning(
                    "tier_access_denied", extra={"extra_fields": {"actor_id": str(self.user.id), "role": self.user.role, "school_id": str(school_id), "service_key": service_key, "reason": denial[0]}}
                )
        return self.decided[(school_id, service_key)]


async def _notify_after_commit(db: AsyncSession, batch_id: UUID, notices: list[tuple[UUID, str, str]]) -> None:
    """The single create's parent notice for each accepted row, each in its own transaction (the ENH-026 pattern): a failed send
    never undoes a record. The student is re-read by id because a rollback expires every loaded object."""
    for student_id, title, body in notices:
        try:
            student = await db.get(SchoolStudent, student_id)
            if student is not None:  # locked for the whole batch, so it exists; the check only satisfies the type
                await _notify_student_parents(db, student, title=title, body=body, action_url=f"/school/parent/children/{student_id}")
                await db.commit()
        except Exception:
            await db.rollback()
            logger.warning("bulk_upload_notify_failed", extra={"extra_fields": {"batch_id": str(batch_id), "student_id": str(student_id)}})


async def _upload(target: BulkTarget, file: UploadFile, idempotency_key: str | None, user: User, db: AsyncSession) -> dict:
    started = time.monotonic()
    if user.role != target.role:
        raise HTTPException(403, target.role_error)
    if not idempotency_key:
        raise HTTPException(422, "Idempotency-Key header is required")
    if not KEY_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(422, "Idempotency-Key must be 1-120 letters, digits or . _ : -")
    raw = await file.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise _file_error(target, user, "too_large", "The file is larger than 1 MB", 413)
    filled = _filled_rows(raw, target, user)

    # `set_config(..., true)` is SET LOCAL with a bound parameter: it bounds both the key wait and the student row locks.
    await db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": LOCK_TIMEOUT})
    claimed = await _claim(db, target, user, idempotency_key, hashlib.sha256(raw).hexdigest())
    if isinstance(claimed, dict):
        return claimed
    batch = claimed

    students = await _lock_students(db, target, user, {cells.get("student_code", "").upper() for _, cells in filled} - {""})
    portfolio = await _portfolio_school_ids(db, user)
    existing = await target.existing_keys(db, [s.id for s in students.values() if s.school_id in portfolio])
    tier = _TierCheck(db, user)
    seen: dict[tuple, int] = {}
    rows: list[SchoolBulkUploadRow] = []
    notices: list[tuple[UUID, str, str]] = []
    for line, cells in filled:
        code = cells.get("student_code", "").upper()
        student = students.get(code)
        error, created = None, None
        if not code:
            error = "student_code is required"
        elif student is None:
            error = UNKNOWN_CODE
        elif student.school_id not in portfolio:
            error = OUTSIDE_PORTFOLIO
        else:
            try:
                row = target.row_model.model_validate(cells)
            except ValidationError as exc:
                error = validation_message(exc)
            else:
                key = (student.id, *target.natural_key(row))
                error = await tier.error(student.school_id, target.service_key(row))
                if error is None and key in existing:
                    error = f"this student already has {target.noun} for the same {target.key_fields}"
                elif error is None and key in seen:
                    error = f"same student and {target.key_fields} as row {seen[key]} of this file"
                elif error is None:
                    created = await target.create(db, user, student, row, batch.id)
                    seen[key] = line
                    if created.notice:
                        notices.append((student.id, *created.notice))
        outcome = SchoolBulkUploadRow(
            batch_id=batch.id,
            row_number=line,
            status="rejected" if error else "accepted",
            error_message=error,
            student_code=code if 0 < len(code) <= 8 else None,
            created_record_id=created.record_id if created else None,
        )
        db.add(outcome)
        rows.append(outcome)

    batch.total_rows = len(rows)
    batch.accepted_count = sum(r.status == "accepted" for r in rows)
    batch.rejected_count = batch.total_rows - batch.accepted_count
    db.add(
        AuditLog(
            user_id=user.id,
            action="school.bulk_upload",
            entity_type="school_bulk_upload_batch",
            entity_id=str(batch.id),
            metadata_json={"target_type": target.target_type, "total": batch.total_rows, "accepted": batch.accepted_count, "rejected": batch.rejected_count, "file_sha256": batch.file_sha256},
        )
    )
    await db.commit()
    report = _report(batch, rows)
    logger.info(
        "bulk_upload_completed",
        extra={
            "extra_fields": {
                "batch_id": str(batch.id),
                "target_type": target.target_type,
                "actor_id": str(user.id),
                "total": batch.total_rows,
                "accepted": batch.accepted_count,
                "rejected": batch.rejected_count,
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
        },
    )
    await _notify_after_commit(db, batch.id, notices)
    return report


# --- Pre-filled templates (spec Â§5.2) -----------------------------------------------------------------------------------------

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value: str) -> str:
    """Stored text (a coordinator-typed name) must not run as a formula when the template is opened in a spreadsheet."""
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value


async def _template(target: BulkTarget, user: User, db: AsyncSession) -> Response:
    if user.role != target.role:
        raise HTTPException(403, target.role_error)
    portfolio = await _portfolio_school_ids(db, user)
    students = (
        (
            await db.execute(
                select(SchoolStudent.student_code, SchoolStudent.full_name, School.name)
                .join(School, School.id == SchoolStudent.school_id)
                .where(SchoolStudent.school_id.in_(portfolio))
                .order_by(School.name, SchoolStudent.full_name)
            )
        ).all()
        if portfolio
        else []
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([*STUDENT_COLUMNS, *target.columns])
    for code, name, school in students:
        writer.writerow([code, _safe_cell(name), _safe_cell(school), *[""] * len(target.columns)])
    filename = f"{target.target_type.replace('_', '-')}-bulk-template.csv"
    return Response(content=buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}", "Cache-Control": "private, no-store"})


@router.get("/academic-team/results/bulk-template")
async def bulk_template_results(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _template(RESULTS, user, db)


@router.get("/psychometric-team/records/bulk-template")
async def bulk_template_psychometric(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _template(PSYCHOMETRIC, user, db)


@router.get("/academic-team/test-prep-records/bulk-template")
async def bulk_template_test_prep(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _template(TEST_PREP, user, db)


@router.get("/academic-team/language-records/bulk-template")
async def bulk_template_language(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _template(LANGUAGE, user, db)


@router.post("/academic-team/results/bulk-upload", status_code=201)
async def bulk_upload_results(
    file: UploadFile = File(...), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await _upload(RESULTS, file, idempotency_key, user, db)


@router.post("/psychometric-team/records/bulk-upload", status_code=201)
async def bulk_upload_psychometric(
    file: UploadFile = File(...), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await _upload(PSYCHOMETRIC, file, idempotency_key, user, db)


@router.post("/academic-team/test-prep-records/bulk-upload", status_code=201)
async def bulk_upload_test_prep(
    file: UploadFile = File(...), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await _upload(TEST_PREP, file, idempotency_key, user, db)


@router.post("/academic-team/language-records/bulk-upload", status_code=201)
async def bulk_upload_language(
    file: UploadFile = File(...), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await _upload(LANGUAGE, file, idempotency_key, user, db)
