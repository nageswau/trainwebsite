"""AGN-004 -- list, create, detail and the duplicate warning (spec §5.4-§5.5; AC01, AC02, AC05, AC07, AC08, AC11)."""

import asyncio
import logging
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.api import agent_students as router_module
from app.models import AgentStudent, AuditLog, User
from tests.agn001_helpers import client_for, login, mk_active_org, mk_user
from tests.agn004_helpers import RECORDS, mk_record, mk_staff


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    # alembic's fileConfig (run by test_agn_004_migration.py and other migration tests) disables loggers that already exist;
    # re-enable ours so the log assertions do not depend on test order (the test_enh_015_progress_report.py precedent).
    logging.getLogger("app.agent_students").disabled = False
    yield


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.local"


@pytest_asyncio.fixture
async def agency(db_session):
    ctx = await mk_active_org(db_session, name="Records Agency")
    other = await mk_active_org(db_session, name="Other Agency")
    s1 = await mk_staff(db_session, ctx["org"], full_name="Rec Staff One")
    s2 = await mk_staff(db_session, ctx["org"], full_name="Rec Staff Two")
    return ctx | {"other": other, "s1": s1, "s2": s2, "tag": uuid.uuid4().hex[:8]}


@pytest.mark.asyncio
async def test_master_creates_a_student_with_no_login_and_no_user_row(db_session, agency):
    users_before = await db_session.scalar(select(func.count()).select_from(User))
    async with client_for(agency["master"].email) as c:
        response = await c.post(RECORDS, json={"full_name": "Asha Rao", "email": _email("asha"), "preferred_country": "Canada"})
    assert response.status_code == 201, response.text
    body = response.json()["student"]
    assert body["has_login"] is False and body["assigned_to"] is None and body["status"] == "active"
    assert await db_session.scalar(select(func.count()).select_from(User)) == users_before
    row = await db_session.get(AgentStudent, uuid.UUID(body["id"]), populate_existing=True)
    assert row.student_id is None and row.agent_id == agency["master"].id
    assert set(body) >= {"id", "has_login", "full_name", "email", "phone", "preferred_country", "preferred_intake", "status", "assigned_to", "created_at"}
    assert not {"agent_id", "student_id", "phone_digits"} & set(body)


@pytest.mark.asyncio
async def test_staff_creation_is_assigned_to_the_creator(agency):
    async with client_for(agency["s1"]["user"].email) as c:
        body = (await c.post(RECORDS, json={"full_name": "Staff Made"})).json()["student"]
    assert body["assigned_to"]["id"] == str(agency["s1"]["member"].id) and body["assigned_to"]["code"].endswith("-S001")


@pytest.mark.asyncio
async def test_staff_list_and_detail_are_assigned_only(db_session, agency):
    mine = await mk_record(db_session, agent=agency["master"], full_name="Mine Rec", assigned_member=agency["s1"]["member"])
    theirs = await mk_record(db_session, agent=agency["master"], full_name="Theirs Rec", assigned_member=agency["s2"]["member"])
    unassigned = await mk_record(db_session, agent=agency["master"], full_name="Nobody Rec")
    foreign = await mk_record(db_session, agent=agency["other"]["master"], full_name="Foreign Rec")
    async with client_for(agency["s1"]["user"].email) as c:
        ids = {i["id"] for i in (await c.get(RECORDS)).json()["items"]}
        codes = {sid: (await c.get(f"{RECORDS}/{sid}")).status_code for sid in (mine.id, theirs.id, unassigned.id, foreign.id)}
        filtered = await c.get(RECORDS, params={"assigned": "none"})
    assert ids == {str(mine.id)}
    assert codes == {mine.id: 200, theirs.id: 404, unassigned.id: 404, foreign.id: 404}
    assert filtered.status_code == 422


@pytest.mark.asyncio
async def test_other_agency_master_gets_404_and_never_sees_rows(db_session, agency):
    row = await mk_record(db_session, agent=agency["master"], full_name="Private Rec")
    async with client_for(agency["other"]["master"].email) as c:
        assert (await c.get(f"{RECORDS}/{row.id}")).status_code == 404
        assert str(row.id) not in {i["id"] for i in (await c.get(RECORDS)).json()["items"]}


