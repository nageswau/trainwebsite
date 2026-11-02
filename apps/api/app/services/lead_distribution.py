"""tel-007 (DEC-SCOPE-087, spec §2/§4): who a lead goes to -- the team's product rule, then its city rule, then round robin among the
team's active telecallers; otherwise the unassigned queue (T11, T18). Manual (re)assignment shares `assign` and `assignee`.
itc-006 (DEC-SCOPE-337): a source rule is tried first, and the team's strategy may replace round robin with the fewest open leads.

Functions only; nothing here commits -- the route owns the transaction. Logs and audit rows carry ids and the method, never a lead's
name, phone or city."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import CLOSED
from app.models import AuditLog, Enquiry, TelDistributionRule, TelecallerProfile, TelProduct, TelRoundRobinCursor, TelSetting, User
from app.services import lead_pipeline, telecaller_alerts
from app.services.telecaller import TEAM_LABEL, TEAMS

logger = logging.getLogger("app.leads")

NOT_REPORT = "You can only assign leads to your direct reports"
NOT_TELECALLER = "Choose an active telecaller"
FINISHED = ("converted", *sorted(CLOSED))  # a closed or converted lead is no longer a telecaller's open work (tel-025 LC2, itc-006 D4)


def _eligible_ids(team: str):
    """DI1: role telecaller, active account, on the team."""
    return (select(User.id).join(TelecallerProfile, TelecallerProfile.user_id == User.id)
            .where(User.role == "telecaller", User.active.is_(True), TelecallerProfile.team == team))


def next_in_turn(candidates: list[UUID], last: UUID | None) -> UUID | None:
    """D2: the first candidate (in id order) after the cursor, wrapping; a cursor that left the pool still marks the place."""
    if not candidates:
        return None
    return next((c for c in candidates if last is not None and c > last), candidates[0])


async def _rule_match(db: AsyncSession, team: str, condition) -> tuple[UUID, UUID] | None:
    """The (telecaller, rule) of the team's matching rule whose telecaller is still eligible."""
    stmt = select(TelDistributionRule.telecaller_user_id, TelDistributionRule.id).where(
        TelDistributionRule.team == team, condition, TelDistributionRule.telecaller_user_id.in_(_eligible_ids(team)))
    return (await db.execute(stmt)).first()


async def _in_turn(db: AsyncSession, team: str, candidates) -> UUID | None:
    """D2: the next of `candidates` (a select of user ids) after the team's cursor. The cursor row is locked FOR UPDATE first, so
    concurrent intakes serialise -- and a workload count read after the lock sees the previous intake's committed assignment."""
    await db.execute(insert(TelRoundRobinCursor).values(team=team).on_conflict_do_nothing(index_elements=["team"]))
    cursor = await db.scalar(select(TelRoundRobinCursor).where(TelRoundRobinCursor.team == team).with_for_update().execution_options(populate_existing=True))
    chosen = next_in_turn(list(await db.scalars(candidates)), cursor.last_user_id)
    if chosen is not None:
        cursor.last_user_id = chosen
    return chosen


def _least_loaded(team: str):
    """itc-006 D4: the eligible telecallers with the fewest open leads, in id order (ties then go in turn)."""
    open_leads = (select(Enquiry.telecaller_user_id.label("user_id"), func.count().label("n"))
                  .where(Enquiry.telecaller_user_id.in_(_eligible_ids(team)), Enquiry.status.not_in(FINISHED))
                  .group_by(Enquiry.telecaller_user_id).subquery())
    load = func.coalesce(open_leads.c.n, 0)
    loads = _eligible_ids(team).add_columns(load.label("load")).outerjoin(open_leads, open_leads.c.user_id == User.id).subquery()
    return select(loads.c.id).where(loads.c.load == select(func.min(loads.c.load)).scalar_subquery()).order_by(loads.c.id)


