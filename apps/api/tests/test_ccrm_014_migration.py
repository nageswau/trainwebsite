"""ccrm-014 -- migration 0167_application_sub_status (DEC-SCOPE-240): chain, columns, the SS2 backfill and the round trip, in a throwaway
database (the csc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from datetime import date

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_014_migration_0167", VERSIONS / "0167_application_sub_status.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0166_application_codes", "0167_application_sub_status"


def test_migration_chains_after_0166_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_models_carry_the_columns():
    from app.models import ApplicationStatusHistory, OverseasApplication

    assert "sub_status" in OverseasApplication.__table__.columns
    assert {"from_sub_status", "to_sub_status"} <= set(ApplicationStatusHistory.__table__.columns.keys())


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm014_migration_{uuid.uuid4().hex[:8]}"
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


def test_backfill_only_where_certain_and_round_trip(isolated_db):  # SS2
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "sub_status" not in _columns(url, "overseas_applications")
    student, university = uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, profile, active, email_verified, locale) "
        "VALUES (:id, :email, 'x', 'Ccrm Student', 'overseas_student', 'overseas', '{}', true, true, 'en-GB')",
        {"id": student, "email": f"{student.hex[:8]}@example.com"},
    )
    country = uuid.uuid4()
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
    cases = {
        "enrolled": ("enrolled", None, None, "enrolled"),
        "conditional": ("offer", "conditional", date(2026, 1, 1), "conditional_offer"),
        "unconditional": ("offer", "unconditional", date(2026, 1, 1), "unconditional_offer"),
        "offer_no_type": ("offer", None, None, None),
        "submitted": ("university_selection", None, None, "submitted"),
        "not_submitted": ("university_selection", None, None, None),
        "enquiry": ("enquiry", None, None, None),
    }
    ids = {}
    for key, (status, offer_type, offer_date, _expected) in cases.items():
        ids[key] = uuid.uuid4()
        _sql(
            url,
            "INSERT INTO overseas_applications (id, student_id, university_id, status, intake, offer_type, offer_date, submitted_on) VALUES (:id, :s, :u, :status, 'Fall 2027', :ot, :od, :sub)",
            {"id": ids[key], "s": student, "u": university, "status": status, "ot": offer_type, "od": offer_date, "sub": date(2026, 1, 1) if key == "submitted" else None},
        )
    command.upgrade(cfg, HEAD)
    assert {"from_sub_status", "to_sub_status"} <= _columns(url, "application_status_history")
    got = dict(_sql(url, "SELECT id, sub_status FROM overseas_applications"))
    assert {key: got[ids[key]] for key in cases} == {key: expected[3] for key, expected in cases.items()}
    command.downgrade(cfg, BASE)
    assert "sub_status" not in _columns(url, "overseas_applications")
    assert "to_sub_status" not in _columns(url, "application_status_history")
