"""upc-032 -- partnership manager deactivation + bulk reassignment (spec §2 RA1-RA12; backlog AC, P1, N1, E1)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, PartnershipTask, University, UniversityAssignmentHistory, User
from app.services.bdm_travel import india_today
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, url

REASSIGN = "/api/v1/partnership/head/reassign"
TEAM = "/api/v1/partnership/head/team"
USERS = "/api/v1/admin/users"


async def _universities(client, db, n: int, *, primary: User | None = None, backup: User | None = None) -> list[UUID]:
    """n universities created by the signed-in caller, then owned directly (the assign route is upc-003's, tested there)."""
    country = await catalogue_country(db)
    ids = [UUID((await create(client, country.id))["id"]) for _ in range(n)]
    await db.execute(update(University).where(University.id.in_(ids)).values(primary_manager_user_id=primary.id if primary else None, backup_manager_user_id=backup.id if backup else None))
    await db.commit()
    return ids


async def _task(db, university_id: UUID, assignee: User, creator: User, status: str = "open") -> PartnershipTask:
    task = PartnershipTask(
        university_id=university_id,
        kind="task",
        title="Send brochure",
        assignee_user_id=assignee.id,
        created_by_user_id=creator.id,
        due_on=india_today() + timedelta(days=3),
        status=status,
        source="manual",
        completed_at=datetime.now(UTC) if status == "done" else None,
        cancelled_at=datetime.now(UTC) if status == "cancelled" else None,
        cancel_reason="No longer needed" if status == "cancelled" else None,
    )
    db.add(task)
    await db.commit()
    return task


async def _team(client, db):
    """A head with two managers; signed in as the head."""
    head = await make_head(db)
    a, b = await make_pm(db, head), await make_pm(db, head)
    await login(client, head)
    return head, a, b


async def _reassign(client, source: User, target_id, expected: int = 200) -> dict:
    response = await client.post(REASSIGN, json={"from_user_id": str(source.id), "to_user_id": str(target_id)})
    assert response.status_code == expected, response.text
    return response.json()


async def _owners(db, ids: list[UUID]) -> set[tuple]:
    rows = (await db.execute(select(University.primary_manager_user_id, University.backup_manager_user_id).where(University.id.in_(ids)))).all()
    return {tuple(r) for r in rows}


async def _deactivate(client, db, manager: User, expected: int) -> dict:
    await as_role(client, db, "super_admin", "global")
    response = await client.patch(f"{USERS}/{manager.id}", json={"active": False})
    assert response.status_code == expected, response.text
    return response.json()


# --- deactivation pre-check (RA1-RA3, RA12) --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deactivating_a_primary_manager_is_refused_with_the_count(client, db_session):
    _, a, _ = await _team(client, db_session)
    await _universities(client, db_session, 2, primary=a)
    body = await _deactivate(client, db_session, a, 422)
    assert body["detail"] == ("This manager is the primary manager of 2 universities. A partnership head must reassign them (Team page) before deactivation.")
    await db_session.refresh(a)
    assert a.active is True


@pytest.mark.asyncio
async def test_overseas_admin_gets_the_same_refusal(client, db_session):
    _, a, _ = await _team(client, db_session)
    await _universities(client, db_session, 1, primary=a)
    await as_role(client, db_session, "overseas_admin", "overseas")
    response = await client.patch(f"{USERS}/{a.id}", json={"active": False})
    assert response.status_code == 422 and "primary manager of 1 university." in response.json()["detail"]


@pytest.mark.asyncio
async def test_backup_slots_and_open_tasks_do_not_block_deactivation(client, db_session):
    head, a, b = await _team(client, db_session)
    [uni] = await _universities(client, db_session, 1, primary=b, backup=a)
    await _task(db_session, uni, a, head)
    await _deactivate(client, db_session, a, 200)
    await db_session.refresh(a)
    assert a.active is False


@pytest.mark.asyncio
async def test_deactivation_succeeds_after_reassignment_and_reactivation_is_unchanged(client, db_session):
    _, a, b = await _team(client, db_session)
    await _universities(client, db_session, 1, primary=a)
    await _reassign(client, a, b.id)
    await _deactivate(client, db_session, a, 200)
    response = await client.patch(f"{USERS}/{a.id}", json={"active": True})
    assert response.status_code == 200, response.text


# --- reassign (RA5-RA10) --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_head_moves_primary_backup_and_open_tasks_with_history(client, db_session):
    head, a, b = await _team(client, db_session)
    other = await make_pm(db_session, head)
    primary_ids = await _universities(client, db_session, 2, primary=a, backup=other)
    backup_ids = await _universities(client, db_session, 1, primary=other, backup=a)
    open_task = await _task(db_session, primary_ids[0], a, head)
    done_task = await _task(db_session, primary_ids[0], a, head, status="done")
    body = await _reassign(client, a, b.id)
    assert body == {"from_user_id": str(a.id), "to_user_id": str(b.id), "moved": {"primary": 2, "backup": 1, "tasks": 1}}
    assert await _owners(db_session, primary_ids) == {(b.id, other.id)}
    assert await _owners(db_session, backup_ids) == {(other.id, b.id)}
    assignee = select(PartnershipTask.assignee_user_id).where
    assert await db_session.scalar(assignee(PartnershipTask.id == open_task.id)) == b.id
    assert await db_session.scalar(assignee(PartnershipTask.id == done_task.id)) == a.id  # history stays
    history = (
        await db_session.execute(
            select(
                UniversityAssignmentHistory.university_id,
                UniversityAssignmentHistory.slot,
                UniversityAssignmentHistory.from_user_id,
                UniversityAssignmentHistory.to_user_id,
                UniversityAssignmentHistory.actor_user_id,
            ).where(UniversityAssignmentHistory.university_id.in_(primary_ids + backup_ids))
        )
    ).all()
    assert sorted(history, key=str) == sorted([*((u, "primary", a.id, b.id, head.id) for u in primary_ids), (backup_ids[0], "backup", a.id, b.id, head.id)], key=str)
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == head.id, AuditLog.action.in_(("university.assign", "partnership_task.reassign", "partnership.reassign"))))).all()
    by_action = {}
    for row in audits:
        by_action.setdefault(row.action, []).append(row)
    assert len(by_action["university.assign"]) == 3
    assert by_action["university.assign"][0].metadata_json["reason"] == "reassign"
    assert [(r.entity_id, r.metadata_json) for r in by_action["partnership_task.reassign"]] == [(str(open_task.id), {"assignee": [str(a.id), str(b.id)]})]
    [summary] = by_action["partnership.reassign"]
    assert summary.entity_id == str(a.id) and summary.metadata_json == {"to_user_id": str(b.id), "moved": {"primary": 2, "backup": 1, "tasks": 1}}


