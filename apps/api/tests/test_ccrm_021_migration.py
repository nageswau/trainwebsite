"""ccrm-021 -- migration 0174_document_status (DEC-SCOPE-249): the chain, the constants it repeats, the S1 data map, the reviewed_at
backfill, the CHECKs and the round trip, in a throwaway database (the ccrm-018 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_021_migration_0174", VERSIONS / "0174_document_status.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0174_document_status", "0173_checklist_templates"


def test_migration_chains_after_0173_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_migration_repeats_the_model_constants():
    from app.document_checklists import ITEM_STATUSES, LEGACY_STATUSES
    from app.models import DOCUMENT_EVENTS

    assert _migration.STATUSES == ITEM_STATUSES and _migration.LEGACY == LEGACY_STATUSES
    assert set(_migration.EVENTS) == set(DOCUMENT_EVENTS)


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm021_migration_{uuid.uuid4().hex[:8]}"
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
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'student_documents'")}


def test_data_map_backfill_checks_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "expiry_date" not in _columns(url)
    user = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile, created_at, updated_at) "
        "VALUES (:id, :email, 'x', 'S', 'overseas_student', 'overseas', true, false, 'en', '{}', now(), now())",
        {"id": user, "email": f"{user.hex[:8]}@example.local"},
    )
    docs = {status: uuid.uuid4() for status in ("pending", "verified", "rejected", "changes_required", "Looks fine")}
    for status, doc in docs.items():
        _sql(
            url,
            "INSERT INTO student_documents (id, student_id, document_type, file_url, verification_status, created_at, updated_at) VALUES (:id, :s, 'Passport', 'k', :status, now(), now())",
            {"id": doc, "s": user, "status": status},
        )
    _sql(url, "INSERT INTO document_events (id, document_id, event, created_at) VALUES (:id, :d, 'rejected', '2026-01-02')", {"id": uuid.uuid4(), "d": docs["rejected"]})

    command.upgrade(cfg, HEAD)
    stored = dict(_sql(url, "SELECT id, verification_status FROM student_documents"))
    assert {k: stored[v] for k, v in docs.items()} == {
        "pending": "pending",
        "verified": "verified",
        "rejected": "reupload_required",
        "changes_required": "incomplete",
        "Looks fine": "under_review",
    }
    reviewed = dict(_sql(url, "SELECT id, reviewed_at FROM student_documents"))
    assert reviewed[docs["rejected"]].date().isoformat() == "2026-01-02" and reviewed[docs["pending"]] is None
    assert {"expiry_date", "reviewed_at", "archived_at", "version_of_id"} <= _columns(url)
    with pytest.raises(sa.exc.IntegrityError):
        _sql(url, "UPDATE student_documents SET verification_status = 'rejected' WHERE id = :id", {"id": docs["pending"]})
    _sql(url, "INSERT INTO document_events (id, document_id, event, created_at) VALUES (:id, :d, 'expired', now())", {"id": uuid.uuid4(), "d": docs["verified"]})

    command.downgrade(cfg, BASE)
    stored = dict(_sql(url, "SELECT id, verification_status FROM student_documents"))
    assert (stored[docs["rejected"]], stored[docs["changes_required"]], stored[docs["Looks fine"]]) == ("rejected", "changes_required", "pending")
    assert "expiry_date" not in _columns(url)
    assert [r[0] for r in _sql(url, "SELECT event FROM document_events")] == ["rejected"]
