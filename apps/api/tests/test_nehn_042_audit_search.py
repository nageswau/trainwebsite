"""nehn-042 (DEC-SCOPE-288) -- GET /admin/audit filters, paging and the division scope in SQL (spec A1-A5; AC1-AC4)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.models import AuditLog
from tests.bdm001_helpers import login, make_user

AUDIT = "/api/v1/admin/audit"


def tag() -> str:
    """A unique entity type per test, so rows other tests (or the seed) wrote never match."""
    return f"n042.{uuid.uuid4().hex[:10]}"


async def write(db, actor, entity_type: str, *, action: str = "thing.update", entity_id: str | None = "E-1", at: datetime | None = None) -> AuditLog:
    row = AuditLog(user_id=actor.id if actor else None, action=action, entity_type=entity_type, entity_id=entity_id, metadata_json={})
    db.add(row)
    await db.flush()
    if at:
        await db.execute(update(AuditLog).where(AuditLog.id == row.id).values(created_at=at))
    await db.commit()
    return row


async def audit(client, **params) -> list[dict]:
    response = await client.get(AUDIT, params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_ac1_entity_filter_returns_one_payments_whole_history(client, db_session):
    admin = await make_user(db_session, "super_admin", "global")
    kind = tag()
    payment_id = str(uuid.uuid4())
    await write(db_session, admin, kind, action="payment.create", entity_id=payment_id)
    await write(db_session, admin, kind, action="payment.discount", entity_id=payment_id)
    await write(db_session, admin, kind, action="payment.create", entity_id=str(uuid.uuid4()))  # another payment
    await login(client, admin)
    rows = await audit(client, entity_type=kind, entity_id=payment_id)
    assert [r["action"] for r in rows] == ["payment.discount", "payment.create"]  # newest first
    assert rows[0]["actor"] == {"id": str(admin.id), "full_name": admin.full_name, "email": admin.email, "division": "global"}


@pytest.mark.asyncio
async def test_action_is_a_literal_prefix_and_actor_and_division_filter(client, db_session):
    admin = await make_user(db_session, "super_admin", "global")
    it_user = await make_user(db_session, "trainer", "it")
    ov_user = await make_user(db_session, "counselor", "overseas")
    kind = tag()
    await write(db_session, it_user, kind, action="payment.discount")
    await write(db_session, ov_user, kind, action="payment.create")
    await write(db_session, it_user, kind, action="lead.update")
    await write(db_session, it_user, kind, action="pay%ment.x")
    await login(client, admin)
    assert sorted(r["action"] for r in await audit(client, entity_type=kind, action="payment.")) == ["payment.create", "payment.discount"]
    assert [r["action"] for r in await audit(client, entity_type=kind, action="pay%")] == ["pay%ment.x"]  # % is literal
    assert {r["user_id"] for r in await audit(client, entity_type=kind, actor=str(ov_user.id))} == {str(ov_user.id)}
    assert {r["actor"]["division"] for r in await audit(client, entity_type=kind, division="it")} == {"it"}


@pytest.mark.asyncio
async def test_date_range_is_inclusive_india_days(client, db_session):
    admin = await make_user(db_session, "super_admin", "global")
    kind = tag()
    # 2026-03-01 23:30 IST is 18:00 UTC; 2026-03-02 00:30 IST is 2026-03-01 19:00 UTC.
    await write(db_session, admin, kind, action="a.first", at=datetime(2026, 3, 1, 18, 0, tzinfo=UTC))
    await write(db_session, admin, kind, action="a.second", at=datetime(2026, 3, 1, 19, 0, tzinfo=UTC))
    await login(client, admin)
    assert [r["action"] for r in await audit(client, entity_type=kind, date_from="2026-03-01", date_to="2026-03-01")] == ["a.first"]
    assert [r["action"] for r in await audit(client, entity_type=kind, date_from="2026-03-02")] == ["a.second"]


@pytest.mark.asyncio
async def test_ac2_it_admin_never_receives_overseas_rows_even_beyond_the_newest_500(client, db_session):
    it_admin = await make_user(db_session, "it_admin", "it")
    it_user = await make_user(db_session, "trainer", "it")
    ov_user = await make_user(db_session, "counselor", "overseas")
    kind = tag()
    old = datetime.now(UTC) - timedelta(days=400)
    mine = await write(db_session, it_user, kind, action="x.mine", at=old)
    system = await write(db_session, None, kind, action="x.system", at=old)
    await write(db_session, ov_user, kind, action="x.overseas")
    await login(client, it_admin)
    assert {r["id"] for r in await audit(client, entity_type=kind)} == {str(mine.id), str(system.id)}
    assert await audit(client, entity_type=kind, division="overseas") == []
    assert await audit(client, entity_type=kind, actor=str(ov_user.id)) == []
    # The scope is in the SQL: an unfiltered page of the newest rows holds no overseas actor either.
    page = await audit(client, limit=500)
    assert all(r["actor"] is None or r["actor"]["division"] == "it" for r in page)


@pytest.mark.asyncio
async def test_ac3_paging_goes_beyond_500_rows(client, db_session):
    admin = await make_user(db_session, "super_admin", "global")
    kind = tag()
    start = datetime(2025, 1, 1, tzinfo=UTC)
    db_session.add_all([AuditLog(user_id=admin.id, action=f"bulk.{i:03d}", entity_type=kind, entity_id=str(i), metadata_json={}, created_at=start + timedelta(minutes=i)) for i in range(503)])
    await db_session.commit()
    await login(client, admin)
    first = await audit(client, entity_type=kind)
    assert len(first) == 500  # the default page is today's 500
    rest = await audit(client, entity_type=kind, offset=500)
    assert [r["action"] for r in rest] == ["bulk.002", "bulk.001", "bulk.000"]
    small = await audit(client, entity_type=kind, limit=2, offset=1)
    assert [r["action"] for r in small] == ["bulk.501", "bulk.500"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"date_from": "2026-03-02", "date_to": "2026-03-01"},
        {"division": "mars"},
        {"actor": "not-a-uuid"},
        {"date_from": "yesterday"},
        {"limit": 0},
        {"limit": 501},
        {"offset": -1},
    ],
)
async def test_bad_filters_are_422(client, db_session, params):
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await client.get(AUDIT, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_ac4_non_admin_is_403_whatever_the_filters(client, db_session):
    await login(client, await make_user(db_session, "counselor", "overseas"))
    assert (await client.get(AUDIT, params={"entity_type": "payment"})).status_code == 403


@pytest.mark.asyncio
async def test_system_rows_have_no_actor(client, db_session):
    admin = await make_user(db_session, "super_admin", "global")
    kind = tag()
    await write(db_session, None, kind, action="x.system")
    await login(client, admin)
    (row,) = await audit(client, entity_type=kind)
    assert row["user_id"] is None and row["actor"] is None
