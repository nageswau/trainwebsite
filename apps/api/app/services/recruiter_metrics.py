"""rec-032 (DEC-SCOPE-179, spec §3-§5): the single source of every Recruiter CRM count -- the dashboard tiles D1-D14 (EVID-018 §1;
backlog Appendix B). rec-033…035 extend it.

Scope is the lists' own (DB1): company-side tiles use rec-003's `companies.caller_scope`, requirement-side tiles rec-007's
`requirements.caller_scope`, so a tile and the list it opens agree. A manager or super_admin may narrow to one recruiter (DB3): the
figures are then that recruiter's own scope. "Today" is the IST date; flow tiles count the current IST month to now (DB4). All fifteen
numbers come from one statement of scalar sub-selects. Reads only; nothing here writes."""

from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, distinct, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Company,
    Interview,
    Job,
    JobApplication,
    JobApplicationStatusHistory,
    JobOffer,
    ProfileShare,
    ProfileShareItem,
    RecruiterCall,
    RecruiterFollowUp,
    RecruiterMeeting,
    RecruiterProfile,
    User,
)
from app.services import recruiter_companies as companies
from app.services import recruiter_follow_ups as follow_ups
from app.services import recruiter_requirements as requirements
from app.services.bdm_appointments import IST, today_ist
from app.services.interviews import OPEN as OPEN_INTERVIEWS
from app.services.recruiter import MANAGER_ROLE, ROLE

RECENT_DAYS = 7  # D1, D4, D6: "the last / next 7 days"
PARKED_REQUIREMENTS = ("on_hold", "closed", "cancelled")  # D5 (DB5): every other requirement status keeps a company active
NOT_FOUND = "Recruiter not found"


async def _subject(db: AsyncSession, user: User, recruiter_id: UUID | None) -> User | None:
    """DB2/DB3: the recruiter the figures are narrowed to, or None for the caller's whole scope."""
    if user.role not in (ROLE, MANAGER_ROLE, "super_admin"):
        raise HTTPException(403, "Recruiter role required")
    if recruiter_id is None or (user.role == ROLE and recruiter_id == user.id):
        return None
    if user.role == ROLE:
        raise HTTPException(403, "You can only view your own dashboard")
    stmt = select(User).join(RecruiterProfile, RecruiterProfile.user_id == User.id).where(User.id == recruiter_id, User.role == ROLE)
    if user.role == MANAGER_ROLE:
        stmt = stmt.where(RecruiterProfile.reporting_manager_user_id == user.id)
    subject = await db.scalar(stmt)
    if subject is None:
        raise HTTPException(404, NOT_FOUND)
    return subject


def _count(*froms, where: list, of=None):
    """One scalar sub-select: `count(*)` (or `count(DISTINCT of)`) over the joined `froms`."""
    stmt = select(func.count(distinct(of)) if of is not None else func.count()).select_from(froms[0])
    for model, on in froms[1:]:
        stmt = stmt.join(model, on)
    return stmt.where(*where).scalar_subquery()


def period(now: datetime) -> tuple[date, date, datetime]:
    """DB4: the current IST month to today, and the instant it starts."""
    today = today_ist(now)
    first = today.replace(day=1)
    return first, today, datetime.combine(first, time.min, tzinfo=IST)


async def dashboard(db: AsyncSession, user: User, recruiter_id: UUID | None, now: datetime) -> dict:
    subject = await _subject(db, user, recruiter_id)
    scoped = subject or user
    company_scope = await companies.caller_scope(db, scoped)
    job_scope = await requirements.caller_scope(db, scoped)
    first, today, month_start = period(now)
    recent = now - timedelta(days=RECENT_DAYS)

    open_company = [Company.archived_at.is_(None), Company.lost_at.is_(None)]
    new_lead = [*company_scope, *open_company, Company.stage == "new_lead"]
    history_job = ((JobApplication, JobApplication.id == JobApplicationStatusHistory.application_id), (Job, Job.id == JobApplication.job_id))

    def entered(status: str):
        return _count(
            JobApplicationStatusHistory,
            *history_job,
            of=JobApplicationStatusHistory.application_id,
            where=[
                *job_scope,
                JobApplicationStatusHistory.to_status == status,
                JobApplicationStatusHistory.created_at >= month_start,
            ],
        )

    expired = and_(*requirements.deadline_filter("expired"))
    figures = {
        "new_leads": _count(Company, where=[*new_lead, Company.created_at >= recent]),
        "contacts_pending": _count(Company, where=[*new_lead, ~exists().where(RecruiterCall.company_id == Company.id)]),
        "hot_companies": _count(Company, where=[*company_scope, *open_company, Company.priority == "hot", Company.stage != "requirement_closed"]),
        "meetings_scheduled": _count(
            RecruiterMeeting,
            (Company, Company.id == RecruiterMeeting.company_id),
            where=[
                *company_scope,
                RecruiterMeeting.status == "scheduled",
                RecruiterMeeting.starts_at >= now,
                RecruiterMeeting.starts_at < now + timedelta(days=RECENT_DAYS),
            ],
        ),
        "active_companies": _count(
            Company,
            where=[
                *company_scope,
                Company.archived_at.is_(None),
                exists().where(Job.company_id == Company.id, Job.status.not_in(PARKED_REQUIREMENTS)),
            ],
        ),
        "new_requirements": _count(Job, where=[*job_scope, Job.created_at >= recent]),
        "candidates_sourced": _count(JobApplication, (Job, Job.id == JobApplication.job_id), where=[*job_scope, JobApplication.created_at >= month_start]),
        "profiles_shared": _count(
            ProfileShareItem,
            (ProfileShare, ProfileShare.id == ProfileShareItem.share_id),
            (Job, Job.id == ProfileShare.job_id),
            where=[
                *job_scope,
                ProfileShareItem.created_at >= month_start,
            ],
        ),
        "interviews_scheduled": _count(
            Interview,
            (JobApplication, JobApplication.id == Interview.application_id),
            (Job, Job.id == JobApplication.job_id),
            where=[
                *job_scope,
                Interview.status.in_(OPEN_INTERVIEWS),
                Interview.scheduled_at >= now,
            ],
        ),
        "candidates_selected": entered("selected"),
        "candidates_joined": _count(
            JobOffer,
            (JobApplication, JobApplication.id == JobOffer.application_id),
            (Job, Job.id == JobApplication.job_id),
            where=[
                *job_scope,
                JobOffer.joining_status == "joined",
                JobOffer.actual_joining_date >= first,
                JobOffer.actual_joining_date <= today,
            ],
        ),
        "candidates_rejected": entered("rejected"),
        "follow_ups_due": _count(
            RecruiterFollowUp,
            (Company, Company.id == RecruiterFollowUp.company_id),
            where=[
                *company_scope,
                follow_ups.views(now)["today"],
            ],
        ),
        "requirements_expiring": _count(Job, where=[*job_scope, or_(and_(*requirements.deadline_filter("expiring")), expired)]),
        "requirements_expired": _count(Job, where=[*job_scope, expired]),
    }
    row = (await db.execute(select(*(value.label(key) for key, value in figures.items())))).one()
    return {
        "day": today,
        "period": {"from": first, "to": today},
        "recruiter": {"id": subject.id, "full_name": subject.full_name} if subject else None,
        "tiles": {key: getattr(row, key) or 0 for key in figures},
    }
