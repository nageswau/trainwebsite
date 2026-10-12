"""mgmt-028 -- management to-do + staff "Management tasks" (spec MT1-MT14; AC1-AC3)."""

import datetime
import uuid
from datetime import timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models import AuditLog, ManagementTask, Notification
from app.services import management_tasks as svc
from tests.bdm001_helpers import login, make_user

TASKS = "/api/v1/management/tasks"
MINE = "/api/v1/me/management-tasks"
TODAY = datetime.datetime.now(ZoneInfo("Asia/Kolkata")).date()


async def as_user(client, db, role: str = "partner", division: str = "global", **kwargs):
    user = await make_user(db, role, division, **kwargs)
    await login(client, user)
    return user


def body(owner_id, **overrides) -> dict:
    data = {"title": "Approve marketing budget", "owner_user_id": str(owner_id), "priority": "high", "deadline": TODAY.isoformat()}
    data.update(overrides)
    return data


async def create(client, data: dict) -> dict:
    response = await client.post(TASKS, json=data)
    assert response.status_code == 201, response.text
    return response.json()


async def notes_for(db, user_id) -> list[Notification]:
    db.expire_all()
    return list((await db.scalars(select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at))).all())


# --- AC1: bands in IST (MT3) -------------------------------------------------------------------------------------------------
WEDNESDAY = datetime.date(2026, 10, 14)


def task(deadline, status="open", completed_on=None):
    completed_at = datetime.datetime.combine(completed_on, datetime.time(12), ZoneInfo("Asia/Kolkata")) if completed_on else None
    return SimpleNamespace(deadline=deadline, status=status, completed_at=completed_at)


def test_week_ends_on_sunday_of_the_monday_to_sunday_week():
    assert svc.week_end(WEDNESDAY) == datetime.date(2026, 10, 18)
    assert svc.week_end(datetime.date(2026, 10, 12)) == datetime.date(2026, 10, 18)  # Monday
    assert svc.week_end(datetime.date(2026, 10, 18)) == datetime.date(2026, 10, 18)  # Sunday


@pytest.mark.parametrize(
    ("deadline", "expected"),
    [
        (WEDNESDAY - timedelta(days=1), "overdue"),
        (WEDNESDAY, "today"),
        (WEDNESDAY + timedelta(days=1), "week"),
        (datetime.date(2026, 10, 18), "week"),
        (datetime.date(2026, 10, 19), "later"),
    ],
)
def test_ac1_open_task_bands(deadline, expected):
    assert svc.band_of(task(deadline), WEDNESDAY) == expected
    assert svc.band_of(task(deadline, "in_progress"), WEDNESDAY) == expected


def test_ac1_on_sunday_this_week_is_only_today():
    sunday = datetime.date(2026, 10, 18)
    assert svc.band_of(task(sunday + timedelta(days=1)), sunday) == "later"


def test_completed_band_covers_the_last_seven_ist_days_and_cancelled_none():
    assert svc.band_of(task(WEDNESDAY - timedelta(days=30), "completed", WEDNESDAY - timedelta(days=6)), WEDNESDAY) == "completed"
    assert svc.band_of(task(WEDNESDAY, "completed", WEDNESDAY - timedelta(days=7)), WEDNESDAY) is None
    assert svc.band_of(task(WEDNESDAY, "cancelled"), WEDNESDAY) == "cancelled"


