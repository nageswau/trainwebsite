"""bdm-005 (DEC-SCOPE-074, spec §6.2): MoU rules, history, audit and output.

Functions only; nothing here commits -- the route owns the transaction (bdm-002's rule). Every write runs on the organization row
locked by `bdm_organizations.load_scoped(lock=True)` and then the current MoU row (the lock order of spec §6.5). Audit metadata and
logs carry ids, status keys and field names only, never the notes, reference, file name or storage key (spec §6.6)."""

import hashlib
import logging
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bdm_stages import MOU_SIGNED_STAGE
from app.models import BDM_MOU_EXPIRING, BDM_MOU_STATUS_LABELS, AuditLog, BdmMou, BdmMouEvent, BdmOrganization, User
from app.services import bdm_organizations as org_svc
from app.services import bdm_pipeline
from app.services.agent_orgs import retry_after
from app.services.bdm import person_ref
from app.services.bdm_pipeline import LOST_CONFLICT, _invalid
from app.services.storage import storage

IST = ZoneInfo("Asia/Kolkata")  # M2: "today" is the India calendar date (as bdm_appointments.IST)
FIELDS = ("proposal_sent_on", "signed_on", "valid_from", "valid_until", "reference", "notes")
RENEWABLE = ("expired", "rejected")  # M6
NO_MOU = "No MoU yet"
MOU_EXISTS = {"message": "This organization already has an MoU in progress", "code": "mou_exists"}
MOU_EXPIRED = {"message": "This MoU has expired. Start a renewal.", "code": "mou_expired"}  # M9
SAME_STATUS = "The MoU is already at this status"
SIGNED_ON_REQUIRED = "Add the signed date"
WINDOW_REQUIRED = "Add the validity window"
WINDOW_ORDER = "Valid-until can't be before valid-from"
SIGN_NOTE = "Advanced by MoU signed"
NOT_FOUND = "MoU not found"
NO_DOCUMENT = "No document on file"
STORAGE_PREFIX = "bdm-mous"
UPLOAD_ACTION = "bdm_mou.document_uploaded"
UPLOAD_LIMIT = 20  # M8: per user per rolling hour
UPLOAD_WINDOW = timedelta(hours=1)
THROTTLED = "Too many uploads. Try again later."

logger = logging.getLogger("app.bdm")


def today() -> date:
    return datetime.now(IST).date()


def effective_status(mou: BdmMou, on: date) -> str:
    """M2 / M7: a signed or active MoU whose `valid_until` is before `on` reads Expired; `expired` is never stored."""
    if mou.status in BDM_MOU_EXPIRING and mou.valid_until is not None and mou.valid_until < on:
        return "expired"
    return mou.status


def effective_status_sql(on: date):
    """`effective_status` as SQL, so the list filter and the detail always agree (AC3)."""
    expired = and_(BdmMou.status.in_(BDM_MOU_EXPIRING), BdmMou.valid_until.is_not(None), BdmMou.valid_until < on)
    return case((expired, "expired"), else_=BdmMou.status)


def label(status: str) -> str:
    return BDM_MOU_STATUS_LABELS[status]


def apply_defaults(state: dict, on: date) -> None:
    """Proposal Sent without a date is dated today (spec §6.1); an existing date is kept."""
    if state["status"] == "proposal_sent" and state["proposal_sent_on"] is None:
        state["proposal_sent_on"] = on


def check_rules(state: dict) -> None:
    """M2 / AC2 on the merged state (stored values + the request), so clearing a required date alone is refused too."""
    if state["status"] in BDM_MOU_EXPIRING and state["signed_on"] is None:
        raise _invalid("signed_on", SIGNED_ON_REQUIRED, None)
    if state["status"] == "active":
        for field in ("valid_from", "valid_until"):
            if state[field] is None:
                raise _invalid(field, WINDOW_REQUIRED, None)
    if state["valid_from"] and state["valid_until"] and state["valid_until"] < state["valid_from"]:
        raise _invalid("valid_until", WINDOW_ORDER, state["valid_until"].isoformat())


def stored_state(mou: BdmMou) -> dict:
    return {"status": mou.status, **{f: getattr(mou, f) for f in FIELDS}}


def check_status_change(before: str, status: str, from_status: str | None) -> None:
    """A status change from the form (spec §6.4 step 5): stale `from_status` 409, Expired 409 (M9), the same status 422."""
    if from_status != before:
        raise HTTPException(409, {"message": f"This MoU moved to {label(before)} meanwhile", "code": "mou_status_changed", "current_status": before})
    if before == "expired":
        raise HTTPException(409, MOU_EXPIRED)
    if status == before:
        raise _invalid("status", SAME_STATUS, status)


