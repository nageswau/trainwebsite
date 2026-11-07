"""pob-009 -- PO targets (T3, AC2), territories (T4), target companies (T5), the daily plan (T6) and daily/weekly activity reports (T7, AC3)
with the contacts drill-down (T8, AC1). The shared test database is never truncated, so every case uses a fresh Team Lead and fresh POs."""

import uuid
from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company, CompanyContact, RecruiterFollowUp, RecruiterMessage
from app.services.bdm_appointments import IST, today_ist
from tests.rec001_helpers import login, make_pm, make_recruiter

API = "/api/v1/recruiter"


def _tag() -> str:
    return uuid.uuid4().hex[:8]


def _today():
    return today_ist(datetime.now(UTC))


def _month(shift: int = 0) -> str:
    first = _today().replace(day=1)
    index = first.year * 12 + first.month - 1 + shift
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


async def _team(db, size=1):
    lead = await make_pm(db)
    return lead, [await make_recruiter(db, lead) for _ in range(size)]


async def _company(db, po=None, **fields) -> Company:
    company = Company(name=f"Target {_tag()}", assigned_recruiter_user_id=po.id if po else None, **fields)
    db.add(company)
    await db.commit()
    return company


async def _sheet(client, url, **params) -> dict:
    response = await client.get(url, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _kpi(sheet: dict, key: str) -> dict:
    return next(k for k in sheet["kpis"] if k["key"] == key)


# --- T3 targets (AC2) --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_team_lead_sets_targets_and_the_po_sees_target_vs_actual(client, db_session):
    lead, (po,) = await _team(db_session)
    company = await _company(db_session, po)
    contact = CompanyContact(company_id=company.id, name=f"Ravi {_tag()}")
    db_session.add(contact)
    await db_session.flush()
    db_session.add(RecruiterMessage(company_id=company.id, contact_id=contact.id, sender_user_id=po.id, channel="whatsapp", body="Hi",
                                    sent_at=datetime.now(UTC), replied_at=datetime.now(UTC)))
    await db_session.commit()

    await login(client, lead)
    put = await client.put(f"{API}/manager/targets", json={"month": _month(), "items": [
        {"recruiter_user_id": str(po.id), "kpi_key": "outreach", "target": 4},
        {"recruiter_user_id": str(po.id), "kpi_key": "placements", "target": 2},
    ]})
    assert put.status_code == 200, put.text
    assert put.json()["changed"] == 2
    team = await _sheet(client, f"{API}/manager/targets", month=_month())
    row = next(r for r in team["items"] if r["recruiter"]["id"] == str(po.id))
    assert next(k for k in row["kpis"] if k["key"] == "outreach").items() >= {"target": 4, "achieved": 1, "percent": 25}.items()

    await login(client, po)
    mine = await _sheet(client, f"{API}/targets", month=_month())
    assert _kpi(mine, "outreach").items() >= {"target": 4, "achieved": 1, "percent": 25}.items()
    assert _kpi(mine, "meetings")["target"] is None and _kpi(mine, "meetings")["percent"] is None
    assert mine["response_rate"] == 100 and mine["editable"] is False


@pytest.mark.asyncio
async def test_a_mid_month_change_applies_at_once_and_is_audited(client, db_session):
    lead, (po,) = await _team(db_session)
    await login(client, lead)
    item = {"recruiter_user_id": str(po.id), "kpi_key": "meetings"}
    assert (await client.put(f"{API}/manager/targets", json={"month": _month(), "items": [item | {"target": 10}]})).status_code == 200
    assert (await client.put(f"{API}/manager/targets", json={"month": _month(), "items": [item | {"target": 6}]})).status_code == 200
    sheet = await _sheet(client, f"{API}/manager/targets/{po.id}", month=_month())
    assert _kpi(sheet, "meetings")["target"] == 6 and sheet["editable"] is True
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(po.id), AuditLog.action == "recruiter_target.set"))).all()
    assert [r.metadata_json["changes"] for r in rows][-1] == [{"kpi": "meetings", "from": 10, "to": 6}]
    cleared = await client.put(f"{API}/manager/targets", json={"month": _month(), "items": [item | {"target": None}]})
    assert cleared.json()["changed"] == 1
    assert _kpi(await _sheet(client, f"{API}/manager/targets/{po.id}", month=_month()), "meetings")["target"] is None


