"""rec-030 (DEC-SCOPE-156, spec §1-§3): recruiter contracts -- rules, history, audit and output (the bdm-005 MoU pattern).

Functions only; nothing here commits -- the route owns the transaction. Every write runs on the company row locked by
`recruiter_companies.load_scoped(lock=True)` and then the current contract row. Audit metadata and logs carry ids, status keys and field
names only, never the terms, fee, file name or storage key."""

import hashlib
import logging
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RECRUITER_CONTRACT_EXPIRING, AuditLog, Company, RecruiterContract, RecruiterContractEvent, User
from app.services import permissions
from app.services import recruiter_companies as companies
from app.services.agent_orgs import retry_after
from app.services.bdm_pipeline import _invalid
from app.services.storage import storage

IST = ZoneInfo("Asia/Kolkata")  # CT2: "today" is the India calendar date (bdm-005's rule)
LABELS = {
    "discussion": "Discussion",
    "proposal_sent": "Proposal Sent",
    "negotiation": "Negotiation",
    "contract_sent": "Contract Sent",
    "signed": "Signed",
    "active": "Active",
    "expired": "Expired",
}
FIELDS = (
    "agreement_type", "start_date", "end_date", "fee_basis", "fee_value", "payment_terms", "replacement_policy", "direction", "confidentiality_terms",
    "guarantee_days",  # pob-025 (DEC-SCOPE-436 G1)
)  # fmt: skip
VENDOR_TERMS = ("direction", "confidentiality_terms")  # pob-010 V8: a vendor agreement's alone
TERMS = ("fee_basis", "fee_value", "payment_terms", "replacement_policy", "guarantee_days", *VENDOR_TERMS)  # pob-001 C5: behind `commercials.client`; pob-010 V9: `commercials.vendor` for a vendor agreement
CLIENT, VENDOR = "client", "vendor"
DOCUMENT_KINDS = ("contract", "mou")
RENEWABLE = ("signed", "active", "expired")  # CT7: a renewal follows a concluded contract
NO_CONTRACT = "No contract yet"
NOT_FOUND = "Contract not found"
NO_DOCUMENT = "No document on file"
CONTRACT_EXISTS = {"message": "This company already has a contract in progress", "code": "contract_exists"}
CONTRACT_EXPIRED = {"message": "This contract has expired. Start a renewal.", "code": "contract_expired"}
CONTRACT_CHANGED = {"message": "This contract was changed meanwhile", "code": "contract_changed"}
CONTRACT_OVERLAP = {"message": "These dates overlap a previous contract of this company", "code": "contract_overlap"}
SAME_STATUS = "The contract is already at this status"
DOCUMENT_REQUIRED = "Upload the signed contract document first"
WINDOW_REQUIRED = "Add the contract start and end dates"
WINDOW_ORDER = "The end date can't be before the start date"
FEE_VALUE_REQUIRED = "Enter the fee"
FEE_BASIS_REQUIRED = "Choose how the fee is charged"
FEE_PERCENT_MAX = "A percentage of CTC can be at most 100"
STORAGE_PREFIX = "recruiter-contracts"
UPLOAD_ACTION = "recruiter_contract.document_uploaded"
UPLOAD_LIMIT = 20  # per user per rolling hour (bdm-005 M8)
UPLOAD_WINDOW = timedelta(hours=1)
THROTTLED = "Too many uploads. Try again later."
NO_TERMS = "Your role cannot view or change client commercial terms"  # pob-001 C5
NO_VENDOR_TERMS = "Your role cannot view or change vendor commercial terms"  # pob-010 V9
WRONG_PARTY = "This company has no such agreement side"
VENDOR_ONLY = "Only a vendor agreement has this term"
DIRECTION_REQUIRED = "Choose who pays whom before signing"

logger = logging.getLogger("app.recruiter")


def today() -> date:
    return datetime.now(IST).date()


def now() -> datetime:
    return datetime.now(UTC)


def effective_status(contract: RecruiterContract, on: date) -> str:
    """CT2: a Signed or Active contract whose end date is before `on` reads Expired; `expired` is never stored."""
    if contract.status in RECRUITER_CONTRACT_EXPIRING and contract.end_date is not None and contract.end_date < on:
        return "expired"
    return contract.status


