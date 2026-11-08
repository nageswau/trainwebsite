"""pob-012 (DEC-SCOPE-433 W8, API §12LZ): vendor bills (payables / receivables), their payments, and the vendor performance report.

The `commercials.vendor` grant first (403: view to read, edit to write), then the company scope (404). Every write is one transaction --
the bill row lock, the rules (422 on a field / coded 409), the write, an audit row (ids and amounts only), one commit here, then the log."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import VendorBillCancel, VendorBillCreate, VendorBillEnvelope, VendorBillList, VendorBillPaymentCreate, VendorPerformanceDetail, VendorPerformancePage
from app.services import vendor_commercials as svc

router = APIRouter(prefix="/recruiter", tags=["vendor-commercials"])


@router.get("/companies/{company_id}/vendor-bills", response_model=VendorBillList)
async def list_bills(company_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.vendor_bills(db, user, await svc.load_vendor(db, user, company_id, "vendor_bills_view"))


@router.post("/companies/{company_id}/vendor-bills", status_code=201, response_model=VendorBillEnvelope)
async def create_bill(company_id: UUID, payload: VendorBillCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    vendor = await svc.load_vendor(db, user, company_id, "vendor_bill_create", edit=True)
    bill = await svc.add_bill(db, user, vendor, payload)
    await db.commit()
    await db.refresh(bill)
    svc.log("vendor_bill_created", user, company_id=vendor.id, bill_id=bill.id)
    return {"bill": await svc.bill_out(db, user, bill)}


@router.post("/vendor-bills/{bill_id}/payments", status_code=201, response_model=VendorBillEnvelope)
async def record_payment(bill_id: UUID, payload: VendorBillPaymentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    bill = await svc.load_bill(db, user, bill_id, "vendor_bill_payment")
    payment = await svc.add_payment(db, user, bill, payload)
    await db.commit()
    await db.refresh(bill)
    svc.log("vendor_bill_payment_recorded", user, bill_id=bill.id, payment_id=payment.id)
    return {"bill": await svc.bill_out(db, user, bill)}


@router.post("/vendor-bills/{bill_id}/cancel", response_model=VendorBillEnvelope)
async def cancel_bill(bill_id: UUID, payload: VendorBillCancel, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    bill = await svc.load_bill(db, user, bill_id, "vendor_bill_cancel")
    await svc.cancel(db, user, bill, payload.reason)
    await db.commit()
    await db.refresh(bill)
    svc.log("vendor_bill_cancelled", user, bill_id=bill.id)
    return {"bill": await svc.bill_out(db, user, bill)}


@router.get("/vendors/performance", response_model=VendorPerformancePage)
async def performance(limit: int = Query(50, ge=1, le=100), offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.require_grant(db, user, "vendor_performance")
    return await svc.performance_page(db, user, limit, offset)


@router.get("/vendors/{company_id}/performance", response_model=VendorPerformanceDetail)
async def vendor_performance(company_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.performance_detail(db, user, await svc.load_vendor(db, user, company_id, "vendor_performance"))
