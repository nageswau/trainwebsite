"""ccrm-036 (DEC-SCOPE-269, P1-P9) -- GET /counselor/performance: the overseas counselor's own figures. The period figures are
mgmt-018's (the same builders, so the same definitions) without revenue; then lead follow-up completion, tasks, and the caseload now
(applications by stage and sub-status, offers, visas, enrolments).

The test database is shared and never truncated, so every test reads a counselor it made itself, over a fixed past period."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import CounselorTask, LeadFollowUp, OverseasApplication, StudentDocument, VisaCase
from app.services.bdm_travel import india_today
from tests.agn003_helpers import mk_university
from tests.bdm001_helpers import login, make_user
from tests.test_mgmt_018_counseling import BEFORE, IN, OUT, PERIOD, called, converted, handed, lead, session

pytestmark = pytest.mark.asyncio

URL = "/api/v1/counselor/performance"
MANAGEMENT = ["leads_assigned", "calls", "counseling_sessions", "follow_ups", "conversions", "conversion_pct"]


async def me(client, db, role: str = "counselor", division: str = "overseas"):
    client.cookies.clear()
    user = await make_user(db, role, division)
    await login(client, user)
    return user


async def read(client, **params) -> dict:
    response = await client.get(URL, params={**PERIOD, **params})
    assert response.status_code == 200, response.text
    return response.json()


def values(body: dict, part: str) -> dict:
    return {f["key"]: f["value"] for f in body[part]}


async def add(db, row):
    db.add(row)
    await db.commit()
    return row


# --- P1 access ------------------------------------------------------------------------------------------------------------------
async def test_the_overseas_counselor_reads_their_own_report(client, db_session):
    await me(client, db_session)
    body = await read(client)
    assert (body["from"], body["to"]) == (PERIOD["from"], PERIOD["to"])
    for part in ("period", "now"):
        assert body[part] and all(f["label"] and f["definition"] and f["unit"] in {"count", "percent"} for f in body[part])
    assert body["applications"]["rows"] == [] and body["applications"]["total"] == {"applications": 0, "students": 0}
    assert body["applications"]["definitions"]


@pytest.mark.parametrize(
    ("role", "division"),
    [("counselor", "it"), ("overseas_admin", "overseas"), ("super_admin", "global"), ("partner", "global"), ("overseas_student", "overseas"), ("agent", "overseas")],
)
async def test_everyone_else_is_refused(client, db_session, role, division):
    await me(client, db_session, role, division)
    assert (await client.get(URL)).status_code == 403


async def test_anonymous_is_refused(client):
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401


# --- P2 period ------------------------------------------------------------------------------------------------------------------
async def test_the_period_defaults_to_this_ist_month(client, db_session):
    await me(client, db_session)
    response = await client.get(URL)
    assert response.status_code == 200, response.text
    today = india_today()
    assert response.json()["from"] == today.replace(day=1).isoformat()
    assert date.fromisoformat(response.json()["to"]) >= today


@pytest.mark.parametrize("params", [{"from": "2024-06-30", "to": "2024-06-01"}, {"from": "2020-01-01", "to": "2024-06-30"}, {"from": "not-a-date"}])
async def test_a_bad_period_is_422(client, db_session, params):
    await me(client, db_session)
    assert (await client.get(URL, params=params)).status_code == 422


# --- P3 the management definitions, no revenue -------------------------------------------------------------------------------------
async def test_period_figures_equal_the_counseling_dashboard_row_and_carry_no_revenue(client, db_session):
    counselor = await make_user(db_session, "counselor", "overseas")
    kept, lost = await lead(db_session, counselor), await lead(db_session, counselor)
    await handed(db_session, kept, counselor, IN)
    await handed(db_session, lost, counselor, IN)
    await handed(db_session, await lead(db_session, counselor), counselor, OUT)
    await converted(db_session, kept, IN)
    await called(db_session, counselor, kept, IN)
    await session(db_session, counselor, BEFORE, lead_row=kept)
    await session(db_session, counselor, IN, lead_row=kept)
    await session(db_session, counselor, IN, lead_row=lost)

    client.cookies.clear()
    await login(client, await make_user(db_session, "partner", "global"))
    dashboard = (await client.get("/api/v1/management/counseling", params=PERIOD)).json()
    expected = next(r for r in dashboard["counselors"] if r["id"] == str(counselor.id))

    client.cookies.clear()
    await login(client, counselor)
    response = await client.get(URL, params=PERIOD)
    figures = values(response.json(), "period")
    assert {k: figures[k] for k in MANAGEMENT} == {k: expected[k] for k in MANAGEMENT}
    assert (figures["leads_assigned"], figures["conversions"], figures["conversion_pct"], figures["follow_ups"]) == (2, 1, 50.0, 1)
    labels = {f["key"]: (f["label"], f["definition"]) for f in response.json()["period"]}
    assert labels["leads_assigned"] == next((f["label"], f["definition"]) for f in dashboard["figures"] if f["key"] == "leads_assigned")
    assert "revenue" not in response.text.lower()


async def test_no_leads_assigned_gives_no_conversion_percentage(client, db_session):
    await me(client, db_session)
    assert values(await read(client), "period")["conversion_pct"] is None


# --- P4 / P6 lead follow-ups ------------------------------------------------------------------------------------------------------
async def follow_up(db, lead_row, by, due: datetime, status: str = "open") -> None:
    done, cancelled = status == "done", status == "cancelled"
    await add(db, LeadFollowUp(lead_id=lead_row.id, due_at=due, reason="counselor_call", status=status, created_by_user_id=by.id,
                               completed_at=due if done else None, completed_by_user_id=by.id if done else None,
                               cancelled_at=due if cancelled else None, cancel_reason="Closed" if cancelled else None))  # fmt: skip


async def test_follow_up_completion_counts_the_follow_ups_on_my_leads_due_in_the_period(client, db_session):
    counselor = await me(client, db_session)
    mine = await lead(db_session, counselor)
    await follow_up(db_session, mine, counselor, IN, "done")
    await follow_up(db_session, mine, counselor, IN, "open")  # due in the period, still open: overdue now too
    await follow_up(db_session, mine, counselor, IN, "cancelled")  # P4: cancelled ones are not due
    await follow_up(db_session, mine, counselor, OUT, "done")  # outside the period
    await follow_up(db_session, mine, counselor, datetime.now(UTC) + timedelta(days=2))  # open, not yet due
    other = await make_user(db_session, "counselor", "overseas")
    await follow_up(db_session, await lead(db_session, other), other, IN, "open")  # another counselor's lead

    body = await read(client)
    period = values(body, "period")
    assert (period["follow_ups_due"], period["follow_ups_completed"], period["follow_up_completion_pct"]) == (2, 1, 50.0)
    assert values(body, "now")["overdue_follow_ups"] == 1


async def test_no_follow_ups_due_gives_no_completion_percentage(client, db_session):
    await me(client, db_session)
    assert values(await read(client), "period")["follow_up_completion_pct"] is None


# --- P5 tasks -------------------------------------------------------------------------------------------------------------------
async def task(db, counselor, due: date, status: str = "open", completed_at: datetime | None = None) -> None:
    await add(db, CounselorTask(title=f"Task {uuid.uuid4().hex[:6]}", counselor_user_id=counselor.id, due_on=due, status=status, completed_at=completed_at,
                                cancelled_at=datetime.now(UTC) if status == "cancelled" else None, created_by_user_id=counselor.id, updated_by_user_id=counselor.id))  # fmt: skip


async def test_overdue_tasks_now_and_tasks_completed_in_the_period(client, db_session):
    counselor = await me(client, db_session)
    today = india_today()
    await task(db_session, counselor, today - timedelta(days=1))  # overdue
    await task(db_session, counselor, today - timedelta(days=9))  # overdue
    await task(db_session, counselor, today)  # due today: not overdue
    await task(db_session, counselor, today - timedelta(days=3), "cancelled")
    await task(db_session, counselor, date(2024, 6, 1), "done", IN)  # completed in the period
    await task(db_session, counselor, date(2024, 6, 1), "done", OUT)
    other = await make_user(db_session, "counselor", "overseas")
    await task(db_session, other, today - timedelta(days=1))

    body = await read(client)
    assert values(body, "now")["overdue_tasks"] == 2
    assert values(body, "period")["tasks_completed"] == 1


# --- P7 / P8 caseload ---------------------------------------------------------------------------------------------------------------
async def application(db, university, counselor, status: str = "enquiry", *, student=None, **fields) -> OverseasApplication:
    student = student or await make_user(db, "overseas_student", "overseas")
    return await add(db, OverseasApplication(university_id=university.id, student_id=student.id, counselor_id=counselor.id, intake=fields.pop("intake", "Fall 2027"), status=status, **fields))


async def test_the_caseload_counts_applications_students_offers_visas_enrolments_and_pending_documents(client, db_session):
    counselor = await me(client, db_session)
    university = await mk_university(db_session)
    shared = await make_user(db_session, "overseas_student", "overseas")
    await application(db_session, university, counselor, student=shared)
    offered = await application(db_session, university, counselor, "offer", student=shared)
    approved = await application(db_session, university, counselor, "visa_documentation")
    refused = await application(db_session, university, counselor, "visa_documentation")
    pending = await application(db_session, university, counselor, "visa_documentation")
    await application(db_session, university, counselor, "enrolled", enrollment_confirmed_at=datetime.now(UTC), enrollment_date=date.today())
    await application(db_session, university, counselor, "enrolled")  # not confirmed: not an enrolment (ccrm-027 E4)
    for app, status in ((approved, "approved"), (refused, "refused"), (pending, "decision_pending")):
        decided = status in {"approved", "refused"}
        await add(db_session, VisaCase(application_id=app.id, visa_status=status, decision=status if decided else None, status="decision" if decided else "checklist"))
    for doc_status in ("pending", "pending", "verified"):
        await add(db_session, StudentDocument(student_id=offered.student_id, application_id=offered.id, document_type="passport", file_url=f"k/{uuid.uuid4().hex}", verification_status=doc_status))
    other = await make_user(db_session, "counselor", "overseas")
    await application(db_session, university, other, "offer")  # another counselor's

    now = values(await read(client), "now")
    assert (now["applications"], now["students"]) == (7, 6)
    assert now["offers"] == 6  # the funnel Offer: offer, visa documentation and both enrolled
    assert (now["visas_pending"], now["visas_approved"], now["visas_refused"]) == (1, 1, 1)
    assert now["enrollments"] == 1
    assert now["documents_pending"] == 2


async def test_applications_are_grouped_by_stage_then_sub_status_in_stage_order(client, db_session):
    counselor = await me(client, db_session)
    university = await mk_university(db_session)
    shared = await make_user(db_session, "overseas_student", "overseas")
    await application(db_session, university, counselor, "university_selection", student=shared, sub_status="documents_pending")
    await application(db_session, university, counselor, "university_selection", student=shared, sub_status="documents_pending", intake="Spring 2028")
    await application(db_session, university, counselor, "offer")
    await application(db_session, university, counselor, "enquiry")
    await application(db_session, university, counselor, "withdrawn")  # P8: the whole caseload, closed stages included

    table = (await read(client))["applications"]
    keys = [(r["stage"], r["sub_status"]) for r in table["rows"]]
    assert keys == [("enquiry", None), ("university_selection", "documents_pending"), ("offer", None), ("withdrawn", None)]
    selection = table["rows"][1]
    assert (selection["applications"], selection["students"]) == (2, 1)
    assert (selection["stage_label"], selection["sub_status_label"]) == ("University selection", "Documents pending")
    assert table["rows"][0]["sub_status_label"] == "Not set"
    assert table["total"] == {"applications": 5, "students": 4}
