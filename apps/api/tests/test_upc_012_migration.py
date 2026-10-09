"""upc-012 -- migration 0123_university_comms (spec §2). The round trip and the downgrade refusal run in a throwaway database built from
scratch (the rec-024 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_upc_012_migration_0123", VERSIONS / "0123_university_comms.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0122_candidate_skills", "0123_university_comms"
TABLES = ("partnership_message_templates", "university_calls", "university_messages")


def test_migration_chains_after_its_base_and_there_is_a_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import (
        PARTNERSHIP_TEMPLATE_CHECKS,
        UNIVERSITY_CALL_CHECKS,
        UNIVERSITY_MESSAGE_CHECKS,
        PartnershipMessageTemplate,
        UniversityCall,
        UniversityMessage,
    )

    pairs = (
        (PartnershipMessageTemplate, PARTNERSHIP_TEMPLATE_CHECKS, _migration.TEMPLATE_CHECKS),
        (UniversityCall, UNIVERSITY_CALL_CHECKS, _migration.CALL_CHECKS),
        (UniversityMessage, UNIVERSITY_MESSAGE_CHECKS, _migration.MESSAGE_CHECKS),
    )
    for model, checks, migrated in pairs:
        assert checks == migrated
        for name, sql in checks.items():
            assert str(next(c for c in model.__table__.constraints if c.name == name).sqltext) == sql
    indexes = {i.name for m in (UniversityCall, UniversityMessage) for i in m.__table__.indexes}
    assert set(_migration.INDEXES) <= indexes
    # UC2: deleting a contact (upc-006 CT7) keeps the history on the university
    for model in (UniversityCall, UniversityMessage):
        assert next(iter(model.__table__.c.contact_id.foreign_keys)).ondelete == "SET NULL"


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"upc012_migration_{uuid.uuid4().hex[:8]}"
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


def _exists(url, table: str) -> bool:
    return _sql(url, f"SELECT to_regclass('{table}')") != [(None,)]


def test_round_trip_and_the_downgrade_refuses_while_history_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not any(_exists(url, t) for t in TABLES)
    command.upgrade(cfg, HEAD)
    assert all(_exists(url, t) for t in TABLES)
    with pytest.raises(Exception, match="ck_partnership_message_templates_subject"):  # a WhatsApp template has no subject
        _sql(url, "INSERT INTO partnership_message_templates (id, channel, name, subject, body) VALUES (:id, 'whatsapp', 'W', 'S', 'Hi')", {"id": uuid.uuid4()})
    _sql(url, "INSERT INTO partnership_message_templates (id, channel, name, body) VALUES (:id, 'whatsapp', 'W', 'Hi')", {"id": uuid.uuid4()})
    with pytest.raises(RuntimeError, match="0123_university_comms"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM partnership_message_templates")
    command.downgrade(cfg, BASE)
    assert not any(_exists(url, t) for t in TABLES)
