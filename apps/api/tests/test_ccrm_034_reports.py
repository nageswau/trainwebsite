"""ccrm-034 (DEC-SCOPE-267, R1-R10) -- the management CRM reports: ageing, university performance, visa outcomes, document readiness,
lead conversion by intake and the forecast by intake (§13, AC 8). Each report counts students and applications separately.

The test database is shared and seeded, so every test makes its own university (and its own intake) and reads the reports filtered to
it: the cohort is then exactly the rows the test made."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import (
    ApplicationChecklist,
    ApplicationChecklistItem,
    ApplicationChecklistItemDocument,
    ApplicationOffer,
    Enquiry,
    LeadQualification,
    OverseasApplication,
    StudentDocument,
    VisaCase,
)
from tests.agn003_helpers import mk_university
from tests.bdm001_helpers import make_user
from tests.upc001_helpers import as_role

pytestmark = pytest.mark.asyncio

URL = "/api/v1/management/crm-reports"
REPORTS = ("ageing", "universities", "visa", "readiness", "leads", "forecast")


async def add(db, row):
    db.add(row)
    await db.flush()
    return row


async def reports(client, **params) -> dict:
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def application(db, university, status: str = "enquiry", *, student=None, **fields) -> OverseasApplication:
    student = student or await make_user(db, "overseas_student", "overseas")
    return await add(db, OverseasApplication(university_id=university.id, student_id=student.id, intake=fields.pop("intake", "Fall 2027"), status=status, **fields))


def ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


# --- access (R1) ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("role", "division"), [("partner", "global"), ("super_admin", "global"), ("overseas_admin", "overseas")])
async def test_management_and_the_overseas_admin_read_the_reports(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    university = await mk_university(db_session)
    body = await reports(client, university=str(university.id))
    for key in REPORTS:
        assert body[key]["definitions"], key
        assert all(d["label"] and d["definition"] for d in body[key]["definitions"])
        if key != "leads":  # R2: the university filter does not apply to leads
            assert body[key]["rows"] == []
    assert body["filters"]["university"] == str(university.id)
    assert {"counselors", "countries", "universities", "courses", "intakes"} <= set(body["options"])


@pytest.mark.parametrize(("role", "division"), [("accountant", "global"), ("counselor", "overseas"), ("overseas_student", "overseas"), ("it_admin", "it")])
async def test_everyone_else_is_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(URL)).status_code == 403


async def test_anonymous_is_refused(client):
    assert (await client.get(URL)).status_code == 401


# --- R5 ageing --------------------------------------------------------------------------------------------------------------------
async def test_ageing_groups_open_applications_by_stage_and_sub_status_with_day_bands(client, db_session):
    await as_role(client, db_session, "partner", "global")
    university = await mk_university(db_session)
    await application(db_session, university, updated_at=ago(3))
    shared = await make_user(db_session, "overseas_student", "overseas")
    await application(db_session, university, "university_selection", student=shared, sub_status="documents_pending", updated_at=ago(20))
    await application(db_session, university, "university_selection", student=shared, sub_status="documents_pending", updated_at=ago(70), intake="Spring 2028")
    await application(db_session, university, "withdrawn", updated_at=ago(90))  # R4: closed rows do not age
    await application(db_session, university, "university_selection", outcome="rejected", updated_at=ago(90))
    await application(db_session, university, "enrolled", updated_at=ago(90))
    await application(db_session, university, "offer", outcome="on_hold", updated_at=ago(10))  # on hold is open
    await db_session.commit()

    ageing = (await reports(client, university=str(university.id)))["ageing"]
    rows = {(r["stage"], r["sub_status"]): r for r in ageing["rows"]}
    assert set(rows) == {("enquiry", None), ("university_selection", "documents_pending"), ("offer", None)}
    selection = rows[("university_selection", "documents_pending")]
    assert (selection["applications"], selection["students"]) == (2, 1)  # one student, two applications
    assert selection["bands"] == {"d0_7": 0, "d8_14": 0, "d15_30": 1, "d31_60": 0, "d61_plus": 1}
    assert selection["oldest_days"] == 70
    assert selection["stage_label"] == "University selection" and selection["sub_status_label"] == "Documents pending"
    assert rows[("enquiry", None)]["bands"]["d0_7"] == 1 and rows[("enquiry", None)]["sub_status_label"] == "Not set"
    assert [r["stage"] for r in ageing["rows"]] == ["enquiry", "university_selection", "offer"]  # stage order
    assert (ageing["total"]["applications"], ageing["total"]["students"]) == (4, 3)


# --- R6 university performance ----------------------------------------------------------------------------------------------------
async def test_university_performance_counts_offers_rejections_acceptances_and_confirmed_enrolments(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    university = await mk_university(db_session)
    accepted = await application(db_session, university, "offer")
    await add(db_session, ApplicationOffer(application_id=accepted.id, offer_type="conditional", issue_date=date.today(), decision="accepted", decision_date=date.today()))
    await application(db_session, university, "enrolled", enrollment_confirmed_at=datetime.now(UTC), enrollment_date=date.today())
    await application(db_session, university, "enrolled")  # an unconfirmed enrolment is not one (ccrm-027 E4)
    await application(db_session, university, "university_selection", outcome="rejected")
    await db_session.commit()

    perf = (await reports(client, university=str(university.id)))["universities"]
    [row] = perf["rows"]
    assert row["university_id"] == str(university.id) and row["label"] == "AGN003 University"
    assert (row["applications"], row["students"]) == (4, 4)
    assert (row["offers"], row["rejections"], row["acceptances"], row["enrollments"]) == (3, 1, 1, 1)
    assert row["offer_rate"] == 75.0
    assert perf["total"]["offers"] == 3 and perf["total"]["offer_rate"] == 75.0


# --- R7 visa outcomes -------------------------------------------------------------------------------------------------------------
async def test_visa_outcomes_by_destination(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    university = await mk_university(db_session)
    approved = await application(db_session, university, "enrolled", enrollment_confirmed_at=datetime.now(UTC), enrollment_date=date.today())
    pending = await application(db_session, university, "status_tracking")
    refused = await application(db_session, university, "status_tracking", outcome="visa_refused")
    started = await application(db_session, university, "visa_documentation")
    await application(db_session, university, "offer")  # no visa case: not in the report
    for app, visa_status, decision in ((approved, "approved", "approved"), (pending, "decision_pending", None), (refused, "refused", "refused"), (started, "not_started", None)):
        await add(db_session, VisaCase(application_id=app.id, visa_status=visa_status, decision=decision, status="decision" if decision else "checklist"))
    await db_session.commit()

    visa = (await reports(client, university=str(university.id)))["visa"]
    [row] = visa["rows"]
    assert row["country_id"] == str(university.country_id) and row["label"] == "Testland"
    assert (row["applications"], row["students"]) == (4, 4)
    assert (row["submitted"], row["pending"], row["approved"], row["refused"], row["enrolled"]) == (3, 1, 1, 1, 1)
    assert visa["total"]["submitted"] == 3


# --- R8 document readiness --------------------------------------------------------------------------------------------------------
async def checklist(db, app, gate_mode: str, *items: tuple[bool, str | None, str | None]) -> None:
    """items: (required, mark, a linked document's verification status)."""
    await add(db, ApplicationChecklist(application_id=app.id, gate_mode=gate_mode))
    for position, (required, mark, doc_status) in enumerate(items):
        item = await add(db, ApplicationChecklistItem(application_id=app.id, position=position, document_type="passport", required=required, mark=mark))
        if doc_status:
            doc = await add(db, StudentDocument(student_id=app.student_id, application_id=app.id, document_type="passport", file_url=f"k/{uuid.uuid4().hex}", verification_status=doc_status))
            await add(db, ApplicationChecklistItemDocument(item_id=item.id, document_id=doc.id))


async def test_readiness_splits_pre_submission_applications_by_checklist_state(client, db_session):
    await as_role(client, db_session, "partner", "global")
    university = await mk_university(db_session)
    blocked = await application(db_session, university, "university_selection", sub_status="documents_pending")
    await checklist(db_session, blocked, "block", (True, None, "uploaded"), (True, "not_required", None))
    override = await application(db_session, university, "university_selection")
    await checklist(db_session, override, "warn", (True, "requested", None))
    ready = await application(db_session, university, "eligibility_evaluation")
    await checklist(db_session, ready, "block", (True, None, "verified"), (True, "not_required", None), (False, None, None))
    await application(db_session, university)  # no checklist
    submitted = await application(db_session, university, "university_selection", submitted_on=date.today())
    await checklist(db_session, submitted, "block", (True, None, None))
    await application(db_session, university, "offer")  # past submission
    await application(db_session, university, "university_selection", sub_status="under_review")
    await application(db_session, university, "university_selection", outcome="withdrawn")
    await db_session.commit()

    readiness = (await reports(client, university=str(university.id)))["readiness"]
    rows = {r["stage"]: r for r in readiness["rows"]}
    assert set(rows) == {"enquiry", "eligibility_evaluation", "university_selection"}
    assert (rows["university_selection"]["blocked"], rows["university_selection"]["needs_override"]) == (1, 1)
    assert rows["eligibility_evaluation"]["ready"] == 1 and rows["enquiry"]["no_checklist"] == 1
    total = readiness["total"]
    assert (total["applications"], total["students"], total["ready"], total["blocked"], total["needs_override"], total["no_checklist"]) == (4, 4, 1, 1, 1, 1)


# --- R9 lead conversion by intake -------------------------------------------------------------------------------------------------
async def lead(db, intake: str | None, *, division: str = "overseas", owner=None, converted_to=None) -> Enquiry:
    actor = await make_user(db, "overseas_admin", "overseas")
    conversion = {"status": "converted", "converted_user_id": converted_to.id, "converted_at": datetime.now(UTC), "converted_by_user_id": actor.id} if converted_to else {}
    row = await add(db, Enquiry(division=division, name="Lead", subject="Study", message="-", owner_id=owner.id if owner else None, **conversion))
    if intake is not None:
        await add(db, LeadQualification(lead_id=row.id, intake=intake, updated_by_user_id=actor.id))
    return row


async def test_lead_conversion_by_intake(client, db_session):
    await as_role(client, db_session, "partner", "global")
    intake = f"I-{uuid.uuid4().hex[:8]}"
    student = await make_user(db_session, "overseas_student", "overseas")
    university = await mk_university(db_session)
    await application(db_session, university, student=student)
    await application(db_session, university, student=student, intake="Spring 2028")
    await lead(db_session, intake, converted_to=student)
    await lead(db_session, intake)
    await lead(db_session, intake, division="it")  # R9: overseas leads only
    await db_session.commit()

    leads = (await reports(client, intake=intake))["leads"]
    [row] = leads["rows"]
    assert (row["intake"], row["label"]) == (intake, intake)
    assert (row["leads"], row["converted"], row["students"], row["applications"]) == (2, 1, 1, 2)
    assert row["conversion_pct"] == 50.0
    assert leads["total"]["leads"] == 2


async def test_lead_report_filters_by_owner_counselor_and_names_a_blank_intake(client, db_session):
    await as_role(client, db_session, "partner", "global")
    counselor = await make_user(db_session, "counselor", "overseas")
    await lead(db_session, None, owner=counselor)
    await lead(db_session, "Fall 2027", owner=counselor)
    await lead(db_session, "Fall 2027")
    await db_session.commit()

    rows = {r["intake"]: r for r in (await reports(client, counselor=str(counselor.id)))["leads"]["rows"]}
    assert set(rows) == {None, "Fall 2027"}
    assert rows[None]["label"] == "Not recorded" and rows["Fall 2027"]["leads"] == 1


# --- R10 forecast by intake -------------------------------------------------------------------------------------------------------
async def test_forecast_by_intake_is_confirmed_plus_visa_approved(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    university = await mk_university(db_session)
    intake = f"F-{uuid.uuid4().hex[:8]}"
    await application(db_session, university, "enrolled", intake=intake, enrollment_confirmed_at=datetime.now(UTC), enrollment_date=date.today())
    expected = await application(db_session, university, "status_tracking", intake=intake, sub_status="visa_approved")
    await add(db_session, VisaCase(application_id=expected.id, visa_status="approved", decision="approved", status="decision"))
    await application(db_session, university, "offer", intake=intake)  # possible
    await application(db_session, university, "status_tracking", intake=intake, outcome="visa_refused")  # lost
    await application(db_session, university, "withdrawn", intake=intake)  # lost
    await application(db_session, university, "enquiry", intake=intake)
    await db_session.commit()

    forecast = (await reports(client, university=str(university.id)))["forecast"]
    [row] = forecast["rows"]
    assert row["intake"] == intake and row["applications"] == 6 and row["students"] == 6
    assert (row["confirmed"], row["expected"], row["possible"], row["lost"], row["forecast"]) == (1, 1, 1, 2, 2)


# --- R2 filters -------------------------------------------------------------------------------------------------------------------
async def test_filters_narrow_every_application_report(client, db_session):
    await as_role(client, db_session, "partner", "global")
    university = await mk_university(db_session)
    counselor = await make_user(db_session, "counselor", "overseas")
    await application(db_session, university, counselor_id=counselor.id)
    await application(db_session, university)
    old = await application(db_session, university, intake="Spring 2028")
    old.created_at = ago(40)
    await db_session.commit()

    scoped = str(university.id)
    assert (await reports(client, university=scoped))["ageing"]["total"]["applications"] == 3
    assert (await reports(client, university=scoped, counselor=str(counselor.id)))["ageing"]["total"]["applications"] == 1
    assert (await reports(client, university=scoped, counselor="none"))["ageing"]["total"]["applications"] == 2
    assert (await reports(client, university=scoped, intake="Spring 2028"))["forecast"]["total"]["applications"] == 1
    assert (await reports(client, university=scoped, country=str(university.country_id)))["universities"]["total"]["applications"] == 3
    recent = (date.today() - timedelta(days=7)).isoformat()
    assert (await reports(client, university=scoped, date_from=recent))["universities"]["total"]["applications"] == 2


async def test_intake_choices_never_offer_a_blank(client, db_session):
    """Browser QA-02: a blank intake on an application would be a choice that silently means "All"."""
    await as_role(client, db_session, "partner", "global")
    university = await mk_university(db_session)
    await application(db_session, university, intake="   ")
    await application(db_session, university, intake="")
    await db_session.commit()
    intakes = [o["value"] for o in (await reports(client, university=str(university.id)))["options"]["intakes"]]
    assert all(value.strip() for value in intakes)


async def test_bad_filters_are_422(client, db_session):
    await as_role(client, db_session, "partner", "global")
    assert (await client.get(URL, params={"date_from": "2027-02-01", "date_to": "2027-01-01"})).status_code == 422
    assert (await client.get(URL, params={"counselor": "not-an-id"})).status_code == 422
    assert (await client.get(URL, params={"university": "nope"})).status_code == 422
