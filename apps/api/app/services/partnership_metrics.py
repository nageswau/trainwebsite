"""Partnership metrics (backlog Appendix B). upc-018 owns the module; upc-021 (DEC-SCOPE-146, spec TG8-TG13) adds the monthly target actuals.

Every actual is read from append-only facts -- `university_assignment_history`, `university_stage_history`, `university_agreement_events`,
the once-set `university_meetings.completed_at` -- and credited to the university's primary manager *at the time of the event*, so a closed month never changes (AC2: past months are
never re-scored). A constant number of queries whatever the team size."""

from collections import defaultdict
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    University,
    UniversityAgreement,
    UniversityAgreementEvent,
    UniversityAssignmentHistory,
    UniversityMeeting,
    UniversityStageHistory,
)
from app.partnership_stages import STAGE_KEYS
from app.partnership_target_kpis import KPIS
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
