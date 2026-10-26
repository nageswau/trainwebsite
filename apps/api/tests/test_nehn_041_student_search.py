"""nehn-041 (DEC-SCOPE-291 S1-S9) -- GET /search/students: one box across the student kinds a caller may already see (IT, overseas,
agency students with no login, school students), by Student ID, name, email, phone in any format, course or agency, each kind capped
and scoped; every search audited without its text and throttled at 30 a minute."""

import datetime
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentStudent, AuditLog, Batch, Enrollment, OverseasStudentCounselor, Program
from app.services import student_search
from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn002_helpers import mk_staff
from tests.agn004_helpers import mk_record
from tests.enh005_helpers import mk_school
from tests.enh031_helpers import mk_application, mk_course, mk_university

SEARCH = "/api/v1/search/students"
KINDS = ("it_student", "overseas_student", "agency_student", "school_student")


def _digits() -> str:
    """Ten digits no other test row holds, so a phone search is exact even on the shared database."""
    return "7" + str(uuid.uuid4().int)[:9]


def _code() -> str:
    return uuid.uuid4().hex[:8].upper()


async def _enrol(db, student, title: str) -> Program:
    program = Program(
        slug=f"n041-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=title,
        summary="",
        duration="8 weeks",
        eligibility="",
        fees=1000,
        certification="",
        curriculum=[],
        placement_assistance="",
        trainer_name="T",
        active=True,
    )
    db.add(program)
    await db.flush()
    batch = Batch(
        program_id=program.id,
        name=f"B-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=60),
        schedule="Mon-Fri",
        capacity=20,
        enrollment_open=True,
        status="active",
    )
    db.add(batch)
    await db.flush()
    db.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"N041-{uuid.uuid4().hex[:8]}"))
    await db.commit()
    return program


@pytest_asyncio.fixture
async def world(db_session):
    db = db_session
    tag = uuid.uuid4().hex[:6]
    w: dict = {"tag": tag, "phone": _digits()}
    w["super"] = await mk_user(db, role="super_admin", division="global", full_name=f"Super {tag}")
    w["it_admin"] = await mk_user(db, role="it_admin", division="it", full_name=f"IT Admin {tag}")
    w["ov_admin"] = await mk_user(db, role="overseas_admin", full_name=f"Ov Admin {tag}")
    w["counselor"] = await mk_user(db, role="counselor", full_name=f"Counselor {tag}")
    w["it_student"] = await mk_user(db, role="it_student", division="it", full_name=f"Ivy Turing {tag}")
    w["it_student"].student_code, w["it_student"].phone = _code(), f"+91 {w['phone'][:5]}-{w['phone'][5:]}"
    w["program"] = await _enrol(db, w["it_student"], f"Quantum Rust {tag}")
    w["ov_student"] = await mk_user(db, role="overseas_student", full_name=f"Olga Seas {tag}")
    w["ov_student"].student_code = _code()
    w["ov_other"] = await mk_user(db, role="overseas_student", full_name=f"Olga Other {tag}")
    w["linked"] = await mk_user(db, role="overseas_student", full_name=f"Olga Linked {tag}")
    db.add(OverseasStudentCounselor(student_user_id=w["linked"].id, counselor_user_id=w["counselor"].id, assigned_by_user_id=w["ov_admin"].id))
    await db.commit()
    university = await mk_university(db)
    w["course"] = await mk_course(db, university, f"MSc Comets {tag}")
    await mk_application(db, student=w["ov_student"], university=university, counselor=w["counselor"], course=w["course"])
    w["agency"] = await mk_active_org(db, name=f"Agency {tag}")
    w["other_agency"] = await mk_active_org(db, name=f"Rival {tag}")
    w["staff"] = await mk_staff(db, w["agency"]["org"], full_name=f"Staff {tag}")
    w["record"] = await mk_record(db, agent=w["agency"]["master"], full_name=f"Olga Record {tag}", email=f"olga.record.{tag}@example.local")
    w["record"].student_code = _code()
    w["assigned"] = await mk_record(db, agent=w["agency"]["master"], full_name=f"Olga Assigned {tag}", assigned_member=w["staff"]["member"])
    w["rival_record"] = await mk_record(db, agent=w["other_agency"]["master"], full_name=f"Olga Rival {tag}")
    db.add(AgentStudent(agent_id=w["agency"]["master"].id, student_id=w["ov_other"].id, status="active"))
    school = await mk_school(db, label=f"Olga School {tag}", students=1, with_teacher=False)
    w["school"], w["school_student"], w["coordinator"] = school["school"], school["students"][0], school["coordinator"]
    w["school_student"].full_name = f"Olga Pupil {tag}"
    await db.commit()
    return w


async def _search(c, q, **params):
    r = await c.get(SEARCH, params={"q": q, **params})
    assert r.status_code == 200, r.text
    data = r.json()
    return data, {kind: {i["id"] for i in group["items"]} for kind, group in data["groups"].items()}


def _ids(*rows) -> set[str]:
    return {str(r.id) for r in rows}


