# ENH-026 Career Counselling Record + ENH-021 Internship Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Structured §7 counselling records with the status lifecycle (ENH-026), and §22 internship tracking with a
certificate on the portfolio `internship` section (ENH-021), feeding the dashboard KPI/chart, entitlement usage and
Student 360°, with no change to existing data or contracts beyond additive fields.

**Architecture:** Additive nullable columns on `school_career_records` (migration 0042) and `portfolio_entries`
(migration 0043). Existing routes are extended; one new PATCH (career records) and one new module
(`portfolio_certificates.py`) are added. All scope, tier and upload rules reuse existing helpers in `schools.py`,
`portfolio.py`, `school_student_profile.py`, `services/storage.py`, `services/image_metadata.py`.

**Tech Stack:** FastAPI + SQLAlchemy 2 async + Alembic + PostgreSQL (pytest, real DB); Next.js App Router + React
(vitest + Testing Library); Playwright E2E.

**Spec:** `docs/superpowers/specs/2026-09-27-enh-021-026-internship-and-counselling-record-design.md` (decisions
C1–C14, I1–I8, reviews A1–A10, F1–F10, S1–S13). Decision register: `DEC-SCOPE-031`, `DEC-SCOPE-032`.

## Global Constraints

- Branch `feature/enh-021-026-internship-counselling-record`, worktree `.claude/worktrees/enh-021_enh-26`. Never `cd`
  outside it; never bare `git stash`.
- The user runs `docker compose`; never start/stop it. Apply migrations with `cd apps/api && alembic upgrade head`
  before backend tests.
- TDD for every behaviour: RED (write test, run, see the expected failure) → GREEN (minimum code, run, pass) →
  REFACTOR (rerun). Record the failing output reason in the task notes.
- Additive only: no existing column/key renamed, retyped or removed; no data backfilled.
- Existing tests must pass **unmodified**, except the two assertions changed by requirement in Task 12
  (`test_sch_reports.py:302,305`, `test_sch_011_entitlements.py:137`).
- Error shapes: career-record routes return string `detail` (via `_master_fields_or_422`); portfolio routes keep
  FastAPI's list shape for schema errors and `HTTPException(422, "<text>")` for post-merge rules.
- New JSON columns use `JSON(none_as_null=True)` so a cleared list is SQL `NULL`, never JSON `'null'`.
- Lists reuse `schemas._clean_list` (≤ 20 items, each ≤ 80 chars, trimmed, case-insensitive de-dup, empty ⇒ `None`).
  (Spec §5.1 said "≤ 100 chars"; reusing the ENH-025 rule is the no-duplication choice — recorded in Task 15's doc
  update.)
- Logs: ids, counts, status names only. Never notes, strengths, weak areas, feedback, mentor names, file names or
  storage keys (key digest only).
- No new dependency (Python or npm).
- Status labels (UI and 422 text): `not_started` "Not Started", `scheduled` "Scheduled", `completed` "Completed",
  `follow_up_required` "Follow-up Required", `None` "No status".
- Backend test command: `cd apps/api && pytest <file> -v`. Web: `cd apps/web && npx vitest run <file>`.
  Types: `cd apps/web && npx tsc --noEmit`. Full regression only in Task 15.

## Review Focus

1. **A PATCH that carries the record's unchanged values** (the edit form re-sends everything) must be a no-op for
   status transitions and must not trigger the Platinum gate on an internship entry — pinned in Task 4
   (`test_patch_resending_current_values_is_a_noop`) and Task 13 (form sends only changed internship fields).
2. **Re-entering `scheduled` from `follow_up_required` without a new date** must be refused, not silently reuse the old
   `scheduled_for` — pinned in Task 4 (`test_rescheduling_requires_a_new_scheduled_for`).
3. **A legacy row edited only for notes** keeps `status = NULL` and still counts as completed — pinned in Task 4
   (`test_legacy_field_edit_keeps_status_null`) and Task 5.
4. **A Gold school editing the title/dates of an internship entry it created before ENH-021** succeeds and needs no
   Platinum — pinned in Task 9 (`test_gold_school_keeps_basic_edit_and_delete_of_existing_internships`).
