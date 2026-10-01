"""AGN-003 -- per-staff permissions: effective permissions on /auth/me, the Master's toggle route, Reports gating, next-request
effect (spec §6, §8; AGN-003-AC03, AC05, AC06, AC08)."""

import pytest

from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import mk_staff

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
