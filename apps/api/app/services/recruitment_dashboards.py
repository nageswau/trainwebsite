"""hrc-033 (DEC-SCOPE-414, spec docs/superpowers/specs/2026-11-06-hrc-033-operational-recruitment-dashboards-design.md): the five operational
recruitment dashboards -- funnel, vacancy, recruiter, placement officer, interview.

Every figure is declared once, as a record kind and a predicate. Its value and its drill-down are built from that one predicate by `_where`,
so a figure always equals the records it opens (AC). All the figures of a board come from one statement of scalar sub-selects. Filters are
ANDed with the caller's scope, so a value outside it reads as zero. Reads only; drill-down rows carry no contact details, money or results."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Date, cast, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, join

from app.models import (
    JOB_OPEN_STATUSES,
    Candidate,
    Company,
    Interview,
    InterviewResult,
    Job,
    JobApplication,
    JobApplicationStatusHistory,
    JobAssignment,
    RecCandidateSource,
    RecruiterProfile,
    User,
)
from app.services import candidate_ownership, website_registrations
from app.services import candidates as candidates_svc
from app.services import interviews as interviews_svc
from app.services import recruiter_requirements as requirements
from app.services.bdm_appointments import IST, today_ist
from app.services.recruiter import MANAGER_ROLE, ROLE
from app.services.recruiter_metrics import HELD_INTERVIEWS
from app.services.telecaller_performance import date_range
from app.services.website_intake import SOURCE

OFFICER_ROLE = "placement_officer"
WHOLE_ORGANISATION = ("hr_manager", "it_admin", "partner", "super_admin")
NO_SCOPE = "Your role has no recruitment dashboards"
NAMELESS_ROLES = ("it_admin", "partner")  # D9: management reads figures and codes; the people are the recruitment team's to work
REQUIREMENT_OPENERS = (ROLE, MANAGER_ROLE, OFFICER_ROLE, "super_admin")
OPTIONS_LIMIT = 500


@dataclass(frozen=True)
class Context:
    user: User
    now: datetime
    start: datetime | None
    end: datetime | None
    first: date | None
    last: date | None
    owner: UUID | None
    employer: UUID | None
    job: UUID | None
    job_scope: list
    candidate_scope: list


@dataclass(frozen=True)
class Figure:
    key: str
    label: str
    definition: str
    kind: str  # candidate | job | application | interview
    where: Callable[[Context], list]


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    figures: tuple[Figure, ...]


@dataclass(frozen=True)
class Board:
    key: str
    label: str
    note: str
    owner_label: str
    sections: tuple[Section, ...]
    default_month: bool = True  # D5: the vacancy board is a snapshot and covers everything unless dates are given
    by_officer: bool = False  # D6: its owner filter means the placement officer


def _during(column, ctx: Context) -> list:
    return [column >= ctx.start, column < ctx.end]


# --- shared predicates --------------------------------------------------------------------------------------------------------------------
def _job_owner():
    """PF2: a requirement's assigned recruiter, else its company's."""
    return func.coalesce(Job.assigned_recruiter_user_id, Company.assigned_recruiter_user_id)


def _chosen_job(ctx: Context) -> list:
    return [*([Job.company_id == ctx.employer] if ctx.employer else []), *([Job.id == ctx.job] if ctx.job else [])]


def _officer_of_job(ctx: Context):
    """D7: on the officer board an officer reads what they are officer of; `owner` narrows further, and never widens."""
    wanted = [JobAssignment.user_id == person for person in (ctx.user.id if ctx.user.role == OFFICER_ROLE else None, ctx.owner) if person]
    return exists().where(JobAssignment.job_id == Job.id, JobAssignment.role == "placement_officer", *wanted)


def _officer_of_candidate(ctx: Context) -> list:
    wanted = [Candidate.placement_officer_user_id == person for person in (ctx.user.id if ctx.user.role == OFFICER_ROLE else None, ctx.owner) if person]
    return wanted or [Candidate.placement_officer_user_id.is_not(None)]


def _application_reached(ctx: Context, statuses: tuple[str, ...] | None = None):
    """An application of this candidate on the chosen job; with `statuses`, one now in or ever moved into one of them (history tables).
    D6: a chosen employer or job is ANDed with the caller's requirement scope, so one outside it reads as zero."""
    chosen = _chosen_job(ctx)
    stmt = select(JobApplication.id).join(Job, Job.id == JobApplication.job_id).where(JobApplication.candidate_id == Candidate.id, *chosen, *(ctx.job_scope if chosen else []))
    if statuses:
        moved = exists().where(JobApplicationStatusHistory.application_id == JobApplication.id, JobApplicationStatusHistory.to_status.in_(statuses))
        stmt = stmt.where(or_(JobApplication.status.in_(statuses), moved))
    return stmt.exists()


