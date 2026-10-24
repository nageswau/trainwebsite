"""ccrm-021 (DEC-SCOPE-249) -- the fixed document status list, review metadata, passport expiry, versions on replace and the expiry job.
Spec: docs/superpowers/specs/2026-10-24-ccrm-021-document-status-design.md (S1-S7)."""

import io
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, DocumentEvent, StudentDocument
from app.services.document_expiry import expire_documents
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import mk_staff
from tests.agn003_helpers import agency_document
from tests.test_ovs_005_documents import _make_application, _make_university

VERIFY = "/api/v1/workflows/overseas/documents/{}/verify"
VERSIONS = "/api/v1/workflows/overseas/documents/{}/versions"
UPLOAD = "/api/v1/workflows/overseas/documents"
QUEUE = "/api/v1/portal/overseas/counselor/documents"
STUDENT_DOCS = "/api/v1/portal/overseas/student/documents"
PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


async def _world(db, *, document_type="Transcripts", status="pending", expiry=None) -> dict:
    student = await mk_user(db, role="overseas_student", full_name=f"Doc Student {uniq()}")
    counselor = await mk_user(db, role="counselor", full_name="Doc Counselor")
    application = await _make_application(db, student, await _make_university(db), counselor)
    document = StudentDocument(
        student_id=student.id,
        application_id=application.id,
        document_type=document_type,
        file_url=f"uploads/{uniq('doc')}.pdf",
        verification_status=status,
        expiry_date=expiry,
    )
    db.add(document)
    await db.commit()
    return {"student": student, "counselor": counselor, "application": application, "document": document}


async def _doc(db, document_id) -> StudentDocument:
    return await db.get(StudentDocument, document_id, populate_existing=True)


async def _events(db, document_id) -> list[str]:
    return list((await db.scalars(select(DocumentEvent.event).where(DocumentEvent.document_id == document_id).order_by(DocumentEvent.seq))).all())


def _file(data: bytes = PDF) -> dict:
    return {"file": ("new.pdf", io.BytesIO(data), "application/pdf")}


# --- S1: counselor / admin review -------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["under_review", "verified", "incomplete", "reupload_required", "not_required"])
async def test_a_counselor_sets_each_review_status_with_reviewer_and_date(db_session, status):
    w = await _world(db_session)
    async with client_for(w["counselor"].email) as c:
        response = await c.patch(VERIFY.format(w["document"].id), json={"verification_status": status, "notes": "Looked at it"})
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == status
    doc = await _doc(db_session, w["document"].id)
    assert (doc.verification_status, doc.verified_by_id, doc.reviewer_notes) == (status, w["counselor"].id, "Looked at it")
    assert doc.reviewed_at is not None and datetime.now(UTC) - doc.reviewed_at < timedelta(minutes=5)
    assert await _events(db_session, doc.id) == [status]


@pytest.mark.asyncio
@pytest.mark.parametrize(("legacy", "stored"), [("rejected", "reupload_required"), ("changes_required", "incomplete")])
async def test_the_pre_0174_outcomes_are_accepted_and_stored_as_their_new_codes(db_session, legacy, stored):
    w = await _world(db_session)
    async with client_for(w["counselor"].email) as c:
        response = await c.patch(VERIFY.format(w["document"].id), json={"verification_status": legacy})
    assert response.status_code == 200 and response.json()["verification_status"] == stored
    assert (await _doc(db_session, w["document"].id)).verification_status == stored


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["nonsense", "expired", "requested", "uploaded", "pending", ""])
async def test_a_status_outside_the_review_list_is_refused_and_nothing_changes(db_session, status):
    w = await _world(db_session)
    async with client_for(w["counselor"].email) as c:
        response = await c.patch(VERIFY.format(w["document"].id), json={"verification_status": status})
    assert response.status_code == 422
    assert (await _doc(db_session, w["document"].id)).verification_status == "pending"


@pytest.mark.asyncio
async def test_a_missing_status_still_means_verified(db_session):  # the OVS-005 default body is unchanged
    w = await _world(db_session)
    async with client_for(w["counselor"].email) as c:
        response = await c.patch(VERIFY.format(w["document"].id), json={})
    assert response.status_code == 200 and response.json()["verification_status"] == "verified"


@pytest.mark.asyncio
async def test_drafting_statuses_only_on_cv_and_sop_documents(db_session):
    sop = await _world(db_session, document_type="SOP")
    transcript = await _world(db_session)
    async with client_for(sop["counselor"].email) as c:
        assert (await c.patch(VERIFY.format(sop["document"].id), json={"verification_status": "draft"})).status_code == 200
    async with client_for(transcript["counselor"].email) as c:
        refused = await c.patch(VERIFY.format(transcript["document"].id), json={"verification_status": "approved"})
    assert refused.status_code == 422 and "CV" in refused.json()["detail"]


