"""ccrm-025 (DEC-SCOPE-255, D2): the counselor's record of an application's university deposit -- any currency, no payment taken, one
per application. The only writer of `application_deposit_records`; AGN-011's `application_deposits` (agency, INR, Razorpay) is read
only, to refuse a second deposit beside it. Nothing here commits: the route scopes, locks the application row, writes history, notifies,
audits and commits. Spec: docs/superpowers/specs/2026-10-24-ccrm-025-offer-decisions-deposits-design.md §3.3.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import ApplicationDeposit, ApplicationDepositRecord, ApplicationOffer, OverseasApplication, StudentDocument, User
from app.services.application_offers import document_view, money

FIELDS = ("required", "amount", "currency", "due_date", "payment_status", "paid_on", "receipt_document_id")
STATUS_LABELS = {"not_required": "Not required", "pending": "Pending", "paid_to_university": "Paid directly to the university", "paid_via_edusphere": "Paid via EduSphere"}
RECEIPT = "Deposit receipt"
AGENCY_MANAGED = "The agency pays this deposit through EduSphere -- it is shown read-only"
RECEIPT_MISMATCH = "Choose a deposit receipt uploaded for this application"
NO_REQUIRED_DEPOSIT = "Record a required deposit on the application first"  # ccrm-048


async def record_for(db: AsyncSession, application_id) -> ApplicationDepositRecord | None:
    return await db.scalar(select(ApplicationDepositRecord).where(ApplicationDepositRecord.application_id == application_id))


async def agency_deposit(db: AsyncSession, application_id) -> dict | None:
    """The AGN-011 deposit, read-only: what the counselor needs to see, not its payments."""
    row = await db.scalar(select(ApplicationDeposit).where(ApplicationDeposit.application_id == application_id))
    return {"status": row.status, "amount": money(row.amount), "currency": row.currency, "due_date": row.due_date} if row else None


def values_of(record: ApplicationDepositRecord | None) -> dict | None:
    return {field: getattr(record, field) for field in FIELDS} if record else None


def save(user: User, app: OverseasApplication, record: ApplicationDepositRecord | None, values: dict) -> ApplicationDepositRecord:
    """Create the record or replace its values (the caller has validated them and checked the receipt)."""
    if record is None:
        record = ApplicationDepositRecord(application_id=app.id, recorded_by_id=user.id)
    for field in FIELDS:
        setattr(record, field, values[field])
    record.updated_by_id = user.id
    return record


def summary(record: ApplicationDepositRecord) -> str:
    """The history note: status, amount and due date (the receipt stays on the record)."""
    if not record.required:
        return "Deposit: not required."
    text = f"Deposit: {STATUS_LABELS[record.payment_status]}, {record.currency} {money(record.amount)}"
    if record.due_date:
        text += f", due {record.due_date.isoformat()}"
    if record.paid_on:
        text += f", paid {record.paid_on.isoformat()}"
    return text + "."


def prefill(offer: ApplicationOffer | None) -> dict | None:
    """The current offer's deposit, to start a new record from."""
    if offer is None or offer.deposit_amount is None:
        return None
    return {"amount": money(offer.deposit_amount), "currency": offer.currency, "due_date": offer.deposit_deadline}


_Updater = aliased(User)


async def view(db: AsyncSession, application_id) -> dict | None:
    """The record with its receipt's id and name (never `file_url`) and who last changed it."""
    row = (
        await db.execute(
            select(ApplicationDepositRecord, StudentDocument, _Updater.full_name)
            .outerjoin(StudentDocument, StudentDocument.id == ApplicationDepositRecord.receipt_document_id)
            .outerjoin(_Updater, _Updater.id == ApplicationDepositRecord.updated_by_id)
            .where(ApplicationDepositRecord.application_id == application_id)
        )
    ).first()
    if row is None:
        return None
    record, receipt, updater = row
    return {
        "id": record.id,
        "required": record.required,
        "amount": money(record.amount),
        "currency": record.currency,
        "due_date": record.due_date,
        "payment_status": record.payment_status,
        "payment_status_label": STATUS_LABELS[record.payment_status],
        "paid_on": record.paid_on,
        "receipt": document_view(receipt) if receipt else None,
        "updated_by": updater,
        "updated_at": record.updated_at,
    }
