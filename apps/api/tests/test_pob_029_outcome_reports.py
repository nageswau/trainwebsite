"""pob-029 -- placement outcome reports (DEC-SCOPE-437 R1-R12; AC: each figure ties out to its definition and the conversions are the
period's own counts; +/−/E: a period with placements but no invoices). The shared test database is never truncated, so every report here
is narrowed to this test's company."""

import csv
import io
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, JobOffer, PlacementSurvey
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user
from tests.test_pob_024_placements import PLACEMENTS, _accept, _issue_body, _join, _world
from tests.test_pob_025_guarantee import _dropout, _guaranteed, _second_hire
from tests.test_pob_026_surveys import _joined, _surveys, _sweep
from tests.test_rec_022_offers import _status

REPORT = "/api/v1/recruiter/reports/placement-outcomes"
TODAY = date.today()


async def _report(client, s, **params) -> dict:
    response = await client.get(REPORT, params={"company": str(s["job"].company_id), **params})
    assert response.status_code == 200, response.text
    return response.json()


async def _two_placements(client, db) -> dict:
    """One joined hire with an issued invoice part paid, and a second accepted offer on the same requirement still pending."""
    s = await _world(client, db)
    placement_id = (await _accept(client, s))["placement_id"]
    await _join(client, s)
    issued = await client.post(f"{PLACEMENTS}/{placement_id}/invoice-draft/issue", json=_issue_body())
    assert issued.status_code == 201, issued.text
    invoice_id = issued.json()["placement"]["commercials"]["invoice"]["invoice"]["id"]
    paid = await client.post(f"/api/v1/recruiter/invoices/{invoice_id}/payments", json={"received_on": TODAY.isoformat(), "amount": "20000.00"})
    assert paid.status_code == 201, paid.text
    second = await _second_hire(client, db, s)
    assert (await _status(client, second["offer"]["id"], "accepted")).status_code == 200
    s["placement_id"] = placement_id
    return s


def _sum(rows: list[dict], key: str) -> int:
    return sum(row["figures"][key] for row in rows)


# --- AC: each figure ties out to its definition -------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_figures_tie_out_to_the_placements_behind_them(client, db_session):
    s = await _two_placements(client, db_session)
    await login(client, s["manager"])
    data = await _report(client, s)
    t = data["totals"]
    assert (t["placements"], t["joined"], t["pending"], t["did_not_join"]) == (2, 1, 1, 0)
    assert (t["joining_rate"], t["time_to_fill_days"]) == (100.0, 0.0)  # joined ÷ decided; the requirement was opened today
    assert data["revenue_visible"] is True
    assert (t["fee_generated"], t["invoiced"], t["collected"], t["outstanding"]) == ("50000.00", "50000.00", "20000.00", "30000.00")
    assert len(data["placements"]) == 2 and data["placements_total"] == 2  # the drill-down is the cohort itself
    assert {p["status"] for p in data["placements"]} == {"joined", "pending"}
    for group in ("company", "vendor", "role", "source", "recruiter", "po"):
        rows = (await _report(client, s, group_by=group))["items"]
        assert _sum(rows, "placements") == 2 and _sum(rows, "joined") == 1, group
    by_recruiter = (await _report(client, s, group_by="recruiter"))["items"]
    assert [row["label"] for row in by_recruiter] == [s["recruiter"].full_name]
    assert [row["label"] for row in (await _report(client, s, group_by="vendor"))["items"]] == ["Direct"]
    assert [row["label"] for row in (await _report(client, s, group_by="po"))["items"]] == [s["recruiter"].full_name]  # pob-024 P6


@pytest.mark.asyncio
async def test_the_conversions_count_the_period(client, db_session):
    s = await _two_placements(client, db_session)
    await login(client, s["manager"])
    f = (await _report(client, s))["funnel"]
    assert (f["requirements"], f["submissions"], f["interviews"], f["offers"], f["offers_accepted"], f["offers_declined"]) == (1, 0, 0, 2, 2, 0)
    assert (f["offer_acceptance"], f["interview_to_offer"], f["submission_to_interview"]) == (100.0, None, None)  # nothing to divide by → None
    old = await _report(client, s, **{"from": (TODAY - timedelta(days=40)).isoformat(), "to": (TODAY - timedelta(days=35)).isoformat()})
    assert (old["totals"]["placements"], old["funnel"]["offers"], old["placements"]) == (0, 0, [])


# --- +/−/E: placements but no invoices ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_period_with_placements_but_no_invoices(client, db_session):
    s = await _world(client, db_session)
    await _accept(client, s)
    await _join(client, s)
    await login(client, s["manager"])
    t = (await _report(client, s))["totals"]
    assert (t["placements"], t["joined"], t["fee_generated"], t["invoiced"], t["collected"], t["outstanding"]) == (1, 1, "50000.00", "0.00", "0.00", "0.00")


