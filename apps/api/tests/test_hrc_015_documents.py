"""hrc-015 (DEC-SCOPE-379) -- DOC resumes by bytes, previews (PDF inline, DOC/DOCX through a converted PDF rendition), short-lived signed
links for every resume/document download, candidate documents and document requests (staff and the candidate's own student login).
The shared test database is never truncated, so every assertion uses rows created by the test. The converter never runs here: the
enqueue is recorded and the conversion is called with a fake converter (D1)."""

import datetime
import struct
import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, CandidateDocument, CandidateDocumentRequest, CandidateResume
from app.services import candidate_previews as previews
from app.services import candidates as svc
from app.services.storage import storage
from tests.rec001_helpers import as_role, login, make_user
from tests.test_rec_009_candidates import BASE, as_recruiter, create
from tests.test_rec_009_resumes import PDF, docx, upload
from tests.test_rec_012_resume_extract import _pdf as text_pdf

ACCOUNT = "/api/v1/account/candidate-documents"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
OLE = bytes.fromhex("D0CF11E0A1B11AE1")


def doc(stream: str = "WordDocument") -> bytes:
    """An OLE2 header and a directory entry naming `stream` (UTF-16LE) -- enough for the sniff, which never parses the rest."""
    name = stream.encode("utf-16-le") + b"\x00\x00"
    entry = name.ljust(64, b"\x00") + struct.pack("<H", len(name))
    return OLE + b"\x00" * 504 + entry + b"\x00" * 256


@pytest.fixture
def queued(monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(previews, "enqueue", lambda kind, row_id: calls.append((kind, str(row_id))))
    return calls


async def _resume(db, candidate_id: str, version: int) -> CandidateResume:
    return await db.scalar(select(CandidateResume).where(CandidateResume.candidate_id == uuid.UUID(candidate_id), CandidateResume.version == version).execution_options(populate_existing=True))


async def _fetch(client, url: str):
    return await client.get(url)


# --- D2: DOC by bytes ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_doc_resume_uploads_by_its_bytes_and_queues_a_preview(client, db_session, queued):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    response = await upload(client, candidate["id"], doc(), "cv.pdf", "application/pdf")
    assert response.status_code == 201, response.text
    assert response.json()["content_type"] == svc.DOC
    resume = await _resume(db_session, candidate["id"], 1)
    assert resume.preview_status == "pending" and resume.preview_key is None
    assert queued == [("resume", str(resume.id))]
    detail = (await client.get(f"{BASE}/{candidate['id']}")).json()
    assert detail["resumes"][0]["preview_status"] == "pending"
    pdf = await upload(client, candidate["id"], PDF)
    assert pdf.status_code == 201 and len(queued) == 1  # a PDF previews itself: nothing to convert
    assert (await _resume(db_session, candidate["id"], 2)).preview_status is None


@pytest.mark.asyncio
async def test_an_ole_file_that_is_not_a_word_document_is_refused(client, db_session, queued):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    assert (await upload(client, candidate["id"], doc("Workbook"))).status_code == 415
    assert (await upload(client, candidate["id"], OLE + b"\x00" * 100)).status_code == 415
    assert queued == []


@pytest.mark.asyncio
async def test_the_jd_upload_still_takes_pdf_and_docx_only():
    import io

    from fastapi import HTTPException
    from starlette.datastructures import UploadFile

    with pytest.raises(HTTPException) as refused:
        await svc.read_pdf_or_docx(UploadFile(io.BytesIO(doc()), filename="jd.doc"), 1024 * 1024, "too big")
    assert refused.value.status_code == 415


# --- D4: signed links (AC3) -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_resume_download_link_is_short_lived_audited_and_serves_the_file(client, db_session, queued):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    await upload(client, candidate["id"], PDF)
    link = await client.get(f"{BASE}/{candidate['id']}/resume/1/link", params={"mode": "download"})
    assert link.status_code == 200, link.text
    assert link.json()["expires_in"] == 300 and link.headers["cache-control"] == "private, no-store"
    served = await _fetch(client, link.json()["url"])
    assert served.status_code == 200 and served.content == PDF
    assert served.headers["content-disposition"] == f'attachment; filename="resume-{candidate["candidate_code"]}-v1.pdf"'
    assert served.headers["x-content-type-options"] == "nosniff"
    preview = await client.get(f"{BASE}/{candidate['id']}/resume/1/link", params={"mode": "preview"})
    shown = await _fetch(client, preview.json()["url"])
    assert shown.status_code == 200 and shown.headers["content-type"] == "application/pdf"
    assert shown.headers["content-disposition"].startswith("inline")
    modes = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.action == "candidate.resume_link", AuditLog.entity_id == candidate["id"]))).all()
    assert sorted(m["mode"] for m in modes) == ["download", "preview"]
    assert (await client.get(f"{BASE}/{candidate['id']}/resume/9/link", params={"mode": "download"})).status_code == 404
    assert (await client.get(f"{BASE}/{candidate['id']}/resume/1/link", params={"mode": "print"})).status_code == 422