@pytest.mark.asyncio
async def test_target_rules_and_scope(client, db_session):
    lead, (po,) = await _team(db_session)
    _, (other,) = await _team(db_session)
    await login(client, lead)
    past = await client.put(f"{API}/manager/targets", json={"month": _month(-1), "items": [{"recruiter_user_id": str(po.id), "kpi_key": "outreach", "target": 1}]})
    assert past.status_code == 422
    far = await client.put(f"{API}/manager/targets", json={"month": _month(13), "items": [{"recruiter_user_id": str(po.id), "kpi_key": "outreach", "target": 1}]})
    assert far.status_code == 422
    bad = await client.put(f"{API}/manager/targets", json={"month": _month(), "items": [{"recruiter_user_id": str(po.id), "kpi_key": "revenue", "target": 1}]})
    assert bad.status_code == 422
    foreign = await client.put(f"{API}/manager/targets", json={"month": _month(), "items": [{"recruiter_user_id": str(other.id), "kpi_key": "outreach", "target": 1}]})
    assert foreign.status_code == 404
    assert (await client.get(f"{API}/manager/targets/{other.id}")).status_code == 404
    future = await _sheet(client, f"{API}/manager/targets/{po.id}", month=_month(1))
    assert future["month_status"] == "future" and _kpi(future, "outreach")["achieved"] is None
    await login(client, po)
    assert (await client.put(f"{API}/manager/targets", json={"month": _month(), "items": [{"recruiter_user_id": str(po.id), "kpi_key": "outreach", "target": 1}]})).status_code == 403
    assert (await client.get(f"{API}/manager/targets")).status_code == 403


# --- T4 territory, T5 target companies ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_territory_and_target_companies(client, db_session):
    lead, (po, peer) = await _team(db_session, size=2)
    territory = f"North {_tag()}"
    a = await _company(db_session, po, territory=territory)
    b = await _company(db_session, peer, territory=territory.upper())
    await _company(db_session, None, territory=territory)
    gone = await _company(db_session, po, territory=territory, archived_at=datetime.now(UTC))
    _, (stranger,) = await _team(db_session)
    foreign = await _company(db_session, stranger, territory=territory)

    await login(client, lead)
    put = await client.put(f"{API}/manager/team/{po.id}/territory", json={"territory": f"  {territory} "})
    assert put.status_code == 200 and put.json()["territory"] == territory
    added = await client.post(f"{API}/manager/target-companies", json={"recruiter_user_id": str(po.id), "month": _month(), "territory": territory.lower()})
    assert added.status_code == 201, added.text
    sheet = await _sheet(client, f"{API}/manager/targets/{po.id}", month=_month())
    ids = {row["company"]["id"] for row in sheet["target_companies"]}
    assert {str(a.id), str(b.id)} <= ids and str(gone.id) not in ids and str(foreign.id) not in ids
    assert sheet["territory"] == territory
    again = await client.post(f"{API}/manager/target-companies", json={"recruiter_user_id": str(po.id), "month": _month(), "company_ids": [str(a.id)]})
    assert again.status_code == 201 and again.json()["added"] == 0  # already on the list
    refused = await client.post(f"{API}/manager/target-companies", json={"recruiter_user_id": str(po.id), "month": _month(), "company_ids": [str(foreign.id)]})
    assert refused.status_code == 404
    both = await client.post(f"{API}/manager/target-companies", json={"recruiter_user_id": str(po.id), "month": _month(), "company_ids": [str(a.id)], "territory": "x"})
    assert both.status_code == 422
    row = next(r for r in sheet["target_companies"] if r["company"]["id"] == str(a.id))
    assert (await client.delete(f"{API}/manager/target-companies/{row['id']}")).status_code == 204
    assert (await client.delete(f"{API}/manager/target-companies/{row['id']}")).status_code == 404

    await login(client, po)
    mine = await _sheet(client, f"{API}/targets", month=_month())
    assert str(b.id) in {r["company"]["id"] for r in mine["target_companies"]}
    assert (await client.put(f"{API}/manager/team/{po.id}/territory", json={"territory": None})).status_code == 403


