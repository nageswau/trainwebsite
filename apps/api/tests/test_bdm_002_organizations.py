"""bdm-002 -- organizations: create, read, list, duplicates (AC1, AC2, AC6, AC7; spec §5.3)."""

import re
import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, BdmOrganization
from app.services import bdm_organizations as svc
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import ORGS, create_org, make_bdm, org_payload, unique_name


async def _audits(db, org_id) -> list[str]:
    rows = await db.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(org_id)).order_by(AuditLog.created_at))
    return list(rows.all())


@pytest.mark.asyncio
async def test_bdm_creates_in_own_type_with_a_server_code_and_contacts(client, db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session), "school")
    await login(client, bdm)
    contacts = [{"name": "Dr Rao", "role": "principal"}, {"name": "Ms Iyer", "role": "placement_officer", "email": "IYER@X.EDU"}]
    org = await create_org(client, contacts=contacts)
    assert re.fullmatch(r"ORG-\d{6,}", org["code"])
    assert org["bdm_type"] == "school" and org["assigned_bdm"]["id"] == str(bdm.id) and org["archived"] is False
    assert [c["name"] for c in org["contacts"]] == ["Dr Rao", "Ms Iyer"] and org["contacts"][0]["is_primary"]
    assert org["contacts"][1]["email"] == "iyer@x.edu"
    assert org["primary_contact"]["name"] == "Dr Rao"
    assert org["last_meeting_at"] is None and org["next_meeting_at"] is None  # AC6
    assert org["permissions"] == {"can_edit": True, "can_archive": True, "can_restore": False, "can_reassign": False}
    assert "name_key" not in org and "city_key" not in org and "created_by_user_id" not in org
    assert await _audits(db_session, org["id"]) == ["bdm_organization.create"]


@pytest.mark.asyncio
async def test_codes_are_unique_and_increasing(client, db_session):
    await login(client, await make_bdm(db_session, await make_manager(db_session)))
    first, second = await create_org(client), await create_org(client)
    assert int(second["code"][4:]) > int(first["code"][4:])


@pytest.mark.asyncio
async def test_flagged_primary_wins(client, db_session):
    await login(client, await make_bdm(db_session, await make_manager(db_session)))
    org = await create_org(client, contacts=[{"name": "A"}, {"name": "B", "is_primary": True}])
    assert org["primary_contact"]["name"] == "B" and [c["name"] for c in org["contacts"]] == ["B", "A"]


@pytest.mark.asyncio
async def test_create_validation_and_roles(client, db_session):
    manager = await make_manager(db_session)
    await login(client, await make_bdm(db_session, manager))
    for bad in ({"contacts": []}, {"city": ""}, {"code": "ORG-000001"}, {"bdm_type": "agent"}, {"assigned_bdm_user_id": str(uuid.uuid4())}):
        assert (await client.post(ORGS, json=org_payload(**bad))).status_code == 422, bad
    for user in (manager, await make_user(db_session, "super_admin", "global"), await make_user(db_session, "it_admin", "it")):
        await login(client, user)
        response = await client.post(ORGS, json=org_payload())
        assert response.status_code == 403 and response.json()["detail"] == "BDM role required"


@pytest.mark.asyncio
async def test_duplicate_warns_then_confirm_creates_and_audits(client, db_session):
    await login(client, await make_bdm(db_session, await make_manager(db_session)))
    name = unique_name()
    first = await create_org(client, name=name, city="Kochi")
    warned = await client.post(ORGS, json=org_payload(name=f"  {name.upper()} ", city=" kochi"))
    assert warned.status_code == 409
    detail = warned.json()["detail"]
    assert detail["code"] == "possible_duplicate" and detail["total"] == 1
    assert detail["matches"] == [{"id": first["id"], "code": first["code"], "name": name, "city": "Kochi", "archived": False, "assigned_bdm_name": first["assigned_bdm"]["full_name"]}]
    count = await db_session.scalar(select(func.count()).select_from(BdmOrganization).where(BdmOrganization.name == name))
    assert count == 1  # nothing written by the warning
    confirmed = await client.post(ORGS, json=org_payload(name=name, city="Kochi", confirm_duplicate=True))
    assert confirmed.status_code == 201
    assert await _audits(db_session, confirmed.json()["organization"]["id"]) == ["bdm_organization.create", "bdm_organization.duplicate_override"]


