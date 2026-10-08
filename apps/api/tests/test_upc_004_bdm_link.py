"""upc-004 -- a BDM University organization and the Global University Master (spec §1 UD7-UD11; AC2, AC5)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.bdm001_helpers import login as bdm_login
from tests.bdm001_helpers import make_manager
from tests.bdm002_helpers import ORGS, create_org, make_bdm, org_payload
from tests.upc003_helpers import catalogue_country, create, login, make_head, url


async def _master_university(client, db, **overrides) -> dict:
    await login(client, await make_head(db))
    return await create(client, (await catalogue_country(db)).id, name=f"ABC University {uuid.uuid4().hex[:8]}", **overrides)


async def _college_bdm(client, db):
    bdm = await make_bdm(db, await make_manager(db), "college")
    await bdm_login(client, bdm)
    return bdm


@pytest.mark.asyncio
async def test_bdm_university_create_shows_the_master_panel_and_blocks_until_acknowledged(client, db_session):
    uni = await _master_university(client, db_session, existing_relationship="existing")
    await _college_bdm(client, db_session)
    response = await client.post(ORGS, json=org_payload(org_type="university", name=uni["name"].lower()))
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "possible_duplicate" and detail["matches"] == [] and detail["total"] == 0
    assert detail["university_total"] == 1 and detail["university_matches"][0]["id"] == uni["id"]
    assert detail["university_matches"][0]["existing_relationship"] == "existing"
    assert "University Master" in detail["message"]
    saved = await client.post(ORGS, json=org_payload(org_type="university", name=uni["name"], confirm_duplicate=True))
    assert saved.status_code == 201 and saved.json()["organization"]["university"] is None


@pytest.mark.asyncio
async def test_bdm_links_on_create_and_the_master_lists_the_link(client, db_session):
    uni = await _master_university(client, db_session)
    bdm = await _college_bdm(client, db_session)
    org = await create_org(client, org_type="university", name=uni["name"], university_id=uni["id"], confirm_duplicate=True)
    assert org["university"] == {
        "id": uni["id"],
        "university_code": uni["university_code"],
        "name": uni["name"],
        "country_name": uni["country"]["name"],
        "city": uni["city"],
        "primary_manager_name": None,
    }
    assert "commission" not in str(org["university"])
    create_audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == org["id"], AuditLog.action == "bdm_organization.create"))
    assert "university_id" in create_audit.metadata_json["fields"]
    await login(client, await make_head(db_session))
    linked = (await client.get(url(uni["id"]))).json()["university"]["linked_bdm_organizations"]
    assert linked == [{"id": org["id"], "code": org["code"], "name": org["name"], "city": org["city"], "bdm_type": "college", "assigned_bdm_name": bdm.full_name, "archived": False}]


@pytest.mark.asyncio
async def test_link_without_a_master_match_needs_no_confirmation(client, db_session):
    uni = await _master_university(client, db_session)
    await _college_bdm(client, db_session)
    org = await create_org(client, org_type="university", name=f"Different name {uuid.uuid4().hex[:6]}", university_id=uni["id"])
    assert org["university"]["id"] == uni["id"]


@pytest.mark.asyncio
async def test_link_is_validated(client, db_session):
    uni = await _master_university(client, db_session)
    await _college_bdm(client, db_session)
    unknown = await client.post(ORGS, json=org_payload(org_type="university", university_id=str(uuid.uuid4())))
    assert unknown.status_code == 422 and unknown.json()["detail"] == "Unknown university"
    wrong_type = await client.post(ORGS, json=org_payload(org_type="college", university_id=uni["id"]))
    assert wrong_type.status_code == 422 and wrong_type.json()["detail"] == "Only University organizations can be linked to the University Master"


@pytest.mark.asyncio
async def test_non_university_orgs_are_never_matched_against_the_master(client, db_session):
    uni = await _master_university(client, db_session)
    await _college_bdm(client, db_session)
    await create_org(client, org_type="college", name=uni["name"])  # a college may share a university's name


@pytest.mark.asyncio
async def test_patch_links_unlinks_and_a_type_change_clears_the_link(client, db_session):
    uni = await _master_university(client, db_session)
    await _college_bdm(client, db_session)
    org = await create_org(client, org_type="university", name=f"Org {uuid.uuid4().hex[:6]}")
    linked = await client.patch(f"{ORGS}/{org['id']}", json={"university_id": uni["id"]})
    assert linked.status_code == 200 and linked.json()["organization"]["university"]["id"] == uni["id"]
    unlinked = await client.patch(f"{ORGS}/{org['id']}", json={"university_id": None})
    assert unlinked.status_code == 200 and unlinked.json()["organization"]["university"] is None
    await client.patch(f"{ORGS}/{org['id']}", json={"university_id": uni["id"]})
    moved = await client.patch(f"{ORGS}/{org['id']}", json={"org_type": "college"})
    assert moved.status_code == 200 and moved.json()["organization"]["university"] is None
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == org["id"], AuditLog.action == "bdm_organization.update").order_by(AuditLog.created_at))).all()
    assert audits[-1].metadata_json["fields"] == ["org_type", "university_id"]
    refused = await client.patch(f"{ORGS}/{org['id']}", json={"university_id": uni["id"]})
    assert refused.status_code == 422
