"""nehn-032 -- the Founder and Coordinator certificate signatures (DEC-SCOPE-300; spec
docs/superpowers/specs/2026-10-27-nehn-032-certificate-signatures-design.md; API_CONTRACT §12GX; RBAC_MATRIX §2.211). Every route needs
`certificates.manage` (super_admin until granted). Images are private: stored under a server-generated key, streamed only here, never
presigned, never in a response body. A new image is a new version; issued certificates keep the version they snapshot."""

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, CertificateSignatory, User
from app.schemas import CertificateSignatoryUpdate
from app.services import certificates, upload_policy
from app.services.image_metadata import PNG, InvalidImage, strip_metadata
from app.services.storage import storage

router = APIRouter(prefix="/admin", tags=["certificate-signatories"])
logger = get_logger("app.certificates.signatories")

CAN_MANAGE = require_permission("certificates", "manage", "You do not have permission to manage certificate signatures")
PRIVATE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
NAME_LIMIT = 120


def _out(row: CertificateSignatory) -> dict:
    return {
        "id": row.id,
        "role": row.role,
        "display_name": row.display_name,
        "designation": row.designation,
        "active": row.active_to is None,
        "active_from": row.active_from,
        "active_to": row.active_to,
    }


def _text(value: str, field: str) -> str:
    value = value.strip()
    if not value or len(value) > NAME_LIMIT:
        raise HTTPException(422, f"{field} must be 1-{NAME_LIMIT} characters")
    return value


def _audit(db: AsyncSession, user: User, action: str, row: CertificateSignatory) -> None:
    db.add(AuditLog(user_id=user.id, action=action, entity_type="certificate_signatory", entity_id=str(row.id), metadata_json={"role": row.role}))


@router.get("/certificate-signatories")
async def list_signatories(user: User = Depends(CAN_MANAGE), db: AsyncSession = Depends(get_db)):
    """Every version, the active one first in each slot, newest first (at most 100)."""
    rows = (
        await db.scalars(select(CertificateSignatory).order_by(CertificateSignatory.role.desc(), CertificateSignatory.active_to.is_not(None), CertificateSignatory.active_from.desc()).limit(100))
    ).all()
    return {"items": [_out(row) for row in rows]}


@router.post("/certificate-signatories", status_code=201)
async def upload_signatory(
    role: Literal["founder", "coordinator"] = Form(...),
    display_name: str = Form(..., max_length=NAME_LIMIT * 2),
    designation: str = Form(..., max_length=NAME_LIMIT * 2),
    file: UploadFile = File(...),
    user: User = Depends(CAN_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    display_name, designation = _text(display_name, "Name"), _text(designation, "Designation")
    try:
        upload_policy.check_upload("signature", file)  # nehn-003: PNG, at most 1 MB, content type and magic bytes
    except upload_policy.PolicyError as refused:
        raise HTTPException(refused.status_code, refused.detail) from None
    data = await file.read()
    certificates.check_signature_image(data)
    try:
        data = strip_metadata(data, PNG)  # text chunks and timestamps are not kept
    except InvalidImage as error:
        raise HTTPException(422, "The signature is not a readable PNG image") from error

    key = f"signatures/{uuid4().hex}.png"
    storage.write_bytes(key, data, PNG)
    try:
        # S2: the slot's active row is locked and closed before the new one goes in; two first uploads racing meet the partial unique index.
        previous = await db.scalar(select(CertificateSignatory).where(CertificateSignatory.role == role, CertificateSignatory.active_to.is_(None)).with_for_update())
        if previous:
            previous.active_to = datetime.now(UTC)
            await db.flush()
        row = CertificateSignatory(role=role, display_name=display_name, designation=designation, image_key=key, created_by_id=user.id)
        db.add(row)
        await db.flush()
        _audit(db, user, "certificate_signatory.upload", row)
        await db.commit()
    except Exception as error:
        await db.rollback()
        storage.delete(key)  # nothing points at the new image
        if isinstance(error, IntegrityError):
            raise HTTPException(409, "The signature was changed at the same time; reload and try again") from None
        raise
    await db.refresh(row)
    logger.info("certificate_signatory.upload", extra={"extra_fields": {"actor_id": str(user.id), "role": role, "signatory_id": str(row.id)}})
    return _out(row)


@router.patch("/certificate-signatories/{signatory_id}")
async def update_signatory(signatory_id: UUID, payload: CertificateSignatoryUpdate, user: User = Depends(CAN_MANAGE), db: AsyncSession = Depends(get_db)):
    """S3: the active version's name and designation, in place (issued PDFs and their snapshots are unaffected)."""
    row = await db.scalar(select(CertificateSignatory).where(CertificateSignatory.id == signatory_id).with_for_update())
    if not row:
        raise HTTPException(404, "Signature not found")
    if row.active_to is not None:
        raise HTTPException(409, "This signature version is no longer active")
    if payload.display_name is not None:
        row.display_name = _text(payload.display_name, "Name")
    if payload.designation is not None:
        row.designation = _text(payload.designation, "Designation")
    _audit(db, user, "certificate_signatory.update", row)
    await db.commit()
    await db.refresh(row)
    return _out(row)


@router.get("/certificate-signatories/{signatory_id}/image")
async def signatory_image(signatory_id: UUID, user: User = Depends(CAN_MANAGE), db: AsyncSession = Depends(get_db)):
    row = await db.get(CertificateSignatory, signatory_id)
    if not row:
        raise HTTPException(404, "Signature not found")
    try:
        data = storage.read_bytes(row.image_key)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "The signature image is missing") from None
    return Response(data, media_type=PNG, headers=PRIVATE)


@router.get("/certificates/preview")
async def preview_certificate(user: User = Depends(CAN_MANAGE), db: AsyncSession = Depends(get_db)):
    """S9: the layout with the current signatures and deliberately long sample text; nothing is stored."""
    signatories = await certificates.active_signatories(db)
    certificates.require_signatories(signatories)
    pdf = certificates.render_certificate_pdf(
        certificate_no="EDU-CERT-PREVIEW",
        student_name="Aaradhya Venkatasubramanian Krishnamurthy",
        program_title="Full Stack Java Development with Spring Boot and React",
        issued_on=date.today(),
        verification_code="preview-only",
        signatories=signatories,
    )
    return Response(pdf, media_type="application/pdf", headers={**PRIVATE, "Content-Disposition": 'inline; filename="certificate-preview.pdf"'})
