"""ccrm-027 test helpers: since DEC-SCOPE-259 (E3) a counselor/Admin reaches `enrolled` only through `PUT …/enrollment`. Tests that need
an enrolled application as a step confirm it the real way: an "Enrolment confirmation" document of the application, then the PUT."""

from datetime import date

from app.models import AgentStudent, User
from tests.agn009_helpers import mk_doc

ENROLL = "/api/v1/workflows/overseas/applications/{}/enrollment"


async def confirm_enrollment(client, db, app, *, expected_status: str = "offer"):
    """PUT the confirmation with `client` (already signed in) and return the response; the application must be at an offer stage."""
    record = await db.get(AgentStudent, app.agent_student_id) if app.agent_student_id else None
    student = await db.get(User, app.student_id) if record is None and app.student_id else None
    document = await mk_doc(db, record=record, student=student, application=app, document_type="Enrolment confirmation")
    body = {"expected_status": expected_status, "enrollment_date": date.today().isoformat(), "enrollment_document_id": str(document.id), "pre_enrollment_checklist_complete": True}
    return await client.put(ENROLL.format(app.id), json=body)
