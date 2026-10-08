"""rec-017 (DEC-SCOPE-135, spec §2): candidate + requirement tracking -- the only writer of `job_applications.status`.

Functions only; nothing here commits -- the route owns the transaction. The recruiter routes and the legacy workflows/employer routes all
come through here, so every change writes `job_application_status_history`. Explicit status writes use `change_status` (a move that is
not allowed is a 409); the legacy side effects (interviews, offers) use `follow`, which only moves when the move is allowed, so those
routes never start failing where they used to succeed (A2). Logs and audit rows carry ids and statuses, never a name or contact."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import APPLICATION_STATUSES, AuditLog, Candidate, Company, Job, JobApplication, JobApplicationStatusHistory, Notification, RecCandidateSource, User
from app.notifications.dispatch import queue_deliveries
from app.services import candidates, company_pipeline
from app.services import recruiter_requirements as requirements
from app.services.recruiter import ROLE

logger = logging.getLogger("app.recruiter")

LABELS = {
    "sourced": "Sourced", "screened": "Screened", "shortlisted": "Shortlisted", "profile_shared": "Profile Shared", "interview": "Interview",
    "selected": "Selected", "joined": "Joined", "rejected": "Rejected", "withdrawn": "Withdrawn",
}
LEGACY = {  # A1: the words the legacy routes have always written; migration 0120 repeats this map (test_rec_017_migration)
    "applied": "sourced", "screening": "screened", "shortlisted": "shortlisted", "interview_scheduled": "interview",
    "offer_received": "selected", "hired": "joined", "rejected": "rejected", "withdrawn": "withdrawn",
}
OPEN = ("sourced", "screened", "shortlisted", "profile_shared", "interview")
INITIAL = ("sourced", "screened", "shortlisted")  # what a recruiter may add a candidate at
TRANSITIONS = {  # A2: free moves among the open statuses; Joined only from Selected; Rejected / Withdrawn reopen to Sourced
    **{s: (*(o for o in OPEN if o != s), "selected", "rejected", "withdrawn") for s in OPEN},
    "selected": ("joined", "rejected", "withdrawn"),
    "joined": (),
    "rejected": ("sourced",),
    "withdrawn": ("sourced",),
}
WRITERS = (ROLE, "super_admin")  # rec-007's `can_edit` holders; the manager, BDM and hr_team read
NOT_FOUND = "Job application not found"
DUPLICATE = "This candidate is already on this requirement"
JOINED_GATE = "Joined needs the candidate to be Selected (an offer) first"
UNIQUE = "uq_job_applications_candidate_job"
STUDENT_SOURCE = "Edusphere students"  # the source migration 0120 backfills students from


def label(status: str) -> str:
    """A key no longer in the catalogue (history after a future change) is shown as stored."""
    return LABELS.get(status, status)


def from_legacy(word: str) -> str | None:
    """A legacy PATCH value or a new key -> the new key; None when it is neither."""
    return word if word in LABELS else LEGACY.get(word)


def check_transition(current: str, target: str) -> None:
    if target == current:
        raise HTTPException(409, f"The application is already {label(current)}")
    if target not in TRANSITIONS.get(current, ()):
        raise HTTPException(409, JOINED_GATE if target == "joined" else f"An application cannot move from {label(current)} to {label(target)}")


def _record(db: AsyncSession, actor: User | None, application: JobApplication, target: str, note: str | None) -> str:
    previous = application.status
    db.add(JobApplicationStatusHistory(application_id=application.id, from_status=previous, to_status=target, note=note, changed_by_user_id=actor.id if actor else None))
    application.status = target
    application.stage_changed_at = datetime.now(UTC)
    return previous


async def change_status(db: AsyncSession, actor: User | None, application: JobApplication, target: str, note: str | None = None) -> str:
    """Validated move + history; returns the previous status. The caller locked the row."""
    check_transition(application.status, target)
    return _record(db, actor, application, target, note)


def follow(db: AsyncSession, actor: User | None, application: JobApplication, target: str, note: str | None = None) -> bool:
    """A legacy side effect: move only when the move is allowed (A2). Returns whether it moved."""
    if target == application.status or target not in TRANSITIONS.get(application.status, ()):
        return False
    _record(db, actor, application, target, note)
    return True


# --- candidates for students (R6, A3, A4) -------------------------------------------------------------------------------------------
async def _student_source(db: AsyncSession) -> UUID:
    source_id = await db.scalar(select(RecCandidateSource.id).where(func.lower(RecCandidateSource.name) == STUDENT_SOURCE.lower()))
    if source_id is None:  # renamed or removed since migration 0120 seeded it
        source = RecCandidateSource(name=STUDENT_SOURCE)
        db.add(source)
        await db.flush()
        source_id = source.id
    return source_id


async def candidate_for_student(db: AsyncSession, student: User) -> Candidate:
    """The student's candidate: the linked one; else an unlinked candidate with their email or mobile, linked and kept in the pool (A3);
    else a new one outside the pool until they opt in (rec-010). A contact already used by another candidate is left off (Q-07)."""
    existing = await db.scalar(select(Candidate).where(Candidate.user_id == student.id))
    if existing:
        return existing
    mobile_key, email_key = candidates.keys(student.phone, student.email)
    matches = [func.lower(Candidate.email) == email_key] + ([Candidate.mobile_normalized == mobile_key] if mobile_key else [])
    match = await db.scalar(
        select(Candidate).where(Candidate.user_id.is_(None), or_(*matches)).order_by((func.lower(Candidate.email) == email_key).desc().nulls_last(), Candidate.created_at).limit(1)
    )
    if match:
        match.user_id, match.opted_in = student.id, True
        return match
    mobile_taken = mobile_key and await db.scalar(select(Candidate.id).where(Candidate.mobile_normalized == mobile_key))
    email_taken = await db.scalar(select(Candidate.id).where(func.lower(Candidate.email) == email_key))
    candidate = Candidate(
        candidate_code=await candidates.next_code(db),
        name=student.full_name[:160],
        email=None if email_taken else student.email,
        mobile=None if mobile_taken or not mobile_key else student.phone,
        mobile_normalized=None if mobile_taken else mobile_key,
        preferred_locations=[],
        source_id=await _student_source(db),
        user_id=student.id,
        opted_in=False,
        created_by_user_id=student.id,
    )
    db.add(candidate)
    await db.flush()
    return candidate


# --- create --------------------------------------------------------------------------------------------------------------------------
async def create(db: AsyncSession, actor: User, job: Job, candidate: Candidate, status: str = "sourced", note: str | None = None, resume_url: str | None = None) -> JobApplication:
    """One candidate on one requirement (409 on a duplicate, the unique index deciding a race), its first history row and rec-005's
    `candidates_sourcing` event on the company (forward only, so a company already further on never moves back)."""
    if await db.scalar(select(JobApplication.id).where(JobApplication.candidate_id == candidate.id, JobApplication.job_id == job.id)):
        raise HTTPException(409, DUPLICATE)
    application = JobApplication(
        job_id=job.id,
        candidate_id=candidate.id,
        student_id=candidate.user_id,
        status=status,
        resume_url=resume_url,
        added_by_user_id=None if actor.id == candidate.user_id else actor.id,
    )
    db.add(application)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if UNIQUE in str(exc.orig):
            raise HTTPException(409, DUPLICATE) from None
        raise
    db.add(JobApplicationStatusHistory(application_id=application.id, from_status=None, to_status=status, note=note, changed_by_user_id=actor.id))
    company = await db.scalar(select(Company).where(Company.id == job.company_id).with_for_update().execution_options(populate_existing=True))
    await company_pipeline.apply_event(db, company, "candidates_sourcing", actor)
    return application


# --- scope and permissions ----------------------------------------------------------------------------------------------------------
async def load_scoped(db: AsyncSession, user: User, application_id: UUID, *, lock: bool = False) -> tuple[JobApplication, Job]:
    """Through the requirement's scope (out of scope = the same 404 as missing). With `lock`, the row is locked by id first."""
    if lock:
        await db.execute(select(JobApplication.id).where(JobApplication.id == application_id).with_for_update())
    stmt = select(JobApplication, Job).join(Job, Job.id == JobApplication.job_id).where(JobApplication.id == application_id, *await requirements.caller_scope(db, user))
    row = (await db.execute(stmt.execution_options(populate_existing=True) if lock else stmt)).first()
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row[0], row[1]


