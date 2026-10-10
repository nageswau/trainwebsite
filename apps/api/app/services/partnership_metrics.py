"""Partnership metrics (backlog Appendix B). upc-018 owns the module; upc-021 (DEC-SCOPE-146, spec TG8-TG13) adds the monthly target actuals.

Every actual is read from append-only facts -- `university_assignment_history`, `university_stage_history`, `university_agreement_events`,
the once-set `university_meetings.completed_at` -- and credited to the university's primary manager *at the time of the event*, so a closed month never changes (AC2: past months are
never re-scored). A constant number of queries whatever the team size."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import NamedTuple, cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Subquery, and_, distinct, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentStudentShortlistEntry,
    ApplicationDeposit,
    ApplicationStatusHistory,
    OverseasApplication,
    PartnershipTask,
    University,
    UniversityAgreement,
    UniversityAgreementEvent,
    UniversityAssignmentHistory,
    UniversityMeeting,
    UniversityStageHistory,
    UniversityVisit,
    UniversityVisitEvent,
    User,
    VisaCase,
)
from app.partnership_stages import GROUPS, STAGE_KEYS
from app.partnership_target_kpis import KPIS
from app.services.agent_applications import OFFER_COUNTED_STATUSES, WITHDRAWN
from app.services.bdm_appointments import IST
from app.services.bdm_metrics import month_range
from app.services.partnership_tasks import band_filter

TRACKED = tuple(k.key for k in KPIS if k.tracked)
CONTACTED_OR_LATER = STAGE_KEYS[STAGE_KEYS.index("initial_contact") :]  # T2 = D6
ENTRY_KPIS = {"proposal_sent": "proposals", "commercial_discussion": "negotiations", "partner_activated": "new_active"}  # T4 = D9, T5, T7 = D12

Hist = UniversityAssignmentHistory
PRIMARY = Hist.slot == "primary"


def _owner_at(rows: list[tuple[datetime, UUID | None, UUID | None]], current: UUID | None, at: datetime) -> UUID | None:
    """TG8: the latest primary change at or before `at` gives its new owner; with none yet, the first later change's previous owner; with
    no change at all, the current primary (a row that was never reassigned)."""
    prior = [to for when, _, to in rows if when <= at]
    if prior:
        return prior[-1]
    return rows[0][1] if rows else current


async def target_actuals(db: AsyncSession, manager_ids: list[UUID], month: date) -> dict[UUID, dict[str, int]]:
    """The tracked §21 KPIs (T1-T7) per manager for the IST month. Not-tracked KPIs and the future are the caller's."""
    start, end = month_range(month)
    managers = set(manager_ids)
    found: dict[UUID, dict[str, set]] = {m: defaultdict(set) for m in managers}
    if not managers:
        return {}
    # Only universities these managers ever owned can credit them.
    touched = select(Hist.university_id).where(PRIMARY, or_(Hist.to_user_id.in_(managers), Hist.from_user_id.in_(managers)))
    owned_now = select(University.id).where(University.primary_manager_user_id.in_(managers))

    def ever_owned(column):
        return or_(column.in_(touched), column.in_(owned_now))

    in_scope = ever_owned(UniversityStageHistory.university_id)

    # T1: a university's first-ever primary assignment (no previous primary), in the month.
    first = (
        select(Hist.university_id, Hist.from_user_id, Hist.to_user_id, Hist.created_at).where(PRIMARY).distinct(Hist.university_id).order_by(Hist.university_id, Hist.created_at, Hist.id).subquery()
    )
    firsts = await db.execute(select(first.c.university_id, first.c.to_user_id).where(
        first.c.from_user_id.is_(None), first.c.to_user_id.in_(managers), first.c.created_at >= start, first.c.created_at < end))  # fmt: skip
    for university_id, manager in firsts.all():
        found[manager]["new_universities"].add(university_id)

    # Events to credit to the owner at the time: (university, kpi, item counted, when).
    events: list[tuple[UUID, str, UUID, datetime]] = []
    first_contact = func.min(UniversityStageHistory.created_at)
    contacts = await db.execute(
        select(UniversityStageHistory.university_id, first_contact)
        .where(UniversityStageHistory.to_stage.in_(CONTACTED_OR_LATER), in_scope)
        .group_by(UniversityStageHistory.university_id)
        .having(first_contact >= start, first_contact < end)
    )
    events += [(u, "contacted", u, at) for u, at in contacts.all()]
    entries = await db.execute(
        select(UniversityStageHistory.university_id, UniversityStageHistory.to_stage, UniversityStageHistory.created_at).where(
            UniversityStageHistory.kind == "move", UniversityStageHistory.to_stage.in_(ENTRY_KPIS), UniversityStageHistory.from_stage != UniversityStageHistory.to_stage,
            UniversityStageHistory.created_at >= start, UniversityStageHistory.created_at < end, in_scope,
        )
    )  # fmt: skip
    events += [(u, ENTRY_KPIS[stage], u, at) for u, stage, at in entries.all()]
    signed = await db.execute(
        select(UniversityAgreement.university_id, UniversityAgreementEvent.agreement_id, UniversityAgreementEvent.created_at)
        .join(UniversityAgreement, UniversityAgreement.id == UniversityAgreementEvent.agreement_id)
        .where(
            UniversityAgreementEvent.kind == "status", UniversityAgreementEvent.to_status == "signed",
            UniversityAgreementEvent.created_at >= start, UniversityAgreementEvent.created_at < end,
            ever_owned(UniversityAgreement.university_id),
        )
    )  # fmt: skip
    events += [(u, "mous", agreement, at) for u, agreement, at in signed.all()]
    # T3 = D7 (TG13): meetings completed in the month; completion is final, so `completed_at` never moves.
    completed = await db.execute(
        select(UniversityMeeting.university_id, UniversityMeeting.id, UniversityMeeting.completed_at).where(
            UniversityMeeting.status == "completed", UniversityMeeting.completed_at >= start, UniversityMeeting.completed_at < end,
            ever_owned(UniversityMeeting.university_id),
        )
    )  # fmt: skip
    events += [(u, "meetings", meeting, at) for u, meeting, at in completed.all() if at is not None]  # the WHERE already ensures it

    if events:
        universities = {u for u, *_ in events}
        history: dict[UUID, list] = defaultdict(list)
        changes = await db.execute(
            select(Hist.university_id, Hist.created_at, Hist.from_user_id, Hist.to_user_id).where(PRIMARY, Hist.university_id.in_(universities)).order_by(Hist.created_at, Hist.id)
        )
        for university_id, *change in changes.all():
            history[university_id].append(tuple(change))
        current = dict((await db.execute(select(University.id, University.primary_manager_user_id).where(University.id.in_(universities)))).all())
        for university_id, kpi, item, at in events:
            owner = _owner_at(history[university_id], current.get(university_id), at)
            if owner in managers:
                found[owner][kpi].add(item)
    return {m: {k: len(found[m][k]) for k in TRACKED} for m in managers}


