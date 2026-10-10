"""upc-032 (DEC-SCOPE-171, spec §2): partnership manager deactivation and the head's bulk reassignment of universities and open tasks.

Functions only; nothing here commits -- the route (or `admin.update_user`) owns the transaction. Lock order (RA11): the source's
universities (by id), then its open tasks (by id), then the target (FOR SHARE, upc-003 `locked_manager`) -- the assign route's
university-then-manager order, so the two cannot deadlock. Logs and audit carry ids and counts only."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PartnershipProfile, PartnershipTask, University, UniversityAssignmentHistory, User
from app.services import partnership_tasks, partnership_universities

logger = logging.getLogger("app.partnership")

NOT_FOUND = "Partnership manager not found"
NOT_IN_TEAM = "This manager is not in your team"
NOTHING = "This manager has no universities or open tasks to reassign"


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


async def work_counts(db: AsyncSession, user_ids: list[UUID]) -> dict[UUID, dict[str, int]]:
    """RA14: each manager's primary and backup universities and open tasks -- three grouped queries for a whole page."""
    counts = {uid: {"primary": 0, "backup": 0, "tasks": 0} for uid in user_ids}
    queries = {
        "primary": select(University.primary_manager_user_id, func.count()).where(University.primary_manager_user_id.in_(user_ids)).group_by(University.primary_manager_user_id),
        "backup": select(University.backup_manager_user_id, func.count()).where(University.backup_manager_user_id.in_(user_ids)).group_by(University.backup_manager_user_id),
        "tasks": select(PartnershipTask.assignee_user_id, func.count())
        .where(PartnershipTask.assignee_user_id.in_(user_ids), PartnershipTask.status == "open")
        .group_by(PartnershipTask.assignee_user_id),
    }
    for key, stmt in queries.items():
        for uid, n in (await db.execute(stmt)).all():
            counts[uid][key] = n
    return counts


async def refuse_primary_deactivation(db: AsyncSession, user: User) -> None:
    """RA2/RA3/RA12: the user row is locked before counting, so a concurrent assign is either counted or then sees an inactive manager.
    422, not 409 -- the Users page reads a 409 as the trainer "confirm cascade" prompt."""
    if user.role != "partnership_manager":
        return
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    n = await db.scalar(select(func.count()).select_from(University).where(University.primary_manager_user_id == user.id)) or 0
    if n:
        raise HTTPException(422, f"This manager is the primary manager of {_plural(n, 'university', 'universities')}. A partnership head must reassign them (Team page) before deactivation.")


async def load_source(db: AsyncSession, actor: User, user_id: UUID) -> User:
    """RA9: 404 unless a partnership manager with a profile; 403 unless the head's direct report (super_admin: anyone)."""
    source = await db.get(User, user_id)
    profile = await db.get(PartnershipProfile, user_id) if source is not None and source.role == "partnership_manager" else None
    if profile is None:
        raise HTTPException(404, NOT_FOUND)
    if actor.role != "super_admin" and profile.reporting_head_user_id != actor.id:
        log("partnership_reassign_refused", actor, from_user_id=str(user_id))
        raise HTTPException(403, NOT_IN_TEAM)
    return source


async def reassign(db: AsyncSession, actor: User, source: User, target_id: UUID) -> dict[str, int]:
    """RA5-RA10: every slot and open task of the source moves to the target. Where the target already holds the other slot, the target
    keeps (or takes) the primary and the backup is cleared (RA6)."""
    unis = (
        await db.scalars(
            select(University)
            .where(or_(University.primary_manager_user_id == source.id, University.backup_manager_user_id == source.id))
            .order_by(University.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    tasks = (
        await db.scalars(
            select(PartnershipTask)
            .where(PartnershipTask.assignee_user_id == source.id, PartnershipTask.status == "open")
            .order_by(PartnershipTask.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    if target_id == source.id:
        raise HTTPException(422, partnership_universities.MANAGER_INVALID)
    target = await partnership_universities.locked_manager(db, actor, target_id)
    if not unis and not tasks:
        raise HTTPException(409, NOTHING)
    moved = {"primary": 0, "backup": 0, "tasks": len(tasks)}
    for uni in unis:
        current = {"primary": uni.primary_manager_user_id, "backup": uni.backup_manager_user_id}
        moved["primary" if current["primary"] == source.id else "backup"] += 1
        wanted = {slot: target.id if who == source.id else who for slot, who in current.items()}
        if wanted["backup"] == wanted["primary"]:
            wanted["backup"] = None
        changed = [slot for slot in ("primary", "backup") if wanted[slot] != current[slot]]
        uni.primary_manager_user_id, uni.backup_manager_user_id = wanted["primary"], wanted["backup"]
        db.add_all(UniversityAssignmentHistory(university_id=uni.id, slot=slot, from_user_id=current[slot], to_user_id=wanted[slot], actor_user_id=actor.id) for slot in changed)
        partnership_universities.audit(db, actor, "assign", uni.id, {"reason": "reassign", **{slot: [_id(current[slot]), _id(wanted[slot])] for slot in changed}})
    for task in tasks:
        task.assignee_user_id = target.id
        partnership_tasks.audit(db, actor, "reassign", task.id, {"assignee": [str(source.id), str(target.id)]})
    return moved


def _id(value: UUID | None) -> str | None:
    return str(value) if value else None


def log(event: str, actor: User, **fields) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(actor.id), **fields}})