def stored_state(contract: RecruiterContract) -> dict:
    return {"status": contract.status, "party": contract.party, **{f: getattr(contract, f) for f in FIELDS}, "has_document": contract.contract_document_key is not None}


def resolve_party(company: Company, party: str | None) -> str:
    """pob-010 V8: unsent = the company's client side, or the vendor side of a vendor-only company. A side the company does not have is a 422."""
    sides = {"vendor": (VENDOR,), "vendor_client": (CLIENT, VENDOR)}.get(company.partner_type, (CLIENT,))
    if party is None:
        return sides[0]
    if party not in sides:
        raise HTTPException(422, WRONG_PARTY)
    return party


def check_rules(state: dict) -> None:
    """CT3 / CT4 and the date order on the merged state (stored values + the request), so clearing a required value alone is refused too."""
    if state["start_date"] and state["end_date"] and state["end_date"] < state["start_date"]:
        raise _invalid("end_date", WINDOW_ORDER, state["end_date"].isoformat())
    if state["fee_basis"] is not None and state["fee_value"] is None:
        raise _invalid("fee_value", FEE_VALUE_REQUIRED, None)
    if state["fee_value"] is not None and state["fee_basis"] is None:
        raise _invalid("fee_basis", FEE_BASIS_REQUIRED, None)
    if state["fee_basis"] == "percent_of_ctc" and state["fee_value"] > 100:
        raise _invalid("fee_value", FEE_PERCENT_MAX, str(state["fee_value"]))
    if state["status"] in RECRUITER_CONTRACT_EXPIRING and not state["has_document"]:
        raise _invalid("status", DOCUMENT_REQUIRED, state["status"])
    if state["party"] == CLIENT:  # pob-010 V8
        for field in VENDOR_TERMS:
            if state[field] is not None:
                raise _invalid(field, VENDOR_ONLY, None)
    elif state["status"] in RECRUITER_CONTRACT_EXPIRING and state["direction"] is None:
        raise _invalid("direction", DIRECTION_REQUIRED, None)
    if state["status"] == "active":
        for field in ("start_date", "end_date"):
            if state[field] is None:
                raise _invalid(field, WINDOW_REQUIRED, None)


def check_status_change(before: str, status: str, from_status: str | None) -> None:
    """A status change from the form: a stale `from_status` 409, Expired 409, the same status 422."""
    if from_status != before:
        raise HTTPException(409, {"message": f"This contract moved to {LABELS[before]} meanwhile", "code": "contract_status_changed", "current_status": before})
    if before == "expired":
        raise HTTPException(409, CONTRACT_EXPIRED)
    if status == before:
        raise _invalid("status", SAME_STATUS, status)


def check_version(contract: RecruiterContract, expected: datetime | None) -> None:
    if expected is not None and expected != contract.updated_at:
        raise HTTPException(409, CONTRACT_CHANGED)


async def check_overlap(db: AsyncSession, company: Company, state: dict, exclude_id: UUID | None) -> None:
    """CT8: the window may not overlap a previous contract that has a start date; a missing end date is open-ended. Runs under the
    company lock, so two writers can't both pass."""
    start = state["start_date"]
    if start is None:
        return
    end = state["end_date"] or date.max
    where = [RecruiterContract.company_id == company.id, RecruiterContract.party == state["party"], RecruiterContract.start_date.is_not(None), RecruiterContract.start_date <= end,
             func.coalesce(RecruiterContract.end_date, date.max) >= start]  # fmt: skip
    if exclude_id is not None:
        where.append(RecruiterContract.id != exclude_id)
    if await db.scalar(select(RecruiterContract.id).where(*where).limit(1)):
        raise HTTPException(409, CONTRACT_OVERLAP)


async def load_current(db: AsyncSession, company: Company, *, lock: bool = False, party: str = CLIENT) -> RecruiterContract | None:
    stmt = select(RecruiterContract).where(RecruiterContract.company_id == company.id, RecruiterContract.party == party, RecruiterContract.is_current.is_(True))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(stmt)


