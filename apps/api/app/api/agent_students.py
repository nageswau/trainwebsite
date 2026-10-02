"""AGN-004 -- an agency's students, including students who never log in (DEC-SCOPE-042; spec §5.4).

Masters see the whole agency; staff only students assigned to them (G4); anything outside the caller's scope is 404. Every write
locks the organisation row, writes an audit row in the same transaction and commits once, so the duplicate check and assignment
hold under concurrency.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rbac import agent_denial_reason, is_agent_staff
from app.models import AgentOrgMember, AuditLog, User
from app.schemas import AgentStudentAssign, AgentStudentCounselingSave, AgentStudentRecordCreate, AgentStudentRecordUpdate
from app.services.agent_orgs import lock_active_org
from app.services.agent_students import (
    active_staff_member,
    apply_update,
    create_record,
    duplicate_conflict,
    find_duplicates,
    list_page,
    load_scoped,
    record_detail,
    save_counseling,
    set_archived,
)

logger = logging.getLogger("app.agent_students")

router = APIRouter(prefix="/workflows/overseas/agent/crm/students", tags=["agent-students"])


def _gate(user: User) -> AgentOrgMember:
    """Agents of an active organisation only (Masters and staff). super_admin is not admitted: these routes are agency-internal."""
    if user.role != "agent" or user.division != "overseas":
        raise HTTPException(403, "This role cannot perform this operation")
    reason = agent_denial_reason(user)
    if reason:
        raise HTTPException(403, reason)
    return user.agent_membership


def _audit(db: AsyncSession, user: User, action: str, student_id, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed, SEC-001); ids, field names and counts only."""
    db.add(AuditLog(user_id=user.id, action=f"agent_student.{action}", entity_type="agent_student", entity_id=str(student_id), metadata_json=metadata or {}))


def _log(event: str, membership: AgentOrgMember, user: User, student_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"org_id": str(membership.org_id), "actor_id": str(user.id), "student_id": str(student_id), **extra}})


def _assigned_filter(user: User, assigned: str | None):
    if assigned is None:
        return None
    if is_agent_staff(user):
        raise HTTPException(422, "assigned is a Master-only filter")
    if assigned == "me":
        return user.agent_membership.id
    if assigned == "none":
        return "none"
    try:
        return UUID(assigned)
    except ValueError:
        raise HTTPException(422, "assigned must be me, none or a member id") from None


