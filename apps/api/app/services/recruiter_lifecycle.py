"""rec-037 (DEC-SCOPE-175, spec §2): recruiter deactivation and the placement manager's bulk reassignment of companies and requirements.

Functions only; nothing here commits -- the route (or `admin.update_user`) owns the transaction. Lock order (RC10): the source's companies
(by id), then its requirements (by id), then the target (FOR SHARE, rec-003 `locked_recruiter_target`) -- the assign routes' row-then-
recruiter order, so they cannot deadlock. Follow-ups belong to the company (rec-024 FU4) and move with it untouched. Logs and audit carry
ids and counts only."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, Job, RecruiterFollowUp, RecruiterProfile, User
from app.services import recruiter_companies, recruiter_requirements
from app.services.recruiter import ROLE

logger = logging.getLogger("app.recruiter")

NOT_FOUND = "Recruiter not found"
NOT_IN_TEAM = "This recruiter is not in your team"
NOTHING = "This recruiter has no companies or requirements to reassign"


def _plural(n: int, singular: str, plural: str | None = None) -> str:
    return f"{n} {singular if n == 1 else plural or singular + 's'}"


def _open_follow_ups(*where):
    return (
        select(Company.assigned_recruiter_user_id, func.count())
        .select_from(RecruiterFollowUp)
        .join(Company, Company.id == RecruiterFollowUp.company_id)
        .where(RecruiterFollowUp.status == "open", *where)
    )


async def work_counts(db: AsyncSession, user_ids: list[UUID]) -> dict[UUID, dict[str, int]]:
    """RC15: what a reassignment would move -- three grouped queries for a whole page."""
    counts = {uid: {"companies": 0, "requirements": 0, "follow_ups": 0} for uid in user_ids}
    queries = {
        "companies": select(Company.assigned_recruiter_user_id, func.count()).where(Company.assigned_recruiter_user_id.in_(user_ids)),
        "requirements": select(Job.assigned_recruiter_user_id, func.count()).where(Job.assigned_recruiter_user_id.in_(user_ids)),
        "follow_ups": _open_follow_ups(Company.assigned_recruiter_user_id.in_(user_ids)),
    }
    for key, stmt in queries.items():
        for uid, n in (await db.execute(stmt.group_by(stmt.selected_columns[0]))).all():
            counts[uid][key] = n
    return counts


async def refuse_open_work_deactivation(db: AsyncSession, user: User) -> None:
    """RC2/RC3/RC11: the user row is locked before counting, so a concurrent assign is either counted or then sees an inactive recruiter.
    422, not 409 -- the Users page reads a 409 as the trainer "confirm cascade" prompt. Otherwise the session ends (RC12)."""
    if user.role != ROLE:
        return
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    companies = await db.scalar(select(func.count()).select_from(Company).where(Company.assigned_recruiter_user_id == user.id, Company.archived_at.is_(None))) or 0
    requirements = await db.scalar(select(func.count()).select_from(Job).where(Job.assigned_recruiter_user_id == user.id, Job.status.notin_(recruiter_requirements.ENDED))) or 0
    parts = [_plural(companies, "company", "companies")] * bool(companies) + [_plural(requirements, "open requirement")] * bool(requirements)
    if parts:
        raise HTTPException(422, f"This recruiter has {' and '.join(parts)}. A placement manager must reassign them (Team page) before deactivation.")
    user.session_version += 1


async def load_source(db: AsyncSession, actor: User, user_id: UUID) -> User:
    """RC8: 404 unless a recruiter with a profile; 403 unless the manager's direct report (super_admin: anyone, RC9)."""
    source = await db.get(User, user_id)
    profile = await db.scalar(select(RecruiterProfile).where(RecruiterProfile.user_id == user_id)) if source is not None and source.role == ROLE else None
    if source is None or profile is None:
        raise HTTPException(404, NOT_FOUND)
    if actor.role != "super_admin" and profile.reporting_manager_user_id != actor.id:
        log("recruiter_reassign_refused", actor, from_user_id=str(user_id))
        raise HTTPException(403, NOT_IN_TEAM)
    return source


async def reassign(db: AsyncSession, actor: User, source: User, target_id: UUID) -> dict[str, int]:
    """RC5-RC7: every company and requirement of the source moves to the target, with history and audit; open follow-ups ride along."""

    def locked(model, column):
        return select(model).where(column == source.id).order_by(model.id).with_for_update().execution_options(populate_existing=True)

    companies = (await db.scalars(locked(Company, Company.assigned_recruiter_user_id))).all()
    jobs = (await db.scalars(locked(Job, Job.assigned_recruiter_user_id))).all()
    if target_id == source.id:
        raise HTTPException(422, recruiter_companies.REASSIGN_INVALID)
    target = await recruiter_companies.locked_recruiter_target(db, actor, target_id)
    if not companies and not jobs:
        raise HTTPException(409, NOTHING)
    follow_ups = (await work_counts(db, [source.id]))[source.id]["follow_ups"]  # counted before the move
    moved = {"companies": len(companies), "requirements": len(jobs), "follow_ups": follow_ups}
    change = {"from_user_id": str(source.id), "to_user_id": str(target.id), "reason": "reassign"}
    for company in companies:
        recruiter_companies.record_assignment(db, actor, company, target.id)
        recruiter_companies.audit(db, actor, "assign", company.id, change)
    for job in jobs:
        job.assigned_recruiter_user_id = target.id
        recruiter_requirements.audit(db, actor, "assign", job.id, change)
    return moved


def log(event: str, actor: User, **fields) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(actor.id), **fields}})
