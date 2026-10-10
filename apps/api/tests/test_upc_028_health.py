"""upc-028 -- the §30 partnership health score (spec HS3-HS8; AC1-AC4, AC7). Each test builds a fresh university and scores it as of
30 Jun 2023 (IST), so the trailing windows (365 / 90 days) hold only this file's rows."""

import itertools
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event

from app.core.database import engine
from app.models import UniversityCall, UniversityCommissionReceipt, UniversityMeeting, UniversityMessage
from app.services.partnership_metrics import HEALTH_FACTORS, band, health, health_score
from tests.agn003_helpers import mk_university
from tests.upc018_helpers import application, history, visa
from tests.upc019_helpers import agreement, enrolled, staff, term, tuition_course

NOW = datetime(2023, 6, 30, 6, tzinfo=UTC)  # 30 Jun 2023, 11:30 IST
IN_WINDOW = datetime(2023, 3, 10, 6, tzinfo=UTC)
RECENT = datetime(2023, 6, 1, 6, tzinfo=UTC)  # inside the last 90 days
FULL = {f.key: 1.0 for f in HEALTH_FACTORS if f.tracked}


async def _health(db, uni) -> dict:
    return (await health(db, [uni.id], NOW))[uni.id]


def _factor(result: dict, key: str) -> dict:
    return next(f for f in result["factors"] if f["key"] == key)


async def _meeting(db, uni, by, *, completed_at: datetime | None) -> None:
    db.add(
        UniversityMeeting(
            code=f"H-{uuid.uuid4().hex[:10]}", university_id=uni.id, meeting_type="introduction", starts_at=completed_at or RECENT, mode="online",
            responsible_user_id=by.id, created_by_user_id=by.id, status="completed" if completed_at else "scheduled", completed_at=completed_at,
            completed_by_user_id=by.id if completed_at else None,
        )
    )  # fmt: skip
    await db.commit()


async def _message(db, uni, by, sent_at: datetime, *, channel: str = "whatsapp", delivery_status: str | None = None) -> None:
    email = channel == "email"
    db.add(UniversityMessage(
        university_id=uni.id, sender_user_id=by.id, channel=channel, body="Hello", subject="Hi" if email else None,
        delivery_status=(delivery_status or "sent") if email else None, sent_at=sent_at,
    ))  # fmt: skip
    await db.commit()


async def _call(db, uni, by, at: datetime, *, direction: str = "incoming", outcome: str = "connected") -> None:
    db.add(UniversityCall(university_id=uni.id, caller_user_id=by.id, occurred_at=at, direction=direction, outcome=outcome))
    await db.commit()


# --- the maths (HS5-HS7) ------------------------------------------------------------------------------------------------------------
def test_factor_catalogue_weights_sum_to_100_and_satisfaction_is_not_tracked():
    assert [f.key for f in HEALTH_FACTORS] == [
        "applications", "offers", "visa_success", "enrolments", "commission", "response_time", "meetings", "agreement", "satisfaction",
    ]  # fmt: skip
    assert sum(f.weight for f in HEALTH_FACTORS) == 100
    satisfaction = HEALTH_FACTORS[-1]
    assert (satisfaction.tracked, satisfaction.weight) == (False, 0)


@pytest.mark.parametrize(
    ("score", "expected"), [(100, "excellent"), (92, "excellent"), (80, "excellent"), (79, "good"), (60, "good"), (59, "needs_attention"), (48, "needs_attention"), (0, "needs_attention")]
)
def test_bands(score, expected):
    assert band(score) == expected


def test_full_marks_score_100_with_the_weights_as_points():
    score, points = health_score(FULL)
    assert score == 100
    assert points == {f.key: f.weight if f.tracked else None for f in HEALTH_FACTORS}


def test_zero_counts_are_data_and_score_zero():
    score, points = health_score(dict.fromkeys(FULL, 0.0))
    assert score == 0 and all(p in (0, None) for p in points.values())


def test_a_factor_without_data_shares_its_weight_out():
    score, points = health_score(FULL | {"offers": None, "visa_success": None})
    assert score == 100 and points["offers"] is None and points["visa_success"] is None
    assert sum(p for p in points.values() if p) == 100


def test_the_breakdown_always_sums_to_the_score():
    """AC1, over awkward fractions and every pattern of missing ratios."""
    grid = (0.0, 1 / 3, 0.5, 2 / 3, 0.8333, 1.0)
    for combo in itertools.product(grid, repeat=3):
        for missing in ((), ("offers",), ("commission", "response_time"), ("offers", "visa_success", "commission", "response_time")):
            values = FULL | {"applications": combo[0], "meetings": combo[1], "agreement": combo[2]} | dict.fromkeys(missing)
            score, points = health_score(values)
            assert sum(p for p in points.values() if p is not None) == score, values
            assert 0 <= score <= 100