def _entered(status: str):
    """rec-032: an application moved into `status` during the period."""

    def where(ctx: Context) -> list:
        return [exists().where(JobApplicationStatusHistory.application_id == JobApplication.id, JobApplicationStatusHistory.to_status == status,
                               *_during(JobApplicationStatusHistory.created_at, ctx))]  # fmt: skip

    return where


# --- the funnel (Appendix B) --------------------------------------------------------------------------------------------------------------
# Each stage counts its own status and every later one, so a skipped stage still counts and each stage is a subset of the one before.
_FUNNEL_ORDER = ("screened", "shortlisted", "profile_shared", "interview", "selected", "joined")
_FUNNEL_LABELS = {"screened": "Screened", "shortlisted": "Shortlisted", "profile_shared": "Profile shared", "interview": "Interview", "selected": "Selected", "joined": "Joined"}


def _registered(ctx: Context) -> list:
    return _during(Candidate.created_at, ctx)


def _stage(statuses: tuple[str, ...] | None):
    return lambda ctx: [*_registered(ctx), _application_reached(ctx, statuses)]


_FUNNEL = Board(
    "funnel", "Recruitment funnel",
    "One cohort: the candidates registered in the period. Each stage counts the candidates who reached it or went past it, on any application.",
    "Candidate owner",
    (Section("stages", "Stages", (
        Figure("registered", "Registered", "Candidates registered in the period, on the chosen employer or job when one is chosen.", "candidate", _registered),
        Figure("applied", "Applied", "Registered candidates with at least one job application, whoever added it.", "candidate", _stage(None)),
        *(Figure(status, _FUNNEL_LABELS[status], f"Registered candidates whose application reached {_FUNNEL_LABELS[status]} or a later stage.", "candidate", _stage(_FUNNEL_ORDER[i:]))
          for i, status in enumerate(_FUNNEL_ORDER)),
    )),),
)  # fmt: skip


# --- the vacancy board (Appendix B) -------------------------------------------------------------------------------------------------------
def _opened_on():
    """`Job` has no `opened_on`: its requirement date, else the IST date it was created."""
    return func.coalesce(Job.requirement_date, cast(func.timezone("Asia/Kolkata", Job.created_at), Date))


def _vacancy(ctx: Context) -> list:
    return [_opened_on() >= ctx.first, _opened_on() <= ctx.last] if ctx.first else []


def _statuses(*statuses: str):
    return lambda ctx: [*_vacancy(ctx), Job.status.in_(statuses)]


def _aged(youngest: int, oldest: int | None):
    def where(ctx: Context) -> list:
        today = today_ist(ctx.now)
        old_enough = [_opened_on() <= today - timedelta(days=youngest)] if youngest else []  # no lower bound: a future date ages as 0
        young_enough = [_opened_on() >= today - timedelta(days=oldest)] if oldest is not None else []
        return [*_vacancy(ctx), Job.status.in_(JOB_OPEN_STATUSES), *old_enough, *young_enough]

    return where


