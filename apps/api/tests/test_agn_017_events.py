"""AGN-017 AC1-AC3, AC7 -- each agency event creates exactly one notice per recipient, in the request's transaction; refused or no-op
writes create none; bodies carry no names or user-typed text."""

import pytest
import pytest_asyncio

from app.models import OverseasApplication, University
from tests.agn001_helpers import client_for, mk_user
from tests.agn004_helpers import RECORDS, mk_record
from tests.agn008_helpers import APPS, agency_world, mk_application
from tests.agn009_helpers import REQUESTS, VERIFY, mk_doc
from tests.agn009_helpers import world as docs_world
from tests.agn016_helpers import mk_task
from tests.agn017_helpers import all_text, channels_of, deactivate, notices, titled

ASSIGNED = "Student assigned to you"


@pytest_asyncio.fixture
async def world(db_session):
    return await agency_world(db_session)


# --- assignment (N1, N9) ---------------------------------------------------------------------------------------------------------


async def _assign(world, member_id):
    async with client_for(world["master"].email) as c:
        return await c.post(f"{RECORDS}/{world['record'].id}/assign", json={"member_id": str(member_id) if member_id else None})


@pytest.mark.asyncio
async def test_reassigning_tells_only_the_new_assignee_with_the_open_tasks_that_moved(db_session, world):
    for status in ("open", "open", "done"):
        await mk_task(db_session, record=world["record"], author=world["master"], status=status)
    response = await _assign(world, world["other_staff"]["member"].id)
    assert response.status_code == 200, response.text
    [item] = await notices(db_session, world["other_staff"]["user"])
    assert (item.title, item.action_url) == (ASSIGNED, "/overseas/agent/students")
    assert item.body == "A student is now assigned to you. 2 open tasks moved with them."
    assert world["record"].full_name not in item.body
    assert await channels_of(db_session, item) == ["email"]
    assert await notices(db_session, world["staff"]["user"]) == []  # N9: the previous assignee is not told
    assert await notices(db_session, world["master"]) == []  # the actor


@pytest.mark.asyncio
async def test_assigning_a_student_without_open_tasks_omits_the_count(db_session, world):
    await _assign(world, world["other_staff"]["member"].id)
    [item] = await notices(db_session, world["other_staff"]["user"])
    assert item.body == "A student is now assigned to you."


@pytest.mark.asyncio
async def test_reassigning_the_current_assignee_or_unassigning_notifies_nobody(db_session, world):
    assert (await _assign(world, world["staff"]["member"].id)).status_code == 200
    assert (await _assign(world, None)).status_code == 200
    for user in (world["staff"]["user"], world["other_staff"]["user"], world["master"]):
        assert await titled(db_session, user, ASSIGNED) == []


# --- documents (N9, §8) -----------------------------------------------------------------------------------------------------------

REQUESTED, ATTENTION = "Document requested", "Document needs attention"


@pytest_asyncio.fixture
async def dw(db_session):
    return await docs_world(db_session)


@pytest.mark.asyncio
async def test_a_master_request_tells_the_assignee_without_the_label_or_note(db_session, dw):
    body = {"agent_student_id": str(dw["record"].id), "document_type": "Other", "document_label": "rahul@example.com\r\nBcc: x", "note": "call +91 98765 43210"}
    async with client_for(dw["master"].email) as c:
        response = await c.post(REQUESTS, json=body)
    assert response.status_code == 201, response.text
    [item] = await notices(db_session, dw["staff"]["user"])
    assert (item.title, item.body, item.action_url) == (REQUESTED, "A document was requested for one of your students.", "/overseas/agent/documents")
    text = await all_text(db_session)
    for leaked in ("rahul@example.com", "Bcc", "98765", "\r"):
        assert leaked not in text


@pytest.mark.asyncio
async def test_a_known_type_is_named_and_the_requesting_assignee_is_not_told(db_session, dw):
    async with client_for(dw["master"].email) as c:
        await c.post(REQUESTS, json={"agent_student_id": str(dw["record"].id), "document_type": "Passport"})
    [item] = await notices(db_session, dw["staff"]["user"])
    assert item.body == "Passport was requested for one of your students."
    async with client_for(dw["staff"]["user"].email) as c:
        assert (await c.post(REQUESTS, json={"agent_student_id": str(dw["record"].id), "document_type": "CV"})).status_code == 201
    assert len(await titled(db_session, dw["staff"]["user"], REQUESTED)) == 1  # their own request: nobody
    assert await titled(db_session, dw["master"], REQUESTED) == []


