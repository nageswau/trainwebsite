"""upc-019 -- the commission ledger API (spec §3; AC1-AC3, P1, N1; CL9-CL14): read Expected / Received / Outstanding, record and remove
receipts. Restricted to the commission roles (U2); recording to the head and super_admin (Q-20)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, UniversityCommissionReceipt
from app.services.bdm_travel import india_today
from tests.agn003_helpers import mk_university
from tests.upc001_helpers import as_role, make_head
from tests.upc003_helpers import login, make_pm
from tests.upc019_helpers import agreement, enrolled, staff, term, tuition_course


def ledger_url(university_id, tail: str = "") -> str:
    return f"/api/v1/partnership/universities/{university_id}/commission{tail}"


def receipt_body(**over) -> dict:
    """P1: a lump-sum receipt for the January intake."""
    return {"amount": "2700.00", "currency": "GBP", "received_on": india_today().isoformat(), "reference": f"REM-{uuid.uuid4().hex[:8]}", "note": "Jan 2026 intake"} | over


async def _ledger(db):
    """A university with one enrolled application counted at 15% of GBP 18,000 (AC1)."""
    uni, by = await mk_university(db), await staff(db)
    c = await tuition_course(db, uni)
    a = await agreement(db, uni, by)
    await term(db, a, by)
    counted = await enrolled(db, uni, c)
    return uni, counted


@pytest.mark.asyncio
async def test_ac1_ac2_head_reads_expected_and_a_receipt_reduces_outstanding(client, db_session):
    uni, app = await _ledger(db_session)
    head = await make_head(db_session)
    await login(client, head)
    before = (await client.get(ledger_url(uni.id))).json()
    assert before["totals"] == [{"currency": "GBP", "expected": "2700.00", "received": "0.00", "outstanding": "2700.00"}]
    assert before["applications_total"] == 1 and before["receipts"] == [] and before["permissions"] == {"can_record": True}
    row = before["applications"][0]
    assert row["id"] == str(app.id) and row["status"] == "counted" and row["status_label"] == "Counted" and row["amount"] == "2700.00"
    assert row["currency"] == "GBP" and row["course"] == "MSc Data Science" and row["enrolled_on"] == "2026-01-15"
    assert before["university"]["id"] == str(uni.id)
    response = await client.post(ledger_url(uni.id, "/receipts"), json=receipt_body(amount="1000.50", application_ids=[str(app.id)]))
    assert response.status_code == 201, response.text
    receipt = response.json()["receipt"]
    assert receipt["amount"] == "1000.50" and receipt["currency"] == "GBP" and receipt["application_ids"] == [str(app.id)]
    assert receipt["note"] == "Jan 2026 intake" and receipt["created_by"]["id"] == str(head.id)
    after = (await client.get(ledger_url(uni.id))).json()
    assert after["totals"] == [{"currency": "GBP", "expected": "2700.00", "received": "1000.50", "outstanding": "1699.50"}]
    assert [r["id"] for r in after["receipts"]] == [receipt["id"]] and after["receipts_total"] == 1


@pytest.mark.asyncio
async def test_a_receipt_in_another_currency_gets_its_own_line_and_overpayment_shows_negative(client, db_session):
    uni, _ = await _ledger(db_session)
    await login(client, await make_head(db_session))
    assert (await client.post(ledger_url(uni.id, "/receipts"), json=receipt_body(amount="500", currency="USD"))).status_code == 201
    assert (await client.post(ledger_url(uni.id, "/receipts"), json=receipt_body(amount="3000"))).status_code == 201
    totals = (await client.get(ledger_url(uni.id))).json()["totals"]
    assert totals == [
        {"currency": "GBP", "expected": "2700.00", "received": "3000.00", "outstanding": "-300.00"},
        {"currency": "USD", "expected": "0.00", "received": "500.00", "outstanding": "-500.00"},
    ]


@pytest.mark.asyncio
async def test_n1_invalid_receipts_are_422(client, db_session):
    uni, app = await _ledger(db_session)
    other_uni, other_app = await _ledger(db_session)
    pending = await enrolled(db_session, uni, None, at=None, status="visa_documentation")
    await login(client, await make_head(db_session))
    post = lambda **over: client.post(ledger_url(uni.id, "/receipts"), json=receipt_body(**over))  # noqa: E731
    assert (await post(amount="-10")).status_code == 422  # the backlog's negative scenario
    assert (await post(amount="0")).status_code == 422
    assert (await post(amount="10.001")).status_code == 422
    assert (await post(amount="100000000")).status_code == 422
    assert (await post(currency="AED")).status_code == 422
    assert (await post(received_on=(india_today() + timedelta(days=1)).isoformat())).status_code == 422  # not in the future
    assert (await post(reference="  ")).status_code == 422
    assert (await post(reference="x" * 121)).status_code == 422
    assert (await post(note="x" * 501)).status_code == 422
    assert (await post(application_ids=[str(other_app.id)])).status_code == 422  # another university's application
    assert (await post(application_ids=[str(pending.id)])).status_code == 422  # not enrolled
    assert (await post(surprise=1)).status_code == 422
    repeated = await post(application_ids=[str(app.id), str(app.id)])  # a repeated pick is one pick (the schemas' idiom)
    assert repeated.status_code == 201 and repeated.json()["receipt"]["application_ids"] == [str(app.id)]
    assert (await client.post(ledger_url(uuid.uuid4(), "/receipts"), json=receipt_body())).status_code == 404
    assert (await client.get(ledger_url(uuid.uuid4()))).status_code == 404
    assert other_uni.id != uni.id


@pytest.mark.asyncio
async def test_the_same_reference_twice_is_409_in_any_case_but_fine_for_another_university(client, db_session):
    uni, _ = await _ledger(db_session)
    other, _ = await _ledger(db_session)
    await login(client, await make_head(db_session))
    assert (await client.post(ledger_url(uni.id, "/receipts"), json=receipt_body(reference="SWIFT-JAN-26"))).status_code == 201
    duplicate = await client.post(ledger_url(uni.id, "/receipts"), json=receipt_body(reference=" swift-jan-26 "))
    assert duplicate.status_code == 409, duplicate.text
    assert (await client.post(ledger_url(other.id, "/receipts"), json=receipt_body(reference="SWIFT-JAN-26"))).status_code == 201


@pytest.mark.asyncio
async def test_removing_a_receipt_restores_outstanding_and_both_writes_are_audited_without_money(client, db_session):
    uni, _ = await _ledger(db_session)
    await login(client, await make_head(db_session))
    receipt = (await client.post(ledger_url(uni.id, "/receipts"), json=receipt_body(amount="1234.56", reference="AUDIT-REF-77", note="secret"))).json()["receipt"]
    assert (await client.delete(ledger_url(uni.id, f"/receipts/{receipt['id']}"))).status_code == 204
    assert (await client.delete(ledger_url(uni.id, f"/receipts/{receipt['id']}"))).status_code == 404
    assert (await client.get(ledger_url(uni.id))).json()["totals"][0]["received"] == "0.00"
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == receipt["id"]).order_by(AuditLog.created_at))).all()
    assert [r.action for r in audit] == ["university_commission_receipt.create", "university_commission_receipt.delete"]
    text = str([r.metadata_json for r in audit])
    assert "1234" not in text and "AUDIT-REF-77" not in text and "secret" not in text and "GBP" in text
    assert await db_session.get(UniversityCommissionReceipt, uuid.UUID(receipt["id"])) is None


@pytest.mark.asyncio
async def test_cl9_manager_reads_but_cannot_record_and_super_admin_records(client, db_session):
    uni, _ = await _ledger(db_session)
    pm = await make_pm(db_session, await make_head(db_session))
    await login(client, pm)
    read = await client.get(ledger_url(uni.id))
    assert read.status_code == 200 and read.json()["permissions"] == {"can_record": False}
    assert (await client.post(ledger_url(uni.id, "/receipts"), json=receipt_body())).status_code == 403
    await as_role(client, db_session, "super_admin", "global")
    receipt = await client.post(ledger_url(uni.id, "/receipts"), json=receipt_body())
    assert receipt.status_code == 201
    await login(client, pm)
    assert (await client.delete(ledger_url(uni.id, f"/receipts/{receipt.json()['receipt']['id']}"))).status_code == 403


@pytest.mark.asyncio
async def test_ac3_no_other_role_sees_or_writes_any_of_it(client, db_session):
    uni, _ = await _ledger(db_session)
    await login(client, await make_head(db_session))
    rid = (await client.post(ledger_url(uni.id, "/receipts"), json=receipt_body())).json()["receipt"]["id"]
    for role, division in (("overseas_admin", "overseas"), ("counselor", "overseas"), ("bdm", "overseas"), ("agent", "overseas"), ("university_rep", "overseas"), ("overseas_student", "overseas")):
        await as_role(client, db_session, role, division)
        assert (await client.get(ledger_url(uni.id))).status_code == 403, role
        assert (await client.post(ledger_url(uni.id, "/receipts"), json=receipt_body())).status_code == 403, role
        assert (await client.delete(ledger_url(uni.id, f"/receipts/{rid}"))).status_code == 403, role
    client.cookies.clear()
    assert (await client.get(ledger_url(uni.id))).status_code == 401
    assert (await client.post(ledger_url(uni.id, "/receipts"), json=receipt_body())).status_code == 401
