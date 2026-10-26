import hashlib
import logging
import math
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import check_session, get_current_user
from app.core.client_ip import client_ip
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.identifiers import unique_student_code
from app.core.rbac import agent_permissions
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.models import AgentOrg, AgentOrgKycDocument, AgentStudent, AuditLog, Notification, NotificationDelivery, PasswordResetToken, User, UserRoleAssignment
from app.schemas import ChangePasswordRequest, LoginRequest, LoginResponse, ProfileUpdate, RegistrationRequest, UserOut
from app.services import agent_kyc as kyc
from app.services.agent_orgs import ensure_agent_org
from app.services.integrations import send_notification
from app.services.mailer import send_password_reset_email
from app.services.provisioning import ADMIN_PORTAL_ROLES, portal_password_url
from app.services.telecaller import parse_self_update

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger("app.auth")
PHONE_ONLY_ROLES = {"telecaller": "Telecallers", "partnership_manager": "Partnership managers"}
PORTAL_SIGN_IN = {"it": "/it/login", "overseas": "/overseas/login", "global": "/admin/login"}

CHANGE_PASSWORD_FAILED = "auth.change_password_failed"
# DEC-SCOPE-021: 5 wrong current passwords per user per 15 minutes, counted from the audit rows written on each failure.
CHANGE_PASSWORD_MAX_FAILURES = 5
CHANGE_PASSWORD_WINDOW = timedelta(minutes=15)


async def _change_password_wait_seconds(db: AsyncSession, user_id: UUID) -> int:
    """Seconds this user must wait before another change-password attempt; 0 means allowed.

    Blocked when the newest MAX_FAILURES failures are all inside the window; the block lifts when the oldest of those
    leaves it. Derived from existing audit rows (same idea as the Re-send throttle), so it needs no table. Clamped so
    app/DB clock skew can never produce an absurd wait."""
    now = datetime.now(UTC)
    newest = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.user_id == user_id, AuditLog.action == CHANGE_PASSWORD_FAILED, AuditLog.created_at > now - CHANGE_PASSWORD_WINDOW)
            .order_by(AuditLog.created_at.desc())
            .limit(CHANGE_PASSWORD_MAX_FAILURES)
        )
    ).all()
    if len(newest) < CHANGE_PASSWORD_MAX_FAILURES:
        return 0
    remaining = (newest[-1] + CHANGE_PASSWORD_WINDOW - now).total_seconds()
    return min(int(CHANGE_PASSWORD_WINDOW.total_seconds()), max(1, math.ceil(remaining)))


async def _sync_role_assignment(db: AsyncSession, user: User, assigned_by_user_id: UUID | None = None) -> UserRoleAssignment:
    """Ensure a UserRoleAssignment row exists for `user`'s primary (division, role).

    Foundation-level plumbing only (FND-002, DATA_MODEL.md §1.1) -- keeps the new
    division-aware identity model in sync with the legacy User.role/User.division columns
    every existing base-codebase route still reads, so neither representation drifts out
    of the other. Idempotent: existing assignments are never overwritten (in particular,
    an Agent's approval_status is never reset by a later login).
    """

    assignment = await db.scalar(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user.id,
            UserRoleAssignment.division == user.division,
            UserRoleAssignment.role == user.role,
        )
    )
    if assignment is None:
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
    if user.role == "agent":
        await ensure_agent_org(db, user)  # AGN-001 (E7): every agent has an organisation
    return assignment


def _set_auth_cookies(response: Response, user: User):
    access = create_token(str(user.id), user.role, user.division, "access", user.session_version)
    refresh = create_token(str(user.id), user.role, user.division, "refresh", user.session_version)
    common = {"httponly": True, "secure": settings.cookie_secure, "samesite": "lax", "path": "/"}
    response.set_cookie("edusphere_access", access, max_age=settings.access_token_minutes * 60, **common)
    response.set_cookie("edusphere_refresh", refresh, max_age=settings.refresh_token_days * 86400, **common)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == payload.email.lower(), User.active.is_(True)))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    if user.role != "super_admin" and payload.division != user.division:
        # bdm-001 QA-07: BDMs are split across portals by module, so name the right one. Only reached after the password matched.
        raise HTTPException(403, f"Use the correct EduSphere portal for this account: sign in at {PORTAL_SIGN_IN.get(user.division, '/')}")
    await _sync_role_assignment(db, user)
    _set_auth_cookies(response, user)
    db.add(AuditLog(user_id=user.id, action="auth.login", entity_type="user", entity_id=str(user.id), metadata_json={"division": payload.division}))
    await db.commit()
    user = await db.scalar(select(User).where(User.id == user.id).options(selectinload(User.role_assignments)))
    return LoginResponse(user=UserOut.model_validate(user), expires_in_minutes=settings.access_token_minutes)