# --- T6 the daily plan -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_daily_plan_picks_due_follow_ups_and_target_companies(client, db_session):
    lead, (po,) = await _team(db_session)
    company = await _company(db_session, po)
    target = await _company(db_session, None)
    due = RecruiterFollowUp(company_id=company.id, reason="new_requirement", due_at=datetime.now(UTC) - timedelta(hours=1), created_by_user_id=po.id)
    later = RecruiterFollowUp(company_id=company.id, reason="new_requirement", due_at=datetime.now(UTC) + timedelta(days=3), created_by_user_id=po.id)
    db_session.add_all([due, later])
    await db_session.commit()
    await login(client, lead)
    assert (await client.post(f"{API}/manager/target-companies", json={"recruiter_user_id": str(po.id), "month": _month(), "company_ids": [str(target.id)]})).status_code == 201

    await login(client, po)
    plan = await _sheet(client, f"{API}/daily-plan")
    assert plan["editable"] is True and plan["items"] == []
    assert str(due.id) in {s["follow_up"]["id"] for s in plan["suggested_follow_ups"]}
    assert str(later.id) not in {s["follow_up"]["id"] for s in plan["suggested_follow_ups"]}
    assert str(target.id) in {s["id"] for s in plan["suggested_companies"]}

    first = await client.post(f"{API}/daily-plan/items", json={"follow_up_id": str(due.id)})
    assert first.status_code == 201, first.text
    assert (await client.post(f"{API}/daily-plan/items", json={"follow_up_id": str(due.id)})).status_code == 409
    assert (await client.post(f"{API}/daily-plan/items", json={"company_id": str(target.id)})).status_code == 201
    assert (await client.post(f"{API}/daily-plan/items", json={"company_id": str(company.id)})).status_code == 422  # not a target company
    item = first.json()
    done = await client.patch(f"{API}/daily-plan/items/{item['id']}", json={"done": True})
    assert done.status_code == 200 and done.json()["done_at"] is not None
    plan = await _sheet(client, f"{API}/daily-plan")
    assert len(plan["items"]) == 2 and plan["suggested_follow_ups"] == [] and plan["suggested_companies"] == []
    yesterday = await _sheet(client, f"{API}/daily-plan", date=str(_today() - timedelta(days=1)))
    assert yesterday["editable"] is False and yesterday["items"] == []
    assert (await client.get(f"{API}/daily-plan", params={"date": str(_today() + timedelta(days=1))})).status_code == 422

    _, (other,) = await _team(db_session)
    await login(client, other)
    assert (await client.patch(f"{API}/daily-plan/items/{item['id']}", json={"done": False})).status_code == 404
    assert (await client.post(f"{API}/daily-plan/items", json={"follow_up_id": str(due.id)})).status_code == 404
    await login(client, po)
    assert (await client.delete(f"{API}/daily-plan/items/{item['id']}")).status_code == 204


