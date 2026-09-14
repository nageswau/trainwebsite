"""Verifies the Zoho Meeting live-class integration against the real Zoho API, using the
real credentials now present in `.env` (`ZOHO_CLIENT_ID`/`SECRET`/`REFRESH_TOKEN`/
`ORGANIZATION_ID`/`PRESENTER_ID`) -- exercised for real, not mocked, same treatment
`STU-010`/`PAY-001` gave real Razorpay TEST credentials.

Found and fixed a real, confirmed bug verifying this: `ZOHO_MEETING_BASE_URL` in `.env`
was `https://meeting.zoho.com`, but this account's OAuth tokens are issued by
`https://accounts.zoho.in` (an India-data-center account) -- Zoho OAuth tokens are
data-center-scoped, so calling the `.com` Meeting API with an `.in`-issued token failed
with a real `401 INVALID_OAUTHTOKEN`, confirmed directly against the live API before
changing anything. Corrected to `https://meeting.zoho.in`, matching the account's actual
data center (exactly the region-mismatch risk `PENDING_ZOHO_LIVE_CLASSES.md` had already
flagged as unconfirmed). `create_provider_meeting("zoho_meeting", ...)` now succeeds end
to end and returns a real, live, joinable session.
"""

import datetime
import uuid

import pytest

from app.core.config import settings
from app.core.security import hash_password
from app.models import Batch, Program, User
from app.services.meetings import MeetingProviderError, create_provider_meeting


async def _create_trainer(db_session) -> User:
    trainer = User(
        email=f"zoho-trainer-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Zoho Verification Trainer",
        role="trainer",
        division="it",
        active=True,
    )
    db_session.add(trainer)
    await db_session.commit()
    return trainer


async def _create_batch(db_session, trainer: User) -> Batch:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"Zoho Verification Program {uuid.uuid4().hex[:6]}",
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
    await db_session.commit()
    return batch


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_real_zoho_credentials_are_configured():
    """Sanity check that this environment actually has real credentials -- if this
    fails, every other test below will fail for the boring reason (not configured), not
    because the integration itself is broken."""
    assert settings.zoho_client_id
    assert settings.zoho_client_secret
    assert settings.zoho_refresh_token
    assert settings.zoho_organization_id
    assert settings.zoho_presenter_id


@pytest.mark.asyncio
async def test_create_provider_meeting_creates_a_real_zoho_session():
    starts = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
    ends = starts + datetime.timedelta(hours=1)
    try:
        result = await create_provider_meeting(
            "zoho_meeting",
            title=f"pytest Zoho verification {uuid.uuid4().hex[:8]}",
            agenda="Automated real-API verification.",
            starts_at=starts,
            ends_at=ends,
            attendee_emails=[],
        )
    except MeetingProviderError as exc:
        pytest.fail(f"Real Zoho Meeting API call failed: {exc}")
    assert result.provider == "zoho_meeting"
    assert result.meeting_url  # a real join link, not a placeholder
    assert result.host_url
    assert result.provider_meeting_id
    assert result.sync_status == "created"


@pytest.mark.asyncio
async def test_trainer_schedules_a_real_zoho_live_session_via_the_api(client, db_session):
    trainer = await _create_trainer(db_session)
    batch = await _create_batch(db_session, trainer)
    await _login(client, trainer.email)

    starts = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=2)).isoformat()
    ends = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=2, hours=1)).isoformat()
    response = await client.post(
        "/api/v1/communications/it/live-sessions",
        json={"batch_id": str(batch.id), "title": "Zoho E2E verification session", "starts_at": starts, "ends_at": ends, "provider": "zoho_meeting"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["provider"] == "zoho_meeting"
    assert body["sync_status"] == "created"
    assert body["meeting_url"]
    assert body["host_url"]