MAX_REGISTRATION_BYTES = 3 * kyc.MAX_BYTES + 1024 * 1024  # three KYC files plus form overhead


def _origin_of(url: str) -> str:
    parts = urlsplit(url.strip())
    return f"{parts.scheme}://{parts.netloc}".lower() if parts.scheme and parts.netloc else ""


def _check_form_origin(request: Request) -> None:
    """Form bodies are CORS-simple requests (no preflight), so a cross-site page could post one: refuse a foreign Origin/Referer."""
    source = request.headers.get("origin") or request.headers.get("referer")
    if source and _origin_of(source) != _origin_of(settings.frontend_url):
        raise HTTPException(403, "Cross-site registration is not allowed")


def _check_form_size(request: Request) -> None:
    """Refuse an oversize body before it is read (the form parser would spool it to disk)."""
    raw = request.headers.get("content-length", "")
    if not raw.isdigit():
        raise HTTPException(411, "Content-Length required")
    if int(raw) > MAX_REGISTRATION_BYTES:
        raise HTTPException(413, "The registration upload is too large")


def _safe_errors(errors) -> list[dict]:
    """Validation errors without `input`/`ctx`: they would echo the submitted form (password, PAN, licence number)."""
    return [{k: v for k, v in e.items() if k not in ("input", "ctx", "url")} for e in errors]


def _media_type(request: Request) -> str:
    return request.headers.get("content-type", "").split(";")[0].strip().lower()


def _is_json(media_type: str) -> bool:
    return media_type == "application/json" or (media_type.endswith("+json") and "/" in media_type)


async def _registration_input(request: Request):
    """AGN-024 (DEC-SCOPE-224): JSON as before, or multipart -- an agent's signup carries its three KYC files. Returns (fields, files,
    form-to-close). Any other content type is refused before the body is read: a cross-site `<form enctype="text/plain">` can carry
    a valid JSON object, and `request.json()` would parse it regardless of the declared type (login CSRF)."""
    media_type = _media_type(request)
    if media_type in ("multipart/form-data", "application/x-www-form-urlencoded"):
        _check_form_origin(request)
        _check_form_size(request)
        form = await request.form(max_files=3, max_fields=20)
        fields = {k: v for k, v in form.multi_items() if isinstance(v, str)}
        files = {k: v for k, v in form.multi_items() if not isinstance(v, str)}
        return fields, files, form
    if not _is_json(media_type):
        raise HTTPException(415, "Unsupported content type")
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise RequestValidationError([{"type": "json_invalid", "loc": ("body",), "msg": "A JSON object or multipart form is required"}])
    return body, {}, None


