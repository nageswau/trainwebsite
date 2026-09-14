"""SCH-003 -- School Coordinator invites Principal/Teacher/Parent; invite acceptance.

Net-new router. `POST /overseas-admin/schools`/`GET /overseas-admin/schools` (Overseas
Admin creates the School + seed Coordinator) live in `admin.py`'s `agents_router`
(`/overseas-admin` namespace, alongside the Agent approval routes) -- this file covers the
Coordinator-side invite flow and public token acceptance, per `API_CONTRACT.md` §12A.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _set_auth_cookies
from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import hash_password
from app.models import AuditLog, School, SchoolAccountInvite, User, UserRoleAssignment
from app.services.integrations import send_notification

router = APIRouter(prefix="/school", tags=["school"])

INVITABLE_ROLES = {"school_principal", "school_teacher", "school_parent"}
INVITE_EXPIRY_DAYS = 7


def _require_coordinator(user: User) -> UUID:
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = user.profile.get("school_id") if user.profile else None
    if not school_id:
        raise HTTPException(403, "This account is not linked to a school")
    return UUID(str(school_id))


@router.post("/team/invites", status_code=201)
async def create_invite(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    school_id = _require_coordinator(user)
    role = payload.get("role")
    if role not in INVITABLE_ROLES:
        raise HTTPException(422, f"role must be one of {sorted(INVITABLE_ROLES)}")
    email = str(payload.get("email", "")).lower().strip()
    full_name = str(payload.get("full_name", "")).strip()
    if not email or not full_name:
        raise HTTPException(422, "email and full_name are required")
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    raw = secrets.token_urlsafe(32)
    invite = SchoolAccountInvite(
        school_id=school_id,
        role=role,
        invited_by_user_id=user.id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        email=email,
        full_name=full_name,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.add(invite)
    await db.flush()
    # SCH-003: this table's own Contracts-phase note (`DATA_MODEL.md` §6.15) leaves invite
    # delivery channel as email-only per `NOT-001` -- no `Notification` row is created
    # since no `User` exists yet to own one; the send is fire-and-forget, same
    # never-block-the-write discipline as every other notification path (`OVS-004-AC02`).
    status_, error = await send_notification("email", {"to": email, "template": "school_invite", "role": role, "school_id": str(school_id), "invite_token": raw})
    db.add(AuditLog(user_id=user.id, action="school.invite_create", entity_type="school_account_invite", entity_id=str(invite.id), metadata_json={"role": role, "school_id": str(school_id), "notification_status": status_, "notification_error": error}))
    await db.commit()
    response = {"id": invite.id, "role": invite.role, "email": invite.email, "status": invite.status, "expires_at": invite.expires_at}
    from app.core.config import settings

    if settings.environment == "development":
        response["development_invite_token"] = raw
    return response


@router.get("/team")
async def list_team(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    school_id = _require_coordinator(user)
    accounts = (
        await db.scalars(select(User).where(User.role.in_(("school_principal", "school_teacher", "school_parent", "school_coordinator"))))
    ).all()
    accounts = [a for a in accounts if (a.profile or {}).get("school_id") == str(school_id)]
    invites = (
        await db.scalars(select(SchoolAccountInvite).where(SchoolAccountInvite.school_id == school_id, SchoolAccountInvite.status == "pending").order_by(SchoolAccountInvite.created_at.desc()))
    ).all()
    return {
        "accounts": [{"id": a.id, "name": a.full_name, "email": a.email, "role": a.role} for a in accounts],
        "pending_invites": [{"id": i.id, "role": i.role, "email": i.email, "full_name": i.full_name, "expires_at": i.expires_at} for i in invites],
    }


@router.post("/invites/{token}/accept", status_code=201)
async def accept_invite(token: str, payload: dict, response: Response, db: AsyncSession = Depends(get_db)):
    digest = hashlib.sha256(token.encode()).hexdigest()
    invite = await db.scalar(select(SchoolAccountInvite).where(SchoolAccountInvite.token_hash == digest))
    if not invite or invite.status != "pending":
        raise HTTPException(409, "This invite has already been used, expired, or was revoked")
    if invite.expires_at < datetime.now(UTC):
        invite.status = "expired"
        await db.commit()
        raise HTTPException(409, "This invite has already been used, expired, or was revoked")
    password = str(payload.get("password", ""))
    if len(password) < 10:
        raise HTTPException(422, "Password must be at least 10 characters")
    if await db.scalar(select(User).where(User.email == invite.email)):
        raise HTTPException(409, "Email already exists")
    # SCH-003-AC06 / DATA_MODEL.md §6.15: the resulting account's `school_id` is always the
    # invite's own `school_id`, never a value supplied at acceptance time -- closes the
    # same class of IDOR risk `AGT-002`/`UNI-001` already guard against, applied here to
    # account creation.
    account = User(
        email=invite.email,
        password_hash=hash_password(password),
        full_name=invite.full_name,
        role=invite.role,
        division="overseas",
        active=True,
        email_verified=False,
        profile={"school_id": str(invite.school_id)},
    )
    db.add(account)
    await db.flush()
    db.add(UserRoleAssignment(user_id=account.id, division="overseas", role=invite.role, is_active=True, assigned_by_user_id=invite.invited_by_user_id, approval_status="approved"))
    invite.status = "accepted"
    invite.accepted_at = datetime.now(UTC)
    invite.accepted_by_user_id = account.id
    db.add(AuditLog(user_id=account.id, action="school.invite_accept", entity_type="school_account_invite", entity_id=str(invite.id), metadata_json={"role": invite.role, "school_id": str(invite.school_id)}))
    await db.commit()
    _set_auth_cookies(response, account)
    return {"id": account.id, "email": account.email, "role": account.role}
