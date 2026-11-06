"""hrc-006 (DEC-SCOPE-384): a requirement's owners -- the primary (`jobs.assigned_recruiter_user_id`), at most one placement-officer owner
and any collaborators (`job_assignments`) -- and their append-only history (`job_assignment_history`).

Functions only; nothing here commits or audits -- the route (or `admin.update_user`, `recruiter_lifecycle.reassign`) owns the transaction.
Callers lock the job row first; a target user is then read FOR SHARE (O9), so the job lock serialises every owner write of one job."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import AuditLog, Job, JobAssignment, JobAssignmentHistory, RecruiterProfile, User
from app.notifications.events import notify
from app.services.recruiter import ROLE
from app.services.recruiter_companies import person

OFFICER_ROLE = "placement_officer"
BACKUP = "backup"  # pob-002 (DEC-SCOPE-407 R9): the picker's role for `jobs.backup_owner_user_id` (not a job_assignments role)
ROLE_LABELS = {"primary": "Primary owner", "placement_officer": "Placement officer owner", "collaborator": "Collaborator"}
ELIGIBLE = {"collaborator": (ROLE, OFFICER_ROLE), "placement_officer": (OFFICER_ROLE,)}  # O3
INVALID = {"collaborator": "Choose an active recruiter or placement officer", "placement_officer": "Choose an active placement officer"}
IS_PRIMARY = "This person is the primary owner"
PRIMARY_STAYS = "A placement manager must reassign the primary owner first"
ALREADY = "Already an owner of this requirement"
ONE_OFFICER = "This requirement already has a placement officer owner"
NOT_OWNER = "This person is not an owner of this requirement"


def jobs_of(*user_condition):
    """The ids of the jobs the matching users are assignees of -- the scope join (index `(user_id, job_id)`)."""
    return select(JobAssignment.job_id).where(*user_condition)


async def people(db: AsyncSession, job: Job, *, also: tuple = (), without: tuple = ()) -> list[User]:
    """hrc-009/hrc-032: who a notice about this vacancy goes to -- its primary and assignees, `also` these, never `without` these."""
    assignees = (await db.scalars(select(JobAssignment.user_id).where(JobAssignment.job_id == job.id))).all()
    ids = {job.assigned_recruiter_user_id, *assignees, *also} - {None, *without}
    return list((await db.scalars(select(User).where(User.id.in_(ids)))).all())


async def notify_assigned(db: AsyncSession, actor: User | None, job: Job, target_id: UUID) -> None:
    """hrc-032 (N3): the person now on the vacancy, unless they did it themselves."""
    if actor is None or target_id != actor.id:
        await notify(db, [await db.get(User, target_id)], "it.requirement.assigned", job.id, action_url=f"/recruiter/requirements/{job.id}")


def _record(db: AsyncSession, job_id: UUID, user_id: UUID, role: str, action: str, actor: User | None, reason: str | None = None) -> None:
    """clock_timestamp, not now(): rows of one transaction keep the order they were written in."""
    db.add(JobAssignmentHistory(job_id=job_id, user_id=user_id, role=role, action=action, reason=reason, changed_by_user_id=actor.id if actor else None,
                                created_at=func.clock_timestamp()))  # fmt: skip


def record_primary(db: AsyncSession, actor: User | None, job: Job) -> None:
    """A new requirement's primary (create paths), after the job row is flushed."""
    if job.assigned_recruiter_user_id:
        _record(db, job.id, job.assigned_recruiter_user_id, "primary", "added", actor)


async def set_primary(db: AsyncSession, actor: User, job: Job, target_id: UUID) -> None:
    """O7: the primary moves (the caller validated the target); a target who held another role on the job gives it up."""
    row = await db.scalar(select(JobAssignment).where(JobAssignment.job_id == job.id, JobAssignment.user_id == target_id).with_for_update())
    if row is not None:
        _record(db, job.id, target_id, row.role, "removed", actor, "reassign")
        await db.delete(row)
    if job.assigned_recruiter_user_id:
        _record(db, job.id, job.assigned_recruiter_user_id, "primary", "removed", actor, "reassign")
    if job.backup_owner_user_id == target_id:  # pob-002 (DEC-SCOPE-407 R9): the backup promoted is no longer the backup
        job.backup_owner_user_id = None
    job.assigned_recruiter_user_id = target_id
    _record(db, job.id, target_id, "primary", "added", actor, "reassign")
    await notify_assigned(db, actor, job, target_id)


def _eligible_users(role: str) -> list:
    """Active users of the role's kinds; a recruiter needs a profile (rec-001), as everywhere in the recruiter CRM."""
    return [User.active.is_(True), User.role.in_(ELIGIBLE[role]), or_(User.role == OFFICER_ROLE, User.id.in_(select(RecruiterProfile.user_id)))]


