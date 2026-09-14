"""AGT-003 -- Commission accrual (automatic trigger).

`DATA_MODEL.md` #6.3 (`ADR-012` resolution): the automatic commission-accrual trigger
fires when an `ApplicationStatusHistory` row is written with `to_status='enrolled'` for
an application that has an assigned `agent_id`. Implemented as `_maybe_trigger_agent_
commission()` in `apps/api/app/api/workflows.py`, called from both existing status-
change write sites (`PATCH /overseas/applications/{id}` and
`POST /overseas/applications/{id}/advance`) -- the trigger is about the status
transition itself, regardless of which endpoint performed it. Real, confirmed gap found
in the base codebase's existing manual-commission-creation endpoint
(`POST /overseas/agent/commissions`): it never checked the application had reached
`enrolled` at all -- an Overseas Admin could create a commission for an application still
at `enquiry` (`AGT-003-AC03`). Also added the missing `PATCH .../commissions/{id}`
Overseas-Admin-only "set/adjust amount" action (`AGT-003-AC02`) -- no endpoint existed for
an Admin to put a real amount on a system-triggered `estimated` row (amount=0, since no
fixed commission rate is confirmed, `DEC-SCOPE-005`).
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import (
    AgentCommission,
    AgentStudent,
    Country,
    OverseasApplication,
    University,
    User,
    UserRoleAssignment,
)


async def _create_user(db_session, *, role: str, division: str = "overseas", **overrides) -> User:
    defaults = dict(
        email=f"agt003-{role}-{uuid.uuid4().hex[:8]}@example.local",
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


async def _create_agent(db_session) -> User:
    agent = await _create_user(db_session, role="agent")
    db_session.add(UserRoleAssignment(user_id=agent.id, division="overseas", role="agent", approval_status="approved"))
    await db_session.commit()
    return agent


async def _make_university(db_session) -> University:
    country = Country(
        slug=f"agt003-country-{uuid.uuid4().hex[:8]}",
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
        slug=f"agt003-university-{uuid.uuid4().hex[:8]}",
        name=f"AGT-003 Test University {uuid.uuid4().hex[:8]}",
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


async def _make_application(db_session, *, agent, student, university, status="status_tracking") -> OverseasApplication:
    application = OverseasApplication(
        student_id=student.id,
        university_id=university.id,
        agent_id=agent.id if agent else None,
        status=status,
        next_action="",
        intake="September 2027",
    )
    db_session.add(application)
    await db_session.commit()
    return application


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


async def _create_counselor(db_session) -> User:
    return await _create_user(db_session, role="counselor")


async def _create_overseas_admin(db_session) -> User:
    return await _create_user(db_session, role="overseas_admin")


@pytest.mark.asyncio
async def test_advancing_to_enrolled_auto_creates_an_estimated_commission(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    counselor = await _create_counselor(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university)
    application.counselor_id = counselor.id
    await db_session.commit()

    await _login(client, counselor.email)
    response = await client.post(f"/api/v1/workflows/overseas/applications/{application.id}/advance", json={"to_status": "enrolled"})
    assert response.status_code == 200

    commission = await db_session.scalar(select(AgentCommission).where(AgentCommission.application_id == application.id))
    assert commission is not None
    assert commission.agent_id == agent.id
    assert commission.status == "estimated"
    assert float(commission.amount) == 0
    assert commission.created_by == "system_trigger"


@pytest.mark.asyncio
async def test_generic_patch_reaching_enrolled_also_triggers_the_commission(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university)

    await _login(client, admin.email)
    response = await client.patch(f"/api/v1/workflows/overseas/applications/{application.id}", json={"status": "enrolled"})
    assert response.status_code == 200

    commission = await db_session.scalar(select(AgentCommission).where(AgentCommission.application_id == application.id))
    assert commission is not None
    assert commission.created_by == "system_trigger"


@pytest.mark.asyncio
async def test_no_commission_when_the_application_has_no_agent(db_session, client):
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    counselor = await _create_counselor(db_session)
    application = await _make_application(db_session, agent=None, student=student, university=university)
    application.counselor_id = counselor.id
    await db_session.commit()

    await _login(client, counselor.email)
    response = await client.post(f"/api/v1/workflows/overseas/applications/{application.id}/advance", json={"to_status": "enrolled"})
    assert response.status_code == 200

    commission = await db_session.scalar(select(AgentCommission).where(AgentCommission.application_id == application.id))
    assert commission is None


@pytest.mark.asyncio
async def test_no_duplicate_commission_on_a_second_write_at_enrolled(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university, status="enrolled")

    await _login(client, admin.email)
    # Re-saving the same status (still "enrolled") must not create a second row.
    response = await client.patch(f"/api/v1/workflows/overseas/applications/{application.id}", json={"next_action": "Orientation next week"})
    assert response.status_code == 200

    count = (await db_session.execute(select(AgentCommission).where(AgentCommission.application_id == application.id))).scalars().all()
    assert len(count) == 0  # never reached "enrolled" *through this session* (already was) -- no trigger fires


@pytest.mark.asyncio
async def test_admin_manual_commission_creation_before_enrolled_is_rejected(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university, status="offer")

    await _login(client, admin.email)
    response = await client.post("/api/v1/workflows/overseas/agent/commissions", json={"agent_id": str(agent.id), "application_id": str(application.id), "amount": 15000, "currency": "INR"})
    assert response.status_code == 409

    count = (await db_session.execute(select(AgentCommission).where(AgentCommission.application_id == application.id))).scalars().all()
    assert len(count) == 0


@pytest.mark.asyncio
async def test_admin_manual_commission_creation_at_enrolled_is_allowed_and_tagged(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university, status="enrolled")

    await _login(client, admin.email)
    response = await client.post("/api/v1/workflows/overseas/agent/commissions", json={"agent_id": str(agent.id), "application_id": str(application.id), "amount": 15000, "currency": "INR"})
    assert response.status_code == 201

    commission = await db_session.scalar(select(AgentCommission).where(AgentCommission.application_id == application.id))
    assert commission.created_by == "admin_manual"
    assert commission.status == "eligible"


@pytest.mark.asyncio
async def test_overseas_admin_can_set_the_amount_on_an_estimated_commission(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university, status="enrolled")
    commission = AgentCommission(agent_id=agent.id, application_id=application.id, amount=0, currency="INR", status="estimated", created_by="system_trigger")
    db_session.add(commission)
    await db_session.commit()

    await _login(client, admin.email)
    response = await client.patch(f"/api/v1/workflows/overseas/agent/commissions/{commission.id}", json={"amount": 12000})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "eligible"
    assert body["amount"] == 12000

    await db_session.refresh(commission)
    assert commission.status == "eligible"
    assert float(commission.amount) == 12000


@pytest.mark.asyncio
async def test_amount_cannot_be_adjusted_once_claimed(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university, status="enrolled")
    commission = AgentCommission(agent_id=agent.id, application_id=application.id, amount=10000, currency="INR", status="claimed", created_by="system_trigger")
    db_session.add(commission)
    await db_session.commit()

    await _login(client, admin.email)
    response = await client.patch(f"/api/v1/workflows/overseas/agent/commissions/{commission.id}", json={"amount": 99999})
    assert response.status_code == 409

    await db_session.refresh(commission)
    assert float(commission.amount) == 10000


@pytest.mark.asyncio
async def test_agent_cannot_adjust_a_commission_amount(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university, status="enrolled")
    commission = AgentCommission(agent_id=agent.id, application_id=application.id, amount=0, currency="INR", status="estimated", created_by="system_trigger")
    db_session.add(commission)
    await db_session.commit()

    await _login(client, agent.email)
    response = await client.patch(f"/api/v1/workflows/overseas/agent/commissions/{commission.id}", json={"amount": 12000})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_adjusting_an_unknown_commission_404s(db_session, client):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    response = await client.patch(f"/api/v1/workflows/overseas/agent/commissions/{uuid.uuid4()}", json={"amount": 1000})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_amount_adjustment_requires_authentication(client):
    response = await client.patch(f"/api/v1/workflows/overseas/agent/commissions/{uuid.uuid4()}", json={"amount": 1000})
    assert response.status_code == 401
