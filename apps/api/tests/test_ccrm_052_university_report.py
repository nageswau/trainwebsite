"""ccrm-052 (spec docs/superpowers/specs/2026-10-28-ccrm-052-university-report-deposits-visas-design.md): the university performance
report gains deposits paid and the visa outcome per application, and a drill-down lists the applications behind a university's row.

Each test makes its own university and reads the report filtered to it (the shared database is seeded), as test_ccrm_034_reports.py."""

import csv
import io
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.models import AgentStudent, ApplicationDeposit, ApplicationDepositRecord, OverseasApplication, OverseasCourse, Payment, VisaCase
from tests.agn003_helpers import mk_university
from tests.bdm001_helpers import make_user
from tests.upc001_helpers import as_role

pytestmark = pytest.mark.asyncio

URL = "/api/v1/management/crm-reports"
NEW = ("deposits_paid", "visas_approved", "visas_refused", "visas_pending")


async def add(db, row):
    db.add(row)
    await db.flush()
    return row


async def application(db, university, status: str = "university_selection", *, student=None, **fields) -> OverseasApplication:
    student = student or await make_user(db, "overseas_student", "overseas")
    return await add(db, OverseasApplication(university_id=university.id, student_id=student.id, intake=fields.pop("intake", "Fall 2027"), status=status, **fields))


async def visa(db, app, visa_status: str) -> VisaCase:
    return await add(db, VisaCase(application_id=app.id, visa_status=visa_status))


async def counselor_deposit(db, app, payment_status: str) -> None:
    by = await make_user(db, "counselor", "overseas")
    paid = payment_status in ("paid_to_university", "paid_via_edusphere")
    await add(db, ApplicationDepositRecord(
        application_id=app.id, required=True, amount=Decimal("500"), currency="GBP", payment_status=payment_status,
        paid_on=date.today() if paid else None, recorded_by_id=by.id, updated_by_id=by.id,
    ))  # fmt: skip


async def agency_deposit(db, app, status: str) -> None:
    actor = await make_user(db, "overseas_admin", "overseas")
    payment = None if status == "pending" else await add(db, Payment(user_id=actor.id, division="overseas", reference_type="agent_deposit", amount=100, status="paid"))
    extra = {
        "refunded": {"refunded_at": date.today(), "refund_amount": Decimal("100"), "refund_reason": "visa refused"},
        "remitted": {"remitted_at": date.today(), "remittance_reference": "R-1"},
    }.get(status, {})
    await add(db, ApplicationDeposit(
        application_id=app.id, required=True, amount=Decimal("100"), status=status, paid_payment_id=payment.id if payment else None,
        paid_at=datetime.now(UTC) if payment else None, created_by_user_id=actor.id, updated_by_user_id=actor.id, **extra,
    ))  # fmt: skip


async def universities(client, **params) -> dict:
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()["universities"]


async def drill(client, university_id, **params):
    return await client.get(f"{URL}/universities/{university_id}/applications", params=params)


