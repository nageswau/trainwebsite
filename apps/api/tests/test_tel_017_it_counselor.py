"""tel-017 (DEC-SCOPE-076) -- the counselor role in the IT division; an IT counselor gets no overseas access (AC1-AC4)."""

import uuid

import pytest

from app.models import Enquiry
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


# --- AC2 / C1 -------------------------------------------------------------------------------------------------------------
async def _lead(db, division: str, owner, name: str, status: str = "new") -> Enquiry:
    row = Enquiry(division=division, name=name, email=email("lead"), subject="Full Stack", message="x", owner_id=owner.id if owner else None, status=status)
    db.add(row)
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_it_counselor_sees_only_it_leads_routed_to_them(client, db_session):
    me, other = await make_user(db_session, "counselor", "it"), await make_user(db_session, "counselor", "it")
    tag = uuid.uuid4().hex[:6]
    await _lead(db_session, "it", me, f"Mine {tag}")
    await _lead(db_session, "it", me, f"Mine contacted {tag}", status="contacted")
    await _lead(db_session, "it", other, f"Theirs {tag}")
    await _lead(db_session, "it", None, f"Unrouted {tag}")
    await _lead(db_session, "overseas", me, f"Overseas {tag}")
    await login(client, me)
    leads = await client.get("/api/v1/portal/it/counselor/leads")
    assert leads.status_code == 200, leads.text
    assert leads.json()["title"] == "My Leads"
    assert {r["name"] for r in leads.json()["rows"]} == {f"Mine {tag}", f"Mine contacted {tag}"}
    dash = await client.get("/api/v1/portal/it/counselor/dashboard")
    assert dash.status_code == 200, dash.text
    assert {m["label"]: m["value"] for m in dash.json()["metrics"]} == {"Leads routed to you": 2, "New leads": 1}
    assert {r["name"] for r in dash.json()["rows"]} == {f"Mine {tag}", f"Mine contacted {tag}"}


@pytest.mark.asyncio
async def test_it_counselor_with_no_leads_gets_empty_sections(client, db_session):
    await login(client, await make_user(db_session, "counselor", "it"))
    leads = await client.get("/api/v1/portal/it/counselor/leads")
    assert leads.status_code == 200 and leads.json()["rows"] == []
    dash = await client.get("/api/v1/portal/it/counselor/dashboard")
    assert {m["label"]: m["value"] for m in dash.json()["metrics"]} == {"Leads routed to you": 0, "New leads": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["students", "documents", "applications", "school-applications", "visa", "appointments", "counselor-chat", "reports"])
async def test_it_counselor_has_no_overseas_sections(client, db_session, section):
    await login(client, await make_user(db_session, "counselor", "it"))
    assert (await client.get(f"/api/v1/portal/it/counselor/{section}")).status_code == 404


# --- AC3 / AC4: each counselor's portal refuses the other division --------------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_portals_refuse_the_other_division(client, db_session):
    await login(client, await make_user(db_session, "counselor", "it"))
    assert (await client.get("/api/v1/portal/overseas/counselor/dashboard")).status_code == 403
    await login(client, await make_user(db_session, "counselor", "overseas"))
    assert (await client.get("/api/v1/portal/it/counselor/leads")).status_code == 403


@pytest.mark.asyncio
async def test_overseas_counselor_leads_still_ignore_it_leads(client, db_session):
    me = await make_user(db_session, "counselor", "overseas")
    tag = uuid.uuid4().hex[:6]
    await _lead(db_session, "overseas", me, f"Overseas mine {tag}")
    await _lead(db_session, "it", me, f"IT stray {tag}")
    await login(client, me)
    response = await client.get("/api/v1/portal/overseas/counselor/leads")
    assert response.status_code == 200
    assert {r["name"] for r in response.json()["rows"]} == {f"Overseas mine {tag}"}
