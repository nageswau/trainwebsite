"""ccrm-050 (DEC-SCOPE-320): the agent-Master commission on the Add/Edit University form -- an optional `agent_commission` object on
POST / PATCH /partnership/universities, for super_admin / overseas_admin only (403 for anyone else, even null), one transaction, audited
with before/after like the dtu-001 PUT."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, University
from tests.agn001_helpers import client_for, mk_active_org
from tests.agn004_helpers import mk_staff
from tests.upc001_helpers import as_role, login
from tests.upc003_helpers import BASE, catalogue_country, create, payload
from tests.upc007_helpers import owned_university

PARTNERS = "/api/v1/workflows/overseas/agent/crm/partner-universities"
TEN = {"percent": "10", "note": "Standard agent rate"}


async def _audits(db, university_id) -> list[dict]:
    rows = await db.scalars(select(AuditLog).where(AuditLog.entity_id == str(university_id), AuditLog.action == "university.agent_commission").order_by(AuditLog.created_at))
    return [r.metadata_json for r in rows]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["overseas_admin", "super_admin"])
async def test_ac1_an_admin_creates_a_university_with_its_agent_commission(client, db_session, role):
    await as_role(client, db_session, role, "overseas")
    uni = await create(client, (await catalogue_country(db_session)).id, agent_commission=TEN)
    assert uni["agent_commission"] == {"percent": "10.00", "amount": None, "currency": None, "note": "Standard agent rate"}
    row = await db_session.get(University, uuid.UUID(uni["id"]), populate_existing=True)
    assert row.agent_commission_percent == 10 and row.agent_commission_note == "Standard agent rate"
    assert await _audits(db_session, uni["id"]) == [{"before": None, "after": uni["agent_commission"]}]
    create_audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == uni["id"], AuditLog.action == "university.create"))
    assert "agent_commission" not in create_audit.metadata_json["fields"]


@pytest.mark.asyncio
async def test_a_create_without_the_field_has_no_commission_and_no_commission_audit(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    country = (await catalogue_country(db_session)).id
    for extra in ({}, {"agent_commission": None}):
        uni = await create(client, country, **extra)
        assert uni["agent_commission"] is None
        assert await _audits(db_session, uni["id"]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [TEN, None])
async def test_ac2_a_partnership_head_creating_with_the_field_is_403_and_nothing_is_created(client, db_session, value):
    await as_role(client, db_session, "partnership_head", "global")
    body = payload((await catalogue_country(db_session)).id, agent_commission=value)
    r = await client.post(BASE, json=body)
    assert r.status_code == 403 and r.json()["detail"] == "Only a super admin or an overseas admin can change the agent commission"
    assert await db_session.scalar(select(func.count()).select_from(University).where(University.name == body["name"])) == 0
    without = await client.post(BASE, json={k: v for k, v in body.items() if k != "agent_commission"})
    assert without.status_code == 201 and "agent_commission" not in without.text


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [TEN, None])
async def test_ac2_the_assigned_manager_and_head_editing_with_the_field_are_403_and_nothing_changes(client, db_session, value):
    head, pm, uni = await owned_university(client, db_session)
    await as_role(client, db_session, "super_admin", "overseas")
    assert (await client.put(f"{BASE}/{uni['id']}/agent-commission", json={"percent": "16"})).status_code == 200
    for who in (pm, head):
        await login(client, who)
        r = await client.patch(f"{BASE}/{uni['id']}", json={"city": "Leeds", "agent_commission": value})
        assert r.status_code == 403, r.text
        assert "16.00" not in r.text
    row = await db_session.get(University, uuid.UUID(uni["id"]), populate_existing=True)
    assert row.agent_commission_percent == 16 and row.city != "Leeds"
    await login(client, pm)
    ok = await client.patch(f"{BASE}/{uni['id']}", json={"city": "Leeds"})
    assert ok.status_code == 200 and "agent_commission" not in ok.text


@pytest.mark.asyncio
async def test_an_admin_edit_sets_keeps_and_clears_the_commission(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    uni = await create(client, (await catalogue_country(db_session)).id)
    url = f"{BASE}/{uni['id']}"
    r = await client.patch(url, json={"agent_commission": {"amount": "4000", "currency": "GBP"}})
    assert r.status_code == 200, r.text
    assert r.json()["university"]["agent_commission"] == {"percent": None, "amount": "4000.00", "currency": "GBP", "note": None}
    assert (await client.patch(url, json={"agent_commission": {"amount": "4000.00", "currency": "GBP"}})).status_code == 200  # unchanged
    assert (await client.patch(url, json={"city": "Bath"})).json()["university"]["agent_commission"]["amount"] == "4000.00"  # omitted
    cleared = await client.patch(url, json={"agent_commission": None})
    assert cleared.status_code == 200 and cleared.json()["university"]["agent_commission"] is None
    after = {"percent": None, "amount": "4000.00", "currency": "GBP", "note": None}
    assert await _audits(db_session, uni["id"]) == [{"before": None, "after": after}, {"before": after, "after": None}]


@pytest.mark.asyncio
async def test_the_rate_is_validated_like_the_card(client, db_session):
    await as_role(client, db_session, "super_admin", "overseas")
    country = (await catalogue_country(db_session)).id
    for bad in ({"percent": "10", "amount": "100", "currency": "GBP"}, {"amount": "100"}, {"percent": "0"}, {"percent": "100.01"}, {"percent": "5", "extra": 1}):
        r = await client.post(BASE, json=payload(country, agent_commission=bad))
        assert r.status_code == 422, bad
        assert r.json()["detail"][0]["loc"][:2] == ["body", "agent_commission"]
    uni = await create(client, country)
    assert (await client.patch(f"{BASE}/{uni['id']}", json={"agent_commission": {"percent": "10", "amount": "1", "currency": "GBP"}})).status_code == 422


@pytest.mark.asyncio
async def test_an_inactive_university_keeps_the_409(client, db_session):
    await as_role(client, db_session, "super_admin", "overseas")
    uni = await create(client, (await catalogue_country(db_session)).id)
    assert (await client.post(f"{BASE}/{uni['id']}/deactivate", json={"confirm": True})).status_code == 200
    assert (await client.patch(f"{BASE}/{uni['id']}", json={"agent_commission": TEN})).status_code == 409
    row = await db_session.get(University, uuid.UUID(uni["id"]), populate_existing=True)
    assert row.agent_commission_percent is None


@pytest.mark.asyncio
async def test_an_overseas_admin_outside_overseas_is_refused(client, db_session):
    await as_role(client, db_session, "overseas_admin", "it")
    r = await client.post(BASE, json=payload((await catalogue_country(db_session)).id, agent_commission=TEN))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_ac3_ac4_the_master_sees_the_form_rate_after_publish_and_staff_never_do(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    uni = await create(client, (await catalogue_country(db_session)).id, overview="An overview.", agent_commission=TEN)
    org = await mk_active_org(db_session)
    staff = await mk_staff(db_session, org["org"])
    await db_session.commit()
    async with client_for(org["master"].email) as master:
        assert (await master.get(f"{PARTNERS}/{uni['id']}")).status_code == 404  # internal until published
    assert (await client.post(f"{BASE}/{uni['id']}/publish")).status_code == 200
    async with client_for(org["master"].email) as master:
        assert (await master.get(f"{PARTNERS}/{uni['id']}")).json()["university"]["agent_commission"]["percent"] == "10.00"
    async with client_for(staff["user"].email) as s:
        r = await s.get(f"{PARTNERS}/{uni['id']}")
        assert r.status_code == 200 and "agent_commission" not in r.text
