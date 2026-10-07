"""AGN-023 final whole-branch review fixes: C1 (the generic PATCH refuses a counselor on an agency application), I1 (withdrawn/archived
agency applications), I2 (a typed agency visa body), I4 (scope re-checked under the row lock), I3 (school-bridged rows carry the assign
column), M1 (no assign control on closed rows)."""

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.api import workflows
from app.core.database import SessionLocal
from app.models import AgentCommission, AgentStudent, AuditLog, OverseasApplication
from tests.agn001_helpers import client_for
from tests.agn008_helpers import mk_application, mk_school_student
from tests.agn012_helpers import case_of, mk_case
from tests.agn023_helpers import ADVANCE, ASSIGN, PORTAL, UPDATE, assign_world, fresh

VISA = "/api/v1/workflows/overseas/visa"
USE_ADVANCE = "Use Advance stage to move an agency application"
WITHDRAWN = "This application is withdrawn"
ARCHIVED = "Unarchive this student first"
OUTSIDE = "Application is outside your assigned scope"


@pytest_asyncio.fixture
async def world(db_session):
    w = await assign_world(db_session)
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    return w


async def _set(db, model, row_id, **values):
    row = await db.get(model, row_id, populate_existing=True)
    for key, value in values.items():
        setattr(row, key, value)
    await db.commit()


async def _visa_audits(db, case) -> int:
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(case.id), AuditLog.action == "visa.update"))


# --- C1 ---


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"status": "enrolled"}, {"status": "enquiry"}, {"intake": "X"}, {"application_reference": "R-1"}, {"offer_letter_url": "https://x.example/o.pdf"}])
async def test_the_generic_update_refuses_a_counselor_on_an_agency_application(db_session, world, body):
    before = await fresh(db_session, world["app"])
    snapshot = (before.status, before.intake, before.application_reference, before.offer_letter_url)
    async with client_for(world["counselor"].email) as c:
        r = await c.patch(UPDATE.format(world["app"].id), json=body)
    assert r.status_code == 403 and r.json()["detail"] == USE_ADVANCE
    after = await fresh(db_session, world["app"])
    assert (after.status, after.intake, after.application_reference, after.offer_letter_url) == snapshot
    count = await db_session.scalar(select(func.count()).select_from(AgentCommission).where(AgentCommission.application_id == world["app"].id))
    assert count == 0


@pytest.mark.asyncio
async def test_the_generic_update_still_serves_a_counselor_on_a_direct_application(db_session, world):
    async with client_for(world["counselor"].email) as c:
        r = await c.patch(UPDATE.format(world["direct_app"].id), json={"status": "visa_documentation"})
    assert r.status_code == 200, r.text
    assert (await fresh(db_session, world["direct_app"])).status == "visa_documentation"


@pytest.mark.asyncio
async def test_the_admin_generic_update_on_an_agency_application_is_unchanged(db_session, world):
    async with client_for(world["admin"].email) as c:
        r = await c.patch(UPDATE.format(world["app"].id), json={"intake": "Spring 2028"})
    assert r.status_code == 200, r.text
    assert (await fresh(db_session, world["app"])).intake == "Spring 2028"


# --- I1 ---


@pytest.mark.asyncio
async def test_a_withdrawn_agency_application_refuses_the_counselor_visa_start(db_session, world):
    await _set(db_session, OverseasApplication, world["app"].id, status="withdrawn")
    async with client_for(world["counselor"].email) as c:
        r = await c.post(VISA, json={"application_id": str(world["app"].id), "checklist": ["Passport"]})
    assert r.status_code == 409 and r.json()["detail"] == WITHDRAWN
    assert await case_of(db_session, world["app"]) is None


