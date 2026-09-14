"""EMP-001 -- Employer registration.

Net-new: no Employer role/login existed anywhere in the base codebase (corporate hiring was
previously mediated entirely by internal `placement_team`/`hr_team` staff plus a public
apply-and-track flow). Registration is atomic (User + Company + EmployerProfile all
created, or none are -- EMP-001-AC02) and the account is active immediately: whether
registration needs Admin approval before activation is an explicitly open item
(`FEATURE_QUESTIONS.md` #7), so `registration_status` is recorded but never enforced as a
login gate here.
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import Company, EmployerProfile, User


def _payload(**overrides) -> dict:
    base = {
        "email": f"emp001-{uuid.uuid4().hex[:8]}@example.local",
        "password": "Sup3r-Secret-Pass!",
        "full_name": "New Employer Contact",
        "company_name": f"Acme Corp {uuid.uuid4().hex[:6]}",
        "company_website": "https://acme.example.com",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_registration_creates_user_company_and_profile_atomically_and_logs_in(db_session, client):
    payload = _payload()
    response = await client.post("/api/v1/employer/register", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "employer"
    assert response.cookies.get("edusphere_access")

    user = await db_session.scalar(select_user(payload["email"]))
    assert user is not None
    company = await db_session.scalar(select_company(payload["company_name"]))
    assert company is not None
    assert company.owner_type == "employer_self_service"
    assert company.employer_user_id == user.id
    profile = await db_session.scalar(select_profile(user.id))
    assert profile is not None
    assert profile.company_id == company.id
    assert profile.registration_status is None


@pytest.mark.asyncio
async def test_registration_is_usable_immediately_no_approval_gate(db_session, client):
    payload = _payload()
    register = await client.post("/api/v1/employer/register", json=payload)
    assert register.status_code == 200

    login = await client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"], "division": "it"})
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_email_is_rejected(db_session, client):
    payload = _payload()
    first = await client.post("/api/v1/employer/register", json=payload)
    assert first.status_code == 200
    second = await client.post("/api/v1/employer/register", json=_payload(email=payload["email"]))
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_duplicate_company_name_is_rejected(db_session, client):
    payload = _payload()
    first = await client.post("/api/v1/employer/register", json=payload)
    assert first.status_code == 200
    second = await client.post("/api/v1/employer/register", json=_payload(company_name=payload["company_name"]))
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_a_failed_registration_leaves_no_partial_state(db_session, client):
    payload = _payload()
    await client.post("/api/v1/employer/register", json=payload)
    # Same email, different company -- must fail before any new Company row is created.
    conflicting_company = _payload(email=payload["email"])["company_name"]
    await client.post("/api/v1/employer/register", json=_payload(email=payload["email"], company_name=conflicting_company))

    orphaned_company = await db_session.scalar(select_company(conflicting_company))
    assert orphaned_company is None


@pytest.mark.asyncio
async def test_employer_can_read_and_update_own_profile(db_session, client):
    payload = _payload()
    await client.post("/api/v1/employer/register", json=payload)
    await client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"], "division": "it"})

    get_response = await client.get("/api/v1/employer/profile")
    assert get_response.status_code == 200
    assert get_response.json()["company_name"] == payload["company_name"]

    patch_response = await client.patch("/api/v1/employer/profile", json={"company_website": "https://updated.example.com"})
    assert patch_response.status_code == 200
    assert patch_response.json()["company_website"] == "https://updated.example.com"


@pytest.mark.asyncio
async def test_non_employer_role_cannot_view_employer_profile(db_session, client):
    student = User(email=f"emp001-student-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"), full_name="Student", role="it_student", division="it", active=True)
    db_session.add(student)
    await db_session.commit()
    await client.post("/api/v1/auth/login", json={"email": student.email, "password": "Sup3r-Secret-Pass!", "division": "it"})

    response = await client.get("/api/v1/employer/profile")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_employer_profile_requires_authentication(client):
    assert (await client.get("/api/v1/employer/profile")).status_code == 401
    assert (await client.patch("/api/v1/employer/profile", json={})).status_code == 401


def select_user(email: str):
    from sqlalchemy import select

    return select(User).where(User.email == email)


def select_company(name: str):
    from sqlalchemy import select

    return select(Company).where(Company.name == name)


def select_profile(user_id):
    from sqlalchemy import select

    return select(EmployerProfile).where(EmployerProfile.user_id == user_id)
