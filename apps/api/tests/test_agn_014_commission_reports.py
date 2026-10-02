"""AGN-014 (DEC-SCOPE-051) -- Master-only commission report, CSV export and dashboard Revenue (spec §5-§6, AC01-AC08)."""

import csv
import io
from datetime import UTC, datetime

import pytest

from app.models import AgentOrg
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import mk_staff
from tests.agn014_helpers import CSV, REPORT, mk_commission


def _day(y, m, d, hh=12, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=UTC)


@pytest.mark.asyncio
async def test_master_report_breaks_down_by_status_university_country_intake(db_session):  # AC05
    ctx = await mk_active_org(db_session, name=f"Report {uniq()}")
    await mk_commission(db_session, ctx, status="paid", amount=1500, university_name="Alpha U", country_name="Aland", intake="Sep 2027")
    await mk_commission(db_session, ctx, status="estimated", amount=500, university_name="Alpha U", country_name="Aland", intake="Jan 2028")
    await mk_commission(db_session, ctx, status="claimed", amount=2000, university_name="Beta U", country_name="Bland", intake="Sep 2027")
    async with client_for(ctx["master"].email) as c:
        response = await c.get(REPORT)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["date_from"] is None and body["date_to"] is None
    assert body["totals"] == [{"currency": "INR", "count": 3, "amount": 4000.0}]
    assert [(r["status"], r["count"], r["amount"]) for r in body["by_status"]] == [("estimated", 1, 500.0), ("claimed", 1, 2000.0), ("paid", 1, 1500.0)]
    # Two universities named "Alpha U" in two countries both called "Aland" would be one group; here each helper call makes its own
    # country row, so the grouping key is the (university, country) *names*, as a Master reads them.
    assert [(r["university"], r["country"], r["count"], r["amount"]) for r in body["by_university"]] == [("Alpha U", "Aland", 2, 2000.0), ("Beta U", "Bland", 1, 2000.0)]
    assert [(r["country"], r["amount"]) for r in body["by_country"]] == [("Aland", 2000.0), ("Bland", 2000.0)]
    assert [(r["intake"], r["count"], r["amount"]) for r in body["by_intake"]] == [("Sep 2027", 2, 3500.0), ("Jan 2028", 1, 500.0)]


@pytest.mark.asyncio
async def test_report_groups_per_currency(db_session):  # Review Focus 2
    ctx = await mk_active_org(db_session, name=f"Currency {uniq()}")
    await mk_commission(db_session, ctx, amount=1000, currency="INR")
    await mk_commission(db_session, ctx, amount=250, currency="USD")
    async with client_for(ctx["master"].email) as c:
        body = (await c.get(REPORT)).json()
    assert body["totals"] == [{"currency": "INR", "count": 1, "amount": 1000.0}, {"currency": "USD", "count": 1, "amount": 250.0}]
    assert {(r["status"], r["currency"]) for r in body["by_status"]} == {("paid", "INR"), ("paid", "USD")}


