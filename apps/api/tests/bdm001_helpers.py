"""bdm-001 test builders. Every value is unique per call: the test database is shared and never truncated."""

import uuid

from app.core.security import hash_password
from app.models import User

PASSWORD = "Sup3r-Secret-Pass!"
USERS = "/api/v1/admin/users"


def email(prefix: str = "bdm001") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.local"


def emp() -> str:
    return f"E-{uuid.uuid4().hex[:10]}"


async def make_user(db, role: str, division: str, *, active: bool = True, name: str | None = None) -> User:
    user = User(
        email=email(role.replace("_", "-")), password_hash=hash_password(PASSWORD), full_name=name or f"{role} {uuid.uuid4().hex[:4]}",
        role=role, division=division, active=active, email_verified=True,
    )
    db.add(user)
    await db.commit()
    return user


async def make_manager(db, *, active: bool = True, name: str | None = None) -> User:
    return await make_user(db, "bdm_manager", "global", active=active, name=name)


async def login(client, user: User):
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD, "division": user.division})
    assert response.status_code == 200, response.text
    return response


def bdm_payload(manager_id, *, bdm_type: str = "college", **overrides) -> dict:
    payload = {
        "role": "bdm", "email": email("bdm"), "full_name": "Asha BDM", "phone": "+91 90000 00000",
        "bdm_profile": {"bdm_type": bdm_type, "employee_id": emp(), "designation": "BDM", "territory": "Kochi", "reporting_manager_user_id": str(manager_id)},
    }
    payload.update(overrides)
    return payload


async def create_bdm(client, manager_id, **overrides):
    return await client.post(USERS, json=bdm_payload(manager_id, **overrides))
