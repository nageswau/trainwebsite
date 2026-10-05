"""bdm-004 -- the pipeline on the organization detail and stage moves (spec §6; AC1-AC4, AC7 stale, AC9, AC12)."""

import pytest
from sqlalchemy import select

from app.bdm_stages import PIPELINES
from app.models import BdmOrganization
from app.services import bdm_organizations as org_svc
from tests.bdm001_helpers import login
from tests.bdm002_helpers import ORGS, create_org
from tests.bdm003_helpers import bdm_of
from tests.bdm004_helpers import audits, events, move

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


def _field(response, field: str) -> str:
    assert response.status_code == 422, response.text
    errors = [e for e in response.json()["detail"] if e["loc"][-1] == field]
    assert errors, response.json()
    return errors[0]["msg"]


async def _college(client, db):
    await login(client, await bdm_of(db, "college"))
    return await create_org(client)


@pytest.mark.asyncio
async def test_forward_moves_may_skip_and_write_one_history_and_one_audit_row(client, db_session):
    org = await _college(client, db_session)
    response = await move(client, org, "proposal")
    assert response.status_code == 200, response.text
    p = response.json()["organization"]["pipeline"]
    assert (p["stage"], p["stage_label"]) == ("proposal", "Proposal")
    assert [s["state"] for s in p["steps"][:6]] == ["done", "done", "done", "done", "current", "upcoming"]
    [event] = await events(db_session, org["id"])
    assert (event.kind, event.from_stage, event.to_stage, event.note) == ("move", "prospect", "proposal", None)
    [audit] = await audits(db_session, org["id"], "stage_changed")
    assert audit.metadata_json == {"from": "prospect", "to": "proposal", "backward": False, "note": False}


@pytest.mark.asyncio
async def test_backward_needs_a_note(client, db_session):
    org = await _college(client, db_session)
    org = (await move(client, org, "presentation")).json()["organization"]
    assert _field(await move(client, org, "contacted"), "note") == "Add a note to move an organization back"
    assert _field(await move(client, org, "contacted", note="   "), "note") == "Add a note to move an organization back"
    response = await move(client, org, "contacted", note="Wrong stage chosen")
    assert response.status_code == 200 and response.json()["organization"]["pipeline"]["stage"] == "contacted"
    last = (await events(db_session, org["id"]))[-1]
    assert (last.from_stage, last.to_stage, last.note) == ("presentation", "contacted", "Wrong stage chosen")
    audit = (await audits(db_session, org["id"], "stage_changed"))[-1]
    assert audit.metadata_json == {"from": "presentation", "to": "contacted", "backward": True, "note": True}
    assert "Wrong stage" not in str(audit.metadata_json)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bdm_type, to_stage, message",
    [
        ("agent", "master_login_created", "This stage is set by the onboarding handover"),
        ("school", "school_onboarding", "This stage is set by the onboarding handover"),
        ("agent", "enrollments", "This step is counted from live records, not set by hand"),
        ("college", "placement", "This step is counted from live records, not set by hand"),
        ("college", "agreement_signed", "Choose a stage of this organization's pipeline"),
        ("school", "nope", "Choose a stage of this organization's pipeline"),
        ("college", "prospect", "The organization is already at this stage"),
    ],
)
async def test_stages_that_cannot_be_set_by_hand_are_422_and_write_nothing(client, db_session, bdm_type, to_stage, message):
    await login(client, await bdm_of(db_session, bdm_type))
    org = await create_org(client)
    assert _field(await move(client, org, to_stage), "to_stage") == message
    assert (await client.get(f"{ORGS}/{org['id']}")).json()["organization"]["pipeline"]["stage"] == "prospect"
    assert await events(db_session, org["id"]) == [] and await audits(db_session, org["id"], "stage_changed") == []


@pytest.mark.asyncio
async def test_a_stale_from_stage_is_409_with_the_current_stage(client, db_session):
    org = await _college(client, db_session)
    await move(client, org, "contacted")
    response = await move(client, org, "meeting", from_stage="prospect")
    assert response.status_code == 409
    assert response.json()["detail"] == {"message": "This organization moved to Contacted meanwhile", "code": "stage_changed", "current_stage": "contacted"}


@pytest.mark.asyncio
async def test_archived_organizations_are_read_only(client, db_session):
    org = await _college(client, db_session)
    assert (await client.post(f"{ORGS}/{org['id']}/archive")).status_code == 200
    response = await move(client, org, "contacted")
    assert response.status_code == 409 and response.json()["detail"] == "Restore this organization first"


@pytest.mark.asyncio
async def test_agent_status_follows_the_stage(client, db_session):
    await login(client, await bdm_of(db_session, "agent"))
    org = await create_org(client)
    org = (await move(client, org, "meeting_completed")).json()["organization"]
    assert org["pipeline"]["agent_status"] == "Meeting"
    org = (await move(client, org, "agreement_signed")).json()["organization"]
    assert org["pipeline"]["agent_status"] == "Agreement"


@pytest.mark.asyncio
async def test_a_failure_before_commit_leaves_nothing(client, db_session, monkeypatch):
    """Transaction failure: the audit write raising rolls back the stage and the history row."""
    org = await _college(client, db_session)

    def boom(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(org_svc, "audit", boom)
    with pytest.raises(RuntimeError):
        await move(client, org, "contacted")
    db_session.expire_all()
    stored = await db_session.scalar(select(BdmOrganization.pipeline_stage).where(BdmOrganization.id == org["id"]))
    assert stored == "prospect" and await events(db_session, org["id"]) == []
