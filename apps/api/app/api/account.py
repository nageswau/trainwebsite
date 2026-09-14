import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AuditLog, Certificate, ConsentRecord, DataSubjectRequest, Enrollment, Payment, User, UserRoleAssignment
from app.services.storage import storage

router = APIRouter(prefix="/account", tags=["account"])


def _out(item: DataSubjectRequest) -> dict:
    return {
        "id": item.id,
        "type": item.type,
        "status": item.status,
        "created_at": item.created_at,
        "fulfilled_at": item.fulfilled_at,
        "rejection_reason": item.rejection_reason,
    }


async def _build_export(db: AsyncSession, user: User) -> dict:
    assignments = (await db.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id))).all()
    enrollments = (await db.scalars(select(Enrollment).where(Enrollment.student_id == user.id))).all()
    certificates = (await db.scalars(select(Certificate).where(Certificate.student_id == user.id))).all()
    consents = (await db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user.id))).all()
    return {
        "profile": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
            "division": user.division,
            "role": user.role,
            "profile": user.profile,
            "created_at": user.created_at.isoformat(),
        },
        "role_assignments": [{"division": a.division, "role": a.role, "is_active": a.is_active} for a in assignments],
        "enrollments": [{"id": str(e.id), "batch_id": str(e.batch_id), "status": e.status} for e in enrollments],
        "certificates": [{"id": str(c.id), "certificate_no": c.certificate_no, "status": c.status} for c in certificates],
        "consents": [{"agreement_id": str(c.agreement_id), "version": c.version, "accepted_at": c.created_at.isoformat()} for c in consents],
    }


def _retention_hold_reason(consents: list, payments: list) -> str | None:
    # DATA_MODEL.md #8: "No hard delete of financial/audit/consent records without an
    # explicit, confirmed retention rule" -- the one concrete, evidence-backed hold rule
    # that exists today. Exact retention periods remain open (PRD_OPEN_ITEMS.md item 15);
    # this checks presence, not a numeric period, and is never invented beyond that.
    if payments:
        return "An active payment record exists for this account and must be retained for financial/legal purposes."
    if consents:
        return "A signed enrolment agreement exists for this account and must be retained as legal evidence (DATA_MODEL.md #3.4)."
    return None


@router.post("/data-requests", status_code=201)
async def create_data_request(
    payload: dict,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    request_type = payload.get("type")
    if request_type not in {"export", "delete"}:
        raise HTTPException(422, "type must be 'export' or 'delete'")
    if not idempotency_key:
        raise HTTPException(422, "Idempotency-Key header is required")

    existing = await db.scalar(
        select(DataSubjectRequest).where(DataSubjectRequest.requesting_user_id == user.id, DataSubjectRequest.idempotency_key == idempotency_key)
    )
    if existing:
        if existing.type != request_type:
            raise HTTPException(409, "This idempotency key was already used for a different request type")
        return _out(existing)

    item = DataSubjectRequest(requesting_user_id=user.id, type=request_type, status="received", idempotency_key=idempotency_key)
    db.add(item)
    await db.flush()

    if request_type == "export":
        export = await _build_export(db, user)
        key = f"gdpr-exports/{item.id}.json"
        storage.write_bytes(key, json.dumps(export, default=str).encode("utf-8"), "application/json")
        item.status = "fulfilled"
        item.fulfilled_at = datetime.now(UTC)
        item.export_key = key
        db.add(AuditLog(user_id=user.id, action="gdpr.export.fulfil", entity_type="data_subject_request", entity_id=str(item.id), metadata_json={}))
    else:
        consents = (await db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user.id))).all()
        payments = (await db.scalars(select(Payment).where(Payment.user_id == user.id))).all()
        hold = _retention_hold_reason(consents, payments)
        if hold:
            item.status = "rejected"
            item.rejection_reason = hold
        else:
            item.status = "in_progress"
        db.add(AuditLog(user_id=user.id, action="gdpr.delete.request", entity_type="data_subject_request", entity_id=str(item.id), metadata_json={"status": item.status}))

    await db.commit()
    await db.refresh(item)
    return _out(item)


@router.get("/data-requests/{request_id}")
async def get_data_request(request_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(DataSubjectRequest, request_id)
    if not item or item.requesting_user_id != user.id:
        raise HTTPException(404, "Request not found")
    return _out(item)


@router.get("/data-requests/{request_id}/export")
async def download_data_request_export(request_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(DataSubjectRequest, request_id)
    if not item or item.requesting_user_id != user.id:
        raise HTTPException(404, "Request not found")
    if item.type != "export" or item.status != "fulfilled" or not item.export_key:
        raise HTTPException(409, "Export is not ready")
    return {"url": storage.presign_download(item.export_key), "expires_in": 900 if storage.bucket else None}
