"""mgmt-024 -- the Applications funnel (§20, Appendix B "Funnels", spec MF1-MF18; AC1 each stage = its definition, AC2 filters narrow).

The test database is shared and seeded, so every test makes its own university and reads the funnel filtered to it: the cohort is then
exactly the rows the test made."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.models import (
    AgentStudent,
    ApplicationDeposit,
    ApplicationStatusHistory,
    DocumentRequest,
    OverseasApplication,
    OverseasCourse,
    Payment,
    StudentDocument,
    VisaCase,
)
from tests.agn001_helpers import mk_active_org
from tests.agn003_helpers import mk_university
from tests.bdm001_helpers import make_user
from tests.upc001_helpers import as_role

pytestmark = pytest.mark.asyncio

URL = "/api/v1/management/applications"
STAGES = [
    "created", "documents_complete", "submitted", "under_review", "offer", "accepted", "deposit", "cas_coe", "visa", "visa_approved",
    "enrollment",
]  # fmt: skip
NOT_TRACKED = {"under_review", "accepted", "cas_coe"}


async def add(db, row):
    db.add(row)
    await db.flush()
    return row


async def funnel(client, **params) -> dict:
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def values(body: dict) -> dict:
    return {stage["key"]: stage["value"] for stage in body["stages"]}


async def application(db, university, status: str = "enquiry", **fields) -> OverseasApplication:
    student = await make_user(db, "overseas_student", "overseas")
    return await add(db, OverseasApplication(university_id=university.id, student_id=student.id, intake=fields.pop("intake", "Fall 2027"), status=status, **fields))


async def document(db, app, status: str):
    await add(db, StudentDocument(student_id=app.student_id, application_id=app.id, document_type="passport", file_url=f"k/{uuid.uuid4().hex}", verification_status=status))


async def deposit(db, app, status: str):
    actor = await make_user(db, "overseas_admin", "overseas")
    payment = None
    if status not in ("pending", "not_required"):
        payment = await add(db, Payment(user_id=actor.id, division="overseas", reference_type="agent_deposit", amount=100, status="paid"))
    required = status != "not_required"
    extra = {}
    if status == "remitted":
        extra = {"remitted_at": date.today(), "remittance_reference": "R-1"}
    if status == "refunded":
        extra = {"refunded_at": date.today(), "refund_amount": Decimal("100"), "refund_reason": "visa refused"}
    await add(db, ApplicationDeposit(
        application_id=app.id, required=required, amount=Decimal("100") if required else None, status=status, paid_payment_id=payment.id if payment else None,
        paid_at=datetime.now(UTC) if payment else None, created_by_user_id=actor.id, updated_by_user_id=actor.id, **extra,
    ))  # fmt: skip


# --- access (M13: operational tier) ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("role", ["partner", "super_admin"])
async def test_operational_tier_reads_the_funnel(client, db_session, role):
    await as_role(client, db_session, role, "global")
    body = await funnel(client)
    assert [stage["key"] for stage in body["stages"]] == STAGES
    assert [stage["label"] for stage in body["stages"]][:3] == ["Applications Created", "Documents Complete", "Submitted"]
    for stage in body["stages"]:
        assert (stage["value"] is None) == (stage["key"] in NOT_TRACKED)
        assert stage["tracked"] == (stage["key"] not in NOT_TRACKED)
    assert isinstance(body["withdrawn"], int)
    assert set(body["options"]) == {"agencies", "counselors", "countries", "universities", "courses", "intakes", "staff", "statuses"}


@pytest.mark.parametrize(("role", "division"), [("accountant", "global"), ("overseas_admin", "overseas"), ("counselor", "overseas"), ("trainer", "it")])
async def test_everyone_else_is_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    response = await client.get(URL)
    assert response.status_code == 403
    assert response.json()["detail"] in {"Operational access required", "Management access required"}


async def test_signed_out_is_401(client):
    assert (await client.get(URL)).status_code == 401


# --- AC1: each stage counts exactly its definition ----------------------------------------------------------------------------
async def test_each_stage_counts_exactly_its_definition(client, db_session):
    db = db_session
    await as_role(client, db, "partner", "global")
    uni = await mk_university(db)

    plain = await application(db, uni)  # created only
    submitted = await application(db, uni, submitted_on=date.today())
    await document(db, submitted, "verified")  # documents complete: one doc, verified
    half = await application(db, uni)
    await document(db, half, "verified")
    await document(db, half, "pending")  # not complete: a doc still pending
    await application(db, uni, "offer")  # offer by stage
    await application(db, uni, "university_selection", offer_type="conditional", offer_date=date.today())  # offer recorded
    withdrawn_after_offer = await application(db, uni, "withdrawn", offer_type="unconditional", offer_date=date.today())  # O5: still an offer
    for status in ("paid", "remitted", "refunded", "pending"):
        await deposit(db, await application(db, uni, "visa_documentation"), status)  # 4 more offers; paid + remitted count as Deposit
    visa = await application(db, uni, "status_tracking")
    await add(db, VisaCase(application_id=visa.id, checklist=[]))
    approved = await application(db, uni, "enrolled")
    await add(db, VisaCase(application_id=approved.id, checklist=[], decision="approved", decided_at=datetime.now(UTC)))
    await add(db, VisaCase(application_id=withdrawn_after_offer.id, checklist=[], decision="refused", decided_at=datetime.now(UTC)))
    await db.commit()
    assert plain.id

    body = await funnel(client, university=str(uni.id))
    assert values(body) == {
        "created": 12, "documents_complete": 1, "submitted": 1, "under_review": None, "offer": 9, "accepted": None, "deposit": 2,
        "cas_coe": None, "visa": 3, "visa_approved": 1, "enrollment": 1,
    }  # fmt: skip
    assert body["withdrawn"] == 1


async def test_documents_complete_needs_no_open_request_for_an_agency_student(client, db_session):
    db = db_session
    await as_role(client, db, "partner", "global")
    uni = await mk_university(db)
    org = await mk_active_org(db, name=f"MG24 Docs {uuid.uuid4().hex[:6]}")
    record = await add(db, AgentStudent(agent_id=org["master"].id, full_name="Agency Student"))
    app = await add(db, OverseasApplication(university_id=uni.id, agent_student_id=record.id, agent_id=org["master"].id, intake="Fall 2027", status="enquiry"))
    await add(db, StudentDocument(agent_student_id=record.id, application_id=app.id, document_type="passport", file_url="k/x", verification_status="verified"))
    request = await add(db, DocumentRequest(agent_student_id=record.id, document_type="transcript", status="open"))
    await db.commit()
    assert values(await funnel(client, university=str(uni.id)))["documents_complete"] == 0
    request.status = "fulfilled"
    await db.commit()
    assert values(await funnel(client, university=str(uni.id)))["documents_complete"] == 1


async def test_school_bridged_applications_are_in_the_funnel(client, db_session):
    from tests.enh005_helpers import mk_school

    db = db_session
    await as_role(client, db, "super_admin", "global")
    uni = await mk_university(db)
    pupil = (await mk_school(db, label=f"mg24-{uuid.uuid4().hex[:6]}"))["students"][0]
    await add(db, OverseasApplication(university_id=uni.id, school_student_id=pupil.id, intake="Fall 2027", status="enquiry"))
    await db.commit()
    assert values(await funnel(client, university=str(uni.id)))["created"] == 1


async def test_stage_counts_are_one_statement(db_session):
    """MF15: the computed stages and the withdrawn figure are one SELECT."""
    from app.services import management_metrics

    statements = []
    engine = db_session.bind.sync_engine

    def count(*_args):
        statements.append(1)

    event.listen(engine, "before_cursor_execute", count)
    try:
        figures = await management_metrics.applications(db_session, management_metrics.ApplicationFunnelFilters())
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert len(statements) == 1
    assert set(figures) == {"created", "documents_complete", "submitted", "offer", "deposit", "visa", "visa_approved", "enrollment", "withdrawn"}


# --- AC2: each filter narrows to its own rows --------------------------------------------------------------------------------
async def test_every_filter_narrows_consistently(client, db_session):
    db = db_session
    await as_role(client, db, "partner", "global")
    uni = await mk_university(db)
    other_uni = await mk_university(db)
    course = await add(db, OverseasCourse(university_id=uni.id, title="MSc Data", level="masters", category="cs", duration="1y", tuition_fee="x", intake="Sep"))
    counselor = await make_user(db, "counselor", "overseas", name="MG24 Counselor")
    staff = await make_user(db, "overseas_admin", "overseas", name="MG24 Staff")
    org = await mk_active_org(db, name=f"MG24 Agency {uuid.uuid4().hex[:6]}")
    record = await add(db, AgentStudent(agent_id=org["master"].id, full_name="Agency Student"))

    agency_app = await add(db, OverseasApplication(university_id=uni.id, agent_student_id=record.id, agent_id=org["master"].id, intake="Jan 2028", status="offer"))
    counselled = await application(db, uni, "enquiry", counselor_id=counselor.id, course_id=course.id)
    await add(db, ApplicationStatusHistory(application_id=counselled.id, from_status=None, to_status="enquiry", changed_by_id=staff.id))
    await application(db, other_uni, "enquiry")  # the second university's own
    await db.commit()

    country = str(uni.country_id)
    assert values(await funnel(client, country=country))["created"] == 2
    assert values(await funnel(client, university=str(uni.id)))["created"] == 2
    assert values(await funnel(client, university=str(other_uni.id)))["created"] == 1
    assert values(await funnel(client, university=str(uni.id), agency=str(org["org"].id)))["created"] == 1
    assert values(await funnel(client, university=str(uni.id), agency="none"))["created"] == 1
    assert values(await funnel(client, university=str(uni.id), counselor=str(counselor.id)))["created"] == 1
    assert values(await funnel(client, university=str(uni.id), counselor="none"))["created"] == 1
    assert values(await funnel(client, university=str(uni.id), course=str(course.id)))["created"] == 1
    assert values(await funnel(client, university=str(uni.id), intake="Jan 2028"))["offer"] == 1
    assert values(await funnel(client, university=str(uni.id), staff=str(staff.id)))["created"] == 1
    assert values(await funnel(client, university=str(uni.id), status="offer"))["created"] == 1
    combined = await funnel(client, university=str(uni.id), agency=str(org["org"].id), status="enquiry")
    assert values(combined)["created"] == 0  # filters AND together
    assert combined["filters"]["agency"] == str(org["org"].id) and combined["filters"]["status"] == "enquiry"
    assert agency_app.id

    options = (await funnel(client))["options"]
    assert {"value": str(org["org"].id), "label": org["org"].name} in options["agencies"]
    assert {"value": str(counselor.id), "label": "MG24 Counselor"} in options["counselors"]
    assert {"value": str(staff.id), "label": "MG24 Staff"} in options["staff"]
    assert any(o["value"] == str(course.id) for o in options["courses"])
    assert {"value": "Jan 2028", "label": "Jan 2028"} in options["intakes"]
    assert {"value": "offer", "label": "Offer"} in options["statuses"]


async def test_created_date_range_is_india_days(client, db_session):
    db = db_session
    await as_role(client, db, "partner", "global")
    uni = await mk_university(db)
    app = await application(db, uni)
    # 20:00 UTC on day D is 01:30 IST on D+1 -- the India day decides
    app.created_at = datetime(2026, 3, 10, 20, 0, tzinfo=UTC)
    await db.commit()
    assert values(await funnel(client, university=str(uni.id), date_from="2026-03-11", date_to="2026-03-11"))["created"] == 1
    assert values(await funnel(client, university=str(uni.id), date_from="2026-03-10", date_to="2026-03-10"))["created"] == 0
    assert values(await funnel(client, university=str(uni.id), date_to=str(date(2026, 3, 11) + timedelta(days=-1))))["created"] == 0


@pytest.mark.parametrize(
    "params",
    [{"agency": "not-a-uuid"}, {"counselor": "12"}, {"university": "x"}, {"date_from": "2026-13-01"}, {"date_from": "2026-03-02", "date_to": "2026-03-01"}],
)
async def test_bad_filter_values_are_422(client, db_session, params):
    await as_role(client, db_session, "partner", "global")
    assert (await client.get(URL, params=params)).status_code == 422


async def test_unknown_ids_narrow_to_nothing(client, db_session):
    await as_role(client, db_session, "partner", "global")
    body = await funnel(client, university=str(uuid.uuid4()))
    assert values(body)["created"] == 0 and body["withdrawn"] == 0