# --- S2: passport expiry ----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_passport_cannot_be_verified_without_an_expiry_date(db_session):
    w = await _world(db_session, document_type="Passport")
    async with client_for(w["counselor"].email) as c:
        refused = await c.patch(VERIFY.format(w["document"].id), json={"verification_status": "verified"})
        assert refused.status_code == 422 and "expiry" in refused.json()["detail"].lower()
        past = await c.patch(VERIFY.format(w["document"].id), json={"verification_status": "verified", "expiry_date": "2020-01-01"})
        assert past.status_code == 422
        future = (date.today() + timedelta(days=900)).isoformat()
        ok = await c.patch(VERIFY.format(w["document"].id), json={"verification_status": "verified", "expiry_date": future})
    assert ok.status_code == 200, ok.text
    doc = await _doc(db_session, w["document"].id)
    assert (doc.verification_status, doc.expiry_date.isoformat()) == ("verified", future)


@pytest.mark.asyncio
async def test_a_passport_with_a_stored_expiry_is_verified_and_other_statuses_need_none(db_session):
    w = await _world(db_session, document_type="passport", expiry=date.today() + timedelta(days=400))
    other = await _world(db_session, document_type="Passport")
    async with client_for(w["counselor"].email) as c:
        assert (await c.patch(VERIFY.format(w["document"].id), json={"verification_status": "verified"})).status_code == 200
    async with client_for(other["counselor"].email) as c:
        assert (await c.patch(VERIFY.format(other["document"].id), json={"verification_status": "incomplete", "notes": "Blurry"})).status_code == 200


@pytest.mark.parametrize(
    ("document_type", "status", "refused"),
    [
        ("QA Passport", "verified", True),
        ("Passport copy (front)", "verified", True),
        ("passports", "verified", False),
        ("SOP draft", "draft", False),
        ("Statement of Purpose v2", "approved", False),
        ("CVS receipt", "draft", True),
    ],
)
def test_type_rules_match_free_text_names_by_word(document_type, status, refused):  # browser QA-01: student types are free text
    from app.document_checklists import review_refusal

    assert (review_refusal(document_type, status, None, date(2030, 1, 1)) is not None) is refused


@pytest.mark.asyncio
async def test_an_upload_may_carry_an_expiry_date(db_session):
    w = await _world(db_session)
    future = (date.today() + timedelta(days=30)).isoformat()
    async with client_for(w["student"].email) as s:
        response = await s.post(UPLOAD, json={"application_id": str(w["application"].id), "document_type": "Passport", "file_url": "uploads/p.pdf", "expiry_date": future})
    assert response.status_code == 201, response.text
    assert (await _doc(db_session, response.json()["id"])).expiry_date.isoformat() == future


# --- S3: versions -----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replace_creates_a_new_version_and_archives_the_old_one(db_session):
    w = await _world(db_session, status="reupload_required", expiry=date(2031, 5, 1))
    old_key = w["document"].file_url
    async with client_for(w["counselor"].email) as c:
        response = await c.post(VERSIONS.format(w["document"].id), files=_file())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["verification_status"] == "pending" and body["version_of_id"] == str(w["document"].id)
    old, new = await _doc(db_session, w["document"].id), await _doc(db_session, body["id"])
    assert old.archived_at is not None and old.file_url == old_key and old.verification_status == "reupload_required"  # never overwritten
    assert (new.student_id, new.application_id, new.document_type, new.expiry_date) == (old.student_id, old.application_id, old.document_type, old.expiry_date)
    assert new.file_url != old_key and new.archived_at is None and new.uploaded_by_user_id == w["counselor"].id
    assert await _events(db_session, old.id) == ["replaced"] and await _events(db_session, new.id) == ["uploaded"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "document.replace", AuditLog.entity_id == str(new.id)))
    assert audit is not None and audit.metadata_json == {"version_of_id": str(old.id)}


@pytest.mark.asyncio
async def test_replace_takes_a_new_expiry_and_an_archived_version_is_read_only(db_session):
    w = await _world(db_session, document_type="Passport")
    async with client_for(w["counselor"].email) as c:
        first = await c.post(VERSIONS.format(w["document"].id), files=_file(), data={"expiry_date": "2033-02-02"})
        assert first.status_code == 201 and first.json()["expiry_date"] == "2033-02-02"
        again = await c.post(VERSIONS.format(w["document"].id), files=_file())
        review = await c.patch(VERIFY.format(w["document"].id), json={"verification_status": "verified", "expiry_date": "2033-02-02"})
    assert again.status_code == 409 and review.status_code == 409


