"""OVS-006 -- Scholarship listing and application.

`GET /public/scholarships` and `POST /overseas/scholarships/{id}/apply` already existed
and were already correct (self-scoped, duplicate-blocked, RBAC'd to `overseas_student`).
The real gap was read-only: no endpoint existed for a student to see which scholarships
they had already applied to, so the frontend could only ever show a bare apply action
with no status -- added the `scholarships` portal section (`services/portal.py`) instead
of inventing a new route file. `ScholarshipApplyPanel.tsx` is the new frontend half.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Country, Scholarship, ScholarshipApplication, User


async def _create_overseas_student(db_session, **overrides) -> User:
    defaults = dict(
        email=f"ovs-scholar-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Overseas Student",
        role="overseas_student",
        division="overseas",
        active=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    await db_session.commit()
    return user


async def _make_scholarship(db_session, **overrides) -> Scholarship:
    country = Country(
        slug=f"test-country-{uuid.uuid4().hex[:8]}",
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
    defaults = dict(
        title=f"Test Scholarship {uuid.uuid4().hex[:8]}",
        country_id=country.id,
        eligibility="Strong academic profile.",
        amount="USD 1,000",
        active=True,
    )
    defaults.update(overrides)
    scholarship = Scholarship(**defaults)
    db_session.add(scholarship)
    await db_session.commit()
    return scholarship


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_student_applies_to_a_listed_scholarship(client, db_session):
    student = await _create_overseas_student(db_session)
    scholarship = await _make_scholarship(db_session)

    await _login(client, student.email)
    response = await client.post(f"/api/v1/workflows/overseas/scholarships/{scholarship.id}/apply")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "submitted"

    stored = await db_session.get(ScholarshipApplication, uuid.UUID(body["id"]))
    assert stored.student_id == student.id
    assert stored.scholarship_id == scholarship.id


@pytest.mark.asyncio
async def test_duplicate_application_to_the_same_scholarship_is_rejected(client, db_session):
    student = await _create_overseas_student(db_session)
    scholarship = await _make_scholarship(db_session)

    await _login(client, student.email)
    first = await client.post(f"/api/v1/workflows/overseas/scholarships/{scholarship.id}/apply")
    assert first.status_code == 201
    second = await client.post(f"/api/v1/workflows/overseas/scholarships/{scholarship.id}/apply")
    assert second.status_code == 409

    count = (await db_session.execute(select(ScholarshipApplication).where(ScholarshipApplication.student_id == student.id, ScholarshipApplication.scholarship_id == scholarship.id))).scalars().all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_inactive_scholarship_is_not_applyable(client, db_session):
    student = await _create_overseas_student(db_session)
    scholarship = await _make_scholarship(db_session, active=False)

    await _login(client, student.email)
    response = await client.post(f"/api/v1/workflows/overseas/scholarships/{scholarship.id}/apply")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_it_student_role_is_rejected(client, db_session):
    it_student = User(
        email=f"it-student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="IT Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(it_student)
    await db_session.commit()
    scholarship = await _make_scholarship(db_session)

    login = await client.post("/api/v1/auth/login", json={"email": it_student.email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert login.status_code == 200
    response = await client.post(f"/api/v1/workflows/overseas/scholarships/{scholarship.id}/apply")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_apply_requires_authentication(client, db_session):
    scholarship = await _make_scholarship(db_session)
    response = await client.post(f"/api/v1/workflows/overseas/scholarships/{scholarship.id}/apply")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_public_listing_only_shows_active_scholarships(client, db_session):
    active = await _make_scholarship(db_session, active=True)
    inactive = await _make_scholarship(db_session, active=False)

    response = await client.get("/api/v1/public/scholarships")
    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert str(active.id) in ids
    assert str(inactive.id) not in ids


@pytest.mark.asyncio
async def test_portal_scholarships_section_reflects_own_application_status_only(client, db_session):
    student = await _create_overseas_student(db_session)
    other_student = await _create_overseas_student(db_session)
    scholarship = await _make_scholarship(db_session)
    other_scholarship = await _make_scholarship(db_session)

    await _login(client, student.email)
    applied = await client.post(f"/api/v1/workflows/overseas/scholarships/{scholarship.id}/apply")
    assert applied.status_code == 201

    other_app = ScholarshipApplication(scholarship_id=other_scholarship.id, student_id=other_student.id, status="submitted")
    db_session.add(other_app)
    await db_session.commit()

    response = await client.get("/api/v1/portal/overseas/student/scholarships")
    assert response.status_code == 200
    rows = response.json()["rows"]
    scholarship_ids = {row["scholarship_id"] for row in rows}
    assert str(scholarship.id) in scholarship_ids
    assert str(other_scholarship.id) not in scholarship_ids


@pytest.mark.asyncio
async def test_portal_scholarships_section_requires_authentication(client, db_session):
    response = await client.get("/api/v1/portal/overseas/student/scholarships")
    assert response.status_code == 401
