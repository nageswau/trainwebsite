"""One-off production admin bootstrap -- NOT part of the app's normal startup path and
NOT related to app/seed.py (that script creates a large batch of demo/fake data with the
published password "Demo@123" and must never be run against a real database).

This creates real super_admin / it_admin / overseas_admin accounts using credentials you
supply at invocation time via environment variables -- nothing here is hardcoded, nothing
is written to any file, and a password is never printed back. Safe to re-run: an account
that already exists with the matching role is left untouched and reported as skipped; an
existing account under the same email but a different role is left untouched and refused,
never silently overwritten.

Usage (run once, right after the database is up, then discard the values you passed):

    docker compose exec \
      -e SUPER_ADMIN_EMAIL=you@yourdomain.com -e SUPER_ADMIN_PASSWORD='...' \
      -e IT_ADMIN_EMAIL=itadmin@yourdomain.com -e IT_ADMIN_PASSWORD='...' \
      -e OVERSEAS_ADMIN_EMAIL=overseasadmin@yourdomain.com -e OVERSEAS_ADMIN_PASSWORD='...' \
      api python -m app.bootstrap_admin

Any of the three email/password pairs may be omitted (that role is simply skipped) -- run
it for one role at a time, or all three in one pass. *_NAME is optional for each.
"""

import asyncio
import os
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import User, UserRoleAssignment

# (env prefix, role, division, default full_name) -- division convention matches the
# same three roles' existing dev-seed accounts (app/seed.py) for consistency.
ROLES = [
    ("SUPER_ADMIN", "super_admin", "global", "Super Admin"),
    ("IT_ADMIN", "it_admin", "it", "IT Division Administrator"),
    ("OVERSEAS_ADMIN", "overseas_admin", "overseas", "Overseas Administrator"),
]

MIN_PASSWORD_LENGTH = 12
REJECTED_PASSWORDS = {"demo@123", "password", "changeme", "admin", "admin123", "password123"}


async def _bootstrap_one(db, *, env_prefix: str, role: str, division: str, default_name: str) -> tuple[str, bool]:
    """Returns (message, was_configured) -- was_configured is True whenever this role's
    env vars were actually provided, regardless of whether the outcome was create/skip/
    refuse, so the final summary can tell "nothing configured" apart from "already done"."""
    email = os.environ.get(f"{env_prefix}_EMAIL", "").strip().lower()
    password = os.environ.get(f"{env_prefix}_PASSWORD", "")
    full_name = os.environ.get(f"{env_prefix}_NAME", default_name).strip()

    if not email and not password:
        return f"{role}: skipped (no {env_prefix}_EMAIL/{env_prefix}_PASSWORD set)", False
    if not email or not password:
        return f"{role}: REFUSED -- set both {env_prefix}_EMAIL and {env_prefix}_PASSWORD, not just one", True
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"{role}: REFUSED -- {env_prefix}_PASSWORD is shorter than {MIN_PASSWORD_LENGTH} characters", True
    if password.lower() in REJECTED_PASSWORDS:
        return f"{role}: REFUSED -- {env_prefix}_PASSWORD is a known default/demo password, not safe for production", True

    existing = await db.scalar(select(User).where(User.email == email))
    if existing:
        if existing.role == role:
            return f"{role}: already exists with this role, left unchanged (password not touched) -- {email}", True
        return f"{role}: REFUSED -- {email} already exists as role '{existing.role}', not overwriting", True

    account = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
        division=division,
        active=True,
        email_verified=True,
        profile={},
    )
    db.add(account)
    await db.flush()
    db.add(UserRoleAssignment(user_id=account.id, division=division, role=role, is_active=True, approval_status="approved"))
    return f"{role}: created -- {email}", True


async def main() -> int:
    async with SessionLocal() as db:
        outcomes = [await _bootstrap_one(db, env_prefix=p, role=r, division=d, default_name=n) for p, r, d, n in ROLES]
        results = [message for message, _ in outcomes]
        any_configured = any(was_configured for _, was_configured in outcomes)
        any_created = any(": created" in r for r in results)
        any_refused = any("REFUSED" in r for r in results)
        if any_created:
            await db.commit()
        else:
            await db.rollback()
    for line in results:
        print(line)
    if not any_configured:
        print("\nNothing to do -- no *_EMAIL/*_PASSWORD environment variables were set for any role.")
        return 1
    if not any_created and not any_refused:
        print("\nAll requested accounts already existed with the matching role -- nothing new created.")
    return 2 if any_refused else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