5. **Upload of a file whose name/Content-Type claims PDF but whose bytes are HTML** is refused 415 — pinned in
   Task 10 (`test_type_is_decided_by_content_not_by_name`).

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/alembic/versions/0042_career_record_structured_fields.py` (new) | ENH-026 columns, CHECK, index |
| `apps/api/alembic/versions/0043_portfolio_internship_tracking.py` (new) | ENH-021 columns, CHECKs |
| `apps/api/app/models.py` (modify `SchoolCareerRecord`, `PortfolioEntry`) | ORM mirrors of both migrations |
| `apps/api/app/schemas.py` (modify) | ENH-026 constants/models; portfolio schema extensions |
| `apps/api/app/api/schools.py` (modify) | career POST/PATCH, serializer, status rules, aggregates |
| `apps/api/app/api/portfolio.py` (modify) | tracking fields, gate split, locking, certificate discard on delete |
| `apps/api/app/api/portfolio_certificates.py` (new) | certificate PUT/GET/DELETE |
| `apps/api/app/api/student_360.py` (modify) | internship programme status |
| `apps/api/app/main.py` (modify) | register the certificate router |
| `apps/api/tests/test_enh_026_migration.py`, `test_enh_026_schemas.py`, `test_enh_026_counselling_record.py`, `test_enh_026_aggregates.py` (new) | ENH-026 tests |
| `apps/api/tests/test_enh_021_migration.py`, `test_enh_021_internship.py`, `test_enh_021_certificate.py`, `test_enh_021_aggregates.py` (new) | ENH-021 tests |
| `apps/web/lib/careerRecords.ts` (new) | status labels, transition map, record type |
| `apps/web/lib/apiErrors.ts` (modify) | `SendOutcome` failure gains optional `status` |
| `apps/web/components/CareerRecordForm.tsx` (new) | create/edit form |
| `apps/web/components/CareerRecordDetails.tsx` (new) | read-only structured view (overview + 360°) |
| `apps/web/components/SchoolCareerRecordsPanel.tsx` (modify) | table columns, edit flow |
| `apps/web/app/school/career-counselor/dashboard/loading.tsx` (new) | loading skeleton |
| `apps/web/components/SchoolChildOverview.tsx`, `Student360Panels.tsx` (modify) | show status/structured fields, internship programme |
| `apps/web/components/InternshipFields.tsx`, `InternshipDetails.tsx`, `InternshipCertificate.tsx` (new) | internship form fields, read view, certificate control |
| `apps/web/components/PortfolioEntryForm.tsx`, `PortfolioPanel.tsx`, `apps/web/lib/portfolio.ts` (modify) | wire internship UI |
| `apps/web/tests/components/*.test.tsx` (new/extended) | component tests |
| `apps/web/tests/e2e/enh-026-counselling-record.spec.ts`, `enh-021-internship.spec.ts` (new) | E2E |
| `docs/quality/RTM.md`, `docs/architecture/API_CONTRACT.md`, `docs/architecture/DATA_MODEL.md`, `docs/delivery/ENHANCEMENT_BACKLOG.md` (modify) | traceability |

---

# Part 1 — ENH-026

### Task 1: Migration 0042 and `SchoolCareerRecord` columns

**Files:**
- Create: `apps/api/alembic/versions/0042_career_record_structured_fields.py`
- Modify: `apps/api/app/models.py:1257-1266` (`SchoolCareerRecord`)
- Test: `apps/api/tests/test_enh_026_migration.py`

**Interfaces:**
- Produces: ORM attributes `status, scheduled_for, completed_on, next_follow_up_date, career_interests,
  global_education_interest, academic_strengths, weak_areas, recommended_careers, recommended_courses,
  recommended_stream, recommended_skills, parent_participated, parent_participation_note, updated_by_user_id` on
  `SchoolCareerRecord`; constraint `ck_career_record_status`; index `ix_school_career_records_student_type_status`.

- [ ] **Step 0: Confirm the migration head is free**

Run: `cd apps/api && alembic heads`
Expected: `0041_student_master_fields (head)`. If another head exists, renumber this migration and 0043 to follow it
and note the re-chain in the docstring (precedent: 0041's docstring).

- [ ] **Step 1: Write the failing test**

```python
"""ENH-026 -- school_career_records structured fields (spec §4.1, DEC-SCOPE-031): additive, nullable, no backfill."""
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from enh005_helpers import mk_school, mk_staff
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import SchoolCareerRecord

NEW_COLUMNS = {
    "status": "character varying", "scheduled_for": "timestamp with time zone", "completed_on": "date",
    "next_follow_up_date": "date", "career_interests": "json", "global_education_interest": "boolean",
    "academic_strengths": "json", "weak_areas": "json", "recommended_careers": "json", "recommended_courses": "json",
    "recommended_stream": "json", "recommended_skills": "json", "parent_participated": "boolean",
    "parent_participation_note": "character varying", "updated_by_user_id": "uuid",
}


@pytest.mark.asyncio
async def test_new_columns_exist_nullable_without_default(db_session):
    rows = (await db_session.execute(text(
        "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
        "WHERE table_name = 'school_career_records'"
    ))).all()
    found = {r[0]: r for r in rows}
    for name, data_type in NEW_COLUMNS.items():
        assert name in found, f"{name} missing -- migration 0042 not applied"
        assert found[name][1:] == (data_type, "YES", None), name


@pytest.mark.asyncio
async def test_alembic_is_at_head_and_includes_0042(db_session):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    script = ScriptDirectory.from_config(config)
    version = await db_session.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == script.get_current_head()
    assert "0042_career_record_structured_fields" in {rev.revision for rev in script.iterate_revisions(version, "base")}


@pytest.mark.asyncio
async def test_a_record_written_the_old_way_has_every_new_field_null(db_session):
    ctx = await mk_school(db_session, label="E26-Mig")
    counselor = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    record = SchoolCareerRecord(school_student_id=ctx["students"][0].id, career_counselor_user_id=counselor.id, record_type="counselling_note", notes="old")
    db_session.add(record)
    await db_session.commit()
    raw = (await db_session.execute(text(
        "SELECT " + ", ".join(NEW_COLUMNS) + " FROM school_career_records WHERE id = :id"), {"id": record.id})).one()
    assert all(value is None for value in raw)  # SQL NULL, never JSON 'null'


@pytest.mark.asyncio
async def test_status_check_rejects_an_unknown_value(db_session):
    ctx = await mk_school(db_session, label="E26-Chk")
    counselor = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    db_session.add(SchoolCareerRecord(school_student_id=ctx["students"][0].id, career_counselor_user_id=counselor.id, record_type="counselling_note", notes="n", status="done"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/api && pytest tests/test_enh_026_migration.py -v`
Expected: FAIL — `status missing -- migration 0042 not applied` (and a `TypeError: 'status' is an invalid keyword`
for the CHECK test).

- [ ] **Step 3: Write the migration**

```python
"""ENH-026 -- structured Counselling Record fields on school_career_records.

Revision ID: 0042_career_record_structured_fields
Revises: 0041_student_master_fields

docs/superpowers/specs/2026-09-27-enh-021-026-internship-and-counselling-record-design.md §4.1 (DEC-SCOPE-031).
Additive only: nullable columns, a CHECK on status, one index. No backfill -- existing rows keep status NULL, which
the application treats as "recorded before tracking" (C4/C5). `downgrade()` drops exactly what this adds.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0042_career_record_structured_fields"
down_revision = "0041_student_master_fields"
branch_labels = None
depends_on = None

TABLE = "school_career_records"
JSON = postgresql.JSON(none_as_null=True)
COLUMNS = (
    ("status", sa.String(30)), ("scheduled_for", sa.DateTime(timezone=True)), ("completed_on", sa.Date()),
    ("next_follow_up_date", sa.Date()), ("career_interests", JSON), ("global_education_interest", sa.Boolean()),
    ("academic_strengths", JSON), ("weak_areas", JSON), ("recommended_careers", JSON), ("recommended_courses", JSON),
    ("recommended_stream", JSON), ("recommended_skills", JSON), ("parent_participated", sa.Boolean()),
    ("parent_participation_note", sa.String(500)),
)
STATUS_CHECK = "status IS NULL OR status IN ('not_started', 'scheduled', 'completed', 'follow_up_required')"
INDEX = "ix_school_career_records_student_type_status"


def upgrade() -> None:
    # Guarded like 0041: 0001_initial builds tables from the current models, so on a from-scratch replay these exist.
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns(TABLE)}
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
    if "updated_by_user_id" not in existing:
        op.add_column(TABLE, sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", name="fk_school_career_records_updated_by"), nullable=True))
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints(TABLE)}
    if "ck_career_record_status" not in checks:
        op.create_check_constraint("ck_career_record_status", TABLE, STATUS_CHECK)
    indexes = set() if offline else {i["name"] for i in inspector.get_indexes(TABLE)}
    if INDEX not in indexes:
        op.create_index(INDEX, TABLE, ["school_student_id", "record_type", "status"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_constraint("ck_career_record_status", TABLE, type_="check")
    op.drop_column(TABLE, "updated_by_user_id")
    for name, _type in reversed(COLUMNS):
        op.drop_column(TABLE, name)
```

- [ ] **Step 4: Mirror it in the model** (`models.py`, replace the `SchoolCareerRecord` class body)

```python
class SchoolCareerRecord(Base, TimestampMixin):
    """SCH-004 -- Career Guidance & Counselling. Net-new, `DATA_MODEL.md` §6.17. No
    Draft/Published gate -- visible to readers as soon as it's created.
    ENH-026 (DEC-SCOPE-031): the §7 structured fields and status lifecycle, all nullable. `status` NULL means the
    record predates tracking (or is a `recommendation`, which never has one)."""

    __tablename__ = "school_career_records"
    __table_args__ = (
        CheckConstraint("status IS NULL OR status IN ('not_started', 'scheduled', 'completed', 'follow_up_required')", name="ck_career_record_status"),
        Index("ix_school_career_records_student_type_status", "school_student_id", "record_type", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    career_counselor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    record_type: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    career_interests: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    global_education_interest: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    academic_strengths: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    weak_areas: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    recommended_careers: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    recommended_courses: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    recommended_stream: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    recommended_skills: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    parent_participated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    parent_participation_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
```

(`CheckConstraint`, `Index`, `Date`, `DateTime`, `Boolean`, `JSON` are already imported in `models.py`; confirm with
`grep -n "^from sqlalchemy import" apps/api/app/models.py` and add any missing name to that import.)

- [ ] **Step 5: Apply and run**

Run: `cd apps/api && alembic upgrade head && pytest tests/test_enh_026_migration.py -v`
Expected: 4 passed.

- [ ] **Step 6: Round-trip the migration**

Run: `cd apps/api && alembic downgrade -1 && alembic upgrade head && pytest tests/test_enh_026_migration.py tests/test_sch_004_career_guidance.py -v`
Expected: all pass (existing SCH-004 tests unmodified).

- [ ] **Step 7: Commit**

```bash
git add apps/api/alembic/versions/0042_career_record_structured_fields.py apps/api/app/models.py apps/api/tests/test_enh_026_migration.py
git commit -m "feat(enh-026): add structured counselling-record columns (migration 0042)"
```

---

### Task 2: ENH-026 schemas and pure status rules

**Files:**
- Modify: `apps/api/app/schemas.py` (new block after the ENH-025 block, before `# --- ENH-005`)
- Test: `apps/api/tests/test_enh_026_schemas.py`

**Interfaces:**
- Consumes: `_clean_list`, `_clean_text`, `StrictBool` (already in `schemas.py`).
- Produces:
  - `CAREER_STATUSES: tuple[str, ...]`, `CAREER_STATUS_LABEL: dict[str | None, str]`
  - `STRUCTURED_RECORD_TYPES: frozenset[str]` = `{"guidance_session", "counselling_note"}`
  - `CAREER_RECORD_TYPES: tuple[str, ...]` = `("guidance_session", "counselling_note", "recommendation")`
  - `CAREER_STATUS_INITIAL: frozenset[str]`, `CAREER_STATUS_NEXT: dict[str | None, frozenset[str]]`
  - `CAREER_LIST_KEYS`, `CAREER_STRUCTURED_KEYS`, `CAREER_DATE_KEYS: tuple[str, ...]`
  - `COUNTED_CAREER_STATUSES: tuple[str, ...]` = `("completed", "follow_up_required")`
  - `career_transition_allowed(current: str | None, requested: str) -> bool`
  - `counts_as_completed(status: str | None) -> bool`
  - `class CareerRecordFields(BaseModel)` (create body minus `school_student_id`/`record_type`)
  - `class CareerRecordUpdate(CareerRecordFields)` adds `expected_status`

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-026 -- schema and pure-rule tests (spec §3.1 C1-C8, §11.1 A4/A5/A10)."""
import pytest
from pydantic import ValidationError

from app.schemas import (
    CAREER_STATUS_LABEL, CareerRecordFields, CareerRecordUpdate, career_transition_allowed, counts_as_completed,
)


@pytest.mark.parametrize("current,requested,allowed", [
    ("not_started", "scheduled", True), ("not_started", "completed", False), ("not_started", "follow_up_required", False),
    ("scheduled", "completed", True), ("scheduled", "not_started", False),
    ("completed", "follow_up_required", True), ("completed", "scheduled", False),
    ("follow_up_required", "scheduled", True), ("follow_up_required", "completed", True), ("follow_up_required", "not_started", False),
    (None, "completed", True), (None, "follow_up_required", True), (None, "not_started", False), (None, "scheduled", False),
    ("scheduled", "scheduled", True),  # re-sending the current status is a no-op
])
def test_transitions_follow_the_section_7_lifecycle(current, requested, allowed):
    assert career_transition_allowed(current, requested) is allowed


@pytest.mark.parametrize("status,counted", [(None, True), ("completed", True), ("follow_up_required", True), ("not_started", False), ("scheduled", False)])
def test_counts_as_completed(status, counted):
    assert counts_as_completed(status) is counted


def test_labels_cover_every_status_and_legacy():
    assert CAREER_STATUS_LABEL == {"not_started": "Not Started", "scheduled": "Scheduled", "completed": "Completed", "follow_up_required": "Follow-up Required", None: "No status"}


def test_lists_are_cleaned_and_empty_means_none():
    fields = CareerRecordFields.model_validate({"weak_areas": [" Algebra ", "algebra", ""], "recommended_careers": []})
    assert fields.weak_areas == ["Algebra"]
    assert fields.recommended_careers is None


def test_scheduled_for_must_be_timezone_aware():
    with pytest.raises(ValidationError):
        CareerRecordFields.model_validate({"scheduled_for": "2026-10-01T10:00:00"})
    assert CareerRecordFields.model_validate({"scheduled_for": "2026-10-01T10:00:00+05:30"}).scheduled_for is not None


@pytest.mark.parametrize("key", ["career_counselor_user_id", "updated_by_user_id", "school_student_id", "record_type", "id"])
def test_owner_and_identity_fields_are_not_writable(key):
    with pytest.raises(ValidationError):
        CareerRecordUpdate.model_validate({key: "x"})


def test_unknown_status_is_rejected():
    with pytest.raises(ValidationError):
        CareerRecordFields.model_validate({"status": "done"})


def test_notes_keep_the_sch_004_rule_but_refuse_nul():
    assert CareerRecordFields.model_validate({"notes": "  Met parents.  "}).notes == "Met parents."
    assert CareerRecordFields.model_validate({"notes": None}).notes == ""
    with pytest.raises(ValidationError):
        CareerRecordFields.model_validate({"notes": "a\x00b"})


def test_expected_status_distinguishes_absent_from_legacy_null():
    assert "expected_status" not in CareerRecordUpdate.model_validate({}).model_fields_set
    update = CareerRecordUpdate.model_validate({"expected_status": None})
    assert "expected_status" in update.model_fields_set and update.expected_status is None


def test_parent_participation_note_is_single_line_and_capped():
    with pytest.raises(ValidationError):
        CareerRecordFields.model_validate({"parent_participation_note": "a" * 501})
    with pytest.raises(ValidationError):
        CareerRecordFields.model_validate({"parent_participation_note": "line\nbreak"})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_026_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'CAREER_STATUS_LABEL'`.

- [ ] **Step 3: Implement** (append to `schemas.py` after `validation_message`, before `# --- ENH-005`)

```python
# --- ENH-026: Career Counselling record (docs/superpowers/specs/2026-09-27-enh-021-026-internship-and-counselling-record-design.md §3.1) ---

CAREER_STATUSES: tuple[str, ...] = ("not_started", "scheduled", "completed", "follow_up_required")
CareerStatus = Literal["not_started", "scheduled", "completed", "follow_up_required"]
CAREER_STATUS_LABEL: dict[str | None, str] = {
    "not_started": "Not Started", "scheduled": "Scheduled", "completed": "Completed", "follow_up_required": "Follow-up Required", None: "No status",
}
CAREER_RECORD_TYPES: tuple[str, ...] = ("guidance_session", "counselling_note", "recommendation")
STRUCTURED_RECORD_TYPES: frozenset[str] = frozenset({"guidance_session", "counselling_note"})  # C1
CAREER_STATUS_INITIAL: frozenset[str] = frozenset({"not_started", "scheduled", "completed"})  # C2 create
CAREER_STATUS_NEXT: dict[str | None, frozenset[str]] = {  # C2 / C4 (None = a legacy row, recorded before tracking)
    "not_started": frozenset({"scheduled"}),
    "scheduled": frozenset({"completed"}),
    "completed": frozenset({"follow_up_required"}),
    "follow_up_required": frozenset({"scheduled", "completed"}),
    None: frozenset({"completed", "follow_up_required"}),
}
COUNTED_CAREER_STATUSES: tuple[str, ...] = ("completed", "follow_up_required")  # C5, plus NULL
CAREER_LIST_KEYS: tuple[str, ...] = (
    "career_interests", "academic_strengths", "weak_areas",
    "recommended_careers", "recommended_courses", "recommended_stream", "recommended_skills",
)
CAREER_STRUCTURED_KEYS: tuple[str, ...] = (*CAREER_LIST_KEYS, "global_education_interest", "parent_participated", "parent_participation_note")
CAREER_DATE_KEYS: tuple[str, ...] = ("scheduled_for", "completed_on", "next_follow_up_date")


def career_transition_allowed(current: str | None, requested: str) -> bool:
    return requested == current or requested in CAREER_STATUS_NEXT[current]


def counts_as_completed(status: str | None) -> bool:
    """C5: one rule for KPIs, overview status and entitlement usage. A legacy NULL row was a held session."""
    return status is None or status in COUNTED_CAREER_STATUSES


def _career_notes(value) -> str:
    """SCH-004's own rule, unchanged (any value, str() then strip, no length cap) -- plus NUL refused, which PostgreSQL
    text cannot store (it surfaced as a 500 before). NOT NULL column: absent/None is the empty string."""
    text_value = "" if value is None else str(value).strip()
    if "\x00" in text_value:
        raise ValueError("must not contain NUL characters")
    return text_value


class CareerRecordFields(BaseModel):
    """ENH-026 body fields shared by create and update. extra="forbid" (A10): ids, owners and record_type are never
    writable here."""

    model_config = {"extra": "forbid"}
    notes: str = ""
    status: CareerStatus | None = None
    scheduled_for: AwareDatetime | None = None
    completed_on: date | None = None
    next_follow_up_date: date | None = None
    career_interests: list[str] | None = None
    academic_strengths: list[str] | None = None
    weak_areas: list[str] | None = None
    recommended_careers: list[str] | None = None
    recommended_courses: list[str] | None = None
    recommended_stream: list[str] | None = None
    recommended_skills: list[str] | None = None
    global_education_interest: StrictBool | None = None
    parent_participated: StrictBool | None = None
    parent_participation_note: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def _notes(cls, value):
        return _career_notes(value)

    @field_validator(*CAREER_LIST_KEYS, mode="before")
    @classmethod
    def _lists(cls, value):
        return _clean_list(value)

    @field_validator("parent_participation_note", mode="before")
    @classmethod
    def _note(cls, value):
        return _clean_text(value, 500)


class CareerRecordUpdate(CareerRecordFields):
    """PATCH body. `expected_status` is an optional precondition (spec §5.1 step 5): present ⇒ must equal the locked
    record's status (None matches a legacy row), else 409."""

    expected_status: CareerStatus | None = None
```

Imports: add `AwareDatetime` to the existing `from pydantic import ...` line (confirm with
`grep -n "^from pydantic import" apps/api/app/schemas.py`); `date` and `Literal` are already imported (confirm the same
way).

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/api && pytest tests/test_enh_026_schemas.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas.py apps/api/tests/test_enh_026_schemas.py
git commit -m "feat(enh-026): counselling-record schemas and status lifecycle rules"
```

---

### Task 3: Shared serializer + extended `POST /career-counselor/records` + list endpoints

**Files:**
- Modify: `apps/api/app/api/schools.py` (`create_career_record` 1892-1915, `list_career_counselor_records`
  1918-1927, `list_readable_career_records` 1930-1940; new helpers near `_notify_student_parents`)
- Test: `apps/api/tests/test_enh_026_counselling_record.py` (new; Task 4 appends to it)

**Interfaces:**
- Consumes: Task 2 names; `_master_fields_or_422`, `_today_ist`, `_student_in_portfolio`, `require_school_entitlement`.
- Produces (in `schools.py`):
  - `async def _user_names(db, ids: Iterable[UUID | None]) -> dict[UUID, str]`
  - `def _career_record_out(r: SchoolCareerRecord, names: dict[UUID, str]) -> dict` — keys: `id, school_student_id,
    record_type, notes, created_at, updated_at, status, scheduled_for, completed_on, next_follow_up_date,` every
    `CAREER_STRUCTURED_KEYS`, `counselor_name, updated_by_name`.
  - `async def _career_records_out(db, rows) -> list[dict]` (batch name lookup + serializer)
  - `def _enter_career_status(record, new: str | None, old: str | None, sent: set[str]) -> str | None` (returns a
    422 message or None; applies C6/C7 defaults)
  - `def _career_rule_error(record) -> str | None` (post-merge C6–C8)

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-026 -- counselling record API (spec §5.1, AC26-1..AC26-9, AC-R1..AC-R4)."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school, mk_staff
from sqlalchemy import select

from app.models import AuditLog, Notification, SchoolCareerRecord

RECORDS = "/api/v1/school/career-counselor/records"
IST = ZoneInfo("Asia/Kolkata")
TODAY = datetime.now(IST).date()
LEGACY_KEYS = {"id", "school_student_id", "record_type", "notes", "created_at"}


@pytest_asyncio.fixture
async def world(db_session):
    ctx = await mk_school(db_session, label="E26", students=2)
    ctx["counselor"] = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    ctx["sid"] = str(ctx["students"][0].id)
    return ctx


async def _create(client, world, **body):
    return await client.post(RECORDS, json={"school_student_id": world["sid"], "record_type": "counselling_note", "notes": "Met.", **body})


@pytest.mark.asyncio
async def test_legacy_three_field_post_behaves_as_before(client, world):
    await login(client, world["counselor"].email)
    r = await _create(client, world)
    assert r.status_code == 201
    body = r.json()
    assert LEGACY_KEYS <= set(body)
    assert body["status"] == "completed" and body["completed_on"] == TODAY.isoformat()  # C3


@pytest.mark.asyncio
async def test_create_with_every_section_7_field(client, world):
    await login(client, world["counselor"].email)
    fields = {
        "status": "scheduled", "scheduled_for": "2026-12-01T10:00:00+05:30", "notes": "",
        "career_interests": ["Design"], "global_education_interest": True, "academic_strengths": ["Maths"],
        "weak_areas": ["Essays"], "recommended_careers": ["Architect"], "recommended_courses": ["B.Arch"],
        "recommended_stream": ["Science"], "recommended_skills": ["Sketching"], "parent_participated": True,
        "parent_participation_note": "Mother attended online",
    }
    r = await _create(client, world, **fields)
    assert r.status_code == 201, r.text
    listed = (await client.get(RECORDS)).json()[0]
    for key, value in fields.items():
        if key == "scheduled_for":
            assert datetime.fromisoformat(listed[key]) == datetime.fromisoformat(value)
        else:
            assert listed[key] == value, key
    assert listed["counselor_name"] == world["counselor"].full_name


@pytest.mark.parametrize("status", ["not_started", "scheduled", "completed"])
@pytest.mark.asyncio
async def test_create_accepts_only_the_initial_statuses(client, world, status):
    await login(client, world["counselor"].email)
    extra = {"scheduled_for": "2026-12-01T10:00:00+05:30"} if status == "scheduled" else {}
    assert (await _create(client, world, status=status, **extra)).status_code == 201


@pytest.mark.asyncio
async def test_create_cannot_start_at_follow_up(client, world):
    await login(client, world["counselor"].email)
    r = await _create(client, world, status="follow_up_required", next_follow_up_date=(TODAY + timedelta(days=3)).isoformat())
    assert r.status_code == 422
    assert r.json()["detail"] == "status must be one of not_started, scheduled, completed when creating a record"


@pytest.mark.asyncio
async def test_scheduled_needs_a_date_and_completed_needs_notes(client, world):
    await login(client, world["counselor"].email)
    r = await _create(client, world, status="scheduled", notes="")
    assert (r.status_code, r.json()["detail"]) == (422, "scheduled_for is required when status is Scheduled")
    r = await _create(client, world, status="completed", notes="  ")
    assert (r.status_code, r.json()["detail"]) == (422, "notes is required")


@pytest.mark.asyncio
async def test_recommendation_stays_notes_only(client, world):
    await login(client, world["counselor"].email)
    ok = await client.post(RECORDS, json={"school_student_id": world["sid"], "record_type": "recommendation", "notes": "Cyber security"})
    assert ok.status_code == 201 and ok.json()["status"] is None
    bad = await client.post(RECORDS, json={"school_student_id": world["sid"], "record_type": "recommendation", "notes": "x", "status": "completed"})
    assert (bad.status_code, bad.json()["detail"]) == (422, "recommendation records take notes only")


@pytest.mark.asyncio
async def test_existing_error_messages_are_unchanged(client, world):
    await login(client, world["counselor"].email)
    assert (await client.post(RECORDS, json={"record_type": "counselling_note", "notes": "x"})).json()["detail"] == "school_student_id is required"
    bad_type = await client.post(RECORDS, json={"school_student_id": world["sid"], "record_type": "nope", "notes": "x"})
    assert bad_type.json()["detail"] == "record_type must be one of guidance_session, counselling_note, recommendation"
    assert (await _create(client, world, notes="")).json()["detail"] == "notes is required"


@pytest.mark.asyncio
async def test_owner_fields_cannot_be_set_on_create(client, world):
    await login(client, world["counselor"].email)
    r = await _create(client, world, career_counselor_user_id=str(world["coordinator"].id))
    assert (r.status_code, r.json()["detail"]) == (422, "career_counselor_user_id is not an accepted field")


@pytest.mark.asyncio
async def test_school_readers_see_the_structured_fields(client, world):
    await login(client, world["counselor"].email)
    await _create(client, world, weak_areas=["Essays"])
    await login(client, world["coordinator"].email)
    row = (await client.get("/api/v1/school/career-records")).json()[0]
    assert row["weak_areas"] == ["Essays"] and row["status"] == "completed" and LEGACY_KEYS <= set(row)


@pytest.mark.asyncio
async def test_counsellor_payloads_never_carry_student_master_data(client, world):
    """AC26-9 / C10: DEC-SCOPE-028 keeps service roles to name + school; the record serializer adds no student fields."""
    await login(client, world["counselor"].email)
    created = (await _create(client, world)).json()
    listed = (await client.get(RECORDS)).json()[0]
    for body in (created, listed):
        assert not {"grade_or_class", "grade_level", "date_of_birth", "section", "roll_number", "student_code"} & set(body)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_026_counselling_record.py -v`
Expected: FAIL — `KeyError: 'status'` in the first test (the old POST returns only the legacy keys) and 201 instead
of 422 for the validation tests.

- [ ] **Step 3: Implement the helpers** (in `schools.py`, directly after `_notify_student_parents`)

```python
# --- ENH-026: one serializer and one rule set for career records (spec §5.1, A3) -------------------------------

async def _user_names(db: AsyncSession, ids) -> dict:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(wanted)))).all())


def _career_record_out(r: SchoolCareerRecord, names: dict) -> dict:
    return {
        "id": r.id, "school_student_id": r.school_student_id, "record_type": r.record_type, "notes": r.notes,
        "created_at": r.created_at, "updated_at": r.updated_at, "status": r.status,
        **{key: getattr(r, key) for key in CAREER_DATE_KEYS}, **{key: getattr(r, key) for key in CAREER_STRUCTURED_KEYS},
        "counselor_name": names.get(r.career_counselor_user_id), "updated_by_name": names.get(r.updated_by_user_id),
    }


async def _career_records_out(db: AsyncSession, rows) -> list[dict]:
    names = await _user_names(db, [i for r in rows for i in (r.career_counselor_user_id, r.updated_by_user_id)])
    return [_career_record_out(r, names) for r in rows]


def _enter_career_status(record: SchoolCareerRecord, new: str | None, old: str | None, sent: set) -> str | None:
    """Apply a status change's own rules (C6/C7). Returns a 422 message, or None."""
    record.status = new
    if new == old:
        return None
    if new == "scheduled" and "scheduled_for" not in sent:
        return "scheduled_for is required when status is Scheduled"
    if new == "completed" and "completed_on" not in sent:
        record.completed_on = _today_ist()
    if new == "follow_up_required" and "next_follow_up_date" not in sent:
        return "next_follow_up_date is required when status is Follow-up Required"
    if old == "follow_up_required":
        record.next_follow_up_date = None
    return None


def _career_rule_error(record: SchoolCareerRecord) -> str | None:
    """Post-merge rules (C6-C8) on the record as it would be saved."""
    if record.status == "scheduled" and record.scheduled_for is None:
        return "scheduled_for is required when status is Scheduled"
    if record.status in COUNTED_CAREER_STATUSES and not record.notes:
        return "notes is required"
    if record.status == "follow_up_required" and record.next_follow_up_date is not None and record.next_follow_up_date < _today_ist():
        return "next_follow_up_date must be today or later"
    if record.status != "follow_up_required" and record.next_follow_up_date is not None:
        return "next_follow_up_date is only set when status is Follow-up Required"
    return None
```

Add the Task 2 names to the `from app.schemas import (...)` block of `schools.py`:
`CAREER_DATE_KEYS, CAREER_RECORD_TYPES, CAREER_STATUS_INITIAL, CAREER_STATUS_LABEL, CAREER_STRUCTURED_KEYS,
COUNTED_CAREER_STATUSES, STRUCTURED_RECORD_TYPES, CareerRecordFields, CareerRecordUpdate, career_transition_allowed,
counts_as_completed`.

- [ ] **Step 4: Replace `create_career_record`** (keep decorator; order of the first checks unchanged)

```python
@router.post("/career-counselor/records", status_code=201)
async def create_career_record(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "career_counselor":
        raise HTTPException(403, "Career Counselor role required")
    student_id = payload.get("school_student_id")
    if not student_id:
        raise HTTPException(422, "school_student_id is required")
    student = await _student_in_portfolio(db, user, UUID(str(student_id)))
    await require_school_entitlement(db, user, student.school_id, "individual_counselling")  # D5: every record type
    record_type = payload.get("record_type")
    if record_type not in CAREER_RECORD_TYPES:
        raise HTTPException(422, "record_type must be one of guidance_session, counselling_note, recommendation")
    fields = _master_fields_or_422(CareerRecordFields, {k: v for k, v in payload.items() if k not in ("school_student_id", "record_type")})
    sent = fields.model_fields_set - {"notes"}
    if record_type not in STRUCTURED_RECORD_TYPES:
        if sent:
            raise HTTPException(422, "recommendation records take notes only")
        if not fields.notes:
            raise HTTPException(422, "notes is required")
        status = None
    else:
        status = fields.status if fields.status is not None else "completed"  # C3
        if status not in CAREER_STATUS_INITIAL:
            raise HTTPException(422, "status must be one of not_started, scheduled, completed when creating a record")
    record = SchoolCareerRecord(school_student_id=student.id, career_counselor_user_id=user.id, record_type=record_type, notes=fields.notes)
    for key in (*CAREER_DATE_KEYS, *CAREER_STRUCTURED_KEYS):
        if key in sent:
            setattr(record, key, getattr(fields, key))
    if status is not None:
        error = _enter_career_status(record, status, None, sent) or _career_rule_error(record)
        if error:
            raise HTTPException(422, error)
    db.add(record)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.career_record_create", entity_type="school_career_record", entity_id=str(record.id), metadata_json={"record_type": record_type, "status": status, "fields": sorted(sent)}))
    # SCH-007 "Counselling" trigger (guidance session / counselling note / recommendation).
    label = {"guidance_session": "Career guidance session recorded", "counselling_note": "Counselling note added", "recommendation": "Career recommendation added"}[record_type]
    await _notify_student_parents(db, student, title=f"{label} for {student.full_name}", body=f"A Career Counselor has added a new {record_type.replace('_', ' ')} to {student.full_name}'s career profile.", action_url=f"/school/parent/children/{student.id}")
    await db.commit()
    await db.refresh(record)
    logger.info("career_record_create", extra={"extra_fields": {"actor_id": str(user.id), "record_id": str(record.id), "record_type": record_type, "status": status}})
    return (await _career_records_out(db, [record]))[0]
```

Note on `_enter_career_status(record, status, None, sent)`: with `old=None` and `new="completed"` it sets
`completed_on` when not sent; with `new="scheduled"` it requires `scheduled_for`.

Replace the two list endpoints' return lines:

```python
    return await _career_records_out(db, rows)
```

(`list_career_counselor_records`, `list_readable_career_records`; both previously returned hand-built dicts.)

- [ ] **Step 5: Run to verify pass, and the existing SCH-004/007/008/011 suites unmodified**

Run: `cd apps/api && pytest tests/test_enh_026_counselling_record.py tests/test_sch_004_career_guidance.py tests/test_sch_007_parent_portal.py tests/test_sch_008_student_timeline.py tests/test_sch_011_entitlements.py tests/test_enh_022_tier_enforcement.py -v`
Expected: all passed.

- [ ] **Step 6: REFACTOR** — the three list endpoints and the POST now share `_career_records_out`; remove any
leftover hand-built record dicts in `schools.py` (`grep -n '"record_type": r.record_type' apps/api/app/api/schools.py`
should only match `portfolio.py`'s own line after Task 5); rerun Step 5.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_enh_026_counselling_record.py
git commit -m "feat(enh-026): structured fields and initial status on career-record create"
```

---

### Task 4: `PATCH /career-counselor/records/{record_id}`

**Files:**
- Modify: `apps/api/app/api/schools.py` (new route after `create_career_record`)
- Test: append to `apps/api/tests/test_enh_026_counselling_record.py`

**Interfaces:**
- Consumes: Task 2/3 names; `_portfolio_school_ids`, `_notify_student_parents`.
- Produces: route `PATCH /api/v1/school/career-counselor/records/{record_id}` → 200 `_career_record_out`.

- [ ] **Step 1: Write the failing tests** (append)

```python
import asyncio
from contextlib import asynccontextmanager

import httpx
from httpx import ASGITransport

from app.api import schools as schools_api
from app.core.database import SessionLocal
from app.main import app


def _patch_url(rid):
    return f"{RECORDS}/{rid}"


async def _new(client, world, **body):
    r = await _create(client, world, **body)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_full_lifecycle_with_follow_up_loop(client, world):
    await login(client, world["counselor"].email)
    rec = await _new(client, world, status="not_started", notes="")
    url = _patch_url(rec["id"])
    r = await client.patch(url, json={"status": "scheduled", "scheduled_for": "2026-12-01T10:00:00+05:30", "expected_status": "not_started"})
    assert r.status_code == 200 and r.json()["status"] == "scheduled"
    r = await client.patch(url, json={"status": "completed", "notes": "Discussed design."})
    assert r.json()["status"] == "completed" and r.json()["completed_on"] == TODAY.isoformat()
    follow = (TODAY + timedelta(days=7)).isoformat()
    r = await client.patch(url, json={"status": "follow_up_required", "next_follow_up_date": follow})
    assert r.json()["next_follow_up_date"] == follow
    r = await client.patch(url, json={"status": "scheduled", "scheduled_for": "2027-01-05T09:00:00+05:30"})
    assert r.status_code == 200 and r.json()["next_follow_up_date"] is None  # C7: cleared on leaving
    assert r.json()["updated_by_name"] == world["counselor"].full_name


@pytest.mark.parametrize("start,target", [("not_started", "completed"), ("scheduled", "not_started"), ("completed", "scheduled")])
@pytest.mark.asyncio
async def test_skips_and_backward_moves_are_422(client, world, start, target):
    await login(client, world["counselor"].email)
    extra = {"scheduled_for": "2026-12-01T10:00:00+05:30"} if start == "scheduled" else {}
    rec = await _new(client, world, status=start, **extra)
    r = await client.patch(_patch_url(rec["id"]), json={"status": target, "scheduled_for": "2026-12-02T10:00:00+05:30", "notes": "n"})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("Cannot change status from ")


@pytest.mark.asyncio
async def test_rescheduling_requires_a_new_scheduled_for(client, world):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)  # completed
    await client.patch(_patch_url(rec["id"]), json={"status": "follow_up_required", "next_follow_up_date": (TODAY + timedelta(days=1)).isoformat()})
    r = await client.patch(_patch_url(rec["id"]), json={"status": "scheduled"})
    assert (r.status_code, r.json()["detail"]) == (422, "scheduled_for is required when status is Scheduled")


@pytest.mark.asyncio
async def test_follow_up_date_must_not_be_in_the_past(client, world):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    r = await client.patch(_patch_url(rec["id"]), json={"status": "follow_up_required", "next_follow_up_date": (TODAY - timedelta(days=1)).isoformat()})
    assert (r.status_code, r.json()["detail"]) == (422, "next_follow_up_date must be today or later")


@pytest.mark.asyncio
async def test_legacy_row_moves_only_to_completed_or_follow_up(client, world, db_session):
    legacy = SchoolCareerRecord(school_student_id=world["students"][0].id, career_counselor_user_id=world["counselor"].id, record_type="counselling_note", notes="old note")
    db_session.add(legacy)
    await db_session.commit()
    await login(client, world["counselor"].email)
    assert (await client.patch(_patch_url(legacy.id), json={"status": "not_started"})).status_code == 422
    assert (await client.patch(_patch_url(legacy.id), json={"status": "scheduled", "scheduled_for": "2026-12-01T10:00:00+05:30"})).status_code == 422
    r = await client.patch(_patch_url(legacy.id), json={"status": "completed", "expected_status": None})
    assert r.status_code == 200 and r.json()["status"] == "completed" and r.json()["notes"] == "old note"


@pytest.mark.asyncio
async def test_legacy_field_edit_keeps_status_null(client, world, db_session):
    legacy = SchoolCareerRecord(school_student_id=world["students"][0].id, career_counselor_user_id=world["counselor"].id, record_type="guidance_session", notes="old")
    db_session.add(legacy)
    await db_session.commit()
    await login(client, world["counselor"].email)
    r = await client.patch(_patch_url(legacy.id), json={"weak_areas": ["Essays"]})
    assert r.status_code == 200 and r.json()["status"] is None and r.json()["weak_areas"] == ["Essays"]


@pytest.mark.asyncio
async def test_stale_expected_status_is_409_and_writes_nothing(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)  # completed
    before = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == rec["id"]))
    r = await client.patch(_patch_url(rec["id"]), json={"expected_status": "scheduled", "notes": "changed"})
    assert r.status_code == 409
    assert r.json()["detail"] == "This record was changed by someone else (now Completed). Reload to see the latest."
    after = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == rec["id"]))
    assert after == before


@pytest.mark.asyncio
async def test_patch_resending_current_values_is_a_noop(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world, weak_areas=["Essays"])
    audits = select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.career_record_update", AuditLog.entity_id == rec["id"])
    r = await client.patch(_patch_url(rec["id"]), json={"status": "completed", "notes": "Met.", "weak_areas": ["Essays"], "expected_status": "completed"})
    assert r.status_code == 200
    assert await db_session.scalar(audits) == 0


@pytest.mark.asyncio
async def test_update_is_audited_with_names_and_status_only(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    await client.patch(_patch_url(rec["id"]), json={"status": "follow_up_required", "next_follow_up_date": (TODAY + timedelta(days=2)).isoformat(), "weak_areas": ["Secret detail"]})
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.career_record_update", AuditLog.entity_id == rec["id"]))
    assert row.metadata_json["status"] == {"old": "completed", "new": "follow_up_required"}
    assert "weak_areas" in row.metadata_json["changed_fields"]
    assert "Secret detail" not in str(row.metadata_json)


@pytest.mark.asyncio
async def test_parents_are_notified_only_on_status_change(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    parent_rows = select(func.count()).select_from(Notification).where(Notification.user_id == world["parent"].id)
    after_create = await db_session.scalar(parent_rows)
    await client.patch(_patch_url(rec["id"]), json={"weak_areas": ["Essays"]})
    assert await db_session.scalar(parent_rows) == after_create
    await client.patch(_patch_url(rec["id"]), json={"status": "follow_up_required", "next_follow_up_date": (TODAY + timedelta(days=2)).isoformat()})
    assert await db_session.scalar(parent_rows) == after_create + 1


@pytest.mark.asyncio
async def test_notification_failure_keeps_the_status_change(client, world, db_session, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("smtp down")
    await login(client, world["counselor"].email)
    rec = await _new(client, world)  # created while the mailer is healthy
    monkeypatch.setattr(schools_api, "send_parent_notification_email", boom)
    r = await client.patch(_patch_url(rec["id"]), json={"status": "follow_up_required", "next_follow_up_date": (TODAY + timedelta(days=2)).isoformat()})
    assert r.status_code == 200
    saved = await db_session.get(SchoolCareerRecord, rec["id"], populate_existing=True)
    assert saved.status == "follow_up_required"


@pytest.mark.asyncio
async def test_authorization(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    other = await mk_school(db_session, label="E26-Other", students=0)
    outsider = await mk_staff(db_session, other["school"], other["admin"], role="career_counselor")
    await login(client, outsider.email)
    assert (await client.patch(_patch_url(rec["id"]), json={"notes": "x"})).status_code == 403
    await login(client, world["coordinator"].email)
    assert (await client.patch(_patch_url(rec["id"]), json={"notes": "x"})).status_code == 403
    await login(client, world["counselor"].email)
    assert (await client.patch(_patch_url("00000000-0000-0000-0000-000000000000"), json={"notes": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_a_second_portfolio_counsellor_may_edit(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    second = await mk_staff(db_session, world["school"], world["admin"], role="career_counselor")
    await login(client, second.email)
    r = await client.patch(_patch_url(rec["id"]), json={"weak_areas": ["Essays"]})
    assert r.status_code == 200
    assert r.json()["counselor_name"] == world["counselor"].full_name and r.json()["updated_by_name"] == second.full_name


@pytest.mark.asyncio
async def test_below_silver_is_a_tier_denial(client, db_session):
    ctx = await mk_school(db_session, label="E26-Bronze", tier="bronze")
    counselor = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    rec = SchoolCareerRecord(school_student_id=ctx["students"][0].id, career_counselor_user_id=counselor.id, record_type="counselling_note", notes="n", status="not_started")
    db_session.add(rec)
    await db_session.commit()
    await login(client, counselor.email)
    r = await client.patch(_patch_url(rec.id), json={"status": "scheduled", "scheduled_for": "2026-12-01T10:00:00+05:30"})
    assert r.status_code == 403


@asynccontextmanager
async def _client_for(email):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await login(c, email)
        yield c


@asynccontextmanager
async def _held(pk):
    session = SessionLocal()
    try:
        await session.execute(select(SchoolCareerRecord).where(SchoolCareerRecord.id == pk).with_for_update())
        yield
    finally:
        await session.rollback()
        await session.close()


@pytest.mark.asyncio
async def test_concurrent_transitions_serialize_on_the_row_lock(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world, status="scheduled", scheduled_for="2026-12-01T10:00:00+05:30")
    second = await mk_staff(db_session, world["school"], world["admin"], role="career_counselor")
    async with _client_for(world["counselor"].email) as a, _client_for(second.email) as b:
        async with _held(rec["id"]):
            first = asyncio.create_task(a.patch(_patch_url(rec["id"]), json={"status": "completed", "notes": "A", "expected_status": "scheduled"}))
            other = asyncio.create_task(b.patch(_patch_url(rec["id"]), json={"status": "completed", "notes": "B", "expected_status": "scheduled"}))
            await asyncio.sleep(0.3)
        results = sorted([(await first).status_code, (await other).status_code])
    assert results == [200, 409]


@pytest.mark.asyncio
async def test_record_type_and_owner_cannot_be_patched(client, world):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    for key in ("record_type", "school_student_id", "career_counselor_user_id"):
        r = await client.patch(_patch_url(rec["id"]), json={key: "x"})
        assert (r.status_code, r.json()["detail"]) == (422, f"{key} is not an accepted field")


@pytest.mark.asyncio
async def test_recommendation_patch_accepts_notes_only(client, world):
    await login(client, world["counselor"].email)
    rec = (await client.post(RECORDS, json={"school_student_id": world["sid"], "record_type": "recommendation", "notes": "A"})).json()
    assert (await client.patch(_patch_url(rec["id"]), json={"notes": "B"})).json()["notes"] == "B"
    r = await client.patch(_patch_url(rec["id"]), json={"status": "completed"})
    assert (r.status_code, r.json()["detail"]) == (422, "recommendation records take notes only")
```

Add `from sqlalchemy import func, select` (replace the file's `from sqlalchemy import select`).

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_026_counselling_record.py -v`
Expected: Task 3's tests still pass; every new test FAILS with `405 Method Not Allowed` on the PATCH.

- [ ] **Step 3: Implement the route** (after `create_career_record`)

```python
OUTSIDE_COUNSELOR_PORTFOLIO = "This student is at a school outside your own portfolio"  # _student_in_portfolio's own wording


@router.patch("/career-counselor/records/{record_id}")
async def update_career_record(record_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ENH-026 spec §5.1. One transaction up to the record commit: lock the record, lock its student (the lock transfer
    approval takes) and re-check the portfolio under it, tier gate, precondition, transition, merge, rules, audit.
    Parents are notified after the commit (step 10) so no lock is held across email delivery."""
    if user.role != "career_counselor":
        raise HTTPException(403, "Career Counselor role required")
    record = await db.scalar(select(SchoolCareerRecord).where(SchoolCareerRecord.id == record_id).with_for_update().execution_options(populate_existing=True))
    if record is None:
        raise HTTPException(404, "Career record not found")
    student = await db.scalar(select(SchoolStudent).where(SchoolStudent.id == record.school_student_id).with_for_update().execution_options(populate_existing=True))
    if student is None or student.school_id not in await _portfolio_school_ids(db, user):
        raise HTTPException(403, OUTSIDE_COUNSELOR_PORTFOLIO)
    await require_school_entitlement(db, user, student.school_id, "individual_counselling", grandfathered_since=record.created_at)
    fields = _master_fields_or_422(CareerRecordUpdate, payload)
    sent = set(fields.model_fields_set)
    if "expected_status" in sent and fields.expected_status != record.status:
        raise HTTPException(409, f"This record was changed by someone else (now {CAREER_STATUS_LABEL[record.status]}). Reload to see the latest.")
    sent.discard("expected_status")
    if record.record_type not in STRUCTURED_RECORD_TYPES and sent - {"notes"}:
        raise HTTPException(422, "recommendation records take notes only")

    tracked = ("notes", "status", *CAREER_DATE_KEYS, *CAREER_STRUCTURED_KEYS)
    before = {key: getattr(record, key) for key in tracked}
    old_status = record.status
    if "status" in sent and fields.status != old_status:
        if fields.status is None or not career_transition_allowed(old_status, fields.status):
            raise HTTPException(422, f"Cannot change status from {CAREER_STATUS_LABEL[old_status]} to {CAREER_STATUS_LABEL[fields.status]}")
    for key in sent - {"status"}:
        setattr(record, key, getattr(fields, key))
    if "status" in sent:
        error = _enter_career_status(record, fields.status, old_status, sent)
        if error:
            raise HTTPException(422, error)
    error = _career_rule_error(record)
    if error:
        raise HTTPException(422, error)

    changed = [key for key in tracked if getattr(record, key) != before[key]]
    if not changed:
        return (await _career_records_out(db, [record]))[0]  # A6: a repeat PATCH writes nothing
    record.updated_by_user_id = user.id
    metadata = {"changed_fields": changed}
    for key in ("status", *CAREER_DATE_KEYS):
        if key in changed:
            old, new = before[key], getattr(record, key)
            metadata[key] = {"old": old.isoformat() if hasattr(old, "isoformat") else old, "new": new.isoformat() if hasattr(new, "isoformat") else new}
    db.add(AuditLog(user_id=user.id, action="school.career_record_update", entity_type="school_career_record", entity_id=str(record.id), metadata_json=metadata))
    await db.commit()
    await db.refresh(record)
    if record.status != old_status:
        try:
            await _notify_student_parents(
                db, student, title=f"{CAREER_STATUS_LABEL[record.status]} — career record for {student.full_name}",
                body=f"A Career Counselor updated {student.full_name}'s career record to {CAREER_STATUS_LABEL[record.status]}.",
                action_url=f"/school/parent/children/{student.id}",
            )
            await db.commit()
        except Exception:
            await db.rollback()
            logger.warning("career_record_notify_failed", extra={"extra_fields": {"record_id": str(record.id), "student_id": str(student.id)}})
    logger.info("career_record_update", extra={"extra_fields": {"actor_id": str(user.id), "record_id": str(record.id), "status": record.status, "changed": len(changed)}})
    return (await _career_records_out(db, [record]))[0]
```

`send_parent_notification_email` must be referenced through the `schools` module at call time for the monkeypatch to
work — `_notify_parent` already calls it by its module-level name, so patching `schools_api.send_parent_notification_email`
suffices. Confirm with `grep -n "send_parent_notification_email" apps/api/app/api/schools.py`.

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/api && pytest tests/test_enh_026_counselling_record.py -v`
Expected: all passed.

- [ ] **Step 5: REFACTOR** — tidy the notification-failure test as noted; extract the `isoformat` lambda into a local
`_iso(value)` helper in `schools.py` if it reads better; rerun Step 4 plus
`pytest tests/test_enh_013_career_goal.py tests/test_enh_005_concurrency.py -v`.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_enh_026_counselling_record.py
git commit -m "feat(enh-026): PATCH career records with status lifecycle, precondition and post-commit notification"
```

---

### Task 5: ENH-026 aggregates (dashboard, entitlements, overview, portfolio)

**Files:**
- Modify: `apps/api/app/api/schools.py` (`_school_dashboard_payload` 403-405; `school_entitlements` 1044-1046;
  `_overview_payload` 1191-1207); `apps/api/app/api/portfolio.py:129`
- Test: `apps/api/tests/test_enh_026_aggregates.py`

**Interfaces:**
- Consumes: `counts_as_completed`, `COUNTED_CAREER_STATUSES`, `_career_records_out`.
- Produces: overview keys `career_guidance.status`/`counselling.status` ∈ {`completed`, `in_progress`,
  `not_started`}; `structured_recommendations: list[{record_id, record_type, created_at, recommended_careers,
  recommended_courses, recommended_stream, recommended_skills}]`; portfolio `career_guidance[*].status`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-026 -- counted-as-completed rule in every aggregate (spec §5.3, C5, C14, AC26-6)."""
import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school, mk_staff

from app.models import SchoolCareerRecord


@pytest_asyncio.fixture
async def world(db_session):
    ctx = await mk_school(db_session, label="E26-Agg", students=5)
    counselor = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    s = ctx["students"]
    rows = [
        (s[0], "counselling_note", None), (s[1], "counselling_note", "completed"), (s[2], "counselling_note", "follow_up_required"),
        (s[3], "counselling_note", "not_started"), (s[4], "counselling_note", "scheduled"),
        (s[0], "guidance_session", "scheduled"),
    ]
    for student, record_type, status in rows:
        db_session.add(SchoolCareerRecord(school_student_id=student.id, career_counselor_user_id=counselor.id, record_type=record_type, notes="n", status=status, recommended_careers=["Law"] if status == "completed" else None))
    await db_session.commit()
    ctx["counselor"] = counselor
    return ctx


@pytest.mark.asyncio
async def test_kpis_count_only_completed_follow_up_and_legacy(client, world):
    await login(client, world["coordinator"].email)
    data = (await client.get("/api/v1/school/dashboard")).json()
    kpis = {k["key"]: k for k in data["school_crm_kpis"]}
    assert kpis["individual_counselling_completed"]["value"] == 3  # s0 legacy, s1, s2
    assert kpis["career_guidance_completed"]["value"] == 0  # s0's guidance session is only scheduled
    assert data["career_guidance"]["students_covered"] == 5  # any record, unchanged


@pytest.mark.asyncio
async def test_entitlement_usage_counts_delivered_counselling_notes(client, world):
    await login(client, world["coordinator"].email)
    services = {s["key"]: s for s in (await client.get("/api/v1/school/entitlements")).json()["services"]}
    assert services["individual_counselling"]["used"] == 3


@pytest.mark.asyncio
async def test_overview_status_values(client, world):
    await login(client, world["coordinator"].email)
    s = world["students"]
    assert (await client.get(f"/api/v1/school/students/{s[0].id}/overview")).json()["career_guidance"]["status"] == "in_progress"
    assert (await client.get(f"/api/v1/school/students/{s[0].id}/overview")).json()["counselling"]["status"] == "completed"
    assert (await client.get(f"/api/v1/school/students/{s[3].id}/overview")).json()["counselling"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_overview_keeps_old_keys_and_adds_structured_recommendations(client, world):
    await login(client, world["coordinator"].email)
    body = (await client.get(f"/api/v1/school/students/{world['students'][1].id}/overview")).json()
    note = body["counselling"]["notes"][0]
    assert {"id", "record_type", "notes", "created_at"} <= set(note) and note["status"] == "completed"
    assert body["recommended_careers"] == []  # unchanged meaning: recommendation-type notes
    assert body["structured_recommendations"][0]["recommended_careers"] == ["Law"]


@pytest.mark.asyncio
async def test_portfolio_career_guidance_carries_status(client, world):
    await login(client, world["coordinator"].email)
    body = (await client.get(f"/api/v1/school/students/{world['students'][1].id}/portfolio")).json()
    assert body["career_guidance"][0]["status"] == "completed"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_026_aggregates.py -v`
Expected: FAIL — KPI value 5 instead of 3; `in_progress` missing; `structured_recommendations` KeyError.

- [ ] **Step 3: Implement**

`_school_dashboard_payload` (lines 404-405):

```python
    guidance_students = {r.school_student_id for r in career_rows if r.record_type == "guidance_session" and counts_as_completed(r.status)}
    counselling_students = {r.school_student_id for r in career_rows if r.record_type == "counselling_note" and counts_as_completed(r.status)}
```

`school_entitlements` (lines 1044-1046):

```python
        usage["individual_counselling"] = len(
            (await db.scalars(select(SchoolCareerRecord.id).where(
                SchoolCareerRecord.school_student_id.in_(student_ids), SchoolCareerRecord.record_type == "counselling_note",
                or_(SchoolCareerRecord.status.is_(None), SchoolCareerRecord.status.in_(COUNTED_CAREER_STATUSES)),
            ))).all()
        )
```

(add `or_` to the `from sqlalchemy import ...` line if missing.)

`_overview_payload` (replace lines 1191-1207's career parts):

```python
    career_out = {row["id"]: row for row in await _career_records_out(db, career_rows)}

    def _career(rows: list) -> list[dict]:
        return [career_out[r.id] for r in rows]

    def _module_status(rows: list) -> str:  # C14
        if any(counts_as_completed(r.status) for r in rows):
            return "completed"
        return "in_progress" if rows else "not_started"

    guidance = [r for r in career_rows if r.record_type == "guidance_session"]
    counselling = [r for r in career_rows if r.record_type == "counselling_note"]
    recommendations = [r for r in career_rows if r.record_type == "recommendation"]
    structured_recommendations = [
        {"record_id": r.id, "record_type": r.record_type, "created_at": r.created_at,
         **{key: getattr(r, key) for key in ("recommended_careers", "recommended_courses", "recommended_stream", "recommended_skills")}}
        for r in guidance + counselling
        if any(getattr(r, key) for key in ("recommended_careers", "recommended_courses", "recommended_stream", "recommended_skills"))
    ]
```

and in the returned dict:

```python
        "career_guidance": {"status": _module_status(guidance), "sessions": _career(guidance)},
        "counselling": {"status": _module_status(counselling), "notes": _career(counselling)},
        "recommended_careers": _career(recommendations),
        "structured_recommendations": structured_recommendations,
```

`portfolio.py:129`:

```python
        "career_guidance": [{"id": r.id, "record_type": r.record_type, "notes": r.notes, "created_at": r.created_at, "status": r.status} for r in career],
```

- [ ] **Step 4: Run to verify pass, plus the suites that read these payloads (unmodified)**

Run: `cd apps/api && pytest tests/test_enh_026_aggregates.py tests/test_sch_reports.py tests/test_sch_007_parent_portal.py tests/test_sch_011_entitlements.py tests/test_enh_013_360_view.py tests/test_enh_012_digital_portfolio.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/app/api/portfolio.py apps/api/tests/test_enh_026_aggregates.py
git commit -m "feat(enh-026): counted-as-completed rule in KPIs, usage and overview; structured recommendations"
```

---

### Task 6: Counsellor screen — form, edit flow, loading state

**Files:**
- Create: `apps/web/lib/careerRecords.ts`, `apps/web/components/CareerRecordForm.tsx`,
  `apps/web/app/school/career-counselor/dashboard/loading.tsx`, `apps/web/tests/components/CareerRecordForm.test.tsx`,
  `apps/web/tests/components/careerRecords.test.ts`
- Modify: `apps/web/lib/apiErrors.ts` (`SendOutcome`, `sendJson`), `apps/web/components/SchoolCareerRecordsPanel.tsx`,
  `apps/web/app/school/career-counselor/dashboard/page.tsx` (type import only),
  `apps/web/tests/components/SchoolCareerRecordsPanel.test.tsx` (append tests only; existing ones unmodified)

**Interfaces:**
- Consumes: API from Tasks 3–4; `splitList`, `listText` from `lib/schoolStudents.ts`; `FormMessage`, `refocus`.
- Produces:
  - `lib/careerRecords.ts`: `type CareerStatus`, `type CareerRecord`, `CAREER_STATUS_LABEL`, `NO_STATUS_LABEL`,
    `STRUCTURED_TYPES`, `CAREER_LIST_FIELDS: {key, label}[]`, `statusOptions(current, creating): CareerStatus[]`,
    `statusLabel(status): string`
  - `SendOutcome` failure: `{ ok: false; message: string; status?: number }`
  - `CareerRecordForm({ students, record, onDone, onCancel })`

- [ ] **Step 1: Write the failing tests**

`apps/web/tests/components/careerRecords.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { NO_STATUS_LABEL, statusLabel, statusOptions } from "@/lib/careerRecords";

describe("statusOptions", () => {
  it("offers the three initial statuses on create", () => {
    expect(statusOptions(undefined, true)).toEqual(["not_started", "scheduled", "completed"]);
  });
  it("offers the current status plus its allowed next states", () => {
    expect(statusOptions("completed", false)).toEqual(["completed", "follow_up_required"]);
    expect(statusOptions("follow_up_required", false)).toEqual(["follow_up_required", "scheduled", "completed"]);
  });
  it("offers only completed/follow-up for a legacy record", () => {
    expect(statusOptions(null, false)).toEqual(["completed", "follow_up_required"]);
  });
  it("labels a legacy record", () => {
    expect(statusLabel(null)).toBe(NO_STATUS_LABEL);
    expect(statusLabel("follow_up_required")).toBe("Follow-up Required");
  });
});
```

`apps/web/tests/components/CareerRecordForm.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CareerRecordForm from "@/components/CareerRecordForm";
import type { CareerRecord } from "@/lib/careerRecords";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const STUDENTS = [{ id: "s1", full_name: "Asha", school_name: "Hill School" }];
const RECORD: CareerRecord = {
  id: "r1", school_student_id: "s1", record_type: "counselling_note", notes: "Met.", created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z",
  status: "completed", scheduled_for: null, completed_on: "2026-09-01", next_follow_up_date: null,
  career_interests: null, academic_strengths: null, weak_areas: ["Essays"], recommended_careers: null, recommended_courses: null,
  recommended_stream: null, recommended_skills: null, global_education_interest: null, parent_participated: null, parent_participation_note: null,
  counselor_name: "C", updated_by_name: null,
};

describe("CareerRecordForm", () => {
  it("shows the date input that belongs to the chosen status", () => {
    render(<CareerRecordForm students={STUDENTS} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "counselling_note" } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "scheduled" } });
    expect(screen.getByLabelText("Scheduled for")).toBeInTheDocument();
    expect(screen.queryByLabelText("Next follow-up")).not.toBeInTheDocument();
  });

  it("hides status and structured fields for a recommendation", () => {
    render(<CareerRecordForm students={STUDENTS} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "recommendation" } });
    expect(screen.queryByLabelText("Status")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Weak areas")).not.toBeInTheDocument();
  });

  it("edits with PATCH and sends expected_status", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ...RECORD }) });
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();
    render(<CareerRecordForm students={STUDENTS} record={RECORD} onDone={onDone} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await vi.waitFor(() => expect(onDone).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/career-counselor/records/r1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toMatchObject({ expected_status: "completed", weak_areas: ["Essays"] });
  });

  it("offers a reload when the record changed elsewhere (409)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => ({ detail: "This record was changed by someone else (now Follow-up Required). Reload to see the latest." }) }));
    render(<CareerRecordForm students={STUDENTS} record={RECORD} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed by someone else");
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it("cancels with Escape", () => {
    const onCancel = vi.fn();
    render(<CareerRecordForm students={STUDENTS} record={RECORD} onDone={vi.fn()} onCancel={onCancel} />);
    fireEvent.keyDown(screen.getByLabelText("Status"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });
});
```

Append to `SchoolCareerRecordsPanel.test.tsx` (existing three tests untouched):

```tsx
describe("SchoolCareerRecordsPanel records table (ENH-026)", () => {
  const record = { id: "r1", school_student_id: "s1", record_type: "counselling_note", notes: "Met.", created_at: "2026-09-01T00:00:00Z", status: null, next_follow_up_date: null };

  it("labels a record made before tracking", () => {
    render(<SchoolCareerRecordsPanel records={[record]} students={STUDENTS} />);
    expect(screen.getByText("No status (recorded before tracking)")).toBeInTheDocument();
  });

  it("opens the edit form and returns focus to the Edit button on cancel", async () => {
    render(<SchoolCareerRecordsPanel records={[record]} students={STUDENTS} />);
    const edit = screen.getByRole("button", { name: "Edit record for Asha" });
    fireEvent.click(edit);
    expect(screen.getByRole("heading", { name: "Edit record for Asha" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await vi.waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Edit record for Asha" })));
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && npx vitest run tests/components/careerRecords.test.ts tests/components/CareerRecordForm.test.tsx tests/components/SchoolCareerRecordsPanel.test.tsx`
Expected: FAIL — module `@/lib/careerRecords` not found; panel has no Edit button.

- [ ] **Step 3: Implement `lib/careerRecords.ts`**

```ts
// ENH-026 (DEC-SCOPE-031): one source for the counselling-record lifecycle and labels, used by the form and every read view.
export type CareerStatus = "not_started" | "scheduled" | "completed" | "follow_up_required";

export type CareerRecord = {
  id: string; school_student_id: string; record_type: string; notes: string; created_at: string; updated_at?: string;
  status?: CareerStatus | null; scheduled_for?: string | null; completed_on?: string | null; next_follow_up_date?: string | null;
  career_interests?: string[] | null; academic_strengths?: string[] | null; weak_areas?: string[] | null;
  recommended_careers?: string[] | null; recommended_courses?: string[] | null; recommended_stream?: string[] | null; recommended_skills?: string[] | null;
  global_education_interest?: boolean | null; parent_participated?: boolean | null; parent_participation_note?: string | null;
  counselor_name?: string | null; updated_by_name?: string | null;
};

export const CAREER_STATUS_LABEL: Record<CareerStatus, string> = {
  not_started: "Not Started", scheduled: "Scheduled", completed: "Completed", follow_up_required: "Follow-up Required",
};
export const NO_STATUS_LABEL = "No status (recorded before tracking)";
export const STRUCTURED_TYPES = ["guidance_session", "counselling_note"];
export const RECORD_TYPE_LABEL: Record<string, string> = { guidance_session: "Guidance session", counselling_note: "Counselling note", recommendation: "Recommendation" };

export const CAREER_LIST_FIELDS = [
  { key: "career_interests", label: "Career interests", group: "assessment" },
  { key: "academic_strengths", label: "Academic strengths", group: "assessment" },
  { key: "weak_areas", label: "Weak areas", group: "assessment" },
  { key: "recommended_careers", label: "Recommended careers", group: "recommendations" },
  { key: "recommended_courses", label: "Recommended courses", group: "recommendations" },
  { key: "recommended_stream", label: "Recommended subjects/stream", group: "recommendations" },
  { key: "recommended_skills", label: "Recommended skills", group: "recommendations" },
] as const;

const INITIAL: CareerStatus[] = ["not_started", "scheduled", "completed"];
const NEXT: Record<CareerStatus, CareerStatus[]> = {
  not_started: ["scheduled"], scheduled: ["completed"], completed: ["follow_up_required"], follow_up_required: ["scheduled", "completed"],
};

export function statusOptions(current: CareerStatus | null | undefined, creating: boolean): CareerStatus[] {
  if (creating) return INITIAL;
  if (!current) return ["completed", "follow_up_required"];
  return [current, ...NEXT[current]];
}

export function statusLabel(status: CareerStatus | null | undefined): string {
  return status ? CAREER_STATUS_LABEL[status] : NO_STATUS_LABEL;
}
```

- [ ] **Step 4: Extend `sendJson`** (`apps/web/lib/apiErrors.ts`) — additive:

```ts
export type SendOutcome = { ok: true; data: Record<string, unknown> } | { ok: false; message: string; status?: number };
// ...inside sendJson, replace the error return:
  if (!response.ok) return { ok: false, message: detailMessage(data?.detail), status: response.status };
```

- [ ] **Step 5: Implement `CareerRecordForm.tsx`**

```tsx
"use client";

import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { sendJson } from "@/lib/apiErrors";
import { CAREER_LIST_FIELDS, type CareerRecord, type CareerStatus, RECORD_TYPE_LABEL, STRUCTURED_TYPES, statusLabel, statusOptions } from "@/lib/careerRecords";
import { listText, splitList } from "@/lib/schoolStudents";

type Student = { id: string; full_name: string; school_name: string };

// ENH-026: create and edit one counselling record. Groups follow spec §11.2 F1; the status select only ever offers states the
// API will accept (F3), so a refused transition means someone else changed the record -- shown with a Reload action (F7).
export default function CareerRecordForm({ students, record, onDone, onCancel }: { students: Student[]; record?: CareerRecord; onDone: () => void; onCancel: () => void }) {
  const router = useRouter();
  const editing = Boolean(record);
  const [recordType, setRecordType] = useState(record?.record_type ?? "");
  const [status, setStatus] = useState<CareerStatus | "">(record?.status ?? (editing ? "" : "completed"));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const [stale, setStale] = useState(false);
  const inFlight = useRef(false);
  const structured = STRUCTURED_TYPES.includes(recordType);
  const prefix = record ? `career-${record.id}` : "career-new";

  function onKey(event: KeyboardEvent) {
    if (event.key === "Escape") onCancel();
  }

  function payload(form: FormData): Record<string, unknown> {
    const body: Record<string, unknown> = { notes: String(form.get("notes") ?? "") };
    if (!editing) Object.assign(body, { school_student_id: form.get("school_student_id"), record_type: recordType });
    if (!structured) return body;
    if (status) body.status = status;
    const scheduled = String(form.get("scheduled_for") ?? "");
    if (scheduled) body.scheduled_for = new Date(scheduled).toISOString();
    const followUp = String(form.get("next_follow_up_date") ?? "");
    if (followUp) body.next_follow_up_date = followUp;
    const completedOn = String(form.get("completed_on") ?? "");
    if (completedOn) body.completed_on = completedOn;
    for (const field of CAREER_LIST_FIELDS) {
      const items = splitList(form.get(field.key));
      if (items.length || editing) body[field.key] = items.length ? items : null;
    }
    for (const key of ["global_education_interest", "parent_participated"]) {
      const value = String(form.get(key) ?? "");
      if (value || editing) body[key] = value === "" ? null : value === "yes";
    }
    const note = String(form.get("parent_participation_note") ?? "").trim();
    if (note || editing) body.parent_participation_note = note || null;
    if (editing) body.expected_status = record?.status ?? null;
    return body;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || inFlight.current) return;
    const formElement = event.currentTarget;
    inFlight.current = true;
    setBusy(true);
    setMessage(null);
    setStale(false);
    const url = editing ? `/api/v1/school/career-counselor/records/${record!.id}` : "/api/v1/school/career-counselor/records";
    const result = await sendJson(url, editing ? "PATCH" : "POST", payload(new FormData(formElement)));
    inFlight.current = false;
    setBusy(false);
    if (!result.ok) {
      setStale(result.status === 409);
      setMessage({ text: result.message, failed: true });
      return;
    }
    setMessage({ text: "Record saved.", failed: false });
    if (!editing) formElement.reset();
    router.refresh();
    onDone();
  }

  const yesNo = (value: boolean | null | undefined) => (value === true ? "yes" : value === false ? "no" : "");

  return (
    <form className="form" onSubmit={submit} onKeyDown={onKey}>
      <fieldset className="form-busy-wrap" disabled={busy}>
        {!editing && (
          <>
            <div className="field">
              <label htmlFor={`${prefix}-student`}>Student</label>
              <select id={`${prefix}-student`} name="school_student_id" required defaultValue="">
                <option value="" disabled>Select student</option>
                {students.map((s) => <option key={s.id} value={s.id}>{s.full_name} — {s.school_name}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor={`${prefix}-type`}>Type</label>
              <select id={`${prefix}-type`} name="record_type" required value={recordType} onChange={(e) => setRecordType(e.target.value)}>
                <option value="" disabled>Select type</option>
                {Object.entries(RECORD_TYPE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </div>
          </>
        )}
        {structured && (
          <fieldset className="form-section">
            <legend>Session</legend>
            <div className="form-grid">
              <div className="field">
                <label htmlFor={`${prefix}-status`}>Status</label>
                <select id={`${prefix}-status`} value={status} onChange={(e) => setStatus(e.target.value as CareerStatus)} aria-describedby={`${prefix}-status-help`}>
                  {editing && !record?.status && <option value="">{statusLabel(null)}</option>}
                  {statusOptions(record?.status, !editing).map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
                </select>
                <p id={`${prefix}-status-help`} className="field-help muted">Not Started → Scheduled → Completed → Follow-up Required → Completed</p>
              </div>
              {status === "scheduled" && (
                <div className="field">
                  <label htmlFor={`${prefix}-scheduled`}>Scheduled for</label>
                  <input id={`${prefix}-scheduled`} name="scheduled_for" type="datetime-local" required />
                </div>
              )}
              {status === "completed" && (
                <div className="field">
                  <label htmlFor={`${prefix}-completed`}>Completed on (defaults to today)</label>
                  <input id={`${prefix}-completed`} name="completed_on" type="date" defaultValue={record?.completed_on ?? ""} />
                </div>
              )}
              {status === "follow_up_required" && (
                <div className="field">
                  <label htmlFor={`${prefix}-follow`}>Next follow-up</label>
                  <input id={`${prefix}-follow`} name="next_follow_up_date" type="date" required defaultValue={record?.next_follow_up_date ?? ""} />
                </div>
              )}
            </div>
          </fieldset>
        )}
        {structured && (["assessment", "recommendations"] as const).map((group) => (
          <fieldset className="form-section" key={group}>
            <legend>{group === "assessment" ? "Assessment" : "Recommendations"}</legend>
            <div className="form-grid">
              {CAREER_LIST_FIELDS.filter((f) => f.group === group).map((f) => (
                <div className="field" key={f.key}>
                  <label htmlFor={`${prefix}-${f.key}`}>{f.label}</label>
                  <input id={`${prefix}-${f.key}`} name={f.key} defaultValue={listText(record?.[f.key])} aria-describedby={`${prefix}-list-help`} />
                </div>
              ))}
              {group === "assessment" && (
                <div className="field">
                  <label htmlFor={`${prefix}-global`}>Interested in global education</label>
                  <select id={`${prefix}-global`} name="global_education_interest" defaultValue={yesNo(record?.global_education_interest)}>
                    <option value="">Not recorded</option><option value="yes">Yes</option><option value="no">No</option>
                  </select>
                </div>
              )}
            </div>
            <p id={`${prefix}-list-help`} className="field-help muted">Separate items with commas.</p>
          </fieldset>
        ))}
        {structured && (
          <fieldset className="form-section">
            <legend>Parent participation</legend>
            <div className="form-grid">
              <div className="field">
                <label htmlFor={`${prefix}-parent`}>Parent participated</label>
                <select id={`${prefix}-parent`} name="parent_participated" defaultValue={yesNo(record?.parent_participated)}>
                  <option value="">Not recorded</option><option value="yes">Yes</option><option value="no">No</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor={`${prefix}-parent-note`}>Participation note (optional)</label>
                <input id={`${prefix}-parent-note`} name="parent_participation_note" maxLength={500} defaultValue={record?.parent_participation_note ?? ""} />
              </div>
            </div>
          </fieldset>
        )}
        <fieldset className="form-section">
          <legend>Counsellor notes</legend>
          <div className="field full">
            <label htmlFor={`${prefix}-notes`}>Notes</label>
            <textarea id={`${prefix}-notes`} name="notes" required={!structured || status === "completed" || status === "follow_up_required"} defaultValue={record?.notes ?? ""} />
          </div>
        </fieldset>
        <div className="actions">
          <button className="btn" id={`${prefix}-save`}>{busy ? "Saving…" : editing ? "Save changes" : "Save record"}</button>
          {editing && <button type="button" className="btn secondary" onClick={onCancel}>Cancel</button>}
        </div>
      </fieldset>
      {message && <FormMessage message={message} />}
      {stale && <button type="button" className="btn secondary small" onClick={() => { router.refresh(); onCancel(); }}>Reload</button>}
    </form>
  );
}
```

Keep the create-mode labels exactly "Student", "Type", "Notes" and the button "Save record" — the existing
`SchoolCareerRecordsPanel` tests query them. If the file exceeds ~200 lines, move the Session fieldset into a local
`SessionFields` component in the same file during REFACTOR.

- [ ] **Step 6: Rewrite `SchoolCareerRecordsPanel.tsx`**

```tsx
"use client";

import { useState } from "react";
import CareerPreferencesCard from "@/components/CareerPreferencesCard";
import CareerRecordForm from "@/components/CareerRecordForm";
import { type CareerRecord, RECORD_TYPE_LABEL, statusLabel } from "@/lib/careerRecords";
import { formatCalendarDate } from "@/lib/formatDate";
import { refocus } from "@/lib/focus";

type Student = { id: string; full_name: string; school_name: string };

// SCH-004 + ENH-026: the Career Counselor's records -- visible to readers immediately (no Draft/Published gate). ENH-026 adds the
// §7 status and structured fields, and inline editing (spec §11.2 F2): opening moves focus to the form heading, closing returns it
// to the row's Edit button.
export default function SchoolCareerRecordsPanel({ records, students }: { records: CareerRecord[]; students: Student[] }) {
  const [editing, setEditing] = useState<CareerRecord | null>(null);

  function studentName(id: string) {
    return students.find((s) => s.id === id)?.full_name || "Unknown student";
  }

  function open(record: CareerRecord) {
    setEditing(record);
    refocus("career-edit-heading");
  }

  function close() {
    const id = editing?.id;
    setEditing(null);
    if (id) refocus(`career-edit-${id}`);
  }

  return (
    <div className="portal-content">
      <div className="card">
        <h2>Records</h2>
        {records.length === 0 ? (
          <p className="muted">No career guidance or counselling recorded yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Student</th><th>Type</th><th>Status</th><th>Next follow-up</th><th>Notes</th><th><span className="visually-hidden">Actions</span></th></tr>
              </thead>
              <tbody>
                {records.map((r) => (
                  <tr key={r.id}>
                    <td>{studentName(r.school_student_id)}</td>
                    <td>{RECORD_TYPE_LABEL[r.record_type] || r.record_type}</td>
                    <td>{r.record_type === "recommendation" ? "—" : <span className={`status${r.status === "completed" ? "" : " pending"}`}>{statusLabel(r.status)}</span>}</td>
                    <td>{r.next_follow_up_date ? formatCalendarDate(r.next_follow_up_date) : "—"}</td>
                    <td>{r.notes}</td>
                    <td><button id={`career-edit-${r.id}`} type="button" className="btn secondary small" onClick={() => open(r)}>Edit<span className="visually-hidden"> record for {studentName(r.school_student_id)}</span></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing && (
        <div className="action-card">
          <h3 id="career-edit-heading" tabIndex={-1}>Edit record for {studentName(editing.school_student_id)}</h3>
          <CareerRecordForm key={editing.id} students={students} record={editing} onDone={close} onCancel={close} />
        </div>
      )}

      <div className="action-card">
        <h3>Add a record</h3>
        {students.length === 0 ? (
          <p className="muted">No students in your portfolio yet. Contact your Overseas Admin.</p>
        ) : (
          <CareerRecordForm students={students} onDone={() => undefined} onCancel={() => undefined} />
        )}
      </div>

      <CareerPreferencesCard students={students} />
    </div>
  );
}
```

The Edit button's accessible name is "Edit record for <name>" (visible "Edit" + visually hidden suffix). In
`career-counselor/dashboard/page.tsx` replace the local `Record_` type with
`import type { CareerRecord } from "@/lib/careerRecords";` and use `CareerRecord[]`.

- [ ] **Step 7: Loading state** — `apps/web/app/school/career-counselor/dashboard/loading.tsx`

```tsx
// ENH-026 (spec §11.2 F5): shown while the server reads the counsellor's records, so navigation is never a blank screen.
export default function Loading() {
  return (
    <div className="portal-content" aria-busy="true" aria-label="Loading career records">
      <div className="card">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Run to verify pass**

Run: `cd apps/web && npx vitest run tests/components/careerRecords.test.ts tests/components/CareerRecordForm.test.tsx tests/components/SchoolCareerRecordsPanel.test.tsx && npx tsc --noEmit`
Expected: all passed; tsc exit 0.

- [ ] **Step 9: Commit**

```bash
git add apps/web/lib/careerRecords.ts apps/web/lib/apiErrors.ts apps/web/components/CareerRecordForm.tsx apps/web/components/SchoolCareerRecordsPanel.tsx apps/web/app/school/career-counselor/dashboard apps/web/tests/components/careerRecords.test.ts apps/web/tests/components/CareerRecordForm.test.tsx apps/web/tests/components/SchoolCareerRecordsPanel.test.tsx
git commit -m "feat(enh-026): counsellor form with status lifecycle, inline edit and loading state"
```

---

### Task 7: Read views — parent/school overview and Student 360° career tab

**Files:**
- Create: `apps/web/components/CareerRecordDetails.tsx`, `apps/web/tests/components/CareerRecordDetails.test.tsx`
- Modify: `apps/web/components/SchoolChildOverview.tsx` (types lines 14-31, career cards 126-151),
  `apps/web/components/Student360Panels.tsx:107-108`, `apps/web/tests/components/Student360Panels.test.tsx` (append)

**Interfaces:**
- Consumes: `CareerRecord`, `statusLabel`, `CAREER_LIST_FIELDS` from Task 6; overview keys from Task 5.
- Produces: `CareerRecordDetails({ record }: { record: CareerRecord })`.

- [ ] **Step 1: Write the failing tests**

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import CareerRecordDetails from "@/components/CareerRecordDetails";

afterEach(cleanup);

describe("CareerRecordDetails", () => {
  it("shows status as text, dates and only the fields that have content", () => {
    render(<CareerRecordDetails record={{ id: "r", school_student_id: "s", record_type: "counselling_note", notes: "Met.", created_at: "2026-09-01T00:00:00Z", status: "follow_up_required", next_follow_up_date: "2026-10-05", weak_areas: ["Essays"], recommended_careers: null, counselor_name: "Priya" }} />);
    expect(screen.getByText("Follow-up Required")).toBeInTheDocument();
    expect(screen.getByText("Weak areas")).toBeInTheDocument();
    expect(screen.queryByText("Recommended careers")).not.toBeInTheDocument();
    expect(screen.getByText("Priya")).toBeInTheDocument();
  });

  it("labels a legacy record without inventing fields", () => {
    render(<CareerRecordDetails record={{ id: "r", school_student_id: "s", record_type: "guidance_session", notes: "Old.", created_at: "2026-09-01T00:00:00Z", status: null }} />);
    expect(screen.getByText("No status (recorded before tracking)")).toBeInTheDocument();
    expect(screen.queryByRole("term")).toBeNull();
  });
});
```

Append to `Student360Panels.test.tsx`:

```tsx
  it("shows the counselling status in the career tab (ENH-026)", () => {
    const career: Tab360 = { status: "has_data", count: 1, not_tracked: [], data: { records: [{ id: "c2", record_type: "counselling_note", notes: "Met.", created_at: "2026-09-01T00:00:00Z", status: "scheduled", scheduled_for: "2026-10-01T04:30:00Z" }] } };
    render(view({ tabs: { ...BASE.tabs, career_guidance: career } }, "career_guidance"));
    expect(screen.getByText("Scheduled")).toBeInTheDocument();
  });
```

(Use the file's existing `view`/`BASE` helpers — read the top of `Student360Panels.test.tsx` and match its names
exactly before pasting.)

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && npx vitest run tests/components/CareerRecordDetails.test.tsx tests/components/Student360Panels.test.tsx`
Expected: FAIL — module not found; "Scheduled" not rendered.

- [ ] **Step 3: Implement `CareerRecordDetails.tsx`**

```tsx
import { CAREER_LIST_FIELDS, type CareerRecord, statusLabel } from "@/lib/careerRecords";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";

// ENH-026: the structured part of one counselling/guidance record, read-only. Empty fields are omitted (spec §11.2 F6);
// status is always text in the shared .status chip (never colour alone).
export default function CareerRecordDetails({ record }: { record: CareerRecord }) {
  const lists = CAREER_LIST_FIELDS.filter((f) => record[f.key]?.length);
  const yesNo = (v: boolean | null | undefined) => (v === true ? "Yes" : v === false ? "No" : null);
  const rows: [string, string][] = [
    ...(record.scheduled_for ? [["Scheduled for", formatSchoolDateTime(record.scheduled_for)] as [string, string]] : []),
    ...(record.completed_on ? [["Completed on", formatCalendarDate(record.completed_on)] as [string, string]] : []),
    ...(record.next_follow_up_date ? [["Next follow-up", formatCalendarDate(record.next_follow_up_date)] as [string, string]] : []),
    ...lists.map((f) => [f.label, record[f.key]!.join(", ")] as [string, string]),
    ...(yesNo(record.global_education_interest) ? [["Interested in global education", yesNo(record.global_education_interest)!] as [string, string]] : []),
    ...(yesNo(record.parent_participated) ? [["Parent participated", `${yesNo(record.parent_participated)}${record.parent_participation_note ? ` — ${record.parent_participation_note}` : ""}`] as [string, string]] : []),
    ...(record.counselor_name ? [["Counsellor", record.counselor_name] as [string, string]] : []),
  ];
  return (
    <div className="career-record-details">
      <span className={`status${record.status === "completed" ? "" : " pending"}`}>{statusLabel(record.status)}</span>
      {rows.length > 0 && (
        <dl className="student-profile">
          {rows.map(([term, value]) => <div key={term}><dt>{term}</dt><dd>{value}</dd></div>)}
        </dl>
      )}
    </div>
  );
}
```

(`formatSchoolDateTime` is already exported from `lib/formatDate.ts` — imported by `SchoolChildOverview.tsx`.)

- [ ] **Step 4: Wire it in**

`SchoolChildOverview.tsx`:
- replace `type CareerRecord = …` with `import type { CareerRecord } from "@/lib/careerRecords";`
- extend `ChildOverview` with `structured_recommendations?: { record_id: string; record_type: string; created_at: string; recommended_careers: string[] | null; recommended_courses: string[] | null; recommended_stream: string[] | null; recommended_skills: string[] | null }[];`
- in the Career guidance and Counselling cards, render each item as
  `<li key={r.id}><strong>{formatDate(r.created_at, false, SCHOOL_TIME_ZONE)}</strong> — {r.notes}<CareerRecordDetails record={r} /></li>`
- after the "Recommended careers" card's list add:

```tsx
        {(overview.structured_recommendations ?? []).length > 0 && (
          <>
            <h4>From counselling sessions</h4>
            <ul>{overview.structured_recommendations!.map((r) => (
              <li key={r.record_id}>
                {[...(r.recommended_careers ?? []), ...(r.recommended_courses ?? []), ...(r.recommended_stream ?? []), ...(r.recommended_skills ?? [])].map((item) => <span className="badge" key={item}>{item}</span>)}
                {" "}<span className="muted">{formatDate(r.created_at, false, SCHOOL_TIME_ZONE)}</span>
              </li>
            ))}</ul>
          </>
        )}
```

and change the empty-state condition to `overview.recommended_careers.length === 0 && !(overview.structured_recommendations ?? []).length`.

`Student360Panels.tsx` line 108 (career tab): render
`<li key={r.id}><strong>{RECORD_TYPE[r.record_type] ?? r.record_type}</strong> <span className="muted">{formatDate(r.created_at, false, SCHOOL_TIME_ZONE)}</span><p>{r.notes}</p>{r.record_type !== "recommendation" && <CareerRecordDetails record={r as CareerRecord} />}</li>`.

- [ ] **Step 5: Run to verify pass** (existing overview/360 tests unmodified)

Run: `cd apps/web && npx vitest run tests/components/CareerRecordDetails.test.tsx tests/components/Student360Panels.test.tsx tests/components/SchoolChildOverview.skills.test.tsx && npx tsc --noEmit`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/CareerRecordDetails.tsx apps/web/components/SchoolChildOverview.tsx apps/web/components/Student360Panels.tsx apps/web/tests/components/CareerRecordDetails.test.tsx apps/web/tests/components/Student360Panels.test.tsx
git commit -m "feat(enh-026): show counselling status and structured fields in overview and 360 view"
```

---

# Part 2 — ENH-021

### Task 8: Migration 0043 and `PortfolioEntry` columns

**Files:**
- Create: `apps/api/alembic/versions/0043_portfolio_internship_tracking.py`
- Modify: `apps/api/app/models.py:1133-1151` (`PortfolioEntry`)
- Test: `apps/api/tests/test_enh_021_migration.py`

**Interfaces:**
- Produces: `PortfolioEntry.mentor_name, mentor_designation, attendance_percent, completion_status, feedback,
  skills_acquired, certificate_key, certificate_content_type`; read-only `PortfolioEntry.has_certificate -> bool`;
  constant `INTERNSHIP_COLUMNS: tuple[str, ...]` in the migration.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-021 -- portfolio_entries internship tracking columns (spec §4.2, DEC-SCOPE-032)."""
import pytest
from enh005_helpers import mk_school
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import PortfolioEntry

COLUMNS = ("mentor_name", "mentor_designation", "attendance_percent", "completion_status", "feedback", "skills_acquired", "certificate_key", "certificate_content_type")


async def _entry(db, ctx, **kw):
    s, c = ctx["students"][0], ctx["coordinator"]
    e = PortfolioEntry(school_student_id=s.id, title="Intern", created_by_user_id=c.id, updated_by_user_id=c.id, **{"section": "internship", **kw})
    db.add(e)
    await db.commit()
    return e


@pytest.mark.asyncio
async def test_columns_exist_and_are_nullable(db_session):
    rows = dict((await db_session.execute(text("SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name = 'portfolio_entries'"))).all())
    assert all(rows.get(c) == "YES" for c in COLUMNS), rows


@pytest.mark.asyncio
async def test_existing_style_entries_keep_every_new_field_null(db_session):
    ctx = await mk_school(db_session, label="E21-Mig")
    e = await _entry(db_session, ctx, section="project")
    raw = (await db_session.execute(text("SELECT " + ", ".join(COLUMNS) + " FROM portfolio_entries WHERE id = :id"), {"id": e.id})).one()
    assert all(v is None for v in raw) and e.has_certificate is False


@pytest.mark.parametrize("kw", [{"attendance_percent": 101}, {"completion_status": "done"}, {"section": "project", "mentor_name": "M"}])
@pytest.mark.asyncio
async def test_checks_reject_bad_values(db_session, kw):
    ctx = await mk_school(db_session, label="E21-Chk")
    with pytest.raises(IntegrityError):
        await _entry(db_session, ctx, **kw)
    await db_session.rollback()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_021_migration.py -v`
Expected: FAIL — columns missing / `TypeError: 'attendance_percent' is an invalid keyword`.

- [ ] **Step 3: Write the migration**

```python
"""ENH-021 -- internship tracking on the portfolio `internship` section.

Revision ID: 0043_portfolio_internship_tracking
Revises: 0042_career_record_structured_fields

docs/superpowers/specs/2026-09-27-enh-021-026-internship-and-counselling-record-design.md §4.2 (DEC-SCOPE-032).
Additive only: nullable columns and three CHECKs (attendance range, completion values, internship-only fields).
No backfill. `downgrade()` drops what this adds; certificate objects already in storage become orphans and must be
removed by hand (prefix `portfolio-certificates/`).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0043_portfolio_internship_tracking"
down_revision = "0042_career_record_structured_fields"
branch_labels = None
depends_on = None

TABLE = "portfolio_entries"
COLUMNS = (
    ("mentor_name", sa.String(200)), ("mentor_designation", sa.String(200)), ("attendance_percent", sa.Integer()),
    ("completion_status", sa.String(20)), ("feedback", sa.Text()), ("skills_acquired", postgresql.JSON(none_as_null=True)),
    ("certificate_key", sa.String(300)), ("certificate_content_type", sa.String(50)),
)
CHECKS = {
    "ck_portfolio_attendance_percent": "attendance_percent IS NULL OR attendance_percent BETWEEN 0 AND 100",
    "ck_portfolio_completion_status": "completion_status IS NULL OR completion_status IN ('not_started', 'in_progress', 'completed', 'discontinued')",
    "ck_portfolio_internship_fields": "section = 'internship' OR (" + " AND ".join(f"{name} IS NULL" for name, _ in COLUMNS) + ")",
}


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns(TABLE)}
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints(TABLE)}
    for name, condition in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, condition)


def downgrade() -> None:
    for name in reversed(CHECKS):
        op.drop_constraint(name, TABLE, type_="check")
    for name, _type in reversed(COLUMNS):
        op.drop_column(TABLE, name)
```

- [ ] **Step 4: Mirror in the model** (add to `PortfolioEntry`)

```python
    __table_args__ = (
        Index("ix_portfolio_entries_student_section", "school_student_id", "section"),
        CheckConstraint("attendance_percent IS NULL OR attendance_percent BETWEEN 0 AND 100", name="ck_portfolio_attendance_percent"),
        CheckConstraint("completion_status IS NULL OR completion_status IN ('not_started', 'in_progress', 'completed', 'discontinued')", name="ck_portfolio_completion_status"),
        CheckConstraint(
            "section = 'internship' OR (mentor_name IS NULL AND mentor_designation IS NULL AND attendance_percent IS NULL AND completion_status IS NULL "
            "AND feedback IS NULL AND skills_acquired IS NULL AND certificate_key IS NULL AND certificate_content_type IS NULL)",
            name="ck_portfolio_internship_fields",
        ),
    )
    # ... existing columns unchanged ...
    # ENH-021 (DEC-SCOPE-032): internship tracking, section='internship' only (CHECK above). All nullable.
    mentor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mentor_designation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attendance_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills_acquired: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    certificate_key: Mapped[str | None] = mapped_column(String(300), nullable=True)  # never serialized (spec S9)
    certificate_content_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    @property
    def has_certificate(self) -> bool:
        return self.certificate_key is not None
```

The CHECK string must match the migration's generated text for `ck_portfolio_internship_fields` column-for-column
(same order).

- [ ] **Step 5: Apply, run, round-trip**

Run: `cd apps/api && alembic upgrade head && pytest tests/test_enh_021_migration.py -v && alembic downgrade -1 && alembic upgrade head && pytest tests/test_enh_021_migration.py tests/test_enh_012_digital_portfolio.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/alembic/versions/0043_portfolio_internship_tracking.py apps/api/app/models.py apps/api/tests/test_enh_021_migration.py
git commit -m "feat(enh-021): add internship tracking columns to portfolio entries (migration 0043)"
```

---

### Task 9: Internship fields, validation, tier split and locking on the portfolio entry API

**Files:**
- Modify: `apps/api/app/schemas.py` (`PortfolioEntryCreate` 952-985, `PortfolioEntryUpdate` 988-1024,
  `PortfolioEntryOut` 1027-1040); `apps/api/app/api/portfolio.py` (`_entry_out` 73-80, create 136-153,
  `_load_portfolio_entry` 156-160, update 163-192, delete 195-206)
- Test: `apps/api/tests/test_enh_021_internship.py`

**Interfaces:**
- Consumes: Task 8 columns; `require_school_entitlement`; `_clean_list`, `_no_control_characters`,
  `_clean_multiline_text`.
- Produces:
  - `schemas.INTERNSHIP_FIELD_KEYS: tuple[str, ...]`, `schemas.COMPLETION_STATUSES: tuple[str, ...]`
  - `portfolio._load_portfolio_entry(db, student_id, entry_id, *, for_update: bool = False) -> PortfolioEntry`
  - `portfolio.CERTIFICATE_PREFIX = "portfolio-certificates"`, `portfolio.discard_certificate(key: str, entry_id) -> None`
  - `_entry_out` / `PortfolioEntryOut` new keys: the six `INTERNSHIP_FIELD_KEYS`, `has_certificate`,
    `certificate_content_type`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-021 -- internship entries (spec §5.2, I1-I6, AC21-1/2/4/6/7, AC-R3)."""
import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school
from sqlalchemy import select

from app.models import PortfolioEntry
from app.schemas import PortfolioEntryOut

ENTRIES = "/api/v1/school/students/{sid}/portfolio/entries"
INTERNSHIP = {"section": "internship", "title": "Design intern", "organization": "Acme", "date_from": "2026-05-01", "date_to": "2026-06-30",
              "mentor_name": "R. Rao", "mentor_designation": "Lead designer", "attendance_percent": 92, "completion_status": "completed",
              "feedback": "Strong work.", "skills_acquired": ["Figma", "Research"]}


@pytest_asyncio.fixture
async def world(db_session):
    return await mk_school(db_session, label="E21", students=2)


def _url(world, i=0, eid=None):
    base = ENTRIES.format(sid=world["students"][i].id)
    return f"{base}/{eid}" if eid else base


@pytest.mark.asyncio
async def test_create_and_read_back_every_section_22_field(client, world):
    await login(client, world["coordinator"].email)
    r = await client.post(_url(world), json=INTERNSHIP)
    assert r.status_code == 201, r.text
    body = r.json()
    for key, value in INTERNSHIP.items():
        assert body[key] == value, key
    assert body["has_certificate"] is False and "certificate_key" not in body
    listed = (await client.get(f"/api/v1/school/students/{world['students'][0].id}/portfolio")).json()["entries"]["internship"][0]
    assert set(listed) == set(body)  # _entry_out and PortfolioEntryOut agree (A3)


@pytest.mark.asyncio
async def test_serializers_never_expose_the_storage_key():
    assert "certificate_key" not in PortfolioEntryOut.model_fields


@pytest.mark.parametrize("patch,detail", [
    ({"organization": None}, "organization"), ({"completion_status": "completed", "date_to": None}, "end date"),
    ({"attendance_percent": 101}, None),
])
@pytest.mark.asyncio
async def test_internship_rules_on_create(client, world, patch, detail):
    await login(client, world["coordinator"].email)
    r = await client.post(_url(world), json={**INTERNSHIP, **patch})
    assert r.status_code == 422
    if detail:
        assert detail in r.text


@pytest.mark.asyncio
async def test_tracking_fields_are_refused_on_other_sections(client, world):
    await login(client, world["coordinator"].email)
    r = await client.post(_url(world), json={"section": "project", "title": "P", "mentor_name": "M"})
    assert r.status_code == 422 and "only accepted for the internship section" in r.text
    project = (await client.post(_url(world), json={"section": "project", "title": "P"})).json()
    r = await client.patch(_url(world, eid=project["id"]), json={"feedback": "x"})
    assert (r.status_code, r.json()["detail"]) == (422, "internship fields are only accepted for the internship section")


@pytest.mark.asyncio
async def test_post_merge_rules_on_update(client, world):
    await login(client, world["coordinator"].email)
    e = (await client.post(_url(world), json={**INTERNSHIP, "completion_status": "in_progress", "date_to": None})).json()
    r = await client.patch(_url(world, eid=e["id"]), json={"completion_status": "completed"})
    assert (r.status_code, r.json()["detail"]) == (422, "An internship marked completed needs an end date")
    r = await client.patch(_url(world, eid=e["id"]), json={"organization": None})
    assert (r.status_code, r.json()["detail"]) == (422, "Company is required for an internship")


@pytest.mark.asyncio
async def test_certificate_blocks_leaving_completed(client, world, db_session):
    await login(client, world["coordinator"].email)
    e = (await client.post(_url(world), json=INTERNSHIP)).json()
    row = await db_session.get(PortfolioEntry, e["id"])
    row.certificate_key, row.certificate_content_type = "portfolio-certificates/x", "application/pdf"
    await db_session.commit()
    r = await client.patch(_url(world, eid=e["id"]), json={"completion_status": "in_progress"})
    assert (r.status_code, r.json()["detail"]) == (422, "Remove the certificate first")


@pytest.mark.asyncio
async def test_creating_an_internship_needs_platinum(client, db_session):
    gold = await mk_school(db_session, label="E21-Gold", tier="gold")
    await login(client, gold["coordinator"].email)
    r = await client.post(ENTRIES.format(sid=gold["students"][0].id), json=INTERNSHIP)
    assert r.status_code == 403 and "Internships" in r.json()["detail"]
    other = await client.post(ENTRIES.format(sid=gold["students"][0].id), json={"section": "project", "title": "P"})
    assert other.status_code == 201  # other sections keep the Gold gate


@pytest.mark.asyncio
async def test_gold_school_keeps_basic_edit_and_delete_of_existing_internships(client, db_session):
    gold = await mk_school(db_session, label="E21-Legacy", tier="gold")
    c = gold["coordinator"]
    legacy = PortfolioEntry(school_student_id=gold["students"][0].id, section="internship", title="Old", organization="Acme", created_by_user_id=c.id, updated_by_user_id=c.id)
    db_session.add(legacy)
    await db_session.commit()
    await login(client, c.email)
    url = f"{ENTRIES.format(sid=gold['students'][0].id)}/{legacy.id}"
    assert (await client.patch(url, json={"title": "Renamed", "date_from": "2026-01-01"})).status_code == 200
    assert (await client.patch(url, json={"mentor_name": "M"})).status_code == 403  # tracking needs Platinum
    body = (await client.get(f"/api/v1/school/students/{gold['students'][0].id}/portfolio")).json()["entries"]["internship"][0]
    assert body["completion_status"] is None  # AC21-7: legacy entry, "No status"
    assert (await client.delete(url)).status_code == 204


@pytest.mark.asyncio
async def test_unassigned_teacher_cannot_edit(client, world):
    await login(client, world["coordinator"].email)
    e = (await client.post(_url(world, i=1), json=INTERNSHIP)).json()  # student 1 is not assigned to the teacher
    await login(client, world["teacher"].email)
    assert (await client.patch(_url(world, i=1, eid=e["id"]), json={"title": "x"})).status_code == 403


@pytest.mark.asyncio
async def test_entry_id_under_another_student_is_404(client, world):
    await login(client, world["coordinator"].email)
    e = (await client.post(_url(world, i=0), json=INTERNSHIP)).json()
    assert (await client.patch(_url(world, i=1, eid=e["id"]), json={"title": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_storage_fields_are_not_writable(client, world):
    await login(client, world["coordinator"].email)
    r = await client.post(_url(world), json={**INTERNSHIP, "certificate_key": "portfolio-certificates/evil"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_021_internship.py -v`
Expected: FAIL — `extra_forbidden` 422 for `mentor_name` on create (the fields do not exist yet).

- [ ] **Step 3: Schemas** — add above `PortfolioEntryCreate`:

```python
# --- ENH-021: internship tracking on the portfolio `internship` section (spec §3.2 I1-I4) ---
INTERNSHIP_FIELD_KEYS: tuple[str, ...] = ("mentor_name", "mentor_designation", "attendance_percent", "completion_status", "feedback", "skills_acquired")
COMPLETION_STATUSES: tuple[str, ...] = ("not_started", "in_progress", "completed", "discontinued")
CompletionStatus = Literal["not_started", "in_progress", "completed", "discontinued"]
INTERNSHIP_ONLY_ERROR = "internship fields are only accepted for the internship section"
INTERNSHIP_COMPANY_ERROR = "Company is required for an internship"
INTERNSHIP_END_DATE_ERROR = "An internship marked completed needs an end date"


class _InternshipFields(BaseModel):
    mentor_name: str | None = Field(default=None, max_length=200)
    mentor_designation: str | None = Field(default=None, max_length=200)
    attendance_percent: StrictInt | None = Field(default=None, ge=0, le=100)
    completion_status: CompletionStatus | None = None
    feedback: str | None = Field(default=None, max_length=2000)
    skills_acquired: list[str] | None = None

    @field_validator("mentor_name", "mentor_designation")
    @classmethod
    def _single_line(cls, value: str | None) -> str | None:
        return _no_control_characters(value)

    @field_validator("feedback")
    @classmethod
    def _feedback(cls, value: str | None) -> str | None:
        return _clean_multiline_text(value)

    @field_validator("skills_acquired", mode="before")
    @classmethod
    def _skills(cls, value):
        return _clean_list(value)
```

Make both portfolio input models inherit it: `class PortfolioEntryCreate(_InternshipFields):` and
`class PortfolioEntryUpdate(_InternshipFields):` (their existing bodies unchanged; `model_config` stays on each).
Add to `PortfolioEntryCreate` a validator:

```python
    @model_validator(mode="after")
    def _internship_rules(self):
        tracking_sent = bool(self.model_fields_set & set(INTERNSHIP_FIELD_KEYS))
        if self.section != "internship":
            if tracking_sent:
                raise ValueError(INTERNSHIP_ONLY_ERROR)
            return self
        if not self.organization:
            raise ValueError(INTERNSHIP_COMPANY_ERROR)
        if self.completion_status == "completed" and self.date_to is None:
            raise ValueError(INTERNSHIP_END_DATE_ERROR)
        return self
```

Extend `PortfolioEntryOut` with:

```python
    mentor_name: str | None = None
    mentor_designation: str | None = None
    attendance_percent: int | None = None
    completion_status: str | None = None
    feedback: str | None = None
    skills_acquired: list[str] | None = None
    has_certificate: bool = False
    certificate_content_type: str | None = None
```

`StrictInt` — add to the pydantic import if absent.

- [ ] **Step 4: `portfolio.py`**

`_entry_out` — add after `"date_to": entry.date_to,`:

```python
        **{key: getattr(entry, key) for key in INTERNSHIP_FIELD_KEYS},
        "has_certificate": entry.has_certificate, "certificate_content_type": entry.certificate_content_type,
```

Helpers (after the imports/`WRITE_ROLES`):

```python
CERTIFICATE_PREFIX = "portfolio-certificates"


def _entry_service_key(section: str, tracking_sent: bool) -> str:
    """ENH-021 I6: Platinum `internships` to create an internship entry or to set its tracking fields; everything else keeps
    ENH-012's Gold `digital_portfolio_creation`, so a Gold school keeps control of internship entries it already has."""
    return "internships" if section == "internship" and tracking_sent else "digital_portfolio_creation"


def discard_certificate(key: str, entry_id) -> None:
    """Delete a certificate object after its row change committed. Only keys this module generated are ever deleted (S5)."""
    if not key.startswith(f"{CERTIFICATE_PREFIX}/"):
        logger.error("internship_certificate_discard_refused", extra={"extra_fields": {"entry_id": str(entry_id), "key_digest": _digest(key)}})
        return
    try:
        storage.delete(key)
    except Exception:
        logger.warning("internship_certificate_orphaned", extra={"extra_fields": {"entry_id": str(entry_id), "key_digest": _digest(key)}})
```

Imports: `from app.api.school_student_profile import _digest`, `from app.services.storage import storage`,
and from schemas `INTERNSHIP_FIELD_KEYS, INTERNSHIP_ONLY_ERROR, INTERNSHIP_COMPANY_ERROR, INTERNSHIP_END_DATE_ERROR`.

Create — replace the `require_school_entitlement` line and the constructor:

```python
    await require_school_entitlement(db, user, student.school_id, _entry_service_key(payload.section, payload.section == "internship"))
    entry = PortfolioEntry(
        school_student_id=student.id, section=payload.section, title=payload.title,
        description=payload.description, organization=payload.organization,
        date_from=payload.date_from, date_to=payload.date_to,
        **{key: getattr(payload, key) for key in INTERNSHIP_FIELD_KEYS},
        created_by_user_id=user.id, updated_by_user_id=user.id,
    )
```

`_load_portfolio_entry`:

```python
async def _load_portfolio_entry(db: AsyncSession, student_id: UUID, entry_id: UUID, *, for_update: bool = False) -> PortfolioEntry:
    stmt = select(PortfolioEntry).where(PortfolioEntry.id == entry_id)
    if for_update:  # ENH-021: edits, deletes and certificate changes on one entry serialize (spec §5.2)
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    entry = await db.scalar(stmt)
    if not entry or entry.school_student_id != student_id:
        raise HTTPException(404, "Portfolio entry not found")
    return entry
```

Update — replace from `entry = await _load_portfolio_entry(...)` through the date-range check:

```python
    entry = await _load_portfolio_entry(db, student.id, entry_id, for_update=True)
    fields_set = payload.model_fields_set
    tracking_sent = bool(fields_set & set(INTERNSHIP_FIELD_KEYS))
    if tracking_sent and entry.section != "internship":
        raise HTTPException(422, INTERNSHIP_ONLY_ERROR)
    # ENH-023 D8: editing an entry that existed before a downgrade finishes existing work.
    await require_school_entitlement(db, user, student.school_id, _entry_service_key(entry.section, tracking_sent), grandfathered_since=entry.created_at)
    for field in ("title", "description", "organization", "date_from", "date_to", *INTERNSHIP_FIELD_KEYS):
        if field in fields_set:
            setattr(entry, field, getattr(payload, field))
    if date_range_is_invalid(entry.date_from, entry.date_to):
        raise HTTPException(422, DATE_RANGE_ERROR)
    if entry.section == "internship":
        if not entry.organization:
            raise HTTPException(422, INTERNSHIP_COMPANY_ERROR)
        if entry.completion_status == "completed" and entry.date_to is None:
            raise HTTPException(422, INTERNSHIP_END_DATE_ERROR)
        if entry.certificate_key and entry.completion_status != "completed":
            raise HTTPException(422, "Remove the certificate first")
```

(Keep the long existing comment about `model_fields_set` above this block.)

Delete — lock and discard after commit:

```python
    entry = await _load_portfolio_entry(db, student.id, entry_id, for_update=True)
    await require_school_entitlement(db, user, student.school_id, "digital_portfolio_creation", grandfathered_since=entry.created_at)
    section, entry_id_str, certificate_key = entry.section, str(entry.id), entry.certificate_key
    await db.delete(entry)
    db.add(AuditLog(user_id=user.id, action="school.portfolio_entry_delete", entity_type="portfolio_entry", entity_id=entry_id_str, metadata_json={"section": section, "school_student_id": str(student.id), "had_certificate": certificate_key is not None}))
    await db.commit()
    if certificate_key:
        discard_certificate(certificate_key, entry_id_str)
```

- [ ] **Step 5: Run to verify pass, plus ENH-012/013/022/023 suites unmodified**

Run: `cd apps/api && pytest tests/test_enh_021_internship.py tests/test_enh_012_digital_portfolio.py tests/test_enh_013_360_view.py tests/test_enh_022_tier_enforcement.py tests/test_enh_023_tier_change.py -v`
Expected: all passed.

- [ ] **Step 6: REFACTOR** — the three internship rules exist in the create validator and the update route; if a
single `internship_rule_error(organization, completion_status, date_to) -> str | None` in `schemas.py` can serve
both without changing either error shape, extract it; rerun Step 5.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/schemas.py apps/api/app/api/portfolio.py apps/api/tests/test_enh_021_internship.py
git commit -m "feat(enh-021): internship tracking fields, rules, Platinum gate split and row locking"
```

---

### Task 10: Certificate endpoints

**Files:**
- Create: `apps/api/app/api/portfolio_certificates.py`, `apps/api/tests/test_enh_021_certificate.py`
- Modify: `apps/api/app/main.py` (import and add `portfolio_certificates.router` to the router tuple on line 53)

**Interfaces:**
- Consumes: `_load_student_for_reader`, `_require_portfolio_write`, `_load_portfolio_entry(for_update=True)`,
  `CERTIFICATE_PREFIX`, `discard_certificate` (Task 9); `detect_image_type`, `strip_metadata`, `InvalidImage`;
  `storage`; `require_school_entitlement`; `_digest`.
- Produces: `PUT|GET|DELETE /api/v1/school/students/{student_id}/portfolio/entries/{entry_id}/certificate`;
  `MAX_CERTIFICATE_BYTES = 5 * 1024 * 1024`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-021 -- internship certificate (spec §5.2, I5, S5/S6/S13, AC21-1/3/8)."""
import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school, mk_staff
from enh025_helpers import jpeg_bytes, png_bytes
from httpx import ASGITransport
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.main import app
from app.models import AuditLog, PortfolioEntry
from app.services.storage import storage

ENTRIES = "/api/v1/school/students/{sid}/portfolio/entries"
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture(autouse=True)
def _local_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "bucket", "")
    monkeypatch.setattr(storage, "local_dir", tmp_path)
    return tmp_path


@pytest_asyncio.fixture
async def world(db_session, client):
    ctx = await mk_school(db_session, label="E21-Cert", students=2)
    await login(client, ctx["coordinator"].email)
    body = {"section": "internship", "title": "Intern", "organization": "Acme", "date_from": "2026-05-01", "date_to": "2026-06-01", "completion_status": "completed"}
    ctx["entry"] = (await client.post(ENTRIES.format(sid=ctx["students"][0].id), json=body)).json()
    ctx["url"] = f"{ENTRIES.format(sid=ctx['students'][0].id)}/{ctx['entry']['id']}/certificate"
    return ctx


async def _put(client, url, data, name="c.pdf", ctype="application/pdf"):
    return await client.put(url, files={"file": (name, data, ctype)})


def _objects(root):
    return [p for p in root.rglob("*") if p.is_file()]


@pytest.mark.asyncio
async def test_pdf_upload_and_download_by_every_reader(client, world, db_session):
    r = await _put(client, world["url"], PDF)
    assert r.status_code == 200 and r.json() == {"has_certificate": True, "content_type": "application/pdf"}
    for role in ("coordinator", "principal", "teacher", "parent"):
        await login(client, world[role].email)
        got = await client.get(world["url"])
        assert got.status_code == 200, role
        assert got.content == PDF
        assert got.headers["content-disposition"] == 'attachment; filename="internship-certificate.pdf"'
        assert got.headers["x-content-type-options"] == "nosniff"
        assert got.headers["content-security-policy"] == "default-src 'none'; sandbox"
        assert got.headers["cache-control"] == "private, no-store"
    downloads = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.internship_certificate_download", AuditLog.entity_id == world["entry"]["id"]))
    assert downloads == 4  # AC21-8


@pytest.mark.asyncio
async def test_images_have_metadata_stripped(client, world):
    assert (await _put(client, world["url"], jpeg_bytes(with_gps=True), "c.jpg", "image/jpeg")).status_code == 200
    got = await client.get(world["url"])
    assert b"GPSLatitude" not in got.content and got.headers["content-disposition"].endswith('.jpg"')


@pytest.mark.asyncio
async def test_type_is_decided_by_content_not_by_name(client, world):
    r = await _put(client, world["url"], b"<html><script>alert(1)</script></html>", "c.pdf", "application/pdf")
    assert (r.status_code, r.json()["detail"]) == (415, "certificate must be a PDF, JPEG or PNG file")


@pytest.mark.asyncio
async def test_size_and_empty_limits(client, world):
    assert (await _put(client, world["url"], b"")).status_code == 422
    big = PDF + b"0" * (5 * 1024 * 1024)
    assert (await _put(client, world["url"], big)).status_code == 413


@pytest.mark.asyncio
async def test_only_completed_internships_take_a_certificate(client, world, db_session):
    row = await db_session.get(PortfolioEntry, world["entry"]["id"])
    row.completion_status = "in_progress"
    await db_session.commit()
    r = await _put(client, world["url"], PDF)
    assert (r.status_code, r.json()["detail"]) == (422, "A certificate can only be attached to a completed internship")


@pytest.mark.asyncio
async def test_replace_and_remove_delete_the_old_object(client, world, _local_storage):
    await _put(client, world["url"], PDF)
    await _put(client, world["url"], png_bytes(), "c.png", "image/png")
    assert len(_objects(_local_storage)) == 1
    assert (await client.delete(world["url"])).status_code == 204
    assert _objects(_local_storage) == []
    assert (await client.get(world["url"])).status_code == 404
    assert (await client.delete(world["url"])).status_code == 204  # idempotent


@pytest.mark.asyncio
async def test_deleting_the_entry_deletes_its_certificate(client, world, _local_storage):
    await _put(client, world["url"], PDF)
    entry_url = world["url"].removesuffix("/certificate")
    assert (await client.delete(entry_url)).status_code == 204
    assert _objects(_local_storage) == []


@pytest.mark.asyncio
async def test_failed_commit_leaves_no_new_object(client, world, _local_storage, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    original = AsyncSession.commit

    async def failing(self):
        raise RuntimeError("db down")
    monkeypatch.setattr(AsyncSession, "commit", failing)
    with pytest.raises(RuntimeError):
        await _put(client, world["url"], PDF)
    monkeypatch.setattr(AsyncSession, "commit", original)
    assert _objects(_local_storage) == []


@pytest.mark.asyncio
async def test_authorization(client, world, db_session):
    await _put(client, world["url"], PDF)
    await login(client, world["parent"].email)
    assert (await _put(client, world["url"], PDF)).status_code == 403  # readers cannot write
    other = await mk_school(db_session, label="E21-CertO")
    await login(client, other["coordinator"].email)
    assert (await client.get(world["url"])).status_code == 403
    await login(client, world["coordinator"].email)
    project = (await client.post(ENTRIES.format(sid=world["students"][0].id), json={"section": "project", "title": "P"})).json()
    project_url = f"{ENTRIES.format(sid=world['students'][0].id)}/{project['id']}/certificate"
    assert (await _put(client, project_url, PDF)).status_code == 404


@pytest.mark.asyncio
async def test_denied_download_writes_no_audit(client, world, db_session):
    await _put(client, world["url"], PDF)
    other = await mk_school(db_session, label="E21-CertD")
    await login(client, other["coordinator"].email)
    await client.get(world["url"])
    count = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.internship_certificate_download", AuditLog.entity_id == world["entry"]["id"]))
    assert count == 0


@pytest.mark.asyncio
async def test_gold_school_cannot_manage_certificates(client, db_session):
    gold = await mk_school(db_session, label="E21-CertG", tier="gold")
    c = gold["coordinator"]
    e = PortfolioEntry(school_student_id=gold["students"][0].id, section="internship", title="Old", organization="Acme", date_to=None, created_by_user_id=c.id, updated_by_user_id=c.id)
    db_session.add(e)
    await db_session.commit()
    e.completion_status, e.date_to = "completed", __import__("datetime").date(2026, 6, 1)
    await db_session.commit()
    await login(client, c.email)
    r = await _put(client, f"{ENTRIES.format(sid=gold['students'][0].id)}/{e.id}/certificate", PDF)
    assert r.status_code == 403


@asynccontextmanager
async def _client_for(email):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await login(c, email)
        yield c


@asynccontextmanager
async def _held(pk):
    session = SessionLocal()
    try:
        await session.execute(select(PortfolioEntry).where(PortfolioEntry.id == pk).with_for_update())
        yield
    finally:
        await session.rollback()
        await session.close()


@pytest.mark.asyncio
async def test_concurrent_uploads_leave_exactly_one_object(world, _local_storage, db_session):
    async with _client_for(world["coordinator"].email) as a, _client_for(world["coordinator"].email) as b:
        async with _held(world["entry"]["id"]):
            t1 = asyncio.create_task(_put(a, world["url"], PDF))
            t2 = asyncio.create_task(_put(b, world["url"], png_bytes(), "c.png", "image/png"))
            await asyncio.sleep(0.3)
        assert {(await t1).status_code, (await t2).status_code} == {200}
    row = await db_session.get(PortfolioEntry, world["entry"]["id"], populate_existing=True)
    objects = _objects(_local_storage)
    assert len(objects) == 1 and objects[0].as_posix().endswith(row.certificate_key)
```

Clean the `__import__("datetime")` line in REFACTOR (import `date` at the top).

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_021_certificate.py -v`
Expected: FAIL — 404/405 for every `/certificate` call (route missing).

- [ ] **Step 3: Implement `portfolio_certificates.py`**

```python
"""ENH-021 -- internship certificate upload/download/remove (docs/superpowers/specs/
2026-09-27-enh-021-026-internship-and-counselling-record-design.md §5.2, DEC-SCOPE-032 I5, security S5/S6/S13).
Modelled on ENH-025's photo routes (school_student_profile.py): content-sniffed type, size cap before a full read,
image metadata stripped, server-generated key, write -> commit -> delete old (a failed commit deletes the new object).
Scope and write rules are portfolio.py's own, imported -- never re-implemented here."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.portfolio import CERTIFICATE_PREFIX, _load_portfolio_entry, _require_portfolio_write, discard_certificate
from app.api.schools import _load_student_for_reader, require_school_entitlement
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, PortfolioEntry, SchoolStudent, User
from app.services.image_metadata import InvalidImage, detect_image_type, strip_metadata
from app.services.storage import storage

router = APIRouter(prefix="/school", tags=["school-portfolio"])
logger = get_logger("app.portfolio.certificate")

MAX_CERTIFICATE_BYTES = 5 * 1024 * 1024
PDF = "application/pdf"
EXTENSION = {PDF: "pdf", "image/jpeg": "jpg", "image/png": "png"}
CERTIFICATE_URL = "/students/{student_id}/portfolio/entries/{entry_id}/certificate"
HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"}


def _content_type(data: bytes) -> str | None:
    return PDF if data.startswith(b"%PDF-") else detect_image_type(data)


async def _writable_internship(db: AsyncSession, user: User, student_id: UUID, entry_id: UUID) -> tuple[SchoolStudent, PortfolioEntry]:
    student = await _load_student_for_reader(db, user, student_id)
    _require_portfolio_write(user, student)
    entry = await _load_portfolio_entry(db, student.id, entry_id, for_update=True)
    if entry.section != "internship":
        raise HTTPException(404, "Internship entry not found")
    return student, entry


@router.put(CERTIFICATE_URL)
async def put_certificate(student_id: UUID, entry_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student, entry = await _writable_internship(db, user, student_id, entry_id)
    if entry.completion_status != "completed":
        raise HTTPException(422, "A certificate can only be attached to a completed internship")
    await require_school_entitlement(db, user, student.school_id, "internships", grandfathered_since=entry.created_at)
    data = await file.read(MAX_CERTIFICATE_BYTES + 1)
    if not data:
        raise HTTPException(422, "certificate file is empty")
    if len(data) > MAX_CERTIFICATE_BYTES:
        raise HTTPException(413, "certificate must be at most 5 MB")
    content_type = _content_type(data)
    if content_type is None:
        raise HTTPException(415, "certificate must be a PDF, JPEG or PNG file")
    if content_type != PDF:
        try:
            data = strip_metadata(data, content_type)
        except InvalidImage:
            raise HTTPException(422, "certificate could not be read as a valid JPEG or PNG image") from None

    old_key, new_key = entry.certificate_key, f"{CERTIFICATE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(new_key, data, content_type)
    except Exception:
        logger.exception("internship_certificate_store_failed", extra={"extra_fields": {"entry_id": str(entry.id)}})
        raise HTTPException(500, "Could not store the certificate; please try again") from None
    entry.certificate_key, entry.certificate_content_type, entry.updated_by_user_id = new_key, content_type, user.id
    db.add(AuditLog(user_id=user.id, action="school.internship_certificate_set", entity_type="portfolio_entry", entity_id=str(entry.id), metadata_json={"school_student_id": str(student.id), "replaced": old_key is not None, "content_type": content_type, "bytes": len(data)}))
    try:
        await db.commit()
    except Exception:
        discard_certificate(new_key, entry.id)
        raise
    if old_key:
        discard_certificate(old_key, entry.id)
    logger.info("internship_certificate_set", extra={"extra_fields": {"actor_id": str(user.id), "entry_id": str(entry.id), "replaced": old_key is not None, "bytes": len(data)}})
    return {"has_certificate": True, "content_type": content_type}


@router.get(CERTIFICATE_URL)
async def get_certificate(student_id: UUID, entry_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_student_for_reader(db, user, student_id)
    entry = await _load_portfolio_entry(db, student.id, entry_id)
    if entry.section != "internship" or not entry.certificate_key:
        raise HTTPException(404, "No certificate on file")
    try:
        data = storage.read_bytes(entry.certificate_key)
    except FileNotFoundError:
        logger.warning("internship_certificate_object_missing", extra={"extra_fields": {"entry_id": str(entry.id)}})
        raise HTTPException(404, "No certificate on file") from None
    # S13: the audit row is committed before any byte leaves; a failed commit serves nothing.
    db.add(AuditLog(user_id=user.id, action="school.internship_certificate_download", entity_type="portfolio_entry", entity_id=str(entry.id), metadata_json={"school_student_id": str(student.id), "role": user.role}))
    await db.commit()
    extension = EXTENSION.get(entry.certificate_content_type or "", "bin")
    return Response(content=data, media_type=entry.certificate_content_type, headers={**HEADERS, "Content-Disposition": f'attachment; filename="internship-certificate.{extension}"'})


@router.delete(CERTIFICATE_URL, status_code=204)
async def delete_certificate(student_id: UUID, entry_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student, entry = await _writable_internship(db, user, student_id, entry_id)
    await require_school_entitlement(db, user, student.school_id, "internships", grandfathered_since=entry.created_at)
    old_key = entry.certificate_key
    if old_key is None:
        return Response(status_code=204)
    entry.certificate_key, entry.certificate_content_type, entry.updated_by_user_id = None, None, user.id
    db.add(AuditLog(user_id=user.id, action="school.internship_certificate_remove", entity_type="portfolio_entry", entity_id=str(entry.id), metadata_json={"school_student_id": str(student.id)}))
    await db.commit()
    discard_certificate(old_key, entry.id)
    logger.info("internship_certificate_removed", extra={"extra_fields": {"actor_id": str(user.id), "entry_id": str(entry.id)}})
    return Response(status_code=204)
```

`main.py`: add `portfolio_certificates` to the `from app.api import (...)` list and `portfolio_certificates.router`
to the router tuple on line 53 (after `portfolio.router`).

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/api && pytest tests/test_enh_021_certificate.py tests/test_enh_021_internship.py tests/test_enh_025_photo.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/portfolio_certificates.py apps/api/app/main.py apps/api/tests/test_enh_021_certificate.py
git commit -m "feat(enh-021): internship certificate upload, audited download and removal"
```

---

### Task 11: Sensitive-log assertions (AC-R4)

**Files:**
- Test: `apps/api/tests/test_enh_021_026_logging.py` (new; no production change expected)

**Interfaces:**
- Consumes: the routes from Tasks 3, 4, 9, 10.

- [ ] **Step 1: Write the test**

```python
"""AC-R4 -- no response or log line carries storage keys or sensitive free text (spec §11.3 S9/S10)."""
import logging

import pytest
from enh005_helpers import login, mk_school, mk_staff

from app.services.storage import storage

SECRET = "ZZ-sensitive-ZZ"


@pytest.fixture(autouse=True)
def _local_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "bucket", "")
    monkeypatch.setattr(storage, "local_dir", tmp_path)


@pytest.mark.asyncio
async def test_logs_and_responses_carry_no_sensitive_values(client, db_session, caplog):
    ctx = await mk_school(db_session, label="E21-Log")
    counselor = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    caplog.set_level(logging.DEBUG)
    await login(client, counselor.email)
    r = await client.post("/api/v1/school/career-counselor/records", json={"school_student_id": str(ctx["students"][0].id), "record_type": "counselling_note", "notes": SECRET, "weak_areas": [SECRET]})
    await client.patch(f"/api/v1/school/career-counselor/records/{r.json()['id']}", json={"academic_strengths": [SECRET]})
    await login(client, ctx["coordinator"].email)
    sid = ctx["students"][0].id
    e = (await client.post(f"/api/v1/school/students/{sid}/portfolio/entries", json={"section": "internship", "title": "T", "organization": "Acme", "date_to": "2026-06-01", "completion_status": "completed", "mentor_name": SECRET, "feedback": SECRET})).json()
    put = await client.put(f"/api/v1/school/students/{sid}/portfolio/entries/{e['id']}/certificate", files={"file": (f"{SECRET}.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")})
    assert "portfolio-certificates" not in put.text and "portfolio-certificates" not in str(e)
    logged = "\n".join(f"{rec.getMessage()} {getattr(rec, 'extra_fields', '')}" for rec in caplog.records)
    assert SECRET not in logged
    assert "portfolio-certificates/" not in logged
```

- [ ] **Step 2: Run** — Run: `cd apps/api && pytest tests/test_enh_021_026_logging.py -v`
Expected: PASS. If it fails, the failing log call is the defect: remove the offending field from that log's
`extra_fields` (never weaken the assertion); rerun.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_enh_021_026_logging.py
git commit -m "test(enh-021,enh-026): assert no sensitive values reach logs or responses"
```

---

### Task 12: ENH-021 aggregates (KPI, chart, usage, 360° programme)

**Files:**
- Modify: `apps/api/app/api/schools.py` (`UNTRACKED_SCHOOL_DASHBOARD_KPIS` 86-89, `UNTRACKED_SCHOOL_DASHBOARD_CHARTS`
  90-94, `_school_dashboard_payload` 383-487, `school_entitlements` 1041-1054); `apps/api/app/api/student_360.py`
  (programmes, ~line 108)
- Modify (requirement change): `apps/api/tests/test_sch_reports.py:302,305`, `apps/api/tests/test_sch_011_entitlements.py:137`
- Test: `apps/api/tests/test_enh_021_aggregates.py`

**Interfaces:**
- Produces: `schools.INTERNSHIP_STATUS_ORDER`, `schools.internship_progress(statuses: Iterable[str | None]) -> str`;
  dashboard payload key `internship_status: list[{status, count}]`; KPI `internships` tracked; entitlement
  `usage["internships"]: int`; 360° programme `{"key": "internship", "status": ...}`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-021 -- internships in the dashboard, entitlements and 360° view (spec §5.3, I7, I8, AC21-5)."""
import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school

from app.api.schools import internship_progress
from app.models import PortfolioEntry


@pytest.mark.parametrize("statuses,expected", [
    ([], "not_started"), ([None], "not_started"), (["discontinued"], "not_started"), (["not_started", "in_progress"], "in_progress"),
    (["in_progress", "completed"], "completed"), ([None, "completed"], "completed"),
])
def test_best_progress_wins(statuses, expected):
    assert internship_progress(statuses) == expected


@pytest_asyncio.fixture
async def world(db_session):
    ctx = await mk_school(db_session, label="E21-Agg", students=3)
    c, s = ctx["coordinator"], ctx["students"]
    for student, status in ((s[0], "completed"), (s[0], "in_progress"), (s[1], None)):
        db_session.add(PortfolioEntry(school_student_id=student.id, section="internship", title="I", organization="A", completion_status=status, created_by_user_id=c.id, updated_by_user_id=c.id))
    await db_session.commit()
    return ctx


@pytest.mark.asyncio
async def test_kpi_and_chart(client, world):
    await login(client, world["coordinator"].email)
    data = (await client.get("/api/v1/school/dashboard")).json()
    kpi = {k["key"]: k for k in data["school_crm_kpis"]}["internships"]
    assert kpi["tracked"] is True and kpi["value"] == 2
    assert data["internship_status"] == [
        {"status": "not_started", "count": 0}, {"status": "in_progress", "count": 1}, {"status": "completed", "count": 1},
        {"status": "discontinued", "count": 0}, {"status": "no_status", "count": 1},
    ]
    assert "internships" not in {c["key"] for c in data["untracked_charts"]}


@pytest.mark.asyncio
async def test_entitlement_usage_is_distinct_students(client, world):
    await login(client, world["coordinator"].email)
    services = {s["key"]: s for s in (await client.get("/api/v1/school/entitlements")).json()["services"]}
    assert services["internships"]["used"] == 2


@pytest.mark.asyncio
async def test_360_programme_status(client, world):
    await login(client, world["coordinator"].email)
    for i, expected in ((0, "completed"), (1, "not_started"), (2, "not_started")):
        body = (await client.get(f"/api/v1/school/students/{world['students'][i].id}/360-view")).json()
        programmes = {p["key"]: p["status"] for p in body["tabs"]["edusphere_programs"]["data"]["programmes"]}
        assert programmes["internship"] == expected, i
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_021_aggregates.py -v`
Expected: FAIL — `ImportError: cannot import name 'internship_progress'`.

- [ ] **Step 3: Implement**

`schools.py` — constants:

```python
UNTRACKED_SCHOOL_DASHBOARD_KPIS = {
    "digital_portfolios_created": "No confirmed School digital-portfolio model exists yet.",
}
UNTRACKED_SCHOOL_DASHBOARD_CHARTS = [
    {"key": "skills_training", "label": "Skills training", "note": "No confirmed School soft-skills training model exists yet."},
    {"key": "student_participation_by_program", "label": "Student participation by program", "note": "No confirmed School program-participation model exists yet."},
]
INTERNSHIP_STATUS_ORDER = ("not_started", "in_progress", "completed", "discontinued")  # ENH-021 I7 chart order, then "no_status"


def internship_progress(statuses) -> str:
    """ENH-021 I8 (§35): best progress wins. Not started, discontinued and legacy (None) entries all read as not started."""
    seen = set(statuses)
    if "completed" in seen:
        return "completed"
    return "in_progress" if "in_progress" in seen else "not_started"
```

`_school_dashboard_payload` — with the other per-student queries inside `if student_ids:` (initialise
`internship_rows: list = []` beside `career_rows`):

```python
        internship_rows = (await db.execute(
            select(PortfolioEntry.school_student_id, PortfolioEntry.completion_status)
            .where(PortfolioEntry.school_student_id.in_(student_ids), PortfolioEntry.section == "internship")
        )).all()
```

after the other derived sets:

```python
    internship_students = {student_id for student_id, _status in internship_rows}
    internship_status = [{"status": s, "count": sum(1 for _sid, status in internship_rows if status == s)} for s in INTERNSHIP_STATUS_ORDER]
    internship_status.append({"status": "no_status", "count": sum(1 for _sid, status in internship_rows if status is None)})
```

replace the internships KPI line with
`_school_dashboard_kpi("internships", "Internships", len(internship_students)),` and add
`"internship_status": internship_status,` beside `"visa_status"` in the returned dict. Add `PortfolioEntry` to the
models import if absent.

`school_entitlements` — inside `if student_ids:`:

```python
        usage["internships"] = await db.scalar(
            select(func.count(distinct(PortfolioEntry.school_student_id))).where(PortfolioEntry.school_student_id.in_(student_ids), PortfolioEntry.section == "internship")
        )
```

and add `"internships": 0` to the `else` branch's `usage.update({...})`. (`func`, `distinct` from `sqlalchemy`.)

`student_360.py` — before the `if school_role:` global-education append:

```python
    programmes.append({"key": "internship", "status": internship_progress(e["completion_status"] for e in entries["internship"])})  # ENH-021 I8
```

(import `internship_progress` from `app.api.schools`).

Requirement-change test edits:
- `test_sch_reports.py:302` → `assert kpis["internships"]["tracked"] is True and kpis["internships"]["value"] == 0`
- `test_sch_reports.py:305` → `assert {chart["key"] for chart in data["untracked_charts"]} == {"skills_training", "student_participation_by_program"}`
- `test_sch_011_entitlements.py:137` → drop `"internships"` from the tuple and add below the loop:
  `assert _service(body, "internships")["used"] == 0  # ENH-021: tracked now`
Each edit gets a trailing comment `# ENH-021 (DEC-SCOPE-032): internships are tracked by requirement`.

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/api && pytest tests/test_enh_021_aggregates.py tests/test_sch_reports.py tests/test_sch_011_entitlements.py tests/test_enh_013_360_view.py tests/test_enh_023_tier_rules.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/app/api/student_360.py apps/api/tests/test_enh_021_aggregates.py apps/api/tests/test_sch_reports.py apps/api/tests/test_sch_011_entitlements.py
git commit -m "feat(enh-021): track internships in the KPI, status chart, entitlement usage and 360 view"
```

---

### Task 13: Internship UI — form fields, details, certificate control

**Files:**
- Create: `apps/web/components/InternshipFields.tsx`, `apps/web/components/InternshipDetails.tsx`,
  `apps/web/components/InternshipCertificate.tsx`, `apps/web/tests/components/InternshipFields.test.tsx`,
  `apps/web/tests/components/InternshipCertificate.test.tsx`
- Modify: `apps/web/lib/portfolio.ts` (`PortfolioEntry` type), `apps/web/components/PortfolioEntryForm.tsx`,
  `apps/web/components/PortfolioPanel.tsx` (EntryList view branch, lines 72-76),
  `apps/web/components/Student360Panels.tsx` (`PROGRAMME` line 37, `Entries` line 44-52)

**Interfaces:**
- Consumes: API from Tasks 9, 10, 12.
- Produces:
  - `lib/portfolio.ts`: `PortfolioEntry` gains optional `mentor_name, mentor_designation, attendance_percent,
    completion_status, feedback, skills_acquired, has_certificate, certificate_content_type`;
    `COMPLETION_LABEL: Record<string, string>`; `type InternshipValues`; `internshipChanges(initial, current)`.
  - `InternshipFields({ values, onChange, disabled })`, `InternshipDetails({ entry, studentId, canEdit })`,
    `InternshipCertificate({ studentId, entryId, hasCertificate, contentType, canEdit, completed })`.

- [ ] **Step 1: Write the failing tests**

`InternshipFields.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import PortfolioEntryForm from "@/components/PortfolioEntryForm";
import { internshipChanges } from "@/lib/portfolio";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("internship entry form", () => {
  it("requires a company for an internship", async () => {
    render(<PortfolioEntryForm studentId="s1" section="internship" onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "Design intern" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Enter the company.")).toBeInTheDocument();
  });

  it("sends only the internship fields that changed on edit", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "e1" }) });
    vi.stubGlobal("fetch", fetchMock);
    const initial = { title: "Intern", description: null, organization: "Acme", date_from: null, date_to: null, mentor_name: "R", mentor_designation: null, attendance_percent: 90, completion_status: null, feedback: null, skills_acquired: null };
    render(<PortfolioEntryForm studentId="s1" section="internship" entryId="e1" initial={initial} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "Senior intern" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.title).toBe("Senior intern");
    expect(body).not.toHaveProperty("mentor_name");  // unchanged tracking fields are not sent (keeps the Gold gate)
  });

  it("computes changed internship fields", () => {
    expect(internshipChanges({ mentor_name: "A", skills_acquired: ["x"] }, { mentor_name: "A", skills_acquired: ["x", "y"] })).toEqual({ skills_acquired: ["x", "y"] });
  });
});
```

`InternshipCertificate.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import InternshipCertificate from "@/components/InternshipCertificate";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function pick(file: File) {
  fireEvent.change(screen.getByLabelText(/Upload certificate|Replace certificate/), { target: { files: [file] } });
}

describe("InternshipCertificate", () => {
  it("refuses a wrong type before uploading", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<InternshipCertificate studentId="s" entryId="e" hasCertificate={false} contentType={null} canEdit completed />);
    pick(new File(["x"], "a.txt", { type: "text/plain" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Certificate must be a PDF, JPEG or PNG file");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uploads and announces progress politely", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ has_certificate: true, content_type: "application/pdf" }) }));
    render(<InternshipCertificate studentId="s" entryId="e" hasCertificate={false} contentType={null} canEdit completed />);
    pick(new File(["%PDF-"], "c.pdf", { type: "application/pdf" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Certificate saved.");
    expect(screen.getByRole("link", { name: "Download certificate (PDF)" })).toHaveAttribute("href", "/api/v1/school/students/s/portfolio/entries/e/certificate");
  });

  it("shows the server's message on 413", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 413, json: async () => ({ detail: "certificate must be at most 5 MB" }) }));
    render(<InternshipCertificate studentId="s" entryId="e" hasCertificate={false} contentType={null} canEdit completed />);
    pick(new File(["%PDF-"], "c.pdf", { type: "application/pdf" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("certificate must be at most 5 MB");
  });

  it("is download-only for readers and absent when not completed", () => {
    const { rerender } = render(<InternshipCertificate studentId="s" entryId="e" hasCertificate contentType="image/png" canEdit={false} completed />);
    expect(screen.getByRole("link", { name: "Download certificate (image)" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/certificate/i, { selector: "input" })).toBeNull();
    rerender(<InternshipCertificate studentId="s" entryId="e" hasCertificate={false} contentType={null} canEdit completed={false} />);
    expect(screen.queryByLabelText(/Upload certificate/)).toBeNull();
  });

  it("requires confirmation to remove", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    render(<InternshipCertificate studentId="s" entryId="e" hasCertificate contentType="application/pdf" canEdit completed />);
    fireEvent.click(screen.getByRole("button", { name: "Remove certificate" }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/school/students/s/portfolio/entries/e/certificate", { method: "DELETE" }));
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && npx vitest run tests/components/InternshipFields.test.tsx tests/components/InternshipCertificate.test.tsx`
Expected: FAIL — no "Role" label; module not found.

- [ ] **Step 3: `lib/portfolio.ts`** — extend and add helpers:

```ts
export type InternshipValues = {
  mentor_name?: string | null; mentor_designation?: string | null; attendance_percent?: number | null;
  completion_status?: string | null; feedback?: string | null; skills_acquired?: string[] | null;
};
export type PortfolioEntry = { id: string; section: string; title: string; description: string | null; organization: string | null; date_from: string | null; date_to: string | null; created_at: string; updated_at: string }
  & InternshipValues & { has_certificate?: boolean; certificate_content_type?: string | null };

export const COMPLETION_LABEL: Record<string, string> = { not_started: "Not started", in_progress: "In progress", completed: "Completed", discontinued: "Discontinued" };
export const INTERNSHIP_KEYS = ["mentor_name", "mentor_designation", "attendance_percent", "completion_status", "feedback", "skills_acquired"] as const;

/** ENH-021: only the tracking fields that changed, so an edit of title/dates never trips the Platinum-only gate (spec I6). */
export function internshipChanges(initial: InternshipValues, current: InternshipValues): InternshipValues {
  const out: InternshipValues = {};
  for (const key of INTERNSHIP_KEYS) {
    if (JSON.stringify(initial[key] ?? null) !== JSON.stringify(current[key] ?? null)) (out as Record<string, unknown>)[key] = current[key] ?? null;
  }
  return out;
}
```

- [ ] **Step 4: `InternshipFields.tsx`**

```tsx
"use client";

