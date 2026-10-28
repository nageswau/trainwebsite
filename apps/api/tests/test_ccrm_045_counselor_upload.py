"""ccrm-045 (DEC-SCOPE-318) -- the counselor (and the Overseas Admin) upload a document on the student 360's Documents tab, with or
without an application; the student sees it at once. POST /counselor/students/{id}/documents (multipart). An unattached document
follows the counselor's caseload for download; an offer letter uploaded against an application is listed on the student's Offer Letters.
Spec: docs/superpowers/specs/2026-10-28-ccrm-045-counselor-document-upload-design.md."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.models import AuditLog, OverseasStudentArchive, OverseasStudentCounselor, StudentDocument
from app.services.storage import storage
from tests.agn001_helpers import login, mk_user, uniq
from tests.agn009_helpers import PDF, PNG, events_of, upload_files
from tests.enh031_helpers import mk_application, mk_university


def url(student_id) -> str:
    return f"/api/v1/counselor/students/{student_id}/documents"


DOWNLOAD = "/api/v1/workflows/overseas/documents/{}/download"
PORTAL = "/api/v1/portal/overseas/student/{}"


@pytest_asyncio.fixture
async def w(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name="Nora Counselor")
    other = await mk_user(db_session, role="counselor", full_name="Omar Counselor")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Ada Admin")
    walk_in = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('c45')} Walk In")
    db_session.add(OverseasStudentCounselor(student_user_id=walk_in.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    uni = await mk_university(db_session, name=uniq("Alpha Uni"))
    own = await mk_application(db_session, student=walk_in, university=uni, counselor=counselor, status="offer")
    foreign = await mk_application(db_session, student=walk_in, university=await mk_university(db_session, name=uniq("Beta Uni")), counselor=other)
    stranger = await mk_user(db_session, role="overseas_student")
    await db_session.commit()
    return {"counselor": counselor, "other": other, "admin": admin, "student": walk_in, "own": own, "foreign": foreign, "uni": uni, "stranger": stranger}


async def _linked_only(db_session, counselor):
    """A walk-in in the caseload through csc-001 only -- no application at all (AC1)."""
    student = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('c45')} Fresh")
    db_session.add(OverseasStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db_session.commit()
    return student


@pytest.mark.asyncio
async def test_ac1_walk_in_without_application_upload_is_visible_to_the_student(client, db_session, w):
    student = await _linked_only(db_session, w["counselor"])
    await login(client, w["counselor"].email)
    response = await client.post(url(student.id), data={"document_type": "Passport"}, files=upload_files(PDF, "passport.pdf"))
    assert response.status_code == 201, response.text
    body = response.json()["document"]
    assert body["document_type"] == "Passport" and body["application_id"] is None and body["status"] == "pending"
    doc = await db_session.get(StudentDocument, body["id"])
    assert doc.student_id == student.id and doc.uploaded_by_user_id == w["counselor"].id and doc.application_id is None
    assert doc.file_url.startswith("agent-documents/") and doc.content_type == "application/pdf" and doc.original_filename == "passport.pdf"
    assert [e.event for e in await events_of(db_session, doc.id)] == ["uploaded"]

    # the 360 lists it, downloadable by the counselor (AC5)
    items = (await client.get(url(student.id))).json()["items"]
    assert [i["id"] for i in items] == [str(doc.id)] and items[0]["can_download"] is True
    assert (await client.get(DOWNLOAD.format(doc.id))).status_code == 200

    await login(client, student.email)
    rows = (await client.get(PORTAL.format("documents"))).json()["rows"]
    assert [r["id"] for r in rows] == [str(doc.id)]
    assert (await client.get(DOWNLOAD.format(doc.id))).status_code == 200


@pytest.mark.asyncio
async def test_ac2_offer_letter_against_an_application_reaches_the_students_offer_letters(client, db_session, w):
    own2 = await mk_application(db_session, student=w["student"], university=await mk_university(db_session, name=uniq("Gamma Uni")), counselor=w["counselor"], status="submitted")
    await login(client, w["counselor"].email)
    response = await client.post(url(w["student"].id), data={"document_type": "Offer letter", "application_id": str(own2.id)}, files=upload_files(PDF, "offer.pdf"))
    assert response.status_code == 201, response.text
    doc_id = response.json()["document"]["id"]
    assert response.json()["document"]["application_id"] == str(own2.id)
    assert (await client.get(DOWNLOAD.format(doc_id))).status_code == 200  # AC5 on an application-bound upload

    await login(client, w["student"].email)
    rows = (await client.get(PORTAL.format("offer-letters"))).json()["rows"]
    letter = [r for r in rows if r["university"] == (await db_session.get(type(w["uni"]), own2.university_id)).name]
    assert len(letter) == 1 and letter[0]["offer"] == "offer.pdf"


@pytest.mark.asyncio
async def test_offer_letter_needs_an_application_and_other_needs_a_name(client, w):
    await login(client, w["counselor"].email)
    assert (await client.post(url(w["student"].id), data={"document_type": "Offer letter"}, files=upload_files())).status_code == 422
    assert (await client.post(url(w["student"].id), data={"document_type": "Other"}, files=upload_files())).status_code == 422
    assert (await client.post(url(w["student"].id), data={"document_type": "Passport", "document_label": "Mine"}, files=upload_files())).status_code == 422
    ok = await client.post(url(w["student"].id), data={"document_type": "Other", "document_label": "Bank letter"}, files=upload_files())
    assert ok.status_code == 201 and ok.json()["document"]["name"] == "Bank letter"
    assert (await client.post(url(w["student"].id), data={"document_type": "Driving licence"}, files=upload_files())).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(("data", "name", "code"), [(b"hello", "notes.txt", 415), (b"MZ\x90\x00", "passport.pdf", 415), (b"", "empty.pdf", 422)])
async def test_ac3_file_type_is_sniffed(client, w, data, name, code):
    await login(client, w["counselor"].email)
    assert (await client.post(url(w["student"].id), data={"document_type": "Passport"}, files=upload_files(data, name))).status_code == code


@pytest.mark.asyncio
async def test_ac3_oversize_is_413_and_images_are_accepted(client, w, monkeypatch):
    await login(client, w["counselor"].email)
    png = await client.post(url(w["student"].id), data={"document_type": "Passport"}, files=upload_files(PNG, "scan.png", "image/png"))
    assert png.status_code == 201
    monkeypatch.setattr(settings, "max_upload_bytes", 16)
    assert (await client.post(url(w["student"].id), data={"document_type": "Passport"}, files=upload_files())).status_code == 413


@pytest.mark.asyncio
async def test_ac4_scope_and_roles(client, db_session, w):
    await login(client, w["counselor"].email)
    assert (await client.post(url(w["stranger"].id), data={"document_type": "Passport"}, files=upload_files())).status_code == 404
    await login(client, w["other"].email)  # has an application with the student, so it is in their caseload too
    assert (await client.post(url(w["student"].id), data={"document_type": "Passport"}, files=upload_files())).status_code == 201
    for role, division in (("agent", "overseas"), ("counselor", "it"), ("super_admin", "global")):
        user = await mk_user(db_session, role=role, division=division)
        await login(client, user.email, division)
        assert (await client.post(url(w["student"].id), data={"document_type": "Passport"}, files=upload_files())).status_code == 403, role
    await login(client, w["student"].email)
    assert (await client.post(url(w["student"].id), data={"document_type": "Passport"}, files=upload_files())).status_code == 403


@pytest.mark.asyncio
async def test_application_rules(client, db_session, w):
    await login(client, w["counselor"].email)
    other_students = await mk_application(db_session, student=w["stranger"], university=w["uni"], counselor=w["counselor"])
    assert (await client.post(url(w["student"].id), data={"document_type": "Passport", "application_id": str(other_students.id)}, files=upload_files())).status_code == 422
    assert (await client.post(url(w["student"].id), data={"document_type": "Passport", "application_id": str(w["foreign"].id)}, files=upload_files())).status_code == 403
    w["own"].status = "withdrawn"
    await db_session.commit()
    assert (await client.post(url(w["student"].id), data={"document_type": "Passport", "application_id": str(w["own"].id)}, files=upload_files())).status_code == 409

    await login(client, w["admin"].email)  # U1: the Admin, on any of the student's applications
    response = await client.post(url(w["student"].id), data={"document_type": "Transcripts", "application_id": str(w["foreign"].id)}, files=upload_files())
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_archived_student_is_409(client, db_session, w):
    db_session.add(OverseasStudentArchive(student_user_id=w["student"].id, archived_by_user_id=w["admin"].id, reason="Left"))
    await db_session.commit()
    await login(client, w["counselor"].email)
    assert (await client.post(url(w["student"].id), data={"document_type": "Passport"}, files=upload_files())).status_code == 409


@pytest.mark.asyncio
async def test_ac6_history_and_audit_record_the_uploader(client, db_session, w):
    await login(client, w["counselor"].email)
    doc_id = (await client.post(url(w["student"].id), data={"document_type": "CV"}, files=upload_files())).json()["document"]["id"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == doc_id, AuditLog.action == "document.upload"))
    assert audit.user_id == w["counselor"].id and audit.metadata_json["document_type"] == "CV"
    history = (await client.get(f"/api/v1/counselor/students/{w['student'].id}/history")).json()["items"]
    assert {"summary": "Uploaded: CV", "actor": "Nora Counselor"}.items() <= next(h for h in history if h["kind"] == "document").items()


@pytest.mark.asyncio
async def test_failed_commit_discards_the_stored_file(client, db_session, w, monkeypatch):
    from app.api import counselor_students as router_module

    stored: list[str] = []
    real_write = storage.write_bytes
    monkeypatch.setattr(storage, "write_bytes", lambda key, data, ct: (stored.append(key), real_write(key, data, ct)))

    def boom(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(router_module, "_audit", boom)
    await login(client, w["counselor"].email)
    with pytest.raises(RuntimeError):
        await client.post(url(w["student"].id), data={"document_type": "Passport"}, files=upload_files())
    assert await db_session.scalar(select(StudentDocument.id).where(StudentDocument.student_id == w["student"].id)) is None
    assert len(stored) == 1
    with pytest.raises(FileNotFoundError):
        storage.read_bytes(stored[0])


@pytest.mark.asyncio
async def test_unattached_document_download_follows_the_caseload(client, db_session, w):
    """The download route: a counselor linked by csc-001 only (no application) now downloads the student's unattached documents; a
    counselor outside the caseload still cannot."""
    student = await _linked_only(db_session, w["counselor"])
    doc = StudentDocument(student_id=student.id, document_type="Passport", file_url="/local-files/x.pdf", verification_status="pending")
    db_session.add(doc)
    await db_session.commit()
    await login(client, w["counselor"].email)
    assert (await client.get(DOWNLOAD.format(doc.id))).status_code == 200
    await login(client, w["other"].email)
    assert (await client.get(DOWNLOAD.format(doc.id))).status_code == 403
