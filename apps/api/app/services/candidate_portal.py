"""hrc-022 (DEC-SCOPE-386, spec docs/superpowers/specs/2026-11-04-hrc-022-candidate-portal-identity-design.md): the external candidate's
own login -- registration (C2), email verification and the candidate link (C3/C4), resend (C5), the own profile with the allow-listed
self-service fields (C7/C10/C11), the verified email change (C9) and the pool consent (C12).

Functions only; nothing here commits -- the route owns the transaction, and emails go out after it (C2, the ENH-032 idiom). Tokens are
hashed at rest and never logged or audited; logs and audit rows carry ids, never an email, phone or name."""

import hashlib
import logging
import math
import secrets
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models import AuditLog, Candidate, CandidateConsent, CandidateSelfServiceSetting, User, UserVerificationToken
from app.notifications.phone import normalise_phone
from app.schemas import CANDIDATE_FIELD_LABELS, CandidateUpdate
from app.services import candidate_duplicates as duplicates
from app.services import candidate_profile as profile
from app.services import candidates as svc
from app.services import recruitment_history, website_intake
from app.services.mailer import send_generic_notification_email
from app.services.provisioning import DEV_TOKEN_ENVIRONMENTS
from app.services.telecaller import _parse

logger = logging.getLogger("app.candidate_portal")

ROLE = "candidate"
DIVISION = "it"
TOKEN_TTL = timedelta(hours=24)
INVALID_TOKEN = "This link is invalid or has expired"
NO_PROFILE = "Your candidate profile is not available -- contact the recruitment team"

# C2: at most REGISTER_MAX_PER_IP registrations per client IP per rolling hour, counted from the audit rows each attempt writes.
REGISTER_MAX_PER_IP = 5
REGISTER_WINDOW = timedelta(hours=1)
THROTTLED = "Too many registrations from this network -- try again later"
# C5/C9: at most EMAILS_PER_WINDOW verification emails (resend) or email-change requests per user per rolling EMAIL_WINDOW.
EMAILS_PER_WINDOW = 3
EMAIL_WINDOW = timedelta(minutes=15)
EMAIL_CHANGE_REQUESTED = "candidate_portal.email_change_request"

# C12 (the rec-010 idiom): the wording the candidate agrees to; a new wording gets a new version.
CONSENT_VERSION = "candidate-v1"
CONSENT_TEXT = (
    "I agree that EduSphere may keep my profile in its candidate pool and that its recruiters may contact me about jobs. I can leave "
    "the pool at any time from Privacy; my existing applications continue."
)

# C7: every field a candidate could ever edit, and the default allow-list (all but the name). Email (C9) and mobile (C8) never.
UNIVERSE = (
    "name", "city", "state", "country", "linkedin", "current_company", "notice_days", "preferred_roles", "tools", "languages",
    "available_from", "willing_to_relocate", "preferred_contact",
)  # fmt: skip
DEFAULT_FIELDS = tuple(f for f in UNIVERSE if f != "name")


class Delivery(NamedTuple):
    """An email to send after the commit: never stored, never logged."""

    to_email: str
    name: str
    purpose: str
    raw: str


def _label(field: str) -> str:
    return CANDIDATE_FIELD_LABELS.get(field, field)


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _wait(newest: list[datetime], cap: int, window: timedelta) -> int:
    """Seconds until the oldest of the newest `cap` events leaves the window; 0 when under the cap. Clamped against clock skew."""
    if len(newest) < cap:
        return 0
    remaining = (newest[-1] + window - datetime.now(UTC)).total_seconds()
    return min(int(window.total_seconds()), max(1, math.ceil(remaining)))


def dev_token(delivery: Delivery | None) -> dict:
    """Development/test only (the ENH-003 idiom): the raw token in the response, so the flow is testable without a mailbox."""
    return {"development_verification_token": delivery.raw} if delivery and settings.environment in DEV_TOKEN_ENVIRONMENTS else {}


