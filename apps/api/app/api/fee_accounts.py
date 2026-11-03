"""itc-013 (DEC-SCOPE-346) -- the per-enrolment fee account: read by the student (their own), the IT counselor (their linked students,
itc-003) and a `payments.view` holder in IT; an offline payment recorded by a `payments.add` holder in IT. A record outside the caller's
reach is 404; a role with no access at all is 403. API_CONTRACT.md §12IR; RBAC_MATRIX.md §2.246."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import PAYMENTS_ADD, _every_division
from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.identifiers import uuid_reference
from app.models import Enrollment, ItStudentCounselor, User
from app.services import fee_accounts, it_lifecycle, permissions

router = APIRouter(prefix="/it", tags=["it-fee-accounts"])

NOT_FOUND = "Enrolment not found"
NO_ACCESS = "You do not have access to fee accounts"


class RecordPayment(BaseModel):
    amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
    payment_mode: Literal["cash", "upi", "card", "bank_transfer", "cheque"]  # fee_accounts.OFFLINE_MODES
    provider_reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)] | None = None


def _in_it(user: User) -> bool:
    return _every_division(user) or user.division == "it"


async def _enrollment(db: AsyncSession, enrollment_id: UUID) -> Enrollment:
    item = await db.get(Enrollment, enrollment_id)
    if item is None:
        raise HTTPException(404, NOT_FOUND)
    return item


async def _readable(db: AsyncSession, user: User, enrollment_id: UUID) -> Enrollment:
    """The enrolment, if this caller may read its account (see the module docstring)."""
    if user.role == "it_student":
        item = await _enrollment(db, enrollment_id)
        if item.student_id != user.id:
            raise HTTPException(404, NOT_FOUND)
        return item
    if user.role == "counselor" and user.division == "it":
        item = await _enrollment(db, enrollment_id)
        linked = await db.scalar(select(ItStudentCounselor.id).where(ItStudentCounselor.student_user_id == item.student_id, ItStudentCounselor.counselor_user_id == user.id))
        if linked is None:
            raise HTTPException(404, NOT_FOUND)
        return item
    if not await permissions.user_has_grant(db, user, "payments", "view"):
        raise HTTPException(403, NO_ACCESS)
    item = await _enrollment(db, enrollment_id)
    if not _in_it(user):
        raise HTTPException(404, NOT_FOUND)
    return item


@router.get("/enrollments/{enrollment_id}/fee-account")
async def fee_account(enrollment_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await fee_accounts.account(db, await _readable(db, user, enrollment_id))


@router.get("/student/fee-accounts")
async def my_fee_accounts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "it_student":
        raise HTTPException(403, "Only an IT student has fee accounts")
    enrollments = (await db.scalars(select(Enrollment).where(Enrollment.student_id == user.id).order_by(Enrollment.created_at.desc()))).all()
    return await fee_accounts.accounts(db, list(enrollments))


@router.post("/enrollments/{enrollment_id}/payments", status_code=201)
async def record_payment(enrollment_id: str, payload: RecordPayment, user: User = Depends(PAYMENTS_ADD), db: AsyncSession = Depends(get_db)):
    # QA13-02: the reference is typed into the Payments form, so a typo gets a plain message rather than the UUID parser's
    enrollment = await _enrollment(db, uuid_reference(enrollment_id, "enrolment reference"))
    if not _in_it(user):
        raise HTTPException(404, NOT_FOUND)
    paid = await fee_accounts.record_payment(db, user, enrollment, float(payload.amount), payload.payment_mode, payload.provider_reference or None)
    await it_lifecycle.sync(db, [enrollment.id], actor=user, cause="fee")  # itc-031: e.g. Partially paid -> Paid
    await db.commit()
    return {
        "payment": {"id": paid.id, "amount": float(paid.amount), "status": paid.status, "payment_mode": paid.payment_mode, "provider_reference": paid.provider_reference},
        "account": await fee_accounts.account(db, enrollment),
    }
