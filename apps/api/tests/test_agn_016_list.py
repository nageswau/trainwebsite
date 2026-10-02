"""AGN-016 AC02, AC04, AC06 -- the task list: views, overdue boundary, order, scope, archived students, paging bounds."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for, mk_user
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import agency_world
from tests.agn016_helpers import TASKS, due, mk_task


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    m = w["master"]
    archived = await mk_record(db_session, agent=m, full_name="Archived", status="archived", assigned_member=w["staff"]["member"])
    w["tasks"] = {
        "later": await mk_task(db_session, record=w["record"], author=m, title="Later", due_at=due(days=3)),
        "late": await mk_task(db_session, record=w["record"], author=m, title="Late", due_at=due(hours=-5)),
        "linked": await mk_task(db_session, record=w["linked_record"], author=m, title="Linked", due_at=due(days=1)),
        "done": await mk_task(db_session, record=w["record"], author=m, title="Done", status="done"),
        "cancelled": await mk_task(db_session, record=w["record"], author=m, title="Cancelled", status="cancelled"),
        "archived": await mk_task(db_session, record=archived, author=m, title="Archived open", due_at=due(hours=-1)),
    }
    w["archived"] = archived
    return w


async def _titles(email, query="") -> list[str]:
    async with client_for(email) as c:
        response = await c.get(f"{TASKS}{query}")
    assert response.status_code == 200, response.text
    return [t["title"] for t in response.json()["items"]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", ["Late", "Linked", "Later"]),  # default view: open, earliest due first, archived students left out
        ("?view=open", ["Late", "Linked", "Later"]),
        ("?view=overdue", ["Late"]),
        ("?view=done", ["Done"]),
        ("?view=cancelled", ["Cancelled"]),
    ],
)
async def test_views(world, query, expected):
    assert await _titles(world["master"].email, query) == expected


@pytest.mark.asyncio
async def test_view_all_lists_open_by_due_then_closed_newest_first(db_session, world):
    titles = await _titles(world["master"].email, "?view=all")
    assert titles[:4] == ["Late", "Archived open", "Linked", "Later"]
    assert sorted(titles[4:]) == ["Cancelled", "Done"] and titles[4] == "Cancelled"  # closed after Done, so listed first


@pytest.mark.asyncio
async def test_overdue_flag_is_exactly_open_and_due_before_now(db_session, world):
    just_late = await mk_task(db_session, record=world["record"], author=world["master"], title="Just late", due_at=datetime.now(UTC) - timedelta(seconds=1))
    not_yet = await mk_task(db_session, record=world["record"], author=world["master"], title="Not yet", due_at=datetime.now(UTC) + timedelta(minutes=2))
    closed_late = await mk_task(db_session, record=world["record"], author=world["master"], title="Closed late", due_at=due(days=-3), status="done")
    async with client_for(world["master"].email) as c:
        items = {t["title"]: t["overdue"] for t in (await c.get(f"{TASKS}?view=all&limit=100")).json()["items"]}
    assert (items[just_late.title], items[not_yet.title], items[closed_late.title]) == (True, False, False)


@pytest.mark.asyncio
async def test_student_filter_shows_an_archived_students_tasks(world):
    assert await _titles(world["master"].email, f"?student={world['archived'].id}") == ["Archived open"]
    assert await _titles(world["master"].email, f"?student={world['record'].id}") == ["Late", "Later"]


@pytest.mark.asyncio
async def test_staff_list_only_their_students(db_session, world):
    assert await _titles(world["staff"]["user"].email) == ["Late", "Linked", "Later"]
    assert await _titles(world["other_staff"]["user"].email, "?view=all") == []
    assert await _titles(world["other"]["master"].email, "?view=all") == []


@pytest.mark.asyncio
async def test_out_of_scope_student_filter_is_an_empty_page(world):
    async with client_for(world["other_staff"]["user"].email) as c:
        body = (await c.get(f"{TASKS}?view=all&student={world['record'].id}")).json()
    assert (body["items"], body["total"]) == ([], 0)


@pytest.mark.asyncio
async def test_paging(world):
    async with client_for(world["master"].email) as c:
        first = (await c.get(f"{TASKS}?view=all&limit=2")).json()
        second = (await c.get(f"{TASKS}?view=all&limit=2&offset=2")).json()
    assert (first["total"], first["limit"], first["offset"], len(first["items"])) == (6, 2, 0, 2)
    assert {t["id"] for t in first["items"]}.isdisjoint({t["id"] for t in second["items"]})


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["?limit=0", "?limit=101", "?offset=-1", "?offset=10001", "?view=archived", "?student=nope"])
async def test_bad_parameters_are_422(world, query):
    async with client_for(world["master"].email) as c:
        assert (await c.get(f"{TASKS}{query}")).status_code == 422


@pytest.mark.asyncio
async def test_other_roles_cannot_list(db_session, world):
    user = await mk_user(db_session, role="counselor")
    async with client_for(user.email) as c:
        assert (await c.get(TASKS)).status_code == 403
