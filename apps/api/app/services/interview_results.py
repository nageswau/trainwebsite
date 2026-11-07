"""hrc-030 (DEC-SCOPE-409, spec R1-R11): interview results and their release.

A Selected / Rejected interview decision becomes a result. The application moves as it always did (offers, pipelines and reports read
it), but the candidate's own view (`candidate_status`) is held until a `results.release` holder publishes the result with a
candidate-facing message -- or at once when the global switch says auto-release. Only then do the candidate's surfaces (application stage,
"My results", interview schedule) show it and the candidate is notified, with the message only (never feedback or scores).

Functions only; nothing here commits -- the route owns the transaction. Emails queued in a write are kept on the session (`take_emails`)
for the route to publish after its commit. Logs and audit carry ids and keys, never the message."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Candidate, Company, Interview, InterviewResult, Job, JobApplication, RecruiterMessage, ResultReleaseSetting, User
from app.services import applications, interviews, mailer

NOTICE = "Interview result"
OUTCOME_LABELS = {"selected": "Selected", "rejected": "Not selected"}
STATE_LABELS = {"pending_approval": "Waiting for approval", "released": "Published"}
NOT_FOUND = "Interview result not found"
OWN_DECISION = "You cannot publish a result you decided yourself"
ALREADY_RELEASED = "This result has already been published"
NOT_RELEASED_OFFER = "Publish the interview result before making an offer"
SUPER_ADMIN_ONLY = "Only a super admin can change the result release setting"
_EMAILS = "hrc030_result_emails"


def default_message(outcome: str, is_final: bool, round_name: str, role: str, company: str) -> str:
    if outcome == "rejected":
        return f"Thank you for interviewing for {role} at {company}. We will not be moving forward with your application this time."
    if is_final:
        return f"Congratulations! You have been selected for {role} at {company}."
    return f"You have cleared the {round_name} for {role} at {company}. We will contact you about the next step."


def _message(row: InterviewResult, interview: Interview, job: Job, company: Company) -> str:
    return row.candidate_message or default_message(row.outcome, row.is_final, interviews.round_text(interview), job.title, company.name)


def out(row: InterviewResult | None, interview: Interview, job: Job, company: Company) -> dict | None:
    """R10: the result on a recruiter's interview read (the default message while it waits)."""
    if row is None:
        return None
    return {
        "id": row.id,
        "outcome": row.outcome,
        "outcome_label": OUTCOME_LABELS[row.outcome],
        "is_final": row.is_final,
        "state": row.state,
        "state_label": STATE_LABELS[row.state],
        "candidate_message": _message(row, interview, job, company),
        "release_mode": row.release_mode,
        "released_at": row.released_at,
    }


async def for_interviews(db: AsyncSession, ids: list[UUID]) -> dict[UUID, InterviewResult]:
    if not ids:
        return {}
    rows = await db.scalars(select(InterviewResult).where(InterviewResult.interview_id.in_(ids)).execution_options(populate_existing=True))
    return {r.interview_id: r for r in rows}


async def auto_release(db: AsyncSession) -> bool:
    return bool(await db.scalar(select(ResultReleaseSetting.auto_release).where(ResultReleaseSetting.id == 1)))


def take_emails(db: AsyncSession) -> list[UUID]:
    """The email ids queued by this session's releases, for the route to publish after its commit."""
    return db.info.pop(_EMAILS, [])


async def record(db: AsyncSession, user: User | None, interview: Interview, application: JobApplication, outcome: str, *, decides: bool, note: str) -> None:
    """R1/R3/R4: a decision is recorded as a result; when it `decides` the application, the application follows it (held from the
    candidate unless auto-release is on, which publishes it in the same transaction). One result per interview: a decided interview never
    moves again (IV3), and `interview_id` is unique."""
    auto = user is not None and await auto_release(db)
    if decides:
        applications.follow(db, user, application, outcome, note, visible=auto)
    row = InterviewResult(interview_id=interview.id, application_id=application.id, outcome=outcome, is_final=decides, state="pending_approval",
                          decided_by_user_id=user.id if user else None)  # fmt: skip
    db.add(row)
    await db.flush()
    if auto:
        await _publish(db, user, row, application, interview, None, "auto")


