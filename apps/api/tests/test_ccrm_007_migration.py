"""ccrm-007 -- migration 0174_student_profiles (DEC-SCOPE-249): the chain, the constants it repeats, the three tables, the one-time copy
of the old `users.profile` keys (P4: copied, never deleted) and the round trip, in a throwaway database (the ccrm-018 pattern). Plain
tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import json
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_007_migration_0174", VERSIONS / "0174_student_profiles.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0174_student_profiles", "0173_checklist_templates"
TABLES = {"overseas_student_profiles", "overseas_student_qualifications", "overseas_student_english_tests"}


def test_migration_chains_after_0173_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_migration_repeats_the_model_constants():
    from app.models import COUNSELING_CURRENCIES, COURSE_LEVELS, ENGLISH_TEST_STATUSES, ENGLISH_TESTS, QUALIFICATION_LEVELS, SCORE_TYPES, STUDY_MODES

    assert _migration.LEVELS == COURSE_LEVELS and _migration.CURRENCIES == COUNSELING_CURRENCIES and _migration.STUDY_MODES == STUDY_MODES
    assert _migration.QUALIFICATION_LEVELS == QUALIFICATION_LEVELS and _migration.SCORE_TYPES == SCORE_TYPES
    assert _migration.TEST_TYPES == ENGLISH_TESTS and _migration.TEST_STATUSES == ENGLISH_TEST_STATUSES


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm007_migration_{uuid.uuid4().hex[:8]}"
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


def _user(url, role: str, profile: dict) -> uuid.UUID:
    uid = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :email, 'x', 'Mig User', :role, 'overseas', true, true, 'en-GB', CAST(:profile AS JSON))",
        {"id": uid, "email": f"{uid.hex[:10]}@example.local", "role": role, "profile": json.dumps(profile)},
    )
    return uid


def test_old_profile_keys_are_copied_once_and_kept(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not TABLES & _tables(url)
    country = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO countries (id, slug, name, overview, tuition, living_expenses, visa_process, work_opportunities, post_study_work, pr_opportunities, faq) "
        "VALUES (:id, :slug, 'Testland', '', '', '', '[]', '', '', '', '[]')",
        {"id": country, "slug": f"c-{country.hex[:8]}"},
    )
    legacy = {"education": "B.Tech", "preferred_countries": ["testland", "Nowhere"], "preferred_intake": "September 2027", "english_test": "IELTS planned"}
    student = _user(url, "overseas_student", legacy)
    bare = _user(url, "overseas_student", {"registration_source": "counselor_walk_in"})
    it_student = _user(url, "it_student", {"education": "B.Sc"})

    command.upgrade(cfg, HEAD)
    assert TABLES <= _tables(url)
    rows = _sql(url, "SELECT student_user_id, preferred_country_ids, preferred_intake FROM overseas_student_profiles")
    assert [(r[0], r[1], r[2]) for r in rows] == [(student, [str(country)], "September 2027")]  # unmatched names dropped
    assert _sql(url, "SELECT level, qualification_name, position FROM overseas_student_qualifications WHERE student_user_id = :s", {"s": student}) == [("other", "B.Tech", 0)]
    assert _sql(url, "SELECT test_type, status, remarks FROM overseas_student_english_tests WHERE student_user_id = :s", {"s": student}) == [("IELTS", None, "IELTS planned")]
    assert not _sql(url, "SELECT 1 FROM overseas_student_profiles WHERE student_user_id IN (:a, :b)", {"a": bare, "b": it_student})
    kept = _sql(url, "SELECT profile FROM users WHERE id = :s", {"s": student})[0][0]
    assert kept == legacy  # P4: never deleted

    command.downgrade(cfg, BASE)
    assert not TABLES & _tables(url)
    command.upgrade(cfg, HEAD)  # the copy runs again on a fresh upgrade, once per student
    assert len(_sql(url, "SELECT 1 FROM overseas_student_profiles")) == 1
