"""tel-012 (DEC-SCOPE-076, spec §4-§6): the script, message-template and brochure library -- placeholder rules and rendering, the
merged-row template checks, the signed brochure links, and the stored PDF objects.

Functions only; nothing here commits -- the route owns the transaction. Audit rows carry ids and changed field names only (tel-002's
`audit`). Never log a link token or a storage key (a digest only)."""

import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import ALGORITHM, decode_token
from app.models import TelAsset, TelMessageTemplate, TelProduct, TelScript, User
from app.services.storage import storage
from app.tel_content_kinds import KINDS_BY_CHANNEL

logger = logging.getLogger("app.telecaller_content")

# Recorded default (spec §1): telecallers read the library; managers and super_admin also write and see inactive rows.
CONTENT_READERS = frozenset({"telecaller", "telecaller_manager", "super_admin"})
SCRIPT_INDEX, TEMPLATE_NAME_INDEX = "uq_tel_scripts_active_product", "uq_tel_message_templates_channel_name"
CHANNEL_LABEL = {"whatsapp": "WhatsApp", "email": "email"}
BODY_LIMIT = {"whatsapp": 1000, "email": 5000}

PLACEHOLDERS = ("name", "product", "brochure_link", "appointment_time")
_TOKEN = re.compile(r"\{([^{}\n]*)\}")
_UNKNOWN = "Unknown placeholder {%s}. Use {name}, {product}, {brochure_link} or {appointment_time}"
# The preview's stand-in lead (C2: rendering from a real lead arrives with tel-008/tel-013).
SAMPLE_VALUES = {"name": "Priya Sharma", "product": "Cyber Security", "appointment_time": "Mon 14 Sept 2026, 10:30 AM"}

# C1: a brochure link is a signed, asset-scoped token for 7 days. Its type is never "access", so deps.get_current_user refuses it.
LINK_TTL = timedelta(days=7)
LINK_TYPE = "tel_asset"
PUBLIC_ASSET_PATH = "/api/v1/public/telecaller-assets/"
STORAGE_PREFIX = "tel-assets"
PDF = "application/pdf"


def require_content_reader(user: User) -> None:
    if user.role not in CONTENT_READERS:
        raise HTTPException(403, "Your role cannot view the telecaller library")


# --- placeholders ---------------------------------------------------------------------------------------------------------------
def check_placeholders(*texts: str | None) -> set[str]:
    """AC3: every `{...}` in the texts must be one of the four placeholders, spelled exactly; returns the ones used. A lone brace is
    plain text."""
    used: set[str] = set()
    for text in texts:
        for token in _TOKEN.findall(text or ""):
            if token not in PLACEHOLDERS:
                raise HTTPException(422, _UNKNOWN % token)
            used.add(token)
    return used


def render(text: str, values: dict[str, str]) -> str:
    """AC2: one pass, so a value that looks like a placeholder is never expanded again; a missing value renders empty. Plain text out --
    the sink escapes (wa.me URL-encoding in tel-013, HTML in tel-014)."""
    return _TOKEN.sub(lambda m: values.get(m.group(1), "") if m.group(1) in PLACEHOLDERS else m.group(0), text)


def check_template(channel: str, kind: str, subject: str | None, body: str, asset_id) -> None:
    """The template rules, on the merged row (create, or a row plus a PATCH)."""
    if kind not in KINDS_BY_CHANNEL[channel]:
        raise HTTPException(422, f"Choose {'a WhatsApp' if channel == 'whatsapp' else 'an email'} template kind")
    if channel == "whatsapp" and subject is not None:
        raise HTTPException(422, "Only email templates have a subject")
    if channel == "email" and subject is None:
        raise HTTPException(422, "Subject is required")
    if len(body) > BODY_LIMIT[channel]:
        raise HTTPException(422, f"{'A WhatsApp' if channel == 'whatsapp' else 'An email'} message must be at most {BODY_LIMIT[channel]} characters")
    if "brochure_link" in check_placeholders(subject, body) and asset_id is None:
        raise HTTPException(422, "Attach a brochure to use {brochure_link}")