@pytest.mark.asyncio
async def test_ac1_list_puts_each_task_in_its_ist_band_with_counts(client, db_session):
    owner = await make_user(db_session, "trainer", "it")
    await as_user(client, db_session)
    for days, title in ((-2, "Review agent performance"), (0, "Meet university representative"), (60, "Review school proposal")):
        db_session.add(ManagementTask(title=title, owner_user_id=owner.id, priority="medium", deadline=TODAY + timedelta(days=days), created_by_user_id=owner.id, updated_by_user_id=owner.id))
    await db_session.commit()
    page = (await client.get(TASKS, params={"owner": str(owner.id)})).json()
    bands = {item["title"]: item["band"] for item in page["items"]}
    assert bands == {"Review agent performance": "overdue", "Meet university representative": "today", "Review school proposal": "later"}
    assert page["counts"]["overdue"] == 1 and page["counts"]["today"] == 1 and page["counts"]["later"] == 1
    assert page["today"] == TODAY.isoformat()
    overdue = (await client.get(TASKS, params={"owner": str(owner.id), "band": "overdue"})).json()
    assert [i["title"] for i in overdue["items"]] == ["Review agent performance"]


# --- create / edit (MT1, MT6-MT8) ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_partner_creates_a_task_for_a_staff_owner(client, db_session):
    owner = await make_user(db_session, "partnership_manager", "global", name="University BDM")
    partner = await as_user(client, db_session)
    created = await create(client, body(owner.id))
    assert created["title"] == "Approve marketing budget"
    assert created["owner"]["full_name"] == "University BDM" and created["owner_active"] is True
    assert created["priority"] == "high" and created["status"] == "open" and created["source"] == "manual"
    assert created["band"] == "today" and created["created_by"]["id"] == str(partner.id)
    assert (await client.get(f"{TASKS}/{created['id']}")).json()["id"] == created["id"]


@pytest.mark.asyncio
async def test_positive_scenario_partner_assigns_a_task_to_themselves_and_lists_my_tasks(client, db_session):
    partner = await as_user(client, db_session)
    created = await create(client, body(partner.id))
    mine = (await client.get(TASKS, params={"owner": "me"})).json()
    assert [i["id"] for i in mine["items"]] == [created["id"]]


@pytest.mark.asyncio
async def test_super_admin_may_manage_tasks_accountant_and_staff_may_not(client, db_session):
    owner = await make_user(db_session, "trainer", "it")
    await as_user(client, db_session, "super_admin")
    created = await create(client, body(owner.id))
    for role, division in (("accountant", "global"), ("bdm", "it"), ("trainer", "it")):
        await as_user(client, db_session, role, division)
        assert (await client.get(TASKS)).status_code == 403
        assert (await client.post(TASKS, json=body(owner.id))).status_code == 403
        assert (await client.patch(f"{TASKS}/{created['id']}", json={"status": "completed"})).status_code == 403
        assert (await client.get(f"{TASKS}/options")).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(TASKS)).status_code == 401
    assert (await client.get(MINE)).status_code == 401


@pytest.mark.asyncio
async def test_owner_must_be_an_active_staff_user(client, db_session):
    inactive = await make_user(db_session, "trainer", "it", active=False)
    student = await make_user(db_session, "it_student", "it")
    await as_user(client, db_session)
    for owner in (inactive, student):
        response = await client.post(TASKS, json=body(owner.id))
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "owner_user_id"]
    assert (await client.post(TASKS, json=body(uuid.uuid4()))).status_code == 422


@pytest.mark.asyncio
async def test_field_rules(client, db_session):
    owner = await make_user(db_session, "trainer", "it")
    await as_user(client, db_session)
    past = await client.post(TASKS, json=body(owner.id, deadline=(TODAY - timedelta(days=1)).isoformat()))
    assert past.status_code == 422 and past.json()["detail"][0]["loc"] == ["body", "deadline"]
    far = await client.post(TASKS, json=body(owner.id, deadline=(TODAY + timedelta(days=800)).isoformat()))
    assert far.status_code == 422
    assert (await client.post(TASKS, json=body(owner.id, title="x"))).status_code == 422
    assert (await client.post(TASKS, json=body(owner.id, priority="urgent"))).status_code == 422
    assert (await client.post(TASKS, json={**body(owner.id), "source": "decision"})).status_code == 422  # never client-set
    created = await create(client, body(owner.id))
    assert (await client.patch(f"{TASKS}/{created['id']}", json={"title": None})).status_code == 422
    assert (await client.patch(f"{TASKS}/{created['id']}", json={"deadline": None})).status_code == 422
    assert (await client.get(TASKS, params={"band": "someday"})).status_code == 422
    assert (await client.get(TASKS, params={"owner": "everyone"})).status_code == 422
    assert (await client.get(f"{TASKS}/{uuid.uuid4()}")).status_code == 404


