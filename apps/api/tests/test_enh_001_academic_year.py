"""ENH-001 -- Academic-Year foundation model (docs/delivery/ENHANCEMENT_BACKLOG.md,
docs/superpowers/specs/2026-09-18-enh-001-academic-year-design.md)."""

import importlib.util
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import AcademicYear, School, SchoolStudent


def test_academic_year_model_has_expected_columns():
    columns = AcademicYear.__table__.columns
    assert "label" in columns
    assert columns["label"].unique is True
    assert "start_date" in columns
    assert "end_date" in columns
    assert columns["status"].default.arg == "active"


def test_school_student_has_academic_year_and_grade_level_columns():
    columns = SchoolStudent.__table__.columns
    assert columns["academic_year_id"].nullable is True
    assert columns["grade_level"].nullable is True
    # grade_or_class must be untouched -- zero data loss per the spec.
    assert "grade_or_class" in columns


# Import the migration's actual `_derive_grade_level` by file path, rather than
# duplicating it here, so this test exercises the real migration code and can't drift
# from it. `importlib.import_module` can't resolve "0030_academic_years" directly -- a
# module path component starting with a digit isn't a valid Python identifier there --
# so `spec_from_file_location` loads it by file path instead.
_migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0030_academic_years.py"
_spec = importlib.util.spec_from_file_location("_enh_001_migration_0030", _migration_path)
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)
_derive_grade_level = _migration._derive_grade_level


@pytest.mark.parametrize(
    "label,expected",
    [
        ("Grade 9", 9), ("Class 9", 9), ("Grade 10-A", 10), ("grade 8", 8),
        ("Nonsense", None), (None, None), ("", None), ("Grade 13", None),
    ],
)
def test_grade_level_backfill_parser(label, expected):
    assert _derive_grade_level(label) == expected


@pytest.mark.asyncio
async def test_migration_backfills_existing_school_students(db_session):
    # This test assumes `alembic upgrade head` has already been run against the test
    # database (conftest.py disables schema autocreate) -- it verifies the *outcome* of
    # the migration that already ran, not a live revision-to-revision replay. Create a
    # real User first (School.created_by_user_id is a NOT NULL FK) rather than reaching
    # for some other test's leftover row.
    from app.core.security import hash_password
    from app.models import User

    creator = User(email=f"enh001-creator-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"), full_name="Migration Check Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(creator)
    await db_session.flush()
    school = School(name="ENH-001 Migration Check School", created_by_user_id=creator.id)
    db_session.add(school)
    await db_session.flush()
    student = SchoolStudent(school_id=school.id, student_code="ENH0001Z", full_name="Backfill Check", grade_or_class="Grade 9", created_by_user_id=creator.id)
    db_session.add(student)
    await db_session.commit()

    # A freshly-created row after the migration should still get a sane academic_year_id
    # default at the application layer in Task 5 -- this test only asserts the migration
    # itself produced at least one seed AcademicYear row to backfill onto.
    seed_year = await db_session.scalar(select(AcademicYear).where(AcademicYear.status == "active"))
    assert seed_year is not None
    assert re.match(r"^\d{4}-\d{2}$", seed_year.label)