async def locked_active_asset(db: AsyncSession, asset_id) -> TelAsset:
    """FOR SHARE: a concurrent deactivation waits for this template's commit (the tel-002 `locked_active_product` idiom)."""
    asset = await db.scalar(select(TelAsset).where(TelAsset.id == asset_id).with_for_update(read=True))
    if not asset or not asset.active:
        raise HTTPException(422, "Choose an active brochure")
    return asset


# --- signed brochure links ------------------------------------------------------------------------------------------------------
def asset_link(asset: TelAsset) -> dict:
    expires_at = datetime.now(UTC) + LINK_TTL
    token = jwt.encode({"sub": str(asset.id), "type": LINK_TYPE, "exp": expires_at}, settings.secret_key, algorithm=ALGORITHM)
    return {"url": f"{settings.frontend_url.rstrip('/')}{PUBLIC_ASSET_PATH}{token}", "expires_at": expires_at.replace(microsecond=0)}


async def asset_from_token(db: AsyncSession, token: str) -> TelAsset | None:
    """None for a bad signature, an expired token, another token type (a session), or a missing or deactivated asset (AC4)."""
    try:
        claims = decode_token(token)
        asset_id = UUID(str(claims.get("sub"))) if claims.get("type") == LINK_TYPE else None
    except (jwt.PyJWTError, ValueError):
        return None
    asset = await db.get(TelAsset, asset_id) if asset_id else None
    return asset if asset and asset.active else None


# --- stored PDFs ----------------------------------------------------------------------------------------------------------------
async def read_pdf(file: UploadFile) -> tuple[bytes, str]:
    """The bytes decide (never the name or the client's Content-Type). Returns (bytes, display file name)."""
    data = await file.read(settings.max_upload_bytes + 1)
    if not data:
        raise HTTPException(422, "The file is empty")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"The file must be at most {max(1, settings.max_upload_bytes // (1024 * 1024))} MB")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(422, "Upload a PDF file")
    name = Path(file.filename or "").name.strip()[:255] or "brochure.pdf"
    return data, name


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def store(data: bytes) -> str:
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(key, data, PDF)
    except Exception:
        logger.exception("tel_asset_store_failed", extra={"extra_fields": {"key_digest": _digest(key)}})
        raise HTTPException(500, "Could not store the file; please try again") from None
    return key


def discard(key: str) -> None:
    """Delete an object stored for a write that did not commit; a failure leaves an orphan, logged by digest."""
    try:
        storage.delete(key)
    except Exception:
        logger.warning("tel_asset_orphaned", extra={"extra_fields": {"key_digest": _digest(key)}})


def read_object(asset: TelAsset) -> bytes | None:
    try:
        return storage.read_bytes(asset.storage_key)
    except Exception:
        logger.warning("tel_asset_unreadable", extra={"extra_fields": {"asset_id": str(asset.id)}})
        return None


# --- shapes ---------------------------------------------------------------------------------------------------------------------
def product_ref(product: TelProduct | None) -> dict | None:
    return {"id": product.id, "name": product.name, "group": product.product_group, "active": product.active} if product else None


def script_out(script: TelScript, product: TelProduct) -> dict:
    return {"id": script.id, "product": product_ref(product), "name": script.name, "steps": script.steps, "active": script.active}


def template_out(template: TelMessageTemplate, product: TelProduct | None, asset: TelAsset | None) -> dict:
    return {
        "id": template.id,
        "channel": template.channel,
        "kind": template.kind,
        "name": template.name,
        "product": product_ref(product),
        "asset": {"id": asset.id, "name": asset.name, "active": asset.active} if asset else None,
        "subject": template.subject,
        "body": template.body,
        "active": template.active,
    }


def asset_out(asset: TelAsset, product: TelProduct | None) -> dict:
    return {
        "id": asset.id,
        "name": asset.name,
        "kind": asset.kind,
        "product": product_ref(product),
        "file_name": asset.file_name,
        "size_bytes": asset.size_bytes,
        "active": asset.active,
        "uploaded_at": asset.created_at,
    }
