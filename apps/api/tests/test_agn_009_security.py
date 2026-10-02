"""AGN-009 -- security sweep (spec §4.5): role gate, IDOR on every id-taking route, a student shared by two agencies, logs."""

import logging

import pytest
import pytest_asyncio

from app.models import AgentStudent
from tests.agn001_helpers import client_for, mk_user
from tests.agn009_helpers import DOCS, DOWNLOAD, REQUESTS, VERIFY, mk_doc, upload_files, world


@pytest_asyncio.fixture
async def w(db_session):
    return await world(db_session)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["counselor", "overseas_student", "overseas_admin", "university_rep"])
async def test_only_agency_members_use_the_agency_routes(db_session, w, role):
    user = await mk_user(db_session, role=role)
    doc = await mk_doc(db_session, record=w["record"])
    async with client_for(user.email) as c:
        responses = [
            await c.get(DOCS),
            await c.get(REQUESTS),
            await c.post(DOCS, data={"agent_student_id": str(w["record"].id), "document_type": "CV"}, files=upload_files()),
            await c.put(f"{DOCS}/{doc.id}/file", files=upload_files()),
            await c.get(f"{DOCS}/{doc.id}/history"),
            await c.post(REQUESTS, json={"agent_student_id": str(w["record"].id), "document_type": "CV"}),
        ]
    assert [r.status_code for r in responses] == [403] * len(responses)


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["plain", "other"])
async def test_every_id_route_hides_what_is_out_of_scope(db_session, w, who):
    doc = await mk_doc(db_session, record=w["record"])
    async with client_for(w["master"].email) as c:
        request_id = (await c.post(REQUESTS, json={"agent_student_id": str(w["record"].id), "document_type": "CV"})).json()["request"]["id"]
    email = w["plain"]["user"].email if who == "plain" else w["other"]["master"].email
    async with client_for(email) as c:
        assert (await c.get(f"{DOCS}/{doc.id}/history")).status_code == 404
        assert (await c.put(f"{DOCS}/{doc.id}/file", files=upload_files())).status_code == 404
        assert (await c.post(f"{REQUESTS}/{request_id}/cancel")).status_code == 404
        assert (await c.get(DOWNLOAD.format(doc.id))).status_code == 403
        assert (await c.patch(VERIFY.format(doc.id), json={"verification_status": "rejected", "notes": "x"})).status_code == 403
        assert (await c.get(DOCS, params={"student": str(w["record"].id)})).status_code == 404
        assert (await c.get(REQUESTS, params={"student": str(w["record"].id)})).status_code == 404


@pytest.mark.asyncio
async def test_a_request_of_another_agency_cannot_be_fulfilled(db_session, w):
    other_record = AgentStudent(agent_id=w["other"]["master"].id, student_id=None, status="active", full_name="Theirs")
    db_session.add(other_record)
    await db_session.commit()
    async with client_for(w["other"]["master"].email) as c:
        their_request = (await c.post(REQUESTS, json={"agent_student_id": str(other_record.id), "document_type": "CV"})).json()["request"]["id"]
    async with client_for(w["master"].email) as c:
        response = await c.post(DOCS, data={"agent_student_id": str(w["record"].id), "document_type": "CV", "request_id": their_request}, files=upload_files())
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_other_agency_sees_nothing_of_a_shared_student(db_session, w):
    """A student with a login linked to two agencies: agency B must not reach agency A's agency-record documents through the shared
    account (it keeps reaching documents on the account itself, as before AGN-009)."""
    db_session.add(AgentStudent(agent_id=w["other"]["master"].id, student_id=w["linked_user"].id, status="active"))
    await db_session.commit()
    ours = await mk_doc(db_session, record=w["linked_record"])
    own_upload = await mk_doc(db_session, student=w["linked_user"], key="uploads/self.pdf")
    async with client_for(w["other"]["master"].email) as c:
        listed = {d["id"] for d in (await c.get(DOCS, params={"limit": 100})).json()["items"]}
        assert (await c.get(DOWNLOAD.format(ours.id))).status_code == 403
        assert (await c.get(f"{DOCS}/{ours.id}/history")).status_code == 404
        assert (await c.get(DOWNLOAD.format(own_upload.id))).status_code == 200
    assert str(ours.id) not in listed and str(own_upload.id) in listed


@pytest.mark.asyncio
async def test_logs_carry_no_file_name_or_reason(db_session, w, caplog, monkeypatch):
    # alembic/env.py's fileConfig() disables loggers that already exist when a migration test runs earlier in the same session.
    for name in ("app.agent_documents", "app.workflows"):
        monkeypatch.setattr(logging.getLogger(name), "disabled", False)
    caplog.set_level(logging.DEBUG)
    async with client_for(w["master"].email) as c:
        doc_id = (await c.post(DOCS, data={"agent_student_id": str(w["record"].id), "document_type": "CV"}, files=upload_files(name="SECRET-cv-name.pdf"))).json()["document"]["id"]
        await c.patch(VERIFY.format(doc_id), json={"verification_status": "rejected", "notes": "SECRET-reason"})
    text = "\n".join(f"{r.getMessage()} {getattr(r, 'extra_fields', '')}" for r in caplog.records)
    assert "agent_document_uploaded" in text
    assert "SECRET" not in text