def test_a_value_outside_0_1_is_clamped():
    assert health_score(FULL | {"applications": 3.0})[0] == 100
    assert health_score(dict.fromkeys(FULL, -1.0))[0] == 0


# --- the factors from data (HS3, HS4) ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_new_partner_with_no_data_is_insufficient(db_session):
    result = await _health(db_session, await mk_university(db_session))
    assert (result["score"], result["band"], result["band_label"]) == (None, "insufficient_data", "Insufficient data")
    assert result["as_of"] == date(2023, 6, 30)
    assert _factor(result, "satisfaction") == {
        "key": "satisfaction", "label": "Student satisfaction", "tracked": False, "has_data": False, "measure": "Not tracked", "weight": 0, "points": None, "value": None,
    }  # fmt: skip


@pytest.mark.asyncio
async def test_applications_offers_and_enrolments_over_the_last_365_days(db_session):
    uni = await mk_university(db_session)
    for i in range(10):
        await application(db_session, uni, when=IN_WINDOW, **({"status": "offer", "offer_type": "conditional", "offer_date": date(2023, 3, 20)} if i < 5 else {}))
    await application(db_session, uni, when=NOW - timedelta(days=400))  # outside the window
    for _ in range(3):
        app = await application(db_session, uni, when=IN_WINDOW, status="enrolled")
        await history(db_session, app, "enrolled", IN_WINDOW)
    result = await _health(db_session, uni)
    assert _factor(result, "applications")["value"] == pytest.approx(13 / 20)
    assert _factor(result, "applications")["measure"] == "13 in the last 12 months"
    assert _factor(result, "offers")["value"] == pytest.approx(8 / 13)  # F6: an enrolment passed the offer stage
    assert _factor(result, "enrolments")["value"] == pytest.approx(3 / 10)
    assert result["score"] is not None


@pytest.mark.asyncio
async def test_offers_without_applications_have_no_data(db_session):
    uni = await mk_university(db_session)
    await _meeting(db_session, uni, await staff(db_session), completed_at=RECENT)
    offers = _factor(await _health(db_session, uni), "offers")
    assert (offers["has_data"], offers["points"], offers["measure"]) == (False, None, "No applications in the last 12 months")


@pytest.mark.asyncio
async def test_visa_success_is_approved_over_approved_plus_refused_in_the_window(db_session):
    uni = await mk_university(db_session)
    for decision in ("approved", "approved", "approved", "refused", "withdrawn"):
        await visa(db_session, await application(db_session, uni, when=NOW - timedelta(days=500)), decision, IN_WINDOW)
    await visa(db_session, await application(db_session, uni, when=NOW - timedelta(days=500)), "approved", NOW - timedelta(days=400))
    result = _factor(await _health(db_session, uni), "visa_success")
    assert result["value"] == pytest.approx(0.75) and result["measure"] == "3 of 4 decisions approved (75%)"


