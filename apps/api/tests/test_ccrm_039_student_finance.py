"""ccrm-039 (DEC-SCOPE-272, F1-F7) -- the finance tab of the counselor's student 360: read-only GET /counselor/students/{id}/finance.
The student's service fees and payments (with invoice / receipt numbers), each application's university deposit (ccrm-025 record or
AGN-011 agency deposit) and refunds. Same gate as ccrm-009; downloads keep their own routes' rules."""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models import ApplicationDeposit, ApplicationDepositRecord, Invoice, Payment, Receipt, StudentDocument
from tests.agn001_helpers import login, mk_user, uniq
from tests.enh031_helpers import mk_application, mk_university


def url(student_id) -> str:
    return f"/api/v1/counselor/students/{student_id}/finance"


async def mk_payment(db, user, *, status="pending", amount="25000.00", reference_type="service_fee", invoice=True, receipt=False, **fields) -> Payment:
    payment = Payment(user_id=user.id, division="overseas", reference_type=reference_type, amount=Decimal(amount), currency="INR", provider="manual", status=status, is_manual=True, **fields)
    db.add(payment)
    await db.flush()
    if invoice:
        db.add(Invoice(payment_id=payment.id, user_id=user.id, division="overseas", invoice_no=uniq("INV"), amount=payment.amount, file_url="/local-files/i.pdf"))
    if receipt:
        db.add(Receipt(payment_id=payment.id, user_id=user.id, division="overseas", receipt_no=uniq("RCT"), amount=payment.amount, file_url="/local-files/r.pdf"))
    await db.commit()
    return payment


@pytest_asyncio.fixture
async def world(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name="Nora Counselor")
    other = await mk_user(db_session, role="counselor", full_name="Omar Counselor")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Ada Admin")
    agent = await mk_user(db_session, role="agent", full_name="Agnes Agent")
    student = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('c39')} Student")
    own = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("Alpha Uni")), counselor=counselor, status="offer")
    foreign = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("Beta Uni")), counselor=other, status="offer")
    agency = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("Gamma Uni")), counselor=counselor, agent=agent, status="offer")
    return {"counselor": counselor, "other": other, "admin": admin, "agent": agent, "student": student, "own": own, "foreign": foreign, "agency": agency}


@pytest.mark.asyncio
async def test_an_empty_finance_tab(client, world):
    await login(client, world["counselor"].email)
    response = await client.get(url(world["student"].id))
    assert response.status_code == 200, response.text
    assert response.json() == {"payments": [], "deposits": [], "refunds": []}


@pytest.mark.asyncio
async def test_lists_the_students_own_fees_with_invoice_and_receipt_numbers(client, db_session, world):
    paid = await mk_payment(db_session, world["student"], status="paid", receipt=True)
    due = await mk_payment(db_session, world["student"], status="pending", amount="1200.50", due_date=date(2027, 1, 15), invoice=False)
    await mk_payment(db_session, world["other"], status="paid")  # someone else's
    await mk_payment(db_session, world["student"], reference_type="agent_deposit")  # F7: never an agency deposit payment
    await login(client, world["counselor"].email)
    data = (await client.get(url(world["student"].id))).json()
    rows = {p["id"]: p for p in data["payments"]}
    assert set(rows) == {str(paid.id), str(due.id)}
    p, d = rows[str(paid.id)], rows[str(due.id)]
    assert (p["description"], p["amount"], p["currency"], p["status"], p["status_label"]) == ("Service fee", "25000.00", "INR", "paid", "Paid")
    assert p["invoice_no"].startswith("INV") and p["receipt_no"].startswith("RCT")
    assert (d["amount"], d["due_date"], d["status_label"], d["invoice_no"], d["receipt_no"]) == ("1200.50", "2027-01-15", "Pending", None, None)
    assert p["can_download"] is False and d["can_download"] is False  # F5: the receipt route refuses a counselor
    assert "file_url" not in str(data)


@pytest.mark.asyncio
async def test_the_overseas_admin_reads_it_and_may_download(client, db_session, world):
    await mk_payment(db_session, world["student"], status="paid", receipt=True)
    await login(client, world["admin"].email)
    response = await client.get(url(world["student"].id))
    assert response.status_code == 200, response.text
    assert [p["can_download"] for p in response.json()["payments"]] == [True]