async def _choose(db: AsyncSession, lead: Enquiry) -> tuple[UUID | None, str | None, UUID | None]:
    """The telecaller, the method and the matched rule (None for the team strategy)."""
    team = lead.division
    if team not in TEAMS:
        return None, None, None
    if lead.product_id is not None and await db.scalar(select(TelProduct.team).where(TelProduct.id == lead.product_id)) is None:
        return None, None, None  # T18: a product without a team waits for a manager
    conditions = [("source_rule", (TelDistributionRule.kind == "source") & (TelDistributionRule.source == lead.source))]
    if lead.product_id is not None:
        conditions.append(("product_rule", (TelDistributionRule.kind == "product") & (TelDistributionRule.product_id == lead.product_id)))
    if lead.city and lead.city.strip():
        conditions.append(("city_rule", (TelDistributionRule.kind == "city") & (func.lower(TelDistributionRule.city) == lead.city.strip().lower())))
    for method, condition in conditions:
        if match := await _rule_match(db, team, condition):
            return match[0], method, match[1]
    strategy = await db.scalar(select(TelSetting.distribution_strategy).where(TelSetting.team == team)) or "round_robin"
    chosen = await _in_turn(db, team, _least_loaded(team) if strategy == "workload" else _eligible_ids(team).order_by(User.id))
    return chosen, strategy if chosen else None, None


async def assign(db: AsyncSession, lead: Enquiry, telecaller_id: UUID, method: str, actor: User | None, *, notify: bool = True,
                 rule_id: UUID | None = None) -> None:
    """D4: the telecaller, the `assigned` stage event (new leads only) and one audit row per change. `notify=False` (tel-025's lifecycle
    moves, DEC-SCOPE-111 AL13) skips tel-020's per-lead alert: the caller tells the new telecaller once. itc-006 AC4: a rule's id is
    recorded with its method."""
    before = lead.telecaller_user_id
    lead.telecaller_user_id = telecaller_id
    await lead_pipeline.apply_event(db, lead, "assigned", actor)
    actor_id = actor.id if actor else None
    metadata = {"from": str(before) if before else None, "to": str(telecaller_id), "method": method} | ({"rule_id": str(rule_id)} if rule_id else {})
    db.add(AuditLog(user_id=actor_id, action="lead.assign", entity_type="enquiry", entity_id=str(lead.id), metadata_json=metadata))
    logger.info("lead_assigned", extra={"extra_fields": {
        "lead_id": str(lead.id), "telecaller_id": str(telecaller_id), "method": method, "actor_id": str(actor_id) if actor_id else None}})
    if notify and before != telecaller_id:
        await telecaller_alerts.notify_assigned(db, lead, actor)  # tel-020: New Lead Assigned, in this transaction


async def distribute(db: AsyncSession, lead: Enquiry) -> str | None:
    """Spec §2 for a new, unassigned lead (already flushed). Returns the method, or None when it stays in the unassigned queue."""
    chosen, method, rule_id = await _choose(db, lead)
    if chosen is None:
        return None
    await assign(db, lead, chosen, method, None, rule_id=rule_id)
    return method


async def on_intake(db: AsyncSession, lead: Enquiry) -> None:
    """The intake call (website, BDM; tel-005/006 later): distribution in a SAVEPOINT, so an unexpected error leaves the enquiry saved
    and unassigned instead of failing the request."""
    lead_id = str(lead.id)  # the savepoint's rollback expires the row
    try:
        async with db.begin_nested():
            await distribute(db, lead)
    except Exception:
        logger.exception("lead_distribution_failed", extra={"extra_fields": {"lead_id": lead_id}})
        await db.refresh(lead)


async def assignee(db: AsyncSession, actor: User, user_id: UUID, team: str) -> User:
    """The target of a rule or a manual assignment: an active telecaller on `team` (422) who reports to the actor (403, AC5; super_admin:
    anyone). The profile is read FOR SHARE, so a concurrent change of manager or team waits for this write."""
    row = (await db.execute(
        select(User, TelecallerProfile).join(TelecallerProfile, TelecallerProfile.user_id == User.id)
        .where(User.id == user_id, User.role == "telecaller").with_for_update(read=True, of=TelecallerProfile)
    )).first()
    if row is None:
        raise HTTPException(422, NOT_TELECALLER)
    user, profile = row
    if actor.role != "super_admin" and profile.reporting_manager_user_id != actor.id:
        raise HTTPException(403, NOT_REPORT)
    if not user.active:
        raise HTTPException(422, "This telecaller is inactive")
    if profile.team != team:
        raise HTTPException(422, f"{user.full_name} is on the {TEAM_LABEL[profile.team]} team")
    return user
