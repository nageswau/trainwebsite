"""itc-014 (DEC-SCOPE-363) -- discount and waiver approval (maker-checker). API_CONTRACT.md §12JI; RBAC_MATRIX.md §2.263.

- Requesting: the IT counselor linked to the student (itc-003), or a `discounts.add` holder in IT. Another counselor's student, or a
  holder in another division, is 404; any other role 403.
- Reading an enrolment's requests: whoever reads its fee account (itc-013), except the student (403).
- Deciding, and the queue: a `discounts.approve` holder in IT, never on their own request (403).
"""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.api.fee_accounts import NOT_FOUND, _enrollment, _in_it, _readable
from app.core.database import get_db
from app.models import Enrollment, User
from app.services import fee_accounts, fee_discounts, it_lifecycle, permissions

router = APIRouter(prefix="/it", tags=["it-fee-discounts"])

NO_REQUEST = "You cannot request fee discounts"
NO_APPROVE = "You cannot approve fee discounts"
APPROVER = require_permission("discounts", "approve", NO_APPROVE)
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class DiscountRequestIn(BaseModel):
    amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
    reason: Note


class ApproveIn(BaseModel):
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class RejectIn(BaseModel):
    note: Note


async def _requestable(db: AsyncSession, user: User, enrollment_id: UUID) -> Enrollment:
    if user.role == "counselor" and user.division == "it":
        return await _readable(db, user, enrollment_id)  # linked students only
    if not await permissions.user_has_grant(db, user, "discounts", "add"):
        raise HTTPException(403, NO_REQUEST)
    item = await _enrollment(db, enrollment_id)
    if not _in_it(user):
        raise HTTPException(404, NOT_FOUND)
    return item


def _approver_in_it(user: User) -> User:
    if not _in_it(user):
        raise HTTPException(403, NO_APPROVE)
    return user


@router.get("/enrollments/{enrollment_id}/discount-requests")
async def enrollment_requests(enrollment_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role == "it_student":
        raise HTTPException(403, "Students see approved discounts on their fee account")
    await _readable(db, user, enrollment_id)
    return await fee_discounts.listing(db, user, enrollment_id=enrollment_id)


@router.post("/enrollments/{enrollment_id}/discount-requests", status_code=201)
async def request_discount(enrollment_id: UUID, payload: DiscountRequestIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    enrollment = await _requestable(db, user, enrollment_id)
    item = await fee_discounts.create(db, user, enrollment, float(payload.amount), payload.reason)
    await db.commit()
    return await fee_discounts.one(db, user, item.id)


@router.get("/discount-requests")
async def discount_queue(status: Literal["pending", "approved", "rejected"] = "pending", user: User = Depends(APPROVER), db: AsyncSession = Depends(get_db)):
    return await fee_discounts.listing(db, _approver_in_it(user), status=status)


@router.post("/discount-requests/{request_id}/approve")
async def approve_discount(request_id: UUID, payload: ApproveIn, user: User = Depends(APPROVER), db: AsyncSession = Depends(get_db)):
    item = await fee_discounts.approve(db, _approver_in_it(user), request_id, payload.note or None)
    await it_lifecycle.sync(db, [item.enrollment_id], actor=user, cause="fee")  # itc-031: a full waiver moves the enrolment to Paid
    await db.commit()
    enrollment = await db.get(Enrollment, item.enrollment_id)
    return {"request": await fee_discounts.one(db, user, item.id), "account": await fee_accounts.account(db, enrollment)}


@router.post("/discount-requests/{request_id}/reject")
async def reject_discount(request_id: UUID, payload: RejectIn, user: User = Depends(APPROVER), db: AsyncSession = Depends(get_db)):
    item = await fee_discounts.reject(db, _approver_in_it(user), request_id, payload.note)
    await db.commit()
    return {"request": await fee_discounts.one(db, user, item.id)}
