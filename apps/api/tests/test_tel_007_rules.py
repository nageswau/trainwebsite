"""tel-007 -- the distribution-rule routes (spec §5; DI3, D6; backlog negative: a rule pointing at another team's telecaller -> 422)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, TelDistributionRule
from tests.tel007_helpers import RULES, city, login, make_telecaller, make_tl_manager, make_user, product, rule


async def _signed_in_manager(client, db):
    manager = await make_tl_manager(db)
    await login(client, manager)
    return manager


def _city_body(tel, town=None, *, team="it", **extra):
    return {"team": team, "kind": "city", "city": town or city(), "telecaller_user_id": str(tel.id), **extra}


async def _mine(client, tel):
    response = await client.get(RULES, params={"telecaller_user_id": str(tel.id)})
    assert response.status_code == 200, response.text
    return response.json()


# --- roles ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_signed_out_is_401_and_other_roles_403(client, db_session):
    assert (await client.get(RULES)).status_code == 401
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    for role, division in (("telecaller", "it"), ("it_admin", "it"), ("counselor", "overseas")):
        await login(client, tel if role == "telecaller" else await make_user(db_session, role, division))
        assert (await client.get(RULES)).status_code == 403
        assert (await client.post(RULES, json=_city_body(tel))).status_code == 403


# --- create -------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_manager_creates_a_city_rule_for_a_report(client, db_session):
    manager = await _signed_in_manager(client, db_session)
    tel = await make_telecaller(db_session, manager)
    town = f"  {city()} "
    response = await client.post(RULES, json=_city_body(tel, town))
    assert response.status_code == 201, response.text
    data = response.json()
    assert (data["team"], data["kind"], data["city"], data["product"], data["editable"]) == ("it", "city", town.strip(), None, True)
    assert data["telecaller"] == {"id": str(tel.id), "full_name": tel.full_name, "active": True}
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "telecaller.rule_create", AuditLog.entity_id == data["id"]))
    assert audit.user_id == manager.id and audit.metadata_json == {"team": "it", "kind": "city", "telecaller_user_id": str(tel.id)}
    assert (await client.post(RULES, json=_city_body(tel, town.upper()))).status_code == 409  # one rule per team + city, any case


@pytest.mark.asyncio
async def test_a_product_rule_needs_an_active_product_of_the_team(client, db_session):
    manager = await _signed_in_manager(client, db_session)
    tel = await make_telecaller(db_session, manager)
    good = await product(db_session)
    body = {"team": "it", "kind": "product", "product_id": str(good.id), "telecaller_user_id": str(tel.id)}
    response = await client.post(RULES, json=body)
    assert response.status_code == 201 and response.json()["product"] == {"id": str(good.id), "name": good.name, "active": True}
    assert (await client.post(RULES, json=body)).status_code == 409
    overseas = await product(db_session, group="overseas", team="overseas")
    no_team = await product(db_session, group="other", team=None)
    inactive = await product(db_session, active=False)
    for bad, detail in ((overseas, "This product belongs to the Overseas team"), (no_team, "This product has no team: its leads wait in the unassigned queue"),
                        (inactive, "Choose an active product")):
        response = await client.post(RULES, json={**body, "product_id": str(bad.id)})
        assert (response.status_code, response.json()["detail"]) == (422, detail)
    assert (await client.post(RULES, json={**body, "product_id": str(uuid.uuid4())})).json()["detail"] == "Choose an active product"


@pytest.mark.asyncio
async def test_the_rule_shape_is_checked(client, db_session):
    manager = await _signed_in_manager(client, db_session)
    tel = await make_telecaller(db_session, manager)
    item = await product(db_session)
    cases = [
        ({"team": "it", "kind": "product", "telecaller_user_id": str(tel.id)}, "Choose a product"),
        ({"team": "it", "kind": "product", "product_id": str(item.id), "city": "Pune", "telecaller_user_id": str(tel.id)}, "A product rule has no city"),
        ({"team": "it", "kind": "city", "city": "   ", "telecaller_user_id": str(tel.id)}, "Enter a city"),
        ({"team": "it", "kind": "city", "city": "Pune", "product_id": str(item.id), "telecaller_user_id": str(tel.id)}, "A city rule has no product"),
    ]
    for body, detail in cases:
        response = await client.post(RULES, json=body)
        assert (response.status_code, response.json()["detail"]) == (422, detail)
    for body in (_city_body(tel, team="global"), _city_body(tel, kind="state"), _city_body(tel, telecaller="x")):
        assert (await client.post(RULES, json=body)).status_code == 422


@pytest.mark.asyncio
async def test_the_rule_telecaller_must_be_an_active_report_on_the_team(client, db_session):
    manager = await _signed_in_manager(client, db_session)
    overseas = await make_telecaller(db_session, manager, team="overseas")
    other_managers = await make_telecaller(db_session, await make_tl_manager(db_session))
    inactive = await make_telecaller(db_session, manager)
    inactive.active = False
    await db_session.commit()
    admin = await make_user(db_session, "it_admin", "it")
    expected = [
        (overseas, 422, f"{overseas.full_name} is on the Overseas team"),  # the backlog's negative scenario
        (other_managers, 403, "You can only assign leads to your direct reports"),
        (inactive, 422, "This telecaller is inactive"),
        (admin, 422, "Choose an active telecaller"),
    ]
    for target, status, detail in expected:
        response = await client.post(RULES, json=_city_body(target))
        assert (response.status_code, response.json()["detail"]) == (status, detail)


@pytest.mark.asyncio
async def test_super_admin_creates_a_rule_for_anyone(client, db_session):
    tel = await make_telecaller(db_session, await make_tl_manager(db_session), team="overseas")
    await login(client, await make_user(db_session, "super_admin", "global"))
    response = await client.post(RULES, json=_city_body(tel, team="overseas"))
    assert response.status_code == 201 and response.json()["editable"] is True


# --- list, change, delete -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_every_manager_reads_all_rules_but_edits_only_their_reports(client, db_session):
    owner = await make_tl_manager(db_session)
    theirs = await make_telecaller(db_session, owner)
    created = await rule(db_session, theirs, city_name=city())
    manager = await _signed_in_manager(client, db_session)
    mine = await make_telecaller(db_session, manager)
    [row] = (await _mine(client, theirs))["items"]
    assert (row["id"], row["editable"]) == (str(created.id), False)
    url = f"{RULES}/{created.id}"
    assert (await client.patch(url, json={"telecaller_user_id": str(mine.id)})).status_code == 403
    assert (await client.delete(url)).status_code == 403
    assert (await client.get(RULES, params={"team": "overseas", "telecaller_user_id": str(theirs.id)})).json()["total"] == 0
    assert (await client.get(RULES, params={"kind": "product", "telecaller_user_id": str(theirs.id)})).json()["total"] == 0


@pytest.mark.asyncio
async def test_a_manager_changes_and_deletes_their_rule(client, db_session):
    manager = await _signed_in_manager(client, db_session)
    first, second = await make_telecaller(db_session, manager), await make_telecaller(db_session, manager)
    created = (await client.post(RULES, json=_city_body(first))).json()
    url = f"{RULES}/{created['id']}"
    response = await client.patch(url, json={"telecaller_user_id": str(second.id)})
    assert response.status_code == 200 and response.json()["telecaller"]["id"] == str(second.id)
    assert (await client.patch(url, json={"telecaller_user_id": str(second.id), "city": "Pune"})).status_code == 422  # D6: telecaller only
    other = await make_telecaller(db_session, await make_tl_manager(db_session))
    assert (await client.patch(url, json={"telecaller_user_id": str(other.id)})).status_code == 403
    assert (await client.delete(url)).status_code == 204
    assert await db_session.get(TelDistributionRule, uuid.UUID(created["id"])) is None
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == created["id"]).order_by(AuditLog.created_at))).all()
    assert actions == ["telecaller.rule_create", "telecaller.rule_update", "telecaller.rule_delete"]
    assert (await client.delete(url)).status_code == 404
    assert (await client.patch(url, json={"telecaller_user_id": str(second.id)})).status_code == 404
