"""STU-005 -- Support ticket.

`POST /workflows/support` and `GET /workflows/support` already existed (student raise +
self-scoped list) -- untested until now, and DATA_MODEL.md §4.5's own stated
`assigned_to_user_id` field didn't exist at all, so staff had no way to see, claim, or
resolve a ticket. Covers: student raises and sees only their own ticket (AC01/AC03),
Trainer/Admin see the division queue including unassigned tickets (AC02), staff PATCH
auto-claims + resolves (never a client-supplied assignee), the ticket creator is notified
on resolution, and RBAC (only staff can act, only within their own division).
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Notification, SupportTicket, User


async def _create_user(db_session, role: str, division: str = "it") -> User:
    user = User(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role}",
        role=role,
        division=division,
        active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client, user: User, division: str = "it"):
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "Sup3r-Secret-Pass!", "division": division})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_student_raises_a_ticket_and_sees_it_in_their_own_list(client, db_session):
    student = await _create_user(db_session, "it_student")
    await _login(client, student)

    create = await client.post("/api/v1/workflows/support", json={"subject": "Can't access course", "description": "The course page shows a blank screen.", "priority": "high"})
    assert create.status_code == 201
    assert create.json()["status"] == "open"

    listing = await client.get("/api/v1/workflows/support")
    assert listing.status_code == 200
    subjects = [item["subject"] for item in listing.json()]
    assert "Can't access course" in subjects


@pytest.mark.asyncio
async def test_a_student_never_sees_another_students_ticket(client, db_session):
    owner = await _create_user(db_session, "it_student")
    ticket = SupportTicket(user_id=owner.id, division="it", subject="Owner-only ticket", description="Should not leak.", priority="normal", status="open")
    db_session.add(ticket)
    await db_session.commit()

    other = await _create_user(db_session, "it_student")
    await _login(client, other)

    listing = await client.get("/api/v1/workflows/support")
    assert listing.status_code == 200
    assert all(item["subject"] != "Owner-only ticket" for item in listing.json())


@pytest.mark.asyncio
async def test_trainer_sees_unassigned_division_tickets_not_just_their_own(client, db_session):
    # STU-005-AC02: an unassigned ticket stays visible, never hidden from the staff queue.
    student = await _create_user(db_session, "it_student")
    ticket = SupportTicket(user_id=student.id, division="it", subject="Unassigned billing question", description="Fee receipt missing.", priority="normal", status="open")
    db_session.add(ticket)
    await db_session.commit()

    trainer = await _create_user(db_session, "trainer")
    await _login(client, trainer)

    listing = await client.get("/api/v1/workflows/support")
    assert listing.status_code == 200
    row = next(item for item in listing.json() if item["subject"] == "Unassigned billing question")
    assert row["assigned_to_user_id"] is None


@pytest.mark.asyncio
async def test_staff_action_auto_claims_an_unassigned_ticket_never_client_supplied(client, db_session):
    student = await _create_user(db_session, "it_student")
    ticket = SupportTicket(user_id=student.id, division="it", subject="Login issue", description="Cannot sign in.", priority="urgent", status="open")
    db_session.add(ticket)
    await db_session.commit()
    await db_session.refresh(ticket)

    trainer = await _create_user(db_session, "trainer")
    await _login(client, trainer)

    response = await client.patch(f"/api/v1/workflows/support/{ticket.id}", json={"status": "in_progress"})
    assert response.status_code == 200
    body = response.json()
    assert body["assigned_to_user_id"] == str(trainer.id)
    assert body["status"] == "in_progress"


@pytest.mark.asyncio
async def test_resolving_a_ticket_notifies_the_student_who_raised_it(client, db_session):
    student = await _create_user(db_session, "it_student")
    ticket = SupportTicket(user_id=student.id, division="it", subject="Certificate not downloading", description="Link is broken.", priority="normal", status="open")
    db_session.add(ticket)
    await db_session.commit()
    await db_session.refresh(ticket)

    admin = await _create_user(db_session, "it_admin")
    await _login(client, admin)

    response = await client.patch(f"/api/v1/workflows/support/{ticket.id}", json={"status": "resolved", "resolution_note": "Regenerated the certificate link."})
    assert response.status_code == 200
    assert response.json()["resolution_note"] == "Regenerated the certificate link."

    notification = await db_session.scalar(select(Notification).where(Notification.user_id == student.id))
    assert notification is not None
    assert "resolved" in notification.title.lower()


@pytest.mark.asyncio
async def test_a_student_cannot_act_on_a_support_ticket_even_their_own(client, db_session):
    student = await _create_user(db_session, "it_student")
    ticket = SupportTicket(user_id=student.id, division="it", subject="My own ticket", description="Testing self-action.", priority="normal", status="open")
    db_session.add(ticket)
    await db_session.commit()
    await db_session.refresh(ticket)

    await _login(client, student)
    response = await client.patch(f"/api/v1/workflows/support/{ticket.id}", json={"status": "resolved"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_staff_cannot_act_on_a_ticket_outside_their_division(client, db_session):
    student = await _create_user(db_session, "it_student")
    ticket = SupportTicket(user_id=student.id, division="it", subject="IT-only ticket", description="Division scoped.", priority="normal", status="open")
    db_session.add(ticket)
    await db_session.commit()
    await db_session.refresh(ticket)

    overseas_admin = await _create_user(db_session, "overseas_admin", division="overseas")
    await _login(client, overseas_admin, division="overseas")

    response = await client.patch(f"/api/v1/workflows/support/{ticket.id}", json={"status": "resolved"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_support_ticket_endpoints_require_authentication(client):
    assert (await client.get("/api/v1/workflows/support")).status_code == 401
    assert (await client.post("/api/v1/workflows/support", json={"subject": "x", "description": "xxxxx"})).status_code == 401
    assert (await client.patch(f"/api/v1/workflows/support/{uuid.uuid4()}", json={"status": "resolved"})).status_code == 401
