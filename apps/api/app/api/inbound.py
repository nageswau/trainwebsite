from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.identifiers import uuid_reference
from app.models import (
    ApplicationStatusHistory,
    AuditLog,
    InboundUniversityEmail,
    Notification,
    NotificationDelivery,
    OverseasApplication,
    User,
)
from app.schemas import InboundUniversityEmailIn
from app.services.integrations import send_notification

router = APIRouter(prefix="/inbound", tags=["inbound-integrations"])


def _check_webhook_secret(value: str | None) -> None:
    if settings.inbound_email_webhook_secret and value != settings.inbound_email_webhook_secret:
        raise HTTPException(401, "Invalid inbound email webhook secret")
    if settings.environment == "production" and not settings.inbound_email_webhook_secret:
        raise HTTPException(503, "Inbound email webhook secret is not configured")


async def _match_application(db: AsyncSession, payload: InboundUniversityEmailIn) -> tuple[OverseasApplication | None, int, str]:
    metadata = payload.metadata or {}
    if metadata.get("application_id"):
        item = await db.get(OverseasApplication, uuid_reference(metadata["application_id"], "application reference", required=False))
        if item:
            return item, 100, "matched"
    if metadata.get("application_reference"):
        item = await db.scalar(select(OverseasApplication).where(OverseasApplication.application_reference == str(metadata["application_reference"])))
        if item:
            return item, 100, "matched"
    if metadata.get("student_email"):
        student = await db.scalar(select(User).where(User.email == str(metadata["student_email"]).lower(), User.role == "overseas_student"))
        if student:
            applications = (await db.scalars(select(OverseasApplication).where(OverseasApplication.student_id == student.id).order_by(OverseasApplication.updated_at.desc()).limit(2))).all()
            if len(applications) == 1:
                return applications[0], 90, "matched"
            if len(applications) > 1:
                return None, 0, "ambiguous"
    haystack = f"{payload.subject}\n{payload.body}".lower()
    references = (await db.scalars(select(OverseasApplication).where(OverseasApplication.application_reference.is_not(None)).limit(5000))).all()
    matches = [item for item in references if item.application_reference and item.application_reference.lower() in haystack]
    if len(matches) == 1:
        return matches[0], 95, "matched"
    if len(matches) > 1:
        return None, 0, "ambiguous"
    students = (await db.scalars(select(User).where(User.role == "overseas_student", User.division == "overseas", User.active.is_(True)).limit(5000))).all()
    name_matches = [student for student in students if len(student.full_name) >= 5 and student.full_name.lower() in haystack]
    if len(name_matches) == 1:
        applications = (await db.scalars(select(OverseasApplication).where(OverseasApplication.student_id == name_matches[0].id).order_by(OverseasApplication.updated_at.desc()).limit(2))).all()
        if len(applications) == 1:
            return applications[0], 55, "matched_low_confidence"
        if len(applications) > 1:
            return None, 0, "ambiguous"
    return None, 0, "unmatched"


async def _notify_student(db: AsyncSession, email: InboundUniversityEmail, application: OverseasApplication) -> None:
    student = await db.get(User, application.student_id)
    if not student:
        return
    notification = Notification(user_id=student.id, title="University update received", body=email.subject, read=False, action_url="/overseas/student/university-communication")
    db.add(notification)
    await db.flush()
    status, error = await send_notification("email", {"to": student.email, "title": notification.title, "body": notification.body, "action_url": notification.action_url})
    db.add(NotificationDelivery(notification_id=notification.id, channel="email", status=status, error=error, sent_at=datetime.now(UTC) if status == "sent" else None))


@router.post("/university-email", status_code=202)
async def receive_university_email(payload: InboundUniversityEmailIn, x_webhook_secret: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    _check_webhook_secret(x_webhook_secret)
    existing = await db.scalar(select(InboundUniversityEmail).where(InboundUniversityEmail.external_message_id == payload.external_message_id))
    if existing:
        return {"accepted": True, "id": existing.id, "duplicate": True, "match_status": existing.match_status}
    application, confidence, match_status = await _match_application(db, payload)
    item = InboundUniversityEmail(
        external_message_id=payload.external_message_id,
        sender=str(payload.sender).lower(),
        recipient=payload.recipient,
        subject=payload.subject,
        body=payload.body,
        received_at=payload.received_at or datetime.now(UTC),
        student_id=application.student_id if application else None,
        application_id=application.id if application else None,
        match_status=match_status,
        match_confidence=confidence,
        attachments=payload.attachments,
        raw_metadata=payload.metadata,
    )
    db.add(item)
    await db.flush()
    if application:
        await _notify_student(db, item, application)
        db.add(
            ApplicationStatusHistory(
                application_id=application.id,
                from_status=application.status,
                to_status=application.status,
                next_action=application.next_action,
                notes=f"University email received: {payload.subject}",
                changed_by_id=None,
            )
        )
    db.add(
        AuditLog(
            user_id=None, action="university_email.receive", entity_type="inbound_university_email", entity_id=str(item.id), metadata_json={"match_status": match_status, "confidence": confidence}
        )
    )
    await db.commit()
    await db.refresh(item)
    return {"accepted": True, "id": item.id, "duplicate": False, "match_status": item.match_status, "match_confidence": item.match_confidence, "application_id": item.application_id}


@router.get("/university-email")
async def list_university_email(match_status: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "overseas_admin", "counselor", "university_rep"}:
        raise HTTPException(403, "Overseas operations role required")
    stmt = select(InboundUniversityEmail).order_by(InboundUniversityEmail.received_at.desc())
    if match_status:
        stmt = stmt.where(InboundUniversityEmail.match_status == match_status)
    rows = (await db.scalars(stmt.limit(500))).all()
    if user.role == "counselor":
        assigned = set((await db.scalars(select(OverseasApplication.id).where(OverseasApplication.counselor_id == user.id))).all())
        rows = [row for row in rows if row.application_id in assigned or row.application_id is None]
    elif user.role == "university_rep":
        university_id = uuid_reference(user.profile.get("university_id"), "university reference", required=False)
        assigned = set((await db.scalars(select(OverseasApplication.id).where(OverseasApplication.university_id == university_id))).all())
        rows = [row for row in rows if row.application_id in assigned]
    return [
        {
            "id": row.id,
            "external_message_id": row.external_message_id,
            "sender": row.sender,
            "subject": row.subject,
            "received_at": row.received_at,
            "student_id": row.student_id,
            "application_id": row.application_id,
            "match_status": row.match_status,
            "match_confidence": row.match_confidence,
            "attachments": row.attachments,
        }
        for row in rows
    ]


@router.patch("/university-email/{email_id}/match")
async def manually_match_email(email_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "overseas_admin", "counselor"}:
        raise HTTPException(403, "Overseas operations role required")
    email = await db.get(InboundUniversityEmail, email_id)
    application = await db.get(OverseasApplication, uuid_reference(payload.get("application_id"), "application reference"))
    if not email or not application:
        raise HTTPException(404, "Email or application not found")
    if user.role == "counselor" and application.counselor_id != user.id:
        raise HTTPException(403, "Application is outside your assigned scope")
    email.application_id = application.id
    email.student_id = application.student_id
    email.match_status = "manually_matched"
    email.match_confidence = 100
    await _notify_student(db, email, application)
    db.add(AuditLog(user_id=user.id, action="university_email.manual_match", entity_type="inbound_university_email", entity_id=str(email.id), metadata_json={"application_id": application.id}))
    await db.commit()
    return {"id": email.id, "match_status": email.match_status, "application_id": email.application_id}
