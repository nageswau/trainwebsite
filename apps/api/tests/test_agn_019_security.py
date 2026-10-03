"""AGN-019 (DEC-SCOPE-063) -- the staff performance endpoint's gate, date validation and contract (spec §5.1, §6a; AC4, AC6-AC8)."""

import logging

import pytest

from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn004_helpers import mk_staff
from tests.agn017_helpers import deactivate, set_org_status

PERFORMANCE_API = "/api/v1/workflows/overseas/agent/crm/performance"
MASTER_ONLY = "Only an agency Master can view staff performance"
ZERO_FUNNEL = dict.fromkeys(("students", "applications", "submitted", "offers", "visa", "enrolled"), 0)
ZERO_COUNTS = dict.fromkeys(("students", "applications", "offers", "visa_applications", "visa_approvals", "enrollments"), 0) | {"funnel": ZERO_FUNNEL}


async def _get(email, **params):
    async with client_for(email) as c:
        return await c.get(PERFORMANCE_API, params=params)


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client):
    assert (await client.get(PERFORMANCE_API)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("super_admin", "global"), ("counselor", "overseas")])
async def test_non_agents_are_refused(db_session, role, division):
    user = await mk_user(db_session, role=role, division=division)
    assert (await _get(user.email)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("can_view_reports", [False, True])
async def test_staff_are_refused_even_with_reports(db_session, can_view_reports):
    ctx = await mk_active_org(db_session)
    staff = await mk_staff(db_session, ctx["org"], can_view_reports=can_view_reports)
    response = await _get(staff["user"].email)
    assert response.status_code == 403 and response.json() == {"detail": MASTER_ONLY}


@pytest.mark.asyncio
async def test_refused_caller_never_sees_a_date_error(db_session):
    """Guards first, then the dates (spec §5.1): a 403 caller cannot probe validation."""
    ctx = await mk_active_org(db_session)
    staff = await mk_staff(db_session, ctx["org"])
    assert (await _get(staff["user"].email, date_from="not-a-date")).status_code == 403


@pytest.mark.asyncio
async def test_suspended_agency_and_deactivated_master_are_refused(db_session):
    ctx = await mk_active_org(db_session)
    async with client_for(ctx["master"].email) as c:
        await set_org_status(db_session, ctx["org"], "suspended")
        assert (await c.get(PERFORMANCE_API)).status_code == 403
    other = await mk_active_org(db_session)
    async with client_for(other["master"].email) as c:
        await deactivate(db_session, other["member"])
        assert (await c.get(PERFORMANCE_API)).status_code in (401, 403)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "detail"),
    [
        ({"date_from": "2026-13-01"}, "date_from must be a date (YYYY-MM-DD)"),
        ({"date_to": "20260101"}, "date_to must be a date (YYYY-MM-DD)"),
        ({"date_from": "2026-02-01", "date_to": "2026-01-31"}, "date_to must be on or after date_from"),
        ({"date_to": "9999-12-31"}, "date_to must be before 9999-12-31"),
    ],
)
async def test_bad_dates_are_422(db_session, params, detail):
    ctx = await mk_active_org(db_session)
    response = await _get(ctx["master"].email, **params)
    assert response.status_code == 422 and response.json() == {"detail": detail}


@pytest.mark.asyncio
async def test_empty_agency_is_zeros_and_not_cached(db_session):
    ctx = await mk_active_org(db_session)
    response = await _get(ctx["master"].email)
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert body["rows"] == [] and body["unassigned"] is None and body["total"] == ZERO_COUNTS
    assert body["date_from"] is None and body["date_to"] is None and body["as_of"]


@pytest.mark.asyncio
async def test_dates_are_echoed(db_session):
    ctx = await mk_active_org(db_session)
    body = (await _get(ctx["master"].email, date_from="2026-01-01", date_to="2026-01-31")).json()
    assert body["date_from"] == "2026-01-01" and body["date_to"] == "2026-01-31"


@pytest.mark.asyncio
async def test_log_line_carries_ids_flags_and_timing_only(db_session, caplog):
    ctx = await mk_active_org(db_session)
    await mk_staff(db_session, ctx["org"], full_name="Logged Staff")
    with caplog.at_level(logging.INFO, logger="app.agent_performance"):
        assert (await _get(ctx["master"].email, date_from="2026-01-01")).status_code == 200
    record = next(r for r in caplog.records if r.getMessage() == "agent_performance.read")
    fields = record.extra_fields
    assert set(fields) == {"org_id", "actor_id", "filtered", "rows", "duration_ms"}
    assert fields["org_id"] == str(ctx["org"].id) and fields["filtered"] is True and fields["rows"] == 1
    assert "Logged Staff" not in str(fields)
