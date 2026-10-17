"""AGN-024 (DEC-SCOPE-224): KYC documents at agent self-registration -- PAN card, Aadhaar card and business licence (K1).

Numbers (K2): the full PAN and licence number; ONLY the last 4 Aadhaar digits. Numbers never reach logs, audit metadata, notification
bodies or error messages. Files (K8): PDF/JPEG/PNG decided from the bytes, metadata stripped, at most 5 MB, stored under `agent-kyc/`
and served only by the admin streaming route. The approval gate (K3) is `assert_complete`, called from `agent_orgs.set_org_status`.
"""

import hashlib
import logging
import re
from collections.abc import Mapping
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KYC_DOC_TYPES, AgentOrg, AgentOrgKycDocument, AgentOrgMember, Notification, User
from app.notifications.dispatch import queue_deliveries
from app.services.agent_documents import read_upload
from app.services.storage import storage

logger = logging.getLogger(__name__)

DOC_TYPES = KYC_DOC_TYPES
LABELS = {"pan": "PAN card", "aadhaar": "Aadhaar card", "business_license": "Business licence"}
NUMBER_FIELDS = {"pan": "pan_number", "aadhaar": "aadhaar_last4", "business_license": "license_number"}
FILE_FIELDS = {"pan": "pan_file", "aadhaar": "aadhaar_file", "business_license": "license_file"}
MAX_BYTES = 5 * 1024 * 1024
STORAGE_PREFIX = "agent-kyc"
STATUS_URL = "/overseas/agent/registration-status"
DASHBOARD_URL = "/overseas/agent/dashboard"
REUPLOAD_LIMIT = 20  # per agency per rolling THROTTLE_WINDOW (24 h), counted from audit rows (the AGN-009 pattern)
CHANNELS = ["email"]
EXTENSIONS = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}

REQUIRED = "PAN card, Aadhaar card and business licence are required"
NOT_VERIFIED = "All verification documents must be verified before approval"
NOT_PENDING_REVIEW = "Documents can only be reviewed while the organisation is pending"
NOT_PENDING_UPLOAD = "Documents can only be changed while your registration is pending"
ONLY_REJECTED = "Only a rejected document can be replaced"
REUPLOAD_THROTTLED = "Too many re-uploads today -- try again later"

_PATTERNS = {
    "pan": re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$"),
    "aadhaar": re.compile(r"^[0-9]{4}$"),
    "business_license": re.compile(r"^[A-Za-z0-9/\-. ]{3,64}$"),
}
_INVALID = {
    "pan": "PAN number must look like ABCDE1234F",
    "aadhaar": "Enter only the last 4 digits of the Aadhaar number",
    "business_license": "Business licence number must be 3-64 letters, digits, spaces or / - .",
}


def clean_number(doc_type: str, raw: str | None) -> str:
    value = (raw or "").strip()
    if doc_type == "pan":
        value = value.upper()
    if not _PATTERNS[doc_type].fullmatch(value):
        raise HTTPException(422, _INVALID[doc_type])
    return value


def clean_numbers(fields: Mapping[str, object]) -> dict[str, str]:
    raw = {t: fields.get(NUMBER_FIELDS[t]) for t in DOC_TYPES}
    if any(not isinstance(v, str) or not v.strip() for v in raw.values()):
        raise HTTPException(422, REQUIRED)
    return {t: clean_number(t, raw[t]) for t in DOC_TYPES}


def require_files(files: Mapping[str, object]) -> dict[str, UploadFile]:
    chosen = {t: files.get(FILE_FIELDS[t]) for t in DOC_TYPES}
    if any(f is None or isinstance(f, str) or not getattr(f, "filename", None) for f in chosen.values()):
        raise HTTPException(422, REQUIRED)
    return chosen  # type: ignore[return-value]


async def read_kyc_file(doc_type: str, file) -> tuple[bytes, str, str | None]:
    try:
        return await read_upload(file, max_bytes=MAX_BYTES)
    except HTTPException as exc:
        raise HTTPException(exc.status_code, f"{LABELS[doc_type]}: {exc.detail}") from None


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def store(data: bytes, content_type: str) -> str:
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(key, data, content_type)
    except Exception:
        logger.exception("agent_kyc_store_failed", extra={"extra_fields": {"key_digest": _digest(key)}})
        raise HTTPException(500, "Could not store the file; please try again") from None
    return key


