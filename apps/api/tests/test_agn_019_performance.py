"""AGN-019 (DEC-SCOPE-063) -- per-staff counts, rows, the funnel and the cohort range against hand counts (spec §4, §7)."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for
from tests.agn004_helpers import RECORDS, mk_record, mk_staff
from tests.agn008_helpers import agency_world, mk_application
from tests.agn017_helpers import deactivate
from tests.agn019_helpers import (
    FUNNEL_S1,
    FUNNEL_S2,
    FUNNEL_S3,
    FUNNEL_TOTAL,
    FUNNEL_UNASSIGNED,
    PERFORMANCE_API,
    STAGES,
    TABLE,
    TABLE_S1,
    TABLE_S2,
    TABLE_S3,
    TABLE_TOTAL,
    TABLE_UNASSIGNED,
    funnel,
    performance_world,
    table,
)


@pytest_asyncio.fixture
async def world(db_session):
    return await performance_world(db_session)


async def _body(email, **params) -> dict:
    async with client_for(email) as c:
        response = await c.get(PERFORMANCE_API, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _table(counts: dict) -> dict:
    return {k: counts[k] for k in TABLE}


def _rows(body: dict) -> dict:
    return {r["name"]: r for r in body["rows"]}


# --- table counts and rows (AC3, AC7) ------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_table_counts_equal_hand_counts(world):
    body = await _body(world["master"].email)
    rows = _rows(body)
    assert list(rows) == ["Staff One", "Staff Two", "Staff Three"]  # by seq
    assert _table(rows["Staff One"]) == TABLE_S1
    assert _table(rows["Staff Two"]) == TABLE_S2
    assert _table(rows["Staff Three"]) == TABLE_S3
    assert _table(body["unassigned"]) == TABLE_UNASSIGNED
    assert _table(body["total"]) == TABLE_TOTAL
    assert rows["Staff One"]["code"] == world["s1"]["member"].code and rows["Staff One"]["active"] is True


@pytest.mark.asyncio
async def test_no_ids_and_no_other_agency(world):
    async with client_for(world["master"].email) as c:
        text = (await c.get(PERFORMANCE_API)).text
    for value in (world["master"].id, world["s1"]["member"].id, world["s1"]["user"].id, world["r6"].id, world["u1"].id, world["other"]["org"].id):
        assert str(value) not in text
    assert "@" not in text  # no emails


@pytest.mark.asyncio
async def test_active_staff_with_nothing_is_listed_with_zeros(world, db_session):
    await mk_staff(db_session, world["org"], full_name="Staff Four")
    rows = _rows(await _body(world["master"].email))
    assert _table(rows["Staff Four"]) == dict.fromkeys(TABLE, 0) and rows["Staff Four"]["active"] is True


@pytest.mark.asyncio
async def test_deactivated_member_with_only_archived_student_is_listed(db_session):
    """Review Focus 3: table zeros, funnel 1 -- still listed, marked inactive."""
    w = await agency_world(db_session)
    await mk_record(db_session, agent=w["master"], full_name="Archived Only", assigned_member=w["staff"]["member"], status="archived")
    await deactivate(db_session, w["staff"]["member"])
    row = next(r for r in (await _body(w["master"].email))["rows"] if r["code"] == w["staff"]["member"].code)
    assert row["active"] is False and row["funnel"]["students"] >= 1


@pytest.mark.asyncio
async def test_deactivated_member_with_nothing_is_dropped(world, db_session):
    four = await mk_staff(db_session, world["org"], full_name="Staff Four")
    await deactivate(db_session, four["member"])
    assert "Staff Four" not in _rows(await _body(world["master"].email))


@pytest.mark.asyncio
async def test_application_reachable_two_ways_counts_once(db_session):
    """Review Focus 1: through the agency record AND the linked login -- one application."""
    w = await agency_world(db_session)

    async def row():
        return next(r for r in (await _body(w["master"].email))["rows"] if r["code"] == w["staff"]["member"].code)

    before = await row()
    await mk_application(db_session, agent=w["master"], university=w["university"], record=w["linked_record"], status="offer")
    after = await row()
    assert after["applications"] - before["applications"] == 1 and after["offers"] - before["offers"] == 1
    assert after["funnel"]["offers"] - before["funnel"]["offers"] <= 1


@pytest.mark.asyncio
async def test_total_is_rows_plus_unassigned(world):
    body = await _body(world["master"].email)
    parts = [*body["rows"], body["unassigned"]]
    assert _table(body["total"]) == {k: sum(p[k] for p in parts) for k in TABLE}
    assert body["total"]["funnel"] == {k: sum(p["funnel"][k] for p in parts) for k in STAGES}


# --- funnel and reassignment (AC1, AC2) ----------------------------------------------------------------------------------------------


def _non_increasing(f: dict) -> bool:
    values = [f[k] for k in STAGES]
    return all(a >= b for a, b in zip(values, values[1:], strict=False))


@pytest.mark.asyncio
async def test_funnel_equals_hand_counts_and_never_increases(world):
    body = await _body(world["master"].email)
    rows = _rows(body)
    assert rows["Staff One"]["funnel"] == FUNNEL_S1
    assert rows["Staff Two"]["funnel"] == FUNNEL_S2
    assert rows["Staff Three"]["funnel"] == FUNNEL_S3
    assert body["unassigned"]["funnel"] == FUNNEL_UNASSIGNED
    assert body["total"]["funnel"] == FUNNEL_TOTAL
    for f in [r["funnel"] for r in body["rows"]] + [body["unassigned"]["funnel"], body["total"]["funnel"]]:
        assert _non_increasing(f), f


@pytest.mark.asyncio
async def test_reassigned_student_counts_for_the_current_owner(world):
    """P1: r7 (enrolled, no visa case) moves s2 -> s1 through the real assign route; all of r7 moves with it."""
    async with client_for(world["master"].email) as c:
        moved = await c.post(f"{RECORDS}/{world['r7'].id}/assign", json={"member_id": str(world["s1"]["member"].id)})
    assert moved.status_code == 200, moved.text
    rows = _rows(await _body(world["master"].email))
    assert rows["Staff One"]["funnel"] == funnel(4, 4, 3, 3, 2, 2)
    assert rows["Staff Two"]["funnel"] == funnel(2, 2, 2, 1, 1, 0)
    assert _table(rows["Staff One"]) == table(3, 6, 4, 1, 1, 2)
    assert _table(rows["Staff Two"]) == table(2, 2, 2, 1, 0, 0)
