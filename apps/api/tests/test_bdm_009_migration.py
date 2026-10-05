"""bdm-009 -- migration 0071_bdm_activities (spec §4; AC10). Round trip and the downgrade refusal run in a throwaway database
(the bdm-001 pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
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
_spec = importlib.util.spec_from_file_location("_bdm_009_migration_0071", VERSIONS / "0071_bdm_activities.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0070_bdm_appointments", "0071_bdm_activities"
USERS = "SELECT id, email, role FROM users ORDER BY id"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0070_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())  # bdm-007's 0072 and bdm-004's 0073 follow; 0071 stays on the single chain
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import BdmActivity

    table = BdmActivity.__table__
    assert {c.name for c in table.columns} == {
        "id", "bdm_user_id", "organization_id", "contact_id", "contact_name", "channel", "direction", "occurred_at", "note",
        "created_at", "updated_at",
    }
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {
        "ck_bdm_activities_channel", "ck_bdm_activities_direction", "ck_bdm_activities_direction_channel",
        "ix_bdm_activities_bdm_user_id_occurred_at", "ix_bdm_activities_organization_id_occurred_at",
    } <= names
    fks = {fk.parent.name: fk.ondelete for fk in table.foreign_keys}
    assert fks == {"bdm_user_id": "RESTRICT", "organization_id": "RESTRICT", "contact_id": "SET NULL"}


@pytest.mark.asyncio
async def test_table_exists_in_the_shared_database(db_session):
    rows = (await db_session.execute(sa.text("SELECT relname FROM pg_class WHERE relname = 'bdm_activities'"))).all()
    assert rows == [("bdm_activities",)]


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
    """A fresh database at 0070 with one BDM user and one organization."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm009_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        owner, org = uuid.uuid4(), uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'Owner', 'bdm', 'it', true, true, 'en-GB', '{}')",
            {"id": owner, "email": f"owner-{name}@example.local"},
        )
        _sql(
            url,
            "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, "
            "created_by_user_id) VALUES (:id, :code, 'college', 'college', 'St Mary', 'st mary', 'Kochi', 'kochi', :owner, :owner)",
            {"id": org, "code": f"ORG-{uuid.uuid4().hex[:6]}", "owner": owner},
        )
        yield {"cfg": cfg, "url": url, "owner": owner, "org": org}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


ACTIVITY = (
    "INSERT INTO bdm_activities (id, bdm_user_id, organization_id, channel, direction, occurred_at) "
    "VALUES (:id, :owner, :org, :channel, :direction, now())"
)


def _activity(db, **over) -> dict:
    params = {"id": uuid.uuid4(), "owner": db["owner"], "org": db["org"], "channel": "call", "direction": "outbound"}
    params.update(over)
    return params


def test_round_trip_keeps_users(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, USERS)
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT count(*) FROM pg_class WHERE relname = 'bdm_activities'")[0][0] == 0
    command.upgrade(cfg, HEAD)
    assert _sql(url, USERS) == before


def test_checks_hold_and_downgrade_refuses_while_activities_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    for over, constraint in (
        ({"channel": "fax"}, "ck_bdm_activities_channel"),
        ({"direction": "sideways"}, "ck_bdm_activities_direction"),
        ({"channel": "call", "direction": None}, "ck_bdm_activities_direction_channel"),
        ({"channel": "visit", "direction": "outbound"}, "ck_bdm_activities_direction_channel"),
    ):
        with pytest.raises(Exception, match=constraint):
            _sql(url, ACTIVITY, _activity(isolated_db, **over))
    _sql(url, ACTIVITY, _activity(isolated_db, channel="visit", direction=None))
    with pytest.raises(Exception, match="activities exist"):
        command.downgrade(cfg, BASE)