# --- upc-018 (DEC-SCOPE-153, spec PF1-PF4): the §17 student funnel / §18 university performance, Appendix B F1-F9 ---
# Each step counts in the period it was *reached* (Appendix B is event-based), per university, for every application owner (agency,
# self-service, School-bridged). Counts only: no student is identified (PF10). Commission (F10/F11) is upc-019's.


class Step(NamedTuple):
    key: str
    label: str
    tracked: bool


STEPS = (
    Step("leads", "Leads", False),  # F1 (U8): leads have no university link
    Step("counselling", "Counselling", False),  # F2
    Step("interested", "Students interested", True),  # F3
    Step("eligible", "Profiles eligible", False),  # F4
    Step("applications", "Applications", True),  # F5
    Step("offers", "Offers", True),  # F6
    Step("deposits", "Deposits", True),  # F7
    Step("visas", "Visa approvals", True),  # F8
    Step("enrolled", "Enrolled", True),  # F9
)
FUNNEL = tuple(s.key for s in STEPS if s.tracked)
MAX_PERIOD_DAYS = 366


def period(first: date, last: date) -> tuple[date, date]:
    """PF1: inclusive IST days, at most a (leap) year."""
    if first > last:
        raise HTTPException(422, "The period must start on or before its end")
    if (last - first).days >= MAX_PERIOD_DAYS:
        raise HTTPException(422, f"A period can be at most {MAX_PERIOD_DAYS} days")
    return first, last


def ist_range(first: date, last: date) -> tuple[datetime, datetime]:
    """The inclusive IST days as a half-open instant range."""
    return datetime.combine(first, time.min, tzinfo=IST), datetime.combine(last + timedelta(days=1), time.min, tzinfo=IST)


def _first_entry(statuses) -> Subquery:
    """Per application, its first status-history entry into one of `statuses`."""
    H = ApplicationStatusHistory
    return select(H.application_id, func.min(H.created_at).label("at")).where(H.to_status.in_(statuses)).group_by(H.application_id).subquery()


