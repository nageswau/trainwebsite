"""AGN-002 -- session version (spec §5, E1): a bumped users.session_version ends every older session; legacy tokens still work."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import update

from app.core.config import settings
from app.core.security import ALGORITHM, create_token, decode_token
from app.models import User
from tests.agn001_helpers import login, mk_user


def _legacy_token(user: User, token_type: str) -> str:
    """A token minted the way every token was before AGN-002: no `sv` claim."""
    exp = datetime.now(UTC) + timedelta(minutes=5)
    return jwt.encode({"sub": str(user.id), "role": user.role, "division": user.division, "type": token_type, "exp": exp}, settings.secret_key, algorithm=ALGORITHM)


def test_create_token_carries_the_session_version():
    assert decode_token(create_token("u", "agent", "overseas", "access", session_version=3))["sv"] == 3
    assert decode_token(create_token("u", "agent", "overseas"))["sv"] == 0


@pytest.mark.asyncio
async def test_a_token_without_sv_still_works(client, db_session):
    user = await mk_user(db_session, role="overseas_student")
    client.cookies.set("edusphere_access", _legacy_token(user, "access"))
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    client.cookies.set("edusphere_refresh", _legacy_token(user, "refresh"))
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200


@pytest.mark.asyncio
async def test_bumping_the_version_ends_access_and_refresh(client, db_session):
    user = await mk_user(db_session, role="overseas_student")
    await login(client, user.email)
    old_access, old_refresh = client.cookies.get("edusphere_access"), client.cookies.get("edusphere_refresh")
    await db_session.execute(update(User).where(User.id == user.id).values(session_version=User.session_version + 1))
    await db_session.commit()
    client.cookies.set("edusphere_access", old_access)
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 401 and me.json()["detail"] == "Session ended"
    client.cookies.set("edusphere_refresh", old_refresh)
    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 401 and refreshed.json()["detail"] == "Session ended"


@pytest.mark.asyncio
async def test_signing_in_again_after_a_bump_works_immediately(client, db_session):
    user = await mk_user(db_session, role="overseas_student")
    await db_session.execute(update(User).where(User.id == user.id).values(session_version=5))
    await db_session.commit()
    await login(client, user.email)
    assert decode_token(client.cookies.get("edusphere_access"))["sv"] == 5
    assert (await client.get("/api/v1/auth/me")).status_code == 200