@pytest.mark.asyncio
async def test_dropouts_replacements_and_satisfaction(client, db_session, recruiter_emails_enqueued):
    s = await _guaranteed(client, db_session)
    assert (await _dropout(client, s["placement_id"])).status_code == 200
    await login(client, s["manager"])
    t = (await _report(client, s))["totals"]
    assert (t["dropouts"], t["early_dropouts"], t["replacements_owed"], t["replacements_filled"]) == (1, 1, 1, 0)
    rated = await _joined(client, db_session)
    await _sweep()
    survey = (await _surveys(db_session, rated["placement_id"]))["client"]
    survey.rating, survey.responded_at = 4, datetime.now(UTC)
    await db_session.commit()
    await login(client, rated["manager"])
    t = (await _report(client, rated,**{"from": (TODAY - timedelta(days=60)).isoformat()}))["totals"]
    assert (t["client_rating"], t["client_responses"], t["candidate_rating"], t["candidate_responses"]) == (4.0, 1, None, 0)
    assert await db_session.scalar(select(PlacementSurvey.rating).where(PlacementSurvey.id == survey.id)) == 4


@pytest.mark.asyncio
async def test_a_joining_dated_before_the_requirement_counts_as_zero_days(client, db_session):
    """QA-03: a joining dated before the requirement was recorded (a legacy or backfilled row) never makes the time to fill negative."""
    s = await _world(client, db_session)
    await _accept(client, s)
    await _join(client, s)
    offer = await db_session.scalar(select(JobOffer).where(JobOffer.id == s["offer"]["id"]))
    offer.actual_joining_date = TODAY - timedelta(days=5)
    await db_session.commit()
    await login(client, s["manager"])
    assert (await _report(client, s))["totals"]["time_to_fill_days"] == 0.0


# --- filters ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_filters_narrow_the_cohort(client, db_session):
    s = await _two_placements(client, db_session)
    await login(client, s["manager"])
    assert (await _report(client, s, recruiter=str(s["recruiter"].id)))["totals"]["placements"] == 2
    assert (await _report(client, s, recruiter=str(s["manager"].id)))["totals"]["placements"] == 0
    assert (await _report(client, s, vendor=str(s["job"].company_id)))["totals"]["placements"] == 0
    bad = await client.get(REPORT, params={"group_by": "planet"})
    assert bad.status_code == 422
    future = await client.get(REPORT, params={"to": (TODAY + timedelta(days=1)).isoformat()})
    assert future.status_code == 422


# --- AuthZ: Team Lead and administrators; revenue behind pob-001 -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_only_team_leads_and_administrators_read_it(client, db_session):
    s = await _world(client, db_session)
    await _accept(client, s)
    assert (await client.get(REPORT)).status_code == 403  # a recruiter
    assert (await client.get(f"{REPORT}.csv")).status_code == 403
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await _report(client, s))["totals"]["placements"] == 1
    other_manager = await make_pm(db_session)
    await make_recruiter(db_session, other_manager)
    await login(client, other_manager)
    assert (await _report(client, s))["totals"]["placements"] == 0  # another team's company is out of scope


@pytest.mark.asyncio
async def test_revenue_is_hidden_without_the_commercial_grant(client, db_session, monkeypatch):
    from app.services import placements

    s = await _two_placements(client, db_session)
    await login(client, s["manager"])

    async def no(*_args, **_kwargs):
        return False

    monkeypatch.setattr(placements, "commercial", no)
    data = await _report(client, s)
    assert data["revenue_visible"] is False
    assert all(data["totals"][k] is None for k in ("fee_generated", "invoiced", "collected", "outstanding"))
    assert "fee_generated" not in {c["key"] for c in data["columns"]}


# --- export: the table, audited, formula-safe ----------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_export_is_the_table_and_is_audited(client, db_session):
    s = await _two_placements(client, db_session)
    await login(client, s["manager"])
    response = await client.get(f"{REPORT}.csv", params={"company": str(s["job"].company_id), "group_by": "recruiter"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv") and "attachment" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text.lstrip("﻿"))))
    assert rows[0][0] == "Recruiter" and rows[1][0] == s["recruiter"].full_name and rows[-1][0] == "Total"
    assert len(rows) == 3
    xlsx = await client.get(f"{REPORT}.xlsx", params={"company": str(s["job"].company_id)})
    assert xlsx.status_code == 200
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "placement_outcomes.export", AuditLog.user_id == s["manager"].id))).all()
    assert len(audits) == 2 and audits[0].metadata_json["group_by"] in {"recruiter", "company"}
