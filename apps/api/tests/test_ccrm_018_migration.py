"""ccrm-018 -- migration 0173_checklist_templates (DEC-SCOPE-248): the chain, the constants it repeats, the tables, the
one-active-template-per-scope index (NULLs equal, intake case-insensitive) and the round trip, in a throwaway database (the ccrm-023
pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_018_migration_0173", VERSIONS / "0173_checklist_templates.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0173_checklist_templates", "0171_application_offers"


def test_migration_chains_after_0171_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_migration_repeats_the_model_constants():
    from app.document_checklists import CHECKLIST_GATE_MODES, CHECKLIST_KINDS
    from app.models import COURSE_LEVELS

    assert _migration.KINDS == CHECKLIST_KINDS and _migration.GATE_MODES == CHECKLIST_GATE_MODES and _migration.LEVELS == COURSE_LEVELS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm018_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _tables(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


def test_tables_scope_index_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "document_checklist_templates" not in _tables(url)
    command.upgrade(cfg, HEAD)
    assert {"document_checklist_templates", "document_checklist_template_items"} <= _tables(url)
    country = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO countries (id, slug, name, overview, tuition, living_expenses, visa_process, work_opportunities, post_study_work, pr_opportunities, faq) "
        "VALUES (:id, :slug, 'Testland', '', '', '', '[]', '', '', '', '[]')",
        {"id": country, "slug": f"c-{country.hex[:8]}"},
    )
    insert = "INSERT INTO document_checklist_templates (id, name, kind, country_id, intake, gate_mode, active) VALUES (:id, 'T', 'admission', :c, :intake, 'block', :active)"
    _sql(url, insert, {"id": uuid.uuid4(), "c": country, "intake": None, "active": True})
    with pytest.raises(sa.exc.IntegrityError):  # NULL scope fields count as equal
        _sql(url, insert, {"id": uuid.uuid4(), "c": country, "intake": None, "active": True})
    _sql(url, insert, {"id": uuid.uuid4(), "c": country, "intake": None, "active": False})  # inactive rows are outside the index
    _sql(url, insert, {"id": uuid.uuid4(), "c": country, "intake": "Sep 2027", "active": True})
    with pytest.raises(sa.exc.IntegrityError):
        _sql(url, insert, {"id": uuid.uuid4(), "c": country, "intake": "SEP 2027", "active": True})
    with pytest.raises(sa.exc.IntegrityError):
        _sql(url, "INSERT INTO document_checklist_templates (id, name, kind, country_id, gate_mode) VALUES (:id, 'T', 'finance', :c, 'block')", {"id": uuid.uuid4(), "c": country})
    command.downgrade(cfg, BASE)
    assert "document_checklist_templates" not in _tables(url) and "document_checklist_template_items" not in _tables(url)