def can_write(user: User) -> bool:
    return user.role in WRITERS


def require_writer(user: User, subject_id, route: str) -> None:
    if not can_write(user):
        logger.warning("recruiter_application_write_refused", extra={"extra_fields": {"actor_id": str(user.id), "subject_id": str(subject_id), "route": route}})
        raise HTTPException(403, "Only the recruiter on this requirement can change its candidates")


# --- notifications, audit, output ---------------------------------------------------------------------------------------------------
async def notify_student(db: AsyncSession, application: JobApplication) -> None:
    """ENH-014's in-app row plus queued deliveries, as the legacy PATCH always sent; external candidates have no login."""
    student = await db.get(User, application.student_id) if application.student_id else None
    if student is None:
        return
    item = Notification(user_id=student.id, title="Job application updated", body=f"Your application status is now {label(application.status)}.", read=False, action_url="/it/student/job-applications")
    db.add(item)
    await db.flush()
    await queue_deliveries(db, item, student)


def audit(db: AsyncSession, user: User, action: str, application: JobApplication, metadata: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id, action=f"recruiter_application.{action}", entity_type="job_application", entity_id=str(application.id), metadata_json=metadata or {}))


def log(event: str, user: User, application: JobApplication, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "application_id": str(application.id), "job_id": str(application.job_id), **extra}})


def allowed(application: JobApplication) -> list[dict]:
    return [{"key": s, "label": LABELS[s]} for s in TRANSITIONS.get(application.status, ())]


def item_out(user: User, application: JobApplication, candidate: Candidate) -> dict:
    return {
        "id": application.id,
        "job_id": application.job_id,
        "candidate": {"id": candidate.id, "code": candidate.candidate_code, "name": candidate.name},
        "status": application.status,
        "status_label": label(application.status),
        "stage_changed_at": application.stage_changed_at,
        "created_at": application.created_at,
        "allowed_statuses": allowed(application) if can_write(user) else [],
    }


async def history_out(db: AsyncSession, application_id: UUID) -> list[dict]:
    rows = (
        await db.execute(
            select(JobApplicationStatusHistory, User)
            .outerjoin(User, User.id == JobApplicationStatusHistory.changed_by_user_id)
            .where(JobApplicationStatusHistory.application_id == application_id)
            .order_by(JobApplicationStatusHistory.created_at.desc(), JobApplicationStatusHistory.id)
        )
    ).all()
    return [
        {
            "from_status": h.from_status,
            "from_label": label(h.from_status) if h.from_status else None,
            "to_status": h.to_status,
            "to_label": label(h.to_status),
            "note": h.note,
            "changed_by": {"id": u.id, "full_name": u.full_name} if u else None,
            "created_at": h.created_at,
        }
        for h, u in rows
    ]


def catalogue() -> list[dict]:
    return [{"key": s, "label": LABELS[s], "initial": s in INITIAL} for s in APPLICATION_STATUSES]
