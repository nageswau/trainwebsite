"""bdm-005 (DEC-SCOPE-074, spec §6.2): MoU rules, history, audit and output.

Functions only; nothing here commits -- the route owns the transaction (bdm-002's rule). Every write runs on the organization row
locked by `bdm_organizations.load_scoped(lock=True)` and then the current MoU row (the lock order of spec §6.5). Audit metadata and
logs carry ids, status keys and field names only, never the notes, reference, file name or storage key (spec §6.6)."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BDM_MOU_EXPIRING, BDM_MOU_STATUS_LABELS, AuditLog, BdmMou, BdmMouEvent, BdmOrganization, User
from app.services import bdm_organizations as org_svc
from app.services.bdm import person_ref
from app.services.bdm_pipeline import LOST_CONFLICT, _invalid

IST = ZoneInfo("Asia/Kolkata")  # M2: "today" is the India calendar date (as bdm_appointments.IST)
FIELDS = ("proposal_sent_on", "signed_on", "valid_from", "valid_until", "reference", "notes")
RENEWABLE = ("expired", "rejected")  # M6
NO_MOU = "No MoU yet"
MOU_EXISTS = {"message": "This organization already has an MoU in progress", "code": "mou_exists"}
SAME_STATUS = "The MoU is already at this status"
SIGNED_ON_REQUIRED = "Add the signed date"
WINDOW_REQUIRED = "Add the validity window"
WINDOW_ORDER = "Valid-until can't be before valid-from"


def today() -> date:
    return datetime.now(IST).date()


def effective_status(mou: BdmMou, on: date) -> str:
    return mou.status


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


def stale_status(current: str) -> HTTPException:
    return HTTPException(409, {"message": f"This MoU moved to {label(current)} meanwhile", "code": "mou_status_changed", "current_status": current})


async def load_current(db: AsyncSession, org: BdmOrganization, *, lock: bool = False) -> BdmMou | None:
    stmt = select(BdmMou).where(BdmMou.organization_id == org.id, BdmMou.is_current.is_(True))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(stmt)


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


def _document(mou: BdmMou) -> dict | None:
    if mou.document_key is None:
        return None
    return {"name": mou.document_name, "content_type": mou.document_content_type, "uploaded_at": mou.document_uploaded_at}


async def mou_out(db: AsyncSession, user: User, org: BdmOrganization, mou: BdmMou, on: date) -> dict:
    status = effective_status(mou, on)
    editable = can_write(user, org) and mou.is_current
    assigned = await db.get(User, org.assigned_bdm_user_id)
    creator = await db.get(User, mou.created_by_user_id)
    return {
        "id": mou.id,
        "organization": {"id": org.id, "code": org.code, "name": org.name, "bdm_type": org.bdm_type},
        "assigned_bdm": person_ref(assigned),
        "status": status,
        "status_label": label(status),
        "status_changed_at": mou.status_changed_at,
        **{f: getattr(mou, f) for f in FIELDS},
        "has_document": mou.document_key is not None,
        "is_current": mou.is_current,
        "document": _document(mou),
        "expired_on": None,
        "created_by": person_ref(creator),
        "permissions": {"can_edit": editable, "can_upload": editable, "can_renew": editable and status in RENEWABLE},
        "pipeline_on_sign": None,
        "created_at": mou.created_at,
        "updated_at": mou.updated_at,
    }


async def org_mou_out(db: AsyncSession, user: User, org: BdmOrganization) -> dict:
    on = today()
    current = await load_current(db, org)
    renewable = current is None or effective_status(current, on) in RENEWABLE
    return {"current": await mou_out(db, user, org, current, on) if current else None, "can_start": can_write(user, org) and renewable}


def now() -> datetime:
    return datetime.now(UTC)
