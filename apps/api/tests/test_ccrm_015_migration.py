"""ccrm-015 -- migration 0170_application_outcomes (DEC-SCOPE-244): merges main's two 0169 heads, adds the outcome column and the
event table, backfills withdrawn rows (O1) and round-trips, in a throwaway database (the ccrm-014 pattern)."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_015_migration_0170", VERSIONS / "0170_application_outcomes.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0169_lead_next_action", "0170_application_outcomes"


def test_migration_merges_both_0169_heads_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert set(_migration.down_revision) == {"0169_lead_next_action", "0169_overseas_student_notes"}
    script = ScriptDirectory.from_config(_config())
    assert script.get_heads() == [HEAD]


def test_models_carry_the_column_and_table():
    from app.models import ApplicationOutcome, OverseasApplication

    assert "outcome" in OverseasApplication.__table__.columns
    assert {"application_id", "outcome", "outcome_date", "reason", "requested_by", "review_date", "hold_owner_id"} <= set(ApplicationOutcome.__table__.columns.keys())


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm015_migration_{uuid.uuid4().hex[:8]}"
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
    return {row[0] for row in _sql(url, f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'")}


def test_backfill_withdrawn_check_and_round_trip(isolated_db):  # O1
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "outcome" not in _columns(url, "overseas_applications")
    student, university, country = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
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
    ids = {status: uuid.uuid4() for status in ("withdrawn", "offer")}
    for status, app_id in ids.items():
        _sql(
            url,
            "INSERT INTO overseas_applications (id, student_id, university_id, status, intake) VALUES (:id, :s, :u, :status, 'Fall 2027')",
            {"id": app_id, "s": student, "u": university, "status": status},
        )
    command.upgrade(cfg, HEAD)
    assert "application_outcomes" in {r[0] for r in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    got = dict(_sql(url, "SELECT id, outcome FROM overseas_applications"))
    assert got == {ids["withdrawn"]: "withdrawn", ids["offer"]: None}
    with pytest.raises(Exception, match="ck_overseas_applications_outcome"):
        _sql(url, "UPDATE overseas_applications SET outcome = 'waitlisted' WHERE id = :id", {"id": ids["offer"]})
    command.downgrade(cfg, BASE)
    assert "outcome" not in _columns(url, "overseas_applications")
    assert not _columns(url, "application_outcomes")
