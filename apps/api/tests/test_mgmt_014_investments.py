"""mgmt-014 -- the investment register: `services/investments.py` and /management/investments (spec MI1-MI14; AC1, AC2)."""

import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.services import investments
from tests.bdm001_helpers import login, make_user

URL = "/api/v1/management/investments"


def a_day() -> date:
    """A day no other test uses, so a date filter isolates this test's rows in the shared, never-truncated database."""
    return date(1990, 1, 1) + timedelta(days=random.randrange(0, 12_000))


def body(day: date, **overrides) -> dict:
    payload = {
        "invested_on": day.isoformat(),
        "investor_kind": "company",
        "amount": "500000",
        "purpose": "Marketing Campaign",
        "vertical": "shared",
        "expected_return": "1500000",
        "actual_return": None,
        "status": "active",
        "notes": None,
    }
    payload.update(overrides)
    return payload


async def partner_client(client, db_session, name: str | None = None):
    partner = await make_user(db_session, "partner", "global", name=name)
    await login(client, partner)
    return partner


async def create(client, payload: dict) -> dict:
    response = await client.post(URL, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def page(client, **params) -> dict:
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def audit_rows(db_session, entity_id: str) -> list[AuditLog]:
    return list((await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == entity_id).order_by(AuditLog.created_at))).all())


# --- ROI (MI7, Appendix B I1) -------------------------------------------------------------------------------------------------
def test_ac1_the_source_example_is_260_percent():
    assert investments.roi(Decimal("500000"), Decimal("1800000")) == Decimal("260.00")


def test_roi_is_unknown_without_an_actual_return_and_can_be_negative():
    assert investments.roi(Decimal("500000"), None) is None
    assert investments.roi(Decimal("300"), Decimal("100")) == Decimal("-66.67")
    assert investments.roi(Decimal("300"), Decimal("0")) == Decimal("-100.00")


# --- create (MI1, MI2, MI4, MI11) ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_returns_the_investment_with_its_code_roi_and_creator(client, db_session):
    partner = await partner_client(client, db_session, name="Partner One")
    day = a_day()
    out = await create(client, body(day, actual_return="1800000", status="completed", notes="Diwali push\nPhase 1"))
    assert out["code"].startswith("INV-") and len(out["code"]) == 10
    assert (out["amount"], out["expected_return"], out["actual_return"], out["roi"]) == ("500000.00", "1500000.00", "1800000.00", "260.00")
    assert (out["invested_on"], out["status"], out["vertical"], out["investor_kind"], out["investor"]) == (day.isoformat(), "completed", "shared", "company", None)
    assert out["notes"] == "Diwali push\nPhase 1"
    assert out["created_by"] == {"id": str(partner.id), "full_name": "Partner One"} and out["updated_by"] == out["created_by"]


@pytest.mark.asyncio
async def test_create_writes_one_partner_only_audit_entry_with_the_values(client, db_session):
    partner = await partner_client(client, db_session)
    out = await create(client, body(a_day()))
    [row] = await audit_rows(db_session, out["id"])
    assert (row.user_id, row.action, row.entity_type) == (partner.id, "mgmt.investment.create", "mgmt.investment")
    fields = row.metadata_json["fields"]
    assert {"invested_on", "investor_kind", "amount", "purpose", "vertical", "expected_return", "status"} <= set(fields)
    assert "actual_return" not in fields and "notes" not in fields  # only the fields set
    assert row.metadata_json["values"]["amount"] == {"before": None, "after": "500000.00"}


@pytest.mark.asyncio
async def test_a_partner_can_be_the_investor(client, db_session):
    await partner_client(client, db_session)
    investor = await make_user(db_session, "partner", "global", name="Partner Two")
    out = await create(client, body(a_day(), investor_kind="partner", investor_user_id=str(investor.id)))
    assert out["investor_kind"] == "partner" and out["investor"] == {"id": str(investor.id), "full_name": "Partner Two"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"investor_kind": "partner"}, "Choose the partner who invested"),
        ({"amount": "0"}, "more than ₹0"),
        ({"amount": "12.345"}, "up to 2 decimals"),
        ({"amount": "abc"}, "up to 2 decimals"),
        ({"expected_return": "-1"}, "can't be negative"),
        ({"purpose": " "}, "Purpose is required"),
        ({"purpose": "x"}, "at least 2 characters"),
        ({"purpose": "a" * 201}, "200"),
        ({"vertical": "space"}, "vertical"),
        ({"status": "lost"}, "status"),
        ({"invested_on": "12-10-2026"}, "valid investment date"),
        ({"notes": "a" * 2001}, "2000"),
        ({"code": "INV-1"}, "Extra inputs"),
    ],
)
async def test_create_rejects_bad_input_with_a_worded_422(client, db_session, overrides, message):
    await partner_client(client, db_session)
    response = await client.post(URL, json=body(a_day(), **overrides))
    assert response.status_code == 422, response.text
    assert message.lower() in response.text.lower()


