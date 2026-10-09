"""rec-030 (DEC-SCOPE-153, spec §3): a company's contract / MoU, its documents and history.

Every `{company_id}` resolves through `recruiter_companies.load_scoped` (out of scope = 404; a non-recruiter role = 403). Every write is
one transaction -- company lock, `require(can_edit)` (the assigned recruiter or super_admin; archived 409), the current contract lock, the
rules, change + history row + audit row, one commit here, then the log line (the bdm-005 MoU routes)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.portfolio_certificates import EXTENSION, HEADERS
from app.core.database import get_db
from app.models import RecruiterContract, User
from app.schemas import RecCompanyContracts, RecContractCreate, RecContractEnvelope, RecContractEventPage, RecContractUpdate
from app.services import recruiter_companies as companies
from app.services import recruiter_contracts as svc
from app.services.agent_documents import read_upload

router = APIRouter(prefix="/recruiter", tags=["recruiter-contracts"])
DocumentKind = Literal["contract", "mou"]


@router.get("/companies/{company_id}/contracts", response_model=RecCompanyContracts)
async def get_contracts(company_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    company = await companies.load_scoped(db, user, company_id)
    return await svc.company_contracts_out(db, user, company)


@router.post("/companies/{company_id}/contracts", status_code=201, response_model=RecContractEnvelope)
async def create_contract(company_id: UUID, payload: RecContractCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A first contract, or a renewal once the current one reads Signed, Active or Expired (CT7): the old row stops being current and
    keeps its history. 409 `contract_exists` while one is in progress; the partial unique index is the backstop under the lock."""
    company = await companies.load_scoped(db, user, company_id, lock=True)
    companies.require(user, company, "can_edit", "contract_create")
    on = svc.today()
    current = await svc.load_current(db, company, lock=True)
    previous = svc.effective_status(current, on) if current else None
    if current is not None and previous not in svc.RENEWABLE:
        raise HTTPException(409, svc.CONTRACT_EXISTS)
    state = payload.model_dump()
    svc.check_rules({**state, "has_document": False})
    await svc.check_overlap(db, company, state, None)
    if current is not None:
        current.is_current = False
        await db.flush()  # the index allows the new current row only after this
    contract = RecruiterContract(company_id=company.id, created_by_user_id=user.id, **state)
    db.add(contract)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, svc.CONTRACT_EXISTS) from None
    if current is not None and previous is not None:
        svc.record(db, user, current, "renewed", previous, previous, [])
        svc.audit(db, user, "renewed", current, {"renewed_by": str(contract.id)})
    svc.record(db, user, contract, "created", None, contract.status, [])
    svc.audit(db, user, "created", contract, {"status": contract.status})
    await db.commit()
    await db.refresh(contract)
    svc.log("recruiter_contract_created", user, contract, status=contract.status, renewed=current is not None)
    return {"contract": await svc.contract_out(db, user, company, contract, on)}


