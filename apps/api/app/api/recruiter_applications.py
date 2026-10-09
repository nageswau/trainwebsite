"""rec-017 (DEC-SCOPE-136, spec §3): candidates on a requirement, their per-requirement status and its history, and a candidate's
applications across requirements.

A requirement or application id resolves through rec-007's requirement scope (out of scope = 404); every write is one transaction --
scope, row lock, change, history/audit, one commit here."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import APPLICATION_STATUSES, ApplicationScreening, Candidate, Company, Job, JobApplication, User
from app.schemas import RecApplicationCreate, RecApplicationStatusChange, RecScreeningIn
from app.services import application_screening as screening
from app.services import applications as svc
from app.services import candidates
from app.services import recruiter_requirements as requirements

router = APIRouter(prefix="/recruiter", tags=["recruiter-applications"])


async def _item(db: AsyncSession, user: User, application: JobApplication) -> dict:
    await db.refresh(application)
    result = await db.scalar(select(ApplicationScreening.result).where(ApplicationScreening.application_id == application.id))
    return svc.item_out(user, application, await db.get(Candidate, application.candidate_id), screening.result_out(result))


@router.get("/requirements/{requirement_id}/candidates")
async def list_requirement_candidates(
    requirement_id: UUID,
    status: Literal[APPLICATION_STATUSES] | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await requirements.load_scoped(db, user, requirement_id)
    stmt = select(JobApplication, Candidate).join(Candidate, Candidate.id == JobApplication.candidate_id).where(JobApplication.job_id == job.id)
    if status:
        stmt = stmt.where(JobApplication.status == status)
    stmt = stmt.add_columns(ApplicationScreening.result).outerjoin(ApplicationScreening, ApplicationScreening.application_id == JobApplication.id)
    rows = (await db.execute(stmt.order_by(JobApplication.stage_changed_at.desc(), JobApplication.id))).all()
    return {
        "items": [svc.item_out(user, a, c, screening.result_out(result)) for a, c, result in rows],
        "statuses": svc.catalogue(),
        "can_add": svc.can_write(user) and job.status not in requirements.ENDED,
    }


@router.post("/requirements/{requirement_id}/candidates", status_code=201)
async def add_requirement_candidate(requirement_id: UUID, payload: RecApplicationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await requirements.load_scoped(db, user, requirement_id, lock=True)
    svc.require_writer(user, job.id, "add_requirement_candidate")
    if job.status in requirements.ENDED:
        raise HTTPException(409, "Candidates cannot be added to a closed or cancelled requirement")
    candidate = await db.scalar(select(Candidate).where(Candidate.id == payload.candidate_id, *candidates.pool_filter()).with_for_update(read=True))
    if candidate is None or candidate.archived_at is not None:
        raise HTTPException(422, "Choose an active candidate from the pool")
    application = await svc.create(db, user, job, candidate, payload.status, payload.note)
    svc.audit(db, user, "add", application, {"job_id": str(job.id), "candidate_id": str(candidate.id), "status": payload.status})
    await db.commit()
    svc.log("recruiter_application_added", user, application, status=payload.status)
    return {"application": await _item(db, user, application)}


@router.post("/applications/{application_id}/status")
async def change_application_status(application_id: UUID, payload: RecApplicationStatusChange, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    application, _job = await svc.load_scoped(db, user, application_id, lock=True)
    svc.require_writer(user, application.id, "change_application_status")
    previous = await svc.change_status(db, user, application, payload.status, payload.note)
    await svc.notify_student(db, application)
    svc.audit(db, user, "status", application, {"from": previous, "to": payload.status})
    await db.commit()
    svc.log("recruiter_application_status_changed", user, application, from_status=previous, to_status=payload.status)
    return {"application": await _item(db, user, application)}


@router.get("/applications/{application_id}/history")
async def application_history(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    application, _job = await svc.load_scoped(db, user, application_id)
    return {"items": await svc.history_out(db, application.id)}


@router.get("/applications/{application_id}/screening")
async def application_screening(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """rec-018 (SC8): the requirement's readers; salary and remarks never leave the recruiter module."""
    application, _job = await svc.load_scoped(db, user, application_id)
    return await screening.read(db, user, application)


@router.put("/applications/{application_id}/screening")
async def save_application_screening(application_id: UUID, payload: RecScreeningIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """rec-018 (SC3-SC7): one transaction -- scope, row lock, the screening, any status move with its history and notice, one commit."""
    application, _job = await svc.load_scoped(db, user, application_id, lock=True)
    svc.require_writer(user, application.id, "save_application_screening")
    sent = payload.model_dump()
    previous = await screening.save(db, user, application, sent)
    if previous:
        await svc.notify_student(db, application)
    await db.commit()
    svc.log("recruiter_application_screened", user, application, result=sent["result"], from_status=previous, to_status=application.status if previous else None)
    return {"screening": await screening.screening_out(db, await screening.current(db, application.id)), "application": await _item(db, user, application)}


@router.get("/candidates/{candidate_id}/applications")
async def candidate_applications(candidate_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A candidate's status per requirement (§12: different statuses for different companies). Every candidate reader sees every row;
    `in_scope` says whether the requirement page opens for the caller."""
    candidates.require_reader(user)
    candidate = await candidates.load(db, candidate_id)
    rows = (
        await db.execute(
            select(JobApplication, Job, Company)
            .join(Job, Job.id == JobApplication.job_id)
            .join(Company, Company.id == Job.company_id)
            .where(JobApplication.candidate_id == candidate.id)
            .order_by(JobApplication.stage_changed_at.desc(), JobApplication.id)
        )
    ).all()
    in_scope: set = set()
    try:
        scope = await requirements.caller_scope(db, user)
    except HTTPException:  # a candidate reader with no requirement scope (hr_team) opens none of them
        scope = None
    if rows and scope is not None:
        ids = [job.id for _, job, _ in rows]
        in_scope = set((await db.scalars(select(Job.id).where(Job.id.in_(ids), *scope))).all())
    return {
        "items": [
            {
                "id": a.id,
                "requirement": {"id": job.id, "code": job.requirement_code, "title": job.title, "status_label": requirements.STATUS_LABELS[job.status]},
                "company": {"id": company.id, "name": company.name},
                "status": a.status,
                "status_label": svc.label(a.status),
                "stage_changed_at": a.stage_changed_at,
                "in_scope": job.id in in_scope,
            }
            for a, job, company in rows
        ]
    }
