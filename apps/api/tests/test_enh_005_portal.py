import pytest
from enh005_helpers import login, mk_request, mk_school

# ENH-005: the admin's `school-transfers` workspace. `PortalPage` (web) needs both a nav entry AND this payload, or the page is a 404.

PORTAL = "/api/v1/portal/overseas/admin/school-transfers"


@pytest.mark.asyncio
async def test_the_school_transfers_workspace_lists_recent_requests_for_the_overseas_admin(client, db_session):
    a = await mk_school(db_session, label="A")
    b = await mk_school(db_session, label="B", students=0)
    kid = a["students"][0]
    await mk_request(db_session, kid, from_school=a["school"], to_school=b["school"], filed_by_school=a["school"], requester=a["coordinator"])
    await login(client, a["admin"].email)

    response = await client.get(PORTAL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "School Transfers"
    assert [c["key"] for c in body["columns"]] == ["id", "student", "student_code", "from_school", "to_school", "status", "requested"]
    mine = next(row for row in body["rows"] if row["student_code"] == kid.student_code)
    assert (mine["student"], mine["from_school"], mine["to_school"], mine["status"]) == (kid.full_name, a["school"].name, b["school"].name, "pending")


@pytest.mark.asyncio
async def test_the_workspace_is_closed_to_everyone_but_the_admin(client, db_session):
    a = await mk_school(db_session, label="A")
    assert (await client.get(PORTAL)).status_code == 401
    for who in (a["coordinator"], a["parent"], a["teacher"]):
        await login(client, who.email)
        assert (await client.get(PORTAL)).status_code == 403, who.role
