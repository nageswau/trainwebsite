"""mgmt-025 -- the company-wide Recruitment dashboard (spec RC1-RC12; AC: totals equal rec-035's), read with `GET /management/recruitment`.

The stack DB is shared and never emptied, so stock figures are asserted as deltas or against the rec-035 / snapshot endpoints read in the
same test, and period figures over one far-past day (or month) that no other test writes to."""

import random
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest

from app.models import Company, CompanyStageHistory, Interview, JobApplication, JobApplicationStatusHistory
from app.services.bdm_appointments import IST
from tests.rec001_helpers import as_role, make_recruiter
from tests.test_mgmt_004_ledger import as_user, category
from tests.test_mgmt_005_auto_lines import recruiter_payment
from tests.test_mgmt_008_recruitment_revenue import approved_income
from tests.test_rec_035_management import _application, _company, _job, _joined

URL = "/api/v1/management/recruitment"
KPIS = [
    "recruiters", "employer_partners", "new_companies", "job_openings", "internship_openings", "candidates", "interviews", "selections",
    "joining", "placement_rate", "revenue",
]  # fmt: skip
PIPELINE = ["lead", "meeting", "requirement", "candidate", "interview", "selection", "joining"]


def _quiet_day() -> date:
    """A random day years back: only this test writes period events on it."""
    return date(2003, 1, 1) + timedelta(days=random.randrange(8 * 365))


def _at(day: date) -> datetime:
    return datetime.combine(day, time(11), tzinfo=IST)


def _day(day: date) -> dict:
    return {"date_from": day.isoformat(), "date_to": day.isoformat()}


async def _read(client, **params) -> dict:
    response = await client.get(URL, params=params or None)
    assert response.status_code == 200, response.text
    return response.json()


async def _partner(client, db):
    return await as_role(client, db, "partner", "global")


# --- shape ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_eleven_kpis_and_the_seven_pipeline_steps_in_source_order(client, db_session):
    await _partner(client, db_session)
    payload = await _read(client)
    assert list(payload["kpis"]) == KPIS
    assert [step["key"] for step in payload["pipeline"]] == PIPELINE
    assert [step["label"] for step in payload["pipeline"]] == ["Lead", "Meeting", "Requirement", "Candidate", "Interview", "Selection", "Joining"]
    assert set(payload) == {"date_from", "date_to", "revenue_visible", "kpis", "pipeline", "requirement_closed", "lost"}


# --- AC: the totals are rec-035's ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_kpis_equal_rec_035_totals_for_the_same_period(client, db_session):
    db = db_session
    day = _quiet_day()
    me = await make_recruiter(db)
    company = await _company(db, me)
    job = await _job(db, company, me)
    application = await _joined(db, job, me, day)
    db.add(Interview(application_id=application.id, scheduled_at=_at(day), status="completed"))
    db.add(JobApplicationStatusHistory(application_id=application.id, from_status="sourced", to_status="selected", created_at=_at(day)))
    await _application(db, job, me, status="interview")
    await db.commit()

    await as_role(client, db, "super_admin", "global")
    rec035 = (await client.get("/api/v1/recruiter/management", params={"from": day.isoformat(), "to": day.isoformat()})).json()["totals"]
    kpis = (await _read(client, **_day(day)))["kpis"]
    assert (kpis["interviews"], kpis["selections"], kpis["joining"]) == (1, 1, 1)
    assert kpis["employer_partners"] == rec035["companies"]
    assert kpis["candidates"] == rec035["candidates_in_pipeline"]
    assert (kpis["interviews"], kpis["selections"], kpis["joining"]) == (rec035["interviews"], rec035["selected"], rec035["joined"])
    assert kpis["job_openings"] + kpis["internship_openings"] == rec035["open_requirements"]


@pytest.mark.asyncio
async def test_recruiters_is_the_snapshot_s15(client, db_session):
    await _partner(client, db_session)
    await make_recruiter(db_session)
    snapshot = (await client.get("/api/v1/management/snapshot")).json()["kpis"]
    s15 = next(kpi["value"] for kpi in snapshot if kpi["key"] == "recruiters")
    assert (await _read(client))["kpis"]["recruiters"] == s15


# --- RC6: job / internship openings -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_open_requirements_split_into_job_and_internship_openings(client, db_session):
    db = db_session
    await _partner(client, db)
    before = (await _read(client))["kpis"]
    company = await _company(db, None)
    await _job(db, company, employment_type="internship")
    await _job(db, company, employment_type="full_time")
    await _job(db, company)  # no type -> a job opening
    await _job(db, company, employment_type="internship", status="closed")  # not open
    await _job(db, company, employment_type="full_time", status="on_hold")  # parked
    await db.commit()
    after = (await _read(client))["kpis"]
    assert (after["job_openings"] - before["job_openings"], after["internship_openings"] - before["internship_openings"]) == (2, 1)


# --- RC5: new companies -------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_new_companies_count_the_first_move_past_interested_in_the_period(client, db_session):
    db = db_session
    day = _quiet_day()
    fresh, earlier, early_lead = [await _company(db, None) for _ in range(3)]

    def move(company: Company, from_stage: str, to_stage: str, on: date) -> CompanyStageHistory:
        return CompanyStageHistory(company_id=company.id, from_stage=from_stage, to_stage=to_stage, event="moved", created_at=_at(on))

    db.add(move(early_lead, "new_lead", "interested", day))  # not past Interested
    db.add(move(fresh, "interested", "meeting_scheduled", day))  # counted
    db.add(move(fresh, "meeting_scheduled", "requirement_received", day))  # the same company again -> once
    db.add(move(earlier, "interested", "meeting_scheduled", day - timedelta(days=1)))  # crossed before the period
    db.add(move(earlier, "meeting_scheduled", "requirement_received", day))
    await db.commit()
    await _partner(client, db)
    assert (await _read(client, **_day(day)))["kpis"]["new_companies"] == 1


