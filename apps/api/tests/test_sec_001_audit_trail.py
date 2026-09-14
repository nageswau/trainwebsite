"""SEC-001 -- Approval-gate audit trail.

`AGT-001`'s approve/reject and `AGT-004`'s payout-approval actions already wrote
`AuditLog` rows in the same transaction/commit as their privileged write -- fail-closed
by construction, confirmed directly by code inspection (a `db.commit()` failure at any
point rolls back everything staged before it, and neither endpoint has a second commit).
The real, confirmed gap: `DATA_MODEL.md` #7.3 names `outcome` as a required `AuditLog`
field ("actor_user_id, action, resource_type, resource_id, outcome, metadata,
created_at") -- and the catalog's own SEC-001 description says the same ("...logged with
actor, timestamp, outcome") -- but the model never had one. Added it (migration `0020`),
and set a real business-outcome value at the two call sites this feature's own scope
names (`AGT-001`'s `approve_agent`/`reject_agent`, `AGT-004`'s
`approve_commission_payout`). Untouched call sites elsewhere in the codebase default to
"recorded" -- a deliberate scope boundary (this feature only touches the two named
actions), not an oversight; verified directly below.

Also verified (not modified, per `RBAC_MATRIX.md` #3's "Privileged-write audit trail"
control): `admin.py`'s GDPR `fulfil_data_request` and `workflows.py`'s certificate-issue
override already share one `db.commit()` with their own `AuditLog` write. "Super Admin
security-log export" (also named in that control row) has no distinct write action
anywhere in the codebase to verify -- only a read-only `GET /admin/audit` view exists --
so there is nothing there to audit-log; not invented as new scope.
"""

import uuid

import pytest
from sqlalchemy import select

import app.api.admin as admin_module
from app.core.security import hash_password
from app.models import AgentCommission, AuditLog, OverseasApplication, University, Country, User, UserRoleAssignment


def _boom(*args, **kwargs):
    raise RuntimeError("simulated audit-log write failure")


async def _register_agent(client, **overrides) -> dict:
    payload = {
        "email": f"sec001-{uuid.uuid4().hex[:8]}@example.local",
        "password": "Sup3r-Secret-Pass!",
        "full_name": "Test Agent",
        "division": "overseas",
        "account_type": "agent",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    return response.json()


async def _create_user(db_session, *, role: str, division: str = "overseas", **overrides) -> User:
    defaults = dict(
        email=f"sec001-{role}-{uuid.uuid4().hex[:8]}@example.local",
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
        slug=f"sec001-country-{uuid.uuid4().hex[:8]}",
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
        slug=f"sec001-university-{uuid.uuid4().hex[:8]}",
        name=f"SEC-001 Test University {uuid.uuid4().hex[:8]}",
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


async def _create_overseas_admin(db_session) -> User:
    return await _create_user(db_session, role="overseas_admin")


@pytest.mark.asyncio
async def test_agent_approval_writes_an_audit_row_with_outcome_approved(db_session, client):
    registration = await _register_agent(client)
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)

    response = await client.post(f"/api/v1/overseas-admin/agents/{registration['user']['id']}/approve")
    assert response.status_code == 200

    log = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent.approve").order_by(AuditLog.created_at.desc()))
    assert log is not None
    assert log.outcome == "approved"


@pytest.mark.asyncio
async def test_agent_rejection_writes_an_audit_row_with_outcome_rejected(db_session, client):
    registration = await _register_agent(client)
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)

    response = await client.post(f"/api/v1/overseas-admin/agents/{registration['user']['id']}/reject")
    assert response.status_code == 200

    log = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent.reject").order_by(AuditLog.created_at.desc()))
    assert log is not None
    assert log.outcome == "rejected"


