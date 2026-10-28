"""ccrm-049 (DEC-SCOPE-324) -- a payment receipt / proof is uploaded from the student 360's Finance tab: POST
/counselor/students/{id}/payments/{pid}/proof (multipart) stores a "Payment receipt" document of the student and links it as
`payments.proof_document_id` in one transaction. The counselor for a student in their caseload, the Overseas Admin any; manual payments
only; the system receipt is untouched. Spec: docs/superpowers/specs/2026-10-28-ccrm-049-payment-proof-upload-design.md."""

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.config import settings
from app.models import AuditLog, DocumentEvent, OverseasStudentArchive, OverseasStudentCounselor, Payment, Receipt, StudentDocument
from app.services import agent_deposits
from tests.agn001_helpers import login, mk_user, uniq
from tests.agn009_helpers import PDF, PNG, upload_files


def url(student_id, payment_id) -> str:
    return f"/api/v1/counselor/students/{student_id}/payments/{payment_id}/proof"


def finance_url(student_id) -> str:
    return f"/api/v1/counselor/students/{student_id}/finance"


def payment(student, **over) -> Payment:
    values = {"user_id": student.id, "division": "overseas", "reference_type": "service_fee", "amount": Decimal("1500.00"), "currency": "GBP", "provider": "manual", "status": "pending", "is_manual": True}  # fmt: skip
    return Payment(**(values | over))


@pytest_asyncio.fixture
async def w(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name="Nora Counselor")
    other = await mk_user(db_session, role="counselor", full_name="Omar Counselor")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Ada Admin")
    student = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('c49')} Student")
    stranger = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('c49')} Stranger")
    db_session.add_all([OverseasStudentCounselor(student_user_id=s.id, counselor_user_id=counselor.id, assigned_by_user_id=admin.id) for s in (student, stranger)])
    manual, online, foreign = payment(student), payment(student, provider="razorpay", status="paid"), payment(stranger)
    deposit = payment(student, reference_type=agent_deposits.REFERENCE_TYPE)
    db_session.add_all([manual, online, foreign, deposit])
    await db_session.flush()
    receipt = Receipt(payment_id=manual.id, user_id=student.id, division="overseas", receipt_no=uniq("RCPT-49-"), amount=manual.amount, currency="GBP", file_url="receipts/x.pdf")
    db_session.add(receipt)
    await db_session.commit()
    return {"counselor": counselor, "other": other, "admin": admin, "student": student, "stranger": stranger, "manual": manual, "online": online, "foreign": foreign, "deposit": deposit, "receipt": receipt}  # fmt: skip


async def _payment(db_session, item) -> Payment:
    return await db_session.scalar(select(Payment).where(Payment.id == item.id).execution_options(populate_existing=True))


async def _docs(db_session, student) -> list[StudentDocument]:
    return (await db_session.scalars(select(StudentDocument).where(StudentDocument.student_id == student.id))).all()


@pytest.mark.asyncio
async def test_ac1_counselor_attaches_a_proof_and_the_student_sees_it(client, db_session, w):
    await login(client, w["counselor"].email)
    response = await client.post(url(w["student"].id, w["manual"].id), files=upload_files(PDF, "transfer.pdf"))
    assert response.status_code == 201, response.text
    row = response.json()["payment"]
    assert row["id"] == str(w["manual"].id) and "file_url" not in str(response.json())
    pay = await _payment(db_session, w["manual"])
    assert str(pay.proof_document_id) == row["proof"]["id"] and row["proof"] == {"id": row["proof"]["id"], "name": "Service fee", "can_download": True}
    assert (pay.amount, pay.status) == (Decimal("1500.00"), "pending")  # never the money fields
    doc = await db_session.get(StudentDocument, pay.proof_document_id)
    assert (doc.student_id, doc.application_id, doc.uploaded_by_user_id, doc.document_type, doc.verification_status) == (w["student"].id, None, w["counselor"].id, "Payment receipt", "pending")
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "payment.proof_attached", AuditLog.entity_id == str(w["manual"].id)))
    assert audit is not None and audit.metadata_json == {"replaced": False, "document_id": row["proof"]["id"], "student_id": str(w["student"].id)}
    # the student: their Documents, and the Payments section's "Uploaded proof" column (never a file key)
    await login(client, w["student"].email)
    assert row["proof"]["id"] in str((await client.get("/api/v1/portal/overseas/student/documents")).json())
    payments = (await client.get("/api/v1/portal/overseas/student/payments")).json()
    assert {"key": "proof", "label": "Uploaded proof"} in payments["columns"]
    [mine] = [r for r in payments["rows"] if r["id"] == str(w["manual"].id)]
    assert mine["proof"] == "Service fee — download from Documents" and doc.file_url not in str(payments)


