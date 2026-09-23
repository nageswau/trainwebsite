# ENH-025 Student Master Field Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 10 missing Student Master value fields + Photo to `SchoolStudent`, settable by single edit and bulk upload (Photo: single edit only), with `section` split out of `grade_or_class`, without changing any existing behavior.

**Architecture:** New nullable columns on `school_students` (+3 on the grade-history ledger) via one additive migration with a conservative `section` backfill. One Pydantic boundary model (`StudentMasterFields`, subset `CareerPreferencesUpdate`) validates the new keys on every write path; one helper applies them. Photo and counselor routes live in a new router module (`school_student_profile.py`) that reuses `schools.py`'s scope loaders, like `portfolio.py` does. Frontend reuses existing classes; two shared modules remove duplication (`lib/schoolStudents.ts`, `SchoolStudentFields.tsx`).

**Tech Stack:** FastAPI + SQLAlchemy 2.0.54 async + Alembic + PostgreSQL 16; Pydantic v2; pytest + pytest-asyncio + httpx; Next.js (App Router) + React + vitest + Testing Library; Playwright.

**Spec:** `docs/superpowers/specs/2026-09-23-enh-025-student-master-fields-design.md` (read it with this plan).

## Global Constraints

- No new dependencies (backend or frontend). No image library.
- Additive only: every existing request key, response key, error message, route and CSV column position unchanged.
- `grade_or_class` is never written by the migration and its behavior is unchanged everywhere.
- All new columns nullable; empty string / empty list stored as NULL.
- Genders exactly: `female`, `male`, `other`, `prefer_not_to_say`.
- Limits: `section` 20, `roll_number` 20, `student_mobile` 20 (`^[0-9+\-() ]{7,20}$`, ≥7 digits), `city` 120, list ≤20 items × ≤80 chars, photo ≤2 MB (2 * 1024 * 1024 bytes), JPEG/PNG only.
- Uniqueness index name: `uq_school_students_roll` on `(school_id, academic_year_id, grade_level, lower(section), roll_number) NULLS NOT DISTINCT WHERE roll_number IS NOT NULL`.
- Errors: FastAPI `{"detail": "<string>"}`; new 422 messages name the field and never echo the value (except `roll_number` in the 409).
- `photo_key` / `photo_content_type` never serialized, never logged.
- Audit metadata carries field names only, never values.
- Revision `0039_student_master_fields`, `down_revision = "0038_portfolio"` (renumber on merge if ENH-013 lands first).
- Decision ID `DEC-SCOPE-027` (renumber on merge if taken).
- Tests run against the local Postgres the user starts (`docker compose` is the user's — never start/stop it). Apply migrations with `cd apps/api && alembic upgrade head` before backend tests.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- pytest runs with `asyncio_mode = "strict"` (`apps/api/pyproject.toml:3`): **every** `async def test_…` in this
  plan needs `@pytest.mark.asyncio` (the code blocks below omit it for brevity — add it to each), and every
  async fixture uses `@pytest_asyncio.fixture` instead of `@pytest.fixture`.

**Spec clarification (applied in this plan):** on `POST`/`PATCH /school/students`, unknown top-level keys such as `academic_year_id`, `school_id`, `photo_key` are **ignored, not rejected** — that is today's behavior for those handlers and changing it to 422 would break AC7. They are never applied (tested). The counselor route validates its whole body with `extra="forbid"` → 422. JPEG APP2 (ICC colour profile) and APP14 (Adobe colour transform) segments are **kept** (they carry no personal data and dropping them can mis-colour images); APP1, APP3–APP13, APP15 and COM are dropped.

## Review Focus

1. A coordinator saves the edit form without touching the new fields → existing values must not be wiped (edit form sends every field; the panel must pre-fill every new input from the student). Test in Task 10.
2. A bulk CSV saved by Excel with a trailing empty column or short rows → missing cells mean "not set", not an error. Test in Task 4.
3. A roll-number clash inside the same CSV (row 2 and row 5 both roll `7`, same section) → row 5 rejected, rows 1–4 kept. Test in Task 4.
4. Uploading a replacement photo while the old file is missing on disk → upload still succeeds; no 500. Test in Task 7.
5. A teacher whose assignment was removed still has the photo URL in browser history → 403, never the image. Test in Task 7.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/app/models.py` (modify) | new `SchoolStudent` columns + index + check; grade-history columns |
| `apps/api/alembic/versions/0039_student_master_fields.py` (create) | additive migration, `section` backfill |
| `apps/api/app/schemas.py` (modify) | `StudentMasterFields`, `CareerPreferencesUpdate`, `validation_message`, grade-history state fields |
| `apps/api/app/api/schools.py` (modify) | `_student_out`, create/update/bulk/template, promotion side effect, grade-history output, shared helpers |
| `apps/api/app/api/school_transfers.py` (modify, 1 line) | clear `section`/`roll_number` on approval |
| `apps/api/app/services/image_metadata.py` (create) | `detect_image_type`, `strip_metadata` (pure functions) |
| `apps/api/app/services/storage.py` (modify) | `read_bytes`, `delete` with root guard |
| `apps/api/app/api/school_student_profile.py` (create) | photo PUT/GET/DELETE, career-preferences GET/PATCH |
| `apps/api/app/main.py` (modify) | register the new router |
| `apps/api/tests/enh025_helpers.py` (create) | JPEG/PNG byte builders; reuses `enh005_helpers` for schools/users |
| `apps/api/tests/test_enh_025_*.py` (create) | backend tests per task |
| `apps/web/lib/schoolStudents.ts` (create) | shared type, options, payload builder, column reference data |
| `apps/web/components/SchoolStudentFields.tsx` (create) | grouped inputs shared by create/edit |
| `apps/web/components/SchoolStudentPhoto.tsx` (create) | photo display + coordinator controls |
| `apps/web/components/CareerPreferencesCard.tsx` (create) | counselor career-preferences card |
| `apps/web/components/SchoolStudentsPanel.tsx`, `SchoolStudentDetailPanel.tsx`, `SchoolChildOverview.tsx`, `SchoolGradeHistory.tsx`, `SchoolCareerRecordsPanel.tsx`, `SchoolBulkUploadPanel.tsx` (modify) | UI wiring |
| `apps/web/app/school/coordinator/students/[id]/page.tsx` (modify) | pass `canEditPhoto` |
| `apps/web/app/globals.css` (modify) | `fieldset.form-section`, `.student-photo` |
| `apps/web/tests/components/*.test.tsx`, `apps/web/tests/e2e/enh-025-student-master-fields.spec.ts` | frontend tests |
| docs: `PRODUCT_DECISION_REGISTER.md`, `ENHANCEMENT_BACKLOG.md`, `API_CONTRACT.md`, `DATA_MODEL.md`, `RTM.md` | records |

---

### Task 1: Decision record and backlog correction

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append after the last `DEC-SCOPE-026` entry)
- Modify: `docs/delivery/ENHANCEMENT_BACKLOG.md` (ENH-025 entry, "Existing behavior" paragraph)

**Interfaces:** Produces the ID `DEC-SCOPE-027` cited in code comments by later tasks.

- [ ] **Step 1: Append the decision**

```markdown
### DEC-SCOPE-027 — Student Master field coverage (ENH-025)

**Status:** `EXPLICIT_APPROVAL` — user, in-session, 2026-09-23 (brainstorming answers, recorded in
`docs/superpowers/specs/2026-09-23-enh-025-student-master-fields-design.md` §9).
**Evidence:** `EVID-014` (`docs/sources/School CRM.md:118-177`); `ENHANCEMENT_BACKLOG.md` `ENH-025`.
**Decisions:**
1. `grade_or_class` kept unchanged; new `section` column; ENH-001's `grade_level` is the Grade column.
2. Career interests, Global education interest, Preferred countries, Preferred courses on `SchoolStudent`;
   written by the School Coordinator (all paths) and the Career Counsellor (own portfolio, dedicated route).
3. Photo via authorized upload/stream endpoints; excluded from bulk upload.
4. Gender fixed list (`female`, `male`, `other`, `prefer_not_to_say`); multi-value fields as JSON string
   lists; Global education interest nullable boolean.
5. Roll number unique per school + academic year + grade + section (blank values form a group).
6. Any academic-year move (promote or hold back) clears roll number; grade history records previous
   section/roll number and new section.
7. Transfer approval clears section and roll number.
8. All new fields optional.
9. Photo metadata (EXIF etc.) stripped in pure Python before storage.
**`NEEDS_CONFIRMATION`:** consent / legal basis for storing photos of minors (client).
**New Feature ID:** none — additive scope on `ENH-025`.
```

- [ ] **Step 2: Correct the backlog's stale model description**

In the ENH-025 "Existing behavior" paragraph, after the list of stored columns, add:
`**Correction (2026-09-23, ENH-025 design):** ENH-001 has since added academic_year_id and grade_level
(models.py:1030-1031); the Grade/Section split therefore reduces to adding section. See DEC-SCOPE-027.`

- [ ] **Step 3: Commit**

```bash
git add docs/decisions/PRODUCT_DECISION_REGISTER.md docs/delivery/ENHANCEMENT_BACKLOG.md
git commit -m "docs(enh-025): record DEC-SCOPE-027 and correct the backlog's model description"
```

---

### Task 2: Model columns and migration 0039

**Files:**
- Modify: `apps/api/app/models.py:992-1031` (`SchoolStudent`), `SchoolStudentGradeHistory` (after its `to_grade_or_class`)
- Create: `apps/api/alembic/versions/0039_student_master_fields.py`
- Test: `apps/api/tests/test_enh_025_migration.py`

**Interfaces:**
- Produces: `SchoolStudent.section|roll_number|gender|student_mobile|city|photo_key|photo_content_type: str | None`, `subjects|career_interests|preferred_countries|preferred_courses: list | None`, `global_education_interest: bool | None`; `SchoolStudentGradeHistory.from_section|from_roll_number|to_section: str | None`; constant `models.GENDERS: tuple[str, ...]`; migration function `_derive_section(label: str | None) -> str | None`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-025 -- migration 0039 and the new SchoolStudent columns (spec §2)."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text

from app.models import SchoolStudent
from tests.enh005_helpers import mk_school

_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0039_student_master_fields.py"
_spec = importlib.util.spec_from_file_location("_enh_025_migration_0039", _path)
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("10-A", "A"), ("Grade 8-A", "A"), ("Class 7 Section C", "C"), ("9B", "B"), ("9b", "b"),
        ("Grade 10 - b", "b"), ("Grade 5 AB", "AB"), ("Grade 6/C", "C"),
        ("Grade 5", None), ("Nursery", None), ("Grade 12", None), ("10th", None), ("2nd", None),
        ("Grade 8 Science", None), ("", None), (None, None), ("   ", None),
    ],
)
def test_derive_section_is_conservative(label, expected):
    assert _migration._derive_section(label) == expected


def test_migration_revises_portfolio_and_is_the_single_head():
    assert _migration.revision == "0039_student_master_fields"
    assert _migration.down_revision == "0038_portfolio"
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    down = {}
    for file in versions.glob("*.py"):
        body = file.read_text(encoding="utf-8")
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in body.splitlines() if line.startswith("revision =")), None)
        parent = next((line.split("=", 1)[1].strip().strip("\"'") for line in body.splitlines() if line.startswith("down_revision =")), None)
        if rev:
            down[rev] = parent
    heads = set(down) - set(down.values())
    assert heads == {"0039_student_master_fields"}


@pytest.mark.asyncio
async def test_new_columns_exist_and_are_nullable(db_session):
    def _cols(sync_conn):
        insp = inspect(sync_conn)
        return {c["name"]: c for c in insp.get_columns("school_students")}, {c["name"] for c in insp.get_columns("school_student_grade_history")}, {i["name"] for i in insp.get_indexes("school_students")}

    conn = await db_session.connection()
    cols, history_cols, indexes = await conn.run_sync(_cols)
    for name in ("section", "roll_number", "gender", "student_mobile", "city", "subjects", "career_interests", "preferred_countries", "preferred_courses", "global_education_interest", "photo_key", "photo_content_type"):
        assert name in cols and cols[name]["nullable"], name
    assert {"from_section", "from_roll_number", "to_section"} <= history_cols
    assert "uq_school_students_roll" in indexes


@pytest.mark.asyncio
async def test_grade_level_and_section_are_independently_queryable(db_session):
    world = await mk_school(db_session, label="Q", students=3)
    a, b, c = world["students"]
    a.grade_level, a.section = 8, "A"
    b.grade_level, b.section = 8, "B"
    c.grade_level, c.section = 9, "A"
    await db_session.commit()
    ids = {s.id for s in world["students"]}
    by_grade = set((await db_session.scalars(select(SchoolStudent.id).where(SchoolStudent.id.in_(ids), SchoolStudent.grade_level == 8))).all())
    by_section = set((await db_session.scalars(select(SchoolStudent.id).where(SchoolStudent.id.in_(ids), SchoolStudent.section == "A"))).all())
    assert by_grade == {a.id, b.id}
    assert by_section == {a.id, c.id}


@pytest.mark.asyncio
async def test_gender_check_constraint_rejects_unknown_values(db_session):
    world = await mk_school(db_session, label="G", students=1)
    with pytest.raises(Exception):
        await db_session.execute(text("UPDATE school_students SET gender = 'unknown' WHERE id = :id"), {"id": world["students"][0].id})
        await db_session.flush()
    await db_session.rollback()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_025_migration.py -v`
Expected: FAIL at collection — `FileNotFoundError` for `0039_student_master_fields.py`.

- [ ] **Step 3: Add the model columns**

In `models.py`, near the top-level constants, add `GENDERS = ("female", "male", "other", "prefer_not_to_say")`. Make sure `func` is imported from `sqlalchemy` (add to the existing import if absent). In `SchoolStudent`, add `__table_args__` and the columns after `grade_level`:

```python
    __table_args__ = (
        # ENH-025 (DEC-SCOPE-027): a roll number is unique within school + academic year + grade + section.
        # NULLS NOT DISTINCT makes a blank section/grade/year its own group; students with no roll number are
        # never constrained. lower(section) so "A" and "a" are the same section.
        Index(
            "uq_school_students_roll",
            "school_id", "academic_year_id", "grade_level", func.lower(text("section")), "roll_number",
            unique=True, postgresql_where=text("roll_number IS NOT NULL"), postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("gender IS NULL OR gender IN ('female', 'male', 'other', 'prefer_not_to_say')", name="ck_school_students_gender"),
    )
```

```python
    # ENH-025 (DEC-SCOPE-027): School CRM.md §3 Student Master fields. All optional; validated at the API
    # boundary by schemas.StudentMasterFields. grade_or_class stays the free-text display label.
    section: Mapped[str | None] = mapped_column(String(20), nullable=True)
    roll_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    student_mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    subjects: Mapped[list | None] = mapped_column(JSON, nullable=True)
    career_interests: Mapped[list | None] = mapped_column(JSON, nullable=True)
    global_education_interest: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    preferred_countries: Mapped[list | None] = mapped_column(JSON, nullable=True)
    preferred_courses: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Internal only -- never serialized or logged (spec §5: in local storage mode the random key is the barrier).
    photo_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    photo_content_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
```

In `SchoolStudentGradeHistory`, after `to_grade_or_class`:

```python
    # ENH-025: previous class details survive roll-number clearing on a year move (DEC-SCOPE-027 item 6).
    from_section: Mapped[str | None] = mapped_column(String(20), nullable=True)
    from_roll_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_section: Mapped[str | None] = mapped_column(String(20), nullable=True)
```

- [ ] **Step 4: Write the migration**

```python
"""ENH-025 -- Student Master fields on school_students, class details on the grade-history ledger.

Revision ID: 0039_student_master_fields
Revises: 0038_portfolio

docs/superpowers/specs/2026-09-23-enh-025-student-master-fields-design.md §2 (DEC-SCOPE-027). Additive only:
nullable columns, a CHECK on gender, a partial unique index on roll numbers, and a backfill of `section`
from `grade_or_class` where the label unambiguously ends in a section letter. `grade_or_class` is read,
never written. Unparseable labels leave `section` NULL (never guessed) and their student codes are printed,
same as 0030. `downgrade()` drops everything this adds.
"""

import re

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0039_student_master_fields"
down_revision = "0038_portfolio"
branch_labels = None
depends_on = None

STUDENT_COLUMNS = (
    ("section", sa.String(20)), ("roll_number", sa.String(20)), ("gender", sa.String(20)),
    ("student_mobile", sa.String(20)), ("city", sa.String(120)),
    ("subjects", postgresql.JSON()), ("career_interests", postgresql.JSON()),
    ("global_education_interest", sa.Boolean()),
    ("preferred_countries", postgresql.JSON()), ("preferred_courses", postgresql.JSON()),
    ("photo_key", sa.String(200)), ("photo_content_type", sa.String(40)),
)
HISTORY_COLUMNS = (("from_section", sa.String(20)), ("from_roll_number", sa.String(20)), ("to_section", sa.String(20)))

# A grade number, then an optional separator (-, /, space) or the word "section", then 1-2 letters that end
# the label: "10-A", "Grade 8-A", "Class 7 Section C", "9B". Ordinal suffixes ("10th") are not sections.
_SECTION = re.compile(r"\d{1,2}\s*(?:section\s+|[-/]\s*|\s+)?([a-z]{1,2})\s*$", re.IGNORECASE)
_ORDINALS = {"st", "nd", "rd", "th"}


def _derive_section(label: str | None) -> str | None:
    if not label or not label.strip():
        return None
    match = _SECTION.search(label.strip())
    if not match or match.group(1).lower() in _ORDINALS:
        return None
    return match.group(1)


def upgrade() -> None:
    bind = op.get_bind()
    offline = op.get_context().as_sql
    existing = set() if offline else {c["name"] for c in sa.inspect(bind).get_columns("school_students")}
    for name, type_ in STUDENT_COLUMNS:
        if name not in existing:
            op.add_column("school_students", sa.Column(name, type_, nullable=True))
    existing_history = set() if offline else {c["name"] for c in sa.inspect(bind).get_columns("school_student_grade_history")}
    for name, type_ in HISTORY_COLUMNS:
        if name not in existing_history:
            op.add_column("school_student_grade_history", sa.Column(name, type_, nullable=True))
    op.create_check_constraint("ck_school_students_gender", "school_students", "gender IS NULL OR gender IN ('female', 'male', 'other', 'prefer_not_to_say')")

    if not offline:
        rows = bind.execute(sa.text("SELECT id, student_code, grade_or_class FROM school_students WHERE section IS NULL AND grade_or_class IS NOT NULL")).fetchall()
        unparsed = []
        for row_id, student_code, label in rows:
            section = _derive_section(label)
            if section is None:
                unparsed.append(student_code)
                continue
            bind.execute(sa.text("UPDATE school_students SET section = :section WHERE id = :id"), {"section": section, "id": row_id})
        if unparsed:
            print(f"[0039_student_master_fields] {len(unparsed)} school_students row(s) had no parseable section in grade_or_class -- section left NULL: {', '.join(unparsed)}")

    op.execute(
        "CREATE UNIQUE INDEX uq_school_students_roll ON school_students "
        "(school_id, academic_year_id, grade_level, lower(section), roll_number) NULLS NOT DISTINCT "
        "WHERE roll_number IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_school_students_roll")
    op.drop_constraint("ck_school_students_gender", "school_students", type_="check")
    for name, _ in HISTORY_COLUMNS:
        op.drop_column("school_student_grade_history", name)
    for name, _ in STUDENT_COLUMNS:
        op.drop_column("school_students", name)
```

- [ ] **Step 5: Apply and prove the round trip keeps `grade_or_class`**

Fingerprint query (run before and after; results must be identical):
`SELECT md5(string_agg(id::text || coalesce(grade_or_class, '~'), ',' ORDER BY id)) FROM school_students`

Run it through a short script in the session scratchpad (not `/tmp`) using the app's own engine
(`from app.core.database import engine`), then:
```bash
cd apps/api && alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```
and run the fingerprint again. Record both fingerprints and the migration's backfill print output in the
task report.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_enh_025_migration.py -v`
Expected: all PASS.

- [ ] **Step 7: Refactor check** — no duplication between model and migration beyond the unavoidable DDL; rerun the test file.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/models.py apps/api/alembic/versions/0039_student_master_fields.py apps/api/tests/test_enh_025_migration.py
git commit -m "feat(enh-025): student master columns, roll-number index and section backfill (0039)"
```

---

### Task 3: Boundary validation models

**Files:**
- Modify: `apps/api/app/schemas.py` (after the ENH-004 block, ~line 600)
- Test: `apps/api/tests/test_enh_025_schemas.py`

**Interfaces:**
- Consumes: `models.GENDERS`.
- Produces: `StudentMasterFields(BaseModel)`, `CareerPreferencesUpdate(BaseModel)`, `MASTER_FIELD_KEYS: tuple[str, ...]`, `CAREER_PREFERENCE_KEYS: tuple[str, ...]`, `LIST_FIELD_KEYS: tuple[str, ...]`, `validation_message(exc: ValidationError) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-025 -- StudentMasterFields / CareerPreferencesUpdate boundary rules (spec §2.1, §3.2)."""

import pytest
from pydantic import ValidationError

from app.schemas import CAREER_PREFERENCE_KEYS, MASTER_FIELD_KEYS, CareerPreferencesUpdate, StudentMasterFields, validation_message


def _msg(model, data):
    with pytest.raises(ValidationError) as exc:
        model.model_validate(data)
    return validation_message(exc.value)


def test_keys_are_the_ten_value_fields():
    assert set(MASTER_FIELD_KEYS) == {"section", "roll_number", "gender", "student_mobile", "city", "subjects", "career_interests", "global_education_interest", "preferred_countries", "preferred_courses"}
    assert set(CAREER_PREFERENCE_KEYS) == {"career_interests", "global_education_interest", "preferred_countries", "preferred_courses"}


def test_text_is_trimmed_and_empty_becomes_none():
    f = StudentMasterFields.model_validate({"city": "  Pune ", "section": "", "roll_number": "   "})
    assert (f.city, f.section, f.roll_number) == ("Pune", None, None)
    assert f.model_fields_set == {"city", "section", "roll_number"}


@pytest.mark.parametrize("value", ["female", "Male", " OTHER ", "prefer_not_to_say"])
def test_gender_accepts_the_fixed_list_case_insensitively(value):
    assert StudentMasterFields.model_validate({"gender": value}).gender == value.strip().lower()


def test_gender_rejects_other_values_without_echoing_them():
    msg = _msg(StudentMasterFields, {"gender": "robot"})
    assert msg == "gender must be one of: female, male, other, prefer_not_to_say"


@pytest.mark.parametrize("value", ["+91 98765 43210", "(020) 1234-567", "9876543210"])
def test_mobile_accepts_phone_shapes(value):
    assert StudentMasterFields.model_validate({"student_mobile": value}).student_mobile == value


@pytest.mark.parametrize("value", ["12345", "call me", "+++---()()", "1" * 21])
def test_mobile_rejects_bad_values_without_echoing_them(value):
    msg = _msg(StudentMasterFields, {"student_mobile": value})
    assert msg.startswith("student_mobile ")
    assert value not in msg


def test_lists_trim_dedupe_case_insensitively_and_empty_becomes_none():
    f = StudentMasterFields.model_validate({"subjects": [" Maths", "maths", "Physics", ""], "preferred_courses": []})
    assert f.subjects == ["Maths", "Physics"]
    assert f.preferred_courses is None


def test_list_limits():
    assert _msg(StudentMasterFields, {"subjects": [f"S{i}" for i in range(21)]}) == "subjects must have at most 20 items"
    assert _msg(StudentMasterFields, {"subjects": ["x" * 81]}) == "subjects items must be at most 80 characters"
    assert _msg(StudentMasterFields, {"subjects": "Maths"}) == "subjects must be a list of text values"


def test_length_limits():
    assert _msg(StudentMasterFields, {"section": "x" * 21}) == "section must be at most 20 characters"
    assert _msg(StudentMasterFields, {"city": "x" * 121}) == "city must be at most 120 characters"


@pytest.mark.parametrize("value", ["A\x00", "Pune\n", "A‮B", "B⁦"])
def test_control_and_bidi_characters_rejected(value):
    assert _msg(StudentMasterFields, {"city": value}) == "city must not contain control or bidirectional-override characters"


def test_zero_width_joiner_is_allowed_for_indic_names():
    assert StudentMasterFields.model_validate({"city": "ತುಮ‍ಕೂರು"}).city == "ತುಮ‍ಕೂರು"


def test_global_interest_is_strict_boolean():
    assert StudentMasterFields.model_validate({"global_education_interest": False}).global_education_interest is False
    assert _msg(StudentMasterFields, {"global_education_interest": "yes"}).startswith("global_education_interest ")


def test_unknown_keys_rejected():
    assert _msg(StudentMasterFields, {"photo_key": "x"}) == "photo_key is not an accepted field"
    assert _msg(CareerPreferencesUpdate, {"roll_number": "7"}) == "roll_number is not an accepted field"


def test_career_update_accepts_only_its_four_fields():
    f = CareerPreferencesUpdate.model_validate({"career_interests": ["Engineering"], "global_education_interest": True})
    assert f.career_interests == ["Engineering"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_025_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'CAREER_PREFERENCE_KEYS'`.

- [ ] **Step 3: Implement**

Add `import re` and `StrictBool` (from `pydantic`) to the existing imports in `schemas.py`, and `from app.models import GENDERS` if `schemas.py` does not already import from models (if it does, extend that import). Then:

```python
# --- ENH-025: Student Master fields (docs/superpowers/specs/2026-09-23-enh-025-student-master-fields-design.md §2.1) ---

_BIDI_OVERRIDES = {chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))}
_MOBILE = re.compile(r"^[0-9+\-() ]{7,20}$")
LIST_MAX_ITEMS = 20
LIST_ITEM_MAX_LENGTH = 80


def _clean_text(value, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("must be text")
    value = value.strip()
    if not value:
        return None
    if len(value) > max_length:
        raise ValueError(f"must be at most {max_length} characters")
    # Cc (NUL, newlines, ...) and explicit bidi overrides only -- not all of Cf, because zero-width joiners are
    # legitimate inside Indic names.
    if any(unicodedata.category(ch) == "Cc" or ch in _BIDI_OVERRIDES for ch in value):
        raise ValueError("must not contain control or bidirectional-override characters")
    return value


def _clean_list(value) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("must be a list of text values")
    if len(value) > LIST_MAX_ITEMS:
        raise ValueError(f"must have at most {LIST_MAX_ITEMS} items")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        try:
            text_ = _clean_text(item, LIST_ITEM_MAX_LENGTH)
        except ValueError as exc:
            raise ValueError(f"items {exc}") from None
        if text_ is None or text_.casefold() in seen:
            continue
        seen.add(text_.casefold())
        cleaned.append(text_)
    return cleaned or None


class CareerPreferencesUpdate(BaseModel):
    """The four career fields a Career Counsellor may write (DEC-SCOPE-027 item 2). extra="forbid": any other
    key is a 422, so the counsellor route cannot reach roll number, mobile, photo, school or year."""

    model_config = {"extra": "forbid"}
    career_interests: list[str] | None = None
    global_education_interest: StrictBool | None = None
    preferred_countries: list[str] | None = None
    preferred_courses: list[str] | None = None

    @field_validator("career_interests", "preferred_countries", "preferred_courses", mode="before")
    @classmethod
    def _lists(cls, value):
        return _clean_list(value)


class StudentMasterFields(CareerPreferencesUpdate):
    """All ten ENH-025 value fields, validated at the API boundary. Only keys the client sent are in
    model_fields_set, which gives PATCH its absent = unchanged / null = clear semantics."""

    section: str | None = None
    roll_number: str | None = None
    gender: str | None = None
    student_mobile: str | None = None
    city: str | None = None
    subjects: list[str] | None = None

    @field_validator("section", "roll_number", mode="before")
    @classmethod
    def _short_text(cls, value):
        return _clean_text(value, 20)

    @field_validator("city", mode="before")
    @classmethod
    def _city(cls, value):
        return _clean_text(value, 120)

    @field_validator("subjects", mode="before")
    @classmethod
    def _subjects(cls, value):
        return _clean_list(value)

    @field_validator("gender", mode="before")
    @classmethod
    def _gender(cls, value):
        value = _clean_text(value, 20)
        if value is None:
            return None
        if value.lower() not in GENDERS:
            raise ValueError(f"must be one of: {', '.join(GENDERS)}")
        return value.lower()

    @field_validator("student_mobile", mode="before")
    @classmethod
    def _mobile(cls, value):
        value = _clean_text(value, 20)
        if value is None:
            return None
        if not _MOBILE.match(value) or sum(ch.isdigit() for ch in value) < 7:
            raise ValueError("must be 7-20 characters of digits, spaces, +, -, ( or ) with at least 7 digits")
        return value


MASTER_FIELD_KEYS: tuple[str, ...] = (
    "section", "roll_number", "gender", "student_mobile", "city", "subjects",
    "career_interests", "global_education_interest", "preferred_countries", "preferred_courses",
)
CAREER_PREFERENCE_KEYS: tuple[str, ...] = tuple(CareerPreferencesUpdate.model_fields)
LIST_FIELD_KEYS: tuple[str, ...] = ("subjects", "career_interests", "preferred_countries", "preferred_courses")


def validation_message(exc: ValidationError) -> str:
    """First error as one '<field> <reason>' string, matching the existing handlers' HTTPException(422, str)
    shape. Never includes the submitted value (spec §5, sensitive logs)."""
    error = exc.errors()[0]
    field = ".".join(str(part) for part in error["loc"] if not isinstance(part, int)) or "request"
    if error["type"] == "extra_forbidden":
        return f"{field} is not an accepted field"
    reason = error["msg"].removeprefix("Value error, ")
    return f"{field} {reason[:1].lower()}{reason[1:]}"
```

Ensure `ValidationError` is imported from `pydantic` in `schemas.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_enh_025_schemas.py -v`
Expected: all PASS.

- [ ] **Step 5: Refactor** — confirm `MASTER_FIELD_KEYS` equals `tuple(StudentMasterFields.model_fields)` as a set (add `assert set(MASTER_FIELD_KEYS) == set(StudentMasterFields.model_fields)` to the first test); rerun.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/schemas.py apps/api/tests/test_enh_025_schemas.py
git commit -m "feat(enh-025): StudentMasterFields boundary validation"
```

---

### Task 4: Create / update / read with roll-number conflicts

**Files:**
- Modify: `apps/api/app/api/schools.py` — imports; `_student_out` (`:584`); `create_student` (`:1155`); `update_student` (`:1208`)
- Test: `apps/api/tests/test_enh_025_student_fields.py`

**Interfaces:**
- Consumes: Task 3 exports.
- Produces (in `schools.py`, imported by Task 7/8): `_master_fields_or_422(model: type[BaseModel], data: dict) -> BaseModel`; `_apply_master_fields(student: SchoolStudent, fields: BaseModel) -> list[str]`; `ROLL_CONSTRAINT = "uq_school_students_roll"`; `_is_roll_conflict(exc: IntegrityError) -> bool`; `ROLL_TAKEN: str` (format with `roll=`); `_flush_or_409(db: AsyncSession, roll_number: str | None) -> None`; `_master_subset(payload: dict) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-025 -- Student Master fields on POST/PATCH/GET /school/students (spec §3.3, §3.6, AC1/2/5/7)."""

import asyncio
import uuid

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, SchoolStudent
from tests.enh005_helpers import login, mk_school

STUDENTS = "/api/v1/school/students"
FULL = {
    "section": "A", "roll_number": "7", "gender": "female", "student_mobile": "+91 98765 43210", "city": "Pune",
    "subjects": ["Maths", "Physics"], "career_interests": ["Engineering"], "global_education_interest": True,
    "preferred_countries": ["Germany"], "preferred_courses": ["Mechanical Engineering"],
}
LEGACY_KEYS = {"id", "student_code", "full_name", "date_of_birth", "grade_or_class", "assigned_teacher_user_id", "pending_parent_email", "academic_year_id", "grade_level"}


@pytest.fixture
async def world(db_session):
    return await mk_school(db_session, label="F", students=1)


async def test_create_sets_every_field_and_response_is_additive(client, world):
    await login(client, world["coordinator"].email)
    r = await client.post(STUDENTS, json={"full_name": "Asha Rao", "grade_level": 8, **FULL})
    assert r.status_code == 201, r.text
    body = r.json()
    assert LEGACY_KEYS <= set(body)
    for key, value in FULL.items():
        assert body[key] == value, key
    assert body["has_photo"] is False
    assert "photo_key" not in body and "photo_content_type" not in body


async def test_legacy_payload_behaves_as_before(client, world):
    await login(client, world["coordinator"].email)
    r = await client.post(STUDENTS, json={"full_name": "Legacy Kid", "grade_or_class": "Grade 5", "grade_level": 5})
    assert r.status_code == 201
    body = r.json()
    assert body["grade_or_class"] == "Grade 5" and body["grade_level"] == 5
    assert all(body[key] is None for key in FULL)


async def test_patch_absent_keeps_null_clears_and_value_changes(client, world, db_session):
    await login(client, world["coordinator"].email)
    sid = world["students"][0].id
    assert (await client.patch(f"{STUDENTS}/{sid}", json=FULL)).status_code == 200
    r = await client.patch(f"{STUDENTS}/{sid}", json={"city": None, "subjects": [], "gender": "male"})
    assert r.status_code == 200
    body = r.json()
    assert body["city"] is None and body["subjects"] is None and body["gender"] == "male"
    assert body["section"] == "A" and body["preferred_countries"] == ["Germany"]


async def test_patch_ignores_system_keys(client, world, db_session):
    await login(client, world["coordinator"].email)
    student = world["students"][0]
    before_year = student.academic_year_id
    r = await client.patch(f"{STUDENTS}/{student.id}", json={"academic_year_id": str(uuid.uuid4()), "school_id": str(uuid.uuid4()), "photo_key": "x", "city": "Pune"})
    assert r.status_code == 200
    fresh = await db_session.get(SchoolStudent, student.id, populate_existing=True)
    assert fresh.academic_year_id == before_year and fresh.school_id == world["school"].id and fresh.photo_key is None and fresh.city == "Pune"


async def test_invalid_field_is_422_naming_the_field(client, world):
    await login(client, world["coordinator"].email)
    r = await client.post(STUDENTS, json={"full_name": "X", "gender": "robot"})
    assert r.status_code == 422
    assert r.json()["detail"] == "gender must be one of: female, male, other, prefer_not_to_say"


async def test_roll_clash_is_409_case_insensitive_section(client, world):
    await login(client, world["coordinator"].email)
    base = {"grade_level": 8, "roll_number": "12"}
    assert (await client.post(STUDENTS, json={"full_name": "One", "section": "A", **base})).status_code == 201
    r = await client.post(STUDENTS, json={"full_name": "Two", "section": "a", **base})
    assert r.status_code == 409
    assert r.json()["detail"] == "roll_number '12' is already used in this grade and section for this academic year"


async def test_blank_section_is_its_own_group(client, world):
    await login(client, world["coordinator"].email)
    assert (await client.post(STUDENTS, json={"full_name": "One", "grade_level": 5, "roll_number": "3"})).status_code == 201
    assert (await client.post(STUDENTS, json={"full_name": "Two", "grade_level": 5, "roll_number": "3"})).status_code == 409
    assert (await client.post(STUDENTS, json={"full_name": "Three", "grade_level": 5, "section": "B", "roll_number": "3"})).status_code == 201


async def test_students_without_roll_numbers_are_unconstrained(client, world):
    await login(client, world["coordinator"].email)
    for name in ("A", "B"):
        assert (await client.post(STUDENTS, json={"full_name": name, "grade_level": 6, "section": "C"})).status_code == 201


async def test_patch_into_a_taken_roll_is_409_and_nothing_changes(client, world, db_session):
    await login(client, world["coordinator"].email)
    await client.post(STUDENTS, json={"full_name": "Holder", "grade_level": 8, "section": "A", "roll_number": "9"})
    sid = world["students"][0].id
    r = await client.patch(f"{STUDENTS}/{sid}", json={"section": "A", "roll_number": "9", "city": "Goa"})
    assert r.status_code == 409
    fresh = await db_session.get(SchoolStudent, sid, populate_existing=True)
    assert fresh.roll_number is None and fresh.city is None


async def test_concurrent_creates_with_the_same_roll_yield_one_success(world):
    async def attempt(name):
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await login(c, world["coordinator"].email)
            return await c.post(STUDENTS, json={"full_name": name, "grade_level": 9, "section": "D", "roll_number": "1"})

    results = await asyncio.wait_for(asyncio.gather(attempt("P"), attempt("Q")), timeout=20)
    assert sorted(r.status_code for r in results) == [201, 409]


async def test_other_roles_cannot_write(client, world):
    for role in ("teacher", "principal", "parent"):
        await login(client, world[role].email)
        assert (await client.patch(f"{STUDENTS}/{world['students'][0].id}", json={"city": "X"})).status_code == 403


async def test_other_school_coordinator_cannot_write(client, db_session, world):
    other = await mk_school(db_session, label="O", students=0)
    await login(client, other["coordinator"].email)
    assert (await client.patch(f"{STUDENTS}/{world['students'][0].id}", json={"city": "X"})).status_code == 403


async def test_readers_see_new_fields_within_scope(client, world):
    await login(client, world["coordinator"].email)
    sid = world["students"][0].id
    await client.patch(f"{STUDENTS}/{sid}", json={"city": "Pune"})
    for role in ("principal", "teacher", "parent"):
        await login(client, world[role].email)
        r = await client.get(f"{STUDENTS}/{sid}")
        assert r.status_code == 200 and r.json()["city"] == "Pune", role


async def test_audit_records_field_names_not_values(client, world, db_session):
    await login(client, world["coordinator"].email)
    sid = world["students"][0].id
    await client.patch(f"{STUDENTS}/{sid}", json={"student_mobile": "+91 98765 43210", "city": "Pune"})
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.student_update", AuditLog.entity_id == str(sid)).order_by(AuditLog.created_at.desc()))
    assert row.metadata_json["changed_fields"] == ["city", "student_mobile"]
    assert "98765" not in str(row.metadata_json) and "Pune" not in str(row.metadata_json)
```

Add `pytestmark = pytest.mark.asyncio` at module top if the project does not run asyncio in auto mode (check `pyproject.toml` `asyncio_mode`; if it is `strict`, decorate each async test with `@pytest.mark.asyncio` and use `pytest_asyncio.fixture` for `world`).

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_025_student_fields.py -v`
Expected: FAIL — e.g. `KeyError: 'section'` / `has_photo` missing in responses.

- [ ] **Step 3: Implement shared helpers in `schools.py`**

Extend imports: `from pydantic import BaseModel, ValidationError` and `from app.schemas import MASTER_FIELD_KEYS, StudentMasterFields, validation_message` (append to the existing `app.schemas` import). Add near `_student_out`:

```python
# --- ENH-025: Student Master fields (DEC-SCOPE-027) -------------------------------------------------

ROLL_CONSTRAINT = "uq_school_students_roll"
ROLL_TAKEN = "roll_number '{roll}' is already used in this grade and section for this academic year"


def _master_fields_or_422(model: type[BaseModel], data: dict) -> BaseModel:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(422, validation_message(exc)) from None


def _master_subset(payload: dict) -> dict:
    """Only the ENH-025 keys; other keys keep their existing hand-written handling (or are ignored, as today)."""
    return {key: payload[key] for key in MASTER_FIELD_KEYS if key in payload}


def _apply_master_fields(student: SchoolStudent, fields: BaseModel) -> list[str]:
    """Set every field the client sent; return the names that actually changed (for audit, never values)."""
    changed = []
    for name in sorted(fields.model_fields_set):
        value = getattr(fields, name)
        if getattr(student, name) != value:
            setattr(student, name, value)
            changed.append(name)
    return changed


def _is_roll_conflict(exc: IntegrityError) -> bool:
    return ROLL_CONSTRAINT in str(exc.orig)


async def _flush_or_409(db: AsyncSession, roll_number: str | None) -> None:
    """Flush inside a savepoint so a roll-number clash is a clean 409, decided by the unique index (no
    read-then-check race). Any other integrity error is re-raised unchanged."""
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        if _is_roll_conflict(exc):
            logger.info("student_roll_conflict", extra={"extra_fields": {"outcome": "rejected"}})
            raise HTTPException(409, ROLL_TAKEN.format(roll=roll_number)) from None
        raise
```

Replace `_student_out`:

```python
def _student_out(s: SchoolStudent) -> dict:
    return {
        "id": s.id,
        "student_code": s.student_code,
        "full_name": s.full_name,
        "date_of_birth": s.date_of_birth,
        "grade_or_class": s.grade_or_class,
        "assigned_teacher_user_id": s.assigned_teacher_user_id,
        "pending_parent_email": s.pending_parent_email,
        "academic_year_id": s.academic_year_id,
        "grade_level": s.grade_level,
        # ENH-025: additive; the photo itself is only ever served by GET .../photo, never as a key or URL.
        **{name: getattr(s, name) for name in MASTER_FIELD_KEYS},
        "has_photo": s.photo_key is not None,
    }
```

- [ ] **Step 4: Wire `create_student`**

Immediately after the `full_name` required check, validate: `master = _master_fields_or_422(StudentMasterFields, _master_subset(payload))`. After constructing `student = SchoolStudent(...)`, replace `db.add(student)` + `await db.flush()` with:

```python
    changed_fields = _apply_master_fields(student, master)
    db.add(student)
    await _flush_or_409(db, student.roll_number)
```

and change the audit metadata to `{"school_id": str(school_id), "parent_status": parent_status, "changed_fields": changed_fields}`.

- [ ] **Step 5: Wire `update_student`**

After the `student.school_id != school_id` check: `master = _master_fields_or_422(StudentMasterFields, _master_subset(payload))`. After the existing teacher block and **before** the parent-link block:

```python
    changed_fields = _apply_master_fields(student, master)
    await _flush_or_409(db, student.roll_number)
```

and audit metadata becomes `{"parent_status": parent_status, "changed_fields": changed_fields}`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_enh_025_student_fields.py -v`
Expected: all PASS.

- [ ] **Step 7: Regression**

Run: `cd apps/api && pytest tests/test_sch_001_school_portal_access.py tests/test_sch_roster_parent_invite.py tests/test_enh_001_academic_year.py -v`
Expected: all PASS (unchanged behavior).

- [ ] **Step 8: Refactor** — `create_student` and `update_student` must share `_master_subset`/`_apply_master_fields`/`_flush_or_409` with no inline copies; rerun Steps 6–7.

- [ ] **Step 9: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_enh_025_student_fields.py
git commit -m "feat(enh-025): student master fields on create/update/read with roll-number 409"
```

---

### Task 5: Bulk upload and template

**Files:**
- Modify: `apps/api/app/api/schools.py` — `ROSTER_TEMPLATE_HEADERS` (`:1450`), `roster_template` (`:899`), `bulk_upload_students` (`:1467`)
- Test: `apps/api/tests/test_enh_025_bulk_upload.py`

**Interfaces:**
- Consumes: Task 3 (`LIST_FIELD_KEYS`, `MASTER_FIELD_KEYS`, `StudentMasterFields`, `validation_message`), Task 4 (`_apply_master_fields`, `_is_roll_conflict`, `ROLL_TAKEN`).
- Produces: `ROSTER_TEMPLATE_HEADERS` (17 entries, original 7 first); `_master_fields_from_csv(row: dict) -> tuple[dict, str | None]`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-025 -- bulk upload + template carry the new columns (spec §3.3, AC1/2/5/6)."""

import csv
import io
import uuid

import pytest
from sqlalchemy import select

from app.models import SchoolParentLink, SchoolStudent, User
from tests.enh005_helpers import login, mk_school

UPLOAD = "/api/v1/school/students/bulk-upload"
ORIGINAL = ["full_name", "date_of_birth", "grade_or_class", "assigned_teacher_email", "parent_name", "parent_email", "grade_level"]
NEW = ["section", "roll_number", "gender", "student_mobile", "city", "subjects", "career_interests", "global_education_interest", "preferred_countries", "preferred_courses"]


def _csv(header: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


async def _upload(client, data: bytes):
    return await client.post(UPLOAD, files={"file": ("roster.csv", data, "text/csv")}, headers={"Idempotency-Key": uuid.uuid4().hex})


@pytest.fixture
async def world(db_session):
    return await mk_school(db_session, label="B", students=0)


async def test_template_keeps_original_columns_first_then_new(client, world):
    await login(client, world["coordinator"].email)
    r = await client.get("/api/v1/school/students/roster-template")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ORIGINAL + NEW
    assert len(rows[1]) == len(ORIGINAL + NEW)


async def test_all_new_columns_load(client, world, db_session):
    await login(client, world["coordinator"].email)
    data = _csv(ORIGINAL + NEW, [["Asha", "", "Grade 8-A", "", "", "", "8", "A", "7", "Female", "+91 98765 43210", "Pune", "Maths;Physics", "Engineering", "yes", "Germany;Canada", "Mechanical"]])
    r = await _upload(client, data)
    assert r.json()["accepted_count"] == 1, r.text
    s = await db_session.scalar(select(SchoolStudent).where(SchoolStudent.school_id == world["school"].id))
    assert (s.section, s.roll_number, s.gender, s.city) == ("A", "7", "female", "Pune")
    assert s.subjects == ["Maths", "Physics"] and s.preferred_countries == ["Germany", "Canada"]
    assert s.global_education_interest is True


async def test_original_seven_column_csv_still_works(client, world):
    await login(client, world["coordinator"].email)
    r = await _upload(client, _csv(ORIGINAL, [["Legacy", "2015-04-12", "Grade 5", "", "", "", "5"]]))
    assert r.json()["accepted_count"] == 1


async def test_short_rows_and_trailing_empty_column_mean_not_set(client, world, db_session):
    await login(client, world["coordinator"].email)
    raw = ("full_name,grade_level,section,city,\n" "Short,6\n" "Trail,6,B,,\n").encode()
    r = await _upload(client, raw)
    assert r.json()["accepted_count"] == 2, r.text
    rows = {s.full_name: s for s in (await db_session.scalars(select(SchoolStudent).where(SchoolStudent.school_id == world["school"].id))).all()}
    assert rows["Short"].section is None and rows["Trail"].section == "B" and rows["Trail"].city is None


async def test_bad_values_reject_only_that_row_without_echoing_mobile(client, world):
    await login(client, world["coordinator"].email)
    data = _csv(["full_name", "gender", "student_mobile", "global_education_interest"], [
        ["Good", "male", "", ""], ["BadGender", "robot", "", ""], ["BadMobile", "", "12ab", ""], ["BadBool", "", "", "maybe"],
    ])
    body = (await _upload(client, data)).json()
    assert body["accepted_count"] == 1 and body["rejected_count"] == 3
    messages = {r["row_number"]: r["error_message"] for r in body["rows"] if r["status"] == "rejected"}
    assert messages[2] == "gender must be one of: female, male, other, prefer_not_to_say"
    assert messages[3].startswith("student_mobile ") and "12ab" not in messages[3]
    assert messages[4] == "global_education_interest must be yes or no"


async def test_roll_clash_inside_the_file_rejects_the_later_row_only(client, world, db_session):
    await login(client, world["coordinator"].email)
    data = _csv(["full_name", "grade_level", "section", "roll_number"], [
        ["R1", "8", "A", "7"], ["R2", "8", "A", "8"], ["R3", "8", "B", "7"], ["R4", "8", "a", "7"], ["R5", "8", "A", "9"],
    ])
    body = (await _upload(client, data)).json()
    assert body["accepted_count"] == 4 and body["rejected_count"] == 1
    rejected = [r for r in body["rows"] if r["status"] == "rejected"]
    assert rejected[0]["row_number"] == 4
    assert rejected[0]["error_message"] == "roll_number '7' is already used in this grade and section for this academic year"


async def test_rejected_roll_row_never_invites_its_parent(client, world, db_session):
    await login(client, world["coordinator"].email)
    email = f"enh025-parent-{uuid.uuid4().hex[:6]}@example.local"
    data = _csv(["full_name", "grade_level", "section", "roll_number", "parent_email"], [["First", "8", "A", "1", ""], ["Second", "8", "A", "1", email]])
    body = (await _upload(client, data)).json()
    assert body["rejected_count"] == 1
    students = (await db_session.scalars(select(SchoolStudent).where(SchoolStudent.pending_parent_email == email))).all()
    assert students == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_025_bulk_upload.py -v`
Expected: FAIL — template header mismatch; new columns ignored.

- [ ] **Step 3: Implement**

Template constants:

```python
# ENH-025: the ten Student Master columns are appended after the original seven, so existing positions never move.
ROSTER_TEMPLATE_HEADERS = [
    "full_name", "date_of_birth", "grade_or_class", "assigned_teacher_email", "parent_name", "parent_email", "grade_level",
    *MASTER_FIELD_KEYS,
]
ROSTER_TEMPLATE_EXAMPLE = ["Jane Doe", "2015-04-12", "Grade 5-A", "", "Jane's Parent", "", "5", "A", "12", "female", "+91 98765 43210", "Pune", "Maths;Science", "Engineering", "yes", "Germany;Canada", "Mechanical Engineering"]
_CSV_BOOLEANS = {"yes": True, "true": True, "1": True, "no": False, "false": False, "0": False}
```

In `roster_template`, replace the example `writer.writerow([...])` with `writer.writerow(ROSTER_TEMPLATE_EXAMPLE)`. Import `LIST_FIELD_KEYS` from `app.schemas`.

```python
def _master_fields_from_csv(row: dict) -> tuple[dict, str | None]:
    """A CSV row -> the StudentMasterFields input shape. A missing column or a short row means "not set".
    Lists split on ';'. Returns (data, error_message)."""
    data: dict = {}
    for key in MASTER_FIELD_KEYS:
        raw = row.get(key)
        if raw is None:
            continue
        raw = raw.strip()
        if key in LIST_FIELD_KEYS:
            data[key] = raw.split(";") if raw else None
        elif key == "global_education_interest":
            if not raw:
                data[key] = None
            elif raw.lower() in _CSV_BOOLEANS:
                data[key] = _CSV_BOOLEANS[raw.lower()]
            else:
                return {}, "global_education_interest must be yes or no"
        else:
            data[key] = raw or None
    return data, None
```

In the bulk loop, after the existing `grade_level` validation block and before `if error:`:

```python
        master = None
        if not error:
            master_data, error = _master_fields_from_csv(row)
            if not error:
                try:
                    master = StudentMasterFields.model_validate(master_data)
                except ValidationError as exc:
                    error = validation_message(exc)
```

Replace the student insert block (`student = SchoolStudent(...)`, `db.add(student)`, `await db.flush()`) with:

```python
        student = SchoolStudent(
            school_id=school_id, student_code=await unique_student_code(db, SchoolStudent.student_code), full_name=full_name, date_of_birth=student_dob,
            grade_or_class=(row.get("grade_or_class") or "").strip() or None,
            created_by_user_id=user.id, assigned_teacher_user_id=assigned_teacher_user_id,
            grade_level=grade_level, academic_year_id=current_year_id,
        )
        _apply_master_fields(student, master)
        # ENH-025: the insert runs in its own savepoint so a roll-number clash rejects this row only
        # (SCH-002-AC04). The parent link/invite runs after, so a rolled-back row never sends an invite.
        try:
            async with db.begin_nested():
                db.add(student)
                await db.flush()
        except IntegrityError as exc:
            if not _is_roll_conflict(exc):
                raise
            db.add(SchoolRosterUploadRow(batch_id=batch.id, row_number=i, status="rejected", error_message=ROLL_TAKEN.format(roll=student.roll_number)))
            rejected += 1
            continue
```

(the existing `if parent_email: await _link_or_invite_parent(...)` and accepted-row lines follow unchanged). Add to the final `logger`-free audit: nothing changes; additionally emit `logger.info("roster_bulk_upload_completed", extra={"extra_fields": {"batch_id": str(batch.id), "total": len(rows), "accepted": accepted, "rejected": rejected}})` just before `return`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_enh_025_bulk_upload.py tests/test_sch_002_bulk_roster_upload.py tests/test_enh_001_academic_year.py -v`
Expected: all PASS.

- [ ] **Step 5: Refactor** — the row-level validation branch should read like the existing ones (same `if not error:` idiom); no duplicated list/boolean parsing; rerun Step 4.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_enh_025_bulk_upload.py
git commit -m "feat(enh-025): bulk upload and template carry the student master columns"
```

---

### Task 6: Promotion, grade history and transfer side effects

**Files:**
- Modify: `apps/api/app/api/schools.py:1347-1358` (promotion loop), `:1147-1148` (grade-history output)
- Modify: `apps/api/app/schemas.py` (`GradeHistoryState`)
- Modify: `apps/api/app/api/school_transfers.py:443`
- Test: `apps/api/tests/test_enh_025_lifecycle.py`

**Interfaces:**
- Produces: `GradeHistoryState.section: str | None`, `GradeHistoryState.roll_number: str | None`; grade-history JSON `from.section`, `from.roll_number`, `to.section`, `to.roll_number` (always null).

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-025 -- year moves clear roll numbers but history keeps them; transfers clear section/roll (AC10)."""

import pytest
from sqlalchemy import update

from app.models import AcademicYear, SchoolStudent
from tests.enh005_helpers import login, mk_request, mk_school

PROMOTE = "/api/v1/school/students/promotions"


async def _new_active_year(db):
    """Make a fresh academic year active so promotion has somewhere to move students (ENH-004 test pattern)."""
    from datetime import date, timedelta
    import uuid

    await db.execute(update(AcademicYear).where(AcademicYear.status == "active").values(status="closed"))
    start = date.today() + timedelta(days=400)
    year = AcademicYear(label=f"ENH025-{uuid.uuid4().hex[:4]}", start_date=start, end_date=start + timedelta(days=364), status="active")
    db.add(year)
    await db.commit()
    return year


@pytest.fixture
async def world(db_session):
    w = await mk_school(db_session, label="L", students=3)
    for i, s in enumerate(w["students"]):
        s.section, s.roll_number = "A", str(i + 1)
    await db_session.commit()
    return w


async def test_promote_and_hold_back_clear_roll_and_history_keeps_it(client, world, db_session):
    await _new_active_year(db_session)
    await login(client, world["coordinator"].email)
    a, b, _ = world["students"]
    r = await client.post(PROMOTE, json={"items": [{"student_id": str(a.id), "action": "promote"}, {"student_id": str(b.id), "action": "hold_back"}]})
    assert r.status_code == 200, r.text
    for s in (a, b):
        fresh = await db_session.get(SchoolStudent, s.id, populate_existing=True)
        assert fresh.roll_number is None and fresh.section == "A"
    history = (await client.get(f"/api/v1/school/students/{a.id}/grade-history")).json()["history"][0]
    assert history["from"]["section"] == "A" and history["from"]["roll_number"] == "1"
    assert history["to"]["section"] == "A" and history["to"]["roll_number"] is None


async def test_untouched_students_keep_their_roll(client, world, db_session):
    await _new_active_year(db_session)
    await login(client, world["coordinator"].email)
    await client.post(PROMOTE, json={"items": [{"student_id": str(world["students"][0].id), "action": "promote"}]})
    third = await db_session.get(SchoolStudent, world["students"][2].id, populate_existing=True)
    assert third.roll_number == "3"


async def test_transfer_approval_clears_section_and_roll(client, db_session, world):
    b = await mk_school(db_session, label="LB", students=0)
    kid = world["students"][0]
    request = await mk_request(db_session, kid, from_school=world["school"], to_school=b["school"], filed_by_school=world["school"], requester=world["coordinator"])
    await login(client, world["admin"].email)
    r = await client.post(f"/api/v1/admin/school-transfer-requests/{request.id}/approve", json={})
    assert r.status_code in (200, 201), r.text
    fresh = await db_session.get(SchoolStudent, kid.id, populate_existing=True)
    assert fresh.section is None and fresh.roll_number is None
```

Before running, confirm the approve route path by `grep -n "approve" apps/api/app/api/school_transfers.py` and use that path verbatim (the ENH-005 tests in `test_enh_005_approve.py` show the exact call); adjust the URL above if it differs.

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_025_lifecycle.py -v`
Expected: FAIL — `roll_number` still set; `section` key missing in history.

- [ ] **Step 3: Implement**

Promotion loop — add the three history kwargs and clear the roll after recording:

```python
                SchoolStudentGradeHistory(
                    school_student_id=student.id, action=decision.status,
                    from_academic_year_id=student.academic_year_id, from_grade_level=student.grade_level, from_grade_or_class=student.grade_or_class,
                    to_academic_year_id=active_year.id, to_grade_level=decision.grade_level, to_grade_or_class=decision.grade_or_class,
                    # ENH-025 (DEC-SCOPE-027 item 6): previous class details survive the roll-number reset below.
                    from_section=student.section, from_roll_number=student.roll_number, to_section=student.section,
                    performed_by_user_id=user.id,
                )
            )
            student.academic_year_id = active_year.id
            student.grade_level = decision.grade_level
            student.grade_or_class = decision.grade_or_class
            # Roll numbers are reassigned each year; NULL can never violate uq_school_students_roll, so this
            # cannot fail the promotion's single transaction.
            student.roll_number = None
```

Grade-history output:

```python
                "from": {"academic_year_id": h.from_academic_year_id, "academic_year_label": from_y.label if from_y else None, "grade_level": h.from_grade_level, "grade_or_class": h.from_grade_or_class, "section": h.from_section, "roll_number": h.from_roll_number},
                "to": {"academic_year_id": h.to_academic_year_id, "academic_year_label": to_y.label, "grade_level": h.to_grade_level, "grade_or_class": h.to_grade_or_class, "section": h.to_section, "roll_number": None},
```

`GradeHistoryState` gains `section: str | None = None` and `roll_number: str | None = None`.

`school_transfers.py:443` becomes:

```python
    # ENH-025 (DEC-SCOPE-027 item 7): section and roll number belong to the losing school, like the teacher.
    student.school_id, student.assigned_teacher_user_id, student.pending_parent_email = request.to_school_id, None, None
    student.section, student.roll_number = None, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_enh_025_lifecycle.py tests/test_enh_004_student_promotion.py tests/test_enh_005_approve.py tests/test_enh_005_concurrency.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/app/schemas.py apps/api/app/api/school_transfers.py apps/api/tests/test_enh_025_lifecycle.py
git commit -m "feat(enh-025): year moves clear roll numbers with history kept; transfers clear section and roll"
```

---

### Task 7: Image metadata stripping and storage read/delete

**Files:**
- Create: `apps/api/app/services/image_metadata.py`
- Modify: `apps/api/app/services/storage.py`
- Create: `apps/api/tests/enh025_helpers.py`
- Test: `apps/api/tests/test_enh_025_image_metadata.py`

**Interfaces:**
- Produces: `detect_image_type(data: bytes) -> str | None` (`"image/jpeg"`/`"image/png"`/`None`); `strip_metadata(data: bytes, content_type: str) -> bytes`; `class InvalidImage(ValueError)`; `StorageService.read_bytes(key: str) -> bytes`, `StorageService.delete(key: str) -> None`; helpers `jpeg_bytes(with_gps: bool = True) -> bytes`, `png_bytes(with_text: bool = True) -> bytes`.

- [ ] **Step 1: Write helpers and failing tests**

`tests/enh025_helpers.py`:

```python
"""ENH-025 byte builders: minimal, structurally valid JPEG/PNG files with and without metadata."""

import struct
import zlib


def _segment(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def jpeg_bytes(with_gps: bool = True) -> bytes:
    parts = [b"\xff\xd8", _segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")]
    if with_gps:
        parts.append(_segment(0xE1, b"Exif\x00\x00GPSLatitude=18.52;GPSLongitude=73.85"))
        parts.append(_segment(0xFE, b"comment: home address"))
    parts.append(_segment(0xE2, b"ICC_PROFILE\x00\x01\x01profile"))
    parts.append(_segment(0xDB, b"\x00" + bytes(64)))
    parts.append(_segment(0xDA, b"\x01\x01\x00\x00\x3f\x00") + b"\x12\x34\x56\xff\x00\x78" + b"\xff\xd9")
    return b"".join(parts)


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png_bytes(with_text: bool = True) -> bytes:
    parts = [b"\x89PNG\r\n\x1a\n", _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))]
    if with_text:
        parts += [_chunk(b"tEXt", b"Location\x00Pune"), _chunk(b"eXIf", b"GPS"), _chunk(b"tIME", bytes(7))]
    parts += [_chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")), _chunk(b"IEND", b"")]
    return b"".join(parts)
```

`tests/test_enh_025_image_metadata.py`:

```python
"""ENH-025 -- photo type detection and metadata stripping (spec §5 privacy row)."""

import pytest

from app.services.image_metadata import InvalidImage, detect_image_type, strip_metadata
from app.services.storage import StorageService
from tests.enh025_helpers import jpeg_bytes, png_bytes


def test_detects_by_magic_bytes_only():
    assert detect_image_type(jpeg_bytes()) == "image/jpeg"
    assert detect_image_type(png_bytes()) == "image/png"
    assert detect_image_type(b"<svg xmlns='http://www.w3.org/2000/svg'/>") is None
    assert detect_image_type(b"<html><script>alert(1)</script>") is None
    assert detect_image_type(b"") is None


def test_jpeg_exif_and_comments_removed_icc_kept():
    out = strip_metadata(jpeg_bytes(with_gps=True), "image/jpeg")
    assert b"GPSLatitude" not in out and b"home address" not in out
    assert b"ICC_PROFILE" in out and b"JFIF" in out
    assert out.startswith(b"\xff\xd8") and out.endswith(b"\xff\xd9")


def test_jpeg_trailing_bytes_after_eoi_dropped():
    out = strip_metadata(jpeg_bytes(with_gps=False) + b"<html>trailer</html>", "image/jpeg")
    assert b"trailer" not in out and out.endswith(b"\xff\xd9")


def test_png_text_exif_time_chunks_removed():
    out = strip_metadata(png_bytes(with_text=True), "image/png")
    assert b"tEXt" not in out and b"eXIf" not in out and b"tIME" not in out and b"Pune" not in out
    assert out == png_bytes(with_text=False)


@pytest.mark.parametrize(("data", "kind"), [(jpeg_bytes()[:40], "image/jpeg"), (png_bytes()[:30], "image/png"), (b"\xff\xd8\xff\xe0\x00", "image/jpeg")])
def test_truncated_or_malformed_files_raise(data, kind):
    with pytest.raises(InvalidImage):
        strip_metadata(data, kind)


def test_storage_read_delete_round_trip_and_root_guard(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "aws_s3_bucket", "")
    monkeypatch.setattr(settings, "local_upload_dir", str(tmp_path))
    store = StorageService()
    store.write_bytes("school-student-photos/abc", b"data", "image/png")
    assert store.read_bytes("school-student-photos/abc") == b"data"
    store.delete("school-student-photos/abc")
    store.delete("school-student-photos/abc")  # idempotent
    with pytest.raises(FileNotFoundError):
        store.read_bytes("school-student-photos/abc")
    with pytest.raises(ValueError):
        store.delete("../outside")
    with pytest.raises(ValueError):
        store.read_bytes("school-student-photos")  # the prefix itself, not an object under it is fine; root itself is not
```

Replace the last assertion's key with `""` (the root itself) if `school-student-photos` resolves under the root — the rule under test is "the target must be strictly below the storage root".

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_025_image_metadata.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.image_metadata`.

- [ ] **Step 3: Implement `image_metadata.py`**

```python
"""ENH-025 -- identify JPEG/PNG by magic bytes and strip metadata without decoding pixels (no image library;
spec §5). Location data in phone photos (EXIF GPS) must never be stored for a minor."""

JPEG = "image/jpeg"
PNG = "image/png"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Dropped: APP1 (EXIF/XMP, incl. GPS), APP3-APP13 (incl. APP13 Photoshop/IPTC), APP15, COM. Kept: APP0 (JFIF),
# APP2 (ICC colour profile) and APP14 (Adobe colour transform) -- they carry no personal data and dropping
# them can mis-colour the image.
_JPEG_DROP = {0xE1, *range(0xE3, 0xEE), 0xEF, 0xFE}
_PNG_DROP = {b"tEXt", b"iTXt", b"zTXt", b"eXIf", b"tIME"}


class InvalidImage(ValueError):
    pass


def detect_image_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith(_PNG_SIGNATURE):
        return PNG
    return None


def strip_metadata(data: bytes, content_type: str) -> bytes:
    if content_type == JPEG:
        return _strip_jpeg(data)
    if content_type == PNG:
        return _strip_png(data)
    raise InvalidImage("unsupported image type")


def _strip_jpeg(data: bytes) -> bytes:
    out = bytearray(b"\xff\xd8")
    i, n = 2, len(data)
    while i < n:
        if data[i] != 0xFF:
            raise InvalidImage("expected a JPEG marker")
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            break
        marker = data[i]
        i += 1
        if marker == 0xD9:
            return bytes(out + b"\xff\xd9")
        if marker == 0xDA:
            end = data.rfind(b"\xff\xd9", i)
            if end == -1:
                raise InvalidImage("JPEG has no end-of-image marker")
            return bytes(out + b"\xff\xda" + data[i : end + 2])
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            out += bytes((0xFF, marker))
            continue
        if i + 2 > n:
            break
        length = int.from_bytes(data[i : i + 2], "big")
        if length < 2 or i + length > n:
            raise InvalidImage("JPEG segment runs past the end of the file")
        if marker not in _JPEG_DROP:
            out += bytes((0xFF, marker)) + data[i : i + length]
        i += length
    raise InvalidImage("JPEG is truncated")


def _strip_png(data: bytes) -> bytes:
    if not data.startswith(_PNG_SIGNATURE):
        raise InvalidImage("not a PNG")
    out = bytearray(_PNG_SIGNATURE)
    i, n = len(_PNG_SIGNATURE), len(data)
    while i + 8 <= n:
        length = int.from_bytes(data[i : i + 4], "big")
        kind = data[i + 4 : i + 8]
        end = i + 12 + length
        if end > n:
            raise InvalidImage("PNG chunk runs past the end of the file")
        if kind not in _PNG_DROP:
            out += data[i:end]
        i = end
        if kind == b"IEND":
            return bytes(out)
    raise InvalidImage("PNG is truncated")
```

- [ ] **Step 4: Implement storage `read_bytes` / `delete`**

```python
    def _local_path(self, key: str) -> Path:
        """Resolve a key under the storage root. Keys are server-generated, but a destructive call still
        checks the resolved target is strictly below the root (spec §5)."""
        root = self.local_dir.resolve()
        path = (self.local_dir / key).resolve()
        if root not in path.parents:
            raise ValueError("storage key resolves outside the upload root")
        return path

    def read_bytes(self, key: str) -> bytes:
        if self.bucket:
            return boto3.client("s3", region_name=settings.aws_region).get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return self._local_path(key).read_bytes()

    def delete(self, key: str) -> None:
        if self.bucket:
            boto3.client("s3", region_name=settings.aws_region).delete_object(Bucket=self.bucket, Key=key)
            return
        self._local_path(key).unlink(missing_ok=True)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_enh_025_image_metadata.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/image_metadata.py apps/api/app/services/storage.py apps/api/tests/enh025_helpers.py apps/api/tests/test_enh_025_image_metadata.py
git commit -m "feat(enh-025): strip photo metadata without an image library; storage read/delete"
```

---

### Task 8: Photo endpoints

**Files:**
- Create: `apps/api/app/api/school_student_profile.py`
- Modify: `apps/api/app/main.py:9` and the router list near `:34`
- Test: `apps/api/tests/test_enh_025_photo.py`

**Interfaces:**
- Consumes: Task 4 (`_master_fields_or_422`, `_apply_master_fields`), Task 7, `schools._load_readable_student`, `schools._own_school_id`, `schools._student_in_portfolio`.
- Produces: `router` (prefix `/school`); `MAX_PHOTO_BYTES = 2 * 1024 * 1024`; `PHOTO_HEADERS: dict[str, str]`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-025 -- authorized photo upload/stream/delete (spec §3.4, §5, AC8, AC12)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, SchoolStudent
from app.services.storage import storage
from tests.enh005_helpers import login, mk_school, mk_staff, mk_student
from tests.enh025_helpers import jpeg_bytes, png_bytes

PHOTO = "/api/v1/school/students/{sid}/photo"


@pytest.fixture(autouse=True)
def _local_storage(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "aws_s3_bucket", "")
    monkeypatch.setattr(storage, "bucket", "")
    monkeypatch.setattr(storage, "local_dir", tmp_path)


@pytest.fixture
async def world(db_session):
    return await mk_school(db_session, label="P", students=2)


async def _put(client, sid, data, name="p.jpg", ctype="image/jpeg"):
    return await client.put(PHOTO.format(sid=sid), files={"file": (name, data, ctype)})


async def test_upload_strips_metadata_and_readers_in_scope_get_it(client, world):
    sid = world["students"][0].id
    await login(client, world["coordinator"].email)
    r = await _put(client, sid, jpeg_bytes(with_gps=True))
    assert r.status_code == 200 and r.json() == {"has_photo": True}
    assert (await client.get(f"/api/v1/school/students/{sid}")).json()["has_photo"] is True
    for role in ("coordinator", "principal", "teacher", "parent"):
        await login(client, world[role].email)
        got = await client.get(PHOTO.format(sid=sid))
        assert got.status_code == 200, role
        assert got.headers["content-type"] == "image/jpeg"
        assert got.headers["cache-control"] == "private, no-store"
        assert got.headers["x-content-type-options"] == "nosniff"
        assert got.headers["content-security-policy"] == "default-src 'none'; sandbox"
        assert b"GPSLatitude" not in got.content


async def test_out_of_scope_readers_are_refused(client, world, db_session):
    sid = world["students"][1].id  # not assigned to the teacher, not linked to the parent
    await login(client, world["coordinator"].email)
    await _put(client, sid, png_bytes(), "p.png", "image/png")
    for role in ("teacher", "parent"):
        await login(client, world[role].email)
        assert (await client.get(PHOTO.format(sid=sid))).status_code == 403, role
    other = await mk_school(db_session, label="PO", students=0)
    await login(client, other["coordinator"].email)
    assert (await client.get(PHOTO.format(sid=sid))).status_code == 403
    counselor = await mk_staff(db_session, world["school"], world["admin"], role="career_counselor")
    await login(client, counselor.email)
    assert (await client.get(PHOTO.format(sid=sid))).status_code == 403


@pytest.mark.parametrize(
    ("data", "name", "ctype", "status"),
    [
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "x.svg", "image/svg+xml", 415),
        (b"<html><script>alert(1)</script></html>", "x.jpg", "image/jpeg", 415),
        (b"", "x.jpg", "image/jpeg", 422),
        (b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024), "big.jpg", "image/jpeg", 413),
        (b"\xff\xd8\xff\xe0\x00", "trunc.jpg", "image/jpeg", 422),
    ],
)
async def test_bad_uploads_are_rejected(client, world, data, name, ctype, status):
    await login(client, world["coordinator"].email)
    r = await _put(client, world["students"][0].id, data, name, ctype)
    assert r.status_code == status, r.text


async def test_png_sent_with_jpeg_content_type_is_stored_as_png(client, world):
    sid = world["students"][0].id
    await login(client, world["coordinator"].email)
    assert (await _put(client, sid, png_bytes(), "p.jpg", "image/jpeg")).status_code == 200
    assert (await client.get(PHOTO.format(sid=sid))).headers["content-type"] == "image/png"


async def test_only_own_school_coordinator_can_write(client, world, db_session):
    sid = world["students"][0].id
    for role in ("principal", "teacher", "parent"):
        await login(client, world[role].email)
        assert (await _put(client, sid, jpeg_bytes())).status_code == 403, role
        assert (await client.delete(PHOTO.format(sid=sid))).status_code == 403, role
    other = await mk_school(db_session, label="PW", students=0)
    await login(client, other["coordinator"].email)
    assert (await _put(client, sid, jpeg_bytes())).status_code == 403


async def test_replace_deletes_the_old_object_and_delete_is_idempotent(client, world, db_session, tmp_path):
    sid = world["students"][0].id
    await login(client, world["coordinator"].email)
    await _put(client, sid, jpeg_bytes())
    first_key = (await db_session.get(SchoolStudent, sid, populate_existing=True)).photo_key
    await _put(client, sid, png_bytes(), "p.png", "image/png")
    second_key = (await db_session.get(SchoolStudent, sid, populate_existing=True)).photo_key
    assert first_key != second_key
    assert not (tmp_path / first_key).exists() and (tmp_path / second_key).exists()
    assert (await client.delete(PHOTO.format(sid=sid))).status_code == 204
    assert (await client.delete(PHOTO.format(sid=sid))).status_code == 204
    assert not (tmp_path / second_key).exists()
    assert (await client.get(PHOTO.format(sid=sid))).status_code == 404


async def test_replacing_when_the_old_file_is_already_gone_still_succeeds(client, world, db_session, tmp_path):
    sid = world["students"][0].id
    await login(client, world["coordinator"].email)
    await _put(client, sid, jpeg_bytes())
    key = (await db_session.get(SchoolStudent, sid, populate_existing=True)).photo_key
    (tmp_path / key).unlink()
    assert (await _put(client, sid, jpeg_bytes())).status_code == 200


async def test_missing_object_on_read_is_404_not_500(client, world, db_session, tmp_path):
    sid = world["students"][0].id
    await login(client, world["coordinator"].email)
    await _put(client, sid, jpeg_bytes())
    (tmp_path / (await db_session.get(SchoolStudent, sid, populate_existing=True)).photo_key).unlink()
    assert (await client.get(PHOTO.format(sid=sid))).status_code == 404


async def test_key_never_leaks_into_responses_or_audit(client, world, db_session):
    sid = world["students"][0].id
    await login(client, world["coordinator"].email)
    await _put(client, sid, jpeg_bytes())
    key = (await db_session.get(SchoolStudent, sid, populate_existing=True)).photo_key
    for url in (f"/api/v1/school/students/{sid}", "/api/v1/school/students", f"/api/v1/school/students/{sid}/overview"):
        assert key not in (await client.get(url)).text
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(sid), AuditLog.action.like("school.student_photo_%")))).all()
    assert rows and all(key not in str(r.metadata_json) for r in rows)


async def test_commit_failure_removes_the_new_object(client, world, db_session, tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    sid = world["students"][0].id
    await login(client, world["coordinator"].email)

    async def boom(self):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(AsyncSession, "commit", boom)
    with pytest.raises(RuntimeError):
        await _put(client, sid, jpeg_bytes())
    monkeypatch.undo()
    assert list((tmp_path / "school-student-photos").glob("*")) == []
```

(`mk_student` import is available for extra fixtures if needed; remove it if unused after writing the file.)

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_025_photo.py -v`
Expected: FAIL — 404/405 on `/photo` routes.

- [ ] **Step 3: Implement the router (photo part)**

```python
"""ENH-025 -- Student Master photo and career-preference routes (docs/superpowers/specs/
2026-09-23-enh-025-student-master-fields-design.md §3.4, DEC-SCOPE-027). Scope checks are imported from
schools.py (same pattern as portfolio.py), never re-implemented here."""

import hashlib
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import _apply_master_fields, _load_readable_student, _master_fields_or_422, _own_school_id, _student_in_portfolio
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, SchoolStudent, User
from app.schemas import CAREER_PREFERENCE_KEYS, CareerPreferencesUpdate
from app.services.image_metadata import InvalidImage, detect_image_type, strip_metadata
from app.services.storage import storage

router = APIRouter(prefix="/school", tags=["school"])
logger = get_logger("app.school.profile")

MAX_PHOTO_BYTES = 2 * 1024 * 1024
PHOTO_PREFIX = "school-student-photos"
PHOTO_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Content-Disposition": "inline",
}


def _digest(key: str) -> str:
    """Operators can match an orphan to a file by hashing names; the key itself is never logged (spec §5)."""
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def _discard(key: str, student_id: UUID) -> None:
    try:
        storage.delete(key)
    except Exception:
        logger.warning("student_photo_orphaned", extra={"extra_fields": {"student_id": str(student_id), "key_digest": _digest(key)}})


async def _coordinator_student(db: AsyncSession, user: User, student_id: UUID) -> SchoolStudent:
    """Own-school coordinator only, row locked so concurrent photo writes serialize (no orphaned objects)."""
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    student = await db.scalar(select(SchoolStudent).where(SchoolStudent.id == student_id).with_for_update())
    if not student:
        raise HTTPException(404, "Student not found")
    if student.school_id != school_id:
        raise HTTPException(403, "This student is at a different institution")
    return student


@router.put("/students/{student_id}/photo")
async def put_student_photo(student_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _coordinator_student(db, user, student_id)
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if not data:
        raise HTTPException(422, "photo file is empty")
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "photo must be at most 2 MB")
    content_type = detect_image_type(data)
    if content_type is None:
        raise HTTPException(415, "photo must be a JPEG or PNG image")
    try:
        data = strip_metadata(data, content_type)
    except InvalidImage:
        raise HTTPException(422, "photo could not be read as a valid JPEG or PNG image") from None

    old_key, new_key = student.photo_key, f"{PHOTO_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(new_key, data, content_type)
    except Exception:
        logger.exception("student_photo_store_failed", extra={"extra_fields": {"student_id": str(student.id)}})
        raise HTTPException(500, "Could not store the photo; please try again") from None
    student.photo_key, student.photo_content_type = new_key, content_type
    db.add(AuditLog(user_id=user.id, action="school.student_photo_set", entity_type="school_student", entity_id=str(student.id), metadata_json={"school_id": str(student.school_id), "replaced": old_key is not None, "content_type": content_type, "bytes": len(data)}))
    try:
        await db.commit()
    except Exception:
        _discard(new_key, student.id)
        raise
    if old_key:
        _discard(old_key, student.id)
    logger.info("student_photo_set", extra={"extra_fields": {"student_id": str(student.id), "replaced": old_key is not None, "bytes": len(data)}})
    return {"has_photo": True}


@router.get("/students/{student_id}/photo")
async def get_student_photo(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_readable_student(db, user, student_id)
    if not student.photo_key:
        raise HTTPException(404, "No photo on file")
    try:
        data = storage.read_bytes(student.photo_key)
    except FileNotFoundError:
        logger.warning("student_photo_object_missing", extra={"extra_fields": {"student_id": str(student.id), "key_digest": _digest(student.photo_key)}})
        raise HTTPException(404, "No photo on file") from None
    return Response(content=data, media_type=student.photo_content_type, headers=PHOTO_HEADERS)


@router.delete("/students/{student_id}/photo", status_code=204)
async def delete_student_photo(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _coordinator_student(db, user, student_id)
    old_key = student.photo_key
    if old_key is None:
        return Response(status_code=204)
    student.photo_key, student.photo_content_type = None, None
    db.add(AuditLog(user_id=user.id, action="school.student_photo_remove", entity_type="school_student", entity_id=str(student.id), metadata_json={"school_id": str(student.school_id)}))
    await db.commit()
    _discard(old_key, student.id)
    logger.info("student_photo_removed", extra={"extra_fields": {"student_id": str(student.id)}})
    return Response(status_code=204)
```

Note: `_load_readable_student` for a non-school role calls `_own_school_id(user)`; confirm it returns 403 for `career_counselor` (the out-of-scope test asserts 403). If it raises something else, add an explicit role guard in `get_student_photo`: `if user.role not in {"school_coordinator", "school_principal", "school_teacher", "school_parent"}: raise HTTPException(403, "Not permitted to view this student's photo")`.

Register: add `school_student_profile` to the `from app.api import ...` list in `main.py` and to the router tuple iterated at line ~34.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_enh_025_photo.py -v`
Expected: all PASS.

- [ ] **Step 5: Refactor** — `_coordinator_student` must be the only coordinator-write guard in the module; rerun.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/school_student_profile.py apps/api/app/main.py apps/api/tests/test_enh_025_photo.py
git commit -m "feat(enh-025): authorized student photo upload, stream and removal"
```

---

### Task 9: Counselor career-preferences endpoints

**Files:**
- Modify: `apps/api/app/api/school_student_profile.py`
- Test: `apps/api/tests/test_enh_025_career_preferences.py`

**Interfaces:**
- Produces: `GET/PATCH /school/students/{id}/career-preferences` returning `{"student_id", "career_interests", "global_education_interest", "preferred_countries", "preferred_courses"}`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-025 -- Career Counsellor career-preferences route (spec §3.4, §3.5, AC9)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, SchoolStudent
from tests.enh005_helpers import login, mk_school, mk_staff

URL = "/api/v1/school/students/{sid}/career-preferences"


@pytest.fixture
async def world(db_session):
    w = await mk_school(db_session, label="C", students=1)
    w["counselor"] = await mk_staff(db_session, w["school"], w["admin"], role="career_counselor")
    return w


async def test_counselor_reads_and_writes_the_four_fields(client, world, db_session):
    sid = world["students"][0].id
    await login(client, world["counselor"].email)
    assert (await client.get(URL.format(sid=sid))).json() == {"student_id": str(sid), "career_interests": None, "global_education_interest": None, "preferred_countries": None, "preferred_courses": None}
    r = await client.patch(URL.format(sid=sid), json={"career_interests": ["Design"], "global_education_interest": True})
    assert r.status_code == 200 and r.json()["career_interests"] == ["Design"]
    fresh = await db_session.get(SchoolStudent, sid, populate_existing=True)
    assert fresh.global_education_interest is True
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.student_career_preferences_update", AuditLog.entity_id == str(sid)))
    assert audit.metadata_json["changed_fields"] == ["career_interests", "global_education_interest"]
    assert "Design" not in str(audit.metadata_json)


@pytest.mark.parametrize("key", ["roll_number", "student_mobile", "school_id", "academic_year_id", "photo_key", "section"])
async def test_non_career_keys_are_422(client, world, key):
    await login(client, world["counselor"].email)
    r = await client.patch(URL.format(sid=world["students"][0].id), json={key: "x"})
    assert r.status_code == 422 and r.json()["detail"] == f"{key} is not an accepted field"


async def test_counselor_outside_portfolio_is_403(client, world, db_session):
    other = await mk_school(db_session, label="CO", students=1)
    await login(client, world["counselor"].email)
    assert (await client.get(URL.format(sid=other["students"][0].id))).status_code == 403
    assert (await client.patch(URL.format(sid=other["students"][0].id), json={"career_interests": ["X"]})).status_code == 403


async def test_other_roles_are_403(client, world):
    for role in ("coordinator", "principal", "teacher", "parent"):
        await login(client, world[role].email)
        assert (await client.get(URL.format(sid=world["students"][0].id))).status_code == 403, role


async def test_coordinator_sees_counselor_edits(client, world):
    sid = world["students"][0].id
    await login(client, world["counselor"].email)
    await client.patch(URL.format(sid=sid), json={"preferred_countries": ["Japan"]})
    await login(client, world["coordinator"].email)
    assert (await client.get(f"/api/v1/school/students/{sid}")).json()["preferred_countries"] == ["Japan"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_025_career_preferences.py -v`
Expected: FAIL — 404/405.

- [ ] **Step 3: Implement**

Append to `school_student_profile.py`:

```python
async def _counselor_student(db: AsyncSession, user: User, student_id: UUID) -> SchoolStudent:
    if user.role != "career_counselor":
        raise HTTPException(403, "Career Counselor role required")
    return await _student_in_portfolio(db, user, student_id)


def _career_out(student: SchoolStudent) -> dict:
    return {"student_id": student.id, **{key: getattr(student, key) for key in CAREER_PREFERENCE_KEYS}}


@router.get("/students/{student_id}/career-preferences")
async def get_career_preferences(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return _career_out(await _counselor_student(db, user, student_id))


@router.patch("/students/{student_id}/career-preferences")
async def update_career_preferences(student_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _counselor_student(db, user, student_id)
    fields = _master_fields_or_422(CareerPreferencesUpdate, payload)
    changed = _apply_master_fields(student, fields)
    db.add(AuditLog(user_id=user.id, action="school.student_career_preferences_update", entity_type="school_student", entity_id=str(student.id), metadata_json={"school_id": str(student.school_id), "changed_fields": changed}))
    await db.commit()
    logger.info("student_career_preferences_updated", extra={"extra_fields": {"student_id": str(student.id), "changed": len(changed)}})
    return _career_out(student)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && pytest tests/test_enh_025_career_preferences.py tests/test_enh_025_photo.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/school_student_profile.py apps/api/tests/test_enh_025_career_preferences.py
git commit -m "feat(enh-025): career counsellor career-preferences route"
```

---

### Task 10: Frontend shared module, field groups and roster forms

**Files:**
- Create: `apps/web/lib/schoolStudents.ts`
- Create: `apps/web/components/SchoolStudentFields.tsx`
- Modify: `apps/web/components/SchoolStudentsPanel.tsx`
- Modify: `apps/web/app/globals.css` (append)
- Test: `apps/web/tests/components/schoolStudents.test.ts`, `apps/web/tests/components/SchoolStudentsPanel.test.tsx`

**Interfaces:**
- Produces: `type SchoolStudent`, `GENDER_OPTIONS: {value: string; label: string}[]`, `MASTER_LIST_FIELDS`, `toMasterPayload(form: FormData, mode: "create" | "edit"): Record<string, unknown>`, `listText(value: string[] | null): string`, `ROSTER_COLUMNS: {name: string; required: boolean; format: string; example: string}[]`, `detailMessage(detail: unknown, fallback?: string): string`; component `SchoolStudentFields({ idPrefix, student, teachers, includeInactiveTeachers })`.

- [ ] **Step 1: Write the failing tests**

`tests/components/schoolStudents.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { ROSTER_COLUMNS, listText, toMasterPayload } from "@/lib/schoolStudents";

function form(entries: Record<string, string>) {
  const f = new FormData();
  Object.entries(entries).forEach(([k, v]) => f.append(k, v));
  return f;
}

describe("toMasterPayload", () => {
  it("splits lists on commas, trims, drops empties", () => {
    const p = toMasterPayload(form({ subjects: " Maths, Physics ,, ", city: " Pune ", gender: "female", global_education_interest: "yes" }), "create");
    expect(p).toEqual({ subjects: ["Maths", "Physics"], city: "Pune", gender: "female", global_education_interest: true });
  });
  it("create omits empty fields; edit sends null to clear", () => {
    const f = form({ city: "", subjects: "", gender: "", global_education_interest: "" });
    expect(toMasterPayload(f, "create")).toEqual({});
    expect(toMasterPayload(f, "edit")).toEqual({ city: null, subjects: null, gender: null, global_education_interest: null, section: null, roll_number: null, student_mobile: null, career_interests: null, preferred_countries: null, preferred_courses: null });
  });
  it("maps no to false", () => {
    expect(toMasterPayload(form({ global_education_interest: "no" }), "create")).toEqual({ global_education_interest: false });
  });
});

describe("listText / ROSTER_COLUMNS", () => {
  it("joins lists for inputs", () => {
    expect(listText(["A", "B"])).toBe("A, B");
    expect(listText(null)).toBe("");
  });
  it("documents the original seven columns first and marks photo as not in CSV", () => {
    expect(ROSTER_COLUMNS.slice(0, 7).map((c) => c.name)).toEqual(["full_name", "date_of_birth", "grade_or_class", "assigned_teacher_email", "parent_name", "parent_email", "grade_level"]);
    expect(ROSTER_COLUMNS).toHaveLength(17);
    expect(ROSTER_COLUMNS.filter((c) => c.required).map((c) => c.name)).toEqual(["full_name"]);
  });
});
```

`tests/components/SchoolStudentsPanel.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SchoolStudentsPanel from "@/components/SchoolStudentsPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const student = {
  id: "s1", student_code: "A3F9C21B", full_name: "Asha Rao", date_of_birth: "2012-01-02", grade_or_class: "Grade 8-A", academic_year_id: null, grade_level: 8,
  assigned_teacher_user_id: null, pending_parent_email: null, section: "A", roll_number: "7", gender: "female", student_mobile: "+91 98765 43210", city: "Pune",
  subjects: ["Maths", "Physics"], career_interests: null, global_education_interest: true, preferred_countries: ["Germany"], preferred_courses: null, has_photo: false,
};

let calls: { url: string; init?: RequestInit }[] = [];
beforeEach(() => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (url === "/api/v1/school/team") return new Response(JSON.stringify({ accounts: [] }));
    return new Response(JSON.stringify({ ...student, full_name: "Asha Rao" }), { status: 200 });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("SchoolStudentsPanel (ENH-025)", () => {
  it("shows section and roll number columns", () => {
    render(<SchoolStudentsPanel students={[student]} />);
    expect(screen.getByRole("columnheader", { name: "Section" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Roll no." })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "7" })).toBeTruthy();
  });

  it("edit form is grouped, pre-filled, and saving untouched keeps every value", async () => {
    render(<SchoolStudentsPanel students={[student]} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    for (const legend of ["Identity", "Class placement", "Contact", "Studies & interests"]) {
      expect(screen.getAllByRole("group", { name: legend }).length).toBeGreaterThan(0);
    }
    expect((screen.getByLabelText("City", { selector: "#edit-city" }) as HTMLInputElement).value).toBe("Pune");
    expect(document.activeElement?.id).toBe("edit-heading");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(calls.some((c) => c.init?.method === "PATCH")).toBe(true));
    const body = JSON.parse(String(calls.find((c) => c.init?.method === "PATCH")!.init!.body));
    expect(body).toMatchObject({ section: "A", roll_number: "7", gender: "female", city: "Pune", subjects: ["Maths", "Physics"], global_education_interest: true, preferred_countries: ["Germany"], date_of_birth: "2012-01-02" });
  });

  it("create form sends only filled new fields", async () => {
    render(<SchoolStudentsPanel students={[]} />);
    fireEvent.change(screen.getByLabelText("Full name", { selector: "#new-full-name" }), { target: { value: "New Kid" } });
    fireEvent.change(screen.getByLabelText("Roll number", { selector: "#new-roll" }), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Add student" }));
    await waitFor(() => expect(calls.some((c) => c.init?.method === "POST")).toBe(true));
    const body = JSON.parse(String(calls.find((c) => c.init?.method === "POST")!.init!.body));
    expect(body.roll_number).toBe("3");
    expect("city" in body).toBe(false);
  });

  it("shows a server error inside the form as an alert", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => url === "/api/v1/school/team" ? new Response(JSON.stringify({ accounts: [] })) : new Response(JSON.stringify({ detail: "roll_number '7' is already used in this grade and section for this academic year" }), { status: 409 })));
    render(<SchoolStudentsPanel students={[student]} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect((await screen.findByRole("alert")).textContent).toContain("already used");
  });

  it("empty roster points to add and bulk upload", () => {
    render(<SchoolStudentsPanel students={[]} />);
    expect(screen.getByText(/No students yet/)).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /bulk upload/i }).length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && npx vitest run tests/components/schoolStudents.test.ts tests/components/SchoolStudentsPanel.test.tsx`
Expected: FAIL — module `@/lib/schoolStudents` not found.

- [ ] **Step 3: Implement `lib/schoolStudents.ts`**

```ts
// ENH-025 (DEC-SCOPE-027): shared shape and helpers for the School student record, replacing per-component copies.

export type SchoolStudent = {
  id: string;
  student_code: string;
  full_name: string;
  date_of_birth: string | null;
  grade_or_class: string | null;
  academic_year_id: string | null;
  grade_level: number | null;
  assigned_teacher_user_id: string | null;
  pending_parent_email: string | null;
  section: string | null;
  roll_number: string | null;
  gender: string | null;
  student_mobile: string | null;
  city: string | null;
  subjects: string[] | null;
  career_interests: string[] | null;
  global_education_interest: boolean | null;
  preferred_countries: string[] | null;
  preferred_courses: string[] | null;
  has_photo: boolean;
};

export const GENDER_OPTIONS = [
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
  { value: "other", label: "Other" },
  { value: "prefer_not_to_say", label: "Prefer not to say" },
];

export const GENDER_LABEL: Record<string, string> = Object.fromEntries(GENDER_OPTIONS.map((o) => [o.value, o.label]));

const TEXT_FIELDS = ["section", "roll_number", "gender", "student_mobile", "city"] as const;
export const MASTER_LIST_FIELDS = ["subjects", "career_interests", "preferred_countries", "preferred_courses"] as const;

export function listText(value: string[] | null | undefined): string {
  return value ? value.join(", ") : "";
}

function splitList(raw: string): string[] {
  return raw.split(",").map((s) => s.trim()).filter(Boolean);
}

/** create: empty fields are omitted; edit: empty fields are sent as null so the server clears them. */
export function toMasterPayload(form: FormData, mode: "create" | "edit"): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const put = (key: string, value: unknown, empty: boolean) => {
    if (!empty) out[key] = value;
    else if (mode === "edit") out[key] = null;
  };
  for (const key of TEXT_FIELDS) {
    const raw = String(form.get(key) ?? "").trim();
    put(key, raw, raw === "");
  }
  for (const key of MASTER_LIST_FIELDS) {
    const items = splitList(String(form.get(key) ?? ""));
    put(key, items, items.length === 0);
  }
  const interest = String(form.get("global_education_interest") ?? "");
  put("global_education_interest", interest === "yes", interest === "");
  return out;
}

