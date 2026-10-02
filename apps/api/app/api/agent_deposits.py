"""AGN-011 -- an agency application's deposit, paid through EduSphere Razorpay (DEC-SCOPE-057; spec §4).

Master, and Staff for students assigned to them, set the deposit and pay it (D7); anything outside the caller's scope is 404 (the AGN-008
application scope). Writes lock the organisation, the application, the deposit and then any payment, and commit once. Only the payments
paid hook marks a deposit paid; only an Overseas Admin records remittance and refunds (D5).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_applications import _audit, _gate, _locked, _log, _refuse_closed
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import ApplicationDeposit, User
from app.schemas import AgentDepositSave
from app.services.agent_applications import detail
from app.services.agent_deposits import PAID_LOCKED, PAID_STATES, cancel_active, deposit_for

router = APIRouter(prefix="/workflows/overseas/agent/crm/applications", tags=["agent-deposits"])
admin_router = APIRouter(prefix="/overseas-admin/deposits", tags=["overseas-admin"])


@router.put("/{application_id}/deposit")
async def save_deposit(application_id: UUID, payload: AgentDepositSave, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§4.2: create or replace the deposit terms while it is unpaid. An identical request writes nothing (a retry is safe). Changing the
    amount, or making it not required, cancels the open checkout so its order can never mark the deposit paid."""
    membership = _gate(user)
    item = await _locked(db, user, membership, application_id)
    record = await _refuse_closed(db, user, item)
    deposit = await deposit_for(db, item.id, lock=True)
    if deposit is not None and deposit.status in PAID_STATES:
        raise HTTPException(409, PAID_LOCKED)
    new = {"required": payload.required, "amount": payload.amount, "due_date": payload.due_date, "status": "pending" if payload.required else "not_required"}
    if deposit is None:
        deposit = ApplicationDeposit(application_id=item.id, currency="INR", created_by_user_id=user.id, updated_by_user_id=user.id)
        db.add(deposit)
        changed = sorted(k for k in ("required", "amount", "due_date") if new[k] is not None or k == "required")
    else:
        changed = sorted(k for k in ("required", "amount", "due_date") if getattr(deposit, k) != new[k])
    if not changed:
        return {"application": await detail(db, user, item, record=record)}
    if {"required", "amount"} & set(changed):
        await cancel_active(db, deposit)
    for key, value in new.items():
        setattr(deposit, key, value)
    deposit.updated_by_user_id = user.id
    _audit(db, user, "deposit", item.id, {"fields": changed, "required": payload.required})
    await db.commit()
    _log("agent_deposit_saved", membership, user, item.id, fields=changed, required=payload.required)
    return {"application": await detail(db, user, item, record=record)}
