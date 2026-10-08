"""rec-001 test builders, on top of bdm-001's. Every value is unique per call: the test database is shared and never truncated."""

from sqlalchemy import select

from app.models import RecruiterProfile, User
from tests.bdm001_helpers import PASSWORD, USERS, email, emp, login, make_user

__all__ = ["PASSWORD", "USERS", "as_role", "create_recruiter", "email", "emp", "login", "make_pm", "make_recruiter", "make_user", "profile_of", "rec_payload"]


async def make_pm(db, *, active: bool = True, name: str | None = None) -> User:
    return await make_user(db, "placement_manager", "global", active=active, name=name)


async def make_recruiter(db, manager: User | None = None, *, employee_id: str | None = None, active: bool = True, name: str | None = None) -> User:
    """A recruiter with a profile written directly (the backfill shape when `manager` is None)."""
    user = await make_user(db, "placement_team", "it", active=active, name=name)
    db.add(RecruiterProfile(user_id=user.id, employee_id=employee_id, reporting_manager_user_id=manager.id if manager else None))
    await db.commit()
    return user


def rec_payload(manager_id, **overrides) -> dict:
    payload = {
        "role": "placement_team", "email": email("rec"), "full_name": "Priya Recruiter", "phone": "+91 90000 00002",
        "recruiter_profile": {"employee_id": emp(), "reporting_manager_user_id": str(manager_id)},
    }
    payload.update(overrides)
    return payload


async def create_recruiter(client, manager_id, **overrides):
    return await client.post(USERS, json=rec_payload(manager_id, **overrides))


async def as_role(client, db, role: str, division: str) -> User:
    actor = await make_user(db, role, division)
    await login(client, actor)
    return actor


async def profile_of(db, user_id) -> RecruiterProfile | None:
    db.expire_all()
    return await db.scalar(select(RecruiterProfile).where(RecruiterProfile.user_id == user_id))
