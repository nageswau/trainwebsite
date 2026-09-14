"""PUB-004 -- Webinar listing and registration.

Covers: public listing (Event, division-scoped, no dedicated Webinar table -- see
DATA_MODEL.md §2.4 correction / alembic 0009), in-app registration capture (net-new --
Event.registration_url was only ever an external link), the past-webinar-closes-
registration edge case (PUB-004-AC02), and no-auth-required (PUB-004-AC03).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Event, WebinarRegistration


async def _make_event(db_session, *, division="it", starts_at=None):
    event = Event(
        division=division,
        title=f"Test Webinar {uuid.uuid4().hex[:8]}",
        event_type="Webinar",
        starts_at=starts_at or (datetime.now(UTC) + timedelta(days=5)),
        location="Online",
        description="A test webinar.",
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


@pytest.mark.asyncio
async def test_webinars_list_is_public_and_division_scoped(client, db_session):
    it_event = await _make_event(db_session, division="it")
    overseas_event = await _make_event(db_session, division="overseas")

    response = await client.get("/api/v1/public/webinars?division=it")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert str(it_event.id) in ids
    assert str(overseas_event.id) not in ids


@pytest.mark.asyncio
async def test_webinar_detail_404s_for_unknown_id(client):
    response = await client.get(f"/api/v1/public/webinars/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_visitor_can_register_for_an_upcoming_webinar_no_auth(client, db_session):
    event = await _make_event(db_session)
    email = f"visitor-{uuid.uuid4().hex[:8]}@example.com"

    response = await client.post(
        f"/api/v1/public/webinars/{event.id}/register",
        json={"full_name": "Test Visitor", "email": email, "phone": "+919999000000"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "registered"


@pytest.mark.asyncio
async def test_registration_persists_and_is_linked_to_the_event(client, db_session):
    from sqlalchemy import select

    event = await _make_event(db_session)
    email = f"visitor-{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(
        f"/api/v1/public/webinars/{event.id}/register",
        json={"full_name": "Persisted Visitor", "email": email},
    )
    assert response.status_code == 201

    reg = await db_session.scalar(select(WebinarRegistration).where(WebinarRegistration.email == email))
    assert reg is not None
    assert reg.event_id == event.id


@pytest.mark.asyncio
async def test_registration_for_a_past_webinar_is_rejected_not_silently_accepted(client, db_session):
    # PUB-004-AC02 / SCR-PUB-016: a past webinar shows a closed state, not an open form
    # -- enforced at the API layer, not just hidden in the UI.
    event = await _make_event(db_session, starts_at=datetime.now(UTC) - timedelta(days=1))

    response = await client.post(
        f"/api/v1/public/webinars/{event.id}/register",
        json={"full_name": "Late Visitor", "email": f"late-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_registration_for_unknown_webinar_404s(client):
    response = await client.post(
        f"/api/v1/public/webinars/{uuid.uuid4()}/register",
        json={"full_name": "Nobody", "email": f"nobody-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_registration_capacity_is_unenforced_open_item_accepts_unconditionally(client, db_session):
    # DATA_MODEL.md §2.4: capacity/waitlist is a documented open item -- no invented cap.
    # Two registrations for the same event must both succeed.
    event = await _make_event(db_session)
    for _ in range(2):
        response = await client.post(
            f"/api/v1/public/webinars/{event.id}/register",
            json={"full_name": "Repeat Visitor", "email": f"repeat-{uuid.uuid4().hex[:8]}@example.com"},
        )
        assert response.status_code == 201
