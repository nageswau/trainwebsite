"""EMP-003 -- Candidate profile search.

Net-new: `GET /employer/candidates`, per `API_CONTRACT.md` #6, reads `PlacementProfile`
and returns only a conservative allowlist -- name, course, skills, availability -- never
raw contact info (email/phone), pending confirmation of the exact GDPR-approved field set
(`EMP-003-AC02`). Excludes only withdrawn candidates by default, the same "active pool"
rule `ADM-007-AC02` already established; a student with no `PlacementProfile` at all
(never entered the placement pipeline) is not a searchable candidate.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, Company, Enrollment, EmployerProfile, PlacementProfile, Program, User


async def _create_employer(db_session) -> User:
    user = User(
        email=f"emp003-employer-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Test Employer", role="employer", division="it", active=True,
    )
    db_session.add(user)
    await db_session.flush()
    company = Company(name=f"EMP-003 Test Co {uuid.uuid4().hex[:6]}", partner_type="employer", owner_type="employer_self_service", employer_user_id=user.id)
    db_session.add(company)
    await db_session.flush()
    db_session.add(EmployerProfile(user_id=user.id, company_id=company.id, registration_status=None))
    await db_session.commit()
    return user


async def _create_candidate(db_session, *, skills=None, available=True, withdrawn=False, with_profile=True, with_enrollment=True) -> User:
    candidate = User(
        email=f"emp003-candidate-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Candidate {uuid.uuid4().hex[:6]}", role="it_student", division="it", active=True,
        profile={"skills": skills or []},
    )
    db_session.add(candidate)
    await db_session.flush()
    if with_enrollment:
        trainer = User(email=f"emp003-trainer-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"), full_name="Trainer", role="trainer", division="it", active=True)
        db_session.add(trainer)
        await db_session.flush()
        program_title = f"EMP-003 Test Program {uuid.uuid4().hex[:6]}"
        program = Program(
            slug=f"emp003-prog-{uuid.uuid4().hex[:8]}", category="Software Development", title=program_title, summary="Test", duration="8 weeks",
            eligibility="None", fees=10000, certification="Test cert", curriculum=["Module 1"], placement_assistance="Yes", trainer_name="Test Trainer", active=True,
        )
        db_session.add(program)
        await db_session.flush()
        batch = Batch(
            program_id=program.id, trainer_id=trainer.id, name=f"Batch-{uuid.uuid4().hex[:6]}", start_date=datetime.date.today(),
            end_date=datetime.date.today() + datetime.timedelta(days=90), schedule="Mon-Fri 7pm", capacity=20, enrollment_open=True, status="active",
        )
        db_session.add(batch)
        await db_session.flush()
        db_session.add(Enrollment(student_id=candidate.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    if with_profile:
        db_session.add(PlacementProfile(student_id=candidate.id, available=available, withdrawn=withdrawn))
    await db_session.commit()
    return candidate


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_employer_sees_allowlisted_fields_and_never_raw_contact_info(client, db_session):
    employer = await _create_employer(db_session)
    candidate = await _create_candidate(db_session, skills=["Python", "SQL"])

    await _login(client, employer.email)
    response = await client.get("/api/v1/employer/candidates")
    assert response.status_code == 200
    match = next(c for c in response.json() if c["student_id"] == str(candidate.id))
    assert match["name"] == candidate.full_name
    assert match["course"].startswith("EMP-003 Test Program")
    assert match["skills"] == ["Python", "SQL"]
    assert match["availability"] is True
    assert set(match) == {"student_id", "name", "course", "skills", "availability"}
    assert "email" not in match and "phone" not in match


@pytest.mark.asyncio
async def test_withdrawn_candidate_is_excluded(client, db_session):
    employer = await _create_employer(db_session)
    candidate = await _create_candidate(db_session, withdrawn=True)

    await _login(client, employer.email)
    response = await client.get("/api/v1/employer/candidates")
    assert not any(c["student_id"] == str(candidate.id) for c in response.json())


@pytest.mark.asyncio
async def test_unavailable_but_not_withdrawn_candidate_is_still_shown(client, db_session):
    employer = await _create_employer(db_session)
    candidate = await _create_candidate(db_session, available=False)

    await _login(client, employer.email)
    response = await client.get("/api/v1/employer/candidates")
    match = next(c for c in response.json() if c["student_id"] == str(candidate.id))
    assert match["availability"] is False


@pytest.mark.asyncio
async def test_a_student_with_no_placement_profile_is_not_a_candidate(client, db_session):
    employer = await _create_employer(db_session)
    candidate = await _create_candidate(db_session, with_profile=False)

    await _login(client, employer.email)
    response = await client.get("/api/v1/employer/candidates")
    assert not any(c["student_id"] == str(candidate.id) for c in response.json())


@pytest.mark.asyncio
async def test_search_query_filters_by_skill(client, db_session):
    employer = await _create_employer(db_session)
    match_candidate = await _create_candidate(db_session, skills=["Rust", "WebAssembly"])
    other_candidate = await _create_candidate(db_session, skills=["Java"])

    await _login(client, employer.email)
    response = await client.get("/api/v1/employer/candidates", params={"q": "Rust"})
    ids = {c["student_id"] for c in response.json()}
    assert str(match_candidate.id) in ids
    assert str(other_candidate.id) not in ids


@pytest.mark.asyncio
async def test_non_employer_role_is_rejected(client, db_session):
    student = await _create_candidate(db_session)
    await _login(client, student.email)
    response = await client.get("/api/v1/employer/candidates")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_candidate_search_requires_authentication(client):
    response = await client.get("/api/v1/employer/candidates")
    assert response.status_code == 401
