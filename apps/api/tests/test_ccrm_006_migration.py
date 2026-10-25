"""ccrm-006 -- migration 0185_lead_loss_capture (DEC-SCOPE-263): the Duplicate stage in the status CHECK, the closure columns and CHECKs
on `enquiries` and the seeded `lead_lost_reasons` list. Round trip in a throwaway database built from scratch (the csc-001 pattern); a
downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_006_migration_0185", VERSIONS / "0185_lead_loss_capture.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0184_enrollment_confirmation", "0185_lead_loss_capture"
COLUMNS = {"duplicate_of_id", "lost_reason_id", "lost_to"}


def test_migration_chains_after_0184_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.lead_stages import STAGES
    from app.models import LEAD_CLOSURE_CHECKS, LEAD_STATUS_CHECK, Enquiry, LeadLostReason

    assert _migration.STAGES == STAGES and _migration.STATUS_CHECK == LEAD_STATUS_CHECK
    assert _migration.CLOSURE_CHECKS == LEAD_CLOSURE_CHECKS
    checks = {c.name: str(c.sqltext) for c in Enquiry.__table__.constraints if isinstance(c, sa.CheckConstraint)}
    assert checks["ck_enquiries_status"] == LEAD_STATUS_CHECK and set(LEAD_CLOSURE_CHECKS) <= set(checks)
    assert COLUMNS <= {c.name for c in Enquiry.__table__.columns}
    assert LeadLostReason.__tablename__ == "lead_lost_reasons"


@pytest.fixture
def isolated_db():
    """A fresh database at 0184_enrollment_confirmation."""
    cfg = _config()
    original = settings.database_url
    name = f"ccrm006_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url: str, table: str) -> set[str]:
    return {row[0] for row in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = :t", {"t": table})}


INSERT = (
    "INSERT INTO enquiries (id, division, name, email, subject, message, source, status, crm_sync_status, metadata_json, created_at, updated_at) "
    "VALUES (:id, 'it', 'Lead', 'l@example.com', 'S', '', 'website', :status, 'pending', '{}', now(), now())"
)


def test_round_trip_seeds_the_reasons_and_enforces_the_closure(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not COLUMNS & _columns(url, "enquiries") and not _columns(url, "lead_lost_reasons")
    with pytest.raises(IntegrityError):
        _sql(url, INSERT, {"id": str(uuid.uuid4()), "status": "duplicate"})
    command.upgrade(cfg, HEAD)
    assert COLUMNS <= _columns(url, "enquiries")
    names = [r[0] for r in _sql(url, "SELECT name FROM lead_lost_reasons ORDER BY sort_order")]
    assert names == list(_migration.SEED)
    survivor = str(uuid.uuid4())
    _sql(url, INSERT, {"id": survivor, "status": "contacted"})
    with pytest.raises(IntegrityError):  # a duplicate needs its survivor
        _sql(url, INSERT, {"id": str(uuid.uuid4()), "status": "duplicate"})
    dup = str(uuid.uuid4())
    _sql(url, INSERT.replace("metadata_json,", "metadata_json, duplicate_of_id,").replace("'{}',", "'{}', :dup,"), {"id": dup, "status": "duplicate", "dup": survivor})
    with pytest.raises(IntegrityError):  # a reason only on Lost / Not Interested
        _sql(url, "UPDATE enquiries SET lost_to = 'UK' WHERE id = :id", {"id": survivor})
    command.downgrade(cfg, BASE)  # the duplicate lead becomes Lost so the old CHECK holds
    assert _sql(url, "SELECT status FROM enquiries WHERE id = :id", {"id": dup})[0][0] == "lost"
    assert not COLUMNS & _columns(url, "enquiries")