export function detailMessage(detail: unknown, fallback = "Something went wrong."): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return fallback;
}

export const ROSTER_COLUMNS: { name: string; required: boolean; format: string; example: string }[] = [
  { name: "full_name", required: true, format: "Text", example: "Jane Doe" },
  { name: "date_of_birth", required: false, format: "YYYY-MM-DD", example: "2015-04-12" },
  { name: "grade_or_class", required: false, format: "Text label, up to 60 characters", example: "Grade 5-A" },
  { name: "assigned_teacher_email", required: false, format: "Email of an existing Teacher at your school", example: "teacher@school.edu" },
  { name: "parent_name", required: false, format: "Text (used only when inviting a new parent)", example: "Jane's Parent" },
  { name: "parent_email", required: false, format: "Email; links or invites the parent", example: "parent@example.com" },
  { name: "grade_level", required: false, format: "Whole number 1-12", example: "5" },
  { name: "section", required: false, format: "Up to 20 characters", example: "A" },
  { name: "roll_number", required: false, format: "Up to 20 characters; unique within grade + section + year", example: "12" },
  { name: "gender", required: false, format: "female, male, other or prefer_not_to_say", example: "female" },
  { name: "student_mobile", required: false, format: "7-20 digits, spaces, + - ( )", example: "+91 98765 43210" },
  { name: "city", required: false, format: "Up to 120 characters", example: "Pune" },
  { name: "subjects", required: false, format: "List separated by ;", example: "Maths;Science" },
  { name: "career_interests", required: false, format: "List separated by ;", example: "Engineering" },
  { name: "global_education_interest", required: false, format: "yes or no", example: "yes" },
  { name: "preferred_countries", required: false, format: "List separated by ;", example: "Germany;Canada" },
  { name: "preferred_courses", required: false, format: "List separated by ;", example: "Mechanical Engineering" },
];
```

- [ ] **Step 4: Implement `SchoolStudentFields.tsx`**

```tsx
import { GENDER_OPTIONS, listText, type SchoolStudent } from "@/lib/schoolStudents";