@pytest.mark.asyncio
async def test_an_expired_or_forged_link_is_refused(client, db_session):
    key = f"{svc.STORAGE_PREFIX}/{uuid.uuid4().hex}"
    storage.write_bytes(key, PDF, svc.PDF)
    expired = storage.presign_download(key, filename="x.pdf", content_type=svc.PDF, ttl=-5)
    assert (await client.get(expired)).status_code == 404
    live = storage.presign_download(key, filename="x.pdf", content_type=svc.PDF, ttl=60)
    assert (await client.get(live)).status_code == 200
    assert (await client.get(live[:-3] + "abc")).status_code == 404


@pytest.mark.asyncio
async def test_doc_preview_waits_for_the_rendition_then_serves_it(client, db_session, queued):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    await upload(client, candidate["id"], doc())
    url = f"{BASE}/{candidate['id']}/resume/1/link"
    pending = await client.get(url, params={"mode": "preview"})
    assert pending.status_code == 409 and "prepared" in pending.json()["detail"]
    resume = await _resume(db_session, candidate["id"], 1)
    assert await previews.convert("resume", resume.id, converter=lambda data, ext: PDF) == "ready"
    ready = await client.get(url, params={"mode": "preview"})
    assert ready.status_code == 200
    shown = await _fetch(client, ready.json()["url"])
    assert shown.content == PDF and shown.headers["content-type"] == "application/pdf"
    original = await _fetch(client, (await client.get(url, params={"mode": "download"})).json()["url"])
    assert original.content == doc() and original.headers["content-disposition"].endswith('-v1.doc"')
    assert (await _resume(db_session, candidate["id"], 1)).preview_key.startswith(f"{previews.PREFIX}/")


@pytest.mark.asyncio
async def test_a_failed_conversion_leaves_download_only(client, db_session, queued):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    await upload(client, candidate["id"], docx())
    resume = await _resume(db_session, candidate["id"], 1)

    def broken(data, ext):
        raise previews.ConversionError("password protected")

    assert await previews.convert("resume", resume.id, converter=broken) == "failed"
    assert await previews.convert("resume", resume.id, converter=lambda d, e: PDF) == "failed"  # only a pending row is converted
    refused = await client.get(f"{BASE}/{candidate['id']}/resume/1/link", params={"mode": "preview"})
    assert refused.status_code == 422 and "Download" in refused.json()["detail"]
    assert (await client.get(f"{BASE}/{candidate['id']}/resume/1/link", params={"mode": "download"})).status_code == 200


def test_the_real_converter_reports_a_missing_binary(monkeypatch):
    monkeypatch.setattr(previews.shutil, "which", lambda name: None)
    with pytest.raises(previews.ConversionError):
        previews.soffice_pdf(doc(), "doc")


@pytest.mark.asyncio
async def test_doc_extraction_reads_the_rendition(client, db_session, queued):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    await upload(client, candidate["id"], doc())
    extract = f"{BASE}/{candidate['id']}/resume/1/extract"
    assert (await client.post(extract)).status_code == 409
    resume = await _resume(db_session, candidate["id"], 1)
    await previews.convert("resume", resume.id, converter=lambda d, e: text_pdf("Python developer with Django"))
    extracted = await client.post(extract)
    assert extracted.status_code == 200, extracted.text
    assert "Django" in (await _resume(db_session, candidate["id"], 1)).extracted_text


@pytest.mark.asyncio
async def test_a_failed_doc_cannot_be_extracted(client, db_session, queued):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    await upload(client, candidate["id"], doc())
    resume = await _resume(db_session, candidate["id"], 1)

    def broken(data, ext):
        raise previews.ConversionError("broken")

    await previews.convert("resume", resume.id, converter=broken)
    assert (await client.post(f"{BASE}/{candidate['id']}/resume/1/extract")).status_code == 422


# --- D6/D7: documents and requests (AC2) ----------------------------------------------------------------------------------------------
async def _post_doc(client, url: str, data: bytes, **fields):
    form = {k: (None, str(v)) for k, v in fields.items()}
    return await client.post(url, files={**form, "file": ("file.bin", data, "application/octet-stream")})