@pytest.mark.asyncio
async def test_super_admin_finds_every_kind_by_name(world):
    async with client_for(world["super"].email, "global") as c:
        _, hits = await _search(c, world["tag"])
    assert set(hits) == set(KINDS)
    assert _ids(world["it_student"]) <= hits["it_student"]
    assert _ids(world["ov_student"], world["ov_other"], world["linked"]) <= hits["overseas_student"]
    assert _ids(world["record"], world["assigned"], world["rival_record"]) <= hits["agency_student"]
    assert _ids(world["school_student"]) <= hits["school_student"]


@pytest.mark.asyncio
async def test_phone_in_any_format_finds_the_student(world):  # AC1
    digits = world["phone"]
    async with client_for(world["super"].email, "global") as c:
        for q in (digits, f"+91 {digits[:5]} {digits[5:]}", f"0{digits[:5]}-{digits[5:]}", f"({digits[:3]}) {digits[3:6]}.{digits[6:]}", f"91{digits}"):
            _, hits = await _search(c, q)
            assert hits["it_student"] == _ids(world["it_student"]), q


@pytest.mark.asyncio
async def test_student_id_and_email_match(world):
    async with client_for(world["super"].email, "global") as c:
        _, hits = await _search(c, world["it_student"].student_code.lower())
        assert hits["it_student"] == _ids(world["it_student"])
        _, hits = await _search(c, world["record"].student_code)
        assert hits["agency_student"] == _ids(world["record"])
        _, hits = await _search(c, world["school_student"].student_code)
        assert hits["school_student"] == _ids(world["school_student"])
        _, hits = await _search(c, f"OLGA.RECORD.{world['tag']}")
        assert hits["agency_student"] == _ids(world["record"])


@pytest.mark.asyncio
async def test_course_name_returns_enrolled_and_applied_students(world):  # AC2
    async with client_for(world["super"].email, "global") as c:
        _, hits = await _search(c, f"quantum rust {world['tag']}")
        assert hits["it_student"] == _ids(world["it_student"])
        _, hits = await _search(c, f"MSc Comets {world['tag']}")
        assert hits["overseas_student"] == _ids(world["ov_student"])


@pytest.mark.asyncio
async def test_agency_name_and_school_name_match(world):
    async with client_for(world["super"].email, "global") as c:
        _, hits = await _search(c, world["agency"]["org"].prefix)  # the agency code (other agencies may share its letters)
        assert _ids(world["record"], world["assigned"]) <= hits["agency_student"]
        _, hits = await _search(c, world["agency"]["org"].name)
        assert hits["agency_student"] == _ids(world["record"], world["assigned"])
        _, hits = await _search(c, world["school"].name)
        assert hits["school_student"] == _ids(world["school_student"])


@pytest.mark.asyncio
async def test_it_admin_sees_it_students_only(world):  # AC3
    async with client_for(world["it_admin"].email, "it") as c:
        data, hits = await _search(c, world["tag"])
    assert set(hits) == {"it_student"} and _ids(world["it_student"]) <= hits["it_student"]


@pytest.mark.asyncio
async def test_overseas_admin_sees_overseas_and_agency_students(world):
    async with client_for(world["ov_admin"].email) as c:
        _, hits = await _search(c, world["tag"])
    assert set(hits) == {"overseas_student", "agency_student"}
    assert _ids(world["ov_student"], world["ov_other"], world["linked"]) <= hits["overseas_student"]
    assert _ids(world["record"], world["assigned"], world["rival_record"]) <= hits["agency_student"]


@pytest.mark.asyncio
async def test_counselor_finds_only_their_students(world):  # AC3
    async with client_for(world["counselor"].email) as c:
        _, hits = await _search(c, "Olga")
        assert set(hits) == {"overseas_student"} and hits["overseas_student"] == _ids(world["ov_student"], world["linked"])
        _, hits = await _search(c, f"Olga Other {world['tag']}")
        assert hits["overseas_student"] == set()


@pytest.mark.asyncio
async def test_agent_finds_only_own_agency(world):  # AC3
    async with client_for(world["agency"]["master"].email) as c:
        _, hits = await _search(c, world["tag"])
    assert set(hits) == {"overseas_student", "agency_student"}
    assert hits["agency_student"] == _ids(world["record"], world["assigned"])  # the rival agency's row never matches
    assert hits["overseas_student"] == _ids(world["ov_other"])  # a linked student appears once, as their account


@pytest.mark.asyncio
async def test_agent_staff_finds_only_assigned_students(world):
    async with client_for(world["staff"]["user"].email) as c:
        _, hits = await _search(c, world["tag"])
    assert hits["agency_student"] == _ids(world["assigned"]) and hits["overseas_student"] == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("telecaller_manager", "overseas"), ("it_student", "it"), ("trainer", "it"), ("school_coordinator", "overseas")])