type TeacherOption = { id: string; name: string; active: boolean };

// ENH-025: the grouped roster fields, shared by "Add one student" and "Edit" so both forms stay identical.
// Every input is pre-filled from `student` in edit mode, so saving without touching a field keeps its value.
export default function SchoolStudentFields({ idPrefix, student, teachers, includeInactiveTeachers }: { idPrefix: string; student?: SchoolStudent; teachers: TeacherOption[]; includeInactiveTeachers: boolean }) {
  const id = (name: string) => `${idPrefix}-${name}`;
  const interest = student?.global_education_interest == null ? "" : student.global_education_interest ? "yes" : "no";
  const teacherOptions = includeInactiveTeachers ? teachers : teachers.filter((t) => t.active);
  return (
    <>
      <fieldset className="form-section">
        <legend>Identity</legend>
        <div className="form-grid">
          <div className="field">
            <label htmlFor={id("full-name")}>Full name</label>
            <input id={id("full-name")} name="full_name" defaultValue={student?.full_name} required />
          </div>
          <div className="field">
            <label htmlFor={id("dob")}>Date of birth</label>
            <input id={id("dob")} name="date_of_birth" type="date" defaultValue={student?.date_of_birth ?? ""} />
          </div>
          <div className="field">
            <label htmlFor={id("gender")}>Gender</label>
            <select id={id("gender")} name="gender" defaultValue={student?.gender ?? ""}>
              <option value="">Not recorded</option>
              {GENDER_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend>Class placement</legend>
        <div className="form-grid">
          <div className="field">
            <label htmlFor={id("grade")}>Grade/Class</label>
            <input id={id("grade")} name="grade_or_class" defaultValue={student?.grade_or_class ?? ""} maxLength={60} />
          </div>
          <div className="field">
            <label htmlFor={id("grade-level")}>Grade level (1-12, optional)</label>
            <input id={id("grade-level")} name="grade_level" type="number" min={1} max={12} step={1} defaultValue={student?.grade_level ?? ""} />
          </div>
          <div className="field">
            <label htmlFor={id("section")}>Section</label>
            <input id={id("section")} name="section" defaultValue={student?.section ?? ""} maxLength={20} />
          </div>
          <div className="field">
            <label htmlFor={id("roll")}>Roll number</label>
            <input id={id("roll")} name="roll_number" defaultValue={student?.roll_number ?? ""} maxLength={20} aria-describedby={id("roll-help")} />
            <span id={id("roll-help")} className="muted field-help">Unique within the grade, section and academic year.</span>
          </div>
          <div className="field">
            <label htmlFor={id("teacher")}>Assigned Teacher</label>
            <select id={id("teacher")} name="assigned_teacher_user_id" defaultValue={student?.assigned_teacher_user_id ?? ""}>
              <option value="">Unassigned</option>
              {teacherOptions.map((t) => <option key={t.id} value={t.id}>{t.name}{t.active ? "" : " (inactive)"}</option>)}
            </select>
          </div>
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend>Contact</legend>
        <div className="form-grid">
          <div className="field">
            <label htmlFor={id("mobile")}>Student mobile</label>
            <input id={id("mobile")} name="student_mobile" type="tel" inputMode="tel" autoComplete="off" defaultValue={student?.student_mobile ?? ""} maxLength={20} />
          </div>
          <div className="field">
            <label htmlFor={id("city")}>City</label>
            <input id={id("city")} name="city" defaultValue={student?.city ?? ""} maxLength={120} />
          </div>
          <div className="field">
            <label htmlFor={id("parent-name")}>Parent&apos;s name</label>
            <input id={id("parent-name")} name="parent_name" placeholder="Only used if this parent has no account yet" />
          </div>
          <div className="field">
            <label htmlFor={id("parent-email")}>Parent&apos;s email</label>
            <input id={id("parent-email")} name="parent_email" type="email" defaultValue={student?.pending_parent_email ?? ""} placeholder="Sends an invite if they don't have an account yet" />
          </div>
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend>Studies &amp; interests</legend>
        <p id={id("list-help")} className="muted field-help">Separate multiple values with commas.</p>
        <div className="form-grid">
          {([["subjects", "Subjects"], ["career_interests", "Career interests"], ["preferred_countries", "Preferred countries"], ["preferred_courses", "Preferred courses"]] as const).map(([name, label]) => (
            <div className="field" key={name}>
              <label htmlFor={id(name)}>{label}</label>
              <input id={id(name)} name={name} defaultValue={listText(student?.[name])} aria-describedby={id("list-help")} />
            </div>
          ))}
          <div className="field">
            <label htmlFor={id("global")}>Interested in studying abroad</label>
            <select id={id("global")} name="global_education_interest" defaultValue={interest}>
              <option value="">Not recorded</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </div>
        </div>
      </fieldset>
    </>
  );
}
```

- [ ] **Step 5: Rewire `SchoolStudentsPanel.tsx`**

Changes (keep everything else, including the link-parent card and teacher fetch):
1. Replace the local `Student` type and `detailMessage` with imports from `@/lib/schoolStudents` (`SchoolStudent`, `detailMessage`, `toMasterPayload`); `students: SchoolStudent[]`.
2. Add `const editHeading = useRef<HTMLHeadingElement>(null)`, `const lastEditButton = useRef<HTMLButtonElement | null>(null)` and a `formMessage` state scoped per form: `const [message, setMessage] = useState<{ text: string; failed: boolean; form: "edit" | "create" | "link" } | null>(null)`.
3. `useEffect(() => { if (editingId) { editHeading.current?.focus(); editHeading.current?.scrollIntoView({ block: "start" }); } }, [editingId]);`
4. `createStudent` body: `{ full_name, grade_or_class, grade_level, date_of_birth, assigned_teacher_user_id, parent_name, parent_email, ...toMasterPayload(form, "create") }`.
5. `saveEdit` body: `{ full_name, grade_or_class: … || null, grade_level: … ?? null, date_of_birth: form.get("date_of_birth") || null, assigned_teacher_user_id: … || null, parent_name, parent_email, ...toMasterPayload(form, "edit") }`. On success and on Cancel: `setEditingId(null); lastEditButton.current?.focus();`.
6. Table header: `<th>Student ID</th><th>Name</th><th>Grade/Class</th><th>Section</th><th>Roll no.</th><th>Parent</th><th>Actions</th>`; cells `<td>{s.section || "-"}</td><td>{s.roll_number || "-"}</td>`; the Edit button gets `onClick={(e) => { lastEditButton.current = e.currentTarget; setEditingId(s.id); setLinkingId(null); }}`.
7. Empty state: `<p className="muted">No students yet. Add one below, or <Link href="/school/coordinator/students/bulk-upload">use bulk upload</Link> for many at once.</p>`.
8. Edit card: `<h3 id="edit-heading" ref={editHeading} tabIndex={-1}>Edit {editing.full_name} …</h3>`; form: `<form className="form" aria-busy={busy} onSubmit={…}><fieldset disabled={busy} className="form-busy-wrap"><SchoolStudentFields idPrefix="edit" student={editing} teachers={teachers} includeInactiveTeachers />{buttons}</fieldset></form>` followed by `{message?.form === "edit" && <FormMessage message={message} />}`.
9. Create card: same pattern with `<SchoolStudentFields idPrefix="new" teachers={teachers} includeInactiveTeachers={false} />` and `message?.form === "create"`.
10. Local component at file bottom:

```tsx
function FormMessage({ message }: { message: { text: string; failed: boolean } }) {
  return message.failed
    ? <div className="form-error" role="alert">{message.text}</div>
    : <div className="form-message" role="status" aria-live="polite">{message.text}</div>;
}
```

The link-parent card renders `message?.form === "link"` the same way. Remove the old page-bottom message block.

Note the test IDs: `idPrefix="edit"` yields `edit-city`, `edit-roll`; `idPrefix="new"` yields `new-full-name`, `new-roll`. The old IDs `new-full-name`/`edit-full-name`/`new-grade`/`edit-grade`/`new-dob` are preserved by this scheme; confirm existing Playwright specs (`grep -rn "#new-\|#edit-" apps/web/tests/e2e`) still match and update any selector that referenced a removed ID.

- [ ] **Step 6: CSS** (append to `app/globals.css`)

```css
fieldset.form-section{border:1px solid var(--line);border-radius:12px;padding:14px;margin:0 0 14px;display:grid;gap:12px;min-width:0}
fieldset.form-section legend{font-weight:800;padding:0 6px}
fieldset.form-busy-wrap{border:0;padding:0;margin:0;min-width:0}
.field-help{font-size:12px}
.student-photo{width:96px;height:96px;border-radius:12px;object-fit:cover;background:var(--soft);display:inline-flex;align-items:center;justify-content:center;font-weight:800;color:var(--muted);flex-shrink:0}
.student-profile{display:grid;grid-template-columns:auto 1fr;gap:16px;align-items:start}
.student-profile dl{display:grid;grid-template-columns:max-content 1fr;gap:6px 14px;margin:0}
.student-profile dt{font-weight:700}
.student-profile dd{margin:0}
@media(max-width:640px){.student-profile{grid-template-columns:1fr}.student-profile dl{grid-template-columns:1fr}}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd apps/web && npx vitest run tests/components/schoolStudents.test.ts tests/components/SchoolStudentsPanel.test.tsx`
Expected: all PASS.

- [ ] **Step 8: Refactor + typecheck**

Run: `cd apps/web && npx tsc --noEmit && npx vitest run`
Expected: no type errors; whole vitest suite green.

- [ ] **Step 9: Commit**

```bash
git add apps/web/lib/schoolStudents.ts apps/web/components/SchoolStudentFields.tsx apps/web/components/SchoolStudentsPanel.tsx apps/web/app/globals.css apps/web/tests/components/schoolStudents.test.ts apps/web/tests/components/SchoolStudentsPanel.test.tsx
git commit -m "feat(enh-025): grouped roster forms with the student master fields"
```

---

### Task 11: Photo component and read views

**Files:**
- Create: `apps/web/components/SchoolStudentPhoto.tsx`
- Modify: `apps/web/components/SchoolStudentDetailPanel.tsx`, `apps/web/components/SchoolChildOverview.tsx`, `apps/web/components/SchoolGradeHistory.tsx`, `apps/web/app/school/coordinator/students/[id]/page.tsx`
- Test: `apps/web/tests/components/SchoolStudentPhoto.test.tsx`; extend `SchoolStudentDetailPanel.test.tsx`, `SchoolGradeHistory.test.tsx`

**Interfaces:**
- Consumes: `SchoolStudent`, `GENDER_LABEL`, `listText`, `detailMessage` (Task 10).
- Produces: `SchoolStudentPhoto({ studentId, name, hasPhoto, canEdit })`; `SchoolStudentDetailPanel` prop `canEditPhoto?: boolean`.

- [ ] **Step 1: Write the failing tests**

`tests/components/SchoolStudentPhoto.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SchoolStudentPhoto from "@/components/SchoolStudentPhoto";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const file = (type: string, size: number) => new File([new Uint8Array(size)], "p", { type });

describe("SchoolStudentPhoto", () => {
  it("shows the initials placeholder when there is no photo", () => {
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto={false} canEdit={false} />);
    expect(screen.getByRole("img", { name: "No photo for Asha Rao" }).textContent).toBe("AR");
  });

  it("renders the image and falls back to the placeholder if it fails to load", () => {
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto canEdit={false} />);
    const img = screen.getByRole("img", { name: "Photo of Asha Rao" });
    expect(img.getAttribute("src")).toContain("/api/v1/school/students/s1/photo");
    fireEvent.error(img);
    expect(screen.getByRole("img", { name: "No photo for Asha Rao" })).toBeTruthy();
  });

  it("read-only mode shows no controls", () => {
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto canEdit={false} />);
    expect(screen.queryByLabelText(/upload a photo/i)).toBeNull();
  });

  it("rejects a wrong type or oversize file before uploading", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto={false} canEdit />);
    const input = screen.getByLabelText(/upload a photo/i);
    fireEvent.change(input, { target: { files: [file("image/gif", 10)] } });
    expect((await screen.findByRole("alert")).textContent).toContain("JPEG or PNG");
    fireEvent.change(input, { target: { files: [file("image/png", 2 * 1024 * 1024 + 1)] } });
    expect((await screen.findByRole("alert")).textContent).toContain("2 MB");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uploads, shows busy state, then the new photo", async () => {
    let resolve!: (r: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((r) => { resolve = r; })));
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto={false} canEdit />);
    fireEvent.change(screen.getByLabelText(/upload a photo/i), { target: { files: [file("image/png", 10)] } });
    expect(await screen.findByText("Uploading…")).toBeTruthy();
    resolve(new Response(JSON.stringify({ has_photo: true })));
    expect(await screen.findByRole("img", { name: "Photo of Asha Rao" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("Photo saved");
  });

  it("remove needs confirmation and can be cancelled", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Remove photo" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Remove photo" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/school/students/s1/photo", { method: "DELETE" }));
    expect(await screen.findByRole("img", { name: "No photo for Asha Rao" })).toBeTruthy();
  });

  it("shows the server's message when upload fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "photo must be a JPEG or PNG image" }), { status: 415 })));
    render(<SchoolStudentPhoto studentId="s1" name="Asha Rao" hasPhoto={false} canEdit />);
    fireEvent.change(screen.getByLabelText(/upload a photo/i), { target: { files: [file("image/png", 10)] } });
    expect((await screen.findByRole("alert")).textContent).toBe("photo must be a JPEG or PNG image");
  });
});
```

Extend `SchoolStudentDetailPanel.test.tsx` (reuse its `api()` helper; add the new fields to its `student` fixture):

```tsx
it("ENH-025: shows the profile with Not recorded for empty values and no photo controls by default", async () => {
  api();
  render(await SchoolStudentDetailPanel({ student: { ...student, gender: "female", section: "A", roll_number: null, student_mobile: null, city: "Pune", subjects: ["Maths"], career_interests: null, global_education_interest: null, preferred_countries: null, preferred_courses: null, has_photo: false }, backHref: "/b", backLabel: "Back" }));
  expect(screen.getByText("Female")).toBeTruthy();
  expect(screen.getAllByText("Not recorded").length).toBeGreaterThan(0);
  expect(screen.queryByLabelText(/upload a photo/i)).toBeNull();
});
```

Extend `SchoolGradeHistory.test.tsx`:

```tsx
it("ENH-025: shows the previous section and roll number when recorded", () => {
  const entry = { id: "h1", action: "promoted" as const, created_at: "2026-09-20T10:00:00Z", from: { academic_year_id: "y1", academic_year_label: "2025-26", grade_level: 8, grade_or_class: "Grade 8-A", section: "A", roll_number: "7" }, to: { academic_year_id: "y2", academic_year_label: "2026-27", grade_level: 9, grade_or_class: "Grade 9-A", section: "A", roll_number: null } };
  render(<SchoolGradeHistory history={[entry]} />);
  expect(screen.getByText("Previous section A, roll number 7")).toBeTruthy();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && npx vitest run tests/components/SchoolStudentPhoto.test.tsx tests/components/SchoolStudentDetailPanel.test.tsx tests/components/SchoolGradeHistory.test.tsx`
Expected: FAIL — `SchoolStudentPhoto` missing; profile text absent.

- [ ] **Step 3: Implement `SchoolStudentPhoto.tsx`**

```tsx
"use client";

import { ChangeEvent, useState } from "react";
import { detailMessage } from "@/lib/schoolStudents";

const MAX_BYTES = 2 * 1024 * 1024;
const TYPES = ["image/jpeg", "image/png"];

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join("");
}

// ENH-025: the student photo. Served only through GET .../photo (scoped like the rest of the record); a missing
// or broken image always falls back to initials, never an error. Coordinator-only controls when `canEdit`.
export default function SchoolStudentPhoto({ studentId, name, hasPhoto, canEdit }: { studentId: string; name: string; hasPhoto: boolean; canEdit: boolean }) {
  const [present, setPresent] = useState(hasPhoto);
  const [broken, setBroken] = useState(false);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState<"upload" | "remove" | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const url = `/api/v1/school/students/${studentId}/photo`;

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    if (!TYPES.includes(file.type)) return setMessage({ text: "Choose a JPEG or PNG image.", failed: true });
    if (file.size > MAX_BYTES) return setMessage({ text: "The photo must be 2 MB or smaller.", failed: true });
    setBusy("upload");
    setMessage(null);
    const body = new FormData();
    body.append("file", file);
    const response = await fetch(url, { method: "PUT", body }).catch(() => null);
    setBusy(null);
    input.value = "";
    if (!response?.ok) {
      const data = response ? await response.json().catch(() => ({})) : {};
      return setMessage({ text: detailMessage(data.detail, "Upload failed; please try again."), failed: true });
    }
    setPresent(true);
    setBroken(false);
    setVersion((v) => v + 1);
    setMessage({ text: "Photo saved.", failed: false });
  }

  async function remove() {
    setBusy("remove");
    setMessage(null);
    const response = await fetch(url, { method: "DELETE" }).catch(() => null);
    setBusy(null);
    setConfirming(false);
    if (!response?.ok) return setMessage({ text: "Could not remove the photo; please try again.", failed: true });
    setPresent(false);
    setMessage({ text: "Photo removed.", failed: false });
  }

  const showImage = present && !broken;
  return (
    <div className="student-photo-block">
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element -- authenticated, uncacheable API image; next/image would proxy it
        <img className="student-photo" src={`${url}?v=${version}`} alt={`Photo of ${name}`} width={96} height={96} onError={() => setBroken(true)} />
      ) : (
        <span className="student-photo" role="img" aria-label={`No photo for ${name}`}>{initials(name)}</span>
      )}
      {canEdit && (
        <div className="field" style={{ marginTop: 8 }}>
          <label htmlFor={`photo-${studentId}`}>{present ? "Replace photo" : "Upload a photo"} (JPEG or PNG, up to 2 MB)</label>
          <input id={`photo-${studentId}`} type="file" accept="image/jpeg,image/png" onChange={upload} disabled={busy !== null} />
          {busy === "upload" && <span className="muted" aria-live="polite">Uploading…</span>}
          {present && !confirming && <button type="button" className="btn ghost small" onClick={() => setConfirming(true)} disabled={busy !== null}>Remove photo</button>}
          {confirming && (
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" className="btn small" onClick={remove} disabled={busy !== null}>{busy === "remove" ? "Removing…" : "Confirm remove"}</button>
              <button type="button" className="btn secondary small" onClick={() => setConfirming(false)}>Cancel</button>
            </div>
          )}
        </div>
      )}
      {message && (message.failed ? <div className="form-error" role="alert">{message.text}</div> : <div className="form-message" role="status" aria-live="polite">{message.text}</div>)}
    </div>
  );
}
```

- [ ] **Step 4: Wire the read views**

`SchoolStudentDetailPanel.tsx`: replace the local `Student` type with `SchoolStudent` from `@/lib/schoolStudents` (make the extra fields optional-tolerant: type the prop as `SchoolStudent`); add prop `canEditPhoto = false`; replace the header card body with:

```tsx
      <div className="card">
        <h2>{student.full_name} <span className="muted" style={{ fontSize: 14 }}>({student.student_code})</span></h2>
        <div className="student-profile">
          <SchoolStudentPhoto studentId={student.id} name={student.full_name} hasPhoto={student.has_photo} canEdit={canEditPhoto} />
          <dl>
            <dt>Grade/Class</dt><dd>{student.grade_or_class || "-"}</dd>
            <dt>Date of birth</dt><dd>{formatDate(student.date_of_birth)}</dd>
            {PROFILE_ROWS.map(([label, value]) => {
              const shown = value(student);
              return [<dt key={`${label}-t`}>{label}</dt>, <dd key={`${label}-d`} className={shown ? undefined : "muted"}>{shown || "Not recorded"}</dd>];
            })}
          </dl>
        </div>
        {pending && <p><span className="status pending">Transfer requested</span> to {pending.to_school.name}</p>}
        <a className="btn secondary" href={backHref}>{backLabel}</a>
      </div>
