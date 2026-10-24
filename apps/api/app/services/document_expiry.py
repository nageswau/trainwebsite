"""ccrm-021 (DEC-SCOPE-251 S4) -- the daily job that marks documents past their expiry date as `expired`.

A document expires the day after its expiry date (India calendar). Archived versions and `not_required` documents are left alone. Each
change writes an `expired` history event with no actor. Rows are locked SKIP LOCKED, so an overlapping run or a concurrent review never
waits or double-writes; a rerun finds nothing left to do.
"""

import logging
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StudentDocument
from app.services import application_checklists
from app.services.agent_documents import add_event

logger = logging.getLogger("app.document_expiry")
INDIA = ZoneInfo("Asia/Kolkata")
UNTOUCHED = ("expired", "not_required")


async def expire_documents(db: AsyncSession, today: date) -> int:
    """Marks every current document whose expiry date is before `today`; returns how many."""
    rows = (
        await db.scalars(
            select(StudentDocument)
            .where(
                StudentDocument.archived_at.is_(None),
                StudentDocument.expiry_date < today,
                StudentDocument.verification_status.not_in(UNTOUCHED),
            )
            .with_for_update(skip_locked=True)
        )
    ).all()
    for document in rows:
        add_event(db, event="expired", actor=None, document=document, from_status=document.verification_status, to_status="expired")
        document.verification_status = "expired"
    await application_checklists.sync_for_documents(db, [d.id for d in rows])  # ccrm-019 AC9
    await db.commit()
    logger.info("documents_expired", extra={"extra_fields": {"day": today.isoformat(), "count": len(rows)}})
    return len(rows)


async def run_document_expiry() -> int:
    """The beat task's entry point: its own session, today's India date."""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await expire_documents(db, datetime.now(UTC).astimezone(INDIA).date())
