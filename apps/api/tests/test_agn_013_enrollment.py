"""AGN-013 AC01-AC06, AC08 -- a Master confirms enrollment once; corrections never duplicate the commission; refusals write nothing."""

import logging

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentCommission, ApplicationStatusHistory, AuditLog, OverseasApplication
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import APPS, agency_world, mk_application

COMMISSIONS = "/api/v1/workflows/overseas/agent/commissions"


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"], status="offer", intake="Sep 2027")
    return w


def _body(expected="offer", **over):
    return {"enrollment_date": "2027-09-20", "university_student_id": "S-123", "expected_status": expected, **over}


async def _put(c, app_id, body):
    return await c.put(f"{APPS}/{app_id}/enrollment", json=body)


async def _set(db, world, **fields):
    row = await db.get(OverseasApplication, world["app"].id, populate_existing=True)
    for key, value in fields.items():
        setattr(row, key, value)
    await db.commit()


async def _rows(db, model, app_id) -> int:
    where = AuditLog.entity_id == str(app_id) if model is AuditLog else model.application_id == app_id
    return await db.scalar(select(func.count()).select_from(model).where(where))


async def _assert_untouched(db, world, status):
    row = await db.get(OverseasApplication, world["app"].id, populate_existing=True)
    assert (row.status, row.enrollment_date, row.university_student_id, row.enrollment_confirmed_at) == (status, None, None, None)
    for model in (ApplicationStatusHistory, AgentCommission, AuditLog):
        assert await _rows(db, model, world["app"].id) == 0, model


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["offer", "visa_documentation", "status_tracking"])
async def test_master_confirms_and_one_estimated_commission_is_created(db_session, world, stage):
    await _set(db_session, world, status=stage)
    async with client_for(world["master"].email) as c:
        r = await _put(c, world["app"].id, _body(stage, notes="Joined in person"))
        assert r.status_code == 200, r.text
        a = r.json()["application"]
        assert (a["status"], a["enrollment_date"], a["university_student_id"], a["enrollment_check"]) == ("enrolled", "2027-09-20", "S-123", None)
        assert a["enrollment_confirmed_at"]
        assert [(h["from_status"], h["to_status"], h["notes"]) for h in a["history"]] == [(stage, "enrolled", "Joined in person")]
        listed = (await c.get(COMMISSIONS)).json()
    item = (await db_session.scalars(select(AgentCommission).where(AgentCommission.application_id == world["app"].id))).one()
    assert (item.status, float(item.amount), item.created_by, item.agent_id) == ("estimated", 0.0, "system_trigger", world["master"].id)
    assert str(item.id) in str(listed)  # every Master of the org sees it (E3)
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id.in_([str(world["app"].id), str(item.id)])))).all()
    assert sorted(actions) == ["agent.commission_auto_create", "overseas.application.enroll"]


@pytest.mark.asyncio
async def test_resaving_corrects_details_without_a_second_commission(db_session, world):
    async with client_for(world["master"].email) as c:
        first = await _put(c, world["app"].id, _body())
        assert first.status_code == 200
        r = await _put(c, world["app"].id, _body("enrolled", enrollment_date="2027-09-22", university_student_id=None))
        assert r.status_code == 200, r.text
        a = r.json()["application"]
        assert (a["enrollment_date"], a["university_student_id"]) == ("2027-09-22", None)
        assert a["enrollment_confirmed_at"] == first.json()["application"]["enrollment_confirmed_at"]  # the first confirmation stays
        assert (await _put(c, world["app"].id, _body("enrolled", enrollment_date="2027-09-22", university_student_id=None))).status_code == 200
    assert await _rows(db_session, AgentCommission, world["app"].id) == 1
    assert await _rows(db_session, ApplicationStatusHistory, world["app"].id) == 1
    updates = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "overseas.application.enrollment_update", AuditLog.entity_id == str(world["app"].id)))).all()
    assert [u.metadata_json for u in updates] == [{"fields": ["enrollment_date", "university_student_id"]}]  # the no-op save wrote nothing


@pytest.mark.asyncio
async def test_missing_date_is_422_and_writes_nothing(db_session, world):
    body = _body()
    del body["enrollment_date"]
    async with client_for(world["master"].email) as c:
        assert (await _put(c, world["app"].id, body)).status_code == 422
    await _assert_untouched(db_session, world, "offer")


@pytest.mark.asyncio
@pytest.mark.parametrize(("enrolled", "intake", "check"), [("2027-10-05", "Sep 2027", "after_intake"), ("2027-10-05", "Next intake", "intake_unrecognised"), ("2027-09-05", "Sep 2027", None)])
async def test_date_check_is_a_warning_not_a_block(db_session, world, enrolled, intake, check):
    await _set(db_session, world, intake=intake)
    async with client_for(world["master"].email) as c:
        r = await _put(c, world["app"].id, _body(enrollment_date=enrolled))
        assert r.status_code == 200 and r.json()["application"]["enrollment_check"] == check
        assert (await c.get(f"{APPS}/{world['app'].id}")).json()["application"]["enrollment_check"] == check


