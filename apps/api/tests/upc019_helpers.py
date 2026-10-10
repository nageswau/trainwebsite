"""upc-019 fixtures: a fresh university per test (the shared test DB is never truncated), its courses, in-force agreements with commission
terms, and enrolled applications -- all built directly, so the Expected rules (spec CL1-CL8) are tested without the agreement workflow."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import (
    ApplicationStatusHistory,
    OverseasApplication,
    OverseasCourse,
    UniversityAgreement,
    UniversityCommissionTerm,
    UniversityDocument,
    User,
    VisaCase,
)
from tests.bdm001_helpers import make_user

JAN_15 = datetime(2026, 1, 15, 6, tzinfo=UTC)  # 15 Jan 2026 IST


async def staff(db) -> User:
    return await make_user(db, "partnership_head", "global")


async def tuition_course(db, university, *, amount: str | None = "18000", currency: str | None = "GBP", title: str = "MSc Data Science") -> OverseasCourse:
    row = OverseasCourse(
        university_id=university.id, title=title, level="PG", category="Tech", duration="1 year", tuition_fee=f"{currency} {amount}", intake="Jan",
        tuition_amount=Decimal(amount) if amount else None, tuition_currency=currency,
    )  # fmt: skip
    db.add(row)
    await db.commit()
    return row


async def agreement(db, university, by: User, *, status: str = "active", start: date = date(2025, 6, 1), expiry: date = date(2028, 6, 1)) -> UniversityAgreement:
    """An agreement in `status`; the signed-row CHECK needs its document and both signatories."""
    doc = UniversityDocument(university_id=university.id, kind="mou", title=f"MoU {uuid.uuid4().hex[:6]}", shareable=False, created_by_user_id=by.id)
    db.add(doc)
    await db.flush()
    row = UniversityAgreement(
        mou_number=f"T{uuid.uuid4().hex[:10]}", university_id=university.id, agreement_type="mou", status=status, start_date=start, expiry_date=expiry,
        exclusivity="exclusive", course_ids=[], country_ids=[], document_id=doc.id, edusphere_signatory_user_id=by.id, edusphere_signed_on=start,
        university_signatory_name="Registrar", university_signed_on=start, created_by_user_id=by.id,
    )  # fmt: skip
    db.add(row)
    await db.commit()
    return row


async def term(
    db, agreement_row, by: User, *, percent: str | None = "15", fixed: str | None = None, currency: str = "GBP", trigger: str = "enrolment", courses=(), countries=(), when: datetime | None = None
) -> UniversityCommissionTerm:
    row = UniversityCommissionTerm(
        agreement_id=agreement_row.id, commission_percent=Decimal(percent) if percent else None, fixed_amount=Decimal(fixed) if fixed else None,
        currency=currency, trigger=trigger, course_ids=[str(c.id) for c in courses], country_ids=[str(c) for c in countries],
        created_by_user_id=by.id, updated_by_user_id=by.id, **({"created_at": when} if when else {}),
    )  # fmt: skip
    db.add(row)
    await db.commit()
    return row


async def enrolled(db, university, course=None, *, at: datetime | None = JAN_15, status: str = "enrolled", intake: str = "Jan 2026", **fields) -> OverseasApplication:
    """An application of the university; `at` is its first status-history entry into enrolled (None = no history row)."""
    row = OverseasApplication(university_id=university.id, course_id=course.id if course else None, status=status, intake=intake, **fields)
    db.add(row)
    await db.flush()
    if at is not None:
        db.add(ApplicationStatusHistory(application_id=row.id, from_status="status_tracking", to_status="enrolled", created_at=at))
    await db.commit()
    return row


async def approved_visa(db, app, decision: str = "approved") -> None:
    db.add(VisaCase(application_id=app.id, decision=decision, decided_at=JAN_15))
    await db.commit()
