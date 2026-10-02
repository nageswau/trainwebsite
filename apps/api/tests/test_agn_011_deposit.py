"""AGN-011 -- the agency sets the deposit (spec §4.2, §4.3): scope, closed applications, paid lock, no-op retries, a superseded checkout,
and the detail's `deposit` / `payment_available`."""

from decimal import Decimal

import pytest
import pytest_asyncio

from app.models import ApplicationDeposit, Payment
from tests.agn001_helpers import client_for
from tests.agn008_helpers import APPS, mk_application
from tests.agn011_helpers import audits, deposit_url, deposit_world, mk_deposit, mk_deposit_payment, razorpay_off, razorpay_on, reload

BODY = {"required": True, "amount": "50000.00", "due_date": "2026-12-01"}


@pytest_asyncio.fixture
async def world(db_session):
    return await deposit_world(db_session)


@pytest.mark.asyncio
async def test_detail_has_no_deposit_until_one_is_set_and_reports_payment_availability(world, monkeypatch):
    razorpay_off(monkeypatch)
    async with client_for(world["master"].email) as c:
        body = (await c.get(f"{APPS}/{world['app'].id}")).json()["application"]
        assert body["deposit"] is None and body["payment_available"] is False
        razorpay_on(monkeypatch)
        assert (await c.get(f"{APPS}/{world['app'].id}")).json()["application"]["payment_available"] is True


@pytest.mark.asyncio
async def test_master_records_a_deposit_with_one_audit_row_and_no_amount_in_it(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await c.put(deposit_url(world["app"].id), json=BODY)
    assert r.status_code == 200, r.text
    deposit = r.json()["application"]["deposit"]
    assert {k: deposit[k] for k in ("required", "amount", "currency", "due_date", "status", "paid_at", "receipt_available", "checkout_in_progress")} == {
        "required": True,
        "amount": "50000.00",
        "currency": "INR",
        "due_date": "2026-12-01",
        "status": "pending",
        "paid_at": None,
        "receipt_available": False,
        "checkout_in_progress": False,
    }
    assert "active_payment_id" not in deposit and "paid_payment_id" not in deposit
    [audit] = await audits(db_session, "overseas.application.deposit", world["app"].id)
    assert audit.user_id == world["master"].id and audit.metadata_json["required"] is True
    assert "50000" not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_assigned_staff_updates_and_an_identical_save_writes_nothing(db_session, world):
    await mk_deposit(db_session, world["app"], by=world["master"])
    async with client_for(world["staff"]["user"].email) as c:
        r = await c.put(deposit_url(world["app"].id), json={"required": True, "amount": "60000", "due_date": None})
        assert r.status_code == 200, r.text
        assert r.json()["application"]["deposit"]["amount"] == "60000.00"
        again = await c.put(deposit_url(world["app"].id), json={"required": True, "amount": "60000.00"})
        assert again.status_code == 200
    assert len(await audits(db_session, "overseas.application.deposit", world["app"].id)) == 1


@pytest.mark.asyncio
async def test_not_required_clears_amount_and_due_date(db_session, world):
    deposit = await mk_deposit(db_session, world["app"], by=world["master"])
    async with client_for(world["master"].email) as c:
        r = await c.put(deposit_url(world["app"].id), json={"required": False})
    assert r.status_code == 200, r.text
    row = await reload(db_session, ApplicationDeposit, deposit.id)
    assert (row.status, row.amount, row.due_date) == ("not_required", None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["other_master", "other_staff"])
async def test_out_of_scope_callers_get_404_and_nothing_is_written(db_session, world, who):
    email = world["other"]["master"].email if who == "other_master" else world["other_staff"]["user"].email
    async with client_for(email) as c:
        r = await c.put(deposit_url(world["app"].id), json=BODY)
    assert r.status_code == 404
    assert await audits(db_session, "overseas.application.deposit", world["app"].id) == []


@pytest.mark.asyncio
async def test_withdrawn_application_and_archived_student_are_409(db_session, world):
    withdrawn = await mk_application(db_session, agent=world["master"], university=world["university"], record=world["record"], status="withdrawn", intake="Spring 2028")
    async with client_for(world["master"].email) as c:
        assert (await c.put(deposit_url(withdrawn.id), json=BODY)).status_code == 409
        world["record"].status = "archived"
        await db_session.commit()
        r = await c.put(deposit_url(world["app"].id), json=BODY)
    assert r.status_code == 409 and r.json()["detail"] == "Unarchive this student first"


@pytest.mark.asyncio
async def test_a_paid_deposit_cannot_be_changed(db_session, world):
    deposit = await mk_deposit(db_session, world["app"], by=world["master"])
    payment = await mk_deposit_payment(db_session, deposit, world["master"], status="paid", active=False)
    from datetime import UTC, datetime

    deposit.status, deposit.paid_payment_id, deposit.paid_at = "paid", payment.id, datetime.now(UTC)
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await c.put(deposit_url(world["app"].id), json={"required": True, "amount": "1"})
    assert r.status_code == 409 and r.json()["detail"] == "This deposit is already paid and can no longer be changed"
    assert (await reload(db_session, ApplicationDeposit, deposit.id)).amount == Decimal("50000.00")


@pytest.mark.asyncio
async def test_changing_the_amount_cancels_the_open_checkout(db_session, world):
    deposit = await mk_deposit(db_session, world["app"], by=world["master"])
    payment = await mk_deposit_payment(db_session, deposit, world["staff"]["user"])
    async with client_for(world["master"].email) as c:
        r = await c.put(deposit_url(world["app"].id), json={"required": True, "amount": "45000"})
    assert r.status_code == 200, r.text
    assert (await reload(db_session, Payment, payment.id)).status == "cancelled"
    assert (await reload(db_session, ApplicationDeposit, deposit.id)).active_payment_id is None


@pytest.mark.asyncio
async def test_changing_only_the_due_date_keeps_the_open_checkout(db_session, world):
    deposit = await mk_deposit(db_session, world["app"], by=world["master"])
    payment = await mk_deposit_payment(db_session, deposit, world["master"])
    async with client_for(world["master"].email) as c:
        r = await c.put(deposit_url(world["app"].id), json={"required": True, "amount": "50000", "due_date": "2027-01-15"})
    assert r.status_code == 200, r.text
    assert r.json()["application"]["deposit"]["checkout_in_progress"] is True
    assert (await reload(db_session, Payment, payment.id)).status == "pending"
