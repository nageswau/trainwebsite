"""ccrm-020 (DEC-SCOPE-266, R1-R9) -- a counselor's / Overseas Admin's document requests to a direct student: create (rules, scope,
duplicate, notice), the student's list and upload against a request, the counselor's review (verified keeps it fulfilled, a rejection
reopens it), the checklist tie (mark Requested, auto-link, Verified leaves "missing"), cancel, overdue, and the AGN-009 agency list
untouched. Spec: docs/superpowers/specs/2026-10-25-ccrm-020-document-requests-design.md."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio

from app.models import ApplicationChecklistItem, DocumentRequest, StudentDocument
from tests.agn001_helpers import client_for, mk_user
from tests.agn009_helpers import REQUESTS, VERIFY, audit_actions, events_of, upload_files
from tests.agn023_helpers import notices
from tests.ccrm025_helpers import offers_world

STAFF = "/api/v1/counselor/students/{}/document-requests"
CANCEL = STAFF + "/{}/cancel"
MINE = "/api/v1/overseas/me/document-requests"
UPLOAD = MINE + "/{}/upload"
CHECKLIST = "/api/v1/workflows/overseas/applications/{}/checklist"


def _today():
    return datetime.now(UTC).astimezone(ZoneInfo("Asia/Kolkata")).date()


def _due(days: int = 7) -> str:
    return (_today() + timedelta(days=days)).isoformat()


@pytest_asyncio.fixture
async def w(db_session):
    return await offers_world(db_session)


async def _request(c, student, **body):
    return await c.post(STAFF.format(student.id), json={"document_type": "English test", "due_date": _due(), **body})


async def _fresh(db, model, id_):
    return await db.get(model, id_, populate_existing=True)


# --- create ---------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_counselor_requests_a_document_and_the_student_is_told(db_session, w):
    student = w["direct_student"]
    async with client_for(w["counselor"].email) as c:
        r = await _request(c, student, document_type="Other", document_label="IELTS scorecard", note="Academic, 6.5 overall")
        listed = (await c.get(STAFF.format(student.id))).json()
    assert r.status_code == 201, r.text
    req = r.json()["request"]
    assert (req["name"], req["status"], req["due_date"], req["overdue"], req["requested_by"]) == ("IELTS scorecard", "open", _due(), False, w["counselor"].full_name)
    assert req["note"] == "Academic, 6.5 overall" and req["document"] is None
    assert [i["id"] for i in listed["items"]] == [req["id"]] and listed["total"] == 1
    told = [n for n in await notices(db_session, student) if n.title == "Document requested"]
    assert len(told) == 1 and "IELTS scorecard" in told[0].body and "6.5" not in told[0].body  # never the note (R6)
    assert [e.event for e in await events_of(db_session, request_id=req["id"])] == ["requested"]
    assert await audit_actions(db_session, req["id"]) == ["document_request.create"]


@pytest.mark.asyncio
async def test_create_rules(db_session, w):
    student = w["direct_student"]
    async with client_for(w["counselor"].email) as c:
        past = await _request(c, student, due_date=(_today() - timedelta(days=1)).isoformat())
        no_due = await c.post(STAFF.format(student.id), json={"document_type": "CV"})
        no_label = await _request(c, student, document_type="Other")
        offer = await _request(c, student, document_type="Offer letter")
        no_type = await c.post(STAFF.format(student.id), json={"due_date": _due()})
        first = await _request(c, student)
        dup = await _request(c, student)
        other_app = await _request(c, student, application_id=str(w["app"].id))  # an agency application, not this student's
    assert [x.status_code for x in (past, no_due, no_label, offer, no_type)] == [422, 422, 422, 422, 422]
    assert first.status_code == 201 and dup.status_code == 409 and other_app.status_code == 422


@pytest.mark.asyncio
async def test_scope_admin_yes_other_counselor_and_roles_no(db_session, w):
    student = w["direct_student"]
    async with client_for(w["admin"].email) as c:
        admin = await _request(c, student, document_type="Passport")
    async with client_for(w["counselor2"].email) as c:
        outside = await _request(c, student, document_type="CV")
        outside_list = await c.get(STAFF.format(student.id))
        outside_cancel = await c.post(CANCEL.format(student.id, admin.json()["request"]["id"]))
    async with client_for(w["it_counselor"].email, division="it") as c:
        it = await _request(c, student)
    async with client_for(student.email) as c:
        own = await _request(c, student)
    assert admin.status_code == 201 and admin.json()["request"]["requested_by"] == w["admin"].full_name
    assert (outside.status_code, outside_list.status_code, outside_cancel.status_code) == (404, 404, 404)
    assert it.status_code == 403 and own.status_code == 403


# --- student list and upload ------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_student_sees_the_request_and_uploads_against_it(db_session, w):
    student, app = w["direct_student"], w["direct_app"]
    other = await mk_user(db_session, role="overseas_student", full_name="Other Student")
    async with client_for(w["counselor"].email) as c:
        req = (await _request(c, student, application_id=str(app.id))).json()["request"]
    async with client_for(other.email) as c:
        theirs = (await c.get(MINE)).json()
        foreign = await c.post(UPLOAD.format(req["id"]), files=upload_files())
    async with client_for(student.email) as c:
        mine = (await c.get(MINE)).json()
        wrong = await c.post(UPLOAD.format(req["id"]), files=upload_files(b"not a pdf", "x.txt", "text/plain"))
        r = await c.post(UPLOAD.format(req["id"]), files=upload_files(), data={"expiry_date": _due(400)})
        again = await c.post(UPLOAD.format(req["id"]), files=upload_files())
    assert theirs["items"] == [] and foreign.status_code == 404
    assert [i["id"] for i in mine["items"]] == [req["id"]] and mine["items"][0]["due_date"] == _due()
    assert wrong.status_code == 415
    assert r.status_code == 201, r.text
    assert r.json()["request"]["status"] == "fulfilled" and r.json()["request"]["document"]["verification_status"] == "pending"
    assert again.status_code == 409
    doc = await _fresh(db_session, StudentDocument, r.json()["document_id"])
    assert (doc.student_id, doc.application_id, doc.document_type, doc.uploaded_by_user_id) == (student.id, app.id, "English test", student.id)
    assert str(doc.fulfils_request_id) == req["id"]
    assert doc.expiry_date.isoformat() == _due(400) and doc.file_url.startswith("agent-documents/")
    assert [e.event for e in await events_of(db_session, request_id=req["id"])] == ["requested", "fulfilled"]
    assert any(n.title == "Document uploaded" for n in await notices(db_session, w["counselor"]))


@pytest.mark.asyncio
async def test_verified_keeps_it_fulfilled_a_rejection_reopens_it(db_session, w):
    student = w["direct_student"]
    async with client_for(w["counselor"].email) as c:
        req = (await _request(c, student, document_type="Transcripts")).json()["request"]
    async with client_for(student.email) as c:
        first = (await c.post(UPLOAD.format(req["id"]), files=upload_files())).json()["document_id"]
    async with client_for(w["counselor"].email) as c:
        assert (await c.patch(VERIFY.format(first), json={"verification_status": "reupload_required", "notes": "Page 2 missing"})).status_code == 200
        reopened = (await c.get(STAFF.format(student.id))).json()["items"][0]
    assert reopened["status"] == "open" and reopened["document"] is None
    assert reopened["review_note"] == "Page 2 missing"  # browser QA-01: why it is back, for the counselor and the student
    async with client_for(student.email) as c:
        assert (await c.get(MINE)).json()["items"][0]["review_note"] == "Page 2 missing"
    assert (await _fresh(db_session, StudentDocument, first)).fulfils_request_id is None  # the rejected file stays, unlinked
    async with client_for(student.email) as c:
        second = (await c.post(UPLOAD.format(req["id"]), files=upload_files())).json()["document_id"]
    async with client_for(w["counselor"].email) as c:
        assert (await c.patch(VERIFY.format(second), json={"verification_status": "verified"})).status_code == 200
        done = (await c.get(STAFF.format(student.id))).json()["items"][0]
    assert done["status"] == "fulfilled" and done["document"]["id"] == second and done["document"]["verification_status"] == "verified"
    assert done["review_note"] is None  # only an open (reopened) request carries it
    events = [(e.event, e.from_status, e.to_status) for e in await events_of(db_session, request_id=req["id"])]
    assert events == [("requested", None, "open"), ("fulfilled", None, "fulfilled"), ("requested", "fulfilled", "open"), ("fulfilled", None, "fulfilled")]


# --- checklist tie (R2) -------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_checklist_request_marks_links_and_clears_from_missing(db_session, w):
    student, app = w["direct_student"], w["direct_app"]
    async with client_for(w["counselor"].email) as c:
        assert (await c.post(CHECKLIST.format(app.id))).status_code == 201
        added = await c.post(CHECKLIST.format(app.id) + "/items", json={"document_type": "English test", "label": "IELTS scorecard"})
        item_id = added.json()["checklist"]["items"][0]["id"]
        wrong_item = await c.post(STAFF.format(student.id), json={"due_date": _due(), "checklist_item_id": item_id})  # needs the application
        r = await c.post(STAFF.format(student.id), json={"due_date": _due(), "application_id": str(app.id), "checklist_item_id": item_id})
        payload = (await c.get(CHECKLIST.format(app.id))).json()
        marked = payload["checklist"]
    assert wrong_item.status_code == 422
    assert payload["student_id"] == str(student.id) and marked["items"][0]["open_request"]["due_date"] == _due()  # the row's request
    assert r.status_code == 201, r.text
    assert (r.json()["request"]["document_type"], r.json()["request"]["name"]) == ("English test", "IELTS scorecard")  # the item's
    assert marked["items"][0]["status"] == "requested" and marked["summary"]["missing"][0]["label"] == "IELTS scorecard"
    async with client_for(student.email) as c:
        doc = (await c.post(UPLOAD.format(r.json()["request"]["id"]), files=upload_files())).json()["document_id"]
    async with client_for(w["counselor"].email) as c:
        linked = (await c.get(CHECKLIST.format(app.id))).json()["checklist"]
        await c.patch(VERIFY.format(doc), json={"verification_status": "verified"})
        done = (await c.get(CHECKLIST.format(app.id))).json()["checklist"]
    assert linked["items"][0]["open_request"] is None
    assert linked["items"][0]["mark"] is None and linked["items"][0]["status"] == "pending" and [d["id"] for d in linked["items"][0]["documents"]] == [doc]
    assert done["items"][0]["status"] == "verified" and done["summary"]["missing"] == [] and done["documents_completed_on"] is not None


# --- cancel, overdue, agency regression --------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_closes_it_tells_the_student_and_clears_the_mark(db_session, w):
    student, app = w["direct_student"], w["direct_app"]
    async with client_for(w["counselor"].email) as c:
        await c.post(CHECKLIST.format(app.id))
        item_id = (await c.post(CHECKLIST.format(app.id) + "/items", json={"document_type": "CV"})).json()["checklist"]["items"][0]["id"]
        req = (await c.post(STAFF.format(student.id), json={"due_date": _due(), "application_id": str(app.id), "checklist_item_id": item_id})).json()["request"]
        r = await c.post(CANCEL.format(student.id, req["id"]))
        again = await c.post(CANCEL.format(student.id, req["id"]))
    async with client_for(student.email) as c:
        late = await c.post(UPLOAD.format(req["id"]), files=upload_files())
        mine = (await c.get(MINE)).json()
        everything = (await c.get(MINE + "?status=all")).json()
    assert r.status_code == 200 and r.json()["request"]["status"] == "cancelled" and again.status_code == 409 and late.status_code == 409
    assert (await _fresh(db_session, ApplicationChecklistItem, item_id)).mark is None
    assert any(n.title == "Document request cancelled" for n in await notices(db_session, student))
    assert mine["items"] == [] and [i["status"] for i in everything["items"]] == ["cancelled"]  # open is the student's default view
    assert await audit_actions(db_session, req["id"]) == ["document_request.create", "document_request.cancel"]


@pytest.mark.asyncio
async def test_the_staff_list_shows_open_requests_first(db_session, w):
    student = w["direct_student"]
    async with client_for(w["counselor"].email) as c:
        older = (await _request(c, student, document_type="Passport")).json()["request"]
        newer = (await _request(c, student, document_type="CV")).json()["request"]
        await c.post(CANCEL.format(student.id, newer["id"]))
        listed = (await c.get(STAFF.format(student.id))).json()["items"]
    assert [i["id"] for i in listed] == [older["id"], newer["id"]]  # browser QA-02: open before closed, even when older


@pytest.mark.asyncio
async def test_an_open_request_past_its_due_date_is_overdue(db_session, w):
    student = w["direct_student"]
    async with client_for(w["counselor"].email) as c:
        req = (await _request(c, student)).json()["request"]
    row = await _fresh(db_session, DocumentRequest, req["id"])
    row.due_date = _today() - timedelta(days=2)
    await db_session.commit()
    async with client_for(w["counselor"].email) as c:
        staff = (await c.get(STAFF.format(student.id))).json()["items"][0]
    async with client_for(student.email) as c:
        own = (await c.get(MINE)).json()["items"][0]
    assert staff["overdue"] is True and own["overdue"] is True


@pytest.mark.asyncio
async def test_the_agency_request_list_never_shows_a_direct_students_request(db_session, w):
    async with client_for(w["counselor"].email) as c:
        assert (await _request(c, w["direct_student"])).status_code == 201
    async with client_for(w["master"].email) as c:
        agency = await c.get(REQUESTS + "?status=all")
    assert agency.status_code == 200 and agency.json()["items"] == []
