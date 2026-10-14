"""mgmt-004 (spec ML1-ML16): the management ledger routes. Finance tier only (partner, accountant; M13): `super_admin` and every other
role 403. Every write locks its row, checks the status after the lock, adds an entry event + a management audit row, and commits once
here; a log line follows the commit (ids and statuses only)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.portfolio_certificates import EXTENSION, HEADERS
from app.models import LEDGER_KINDS, LEDGER_STATUSES, LEDGER_VERTICALS, LedgerCategory, LedgerEntry, User
from app.schemas import (
    LedgerCategoryCreate,
    LedgerCategoryOut,
    LedgerCategoryPage,
    LedgerCategoryUpdate,
    LedgerEntryCreate,
    LedgerEntryDetail,
    LedgerEntryUpdate,
    LedgerOptions,
    LedgerPage,
    LedgerReasonIn,
)
from app.services import ledger as svc
from app.services import management_audit
from app.services.agent_documents import read_upload

router = APIRouter(prefix="/management/ledger", tags=["management-ledger"])
MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


# --- categories (ML1-ML3) -----------------------------------------------------------------------------------------------------
@router.get("/categories", response_model=LedgerCategoryPage)
async def list_categories(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_finance(user)
    return {"items": await svc.categories(db)}


@router.post("/categories", status_code=201, response_model=LedgerCategoryOut)
async def create_category(payload: LedgerCategoryCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_finance(user)
    if await svc.name_taken(db, payload.kind, payload.name):
        raise HTTPException(409, svc.DUPLICATE_CATEGORY)
    category = LedgerCategory(kind=payload.kind, nature=payload.nature, name=payload.name, created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(category)
    try:
        await db.flush()
    except IntegrityError:  # the unique index, when two people add the same name at once
        await db.rollback()
        raise HTTPException(409, svc.DUPLICATE_CATEGORY) from None
    management_audit.record(db, user, "mgmt.ledger_category", "create", str(category.id), fields=["kind", "nature", "name"])
    await db.commit()
    svc.log("ledger_category_created", user, category.id)
    return svc.category_out(category)


@router.patch("/categories/{category_id}", response_model=LedgerCategoryOut)
async def change_category(category_id: UUID, payload: LedgerCategoryUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Rename or (de)activate. Kind and nature never change (ML2); a deactivated category keeps its entries (ML3)."""
    svc.require_finance(user)
    category = await svc.load_category(db, category_id, lock=True)
    sent = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    changed = [field for field, value in sent.items() if getattr(category, field) != value]
    if not changed:
        return svc.category_out(category)
    if "name" in changed and await svc.name_taken(db, category.kind, sent["name"], except_id=category.id):
        raise HTTPException(409, svc.DUPLICATE_CATEGORY)
    for field in changed:
        setattr(category, field, sent[field])
    category.updated_by_user_id = user.id
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, svc.DUPLICATE_CATEGORY) from None
    management_audit.record(db, user, "mgmt.ledger_category", "update", str(category.id), fields=changed)
    await db.commit()
    svc.log("ledger_category_changed", user, category.id, changed=changed)
    return svc.category_out(category)


