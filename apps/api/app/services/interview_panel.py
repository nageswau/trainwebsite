"""hrc-029 (DEC-SCOPE-405, spec docs/superpowers/specs/2026-11-05-hrc-029-interviewer-access-feedback-design.md): the interview panel.

Recruiter side (V2-V4, V10): who can be assigned, replacing the panel, the assignment notice. Interviewer side (V5-V7): the caller's own
assigned interviews, the resume version shared with them and their own feedback. An interviewer reads only interviews they are assigned
to (anything else is the same 404 as a missing id), an employer user only while they belong to the requirement's company, and no other
role reads here (403). Panel feedback is advisory (V8): it never moves the interview or the application. Functions only; nothing here
commits -- the route owns the transaction. Logs and audit carry ids and field names, never notes, names or the resume."""

from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    Candidate,
    CandidateResume,
    Company,
    EmployerProfile,
    Interview,
    InterviewInterviewer,
    InterviewPanelFeedback,
    Job,
    JobApplication,
    Notification,
    User,
)
from app.notifications.dispatch import queue_deliveries
from app.services import applications, share_gate
from app.services import interviews as svc
from app.services.profile_sharing import skill_names

ROLES = {"interviewer": "internal", "employer": "employer"}  # the role -> the assignment kind it reads
FEEDBACK_FIELDS = ("attendance", "score", "recommendation", "notes")
RESUME_WINDOW = timedelta(days=7)  # V5: after the interview's end
OVERDUE_AFTER = timedelta(hours=24)  # V10
DASHBOARDS = {"internal": "/it/interviewer/dashboard", "employer": "/it/employer/dashboard"}

ROLE_REQUIRED = "Interviewer access required"
CLOSED = "This interview is closed: its panel can no longer change"
NOT_ELIGIBLE = "Choose active interviewers or users of this requirement's company"
HAS_FEEDBACK = "An interviewer who has submitted feedback cannot be removed"
NOT_STARTED = "You can submit feedback once the interview time has passed"
NO_RESUME = "Resume not available"


def _end(interview: Interview) -> datetime:
    return interview.ends_at or interview.scheduled_at + svc.DEFAULT_LENGTH


# --- recruiter side -------------------------------------------------------------------------------------------------------------------
async def load_for_options(db: AsyncSession, user: User, interview_id: UUID) -> Job:
    """In scope (404) -> the writer (403); a read, so no lock."""
    application_id = await db.scalar(select(Interview.application_id).where(Interview.id == interview_id))
    if application_id is None:
        raise HTTPException(404, svc.NOT_FOUND)
    _application, job = await svc._scoped(db, user, application_id)
    applications.require_writer(user, interview_id, "interview_panel_options")
    return job


async def options(db: AsyncSession, job: Job) -> list[dict]:
    """V2: every active internal interviewer, then the active employer users of the requirement's company -- by name."""
    rows = await db.execute(
        select(User, EmployerProfile.company_id)
        .outerjoin(EmployerProfile, EmployerProfile.user_id == User.id)
        .where(User.active.is_(True), or_(User.role == "interviewer", and_(User.role == "employer", EmployerProfile.company_id == job.company_id)))
        .order_by(User.role.desc(), func.lower(User.full_name), User.id)
    )
    return [{"id": u.id, "full_name": u.full_name, "email": u.email, "kind": ROLES[u.role], "kind_label": svc.KIND_LABELS[ROLES[u.role]]} for u, _ in rows]


async def _current_resume(db: AsyncSession, candidate_id: UUID) -> UUID | None:
    return await db.scalar(select(CandidateResume.id).where(CandidateResume.candidate_id == candidate_id).order_by(CandidateResume.version.desc()).limit(1))


async def assign(db: AsyncSession, user: User, interview: Interview, application: JobApplication, job: Job, members: list) -> list[UUID]:
    """V3: the caller holds `load_for_write`'s locks. Replaces the panel; returns the newly added user ids (the route notifies them)."""
    if interview.status in svc.CLOSED:
        raise HTTPException(409, CLOSED)
    eligible = {o["id"]: o["kind"] for o in await options(db, job)}
    if any(m.user_id not in eligible for m in members):
        raise svc.field_error("interviewers", NOT_ELIGIBLE)
    current = {r.user_id: r for r in await db.scalars(select(InterviewInterviewer).where(InterviewInterviewer.interview_id == interview.id))}
    wanted = {m.user_id: m.is_lead for m in members}
    removed = [uid for uid in current if uid not in wanted]
    if removed and await db.scalar(
        select(func.count()).select_from(InterviewPanelFeedback).where(InterviewPanelFeedback.interview_id == interview.id, InterviewPanelFeedback.interviewer_user_id.in_(removed))
    ):
        raise HTTPException(409, HAS_FEEDBACK)
    lead_before = next((uid for uid, r in current.items() if r.is_lead), None)
    if removed:
        await db.execute(delete(InterviewInterviewer).where(InterviewInterviewer.interview_id == interview.id, InterviewInterviewer.user_id.in_(removed)))
    # the lead index is unique per interview: clear it before setting the new lead
    await db.execute(update(InterviewInterviewer).where(InterviewInterviewer.interview_id == interview.id).values(is_lead=False))
    added = [uid for uid in wanted if uid not in current]
    resume_id = await _current_resume(db, application.candidate_id) if added else None
    db.add_all(InterviewInterviewer(interview_id=interview.id, user_id=uid, kind=eligible[uid], resume_id=resume_id, assigned_by_user_id=user.id) for uid in added)
    await db.flush()
    lead = next((uid for uid, is_lead in wanted.items() if is_lead), None)
    if lead is not None:
        await db.execute(update(InterviewInterviewer).where(InterviewInterviewer.interview_id == interview.id, InterviewInterviewer.user_id == lead).values(is_lead=True))
    if added or removed or lead != lead_before:
        svc.audit(db, user, "interviewers", interview, {"added": [str(u) for u in added], "removed": [str(u) for u in removed], "lead": str(lead) if lead else None})
    await _notify(db, interview, application, job, added, eligible)
    return added


