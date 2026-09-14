"""OVS-007 -- Events and workshops (Overseas division).

The registration endpoint (`POST /public/webinars/{id}/register`) already existed and
was already division-agnostic over any `Event` row (confirmed by reading
`app/api/public.py::webinar_register` -- it never filters or checks `Event.division`),
built generically by PUB-004. It was already exercised against an `it`-division event
there; this file closes the gap of actually confirming it against an `overseas`-division
event too, rather than assuming the lack of a division check extends here. The real
`OVS-007` gap was entirely frontend: `/overseas/events` never linked to an in-app
registration flow at all (see `apps/web/app/overseas/events/[id]/page.tsx`, new).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Event, WebinarRegistration


async def _make_overseas_event(db_session, *, starts_at=None):
    event = Event(
        division="overseas",
        title=f"Test Overseas Event {uuid.uuid4().hex[:8]}",
        event_type="Education Fair",
        starts_at=starts_at or (datetime.now(UTC) + timedelta(days=10)),
        location="Online",
        description="A test overseas event.",
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


@pytest.mark.asyncio
async def test_overseas_event_is_visible_in_the_division_scoped_listing(client, db_session):
    event = await _make_overseas_event(db_session)

    response = await client.get("/api/v1/public/events?division=overseas")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert str(event.id) in ids


@pytest.mark.asyncio
async def test_anyone_can_register_for_an_overseas_event_with_no_authentication(client, db_session):
    from sqlalchemy import select

    event = await _make_overseas_event(db_session)
    email = f"visitor-{uuid.uuid4().hex[:8]}@example.com"

    response = await client.post(
        f"/api/v1/public/webinars/{event.id}/register",
        json={"full_name": "Overseas Visitor", "email": email},
    )
    assert response.status_code == 201

    reg = await db_session.scalar(select(WebinarRegistration).where(WebinarRegistration.email == email))
    assert reg is not None
    assert reg.event_id == event.id


@pytest.mark.asyncio
async def test_registration_for_a_past_overseas_event_is_rejected(client, db_session):
    event = await _make_overseas_event(db_session, starts_at=datetime.now(UTC) - timedelta(days=2))

    response = await client.post(
        f"/api/v1/public/webinars/{event.id}/register",
        json={"full_name": "Late Visitor", "email": f"late-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert response.status_code == 409
