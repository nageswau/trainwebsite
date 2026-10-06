"""bdm-005 -- create, read and change an organization's MoU (spec §6.2-§6.4; AC1, AC2, AC7 create half, Review Focus 1)."""

import logging

import pytest

from app.services import bdm_mous as svc
from tests.bdm002_helpers import ORGS, create_org
from tests.bdm005_helpers import audits, change, events, mou_url, start, started, world

ACTIVE = {"signed_on": "2026-01-10", "valid_from": "2026-01-15", "valid_until": "2099-01-14"}


def _field(response, field: str) -> str:
    assert response.status_code == 422, response.text
    errors = [e for e in response.json()["detail"] if e["loc"][-1] == field]
    assert errors, response.json()
    return errors[0]["msg"]


@pytest.mark.asyncio
async def test_no_mou_yet_reads_null_and_the_owner_may_start_one(client, db_session):
    w = await world(client, db_session)
    response = await client.get(mou_url(w["org"]["id"]))
    assert response.status_code == 200 and response.json() == {"current": None, "can_start": True}


@pytest.mark.asyncio
async def test_create_records_one_event_and_one_audit_row(client, db_session):
    w = await world(client, db_session)
    mou = await started(client, w["org"], reference="MOU-2026-014", notes="Met the dean")
    assert (mou["status"], mou["status_label"], mou["is_current"], mou["reference"]) == ("prospect", "Prospect", True, "MOU-2026-014")
    assert mou["organization"] == {"id": w["org"]["id"], "code": w["org"]["code"], "name": w["org"]["name"], "bdm_type": "college"}
    assert mou["created_by"]["id"] == str(w["owner"].id) and mou["assigned_bdm"]["id"] == str(w["owner"].id)
    assert mou["permissions"] == {"can_edit": True, "can_upload": True, "can_renew": False}
    assert mou["document"] is None and mou["has_document"] is False and mou["expired_on"] is None
    [event] = await events(db_session, mou["id"])
    assert (event.kind, event.from_status, event.to_status, event.actor_user_id) == ("created", None, "prospect", w["ids"]["owner"])
    [audit] = await audits(db_session, mou["id"], "created")
    assert audit.metadata_json == {"org_id": w["org"]["id"], "status": "prospect"}
    assert (await client.get(mou_url(w["org"]["id"]))).json() == {"current": mou, "can_start": False}


@pytest.mark.asyncio
async def test_a_second_create_is_409(client, db_session):
    w = await world(client, db_session)
    await started(client, w["org"])
    response = await start(client, w["org"])
    assert response.status_code == 409 and response.json()["detail"]["code"] == "mou_exists"


@pytest.mark.asyncio
async def test_a_status_change_is_recorded_with_actor_and_time(client, db_session):
    w = await world(client, db_session)
    mou = await started(client, w["org"])
    response = await change(client, w["org"], status="under_negotiation", from_status="prospect")
    assert response.status_code == 200, response.text
    body = response.json()["mou"]
    assert body["status"] == "under_negotiation" and body["status_changed_at"] >= mou["status_changed_at"]
    last = (await events(db_session, mou["id"]))[-1]
    assert (last.kind, last.from_status, last.to_status, last.actor_user_id, last.changed) == ("status", "prospect", "under_negotiation", w["ids"]["owner"], ["status"])
    assert last.created_at is not None
    [audit] = await audits(db_session, mou["id"], "status_changed")
    assert audit.metadata_json == {"org_id": w["org"]["id"], "from": "prospect", "to": "under_negotiation", "changed": ["status"]}


@pytest.mark.asyncio
async def test_a_field_edit_is_recorded_by_field_name_only(client, db_session, caplog):
    w = await world(client, db_session)
    mou = await started(client, w["org"])
    caplog.set_level(logging.INFO)
    response = await change(client, w["org"], notes="Confidential pricing 12%", reference="MOU-77")
    assert response.status_code == 200 and response.json()["mou"]["notes"] == "Confidential pricing 12%"
    last = (await events(db_session, mou["id"]))[-1]
    assert (last.kind, last.from_status, last.to_status, sorted(last.changed)) == ("updated", "prospect", "prospect", ["notes", "reference"])
    [audit] = await audits(db_session, mou["id"], "updated")
    assert "12%" not in str(audit.metadata_json) and "MOU-77" not in str(audit.metadata_json)
    assert "12%" not in caplog.text and "MOU-77" not in caplog.text


