"""AGN-011 -- Overseas Admin's Agent deposits (spec §4.7; AC4, D3, D5): the list, recording remittance and the one refund, and that no
other role can record either."""

from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio

from app.models import ApplicationDeposit
from tests.agn001_helpers import client_for, mk_user
from tests.agn011_helpers import audits, deposit_world, mk_deposit, mk_deposit_payment, reload

ADMIN = "/api/v1/overseas-admin/deposits"


async def _paid(db, w, *, paid_days_ago: int = 3) -> ApplicationDeposit:
    deposit = await mk_deposit(db, w["app"], by=w["master"])
    payment = await mk_deposit_payment(db, deposit, w["staff"]["user"], status="paid", active=False)
    deposit.status, deposit.paid_payment_id, deposit.paid_at = "paid", payment.id, datetime.now(UTC) - timedelta(days=paid_days_ago)
    await db.commit()
    return deposit


@pytest_asyncio.fixture
async def world(db_session):
    w = await deposit_world(db_session)
    return w | {"deposit": await _paid(db_session, w), "admin": await mk_user(db_session, role="overseas_admin")}


def _remit(**kw) -> dict:
    return {"remitted_on": date.today().isoformat(), "reference": "UTR 99812"} | kw


def _refund(**kw) -> dict:
    return {"refunded_on": date.today().isoformat(), "amount": "20000", "reason": "Visa refused"} | kw


@pytest.mark.asyncio
async def test_the_list_shows_the_deposit_with_its_agency_student_and_unlinked_count(db_session, world):
    await mk_deposit_payment(db_session, world["deposit"], world["master"], status="paid", active=False)  # a second, unlinked capture
    async with client_for(world["admin"].email) as c:
        body = (await c.get(ADMIN, params={"status": "paid", "limit": 100})).json()
        assert {"items", "total", "limit", "offset"} <= body.keys()
        [row] = [i for i in body["items"] if i["id"] == str(world["deposit"].id)]
        assert (row["agency"], row["student"], row["university"]) == (world["org"].name, world["record"].full_name, world["university"].name)
        assert (row["amount"], row["currency"], row["status"], row["paid_by"], row["unlinked_paid_payments"]) == ("50000.00", "INR", "paid", world["staff"]["user"].full_name, 1)
        remitted = (await c.get(ADMIN, params={"status": "remitted", "limit": 100})).json()["items"]
        assert str(world["deposit"].id) not in [i["id"] for i in remitted]
        page = (await c.get(ADMIN, params={"limit": 1})).json()
        assert len(page["items"]) == 1 and page["total"] >= 1


@pytest.mark.asyncio
async def test_super_admin_reads_the_list_and_agents_cannot(db_session, world):
    async with client_for((await mk_user(db_session, role="super_admin")).email) as c:
        assert (await c.get(ADMIN)).status_code == 200
    async with client_for(world["master"].email) as c:
        assert (await c.get(ADMIN)).status_code == 403


@pytest.mark.asyncio
async def test_overseas_admin_records_remittance_then_a_refund(db_session, world):
    async with client_for(world["admin"].email) as c:
        r = await c.post(f"{ADMIN}/{world['deposit'].id}/remit", json=_remit())
        assert r.status_code == 200, r.text
        assert (r.json()["status"], r.json()["remittance_reference"]) == ("remitted", "UTR 99812")
        again = await c.post(f"{ADMIN}/{world['deposit'].id}/remit", json=_remit())
        assert again.status_code == 409
        refund = await c.post(f"{ADMIN}/{world['deposit'].id}/refund", json=_refund())
        assert refund.status_code == 200, refund.text
        assert (refund.json()["status"], refund.json()["refund_amount"]) == ("refunded", "20000.00")
        assert (await c.post(f"{ADMIN}/{world['deposit'].id}/refund", json=_refund())).status_code == 409
    [remit] = await audits(db_session, "overseas.deposit.remit", world["deposit"].id)
    [refunded] = await audits(db_session, "overseas.deposit.refund", world["deposit"].id)
    assert remit.user_id == refunded.user_id == world["admin"].id
    assert refunded.metadata_json == {"amount": "20000.00", "from_status": "remitted"}


@pytest.mark.asyncio
async def test_a_refund_cannot_exceed_the_paid_amount(db_session, world):
    async with client_for(world["admin"].email) as c:
        r = await c.post(f"{ADMIN}/{world['deposit'].id}/refund", json=_refund(amount="50000.01"))
    assert r.status_code == 422 and r.json()["detail"] == "A refund cannot exceed the paid amount"
    assert (await reload(db_session, ApplicationDeposit, world["deposit"].id)).status == "paid"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "body", "message"),
    [
        ("remit", _remit(remitted_on=(date.today() + timedelta(days=1)).isoformat()), "The date cannot be in the future"),
        ("remit", _remit(remitted_on=(date.today() - timedelta(days=10)).isoformat()), "The date cannot be before the deposit was paid"),
        ("refund", _refund(refunded_on=(date.today() - timedelta(days=10)).isoformat()), "The date cannot be before the deposit was paid"),
    ],
)
async def test_dates_must_fall_between_payment_and_today(world, path, body, message):
    async with client_for(world["admin"].email) as c:
        r = await c.post(f"{ADMIN}/{world['deposit'].id}/{path}", json=body)
    assert r.status_code == 422 and r.json()["detail"] == message


@pytest.mark.asyncio
async def test_an_unpaid_deposit_cannot_be_remitted_or_refunded(db_session, world):
    other = await deposit_world(db_session)
    pending = await mk_deposit(db_session, other["app"], by=other["master"])
    async with client_for(world["admin"].email) as c:
        assert (await c.post(f"{ADMIN}/{pending.id}/remit", json=_remit())).status_code == 409
        assert (await c.post(f"{ADMIN}/{pending.id}/refund", json=_refund())).status_code == 409
        assert (await c.post(f"{ADMIN}/{other['app'].id}/remit", json=_remit())).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["master", "staff", "super_admin"])
async def test_only_overseas_admin_records_remittance_and_refunds(db_session, world, who):
    email = {"master": world["master"].email, "staff": world["staff"]["user"].email}.get(who) or (await mk_user(db_session, role="super_admin")).email
    async with client_for(email) as c:
        for path, body in (("remit", _remit()), ("refund", _refund())):
            r = await c.post(f"{ADMIN}/{world['deposit'].id}/{path}", json=body)
            assert r.status_code == 403 and r.json()["detail"] == "Only an Overseas Admin can record remittances and refunds"
    assert (await reload(db_session, ApplicationDeposit, world["deposit"].id)).status == "paid"
