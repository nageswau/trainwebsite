"""pob-023 -- migration 0298_template_governance (DEC-SCOPE-408 G1-G7). It checks the chain, that the checks are frozen copies, and that
`active` -> `status` is lossless both ways, with categories and v1 backfilled. It also checks that the downgrade refuses what 0120 cannot
hold. Everything runs in a throwaway database (the pob-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import REC_EMAIL_KINDS, REC_WHATSAPP_KINDS, RECRUITER_TEMPLATE_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pob_023_migration_0298", VERSIONS / "0298_template_governance.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0298_template_governance", "0297_crm_import_merge"
T = "recruiter_message_templates"


def test_migration_is_in_the_single_chain():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_checks_are_frozen_copies_of_the_models():
    assert _migration.TEMPLATE_CHECKS == RECRUITER_TEMPLATE_CHECKS
    assert (_migration.WHATSAPP_KINDS, _migration.EMAIL_KINDS) == (REC_WHATSAPP_KINDS, REC_EMAIL_KINDS)


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pob023_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip_keeps_every_template_and_its_state(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    archived, candidate_email = uuid.uuid4(), uuid.uuid4()
    _sql(url, f"INSERT INTO {T} (id, channel, kind, name, subject, body, active) VALUES "
              f"('{archived}', 'whatsapp', 'follow_up', 'Old WA', NULL, 'Hi', false), "
              f"('{candidate_email}', 'email', 'offer_follow_up', 'Old offer', 'S', 'Hi', true)")
    before = _sql(url, f"SELECT count(*) FROM {T}")[0][0]
    command.upgrade(cfg, HEAD)
    rows = {r[0]: r[1:] for r in _sql(url, f"SELECT id::text, status, category, version FROM {T}")}
    assert rows[str(archived)] == ("archived", "whatsapp", 1) and rows[str(candidate_email)] == ("approved", "candidate", 1)
    assert _sql(url, "SELECT count(*) FROM recruiter_template_versions")[0][0] == before == len(rows)
    command.upgrade(cfg, HEAD)  # idempotent at head
    command.downgrade(cfg, BASE)
    assert {r[0]: r[1] for r in _sql(url, f"SELECT id::text, active FROM {T}")}[str(archived)] is False
    assert _sql(url, f"SELECT count(*) FROM {T}")[0][0] == before


def test_the_downgrade_refuses_linkedin_and_personal_templates(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _sql(url, f"INSERT INTO {T} (id, channel, kind, category, name, body, status) VALUES ('{uuid.uuid4()}', 'linkedin', NULL, 'linkedin', 'LI', 'Hi', 'approved')")
    with pytest.raises(RuntimeError, match="cannot hold them"):
        command.downgrade(cfg, BASE)
