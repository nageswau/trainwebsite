"""tel-004 -- services/lead_pipeline.py on the database session (spec §2, §4; AC1-AC4, PL2, PL4, D1-D3)."""

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select

from app.lead_stages import CLOSED, EVENTS, STAGES
from app.models import LeadStageHistory
from app.services import lead_pipeline
from tests.tel004_helpers import lead, make_telecaller, make_tl_manager


async def _history(db, row):
    return (await db.execute(select(LeadStageHistory.from_stage, LeadStageHistory.to_stage, LeadStageHistory.event, LeadStageHistory.reason)
                             .where(LeadStageHistory.lead_id == row.id).order_by(LeadStageHistory.position))).all()


async def _move(db, row, kind, to_stage, reason=None, *, actor):
    locked = await lead_pipeline.locked_lead(db, row.id)
    await lead_pipeline.person_move(db, locked, actor, kind, to_stage, reason)
    await db.commit()
    return locked


async def _fixtures(db):
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager)


# --- AC1: each automatic transition fires once from its event ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_events_walk_the_pipeline_once_each(db_session):
    _, tel = await _fixtures(db_session)
    row = await lead(db_session, telecaller=tel)
    before = row.stage_changed_at
    for event, expected in (("assigned", "assigned"), ("call_unconnected", "first_call_pending"), ("call_connected", "contacted"),
                            ("appointment_booked", "counselling_scheduled"), ("appointment_completed", "counselling_completed"),
                            ("student_linked", "application_enrollment"), ("converted", "converted")):
        locked = await lead_pipeline.locked_lead(db_session, row.id)
        assert await lead_pipeline.apply_event(db_session, locked, event) is True
        await db_session.commit()
        assert locked.status == expected
        locked = await lead_pipeline.locked_lead(db_session, row.id)
        assert await lead_pipeline.apply_event(db_session, locked, event) is False  # a repeat never fires twice
        await db_session.commit()
    history = await _history(db_session, row)
    assert [h[1] for h in history] == ["assigned", "first_call_pending", "contacted", "counselling_scheduled", "counselling_completed",
                                       "application_enrollment", "converted"]
    assert all(h[2] != "manual" for h in history)
    assert locked.stage_changed_at >= before


@pytest.mark.asyncio
async def test_first_connected_call_moves_first_call_pending_to_contacted(db_session):
    row = await lead(db_session, status="first_call_pending")
    locked = await lead_pipeline.locked_lead(db_session, row.id)
    assert await lead_pipeline.apply_event(db_session, locked, "call_connected")
    await db_session.commit()
    assert (await _history(db_session, row)) == [("first_call_pending", "contacted", "call_connected", None)]


@pytest.mark.asyncio
async def test_unlink_returns_application_enrollment_to_follow_up_only(db_session):
    row = await lead(db_session, status="application_enrollment")
    locked = await lead_pipeline.locked_lead(db_session, row.id)
    assert await lead_pipeline.apply_event(db_session, locked, "student_unlinked")
    assert locked.status == "follow_up"
    assert await lead_pipeline.apply_event(db_session, locked, "student_unlinked") is False
    await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("event", sorted(EVENTS))
async def test_events_on_a_closed_lead_do_not_move_it(db_session, event):
    row = await lead(db_session, status="lost")
    locked = await lead_pipeline.locked_lead(db_session, row.id)
    assert await lead_pipeline.apply_event(db_session, locked, event) is False
    await db_session.commit()
    assert locked.status == "lost" and await _history(db_session, row) == []


@pytest.mark.asyncio
async def test_unknown_event_is_a_programming_error(db_session):
    row = await lead(db_session)
    with pytest.raises(KeyError):
        await lead_pipeline.apply_event(db_session, row, "teleported")


# --- AC2 / D2: what a person may choose ------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("to_stage", ["new", "assigned", "first_call_pending", "contacted", "counselling_scheduled", "counselling_completed",
                                      "application_enrollment", "converted"])
