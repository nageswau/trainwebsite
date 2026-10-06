"""tel-004 browser QA-02: the portal workspace lead tables (admin "Leads", counselor "My Leads" and dashboard) show the pipeline stage
by its label ("First Call Pending"), not its key ("first_call_pending")."""

import pytest

from tests.tel004_helpers import lead, login, make_user


def stage_column(body: dict) -> None:
    assert {"key": "status", "label": "Stage"} in body["columns"]


@pytest.mark.asyncio
async def test_the_admin_leads_workspace_shows_stage_labels(client, db_session):
    row = await lead(db_session, status="first_call_pending")
    await login(client, await make_user(db_session, "it_admin", "it"))
    body = (await client.get("/api/v1/portal/it/admin/leads")).json()
    stage_column(body)
    assert next(r for r in body["rows"] if r["id"] == str(row.id))["status"] == "First Call Pending"


@pytest.mark.asyncio
@pytest.mark.parametrize(("division", "section"), [("overseas", "leads"), ("it", "leads"), ("it", "dashboard")])
async def test_the_counselor_workspace_shows_stage_labels(client, db_session, division, section):
    counselor = await make_user(db_session, "counselor", division)
    row = await lead(db_session, division=division, status="follow_up")
    row.owner_id = counselor.id
    await db_session.commit()
    await login(client, counselor)
    body = (await client.get(f"/api/v1/portal/{division}/counselor/{section}")).json()
    stage_column(body)
    assert [r["status"] for r in body["rows"]] == ["Follow-up"]
