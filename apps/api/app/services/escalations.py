"""pob-027 (DEC-SCOPE-434 I7/I8): the escalation rules and their evaluator.

A rule says "an item of this type still waiting N hours later goes to the Team Lead(s)". The beat runs every rule; each item escalates once
per rule: the `escalation_events` row is inserted with ON CONFLICT DO NOTHING on (rule, item) and the notice is sent only when it was
inserted, in the same transaction -- a rerun or a concurrent run adds nothing. An item that reached its threshold before the rule existed is
left alone (no backlog flood when a rule is added). Bounded: 200 items per rule per run, oldest first. Logs and audit carry ids and counts."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import exists, func, null, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models import AuditLog, Company, EscalationEvent, EscalationRule, Job, RecruiterFollowUp, RecruiterProfile, RequirementTask, User
from app.notifications.events import notify
from app.services.recruiter import MANAGER_ROLE
from app.services.requirement_intake import require_editor, team_leads

logger = logging.getLogger("app.recruiter")

EVENT = "it.recruiter.escalated"
SWEEP_LIMIT = 200
CLOSED_JOB_STATUSES = ("filled", "closed", "cancelled")
FIELDS = ("event_type", "after_hours", "notify", "active")


# --- I7: the rules -------------------------------------------------------------------------------------------------------------------
def rule_out(rule: EscalationRule) -> dict:
    return {"id": rule.id, **{key: getattr(rule, key) for key in FIELDS}, "created_at": rule.created_at}


async def list_rules(db: AsyncSession) -> list[EscalationRule]:
    return list((await db.scalars(select(EscalationRule).order_by(EscalationRule.created_at, EscalationRule.id))).all())


def _audit(db: AsyncSession, user: User, action: str, rule: EscalationRule, changes: dict) -> None:
    db.add(AuditLog(user_id=user.id, action=action, entity_type="escalation_rule", entity_id=str(rule.id), metadata_json={"changes": changes}))


async def create_rule(db: AsyncSession, user: User, values: dict) -> EscalationRule:
    """The Team Lead (403 otherwise); audited with its values."""
    require_editor(user)
    rule = EscalationRule(**values, active=True, created_by_user_id=user.id)
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    _audit(db, user, "escalation_rule.create", rule, {key: [None, getattr(rule, key)] for key in FIELDS})
    return rule


async def update_rule(db: AsyncSession, user: User, rule_id: UUID, values: dict) -> EscalationRule:
    require_editor(user)
    rule = await db.get(EscalationRule, rule_id, with_for_update=True, populate_existing=True)
    if rule is None:
        raise HTTPException(404, "Escalation rule not found")
    changes = {key: [getattr(rule, key), value] for key, value in values.items() if getattr(rule, key) != value}
    for key, value in values.items():
        setattr(rule, key, value)
    rule.updated_by_user_id = user.id
    if changes:
        _audit(db, user, "escalation_rule.update", rule, changes)
    return rule


# --- I8: the evaluator -----------------------------------------------------------------------------------------------------------------
def _due_query(rule: EscalationRule, now: datetime):
    """(item id, owner id or None, link) for the items past the rule's threshold, reached since the rule exists, not yet escalated."""
    window = timedelta(hours=rule.after_hours)

    def bounded(column):
        return [column <= now - window, column >= rule.created_at - window]

    def fresh(id_column):
        return ~exists(select(EscalationEvent.id).where(EscalationEvent.rule_id == rule.id, EscalationEvent.entity_id == id_column))

    if rule.event_type == "requirement_unowned":
        return (select(Job.id, null(), Job.id)
                .where(Job.assigned_recruiter_user_id.is_(None), Job.status.not_in(CLOSED_JOB_STATUSES), *bounded(Job.created_at), fresh(Job.id))
                .order_by(Job.created_at))  # fmt: skip
    if rule.event_type == "requirement_task_overdue":
        task = RequirementTask
        return (select(task.id, task.assignee_user_id, task.job_id)
                .where(task.status == "open", *bounded(task.due_at), fresh(task.id))
                .order_by(task.due_at))  # fmt: skip
    fu = RecruiterFollowUp
    return (select(fu.id, func.coalesce(Company.assigned_recruiter_user_id, fu.created_by_user_id), null())
            .join(Company, Company.id == fu.company_id)
            .where(fu.status == "open", Company.archived_at.is_(None), *bounded(fu.due_at), fresh(fu.id))
            .order_by(fu.due_at))  # fmt: skip


def _link(rule: EscalationRule, job_id: UUID | None) -> str:
    return f"/recruiter/requirements/{job_id}" if job_id else "/recruiter/follow-ups"


async def _recipients(db: AsyncSession, rule: EscalationRule, owner_id: UUID | None, leads: list[User]) -> list[User]:
    """`reporting_manager`: the owner's reporting manager when an active Team Lead, else every active one (pob-022's rule)."""
    if rule.notify == "all_team_leads" or owner_id is None:
        return leads
    lead_id = await db.scalar(select(RecruiterProfile.reporting_manager_user_id).where(RecruiterProfile.user_id == owner_id))
    lead = await db.get(User, lead_id) if lead_id else None
    return [lead] if lead is not None and lead.active and lead.role == MANAGER_ROLE else leads


async def _fire(db: AsyncSession, rule: EscalationRule, now: datetime, leads: list[User]) -> int:
    fired = 0
    for entity_id, owner_id, job_id in (await db.execute(_due_query(rule, now).limit(SWEEP_LIMIT))).all():
        recipients = await _recipients(db, rule, owner_id, leads)
        if not recipients:  # no Team Lead at all: left for a later run
            continue
        inserted = await db.scalar(
            insert(EscalationEvent).values(rule_id=rule.id, entity_id=entity_id, fired_at=now)
            .on_conflict_do_nothing(constraint="uq_escalation_events_rule_entity").returning(EscalationEvent.id)
        )  # fmt: skip
        if inserted is None:  # a concurrent run escalated it first
            continue
        await notify(db, recipients, EVENT, entity_id, action_url=_link(rule, job_id))
        fired += 1
    return fired


async def run_escalations(now: datetime | None = None) -> dict[str, int]:
    """Every active rule, in one transaction: its escalation rows and notices commit together."""
    now = now or datetime.now(UTC)
    async with SessionLocal() as db:
        rules = list((await db.scalars(select(EscalationRule).where(EscalationRule.active).order_by(EscalationRule.created_at))).all())
        leads = await team_leads(db) if rules else []
        fired = 0
        for rule in rules:
            fired += await _fire(db, rule, now, leads)
        await db.commit()
    counts = {"rules": len(rules), "escalated": fired}
    logger.info("escalation_sweep", extra={"extra_fields": counts})
    return counts
