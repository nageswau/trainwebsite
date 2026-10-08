"""rec-002 -- recruiter campaigns (spec §4; AC2, AC3, AC6; DEC-SCOPE-117). Names are unique per test (shared database)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.rec001_helpers import as_role, login, make_recruiter

BASE = "/api/v1/recruiter/catalogue"
CAMPAIGNS, SOURCES = f"{BASE}/campaigns", f"{BASE}/lead-sources"


def _name(prefix: str = "Camp") -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


async def _manager(client, db):
    return await as_role(client, db, "placement_manager", "global")


async def _source(client, *, active=True) -> dict:
    source = (await client.post(SOURCES, json={"name": _name("Src")})).json()
    if not active:
        source = (await client.patch(f"{SOURCES}/{source['id']}", json={"active": False})).json()
    return source


async def _create(client, source_id, **body):
    payload = {"name": _name(), "lead_source_id": str(source_id), "start_date": "2026-09-01", **body}
    return await client.post(CAMPAIGNS, json=payload)


@pytest.mark.asyncio
async def test_create_a_campaign_and_audit_it(client, db_session):
    user = await _manager(client, db_session)
    linkedin = (await client.get(SOURCES, params={"q": "LinkedIn"})).json()["items"][0]
    name = _name("Q4 IT hiring push")
    response = await _create(client, linkedin["id"], name=name, start_date="2026-10-01", end_date="2026-12-31")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body == {
        "id": body["id"],
        "name": name,
        "start_date": "2026-10-01",
        "end_date": "2026-12-31",
        "active": True,
        "lead_source": {"id": linkedin["id"], "name": "LinkedIn", "active": True},
    }
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"]))
    assert audit.action == "recruiter.catalogue_create" and audit.user_id == user.id and audit.entity_type == "rec_campaigns"
    assert sorted(audit.metadata_json["fields"]) == ["end_date", "lead_source_id", "name", "start_date"]


@pytest.mark.asyncio
async def test_end_date_is_optional_but_not_before_the_start(client, db_session):
    """AC6."""
    await _manager(client, db_session)
    source = await _source(client)
    assert (await _create(client, source["id"])).json()["end_date"] is None
    refused = await _create(client, source["id"], start_date="2026-09-30", end_date="2026-09-01")
    assert refused.status_code == 422 and refused.json()["detail"] == "End date cannot be before the start date"
    assert (await _create(client, source["id"], start_date="2026-09-01", end_date="2026-09-01")).status_code == 201


@pytest.mark.asyncio
async def test_lead_source_must_exist_and_be_active(client, db_session):
    """AC6: a deactivated source is gone from pickers, so a new campaign cannot take it."""
    await _manager(client, db_session)
    for source_id in ((await _source(client, active=False))["id"], uuid.uuid4()):
        response = await _create(client, source_id)
        assert response.status_code == 422 and response.json()["detail"] == "Choose an active lead source"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"name": "  "}, "Name is required"),
        ({"name": "x" * 161}, "Name must be at most 160 characters"),
        ({"start_date": None}, "Start date"),
        ({"start_date": "01/09/2026"}, "Start date"),
        ({"lead_source_id": "nope"}, "Lead source: choose one from the list"),
        ({"product_id": "x"}, "Unknown field"),
    ],
)
async def test_create_validation(client, db_session, body, message):
    await _manager(client, db_session)
    response = await _create(client, (await _source(client))["id"], **body)
    assert response.status_code == 422
    assert message in str(response.json()["detail"])


@pytest.mark.asyncio
async def test_duplicate_name_is_409_case_insensitive(client, db_session):
    await _manager(client, db_session)
    source = await _source(client)
    name = _name()
    assert (await _create(client, source["id"], name=name)).status_code == 201
    duplicate = await _create(client, source["id"], name=name.lower())
    assert duplicate.status_code == 409 and duplicate.json()["detail"] == f"A campaign named “{name.lower()}” already exists"


@pytest.mark.asyncio
async def test_update_rename_dates_source_and_deactivate(client, db_session):
    await _manager(client, db_session)
    source, other = await _source(client), await _source(client)
    created = (await _create(client, source["id"], end_date="2026-09-30")).json()
    url = f"{CAMPAIGNS}/{created['id']}"
    renamed = await client.patch(url, json={"name": (new := _name("Renamed")), "lead_source_id": other["id"], "end_date": None})
    assert renamed.status_code == 200
    assert renamed.json() == {**created, "name": new, "end_date": None, "lead_source": {"id": other["id"], "name": other["name"], "active": True}}
    merged = await client.patch(url, json={"end_date": "2026-08-01"})  # checked on the merged row (start 2026-09-01)
    assert merged.status_code == 422 and merged.json()["detail"] == "End date cannot be before the start date"
    assert (await client.patch(url, json={"active": False})).json()["active"] is False
    assert (await client.patch(f"{CAMPAIGNS}/{uuid.uuid4()}", json={"name": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_keeping_a_since_deactivated_source_is_allowed_but_moving_to_one_is_not(client, db_session):
    """AC2: a record keeps its deactivated value."""
    await _manager(client, db_session)
    source, retired = await _source(client), await _source(client)
    created = (await _create(client, source["id"])).json()
    await client.patch(f"{SOURCES}/{source['id']}", json={"active": False})
    await client.patch(f"{SOURCES}/{retired['id']}", json={"active": False})
    kept = await client.patch(f"{CAMPAIGNS}/{created['id']}", json={"name": _name(), "lead_source_id": source["id"]})
    assert kept.status_code == 200 and kept.json()["lead_source"]["active"] is False
    moved = await client.patch(f"{CAMPAIGNS}/{created['id']}", json={"lead_source_id": retired["id"]})
    assert moved.status_code == 422 and moved.json()["detail"] == "Choose an active lead source"


@pytest.mark.asyncio
async def test_reads_filters_and_recruiters_see_active_only(client, db_session):
    tag = uuid.uuid4().hex[:8]
    await _manager(client, db_session)
    source = await _source(client)
    live = (await _create(client, source["id"], name=f"Live {tag}")).json()
    gone = (await _create(client, source["id"], name=f"Gone {tag}")).json()
    await client.patch(f"{CAMPAIGNS}/{gone['id']}", json={"active": False})

    async def listed(params):
        return [r["name"] for r in (await client.get(CAMPAIGNS, params={"q": tag, **params})).json()["items"]]

    assert await listed({}) == [live["name"], gone["name"]]  # active first
    assert await listed({"lead_source_id": source["id"]}) == [live["name"], gone["name"]]
    assert await listed({"lead_source_id": str(uuid.uuid4())}) == []
    recruiter = await make_recruiter(db_session)
    await login(client, recruiter)
    assert await listed({}) == [live["name"]]
    assert await listed({"active": "false"}) == []
    assert (await _create(client, source["id"])).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("hr_team", "it"), ("it_admin", "it"), ("telecaller_manager", "global")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(CAMPAIGNS)).status_code == 403
    assert (await client.post(CAMPAIGNS, json={})).status_code == 403