# --- tokens ------------------------------------------------------------------------------------------------------------------------
async def _issue(db: AsyncSession, user: User, purpose: str, new_email: str | None = None) -> str:
    """Supersedes the user's open tokens of this purpose (only the newest link works) and stores a new one."""
    now = datetime.now(UTC)
    await db.execute(
        update(UserVerificationToken)
        .where(UserVerificationToken.user_id == user.id, UserVerificationToken.purpose == purpose, UserVerificationToken.used_at.is_(None),
               UserVerificationToken.superseded_at.is_(None))
        .values(superseded_at=now)
    )  # fmt: skip
    raw = secrets.token_urlsafe(32)
    db.add(UserVerificationToken(user_id=user.id, purpose=purpose, token_hash=_digest(raw), new_email=new_email, expires_at=now + TOKEN_TTL))
    return raw


async def _recent_tokens(db: AsyncSession, user: User, purpose: str) -> int:
    since = datetime.now(UTC) - EMAIL_WINDOW
    return await db.scalar(
        select(func.count()).select_from(UserVerificationToken)
        .where(UserVerificationToken.user_id == user.id, UserVerificationToken.purpose == purpose, UserVerificationToken.created_at > since)
    ) or 0  # fmt: skip


async def deliver(delivery: Delivery) -> None:
    """A background task after the response. The link travels only in the email; the outcome is logged by status, never the token."""
    url = f"{settings.frontend_url}/it/careers/verify-email?token={delivery.raw}"
    if delivery.purpose == "email_change":
        title, body = "Confirm your new email address", "Confirm this address to use it for your EduSphere candidate account. The link expires in 24 hours."
    else:
        title, body = "Verify your email address", "Verify your email to finish creating your EduSphere candidate account. The link expires in 24 hours."
    status, _error = await send_generic_notification_email(to_email=delivery.to_email, recipient_name=delivery.name, title=title, body=body, action_url=url)
    logger.log(logging.INFO if status == "sent" else logging.WARNING, "candidate_verification_email", extra={"extra_fields": {"purpose": delivery.purpose, "status": status}})


# --- C2 registration / C5 resend ---------------------------------------------------------------------------------------------------
async def register_wait_seconds(db: AsyncSession, ip: str) -> int:
    newest = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.action == "candidate_portal.register", AuditLog.created_at > datetime.now(UTC) - REGISTER_WINDOW,
                   AuditLog.metadata_json["ip"].as_string() == ip)
            .order_by(AuditLog.created_at.desc())
            .limit(REGISTER_MAX_PER_IP)
        )
    ).all()  # fmt: skip
    return _wait(list(newest), REGISTER_MAX_PER_IP, REGISTER_WINDOW)


async def register(db: AsyncSession, *, full_name: str, email: str, phone: str | None, password: str, ip: str, utm: dict | None = None) -> Delivery | None:
    """C2: a new email creates an unverified candidate account; an unverified candidate's email re-sends its link (C5 cap); any other
    existing email does nothing. Every attempt is audited with the IP (the throttle key), so the answer never depends on the email."""
    if wait := await register_wait_seconds(db, ip):
        logger.warning("candidate_register_throttled", extra={"extra_fields": {"wait_seconds": wait}})
        raise HTTPException(429, THROTTLED, headers={"Retry-After": str(wait)})
    account = await db.scalar(select(User).where(func.lower(User.email) == email).with_for_update())
    delivery, outcome = None, "exists"
    if account is None:
        user = User(email=email, password_hash=hash_password(password), full_name=full_name, role=ROLE, division=DIVISION, phone=phone, active=True,
                    email_verified=False, profile={"registration_source": "candidate_portal", "candidate_consent_version": CONSENT_VERSION,
                             **({"utm": utm} if utm else {})})  # fmt: skip
        try:
            async with db.begin_nested():  # a concurrent signup for the same email loses at the unique index: the same 202, nothing sent
                db.add(user)
                await db.flush()
            account, outcome = user, "created"
            delivery = Delivery(email, full_name, "verify_email", await _issue(db, user, "verify_email"))
        except IntegrityError:
            pass
    elif account.role == ROLE and not account.email_verified and account.active:
        delivery, outcome = await _resend(db, account), "resent"
    db.add(AuditLog(user_id=account.id if account else None, action="candidate_portal.register", entity_type="user",
                    entity_id=str(account.id) if account else None, metadata_json={"ip": ip, "outcome": outcome}))  # fmt: skip
    return delivery


async def _resend(db: AsyncSession, user: User) -> Delivery | None:
    if await _recent_tokens(db, user, "verify_email") >= EMAILS_PER_WINDOW:
        return None  # over the cap: the same answer, nothing sent (no enumeration signal)
    return Delivery(user.email, user.full_name, "verify_email", await _issue(db, user, "verify_email"))