# --- T7 reports (AC3), T8 drill-down (AC1) -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_weekly_report_covers_monday_to_sunday_ist(client, db_session):
    lead, (po,) = await _team(db_session)
    company = await _company(db_session, po)
    contact = CompanyContact(company_id=company.id, name=f"Meera {_tag()}")
    db_session.add(contact)
    await db_session.flush()
    monday = _today() - timedelta(days=_today().weekday())
    last_monday = monday - timedelta(days=7)
    sunday_late = datetime.combine(monday, time.min, tzinfo=IST) - timedelta(minutes=30)  # last week's Sunday 23:30 IST
    monday_early = datetime.combine(monday, time.min, tzinfo=IST) + timedelta(minutes=30)  # this week's Monday 00:30 IST
    for at in (sunday_late, monday_early, datetime.combine(last_monday, time.min, tzinfo=IST)):
        db_session.add(RecruiterMessage(company_id=company.id, contact_id=contact.id, sender_user_id=po.id, channel="whatsapp", body="Hi", sent_at=at))
    await db_session.commit()

    await login(client, po)
    week = await _sheet(client, f"{API}/activity-reports/weekly/{last_monday}")
    assert (week["period_start"], week["period_end"], week["status"]) == (str(last_monday), str(monday - timedelta(days=1)), "draft")
    assert week["counts"]["outreach"] == 2
    assert (await client.get(f"{API}/activity-reports/weekly/{last_monday + timedelta(days=2)}")).status_code == 422
    assert (await client.get(f"{API}/activity-reports/daily/{_today() + timedelta(days=1)}")).status_code == 422
    assert (await client.get(f"{API}/activity-reports/monthly/{_today()}")).status_code == 422

    submitted = await client.post(f"{API}/activity-reports/weekly/{last_monday}/submit", json={"note": " Good week "})
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["status"] == "submitted" and submitted.json()["note"] == "Good week" and submitted.json()["counts"]["outreach"] == 2
    assert (await client.post(f"{API}/activity-reports/weekly/{last_monday}/submit", json={})).status_code == 409
    db_session.add(RecruiterMessage(company_id=company.id, contact_id=contact.id, sender_user_id=po.id, channel="whatsapp", body="Late", sent_at=sunday_late))
    await db_session.commit()
    assert (await _sheet(client, f"{API}/activity-reports/weekly/{last_monday}"))["counts"]["outreach"] == 2  # frozen at submission

    drill = await _sheet(client, f"{API}/activity-contacts", period="weekly", start=str(last_monday))
    assert drill["total"] == 1 and drill["items"][0]["outreach"] == 3

    await login(client, lead)
    grid = await _sheet(client, f"{API}/manager/activity-reports", period="weekly", start=str(last_monday))
    assert next(r for r in grid["items"] if r["recruiter"]["id"] == str(po.id))["status"] == "submitted"
    seen = await _sheet(client, f"{API}/manager/activity-reports/{po.id}/weekly/{last_monday}")
    assert seen["note"] == "Good week"
    assert (await _sheet(client, f"{API}/activity-contacts", period="weekly", start=str(last_monday), recruiter_id=str(po.id)))["total"] == 1


@pytest.mark.asyncio
async def test_a_daily_report_carries_the_plan_and_reports_are_private(client, db_session):
    lead, (po, peer) = await _team(db_session, size=2)
    _, (stranger,) = await _team(db_session)
    await login(client, po)
    today = str(_today())
    draft = await _sheet(client, f"{API}/activity-reports/daily/{today}")
    assert draft["period_end"] == today and draft["plan"] == {"planned": 0, "done": 0}
    assert (await client.post(f"{API}/activity-reports/daily/{today}/submit", json={"note": "x" * 2001})).status_code == 422
    assert (await client.get(f"{API}/activity-contacts", params={"period": "daily", "start": today, "recruiter_id": str(peer.id)})).status_code == 403
    assert (await client.get(f"{API}/manager/activity-reports", params={"period": "daily", "start": today})).status_code == 403

    await login(client, lead)
    grid = await _sheet(client, f"{API}/manager/activity-reports", period="daily", start=today)
    assert next(r for r in grid["items"] if r["recruiter"]["id"] == str(po.id))["status"] == "missing"
    assert str(stranger.id) not in {r["recruiter"]["id"] for r in grid["items"]}
    assert (await client.get(f"{API}/manager/activity-reports/{stranger.id}/daily/{today}")).status_code == 404
    assert (await client.get(f"{API}/activity-contacts", params={"period": "daily", "start": today, "recruiter_id": str(stranger.id)})).status_code == 404
    assert (await client.post(f"{API}/activity-reports/daily/{today}/submit", json={})).status_code == 403


# --- T4 the company's territory ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_company_territory_is_edited_and_filtered(client, db_session):
    _, (po,) = await _team(db_session)
    await login(client, po)
    territory = f"West {_tag()}"
    created = await client.post(f"{API}/companies", json={"name": f"Terr {_tag()}", "territory": f" {territory} "})
    assert created.status_code == 201, created.text
    company = created.json()["company"]
    assert company["territory"] == territory
    listed = await _sheet(client, f"{API}/companies", territory=territory.upper())
    assert [row["id"] for row in listed["items"]] == [company["id"]] and listed["items"][0]["territory"] == territory
    cleared = await client.patch(f"{API}/companies/{company['id']}", json={"territory": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["company"]["territory"] is None
    assert (await _sheet(client, f"{API}/companies", territory=territory))["total"] == 0
    assert (await client.patch(f"{API}/companies/{company['id']}", json={"territory": "x" * 121})).status_code == 422
