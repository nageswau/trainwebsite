"""hrc-012 (DEC-SCOPE-382, spec docs/superpowers/specs/2026-11-04-hrc-012-candidate-ownership-design.md): who owns a candidate -- one
primary recruiter (O2), a placement-officer owner (O3), collaborators while shared ownership is on (O4) -- who may change that (O5), the
history (O6) and the rec-037 handover (O8). Visibility stays pool-wide (O1): nothing here narrows what a reader sees.

Functions only; nothing here commits -- the route owns the transaction. Lock order: the candidate row (FOR UPDATE, by the caller), then
each named user (FOR SHARE), the rec-003 row-then-user order, so a concurrent deactivation waits or is seen. Logs and audit carry ids;
the audit's `changes` name people (the hrc-004 history shows them)."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    Candidate,
    CandidateAssignmentHistory,
    CandidateCollaborator,
    CandidateOwnershipSetting,
    RecruiterProfile,
    User,
)
from app.notifications.events import notify
from app.services.recruiter import MANAGER_ROLE, ROLE

logger = logging.getLogger("app.candidates")

OFFICER = "placement_officer"
ASSIGNERS = frozenset({MANAGER_ROLE, "super_admin"})  # O5: any candidate; a recruiter only their own
SETTING_EDITORS = ASSIGNERS
KINDS = {"recruiter": (ROLE,), "officer": (OFFICER,), "collaborator": (ROLE, OFFICER)}
INVALID = {"recruiter": "Choose an active recruiter", "officer": "Choose an active placement officer", "collaborator": "Choose active recruiters or placement officers"}
CANNOT_ASSIGN = "Only the primary recruiter or a placement manager can change who owns this candidate"
NEEDS_OWNER = "A candidate keeps one primary recruiter"
SHARING_OFF = "Shared ownership is switched off"
OWNER_IS_COLLABORATOR = "The primary recruiter is already an owner"
LOOKUP_LIMIT = 20


def may_assign(user: User, candidate: Candidate) -> bool:
    return user.role in ASSIGNERS or (user.role == ROLE and candidate.owner_user_id == user.id)


async def shared_ownership(db: AsyncSession) -> bool:
    return bool(await db.scalar(select(CandidateOwnershipSetting.shared_ownership).where(CandidateOwnershipSetting.id == 1)))


async def save_setting(db: AsyncSession, user: User, shared: bool) -> None:
    row = await db.get(CandidateOwnershipSetting, 1, with_for_update=True)
    if row is None:
        row = CandidateOwnershipSetting(id=1)
        db.add(row)
    row.shared_ownership, row.updated_by_user_id = shared, user.id
    db.add(AuditLog(user_id=user.id, action="candidate.ownership_settings", entity_type="candidate_ownership_settings", entity_id="1",
                    metadata_json={"shared_ownership": shared}))  # fmt: skip


def mine(user_id: UUID):
    """O1: "My candidates" -- primary recruiter, placement officer or collaborator."""
    collaborates = exists().where(CandidateCollaborator.candidate_id == Candidate.id, CandidateCollaborator.user_id == user_id)
    return or_(Candidate.owner_user_id == user_id, Candidate.placement_officer_user_id == user_id, collaborates)


def _eligible(kind: str):
    return [User.active.is_(True), User.role.in_(KINDS[kind]), or_(User.role != ROLE, exists().where(RecruiterProfile.user_id == User.id))]


async def _locked_people(db: AsyncSession, ids: set[UUID], kind: str) -> dict[UUID, User]:
    """FOR SHARE on every named user; any id that is not an active eligible person is one 422 (no probing which)."""
    if not ids:
        return {}
    found = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids), *_eligible(kind)).order_by(User.id).with_for_update(read=True))).all()}
    if set(found) != ids:
        raise HTTPException(422, INVALID[kind])
    return found


async def lookup(db: AsyncSession, kind: str, pattern: str | None) -> list[dict]:
    stmt = select(User.id, User.full_name, User.role).where(*_eligible(kind))
    if pattern:
        stmt = stmt.where(User.full_name.ilike(pattern, escape="\\"))
    rows = (await db.execute(stmt.order_by(User.full_name, User.id).limit(LOOKUP_LIMIT))).all()
    return [{"id": i, "full_name": n, "role": r} for i, n, r in rows]


def record(db: AsyncSession, actor: User, candidate_id: UUID, kind: str, from_id: UUID | None, to_id: UUID | None, reason: str) -> None:
    db.add(CandidateAssignmentHistory(candidate_id=candidate_id, kind=kind, from_user_id=from_id, to_user_id=to_id, changed_by_user_id=actor.id, reason=reason))


def on_create(db: AsyncSession, actor: User, candidate: Candidate) -> None:
    """O7: a recruiter who adds a candidate is its primary recruiter (the row must be flushed: the history references it)."""
    if actor.role == ROLE:
        candidate.owner_user_id = actor.id
        record(db, actor, candidate.id, "owner", None, actor.id, "create")


async def change(db: AsyncSession, actor: User, candidate: Candidate, sent: dict) -> list[str]:
    """Apply the sent keys to a locked candidate; returns the audit labels that changed ([] = nothing to do). The route checks rights."""
    current = list((await db.scalars(select(CandidateCollaborator).where(CandidateCollaborator.candidate_id == candidate.id))).all())
    owner_id = sent["owner_user_id"] if "owner_user_id" in sent else candidate.owner_user_id
    if owner_id is None and candidate.owner_user_id is not None:
        raise HTTPException(422, NEEDS_OWNER)
    officer_id = sent["placement_officer_user_id"] if "placement_officer_user_id" in sent else candidate.placement_officer_user_id
    wanted = list(dict.fromkeys(sent["collaborator_user_ids"])) if "collaborator_user_ids" in sent else [c.user_id for c in current]
    if owner_id in wanted:
        if "collaborator_user_ids" in sent and "owner_user_id" not in sent:
            raise HTTPException(422, OWNER_IS_COLLABORATOR)
        wanted.remove(owner_id)  # O4: a collaborator who becomes the primary recruiter is no longer a collaborator

    people: dict[UUID, User] = {}
    if owner_id != candidate.owner_user_id:
        people |= await _locked_people(db, {owner_id}, "recruiter")
    if officer_id is not None and officer_id != candidate.placement_officer_user_id:
        people |= await _locked_people(db, {officer_id}, "officer")
    held = {c.user_id for c in current}
    added = [uid for uid in wanted if uid not in held]
    removed = [c for c in current if c.user_id not in wanted]
    if added:
        if not await shared_ownership(db):
            raise HTTPException(422, SHARING_OFF)
        people |= await _locked_people(db, set(added), "collaborator")

    involved = {candidate.owner_user_id, candidate.placement_officer_user_id, *held, *people} - {None}  # the audit names old and new people
    name = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(involved)))).all()).get
    changes: dict[str, list] = {}
    if owner_id != candidate.owner_user_id:
        record(db, actor, candidate.id, "owner", candidate.owner_user_id, owner_id, "assign")
        changes["primary recruiter"] = [name(candidate.owner_user_id), name(owner_id)]
        candidate.owner_user_id = owner_id
    if officer_id != candidate.placement_officer_user_id:
        record(db, actor, candidate.id, "placement_officer", candidate.placement_officer_user_id, officer_id, "assign")
        changes["placement officer"] = [name(candidate.placement_officer_user_id), name(officer_id)]
        candidate.placement_officer_user_id = officer_id
    for row in removed:
        record(db, actor, candidate.id, "collaborator_removed", row.user_id, None, "assign")
        await db.delete(row)
    for uid in added:
        db.add(CandidateCollaborator(candidate_id=candidate.id, user_id=uid, added_by_user_id=actor.id))
        record(db, actor, candidate.id, "collaborator_added", None, uid, "assign")
    if added or removed:
        changes["collaborators"] = [", ".join(sorted(name(u) or "" for u in held)) or None, ", ".join(sorted(name(u) or "" for u in wanted)) or None]
    if not changes:
        return []
    db.add(AuditLog(user_id=actor.id, action="candidate.assign", entity_type="candidates", entity_id=str(candidate.id), metadata_json={"changes": changes}))
    await db.flush()
    newly = [people.get(uid) for uid in {owner_id if "primary recruiter" in changes else None, officer_id if "placement officer" in changes else None, *added} - {None, actor.id}]
    for person in newly:  # O10: an officer has no recruiter screens -- their notice links nowhere
        url = None if person.role == OFFICER else f"/recruiter/candidates/{candidate.id}"
        await notify(db, [person], "it.candidate.assigned", candidate.id, action_url=url)
    logger.info("candidate_ownership_changed", extra={"extra_fields": {"actor_id": str(actor.id), "candidate_id": str(candidate.id), "fields": sorted(changes)}})
    return sorted(changes)


def _person(user: User | None) -> dict | None:
    return {"id": user.id, "full_name": user.full_name, "active": user.active} if user else None


async def owners(db: AsyncSession, candidates: list[Candidate]) -> dict[UUID, User]:
    ids = {c.owner_user_id for c in candidates} - {None}
    return {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids)))).all()} if ids else {}


def owner_out(people: dict[UUID, User], candidate: Candidate) -> dict | None:
    return _person(people.get(candidate.owner_user_id))


async def ownership_out(db: AsyncSession, user: User, candidate: Candidate) -> dict:
    collaborators = (await db.scalars(select(User).join(CandidateCollaborator, CandidateCollaborator.user_id == User.id)
                                      .where(CandidateCollaborator.candidate_id == candidate.id).order_by(User.full_name, User.id))).all()  # fmt: skip
    return {
        "owner": _person(await db.get(User, candidate.owner_user_id) if candidate.owner_user_id else None),
        "placement_officer": _person(await db.get(User, candidate.placement_officer_user_id) if candidate.placement_officer_user_id else None),
        "collaborators": [_person(u) for u in collaborators],
        "shared_ownership": await shared_ownership(db),
        "can_assign": may_assign(user, candidate) and candidate.archived_at is None,
    }


# --- O8: rec-037 handover ------------------------------------------------------------------------------------------------------
async def owned_counts(db: AsyncSession, user_ids: list[UUID]) -> dict[UUID, int]:
    rows = (await db.execute(select(Candidate.owner_user_id, func.count()).where(Candidate.owner_user_id.in_(user_ids)).group_by(Candidate.owner_user_id))).all()
    return dict(rows)


async def open_owned_count(db: AsyncSession, user_id: UUID) -> int:
    return await db.scalar(select(func.count()).select_from(Candidate).where(Candidate.owner_user_id == user_id, Candidate.archived_at.is_(None))) or 0


async def move_owned(db: AsyncSession, actor: User, source: User, target: User, rows) -> None:
    """The source's candidates (archived too; locked by the caller before the target, RC10) move to the target with history and audit."""
    for candidate in rows:
        record(db, actor, candidate.id, "owner", source.id, target.id, "reassign")
        candidate.owner_user_id = target.id
        # a target who collaborated on it is now its primary recruiter (O4)
        await db.execute(CandidateCollaborator.__table__.delete().where(CandidateCollaborator.candidate_id == candidate.id, CandidateCollaborator.user_id == target.id))
        db.add(AuditLog(user_id=actor.id, action="candidate.assign", entity_type="candidates", entity_id=str(candidate.id),
                        metadata_json={"reason": "reassign", "changes": {"primary recruiter": [source.full_name, target.full_name]}}))  # fmt: skip
