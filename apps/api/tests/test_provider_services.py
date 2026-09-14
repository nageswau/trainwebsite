from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.schemas import RegistrationRequest
from app.services.meetings import MeetingProviderError, _google_join_url, create_provider_meeting
from app.services.payment import payments


@pytest.mark.asyncio
async def test_manual_meeting_requires_a_link():
    now = datetime.now(UTC)
    with pytest.raises(MeetingProviderError, match="meeting URL"):
        await create_provider_meeting("manual", title="Class", agenda="", starts_at=now, ends_at=now + timedelta(hours=1), attendee_emails=[])


@pytest.mark.asyncio
async def test_manual_meeting_returns_provider_link():
    now = datetime.now(UTC)
    result = await create_provider_meeting("manual", title="Class", agenda="", starts_at=now, ends_at=now + timedelta(hours=1), attendee_emails=[], meeting_url="https://meet.example.test/class")
    assert result.provider == "manual"
    assert result.meeting_url == "https://meet.example.test/class"
    assert result.sync_status == "manual"


@pytest.mark.asyncio
async def test_google_meet_requires_configuration(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", None)
    monkeypatch.setattr(settings, "google_client_secret", None)
    monkeypatch.setattr(settings, "google_refresh_token", None)
    now = datetime.now(UTC)
    with pytest.raises(MeetingProviderError, match="not configured"):
        await create_provider_meeting("google_meet", title="Class", agenda="", starts_at=now, ends_at=now + timedelta(hours=1), attendee_emails=[])


def test_google_join_url_supports_both_response_shapes():
    assert _google_join_url({"hangoutLink": "https://meet.google.com/abc-defg-hij"}).endswith("abc-defg-hij")
    assert _google_join_url({"conferenceData": {"entryPoints": [{"entryPointType": "video", "uri": "https://meet.google.com/xyz"}]}}).endswith("xyz")


@pytest.mark.asyncio
async def test_payment_provider_reports_missing_configuration(monkeypatch):
    monkeypatch.setattr(settings, "razorpay_key_id", None)
    monkeypatch.setattr(settings, "razorpay_key_secret", None)
    result = await payments.create_checkout("razorpay", 1000, "INR", "EDU-TEST")
    assert result["status"] == "configuration_required"
    assert result["provider"] == "razorpay"


def test_it_agent_registration_is_rejected():
    with pytest.raises(ValidationError):
        RegistrationRequest(email="agent@example.com", password="long-password", full_name="Agent User", division="it", account_type="agent")
