"""AGN-008 -- an agency's applications for its students, with or without a login (DEC-SCOPE-050; spec §5.3).

Masters see the agency's applications; staff only those of students assigned to them (G4); anything outside the caller's scope is
404. Every write locks the organisation row first and the application row second (AGN-004's lock order), writes its history and
audit rows in the same transaction and commits once, so the duplicate check, the throttle and the status rules hold under
concurrency. Agents move an application forward up to status_tracking or withdraw it; the status route never sets `enrolled` (A4).
AGN-013 (DEC-SCOPE-054) amends A4 narrowly: only a Master confirms enrollment, through its own route, from an offer onwards.
AGN-012 (DEC-SCOPE-055): Master and Staff run the visa case of an application from an offer onwards, through its own two routes; the
case never moves the application stage.
"""

import logging
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_students import _gate, _require_master_action
from app.api.deps import get_current_user
from app.api.workflows import _maybe_trigger_agent_commission, _notify_user
from app.core.database import get_db
from app.models import AgentOrgMember, AgentStudent, ApplicationStatusHistory, AuditLog, OverseasApplication, University, User, VisaCase
from app.schemas import AgentApplicationCreate, AgentApplicationEnrollment, AgentApplicationStatus, AgentApplicationUpdate, AgentVisaStart, AgentVisaUpdate
from app.services.agent_applications import (
    ARCHIVED,
    DEFAULT_NEXT_ACTION,
    DUPLICATE,
    ENROLLABLE,
    MASTER_ONLY_ENROLLMENT,
    OFFER_NEEDED,
    OFFER_STAGES_ON,
    STALE,
    THROTTLED,
    WITHDRAWN,
    WITHDRAWN_REFUSED,
    check_course,
    check_transition,
    create_wait_seconds,
    detail,
    duplicate_exists,
    list_page,
    load_scoped,
    owner_record,
)
from app.services.agent_orgs import lock_active_org
from app.services.agent_students import load_scoped as load_scoped_student
from app.services.agent_visa import VISA_ENROLLED, VISA_EXISTS, VISA_OFFER_NEEDED, VISA_STALE, ChecklistGateRefused, check_dates, load_case, update_case

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
        student = await db.get(User, record.student_id)  # the foreign key guarantees the account exists
        await _notify_user(db, student, "Application created", f"Your application to {university.name} has been created.", "/overseas/student/applications")
    await db.commit()
    _log("agent_application_created", membership, user, item.id)
    return {"application": await detail(db, user, item, record=record)}


async def _refuse_closed(db: AsyncSession, user: User, item) -> AgentStudent | None:
    """A15 then A1: an archived student's applications and a withdrawn application are read-only. Returns the owner record so the
    write can hand it to `detail` instead of fetching it again."""
    record = await owner_record(db, user, item)
    if record is not None and record.status == "archived":
        raise HTTPException(409, ARCHIVED)
    if item.status == WITHDRAWN:
        raise HTTPException(409, WITHDRAWN_REFUSED)
    return record


