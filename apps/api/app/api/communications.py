from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.identifiers import uuid_reference
from app.models import Attendance, AuditLog, Batch, Enrollment, LiveSession, Message, Notification, User
from app.notifications.dispatch import queue_deliveries
from app.schemas import LiveSessionCancel, LiveSessionUpdate, MeetingCreate, RecordingLinkUpdate
from app.services.integrations import send_notification
from app.services.meetings import MeetingProviderError, create_provider_meeting

router = APIRouter(prefix="/communications", tags=["communications"])


@router.get("/messages/{other_user_id}")
async def conversation(other_user_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    other = await db.get(User, other_user_id)
    if not other:
        raise HTTPException(404, "User not found")
    if user.role != "super_admin" and other.division != user.division:
        raise HTTPException(403, "Cross-division messaging is not allowed")
    rows = (
        await db.scalars(
            select(Message)
            .where(or_((Message.sender_id == user.id) & (Message.recipient_id == other_user_id), (Message.sender_id == other_user_id) & (Message.recipient_id == user.id)))
            .order_by(Message.created_at)
            .limit(500)
        )
    ).all()
    for x in rows:
        if x.recipient_id == user.id:
            x.read = True
    await db.commit()
    return [
        {"id": x.id, "sender_id": x.sender_id, "recipient_id": x.recipient_id, "body": x.body, "read": x.read, "created_at": x.created_at, "context_type": x.context_type, "context_id": x.context_id}
        for x in rows
    ]


@router.post("/messages", status_code=201)
async def send_message(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    recipient = await db.get(User, uuid_reference(payload.get("recipient_id"), "recipient reference"))
    if not recipient or not recipient.active:
        raise HTTPException(404, "Recipient unavailable")
    if user.role != "super_admin" and recipient.division != user.division:
        raise HTTPException(403, "Cross-division messaging is not allowed")
    item = Message(
        division=recipient.division if user.division == "global" else user.division,
        sender_id=user.id,
        recipient_id=recipient.id,
        context_type=payload.get("context_type", "direct"),
        context_id=uuid_reference(payload.get("context_id"), "conversation reference", required=False),
        body=str(payload["body"]).strip(),
    )
    if not item.body:
        raise HTTPException(422, "Message body is required")
    db.add(item)
    await db.flush()
    db.add(Notification(user_id=recipient.id, title=f"Message from {user.full_name}", body=item.body[:240], read=False, action_url=payload.get("action_url")))
    db.add(AuditLog(user_id=user.id, action="message.send", entity_type="message", entity_id=str(item.id), metadata_json={"recipient_id": recipient.id}))
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "created_at": item.created_at}


@router.post("/notify", status_code=202)
async def notify(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "it_admin", "overseas_admin", "placement_team", "counselor"}:
        raise HTTPException(403, "Notification permission required")
    recipient_id = payload.get("user_id")
    channels = payload.get("channels", ["email"])
    statuses: dict[str, str] = {}
    if recipient_id:
        recipient = await db.get(User, uuid_reference(recipient_id, "recipient reference"))
        if not recipient:
            raise HTTPException(404, "Recipient not found")
        if user.role != "super_admin" and recipient.division != user.division:
            raise HTTPException(403, "Cross-division notification is not allowed")
        notification = Notification(user_id=recipient.id, title=payload["title"], body=payload["body"], action_url=payload.get("action_url"))
        db.add(notification)
        # ENH-014: queued per channel, sent after commit; WhatsApp/SMS only for a recipient who opted in.
        statuses = {row.channel: row.status for row in await queue_deliveries(db, notification, recipient, channels=channels)}
    else:
        for channel in channels:
            status, _error = await send_notification(channel, {"user_id": None, "to": None, "phone": None, "title": payload["title"], "body": payload["body"], "metadata": payload.get("metadata", {})})
            statuses[channel] = status
    db.add(AuditLog(user_id=user.id, action="notification.send", entity_type="notification", entity_id=None, metadata_json={"channels": statuses, "recipient_id": recipient_id}))
    await db.commit()
    return {"queued": True, "channels": statuses}


@router.post("/it/live-sessions", status_code=201)
async def create_live_session(payload: MeetingCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"trainer", "it_admin", "super_admin"}:
        raise HTTPException(403, "Trainer/admin required")
    batch = await db.get(Batch, payload.batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    if user.role == "trainer" and batch.trainer_id != user.id:
        raise HTTPException(403, "Trainer is not assigned to this batch")
    try:
        batch_timezone = ZoneInfo(batch.timezone or "Asia/Kolkata")
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(422, "Batch timezone is invalid") from exc
    starts_at = payload.starts_at.replace(tzinfo=batch_timezone) if payload.starts_at.tzinfo is None else payload.starts_at
    ends_at = payload.ends_at.replace(tzinfo=batch_timezone) if payload.ends_at.tzinfo is None else payload.ends_at
    if ends_at <= starts_at:
        raise HTTPException(422, "Meeting end time must be after start time")
    attendee_emails = [str(email) for email in payload.attendee_emails]
    if not attendee_emails:
        attendee_emails = list((await db.scalars(select(User.email).join(Enrollment, Enrollment.student_id == User.id).where(Enrollment.batch_id == batch.id, Enrollment.status == "active"))).all())
    try:
        meeting = await create_provider_meeting(
            payload.provider, title=payload.title, agenda=payload.agenda, starts_at=starts_at, ends_at=ends_at, attendee_emails=attendee_emails, meeting_url=payload.meeting_url
        )
    except MeetingProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    item = LiveSession(
        batch_id=batch.id,
        trainer_id=user.id if user.role == "trainer" else batch.trainer_id,
        title=payload.title,
        starts_at=starts_at,
        ends_at=ends_at,
        provider=meeting.provider,
        meeting_url=meeting.meeting_url,
        host_url=meeting.host_url,
        provider_event_id=meeting.provider_event_id,
        provider_meeting_id=meeting.provider_meeting_id,
        sync_status=meeting.sync_status,
        status="scheduled",
    )
    db.add(item)
    await db.flush()
    students = (await db.execute(select(User).join(Enrollment, Enrollment.student_id == User.id).where(Enrollment.batch_id == batch.id, Enrollment.status == "active"))).scalars().all()
    for student in students:
        notification = Notification(user_id=student.id, title="Live class scheduled", body=f"{item.title} is scheduled for {item.starts_at.isoformat()}.", read=False, action_url="/it/student/course")
        db.add(notification)
    db.add(AuditLog(user_id=user.id, action="live_session.create", entity_type="live_session", entity_id=str(item.id), metadata_json={"provider": item.provider, "sync_status": item.sync_status}))
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "provider": item.provider, "meeting_url": item.meeting_url, "host_url": item.host_url, "sync_status": item.sync_status, "status": item.status}


@router.get("/it/live-sessions")
async def list_live_sessions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(LiveSession, Batch).join(Batch)
    if user.role == "it_student":
        stmt = stmt.join(Enrollment, Enrollment.batch_id == Batch.id).where(Enrollment.student_id == user.id, Enrollment.status == "active")
    elif user.role == "trainer":
        stmt = stmt.where(Batch.trainer_id == user.id)
    elif user.role not in {"it_admin", "super_admin"}:
        raise HTTPException(403, "Live-session access denied")
    rows = (await db.execute(stmt.order_by(LiveSession.starts_at.desc()).limit(300))).all()
    return [
        {
            "id": session.id,
            "batch": batch.name,
            "title": session.title,
            "starts_at": session.starts_at,
            "ends_at": session.ends_at,
            "provider": session.provider,
            "meeting_url": session.meeting_url,
            "host_url": session.host_url if user.role in {"trainer", "it_admin", "super_admin"} else None,
            "recording_url": session.recording_url,
            "recording_status": session.recording_status,
            "sync_status": session.sync_status,
            "status": session.status,
            "cancel_reason": session.cancel_reason,
            "timezone": batch.timezone,  # nehn-029: the reschedule form edits times in the batch's zone
        }
        for session, batch in rows
    ]


PROVIDER_LABEL = {"google_meet": "Google Meet", "zoho_meeting": "Zoho Meeting"}


async def _manageable_session(session_id: UUID, user: User, db: AsyncSession) -> tuple[LiveSession, Batch]:
    """nehn-029: a not-yet-started, not-cancelled session the caller may change, row-locked so a double submit cannot act twice."""
    if user.role not in {"trainer", "it_admin", "super_admin"}:
        raise HTTPException(403, "Trainer/admin required")
    item = await db.get(LiveSession, session_id, with_for_update=True)
    if not item:
        raise HTTPException(404, "Live session not found")
    batch = await db.get(Batch, item.batch_id)
    if user.role == "trainer" and (not batch or batch.trainer_id != user.id):
        raise HTTPException(403, "Session is outside your assigned batch")
    if item.status == "cancelled":
        raise HTTPException(409, "This live session is cancelled")
    if item.starts_at <= datetime.now(UTC):
        raise HTTPException(409, "Past sessions cannot be rescheduled or cancelled")
    return item, batch


def _batch_zone(batch: Batch) -> ZoneInfo:
    try:
        return ZoneInfo(batch.timezone or "Asia/Kolkata")
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(422, "Batch timezone is invalid") from exc


def _provider_warning(item: LiveSession, change: str) -> str | None:
    """No provider update API is wired (the Zoho live-class decisions are open): the local change stands and the trainer is told."""
    label = PROVIDER_LABEL.get(item.provider)
    if not label:
        return None
    item.sync_status = "manual_update_required"
    return f"EduSphere has {change} this session, but {label} was not changed. {change.capitalize()} the {label} meeting yourself so its invitation matches."


async def _notify_students(db: AsyncSession, batch: Batch, title: str, body: str) -> None:
    students = (await db.scalars(select(User).join(Enrollment, Enrollment.student_id == User.id).where(Enrollment.batch_id == batch.id, Enrollment.status == "active"))).all()
    for student in students:
        notification = Notification(user_id=student.id, title=title, body=body, read=False, action_url="/it/student/course")
        db.add(notification)
        await queue_deliveries(db, notification, student)  # in-app row + email (WhatsApp/SMS on opt-in), sent by the worker after commit


def _when(value: datetime, zone: ZoneInfo) -> str:
    return value.astimezone(zone).strftime("%d %b %Y, %I:%M %p ") + str(zone)


@router.patch("/it/live-sessions/{session_id}")
async def update_live_session(session_id: UUID, payload: LiveSessionUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item, batch = await _manageable_session(session_id, user, db)
    zone = _batch_zone(batch)
    changes = payload.model_dump(exclude_none=True)
    for key in ("starts_at", "ends_at"):
        if key in changes and changes[key].tzinfo is None:
            changes[key] = changes[key].replace(tzinfo=zone)
    starts_at, ends_at = changes.get("starts_at", item.starts_at), changes.get("ends_at", item.ends_at)
    if "starts_at" in changes and starts_at <= datetime.now(UTC):
        raise HTTPException(422, "The new start time must be in the future")
    if ends_at is not None and ends_at <= starts_at:
        raise HTTPException(422, "Meeting end time must be after start time")
    changed = sorted(key for key, value in changes.items() if getattr(item, key) != value)
    warning = None
    if changed:
        original_title = item.title
        for key in changed:
            setattr(item, key, changes[key])
        moved = bool({"starts_at", "ends_at"} & set(changed))
        warning = _provider_warning(item, "rescheduled" if moved else "updated")
        await _notify_students(
            db,
            batch,
            "Live class rescheduled" if moved else "Live class updated",
            f'{original_title} is now "{item.title}" on {_when(item.starts_at, zone)}.' if item.title != original_title else f"{item.title} is now on {_when(item.starts_at, zone)}.",
        )
        db.add(AuditLog(user_id=user.id, action="live_session.update", entity_type="live_session", entity_id=str(item.id), metadata_json={"changed": changed, "provider": item.provider}))
    await db.commit()
    return {
        "id": item.id,
        "title": item.title,
        "starts_at": item.starts_at,
        "ends_at": item.ends_at,
        "meeting_url": item.meeting_url,
        "status": item.status,
        "sync_status": item.sync_status,
        "warning": warning,
    }


@router.post("/it/live-sessions/{session_id}/cancel")
async def cancel_live_session(session_id: UUID, payload: LiveSessionCancel, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item, batch = await _manageable_session(session_id, user, db)
    zone = _batch_zone(batch)
    item.status, item.cancel_reason = "cancelled", payload.reason
    warning = _provider_warning(item, "cancelled")
    # Attendance is kept per batch and date; anything already marked for that date stays (the trainer is told how much).
    marked = await db.scalar(select(func.count()).select_from(Attendance).where(Attendance.batch_id == batch.id, Attendance.session_date == item.starts_at.astimezone(zone).date()))
    await _notify_students(db, batch, "Live class cancelled", f"{item.title} on {_when(item.starts_at, zone)} is cancelled. Reason: {payload.reason}")
    db.add(AuditLog(user_id=user.id, action="live_session.cancel", entity_type="live_session", entity_id=str(item.id), metadata_json={"provider": item.provider, "attendance_records": marked}))
    await db.commit()
    return {"id": item.id, "status": item.status, "cancel_reason": item.cancel_reason, "sync_status": item.sync_status, "attendance_records": marked, "warning": warning}


@router.patch("/it/live-sessions/{session_id}/recording")
async def update_recording_link(session_id: UUID, payload: RecordingLinkUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"trainer", "it_admin", "super_admin"}:
        raise HTTPException(403, "Trainer/admin required")
    item = await db.get(LiveSession, session_id)
    if not item:
        raise HTTPException(404, "Live session not found")
    batch = await db.get(Batch, item.batch_id)
    if user.role == "trainer" and (not batch or batch.trainer_id != user.id):
        raise HTTPException(403, "Session is outside your assigned batch")
    item.recording_url = payload.recording_url
    item.recording_external_id = payload.recording_external_id
    item.recording_status = payload.recording_status
    db.add(
        AuditLog(
            user_id=user.id,
            action="live_session.recording_update",
            entity_type="live_session",
            entity_id=str(item.id),
            metadata_json={"provider": item.provider, "recording_status": item.recording_status},
        )
    )
    await db.commit()
    return {"id": item.id, "recording_status": item.recording_status, "recording_url": item.recording_url}
