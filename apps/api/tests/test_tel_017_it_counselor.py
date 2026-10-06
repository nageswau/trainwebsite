"""tel-017 (DEC-SCOPE-076) -- the counselor role in the IT division; an IT counselor gets no overseas access (AC1-AC4)."""

import uuid

import pytest

from tests.bdm001_helpers import USERS, email, login, make_user

ZERO = uuid.UUID(int=0)


def _counselor_payload(division: str) -> dict:
    return {"role": "counselor", "division": division, "email": email("cns"), "full_name": "Kavya Counselor"}


# --- AC1 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "division", "target"),
    [("it_admin", "it", "it"), ("super_admin", "global", "it"), ("overseas_admin", "overseas", "overseas"), ("super_admin", "global", "overseas")],
)
async def test_admin_creates_a_counselor_in_its_division(client, db_session, role, division, target):
    await login(client, await make_user(db_session, role, division))
    response = await client.post(USERS, json=_counselor_payload(target))
    assert response.status_code == 201, response.text
    assert (response.json()["role"], response.json()["division"]) == ("counselor", target)


@pytest.mark.asyncio
async def test_overseas_admin_still_cannot_create_an_it_counselor(client, db_session):
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await client.post(USERS, json=_counselor_payload("it"))).status_code == 403


# --- AC3 ------------------------------------------------------------------------------------------------------------------
# Every counselor-admitting overseas route (workflows.py's 14 plus the 9 role-only gates). A nil id is enough: the division gate
# refuses before any row is read, so no fixture rows are needed. Bodies are valid, so FastAPI's own 422 can't mask the gate.
OVERSEAS_ROUTES = [
    ("POST", "/api/v1/workflows/overseas/applications", {"student_id": str(ZERO), "university_id": str(ZERO), "intake": "Fall 2027"}),
    ("GET", "/api/v1/workflows/overseas/applications", None),
    ("PATCH", f"/api/v1/workflows/overseas/applications/{ZERO}", {"status": "enquiry"}),
    ("POST", f"/api/v1/workflows/overseas/applications/{ZERO}/advance", {"to_status": "eligibility_evaluation"}),
    ("GET", f"/api/v1/workflows/overseas/applications/{ZERO}/status", None),
    ("POST", "/api/v1/workflows/overseas/documents", {"student_id": str(ZERO), "document_type": "passport", "file_url": "local://p.pdf"}),
    ("PATCH", f"/api/v1/workflows/overseas/documents/{ZERO}/verify", {"verification_status": "verified"}),
    ("GET", f"/api/v1/workflows/overseas/documents/{ZERO}/download", None),
    ("GET", f"/api/v1/workflows/overseas/applications/{ZERO}/visa-checklist", None),
    ("GET", f"/api/v1/workflows/overseas/applications/{ZERO}/visa-status", None),
    ("PATCH", f"/api/v1/workflows/overseas/visa/{ZERO}", {"status": "submitted"}),
    ("POST", "/api/v1/workflows/overseas/visa", {"application_id": str(ZERO)}),
    ("POST", "/api/v1/workflows/overseas/appointments", {"student_id": str(ZERO), "scheduled_at": "2027-01-01T10:00:00Z", "appointment_type": "counselling"}),
    ("PATCH", f"/api/v1/workflows/overseas/appointments/{ZERO}", {"status": "completed"}),
    ("GET", "/api/v1/overseas-admin/school-students/lookup?code=STU-0001", None),
    ("POST", f"/api/v1/overseas-admin/school-students/{ZERO}/applications", {"university_id": str(ZERO), "intake": "Fall 2027"}),
    ("GET", "/api/v1/overseas-admin/school-applications", None),
    ("GET", "/api/v1/lookups/overseas-students", None),
    ("GET", "/api/v1/lookups/overseas-applications", None),
    ("GET", "/api/v1/lookups/schools", None),
    ("GET", f"/api/v1/lookups/school-students?school_id={ZERO}", None),
    ("GET", "/api/v1/inbound/university-email", None),
    ("PATCH", f"/api/v1/inbound/university-email/{ZERO}/match", {"application_id": str(ZERO)}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path", "body"), OVERSEAS_ROUTES, ids=[f"{m} {p.split('?')[0]}" for m, p, _ in OVERSEAS_ROUTES])
async def test_every_overseas_counselor_route_refuses_an_it_counselor(client, db_session, method, path, body):
    await login(client, await make_user(db_session, "counselor", "it"))
    response = await client.request(method, path, json=body)
    assert response.status_code == 403, response.text