@router.post("/register", status_code=201)
async def register(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    fields, files, form = await _registration_input(request)
    try:
        return await _register(fields, files, response, db, client_ip(request))
    finally:
        if form is not None:
            await form.close()


# AGN-024 K11 (DEC-SCOPE-224): at most 5 agent signups per client IP per rolling hour -- each one stores up to 15 MB of KYC files
# from an anonymous caller. Counted from the `auth.register` audit rows, which carry the IP for agent signups (as the
# change-password throttle counts its own audit rows), so it needs no table.
AGENT_SIGNUP_MAX_PER_IP = 5
AGENT_SIGNUP_WINDOW = timedelta(hours=1)
AGENT_SIGNUP_THROTTLED = "Too many registrations from this network -- try again later"


async def _agent_signup_wait_seconds(db: AsyncSession, ip: str) -> int:
    """Seconds before this IP may register another agent; 0 means allowed. Blocked while the newest MAX signups are all inside the
    window; the block lifts when the oldest of those leaves it."""
    now = datetime.now(UTC)
    newest = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(
                AuditLog.action == "auth.register",
                AuditLog.created_at > now - AGENT_SIGNUP_WINDOW,
                AuditLog.metadata_json["role"].as_string() == "agent",
                AuditLog.metadata_json["ip"].as_string() == ip,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(AGENT_SIGNUP_MAX_PER_IP)
        )
    ).all()
    if len(newest) < AGENT_SIGNUP_MAX_PER_IP:
        return 0
    remaining = (newest[-1] + AGENT_SIGNUP_WINDOW - now).total_seconds()
    return min(int(AGENT_SIGNUP_WINDOW.total_seconds()), max(1, math.ceil(remaining)))