async def resend(db: AsyncSession, email: str) -> Delivery | None:
    user = await db.scalar(select(User).where(func.lower(User.email) == email, User.role == ROLE, User.active.is_(True)).with_for_update())
    if user is None or user.email_verified:
        return None
    return await _resend(db, user)


# --- C3/C4 verification ------------------------------------------------------------------------------------------------------------
def _consent(db: AsyncSession, user: User, candidate: Candidate, action: str, ip: str | None) -> None:
    db.add(CandidateConsent(candidate_id=candidate.id, user_id=user.id, action=action, consent_version=CONSENT_VERSION, ip_address=ip,
                            source="portal", lawful_basis="consent"))  # hrc-035 K1
    db.add(AuditLog(user_id=user.id, action=f"candidate_portal.{action}", entity_type="candidates", entity_id=str(candidate.id), metadata_json={}))


async def _email_in_use(db: AsyncSession, email: str, user: User) -> bool:
    other_user = await db.scalar(select(User.id).where(func.lower(User.email) == email, User.id != user.id))
    other_candidate = await db.scalar(select(Candidate.id).where(func.lower(Candidate.email) == email, Candidate.user_id.is_distinct_from(user.id)))
    return bool(other_user or other_candidate)


async def link_candidate(db: AsyncSession, user: User, ip: str | None) -> Candidate | None:
    """C4: the user's candidate -- the linked one; else an unlinked, unmerged candidate with the (verified) email, claimed; else a new one.
    Never matched by phone (unverified). A contact another candidate already holds is left off; with neither left, no candidate (logged)."""
    if candidate := await db.scalar(select(Candidate).where(Candidate.user_id == user.id)):
        return candidate
    now = datetime.now(UTC)
    claimed = await db.scalar(
        select(Candidate).where(func.lower(Candidate.email) == user.email, Candidate.user_id.is_(None), Candidate.merged_into_id.is_(None)).with_for_update()
    )
    if claimed:
        claimed.user_id, claimed.opted_in, claimed.email_verified_at, claimed.updated_by_user_id = user.id, True, now, user.id
        _consent(db, user, claimed, "opt_in", ip)
        logger.info("candidate_portal_claimed", extra={"extra_fields": {"user_id": str(user.id), "candidate_id": str(claimed.id)}})
        return claimed
    mobile_key = normalise_phone(user.phone) if user.phone else None
    email_taken = await db.scalar(select(Candidate.id).where(func.lower(Candidate.email) == user.email))
    mobile_taken = mobile_key and await db.scalar(select(Candidate.id).where(Candidate.mobile_normalized == mobile_key))
    email = None if email_taken else user.email
    mobile_key = None if mobile_taken else mobile_key
    if email is None and mobile_key is None:
        logger.warning("candidate_portal_no_contact", extra={"extra_fields": {"user_id": str(user.id)}})
        return None
    candidate = Candidate(candidate_code=await svc.next_code(db), name=user.full_name[:160], email=email, email_verified_at=now if email else None,
                          mobile=user.phone if mobile_key else None, mobile_normalized=mobile_key, preferred_locations=[], source_id=await website_intake.source_id(db),
                          user_id=user.id, opted_in=True, created_by_user_id=user.id,
                          # hrc-023 W2: the website registration form is a Website source, with the visit's UTM kept at registration
                          source_detail=website_intake.DETAIL_REGISTRATION, utm=website_intake.clean_utm((user.profile or {}).get("utm")))  # fmt: skip
    db.add(candidate)
    await db.flush()
    _consent(db, user, candidate, "opt_in", ip)
    await duplicates.detect(db, candidate.id)  # hrc-014 D2: as any new candidate
    return candidate