@router.get("")
async def list_students(
    q: str | None = Query(None, max_length=100),
    include_archived: bool = False,
    assigned: str | None = Query(None, max_length=36),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _gate(user)
    return await list_page(db, user, q=q, include_archived=include_archived, assigned=_assigned_filter(user, assigned), limit=limit, offset=offset)


@router.post("", status_code=201)
async def create_student(payload: AgentStudentRecordCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    await lock_active_org(db, membership.org_id)  # serialises creates: two cannot both pass the duplicate check
    data = payload.model_dump(exclude={"confirm_duplicate"})
    matches, hidden = await find_duplicates(db, user, email=data.get("email"), phone=data.get("phone"))
    found = len(matches) + hidden
    if found and not payload.confirm_duplicate:
        _log("agent_student_duplicate_warned", membership, user, "-", match_count=found)
        raise duplicate_conflict(matches, hidden)
    row = create_record(db, user, data)
    await db.flush()
    _audit(db, user, "create", row.id, {"fields": sorted(k for k, v in data.items() if v is not None), "assigned_member_id": str(row.assigned_member_id) if row.assigned_member_id else None})
    if found:
        _audit(db, user, "duplicate_override", row.id, {"match_count": found})
    await db.commit()
    _log("agent_student_created", membership, user, row.id)
    if found:
        _log("agent_student_duplicate_overridden", membership, user, row.id, match_count=found)
    return {"student": await record_detail(db, row)}


@router.get("/{student_id}")
async def get_student(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _gate(user)
    return {"student": await record_detail(db, await load_scoped(db, user, student_id))}


def _require_master_action(user: User, message: str) -> None:
    if is_agent_staff(user):
        raise HTTPException(403, message)


async def _locked_row(db: AsyncSession, user: User, membership: AgentOrgMember, student_id: UUID):
    """Organisation lock first (the lock order every agency write uses), then the scoped row -- another staff member's student
    stays 404 before any role check can reveal it exists."""
    await lock_active_org(db, membership.org_id)
    return await load_scoped(db, user, student_id, lock=True)


@router.patch("/{student_id}")
async def update_student(student_id: UUID, payload: AgentStudentRecordUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    row = await _locked_row(db, user, membership, student_id)
    if row.student_id is not None:
        raise HTTPException(409, "Linked students are edited in their own account")
    if row.status == "archived":
        raise HTTPException(409, "Unarchive this student first")
    changes = payload.model_dump(exclude_unset=True, exclude={"confirm_duplicate"})
    found, matches, hidden = 0, [], 0
    if {"email", "phone"} & changes.keys():
        email = changes["email"] if "email" in changes else row.email
        phone = changes["phone"] if "phone" in changes else row.phone
        matches, hidden = await find_duplicates(db, user, email=email, phone=phone, exclude_id=row.id)
        found = len(matches) + hidden
        if found and not payload.confirm_duplicate:
            _log("agent_student_duplicate_warned", membership, user, row.id, match_count=found)
            raise duplicate_conflict(matches, hidden)
    changed = apply_update(row, user, changes)
    if changed:
        _audit(db, user, "update", row.id, {"fields": changed})
        if found:
            _audit(db, user, "duplicate_override", row.id, {"match_count": found})
    await db.commit()
    if changed:
        _log("agent_student_updated", membership, user, row.id, fields=changed)
    return {"student": await record_detail(db, row)}


async def _archive(student_id: UUID, user: User, db: AsyncSession, archived: bool) -> dict:
    membership = _gate(user)
    row = await _locked_row(db, user, membership, student_id)
    _require_master_action(user, "Only an agency Master can archive students")
    if (row.status == "archived") == archived:
        raise HTTPException(409, "Already archived" if archived else "Already active")
    set_archived(row, user, archived)
    _audit(db, user, "archive" if archived else "unarchive", row.id)
    await db.commit()
    _log("agent_student_archived" if archived else "agent_student_unarchived", membership, user, row.id)
    return {"student": await record_detail(db, row)}


@router.post("/{student_id}/archive")
async def archive_student(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _archive(student_id, user, db, True)


@router.post("/{student_id}/unarchive")
async def unarchive_student(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _archive(student_id, user, db, False)


@router.post("/{student_id}/assign")
async def assign_student(student_id: UUID, payload: AgentStudentAssign, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    row = await _locked_row(db, user, membership, student_id)
    _require_master_action(user, "Only an agency Master can assign students")
    if row.status == "archived":
        raise HTTPException(409, "Unarchive this student first")
    target = await active_staff_member(db, user, payload.member_id) if payload.member_id else None
    new_id = target.id if target else None
    changed = row.assigned_member_id != new_id  # re-assigning the current assignee is a no-op: 200, nothing audited
    if changed:
        previous = row.assigned_member_id
        row.assigned_member_id, row.updated_by_user_id = new_id, user.id
        _audit(db, user, "assign", row.id, {"from": str(previous) if previous else None, "to": str(new_id) if new_id else None})
    await db.commit()
    if changed:
        _log("agent_student_assigned", membership, user, row.id, member_id=str(new_id) if new_id else None)
    return {"student": await record_detail(db, row)}


@router.put("/{student_id}/counseling")
async def save_student_counseling(student_id: UUID, payload: AgentStudentCounselingSave, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-006 (DEC-SCOPE-048): replace the student's counseling record. Same locks and scope as an edit: out of scope is 404 before
    any other check; a student with a login or an archived student is 409. A save that changes nothing is 200 with no audit row."""
    membership = _gate(user)
    row = await _locked_row(db, user, membership, student_id)
    if row.student_id is not None:
        raise HTTPException(409, "Counseling is recorded only for students without a login")
    if row.status == "archived":
        raise HTTPException(409, "Unarchive this student first")
    changed = await save_counseling(db, row, user, payload.model_dump())
    if changed:
        _audit(db, user, "counseling", row.id, {"fields": changed})
    await db.commit()
    if changed:
        _log("agent_student_counseling_saved", membership, user, row.id, fields=changed)
    return {"student": await record_detail(db, row)}
