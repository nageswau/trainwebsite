"""tel-002 -- the campaign list API (spec §4; AC2, AC3, AC4, AC5; DEC-SCOPE-074 P1/P3/P4). Names are unique per test (shared database)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.bdm001_helpers import login, make_user

PRODUCTS, CAMPAIGNS = "/api/v1/telecaller/products", "/api/v1/telecaller/campaigns"


def _name(prefix: str = "Camp") -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


async def _as(client, db, role="telecaller_manager", division="global"):
    user = await make_user(db, role, division)
    await login(client, user)
    return user


async def _product(client, *, active=True) -> dict:
    product = (await client.post(PRODUCTS, json={"group": "it", "name": _name("Prod")})).json()
    if not active:
        product = (await client.patch(f"{PRODUCTS}/{product['id']}", json={"active": False})).json()
    return product


async def _create(client, product_id, **body):
    payload = {"name": _name(), "source": "instagram", "product_id": str(product_id), "start_date": "2026-09-01", **body}
    return await client.post(CAMPAIGNS, json=payload)


@pytest.mark.asyncio
async def test_create_the_backlog_example(client, db_session):
    """ "Sep 2026 Cyber Security" (Instagram, Cyber Security) -- the backlog's positive scenario."""
    user = await _as(client, db_session)
    cyber = (await client.get(PRODUCTS, params={"q": "Cyber Security", "group": "it"})).json()["items"][0]
    name = f"Sep 2026 Cyber Security {uuid.uuid4().hex[:6]}"
    response = await _create(client, cyber["id"], name=name, start_date="2026-09-01", end_date="2026-09-30")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body == {
        "id": body["id"],
        "name": name,
        "source": "instagram",
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
        "active": True,
        "product": {"id": cyber["id"], "name": "Cyber Security", "group": "it", "active": True},
    }
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"]))
    assert audit.action == "telecaller.campaign_create" and audit.user_id == user.id and audit.entity_type == "tel_campaign"


@pytest.mark.asyncio
async def test_end_date_is_optional(client, db_session):
    await _as(client, db_session)
    response = await _create(client, (await _product(client))["id"])
    assert response.status_code == 201 and response.json()["end_date"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["tiktok", "Instagram", "", None])
async def test_source_must_be_a_section_2_source(client, db_session, source):
    """AC3."""
    await _as(client, db_session)
    response = await _create(client, (await _product(client))["id"], source=source)
    assert response.status_code == 422 and "Source" in str(response.json()["detail"])


@pytest.mark.asyncio
async def test_product_must_exist_and_be_active(client, db_session):
    """AC3 / P4."""
    await _as(client, db_session)
    inactive = await _product(client, active=False)
    for product_id in (inactive["id"], uuid.uuid4()):
        response = await _create(client, product_id)
        assert response.status_code == 422 and "active product" in response.json()["detail"]


@pytest.mark.asyncio
async def test_end_before_start_is_422_on_create_and_on_the_merged_row(client, db_session):
    """AC4: on PATCH the rule is checked against the stored dates too."""
    await _as(client, db_session)
    product = await _product(client)
    response = await _create(client, product["id"], start_date="2026-09-30", end_date="2026-09-01")
    assert response.status_code == 422 and "End date cannot be before the start date" in response.json()["detail"]
    campaign = (await _create(client, product["id"], start_date="2026-09-10", end_date="2026-09-20")).json()
    url = f"{CAMPAIGNS}/{campaign['id']}"
    assert (await client.patch(url, json={"end_date": "2026-09-05"})).status_code == 422
    assert (await client.patch(url, json={"start_date": "2026-09-25"})).status_code == 422
    assert (await client.patch(url, json={"end_date": None})).json()["end_date"] is None  # null clears the optional end
    assert (await client.patch(url, json={"start_date": None})).status_code == 422
    assert (await client.patch(url, json={"start_date": "2026-13-01"})).status_code == 422


@pytest.mark.asyncio
async def test_duplicate_name_is_409_case_insensitive(client, db_session):
    await _as(client, db_session)
    product = await _product(client)
    name = _name()
    assert (await _create(client, product["id"], name=name)).status_code == 201
    response = await _create(client, product["id"], name=f" {name.lower()} ")
    assert response.status_code == 409 and "already exists" in response.json()["detail"]
    other = (await _create(client, product["id"])).json()
    assert (await client.patch(f"{CAMPAIGNS}/{other['id']}", json={"name": name.upper()})).status_code == 409


