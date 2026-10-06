"""tel-007 -- services/lead_distribution.py on the database session (spec §2, §4; AC1-AC4, DI1, DI2, D1, D2, D4)."""

import uuid
from collections import Counter

import pytest
from sqlalchemy import select

from app.models import AuditLog, LeadStageHistory
from app.services import lead_distribution
from tests.tel007_helpers import city, lead, make_telecaller, make_tl_manager, only_eligible, product, rule


async def _history(db, row):
    return (await db.execute(select(LeadStageHistory.from_stage, LeadStageHistory.to_stage, LeadStageHistory.event, LeadStageHistory.actor_user_id)
                             .where(LeadStageHistory.lead_id == row.id))).all()


async def _audits(db, row):
    return (await db.scalars(select(AuditLog).where(AuditLog.action == "lead.assign", AuditLog.entity_id == str(row.id)))).all()


# --- AC2: the pure round-robin step --------------------------------------------------------------------------------------
def test_next_in_turn_is_even_and_wraps():
    a, b, c = sorted(uuid.uuid4() for _ in range(3))
    assert lead_distribution.next_in_turn([a, b, c], None) == a
    assert lead_distribution.next_in_turn([a, b, c], a) == b
    assert lead_distribution.next_in_turn([a, b, c], c) == a  # wraps
    last, picks = None, []
    for _ in range(9):
        last = lead_distribution.next_in_turn([a, b, c], last)
        picks.append(last)
    assert Counter(picks) == {a: 3, b: 3, c: 3}  # 3 telecallers, 9 leads -> 3 each


def test_next_in_turn_skips_a_departed_cursor_and_handles_nobody():
    a, b, c = sorted(uuid.uuid4() for _ in range(3))
    assert lead_distribution.next_in_turn([a, c], b) == c  # b was deactivated: the next one after it in order
    assert lead_distribution.next_in_turn([], a) is None


# --- AC1: product rule, then city rule, then round robin -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_rules_apply_in_order(db_session):
    manager = await make_tl_manager(db_session)
    by_product, by_city = await make_telecaller(db_session, manager), await make_telecaller(db_session, manager)
    item, town = await product(db_session), city()
    await rule(db_session, by_product, product_id=item.id)
    await rule(db_session, by_city, city_name=town)

    both = await lead(db_session, product_id=item.id, city_name=town)
    assert await lead_distribution.distribute(db_session, both) == "product_rule"
    assert both.telecaller_user_id == by_product.id

    city_only = await lead(db_session, city_name=f"  {town.upper()} ")  # matched trimmed and case-insensitively
    assert await lead_distribution.distribute(db_session, city_only) == "city_rule"
    assert city_only.telecaller_user_id == by_city.id

    neither = await lead(db_session)
    assert await lead_distribution.distribute(db_session, neither) == "round_robin"
    assert neither.telecaller_user_id is not None
    await db_session.commit()


@pytest.mark.asyncio
async def test_assignment_moves_the_stage_and_is_audited(db_session):
    manager = await make_tl_manager(db_session)
    tel, town = await make_telecaller(db_session, manager), city()
    await rule(db_session, tel, city_name=town)
    row = await lead(db_session, city_name=town)
    assert await lead_distribution.distribute(db_session, row) == "city_rule"
    await db_session.commit()
    assert row.status == "assigned"
    assert await _history(db_session, row) == [("new", "assigned", "assigned", None)]  # the system moved it
    [audit] = await _audits(db_session, row)
    assert audit.user_id is None and audit.metadata_json == {"from": None, "to": str(tel.id), "method": "city_rule"}


# --- AC3: a deactivated telecaller is skipped -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_inactive_rule_telecaller_falls_through(db_session):
    manager = await make_tl_manager(db_session)
    gone, by_city = await make_telecaller(db_session, manager), await make_telecaller(db_session, manager)
    item, town = await product(db_session), city()
    await rule(db_session, gone, product_id=item.id)
    await rule(db_session, by_city, city_name=town)
    gone.active = False
    await db_session.commit()
    row = await lead(db_session, product_id=item.id, city_name=town)
    assert await lead_distribution.distribute(db_session, row) == "city_rule"
    assert row.telecaller_user_id == by_city.id
    await db_session.commit()


@pytest.mark.asyncio
async def test_a_rule_on_the_other_team_never_matches(db_session):
    manager = await make_tl_manager(db_session)
    overseas, town = await make_telecaller(db_session, manager, team="overseas"), city()
    await rule(db_session, overseas, team="overseas", city_name=town)
    row = await lead(db_session, division="it", city_name=town)
    assert await lead_distribution.distribute(db_session, row) == "round_robin"
    assert row.telecaller_user_id != overseas.id
    await db_session.rollback()


# --- AC2 integration: even across the team's active telecallers, in cursor order ------------------------------------------
@pytest.mark.asyncio
async def test_round_robin_is_even_across_the_active_team(db_session):
    manager = await make_tl_manager(db_session)
    team = [await make_telecaller(db_session, manager, team="overseas") for _ in range(3)]
    ids = sorted(u.id for u in team)  # read before the rollback expires the rows
    leads = [await lead(db_session, division="overseas") for _ in range(9)]
    await only_eligible(db_session, "overseas", team)  # uncommitted; rolled back below
    picks = []
    for row in leads:
        assert await lead_distribution.distribute(db_session, row) == "round_robin"
        picks.append(row.telecaller_user_id)
    await db_session.rollback()
    assert Counter(picks) == {i: 3 for i in ids}
    assert picks[:3] == picks[3:6] == picks[6:]  # a fixed rotation, in user-id order from wherever the cursor stood
    assert all(lead_distribution.next_in_turn(ids, a) == b for a, b in zip(picks, picks[1:], strict=False))


# --- AC4: no candidate -> unassigned ----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_nobody_eligible_leaves_the_lead_unassigned(db_session):
    row = await lead(db_session, division="overseas")
    await only_eligible(db_session, "overseas", [])
    assert await lead_distribution.distribute(db_session, row) is None
    assert row.telecaller_user_id is None and row.status == "new"
    await db_session.rollback()


@pytest.mark.asyncio
async def test_a_product_without_a_team_goes_to_the_queue(db_session):
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    item = await product(db_session, group="other", team=None)  # T18: Career Guidance / General Enquiry
    await rule(db_session, tel, city_name=(town := city()))
    row = await lead(db_session, product_id=item.id, city_name=town)
    assert await lead_distribution.distribute(db_session, row) is None
    await db_session.commit()
    assert row.telecaller_user_id is None and row.status == "new"
    assert await _history(db_session, row) == [] and await _audits(db_session, row) == []


# --- spec §4: intake never loses an enquiry to a distribution error ----------------------------------------------------------
@pytest.mark.asyncio
async def test_on_intake_rolls_back_to_the_savepoint_on_error(db_session, monkeypatch):
    async def broken(db, row):
        row.telecaller_user_id = uuid.uuid4()  # a half-done write that must not survive
        raise RuntimeError("boom")

    monkeypatch.setattr(lead_distribution, "distribute", broken)
    row = await lead(db_session)
    await lead_distribution.on_intake(db_session, row)
    await db_session.commit()
    await db_session.refresh(row)
    assert row.telecaller_user_id is None and row.status == "new"
