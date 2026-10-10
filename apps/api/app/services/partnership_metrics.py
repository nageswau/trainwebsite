"""Partnership metrics (backlog Appendix B). upc-018 owns the module; upc-021 (DEC-SCOPE-146, spec TG8-TG13) adds the monthly target actuals.

Every actual is read from append-only facts -- `university_assignment_history`, `university_stage_history`, `university_agreement_events`,
the once-set `university_meetings.completed_at` -- and credited to the university's primary manager *at the time of the event*, so a closed month never changes (AC2: past months are
never re-scored). A constant number of queries whatever the team size."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from math import floor
from statistics import median
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
    UniversityCall,
    UniversityMeeting,
    UniversityMessage,
    UniversityStageHistory,
    VisaCase,
)
from app.partnership_stages import STAGE_KEYS
from app.partnership_target_kpis import KPIS
from app.services import university_commission as commission
from app.services.agent_applications import OFFER_COUNTED_STATUSES, WITHDRAWN
from app.services.bdm_appointments import IST, today_ist
from app.services.bdm_metrics import month_range
from app.services.university_agreements import STATUS_LABELS, effective_status

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


# --- upc-028 (DEC-SCOPE-168, spec HS1-HS11): the §30 partnership health score, computed on read as of today (IST) -------------------
# Each factor is normalised to 0-1 (None = no data: left out, its weight shared out over the rest, HS5); the points are rounded by the
# largest remainder so the breakdown always adds up to the score (AC1). The commission factor is in every score but its breakdown is the
# caller's to strip for non-commission roles (HS9).


class Factor(NamedTuple):
    key: str
    label: str
    weight: int
    tracked: bool


HEALTH_FACTORS = (
    Factor("applications", "Student applications", 15, True),
    Factor("offers", "Offers", 10, True),
    Factor("visa_success", "Visa success", 10, True),
    Factor("enrolments", "Enrolments", 15, True),
    Factor("commission", "Commission", 10, True),
    Factor("response_time", "Response time", 10, True),
    Factor("meetings", "Meeting frequency", 15, True),
    Factor("agreement", "Agreement status", 15, True),
    Factor("satisfaction", "Student satisfaction", 0, False),  # Q-24: not tracked, excluded
)
BAND_LABELS = {"excellent": "Excellent", "good": "Good", "needs_attention": "Needs attention", "insufficient_data": "Insufficient data"}
HEALTH_DAYS, RECENT_DAYS = 365, 90  # HS3: the student factors look back a year; meetings and replies 90 days
FULL_APPLICATIONS, FULL_ENROLMENTS, FULL_MEETINGS = 20, 10, 3
FAST_REPLY_DAYS, SLOW_REPLY_DAYS = 2, 14  # HS4
AGREEMENT_VALUES = {"active": 1.0, "signed": 1.0, "expiring": 0.5}  # AG4 effective status; anything else 0


def band(score: int) -> str:
    """HS7: Excellent >= 80, Good 60-79, Needs attention < 60."""
    return "excellent" if score >= 80 else "good" if score >= 60 else "needs_attention"


def health_score(values: dict[str, float | None]) -> tuple[int, dict[str, int | None]]:
    """HS5/HS6: the 0-100 score and each factor's points (None when untracked or without data); Σ points = score."""
    have = [f for f in HEALTH_FACTORS if f.tracked and values.get(f.key) is not None]
    weights = sum(f.weight for f in have)
    shares = {f.key: f.weight * min(max(cast(float, values[f.key]), 0.0), 1.0) * 100 / weights for f in have} if weights else {}
    score = floor(sum(shares.values()) + 0.5 + 1e-9)
    points = {key: floor(share + 1e-9) for key, share in shares.items()}
    by_remainder = sorted(shares, key=lambda key: points[key] - shares[key])  # largest remainder first; stable in factor order
    for key in by_remainder[: score - sum(points.values())]:
        points[key] += 1
    return score, {f.key: points.get(f.key) for f in HEALTH_FACTORS}


def _ratio(part: int, whole: int, noun: str) -> str:
    return f"{part} of {whole} {noun} ({round(part * 100 / whole)}%)"


def _days(value: float) -> str:
    text = f"{value:.1f}".removesuffix(".0")
    return f"{text} day" if text == "1" else f"{text} days"


