"""ccrm-014 (DEC-SCOPE-240, SS1-SS4) -- an application's sub-status under its stage: the mapping, the forward rule, history, scope,
the stage-change sync (SS3) and the reads. Agency world: tests/agn023_helpers.py."""

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.application_sub_status import STAGE_OF, SUB_STATUSES, label
from app.models import AgentCommission, ApplicationStatusHistory
from tests.agn001_helpers import client_for, mk_active_org
from tests.agn008_helpers import APPS
from tests.agn023_helpers import ADVANCE, ASSIGN, PORTAL, assign_world, fresh, notices

SUB = "/api/v1/workflows/overseas/applications/{}/sub-status"
AGENT_SUB = APPS + "/{}/sub-status"
STATUS = "/api/v1/workflows/overseas/applications/{}/status"


async def _assigned(db, *, status="university_selection"):
    w = await assign_world(db, status=status)
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    return w


@pytest_asyncio.fixture
async def world(db_session):
    return await _assigned(db_session)


async def _history(db, app) -> list[ApplicationStatusHistory]:
    stmt = select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == app.id).order_by(ApplicationStatusHistory.created_at)
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


def test_the_mapping_is_the_owner_list():  # SS1
    assert SUB_STATUSES == {
        "university_selection": ("application_created", "documents_pending", "ready_for_submission", "submitted", "under_review"),
        "offer": ("conditional_offer", "unconditional_offer", "offer_accepted"),
        "visa_documentation": ("visa_preparation", "visa_applied"),
        "status_tracking": ("visa_decision_pending", "visa_approved"),
        "enrolled": ("enrolled",),
    }
    assert STAGE_OF["visa_applied"] == "visa_documentation"
    assert label("ready_for_submission") == "Ready for submission" and label(None) is None


@pytest.mark.asyncio
async def test_the_counselor_moves_within_the_stage_and_history_keeps_both_levels(db_session, world):  # AC 6
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        r = await c.post(SUB.format(app.id), json={"sub_status": "documents_pending", "notes": "Waiting for transcripts"})
        assert r.status_code == 200, r.text
        assert r.json() == {"id": str(app.id), "status": "university_selection", "sub_status": "documents_pending", "sub_status_label": "Documents pending", "changed": True}
        assert (await c.post(SUB.format(app.id), json={"sub_status": "submitted"})).status_code == 200
    item = await fresh(db_session, app)
    assert (item.status, item.sub_status) == ("university_selection", "submitted")
    rows = [h for h in await _history(db_session, app) if h.to_sub_status]
    assert [(h.from_status, h.to_status, h.from_sub_status, h.to_sub_status) for h in rows] == [
        ("university_selection", "university_selection", None, "documents_pending"),
        ("university_selection", "university_selection", "documents_pending", "submitted"),
    ]
    assert rows[0].notes == "Waiting for transcripts" and rows[0].changed_by_id == world["counselor"].id


@pytest.mark.asyncio
async def test_a_later_stage_sub_status_advances_the_stage_and_never_moves_back(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(SUB.format(app.id), json={"sub_status": "conditional_offer"})).status_code == 200
        assert (await fresh(db_session, app)).status == "offer"
        r = await c.post(SUB.format(app.id), json={"sub_status": "submitted"})
        assert r.status_code == 422 and "earlier stage" in r.json()["detail"]
        r = await c.post(SUB.format(app.id), json={"sub_status": "rejected"})
        assert r.status_code == 422 and r.json()["detail"] == "Choose a sub-status from the list"
    student_notes = [n.body for n in await notices(db_session, world["direct_student"])]
    assert any("Conditional offer" in body for body in student_notes)


@pytest.mark.asyncio
async def test_the_same_sub_status_twice_writes_nothing(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(SUB.format(app.id), json={"sub_status": "submitted"})).json()["changed"] is True
        before = len(await _history(db_session, app))
        r = await c.post(SUB.format(app.id), json={"sub_status": "submitted"})
    assert r.status_code == 200 and r.json()["changed"] is False
    assert len(await _history(db_session, app)) == before


@pytest.mark.asyncio
async def test_one_application_change_never_touches_another(db_session, world):  # AC 9
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(SUB.format(world["direct_app"].id), json={"sub_status": "visa_applied"})).status_code == 200
    other = await fresh(db_session, world["app"])
    assert (other.status, other.sub_status) == ("university_selection", None)


