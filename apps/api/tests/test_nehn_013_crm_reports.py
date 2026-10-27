"""nehn-013 (DEC-SCOPE-301, spec docs/superpowers/specs/2026-10-27-nehn-013-crm-report-gaps-design.md): the CRM report gaps -- Lost and
Conversion rate on every funnel report, and the counselor, date-wise, follow-up status and pending follow-up reports. Figures are
hand-computed against fixtures isolated by a fresh campaign / manager (the shared test database is never truncated)."""

from datetime import datetime, timedelta

import pytest

from app.models import LEAD_FOLLOW_UP_REASONS, LeadFollowUp
from app.services import telecaller_reports
from app.services.bdm_appointments import IST, db_now, today_ist
from tests.bdm001_helpers import make_user
from tests.bdm017_helpers import as_user
from tests.test_tel_024_reports import REPORTS, add, campaign, get, history, make_lead, product, row, team

pytestmark = pytest.mark.asyncio

FUNNEL_TAIL = ["Lost", "Conversion rate (%)"]


async def funnel_world(db):
    """Six leads on one campaign: 1 enrolled, 2 lost (lost + not interested), 3 open -- a 1/6 = 16.7% conversion rate."""
    manager, tel, _ = await team(db)
    camp = await campaign(db, await product(db))
    on = {"campaign_id": camp.id, "product_id": camp.product_id, "source": "instagram"}
    enrolled = await make_lead(db, tel, **on, status="converted")
    lost = await make_lead(db, tel, **on, status="lost")
    await make_lead(db, tel, **on, status="not_interested")
    reopened = await make_lead(db, tel, **on, status="contacted")  # lost once, reopened: no longer lost (R1)
    for _ in range(2):
        await make_lead(db, tel, **on)
    await add(db, *history(enrolled, "contacted", "qualified", "counselling_scheduled", "counselling_completed", "application_enrollment", "converted"),
              *history(lost, "contacted", "lost"), *history(reopened, "contacted", "lost", "contacted"))
    return manager, tel, camp


# --- AC1: Lost and Conversion rate on every funnel report ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["source", "product", "campaign"])
async def test_funnel_reports_append_lost_and_conversion_rate(client, db_session, kind):
    manager, _, camp = await funnel_world(db_session)
    await as_user(client, manager)
    body = await get(client, kind, campaign_id=str(camp.id))
    assert [c["label"] for c in body["columns"]][-2:] == FUNNEL_TAIL
    assert [c["key"] for c in body["columns"]][1:6] == ["leads", "connected", "qualified", "counselling", "enrolled"]  # existing order kept
    line = body["items"][0]
    assert (line["leads"], line["enrolled"], line["lost"], line["conversion_rate"]) == (6, 1, 2, 16.7)
    assert (body["totals"]["lost"], body["totals"]["conversion_rate"]) == (2, 16.7)


async def test_the_total_rate_is_recomputed_not_summed(client, db_session):
    manager, tel, camp = await funnel_world(db_session)  # instagram: 1 of 6
    await make_lead(db_session, tel, campaign_id=camp.id, source="google", status="converted")  # google: 1 of 1
    await as_user(client, manager)
    body = await get(client, "source", campaign_id=str(camp.id))
    assert row(body, label="Google")["conversion_rate"] == 100.0
    assert row(body, label="Instagram")["conversion_rate"] == 16.7
    assert (body["totals"]["leads"], body["totals"]["enrolled"], body["totals"]["conversion_rate"]) == (7, 2, 28.6)


async def test_the_existing_non_funnel_reports_keep_their_columns(client, db_session):
    manager, _, _ = await team(db_session)
    await as_user(client, manager)
    assert [c["key"] for c in (await get(client, "handover"))["columns"]] == ["telecaller", "counselor", "handed_over", "counselling_done", "enrolled"]
    assert "conversion_rate" not in [c["key"] for c in (await get(client, "telecaller"))["columns"]]


# --- AC2: counselor report ------------------------------------------------------------------------------------------------------------

