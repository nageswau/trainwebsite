"""ENH-003 / DEC-SCOPE-019 -- first-time provisioning of admin-created accounts.

An admin never knows or chooses a credential: the account is created with an unusable password
hash and the user receives a single-use, hashed-at-rest, 72-hour set-password link
(`PasswordResetToken`, `purpose="welcome"`). Functions only -- no new abstraction layer.

Transaction shape (spec §6): the caller creates the user and calls `issue_welcome_token` in ONE
transaction and commits; `deliver_welcome_link` runs AFTER that commit, so a failed or
unconfigured send can never roll back the account, and never holds a DB transaction open across
the (up to 10 s) SMTP call. `deliver_welcome_link` never raises.
"""

import asyncio
import hashlib
import logging
import math
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import AuditLog, PasswordResetToken, User
from app.services.integrations import send_notification
from app.services.mailer import send_welcome_email

logger = logging.getLogger("app.provisioning")

WELCOME_EXPIRY_HOURS = 72
DEV_TOKEN_ENVIRONMENTS = ("development", "test")
RESEND_COOLDOWN_SECONDS = 60

_URL = re.compile(r"https?://\S+")
_EMAIL = re.compile(r"[^\s<>@,;]+@[^\s<>@,;]+")


class IssuedWelcome(NamedTuple):
    raw: str
    expires_at: datetime
    token_id: UUID


def unusable_password_hash() -> str:
    """Hash of a random secret that is discarded immediately -- never a constant."""
    return hash_password(secrets.token_urlsafe(48))


def _set_password_url(user: User, raw: str) -> str:
    # Built from configuration, never from the request's Host header (no host-header poisoning).
    segment = "overseas" if user.division == "overseas" else "it"  # super_admin logs in via /it
    return f"{settings.frontend_url}/{segment}/reset-password?token={raw}"


def _redact(text: str | None) -> str | None:
    """Stored/logged errors can echo a webhook/SMTP URL (which may embed a secret) or the recipient's
    address (SMTP refusals often do); keep neither. URLs go first because they can contain '@'."""
    return None if text is None else _EMAIL.sub("[redacted-email]", _URL.sub("[redacted-url]", text))[:500]


def _outcome(result) -> tuple[str, str | None]:
    if isinstance(result, BaseException):  # a sender that raised is a failed send, not a 500
        return "failed", _redact(str(result))
    status, error = result
    return status, _redact(error)


async def revoke_welcome_tokens(db: AsyncSession, user_id: UUID) -> None:
    """No commit. Supersedes the user's open welcome tokens. Used by Re-send (old link replaced) and
    when an admin changes `active`, so a link mailed to a wrong recipient cannot come back to life on
    reactivation -- the account then reads `link_expired` and needs an explicit Re-send."""
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user_id, PasswordResetToken.purpose == "welcome", PasswordResetToken.used_at.is_(None), PasswordResetToken.superseded_at.is_(None))
        .values(superseded_at=datetime.now(UTC))
    )


async def issue_welcome_token(db: AsyncSession, *, user: User, issued_by: User) -> IssuedWelcome:
    """No commit. Revokes open welcome tokens, inserts a new one, audits the issue (token id + expiry
    only -- never the raw token)."""
    await revoke_welcome_tokens(db, user.id)
    raw = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=WELCOME_EXPIRY_HOURS)
    token = PasswordResetToken(user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), purpose="welcome", expires_at=expires_at)
    db.add(token)
    await db.flush()
    db.add(
        AuditLog(user_id=issued_by.id, action="user.welcome_link_issue", entity_type="user", entity_id=str(user.id), metadata_json={"token_id": str(token.id), "expires_at": expires_at.isoformat()})
    )
    return IssuedWelcome(raw, expires_at, token.id)


