"""upc-018 -- the §17/§18 funnel counts (spec PF2-PF4, Appendix B F3/F5-F9; AC1-AC5, AC9). Each test builds a fresh university and
reads March 2025 (IST), so no other test's rows are counted."""

from datetime import UTC, date, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from app.core.database import engine
from app.services.partnership_metrics import STEPS, funnel_counts, ist_range, period
from tests.agn003_helpers import mk_university
from tests.upc018_helpers import APRIL, FEB, IN_MARCH, agency, application, history, mk_deposit, paid_deposit, shortlist, students, visa

MARCH_START, MARCH_END = date(2025, 3, 1), date(2025, 3, 31)
ZERO = {"interested": 0, "applications": 0, "offers": 0, "deposits": 0, "visas": 0, "enrolled": 0}


async def _counts(db_session, university) -> dict:
    return (await funnel_counts(db_session, [university.id], MARCH_START, MARCH_END)).get(university.id, ZERO)


def test_step_catalogue_in_source_order_with_the_untracked_steps():
    assert [s.key for s in STEPS] == ["leads", "counselling", "interested", "eligible", "applications", "offers", "deposits", "visas", "enrolled"]
    assert [s.key for s in STEPS if not s.tracked] == ["leads", "counselling", "eligible"]


def test_period_is_inclusive_ist_days():
    start, end = ist_range(date(2025, 3, 1), date(2025, 3, 31))
    assert start == datetime(2025, 2, 28, 18, 30, tzinfo=UTC)
    assert end == datetime(2025, 3, 31, 18, 30, tzinfo=UTC)


def test_period_rules():
    assert period(date(2025, 3, 1), date(2025, 3, 1)) == (date(2025, 3, 1), date(2025, 3, 1))
    assert period(date(2024, 1, 1), date(2024, 12, 31)) == (date(2024, 1, 1), date(2024, 12, 31))  # 366 days (leap year)
    for first, last in ((date(2025, 3, 2), date(2025, 3, 1)), (date(2024, 1, 1), date(2025, 1, 1))):
        with pytest.raises(HTTPException) as refused:
            period(first, last)
        assert refused.value.status_code == 422


@pytest.mark.asyncio
async def test_empty_university_counts_nothing(db_session):
    uni = await mk_university(db_session)
    assert await _counts(db_session, uni) == ZERO


@pytest.mark.asyncio
async def test_interested_is_distinct_students_shortlisting_in_the_period(db_session):
    uni, other = await mk_university(db_session), await mk_university(db_session)
    org = await agency(db_session)
    a, b, c = await students(db_session, org, 3)
    await shortlist(db_session, a, uni)
    await shortlist(db_session, a, uni)  # the same student twice: one interested student
    await shortlist(db_session, b, uni)
    await shortlist(db_session, c, uni, FEB)  # before the period
    await shortlist(db_session, c, other)  # another university
    assert (await _counts(db_session, uni))["interested"] == 2


@pytest.mark.asyncio
async def test_applications_created_in_the_period_of_every_owner_kind(db_session):
    uni = await mk_university(db_session)
    org = await agency(db_session)
    (rec,) = await students(db_session, org, 1)
    await application(db_session, uni, org=org, record=rec)  # agency
    await application(db_session, uni)  # self-service / legacy row (no owner needed for counting)
    await application(db_session, uni, when=APRIL)  # after the period
    await application(db_session, uni, org=org, record=rec, status="withdrawn")  # withdrawn before submission: not an application
    await application(db_session, uni, org=org, record=rec, status="withdrawn", submitted_on=date(2025, 3, 2))  # withdrawn after submitting: counts
    assert (await _counts(db_session, uni))["applications"] == 3


@pytest.mark.asyncio
async def test_ist_day_boundaries(db_session):
    uni = await mk_university(db_session)
    await application(db_session, uni, when=datetime(2025, 2, 28, 19, tzinfo=UTC))  # 1 Mar 00:30 IST: in
    await application(db_session, uni, when=datetime(2025, 3, 31, 19, tzinfo=UTC))  # 1 Apr 00:30 IST: out
    await application(db_session, uni, when=datetime(2025, 2, 28, 18, tzinfo=UTC))  # 28 Feb 23:30 IST: out
    assert (await _counts(db_session, uni))["applications"] == 1


@pytest.mark.asyncio
async def test_offers_by_offer_date_else_first_history_entry(db_session):
    uni = await mk_university(db_session)
    recorded = await application(db_session, uni, when=FEB, status="offer", offer_type="conditional", offer_date=date(2025, 3, 3))
    await history(db_session, recorded, "offer", FEB)  # the recorded offer date wins over the history time
    by_history = await application(db_session, uni, when=FEB, status="visa_documentation")
    await history(db_session, by_history, "offer", IN_MARCH)
    await history(db_session, by_history, "visa_documentation", APRIL, "offer")
    earlier = await application(db_session, uni, when=FEB, status="offer")
    await history(db_session, earlier, "offer", FEB)  # offer reached before the period
    await application(db_session, uni, status="offer", offer_type="unconditional", offer_date=date(2025, 4, 1))  # after
    assert (await _counts(db_session, uni))["offers"] == 2