async def health(db: AsyncSession, university_ids: list[UUID], now: datetime) -> dict[UUID, dict]:
    """HS3/HS4/HS8 per university as of `now`; the caller passes partners only (HS1). A constant number of grouped queries."""
    if not university_ids:
        return {}
    today = today_ist(now)
    first = today - timedelta(days=HEALTH_DAYS - 1)
    start, end = ist_range(first, today)
    recent = ist_range(today - timedelta(days=RECENT_DAYS - 1), today)[0]
    ours = OverseasApplication.university_id.in_(university_ids)
    funnel = await funnel_counts(db, university_ids, first, today)

    decided: dict[UUID, dict[str, int]] = defaultdict(dict)
    rows = await db.execute(
        select(OverseasApplication.university_id, VisaCase.decision, func.count())
        .join(VisaCase, VisaCase.application_id == OverseasApplication.id)
        .where(ours, VisaCase.decision.in_(("approved", "refused")), VisaCase.decided_at >= start, VisaCase.decided_at < end)
        .group_by(OverseasApplication.university_id, VisaCase.decision)
    )
    for university_id, decision, n in rows.all():
        decided[university_id][cast(str, decision)] = n  # the WHERE excludes null

    # Replies (HS4): an incoming call, a connected outgoing call or a completed meeting; completed meetings also give the frequency.
    replies: dict[UUID, list[datetime]] = defaultdict(list)
    meetings: dict[UUID, int] = defaultdict(int)
    completed = await db.execute(
        select(UniversityMeeting.university_id, UniversityMeeting.completed_at).where(
            UniversityMeeting.university_id.in_(university_ids), UniversityMeeting.status == "completed", UniversityMeeting.completed_at >= recent,
            UniversityMeeting.completed_at < end,
        )
    )  # fmt: skip
    for university_id, at in completed.all():
        meetings[university_id] += 1
        replies[university_id].append(cast(datetime, at))  # completed, so never null (the CHECK)
    calls = await db.execute(
        select(UniversityCall.university_id, UniversityCall.occurred_at).where(
            UniversityCall.university_id.in_(university_ids), UniversityCall.occurred_at >= recent, UniversityCall.occurred_at <= now,
            or_(UniversityCall.direction == "incoming", UniversityCall.outcome == "connected"),
        )
    )  # fmt: skip
    for university_id, at in calls.all():
        replies[university_id].append(at)
    sent: dict[UUID, list[datetime]] = defaultdict(list)
    messages = await db.execute(
        select(UniversityMessage.university_id, UniversityMessage.sent_at).where(
            UniversityMessage.university_id.in_(university_ids), UniversityMessage.sent_at >= recent, UniversityMessage.sent_at <= now,
            or_(UniversityMessage.delivery_status.is_(None), UniversityMessage.delivery_status != "failed"),  # a failed email never arrived
        )
    )  # fmt: skip
    for university_id, at in messages.all():
        sent[university_id].append(at)

    agreements: dict[UUID, list[UniversityAgreement]] = defaultdict(list)
    for a in (await db.scalars(select(UniversityAgreement).where(UniversityAgreement.university_id.in_(university_ids)))).all():
        agreements[a.university_id].append(a)

    expected_rows = await commission.expected_rows(db, university_ids)
    received = await commission.received_sums(db, university_ids)

    found: dict[UUID, dict] = {}
    for university_id in university_ids:
        counts = funnel.get(university_id, dict.fromkeys(FUNNEL, 0))
        applications, offers, enrolments = counts["applications"], counts["offers"], counts["enrolled"]
        approved, refused = decided[university_id].get("approved", 0), decided[university_id].get("refused", 0)
        decisions = approved + refused
        expected = {c: v for c, v in commission.currency_sums(expected_rows.get(university_id, [])).items() if v > 0}
        paid = received.get(university_id, {})
        collected = sum(min(float(paid.get(c, 0)) / float(v), 1.0) for c, v in expected.items()) / len(expected) if expected else None
        waits = [
            (min((r for r in replies[university_id] if r > at), default=now) - at).total_seconds() / 86400 for at in sent[university_id]
        ]  # fmt: skip
        wait = median(waits) if waits else None
        statuses = [effective_status(a, today) for a in agreements[university_id]]
        best = max(statuses, key=lambda s: AGREEMENT_VALUES.get(s, 0.0), default=None)

        values: dict[str, float | None] = {
            "applications": min(applications / FULL_APPLICATIONS, 1.0),
            "offers": min(offers / applications, 1.0) if applications else None,
            "visa_success": approved / decisions if decisions else None,
            "enrolments": min(enrolments / FULL_ENROLMENTS, 1.0),
            "commission": collected,
            "response_time": None if wait is None else min(max((SLOW_REPLY_DAYS - wait) / (SLOW_REPLY_DAYS - FAST_REPLY_DAYS), 0.0), 1.0),
            "meetings": min(meetings[university_id] / FULL_MEETINGS, 1.0),
            "agreement": AGREEMENT_VALUES.get(best, 0.0) if best else 0.0,
        }
        measures = {
            "applications": f"{applications} in the last 12 months",
            "offers": _ratio(offers, applications, "applications") if applications else "No applications in the last 12 months",
            "visa_success": _ratio(approved, decisions, "decisions approved") if decisions else "No visa decisions in the last 12 months",
            "enrolments": f"{enrolments} in the last 12 months",
            "commission": f"{round(cast(float, collected) * 100)}% of expected commission received" if expected else "No expected commission",
            "response_time": f"Median {_days(wait)} to a reply ({len(waits)} message{'' if len(waits) == 1 else 's'})" if wait is not None else "No messages in the last 90 days",
            "meetings": f"{meetings[university_id]} completed in the last {RECENT_DAYS} days",
            "agreement": STATUS_LABELS.get(best, best) if best else "No agreement",
            "satisfaction": "Not tracked",
        }  # fmt: skip
        evidence = (
            applications or offers or decisions or enrolments or meetings[university_id] or sent[university_id] or expected
            or any(a.status in commission.APPLIED_STATUSES for a in agreements[university_id])  # HS8: an agreement that is or was in force
        )  # fmt: skip
        score, points = health_score(values) if evidence else (None, {})
        key = band(score) if score is not None else "insufficient_data"
        found[university_id] = {
            "as_of": today, "score": score, "band": key, "band_label": BAND_LABELS[key],
            "factors": [
                {
                    "key": f.key, "label": f.label, "tracked": f.tracked, "has_data": values.get(f.key) is not None, "measure": measures[f.key],
                    "weight": f.weight, "points": points.get(f.key), "value": values.get(f.key),  # the 0-1 value: tests only, not in the schema
                }
                for f in HEALTH_FACTORS
            ],
        }  # fmt: skip
    return found