_VACANCY = Board(
    "vacancy", "Vacancy dashboard",
    "Vacancies as they stand now. With dates, only those opened in the range. Opened on is the requirement date, else the day the vacancy was created.",
    "Requirement owner",
    (
        Section("status", "Status", (
            Figure("total", "All vacancies", "Every vacancy in view, in any status.", "job", _vacancy),
            Figure("not_yet_open", "Not yet open", "New or waiting for approval.", "job", _statuses("new", "pending_approval")),
            Figure("open", "Open", "Requirement received, sourcing, shortlisting, profiles shared or interviewing.", "job", _statuses(*JOB_OPEN_STATUSES)),
            Figure("on_hold", "On hold", "Paused.", "job", _statuses("on_hold")),
            Figure("selected_or_filled", "Selected or filled", "A candidate selected or joined, or the vacancy filled.", "job", _statuses("selected", "joined", "filled")),
            Figure("closed", "Closed", "Closed.", "job", _statuses("closed")),
            Figure("cancelled", "Cancelled", "Cancelled.", "job", _statuses("cancelled")),
        )),
        Section("ageing", "Open vacancies by age", (
            Figure("age_0_15", "0–15 days", "Open vacancies opened up to 15 days ago.", "job", _aged(0, 15)),
            Figure("age_16_30", "16–30 days", "Open vacancies opened 16 to 30 days ago.", "job", _aged(16, 30)),
            Figure("age_31_60", "31–60 days", "Open vacancies opened 31 to 60 days ago.", "job", _aged(31, 60)),
            Figure("age_over_60", "Over 60 days", "Open vacancies opened more than 60 days ago.", "job", _aged(61, None)),
        )),
    ),
    default_month=False,
)  # fmt: skip


# --- the recruiter board: website registrations and contact SLA (hrc-025 N5/N8) -----------------------------------------------------------
def _website(ctx: Context) -> list:
    source = select(RecCandidateSource.id).where(func.lower(RecCandidateSource.name) == SOURCE.lower()).scalar_subquery()
    return [Candidate.source_id == source, *_during(Candidate.created_at, ctx)]


def _sla(state: str):
    return lambda ctx: [*_website(ctx), website_registrations.contact_sla(website_registrations.first_contact()) == state]


def _open_requirement(_ctx: Context) -> list:
    return [Job.status.in_(JOB_OPEN_STATUSES)]


def _added(ctx: Context) -> list:
    return _during(JobApplication.created_at, ctx)


def _in_period(ctx: Context) -> list:
    return _during(Interview.scheduled_at, ctx)


_RECRUITER = Board(
    "recruiter", "Recruiter dashboard",
    "Website registrations in the period and how fast they were first contacted, then the recruitment work on your requirements.",
    "Owner",
    (
        Section("registrations", "Website registrations", (
            Figure("registrations", "Registered", "Candidates the website created in the period.", "candidate", _website),
            Figure("registrations_assigned", "Assigned", "Website registrations with a primary recruiter.", "candidate", lambda ctx: [*_website(ctx), Candidate.owner_user_id.is_not(None)]),
            Figure("registrations_unassigned", "Unassigned", "Website registrations with no primary recruiter yet.", "candidate", lambda ctx: [*_website(ctx), Candidate.owner_user_id.is_(None)]),
            Figure("registrations_contacted", "Contacted", "Website registrations with a call or message logged.", "candidate", lambda ctx: [*_website(ctx), website_registrations.first_contact().is_not(None)]),
        )),
        Section("sla", f"Contact target: first call or message within {website_registrations.SLA_HOURS} hours", (
            Figure("sla_met", "Met", "First contact was within the target.", "candidate", _sla("met")),
            Figure("sla_pending", "Still in time", "Not contacted yet, and the target has not passed.", "candidate", _sla("pending")),
            Figure("sla_breached", "Missed", "First contact was late, or the target passed with no contact.", "candidate", _sla("breached")),
        )),
        Section("work", "Recruitment work", (
            Figure("open_requirements", "Open requirements", "Open right now, whatever the period.", "job", _open_requirement),
            Figure("candidates_added", "Candidates added", "Applications created in the period.", "application", _added),
            Figure("interviews_scheduled", "Interviews", "Interviews dated in the period, cancelled ones left out.", "interview", lambda ctx: [*_in_period(ctx), Interview.status != "cancelled"]),
            Figure("selected", "Selected", "Applications moved to Selected in the period.", "application", _entered("selected")),
            Figure("joined", "Joined", "Applications moved to Joined in the period.", "application", _entered("joined")),
        )),
    ),
)  # fmt: skip


