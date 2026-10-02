"""AGN-008 -- an agency's applications for its students, with or without a login (DEC-SCOPE-050; spec §5.3).

Masters see the agency's applications; staff only those of students assigned to them (G4); anything outside the caller's scope is
404. Every write locks the organisation row first and the application row second (AGN-004's lock order), writes its history and
audit rows in the same transaction and commits once, so the duplicate check, the throttle and the status rules hold under
concurrency. Agents move an application forward up to status_tracking or withdraw it; `enrolled` stays with counselor, university
and admin, so an agent never accrues their own commission (A4).
"""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_students import _gate
from app.api.deps import get_current_user
from app.api.workflows import _notify_user
from app.core.database import get_db
from app.models import AgentOrgMember, ApplicationStatusHistory, AuditLog, OverseasApplication, University, User
from app.schemas import AgentApplicationCreate
from app.services.agent_applications import (
    ARCHIVED,
    DEFAULT_NEXT_ACTION,
    DUPLICATE,
    THROTTLED,
    check_course,
    create_wait_seconds,
    detail,
    duplicate_exists,
    list_page,
    load_scoped,
)
from app.services.agent_orgs import lock_active_org
from app.services.agent_students import load_scoped as load_scoped_student

logger = logging.getLogger("app.agent_applications")

router = APIRouter(prefix="/workflows/overseas/agent/crm/applications", tags=["agent-applications"])

StatusGroup = Literal["all", "draft", "submitted", "offer", "visa", "enrolled", "withdrawn"]


def _audit(db: AsyncSession, user: User, action: str, application_id, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed, SEC-001); ids, field names and statuses only. The `overseas.application.*`
    names are the ones the existing paths write, so AGN-021 activity and the throttle read one record."""
    db.add(AuditLog(user_id=user.id, action=f"overseas.application.{action}", entity_type="overseas_application", entity_id=str(application_id), metadata_json=metadata or {}))


def _log(event: str, membership: AgentOrgMember, user: User, application_id, *, level: int = logging.INFO, **extra) -> None:
    logger.log(level, event, extra={"extra_fields": {"org_id": str(membership.org_id), "actor_id": str(user.id), "application_id": str(application_id), **extra}})


async def _locked(db: AsyncSession, user: User, membership: AgentOrgMember, application_id: UUID):
    """Organisation lock first (the order every agency write uses), then the scoped row -- out of scope stays 404."""
    await lock_active_org(db, membership.org_id)
    return await load_scoped(db, user, application_id, lock=True)


@router.get("")
async def list_applications(
    status: StatusGroup = "all",
    student: UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _gate(user)
    return await list_page(db, user, group=status, agent_student_id=student, limit=limit, offset=offset)


@router.get("/{application_id}")
async def get_application(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _gate(user)
    return {"application": await detail(db, user, await load_scoped(db, user, application_id))}


@router.post("", status_code=201)
async def create_application(payload: AgentApplicationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    await lock_active_org(db, membership.org_id)  # serialises the throttle count and the duplicate check for the agency
    wait = await create_wait_seconds(db, user)
    if wait:
        _log("agent_application_create_throttled", membership, user, "-", level=logging.WARNING, wait_seconds=wait)
        raise HTTPException(429, THROTTLED, headers={"Retry-After": str(wait)})
    record = await load_scoped_student(db, user, payload.agent_student_id)  # 404 "Student not found" outside scope
    if record.status == "archived":
        raise HTTPException(409, ARCHIVED)
    university = await db.get(University, payload.university_id)
    if university is None:
        raise HTTPException(404, "University not found")
    await check_course(db, university.id, payload.course_id)
    if await duplicate_exists(db, agent_student_id=record.id, student_id=record.student_id, university_id=university.id, course_id=payload.course_id):
        raise HTTPException(409, DUPLICATE)
    item = OverseasApplication(
        agent_id=user.id,
        agent_student_id=record.id,
        student_id=record.student_id,
        university_id=university.id,
        course_id=payload.course_id,
        intake=payload.intake,
        status="enquiry",
        application_reference=payload.application_reference,
        submitted_on=payload.submitted_on,
        application_deadline=payload.application_deadline,
        offer_deadline=payload.offer_deadline,
        next_action=payload.next_action or DEFAULT_NEXT_ACTION,
    )
    db.add(item)
    await db.flush()
    db.add(ApplicationStatusHistory(application_id=item.id, from_status=None, to_status=item.status, next_action=item.next_action, changed_by_id=user.id))
    _audit(db, user, "create", item.id, {"agent_student_id": str(record.id), "university_id": str(university.id)})
    if record.student_id is not None:  # A8: a student with a login keeps today's notification
        student = await db.get(User, record.student_id)
        if student is not None:
            await _notify_user(db, student, "Application created", f"Your application to {university.name} has been created.", "/overseas/student/applications")
    await db.commit()
    _log("agent_application_created", membership, user, item.id)
    return {"application": await detail(db, user, item)}
