"""ENH-014 test helpers (same precedent as enh005_helpers.py)."""

import uuid
from datetime import UTC, datetime

from app.core.security import hash_password
from app.models import NotificationPreference, User, UserRoleAssignment

PASSWORD = "Sup3r-Secret-Pass!"


async def make_user(db, *, role: str = "school_parent", division: str = "overseas", phone: str | None = None, active: bool = True) -> User:
    user = User(
        email=f"enh014-{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password(PASSWORD),
        full_name="Enh Fourteen",
        role=role,
        division=division,
        active=active,
        phone=phone,
    )
    db.add(user)
    await db.flush()
    db.add(UserRoleAssignment(user_id=user.id, division=division, role=role, is_active=True, assigned_by_user_id=user.id, approval_status="approved"))
    await db.commit()
    return user


async def login(client, email: str, division: str = "overseas") -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": division})
    assert response.status_code == 200, response.text


async def set_prefs(db, user: User, *, whatsapp: bool = False, sms: bool = False) -> None:
    now = datetime.now(UTC)
    db.add(NotificationPreference(user_id=user.id, whatsapp_opt_in=whatsapp, sms_opt_in=sms, whatsapp_opted_in_at=now if whatsapp else None, sms_opted_in_at=now if sms else None))
    await db.commit()
