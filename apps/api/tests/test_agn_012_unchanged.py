"""AGN-012 AC10 -- the counselor/admin/student visa routes and responses are unchanged on a case that carries the new columns (V8)."""

from datetime import UTC, date, datetime

import pytest

from app.models import OverseasApplication
from tests.agn001_helpers import client_for, mk_user
from tests.agn003_helpers import mk_university
from tests.agn012_helpers import mk_case

BASE = "/api/v1/workflows/overseas"


@pytest.mark.asyncio
async def test_student_and_admin_responses_keep_their_keys(db_session):
    student = await mk_user(db_session, role="overseas_student")
    admin = await mk_user(db_session, role="overseas_admin")
    university = await mk_university(db_session)
    app = OverseasApplication(student_id=student.id, university_id=university.id, status="visa_documentation", intake="Sep 2027")
    db_session.add(app)
    await db_session.commit()
    case = await mk_case(
        db_session, app, status="documentation", checklist=["Passport"], visa_application_date=date(2027, 5, 1), interview_date=date(2027, 5, 9), decision="approved", decided_at=datetime.now(UTC)
    )
    async with client_for(student.email) as c:
        checklist = (await c.get(f"{BASE}/applications/{app.id}/visa-checklist")).json()
        status = (await c.get(f"{BASE}/applications/{app.id}/visa-status")).json()
    assert set(checklist) == {"exists", "id", "status", "appointment_date", "tracking_reference", "checklist"}
    assert set(status) == {"exists", "status", "appointment_date", "tracking_reference", "disclaimer"}
    async with client_for(admin.email) as c:
        r = await c.patch(f"{BASE}/visa/{case.id}", json={"status": "checklist"})  # the old route still allows a backward move
        assert (r.status_code, set(r.json())) == (200, {"id", "status"})
        assert (await c.post(f"{BASE}/visa", json={"application_id": str(app.id)})).status_code == 409