@pytest.mark.asyncio
async def test_staff_is_403_even_in_scope(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        r = await _put(c, world["app"].id, _body())
        assert r.status_code == 403 and r.json()["detail"] == "Only an agency Master can confirm enrollment"
        assert (await c.get(f"{APPS}/{world['app'].id}")).status_code == 200  # Staff still read it
    await _assert_untouched(db_session, world, "offer")


@pytest.mark.asyncio
async def test_other_org_master_is_404(db_session, world):
    async with client_for(world["other"]["master"].email) as c:
        assert (await _put(c, world["app"].id, _body())).status_code == 404
    await _assert_untouched(db_session, world, "offer")


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["counselor", "overseas_admin", "overseas_student"])
async def test_non_agents_are_403(db_session, world, role):
    user = await mk_user(db_session, role=role)
    async with client_for(user.email) as c:
        assert (await _put(c, world["app"].id, _body())).status_code == 403
    await _assert_untouched(db_session, world, "offer")


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client, db_session, world):
    assert (await _put(client, world["app"].id, _body())).status_code == 401
    await _assert_untouched(db_session, world, "offer")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setup", "code", "status"),
    [
        ("withdrawn", 409, "withdrawn"),
        ("archived", 409, "offer"),
        ("stale", 409, "offer"),
        ("enquiry", 422, "enquiry"),
        ("university_selection", 422, "university_selection"),
        ("University review", 422, "University review"),
    ],
)
async def test_refusals_write_nothing(db_session, world, setup, code, status):
    expected = "offer"
    if setup == "archived":
        world["record"].status = "archived"
        db_session.add(world["record"])
        await db_session.commit()
    elif setup == "stale":
        expected = "status_tracking"
    else:
        await _set(db_session, world, status=setup)
        expected = setup
    async with client_for(world["master"].email) as c:
        r = await _put(c, world["app"].id, _body(expected))
    assert r.status_code == code, r.text
    if code == 422:
        assert r.json()["detail"] == "An offer is needed before enrollment"
    await _assert_untouched(db_session, world, status)


@pytest.mark.asyncio
async def test_extra_fields_are_422(db_session, world):
    async with client_for(world["master"].email) as c:
        for extra in ({"status": "enrolled"}, {"agent_id": str(world["master"].id)}, {"university_id": str(world["university"].id)}):
            assert (await _put(c, world["app"].id, _body(**extra))).status_code == 422
    await _assert_untouched(db_session, world, "offer")


@pytest.mark.asyncio
async def test_master_adds_details_to_a_counselor_enrolled_application(db_session, world):
    await _set(db_session, world, status="enrolled")
    async with client_for(world["master"].email) as c:
        r = await _put(c, world["app"].id, _body("enrolled"))
    assert r.status_code == 200 and r.json()["application"]["enrollment_confirmed_at"]
    assert await _rows(db_session, AgentCommission, world["app"].id) == 0
    assert await _rows(db_session, ApplicationStatusHistory, world["app"].id) == 0


@pytest.mark.asyncio
async def test_status_route_still_refuses_enrolled(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await c.post(f"{APPS}/{world['app'].id}/status", json={"to_status": "enrolled", "expected_status": "offer"})
    assert r.status_code == 403
    await _assert_untouched(db_session, world, "offer")


@pytest.mark.asyncio
async def test_logs_and_audit_never_carry_the_student_id_or_notes(db_session, world, caplog):
    # alembic's fileConfig (run in-process by the migration tests) disables existing loggers; re-enable ours (test_agn_004_students.py precedent).
    logging.getLogger("app.agent_applications").disabled = False
    caplog.set_level(logging.INFO, logger="app.agent_applications")
    async with client_for(world["master"].email) as c:
        assert (await _put(c, world["app"].id, _body(university_student_id="SECRET-ID-9", notes="private note"))).status_code == 200
        assert (await _put(c, world["app"].id, _body("enrolled", university_student_id="SECRET-ID-10"))).status_code == 200
    records = [r for r in caplog.records if r.name == "app.agent_applications"]
    assert [r.msg for r in records] == ["agent_application_enrolled", "agent_application_enrollment_updated"]
    assert records[0].extra_fields["from_status"] == "offer" and records[1].extra_fields["fields"] == ["university_student_id"]
    metadata = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == str(world["app"].id)))).all()
    text = " ".join(str(r.extra_fields) for r in records) + str(metadata)
    assert "SECRET-ID" not in text and "private note" not in text
