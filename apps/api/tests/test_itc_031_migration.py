"""itc-031 -- migration 0240_enrollment_lifecycle (DEC-SCOPE-358): the lifecycle history table, the enrolment override columns and the
enrolment status CHECK. Round trip in a throwaway database built from scratch (the upc-001 pattern). Plain tests: alembic/env.py calls
asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import settings
from app.models import ENROLLMENT_STATUSES, Enrollment, EnrollmentLifecycleHistory
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_itc_031_migration_0240", VERSIONS / "0240_enrollment_lifecycle.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0240_enrollment_lifecycle"
BASE = _migration.down_revision
TABLE = "SELECT to_regclass('enrollment_lifecycle_history') IS NOT NULL"
COLUMNS = "SELECT column_name FROM information_schema.columns WHERE table_name = 'enrollments' AND column_name LIKE 'lifecycle_%' ORDER BY 1"
CHECKS = "SELECT conname, convalidated FROM pg_constraint WHERE conname IN ('ck_enrollments_status', 'ck_enrollments_lifecycle_override') ORDER BY 1"


def test_migration_is_in_the_single_head_chain():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    assert _migration.STATUSES == ENROLLMENT_STATUSES
    columns = Enrollment.__table__.columns
    assert columns["lifecycle_override"].nullable and columns["lifecycle_override_reason"].nullable
    history = EnrollmentLifecycleHistory.__table__.columns
    assert history["from_stage"].nullable and history["actor_user_id"].nullable and not history["to_stage"].nullable


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"itc031_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001 builds from the current models, so step back to the base to start without the new objects
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _seed_enrollment(url: str, status: str) -> uuid.UUID:
    user, program, batch, enrollment = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
              "VALUES (:id, :email, 'x', 'Student', 'it_student', 'it', true, true, 'en-GB', '{}')", {"id": user, "email": f"s-{user.hex[:8]}@example.local"}, autocommit=True)  # fmt: skip
    _sql(url, "INSERT INTO programs (id, slug, category, title, summary, duration, eligibility, fees, certification, curriculum, syllabus_modules, placement_assistance, trainer_name, active) "
              "VALUES (:id, :slug, 'IT', 'Python', '', '8 weeks', '', 1000, '', '[]', '[]', '', 'T', true)", {"id": program, "slug": f"p-{program.hex[:8]}"}, autocommit=True)  # fmt: skip
    _sql(url, "INSERT INTO batches (id, program_id, name, start_date, end_date, schedule, capacity, enrollment_open, status, mode, timezone) "
              "VALUES (:id, :program, 'B', current_date, current_date + 30, 'Mon', 20, true, 'active', 'Online', 'Asia/Kolkata')", {"id": batch, "program": program}, autocommit=True)  # fmt: skip
    _sql(url, "INSERT INTO enrollments (id, student_id, batch_id, enrollment_code, enrolled_on, slot_locked, status, progress_percent) "
              "VALUES (:id, :student, :batch, :code, current_date, true, :status, 0)",
         {"id": enrollment, "student": user, "batch": batch, "code": f"E-{enrollment.hex[:8]}", "status": status}, autocommit=True)  # fmt: skip
    return enrollment


def test_upgrade_adds_the_table_columns_and_checks_and_keeps_data(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    kept = _seed_enrollment(url, "active")
    assert _sql(url, TABLE) == [(False,)] and _sql(url, COLUMNS) == [] and _sql(url, CHECKS) == []

    command.upgrade(cfg, HEAD)
    assert _sql(url, TABLE) == [(True,)]
    assert _sql(url, COLUMNS) == [("lifecycle_override",), ("lifecycle_override_reason",)]
    assert _sql(url, CHECKS) == [("ck_enrollments_lifecycle_override", True), ("ck_enrollments_status", True)]
    assert _sql(url, "SELECT status, lifecycle_override FROM enrollments WHERE id = :id", {"id": kept}) == [("active", None)]
    with pytest.raises(IntegrityError):  # the status is no longer free text
        _sql(url, "UPDATE enrollments SET status = 'whatever' WHERE id = :id", {"id": kept}, autocommit=True)
    with pytest.raises(IntegrityError):
        _sql(url, "UPDATE enrollments SET lifecycle_override = 'placed' WHERE id = :id", {"id": kept}, autocommit=True)

    command.downgrade(cfg, BASE)
    assert _sql(url, TABLE) == [(False,)] and _sql(url, COLUMNS) == [] and _sql(url, CHECKS) == []
    assert _sql(url, "SELECT status FROM enrollments WHERE id = :id", {"id": kept}) == [("active",)]


def test_a_legacy_status_is_kept_and_leaves_the_check_not_validated(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    legacy = _seed_enrollment(url, "on_hold")

    command.upgrade(cfg, HEAD)
    assert _sql(url, CHECKS) == [("ck_enrollments_lifecycle_override", True), ("ck_enrollments_status", False)]
    assert _sql(url, "SELECT status FROM enrollments WHERE id = :id", {"id": legacy}) == [("on_hold",)]  # never rewritten
    with pytest.raises(IntegrityError):  # new writes are still checked
        _sql(url, "UPDATE enrollments SET status = 'whatever' WHERE id = :id", {"id": legacy}, autocommit=True)
