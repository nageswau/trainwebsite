"""nehn-022 (DEC-SCOPE-282): RAZORPAY_MODE=test|live, checked at startup against the key prefix; the non-secret mode read for the
payment-screen banner; the admin system-status row."""

import uuid

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.security import hash_password
from app.models import User

LIVE = {"razorpay_key_id": "rzp_live_AbC123", "razorpay_key_secret": "live-secret-xyz", "razorpay_webhook_secret": "live-hook-xyz"}
TEST = {"razorpay_key_id": "rzp_test_AbC123", "razorpay_key_secret": "test-secret-xyz", "razorpay_webhook_secret": "test-hook-xyz"}
NONE = {"razorpay_key_id": None, "razorpay_key_secret": None, "razorpay_webhook_secret": None}


def build(**values) -> Settings:
    return Settings(_env_file=None, **values)


# ---- AC1: startup check (M1-M3) ----


def test_mode_defaults_to_test():
    assert build(razorpay_mode="test", **NONE).razorpay_mode == "test"
    assert Settings.model_fields["razorpay_mode"].default == "test"


@pytest.mark.parametrize("keys", [NONE, TEST, {**NONE, "razorpay_key_id": ""}])
def test_test_mode_accepts_test_keys_or_none(keys):
    assert build(razorpay_mode="test", **keys).razorpay_mode == "test"


def test_live_mode_accepts_complete_live_keys():
    assert build(razorpay_mode="live", **LIVE).razorpay_mode == "live"


def test_live_mode_with_test_keys_refuses_to_start():
    with pytest.raises(ValidationError) as caught:
        build(razorpay_mode="live", **TEST)
    message = str(caught.value)
    assert "RAZORPAY_MODE=live" in message and "rzp_live_" in message


def test_test_mode_with_live_keys_refuses_to_start():
    with pytest.raises(ValidationError) as caught:
        build(razorpay_mode="test", **LIVE)
    assert "rzp_test_" in str(caught.value)


@pytest.mark.parametrize("missing", ["razorpay_key_id", "razorpay_key_secret", "razorpay_webhook_secret"])
def test_live_mode_needs_every_live_value(missing):
    with pytest.raises(ValidationError) as caught:
        build(razorpay_mode="live", **{**LIVE, missing: None})
    assert missing.upper() in str(caught.value)


def test_unknown_mode_refuses_to_start():
    with pytest.raises(ValidationError):
        build(razorpay_mode="production", **NONE)


@pytest.mark.parametrize(("mode", "keys"), [("live", TEST), ("test", LIVE), ("live", {**LIVE, "razorpay_webhook_secret": None})])
def test_the_startup_error_never_shows_a_key_or_secret(mode, keys):
    with pytest.raises(ValidationError) as caught:
        build(razorpay_mode=mode, secret_key="app-signing-secret", **keys)
    message = str(caught.value)
    for value in (*[v for v in keys.values() if v], "app-signing-secret"):
        assert value not in message


# ---- signed-in helpers ----


async def _sign_in(db_session, client, role: str, division: str = "it") -> None:
    email = f"nehn022-{uuid.uuid4().hex[:8]}@example.local"
    db_session.add(User(email=email, password_hash=hash_password("Sup3r-Secret-Pass!"), full_name="Mode Check", role=role, division=division, active=True))
    await db_session.commit()
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": division})
    assert login.status_code == 200


# ---- AC2 support: the mode read (M4) ----


@pytest.mark.asyncio
async def test_mode_read_needs_a_session(client):
    assert (await client.get("/api/v1/payments/mode")).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["test", "live"])
async def test_mode_read_reports_the_configured_mode(db_session, client, monkeypatch, mode):
    monkeypatch.setattr(settings, "razorpay_mode", mode)
    monkeypatch.setattr(settings, "razorpay_key_id", LIVE["razorpay_key_id"] if mode == "live" else TEST["razorpay_key_id"])
    await _sign_in(db_session, client, "it_student")
    response = await client.get("/api/v1/payments/mode")
    assert response.status_code == 200
    assert response.json() == {"mode": mode}  # nothing else: never a key id or secret


# ---- the admin system-status indicator (M5) ----


@pytest.mark.asyncio
@pytest.mark.parametrize(("mode", "label"), [("test", "test mode"), ("live", "live mode")])
async def test_system_status_shows_the_razorpay_mode(db_session, client, monkeypatch, mode, label):
    monkeypatch.setattr(settings, "razorpay_mode", mode)
    await _sign_in(db_session, client, "super_admin")
    response = await client.get("/api/v1/admin/system-status")
    assert response.status_code == 200
    rows = [r for r in response.json() if r["service"] == "Razorpay mode"]
    assert rows == [{"service": "Razorpay mode", "status": label}]
