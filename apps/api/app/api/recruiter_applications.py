"""rec-017 (DEC-SCOPE-136, spec §3): candidates on a requirement, their per-requirement status and its history, and a candidate's
applications across requirements.

A requirement or application id resolves through rec-007's requirement scope (out of scope = 404); every write is one transaction --
scope, row lock, change, history/audit, one commit here."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api import recruiter_screening
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import APPLICATION_STATUSES, ApplicationScreening, Candidate, Company, Job, JobApplication, User
from app.schemas import RecApplicationCreate, RecApplicationStatusChange, RecBulkShortlistIn, RecScreeningIn
from app.services import application_review as review
from app.services import application_screening as screening
from app.services import applications as svc
from app.services import candidates, joinings
from app.services import recruiter_requirements as requirements
from app.services import recruitment_drives as drives

router = APIRouter(prefix="/recruiter", tags=["recruiter-applications"])


async def _item(db: AsyncSession, user: User, application: JobApplication) -> dict:
    await db.refresh(application)
    result = await db.scalar(select(ApplicationScreening.result).where(ApplicationScreening.application_id == application.id))
    owner = await db.get(User, application.owner_user_id) if application.owner_user_id else None
    return svc.item_out(user, application, await db.get(Candidate, application.candidate_id), screening.result_out(result), owner)


@router.get("/requirements/{requirement_id}/candidates")
async def list_requirement_candidates(
    requirement_id: UUID,
    status: Literal[APPLICATION_STATUSES] | None = None,
    needs_review: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await requirements.load_scoped(db, user, requirement_id)
    owner = aliased(User)  # hrc-026 (A6): the owning recruiter, shown on each row
    stmt = (
        select(JobApplication, Candidate, owner)
        .join(Candidate, Candidate.id == JobApplication.candidate_id)
        .outerjoin(owner, owner.id == JobApplication.owner_user_id)
        .where(JobApplication.job_id == job.id)
    )
    if status:
        stmt = stmt.where(JobApplication.status == status)
    if needs_review:  # hrc-009 (R8): the review list
        stmt = stmt.where(JobApplication.needs_review_since.is_not(None))
    stmt = stmt.add_columns(ApplicationScreening.result).outerjoin(ApplicationScreening, ApplicationScreening.application_id == JobApplication.id)
    rows = (await db.execute(stmt.order_by(JobApplication.stage_changed_at.desc(), JobApplication.id))).all()
    return {
        "items": [svc.item_out(user, a, c, screening.result_out(result), o) for a, c, o, result in rows],
        "statuses": svc.catalogue(),
        "rejection_reasons": svc.reasons(),  # hrc-026 (A7): the Rejected move's required list
        "can_add": svc.can_write(user) and job.status not in requirements.ENDED,
        "needs_review_count": await db.scalar(
            select(func.count()).where(JobApplication.job_id == job.id, JobApplication.needs_review_since.is_not(None))
        ),
    }


@router.post("/requirements/{requirement_id}/candidates", status_code=201)
async def add_requirement_candidate(requirement_id: UUID, payload: RecApplicationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await requirements.load_scoped(db, user, requirement_id, lock=True)
    svc.require_writer(user, job.id, "add_requirement_candidate")
    if job.status in requirements.ENDED:
        raise HTTPException(409, "Candidates cannot be added to a closed or cancelled requirement")
    candidate = await db.scalar(select(Candidate).where(Candidate.id == payload.candidate_id, *candidates.pool_filter(user.id)).with_for_update(read=True))
    if candidate is None or candidate.archived_at is not None:
        raise HTTPException(422, "Choose an active candidate from the pool")
    if payload.drive_id is not None:
        await drives.check_tag(db, user, job, payload.drive_id)
    application = await svc.create(db, user, job, candidate, payload.status, payload.note, drive_id=payload.drive_id)
    svc.audit(db, user, "add", application, {"job_id": str(job.id), "candidate_id": str(candidate.id), "status": payload.status,
                                             **({"drive_id": str(payload.drive_id)} if payload.drive_id else {})})
    await db.commit()
    svc.log("recruiter_application_added", user, application, status=payload.status)
    return {"application": await _item(db, user, application)}


SKIPS = {  # pob-019 (DEC-SCOPE-437 T8): why a bulk shortlist left a candidate out
    "already_added": svc.DUPLICATE,
    "do_not_contact": "This candidate is marked Do Not Contact",
    "unavailable": "This candidate is not an active candidate in the pool",
}


def skip(candidate_id: UUID, reason: str) -> dict:
    return {"candidate_id": candidate_id, "reason": reason, "message": SKIPS[reason]}


@router.post("/requirements/{requirement_id}/candidates/bulk")
async def bulk_shortlist(requirement_id: UUID, payload: RecBulkShortlistIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """pob-019 (T7/T8, AC2): shortlist up to 50 candidates -- the single add's checks, each candidate added as Shortlisted, the rest skipped
    with a reason. One transaction, one commit; a concurrent add of the same pair hits the unique index and the whole batch is a 409 (retry).
    Not idempotent: a repeat reports `already_added`."""
    job = await requirements.load_scoped(db, user, requirement_id, lock=True)
    svc.require_writer(user, job.id, "bulk_shortlist")
    if job.status in requirements.ENDED:
        raise HTTPException(409, "Candidates cannot be added to a closed or cancelled requirement")
    found = {c.id: c for c in await db.scalars(
        select(Candidate).where(Candidate.id.in_(payload.candidate_ids), *candidates.pool_filter(user.id)).order_by(Candidate.id).with_for_update(read=True)
    )}  # fmt: skip
    there = set(await db.scalars(select(JobApplication.candidate_id).where(JobApplication.job_id == job.id, JobApplication.candidate_id.in_(list(found)))))
    added, skipped = [], []
    for candidate_id in payload.candidate_ids:
        candidate = found.get(candidate_id)
        if candidate is None or candidate.archived_at is not None:
            skipped.append(skip(candidate_id, "unavailable"))
        elif candidate_id in there:
            skipped.append(skip(candidate_id, "already_added"))
        elif candidate.status == "do_not_contact":
            skipped.append(skip(candidate_id, "do_not_contact"))
        else:
            application = await svc.create(db, user, job, candidate, "shortlisted", payload.note)
            svc.audit(db, user, "add", application, {"job_id": str(job.id), "candidate_id": str(candidate.id), "status": "shortlisted", "bulk": True})
            added.append({"candidate_id": candidate.id, "application_id": application.id})
    await db.commit()
    svc.logger.info("recruiter_applications_bulk_added", extra={"extra_fields": {"actor_id": str(user.id), "job_id": str(job.id), "added": len(added), "skipped": len(skipped)}})
    return {"added": added, "skipped": skipped}


@router.post("/applications/{application_id}/status")
async def change_application_status(application_id: UUID, payload: RecApplicationStatusChange, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    application, _job = await svc.load_scoped(db, user, application_id, lock=True)
    svc.require_writer(user, application.id, "change_application_status")
    if payload.status == "joined" and await joinings.has_offer(db, application.id):
        raise HTTPException(409, joinings.USE_JOINING)  # rec-023 JN9: an offered candidate joins through the joining (actual date)
    seen = application.candidate_status
    previous = await svc.change_status(db, user, application, payload.status, payload.note, payload.rejection_reason)
    await svc.notify_student(db, application, seen)
    reason = {"rejection_reason": payload.rejection_reason} if payload.rejection_reason else {}
    svc.audit(db, user, "status", application, {"from": previous, "to": payload.status, "changes": {"status": [previous, payload.status]}, **reason})
    await db.commit()
    svc.log("recruiter_application_status_changed", user, application, from_status=previous, to_status=payload.status, **reason)
    return {"application": await _item(db, user, application)}


@router.post("/applications/{application_id}/confirm-review")
async def confirm_application_review(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """hrc-009 (R4/R9): keep a flagged application where it is after an eligibility change; 409 when it is not flagged."""
    application, _job = await svc.load_scoped(db, user, application_id, lock=True)
    svc.require_writer(user, application.id, "confirm_application_review")
    review.confirm(db, user, application)
    await db.commit()
    svc.log("recruiter_application_review_confirmed", user, application)
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
    await screening.keep_hidden_salary(db, user, application, sent, payload.model_fields_set)
    seen = application.candidate_status
    previous = await screening.save(db, user, application, sent)
    if previous:
        await svc.notify_student(db, application, seen)
    await db.commit()
    svc.log("recruiter_application_screened", user, application, result=sent["result"], from_status=previous, to_status=application.status if previous else None)
    return {"screening": await screening.screening_out(db, user, await screening.current(db, application.id)), "application": await _item(db, user, application)}


@router.get("/candidates/{candidate_id}/applications")
async def candidate_applications(candidate_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A candidate's status per requirement (§12: different statuses for different companies). Every candidate reader sees every row;
    `in_scope` says whether the requirement page opens for the caller."""
    candidates.require_reader(user)
    candidate = await candidates.load(db, candidate_id, viewer_id=user.id)
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
                "code": a.application_code,  # hrc-026 (A1)
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


router.include_router(recruiter_screening.router)  # pob-020
