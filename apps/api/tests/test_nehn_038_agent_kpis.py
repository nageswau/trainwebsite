"""nehn-038 (DEC-SCOPE-306) -- the agency dashboard's remaining KPIs: applications submitted, visa outcomes split, conversion, and
the optional referral-date filter. Every expected number is a hand count over the world below."""

from datetime import UTC, date, datetime

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn004_helpers import mk_record, mk_staff
from tests.agn008_helpers import mk_application, mk_school_student
from tests.agn012_helpers import mk_case
from tests.agn016_helpers import mk_task
from tests.agn017_helpers import set_org_status
from tests.agn018_helpers import DASHBOARD_API, mk_commission, mk_place

NEW = ("applications_submitted", "visa_applications", "visa_decisions", "visa_approvals", "visa_refusals", "visa_withdrawals", "conversions", "conversion_rate")
SUBMITTED = {"submitted_on": date(2026, 2, 1)}


async def _created(db, record, day: date):
    record.created_at = datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
    await db.commit()
    return record


@pytest_asyncio.fixture
async def world(db_session):
    db = db_session
    ctx = await mk_active_org(db, name=f"Kpi {uniq()}")
    other = await mk_active_org(db, name=f"Noise {uniq()}")
    master = ctx["master"]
    a = await mk_staff(db, ctx["org"], full_name="Staff A")
    b = await mk_staff(db, ctx["org"], full_name="Staff B")
    place = await mk_place(db, university="Kpi University", country="Kpiland")

    r1 = await _created(db, await mk_record(db, agent=master, full_name=f"R1 {uniq()}", assigned_member=a["member"]), date(2026, 1, 10))
    r2 = await _created(db, await mk_record(db, agent=master, full_name=f"R2 {uniq()}", assigned_member=a["member"]), date(2026, 3, 5))
    r3 = await _created(db, await mk_record(db, agent=master, full_name=f"R3 {uniq()}", assigned_member=b["member"]), date(2026, 3, 20))
    r4 = await _created(db, await mk_record(db, agent=master, full_name=f"R4 {uniq()}", assigned_member=b["member"], status="archived"), date(2026, 3, 21))
    await _created(db, await mk_record(db, agent=master, full_name=f"R5 {uniq()}"), date(2026, 5, 1))  # r5: unassigned, no application

    async def app(record, status, **fields):
        return await mk_application(db, agent=master, university=place, record=record, status=status, **fields)

    p1 = await app(r1, "enrolled", **SUBMITTED)
    p2 = await app(r1, "offer", **SUBMITTED)
    p3 = await app(r2, "visa_documentation", **SUBMITTED)
    p4 = await app(r2, "withdrawn", **SUBMITTED)  # withdrawn after submission: still submitted
    await app(r3, "enrolled")  # p5: enrolled, never marked submitted
    await app(r4, "enrolled", **SUBMITTED)  # p6: an archived student's application -- counted, but r4 is not a conversion
    await mk_application(db, agent=master, university=place, school_student=await mk_school_student(db), status="enrolled", **SUBMITTED)  # bridged: nowhere

    await mk_case(db, p1, status="checklist")  # a visa application, no decision yet
    await mk_case(db, p2, status="decision", decision="refused")
    await mk_case(db, p2, status="decision", decision="approved")  # approved wins over the earlier refusal
    await mk_case(db, p3, status="decision", decision="refused")
    await mk_case(db, p4, status="decision", decision="withdrawn")

    await mk_task(db, record=r1, author=master)  # an open task on a January student: a work queue, never date-filtered
    await mk_commission(db, agent=master, application=p1, status="paid", amount=900)

    nr = await mk_record(db, agent=other["master"], full_name=f"Noise {uniq()}")
    na = await mk_application(db, agent=other["master"], university=place, record=nr, status="enrolled", **SUBMITTED)
    await mk_case(db, na, status="decision", decision="refused")
    return ctx | {"a": a, "b": b, "other": other}


