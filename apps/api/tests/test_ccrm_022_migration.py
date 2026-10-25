"""ccrm-022 -- migration 0184_document_sensitivity (DEC-SCOPE-262): the chain, the word lists it repeats, the SQL classing agreeing with
the app's rule, the backfill, the CHECKs and the round trip, in a throwaway database (the ccrm-024 pattern). Plain tests: alembic/env.py
calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import settings
from app.document_checklists import FINANCIAL_TYPES, IDENTITY_TYPES, SENSITIVITY_CLASSES, type_sensitivity
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_022_migration_0184", VERSIONS / "0184_document_sensitivity.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0184_document_sensitivity", "0183_offer_conditions"
SAMPLES = ("Passport", "QA passport copy", "National-ID", "Birth certificate", "Financial documents", "Other Bank statement", "Income tax return", "Transcripts", "Bankruptcy-free", "CV")


def test_migration_chains_after_0183_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_migration_repeats_the_app_word_lists():
    assert _migration.CLASSES == SENSITIVITY_CLASSES
    assert set(_migration.IDENTITY_TYPES) == IDENTITY_TYPES and set(_migration.FINANCIAL_TYPES) == FINANCIAL_TYPES


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm022_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url, table) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = :t", {"t": table})}


def test_existing_items_are_classed_like_the_app_the_checks_hold_and_it_round_trips(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    table = "document_checklist_template_items"
    assert "sensitivity" not in _columns(url, table)
    country, template = uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO countries (id, slug, name, overview, tuition, living_expenses, visa_process, work_opportunities, post_study_work, pr_opportunities, faq) "
        "VALUES (:id, :slug, 'Testland', '', '', '', '[]', '', '', '', '[]')",
        {"id": country, "slug": f"c-{country.hex[:8]}"},
    )
    _sql(url, "INSERT INTO document_checklist_templates (id, name, kind, country_id, gate_mode, version, active) VALUES (:id, 'T', 'admission', :c, 'warn', 1, true)", {"id": template, "c": country})
    for position, sample in enumerate(SAMPLES, start=1):
        document_type, _, label = sample.partition(" ") if sample.startswith("Other ") else (sample, "", "")
        _sql(
            url,
            f"INSERT INTO {table} (id, template_id, position, document_type, label, required, allowed_statuses) VALUES (:id, :t, :p, :d, :l, true, '[]')",
            {"id": uuid.uuid4(), "t": template, "p": position, "d": document_type, "l": label or None},
        )
    command.upgrade(cfg, HEAD)
    stored = {tuple(r) for r in _sql(url, f"SELECT trim(document_type || ' ' || coalesce(label, '')), sensitivity FROM {table}")}
    assert stored == {(s, type_sensitivity(s)) for s in SAMPLES}
    for checked in (table, "application_checklist_items"):
        assert "sensitivity" in _columns(url, checked)
    with pytest.raises(IntegrityError):
        _sql(url, f"UPDATE {table} SET sensitivity = 'secret'")
    command.downgrade(cfg, BASE)
    assert "sensitivity" not in _columns(url, table) and "sensitivity" not in _columns(url, "application_checklist_items")
    command.upgrade(cfg, HEAD)
