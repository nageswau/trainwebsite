"""rec-002 -- the six simple recruiter lists (spec §4; AC1-AC5; DEC-SCOPE-117 C1-C3). Names are unique per test (shared database)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.rec001_helpers import as_role, login, make_recruiter

BASE = "/api/v1/recruiter/catalogue"
KINDS = ["lead-sources", "candidate-sources", "industries", "job-categories", "contact-roles", "company-sizes"]
WRITERS = [("placement_manager", "global"), ("super_admin", "global")]
OUTSIDERS = [("hr_team", "it"), ("it_admin", "it"), ("telecaller_manager", "global"), ("bdm", "it"), ("it_student", "it")]


def _name(prefix: str = "Value") -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


async def _as_recruiter(client, db):
    user = await make_recruiter(db)
    await login(client, user)
    return user


async def _create(client, kind="lead-sources", **body):
    return await client.post(f"{BASE}/{kind}", json={"name": _name(), **body})


async def _all(client, kind: str) -> list[dict]:
    return (await client.get(f"{BASE}/{kind}", params={"limit": 100})).json()["items"]


# --- seed (AC1) -----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_seeds_are_listed_in_source_order(client, db_session):
    await _as_recruiter(client, db_session)
    lists = {kind: await _all(client, kind) for kind in KINDS}
    names = lambda kind: [r["name"] for r in lists[kind]]  # noqa: E731
    assert names("lead-sources")[:15] == [
        "LinkedIn",
        "College visits",
        "Job fairs",
        "Recruitment events",
        "Company visits",
        "Website",
        "Google",
        "Social media",
        "Referrals",
        "Existing clients",
        "BDM network",
        "Corporate database",
        "Cold calling",
        "Email campaigns",
        "WhatsApp campaigns",
    ]
    assert names("candidate-sources")[:12] == [
        "College placements",
        "Edusphere students",
        "IT training students",
        "Job portals",
        "LinkedIn",
        "Referral",
        "Walk-ins",
        "Social media",
        "Career fairs",
        "Campus drives",
        "Database",
        "Employee referrals",
    ]
    assert names("job-categories")[:6] == ["IT", "Sales", "Marketing", "Finance", "HR", "Engineering"]
    assert names("contact-roles")[:5] == ["HR Manager", "Talent Acquisition Manager", "Recruiter", "Hiring Manager", "HR Head"]
    assert names("company-sizes")[:6] == ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001+"]
    first = lists["lead-sources"][0]
    assert set(first) == {"id", "name", "active", "sort_order"} and first["active"] is True and first["sort_order"] == 1


# --- create ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
async def test_manager_adds_a_value_at_the_end_and_it_is_audited(client, db_session, kind):
    """The backlog's positive scenario (the manager adds the source "Naukri") on every list."""
    user = await as_role(client, db_session, "placement_manager", "global")
    name = _name("Naukri")
    response = await client.post(f"{BASE}/{kind}", json={"name": f"  {name}  "})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body == {"id": body["id"], "name": name, "active": True, "sort_order": body["sort_order"]}
    assert body["sort_order"] == max(r["sort_order"] for r in await _all_pages(client, kind))
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"]))
    assert audit.action == "recruiter.catalogue_create" and audit.user_id == user.id
    assert audit.entity_type == f"rec_{kind.replace('-', '_')}" and audit.metadata_json == {"fields": ["name"]}


async def _all_pages(client, kind):
    items, offset = [], 0
    while True:
        page = (await client.get(f"{BASE}/{kind}", params={"limit": 100, "offset": offset})).json()
        items += page["items"]
        offset += 100
        if offset >= page["total"]:
            return items


@pytest.mark.asyncio
async def test_super_admin_writes_too(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    assert (await _create(client, "industries")).status_code == 201


@pytest.mark.asyncio
async def test_duplicate_name_is_409_case_insensitive_per_list(client, db_session):
    """AC4."""
    await as_role(client, db_session, "placement_manager", "global")
    name = _name()
    assert (await _create(client, "job-categories", name=name)).status_code == 201
    duplicate = await _create(client, "job-categories", name=name.upper())
    assert duplicate.status_code == 409 and duplicate.json()["detail"] == f"A value named “{name.upper()}” already exists in this list"
    assert (await _create(client, "contact-roles", name=name)).status_code == 201  # another list is fine
    assert (await _create(client, "lead-sources", name="linkedin")).status_code == 409  # the seed counts too


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"name": "   "}, "Name is required"),
        ({"name": "x" * 121}, "Name must be at most 120 characters"),
        ({"name": "bad\x07name"}, "Name contains invalid characters"),
        ({"name": None}, "Name"),
        ({"colour": "red"}, "Unknown field"),
        ({"active": False}, "Unknown field"),
    ],
)
async def test_create_validation(client, db_session, body, message):
    await as_role(client, db_session, "placement_manager", "global")
    response = await client.post(f"{BASE}/industries", json={"name": _name(), **body})
    assert response.status_code == 422
    assert message in str(response.json()["detail"])


@pytest.mark.asyncio
async def test_body_must_be_an_object(client, db_session):
    await as_role(client, db_session, "placement_manager", "global")
    assert (await client.post(f"{BASE}/industries", json=["x"])).status_code == 422  # FastAPI's dict body refuses it first


