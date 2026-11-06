"""hrc-032 (DEC-SCOPE-413 N6/N7): the two recruitment triggers no request raises -- overdue interview feedback and a new matching vacancy. Each
hourly beat job takes a bounded batch, and writes its marker in the transaction of its notices: both or neither, so a rerun adds nothing.
`FOR UPDATE SKIP LOCKED` lets a second beat process pass over what the first holds. Logs carry counts only."""

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models import JOB_OPEN_STATUSES, Interview, InterviewFeedback, InterviewInterviewer, InterviewPanelFeedback, Job, JobApplication, User
from app.notifications.events import notify
from app.services import candidate_jobs, interview_panel, interviews, job_visibility, matching

logger = logging.getLogger("app.recruiter")

FEEDBACK_EVENT = "it.interview.feedback_overdue"
MATCH_EVENT = "it.job.new_match"
FEEDBACK_GRACE_HOURS = 24  # N6 (NEEDS_CONFIRMATION): no source says how soon feedback is due
AWAITING_FEEDBACK = (*interviews.OPEN, "completed")  # on hold, no show, decided and cancelled owe no feedback
SWEEP_LIMIT = 200
MATCH_JOBS_LIMIT = 20
MATCH_RECIPIENTS_LIMIT = 200
STAFF_URL = "/recruiter/interviews"
MATCH_URLS = {"it_student": "/it/student/jobs", "candidate": candidate_jobs.CANDIDATE_JOBS_URL}


async def _notify_overdue(db: AsyncSession, interview: Interview, owner: User | None, panel: list[User]) -> None:
    await notify(db, [owner], FEEDBACK_EVENT, interview.id, action_url=STAFF_URL)
    for kind, url in interview_panel.DASHBOARDS.items():
        await notify(db, [u for u in panel if interview_panel.ROLES.get(u.role) == kind], FEEDBACK_EVENT, interview.id, action_url=url)


async def run_feedback_overdue(now: datetime | None = None) -> dict[str, int]:
    """N6: an interview that ended over the grace period ago with no feedback tells, once, its application's owner (else the vacancy's primary)
    and each panel member who has not given theirs. Oldest first."""
    now = now or datetime.now(UTC)
    async with SessionLocal() as db:
        due = (await db.execute(
            select(Interview, JobApplication.owner_user_id, Job.assigned_recruiter_user_id)
            .join(JobApplication, JobApplication.id == Interview.application_id)
            .join(Job, Job.id == JobApplication.job_id)
            .where(Interview.overdue_notified_at.is_(None), Interview.status.in_(AWAITING_FEEDBACK),
                   func.coalesce(Interview.ends_at, Interview.scheduled_at) < now - timedelta(hours=FEEDBACK_GRACE_HOURS),
                   ~exists(select(InterviewFeedback.interview_id).where(InterviewFeedback.interview_id == Interview.id)))
            .order_by(Interview.scheduled_at, Interview.id)
            .limit(SWEEP_LIMIT)
            .with_for_update(of=Interview, skip_locked=True)
        )).all()  # fmt: skip
        ids = [row[0].id for row in due]
        panels: dict = {}
        if ids:
            owing = await db.execute(
                select(InterviewInterviewer.interview_id, User)
                .join(User, User.id == InterviewInterviewer.user_id)
                .where(InterviewInterviewer.interview_id.in_(ids),
                       ~exists(select(InterviewPanelFeedback.interview_id).where(InterviewPanelFeedback.interview_id == InterviewInterviewer.interview_id,
                                                                                 InterviewPanelFeedback.interviewer_user_id == InterviewInterviewer.user_id)))
            )  # fmt: skip
            for interview_id, person in owing.all():
                panels.setdefault(interview_id, []).append(person)
        owner_ids = {owner or primary for _, owner, primary in due} - {None}
        owners = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(owner_ids)))).all()} if owner_ids else {}
        for interview, owner, primary in due:
            await _notify_overdue(db, interview, owners.get(owner or primary), panels.get(interview.id, []))
            interview.overdue_notified_at = now
        await db.commit()
    counts = {"interviews": len(due)}
    logger.info("feedback_overdue_sweep", extra={"extra_fields": counts})
    return counts


async def _visible_people(db: AsyncSession, job: Job, candidates: list) -> list[User]:
    """The matching candidates' portal users who may see this job (hrc-008): a segment job only reaches its pool's members."""
    ids = [c.user_id for c in candidates]
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids), User.role.in_(MATCH_URLS)))).all()} if ids else {}
    ordered = [people[i] for i in ids if i in people]
    return [u for u in ordered if await job_visibility.visible_to_student(db, u, job)]


async def _match_one(db: AsyncSession, job: Job, now: datetime) -> int:
    best = await matching.portal_matches(db, job, min_score=candidate_jobs.RECOMMENDED_MIN_SCORE, limit=MATCH_RECIPIENTS_LIMIT)
    people = await _visible_people(db, job, best)
    for role, url in MATCH_URLS.items():
        await notify(db, [u for u in people if u.role == role], MATCH_EVENT, job.id, action_url=url)
    job.match_notified_at = now
    return len(people)


async def run_new_matches(now: datetime | None = None) -> dict[str, int]:
    """N7: each open job a candidate may see, once. One transaction per job, so one job's failure costs only that job."""
    now = now or datetime.now(UTC)
    fresh = (Job.match_notified_at.is_(None), Job.status.in_(JOB_OPEN_STATUSES), or_(Job.closes_on.is_(None), Job.closes_on >= date.today()),
             Job.visibility.in_((*job_visibility.PORTAL, "segment")))  # fmt: skip
    jobs = candidates = 0
    async with SessionLocal() as db:
        ids = (await db.scalars(select(Job.id).where(*fresh).order_by(Job.created_at, Job.id).limit(MATCH_JOBS_LIMIT))).all()
    for job_id in ids:
        async with SessionLocal() as db:
            job = await db.scalar(select(Job).where(Job.id == job_id, *fresh).with_for_update(skip_locked=True))
            if job is None:
                continue
            candidates += await _match_one(db, job, now)
            await db.commit()
            jobs += 1
    counts = {"jobs": jobs, "candidates": candidates}
    logger.info("new_match_sweep", extra={"extra_fields": counts})
    return counts
