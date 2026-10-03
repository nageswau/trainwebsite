"""AGN-015 -- migration 0067_audit_entity_index (spec §6): one additive index, no row read or written."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

API_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("_agn_015_migration_0067", API_ROOT / "alembic" / "versions" / "0067_audit_entity_index.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_chains_after_0066_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == ("0067_audit_entity_index", "0066_bdm_organizations")
    # One head with 0067 in its history (the AGN-017/bdm-002 form), so a later migration does not have to edit this test.
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1
    assert "0067_audit_entity_index" in {revision.revision for revision in script.walk_revisions()}


def test_model_declares_the_index():
    from app.models import AuditLog

    index = {i.name: i for i in AuditLog.__table__.indexes}["ix_audit_logs_entity"]
    assert [c.name for c in index.columns] == ["entity_type", "entity_id", "created_at"]


@pytest.mark.asyncio
async def test_index_exists_in_the_shared_database(db_session):
    indexdef = await db_session.scalar(sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_audit_logs_entity'"))
    assert indexdef is not None and "(entity_type, entity_id, created_at)" in indexdef
