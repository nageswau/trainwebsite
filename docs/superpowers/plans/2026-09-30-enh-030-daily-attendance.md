# ENH-030 Daily Class Attendance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A School teacher marks their whole assigned class's attendance for a day in one Save; the record shows on the Parent dashboard card and the Student 360° Attendance tab.

**Architecture:** One new table (`school_attendance_records`, migration `0046`) and one new router (`apps/api/app/api/school_attendance.py`: `GET`/`PUT /school/attendance`) that reuse the existing School scope helpers (`_own_school_id`, `_scoped_students_query`, `require_school_entitlement`) and the ENH-011 typed-upsert pattern. Reads are one additive `daily_attendance` key on the existing `_overview_payload`, which the Parent card and the 360 view already consume. Frontend: one new teacher page + one client roster component; two additive read renderings.

**Tech Stack:** FastAPI, Pydantic v2, async SQLAlchemy 2 (PostgreSQL `INSERT … ON CONFLICT`), Alembic, pytest; Next.js 15 (App Router, server pages + client components), React 19, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-30-enh-030-daily-attendance-design.md` (decisions D1–D6, choices C1–C4, AC01–AC13). Decision: `DEC-SCOPE-038`.

## Global Constraints

- No new dependency (backend or frontend).
- Statuses exactly `present`, `absent`, `late`, `excused`; a missing row means "not marked", never absent.
- One record per `(school_student_id, session_date)`; constraint name `uq_school_attendance_student_date`; check name `ck_school_attendance_status`.
- Writer is `school_teacher` only, assigned students only (`assigned_teacher_user_id == user.id` AND `school_id == own school`).
- Tier gate: `require_school_entitlement(db, user, school_id, None)` — after scope checks, before any write. No `TIER_SERVICES` key.
- Future date = after `_today_ist()` (Asia/Kolkata) → 422 `"Attendance cannot be marked for a future date"`.
- Scope failure → 403 `"One or more students are not assigned to you"`; non-teacher → 403 `"Teacher role required"`.
- 1–200 records per call, unique `student_id`, `extra="forbid"`.
- Readers see only records whose `school_id` equals the student's current `school_id` (C1).
- Read summary = 30 most recent records, newest first, with per-status counts over those same records (C3).
- Existing keys unchanged: `/school/dashboard` + `/school/reports` `attendance`, all 16 360 tab keys, `SCHOOL_NAV.parent`.
- 360 attendance empty text must start with `"No "`.
- Backend commands run in `apps/api` (local venv) or `docker compose exec api python -m pytest -q …` after `docker compose build api && docker compose up -d --force-recreate api worker beat` (AGENTS.md:101-126). Frontend commands run in `apps/web`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Concurrent transfer/reassignment while a teacher saves** — the save must either finish before the move or be refused; never write a row for a student who has left the teacher. Pinned by the `FOR SHARE` lock + re-check under it (Task 3); the `moved_away` case in Task 3 is the sequential proxy (a true two-connection race is not unit-tested -- the reviewer checks the lock order and the re-check against `school_transfers.py:398`).
2. **A same-day record from the student's previous school** — the upsert overwrites that row (one row per student per day) and re-stamps `school_id`; the new school then sees it. Pinned by `test_mark_after_transfer_restamps_school` in Task 3.
3. **A teacher with zero assigned students** — `GET` returns `students: []` (200, not an error); the page shows the empty state. Pinned in Task 3 (`test_roster_empty_for_teacher_without_students`) and Task 5.
4. **Browser "today" vs school "today"** — the date picker's `max` comes from the server's `today` (IST), never `new Date()` (UTC). Pinned in Task 5 (`max` attribute test).
5. **Saving with nothing chosen** — no request is sent; the teacher gets an inline message. Pinned in Task 5.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `apps/api/app/models.py` | Modify (append after `SchoolActivityAttendance`, ~L1227) | `ATTENDANCE_STATUSES`, `SchoolAttendanceRecord` |
| `apps/api/alembic/versions/0046_school_attendance_records.py` | Create | Create-table migration |
| `apps/api/tests/test_enh_027_migration.py` | Modify L20-31 | Relax pinned head |
| `apps/api/app/schemas.py` | Modify (after `SkillAttendanceIn`, ~L1477) | `SchoolAttendanceMark`, `SchoolAttendanceIn` |
| `apps/api/app/api/school_attendance.py` | Create | Router, roster, mark, `daily_attendance_summary` |
| `apps/api/app/main.py` | Modify L9-33, L57 | Register router |
| `apps/api/app/api/schools.py` | Modify (`_skills()` ~L332, `_overview_payload` return ~L1403) | `_attendance()` lazy import + additive key |
| `apps/api/app/api/student_360.py` | Modify L38, L94 | Remove ENH-030 note; add `daily` |
| `apps/api/tests/test_enh_030_*.py` | Create (model, migration, schemas, mark, reads) | Backend tests |
| `apps/web/lib/apiErrors.ts` | Modify L39 | `sendJson` accepts `"PUT"` |
| `apps/web/lib/navigation.ts` | Modify L39 | Teacher nav gains Attendance |
| `apps/web/components/SchoolDailyAttendance.tsx` | Create | Client roster form |
| `apps/web/app/school/teacher/attendance/page.tsx`, `loading.tsx` | Create | Teacher page |
| `apps/web/components/SchoolChildOverview.tsx` | Modify L33-46, L69-86 | Optional type + metric |
| `apps/web/components/Student360Panels.tsx` | Modify L27, L105-111 | Empty text + daily table |
| `apps/web/tests/components/*` | Create/modify | Vitest |
| `apps/web/tests/e2e/enh-030-daily-attendance.spec.ts` | Create | Playwright |
| Docs (backlog, catalog, RTM, screen catalog, data model) | Modify | Traceability |

---

### Task 1: `SchoolAttendanceRecord` model + migration 0046

**Files:**
- Modify: `apps/api/app/models.py` (insert after `class SchoolActivityAttendance`, ~L1227)
- Create: `apps/api/alembic/versions/0046_school_attendance_records.py`
- Modify: `apps/api/tests/test_enh_027_migration.py:20-31`
- Test: `apps/api/tests/test_enh_030_model.py`, `apps/api/tests/test_enh_030_migration.py`

**Interfaces:**
- Produces: `app.models.ATTENDANCE_STATUSES: tuple[str, ...]`, `app.models.SchoolAttendanceRecord` (columns `id, school_student_id, school_id, session_date, status, marked_by_user_id, created_at, updated_at`), constraint `uq_school_attendance_student_date`, check `ck_school_attendance_status`, table `school_attendance_records`, revision `0046_school_attendance_records`.

- [ ] **Step 1: Write the failing model test** — `apps/api/tests/test_enh_030_model.py`

```python
"""ENH-030 -- SchoolAttendanceRecord constraints (spec §4, D4/D5)."""

from datetime import date

import pytest
from enh005_helpers import mk_school
from sqlalchemy.exc import IntegrityError

from app.models import ATTENDANCE_STATUSES, SchoolAttendanceRecord


def test_statuses_mirror_it_attendance():
    assert ATTENDANCE_STATUSES == ("present", "absent", "late", "excused")


def _row(w, **over):
    s = w["students"][0]
    return SchoolAttendanceRecord(school_student_id=s.id, school_id=w["school"].id, session_date=date(2026, 9, 1), status="present", marked_by_user_id=w["teacher"].id, **over)


@pytest.mark.asyncio
async def test_one_record_per_student_per_day(db_session):
    w = await mk_school(db_session, label="AttModel")
    db_session.add(_row(w))
    await db_session.commit()
    db_session.add(_row(w, status="absent"))
    with pytest.raises(IntegrityError, match="uq_school_attendance_student_date"):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_status_is_checked_in_the_database(db_session):
    w = await mk_school(db_session, label="AttModel")
    db_session.add(_row(w, status="sick"))
    with pytest.raises(IntegrityError, match="ck_school_attendance_status"):
        await db_session.commit()
    await db_session.rollback()
```

- [ ] **Step 2: Write the failing migration test** — `apps/api/tests/test_enh_030_migration.py`

```python
"""ENH-030 -- migration 0046 (spec §4, AC13): single head, create-table only, matches the model."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_enh_030_migration_0046", VERSIONS / "0046_school_attendance_records.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def _parents() -> dict[str, str | None]:
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        parent = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
        if rev:
            parents[rev] = parent
    return parents


def test_migration_follows_0045_and_is_the_single_head():
    assert _migration.revision == "0046_school_attendance_records"
    assert _migration.down_revision == "0045_psychometric_result_fields"
    parents = _parents()
    heads = set(parents) - set(parents.values())
    assert len(heads) == 1
    assert "0045_psychometric_result_fields" in set(parents.values())


@pytest.mark.asyncio
async def test_table_matches_the_model(db_session):
    def _describe(sync_conn):
        insp = inspect(sync_conn)
        return (
            {c["name"]: c["nullable"] for c in insp.get_columns("school_attendance_records")},
            {u["name"] for u in insp.get_unique_constraints("school_attendance_records")},
            {c["name"] for c in insp.get_check_constraints("school_attendance_records")},
            {i["name"] for i in insp.get_indexes("school_attendance_records")},
        )

    conn = await db_session.connection()
    columns, uniques, checks, indexes = await conn.run_sync(_describe)
    assert columns == {"id": False, "school_student_id": False, "school_id": False, "session_date": False, "status": False, "marked_by_user_id": False, "created_at": False, "updated_at": False}
    assert uniques == {"uq_school_attendance_student_date"}
    assert checks == {"ck_school_attendance_status"}
    assert {"ix_school_attendance_records_school_student_id", "ix_school_attendance_records_school_id", "ix_school_attendance_records_session_date"} <= indexes
```

- [ ] **Step 3: Run both to verify they fail**

Run: `python -m pytest -q tests/test_enh_030_model.py tests/test_enh_030_migration.py`
Expected: FAIL — `ImportError: cannot import name 'ATTENDANCE_STATUSES'` and `FileNotFoundError … 0046_school_attendance_records.py`.

- [ ] **Step 4: Add the model** — in `apps/api/app/models.py`, directly after `class SchoolActivityAttendance` (ends ~L1226):

```python
# ENH-030 (DEC-SCOPE-038 D4): the IT `Attendance.status` values; a missing row is "not marked", never absent.
ATTENDANCE_STATUSES = ("present", "absent", "late", "excused")


class SchoolAttendanceRecord(Base, TimestampMixin):
    """ENH-030 -- one School student's daily class attendance (docs/superpowers/specs/2026-09-30-enh-030-daily-attendance-design.md §4).

    One row per student per day (D5); re-marking updates it. `school_id` is stamped at mark time so, after a transfer, readers see only
    the current school's rows (C1) while the old ones are kept."""

    __tablename__ = "school_attendance_records"
    __table_args__ = (
        UniqueConstraint("school_student_id", "session_date", name="uq_school_attendance_student_date"),
        CheckConstraint("status IN ('present', 'absent', 'late', 'excused')", name="ck_school_attendance_status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"), index=True)
    session_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20))
    marked_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
```

- [ ] **Step 5: Add the migration** — `apps/api/alembic/versions/0046_school_attendance_records.py`

```python
"""ENH-030 -- school_attendance_records.

Revision ID: 0046_school_attendance_records
Revises: 0045_psychometric_result_fields

docs/superpowers/specs/2026-09-30-enh-030-daily-attendance-design.md §4. Create-table only: no existing table is altered and no
existing row is read or written. `downgrade()` drops the indexes, then the table.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0046_school_attendance_records"
down_revision = "0045_psychometric_result_fields"
branch_labels = None
depends_on = None

TABLE = "school_attendance_records"
INDEXED = ("school_student_id", "school_id", "session_date")


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("marked_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_student_id", "session_date", name="uq_school_attendance_student_date"),
        sa.CheckConstraint("status IN ('present', 'absent', 'late', 'excused')", name="ck_school_attendance_status"),
    )
    for column in INDEXED:
        op.create_index(f"ix_{TABLE}_{column}", TABLE, [column])


def downgrade() -> None:
    for column in reversed(INDEXED):
        op.drop_index(f"ix_{TABLE}_{column}", table_name=TABLE)
    op.drop_table(TABLE)
```

- [ ] **Step 6: Relax the ENH-027 head test** — in `apps/api/tests/test_enh_027_migration.py`, replace the last line of `test_migration_follows_enh024_and_is_the_single_head`:

```python
    # ENH-030 chained 0046 after this migration, so the intent is kept without pinning the head -- the relaxation
    # test_enh_025_migration.py received: one head, and 0045 is a parent in the chain.
    heads = set(parents) - set(parents.values())
    assert len(heads) == 1
    assert "0045_psychometric_result_fields" in set(parents.values())
```

- [ ] **Step 7: Apply the migration and run the tests**

Run (in `apps/api`, DB up): `alembic upgrade head` then `python -m pytest -q tests/test_enh_030_model.py tests/test_enh_030_migration.py tests/test_enh_027_migration.py tests/test_enh_025_migration.py`
Expected: all PASS. Then `alembic downgrade -1 && alembic upgrade head` — both succeed (AC13 round trip).

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/models.py apps/api/alembic/versions/0046_school_attendance_records.py apps/api/tests/test_enh_030_model.py apps/api/tests/test_enh_030_migration.py apps/api/tests/test_enh_027_migration.py
git commit -m "feat(enh-030): SchoolAttendanceRecord model and migration 0046"
```

---

### Task 2: Request schema `SchoolAttendanceIn`

**Files:**
- Modify: `apps/api/app/schemas.py` (after `class SkillAttendanceIn`, ~L1477)
- Test: `apps/api/tests/test_enh_030_schemas.py`

**Interfaces:**
- Consumes: `_unique_ids` (`schemas.py:1402`).
- Produces: `SchoolAttendanceMark(student_id: UUID, status: Literal["present","absent","late","excused"])`, `SchoolAttendanceIn(session_date: date, records: list[SchoolAttendanceMark])` (1–200, unique ids, `extra="forbid"`).

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_enh_030_schemas.py`

```python
"""ENH-030 -- request validation (spec §5.2, AC05)."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas import SchoolAttendanceIn


def _body(records=None, **over):
    return {"session_date": "2026-09-30", "records": records if records is not None else [{"student_id": str(uuid.uuid4()), "status": "present"}], **over}


def test_accepts_all_four_statuses():
    records = [{"student_id": str(uuid.uuid4()), "status": s} for s in ("present", "absent", "late", "excused")]
    parsed = SchoolAttendanceIn.model_validate(_body(records))
    assert [r.status for r in parsed.records] == ["present", "absent", "late", "excused"]


@pytest.mark.parametrize(
    "body",
    [
        _body([{"student_id": str(uuid.uuid4()), "status": "sick"}]),
        _body([]),
        _body([{"student_id": str(uuid.uuid4()), "status": "present"} for _ in range(201)]),
        _body(extra="x"),
        _body([{"student_id": str(uuid.uuid4()), "status": "present", "note": "x"}]),
        {"records": [{"student_id": str(uuid.uuid4()), "status": "present"}]},
    ],
    ids=["bad-status", "empty", "over-200", "extra-field", "extra-record-field", "no-date"],
)
def test_rejects_invalid_bodies(body):
    with pytest.raises(ValidationError):
        SchoolAttendanceIn.model_validate(body)


def test_rejects_a_repeated_student():
    sid = str(uuid.uuid4())
    with pytest.raises(ValidationError, match="must not repeat an id"):
        SchoolAttendanceIn.model_validate(_body([{"student_id": sid, "status": "present"}, {"student_id": sid, "status": "absent"}]))


def test_accepts_exactly_200():
    assert len(SchoolAttendanceIn.model_validate(_body([{"student_id": str(uuid.uuid4()), "status": "present"} for _ in range(200)])).records) == 200
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest -q tests/test_enh_030_schemas.py`
Expected: FAIL — `ImportError: cannot import name 'SchoolAttendanceIn'`.

- [ ] **Step 3: Implement** — in `apps/api/app/schemas.py`, after `class SkillAttendanceIn`:

```python
# ENH-030 (DEC-SCOPE-038): a teacher's whole-class mark for one day, one call (spec §5.2).
SchoolAttendanceStatus = Literal["present", "absent", "late", "excused"]


class SchoolAttendanceMark(BaseModel):
    model_config = {"extra": "forbid"}
    student_id: UUID
    status: SchoolAttendanceStatus


def _unique_students(rows: list) -> list:
    _unique_ids([r.student_id for r in rows])
    return rows


class SchoolAttendanceIn(BaseModel):
    model_config = {"extra": "forbid"}
    session_date: date
    records: Annotated[list[SchoolAttendanceMark], Field(min_length=1, max_length=200), AfterValidator(_unique_students)]
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest -q tests/test_enh_030_schemas.py`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas.py apps/api/tests/test_enh_030_schemas.py
git commit -m "feat(enh-030): SchoolAttendanceIn request schema"
```

---

### Task 3: Router — `GET` roster and `PUT` whole-class mark

**Files:**
- Create: `apps/api/app/api/school_attendance.py`
- Modify: `apps/api/app/main.py` (import list L9-33; router tuple L57)
- Test: `apps/api/tests/test_enh_030_mark.py`

**Interfaces:**
- Consumes: `SchoolAttendanceRecord`, `ATTENDANCE_STATUSES` (Task 1); `SchoolAttendanceIn` (Task 2); `schools._own_school_id(user) -> UUID`, `schools._scoped_students_query(db, user, school_id) -> Select` (async), `schools._today_ist() -> date`, `schools.require_school_entitlement(db, user, school_id, service_key)`.
- Produces: `GET /api/v1/school/attendance?date=` and `PUT /api/v1/school/attendance`, both returning `{"session_date": "YYYY-MM-DD", "today": "YYYY-MM-DD", "students": [{"id", "full_name", "grade_or_class", "status": str|None}]}`; constants `FUTURE_DATE`, `NOT_ASSIGNED`, `TEACHER_REQUIRED`, `MARK_ACTION = "school.daily_attendance_mark"`; `RECENT_LIMIT = 30` (used by Task 4).

- [ ] **Step 1: Write the failing tests** — `apps/api/tests/test_enh_030_mark.py`

```python
"""ENH-030 -- GET/PUT /school/attendance (spec §5.1-5.2, AC01-AC07). Each test builds its own throwaway school."""

import uuid
from datetime import date, timedelta

import pytest
from enh005_helpers import login, mk_school, move_student_directly
from sqlalchemy import func, select

from app.api.schools import TIER_DENIED, _today_ist
from app.models import AuditLog, SchoolAttendanceRecord

URL = "/api/v1/school/attendance"
DAY = "2026-09-01"


async def _world(db, *, students: int = 3, **over) -> dict:
    """mk_school assigns only the first student to the teacher; here every student but the last is assigned (the last is the
    same-school, unassigned control)."""
    w = await mk_school(db, label="Att", students=students, **over)
    for s in w["students"][:-1]:
        s.assigned_teacher_user_id = w["teacher"].id
    await db.commit()
    w["mine"] = w["students"][:-1]
    w["unassigned"] = w["students"][-1]
    return w


def _marks(students, status="present"):
    return [{"student_id": str(s.id), "status": status} for s in students]


async def _rows(db, **where):
    stmt = select(SchoolAttendanceRecord)
    for key, value in where.items():
        stmt = stmt.where(getattr(SchoolAttendanceRecord, key) == value)
    return (await db.scalars(stmt.execution_options(populate_existing=True))).all()


async def _mark_audits(db, school_id):
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.daily_attendance_mark", AuditLog.entity_id == str(school_id)))


@pytest.mark.asyncio
async def test_teacher_marks_whole_class_in_one_call(client, db_session):  # AC01
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    records = [{"student_id": str(w["mine"][0].id), "status": "present"}, {"student_id": str(w["mine"][1].id), "status": "late"}]
    response = await client.put(URL, json={"session_date": DAY, "records": records})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_date"] == DAY
    assert {s["id"]: s["status"] for s in body["students"]} == {str(w["mine"][0].id): "present", str(w["mine"][1].id): "late"}
    rows = await _rows(db_session, session_date=date(2026, 9, 1))
    assert {(r.school_student_id, r.status) for r in rows} == {(w["mine"][0].id, "present"), (w["mine"][1].id, "late")}
    assert {r.marked_by_user_id for r in rows} == {w["teacher"].id}
    assert {r.school_id for r in rows} == {w["school"].id}


@pytest.mark.asyncio
async def test_remark_updates_never_duplicates_and_retry_is_harmless(client, db_session):  # AC02
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    assert (await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"])})).status_code == 200
    assert (await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"][:1], "absent")})).status_code == 200
    assert (await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"][:1], "absent")})).status_code == 200
    rows = {r.school_student_id: r.status for r in await _rows(db_session, session_date=date(2026, 9, 1))}
    assert rows == {w["mine"][0].id: "absent", w["mine"][1].id: "present"}  # partial roster: the second student is untouched
    assert await _mark_audits(db_session, w["school"].id) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["unassigned", "other_school", "unknown", "moved_away"])
async def test_any_student_outside_the_class_rejects_the_whole_call(client, db_session, case):  # AC03
    w = await _world(db_session)
    other = await mk_school(db_session, admin=w["admin"], label="AttOther")
    if case == "moved_away":
        await move_student_directly(db_session, w["mine"][1], other["school"])
    outsider = {
        "unassigned": w["unassigned"].id,
        "other_school": other["students"][0].id,
        "unknown": uuid.uuid4(),
        "moved_away": w["mine"][1].id,
    }[case]
    await login(client, w["teacher"].email)
    records = [{"student_id": str(w["mine"][0].id), "status": "present"}, {"student_id": str(outsider), "status": "present"}]
    response = await client.put(URL, json={"session_date": DAY, "records": records})
    assert response.status_code == 403
    assert response.json()["detail"] == "One or more students are not assigned to you"
    assert await _rows(db_session, school_student_id=w["mine"][0].id) == []
    assert await _mark_audits(db_session, w["school"].id) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["coordinator", "principal", "parent"])
async def test_only_teachers_may_read_or_mark(client, db_session, role):  # AC04
    w = await _world(db_session)
    await login(client, w[role].email)
    assert (await client.get(URL)).status_code == 403
    response = await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"])})
    assert response.status_code == 403 and response.json()["detail"] == "Teacher role required"
    assert await _rows(db_session, school_id=w["school"].id) == []


@pytest.mark.asyncio
async def test_future_date_is_refused(client, db_session):  # AC05
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    tomorrow = (_today_ist() + timedelta(days=1)).isoformat()
    put = await client.put(URL, json={"session_date": tomorrow, "records": _marks(w["mine"])})
    assert put.status_code == 422 and put.json()["detail"] == "Attendance cannot be marked for a future date"
    get = await client.get(URL, params={"date": tomorrow})
    assert get.status_code == 422
    assert (await client.put(URL, json={"session_date": _today_ist().isoformat(), "records": _marks(w["mine"])})).status_code == 200


@pytest.mark.asyncio
async def test_invalid_bodies_are_422_and_write_nothing(client, db_session):  # AC05
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    sid = str(w["mine"][0].id)
    for body in (
        {"session_date": DAY, "records": [{"student_id": sid, "status": "sick"}]},
        {"session_date": DAY, "records": []},
        {"session_date": DAY, "records": [{"student_id": sid, "status": "present"}, {"student_id": sid, "status": "absent"}]},
        {"session_date": DAY, "records": _marks(w["mine"]), "school_id": str(w["school"].id)},
    ):
        assert (await client.put(URL, json=body)).status_code == 422
    assert await _rows(db_session, school_id=w["school"].id) == []


@pytest.mark.asyncio
async def test_expired_partnership_is_denied_with_its_audit_row(client, db_session):  # AC06
    w = await _world(db_session, tier_valid_until=_today_ist() - timedelta(days=1))
    await login(client, w["teacher"].email)
    response = await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"])})
    assert response.status_code == 403 and "expired" in response.json()["detail"]
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == TIER_DENIED, AuditLog.entity_id == str(w["school"].id))) == 1
    assert await _rows(db_session, school_id=w["school"].id) == []


@pytest.mark.asyncio
async def test_each_mark_writes_one_audit_row_with_a_tally(client, db_session):  # AC07
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    records = [{"student_id": str(w["mine"][0].id), "status": "present"}, {"student_id": str(w["mine"][1].id), "status": "absent"}]
    assert (await client.put(URL, json={"session_date": DAY, "records": records})).status_code == 200
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.daily_attendance_mark", AuditLog.entity_id == str(w["school"].id)))).one()
    assert audit.user_id == w["teacher"].id and audit.entity_type == "school"
    assert audit.metadata_json == {"session_date": DAY, "count": 2, "statuses": {"present": 1, "absent": 1}}


@pytest.mark.asyncio
async def test_roster_lists_only_assigned_students_with_saved_status(client, db_session):  # AC01 (read side)
    w = await _world(db_session)
    await login(client, w["teacher"].email)
    await client.put(URL, json={"session_date": DAY, "records": _marks(w["mine"][:1], "excused")})
    body = (await client.get(URL, params={"date": DAY})).json()
    assert body["today"] == _today_ist().isoformat()
    assert {s["id"]: s["status"] for s in body["students"]} == {str(w["mine"][0].id): "excused", str(w["mine"][1].id): None}
    default = (await client.get(URL)).json()
    assert default["session_date"] == _today_ist().isoformat()


@pytest.mark.asyncio
async def test_roster_empty_for_teacher_without_students(client, db_session):  # Review Focus 3
    w = await mk_school(db_session, label="AttEmpty", students=0)
    await login(client, w["teacher"].email)
    response = await client.get(URL)
    assert response.status_code == 200 and response.json()["students"] == []


@pytest.mark.asyncio
async def test_mark_after_transfer_restamps_school(client, db_session):  # Review Focus 2
    w = await _world(db_session)
    old = await mk_school(db_session, admin=w["admin"], label="AttOld")
    student = w["mine"][0]
    db_session.add(SchoolAttendanceRecord(school_student_id=student.id, school_id=old["school"].id, session_date=date(2026, 9, 1), status="absent", marked_by_user_id=old["teacher"].id))
    await db_session.commit()
    await login(client, w["teacher"].email)
    assert (await client.put(URL, json={"session_date": DAY, "records": _marks([student])})).status_code == 200
    rows = await _rows(db_session, school_student_id=student.id)
    assert [(r.school_id, r.status) for r in rows] == [(w["school"].id, "present")]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest -q tests/test_enh_030_mark.py`
Expected: FAIL — every test gets `404` (route does not exist).

- [ ] **Step 3: Implement the router** — `apps/api/app/api/school_attendance.py`

```python
"""ENH-030 -- daily class attendance for School students (docs/superpowers/specs/2026-09-30-enh-030-daily-attendance-design.md).

A teacher marks their assigned students for one day in one call (DEC-SCOPE-038 D1/D2). Its own router, like ENH-005/011/013's, so
`schools.py` does not grow; `schools._overview_payload` reads `daily_attendance_summary` through a call-time import.
"""

from collections import Counter
from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import _own_school_id, _scoped_students_query, _today_ist, require_school_entitlement
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import ATTENDANCE_STATUSES, AuditLog, SchoolAttendanceRecord, SchoolStudent, User
from app.schemas import SchoolAttendanceIn

router = APIRouter(prefix="/school", tags=["school-attendance"])
logger = get_logger("app.school.attendance")

TEACHER_REQUIRED = "Teacher role required"
FUTURE_DATE = "Attendance cannot be marked for a future date"
NOT_ASSIGNED = "One or more students are not assigned to you"
MARK_ACTION = "school.daily_attendance_mark"
RECENT_LIMIT = 30  # C3: the read summary covers the 30 most recent marked days


def _require_teacher(user: User = Depends(get_current_user)) -> User:
    if user.role != "school_teacher":
        raise HTTPException(403, TEACHER_REQUIRED)
    return user


def _check_date(day: date) -> None:
    if day > _today_ist():
        raise HTTPException(422, FUTURE_DATE)


async def _roster(db: AsyncSession, user: User, school_id: UUID, day: date) -> dict:
    """The teacher's assigned students (the existing SCH-001-AC03 scope) with that day's status at this school, or None (not marked)."""
    scoped = await _scoped_students_query(db, user, school_id)
    students = (await db.scalars(scoped.order_by(SchoolStudent.grade_or_class, SchoolStudent.full_name, SchoolStudent.id))).all()
    marks: dict[UUID, str] = {}
    if students:
        rows = await db.execute(
            select(SchoolAttendanceRecord.school_student_id, SchoolAttendanceRecord.status).where(
                SchoolAttendanceRecord.school_student_id.in_([s.id for s in students]),
                SchoolAttendanceRecord.session_date == day,
                SchoolAttendanceRecord.school_id == school_id,
            )
        )
        marks = dict(rows.all())
    return {
        "session_date": day,
        "today": _today_ist(),
        "students": [{"id": s.id, "full_name": s.full_name, "grade_or_class": s.grade_or_class, "status": marks.get(s.id)} for s in students],
    }


@router.get("/attendance")
async def attendance_roster(day: date | None = Query(None, alias="date"), user: User = Depends(_require_teacher), db: AsyncSession = Depends(get_db)):
    """Spec §5.1. Pure read: no database write."""
    school_id = _own_school_id(user)
    day = day or _today_ist()
    _check_date(day)
    body = await _roster(db, user, school_id, day)
    logger.info("school_attendance_roster_read", extra={"extra_fields": {"actor_id": str(user.id), "session_date": day.isoformat(), "count": len(body["students"])}})
    return body


@router.put("/attendance")
async def mark_daily_attendance(payload: SchoolAttendanceIn, user: User = Depends(_require_teacher), db: AsyncSession = Depends(get_db)):
    """Spec §5.2. One transaction: lock the listed students FOR SHARE (a transfer approval or reassignment takes them FOR UPDATE, so
    it waits for this write, or this waits for it and sees the result), re-check scope under the lock, tier gate, upsert, audit,
    commit. Any failure before the commit leaves nothing written. Rows are locked in id order so two saves cannot deadlock.
    Unlisted students are untouched; a retry of the same body is harmless."""
    school_id = _own_school_id(user)
    _check_date(payload.session_date)
    ids = sorted({r.student_id for r in payload.records})
    locked = (
        await db.scalars(
            select(SchoolStudent).where(SchoolStudent.id.in_(ids)).order_by(SchoolStudent.id).with_for_update(read=True).execution_options(populate_existing=True)
        )
    ).all()
    if len(locked) != len(ids) or any(s.school_id != school_id or s.assigned_teacher_user_id != user.id for s in locked):
        raise HTTPException(403, NOT_ASSIGNED)
    # ENH-022: after scope, before any write -- a denial commits only its own audit row.
    await require_school_entitlement(db, user, school_id, None)
    stmt = pg_insert(SchoolAttendanceRecord).values(
        [
            {"id": uuid4(), "school_student_id": r.student_id, "school_id": school_id, "session_date": payload.session_date, "status": r.status, "marked_by_user_id": user.id}
            for r in payload.records
        ]
    )
    await db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_school_attendance_student_date",
            set_={"status": stmt.excluded.status, "school_id": stmt.excluded.school_id, "marked_by_user_id": stmt.excluded.marked_by_user_id, "updated_at": func.now()},
        )
    )
    tally = Counter(r.status for r in payload.records)
    statuses = {s: tally[s] for s in ATTENDANCE_STATUSES if tally[s]}
    db.add(AuditLog(user_id=user.id, action=MARK_ACTION, entity_type="school", entity_id=str(school_id), metadata_json={"session_date": payload.session_date.isoformat(), "count": len(payload.records), "statuses": statuses}))
    await db.commit()
    logger.info("school_attendance_marked", extra={"extra_fields": {"actor_id": str(user.id), "school_id": str(school_id), "session_date": payload.session_date.isoformat(), "count": len(payload.records)}})
    return await _roster(db, user, school_id, payload.session_date)
```

- [ ] **Step 4: Register the router** — `apps/api/app/main.py`: add `school_attendance,` to the `from app.api import (...)` list (alphabetically, before `school_feedback`), and add `school_attendance.router` to the `for r in (...)` tuple right after `school_reports.router`.

- [ ] **Step 5: Run to verify they pass**

Run: `python -m pytest -q tests/test_enh_030_mark.py`
Expected: PASS (all parametrized cases).

- [ ] **Step 6: Lint**

Run: `python -m ruff check app/api/school_attendance.py app/main.py tests/test_enh_030_mark.py`
Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/api/school_attendance.py apps/api/app/main.py apps/api/tests/test_enh_030_mark.py
git commit -m "feat(enh-030): GET/PUT /school/attendance -- teacher marks the class in one call"
```

---

### Task 4: Read surfaces — overview `daily_attendance` and the 360 Attendance tab

**Files:**
- Modify: `apps/api/app/api/school_attendance.py` (add `daily_attendance_summary`)
- Modify: `apps/api/app/api/schools.py` (`_attendance()` beside `_skills()` ~L332; `_overview_payload` return dict ~L1403)
- Modify: `apps/api/app/api/student_360.py:38` (delete line), `:94`
- Test: `apps/api/tests/test_enh_030_reads.py`

**Interfaces:**
- Consumes: `RECENT_LIMIT`, `SchoolAttendanceRecord`, `ATTENDANCE_STATUSES`.
- Produces: `school_attendance.daily_attendance_summary(db, student: SchoolStudent) -> {"counts": {"present": int, "absent": int, "late": int, "excused": int}, "recent": [{"session_date": date, "status": str}]}`; overview key `daily_attendance` (same shape); 360 `tabs.attendance.data.daily` (same shape).

- [ ] **Step 1: Write the failing tests** — `apps/api/tests/test_enh_030_reads.py`

```python
"""ENH-030 -- where a mark is read (spec §5.3, AC08-AC11)."""

from datetime import date, timedelta

import pytest
from enh005_helpers import login, mk_school, mk_staff, mk_student, move_student_directly
from sqlalchemy import select

from app.models import SchoolAttendanceRecord

URL = "/api/v1/school/attendance"
ZERO = {"present": 0, "absent": 0, "late": 0, "excused": 0}


async def _marked_world(client, db):
    """Student 0 (assigned to the teacher, linked to the parent) marked on two days by the real endpoint."""
    w = await mk_school(db, label="AttRead", students=2)
    await login(client, w["teacher"].email)
    sid = str(w["students"][0].id)
    for day, status in (("2026-09-01", "present"), ("2026-09-02", "late")):
        assert (await client.put(URL, json={"session_date": day, "records": [{"student_id": sid, "status": status}]})).status_code == 200
    return w


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["parent", "teacher", "coordinator", "principal"])
async def test_overview_carries_daily_attendance_for_every_reader(client, db_session, role):  # AC08
    w = await _marked_world(client, db_session)
    await login(client, w[role].email)
    body = (await client.get(f"/api/v1/school/students/{w['students'][0].id}/overview")).json()
    assert body["daily_attendance"] == {
        "counts": {"present": 1, "absent": 0, "late": 1, "excused": 0},
        "recent": [{"session_date": "2026-09-02", "status": "late"}, {"session_date": "2026-09-01", "status": "present"}],
    }


@pytest.mark.asyncio
async def test_unmarked_student_has_zero_counts(client, db_session):  # AC08
    w = await _marked_world(client, db_session)
    await login(client, w["coordinator"].email)
    body = (await client.get(f"/api/v1/school/students/{w['students'][1].id}/overview")).json()
    assert body["daily_attendance"] == {"counts": ZERO, "recent": []}


@pytest.mark.asyncio
async def test_recent_is_capped_at_30_newest_first(client, db_session):  # C3
    w = await mk_school(db_session, label="AttCap")
    s = w["students"][0]
    for d in range(35):
        db_session.add(SchoolAttendanceRecord(school_student_id=s.id, school_id=w["school"].id, session_date=date(2026, 9, 1) - timedelta(days=d), status="present", marked_by_user_id=w["teacher"].id))
    await db_session.commit()
    await login(client, w["coordinator"].email)
    daily = (await client.get(f"/api/v1/school/students/{s.id}/overview")).json()["daily_attendance"]
    assert len(daily["recent"]) == 30 and daily["counts"]["present"] == 30
    dates = [r["session_date"] for r in daily["recent"]]
    assert dates[0] == "2026-09-01" and dates == sorted(dates, reverse=True)


@pytest.mark.asyncio
async def test_360_attendance_tab_shows_daily_and_drops_the_enh030_note(client, db_session):  # AC09
    w = await _marked_world(client, db_session)
    await login(client, w["teacher"].email)
    tab = (await client.get(f"/api/v1/school/students/{w['students'][0].id}/360-view")).json()["tabs"]["attendance"]
    assert tab["status"] == "has_data" and tab["count"] == 2 and tab["not_tracked"] == []
    assert [r["status"] for r in tab["data"]["daily"]["recent"]] == ["late", "present"]
    assert tab["data"]["activities"] == [] and tab["data"]["skill_sessions"] == []


@pytest.mark.asyncio
async def test_360_fresh_student_attendance_stays_empty_and_service_roles_restricted(client, db_session):  # AC09
    w = await mk_school(db_session, label="AttFresh")
    fresh = await mk_student(db_session, w["school"], w["coordinator"], "Fresh")
    await db_session.commit()
    await login(client, w["coordinator"].email)
    tab = (await client.get(f"/api/v1/school/students/{fresh.id}/360-view")).json()["tabs"]["attendance"]
    assert tab["status"] == "empty" and tab["count"] == 0 and tab["not_tracked"] == []
    staff = await mk_staff(db_session, w["school"], w["admin"], role="academic_team")
    await login(client, staff.email)
    tab = (await client.get(f"/api/v1/school/students/{fresh.id}/360-view")).json()["tabs"]["attendance"]
    assert tab == {"status": "restricted", "count": None, "not_tracked": [], "data": {}}


@pytest.mark.asyncio
async def test_after_transfer_new_school_does_not_see_old_records(client, db_session):  # AC10
    w = await _marked_world(client, db_session)
    new = await mk_school(db_session, admin=w["admin"], label="AttNew")
    student = w["students"][0]
    await move_student_directly(db_session, student, new["school"])
    await login(client, new["coordinator"].email)
    body = (await client.get(f"/api/v1/school/students/{student.id}/overview")).json()
    assert body["daily_attendance"] == {"counts": ZERO, "recent": []}
    kept = (await db_session.scalars(select(SchoolAttendanceRecord).where(SchoolAttendanceRecord.school_student_id == student.id))).all()
    assert len(kept) == 2  # data preserved


@pytest.mark.asyncio
async def test_dashboard_and_reports_attendance_are_unchanged(client, db_session):  # AC11
    w = await _marked_world(client, db_session)
    await login(client, w["coordinator"].email)
    for path in ("/api/v1/school/dashboard", "/api/v1/school/reports"):
        body = (await client.get(path)).json()
        assert body["attendance"] == {"present": 0, "total": 0}, path  # activity attendance only
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest -q tests/test_enh_030_reads.py`
Expected: FAIL — `KeyError: 'daily_attendance'` / `'daily'`, and `not_tracked` still carries the ENH-030 note. `test_dashboard_and_reports_attendance_are_unchanged` already passes (a guard, not new behaviour).

- [ ] **Step 3: Add the summary helper** — append to `apps/api/app/api/school_attendance.py`:

```python
async def daily_attendance_summary(db: AsyncSession, student: SchoolStudent) -> dict:
    """Spec §5.3 / C1 / C3: the student's 30 most recent records at their CURRENT school, newest first, with per-status counts over
    those same records. No scope check here: callers (`_overview_payload`) have already applied the reader's own."""
    rows = (
        await db.execute(
            select(SchoolAttendanceRecord.session_date, SchoolAttendanceRecord.status)
            .where(SchoolAttendanceRecord.school_student_id == student.id, SchoolAttendanceRecord.school_id == student.school_id)
            .order_by(SchoolAttendanceRecord.session_date.desc())
            .limit(RECENT_LIMIT)
        )
    ).all()
    counts = Counter(status for _day, status in rows)
    return {"counts": {s: counts[s] for s in ATTENDANCE_STATUSES}, "recent": [{"session_date": day, "status": status} for day, status in rows]}
```

- [ ] **Step 4: Wire it into `_overview_payload`** — in `apps/api/app/api/schools.py`, add directly after `def _skills():` (~L332-337):

```python
def _attendance():
    """ENH-030's module, imported at call time for the same reason as `_skills()`: `school_attendance` imports this module's helpers."""
    from app.api import school_attendance  # noqa: PLC0415

    return school_attendance
```

and in `_overview_payload`'s returned dict, after the `"skills": …` entry:

```python
        # ENH-030 (DEC-SCOPE-038): additive key; same reader scope as everything above.
        "daily_attendance": await _attendance().daily_attendance_summary(db, student),
```

- [ ] **Step 5: Update the 360 tab** — in `apps/api/app/api/student_360.py`: delete the line `"attendance": "Daily and period attendance is not tracked yet (ENH-030).",` from `NOT_TRACKED`, and replace the `tabs["attendance"] = …` line with:

```python
    daily = overview["daily_attendance"]  # ENH-030: School roles only, like the rest of this tab
    tabs["attendance"] = (
        _tab("attendance", {"activities": attended, "skill_sessions": skill_sessions, "daily": daily}, len(attended) + len(skill_sessions) + len(daily["recent"]))
        if school_role
        else _restricted()
    )
```

- [ ] **Step 6: Run the new and the guarding suites**

Run: `python -m pytest -q tests/test_enh_030_reads.py tests/test_enh_013_360_view.py tests/test_enh_013_career_goal.py tests/test_sch_007_parent_portal.py tests/test_sch_reports.py tests/test_enh_016_contracts.py tests/test_school_reports*.py`
Expected: all PASS, existing files unchanged. (If `tests/test_school_reports*.py` does not match a file, drop that glob; `ls tests | grep -i report` lists the ENH-015 files to include.)

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/api/school_attendance.py apps/api/app/api/schools.py apps/api/app/api/student_360.py apps/api/tests/test_enh_030_reads.py
git commit -m "feat(enh-030): daily attendance on the child overview and the 360 Attendance tab"
```

---

### Task 5: `SchoolDailyAttendance` client roster (+ `sendJson` PUT, teacher nav)

**Files:**
- Modify: `apps/web/lib/apiErrors.ts:39` (method type)
- Modify: `apps/web/lib/navigation.ts:39`
- Create: `apps/web/lib/attendance.ts` (plain module, shared by client and server components)
- Create: `apps/web/components/SchoolDailyAttendance.tsx`
- Test: `apps/web/tests/components/SchoolDailyAttendance.test.tsx`

**Interfaces:**
- Consumes: `PUT /api/v1/school/attendance` body/response (Task 3); `sendJson`, `FormMessage`, `formatCalendarDate`.
- Produces: `lib/attendance.ts` exports `ATTENDANCE_STATUSES`, `ATTENDANCE_LABEL: Record<AttendanceStatus,string>`, type `AttendanceStatus`; `components/SchoolDailyAttendance.tsx` default export `SchoolDailyAttendance({ roster }: { roster: DailyRoster })` and types `RosterStudent`, `DailyRoster = { session_date: string; today: string; students: RosterStudent[] }`.

- [ ] **Step 1: Write the failing test** — `apps/web/tests/components/SchoolDailyAttendance.test.tsx`

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolDailyAttendance, { type DailyRoster } from "@/components/SchoolDailyAttendance";
import { SCHOOL_NAV } from "@/lib/navigation";

import { json, stubFetch } from "./skillFixtures";

// ENH-030 spec §6: one fieldset of four labelled radios per assigned student, no default for an unmarked student (C2), Mark all
// present fills only unmarked rows, one Save for the class, messages under the form, unsaved-changes flag, server-provided "today".
const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

const ROSTER: DailyRoster = {
  session_date: "2026-09-29",
  today: "2026-09-30",
  students: [
    { id: "s1", full_name: "Asha Rao", grade_or_class: "Grade 5-A", status: "absent" },
    { id: "s2", full_name: "Ben Das", grade_or_class: "Grade 5-A", status: null },
  ],
};
const group = (name: string) => screen.getByRole("group", { name: new RegExp(name) });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  push.mockReset();
  refresh.mockReset();
});

describe("SchoolDailyAttendance", () => {
  it("prefills saved marks and leaves unmarked students unselected", () => {
    render(<SchoolDailyAttendance roster={ROSTER} />);
    expect((within(group("Asha Rao")).getByLabelText("Absent") as HTMLInputElement).checked).toBe(true);
    expect(within(group("Ben Das")).getAllByRole("radio").some((r) => (r as HTMLInputElement).checked)).toBe(false);
    expect(within(group("Ben Das")).getByText("Not marked")).toBeTruthy();
    expect(screen.queryByText("Unsaved changes")).toBeNull();
  });

  it("caps the date at the server's today and navigates on change", () => {
    render(<SchoolDailyAttendance roster={ROSTER} />);
    const date = screen.getByLabelText("Date");
    expect(date.getAttribute("max")).toBe("2026-09-30");
    fireEvent.change(date, { target: { value: "2026-09-28" } });
    expect(push).toHaveBeenCalledWith("/school/teacher/attendance?date=2026-09-28");
  });

  it("asks before leaving the date with unsaved marks", () => {
    const confirm = vi.fn(() => false);
    vi.stubGlobal("confirm", confirm);
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(within(group("Ben Das")).getByLabelText("Late"));
    expect(screen.getByText("Unsaved changes")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-09-28" } });
    expect(confirm).toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it("Mark all present fills only unmarked students", () => {
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark all present" }));
    expect((within(group("Asha Rao")).getByLabelText("Absent") as HTMLInputElement).checked).toBe(true);
    expect((within(group("Ben Das")).getByLabelText("Present") as HTMLInputElement).checked).toBe(true);
  });

  it("saves the whole class in one PUT and confirms", async () => {
    const fetchMock = stubFetch(() => json({ ...ROSTER, students: ROSTER.students.map((s) => ({ ...s, status: s.status ?? "present" })) }));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark all present" }));
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/attendance");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ session_date: "2026-09-29", records: [{ student_id: "s1", status: "absent" }, { student_id: "s2", status: "present" }] });
    expect(screen.getByRole("status").textContent).toMatch(/Attendance saved for 2 students on/);
  });

  it("sends only chosen students and says how many are left unmarked", async () => {
    const fetchMock = stubFetch(() => json(ROSTER));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body)).records).toEqual([{ student_id: "s1", status: "absent" }]);
    expect(screen.getByRole("status").textContent).toMatch(/1 student on .* 1 left unmarked\./);
  });

  it("keeps the marks and shows the server's reason when a save fails", async () => {
    stubFetch(() => json({ detail: "One or more students are not assigned to you" }, 403));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(within(group("Ben Das")).getByLabelText("Late"));
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("One or more students are not assigned to you"));
    expect((within(group("Ben Das")).getByLabelText("Late") as HTMLInputElement).checked).toBe(true);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("does not send a request when nothing is chosen", () => {
    const fetchMock = stubFetch(() => json(ROSTER));
    render(<SchoolDailyAttendance roster={{ ...ROSTER, students: [{ ...ROSTER.students[1] }] }} />);
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toBe("Choose a status for at least one student.");
  });

  it("disables the form while saving", async () => {
    let resolve: (r: Response) => void = () => {};
    stubFetch(() => new Promise<Response>((r) => { resolve = r; }));
    render(<SchoolDailyAttendance roster={ROSTER} />);
    fireEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    expect(screen.getByRole("button", { name: "Saving…" }).hasAttribute("disabled")).toBe(true);
    expect((screen.getByLabelText("Date") as HTMLInputElement).disabled).toBe(true);
    resolve(json(ROSTER));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save attendance" })).toBeTruthy());
  });

  it("explains an empty class", () => {
    render(<SchoolDailyAttendance roster={{ ...ROSTER, students: [] }} />);
    expect(screen.getByRole("status").textContent).toBe("No students assigned to you yet. Your School Coordinator assigns students to teachers.");
  });

  it("adds Attendance to the teacher's navigation only", () => {
    expect(SCHOOL_NAV.teacher.map((i) => [i.label, i.href])).toEqual([["Dashboard", "/school/teacher/dashboard"], ["Attendance", "/school/teacher/attendance"]]);
    expect(SCHOOL_NAV.parent.map((i) => i.label)).toEqual(["Dashboard", "Notifications"]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run (in `apps/web`): `npx vitest run tests/components/SchoolDailyAttendance.test.tsx`
Expected: FAIL — `Failed to resolve import "@/components/SchoolDailyAttendance"`.

- [ ] **Step 3: Widen `sendJson`** — `apps/web/lib/apiErrors.ts:39`:

```ts
export async function sendJson(url: string, method: "POST" | "PATCH" | "PUT", body: unknown): Promise<SendOutcome> {
```

- [ ] **Step 4: Teacher nav** — `apps/web/lib/navigation.ts:39`: change `["dashboard"]` to `["dashboard", "attendance"]` in the `teacher:` entry only.

- [ ] **Step 5a: Shared constants** — `apps/web/lib/attendance.ts` (no `"use client"`, so server components such as `SchoolChildOverview` can import it)

```ts
// ENH-030 (DEC-SCOPE-038 D4): the four daily attendance statuses, mirroring the backend's ATTENDANCE_STATUSES.
export const ATTENDANCE_STATUSES = ["present", "absent", "late", "excused"] as const;
export type AttendanceStatus = (typeof ATTENDANCE_STATUSES)[number];
export const ATTENDANCE_LABEL: Record<AttendanceStatus, string> = { present: "Present", absent: "Absent", late: "Late", excused: "Excused" };
```

- [ ] **Step 5b: Implement the component** — `apps/web/components/SchoolDailyAttendance.tsx`

```tsx
"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { sendJson } from "@/lib/apiErrors";
import { ATTENDANCE_LABEL, ATTENDANCE_STATUSES, type AttendanceStatus } from "@/lib/attendance";
import { formatCalendarDate } from "@/lib/formatDate";

// ENH-030 spec §6: the teacher marks their assigned class for one day with one Save (DEC-SCOPE-038 D1/D2). Four labelled radios per
// student (D4); an unmarked student starts with nothing chosen (C2) and "Mark all present" fills only those. The date picker's max is
// the server's school-calendar "today", never the browser clock. Unsaved marks are flagged and guarded against leaving the page.
export type RosterStudent = { id: string; full_name: string; grade_or_class: string | null; status: AttendanceStatus | null };
export type DailyRoster = { session_date: string; today: string; students: RosterStudent[] };

type Marks = Record<string, AttendanceStatus | null>;
const PAGE = "/school/teacher/attendance";
const LEAVE_WITH_UNSAVED = "You have unsaved attendance. Leave without saving it?";
const savedMarks = (roster: DailyRoster): Marks => Object.fromEntries(roster.students.map((s) => [s.id, s.status]));
const plural = (n: number) => `${n} student${n === 1 ? "" : "s"}`;

export default function SchoolDailyAttendance({ roster }: { roster: DailyRoster }) {
  const router = useRouter();
  const saved = savedMarks(roster);
  const [marks, setMarks] = useState<Marks>(() => savedMarks(roster));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const dirty = roster.students.some((s) => marks[s.id] !== saved[s.id]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    // Same guard as SchoolSkillAttendance: an in-app link is a client navigation that never fires `beforeunload`.
    const guardLinks = (event: MouseEvent) => {
      const link = (event.target as Element | null)?.closest?.("a[href]");
      if (!link || link.getAttribute("target") === "_blank") return;
      if (!window.confirm(LEAVE_WITH_UNSAVED)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", guardLinks, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", guardLinks, true);
    };
  }, [dirty]);

  function changeDate(value: string) {
    if (!value || value === roster.session_date) return;
    if (dirty && !window.confirm(LEAVE_WITH_UNSAVED)) return;
    router.push(`${PAGE}?date=${value}`);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    const records = roster.students.flatMap((s) => (marks[s.id] ? [{ student_id: s.id, status: marks[s.id] }] : []));
    if (records.length === 0) {
      setMessage({ text: "Choose a status for at least one student.", failed: true });
      return;
    }
    setBusy(true);
    setMessage(null);
    const outcome = await sendJson("/api/v1/school/attendance", "PUT", { session_date: roster.session_date, records });
    setBusy(false);
    if (!outcome.ok) {
      setMessage({ text: outcome.message, failed: true });
      return;
    }
    const left = roster.students.length - records.length;
    setMessage({ text: `Attendance saved for ${plural(records.length)} on ${formatCalendarDate(roster.session_date)}.${left ? ` ${left} left unmarked.` : ""}`, failed: false });
    router.refresh();
  }

  if (roster.students.length === 0) {
    return <p className="muted" role="status">No students assigned to you yet. Your School Coordinator assigns students to teachers.</p>;
  }
  return (
    <form className="form" onSubmit={save} aria-busy={busy}>
      <div className="field" style={{ maxWidth: 220 }}>
        <label htmlFor="attendance-date">Date</label>
        <input id="attendance-date" type="date" value={roster.session_date} max={roster.today} disabled={busy} onChange={(e) => changeDate(e.target.value)} />
      </div>
      <div style={{ display: "grid", gap: 12 }}>
        {roster.students.map((s) => (
          <fieldset key={s.id} style={{ border: 0, borderTop: "1px solid var(--line)", padding: "8px 0 0", margin: 0, minWidth: 0 }}>
            <legend style={{ padding: 0 }}>
              <strong>{s.full_name}</strong>
              {s.grade_or_class ? <span className="muted"> · {s.grade_or_class}</span> : null}
              {saved[s.id] === null ? <> <span className="badge">Not marked</span></> : null}
            </legend>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0 18px" }}>
              {ATTENDANCE_STATUSES.map((status) => (
                <label key={status} style={{ display: "inline-flex", alignItems: "center", gap: 8, minHeight: 44 }}>
                  <input type="radio" name={`attendance-${s.id}`} value={status} checked={marks[s.id] === status} disabled={busy} onChange={() => setMarks((m) => ({ ...m, [s.id]: status }))} />
                  {ATTENDANCE_LABEL[status]}
                </label>
              ))}
            </div>
          </fieldset>
        ))}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
        <button type="button" className="btn secondary small" disabled={busy} onClick={() => setMarks((m) => Object.fromEntries(roster.students.map((s) => [s.id, m[s.id] ?? "present"])))}>
          Mark all present
        </button>
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save attendance"}</button>
        {dirty && <span className="muted">Unsaved changes</span>}
      </div>
      {message && <FormMessage message={message} />}
    </form>
  );
}
```

- [ ] **Step 6: Run to verify it passes, plus the suites that read nav and `sendJson`**

Run: `npx vitest run tests/components/SchoolDailyAttendance.test.tsx tests/components/Enh015ReportPlacement.test.tsx tests/components/GlobalEducationPage.test.tsx tests/lib/clientBoundary.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/web/lib/apiErrors.ts apps/web/lib/navigation.ts apps/web/lib/attendance.ts apps/web/components/SchoolDailyAttendance.tsx apps/web/tests/components/SchoolDailyAttendance.test.tsx
git commit -m "feat(enh-030): teacher's whole-class attendance roster"
```

---

### Task 6: Teacher page `/school/teacher/attendance` (+ loading state)

**Files:**
- Create: `apps/web/app/school/teacher/attendance/page.tsx`, `apps/web/app/school/teacher/attendance/loading.tsx`
- Test: `apps/web/tests/components/TeacherAttendancePage.test.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/school/attendance?date=` (Task 3); `SchoolDailyAttendance`, `DailyRoster` (Task 5); `serverApi`, `accessUnavailable`, `PortalShell`, `SCHOOL_NAV.teacher`.
- Produces: the route.

- [ ] **Step 1: Write the failing test** — `apps/web/tests/components/TeacherAttendancePage.test.tsx`

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// ENH-030 spec §6: the page reads the roster for ?date= (validated to YYYY-MM-DD before it reaches the API) and hands it to the
// client form; a refused read (403/422) renders the shared Access-unavailable card with the server's message.
const serverApi = vi.fn();
vi.mock("@/lib/api", () => ({ serverApi: (...a: unknown[]) => serverApi(...a), ApiError: class ApiError extends Error { status = 0; } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/school/teacher/attendance" }));

import Page from "@/app/school/teacher/attendance/page";

const ME = { id: "t1", full_name: "Tara Teacher", role: "school_teacher" };
const ROSTER = { session_date: "2026-09-29", today: "2026-09-30", students: [{ id: "s1", full_name: "Asha Rao", grade_or_class: "Grade 5", status: null }] };

afterEach(() => {
  cleanup();
  serverApi.mockReset();
});

describe("Teacher attendance page", () => {
  it("loads the roster for the requested date", async () => {
    serverApi.mockImplementation((path: string) => Promise.resolve(path === "/api/v1/auth/me" ? ME : ROSTER));
    render(await Page({ searchParams: Promise.resolve({ date: "2026-09-29" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/school/attendance?date=2026-09-29");
    expect(screen.getByRole("heading", { level: 1, name: "Attendance" })).toBeTruthy();
    expect(screen.getByRole("group", { name: /Asha Rao/ })).toBeTruthy();
  });

  it("ignores a malformed date and asks for today", async () => {
    serverApi.mockImplementation((path: string) => Promise.resolve(path === "/api/v1/auth/me" ? ME : ROSTER));
    await Page({ searchParams: Promise.resolve({ date: "../../admin" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/school/attendance");
  });

  it("shows the server's reason when the roster cannot be read", async () => {
    serverApi.mockImplementation((path: string) => (path === "/api/v1/school/attendance?date=2099-01-01" ? Promise.reject(new Error("Attendance cannot be marked for a future date")) : Promise.resolve(ME)));
    render(await Page({ searchParams: Promise.resolve({ date: "2099-01-01" }) }));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
    expect(screen.getByText("Attendance cannot be marked for a future date")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run tests/components/TeacherAttendancePage.test.tsx`
Expected: FAIL — cannot resolve `@/app/school/teacher/attendance/page`.

- [ ] **Step 3: Implement the page** — `apps/web/app/school/teacher/attendance/page.tsx`

```tsx
import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import SchoolDailyAttendance, { type DailyRoster } from "@/components/SchoolDailyAttendance";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-030 (DEC-SCOPE-038): the teacher marks their assigned class for one day. The server scopes the roster (assigned students
// only) and decides "today" on the school calendar; only a well-formed YYYY-MM-DD is passed on.
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export default async function SchoolTeacherAttendancePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const raw = (await searchParams).date;
  const day = typeof raw === "string" && ISO_DATE.test(raw) ? raw : null;
  let user: User;
  let roster: DailyRoster;
  try {
    [user, roster] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<DailyRoster>(`/api/v1/school/attendance${day ? `?date=${day}` : ""}`)]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.teacher} roleLabel="Teacher" userName={user.full_name}>
      <div className="portal-content">
        <h1>Attendance</h1>
        <div className="card">
          <SchoolDailyAttendance key={roster.session_date} roster={roster} />
        </div>
      </div>
    </PortalShell>
  );
}
```

(`key={roster.session_date}`: a new date remounts the form with that day's marks; `router.refresh()` after a save keeps the same key, so the success message stays.)

- [ ] **Step 4: Implement the loading state** — `apps/web/app/school/teacher/attendance/loading.tsx`

```tsx
import PortalShell from "@/components/PortalShell";
import { SCHOOL_NAV } from "@/lib/navigation";

export default function Loading() {
  return (
    <PortalShell nav={SCHOOL_NAV.teacher} roleLabel="Teacher" userName="">
      <div className="portal-content" aria-busy="true" aria-label="Loading attendance">
        <h1>Attendance</h1>
        <div className="card"><div className="skeleton-line" style={{ marginBottom: 10 }} /><div className="skeleton-line" style={{ width: "60%" }} /></div>
      </div>
    </PortalShell>
  );
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `npx vitest run tests/components/TeacherAttendancePage.test.tsx`
Expected: PASS. If `PortalShell` needs extra mocks in this test environment, copy the mock block from an existing page test that renders `PortalShell` (`grep -l "PortalShell" tests/components/*Page*.test.tsx`).

- [ ] **Step 6: Commit**

```bash
git add apps/web/app/school/teacher/attendance apps/web/tests/components/TeacherAttendancePage.test.tsx
git commit -m "feat(enh-030): /school/teacher/attendance page"
```

---

### Task 7: Parent card metric and the 360 Attendance panel

**Files:**
- Modify: `apps/web/components/SchoolChildOverview.tsx` (`ChildOverview` type ~L33-46; `ChildStatusRow` ~L69-86)
- Modify: `apps/web/components/Student360Panels.tsx:27` and the `case "attendance"` body (~L105-111)
- Modify: `apps/web/tests/components/Student360Panels.test.tsx:18,49-53`
- Test: `apps/web/tests/components/SchoolChildOverview.attendance.test.tsx`

**Interfaces:**
- Consumes: overview `daily_attendance` and 360 `data.daily` (Task 4); `ATTENDANCE_LABEL`, `AttendanceStatus` from `@/lib/attendance` (Task 5).
- Produces: exported `DailyAttendance` type, `dailyAttendanceText(d: DailyAttendance): string` and `markedDays(n: number): string` from `SchoolChildOverview.tsx`.

- [ ] **Step 1: Write the failing tests** — `apps/web/tests/components/SchoolChildOverview.attendance.test.tsx`

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));

import { ChildStatusRow, type ChildOverview } from "@/components/SchoolChildOverview";

// ENH-030 spec §6: the parent's child card shows the last marked days as raw counts (C3); an older API without the key renders as before.
const base: ChildOverview = {
  student: { id: "s1", student_code: "S1", full_name: "Asha Rao", date_of_birth: null, grade_or_class: "Grade 5", school_name: "North", assigned_teacher_name: null },
  career_guidance: { status: "not_started", sessions: [] },
  counselling: { status: "not_started", notes: [] },
  recommended_careers: [],
  psychometric: { status: "not_started", assessments: [] },
  results: [],
  activities: { attended: [], upcoming: [] },
};

afterEach(cleanup);

describe("ChildStatusRow — daily attendance (ENH-030)", () => {
  it("shows the counts over the last marked days", () => {
    const daily = { counts: { present: 18, absent: 1, late: 1, excused: 0 }, recent: Array.from({ length: 20 }, (_, i) => ({ session_date: `2026-09-${String(i + 1).padStart(2, "0")}`, status: "present" as const })) };
    render(<ChildStatusRow overview={{ ...base, daily_attendance: daily }} />);
    expect(screen.getByText("Attendance (last 20 marked days)")).toBeTruthy();
    expect(screen.getByText("18 present · 1 late · 1 absent · 0 excused")).toBeTruthy();
  });

  it("says not marked yet when there are no records", () => {
    render(<ChildStatusRow overview={{ ...base, daily_attendance: { counts: { present: 0, absent: 0, late: 0, excused: 0 }, recent: [] } }} />);
    expect(screen.getByText("Attendance")).toBeTruthy();
    expect(screen.getByText("Not marked yet")).toBeTruthy();
  });

  it("renders exactly as before without the key", () => {
    render(<ChildStatusRow overview={base} />);
    expect(screen.queryByText(/^Attendance/)).toBeNull();
  });
});
```

and in `apps/web/tests/components/Student360Panels.test.tsx`: change line 18 to
`  attendance: { activities: [], skill_sessions: [], daily: { counts: { present: 0, absent: 0, late: 0, excused: 0 }, recent: [] } },`
and replace the test `"renders an empty state naming who records the data, plus the not-tracked note"` with:

```tsx
  it("renders an empty state naming who records the data", () => {
    render(<>{renderPanel("attendance", empty("attendance"), view())}</>);
    expect(screen.getByRole("status")).toHaveTextContent("No attendance recorded yet. Teachers mark daily attendance; the School Coordinator marks activity attendance.");
    expect(screen.queryByText(/not tracked yet/)).not.toBeInTheDocument();
  });

  it("renders daily attendance with its summary (ENH-030)", () => {
    const tab: Tab360 = { status: "has_data", count: 2, not_tracked: [], data: { activities: [], skill_sessions: [], daily: {
      counts: { present: 1, absent: 0, late: 1, excused: 0 },
      recent: [{ session_date: "2026-09-02", status: "late" }, { session_date: "2026-09-01", status: "present" }],
    } } };
    render(<>{renderPanel("attendance", tab, view())}</>);
    const table = screen.getByRole("table", { name: "Daily attendance" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByText("Late")).toBeInTheDocument();
    expect(screen.getByText("Last 2 marked days: 1 present · 1 late · 0 absent · 0 excused")).toBeInTheDocument();
  });

  it("still renders a 360 payload from an older API without daily", () => {
    const tab: Tab360 = { status: "has_data", count: 1, not_tracked: [], data: { activities: [{ title: "Career fair", scheduled_at: "2026-09-01T04:30:00Z", present: true }], skill_sessions: [] } };
    render(<>{renderPanel("attendance", tab, view())}</>);
    expect(screen.getByRole("table", { name: "School activity attendance" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Daily attendance" })).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run tests/components/SchoolChildOverview.attendance.test.tsx tests/components/Student360Panels.test.tsx`
Expected: FAIL — no "Attendance (last 20 marked days)" metric; old empty text; no "Daily attendance" table. (If the existing `Table` helper labels tables by caption, the `name` queries resolve once the caption exists; check `function Table` in `Student360Panels.tsx`.)

- [ ] **Step 3: Parent card** — in `apps/web/components/SchoolChildOverview.tsx` add, above `export type ChildOverview`:

```tsx
import { ATTENDANCE_LABEL, type AttendanceStatus } from "@/lib/attendance";

// ENH-030 (spec §5.3, C3): the 30 most recent marked days at the student's current school, with counts over those same days.
export type DailyAttendance = { counts: Record<AttendanceStatus, number>; recent: { session_date: string; status: AttendanceStatus }[] };

/** "18 present · 1 late · 1 absent · 0 excused" -- raw counts, no percentage (C3). Shared by the parent card and the 360 tab. */
export function dailyAttendanceText(d: DailyAttendance): string {
  return (["present", "late", "absent", "excused"] as const).map((s) => `${d.counts[s]} ${ATTENDANCE_LABEL[s].toLowerCase()}`).join(" · ");
}