@pytest.mark.asyncio
async def test_scope_withdrawn_and_role_refusals(db_session, world):
    async with client_for(world["counselor2"].email) as c:  # not their application
        assert (await c.post(SUB.format(world["direct_app"].id), json={"sub_status": "submitted"})).status_code == 403
    async with client_for(world["direct_student"].email) as c:  # students read only
        assert (await c.post(SUB.format(world["direct_app"].id), json={"sub_status": "submitted"})).status_code == 403
    app = await fresh(db_session, world["direct_app"])
    app.status = "withdrawn"
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        r = await c.post(SUB.format(app.id), json={"sub_status": "submitted"})
    assert r.status_code == 409 and r.json()["detail"] == "This application is withdrawn"


@pytest.mark.asyncio
async def test_on_an_agency_application_the_counselor_cannot_enrol_and_the_agency_is_told(db_session, world):  # SS4, CC5
    app = world["app"]
    async with client_for(world["counselor"].email) as c:
        r = await c.post(SUB.format(app.id), json={"sub_status": "enrolled"})
        assert r.status_code == 403 and r.json()["detail"] == "Only the agency's Master confirms enrollment"
        assert (await c.post(SUB.format(app.id), json={"sub_status": "under_review"})).status_code == 200
    titles = [n.title for n in await notices(db_session, world["staff"]["user"])]  # AGN-017 recipients: the assigned staff member
    assert "Application sub-status changed" in titles


@pytest.mark.asyncio
async def test_the_admin_can_enrol_and_the_commission_trigger_runs(db_session, world):
    app = world["app"]
    async with client_for(world["admin"].email) as c:
        r = await c.post(SUB.format(app.id), json={"sub_status": "enrolled"})
    assert r.status_code == 200 and r.json()["status"] == "enrolled"
    count = await db_session.scalar(select(func.count()).select_from(AgentCommission).where(AgentCommission.application_id == app.id))
    assert count == 1


@pytest.mark.asyncio
async def test_the_agent_sets_sub_status_up_to_status_tracking_and_the_counselor_is_told(db_session, world):  # SS4, CC5
    app = world["app"]
    async with client_for(world["master"].email) as c:
        r = await c.post(AGENT_SUB.format(app.id), json={"sub_status": "visa_decision_pending"})
        assert r.status_code == 200, r.text
        detail = r.json()["application"]
        assert (detail["status"], detail["sub_status"], detail["sub_status_label"]) == ("status_tracking", "visa_decision_pending", "Visa decision pending")
        assert detail["history"][-1]["to_sub_status"] == "visa_decision_pending"
        r = await c.post(AGENT_SUB.format(app.id), json={"sub_status": "enrolled"})
        assert r.status_code == 403
    assert "Application sub-status changed" in [n.title for n in await notices(db_session, world["counselor"])]
    other = await mk_active_org(db_session, name="Other Sub")
    async with client_for(other["master"].email) as c:
        assert (await c.post(AGENT_SUB.format(app.id), json={"sub_status": "visa_approved"})).status_code == 404


@pytest.mark.asyncio
async def test_a_stage_change_elsewhere_clears_a_foreign_sub_status_and_enrolled_sets_it(db_session, world):  # SS3
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(SUB.format(app.id), json={"sub_status": "submitted"})).status_code == 200
        assert (await c.post(ADVANCE.format(app.id), json={"to_status": "offer"})).status_code == 200
        assert (await fresh(db_session, app)).sub_status is None
        assert (await c.post(ADVANCE.format(app.id), json={"to_status": "enrolled"})).status_code == 200
    assert (await fresh(db_session, app)).sub_status == "enrolled"


@pytest.mark.asyncio
async def test_reads_carry_the_sub_status(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(SUB.format(app.id), json={"sub_status": "ready_for_submission"})).status_code == 200
        rows = (await c.get("/api/v1/workflows/overseas/applications")).json()
        assert next(r for r in rows if r["id"] == str(app.id))["sub_status"] == "ready_for_submission"
        history = (await c.get(STATUS.format(app.id))).json()
        assert history["sub_status"] == "ready_for_submission" and history["history"][-1]["to_sub_status"] == "ready_for_submission"
        table = (await c.get(PORTAL.format("counselor", "applications"))).json()
        assert {"key": "sub_status_label", "label": "Sub-status"} in table["columns"]
        row = next(r for r in table["rows"] if r["id"] == str(app.id))
        assert (row["sub_status"], row["sub_status_label"]) == ("ready_for_submission", "Ready for submission")
    async with client_for(world["direct_student"].email) as c:
        table = (await c.get(PORTAL.format("student", "applications"))).json()
        assert next(r for r in table["rows"] if r["id"] == str(app.id))["sub_status_label"] == "Ready for submission"
