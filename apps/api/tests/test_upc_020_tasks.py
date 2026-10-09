"""upc-020 -- partnership tasks and follow-ups: create, bands, scope and commands (spec §1 TK2, TK8-TK13; AC2, AC3, N1, R1)."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, PartnershipTask, University
from app.services.bdm_travel import india_today
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, url

TASKS = "/api/v1/partnership/tasks"


def task_url(task_id, action: str | None = None) -> str:
    return f"{TASKS}/{task_id}" + (f"/{action}" if action else "")


def day(offset: int) -> str:
    return (india_today() + timedelta(days=offset)).isoformat()


async def _owned(client, db):
    """A head creates a university owned by `pm`. Returns (head, pm, other_pm_of_same_head, university), signed in as the head."""
    head = await make_head(db)
    pm, other = await make_pm(db, head), await make_pm(db, head)
    await login(client, head)
    uni = await create(client, (await catalogue_country(db)).id)
    response = await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})
    assert response.status_code == 200, response.text
    return head, pm, other, uni


async def add(client, university_id, expected: int = 201, **overrides) -> dict:
    body = {"university_id": str(university_id), "kind": "follow_up", "title": "Follow-up call", "due_on": day(2)}
    body.update(overrides)
    response = await client.post(TASKS, json=body)
    assert response.status_code == expected, response.text
    return response.json().get("task", response.json())


async def act(client, task_id, action: str, expected: int = 200, **body) -> dict:
    response = await client.post(task_url(task_id, action), json=body or None)
    assert response.status_code == expected, response.text
    return response.json()


async def listing(client, expected: int = 200, **params) -> dict:
    response = await client.get(TASKS, params=params)
    assert response.status_code == expected, response.text
    return response.json()


# --- create (TK2, TK9, TK10) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_owning_manager_adds_a_follow_up_for_themselves(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    t = await add(client, uni["id"], notes="Ask about the January intake", priority="high")
    assert t["title"] == "Follow-up call" and t["kind"] == "follow_up" and t["priority"] == "high" and t["status"] == "open"
    assert t["source"] == "manual" and t["due_on"] == day(2) and t["band"] == "upcoming" and not t["overdue"]
    assert t["assignee"]["id"] == str(pm.id) and t["created_by"]["id"] == str(pm.id)
    assert t["university"] == {"id": uni["id"], "university_code": uni["university_code"], "name": uni["name"]}
    assert t["permissions"] == {"can_edit": True, "can_reschedule": True, "can_complete": True, "can_cancel": True}
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == t["id"]))).all()
    assert [(a.action, a.metadata_json) for a in audit] == [("partnership_task.create", {"kind": "follow_up", "source": "manual", "university_id": uni["id"]})]


@pytest.mark.asyncio
async def test_priority_defaults_to_medium_and_the_catalogue_lists_the_twelve_titles(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    assert (await add(client, uni["id"]))["priority"] == "medium"
    titles = (await client.get(f"{TASKS}/catalogue")).json()["titles"]
    assert len(titles) == 12 and titles[0] == "Follow up with university" and titles[-1] == "Follow up on offers"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"title": "x" * 201},
        {"notes": "x" * 2001},
        {"due_on": None},
        {"kind": "meeting"},
        {"priority": "urgent"},
        {"status": "done"},  # never written directly
        {"source": "stage"},
    ],
)
async def test_invalid_bodies_are_422(client, db_session, overrides):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    await add(client, uni["id"], 422, **overrides)


@pytest.mark.asyncio
async def test_a_past_due_date_is_422(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    response = await client.post(TASKS, json={"university_id": uni["id"], "kind": "task", "title": "Send MoU", "due_on": day(-1)})
    assert response.status_code == 422 and "past" in response.text


@pytest.mark.asyncio
async def test_n1_assignee_must_be_yourself_or_your_direct_report(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    stranger = await make_pm(db_session, await make_head(db_session))
    await login(client, pm)
    await add(client, uni["id"], 422, assignee_user_id=str(other.id))  # a manager assigns only themselves
    await login(client, head)
    await add(client, uni["id"], 422, assignee_user_id=str(stranger.id))  # outside the head's team
    t = await add(client, uni["id"], assignee_user_id=str(other.id))
    assert t["assignee"]["id"] == str(other.id) and t["created_by"]["id"] == str(head.id)
    assert (await add(client, uni["id"]))["assignee"]["id"] == str(head.id)  # default: the creator


@pytest.mark.asyncio
async def test_r1_create_scope(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    await login(client, other)
    await add(client, uni["id"], 403)  # not the university's manager
    await add(client, uuid4(), 422)  # unknown university
    await as_role(client, db_session, "super_admin", "global")
    await add(client, uni["id"], 403)  # super_admin reads only (TK9)
    await as_role(client, db_session, "overseas_admin", "overseas")
    await add(client, uni["id"], 403)
    await listing(client, 403)
    await db_session.execute(update(University).where(University.id == UUID(uni["id"])).values(active=False))
    await db_session.commit()
    await login(client, pm)
    await add(client, uni["id"], 409)  # inactive university


# --- read + bands (TK8, TK13; AC2, AC3) --------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac2_bands_follow_ist_dates_and_counts_add_up(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    today, tomorrow, later, late = [await add(client, uni["id"], due_on=day(n)) for n in (0, 1, 5, 0)]
    await db_session.execute(update(PartnershipTask).where(PartnershipTask.id == UUID(late["id"])).values(due_on=india_today() - timedelta(days=3)))
    await db_session.commit()
    expected = {"overdue": late, "today": today, "tomorrow": tomorrow, "upcoming": later}
    for band, task in expected.items():
        page = await listing(client, band=band, university_id=uni["id"])
        assert [t["id"] for t in page["items"]] == [task["id"]], band
        assert page["items"][0]["band"] == band
    page = await listing(client, band="open", university_id=uni["id"])
    assert page["counts"] == {"overdue": 1, "today": 1, "tomorrow": 1, "upcoming": 1, "done": 0, "cancelled": 0}
    assert page["today"] == day(0) and page["total"] == 4
    assert [t["id"] for t in page["items"]] == [late["id"], today["id"], tomorrow["id"], later["id"]]  # due date first
    assert page["items"][0]["overdue"] is True


@pytest.mark.asyncio
async def test_ac3_a_completed_task_is_never_overdue(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    t = await add(client, uni["id"], due_on=day(0))
    await db_session.execute(update(PartnershipTask).where(PartnershipTask.id == UUID(t["id"])).values(due_on=india_today() - timedelta(days=2)))
    await db_session.commit()
    done = (await act(client, t["id"], "complete"))["task"]
    assert done["status"] == "done" and done["overdue"] is False and done["band"] == "done" and done["completed_at"]
    assert (await listing(client, band="overdue", university_id=uni["id"]))["total"] == 0
    assert [x["id"] for x in (await listing(client, band="done", university_id=uni["id"]))["items"]] == [t["id"]]


@pytest.mark.asyncio
async def test_every_partnership_reader_reads_every_task_and_the_assignee_filter_narrows(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    await login(client, head)
    mine = await add(client, uni["id"])
    theirs = await add(client, uni["id"], assignee_user_id=str(pm.id))
    await login(client, other)  # not the university's manager: still reads (TK8), but cannot act
    page = await listing(client, band="open", university_id=uni["id"])
    assert {t["id"] for t in page["items"]} == {mine["id"], theirs["id"]}
    assert all(not any(t["permissions"].values()) for t in page["items"])
    assert (await listing(client, band="open", university_id=uni["id"], assignee="me"))["total"] == 0
    await login(client, head)
    assert [t["id"] for t in (await listing(client, band="open", university_id=uni["id"], assignee="me"))["items"]] == [mine["id"]]
    assert (await listing(client, band="open", university_id=uni["id"], assignee="team"))["total"] == 2
    assert [t["id"] for t in (await listing(client, band="open", university_id=uni["id"], assignee=str(pm.id)))["items"]] == [theirs["id"]]
    await as_role(client, db_session, "super_admin", "global")
    assert (await listing(client, band="open", university_id=uni["id"]))["total"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"band": "late"}, {"assignee": "everyone"}, {"kind": "call"}, {"limit": 0}])
async def test_unknown_filters_are_422(client, db_session, params):
    _, pm, _, _ = await _owned(client, db_session)
    await login(client, pm)
    await listing(client, 422, **params)


# --- commands (TK11, TK12; R1) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_assignee_edits_reschedules_and_cancels(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    t = await add(client, uni["id"])
    response = await client.patch(task_url(t["id"]), json={"title": "Send partnership proposal", "priority": "low", "notes": "PDF v2"})
    assert response.status_code == 200, response.text
    edited = response.json()["task"]
    assert (edited["title"], edited["priority"], edited["notes"]) == ("Send partnership proposal", "low", "PDF v2")
    assert (await client.patch(task_url(t["id"]), json={"due_on": day(9)})).status_code == 422  # only through reschedule
    await act(client, t["id"], "reschedule", 422, due_on=day(-1))
    assert (await act(client, t["id"], "reschedule", due_on=day(9)))["task"]["due_on"] == day(9)
    await act(client, t["id"], "cancel", 422)  # a reason is required
    cancelled = (await act(client, t["id"], "cancel", reason="University paused intake"))["task"]
    assert cancelled["status"] == "cancelled" and cancelled["cancel_reason"] == "University paused intake" and cancelled["band"] == "cancelled"
    assert not any(cancelled["permissions"].values())
    for action, body in (("complete", {}), ("reschedule", {"due_on": day(3)}), ("cancel", {"reason": "again"})):
        await act(client, t["id"], action, 409, **body)
    assert (await client.patch(task_url(t["id"]), json={"title": "x"})).status_code == 409
    actions = [a.action for a in (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == t["id"]).order_by(AuditLog.created_at))).all()]
    assert actions == ["partnership_task.create", "partnership_task.update", "partnership_task.reschedule", "partnership_task.cancel"]


@pytest.mark.asyncio
async def test_only_the_assignee_or_their_head_acts(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    await login(client, pm)
    t = await add(client, uni["id"])
    await login(client, other)
    await act(client, t["id"], "complete", 403)
    assert (await client.patch(task_url(t["id"]), json={"title": "x"})).status_code == 403
    await login(client, await make_head(db_session))  # another team's head
    await act(client, t["id"], "complete", 403)
    await as_role(client, db_session, "super_admin", "global")
    await act(client, t["id"], "complete", 403)
    await login(client, head)  # the assignee's reporting head reassigns, then completes
    response = await client.patch(task_url(t["id"]), json={"assignee_user_id": str(other.id)})
    assert response.status_code == 200 and response.json()["task"]["assignee"]["id"] == str(other.id)
    assert (await act(client, t["id"], "complete"))["task"]["status"] == "done"
    await act(client, uuid4(), "complete", 404)


@pytest.mark.asyncio
async def test_a_manager_cannot_reassign_to_someone_else(client, db_session):
    _, pm, other, uni = await _owned(client, db_session)
    await login(client, pm)
    t = await add(client, uni["id"])
    assert (await client.patch(task_url(t["id"]), json={"assignee_user_id": str(other.id)})).status_code == 422
