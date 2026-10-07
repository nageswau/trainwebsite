"""tel-015 (DEC-SCOPE-114, spec §3): a lead's merged timeline -- one `UNION ALL` over the tables that already record each event (D2: nothing
is copied, so an unlink or a same-day delete is reflected as in its own section). The caller has applied its route's scope (D1); this
module only sees a lead id. Read only; nothing is logged.

Each branch yields the same columns. Keys, not labels, for calls / messages / follow-ups / appointments (the web client owns those
labels); stage and priority keep tel-008's server labels. Free text is an excerpt (TM2)."""

from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Integer, String, Uuid, case, cast, func, literal, null, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.lead_stages import label as stage_label
from app.models import (
    Appointment,
    AppointmentEvent,
    AuditLog,
    Batch,
    Enquiry,
    Enrollment,
    LeadCall,
    LeadEnquiry,
    LeadFollowUp,
    LeadMessage,
    LeadStageHistory,
    OverseasApplication,
    University,
    User,
    VisaCase,
)
from app.services.telecaller_leads import PRIORITY_CHANGE, PRIORITY_LABEL

EXCERPT = 200
# D4: one transaction's rows share `at`; the rank puts them in causal order (newest first shows a stage move above its cause).
RANK = {"created": 0, "enquiry": 1, "assignment": 2, "handover": 2, "student_link": 2, "stage": 4}
OTHER_RANK = 3
SERVER_LABELLED = ("stage", "priority")


def _excerpt(column):
    return func.left(cast(column, String), EXCERPT)


def _branch(row_id, kind: str, at, *, seq=None, actor=None, from_value=None, from_name=None, to_value=None, to_name=None, reason=None,
            event=None, subject=None, status=None, duration=None, scheduled_for=None):
    """One source as the shared column list. A missing value is a typed NULL (or "" for from/to, which the contract keeps as strings)."""
    def text(value):
        return cast(null(), String) if value is None else (literal(value, String) if isinstance(value, str) else cast(value, String))

    return select(
        row_id.label("id"), literal(kind, String).label("kind"), literal(RANK.get(kind, OTHER_RANK), Integer).label("rank"), at.label("at"),
        (literal(0, BigInteger) if seq is None else seq).label("seq"), (cast(null(), Uuid) if actor is None else actor).label("actor_id"),
        func.coalesce(text(from_value), "").label("from_value"), text(from_name).label("from_name"),
        func.coalesce(text(to_value), "").label("to_value"), text(to_name).label("to_name"), text(reason).label("reason"),
        text(event).label("event"), text(subject).label("subject"), text(status).label("status"),
        (cast(null(), Integer) if duration is None else duration).label("duration_seconds"),
        (cast(null(), DateTime(timezone=True)) if scheduled_for is None else scheduled_for).label("scheduled_for"),
    )


def _audits(lead_id: UUID, *actions: str):
    return (AuditLog.entity_type == "enquiry", AuditLog.entity_id == str(lead_id), AuditLog.action.in_(actions))


