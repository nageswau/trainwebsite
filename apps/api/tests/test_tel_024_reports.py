"""tel-024 (DEC-SCOPE-109, API §12AC, RBAC §2.35): the five management reports and their CSV export -- figures, scope, refusals and
inputs. The shared test database is never truncated, so every test isolates its rows with a fresh campaign / product / manager."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry, LeadCall, LeadStageHistory, TelCampaign, TelProduct
from app.services import telecaller_metrics as metrics
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import db_now, today_ist
from tests.bdm001_helpers import make_user
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager

REPORTS = "/api/v1/telecaller/reports"
KINDS = ("source", "product", "telecaller", "handover", "campaign")

pytestmark = pytest.mark.asyncio


async def team(db):
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager), await make_telecaller(db, manager)


async def add(db, *rows):
    db.add_all(rows)
    await db.commit()
    return rows[0] if len(rows) == 1 else rows


async def product(db, group="it", name=None) -> TelProduct:
    return await add(db, TelProduct(product_group=group, team=group, name=name or f"Course {uuid.uuid4().hex[:8]}"))


async def campaign(db, prod, source="instagram", name=None) -> TelCampaign:
    return await add(db, TelCampaign(name=name or f"Campaign {uuid.uuid4().hex[:8]}", source=source, product_id=prod.id, start_date=date(2026, 1, 1)))


async def make_lead(db, tel=None, **over) -> Enquiry:
    values = {"division": "it", "name": "Lead", "email": f"{uuid.uuid4().hex[:8]}@example.local", "subject": "Python", "message": "Hi",
              "source": "website", "status": "assigned", "telecaller_user_id": tel.id if tel else None} | over
    return await add(db, Enquiry(**values))


def history(lead, *stages):
    """The lead's path, one history row per move (from the previous stage)."""
    path = ("new", *stages)
    return [LeadStageHistory(lead_id=lead.id, from_stage=a, to_stage=b, event="manual") for a, b in zip(path, path[1:], strict=False)]


def row(body, **match) -> dict:
    found = [item for item in body["items"] if all(item[k] == v for k, v in match.items())]
    assert len(found) == 1, (match, body["items"])
    return found[0]