async def load_current(db: AsyncSession, org: BdmOrganization, *, lock: bool = False) -> BdmMou | None:
    stmt = select(BdmMou).where(BdmMou.organization_id == org.id, BdmMou.is_current.is_(True))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(stmt)


async def load_scoped_mou(db: AsyncSession, user: User, mou_id: UUID) -> tuple[BdmMou, BdmOrganization]:
    """Any MoU (current or previous) through its organization's read scope; unknown and out of scope give the same 404 (§7 IDOR)."""
    stmt = select(BdmMou, BdmOrganization).join(BdmOrganization, BdmOrganization.id == BdmMou.organization_id)
    row = (await db.execute(stmt.where(BdmMou.id == mou_id, *await org_svc.caller_scope(db, user)))).first()
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row[0], row[1]


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def store(data: bytes, content_type: str) -> str:
    """M4: a server-generated key; the client never names a path. A storage failure is a 500, logged by key digest (never the key)."""
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(key, data, content_type)
    except Exception:
        logger.exception("bdm_mou_document_store_failed", extra={"extra_fields": {"key_digest": _digest(key)}})
        raise
    return key


def discard(key: str) -> None:
    """Delete an object stored for a write that did not commit; only this module's keys. A failure leaves a logged orphan."""
    if not key.startswith(f"{STORAGE_PREFIX}/"):
        logger.error("bdm_mou_document_discard_refused", extra={"extra_fields": {"key_digest": _digest(key)}})
        return
    try:
        storage.delete(key)
    except Exception:
        logger.warning("bdm_mou_document_orphaned", extra={"extra_fields": {"key_digest": _digest(key)}})


def read_document(mou: BdmMou) -> bytes:
    if mou.document_key is None:
        raise HTTPException(404, NO_DOCUMENT)
    try:
        return storage.read_bytes(mou.document_key)
    except FileNotFoundError:
        logger.warning("bdm_mou_document_missing", extra={"extra_fields": {"mou_id": str(mou.id), "key_digest": _digest(mou.document_key)}})
        raise HTTPException(404, NO_DOCUMENT) from None


async def upload_wait(db: AsyncSession, user: User) -> int:
    """M8: seconds before the caller may upload again (their audit rows in the last hour; shared by every API instance)."""
    now = datetime.now(UTC)
    stmt = (
        select(AuditLog.created_at)
        .where(AuditLog.user_id == user.id, AuditLog.action == UPLOAD_ACTION, AuditLog.created_at > now - UPLOAD_WINDOW)
        .order_by(AuditLog.created_at.desc())
        .limit(UPLOAD_LIMIT)
    )
    return retry_after(list((await db.scalars(stmt)).all()), UPLOAD_LIMIT, now, UPLOAD_WINDOW)


def can_write(user: User, org: BdmOrganization) -> bool:
    return org_svc.permissions(user, org)["can_edit"] and org.lost_at is None


def writable(user: User, org: BdmOrganization, route: str) -> None:
    """M3 / M5: 403 for the wrong person, 409 archived (bdm-002's require), then 409 Lost (bdm-004's conflict)."""
    org_svc.require(user, org, "can_edit", route)
    if org.lost_at is not None:
        raise HTTPException(409, LOST_CONFLICT)


def record(db: AsyncSession, user: User, mou: BdmMou, kind: str, from_status: str | None, to_status: str, changed: list[str], document_key: str | None = None) -> None:
    db.add(BdmMouEvent(mou_id=mou.id, actor_user_id=user.id, kind=kind, from_status=from_status, to_status=to_status, changed=changed, document_key=document_key))


def audit(db: AsyncSession, user: User, action: str, mou: BdmMou, metadata: dict) -> None:
    """Same transaction as the write (fail closed); ids, status keys and field names only."""
    db.add(AuditLog(user_id=user.id, action=f"bdm_mou.{action}", entity_type="bdm_mou", entity_id=str(mou.id), metadata_json={"org_id": str(mou.organization_id), **metadata}))


def log(event: str, user: User, mou: BdmMou, **extra) -> None:
    org_svc.log(event, user, mou.organization_id, mou_id=str(mou.id), **extra)


def advance_on_sign(db: AsyncSession, user: User, org: BdmOrganization) -> str | None:
    """D28 inside the MoU write's transaction, on the already-locked organization; bdm-004's audit row marked `source: mou`."""
    target = MOU_SIGNED_STAGE[org.bdm_type]
    from_stage = bdm_pipeline.advance_to(db, user, org, target, SIGN_NOTE)
    if from_stage is not None:
        org_svc.audit(db, user, "stage_changed", org.id, {"from": from_stage, "to": target, "backward": False, "note": True, "source": "mou"})
    return from_stage


