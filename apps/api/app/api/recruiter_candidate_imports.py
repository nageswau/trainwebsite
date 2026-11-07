"""hrc-013 (DEC-SCOPE-391, spec docs/superpowers/specs/2026-11-04-hrc-013-candidate-bulk-import-design.md): candidate bulk import.

`preview` checks a file and writes nothing (I5); the commit sends the same file with an Idempotency-Key and creates, matches or rejects each
row in one transaction (I6/I7). A repeated key or the same file replays the stored report (I8). Imports run one at a time. Every route needs
`candidates.import` (I1); the history and reports are the caller's own, or everyone's for a placement manager and super_admin (I11)."""

import csv
import hashlib
import io
import time
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Response, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE
from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.school_bulk import IN_PROGRESS, KEY_PATTERN, KEY_REUSED, LOCK_TIMEOUT, _lock_timed_out
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, BdmOrganization, CandidateImportBatch, InstitutionDataPermission, RecCandidateSource, User
from app.services import candidate_import as imports
from app.services import candidate_privacy as privacy
from app.services import candidates as svc
from app.services.recruiter import MANAGER_ROLE

logger = get_logger("app.candidates")
router = APIRouter(prefix="/recruiter/candidate-imports", tags=["recruiter-candidates"])
LOCK_KEY = 290_013  # pg_advisory_xact_lock key serialising candidate imports (a fixed constant, bound as a parameter)
NOT_FOUND = "Import not found"
SEE_ALL = frozenset({MANAGER_ROLE, "super_admin"})


def _scope(user: User) -> list:
    return [] if user.role in SEE_ALL else [CandidateImportBatch.uploaded_by_user_id == user.id]


def _institution(permission, org, notice_status: str) -> dict:
    """pob-014 S7: what each created row is stamped with."""
    columns = {"institution_org_id": org.id, "institution_permission_id": permission.id, "institution_notice_status": notice_status}
    return {"columns": columns, "college": org.name[:200]}


async def _rows(file: UploadFile) -> tuple[bytes, list]:
    raw = await file.read(imports.MAX_BYTES + 1)
    return raw, imports.read_file(file.filename or "", raw)


