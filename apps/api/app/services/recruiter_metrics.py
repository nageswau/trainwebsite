"""rec-032 (DEC-SCOPE-180, spec §3-§5): the single source of every Recruiter CRM count -- the dashboard tiles D1-D14 (EVID-018 §1;
backlog Appendix B). rec-033…035 extend it.

Scope is the lists' own (DB1): company-side tiles use rec-003's `companies.caller_scope`, requirement-side tiles rec-007's
`requirements.caller_scope`, so a tile and the list it opens agree. A manager or super_admin may narrow to one recruiter (DB3): the
figures are then that recruiter's own scope. "Today" is the IST date; flow tiles count the current IST month to now (DB4). All fifteen
numbers come from one statement of scalar sub-selects. Reads only; nothing here writes."""

from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import ColumnElement, Date, String, and_, cast, distinct, exists, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Company,
    CompanyContact,
    Interview,
    Job,
    JobApplication,
    JobApplicationStatusHistory,
    JobOffer,
    JobStatusHistory,
    ProfileShare,
    ProfileShareItem,
    RecJobCategory,
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
from app.services.telecaller_performance import date_range  # rec-033 PF3: tel-023's range rules and messages

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


# --- rec-033 (DEC-SCOPE-182 PF1-PF9): the §24 performance dashboard, P1-P15 per recruiter over a period ----------------------------------
PERFORMANCE_ROLES = (MANAGER_ROLE, "super_admin", "it_admin")  # PF1 (Q-25): recruiters are IT staff (R2), so it_admin reads too
COUNTS = ("recruiter_leads", "active_companies", "requirements", "candidates_sourced", "profiles_shared", "interviews", "selected", "joined", "requirements_closed")
# PF6/PF8: key -> (numerator, denominator, scale, decimals); a zero denominator is None ("—").
RATIOS = {
    "selection_pct": ("selected", "candidates_sourced", 100, 1),
    "joining_pct": ("joined", "selected", 100, 1),
    "profile_to_interview": ("interviews", "profiles_shared", 1, 2),
    "interview_to_selection": ("selected", "interviews", 1, 2),
    "selection_to_joining": ("joined", "selected", 1, 2),
}
COLUMNS = [  # the screen's and the CSV's columns, in EVID-018 §24 order
    {"key": "full_name", "label": "Recruiter"}, {"key": "status", "label": "Status"},
    {"key": "recruiter_leads", "label": "Recruiter Leads"}, {"key": "active_companies", "label": "Active Companies"},
    {"key": "requirements", "label": "Requirements"}, {"key": "candidates_sourced", "label": "Candidates Sourced"},
    {"key": "profiles_shared", "label": "Profiles Shared"}, {"key": "interviews", "label": "Interviews"}, {"key": "selected", "label": "Selected"},
    {"key": "joined", "label": "Joined"}, {"key": "selection_pct", "label": "Selection %"}, {"key": "joining_pct", "label": "Joining %"},
    {"key": "profile_to_interview", "label": "Profile-to-Interview Ratio"}, {"key": "interview_to_selection", "label": "Interview-to-Selection Ratio"},
    {"key": "selection_to_joining", "label": "Selection-to-Joining Ratio"}, {"key": "avg_closure_days", "label": "Average Closure Time (days)"},
    {"key": "requirements_closed", "label": "Requirements Closed"},
]
HELD_INTERVIEWS = ("completed", "selected", "rejected")  # PF5: an interview that took place (an outcome is recorded)
UNASSIGNED = "Unassigned"
PERFORMANCE_REFUSED = "Recruiter performance is for managers and administrators"


async def _people(db: AsyncSession, user: User, recruiter_id: UUID | None) -> list[User]:
    """PF1: the recruiters the caller compares (a manager's direct reports; every recruiter for an administrator), or the one drilled into."""
    if user.role not in PERFORMANCE_ROLES:
        raise HTTPException(403, PERFORMANCE_REFUSED)
    stmt = select(User).join(RecruiterProfile, RecruiterProfile.user_id == User.id).where(User.role == ROLE)
    if user.role == MANAGER_ROLE:
        stmt = stmt.where(RecruiterProfile.reporting_manager_user_id == user.id)
    if recruiter_id is None:
        return sorted((await db.scalars(stmt)).all(), key=lambda person: person.full_name.casefold())
    person = await db.scalar(stmt.where(User.id == recruiter_id))
    if person is None:
        raise HTTPException(404, NOT_FOUND)
    return [person]


def _figures(sums: dict[str, int]) -> dict:
    """PF8: the counts, the ratios worked out from them, and the mean closure time (from the summed `closure_days`)."""
    counts = {key: sums[key] for key in COUNTS}
    ratios = {key: round(counts[top] * scale / counts[bottom], places) if counts[bottom] else None for key, (top, bottom, scale, places) in RATIOS.items()}
    closed = counts["requirements_closed"]
    return {**counts, **ratios, "avg_closure_days": round(sums["closure_days"] / closed, 1) if closed else None}