```

with, at module level:

```tsx
const PROFILE_ROWS: [string, (s: SchoolStudent) => string][] = [
  ["Gender", (s) => (s.gender ? GENDER_LABEL[s.gender] ?? s.gender : "")],
  ["Section", (s) => s.section ?? ""],
  ["Roll number", (s) => s.roll_number ?? ""],
  ["Student mobile", (s) => s.student_mobile ?? ""],
  ["City", (s) => s.city ?? ""],
  ["Subjects", (s) => listText(s.subjects)],
  ["Career interests", (s) => listText(s.career_interests)],
  ["Interested in studying abroad", (s) => (s.global_education_interest == null ? "" : s.global_education_interest ? "Yes" : "No")],
  ["Preferred countries", (s) => listText(s.preferred_countries)],
  ["Preferred courses", (s) => listText(s.preferred_courses)],
];
```

Coordinator page `app/school/coordinator/students/[id]/page.tsx`: import `SchoolStudent` type instead of the local `Student`, and pass `canEditPhoto` to `SchoolStudentDetailPanel`. Principal/teacher pages: switch their local `Student` type to `SchoolStudent` only if TypeScript requires it; they pass no `canEditPhoto`.

`SchoolChildOverview.tsx`: add `section`, `roll_number`, `has_photo` (optional in the type: `section?: string | null; roll_number?: string | null; has_photo?: boolean`) to `ChildOverview.student`; in the header card insert `<SchoolStudentPhoto studentId={s.id} name={s.full_name} hasPhoto={Boolean(s.has_photo)} canEdit={false} />` above the School line and `<p><strong>Section / Roll number:</strong> {s.section || "-"} / {s.roll_number || "-"}</p>` below Grade/Class.

`SchoolGradeHistory.tsx`: `State` gains `section?: string | null; roll_number?: string | null`; inside `.jtl-body` after the academic-year line add:

```tsx
              {(h.from.section || h.from.roll_number) && (
                <p className="jtl-detail">Previous section {h.from.section || "-"}, roll number {h.from.roll_number || "-"}</p>
              )}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/web && npx vitest run tests/components/SchoolStudentPhoto.test.tsx tests/components/SchoolStudentDetailPanel.test.tsx tests/components/SchoolGradeHistory.test.tsx tests/components/SchoolChildOverview.skills.test.tsx`
Expected: all PASS.

- [ ] **Step 6: Typecheck + full vitest**

Run: `cd apps/web && npx tsc --noEmit && npx vitest run`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/SchoolStudentPhoto.tsx apps/web/components/SchoolStudentDetailPanel.tsx apps/web/components/SchoolChildOverview.tsx apps/web/components/SchoolGradeHistory.tsx "apps/web/app/school/coordinator/students/[id]/page.tsx" apps/web/tests/components/SchoolStudentPhoto.test.tsx apps/web/tests/components/SchoolStudentDetailPanel.test.tsx apps/web/tests/components/SchoolGradeHistory.test.tsx
git commit -m "feat(enh-025): student photo and profile in the read views"
```

