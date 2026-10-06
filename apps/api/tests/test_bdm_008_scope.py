"""bdm-008 -- who reads and who writes (spec §6.6, §8; AC5; Review Focus 5)."""

import logging

import pytest

from app.models import BdmTask
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm006_helpers import bdm_with_org
from tests.bdm008_helpers import TASKS, create_task, listed


@pytest.mark.asyncio
async def test_another_bdm_gets_404_everywhere(client, db_session):
    manager, _, _ = await bdm_with_org(client, db_session)
    t = await create_task(client)
    await login(client, await make_bdm(db_session, manager))
    for method, path, body in (("PATCH", "", {"title": "x"}), ("POST", "/complete", None), ("POST", "/cancel", {"reason": "x"})):
        r = await client.request(method, f"{TASKS}/{t['id']}{path}", json=body)
        assert (r.status_code, r.json()["detail"]) == (404, "Task not found")
    assert (await listed(client))["total"] == 0


@pytest.mark.asyncio
async def test_manager_reads_the_team_and_cannot_write(client, db_session, caplog):
    manager, bdm, _ = await bdm_with_org(client, db_session)
    t = await create_task(client)
    await login(client, manager)
    page = await listed(client)
    assert [i["id"] for i in page["items"]] == [t["id"]] and not any(page["items"][0]["permissions"].values())
    assert (await listed(client, bdm_user_id=str(bdm.id)))["total"] == 1
    caplog.set_level(logging.WARNING, logger="app.bdm")
    r = await client.post(f"{TASKS}/{t['id']}/complete")
    assert (r.status_code, r.json()["detail"]) == (403, "Only the assigned BDM can change this task")
    assert "bdm_task_write_refused" in caplog.text
    row = await db_session.get(BdmTask, t["id"], populate_existing=True)
    assert row.status == "open"


@pytest.mark.asyncio
async def test_other_manager_and_filters_never_widen_scope(client, db_session):
    _, bdm, _ = await bdm_with_org(client, db_session)
    await create_task(client)
    await login(client, await make_manager(db_session))
    assert (await listed(client))["total"] == 0
    assert (await listed(client, bdm_user_id=str(bdm.id)))["total"] == 0


@pytest.mark.asyncio
async def test_super_admin_reads_all_and_other_roles_are_refused(client, db_session):
    _, bdm, _ = await bdm_with_org(client, db_session)
    t = await create_task(client)
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert t["id"] in [i["id"] for i in (await listed(client, bdm_user_id=str(bdm.id)))["items"]]
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(TASKS)).status_code == 403