@pytest.mark.asyncio
async def test_the_investor_must_be_a_partner_and_active(client, db_session):
    await partner_client(client, db_session)
    accountant = await make_user(db_session, "accountant", "global")
    gone = await make_user(db_session, "partner", "global", active=False)
    for user_id in (accountant.id, gone.id, uuid.uuid4()):
        response = await client.post(URL, json=body(a_day(), investor_kind="partner", investor_user_id=str(user_id)))
        assert response.status_code == 422 and "active partner" in response.text, response.text
    response = await client.post(URL, json=body(a_day(), investor_kind="company", investor_user_id=str(accountant.id)))
    assert response.status_code == 422 and "company" in response.text.lower()


# --- the register (MI8, MI9) --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_register_totals_skip_cancelled_and_count_roi_only_where_actual_is_known(client, db_session):
    await partner_client(client, db_session)
    day = a_day()
    await create(client, body(day, amount="500000", actual_return="1800000", status="completed"))
    await create(client, body(day, amount="100000", actual_return="50000", status="completed"))
    await create(client, body(day, amount="200000"))  # no actual yet
    await create(client, body(day, amount="900000", actual_return="9000000", status="cancelled"))
    out = await page(client, date_from=day.isoformat(), date_to=day.isoformat())
    assert out["total"] == 4 and len(out["items"]) == 4
    assert out["totals"] == {"count": 3, "invested": "800000.00", "actual_return": "1850000.00", "roi": "208.33"}  # (1.85M - 0.6M) / 0.6M


@pytest.mark.asyncio
async def test_register_roi_total_is_unknown_when_no_actual_is_known(client, db_session):
    await partner_client(client, db_session)
    day = a_day()
    await create(client, body(day))
    out = await page(client, date_from=day.isoformat(), date_to=day.isoformat())
    assert out["totals"] == {"count": 1, "invested": "500000.00", "actual_return": "0.00", "roi": None}
    assert out["items"][0]["roi"] is None


@pytest.mark.asyncio
async def test_register_filters_pages_and_orders_newest_first(client, db_session):
    await partner_client(client, db_session)
    day = a_day()
    later = day + timedelta(days=1)
    first = await create(client, body(day, vertical="it"))
    second = await create(client, body(later, vertical="abroad", status="planned"))
    span = {"date_from": day.isoformat(), "date_to": later.isoformat()}
    assert [i["id"] for i in (await page(client, **span))["items"]] == [second["id"], first["id"]]
    assert [i["id"] for i in (await page(client, **span, vertical="it"))["items"]] == [first["id"]]
    assert [i["id"] for i in (await page(client, **span, status="planned"))["items"]] == [second["id"]]
    paged = await page(client, **span, limit=1, offset=1)
    assert (paged["total"], [i["id"] for i in paged["items"]], paged["limit"], paged["offset"]) == (2, [first["id"]], 1, 1)


