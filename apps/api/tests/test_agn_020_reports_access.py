"""AGN-020 (DEC-SCOPE-063) -- who may read which report, in the fixed check order of spec §5.1 (AC4)."""

import pytest
import pytest_asyncio
from sqlalchemy import update

from app.core.rbac import REPORTS_REFUSED
from app.models import AgentOrgMember
from tests.agn001_helpers import client_for, mk_user
from tests.agn020_helpers import REPORTS, reports_world

KINDS = ["students", "applications", "enrollments", "universities", "countries", "intakes", "staff"]
STAFF_KINDS = [k for k in KINDS if k != "staff"]
READY = ["countries"]  # widened to KINDS once every kind is built (plan Tasks 3-4)
FORMATS = ["", ".csv"]
STAFF_REPORT_REFUSED = "Only an agency Master can view staff performance"


@pytest_asyncio.fixture
async def world(db_session):
    return await reports_world(db_session)


async def _get(email, path, **params):
    async with client_for(email) as c:
        return await c.get(f"{REPORTS}/{path}", params=params)


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("path", [*KINDS, "no-such-kind"])
async def test_staff_without_the_toggle_are_refused_before_anything_else(world, path, fmt):
    """403 REPORTS_REFUSED beats the unknown kind (404) and a bad date (422)."""
    response = await _get(world["s3"]["user"].email, f"{path}{fmt}", date_from="not-a-date")
    assert response.status_code == 403 and response.json()["detail"] == REPORTS_REFUSED


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", FORMATS)
async def test_staff_with_the_toggle_never_get_staff_performance(world, fmt):
    response = await _get(world["s1"]["user"].email, f"staff{fmt}", date_from="not-a-date")
    assert response.status_code == 403 and response.json()["detail"] == STAFF_REPORT_REFUSED


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [k for k in STAFF_KINDS if k in READY])
async def test_staff_with_the_toggle_read_their_own_scope(world, kind):
    response = await _get(world["s1"]["user"].email, kind)
    assert response.status_code == 200, response.text
    assert response.json()["scope"] == "own" and response.json()["kind"] == kind


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", READY)
async def test_masters_read_every_report(world, kind):
    response = await _get(world["master"].email, kind)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "agency" and body["kind"] == kind
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["super_admin", "counselor", "overseas_student"])
@pytest.mark.parametrize("fmt", FORMATS)
async def test_non_agency_callers_are_refused(db_session, role, fmt):
    user = await mk_user(db_session, role=role, division="global" if role == "super_admin" else "overseas")
    response = await _get(user.email, f"countries{fmt}")
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", FORMATS)
async def test_unknown_kind_is_404_after_authorization(world, fmt):
    response = await _get(world["master"].email, f"no-such-kind{fmt}")
    assert response.status_code == 404 and response.json()["detail"] == "Report not found"


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", FORMATS)
async def test_bad_input_is_a_422_naming_the_param(world, fmt):
    response = await _get(world["master"].email, f"countries{fmt}", date_from="2026-13-01")
    assert response.status_code == 422
    assert response.json()["detail"] == [{"loc": ["query", "date_from"], "msg": "date_from must be a date (YYYY-MM-DD)", "type": "value_error"}]


@pytest.mark.asyncio
async def test_the_csv_suffix_is_not_read_as_a_kind(world):
    response = await _get(world["master"].email, "countries.csv")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")


@pytest.mark.asyncio
async def test_switching_the_toggle_off_applies_on_the_next_request(world, db_session):
    email = world["s1"]["user"].email
    assert (await _get(email, "countries")).status_code == 200
    await db_session.execute(update(AgentOrgMember).where(AgentOrgMember.id == world["s1"]["member"].id).values(can_view_reports=False))
    await db_session.commit()
    response = await _get(email, "countries")
    assert response.status_code == 403 and response.json()["detail"] == REPORTS_REFUSED