@router.patch("/{application_id}")
async def update_application(application_id: UUID, payload: AgentApplicationUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    item = await _locked(db, user, membership, application_id)
    record = await _refuse_closed(db, user, item)
    changes = payload.model_dump(exclude_unset=True)
    changed = sorted(k for k, v in changes.items() if getattr(item, k) != v)
    if "course_id" in changed:
        await check_course(db, item.university_id, changes["course_id"])
        if await duplicate_exists(db, agent_student_id=item.agent_student_id, student_id=item.student_id, university_id=item.university_id, course_id=changes["course_id"], exclude_id=item.id):
            raise HTTPException(409, DUPLICATE)
    for key in changed:
        setattr(item, key, changes[key])
    if changed:
        if "next_action" in changed:  # the existing PATCH's rule: a next-action change is part of the status timeline
            db.add(ApplicationStatusHistory(application_id=item.id, from_status=item.status, to_status=item.status, next_action=item.next_action, changed_by_id=user.id))
        _audit(db, user, "update", item.id, {"fields": changed})
    await db.commit()
    if changed:
        _log("agent_application_updated", membership, user, item.id, fields=changed)
    return {"application": await detail(db, user, item, record=record)}


@router.post("/{application_id}/status")
async def change_status(application_id: UUID, payload: AgentApplicationStatus, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    item = await _locked(db, user, membership, application_id)
    record = await _refuse_closed(db, user, item)
    if payload.expected_status is not None and payload.expected_status != item.status:
        raise HTTPException(409, STALE)
    check_transition(item.status, payload.to_status)
    old = item.status
    item.status = payload.to_status
    if payload.next_action is not None:
        item.next_action = payload.next_action
    db.add(ApplicationStatusHistory(application_id=item.id, from_status=old, to_status=item.status, next_action=item.next_action, notes=payload.notes, changed_by_id=user.id))
    withdrawn = item.status == WITHDRAWN
    _audit(db, user, "withdraw" if withdrawn else "advance", item.id, {"from_status": old, "to_status": item.status})
    await db.commit()
    _log("agent_application_withdrawn" if withdrawn else "agent_application_advanced", membership, user, item.id, from_status=old, to_status=item.status)
    return {"application": await detail(db, user, item, record=record)}


@router.put("/{application_id}/enrollment")
async def save_enrollment(application_id: UUID, payload: AgentApplicationEnrollment, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-013 (DEC-SCOPE-054): a Master confirms enrollment from an offer onwards -- `enrolled`, one history row and the AGT-003
    commission trigger, which creates at most one commission per application -- or, once enrolled, corrects the date and student
    ID (no history row, no commission). Locks as every agency write: organisation, then the row; one commit."""
    membership = _gate(user)
    _require_master_action(user, MASTER_ONLY_ENROLLMENT)  # E1: refused before any load, so staff learn nothing about ids
    item = await _locked(db, user, membership, application_id)
    record = await _refuse_closed(db, user, item)
    if payload.expected_status != item.status:
        raise HTTPException(409, STALE)
    old = item.status
    confirming = old != "enrolled"
    if confirming and old not in ENROLLABLE:
        raise HTTPException(422, OFFER_NEEDED)
    fields = {"enrollment_date": payload.enrollment_date, "university_student_id": payload.university_student_id}
    changed = [key for key, value in fields.items() if getattr(item, key) != value]
    for key in changed:
        setattr(item, key, fields[key])
    if confirming:
        item.enrollment_confirmed_at = datetime.now(UTC)
        item.status = "enrolled"
        db.add(ApplicationStatusHistory(application_id=item.id, from_status=old, to_status=item.status, next_action=item.next_action, notes=payload.notes, changed_by_id=user.id))
        await _maybe_trigger_agent_commission(db, item, old, user)
        _audit(db, user, "enroll", item.id, {"from_status": old, "to_status": item.status})
    elif changed:  # a correction: no history row, no commission; an unchanged re-save writes nothing
        item.enrollment_confirmed_at = item.enrollment_confirmed_at or datetime.now(UTC)
        _audit(db, user, "enrollment_update", item.id, {"fields": changed})
    await db.commit()
    if confirming:
        _log("agent_application_enrolled", membership, user, item.id, from_status=old)
    elif changed:
        _log("agent_application_enrollment_updated", membership, user, item.id, fields=changed)
    return {"application": await detail(db, user, item, record=record)}


async def _visa_entry(db: AsyncSession, user: User, membership: AgentOrgMember, application_id: UUID):
    """AGN-012: the enrollment route's entry (organisation lock, scoped row lock, archived/withdrawn 409) plus enrolled 409 (V5). The
    case is read after the application lock, so every agency visa write for one application is serialised."""
    item = await _locked(db, user, membership, application_id)
    record = await _refuse_closed(db, user, item)
    if item.status == "enrolled":
        raise HTTPException(409, VISA_ENROLLED)
    return item, record


_VISA_EVENTS = {"visa_decision": "agent_visa_decided", "visa_advance": "agent_visa_advanced", "visa_update": "agent_visa_updated"}


@router.post("/{application_id}/visa", status_code=201)
async def start_visa(application_id: UUID, payload: AgentVisaStart, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-012 (DEC-SCOPE-055) §4.1: start the application's visa case at `checklist`, from an offer onwards; one case per application."""
    membership = _gate(user)
    item, record = await _visa_entry(db, user, membership, application_id)
    if payload.expected_status != item.status:
        raise HTTPException(409, STALE)
    if item.status not in OFFER_STAGES_ON:
        raise HTTPException(422, VISA_OFFER_NEEDED)
    if await load_case(db, item.id) is not None:
        raise HTTPException(409, VISA_EXISTS)
    check_dates(payload.visa_application_date, payload.interview_date)
    db.add(
        VisaCase(
            application_id=item.id,
            status="checklist",
            checklist=payload.checklist,
            visa_application_date=payload.visa_application_date,
            appointment_date=payload.appointment_date,
            interview_date=payload.interview_date,
        )
    )
    _audit(db, user, "visa_start", item.id, {"checklist_items": len(payload.checklist)})
    await db.commit()
    _log("agent_visa_started", membership, user, item.id, checklist_items=len(payload.checklist))
    return {"application": await detail(db, user, item, record=record)}


@router.patch("/{application_id}/visa")
async def update_visa_case(application_id: UUID, payload: AgentVisaUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-012 §4.2: dates, the checklist (at `checklist` only), a forward move through the checklist gate, or the final decision."""
    membership = _gate(user)
    item, record = await _visa_entry(db, user, membership, application_id)
    case = await load_case(db, item.id)
    if case is None:  # the screen believed a case exists; a 404 would read as "the application is gone"
        raise HTTPException(409, VISA_STALE)
    try:
        outcome = await update_case(db, case, payload.model_dump(exclude_unset=True))
    except ChecklistGateRefused as refused:
        _log("agent_visa_gate_blocked", membership, user, item.id, level=logging.WARNING, from_stage=case.status, unverified_items=len(refused.unverified))
        raise
    if outcome is None:  # nothing changed: no write, no audit
        return {"application": await detail(db, user, item, record=record)}
    action, metadata = outcome
    _audit(db, user, action, item.id, metadata)
    await db.commit()
    _log(_VISA_EVENTS[action], membership, user, item.id, **{k: v for k, v in metadata.items() if k != "decision"})  # never the outcome (§10.3)
    return {"application": await detail(db, user, item, record=record)}
