"""tel-001 test builders, on top of bdm-001's. Every value is unique per call: the test database is shared and never truncated."""

import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.models import User
from tests.bdm001_helpers import PASSWORD, USERS, email, emp, login, make_user

__all__ = ["PASSWORD", "USERS", "create_telecaller", "emp", "login", "make_tl_manager", "make_user", "sign_in_as_created", "tel_payload"]


async def make_tl_manager(db, *, active: bool = True, name: str | None = None) -> User:
    return await make_user(db, "telecaller_manager", "global", active=active, name=name)


def tel_payload(manager_id, *, team: str = "it", **overrides) -> dict:
    payload = {
        "role": "telecaller", "email": email("tel"), "full_name": "Ravi Telecaller", "phone": "+91 90000 00001",
        "telecaller_profile": {"team": team, "employee_id": emp(), "reporting_manager_user_id": str(manager_id)},
    }
    payload.update(overrides)
    return payload


async def create_telecaller(client, manager_id, **overrides):
    return await client.post(USERS, json=tel_payload(manager_id, **overrides))


async def sign_in_as_created(client, db, created: dict) -> User:
    """An admin-created account has an unusable password; give it the test password so it can sign in."""
    user = await db.scalar(select(User).where(User.id == uuid.UUID(created["id"])))
    user.password_hash = hash_password(PASSWORD)
    await db.commit()
    await login(client, user)
    return user