async def _publish(db: AsyncSession, user: User, row: InterviewResult, application: JobApplication, interview: Interview, message: str | None, mode: str) -> None:
    """R6: store the message (the default when blank), release, move the candidate's view, notify once, audit."""
    job = await db.get(Job, application.job_id)
    company = await db.get(Company, job.company_id)
    row.candidate_message = (message or "").strip() or default_message(row.outcome, row.is_final, interviews.round_text(interview), job.title, company.name)
    row.state, row.release_mode, row.released_by_user_id, row.released_at = "released", mode, user.id, datetime.now(UTC)
    if row.is_final and application.status == row.outcome:
        application.candidate_status = row.outcome
    if application.student_id is not None:  # a portal user (student or candidate): in-app plus their delivery channels
        await applications.notify_candidate(db, application, "it.interview.result_published", row.id)  # hrc-032 (N4): the message is in My results, not the preview
    else:
        candidate = await db.get(Candidate, application.candidate_id)
        if mailer.smtp_configured() and candidate.email:
            subject = f"{NOTICE}: {interviews.round_text(interview)} - {job.title}"[:200]
            mail = RecruiterMessage(candidate_id=candidate.id, subject=subject, body=f"Dear {candidate.name},\n\n{row.candidate_message}", **interviews._mail(user))
            db.add(mail)
            await db.flush()
            db.info.setdefault(_EMAILS, []).append(mail.id)
    db.add(AuditLog(user_id=user.id, action="interview_result.release", entity_type="interview_result", entity_id=str(row.id),
                    metadata_json={"interview_id": str(row.interview_id), "application_id": str(row.application_id), "outcome": row.outcome, "mode": mode}))  # fmt: skip
    await db.flush()


async def release(db: AsyncSession, user: User, result_id: UUID, message: str | None) -> InterviewResult:
    """R5/R6/R7: the caller holds `results.release` (the route's dependency). 404 missing, 403 own decision, 409 already released. Lock
    order: the application, then the result (as a decision writes them)."""
    application_id = await db.scalar(select(InterviewResult.application_id).where(InterviewResult.id == result_id))
    if application_id is None:
        raise HTTPException(404, NOT_FOUND)
    application = await db.scalar(select(JobApplication).where(JobApplication.id == application_id).with_for_update().execution_options(populate_existing=True))
    row = await db.scalar(select(InterviewResult).where(InterviewResult.id == result_id).with_for_update().execution_options(populate_existing=True))
    if row.decided_by_user_id == user.id:
        raise HTTPException(403, OWN_DECISION)
    if row.state == "released":
        raise HTTPException(409, ALREADY_RELEASED)
    await _publish(db, user, row, application, await db.get(Interview, row.interview_id), message, "approval")
    return row


async def require_no_unreleased_final(db: AsyncSession, application_id: UUID) -> None:
    """R8: an offer is visible to the candidate, so it waits for the application's final result to be published (409)."""
    pending = select(InterviewResult.id).where(InterviewResult.application_id == application_id, InterviewResult.is_final.is_(True),
                                               InterviewResult.state == "pending_approval")  # fmt: skip
    if await db.scalar(pending.limit(1)) is not None:
        raise HTTPException(409, NOT_RELEASED_OFFER)


# --- reads -------------------------------------------------------------------------------------------------------------------------
def _rows():
    return (
        select(InterviewResult, Interview, Candidate, Job, Company, User)
        .join(Interview, Interview.id == InterviewResult.interview_id)
        .join(JobApplication, JobApplication.id == InterviewResult.application_id)
        .join(Candidate, Candidate.id == JobApplication.candidate_id)
        .join(Job, Job.id == JobApplication.job_id)
        .join(Company, Company.id == Job.company_id)
        .outerjoin(User, User.id == InterviewResult.decided_by_user_id)
    )


