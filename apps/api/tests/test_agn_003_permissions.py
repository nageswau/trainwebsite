"""AGN-003 -- per-staff permissions: effective permissions on /auth/me, the Master's toggle route, Reports gating, next-request
effect (spec §6, §8; AGN-003-AC03, AC05, AC06, AC08)."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import AgentOrg, AgentOrgMember, AuditLog
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import STAFF, mk_staff

ME = "/api/v1/auth/me"
REPORTS = "/api/v1/portal/overseas/agent/reports"
NONE_ON = {"can_verify_documents": False, "can_view_reports": False}
ALL_ON = {"can_verify_documents": True, "can_view_reports": True}


@pytest.mark.asyncio
async def test_auth_me_reports_effective_permissions(db_session):
    ctx = await mk_active_org(db_session, name=f"Me Perms {uniq()}")
    plain = await mk_staff(db_session, ctx["org"], full_name="Plain Staff")
    reports_only = await mk_staff(db_session, ctx["org"], full_name="Reports Staff", can_view_reports=True)
    async with client_for(plain["user"].email) as c:
        assert (await c.get(ME)).json()["agent_permissions"] == NONE_ON
    async with client_for(reports_only["user"].email) as c:
        assert (await c.get(ME)).json()["agent_permissions"] == {"can_verify_documents": False, "can_view_reports": True}
    async with client_for(ctx["master"].email) as m:
        assert (await m.get(ME)).json()["agent_permissions"] == ALL_ON  # a Master is never limited (P2)
    student = await mk_user(db_session, role="overseas_student")
    async with client_for(student.email) as s:
        assert (await s.get(ME)).json()["agent_permissions"] is None


@pytest.mark.asyncio
async def test_reports_is_off_for_staff_by_default(db_session):
    ctx = await mk_active_org(db_session, name=f"Reports Off {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as c:
        response = await c.get(REPORTS)
    assert response.status_code == 403
    assert response.json()["detail"] == "Your agency Master hasn't given you access to reports"


@pytest.mark.asyncio
async def test_reports_on_shows_the_staff_report_without_commission(db_session):
    ctx = await mk_active_org(db_session, name=f"Reports On {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], can_view_reports=True)
    async with client_for(staff["user"].email) as c:
        response = await c.get(REPORTS)
    assert response.status_code == 200
    assert "commission" not in str(response.json()).lower()


@pytest.mark.asyncio
async def test_masters_always_see_reports(db_session):
    ctx = await mk_active_org(db_session, name=f"Reports Master {uniq()}")
    async with client_for(ctx["master"].email) as m:
        response = await m.get(REPORTS)
    assert response.status_code == 200 and "Paid commission" in str(response.json())


def _perms(member_id) -> str:
    return f"{STAFF}/{member_id}/permissions"


async def _audits(db_session, org_id) -> list[AuditLog]:
    return (await db_session.scalars(
        select(AuditLog).where(AuditLog.action == "agent_org.staff_permissions", AuditLog.entity_id == str(org_id)).execution_options(populate_existing=True)
    )).all()


@pytest.mark.asyncio
async def test_a_master_sets_permissions_and_the_change_is_audited(db_session):
    ctx = await mk_active_org(db_session, name=f"Set Perms {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(ctx["master"].email) as m:
        response = await m.put(_perms(staff["member"].id), json={"can_verify_documents": True, "can_view_reports": False})
        assert response.status_code == 200, response.text
        assert response.json()["member"]["permissions"] == {"can_verify_documents": True, "can_view_reports": False}
        listed = (await m.get(STAFF)).json()["items"]
        assert next(i for i in listed if i["id"] == str(staff["member"].id))["permissions"]["can_verify_documents"] is True
    member = await db_session.get(AgentOrgMember, staff["member"].id, populate_existing=True)
    assert (member.can_verify_documents, member.can_view_reports) == (True, False)
    [row] = await _audits(db_session, ctx["org"].id)
    assert row.user_id == ctx["master"].id and row.outcome == "updated"
    assert row.metadata_json == {"member_id": str(staff["member"].id), "code": staff["member"].code, "before": NONE_ON, "after": {"can_verify_documents": True, "can_view_reports": False}}


@pytest.mark.asyncio
async def test_saving_the_same_permissions_again_writes_nothing(db_session):
    ctx = await mk_active_org(db_session, name=f"Noop Perms {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], can_view_reports=True)
    async with client_for(ctx["master"].email) as m:
        response = await m.put(_perms(staff["member"].id), json={"can_verify_documents": False, "can_view_reports": True})
    assert response.status_code == 200
    assert await _audits(db_session, ctx["org"].id) == []


@pytest.mark.asyncio
async def test_permissions_can_be_set_on_a_deactivated_staff_member(db_session):
    ctx = await mk_active_org(db_session, name=f"Deact Perms {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], active=False)
    async with client_for(ctx["master"].email) as m:
        response = await m.put(_perms(staff["member"].id), json=ALL_ON)
    assert response.status_code == 200 and response.json()["member"]["status"] == "deactivated"


@pytest.mark.asyncio
async def test_only_a_master_of_the_same_agency_can_set_permissions(db_session):
    ctx = await mk_active_org(db_session, name=f"Scope Perms {uniq()}")
    other = await mk_active_org(db_session, name=f"Other Perms {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    peer = await mk_staff(db_session, ctx["org"], full_name="Peer Staff")
    async with client_for(other["master"].email) as o:
        response = await o.put(_perms(staff["member"].id), json=ALL_ON)
        assert response.status_code == 404 and response.json()["detail"] == "Staff member not found"
    async with client_for(ctx["master"].email) as m:
        assert (await m.put(_perms(ctx["member"].id), json=ALL_ON)).status_code == 404  # a Master's member id
        assert (await m.put(_perms(uuid.uuid4()), json=ALL_ON)).status_code == 404
    async with client_for(peer["user"].email) as p:
        for target in (staff["member"].id, peer["member"].id):  # another staff member, or themselves
            response = await p.put(_perms(target), json=ALL_ON)
            assert response.status_code == 403 and response.json()["detail"] == "Only an agency Master can manage the team"
    member = await db_session.get(AgentOrgMember, staff["member"].id, populate_existing=True)
    assert (member.can_verify_documents, member.can_view_reports) == (False, False)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {},
    {"can_verify_documents": True},
    {"can_verify_documents": "true", "can_view_reports": False},
    {"can_verify_documents": 1, "can_view_reports": False},
    {"can_verify_documents": True, "can_view_reports": True, "is_master": True},
])
async def test_bad_bodies_are_refused(db_session, body):
    ctx = await mk_active_org(db_session, name=f"Bad Perms {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(ctx["master"].email) as m:
        assert (await m.put(_perms(staff["member"].id), json=body)).status_code == 422
    member = await db_session.get(AgentOrgMember, staff["member"].id, populate_existing=True)
    assert (member.can_verify_documents, member.can_view_reports) == (False, False)


@pytest.mark.asyncio
async def test_a_suspended_agency_cannot_change_permissions(db_session):
    ctx = await mk_active_org(db_session, name=f"Susp Perms {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    org = await db_session.get(AgentOrg, ctx["org"].id, populate_existing=True)
    org.status = "suspended"
    await db_session.commit()
    async with client_for(ctx["master"].email) as m:
        assert (await m.put(_perms(staff["member"].id), json=ALL_ON)).status_code == 403


@pytest.mark.asyncio
async def test_toggle_applies_on_next_request(db_session):  # AGN-003-AC05, Review Focus 1
    ctx = await mk_active_org(db_session, name=f"Next Req {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as s, client_for(ctx["master"].email) as m:
        assert (await s.get(REPORTS)).status_code == 403
        assert (await m.put(_perms(staff["member"].id), json={"can_verify_documents": False, "can_view_reports": True})).status_code == 200
        assert (await s.get(REPORTS)).status_code == 200  # same cookie jar, no sign-in
        assert (await s.get(ME)).json()["agent_permissions"]["can_view_reports"] is True
        assert (await m.put(_perms(staff["member"].id), json=NONE_ON)).status_code == 200
        assert (await s.get(REPORTS)).status_code == 403
    count = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "agent_org.staff_permissions", AuditLog.entity_id == str(ctx["org"].id)))
    assert count == 2
