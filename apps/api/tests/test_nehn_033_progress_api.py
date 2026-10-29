"""nehn-033 (DEC-SCOPE-332): GET /overseas/me/progress -- the overseas student's own stepper per application, the documents they still
have to upload (each linking to upload) and their next actions. Read-only; the student's own rows only; staff roles are 403."""

from datetime import date, timedelta

import pytest

from app.models import (
    ApplicationChecklist,
    ApplicationChecklistItem,
    ApplicationDepositRecord,
    ApplicationOffer,
    ApplicationStatusHistory,
    DocumentRequest,
    StudentDocument,
    VisaCase,
)
from tests.agn001_helpers import login, mk_user, uniq
from tests.enh031_helpers import mk_application, mk_university

URL = "/api/v1/overseas/me/progress"
UPLOAD = "/overseas/student/documents"


async def world(db, status="offer", **fields):
    student = await mk_user(db, role="overseas_student", full_name="Progress Student")
    uni = await mk_university(db, name=uniq("Progress Uni"))
    app = await mk_application(db, student=student, university=uni, status=status)
    for key, value in fields.items():
        setattr(app, key, value)
    await db.commit()
    return student, uni, app


def doc(student, app, document_type, status):
    return StudentDocument(student_id=student.id, application_id=app.id, document_type=document_type, file_url=f"k/{uniq()}", verification_status=status)


async def read(client, student) -> dict:
    await login(client, student.email)
    response = await client.get(URL)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_ac1_a_conditional_offer_is_the_current_step(client, db_session):
    student, uni, app = await world(db_session, "offer", offer_type="conditional", offer_date=date.today(), submitted_on=date.today())
    body = await read(client, student)
    [item] = body["applications"]
    assert item["id"] == str(app.id) and item["application_code"] == app.application_code and item["university"] == uni.name
    assert item["current"] == {"key": "offer", "label": "Conditional offer"} and item["closed"] is False
    assert [s["state"] for s in item["steps"]][:5] == ["done"] * 4 + ["current"]


@pytest.mark.asyncio
async def test_ac2_a_refused_visa_is_the_final_outcome_without_the_reason(client, db_session):
    student, _, app = await world(db_session, "status_tracking", outcome="visa_refused")
    db_session.add(VisaCase(application_id=app.id, status="decision", visa_status="refused", decision="refused", refusal_reason="SECRET-REASON", checklist=[]))
    await db_session.commit()
    body = await read(client, student)
    [item] = body["applications"]
    assert item["current"]["label"] == "Visa decision: Rejected" and item["closed"] is True
    assert item["steps"][-1] == {"key": "final", "label": "Final outcome: Visa rejected", "state": "stopped"}
    assert "SECRET-REASON" not in str(body)


@pytest.mark.asyncio
async def test_ac3_missing_documents_link_to_upload(client, db_session):
    student, uni, app = await world(db_session, "visa_documentation")
    db_session.add(VisaCase(application_id=app.id, status="documentation", visa_status="preparing", checklist=["Passport", "Bank statement", "Photo"]))
    db_session.add_all([doc(student, app, "Passport", "verified"), doc(student, app, "Bank statement", "reupload_required")])
    db_session.add(ApplicationChecklist(application_id=app.id, gate_mode="warn"))
    await db_session.flush()
    db_session.add_all(
        [
            ApplicationChecklistItem(application_id=app.id, position=1, document_type="Transcript", required=True, allowed_statuses=[]),
            ApplicationChecklistItem(application_id=app.id, position=2, document_type="CV", required=False, allowed_statuses=[]),  # optional: not listed
            requested := ApplicationChecklistItem(application_id=app.id, position=3, document_type="SOP", required=True, allowed_statuses=[]),
        ]
    )
    await db_session.flush()
    due = date.today() + timedelta(days=3)
    db_session.add(DocumentRequest(student_user_id=student.id, application_id=app.id, checklist_item_id=requested.id, document_type="SOP", due_date=due))
    await db_session.commit()
    body = await read(client, student)
    missing = {(m["name"], m["source"], m["status_label"]) for m in body["missing_documents"]}
    assert missing == {
        ("SOP", "Document request", "Requested"),  # the item's open request is listed once, as the request
        ("Transcript", "Admission checklist", "Missing"),
        ("Bank statement", "Visa checklist", "Re-upload required"),
        ("Photo", "Visa checklist", "Not uploaded"),
    }
    assert {m["upload_url"] for m in body["missing_documents"]} == {UPLOAD}
    assert all(m["university"] == uni.name and m["application_code"] == app.application_code for m in body["missing_documents"])
    assert next(m for m in body["missing_documents"] if m["name"] == "SOP")["due_date"] == due.isoformat()
    assert body["next_actions"][0] == {"text": "Upload 4 missing documents", "href": UPLOAD}
    assert body["applications"][0]["steps"][5]["label"] == "Documentation pending"


