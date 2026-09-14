"""AGT-004 -- Commission payout request and approval.

Net-new -- no equivalent existed in the base codebase
(`REFERENCE_IMPLEMENTATION_FINDINGS.md` #5.4). `PRD.md` #6.4's confirmed state machine
("...Commission Accrued -> Payout Requested -> Overseas Admin Approval -> Paid") names
only two actions: the Agent's existing claim (already `status="claimed"`, unchanged) and
this feature's new `POST /overseas-admin/commissions/{id}/approve-payout`.
`DATA_MODEL.md` #6.7 additionally requires the commission is genuinely written through a
"payout_pending" status before "paid" -- "claimed can never transition directly to
paid" -- honored by writing two audit rows for the one approval request rather than
skipping straight to paid.

Two-gate same-actor rule (`NFR-SEC-002`, `RBAC_MATRIX.md` #2.8): the Overseas Admin who
created an *admin-manual* commission cannot also approve its own payout. Confirmed as
scoped to creation-mode (`created_by`), not to whether the amount was later adjusted --
`test_same_admin_can_approve_a_system_triggered_commission_even_after_setting_its_amount`
below documents this literal, confirmed (if arguably incomplete) scope directly, per the
open item noted in `admin.py`'s `approve_commission_payout`.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import (
    AgentCommission,
    AuditLog,
    Country,
    OverseasApplication,
    University,
    User,
    UserRoleAssignment,
)


async def _create_user(db_session, *, role: str, division: str = "overseas", **overrides) -> User:
    defaults = dict(
        email=f"agt004-{role}-{uuid.uuid4().hex[:8]}@example.local",
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
        slug=f"agt004-country-{uuid.uuid4().hex[:8]}",
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
        slug=f"agt004-university-{uuid.uuid4().hex[:8]}",
        name=f"AGT-004 Test University {uuid.uuid4().hex[:8]}",
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


async def _make_application(db_session, *, agent, student, university, status="enrolled") -> OverseasApplication:
    application = OverseasApplication(
        student_id=student.id,
        university_id=university.id,
        agent_id=agent.id,
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


async def _create_overseas_admin(db_session) -> User:
    return await _create_user(db_session, role="overseas_admin")


async def _claimed_commission(db_session, *, agent, application, created_by="system_trigger", amount=15000) -> AgentCommission:
    commission = AgentCommission(agent_id=agent.id, application_id=application.id, amount=amount, currency="INR", status="claimed", created_by=created_by)
    db_session.add(commission)
    await db_session.commit()
    return commission


@pytest.mark.asyncio
async def test_overseas_admin_approves_payout_and_it_reaches_paid(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university)
    commission = await _claimed_commission(db_session, agent=agent, application=application)

    await _login(client, admin.email)
    response = await client.post(f"/api/v1/overseas-admin/commissions/{commission.id}/approve-payout")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "paid"
    assert body["paid_at"] is not None

    await db_session.refresh(commission)
    assert commission.status == "paid"
    assert commission.payout_approved_by_user_id == admin.id
    assert commission.payout_approved_at is not None
    assert commission.paid_at is not None


@pytest.mark.asyncio
async def test_payout_transitions_through_payout_pending_before_paid_in_the_audit_trail(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university)
    commission = await _claimed_commission(db_session, agent=agent, application=application)

    await _login(client, admin.email)
    response = await client.post(f"/api/v1/overseas-admin/commissions/{commission.id}/approve-payout")
    assert response.status_code == 200

    logs = (await db_session.execute(select(AuditLog).where(AuditLog.entity_type == "agent_commission", AuditLog.entity_id == str(commission.id)).order_by(AuditLog.created_at))).scalars().all()
    actions = [log.action for log in logs]
    assert "agent.commission_payout_pending" in actions
    assert "agent.commission_payout_approve" in actions
    assert actions.index("agent.commission_payout_pending") < actions.index("agent.commission_payout_approve")


@pytest.mark.asyncio
async def test_a_not_yet_claimed_commission_cannot_have_its_payout_approved(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university)
    commission = AgentCommission(agent_id=agent.id, application_id=application.id, amount=15000, currency="INR", status="eligible", created_by="system_trigger")
    db_session.add(commission)
    await db_session.commit()

    await _login(client, admin.email)
    response = await client.post(f"/api/v1/overseas-admin/commissions/{commission.id}/approve-payout")
    assert response.status_code == 409

    await db_session.refresh(commission)
    assert commission.status == "eligible"


@pytest.mark.asyncio
async def test_an_already_paid_commission_cannot_be_approved_again(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university)
    commission = AgentCommission(agent_id=agent.id, application_id=application.id, amount=15000, currency="INR", status="paid", created_by="system_trigger")
    db_session.add(commission)
    await db_session.commit()

    await _login(client, admin.email)
    response = await client.post(f"/api/v1/overseas-admin/commissions/{commission.id}/approve-payout")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_agent_cannot_approve_their_own_payout(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university)
    commission = await _claimed_commission(db_session, agent=agent, application=application)

    await _login(client, agent.email)
    response = await client.post(f"/api/v1/overseas-admin/commissions/{commission.id}/approve-payout")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_admin_who_manually_created_a_commission_cannot_approve_its_own_payout(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university)

    await _login(client, admin.email)
    created = await client.post("/api/v1/workflows/overseas/agent/commissions", json={"agent_id": str(agent.id), "application_id": str(application.id), "amount": 15000, "currency": "INR"})
    assert created.status_code == 201
    commission_id = created.json()["id"]

    await _login(client, agent.email)
    claim = await client.post(f"/api/v1/workflows/overseas/agent/commissions/{commission_id}/claim")
    assert claim.status_code == 200

    await _login(client, admin.email)
    response = await client.post(f"/api/v1/overseas-admin/commissions/{commission_id}/approve-payout")
    assert response.status_code == 403

    commission = await db_session.get(AgentCommission, uuid.UUID(commission_id))
    assert commission.status == "claimed"


@pytest.mark.asyncio
async def test_a_different_admin_can_approve_the_payout_of_a_manually_created_commission(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    creating_admin = await _create_overseas_admin(db_session)
    approving_admin = await _create_overseas_admin(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university)

    await _login(client, creating_admin.email)
    created = await client.post("/api/v1/workflows/overseas/agent/commissions", json={"agent_id": str(agent.id), "application_id": str(application.id), "amount": 15000, "currency": "INR"})
    assert created.status_code == 201
    commission_id = created.json()["id"]

    await _login(client, agent.email)
    claim = await client.post(f"/api/v1/workflows/overseas/agent/commissions/{commission_id}/claim")
    assert claim.status_code == 200

    await _login(client, approving_admin.email)
    response = await client.post(f"/api/v1/overseas-admin/commissions/{commission_id}/approve-payout")
    assert response.status_code == 200
    assert response.json()["status"] == "paid"


@pytest.mark.asyncio
async def test_same_admin_can_approve_a_system_triggered_commission_even_after_setting_its_amount(db_session, client):
    """Documents the confirmed (literal RBAC_MATRIX.md) scope of the two-gate rule: it is
    keyed on `created_by` at creation time, not on who last adjusted the amount. A
    system_trigger-created commission is exempt even if the same Admin later set its
    amount via AGT-003's PATCH endpoint -- a real, deliberate open item (see
    `admin.py`'s `approve_commission_payout` and `docs/product/PRD_OPEN_ITEMS.md`), not
    silently tightened beyond what the confirmed contract states.
    """

    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = await _make_application(db_session, agent=agent, student=student, university=university)
    commission = AgentCommission(agent_id=agent.id, application_id=application.id, amount=0, currency="INR", status="estimated", created_by="system_trigger")
    db_session.add(commission)
    await db_session.commit()

    await _login(client, admin.email)
    set_amount = await client.patch(f"/api/v1/workflows/overseas/agent/commissions/{commission.id}", json={"amount": 15000})
    assert set_amount.status_code == 200

    await _login(client, agent.email)
    claim = await client.post(f"/api/v1/workflows/overseas/agent/commissions/{commission.id}/claim")
    assert claim.status_code == 200

    await _login(client, admin.email)
    response = await client.post(f"/api/v1/overseas-admin/commissions/{commission.id}/approve-payout")
    assert response.status_code == 200
    assert response.json()["status"] == "paid"


@pytest.mark.asyncio
async def test_approving_an_unknown_commission_404s(db_session, client):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    response = await client.post(f"/api/v1/overseas-admin/commissions/{uuid.uuid4()}/approve-payout")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_payout_approval_requires_authentication(client):
    response = await client.post(f"/api/v1/overseas-admin/commissions/{uuid.uuid4()}/approve-payout")
    assert response.status_code == 401
