"""itc-009 (DEC-SCOPE-342; backlog §itc-009, source §9): escalate a follow-up that is overdue by the team's `escalate_after_hours`.

- A telecaller's follow-up (`TELECALLER_FOLLOW_UP`) goes to that telecaller's reporting manager; an inactive manager falls back to the
  team's division admins (`it_admin` / `overseas_admin`). An IT counselor's follow-up goes to every active IT admin. Overseas counselor
  follow-ups are ccrm-031's and are not touched here.
- Once per follow-up (AC1): `escalated_at` is claimed with a conditional UPDATE in the same savepoint as the notices, so two overlapping
  runs never both claim and a failed notice un-claims. Only open follow-ups qualify (AC2), never on a Nurture lead (itc-004 N5, through
  `follow_up_overdue`); 0 hours turns the team off (AC3). With no recipient the follow-up stays unclaimed for a later run.
- Only follow-ups that crossed the threshold within the last day are escalated (`GUARD`, like tel-020's AL10), so switching it on never
  floods anyone about months-old work.

Notices use itc-002's fixed, preview-safe `it.followup.overdue` text: no name, phone or note. Logs carry counts and ids only.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Enquiry, LeadFollowUp, TelecallerProfile, TelSetting, User
from app.notifications.events import notify
from app.services.lead_pipeline import TELECALLER_FOLLOW_UP, follow_up_overdue

logger = logging.getLogger(__name__)

EVENT = "it.followup.overdue"
GUARD = timedelta(hours=24)
DIVISION_ADMIN = {"it": "it_admin", "overseas": "overseas_admin"}
_Manager = aliased(User)


async def _admins(db: AsyncSession, team: str) -> list[User]:
    return list(await db.scalars(select(User).where(User.role == DIVISION_ADMIN[team], User.division == team, User.active.is_(True))))


def _due(team: str, hours: int, now: datetime):
    """Open, unescalated follow-ups on the team's leads that crossed the threshold within the guard window."""
    cutoff = now - timedelta(hours=hours)
    return (
        select(LeadFollowUp)
        .join(Enquiry, Enquiry.id == LeadFollowUp.lead_id)
        .where(follow_up_overdue(cutoff), LeadFollowUp.due_at > cutoff - GUARD, LeadFollowUp.escalated_at.is_(None), Enquiry.division == team)
    )


async def _escalate(db: AsyncSession, counts: dict, fu: LeadFollowUp, recipients: list[User], action_url: str | None, now: datetime) -> None:
    if not recipients:
        counts["skipped"] += 1
        return
    try:
        async with db.begin_nested():
            claimed = await db.scalar(update(LeadFollowUp).where(LeadFollowUp.id == fu.id, LeadFollowUp.escalated_at.is_(None)).values(escalated_at=now).returning(LeadFollowUp.id))
            if claimed is not None:
                await notify(db, recipients, EVENT, fu.id, action_url=action_url)
        await db.commit()
        counts["escalated" if claimed is not None else "duplicate"] += 1
    except Exception:
        await db.rollback()
        counts["failed"] += 1
        logger.exception("itc009_escalation_failed", extra={"extra_fields": {"follow_up_id": str(fu.id)}})


async def escalate_overdue_follow_ups(db: AsyncSession, *, now: datetime) -> dict[str, int]:
    counts = {"escalated": 0, "duplicate": 0, "skipped": 0, "failed": 0}
    for team, hours in (await db.execute(select(TelSetting.team, TelSetting.escalate_after_hours))).all():
        if not hours:  # 0 = off (AC3)
            continue
        admins = await _admins(db, team)
        telecaller = (
            _due(team, hours, now)
            .add_columns(_Manager)
            .join(TelecallerProfile, TelecallerProfile.user_id == Enquiry.telecaller_user_id)
            .join(_Manager, _Manager.id == TelecallerProfile.reporting_manager_user_id)
            .where(TELECALLER_FOLLOW_UP)
        )
        for fu, manager in (await db.execute(telecaller)).all():
            if manager.active:
                await _escalate(db, counts, fu, [manager], f"/telecaller/manager/leads/{fu.lead_id}", now)
            else:
                await _escalate(db, counts, fu, admins, None, now)
        if team == "it":  # an overseas counselor's follow-ups are ccrm-031's
            for fu in (await db.scalars(_due(team, hours, now).where(~TELECALLER_FOLLOW_UP))).all():
                await _escalate(db, counts, fu, admins, None, now)
    logger.info("itc009_escalations_done", extra={"extra_fields": {"at": now.isoformat(), **counts}})
    return counts


async def run_follow_up_escalations() -> dict[str, int]:
    """The beat task's entry point: its own session, the current time."""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await escalate_overdue_follow_ups(db, now=datetime.now(UTC))