@pytest.mark.asyncio
async def test_an_empty_patch_changes_nothing_and_records_nothing(client, db_session):
    w = await world(client, db_session)
    mou = await started(client, w["org"], notes="x")
    response = await change(client, w["org"], notes="x")
    assert response.status_code == 200
    assert [e.kind for e in await events(db_session, mou["id"])] == ["created"]


@pytest.mark.asyncio
async def test_a_stale_from_status_is_409_with_the_current_status(client, db_session):
    w = await world(client, db_session)
    await started(client, w["org"])
    await change(client, w["org"], status="discussion_started", from_status="prospect")
    response = await change(client, w["org"], status="proposal_sent", from_status="prospect")
    assert response.status_code == 409
    assert response.json()["detail"] == {"message": "This MoU moved to Discussion Started meanwhile", "code": "mou_status_changed", "current_status": "discussion_started"}


@pytest.mark.asyncio
async def test_the_same_status_is_422(client, db_session):
    w = await world(client, db_session)
    await started(client, w["org"])
    assert _field(await change(client, w["org"], status="prospect", from_status="prospect"), "status") == "The MoU is already at this status"


@pytest.mark.asyncio
async def test_signed_and_active_need_their_dates(client, db_session):
    w = await world(client, db_session)
    await started(client, w["org"])
    assert _field(await change(client, w["org"], status="signed", from_status="prospect"), "signed_on") == "Add the signed date"
    assert _field(await change(client, w["org"], status="active", from_status="prospect", signed_on="2026-01-10"), "valid_from") == "Add the validity window"
    assert _field(await change(client, w["org"], status="active", from_status="prospect", signed_on="2026-01-10", valid_from="2026-01-10"), "valid_until") == "Add the validity window"
    window = {"valid_from": "2026-02-01", "valid_until": "2026-01-31"}
    assert _field(await change(client, w["org"], **window), "valid_until") == "Valid-until can't be before valid-from"
    fresh = await create_org(client)
    assert _field(await start(client, fresh, status="signed"), "signed_on") == "Add the signed date"


@pytest.mark.asyncio
async def test_clearing_a_required_date_on_an_active_mou_is_422(client, db_session):
    """Review Focus 1: the rules run on the merged state, so a PATCH sending only `signed_on: null` is refused."""
    w = await world(client, db_session)
    await started(client, w["org"], status="active", **ACTIVE)
    assert _field(await change(client, w["org"], signed_on=None), "signed_on") == "Add the signed date"
    assert _field(await change(client, w["org"], valid_until=None), "valid_until") == "Add the validity window"


@pytest.mark.asyncio
async def test_proposal_sent_defaults_its_date_to_today(client, db_session):
    w = await world(client, db_session)
    await started(client, w["org"])
    body = (await change(client, w["org"], status="proposal_sent", from_status="prospect")).json()["mou"]
    assert body["proposal_sent_on"] == svc.today().isoformat()
    kept = (await change(client, w["org"], status="draft_shared", from_status="proposal_sent")).json()["mou"]
    assert kept["proposal_sent_on"] == svc.today().isoformat()


@pytest.mark.asyncio
async def test_a_patch_without_an_mou_is_404(client, db_session):
    w = await world(client, db_session)
    response = await change(client, w["org"], notes="x")
    assert response.status_code == 404 and response.json()["detail"] == "No MoU yet"


@pytest.mark.asyncio
async def test_rejected_reopens_by_moving_on(client, db_session):
    w = await world(client, db_session)
    await started(client, w["org"], status="rejected")
    response = await change(client, w["org"], status="discussion_started", from_status="rejected")
    assert response.status_code == 200 and response.json()["mou"]["status"] == "discussion_started"


@pytest.mark.asyncio
async def test_archived_and_lost_organizations_refuse_mou_writes(client, db_session):
    w = await world(client, db_session)
    await started(client, w["org"])
    await client.post(f"{ORGS}/{w['org']['id']}/lost", json={"reason": "No budget"})
    lost = await change(client, w["org"], notes="x")
    assert lost.status_code == 409 and lost.json()["detail"]["code"] == "organization_lost"
    assert (await client.get(mou_url(w["org"]["id"]))).json()["current"]["permissions"]["can_edit"] is False
    await client.post(f"{ORGS}/{w['org']['id']}/revive", json={"reason": "Budget back"})
    await client.post(f"{ORGS}/{w['org']['id']}/archive")
    archived = await change(client, w["org"], notes="x")
    assert archived.status_code == 409 and archived.json()["detail"] == "Restore this organization first"