def log_advance(user: User, org: BdmOrganization, from_stage: str | None) -> None:
    if from_stage is not None:
        org_svc.log("bdm_org_stage_changed", user, org.id, from_stage=from_stage, to_stage=org.pipeline_stage, backward=False, source="mou")


def _pipeline_on_sign(org: BdmOrganization) -> dict | None:
    target = MOU_SIGNED_STAGE[org.bdm_type]
    return {"key": target, "label": bdm_pipeline.label_of(org.bdm_type, target)} if bdm_pipeline.behind(org, target) else None


def _document(mou: BdmMou) -> dict | None:
    if mou.document_key is None:
        return None
    return {"name": mou.document_name, "content_type": mou.document_content_type, "uploaded_at": mou.document_uploaded_at}


def row_out(mou: BdmMou, org: BdmOrganization, assigned: User, status: str) -> dict:
    """The list row (BdmMouRow): no notes, no document details."""
    return {
        "id": mou.id,
        "organization": {"id": org.id, "code": org.code, "name": org.name, "bdm_type": org.bdm_type},
        "assigned_bdm": person_ref(assigned),
        "status": status,
        "status_label": label(status),
        "status_changed_at": mou.status_changed_at,
        "signed_on": mou.signed_on,
        "valid_until": mou.valid_until,
        "reference": mou.reference,
        "has_document": mou.document_key is not None,
        "is_current": mou.is_current,
    }


async def mou_out(db: AsyncSession, user: User, org: BdmOrganization, mou: BdmMou, on: date) -> dict:
    status = effective_status(mou, on)
    editable = can_write(user, org) and mou.is_current
    assigned = await db.get_one(User, org.assigned_bdm_user_id)  # RESTRICT foreign keys: both rows always exist
    creator = await db.get_one(User, mou.created_by_user_id)
    return {
        **row_out(mou, org, assigned, status),
        "proposal_sent_on": mou.proposal_sent_on,
        "valid_from": mou.valid_from,
        "notes": mou.notes,
        "document": _document(mou),
        "expired_on": mou.valid_until + timedelta(days=1) if status == "expired" and mou.valid_until else None,
        "created_by": person_ref(creator),
        "permissions": {"can_edit": editable, "can_upload": editable, "can_renew": editable and status in RENEWABLE},
        "pipeline_on_sign": _pipeline_on_sign(org),
        "created_at": mou.created_at,
        "updated_at": mou.updated_at,
    }


async def org_mou_out(db: AsyncSession, user: User, org: BdmOrganization) -> dict:
    on = today()
    current = await load_current(db, org)
    renewable = current is None or effective_status(current, on) in RENEWABLE
    return {"current": await mou_out(db, user, org, current, on) if current else None, "can_start": can_write(user, org) and renewable}


async def list_page(db: AsyncSession, user: User, *, on: date, status: str | None, bdm_type: str | None, organization: UUID | None, current: bool, limit: int, offset: int) -> dict:
    effective = effective_status_sql(on)
    where = [*await org_svc.caller_scope(db, user), BdmMou.is_current.is_(current)]
    if status is not None:
        where.append(effective == status)
    if bdm_type is not None:
        where.append(BdmOrganization.bdm_type == bdm_type)
    if organization is not None:
        where.append(BdmMou.organization_id == organization)
    base = select(BdmMou, BdmOrganization, User).join(BdmOrganization, BdmOrganization.id == BdmMou.organization_id)
    base = base.join(User, User.id == BdmOrganization.assigned_bdm_user_id).where(*where)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(base.order_by(BdmMou.status_changed_at.desc(), BdmMou.id).limit(limit).offset(offset))).all()
    items = [row_out(mou, org, assigned, effective_status(mou, on)) for mou, org, assigned in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def history_page(db: AsyncSession, mou: BdmMou, limit: int, offset: int) -> dict:
    """Newest first (bdm-004's stage history order); the replaced document's key is never returned."""
    where = BdmMouEvent.mou_id == mou.id
    total = await db.scalar(select(func.count()).select_from(BdmMouEvent).where(where))
    stmt = select(BdmMouEvent, User).join(User, User.id == BdmMouEvent.actor_user_id).where(where)
    rows = (await db.execute(stmt.order_by(BdmMouEvent.position.desc()).limit(limit).offset(offset))).all()
    items = [
        {
            "id": e.id,
            "kind": e.kind,
            "from_status": e.from_status,
            "from_label": label(e.from_status) if e.from_status else None,
            "to_status": e.to_status,
            "to_label": label(e.to_status),
            "changed": e.changed,
            "actor": person_ref(actor),
            "created_at": e.created_at,
        }
        for e, actor in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def now() -> datetime:
    return datetime.now(UTC)