---

### Task 12: Counselor card and bulk column reference

**Files:**
- Create: `apps/web/components/CareerPreferencesCard.tsx`
- Modify: `apps/web/components/SchoolCareerRecordsPanel.tsx`, `apps/web/components/SchoolBulkUploadPanel.tsx`
- Test: `apps/web/tests/components/CareerPreferencesCard.test.tsx`, `apps/web/tests/components/SchoolBulkUploadPanel.test.tsx` (create if absent)

**Interfaces:**
- Consumes: `listText`, `detailMessage`, `ROSTER_COLUMNS` (Task 10).
- Produces: `CareerPreferencesCard({ students }: { students: { id: string; full_name: string; school_name: string }[] })`.

- [ ] **Step 1: Write the failing tests**

`tests/components/CareerPreferencesCard.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CareerPreferencesCard from "@/components/CareerPreferencesCard";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const students = [{ id: "s1", full_name: "Asha Rao", school_name: "Sunrise" }];
const prefs = { student_id: "s1", career_interests: ["Design"], global_education_interest: true, preferred_countries: null, preferred_courses: null };

describe("CareerPreferencesCard", () => {
  it("loads the selected student's preferences with a busy state", async () => {
    let resolve!: (r: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((r) => { resolve = r; })));
    render(<CareerPreferencesCard students={students} />);
    fireEvent.change(screen.getByLabelText("Student"), { target: { value: "s1" } });
    expect(await screen.findByText("Loading…")).toBeTruthy();
    resolve(new Response(JSON.stringify(prefs)));
    expect(((await screen.findByLabelText("Career interests")) as HTMLInputElement).value).toBe("Design");
  });

  it("shows an error with Retry when loading fails", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response("{}", { status: 500 })).mockResolvedValueOnce(new Response(JSON.stringify(prefs)));
    vi.stubGlobal("fetch", fetchMock);
    render(<CareerPreferencesCard students={students} />);
    fireEvent.change(screen.getByLabelText("Student"), { target: { value: "s1" } });
    expect((await screen.findByRole("alert")).textContent).toContain("Could not load");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByLabelText("Career interests")).toBeTruthy();
  });

  it("saves only the four career fields", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(prefs))).mockResolvedValueOnce(new Response(JSON.stringify(prefs)));
    vi.stubGlobal("fetch", fetchMock);
    render(<CareerPreferencesCard students={students} />);
    fireEvent.change(screen.getByLabelText("Student"), { target: { value: "s1" } });
    fireEvent.change(await screen.findByLabelText("Preferred countries"), { target: { value: "Japan, Korea" } });
    fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/v1/school/students/s1/career-preferences");
    expect(Object.keys(JSON.parse(init.body)).sort()).toEqual(["career_interests", "global_education_interest", "preferred_countries", "preferred_courses"]);
    expect(await screen.findByRole("status")).toBeTruthy();
  });

  it("empty portfolio shows the existing message", () => {
    render(<CareerPreferencesCard students={[]} />);
    expect(screen.getByText(/No students in your portfolio yet/)).toBeTruthy();
  });
});
```

