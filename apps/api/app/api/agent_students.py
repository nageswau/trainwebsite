"""AGN-004 -- an agency's students, including students who never log in (DEC-SCOPE-041; spec §5.4).

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
from app.schemas import AgentStudentRecordCreate
from app.services.agent_orgs import lock_active_org
from app.services.agent_students import create_record, duplicate_conflict, find_duplicates, list_page, load_scoped, phone_digits, record_detail

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
    matches, hidden = await find_duplicates(db, user, email=data.get("email"), digits=phone_digits(data.get("phone")))
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
