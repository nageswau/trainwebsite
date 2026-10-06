"""bdm-005 -- D28: Signed advances the pipeline forward only (M5; AC6)."""

import pytest

from app.bdm_stages import MOU_SIGNED_STAGE, PIPELINES
from tests.bdm002_helpers import ORGS
from tests.bdm004_helpers import audits as org_audits
from tests.bdm004_helpers import events as stage_events
from tests.bdm004_helpers import move
from tests.bdm005_helpers import change, started, world

SIGNED = {"signed_on": "2026-01-10"}
NOTE = "Advanced by MoU signed"


def _label(bdm_type: str, key: str) -> str:
    return next(s.label for s in PIPELINES[bdm_type] if s.key == key)


async def _stage(client, org_id: str) -> str:
    return (await client.get(f"{ORGS}/{org_id}")).json()["organization"]["pipeline"]["stage"]


@pytest.mark.asyncio
@pytest.mark.parametrize("bdm_type", ["agent", "school", "college"])
async def test_signing_advances_a_behind_organization_to_its_signed_stage(client, db_session, bdm_type):
    w = await world(client, db_session, bdm_type)
    target = MOU_SIGNED_STAGE[bdm_type]
    mou = await started(client, w["org"])
    assert mou["pipeline_on_sign"] == {"key": target, "label": _label(bdm_type, target)}
    response = await change(client, w["org"], status="signed", from_status="prospect", **SIGNED)
    assert response.status_code == 200, response.text
    assert response.json()["mou"]["pipeline_on_sign"] is None
    assert await _stage(client, w["org"]["id"]) == target
    [event] = await stage_events(db_session, w["org"]["id"])
    assert (event.kind, event.from_stage, event.to_stage, event.note, event.actor_user_id) == ("move", "prospect", target, NOTE, w["ids"]["owner"])
    [audit] = await org_audits(db_session, w["org"]["id"], "stage_changed")
    assert audit.metadata_json == {"from": "prospect", "to": target, "backward": False, "note": True, "source": "mou"}


@pytest.mark.asyncio
async def test_creating_an_mou_as_signed_advances_too(client, db_session):
    w = await world(client, db_session, "school")
    await started(client, w["org"], status="signed", **SIGNED)
    assert await _stage(client, w["org"]["id"]) == "signed"


@pytest.mark.asyncio
async def test_an_organization_at_or_past_the_signed_stage_does_not_move(client, db_session):
    w = await world(client, db_session, "college")
    moved = await move(client, w["org"], "college_activated")
    assert moved.status_code == 200
    mou = await started(client, w["org"])
    assert mou["pipeline_on_sign"] is None
    await change(client, w["org"], status="signed", from_status="prospect", **SIGNED)
    assert await _stage(client, w["org"]["id"]) == "college_activated"
    assert [e.kind for e in await stage_events(db_session, w["org"]["id"])] == ["move"]  # only the manual move


@pytest.mark.asyncio
async def test_active_after_signed_and_other_statuses_never_move_the_pipeline(client, db_session):
    w = await world(client, db_session, "agent")
    await started(client, w["org"], status="under_negotiation")
    assert await _stage(client, w["org"]["id"]) == "prospect"
    await change(client, w["org"], status="signed", from_status="under_negotiation", **SIGNED)
    await change(client, w["org"], status="active", from_status="signed", valid_from="2026-01-10", valid_until="2099-01-09")
    assert len(await stage_events(db_session, w["org"]["id"])) == 1