async def verify(db: AsyncSession, raw: str, ip: str | None) -> str:
    """C3: consume a token once (lock order: user row, then the token -- the reset-password order). Every failure is one 400."""
    owner_id = await db.scalar(select(UserVerificationToken.user_id).where(UserVerificationToken.token_hash == _digest(raw)))
    if owner_id is None:
        raise HTTPException(400, INVALID_TOKEN)
    user = await db.scalar(select(User).where(User.id == owner_id).with_for_update())
    now = datetime.now(UTC)
    consumed = (
        await db.execute(
            update(UserVerificationToken)
            .where(UserVerificationToken.token_hash == _digest(raw), UserVerificationToken.used_at.is_(None),
                   UserVerificationToken.superseded_at.is_(None), UserVerificationToken.expires_at > now)
            .values(used_at=now)
            .returning(UserVerificationToken.purpose, UserVerificationToken.new_email)
        )
    ).first()  # fmt: skip
    if not consumed or not user.active or user.role != ROLE:
        raise HTTPException(400, INVALID_TOKEN)
    if consumed.purpose == "verify_email":
        user.email_verified = True
        candidate = await link_candidate(db, user, ip)
        db.add(AuditLog(user_id=user.id, action="candidate_portal.email_verified", entity_type="user", entity_id=str(user.id),
                        metadata_json={"candidate_id": str(candidate.id) if candidate else None}))  # fmt: skip
        return consumed.purpose
    # C9: the new address replaces the old only now, and only while nobody else has taken it meanwhile.
    new_email = consumed.new_email
    if await _email_in_use(db, new_email, user):
        raise HTTPException(409, "That email address is already in use")
    user.email, user.email_verified = new_email, True
    candidate = await db.scalar(select(Candidate).where(Candidate.user_id == user.id).with_for_update())
    if candidate:
        before = {"email": candidate.email}
        candidate.email, candidate.email_verified_at, candidate.updated_by_user_id, candidate.updated_at = new_email, now, user.id, now
        svc.audit(db, user, "update", candidate, {"fields": ["email"], "changes": recruitment_history.diff(before, {"email": new_email}), "self_service": True})
    db.add(AuditLog(user_id=user.id, action="candidate_portal.email_changed", entity_type="user", entity_id=str(user.id), metadata_json={}))
    return consumed.purpose


# --- C10/C11 own profile -----------------------------------------------------------------------------------------------------------
async def allow_list(db: AsyncSession) -> list[str]:
    stored = await db.scalar(select(CandidateSelfServiceSetting.fields).where(CandidateSelfServiceSetting.id == 1))
    return [f for f in stored if f in UNIVERSE] if stored is not None else list(DEFAULT_FIELDS)


async def save_allow_list(db: AsyncSession, user: User, fields) -> list[str]:
    if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
        raise HTTPException(422, "Choose the fields as a list")
    if unknown := [f for f in fields if f not in UNIVERSE]:
        raise HTTPException(422, f"{_label(unknown[0])} cannot be offered for self-service")
    chosen = list(dict.fromkeys(fields))
    row = await db.get(CandidateSelfServiceSetting, 1, with_for_update=True)
    if row is None:
        row = CandidateSelfServiceSetting(id=1)
        db.add(row)
    before = row.fields if row.fields is not None else list(DEFAULT_FIELDS)
    row.fields, row.updated_by_user_id = chosen, user.id
    db.add(AuditLog(user_id=user.id, action="candidate.self_service_settings", entity_type="candidate_self_service_settings", entity_id="1",
                    metadata_json={"from": before, "to": chosen}))  # fmt: skip
    return chosen


async def own(db: AsyncSession, user: User, lock: bool = False) -> Candidate:
    stmt = select(Candidate).where(Candidate.user_id == user.id, Candidate.merged_into_id.is_(None))
    candidate = await db.scalar(stmt.with_for_update() if lock else stmt)
    if candidate is None:
        raise HTTPException(404, NO_PROFILE)
    return candidate


async def pending_email(db: AsyncSession, user: User) -> str | None:
    return await db.scalar(
        select(UserVerificationToken.new_email)
        .where(UserVerificationToken.user_id == user.id, UserVerificationToken.purpose == "email_change", UserVerificationToken.used_at.is_(None),
               UserVerificationToken.superseded_at.is_(None), UserVerificationToken.expires_at > datetime.now(UTC))
        .order_by(UserVerificationToken.created_at.desc()).limit(1)
    )  # fmt: skip


async def profile_out(db: AsyncSession, user: User, candidate: Candidate) -> dict:
    return {
        "candidate_code": candidate.candidate_code,
        "name": candidate.name,
        "email": user.email,
        "email_verified": candidate.email_verified_at is not None,
        "mobile": candidate.mobile,
        "pending_email": await pending_email(db, user),
        "fields": {f: getattr(candidate, f) for f in UNIVERSE},
        "editable": await allow_list(db),
    }


