"""ccrm-048 (DEC-SCOPE-321) -- the deposit receipt is uploaded from the student 360's Finance tab: POST
/workflows/overseas/applications/{id}/deposit/receipt (multipart) stores a "Deposit receipt" document and attaches it to the counselor's
deposit record in one transaction. The counselor on their own application, the Overseas Admin on any; never beside an agency (AGN-011)
deposit or on a deposit that is not required. `finance()` says where the control is offered (`can_upload`).
Spec: docs/superpowers/specs/2026-10-28-ccrm-048-deposit-receipt-upload-design.md."""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.models import (
    ApplicationDeposit,
    ApplicationDepositRecord,
    ApplicationStatusHistory,
    AuditLog,
    Notification,
    OverseasStudentArchive,
    StudentDocument,
)  # fmt: skip
from tests.agn001_helpers import login, mk_user, uniq
from tests.agn009_helpers import PDF, PNG, upload_files
from tests.enh031_helpers import mk_application, mk_university


def url(application_id) -> str:
    return f"/api/v1/workflows/overseas/applications/{application_id}/deposit/receipt"


def finance_url(student_id) -> str:
    return f"/api/v1/counselor/students/{student_id}/finance"


def record(application, by, *, required=True) -> ApplicationDepositRecord:
    if not required:
        return ApplicationDepositRecord(application_id=application.id, required=False, payment_status="not_required", recorded_by_id=by.id, updated_by_id=by.id)
    return ApplicationDepositRecord(
        application_id=application.id, required=True, amount=Decimal("3000.00"), currency="GBP", due_date=date(2026, 12, 1), payment_status="pending",
        recorded_by_id=by.id, updated_by_id=by.id,
    )  # fmt: skip


@pytest_asyncio.fixture
async def w(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name="Nora Counselor")
    other = await mk_user(db_session, role="counselor", full_name="Omar Counselor")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Ada Admin")
    agent = await mk_user(db_session, role="agent", full_name="Agnes Agent")
    student = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('c48')} Student")
    own = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("Alpha Uni")), counselor=counselor, status="offer")
    foreign = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("Beta Uni")), counselor=other, status="offer")
    agency = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("Gamma Uni")), counselor=counselor, agent=agent, status="offer")
    unrequired = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("Delta Uni")), counselor=counselor, status="offer")
    bare = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("Eps Uni")), counselor=counselor, status="offer")
    db_session.add_all([
        record(own, counselor), record(foreign, other), record(unrequired, counselor, required=False),
        ApplicationDeposit(application_id=agency.id, required=True, amount=Decimal("50000.00"), currency="INR", status="pending", created_by_user_id=agent.id, updated_by_user_id=agent.id),
    ])  # fmt: skip
    await db_session.commit()
    return {"counselor": counselor, "other": other, "admin": admin, "agent": agent, "student": student, "own": own, "foreign": foreign, "agency": agency, "unrequired": unrequired, "bare": bare}


async def _record(db_session, application) -> ApplicationDepositRecord:
    stmt = select(ApplicationDepositRecord).where(ApplicationDepositRecord.application_id == application.id).execution_options(populate_existing=True)
    return await db_session.scalar(stmt)


@pytest.mark.asyncio
async def test_ac1_counselor_uploads_a_receipt_and_it_is_attached(client, db_session, w):
    await login(client, w["counselor"].email)
    response = await client.post(url(w["own"].id), files=upload_files(PDF, "deposit.pdf"))
    assert response.status_code == 201, response.text
    receipt = response.json()["record"]["receipt"]
    assert receipt["name"] == "deposit.pdf" and "file_url" not in str(response.json())
    rec = await _record(db_session, w["own"])
    assert str(rec.receipt_document_id) == receipt["id"] and rec.updated_by_id == w["counselor"].id
    assert (rec.amount, rec.payment_status) == (Decimal("3000.00"), "pending")  # nothing else on the record moves
    doc = await db_session.get(StudentDocument, rec.receipt_document_id)
    assert (doc.student_id, doc.application_id, doc.uploaded_by_user_id, doc.document_type) == (w["student"].id, w["own"].id, w["counselor"].id, "Deposit receipt")
    # shown with a download on the Finance tab
    [deposit] = [d for d in (await client.get(finance_url(w["student"].id))).json()["deposits"] if d["application_id"] == str(w["own"].id)]
    assert deposit["receipt"] == {"id": receipt["id"], "name": "Deposit receipt", "can_download": True}
    # history, audit and the student's notice
    notes = (await db_session.scalars(select(ApplicationStatusHistory.notes).where(ApplicationStatusHistory.application_id == w["own"].id))).all()
    assert "Deposit receipt uploaded." in notes
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "overseas.application.deposit_receipt", AuditLog.entity_id == str(w["own"].id)))
    assert audit is not None and audit.metadata_json == {"replaced": False, "document_id": receipt["id"]}
    assert await db_session.scalar(select(Notification.id).where(Notification.user_id == w["student"].id, Notification.title == "Deposit receipt added"))


@pytest.mark.asyncio
async def test_the_student_sees_the_receipt_in_their_documents(client, db_session, w):
    await login(client, w["counselor"].email)
    receipt = (await client.post(url(w["own"].id), files=upload_files())).json()["record"]["receipt"]
    await login(client, w["student"].email)
    docs = (await client.get("/api/v1/portal/overseas/student/documents")).json()
    assert receipt["id"] in str(docs)


