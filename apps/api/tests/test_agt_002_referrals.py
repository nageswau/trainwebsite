"""AGT-002 -- Referred-student roster and status.

`GET /portal/overseas/agent/students` and `GET /portal/overseas/agent/applications`
already existed, already self-scoped (`agent_id == user.id`) and already denied a
Pending/Rejected agent via `agent_is_approved()` (inherited from `AGT-001`'s fix). The
real, confirmed gap against `AGT-002`'s "roster of referred students and each one's
application status" wording: the students roster only ever showed the `AgentStudent`
link's own status (an "active"/"inactive" flag), never the referred student's actual
`OverseasApplication` status -- an agent had to cross-reference a second page by name to
see it. Fixed in `apps/api/app/services/portal.py`'s `_agent()` "students" branch by
joining in each student's most recent application (reusing the query already scoped to
this agent, no new query, no schema change per `DATA_MODEL.md` #6.8's "DB impact: N").
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import (
    AgentStudent,
    Country,
    OverseasApplication,
    University,
    User,
    UserRoleAssignment,
)


async def _create_user(db_session, *, role: str, division: str = "overseas", **overrides) -> User:
    defaults = dict(
        email=f"agt002-{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role.title()}",
        role=role,
        division=division,
        active=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    await db_session.commit()
    return user


async def _create_agent(db_session, *, approval_status: str = "approved") -> User:
    agent = await _create_user(db_session, role="agent")
    db_session.add(UserRoleAssignment(user_id=agent.id, division="overseas", role="agent", approval_status=approval_status))
    await db_session.commit()
    return agent


async def _make_university(db_session) -> University:
    country = Country(
        slug=f"agt002-country-{uuid.uuid4().hex[:8]}",
        name="Testland",
        overview="A test destination.",
        tuition="USD 20,000/year",
        living_expenses="USD 1,000/month",
        visa_process=[],
        work_opportunities="",
        post_study_work="",
        pr_opportunities="",
        faq=[],
    )
    db_session.add(country)
    await db_session.flush()
    university = University(
        country_id=country.id,
        slug=f"agt002-university-{uuid.uuid4().hex[:8]}",
        name=f"AGT-002 Test University {uuid.uuid4().hex[:8]}",
        city="Testville",
        overview="A test university.",
        eligibility="",
        requirements=[],
        deadlines=[],
        scholarships=[],
    )
    db_session.add(university)
    await db_session.commit()
    return university


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_agent_roster_shows_referred_student_with_application_status(client, db_session):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    db_session.add(AgentStudent(agent_id=agent.id, student_id=student.id, status="active"))
    db_session.add(
        OverseasApplication(
            student_id=student.id,
            university_id=university.id,
            agent_id=agent.id,
            status="university_review",
            next_action="Await the university decision",
            intake="September 2027",
        )
    )
    await db_session.commit()

    await _login(client, agent.email)
    response = await client.get("/api/v1/portal/overseas/agent/students")
    assert response.status_code == 200
    rows = response.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["student"] == student.full_name
    assert rows[0]["application_status"] == "university_review"
    assert rows[0]["university"] == university.name


@pytest.mark.asyncio
async def test_referred_student_without_an_application_shows_as_not_yet_applied(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    db_session.add(AgentStudent(agent_id=agent.id, student_id=student.id, status="active"))
    await db_session.commit()

    await _login(client, agent.email)
    response = await client.get("/api/v1/portal/overseas/agent/students")
    assert response.status_code == 200
    rows = response.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["application_status"] == "No application yet"


@pytest.mark.asyncio
async def test_agent_never_sees_another_agents_referrals(db_session, client):
    agent_a = await _create_agent(db_session)
    agent_b = await _create_agent(db_session)
    student_a = await _create_user(db_session, role="overseas_student", full_name="Referral Student A")
    student_b = await _create_user(db_session, role="overseas_student", full_name="Referral Student B")
    db_session.add(AgentStudent(agent_id=agent_a.id, student_id=student_a.id, status="active"))
    db_session.add(AgentStudent(agent_id=agent_b.id, student_id=student_b.id, status="active"))
    await db_session.commit()

    await _login(client, agent_a.email)
    response = await client.get("/api/v1/portal/overseas/agent/students")
    assert response.status_code == 200
    names = {row["student"] for row in response.json()["rows"]}
    assert names == {student_a.full_name}
    assert student_b.full_name not in names


@pytest.mark.asyncio
async def test_pending_agent_is_denied_the_referral_roster(db_session, client):
    agent = await _create_agent(db_session, approval_status="pending")
    await _login(client, agent.email)
    response = await client.get("/api/v1/portal/overseas/agent/students")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_rejected_agent_is_denied_the_referral_roster(db_session, client):
    agent = await _create_agent(db_session, approval_status="rejected")
    await _login(client, agent.email)
    response = await client.get("/api/v1/portal/overseas/agent/students")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_referral_roster_requires_authentication(client):
    response = await client.get("/api/v1/portal/overseas/agent/students")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_agent_role_cannot_view_the_referral_roster(db_session, client):
    counselor = await _create_user(db_session, role="counselor")
    await _login(client, counselor.email)
    response = await client.get("/api/v1/portal/overseas/agent/students")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_applications_list_used_alongside_the_roster_is_also_self_scoped(db_session, client):
    """`AGT-002-AC01`'s status view is the roster + the existing applications section --
    confirm the latter is (still) agent_id-scoped, not just the roster itself."""
    agent_a = await _create_agent(db_session)
    agent_b = await _create_agent(db_session)
    student_a = await _create_user(db_session, role="overseas_student", full_name="Application Student A")
    student_b = await _create_user(db_session, role="overseas_student", full_name="Application Student B")
    university = await _make_university(db_session)
    db_session.add(OverseasApplication(student_id=student_a.id, university_id=university.id, agent_id=agent_a.id, status="enquiry", intake="September 2027"))
    db_session.add(OverseasApplication(student_id=student_b.id, university_id=university.id, agent_id=agent_b.id, status="enquiry", intake="September 2027"))
    await db_session.commit()

    await _login(client, agent_a.email)
    response = await client.get("/api/v1/portal/overseas/agent/applications")
    assert response.status_code == 200
    students_seen = {row["student"] for row in response.json()["rows"]}
    assert students_seen == {student_a.full_name}
