"""bdm-004 -- the pipeline on the organization detail and stage moves (spec §6; AC1-AC4, AC7 stale, AC9, AC12)."""

import pytest

from app.bdm_stages import PIPELINES
from tests.bdm001_helpers import login
from tests.bdm002_helpers import ORGS, create_org
from tests.bdm003_helpers import bdm_of
from tests.bdm004_helpers import events

EXPECTED_STATE = {"manual": "upcoming", "live": "awaiting_handover", "volume": "not_tracked"}


@pytest.mark.asyncio
@pytest.mark.parametrize("bdm_type", ["agent", "school", "college"])
async def test_a_new_organization_starts_at_prospect_with_its_own_pipeline(client, db_session, bdm_type):
    await login(client, await bdm_of(db_session, bdm_type))
    org = await create_org(client)
    p = org["pipeline"]
    assert (p["stage"], p["lost"]) == ("prospect", None)
    assert p["stage_label"] == PIPELINES[bdm_type][0].label
    assert [(s["key"], s["label"], s["kind"]) for s in p["steps"]] == [tuple(s) for s in PIPELINES[bdm_type]]
    assert p["steps"][0]["state"] == "current"
    assert [s["state"] for s in p["steps"][1:]] == [EXPECTED_STATE[s.kind] for s in PIPELINES[bdm_type][1:]]
    assert p["agent_status"] == ("Prospect" if bdm_type == "agent" else None)
    assert await events(db_session, org["id"]) == []  # no history row on create (spec §5.2)
    detail = (await client.get(f"{ORGS}/{org['id']}")).json()["organization"]
    assert detail["pipeline"] == p


@pytest.mark.asyncio
async def test_list_rows_do_not_change(client, db_session):
    """AC12: only the detail gains `pipeline`."""
    await login(client, await bdm_of(db_session, "college"))
    org = await create_org(client)
    row = (await client.get(ORGS, params={"q": org["code"]})).json()["items"][0]
    assert "pipeline" not in row and set(row["permissions"]) == {"can_edit", "can_archive", "can_restore", "can_reassign"}