def test_migration_0030_backfills_preexisting_school_student_via_downgrade_upgrade_cycle():
    """Review finding fix: `test_migration_backfills_existing_school_students` above only
    ever creates its School/SchoolStudent row *after* 0030 has already run against the
    test DB, so the migration's `UPDATE ... WHERE academic_year_id IS NULL` backfill loop
    never actually touches a pre-existing row in CI (the test DB is empty before
    migrations run). This test reproduces the real deploy scenario instead: downgrade to
    the revision just before 0030, insert a row against that pre-migration schema via raw
    SQL (the ORM models describe the *current* schema and no longer match a downgraded
    one), upgrade back to head, then assert the backfill actually populated
    `academic_year_id`/`grade_level` on that specific pre-existing row.

    Uses the same downgrade/reseed/upgrade technique the prior implementer used manually
    for this migration's Step 5 verification (see task-2-report.md), encoded here as an
    automated test instead of a one-off manual check.

    Deliberately a plain (non-async) test: `alembic/env.py`'s `run_migrations_online()`
    calls `asyncio.run(...)` internally, which raises if invoked from inside an already-
    running event loop -- exactly what a `@pytest.mark.asyncio` test body would be. Kept
    synchronous, this test never has a loop running when `command.downgrade`/`upgrade`
    make that call, so no conflict. The raw-SQL insert/select steps below each use their
    own short-lived engine + `asyncio.run()` for the same reason: sequential, not nested.
    """
    import asyncio
    import uuid as uuid_mod
    from pathlib import Path

    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import settings

    api_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(api_root / "alembic.ini"))
    # Set explicitly rather than relying on alembic.ini's relative "alembic" resolving
    # against whatever the pytest process's cwd happens to be.
    cfg.set_main_option("script_location", str(api_root / "alembic"))

    creator_id = uuid_mod.uuid4()
    school_id = uuid_mod.uuid4()
    student_id = uuid_mod.uuid4()
    unique = uuid_mod.uuid4().hex[:8]

    def _exec(sql, params=None):
        async def _inner():
            engine = create_async_engine(settings.database_url)
            try:
                async with engine.begin() as conn:
                    await conn.execute(sa.text(sql), params or {})
            finally:
                await engine.dispose()

        asyncio.run(_inner())

    def _query(sql, params=None):
        async def _inner():
            engine = create_async_engine(settings.database_url)
            try:
                async with engine.begin() as conn:
                    result = await conn.execute(sa.text(sql), params or {})
                    return result.fetchall()
            finally:
                await engine.dispose()

        return asyncio.run(_inner())

    try:
        # 1. Downgrade to the revision just before 0030: academic_years / academic_year_id
        #    / grade_level don't exist at this point -- the real pre-migration shape.
        command.downgrade(cfg, "0029_partnership_gaps")

        # 2. Insert School/SchoolStudent rows via raw SQL against that pre-migration
        #    schema (a real NOT NULL column list for `users`/`schools`/`school_students`
        #    at this revision -- the ORM models describe the post-migration schema and
        #    would reference columns/relations that don't exist at 0029).
        _exec(
            "INSERT INTO users (id, email, password_hash, full_name, role, division, "
            "phone, active, email_verified, locale, profile, student_code) "
            "VALUES (:id, :email, 'x', :full_name, 'overseas_admin', 'overseas', "
            "NULL, true, true, 'en-GB', '{}', NULL)",
            {"id": creator_id, "email": f"enh001-downgrade-{unique}@example.local", "full_name": "Downgrade Cycle Admin"},
        )
        _exec(
            "INSERT INTO schools (id, name, created_by_user_id) VALUES (:id, :name, :creator)",
            {"id": school_id, "name": "ENH-001 Downgrade Cycle School", "creator": creator_id},
        )
        _exec(
            "INSERT INTO school_students (id, school_id, student_code, full_name, grade_or_class, created_by_user_id) "
            "VALUES (:id, :school_id, :code, :full_name, :goc, :creator)",
            {
                "id": student_id,
                "school_id": school_id,
                "code": f"E{unique[:7]}".upper(),
                "full_name": "Downgrade Cycle Student",
                "goc": "Grade 9",
                "creator": creator_id,
            },
        )

        # 3. Re-apply 0030 (back to head) -- this must backfill the row that already
        #    existed *before* this upgrade ran: the exact gap the review finding
        #    identified (the other DB-backed test only ever inserts *after* the upgrade).
        command.upgrade(cfg, "head")

        # 4. Assert the backfill actually touched this specific pre-existing row.
        rows = _query(
            "SELECT academic_year_id, grade_level FROM school_students WHERE id = :id",
            {"id": student_id},
        )
        assert rows, "expected the pre-existing school_students row to still exist after upgrade"
        academic_year_id, grade_level = rows[0]
        assert academic_year_id is not None
        assert grade_level == 9
    finally:
        # 5. Always leave the test database at head, even if an assertion above failed,
        #    so later tests in this session see the expected (post-migration) schema.
        #    `alembic upgrade head` is idempotent by the migration's own design (guarded
        #    by inspector checks in 0030), so calling it again here -- even if already at
        #    head -- is safe.
        command.upgrade(cfg, "head")