async def _register(fields: dict, files: dict, response: Response, db: AsyncSession, ip: str):
    try:
        payload = RegistrationRequest.model_validate(fields)
    except ValidationError as exc:
        raise RequestValidationError(_safe_errors(exc.errors(include_url=False))) from None
    is_agent = payload.account_type == "agent"
    # K1: numbers and file presence are checked before anything is looked up or stored.
    numbers = kyc.clean_numbers(fields) if is_agent else {}
    uploads = kyc.require_files(files) if is_agent else {}
    if is_agent and (wait := await _agent_signup_wait_seconds(db, ip)):  # K11: before any file is read or stored
        logger.warning("agent_signup_throttled", extra={"extra_fields": {"wait_seconds": wait}})
        raise HTTPException(429, AGENT_SIGNUP_THROTTLED, headers={"Retry-After": str(wait)})
    email = payload.email.lower().strip()
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    contents = {t: await kyc.read_kyc_file(t, f) for t, f in uploads.items()}  # K8: every file passes before any is stored
    stored: list[str] = []
    try:
        for _doc_type, (data, content_type, _name) in contents.items():
            stored.append(kyc.store(data, content_type))
        role = "agent" if is_agent else ("it_student" if payload.division == "it" else "overseas_student")
        student_code = await unique_student_code(db, User.student_code, AgentStudent.student_code) if role in ("it_student", "overseas_student") else None
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
        metadata = {"division": user.division, "role": user.role}
        if role == "agent":
            # AGN-001 (D2, E2): one pending organisation + Master M001, named from the optional agency name.
            member = await ensure_agent_org(db, user, agency_name=payload.agency_name, status="pending")
            org = await db.get(AgentOrg, member.org_id)
            org.kyc_required = True  # AGN-024 K4: only self-registered agencies are gated
            for (doc_type, (data, content_type, name)), key in zip(contents.items(), stored, strict=True):
                db.add(AgentOrgKycDocument(org_id=org.id, doc_type=doc_type, doc_number=numbers[doc_type], file_key=key, original_filename=name,
                                           content_type=content_type, file_size=len(data), status="pending", uploaded_by_user_id=user.id))  # fmt: skip
            metadata["kyc_documents"] = len(stored)
            metadata["ip"] = ip  # K11 throttle key; the IP only, never a document number
        await _sync_role_assignment(db, user)
        db.add(AuditLog(user_id=user.id, action="auth.register", entity_type="user", entity_id=str(user.id), metadata_json=metadata))
        await db.commit()
    except BaseException as exc:
        try:
            await db.rollback()
        finally:
            for key in stored:
                kyc.discard(key)
        if isinstance(exc, IntegrityError):  # a concurrent signup took the email between the check and the commit
            raise HTTPException(409, "Email already exists") from None
        raise
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
    user = await check_session(db, uid, user, p)
    _set_auth_cookies(response, user)
    return LoginResponse(user=UserOut.model_validate(user), expires_in_minutes=settings.access_token_minutes)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("edusphere_access", path="/")
    response.delete_cookie("edusphere_refresh", path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    out = UserOut.model_validate(user)
    # AGN-002: the portal hides Master-only pages from staff (the server refuses them regardless).
    out.agent_member_role = user.agent_membership.role if user.agent_membership else None
    out.agent_permissions = agent_permissions(user)
    return out


# Profile keys that carry an authorization scope. A user may echo their own current value back (the web
# "Update profile" form sends the whole profile) but may never change it: only an admin route sets these.
# school_id scopes the School portal (schools.py); university_id scopes a University Rep's access to applications
# (workflows.py, portal.py, inbound.py). assigned_grade/assigned_section are reserved, not yet backed by any
# real field or route (ENH-007's own acceptance criteria names them as the negative scenario a School
# Coordinator's teacher-assignment authority must never be bypassable through -- ENHANCEMENT_BACKLOG.md
# ENH-007, "Authorization impact"): blocked pre-emptively so a future feature that adds them to User.profile
# doesn't have to remember to add the guard too. Add a key here if a new profile key is ever used to
# authorize access.
SERVER_OWNED_PROFILE_KEYS = ("school_id", "university_id", "assigned_grade", "assigned_section")


@router.patch("/me", response_model=UserOut)
async def update_me(payload: ProfileUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    changes = payload.model_dump(exclude_unset=True)
    # Checked before anything is mutated: the audit commit below would otherwise also persist an
    # already-assigned full_name/phone from a request that is being refused.
    incoming = changes.get("profile") or {}
    current = user.profile or {}
    for key in SERVER_OWNED_PROFILE_KEYS:
        if key in incoming and incoming[key] != current.get(key):
            db.add(AuditLog(user_id=user.id, action="profile.update_denied", entity_type="user", entity_id=str(user.id), outcome="denied", metadata_json={"field": key}))
            await db.commit()
            logger.warning("profile_update_denied", extra={"extra_fields": {"user_id": str(user.id), "field": key}})
            raise HTTPException(403, f"{key} cannot be changed here")
    if user.role in PHONE_ONLY_ROLES:
        # tel-001 TL8 / upc-001 PU3: these roles change only their phone (the generic account form resubmits the unchanged name, which
        # is fine).
        name_changed = "full_name" in changes and changes["full_name"].strip() != user.full_name
        profile_changed = "profile" in changes and (changes["profile"] or {}) != (user.profile or {})
        if name_changed or profile_changed:
            raise HTTPException(403, f"{PHONE_ONLY_ROLES[user.role]} can change only their phone number — contact your administrator")
        if "phone" in changes:
            changes["phone"] = parse_self_update({"phone": changes["phone"]}).phone
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


# ENH-032 / DEC-SCOPE-225 (I1): at most RESET_EMAILS_PER_WINDOW password-reset emails per user per rolling RESET_WINDOW. A
# reset token expires RESET_TOKEN_TTL after issue, so "issued within the window" is `expires_at > now + (TTL - window)`;
# only purpose="reset" rows count (admin-provisioned welcome/set-password tokens are purpose="welcome", ENH-003). Over the cap
# the request answers exactly as usual -- no 429, no enumeration signal -- and creates/sends nothing.
RESET_EMAILS_PER_WINDOW = 3
RESET_WINDOW = timedelta(minutes=15)
RESET_TOKEN_TTL = timedelta(minutes=30)


async def _deliver_password_reset(notification_id: UUID, to_email: str, recipient_name: str, reset_url: str, raw: str) -> None:
    """ENH-032 E8 / I1: runs as a background task after the response, in its own session. The raw token travels only inside the
    link / webhook payload -- failure_text never carries it into the stored error, and it is never logged."""
    expires_minutes = int(RESET_TOKEN_TTL.total_seconds() // 60)
    status, error = await send_password_reset_email(to_email=to_email, recipient_name=recipient_name, reset_url=reset_url, expires_minutes=expires_minutes)
    if status == "not_configured":
        status, error = await send_notification("email", {"to": to_email, "template": "password_reset", "reset_token": raw, "expires_minutes": expires_minutes})
    async with SessionLocal() as db:
        db.add(NotificationDelivery(notification_id=notification_id, channel="email", status=status, error=error, sent_at=datetime.now(UTC) if status == "sent" else None))
        await db.commit()


@router.post("/forgot-password", status_code=202)
async def forgot_password(payload: dict, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    email = str(payload.get("email", "")).lower().strip()
    user = await db.scalar(select(User).where(User.email == email, User.active.is_(True)))
    # Always return the same shape to reduce account enumeration.
    if user:
        now = datetime.now(UTC)
        recent = await db.scalar(
            select(func.count()).select_from(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.purpose == "reset",
                PasswordResetToken.expires_at > now + (RESET_TOKEN_TTL - RESET_WINDOW),
            )
        )
        if (recent or 0) >= RESET_EMAILS_PER_WINDOW:
            return {"accepted": True}
        raw = secrets.token_urlsafe(32)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        db.add(PasswordResetToken(user_id=user.id, token_hash=digest, expires_at=now + RESET_TOKEN_TTL))
        notification = Notification(user_id=user.id, title="Password reset requested", body="Use the link we emailed you to reset your password. It expires in 30 minutes.", read=False, action_url=None)
        db.add(notification)
        await db.commit()
        # ENH-032 / DEC-SCOPE-225 (E8, I1): the email (configured transport, webhook fallback) is sent off the request path.
        background_tasks.add_task(_deliver_password_reset, notification.id, user.email, user.full_name, portal_password_url(user, raw), raw)
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
    # bdm-001 (spec §5.6): a BDM manager (division `global`) signs in at /admin/login, and the reset form follows this. The key is
    # always present (null for everyone else), so the response shape never varies by role.
    # bdm-001 (spec §5.6) / tel-001: a `global` manager signs in at /admin/login, and the reset form follows this. The key is always
    # present (null for everyone else), so the response shape never varies by role.
    return {"ok": True, "login_portal": "admin" if user.role in ADMIN_PORTAL_ROLES else None}


@router.post("/change-password")
async def change_password(payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # ENH-006 / DEC-SCOPE-021. The order of these checks is part of the contract (spec §4): authenticate (the
    # dependency) -> body validation (the model) -> same-password compare -> lock -> verify -> write. The compare is
    # between the two request fields only, so it reveals nothing about the stored hash.
    if payload.new_password == payload.current_password:
        raise HTTPException(422, "New password must be different from the current password")
    # get_current_user loaded this row without a lock: lock it and refresh the hash in one statement, so a request that
    # waited behind another change verifies against the hash that change committed, not a stale one.
    await db.refresh(user, attribute_names=["password_hash"], with_for_update=True)
    # Before bcrypt, so a blocked caller cannot burn CPU; a blocked attempt is logged but NOT audited as a failure, or a
    # lockout would extend itself forever.
    wait = await _change_password_wait_seconds(db, user.id)
    if wait:
        logger.warning("change_password_throttled", extra={"extra_fields": {"user_id": str(user.id), "wait_seconds": wait}})
        raise HTTPException(429, f"Too many incorrect attempts; try again in {wait} seconds", headers={"Retry-After": str(wait)})
    if not verify_password(payload.current_password, user.password_hash):
        # Commit BEFORE raising (the update_me denial pattern) so the failure survives the error response.
        db.add(AuditLog(user_id=user.id, action=CHANGE_PASSWORD_FAILED, entity_type="user", entity_id=str(user.id), outcome="denied", metadata_json={"reason": "incorrect_current_password"}))
        await db.commit()
        raise HTTPException(400, "Incorrect current password")
    user.password_hash = hash_password(payload.new_password)
    # DEC-SCOPE-021 #5: a change also kills any reset link still in the mail (it could otherwise overwrite this password
    # for up to 30 minutes). Only unused "reset" links of THIS user: welcome links belong to accounts with no password
    # yet (ENH-003's state machine), used links are history, and other users' links are not ours.
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.purpose == "reset", PasswordResetToken.used_at.is_(None), PasswordResetToken.superseded_at.is_(None))
        .values(superseded_at=datetime.now(UTC))
    )
    db.add(AuditLog(user_id=user.id, action="auth.change_password", entity_type="user", entity_id=str(user.id), metadata_json={}))
    await db.commit()
    logger.info("password_changed", extra={"extra_fields": {"user_id": str(user.id)}})
    return {"ok": True}
