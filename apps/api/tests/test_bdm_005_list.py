"""bdm-005 -- the MoU list and an MoU's history (spec §6.3; AC1 history, AC3 filter). The test database is shared, so every list
assertion narrows to this test's own organizations."""

import uuid
from datetime import date

import pytest

from app.services import bdm_mous as svc
from tests.bdm001_helpers import login
from tests.bdm002_helpers import create_org
from tests.bdm005_helpers import MOUS, change, started, world

PAST = {"status": "active", "signed_on": "2025-10-01", "valid_from": "2025-10-01", "valid_until": "2026-10-05"}


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(svc, "today", lambda: date(2026, 10, 6))


async def _list(client, **params) -> dict:
    response = await client.get(MOUS, params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_rows_carry_the_organization_and_the_assigned_bdm(client, db_session):
    w = await world(client, db_session)
    mou = await started(client, w["org"], reference="MOU-9")
    [row] = (await _list(client, organization=w["org"]["id"]))["items"]
    assert row["id"] == mou["id"] and row["organization"]["code"] == w["org"]["code"]
    assert row["assigned_bdm"]["id"] == str(w["ids"]["owner"]) and row["status_label"] == "Prospect"
    assert (row["reference"], row["has_document"], row["is_current"]) == ("MOU-9", False, True)
    assert "notes" not in row and "document_key" not in row


@pytest.mark.asyncio
async def test_the_list_follows_organization_scope(client, db_session):
    w = await world(client, db_session)
    await started(client, w["org"])
    for actor, visible in (("peer", 1), ("manager", 1), ("super_admin", 1), ("other_type", 0), ("other_manager", 0)):
        await login(client, w[actor])
        assert (await _list(client, organization=w["org"]["id"]))["total"] == visible, actor
    await login(client, w["it_admin"])
    assert (await client.get(MOUS)).status_code == 403


@pytest.mark.asyncio
async def test_the_status_filter_uses_the_derived_status(client, db_session, frozen):
    w = await world(client, db_session)
    expired = await started(client, w["org"], **PAST)
    other = await create_org(client)
    live = await started(client, other, **{**PAST, "valid_until": "2027-01-01"})
    ids = {expired["id"], live["id"]}

    async def found(status: str) -> set[str]:
        return {r["id"] for r in (await _list(client, status=status, limit=100))["items"]} & ids

    assert await found("expired") == {expired["id"]}
    assert await found("active") == {live["id"]}
    [row] = (await _list(client, organization=w["org"]["id"]))["items"]
    assert row["status"] == "expired"
    assert (await client.get(MOUS, params={"status": "bogus"})).status_code == 422


@pytest.mark.asyncio
async def test_previous_mous_are_listed_with_current_false(client, db_session):
    w = await world(client, db_session)
    old = await started(client, w["org"], status="rejected")
    new = await started(client, w["org"])
    assert [r["id"] for r in (await _list(client, organization=w["org"]["id"]))["items"]] == [new["id"]]
    assert [r["id"] for r in (await _list(client, organization=w["org"]["id"], current="false"))["items"]] == [old["id"]]


@pytest.mark.asyncio
async def test_pagination(client, db_session):
    w = await world(client, db_session)
    await started(client, w["org"])
    page = await _list(client, organization=w["org"]["id"], limit=1, offset=0)
    assert (page["total"], page["limit"], page["offset"], len(page["items"])) == (1, 1, 0, 1)
    assert (await _list(client, organization=w["org"]["id"], offset=1))["items"] == []
    assert (await client.get(MOUS, params={"limit": 0})).status_code == 422


@pytest.mark.asyncio
async def test_history_lists_every_change_with_actor_and_labels(client, db_session):
    w = await world(client, db_session)
    mou = await started(client, w["org"])
    await change(client, w["org"], status="proposal_sent", from_status="prospect")
    await change(client, w["org"], notes="x")
    page = (await client.get(f"{MOUS}/{mou['id']}/history")).json()
    assert page["total"] == 3
    assert [(e["kind"], e["from_status"], e["to_status"]) for e in page["items"]] == [
        ("updated", "proposal_sent", "proposal_sent"),
        ("status", "prospect", "proposal_sent"),
        ("created", None, "prospect"),
    ]
    status = page["items"][1]
    assert (status["from_label"], status["to_label"], status["actor"]["id"]) == ("Prospect", "Proposal Sent", str(w["ids"]["owner"]))
    assert status["changed"] == ["proposal_sent_on", "status"]
    assert "document_key" not in str(page)


@pytest.mark.asyncio
async def test_history_is_scoped(client, db_session):
    w = await world(client, db_session)
    mou = await started(client, w["org"])
    await login(client, w["manager"])
    assert (await client.get(f"{MOUS}/{mou['id']}/history")).status_code == 200
    await login(client, w["other_type"])
    assert (await client.get(f"{MOUS}/{mou['id']}/history")).json() == {"detail": "MoU not found"}
    assert (await client.get(f"{MOUS}/{uuid.uuid4()}/history")).json() == {"detail": "MoU not found"}
