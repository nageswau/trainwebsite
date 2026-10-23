"""ccrm-023 -- migration 0171_application_offers (DEC-SCOPE-245): chain after ccrm-015's 0170, the table, the widened offer-type CHECK,
the backfill (AC7) and the round trip, in a throwaway database (the ccrm-014 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from datetime import date

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_ccrm_014_migration import _columns
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_023_migration_0171", VERSIONS / "0171_application_offers.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0171_application_offers", "0170_application_outcomes"


def test_migration_chains_after_0170_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert script.get_heads() == [HEAD]


def test_the_migration_repeats_the_model_constants():
    from app.models import APPLICATION_OFFER_STATUSES, APPLICATION_OFFER_TYPES

    assert _migration.TYPES == APPLICATION_OFFER_TYPES and _migration.STATUSES == APPLICATION_OFFER_STATUSES


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm023_migration_{uuid.uuid4().hex[:8]}"
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


def test_backfill_one_active_row_per_recorded_offer_and_round_trip(isolated_db):  # AC7
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "application_offers" not in {r[0] for r in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
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
    with_offer, without = uuid.uuid4(), uuid.uuid4()
    for app_id, offer_type in ((with_offer, "conditional"), (without, None)):
        _sql(
            url,
            "INSERT INTO overseas_applications (id, student_id, university_id, status, intake, offer_type, offer_date, offer_deadline, offer_conditions) "
            "VALUES (:id, :s, :u, 'offer', 'Fall 2027', :ot, :od, :dl, :cond)",
            {
                "id": app_id,
                "s": student,
                "u": university,
                "ot": offer_type,
                "od": date(2026, 1, 1) if offer_type else None,
                "dl": date(2026, 2, 1) if offer_type else None,
                "cond": "IELTS" if offer_type else None,
            },
        )
    command.upgrade(cfg, HEAD)
    rows = _sql(url, "SELECT application_id, offer_type, issue_date, offer_deadline, conditions, status, recorded_by_id FROM application_offers")
    assert [tuple(r) for r in rows] == [(with_offer, "conditional", date(2026, 1, 1), date(2026, 2, 1), "IELTS", "active", None)]
    _sql(url, "UPDATE overseas_applications SET offer_type = 'pathway', offer_date = '2026-01-01' WHERE id = :id", {"id": without})  # widened CHECK
    _sql(url, "UPDATE overseas_applications SET offer_type = NULL, offer_date = NULL WHERE id = :id", {"id": without})
    command.downgrade(cfg, BASE)
    assert "offer_type" in _columns(url, "overseas_applications")
    assert "application_offers" not in {r[0] for r in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
