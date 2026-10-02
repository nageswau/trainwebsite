"""AGN-009 -- document requests ("Additional", G4/G5; AC4) and the Pending / Uploaded lists (G9)."""

import asyncio

import pytest
import pytest_asyncio

from app.models import AgentStudent, DocumentRequest, StudentDocument
from tests.agn001_helpers import client_for
from tests.agn009_helpers import DOCS, REQUESTS, audit_actions, events_of, mk_doc, upload_files, world


@pytest_asyncio.fixture
async def w(db_session):
    return await world(db_session)


def ask(record, **extra) -> dict:
    return {"agent_student_id": str(record.id), "document_type": "LOR", **extra}


async def open_ids(c, **params) -> list[str]:
    response = await c.get(REQUESTS, params={"status": "open", **params})
    assert response.status_code == 200, response.text
    return [r["id"] for r in response.json()["items"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["master", "staff"])
async def test_master_and_staff_create_a_request(db_session, w, who):
    email = w["master"].email if who == "master" else w["staff"]["user"].email
    async with client_for(email) as c:
        response = await c.post(REQUESTS, json=ask(w["record"], note="Signed by the principal"))
        assert response.status_code == 201, response.text
        body = response.json()["request"]
        assert body["status"] == "open" and body["note"] == "Signed by the principal" and body["student"] == w["record"].full_name
        assert body["id"] in await open_ids(c)
    assert [e.event for e in await events_of(db_session, request_id=body["id"])] == ["requested"]
    assert await audit_actions(db_session, body["id"]) == ["document_request.create"]


@pytest.mark.asyncio
async def test_request_rules(db_session, w):
    async with client_for(w["master"].email) as c:
        assert (await c.post(REQUESTS, json=ask(w["record"]))).status_code == 201
        assert (await c.post(REQUESTS, json=ask(w["record"]))).status_code == 409  # one open request per type + label
        assert (await c.post(REQUESTS, json=ask(w["record"], document_type="Other"))).status_code == 422
        assert (await c.post(REQUESTS, json=ask(w["record"], document_type="Other", document_label="Medical"))).status_code == 201
        assert (await c.post(REQUESTS, json=ask(w["record"], document_type="Other", document_label="Bank letter"))).status_code == 201
        assert (await c.post(REQUESTS, json=ask(w["record"], document_type="Visa"))).status_code == 422
        assert (await c.post(REQUESTS, json=ask(w["record"], surprise=True))).status_code == 422
    async with client_for(w["plain"]["user"].email) as c:
        assert (await c.post(REQUESTS, json=ask(w["record"], document_type="CV"))).status_code == 404
    async with client_for(w["other"]["master"].email) as c:
        assert (await c.post(REQUESTS, json=ask(w["record"], document_type="CV"))).status_code == 404


@pytest.mark.asyncio
async def test_archived_student_takes_no_request(db_session, w):
    record = await db_session.get(AgentStudent, w["record"].id)
    record.status = "archived"
    await db_session.commit()
    async with client_for(w["master"].email) as c:
        assert (await c.post(REQUESTS, json=ask(w["record"]))).status_code == 409


@pytest.mark.asyncio
async def test_cancel(db_session, w):
    async with client_for(w["staff"]["user"].email) as c:
        request_id = (await c.post(REQUESTS, json=ask(w["record"]))).json()["request"]["id"]
        first = await c.post(f"{REQUESTS}/{request_id}/cancel")
        again = await c.post(f"{REQUESTS}/{request_id}/cancel")
        assert first.status_code == 200 and first.json()["request"]["status"] == "cancelled"
        assert again.status_code == 409
        assert request_id not in await open_ids(c)
    async with client_for(w["plain"]["user"].email) as c:
        assert (await c.post(f"{REQUESTS}/{request_id}/cancel")).status_code == 404
    assert [e.event for e in await events_of(db_session, request_id=request_id)] == ["requested", "cancelled"]


@pytest.mark.asyncio
async def test_a_request_shows_under_additional_until_an_upload_fulfils_it(db_session, w):
    async with client_for(w["master"].email) as c:
        request_id = (await c.post(REQUESTS, json=ask(w["record"]))).json()["request"]["id"]
        assert request_id in await open_ids(c)  # AC4
        upload = await c.post(DOCS, data={"agent_student_id": str(w["record"].id), "document_type": "LOR", "request_id": request_id}, files=upload_files())
        assert upload.status_code == 201, upload.text
        assert upload.json()["document"]["fulfils_request_id"] == request_id
        assert request_id not in await open_ids(c)
        listed = (await c.get(REQUESTS, params={"status": "all"})).json()["items"]
        fulfilled = next(r for r in listed if r["id"] == request_id)
        assert fulfilled["status"] == "fulfilled" and fulfilled["fulfilled_by_document_id"] == upload.json()["document"]["id"]
        again = await c.post(DOCS, data={"agent_student_id": str(w["record"].id), "document_type": "LOR", "request_id": request_id}, files=upload_files())
        assert again.status_code == 409
    assert [e.event for e in await events_of(db_session, request_id=request_id)] == ["requested", "fulfilled"]


@pytest.mark.asyncio
async def test_a_request_of_another_student_is_refused(db_session, w):
    async with client_for(w["master"].email) as c:
        request_id = (await c.post(REQUESTS, json=ask(w["unassigned"]))).json()["request"]["id"]
        response = await c.post(DOCS, data={"agent_student_id": str(w["record"].id), "document_type": "LOR", "request_id": request_id}, files=upload_files())
    assert response.status_code == 422
    assert (await db_session.get(DocumentRequest, request_id)).status == "open"


@pytest.mark.asyncio
async def test_concurrent_fulfilment_has_one_winner(db_session, w):
    async with client_for(w["master"].email) as c:
        request_id = (await c.post(REQUESTS, json=ask(w["record"]))).json()["request"]["id"]
    data = {"agent_student_id": str(w["record"].id), "document_type": "LOR", "request_id": request_id}

    async def send(email):
        async with client_for(email) as c:
            return await c.post(DOCS, data=data, files=upload_files())

    results = await asyncio.gather(send(w["master"].email), send(w["staff"]["user"].email))
    assert sorted(r.status_code for r in results) == [201, 409]
    rows = (await db_session.execute(StudentDocument.__table__.select().where(StudentDocument.fulfils_request_id == request_id))).all()
    assert len(rows) == 1


# --- lists ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_and_uploaded_views(db_session, w):
    pending = await mk_doc(db_session, record=w["record"])
    verified = await mk_doc(db_session, record=w["record"], status="verified", verified_by=w["master"])
    legacy = await mk_doc(db_session, student=w["linked_user"], key="uploads/legacy.pdf")
    async with client_for(w["master"].email) as c:
        pending_ids = [d["id"] for d in (await c.get(DOCS, params={"view": "pending", "limit": 100})).json()["items"]]
        uploaded = (await c.get(DOCS, params={"view": "uploaded", "limit": 100})).json()
        bad = await c.get(DOCS, params={"view": "everything"})
    assert str(pending.id) in pending_ids and str(verified.id) not in pending_ids and str(legacy.id) in pending_ids
    assert {str(pending.id), str(verified.id), str(legacy.id)} <= {d["id"] for d in uploaded["items"]}
    assert set(uploaded) == {"items", "total", "limit", "offset"}
    assert all("file_url" not in d for d in uploaded["items"])
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_student_filter_and_staff_scope(db_session, w):
    mine = await mk_doc(db_session, record=w["record"])
    linked = await mk_doc(db_session, record=w["linked_record"])
    elsewhere = await mk_doc(db_session, record=w["unassigned"])
    async with client_for(w["staff"]["user"].email) as c:
        all_ids = {d["id"] for d in (await c.get(DOCS, params={"view": "uploaded", "limit": 100})).json()["items"]}
        filtered = {d["id"] for d in (await c.get(DOCS, params={"view": "uploaded", "student": str(w["record"].id)})).json()["items"]}
        foreign_filter = await c.get(DOCS, params={"view": "uploaded", "student": str(w["unassigned"].id)})
    assert {str(mine.id), str(linked.id)} <= all_ids and str(elsewhere.id) not in all_ids
    assert filtered == {str(mine.id)}
    assert foreign_filter.status_code == 404


@pytest.mark.asyncio
async def test_other_agency_lists_nothing_of_ours(db_session, w):
    doc = await mk_doc(db_session, record=w["record"])
    async with client_for(w["master"].email) as c:
        await c.post(REQUESTS, json=ask(w["record"], document_type="CV"))
    async with client_for(w["other"]["master"].email) as c:
        docs = (await c.get(DOCS, params={"view": "uploaded", "limit": 100})).json()["items"]
        requests = (await c.get(REQUESTS, params={"status": "all", "limit": 100})).json()["items"]
    assert str(doc.id) not in {d["id"] for d in docs}
    assert all(r["agent_student_id"] != str(w["record"].id) for r in requests)