async def _notify(db: AsyncSession, interview: Interview, application: JobApplication, job: Job, user_ids: list[UUID], kinds: dict) -> None:
    """V10: an in-app notice (and the person's allowed channels) to each newly assigned interviewer -- the candidate's name and code only."""
    if not user_ids:
        return
    candidate = await db.get(Candidate, application.candidate_id)
    company = await db.get(Company, job.company_id)
    when = interview.scheduled_at.astimezone(svc.IST).strftime("%d %b %Y, %H:%M IST")
    body = "\n".join([f"Candidate: {candidate.name} ({candidate.candidate_code})", f"Requirement: {job.title}", f"Company: {company.name}",
                      f"Round: {svc.round_text(interview)}", f"Date and time: {when}"])  # fmt: skip
    for uid in user_ids:
        person = await db.get(User, uid)
        item = Notification(user_id=uid, title="Interview assigned", body=body, read=False, action_url=DASHBOARDS[kinds[uid]],
                            event_type="it.interview.assigned", entity_type="interview", entity_id=str(interview.id))  # fmt: skip
        db.add(item)
        await queue_deliveries(db, item, person)


# --- interviewer side -----------------------------------------------------------------------------------------------------------------
def require_role(user: User) -> str:
    kind = ROLES.get(user.role)
    if kind is None:
        raise HTTPException(403, ROLE_REQUIRED)
    return kind


def _mine(user: User, kind: str) -> list:
    """The caller's own assignments; an employer's only while they belong to the requirement's company (V6)."""
    where = [InterviewInterviewer.user_id == user.id, InterviewInterviewer.kind == kind]
    if kind == "employer":
        where.append(Job.company_id == select(EmployerProfile.company_id).where(EmployerProfile.user_id == user.id).scalar_subquery())
    return where


def _rows():
    return (
        select(Interview, InterviewInterviewer, Candidate, Job, Company, InterviewPanelFeedback)
        .join(InterviewInterviewer, InterviewInterviewer.interview_id == Interview.id)
        .join(JobApplication, JobApplication.id == Interview.application_id)
        .join(Candidate, Candidate.id == JobApplication.candidate_id)
        .join(Job, Job.id == JobApplication.job_id)
        .join(Company, Company.id == Job.company_id)
        .outerjoin(InterviewPanelFeedback, and_(InterviewPanelFeedback.interview_id == Interview.id, InterviewPanelFeedback.interviewer_user_id == InterviewInterviewer.user_id))
    )


def can_feedback(interview: Interview, now: datetime) -> bool:
    return interview.status not in svc.CLOSED and interview.scheduled_at <= now


async def _shareable(db: AsyncSession, rows) -> set[UUID]:
    """pob-030 G4/G7: the candidates an employer panel member may still receive the resume of (internal members are staff)."""
    return await share_gate.deliverable_ids(db, [row[2] for row in rows if row[1].kind == "employer"])


def _resume_open(interview: Interview, assignment: InterviewInterviewer, candidate: Candidate, now: datetime, shareable: set[UUID]) -> bool:
    return (assignment.resume_id is not None and interview.status != "cancelled" and candidate.archived_at is None and now <= _end(interview) + RESUME_WINDOW
            and (assignment.kind != "employer" or candidate.id in shareable))  # fmt: skip


