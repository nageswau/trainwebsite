"""rec-027 (spec §1-§2, TL1-TL10): a company's and a candidate's timeline -- one `UNION ALL` over the tables that already record each event
(nothing is copied; tel-015's branch builder, upc-013's order). The route has checked the reader and the party (TL3); this module only
sees its id. Read only; nothing is logged (TL9).

TL4: every branch names its columns -- candidates by name and code, never their mobile or email; no document or letter key, share token,
fee or changed-field list. Status-like keys get their server labels; meeting types, follow-up reasons and share channels / responses are
keys the web client labels. Free text is a 200-character excerpt."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import String, case, cast, func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app import recruiter_stages
from app.models import (
    AuditLog,
    Candidate,
    Company,
    CompanyContact,
    CompanyStageHistory,
    Interview,
    InterviewEvent,
    Job,
    JobApplication,
    JobApplicationStatusHistory,
    JobOffer,
    JobOfferEvent,
    JobStatusHistory,
    ProfileShare,
    ProfileShareItem,
    RecruiterCall,
    RecruiterContract,
    RecruiterContractEvent,
    RecruiterFollowUp,
    RecruiterMeeting,
    RecruiterMeetingEvent,
    RecruiterMessage,
    User,
)
from app.services import applications, interviews, offers, recruiter_contracts
from app.services.lead_timeline import _branch, _excerpt
from app.services.recruiter_calls import OUTCOMES
from app.services.recruiter_requirements import STATUS_LABELS as REQUIREMENT_LABELS

# TL5: one transaction's rows share `at`; newest first shows the effect above its cause -- a call or meeting outcome creates its follow-up,
# a share / interview / offer moves the application, and any of them can move the company's stage.
ACTIVITY, EFFECT, STAGE = 1, 2, 3
# TL8: the server catalogues of each status-like kind (and the call outcomes); a key no longer in its catalogue is shown as stored.
LABELS: dict[str, dict[str, str]] = {
    "stage": recruiter_stages.LABELS,
    "requirement": REQUIREMENT_LABELS,
    "application": applications.LABELS,
    "interview": interviews.STATUS_LABELS,
    "offer": offers.STATUS_LABELS,
    "contract": recruiter_contracts.LABELS,
    "call": OUTCOMES,
}
STATUS_KINDS = ("stage", "requirement", "application", "interview", "offer", "contract")  # `to_label` is a status, not a person or contact


def _call_at(C):
    """QA15-01: the call form sends its time to the minute, so a call logged now would read seconds before what was recorded earlier in that
    minute; within the minute it is placed when it was recorded. A call dated earlier keeps its own time."""
    return case((C.created_at < C.occurred_at + timedelta(minutes=1), C.created_at), else_=C.occurred_at)


def _requirement(J):
    return J.requirement_code + " — " + J.title


def _company_sources(company_id: UUID) -> list:
    S, C, M, F, ME, MT = CompanyStageHistory, RecruiterCall, RecruiterMessage, RecruiterFollowUp, RecruiterMeetingEvent, RecruiterMeeting
    JH, J, PS, PI, CE, CT = JobStatusHistory, Job, ProfileShare, ProfileShareItem, RecruiterContractEvent, RecruiterContract
    cancelled_by = (
        select(AuditLog.user_id)
        .where(AuditLog.entity_type == "recruiter_follow_up", AuditLog.entity_id == cast(F.id, String), AuditLog.action == "recruiter_follow_up.cancel")
        .limit(1)
        .scalar_subquery()
    )
    follow_up = dict(from_value=F.reason, rank=EFFECT)
    items = select(func.count()).where(PI.share_id == PS.id).scalar_subquery()
    return [
        _branch(S.id, "stage", S.created_at, seq=S.position, actor=S.actor_user_id, event=S.event, from_value=S.from_stage, to_value=S.to_stage, reason=S.reason, rank=STAGE).where(
            S.company_id == company_id
        ),
        _branch(
            C.id,
            "call",
            _call_at(C),
            actor=C.caller_user_id,
            event=C.direction,
            from_value=C.outcome,
            to_name=CompanyContact.name,
            reason=_excerpt(C.notes),
            duration=C.duration_seconds,
            rank=ACTIVITY,
        )
        .outerjoin(CompanyContact, CompanyContact.id == C.contact_id)
        .where(C.company_id == company_id),
        _branch(
            M.id,
            "message",
            M.sent_at,
            actor=M.sender_user_id,
            event=M.channel,
            from_value=M.template_name,
            to_name=CompanyContact.name,
            subject=M.subject,
            status=M.delivery_status,
            reason=_excerpt(M.body),
            rank=ACTIVITY,
        )
        .outerjoin(CompanyContact, CompanyContact.id == M.contact_id)
        .where(M.company_id == company_id),
        _branch(
            ME.id,
            "meeting",
            ME.created_at,
            seq=ME.position,
            actor=ME.actor_user_id,
            event=ME.event,
            from_value=MT.meeting_type,
            subject=MT.meeting_code,
            reason=_excerpt(ME.reason),
            scheduled_for=func.coalesce(ME.new_starts_at, MT.starts_at),
            rank=ACTIVITY,
        )
        .join(MT, MT.id == ME.meeting_id)
        .where(MT.company_id == company_id),
        _branch(F.id, "follow_up", F.created_at, actor=F.created_by_user_id, event="scheduled", reason=_excerpt(F.notes), scheduled_for=F.due_at, **follow_up).where(F.company_id == company_id),
        _branch(F.id, "follow_up", F.completed_at, actor=F.completed_by_user_id, event="done", reason=_excerpt(F.outcome), **follow_up).where(F.company_id == company_id, F.completed_at.is_not(None)),
        _branch(F.id, "follow_up", F.cancelled_at, actor=cancelled_by, event="cancelled", reason=_excerpt(F.cancel_reason), **follow_up).where(F.company_id == company_id, F.cancelled_at.is_not(None)),
        _branch(JH.id, "requirement", JH.created_at, actor=JH.changed_by_user_id, from_value=JH.from_status, to_value=JH.to_status, subject=_requirement(J), reason=_excerpt(JH.note), rank=ACTIVITY)
        .join(J, J.id == JH.job_id)
        .where(J.company_id == company_id),
        _branch(PS.id, "share", PS.created_at, actor=PS.shared_by_user_id, event=PS.channel, to_value=items, to_name=CompanyContact.name, subject=_requirement(J), rank=ACTIVITY)
        .join(J, J.id == PS.job_id)
        .outerjoin(CompanyContact, CompanyContact.id == PS.contact_id)
        .where(PS.company_id == company_id),
        _branch(
            PI.id, "share_response", PI.responded_at, actor=PI.responded_by_user_id, event=PI.response, to_name=Candidate.name, subject=_requirement(J), reason=_excerpt(PI.feedback), rank=ACTIVITY
        )
        .join(PS, PS.id == PI.share_id)
        .join(J, J.id == PS.job_id)
        .join(Candidate, Candidate.id == PI.candidate_id)
        .where(PS.company_id == company_id, PI.responded_at.is_not(None)),
        _branch(CE.id, "contract", CE.created_at, seq=CE.position, actor=CE.actor_user_id, event=CE.kind, from_value=CE.from_status, to_value=CE.to_status, subject=CT.agreement_type, rank=ACTIVITY)
        .join(CT, CT.id == CE.contract_id)
        .where(CT.company_id == company_id),
    ]


def _candidate_sources(candidate_id: UUID) -> list:
    C, M, AH, A, J, Co = RecruiterCall, RecruiterMessage, JobApplicationStatusHistory, JobApplication, Job, Company
    IE, Iv, OE, Of, PI, PS = InterviewEvent, Interview, JobOfferEvent, JobOffer, ProfileShareItem, ProfileShare
    on_requirement = dict(subject=_requirement(J), from_name=Co.name)
    return [
        _branch(C.id, "call", _call_at(C), actor=C.caller_user_id, event=C.direction, from_value=C.outcome, reason=_excerpt(C.notes), duration=C.duration_seconds, rank=ACTIVITY).where(
            C.candidate_id == candidate_id
        ),
        _branch(
            M.id, "message", M.sent_at, actor=M.sender_user_id, event=M.channel, from_value=M.template_name, subject=M.subject, status=M.delivery_status, reason=_excerpt(M.body), rank=ACTIVITY
        ).where(M.candidate_id == candidate_id),
        _branch(AH.id, "application", AH.created_at, actor=AH.changed_by_user_id, from_value=AH.from_status, to_value=AH.to_status, reason=_excerpt(AH.note), rank=EFFECT, **on_requirement)
        .join(A, A.id == AH.application_id)
        .join(J, J.id == A.job_id)
        .join(Co, Co.id == J.company_id)
        .where(A.candidate_id == candidate_id),
        _branch(
            IE.id,
            "interview",
            IE.created_at,
            seq=IE.position,
            actor=IE.actor_user_id,
            event=IE.event,
            from_value=IE.from_status,
            to_value=IE.to_status,
            status=Iv.round,
            reason=_excerpt(IE.note),
            scheduled_for=IE.new_scheduled_at,
            rank=ACTIVITY,
            subject=Iv.interview_code,
            from_name=Co.name,
        )
        .join(Iv, Iv.id == IE.interview_id)
        .join(A, A.id == Iv.application_id)
        .join(J, J.id == A.job_id)
        .join(Co, Co.id == J.company_id)
        .where(A.candidate_id == candidate_id),
        _branch(
            OE.id,
            "offer",
            OE.created_at,
            seq=OE.position,
            actor=OE.actor_user_id,
            event=OE.event,
            from_value=OE.from_status,
            to_value=OE.to_status,
            reason=_excerpt(OE.note),
            rank=ACTIVITY,
            **on_requirement,
        )
        .join(Of, Of.id == OE.offer_id)
        .join(A, A.id == Of.application_id)
        .join(J, J.id == A.job_id)
        .join(Co, Co.id == J.company_id)
        .where(A.candidate_id == candidate_id),
        _branch(PI.id, "share", PI.created_at, actor=PS.shared_by_user_id, event=PS.channel, rank=ACTIVITY, **on_requirement)
        .join(PS, PS.id == PI.share_id)
        .join(J, J.id == PS.job_id)
        .join(Co, Co.id == PS.company_id)
        .where(PI.candidate_id == candidate_id),
        _branch(PI.id, "share_response", PI.responded_at, actor=PI.responded_by_user_id, event=PI.response, reason=_excerpt(PI.feedback), rank=ACTIVITY, **on_requirement)
        .join(PS, PS.id == PI.share_id)
        .join(J, J.id == PS.job_id)
        .join(Co, Co.id == PS.company_id)
        .where(PI.candidate_id == candidate_id, PI.responded_at.is_not(None)),
    ]


def _label(kind: str, value: str) -> str:
    return LABELS[kind].get(value, value) if value and kind in LABELS else ""


async def _page(db: AsyncSession, sources: list, limit: int, offset: int) -> dict:
    """Newest first; TL5 makes the order total, so paging never repeats or skips a row. Two queries, whatever the data (TL7)."""
    events = union_all(*sources).subquery()
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
            "from_label": _label(r.kind, r.from_value),
            "to_value": r.to_value,
            "to_label": _label(r.kind, r.to_value) if r.kind in STATUS_KINDS else (r.to_name or ""),
            "subject": r.subject,
            "status": r.status,
            "reason": r.reason,
            "context": r.from_name,
            "duration_seconds": r.duration_seconds,
            "scheduled_for": r.scheduled_for,
        }
        for r in (await db.execute(stmt)).all()
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


async def company_page(db: AsyncSession, company_id: UUID, limit: int, offset: int) -> dict:
    return await _page(db, _company_sources(company_id), limit, offset)


async def candidate_page(db: AsyncSession, candidate_id: UUID, limit: int, offset: int) -> dict:
    return await _page(db, _candidate_sources(candidate_id), limit, offset)