@pytest.mark.asyncio
async def test_unknown_catalogue_is_404(client, db_session):
    await as_role(client, db_session, "placement_manager", "global")
    assert (await client.get(f"{BASE}/colours")).status_code == 404
    assert (await client.post(f"{BASE}/colours", json={"name": "x"})).status_code == 404
    assert (await client.patch(f"{BASE}/colours/{uuid.uuid4()}", json={"name": "x"})).status_code == 404


# --- update (AC2, AC5) ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rename_keeps_the_id_and_audits_field_names(client, db_session):
    user = await as_role(client, db_session, "placement_manager", "global")
    created = (await _create(client, "company-sizes")).json()
    new_name = _name("Renamed")
    response = await client.patch(f"{BASE}/company-sizes/{created['id']}", json={"name": new_name})
    assert response.status_code == 200 and response.json() == {**created, "name": new_name}
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == created["id"], AuditLog.action == "recruiter.catalogue_update"))).one()
    assert audit.user_id == user.id and audit.metadata_json == {"fields": ["name"]}


@pytest.mark.asyncio
async def test_a_patch_that_changes_nothing_writes_no_audit(client, db_session):
    await as_role(client, db_session, "placement_manager", "global")
    created = (await _create(client, "industries")).json()
    assert (await client.patch(f"{BASE}/industries/{created['id']}", json={"name": created["name"], "active": True})).status_code == 200
    updates = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == created["id"], AuditLog.action == "recruiter.catalogue_update"))).all()
    assert updates == []


@pytest.mark.asyncio
async def test_update_rules(client, db_session):
    await as_role(client, db_session, "placement_manager", "global")
    created = (await _create(client, "contact-roles")).json()
    url = f"{BASE}/contact-roles/{created['id']}"
    assert (await client.patch(url, json={"name": None})).status_code == 422
    assert (await client.patch(url, json={"active": None})).status_code == 422
    assert (await client.patch(url, json={"active": "no"})).status_code == 422
    assert (await client.patch(url, json={"sort_order": 1})).status_code == 422
    assert (await client.patch(f"{BASE}/contact-roles/{uuid.uuid4()}", json={"name": "x"})).status_code == 404
    other = (await _create(client, "lead-sources")).json()
    assert (await client.patch(f"{BASE}/contact-roles/{other['id']}", json={"name": "x"})).status_code == 404  # an id from another list
    duplicate = await client.patch(url, json={"name": "hr head"})
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_deactivate_hides_from_recruiters_and_reactivate_restores(client, db_session):
    """AC2: deactivated, never deleted -- a recruiter's read (the picker) no longer offers it; the manager still sees it."""
    tag = uuid.uuid4().hex[:8]
    await as_role(client, db_session, "placement_manager", "global")
    live = (await _create(client, "candidate-sources", name=f"Live {tag}")).json()
    gone = (await _create(client, "candidate-sources", name=f"Gone {tag}")).json()
    deactivated = await client.patch(f"{BASE}/candidate-sources/{gone['id']}", json={"active": False})
    assert deactivated.status_code == 200 and deactivated.json()["active"] is False

    async def listed(params):
        return {r["name"] for r in (await client.get(f"{BASE}/candidate-sources", params={"q": tag, **params})).json()["items"]}

    assert await listed({}) == {live["name"], gone["name"]}
    assert await listed({"active": "false"}) == {gone["name"]}
    await _as_recruiter(client, db_session)
    assert await listed({}) == {live["name"]}
    assert await listed({"active": "false"}) == set()  # `active` cannot widen a recruiter's view
    await as_role(client, db_session, "placement_manager", "global")
    assert (await client.patch(f"{BASE}/candidate-sources/{gone['id']}", json={"active": True})).json()["active"] is True


@pytest.mark.asyncio
async def test_delete_is_not_offered(client, db_session):
    await as_role(client, db_session, "placement_manager", "global")
    created = (await _create(client, "industries")).json()
    assert (await client.delete(f"{BASE}/industries/{created['id']}")).status_code == 405


# --- who (AC3, C3) --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recruiter_reads_but_cannot_write(client, db_session):
    """AC3 + the backlog's negative scenario: a recruiter calls POST → 403."""
    await _as_recruiter(client, db_session)
    assert (await client.get(f"{BASE}/lead-sources")).status_code == 200
    refused = await _create(client)
    assert refused.status_code == 403 and refused.json()["detail"] == "Placement manager role required"
    seeded = (await _all(client, "lead-sources"))[0]["id"]
    assert (await client.patch(f"{BASE}/lead-sources/{seeded}", json={"name": "x"})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), OUTSIDERS)
async def test_other_roles_can_neither_read_nor_write(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    response = await client.get(f"{BASE}/lead-sources")
    assert response.status_code == 403 and response.json()["detail"] == "Your role cannot view the recruiter catalogues"
    assert (await _create(client)).status_code == 403


@pytest.mark.asyncio
async def test_list_shape_search_and_paging(client, db_session):
    await _as_recruiter(client, db_session)
    body = (await client.get(f"{BASE}/job-categories", params={"q": "ing", "limit": 1})).json()
    assert set(body) == {"items", "total", "limit", "offset"} and body["limit"] == 1 and len(body["items"]) == 1
    assert body["items"][0]["name"] == "Marketing" and body["total"] >= 2  # Marketing, Engineering in seed order
    assert (await client.get(f"{BASE}/job-categories", params={"limit": 101})).status_code == 422


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(f"{BASE}/lead-sources")).status_code == 401
