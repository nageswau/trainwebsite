"""ENH-001 -- Academic-Year foundation model (docs/delivery/ENHANCEMENT_BACKLOG.md,
docs/superpowers/specs/2026-09-18-enh-001-academic-year-design.md)."""

import importlib.util
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import AcademicYear, School, SchoolStudent, User

ADMIN_PASSWORD = "Sup3r-Secret-Pass!"


async def _create_admin_and_login(client, db_session) -> User:
    admin = User(email=f"enh001-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(ADMIN_PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.commit()
    response = await client.post("/api/v1/auth/login", json={"email": admin.email, "password": ADMIN_PASSWORD, "division": "overseas"})
    assert response.status_code == 200
    return admin


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
    student = SchoolStudent(school_id=school.id, student_code=f"ENH{uuid.uuid4().hex[:5].upper()}", full_name="Backfill Check", grade_or_class="Grade 9", created_by_user_id=creator.id)
    db_session.add(student)
    await db_session.commit()

    # A freshly-created row after the migration should still get a sane academic_year_id
    # default at the application layer in Task 5 -- this test only asserts the migration
    # itself produced at least one seed AcademicYear row to backfill onto.
    #
    # Found by actually re-running this file twice (finding 6, idempotency): other tests
    # below also drive AcademicYear rows to (and away from) status="active" with
    # differently-shaped labels, so on a second pass through this file against this same
    # persistent DB, `status == "active"` alone no longer uniquely identifies the
    # migration's own seed row -- it can just as easily pick up a leftover row from a
    # prior test. The seed row's label is always exactly "<4-digit year>-<2-digit year>"
    # (0030_academic_years.py's own `f"{start_year}-{str(start_year + 1)[-2:]}"`), and it's
    # inserted at most once (keyed on that exact label, see the migration's
    # `existing_seed` check), so matching the label shape -- not the status -- is what
    # stays stable across re-runs.
    all_years = (await db_session.scalars(select(AcademicYear))).all()
    seed_year = next((y for y in all_years if re.match(r"^\d{4}-\d{2}$", y.label)), None)
    assert seed_year is not None


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


@pytest.mark.asyncio
async def test_admin_creates_an_academic_year(client, db_session):
    await _create_admin_and_login(client, db_session)
    label = f"2030-31-{uuid.uuid4().hex[:4]}"
    response = await client.post("/api/v1/overseas-admin/academic-years", json={"label": label, "start_date": "2030-04-01", "end_date": "2031-03-31"})
    assert response.status_code == 201, response.text
    assert response.json()["label"] == label
    assert response.json()["status"] == "draft"


@pytest.mark.asyncio
async def test_duplicate_academic_year_label_is_rejected_with_409(client, db_session):
    await _create_admin_and_login(client, db_session)
    payload = {"label": f"2031-32-{uuid.uuid4().hex[:4]}", "start_date": "2031-04-01", "end_date": "2032-03-31"}
    first = await client.post("/api/v1/overseas-admin/academic-years", json=payload)
    assert first.status_code == 201
    second = await client.post("/api/v1/overseas-admin/academic-years", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_end_date_before_start_date_is_rejected(client, db_session):
    await _create_admin_and_login(client, db_session)
    response = await client.post("/api/v1/overseas-admin/academic-years", json={"label": f"2032-33-{uuid.uuid4().hex[:4]}", "start_date": "2032-04-01", "end_date": "2031-03-31"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_school_coordinator_cannot_create_an_academic_year(client, db_session):
    coordinator = User(email=f"enh001-coord-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(ADMIN_PASSWORD), full_name="Coordinator", role="school_coordinator", division="overseas", active=True, profile={"school_id": str(uuid.uuid4())})
    db_session.add(coordinator)
    await db_session.commit()
    await client.post("/api/v1/auth/login", json={"email": coordinator.email, "password": ADMIN_PASSWORD, "division": "overseas"})
    response = await client.post("/api/v1/overseas-admin/academic-years", json={"label": f"2033-34-{uuid.uuid4().hex[:4]}", "start_date": "2033-04-01", "end_date": "2034-03-31"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_status_transition_forward_succeeds_and_backward_is_conflict(client, db_session):
    await _create_admin_and_login(client, db_session)
    created = await client.post("/api/v1/overseas-admin/academic-years", json={"label": f"2034-35-{uuid.uuid4().hex[:4]}", "start_date": "2034-04-01", "end_date": "2035-03-31"})
    year_id = created.json()["id"]

    forward = await client.patch(f"/api/v1/overseas-admin/academic-years/{year_id}", json={"status": "active"})
    assert forward.status_code == 200
    assert forward.json()["status"] == "active"

    backward = await client.patch(f"/api/v1/overseas-admin/academic-years/{year_id}", json={"status": "draft"})
    assert backward.status_code == 409

    bad_value = await client.patch(f"/api/v1/overseas-admin/academic-years/{year_id}", json={"status": "banana"})
    assert bad_value.status_code == 422


@pytest.mark.asyncio
async def test_academic_year_malformed_start_date_returns_422_not_500(client, db_session):
    """Review finding fix: `date.fromisoformat(...)` only had `(KeyError, ValueError)`
    caught around it. A non-string `start_date` (e.g. JSON `null`) makes
    `date.fromisoformat` raise `TypeError`, which propagated uncaught into a 500 instead
    of the required 422 for malformed input."""
    await _create_admin_and_login(client, db_session)
    response = await client.post(
        "/api/v1/overseas-admin/academic-years",
        json={"label": f"2035-36-{uuid.uuid4().hex[:4]}", "start_date": None, "end_date": "2036-03-31"},
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_academic_year_non_string_end_date_returns_422_not_500(client, db_session):
    """Same finding, other field and shape: a non-date-shaped (int, not just null)
    `end_date` must also 422, not 500."""
    await _create_admin_and_login(client, db_session)
    response = await client.post(
        "/api/v1/overseas-admin/academic-years",
        json={"label": f"2036-37-{uuid.uuid4().hex[:4]}", "start_date": "2036-04-01", "end_date": 20370331},
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_list_academic_years_requires_admin(client, db_session):
    await _create_admin_and_login(client, db_session)
    response = await client.get("/api/v1/overseas-admin/academic-years")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    coordinator = User(
        email=f"enh001-coord-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password(ADMIN_PASSWORD),
        full_name="Coordinator",
        role="school_coordinator",
        division="overseas",
        active=True,
        profile={"school_id": str(uuid.uuid4())},
    )
    db_session.add(coordinator)
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": coordinator.email, "password": ADMIN_PASSWORD, "division": "overseas"},
    )
    assert login.status_code == 200
    forbidden = await client.get("/api/v1/overseas-admin/academic-years")
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_patch_academic_year_requires_admin(client, db_session):
    """Review finding fix: no existing test verified a non-admin gets 403 on the PATCH
    status-transition endpoint (mirrors `test_school_coordinator_cannot_create_an_academic_year`
    for the create endpoint)."""
    await _create_admin_and_login(client, db_session)
    created = await client.post(
        "/api/v1/overseas-admin/academic-years",
        json={"label": f"2037-38-{uuid.uuid4().hex[:4]}", "start_date": "2037-04-01", "end_date": "2038-03-31"},
    )
    assert created.status_code == 201, created.text
    year_id = created.json()["id"]

    coordinator = User(
        email=f"enh001-coord-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password(ADMIN_PASSWORD),
        full_name="Coordinator",
        role="school_coordinator",
        division="overseas",
        active=True,
        profile={"school_id": str(uuid.uuid4())},
    )
    db_session.add(coordinator)
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": coordinator.email, "password": ADMIN_PASSWORD, "division": "overseas"},
    )
    assert login.status_code == 200
    response = await client.patch(
        f"/api/v1/overseas-admin/academic-years/{year_id}",
        json={"status": "active"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_coordinator_reads_the_active_academic_year(client, db_session):
    admin = await _create_admin_and_login(client, db_session)
    unique = uuid.uuid4().hex[:8]

    # Deactivate any existing active years to isolate this test
    active_years = await db_session.execute(select(AcademicYear).where(AcademicYear.status == "active"))
    for year in active_years.scalars():
        # "archived" is not a valid AcademicYear status (draft/active/closed per
        # ACADEMIC_YEAR_STATUSES) -- writing it directly via the ORM would permanently
        # corrupt the migration's seed row that test_migration_backfills_existing_school_students
        # depends on finding with status == "active". "closed" is the real terminal status.
        year.status = "closed"
    await db_session.commit()

    created = await client.post("/api/v1/overseas-admin/academic-years", json={"label": f"enh001-read-{unique}", "start_date": "2035-04-01", "end_date": "2036-03-31"})
    assert created.status_code == 201, created.text
    year_id = created.json()["id"]
    patch_resp = await client.patch(f"/api/v1/overseas-admin/academic-years/{year_id}", json={"status": "active"})
    assert patch_resp.status_code == 200

    coordinator = User(email=f"enh001-read-{unique}@example.local", password_hash=hash_password(ADMIN_PASSWORD), full_name="Coordinator", role="school_coordinator", division="overseas", active=True, profile={"school_id": str(uuid.uuid4())})
    db_session.add(coordinator)
    await db_session.commit()
    await client.post("/api/v1/auth/login", json={"email": coordinator.email, "password": ADMIN_PASSWORD, "division": "overseas"})

    response = await client.get("/api/v1/school/academic-years/active")
    assert response.status_code == 200
    assert response.json()["label"] == f"enh001-read-{unique}"


@pytest.mark.asyncio
async def test_active_academic_year_is_out_of_scope_for_unrelated_roles(client, db_session):
    unrelated = User(email=f"enh001-unrelated-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(ADMIN_PASSWORD), full_name="IT Student", role="it_student", division="it", active=True)
    db_session.add(unrelated)
    await db_session.commit()
    await client.post("/api/v1/auth/login", json={"email": unrelated.email, "password": ADMIN_PASSWORD, "division": "it"})
    response = await client.get("/api/v1/school/academic-years/active")
    assert response.status_code == 403


async def _create_school_with_coordinator(client, db_session, *, suffix: str | None = None) -> dict:
    admin = await _create_admin_and_login(client, db_session)
    suffix = suffix or uuid.uuid4().hex[:8]
    response = await client.post(
        "/api/v1/overseas-admin/schools",
        json={"name": f"ENH-001 School {suffix}", "coordinator_full_name": "Coordinator", "coordinator_email": f"enh001-coord-{suffix}@example.local", "coordinator_password": ADMIN_PASSWORD},
    )
    assert response.status_code == 201
    data = response.json()
    await client.post("/api/v1/auth/login", json={"email": data["coordinator_email"], "password": ADMIN_PASSWORD, "division": "overseas"})
    return data


@pytest.mark.asyncio
async def test_create_student_accepts_a_valid_grade_level(client, db_session):
    await _create_school_with_coordinator(client, db_session)
    response = await client.post("/api/v1/school/students", json={"full_name": "Test Student", "grade_or_class": "Grade 9", "grade_level": 9})
    assert response.status_code == 201, response.text
    assert response.json()["grade_level"] == 9
    assert response.json()["grade_or_class"] == "Grade 9"  # zero data loss -- both present


@pytest.mark.asyncio
async def test_create_student_rejects_an_out_of_range_grade_level(client, db_session):
    await _create_school_with_coordinator(client, db_session)
    response = await client.post("/api/v1/school/students", json={"full_name": "Test Student", "grade_level": 13})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_student_rejects_a_boolean_grade_level(client, db_session):
    await _create_school_with_coordinator(client, db_session)
    response = await client.post("/api/v1/school/students", json={"full_name": "Test Student", "grade_level": True})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_student_ignores_a_client_supplied_academic_year_id(client, db_session):
    await _create_school_with_coordinator(client, db_session)
    bogus_year_id = str(uuid.uuid4())
    response = await client.post("/api/v1/school/students", json={"full_name": "Test Student", "academic_year_id": bogus_year_id})
    assert response.status_code == 201
    assert response.json()["academic_year_id"] != bogus_year_id


@pytest.mark.asyncio
async def test_update_student_can_set_grade_level(client, db_session):
    school = await _create_school_with_coordinator(client, db_session)
    created = await client.post("/api/v1/school/students", json={"full_name": "Test Student"})
    student_id = created.json()["id"]
    response = await client.patch(f"/api/v1/school/students/{student_id}", json={"grade_level": 7})
    assert response.status_code == 200
    assert response.json()["grade_level"] == 7


@pytest.mark.asyncio
async def test_bulk_upload_accepts_an_optional_grade_level_column(client, db_session):
    await _create_school_with_coordinator(client, db_session)
    csv_body = "full_name,date_of_birth,grade_or_class,grade_level\nBulk Student,,Grade 6,6\n"
    response = await client.post(
        "/api/v1/school/students/bulk-upload",
        files={"file": ("roster.csv", csv_body, "text/csv")},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201, response.text
    assert response.json()["accepted_count"] == 1

    students = await client.get("/api/v1/school/students")
    assert any(s["full_name"] == "Bulk Student" and s["grade_level"] == 6 for s in students.json())


@pytest.mark.asyncio
async def test_bulk_upload_rejects_an_out_of_range_grade_level_for_that_row_only(client, db_session):
    await _create_school_with_coordinator(client, db_session)
    csv_body = "full_name,date_of_birth,grade_or_class,grade_level\nBad Row,,Grade 6,99\nGood Row,,Grade 7,7\n"
    response = await client.post(
        "/api/v1/school/students/bulk-upload",
        files={"file": ("roster.csv", csv_body, "text/csv")},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201
    assert response.json()["accepted_count"] == 1
    assert response.json()["rejected_count"] == 1


@pytest.mark.asyncio
async def test_dashboard_grade_level_counts_use_the_stored_column_not_regex_parsing(client, db_session):
    """Task 7: `_school_dashboard_payload()` has no top-level `grade_level_counts` key --
    confirmed by reading schools.py:293/380-400 -- the per-grade counts are exposed as
    individual `school_crm_kpis` entries keyed `grade_8`..`grade_12` (see
    test_sch_reports.py's `kpis = {k["key"]: k for k in data["school_crm_kpis"]}` pattern).
    "Std IX" is a label the old `_grade_number()` regex (`\\b(?:grade|class)\\s*(8-12)\\b`)
    cannot parse at all -- it only matches "grade"/"class" prefixed or bare numbers -- so a
    student with only that label would be silently dropped from the count entirely (not
    even miscounted into a wrong grade) under the old regex path. Reading `grade_level`
    directly must count both students correctly."""
    school = await _create_school_with_coordinator(client, db_session)
    first = await client.post("/api/v1/school/students", json={"full_name": "A", "grade_or_class": "Std IX", "grade_level": 9})
    assert first.status_code == 201, first.text
    second = await client.post("/api/v1/school/students", json={"full_name": "B", "grade_or_class": "Grade 9", "grade_level": 9})
    assert second.status_code == 201, second.text

    report = await client.get("/api/v1/school/dashboard")
    assert report.status_code == 200, report.text
    kpis = {k["key"]: k for k in report.json()["school_crm_kpis"]}
    assert kpis["grade_9"]["value"] == 2