import { COMPLETION_LABEL, type InternshipValues } from "@/lib/portfolio";
import { listText, splitList } from "@/lib/schoolStudents";

// ENH-021 (§22): the tracking fields of an internship entry, grouped per spec §11.2 F1. Controlled by PortfolioEntryForm.
export default function InternshipFields({ values, onChange, disabled }: { values: InternshipValues; onChange: (next: InternshipValues) => void; disabled: boolean }) {
  const set = (patch: InternshipValues) => onChange({ ...values, ...patch });
  return (
    <>
      <fieldset className="form-section">
        <legend>Mentor</legend>
        <div className="form-grid">
          <div className="field"><label htmlFor="pf-mentor">Mentor name (optional)</label><input id="pf-mentor" className="search" maxLength={200} disabled={disabled} value={values.mentor_name ?? ""} onChange={(e) => set({ mentor_name: e.target.value || null })} /></div>
          <div className="field"><label htmlFor="pf-mentor-role">Mentor designation (optional)</label><input id="pf-mentor-role" className="search" maxLength={200} disabled={disabled} value={values.mentor_designation ?? ""} onChange={(e) => set({ mentor_designation: e.target.value || null })} /></div>
        </div>
      </fieldset>
      <fieldset className="form-section">
        <legend>Progress</legend>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="pf-completion">Completion</label>
            <select id="pf-completion" className="search" disabled={disabled} value={values.completion_status ?? ""} onChange={(e) => set({ completion_status: e.target.value || null })}>
              <option value="">No status</option>
              {Object.entries(COMPLETION_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <p className="field-help muted">A completed internship needs an end date.</p>
          </div>
          <div className="field">
            <label htmlFor="pf-attendance">Attendance % (optional)</label>
            <input id="pf-attendance" className="search" type="number" inputMode="numeric" min={0} max={100} disabled={disabled} value={values.attendance_percent ?? ""} onChange={(e) => set({ attendance_percent: e.target.value === "" ? null : Number(e.target.value) })} />
          </div>
        </div>
      </fieldset>
      <fieldset className="form-section">
        <legend>Outcome</legend>
        <div className="field"><label htmlFor="pf-skills">Skills acquired (optional)</label><input id="pf-skills" className="search" disabled={disabled} value={listText(values.skills_acquired)} onChange={(e) => set({ skills_acquired: splitList(e.target.value).length ? splitList(e.target.value) : null })} aria-describedby="pf-skills-help" /><p id="pf-skills-help" className="field-help muted">Separate items with commas.</p></div>
        <div className="field"><label htmlFor="pf-feedback">Feedback (optional)</label><textarea id="pf-feedback" className="search" rows={3} maxLength={2000} disabled={disabled} value={values.feedback ?? ""} onChange={(e) => set({ feedback: e.target.value || null })} /></div>
      </fieldset>
    </>
  );
}
```

Note: `splitList` on a controlled comma input drops a trailing comma while typing. In REFACTOR, keep the raw text
in local state (`const [skillsText, setSkillsText] = useState(listText(values.skills_acquired))`) and only split in
`onChange`'s payload — adjust and rerun the tests.

- [ ] **Step 5: `PortfolioEntryForm.tsx`** — changes (everything else as today):
- extend `initial` prop type with `& InternshipValues`;
- `const internship = section === "internship";`
- `const [tracking, setTracking] = useState<InternshipValues>(() => pick(initial))` where `pick` copies
  `INTERNSHIP_KEYS` from `initial ?? {}`;
- label for title: `{internship ? "Role" : "Title"}`; organization label `{internship ? "Company" : "Organization (optional)"}`;
- validation before submit: `if (internship && !organization.trim()) { setFieldError("Enter the company."); return; }`
  (render it under the organization input with `id="pf-organization-error"` and `aria-invalid`);
- body: `...(internship ? (entryId ? internshipChanges(pick(initial), tracking) : clean(tracking)) : {})` where
  `clean` drops null/empty keys;
- render `{internship && <InternshipFields values={tracking} onChange={setTracking} disabled={busy} />}` before the
  description field.

Title field-error message stays "Enter a title." for non-internship sections and becomes "Enter the role." for
internships.

- [ ] **Step 6: `InternshipCertificate.tsx`**

```tsx
"use client";

import { ChangeEvent, useState } from "react";
import { detailMessage } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";

const MAX_BYTES = 5 * 1024 * 1024;
const TYPES = ["application/pdf", "image/jpeg", "image/png"];

// ENH-021 (I5): the certificate of a completed internship. Readers get a download link; writers also upload/replace/remove
// (two-step remove, as the photo control). Client checks are fast feedback only -- the server re-validates by content.
export default function InternshipCertificate({ studentId, entryId, hasCertificate, contentType, canEdit, completed }: {
  studentId: string; entryId: string; hasCertificate: boolean; contentType: string | null; canEdit: boolean; completed: boolean;
}) {
  const [present, setPresent] = useState(hasCertificate);
  const [kind, setKind] = useState(contentType);
  const [busy, setBusy] = useState<"upload" | "remove" | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const url = `/api/v1/school/students/${studentId}/portfolio/entries/${entryId}/certificate`;
  const inputId = `cert-${entryId}`;

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    if (!TYPES.includes(file.type)) return setMessage({ text: "Certificate must be a PDF, JPEG or PNG file", failed: true });
    if (file.size > MAX_BYTES) return setMessage({ text: "Certificate must be at most 5 MB", failed: true });
    setBusy("upload");
    setMessage(null);
    const body = new FormData();
    body.append("file", file);
    const response = await fetch(url, { method: "PUT", body }).catch(() => null);
    const data = response ? await response.json().catch(() => ({})) : {};
    setBusy(null);
    input.value = "";
    refocus(inputId);
    if (!response?.ok) return setMessage({ text: detailMessage(data.detail, "Upload failed; please try again."), failed: true });
    setPresent(true);
    setKind(data.content_type ?? file.type);
    setMessage({ text: "Certificate saved.", failed: false });
  }

  async function remove() {
    setBusy("remove");
    setMessage(null);
    const response = await fetch(url, { method: "DELETE" }).catch(() => null);
    setBusy(null);
    setConfirming(false);
    if (!response?.ok) return setMessage({ text: "Could not remove the certificate; please try again.", failed: true });
    setPresent(false);
    setMessage({ text: "Certificate removed.", failed: false });
  }

  if (!present && !(canEdit && completed)) return null;
  return (
    <div className="field">
      {present && <a className="btn ghost small" href={url} download>Download certificate ({kind === "application/pdf" ? "PDF" : "image"})</a>}
      {canEdit && completed && (
        <>
          <label htmlFor={inputId}>{present ? "Replace certificate" : "Upload certificate"} (PDF, JPEG or PNG, up to 5 MB)</label>
          <input id={inputId} type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={upload} disabled={busy !== null} />
          {busy === "upload" && <span className="muted" aria-live="polite">Uploading…</span>}
          {present && !confirming && <button type="button" className="btn ghost small" onClick={() => setConfirming(true)} disabled={busy !== null}>Remove certificate</button>}
          {confirming && (
            <div className="actions">
              <button type="button" className="btn small" onClick={remove} disabled={busy !== null}>{busy === "remove" ? "Removing…" : "Confirm remove"}</button>
              <button type="button" className="btn secondary small" onClick={() => setConfirming(false)}>Cancel</button>
            </div>
          )}
        </>
      )}
      {message && (message.failed ? <div className="form-error" role="alert">{message.text}</div> : <div className="form-message" role="status" aria-live="polite">{message.text}</div>)}
    </div>
  );
}
```

`detailMessage` is exported from `lib/apiErrors.ts` (confirm; `SchoolStudentPhoto` imports a same-named helper from
`lib/schoolStudents` — use whichever exists, not both).

- [ ] **Step 7: `InternshipDetails.tsx`** and wiring

```tsx
import InternshipCertificate from "@/components/InternshipCertificate";
import { COMPLETION_LABEL, type PortfolioEntry } from "@/lib/portfolio";

// ENH-021: an internship entry's tracking fields, read-only; empty fields omitted, status as text (spec §11.2 F6/F10).
export default function InternshipDetails({ entry, studentId, canEdit }: { entry: PortfolioEntry; studentId: string; canEdit: boolean }) {
  const mentor = [entry.mentor_name, entry.mentor_designation].filter(Boolean).join(", ");
  return (
    <div className="internship-details">
      <span className={`status${entry.completion_status === "completed" ? "" : " pending"}`}>{entry.completion_status ? COMPLETION_LABEL[entry.completion_status] : "No status"}</span>
      <dl className="student-profile">
        {mentor && <div><dt>Mentor</dt><dd>{mentor}</dd></div>}
        {entry.attendance_percent != null && <div><dt>Attendance</dt><dd>{entry.attendance_percent}%</dd></div>}
        {entry.skills_acquired?.length ? <div><dt>Skills acquired</dt><dd>{entry.skills_acquired.join(", ")}</dd></div> : null}
        {entry.feedback && <div><dt>Feedback</dt><dd>{entry.feedback}</dd></div>}
      </dl>
      <InternshipCertificate studentId={studentId} entryId={entry.id} hasCertificate={Boolean(entry.has_certificate)} contentType={entry.certificate_content_type ?? null} canEdit={canEdit} completed={entry.completion_status === "completed"} />
    </div>
  );
}
```

`PortfolioPanel.tsx` EntryList view branch: after `{e.description && …}` add
`{e.section === "internship" && <InternshipDetails entry={e} studentId={studentId} canEdit={canEdit} />}`; pass the
tracking fields in the edit form's `initial` (spread `e`).
`Student360Panels.tsx`: `PROGRAMME` gains `internship: "Internship"`; in `Entries` add
`{e.completion_status ? <> <StatusChip status={e.completion_status} /></> : null}` after the dates (`StatusChip`
already imported; `COMPLETION_LABEL` values match its `not_started`/`in_progress`/`completed` labels — add
`discontinued: "Discontinued"` to `STATUS_LABEL` in `SchoolChildOverview.tsx` if absent).

- [ ] **Step 8: Run to verify pass** (existing portfolio/360 tests unmodified)

Run: `cd apps/web && npx vitest run tests/components/InternshipFields.test.tsx tests/components/InternshipCertificate.test.tsx tests/components/PortfolioPanel.test.tsx tests/components/Student360Panels.test.tsx && npx tsc --noEmit`
Expected: all passed.

- [ ] **Step 9: Commit**

```bash
git add apps/web/lib/portfolio.ts apps/web/components/InternshipFields.tsx apps/web/components/InternshipDetails.tsx apps/web/components/InternshipCertificate.tsx apps/web/components/PortfolioEntryForm.tsx apps/web/components/PortfolioPanel.tsx apps/web/components/Student360Panels.tsx apps/web/components/SchoolChildOverview.tsx apps/web/tests/components/InternshipFields.test.tsx apps/web/tests/components/InternshipCertificate.test.tsx
git commit -m "feat(enh-021): internship fields, details and certificate control in the portfolio"
```

---

### Task 14: E2E — both features in the real browser

**Files:**
- Create: `apps/web/tests/e2e/enh-026-counselling-record.spec.ts`, `apps/web/tests/e2e/enh-021-internship.spec.ts`

**Interfaces:**
- Consumes: `E2E_PASSWORD`, `createAndActivate` from `./helpers/welcome`; the `apiAs`/`signIn` pattern from
  `enh-013-student-360.spec.ts`.

- [ ] **Step 1: Write `enh-026-counselling-record.spec.ts`**

```ts
import { expect, request as playwrightRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ENH-026 (AC26-1..AC26-8, AC-R5): a counsellor records a session through the real form, moves it Scheduled -> Completed with
// the keyboard, and the parent sees the status. Setup is API-only (throwaway school), like enh-013.
const unique = Date.now();
const email = (who: string) => `enh026-e2e-${who}-${unique}@example.local`;
const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";
const ctx = { studentName: `Asha 026 ${unique}`, parentEmail: email("parent"), studentId: "" };

async function apiAs(address: string, password: string): Promise<APIRequestContext> {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post("/api/v1/auth/login", { data: { email: address, password, division: "overseas" } });
  if (!res.ok()) throw new Error(`login ${address}: ${res.status()}`);
  return api;
}

async function signIn(page: Page, address: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/overseas/login");
  await page.fill("#login-email", address);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test.describe.serial("ENH-026 counselling record", () => {
  test.beforeAll(async () => {
    test.setTimeout(120_000);
    const admin = await apiAs("overseasadmin@edusphere.local", "Demo@123");
    const school = await createAndActivate(admin, "/api/v1/overseas-admin/schools", { name: `E2E 026 School ${unique}`, coordinator_full_name: "E2E 026 Coordinator", coordinator_email: email("coord") });
    await admin.patch(`/api/v1/overseas-admin/schools/${school.id}`, { data: { tier: "platinum" } });
    await createAndActivate(admin, "/api/v1/overseas-admin/school-staff", { role: "career_counselor", full_name: "E2E 026 Counselor", email: email("counselor"), school_ids: [school.id] });
    await admin.dispose();
    const coord = await apiAs(email("coord"), E2E_PASSWORD);
    const created = await coord.post("/api/v1/school/students", { data: { full_name: ctx.studentName, grade_or_class: "Grade 9", parent_name: "E2E 026 Parent", parent_email: ctx.parentEmail } });
    const student = await created.json();
    ctx.studentId = student.id;
    await coord.dispose();
    const accept = await playwrightRequest.newContext({ baseURL });
    await accept.post(`/api/v1/school/invites/${student.development_invite_token}/accept`, { data: { password: E2E_PASSWORD } });
    await accept.dispose();
  });

  test("counsellor schedules, then completes a session with the keyboard", async ({ page }) => {
    await signIn(page, email("counselor"), E2E_PASSWORD, "/school/career-counselor/dashboard");
    const add = page.locator(".action-card", { has: page.getByRole("heading", { name: "Add a record" }) });
    await add.getByLabel("Student").selectOption({ label: new RegExp(ctx.studentName) as unknown as string });
    await add.getByLabel("Type").selectOption("counselling_note");
    await add.getByLabel("Status").selectOption("scheduled");
    await add.getByLabel("Scheduled for").fill("2026-12-01T10:00");
    await add.getByLabel("Weak areas").fill("Essays, Time management");
    await add.getByRole("button", { name: "Save record" }).click();
    await expect(add.getByRole("status")).toHaveText("Record saved.");
    const row = page.getByRole("row", { name: new RegExp(ctx.studentName) });
    await expect(row.getByText("Scheduled")).toBeVisible();

    await row.getByRole("button", { name: `Edit record for ${ctx.studentName}` }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: `Edit record for ${ctx.studentName}` })).toBeFocused();
    await page.getByLabel("Status").first().selectOption("completed");
    await page.getByLabel("Notes").first().fill("Discussed essay practice.");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("row", { name: new RegExp(ctx.studentName) }).getByText("Completed")).toBeVisible();
    await expect(page.getByRole("button", { name: `Edit record for ${ctx.studentName}` })).toBeFocused();
  });

  test("parent sees the completed counselling status", async ({ page }) => {
    await signIn(page, ctx.parentEmail, E2E_PASSWORD, "/school/parent/dashboard");
    await page.goto(`/school/parent/children/${ctx.studentId}`);
    await expect(page.getByText("Completed").first()).toBeVisible();
    await expect(page.getByText("Weak areas")).toBeVisible();
  });

  for (const width of [320, 768, 1024, 1440]) {
    test(`counsellor screen has no page-level horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page, email("counselor"), E2E_PASSWORD, "/school/career-counselor/dashboard");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }
});
```

(Adjust `selectOption({ label })` to the exact option text "<name> — <school>" once the school name is known; use
`page.getByLabel("Student").selectOption({ index: 1 })` if a regex label is not supported.)

- [ ] **Step 2: Write `enh-021-internship.spec.ts`**

```ts
import { expect, request as playwrightRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ENH-021 (AC21-1, AC21-3, AC21-5): a Platinum school's coordinator adds an internship through the real form, marks it completed,
// uploads a certificate; the parent downloads it; the KPI counts the student.
const unique = Date.now();
const email = (who: string) => `enh021-e2e-${who}-${unique}@example.local`;
const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";
const ctx = { studentId: "", parentEmail: email("parent") };
const PDF = Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n");

async function apiAs(address: string, password: string): Promise<APIRequestContext> {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post("/api/v1/auth/login", { data: { email: address, password, division: "overseas" } });
  if (!res.ok()) throw new Error(`login ${address}: ${res.status()}`);
  return api;
}

async function signIn(page: Page, address: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/overseas/login");
  await page.fill("#login-email", address);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test.describe.serial("ENH-021 internship", () => {
  test.beforeAll(async () => {
    test.setTimeout(120_000);
    const admin = await apiAs("overseasadmin@edusphere.local", "Demo@123");
    const school = await createAndActivate(admin, "/api/v1/overseas-admin/schools", { name: `E2E 021 School ${unique}`, coordinator_full_name: "E2E 021 Coordinator", coordinator_email: email("coord") });
    await admin.patch(`/api/v1/overseas-admin/schools/${school.id}`, { data: { tier: "platinum" } });
    await admin.dispose();
    const coord = await apiAs(email("coord"), E2E_PASSWORD);
    const student = await (await coord.post("/api/v1/school/students", { data: { full_name: `Ravi 021 ${unique}`, grade_or_class: "Grade 11", parent_name: "E2E 021 Parent", parent_email: ctx.parentEmail } })).json();
    ctx.studentId = student.id;
    await coord.dispose();
    const accept = await playwrightRequest.newContext({ baseURL });
    await accept.post(`/api/v1/school/invites/${student.development_invite_token}/accept`, { data: { password: E2E_PASSWORD } });
    await accept.dispose();
  });

  test("coordinator adds, completes and certifies an internship", async ({ page }) => {
    await signIn(page, email("coord"), E2E_PASSWORD, "/school/coordinator/dashboard");
    await page.goto(`/school/coordinator/students/${ctx.studentId}`);
    await page.getByRole("button", { name: "Add internship" }).click();
    await page.getByLabel("Role").fill("Design intern");
    await page.getByLabel("Company").fill("Acme Studio");
    await page.getByLabel("Start date (optional)").fill("2026-05-01");
    await page.getByLabel("End date (optional)").fill("2026-06-30");
    await page.getByLabel("Completion").selectOption("completed");
    await page.getByLabel("Attendance % (optional)").fill("92");
    await page.getByLabel("Skills acquired (optional)").fill("Figma, Research");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Acme Studio")).toBeVisible();
    await expect(page.locator(".internship-details").getByText("Completed")).toBeVisible();
    await page.getByLabel(/Upload certificate/).setInputFiles({ name: "cert.pdf", mimeType: "application/pdf", buffer: PDF });
    await expect(page.getByRole("status")).toHaveText("Certificate saved.");
    await expect(page.getByRole("link", { name: "Download certificate (PDF)" })).toBeVisible();
  });

  test("parent downloads the certificate", async ({ page }) => {
    await signIn(page, ctx.parentEmail, E2E_PASSWORD, "/school/parent/dashboard");
    await page.goto(`/school/parent/children/${ctx.studentId}`);
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Download certificate (PDF)" }).click()]);
    expect(download.suggestedFilename()).toBe("internship-certificate.pdf");
  });

  test("dashboard KPI counts the student", async () => {
    const coord = await apiAs(email("coord"), E2E_PASSWORD);
    const data = await (await coord.get("/api/v1/school/dashboard")).json();
    const kpi = data.school_crm_kpis.find((k: { key: string }) => k.key === "internships");
    expect(kpi).toMatchObject({ tracked: true, value: 1 });
    await coord.dispose();
  });

  for (const width of [320, 768]) {
    test(`student page has no page-level horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page, email("coord"), E2E_PASSWORD, "/school/coordinator/dashboard");
      await page.goto(`/school/coordinator/students/${ctx.studentId}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    });
  }
});
```

Before running, confirm the coordinator's student route (`/school/coordinator/students/[id]`) mounts
`PortfolioPanel` via `SchoolStudentDetailPanel`, and the "Add …" button text for the internship section
(`singular("internship")` in `PortfolioPanel.tsx`); align the selectors if they differ.

- [ ] **Step 3: Run** (the user's stack must be up; ask the user to confirm it is before running)

Run: `cd apps/web && npx playwright test tests/e2e/enh-026-counselling-record.spec.ts tests/e2e/enh-021-internship.spec.ts`
Expected: all passed. On failure, open only the failing test's trace/screenshot.

- [ ] **Step 4: Commit**

```bash
git add apps/web/tests/e2e/enh-026-counselling-record.spec.ts apps/web/tests/e2e/enh-021-internship.spec.ts
git commit -m "test(enh-021,enh-026): end-to-end counselling lifecycle and internship certificate"
```

---

### Task 15: Traceability docs, full regression, graph refresh — *not* completion

**Files:**
- Modify: `docs/quality/RTM.md` (rows for ENH-021/ENH-026: AC → test file::test), `docs/architecture/API_CONTRACT.md`
  (PATCH career record; certificate routes; additive fields), `docs/architecture/DATA_MODEL.md` (0042/0043 columns),
  `docs/delivery/ENHANCEMENT_BACKLOG.md` (ENH-021/ENH-026 status: "Implemented — pending browser validation and
  independent Codex review"), spec §5.1 list-length note (≤ 80 chars, reused ENH-025 rule).

- [ ] **Step 1: Full backend regression** — Run: `cd apps/api && pytest -q`
Expected: all pass except the recorded provider-credential baseline (compare with the RTM's last recorded baseline;
any new failure is investigated, not waved through).

- [ ] **Step 2: Web gates** — Run: `cd apps/web && npx tsc --noEmit && npx vitest run && npx eslint . && npx next build`
Expected: exit 0 each.

- [ ] **Step 3: Full E2E** — Run: `cd apps/web && npx playwright test` (user's stack up).
Expected: new specs pass; any other failure traced to a recorded pre-existing cause or fixed.

- [ ] **Step 4: Update the four docs** with the real numbers from Steps 1–3 (no placeholders; paste counts).

- [ ] **Step 5: Refresh the knowledge graph** — run `/graphify` update (no confirmation needed per user preference).

- [ ] **Step 6: Commit**

```bash
git add docs/ graphify-out/
git commit -m "docs(enh-021,enh-026): traceability, contracts and regression evidence"
```

- [ ] **Step 7: Stop.** Report results and hand over for **browser validation** and **independent Codex review**.
Do not mark either feature COMPLETE (CLAUDE.md completion gate; user instruction 2026-09-28).