async def add(db: AsyncSession, actor: User, job: Job, user_id: UUID, role: str) -> User:
    """O3: 409 for the primary, an existing owner or a second placement-officer owner; 422 for anyone else ineligible."""
    if user_id == job.assigned_recruiter_user_id:
        raise HTTPException(409, IS_PRIMARY)
    target = await db.scalar(select(User).where(User.id == user_id, *_eligible_users(role)).with_for_update(read=True))
    if target is None:
        raise HTTPException(422, INVALID[role])
    if await db.scalar(select(JobAssignment.id).where(JobAssignment.job_id == job.id, JobAssignment.user_id == user_id)):
        raise HTTPException(409, ALREADY)
    if role == OFFICER_ROLE and await db.scalar(select(JobAssignment.id).where(JobAssignment.job_id == job.id, JobAssignment.role == OFFICER_ROLE)):
        raise HTTPException(409, ONE_OFFICER)
    db.add(JobAssignment(job_id=job.id, user_id=user_id, role=role, added_by_user_id=actor.id))
    _record(db, job.id, user_id, role, "added", actor)
    return target


async def remove(db: AsyncSession, actor: User, job: Job, user_id: UUID) -> tuple[User, str]:
    """O6: never the primary (edge case E); returns the person and the role they held."""
    if user_id == job.assigned_recruiter_user_id:
        raise HTTPException(409, PRIMARY_STAYS)
    row = await db.scalar(select(JobAssignment).where(JobAssignment.job_id == job.id, JobAssignment.user_id == user_id))
    if row is None:
        raise HTTPException(404, NOT_OWNER)
    _record(db, job.id, user_id, row.role, "removed", actor)
    await db.delete(row)
    return await db.get(User, user_id), row.role


async def release(db: AsyncSession, actor: User, user: User) -> int:
    """O8: a deactivated user leaves every job they co-own (the primary was reassigned first, rec-037). Returns the count."""
    rows = (await db.scalars(select(JobAssignment).where(JobAssignment.user_id == user.id).order_by(JobAssignment.job_id).with_for_update())).all()
    for row in rows:
        _record(db, row.job_id, user.id, row.role, "removed", actor, "deactivated")
        await db.delete(row)
    # pob-002 (DEC-SCOPE-407 R9): and stops being a backup owner -- one audit row per job (the hrc-004 History shows it), not a co-owner row
    backups = (await db.scalars(select(Job).where(Job.backup_owner_user_id == user.id).order_by(Job.id).with_for_update())).all()
    for job in backups:
        job.backup_owner_user_id = None
        db.add(AuditLog(user_id=actor.id, action="recruiter_requirement.backup_released", entity_type="job", entity_id=str(job.id),
                        metadata_json={"user_id": str(user.id), "changes": {"backup_owner": [user.full_name, None]}}))  # fmt: skip
    return len(rows) + len(backups)


async def owners_out(db: AsyncSession, job_id: UUID) -> list[dict]:
    """The detail's `owners`: the placement-officer owner first, then the collaborators by name."""
    Adder = aliased(User)
    stmt = (
        select(JobAssignment, User, Adder)
        .join(User, User.id == JobAssignment.user_id)
        .join(Adder, Adder.id == JobAssignment.added_by_user_id)
        .where(JobAssignment.job_id == job_id)
        .order_by(JobAssignment.role.desc(), User.full_name, User.id)
    )
    return [
        {"user": {**person(u), "email": u.email}, "role": a.role, "role_label": ROLE_LABELS[a.role], "added_by": person(adder), "added_at": a.created_at}
        for a, u, adder in (await db.execute(stmt)).all()
    ]


async def options(db: AsyncSession, job: Job, role: str, matching: list, limit: int) -> dict:
    """The picker: eligible people not already on the job. pob-002 (R9): `backup` = active recruiters other than the primary and the backup
    (a collaborator may become the backup)."""
    if role == BACKUP:
        filters = [User.active.is_(True), User.role == ROLE, User.id.in_(select(RecruiterProfile.user_id)), *matching]
        filters += [User.id != u for u in (job.assigned_recruiter_user_id, job.backup_owner_user_id) if u]
    else:
        filters = [*_eligible_users(role), User.id.not_in(select(JobAssignment.user_id).where(JobAssignment.job_id == job.id)), *matching]
        if job.assigned_recruiter_user_id:
            filters.append(User.id != job.assigned_recruiter_user_id)
    total = await db.scalar(select(func.count()).select_from(User).where(*filters)) or 0
    rows = (await db.scalars(select(User).where(*filters).order_by(User.full_name, User.id).limit(limit))).all()
    return {"items": [{"id": u.id, "full_name": u.full_name, "email": u.email, "role": u.role} for u in rows], "total": total}


async def history(db: AsyncSession, job_id: UUID, *, limit: int, offset: int) -> dict:
    """Newest first; `changed_by` null = the system (0261's backfill)."""
    Actor = aliased(User)
    where = JobAssignmentHistory.job_id == job_id
    total = await db.scalar(select(func.count()).select_from(JobAssignmentHistory).where(where)) or 0
    stmt = (
        select(JobAssignmentHistory, User, Actor)
        .join(User, User.id == JobAssignmentHistory.user_id)
        .outerjoin(Actor, Actor.id == JobAssignmentHistory.changed_by_user_id)
        .where(where)
        .order_by(JobAssignmentHistory.created_at.desc(), JobAssignmentHistory.id)
        .limit(limit)
        .offset(offset)
    )
    items = [
        {"id": h.id, "user": person(u), "role": h.role, "role_label": ROLE_LABELS[h.role], "action": h.action, "reason": h.reason,
         "changed_by": person(actor), "created_at": h.created_at}
        for h, u, actor in (await db.execute(stmt)).all()
    ]  # fmt: skip
    return {"items": items, "total": total, "limit": limit, "offset": offset}
