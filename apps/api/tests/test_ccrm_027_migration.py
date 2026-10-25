"""ccrm-027 -- migration 0181_enrollment_confirmation (DEC-SCOPE-259): the chain, the outcome values it repeats, the two columns, the
three outcome CHECKs taking the new values, and the round trip, in a throwaway database (the ccrm-025 pattern)."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import settings
from tests.test_ccrm_014_migration import _columns
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_027_migration_0181", VERSIONS / "0181_enrollment_confirmation.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0181_enrollment_confirmation", "0180_application_checklists"


def test_migration_chains_after_0180_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_migration_repeats_the_outcome_values():
    from app.application_outcome import CLEARED, OUTCOMES

    assert _migration.OUTCOMES == OUTCOMES and _migration.CLEARED == CLEARED


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm027_migration_{uuid.uuid4().hex[:8]}"
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


def test_the_columns_and_outcome_checks_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "enrollment_document_id" not in _columns(url, "overseas_applications")
    student, university, country, app_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
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
    _sql(url, "INSERT INTO overseas_applications (id, student_id, university_id, status, intake) VALUES (:id, :s, :u, 'enrolled', 'Fall 2027')", {"id": app_id, "s": student, "u": university})
    with pytest.raises(IntegrityError):  # before the upgrade the new outcome is refused
        _sql(url, "UPDATE overseas_applications SET outcome = 'non_arrival'")
    command.upgrade(cfg, HEAD)
    assert [tuple(r) for r in _sql(url, "SELECT pre_enrollment_checklist_complete, enrollment_document_id FROM overseas_applications")] == [(False, None)]
    _sql(url, "UPDATE overseas_applications SET outcome = 'non_arrival'")
    _sql(url, "UPDATE overseas_applications SET outcome = 'cancelled'")
    with pytest.raises(IntegrityError):
        _sql(url, "UPDATE overseas_applications SET outcome = 'lost'")
    _sql(url, "UPDATE overseas_applications SET outcome = NULL")
    command.downgrade(cfg, BASE)
    assert "enrollment_document_id" not in _columns(url, "overseas_applications")
    command.upgrade(cfg, HEAD)
