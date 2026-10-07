"""AGN-008 AC05, AC06, AC16 -- forward-only to status_tracking, withdraw, terminal, stale, no commission; counselor guards."""

import logging

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentCommission, ApplicationStatusHistory, AuditLog, OverseasApplication
from app.services.agent_applications import AGENT_MAX_STAGE, OVERSEAS_APPLICATION_STAGES
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import APPS, agency_world, mk_application


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    return w


async def _status(c, app_id, to, expected=None, **extra):
    body = {"to_status": to, **({"expected_status": expected} if expected else {}), **extra}
    return await c.post(f"{APPS}/{app_id}/status", json=body)


@pytest.mark.asyncio
async def test_forward_and_skip_write_one_history_row_each(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        assert (await _status(c, world["app"].id, "eligibility_evaluation", "enquiry")).status_code == 200
        r = await _status(c, world["app"].id, "visa_documentation", "eligibility_evaluation", notes="Offer came early")
        assert r.status_code == 200 and r.json()["application"]["status"] == "visa_documentation"
        assert (await _status(c, world["app"].id, "status_tracking")).status_code == 200
    rows = (await db_session.scalars(select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == world["app"].id).order_by(ApplicationStatusHistory.created_at))).all()
    assert [(h.from_status, h.to_status) for h in rows] == [("enquiry", "eligibility_evaluation"), ("eligibility_evaluation", "visa_documentation"), ("visa_documentation", "status_tracking")]
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(world["app"].id)))).all()
    assert actions.count("overseas.application.advance") == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "target", "code"), [("offer", "offer", 422), ("offer", "eligibility_evaluation", 422), ("offer", "rejected", 422), ("offer", "enrolled", 403)])
async def test_backward_same_unknown_422_enrolled_403(db_session, world, start, target, code):
    row = await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)
    row.status = start
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await _status(c, world["app"].id, target)
    assert r.status_code == code
    assert (await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)).status == start
    assert await db_session.scalar(select(func.count()).select_from(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == world["app"].id)) == 0
    assert await db_session.scalar(select(func.count()).select_from(AgentCommission).where(AgentCommission.application_id == world["app"].id)) == 0


@pytest.mark.asyncio
async def test_withdraw_then_everything_is_409(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await _status(c, world["app"].id, "withdrawn", "enquiry")
        assert r.status_code == 200 and r.json()["application"]["read_only_reason"] == "withdrawn"
        for to in ("offer", "withdrawn"):
            assert (await _status(c, world["app"].id, to)).status_code == 409
        assert (await c.patch(f"{APPS}/{world['app'].id}", json={"intake": "X"})).status_code == 409
    assert "overseas.application.withdraw" in (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(world["app"].id)))).all()


@pytest.mark.asyncio
async def test_enrolled_cannot_be_withdrawn(db_session, world):
    row = await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)
    row.status = "enrolled"
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await _status(c, world["app"].id, "withdrawn")
    assert r.status_code == 409 and r.json()["detail"] == "An enrolled application cannot be withdrawn"


@pytest.mark.asyncio
async def test_stale_expected_status_is_refused(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await _status(c, world["app"].id, "offer", expected="university_selection")
    assert r.status_code == 409 and r.json()["detail"].startswith("This application changed since you opened it")
    assert (await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)).status == "enquiry"


@pytest.mark.asyncio
async def test_legacy_application_follows_the_archived_record(db_session, world):
    legacy = await mk_application(db_session, agent=world["master"], university=world["university"], student=world["linked_user"], intake="Legacy")
    world["linked_record"].status = "archived"
    db_session.add(world["linked_record"])
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        assert (await _status(c, legacy.id, "offer")).status_code == 409


@pytest.mark.asyncio
async def test_counselor_cannot_revive_a_withdrawn_application(db_session, world):
    counselor = await mk_user(db_session, role="counselor", full_name="Counselor")
    row = await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)
    row.status, row.counselor_id = "withdrawn", counselor.id
    await db_session.commit()
    async with client_for(counselor.email) as c:
        advance = await c.post(f"/api/v1/workflows/overseas/applications/{world['app'].id}/advance", json={"to_status": "offer"})
        patch = await c.patch(f"/api/v1/workflows/overseas/applications/{world['app'].id}", json={"status": "offer"})
        notes_only = await c.patch(f"/api/v1/workflows/overseas/applications/{world['app'].id}", json={"next_action": "Archive the file"})
    assert advance.status_code == 409
    # AGN-023 (DEC-SCOPE-090 H4, final review C1): a counselor's generic PATCH of an agency application is refused outright
    assert (patch.status_code, notes_only.status_code) == (403, 403)
    assert (await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)).status == "withdrawn"


@pytest.mark.asyncio
async def test_status_change_is_logged(world, caplog, monkeypatch):
    monkeypatch.setattr(logging.getLogger("app.agent_applications"), "disabled", False)
    caplog.set_level(logging.INFO, logger="app.agent_applications")
    async with client_for(world["master"].email) as c:
        await _status(c, world["app"].id, "offer")
    record = next(r for r in caplog.records if r.getMessage() == "agent_application_advanced")
    assert record.extra_fields["from_status"] == "enquiry" and record.extra_fields["to_status"] == "offer"


def test_only_enrolled_lies_beyond_the_agent_maximum():
    assert OVERSEAS_APPLICATION_STAGES[OVERSEAS_APPLICATION_STAGES.index(AGENT_MAX_STAGE) + 1 :] == ["enrolled"]
