"""upc-020 -- auto-generated tasks (Q-22: TK4-TK7, TK16) and the university's Next / Last Action (TK14, TK15; AC1, P1, E1, V1)."""

from uuid import UUID

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, PartnershipTask, User
from tests.test_upc_020_tasks import _owned, act, add, day, listing
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, url

VISITS = "/api/v1/partnership/visits"


async def move(client, uni_id, from_stage: str, to_stage: str, note: str | None = None) -> dict:
    response = await client.post(url(uni_id, "stage"), json={"from_stage": from_stage, "to_stage": to_stage, "note": note})
    assert response.status_code == 200, response.text
    return response.json()["university"]


async def open_tasks(db, uni_id) -> list[PartnershipTask]:
    stmt = select(PartnershipTask).where(PartnershipTask.university_id == UUID(uni_id), PartnershipTask.status == "open")
    return list((await db.scalars(stmt.order_by(PartnershipTask.created_at).execution_options(populate_existing=True))).all())


# --- AC1 / TK4-TK6 ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_proposal_sent_creates_follow_up_on_proposal_for_the_primary_manager(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    await move(client, uni["id"], "target_university", "proposal_sent")
    [task] = await open_tasks(db_session, uni["id"])
    assert (task.title, task.kind, task.priority, task.source, task.rule) == ("Follow up on proposal", "follow_up", "high", "stage", "stage:proposal_sent")
    assert task.due_on.isoformat() == day(7) and task.assignee_user_id == pm.id and task.created_by_user_id == pm.id
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(task.id)))).all()
    assert [(a.action, a.metadata_json) for a in audit] == [("partnership_task.auto_create", {"kind": "follow_up", "source": "stage", "university_id": uni["id"], "rule": "stage:proposal_sent"})]
    item = (await listing(client, band="upcoming", university_id=uni["id"]))["items"][0]
    assert item["source"] == "stage" and item["permissions"]["can_complete"]


@pytest.mark.asyncio
async def test_a_stage_without_a_rule_creates_nothing(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    await move(client, uni["id"], "target_university", "researching")
    assert await open_tasks(db_session, uni["id"]) == []


@pytest.mark.asyncio
async def test_tk6_unowned_university_goes_to_the_head_who_moved_it_and_super_admin_moves_create_nothing(client, db_session):
    head = await make_head(db_session)
    await login(client, head)
    uni = await create(client, (await catalogue_country(db_session)).id)
    await move(client, uni["id"], "target_university", "interested")
    [task] = await open_tasks(db_session, uni["id"])
    assert task.title == "Schedule meeting" and task.assignee_user_id == head.id and task.due_on.isoformat() == day(2)
    await as_role(client, db_session, "super_admin", "global")
    await move(client, uni["id"], "interested", "meeting_completed")  # no manager, a super_admin actor: skipped, the move still succeeds
    assert [t.title for t in await open_tasks(db_session, uni["id"])] == ["Schedule meeting"]


@pytest.mark.asyncio
async def test_tk6_an_inactive_primary_manager_falls_back_to_the_backup(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    response = await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id), "backup_manager_user_id": str(other.id)})
    assert response.status_code == 200, response.text
    await db_session.execute(update(User).where(User.id == pm.id).values(active=False))
    await db_session.commit()
    await move(client, uni["id"], "target_university", "initial_contact")  # the head moves it
    [task] = await open_tasks(db_session, uni["id"])
    assert task.title == "Follow up with university" and task.assignee_user_id == other.id and task.created_by_user_id == head.id


# --- E1 / TK7 ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e1_reentering_a_stage_keeps_one_open_auto_task(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    await move(client, uni["id"], "target_university", "proposal_sent")
    await move(client, uni["id"], "proposal_sent", "interested", note="They asked to restart")
    await move(client, uni["id"], "interested", "proposal_sent")
    titles = [t.title for t in await open_tasks(db_session, uni["id"])]
    assert titles == ["Follow up on proposal", "Schedule meeting"]
    first = (await open_tasks(db_session, uni["id"]))[0]
    await act(client, first.id, "complete")
    await move(client, uni["id"], "proposal_sent", "interested", note="Again")
    await move(client, uni["id"], "interested", "proposal_sent")  # the first is done, so a new one is due
    assert sorted(t.title for t in await open_tasks(db_session, uni["id"])) == ["Follow up on proposal", "Schedule meeting"]


