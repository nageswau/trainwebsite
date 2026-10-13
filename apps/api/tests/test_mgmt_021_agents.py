"""mgmt-021 -- GET /management/agents: the §17 agent network figures and the agency ranking (spec AN1-AN14).

The test database is shared and never truncated, so every figure is checked on agencies made by the test itself, over a fixed past period,
and the totals only for their internal consistency (they are the sum of the agency rows, AN12)."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.models import Payment, VisaCase
from app.services.bdm_appointments import IST
from tests.agn001_helpers import mk_active_org, uniq
from tests.agn004_helpers import mk_record, mk_staff
from tests.agn008_helpers import mk_application
from tests.agn018_helpers import mk_commission, mk_place
from tests.bdm001_helpers import login, make_user

pytestmark = pytest.mark.asyncio

URL = "/api/v1/management/agents"
PERIOD = {"from": "2024-06-01", "to": "2024-06-30"}
IN = datetime(2024, 6, 12, 11, 0, tzinfo=IST)
BEFORE = datetime(2024, 5, 31, 23, 30, tzinfo=IST)  # 30 minutes before the period's first IST day
OUT = datetime(2024, 7, 1, 0, 30, tzinfo=IST)  # 30 minutes after its last
COUNTS = ["staff", "students", "applications", "offers", "visa", "enrollments"]
MONEY = ["commission", "revenue"]
FIGURE_KEYS = ["agents", "new_agents", "active_agents", "inactive_agents", "staff", "students", "applications", "offers", "visa", "enrollments", "commission", "revenue"]


async def as_role(client, db, role: str):
    client.cookies.clear()
    user = await make_user(db, role, "global")
    await login(client, user)
    return user


async def read(client, **params) -> dict:
    response = await client.get(URL, params={**PERIOD, **params})
    assert response.status_code == 200, response.text
    return response.json()


def row(body: dict, org) -> dict:
    return next(r for r in body["agencies"] if r["id"] == str(org.id))


async def backdate(db, item, at: datetime) -> None:
    item.created_at = at
    await db.commit()


async def agency(db, *, status: str = "active", created: datetime = BEFORE) -> dict:
    world = await mk_active_org(db, name=f"AN {uniq()}")
    world["org"].status = status
    await backdate(db, world["org"], created)
    return world


async def paid(db, payer, application, amount: str, at: datetime, *, status: str = "paid") -> None:
    db.add(Payment(user_id=payer.id, division="overseas", reference_type="service_fee", reference_id=application.id, amount=Decimal(amount),
                   currency="INR", status=status, created_at=at, updated_at=at))  # fmt: skip
    await db.commit()


async def commission(db, agent, application, amount: float, at: datetime, *, status: str = "paid", currency: str = "INR") -> None:
    row = await mk_commission(db, agent=agent, application=application, status=status, amount=amount, currency=currency)
    row.paid_at = at if status == "paid" else None
    await db.commit()


async def producing_agency(db) -> dict:
    """Agency A, worked out by hand next to its rows (AN3-AN8)."""
    w = await agency(db, created=IN)  # new in the period
    master, org = w["master"], w["org"]
    await mk_staff(db, org, full_name="Staff One")
    await mk_staff(db, org, full_name="Staff Gone", active=False)  # AN4: not an active staff member
    place = await mk_place(db, university=f"Uni {uniq()}", country=f"Land {uniq()}")
    for status, at in (("active", IN), ("archived", IN), ("active", BEFORE)):  # AN5: two added in the period, any status
        await backdate(db, await mk_record(db, agent=master, full_name="Student", status=status), at)
    a1 = await mk_application(db, agent=master, university=place)
    a2 = await mk_application(db, agent=master, university=place, offer_type="conditional", offer_date=date(2024, 6, 10))
    a3 = await mk_application(db, agent=master, university=place, status="enrolled")
    a4 = await mk_application(db, agent=master, university=place, status="enrolled")
    a5 = await mk_application(db, agent=master, university=place, status="withdrawn")
    for app_row, at in ((a1, IN), (a2, IN), (a3, IN), (a4, BEFORE), (a5, IN)):
        await backdate(db, app_row, at)
    db.add(VisaCase(application_id=a3.id))
    await db.commit()
    # AN7: a3's paid commission in the period counts; a4's paid after it, a claimed one and a dollar one do not.
    await commission(db, master, a3, 5000.0, IN)
    await commission(db, master, a4, 700.0, OUT)
    await commission(db, master, a1, 300.0, IN, status="claimed")
    await commission(db, master, a2, 90.0, IN, currency="USD")
    # AN8: a paid service fee on a3 in the period; one after it and a pending one do not.
    await paid(db, master, a3, "10000.00", IN)
    await paid(db, master, a4, "2000.00", OUT)
    await paid(db, master, a1, "400.00", IN, status="pending")
    return w | {"apps": (a1, a2, a3, a4, a5)}


# Applications created in the period: a1 a2 a3 a5 (a5 withdrawn, still created, mgmt-024); offers a2 (offer recorded) + a3 (enrolled).
EXPECTED_A = {"status": "active", "new": True, "staff": 1, "students": 2, "applications": 4, "offers": 2, "visa": 1, "enrollments": 1,
              "commission": "5000.00", "revenue": "10000.00"}  # fmt: skip


# --- access (AN14) -----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["partner", "super_admin"])
async def test_operational_tier_reads_the_dashboard(client, db_session, role):
    await as_role(client, db_session, role)
    body = await read(client)
    assert body["from"] == PERIOD["from"] and body["to"] == PERIOD["to"]
    assert [f["key"] for f in body["figures"]] == FIGURE_KEYS
    assert body["money_visible"] is (role == "partner")


async def test_accountant_is_refused(client, db_session):
    await as_role(client, db_session, "accountant")
    response = await client.get(URL)
    assert response.status_code == 403
    assert response.json()["detail"] == "Operational access required"


@pytest.mark.parametrize("role", ["counselor", "overseas_admin", "agent"])
async def test_other_roles_are_refused(client, db_session, role):
    await as_role(client, db_session, role)
    assert (await client.get(URL)).status_code == 403


async def test_signed_out_is_401(client):
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401


# --- definitions (AN1-AN8, AN11) ---------------------------------------------------------------------------------------------------


async def test_an_agency_row_counts_its_period(client, db_session):
    a = await producing_agency(db_session)
    await as_role(client, db_session, "partner")
    got = row(await read(client), a["org"])
    assert {key: got[key] for key in EXPECTED_A} == EXPECTED_A
    assert got["name"] == a["org"].name and got["prefix"] == a["org"].prefix


async def test_suspended_agency_stays_and_pending_or_rejected_do_not(client, db_session):
    suspended = await agency(db_session, status="suspended")
    place = await mk_place(db_session, university=f"Uni {uniq()}", country=f"Land {uniq()}")
    await backdate(db_session, await mk_application(db_session, agent=suspended["master"], university=place, status="enrolled"), IN)
    pending, rejected = await agency(db_session, status="pending"), await agency(db_session, status="rejected")
    await as_role(client, db_session, "partner")
    body = await read(client)
    got = row(body, suspended["org"])
    assert (got["status"], got["new"], got["applications"], got["enrollments"]) == ("suspended", False, 1, 1)
    ids = {r["id"] for r in body["agencies"]}
    assert str(pending["org"].id) not in ids and str(rejected["org"].id) not in ids


async def test_totals_are_the_sum_of_the_agency_rows(client, db_session):
    await producing_agency(db_session)
    await agency(db_session, status="suspended", created=IN)
    await as_role(client, db_session, "partner")
    body = await read(client)
    rows, totals = body["agencies"], body["totals"]
    assert totals["agents"] == len(rows)
    assert totals["active_agents"] == sum(r["status"] == "active" for r in rows)
    assert totals["inactive_agents"] == sum(r["status"] == "suspended" for r in rows)
    assert totals["active_agents"] + totals["inactive_agents"] == totals["agents"]
    assert totals["new_agents"] == sum(r["new"] for r in rows)
    for key in COUNTS:
        assert totals[key] == sum(r[key] for r in rows), key
    for key in MONEY:
        assert Decimal(totals[key]) == sum(Decimal(r[key]) for r in rows), key
    chain = {step["key"]: step["value"] for step in body["chain"]}
    assert [step["key"] for step in body["chain"]] == ["agents", "staff", "students", "applications", "enrollments", "revenue"]
    assert chain["applications"] == totals["applications"] and chain["revenue"] == totals["revenue"]


async def test_ranking_by_enrollments_then_applications_then_students(client, db_session):
    await producing_agency(db_session)
    await as_role(client, db_session, "partner")
    rows = (await read(client))["agencies"]
    assert rows == sorted(rows, key=lambda r: (-r["enrollments"], -r["applications"], -r["students"], r["name"].casefold(), r["id"]))


async def test_an_agency_row_equals_the_applications_funnel_for_that_agency(client, db_session):
    a = await producing_agency(db_session)
    await as_role(client, db_session, "partner")
    got = row(await read(client), a["org"])
    funnel = await client.get("/api/v1/management/applications", params={"date_from": PERIOD["from"], "date_to": PERIOD["to"], "agency": str(a["org"].id)})
    stages = {s["key"]: s["value"] for s in funnel.json()["stages"]}
    assert (stages["created"], stages["offer"], stages["visa"], stages["enrollment"]) == (got["applications"], got["offers"], got["visa"], got["enrollments"])


# --- money tier (AN9) --------------------------------------------------------------------------------------------------------------


async def test_super_admin_gets_no_money(client, db_session):
    a = await producing_agency(db_session)
    await as_role(client, db_session, "super_admin")
    body = await read(client)
    assert body["totals"]["commission"] is None and body["totals"]["revenue"] is None
    assert all(r["commission"] is None and r["revenue"] is None for r in body["agencies"])
    assert "revenue" not in [step["key"] for step in body["chain"]]
    got = row(body, a["org"])
    assert {key: got[key] for key in COUNTS} == {key: EXPECTED_A[key] for key in COUNTS}


# --- period (AN13) -----------------------------------------------------------------------------------------------------------------


async def test_default_period_is_this_month(client, db_session):
    await as_role(client, db_session, "partner")
    body = (await client.get(URL)).json()
    assert body["from"].endswith("-01") and body["from"][:7] == body["to"][:7]


@pytest.mark.parametrize(
    ("params", "detail"),
    [({"from": "2024-06-30", "to": "2024-06-01"}, "start"), ({"from": "2023-01-01", "to": "2024-06-30"}, "366")],
)
async def test_bad_periods_are_422(client, db_session, params, detail):
    await as_role(client, db_session, "partner")
    response = await client.get(URL, params=params)
    assert response.status_code == 422
    assert detail in response.json()["detail"]


async def test_malformed_date_is_422(client, db_session):
    await as_role(client, db_session, "partner")
    assert (await client.get(URL, params={"from": "2024-13-01"})).status_code == 422