@pytest.mark.asyncio
async def test_a_complete_visa_checklist_reads_documentation_completed(client, db_session):
    student, _, app = await world(db_session, "visa_documentation")
    db_session.add(VisaCase(application_id=app.id, status="documentation", visa_status="preparing", checklist=["Passport"], appointment_date=date.today()))
    db_session.add(doc(student, app, "Passport", "verified"))
    await db_session.commit()
    body = await read(client, student)
    assert body["applications"][0]["current"]["label"] == "Documentation completed"
    assert body["missing_documents"] == [] and body["next_actions"] == []


@pytest.mark.asyncio
async def test_next_actions_from_the_offer_deposit_visa_and_counselor(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    student, uni, app = await world(db_session, "offer", offer_type="unconditional", offer_date=date.today(), next_action="Send your passport copy")
    deadline = date.today() + timedelta(days=10)
    db_session.add(ApplicationOffer(application_id=app.id, offer_type="unconditional", issue_date=date.today(), offer_deadline=deadline))
    db_session.add(
        ApplicationDepositRecord(application_id=app.id, required=True, amount=500, currency="GBP", due_date=deadline, payment_status="pending", recorded_by_id=counselor.id, updated_by_id=counselor.id)
    )
    visa_uni = await mk_university(db_session, name=uniq("Visa Uni"))
    visa_app = await mk_application(db_session, student=student, university=visa_uni, status="visa_documentation")
    db_session.add(VisaCase(application_id=visa_app.id, status="checklist", visa_status="not_started", checklist=[]))
    info_app = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("Info Uni")), status="status_tracking")
    db_session.add(VisaCase(application_id=info_app.id, status="tracking", visa_status="additional_info_requested", checklist=[]))
    await db_session.commit()
    texts = [a["text"] for a in (await read(client, student))["next_actions"]]
    assert "Send your passport copy" in texts
    assert f"Tell your counselor whether you accept the offer from {uni.name} by {deadline:%d %b %Y}" in texts
    assert f"Pay the deposit for {uni.name} by {deadline:%d %b %Y}" in texts
    assert f"Book your visa appointment ({visa_uni.name})" in texts
    assert any(t.startswith("Send the additional information the visa office asked for") for t in texts)


@pytest.mark.asyncio
async def test_a_withdrawn_application_stops_where_it_was_and_has_no_actions(client, db_session):
    student, _, app = await world(db_session, "withdrawn", next_action="Ignored once closed")
    db_session.add(ApplicationStatusHistory(application_id=app.id, from_status="university_selection", to_status="withdrawn"))
    db_session.add(VisaCase(application_id=app.id, status="checklist", visa_status="not_started", checklist=["Passport"]))
    await db_session.commit()
    body = await read(client, student)
    [item] = body["applications"]
    assert item["closed"] is True and item["current"]["label"] == "Final outcome: Withdrawn"
    assert [s["state"] for s in item["steps"]][:3] == ["done", "done", "stopped"]
    assert body["missing_documents"] == [] and body["next_actions"] == []


@pytest.mark.asyncio
async def test_live_applications_come_first(client, db_session):
    student, _, closed = await world(db_session, "offer", outcome="rejected")
    live = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("Live Uni")), status="enquiry")
    body = await read(client, student)
    assert [a["id"] for a in body["applications"]] == [str(live.id), str(closed.id)]


@pytest.mark.asyncio
async def test_only_the_students_own_rows(client, db_session):
    student, _, _ = await world(db_session, "offer")
    other, _, other_app = await world(db_session, "enquiry")
    db_session.add(DocumentRequest(student_user_id=other.id, document_type="Other's passport"))
    await db_session.commit()
    body = await read(client, student)
    assert str(other_app.id) not in str(body) and "Other's passport" not in str(body)


@pytest.mark.asyncio
async def test_no_applications_is_an_empty_page(client, db_session):
    student = await mk_user(db_session, role="overseas_student")
    assert await read(client, student) == {"applications": [], "missing_documents": [], "next_actions": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["counselor", "overseas_admin", "agent", "university_rep"])
async def test_staff_roles_are_forbidden(client, db_session, role):
    user = await mk_user(db_session, role=role)
    await login(client, user.email)
    assert (await client.get(URL)).status_code == 403


@pytest.mark.asyncio
async def test_the_portal_section_is_a_header_only(client, db_session):
    student, _, _ = await world(db_session, "offer")
    await login(client, student.email)
    response = await client.get("/api/v1/portal/overseas/student/progress")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Progress" and body["rows"] == [] and body["columns"] == []


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(URL)).status_code == 401
