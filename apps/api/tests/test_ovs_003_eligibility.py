"""OVS-003 -- Eligibility evaluation.

`PATCH /overseas/applications/{id}` already let a Counselor/University Rep/Admin change
`status` to any free-text value at all -- no dedicated `advance` endpoint existed, and
nothing enforced `DATA_MODEL.md` #6.2's contract-fixed enum sequence (`OVS-003-AC02`: an
attempt to set a rejection/waitlist/deferral outcome must be rejected with a clear "not
yet supported" error, never silently accepted). Added `POST
/overseas/applications/{id}/advance` (Counselor-only, forward-only, enum-validated) and
closed the same gap in the generic PATCH for every caller. `_assigned_application`
already correctly scoped a Counselor to their own assigned applications (BOLA/IDOR-safe,
`OVS-003-AC03`) -- verified directly here, not assumed.
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import ApplicationStatusHistory, Country, OverseasApplication, University, User


async def _create_user(db_session, role: str, **overrides) -> User:
    defaults = dict(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role}",
        role=role,
        division="overseas",
        active=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    await db_session.commit()
    return user


async def _make_university(db_session) -> University:
    country = Country(
        slug=f"test-country-{uuid.uuid4().hex[:8]}",
        name="Testland",
        overview="",
        tuition="",
        living_expenses="",
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
        slug=f"test-university-{uuid.uuid4().hex[:8]}",
        name="Test University",
        city="Testville",
        overview="",
        eligibility="",
        requirements=[],
        deadlines=[],
        scholarships=[],
    )
    db_session.add(university)
    await db_session.commit()
    return university


async def _make_application(db_session, student, university, counselor, status="enquiry") -> OverseasApplication:
    application = OverseasApplication(
        student_id=student.id,
        university_id=university.id,
        counselor_id=counselor.id if counselor else None,
        intake="Fall 2027",
        status=status,
    )
    db_session.add(application)
    await db_session.commit()
    return application


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_assigned_counselor_advances_the_application_forward(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, counselor)

    await _login(client, counselor.email)
    response = await client.post(f"/api/v1/workflows/overseas/applications/{application.id}/advance", json={"to_status": "eligibility_evaluation", "next_action": "Awaiting transcripts"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "eligibility_evaluation"

    await db_session.refresh(application)
    assert application.status == "eligibility_evaluation"
    assert application.next_action == "Awaiting transcripts"


@pytest.mark.asyncio
async def test_a_counselor_not_assigned_to_the_application_is_rejected_even_by_direct_id(client, db_session):
    university = await _make_university(db_session)
    assigned_counselor = await _create_user(db_session, "counselor")
    other_counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, assigned_counselor)

    await _login(client, other_counselor.email)
    response = await client.post(f"/api/v1/workflows/overseas/applications/{application.id}/advance", json={"to_status": "eligibility_evaluation"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_setting_an_unsupported_exception_status_is_rejected_not_silently_accepted(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, counselor)

    await _login(client, counselor.email)
    for unsupported in ("rejected", "waitlisted", "deferred", "not-a-real-status"):
        response = await client.post(f"/api/v1/workflows/overseas/applications/{application.id}/advance", json={"to_status": unsupported})
        assert response.status_code == 422

    unchanged = await db_session.get(OverseasApplication, application.id)
    await db_session.refresh(unchanged)
    assert unchanged.status == "enquiry"


@pytest.mark.asyncio
async def test_moving_backward_or_to_the_same_stage_is_rejected(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, counselor, status="university_selection")

    await _login(client, counselor.email)
    same_stage = await client.post(f"/api/v1/workflows/overseas/applications/{application.id}/advance", json={"to_status": "university_selection"})
    assert same_stage.status_code == 422
    backward = await client.post(f"/api/v1/workflows/overseas/applications/{application.id}/advance", json={"to_status": "enquiry"})
    assert backward.status_code == 422


@pytest.mark.asyncio
async def test_non_counselor_role_is_rejected_on_the_advance_endpoint(client, db_session):
    university = await _make_university(db_session)
    admin = await _create_user(db_session, "overseas_admin")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)

    await _login(client, admin.email)
    response = await client.post(f"/api/v1/workflows/overseas/applications/{application.id}/advance", json={"to_status": "eligibility_evaluation"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_generic_patch_endpoint_also_rejects_an_unsupported_status(client, db_session):
    university = await _make_university(db_session)
    admin = await _create_user(db_session, "overseas_admin")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)

    await _login(client, admin.email)
    response = await client.patch(f"/api/v1/workflows/overseas/applications/{application.id}", json={"status": "rejected"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_advance_requires_authentication(client, db_session):
    university = await _make_university(db_session)
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)

    response = await client.post(f"/api/v1/workflows/overseas/applications/{application.id}/advance", json={"to_status": "eligibility_evaluation"})
    assert response.status_code == 401