@pytest.mark.asyncio
async def test_ac2_overseas_admin_replaces_it_audited(client, db_session, w):
    await login(client, w["counselor"].email)
    first = (await client.post(url(w["student"].id, w["manual"].id), files=upload_files())).json()["payment"]["proof"]["id"]
    await login(client, w["admin"].email)
    response = await client.post(url(w["student"].id, w["manual"].id), files=upload_files(PNG, "scan.png", "image/png"))
    assert response.status_code == 201, response.text
    second = response.json()["payment"]["proof"]["id"]
    assert second != first and str((await _payment(db_session, w["manual"])).proof_document_id) == second
    assert (await db_session.get(StudentDocument, first)).archived_at is None  # the replaced proof stays one of the student's documents
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "payment.proof_attached", AuditLog.user_id == w["admin"].id))
    assert audit.metadata_json["replaced"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("which", ["foreign", "deposit"])
async def test_ac3_a_payment_that_is_not_this_students_is_404(client, db_session, w, which):
    await login(client, w["admin"].email)
    response = await client.post(url(w["student"].id, w[which].id), files=upload_files())
    assert response.status_code == 404 and response.json()["detail"] == "Payment not found"
    assert await _docs(db_session, w["student"]) == []


@pytest.mark.asyncio
async def test_unknown_payment_is_404(client, w):
    await login(client, w["admin"].email)
    assert (await client.post(url(w["student"].id, "00000000-0000-0000-0000-000000000000"), files=upload_files())).status_code == 404


@pytest.mark.asyncio
async def test_ac4_counselor_outside_the_caseload_is_404(client, db_session, w):
    await login(client, w["other"].email)
    assert (await client.post(url(w["student"].id, w["manual"].id), files=upload_files())).status_code == 404
    assert (await _payment(db_session, w["manual"])).proof_document_id is None


@pytest.mark.asyncio
async def test_ac6_the_system_receipt_is_unaffected(client, db_session, w):
    await login(client, w["admin"].email)
    row = (await client.post(url(w["student"].id, w["manual"].id), files=upload_files())).json()["payment"]
    assert row["receipt_no"] == w["receipt"].receipt_no
    receipt = await db_session.scalar(select(Receipt).where(Receipt.payment_id == w["manual"].id).execution_options(populate_existing=True))
    assert (receipt.id, receipt.file_url) == (w["receipt"].id, "receipts/x.pdf")


@pytest.mark.asyncio
async def test_a_gateway_payment_is_409(client, db_session, w):
    await login(client, w["admin"].email)
    response = await client.post(url(w["student"].id, w["online"].id), files=upload_files())
    assert response.status_code == 409 and response.json()["detail"] == "An online payment already has its system receipt"
    assert await _docs(db_session, w["student"]) == []


@pytest.mark.asyncio
async def test_archived_student_is_409(client, db_session, w):
    db_session.add(OverseasStudentArchive(student_user_id=w["student"].id, archived_by_user_id=w["admin"].id, reason="Left"))
    await db_session.commit()
    await login(client, w["admin"].email)
    assert (await client.post(url(w["student"].id, w["manual"].id), files=upload_files())).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(("data", "name", "code"), [(b"hello", "notes.txt", 415), (b"", "empty.pdf", 422)])
async def test_file_type_is_sniffed_and_nothing_is_attached(client, db_session, w, data, name, code):
    await login(client, w["counselor"].email)
    assert (await client.post(url(w["student"].id, w["manual"].id), files=upload_files(data, name))).status_code == code
    assert (await _payment(db_session, w["manual"])).proof_document_id is None and await _docs(db_session, w["student"]) == []


@pytest.mark.asyncio
async def test_oversize_is_413(client, w, monkeypatch):
    await login(client, w["counselor"].email)
    monkeypatch.setattr(settings, "max_upload_bytes", 16)
    assert (await client.post(url(w["student"].id, w["manual"].id), files=upload_files())).status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["overseas_student", "agent", "telecaller"])
async def test_other_roles_are_refused(client, db_session, w, role):
    user = w["student"] if role == "overseas_student" else await mk_user(db_session, role=role)
    await login(client, user.email)
    assert (await client.post(url(w["student"].id, w["manual"].id), files=upload_files())).status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client, w):
    assert (await client.post(url(w["student"].id, w["manual"].id), files=upload_files())).status_code == 401


@pytest.mark.asyncio
async def test_finance_says_where_the_upload_is_offered(client, db_session, w):
    await login(client, w["counselor"].email)
    rows = {p["id"]: p for p in (await client.get(finance_url(w["student"].id))).json()["payments"]}
    assert {k: (p["can_upload_proof"], p["proof"]) for k, p in rows.items()} == {str(w["manual"].id): (True, None), str(w["online"].id): (False, None)}
    db_session.add(OverseasStudentArchive(student_user_id=w["student"].id, archived_by_user_id=w["admin"].id, reason="Left"))
    await db_session.commit()
    await login(client, w["admin"].email)
    assert not any(p["can_upload_proof"] for p in (await client.get(finance_url(w["student"].id))).json()["payments"])


@pytest.mark.asyncio
async def test_a_deleted_document_leaves_no_proof(client, db_session, w):
    await login(client, w["admin"].email)
    proof = (await client.post(url(w["student"].id, w["manual"].id), files=upload_files())).json()["payment"]["proof"]["id"]
    await db_session.execute(delete(DocumentEvent).where(DocumentEvent.document_id == proof))  # its append-only history goes first
    await db_session.execute(delete(StudentDocument).where(StudentDocument.id == proof))
    await db_session.commit()
    assert (await _payment(db_session, w["manual"])).proof_document_id is None  # ON DELETE SET NULL
    [row] = [p for p in (await client.get(finance_url(w["student"].id))).json()["payments"] if p["id"] == str(w["manual"].id)]
    assert row["proof"] is None
