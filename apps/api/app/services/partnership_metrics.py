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
    University,
    UniversityAgreement,
    UniversityAgreementEvent,
    UniversityAssignmentHistory,
    UniversityMeeting,
    UniversityStageHistory,
    VisaCase,
)
from app.partnership_stages import STAGE_KEYS
from app.partnership_target_kpis import KPIS
from app.services.agent_applications import OFFER_COUNTED_STATUSES, WITHDRAWN
from app.services.bdm_appointments import IST
from app.services.bdm_metrics import month_range

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


# --- upc-018 (DEC-SCOPE-152, spec PF1-PF4): the §17 student funnel / §18 university performance, Appendix B F1-F9 ---
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