# --- the interview board ------------------------------------------------------------------------------------------------------------------
def _view(name: str):
    """The Interviews page's own view (rec-020), so this equals what that page lists."""
    return lambda ctx: [interviews_svc.views(ctx.now)[name][0]]


def _interview_status(*statuses: str):
    return lambda ctx: [*_in_period(ctx), Interview.status.in_(statuses)]


def _result_awaiting(_ctx: Context) -> list:
    return [exists().where(InterviewResult.interview_id == Interview.id, InterviewResult.state == "pending_approval")]


_INTERVIEW = Board(
    "interview", "Interview dashboard",
    "What needs attention right now, then what happened to interviews dated in the period.",
    "Requirement owner",
    (
        Section("now", "Right now", (
            Figure("upcoming", "Upcoming", "Not yet held and still in the future.", "interview", _view("upcoming")),
            Figure("awaiting_update", "Awaiting update", "Time has passed with no update, or held with no decision.", "interview", _view("awaiting_update")),
            Figure("on_hold", "On hold", "Decision paused.", "interview", _view("on_hold")),
            Figure("results_awaiting", "Results awaiting approval", "Decided, and waiting to be published to the candidate.", "interview", _result_awaiting),
        )),
        Section("period", "In the period", (
            Figure("held", "Held", "Completed, selected or rejected.", "interview", _interview_status(*HELD_INTERVIEWS)),
            Figure("cancelled", "Cancelled", "Cancelled before being held.", "interview", _interview_status("cancelled")),
            Figure("no_show", "No-shows", "The candidate did not attend.", "interview", _interview_status("no_show")),
        )),
    ),
)  # fmt: skip


# --- the placement officer board ----------------------------------------------------------------------------------------------------------
_OFFICER = Board(
    "officer", "Placement officer dashboard",
    "Candidates and requirements that have a placement officer. Their open work right now, then what moved in the period.",
    "Placement officer",
    (
        Section("work", "Assigned right now", (
            Figure("open_requirements", "Open requirements", "Open requirements with this placement officer.", "job", _open_requirement),
            Figure("candidates_assigned", "Candidates assigned", "Candidates with this placement officer.", "candidate", lambda _ctx: []),
            Figure("candidates_uncontacted", "Not yet contacted", "Assigned candidates with no call or message logged.", "candidate", lambda _ctx: [website_registrations.first_contact().is_(None)]),
            Figure("upcoming", "Interviews upcoming", "Interviews on these requirements, not yet held and still in the future.", "interview", _view("upcoming")),
            Figure("awaiting_update", "Interviews awaiting update", "Time has passed with no update, or held with no decision.", "interview", _view("awaiting_update")),
        )),
        Section("period", "In the period", (
            Figure("candidates_added", "Candidates added", "Applications created on these requirements.", "application", _added),
            Figure("selected", "Selected", "Applications moved to Selected.", "application", _entered("selected")),
            Figure("joined", "Joined", "Applications moved to Joined.", "application", _entered("joined")),
        )),
    ),
    by_officer=True,
)  # fmt: skip

BOARDS: dict[str, Board] = {board.key: board for board in (_FUNNEL, _VACANCY, _RECRUITER, _OFFICER, _INTERVIEW)}


# --- record kinds: the one place a figure's rows are selected from -------------------------------------------------------------------------
_JOBS = join(Job, Company, Company.id == Job.company_id)
_APPLICATIONS = join(JobApplication, _JOBS, Job.id == JobApplication.job_id).join(Candidate, Candidate.id == JobApplication.candidate_id)
_INTERVIEWS = join(Interview, _APPLICATIONS, JobApplication.id == Interview.application_id)
_FROM = {"candidate": Candidate, "job": _JOBS, "application": _APPLICATIONS, "interview": _INTERVIEWS}


