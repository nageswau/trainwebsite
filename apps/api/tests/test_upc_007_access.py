"""upc-007 -- who may move, mark lost, reopen and read (spec PS5, PS6, PS8; N1, E1, E3)."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.upc003_helpers import as_role, make_head, make_pm, make_user, url
from tests.upc007_helpers import history, login, move, move_ok, owned_university


@pytest.mark.asyncio
async def test_backup_manager_moves(client, db_session):
    head, pm, uni = await owned_university(client, db_session)
    backup = await make_pm(db_session, head)
    await login(client, head)
    assigned = await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id), "backup_manager_user_id": str(backup.id)})
    assert assigned.status_code == 200
    await login(client, backup)
    await move_ok(client, uni["id"], "target_university", "researching")


@pytest.mark.asyncio
async def test_non_owner_manager_reads_but_cannot_move_or_mark_lost(client, db_session):
    head, _, uni = await owned_university(client, db_session)
    other = await make_pm(db_session, head)
    await login(client, other)
    body = (await client.get(url(uni["id"]))).json()["university"]
    assert body["permissions"]["can_move_stage"] is False
    assert (await move(client, uni["id"], "target_university", "interested")).status_code == 403
    assert (await client.post(url(uni["id"], "lost"), json={"reason": "x"})).status_code == 403
    assert (await client.get(url(uni["id"], "stage-history"))).status_code == 200
    assert await history(db_session, uni["id"]) == []


@pytest.mark.asyncio
async def test_overseas_admin_reads_but_cannot_move(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    await as_role(client, db_session, "overseas_admin", "overseas")
    body = (await client.get(url(uni["id"]))).json()["university"]
    assert body["permissions"]["can_move_stage"] is False and body["permissions"]["can_reopen"] is False
    assert (await move(client, uni["id"], "target_university", "interested")).status_code == 403
    assert (await client.get(url(uni["id"], "stage-history"))).status_code == 200


@pytest.mark.asyncio
async def test_head_moves_team_universities_but_not_another_teams(client, db_session):
    head, _, uni = await owned_university(client, db_session)
    await login(client, head)
    await move_ok(client, uni["id"], "target_university", "researching")
    other_head = await make_head(db_session)
    await login(client, other_head)
    assert (await move(client, uni["id"], "researching", "interested")).status_code == 403
    assert (await client.post(url(uni["id"], "lost"), json={"reason": "x"})).status_code == 403


@pytest.mark.asyncio
async def test_super_admin_moves_marks_lost_and_reopens(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    await login(client, await make_user(db_session, "super_admin", "global"))
    await move_ok(client, uni["id"], "target_university", "interested")
    assert (await client.post(url(uni["id"], "lost"), json={"reason": "Closed"})).status_code == 200
    assert (await client.post(url(uni["id"], "reopen"), json={"reason": "Reopened"})).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("overseas_student", "overseas"), ("bdm", "overseas")])
async def test_other_roles_are_refused(client, db_session, role, division):
    _, _, uni = await owned_university(client, db_session)
    await as_role(client, db_session, role, division)
    assert (await move(client, uni["id"], "target_university", "interested")).status_code == 403
    assert (await client.get(url(uni["id"], "stage-history"))).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    client.cookies.clear()
    assert (await move(client, uni["id"], "target_university", "interested")).status_code == 401


@pytest.mark.asyncio
async def test_an_inactive_university_is_read_only(client, db_session):
    head, pm, uni = await owned_university(client, db_session)
    await login(client, head)
    assert (await client.post(url(uni["id"], "deactivate"), json={})).status_code == 200
    await login(client, pm)
    response = await move(client, uni["id"], "target_university", "interested")
    assert response.status_code == 409 and response.json()["detail"] == "Reactivate this university first"
    assert (await client.get(url(uni["id"]))).json()["university"]["permissions"]["can_move_stage"] is False


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_two_moves_from_the_same_stage_one_wins(client, db_session):
    _, pm, uni = await owned_university(client, db_session)
    async with _client() as a, _client() as b:
        await login(a, pm)
        await login(b, pm)
        results = await asyncio.gather(move(a, uni["id"], "target_university", "researching"), move(b, uni["id"], "target_university", "interested"))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert len(await history(db_session, uni["id"])) == 1
