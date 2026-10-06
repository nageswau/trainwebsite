"""bdm-008 -- races (spec §7). Two real sessions through the app (bdm-006/007 pattern)."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models import BdmTask
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm006_helpers import create_appt, move_to_past
from tests.bdm007_helpers import REPORT
from tests.bdm008_helpers import TASKS, ist_day, task_body


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _logged_in(db, one: AsyncClient, two: AsyncClient) -> None:
    """Two sessions of one fresh BDM (call inside `async with` -- an httpx client opens once)."""
    bdm = await make_bdm(db, await make_manager(db))
    await login(one, bdm)
    await login(two, bdm)


@pytest.mark.asyncio
async def test_double_complete(db_session):
    async with _client() as one, _client() as two:
        await _logged_in(db_session, one, two)
        t = (await one.post(TASKS, json=task_body())).json()
        results = await asyncio.gather(one.post(f"{TASKS}/{t['id']}/complete"), two.post(f"{TASKS}/{t['id']}/complete"))
    assert sorted(r.status_code for r in results) == [200, 409]


@pytest.mark.asyncio
async def test_complete_and_report_date_edit_serialize_on_the_appointment(db_session):
    async with _client() as one, _client() as two:
        await _logged_in(db_session, one, two)
        org = await create_org(one)
        a = await create_appt(one, org)
        await move_to_past(db_session, a["id"])
        a = (await one.post(f"/api/v1/bdm/appointments/{a['id']}/complete", json={**REPORT, "next_follow_up_on": ist_day(2).isoformat()})).json()["appointment"]
        done, edit = await asyncio.gather(
            one.post(f"{TASKS}/{a['follow_up']['id']}/complete"),
            two.patch(f"/api/v1/bdm/appointments/{a['id']}/report", json={"next_follow_up_on": ist_day(4).isoformat()}),
        )
    assert done.status_code == 200 and edit.status_code in (200, 409)
    row = (await db_session.execute(select(BdmTask.status, BdmTask.due_on).where(BdmTask.id == a["follow_up"]["id"]).execution_options(populate_existing=True))).one()
    assert row.status == "done"  # never reopened or duplicated


@pytest.mark.asyncio
async def test_create_and_archive_serialize_on_the_organization(db_session):
    async with _client() as one, _client() as two:
        await _logged_in(db_session, one, two)
        org = await create_org(one)
        created, archived = await asyncio.gather(
            one.post(TASKS, json=task_body(organization_id=org["id"])), two.post(f"/api/v1/bdm/organizations/{org['id']}/archive"))
    assert archived.status_code == 200 and created.status_code in (201, 422)
    rows = (await db_session.scalars(select(BdmTask.status).where(BdmTask.organization_id == org["id"]).execution_options(populate_existing=True))).all()
    assert all(s == "cancelled" for s in rows)  # a task created first was cancelled by the archive; none is left open