/** "1 marked day" / "20 marked days". */
export const markedDays = (n: number) => `${n} marked day${n === 1 ? "" : "s"}`;
```

(put the `import` with the file's other imports at the top), add to `ChildOverview` after `skills?`:

```tsx
  // ENH-030. Optional: an API without it (an older deployment) renders exactly as before.
  daily_attendance?: DailyAttendance;
```

and in `ChildStatusRow`, after the `Published results` metric:

```tsx
      {overview.daily_attendance && (
        <div className="metric">
          <span>{overview.daily_attendance.recent.length ? `Attendance (last ${markedDays(overview.daily_attendance.recent.length)})` : "Attendance"}</span>
          <strong>{overview.daily_attendance.recent.length ? dailyAttendanceText(overview.daily_attendance) : "Not marked yet"}</strong>
        </div>
      )}
```

- [ ] **Step 4: 360 panel** — in `apps/web/components/Student360Panels.tsx`: import `{ type DailyAttendance, dailyAttendanceText, markedDays }` from `@/components/SchoolChildOverview` (extend the existing import) and `{ ATTENDANCE_LABEL }` from `@/lib/attendance`; set

```tsx
  attendance: "No attendance recorded yet. Teachers mark daily attendance; the School Coordinator marks activity attendance.",
```

and make the attendance case:

```tsx
    case "attendance": {
      const daily = d.daily as DailyAttendance | undefined; // absent from an older API
      return (
        <Card>
          {daily?.recent.length ? (
            <>
              <p>{`Last ${markedDays(daily.recent.length)}: ${dailyAttendanceText(daily)}`}</p>
              <Table caption="Daily attendance" head={["Date", "Status"]} rows={daily.recent.map((r) => [formatCalendarDate(r.session_date), ATTENDANCE_LABEL[r.status]])} />
            </>
          ) : null}
          {d.activities.length ? <Table caption="School activity attendance" head={["Activity", "Date", "Attendance"]} rows={d.activities.map((a: Row) => [a.title, formatDate(a.scheduled_at, false, SCHOOL_TIME_ZONE), a.present ? "Present" : "Absent"])} /> : null}
          {d.skill_sessions.length ? <Table caption="Skills session attendance" head={["Skills batch", "Sessions attended"]} rows={d.skill_sessions.map((s: Row) => [s.batch_title, `${s.present} of ${s.marked}`])} /> : null}
        </Card>
      );
    }
