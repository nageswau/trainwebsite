"""bdm-010 -- expense lines (T5, T7, T13, A9; AC5)."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, BdmTripExpense
from app.services.bdm_travel import MAX_EXPENSES, india_today
from tests.bdm010_helpers import TEAM_TRIPS, TRIPS, act, bdm_pair, make_trip, sign_in


async def _approved(client, db):
    manager, bdm = await bdm_pair(client, db)
    trip = await make_trip(client)
    await act(client, trip["id"], "submit")
    await sign_in(client, manager)
    await client.post(f"{TEAM_TRIPS}/{trip['id']}/approve")
    await sign_in(client, bdm)
    return trip


def _line(**over):
    return {"category": "food", "amount": "450.50", "expense_date": str(india_today()), **over}


@pytest.mark.asyncio
async def test_expenses_only_after_approval(client, db_session):
    await bdm_pair(client, db_session)
    trip = await make_trip(client)
    refused = await client.post(f"{TRIPS}/{trip['id']}/expenses", json=_line())
    assert (refused.status_code, refused.json()["detail"]) == (409, "Expenses can be added once the trip is approved")


@pytest.mark.asyncio
async def test_actual_cost_is_the_sum_of_lines_and_each_write_is_audited(client, db_session):
    trip = await _approved(client, db_session)
    first = await client.post(f"{TRIPS}/{trip['id']}/expenses", json=_line())
    assert first.status_code == 201 and first.json()["actual_cost"] == "450.50"
    second = (await client.post(f"{TRIPS}/{trip['id']}/expenses", json=_line(category="stay", amount=1200))).json()
    assert second["actual_cost"] == "1650.50" and len(second["expenses"]) == 2
    line_id = second["expenses"][0]["id"]
    updated = (await client.patch(f"{TRIPS}/{trip['id']}/expenses/{line_id}", json={"amount": "500"})).json()
    assert updated["actual_cost"] == "1700.00"
    deleted = await client.delete(f"{TRIPS}/{trip['id']}/expenses/{line_id}")
    assert deleted.status_code == 200 and deleted.json()["actual_cost"] == "1200.00"
    assert (await client.delete(f"{TRIPS}/{trip['id']}/expenses/{line_id}")).status_code == 404
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == trip["id"]))).all()
    assert {"bdm.trip_expense_add", "bdm.trip_expense_update", "bdm.trip_expense_delete"} <= set(actions)
    listed = (await client.get(TRIPS)).json()["items"][0]
    assert listed["actual_cost"] == "1200.00"


@pytest.mark.asyncio
async def test_amount_must_be_positive(client, db_session):
    trip = await _approved(client, db_session)
    for amount in ("0", "-5", "1.005"):
        assert (await client.post(f"{TRIPS}/{trip['id']}/expenses", json=_line(amount=amount))).status_code == 422


@pytest.mark.asyncio
async def test_expenses_allowed_after_completion_and_after_cancel(client, db_session):
    trip = await _approved(client, db_session)
    await act(client, trip["id"], "cancel")
    assert (await client.post(f"{TRIPS}/{trip['id']}/expenses", json=_line())).status_code == 201


@pytest.mark.asyncio
async def test_line_cap(client, db_session):
    trip = await _approved(client, db_session)
    db_session.add_all([BdmTripExpense(trip_id=uuid.UUID(trip["id"]), category="food", amount=1, expense_date=india_today(),
                                       created_by_user_id=uuid.UUID(trip["bdm"]["id"])) for _ in range(MAX_EXPENSES)])
    await db_session.commit()
    over = await client.post(f"{TRIPS}/{trip['id']}/expenses", json=_line())
    assert (over.status_code, over.json()["detail"]) == (409, f"A trip can have at most {MAX_EXPENSES} expense lines")
    count = await db_session.scalar(select(func.count()).where(BdmTripExpense.trip_id == uuid.UUID(trip["id"])))
    assert count == MAX_EXPENSES


@pytest.mark.asyncio
async def test_empty_expense_patch(client, db_session):
    trip = await _approved(client, db_session)
    line = (await client.post(f"{TRIPS}/{trip['id']}/expenses", json=_line())).json()["expenses"][0]
    assert (await client.patch(f"{TRIPS}/{trip['id']}/expenses/{line['id']}", json={})).json()["detail"] == "Nothing to change"
