import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.identifiers import unique_student_code
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.models import AuditLog, Notification, NotificationDelivery, PasswordResetToken, User, UserRoleAssignment
from app.schemas import LoginRequest, LoginResponse, ProfileUpdate, RegistrationRequest, UserOut
from app.services.integrations import send_notification

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger("app.auth")


async def _sync_role_assignment(db: AsyncSession, user: User, assigned_by_user_id: UUID | None = None) -> UserRoleAssignment:
    """Ensure a UserRoleAssignment row exists for `user`'s primary (division, role).

    Foundation-level plumbing only (FND-002, DATA_MODEL.md §1.1) -- keeps the new
    division-aware identity model in sync with the legacy User.role/User.division columns
    every existing base-codebase route still reads, so neither representation drifts out
    of the other. Idempotent: existing assignments are never overwritten (in particular,
    an Agent's approval_status is never reset by a later login).
    """

    existing = await db.scalar(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user.id,
            UserRoleAssignment.division == user.division,
            UserRoleAssignment.role == user.role,
        )
    )
    if existing:
        return existing
    assignment = UserRoleAssignment(
        user_id=user.id,
        division=user.division,
        role=user.role,
        is_active=True,
        assigned_by_user_id=assigned_by_user_id,
        approval_status="pending" if user.role == "agent" else "approved",
    )
    db.add(assignment)
    await db.flush()
    return assignment


def _set_auth_cookies(response: Response, user: User):
    access = create_token(str(user.id), user.role, user.division, "access")
    refresh = create_token(str(user.id), user.role, user.division, "refresh")
    common = {"httponly": True, "secure": settings.cookie_secure, "samesite": "lax", "path": "/"}
    response.set_cookie("edusphere_access", access, max_age=settings.access_token_minutes * 60, **common)
    response.set_cookie("edusphere_refresh", refresh, max_age=settings.refresh_token_days * 86400, **common)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == payload.email.lower(), User.active.is_(True)))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    if user.role != "super_admin" and payload.division != user.division:
        raise HTTPException(403, "Use the correct EduSphere portal for this account")
    await _sync_role_assignment(db, user)
    _set_auth_cookies(response, user)
    db.add(AuditLog(user_id=user.id, action="auth.login", entity_type="user", entity_id=str(user.id), metadata_json={"division": payload.division}))
    await db.commit()
    user = await db.scalar(select(User).where(User.id == user.id).options(selectinload(User.role_assignments)))
    return LoginResponse(user=UserOut.model_validate(user), expires_in_minutes=settings.access_token_minutes)


@router.post("/register", status_code=201)
async def register(payload: RegistrationRequest, response: Response, db: AsyncSession = Depends(get_db)):
    email = payload.email.lower().strip()
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    role = "agent" if payload.account_type == "agent" else ("it_student" if payload.division == "it" else "overseas_student")
    student_code = await unique_student_code(db, User.student_code) if role in ("it_student", "overseas_student") else None
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=role,
        division=payload.division,
        phone=payload.phone,
        active=True,
        email_verified=False,
        student_code=student_code,
        profile={"registration_source": "self_service"},
    )
    db.add(user)
    await db.flush()
    await _sync_role_assignment(db, user)
    db.add(AuditLog(user_id=user.id, action="auth.register", entity_type="user", entity_id=str(user.id), metadata_json={"division": user.division, "role": user.role}))
    await db.commit()
    loaded = await db.scalar(select(User).where(User.id == user.id).options(selectinload(User.role_assignments)))
    assert loaded is not None
    _set_auth_cookies(response, loaded)
    return {"user": UserOut.model_validate(loaded), "expires_in_minutes": settings.access_token_minutes}