@pytest.mark.asyncio
async def test_replace_is_scoped_like_review_and_checks_the_file(db_session):
    w = await _world(db_session)
    stranger = await mk_user(db_session, role="counselor")
    async with client_for(stranger.email) as c:
        assert (await c.post(VERSIONS.format(w["document"].id), files=_file())).status_code == 403
    async with client_for(w["student"].email) as s:
        assert (await s.post(VERSIONS.format(w["document"].id), files=_file())).status_code == 403
    async with client_for(w["counselor"].email) as c:
        assert (await c.post(VERSIONS.format(w["document"].id), files=_file(b"not a pdf"))).status_code == 415
    assert (await _doc(db_session, w["document"].id)).archived_at is None


@pytest.mark.asyncio
async def test_lists_show_the_current_version_with_review_metadata(db_session):
    w = await _world(db_session, expiry=date(2032, 1, 1))
    async with client_for(w["counselor"].email) as c:
        new_id = (await c.post(VERSIONS.format(w["document"].id), files=_file())).json()["id"]
        await c.patch(VERIFY.format(new_id), json={"verification_status": "verified", "notes": "Fine"})
        queue = (await c.get(QUEUE)).json()["rows"]
    mine = [r for r in queue if r["id"] in {str(w["document"].id), new_id}]
    assert [r["id"] for r in mine] == [new_id]
    row = mine[0]
    assert (row["status"], row["notes"], row["reviewer"], row["expiry_date"], row["replaces_earlier"]) == ("verified", "Fine", "Doc Counselor", "2032-01-01", True)
    assert row["reviewed_at"] and row["status_label"] == "Verified"  # browser QA-02: the generic table shows words
    async with client_for(w["student"].email) as s:
        student_rows = (await s.get(STUDENT_DOCS)).json()["rows"]
    assert [r["id"] for r in student_rows] == [new_id]


@pytest.mark.asyncio
async def test_there_is_no_delete_route(db_session):  # S7: archive is the only way out of the lists
    w = await _world(db_session)
    async with client_for(w["counselor"].email) as c:
        assert (await c.delete(f"{UPLOAD}/{w['document'].id}")).status_code in {404, 405}  # no such route


# --- agency review keeps AGN-003, with the new codes --------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agency_master_decides_with_new_or_legacy_codes(db_session):
    ctx = await mk_active_org(db_session, name=f"ccrm021 {uniq()}")
    first, second = await agency_document(db_session, ctx), await agency_document(db_session, ctx)
    async with client_for(ctx["master"].email) as m:
        new = await m.patch(VERIFY.format(first["document"].id), json={"verification_status": "incomplete", "notes": "Page 2 missing"})
        legacy = await m.patch(VERIFY.format(second["document"].id), json={"verification_status": "rejected", "notes": "Wrong file"})
    assert new.json()["verification_status"] == "incomplete" and legacy.json()["verification_status"] == "reupload_required"
    doc = await _doc(db_session, first["document"].id)
    assert doc.reviewed_at is not None


@pytest.mark.asyncio
async def test_agency_staff_still_only_verify(db_session):
    ctx = await mk_active_org(db_session, name=f"ccrm021 staff {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], can_verify_documents=True)
    w = await agency_document(db_session, ctx, assigned_to=staff["member"])
    async with client_for(staff["user"].email) as s:
        assert (await s.patch(VERIFY.format(w["document"].id), json={"verification_status": "reupload_required", "notes": "x"})).status_code == 403


# --- S4: the expiry job -----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_expiry_job_marks_expired_documents_once(db_session):
    today = date(2030, 6, 15)
    lapsed = await _world(db_session, status="verified", expiry=today - timedelta(days=1))
    due_today = await _world(db_session, status="verified", expiry=today)
    waived = await _world(db_session, status="not_required", expiry=today - timedelta(days=9))
    archived = await _world(db_session, status="verified", expiry=today - timedelta(days=9))
    archived["document"].archived_at = datetime.now(UTC)
    await db_session.commit()

    assert await expire_documents(db_session, today) >= 1
    assert await expire_documents(db_session, today) == 0  # idempotent
    assert (await _doc(db_session, lapsed["document"].id)).verification_status == "expired"
    for w in (due_today, waived, archived):
        assert (await _doc(db_session, w["document"].id)).verification_status != "expired"
    event = await db_session.scalar(select(DocumentEvent).where(DocumentEvent.document_id == lapsed["document"].id))
    assert (event.event, event.from_status, event.to_status, event.actor_user_id) == ("expired", "verified", "expired", None)
