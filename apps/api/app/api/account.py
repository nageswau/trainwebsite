import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AuditLog, Certificate, ConsentRecord, DataSubjectRequest, Enrollment, NotificationPreference, Payment, User, UserRoleAssignment
from app.notifications.phone import normalise_phone
from app.schemas import NotificationPreferencesIn, NotificationPreferencesOut, PlacementPoolOptIn
from app.services import placement_pool
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
    pref = await db.get(NotificationPreference, user.id)
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
        "notification_preferences": {
            "whatsapp": bool(pref and pref.whatsapp_opt_in),
            "sms": bool(pref and pref.sms_opt_in),
            "whatsapp_opted_in_at": pref.whatsapp_opted_in_at.isoformat() if pref and pref.whatsapp_opted_in_at else None,
            "sms_opted_in_at": pref.sms_opted_in_at.isoformat() if pref and pref.sms_opted_in_at else None,
        },
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


# --- ENH-014: notification channel preferences (spec §5.1-5.2) ------------------------------------------------------
# Self-only: the user always comes from the session and there is no id in the path, so no admin or other user can set
# anyone's consent (D4). PUT + JSON under the SameSite=Lax session cookie is not sendable by a cross-site form.
CONSENT_TEXT_VERSION = "enh014-v1"


def _preferences_out(pref: NotificationPreference | None, user: User) -> NotificationPreferencesOut:
    return NotificationPreferencesOut(whatsapp=bool(pref and pref.whatsapp_opt_in), sms=bool(pref and pref.sms_opt_in), phone_valid=normalise_phone(user.phone) is not None)


@router.get("/notification-preferences", response_model=NotificationPreferencesOut)
async def get_notification_preferences(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return _preferences_out(await db.get(NotificationPreference, user.id), user)


@router.put("/notification-preferences", response_model=NotificationPreferencesOut)
async def put_notification_preferences(payload: NotificationPreferencesIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    current = await db.get(NotificationPreference, user.id)
    before = {"whatsapp": bool(current and current.whatsapp_opt_in), "sms": bool(current and current.sms_opt_in)}
    after = {"whatsapp": payload.whatsapp, "sms": payload.sms}
    # Only a false->true change needs a number: a user whose phone was cleared can still turn channels off.
    if any(after[c] and not before[c] for c in after) and normalise_phone(user.phone) is None:
        raise HTTPException(422, "Add a valid mobile number to your profile first")
    now = datetime.now(UTC)

    def since(channel: str, previous: datetime | None) -> datetime | None:
        if not after[channel]:
            return None
        return previous if before[channel] and previous else now

    values = {
        "whatsapp_opt_in": after["whatsapp"],
        "sms_opt_in": after["sms"],
        "whatsapp_opted_in_at": since("whatsapp", current.whatsapp_opted_in_at if current else None),
        "sms_opted_in_at": since("sms", current.sms_opted_in_at if current else None),
    }
    await db.execute(insert(NotificationPreference).values(user_id=user.id, **values).on_conflict_do_update(index_elements=[NotificationPreference.user_id], set_={**values, "updated_at": now}))
    if after != before:
        db.add(AuditLog(user_id=user.id, action="notification_preference.update", entity_type="user", entity_id=str(user.id), metadata_json={"before": before, "after": after, "consent_text": CONSENT_TEXT_VERSION}))
    await db.commit()
    return _preferences_out(await db.get(NotificationPreference, user.id, populate_existing=True), user)


# --- rec-010 (DEC-SCOPE-138, API §12BF): the student's own placement-pool consent. No user id anywhere: only ever the caller. ---------
def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/placement-pool")
async def get_placement_pool(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    placement_pool.require_student(user)
    return await placement_pool.state(db, user)


@router.post("/placement-pool/opt-in")
async def opt_in_placement_pool(payload: PlacementPoolOptIn, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    placement_pool.require_student(user)
    await placement_pool.opt_in(db, user, payload.consent_version, _client_ip(request))
    await db.commit()
    return await placement_pool.state(db, user)


@router.post("/placement-pool/opt-out")
async def opt_out_placement_pool(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    placement_pool.require_student(user)
    await placement_pool.opt_out(db, user, _client_ip(request))
    await db.commit()
    return await placement_pool.state(db, user)


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