@pytest.mark.asyncio
async def test_an_overdue_task_stays_editable_and_a_deactivated_owner_is_flagged(client, db_session):
    owner = await make_user(db_session, "trainer", "it")
    partner = await as_user(client, db_session)
    row = ManagementTask(title="Review monthly P&L", owner_user_id=owner.id, priority="low", deadline=TODAY - timedelta(days=3), created_by_user_id=partner.id, updated_by_user_id=partner.id)
    db_session.add(row)
    owner.active = False
    await db_session.commit()
    detail = (await client.get(f"{TASKS}/{row.id}")).json()
    assert detail["band"] == "overdue" and detail["owner_active"] is False
    changed = await client.patch(f"{TASKS}/{row.id}", json={"priority": "high"})
    assert changed.status_code == 200 and changed.json()["priority"] == "high"
    replacement = await make_user(db_session, "trainer", "it")
    moved = await client.patch(f"{TASKS}/{row.id}", json={"owner_user_id": str(replacement.id)})
    assert moved.json()["owner"]["id"] == str(replacement.id) and moved.json()["owner_active"] is True


@pytest.mark.asyncio
async def test_cancelled_tasks_leave_the_bands_and_list_under_cancelled(client, db_session):
    owner = await make_user(db_session, "trainer", "it")
    await as_user(client, db_session)
    created = await create(client, body(owner.id))
    cancelled = await client.patch(f"{TASKS}/{created['id']}", json={"status": "cancelled"})
    assert cancelled.json()["band"] == "cancelled"
    assert (await client.get(TASKS, params={"owner": str(owner.id)})).json()["items"] == []
    assert [i["id"] for i in (await client.get(TASKS, params={"owner": str(owner.id), "band": "cancelled"})).json()["items"]] == [created["id"]]


# --- AC2 / AC3: the owner's slice (MT9) -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac2_a_completed_task_leaves_overdue(client, db_session):
    owner = await make_user(db_session, "bdm", "it")
    partner = await as_user(client, db_session)
    row = ManagementTask(title="Approve new trainer", owner_user_id=owner.id, priority="medium", deadline=TODAY - timedelta(days=1), created_by_user_id=partner.id, updated_by_user_id=partner.id)
    db_session.add(row)
    await db_session.commit()
    await login(client, owner)
    mine = (await client.get(MINE)).json()
    assert [(i["title"], i["band"]) for i in mine["items"]] == [("Approve new trainer", "overdue")]
    assert mine["counts"]["overdue"] == 1
    done = await client.patch(f"{MINE}/{row.id}", json={"status": "completed"})
    assert done.status_code == 200 and done.json()["band"] == "completed" and done.json()["status"] == "completed"
    mine = (await client.get(MINE)).json()
    assert mine["counts"]["overdue"] == 0 and mine["counts"]["completed"] == 1
    reopened = await client.patch(f"{MINE}/{row.id}", json={"status": "in_progress"})
    assert reopened.json()["band"] == "overdue"
    await db_session.refresh(row)
    assert row.completed_at is None