@pytest.mark.asyncio
async def test_register_lists_the_active_partners_as_investor_choices(client, db_session):
    me = await partner_client(client, db_session, name="Zed Partner")
    gone = await make_user(db_session, "partner", "global", active=False)
    ids = {c["id"] for c in (await page(client, limit=1))["investors"]}
    assert str(me.id) in ids and str(gone.id) not in ids


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [{"vertical": "space"}, {"status": "lost"}, {"date_from": "2026-10-12", "date_to": "2026-10-11"}, {"limit": 0}, {"limit": 101}, {"offset": 10_001}],
)
async def test_register_rejects_bad_filters(client, db_session, params):
    await partner_client(client, db_session)
    assert (await client.get(URL, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_one_investment_and_unknown_id(client, db_session):
    await partner_client(client, db_session)
    out = await create(client, body(a_day()))
    response = await client.get(f"{URL}/{out['id']}")
    assert response.status_code == 200 and response.json() == out
    assert (await client.get(f"{URL}/{uuid.uuid4()}")).status_code == 404
    assert (await client.patch(f"{URL}/{uuid.uuid4()}", json={"status": "active"})).status_code == 404


# --- update (MI10, MI11) ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_changes_only_the_fields_sent_and_audits_before_and_after(client, db_session):
    await partner_client(client, db_session)
    out = await create(client, body(a_day()))
    editor = await partner_client(client, db_session, name="Partner Two")
    response = await client.patch(f"{URL}/{out['id']}", json={"actual_return": "1800000", "status": "completed", "purpose": "Marketing Campaign"})
    assert response.status_code == 200, response.text
    after = response.json()
    assert (after["actual_return"], after["status"], after["roi"], after["amount"]) == ("1800000.00", "completed", "260.00", "500000.00")
    assert after["updated_by"] == {"id": str(editor.id), "full_name": "Partner Two"} and after["created_by"] != after["updated_by"]
    create_row, update_row = await audit_rows(db_session, out["id"])
    assert (update_row.action, update_row.user_id) == ("mgmt.investment.update", editor.id)
    assert update_row.metadata_json["fields"] == ["actual_return", "status"]  # purpose was sent unchanged
    assert update_row.metadata_json["values"] == {"actual_return": {"before": None, "after": "1800000.00"}, "status": {"before": "active", "after": "completed"}}


@pytest.mark.asyncio
async def test_an_update_that_changes_nothing_writes_no_audit_entry(client, db_session):
    await partner_client(client, db_session)
    out = await create(client, body(a_day()))
    response = await client.patch(f"{URL}/{out['id']}", json={"status": "active", "amount": "500000.00"})
    assert response.status_code == 200 and response.json()["updated_by"] == out["created_by"]
    assert len(await audit_rows(db_session, out["id"])) == 1


@pytest.mark.asyncio
async def test_update_switches_the_investor_and_clears_returns(client, db_session):
    await partner_client(client, db_session)
    investor = await make_user(db_session, "partner", "global")
    out = await create(client, body(a_day(), actual_return="10"))
    assert (await client.patch(f"{URL}/{out['id']}", json={"investor_kind": "partner"})).status_code == 422  # no partner named
    changed = (await client.patch(f"{URL}/{out['id']}", json={"investor_kind": "partner", "investor_user_id": str(investor.id), "actual_return": None})).json()
    assert changed["investor"]["id"] == str(investor.id) and changed["actual_return"] is None and changed["roi"] is None
    back = (await client.patch(f"{URL}/{out['id']}", json={"investor_kind": "company"})).json()
    assert back["investor_kind"] == "company" and back["investor"] is None


@pytest.mark.asyncio
async def test_update_keeps_an_investor_who_has_since_left_but_refuses_choosing_one(client, db_session):
    await partner_client(client, db_session)
    investor = await make_user(db_session, "partner", "global")
    out = await create(client, body(a_day(), investor_kind="partner", investor_user_id=str(investor.id)))
    investor.active = False
    await db_session.commit()
    assert (await client.patch(f"{URL}/{out['id']}", json={"notes": "kept"})).status_code == 200
    again = await client.patch(f"{URL}/{out['id']}", json={"investor_user_id": str(investor.id)})
    assert again.status_code == 200  # unchanged, so not re-checked
    other = await make_user(db_session, "partner", "global", active=False)
    assert (await client.patch(f"{URL}/{out['id']}", json={"investor_user_id": str(other.id)})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"amount": None}, {"purpose": None}, {"status": None}, {"invested_on": None}, {"code": "INV-9"}])
async def test_update_refuses_clearing_a_required_field_or_an_unknown_one(client, db_session, payload):
    await partner_client(client, db_session)
    out = await create(client, body(a_day()))
    assert (await client.patch(f"{URL}/{out['id']}", json=payload)).status_code == 422


# --- access (MI12, M13, AC2 negative) -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "division", "message"),
    [
        ("accountant", "global", "Only partners"),
        ("super_admin", "global", "Only partners"),
        ("bdm_manager", "global", "Management access required"),
        ("it_admin", "it", "Management access required"),
    ],
)
async def test_everyone_but_a_partner_is_refused(client, db_session, role, division, message):
    await partner_client(client, db_session)
    out = await create(client, body(a_day()))
    await login(client, await make_user(db_session, role, division))
    for response in (
        await client.get(URL),
        await client.get(f"{URL}/{out['id']}"),
        await client.post(URL, json=body(a_day())),
        await client.patch(f"{URL}/{out['id']}", json={"status": "completed"}),
        await client.get(f"{URL}/{uuid.uuid4()}"),
    ):
        assert response.status_code == 403 and message in response.text, response.text


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(URL)).status_code == 401
    assert (await client.post(URL, json=body(a_day()))).status_code == 401
