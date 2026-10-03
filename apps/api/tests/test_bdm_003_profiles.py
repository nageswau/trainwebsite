"""bdm-003 -- type-specific profiles through the service and the API (spec §5, §7 AC1-AC8, §12)."""

import asyncio
import logging
import uuid

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, BdmOrganization
from app.services import bdm_organizations as svc
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import ORGS, create_org, unique_name
from tests.bdm003_helpers import bdm_of, profile_org


def _org(org_type: str, **values) -> BdmOrganization:
    return BdmOrganization(id=uuid.uuid4(), org_type=org_type, **values)


def _locs(exc: RequestValidationError) -> dict[str, str]:
    return {e["loc"][-1]: e["msg"] for e in exc.errors()}


def test_check_profile_allows_the_group_and_refuses_other_keys_by_presence():
    svc.check_profile("school", {"board": "CBSE", "grade_from": 6}, None)
    svc.check_profile("university", {"affiliation": "VTU"}, None)
    svc.check_profile("corporate", {}, None)
    with pytest.raises(RequestValidationError) as exc:
        svc.check_profile("college", {"board": None, "country": "India", "affiliation": "VTU"}, None)
    assert _locs(exc.value) == {"board": "Board is not a field for College organizations", "country": "Country is not a field for College organizations"}
    assert all(e["loc"][:2] == ("body", "profile") for e in exc.value.errors())
    with pytest.raises(RequestValidationError) as exc:
        svc.check_profile("other", {"courses": "MBA"}, None)
    assert _locs(exc.value) == {"courses": "Courses is not a field for Other organizations"}


def test_check_profile_grade_order_uses_stored_values_overlaid_by_sent():
    stored = _org("school", grade_from=6, grade_to=12)
    svc.check_profile("school", {"grade_to": 8}, stored)
    svc.check_profile("school", {"grade_from": None, "grade_to": 3}, stored)  # the stored lowest grade is cleared in the same request
    for sent in ({"grade_to": 5}, {"grade_from": 12, "grade_to": 6}, {"grade_from": 12, "grade_to": 11}):
        with pytest.raises(RequestValidationError) as exc:
            svc.check_profile("school", sent, stored)
        assert _locs(exc.value) == {"grade_to": "Lowest grade can't be above the highest grade"}


def test_check_type_change_refuses_across_groups_while_the_old_group_has_data():
    user = type("U", (), {"id": uuid.uuid4()})()
    svc.check_type_change(user, _org("college", affiliation="VTU"), "university")  # same group
    svc.check_type_change(user, _org("school"), "college")  # nothing entered
    svc.check_type_change(user, _org("corporate"), "school")  # no old group
    with pytest.raises(HTTPException) as exc:
        svc.check_type_change(user, _org("school", board="CBSE", grade_to=10), "agent")
    assert exc.value.status_code == 409
    assert exc.value.detail == {"message": "Clear the School details before changing the type", "code": "profile_not_empty", "fields": ["board", "grade_to"]}


def test_profile_out_per_group():
    assert svc.profile_out(_org("agent", country="India", staff_count=4)) == {"kind": "agent", "country": "India", "territory": None, "source": None, "staff_count": 4}
    assert svc.profile_out(_org("university", courses="MBA"))["kind"] == "college"
    assert svc.profile_out(_org("training_institute")) is None


async def _audit(db, org_id, action: str) -> dict | None:
    row = await db.scalar(select(AuditLog).where(AuditLog.entity_id == str(org_id), AuditLog.action == f"bdm_organization.{action}").order_by(AuditLog.created_at.desc()))
    return row.metadata_json if row else None


def _new(org_type: str, **extra) -> dict:
    return {"org_type": org_type, "name": unique_name(), "city": "Kochi", "contacts": [{"name": "Dr Rao"}], **extra}