def _sources(lead_id: UUID) -> list:
    From, To = aliased(User), aliased(User)
    meta = AuditLog.metadata_json
    created_by = select(AuditLog.user_id).where(*_audits(lead_id, "lead.create")).order_by(AuditLog.created_at).limit(1).scalar_subquery()
    cancelled_by = (select(AuditLog.user_id).where(AuditLog.entity_type == "lead_follow_up", AuditLog.entity_id == cast(LeadFollowUp.id, String),
                                                   AuditLog.action == "lead_follow_up.cancel").limit(1).scalar_subquery())
    student = select(Enquiry.converted_user_id).where(Enquiry.id == lead_id).scalar_subquery()
    fu = LeadFollowUp
    return [
        _branch(Enquiry.id, "created", Enquiry.created_at, actor=func.coalesce(created_by, Enquiry.bdm_user_id), from_value=Enquiry.source,
                to_value=Enquiry.subject).where(Enquiry.id == lead_id),
        _branch(LeadEnquiry.id, "enquiry", LeadEnquiry.created_at, actor=LeadEnquiry.created_by_user_id, from_value=LeadEnquiry.source,
                to_value=LeadEnquiry.subject, reason=_excerpt(LeadEnquiry.message)).where(LeadEnquiry.lead_id == lead_id),
        _branch(LeadStageHistory.id, "stage", LeadStageHistory.created_at, seq=LeadStageHistory.position, actor=LeadStageHistory.actor_user_id,
                from_value=LeadStageHistory.from_stage, to_value=LeadStageHistory.to_stage, reason=LeadStageHistory.reason,
                event=LeadStageHistory.event).where(LeadStageHistory.lead_id == lead_id),
        _branch(AuditLog.id, "priority", AuditLog.created_at, actor=AuditLog.user_id, from_value=meta["from"].as_string(),
                to_value=meta["to"].as_string()).where(*_audits(lead_id, PRIORITY_CHANGE)),
        _branch(AuditLog.id, "assignment", AuditLog.created_at, actor=AuditLog.user_id, from_value=meta["from"].as_string(), from_name=From.full_name,
                to_value=meta["to"].as_string(), to_name=To.full_name, event=meta["method"].as_string())
        .outerjoin(From, From.id == cast(meta["from"].as_string(), Uuid)).outerjoin(To, To.id == cast(meta["to"].as_string(), Uuid))
        .where(*_audits(lead_id, "lead.assign")),
        _branch(AuditLog.id, "handover", AuditLog.created_at, actor=AuditLog.user_id, from_value=meta["from_counselor_id"].as_string(),
                from_name=From.full_name, to_value=meta["counselor_id"].as_string(), to_name=To.full_name)
        .outerjoin(From, From.id == cast(meta["from_counselor_id"].as_string(), Uuid)).outerjoin(To, To.id == cast(meta["counselor_id"].as_string(), Uuid))
        .where(*_audits(lead_id, "lead.handover")),
        _branch(AuditLog.id, "student_link", AuditLog.created_at, actor=AuditLog.user_id, to_value=meta["converted_user_id"].as_string(),
                to_name=To.full_name, event=case((AuditLog.action == "lead.convert", "linked"), else_="unlinked"))
        .outerjoin(To, To.id == cast(meta["converted_user_id"].as_string(), Uuid)).where(*_audits(lead_id, "lead.convert", "lead.unconvert")),
        _branch(LeadCall.id, "call", LeadCall.occurred_at, actor=LeadCall.caller_user_id, from_value=LeadCall.call_type, to_value=LeadCall.outcome,
                reason=_excerpt(LeadCall.remarks), duration=LeadCall.duration_seconds).where(LeadCall.lead_id == lead_id),
        _branch(LeadMessage.id, "message", LeadMessage.sent_at, actor=LeadMessage.sender_user_id, from_value=LeadMessage.channel,
                to_value=LeadMessage.template_name, subject=LeadMessage.subject, status=LeadMessage.delivery_status,
                reason=_excerpt(LeadMessage.body)).where(LeadMessage.lead_id == lead_id),
        _branch(fu.id, "follow_up", fu.created_at, actor=fu.created_by_user_id, from_value=fu.reason, event="scheduled", reason=_excerpt(fu.notes),
                scheduled_for=fu.due_at).where(fu.lead_id == lead_id),
        _branch(fu.id, "follow_up", fu.completed_at, actor=fu.completed_by_user_id, from_value=fu.reason, event="done", scheduled_for=fu.due_at)
        .where(fu.lead_id == lead_id, fu.completed_at.is_not(None)),
        # a closing stage move or a handover cancels without an audit row: no actor ("System"), the reason says why
        _branch(fu.id, "follow_up", fu.cancelled_at, actor=cancelled_by, from_value=fu.reason, event="cancelled", reason=_excerpt(fu.cancel_reason),
                scheduled_for=fu.due_at).where(fu.lead_id == lead_id, fu.cancelled_at.is_not(None)),
        _branch(AppointmentEvent.id, "appointment", AppointmentEvent.created_at, seq=AppointmentEvent.position, actor=AppointmentEvent.actor_user_id,
                from_value=AppointmentEvent.from_status, to_value=AppointmentEvent.to_status, event=Appointment.appointment_type,
                subject=Appointment.appointment_code, reason=_excerpt(AppointmentEvent.reason),
                scheduled_for=func.coalesce(AppointmentEvent.new_scheduled_at, Appointment.scheduled_at))
        .join(Appointment, Appointment.id == AppointmentEvent.appointment_id).where(Appointment.lead_id == lead_id),
        # TM3: the linked student's records, read live (an unlink removes them)
        _branch(Enrollment.id, "milestone", Enrollment.created_at, to_value=Batch.name, event="enrollment", subject=Enrollment.enrollment_code,
                status=Enrollment.status).join(Batch, Batch.id == Enrollment.batch_id).where(Enrollment.student_id == student),
        _branch(OverseasApplication.id, "milestone", OverseasApplication.created_at, to_value=University.name, event="application",
                subject=OverseasApplication.application_reference, status=OverseasApplication.status)
        .join(University, University.id == OverseasApplication.university_id).where(OverseasApplication.student_id == student),
        _branch(VisaCase.id, "milestone", VisaCase.created_at, to_value=University.name, event="visa", subject=VisaCase.tracking_reference,
                status=VisaCase.status).join(OverseasApplication, OverseasApplication.id == VisaCase.application_id)
        .join(University, University.id == OverseasApplication.university_id).where(OverseasApplication.student_id == student),
    ]


def _labels(kind: str, value: str, name: str | None) -> str:
    if kind == "stage":
        return stage_label(value)
    if kind == "priority":
        return PRIORITY_LABEL.get(value, value)
    return value if name is None else name


async def page(db: AsyncSession, lead_id: UUID, limit: int, offset: int) -> dict:
    """Newest first; D4 makes the order total, so paging never repeats or skips a row (AC3)."""
    events = union_all(*_sources(lead_id)).subquery()
    total = await db.scalar(select(func.count()).select_from(events))
    stmt = (select(events, User.full_name).outerjoin(User, User.id == events.c.actor_id)
            .order_by(events.c.at.desc(), events.c.rank.desc(), events.c.seq.desc(), events.c.id.desc()).limit(limit).offset(offset))
    items = [
        {
            "id": r.id, "kind": r.kind, "at": r.at, "actor": {"id": r.actor_id, "full_name": r.full_name} if r.actor_id else None,
            "from_value": r.from_value, "from_label": _labels(r.kind, r.from_value, r.from_name),
            "to_value": r.to_value, "to_label": _labels(r.kind, r.to_value, r.to_name), "reason": r.reason, "event": r.event,
            "subject": r.subject, "status": r.status, "duration_seconds": r.duration_seconds, "scheduled_for": r.scheduled_for,
        }
        for r in (await db.execute(stmt)).all()
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}