@pytest.mark.asyncio
async def test_a_duplicate_open_request_is_refused_and_notifies_nobody(db_session, dw):
    body = {"agent_student_id": str(dw["record"].id), "document_type": "Passport"}
    async with client_for(dw["master"].email) as c:
        assert (await c.post(REQUESTS, json=body)).status_code == 201
        assert (await c.post(REQUESTS, json=body)).status_code == 409
    assert len(await titled(db_session, dw["staff"]["user"], REQUESTED)) == 1


@pytest.mark.parametrize(("outcome", "text"), [("rejected", "rejected"), ("changes_required", "changes required")])
@pytest.mark.asyncio
async def test_a_master_rejection_tells_the_assignee(db_session, dw, outcome, text):
    doc = await mk_doc(db_session, record=dw["record"], document_type="Transcripts")
    async with client_for(dw["master"].email) as c:
        response = await c.patch(VERIFY.format(doc.id), json={"verification_status": outcome, "notes": "blurred -- see rahul@example.com"})
    assert response.status_code == 200, response.text
    [item] = await notices(db_session, dw["staff"]["user"])
    assert (item.title, item.body, item.action_url) == (ATTENTION, f"Transcripts: {text}.", "/overseas/agent/documents")
    assert "rahul@example.com" not in await all_text(db_session)


@pytest.mark.asyncio
async def test_verifying_or_a_second_review_notifies_no_agency_member(db_session, dw):
    doc = await mk_doc(db_session, record=dw["record"])
    async with client_for(dw["master"].email) as c:
        assert (await c.patch(VERIFY.format(doc.id), json={"verification_status": "verified"})).status_code == 200
        assert (await c.patch(VERIFY.format(doc.id), json={"verification_status": "rejected", "notes": "late"})).status_code == 409
    assert await titled(db_session, dw["staff"]["user"], ATTENTION) == []


@pytest.mark.asyncio
async def test_a_counselor_rejection_of_an_agency_document_tells_the_assignee_and_still_the_student(db_session, dw):
    counselor = await mk_user(db_session, role="counselor", full_name="Docs Counselor")
    app = OverseasApplication(agent_id=dw["master"].id, agent_student_id=dw["linked_record"].id, student_id=dw["linked_user"].id, university_id=dw["university"].id, counselor_id=counselor.id, intake="Fall 2027", status="enquiry")
    db_session.add(app)
    await db_session.commit()
    doc = await mk_doc(db_session, student=dw["linked_user"], application=app, document_type="rahul scan 2")
    async with client_for(counselor.email) as c:
        assert (await c.patch(VERIFY.format(doc.id), json={"verification_status": "rejected"})).status_code == 200
    [item] = await notices(db_session, dw["staff"]["user"])
    assert (item.title, item.body) == (ATTENTION, "A document: rejected.")  # a free-text type is never named
    assert [n.title for n in await notices(db_session, dw["linked_user"])] == ["Document reviewed"]  # unchanged


@pytest.mark.asyncio
async def test_a_document_without_an_agency_record_notifies_no_agency_member(db_session, dw):
    counselor = await mk_user(db_session, role="counselor", full_name="Docs Counselor")
    app = OverseasApplication(student_id=dw["linked_user"].id, university_id=dw["university"].id, counselor_id=counselor.id, intake="Fall 2027", status="enquiry")
    db_session.add(app)
    await db_session.commit()
    doc = await mk_doc(db_session, student=dw["linked_user"], application=app)
    async with client_for(counselor.email) as c:
        assert (await c.patch(VERIFY.format(doc.id), json={"verification_status": "rejected"})).status_code == 200
    assert await notices(db_session, dw["staff"]["user"]) == []


# --- status changes (N3, AC3) -----------------------------------------------------------------------------------------------------

STATUS, COMMISSION = "Application status changed", "Commission estimated"
LEGACY = "/api/v1/workflows/overseas/applications"


async def _agency_app(db, world, *, record=None, status="enquiry", counselor=None):
    return await mk_application(db, agent=world["master"], university=world["university"], record=record or world["record"], status=status, counselor_id=counselor.id if counselor else None)


@pytest.mark.asyncio
async def test_a_master_status_change_tells_the_assignee(db_session, world):
    university = await db_session.get(University, world["university"].id)
    university.name = "Uni of\r\nTest"
    await db_session.commit()
    app = await _agency_app(db_session, world)
    async with client_for(world["master"].email) as c:
        response = await c.post(f"{APPS}/{app.id}/status", json={"to_status": "eligibility_evaluation", "expected_status": "enquiry"})
    assert response.status_code == 200, response.text
    [item] = await notices(db_session, world["staff"]["user"])
    assert (item.title, item.body, item.action_url) == (STATUS, "Uni of Test: Enquiry → Eligibility evaluation.", "/overseas/agent/applications")
    assert await channels_of(db_session, item) == ["email"]


