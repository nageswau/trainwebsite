"""AGN-011 -- two members paying the same deposit at once (spec §4.4, D8): the deposit row lock lets one order through; the other gets
the 15-minute 409. No deadlock with the deposit PUT running alongside."""

import asyncio
import uuid

import pytest

from tests.agn001_helpers import client_for
from tests.agn011_helpers import checkout_url, count_deposit_payments, deposit_url, deposit_world, fake_orders, mk_deposit, razorpay_on


@pytest.mark.asyncio
async def test_two_members_paying_at_once_open_one_order(db_session, monkeypatch):
    razorpay_on(monkeypatch)
    calls = fake_orders(monkeypatch)
    w = await deposit_world(db_session)
    deposit = await mk_deposit(db_session, w["app"], by=w["master"])
    async with client_for(w["master"].email) as master, client_for(w["staff"]["user"].email) as staff:
        results = await asyncio.gather(
            master.post(checkout_url(w["app"].id), headers={"Idempotency-Key": str(uuid.uuid4())}),
            staff.post(checkout_url(w["app"].id), headers={"Idempotency-Key": str(uuid.uuid4())}),
        )
    assert sorted(r.status_code for r in results) == [200, 409]
    assert len(calls) == 1
    assert await count_deposit_payments(db_session, deposit.id) == 1


@pytest.mark.asyncio
async def test_checkout_and_an_amount_change_at_once_both_finish(db_session, monkeypatch):
    razorpay_on(monkeypatch)
    fake_orders(monkeypatch)
    w = await deposit_world(db_session)
    await mk_deposit(db_session, w["app"], by=w["master"])
    async with client_for(w["master"].email) as master, client_for(w["staff"]["user"].email) as staff:
        results = await asyncio.wait_for(
            asyncio.gather(
                staff.post(checkout_url(w["app"].id), headers={"Idempotency-Key": str(uuid.uuid4())}),
                master.put(deposit_url(w["app"].id), json={"required": True, "amount": "40000"}),
            ),
            timeout=20,
        )
    assert [r.status_code for r in results][1] == 200
    assert results[0].status_code in (200, 409)
