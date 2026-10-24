"""ccrm-025 -- migration 0178_offer_decisions_deposits (DEC-SCOPE-255): the chain, the constants it repeats, existing offers becoming
`considering`, the CHECKs and the round trip, in a throwaway database (the ccrm-023 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from datetime import date

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import settings
from tests.test_ccrm_014_migration import _columns
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_025_migration_0178", VERSIONS / "0178_offer_decisions_deposits.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0178_offer_decisions_deposits", "0177_visa_lifecycle"


def test_migration_chains_after_0177_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}  # ccrm-013's 0179 chains after it


def test_the_migration_repeats_the_model_constants():
    from app.models import APPLICATION_OFFER_DECISIONS, DEPOSIT_RECORD_STATUSES

    assert _migration.DECISIONS == APPLICATION_OFFER_DECISIONS and _migration.DEPOSIT_STATUSES == DEPOSIT_RECORD_STATUSES


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm025_migration_{uuid.uuid4().hex[:8]}"
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


def test_existing_offers_become_considering_the_checks_hold_and_it_round_trips(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "decision" not in _columns(url, "application_offers")
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
    _sql(url, "INSERT INTO application_offers (id, application_id, offer_type, issue_date, status) VALUES (:id, :a, 'conditional', '2026-01-01', 'active')", {"id": uuid.uuid4(), "a": app_id})
    command.upgrade(cfg, HEAD)
    assert [tuple(r) for r in _sql(url, "SELECT decision, decision_date FROM application_offers")] == [("considering", None)]
    with pytest.raises(IntegrityError):  # a decided offer carries its date
        _sql(url, "UPDATE application_offers SET decision = 'accepted'")
    insert = (
        "INSERT INTO application_deposit_records (id, application_id, required, amount, currency, payment_status, paid_on, recorded_by_id, updated_by_id) "
        "VALUES (:id, :a, :req, :amt, :cur, :st, :paid, :u, :u)"
    )
    with pytest.raises(IntegrityError):  # paid without a date
        _sql(url, insert, {"id": uuid.uuid4(), "a": app_id, "req": True, "amt": 3000, "cur": "GBP", "st": "paid_to_university", "paid": None, "u": student})
    _sql(url, insert, {"id": uuid.uuid4(), "a": app_id, "req": True, "amt": 3000, "cur": "GBP", "st": "paid_to_university", "paid": date(2026, 2, 1), "u": student})
    command.downgrade(cfg, BASE)
    assert "decision" not in _columns(url, "application_offers")
    assert "application_deposit_records" not in {r[0] for r in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    command.upgrade(cfg, HEAD)