def _where(board: Board, figure: Figure, ctx: Context) -> list:
    """Scope + filters + the figure's predicate: what both the count and the drill-down read."""
    if figure.kind == "candidate":
        common = [*candidates_svc.pool_filter(), Candidate.archived_at.is_(None), *ctx.candidate_scope]
        if board.by_officer:
            common += _officer_of_candidate(ctx)
        elif ctx.owner:
            common.append(Candidate.owner_user_id == ctx.owner)
        if ctx.employer or ctx.job:
            common.append(_application_reached(ctx))
    else:
        common = [*ctx.job_scope, *_chosen_job(ctx)]
        if ctx.user.role == OFFICER_ROLE and figure.kind != "job":  # D7: an officer's candidate records are their own, even on a job they co-own
            common += ctx.candidate_scope
        if board.by_officer:
            common.append(_officer_of_job(ctx))
        elif ctx.owner:
            common.append(_job_owner() == ctx.owner)
    return [*common, *figure.where(ctx)]


def _count(board: Board, figure: Figure, ctx: Context):
    return select(func.count()).select_from(_FROM[figure.kind]).where(*_where(board, figure, ctx)).scalar_subquery()


# --- reading -------------------------------------------------------------------------------------------------------------------------------
async def _scope(db: AsyncSession, user: User) -> tuple[list, list]:
    """D7: (requirement filters, candidate filters). A role granted the key with no defined record scope is refused, never shown everything."""
    if user.role == ROLE:  # hrc-025 N2: their own candidates and the unassigned queue
        return await requirements.caller_scope(db, user), [or_(candidate_ownership.mine(user.id), Candidate.owner_user_id.is_(None))]
    if user.role == MANAGER_ROLE:  # hrc-025 N2: a manager reads the whole pool
        return await requirements.caller_scope(db, user), []
    if user.role == OFFICER_ROLE:
        return await requirements.caller_scope(db, user, officers=True), [candidate_ownership.mine(user.id)]
    if user.role in WHOLE_ORGANISATION:
        return [], []
    raise HTTPException(403, NO_SCOPE)


async def _context(db: AsyncSession, user: User, board: Board, date_from: date | None, date_to: date | None, owner: UUID | None, employer: UUID | None, job: UUID | None, now: datetime) -> Context:
    job_scope, candidate_scope = await _scope(db, user)
    first: date | None = None
    last: date | None = None
    start = end = None
    if board.default_month or date_from or date_to:
        first, last = date_range(date_from, date_to, today_ist(now))
        start, end = datetime.combine(first, time.min, tzinfo=IST), datetime.combine(last + timedelta(days=1), time.min, tzinfo=IST)
    return Context(user, now, start, end, first, last, owner, employer, job, job_scope, candidate_scope)


async def _options(db: AsyncSession, board: Board, ctx: Context) -> dict:
    """The filter choices, from the caller's own scope. A chosen value sorts first, so it survives the cap."""
    user = ctx.user
    person_role = OFFICER_ROLE if board.by_officer else ROLE
    people = select(User.id, User.full_name).where(User.role == person_role, User.active.is_(True))
    if user.role == person_role:
        people = people.where(User.id == user.id)
    elif user.role == MANAGER_ROLE and not board.by_officer:
        people = people.where(User.id.in_(select(RecruiterProfile.user_id).where(RecruiterProfile.reporting_manager_user_id == user.id)))
    elif user.role == ROLE or (user.role == OFFICER_ROLE and not board.by_officer):
        people = people.where(false())
    employers = (select(Company.id, Company.name).join(Job, Job.company_id == Company.id).where(*ctx.job_scope).group_by(Company.id, Company.name)
                 .order_by(*([(Company.id == ctx.employer).desc()] if ctx.employer else []), Company.name, Company.id).limit(OPTIONS_LIMIT))  # fmt: skip
    jobs = (select(Job.id, Job.requirement_code, Job.title)
            .where(*ctx.job_scope, *([Job.company_id == ctx.employer] if ctx.employer else []))
            .order_by((Job.id == ctx.job).desc() if ctx.job else Job.created_at.desc(), Job.created_at.desc(), Job.id).limit(OPTIONS_LIMIT))  # fmt: skip
    return {
        "owners": [{"id": str(i), "label": name} for i, name in (await db.execute(people.order_by(*([(User.id == ctx.owner).desc()] if ctx.owner else []), User.full_name, User.id).limit(OPTIONS_LIMIT))).all()],
        "employers": [{"id": str(i), "label": name} for i, name in (await db.execute(employers)).all()],
        "jobs": [{"id": str(i), "label": f"{code} — {title}"} for i, code, title in (await db.execute(jobs)).all()],
    }