@router.get("/template")
async def template(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await imports.require_importer(db, user)
    buffer = io.StringIO()
    csv.writer(buffer).writerow(imports.COLUMNS)
    return Response(content=buffer.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=candidate-import-template.csv", **NO_STORE})  # fmt: skip


@router.post("/preview")
async def preview(
    file: UploadFile = File(...),
    source_id: UUID = Form(...),
    institution_permission_id: UUID | None = Form(None),  # pob-014 (DEC-SCOPE-425 S7)
    notice_status: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """I5: every row's outcome if the file were imported now. Read only: no batch, row, candidate or audit is written."""
    await imports.require_importer(db, user)
    if institution_permission_id:
        await imports.usable_permission(db, user, institution_permission_id, notice_status)
    _, rows = await _rows(file)
    await svc.active_source(db, source_id)
    results = await imports.run(db, user, source_id, rows)
    return {**imports.counts(results), "rows": imports.shown(results)}


async def _replay(db: AsyncSession, user: User, key: str, digest: str, source_id: UUID, permission_id: UUID | None) -> CandidateImportBatch | None:
    """I8: the batch this key made (422 when it was another file, source or -- pob-014 -- permission), else the same file, source and
    permission imported under another key."""
    mine = CandidateImportBatch.uploaded_by_user_id == user.id
    batch = await db.scalar(select(CandidateImportBatch).where(mine, CandidateImportBatch.idempotency_key == key))
    if batch is not None:
        if (batch.file_sha256, batch.source_id, batch.institution_permission_id) != (digest, source_id, permission_id):
            raise HTTPException(422, KEY_REUSED)
        return batch
    same = (CandidateImportBatch.file_sha256 == digest, CandidateImportBatch.source_id == source_id, CandidateImportBatch.institution_permission_id.is_not_distinct_from(permission_id))
    return await db.scalar(select(CandidateImportBatch).where(mine, *same).order_by(CandidateImportBatch.created_at).limit(1))


@router.post("", status_code=201)
async def commit(
    file: UploadFile = File(...),
    source_id: UUID = Form(...),
    lawful_basis: str | None = Form(None),  # hrc-035 (DEC-SCOPE-396 K1): optional for older clients; the import form requires it
    institution_permission_id: UUID | None = Form(None),  # pob-014 (DEC-SCOPE-425 S7)
    notice_status: str | None = Form(None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """I6: 201 with the per-row report; a bad file, key or source is 422 before any row (nothing is created)."""
    started = time.monotonic()
    await imports.require_importer(db, user)
    lawful_basis = privacy.basis(lawful_basis or None)
    if not idempotency_key:
        raise HTTPException(422, "Idempotency-Key header is required")
    if not KEY_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(422, "Idempotency-Key must be 1-120 letters, digits or . _ : -")
    raw, rows = await _rows(file)
    digest = hashlib.sha256(raw).hexdigest()
    # `set_config(..., true)` is SET LOCAL with a bound parameter: it bounds the import lock and every row lock below.
    await db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": LOCK_TIMEOUT})
    try:
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
    except DBAPIError as exc:
        if _lock_timed_out(exc):
            raise HTTPException(409, IN_PROGRESS) from exc
        raise
    institution = None
    if institution_permission_id:  # after the import lock, held FOR SHARE to the commit: a concurrent revoke waits
        institution = _institution(*await imports.usable_permission(db, user, institution_permission_id, notice_status, lock=True), notice_status)
    if (batch := await _replay(db, user, idempotency_key, digest, source_id, institution_permission_id)) is not None:
        logger.info("candidate_import_replayed", extra={"extra_fields": {"actor_id": str(user.id), "batch_id": str(batch.id)}})
        return await imports.report(db, batch, user, replayed=True)
    await svc.active_source(db, source_id)
    batch = CandidateImportBatch(uploaded_by_user_id=user.id, source_id=source_id, idempotency_key=idempotency_key, file_sha256=digest,
                                 file_name=(file.filename or "upload")[:200], institution_permission_id=institution_permission_id)  # fmt: skip
    db.add(batch)
    await db.flush()
    try:
        results = await imports.run(db, user, source_id, rows, batch.id, institution)
    except DBAPIError as exc:
        if _lock_timed_out(exc):  # a person's row lock held past lock_timeout by a concurrent edit
            raise HTTPException(409, IN_PROGRESS) from exc
        raise
    created = [UUID(r["candidate"]["id"]) for r in results if r["status"] == "created"]
    privacy.record_staff_basis(db, user, created, "import", lawful_basis)  # hrc-035 K1: one row per created candidate
    await imports.store(db, batch, results)
    tally = {"created": batch.created_count, "matched": batch.matched_count, "error": batch.error_count}
    db.add(AuditLog(user_id=user.id, action="candidate.import", entity_type="candidate_import_batches", entity_id=str(batch.id),
                    metadata_json={"source_id": str(source_id), "total": batch.total_rows, **tally, "file_sha256": digest,
                                   "institution_permission_id": str(institution_permission_id) if institution_permission_id else None}))  # fmt: skip
    await db.commit()
    logger.info("candidate_import_completed", extra={"extra_fields": {
        "batch_id": str(batch.id), "actor_id": str(user.id), "total": batch.total_rows, **tally, "duration_ms": round((time.monotonic() - started) * 1000)}})  # fmt: skip
    return await imports.report(db, batch, user)


@router.get("")
async def history(limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """I11: newest first -- the caller's own, or everyone's for a placement manager and super_admin."""
    await imports.require_importer(db, user)
    filters = _scope(user)
    total = await db.scalar(select(func.count()).select_from(CandidateImportBatch).where(*filters))
    stmt = (select(CandidateImportBatch, User, RecCandidateSource, InstitutionDataPermission, BdmOrganization)
            .join(User, User.id == CandidateImportBatch.uploaded_by_user_id).join(RecCandidateSource, RecCandidateSource.id == CandidateImportBatch.source_id)
            .outerjoin(InstitutionDataPermission, InstitutionDataPermission.id == CandidateImportBatch.institution_permission_id)
            .outerjoin(BdmOrganization, BdmOrganization.id == InstitutionDataPermission.organization_id)
            .where(*filters).order_by(CandidateImportBatch.created_at.desc(), CandidateImportBatch.id.desc()).limit(limit).offset(offset))  # fmt: skip
    items = [imports.summary(batch, uploader, source, imports.permission_ref(permission, org)) for batch, uploader, source, permission, org in (await db.execute(stmt)).all()]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


async def _batch(db: AsyncSession, user: User, batch_id: UUID) -> CandidateImportBatch:
    await imports.require_importer(db, user)
    batch = await db.scalar(select(CandidateImportBatch).where(CandidateImportBatch.id == batch_id, *_scope(user)))
    if batch is None:
        raise HTTPException(404, NOT_FOUND)
    return batch


@router.get("/{batch_id}")
async def import_report(batch_id: UUID, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    response.headers.update(NO_STORE)
    return await imports.report(db, await _batch(db, user, batch_id), user)


@router.get("/{batch_id}/report.csv")
async def import_report_csv(batch_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    body = await imports.report(db, await _batch(db, user, batch_id), user)
    return Response(content=imports.report_csv(body), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=candidate-import-{batch_id}.csv", **NO_STORE})  # fmt: skip