async def funnel_counts(db: AsyncSession, university_ids: list[UUID], first: date, last: date) -> dict[UUID, dict[str, int]]:
    """F3 and F5-F9 per university over the inclusive IST days. One grouped query per step (constant). Universities with nothing are
    absent; the caller fills zeros."""
    if not university_ids:
        return {}
    start, end = ist_range(first, last)
    App = OverseasApplication
    Shortlist = AgentStudentShortlistEntry

    def during(column):
        return and_(column >= start, column < end)

    ours = App.university_id.in_(university_ids)
    offered, enrolled = _first_entry(OFFER_COUNTED_STATUSES), _first_entry(["enrolled"])
    queries = {
        # F3: distinct agency students shortlisting the university.
        "interested": select(Shortlist.university_id, func.count(distinct(Shortlist.agent_student_id)))
        .where(Shortlist.university_id.in_(university_ids), during(Shortlist.created_at))
        .group_by(Shortlist.university_id),
        # F5: created in the period, except those withdrawn before submission (PF3).
        "applications": select(App.university_id, func.count()).where(ours, during(App.created_at), not_(and_(App.status == WITHDRAWN, App.submitted_on.is_(None)))).group_by(App.university_id),
        # F6: the recorded offer date (AGN-010), else the first entry into an offer-or-later stage; a later withdrawal keeps it (PF4).
        "offers": select(App.university_id, func.count())
        .outerjoin(offered, offered.c.application_id == App.id)
        .where(ours, or_(App.offer_date.between(first, last), and_(App.offer_date.is_(None), during(offered.c.at))))
        .group_by(App.university_id),
        # F7: paid in the period; a later remittance or refund does not un-count it.
        "deposits": select(App.university_id, func.count())
        .join(ApplicationDeposit, ApplicationDeposit.application_id == App.id)
        .where(ours, during(ApplicationDeposit.paid_at))
        .group_by(App.university_id),
        # F8: applications with a visa approved in the period (two approved cases on one application count once).
        "visas": select(App.university_id, func.count(distinct(App.id)))
        .join(VisaCase, VisaCase.application_id == App.id)
        .where(ours, VisaCase.decision == "approved", during(VisaCase.decided_at))
        .group_by(App.university_id),
        # F9: applications enrolled now, timed by their first entry into enrolled, else the enrolment confirmation.
        "enrolled": select(App.university_id, func.count())
        .outerjoin(enrolled, enrolled.c.application_id == App.id)
        .where(ours, App.status == "enrolled", during(func.coalesce(enrolled.c.at, App.enrollment_confirmed_at)))
        .group_by(App.university_id),
    }
    found: dict[UUID, dict[str, int]] = {}
    for step, stmt in queries.items():
        for university_id, n in (await db.execute(stmt)).all():
            found.setdefault(cast(UUID, university_id), dict.fromkeys(FUNNEL, 0))[step] = n  # never null: filtered by `IN university_ids`
    return found


# --- upc-023 (DEC-SCOPE-161, spec EX1, EX9, EX10): §23 expected partnerships and the §24 weighted forecast, Appendix B E1-E4 ---


class Window(NamedTuple):
    key: str
    label: str
    first: date
    last: date