async def dashboard(db: AsyncSession, user: User, key: str, date_from: date | None, date_to: date | None, owner: UUID | None, employer: UUID | None, job: UUID | None, now: datetime, *, with_options: bool = True) -> dict:
    board = BOARDS[key]
    ctx = await _context(db, user, board, date_from, date_to, owner, employer, job, now)
    figures = [figure for section in board.sections for figure in section.figures]
    row = (await db.execute(select(*(_count(board, figure, ctx).label(figure.key) for figure in figures)))).one()
    return {
        "board": board.key,
        "label": board.label,
        "note": board.note,
        "owner_label": board.owner_label,
        "date_from": ctx.first,
        "date_to": ctx.last,
        "filters": {"owner": owner, "employer": employer, "job": job},
        "sections": [{"key": section.key, "label": section.label,
                      "figures": [{"key": f.key, "label": f.label, "definition": f.definition, "value": getattr(row, f.key)} for f in section.figures]}
                     for section in board.sections],
        "options": await _options(db, board, ctx) if with_options else None,
    }  # fmt: skip


def _status_label(kind: str, status: str) -> str:
    """D4/D9: an interview's status can hold the decision before its result is published, so a row only says it was held."""
    return "Held" if kind == "interview" and status in ("selected", "rejected") else status.replace("_", " ").capitalize()


_CANDIDATE_CODE = {"key": "candidate", "label": "Candidate", "type": "text"}
_CANDIDATE_NAME = {"key": "name", "label": "Name", "type": "text"}
_STATUS = {"key": "status", "label": "Status", "type": "text"}
_COLUMNS = {
    "candidate": [_CANDIDATE_CODE, _CANDIDATE_NAME, {"key": "owner", "label": "Owner", "type": "text"}, {"key": "registered", "label": "Registered", "type": "datetime"}],
    "job": [{"key": "requirement", "label": "Requirement", "type": "text"}, {"key": "title", "label": "Title", "type": "text"}, {"key": "company", "label": "Employer", "type": "text"},
            _STATUS, {"key": "owner", "label": "Owner", "type": "text"}, {"key": "opened_on", "label": "Opened on", "type": "date"}, {"key": "age_days", "label": "Age (days)", "type": "number"}],
    "application": [{"key": "application", "label": "Application", "type": "text"}, _CANDIDATE_CODE, _CANDIDATE_NAME, {"key": "requirement", "label": "Requirement", "type": "text"},
                    {"key": "company", "label": "Employer", "type": "text"}, _STATUS],
    "interview": [{"key": "interview", "label": "Interview", "type": "text"}, _CANDIDATE_CODE, _CANDIDATE_NAME, {"key": "requirement", "label": "Requirement", "type": "text"},
                  {"key": "company", "label": "Employer", "type": "text"}, {"key": "scheduled", "label": "When", "type": "datetime"}, _STATUS],
}  # fmt: skip