async def performance(db: AsyncSession, user: User, recruiter_id: UUID | None, date_from: date | None, date_to: date | None, now: datetime) -> dict:
    """P1-P15 per recruiter (+ the Unassigned row unless drilled down) and a Total that is the sum of the rows (AC2). Each figure has one
    owner (PF2): a company's assigned recruiter; a requirement's assigned recruiter, else its company's. One statement for every figure."""
    people = await _people(db, user, recruiter_id)
    today = today_ist(now)
    first, last = date_range(date_from, date_to, today)
    start, end = datetime.combine(first, time.min, tzinfo=IST), datetime.combine(last + timedelta(days=1), time.min, tzinfo=IST)
    ids = [person.id for person in people]

    company_owner = Company.assigned_recruiter_user_id
    job_owner = func.coalesce(Job.assigned_recruiter_user_id, Company.assigned_recruiter_user_id)
    of_job = (Company, Company.id == Job.company_id)
    of_application = ((Job, Job.id == JobApplication.job_id), of_job)

    def grouped(key: str, owner, value, *froms, where: list):
        scope = owner.in_(ids) if recruiter_id else or_(owner.in_(ids), owner.is_(None))
        stmt = select(literal(key, String).label("figure"), owner.label("owner"), value.label("value")).select_from(froms[0])
        for model, on in froms[1:]:
            stmt = stmt.join(model, on)
        return stmt.where(*where, scope).group_by(owner)

    def during(column) -> list:
        return [column >= start, column < end]

    # PF4: a requirement's status at the period end -- today's when the period ends today (so P2 = D5), else its last history row before then.
    latest = (
        select(JobStatusHistory.to_status)
        .where(JobStatusHistory.job_id == Job.id, JobStatusHistory.created_at < end)
        .order_by(JobStatusHistory.created_at.desc(), JobStatusHistory.id.desc())
        .limit(1)
        .correlate(Job)
        .scalar_subquery()
    )
    status_at_end: ColumnElement[str] = Job.status.expression if last == today else func.coalesce(latest, Job.status)
    # PF7: each requirement closed in the period, at its last close.
    closes = (
        select(JobStatusHistory.job_id, func.max(JobStatusHistory.created_at).label("closed_at"))
        .where(JobStatusHistory.to_status == "closed", *during(JobStatusHistory.created_at))
        .group_by(JobStatusHistory.job_id)
        .subquery()
    )
    def ist_day(column):
        return cast(func.timezone(IST.key, column), Date)

    closed_job = (closes, (Job, Job.id == closes.c.job_id), of_job)
    selected = JobApplicationStatusHistory

    statement = union_all(
        grouped("recruiter_leads", company_owner, func.count(), Company, where=during(Company.created_at)),
        grouped("active_companies", company_owner, func.count(), Company, where=[
            or_(Company.archived_at.is_(None), Company.archived_at >= end),
            exists().where(Job.company_id == Company.id, Job.created_at < end, status_at_end.not_in(PARKED_REQUIREMENTS)),
        ]),
        grouped("requirements", job_owner, func.count(), Job, of_job, where=during(Job.created_at)),
        grouped("candidates_sourced", job_owner, func.count(), JobApplication, *of_application, where=during(JobApplication.created_at)),
        grouped("profiles_shared", job_owner, func.count(), ProfileShareItem, (ProfileShare, ProfileShare.id == ProfileShareItem.share_id),
                (Job, Job.id == ProfileShare.job_id), of_job, where=during(ProfileShareItem.created_at)),
        grouped("interviews", job_owner, func.count(), Interview, (JobApplication, JobApplication.id == Interview.application_id), *of_application,
                where=[Interview.status.in_(HELD_INTERVIEWS), *during(Interview.scheduled_at)]),
        grouped("selected", job_owner, func.count(distinct(selected.application_id)), selected,
                (JobApplication, JobApplication.id == selected.application_id), *of_application,
                where=[selected.to_status == "selected", *during(selected.created_at)]),
        grouped("joined", job_owner, func.count(), JobOffer, (JobApplication, JobApplication.id == JobOffer.application_id), *of_application,
                where=[JobOffer.joining_status == "joined", JobOffer.actual_joining_date >= first, JobOffer.actual_joining_date <= last]),
        grouped("requirements_closed", job_owner, func.count(), *closed_job, where=[]),
        grouped("closure_days", job_owner, func.sum(ist_day(closes.c.closed_at) - func.coalesce(Job.requirement_date, ist_day(Job.created_at))),
                *closed_job, where=[]),
    )
    values = {(row.figure, row.owner): int(row.value or 0) for row in await db.execute(statement)}
    keys = (*COUNTS, "closure_days")
    # Every value belongs to a row (the scope filter above), so the Total is simply every value summed (AC2).
    totals = {key: sum(value for (figure, _), value in values.items() if figure == key) for key in keys}
    owners = [(person.id, person.full_name, person.active) for person in people] + ([] if recruiter_id else [(None, UNASSIGNED, True)])
    items = [
        {"user_id": owner, "full_name": name, "active": active, "status": "" if owner is None else "Active" if active else "Inactive",
         **_figures({key: values.get((key, owner), 0) for key in keys})}
        for owner, name, active in owners
    ]
    subject = people[0] if recruiter_id else None
    return {
        "date_from": first,
        "date_to": last,
        "recruiter": {"id": subject.id, "full_name": subject.full_name} if subject else None,
        "columns": COLUMNS,
        "items": items,
        "totals": {"user_id": None, "full_name": "Total", "active": True, "status": "", **_figures(totals)},
    }


