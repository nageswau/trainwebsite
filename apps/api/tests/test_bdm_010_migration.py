"""bdm-010 -- migration 0068_bdm_trips (spec §4; AC10). Round trip and the downgrade refusal run in a throwaway database
(the bdm-001 pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_bdm_010_migration_0068", VERSIONS / "0068_bdm_trips.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0067_audit_entity_index", "0068_bdm_trips"
USERS = "SELECT id, email, role FROM users ORDER BY id"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0067_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1  # later revisions (bdm-009) chain after this one


def test_models_match_the_migration():
    from app.models import BdmTrip, BdmTripExpense

    trips = BdmTrip.__table__
    assert {c.name for c in trips.columns} == {
        "id", "code", "bdm_user_id", "travel_date", "return_date", "from_place", "to_place", "purpose", "mode",
        "accommodation_required", "estimated_cost", "currency", "approval_status", "travel_status", "rejection_reason",
        "decided_by_user_id", "submitted_at", "decided_at", "completed_at", "cancelled_at", "remarks", "created_at", "updated_at",
    }
    names = {i.name for i in trips.indexes} | {c.name for c in trips.constraints}
    assert {
        "uq_bdm_trips_code", "ck_bdm_trips_dates", "ck_bdm_trips_mode", "ck_bdm_trips_estimated_cost", "ck_bdm_trips_currency",
        "ck_bdm_trips_approval_status", "ck_bdm_trips_travel_status", "ck_bdm_trips_status_pair",
        "ix_bdm_trips_bdm_travel_date", "ix_bdm_trips_submitted",
    } <= names
    expenses = BdmTripExpense.__table__
    assert {c.name for c in expenses.columns} == {
        "id", "trip_id", "category", "amount", "expense_date", "note", "created_by_user_id", "created_at", "updated_at",
    }
    assert {"ck_bdm_trip_expenses_category", "ck_bdm_trip_expenses_amount", "ix_bdm_trip_expenses_trip"} <= (
        {i.name for i in expenses.indexes} | {c.name for c in expenses.constraints}
    )


@pytest.mark.asyncio
async def test_tables_and_sequence_exist_in_the_shared_database(db_session):
    rows = (await db_session.execute(sa.text(
        "SELECT relname, relkind::text FROM pg_class WHERE relname IN ('bdm_trips', 'bdm_trip_expenses', 'bdm_trip_code_seq')"
    ))).all()
    assert dict(rows) == {"bdm_trips": "r", "bdm_trip_expenses": "r", "bdm_trip_code_seq": "S"}


def _sql(url: str, sql: str, params: dict | None = None, *, autocommit: bool = False):
    async def _inner():
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT") if autocommit else create_async_engine(url)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(sa.text(sql), params or {})
                return result.fetchall() if result.returns_rows else None
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


@pytest.fixture
def isolated_db():
    """A fresh database at 0067 with one user (the trip owner)."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm010_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        owner = uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'Owner', 'bdm', 'it', true, true, 'en-GB', '{}')",
            {"id": owner, "email": f"owner-{name}@example.local"},
        )
        yield {"cfg": cfg, "url": url, "owner": owner}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


TRIP = (
    "INSERT INTO bdm_trips (id, code, bdm_user_id, travel_date, return_date, from_place, to_place, purpose, mode, estimated_cost, "
    "approval_status, travel_status) VALUES (:id, :code, :owner, :travel, :ret, 'Hyderabad', 'Vijayawada', 'Visit', :mode, 100, "
    ":approval, :travel_status)"
)


def _trip(owner, **over):
    params = {"id": uuid.uuid4(), "code": f"TRV-{uuid.uuid4().hex[:6]}", "owner": owner, "travel": date(2026, 10, 10), "ret": date(2026, 10, 11),
              "mode": "train", "approval": "draft", "travel_status": "planned"}
    params.update(over)
    return params


def test_round_trip_keeps_users_and_creates_the_sequence(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, USERS)
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT nextval('bdm_trip_code_seq')")[0][0] >= 1
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT count(*) FROM pg_class WHERE relname = 'bdm_trip_code_seq'")[0][0] == 0
    command.upgrade(cfg, HEAD)
    assert _sql(url, USERS) == before


def test_checks_hold_and_downgrade_refuses_while_trips_exist(isolated_db):
    cfg, url, owner = isolated_db["cfg"], isolated_db["url"], isolated_db["owner"]
    command.upgrade(cfg, HEAD)
    for over, constraint in (
        ({"ret": date(2026, 10, 9)}, "ck_bdm_trips_dates"),
        ({"mode": "ship"}, "ck_bdm_trips_mode"),
        ({"approval": "draft", "travel_status": "completed"}, "ck_bdm_trips_status_pair"),
    ):
        with pytest.raises(Exception, match=constraint):
            _sql(url, TRIP, _trip(owner, **over))
    trip = _trip(owner)
    _sql(url, TRIP, trip)
    with pytest.raises(Exception, match="ck_bdm_trip_expenses_amount"):
        _sql(url, "INSERT INTO bdm_trip_expenses (id, trip_id, category, amount, expense_date, created_by_user_id) "
                  "VALUES (:id, :trip, 'food', 0, CURRENT_DATE, :owner)", {"id": uuid.uuid4(), "trip": trip["id"], "owner": owner})
    with pytest.raises(Exception, match="trips exist"):
        command.downgrade(cfg, BASE)