@pytest.mark.asyncio
async def test_an_archived_agency_student_refuses_the_counselor_visa_start(db_session, world):
    await _set(db_session, AgentStudent, world["record"].id, status="archived")
    async with client_for(world["counselor"].email) as c:
        r = await c.post(VISA, json={"application_id": str(world["app"].id), "checklist": ["Passport"]})
    assert r.status_code == 409 and r.json()["detail"] == ARCHIVED
    assert await case_of(db_session, world["app"]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("closure", "detail"), [("withdrawn", WITHDRAWN), ("archived", ARCHIVED)])
async def test_a_closed_agency_application_refuses_the_counselor_visa_update(db_session, world, closure, detail):
    case = await mk_case(db_session, world["app"], checklist=["Passport"])
    if closure == "withdrawn":
        await _set(db_session, OverseasApplication, world["app"].id, status="withdrawn")
    else:
        await _set(db_session, AgentStudent, world["record"].id, status="archived")
    async with client_for(world["counselor"].email) as c:
        r = await c.patch(f"{VISA}/{case.id}", json={"checklist": ["Passport", "CV"], "tracking_reference": "TR-9"})
    assert r.status_code == 409 and r.json()["detail"] == detail
    row = await case_of(db_session, world["app"])
    assert row.checklist == ["Passport"] and row.tracking_reference is None
    assert await _visa_audits(db_session, case) == 0


@pytest.mark.asyncio
async def test_an_archived_agency_student_refuses_advance(db_session, world):
    await _set(db_session, AgentStudent, world["record"].id, status="archived")
    async with client_for(world["counselor"].email) as c:
        r = await c.post(ADVANCE.format(world["app"].id), json={"to_status": "visa_documentation"})
    assert r.status_code == 409 and r.json()["detail"] == ARCHIVED
    assert (await fresh(db_session, world["app"])).status == "offer"


# --- I2 ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [{"checklist": "Passport"}, {"checklist": ["Bank statement"]}, {"checklist": None}, {"appointment_date": "not-a-date"}, {"tracking_reference": "x" * 121}, {"status": 5}],
)
async def test_a_bad_agency_visa_body_is_422_and_stores_nothing(db_session, world, body):
    case = await mk_case(db_session, world["app"], checklist=["Passport"])
    async with client_for(world["counselor"].email) as c:
        r = await c.patch(f"{VISA}/{case.id}", json=body)
    assert r.status_code == 422, r.text
    row = await case_of(db_session, world["app"])
    assert row.checklist == ["Passport"] and row.appointment_date is None and row.tracking_reference is None and row.status == "checklist"
    assert await _visa_audits(db_session, case) == 0


@pytest.mark.asyncio
async def test_a_typed_agency_visa_body_is_applied(db_session, world):
    case = await mk_case(db_session, world["app"], checklist=["Passport"])
    async with client_for(world["counselor"].email) as c:
        r = await c.patch(f"{VISA}/{case.id}", json={"checklist": ["Passport", "CV"], "appointment_date": "2027-03-01", "tracking_reference": "TR-2"})
    assert r.status_code == 200, r.text
    row = await case_of(db_session, world["app"])
    assert row.checklist == ["Passport", "CV"] and str(row.appointment_date) == "2027-03-01" and row.tracking_reference == "TR-2"


# --- I4 ---


@pytest.fixture
def swap_after_scope_read(monkeypatch):
    """Commit a counselor swap from another session right after the route's scope read and before its row lock -- the window a
    concurrent Admin swap can land in."""
    original = workflows._assigned_application

    def install(to_counselor):
        async def wrapped(db, user, application_id):
            item = await original(db, user, application_id)
            async with SessionLocal() as other:
                row = await other.get(OverseasApplication, item.id)
                row.counselor_id = to_counselor.id
                await other.commit()
            return item

        monkeypatch.setattr(workflows, "_assigned_application", wrapped)

    return install


@pytest.mark.asyncio
async def test_advance_rechecks_scope_under_the_lock(db_session, world, swap_after_scope_read):
    swap_after_scope_read(world["counselor2"])
    async with client_for(world["counselor"].email) as c:
        r = await c.post(ADVANCE.format(world["app"].id), json={"to_status": "visa_documentation"})
    assert r.status_code == 403 and r.json()["detail"] == OUTSIDE
    assert (await fresh(db_session, world["app"])).status == "offer"


