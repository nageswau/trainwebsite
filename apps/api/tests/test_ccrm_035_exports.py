"""ccrm-035 (DEC-SCOPE-268, E1-E9; §13 export, §16, AC 11) -- CSV and xlsx export of the management CRM reports (ccrm-034) and of the
overseas counselor's own application and lead lists: role-restricted, every export audited (who, report, filters, rows) before the file
is returned, throttled, capped, and only allowlisted columns -- never contact details or internal reasons."""

import csv
import io
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.api import crm_exports
from app.api.agent_reports import EXPORT_LIMIT
from app.models import AuditLog
from tests.agn001_helpers import client_for, uniq
from tests.agn003_helpers import mk_university
from tests.agn008_helpers import mk_application
from tests.bdm001_helpers import make_user
from tests.ccrm012_helpers import search_world
from tests.upc001_helpers import as_role

pytestmark = pytest.mark.asyncio

MGMT = "/api/v1/management/crm-reports/export"
APPS = "/api/v1/counselor/exports/applications"
LEADS = "/api/v1/counselor/exports/leads"
CSV_TYPE = "text/csv"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def rows_of(response) -> list[list[str]]:
    """The file as rows of text, whichever format it is."""
    if response.headers["content-type"].startswith(CSV_TYPE):
        return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    from tests.test_ccrm_035_tabular import _sheet

    return [[text for _, text in row] for row in _sheet(response.content)]


async def audits(db, user) -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "crm.export").order_by(AuditLog.created_at))).all())


# --- management reports (E2) ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("role", "division"), [("partner", "global"), ("super_admin", "global"), ("overseas_admin", "overseas")])
@pytest.mark.parametrize("fmt", ["csv", "xlsx"])
async def test_management_roles_export_a_report_with_its_total_and_the_export_is_audited(client, db_session, role, division, fmt):
    actor = await as_role(client, db_session, role, division)
    university = await mk_university(db_session)
    shared = await make_user(db_session, "overseas_student", "overseas")
    for _ in range(2):
        await mk_application(db_session, agent=None, university=university, student=shared, status="offer", intake=uniq("Fall"))
    response = await client.get(MGMT, params={"report": "universities", "format": fmt, "university": str(university.id)})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(CSV_TYPE if fmt == "csv" else XLSX_TYPE)
    assert response.headers["cache-control"] == "private, no-store"
    assert 'filename="crm-universities-' in response.headers["content-disposition"] and response.headers["content-disposition"].endswith(f'.{fmt}"')
    rows = rows_of(response)
    assert rows[0] == ["University", "Applications", "Students", "Offers", "Offer rate (%)", "Rejections", "Acceptances", "Enrolments", "Deposits paid", "Visas approved", "Visas refused", "Visas pending"]  # ccrm-052 appended
    assert rows[1][:5] == [university.name, "2", "1", "2", "100.0"]  # students and applications counted separately
    assert rows[-1][:3] == ["Total", "2", "1"] and len(rows) == 3
    [audit] = await audits(db_session, actor)
    assert (audit.entity_type, audit.entity_id) == ("crm_report", "universities")
    assert audit.metadata_json == {"format": fmt, "filters": {"university": str(university.id)}, "rows": 1}


async def test_ageing_bands_are_one_column_each(client, db_session):
    await as_role(client, db_session, "partner", "global")
    university = await mk_university(db_session)
    await mk_application(db_session, agent=None, university=university, student=await make_user(db_session, "overseas_student", "overseas"))
    rows = rows_of(await client.get(MGMT, params={"report": "ageing", "university": str(university.id)}))
    assert rows[0] == ["Stage · sub-status", "Applications", "Students", "0–7 days", "8–14 days", "15–30 days", "31–60 days", "Over 60 days", "Oldest (days)"]
    assert rows[1] == ["Enquiry · Not set", "1", "1", "1", "0", "0", "0", "0", "0"]


@pytest.mark.parametrize("report", ["ageing", "universities", "visa", "readiness", "leads", "forecast"])
async def test_every_report_exports_a_header_and_a_total(client, db_session, report):
    await as_role(client, db_session, "overseas_admin", "overseas")
    university = await mk_university(db_session)
    rows = rows_of(await client.get(MGMT, params={"report": report, "format": "xlsx", "university": str(university.id), "intake": uniq("none")}))
    assert rows[0][1:] and rows[-1][0] == "Total"


@pytest.mark.parametrize(("role", "division"), [("accountant", "global"), ("counselor", "overseas"), ("overseas_student", "overseas"), ("it_admin", "it")])
async def test_other_roles_cannot_export_management_reports_and_nothing_is_audited(client, db_session, role, division):
    actor = await as_role(client, db_session, role, division)
    assert (await client.get(MGMT, params={"report": "ageing"})).status_code == 403
    assert await audits(db_session, actor) == []


async def test_anonymous_export_is_refused(client):
    for url in (f"{MGMT}?report=ageing", APPS, LEADS):
        assert (await client.get(url)).status_code == 401


@pytest.mark.parametrize(
    "params",
    [
        {"report": "salaries"},
        {"report": "ageing", "format": "pdf"},
        {"report": "ageing", "date_from": "2026-03-01", "date_to": "2026-02-01"},
        {"report": "ageing", "university": "not-a-uuid"},
        {},
    ],
)
async def test_bad_management_export_requests_are_422(client, db_session, params):
    actor = await as_role(client, db_session, "partner", "global")
    assert (await client.get(MGMT, params=params)).status_code == 422
    assert await audits(db_session, actor) == []