# --- P1 / TK14, TK15 --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_p1_university_shows_next_and_last_action(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    fresh = (await client.get(url(uni["id"]))).json()["university"]
    assert fresh["follow_up"] == {"next_action": None, "last_action": None}
    await add(client, uni["id"], kind="task", title="Collect documents", due_on=day(1))  # a task, not a follow-up: never the next action
    body = await move(client, uni["id"], "target_university", "proposal_sent")
    nxt = body["follow_up"]["next_action"]
    assert nxt["title"] == "Follow up on proposal" and nxt["due_on"] == day(7) and nxt["priority"] == "high" and nxt["band"] == "upcoming"
    assert nxt["assignee"]["id"] == str(pm.id)
    assert body["follow_up"]["last_action"]["title"] == "Moved to Proposal Sent"
    call = await add(client, uni["id"], title="Follow-up call", due_on=day(3))
    assert (await client.get(url(uni["id"]))).json()["university"]["follow_up"]["next_action"]["id"] == call["id"]  # earliest open follow-up
    await act(client, call["id"], "complete")
    follow_up = (await client.get(url(uni["id"]))).json()["university"]["follow_up"]
    assert follow_up["last_action"]["title"] == "Follow-up call" and follow_up["next_action"]["title"] == "Follow up on proposal"
    await as_role(client, db_session, "overseas_admin", "overseas")  # every university reader sees the summary
    assert (await client.get(url(uni["id"]))).json()["university"]["follow_up"]["next_action"]["title"] == "Follow up on proposal"


# --- V1 / TK16 --------------------------------------------------------------------------------------------------------------------
async def _completed_visit(client, db, follow_up: int = 4):
    head, pm, _, uni = await _owned(client, db)
    await login(client, pm)
    response = await client.post(VISITS, json={"university_id": uni["id"], "purpose": "MoU talks", "proposed_date": day(0), "confirmed_date": day(0)})
    assert response.status_code == 201, response.text
    v = response.json()["visit"]
    assert (await client.post(f"{VISITS}/{v['id']}/submit")).status_code == 200
    await login(client, head)
    assert (await client.post(f"{VISITS}/{v['id']}/approve")).status_code == 200
    await login(client, pm)
    assert (await client.post(f"{VISITS}/{v['id']}/book")).status_code == 200
    response = await client.post(f"{VISITS}/{v['id']}/complete", json={"follow_up_date": day(follow_up)})
    assert response.status_code == 200, response.text
    return pm, uni, v


@pytest.mark.asyncio
async def test_v1_completing_a_visit_creates_its_follow_up_and_a_date_change_moves_it(client, db_session):
    pm, uni, v = await _completed_visit(client, db_session)
    [task] = await open_tasks(db_session, uni["id"])
    assert (task.title, task.kind, task.source, task.rule, task.priority) == ("Follow up after visit", "follow_up", "visit", f"visit:{v['id']}", "high")
    assert task.due_on.isoformat() == day(4) and task.assignee_user_id == pm.id
    response = await client.patch(f"{VISITS}/{v['id']}", json={"follow_up_date": day(6)})
    assert response.status_code == 200, response.text
    [task] = await open_tasks(db_session, uni["id"])
    assert task.due_on.isoformat() == day(6)
    await act(client, task.id, "complete")
    assert (await client.patch(f"{VISITS}/{v['id']}", json={"follow_up_date": day(8)})).status_code == 200
    done = await db_session.get(PartnershipTask, task.id, populate_existing=True)
    assert done.due_on.isoformat() == day(6)  # a done task keeps its date