def _rows_select(kind: str, ctx: Context):
    """A record kind's rows: `id`, what `_href` needs, and one labelled column per `_COLUMNS` key, in a stable order."""
    if kind == "candidate":
        owner = aliased(User)
        return (select(Candidate.id.label("id"), Candidate.id.label("candidate_id"), Candidate.candidate_code.label("candidate"), Candidate.name.label("name"),
                       owner.full_name.label("owner"), Candidate.created_at.label("registered"))
                .select_from(Candidate).outerjoin(owner, owner.id == Candidate.owner_user_id).order_by(Candidate.created_at.desc(), Candidate.id))  # fmt: skip
    if kind == "job":
        owner = aliased(User)
        opened = _opened_on()
        return (select(Job.id.label("id"), Job.requirement_code.label("requirement"), Job.title.label("title"), Company.name.label("company"), Job.status.label("status"),
                       owner.full_name.label("owner"), opened.label("opened_on"), func.greatest(today_ist(ctx.now) - opened, 0).label("age_days"))
                .select_from(_JOBS).outerjoin(owner, owner.id == _job_owner()).order_by(opened, Job.id))  # fmt: skip
    if kind == "application":
        return (select(JobApplication.id.label("id"), Candidate.id.label("candidate_id"), JobApplication.application_code.label("application"), Candidate.candidate_code.label("candidate"),
                       Candidate.name.label("name"), Job.requirement_code.label("requirement"), Company.name.label("company"), JobApplication.status.label("status"))
                .select_from(_APPLICATIONS).order_by(JobApplication.created_at.desc(), JobApplication.id))  # fmt: skip
    return (select(Interview.id.label("id"), Candidate.id.label("candidate_id"), Interview.interview_code.label("interview"), Candidate.candidate_code.label("candidate"),
                   Candidate.name.label("name"), Job.requirement_code.label("requirement"), Company.name.label("company"), Interview.scheduled_at.label("scheduled"), Interview.status.label("status"))
            .select_from(_INTERVIEWS).order_by(Interview.scheduled_at.desc(), Interview.id))  # fmt: skip


def _href(kind: str, role: str, row) -> str | None:
    """D9: a row links to its record only for a role that can open that screen."""
    if kind == "job":
        return f"/recruiter/requirements/{row.id}" if role in REQUIREMENT_OPENERS else None
    return f"/recruiter/candidates/{row.candidate_id}" if role in candidates_svc.READERS else None


async def drill(db: AsyncSession, user: User, key: str, figure_key: str, date_from: date | None, date_to: date | None, owner: UUID | None, employer: UUID | None, job: UUID | None,
                now: datetime, *, limit: int, offset: int) -> dict:  # fmt: skip
    board = BOARDS[key]
    figure = next((f for section in board.sections for f in section.figures if f.key == figure_key), None)
    if figure is None:
        raise HTTPException(404, "Figure not found")
    ctx = await _context(db, user, board, date_from, date_to, owner, employer, job, now)
    where = _where(board, figure, ctx)
    total = await db.scalar(select(_count(board, figure, ctx)))
    rows = (await db.execute(_rows_select(figure.kind, ctx).where(*where).limit(limit).offset(offset))).all()
    hide_names = user.role in NAMELESS_ROLES
    columns = [c for c in _COLUMNS[figure.kind] if not (hide_names and c["key"] == "name")]
    items = []
    for row in rows:
        values = {c["key"]: _status_label(figure.kind, getattr(row, c["key"])) if c["key"] == "status" else getattr(row, c["key"]) for c in columns}
        items.append({"id": row.id, "href": _href(figure.kind, user.role, row), **values})
    return {"figure": {"key": figure.key, "label": figure.label, "definition": figure.definition}, "total": total or 0, "limit": limit, "offset": offset, "columns": columns, "items": items}


async def export_payload(db: AsyncSession, user: User, key: str, date_from: date | None, date_to: date | None, owner: UUID | None, employer: UUID | None, job: UUID | None, now: datetime) -> dict:
    data = await dashboard(db, user, key, date_from, date_to, owner, employer, job, now, with_options=False)
    return {
        "board": key,
        "date_from": data["date_from"],
        "date_to": data["date_to"],
        "columns": [{"key": "section", "label": "Section"}, {"key": "figure", "label": "Figure"}, {"key": "count", "label": "Count"}, {"key": "definition", "label": "Definition"}],
        "items": [{"section": section["label"], "figure": f["label"], "count": f["value"], "definition": f["definition"]} for section in data["sections"] for f in section["figures"]],
        "totals": None,
    }