async def test_other_roles_are_refused(db_session, role, division):
    user = await mk_user(db_session, role=role, division=division)
    async with client_for(user.email, division) as c:
        r = await c.get(SEARCH, params={"q": "anything"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_an_it_counselor_is_refused(db_session):
    user = await mk_user(db_session, role="counselor", division="it")
    async with client_for(user.email, "it") as c:
        assert (await c.get(SEARCH, params={"q": "anything"})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("q", ["a", "ab", "  a  ", "x" * 101])
async def test_short_or_long_query_is_422(world, q):  # AC5
    async with client_for(world["super"].email, "global") as c:
        assert (await c.get(SEARCH, params={"q": q})).status_code == 422


@pytest.mark.asyncio
async def test_filters_narrow_the_kinds(world):
    async with client_for(world["super"].email, "global") as c:
        _, hits = await _search(c, world["tag"], type="school_student")
        assert set(hits) == {"school_student"}
        _, hits = await _search(c, world["tag"], division="overseas")
        assert set(hits) == {"overseas_student", "agency_student"}
        _, hits = await _search(c, world["tag"], program=str(world["program"].id))
        assert hits == {"it_student": _ids(world["it_student"])}
        for bad in ({"type": "lead"}, {"division": "mars"}, {"program": "nope"}):
            assert (await c.get(SEARCH, params={"q": world["tag"], **bad})).status_code == 422
    async with client_for(world["it_admin"].email, "it") as c:
        _, hits = await _search(c, world["tag"], type="school_student")
        assert hits == {}


@pytest.mark.asyncio
async def test_items_carry_code_detail_and_links(world):  # AC6
    async with client_for(world["super"].email, "global") as c:
        data, _ = await _search(c, world["it_student"].student_code)
        item = data["groups"]["it_student"]["items"][0]
        assert item["label"] == world["it_student"].full_name and item["code"] == world["it_student"].student_code
        assert f"Quantum Rust {world['tag']}" in item["detail"] and item["href"] == f"/admin/users?q={world['it_student'].student_code}"
        data, _ = await _search(c, world["record"].student_code)
        assert data["groups"]["agency_student"]["items"][0]["href"] == f"/overseas/admin/agent-network/{world['agency']['org'].id}"
        data, _ = await _search(c, world["school_student"].student_code)
        school_item = data["groups"]["school_student"]["items"][0]
        assert school_item["href"] is None and world["school"].name in school_item["detail"]
    async with client_for(world["it_admin"].email, "it") as c:
        data, _ = await _search(c, world["it_student"].student_code)
        assert data["groups"]["it_student"]["items"][0]["href"] == f"/it/admin/students?q={world['it_student'].student_code}"
    async with client_for(world["ov_admin"].email) as c:
        data, _ = await _search(c, world["ov_student"].student_code)
        assert data["groups"]["overseas_student"]["items"][0]["href"] == f"/overseas/admin/students/{world['ov_student'].id}"
        data, _ = await _search(c, world["record"].student_code)
        assert data["groups"]["agency_student"]["items"][0]["href"] == f"/overseas/admin/agent-network/{world['agency']['org'].id}"
    async with client_for(world["counselor"].email) as c:
        data, _ = await _search(c, world["ov_student"].student_code)
        assert data["groups"]["overseas_student"]["items"][0]["href"] == f"/overseas/counselor/students/{world['ov_student'].id}"
    async with client_for(world["agency"]["master"].email) as c:
        data, _ = await _search(c, world["record"].student_code)
        assert data["groups"]["agency_student"]["items"][0]["href"] == "/overseas/agent/students"


@pytest.mark.asyncio
async def test_wildcards_are_literal(world):
    async with client_for(world["super"].email, "global") as c:
        _, hits = await _search(c, "%_%")
    assert all(not ids for ids in hits.values())


@pytest.mark.asyncio
async def test_each_kind_is_capped(world, monkeypatch):
    monkeypatch.setattr(student_search, "GROUP_LIMIT", 1)
    async with client_for(world["super"].email, "global") as c:
        data, _ = await _search(c, world["tag"])
    group = data["groups"]["agency_student"]
    assert len(group["items"]) == 1 and group["more"] is True


@pytest.mark.asyncio
async def test_every_search_is_audited_without_its_text(world, db_session):  # AC7
    async with client_for(world["counselor"].email) as c:
        await _search(c, f"Olga Seas {world['tag']}")
    row = await db_session.scalar(select(AuditLog).where(AuditLog.user_id == world["counselor"].id, AuditLog.action == student_search.AUDIT_ACTION))
    assert row.metadata_json == {"overseas_student": 1}
    assert world["tag"] not in str(row.metadata_json)


@pytest.mark.asyncio
async def test_the_31st_search_in_a_minute_is_429(world, db_session):  # AC7
    db_session.add_all(AuditLog(user_id=world["ov_admin"].id, action=student_search.AUDIT_ACTION, entity_type="search", outcome="searched", metadata_json={}) for _ in range(student_search.RATE_LIMIT))
    await db_session.commit()
    async with client_for(world["ov_admin"].email) as c:
        r = await c.get(SEARCH, params={"q": world["tag"]})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    count = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id == world["ov_admin"].id, AuditLog.action == student_search.AUDIT_ACTION))
    assert count == student_search.RATE_LIMIT  # a refused search writes nothing
