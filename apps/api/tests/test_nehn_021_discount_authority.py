"""nehn-021 -- discount authority through the `discounts.add` grant (DEC-SCOPE-309; spec
docs/superpowers/specs/2026-10-28-nehn-021-discount-authority-design.md). A global-division grant holder (the accountant) works every
division's payments; division staff keep their own division; without the grant the route is 403; every discount is audited."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Payment, User
from tests.test_nehn_005_permissions import ADMIN_REQUIRED, API, _headers, _restored, _user

GRANT = {"permissions": ["payments.view", "discounts.add"]}


async def _payment(db, division: str, amount: float = 10000, status: str = "pending") -> Payment:
    student = User(email=f"n021-{uuid.uuid4().hex[:10]}@example.local", password_hash="!", full_name="N021 Student", role=f"{division}_student", division=division, active=True, email_verified=True)
    db.add(student)
    await db.flush()
    payment = Payment(user_id=student.id, division=division, reference_type="enrollment_fee", amount=amount, currency="INR", status=status)
    db.add(payment)
    await db.commit()
    return payment


def _discount(payment: Payment, amount: float = 9000, reason: str = "10% scholarship"):
    return f"{API}/admin/payments/{payment.id}/discount", {"amount": amount, "reason": reason}


@pytest.mark.asyncio
async def test_an_ungranted_accountant_is_refused(client, db_session):
    accountant = await _user(db_session, "accountant")
    payment = await _payment(db_session, "it")
    url, body = _discount(payment)
    async with _restored(db_session, "accountant"):
        response = await client.post(url, json=body, headers=_headers(accountant))
    assert response.status_code == 403 and response.json()["detail"] == ADMIN_REQUIRED
    await db_session.refresh(payment)
    assert float(payment.amount) == 10000


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["trainer", "placement_team", "counselor", "partner"])
async def test_roles_without_the_grant_get_403(client, db_session, role):
    caller = await _user(db_session, role)
    payment = await _payment(db_session, "it")
    url, body = _discount(payment)
    assert (await client.post(url, json=body, headers=_headers(caller))).status_code == 403


@pytest.mark.asyncio
async def test_a_granted_accountant_discounts_either_division_and_is_audited(client, db_session):
    root, accountant = await _user(db_session, "super_admin"), await _user(db_session, "accountant")
    it_fee, overseas_fee = await _payment(db_session, "it"), await _payment(db_session, "overseas", amount=50000)
    async with _restored(db_session, "accountant"):
        assert (await client.put(f"{API}/admin/roles/accountant/permissions", json=GRANT, headers=_headers(root))).status_code == 200

        listed = await client.get(f"{API}/admin/payments", headers=_headers(accountant))
        assert listed.status_code == 200
        ids = {row["id"] for row in listed.json()}
        assert {str(it_fee.id), str(overseas_fee.id)} <= ids

        for payment, amount in ((it_fee, 9000), (overseas_fee, 45000)):
            url, body = _discount(payment, amount=amount)
            response = await client.post(url, json=body, headers=_headers(accountant))
            assert response.status_code == 200, response.text
            assert response.json()["amount"] == amount

    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "payment.discount", AuditLog.user_id == accountant.id))).all()
    assert {row.entity_id for row in audits} == {str(it_fee.id), str(overseas_fee.id)}
    assert all(row.metadata_json["reason"] == "10% scholarship" for row in audits)


@pytest.mark.asyncio
async def test_a_granted_accountant_still_needs_a_reason_and_a_lower_amount(client, db_session):
    root, accountant = await _user(db_session, "super_admin"), await _user(db_session, "accountant")
    payment = await _payment(db_session, "overseas")
    async with _restored(db_session, "accountant"):
        await client.put(f"{API}/admin/roles/accountant/permissions", json=GRANT, headers=_headers(root))
        url, _ = _discount(payment)
        assert (await client.post(url, json={"amount": 9000, "reason": " "}, headers=_headers(accountant))).status_code == 422
        assert (await client.post(url, json={"amount": 12000, "reason": "x"}, headers=_headers(accountant))).status_code == 422


@pytest.mark.asyncio
async def test_division_admins_keep_their_own_division_only(client, db_session):
    it_admin, overseas_admin = await _user(db_session, "it_admin"), await _user(db_session, "overseas_admin")
    it_fee, overseas_fee = await _payment(db_session, "it"), await _payment(db_session, "overseas")
    for caller, own, other in ((it_admin, it_fee, overseas_fee), (overseas_admin, overseas_fee, it_fee)):
        url, body = _discount(other)
        refused = await client.post(url, json=body, headers=_headers(caller))
        assert refused.status_code == 403 and refused.json()["detail"] == "Wrong division"
        url, body = _discount(own)
        assert (await client.post(url, json=body, headers=_headers(caller))).status_code == 200
        listed = {row["division"] for row in (await client.get(f"{API}/admin/payments", headers=_headers(caller))).json()}
        assert listed == {caller.division}
