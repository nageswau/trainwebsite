"""nehn-040 (DEC-SCOPE-279) -- the business-facing Student ID covers agency-created and admin-provisioned students, and is shown and
searchable in the admin users list, the overseas-student lookup, the agency student list and the agent network list, inside each
caller's existing scope."""

import re
import uuid

import pytest
import pytest_asyncio

from app.core import identifiers
from app.models import AgentStudent, User
from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn004_helpers import RECORDS, mk_record
from tests.agn022_helpers import STUDENTS

CODE = re.compile(r"^[0-9A-F]{8}$")
LOOKUP = "/api/v1/lookups/overseas-students"


def _code() -> str:
    return uuid.uuid4().hex[:8].upper()


async def _with_code(db, row, code: str | None = None):
    row.student_code = code or _code()
    await db.commit()
    return row


@pytest_asyncio.fixture
async def agencies(db_session):
    own = await mk_active_org(db_session, name="Code Agency")
    other = await mk_active_org(db_session, name="Other Code Agency")
    own_record = await _with_code(db_session, await mk_record(db_session, agent=own["master"], full_name=f"Own Record {uuid.uuid4().hex[:6]}"))
    other_record = await _with_code(db_session, await mk_record(db_session, agent=other["master"], full_name=f"Other Record {uuid.uuid4().hex[:6]}"))
    account = await _with_code(db_session, await mk_user(db_session, role="overseas_student", full_name=f"Linked Student {uuid.uuid4().hex[:6]}"))
    linked = AgentStudent(agent_id=own["master"].id, student_id=account.id, status="active")
    db_session.add(linked)
    await db_session.commit()
    return {"own": own, "other": other, "own_record": own_record, "other_record": other_record, "account": account, "linked": linked}


@pytest.mark.asyncio
async def test_a_new_code_is_unique_across_every_column_given(db_session, monkeypatch, agencies):  # AC6
    taken = agencies["own_record"].student_code
    candidates = iter([taken, "0A0B0C0D"])
    monkeypatch.setattr(identifiers, "generate_student_code", lambda: next(candidates))
    assert await identifiers.unique_student_code(db_session, User.student_code, AgentStudent.student_code) == "0A0B0C0D"


@pytest.mark.asyncio
async def test_an_agency_created_student_gets_a_code_at_create(db_session, agencies):  # AC2
    async with client_for(agencies["own"]["master"].email) as c:
        response = await c.post(RECORDS, json={"full_name": "Coded Student", "email": f"coded-{uuid.uuid4().hex[:8]}@example.local"})
    assert response.status_code == 201, response.text
    body = response.json()["student"]
    assert CODE.match(body["student_code"])
    row = await db_session.get(AgentStudent, uuid.UUID(body["id"]), populate_existing=True)
    assert row.student_code == body["student_code"]


@pytest.mark.asyncio
async def test_a_linked_student_shows_the_account_code_and_the_row_keeps_none(db_session, agencies):  # AC3, N2
    async with client_for(agencies["own"]["master"].email) as c:
        items = (await c.get(RECORDS, params={"limit": 100})).json()["items"]
        detail = (await c.get(f"{RECORDS}/{agencies['linked'].id}")).json()["student"]
    by_id = {i["id"]: i for i in items}
    assert by_id[str(agencies["linked"].id)]["student_code"] == agencies["account"].student_code
    assert by_id[str(agencies["own_record"].id)]["student_code"] == agencies["own_record"].student_code
    assert detail["student_code"] == agencies["account"].student_code
    assert (await db_session.get(AgentStudent, agencies["linked"].id, populate_existing=True)).student_code is None


@pytest.mark.asyncio
async def test_the_agency_search_matches_a_code_only_inside_the_agency(agencies):  # AC1, AC5
    async with client_for(agencies["own"]["master"].email) as c:
        own = (await c.get(RECORDS, params={"q": agencies["own_record"].student_code.lower()})).json()
        linked = (await c.get(RECORDS, params={"q": agencies["account"].student_code})).json()
        foreign = (await c.get(RECORDS, params={"q": agencies["other_record"].student_code})).json()
    assert [i["id"] for i in own["items"]] == [str(agencies["own_record"].id)]
    assert [i["id"] for i in linked["items"]] == [str(agencies["linked"].id)]
    assert foreign["items"] == [] and foreign["total"] == 0