@pytest.mark.asyncio
async def test_ac3_a_staff_user_cannot_see_or_change_anothers_task(client, db_session):
    owner = await make_user(db_session, "counselor", "overseas")
    other = await make_user(db_session, "counselor", "overseas")
    await as_user(client, db_session)
    created = await create(client, body(owner.id, title="Discuss recruitment targets"))
    await login(client, other)
    assert (await client.get(MINE)).json()["items"] == []
    response = await client.patch(f"{MINE}/{created['id']}", json={"status": "completed"})
    assert response.status_code == 404
    assert (await client.patch(f"{MINE}/{uuid.uuid4()}", json={"status": "completed"})).status_code == 404
    await login(client, owner)
    item = (await client.get(MINE)).json()["items"][0]
    assert set(item) == {"id", "title", "priority", "deadline", "status", "band", "updated_at"}


@pytest.mark.asyncio
async def test_owner_cannot_cancel_or_update_a_cancelled_task(client, db_session):
    owner = await make_user(db_session, "telecaller", "it")
    await as_user(client, db_session)
    created = await create(client, body(owner.id))
    await client.patch(f"{TASKS}/{created['id']}", json={"status": "cancelled"})
    await login(client, owner)
    assert (await client.patch(f"{MINE}/{created['id']}", json={"status": "cancelled"})).status_code == 422
    assert (await client.patch(f"{MINE}/{created['id']}", json={"status": "completed"})).status_code == 409
    assert (await client.get(MINE)).json()["items"] == []


# --- notifications (MT11) and audit (MT12) -------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_owner_is_notified_on_assign_change_and_reassign_not_on_own_update(client, db_session):
    owner = await make_user(db_session, "trainer", "it")
    second = await make_user(db_session, "trainer", "it")
    partner = await as_user(client, db_session)
    owner_id, second_id, partner_id = owner.id, second.id, partner.id  # read before expire_all() in notes_for
    created = await create(client, body(owner_id))
    notes = await notes_for(db_session, owner_id)
    assert [n.title for n in notes] == ["A management task was assigned to you"]
    assert "Approve marketing budget" in notes[0].body and notes[0].action_url == "/account/management-tasks"
    await client.patch(f"{TASKS}/{created['id']}", json={"deadline": (TODAY + timedelta(days=2)).isoformat()})
    assert len(await notes_for(db_session, owner_id)) == 2
    await client.patch(f"{TASKS}/{created['id']}", json={"owner_user_id": str(second_id)})
    assert [n.title for n in await notes_for(db_session, second_id)] == ["A management task was assigned to you"]
    await db_session.refresh(second)
    await login(client, second)
    await client.patch(f"{MINE}/{created['id']}", json={"status": "in_progress"})
    assert len(await notes_for(db_session, second_id)) == 1
    await db_session.refresh(partner)
    await login(client, partner)
    await create(client, body(partner_id))
    assert await notes_for(db_session, partner_id) == []


@pytest.mark.asyncio
async def test_writes_are_audited_with_field_names_only(client, db_session):
    owner = await make_user(db_session, "trainer", "it")
    owner_id = owner.id
    await as_user(client, db_session)
    created = await create(client, body(owner_id))
    await client.patch(f"{TASKS}/{created['id']}", json={"priority": "low"})
    unchanged = await client.patch(f"{TASKS}/{created['id']}", json={"priority": "low"})
    assert unchanged.status_code == 200
    await login(client, owner)
    await client.patch(f"{MINE}/{created['id']}", json={"status": "completed"})
    db_session.expire_all()
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == created["id"]).order_by(AuditLog.created_at))).all()
    assert [r.action for r in rows] == ["mgmt.task.create", "mgmt.task.update", "mgmt.task.complete"]
    assert rows[1].metadata_json == {"fields": ["priority"]}
    assert rows[2].user_id == owner_id
    assert "Approve" not in str([r.metadata_json for r in rows])


@pytest.mark.asyncio
async def test_options_lists_active_staff_only(client, db_session):
    staff = await make_user(db_session, "hr_team", "it")
    student = await make_user(db_session, "it_student", "it")
    await as_user(client, db_session)
    ids = {u["id"] for u in (await client.get(f"{TASKS}/options")).json()["users"]}
    assert str(staff.id) in ids and str(student.id) not in ids
