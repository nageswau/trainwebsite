"""rec-008 (DEC-SCOPE-132, spec §3): a Job Requirement's JD -- create/edit, upload, versions, download.

Every `{requirement_id}` resolves through `services.recruiter_requirements.load_scoped` (out of scope = 404, other roles 403), and writes
need the requirement's `can_edit` (403 wrong role, 409 cancelled). Each write is a new version (not idempotent, like rec-009's resumes):
requirement row lock, new version, audit row, one commit here, then the log line."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.portfolio_certificates import HEADERS
from app.core.database import get_db
from app.models import JobDescription, User
from app.schemas import RecJdCreate
from app.services import job_descriptions as svc
from app.services import recruiter_requirements as requirements

router = APIRouter(prefix="/recruiter/requirements", tags=["recruiter-job-descriptions"])


@router.get("/{requirement_id}/jd")
async def get_jd(requirement_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await requirements.load_scoped(db, user, requirement_id)
    return await svc.jd_out(db, user, job)


@router.post("/{requirement_id}/jd", status_code=201)
async def create_jd(requirement_id: UUID, payload: RecJdCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A new current version from the fields sent; the current version's file carries forward (JD4)."""
    job = await requirements.load_scoped(db, user, requirement_id, lock=True)
    requirements.require(user, job, "can_edit", "jd")
    previous = await svc.current(db, job.id)
    await svc.check_contact(db, job, payload.contact_id, previous.contact_id if previous else None)
    jd = await svc.add_version(db, user, job, payload.model_dump(), None)
    fields = sorted(k for k, v in payload.model_dump().items() if v is not None)
    svc.audit(db, user, "create", job, {"version": jd.version, "jd_number": jd.jd_number, "fields": fields})
    await db.commit()
    svc.log("job_description_created", user, job, version=jd.version)
    return await svc.jd_out(db, user, job)


@router.put("/{requirement_id}/jd/file", status_code=201)
async def upload_jd(requirement_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC1: the file becomes a new current version of this requirement's JD, carrying the current fields forward (or the requirement's).
    Scope and permission are checked before a byte is read; the file is stored before the row lock and discarded if the write fails."""
    requirements.require(user, await requirements.load_scoped(db, user, requirement_id), "can_edit", "jd")
    data, content_type, file_name = await svc.read_file(file)
    key = svc.store(data, content_type)
    try:
        job = await requirements.load_scoped(db, user, requirement_id, lock=True)
        requirements.require(user, job, "can_edit", "jd")
        stored = {"storage_key": key, "file_name": file_name, "content_type": content_type, "size_bytes": len(data)}
        jd = await svc.add_version(db, user, job, None, stored)
        svc.audit(db, user, "upload", job, {"version": jd.version, "jd_number": jd.jd_number, "content_type": content_type, "size_bytes": len(data)})
        await db.commit()
    except Exception:  # a refusal, a lost race on the version pair, or a failed commit: nothing references the stored file
        await db.rollback()
        svc.discard(key)
        raise
    svc.log("job_description_uploaded", user, job, version=jd.version)
    return await svc.jd_out(db, user, job)


@router.get("/{requirement_id}/jd/{version}/file")
async def download_jd(requirement_id: UUID, version: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Readers of the requirement. The audit row is committed before any byte leaves; the file name is built from the JD number."""
    job = await requirements.load_scoped(db, user, requirement_id)
    jd = await db.scalar(select(JobDescription).where(JobDescription.job_id == job.id, JobDescription.version == version))
    if jd is None or jd.storage_key is None:
        raise HTTPException(404, "This JD version has no file")
    data = svc.file_bytes(jd)
    svc.audit(db, user, "download", job, {"version": version, "role": user.role})
    await db.commit()
    svc.log("job_description_downloaded", user, job, version=version)
    return Response(content=data, media_type=jd.content_type, headers={**HEADERS, "Content-Disposition": f'attachment; filename="{svc.download_name(jd)}"'})
