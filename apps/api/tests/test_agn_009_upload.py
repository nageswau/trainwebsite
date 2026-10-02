"""AGN-009 -- upload and replace (spec §4.2, §4.4; AC1). Files are stored by the server under a server-generated key; the client
never names a path."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.models import AgentStudent, StudentDocument
from app.services.storage import storage
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import mk_application
from tests.agn009_helpers import DOCS, PDF, PNG, audit_actions, events_of, mk_doc, upload_files, world


@pytest_asyncio.fixture
async def w(db_session):
    return await world(db_session)


def form(record, **extra) -> dict:
    return {"agent_student_id": str(record.id), "document_type": "Passport", **extra}


@pytest.mark.asyncio
async def test_master_uploads_for_a_student_with_no_login(db_session, w):
    async with client_for(w["master"].email) as c:
        response = await c.post(DOCS, data=form(w["record"]), files=upload_files())
    assert response.status_code == 201, response.text
    body = response.json()["document"]
    assert body["verification_status"] == "pending"  # AC1
    assert body["student"] == w["record"].full_name and body["has_login"] is False
    assert body["original_filename"] == "passport.pdf" and body["content_type"] == "application/pdf"
    assert "file_url" not in body and "file_key" not in body
    row = await db_session.get(StudentDocument, body["id"])
    assert row.agent_student_id == w["record"].id and row.student_id is None
    assert row.file_url.startswith("agent-documents/") and storage.read_bytes(row.file_url) == PDF
    assert row.uploaded_by_user_id == w["master"].id
    assert [(e.event, e.to_status) for e in await events_of(db_session, row.id)] == [("uploaded", "pending")]
    assert await audit_actions(db_session, row.id) == ["document.upload"]


@pytest.mark.asyncio
async def test_upload_for_a_linked_student_also_sets_the_account(db_session, w):
    async with client_for(w["master"].email) as c:
        response = await c.post(DOCS, data=form(w["linked_record"]), files=upload_files())
    assert response.status_code == 201, response.text
    row = await db_session.get(StudentDocument, response.json()["document"]["id"])
    assert row.student_id == w["linked_user"].id and row.agent_student_id == w["linked_record"].id


@pytest.mark.asyncio
@pytest.mark.parametrize(("who", "code"), [("staff", 201), ("plain", 404), ("other", 404)])
async def test_upload_scope(db_session, w, who, code):
    email = {"staff": w["staff"]["user"].email, "plain": w["plain"]["user"].email, "other": w["other"]["master"].email}[who]
    async with client_for(email) as c:
        response = await c.post(DOCS, data=form(w["record"]), files=upload_files())
    assert response.status_code == code, response.text


@pytest.mark.asyncio
async def test_archived_student_is_read_only(db_session, w):
    record = await db_session.get(AgentStudent, w["record"].id)
    record.status = "archived"
    await db_session.commit()
    async with client_for(w["master"].email) as c:
        response = await c.post(DOCS, data=form(w["record"]), files=upload_files())
    assert response.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [{"document_type": "Visa"}, {"document_type": "Other"}, {"document_type": "Other", "document_label": " "}, {"document_label": "Mine"}],
)
async def test_type_and_label_rules(db_session, w, extra):
    async with client_for(w["master"].email) as c:
        response = await c.post(DOCS, data=form(w["record"], **extra), files=upload_files())
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_other_with_a_label(db_session, w):
    async with client_for(w["master"].email) as c:
        response = await c.post(DOCS, data=form(w["record"], document_type="Other", document_label="  Medical report "), files=upload_files())
    assert response.status_code == 201, response.text
    assert response.json()["document"]["document_label"] == "Medical report"


@pytest.mark.asyncio
@pytest.mark.parametrize(("data", "name", "code"), [(b"", "empty.pdf", 422), (b"hello", "notes.txt", 415), (b"MZ\x90\x00", "passport.pdf", 415)])
async def test_file_content_rules(db_session, w, data, name, code):
    async with client_for(w["master"].email) as c:
        response = await c.post(DOCS, data=form(w["record"]), files=upload_files(data, name))
    assert response.status_code == code, response.text


@pytest.mark.asyncio
async def test_oversize_file_is_413(db_session, w, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 16)
    async with client_for(w["master"].email) as c:
        response = await c.post(DOCS, data=form(w["record"]), files=upload_files())
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_png_is_accepted_and_typed_from_its_bytes(db_session, w):
    async with client_for(w["master"].email) as c:
        response = await c.post(DOCS, data=form(w["record"]), files=upload_files(PNG, "scan.pdf", "application/pdf"))
    assert response.status_code == 201, response.text
    assert response.json()["document"]["content_type"] == "image/png"
    assert b"tEXt" in PNG
    row = await db_session.get(StudentDocument, response.json()["document"]["id"])
    assert b"tEXt" not in storage.read_bytes(row.file_url)  # metadata stripped before storing (G8)


@pytest.mark.asyncio
async def test_application_must_belong_to_the_student(db_session, w):
    own = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    other_students = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["unassigned"])
    foreign = await mk_application(db_session, agent=w["other"]["master"], university=w["university"], student=await mk_user(db_session, role="overseas_student"))
    async with client_for(w["master"].email) as c:
        ok = await c.post(DOCS, data=form(w["record"], application_id=str(own.id)), files=upload_files())
        mismatch = await c.post(DOCS, data=form(w["record"], application_id=str(other_students.id)), files=upload_files())
        outside = await c.post(DOCS, data=form(w["record"], application_id=str(foreign.id)), files=upload_files())
    assert ok.status_code == 201 and ok.json()["document"]["application_id"] == str(own.id)
    assert mismatch.status_code == 422
    assert outside.status_code == 404


@pytest.mark.asyncio
async def test_upload_throttle(db_session, w, monkeypatch):
    from app.services import agent_documents

    monkeypatch.setattr(agent_documents, "UPLOAD_LIMIT", 1)
    async with client_for(w["master"].email) as c:
        first = await c.post(DOCS, data=form(w["record"]), files=upload_files())
        second = await c.post(DOCS, data=form(w["record"]), files=upload_files())
    assert first.status_code == 201
    assert second.status_code == 429 and int(second.headers["Retry-After"]) > 0


@pytest.mark.asyncio
async def test_failed_commit_removes_the_stored_file(db_session, w, monkeypatch):
    from app.api import agent_documents as router_module

    stored: list[str] = []
    real_write = storage.write_bytes
    monkeypatch.setattr(storage, "write_bytes", lambda key, data, ct: (stored.append(key), real_write(key, data, ct)))

    def boom(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(router_module, "_audit", boom)
    before = await db_session.scalar(select(StudentDocument.id).where(StudentDocument.agent_student_id == w["record"].id))
    async with client_for(w["master"].email) as c:
        with pytest.raises(RuntimeError):
            await c.post(DOCS, data=form(w["record"]), files=upload_files())
    assert before is None
    assert await db_session.scalar(select(StudentDocument.id).where(StudentDocument.agent_student_id == w["record"].id)) is None
    assert len(stored) == 1
    with pytest.raises(FileNotFoundError):
        storage.read_bytes(stored[0])


# --- replace (G6) ---------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "rejected", "changes_required", "verified"])
async def test_replace_resets_to_pending_and_keeps_the_old_file(db_session, w, status):
    old_key = f"agent-documents/old-{status}"
    storage.write_bytes(old_key, PDF, "application/pdf")
    doc = await mk_doc(db_session, record=w["record"], status=status, verified_by=w["master"] if status != "pending" else None, key=old_key)
    async with client_for(w["staff"]["user"].email) as c:
        response = await c.put(f"{DOCS}/{doc.id}/file", files=upload_files(PNG, "new.png", "image/png"))
    assert response.status_code == 200, response.text
    body = response.json()["document"]
    assert body["verification_status"] == "pending" and body["reviewer_notes"] is None
    row = await db_session.get(StudentDocument, doc.id, populate_existing=True)
    assert row.file_url != old_key and row.file_url.startswith("agent-documents/") and row.verified_by_id is None
    assert storage.read_bytes(old_key) == PDF  # the old file is kept for history
    events = await events_of(db_session, doc.id)
    assert [(e.event, e.from_status, e.to_status, e.file_key) for e in events] == [("replaced", status, "pending", old_key)]
    assert "document.replace" in await audit_actions(db_session, doc.id)


@pytest.mark.asyncio
async def test_replace_refused_after_a_counselor_decision(db_session, w):
    counselor = await mk_user(db_session, role="counselor")
    doc = await mk_doc(db_session, record=w["record"], status="verified", verified_by=counselor)
    async with client_for(w["master"].email) as c:
        response = await c.put(f"{DOCS}/{doc.id}/file", files=upload_files())
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_replace_refused_for_a_document_the_student_uploaded(db_session, w):
    doc = await mk_doc(db_session, student=w["linked_user"])
    async with client_for(w["master"].email) as c:
        response = await c.put(f"{DOCS}/{doc.id}/file", files=upload_files())
    assert response.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(("who", "code"), [("plain", 404), ("other", 404)])
async def test_replace_out_of_scope(db_session, w, who, code):
    doc = await mk_doc(db_session, record=w["record"])
    email = {"plain": w["plain"]["user"].email, "other": w["other"]["master"].email}[who]
    async with client_for(email) as c:
        response = await c.put(f"{DOCS}/{doc.id}/file", files=upload_files())
    assert response.status_code == code


@pytest.mark.asyncio
async def test_replace_refused_for_an_archived_student(db_session, w):
    doc = await mk_doc(db_session, record=w["record"])
    record = await db_session.get(AgentStudent, w["record"].id)
    record.status = "archived"
    await db_session.commit()
    async with client_for(w["master"].email) as c:
        response = await c.put(f"{DOCS}/{doc.id}/file", files=upload_files())
    assert response.status_code == 409