def discard(key: str) -> None:
    """Delete an object this module stored; anything else is refused. A failure leaves an orphan, logged by key digest."""
    if not key.startswith(f"{STORAGE_PREFIX}/"):
        logger.error("agent_kyc_discard_refused", extra={"extra_fields": {"key_digest": _digest(key)}})
        return
    try:
        storage.delete(key)
    except Exception:
        logger.warning("agent_kyc_orphaned", extra={"extra_fields": {"key_digest": _digest(key)}})


def mask(doc_type: str, number: str) -> str:
    if doc_type == "pan":
        return f"{number[:5]}****{number[-1:]}"
    if doc_type == "aadhaar":
        return f"XXXX XXXX {number}"
    return number


def download_name(doc: AgentOrgKycDocument) -> str:
    return f"{doc.doc_type}{EXTENSIONS.get(doc.content_type, '')}"  # never the client's file name (header safety)


async def documents(db: AsyncSession, org_id) -> list[AgentOrgKycDocument]:
    rows = (await db.scalars(select(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org_id))).all()
    return sorted(rows, key=lambda d: DOC_TYPES.index(d.doc_type))


def _common(doc: AgentOrgKycDocument) -> dict:
    return {
        "id": doc.id, "doc_type": doc.doc_type, "label": LABELS[doc.doc_type], "status": doc.status, "rejection_reason": doc.rejection_reason,
        "original_filename": doc.original_filename, "content_type": doc.content_type, "file_size": doc.file_size, "updated_at": doc.updated_at,
    }  # fmt: skip


def admin_view(doc: AgentOrgKycDocument) -> dict:
    return _common(doc) | {"doc_number": doc.doc_number, "reviewed_at": doc.reviewed_at}


def agent_view(doc: AgentOrgKycDocument) -> dict:
    return _common(doc) | {"doc_number_display": mask(doc.doc_type, doc.doc_number)}


async def summaries(db: AsyncSession, org_ids: list) -> dict:
    out = {oid: {"verified": 0, "rejected": 0, "pending": 0} for oid in org_ids}
    if not org_ids:
        return out
    rows = await db.execute(
        select(AgentOrgKycDocument.org_id, AgentOrgKycDocument.status, func.count())
        .where(AgentOrgKycDocument.org_id.in_(org_ids))
        .group_by(AgentOrgKycDocument.org_id, AgentOrgKycDocument.status)
    )
    for org_id, status, count in rows.all():
        out[org_id][status] = count
    return out


async def assert_complete(db: AsyncSession, org: AgentOrg) -> None:
    """K3/K4: a kyc_required org needs all three documents verified; legacy orgs pass untouched."""
    if not org.kyc_required:
        return
    verified = await db.scalar(
        select(func.count()).select_from(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org.id, AgentOrgKycDocument.status == "verified")
    )
    if (verified or 0) < len(DOC_TYPES):
        raise HTTPException(409, NOT_VERIFIED)


async def _active_masters(db: AsyncSession, org_id) -> list[User]:
    rows = await db.scalars(
        select(User)
        .join(AgentOrgMember, AgentOrgMember.user_id == User.id)
        .where(AgentOrgMember.org_id == org_id, AgentOrgMember.role == "master", AgentOrgMember.status == "active", User.active.is_(True))
        .order_by(AgentOrgMember.seq)
    )
    return list(rows)


async def _notify(db: AsyncSession, org_id, title: str, body: str, action_url: str) -> None:
    """No commit: the notice rides the caller's transaction, so a rolled-back action sends nothing (ENH-014 outbox)."""
    for user in await _active_masters(db, org_id):
        item = Notification(user_id=user.id, title=title, body=body, read=False, action_url=action_url)
        db.add(item)
        await queue_deliveries(db, item, user, channels=CHANNELS)


async def notify_rejected(db: AsyncSession, org_id, doc: AgentOrgKycDocument) -> None:
    body = f"Your {LABELS[doc.doc_type]} was rejected: {doc.rejection_reason} Upload a corrected file from your registration status page."
    await _notify(db, org_id, "Verification document rejected", body, STATUS_URL)


async def notify_approved(db: AsyncSession, org: AgentOrg) -> None:
    await _notify(db, org.id, "Agency approved", f"{org.name} has been approved. You can now use the EduSphere agent portal.", DASHBOARD_URL)
