"""AGN-024 -- approval gate (spec §4.5; DEC-SCOPE-224 K3/K4/K6; AC05, AC06, AC08)."""

import pytest
from sqlalchemy import select, update

from app.models import AgentOrgKycDocument, Notification, UserRoleAssignment
from app.services import agent_kyc as kyc
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn024_helpers import org_for, register_kyc_agent, verify_all

ORG_ACTION = "/api/v1/overseas-admin/agent-orgs/{}/{}"
LEGACY_APPROVE = "/api/v1/overseas-admin/agents/{}/approve"


async def _pending(client, db):
    body = await register_kyc_agent(client)
    return body["user"]["id"], await org_for(db, body["user"]["id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("admin_role", ["overseas_admin", "super_admin"])
async def test_approve_refused_until_all_three_verified(client, db_session, admin_role):
    user_id, org = await _pending(client, db_session)
    admin = await mk_user(db_session, role=admin_role)
    async with client_for(admin.email) as c:
        for verified in (0, 1, 2):
            if verified:
                doc_type = kyc.DOC_TYPES[verified - 1]
                await db_session.execute(update(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org.id, AgentOrgKycDocument.doc_type == doc_type).values(status="verified"))
                await db_session.commit()
            refused = await c.post(ORG_ACTION.format(org.id, "approve"))
            assert refused.status_code == 409 and refused.json()["detail"] == kyc.NOT_VERIFIED
        await verify_all(db_session, org.id, admin)
        ok = await c.post(ORG_ACTION.format(org.id, "approve"))
    assert ok.status_code == 200 and ok.json()["status"] == "active"
    note = await db_session.scalar(select(Notification).where(Notification.user_id == user_id, Notification.title == "Agency approved"))
    assert note is not None and note.action_url == "/overseas/agent/dashboard"


@pytest.mark.asyncio
async def test_legacy_per_agent_approve_is_gated_too(client, db_session):
    user_id, org = await _pending(client, db_session)
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        assert (await c.post(LEGACY_APPROVE.format(user_id))).status_code == 409
        assignment = await db_session.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == user_id, UserRoleAssignment.role == "agent").execution_options(populate_existing=True))
        assert assignment.approval_status == "pending"
        await verify_all(db_session, org.id, admin)
        assert (await c.post(LEGACY_APPROVE.format(user_id))).status_code == 200


@pytest.mark.asyncio
async def test_rejected_to_active_is_gated_and_reject_is_never_gated(client, db_session):
    _user_id, org = await _pending(client, db_session)
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        assert (await c.post(ORG_ACTION.format(org.id, "reject"))).status_code == 200
        assert (await c.post(ORG_ACTION.format(org.id, "approve"))).status_code == 409


@pytest.mark.asyncio
async def test_legacy_org_without_kyc_approves_unchanged_and_gets_no_notice(db_session):
    ctx = await mk_active_org(db_session, name=f"Legacy {uniq()}")
    ctx["org"].status = "pending"
    await db_session.commit()
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        assert (await c.post(ORG_ACTION.format(ctx["org"].id, "approve"))).status_code == 200
    assert await db_session.scalar(select(Notification).where(Notification.user_id == ctx["master"].id, Notification.title == "Agency approved")) is None


@pytest.mark.asyncio
async def test_suspend_then_reinstate_is_not_regated_or_renotified(client, db_session):
    user_id, org = await _pending(client, db_session)
    admin = await mk_user(db_session, role="overseas_admin")
    await verify_all(db_session, org.id, admin)
    async with client_for(admin.email) as c:
        assert (await c.post(ORG_ACTION.format(org.id, "approve"))).status_code == 200
        assert (await c.post(ORG_ACTION.format(org.id, "suspend"))).status_code == 200
        assert (await c.post(ORG_ACTION.format(org.id, "reinstate"))).status_code == 200
    notes = (await db_session.scalars(select(Notification).where(Notification.user_id == user_id, Notification.title == "Agency approved"))).all()
    assert len(notes) == 1


@pytest.mark.asyncio
async def test_list_items_carry_kyc_summary(client, db_session):
    _user_id, org = await _pending(client, db_session)
    await db_session.execute(update(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org.id, AgentOrgKycDocument.doc_type == "pan").values(status="verified"))
    await db_session.commit()
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        page = (await c.get("/api/v1/overseas-admin/agent-orgs", params={"status": "pending", "q": org.prefix})).json()
    item = next(i for i in page["items"] if i["id"] == str(org.id))
    assert item["kyc_required"] is True and item["kyc_summary"] == {"verified": 1, "rejected": 0, "pending": 2}