# --- the counselor's own lists (E3, E4) -------------------------------------------------------------------------------------------
@pytest_asyncio.fixture
async def world(db_session):
    return await search_world(db_session)


@pytest.mark.parametrize("fmt", ["csv", "xlsx"])
async def test_counselor_exports_own_applications_with_allowlisted_columns_only(world, db_session, fmt):
    async with client_for(world["a"].email) as c:
        response = await c.get(APPS, params={"format": fmt})
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].startswith('attachment; filename="my-applications-')
    rows = rows_of(response)
    assert rows[0] == ["EduSphere ID", "Student", "University", "Agency", "Intake", "Status", "Sub-status", "Outcome", "Next action", "Last updated"]
    codes = {row[0] for row in rows[1:]}
    assert codes == {world["app1"].application_code, world["app2"].application_code}  # never counselor B's application
    first = next(row for row in rows[1:] if row[0] == world["app1"].application_code)
    assert first[1:7] == [world["s1"].full_name, world["uk"].name, "", "Sep 2027", "Offer", "Conditional offer"]
    text = "\n".join(",".join(row) for row in rows)
    for secret in (world["s1"].email, world["s1"].phone, world["s1"].student_code, str(world["app1"].id)):
        assert secret not in text  # E4: no contact details, codes of other kinds or internal ids
    [audit] = await audits(db_session, world["a"])
    assert (audit.entity_type, audit.entity_id, audit.metadata_json) == ("counselor_list", "applications", {"format": fmt, "filters": {}, "rows": 2})


async def test_application_filters_narrow_the_export_and_are_audited(world, db_session):
    async with client_for(world["a"].email) as c:
        response = await c.get(APPS, params={"country": str(world["uk"].country_id), "stage": "offer"})
    assert [row[0] for row in rows_of(response)[1:]] == [world["app1"].application_code]
    [audit] = await audits(db_session, world["a"])
    assert audit.metadata_json["filters"] == {"country": str(world["uk"].country_id), "stage": "offer"} and audit.metadata_json["rows"] == 1


async def test_counselor_exports_own_leads_without_contact_details(world, db_session):
    async with client_for(world["a"].email) as c:
        response = await c.get(LEADS, params={"format": "csv"})
        hot = await c.get(LEADS, params={"priority": "hot", "format": "xlsx"})
    rows = rows_of(response)
    assert rows[0] == ["Lead ID", "Name", "Interest", "Stage", "Priority", "Source", "Telecaller", "Lead date"]
    assert {row[0] for row in rows[1:]} == {world["lead1"].lead_code, world["lead2"].lead_code}
    lead2 = next(row for row in rows[1:] if row[0] == world["lead2"].lead_code)
    assert lead2[3:5] == ["Follow-up", "Cold"] and lead2[7] == "2026-01-10"
    text = response.content.decode("utf-8-sig")
    assert "98450" not in text and "@example.local" not in text  # E4: never phone or email
    assert [row[0] for row in rows_of(hot)[1:]] == [world["lead1"].lead_code]
    assert [a.metadata_json["filters"] for a in await audits(db_session, world["a"])] == [{}, {"priority": "hot"}]


@pytest.mark.parametrize(
    ("url", "params"), [(APPS, {"stage": "nowhere"}), (APPS, {"counselor": "none"}), (LEADS, {"priority": "lukewarm"}), (LEADS, {"from": "2026-03-01", "to": "2026-02-01"}), (LEADS, {"format": "pdf"})]
)
async def test_bad_counselor_export_requests_are_422(world, db_session, url, params):
    async with client_for(world["a"].email) as c:
        assert (await c.get(url, params=params)).status_code == 422
    assert await audits(db_session, world["a"]) == []


@pytest.mark.parametrize(("role", "division"), [("counselor", "it"), ("overseas_admin", "overseas"), ("overseas_student", "overseas"), ("partner", "global")])
async def test_only_the_overseas_counselor_exports_own_lists(client, db_session, role, division):
    user = await as_role(client, db_session, role, division)
    for url in (APPS, LEADS):
        assert (await client.get(url)).status_code == 403
    assert await audits(db_session, user) == []


# --- throttle (E6) and cap (E7) ---------------------------------------------------------------------------------------------------
async def test_exports_are_throttled_from_the_callers_own_audit_rows(world, db_session):
    for _ in range(EXPORT_LIMIT):
        db_session.add(AuditLog(user_id=world["a"].id, action="crm.export", entity_type="counselor_list", entity_id="leads", created_at=datetime.now(UTC)))
    await db_session.commit()
    async with client_for(world["a"].email) as c:
        response = await c.get(LEADS)
    assert response.status_code == 429 and int(response.headers["retry-after"]) >= 1
    assert len(await audits(db_session, world["a"])) == EXPORT_LIMIT  # a refused export writes nothing


async def test_a_list_over_the_cap_is_refused(world, db_session, monkeypatch):
    monkeypatch.setattr(crm_exports, "ROW_CAP", 1)
    async with client_for(world["a"].email) as c:
        response = await c.get(LEADS)
    assert response.status_code == 422 and "narrow the filters" in response.json()["detail"]
    assert await audits(db_session, world["a"]) == []


async def test_counts_are_unaffected_by_other_users_exports(world, db_session):
    other = world["b"]
    for _ in range(EXPORT_LIMIT):
        db_session.add(AuditLog(user_id=other.id, action="crm.export", entity_type="counselor_list", entity_id="leads"))
    await db_session.commit()
    async with client_for(world["a"].email) as c:
        assert (await c.get(LEADS)).status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id == world["a"].id, AuditLog.action == "crm.export")) == 1
