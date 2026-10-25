"""ccrm-005 -- migration 0182_lead_data_fields (DEC-SCOPE-260): the lead's contact/consent/referral columns, the overseas study and
academic columns on `lead_qualifications` and the `lead_english_tests` table. Round trip in a throwaway database built from scratch (the
csc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from datetime import UTC, datetime

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_005_migration_0182", VERSIONS / "0182_lead_data_fields.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0181_lead_meetings", "0182_lead_data_fields"
LEAD_COLUMNS = {"contact_preference", "enquiry_date", "marketing_opt_in", "marketing_consent_at", "referral_name", "referral_contact"}
QUAL_COLUMNS = {"preferred_country_id", "study_mode", "preferred_campus", "academic_cgpa", "backlogs"}


def test_migration_chains_after_0181_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import CONTACT_PREFERENCES, ENGLISH_TEST_STATUSES, ENGLISH_TESTS, STUDY_MODES, Enquiry, LeadEnglishTest, LeadQualification

    assert _migration.CONTACT_PREFERENCES == CONTACT_PREFERENCES and _migration.STUDY_MODES == STUDY_MODES
    assert _migration.ENGLISH_TESTS == ENGLISH_TESTS and _migration.ENGLISH_TEST_STATUSES == ENGLISH_TEST_STATUSES
    assert LEAD_COLUMNS <= {c.name for c in Enquiry.__table__.columns}
    assert QUAL_COLUMNS <= {c.name for c in LeadQualification.__table__.columns}
    assert set(_migration.LEAD_CHECKS) <= {c.name for c in Enquiry.__table__.constraints}
    assert set(_migration.QUAL_CHECKS) <= {c.name for c in LeadQualification.__table__.constraints}
    assert LeadEnglishTest.__tablename__ == "lead_english_tests"


@pytest.mark.asyncio
async def test_columns_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    names = await conn.run_sync(lambda sync: {t: {c["name"] for c in inspect(sync).get_columns(t)} for t in ("enquiries", "lead_qualifications")})
    assert LEAD_COLUMNS <= names["enquiries"] and QUAL_COLUMNS <= names["lead_qualifications"]


@pytest.fixture
def isolated_db():
    """A fresh database at 0181_lead_meetings."""
    cfg = _config()
    original = settings.database_url
    name = f"ccrm005_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _columns(url: str, table: str) -> set[str]:
    return {row[0] for row in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = :t", {"t": table})}


INSERT = ("INSERT INTO enquiries (id, division, name, email, subject, message, source, status, crm_sync_status, metadata_json, created_at, updated_at) "
          "VALUES (:id, 'overseas', 'Lead', 'l@example.com', 'S', '', 'website', 'new', 'pending', '{}', :at, :at)")


def test_round_trip_backfills_the_enquiry_date_in_ist_and_checks_the_values(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not LEAD_COLUMNS & _columns(url, "enquiries") and not _columns(url, "lead_english_tests")
    old = uuid.uuid4()
    _sql(url, INSERT, {"id": old, "at": datetime(2026, 3, 1, 20, tzinfo=UTC)})  # 01:30 on 2 March in IST
    command.upgrade(cfg, HEAD)
    assert LEAD_COLUMNS <= _columns(url, "enquiries") and QUAL_COLUMNS <= _columns(url, "lead_qualifications")
    assert {"lead_id", "position", "test_type", "valid_until"} <= _columns(url, "lead_english_tests")
    assert str(_sql(url, "SELECT enquiry_date FROM enquiries WHERE id = :id", {"id": old})[0][0]) == "2026-03-02"
    fresh = uuid.uuid4()
    _sql(url, INSERT, {"id": fresh, "at": datetime(2026, 10, 25, 5, tzinfo=UTC)})
    assert _sql(url, "SELECT enquiry_date FROM enquiries WHERE id = :id", {"id": fresh})[0][0] is not None  # the server default
    with pytest.raises(Exception, match="ck_enquiries_contact_preference"):
        _sql(url, "UPDATE enquiries SET contact_preference = 'fax' WHERE id = :id", {"id": old})
    with pytest.raises(Exception, match="ck_enquiries_marketing_consent"):
        _sql(url, "UPDATE enquiries SET marketing_opt_in = true WHERE id = :id", {"id": old})
    _sql(url, "UPDATE enquiries SET marketing_opt_in = true, marketing_consent_at = now() WHERE id = :id", {"id": old})
    command.downgrade(cfg, BASE)
    assert not LEAD_COLUMNS & _columns(url, "enquiries") and not QUAL_COLUMNS & _columns(url, "lead_qualifications")
    assert not _columns(url, "lead_english_tests")
