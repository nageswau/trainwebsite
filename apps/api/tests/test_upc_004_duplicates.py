"""upc-004 -- duplicate prevention in the Global University Master (spec §1 UD1-UD6, UD11; AC1, AC3, AC4)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.upc003_helpers import BASE, as_role, catalogue_country, create, internal_country, login, make_head, make_user, url

DUPLICATES = f"{BASE}/duplicates"
REASON = "Separate campus with its own partnership office"


def _name() -> str:
    return f"ABC University {uuid.uuid4().hex[:8]}"


async def _head(client, db):
    head = await make_head(db)
    await login(client, head)
    return head


async def _audits(db, university_id) -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.entity_id == str(university_id)).order_by(AuditLog.created_at))).all())


# --- search before adding (UD6) -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicates_matches_case_and_spacing_in_the_same_country_only(client, db_session):
    await _head(client, db_session)
    gb, jp = await catalogue_country(db_session), await internal_country(db_session)
    name = _name()
    existing = await create(client, gb.id, name=name, existing_relationship="existing")
    await create(client, jp.id, name=name)  # same name, another country: allowed (AC3)
    response = await client.get(DUPLICATES, params={"name": f"  {name.upper()}  ".replace(" ", "   "), "country_id": str(gb.id)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1 and [m["id"] for m in body["items"]] == [existing["id"]]
    match = body["items"][0]
    assert set(match) == {"id", "university_code", "name", "country", "city", "active", "catalogue_visible", "existing_relationship", "primary_manager", "backup_manager"}
    assert match["country"] == {"id": str(gb.id), "name": gb.name} and match["existing_relationship"] == "existing" and match["primary_manager"] is None
    every = (await client.get(DUPLICATES, params={"name": name})).json()
    assert every["total"] == 2  # no country: every country (the BDM case)


@pytest.mark.asyncio
async def test_duplicates_counts_inactive_rows_and_excludes_the_one_being_edited(client, db_session):
    await _head(client, db_session)
    gb = await catalogue_country(db_session)
    uni = await create(client, gb.id, name=_name())
    assert (await client.post(url(uni["id"], "deactivate"))).status_code == 200
    found = (await client.get(DUPLICATES, params={"name": uni["name"], "country_id": str(gb.id)})).json()
    assert found["total"] == 1 and found["items"][0]["active"] is False
    mine = (await client.get(DUPLICATES, params={"name": uni["name"], "country_id": str(gb.id), "exclude_id": uni["id"]})).json()
    assert mine == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_duplicates_validates_the_name_and_requires_a_master_reader(client, db_session):
    await _head(client, db_session)
    assert (await client.get(DUPLICATES, params={"name": "   "})).status_code == 422
    assert (await client.get(DUPLICATES)).status_code == 422
    await as_role(client, db_session, "counselor", "overseas")
    assert (await client.get(DUPLICATES, params={"name": "x"})).status_code == 403


# --- create blocks; head / super_admin override (UD2, AC1, AC4) -----------------------------------------------------------
@pytest.mark.asyncio
async def test_lower_case_duplicate_is_blocked_with_the_panel(client, db_session):
    await _head(client, db_session)
    gb = await catalogue_country(db_session)
    name = _name()
    existing = await create(client, gb.id, name=name)
    response = await client.post(BASE, json={"name": name.lower(), "country_id": str(gb.id), "city": "Leeds"})
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "university_duplicate" and detail["total"] == 1 and detail["can_override"] is True
    assert detail["matches"][0]["id"] == existing["id"] and detail["matches"][0]["university_code"] == existing["university_code"]
    assert "already" in detail["message"]


@pytest.mark.asyncio
async def test_head_overrides_with_a_reason_and_the_override_is_audited(client, db_session):
    await _head(client, db_session)
    gb = await catalogue_country(db_session)
    name = _name()
    await create(client, gb.id, name=name)
    response = await client.post(BASE, json={"name": name, "country_id": str(gb.id), "city": "Leeds", "duplicate_reason": f"  {REASON}  "})
    assert response.status_code == 201, response.text
    audits = await _audits(db_session, response.json()["university"]["id"])
    assert [a.action for a in audits] == ["university.create", "university.duplicate_override"]
    assert audits[1].metadata_json == {"match_count": 1, "reason": REASON}


@pytest.mark.asyncio
async def test_overseas_admin_cannot_override(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    gb = await catalogue_country(db_session)
    name = _name()
    await create(client, gb.id, name=name)
    response = await client.post(BASE, json={"name": name, "country_id": str(gb.id), "city": "Leeds", "duplicate_reason": REASON})
    assert response.status_code == 409 and response.json()["detail"]["can_override"] is False


@pytest.mark.asyncio
async def test_super_admin_may_override(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    gb = await catalogue_country(db_session)
    name = _name()
    await create(client, gb.id, name=name)
    blocked = await client.post(BASE, json={"name": name, "country_id": str(gb.id), "city": "Leeds"})
    assert blocked.status_code == 409 and blocked.json()["detail"]["can_override"] is True
    assert (await client.post(BASE, json={"name": name, "country_id": str(gb.id), "city": "Leeds", "duplicate_reason": REASON})).status_code == 201


@pytest.mark.asyncio
async def test_reason_length_is_validated_and_ignored_without_a_match(client, db_session):
    await _head(client, db_session)
    gb = await catalogue_country(db_session)
    assert (await client.post(BASE, json={"name": _name(), "country_id": str(gb.id), "city": "Leeds", "duplicate_reason": "too short"})).status_code == 422
    assert (await client.post(BASE, json={"name": _name(), "country_id": str(gb.id), "city": "Leeds", "duplicate_reason": "x" * 501})).status_code == 422
    response = await client.post(BASE, json={"name": _name(), "country_id": str(gb.id), "city": "Leeds", "duplicate_reason": REASON})
    assert response.status_code == 201
    assert [a.action for a in await _audits(db_session, response.json()["university"]["id"])] == ["university.create"]


@pytest.mark.asyncio
async def test_same_name_in_another_country_is_allowed(client, db_session):
    await _head(client, db_session)
    name = _name()
    await create(client, (await catalogue_country(db_session)).id, name=name)
    await create(client, (await internal_country(db_session)).id, name=name)


# --- edit re-runs the check (UD3) -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rename_or_move_into_a_duplicate_is_blocked(client, db_session):
    await _head(client, db_session)
    gb, jp = await catalogue_country(db_session), await internal_country(db_session)
    taken = await create(client, gb.id, name=_name())
    other = await create(client, jp.id, name=taken["name"])
    renamed = await create(client, gb.id, name=_name())
    response = await client.patch(url(renamed["id"]), json={"name": f" {taken['name'].upper()} "})
    assert response.status_code == 409 and response.json()["detail"]["matches"][0]["id"] == taken["id"]
    assert (await client.patch(url(other["id"]), json={"country_id": str(gb.id)})).status_code == 409
    overridden = await client.patch(url(other["id"]), json={"country_id": str(gb.id), "duplicate_reason": REASON})
    assert overridden.status_code == 200
    assert [a.action for a in await _audits(db_session, other["id"])][-2:] == ["university.update", "university.duplicate_override"]


@pytest.mark.asyncio
async def test_edit_without_a_name_or_country_change_is_not_checked(client, db_session):
    await _head(client, db_session)
    gb = await catalogue_country(db_session)
    first = await create(client, gb.id, name=_name())
    second = await client.post(BASE, json={"name": first["name"], "country_id": str(gb.id), "city": "Leeds", "duplicate_reason": REASON})
    second_id = second.json()["university"]["id"]
    assert (await client.patch(url(second_id), json={"city": "York", "name": first["name"]})).status_code == 200  # same name: no change


@pytest.mark.asyncio
async def test_legacy_admin_create_sets_the_key_so_it_is_found(client, db_session):
    admin = await make_user(db_session, "super_admin", "global")
    await login(client, admin)
    gb = await catalogue_country(db_session)
    name = _name()
    legacy = await client.post("/api/v1/admin/universities", json={"country_slug": gb.slug, "slug": f"legacy-{uuid.uuid4().hex[:10]}", "name": name, "city": "Leeds"})
    assert legacy.status_code == 201, legacy.text
    assert (await client.get(DUPLICATES, params={"name": name.lower(), "country_id": str(gb.id)})).json()["total"] == 1