async def test_the_counselor_report_groups_by_lead_owner(client, db_session):
    manager, tel, _ = await team(db_session)
    camp = await campaign(db_session, await product(db_session))
    asha = await make_user(db_session, "counselor", "it", name="Asha Counselor")
    ravi = await make_user(db_session, "counselor", "it", name="Ravi Counselor")
    for owner, status in ((asha, "converted"), (asha, "counselling_completed"), (asha, "lost"), (ravi, "counselling_scheduled")):
        await make_lead(db_session, tel, campaign_id=camp.id, owner_id=owner.id, status=status)
    await make_lead(db_session, tel, campaign_id=camp.id)  # no counselor: not in the report
    await as_user(client, manager)
    body = await get(client, "counselor", campaign_id=str(camp.id))
    assert [c["label"] for c in body["columns"]] == ["Counselor", "Leads", "Counselling done", "Enrolled", *FUNNEL_TAIL]
    assert [i["counselor"] for i in body["items"]] == ["Asha Counselor", "Ravi Counselor"]  # most leads first
    assert {k: row(body, counselor="Asha Counselor")[k] for k in ("leads", "counselling_done", "enrolled", "lost", "conversion_rate")} == {
        "leads": 3, "counselling_done": 2, "enrolled": 1, "lost": 1, "conversion_rate": 33.3}  # cumulative: the enrolled lead too
    assert row(body, counselor="Ravi Counselor")["conversion_rate"] == 0.0
    assert body["totals"]["leads"] == 4 and body["totals"]["counselor"] == "Total"


# --- AC3: date-wise report ------------------------------------------------------------------------------------------------------------

def ist(y, m, d, h=10):
    return datetime(y, m, d, h, tzinfo=IST)


async def date_world(db):
    manager, tel, _ = await team(db)
    camp = await campaign(db, await product(db))
    for when, status in ((ist(2026, 3, 2), "converted"), (ist(2026, 3, 2, 23), "assigned"), (ist(2026, 3, 4), "lost"),
                         (ist(2026, 3, 9, 0), "assigned"), (ist(2026, 4, 1), "converted")):
        await make_lead(db, tel, campaign_id=camp.id, status=status, created_at=when)
    return manager, camp


@pytest.mark.parametrize(("group", "expected"), [
    ("day", [("2026-03-02", 2, 1), ("2026-03-04", 1, 0), ("2026-03-09", 1, 0), ("2026-04-01", 1, 1)]),
    ("week", [("Week of 2026-03-02", 3, 1), ("Week of 2026-03-09", 1, 0), ("Week of 2026-03-30", 1, 1)]),
    ("month", [("March 2026", 4, 1), ("April 2026", 1, 1)]),
])
async def test_the_date_report_groups_by_ist_day_week_or_month_in_calendar_order(client, db_session, group, expected):
    manager, camp = await date_world(db_session)
    await as_user(client, manager)
    body = await get(client, "date", campaign_id=str(camp.id), date_from="2026-03-01", date_to="2026-04-30", group=group)
    assert [(i["period"], i["leads"], i["enrolled"]) for i in body["items"]] == expected
    assert [c["label"] for c in body["columns"]][:2] == ["Period", "Leads"] and [c["label"] for c in body["columns"]][-2:] == FUNNEL_TAIL
    assert (body["totals"]["period"], body["totals"]["leads"], body["totals"]["lost"], body["totals"]["conversion_rate"]) == ("Total", 5, 1, 40.0)


async def test_the_date_report_defaults_to_days_and_refuses_an_unknown_grouping(client, db_session):
    manager, camp = await date_world(db_session)
    await as_user(client, manager)
    body = await get(client, "date", campaign_id=str(camp.id), date_from="2026-03-01", date_to="2026-03-31")
    assert body["items"][0]["period"] == "2026-03-02"
    response = await client.get(f"{REPORTS}/date", params={"group": "year"})
    assert response.status_code == 422 and response.json()["detail"] == "Choose day, week or month"


# --- follow-up status and AC4: pending follow-ups -------------------------------------------------------------------------------------

async def follow_up_world(db):
    manager, tel, tel2 = await team(db)
    camp = await campaign(db, await product(db))
    now = await db_now(db)
    lead = await make_lead(db, tel, campaign_id=camp.id, name="Priya Lead")
    other = await make_lead(db, tel2, campaign_id=camp.id, name="Kiran Lead")
    counselor = await make_user(db, "counselor", "it")

    def fu(on, due, by=tel, **state):
        return LeadFollowUp(lead_id=on.id, due_at=due, reason="fee_details", created_by_user_id=by.id, **state)

    await add(db,
              fu(lead, now - timedelta(days=3)),  # open, 3 days overdue
              fu(lead, now - timedelta(minutes=5)),  # open, due earlier: overdue, 0 days
              fu(lead, now + timedelta(days=2)),  # open, not yet due
              fu(lead, now - timedelta(hours=1), status="done", completed_at=now, completed_by_user_id=tel.id),
              fu(other, now - timedelta(days=1), status="cancelled", cancelled_at=now, cancel_reason="Closed"),
              fu(other, now - timedelta(days=1), by=counselor))  # a counselor's follow-up: not telecaller work (ccrm-003 A5)
    return manager, tel, tel2, camp, now