@pytest.mark.asyncio
async def test_staff_upload_a_certificate_and_preview_an_image(client, db_session, queued):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    url = f"{BASE}/{candidate['id']}/documents"
    made = await _post_doc(client, url, PNG, document_type="certificate", title="AWS Cloud Practitioner")
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["content_type"] == "image/png" and body["document_type"] == "certificate" and body["preview_status"] is None
    assert body["uploaded_by"]["full_name"]
    listing = (await client.get(url)).json()
    assert [d["id"] for d in listing["documents"]] == [body["id"]] and listing["requests"] == []
    link = await client.get(f"{url}/{body['id']}/link", params={"mode": "preview"})
    shown = await _fetch(client, link.json()["url"])
    assert shown.content == PNG and shown.headers["content-type"] == "image/png" and shown.headers["content-disposition"].startswith("inline")
    word = await _post_doc(client, url, doc(), document_type="experience_letter")
    assert word.status_code == 201 and word.json()["preview_status"] == "pending" and queued == [("document", word.json()["id"])]
    assert (await _post_doc(client, url, b"<svg/>", document_type="certificate")).status_code == 415
    assert (await _post_doc(client, url, JPEG, document_type="other")).status_code == 422  # "other" needs a title
    assert (await _post_doc(client, url, JPEG, document_type="passport_scan")).status_code == 422
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate.document_upload", AuditLog.entity_id == candidate["id"]).limit(1))
    assert audit is not None and "file_name" not in audit.metadata_json


@pytest.mark.asyncio
async def test_a_requested_document_shows_pending_then_received(client, db_session, queued):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    other = await create(client, db_session)
    requests_url = f"{BASE}/{candidate['id']}/document-requests"
    due = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    made = await client.post(requests_url, json={"document_type": "education", "note": "Degree certificate, please", "due_date": due})
    assert made.status_code == 201, made.text
    request = made.json()
    assert request["status"] == "pending" and request["due_date"] == due
    assert (await client.post(requests_url, json={"document_type": "education"})).status_code == 409  # one pending per type
    past = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    refused = await client.post(requests_url, json={"document_type": "payslip", "due_date": past})
    assert refused.status_code == 422 and refused.json()["detail"] == "The due date must be today or later"  # QA-02
    docs_url = f"{BASE}/{candidate['id']}/documents"
    foreign = await _post_doc(client, f"{BASE}/{other['id']}/documents", PDF, document_type="education", request_id=request["id"])
    assert foreign.status_code == 404  # the request belongs to another candidate
    fulfilled = await _post_doc(client, docs_url, PDF, document_type="education", request_id=request["id"])
    assert fulfilled.status_code == 201, fulfilled.text
    listing = (await client.get(docs_url)).json()
    assert listing["requests"][0]["status"] == "received" and listing["requests"][0]["document_id"] == fulfilled.json()["id"]
    again = await _post_doc(client, docs_url, PDF, document_type="education", request_id=request["id"])
    assert again.status_code == 409
    assert (await client.post(f"{requests_url}/{request['id']}/cancel")).status_code == 409


@pytest.mark.asyncio
async def test_staff_cancel_a_pending_request(client, db_session):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    url = f"{BASE}/{candidate['id']}/document-requests"
    request = (await client.post(url, json={"document_type": "id_proof"})).json()
    cancelled = await client.post(f"{url}/{request['id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert (await client.post(url, json={"document_type": "id_proof"})).status_code == 201  # a cancelled one no longer blocks
    row = await db_session.scalar(select(CandidateDocumentRequest).where(CandidateDocumentRequest.id == uuid.UUID(request["id"])))
    assert row.cancelled_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("hr_team", "it"), ("employer", "it"), ("it_student", "it")])
async def test_readers_read_and_only_writers_change(client, db_session, role, division, queued):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    await upload(client, candidate["id"], PDF)
    await as_role(client, db_session, role, division)
    docs = f"{BASE}/{candidate['id']}/documents"
    expected_read = 200 if role == "hr_team" else 403
    assert (await client.get(docs)).status_code == expected_read
    assert (await client.get(f"{BASE}/{candidate['id']}/resume/1/link", params={"mode": "download"})).status_code == expected_read
    assert (await _post_doc(client, docs, PDF, document_type="certificate")).status_code == 403
    assert (await client.post(f"{BASE}/{candidate['id']}/document-requests", json={"document_type": "payslip"})).status_code == 403


@pytest.mark.asyncio
async def test_recruitment_document_keys_are_withheld_from_the_generic_routes(client, db_session):
    await as_recruiter(client, db_session)
    for prefix in ("candidate-documents", "candidate-previews"):
        assert (await client.get("/api/v1/files/download", params={"key": f"{prefix}/{uuid.uuid4().hex}"})).status_code == 404


