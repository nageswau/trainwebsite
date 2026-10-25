"""ccrm-016 -- migration 0172_status_history_reason (DEC-SCOPE-247, H1): chain after ccrm-023's 0171, the two columns, the backfill from
same-transaction outcome events and AGN-008 withdrawals, and the round trip, in a throwaway database (the ccrm-014 pattern)."""

import importlib.util
import uuid
from datetime import UTC, datetime

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.core.config import settings
from tests.test_ccrm_014_migration import _columns
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_016_migration_0172", VERSIONS / "0172_status_history_reason.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0172_status_history_reason", "0171_application_offers"


def test_migration_chains_after_0171_and_stays_in_the_single_line():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}  # ccrm-018 0173 follows


def test_the_migration_repeats_the_outcome_values():
    from app.application_outcome import CLEARED, OUTCOMES

    assert _migration.OUTCOMES == (*OUTCOMES[:6], CLEARED)  # ccrm-015's six; 0181 (ccrm-027) adds the rest


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm016_migration_{uuid.uuid4().hex[:8]}"
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


def test_backfill_from_outcome_events_and_withdrawals_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "reason" not in _columns(url, "application_status_history")
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
    _sql(url, "INSERT INTO overseas_applications (id, student_id, university_id, status, intake) VALUES (:id, :s, :u, 'withdrawn', 'Fall 2027')", {"id": app_id, "s": student, "u": university})
    rows = {  # id: (from, to, notes, created_at)
        "plain": ("enquiry", "university_selection", "Moved on", datetime(2026, 1, 1, 10, tzinfo=UTC)),
        "hold": ("university_selection", "university_selection", "Outcome: On hold -- Awaiting funds", datetime(2026, 1, 2, 10, tzinfo=UTC)),
        "resume": ("university_selection", "university_selection", "Resumed (On hold) -- Funds arrived", datetime(2026, 1, 3, 10, tzinfo=UTC)),
        "withdraw": ("university_selection", "withdrawn", "Student chose another country", datetime(2026, 1, 4, 10, tzinfo=UTC)),
    }
    ids = {key: uuid.uuid4() for key in rows}
    for key, (from_status, to_status, notes, at) in rows.items():
        _sql(
            url,
            "INSERT INTO application_status_history (id, application_id, from_status, to_status, notes, created_at, updated_at) VALUES (:id, :a, :f, :t, :n, :at, :at)",
            {"id": ids[key], "a": app_id, "f": from_status, "t": to_status, "n": notes, "at": at},
        )
    for outcome, reason, at in (("on_hold", "Awaiting funds", rows["hold"][3]), ("cleared", "Funds arrived", rows["resume"][3])):
        _sql(
            url,
            "INSERT INTO application_outcomes (id, application_id, outcome, outcome_date, reason, created_by_id, created_at, updated_at) VALUES (:id, :a, :o, '2026-01-01', :r, :s, :at, :at)",
            {"id": uuid.uuid4(), "a": app_id, "o": outcome, "r": reason, "s": student, "at": at},
        )
    command.upgrade(cfg, HEAD)
    found = {r[0]: (r[1], r[2]) for r in _sql(url, "SELECT id, outcome, reason FROM application_status_history")}
    assert found == {
        ids["plain"]: (None, None),
        ids["hold"]: ("on_hold", "Awaiting funds"),
        ids["resume"]: ("cleared", "Funds arrived"),
        ids["withdraw"]: ("withdrawn", "Student chose another country"),
    }
    with pytest.raises(DBAPIError):  # the CHECK
        _sql(url, "UPDATE application_status_history SET outcome = 'waitlisted' WHERE id = :id", {"id": ids["plain"]})
    command.downgrade(cfg, BASE)
    assert {"outcome", "reason"}.isdisjoint(_columns(url, "application_status_history"))
