"""hrc-024 (DEC-SCOPE-393, spec docs/superpowers/specs/2026-11-04-hrc-024-candidate-routing-design.md): who a candidate the website creates
goes to -- the default recruiter (R4), else the first rule kind that matches: source, skill category, location (R1/R5), choosing inside
the rule's group by round robin or least workload (R6); otherwise the unassigned queue and an alert (R9). The assignment is hrc-012's:
primary recruiter, history (reason `route`, no actor), audit and notice (R8). Settings and rules are the placement manager's (R11).

The cursor idiom is tel-007's `lead_distribution`. Functions only; nothing here commits -- the route owns the transaction. Lock order: the
group's cursor (FOR UPDATE), then the chosen recruiter (FOR SHARE). Logs and audit carry ids, the method and the recruiter's name (the
hrc-004 history shows it), never the candidate's name, email or phone."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, union
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CANDIDATE_ROUTING_KINDS,
    AuditLog,
    Candidate,
    CandidateRoutingCursor,
    CandidateRoutingRule,
    CandidateRoutingSetting,
    CandidateSkill,
    RecCandidateSource,
    Skill,
    SkillCategory,
    SkillCategoryTag,
    User,
)
from app.notifications.events import notify
from app.schemas import ROUTING_VALUE
from app.services import candidate_ownership as ownership
from app.services.lead_distribution import next_in_turn
from app.services.recruiter import MANAGER_ROLE

logger = logging.getLogger("app.candidates")

EDITORS = ownership.ASSIGNERS  # R11
NOT_EDITOR = "Only a placement manager can see or change candidate routing"
NOT_RECRUITER = ownership.INVALID["recruiter"]
DUPLICATE = "This recruiter already has this rule"
NOT_FOUND = "Routing rule not found"
UNASSIGNED_EVENT = "it.candidate.unassigned"
QUEUE_URL = "/recruiter/candidates?owner=unassigned"
HR_MANAGER = "hr_manager"
Rule = CandidateRoutingRule


def require_editor(user: User) -> None:
    if user.role not in EDITORS:
        raise HTTPException(403, NOT_EDITOR)


# --- choosing ------------------------------------------------------------------------------------------------------------------------
def _eligible_ids():
    return select(User.id).where(*ownership.eligible("recruiter"))


async def _skill_categories(db: AsyncSession, candidate_id: UUID) -> list[UUID]:
    """R5: the categories of the candidate's skills -- each skill's own and its rec-006 secondary tags."""
    own = select(Skill.category_id).join(CandidateSkill, CandidateSkill.skill_id == Skill.id).where(CandidateSkill.candidate_id == candidate_id)
    tags = select(SkillCategoryTag.category_id).join(CandidateSkill, CandidateSkill.skill_id == SkillCategoryTag.skill_id).where(CandidateSkill.candidate_id == candidate_id)
    return list(await db.scalars(union(own, tags)))


async def _conditions(db: AsyncSession, candidate: Candidate) -> list[tuple[str, object]]:
    """R1: (kind, condition) in routing order; a kind the candidate has no value for is skipped."""
    conditions = [("source", Rule.source_id == candidate.source_id)]
    if categories := await _skill_categories(db, candidate.id):
        conditions.append(("skill_category", Rule.skill_category_id.in_(categories)))
    if place := (candidate.city or candidate.location or "").strip().lower():
        conditions.append(("location", func.lower(Rule.location) == place))
    return conditions


def _value(rule) -> str:
    return str(rule.source_id or rule.skill_category_id or rule.location.lower())


async def _group(db: AsyncSession, condition) -> tuple[str, dict[UUID, UUID]] | None:
    """R2: the matching rules whose recruiter is eligible; the oldest one's value is the group -- its key and {recruiter: rule}."""
    rows = (await db.execute(
        select(Rule.id, Rule.kind, Rule.recruiter_user_id, Rule.source_id, Rule.skill_category_id, Rule.location)
        .where(condition, Rule.recruiter_user_id.in_(_eligible_ids())).order_by(Rule.created_at, Rule.id)
    )).all()  # fmt: skip
    if not rows:
        return None
    value = _value(rows[0])
    return f"{rows[0].kind}:{value}", {r.recruiter_user_id: r.id for r in rows if _value(r) == value}