@pytest.mark.asyncio
async def test_admin_users_list_returns_the_code(db_session, agencies):  # AC1, AC3
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        rows = (await c.get("/api/v1/admin/users", params={"role": "overseas_student"})).json()
    by_id = {r["id"]: r for r in rows}
    assert by_id[str(agencies["account"].id)]["student_code"] == agencies["account"].student_code
    assert all("student_code" in r for r in rows)


@pytest.mark.asyncio
async def test_an_admin_provisioned_student_gets_a_code_and_staff_do_not(db_session):  # N4
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        student = await c.post(
            "/api/v1/admin/users", json={"role": "overseas_student", "division": "overseas", "email": f"prov-{uuid.uuid4().hex[:8]}@example.local", "full_name": "Provisioned Student"}
        )
        staff = await c.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": f"prov-{uuid.uuid4().hex[:8]}@example.local", "full_name": "Provisioned Counselor"})
    assert student.status_code == 201 and staff.status_code == 201, (student.text, staff.text)
    assert CODE.match((await db_session.get(User, uuid.UUID(student.json()["id"]))).student_code)
    assert (await db_session.get(User, uuid.UUID(staff.json()["id"]))).student_code is None


@pytest.mark.asyncio
async def test_the_overseas_student_lookup_matches_and_shows_the_code_in_scope(db_session, agencies):  # AC1, AC3, AC5
    admin = await mk_user(db_session, role="overseas_admin")
    counselor = await mk_user(db_session, role="counselor")
    code = agencies["account"].student_code
    async with client_for(admin.email) as c:
        found = (await c.get(LOOKUP, params={"q": code.lower()})).json()["items"]
    async with client_for(counselor.email) as c:
        hidden = (await c.get(LOOKUP, params={"q": code})).json()["items"]
    assert [i["id"] for i in found] == [str(agencies["account"].id)]
    assert found[0]["detail"] == f"{agencies['account'].email} · {code}"
    assert hidden == []


@pytest.mark.asyncio
async def test_the_link_lookup_does_not_match_a_code(agencies):  # N7
    async with client_for(agencies["other"]["master"].email) as c:
        response = await c.get(LOOKUP, params={"q": agencies["account"].student_code, "purpose": "link"})
    assert response.status_code == 200 and response.json()["items"] == []


@pytest.mark.asyncio
async def test_the_agent_network_students_carry_the_code(db_session, agencies):  # AC3
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        items = (await c.get(STUDENTS.format(oid=agencies["own"]["org"].id))).json()["items"]
    by_id = {i["id"]: i["student_code"] for i in items}
    assert by_id == {
        str(agencies["own_record"].id): agencies["own_record"].student_code,
        str(agencies["linked"].id): agencies["account"].student_code,
    }


@pytest.mark.asyncio
async def test_admin_users_q_finds_a_student_beyond_the_list_cap(db_session, monkeypatch, agencies):  # QA-01: AC1 on a large directory
    from app.api import admin as admin_module

    monkeypatch.setattr(admin_module, "USER_LIST_CAP", 1)
    await mk_user(db_session, role="overseas_student", full_name="Newer Student")  # the newest row fills the capped page
    admin = await mk_user(db_session, role="overseas_admin")
    code = agencies["account"].student_code
    async with client_for(admin.email) as c:
        capped = (await c.get("/api/v1/admin/users")).json()
        found = (await c.get("/api/v1/admin/users", params={"q": code.lower()})).json()
        by_name = (await c.get("/api/v1/admin/users", params={"q": agencies["account"].full_name})).json()
        too_long = await c.get("/api/v1/admin/users", params={"q": "x" * 101})
    assert str(agencies["account"].id) not in {r["id"] for r in capped}
    assert [r["id"] for r in found] == [str(agencies["account"].id)]
    assert [r["id"] for r in by_name] == [str(agencies["account"].id)]
    assert too_long.status_code == 422