@router.patch("/companies/{company_id}/contracts", response_model=RecContractEnvelope)
async def change_contract(company_id: UUID, payload: RecContractUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The fields and an optional status change. Nothing changed = nothing recorded."""
    company = await companies.load_scoped(db, user, company_id, lock=True)
    companies.require(user, company, "can_edit", "contract_change")
    on = svc.today()
    contract = await svc.load_current(db, company, lock=True)
    if contract is None:
        raise HTTPException(404, svc.NO_CONTRACT)
    sent = payload.model_dump(exclude_unset=True)
    status, from_status, expected = sent.pop("status", None), sent.pop("from_status", None), sent.pop("expected_updated_at", None)
    before = svc.effective_status(contract, on)
    if status is not None:
        svc.check_status_change(before, status, from_status)  # first: its message names the status someone else set
    svc.check_version(contract, expected)
    state = {**svc.stored_state(contract), **sent, **({"status": status} if status else {})}
    svc.check_rules(state)
    changed = [f for f in svc.FIELDS if state[f] != getattr(contract, f)] + (["status"] if status else [])
    if not changed:
        return {"contract": await svc.contract_out(db, user, company, contract, on)}
    if {"start_date", "end_date"} & set(changed):
        await svc.check_overlap(db, company, state, contract.id)
    for field in svc.FIELDS:
        setattr(contract, field, state[field])
    if status is not None:
        contract.status, contract.status_changed_at = status, svc.now()
    after = svc.effective_status(contract, on)
    kind, action = ("status", "status_changed") if status else ("updated", "updated")
    svc.record(db, user, contract, kind, before, after, changed)
    svc.audit(db, user, action, contract, {"from": before, "to": after, "changed": changed})
    await db.commit()
    await db.refresh(contract)
    svc.log(f"recruiter_contract_{action}", user, contract, from_status=before, to_status=after, changed=changed)
    return {"contract": await svc.contract_out(db, user, company, contract, on)}


@router.put("/companies/{company_id}/contracts/document", response_model=RecContractEnvelope)
async def upload_document(company_id: UUID, kind: DocumentKind, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Scope and role first, then the bytes (type by content, size cap, metadata stripped) before any lock, then the locked write. The new
    object is deleted when anything after storing it fails; a replaced object is kept (its key is in the event row, never returned)."""
    companies.require(user, await companies.load_scoped(db, user, company_id), "can_edit", "contract_document")
    data, content_type, name = await read_upload(file)
    company = await companies.load_scoped(db, user, company_id, lock=True)
    companies.require(user, company, "can_edit", "contract_document")
    contract = await svc.load_current(db, company, lock=True)
    if contract is None:
        raise HTTPException(404, svc.NO_CONTRACT)
    wait = await svc.upload_wait(db, user)
    if wait:
        svc.log("recruiter_contract_throttled", user, contract, wait_seconds=wait)
        raise HTTPException(429, svc.THROTTLED, headers={"Retry-After": str(wait)})
    on = svc.today()
    old_key = getattr(contract, f"{kind}_document_key")
    key = svc.store(data, content_type)
    try:
        for column, value in (("key", key), ("content_type", content_type), ("name", name), ("uploaded_at", svc.now())):
            setattr(contract, f"{kind}_document_{column}", value)
        status = svc.effective_status(contract, on)
        svc.record(db, user, contract, "document", status, status, [f"{kind}_document"], document_key=old_key)
        svc.audit(db, user, "document_uploaded", contract, {"kind": kind, "content_type": content_type, "replaced": old_key is not None, "bytes": len(data)})
        await db.commit()
    except BaseException:
        await db.rollback()
        svc.discard(key)
        raise
    await db.refresh(contract)
    svc.log("recruiter_contract_document_uploaded", user, contract, kind=kind, content_type=content_type, replaced=old_key is not None, bytes=len(data))
    return {"contract": await svc.contract_out(db, user, company, contract, on)}


@router.get("/contracts/{contract_id}/history", response_model=RecContractEventPage)
async def contract_history(contract_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    contract, _ = await svc.load_scoped_contract(db, user, contract_id)
    return await svc.history_page(db, contract, limit, offset)


@router.get("/contracts/{contract_id}/documents/{kind}")
async def download_document(contract_id: UUID, kind: DocumentKind, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """In the company's read scope only (404 otherwise, as an unknown id). The audit row is committed before any byte leaves; the file
    name is built from the company code, never the uploaded name."""
    contract, company = await svc.load_scoped_contract(db, user, contract_id)
    data, media_type = svc.read_document(contract, kind)
    filename = f"{kind}-{company.company_code}.{EXTENSION.get(media_type, 'bin')}"
    svc.audit(db, user, "document_downloaded", contract, {"kind": kind, "role": user.role})
    await db.commit()
    svc.log("recruiter_contract_document_downloaded", user, contract, kind=kind, role=user.role)
    return Response(content=data, media_type=media_type, headers={**HEADERS, "Content-Disposition": f'attachment; filename="{filename}"'})
