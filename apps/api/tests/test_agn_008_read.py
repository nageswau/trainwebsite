"""AGN-008 AC07 + read side of AC01/AC02 -- list (status groups, student filter, paging, scope) and detail with history."""

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio

from app.models import ApplicationStatusHistory
from tests.agn001_helpers import client_for, mk_user
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import APPS, agency_world, mk_application

GROUPS = {
    "draft": {"pre_unsubmitted"},
    "submitted": {"pre_submitted"},
    "offer": {"offer"},
    "visa": {"visa", "tracking"},
    "enrolled": {"enrolled"},
    "withdrawn": {"withdrawn"},
    "all": {"pre_unsubmitted", "pre_submitted", "offer", "visa", "tracking", "enrolled"},
}


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    u = w["university"]
    m = w["master"]
    rows = {
        "pre_unsubmitted": await mk_application(db_session, agent=m, university=u, record=w["record"], status="eligibility_evaluation"),
        "pre_submitted": await mk_application(db_session, agent=m, university=u, record=w["record"], status="university_selection", submitted_on=date(2026, 9, 1), intake="Spring 2028"),
        "offer": await mk_application(db_session, agent=m, university=u, record=w["record"], status="offer", intake="Fall 2028"),
        "visa": await mk_application(db_session, agent=m, university=u, record=w["record"], status="visa_documentation", intake="Spring 2029"),
        "tracking": await mk_application(db_session, agent=m, university=u, record=w["record"], status="status_tracking", intake="Fall 2029"),
        "enrolled": await mk_application(db_session, agent=m, university=u, record=w["record"], status="enrolled", intake="Spring 2030"),
        "withdrawn": await mk_application(db_session, agent=m, university=u, record=w["record"], status="withdrawn", intake="Fall 2030"),
    }
    return w | {"apps": rows}


@pytest.mark.asyncio
@pytest.mark.parametrize("group", list(GROUPS))
async def test_each_status_group_returns_exactly_its_subset(world, group):
    async with client_for(world["master"].email) as c:
        body = (await c.get(APPS, params={"status": group, "student": str(world["record"].id), "limit": 100})).json()
    expected = {str(world["apps"][k].id) for k in GROUPS[group]}
    assert {i["id"] for i in body["items"]} == expected
    assert body["total"] == len(expected)


@pytest.mark.asyncio
async def test_unknown_group_is_422(world):
    async with client_for(world["master"].email) as c:
        assert (await c.get(APPS, params={"status": "rejected"})).status_code == 422


@pytest.mark.asyncio
async def test_paging_shape_and_totals(world):
    async with client_for(world["master"].email) as c:
        first = (await c.get(APPS, params={"student": str(world["record"].id), "limit": 2, "offset": 0})).json()
        second = (await c.get(APPS, params={"student": str(world["record"].id), "limit": 2, "offset": 2})).json()
    assert (first["total"], first["limit"], first["offset"], len(first["items"])) == (6, 2, 0, 2)
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}


@pytest.mark.asyncio
async def test_item_shape_is_an_allowlist(world):
    async with client_for(world["master"].email) as c:
        item = (await c.get(APPS, params={"status": "offer"})).json()["items"][0]
    assert set(item) == {
        "id",
        "agent_student_id",
        "student",
        "has_login",
        "university",
        "course",
        "intake",
        "status",
        "application_reference",
        "submitted_on",
        "application_deadline",
        "offer_deadline",
        "nearest_deadline",
        "next_action",
        "updated_at",
    }
    assert item["student"] == world["record"].full_name and item["has_login"] is False