@pytest.mark.asyncio
async def test_the_assignee_changing_their_own_students_status_notifies_nobody(db_session, world):
    app = await _agency_app(db_session, world)
    async with client_for(world["staff"]["user"].email) as c:
        assert (await c.post(f"{APPS}/{app.id}/status", json={"to_status": "eligibility_evaluation"})).status_code == 200
    for user in (world["staff"]["user"], world["master"], world["other_staff"]["user"]):
        assert await titled(db_session, user, STATUS) == []


@pytest.mark.asyncio
async def test_a_stale_status_change_is_refused_and_notifies_nobody(db_session, world):
    app = await _agency_app(db_session, world)
    async with client_for(world["master"].email) as c:
        response = await c.post(f"{APPS}/{app.id}/status", json={"to_status": "offer", "expected_status": "university_selection"})
    assert response.status_code == 409
    assert await notices(db_session, world["staff"]["user"]) == []


@pytest.mark.asyncio
async def test_a_deactivated_assignee_sends_the_status_notice_to_the_masters(db_session, world):
    app = await _agency_app(db_session, world)
    await deactivate(db_session, world["staff"]["member"])
    counselor = await mk_user(db_session, role="counselor", full_name="Apps Counselor")
    app.counselor_id = counselor.id
    await db_session.commit()
    async with client_for(counselor.email) as c:
        assert (await c.post(f"{LEGACY}/{app.id}/advance", json={"to_status": "eligibility_evaluation"})).status_code == 200
    assert [n.title for n in await notices(db_session, world["master"])] == [STATUS]


@pytest.mark.asyncio
async def test_a_counselor_advance_tells_the_assignee_and_still_the_student(db_session, world):
    counselor = await mk_user(db_session, role="counselor", full_name="Apps Counselor")
    app = await _agency_app(db_session, world, record=world["linked_record"], counselor=counselor)
    async with client_for(counselor.email) as c:
        assert (await c.post(f"{LEGACY}/{app.id}/advance", json={"to_status": "university_selection"})).status_code == 200
    assert [n.title for n in await notices(db_session, world["staff"]["user"])] == [STATUS]
    assert [n.title for n in await notices(db_session, world["linked_user"])] == ["Application status updated"]  # unchanged


@pytest.mark.asyncio
async def test_a_counselor_patch_of_only_the_next_action_notifies_no_agency_member(db_session, world):
    counselor = await mk_user(db_session, role="counselor", full_name="Apps Counselor")
    app = await _agency_app(db_session, world, counselor=counselor)
    async with client_for(counselor.email) as c:
        assert (await c.patch(f"{LEGACY}/{app.id}", json={"next_action": "Send the transcript"})).status_code == 200
        assert (await c.patch(f"{LEGACY}/{app.id}", json={"status": "offer"})).status_code == 200
    assert [n.title for n in await notices(db_session, world["staff"]["user"])] == [STATUS]


@pytest.mark.asyncio
async def test_an_application_without_an_agency_record_notifies_no_agency_member(db_session, world):
    counselor = await mk_user(db_session, role="counselor", full_name="Apps Counselor")
    app = await mk_application(db_session, agent=world["master"], university=world["university"], student=world["linked_user"], counselor_id=counselor.id)
    async with client_for(counselor.email) as c:
        assert (await c.post(f"{LEGACY}/{app.id}/advance", json={"to_status": "eligibility_evaluation"})).status_code == 200
    for user in (world["staff"]["user"], world["master"]):
        assert await titled(db_session, user, STATUS) == []


@pytest.mark.asyncio
async def test_confirming_enrollment_tells_the_assignee_once_and_the_master_only_about_the_commission(db_session, world):
    app = await _agency_app(db_session, world, status="offer")
    async with client_for(world["master"].email) as c:
        response = await c.put(f"{APPS}/{app.id}/enrollment", json={"enrollment_date": "2027-09-01", "expected_status": "offer"})
    assert response.status_code == 200, response.text
    assert [n.title for n in await notices(db_session, world["staff"]["user"])] == [STATUS]
    assert [n.title for n in await notices(db_session, world["master"])] == [COMMISSION]


@pytest.mark.asyncio
async def test_enrolling_an_unassigned_students_application_gives_each_master_one_notice(db_session, world):
    record = await mk_record(db_session, agent=world["master"], full_name="Unassigned")
    counselor = await mk_user(db_session, role="counselor", full_name="Apps Counselor")
    app = await _agency_app(db_session, world, record=record, status="status_tracking", counselor=counselor)
    async with client_for(counselor.email) as c:
        assert (await c.post(f"{LEGACY}/{app.id}/advance", json={"to_status": "enrolled"})).status_code == 200
    assert [n.title for n in await notices(db_session, world["master"])] == [COMMISSION]  # not also the status notice (AC3)