@pytest.mark.asyncio
async def test_list_filters_paging_and_archived(db_session, agency):
    tag = agency["tag"]
    a = await mk_record(db_session, agent=agency["master"], full_name=f"Paging Alpha {tag}", assigned_member=agency["s1"]["member"])
    b = await mk_record(db_session, agent=agency["master"], full_name=f"Paging Beta {tag}", status="archived")
    async with client_for(agency["master"].email) as c:
        default = {i["id"] for i in (await c.get(RECORDS, params={"q": tag})).json()["items"]}
        everything = {i["id"] for i in (await c.get(RECORDS, params={"q": tag, "include_archived": "true"})).json()["items"]}
        page = (await c.get(RECORDS, params={"q": tag, "include_archived": "true", "limit": 1})).json()
        by_member = {i["id"] for i in (await c.get(RECORDS, params={"q": tag, "include_archived": "true", "assigned": str(agency["s1"]["member"].id)})).json()["items"]}
        unassigned = {i["id"] for i in (await c.get(RECORDS, params={"q": tag, "include_archived": "true", "assigned": "none"})).json()["items"]}
        bad = [(await c.get(RECORDS, params=p)).status_code for p in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"q": "x" * 101}, {"assigned": "someone"})]
    assert default == {str(a.id)} and everything == {str(a.id), str(b.id)}
    assert page["total"] == 2 and len(page["items"]) == 1 and page["limit"] == 1 and page["offset"] == 0
    assert by_member == {str(a.id)} and unassigned == {str(b.id)}
    assert bad == [422] * 5


@pytest.mark.asyncio
async def test_search_metacharacters_match_literally(db_session, agency):
    tag = agency["tag"]
    await mk_record(db_session, agent=agency["master"], full_name=f"Percent 100% {tag}")
    await mk_record(db_session, agent=agency["master"], full_name=f"Plain 1000 {tag}")
    async with client_for(agency["master"].email) as c:
        names = {i["full_name"] for i in (await c.get(RECORDS, params={"q": f"100% {tag}"})).json()["items"]}
        underscore = (await c.get(RECORDS, params={"q": f"_{tag}"})).json()["items"]
    assert names == {f"Percent 100% {tag}"} and underscore == []


@pytest.mark.asyncio
async def test_duplicate_email_warns_then_saves_with_confirmation(db_session, agency):
    email = _email("dup")
    await mk_record(db_session, agent=agency["master"], full_name="First Dup", email=email, status="archived")
    async with client_for(agency["master"].email) as c:
        warned = await c.post(RECORDS, json={"full_name": "Second Dup", "email": email.upper()})
        saved = await c.post(RECORDS, json={"full_name": "Second Dup", "email": email.upper(), "confirm_duplicate": True})
    detail = warned.json()["detail"]
    assert warned.status_code == 409 and detail["code"] == "possible_duplicate" and detail["message"]
    assert detail["matches"][0]["matched_on"] == ["email"] and detail["matches"][0]["status"] == "archived" and detail["hidden_matches"] == 0
    assert saved.status_code == 201
    override = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_student.duplicate_override", AuditLog.entity_id == saved.json()["student"]["id"]))
    assert override is not None and email not in str(override.metadata_json)


@pytest.mark.asyncio
async def test_phone_formats_match_on_digits_only(db_session, agency):
    digits = str(uuid.uuid4().int)[:10]
    await mk_record(db_session, agent=agency["master"], full_name="Phone One", phone=f"+{digits[:2]} {digits[2:7]}-{digits[7:]}")
    async with client_for(agency["master"].email) as c:
        same = await c.post(RECORDS, json={"full_name": "Phone Two", "phone": f"({digits[:2]}) {digits[2:]}"})
        await c.post(RECORDS, json={"full_name": "Phone Three", "phone": "12-34"})
        short = await c.post(RECORDS, json={"full_name": "Phone Four", "phone": "1234"})
    assert same.status_code == 409 and same.json()["detail"]["matches"][0]["matched_on"] == ["phone"]
    assert short.status_code == 201  # fewer than 7 digits never counts as a match


