"""AGN-023 AC09-AC14 -- a counselor on an agency application keeps to the agency's rules (spec §4); the agency sees the name (§6)."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentCommission
from tests.agn001_helpers import client_for
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import APPS, mk_application
from tests.agn009_helpers import mk_doc
from tests.agn012_helpers import case_of, mk_case, verified
from tests.agn023_helpers import ADVANCE, ASSIGN, PORTAL, assign_world, fresh

VISA = "/api/v1/workflows/overseas/visa"


async def _assigned(db, *, status="offer"):
    w = await assign_world(db, status=status)
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    return w


@pytest_asyncio.fixture
async def world(db_session):
    return await _assigned(db_session)


@pytest.mark.asyncio
async def test_the_counselor_cannot_enroll_an_agency_application(db_session, world):  # AC09
    async with client_for(world["counselor"].email) as c:
        r = await c.post(ADVANCE.format(world["app"].id), json={"to_status": "enrolled"})
        assert r.status_code == 403 and r.json()["detail"] == "Only the agency's Master confirms enrollment"
        assert (await c.post(ADVANCE.format(world["app"].id), json={"to_status": "visa_documentation"})).status_code == 200
    assert (await fresh(db_session, world["app"])).status == "visa_documentation"
    count = await db_session.scalar(select(func.count()).select_from(AgentCommission).where(AgentCommission.application_id == world["app"].id))
    assert count == 0


@pytest.mark.asyncio
async def test_a_direct_application_can_still_be_enrolled_by_its_counselor(db_session, world):  # AC11
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(ADVANCE.format(world["direct_app"].id), json={"to_status": "enrolled"})).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "code", "detail"), [("enquiry", 422, "An offer is needed before a visa case"), ("enrolled", 409, "This application is enrolled, so its visa case can no longer be changed")])
async def test_an_agency_visa_case_needs_an_offer_and_an_open_application(db_session, status, code, detail):  # AC10
    w = await _assigned(db_session)
    app = await fresh(db_session, w["app"])
    app.status = status
    await db_session.commit()
    async with client_for(w["counselor"].email) as c:
        r = await c.post(VISA, json={"application_id": str(w["app"].id), "checklist": ["Passport"]})
    assert r.status_code == code and r.json()["detail"] == detail
    assert await case_of(db_session, w["app"]) is None


@pytest.mark.asyncio
async def test_an_agency_visa_case_starts_at_the_checklist(db_session, world):  # AC10
    async with client_for(world["counselor"].email) as c:
        r = await c.post(VISA, json={"application_id": str(world["app"].id), "status": "documentation", "checklist": ["Passport"]})
        assert r.status_code == 422 and r.json()["detail"] == "A visa case starts at the checklist stage"
        assert (await c.post(VISA, json={"application_id": str(world["app"].id), "checklist": ["Passport"]})).status_code == 201


@pytest.mark.asyncio
async def test_agency_visa_updates_follow_the_agency_rules(db_session, world):  # AC10, Review Focus 3
    case = await mk_case(db_session, world["app"], checklist=["Passport"])
    async with client_for(world["counselor"].email) as c:
        gate = await c.patch(f"{VISA}/{case.id}", json={"status": "documentation"})
        assert gate.status_code == 422 and "not yet verified: Passport" in gate.json()["detail"]
        await verified(db_session, world, "Passport")
        assert (await c.patch(f"{VISA}/{case.id}", json={"status": "interview_prep"})).status_code == 200  # a skip, as the agency may
        back = await c.patch(f"{VISA}/{case.id}", json={"status": "documentation"})
        assert back.status_code == 422 and back.json()["detail"] == "A visa case can only move forward"
        locked = await c.patch(f"{VISA}/{case.id}", json={"checklist": ["Passport", "CV"]})
        assert locked.status_code == 422 and locked.json()["detail"] == "The checklist can only be changed at the checklist stage"
        refused = await c.patch(f"{VISA}/{case.id}", json={"decision": "approved"})
        assert refused.status_code == 422 and refused.json()["detail"] == "The visa decision is recorded by the agency"
    row = await case_of(db_session, world["app"])
    row.status, row.decision, row.decided_at = "decision", "approved", datetime.now(UTC)
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        decided = await c.patch(f"{VISA}/{case.id}", json={"tracking_reference": "TR-1"})
        assert decided.status_code == 409 and decided.json()["detail"] == "The visa decision is recorded, so this case can no longer be changed"
        checklist = (await c.get(f"/api/v1/workflows/overseas/applications/{world['app'].id}/visa-checklist")).json()
    assert checklist["locked_reason"] == "The visa decision is recorded, so this case can no longer be changed"


@pytest.mark.asyncio
async def test_a_direct_visa_case_keeps_todays_behavior(db_session, world):  # AC11
    case = await mk_case(db_session, world["direct_app"], status="documentation")
    async with client_for(world["counselor"].email) as c:
        assert (await c.patch(f"{VISA}/{case.id}", json={"status": "checklist"})).status_code == 200  # no forward-only rule outside agencies
        checklist = (await c.get(f"/api/v1/workflows/overseas/applications/{world['direct_app'].id}/visa-checklist")).json()
    assert checklist["locked_reason"] is None


@pytest.mark.asyncio
async def test_the_documents_queue_lists_agency_documents_of_a_no_login_student(db_session, world):  # AC12
    doc = await mk_doc(db_session, record=world["record"], application=world["app"])
    async with client_for(world["counselor"].email) as c:
        rows = (await c.get(PORTAL.format("counselor", "documents"))).json()["rows"]
        assert {"id": str(doc.id), "student": world["record"].full_name} in [{"id": str(r["id"]), "student": r["student"]} for r in rows]
        r = await c.patch(f"/api/v1/workflows/overseas/documents/{doc.id}/verify", json={"verification_status": "rejected", "notes": "Blurred"})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_counselor_responses_carry_no_agency_contact_or_counseling_data(db_session, world):  # AC13
    email, phone = "private-agn023@example.local", "+910000023023"
    record = await mk_record(db_session, agent=world["master"], full_name="Contact Student", email=email, phone=phone)
    app = await mk_application(db_session, agent=world["master"], university=world["university"], record=record, status="offer")
    async with client_for(world["admin"].email) as c:
        assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(world["counselor"].id)})).status_code == 200
    async with client_for(world["counselor"].email) as c:
        bodies = [(await c.get(PORTAL.format("counselor", s))).text for s in ("dashboard", "students", "applications", "documents", "visa")]
        bodies.append((await c.get("/api/v1/lookups/overseas-applications", params={"q": "Contact"})).text)
        bodies.append((await c.get(f"/api/v1/workflows/overseas/applications/{app.id}/visa-checklist")).text)
    for body in bodies:
        assert email not in body and phone not in body
        assert "budget" not in body.lower() and "shortlist" not in body.lower()


@pytest.mark.asyncio
async def test_the_agency_detail_shows_the_counselor_name_only(db_session, world):  # AC14
    async with client_for(world["master"].email) as c:
        detail = (await c.get(f"{APPS}/{world['app'].id}")).json()["application"]
    assert detail["counselor_name"] == world["counselor"].full_name
    assert world["counselor"].email not in str(detail)
    other = await mk_application(db_session, agent=world["master"], university=world["university"], record=world["record"], status="enquiry")
    async with client_for(world["master"].email) as c:
        assert (await c.get(f"{APPS}/{other.id}")).json()["application"]["counselor_name"] is None
