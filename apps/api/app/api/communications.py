from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.identifiers import uuid_reference
from app.models import AuditLog, Batch, Enrollment, LiveSession, Message, Notification, NotificationDelivery, User
from app.schemas import MeetingCreate, RecordingLinkUpdate
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
    if recipient_id:
        recipient = await db.get(User, uuid_reference(recipient_id, "recipient reference"))
        if not recipient:
            raise HTTPException(404, "Recipient not found")
        if user.role != "super_admin" and recipient.division != user.division:
            raise HTTPException(403, "Cross-division notification is not allowed")
        db.add(Notification(user_id=recipient.id, title=payload["title"], body=payload["body"], action_url=payload.get("action_url")))
    statuses = {}
    for channel in payload.get("channels", ["email"]):
        status, error = await send_notification(
            channel,
            {
                "user_id": recipient_id,
                "to": recipient.email if recipient_id else None,
                "phone": recipient.phone if recipient_id else None,
                "title": payload["title"],
                "body": payload["body"],
                "metadata": payload.get("metadata", {}),
            },
        )
        statuses[channel] = status
        if recipient_id:
            notification = await db.scalar(select(Notification).where(Notification.user_id == recipient_id).order_by(Notification.id.desc()))
            if notification:
                db.add(NotificationDelivery(notification_id=notification.id, channel=channel, status=status, error=error, sent_at=datetime.now(UTC) if status == "sent" else None))
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
        }
        for session, batch in rows
    ]


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
