"""mgmt-018 -- GET /management/counseling: the §13 counseling KPIs per counselor and in total (spec CS1-CS12).

The test database is shared and never truncated, so every figure is checked on counselors made by the test itself, over a fixed past
period, and the totals only for their internal consistency (they are the sum of the rows)."""

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from app.models import Appointment, AuditLog, Enquiry, LeadCall, LeadStageHistory, Payment
from app.services.bdm_appointments import IST
from app.services.bdm_performance import _instants
from app.services.telecaller_metrics import conversions_by_user
from tests.bdm001_helpers import login, make_user

pytestmark = pytest.mark.asyncio

URL = "/api/v1/management/counseling"
PERIOD = {"from": "2024-06-01", "to": "2024-06-30"}
IN = datetime(2024, 6, 12, 11, 0, tzinfo=IST)
BEFORE = datetime(2024, 5, 20, 11, 0, tzinfo=IST)
OUT = datetime(2024, 7, 1, 0, 30, tzinfo=IST)  # 30 minutes after the period's last IST day
KEYS = ["leads_assigned", "calls", "counseling_sessions", "follow_ups", "conversions", "revenue", "conversion_pct"]
COUNTS = ["leads_assigned", "calls", "counseling_sessions", "follow_ups", "conversions"]


async def as_role(client, db, role: str):
    client.cookies.clear()
    user = await make_user(db, role, "global")
    await login(client, user)
    return user


async def read(client, **params) -> dict:
    response = await client.get(URL, params={**PERIOD, **params})
    assert response.status_code == 200, response.text
    return response.json()


def row(body: dict, user) -> dict:
    return next(r for r in body["counselors"] if r["id"] == str(user.id))


# --- builders: every row is backdated into (or out of) the period ------------------------------------------------------------------


async def lead(db, counselor, *, status: str = "follow_up", telecaller=None) -> Enquiry:
    row = Enquiry(division=counselor.division, name=f"Lead {uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:8]}@example.local",
                  phone="9876543210", subject="Course", message="", source="website", status=status, owner_id=counselor.id,
                  telecaller_user_id=telecaller.id if telecaller else None)  # fmt: skip
    db.add(row)
    await db.commit()
    return row


async def handed(db, lead_row: Enquiry, counselor, at: datetime) -> None:
    db.add(AuditLog(user_id=None, action="lead.handover", entity_type="enquiry", entity_id=str(lead_row.id), created_at=at,
                    metadata_json={"counselor_id": str(counselor.id), "from_counselor_id": None}))  # fmt: skip
    await db.commit()


async def converted(db, lead_row: Enquiry, at: datetime, *, still: bool = True):
    """The lead's conversion recorded at `at` (T5), linked to a fresh student; `still=False` moves it back (HO2)."""
    student = await make_user(db, f"{lead_row.division}_student", lead_row.division)
    db.add(LeadStageHistory(lead_id=lead_row.id, from_stage="application_enrollment", to_stage="converted", event="converted", created_at=at))
    if still:
        lead_row.status = "converted"
        lead_row.converted_user_id, lead_row.converted_at, lead_row.converted_by_user_id = student.id, at, student.id
    await db.commit()
    return student


async def session(db, counselor, at: datetime, *, lead_row=None, student=None, status: str = "completed") -> None:
    db.add(Appointment(division=counselor.division, lead_id=lead_row.id if lead_row else None, student_id=student.id if student else None,
                       staff_id=counselor.id, scheduled_at=at, appointment_type="Career Counseling", mode="Online", status=status))  # fmt: skip
    await db.commit()


async def called(db, counselor, lead_row: Enquiry, at: datetime) -> None:
    """ccrm-004 (DEC-SCOPE-259 LG6): a call logged on a lead, by the counselor or anyone else."""
    db.add(LeadCall(lead_id=lead_row.id, caller_user_id=counselor.id, occurred_at=at, duration_seconds=60, call_type="outgoing", outcome="interested"))
    await db.commit()


async def paid(db, student, amount: str, at: datetime, *, currency: str = "INR", status: str = "paid") -> None:
    db.add(Payment(user_id=student.id, division=student.division, reference_type="enrollment_fee", amount=Decimal(amount), currency=currency,
                   status=status, created_at=at, updated_at=at))  # fmt: skip
    await db.commit()


# --- access (CS11) -----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["partner", "super_admin"])
async def test_the_operational_tier_reads_it(client, db_session, role):
    await as_role(client, db_session, role)
    body = await read(client)
    assert [f["key"] for f in body["figures"]] == KEYS
    calls = next(f for f in body["figures"] if f["key"] == "calls")
    assert calls["tracked"] is True  # ccrm-004 LG6: counselors log calls
    assert calls["definition"] == "Calls the counselor logged in the period."
    assert body["from"] == PERIOD["from"] and body["to"] == PERIOD["to"] and body["as_of"]
    assert body["revenue_visible"] is (role == "partner")


@pytest.mark.parametrize(("role", "detail"), [("accountant", "Operational access required"), ("counselor", "Management access required"),
                                              ("telecaller_manager", "Management access required")])  # fmt: skip
async def test_everyone_else_is_refused(client, db_session, role, detail):
    await as_role(client, db_session, role)
    response = await client.get(URL)
    assert (response.status_code, response.json()["detail"]) == (403, detail)


async def test_signed_out_is_401(client):
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401


# --- period (CS2) ------------------------------------------------------------------------------------------------------------------


async def test_the_default_is_this_ist_month(client, db_session):
    await as_role(client, db_session, "partner")
    body = (await client.get(URL)).json()
    today = datetime.now(IST).date()
    assert body["from"] == today.replace(day=1).isoformat() and body["from"] <= body["to"]


