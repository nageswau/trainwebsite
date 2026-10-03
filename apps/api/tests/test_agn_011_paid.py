"""AGN-011 -- a deposit becomes paid (spec §4.5, §4.6; AC2, AC5): exactly once through the signed webhook or verify, never from a
superseded checkout or a mismatched amount, and its receipt names the payer and the student."""

import hashlib
import hmac
from pathlib import Path

import pytest
import pytest_asyncio
from pdf_text import pdf_text
from sqlalchemy import select

from app.core.config import settings
from app.models import ApplicationDeposit, Payment, Receipt
from tests.agn001_helpers import client_for
from tests.agn008_helpers import APPS
from tests.agn011_helpers import KEY_SECRET, audits, captured, deposit_url, deposit_world, mk_deposit, mk_deposit_payment, razorpay_on, reload, signed

WEBHOOK = "/api/v1/payments/webhooks/razorpay"


@pytest_asyncio.fixture
async def world(db_session, monkeypatch):
    razorpay_on(monkeypatch)
    w = await deposit_world(db_session)
    deposit = await mk_deposit(db_session, w["app"], by=w["master"])
    payment = await mk_deposit_payment(db_session, deposit, w["staff"]["user"])
    return w | {"deposit": deposit, "payment": payment}


async def _deliver(client, order_id: str, amount_paise: int = 5_000_000, **kw):
    raw, headers = signed(captured(order_id, amount_paise, **kw))
    return await client.post(WEBHOOK, content=raw, headers=headers), raw, headers


def _receipt_text(receipt: Receipt) -> str:
    return pdf_text((Path(settings.local_upload_dir) / receipt.file_url.removeprefix("/local-files/")).read_bytes())


@pytest.mark.asyncio
async def test_a_signed_webhook_marks_payment_and_deposit_paid_once_with_a_receipt_naming_payer_and_student(db_session, client, world):
    r, raw, headers = await _deliver(client, world["payment"].checkout_provider_order_id)
    assert r.json() == {"received": True, "matched": True, "status": "paid"}
    deposit = await reload(db_session, ApplicationDeposit, world["deposit"].id)
    assert (deposit.status, deposit.paid_payment_id, deposit.active_payment_id) == ("paid", world["payment"].id, None) and deposit.paid_at is not None
    [audit] = await audits(db_session, "overseas.application.deposit_paid", world["app"].id)
    assert audit.user_id == world["staff"]["user"].id and audit.metadata_json == {"payment_id": str(world["payment"].id), "source": "webhook"}
    receipt = await db_session.scalar(select(Receipt).where(Receipt.payment_id == world["payment"].id))
    text = _receipt_text(receipt)
    assert f"Billed to: {world['staff']['user'].full_name}" in text and f"Student: {world['record'].full_name}" in text

    replay = await client.post(WEBHOOK, content=raw, headers=headers)
    assert replay.json()["status"] == "already_processed"
    again, _, _ = await _deliver(client, world["payment"].checkout_provider_order_id, event="order.paid")
    assert again.json()["status"] == "paid"
    assert len(await audits(db_session, "overseas.application.deposit_paid", world["app"].id)) == 1


@pytest.mark.asyncio
async def test_verify_marks_the_deposit_paid(db_session, world):
    order = world["payment"].checkout_provider_order_id
    signature = hmac.new(KEY_SECRET.encode(), f"{order}|pay_v1".encode(), hashlib.sha256).hexdigest()
    async with client_for(world["staff"]["user"].email) as c:
        r = await c.post(f"/api/v1/payments/{world['payment'].id}/verify", json={"razorpay_payment_id": "pay_v1", "razorpay_order_id": order, "razorpay_signature": signature})
        assert r.json()["status"] == "paid"
        detail = (await c.get(f"{APPS}/{world['app'].id}")).json()["application"]["deposit"]
    assert detail["status"] == "paid" and detail["paid_by"] == world["staff"]["user"].full_name and detail["receipt_available"] is True
    [audit] = await audits(db_session, "overseas.application.deposit_paid", world["app"].id)
    assert audit.metadata_json["source"] == "verify"


@pytest.mark.asyncio
async def test_a_superseded_checkout_paid_later_is_recorded_but_does_not_pay_the_deposit(db_session, client, world):
    async with client_for(world["master"].email) as c:
        assert (await c.put(deposit_url(world["app"].id), json={"required": True, "amount": "45000"})).status_code == 200
    r, _, _ = await _deliver(client, world["payment"].checkout_provider_order_id)
    assert r.json()["status"] == "paid"
    assert (await reload(db_session, Payment, world["payment"].id)).status == "paid"
    assert (await reload(db_session, ApplicationDeposit, world["deposit"].id)).status == "pending"
    [unlinked] = await audits(db_session, "overseas.deposit.unlinked_payment", world["deposit"].id)
    assert unlinked.metadata_json == {"payment_id": str(world["payment"].id), "reason": "not_the_open_checkout"}


@pytest.mark.asyncio
async def test_an_amount_mismatch_does_not_pay_the_deposit(db_session, client, world):
    r, _, _ = await _deliver(client, world["payment"].checkout_provider_order_id, amount_paise=100)
    assert r.json()["status"] == "paid"
    assert (await reload(db_session, ApplicationDeposit, world["deposit"].id)).status == "pending"
    [unlinked] = await audits(db_session, "overseas.deposit.unlinked_payment", world["deposit"].id)
    assert unlinked.metadata_json["reason"] == "amount_mismatch"


@pytest.mark.asyncio
async def test_receipt_route_is_scoped_and_needs_a_paid_deposit(db_session, client, world):
    url = f"{APPS}/{world['app'].id}/deposit/receipt"
    async with client_for(world["master"].email) as c:
        unpaid = await c.get(url)
    assert unpaid.status_code == 404 and unpaid.json()["detail"] == "Receipt not available"
    await _deliver(client, world["payment"].checkout_provider_order_id)
    async with client_for(world["master"].email) as c:
        ok = await c.get(url)
    assert ok.status_code == 200 and ok.json()["url"]
    for email in (world["other"]["master"].email, world["other_staff"]["user"].email):
        async with client_for(email) as c:
            assert (await c.get(url)).status_code == 404