@router.get("/options", response_model=LedgerOptions)
async def ledger_options(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The entry form's choices: active categories, the 13 lead-source channels (M7), verticals, active courses with their batches, schools."""
    svc.require_finance(user)
    return await svc.options(db)


# --- entries ------------------------------------------------------------------------------------------------------------------
@router.get("", response_model=LedgerPage)
async def list_entries(
    month: str | None = Query(None, pattern=MONTH),
    kind: Literal[LEDGER_KINDS] | None = None,  # type: ignore[valid-type]
    category: UUID | None = None,
    vertical: Literal[LEDGER_VERTICALS] | None = None,  # type: ignore[valid-type]
    status: Literal[LEDGER_STATUSES] | None = None,  # type: ignore[valid-type]
    include: Literal["auto"] | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ML15: newest date first; `totals` are the approved entries matching every filter but status (ML10). mgmt-005 (MA9):
    `include=auto` adds the automatic lines of other modules, read-only, to the list and the totals."""
    svc.require_finance(user)
    filters = {"month": month, "kind": kind, "category_id": category, "vertical": vertical}
    if include:
        return await svc.lines_page(db, user, filters, status, limit, offset)
    return await svc.page(db, user, svc.list_filters(**filters), status, limit, offset)


@router.post("", status_code=201, response_model=LedgerEntryDetail)
async def create_entry(payload: LedgerEntryCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ML4-ML7: a new draft."""
    svc.require_finance(user)
    state = payload.model_dump(exclude={"kind"})
    await svc.entry_category(db, state["category_id"], payload.kind)
    await svc.resolve_tags(db, payload.kind, state)
    entry = LedgerEntry(kind=payload.kind, status="draft", created_by_user_id=user.id, updated_by_user_id=user.id, **state)
    db.add(entry)
    await db.flush()
    svc.add_event(db, user, entry, "created", None)
    fields = [f for f in svc.FIELDS if state.get(f) is not None]
    svc.audit(db, user, "create", entry.id, fields, after=state)
    await db.commit()
    svc.log("ledger_entry_created", user, entry.id, kind=entry.kind)
    return await svc.entry_detail(db, user, entry)


@router.get("/{entry_id}", response_model=LedgerEntryDetail)
async def get_entry(entry_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_finance(user)
    return await svc.entry_detail(db, user, await svc.load_entry(db, entry_id))


@router.patch("/{entry_id}", response_model=LedgerEntryDetail)
async def change_entry(entry_id: UUID, payload: LedgerEntryUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ML7/ML12: a draft or rejected entry only; a rejected entry returns to draft. Nothing changed = nothing recorded."""
    svc.require_finance(user)
    entry = await svc.load_entry(db, entry_id, lock=True)
    if entry.status not in svc.EDITABLE:
        raise HTTPException(409, svc.LOCKED)
    before = {f: getattr(entry, f) for f in svc.FIELDS}
    state = {**before, **payload.model_dump(exclude_unset=True)}
    if state["category_id"] != entry.category_id:
        await svc.entry_category(db, state["category_id"], entry.kind)
    if "program_id" in payload.model_fields_set and "batch_id" not in payload.model_fields_set and state["batch_id"]:
        state["batch_id"] = None  # a new course clears a batch of the old one
    await svc.resolve_tags(db, entry.kind, state)
    changed = [f for f in svc.FIELDS if state[f] != before[f]]
    if not changed:
        return await svc.entry_detail(db, user, entry)
    for field in changed:
        setattr(entry, field, state[field])
    previous = entry.status
    entry.updated_by_user_id = user.id
    if previous == "rejected":
        entry.status, entry.rejection_reason, entry.decided_by_user_id, entry.decided_at = "draft", None, None, None
    svc.add_event(db, user, entry, "updated", previous, fields=changed)
    svc.audit(db, user, "update", entry.id, changed, before, state)
    await db.commit()
    svc.log("ledger_entry_changed", user, entry.id, changed=changed, from_status=previous, to_status=entry.status)
    return await svc.entry_detail(db, user, entry)


@router.post("/{entry_id}/submit", response_model=LedgerEntryDetail)
async def submit_entry(entry_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_finance(user)
    entry = await svc.load_entry(db, entry_id, lock=True)
    if entry.status not in svc.EDITABLE:
        raise HTTPException(409, svc.NOT_SUBMITTABLE)
    previous = entry.status
    entry.status, entry.submitted_at, entry.updated_by_user_id = "submitted", svc.now(), user.id
    svc.add_event(db, user, entry, "submitted", previous)
    svc.audit(db, user, "submit", entry.id, ["status"], {"status": previous}, {"status": "submitted"})
    await db.commit()
    svc.log("ledger_entry_submitted", user, entry.id)
    return await svc.entry_detail(db, user, entry)


async def _decide(db: AsyncSession, user: User, entry_id: UUID, outcome: str, reason: str | None = None) -> dict:
    """ML9: a partner, not the entry's creator, decides a submitted entry. The row lock serialises two partners deciding at once."""
    svc.require_finance(user)
    svc.require_partner(user)
    entry = await svc.load_entry(db, entry_id, lock=True)
    if entry.created_by_user_id == user.id:
        raise HTTPException(403, svc.OWN_ENTRY)
    if entry.status != "submitted":
        raise HTTPException(409, svc.NOT_SUBMITTED)
    entry.status, entry.decided_by_user_id, entry.decided_at, entry.rejection_reason = outcome, user.id, svc.now(), reason
    svc.add_event(db, user, entry, outcome, "submitted", reason=reason)
    svc.audit(db, user, "approve" if outcome == "approved" else "reject", entry.id, ["status"], {"status": "submitted"}, {"status": outcome})
    await db.commit()
    svc.log(f"ledger_entry_{outcome}", user, entry.id)
    return await svc.entry_detail(db, user, entry)


@router.post("/{entry_id}/approve", response_model=LedgerEntryDetail)
async def approve_entry(entry_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _decide(db, user, entry_id, "approved")


@router.post("/{entry_id}/reject", response_model=LedgerEntryDetail)
async def reject_entry(entry_id: UUID, payload: LedgerReasonIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _decide(db, user, entry_id, "rejected", payload.reason)


@router.post("/{entry_id}/reverse", status_code=201, response_model=LedgerEntryDetail)
async def reverse_entry(entry_id: UUID, payload: LedgerReasonIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ML11: a submitted reversing entry dated today (IST); it counts once a partner approves it. One live reversal per entry."""
    svc.require_finance(user)
    original = await svc.load_entry(db, entry_id, lock=True)
    if original.reversal_of_id is not None:
        raise HTTPException(409, svc.REVERSAL_OF_REVERSAL)
    if original.status != "approved":
        raise HTTPException(409, svc.NOT_REVERSIBLE)
    if await svc.live_reversal_id(db, original.id) is not None:
        raise HTTPException(409, svc.ALREADY_REVERSED)
    copied = {f: getattr(original, f) for f in svc.FIELDS if f not in ("entry_date", "description")}
    reversal = LedgerEntry(
        kind=original.kind,
        entry_date=svc.today(),
        description=f"Reversal: {payload.reason}"[:500],
        status="submitted",
        submitted_at=svc.now(),
        reversal_of_id=original.id,
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
        **copied,
    )
    db.add(reversal)
    try:
        await db.flush()
    except IntegrityError:  # the partial unique index, if two reversals race past the check
        await db.rollback()
        raise HTTPException(409, svc.ALREADY_REVERSED) from None
    svc.add_event(db, user, reversal, "created", None, reason=payload.reason)
    svc.add_event(db, user, original, "reversed", original.status, reason=payload.reason)
    management_audit.record(db, user, "mgmt.ledger", "reverse", str(original.id), fields=["reversal_id"], values={"reversal_id": (None, reversal.id)})
    await db.commit()
    svc.log("ledger_entry_reversed", user, original.id, reversal_id=str(reversal.id))
    return await svc.entry_detail(db, user, reversal)


# --- receipt (ML13) -----------------------------------------------------------------------------------------------------------
@router.put("/{entry_id}/receipt", response_model=LedgerEntryDetail)
async def upload_receipt(entry_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Role first, then the bytes (type by content, size cap, metadata stripped), then the locked write. The new object is deleted
    when anything after storing it fails; a replaced object is kept (its key is in the event row, never returned)."""
    svc.require_finance(user)
    data, content_type, name = await read_upload(file)
    entry = await svc.load_entry(db, entry_id, lock=True)
    if entry.status not in svc.EDITABLE:
        raise HTTPException(409, svc.LOCKED)
    old_key = entry.receipt_key
    key = svc.store(data, content_type)
    try:
        entry.receipt_key, entry.receipt_content_type, entry.receipt_name, entry.updated_by_user_id = key, content_type, name, user.id
        svc.add_event(db, user, entry, "receipt", entry.status, fields=["receipt"], receipt_key=old_key)
        svc.audit(db, user, "update", entry.id, ["receipt"])
        await db.commit()
    except BaseException:
        await db.rollback()
        svc.discard(key)
        raise
    svc.log("ledger_receipt_uploaded", user, entry.id, content_type=content_type, replaced=old_key is not None, bytes=len(data))
    return await svc.entry_detail(db, user, entry)


@router.get("/{entry_id}/receipt")
async def download_receipt(entry_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The audit row is committed before any byte leaves; the file name is built here, never the uploaded name."""
    svc.require_finance(user)
    entry = await svc.load_entry(db, entry_id)
    data, media_type = svc.read_receipt(entry)
    management_audit.record(db, user, "mgmt.ledger", "download", str(entry.id), fields=["receipt"])
    await db.commit()
    svc.log("ledger_receipt_downloaded", user, entry.id)
    filename = f"ledger-receipt-{entry.entry_date.isoformat()}-{str(entry.id)[:8]}.{EXTENSION.get(media_type, 'bin')}"
    return Response(content=data, media_type=media_type, headers={**HEADERS, "Content-Disposition": f'attachment; filename="{filename}"'})