async def update_profile(db: AsyncSession, user: User, payload) -> Candidate:
    """C11: the recruiter schema validates (same rules and messages); a key outside the universe is 422, outside the allow-list 403."""
    if isinstance(payload, dict) and (outside := [k for k in payload if k not in UNIVERSE]):
        raise HTTPException(422, f"{_label(outside[0])} cannot be changed in the portal")
    changes = _parse(CandidateUpdate, payload, "Send the fields to change", CANDIDATE_FIELD_LABELS).model_dump(exclude_unset=True)
    allowed = await allow_list(db)
    if refused := [k for k in changes if k not in allowed]:
        raise HTTPException(403, f"{_label(refused[0])} cannot be changed here -- ask your recruiter")
    candidate = await own(db, user, lock=True)
    if candidate.archived_at is not None:
        raise HTTPException(409, svc.ARCHIVED)
    audited = {*changes, *profile.DERIVED}
    stored = await profile.rows(db, candidate.id)
    before = await svc.audited_values(db, candidate, audited)
    applied = svc.apply_fields(candidate, changes)
    profile.sync(candidate, stored, set(changes), stored)  # P5: the place and first preferred role mirrors follow
    changed = recruitment_history.diff(before, await svc.audited_values(db, candidate, audited))
    fields = sorted((set(applied) - set(profile.DERIVED)) | set(changed))
    if fields:
        candidate.updated_by_user_id, candidate.updated_at = user.id, datetime.now(UTC)
        await svc.flush_candidate(db, candidate)
        svc.audit(db, user, "update", candidate, {"fields": fields, "changes": changed, "self_service": True})
        if duplicates.WATCHED & set(fields):  # hrc-014 D2, as a recruiter edit
            await duplicates.detect(db, candidate.id)
        svc.log("candidate_self_service_update", user, candidate, fields=fields)
    return candidate


# --- C9 email change ---------------------------------------------------------------------------------------------------------------
async def email_change_wait_seconds(db: AsyncSession, user: User) -> int:
    """C9: every request is audited and counted, whatever the address, so the cap reveals nothing about it."""
    since = datetime.now(UTC) - EMAIL_WINDOW
    newest = (await db.scalars(select(AuditLog.created_at).where(AuditLog.user_id == user.id, AuditLog.action == EMAIL_CHANGE_REQUESTED,
                                                                 AuditLog.created_at > since).order_by(AuditLog.created_at.desc()).limit(EMAILS_PER_WINDOW))).all()  # fmt: skip
    return _wait(list(newest), EMAILS_PER_WINDOW, EMAIL_WINDOW)


async def request_email_change(db: AsyncSession, user: User, new_email: str) -> Delivery | None:
    """After the route has checked the throttles and the current password. An address in use gets no link (enumeration-safe)."""
    if new_email == user.email:
        raise HTTPException(422, "That is already your email address")
    db.add(AuditLog(user_id=user.id, action=EMAIL_CHANGE_REQUESTED, entity_type="user", entity_id=str(user.id), metadata_json={}))
    if await _email_in_use(db, new_email, user):
        return None  # enumeration-safe: the same 202, nothing sent
    return Delivery(new_email, user.full_name, "email_change", await _issue(db, user, "email_change", new_email))


# --- C12 privacy -------------------------------------------------------------------------------------------------------------------
async def privacy_out(db: AsyncSession, candidate: Candidate) -> dict:
    history = (await db.scalars(select(CandidateConsent).where(CandidateConsent.candidate_id == candidate.id)
                                .order_by(CandidateConsent.created_at, CandidateConsent.id).limit(50))).all()  # fmt: skip
    return {
        "opted_in": candidate.opted_in,
        "consent": {"version": CONSENT_VERSION, "text": CONSENT_TEXT},
        "history": [{"action": c.action, "consent_version": c.consent_version, "created_at": c.created_at} for c in history],
    }


async def set_consent(db: AsyncSession, user: User, opted_in: bool, ip: str | None) -> Candidate:
    candidate = await own(db, user, lock=True)
    if candidate.opted_in != opted_in:
        candidate.opted_in = opted_in
        _consent(db, user, candidate, "opt_in" if opted_in else "opt_out", ip)
    return candidate