@pytest.mark.asyncio
async def test_duplicate_is_per_module_and_full_width_matches(client, db_session):
    manager = await make_manager(db_session)
    name = unique_name("ＣＯＬ")
    await login(client, await make_bdm(db_session, manager, "college"))
    await create_org(client, name=name)
    assert (await client.post(ORGS, json=org_payload(name=name.replace("ＣＯＬ", "col")))).status_code == 409  # NFKC
    await login(client, await make_bdm(db_session, manager, "agent"))
    assert (await client.post(ORGS, json=org_payload(name=name))).status_code == 201  # another module never matches


@pytest.mark.asyncio
async def test_retry_after_a_lost_response_is_a_duplicate_not_a_second_row(client, db_session):
    """Review Focus 4: create is not idempotent; the retry is caught by the warning."""
    await login(client, await make_bdm(db_session, await make_manager(db_session)))
    payload = org_payload()
    assert (await client.post(ORGS, json=payload)).status_code == 201
    retry = await client.post(ORGS, json=payload)
    assert retry.status_code == 409 and retry.json()["detail"]["total"] == 1


@pytest.mark.asyncio
async def test_a_failure_before_commit_leaves_nothing(client, db_session, monkeypatch):
    """Review Focus 5: the audit write raising rolls back the organization and its contacts."""
    await login(client, await make_bdm(db_session, await make_manager(db_session)))
    name = unique_name()

    def boom(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(svc, "audit", boom)
    with pytest.raises(RuntimeError):
        await client.post(ORGS, json=org_payload(name=name))
    assert not await db_session.scalar(select(func.count()).select_from(BdmOrganization).where(BdmOrganization.name == name))


@pytest.mark.asyncio
async def test_list_filters_paging_and_archived_default(client, db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session), "agent")
    await login(client, bdm)
    city = unique_name("City")
    a = await create_org(client, name=unique_name("Alpha"), city=city, org_type="agent")
    b = await create_org(client, name=unique_name("Beta"), city=city, org_type="corporate")
    page = (await client.get(ORGS, params={"city": city.lower()})).json()
    assert {r["id"] for r in page["items"]} == {a["id"], b["id"]} and page["total"] == 2
    row = page["items"][0]
    assert set(row) == {
        "id",
        "code",
        "name",
        "org_type",
        "bdm_type",
        "city",
        "state",
        "existing_partner",
        "assigned_bdm",
        "primary_contact",
        "archived",
        "last_meeting_at",
        "next_meeting_at",
        "permissions",
    }
    assert [r["id"] for r in (await client.get(ORGS, params={"city": city, "org_type": "corporate"})).json()["items"]] == [b["id"]]
    assert [r["id"] for r in (await client.get(ORGS, params={"q": a["code"]})).json()["items"]] == [a["id"]]
    assert (await client.get(ORGS, params={"city": city, "limit": 1})).json()["items"][0]["id"] == min((a, b), key=lambda o: o["name"])["id"]
    assert len((await client.get(ORGS, params={"city": city, "assigned": "me"})).json()["items"]) == 2
    for bad in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"assigned": "nobody"}, {"org_type": "ngo"}):
        assert (await client.get(ORGS, params=bad)).status_code == 422, bad


@pytest.mark.asyncio
async def test_get_unknown_is_404(client, db_session):
    await login(client, await make_bdm(db_session, await make_manager(db_session)))
    response = await client.get(f"{ORGS}/{uuid.uuid4()}")
    assert response.status_code == 404 and response.json()["detail"] == "Organization not found"