async def test_a_person_cannot_choose_a_system_stage(db_session, to_stage):
    _, tel = await _fixtures(db_session)
    row = await lead(db_session, telecaller=tel, status="interested")
    with pytest.raises(RequestValidationError):
        await _move(db_session, row, "telecaller", to_stage, actor=tel)


@pytest.mark.asyncio
@pytest.mark.parametrize("to_stage", ["teleported", "qualified"])
async def test_unknown_or_same_stage_is_422(db_session, to_stage):
    _, tel = await _fixtures(db_session)
    row = await lead(db_session, telecaller=tel, status="qualified")
    with pytest.raises(RequestValidationError):
        await _move(db_session, row, "telecaller", to_stage, actor=tel)


@pytest.mark.asyncio
async def test_manual_moves_any_direction_before_application_with_optional_reason(db_session):
    _, tel = await _fixtures(db_session)
    row = await lead(db_session, telecaller=tel, status="counselling_scheduled")
    await _move(db_session, row, "telecaller", "follow_up", actor=tel)
    await _move(db_session, row, "telecaller", "qualified", "Re-checked eligibility", actor=tel)
    assert await _history(db_session, row) == [("counselling_scheduled", "follow_up", "manual", None),
                                                ("follow_up", "qualified", "manual", "Re-checked eligibility")]


@pytest.mark.asyncio
@pytest.mark.parametrize(("current", "to_stage"), [("application_enrollment", "qualified"), ("converted", "follow_up"), ("converted", "lost")])
async def test_no_manual_or_closed_move_once_counselor_or_converted(db_session, current, to_stage):
    manager, _ = await _fixtures(db_session)
    row = await lead(db_session, status=current)
    with pytest.raises(RequestValidationError):
        await _move(db_session, row, "manager", to_stage, "x", actor=manager)


# --- AC3 / D1: closed outcomes need a reason --------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("to_stage", sorted(CLOSED))
async def test_closed_outcome_needs_a_reason(db_session, to_stage):
    _, tel = await _fixtures(db_session)
    row = await lead(db_session, telecaller=tel, status="contacted")
    with pytest.raises(RequestValidationError):
        await _move(db_session, row, "telecaller", to_stage, None, actor=tel)
    locked = await _move(db_session, row, "telecaller", to_stage, "Asked not to call again", actor=tel)
    assert locked.status == to_stage
    assert (await _history(db_session, row))[-1] == ("contacted", to_stage, "manual", "Asked not to call again")


@pytest.mark.asyncio
async def test_closed_outcome_allowed_from_application_enrollment(db_session):
    manager, _ = await _fixtures(db_session)
    row = await lead(db_session, status="application_enrollment")
    assert (await _move(db_session, row, "manager", "lost", "Chose another institute", actor=manager)).status == "lost"


# --- AC4 / D3: only a manager or admin reopens -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_telecaller_cannot_touch_a_closed_lead(db_session):
    _, tel = await _fixtures(db_session)
    row = await lead(db_session, telecaller=tel, status="no_response")
    for to_stage in ("follow_up", "qualified"):
        with pytest.raises(HTTPException) as refused:
            await _move(db_session, row, "telecaller", to_stage, "Picked up now", actor=tel)
        assert refused.value.status_code == 403


@pytest.mark.asyncio
async def test_manager_reopens_to_follow_up_with_a_reason(db_session):
    manager, tel = await _fixtures(db_session)
    row = await lead(db_session, telecaller=tel, status="wrong_number")
    for to_stage, reason in (("qualified", "x"), ("lost", "x"), ("follow_up", None)):
        with pytest.raises(RequestValidationError):
            await _move(db_session, row, "manager", to_stage, reason, actor=manager)
    locked = await _move(db_session, row, "manager", "follow_up", "Correct number found", actor=manager)
    assert locked.status == "follow_up"
    assert (await _history(db_session, row))[-1] == ("wrong_number", "follow_up", "reopen", "Correct number found")


def test_catalogue_has_eleven_open_stages_and_five_closed():
    assert len(STAGES) == 16 and len(CLOSED) == 5
