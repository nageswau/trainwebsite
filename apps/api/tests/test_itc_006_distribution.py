"""itc-006 (DEC-SCOPE-337) -- services/lead_distribution.py: the source rule (first) and the team's workload strategy.

Pools are narrowed with `only_eligible` inside an uncommitted transaction that each test rolls back (the shared database is never
truncated); the strategy is switched the same way, so no test leaves a team on `workload`."""

import uuid

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, Enquiry, TelDistributionRule, TelSetting
from app.services import lead_distribution
from tests.tel007_helpers import city, make_telecaller, make_tl_manager, only_eligible, product, rule


async def source_rule(db, telecaller, source: str, *, team: str = "it") -> TelDistributionRule:
    """A source is unique per team, so an earlier test's committed rule for it is moved aside inside this (rolled back) transaction."""
    await db.execute(update(TelDistributionRule).where(TelDistributionRule.team == team, TelDistributionRule.source == source)
                     .values(telecaller_user_id=telecaller.id))
    existing = await db.scalar(select(TelDistributionRule).where(TelDistributionRule.team == team, TelDistributionRule.source == source))
    if existing:
        return existing
    row = TelDistributionRule(team=team, kind="source", source=source, telecaller_user_id=telecaller.id)
    db.add(row)
    await db.flush()
    return row


async def new_lead(db, *, division="it", source="website", product_id=None, city_name=None, telecaller=None, status="new") -> Enquiry:
    row = Enquiry(division=division, name=f"Lead {uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:8]}@example.local", subject="Python",
                  message="Hello", source=source, status=status, product_id=product_id, city=city_name,
                  telecaller_user_id=telecaller.id if telecaller else None)
    db.add(row)
    await db.flush()
    return row


async def use_strategy(db, team: str, strategy: str) -> None:
    await db.execute(update(TelSetting).where(TelSetting.team == team).values(distribution_strategy=strategy))


async def _audit(db, row):
    return await db.scalar(select(AuditLog).where(AuditLog.action == "lead.assign", AuditLog.entity_id == str(row.id)))


# --- AC1: a source rule wins over the product and city rules -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_source_rule_wins_over_product_and_city(db_session):
    manager = await make_tl_manager(db_session)
    by_source, by_product, by_city = [await make_telecaller(db_session, manager) for _ in range(3)]
    item, town = await product(db_session), city()
    await rule(db_session, by_product, product_id=item.id)
    await rule(db_session, by_city, city_name=town)
    await source_rule(db_session, by_source, "instagram")
    row = await new_lead(db_session, source="instagram", product_id=item.id, city_name=town)
    assert await lead_distribution.distribute(db_session, row) == "source_rule"
    assert row.telecaller_user_id == by_source.id
    other = await new_lead(db_session, source="facebook", product_id=item.id, city_name=town)
    assert await lead_distribution.distribute(db_session, other) == "product_rule"  # no rule for this source: today's order
    await db_session.rollback()


@pytest.mark.asyncio
async def test_inactive_source_rule_falls_through(db_session):
    manager = await make_tl_manager(db_session)
    gone, by_city = await make_telecaller(db_session, manager), await make_telecaller(db_session, manager)
    town = city()
    await rule(db_session, by_city, city_name=town)
    await source_rule(db_session, gone, "google")
    gone.active = False
    row = await new_lead(db_session, source="google", city_name=town)
    assert await lead_distribution.distribute(db_session, row) == "city_rule"
    assert row.telecaller_user_id == by_city.id
    await db_session.rollback()


@pytest.mark.asyncio
async def test_a_source_rule_on_the_other_team_never_matches(db_session):
    manager = await make_tl_manager(db_session)
    overseas = await make_telecaller(db_session, manager, team="overseas")
    await source_rule(db_session, overseas, "whatsapp", team="overseas")
    row = await new_lead(db_session, division="it", source="whatsapp")
    assert await lead_distribution.distribute(db_session, row) in ("round_robin", "workload")
    assert row.telecaller_user_id != overseas.id
    await db_session.rollback()


