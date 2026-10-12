"""mgmt-003 -- the business snapshot S1-S15 (spec MS1-MS19; AC1, the accountant 403, deactivated users excluded, one query).

The test database is shared and seeded, so every figure is checked as a delta: read the snapshot, add rows that count and rows that
must not, read it again and compare the increase exactly."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event, select

from app.models import AcademicYear, AgentStudent, Batch, Candidate, Company, Enrollment, OverseasApplication, Program, RecCandidateSource
from app.services import candidates as candidate_svc
from tests.agn001_helpers import mk_active_org
from tests.agn003_helpers import mk_university
from tests.bdm001_helpers import make_user
from tests.enh005_helpers import mk_school
from tests.rec001_helpers import make_recruiter
from tests.upc001_helpers import as_role

pytestmark = pytest.mark.asyncio

SNAPSHOT = "/api/v1/management/snapshot"
KEYS = [
    "total_students", "active_students", "it_training_students", "abroad_education_students", "agent_students", "placement_students",
    "active_agents", "partner_schools", "university_partners", "partner_companies", "trainers", "counselors", "telecallers", "bdms",
    "recruiters",
]  # fmt: skip


async def read(client) -> dict[str, int]:
    response = await client.get(SNAPSHOT)
    assert response.status_code == 200, response.text
    return {kpi["key"]: kpi["value"] for kpi in response.json()["kpis"]}


async def add(db, row):
    db.add(row)
    await db.flush()
    return row


async def batch(db, status: str) -> Batch:
    program = await add(db, Program(slug=f"mgmt003-{uuid.uuid4().hex[:8]}", category="Software Development", title="Python", summary="", duration="8 weeks",
                                    eligibility="", fees=1000, certification="", curriculum=[], placement_assistance="", trainer_name="T", active=True))  # fmt: skip
    return await add(db, Batch(program_id=program.id, name=f"B-{uuid.uuid4().hex[:6]}", start_date=date.today(), end_date=date.today() + timedelta(days=60),
                               schedule="Mon-Fri", status=status))  # fmt: skip


def enrol(student, on: Batch, status: str = "active") -> Enrollment:
    return Enrollment(student_id=student.id, batch_id=on.id, enrollment_code=f"MG3-{uuid.uuid4().hex[:10]}", status=status)


def apply(university, status: str, **owner) -> OverseasApplication:
    return OverseasApplication(university_id=university.id, intake="Fall 2027", status=status, **owner)


async def active_year(db) -> AcademicYear:
    year = await db.scalar(select(AcademicYear).where(AcademicYear.status == "active").limit(1))
    return year or await add(db, AcademicYear(label=f"Y{uuid.uuid4().hex[:8]}", start_date=date.today(), end_date=date.today() + timedelta(days=300)))


async def candidate(db, creator, **fields) -> Candidate:
    source = await db.scalar(select(RecCandidateSource).limit(1))
    return await add(db, Candidate(candidate_code=await candidate_svc.next_code(db), source_id=source.id, created_by_user_id=creator.id,
                                   name="Pool Person", email=f"mg3-{uuid.uuid4().hex[:8]}@example.com", preferred_locations=[], **fields))  # fmt: skip


# --- access (M13: operational tier) ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("role", ["partner", "super_admin"])
async def test_operational_tier_reads_the_snapshot(client, db_session, role):
    await as_role(client, db_session, role, "global")
    response = await client.get(SNAPSHOT)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [kpi["key"] for kpi in body["kpis"]] == KEYS
    assert [kpi["id"] for kpi in body["kpis"]] == [f"S{i}" for i in range(1, 16)]
    assert all(isinstance(kpi["value"], int) and kpi["label"] for kpi in body["kpis"])
    assert date.fromisoformat(body["as_of"])


@pytest.mark.parametrize(("role", "division"), [("accountant", "global"), ("it_admin", "it"), ("overseas_admin", "overseas"), ("trainer", "it")])
async def test_everyone_else_is_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    response = await client.get(SNAPSHOT)
    assert response.status_code == 403
    assert response.json()["detail"] in {"Operational access required", "Management access required"}


async def test_signed_out_is_401(client):
    assert (await client.get(SNAPSHOT)).status_code == 401


async def test_one_statement(db_session):
    """MS17: the fifteen counts are one SELECT, however much data there is."""
    from app.services import management_metrics

    statements = []
    engine = db_session.bind.sync_engine

    def count(*_args):
        statements.append(1)

    event.listen(engine, "before_cursor_execute", count)
    try:
        figures = await management_metrics.snapshot(db_session, date.today())
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert len(statements) == 1
    assert list(figures) == KEYS


# --- AC1: each figure equals its definition ------------------------------------------------------------------------------------
async def test_each_figure_counts_exactly_its_definition(client, db_session):
    db = db_session
    await as_role(client, db, "partner", "global")
    before = await read(client)
    today = date.today()

    # IT students (MS1-MS3): an active batch counts; a completed batch, a withdrawn enrolment and a deactivated user do not.
    running, finished = await batch(db, "active"), await batch(db, "completed")
    it_a = await make_user(db, "it_student", "it")
    it_b = await make_user(db, "it_student", "it")
    it_c = await make_user(db, "it_student", "it", active=False)
    it_d = await make_user(db, "it_student", "it")
    db.add_all([enrol(it_a, running), enrol(it_b, finished), enrol(it_c, running), enrol(it_d, running, "withdrawn")])

    # Overseas students (MS1, MS2, MS4): open counts as active; enrolled is abroad but not active; withdrawn is neither.
    university = await mk_university(db)
    os_e = await make_user(db, "overseas_student", "overseas")
    os_f = await make_user(db, "overseas_student", "overseas")
    os_g = await make_user(db, "overseas_student", "overseas")
    os_h = await make_user(db, "overseas_student", "overseas", active=False)
    db.add_all([apply(university, "offer", student_id=os_e.id), apply(university, "enrolled", student_id=os_f.id),
                apply(university, "withdrawn", student_id=os_g.id), apply(university, "offer", student_id=os_h.id)])  # fmt: skip

    # Agencies (MS1, MS2, MS4, MS5, MS7): an active org's students count; a suspended org's do not; a linked login is counted once.
    agency = await mk_active_org(db, name="MG3 Agency")
    master = agency["master"]
    k = await add(db, AgentStudent(agent_id=master.id, full_name="No Login K", status="active"))
    await add(db, AgentStudent(agent_id=master.id, full_name="No Login L", status="active"))
    await add(db, AgentStudent(agent_id=master.id, full_name="Archived M", status="archived"))
    await add(db, AgentStudent(agent_id=master.id, student_id=os_e.id, status="active"))
    db.add_all([apply(university, "enquiry", agent_student_id=k.id, agent_id=master.id), apply(university, "offer", agent_student_id=k.id, agent_id=master.id)])
    suspended = await mk_active_org(db, name="MG3 Suspended")
    suspended["org"].status = "suspended"
    await add(db, AgentStudent(agent_id=suspended["master"].id, full_name="Suspended N", status="active"))

    # Schools (MS1, MS2, MS4, MS8): a valid tier counts; expired and untiered do not. Students count wherever their school stands.
    valid = await mk_school(db, label="MG3 Valid", students=2, tier_valid_until=today + timedelta(days=30))
    await mk_school(db, label="MG3 Expired", students=0, tier_valid_until=today - timedelta(days=1))
    await mk_school(db, label="MG3 Untiered", students=0, tier=None)
    first, _second = valid["students"]
    first.academic_year_id = (await active_year(db)).id
    db.add(apply(university, "offer", school_student_id=_second.id))

    # Placement pool (MS6): opted in, linked and live only.
    creator = await make_user(db, "placement_team", "it")
    await candidate(db, creator, user_id=it_a.id, opted_in=True)
    await candidate(db, creator, user_id=it_b.id, opted_in=False)
    await candidate(db, creator, user_id=it_c.id, opted_in=True)
    await candidate(db, creator, user_id=it_d.id, opted_in=True, archived_at=datetime.now(UTC))

    # University partners (MS9): the partner group, live and not lost.
    for stage, active, lost in [("active_partner", True, False), ("partner_activated", True, True), ("agreement_signed", True, False), ("active_partner", False, False)]:
        row = await mk_university(db)
        row.stage, row.active = stage, active
        if lost:
            row.lost_at, row.lost_reason = datetime.now(UTC), "other"

    # Partner companies (MS10): past Interested, open.
    for stage, lost, archived in [("meeting_scheduled", False, False), ("joined", False, False), ("interested", False, False), ("joined", True, False), ("joined", False, True)]:
        await add(db, Company(name=f"MG3 Co {uuid.uuid4().hex[:8]}", created_by_user_id=creator.id, stage=stage,
                              lost_at=datetime.now(UTC) if lost else None, lost_reason="other" if lost else None, archived_at=datetime.now(UTC) if archived else None))  # fmt: skip

    # Staff (MS11-MS15): active only; managers and school career counsellors are not counted.
    await make_user(db, "trainer", "it")
    await make_user(db, "trainer", "it", active=False)
    await make_user(db, "counselor", "overseas")
    await make_user(db, "counselor", "it")
    await make_user(db, "career_counselor", "overseas")
    await make_user(db, "telecaller", "it")
    await make_user(db, "telecaller_manager", "global")
    await make_user(db, "bdm", "global")
    await make_user(db, "bdm_manager", "global")
    await make_recruiter(db)
    await make_recruiter(db, active=False)
    await db.commit()

    after = await read(client)
    increase = {key: after[key] - before[key] for key in KEYS}
    assert increase == {
        "total_students": 3 + 3 + 2 + 2,  # it a/b/d; overseas e/f/g; agency K, L (E is the user); school two
        "active_students": 1 + 1 + 1 + 2,  # it a; overseas e; agency K; school first (year) and second (open application)
        "it_training_students": 1,
        "abroad_education_students": 2 + 1 + 1,  # e, f; agency K once; school second
        "agent_students": 3,  # K, L and the linked E
        "placement_students": 1,
        "active_agents": 1,
        "partner_schools": 1,
        "university_partners": 1,
        "partner_companies": 2,
        "trainers": 1,
        "counselors": 2,
        "telecallers": 1,
        "bdms": 1,
        "recruiters": 1 + 0,  # creator is placement_team without a profile
    }