@pytest.mark.asyncio
async def test_linked_student_account_email_counts_as_a_duplicate(db_session, agency):
    student = await mk_user(db_session, role="overseas_student", full_name="Linked Dup")
    db_session.add(AgentStudent(agent_id=agency["master"].id, student_id=student.id, status="active"))
    await db_session.commit()
    async with client_for(agency["master"].email) as c:
        response = await c.post(RECORDS, json={"full_name": "Typed Again", "email": student.email})
    assert response.status_code == 409 and response.json()["detail"]["matches"][0]["has_login"] is True


@pytest.mark.asyncio
async def test_other_agency_never_triggers_the_warning(db_session, agency):
    email = _email("elsewhere")
    await mk_record(db_session, agent=agency["other"]["master"], full_name="Elsewhere", email=email)
    async with client_for(agency["master"].email) as c:
        assert (await c.post(RECORDS, json={"full_name": "Here", "email": email})).status_code == 201


@pytest.mark.asyncio
async def test_staff_see_invisible_matches_only_as_a_count(db_session, agency):
    email = _email("hidden")
    await mk_record(db_session, agent=agency["master"], full_name="Hidden Match", email=email, assigned_member=agency["s2"]["member"])
    async with client_for(agency["s1"]["user"].email) as c:
        detail = (await c.post(RECORDS, json={"full_name": "Probe", "email": email})).json()["detail"]
    assert detail["matches"] == [] and detail["hidden_matches"] == 1
    assert "Hidden Match" not in str(detail)


@pytest.mark.asyncio
async def test_concurrent_creates_with_one_email_save_once(agency):
    email = _email("race")
    async with client_for(agency["master"].email) as c1, client_for(agency["master"].email) as c2:
        results = await asyncio.gather(c1.post(RECORDS, json={"full_name": "Racer A", "email": email}), c2.post(RECORDS, json={"full_name": "Racer B", "email": email}))
    assert sorted(r.status_code for r in results) == [201, 409]


@pytest.mark.asyncio
async def test_super_admin_is_not_admitted(db_session):
    admin = await mk_user(db_session, role="super_admin", division="global")
    async with client_for(admin.email) as c:  # a super_admin may sign in through any division
        assert (await c.get(RECORDS)).status_code == 403


@pytest.mark.asyncio
async def test_create_writes_an_audit_row_without_personal_data(db_session, agency, caplog):
    caplog.set_level(logging.INFO, logger="app.agent_students")
    email, name, phone = _email("audit"), f"Audit Me {agency['tag']}", "9" + str(uuid.uuid4().int)[:9]
    async with client_for(agency["master"].email) as c:
        sid = (await c.post(RECORDS, json={"full_name": name, "email": email, "phone": phone})).json()["student"]["id"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_student.create", AuditLog.entity_id == sid))
    assert audit is not None and "agent_student_created" in caplog.text
    for secret in (name, email, phone):
        assert secret not in str(audit.metadata_json) and secret not in caplog.text


def _boom(*args, **kwargs):
    raise RuntimeError("simulated audit-log write failure")


@pytest.mark.asyncio
async def test_create_fails_closed_if_the_audit_write_fails(db_session, agency, monkeypatch, client):
    name = f"Never Saved {agency['tag']}"
    await login(client, agency["master"].email)
    monkeypatch.setattr(router_module, "AuditLog", _boom)
    with pytest.raises(RuntimeError, match="simulated audit-log write failure"):
        await client.post(RECORDS, json={"full_name": name})
    assert await db_session.scalar(select(AgentStudent).where(AgentStudent.full_name == name)) is None


@pytest.mark.asyncio
async def test_server_owned_fields_are_refused(agency):
    async with client_for(agency["s1"]["user"].email) as c:
        response = await c.post(RECORDS, json={"full_name": "Sneaky", "assigned_member_id": str(agency["s2"]["member"].id)})
    assert response.status_code == 422