@pytest.mark.asyncio
async def test_meetings_completed_in_the_last_90_days(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    await _meeting(db_session, uni, by, completed_at=RECENT)
    await _meeting(db_session, uni, by, completed_at=NOW - timedelta(days=10))
    await _meeting(db_session, uni, by, completed_at=NOW - timedelta(days=100))  # too old
    await _meeting(db_session, uni, by, completed_at=None)  # scheduled
    result = _factor(await _health(db_session, uni), "meetings")
    assert result["value"] == pytest.approx(2 / 3) and result["measure"] == "2 completed in the last 90 days"


@pytest.mark.parametrize(
    ("status", "expiry", "value", "measure"),
    [("active", date(2026, 1, 1), 1.0, "Active"), ("signed", date(2026, 1, 1), 1.0, "Signed"), ("active", date(2023, 8, 1), 0.5, "Expiring"),
     ("active", date(2023, 5, 1), 0.0, "Expired"), ("draft", date(2026, 1, 1), 0.0, "Draft")],
)  # fmt: skip
@pytest.mark.asyncio
async def test_agreement_status(db_session, status, expiry, value, measure):
    uni = await mk_university(db_session)
    await agreement(db_session, uni, await staff(db_session), status=status, start=date(2022, 1, 1), expiry=expiry)
    result = _factor(await _health(db_session, uni), "agreement")
    assert (result["value"], result["measure"]) == (value, measure)


@pytest.mark.asyncio
async def test_the_best_agreement_counts_and_none_is_zero(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    await _meeting(db_session, uni, by, completed_at=RECENT)
    assert _factor(await _health(db_session, uni), "agreement").items() >= {"value": 0.0, "measure": "No agreement", "has_data": True}.items()
    await agreement(db_session, uni, by, status="active", start=date(2020, 1, 1), expiry=date(2022, 1, 1))
    await agreement(db_session, uni, by, status="active", start=date(2022, 1, 2), expiry=date(2023, 8, 1))
    assert _factor(await _health(db_session, uni), "agreement")["measure"] == "Expiring"


@pytest.mark.asyncio
async def test_response_time_is_the_median_wait_for_the_next_contact_interaction(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    t1, t2, t3 = NOW - timedelta(days=60), NOW - timedelta(days=40), NOW - timedelta(days=20)
    await _message(db_session, uni, by, t1)
    await _call(db_session, uni, by, t1 + timedelta(days=1))  # incoming: 1 day
    await _message(db_session, uni, by, t2, channel="email")
    await _call(db_session, uni, by, t2 + timedelta(days=2), direction="outgoing", outcome="no_answer")  # not a reply
    await _call(db_session, uni, by, t2 + timedelta(days=4), direction="outgoing", outcome="connected")  # 4 days
    await _message(db_session, uni, by, t3)  # unanswered: 20 days until now
    await _message(db_session, uni, by, t3, channel="email", delivery_status="failed")  # never reached the contact
    await _message(db_session, uni, by, NOW - timedelta(days=120))  # outside the 90 days
    result = _factor(await _health(db_session, uni), "response_time")
    assert result["value"] == pytest.approx((14 - 4) / 12)
    assert result["measure"] == "Median 4 days to a reply (3 messages)"


@pytest.mark.asyncio
async def test_a_completed_meeting_is_a_reply_and_fast_replies_score_full(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    await _message(db_session, uni, by, RECENT)
    await _meeting(db_session, uni, by, completed_at=RECENT + timedelta(hours=12))
    assert _factor(await _health(db_session, uni), "response_time")["value"] == 1.0


@pytest.mark.asyncio
async def test_no_messages_means_no_response_time_data(db_session):
    uni = await mk_university(db_session)
    await _meeting(db_session, uni, await staff(db_session), completed_at=RECENT)
    result = _factor(await _health(db_session, uni), "response_time")
    assert (result["has_data"], result["measure"]) == (False, "No messages in the last 90 days")


@pytest.mark.asyncio
async def test_commission_is_the_collection_rate_of_expected(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    course = await tuition_course(db_session, uni)
    await term(db_session, await agreement(db_session, uni, by, start=date(2022, 1, 1), expiry=date(2026, 1, 1)), by)
    for _ in range(2):  # 2 x 15% of GBP 18,000 = GBP 5,400 expected
        await enrolled(db_session, uni, course, at=IN_WINDOW)
    db_session.add(UniversityCommissionReceipt(university_id=uni.id, amount="2700", currency="GBP", received_on=date(2023, 4, 1), reference="H-1", created_by_user_id=by.id))
    await db_session.commit()
    result = _factor(await _health(db_session, uni), "commission")
    assert result["value"] == pytest.approx(0.5) and result["measure"] == "50% of expected commission received"


@pytest.mark.asyncio
async def test_a_quiet_old_partner_scores_low_rather_than_insufficient(db_session):
    uni = await mk_university(db_session)
    await agreement(db_session, uni, await staff(db_session), status="active", start=date(2019, 1, 1), expiry=date(2022, 1, 1))
    result = await _health(db_session, uni)
    assert (result["score"], result["band"], result["band_label"]) == (0, "needs_attention", "Needs attention")


@pytest.mark.asyncio
async def test_the_breakdown_sums_to_the_score_from_data(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    await agreement(db_session, uni, by, status="active", start=date(2022, 1, 1), expiry=date(2023, 8, 1))
    await _meeting(db_session, uni, by, completed_at=RECENT)
    await application(db_session, uni, when=IN_WINDOW)
    result = await _health(db_session, uni)
    assert sum(f["points"] for f in result["factors"] if f["points"] is not None) == result["score"]
    assert result["band"] == band(result["score"])


@pytest.mark.asyncio
async def test_constant_query_count(db_session):
    async def statements(n: int) -> int:
        by = await staff(db_session)
        unis = [await mk_university(db_session) for _ in range(n)]
        for u in unis:
            await _meeting(db_session, u, by, completed_at=RECENT)
            await _message(db_session, u, by, RECENT)
            await agreement(db_session, u, by, start=date(2022, 1, 1), expiry=date(2026, 1, 1))
        seen = []
        listener = lambda *a, **k: seen.append(1)  # noqa: E731
        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            await health(db_session, [u.id for u in unis], NOW)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        return len(seen)

    assert await statements(1) == await statements(4)


@pytest.mark.asyncio
async def test_no_universities_no_queries(db_session):
    assert await health(db_session, [], NOW) == {}
