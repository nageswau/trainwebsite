"""bdm-004 -- Lost / Revive (S5; AC2, AC8)."""

import pytest

from tests.bdm001_helpers import login
from tests.bdm002_helpers import ORGS, create_org
from tests.bdm003_helpers import bdm_of
from tests.bdm004_helpers import audits, events, move, url


async def _org_at(client, db, stage: str = "proposal"):
    await login(client, await bdm_of(db, "college"))
    org = await create_org(client)
    return (await move(client, org, stage)).json()["organization"]


@pytest.mark.asyncio
async def test_lost_keeps_the_stage_and_needs_a_reason(client, db_session):
    org = await _org_at(client, db_session)
    blank = await client.post(url(org["id"], "lost"), json={"reason": "  "})
    assert blank.status_code == 422 and blank.json()["detail"][0]["loc"][-1] == "reason"
    response = await client.post(url(org["id"], "lost"), json={"reason": "No budget this year"})
    assert response.status_code == 200, response.text
    p = response.json()["organization"]["pipeline"]
    assert p["stage"] == "proposal" and p["lost"]["reason"] == "No budget this year" and p["lost"]["at"]
    last = (await events(db_session, org["id"]))[-1]
    assert (last.kind, last.from_stage, last.to_stage, last.note) == ("lost", "proposal", "proposal", "No budget this year")
    [audit] = await audits(db_session, org["id"], "lost")
    assert audit.metadata_json == {"stage": "proposal"}


@pytest.mark.asyncio
async def test_a_lost_organization_cannot_move_or_be_lost_again(client, db_session):
    org = await _org_at(client, db_session)
    await client.post(url(org["id"], "lost"), json={"reason": "Went with a competitor"})
    moved = await move(client, org, "mou_signed")
    assert moved.status_code == 409 and moved.json()["detail"]["code"] == "organization_lost"
    again = await client.post(url(org["id"], "lost"), json={"reason": "Again"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "organization_lost"


@pytest.mark.asyncio
async def test_revive_returns_to_the_same_stage(client, db_session):
    org = await _org_at(client, db_session)
    await client.post(url(org["id"], "lost"), json={"reason": "Paused"})
    assert (await client.post(url(org["id"], "revive"), json={})).status_code == 422
    response = await client.post(url(org["id"], "revive"), json={"reason": "New principal is keen"})
    assert response.status_code == 200
    p = response.json()["organization"]["pipeline"]
    assert (p["stage"], p["lost"]) == ("proposal", None)
    last = (await events(db_session, org["id"]))[-1]
    assert (last.kind, last.from_stage, last.to_stage, last.note) == ("revived", "proposal", "proposal", "New principal is keen")
    [audit] = await audits(db_session, org["id"], "revived")
    assert audit.metadata_json == {"stage": "proposal"}
    assert (await move(client, response.json()["organization"], "mou_negotiation")).status_code == 200


@pytest.mark.asyncio
async def test_revive_when_not_lost_is_409(client, db_session):
    org = await _org_at(client, db_session)
    response = await client.post(url(org["id"], "revive"), json={"reason": "x"})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "organization_not_lost"


@pytest.mark.asyncio
async def test_archived_refuses_lost_and_revive(client, db_session):
    org = await _org_at(client, db_session)
    await client.post(f"{ORGS}/{org['id']}/archive")
    for action in ("lost", "revive"):
        response = await client.post(url(org["id"], action), json={"reason": "x"})
        assert response.status_code == 409 and response.json()["detail"] == "Restore this organization first"
