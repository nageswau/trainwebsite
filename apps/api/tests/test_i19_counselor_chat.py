"""RAID.md I-19 -- Counselor Chat had no way to send a message at all. The Overseas
Student's own "Counselor Chat" page only ever showed read-only history; `PORTAL_NAV`
never listed the section for the Counselor role either, so there was no way for a
Counselor to see or reply to anything. `ROLE_ACTION_MATRIX.md`'s own confirmed base
action for the Student is "counselor-chat (direct messaging with their assigned
counselor)" -- this closes the gap on both sides:

- New `POST /workflows/overseas/student/counselor-chat` resolves the student's assigned
  counselor server-side (from their own `OverseasApplication.counselor_id`) and sends,
  rather than trusting a client-supplied recipient id.
- New `counselor-chat` section added to the Counselor's own portal dispatcher, reusing
  the exact same generic query the Student side's own section already used.
- The already-existing generic `GET`/`POST /communications/messages...` endpoints needed
  no change at all -- they already supported a Counselor replying to a specific student,
  once the frontend had a way to pick which student.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Country, Message, OverseasApplication, University, User


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
        slug=f"i19-country-{uuid.uuid4().hex[:8]}", name="Testland", overview="", tuition="", living_expenses="",
        visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[],
    )
    db_session.add(country)
    await db_session.flush()
    university = University(
        country_id=country.id, slug=f"i19-university-{uuid.uuid4().hex[:8]}", name="Test University", city="Testville",
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
async def test_student_sends_a_message_to_their_assigned_counselor(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    await _make_application(db_session, student, university, counselor)

    await _login(client, student.email)
    response = await client.post("/api/v1/workflows/overseas/student/counselor-chat", json={"body": "Please review my SOP draft."})
    assert response.status_code == 201

    stored = await db_session.scalar(select(Message).where(Message.sender_id == student.id, Message.recipient_id == counselor.id))
    assert stored is not None
    assert stored.body == "Please review my SOP draft."
    assert stored.context_type == "counselor_chat"


@pytest.mark.asyncio
async def test_student_with_no_assigned_counselor_gets_a_clear_error_not_a_silent_drop(client, db_session):
    student = await _create_user(db_session, "overseas_student")
    await _login(client, student.email)
    response = await client.post("/api/v1/workflows/overseas/student/counselor-chat", json={"body": "Hello?"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_empty_message_body_is_rejected(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    await _make_application(db_session, student, university, counselor)

    await _login(client, student.email)
    response = await client.post("/api/v1/workflows/overseas/student/counselor-chat", json={"body": "   "})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_counselor_sees_the_message_and_can_reply_via_the_existing_generic_endpoints(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    await _make_application(db_session, student, university, counselor)

    await _login(client, student.email)
    sent = await client.post("/api/v1/workflows/overseas/student/counselor-chat", json={"body": "Please review my SOP draft."})
    assert sent.status_code == 201

    await _login(client, counselor.email)
    conversation = await client.get(f"/api/v1/communications/messages/{student.id}")
    assert conversation.status_code == 200
    assert any(m["body"] == "Please review my SOP draft." for m in conversation.json())

    reply = await client.post("/api/v1/communications/messages", json={"recipient_id": str(student.id), "body": "Looks good, thanks!", "context_type": "counselor_chat"})
    assert reply.status_code == 201

    recheck = await client.get(f"/api/v1/communications/messages/{student.id}")
    assert any(m["body"] == "Looks good, thanks!" and m["sender_id"] == str(counselor.id) for m in recheck.json())


@pytest.mark.asyncio
async def test_counselor_chat_portal_section_is_reachable_for_the_counselor_role(client, db_session):
    """Before this fix, `PORTAL_NAV` never listed this section for Counselor at all --
    confirms the new handler renders instead of "Workspace not found"."""
    counselor = await _create_user(db_session, "counselor")
    await _login(client, counselor.email)
    response = await client.get("/api/v1/portal/overseas/counselor/counselor-chat")
    assert response.status_code == 200
    assert response.json()["title"] == "Counselor Chat"


@pytest.mark.asyncio
async def test_counselor_applications_section_now_reports_a_real_student_id(client, db_session):
    university = await _make_university(db_session)
    counselor = await _create_user(db_session, "counselor")
    student = await _create_user(db_session, "overseas_student")
    await _make_application(db_session, student, university, counselor)

    await _login(client, counselor.email)
    response = await client.get("/api/v1/portal/overseas/counselor/applications")
    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["student_id"] == str(student.id)


@pytest.mark.asyncio
async def test_sending_a_counselor_message_requires_authentication(client):
    response = await client.post("/api/v1/workflows/overseas/student/counselor-chat", json={"body": "Hello?"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_only_an_overseas_student_can_use_this_endpoint(client, db_session):
    counselor = await _create_user(db_session, "counselor")
    await _login(client, counselor.email)
    response = await client.post("/api/v1/workflows/overseas/student/counselor-chat", json={"body": "Hello?"})
    assert response.status_code == 403