@pytest.mark.asyncio
async def test_commission_payout_approval_writes_two_audit_rows_with_correct_outcomes_in_order(db_session, client):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = OverseasApplication(student_id=student.id, university_id=university.id, agent_id=agent.id, status="enrolled", next_action="", intake="September 2027")
    db_session.add(application)
    await db_session.commit()
    commission = AgentCommission(agent_id=agent.id, application_id=application.id, amount=15000, currency="INR", status="claimed", created_by="system_trigger")
    db_session.add(commission)
    await db_session.commit()

    await _login(client, admin.email)
    response = await client.post(f"/api/v1/overseas-admin/commissions/{commission.id}/approve-payout")
    assert response.status_code == 200

    logs = (await db_session.execute(select(AuditLog).where(AuditLog.entity_type == "agent_commission", AuditLog.entity_id == str(commission.id)).order_by(AuditLog.created_at))).scalars().all()
    by_action = {log.action: log.outcome for log in logs}
    assert by_action["agent.commission_payout_pending"] == "pending"
    assert by_action["agent.commission_payout_approve"] == "approved"


@pytest.mark.asyncio
async def test_agent_approval_fails_closed_if_the_audit_write_itself_fails(db_session, client, monkeypatch):
    registration = await _register_agent(client)
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)

    monkeypatch.setattr(admin_module, "AuditLog", _boom)
    # `client`'s ASGITransport propagates an unhandled route exception as a raised
    # Python exception rather than converting it to a response (no
    # `raise_app_exceptions=False`) -- the point under test either way is that the
    # request never completes successfully and nothing partial persists.
    with pytest.raises(RuntimeError, match="simulated audit-log write failure"):
        await client.post(f"/api/v1/overseas-admin/agents/{registration['user']['id']}/approve")

    assignment = await db_session.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == uuid.UUID(registration["user"]["id"])))
    assert assignment.approval_status == "pending"


@pytest.mark.asyncio
async def test_commission_payout_approval_fails_closed_if_the_audit_write_itself_fails(db_session, client, monkeypatch):
    agent = await _create_agent(db_session)
    student = await _create_user(db_session, role="overseas_student")
    university = await _make_university(db_session)
    admin = await _create_overseas_admin(db_session)
    application = OverseasApplication(student_id=student.id, university_id=university.id, agent_id=agent.id, status="enrolled", next_action="", intake="September 2027")
    db_session.add(application)
    await db_session.commit()
    commission = AgentCommission(agent_id=agent.id, application_id=application.id, amount=15000, currency="INR", status="claimed", created_by="system_trigger")
    db_session.add(commission)
    await db_session.commit()

    await _login(client, admin.email)
    monkeypatch.setattr(admin_module, "AuditLog", _boom)
    with pytest.raises(RuntimeError, match="simulated audit-log write failure"):
        await client.post(f"/api/v1/overseas-admin/commissions/{commission.id}/approve-payout")

    await db_session.refresh(commission)
    assert commission.status == "claimed"
    assert commission.paid_at is None
    assert commission.payout_approved_by_user_id is None


@pytest.mark.asyncio
async def test_an_untouched_audit_call_site_defaults_to_recorded(db_session, client):
    """Deliberate scope boundary, not an oversight: this feature's own catalog
    description scopes it to AGT-001/AGT-004 specifically. Auth login's own audit row
    (an existing, unrelated call site) is expected to keep the plain "recorded" default.
    """

    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)

    log = await db_session.scalar(select(AuditLog).where(AuditLog.action == "auth.login", AuditLog.user_id == admin.id).order_by(AuditLog.created_at.desc()))
    assert log is not None
    assert log.outcome == "recorded"


@pytest.mark.asyncio
async def test_admin_audit_endpoint_surfaces_the_outcome_field(db_session, client):
    registration = await _register_agent(client)
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    approve = await client.post(f"/api/v1/overseas-admin/agents/{registration['user']['id']}/approve")
    assert approve.status_code == 200

    assignment = await db_session.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == uuid.UUID(registration["user"]["id"])))
    response = await client.get("/api/v1/admin/audit")
    assert response.status_code == 200
    rows = response.json()
    matching = [row for row in rows if row["action"] == "agent.approve" and row["entity_id"] == str(assignment.id)]
    assert matching
    assert matching[0]["outcome"] == "approved"
