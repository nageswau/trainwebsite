"""ccrm-027 (DEC-SCOPE-262): an application's enrolment confirmation -- the document type, the checks and the read view behind the
counselor/Admin routes in api/application_offers.py. Nothing here commits: the route scopes, locks, notifies, audits and commits.
Spec: docs/superpowers/specs/2026-10-25-ccrm-027-enrolment-confirmation-design.md."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OverseasApplication, StudentDocument
from app.services.agent_applications import ENROLLABLE, OFFER_NEEDED
from app.services.application_offers import document_view

CONFIRMATION = "Enrolment confirmation"
DOCUMENT_MISMATCH = "Choose an enrolment confirmation uploaded for this application"
# The fields the save writes, in the order a correction's audit lists them.
FIELDS = ("enrollment_date", "university_student_id", "course_start_date", "enrollment_document_id", "pre_enrollment_checklist_complete")


async def check(db: AsyncSession, app: OverseasApplication, document_id) -> None:
    """E2: from an offer onwards (once enrolled the save is a correction), with this application's confirmation document."""
    if app.status != "enrolled" and app.status not in ENROLLABLE:
        raise HTTPException(422, OFFER_NEEDED)
    document = await db.get(StudentDocument, document_id)
    if document is None or document.application_id != app.id or document.document_type != CONFIRMATION or document.archived_at is not None:
        raise HTTPException(422, DOCUMENT_MISMATCH)


async def view(db: AsyncSession, app: OverseasApplication) -> dict:
    document = await db.get(StudentDocument, app.enrollment_document_id) if app.enrollment_document_id else None
    return {
        "status": app.status,
        "confirmed": app.enrollment_confirmed_at is not None,
        "confirmed_at": app.enrollment_confirmed_at,
        "can_confirm": app.status in ENROLLABLE,
        **{name: getattr(app, name) for name in FIELDS if name != "enrollment_document_id"},
        "document": document_view(document) if document else None,
    }
