"""AGN-023 AC01-AC08 -- the Overseas Admin assigns or swaps an EduSphere counselor (spec §3.1, §3.2, §5)."""

import asyncio
import uuid

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for
from tests.agn023_helpers import ADVANCE, ASSIGN, UPDATE, assign_audits, assign_world, fresh, history_notes, notices


@pytest_asyncio.fixture
async def world(db_session):
    return await assign_world(db_session)


async def _assign(c, app, counselor):
    return await c.put(ASSIGN.format(app.id), json={"counselor_id": str(counselor.id)})


@pytest.mark.asyncio
async def test_admin_assigns_a_counselor_who_then_sees_the_application(db_session, world):  # AC01
    async with client_for(world["admin"].email) as c:
        r = await _assign(c, world["app"], world["counselor"])
    assert r.status_code == 200, r.text
    assert r.json() == {"id": str(world["app"].id), "counselor_id": str(world["counselor"].id), "counselor_name": world["counselor"].full_name, "changed": True}
    assert (await fresh(db_session, world["app"])).counselor_id == world["counselor"].id
    assert await history_notes(db_session, world["app"]) == ["EduSphere counsellor assigned"]
    assert await assign_audits(db_session, world["app"]) == [{"from_counselor_id": None, "to_counselor_id": str(world["counselor"].id)}]
    async with client_for(world["counselor"].email) as c:
        rows = (await c.get("/api/v1/portal/overseas/counselor/applications")).json()["rows"]
    assert str(world["app"].id) in {str(row["id"]) for row in rows}


@pytest.mark.asyncio
async def test_a_swap_moves_access_and_tells_both_counselors(db_session, world):  # AC02, AC08
    async with client_for(world["admin"].email) as c:
        assert (await _assign(c, world["app"], world["counselor"])).status_code == 200
        r = await _assign(c, world["app"], world["counselor2"])
    assert r.status_code == 200 and r.json()["changed"] is True
    assert await history_notes(db_session, world["app"]) == ["EduSphere counsellor assigned", "EduSphere counsellor changed"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(ADVANCE.format(world["app"].id), json={"to_status": "visa_documentation"})).status_code == 403
    assert [n.title for n in await notices(db_session, world["counselor"])] == ["Application assigned to you", "Application reassigned"]
    reassigned = (await notices(db_session, world["counselor"]))[-1]
    assert reassigned.body == "An application has moved to another counselor."
    assert [n.title for n in await notices(db_session, world["counselor2"])] == ["Application assigned to you"]


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["counselor", "master", "university_rep", "super_admin", "overseas_student"])
async def test_only_the_overseas_admin_may_assign(db_session, world, who):  # AC03
    from tests.agn001_helpers import mk_user

    users = {"counselor": world["counselor"], "master": world["master"]}
    user = users.get(who) or await mk_user(db_session, role=who, division="overseas")
    async with client_for(user.email) as c:
        r = await _assign(c, world["app"], world["counselor2"])
    assert r.status_code == 403, r.text
    assert (await fresh(db_session, world["app"])).counselor_id is None


@pytest.mark.asyncio
async def test_an_unknown_application_is_404(world):  # AC03
    async with client_for(world["admin"].email) as c:
        r = await c.put(ASSIGN.format(uuid.uuid4()), json={"counselor_id": str(world["counselor"].id)})
    assert r.status_code == 404 and r.json()["detail"] == "Application not found"


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["null", "missing", "it_counselor", "inactive", "admin", "unknown"])
async def test_the_counselor_must_be_an_active_overseas_counselor(db_session, world, target):  # AC04
    body = {
        "null": {"counselor_id": None},
        "missing": {},
        "it_counselor": {"counselor_id": str(world["it_counselor"].id)},
        "inactive": {"counselor_id": str(world["inactive"].id)},
        "admin": {"counselor_id": str(world["admin"].id)},
        "unknown": {"counselor_id": str(uuid.uuid4())},
    }[target]
    async with client_for(world["admin"].email) as c:
        r = await c.put(ASSIGN.format(world["app"].id), json=body)
    assert r.status_code == 422, r.text
    if target not in {"null", "missing"}:
        assert r.json()["detail"] == "Choose an active overseas counselor"
    assert (await fresh(db_session, world["app"])).counselor_id is None
    assert await history_notes(db_session, world["app"]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["withdrawn", "enrolled"])
async def test_a_closed_application_is_refused(db_session, status):  # AC05
    w = await assign_world(db_session, status=status)
    async with client_for(w["admin"].email) as c:
        r = await _assign(c, w["app"], w["counselor"])
    assert r.status_code == 409 and r.json()["detail"] == "This application is closed"
    assert (await fresh(db_session, w["app"])).counselor_id is None


@pytest.mark.asyncio
async def test_re_picking_the_same_counselor_changes_nothing(db_session, world):  # AC06
    async with client_for(world["admin"].email) as c:
        await _assign(c, world["app"], world["counselor"])
        r = await _assign(c, world["app"], world["counselor"])
    assert r.status_code == 200 and r.json()["changed"] is False
    assert len(await history_notes(db_session, world["app"])) == 1
    assert len(await assign_audits(db_session, world["app"])) == 1
    assert len(await notices(db_session, world["counselor"])) == 1


@pytest.mark.asyncio
async def test_two_assignments_at_once_leave_one_history_row(db_session, world):  # Review Focus 1
    async with client_for(world["admin"].email) as a, client_for(world["admin"].email) as b:
        results = await asyncio.gather(_assign(a, world["app"], world["counselor"]), _assign(b, world["app"], world["counselor"]))
    assert sorted(r.json()["changed"] for r in results) == [False, True]
    assert len(await history_notes(db_session, world["app"])) == 1
    assert len(await notices(db_session, world["counselor"])) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("who", "key"), [("admin", "app"), ("counselor", "direct_app")])  # a counselor's PATCH on an agency app is a 403 (C1)
async def test_the_generic_update_refuses_counselor_id(db_session, world, who, key):  # AC07
    async with client_for(world["admin"].email) as c:
        await _assign(c, world[key], world["counselor"])
    async with client_for(world[who].email) as c:
        for value in (str(world["counselor2"].id), None):
            r = await c.patch(UPDATE.format(world[key].id), json={"counselor_id": value})
            assert r.status_code == 422, r.text
            assert r.json()["detail"] == "Use Assign counselor to change the counselor"
    assert (await fresh(db_session, world[key])).counselor_id == world["counselor"].id


@pytest.mark.asyncio
async def test_the_agency_hears_without_names_and_a_direct_application_does_not_notify_it(db_session, world):  # AC08
    staff = world["staff"]["user"]  # the no-login student's assigned staff member: the AGN-017 recipient
    async with client_for(world["admin"].email) as c:
        await _assign(c, world["app"], world["counselor"])
        await _assign(c, world["app"], world["counselor2"])
        await _assign(c, world["direct_app"], world["counselor"])
    titles = [n.title for n in await notices(db_session, staff)]
    assert titles == ["EduSphere counsellor assigned", "EduSphere counsellor changed"]
    for n in await notices(db_session, staff):
        assert world["counselor"].full_name not in n.body and world["counselor2"].full_name not in n.body
        assert world["record"].full_name not in n.body
    assert await notices(db_session, world["master"]) == []  # the assignee is told, not the Masters (AGN-017 N2)