async def test_visas_are_counted_once_per_application_first_match_wins_ac1(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    university = await mk_university(db_session)
    for _ in range(2):
        await visa(db_session, await application(db_session, university, "visa"), "approved")
    await visa(db_session, await application(db_session, university, "visa"), "refused")
    pending = await application(db_session, university, "visa")
    await visa(db_session, pending, "decision_pending")
    reapplied = await application(db_session, university, "visa")  # refused, then approved: approved wins
    await visa(db_session, reapplied, "refused")
    await visa(db_session, reapplied, "approved")
    await visa(db_session, await application(db_session, university, "visa"), "not_started")  # not submitted: no bucket
    await visa(db_session, await application(db_session, university, "withdrawn"), "approved")  # D2: withdrawn not counted
    await db_session.commit()

    report = await universities(client, university=str(university.id))
    [row] = report["rows"]
    assert (row["visas_approved"], row["visas_refused"], row["visas_pending"]) == (3, 1, 1)
    assert (report["total"]["visas_approved"], report["total"]["visas_refused"], report["total"]["visas_pending"]) == (3, 1, 1)
    assert row["applications"] == 7  # the existing count is unchanged
    assert {d["key"] for d in report["definitions"]} >= set(NEW)


async def test_deposits_paid_counts_applications_once_ac2(client, db_session):
    await as_role(client, db_session, "partner", "global")
    university = await mk_university(db_session)
    await counselor_deposit(db_session, await application(db_session, university), "paid_to_university")
    await counselor_deposit(db_session, await application(db_session, university), "paid_via_edusphere")
    await counselor_deposit(db_session, await application(db_session, university), "pending")
    await agency_deposit(db_session, await application(db_session, university), "paid")
    await agency_deposit(db_session, await application(db_session, university), "remitted")
    await agency_deposit(db_session, await application(db_session, university), "pending")
    await agency_deposit(db_session, await application(db_session, university), "refunded")  # D1: refunded is not paid
    await application(db_session, university)
    await db_session.commit()

    report = await universities(client, university=str(university.id))
    [row] = report["rows"]
    assert row["deposits_paid"] == report["total"]["deposits_paid"] == 4 and row["applications"] == 8


async def test_filters_narrow_the_new_columns_ac3(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    university = await mk_university(db_session)
    fall = await application(db_session, university, "visa", intake="Fall 2027")
    await visa(db_session, fall, "approved")
    await counselor_deposit(db_session, fall, "paid_to_university")
    spring = await application(db_session, university, "visa", intake="Spring 2028")
    await visa(db_session, spring, "refused")
    await db_session.commit()

    [row] = (await universities(client, university=str(university.id), intake="Spring 2028"))["rows"]
    assert (row["applications"], row["deposits_paid"], row["visas_approved"], row["visas_refused"]) == (1, 0, 0, 1)


async def test_the_export_appends_the_new_columns_ac4(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    university = await mk_university(db_session)
    app = await application(db_session, university, "visa")
    await visa(db_session, app, "approved")
    await counselor_deposit(db_session, app, "paid_to_university")
    await db_session.commit()

    response = await client.get(f"{URL}/export", params={"report": "universities", "format": "csv", "university": str(university.id)})
    assert response.status_code == 200, response.text
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == ["University", "Applications", "Students", "Offers", "Offer rate (%)", "Rejections", "Acceptances", "Enrolments",
                       "Deposits paid", "Visas approved", "Visas refused", "Visas pending"]  # fmt: skip
    assert rows[1][-4:] == ["1", "1", "0", "0"]


async def test_the_drill_down_lists_the_rows_applications_ac5(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    university = await mk_university(db_session)
    counselor = await make_user(db_session, "counselor", "overseas")
    course = OverseasCourse(university_id=university.id, title="MSc Data Science", level="Masters", category="Computing", duration="1 year", tuition_fee="GBP 20,000", intake="September")
    await add(db_session, course)
    direct = await application(db_session, university, "visa", course_id=course.id, counselor_id=counselor.id)
    await visa(db_session, direct, "approved")
    await counselor_deposit(db_session, direct, "paid_to_university")
    agent = await make_user(db_session, "agent", "overseas")
    record = await add(db_session, AgentStudent(agent_id=agent.id, status="active", full_name=f"No Login {uuid.uuid4().hex[:6]}"))
    await add(db_session, OverseasApplication(university_id=university.id, agent_id=agent.id, agent_student_id=record.id, intake="Spring 2028", status="offer"))
    await application(db_session, university, "withdrawn")
    other = await mk_university(db_session)
    await application(db_session, other)  # another university's application never appears
    await db_session.commit()

    [row] = (await universities(client, university=str(university.id)))["rows"]
    response = await drill(client, university.id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["university"] == {"id": str(university.id), "label": row["label"]}
    assert body["total"] == row["applications"] == len(body["items"]) == 3
    assert (body["page"], body["page_size"]) == (1, 100)
    by_id = {i["application_id"]: i for i in body["items"]}
    first = by_id[str(direct.id)]
    assert first["student_name"] == (await db_session.get(type(counselor), direct.student_id)).full_name
    assert (first["course"], first["intake"], first["stage"], first["stage_label"]) == ("MSc Data Science", "Fall 2027", "visa", "Visa")
    assert (first["counselor"], first["deposit_paid"], first["visa"]) == (counselor.full_name, True, "approved")
    assert first["application_code"]
    agency = next(i for i in body["items"] if i["student_name"] == record.full_name)
    assert (agency["course"], agency["counselor"], agency["deposit_paid"], agency["visa"]) == (None, None, False, None)
    withdrawn = next(i for i in body["items"] if i["stage"] == "withdrawn")
    assert withdrawn["stage_label"] == "Withdrawn"
    # the filters narrow it like the row
    narrowed = (await drill(client, university.id, intake="Spring 2028")).json()
    assert narrowed["total"] == 1 and [i["intake"] for i in narrowed["items"]] == ["Spring 2028"]


async def test_the_drill_down_pages_by_100(client, db_session):
    await as_role(client, db_session, "partner", "global")
    university = await mk_university(db_session)
    student = await make_user(db_session, "overseas_student", "overseas")
    for _ in range(101):
        db_session.add(OverseasApplication(university_id=university.id, student_id=student.id, intake="Fall 2027", status="enquiry"))
    await db_session.commit()
    first = (await drill(client, university.id)).json()
    second = (await drill(client, university.id, page=2)).json()
    assert (first["total"], len(first["items"]), len(second["items"])) == (101, 100, 1)
    assert not {i["application_id"] for i in first["items"]} & {i["application_id"] for i in second["items"]}


async def test_the_drill_down_refuses_bad_input(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    university = await mk_university(db_session)
    await db_session.commit()
    assert (await drill(client, uuid.uuid4())).status_code == 404
    assert (await drill(client, university.id, page=0)).status_code == 422
    assert (await drill(client, university.id, date_from="2027-02-01", date_to="2027-01-01")).status_code == 422
    assert (await drill(client, university.id, counselor="nobody")).status_code == 422


@pytest.mark.parametrize(("role", "division"), [("accountant", "global"), ("counselor", "overseas"), ("overseas_student", "overseas"), ("agent", "overseas")])
async def test_everyone_else_is_refused_the_drill_down(client, db_session, role, division):
    university = await mk_university(db_session)
    await as_role(client, db_session, role, division)
    assert (await drill(client, university.id)).status_code == 403


async def test_anonymous_is_refused_the_drill_down(client):
    assert (await drill(client, uuid.uuid4())).status_code == 401
