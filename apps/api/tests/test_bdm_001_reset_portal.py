"""bdm-001 -- reset-password names the sign-in portal for a BDM manager (spec §5.6; AC05, AC15)."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import PasswordResetToken
from tests.bdm001_helpers import make_manager, make_user

NEW_PASSWORD = "Brand-New-Pass-1!"


async def _token(db, user, purpose: str = "welcome") -> str:
    raw = uuid.uuid4().hex * 2
    db.add(PasswordResetToken(user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), purpose=purpose, expires_at=datetime.now(UTC) + timedelta(hours=72)))
    await db.commit()
    return raw


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "division", "portal"),
    [("bdm_manager", "global", "admin"), ("bdm", "it", None), ("it_student", "it", None), ("super_admin", "global", None)],
)
async def test_login_portal_is_admin_only_for_a_manager(client, db_session, role, division, portal):
    user = await make_manager(db_session) if role == "bdm_manager" else await make_user(db_session, role, division)
    response = await client.post("/api/v1/auth/reset-password", json={"token": await _token(db_session, user), "new_password": NEW_PASSWORD})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "login_portal": portal}


@pytest.mark.asyncio
async def test_forgot_password_reset_also_names_the_portal(client, db_session):
    manager = await make_manager(db_session)
    response = await client.post("/api/v1/auth/reset-password", json={"token": await _token(db_session, manager, "reset"), "new_password": NEW_PASSWORD})
    assert response.json() == {"ok": True, "login_portal": "admin"}


@pytest.mark.asyncio
async def test_invalid_link_is_still_the_generic_400(client):
    response = await client.post("/api/v1/auth/reset-password", json={"token": "nope", "new_password": NEW_PASSWORD})
    assert response.status_code == 400
    assert "login_portal" not in response.json()