@pytest.mark.asyncio
async def test_withdrawn_counts_only_at_the_steps_it_reached(db_session):
    uni = await mk_university(db_session)
    after_offer = await application(db_session, uni, status="withdrawn", submitted_on=date(2025, 3, 1), offer_type="conditional", offer_date=date(2025, 3, 5))
    await history(db_session, after_offer, "withdrawn", IN_MARCH, "offer")
    before_offer = await application(db_session, uni, status="withdrawn", submitted_on=date(2025, 3, 1))
    await history(db_session, before_offer, "withdrawn", IN_MARCH, "university_selection")
    counts = await _counts(db_session, uni)
    assert (counts["applications"], counts["offers"], counts["enrolled"]) == (2, 1, 0)


@pytest.mark.asyncio
async def test_deposits_paid_in_the_period_even_if_later_refunded(db_session):
    uni = await mk_university(db_session)
    org = await agency(db_session)
    (rec,) = await students(db_session, org, 1)
    by = org["master"]
    await paid_deposit(db_session, await application(db_session, uni, org=org, record=rec), by)
    await paid_deposit(db_session, await application(db_session, uni, org=org, record=rec), by, APRIL)
    await mk_deposit(db_session, await application(db_session, uni, org=org, record=rec), by=by)  # pending: never paid
    refunded = await paid_deposit(db_session, await application(db_session, uni, org=org, record=rec), by)
    refunded.status, refunded.refunded_at, refunded.refund_amount, refunded.refund_reason = "refunded", date(2025, 4, 2), 1000, "Visa refused"
    await db_session.commit()
    assert (await _counts(db_session, uni))["deposits"] == 2


@pytest.mark.asyncio
async def test_visas_approved_in_the_period(db_session):
    uni = await mk_university(db_session)
    approved = await application(db_session, uni, when=FEB)
    await visa(db_session, approved)
    await visa(db_session, approved, "approved", IN_MARCH)  # a second approved case on one application: still one
    await visa(db_session, await application(db_session, uni), "refused")
    await visa(db_session, await application(db_session, uni), None)  # in progress
    await visa(db_session, await application(db_session, uni), "approved", APRIL)
    assert (await _counts(db_session, uni))["visas"] == 1


@pytest.mark.asyncio
async def test_enrolled_by_first_history_entry_else_confirmation(db_session):
    uni = await mk_university(db_session)
    by_history = await application(db_session, uni, when=FEB, status="enrolled", enrollment_confirmed_at=APRIL)
    await history(db_session, by_history, "enrolled", IN_MARCH, "status_tracking")
    await application(db_session, uni, when=FEB, status="enrolled", enrollment_confirmed_at=IN_MARCH)  # no history row
    earlier = await application(db_session, uni, when=FEB, status="enrolled")
    await history(db_session, earlier, "enrolled", FEB, "status_tracking")
    moved_on = await application(db_session, uni, when=FEB, status="status_tracking")  # reached enrolled once, no longer enrolled
    await history(db_session, moved_on, "enrolled", IN_MARCH, "status_tracking")
    assert (await _counts(db_session, uni))["enrolled"] == 2


@pytest.mark.asyncio
async def test_source_abc_example_reproduced(db_session):
    """EVID-020 §17: 45 interested -> 12 applications -> 8 offers -> 5 visa approvals -> 4 enrolled."""
    uni = await mk_university(db_session)
    org = await agency(db_session)
    records = await students(db_session, org, 45)
    for rec in records:
        await shortlist(db_session, rec, uni)
    for i, rec in enumerate(records[:12]):
        status = "enrolled" if i < 4 else "offer" if i < 8 else "university_selection"
        app = await application(db_session, uni, org=org, record=rec, status=status, submitted_on=date(2025, 3, 2))
        if i < 8:
            await history(db_session, app, "offer")
        if i < 5:
            await visa(db_session, app)
        if i < 4:
            await history(db_session, app, "enrolled", IN_MARCH, "status_tracking")
    counts = await _counts(db_session, uni)
    assert counts == {"interested": 45, "applications": 12, "offers": 8, "deposits": 0, "visas": 5, "enrolled": 4}


@pytest.mark.asyncio
async def test_universities_are_counted_separately(db_session):
    uni, other = await mk_university(db_session), await mk_university(db_session)
    await application(db_session, uni)
    await application(db_session, other)
    await application(db_session, other)
    result = await funnel_counts(db_session, [uni.id, other.id], MARCH_START, MARCH_END)
    assert (result[uni.id]["applications"], result[other.id]["applications"]) == (1, 2)


@pytest.mark.asyncio
async def test_constant_query_count(db_session):
    async def statements(n: int) -> int:
        unis = [await mk_university(db_session) for _ in range(n)]
        for u in unis:
            app = await application(db_session, u, status="enrolled")
            await history(db_session, app, "enrolled")
            await visa(db_session, app)
        seen = []
        sync_engine = engine.sync_engine
        listener = lambda *a, **k: seen.append(1)  # noqa: E731
        event.listen(sync_engine, "before_cursor_execute", listener)
        try:
            await funnel_counts(db_session, [u.id for u in unis], MARCH_START, MARCH_END)
        finally:
            event.remove(sync_engine, "before_cursor_execute", listener)
        return len(seen)

    assert await statements(1) == await statements(4)