@pytest.mark.asyncio
async def test_agency_visa_start_rechecks_scope_under_the_lock(db_session, world, swap_after_scope_read):
    swap_after_scope_read(world["counselor2"])
    async with client_for(world["counselor"].email) as c:
        r = await c.post(VISA, json={"application_id": str(world["app"].id), "checklist": ["Passport"]})
    assert r.status_code == 403 and r.json()["detail"] == OUTSIDE
    assert await case_of(db_session, world["app"]) is None


@pytest.mark.asyncio
async def test_agency_visa_update_rechecks_scope_under_the_lock(db_session, world, swap_after_scope_read):
    case = await mk_case(db_session, world["app"], checklist=["Passport"])
    swap_after_scope_read(world["counselor2"])
    async with client_for(world["counselor"].email) as c:
        r = await c.patch(f"{VISA}/{case.id}", json={"tracking_reference": "TR-3"})
    assert r.status_code == 403 and r.json()["detail"] == OUTSIDE
    assert (await case_of(db_session, world["app"])).tracking_reference is None


# --- I3 ---


@pytest.mark.asyncio
async def test_school_bridged_rows_carry_the_assign_column_for_the_admin_only(db_session, world):
    bridged = await mk_application(db_session, agent=None, university=world["university"], school_student=await mk_school_student(db_session), status="offer")
    async with client_for(world["admin"].email) as c:
        r = await c.get(PORTAL.format("admin", "school-applications"))
        assert r.status_code == 200, r.text
        row = next(x for x in r.json()["rows"] if str(x["id"]) == str(bridged.id))
        assert row["counselor"] == "Not assigned" and row["counselor_id"] is None and str(row["assign"]) == str(bridged.id)
        assert {"key": "counselor", "label": "EduSphere counsellor"} in r.json()["columns"]
        assert {"key": "assign", "label": "", "type": "assign_counselor"} in r.json()["columns"]
        assigned = await c.put(ASSIGN.format(bridged.id), json={"counselor_id": str(world["counselor"].id)})
        assert assigned.status_code == 200, assigned.text
        row = next(x for x in (await c.get(PORTAL.format("admin", "school-applications"))).json()["rows"] if str(x["id"]) == str(bridged.id))
        assert row["counselor"] == world["counselor"].full_name and row["counselor_id"] == str(world["counselor"].id)
    assert (await fresh(db_session, bridged)).counselor_id == world["counselor"].id
    async with client_for(world["counselor"].email) as c:
        r = await c.get(PORTAL.format("counselor", "school-applications"))
    assert r.status_code == 200
    assert [col["key"] for col in r.json()["columns"]] == ["id", "student", "student_code", "university", "status"]
    assert all(set(x) == {"id", "student", "student_code", "university", "status"} for x in r.json()["rows"])


# --- M1 ---


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["withdrawn", "enrolled"])
async def test_closed_rows_carry_no_assign_control(db_session, world, status):
    await _set(db_session, OverseasApplication, world["direct_app"].id, status=status)
    bridged = await mk_application(db_session, agent=None, university=world["university"], school_student=await mk_school_student(db_session), status=status)
    async with client_for(world["admin"].email) as c:
        rows = (await c.get(PORTAL.format("admin", "applications"))).json()["rows"]
        school_rows = (await c.get(PORTAL.format("admin", "school-applications"))).json()["rows"]
    by_id = {str(r["id"]): r for r in rows}
    assert by_id[str(world["direct_app"].id)]["assign"] is None
    assert by_id[str(world["app"].id)]["assign"] is not None  # an open row keeps its control
    assert next(r for r in school_rows if str(r["id"]) == str(bridged.id))["assign"] is None