async def load_scoped_contract(db: AsyncSession, user: User, contract_id: UUID) -> tuple[RecruiterContract, Company]:
    """Any contract (current or previous) through its company's read scope; unknown and out of scope give the same 404 (IDOR)."""
    stmt = select(RecruiterContract, Company).join(Company, Company.id == RecruiterContract.company_id)
    row = (await db.execute(stmt.where(RecruiterContract.id == contract_id, *await companies.caller_scope(db, user)))).first()
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row[0], row[1]


async def sees_commercials(db: AsyncSession, user: User, party: str = CLIENT) -> bool:
    """pob-001 (DEC-SCOPE-403): `commercials.client.view` (pob-010 V9: `commercials.vendor.view` for a vendor agreement) -- the user's own
    override, else their role (at most two indexed reads)."""
    return await permissions.user_has_grant(db, user, f"commercials.{party}", "view")


async def commercial_access(db: AsyncSession, user: User, party: str = CLIENT) -> tuple[bool, bool]:
    """pob-001 C4: (view, edit) of that side's commercials; `edit` counts only with `view`."""
    view = await sees_commercials(db, user, party)
    return view, view and await permissions.user_has_grant(db, user, f"commercials.{party}", "edit")


async def require_terms(db: AsyncSession, user: User, route: str, *, edit: bool, message: str | None = None, party: str = CLIENT) -> None:
    """403 without that side's `view` (or, with `edit`, the effective edit), logged with the actor, role and route only -- never the value
    that was sent."""
    allowed = (await commercial_access(db, user, party))[1] if edit else await sees_commercials(db, user, party)
    if not allowed:
        logger.warning("recruiter_commercials_refused", extra={"extra_fields": {"actor_id": str(user.id), "role": user.role, "route": route, "party": party}})
        raise HTTPException(403, message or (NO_VENDOR_TERMS if party == VENDOR else NO_TERMS))


def can_write(user: User, company: Company) -> bool:
    return companies.permissions(user, company)["can_edit"]


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def store(data: bytes, content_type: str) -> str:
    """A server-generated key; the client never names a path. A storage failure is a 500, logged by key digest (never the key)."""
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(key, data, content_type)
    except Exception:
        logger.exception("recruiter_contract_document_store_failed", extra={"extra_fields": {"key_digest": _digest(key)}})
        raise
    return key


def discard(key: str) -> None:
    """Delete an object stored for a write that did not commit. A failure leaves a logged orphan."""
    try:
        storage.delete(key)
    except Exception:
        logger.warning("recruiter_contract_document_orphaned", extra={"extra_fields": {"key_digest": _digest(key)}})


def read_document(contract: RecruiterContract, kind: str) -> tuple[bytes, str]:
    key = getattr(contract, f"{kind}_document_key")
    if key is None:
        raise HTTPException(404, NO_DOCUMENT)
    try:
        return storage.read_bytes(key), getattr(contract, f"{kind}_document_content_type")
    except FileNotFoundError:
        logger.warning("recruiter_contract_document_missing", extra={"extra_fields": {"contract_id": str(contract.id), "key_digest": _digest(key)}})
        raise HTTPException(404, NO_DOCUMENT) from None


async def upload_wait(db: AsyncSession, user: User) -> int:
    """Seconds before the caller may upload again (their audit rows in the last hour; shared by every API instance)."""
    at = now()
    stmt = (
        select(AuditLog.created_at)
        .where(AuditLog.user_id == user.id, AuditLog.action == UPLOAD_ACTION, AuditLog.created_at > at - UPLOAD_WINDOW)
        .order_by(AuditLog.created_at.desc())
        .limit(UPLOAD_LIMIT)
    )
    return retry_after(list((await db.scalars(stmt)).all()), UPLOAD_LIMIT, at, UPLOAD_WINDOW)


def record(db: AsyncSession, user: User, contract: RecruiterContract, kind: str, from_status: str | None, to_status: str, changed: list[str], document_key: str | None = None) -> None:
    db.add(RecruiterContractEvent(contract_id=contract.id, actor_user_id=user.id, kind=kind, from_status=from_status, to_status=to_status, changed=changed, document_key=document_key))