@pytest.mark.asyncio
async def test_report_covers_the_agency_and_staff_created_applications_but_not_other_agencies(db_session):  # AC05
    ctx = await mk_active_org(db_session, name=f"Scope {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    other = await mk_active_org(db_session, name=f"Other {uniq()}")
    await mk_commission(db_session, ctx, amount=100, university_name="Master U")
    await mk_commission(db_session, ctx, amount=200, university_name="Staff U", agent=staff["user"])
    await mk_commission(db_session, other, amount=999, university_name="Foreign U")
    async with client_for(ctx["master"].email) as c:
        body = (await c.get(REPORT)).json()
    assert {r["university"] for r in body["by_university"]} == {"Master U", "Staff U"}
    assert body["totals"] == [{"currency": "INR", "count": 2, "amount": 300.0}]


@pytest.mark.asyncio
async def test_report_names_a_student_without_a_login(db_session):  # Review Focus 1 (the CSV test asserts the name)
    ctx = await mk_active_org(db_session, name=f"Nologin {uniq()}")
    await mk_commission(db_session, ctx, student=False)
    async with client_for(ctx["master"].email) as c:
        response = await c.get(REPORT)
    assert response.status_code == 200 and response.json()["totals"][0]["count"] == 1


@pytest.mark.asyncio
async def test_empty_report_has_empty_lists(db_session):
    ctx = await mk_active_org(db_session, name=f"Empty {uniq()}")
    async with client_for(ctx["master"].email) as c:
        body = (await c.get(REPORT)).json()
    assert all(body[key] == [] for key in ("totals", "by_status", "by_university", "by_country", "by_intake"))


@pytest.mark.asyncio
async def test_date_filter_is_inclusive_utc_days(db_session):  # AC06, Review Focus 3
    ctx = await mk_active_org(db_session, name=f"Dates {uniq()}")
    await mk_commission(db_session, ctx, amount=1, created_at=_day(2026, 8, 31, 23, 59, 59))
    await mk_commission(db_session, ctx, amount=10, created_at=_day(2026, 9, 1, 0, 0, 0))
    await mk_commission(db_session, ctx, amount=100, created_at=_day(2026, 9, 30, 23, 59, 59))
    await mk_commission(db_session, ctx, amount=1000, created_at=_day(2026, 10, 1, 0, 0, 0))
    async with client_for(ctx["master"].email) as c:
        both = (await c.get(REPORT, params={"date_from": "2026-09-01", "date_to": "2026-09-30"})).json()
        only_from = (await c.get(REPORT, params={"date_from": "2026-09-01"})).json()
        only_to = (await c.get(REPORT, params={"date_to": "2026-08-31"})).json()
    assert both["date_from"] == "2026-09-01" and both["date_to"] == "2026-09-30"
    assert both["totals"] == [{"currency": "INR", "count": 2, "amount": 110.0}]
    assert only_from["totals"][0]["amount"] == 1110.0
    assert only_to["totals"][0]["amount"] == 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize(("params", "detail"), [
    ({"date_from": "2026-02-30"}, "date_from must be a date (YYYY-MM-DD)"),
    ({"date_to": "yesterday"}, "date_to must be a date (YYYY-MM-DD)"),
    ({"date_from": "2026-09-30", "date_to": "2026-09-01"}, "date_to must be on or after date_from"),
])
@pytest.mark.parametrize("path", [REPORT, CSV], ids=["json", "csv"])
async def test_bad_dates_are_422_for_a_master(db_session, params, detail, path):  # AC06
    ctx = await mk_active_org(db_session, name=f"Bad {uniq()}")
    async with client_for(ctx["master"].email) as c:
        response = await c.get(path, params=params)
    assert response.status_code == 422 and response.json()["detail"] == detail, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [REPORT, CSV], ids=["json", "csv"])
async def test_staff_get_403_before_any_date_error(db_session, path):  # AC02, Review Focus 5
    ctx = await mk_active_org(db_session, name=f"Staff {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], can_view_reports=True)
    async with client_for(staff["user"].email) as c:
        for params in ({}, {"date_from": "2026-02-30"}, {"date_from": "2026-09-30", "date_to": "2026-09-01"}):
            response = await c.get(path, params=params)
            assert response.status_code == 403 and response.json()["detail"] == "Only an agency Master can view commissions", response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [REPORT, CSV], ids=["json", "csv"])
@pytest.mark.parametrize("role", ["overseas_admin", "overseas_student"])
async def test_non_agents_are_refused(db_session, path, role):  # AC08
    user = await mk_user(db_session, role=role)
    async with client_for(user.email) as c:
        assert (await c.get(path)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [REPORT, CSV], ids=["json", "csv"])
async def test_report_requires_authentication(client, path):  # AC08
    assert (await client.get(path)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [REPORT, CSV], ids=["json", "csv"])
async def test_a_suspended_agency_is_refused(db_session, path):  # AC08
    ctx = await mk_active_org(db_session, name=f"Suspended {uniq()}")
    async with client_for(ctx["master"].email) as c:  # signed in while active, then the agency is suspended
        org = await db_session.get(AgentOrg, ctx["org"].id, populate_existing=True)
        org.status = "suspended"
        await db_session.commit()
        assert (await c.get(path)).status_code == 403


# --- CSV export (AC07) ---------------------------------------------------------------------------------------------------------

HEADER = ["Student", "University", "Country", "Intake", "Status", "Amount", "Currency", "Created", "Claimed", "Paid", "Claim reference"]


def _csv_rows(response):
    return list(csv.reader(io.StringIO(response.text)))