@pytest.mark.asyncio
async def test_creates_each_type_with_its_profile_and_always_returns_both_keys(client, db_session):
    await login(client, await bdm_of(db_session, "school"))
    school = await create_org(client, org_type="school", address="1 Main Rd\nKochi", profile={"board": "CBSE", "school_type": "private", "grade_from": 6, "grade_to": 12})
    assert school["profile"] == {"kind": "school", "board": "CBSE", "school_type": "private", "grade_from": 6, "grade_to": 12}
    assert school["address"] == "1 Main Rd\nKochi"
    assert (await client.get(f"{ORGS}/{school['id']}")).json()["organization"]["profile"] == school["profile"]
    metadata = await _audit(db_session, school["id"], "create")
    assert {"address", "board", "school_type", "grade_from", "grade_to"} <= set(metadata["fields"])
    assert "Main Rd" not in str(metadata) and "CBSE" not in str(metadata)  # names only, never values
    corporate = await create_org(client, org_type="corporate", profile={})
    assert corporate["profile"] is None and corporate["address"] is None
    await login(client, await bdm_of(db_session, "agent"))
    agent = await create_org(client, org_type="agent", profile={"country": "India", "territory": "South", "source": "referral", "staff_count": 8})
    assert agent["profile"] == {"kind": "agent", "country": "India", "territory": "South", "source": "referral", "staff_count": 8}
    await login(client, await bdm_of(db_session, "college"))
    uni = await create_org(client, org_type="university", profile={"affiliation": "VTU", "college_type": "engineering", "courses": "B.Tech CSE\nMBA"})
    assert uni["profile"]["kind"] == "college" and uni["profile"]["courses"] == "B.Tech CSE\nMBA"
    plain = await create_org(client)  # a bdm-002-style payload: unchanged behaviour (AC7)
    assert plain["profile"] == {"kind": "college", "affiliation": None, "college_type": None, "courses": None}


@pytest.mark.asyncio
async def test_create_refuses_another_types_field_and_consumes_no_code(client, db_session):
    await login(client, await bdm_of(db_session, "college"))
    first = await create_org(client)
    refused_body = _new("college", profile={"board": "CBSE", "grade_to": 3})
    refused = await client.post(ORGS, json=refused_body)
    assert refused.status_code == 422
    assert [(e["loc"], e["msg"]) for e in refused.json()["detail"]] == [
        (["body", "profile", "board"], "Board is not a field for College organizations"),
        (["body", "profile", "grade_to"], "Highest grade is not a field for College organizations"),
    ]
    assert await db_session.scalar(select(BdmOrganization).where(BdmOrganization.name == refused_body["name"])) is None
    second = await create_org(client)
    assert int(second["code"][4:]) == int(first["code"][4:]) + 1  # the refused create took no ORG- number
    order = await client.post(ORGS, json=_new("school", profile={"grade_from": 10, "grade_to": 6}))
    assert order.status_code == 422 and order.json()["detail"][0]["msg"] == "Lowest grade can't be above the highest grade"


@pytest.mark.asyncio
async def test_create_refuses_live_metrics_bad_enums_and_a_bad_contact_email(client, db_session):
    await login(client, await bdm_of(db_session, "agent"))
    for profile in ({"commission": 10}, {"students": 1}, {"applications": 1}, {"enrollments": 1}, {"master_login": "x"}, {"source": "tv"}, {"staff_count": "8"}):
        assert (await client.post(ORGS, json=_new("agent", profile=profile))).status_code == 422, profile
    assert (await client.post(ORGS, json=_new("agent", commission=10))).status_code == 422
    assert (await client.post(ORGS, json=_new("agent", contacts=[{"name": "A", "email": "no"}]))).status_code == 422


async def _latest_audit_id(db, org_id):
    return await db.scalar(select(AuditLog.id).where(AuditLog.entity_id == str(org_id)).order_by(AuditLog.created_at.desc()).limit(1))