`tests/components/SchoolBulkUploadPanel.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SchoolBulkUploadPanel from "@/components/SchoolBulkUploadPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
afterEach(cleanup);

describe("SchoolBulkUploadPanel column reference (ENH-025)", () => {
  it("lists every template column and the photo exception", () => {
    render(<SchoolBulkUploadPanel />);
    expect(screen.getByText("Column reference")).toBeTruthy();
    for (const name of ["full_name", "section", "roll_number", "preferred_courses"]) expect(screen.getByRole("cell", { name })).toBeTruthy();
    expect(screen.getByText(/Photos can't be uploaded in the CSV/)).toBeTruthy();
  });
});
```

(Check `SchoolBulkUploadPanel`'s props first; if it takes props, pass minimal ones.)

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && npx vitest run tests/components/CareerPreferencesCard.test.tsx tests/components/SchoolBulkUploadPanel.test.tsx`
Expected: FAIL — component missing; no column reference.

- [ ] **Step 3: Implement `CareerPreferencesCard.tsx`**

```tsx
"use client";

import { FormEvent, useState } from "react";
import { detailMessage, listText } from "@/lib/schoolStudents";

type Prefs = { student_id: string; career_interests: string[] | null; global_education_interest: boolean | null; preferred_countries: string[] | null; preferred_courses: string[] | null };
type Student = { id: string; full_name: string; school_name: string };
const LISTS = [["career_interests", "Career interests"], ["preferred_countries", "Preferred countries"], ["preferred_courses", "Preferred courses"]] as const;

const split = (raw: FormDataEntryValue | null) => String(raw ?? "").split(",").map((s) => s.trim()).filter(Boolean);

// ENH-025 (DEC-SCOPE-027 item 2): a Career Counsellor records a portfolio student's career interests and study-abroad
// preferences. Only these four fields are sent; the server rejects anything else.
export default function CareerPreferencesCard({ students }: { students: Student[] }) {
  const [studentId, setStudentId] = useState("");
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error" | "saving">("idle");
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  async function load(id: string) {
    setState("loading");
    setPrefs(null);
    setMessage(null);
    const response = await fetch(`/api/v1/school/students/${id}/career-preferences`).catch(() => null);
    if (!response?.ok) return setState("error");
    setPrefs(await response.json());
    setState("idle");
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const interest = String(form.get("global_education_interest") ?? "");
    const body = {
      career_interests: split(form.get("career_interests")),
      preferred_countries: split(form.get("preferred_countries")),
      preferred_courses: split(form.get("preferred_courses")),
      global_education_interest: interest === "" ? null : interest === "yes",
    };
    setState("saving");
    setMessage(null);
    const response = await fetch(`/api/v1/school/students/${studentId}/career-preferences`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => null);
    const data = response ? await response.json().catch(() => ({})) : {};
    setState("idle");
    if (!response?.ok) return setMessage({ text: detailMessage(data.detail, "Could not save; please try again."), failed: true });
    setPrefs(data);
    setMessage({ text: "Career preferences saved.", failed: false });
  }

  return (
    <div className="action-card">
      <h3>Career preferences</h3>
      {students.length === 0 ? (
        <p className="muted">No students in your portfolio yet. Contact your Overseas Admin.</p>
      ) : (
        <>
          <div className="field">
            <label htmlFor="prefs-student">Student</label>
            <select id="prefs-student" value={studentId} onChange={(e) => { setStudentId(e.target.value); if (e.target.value) load(e.target.value); }}>
              <option value="" disabled>Select student</option>
              {students.map((s) => <option key={s.id} value={s.id}>{s.full_name} — {s.school_name}</option>)}
            </select>
          </div>
          {state === "loading" && <p className="muted" aria-busy="true" aria-live="polite">Loading…</p>}
          {state === "error" && (
            <div className="form-error" role="alert">
              Could not load this student&apos;s preferences. <button type="button" className="btn ghost small" onClick={() => load(studentId)}>Retry</button>
            </div>
          )}
          {prefs && (
            <form className="form" onSubmit={save} aria-busy={state === "saving"} key={prefs.student_id}>
              <fieldset className="form-busy-wrap" disabled={state === "saving"}>
                <p id="prefs-help" className="muted field-help">Separate multiple values with commas.</p>
                {LISTS.map(([name, label]) => (
                  <div className="field" key={name}>
                    <label htmlFor={`prefs-${name}`}>{label}</label>
                    <input id={`prefs-${name}`} name={name} defaultValue={listText(prefs[name])} aria-describedby="prefs-help" />
                  </div>
                ))}
                <div className="field">
                  <label htmlFor="prefs-global">Interested in studying abroad</label>
                  <select id="prefs-global" name="global_education_interest" defaultValue={prefs.global_education_interest == null ? "" : prefs.global_education_interest ? "yes" : "no"}>
                    <option value="">Not recorded</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </div>
                <button className="btn">{state === "saving" ? "Saving…" : "Save preferences"}</button>
              </fieldset>
            </form>
          )}
          {message && (message.failed ? <div className="form-error" role="alert">{message.text}</div> : <div className="form-message" role="status" aria-live="polite">{message.text}</div>)}
        </>
      )}
    </div>
  );
}
```

In `SchoolCareerRecordsPanel.tsx`, render `<CareerPreferencesCard students={students} />` after the "Add a record" card.

- [ ] **Step 4: Bulk column reference**

In `SchoolBulkUploadPanel.tsx`, import `ROSTER_COLUMNS`; replace the long "Columns: …" sentence with `<p className="muted">Fill it in offline, then upload it below. Only full name is required.</p>` and add after the download button:

```tsx
        <details style={{ marginTop: 12 }}>
          <summary><strong>Column reference</strong></summary>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Column</th><th>Required</th><th>Format</th><th>Example</th></tr></thead>
              <tbody>
                {ROSTER_COLUMNS.map((c) => (
                  <tr key={c.name}><td><code>{c.name}</code></td><td>{c.required ? "Yes" : "No"}</td><td>{c.format}</td><td>{c.example}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted field-help">Photos can&apos;t be uploaded in the CSV — add them from each student&apos;s page after the upload.</p>
        </details>
```

The test queries `getByRole("cell", { name: "full_name" })`; the `<code>` inside the cell keeps the cell's accessible name as the text.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/web && npx vitest run tests/components/CareerPreferencesCard.test.tsx tests/components/SchoolBulkUploadPanel.test.tsx && npx tsc --noEmit && npx vitest run`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/CareerPreferencesCard.tsx apps/web/components/SchoolCareerRecordsPanel.tsx apps/web/components/SchoolBulkUploadPanel.tsx apps/web/tests/components/CareerPreferencesCard.test.tsx apps/web/tests/components/SchoolBulkUploadPanel.test.tsx
git commit -m "feat(enh-025): counsellor career-preferences card and bulk column reference"
```

---

### Task 13: Contract/data-model docs, Playwright, targeted regression

**Files:**
- Modify: `docs/architecture/API_CONTRACT.md` (§12A roster template; school student endpoints), `docs/architecture/DATA_MODEL.md` (§6.11), `docs/quality/RTM.md`
- Modify: `apps/web/tests/e2e/sch-002-bulk-roster-upload.spec.ts`
- Create: `apps/web/tests/e2e/enh-025-student-master-fields.spec.ts`

- [ ] **Step 1: Docs**

`API_CONTRACT.md` §12A: replace the template column list with the 17-column table from `ROSTER_COLUMNS` (column, required, format, example) and the Photo exception sentence; add the five new routes (§3.4 of the spec) with role, statuses and headers; note additive response keys + `has_photo`. `DATA_MODEL.md` §6.11: add the §2.1 table, the index, the history columns. `RTM.md`: add ENH-025 rows mapping AC1–AC12 → test files (`test_enh_025_*.py`, vitest files, the Playwright spec), and the Photo-not-in-bulk exception.

- [ ] **Step 2: Playwright**

First read `apps/web/tests/e2e/sch-002-bulk-roster-upload.spec.ts` and `enh-012-digital-portfolio.spec.ts` for the login/seed helpers and reuse them exactly. In `sch-002`, add one test that downloads the template, asserts the header row starts with the original seven and contains `section,roll_number`, uploads a CSV row with `section=A,roll_number=5,gender=female,city=Pune`, and asserts "1 of 1 row accepted". Create `enh-025-student-master-fields.spec.ts` with:
1. Coordinator: open roster → Edit a seeded student → set Section, Roll number, Gender, City, Subjects → Save → row shows the section/roll; open the student page → Profile shows the values; upload `tests/e2e/fixtures/enh025-photo.png` (create a 1×1 PNG fixture via the helper bytes) → image `Photo of …` visible; Remove → Confirm → initials placeholder.
2. Teacher (seeded, assigned): student page shows the same Profile values, no upload control.
3. Career counsellor: dashboard → Career preferences → select student → set Preferred countries → Save → status message.
4. Same as (1)'s form at `page.setViewportSize({ width: 375, height: 800 })`: every fieldset visible, no horizontal scroll (`document.documentElement.scrollWidth <= 375`).

- [ ] **Step 3: Run the targeted suites** (the user's stack must be up; do not start it)

```bash
cd apps/api && pytest tests/test_enh_025_*.py tests/test_sch_001_school_portal_access.py tests/test_sch_002_bulk_roster_upload.py tests/test_sch_roster_parent_invite.py tests/test_enh_001_academic_year.py tests/test_enh_004_student_promotion.py tests/test_enh_005_*.py tests/test_sch_reports.py tests/test_enh_012_digital_portfolio.py -q
cd ../web && npx tsc --noEmit && npx vitest run && npx playwright test tests/e2e/enh-025-student-master-fields.spec.ts tests/e2e/sch-002-bulk-roster-upload.spec.ts tests/e2e/enh-004-student-promotion.spec.ts tests/e2e/enh-005-school-transfer.spec.ts tests/e2e/sch-001-school-portal-access.spec.ts
```

Expected: all green. Record the exact pass/fail counts in the task report; any failure goes through superpowers:systematic-debugging before any fix. Do **not** alter product behavior to make a draft test pass.

- [ ] **Step 4: Commit**

```bash
git add docs/architecture/API_CONTRACT.md docs/architecture/DATA_MODEL.md docs/quality/RTM.md apps/web/tests/e2e/sch-002-bulk-roster-upload.spec.ts apps/web/tests/e2e/enh-025-student-master-fields.spec.ts apps/web/tests/e2e/fixtures
git commit -m "test(enh-025): e2e coverage, contract and data-model docs, RTM"
```

**Not in this plan (by instruction):** claiming completion. After Task 13: browser validation and an independent Codex review, then the completion gates.