async def get(client, kind, **params):
    response = await client.get(f"{REPORTS}/{kind}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


# --- metrics: the grouped flow counts -----------------------------------------------------------------------------------------------

async def test_flow_counts_by_user_matches_the_one_user_counts(db_session):
    _, tel, idle = await team(db_session)
    now = await db_now(db_session)
    start, end = day_range(today_ist(now))
    lead = await make_lead(db_session, tel)
    await add(db_session,
              LeadCall(lead_id=lead.id, caller_user_id=tel.id, occurred_at=start, duration_seconds=5, call_type="outgoing", outcome="interested"),
              LeadCall(lead_id=lead.id, caller_user_id=tel.id, occurred_at=start, duration_seconds=5, call_type="outgoing", outcome="busy"),
              LeadStageHistory(lead_id=lead.id, from_stage="contacted", to_stage="qualified", event="manual", actor_user_id=tel.id, created_at=start))
    grouped = await metrics.flow_counts_by_user(db_session, [tel.id, idle.id], start, end)
    assert grouped[tel.id] == await metrics.flow_counts(db_session, tel.id, start, end)
    assert grouped[tel.id]["calls"] == 2 and grouped[tel.id]["connected_calls"] == 1 and grouped[tel.id]["qualified_leads"] == 1
    assert all(v == 0 for v in grouped[idle.id].values())


# --- cohort reports -----------------------------------------------------------------------------------------------------------------

async def test_the_campaign_funnel_is_cumulative_and_monotonic(client, db_session):
    manager, tel, _ = await team(db_session)
    camp = await campaign(db_session, await product(db_session))
    on = {"campaign_id": camp.id, "product_id": camp.product_id, "source": "instagram"}
    untouched = await make_lead(db_session, tel, **on)
    contacted = await make_lead(db_session, tel, **on, status="contacted")
    lost = await make_lead(db_session, tel, **on, status="lost")  # qualified, then closed: still counts as reached qualified
    jumped = await make_lead(db_session, tel, **on, status="application_enrollment")  # linked straight from contacted
    unlinked = await make_lead(db_session, tel, **on, status="follow_up")  # converted, then the link was undone
    enrolled = await make_lead(db_session, tel, **on, status="converted")
    await add(db_session, *history(contacted, "contacted"), *history(lost, "contacted", "qualified", "lost"),
              *history(jumped, "contacted", "application_enrollment"), *history(unlinked, "contacted", "application_enrollment", "converted", "follow_up"),
              *history(enrolled, "contacted", "qualified", "counselling_scheduled", "counselling_completed", "application_enrollment", "converted"))
    assert untouched.status == "assigned"
    await as_user(client, manager)
    body = await get(client, "campaign", campaign_id=str(camp.id))
    line = row(body, label=camp.name)
    assert [line[k] for k in ("leads", "connected", "qualified", "counselling", "enrolled")] == [6, 5, 4, 3, 1]
    assert body["totals"]["leads"] == 6 and body["totals"]["label"] == "Total"
    assert [c["label"] for c in body["columns"]] == ["Campaign", "Leads", "Connected", "Qualified", "Counselling", "Enrolled"]


async def test_the_source_report_reconciles_with_the_manager_lead_list(client, db_session):
    manager, tel, tel2 = await team(db_session)
    camp = await campaign(db_session, await product(db_session))
    for owner, source in ((tel, "instagram"), (tel, "instagram"), (tel2, "google"), (tel2, "website")):
        await make_lead(db_session, owner, campaign_id=camp.id, source=source)
    other_manager, outsider, _ = await team(db_session)
    await make_lead(db_session, outsider, campaign_id=camp.id, source="instagram")  # another manager's report: out of scope
    await as_user(client, manager)
    body = await get(client, "source", campaign_id=str(camp.id))
    assert {item["label"]: item["leads"] for item in body["items"]} == {"Instagram": 2, "Google": 1, "Website": 1}
    assert body["items"][0]["label"] == "Instagram"  # most leads first
    listed = (await client.get("/api/v1/telecaller/leads", params={"campaign_id": str(camp.id)})).json()
    assert body["totals"]["leads"] == listed["total"] == 4
    await as_user(client, other_manager)
    assert (await get(client, "source", campaign_id=str(camp.id)))["totals"]["leads"] == 1


async def test_leads_without_a_campaign_or_product_are_named(client, db_session):
    manager, tel, _ = await team(db_session)
    prod = await product(db_session)
    camp = await campaign(db_session, prod)
    await make_lead(db_session, tel, product_id=prod.id)
    await make_lead(db_session, tel, product_id=prod.id, campaign_id=camp.id)
    await as_user(client, manager)
    body = await get(client, "campaign", product_id=str(prod.id))
    assert {item["label"]: item["leads"] for item in body["items"]} == {"No campaign": 1, camp.name: 1}
    body = await get(client, "product", campaign_id=str(camp.id))
    assert [item["label"] for item in body["items"]] == [prod.name]
    no_product = await make_lead(db_session, tel, source="walk_in", campaign_id=(await campaign(db_session, prod)).id)
    body = await get(client, "product", campaign_id=str(no_product.campaign_id))
    assert [item["label"] for item in body["items"]] == ["No product"]


async def test_the_handover_report_groups_telecaller_by_current_counselor(client, db_session):
    manager, tel, tel2 = await team(db_session)
    counselor = await make_user(db_session, "counselor", "it", name="Asha Counselor")
    camp = await campaign(db_session, await product(db_session))
    on = {"campaign_id": camp.id}
    done = await make_lead(db_session, tel, **on, owner_id=counselor.id, status="counselling_completed")
    await make_lead(db_session, tel, **on, owner_id=counselor.id, status="interested")
    won = await make_lead(db_session, tel2, **on, owner_id=counselor.id, status="converted")
    await make_lead(db_session, tel, **on, status="follow_up")  # returned to the telecaller: not with a counselor
    await add(db_session, *history(done, "contacted", "counselling_scheduled", "counselling_completed"),
              *history(won, "contacted", "counselling_scheduled", "counselling_completed", "application_enrollment", "converted"))
    await as_user(client, manager)
    body = await get(client, "handover", campaign_id=str(camp.id))
    assert [c["key"] for c in body["columns"]] == ["telecaller", "counselor", "handed_over", "counselling_done", "enrolled"]
    first = row(body, telecaller=tel.full_name, counselor="Asha Counselor")
    assert (first["handed_over"], first["counselling_done"], first["enrolled"]) == (2, 1, 0)
    second = row(body, telecaller=tel2.full_name)
    assert (second["handed_over"], second["counselling_done"], second["enrolled"]) == (1, 1, 1)
    assert body["totals"]["handed_over"] == 3


# --- the telecaller report (activity in the range, RP1) ------------------------------------------------------------------------------

async def test_the_telecaller_report_sums_the_daily_activity(client, db_session):
    manager, tel, idle = await team(db_session)
    now = await db_now(db_session)
    today = today_ist(now)
    start, _ = day_range(today)
    lead = await make_lead(db_session, tel)
    yesterday = start - timedelta(hours=2)
    await add(db_session,
              LeadCall(lead_id=lead.id, caller_user_id=tel.id, occurred_at=start, duration_seconds=5, call_type="outgoing", outcome="interested"),
              LeadCall(lead_id=lead.id, caller_user_id=tel.id, occurred_at=yesterday, duration_seconds=5, call_type="outgoing", outcome="no_answer"),
              LeadStageHistory(lead_id=lead.id, from_stage="contacted", to_stage="qualified", event="manual", actor_user_id=tel.id, created_at=start))
    await as_user(client, manager)
    first = today - timedelta(days=1)
    body = await get(client, "telecaller", date_from=first.isoformat(), date_to=today.isoformat())
    assert {item["telecaller"] for item in body["items"]} == {tel.full_name, idle.full_name}
    mine = row(body, telecaller=tel.full_name)
    days = [await metrics.daily_activity(db_session, tel.id, d, now) for d in (first, today)]
    expected = {"calls": "calls", "connected": "connected_calls", "qualified": "qualified_leads", "appointments": "new_appointments", "conversions": "converted_leads"}
    assert {k: mine[k] for k in expected} == {k: sum(d[v] for d in days) for k, v in expected.items()}
    assert (mine["calls"], mine["connected"]) == (2, 1)
    assert all(row(body, telecaller=idle.full_name)[k] == 0 for k in expected)


# --- scope -------------------------------------------------------------------------------------------------------------------------

async def test_a_division_admin_sees_only_their_division_and_a_team_filter_only_narrows(client, db_session):
    prod = await product(db_session)
    camp = await campaign(db_session, prod)
    await make_lead(db_session, campaign_id=camp.id, source="website")
    await make_lead(db_session, campaign_id=camp.id, source="google", division="overseas")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    body = await get(client, "source", campaign_id=str(camp.id))
    assert {item["label"]: item["leads"] for item in body["items"]} == {"Website": 1}
    listed = (await client.get("/api/v1/admin/leads", params={"campaign_id": str(camp.id)})).json()
    assert listed["total"] == body["totals"]["leads"]
    assert (await get(client, "source", campaign_id=str(camp.id), team="overseas"))["items"] == []
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    assert (await get(client, "source", campaign_id=str(camp.id)))["totals"]["leads"] == 2
    assert (await get(client, "source", campaign_id=str(camp.id), team="overseas"))["totals"]["leads"] == 1


async def test_the_telecaller_report_lists_the_division_admins_team_only(client, db_session):
    manager = await make_tl_manager(db_session)
    it_tel = await make_telecaller(db_session, manager)
    overseas_tel = await make_telecaller(db_session, manager, team="overseas")
    await as_user(client, await make_user(db_session, "overseas_admin", "overseas"))
    names = {item["telecaller"] for item in (await get(client, "telecaller"))["items"]}
    assert overseas_tel.full_name in names and it_tel.full_name not in names


async def test_a_lead_created_outside_the_range_is_not_counted(client, db_session):
    manager, tel, _ = await team(db_session)
    camp = await campaign(db_session, await product(db_session))
    today = today_ist(await db_now(db_session))
    await make_lead(db_session, tel, campaign_id=camp.id, created_at=day_range(today - timedelta(days=40))[0])
    await make_lead(db_session, tel, campaign_id=camp.id)
    await as_user(client, manager)
    week = {"campaign_id": str(camp.id), "date_from": (today - timedelta(days=7)).isoformat(), "date_to": today.isoformat()}
    assert (await get(client, "campaign", **week))["totals"]["leads"] == 1
    assert (await get(client, "campaign", **week | {"date_from": (today - timedelta(days=60)).isoformat()}))["totals"]["leads"] == 2


# --- refusals and inputs ------------------------------------------------------------------------------------------------------------

async def test_a_telecaller_and_other_roles_are_refused(client, db_session):
    _, tel, _ = await team(db_session)
    for user in (tel, await make_user(db_session, "counselor", "it"), await make_user(db_session, "student", "it")):
        await as_user(client, user)
        for kind in (*KINDS, "nope"):
            assert (await client.get(f"{REPORTS}/{kind}")).status_code == 403
            assert (await client.get(f"{REPORTS}/{kind}.csv")).status_code == 403


async def test_an_unknown_report_is_404(client, db_session):
    manager, _, _ = await team(db_session)
    await as_user(client, manager)
    assert (await client.get(f"{REPORTS}/nope")).status_code == 404
    assert (await client.get(f"{REPORTS}/nope.csv")).status_code == 404


async def test_the_default_range_is_this_month_to_date(client, db_session):
    manager, _, _ = await team(db_session)
    await as_user(client, manager)
    today = today_ist(await db_now(db_session))
    body = await get(client, "source")
    assert (body["date_from"], body["date_to"]) == (today.replace(day=1).isoformat(), today.isoformat())
    assert {"teams", "sources", "products", "campaigns"} <= set(body["options"])


@pytest.mark.parametrize(("params", "message"), [
    ({"date_from": "2026-13-01"}, "'From' is not a valid date"),
    ({"date_to": "yesterday"}, "'To' is not a valid date"),
    ({"date_from": "2026-05-02", "date_to": "2026-05-01"}, "'From' must be on or before 'To'"),
    ({"date_from": "2025-01-01", "date_to": "2026-05-01"}, "Choose a range of at most 366 days"),
    ({"team": "sales"}, "Choose a team from the list"),
    ({"source": "tv"}, "Choose a source from the list"),
    ({"product_id": "abc"}, "Choose a course from the list"),
    ({"campaign_id": "abc"}, "Choose a campaign from the list"),
])
async def test_bad_inputs_are_422_with_a_readable_message(client, db_session, params, message):
    manager, _, _ = await team(db_session)
    await as_user(client, manager)
    response = await client.get(f"{REPORTS}/source", params=params)
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == message


# --- CSV ---------------------------------------------------------------------------------------------------------------------------

async def test_the_csv_export_matches_the_screen_neutralises_formulas_and_is_audited(client, db_session):
    manager, tel, _ = await team(db_session)
    camp = await campaign(db_session, await product(db_session), name=f"=HYPERLINK(\"x\") {uuid.uuid4().hex[:6]}")
    await make_lead(db_session, tel, campaign_id=camp.id)
    await as_user(client, manager)
    response = await client.get(f"{REPORTS}/campaign.csv", params={"campaign_id": str(camp.id)})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "telecaller-campaign-" in response.headers["content-disposition"]
    lines = response.text.lstrip("﻿").splitlines()
    assert lines[0] == "Campaign,Leads,Connected,Qualified,Counselling,Enrolled"
    assert lines[1].startswith("\"'=HYPERLINK") and lines[1].endswith(",1,0,0,0,0")
    assert lines[-1] == "Total,1,0,0,0,0"
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == manager.id, AuditLog.action == "telecaller_report.export"))).all()
    assert len(audit) == 1 and audit[0].entity_id == "campaign" and audit[0].metadata_json["rows"] == 1
    assert audit[0].metadata_json["filters"] == ["campaign_id"]
