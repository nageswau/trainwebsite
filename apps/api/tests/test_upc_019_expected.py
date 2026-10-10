"""upc-019 -- Commission Expected (spec CL1-CL8, AC1). Each test builds a fresh university, so no other test's rows are counted."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.core.database import engine
from app.services.university_commission import currency_sums, expected_rows
from tests.agn003_helpers import mk_university
from tests.upc019_helpers import agreement, approved_visa, enrolled, staff, term, tuition_course


async def _rows(db, university) -> list[dict]:
    return (await expected_rows(db, [university.id])).get(university.id, [])


async def _one(db, university) -> dict:
    (row,) = await _rows(db, university)
    return row


@pytest.mark.asyncio
async def test_ac1_fifteen_percent_of_18000_gbp_is_2700_gbp(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    c = await tuition_course(db_session, uni)
    t = await term(db_session, await agreement(db_session, uni, by), by)
    app = await enrolled(db_session, uni, c, application_reference="UNI-REF-1")
    row = await _one(db_session, uni)
    assert row["id"] == app.id and row["status"] == "counted" and row["term_id"] == t.id
    assert row["amount"] == Decimal("2700.00") and row["currency"] == "GBP" and row["enrolled_on"] == date(2026, 1, 15)
    assert row["course"] == "MSc Data Science" and row["intake"] == "Jan 2026" and row["reference"] == "UNI-REF-1"
    assert currency_sums([row]) == {"GBP": Decimal("2700.00")}


@pytest.mark.asyncio
async def test_only_enrolled_applications_are_listed(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    c = await tuition_course(db_session, uni)
    await term(db_session, await agreement(db_session, uni, by), by)
    await enrolled(db_session, uni, c, at=None, status="visa_documentation")
    await enrolled(db_session, uni, c, at=None, status="withdrawn")
    assert await _rows(db_session, uni) == []


@pytest.mark.asyncio
async def test_cl1_visa_and_enrolment_needs_an_approved_visa(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    c = await tuition_course(db_session, uni)
    await term(db_session, await agreement(db_session, uni, by), by, trigger="visa_and_enrolment")
    app = await enrolled(db_session, uni, c)
    await approved_visa(db_session, app, decision="refused")
    row = await _one(db_session, uni)
    assert row["status"] == "awaiting_visa" and row["amount"] is None
    await approved_visa(db_session, app)
    assert (await _one(db_session, uni))["status"] == "counted"


@pytest.mark.asyncio
async def test_cl1_tuition_paid_is_not_tracked(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    c = await tuition_course(db_session, uni)
    await term(db_session, await agreement(db_session, uni, by), by, trigger="tuition_paid")
    await enrolled(db_session, uni, c)
    row = await _one(db_session, uni)
    assert row["status"] == "trigger_not_tracked" and row["amount"] is None and currency_sums([row]) == {}


@pytest.mark.asyncio
async def test_cl3_enrolment_day_falls_back_to_confirmation_then_recorded_date(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    c = await tuition_course(db_session, uni)
    await term(db_session, await agreement(db_session, uni, by), by)
    await enrolled(db_session, uni, c, at=None, enrollment_confirmed_at=datetime(2026, 2, 1, 20, tzinfo=UTC))  # 2 Feb 01:30 IST
    await enrolled(db_session, uni, c, at=None, enrollment_date=date(2026, 3, 5))
    await enrolled(db_session, uni, c, at=None)
    days = sorted(((r["enrolled_on"], r["status"]) for r in await _rows(db_session, uni)), key=lambda x: (x[0] is None, x[0]))
    assert days == [(date(2026, 2, 2), "counted"), (date(2026, 3, 5), "counted"), (None, "date_unknown")]


@pytest.mark.asyncio
async def test_cl4_agreement_must_be_signed_and_cover_the_enrolment_day(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    c = await tuition_course(db_session, uni)
    await term(db_session, await agreement(db_session, uni, by, status="approved"), by)  # not signed: never applies
    await term(db_session, await agreement(db_session, uni, by, start=date(2026, 2, 1), expiry=date(2027, 2, 1)), by)  # starts after
    await enrolled(db_session, uni, c)
    assert (await _one(db_session, uni))["status"] == "no_term"
    later = await term(db_session, await agreement(db_session, uni, by, status="renewed", start=date(2025, 1, 1), expiry=date(2026, 1, 15)), by, percent="10")
    row = await _one(db_session, uni)  # a renewed agreement still covered its own period; the expiry day is inclusive
    assert row["status"] == "counted" and row["term_id"] == later.id and row["amount"] == Decimal("1800.00")


@pytest.mark.asyncio
async def test_cl5_a_term_naming_the_programme_beats_an_all_programmes_term_and_ties_go_to_the_newest(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    c, other = await tuition_course(db_session, uni), await tuition_course(db_session, uni, title="MBA")
    a = await agreement(db_session, uni, by)
    await term(db_session, a, by, percent="10", when=datetime(2025, 7, 1, tzinfo=UTC))
    await term(db_session, a, by, percent="30", courses=[other])  # another programme: never applies here
    named = await term(db_session, a, by, percent="20", courses=[c], when=datetime(2025, 7, 2, tzinfo=UTC))
    await enrolled(db_session, uni, c)
    assert (await _one(db_session, uni))["term_id"] == named.id
    newer = await term(db_session, a, by, percent="25", courses=[c], when=datetime(2025, 8, 1, tzinfo=UTC))
    row = await _one(db_session, uni)
    assert row["term_id"] == newer.id and row["amount"] == Decimal("4500.00")


@pytest.mark.asyncio
async def test_cl6_a_country_restricted_term_never_matches(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    c = await tuition_course(db_session, uni)
    a = await agreement(db_session, uni, by)
    await term(db_session, a, by, percent="50", courses=[c], countries=[uni.country_id])
    await enrolled(db_session, uni, c)
    assert (await _one(db_session, uni))["status"] == "no_term"
    general = await term(db_session, a, by, percent="10")
    assert (await _one(db_session, uni))["term_id"] == general.id


@pytest.mark.asyncio
async def test_cl8_fixed_uses_the_term_currency_and_percent_the_course_currency(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    usd = await tuition_course(db_session, uni, amount="33333.33", currency="USD", title="MS CS")
    gbp = await tuition_course(db_session, uni, title="MBA")
    a = await agreement(db_session, uni, by)
    await term(db_session, a, by, percent="12.5", currency="GBP", courses=[usd])  # % of USD tuition stays USD
    await term(db_session, a, by, percent=None, fixed="1500", currency="AUD", courses=[gbp])
    await enrolled(db_session, uni, usd)
    await enrolled(db_session, uni, gbp)
    await enrolled(db_session, uni, gbp)
    rows = await _rows(db_session, uni)
    assert currency_sums(rows) == {"USD": Decimal("4166.67"), "AUD": Decimal("3000.00")}  # 4166.66625 rounds half-up


@pytest.mark.asyncio
async def test_cl8_percent_without_course_or_tuition_is_tuition_unknown_but_fixed_still_counts(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    no_fee = await tuition_course(db_session, uni, amount=None, currency=None)
    a = await agreement(db_session, uni, by)
    await term(db_session, a, by)
    await enrolled(db_session, uni, no_fee)
    await enrolled(db_session, uni, None)
    assert {r["status"] for r in await _rows(db_session, uni)} == {"tuition_unknown"}
    await term(db_session, a, by, percent=None, fixed="900", currency="EUR", when=datetime(2030, 1, 1, tzinfo=UTC))  # newest all-programmes
    assert currency_sums(await _rows(db_session, uni)) == {"EUR": Decimal("1800.00")}


@pytest.mark.asyncio
async def test_currency_sums_filter_by_enrolment_day(db_session):
    uni, by = await mk_university(db_session), await staff(db_session)
    c = await tuition_course(db_session, uni)
    await term(db_session, await agreement(db_session, uni, by), by)
    await enrolled(db_session, uni, c)
    await enrolled(db_session, uni, c, at=datetime(2026, 2, 10, 6, tzinfo=UTC))
    rows = await _rows(db_session, uni)
    assert currency_sums(rows, date(2026, 1, 1), date(2026, 1, 31)) == {"GBP": Decimal("2700.00")}
    assert currency_sums(rows) == {"GBP": Decimal("5400.00")}


@pytest.mark.asyncio
async def test_query_count_is_constant(db_session):
    unis, by = [await mk_university(db_session) for _ in range(3)], await staff(db_session)
    for uni in unis:
        c = await tuition_course(db_session, uni)
        await term(db_session, await agreement(db_session, uni, by), by)
        for _ in range(3):
            await enrolled(db_session, uni, c)
    statements: list[str] = []

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", count)
    try:
        found = await expected_rows(db_session, [u.id for u in unis])
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count)
    assert sum(len(v) for v in found.values()) == 9 and len(statements) <= 2