@pytest.mark.asyncio
async def test_nearest_deadline_prefers_the_next_upcoming_then_the_latest_past(db_session, world):
    today = date.today()
    soon = await mk_application(
        db_session,
        agent=world["master"],
        university=world["university"],
        record=world["record"],
        intake="N1",
        application_deadline=today + timedelta(days=3),
        offer_deadline=today + timedelta(days=30),
    )
    past = await mk_application(
        db_session, agent=world["master"], university=world["university"], record=world["record"], intake="N2", application_deadline=today - timedelta(days=9), offer_deadline=today - timedelta(days=2)
    )
    async with client_for(world["master"].email) as c:
        a = (await c.get(f"{APPS}/{soon.id}")).json()["application"]
        b = (await c.get(f"{APPS}/{past.id}")).json()["application"]
    assert a["nearest_deadline"] == {"kind": "application", "date": str(today + timedelta(days=3))}
    assert b["nearest_deadline"] == {"kind": "offer", "date": str(today - timedelta(days=2))}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "app_days", "offer_days", "expected"),
    [
        ("withdrawn", 3, 30, None),  # QA8-13: a closed application has no deadline to chase
        ("enrolled", 3, 30, None),
        ("offer", 3, 30, ("offer", 30)),  # after the offer only the offer deadline counts
        ("visa_documentation", 3, 30, ("offer", 30)),
        ("status_tracking", -9, -2, ("offer", -2)),
        ("offer", 3, None, None),
        ("university_selection", 3, 30, ("application", 3)),  # before the offer both count
    ],
)
async def test_nearest_deadline_depends_on_the_stage(db_session, world, status, app_days, offer_days, expected):
    today = date.today()
    row = await mk_application(
        db_session,
        agent=world["master"],
        university=world["university"],
        record=world["record"],
        status=status,
        intake=f"QA13 {status} {offer_days}",
        application_deadline=today + timedelta(days=app_days),
        offer_deadline=None if offer_days is None else today + timedelta(days=offer_days),
    )
    async with client_for(world["master"].email) as c:
        detail = (await c.get(f"{APPS}/{row.id}")).json()["application"]
        items = (await c.get(APPS, params={"limit": 100, "status": "all"})).json()["items"]
    want = None if expected is None else {"kind": expected[0], "date": str(today + timedelta(days=expected[1]))}
    assert detail["nearest_deadline"] == want
    assert detail["application_deadline"] == str(today + timedelta(days=app_days))  # the dates stay in the detail fields
    listed = [i for i in items if i["id"] == str(row.id)]
    if status != "withdrawn":  # the default "all" group leaves withdrawn out
        assert listed[0]["nearest_deadline"] == want


@pytest.mark.asyncio
async def test_staff_list_only_assigned_and_other_org_sees_nothing(db_session, world):
    stranger = await mk_record(db_session, agent=world["master"], full_name="Unassigned")
    hidden = await mk_application(db_session, agent=world["master"], university=world["university"], record=stranger)
    async with client_for(world["staff"]["user"].email) as c:
        ids = {i["id"] for i in (await c.get(APPS, params={"limit": 100})).json()["items"]}
    assert str(world["apps"]["offer"].id) in ids and str(hidden.id) not in ids
    async with client_for(world["other"]["master"].email) as c:
        assert (await c.get(APPS)).json()["total"] == 0


@pytest.mark.asyncio
async def test_detail_has_history_and_read_only_reason(db_session, world):
    app = world["apps"]["withdrawn"]
    db_session.add(ApplicationStatusHistory(application_id=app.id, from_status=None, to_status="enquiry", changed_by_id=world["master"].id))
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        body = (await c.get(f"{APPS}/{app.id}")).json()["application"]
    assert body["read_only_reason"] == "withdrawn"
    assert body["history"][0]["to_status"] == "enquiry" and body["history"][0]["changed_by"] == world["master"].full_name
    assert {"university_id", "university_slug", "course_id", "created_at"} <= set(body)
    assert not {"agent_id", "student_id", "counselor_id", "email", "phone"} & set(body)


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["other_staff", "other_master"])
async def test_detail_out_of_scope_is_404(world, who):
    user = world["other_staff"]["user"] if who == "other_staff" else world["other"]["master"]
    async with client_for(user.email) as c:
        response = await c.get(f"{APPS}/{world['apps']['offer'].id}")
    assert response.status_code == 404 and response.json()["detail"] == "Application not found"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["super_admin", "counselor", "university_rep", "overseas_student"])
async def test_non_agents_are_refused(db_session, world, role):
    user = await mk_user(db_session, role=role, division="global" if role == "super_admin" else "overseas")
    async with client_for(user.email, "global" if role == "super_admin" else "overseas") as c:
        assert (await c.get(APPS)).status_code == 403


@pytest.mark.asyncio
async def test_unknown_id_is_404(world):
    async with client_for(world["master"].email) as c:
        assert (await c.get(f"{APPS}/{uuid.uuid4()}")).status_code == 404