def _month_start(day: date, months_ahead: int = 0) -> date:
    index = day.year * 12 + day.month - 1 + months_ahead
    return date(index // 12, index % 12 + 1, 1)


def forecast_windows(today: date) -> tuple[Window, ...]:
    """E1-E3 as inclusive IST days: this calendar month, the next one and this calendar quarter (AC2)."""
    quarter = _month_start(today, -((today.month - 1) % 3))
    this_month, next_month = _month_start(today), _month_start(today, 1)

    def last(first: date, months: int) -> date:
        return _month_start(first, months) - timedelta(days=1)

    return (
        Window("this_month", "Expected Partnerships This Month", this_month, last(this_month, 1)),
        Window("next_month", "Expected Next Month", next_month, last(next_month, 1)),
        Window("this_quarter", "Expected This Quarter", quarter, last(quarter, 3)),
    )


def weighted(probabilities: list[int]) -> float:
    """E4: Σ probability, in partnerships (10 × 80% = 8.0), to one decimal."""
    return round(sum(probabilities) / 100, 1)


# --- upc-022 (DEC-SCOPE-165, spec DB1-DB14): the §22 manager dashboard, Appendix B D1-D12 and D14, and the §20 follow-up bands ---
# Counts only, over the universities the caller's scope holds *now* (DB2); D13 is upc-023's E1, added by the route. One statement per
# figure, whatever the data size.

PENDING_AGREEMENTS = ("sent", "under_review", "negotiation")  # D10
OPEN_BANDS = ("overdue", "today", "tomorrow", "upcoming")


def scope_filter(user: User, team: frozenset[UUID]) -> list:
    """upc-018 PF6: manager = primary or backup; head = their team's universities + unowned ones; super_admin, overseas_admin = all."""
    if user.role == "partnership_manager":
        return [or_(University.primary_manager_user_id == user.id, University.backup_manager_user_id == user.id)]
    if user.role == "partnership_head":
        unowned = and_(University.primary_manager_user_id.is_(None), University.backup_manager_user_id.is_(None))
        return [or_(unowned, University.primary_manager_user_id.in_(team), University.backup_manager_user_id.in_(team))]
    return []


def _assignees(user: User, team: frozenset[UUID]) -> list:
    """DB14, the Tasks page default: a manager's own, a head's own and their reports', everyone's for super_admin."""
    if user.role == "partnership_manager":
        return [PartnershipTask.assignee_user_id == user.id]
    if user.role == "partnership_head":
        return [PartnershipTask.assignee_user_id.in_(team | {user.id})]
    return []


def _in_group(group: str):
    return and_(University.lost_at.is_(None), University.stage.in_([key for key, g in GROUPS.items() if g == group]))


async def dashboard_figures(db: AsyncSession, user: User, team: frozenset[UUID], today: date) -> dict:
    """D1-D12 and D14 for the IST month holding `today`; the bands are over the IST days around `today`."""
    start, end = month_range(today.replace(day=1))

    def during(column):
        return and_(column >= start, column < end)

    live = [University.active.is_(True), *scope_filter(user, team)]
    scope = select(University.id).where(*live)
    overview = (
        await db.execute(
            select(
                func.count(), func.count().filter(_in_group("partner")), func.count().filter(_in_group("in_progress")), func.count().filter(_in_group("target")),
                func.count().filter(University.relationship_strength == "at_risk"), func.count().filter(University.lost_at.is_not(None)),
            ).where(*live)
        )
    ).one()  # fmt: skip

    S, Event, Agreement = UniversityStageHistory, UniversityAgreementEvent, UniversityAgreement
    contacted = (
        select(S.university_id).where(S.to_stage.in_(CONTACTED_OR_LATER), S.university_id.in_(scope)).group_by(S.university_id).having(during(func.min(S.created_at))).subquery()
    )  # D6: the first entry into Initial Contact or later falls in the month
    entered = and_(S.kind == "move", S.from_stage != S.to_stage, during(S.created_at), S.university_id.in_(scope))
    month = {
        "contacted": select(func.count()).select_from(contacted),  # D6
        "meetings": select(func.count()).where(UniversityMeeting.status == "completed", during(UniversityMeeting.completed_at), UniversityMeeting.university_id.in_(scope)),  # D7
        "visits": select(func.count(distinct(UniversityVisitEvent.visit_id)))
        .join(UniversityVisit, UniversityVisit.id == UniversityVisitEvent.visit_id)
        .where(UniversityVisitEvent.to_status == "visit_completed", during(UniversityVisitEvent.created_at), UniversityVisit.university_id.in_(scope)),  # D8
        "proposals": select(func.count(distinct(S.university_id))).where(entered, S.to_stage == "proposal_sent"),  # D9
        "mous_negotiating": select(func.count()).where(Agreement.status.in_(PENDING_AGREEMENTS), Agreement.university_id.in_(scope)),  # D10
        "mous_signed": select(func.count(distinct(Event.agreement_id)))
        .join(Agreement, Agreement.id == Event.agreement_id)
        .where(Event.kind == "status", Event.to_status == "signed", during(Event.created_at), Agreement.university_id.in_(scope)),  # D11
        "activated": select(func.count(distinct(S.university_id))).where(entered, S.to_stage == "partner_activated"),  # D12
    }
    bands = (await db.execute(select(*(func.count().filter(band_filter(b, today)) for b in OPEN_BANDS)).select_from(PartnershipTask).where(*_assignees(user, team)))).one()
    return {
        "overview": dict(zip(("total", "partners", "in_progress", "targets", "at_risk", "lost"), overview, strict=True)),
        "this_month": {key: await db.scalar(stmt) or 0 for key, stmt in month.items()},
        "followups": dict(zip(OPEN_BANDS, bands, strict=True)),  # D14 = overdue
    }
