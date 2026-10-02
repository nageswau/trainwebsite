"""AGN-009 -- the agent review rules (G1/G2 on top of DEC-SCOPE-044 P1/P5/P6; AC2, AC3) and a document's history (AC5)."""

import pytest
import pytest_asyncio

from app.models import StudentDocument
from tests.agn001_helpers import client_for
from tests.agn009_helpers import DOCS, DOWNLOAD, REQUESTS, VERIFY, events_of, mk_doc, upload_files, world


@pytest_asyncio.fixture
async def w(db_session):
    return await world(db_session)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["rejected", "changes_required"])
@pytest.mark.parametrize("notes", [None, "", "   "])
async def test_master_needs_a_reason_to_reject_or_ask_for_changes(db_session, w, outcome, notes):
    doc = await mk_doc(db_session, record=w["record"])
    async with client_for(w["master"].email) as c:
        response = await c.patch(VERIFY.format(doc.id), json={"verification_status": outcome, "notes": notes})
    assert response.status_code == 422, response.text  # AC3
    assert (await db_session.get(StudentDocument, doc.id, populate_existing=True)).verification_status == "pending"
    assert await events_of(db_session, doc.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["rejected", "changes_required"])
async def test_master_rejects_with_a_reason(db_session, w, outcome):
    doc = await mk_doc(db_session, record=w["record"])
    async with client_for(w["master"].email) as c:
        response = await c.patch(VERIFY.format(doc.id), json={"verification_status": outcome, "notes": "  Scan is blurred  "})
    assert response.status_code == 200, response.text
    row = await db_session.get(StudentDocument, doc.id, populate_existing=True)
    assert row.verification_status == outcome and row.reviewer_notes == "Scan is blurred"
    assert [(e.event, e.notes) for e in await events_of(db_session, doc.id)] == [(outcome, "Scan is blurred")]


@pytest.mark.asyncio
async def test_verify_needs_no_reason(db_session, w):
    doc = await mk_doc(db_session, record=w["record"])
    async with client_for(w["staff"]["user"].email) as c:
        response = await c.patch(VERIFY.format(doc.id), json={"verification_status": "verified"})
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("notes", [None, "Blurred"])
async def test_staff_reject_without_reason_is_403(db_session, w, notes):
    """Staff cannot reject (§6 ❌, P6) -- with or without a reason; the role rule answers before the reason rule."""
    doc = await mk_doc(db_session, record=w["record"])
    async with client_for(w["staff"]["user"].email) as c:
        response = await c.patch(VERIFY.format(doc.id), json={"verification_status": "rejected", "notes": notes})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_history_lists_every_event_in_order(db_session, w):
    async with client_for(w["master"].email) as c:
        doc_id = (await c.post(DOCS, data={"agent_student_id": str(w["record"].id), "document_type": "Passport"}, files=upload_files())).json()["document"]["id"]
        assert (await c.get(DOWNLOAD.format(doc_id))).status_code == 200
        assert (await c.patch(VERIFY.format(doc_id), json={"verification_status": "rejected", "notes": "Expired"})).status_code == 200
    async with client_for(w["staff"]["user"].email) as c:
        assert (await c.put(f"{DOCS}/{doc_id}/file", files=upload_files())).status_code == 200
        assert (await c.patch(VERIFY.format(doc_id), json={"verification_status": "verified"})).status_code == 200
        response = await c.get(f"{DOCS}/{doc_id}/history")
    assert response.status_code == 200, response.text
    page = response.json()
    assert set(page) == {"items", "total", "limit", "offset"} and page["total"] == 5
    steps = [(e["event"], e["actor"], e["from_status"], e["to_status"]) for e in page["items"]]
    master, staff = w["master"].full_name, w["staff"]["user"].full_name
    assert steps == [  # AC5
        ("uploaded", master, None, "pending"),
        ("downloaded", master, None, None),
        ("rejected", master, "pending", "rejected"),
        ("replaced", staff, "rejected", "pending"),
        ("verified", staff, "pending", "verified"),
    ]
    assert page["items"][2]["notes"] == "Expired"
    assert all("file_key" not in e for e in page["items"])


@pytest.mark.asyncio
async def test_history_includes_the_request_it_fulfilled(db_session, w):
    async with client_for(w["master"].email) as c:
        request_id = (await c.post(REQUESTS, json={"agent_student_id": str(w["record"].id), "document_type": "SOP", "note": "Two pages"})).json()["request"]["id"]
        doc_id = (await c.post(DOCS, data={"agent_student_id": str(w["record"].id), "document_type": "SOP", "request_id": request_id}, files=upload_files())).json()["document"]["id"]
        page = (await c.get(f"{DOCS}/{doc_id}/history")).json()
    assert [(e["event"], e["notes"]) for e in page["items"]] == [("requested", "Two pages"), ("uploaded", None), ("fulfilled", None)]


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["plain", "other"])
async def test_history_out_of_scope_is_404(db_session, w, who):
    doc = await mk_doc(db_session, record=w["record"])
    email = w["plain"]["user"].email if who == "plain" else w["other"]["master"].email
    async with client_for(email) as c:
        assert (await c.get(f"{DOCS}/{doc.id}/history")).status_code == 404