# --- D8: the candidate's own student login --------------------------------------------------------------------------------------------
async def _pooled_student(client, db):
    student = await make_user(db, "it_student", "it", name=f"Docs Student {uuid.uuid4().hex[:6]}")
    await login(client, student)
    assert (await client.post("/api/v1/account/placement-pool/opt-in", json={"consent_version": "v1"})).status_code == 200
    from app.models import Candidate

    candidate = await db.scalar(select(Candidate).where(Candidate.user_id == student.id))
    return student, candidate


@pytest.mark.asyncio
async def test_the_student_sees_and_fulfils_their_own_requests(client, db_session, queued):
    student, candidate = await _pooled_student(client, db_session)
    recruiter = await as_recruiter(client, db_session)
    request = (await client.post(f"{BASE}/{candidate.id}/document-requests", json={"document_type": "certificate", "note": "Your Python certificate"})).json()
    await login(client, student)
    mine = await client.get(ACCOUNT)
    assert mine.status_code == 200
    body = mine.json()
    assert body["available"] is True and [r["id"] for r in body["requests"]] == [request["id"]]
    assert body["requests"][0]["status"] == "pending" and body["requests"][0]["note"] == "Your Python certificate"
    assert recruiter.full_name not in mine.text
    sent = await _post_doc(client, ACCOUNT, PDF, document_type="certificate", request_id=request["id"])
    assert sent.status_code == 201, sent.text
    assert sent.json()["uploaded_by"] == "you"
    after = (await client.get(ACCOUNT)).json()
    assert after["requests"][0]["status"] == "received" and len(after["documents"]) == 1
    link = await client.get(f"{ACCOUNT}/{sent.json()['id']}/link", params={"mode": "download"})
    assert (await _fetch(client, link.json()["url"])).content == PDF
    await as_recruiter(client, db_session)
    staff_view = (await client.get(f"{BASE}/{candidate.id}/documents")).json()
    assert staff_view["requests"][0]["status"] == "received" and staff_view["documents"][0]["uploaded_by"]["id"] == str(student.id)


@pytest.mark.asyncio
async def test_a_student_reaches_only_their_own_documents(client, db_session, queued):
    owner, owner_candidate = await _pooled_student(client, db_session)
    await as_recruiter(client, db_session)
    theirs = (await _post_doc(client, f"{BASE}/{owner_candidate.id}/documents", PDF, document_type="payslip")).json()
    other_request = (await client.post(f"{BASE}/{owner_candidate.id}/document-requests", json={"document_type": "education"})).json()
    intruder, _ = await _pooled_student(client, db_session)
    assert (await client.get(f"{ACCOUNT}/{theirs['id']}/link", params={"mode": "download"})).status_code == 404
    assert (await _post_doc(client, ACCOUNT, PDF, document_type="education", request_id=other_request["id"])).status_code == 404
    assert (await client.get(ACCOUNT)).json()["documents"] == []


@pytest.mark.asyncio
async def test_a_student_outside_the_pool_cannot_upload(client, db_session):
    student = await make_user(db_session, "it_student", "it")
    await login(client, student)
    state = await client.get(ACCOUNT)
    assert state.status_code == 200 and state.json() == {"available": False, "requests": [], "documents": []}
    assert (await _post_doc(client, ACCOUNT, PDF, document_type="certificate")).status_code == 409
    await as_role(client, db_session, "employer", "it")
    assert (await client.get(ACCOUNT)).status_code == 403


@pytest.mark.asyncio
async def test_documents_are_stored_under_their_own_prefix(client, db_session, queued):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    made = (await _post_doc(client, f"{BASE}/{candidate['id']}/documents", PDF, document_type="certificate")).json()
    row = await db_session.scalar(select(CandidateDocument).where(CandidateDocument.id == uuid.UUID(made["id"])))
    assert row.storage_key.startswith("candidate-documents/") and "storage_key" not in made

@pytest.mark.asyncio
async def test_link_reads_stay_out_of_the_change_history(client, db_session, queued):
    """hrc-004's history and hrc-003's stale guard skip reads: a link is a read like a download; document writes are changes."""
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    await upload(client, candidate["id"], PDF)
    await client.get(f"{BASE}/{candidate['id']}/resume/1/link", params={"mode": "download"})
    made = (await _post_doc(client, f"{BASE}/{candidate['id']}/documents", PDF, document_type="certificate")).json()
    await client.get(f"{BASE}/{candidate['id']}/documents/{made['id']}/link", params={"mode": "preview"})
    actions = [i["action"] for i in (await client.get(f"{BASE}/{candidate['id']}/history")).json()["items"]]
    assert "candidate.document_upload" in actions and "candidate.resume_upload" in actions
    assert not [a for a in actions if a.endswith("_link")]
