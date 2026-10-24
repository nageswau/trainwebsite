"""ccrm-025 (DEC-SCOPE-255, D2) -- the counselor's manual deposit record: any currency on a direct application, the prefill from the
offer, the receipt, idempotent saves, the refusals beside an AGN-011 deposit and on a closed application, scope, and no file keys."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import ApplicationDepositRecord, AuditLog
from tests.agn001_helpers import client_for
from tests.agn009_helpers import PDF, mk_doc
from tests.agn011_helpers import mk_deposit
from tests.agn023_helpers import fresh, history_notes, notices
from tests.ccrm025_helpers import offers_world
from tests.test_ccrm_023_offers import BASE, OFFERS, body


@pytest_asyncio.fixture
async def world(db_session):
    return await offers_world(db_session)


DEPOSIT = BASE + "/deposit"
RECEIPTS = BASE + "/deposit-receipts"
PAID = {"required": True, "amount": "3000", "currency": "gbp", "due_date": "2026-11-30", "payment_status": "paid_to_university", "paid_on": "2026-10-20"}


async def _record(db, app) -> ApplicationDepositRecord | None:
    stmt = select(ApplicationDepositRecord).where(ApplicationDepositRecord.application_id == app.id)
    return await db.scalar(stmt.execution_options(populate_existing=True))


@pytest.mark.asyncio
async def test_the_counselor_records_a_gbp_deposit_with_a_receipt_on_a_direct_application(db_session, world):  # AC5
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(OFFERS.format(app.id), json=body(world["direct_letter"]))).status_code == 201
        start = (await c.get(DEPOSIT.format(app.id))).json()
        upload = await c.post(RECEIPTS.format(app.id), files={"file": ("receipt.pdf", PDF, "application/pdf")})
        assert upload.status_code == 201, upload.text
        receipt = upload.json()["document"]
        r = await c.put(DEPOSIT.format(app.id), json=PAID | {"receipt_document_id": receipt["id"]})
        again = await c.put(DEPOSIT.format(app.id), json=PAID | {"receipt_document_id": receipt["id"]})
        listed = (await c.get(DEPOSIT.format(app.id))).json()
    assert start["record"] is None and start["agency_deposit"] is None
    assert start["prefill"] == {"amount": "3000.00", "currency": "GBP", "due_date": body(world["direct_letter"])["deposit_deadline"]}
    assert r.status_code == 200, r.text
    record = r.json()["record"]
    assert (record["amount"], record["currency"], record["payment_status_label"], record["paid_on"]) == ("3000.00", "GBP", "Paid directly to the university", "2026-10-20")
    assert record["receipt"]["id"] == receipt["id"] and record["updated_by"] == world["counselor"].full_name
    assert again.json()["changed"] is False
    assert [r_["id"] for r_ in listed["receipts"]] == [receipt["id"]] and "file_url" not in str(listed)
    row = await _record(db_session, app)
    assert (row.currency, row.recorded_by_id) == ("GBP", world["counselor"].id)
    notes = [n for n in await history_notes(db_session, app) if n and n.startswith("Deposit:")]
    assert notes == ["Deposit: Paid directly to the university, GBP 3000.00, due 2026-11-30, paid 2026-10-20."]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.deposit_record"))
    assert audit.metadata_json == {"payment_status": "paid_to_university", "created": True}
    assert "Deposit updated" in [n.title for n in await notices(db_session, world["direct_student"])]


@pytest.mark.asyncio
async def test_a_save_replaces_the_record_and_not_required_clears_it(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.put(DEPOSIT.format(app.id), json={**PAID, "payment_status": "pending", "paid_on": None})).status_code == 200
        r = await c.put(DEPOSIT.format(app.id), json={"required": False, "payment_status": "not_required"})
    assert r.status_code == 200 and r.json()["record"]["required"] is False
    row = await _record(db_session, app)
    assert (row.required, row.amount, row.currency, row.payment_status) == (False, None, None, "not_required")


@pytest.mark.asyncio
async def test_validation_and_a_foreign_or_wrong_type_receipt_are_422(db_session, world):
    app = world["direct_app"]
    passport = await mk_doc(db_session, student=world["direct_student"], application=app, document_type="Passport")
    other = await mk_doc(db_session, record=world["record"], application=world["app"], document_type="Deposit receipt")
    async with client_for(world["counselor"].email) as c:
        assert (await c.put(DEPOSIT.format(app.id), json={**PAID, "paid_on": None})).status_code == 422
        assert (await c.put(DEPOSIT.format(app.id), json={"required": False, "payment_status": "not_required", "amount": "10"})).status_code == 422
        for document in (passport, other):
            r = await c.put(DEPOSIT.format(app.id), json=PAID | {"receipt_document_id": str(document.id)})
            assert r.status_code == 422 and r.json()["detail"] == "Choose a deposit receipt uploaded for this application"
    assert await _record(db_session, app) is None


@pytest.mark.asyncio
async def test_an_agency_deposit_is_shown_read_only_and_blocks_a_manual_record(db_session, world):  # AC6
    app = world["app"]
    await mk_deposit(db_session, app, by=world["master"], amount="50000.00")
    async with client_for(world["counselor"].email) as c:
        got = (await c.get(DEPOSIT.format(app.id))).json()
        r = await c.put(DEPOSIT.format(app.id), json=PAID)
    assert got["agency_deposit"] == {"status": "pending", "amount": "50000.00", "currency": "INR", "due_date": None}
    assert r.status_code == 409 and r.json()["detail"] == "The agency pays this deposit through EduSphere -- it is shown read-only"
    assert await _record(db_session, app) is None


@pytest.mark.asyncio
async def test_an_agency_application_without_an_agn011_deposit_takes_a_record_and_the_agency_is_told(db_session, world):  # CC4, CC5
    async with client_for(world["counselor"].email) as c:
        assert (await c.put(DEPOSIT.format(world["app"].id), json=PAID)).status_code == 200
    assert "Deposit updated" in [n.title for n in await notices(db_session, world["staff"]["user"])]


@pytest.mark.asyncio
async def test_on_hold_allows_a_deposit_but_a_closed_application_refuses_it(db_session, world):  # AC7
    app = world["direct_app"]
    item = await fresh(db_session, app)
    item.outcome = "on_hold"
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        assert (await c.put(DEPOSIT.format(app.id), json=PAID)).status_code == 200
    item.outcome = "rejected"
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        assert (await c.put(DEPOSIT.format(app.id), json={**PAID, "amount": "10"})).status_code == 409


@pytest.mark.asyncio
async def test_scope_readers_see_no_receipts_and_cannot_write(db_session, world):  # AC7
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.put(DEPOSIT.format(app.id), json=PAID)).status_code == 200
    async with client_for(world["direct_student"].email) as c:
        got = await c.get(DEPOSIT.format(app.id))
        assert got.status_code == 200 and got.json()["receipts"] == [] and got.json()["record"]["currency"] == "GBP"
        assert (await c.put(DEPOSIT.format(app.id), json=PAID)).status_code == 403
    for email in (world["counselor2"].email,):
        async with client_for(email) as c:
            assert (await c.get(DEPOSIT.format(app.id))).status_code == 403, email
            assert (await c.put(DEPOSIT.format(app.id), json=PAID)).status_code == 403, email