```

One text node, so the test's exact `getByText("Last 2 marked days: 1 present · 1 late · 0 absent · 0 excused")` matches.

- [ ] **Step 5: Run the tests and every suite that renders these components**

Run: `npx vitest run tests/components/SchoolChildOverview.attendance.test.tsx tests/components/Student360Panels.test.tsx tests/components/SchoolChildOverview.career.test.tsx tests/components/SchoolChildOverview.skills.test.tsx tests/components/SchoolChildOverview.psychometric.test.tsx tests/components/Student360Tabs.test.tsx tests/components/Student360Page.test.tsx tests/components/SchoolDailyAttendance.test.tsx tests/lib/clientBoundary.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/SchoolChildOverview.tsx apps/web/components/Student360Panels.tsx apps/web/tests/components/SchoolChildOverview.attendance.test.tsx apps/web/tests/components/Student360Panels.test.tsx
git commit -m "feat(enh-030): daily attendance on the parent card and the 360 Attendance tab"
```

---

### Task 8: Playwright end-to-end

**Files:**
- Create: `apps/web/tests/e2e/enh-030-daily-attendance.spec.ts`

**Interfaces:**
- Consumes: the whole stack; `createAndActivate`, `E2E_PASSWORD` (`tests/e2e/helpers/welcome.ts`); seed admin `overseasadmin@edusphere.local` / `Demo@123`.

- [ ] **Step 1: Write the spec**

```ts
import { expect, request as playwrightRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ENH-030 -- daily class attendance (docs/superpowers/specs/2026-09-30-enh-030-daily-attendance-design.md, AC01, AC08, AC09, AC12).
// Setup is API-only (the enh-013 pattern): a throwaway school, an assigned teacher, two students (one with a linked parent). The
// feature -- marking the class, then reading it as the parent and in the 360 view -- is driven through the real UI.

const INVITE_PASSWORD = "Sup3r-Secret-Pass!";
const unique = Date.now();
const email = (who: string) => `enh030-e2e-${who}-${unique}@example.local`;
const ctx = { studentId: "" };
const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";

async function apiAs(address: string, password: string): Promise<APIRequestContext> {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post("/api/v1/auth/login", { data: { email: address, password, division: "overseas" } });
  if (!res.ok()) throw new Error(`login ${address}: ${res.status()} ${await res.text()}`);
  return api;
}

async function acceptInvite(token: string) {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post(`/api/v1/school/invites/${token}/accept`, { data: { password: INVITE_PASSWORD } });
  if (!res.ok()) throw new Error(`accept invite: ${res.status()} ${await res.text()}`);
  await api.dispose();
}

async function signIn(page: Page, address: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/overseas/login");
  await page.fill("#login-email", address);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test.describe.serial("ENH-030 daily class attendance", () => {
  test.beforeAll(async () => {
    test.setTimeout(120_000);
    const admin = await apiAs("overseasadmin@edusphere.local", "Demo@123");
    await createAndActivate(admin, "/api/v1/overseas-admin/schools", { name: `E2E Attendance School ${unique}`, coordinator_full_name: "E2E Att Coordinator", coordinator_email: email("coord") });
    await admin.dispose();
    const coord = await apiAs(email("coord"), E2E_PASSWORD);
    const invite = await coord.post("/api/v1/school/team/invites", { data: { role: "school_teacher", full_name: "E2E Att Teacher", email: email("teacher") } });
    await acceptInvite((await invite.json()).development_invite_token);
    const first = await coord.post("/api/v1/school/students", { data: { full_name: "Asha Attend", grade_or_class: "Grade 5", assigned_teacher_email: email("teacher"), parent_name: "E2E Att Parent", parent_email: email("parent") } });
    expect(first.status()).toBe(201);
    const student = await first.json();
    ctx.studentId = student.id;
    const second = await coord.post("/api/v1/school/students", { data: { full_name: "Ben Attend", grade_or_class: "Grade 5", assigned_teacher_email: email("teacher") } });
    expect(second.status()).toBe(201);
    await coord.dispose();
    await acceptInvite(student.development_invite_token);
  });

  test("the teacher marks the whole class with one Save (AC01, AC12)", async ({ page }) => {
    await signIn(page, email("teacher"), INVITE_PASSWORD, "/school/teacher/dashboard");
    await page.getByRole("link", { name: "Attendance" }).first().click();
    await page.waitForURL("**/school/teacher/attendance");
    await expect(page.getByRole("heading", { level: 1, name: "Attendance" })).toBeVisible();
    await expect(page.getByRole("group")).toHaveCount(2);
    await page.getByRole("button", { name: "Mark all present" }).click();
    await page.getByRole("group", { name: /Ben Attend/ }).getByLabel("Absent").check();
    await page.getByRole("button", { name: "Save attendance" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Attendance saved for 2 students" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("group", { name: /Ben Attend/ }).getByLabel("Absent")).toBeChecked();
    await expect(page.getByRole("group", { name: /Asha Attend/ }).getByLabel("Present")).toBeChecked();
  });

  test("the attendance page fits a phone (AC12)", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await signIn(page, email("teacher"), INVITE_PASSWORD, "/school/teacher/dashboard");
    await page.goto("/school/teacher/attendance");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("the parent sees it on the dashboard card (AC08)", async ({ page }) => {
    await signIn(page, email("parent"), INVITE_PASSWORD, "/school/parent/dashboard");
    await expect(page.getByText("Attendance (last 1 marked day)")).toBeVisible();
    await expect(page.getByText("1 present · 0 late · 0 absent · 0 excused")).toBeVisible();
  });

  test("the 360 Attendance tab shows the day and no longer says 'not tracked' (AC09)", async ({ page }) => {
    await signIn(page, email("teacher"), INVITE_PASSWORD, "/school/teacher/dashboard");
    await page.goto(`/school/teacher/students/${ctx.studentId}/360`);
    await page.getByRole("tab", { name: /^Attendance/ }).click();
    const panel = page.getByRole("tabpanel");
    await expect(panel.getByRole("table", { name: "Daily attendance" })).toContainText("Present");
    await expect(panel).not.toContainText("not tracked yet (ENH-030)");
  });
});
```

- [ ] **Step 2: Rebuild the stack and run it**

Run (repo root): `docker compose build api web && docker compose up -d --force-recreate api worker beat web`, then in `apps/web`: `npx playwright test tests/e2e/enh-030-daily-attendance.spec.ts --workers=1`
Expected: 4 passed.

- [ ] **Step 3: Run the neighbouring specs that touch these screens**

Run: `npx playwright test tests/e2e/enh-013-student-360.spec.ts tests/e2e/sch-001-school-portal-access.spec.ts tests/e2e/sch-007-parent-portal.spec.ts tests/e2e/sch-reports.spec.ts --workers=1`
Expected: all pass (the AC-04 empty-text check still matches `^(No |Not enrolled)`).

- [ ] **Step 4: Commit**

```bash
git add apps/web/tests/e2e/enh-030-daily-attendance.spec.ts
git commit -m "test(enh-030): end-to-end teacher mark, parent card and 360 tab"
```

---

### Task 9: Full gates, traceability and docs

**Files:**
- Modify: `docs/delivery/ENHANCEMENT_BACKLOG.md` (§ENH-030: status line + link to spec/plan)
- Modify: `docs/features/MASTER_FEATURE_CATALOG.md` (ENH-030 entry: implementation status, ACs → tests)
- Modify: `docs/quality/RTM.md` (ENH-030 rows: AC01–AC13 → test files)
- Modify: `docs/ux/SCREEN_CATALOG.md:2544` (drop ENH-030 from the "not tracked yet" list; add the teacher Attendance screen)
- Modify: `docs/architecture/DATA_MODEL.md` (new `school_attendance_records` section)

- [ ] **Step 1: Backend gates** (in `apps/api`)

Run: `python -m ruff check .` then `python -m pytest -q`
Expected: ruff clean; full suite green. Any failure outside `test_enh_030_*`: stop and diagnose (superpowers:systematic-debugging) — do not edit an existing test to pass except the planned `test_enh_027_migration.py` relaxation.

- [ ] **Step 2: Frontend gates** (in `apps/web`)

Run: `npm run lint && npm run typecheck && npm test && npm run build`
Expected: all green; the build proves the client/server module boundary (Task 7 Step 3 note).

- [ ] **Step 3: Docs** — update the five files above: the backlog item's status "Slice 1 implemented (spec/plan links)"; RTM rows mapping AC01 → `test_enh_030_mark.py::test_teacher_marks_whole_class_in_one_call` + e2e, AC02 → `…remark…`, AC03 → `…outside_the_class…`, AC04 → `…only_teachers…`, AC05 → `…future_date…`, `…invalid_bodies…`, `test_enh_030_schemas.py`, AC06 → `…expired_partnership…`, AC07 → `…audit_row…`, AC08 → `test_enh_030_reads.py::test_overview…` + `SchoolChildOverview.attendance.test.tsx` + e2e, AC09 → `…360…` + `Student360Panels.test.tsx` + e2e, AC10 → `…after_transfer…`, AC11 → `…dashboard_and_reports…`, AC12 → `SchoolDailyAttendance.test.tsx` + e2e phone test, AC13 → `test_enh_030_migration.py`.

- [ ] **Step 4: Commit**

```bash
git add docs
git commit -m "docs(enh-030): traceability, data model and screen catalog"
```

- [ ] **Step 5: Browser QA** — with the stack up, sign in as the teacher at desktop and 320 px; check keyboard-only marking (Tab/arrow keys through radio groups, Space to select), the unsaved-changes prompt on a sidebar link, the loading skeleton, and the future-date message via `?date=2099-01-01`. Record findings in the spec's QA section (the ENH-015 "final browser verification" precedent) before calling the feature complete.
