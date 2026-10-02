"""AGN-008 AC04, AC15 (edit) -- PATCH editable fields; university fixed; course re-checks; withdrawn/archived 409."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import ApplicationStatusHistory, AuditLog, OverseasApplication, OverseasCourse
from tests.agn001_helpers import client_for
from tests.agn008_helpers import APPS, agency_world, mk_application


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    course = OverseasCourse(university_id=w["university"].id, title="MSc Data", level="PG", category="x", duration="1y", tuition_fee="1", intake="Sep")
    db_session.add(course)
    await db_session.commit()
    w["course"] = course
    w["app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    return w


@pytest.mark.asyncio
async def test_staff_edits_fields_and_null_clears(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        r = await c.patch(
            f"{APPS}/{world['app'].id}",
            json={
                "application_reference": "APP-9",
                "intake": "Spring 2028",
                "submitted_on": "2026-09-10",
                "application_deadline": "2026-12-01",
                "offer_deadline": "2027-02-01",
                "next_action": "Chase SOP",
                "course_id": str(world["course"].id),
            },
        )
        assert r.status_code == 200, r.text
        r2 = await c.patch(f"{APPS}/{world['app'].id}", json={"application_reference": None})
    body = r2.json()["application"]
    assert body["application_reference"] is None and body["intake"] == "Spring 2028" and body["course"] == "MSc Data"
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "overseas.application.update", AuditLog.entity_id == str(world["app"].id)).order_by(AuditLog.created_at))).all()
    assert audit[0].metadata_json["fields"] == sorted(["application_reference", "intake", "submitted_on", "application_deadline", "offer_deadline", "next_action", "course_id"])
    history = (await db_session.scalars(select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == world["app"].id))).all()
    assert [(h.from_status, h.to_status, h.next_action) for h in history] == [("enquiry", "enquiry", "Chase SOP")]


@pytest.mark.asyncio
async def test_no_change_writes_nothing(db_session, world):
    async with client_for(world["master"].email) as c:
        assert (await c.patch(f"{APPS}/{world['app'].id}", json={"intake": "Fall 2027"})).status_code == 200
    assert (await db_session.scalars(select(AuditLog).where(AuditLog.action == "overseas.application.update", AuditLog.entity_id == str(world["app"].id)))).all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"university_id": str(uuid.uuid4())}, {"status": "offer"}, {"agent_id": str(uuid.uuid4())}, {"intake": ""}])
async def test_forbidden_or_invalid_fields_are_422(world, body):
    async with client_for(world["master"].email) as c:
        assert (await c.patch(f"{APPS}/{world['app'].id}", json=body)).status_code == 422


@pytest.mark.asyncio
async def test_course_change_rechecks_duplicate(db_session, world):
    await mk_application(db_session, agent=world["master"], university=world["university"], record=world["record"], course_id=world["course"].id, intake="Other")
    async with client_for(world["master"].email) as c:
        r = await c.patch(f"{APPS}/{world['app'].id}", json={"course_id": str(world["course"].id)})
    assert r.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(("setup", "detail"), [("withdrawn", "This application is withdrawn"), ("archived", "Unarchive this student first")])
async def test_closed_application_is_409(db_session, world, setup, detail):
    if setup == "withdrawn":
        row = await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)
        row.status = "withdrawn"
    else:
        world["record"].status = "archived"
        db_session.add(world["record"])
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await c.patch(f"{APPS}/{world['app'].id}", json={"intake": "X"})
    assert r.status_code == 409 and r.json()["detail"] == detail


@pytest.mark.asyncio
async def test_other_staff_edit_is_404(world):
    async with client_for(world["other_staff"]["user"].email) as c:
        assert (await c.patch(f"{APPS}/{world['app'].id}", json={"intake": "X"})).status_code == 404
