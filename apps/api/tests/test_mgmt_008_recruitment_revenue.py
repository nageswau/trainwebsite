"""mgmt-008 -- the Recruitment & Placement revenue dashboard (spec RR1-RR12; AC1: revenue per placement = recruitment revenue ÷ joined;
AC2: the KPIs match rec-033), read with `GET /management/revenue/recruitment`.

The stack DB is shared and never emptied, so each test works in a random far-past month and compares company-wide figures before and
after (deltas), or against the rec-033 / snapshot endpoints read in the same test."""

import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import Candidate, Company, Job, JobApplication, JobOffer, RecCandidateSource
from app.services import candidates as candidate_svc
from tests.bdm001_helpers import login, make_user
from tests.test_mgmt_004_ledger import TODAY, as_user, category, create, post
from tests.test_mgmt_005_auto_lines import recruiter_payment

REVENUE = "/api/v1/management/revenue/recruitment"
FLOW = {"candidates": "candidates_sourced", "interviews": "interviews", "selections": "selected", "joining": "joined"}
KPIS = ["recruiters", "partner_companies", "open_positions", "candidates", "interviews", "selections", "joining", "placement_pct", "revenue_per_placement"]


def a_month() -> tuple[int, int]:
    return random.randint(2001, 2025), random.randint(1, 12)


def month_param(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def tag() -> str:
    return uuid.uuid4().hex[:8]


def money(value) -> Decimal:
    return Decimal(value)


async def dashboard(client, month: str | None = None, period: str | None = None) -> dict:
    params = {k: v for k, v in {"month": month, "period": period}.items() if v}
    response = await client.get(REVENUE, params=params or None)
    assert response.status_code == 200, response.text
    return response.json()


async def joined_offer(db, on: date) -> JobOffer:
    """One candidate who joined on `on` (rec-033 P8), on an unassigned requirement of a fresh company."""
    creator = await make_user(db, "placement_team", "global")
    company = Company(name=f"Mgmt008 Co {tag()}")
    db.add(company)
    await db.flush()
    job = Job(company_id=company.id, title=f"Java {tag()}", location="Pune", description="", skills=[], status="sourcing")
    db.add(job)
    await db.flush()
    source = await db.scalar(select(RecCandidateSource).where(func.lower(RecCandidateSource.name) == "referral"))
    candidate = Candidate(
        candidate_code=await candidate_svc.next_code(db), source_id=source.id, created_by_user_id=creator.id, name=f"Asha {tag()}", email=f"{tag()}@example.com", preferred_locations=[]
    )
    db.add(candidate)
    await db.flush()
    application = JobApplication(job_id=job.id, candidate_id=candidate.id, status="joined")
    db.add(application)
    await db.flush()
    offer = JobOffer(application_id=application.id, offered_on=on, status="accepted", joining_status="joined", actual_joining_date=on)
    db.add(offer)
    await db.commit()
    return offer


async def approved_income(client, db, category_id: str, on: date, amount: str, *, vertical: str = "recruitment") -> dict:
    """An accountant's income entry, approved by a partner. Leaves the partner signed in."""
    await as_user(client, db)
    entry = await create(client, category_id, kind="income", entry_date=on.isoformat(), amount=amount, vertical=vertical)
    assert (await post(client, entry["id"], "submit")).status_code == 200
    await as_user(client, db, "partner")
    assert (await post(client, entry["id"], "approve")).status_code == 200
    return entry


def kind(data: dict, label: str) -> dict | None:
    found = [k for k in data["revenue"]["kinds"] if k["label"] == label]
    return found[0] if found else None


# --- access (RR9, M13) --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partner", "accountant"])
async def test_finance_tier_reads_revenue_and_every_kpi(client, db_session, role):
    await as_user(client, db_session, role)
    data = await dashboard(client)
    assert data["revenue_visible"] is True
    assert data["revenue"]["kinds"][0] == {**data["revenue"]["kinds"][0], "key": "recruiter_invoices", "label": "Recruiter invoice payments"}
    assert list(data["kpis"]) == KPIS


@pytest.mark.asyncio
async def test_super_admin_reads_the_kpis_without_any_money(client, db_session):
    await login(client, await make_user(db_session, "super_admin", "global"))
    data = await dashboard(client)
    assert data["revenue_visible"] is False
    assert data["revenue"] is None
    assert data["kpis"]["revenue_per_placement"] is None
    assert list(data["kpis"]) == KPIS


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("it_admin", "it"), ("placement_manager", "global"), ("student", "it")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await login(client, await make_user(db_session, role, division))
    response = await client.get(REVENUE)
    assert response.status_code == 403
    assert response.json()["detail"] == "Management access required"


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(REVENUE)).status_code == 401