def wide(now):
    return {"date_from": (today_ist(now) - timedelta(days=30)).isoformat(), "date_to": (today_ist(now) + timedelta(days=30)).isoformat()}


async def test_the_follow_up_report_counts_status_per_telecaller(client, db_session):
    manager, tel, tel2, camp, now = await follow_up_world(db_session)
    await as_user(client, manager)
    body = await get(client, "follow_ups", campaign_id=str(camp.id), **wide(now))
    assert [c["label"] for c in body["columns"]] == ["Telecaller", "Follow-ups", "Completed", "Open", "Overdue", "Cancelled"]
    mine = row(body, telecaller=tel.full_name)
    assert {k: mine[k] for k in ("follow_ups", "completed", "open", "overdue", "cancelled")} == {
        "follow_ups": 4, "completed": 1, "open": 3, "overdue": 2, "cancelled": 0}
    assert row(body, telecaller=tel2.full_name)["cancelled"] == 1 and row(body, telecaller=tel2.full_name)["follow_ups"] == 1
    assert body["totals"]["follow_ups"] == 5


async def test_pending_follow_ups_lists_open_overdue_ones_most_overdue_first(client, db_session):
    manager, tel, _, camp, now = await follow_up_world(db_session)
    await as_user(client, manager)
    body = await get(client, "pending_follow_ups", campaign_id=str(camp.id), **wide(now))
    assert [c["label"] for c in body["columns"]] == ["Lead", "Telecaller", "Due date", "Reason", "Days overdue"]
    assert [(i["lead"], i["telecaller"], i["reason"], i["overdue_days"]) for i in body["items"]] == [
        ("Priya Lead", tel.full_name, "Need fee details", 3), ("Priya Lead", tel.full_name, "Need fee details",
                                                                (today_ist(now) - today_ist(now - timedelta(minutes=5))).days)]
    assert body["items"][0]["due"] == today_ist(now - timedelta(days=3)).isoformat()
    assert body["totals"]["lead"] == "Total (2)" and body["totals"]["overdue_days"] == ""  # QA-04: the Total row counts the list
    assert not any(k in item for item in body["items"] for k in ("mobile", "email"))


async def test_follow_ups_due_outside_the_range_are_not_counted(client, db_session):
    manager, _, _, camp, now = await follow_up_world(db_session)
    await as_user(client, manager)
    later = (today_ist(now) + timedelta(days=40)).isoformat()
    assert (await get(client, "pending_follow_ups", campaign_id=str(camp.id), date_from=later, date_to=later))["items"] == []


async def test_follow_up_reports_are_scoped_to_the_callers_leads(client, db_session):
    _, _, _, camp, now = await follow_up_world(db_session)
    other_manager, _, _ = await team(db_session)
    await as_user(client, other_manager)
    for kind in ("follow_ups", "pending_follow_ups"):
        assert (await get(client, kind, campaign_id=str(camp.id), **wide(now)))["items"] == []


async def test_the_reason_labels_cover_every_follow_up_reason():
    assert set(telecaller_reports.FOLLOW_UP_REASONS) == set(LEAD_FOLLOW_UP_REASONS)


# --- access and export --------------------------------------------------------------------------------------------------------------

NEW_KINDS = ("counselor", "date", "follow_ups", "pending_follow_ups")


async def test_a_telecaller_and_a_counselor_are_refused_the_new_reports(client, db_session):
    _, tel, _ = await team(db_session)
    for user in (tel, await make_user(db_session, "counselor", "it")):
        await as_user(client, user)
        for kind in NEW_KINDS:
            assert (await client.get(f"{REPORTS}/{kind}")).status_code == 403
            assert (await client.get(f"{REPORTS}/{kind}.csv")).status_code == 403


async def test_the_new_reports_export_as_csv_with_the_screen_columns(client, db_session):
    manager, _, camp = await funnel_world(db_session)
    await as_user(client, manager)
    response = await client.get(f"{REPORTS}/campaign.csv", params={"campaign_id": str(camp.id)})
    lines = response.text.lstrip("﻿").splitlines()
    assert lines[0] == "Campaign,Leads,Connected,Qualified,Counselling,Enrolled,Lost,Conversion rate (%)"
    assert lines[-1] == "Total,6,3,1,1,1,2,16.7"
    for kind in NEW_KINDS:
        assert (await client.get(f"{REPORTS}/{kind}.csv")).status_code == 200
        assert (await client.get(f"{REPORTS}/{kind}.xlsx")).status_code == 200
