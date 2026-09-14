"""ADM-007 -- Placement Team workspace.

Most of this `[base]` feature already existed and worked (candidate profiles, job
requirements, interviews, offers, all with real RBAC) -- but `ADM-007-AC02` ("a candidate
withdrawn from the pool no longer appears in active matching, but historical placement
records are retained") had no supporting concept at all: `PlacementProfile.available` only
ever meant "temporarily unavailable," never a permanent withdrawal. Also, the only existing
write path (`PUT /workflows/it/placement/profiles/{student_id}`) required the caller to
type the student's raw database reference by hand -- same class of gap already fixed for
`ADM-001`/`002`/`003`/`004`/`006`. Added `PlacementProfile.withdrawn` (alembic `0014`),
excluded by default from both `GET /workflows/it/placement/profiles` and the "candidates"
portal section, and a real picker + withdraw/reinstate control (`PlacementCandidatePanel.tsx`).
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Batch, Company, Enrollment, Job, JobApplication, PlacementProfile, Program, User


async def _create_placement_user(db_session, *, role: str = "placement_team") -> User:
    user = User(
        email=f"adm007-{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Placement Staff",
        role=role,
        division="it",
        active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _create_candidate(db_session) -> User:
    trainer = User(
        email=f"adm007-trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Candidate Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.flush()
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"ADM-007 Test Program {uuid.uuid4().hex[:6]}",
        summary="Test",
        duration="8 weeks",
        eligibility="None",
        fees=10000,
        certification="Test cert",
        curriculum=["Module 1"],
        placement_assistance="Yes",
        trainer_name="Test Trainer",
        active=True,
    )
    db_session.add(program)
    await db_session.flush()
    batch = Batch(
        program_id=program.id,
        trainer_id=trainer.id,
        name=f"Batch-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon-Fri 7pm",
        capacity=20,
        enrollment_open=True,
        status="active",
    )
    db_session.add(batch)
    await db_session.flush()
    candidate = User(
        email=f"adm007-candidate-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Placement Candidate",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(candidate)
    await db_session.flush()
    db_session.add(Enrollment(student_id=candidate.id, batch_id=batch.id, enrollment_code=f"EDU-TEST-{uuid.uuid4().hex[:6]}", status="active"))
    await db_session.commit()
    return candidate


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_withdrawn_candidate_excluded_from_active_pool_by_default(db_session, client):
    staff = await _create_placement_user(db_session)
    candidate = await _create_candidate(db_session)
    await _login(client, staff.email)

    withdraw = await client.put(f"/api/v1/workflows/it/placement/profiles/{candidate.id}", json={"withdrawn": True})
    assert withdraw.status_code == 200
    assert withdraw.json()["withdrawn"] is True

    active_pool = await client.get("/api/v1/workflows/it/placement/profiles")
    assert active_pool.status_code == 200
    assert all(r["student_id"] != str(candidate.id) for r in active_pool.json())

    full_pool = await client.get("/api/v1/workflows/it/placement/profiles?include_withdrawn=true")
    assert any(r["student_id"] == str(candidate.id) for r in full_pool.json())


@pytest.mark.asyncio
async def test_withdrawal_does_not_touch_historical_job_application_records(db_session, client):
    staff = await _create_placement_user(db_session)
    candidate = await _create_candidate(db_session)
    company = Company(name=f"Company {uuid.uuid4().hex[:6]}", partner_type="recruiter")
    db_session.add(company)
    await db_session.flush()
    job = Job(company_id=company.id, title=f"Backend Developer {uuid.uuid4().hex[:6]}", location="Remote", description="Test", status="open")
    db_session.add(job)
    await db_session.flush()
    application = JobApplication(job_id=job.id, student_id=candidate.id, status="shortlisted")
    db_session.add(application)
    await db_session.commit()

    await _login(client, staff.email)
    await client.put(f"/api/v1/workflows/it/placement/profiles/{candidate.id}", json={"withdrawn": True})

    await db_session.refresh(application)
    assert application.status == "shortlisted"
    stored = await db_session.get(JobApplication, application.id)
    assert stored is not None


@pytest.mark.asyncio
async def test_reinstating_a_withdrawn_candidate_restores_visibility(db_session, client):
    staff = await _create_placement_user(db_session)
    candidate = await _create_candidate(db_session)
    await _login(client, staff.email)
    await client.put(f"/api/v1/workflows/it/placement/profiles/{candidate.id}", json={"withdrawn": True})

    reinstate = await client.put(f"/api/v1/workflows/it/placement/profiles/{candidate.id}", json={"withdrawn": False})
    assert reinstate.status_code == 200
    assert reinstate.json()["withdrawn"] is False

    active_pool = await client.get("/api/v1/workflows/it/placement/profiles")
    assert any(r["student_id"] == str(candidate.id) for r in active_pool.json())


@pytest.mark.asyncio
async def test_portal_candidates_section_also_excludes_withdrawn(db_session, client):
    staff = await _create_placement_user(db_session)
    candidate = await _create_candidate(db_session)
    await _login(client, staff.email)
    await client.put(f"/api/v1/workflows/it/placement/profiles/{candidate.id}", json={"withdrawn": True})

    response = await client.get("/api/v1/portal/it/placement/candidates")
    assert response.status_code == 200
    assert all(r["id"] != str(candidate.id) for r in response.json()["rows"])


@pytest.mark.asyncio
async def test_hr_team_cannot_write_placement_profiles(db_session, client):
    hr = await _create_placement_user(db_session, role="hr_team")
    candidate = await _create_candidate(db_session)
    await _login(client, hr.email)

    response = await client.put(f"/api/v1/workflows/it/placement/profiles/{candidate.id}", json={"withdrawn": True})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_placement_profile_write_requires_authentication(client):
    response = await client.put(f"/api/v1/workflows/it/placement/profiles/{uuid.uuid4()}", json={"withdrawn": True})
    assert response.status_code == 401