def _row_out(user: User, r: InterviewResult, i: Interview, c: Candidate, job: Job, company: Company, decider: User | None) -> dict:
    return {
        **out(r, i, job, company),
        "interview": {"id": i.id, "code": i.interview_code, "round": interviews.round_text(i), "scheduled_at": i.scheduled_at},
        "candidate": {"id": c.id, "code": c.candidate_code, "name": c.name},
        "requirement": {"id": job.id, "code": job.requirement_code, "title": job.title},
        "company": {"id": company.id, "name": company.name},
        "decided_by": {"id": decider.id, "full_name": decider.full_name} if decider else None,
        "decided_at": r.created_at,
        "can_release": r.state == "pending_approval" and r.decided_by_user_id != user.id,
    }


async def queue(db: AsyncSession, user: User, state: str, limit: int, offset: int) -> dict:
    """R11: division-wide like `jobs.approve`; pending oldest first, published newest first; `counts` for both states."""
    order = (InterviewResult.created_at, InterviewResult.id) if state == "pending_approval" else (InterviewResult.released_at.desc(), InterviewResult.id)
    rows = (await db.execute(_rows().where(InterviewResult.state == state).order_by(*order).limit(limit).offset(offset))).all()
    counts = dict((await db.execute(select(InterviewResult.state, func.count()).group_by(InterviewResult.state))).all())
    items = [_row_out(user, r, i, c, job, company, decider) for r, i, c, job, company, decider in rows]
    return {"items": items, "total": counts.get(state, 0), "limit": limit, "offset": offset,
            "counts": {s: counts.get(s, 0) for s in STATE_LABELS}}  # fmt: skip


async def one(db: AsyncSession, user: User, result_id: UUID) -> dict:
    r, i, c, job, company, decider = (await db.execute(_rows().where(InterviewResult.id == result_id).execution_options(populate_existing=True))).one()
    return _row_out(user, r, i, c, job, company, decider)


async def mine(db: AsyncSession, user: User) -> list[dict]:
    """R9: the caller's own published results only, newest first."""
    rows = await db.execute(
        select(InterviewResult, Interview, Job, Company)
        .join(Interview, Interview.id == InterviewResult.interview_id)
        .join(JobApplication, JobApplication.id == InterviewResult.application_id)
        .join(Job, Job.id == JobApplication.job_id)
        .join(Company, Company.id == Job.company_id)
        .where(JobApplication.student_id == user.id, InterviewResult.state == "released")
        .order_by(InterviewResult.released_at.desc(), InterviewResult.id)
    )
    return [
        {
            "id": r.id,
            "round": interviews.round_text(i),
            "role": job.title,
            "company": company.name,
            "outcome": r.outcome,
            "outcome_label": OUTCOME_LABELS[r.outcome],
            "message": r.candidate_message,
            "released_at": r.released_at,
        }
        for r, i, job, company in rows
    ]


async def released_outcomes(db: AsyncSession, interview_ids: list[UUID]) -> dict[UUID, str]:
    """R9: the published outcome label per interview, for the student's schedule."""
    if not interview_ids:
        return {}
    rows = await db.execute(select(InterviewResult.interview_id, InterviewResult.outcome).where(InterviewResult.interview_id.in_(interview_ids), InterviewResult.state == "released"))
    return {iid: OUTCOME_LABELS[o] for iid, o in rows}


async def settings_out(db: AsyncSession, user: User) -> dict:
    return {"auto_release": await auto_release(db), "can_edit": user.role == "super_admin"}


async def save_settings(db: AsyncSession, user: User, value: bool) -> None:
    """R4: super_admin only (403); the one row, created when missing; audited with the before and after."""
    if user.role != "super_admin":
        raise HTTPException(403, SUPER_ADMIN_ONLY)
    row = await db.get(ResultReleaseSetting, 1, with_for_update=True)
    before = bool(row and row.auto_release)
    if row is None:
        row = ResultReleaseSetting(id=1)
        db.add(row)
    row.auto_release, row.updated_by_user_id = value, user.id
    db.add(AuditLog(user_id=user.id, action="interview_result.settings", entity_type="result_release_settings", entity_id="1",
                    metadata_json={"changes": {"auto_release": [before, value]}}))  # fmt: skip
