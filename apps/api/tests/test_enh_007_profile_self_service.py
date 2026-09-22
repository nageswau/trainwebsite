"""ENH-007 -- Profile self-service, cross-role completion audit.
Spec: docs/superpowers/specs/2026-09-22-enh-007-profile-self-service-design.md

PATCH /auth/me already exists and is reused unmodified except for one validator fix (schemas.py).
Every test creates its own user, per this repo's convention.
"""

import uuid

import pytest
from pydantic_core import ValidationError

from app.core.security import hash_password
from app.models import User
from app.schemas import ProfileUpdate

PASSWORD = "Sup3r-Secret-Pass!"
URL = "/api/v1/auth/me"


async def _make_user(db_session, *, role="school_coordinator", division="overseas") -> User:
    user = User(
        email=f"enh007-{uuid.uuid4().hex[:10]}@example.local",
        password_hash=hash_password(PASSWORD),
        full_name="ENH-007 User",
        role=role,
        division=division,
        active=True,
        email_verified=True,
        profile={"school_id": "11111111-1111-1111-1111-111111111111"},
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _sign_in(client, user, password=PASSWORD):
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password, "division": user.division})
    assert response.status_code == 200, response.text


async def _signed_in_user(client, db_session, **kwargs) -> User:
    user = await _make_user(db_session, **kwargs)
    await _sign_in(client, user)
    return user


def test_schema_rejects_explicit_null_full_name():
    """Unit test: Pydantic validator rejects explicit null full_name."""
    with pytest.raises(ValidationError) as exc_info:
        ProfileUpdate(full_name=None)
    # Verify the error is from our validator
    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["type"] == "null_full_name"


def test_schema_accepts_valid_full_name():
    """Unit test: Pydantic validator accepts valid full_name."""
    update = ProfileUpdate(full_name="Valid Name")
    assert update.full_name == "Valid Name"


def test_schema_accepts_omitted_full_name():
    """Unit test: Omitting full_name (not sending the key) is allowed."""
    update = ProfileUpdate()
    assert update.full_name is None


@pytest.mark.asyncio
async def test_explicit_null_full_name_is_rejected_not_a_crash(client, db_session):
    """Integration test: PATCH /auth/me rejects explicit null with 422, not 500."""
    user = await _signed_in_user(client, db_session)
    response = await client.patch(URL, json={"full_name": None})
    assert response.status_code == 422, response.text
    await db_session.refresh(user)
    assert user.full_name == "ENH-007 User"  # unchanged