@pytest.mark.asyncio
async def test_forty_universities_move_in_one_call(client, db_session):
    _, a, b = await _team(client, db_session)
    ids = await _universities(client, db_session, 40, primary=a)
    assert (await _reassign(client, a, b.id))["moved"] == {"primary": 40, "backup": 0, "tasks": 0}
    assert await _owners(db_session, ids) == {(b.id, None)}


@pytest.mark.asyncio
async def test_target_already_backup_becomes_primary_and_the_backup_is_cleared(client, db_session):
    _, a, b = await _team(client, db_session)
    ids = await _universities(client, db_session, 1, primary=a, backup=b)
    await _reassign(client, a, b.id)
    assert await _owners(db_session, ids) == {(b.id, None)}
    slots = (
        await db_session.execute(
            select(UniversityAssignmentHistory.slot, UniversityAssignmentHistory.from_user_id, UniversityAssignmentHistory.to_user_id).where(UniversityAssignmentHistory.university_id == ids[0])
        )
    ).all()
    assert sorted(slots) == sorted([("primary", a.id, b.id), ("backup", b.id, None)])


@pytest.mark.asyncio
async def test_source_backup_where_target_is_primary_clears_the_backup(client, db_session):
    _, a, b = await _team(client, db_session)
    ids = await _universities(client, db_session, 1, primary=b, backup=a)
    assert (await _reassign(client, a, b.id))["moved"] == {"primary": 0, "backup": 1, "tasks": 0}
    assert await _owners(db_session, ids) == {(b.id, None)}