@router.post("/refresh", response_model=LoginResponse)
async def refresh(response: Response, edusphere_refresh: str | None = Cookie(default=None), db: AsyncSession = Depends(get_db)):
    if not edusphere_refresh:
        raise HTTPException(401, "Refresh session missing")
    try:
        p = decode_token(edusphere_refresh)
        if p.get("type") != "refresh":
            raise ValueError()
        uid = UUID(p["sub"])
    except Exception as exc:
        raise HTTPException(401, "Invalid refresh session") from exc
    user = await db.scalar(
        select(User).where(User.id == uid, User.active.is_(True)).options(selectinload(User.role_assignments))
    )
    if not user:
        raise HTTPException(401, "User unavailable")
    _set_auth_cookies(response, user)
    return LoginResponse(user=UserOut.model_validate(user), expires_in_minutes=settings.access_token_minutes)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("edusphere_access", path="/")
    response.delete_cookie("edusphere_refresh", path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(payload: ProfileUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    changes = payload.model_dump(exclude_unset=True)
    if "full_name" in changes:
        user.full_name = changes["full_name"].strip()
    if "phone" in changes:
        user.phone = changes["phone"]
    if "profile" in changes:
        user.profile = {**(user.profile or {}), **changes["profile"]}
    db.add(AuditLog(user_id=user.id, action="profile.update", entity_type="user", entity_id=str(user.id), metadata_json={"fields": list(changes)}))
    await db.commit()
    await db.refresh(user, attribute_names=["full_name", "phone", "profile", "role_assignments"])
    return user


@router.post("/forgot-password", status_code=202)
async def forgot_password(payload: dict, db: AsyncSession = Depends(get_db)):
    email = str(payload.get("email", "")).lower().strip()
    user = await db.scalar(select(User).where(User.email == email, User.active.is_(True)))
    # Always return the same shape to reduce account enumeration.
    if user:
        raw = secrets.token_urlsafe(32)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        item = PasswordResetToken(user_id=user.id, token_hash=digest, expires_at=datetime.now(UTC) + timedelta(minutes=30))
        db.add(item)
        await db.commit()
        notification = Notification(user_id=user.id, title="Password reset requested", body="Use the link we emailed you to reset your password. It expires in 30 minutes.", read=False, action_url=None)
        db.add(notification)
        await db.flush()
        status, error = await send_notification("email", {"to": user.email, "template": "password_reset", "reset_token": raw, "expires_minutes": 30})
        db.add(NotificationDelivery(notification_id=notification.id, channel="email", status=status, error=error, sent_at=datetime.now(UTC) if status == "sent" else None))
        await db.commit()
        # Development-only token exposure, disabled in production.
        if settings.environment == "development":
            return {"accepted": True, "development_reset_token": raw}
    return {"accepted": True}


@router.post("/reset-password")
async def reset_password(payload: dict, db: AsyncSession = Depends(get_db)):
    raw = str(payload.get("token", ""))
    new_password = str(payload.get("new_password", ""))
    if len(new_password) < 10:
        raise HTTPException(422, "Password must be at least 10 characters")
    if len(new_password) > 128:
        # Same cap as the registration schemas; bcrypt silently ignores bytes past 72 anyway.
        raise HTTPException(422, "Password must be at most 128 characters")
    digest = hashlib.sha256(raw.encode()).hexdigest()
    now = datetime.now(UTC)
    # Lock order: user row FIRST, then the token -- the same order Re-send uses. Consuming the token first and updating
    # the user afterwards was the opposite order, so a reset racing a Re-send could deadlock (Postgres aborts one -> 500).
    # The plain lookup takes no lock; an unknown token is the same generic 400 as every other failure.
    owner_id = await db.scalar(select(PasswordResetToken.user_id).where(PasswordResetToken.token_hash == digest))
    if owner_id is None:
        raise HTTPException(400, "Reset token is invalid or expired")
    user = await db.scalar(select(User).where(User.id == owner_id).with_for_update())
    if not user:
        raise HTTPException(400, "User unavailable")
    # ENH-003: consume atomically so "single-use" holds under concurrency -- a read-then-write
    # let two simultaneous submissions both pass `used_at IS NULL`. Every failure (unknown, used,
    # expired, superseded) is deliberately the same 400 so a caller cannot tell them apart. bcrypt
    # only runs after a valid token, so invalid requests cannot burn CPU.
    consumed = (
        await db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.token_hash == digest, PasswordResetToken.used_at.is_(None), PasswordResetToken.superseded_at.is_(None), PasswordResetToken.expires_at > now)
            .values(used_at=now)
            .returning(PasswordResetToken.purpose)
        )
    ).first()
    if not consumed:
        raise HTTPException(400, "Reset token is invalid or expired")
    welcome = consumed.purpose == "welcome"
    if welcome and not user.active:
        # A welcome link is only good for an active account (security review S2): the rollback keeps
        # the token unconsumed, and deactivation/reactivation revokes it (Task 6).
        logger.warning("welcome_link_refused_inactive_account", extra={"extra_fields": {"user_id": str(user.id)}})
        raise HTTPException(400, "Reset token is invalid or expired")
    user.password_hash = hash_password(new_password)
    if welcome:
        # The link was delivered to this address, so using it proves control of it (DEC-SCOPE-019 #5).
        user.email_verified = True
    db.add(AuditLog(user_id=user.id, action="auth.welcome_password_set" if welcome else "auth.password_reset", entity_type="user", entity_id=str(user.id), metadata_json={}))
    await db.commit()
    if welcome:
        logger.info("welcome_password_set", extra={"extra_fields": {"user_id": str(user.id)}})
    return {"ok": True}