@pytest.mark.asyncio
async def test_deposits_on_every_application_counselor_record_and_agency_deposit(client, db_session, world):
    receipt = StudentDocument(student_id=world["student"].id, application_id=world["own"].id, document_type="Deposit receipt", file_url="/local-files/d.pdf")
    db_session.add(receipt)
    await db_session.flush()
    c = world["counselor"]
    db_session.add_all([
        ApplicationDepositRecord(application_id=world["own"].id, required=True, amount=Decimal("3000.00"), currency="GBP", due_date=date(2026, 12, 1), payment_status="paid_to_university", paid_on=date(2026, 10, 1), receipt_document_id=receipt.id, recorded_by_id=c.id, updated_by_id=c.id),
        ApplicationDepositRecord(application_id=world["foreign"].id, required=False, payment_status="not_required", recorded_by_id=world["other"].id, updated_by_id=world["other"].id),
        ApplicationDeposit(application_id=world["agency"].id, required=True, amount=Decimal("50000.00"), currency="INR", status="pending", created_by_user_id=world["agent"].id, updated_by_user_id=world["agent"].id),
    ])  # fmt: skip
    await db_session.commit()
    await login(client, c.email)
    deposits = {d["application_id"]: d for d in (await client.get(url(world["student"].id))).json()["deposits"]}
    own, foreign, agency = deposits[str(world["own"].id)], deposits[str(world["foreign"].id)], deposits[str(world["agency"].id)]
    assert (own["source"], own["mine"], own["amount"], own["currency"], own["status_label"], own["paid_on"]) == ("counselor", True, "3000.00", "GBP", "Paid directly to the university", "2026-10-01")
    assert own["receipt"] == {"id": str(receipt.id), "name": "Deposit receipt", "can_download": True} and own["refund"] is None
    assert (foreign["source"], foreign["mine"], foreign["required"], foreign["amount"], foreign["status_label"]) == ("counselor", False, False, None, "Not required")
    assert (agency["source"], agency["amount"], agency["currency"], agency["status_label"], agency["receipt"]) == ("agency", "50000.00", "INR", "Pending", None)
    assert own["application_code"].startswith("APP-") and own["university"]


@pytest.mark.asyncio
async def test_a_receipt_on_another_counselors_application_is_not_downloadable(client, db_session, world):
    receipt = StudentDocument(student_id=world["student"].id, application_id=world["foreign"].id, document_type="Deposit receipt", file_url="/local-files/d.pdf")
    db_session.add(receipt)
    await db_session.flush()
    o = world["other"]
    db_session.add(
        ApplicationDepositRecord(
            application_id=world["foreign"].id,
            required=True,
            amount=Decimal("10.00"),
            currency="USD",
            payment_status="pending",
            receipt_document_id=receipt.id,
            recorded_by_id=o.id,
            updated_by_id=o.id,
        )
    )
    await db_session.commit()
    await login(client, world["counselor"].email)
    [deposit] = (await client.get(url(world["student"].id))).json()["deposits"]
    assert deposit["receipt"]["can_download"] is False


@pytest.mark.asyncio
async def test_refunds_from_payments_and_agency_deposits(client, db_session, world):
    refunded = await mk_payment(db_session, world["student"], status="refunded", amount="5000.00")
    db_session.add(
        ApplicationDeposit(
            application_id=world["agency"].id, required=True, amount=Decimal("50000.00"), currency="INR", status="refunded", paid_payment_id=refunded.id,
            paid_at=refunded.created_at, refunded_at=date(2026, 9, 30), refund_amount=Decimal("45000.00"), refund_reason="Visa refused",
            created_by_user_id=world["agent"].id, updated_by_user_id=world["agent"].id,
        )
    )  # fmt: skip
    await db_session.commit()
    await login(client, world["counselor"].email)
    data = (await client.get(url(world["student"].id))).json()
    assert [p["status_label"] for p in data["payments"]] == ["Refunded"]
    [deposit] = data["deposits"]
    assert deposit["status_label"] == "Refunded" and deposit["refund"] == {"amount": "45000.00", "refunded_on": "2026-09-30", "reason": "Visa refused"}
    refunds = {r["kind"]: r for r in data["refunds"]}
    assert (refunds["payment"]["description"], refunds["payment"]["amount"], refunds["payment"]["application_code"]) == ("Service fee", "5000.00", None)
    assert (refunds["deposit"]["amount"], refunds["deposit"]["refunded_on"], refunds["deposit"]["application_code"]) == ("45000.00", "2026-09-30", deposit["application_code"])


@pytest.mark.asyncio
async def test_another_counselors_student_is_not_found(client, db_session, world):
    stranger = await mk_user(db_session, role="overseas_student")
    await mk_payment(db_session, stranger, status="paid")
    await login(client, world["counselor"].email)
    assert (await client.get(url(stranger.id))).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["overseas_student", "agent", "university_rep"])
async def test_other_roles_are_refused(client, db_session, world, role):
    reader = world["student"] if role == "overseas_student" else world["agent"] if role == "agent" else await mk_user(db_session, role=role)
    await login(client, reader.email)
    assert (await client.get(url(world["student"].id))).status_code == 403


@pytest.mark.asyncio
async def test_an_it_counselor_is_refused(client, db_session, world):
    it_counselor = await mk_user(db_session, role="counselor", division="it")
    await login(client, it_counselor.email, division="it")
    assert (await client.get(url(world["student"].id))).status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_is_refused(client, world):
    assert (await client.get(url(world["student"].id))).status_code == 401
