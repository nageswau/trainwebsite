"""ccrm-020 -- migration 0187_student_document_requests (DEC-SCOPE-265): the chain, the new columns, the owner CHECK (an agency record or a
student login, never both or neither), the indexes and the lossy round trip, in a throwaway database (the ccrm-024 pattern). Plain tests:
alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_020_migration_0187", VERSIONS / "0187_student_document_requests.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0187_student_document_requests", "0186_lead_loss_capture"
NEW_COLUMNS = {"student_user_id", "application_id", "checklist_item_id", "due_date"}


def test_migration_chains_after_0186_and_is_in_the_chain():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_model_declares_the_new_shape():
    from app.models import DocumentRequest

    table = DocumentRequest.__table__
    assert NEW_COLUMNS <= set(table.columns.keys()) and table.columns["agent_student_id"].nullable
    assert "ck_document_requests_owner" in {c.name for c in table.constraints}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm020_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'document_requests'")}


def _nullable(url) -> str:
    return _sql(url, "SELECT is_nullable FROM information_schema.columns WHERE table_name = 'document_requests' AND column_name = 'agent_student_id'")[0][0]


def test_columns_check_and_indexes_upgrade_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not NEW_COLUMNS & _columns(url) and _nullable(url) == "NO"
    user = _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile, created_at, updated_at) "
        "VALUES (gen_random_uuid(), :e, 'x', 'S', 'overseas_student', 'overseas', true, false, 'en', '{}', now(), now()) RETURNING id",
        {"e": f"{uuid.uuid4().hex[:8]}@example.local"},
    )[0][0]

    command.upgrade(cfg, HEAD)
    assert NEW_COLUMNS <= _columns(url) and _nullable(url) == "YES"
    indexes = {r[0] for r in _sql(url, "SELECT indexname FROM pg_indexes WHERE tablename = 'document_requests'")}
    assert {"ix_document_requests_student_user_status", "ix_document_requests_open_due"} <= indexes
    insert = "INSERT INTO document_requests (id, student_user_id, agent_student_id, document_type, status, due_date, created_at, updated_at) VALUES (gen_random_uuid(), :u, NULL, 'Passport', 'open', current_date, now(), now()) RETURNING id"
    request = _sql(url, insert, {"u": user})[0][0]
    with pytest.raises(IntegrityError):  # neither an agency record nor a student
        _sql(url, "INSERT INTO document_requests (id, document_type, status, created_at, updated_at) VALUES (gen_random_uuid(), 'CV', 'open', now(), now())")
    _sql(url, "INSERT INTO document_events (id, request_id, event, to_status, created_at) VALUES (gen_random_uuid(), :r, 'requested', 'open', now())", {"r": request})

    command.downgrade(cfg, BASE)  # lossy: a direct student's request and its history go
    assert not NEW_COLUMNS & _columns(url) and _nullable(url) == "NO"
    assert _sql(url, "SELECT count(*) FROM document_requests")[0][0] == 0
    assert _sql(url, "SELECT count(*) FROM document_events")[0][0] == 0
    command.upgrade(cfg, HEAD)
    assert NEW_COLUMNS <= _columns(url)