async def _in_turn(db: AsyncSession, key: str, members: list[UUID], strategy: str) -> UUID:
    """R6/R12: the group's cursor is locked first, so concurrent intakes serialise and a workload count sees the previous assignment."""
    await db.execute(insert(CandidateRoutingCursor).values(group_key=key).on_conflict_do_nothing(index_elements=["group_key"]))
    cursor = await db.scalar(select(CandidateRoutingCursor).where(CandidateRoutingCursor.group_key == key).with_for_update().execution_options(populate_existing=True))
    if strategy == "least_workload":
        open_work = Candidate.owner_user_id.in_(members), Candidate.archived_at.is_(None), Candidate.merged_into_id.is_(None)
        load = dict((await db.execute(select(Candidate.owner_user_id, func.count()).where(*open_work).group_by(Candidate.owner_user_id))).all())
        fewest = min(load.get(m, 0) for m in members)
        members = [m for m in members if load.get(m, 0) == fewest]
    chosen = next_in_turn(sorted(members), cursor.last_user_id)
    cursor.last_user_id = chosen
    return chosen


async def _choose(db: AsyncSession, candidate: Candidate) -> tuple[UUID | None, str | None, UUID | None]:
    """The recruiter, the method and the rule (None for the default recruiter)."""
    setting = await db.get(CandidateRoutingSetting, 1)
    default = setting.default_recruiter_user_id if setting else None
    if default and await db.scalar(_eligible_ids().where(User.id == default)):
        return default, "default_recruiter", None
    for kind, condition in await _conditions(db, candidate):
        if found := await _group(db, (Rule.kind == kind) & condition):
            key, members = found
            chosen = await _in_turn(db, key, list(members), setting.strategy if setting else "round_robin")
            return chosen, f"{kind}_rule", members[chosen]
    return None, None, None


async def route(db: AsyncSession, candidate: Candidate) -> UUID | None:
    """R8: assign the chosen recruiter (read FOR SHARE: a concurrent deactivation waits or is seen). Returns the owner, or None."""
    chosen, method, rule_id = await _choose(db, candidate)
    if chosen is None:
        return None
    recruiter = await db.scalar(select(User).where(User.id == chosen, *ownership.eligible("recruiter")).with_for_update(read=True))
    if recruiter is None:
        return None
    candidate.owner_user_id = recruiter.id
    ownership.record(db, None, candidate.id, "owner", None, recruiter.id, "route")
    metadata = {"reason": "route", "method": method, "changes": {"primary recruiter": [None, recruiter.full_name]}} | ({"rule_id": str(rule_id)} if rule_id else {})
    db.add(AuditLog(user_id=None, action="candidate.assign", entity_type="candidates", entity_id=str(candidate.id), metadata_json=metadata))
    await db.flush()
    await notify(db, [recruiter], "it.candidate.assigned", candidate.id, action_url=f"/recruiter/candidates/{candidate.id}")
    logger.info("candidate_routed", extra={"extra_fields": {"candidate_id": str(candidate.id), "recruiter_id": str(recruiter.id), "method": method}})
    return recruiter.id


async def _alert(db: AsyncSession, candidate_id: UUID) -> None:
    """R9: every active placement manager (linked to the queue) and HR manager (no candidate screens: no link)."""
    people = (await db.scalars(select(User).where(User.role.in_((MANAGER_ROLE, HR_MANAGER)), User.active.is_(True)))).all()
    await notify(db, [u for u in people if u.role == MANAGER_ROLE], UNASSIGNED_EVENT, candidate_id, action_url=QUEUE_URL)
    await notify(db, [u for u in people if u.role == HR_MANAGER], UNASSIGNED_EVENT, candidate_id)
    logger.info("candidate_unassigned", extra={"extra_fields": {"candidate_id": str(candidate_id)}})


async def on_website_candidate(db: AsyncSession, candidate: Candidate) -> UUID | None:
    """R7: routing for a candidate the website just created (flushed), in a SAVEPOINT -- an unexpected error leaves it saved and
    unassigned instead of failing the visitor's request. Unassigned either way -> the alert."""
    candidate_id = candidate.id  # the savepoint's rollback expires the row
    try:
        async with db.begin_nested():
            owner = await route(db, candidate)
    except Exception:
        logger.exception("candidate_routing_failed", extra={"extra_fields": {"candidate_id": str(candidate_id)}})
        await db.refresh(candidate)
        owner = None
    if owner is None:
        await _alert(db, candidate_id)
    return owner


