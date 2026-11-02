"""itc-026 (DEC-SCOPE-350) -- the IT student's resume: append-only versions (PDF, DOC or DOCX by bytes, an IT Admin-configurable limit),
uploaded by the student, their itc-003 counselor or the IT Admin, opened by HR (nehn-017 population, `hr` versions only), and every
download written to the audit log before a byte leaves."""

import io
import uuid
import zipfile

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from app.models import AuditLog, ItStudentCounselor, PlacementProfile, StudentResume, StudentResumeSetting
from app.services import student_resumes as svc
from tests.tel004_helpers import make_user
from tests.tel018_helpers import as_user, make_counselor, make_student

pytestmark = pytest.mark.asyncio

ME = "/api/v1/it/me/resumes"
SETTINGS = "/api/v1/admin/it/resume-settings"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
DOC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504  # OLE2: a legacy Word .doc
EXE = b"MZ\x90\x00" + b"\x00" * 200


def docx() -> bytes:
    """Byte-identical on every call: a fixed entry time (a ZIP header stores it, so two calls could straddle a 2-second tick)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in (("[Content_Types].xml", "<Types/>"), ("word/document.xml", "<w:document/>")):
            archive.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), body)
    return buffer.getvalue()


def staff_url(portal: str, student_id, tail: str = "") -> str:
    prefix = {"counselor": "/api/v1/counselor/it/students", "admin": "/api/v1/admin/it/students", "hr": "/api/v1/hr/students"}[portal]
    return f"{prefix}/{student_id}/resumes{tail}"


async def upload(client, url: str, data: bytes = PDF, name: str = "cv.pdf", content_type: str = "application/pdf", visibility: str | None = None):
    form = {"visibility": visibility} if visibility else None
    return await client.post(url, files={"file": (name, data, content_type)}, data=form)


async def linked(db):
    counselor = await make_counselor(db, "it")
    student = await make_student(db)
    db.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db.commit()
    return counselor, student


async def downloads(db, student_id) -> int:
    return await db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == svc.DOWNLOADED, AuditLog.entity_id == str(student_id)))


async def _reset_limit(db) -> None:
    await db.execute(delete(StudentResumeSetting))
    await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def default_limit(db_session):
    """Each test runs on the 5 MB default and leaves it behind (QA-02: the stack DB is shared with the running app)."""
    await _reset_limit(db_session)
    yield
    await _reset_limit(db_session)


# --- AC3 / R5: the student's versions --------------------------------------------------------------------------------------------


async def test_the_student_uploads_two_versions_and_both_are_kept_newest_first(client, db_session):
    student = await make_student(db_session)
    await as_user(client, student)
    empty = (await client.get(ME)).json()
    assert empty == {"items": [], "max_bytes": 5 * 1024 * 1024, "can_upload": True}

    first = await upload(client, ME, PDF, "Asha CV.pdf")
    assert first.status_code == 201, first.text
    assert first.json()["version"] == 1 and first.json()["content_type"] == svc.PDF and first.json()["visibility"] == "hr"
    second = await upload(client, ME, docx(), "asha.pdf", "application/pdf", visibility="private")  # judged a DOCX by its bytes
    assert second.status_code == 201 and second.json()["version"] == 2 and second.json()["content_type"] == svc.DOCX

    items = (await client.get(ME)).json()["items"]
    assert [i["version"] for i in items] == [2, 1]
    assert items[1]["file_name"] == "Asha CV.pdf" and items[0]["visibility"] == "private"
    assert items[0]["uploaded_by"] == {"id": str(student.id), "full_name": student.full_name} and items[0]["uploaded_by_role"] == "it_student"

    v1 = await client.get(f"{ME}/1/file")  # version 2 did not delete version 1
    assert v1.status_code == 200 and v1.content == PDF
    assert v1.headers["content-disposition"].startswith('attachment; filename="resume-') and v1.headers["content-disposition"].endswith('-v1.pdf"')
    assert v1.headers["x-content-type-options"] == "nosniff" and "sandbox" in v1.headers["content-security-policy"]
    assert (await client.get(f"{ME}/2/file")).headers["content-disposition"].endswith('-v2.docx"')
    assert (await client.get(f"{ME}/3/file")).status_code == 404

    audits = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.action == svc.UPLOADED, AuditLog.entity_id == str(student.id)))).all()
    assert sorted(a["version"] for a in audits) == [1, 2]
    assert all("cv" not in str(a).lower() and "asha" not in str(a).lower() for a in audits)  # no file names in the audit


async def test_a_legacy_doc_is_accepted_as_msword(client, db_session):
    await as_user(client, await make_student(db_session))
    response = await upload(client, ME, DOC, "old.doc", "application/msword")
    assert response.status_code == 201 and response.json()["content_type"] == svc.DOC


# --- AC1 / R3: types are judged by the bytes --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "code"),
    [(EXE, 415), (b"", 422), (b"\x89PNG\r\n\x1a\n" + b"0" * 64, 415), (b"PK\x03\x04 broken", 415), (b"plain text resume", 415)],
    ids=["exe-named-pdf", "empty", "png", "broken-zip", "text"],
)
async def test_wrong_files_are_refused_and_nothing_is_stored(client, db_session, monkeypatch, data, code):
    student = await make_student(db_session)
    await as_user(client, student)
    stored = []
    monkeypatch.setattr(svc.storage, "write_stream", lambda *a, **k: stored.append(a))
    assert (await upload(client, ME, data, "cv.pdf", "application/pdf")).status_code == code
    assert stored == [] and await db_session.scalar(select(StudentResume.id).where(StudentResume.student_user_id == student.id)) is None


async def test_a_bad_visibility_is_422(client, db_session):
    await as_user(client, await make_student(db_session))
    assert (await upload(client, ME, visibility="everyone")).status_code == 422


# --- AC2 / R4: the configurable limit ---------------------------------------------------------------------------------------------


async def test_the_admin_lowers_the_limit_new_big_files_are_refused_and_old_ones_kept(client, db_session):
    _, student = await linked(db_session)
    await as_user(client, student)
    big = b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024)
    assert (await upload(client, ME, big)).status_code == 201

    admin = await make_user(db_session, "it_admin", "it")
    await as_user(client, admin)
    assert (await client.get(SETTINGS)).json() == {"max_mb": 5, "max_bytes": 5 * 1024 * 1024, "min_mb": 1, "max_mb_ceiling": 10}
    for bad in (0, 11, "two", None):
        assert (await client.put(SETTINGS, json={"max_mb": bad})).status_code == 422
    saved = await client.put(SETTINGS, json={"max_mb": 1})
    assert saved.status_code == 200 and saved.json()["max_bytes"] == 1024 * 1024
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == svc.SETTINGS_UPDATED).order_by(AuditLog.created_at.desc()))
    assert audit.metadata_json["changes"] == {"max_mb": [5, 1]}

    await as_user(client, student)
    assert (await client.get(ME)).json()["max_bytes"] == 1024 * 1024
    refused = await upload(client, ME, big)
    assert refused.status_code == 413 and "1 MB" in refused.json()["detail"]
    assert [i["version"] for i in (await client.get(ME)).json()["items"]] == [1]  # the older, bigger version is kept
    assert (await client.get(f"{ME}/1/file")).status_code == 200


async def test_only_the_it_admin_reads_or_changes_the_limit(client, db_session):
    for role, division in (("counselor", "it"), ("it_student", "it"), ("super_admin", "it"), ("hr_team", "it")):
        await as_user(client, await make_user(db_session, role, division))
        assert (await client.get(SETTINGS)).status_code == 403
        assert (await client.put(SETTINGS, json={"max_mb": 2})).status_code == 403


# --- + / R8: staff upload on the student's behalf; scope ---------------------------------------------------------------------------


async def test_the_linked_counselor_uploads_v2_and_the_admin_v3_and_each_download_is_logged(client, db_session):
    counselor, student = await linked(db_session)
    await as_user(client, student)
    assert (await upload(client, ME)).status_code == 201

    await as_user(client, counselor)
    listed = (await client.get(staff_url("counselor", student.id))).json()
    assert [i["version"] for i in listed["items"]] == [1] and listed["can_upload"] is True
    v2 = await upload(client, staff_url("counselor", student.id), docx(), "cv.docx", svc.DOCX)
    assert v2.status_code == 201 and v2.json()["version"] == 2 and v2.json()["uploaded_by"]["id"] == str(counselor.id)
    assert v2.json()["uploaded_by_role"] == "counselor"
    assert (await client.get(staff_url("counselor", student.id, "/1/file"))).status_code == 200

    admin = await make_user(db_session, "it_admin", "it")
    await as_user(client, admin)
    assert (await upload(client, staff_url("admin", student.id))).json()["version"] == 3
    assert (await client.get(staff_url("admin", student.id, "/2/file"))).content == docx()

    await as_user(client, student)
    assert (await client.get(f"{ME}/3/file")).status_code == 200
    assert await downloads(db_session, student.id) == 3  # counselor, admin, student: one access-log row each
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == svc.DOWNLOADED, AuditLog.entity_id == str(student.id)))).all()
    assert sorted(r.metadata_json["role"] for r in rows) == ["counselor", "it_admin", "it_student"]
    assert {r.user_id for r in rows} == {counselor.id, admin.id, student.id}


async def test_out_of_scope_is_404_and_other_roles_403(client, db_session):
    counselor, student = await linked(db_session)
    await as_user(client, student)
    await upload(client, ME)

    other_counselor = await make_counselor(db_session, "it")
    await as_user(client, other_counselor)
    assert (await client.get(staff_url("counselor", student.id))).status_code == 404
    assert (await upload(client, staff_url("counselor", student.id))).status_code == 404
    assert (await client.get(staff_url("counselor", student.id, "/1/file"))).status_code == 404

    other_student = await make_student(db_session)
    await as_user(client, other_student)
    assert (await client.get(f"{ME}/1/file")).status_code == 404  # the other student's v1 is not theirs
    assert (await client.get(staff_url("admin", student.id))).status_code == 403

    for role, division in (("trainer", "it"), ("overseas_student", "overseas"), ("counselor", "overseas")):
        await as_user(client, await make_user(db_session, role, division))
        assert (await client.get(ME)).status_code == 403
        assert (await client.get(staff_url("counselor", student.id))).status_code == 403
        assert (await client.get(staff_url("admin", student.id))).status_code == 403
        assert (await client.get(staff_url("hr", student.id))).status_code == 403

    admin = await make_user(db_session, "it_admin", "it")
    await as_user(client, admin)
    assert (await client.get(staff_url("admin", uuid.uuid4()))).status_code == 404
    assert (await client.get(staff_url("admin", counselor.id))).status_code == 404  # not an IT student
    assert await downloads(db_session, student.id) == 0


# --- R8: HR reads `hr` versions in its population, never uploads -------------------------------------------------------------------


async def test_hr_sees_only_shared_versions_and_downloads_are_logged(client, db_session):
    _, student = await linked(db_session)
    await as_user(client, student)
    await upload(client, ME)  # v1 shared
    await upload(client, ME, docx(), "draft.docx", svc.DOCX, visibility="private")  # v2 private

    hr = await make_user(db_session, "hr_team", "it")
    await as_user(client, hr)
    listed = (await client.get(staff_url("hr", student.id))).json()
    assert [i["version"] for i in listed["items"]] == [1] and listed["can_upload"] is False
    assert (await client.get(staff_url("hr", student.id, "/2/file"))).status_code == 404
    download = await client.get(staff_url("hr", student.id, "/1/file"))
    assert download.status_code == 200 and download.content == PDF
    assert (await upload(client, staff_url("hr", student.id))).status_code == 405  # HR has no upload route
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == svc.DOWNLOADED, AuditLog.entity_id == str(student.id)))
    assert row.user_id == hr.id and row.metadata_json == {"version": 1, "role": "hr_team"}


async def test_hr_outside_the_pool_is_404(client, db_session):
    student = await make_student(db_session)
    db_session.add(PlacementProfile(student_id=student.id, withdrawn=True))
    await db_session.commit()
    await as_user(client, student)
    await upload(client, ME)
    await as_user(client, await make_user(db_session, "hr_team", "it"))
    assert (await client.get(staff_url("hr", student.id))).status_code == 404
    assert (await client.get(staff_url("hr", student.id, "/1/file"))).status_code == 404


# --- R5: a failed write leaves no file ---------------------------------------------------------------------------------------------


async def test_a_failed_commit_discards_the_stored_file(client, db_session, monkeypatch):
    student = await make_student(db_session)
    await as_user(client, student)
    discarded = []
    monkeypatch.setattr(svc, "discard", discarded.append)

    async def boom(*args, **kwargs):
        raise RuntimeError("lost the race")

    monkeypatch.setattr(svc, "_next_version", boom)
    with pytest.raises(RuntimeError):
        await upload(client, ME)
    assert len(discarded) == 1 and discarded[0].startswith("student-resumes/")