@pytest.mark.asyncio
async def test_ac2_overseas_admin_replaces_it(client, db_session, w):
    await login(client, w["counselor"].email)
    first = (await client.post(url(w["own"].id), files=upload_files())).json()["record"]["receipt"]["id"]
    await login(client, w["admin"].email)
    response = await client.post(url(w["own"].id), files=upload_files(PNG, "scan.png", "image/png"))
    assert response.status_code == 201, response.text
    second = response.json()["record"]["receipt"]["id"]
    rec = await _record(db_session, w["own"])
    assert second != first and str(rec.receipt_document_id) == second and rec.updated_by_id == w["admin"].id
    old = await db_session.get(StudentDocument, first)
    assert old.archived_at is None  # the replaced receipt stays one of the student's documents
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "overseas.application.deposit_receipt", AuditLog.user_id == w["admin"].id))
    assert audit.metadata_json["replaced"] is True
    notes = (await db_session.scalars(select(ApplicationStatusHistory.notes).where(ApplicationStatusHistory.application_id == w["own"].id))).all()
    assert "Deposit receipt replaced." in notes


@pytest.mark.asyncio
async def test_ac3_agency_deposit_is_409(client, db_session, w):
    await login(client, w["admin"].email)
    response = await client.post(url(w["agency"].id), files=upload_files())
    assert response.status_code == 409
    assert await db_session.scalar(select(StudentDocument.id).where(StudentDocument.application_id == w["agency"].id)) is None


@pytest.mark.asyncio
async def test_ac4_another_counselors_application_is_403(client, db_session, w):
    await login(client, w["counselor"].email)
    assert (await client.post(url(w["foreign"].id), files=upload_files())).status_code == 403
    assert (await _record(db_session, w["foreign"])).receipt_document_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("which", ["unrequired", "bare"])
async def test_ac5_no_required_deposit_is_422_and_nothing_is_stored(client, db_session, w, which):
    await login(client, w["counselor"].email)
    response = await client.post(url(w[which].id), files=upload_files())
    assert response.status_code == 422
    assert response.json()["detail"] == "Record a required deposit on the application first"
    assert await db_session.scalar(select(StudentDocument.id).where(StudentDocument.application_id == w[which].id)) is None


@pytest.mark.asyncio
async def test_archived_student_is_409(client, db_session, w):
    db_session.add(OverseasStudentArchive(student_user_id=w["student"].id, archived_by_user_id=w["admin"].id, reason="Left"))
    await db_session.commit()
    await login(client, w["admin"].email)
    assert (await client.post(url(w["own"].id), files=upload_files())).status_code == 409


@pytest.mark.asyncio
async def test_withdrawn_application_is_409(client, db_session, w):
    w["own"].status = "withdrawn"
    await db_session.commit()
    await login(client, w["counselor"].email)
    assert (await client.post(url(w["own"].id), files=upload_files())).status_code == 409


@pytest.mark.asyncio
async def test_unknown_application_is_404(client, w):
    await login(client, w["admin"].email)
    assert (await client.post(url("00000000-0000-0000-0000-000000000000"), files=upload_files())).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(("data", "name", "code"), [(b"hello", "notes.txt", 415), (b"", "empty.pdf", 422)])
async def test_file_type_is_sniffed_and_nothing_is_attached(client, db_session, w, data, name, code):
    await login(client, w["counselor"].email)
    assert (await client.post(url(w["own"].id), files=upload_files(data, name))).status_code == code
    assert (await _record(db_session, w["own"])).receipt_document_id is None


@pytest.mark.asyncio
async def test_oversize_is_413(client, w, monkeypatch):
    await login(client, w["counselor"].email)
    monkeypatch.setattr(settings, "max_upload_bytes", 16)
    assert (await client.post(url(w["own"].id), files=upload_files())).status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["overseas_student", "agent", "telecaller"])
async def test_other_roles_are_refused(client, db_session, w, role):
    user = w["student"] if role == "overseas_student" else w["agent"] if role == "agent" else await mk_user(db_session, role=role)
    await login(client, user.email)
    assert (await client.post(url(w["own"].id), files=upload_files())).status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client, w):
    assert (await client.post(url(w["own"].id), files=upload_files())).status_code == 401


@pytest.mark.asyncio
async def test_finance_says_where_the_upload_is_offered(client, db_session, w):
    await login(client, w["counselor"].email)
    deposits = {d["application_id"]: d["can_upload"] for d in (await client.get(finance_url(w["student"].id))).json()["deposits"]}
    assert deposits == {str(w["own"].id): True, str(w["foreign"].id): False, str(w["agency"].id): False, str(w["unrequired"].id): False}
    await login(client, w["admin"].email)
    deposits = {d["application_id"]: d["can_upload"] for d in (await client.get(finance_url(w["student"].id))).json()["deposits"]}
    assert deposits == {str(w["own"].id): True, str(w["foreign"].id): True, str(w["agency"].id): False, str(w["unrequired"].id): False}


@pytest.mark.asyncio
async def test_finance_offers_no_upload_on_a_closed_application_or_an_archived_student(client, db_session, w):
    w["own"].status = "withdrawn"
    await db_session.commit()
    await login(client, w["admin"].email)
    deposits = {d["application_id"]: d["can_upload"] for d in (await client.get(finance_url(w["student"].id))).json()["deposits"]}
    assert deposits[str(w["own"].id)] is False and deposits[str(w["foreign"].id)] is True
    db_session.add(OverseasStudentArchive(student_user_id=w["student"].id, archived_by_user_id=w["admin"].id, reason="Left"))
    await db_session.commit()
    deposits = {d["application_id"]: d["can_upload"] for d in (await client.get(finance_url(w["student"].id))).json()["deposits"]}
    assert not any(deposits.values())
