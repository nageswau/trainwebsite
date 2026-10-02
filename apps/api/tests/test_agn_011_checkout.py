"""AGN-011 -- the deposit checkout (spec §4.4; AC1, AC3, AC6): scope, the stored amount, Razorpay unconfigured, idempotent replay,
one active checkout, the hourly limit and a provider failure. Razorpay itself is never called (`fake_orders`)."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import ApplicationDeposit, Invoice, Payment
from tests.agn001_helpers import client_for
from tests.agn011_helpers import (
    KEY_ID,
    audits,
    checkout_url,
    count_deposit_payments,
    deposit_payments,
    deposit_world,
    fake_orders,
    mk_deposit,
    mk_deposit_payment,
    razorpay_off,
    razorpay_on,
    reload,
)


def key() -> dict:
    return {"Idempotency-Key": str(uuid.uuid4())}


@pytest_asyncio.fixture
async def world(db_session, monkeypatch):
    razorpay_on(monkeypatch)
    w = await deposit_world(db_session)
    return w | {"deposit": await mk_deposit(db_session, w["app"], by=w["master"]), "calls": fake_orders(monkeypatch)}


@pytest.mark.asyncio
async def test_unconfigured_razorpay_answers_configuration_required_and_writes_nothing(db_session, world, monkeypatch):
    razorpay_off(monkeypatch)
    async with client_for(world["master"].email) as c:
        r = await c.post(checkout_url(world["app"].id), headers=key())
    assert r.status_code == 200 and r.json() == {"status": "configuration_required"}
    assert await count_deposit_payments(db_session, world["deposit"].id) == 0
    assert world["calls"] == []


@pytest.mark.asyncio
async def test_checkout_uses_the_stored_amount_and_a_payer_owned_payment(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        r = await c.post(checkout_url(world["app"].id), headers=key(), json={"amount": 1, "currency": "USD"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready" and body["key_id"] == KEY_ID and body["amount"] == 50000.0 and body["currency"] == "INR"
    [payment] = await deposit_payments(db_session, world["deposit"].id)
    assert str(payment.id) == body["payment_id"] and payment.checkout_provider_order_id == body["provider_order_id"]
    assert (payment.user_id, payment.division, payment.amount, payment.currency, payment.status) == (world["staff"]["user"].id, "overseas", world["deposit"].amount, "INR", "pending")
    assert world["calls"] == [{"provider": "razorpay", "amount": 50000.0, "currency": "INR", "reference": f"PAY-{payment.id}"}]
    assert (await reload(db_session, ApplicationDeposit, world["deposit"].id)).active_payment_id == payment.id
    assert await db_session.scalar(select(Invoice.id).where(Invoice.payment_id == payment.id)) is not None
    assert len(await audits(db_session, "payment.checkout", payment.id)) == 1
    [audit] = await audits(db_session, "overseas.application.deposit_checkout", world["app"].id)
    assert audit.metadata_json == {"payment_id": str(payment.id)}


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["other_master", "other_staff"])
async def test_out_of_scope_checkout_is_404(db_session, world, who):
    email = world["other"]["master"].email if who == "other_master" else world["other_staff"]["user"].email
    async with client_for(email) as c:
        assert (await c.post(checkout_url(world["app"].id), headers=key())).status_code == 404
    assert world["calls"] == []


@pytest.mark.asyncio
async def test_the_same_key_replays_the_order_without_a_second_call(db_session, world):
    headers = key()
    async with client_for(world["master"].email) as c:
        first = (await c.post(checkout_url(world["app"].id), headers=headers)).json()
        again = await c.post(checkout_url(world["app"].id), headers=headers)
    assert again.status_code == 200
    assert again.json() == first | {"replayed": True}
    assert len(world["calls"]) == 1


@pytest.mark.asyncio
async def test_the_same_key_while_the_order_is_still_opening_is_409(db_session, world):
    headers = key()
    opening = await mk_deposit_payment(db_session, world["deposit"], world["master"], key=headers["Idempotency-Key"])
    opening.checkout_provider_order_id = None  # step 1 committed, the Razorpay call has not returned yet
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await c.post(checkout_url(world["app"].id), headers=headers)
    assert r.status_code == 409 and r.json()["detail"] == "A checkout is already being opened for this deposit"


@pytest.mark.asyncio
async def test_another_members_recent_checkout_blocks_then_expires(db_session, world):
    other = await mk_deposit_payment(db_session, world["deposit"], world["staff"]["user"])
    async with client_for(world["master"].email) as c:
        blocked = await c.post(checkout_url(world["app"].id), headers=key())
        assert blocked.status_code == 409 and blocked.json()["detail"] == "Another team member is paying this deposit -- try again in a few minutes"
        other.created_at = datetime.now(UTC) - timedelta(minutes=16)
        await db_session.commit()
        r = await c.post(checkout_url(world["app"].id), headers=key())
    assert r.status_code == 200, r.text
    assert (await reload(db_session, Payment, other.id)).status == "cancelled"


@pytest.mark.asyncio
async def test_the_same_payer_can_restart_an_abandoned_checkout_with_a_new_key(db_session, world):
    async with client_for(world["master"].email) as c:
        first = (await c.post(checkout_url(world["app"].id), headers=key())).json()
        second = await c.post(checkout_url(world["app"].id), headers=key())
    assert second.status_code == 200 and second.json()["payment_id"] != first["payment_id"]
    assert (await reload(db_session, Payment, uuid.UUID(first["payment_id"]))).status == "cancelled"


@pytest.mark.asyncio
async def test_a_paid_deposit_is_409(db_session, world):
    payment = await mk_deposit_payment(db_session, world["deposit"], world["master"], status="paid", active=False)
    deposit = world["deposit"]
    deposit.status, deposit.paid_payment_id, deposit.paid_at = "paid", payment.id, datetime.now(UTC)
    await db_session.commit()
    async with client_for(world["staff"]["user"].email) as c:
        r = await c.post(checkout_url(world["app"].id), headers=key())
    assert r.status_code == 409 and r.json()["detail"] == "This deposit is already paid"
    assert world["calls"] == []


@pytest.mark.asyncio
async def test_no_deposit_or_not_required_is_409(db_session, world):
    deposit = world["deposit"]
    deposit.required, deposit.status, deposit.amount = False, "not_required", None
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await c.post(checkout_url(world["app"].id), headers=key())
    assert r.status_code == 409 and r.json()["detail"] == "No deposit is required for this application"


@pytest.mark.asyncio
async def test_the_idempotency_key_is_required(world):
    async with client_for(world["master"].email) as c:
        assert (await c.post(checkout_url(world["app"].id))).status_code == 422
        assert (await c.post(checkout_url(world["app"].id), headers={"Idempotency-Key": "x" * 201})).status_code == 422


@pytest.mark.asyncio
async def test_more_than_ten_checkouts_an_hour_is_429(db_session, world):
    for _ in range(10):
        await mk_deposit_payment(db_session, world["deposit"], world["master"], status="cancelled", active=False)
    async with client_for(world["master"].email) as c:
        r = await c.post(checkout_url(world["app"].id), headers=key())
    assert r.status_code == 429 and 0 < int(r.headers["Retry-After"]) <= 3600
    assert world["calls"] == []


@pytest.mark.asyncio
async def test_a_provider_error_is_502_and_cancels_the_attempt(db_session, world, monkeypatch):
    from app.services.payment import payments

    async def broken(*args):
        raise httpx.ConnectError("razorpay down")

    monkeypatch.setattr(payments, "create_checkout", broken)
    async with client_for(world["master"].email) as c:
        r = await c.post(checkout_url(world["app"].id), headers=key())
    assert r.status_code == 502 and r.json()["detail"] == "The payment provider is unavailable -- nothing was charged. Try again shortly"
    [payment] = await deposit_payments(db_session, world["deposit"].id)
    assert payment.status == "cancelled"
    assert (await reload(db_session, ApplicationDeposit, world["deposit"].id)).active_payment_id is None
