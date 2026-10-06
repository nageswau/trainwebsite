"""bdm-025 -- races (spec §5.2 step 4, §5.9). Two real sessions through the app (bdm-008 pattern)."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models import BdmAssignmentHistory, BdmOrganization
from tests.bdm001_helpers import login, make_user
from tests.bdm025_helpers import BDMS, MANAGERS, appt, org, task, team


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _two_admins(db, one: AsyncClient, two: AsyncClient) -> None:
    await login(one, await make_user(db, "super_admin", "global"))
    await login(two, await make_user(db, "super_admin", "global"))


@pytest.mark.asyncio
async def test_double_deactivate_moves_each_item_once(db_session):
    _, a, b = await team(db_session)
    orgs = [await org(db_session, a) for _ in range(3)]
    await appt(db_session, a, orgs[0])
    await task(db_session, a)
    body = {"mode": "reassign", "reassign_to": str(b.id)}
    async with _client() as one, _client() as two:
        await _two_admins(db_session, one, two)
        results = await asyncio.gather(one.post(f"{BDMS}/{a.id}/deactivate", json=body), two.post(f"{BDMS}/{a.id}/deactivate", json=body))
    assert sorted(r.status_code for r in results) == [200, 409]
    moved = await db_session.scalar(select(func.count()).select_from(BdmAssignmentHistory).where(BdmAssignmentHistory.from_user_id == a.id))
    assert moved == 5


@pytest.mark.asyncio
async def test_deactivate_and_single_reassign_do_not_deadlock(db_session):
    """Both lock the organization before the user (spec §5.2 step 4): one waits for the other, neither errors."""
    manager, a, b = await team(db_session)
    o = await org(db_session, a)
    c = (await team(db_session))[1]  # another College BDM, under a different manager
    async with _client() as one, _client() as two:
        await login(one, await make_user(db_session, "super_admin", "global"))
        await login(two, manager)
        deactivated, reassigned = await asyncio.gather(
            one.post(f"{BDMS}/{a.id}/deactivate", json={"mode": "reassign", "reassign_to": str(c.id)}),
            two.post(f"/api/v1/bdm/organizations/{o.id}/assign", json={"bdm_user_id": str(b.id)}),
        )
    assert deactivated.status_code == 200
    assert reassigned.status_code in (200, 404)  # 404: by the time it ran, the organization had left the manager's team
    owner = await db_session.scalar(select(BdmOrganization.assigned_bdm_user_id).where(BdmOrganization.id == o.id).execution_options(populate_existing=True))
    assert owner in (b.id, c.id)
    rows = await db_session.scalar(select(func.count()).select_from(BdmAssignmentHistory).where(BdmAssignmentHistory.entity_id == o.id))
    assert rows == (2 if owner == c.id and reassigned.status_code == 200 else 1)


@pytest.mark.asyncio
async def test_double_manager_deactivate(db_session):
    old, _, _ = await team(db_session)
    new = (await team(db_session))[0]
    async with _client() as one, _client() as two:
        await _two_admins(db_session, one, two)
        results = await asyncio.gather(*(c.post(f"{MANAGERS}/{old.id}/deactivate", json={"reassign_to": str(new.id)}) for c in (one, two)))
    assert sorted(r.status_code for r in results) == [200, 409]