@pytest.mark.asyncio
async def test_inactive_source_and_inactive_university_are_handed_over(client, db_session):
    _, a, b = await _team(client, db_session)
    ids = await _universities(client, db_session, 1, backup=None, primary=a)
    await db_session.execute(update(University).where(University.id == ids[0]).values(active=False))
    await db_session.execute(update(User).where(User.id == a.id).values(active=False))
    await db_session.commit()
    assert (await _reassign(client, a, b.id))["moved"]["primary"] == 1
    assert await _owners(db_session, ids) == {(b.id, None)}


@pytest.mark.asyncio
async def test_after_reassignment_the_old_manager_cannot_edit(client, db_session):
    _, a, b = await _team(client, db_session)
    [uni] = await _universities(client, db_session, 1, primary=a)
    await _reassign(client, a, b.id)
    await login(client, a)
    response = await client.patch(url(uni), json={"city": "Leeds"})
    assert response.status_code == 403, response.text
    await login(client, b)
    assert (await client.patch(url(uni), json={"city": "Leeds"})).status_code == 200


@pytest.mark.asyncio
async def test_super_admin_reassigns_across_heads(client, db_session):
    _, a, _ = await _team(client, db_session)
    other_head = await make_head(db_session)
    c = await make_pm(db_session, other_head)
    ids = await _universities(client, db_session, 1, primary=a)
    await as_role(client, db_session, "super_admin", "global")
    assert (await _reassign(client, a, c.id))["moved"]["primary"] == 1
    assert await _owners(db_session, ids) == {(c.id, None)}


# --- refusals (RA4, RA9) --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_target_outside_the_team_inactive_or_same_is_422(client, db_session):
    head, a, _ = await _team(client, db_session)
    ids = await _universities(client, db_session, 1, primary=a)
    outsider = await make_pm(db_session, await make_head(db_session))
    inactive = await make_pm(db_session, head, active=False)
    for target in (outsider.id, inactive.id, a.id, head.id, uuid4()):
        body = await _reassign(client, a, target, 422)
        assert body["detail"] == "Choose an active partnership manager from your team"
    assert await _owners(db_session, ids) == {(a.id, None)}


@pytest.mark.asyncio
async def test_source_outside_the_team_is_403_and_unknown_is_404(client, db_session):
    _, _, b = await _team(client, db_session)
    stranger = await make_pm(db_session, await make_head(db_session))
    assert (await _reassign(client, stranger, b.id, 403))["detail"] == "This manager is not in your team"
    response = await client.post(REASSIGN, json={"from_user_id": str(uuid4()), "to_user_id": str(b.id)})
    assert response.status_code == 404 and response.json()["detail"] == "Partnership manager not found"


@pytest.mark.asyncio
async def test_nothing_to_move_is_409(client, db_session):
    _, a, b = await _team(client, db_session)
    assert (await _reassign(client, a, b.id, 409))["detail"] == "This manager has no universities or open tasks to reassign"


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("overseas_admin", "overseas"), ("partnership_manager", "overseas"), ("counselor", "overseas")])
async def test_other_roles_are_403(client, db_session, role, division):
    _, a, b = await _team(client, db_session)
    if role == "partnership_manager":
        await login(client, a)
    else:
        await as_role(client, db_session, role, division)
    assert (await _reassign(client, a, b.id, 403))["detail"] == "Partnership head role required"


@pytest.mark.asyncio
async def test_signed_out_is_401_and_extra_keys_are_422(client, db_session):
    _, a, b = await _team(client, db_session)
    response = await client.post(REASSIGN, json={"from_user_id": str(a.id), "to_user_id": str(b.id), "tasks": False})
    assert response.status_code == 422
    client.cookies.clear()
    assert (await client.post(REASSIGN, json={"from_user_id": str(a.id), "to_user_id": str(b.id)})).status_code == 401


# --- team rows (RA14) -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_team_rows_carry_each_managers_work(client, db_session):
    head, a, b = await _team(client, db_session)
    [uni] = await _universities(client, db_session, 1, primary=a, backup=b)
    await _universities(client, db_session, 2, primary=a)
    await _task(db_session, uni, b, head)
    await _task(db_session, uni, b, head, status="cancelled")
    rows = {r["id"]: r for r in (await client.get(TEAM)).json()["items"]}
    assert rows[str(a.id)]["work"] == {"primary": 3, "backup": 0, "tasks": 0}
    assert rows[str(b.id)]["work"] == {"primary": 0, "backup": 1, "tasks": 1}
