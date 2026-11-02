"""itc-008 (spec docs/superpowers/specs/2026-11-02-itc-008-lead-filters-telecaller-tiles-design.md): the telecaller dashboard's contact
rate (T1), qualified (T2) and handovers (T3) tiles, and AC2 -- they equal the Telecaller Report's figures for the same day (R1). The
shared test database is never truncated, so each test counts only for users it created."""

import uuid
from datetime import timedelta

import pytest

from app.models import AuditLog, Enquiry, LeadCall, LeadStageHistory
from app.services import telecaller_metrics as metrics
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import db_now, today_ist
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager

pytestmark = pytest.mark.asyncio

REPORTS = "/api/v1/telecaller/reports"


async def add(db, *rows):
    db.add_all(rows)
    await db.commit()
    return rows[0] if len(rows) == 1 else rows


async def make_lead(db, tel) -> Enquiry:
    return await add(
        db,
        Enquiry(
            division="it",
            name=f"Lead {uuid.uuid4().hex[:6]}",
            email=f"{uuid.uuid4().hex[:8]}@example.local",
            subject="Python",
            message="Hi",
            source="website",
            status="assigned",
            telecaller_user_id=tel.id,
        ),
    )


def call(lead, tel, at, outcome="interested") -> LeadCall:
    return LeadCall(lead_id=lead.id, caller_user_id=tel.id, occurred_at=at, duration_seconds=60, call_type="outgoing", outcome=outcome)


def handover(lead, actor, at) -> AuditLog:
    return AuditLog(
        user_id=actor.id, action="lead.handover", entity_type="enquiry", entity_id=str(lead.id), created_at=at, metadata_json={"counselor_id": str(uuid.uuid4()), "from_counselor_id": None}
    )


async def world(db):
    """Today: tel calls three leads (one reached after a no-answer, one only busy, one reached twice) and a lead called only yesterday;
    qualifies one lead; hands over two (plus one yesterday, and one the manager handed over). tel2 reaches the only lead they call."""
    manager = await make_tl_manager(db)
    tel, tel2 = await make_telecaller(db, manager), await make_telecaller(db, manager)
    now = await db_now(db)
    start, _ = day_range(today_ist(now))
    reached, busy, twice, old, other = [await make_lead(db, tel) for _ in range(5)]
    theirs = await make_lead(db, tel2)
    at = start + timedelta(minutes=5)
    await add(
        db,
        call(reached, tel, at, "no_answer"),
        call(reached, tel, at, "interested"),
        call(busy, tel, at, "busy"),
        call(twice, tel, at),
        call(twice, tel, at, "follow_up_required"),
        call(old, tel, start - timedelta(hours=1)),
        call(theirs, tel2, at),
        LeadStageHistory(lead_id=reached.id, from_stage="contacted", to_stage="qualified", event="manual", actor_user_id=tel.id, created_at=at),
        handover(reached, tel, at),
        handover(twice, tel, at),
        handover(old, tel, start - timedelta(hours=1)),
        handover(other, manager, at),
    )
    return manager, tel, tel2, now


async def test_the_three_tiles_count_today_for_the_telecaller(db_session):
    _, tel, tel2, now = await world(db_session)
    tiles = await metrics.tiles(db_session, tel.id, "it", now)
    assert tiles["contact_rate"] == 66.7  # 2 of the 3 leads called today were reached
    assert tiles["qualified"] == 1
    assert tiles["handovers"] == 2  # the manager's handover and yesterday's are not today's / not theirs
    assert (await metrics.tiles(db_session, tel2.id, "it", now))["contact_rate"] == 100.0


async def test_no_call_today_is_no_rate_not_zero(db_session):
    manager = await make_tl_manager(db_session)
    idle = await make_telecaller(db_session, manager)
    tiles = await metrics.tiles(db_session, idle.id, "it", await db_now(db_session))
    assert (tiles["contact_rate"], tiles["qualified"], tiles["handovers"]) == (None, 0, 0)


async def test_ac2_the_tiles_equal_the_telecaller_report_for_the_same_day(client, db_session):
    manager, tel, tel2, now = await world(db_session)
    tiles = await metrics.tiles(db_session, tel.id, "it", now)
    await as_user(client, manager)
    today = today_ist(now).isoformat()
    body = (await client.get(f"{REPORTS}/telecaller", params={"date_from": today, "date_to": today})).json()
    keys = [c["key"] for c in body["columns"]]
    assert keys[:6] == ["telecaller", "calls", "connected", "qualified", "appointments", "conversions"]  # existing order kept
    assert keys[6:] == ["contact_rate", "handovers"]
    mine = next(item for item in body["items"] if item["telecaller"] == tel.full_name)
    assert (mine["contact_rate"], mine["qualified"], mine["handovers"]) == (tiles["contact_rate"], tiles["qualified"], tiles["handovers"])
    # the Total row's rate is reached / called over the rows (2 + 1 of 3 + 1), never a sum of rates
    assert body["totals"]["contact_rate"] == 75.0
    assert body["totals"]["handovers"] == 2


async def test_the_dashboard_route_returns_the_new_tiles(client, db_session):
    _, tel, _, _ = await world(db_session)
    await as_user(client, tel)
    tiles = (await client.get("/api/v1/telecaller/dashboard")).json()["tiles"]
    assert (tiles["contact_rate"], tiles["qualified"], tiles["handovers"]) == (66.7, 1, 2)
