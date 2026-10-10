"""upc-013 (DEC-SCOPE-163, spec §3): a university's communication history (§12) -- one `UNION ALL` over the tables that already record
each event (D2: nothing is copied; tel-015's branch builder and order). The route has checked the reader and the university (D1); this
module only sees its id and the reader, for upc-026's document visibility (TL7). Read only; nothing is logged (TL8).

Keys, not labels, for meetings, visits, agreements, documents and tasks (the web client owns those labels); stage and call-outcome labels
come from their server catalogues, people and contacts by name. Free text is a 200-character excerpt (TL6)."""

from uuid import UUID

from sqlalchemy import String, case, cast, func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    AuditLog,
    PartnershipTask,
    UniversityAgreement,
    UniversityAgreementEvent,
    UniversityCall,
    UniversityContact,
    UniversityDocument,
    UniversityDocumentVersion,
    UniversityMeeting,
    UniversityMeetingEvent,
    UniversityMessage,
    UniversityStageHistory,
    UniversityVisit,
    UniversityVisitEvent,
    User,
)
from app.partnership_stages import label_of
from app.services.lead_timeline import _branch, _excerpt
from app.services.recruiter_calls import OUTCOMES
from app.services.university_documents import visibility

# TL5: one transaction's rows share `at`; newest first shows the effect above its cause -- a signed agreement / completed meeting moves the
# stage (stage above it), and a stage move or visit creates its Q-22 auto-task (task above that).
ACTIVITY, STAGE, TASK = 1, 2, 3


def _task_actor(action: str):
    """Who completed or cancelled a task: its audit row (partnership_tasks keeps no completer)."""
    return (
        select(AuditLog.user_id)
        .where(AuditLog.entity_type == "partnership_task", AuditLog.entity_id == cast(PartnershipTask.id, String), AuditLog.action == f"partnership_task.{action}")
        .limit(1)
        .scalar_subquery()
    )


def _sources(university_id: UUID, user: User) -> list:
    S, C, M, T = UniversityStageHistory, UniversityCall, UniversityMessage, PartnershipTask
    ME, MT, VE, V = UniversityMeetingEvent, UniversityMeeting, UniversityVisitEvent, UniversityVisit
    AE, A, DV, D = UniversityAgreementEvent, UniversityAgreement, UniversityDocumentVersion, UniversityDocument
    Contact, Assignee = UniversityContact, aliased(User)
    task = dict(from_value=T.kind, subject=T.title, status=T.source, rank=TASK)
    return [
        _branch(S.id, "stage", S.created_at, seq=S.position, actor=S.actor_user_id, event=S.kind, from_value=S.from_stage, to_value=S.to_stage, reason=S.note, rank=STAGE).where(
            S.university_id == university_id
        ),
        _branch(
            C.id, "call", C.occurred_at, actor=C.caller_user_id, event=C.direction, from_value=C.outcome, to_name=Contact.name, reason=_excerpt(C.notes), duration=C.duration_seconds, rank=ACTIVITY
        )
        .outerjoin(Contact, Contact.id == C.contact_id)
        .where(C.university_id == university_id),
        _branch(
            M.id,
            "message",
            M.sent_at,
            actor=M.sender_user_id,
            event=M.channel,
            from_value=M.template_name,
            to_name=Contact.name,
            subject=M.subject,
            status=M.delivery_status,
            reason=_excerpt(M.body),
            rank=ACTIVITY,
        )
        .outerjoin(Contact, Contact.id == M.contact_id)
        .where(M.university_id == university_id),
        _branch(
            ME.id,
            "meeting",
            ME.created_at,
            seq=ME.position,
            actor=ME.actor_user_id,
            event=ME.event,
            from_value=MT.meeting_type,
            subject=MT.code,
            reason=_excerpt(ME.reason),
            scheduled_for=func.coalesce(ME.new_starts_at, MT.starts_at),
            rank=ACTIVITY,
        )
        .join(MT, MT.id == ME.meeting_id)
        .where(MT.university_id == university_id),
        _branch(VE.id, "visit", VE.created_at, actor=VE.actor_user_id, event=VE.action, from_value=VE.from_status, to_value=VE.to_status, subject=V.code, reason=_excerpt(VE.reason), rank=ACTIVITY)
        .join(V, V.id == VE.visit_id)
        .where(V.university_id == university_id),
        _branch(
            AE.id,
            "agreement",
            AE.created_at,
            seq=AE.position,
            actor=AE.actor_user_id,
            event=AE.kind,
            from_value=AE.from_status,
            to_value=AE.to_status,
            subject=A.mou_number,
            status=A.agreement_type,
            reason=_excerpt(AE.note),
            rank=ACTIVITY,
        )
        .join(A, A.id == AE.agreement_id)
        .where(A.university_id == university_id),
        _branch(T.id, "task", T.created_at, actor=T.created_by_user_id, event="scheduled", to_value=T.due_on, to_name=Assignee.full_name, reason=_excerpt(T.notes), **task)
        .join(Assignee, Assignee.id == T.assignee_user_id)
        .where(T.university_id == university_id),
        _branch(T.id, "task", T.completed_at, actor=_task_actor("complete"), event="done", **task).where(T.university_id == university_id, T.completed_at.is_not(None)),
        _branch(T.id, "task", T.cancelled_at, actor=_task_actor("cancel"), event="cancelled", reason=_excerpt(T.cancel_reason), **task).where(
            T.university_id == university_id, T.cancelled_at.is_not(None)
        ),
        _branch(
            DV.id,
            "document",
            DV.uploaded_at,
            actor=DV.uploaded_by_user_id,
            event=case((DV.version == 1, "uploaded"), else_="new_version"),
            from_value=D.kind,
            to_value=DV.version,
            subject=D.title,
            rank=ACTIVITY,
        )
        .join(D, D.id == DV.document_id)
        .where(D.university_id == university_id, *visibility(user)),
    ]


def _from_label(kind: str, value: str) -> str:
    if kind == "stage":
        return label_of(value)
    return OUTCOMES.get(value, value) if kind == "call" else value


async def page(db: AsyncSession, university_id: UUID, user: User, limit: int, offset: int) -> dict:
    """Newest first; TL5 makes the order total, so paging never repeats or skips a row. Two queries, whatever the data."""
    events = union_all(*_sources(university_id, user)).subquery()
    total = await db.scalar(select(func.count()).select_from(events))
    stmt = (
        select(events, User.full_name)
        .outerjoin(User, User.id == events.c.actor_id)
        .order_by(events.c.at.desc(), events.c.rank.desc(), events.c.seq.desc(), events.c.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [
        {
            "id": r.id,
            "kind": r.kind,
            "at": r.at,
            "actor": {"id": r.actor_id, "full_name": r.full_name} if r.actor_id else None,
            "event": r.event,
            "from_value": r.from_value,
            "from_label": _from_label(r.kind, r.from_value),
            "to_value": r.to_value,
            "to_label": label_of(r.to_value) if r.kind == "stage" else (r.to_name or ""),
            "subject": r.subject,
            "status": r.status,
            "reason": r.reason,
            "duration_seconds": r.duration_seconds,
            "scheduled_for": r.scheduled_for,
        }
        for r in (await db.execute(stmt)).all()
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}