def _out(now: datetime, skills: dict, shareable: set[UUID], i: Interview, a: InterviewInterviewer, c: Candidate, job: Job, company: Company, f: InterviewPanelFeedback | None) -> dict:
    """V6: what the panel member needs to interview -- no contact detail, salary, other members' or the recruiter's feedback."""
    status = svc.unreleased_status(i.status)
    cancelled = i.status == "cancelled"
    open_feedback = can_feedback(i, now)
    return {
        "id": i.id, "code": i.interview_code, "round_label": svc.round_label(i.round), "round_number": i.round_number, "scheduled_at": i.scheduled_at,
        "ends_at": i.ends_at, "mode": i.mode, "platform_label": svc.PLATFORM_LABELS.get(i.platform) if i.platform else None,
        "meeting_url": None if cancelled else i.meeting_url, "location": i.location, "phone_details": i.phone_details, "instructions": i.instructions,
        "status": status, "status_label": svc.STATUS_LABELS[status], "cancel_reason": i.cancel_reason, "is_lead": a.is_lead,
        "candidate": {"code": c.candidate_code, "name": c.name, "location": c.location, "qualification": c.qualification,
                      "experience_months": c.experience_months, "current_company": c.current_company, "skills": skills.get(c.id, [])},
        "requirement": {"code": job.requirement_code, "title": job.title}, "company": {"name": company.name},
        "has_resume": _resume_open(i, a, c, now, shareable), "feedback": svc.panel_feedback_out(f), "can_feedback": open_feedback,
        "feedback_overdue": open_feedback and f is None and _end(i) + OVERDUE_AFTER < now,
    }  # fmt: skip


async def _items(db: AsyncSession, now: datetime, rows) -> list[dict]:
    skills = await skill_names(db, list({row[2].id for row in rows})) if rows else {}
    shareable = await _shareable(db, rows)
    return [_out(now, skills, shareable, *row) for row in rows]


def views(now: datetime) -> dict:
    return {"upcoming": (Interview.scheduled_at > now, (Interview.scheduled_at, Interview.id)), "past": (Interview.scheduled_at <= now, (Interview.scheduled_at.desc(), Interview.id))}


async def list_page(db: AsyncSession, user: User, view: str, now: datetime, limit: int, offset: int) -> dict:
    kind = require_role(user)
    mine = _mine(user, kind)
    conditions = views(now)
    where, order = conditions[view]
    base = (
        select(func.count()).select_from(Interview).join(InterviewInterviewer, InterviewInterviewer.interview_id == Interview.id)
        .join(JobApplication, JobApplication.id == Interview.application_id).join(Job, Job.id == JobApplication.job_id).where(*mine)
    )  # fmt: skip
    total = await db.scalar(base.where(where))
    rows = (await db.execute(_rows().where(*mine, where).order_by(*order).limit(limit).offset(offset))).all()
    counts = (await db.execute(base.with_only_columns(*(func.count().filter(c) for c, _ in conditions.values())))).one()
    return {"items": await _items(db, now, rows), "total": total or 0, "limit": limit, "offset": offset, "counts": dict(zip(conditions, counts, strict=True))}


async def _row(db: AsyncSession, user: User, interview_id: UUID):
    kind = require_role(user)
    row = (await db.execute(_rows().where(Interview.id == interview_id, *_mine(user, kind)).execution_options(populate_existing=True))).first()
    if row is None:
        raise HTTPException(404, svc.NOT_FOUND)
    return row


async def one(db: AsyncSession, user: User, interview_id: UUID, now: datetime) -> dict:
    return (await _items(db, now, [await _row(db, user, interview_id)]))[0]


async def resume(db: AsyncSession, user: User, interview_id: UUID, now: datetime) -> tuple[CandidateResume, Candidate]:
    """V4/V5: the version shared with this member, inside the window; audited before any byte leaves (the route commits)."""
    row = await _row(db, user, interview_id)
    interview, assignment, candidate, *_ = row
    if not _resume_open(interview, assignment, candidate, now, await _shareable(db, [row])):
        raise HTTPException(404, NO_RESUME)
    item = await db.get(CandidateResume, assignment.resume_id)
    db.add(AuditLog(user_id=user.id, action="interviewer.resume_download", entity_type="interview", entity_id=str(interview.id),
                    metadata_json={"candidate_id": str(candidate.id), "resume_id": str(item.id), "version": item.version}))  # fmt: skip
    return item, candidate


async def save_feedback(db: AsyncSession, user: User, interview_id: UUID, sent: dict, now: datetime) -> list[str]:
    """V7: the caller's own row, created or replaced under the interview's lock (two first saves cannot both insert). Returns the changed
    field names."""
    await _row(db, user, interview_id)
    interview = await db.scalar(select(Interview).where(Interview.id == interview_id).with_for_update().execution_options(populate_existing=True))
    if interview.status == "cancelled":
        raise HTTPException(409, svc.CANCELLED)
    if interview.status in svc.FINAL:
        raise HTTPException(409, svc.DECIDED)
    if interview.scheduled_at > now:
        raise HTTPException(409, NOT_STARTED)
    key = {"interview_id": interview_id, "interviewer_user_id": user.id}
    row = await db.scalar(select(InterviewPanelFeedback).filter_by(**key).execution_options(populate_existing=True))
    changed = [f for f in FEEDBACK_FIELDS if row is None or getattr(row, f) != sent[f]]
    if not changed:
        return []
    if row is None:
        row = InterviewPanelFeedback(**key)
        db.add(row)
    for field in FEEDBACK_FIELDS:
        setattr(row, field, sent[field])
    db.add(AuditLog(user_id=user.id, action="interviewer.feedback", entity_type="interview", entity_id=str(interview_id), metadata_json={"fields": changed}))
    await db.flush()
    return changed