# --- rec-035 (DEC-SCOPE MG1-MG8): the §26 management dashboard, M1-M9 for the caller's whole scope ---------------------------------------
FINISHED_APPLICATIONS = ("joined", "rejected", "withdrawn")  # M4: a candidate is in the pipeline while any application is not one of these
TOP = 10  # M8, M9


async def management(db: AsyncSession, user: User, date_from: date | None, date_to: date | None, now: datetime) -> dict:
    """M1-M9: who and whose figures as rec-033 (MG1/MG2: PF1 roles, PF2 owners, Unassigned included). M1-M4 and M9 are now; M5-M8 count
    the period (MG3). Three statements after the team lookup: the seven totals, the top companies, the top job categories."""
    ids = [person.id for person in await _people(db, user, None)]
    first, last = date_range(date_from, date_to, today_ist(now))
    start, end = datetime.combine(first, time.min, tzinfo=IST), datetime.combine(last + timedelta(days=1), time.min, tzinfo=IST)

    def in_scope(owner) -> ColumnElement[bool]:
        return or_(owner.in_(ids), owner.is_(None))

    company_scope = in_scope(Company.assigned_recruiter_user_id)
    job_scope = in_scope(func.coalesce(Job.assigned_recruiter_user_id, Company.assigned_recruiter_user_id))
    of_job = (Company, Company.id == Job.company_id)
    of_application = ((Job, Job.id == JobApplication.job_id), of_job)
    open_job = Job.status.not_in(PARKED_REQUIREMENTS)
    active_company = and_(Company.archived_at.is_(None), exists().where(Job.company_id == Company.id, open_job))
    joined = and_(JobOffer.joining_status == "joined", JobOffer.actual_joining_date >= first, JobOffer.actual_joining_date <= last)
    history = JobApplicationStatusHistory

    figures = {
        "companies": _count(Company, where=[company_scope, Company.archived_at.is_(None), Company.stage != "new_lead"]),  # MG4
        "active_recruiters": _count(CompanyContact, (Company, Company.id == CompanyContact.company_id),
                                    where=[company_scope, CompanyContact.active.is_(True), active_company]),  # MG5
        "open_requirements": _count(Job, of_job, where=[job_scope, open_job]),
        "candidates_in_pipeline": _count(JobApplication, *of_application, of=JobApplication.candidate_id,
                                         where=[job_scope, JobApplication.status.not_in(FINISHED_APPLICATIONS)]),
        "interviews": _count(Interview, (JobApplication, JobApplication.id == Interview.application_id), *of_application,
                             where=[job_scope, Interview.scheduled_at >= start, Interview.scheduled_at < end]),
        "selected": _count(history, (JobApplication, JobApplication.id == history.application_id), *of_application, of=history.application_id,
                           where=[job_scope, history.to_status == "selected", history.created_at >= start, history.created_at < end]),
        "joined": _count(JobOffer, (JobApplication, JobApplication.id == JobOffer.application_id), *of_application, where=[job_scope, joined]),
    }
    totals = (await db.execute(select(*(value.label(key) for key, value in figures.items())))).one()

    hires = func.count().label("joined")
    top_companies = await db.execute(  # MG7
        select(Company.id, Company.name, hires)
        .select_from(JobOffer)
        .join(JobApplication, JobApplication.id == JobOffer.application_id)
        .join(Job, Job.id == JobApplication.job_id)
        .join(Company, Company.id == Job.company_id)
        .where(job_scope, joined)
        .group_by(Company.id, Company.name)
        .order_by(hires.desc(), func.lower(Company.name), Company.id)
        .limit(TOP)
    )
    open_count = func.count().label("open_requirements")
    top_categories = await db.execute(  # MG8
        select(RecJobCategory.id, RecJobCategory.name, open_count)
        .select_from(Job)
        .join(Company, Company.id == Job.company_id)
        .join(RecJobCategory, RecJobCategory.id == Job.job_category_id)
        .where(job_scope, open_job)
        .group_by(RecJobCategory.id, RecJobCategory.name)
        .order_by(open_count.desc(), func.lower(RecJobCategory.name), RecJobCategory.id)
        .limit(TOP)
    )
    return {
        "date_from": first,
        "date_to": last,
        "totals": {key: getattr(totals, key) or 0 for key in figures},
        "top_companies": [{"id": row.id, "name": row.name, "joined": row.joined} for row in top_companies],
        "top_categories": [{"id": row.id, "name": row.name, "open_requirements": row.open_requirements} for row in top_categories],
    }