# --- AC4: the audit row names the rule ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_audit_names_the_rule(db_session):
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    matched = await source_rule(db_session, tel, "referral")
    row = await new_lead(db_session, source="referral")
    await lead_distribution.distribute(db_session, row)
    await db_session.flush()
    audit = await _audit(db_session, row)
    assert audit.metadata_json == {"from": None, "to": str(tel.id), "method": "source_rule", "rule_id": str(matched.id)}
    await db_session.rollback()


# --- AC2: workload picks the fewest open leads; closed and converted leads don't count ------------------------------------------
@pytest.mark.asyncio
async def test_workload_picks_fewest_open_leads(db_session):
    manager = await make_tl_manager(db_session)
    busy, light, idle_but_done = [await make_telecaller(db_session, manager, team="overseas") for _ in range(3)]
    for _ in range(3):
        await new_lead(db_session, division="overseas", telecaller=busy, status="contacted")
    await new_lead(db_session, division="overseas", telecaller=light, status="assigned")
    for status in ("lost", "converted", "no_response", "not_interested"):  # finished work is not workload
        await new_lead(db_session, division="overseas", telecaller=idle_but_done, status=status)
    await only_eligible(db_session, "overseas", [busy, light, idle_but_done])
    await use_strategy(db_session, "overseas", "workload")
    row = await new_lead(db_session, division="overseas")
    assert await lead_distribution.distribute(db_session, row) == "workload"
    assert row.telecaller_user_id == idle_but_done.id
    await db_session.flush()
    assert (await _audit(db_session, row)).metadata_json == {"from": None, "to": str(idle_but_done.id), "method": "workload"}
    nxt = await new_lead(db_session, division="overseas")  # idle_but_done now has 1 open, as light: the tie goes in turn
    assert await lead_distribution.distribute(db_session, nxt) == "workload"
    assert nxt.telecaller_user_id in (light.id, idle_but_done.id) and nxt.telecaller_user_id != busy.id
    await db_session.rollback()


@pytest.mark.asyncio
async def test_workload_ties_go_in_turn(db_session):
    manager = await make_tl_manager(db_session)
    team = [await make_telecaller(db_session, manager, team="overseas") for _ in range(3)]
    ids = {u.id for u in team}
    await only_eligible(db_session, "overseas", team)
    await use_strategy(db_session, "overseas", "workload")
    picks = []
    for _ in range(6):
        row = await new_lead(db_session, division="overseas")
        assert await lead_distribution.distribute(db_session, row) == "workload"
        picks.append(row.telecaller_user_id)
    await db_session.rollback()
    assert set(picks[:3]) == ids and set(picks[3:]) == ids  # equal load: everyone once before anyone twice


# --- AC3 / E: inactive telecallers are never picked; nobody eligible -> the unassigned queue ------------------------------------
@pytest.mark.asyncio
async def test_workload_skips_inactive(db_session):
    manager = await make_tl_manager(db_session)
    gone, here = await make_telecaller(db_session, manager, team="overseas"), await make_telecaller(db_session, manager, team="overseas")
    await new_lead(db_session, division="overseas", telecaller=here, status="contacted")
    await only_eligible(db_session, "overseas", [here])  # `gone` (0 open leads) is inactive
    await use_strategy(db_session, "overseas", "workload")
    row = await new_lead(db_session, division="overseas")
    assert await lead_distribution.distribute(db_session, row) == "workload"
    assert row.telecaller_user_id == here.id != gone.id
    await db_session.rollback()


@pytest.mark.asyncio
async def test_workload_with_nobody_eligible_leaves_unassigned(db_session):
    await only_eligible(db_session, "overseas", [])
    await use_strategy(db_session, "overseas", "workload")
    row = await new_lead(db_session, division="overseas")
    assert await lead_distribution.distribute(db_session, row) is None
    assert row.telecaller_user_id is None and row.status == "new"
    await db_session.rollback()


@pytest.mark.asyncio
async def test_round_robin_stays_the_default(db_session):
    assert (await db_session.get(TelSetting, "it")).distribution_strategy == "round_robin"
    assert (await db_session.get(TelSetting, "overseas")).distribution_strategy == "round_robin"
