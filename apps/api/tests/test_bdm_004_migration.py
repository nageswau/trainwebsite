"""bdm-004 -- migration 0072_bdm_pipeline (spec §5; AC10). Round trip and the downgrade refusal run in a throwaway database (the
bdm-003 pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
BASE, HEAD = "0071_bdm_activities", "0072_bdm_pipeline"
NEW_COLUMNS = {"pipeline_stage", "lost_at", "lost_reason"}


def _migration():
    spec = importlib.util.spec_from_file_location("_bdm_004_migration_0072", VERSIONS / f"{HEAD}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_chains_after_0071_and_is_the_single_head():
    migration = _migration()
    assert (migration.revision, migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_frozen_stage_lists_and_checks_equal_the_model():
    from app.bdm_stages import MANUAL_STAGES
    from app.models import BDM_PIPELINE_CHECKS, BdmOrganization

    migration = _migration()
    assert migration.MANUAL_STAGES == MANUAL_STAGES
    assert migration.CHECKS == BDM_PIPELINE_CHECKS
    model_checks = {c.name: str(c.sqltext) for c in BdmOrganization.__table__.constraints if isinstance(c, CheckConstraint)}
    assert BDM_PIPELINE_CHECKS.items() <= model_checks.items()
    table = BdmOrganization.__table__
    assert NEW_COLUMNS <= {c.name for c in table.columns}
    assert not table.c.pipeline_stage.nullable and table.c.pipeline_stage.server_default.arg == "prospect"
    assert table.c.lost_at.nullable and table.c.lost_reason.nullable
    assert "ix_bdm_organizations_type_stage" in {i.name for i in table.indexes}


def test_event_model_matches_the_migration():
    from app.models import BdmPipelineEvent

    table = BdmPipelineEvent.__table__
    assert {c.name for c in table.columns} == {
        "id", "organization_id", "actor_user_id", "kind", "from_stage", "to_stage", "note", "position", "created_at",
    }
    assert {fk.parent.name: fk.ondelete for fk in table.foreign_keys} == {"organization_id": "RESTRICT", "actor_user_id": "RESTRICT"}
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {"ck_bdm_pipeline_events_kind", "ck_bdm_pipeline_events_note", "ix_bdm_pipeline_events_org"} <= names


@pytest.mark.asyncio
async def test_columns_and_table_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    columns = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_columns("bdm_organizations")})
    tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
    assert NEW_COLUMNS <= columns and "bdm_pipeline_events" in tables


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
    """A fresh database at 0071_bdm_activities with one bdm user."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm004_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        user_id = uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'it', true, true, 'en-GB', '{}')",
            {"id": user_id, "email": f"bdm-{name}@example.local"},
        )
        yield {"cfg": cfg, "url": url, "user": user_id}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


INSERT = (
    "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, created_by_user_id{extra_cols}) "
    "VALUES (:id, :code, 'college', :bdm_type, 'A', 'a', 'K', 'k', :u, :u{extra_vals})"
)


def _insert(db, bdm_type: str, **values) -> uuid.UUID:
    org_id = uuid.uuid4()
    sql = INSERT.format(extra_cols="".join(f", {k}" for k in values), extra_vals="".join(f", :{k}" for k in values))
    _sql(db["url"], sql, {"id": org_id, "code": f"ORG-{uuid.uuid4().hex[:8]}", "bdm_type": bdm_type, "u": db["user"], **values})
    return org_id


def test_round_trip_backfills_prospect_and_enforces_the_checks(isolated_db):
    """0001 builds BASE from the current models, so go up, down to BASE (the migration drops the columns), insert a row, and up
    again: the default and the CHECKs below are 0072's own DDL."""
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    cols = {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'bdm_organizations'")}
    assert not (NEW_COLUMNS & cols)
    kept = _insert(isolated_db, "school")
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT pipeline_stage, lost_at, lost_reason FROM bdm_organizations WHERE id = :id", {"id": kept}) == [("prospect", None, None)]
    assert _sql(url, "SELECT count(*) FROM bdm_pipeline_events") == [(0,)]
    bad = [
        ("college", {"pipeline_stage": "signed"}, "ck_bdm_organizations_pipeline_stage"),  # a School stage
        ("agent", {"pipeline_stage": "master_login_created"}, "ck_bdm_organizations_pipeline_stage"),  # live: never stored
        ("college", {"pipeline_stage": "placement"}, "ck_bdm_organizations_pipeline_stage"),  # volume: never stored
        ("school", {"lost_reason": "No budget"}, "ck_bdm_organizations_lost"),  # a reason without lost_at
    ]
    for bdm_type, values, check in bad:
        with pytest.raises(Exception, match=check):
            _insert(isolated_db, bdm_type, **values)
    _insert(isolated_db, "college", pipeline_stage="college_activated")
    _insert(isolated_db, "agent", pipeline_stage="agreement_signed")
    with pytest.raises(Exception, match="ck_bdm_pipeline_events_note"):
        _sql(
            url,
            "INSERT INTO bdm_pipeline_events (id, organization_id, actor_user_id, kind, from_stage, to_stage) VALUES (:id, :o, :u, 'lost', 'prospect', 'prospect')",
            {"id": uuid.uuid4(), "o": kept, "u": isolated_db["user"]},
        )


def test_downgrade_refuses_while_pipeline_data_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    moved = _insert(isolated_db, "college", pipeline_stage="contacted")
    with pytest.raises(Exception, match="pipeline data exists"):
        command.downgrade(cfg, BASE)
    _sql(url, "UPDATE bdm_organizations SET pipeline_stage = 'prospect' WHERE id = :id", {"id": moved})
    _sql(
        url,
        "INSERT INTO bdm_pipeline_events (id, organization_id, actor_user_id, kind, from_stage, to_stage) VALUES (:id, :o, :u, 'move', 'prospect', 'contacted')",
        {"id": uuid.uuid4(), "o": moved, "u": isolated_db["user"]},
    )
    with pytest.raises(Exception, match="pipeline data exists"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM bdm_pipeline_events")
    command.downgrade(cfg, BASE)  # nothing recorded any more: allowed
