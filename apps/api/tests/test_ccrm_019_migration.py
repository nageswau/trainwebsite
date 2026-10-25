"""ccrm-019 -- migration 0180_application_checklists (DEC-SCOPE-257): the chain, the constants it repeats, the CHECKs and the round trip
in a throwaway database (the ccrm-025 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

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

_spec = importlib.util.spec_from_file_location("_ccrm_019_migration_0180", VERSIONS / "0180_application_checklists.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0180_application_checklists"


def test_migration_chains_after_the_previous_head_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == "0179_application_fields"
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}  # later migrations chain after it


def test_the_migration_repeats_the_model_constants():
    from app.application_checklists import MARKS
    from app.document_checklists import CHECKLIST_GATE_MODES

    assert _migration.MARKS == MARKS and _migration.GATE_MODES == CHECKLIST_GATE_MODES


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm019_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, _migration.down_revision)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_tables_checks_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "application_checklists" not in {r[0] for r in _sql(url, "SELECT tablename FROM pg_tables")}
    command.upgrade(cfg, HEAD)
    assert {"mark", "from_template", "allowed_statuses"} <= set(_columns(url, "application_checklist_items"))
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
    _sql(url, "INSERT INTO overseas_applications (id, student_id, university_id, status, intake) VALUES (:id, :s, :u, 'offer', 'Fall 2027')", {"id": app_id, "s": student, "u": university})
    with pytest.raises(IntegrityError):  # gate mode outside the list
        _sql(url, "INSERT INTO application_checklists (application_id, gate_mode) VALUES (:a, 'maybe')", {"a": app_id})
    with pytest.raises(IntegrityError):  # a template without its version
        _sql(url, "INSERT INTO application_checklists (application_id, gate_mode, template_version) VALUES (:a, 'warn', 2)", {"a": app_id})
    _sql(url, "INSERT INTO application_checklists (application_id, gate_mode) VALUES (:a, 'warn')", {"a": app_id})
    with pytest.raises(IntegrityError):  # a mark outside the list
        _sql(
            url,
            "INSERT INTO application_checklist_items (id, application_id, position, document_type, required, from_template, allowed_statuses, mark) "
            "VALUES (:id, :a, 1, 'Passport', true, false, '[]', 'verified')",
            {"id": uuid.uuid4(), "a": app_id},
        )
    command.downgrade(cfg, _migration.down_revision)
    assert "application_checklist_items" not in {r[0] for r in _sql(url, "SELECT tablename FROM pg_tables")}
