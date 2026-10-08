"""rec-009 (DEC-SCOPE-120, spec §5): the candidate master. Recruiters, placement managers and super_admin read and write the whole pool
(R11); hr_team reads. The role check runs before anything is read; a candidate outside the pool (services/candidates.pool_filter) is a 404.

Bodies are untyped dicts parsed by services/telecaller._parse, so a 422 is one sentence naming the field (the tel-002 idiom). Each write
is one transaction: role, row lock, rules, change, audit row, one commit here, then the log line. `duplicate-check` is declared before
`/{candidate_id}` so it never reaches the id routes."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.api.portfolio_certificates import HEADERS
from app.api.telecaller_catalogue import NOT_AN_OBJECT
from app.core.database import get_db
from app.models import Candidate, CandidateResume, RecCandidateSource, User
from app.notifications.phone import normalise_phone
from app.schemas import CANDIDATE_FIELD_LABELS, CandidateCreate, CandidateDetail, CandidatePage, CandidateStatus, CandidateUpdate
from app.services import candidates as svc
from app.services.telecaller import _parse

router = APIRouter(prefix="/recruiter/candidates", tags=["recruiter-candidates"])


def _body(model, payload):
    return _parse(model, payload, NOT_AN_OBJECT, CANDIDATE_FIELD_LABELS)


@router.get("", response_model=CandidatePage)
async def list_candidates(
    q: str | None = SEARCH,
    source_id: UUID | None = None,
    status: CandidateStatus | None = None,
    archived: bool = False,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Newest first. `q` matches the name, code or email, or the mobile's digits (S2-§13: the source is on every row)."""
    svc.require_reader(user)
    filters = [*svc.pool_filter(), Candidate.archived_at.is_not(None) if archived else Candidate.archived_at.is_(None)]
    pattern = like_pattern(q)
    if pattern:
        digits = "".join(ch for ch in q if ch.isdigit())
        columns = [Candidate.name.ilike(pattern, escape="\\"), Candidate.candidate_code.ilike(pattern, escape="\\"), Candidate.email.ilike(pattern, escape="\\")]
        if len(digits) >= 4:
            columns.append(Candidate.mobile_normalized.contains(digits, autoescape=True))
        filters.append(or_(*columns))
    if source_id:
        filters.append(Candidate.source_id == source_id)
    if status:
        filters.append(Candidate.status == status)
    stmt = select(Candidate, RecCandidateSource).join(RecCandidateSource, RecCandidateSource.id == Candidate.source_id).where(*filters)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(Candidate.created_at.desc(), Candidate.id.desc()).limit(limit).offset(offset))).all()
    return {"items": [svc.item_out(c, s) for c, s in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.get("/duplicate-check")
async def duplicate_check(
    mobile: Annotated[str | None, Query(max_length=40)] = None,
    email: Annotated[str | None, Query(max_length=255)] = None,
    exclude_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The form's live panel (on blur); the create and the edit re-check. An unparseable mobile matches nothing."""
    svc.require_writer(user)
    return {"matches": await svc.find_matches(db, *svc.keys(mobile, email), exclude_id=exclude_id)}


@router.post("", response_model=CandidateDetail, status_code=201)
async def create_candidate(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Q-07: a known mobile or email is the 409 panel, before and (by the unique indexes) under a race."""
    svc.require_writer(user)
    data = _body(CandidateCreate, payload).model_dump()
    await svc.active_source(db, data["source_id"])
    candidate = Candidate(**data, mobile_normalized=normalise_phone(data["mobile"]), created_by_user_id=user.id)  # email: lower-cased by the schema
    await svc.block_duplicates(db, candidate)
    candidate.candidate_code = await svc.next_code(db)
    db.add(candidate)
    await svc.flush_candidate(db, candidate)
    svc.audit(db, user, "create", candidate, {"fields": sorted(k for k, v in data.items() if v not in (None, []))})
    await db.commit()
    svc.log("candidate_created", user, candidate)
    return await svc.detail_out(db, user, candidate)


@router.get("/{candidate_id}", response_model=CandidateDetail)
async def get_candidate(candidate_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_reader(user)
    return await svc.detail_out(db, user, await svc.load(db, candidate_id))


@router.patch("/{candidate_id}", response_model=CandidateDetail)
async def update_candidate(candidate_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Partial. Moving to another source needs an active one; keeping a since-deactivated source is allowed (the rec-002 rule)."""
    svc.require_writer(user)
    changes = _body(CandidateUpdate, payload).model_dump(exclude_unset=True)
    candidate = await svc.load(db, candidate_id, lock=True)
    if candidate.archived_at is not None:
        raise HTTPException(409, svc.ARCHIVED)
    if changes.get("source_id", candidate.source_id) != candidate.source_id:
        await svc.active_source(db, changes["source_id"])
    fields = svc.apply_fields(candidate, changes)
    if {"mobile", "email"} & set(fields):
        await svc.block_duplicates(db, candidate)
    if fields:
        candidate.updated_by_user_id = user.id
        await svc.flush_candidate(db, candidate)
        svc.audit(db, user, "update", candidate, {"fields": fields})
    await db.commit()
    if fields:
        svc.log("candidate_updated", user, candidate, fields=fields)
    return await svc.detail_out(db, user, candidate)


async def _set_archived(db: AsyncSession, user: User, candidate_id: UUID, archive: bool) -> dict:
    svc.require_writer(user)
    candidate = await svc.load(db, candidate_id, lock=True)
    if (candidate.archived_at is not None) == archive:
        raise HTTPException(409, "This candidate is already archived" if archive else "This candidate is not archived")
    candidate.archived_at = datetime.now(UTC) if archive else None
    candidate.archived_by_user_id = user.id if archive else None
    candidate.updated_by_user_id = user.id
    action = "archive" if archive else "restore"
    svc.audit(db, user, action, candidate, {})
    await db.commit()
    svc.log(f"candidate_{action}d", user, candidate)
    return await svc.detail_out(db, user, candidate)


@router.post("/{candidate_id}/archive", response_model=CandidateDetail)
async def archive_candidate(candidate_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _set_archived(db, user, candidate_id, True)


@router.post("/{candidate_id}/restore", response_model=CandidateDetail)
async def restore_candidate(candidate_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _set_archived(db, user, candidate_id, False)


# --- resumes (AC4) ---------------------------------------------------------------------------------------------------------------
@router.put("/{candidate_id}/resume", status_code=201)
async def upload_resume(candidate_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A new version, current from now on. Not idempotent: each upload is a version (the form sends one per click). The file is stored
    before the row lock and discarded when the transaction fails."""
    svc.require_writer(user)
    await svc.load(db, candidate_id)  # 404 before reading a byte of an unknown candidate's upload
    data, content_type, file_name = await svc.read_resume(file)
    key = svc.store(data, content_type)
    try:
        candidate = await svc.load(db, candidate_id, lock=True)
        if candidate.archived_at is not None:
            raise HTTPException(409, svc.ARCHIVED)
        last = await db.scalar(select(func.max(CandidateResume.version)).where(CandidateResume.candidate_id == candidate.id))
        resume = CandidateResume(
            candidate_id=candidate.id,
            version=(last or 0) + 1,
            storage_key=key,
            content_type=content_type,
            file_name=file_name,
            size_bytes=len(data),
            uploaded_by_user_id=user.id,
        )
        db.add(resume)
        candidate.updated_by_user_id = user.id
        svc.audit(db, user, "resume_upload", candidate, {"version": resume.version, "content_type": content_type, "size_bytes": len(data)})
        await db.commit()
    except Exception:  # the 409, a lost race on the version pair, or a failed commit: nothing references the stored file
        await db.rollback()
        svc.discard(key)
        raise
    svc.log("candidate_resume_uploaded", user, candidate, version=resume.version)
    return {"version": resume.version, "file_name": file_name, "content_type": content_type, "size_bytes": len(data)}


@router.get("/{candidate_id}/resume/{version}")
async def download_resume(candidate_id: UUID, version: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Readers only. The audit row is committed before any byte leaves; the file name is built from the candidate code."""
    svc.require_reader(user)
    candidate = await svc.load(db, candidate_id)
    resume = await db.scalar(select(CandidateResume).where(CandidateResume.candidate_id == candidate.id, CandidateResume.version == version))
    if resume is None:
        raise HTTPException(404, "Resume version not found")
    data = svc.read_file(resume)
    svc.audit(db, user, "resume_download", candidate, {"version": version, "role": user.role})
    await db.commit()
    svc.log("candidate_resume_downloaded", user, candidate, version=version, role=user.role)
    filename = f"resume-{candidate.candidate_code}-v{version}.{svc.EXTENSION.get(resume.content_type, 'bin')}"
    return Response(content=data, media_type=resume.content_type, headers={**HEADERS, "Content-Disposition": f'attachment; filename="{filename}"'})
