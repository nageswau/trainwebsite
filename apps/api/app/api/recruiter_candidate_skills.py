"""rec-011 (DEC-SCOPE-137, spec §4): a candidate's skills. Readers and writers are rec-009's (hr_team reads); the role check runs before
anything is read, and a candidate outside the pool is a 404.

Bodies are untyped dicts parsed by services/telecaller._parse, so a 422 is one sentence naming the field (the tel-002 idiom). Each write
is one transaction: role, candidate row lock (archived → 409), rules, change, audit row, one commit here, then the log line."""

from uuid import UUID

from fastapi import APIRouter, Body, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.telecaller_catalogue import NOT_AN_OBJECT
from app.core.database import get_db
from app.models import CandidateSkill, User
from app.schemas import CANDIDATE_SKILL_LABELS, CandidateSkillCreate, CandidateSkillStatusChange, CandidateSkillUpdate
from app.services import candidate_skills as svc
from app.services import candidates
from app.services.telecaller import _parse

router = APIRouter(prefix="/recruiter/candidates/{candidate_id}/skills", tags=["recruiter-candidate-skills"])


def _body(model, payload):
    return _parse(model, payload, NOT_AN_OBJECT, CANDIDATE_SKILL_LABELS)


@router.get("")
async def list_skills(candidate_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    candidates.require_reader(user)
    candidate = await candidates.load(db, candidate_id)
    return {"items": await svc.items_out(db, candidate.id), "can_edit": user.role in candidates.WRITERS and candidate.archived_at is None}


@router.post("", status_code=201)
async def add_skill(candidate_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC1: one row per skill, always `claimed`. AC2: the same skill again (by name, case or alias) → 409. AC4: not in the master → 422."""
    candidates.require_writer(user)
    data = _body(CandidateSkillCreate, payload).model_dump()
    candidate = await svc.writable(db, candidate_id)
    skill = await svc.skill_for_add(db, data.pop("skill"))
    await svc.check_free(db, candidate, skill)
    row = CandidateSkill(candidate_id=candidate.id, skill_id=skill.id, added_by_user_id=user.id, **data)
    db.add(row)
    await svc.flush_new(db, skill)
    svc.audit(db, user, "add", candidate, row)
    await db.commit()
    svc.log("candidate_skill_added", user, candidate, row)
    return await svc.item_out(db, candidate.id, row.id)


@router.patch("/{item_id}")
async def update_skill(candidate_id: UUID, item_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Level, experience, last used and source. A PATCH that changes nothing writes no audit row."""
    candidates.require_writer(user)
    changes = _body(CandidateSkillUpdate, payload).model_dump(exclude_unset=True)
    candidate = await svc.writable(db, candidate_id)
    row = await svc.load_item(db, candidate, item_id)
    fields = svc.apply_fields(row, changes)
    if fields:
        row.updated_by_user_id = user.id
        svc.audit(db, user, "update", candidate, row, fields=fields)
    await db.commit()
    if fields:
        svc.log("candidate_skill_updated", user, candidate, row, fields=fields)
    return await svc.item_out(db, candidate.id, row.id)


@router.delete("/{item_id}", status_code=204)
async def remove_skill(candidate_id: UUID, item_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    candidates.require_writer(user)
    candidate = await svc.writable(db, candidate_id)
    row = await svc.load_item(db, candidate, item_id)
    svc.audit(db, user, "remove", candidate, row, status=row.status)
    await db.delete(row)
    await db.commit()
    svc.log("candidate_skill_removed", user, candidate, row)
    return Response(status_code=204)


@router.post("/{item_id}/status")
async def change_status(candidate_id: UUID, item_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC3 / SK4: any writer may verify or assess; who and when are recorded, and `claimed` clears them. The same status → 409."""
    candidates.require_writer(user)
    status = _body(CandidateSkillStatusChange, payload).status
    candidate = await svc.writable(db, candidate_id)
    row = await svc.load_item(db, candidate, item_id)
    old = svc.set_status(row, user, status)
    svc.audit(db, user, "status", candidate, row, **{"from": old, "to": status})
    await db.commit()
    svc.log("candidate_skill_status_changed", user, candidate, row, status=status)
    return await svc.item_out(db, candidate.id, row.id)
