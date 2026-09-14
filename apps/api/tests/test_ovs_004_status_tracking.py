"""OVS-004 -- Application status tracking and notifications.

The notification side (`_notify_user`, `send_notification`) was already wired into every
status-changing endpoint by earlier features (`OVS-002`/`003`) and is already
exception-safe by construction (`post_optional_webhook` catches every exception and
returns `("failed", error)`, never raises) -- `NOT-001`'s own fix. Verified directly here
rather than assumed: a stage-change notification failure does not block or roll back the
status-history write (`OVS-004-AC02`). The real gap: `API_CONTRACT.md` #7 names a
dedicated `GET /overseas/applications/{id}/status` tracking-view endpoint (distinct from
`VISA-001`/`003`'s own checklist/status endpoints) -- it did not exist.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Country, NotificationDelivery, OverseasApplication, University, User


async def _create_user(db_session, role: str, **overrides) -> User:
    defaults = dict(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role}", role=role, division="overseas", active=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    await db_session.commit()
    return user


async def _make_university(db_session) -> University:
    country = Country(
        slug=f"test-country-{uuid.uuid4().hex[:8]}", name="Testland", overview="", tuition="", living_expenses="",
        visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[],
    )
    db_session.add(country)
    await db_session.flush()
    university = University(
        country_id=country.id, slug=f"test-university-{uuid.uuid4().hex[:8]}", name="Test University", city="Testville",
        overview="", eligibility="", requirements=[], deadlines=[], scholarships=[],
    )
    db_session.add(university)
    await db_session.commit()
    return university


async def _make_application(db_session, student, university, counselor) -> OverseasApplication:
    application = OverseasApplication(student_id=student.id, university_id=university.id, counselor_id=counselor.id if counselor else None, intake="Fall 2027", status="enquiry")
    db_session.add(application)
    await db_session.commit()
    return application


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_student_views_their_own_status_tracking_history(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, counselor)

    await _login(client, counselor.email)
    await client.post(f"/api/v1/workflows/overseas/applications/{application.id}/advance", json={"to_status": "eligibility_evaluation", "next_action": "Submit transcripts"})

    await _login(client, student.email)
    response = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "eligibility_evaluation"
    assert body["next_action"] == "Submit transcripts"
    # `_make_application` inserts the row directly (test setup, not through the real
    # create endpoint), so only the advance above appears in history here.
    assert len(body["history"]) == 1
    assert body["history"][-1]["to_status"] == "eligibility_evaluation"


@pytest.mark.asyncio
async def test_a_different_student_cannot_view_the_status(client, db_session):
    university = await _make_university(db_session)
    student = await _create_user(db_session, "overseas_student")
    other_student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)

    await _login(client, other_student.email)
    response = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/status")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_assigned_counselor_can_view_but_unassigned_counselor_cannot(client, db_session):
    university = await _make_university(db_session)
    assigned_counselor = await _create_user(db_session, "counselor")
    other_counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, assigned_counselor)

    await _login(client, assigned_counselor.email)
    ok = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/status")
    assert ok.status_code == 200

    await _login(client, other_counselor.email)
    denied = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/status")
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_a_notification_send_failure_never_blocks_the_status_write(client, db_session, monkeypatch):
    import app.api.workflows as workflows_module

    async def failing_send(channel, payload):
        return "failed", "Connection timed out after 10s"

    monkeypatch.setattr(workflows_module, "send_notification", failing_send)

    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, counselor)

    await _login(client, counselor.email)
    response = await client.post(f"/api/v1/workflows/overseas/applications/{application.id}/advance", json={"to_status": "eligibility_evaluation"})
    assert response.status_code == 200
    assert response.json()["status"] == "eligibility_evaluation"

    await db_session.refresh(application)
    assert application.status == "eligibility_evaluation"

    delivery = await db_session.scalar(select(NotificationDelivery).where(NotificationDelivery.channel == "email").order_by(NotificationDelivery.created_at.desc()))
    assert delivery is not None
    assert delivery.status == "failed"
    assert delivery.error == "Connection timed out after 10s"


@pytest.mark.asyncio
async def test_status_tracking_requires_authentication(client, db_session):
    university = await _make_university(db_session)
    student = await _create_user(db_session, "overseas_student")
    application = await _make_application(db_session, student, university, None)
    response = await client.get(f"/api/v1/workflows/overseas/applications/{application.id}/status")
    assert response.status_code == 401