async def _get(email, **params):
    async with client_for(email) as c:
        response = await c.get(DASHBOARD_API, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _kpis(body):
    return {k: body[k] for k in NEW}


def _staff(body):
    return {r["name"]: (r["students"], r["applications"], r["enrollments"], r["conversions"], r["conversion_rate"]) for r in body["staff"]}


# Master, all time: active students r1 r2 r3 r5; submitted p1 p2 p3 p4 p6; visa p1 p2 p3 p4, decided p2 (approved) p3 (refused)
# p4 (withdrawn); converted r1 (p1) and r3 (p5) of 4 students.
MASTER = {"applications_submitted": 5, "visa_applications": 4, "visa_decisions": 3, "visa_approvals": 1, "visa_refusals": 1, "visa_withdrawals": 1, "conversions": 2, "conversion_rate": 50.0}
STAFF_A = {"applications_submitted": 4, "visa_applications": 4, "visa_decisions": 3, "visa_approvals": 1, "visa_refusals": 1, "visa_withdrawals": 1, "conversions": 1, "conversion_rate": 50.0}
STAFF_B = {"applications_submitted": 1, "visa_applications": 0, "visa_decisions": 0, "visa_approvals": 0, "visa_refusals": 0, "visa_withdrawals": 0, "conversions": 1, "conversion_rate": 100.0}
# March 2026 cohort: r2 r3 r4 (r4 archived). Submitted p3 p4 p6; decided p3 (refused) p4 (withdrawn); converted r3 of r2 r3.
MARCH = {"applications_submitted": 3, "visa_applications": 2, "visa_decisions": 2, "visa_approvals": 0, "visa_refusals": 1, "visa_withdrawals": 1, "conversions": 1, "conversion_rate": 50.0}


@pytest.mark.asyncio
async def test_master_new_kpis_equal_hand_counts(world):
    body = await _get(world["master"].email)
    assert _kpis(body) == MASTER
    assert body["date_from"] is None and body["date_to"] is None
    assert _staff(body) == {"Staff A": (2, 3, 1, 1, 50.0), "Staff B": (1, 2, 2, 1, 100.0)}


@pytest.mark.asyncio
async def test_visa_outcomes_sum_to_decided(world):
    for email in (world["master"].email, world["a"]["user"].email):
        body = await _get(email)
        assert body["visa_approvals"] + body["visa_refusals"] + body["visa_withdrawals"] == body["visa_decisions"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("who", "expected"), [("a", STAFF_A), ("b", STAFF_B)])
async def test_staff_see_only_their_own_figures(world, who, expected):
    body = await _get(world[who]["user"].email)
    assert body["scope"] == "own" and _kpis(body) == expected and body["staff"] is None


@pytest.mark.asyncio
async def test_date_filter_applies_to_every_kpi_tile(world):
    unfiltered = await _get(world["master"].email)
    body = await _get(world["master"].email, date_from="2026-03-01", date_to="2026-03-31")
    assert body["date_from"] == "2026-03-01" and body["date_to"] == "2026-03-31"
    assert _kpis(body) == MARCH
    # offers p3 p5 p6: a later stage implies the offer (O5); p4 was withdrawn with none.
    assert (body["students"], body["applications"], body["offers"], body["enrollments"]) == (2, 3, 3, 2)
    assert body["by_country"] == {"items": [{"label": "Kpiland", "count": 3}], "other": 0}
    assert _staff(body) == {"Staff A": (1, 1, 0, 0, 0.0), "Staff B": (1, 2, 2, 1, 100.0)}
    assert body["unassigned_students"] == 0
    # Work queues and the commission ledger are current figures, not cohort figures (DEC-SCOPE-306 D2).
    for key in ("pending_documents", "pending_actions", "commission"):
        assert body[key] == unfiltered[key], key


@pytest.mark.asyncio
async def test_open_ended_ranges(world):
    since = await _get(world["master"].email, date_from="2026-03-21")  # r4 (archived) and r5
    assert (since["students"], since["conversions"], since["conversion_rate"], since["applications_submitted"]) == (1, 0, 0.0, 1)
    until = await _get(world["master"].email, date_to="2026-01-31")  # r1 only
    assert (until["students"], until["conversions"], until["applications_submitted"], until["visa_approvals"]) == (1, 1, 2, 1)


@pytest.mark.asyncio
async def test_staff_filter_stays_in_own_scope(world):
    body = await _get(world["a"]["user"].email, date_from="2026-03-01", date_to="2026-03-31", scope="agency")
    assert body["scope"] == "own" and (body["students"], body["applications_submitted"], body["conversions"]) == (1, 2, 0)


@pytest.mark.asyncio
async def test_empty_agency_rate_is_null(db_session):
    ctx = await mk_active_org(db_session)
    body = await _get(ctx["master"].email)
    assert _kpis(body) == {**dict.fromkeys(NEW, 0), "conversion_rate": None}
    filtered = await _get(ctx["master"].email, date_from="2026-01-01")
    assert filtered["conversion_rate"] is None and filtered["staff"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"date_from": "2026-03-31", "date_to": "2026-03-01"}, "date_to must be on or after date_from"),
        ({"date_from": "03/01/2026"}, "date_from"),
        ({"date_to": "9999-12-31"}, "date_to must be before 9999-12-31"),
    ],
)
async def test_bad_ranges_are_422(world, params, message):
    async with client_for(world["master"].email) as c:
        response = await c.get(DASHBOARD_API, params=params)
    assert response.status_code == 422 and message in response.text


@pytest.mark.asyncio
async def test_guards_run_before_date_validation(db_session, client):
    bad = {"date_from": "2026-03-31", "date_to": "2026-03-01"}
    assert (await client.get(DASHBOARD_API, params=bad)).status_code == 401
    counselor = await mk_user(db_session, role="counselor", division="overseas")
    async with client_for(counselor.email) as c:
        assert (await c.get(DASHBOARD_API, params=bad)).status_code == 403
    ctx = await mk_active_org(db_session)
    async with client_for(ctx["master"].email) as c:
        await set_org_status(db_session, ctx["org"], "suspended")
        assert (await c.get(DASHBOARD_API, params=bad)).status_code == 403


@pytest.mark.asyncio
async def test_other_agency_never_counted(world):
    body = await _get(world["other"]["master"].email)
    assert (body["applications_submitted"], body["visa_refusals"], body["conversions"], body["students"]) == (1, 1, 1, 1)