@pytest.mark.asyncio
async def test_deactivation_is_independent(client, db_session):
    """P4: deactivating a product leaves its campaign alone; that campaign stays editable but cannot move to an inactive product."""
    await _as(client, db_session)
    product, spare_inactive, spare = await _product(client), await _product(client, active=False), await _product(client)
    campaign = (await _create(client, product["id"])).json()
    await client.patch(f"{PRODUCTS}/{product['id']}", json={"active": False})
    url = f"{CAMPAIGNS}/{campaign['id']}"
    edited = await client.patch(url, json={"name": _name("Edited"), "product_id": product["id"]})  # unchanged inactive product: allowed
    assert edited.status_code == 200 and edited.json()["active"] is True and edited.json()["product"]["active"] is False
    moved = await client.patch(url, json={"product_id": spare_inactive["id"]})
    assert moved.status_code == 422 and "active product" in moved.json()["detail"]
    assert (await client.patch(url, json={"product_id": spare["id"]})).json()["product"]["id"] == spare["id"]


@pytest.mark.asyncio
async def test_update_audits_field_names_and_404(client, db_session):
    user = await _as(client, db_session)
    campaign = (await _create(client, (await _product(client))["id"])).json()
    response = await client.patch(f"{CAMPAIGNS}/{campaign['id']}", json={"source": "walk_in", "active": False})
    assert response.status_code == 200 and response.json()["source"] == "walk_in" and response.json()["active"] is False
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == campaign["id"], AuditLog.action == "telecaller.campaign_update"))).one()
    assert audit.user_id == user.id and sorted(audit.metadata_json["fields"]) == ["active", "source"]
    assert (await client.patch(f"{CAMPAIGNS}/{uuid.uuid4()}", json={"active": False})).status_code == 404
    assert (await client.patch(f"{CAMPAIGNS}/{campaign['id']}", json={"budget": 5})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("telecaller", "it"), ("it_admin", "it"), ("counselor", "overseas"), ("bdm_manager", "global")])
async def test_non_managers_cannot_write(client, db_session, role, division):
    """AC5."""
    await _as(client, db_session)
    product = await _product(client)
    campaign = (await _create(client, product["id"])).json()
    await _as(client, db_session, role, division)
    assert (await _create(client, product["id"])).status_code == 403
    assert (await client.patch(f"{CAMPAIGNS}/{campaign['id']}", json={"active": False})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "sees_inactive"), [("telecaller", "it", False), ("overseas_admin", "overseas", False), ("super_admin", "global", True)])
async def test_reads_filters_and_active_rule(client, db_session, role, division, sees_inactive):
    """P1 / AC2: readers see active campaigns only; managers and super_admin also see inactive ones. Filters narrow."""
    tag = uuid.uuid4().hex[:8]
    await _as(client, db_session)
    product, other_product = await _product(client), await _product(client)
    live = (await _create(client, product["id"], name=f"Live {tag}", start_date="2026-08-01")).json()
    newer = (await _create(client, other_product["id"], name=f"Newer {tag}", source="google", start_date="2026-09-01")).json()
    gone = (await _create(client, product["id"], name=f"Gone {tag}")).json()
    await client.patch(f"{CAMPAIGNS}/{gone['id']}", json={"active": False})
    await _as(client, db_session, role, division)

    async def listed(**params):
        response = await client.get(CAMPAIGNS, params={"q": tag, **params})
        assert response.status_code == 200
        return [r["name"] for r in response.json()["items"]]

    expected = [newer["name"], live["name"]] + ([gone["name"]] if sees_inactive else [])  # active first, then newest start
    assert await listed() == expected
    assert await listed(source="google") == [newer["name"]]
    assert await listed(product_id=product["id"]) == [live["name"]] + ([gone["name"]] if sees_inactive else [])
    assert await listed(active="false") == ([gone["name"]] if sees_inactive else [])
    assert (await client.get(CAMPAIGNS, params={"source": "tiktok"})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("bdm", "it"), ("overseas_student", "overseas")])
async def test_other_roles_cannot_read(client, db_session, role, division):
    await _as(client, db_session, role, division)
    assert (await client.get(CAMPAIGNS)).status_code == 403
