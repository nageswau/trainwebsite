"""rec-009 -- versioned resumes (spec §5; AC4, Q-09 default: PDF or DOCX by bytes, at most 5 MB)."""

import io
import uuid
import zipfile

import pytest
from sqlalchemy import select

from app.models import AuditLog, CandidateResume
from app.services import candidates as svc
from tests.rec001_helpers import as_role
from tests.test_rec_009_candidates import BASE, as_recruiter, create

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    return buffer.getvalue()


def plain_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes.txt", "hello")
    return buffer.getvalue()


async def upload(client, candidate_id, data: bytes, name="resume.pdf", content_type="application/pdf"):
    return await client.put(f"{BASE}/{candidate_id}/resume", files={"file": (name, data, content_type)})


@pytest.mark.asyncio
async def test_versions_the_current_one_and_downloads_with_an_audit_row(client, db_session):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    first = await upload(client, candidate["id"], PDF, "Rahul CV.pdf")
    assert first.status_code == 201 and first.json()["version"] == 1 and first.json()["content_type"] == svc.PDF
    second = await upload(client, candidate["id"], docx(), "rahul.pdf", "application/pdf")  # named .pdf, judged a DOCX by its bytes
    assert second.status_code == 201 and second.json()["version"] == 2 and second.json()["content_type"] == svc.DOCX
    detail = (await client.get(f"{BASE}/{candidate['id']}")).json()
    assert [r["version"] for r in detail["resumes"]] == [2, 1] and detail["resumes"][1]["file_name"] == "Rahul CV.pdf"
    download = await client.get(f"{BASE}/{candidate['id']}/resume/1")
    assert download.status_code == 200 and download.content == PDF
    assert download.headers["content-disposition"] == f'attachment; filename="resume-{candidate["candidate_code"]}-v1.pdf"'
    assert download.headers["x-content-type-options"] == "nosniff"
    latest = await client.get(f"{BASE}/{candidate['id']}/resume/2")
    assert latest.headers["content-disposition"].endswith('-v2.docx"')
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate.resume_download", AuditLog.entity_id == candidate["id"]))
    assert audit.metadata_json["version"] in (1, 2)
    uploads = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.action == "candidate.resume_upload", AuditLog.entity_id == candidate["id"]))).all()
    assert sorted(m["version"] for m in uploads) == [1, 2]
    assert (await client.get(f"{BASE}/{candidate['id']}/resume/3")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"", 422),
        (b"\x89PNG\r\n\x1a\n" + b"0" * 64, 415),
        (plain_zip(), 415),
        (b"PK\x03\x04 not really a zip", 415),
        (b"%PDF-" + b"0" * (5 * 1024 * 1024), 413),
    ],
    ids=["empty", "png", "zip-not-docx", "broken-zip", "over-5mb"],
)
async def test_wrong_files_are_refused_and_nothing_is_stored(client, db_session, data, code):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    assert (await upload(client, candidate["id"], data)).status_code == code
    count = await db_session.scalar(select(CandidateResume.id).where(CandidateResume.candidate_id == uuid.UUID(candidate["id"])))
    assert count is None


@pytest.mark.asyncio
async def test_an_archived_candidate_takes_no_resume_and_the_stored_file_is_discarded(client, db_session, monkeypatch):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    await client.post(f"{BASE}/{candidate['id']}/archive")
    discarded = []
    monkeypatch.setattr(svc, "discard", discarded.append)
    response = await upload(client, candidate["id"], PDF)
    assert response.status_code == 409 and response.json()["detail"] == "Restore this candidate first"
    assert len(discarded) == 1 and discarded[0].startswith("candidate-resumes/")


@pytest.mark.asyncio
async def test_hr_team_downloads_but_cannot_upload_and_outsiders_get_nothing(client, db_session):
    await as_recruiter(client, db_session)
    candidate = await create(client, db_session)
    await upload(client, candidate["id"], PDF)
    await as_role(client, db_session, "hr_team", "it")
    assert (await client.get(f"{BASE}/{candidate['id']}/resume/1")).status_code == 200
    assert (await upload(client, candidate["id"], PDF)).status_code == 403
    await as_role(client, db_session, "employer", "it")
    assert (await client.get(f"{BASE}/{candidate['id']}/resume/1")).status_code == 403


@pytest.mark.asyncio
async def test_an_unknown_candidate_is_404_for_upload_and_download(client, db_session):
    await as_recruiter(client, db_session)
    missing = uuid.uuid4()
    assert (await upload(client, missing, PDF)).status_code == 404
    assert (await client.get(f"{BASE}/{missing}/resume/1")).status_code == 404
