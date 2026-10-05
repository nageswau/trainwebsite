"""bdm-006 (DEC-SCOPE-068, spec §5.3): BDM appointments.

Every `{appt_id}` resolves through `services.bdm_appointments.load_scoped` (out of scope = 404); every write is one transaction --
scope, row lock (organization before appointment), validation, change, event, audit, one commit here. Lists are
{items, total, limit, offset}, ordered by start time then id."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import BdmAppointment, BdmMeetingReport, BdmOrganization, User
from app.schemas import (
    BDM_APPOINTMENT_OPTIONAL_FIELDS,
    BdmAppointmentCreate,
    BdmAppointmentEnvelope,
    BdmAppointmentPage,
    BdmAppointmentReason,
    BdmAppointmentReschedule,
    BdmAppointmentStatus,
    BdmAppointmentType,
    BdmAppointmentUpdate,
    BdmMeetingReportCreate,
    BdmMeetingReportUpdate,
)
from app.services import bdm_appointments as svc
from app.services import bdm_organizations as org_svc
from app.services.bdm import bdm_context

router = APIRouter(prefix="/bdm/appointments", tags=["bdm-appointments"])
ARCHIVED = "This organization is archived — restore it before booking"
NOT_ASSIGNED = "Only the assigned BDM can book appointments for this organization"
FOREIGN_CONTACT = "Choose a contact of this organization"


async def _envelope(db: AsyncSession, user: User, appt: BdmAppointment, *, refresh: bool = True) -> dict:
    return {"appointment": await svc.appointment_out(db, user, appt, refresh=refresh)}


async def _contact_of(db: AsyncSession, org: BdmOrganization, contact_id: UUID):
    """A contact of another organization is a bad choice in this form (422), not a missing resource."""
    try:
        return await org_svc.load_contact(db, org, contact_id)
    except HTTPException:
        raise HTTPException(422, FOREIGN_CONTACT) from None


def _type_allowed(bdm_type: str, appointment_type: str) -> None:
    if appointment_type not in svc.appointment_types(bdm_type):
        raise HTTPException(422, f"This appointment type is not available for {bdm_type.capitalize()} BDMs")


async def _check_overlap(db: AsyncSession, user: User, starts_at, duration: int, confirm: bool, exclude_id: UUID | None = None) -> int:
    """A6: warn (409) unless acknowledged; returns the match count so the caller can audit the override."""
    matches, total = await svc.find_overlaps(db, user.id, starts_at, duration, exclude_id)
    if total and not confirm:
        svc.log("bdm_appt_overlap_warned", user, exclude_id or "-", match_count=total)
        raise svc.overlap_conflict(matches, total)
    return total


@router.get("", response_model=BdmAppointmentPage)
async def list_appointments(
    date_from: date | None = None,
    date_to: date | None = None,
    status: list[BdmAppointmentStatus] | None = Query(None),
    appointment_type: BdmAppointmentType | None = None,
    organization_id: UUID | None = None,
    bdm_user_id: UUID | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Filters are ANDed with the caller's scope, so they only narrow it (R-A10). One page query: organization + owner (no N+1)."""
    filters = await svc.caller_filters(db, user)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to")
    if bdm_user_id is not None:
        if user.role == "bdm":
            raise HTTPException(422, "bdm_user_id is only for managers")
        filters.append(BdmAppointment.bdm_user_id == bdm_user_id)
    filters += svc.ist_bounds(date_from, date_to)
    if status:
        filters.append(BdmAppointment.status.in_(status))
    if appointment_type:
        filters.append(BdmAppointment.appointment_type == appointment_type)
    if organization_id:
        filters.append(BdmAppointment.organization_id == organization_id)
    pattern = like_pattern(q)
    filters += _matching(pattern, BdmAppointment.code, BdmOrganization.name)
    joined = BdmOrganization.id == BdmAppointment.organization_id
    count = select(func.count()).select_from(BdmAppointment)
    if pattern:  # only the search reads the organization
        count = count.join(BdmOrganization, joined)
    total = await db.scalar(count.where(*filters))
    stmt = (
        select(BdmAppointment, BdmOrganization, User)
        .join(BdmOrganization, joined)
        .join(User, User.id == BdmAppointment.bdm_user_id)
        .where(*filters)
        .order_by(BdmAppointment.starts_at, BdmAppointment.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()
    now = await svc.db_now(db)
    return {"items": [svc.row_out(a, o, u, now) for a, o, u in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.post("", status_code=201, response_model=BdmAppointmentEnvelope)
async def create_appointment(payload: BdmAppointmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """spec §5.5, in this order so each refusal is exactly one rule. Not idempotent: a retry meets the overlap warning (R-A5)."""
    profile = await bdm_context(db, user)
    org = await org_svc.load_scoped(db, user, payload.organization_id, lock=True)  # out of type scope -> 404; serializes with archive
    if org.assigned_bdm_user_id != user.id:
        raise HTTPException(403, NOT_ASSIGNED)
    if org.archived_at is not None:
        raise HTTPException(422, ARCHIVED)
    contact = await _contact_of(db, org, payload.contact_id)
    _type_allowed(profile.bdm_type, payload.appointment_type)
    svc.require_future(payload.starts_at, await svc.db_now(db))
    overlaps = await _check_overlap(db, user, payload.starts_at, payload.duration_minutes, payload.confirm_overlap)
    appt = BdmAppointment(
        code=await svc.next_code(db),
        bdm_user_id=user.id,
        organization_id=org.id,
        starts_at=payload.starts_at,
        duration_minutes=payload.duration_minutes,
        appointment_type=payload.appointment_type,
        status="scheduled",
        **svc.snapshot(contact),
        **{k: getattr(payload, k) for k in BDM_APPOINTMENT_OPTIONAL_FIELDS},
    )
    db.add(appt)
    await db.flush()
    svc.record(db, appt, user, None, "scheduled")
    svc.audit(
        db, user, "create", appt.id,
        {
            "code": appt.code, "organization_id": str(org.id), "appointment_type": appt.appointment_type, "starts_at": appt.starts_at.isoformat(),
            "fields": sorted(k for k in BDM_APPOINTMENT_OPTIONAL_FIELDS if getattr(payload, k) is not None),
        },
    )
    if overlaps:
        svc.audit(db, user, "overlap_override", appt.id, {"match_count": overlaps})
    await db.commit()
    svc.log("bdm_appt_created", user, appt.id, organization_id=str(org.id), overlap_override=bool(overlaps))
    return await _envelope(db, user, appt)


@router.get("/{appt_id}", response_model=BdmAppointmentEnvelope)
async def get_appointment(appt_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    appt = await svc.load_scoped(db, user, appt_id)
    return await _envelope(db, user, appt, refresh=False)  # nothing was written


@router.patch("/{appt_id}", response_model=BdmAppointmentEnvelope)
async def update_appointment(appt_id: UUID, payload: BdmAppointmentUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """PATCH: only the fields sent; values equal to the stored ones are not changes (no audit, no updated_at bump, R-A6). A contact change
    locks the organization first (§5.7: organization -> appointment), so bdm-002's contact delete cannot remove it mid-write."""
    changes = payload.model_dump(exclude_unset=True, exclude={"confirm_overlap"})
    contact = None
    if "contact_id" in changes:  # the organization lock must come first, so peek at the appointment unlocked
        current = await svc.load_scoped(db, user, appt_id)
        svc.require_owner(user, current, "update")
        if changes["contact_id"] != current.contact_id:
            org = await org_svc.load_scoped(db, user, current.organization_id, lock=True)
            contact = await _contact_of(db, org, changes["contact_id"])
    appt = await svc.load_scoped(db, user, appt_id, lock=True)
    svc.require_owner(user, appt, "update")
    svc.require_open(appt)
    changes.pop("contact_id", None)
    changed = sorted(k for k, v in changes.items() if getattr(appt, k) != v)
    if "appointment_type" in changed:
        _type_allowed((await bdm_context(db, user)).bdm_type, changes["appointment_type"])
    overlaps = 0
    if "duration_minutes" in changed and changes["duration_minutes"] > appt.duration_minutes:  # shrinking cannot create a new clash
        overlaps = await _check_overlap(db, user, appt.starts_at, changes["duration_minutes"], payload.confirm_overlap, exclude_id=appt.id)
    for key in changed:
        setattr(appt, key, changes[key])
    if contact is not None:
        for key, value in svc.snapshot(contact).items():
            setattr(appt, key, value)
        changed = sorted({*changed, "contact_id"})
    if changed:
        svc.audit(db, user, "update", appt.id, {"fields": changed})
        if overlaps:
            svc.audit(db, user, "overlap_override", appt.id, {"match_count": overlaps})
    await db.commit()
    if changed:
        svc.log("bdm_appt_updated", user, appt.id, fields=changed)
    return await _envelope(db, user, appt)


async def _transitioning(db: AsyncSession, user: User, appt_id: UUID, action: str, to_status: str) -> BdmAppointment:
    """Scope (404), row lock, owner (403), then state (409) -- the order every action shares."""
    appt = await svc.load_scoped(db, user, appt_id, lock=True)
    svc.require_owner(user, appt, action)
    svc.require_transition(appt, to_status)
    return appt


async def _move(db: AsyncSession, user: User, appt: BdmAppointment, action: str, to_status: str, metadata: dict | None = None, **event) -> dict:
    """The tail every action shares: new status, its history event, audit, one commit, log."""
    before, appt.status = appt.status, to_status
    svc.record(db, appt, user, before, to_status, **event)
    svc.audit(db, user, action, appt.id, {"from": before, "to": to_status, **(metadata or {})})
    await db.commit()
    svc.log(f"bdm_appt_{action}", user, appt.id, from_status=before, to_status=to_status)
    return await _envelope(db, user, appt)


@router.post("/{appt_id}/confirm", response_model=BdmAppointmentEnvelope)
async def confirm_appointment(appt_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    appt = await _transitioning(db, user, appt_id, "confirm", "confirmed")
    return await _move(db, user, appt, "confirm", "confirmed")


@router.post("/{appt_id}/reschedule", response_model=BdmAppointmentEnvelope)
async def reschedule_appointment(appt_id: UUID, payload: BdmAppointmentReschedule, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC4: the old time goes into the event; the status is always Rescheduled (also from Rescheduled)."""
    appt = await _transitioning(db, user, appt_id, "reschedule", "rescheduled")
    svc.require_future(payload.starts_at, await svc.db_now(db))
    if payload.starts_at == appt.starts_at:
        raise HTTPException(422, "Choose a different time")
    duration = payload.duration_minutes or appt.duration_minutes
    overlaps = await _check_overlap(db, user, payload.starts_at, duration, payload.confirm_overlap, exclude_id=appt.id)
    old = appt.starts_at
    appt.starts_at, appt.duration_minutes = payload.starts_at, duration
    if overlaps:
        svc.audit(db, user, "overlap_override", appt.id, {"match_count": overlaps})
    return await _move(
        db, user, appt, "reschedule", "rescheduled", {"old_starts_at": old.isoformat(), "new_starts_at": payload.starts_at.isoformat()},
        old_starts_at=old, new_starts_at=payload.starts_at, reason=payload.reason,
    )


@router.post("/{appt_id}/cancel", response_model=BdmAppointmentEnvelope)
async def cancel_appointment(appt_id: UUID, payload: BdmAppointmentReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    appt = await _transitioning(db, user, appt_id, "cancel", "cancelled")
    return await _move(db, user, appt, "cancel", "cancelled", reason=payload.reason)


@router.post("/{appt_id}/no-show", response_model=BdmAppointmentEnvelope)
async def no_show_appointment(appt_id: UUID, payload: BdmAppointmentReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    appt = await _transitioning(db, user, appt_id, "no_show", "no_show")
    svc.require_started(appt, await svc.db_now(db), "no_show")
    return await _move(db, user, appt, "no_show", "no_show", reason=payload.reason)


async def _outcome_allowed(db: AsyncSession, user: User, outcome: str) -> None:
    bdm_type = (await bdm_context(db, user)).bdm_type
    if outcome not in svc.appointment_outcomes(bdm_type):
        raise HTTPException(422, f"This outcome is not available for {bdm_type.capitalize()} BDMs")


def _follow_up_allowed(due_on: date | None, now) -> None:
    if due_on is not None and due_on < svc.today_ist(now):
        raise HTTPException(422, "Next follow-up can't be in the past")


@router.post("/{appt_id}/complete", response_model=BdmAppointmentEnvelope)
async def complete_appointment(appt_id: UUID, payload: BdmMeetingReportCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """bdm-007 AC1: filing the meeting report is the only way to complete. One transaction: status, report, follow-up (AC3), event,
    audit. A second complete meets `completed` under the row lock -> 409."""
    appt = await _transitioning(db, user, appt_id, "complete", "completed")
    now = await svc.db_now(db)
    svc.require_started(appt, now, "complete")
    await _outcome_allowed(db, user, payload.outcome)
    _follow_up_allowed(payload.next_follow_up_on, now)
    db.add(BdmMeetingReport(appointment_id=appt.id, author_user_id=user.id, submitted_at=now, **{k: getattr(payload, k) for k in svc.REPORT_FIELDS}))
    follow_up = await svc.sync_follow_up(db, appt, payload.next_follow_up_on)
    # Set after the follow-up query: its autoflush must not write an outcome while the status is still open (the CHECKs pair them).
    appt.outcome, appt.next_follow_up_on = payload.outcome, payload.next_follow_up_on
    return await _move(db, user, appt, "complete", "completed", {"outcome": payload.outcome, "follow_up": follow_up is not None})


@router.patch("/{appt_id}/report", response_model=BdmAppointmentEnvelope)
async def update_report(appt_id: UUID, payload: BdmMeetingReportUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """bdm-007 §5.2 (AC4): the author changes the report on the IST day it was filed. Lock order appointment -> report -> follow-up.
    Values equal to the stored ones are not changes (no audit, no updated_at bump)."""
    appt = await svc.load_scoped(db, user, appt_id, lock=True)
    svc.require_owner(user, appt, "report_update")
    report = await svc.load_report(db, appt.id, lock=True)
    if report is None:
        raise HTTPException(409, svc.NO_REPORT)
    now = await svc.db_now(db)
    if not svc.report_editable(report, now):
        raise HTTPException(409, svc.REPORT_LOCKED)
    changes = payload.model_dump(exclude_unset=True)
    target = lambda key: report if key in svc.REPORT_FIELDS else appt  # noqa: E731 -- outcome / follow-up date live on the appointment
    changed = sorted(k for k, v in changes.items() if getattr(target(k), k) != v)
    if "outcome" in changed:
        await _outcome_allowed(db, user, changes["outcome"])
    follow_up = None
    if "next_follow_up_on" in changed:
        _follow_up_allowed(changes["next_follow_up_on"], now)
        follow_up = await svc.sync_follow_up(db, appt, changes["next_follow_up_on"])
    for key in changed:
        setattr(target(key), key, changes[key])
    if changed:
        svc.audit(db, user, "report_update", appt.id, {"fields": changed, **({"follow_up": follow_up} if follow_up else {})})
    await db.commit()
    if changed:
        svc.log("bdm_appt_report_updated", user, appt.id, fields=changed, follow_up=follow_up)
    return await _envelope(db, user, appt)