# --- period and validation (RR1) ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_default_is_the_current_ist_month_and_kpis_count_to_today(client, db_session):
    await as_user(client, db_session)
    data = await dashboard(client)
    assert (data["month"], data["period"], data["start"]) == (TODAY.strftime("%Y-%m"), "month", TODAY.replace(day=1).isoformat())
    assert data["kpi_end"] == TODAY.isoformat()  # rec-033 refuses a range ending in the future (RR5)


@pytest.mark.asyncio
async def test_a_past_month_counts_to_its_last_day_and_the_year_from_april(client, db_session):
    await as_user(client, db_session)
    data = await dashboard(client, "2024-02", "year")
    assert (data["start"], data["end"], data["kpi_end"]) == ("2023-04-01", "2024-02-29", "2024-02-29")
    assert data["label"] == "Financial year 2023-24 to date"
    assert (await dashboard(client, "2024-02"))["label"] == "February 2024"


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"month": "2026-13"}, {"month": "abc"}, {"month": "1999-12"}, {"period": "week"}])
async def test_bad_period_is_422(client, db_session, params):
    await as_user(client, db_session)
    assert (await client.get(REVENUE, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_a_future_month_is_422(client, db_session):
    await as_user(client, db_session)
    later = (TODAY.replace(day=1) + timedelta(days=32)).strftime("%Y-%m")
    response = await client.get(REVENUE, params={"month": later})
    assert response.status_code == 422
    assert response.json()["detail"] == "Choose this month or an earlier one"


# --- revenue (RR2-RR4) --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_invoice_payments_and_recruitment_ledger_income_are_the_kinds(client, db_session):
    year, month = a_month()
    on = date(year, month, 10)
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    await recruiter_payment(db_session, on=on, amount="45000.00")
    internships = await category(client, kind="income", name=f"Internship programs {tag()}")
    await approved_income(client, db_session, internships["id"], on, "12000.00")
    other_vertical = await category(client, kind="income", name=f"Not recruitment {tag()}")
    await approved_income(client, db_session, other_vertical["id"], on, "7000.00", vertical="it")  # another vertical (RR2)
    await as_user(client, db_session)
    await create(client, internships["id"], kind="income", entry_date=on.isoformat(), amount="999.00", vertical="recruitment")  # a draft
    after = await dashboard(client, month_param(year, month))

    invoices_before, invoices_after = kind(before, "Recruiter invoice payments"), kind(after, "Recruiter invoice payments")
    assert money(invoices_after["amount"]) - money(invoices_before["amount"]) == Decimal("45000.00")
    assert money(kind(after, internships["name"])["amount"]) == Decimal("12000.00")
    assert kind(after, internships["name"])["key"] == f"ledger:{internships['name']}"
    assert kind(after, other_vertical["name"]) is None
    assert money(after["revenue"]["total"]) - money(before["revenue"]["total"]) == Decimal("57000.00")
    assert money(after["revenue"]["total"]) == sum((money(k["amount"]) for k in after["revenue"]["kinds"]), Decimal(0))  # RR4


@pytest.mark.asyncio
async def test_a_category_reversed_in_the_same_month_is_not_listed(client, db_session):
    await as_user(client, db_session)
    corporate = await category(client, kind="income", name=f"Corporate training {tag()}")
    entry = await approved_income(client, db_session, corporate["id"], TODAY, "3000.00")
    await as_user(client, db_session)
    reversal = await post(client, entry["id"], "reverse", reason="Booked twice")  # dated today, submitted (ML11)
    assert reversal.status_code == 201, reversal.text
    await as_user(client, db_session, "partner")
    assert (await post(client, reversal.json()["id"], "approve")).status_code == 200
    assert kind(await dashboard(client), corporate["name"]) is None  # nets to zero (RR4)


@pytest.mark.asyncio
async def test_the_financial_year_sums_its_months(client, db_session):
    year = random.randint(2001, 2024)
    await as_user(client, db_session)
    may, june = date(year, 5, 3), date(year, 6, 3)
    totals_before = [money((await dashboard(client, m))["revenue"]["total"]) for m in (f"{year}-05", f"{year}-06")]
    year_before = money((await dashboard(client, f"{year}-06", "year"))["revenue"]["total"])
    await recruiter_payment(db_session, on=may, amount="1000.00")
    await recruiter_payment(db_session, on=june, amount="2000.00")
    year_after = money((await dashboard(client, f"{year}-06", "year"))["revenue"]["total"])
    assert year_after - year_before == Decimal("3000.00")
    assert [money((await dashboard(client, m))["revenue"]["total"]) - b for m, b in zip((f"{year}-05", f"{year}-06"), totals_before, strict=True)] == [
        Decimal("1000.00"), Decimal("2000.00"),
    ]


# --- KPIs (RR5-RR8, AC1, AC2) -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_revenue_per_placement_is_revenue_over_joined(client, db_session):
    year, month = a_month()
    on = date(year, month, 20)
    await recruiter_payment(db_session, on=on, amount="90000.00")
    await joined_offer(db_session, on)
    await joined_offer(db_session, on)
    await as_user(client, db_session)
    data = await dashboard(client, month_param(year, month))
    joining = data["kpis"]["joining"]
    assert joining >= 2
    expected = (money(data["revenue"]["total"]) / joining).quantize(Decimal("0.01"))
    assert money(data["kpis"]["revenue_per_placement"]) == expected


@pytest.mark.asyncio
async def test_ac2_flow_kpis_match_the_rec_033_total_and_placement_pct_follows(client, db_session):
    year, month = a_month()
    await joined_offer(db_session, date(year, month, 5))
    await login(client, await make_user(db_session, "super_admin", "global"))
    data = await dashboard(client, month_param(year, month))
    rec = await client.get("/api/v1/recruiter/performance", params={"from": data["start"], "to": data["kpi_end"]})
    assert rec.status_code == 200, rec.text
    totals = rec.json()["totals"]
    assert {kpi: data["kpis"][kpi] for kpi in FLOW} == {kpi: totals[key] for kpi, key in FLOW.items()}
    kpis = data["kpis"]
    expected = round(kpis["joining"] * 100 / kpis["candidates"], 1) if kpis["candidates"] else None
    assert kpis["placement_pct"] == expected  # RR7


@pytest.mark.asyncio
async def test_a_month_nobody_joined_has_no_ratios(client, db_session):
    await as_user(client, db_session)
    data = await dashboard(client, "2000-01")  # before any test data
    assert data["kpis"]["joining"] == 0
    assert data["kpis"]["revenue_per_placement"] is None
    if data["kpis"]["candidates"] == 0:
        assert data["kpis"]["placement_pct"] is None


@pytest.mark.asyncio
async def test_stock_kpis_match_the_snapshot_and_the_open_requirements(client, db_session):
    await as_user(client, db_session, "partner")
    data = await dashboard(client)
    snapshot = {k["key"]: k["value"] for k in (await client.get("/api/v1/management/snapshot")).json()["kpis"]}
    assert (data["kpis"]["recruiters"], data["kpis"]["partner_companies"]) == (snapshot["recruiters"], snapshot["partner_companies"])


@pytest.mark.asyncio
async def test_open_positions_count_requirements_in_an_open_status(client, db_session):
    await as_user(client, db_session)
    before = (await dashboard(client))["kpis"]["open_positions"]
    company = Company(name=f"Mgmt008 Open {tag()}")
    db_session.add(company)
    await db_session.flush()
    for status in ("sourcing", "requirement_received", "on_hold", "closed", "cancelled"):  # RR6: rec-035 M3's open statuses
        db_session.add(Job(company_id=company.id, title=f"Role {tag()}", location="Pune", description="", skills=[], status=status))
    await db_session.commit()
    assert (await dashboard(client))["kpis"]["open_positions"] - before == 2