@pytest.mark.parametrize("params", [{"from": "2024-06-30", "to": "2024-06-01"}, {"from": "2023-01-01", "to": "2024-06-30"}])
async def test_a_bad_period_is_422(client, db_session, params):
    await as_role(client, db_session, "partner")
    assert (await client.get(URL, params=params)).status_code == 422


# --- the figures (CS3-CS9) ---------------------------------------------------------------------------------------------------------


async def test_each_counselors_figures(client, db_session):
    db = db_session
    a, b = await make_user(db, "counselor", "it"), await make_user(db, "counselor", "overseas")
    # CS3: lead1 handed over twice in the period counts once; lead2 was handed over after it; lead3 before it.
    lead1, lead2, lead3 = await lead(db, a), await lead(db, a), await lead(db, a)
    await handed(db, lead1, a, IN)
    await handed(db, lead1, a, IN.replace(day=14))
    await handed(db, lead2, a, OUT)
    await handed(db, lead3, a, BEFORE)
    # CS7: lead1 and lead3 converted in the period (both A's); a lead converted then unlinked never counts.
    s1, s3 = await converted(db, lead1, IN), await converted(db, lead3, IN)
    await converted(db, await lead(db, a), IN, still=False)
    # CS5 / CS6: sessions completed in the period; a repeat with the same lead or student is a follow-up -- with this counselor only.
    x, y = await make_user(db, "it_student", "it"), await make_user(db, "it_student", "it")
    await session(db, a, BEFORE, lead_row=lead1)
    await session(db, a, IN.replace(day=5), lead_row=lead1)  # follow-up: A completed one with lead1 in May
    await session(db, b, IN.replace(day=1), student=x)  # B's session does not make A's first one with x a follow-up
    await session(db, a, IN.replace(day=10), student=x)
    await session(db, a, IN.replace(day=20), student=x)  # follow-up
    await session(db, a, IN.replace(day=11), student=y, status="cancelled")
    await session(db, a, OUT, student=y)
    # CS8: counted rupee payments in the period by the students of A's converted leads.
    # ccrm-004 LG6: the calls A logged in the period; a telecaller's call on A's lead and A's call after the period do not count.
    await called(db, a, lead1, IN)
    await called(db, a, lead2, IN.replace(day=20))
    await called(db, a, lead1, OUT)
    await called(db, await make_user(db, "telecaller", "it"), lead1, IN)
    await paid(db, s1, "5000.00", IN)
    await paid(db, s3, "2000.00", IN)
    await paid(db, s1, "100.00", IN, currency="USD")
    await paid(db, s1, "900.00", IN, status="pending")
    await paid(db, s1, "800.00", OUT)

    await as_role(client, db, "partner")
    body = await read(client)
    assert row(body, a) | {"id": None} == {
        "id": None, "full_name": a.full_name, "division": "it", "active": True, "leads_assigned": 1, "calls": 2, "counseling_sessions": 3,
        "follow_ups": 2, "conversions": 2, "revenue": "7000.00", "conversion_pct": 100.0,
    }  # fmt: skip
    assert {k: row(body, b)[k] for k in KEYS} == {"leads_assigned": 0, "calls": 0, "counseling_sessions": 1, "follow_ups": 0,
                                                 "conversions": 0, "revenue": "0.00", "conversion_pct": None}  # fmt: skip

    await as_role(client, db, "super_admin")
    body = await read(client)
    assert body["revenue_visible"] is False
    assert row(body, a)["revenue"] is None and body["total"]["revenue"] is None
    assert row(body, a)["conversions"] == 2


async def test_conversion_pct_is_the_share_of_the_periods_leads_converted(client, db_session):
    db = db_session
    c = await make_user(db, "counselor", "overseas")
    leads = [await lead(db, c) for _ in range(3)]
    for item in leads:
        await handed(db, item, c, IN)
    await converted(db, leads[0], IN)
    await as_role(client, db, "partner")
    assert row(await read(client), c)["conversion_pct"] == 33.3


async def test_conversions_match_the_telecaller_definition(client, db_session):
    """AC (T5): the counselor's conversions are the same leads tel-021's D13 counts, credited to the counselor instead."""
    db = db_session
    tel, c = await make_user(db, "telecaller", "it"), await make_user(db, "counselor", "it")
    await converted(db, await lead(db, c, telecaller=tel), IN)
    await converted(db, await lead(db, c, telecaller=tel), OUT)
    await converted(db, await lead(db, c, telecaller=tel), IN, still=False)
    lo, hi = _instants(datetime(2024, 6, 1).date(), datetime(2024, 6, 30).date())
    assert (await conversions_by_user(db, [tel.id], lo, hi)).get(tel.id) == 1
    await as_role(client, db, "partner")
    assert row(await read(client), c)["conversions"] == 1


async def test_an_inactive_counselor_is_listed_and_totals_are_the_sum_of_the_rows(client, db_session):
    db = db_session
    gone = await make_user(db, "counselor", "it", active=False)
    await session(db, gone, IN, student=await make_user(db, "it_student", "it"))
    await as_role(client, db, "partner")
    body = await read(client)
    assert row(body, gone)["active"] is False and row(body, gone)["counseling_sessions"] == 1
    rows, total = body["counselors"], body["total"]
    assert total["counselor_count"] == len(rows)
    assert [g["division"] for g in body["divisions"]][:2] == ["it", "overseas"]
    for key in COUNTS:
        assert total[key] == sum(r[key] for r in rows) == sum(g[key] for g in body["divisions"])
    assert Decimal(total["revenue"]) == sum(Decimal(r["revenue"]) for r in rows)