def audit(db: AsyncSession, user: User, action: str, contract: RecruiterContract, metadata: dict) -> None:
    """Same transaction as the write (fail closed); ids, status keys and field names only."""
    db.add(AuditLog(user_id=user.id, action=f"recruiter_contract.{action}", entity_type="recruiter_contract", entity_id=str(contract.id),
                    metadata_json={"company_id": str(contract.company_id), **metadata}))


def log(event: str, user: User, contract: RecruiterContract, **extra) -> None:
    companies.log(event, user, contract.company_id, contract_id=str(contract.id), **extra)


def _document(contract: RecruiterContract, kind: str) -> dict | None:
    if getattr(contract, f"{kind}_document_key") is None:
        return None
    return {name: getattr(contract, f"{kind}_document_{name}") for name in ("name", "content_type", "uploaded_at")}


async def contract_out(db: AsyncSession, user: User, company: Company, contract: RecruiterContract, on: date, access: tuple[bool, bool] | None = None) -> dict:
    """pob-001 C5: without `commercials.client.view` the terms are absent (the routes answer with response_model_exclude_unset)."""
    status = effective_status(contract, on)
    view, edit = access or await commercial_access(db, user, contract.party)
    editable = can_write(user, company) and contract.is_current
    creator = await db.get_one(User, contract.created_by_user_id)  # RESTRICT foreign key: always exists
    return {
        "id": contract.id,
        "party": contract.party,
        "status": status,
        "status_label": LABELS[status],
        "status_changed_at": contract.status_changed_at,
        **{f: getattr(contract, f) for f in FIELDS if view or f not in TERMS},
        "expired_on": contract.end_date + timedelta(days=1) if status == "expired" and contract.end_date else None,
        "contract_document": _document(contract, "contract"),
        "mou_document": _document(contract, "mou"),
        "is_current": contract.is_current,
        "created_by": companies.person(creator),
        "permissions": {
            "can_edit": editable, "can_upload": editable and edit, "can_renew": editable and status in RENEWABLE,
            "can_view_terms": view, "can_edit_terms": editable and edit,
        },  # fmt: skip
        "created_at": contract.created_at,
        "updated_at": contract.updated_at,
    }


async def company_contracts_out(db: AsyncSession, user: User, company: Company, party: str = CLIENT) -> dict:
    on = today()
    rows = (await db.scalars(select(RecruiterContract).where(RecruiterContract.company_id == company.id, RecruiterContract.party == party)
                             .order_by(RecruiterContract.created_at.desc(), RecruiterContract.id))).all()
    current = next((r for r in rows if r.is_current), None)
    renewable = current is None or effective_status(current, on) in RENEWABLE
    access = await commercial_access(db, user, party)
    return {
        "current": await contract_out(db, user, company, current, on, access) if current else None,
        "previous": [await contract_out(db, user, company, r, on, access) for r in rows if not r.is_current],
        "can_start": can_write(user, company) and renewable,
        "can_view_terms": access[0],  # pob-001 C5: for a first contract's form
        "can_edit_terms": can_write(user, company) and access[1],
    }


async def company_contract_ref(db: AsyncSession, company: Company, party: str = CLIENT) -> dict | None:
    """CT10: the current contract's effective status for the company detail."""
    current = await load_current(db, company, party=party)
    if current is None:
        return None
    status = effective_status(current, today())
    return {"status": status, "status_label": LABELS[status]}


async def history_page(db: AsyncSession, contract: RecruiterContract, limit: int, offset: int) -> dict:
    """Newest first; the replaced document's key is never returned."""
    where = RecruiterContractEvent.contract_id == contract.id
    total = await db.scalar(select(func.count()).select_from(RecruiterContractEvent).where(where))
    stmt = select(RecruiterContractEvent, User).join(User, User.id == RecruiterContractEvent.actor_user_id).where(where)
    rows = (await db.execute(stmt.order_by(RecruiterContractEvent.position.desc()).limit(limit).offset(offset))).all()
    items = [
        {
            "id": e.id,
            "kind": e.kind,
            "from_status": e.from_status,
            "from_label": LABELS[e.from_status] if e.from_status else None,
            "to_status": e.to_status,
            "to_label": LABELS[e.to_status],
            "changed": e.changed,
            "actor": companies.person(actor),
            "created_at": e.created_at,
        }
        for e, actor in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}
