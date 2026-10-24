"""ccrm-029 (DEC-SCOPE-250, T1-T8): counselor tasks -- the counselor's own tasks, the Overseas Admin's tasks for any overseas counselor,
the link scope (T4), the bands (T6), the status moves (T2), who edits what (T3), the notification (T5) and the counselor's own lead
follow-ups (T7, AC 7). The shared test database is never truncated: every assertion is about rows the test made.
Spec: docs/superpowers/specs/2026-10-24-ccrm-029-counselor-tasks-design.md."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AuditLog, CounselorTask, LeadFollowUp, Notification
from app.services.bdm_travel import india_today
from tests.agn001_helpers import login, mk_user, uniq
from tests.agn008_helpers import mk_application
from tests.ccrm012_helpers import mk_lead, mk_university

URL = "/api/v1/counselor/tasks"
FOLLOW_UPS = "/api/v1/counselor/follow-ups"


def day(offset: int = 0) -> str:
    return (india_today() + timedelta(days=offset)).isoformat()


async def as_(client, user) -> None:
    client.cookies.clear()
    await login(client, user.email, user.division)


def field_error(response, field: str) -> bool:
    return response.status_code == 422 and any(e["loc"][-1] == field for e in response.json()["detail"])


async def stored(db, task_id) -> CounselorTask:
    return await db.scalar(select(CounselorTask).where(CounselorTask.id == task_id).execution_options(populate_existing=True))


@pytest_asyncio.fixture
async def world(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name=f"Task Counselor {uniq()}")
    other = await mk_user(db_session, role="counselor", full_name=f"Other Counselor {uniq()}")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Task Admin")
    student = await mk_user(db_session, role="overseas_student", full_name=f"Task Student {uniq()}")
    university = await mk_university(db_session, "United Kingdom")
    application = await mk_application(db_session, agent=None, university=university, student=student, counselor_id=counselor.id)
    lead = await mk_lead(db_session, counselor, status="follow_up")
    other_lead = await mk_lead(db_session, other, status="follow_up")
    return {"counselor": counselor, "other": other, "admin": admin, "student": student, "application": application, "lead": lead, "other_lead": other_lead}


# --- create (T1, T3) ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_creates_a_task_for_themself(client, db_session, world):
    await as_(client, world["counselor"])
    response = await client.post(URL, json={"title": "  Call   the bank  ", "due_on": day(1), "priority": "high"})
    assert response.status_code == 201, response.text
    out = response.json()
    assert out["title"] == "Call the bank" and out["due_on"] == day(1) and out["priority"] == "high" and out["status"] == "open"
    assert out["band"] == "upcoming" and out["source"] == "manual" and out["link"] is None
    assert out["counselor"]["id"] == str(world["counselor"].id) and out["created_by"]["id"] == str(world["counselor"].id)
    assert out["can_edit"] is True
    task = await stored(db_session, out["id"])
    assert task.counselor_user_id == world["counselor"].id
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == out["id"], AuditLog.action == "counselor_task.create"))
    assert audit is not None and "Call the bank" not in str(audit.metadata_json)
    # T5: one's own task notifies nobody
    assert await db_session.scalar(select(Notification).where(Notification.user_id == world["counselor"].id, Notification.body.contains("Call the bank"))) is None


@pytest.mark.asyncio
async def test_counselor_cannot_create_for_another_counselor(client, world):
    await as_(client, world["counselor"])
    response = await client.post(URL, json={"title": "Not mine", "due_on": day(), "counselor_user_id": str(world["other"].id)})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_validation(client, world):
    await as_(client, world["counselor"])
    assert field_error(await client.post(URL, json={"title": "x", "due_on": day()}), "title")
    assert field_error(await client.post(URL, json={"title": "Past", "due_on": day(-1)}), "due_on")
    assert field_error(await client.post(URL, json={"title": "Far", "due_on": day(800)}), "due_on")
    assert (await client.post(URL, json={"title": "Odd", "due_on": day(), "priority": "urgent"})).status_code == 422
    assert (await client.post(URL, json={"title": "Rule", "due_on": day(), "source": "rule"})).status_code == 422  # extra=forbid


@pytest.mark.asyncio
async def test_admin_creates_for_a_counselor_who_is_notified(client, db_session, world):
    await as_(client, world["admin"])
    title = f"Chase offer {uniq()}"
    response = await client.post(URL, json={"title": title, "due_on": day(), "counselor_user_id": str(world["counselor"].id)})
    assert response.status_code == 201, response.text
    assert response.json()["band"] == "today"
    note = await db_session.scalar(select(Notification).where(Notification.user_id == world["counselor"].id, Notification.body.contains(title)))
    assert note is not None and note.action_url == "/overseas/counselor/tasks"


@pytest.mark.asyncio
async def test_admin_must_name_an_active_overseas_counselor(client, db_session, world):
    it_counselor = await mk_user(db_session, role="counselor", division="it")
    inactive = await mk_user(db_session, role="counselor", active=False)
    await as_(client, world["admin"])
    assert field_error(await client.post(URL, json={"title": "No owner", "due_on": day()}), "counselor_user_id")
    for person in (it_counselor, inactive, world["student"]):
        assert field_error(await client.post(URL, json={"title": "Wrong", "due_on": day(), "counselor_user_id": str(person.id)}), "counselor_user_id")


# --- link (T4) ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_links_in_the_assignees_scope(client, world):
    await as_(client, world["counselor"])
    for kind, target in (("lead", world["lead"].id), ("student", world["student"].id), ("application", world["application"].id)):
        response = await client.post(URL, json={"title": f"About {kind}", "due_on": day(), "link": {"type": kind, "id": str(target)}})
        assert response.status_code == 201, response.text
        link = response.json()["link"]
        assert link["type"] == kind and link["id"] == str(target) and link["label"]
    refused = await client.post(URL, json={"title": "Not my lead", "due_on": day(), "link": {"type": "lead", "id": str(world["other_lead"].id)}})
    assert field_error(refused, "link")


@pytest.mark.asyncio
async def test_admin_link_must_be_in_the_chosen_counselors_scope(client, world):
    await as_(client, world["admin"])
    other_lead = {"type": "lead", "id": str(world["other_lead"].id)}
    r = await client.post(URL, json={"title": "Chase lead", "due_on": day(), "counselor_user_id": str(world["counselor"].id), "link": other_lead})
    assert field_error(r, "link"), r.text
    ok = await client.post(URL, json={"title": "Chase lead", "due_on": day(), "counselor_user_id": str(world["other"].id), "link": other_lead})
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_link_options_are_the_assignees(client, world):
    await as_(client, world["counselor"])
    out = (await client.get(URL + "/options")).json()
    assert out["counselors"] == []
    assert str(world["lead"].id) in {x["id"] for x in out["links"]["leads"]}
    assert str(world["other_lead"].id) not in {x["id"] for x in out["links"]["leads"]}
    assert str(world["student"].id) in {x["id"] for x in out["links"]["students"]}
    assert str(world["application"].id) in {x["id"] for x in out["links"]["applications"]}
    await as_(client, world["admin"])
    out = (await client.get(URL + "/options", params={"counselor_id": str(world["other"].id)})).json()
    assert str(world["counselor"].id) in {x["id"] for x in out["counselors"]}
    assert {x["id"] for x in out["links"]["leads"]} >= {str(world["other_lead"].id)} and str(world["lead"].id) not in {x["id"] for x in out["links"]["leads"]}


# --- bands and lists (T6) -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_my_tasks_bands_and_counts(client, db_session, world):
    counselor = world["counselor"]
    rows = [
        CounselorTask(title="Late", counselor_user_id=counselor.id, due_on=india_today() - timedelta(days=2), created_by_user_id=counselor.id, updated_by_user_id=counselor.id),
        CounselorTask(title="Now", counselor_user_id=counselor.id, due_on=india_today(), created_by_user_id=counselor.id, updated_by_user_id=counselor.id),
        CounselorTask(title="Soon", counselor_user_id=counselor.id, due_on=india_today() + timedelta(days=3), created_by_user_id=counselor.id, updated_by_user_id=counselor.id),
        CounselorTask(title="Gone", counselor_user_id=counselor.id, due_on=india_today(), status="cancelled", cancelled_at=datetime.now(UTC), created_by_user_id=counselor.id, updated_by_user_id=counselor.id),
        CounselorTask(title="Finished", counselor_user_id=counselor.id, due_on=india_today(), status="done", completed_at=datetime.now(UTC), created_by_user_id=counselor.id, updated_by_user_id=counselor.id),
        CounselorTask(title="Old done", counselor_user_id=counselor.id, due_on=india_today() - timedelta(days=30), status="done", completed_at=datetime.now(UTC) - timedelta(days=20), created_by_user_id=counselor.id, updated_by_user_id=counselor.id),
        CounselorTask(title="Theirs", counselor_user_id=world["other"].id, due_on=india_today(), created_by_user_id=counselor.id, updated_by_user_id=counselor.id),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    await as_(client, counselor)
    out = (await client.get(URL)).json()
    assert [(i["title"], i["band"]) for i in out["items"]] == [("Late", "overdue"), ("Now", "today"), ("Soon", "upcoming"), ("Finished", "done")]
    assert out["counts"] == {"overdue": 1, "today": 1, "upcoming": 1, "done": 1}
    assert [i["title"] for i in (await client.get(URL, params={"band": "overdue"})).json()["items"]] == ["Late"]
    assert [i["title"] for i in (await client.get(URL, params={"band": "cancelled"})).json()["items"]] == ["Gone"]
    # a counselor never sees another counselor's tasks, whatever they ask for
    assert "Theirs" not in {i["title"] for i in (await client.get(URL, params={"counselor_id": str(world["other"].id)})).json()["items"]}
    assert (await client.get(f"{URL}/{rows[6].id}")).status_code == 404


@pytest.mark.asyncio
async def test_admin_lists_everyone_or_one_counselor(client, db_session, world):
    for owner in (world["counselor"], world["other"]):
        db_session.add(CounselorTask(title=f"For {owner.full_name}", counselor_user_id=owner.id, due_on=india_today(), created_by_user_id=owner.id, updated_by_user_id=owner.id))
    await db_session.commit()
    await as_(client, world["admin"])
    one = (await client.get(URL, params={"counselor_id": str(world["other"].id), "limit": 200})).json()
    assert {i["counselor"]["id"] for i in one["items"]} == {str(world["other"].id)}
    everyone = (await client.get(URL, params={"limit": 200, "band": "today"})).json()
    assert everyone["total"] >= 2


# --- status moves and edits (T2, T3) --------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_done_reopen_cancel(client, db_session, world):
    await as_(client, world["counselor"])
    task_id = (await client.post(URL, json={"title": "Move me", "due_on": day()})).json()["id"]
    done = await client.patch(f"{URL}/{task_id}", json={"status": "done"})
    assert done.status_code == 200 and done.json()["band"] == "done" and done.json()["completed_at"]
    reopened = await client.patch(f"{URL}/{task_id}", json={"status": "open"})
    assert reopened.json()["status"] == "open" and reopened.json()["completed_at"] is None
    cancelled = await client.patch(f"{URL}/{task_id}", json={"status": "cancelled"})
    assert cancelled.json()["band"] == "cancelled"
    assert (await client.patch(f"{URL}/{task_id}", json={"status": "open"})).status_code == 409
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == task_id).order_by(AuditLog.created_at))).all()
    assert actions == ["counselor_task.create", "counselor_task.complete", "counselor_task.reopen", "counselor_task.cancel"]


@pytest.mark.asyncio
async def test_unchanged_patch_records_nothing(client, db_session, world):
    await as_(client, world["counselor"])
    task_id = (await client.post(URL, json={"title": "Same", "due_on": day()})).json()["id"]
    assert (await client.patch(f"{URL}/{task_id}", json={"title": "Same", "due_on": day()})).status_code == 200
    assert (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == task_id))).all() == ["counselor_task.create"]


@pytest.mark.asyncio
async def test_counselor_edits_own_created_tasks_but_only_the_status_of_admin_tasks(client, db_session, world):
    await as_(client, world["admin"])
    admin_task = (await client.post(URL, json={"title": "From admin", "due_on": day(), "counselor_user_id": str(world["counselor"].id)})).json()
    assert admin_task["can_edit"] is True
    await as_(client, world["counselor"])
    listed = next(i for i in (await client.get(URL)).json()["items"] if i["id"] == admin_task["id"])
    assert listed["can_edit"] is False
    assert (await client.patch(f"{URL}/{admin_task['id']}", json={"due_on": day(5)})).status_code == 403
    assert (await client.patch(f"{URL}/{admin_task['id']}", json={"status": "done"})).status_code == 200
    own = (await client.post(URL, json={"title": "Mine", "due_on": day()})).json()
    edited = await client.patch(f"{URL}/{own['id']}", json={"title": "Mine, renamed", "due_on": day(2), "priority": "low", "link": {"type": "lead", "id": str(world["lead"].id)}})
    assert edited.status_code == 200 and edited.json()["title"] == "Mine, renamed" and edited.json()["link"]["type"] == "lead"
    cleared = await client.patch(f"{URL}/{own['id']}", json={"link": None})
    assert cleared.json()["link"] is None
    assert (await client.patch(f"{URL}/{own['id']}", json={"counselor_user_id": str(world["other"].id)})).status_code == 403


@pytest.mark.asyncio
async def test_admin_reassigns_and_the_new_counselor_is_notified(client, db_session, world):
    await as_(client, world["admin"])
    title = f"Hand over {uniq()}"
    task_id = (await client.post(URL, json={"title": title, "due_on": day(), "counselor_user_id": str(world["counselor"].id)})).json()["id"]
    moved = await client.patch(f"{URL}/{task_id}", json={"counselor_user_id": str(world["other"].id)})
    assert moved.status_code == 200 and moved.json()["counselor"]["id"] == str(world["other"].id)
    note = await db_session.scalar(select(Notification).where(Notification.user_id == world["other"].id, Notification.body.contains(title)))
    assert note is not None and note.title == "A task was assigned to you"
    await as_(client, world["counselor"])
    assert (await client.get(f"{URL}/{task_id}")).status_code == 404


@pytest.mark.asyncio
async def test_a_past_due_task_stays_editable(client, db_session, world):
    counselor = world["counselor"]
    task = CounselorTask(title="Old", counselor_user_id=counselor.id, due_on=india_today() - timedelta(days=3), created_by_user_id=counselor.id, updated_by_user_id=counselor.id)
    db_session.add(task)
    await db_session.commit()
    await as_(client, counselor)
    assert (await client.patch(f"{URL}/{task.id}", json={"title": "Old, renamed"})).status_code == 200
    assert field_error(await client.patch(f"{URL}/{task.id}", json={"due_on": day(-1)}), "due_on")


# --- access -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_other_roles_are_refused(client, db_session, world):
    it_counselor = await mk_user(db_session, role="counselor", division="it")
    for person in (world["student"], it_counselor):
        await as_(client, person)
        assert (await client.get(URL)).status_code == 403
        assert (await client.post(URL, json={"title": "Nope", "due_on": day()})).status_code == 403
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401


@pytest.mark.asyncio
async def test_super_admin_passes(client, db_session, world):
    root = await mk_user(db_session, role="super_admin")
    await as_(client, root)
    response = await client.post(URL, json={"title": "From root", "due_on": day(), "counselor_user_id": str(world["counselor"].id)})
    assert response.status_code == 201, response.text


# --- the counselor's follow-ups (T7, AC 7) --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_sees_their_overdue_follow_ups(client, db_session, world):
    counselor = world["counselor"]
    late = LeadFollowUp(lead_id=world["lead"].id, due_at=datetime.now(UTC) - timedelta(hours=5), reason="counselor_call", created_by_user_id=counselor.id)
    theirs = LeadFollowUp(lead_id=world["other_lead"].id, due_at=datetime.now(UTC) - timedelta(hours=5), reason="counselor_call", created_by_user_id=world["other"].id)
    db_session.add_all([late, theirs])
    await db_session.commit()
    await as_(client, counselor)
    out = (await client.get(FOLLOW_UPS, params={"view": "overdue"})).json()
    ids = {i["id"] for i in out["items"]}
    assert str(late.id) in ids and str(theirs.id) not in ids and out["counts"]["overdue"] >= 1
    assert out["items"][0]["lead"]["id"] == str(world["lead"].id)
    await as_(client, world["admin"])
    assert (await client.get(FOLLOW_UPS)).status_code == 403