async def deliver_welcome_link(*, user: User, issued: IssuedWelcome, issued_by: User) -> dict:
    """Call AFTER the caller's commit. SMTP and the generic webhook (parity with the invite flow)
    run concurrently; a sender that raises counts as a failed send. The outcome is audited
    (statuses and URL-redacted errors, never the raw token). Never raises."""
    webhook, smtp = await asyncio.gather(
        send_notification("email", {"to": user.email, "template": "welcome_set_password", "reset_token": issued.raw, "expires_hours": WELCOME_EXPIRY_HOURS}),
        send_welcome_email(
            to_email=user.email,
            recipient_name=user.full_name,
            role=user.role,
            set_password_url=_set_password_url(user, issued.raw),
            expires_at=issued.expires_at,
            invited_by_name=issued_by.full_name,
        ),
        return_exceptions=True,
    )
    webhook_status, webhook_error = _outcome(webhook)
    smtp_status, smtp_error = _outcome(smtp)
    delivered = smtp_status == "sent"
    # Operational signal for "did this person get a link?": ids and statuses only -- never the
    # token, the address, or an unredacted error. `not_configured` is a WARNING on purpose: it
    # leaves an account nobody can reach until an admin Re-sends.
    logger.log(
        logging.INFO if delivered else logging.WARNING,
        "welcome_link_delivered" if delivered else "welcome_link_not_delivered",
        extra={
            "extra_fields": {
                "user_id": str(user.id),
                "issued_by": str(issued_by.id),
                "token_id": str(issued.token_id),
                "smtp_status": smtp_status,
                "smtp_error": smtp_error,
                "webhook_status": webhook_status,
            }
        },
    )
    # Audited in its OWN short session. Rolling back the request's session on an audit failure would expire every ORM
    # object the route still reads to build its response (async lazy-load -> MissingGreenlet -> a 500 for an account and
    # token that are already committed). A failed audit write is logged; it never reaches the caller.
    try:
        async with SessionLocal() as audit_db:
            audit_db.add(
                AuditLog(
                    user_id=issued_by.id,
                    action="user.welcome_link_delivery",
                    entity_type="user",
                    entity_id=str(user.id),
                    metadata_json={"token_id": str(issued.token_id), "smtp_status": smtp_status, "smtp_error": smtp_error, "webhook_status": webhook_status, "webhook_error": webhook_error},
                )
            )
            await audit_db.commit()
    except Exception:
        logger.exception("welcome_link_audit_failed", extra={"extra_fields": {"user_id": str(user.id), "token_id": str(issued.token_id)}})
    result = {"email_status": smtp_status, "expires_at": issued.expires_at}
    if settings.environment in DEV_TOKEN_ENVIRONMENTS:
        result["development_welcome_token"] = issued.raw
    return result


async def provisioning_statuses(db: AsyncSession, user_ids) -> dict[UUID, str]:
    """Derived from each user's LATEST welcome token (superseded ones included, so a revoked link
    with nothing newer reads `link_expired` and stays Re-sendable). A user who has since set a
    password -- the latest welcome token was used, or any token was used at/after its creation
    (e.g. forgot-password) -- is active, i.e. absent. Values are "pending_setup" or "link_expired".
    Two queries; no N+1."""
    ids = list(user_ids)
    if not ids:
        return {}
    tokens = (await db.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id.in_(ids), PasswordResetToken.purpose == "welcome"))).all()
    latest: dict[UUID, PasswordResetToken] = {}
    for token in tokens:
        current = latest.get(token.user_id)
        if current is None or token.created_at > current.created_at:
            latest[token.user_id] = token
    unused = [user_id for user_id, token in latest.items() if token.used_at is None]
    if not unused:
        return {}
    rows = (
        await db.execute(
            select(PasswordResetToken.user_id, func.max(PasswordResetToken.used_at))
            .where(PasswordResetToken.user_id.in_(unused), PasswordResetToken.used_at.is_not(None))
            .group_by(PasswordResetToken.user_id)
        )
    ).all()
    last_used = {row[0]: row[1] for row in rows}
    now = datetime.now(UTC)
    result: dict[UUID, str] = {}
    for user_id in unused:
        token = latest[user_id]
        used = last_used.get(user_id)
        if used is not None and used >= token.created_at:
            continue
        expired = token.superseded_at is not None or token.expires_at < now
        result[user_id] = "link_expired" if expired else "pending_setup"
    return result


async def user_ids_with_status(db: AsyncSession, actor: User, status: str) -> list[UUID]:
    """Active users in the actor's scope (all divisions for super_admin) whose derived
    provisioning status equals `status` -- the exact set, not limited by any list cap."""
    stmt = select(User.id).where(
        User.active.is_(True),
        User.id.in_(select(PasswordResetToken.user_id).where(PasswordResetToken.purpose == "welcome", PasswordResetToken.used_at.is_(None))),
    )
    if actor.role != "super_admin":
        stmt = stmt.where(User.division == actor.division)
    candidates = list((await db.scalars(stmt)).all())
    statuses = await provisioning_statuses(db, candidates)
    return [user_id for user_id in candidates if statuses.get(user_id) == status]


async def resend_wait_seconds(db: AsyncSession, user_id: UUID) -> int:
    """Per-account Re-send throttle (security review 2026-09-19): the first Re-send after creation is
    always allowed; any later one within RESEND_COOLDOWN_SECONDS of the newest welcome link is not.
    0 means allowed. Capped so DB/app clock skew can never produce an absurd wait."""
    count, newest = (
        await db.execute(select(func.count(PasswordResetToken.id), func.max(PasswordResetToken.created_at)).where(PasswordResetToken.user_id == user_id, PasswordResetToken.purpose == "welcome"))
    ).one()
    if count < 2:
        return 0
    remaining = RESEND_COOLDOWN_SECONDS - (datetime.now(UTC) - newest).total_seconds()
    return min(RESEND_COOLDOWN_SECONDS, max(0, math.ceil(remaining)))
