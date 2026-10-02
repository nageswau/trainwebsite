"""AGN-008 AC01-AC03, AC14, AC15 create side -- POST creates an application of an agency student with or without a login."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.api import agent_applications as router_module
from app.models import ApplicationStatusHistory, AuditLog, Notification, OverseasApplication, OverseasCourse
from app.services import agent_applications as service
from tests.agn001_helpers import client_for
from tests.agn003_helpers import mk_university
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import APPS, agency_world, mk_application


@pytest_asyncio.fixture
async def world(db_session):
    return await agency_world(db_session)


def _body(w, **over):
    return {"agent_student_id": str(w["record"].id), "university_id": str(w["university"].id), "intake": "Fall 2027", **over}


async def _count(db, model, *where):
    return await db.scalar(select(func.count()).select_from(model).where(*where))


@pytest.mark.asyncio
async def test_master_creates_for_a_student_with_no_login(db_session, world):
    async with client_for(world["master"].email) as c:
        response = await c.post(APPS, json=_body(world, application_reference="UCAS-1", submitted_on="2026-09-01", offer_deadline="2027-01-15"))
    assert response.status_code == 201, response.text
    body = response.json()["application"]
    assert (body["status"], body["has_login"], body["application_reference"], body["submitted_on"]) == ("enquiry", False, "UCAS-1", "2026-09-01")
    row = await db_session.get(OverseasApplication, uuid.UUID(body["id"]), populate_existing=True)
    assert (row.agent_student_id, row.student_id, row.agent_id) == (world["record"].id, None, world["master"].id)
    history = (await db_session.scalars(select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == row.id))).all()
    assert [(h.from_status, h.to_status) for h in history] == [(None, "enquiry")]
    assert await _count(db_session, AuditLog, AuditLog.action == "overseas.application.create", AuditLog.entity_id == str(row.id)) == 1


@pytest.mark.asyncio
async def test_linked_student_gets_student_id_and_the_existing_notification(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        response = await c.post(APPS, json=_body(world, agent_student_id=str(world["linked_record"].id)))
    assert response.status_code == 201, response.text
    row = await db_session.get(OverseasApplication, uuid.UUID(response.json()["application"]["id"]), populate_existing=True)
    assert row.student_id == world["linked_user"].id and row.agent_id == world["staff"]["user"].id
    assert await _count(db_session, Notification, Notification.user_id == world["linked_user"].id, Notification.title == "Application created") == 1


@pytest.mark.asyncio
async def test_staff_cannot_create_for_an_unassigned_or_foreign_student(db_session, world):
    unassigned = await mk_record(db_session, agent=world["master"], full_name="Unassigned")
    foreign = await mk_record(db_session, agent=world["other"]["master"], full_name="Foreign")
    async with client_for(world["staff"]["user"].email) as c:
        for record in (unassigned, foreign):
            response = await c.post(APPS, json=_body(world, agent_student_id=str(record.id)))
            assert response.status_code == 404 and response.json()["detail"] == "Student not found"


@pytest.mark.asyncio
async def test_archived_student_is_409(db_session, world):
    archived = await mk_record(db_session, agent=world["master"], full_name="Archived", status="archived")
    async with client_for(world["master"].email) as c:
        response = await c.post(APPS, json=_body(world, agent_student_id=str(archived.id)))
    assert response.status_code == 409 and response.json()["detail"] == "Unarchive this student first"


@pytest.mark.asyncio
async def test_unknown_university_404_and_foreign_course_422(db_session, world):
    other_uni = await mk_university(db_session)
    course = OverseasCourse(university_id=other_uni.id, title="MSc", level="PG", category="x", duration="1y", tuition_fee="1", intake="Sep")
    db_session.add(course)
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        assert (await c.post(APPS, json=_body(world, university_id=str(uuid.uuid4())))).status_code == 404
        response = await c.post(APPS, json=_body(world, course_id=str(course.id)))
    assert response.status_code == 422 and response.json()["detail"] == "Course does not belong to selected university"


@pytest.mark.asyncio
async def test_duplicate_is_409_until_withdrawn(db_session, world):
    async with client_for(world["master"].email) as c:
        first = await c.post(APPS, json=_body(world))
        assert first.status_code == 201
        again = await c.post(APPS, json=_body(world))
        assert again.status_code == 409 and again.json()["detail"] == "An application for this university/course already exists"
        row = await db_session.get(OverseasApplication, uuid.UUID(first.json()["application"]["id"]), populate_existing=True)
        row.status = "withdrawn"
        await db_session.commit()
        assert (await c.post(APPS, json=_body(world))).status_code == 201


@pytest.mark.asyncio
async def test_legacy_linked_application_is_a_duplicate(db_session, world):
    await mk_application(db_session, agent=world["master"], university=world["university"], student=world["linked_user"])  # pre-AGN-008 row
    async with client_for(world["master"].email) as c:
        response = await c.post(APPS, json=_body(world, agent_student_id=str(world["linked_record"].id)))
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_throttle_429_with_retry_after_and_other_org_unaffected(db_session, world, monkeypatch):
    monkeypatch.setattr(service, "CREATE_LIMIT", 2)
    for _ in range(2):
        db_session.add(AuditLog(user_id=world["staff"]["user"].id, action="overseas.application.create", entity_type="overseas_application", entity_id=str(uuid.uuid4())))
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        response = await c.post(APPS, json=_body(world))
    assert response.status_code == 429 and int(response.headers["Retry-After"]) > 0
    assert response.json()["detail"] == "Too many applications created today -- try again later"
    other_record = await mk_record(db_session, agent=world["other"]["master"], full_name="Other Org Student")
    async with client_for(world["other"]["master"].email) as c:
        assert (await c.post(APPS, json=_body(world, agent_student_id=str(other_record.id)))).status_code == 201


def test_create_limit_is_200():
    assert service.CREATE_LIMIT == 200


@pytest.mark.asyncio
async def test_a_failure_before_commit_leaves_nothing(db_session, world, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("notification store down")

    monkeypatch.setattr(router_module, "_notify_user", boom)
    async with client_for(world["master"].email) as c:
        with pytest.raises(RuntimeError):
            await c.post(APPS, json=_body(world, agent_student_id=str(world["linked_record"].id)))
    assert await _count(db_session, OverseasApplication, OverseasApplication.agent_student_id == world["linked_record"].id) == 0
    assert await _count(db_session, AuditLog, AuditLog.action == "overseas.application.create", AuditLog.user_id == world["master"].id) == 0


@pytest.mark.asyncio
async def test_create_is_logged_without_personal_data(world, caplog):
    import logging

    logging.getLogger("app.agent_applications").disabled = False
    caplog.set_level(logging.INFO, logger="app.agent_applications")
    async with client_for(world["master"].email) as c:
        await c.post(APPS, json=_body(world, application_reference="SECRET-REF"))
    record = next(r for r in caplog.records if r.getMessage() == "agent_application_created")
    assert set(record.extra_fields) >= {"org_id", "actor_id", "application_id"} and "SECRET-REF" not in str(record.extra_fields)