# --- settings and rules (R11) ----------------------------------------------------------------------------------------------------------
def _person(user: User | None) -> dict | None:
    return {"id": user.id, "full_name": user.full_name, "active": user.active} if user else None


async def _recruiter(db: AsyncSession, user_id: UUID) -> User:
    recruiter = await db.scalar(select(User).where(User.id == user_id, *ownership.eligible("recruiter")).with_for_update(read=True))
    if recruiter is None:
        raise HTTPException(422, NOT_RECRUITER)
    return recruiter


async def overview(db: AsyncSession) -> dict:
    setting = await db.get(CandidateRoutingSetting, 1)
    rows = (await db.execute(
        select(Rule, User, RecCandidateSource.name, SkillCategory.name).join(User, User.id == Rule.recruiter_user_id)
        .outerjoin(RecCandidateSource, RecCandidateSource.id == Rule.source_id).outerjoin(SkillCategory, SkillCategory.id == Rule.skill_category_id)
        .order_by(Rule.created_at, Rule.id)
    )).all()  # fmt: skip
    rules = sorted((_rule_out(rule, user, source or category or rule.location) for rule, user, source, category in rows), key=lambda r: CANDIDATE_ROUTING_KINDS.index(r["kind"]))
    default = await db.get(User, setting.default_recruiter_user_id) if setting and setting.default_recruiter_user_id else None
    return {"default_recruiter": _person(default), "strategy": setting.strategy if setting else "round_robin", "rules": rules, "can_edit": True}


def _rule_out(rule: Rule, recruiter: User, label: str) -> dict:
    return {"id": rule.id, "kind": rule.kind, "value_id": rule.source_id or rule.skill_category_id, "value_label": label,
            "recruiter": _person(recruiter), "created_at": rule.created_at}  # fmt: skip


async def save_settings(db: AsyncSession, user: User, default_id: UUID | None, strategy: str) -> None:
    if default_id is not None:
        await _recruiter(db, default_id)
    row = await db.get(CandidateRoutingSetting, 1, with_for_update=True)
    if row is None:
        row = CandidateRoutingSetting(id=1)
        db.add(row)
    row.default_recruiter_user_id, row.strategy, row.updated_by_user_id = default_id, strategy, user.id
    db.add(AuditLog(user_id=user.id, action="candidate.routing_settings", entity_type="candidate_routing_settings", entity_id="1",
                    metadata_json={"default_recruiter_user_id": str(default_id) if default_id else None, "strategy": strategy}))  # fmt: skip


async def add_rule(db: AsyncSession, user: User, body) -> dict:
    label = body.location
    if body.kind == "source":
        label = await db.scalar(select(RecCandidateSource.name).where(RecCandidateSource.id == body.source_id))
    elif body.kind == "skill_category":
        label = await db.scalar(select(SkillCategory.name).where(SkillCategory.id == body.skill_category_id))
    if label is None:
        raise HTTPException(422, ROUTING_VALUE[body.kind][1])
    recruiter = await _recruiter(db, body.recruiter_user_id)
    rule = Rule(**body.model_dump(), created_by_user_id=user.id)
    try:
        async with db.begin_nested():
            db.add(rule)
            await db.flush()
    except IntegrityError:
        raise HTTPException(409, DUPLICATE) from None
    db.add(AuditLog(user_id=user.id, action="candidate.routing_rule_add", entity_type="candidate_routing_rules", entity_id=str(rule.id),
                    metadata_json={"kind": rule.kind, "value": label, "recruiter_user_id": str(recruiter.id)}))  # fmt: skip
    await db.refresh(rule)
    return _rule_out(rule, recruiter, label)


async def delete_rule(db: AsyncSession, user: User, rule_id: UUID) -> None:
    rule = await db.get(Rule, rule_id, with_for_update=True)
    if rule is None:
        raise HTTPException(404, NOT_FOUND)
    db.add(AuditLog(user_id=user.id, action="candidate.routing_rule_delete", entity_type="candidate_routing_rules", entity_id=str(rule.id),
                    metadata_json={"kind": rule.kind, "value": _value(rule), "recruiter_user_id": str(rule.recruiter_user_id)}))  # fmt: skip
    await db.delete(rule)
