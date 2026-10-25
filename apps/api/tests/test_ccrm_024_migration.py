"""ccrm-024 -- migration 0182_offer_conditions (DEC-SCOPE-260): the chain, the constants it repeats, existing offer text becoming one
open student condition, the CHECKs and the round trip, in a throwaway database (the ccrm-025 pattern). Plain tests: alembic/env.py calls
asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_024_migration_0182", VERSIONS / "0182_offer_conditions.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0182_offer_conditions", "0181_lead_meetings"
TABLE = "application_offer_conditions"


def test_migration_chains_after_0181_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_migration_repeats_the_model_constants():
    from app.models import OFFER_CONDITION_OWNERS, OFFER_CONDITION_STATUSES

    assert _migration.OWNERS == OFFER_CONDITION_OWNERS and _migration.STATUSES == OFFER_CONDITION_STATUSES


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm024_migration_{uuid.uuid4().hex[:8]}"
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


def test_offer_text_becomes_one_open_student_condition_the_checks_hold_and_it_round_trips(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert TABLE not in _tables(url)
    student, university, country, app_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with_text, blank, without = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, profile, active, email_verified, locale) "
        "VALUES (:id, :email, 'x', 'Ccrm Student', 'overseas_student', 'overseas', '{}', true, true, 'en-GB')",
        {"id": student, "email": f"{student.hex[:8]}@example.com"},
    )
    _sql(
        url,
        "INSERT INTO countries (id, slug, name, overview, tuition, living_expenses, visa_process, work_opportunities, post_study_work, pr_opportunities, faq) "
        "VALUES (:id, :slug, 'Testland', '', '', '', '[]', '', '', '', '[]')",
        {"id": country, "slug": f"c-{country.hex[:8]}"},
    )
    _sql(
        url,
        "INSERT INTO universities (id, country_id, slug, name, name_key, city, overview, eligibility, requirements, deadlines, scholarships) "
        "VALUES (:id, :country, :slug, 'Ccrm University', 'ccrm university', 'Town', '', '', '[]', '[]', '[]')",
        {"id": university, "country": country, "slug": f"u-{university.hex[:8]}"},
    )
    _sql(url, "INSERT INTO overseas_applications (id, student_id, university_id, status, intake) VALUES (:id, :s, :u, 'offer', 'Fall 2027')", {"id": app_id, "s": student, "u": university})
    insert = "INSERT INTO application_offers (id, application_id, offer_type, issue_date, status, conditions) VALUES (:id, :a, 'conditional', '2026-01-01', :st, :c)"
    _sql(url, insert, {"id": with_text, "a": app_id, "st": "superseded", "c": "IELTS 6.5 overall"})
    _sql(url, insert, {"id": blank, "a": app_id, "st": "superseded", "c": "   "})
    _sql(url, insert, {"id": without, "a": app_id, "st": "active", "c": None})
    command.upgrade(cfg, HEAD)
    rows = [tuple(r) for r in _sql(url, f"SELECT offer_id, description, owner, status, created_by_id FROM {TABLE}")]
    assert rows == [(with_text, "IELTS 6.5 overall", "student", "open", None)]
    with pytest.raises(IntegrityError):
        _sql(url, f"UPDATE {TABLE} SET status = 'done'")
    with pytest.raises(IntegrityError):
        _sql(url, f"UPDATE {TABLE} SET owner = 'university'")
    command.downgrade(cfg, BASE)
    assert TABLE not in _tables(url)
    command.upgrade(cfg, HEAD)
