"""itc-004 (DEC-SCOPE-338) -- the Nurture stage: a parked open stage outside the linear pipeline (N2), the telecaller's and manager's move
with a reason (N3), re-activation (N4), never overdue (N5), the stage filter (N6) and the history row (N7). The shared test database is
never truncated, so every list assertion narrows to rows the test created."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select

from app.lead_stages import CLOSED, EVENTS, MANUAL, ORDER, STAGE_LABELS, STAGES
from app.models import LeadStageHistory
from app.services import lead_handover, lead_pipeline, telecaller_metrics
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import lead, make_telecaller, make_tl_manager, stage_url
from tests.tel016_helpers import make_counselor
from tests.test_tel_011_follow_ups import FOLLOW_UPS, LEADS, stored
from tests.test_tel_020_alerts import D, follow_up, ist, mk_lead, notes, reset_settings, run


async def _team(db):
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager)


async def _move(db, row, actor, kind, to_stage, reason=None):
    locked = await lead_pipeline.locked_lead(db, row.id)
    await lead_pipeline.person_move(db, locked, actor, kind, to_stage, reason)
    await db.commit()
    return locked


async def _last_history(db, row):
    return (
        await db.execute(
            select(LeadStageHistory.from_stage, LeadStageHistory.to_stage, LeadStageHistory.event, LeadStageHistory.reason, LeadStageHistory.actor_user_id, LeadStageHistory.created_at)
            .where(LeadStageHistory.lead_id == row.id)
            .order_by(LeadStageHistory.position.desc())
            .limit(1)
        )
    ).one()


# --- N2: the catalogue -------------------------------------------------------------------------------------------------------
def test_nurture_is_an_open_stage_outside_the_linear_pipeline():
    assert STAGE_LABELS["nurture"] == "Nurture" and "nurture" in STAGES and "nurture" in MANUAL
    assert "nurture" not in ORDER and "nurture" not in CLOSED
    assert len(STAGES) == 18 and len(ORDER) == 11


def test_only_the_three_reactivating_events_accept_a_nurture_lead():
    accepting = {event for event, (sources, _) in EVENTS.items() if "nurture" in sources}
    assert accepting == {"appointment_booked", "student_linked", "returned"}


# --- N3 / N7: the person's move, with a reason in the history ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_telecaller_moves_a_lead_to_nurture_with_a_reason_recorded_with_actor_and_time(db_session):
    _, tel = await _team(db_session)
    row = await lead(db_session, telecaller=tel, status="interested")
    with pytest.raises(RequestValidationError) as refused:
        await _move(db_session, row, tel, "telecaller", "nurture")
    assert refused.value.errors()[0]["loc"] == ("body", "reason")
    before = datetime.now(UTC)
    assert (await _move(db_session, row, tel, "telecaller", "nurture", "Joining next intake")).status == "nurture"
    *moved, actor, at = await _last_history(db_session, row)
    assert moved == ["interested", "nurture", "manual", "Joining next intake"] and actor == tel.id and at >= before - timedelta(seconds=5)


@pytest.mark.asyncio
async def test_a_nurture_lead_is_reactivated_by_a_manual_move_without_a_reason(db_session):
    manager, tel = await _team(db_session)
    row = await lead(db_session, telecaller=tel, status="nurture")
    assert (await _move(db_session, row, tel, "telecaller", "follow_up")).status == "follow_up"
    row = await lead(db_session, telecaller=tel, status="nurture")
    assert (await _move(db_session, row, manager, "manager", "qualified")).status == "qualified"


@pytest.mark.asyncio
@pytest.mark.parametrize("current", ["application_enrollment", "converted"])
async def test_a_linked_or_converted_lead_cannot_move_to_nurture(db_session, current):
    manager, _ = await _team(db_session)
    row = await lead(db_session, status=current)
    with pytest.raises(RequestValidationError) as refused:
        await _move(db_session, row, manager, "manager", "nurture", "Next year")
    assert refused.value.errors()[0]["msg"] == lead_pipeline.STAGE_PAST


@pytest.mark.asyncio
async def test_a_counselor_cannot_choose_nurture_but_can_reactivate_a_nurture_lead(db_session):
    counselor = await make_counselor(db_session)
    row = await lead(db_session, status="qualified")
    row.owner_id, row.next_action, row.next_action_due = counselor.id, "Call back", date.today() + timedelta(days=1)
    await db_session.commit()
    with pytest.raises(RequestValidationError) as refused:
        await _move(db_session, row, counselor, "counselor", "nurture", "Later")
    assert refused.value.errors()[0]["msg"] == lead_pipeline.STAGE_SYSTEM
    row.status = "nurture"
    await db_session.commit()
    assert (await _move(db_session, row, counselor, "counselor", "follow_up")).status == "follow_up"


@pytest.mark.asyncio
async def test_the_stage_route_takes_nurture_and_refuses_it_without_a_reason(client, db_session):
    _, tel = await _team(db_session)
    row = await lead(db_session, telecaller=tel, status="contacted")
    await as_user(client, tel)
    refused = await client.post(stage_url(row.id), json={"to_stage": "nurture"})
    assert refused.status_code == 422 and refused.json()["detail"][0]["loc"][-1] == "reason"
    moved = await client.post(stage_url(row.id), json={"to_stage": "nurture", "reason": "Exams this month"})
    assert moved.status_code == 200, moved.text
    listed = (await client.get(LEADS, params={"status": "nurture"})).json()["items"]
    assert {i["id"] for i in listed} == {str(row.id)} and listed[0]["status_label"] == "Nurture"  # N6


# --- N4: events re-activate a Nurture lead; a call does not ------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "to_stage"),
    [("appointment_booked", "counselling_scheduled"), ("student_linked", "application_enrollment"), ("returned", "follow_up"), ("call_connected", "nurture"), ("call_unconnected", "nurture")],
)
async def test_events_from_nurture(db_session, event, to_stage):
    row = await lead(db_session, status="nurture")
    locked = await lead_pipeline.locked_lead(db_session, row.id)
    await lead_pipeline.apply_event(db_session, locked, event)
    await db_session.commit()
    assert locked.status == to_stage


@pytest.mark.asyncio
async def test_a_nurture_lead_can_be_handed_over_and_keeps_its_stage(db_session):
    _, tel = await _team(db_session)
    counselor = await make_counselor(db_session)
    row = await lead(db_session, telecaller=tel, status="nurture")
    locked = await lead_pipeline.locked_lead(db_session, row.id)
    await lead_handover.handover(db_session, tel, locked, counselor.id)
    await db_session.commit()
    assert (locked.status, locked.owner_id) == ("nurture", counselor.id)
    assert lead_handover.permissions(locked)["convert"] is False  # N4: not converted from a parked lead


# --- N5: never overdue -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_nurture_leads_past_due_follow_up_is_in_no_overdue_list_count_flag_or_filter(client, db_session):
    _, tel = await _team(db_session)
    working, parked = await lead(db_session, telecaller=tel, status="contacted"), await lead(db_session, telecaller=tel, status="nurture")
    now = datetime.now(UTC)
    late = await stored(db_session, working, tel, now - timedelta(hours=2))
    await stored(db_session, parked, tel, now - timedelta(hours=2))
    await as_user(client, tel)
    overdue = (await client.get(FOLLOW_UPS, params={"view": "overdue"})).json()
    assert [i["id"] for i in overdue["items"]] == [str(late.id)] and overdue["counts"]["overdue"] == 1
    mine = (await client.get(f"{LEADS}/{parked.id}/follow-ups")).json()["items"]
    assert [i["overdue"] for i in mine] == [False]
    filtered = {i["id"] for i in (await client.get(LEADS, params={"follow_up": "overdue"})).json()["items"]}
    assert filtered == {str(working.id)}
    assert (await telecaller_metrics.tiles(db_session, tel.id, "it", now))["overdue"] == 1


@pytest.mark.asyncio
async def test_a_nurture_leads_next_action_is_never_overdue(db_session):
    row = await lead(db_session, status="nurture")
    row.next_action, row.next_action_due = "Call after exams", date.today() - timedelta(days=3)
    await db_session.commit()
    assert (await lead_handover.next_action_out(db_session, row))["next_action_overdue"] is False


@pytest.mark.asyncio
async def test_a_nurture_follow_up_still_reminds_when_due_but_is_never_missed(db_session):
    await reset_settings(db_session)
    tel = await make_telecaller(db_session, await make_tl_manager(db_session))
    parked = await mk_lead(db_session, tel, status="nurture")
    await follow_up(db_session, parked, ist(D, 16))
    for at in (ist(D, 15, 50), ist(D, 17, 5)):
        await run(db_session, at)
    assert [n.title for n in await notes(db_session, tel)] == ["Follow-up due"]
