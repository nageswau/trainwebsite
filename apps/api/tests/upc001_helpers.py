"""upc-001 test builders, on top of bdm-001's and tel-001's. Every value is unique per call: the test database is shared and never
truncated."""

from app.models import User
from tests.bdm001_helpers import PASSWORD, USERS, email, emp, login, make_user
from tests.tel001_helpers import sign_in_as_created

__all__ = ["PASSWORD", "USERS", "as_role", "create_manager", "emp", "head_payload", "login", "make_head", "make_user", "pm_payload", "sign_in_as_created"]


async def make_head(db, *, active: bool = True, name: str | None = None) -> User:
    return await make_user(db, "partnership_head", "global", active=active, name=name)


async def as_role(client, db, role: str, division: str) -> User:
    actor = await make_user(db, role, division)
    await login(client, actor)
    return actor


def pm_payload(head_id, **overrides) -> dict:
    payload = {
        "role": "partnership_manager", "email": email("pm"), "full_name": "Rahul Partnerships", "phone": "+91 90000 00002",
        "partnership_profile": {"employee_id": emp(), "reporting_head_user_id": str(head_id)},
    }
    payload.update(overrides)
    return payload


def head_payload(**overrides) -> dict:
    payload = {"role": "partnership_head", "division": "global", "email": email("ph"), "full_name": "Hema Head"}
    payload.update(overrides)
    return payload


async def create_manager(client, head_id, **overrides):
    return await client.post(USERS, json=pm_payload(head_id, **overrides))