# --- RC7: placement rate -----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_placement_rate_is_joining_over_candidates_sourced(client, db_session):
    db = db_session
    day = _quiet_day()
    me = await make_recruiter(db)
    job = await _job(db, await _company(db, me), me)
    await _joined(db, job, me, day)
    for _ in range(3):
        await _application(db, job, me, status="sourced")
    await db.commit()
    await _backdate_applications(db, job.id, day)

    await as_role(client, db, "super_admin", "global")
    performance = (await client.get("/api/v1/recruiter/performance", params={"from": day.isoformat(), "to": day.isoformat()})).json()["totals"]
    kpis = (await _read(client, **_day(day)))["kpis"]
    assert (performance["candidates_sourced"], performance["joined"]) == (4, 1)
    assert kpis["placement_rate"] == 25.0
    empty = date(1995, 1, 1) + timedelta(days=random.randrange(2000))  # nobody sourced -> "—"
    assert (await _read(client, **_day(empty)))["kpis"]["placement_rate"] is None


async def _backdate_applications(db, job_id, day: date) -> None:
    """rec-033 P4 counts applications by `created_at`; the helpers stamp now."""
    await db.execute(JobApplication.__table__.update().where(JobApplication.job_id == job_id).values(created_at=_at(day)))
    await db.commit()


# --- RC9: the company pipeline -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_pipeline_groups_live_companies_by_their_rec_005_stage(client, db_session):
    db = db_session
    await _partner(client, db)
    before = await _read(client)
    stages = {
        "lead": ["new_lead", "contacted", "interested"], "meeting": ["meeting_scheduled", "requirement_discussion"],
        "requirement": ["requirement_received", "jd_received"], "candidate": ["candidates_sourcing", "profiles_shared"],
        "interview": ["interview"], "selection": ["selected"], "joining": ["joined"],
    }  # fmt: skip
    for group in stages.values():
        for stage in group:
            await _company(db, None, stage=stage)
    await _company(db, None, stage="requirement_closed")
    await _company(db, None, stage="interview", lost_at=datetime.now(UTC), lost_reason="No budget")  # lost: only in `lost`
    await _company(db, None, stage="selected", archived_at=datetime.now(UTC))  # archived: nowhere
    await db.commit()
    after = await _read(client)

    def steps(payload) -> dict:
        return {step["key"]: step["value"] for step in payload["pipeline"]}

    assert {key: steps(after)[key] - steps(before)[key] for key in PIPELINE} == {key: len(group) for key, group in stages.items()}
    assert (after["requirement_closed"] - before["requirement_closed"], after["lost"] - before["lost"]) == (1, 1)


# --- RC8: revenue for the finance tier only -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_partner_sees_the_mgmt_008_revenue_and_the_super_admin_none(client, db_session):
    db = db_session
    year, month = random.randint(2001, 2024), random.randint(1, 12)
    on = date(year, month, 10)
    first, last = date(year, month, 1), (date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1))
    await recruiter_payment(db, on=on, amount="45000.00")
    await as_user(client, db)
    income = await category(client, kind="income", name=f"Corporate training {uuid.uuid4().hex[:8]}")
    await approved_income(client, db, income["id"], on, "5000.00")  # leaves a partner signed in

    payload = await _read(client, date_from=first.isoformat(), date_to=last.isoformat())
    mgmt008 = (await client.get("/api/v1/management/revenue/recruitment", params={"month": f"{year:04d}-{month:02d}"})).json()
    assert payload["revenue_visible"] is True
    assert Decimal(payload["kpis"]["revenue"]) == Decimal(mgmt008["revenue"]["total"]) >= Decimal("50000.00")

    await as_role(client, db, "super_admin", "global")
    hidden = await _read(client, date_from=first.isoformat(), date_to=last.isoformat())
    assert (hidden["revenue_visible"], hidden["kpis"]["revenue"]) == (False, None)


# --- RC1: the period ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_period_defaults_to_this_month_and_obeys_the_range_rules(client, db_session):
    await _partner(client, db_session)
    payload = await _read(client)
    today = date.fromisoformat(payload["date_to"])
    assert payload["date_from"] == today.replace(day=1).isoformat()
    future = today + timedelta(days=1)
    cases = [
        ({"date_to": future.isoformat()}, "The range can't end in the future"),
        ({"date_from": "2020-02-02", "date_to": "2020-02-01"}, "The start date must not be after the end date"),
        ({"date_from": "2019-01-01", "date_to": "2020-12-31"}, "The range can't be longer than 366 days"),
    ]
    for params, message in cases:
        response = await client.get(URL, params=params)
        assert (response.status_code, response.json()["detail"]) == (422, message)
    assert (await client.get(URL, params={"date_from": "2020-13-01"})).status_code == 422


# --- RC10: access -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partner", "super_admin"])
async def test_the_operational_tier_reads_it(client, db_session, role):
    await as_role(client, db_session, role, "global")
    assert (await client.get(URL)).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "division", "message"),
    [
        ("accountant", "global", "Operational access required"),
        ("placement_manager", "it", "Management access required"),
        ("placement_team", "it", "Management access required"),
        ("it_admin", "it", "Management access required"),
    ],
)
async def test_everyone_else_is_refused(client, db_session, role, division, message):
    await as_role(client, db_session, role, division)
    response = await client.get(URL)
    assert (response.status_code, response.json()["detail"]) == (403, message)


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401
