"""tel-004 test builders. Every value is unique per call: the test database is shared and never truncated."""

import uuid

from app.models import Enquiry, TelecallerProfile, User
from tests.tel001_helpers import emp, login, make_tl_manager, make_user

__all__ = ["lead", "login", "make_telecaller", "make_tl_manager", "make_user", "stage_url", "history_url"]


def stage_url(lead_id) -> str:
    return f"/api/v1/telecaller/leads/{lead_id}/stage"


def history_url(lead_id, *, admin: bool = False) -> str:
    return f"/api/v1/{'admin' if admin else 'telecaller'}/leads/{lead_id}/stage-history"


async def make_telecaller(db, manager: User, *, team: str = "it") -> User:
    user = await make_user(db, "telecaller", team)
    db.add(TelecallerProfile(user_id=user.id, team=team, employee_id=emp(), reporting_manager_user_id=manager.id))
    await db.commit()
    return user


async def lead(db, *, division: str = "it", telecaller: User | None = None, status: str = "new") -> Enquiry:
    row = Enquiry(division=division, name=f"Lead {uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:8]}@example.local", subject="Python",
                  message="Hello", source="website", status=status, telecaller_user_id=telecaller.id if telecaller else None)
    db.add(row)
    await db.commit()
    return row