@pytest.mark.asyncio
async def test_patch_partial_clear_no_op_and_null_profile(client, db_session):
    await login(client, await bdm_of(db_session, "school"))
    org = await profile_org(client, "school", board="CBSE", grade_from=6, grade_to=12)
    url = f"{ORGS}/{org['id']}"
    cleared = await client.patch(url, json={"profile": {"board": None}, "address": "Kochi"})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["organization"]["profile"] == {"kind": "school", "board": None, "school_type": None, "grade_from": 6, "grade_to": 12}
    assert sorted((await _audit(db_session, org["id"], "update"))["fields"]) == ["address", "board"]
    before = await _latest_audit_id(db_session, org["id"])
    assert (await client.patch(url, json={"profile": {}})).status_code == 200
    assert (await client.patch(url, json={"profile": {"grade_to": 12}})).status_code == 200  # equal to stored: not a change
    assert await _latest_audit_id(db_session, org["id"]) == before
    assert (await client.patch(url, json={"profile": None})).status_code == 422
    order = await client.patch(url, json={"profile": {"grade_to": 5}})
    assert order.status_code == 422 and order.json()["detail"][0]["loc"] == ["body", "profile", "grade_to"]


@pytest.mark.asyncio
async def test_type_change_is_409_until_cleared_and_college_university_is_free(client, db_session):
    await login(client, await bdm_of(db_session, "school"))
    org = await profile_org(client, "school", board="CBSE", grade_to=10)
    url = f"{ORGS}/{org['id']}"
    refused = await client.patch(url, json={"org_type": "college"})
    assert refused.status_code == 409
    assert refused.json()["detail"] == {"message": "Clear the School details before changing the type", "code": "profile_not_empty", "fields": ["board", "grade_to"]}
    both = await client.patch(url, json={"org_type": "college", "profile": {"board": None}})  # the old group's keys belong to another type now
    assert both.status_code == 422 and both.json()["detail"][0]["loc"] == ["body", "profile", "board"]
    assert (await client.patch(url, json={"profile": {"board": None, "grade_to": None}})).status_code == 200
    moved = await client.patch(url, json={"org_type": "college", "profile": {"affiliation": "VTU"}})
    assert moved.status_code == 200 and moved.json()["organization"]["profile"] == {"kind": "college", "affiliation": "VTU", "college_type": None, "courses": None}
    uni = await client.patch(url, json={"org_type": "university"})
    assert uni.status_code == 200 and uni.json()["organization"]["profile"]["affiliation"] == "VTU"
    assert sorted((await _audit(db_session, org["id"], "update"))["fields"]) == ["org_type"]


@pytest.mark.asyncio
async def test_pre_bdm003_organization_edits_cleanly(client, db_session):
    """Review Focus 1: an organization saved before bdm-003 (every profile column NULL) edits its common fields with no profile check."""
    await login(client, await bdm_of(db_session, "college"))
    org = await create_org(client)
    edited = await client.patch(f"{ORGS}/{org['id']}", json={"name": unique_name(), "org_type": "agent"})
    assert edited.status_code == 200 and edited.json()["organization"]["profile"]["kind"] == "agent"


@pytest.mark.asyncio
async def test_profile_writes_keep_bdm002_authorization(client, db_session):
    manager = await make_manager(db_session)
    owner = await bdm_of(db_session, "school", manager)
    await login(client, owner)
    org = await profile_org(client, "school", board="CBSE")
    url = f"{ORGS}/{org['id']}"
    await login(client, await bdm_of(db_session, "school", manager))  # same type, not assigned
    assert (await client.patch(url, json={"profile": {"board": "ICSE"}})).status_code == 403
    await login(client, manager)
    assert (await client.patch(url, json={"profile": {"board": "ICSE"}})).status_code == 403
    await login(client, await bdm_of(db_session, "agent"))  # other module: out of scope
    assert (await client.patch(url, json={"profile": {"board": "ICSE"}})).status_code == 404
    await login(client, owner)
    assert (await client.post(f"{url}/archive")).status_code == 200
    assert (await client.patch(url, json={"profile": {"board": "ICSE"}})).status_code == 409