@pytest.mark.asyncio
async def test_csv_has_one_row_per_commission_with_the_filter(db_session):  # AC07
    ctx = await mk_active_org(db_session, name=f"Csv {uniq()}")
    reference = uniq("CLM")
    await mk_commission(
        db_session, ctx, amount=1234.5, student_name="Asha Rao", university_name="Gamma U", country_name="Gland", intake="Sep 2027",
        created_at=_day(2026, 9, 15), claim_reference=reference,
    )
    await mk_commission(db_session, ctx, amount=5, created_at=_day(2026, 10, 15))
    async with client_for(ctx["master"].email) as c:
        response = await c.get(CSV, params={"date_from": "2026-09-01", "date_to": "2026-09-30"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == "attachment; filename=agency-commissions-2026-09-01-to-2026-09-30.csv"
    assert response.headers["cache-control"] == "private, no-store"
    rows = _csv_rows(response)
    assert rows[0] == HEADER
    assert rows[1:] == [["Asha Rao", "Gamma U", "Gland", "Sep 2027", "paid", "1234.50", "INR", "2026-09-15", "", "", reference]]


@pytest.mark.asyncio
async def test_empty_csv_is_header_only_and_named_all(db_session):  # AC07
    ctx = await mk_active_org(db_session, name=f"CsvEmpty {uniq()}")
    async with client_for(ctx["master"].email) as c:
        response = await c.get(CSV)
    assert response.status_code == 200 and _csv_rows(response) == [HEADER]
    assert response.headers["content-disposition"] == "attachment; filename=agency-commissions-all-to-all.csv"


@pytest.mark.asyncio
async def test_csv_neutralises_formulas(db_session):  # AC07, Review Focus 4
    ctx = await mk_active_org(db_session, name=f"CsvFormula {uniq()}")
    reference = "-" + uniq("CLM")
    await mk_commission(db_session, ctx, student_name="=HYPERLINK(1)", university_name="+U", intake="@Sep", claim_reference=reference)
    async with client_for(ctx["master"].email) as c:
        row = _csv_rows(await c.get(CSV))[1]
    assert row[0] == "'=HYPERLINK(1)" and row[1] == "'+U" and row[3] == "'@Sep" and row[10] == "'" + reference


@pytest.mark.asyncio
async def test_csv_names_a_student_without_a_login(db_session):  # Review Focus 1
    ctx = await mk_active_org(db_session, name=f"CsvNologin {uniq()}")
    await mk_commission(db_session, ctx, student=False)
    async with client_for(ctx["master"].email) as c:
        assert _csv_rows(await c.get(CSV))[1][0] == "—"


# --- Dashboard Revenue (AC04) --------------------------------------------------------------------------------------------------

DASHBOARD = "/api/v1/portal/overseas/agent/dashboard"


def _metric(payload, label):
    return next((m["value"] for m in payload["metrics"] if m["label"] == label), None)


@pytest.mark.asyncio
async def test_master_dashboard_shows_paid_revenue(db_session):  # AC04
    ctx = await mk_active_org(db_session, name=f"Revenue {uniq()}")
    await mk_commission(db_session, ctx, status="paid", amount=12000)
    await mk_commission(db_session, ctx, status="claimed", amount=999)
    other = await mk_active_org(db_session, name=f"RevOther {uniq()}")
    await mk_commission(db_session, other, status="paid", amount=5)
    async with client_for(ctx["master"].email) as c:
        payload = (await c.get(DASHBOARD)).json()
    assert _metric(payload, "Revenue") == "INR 12,000"
    assert [m["label"] for m in payload["metrics"]][:5] == ["Students", "Applications", "Claimable commission", "Claims", "Revenue"]


@pytest.mark.asyncio
async def test_revenue_is_inr_0_when_nothing_is_paid(db_session):  # AC04
    ctx = await mk_active_org(db_session, name=f"RevZero {uniq()}")
    await mk_commission(db_session, ctx, status="eligible", amount=700)
    async with client_for(ctx["master"].email) as c:
        assert _metric((await c.get(DASHBOARD)).json(), "Revenue") == "INR 0"


@pytest.mark.asyncio
async def test_revenue_is_per_currency(db_session):  # Review Focus 2
    ctx = await mk_active_org(db_session, name=f"RevCur {uniq()}")
    await mk_commission(db_session, ctx, status="paid", amount=12000, currency="INR")
    await mk_commission(db_session, ctx, status="paid", amount=500, currency="USD")
    async with client_for(ctx["master"].email) as c:
        assert _metric((await c.get(DASHBOARD)).json(), "Revenue") == "INR 12,000 · USD 500"


@pytest.mark.asyncio
async def test_staff_dashboard_has_no_revenue(db_session):  # AC04
    ctx = await mk_active_org(db_session, name=f"RevStaff {uniq()}")
    await mk_commission(db_session, ctx, status="paid", amount=12000)
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as c:
        payload = (await c.get(DASHBOARD)).json()
    assert _metric(payload, "Revenue") is None and "commission" not in str(payload).lower()
