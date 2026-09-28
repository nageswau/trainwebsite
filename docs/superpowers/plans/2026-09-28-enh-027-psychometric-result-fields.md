# ENH-027 Psychometric Result Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Psychometric Team record all 12 `School CRM.md §6` fields on a psychometric record, and show them as structured data in the 360° Psychometric tab and the parent's child page, without changing any existing behaviour.

**Architecture:** 10 nullable columns on `school_psychometric_records` via one additive migration (`0042`). One Pydantic boundary model (`PsychometricResultFields`) validates only the new keys inside the existing `payload: dict` routes, parsed and applied with ENH-025's existing generic helpers. One output helper spreads the fields into the six existing read shapes. Frontend: a shared `lib/psychometric.ts` (type, labels, limits, pure form helpers), a server-safe `PsychometricResultDetails.tsx` (display + per-assessment list) used by the 360° tab and the parent overview, and a client `PsychometricResultsForm.tsx` opened from the existing dashboard panel.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + PostgreSQL 16; Pydantic v2; pytest + pytest-asyncio + httpx; Next.js (App Router) + React + vitest + Testing Library; Playwright.

**Spec:** `docs/superpowers/specs/2026-09-28-enh-027-psychometric-result-fields-design.md` (read it with this plan).

## Global Constraints

- No new dependencies (backend or frontend).
- Additive only: every existing request key, response key, error message, status code, route, element id and notification unchanged. Routes keep `payload: dict`; unknown keys stay ignored.
- New columns, exactly: `test_date` Date; `strengths`, `interest_areas`, `personality_indicators`, `career_recommendations`, `recommended_streams` JSON list[str]; `counsellor_remarks` Text; `parent_discussion_on` Date; `parent_discussion_notes` Text; `follow_up_on` Date. All nullable; empty string / empty list stored as NULL.
- Limits: list ≤20 items × ≤80 chars (ENH-025 `_clean_list`); `counsellor_remarks` ≤4000; `parent_discussion_notes` ≤2000; dates `YYYY-MM-DD` only (blank string → null).
- Status rule unchanged: `completed` only when `report_url` is set; result fields never change `status` and never notify parents.
- Only `psychometric_team` writes; readers unchanged; `/school/psychometric-records` still never returns `report_url`.
- Errors: `{"detail": "<field> <reason>"}` via `validation_message`, never echoing the value. 403 checks run before result validation.
- Audit metadata and logs carry field **names** only, never values.
- Revision `0042_psychometric_result_fields`, `down_revision = "0041_student_master_fields"`; Decision ID `DEC-SCOPE-031` (renumber either on merge if taken).
- Tests run against the local Postgres the user starts (`docker compose` is the user's — never start/stop it). Apply migrations with `cd apps/api && alembic upgrade head` before backend tests.
- pytest `asyncio_mode = "strict"`: every `async def test_…` has `@pytest.mark.asyncio`; async fixtures use `@pytest_asyncio.fixture`. Test helpers import as `from enh005_helpers import …`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full backend + E2E regression once, at the end (Task 12), per the user's cadence; per task run only the listed suites.

## Review Focus

1. A team member opens "Edit results", changes one strength and saves → every other field must survive (form sends changed keys only). Test: Task 7 `sends only the changed fields, emptied ones as null`.
2. A counsellor pastes a remark with Windows line endings and blank lines → it is saved, not rejected, and unchanged fields are not re-sent. Test: Task 5 `lib` test `changedFields ignores CRLF and blank-line differences`.
3. The partnership expires while the editor is open → save shows the 403 alert, card stays open, nothing typed is lost. Test: Task 7 `keeps the card open with the input on a failed save`.
4. A legacy record (created before 0042) is opened in the 360° tab and the parent page → "no results recorded yet", no crash. Tests: Task 4 `legacy record serializes nulls`, Task 6 `renders the empty line`.
5. A value typed as a single line with commas ("Logic, Maths") → stored as one item, shown as typed (one item per line is the only split rule). Test: Task 5 `splitLines keeps commas inside an item`.

---

## File Structure

| File | Responsibility |
|---|---|
| `docs/decisions/PRODUCT_DECISION_REGISTER.md` (modify) | `DEC-SCOPE-031` — the 7 in-session answers |
| `apps/api/app/models.py` (modify, `SchoolPsychometricRecord` ~1269) | 10 new columns |
| `apps/api/alembic/versions/0042_psychometric_result_fields.py` (create) | additive, guarded migration |
| `apps/api/tests/test_enh_025_migration.py` (modify, 1 test) | drop its "single head" assertion (moves to ENH-027's test) |
| `apps/api/tests/test_enh_027_migration.py` (create) | revision chain, single head, columns nullable |
| `apps/api/app/schemas.py` (modify, after `validation_message` ~735) | `PSYCHOMETRIC_*_KEYS`, `PsychometricResultFields` |
| `apps/api/tests/test_enh_027_schemas.py` (create) | model unit tests |
| `apps/api/app/api/schools.py` (modify) | `_psychometric_subset`, `_psychometric_result_out`, create/patch/list/readable routes, overview assessments |
| `apps/api/app/api/portfolio.py` (modify, line 128) | spread result fields into `psychometric_report` |
| `apps/api/tests/test_enh_027_psychometric_results.py` (create) | API tests AC01–AC06, AC10 |
| `apps/api/app/seed.py` (modify ~741) | demo values on Aarav's completed record |
| `apps/web/lib/psychometric.ts` (create) | type, labels, limits, `hasResults`, `toDraft`, `splitLines`, `changedFields`, `listError` |
| `apps/web/components/PsychometricResultDetails.tsx` (create) | display one result; `PsychometricResultsList` |
| `apps/web/app/globals.css` (modify, after `.s360-list` rules ~70) | `.psy-result*` rules |
| `apps/web/components/Student360Panels.tsx` (modify line 109-110) | render the list under the table |
| `apps/web/components/SchoolChildOverview.tsx` (modify 15, 154-167) | type + render the list |
| `apps/web/components/PsychometricResultsForm.tsx` (create) | the editor card |
| `apps/web/components/SchoolPsychometricRecordsPanel.tsx` (modify) | results button, one-card state, focus return |
| `apps/web/app/school/psychometric-team/dashboard/page.tsx` (modify line 10) | type |
| `apps/web/lib/portfolio.ts` (modify line 18) | type |
| `apps/web/tests/lib/psychometric.test.ts`, `tests/components/PsychometricResultDetails.test.tsx`, `tests/components/PsychometricResultsForm.test.tsx` (create); `SchoolPsychometricRecordsPanel.test.tsx`, `Student360Panels.test.tsx` (extend); `SchoolChildOverview.psychometric.test.tsx` (create) | web unit tests |
| `apps/web/tests/e2e/enh-027-psychometric-results.spec.ts` (create) | browser flow |
| `docs/architecture/DATA_MODEL.md`, `API_CONTRACT.md`, `SECURITY_CONTROLS.md`, `docs/features/FEATURE_ACCEPTANCE_CRITERIA.md`, `docs/quality/RTM.md`, `docs/delivery/ENHANCEMENT_BACKLOG.md` (modify) | traceability |

---

### Task 1: Decision record and audit-metadata check

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append after the `DEC-SCOPE-030` entry, same format)

**Interfaces:** Produces decision ID `DEC-SCOPE-031`, cited by every later doc change.

- [ ] **Step 1: Confirm the ID is free and read the entry format**

Run: `grep -n "DEC-SCOPE-03[0-9]" docs/decisions/PRODUCT_DECISION_REGISTER.md`
Expected: only `DEC-SCOPE-030` lines. If `031` exists, use the next free number everywhere in this plan.
Run: `sed -n '/^DEC-SCOPE-029 — Student Master field coverage/,/^DEC-SCOPE-030/p' docs/decisions/PRODUCT_DECISION_REGISTER.md | head -60` and copy its heading/field layout.

- [ ] **Step 2: Confirm no code reads the psychometric update audit metadata**

Run: `grep -rn "psychometric_record_update" apps/ --include=*.py --include=*.ts --include=*.tsx`
Expected: only the writer in `apps/api/app/api/schools.py`. If any reader exists, stop and report it (spec §10 assumes none).

- [ ] **Step 3: Append `DEC-SCOPE-031`**

Write the entry in the copied layout with: title "Psychometric record: structured result fields (`ENH-027`)"; status `CONFIRMED_CURRENT`; classification `EXPLICIT_APPROVAL` (user, in-session, 2026-09-27/28); evidence `EVID-014` `School CRM.md §6` lines 254-300; the decisions table from spec §9 (Q1–Q7) verbatim; consequences: 10 columns listed in Global Constraints, `ENH-026` must reuse the `list[str]` career-recommendations shape, `ENH-019` may later read `follow_up_on`; Client Question #20 stays open and unchanged; spec + plan paths.

- [ ] **Step 4: Commit**

```bash
git add docs/decisions/PRODUCT_DECISION_REGISTER.md
git commit -m "docs(enh-027): record DEC-SCOPE-031 psychometric result fields decisions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Model columns and migration 0042

**Files:**
- Modify: `apps/api/app/models.py` — `SchoolPsychometricRecord` (after `status`)
- Create: `apps/api/alembic/versions/0042_psychometric_result_fields.py`
- Modify: `apps/api/tests/test_enh_025_migration.py` — `test_migration_follows_enh018_and_is_the_single_head`
- Test: `apps/api/tests/test_enh_027_migration.py`

**Interfaces:**
- Produces: `SchoolPsychometricRecord.test_date|parent_discussion_on|follow_up_on: date | None`, `.strengths|interest_areas|personality_indicators|career_recommendations|recommended_streams: list | None`, `.counsellor_remarks|parent_discussion_notes: str | None`; migration constant `COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...]`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/test_enh_027_migration.py`:

```python
"""ENH-027 -- migration 0042 and the new SchoolPsychometricRecord columns (spec §3, AC09)."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_enh_027_migration_0042", VERSIONS / "0042_psychometric_result_fields.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

NEW_COLUMNS = (
    "test_date", "strengths", "interest_areas", "personality_indicators", "career_recommendations",
    "recommended_streams", "counsellor_remarks", "parent_discussion_on", "parent_discussion_notes", "follow_up_on",
)


def test_migration_follows_enh025_and_is_the_single_head():
    assert _migration.revision == "0042_psychometric_result_fields"
    assert _migration.down_revision == "0041_student_master_fields"
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        parent = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
        if rev:
            parents[rev] = parent
    assert set(parents) - set(parents.values()) == {"0042_psychometric_result_fields"}


def test_migration_adds_exactly_the_ten_columns():
    assert tuple(name for name, _ in _migration.COLUMNS) == NEW_COLUMNS


@pytest.mark.asyncio
async def test_new_columns_exist_and_are_nullable(db_session):
    def _cols(sync_conn):
        return {c["name"]: c for c in inspect(sync_conn).get_columns("school_psychometric_records")}

    conn = await db_session.connection()
    cols = await conn.run_sync(_cols)
    for name in NEW_COLUMNS:
        assert name in cols and cols[name]["nullable"], name
```

In `apps/api/tests/test_enh_025_migration.py`, the single-head assertion belongs to whichever migration is newest; keep ENH-025's own chain check and move the head check to ENH-027. Replace the test with:

```python
def test_migration_follows_enh018():
    # Re-chained on merge: ENH-013 (0039_student_career_goal) and then ENH-018 (0040_school_activity_feedback) merged to
    # main first (DEC-SCOPE-029 item 11). The "single head" check lives with the newest migration's test
    # (test_enh_027_migration.py since 0042).
    assert _migration.revision == "0041_student_master_fields"
    assert _migration.down_revision == "0040_school_activity_feedback"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_027_migration.py -v`
Expected: collection error — `FileNotFoundError` for `0042_psychometric_result_fields.py`.

- [ ] **Step 3: Add the model columns**

In `apps/api/app/models.py`, `SchoolPsychometricRecord`, after `status`:

```python
    # ENH-027 (DEC-SCOPE-031): School CRM.md §6's structured result. All optional; `status` still flips only on
    # `report_url`. Lists are JSON arrays of short strings (ENH-025's `_clean_list` rule); empty is stored as NULL.
    test_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    strengths: Mapped[list | None] = mapped_column(JSON, nullable=True)
    interest_areas: Mapped[list | None] = mapped_column(JSON, nullable=True)
    personality_indicators: Mapped[list | None] = mapped_column(JSON, nullable=True)
    career_recommendations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    recommended_streams: Mapped[list | None] = mapped_column(JSON, nullable=True)
    counsellor_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_discussion_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    parent_discussion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_on: Mapped[date | None] = mapped_column(Date, nullable=True)
```

(`date`, `Date`, `JSON`, `Text` are already imported in `models.py` — `tier_valid_until` and `subjects` use them.)

- [ ] **Step 4: Write the migration**

`apps/api/alembic/versions/0042_psychometric_result_fields.py`:

```python
"""ENH-027 -- structured result fields on school_psychometric_records.

Revision ID: 0042_psychometric_result_fields
Revises: 0041_student_master_fields

docs/superpowers/specs/2026-09-28-enh-027-psychometric-result-fields-design.md §3 (DEC-SCOPE-031). Additive only:
ten nullable columns, no backfill, no constraint, no rewrite of existing rows -- every existing value is kept.
`downgrade()` drops exactly these ten columns. If another branch reaches `main` first with its own 0042, the
later-merging branch re-chains (precedent: 0041's note).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0042_psychometric_result_fields"
down_revision = "0041_student_master_fields"
branch_labels = None
depends_on = None

TABLE = "school_psychometric_records"
COLUMNS = (
    ("test_date", sa.Date()),
    ("strengths", postgresql.JSON()),
    ("interest_areas", postgresql.JSON()),
    ("personality_indicators", postgresql.JSON()),
    ("career_recommendations", postgresql.JSON()),
    ("recommended_streams", postgresql.JSON()),
    ("counsellor_remarks", sa.Text()),
    ("parent_discussion_on", sa.Date()),
    ("parent_discussion_notes", sa.Text()),
    ("follow_up_on", sa.Date()),
)


def upgrade() -> None:
    # Guarded: on a fresh database 0001_initial's Base.metadata.create_all() has already built this table from the
    # *current* models, columns included (same reason 0030/0041 guard).
    offline = op.get_context().as_sql
    existing = set() if offline else {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column(TABLE, name)
```

- [ ] **Step 5: Apply and run the tests**

Run: `cd apps/api && alembic upgrade head && pytest tests/test_enh_027_migration.py tests/test_enh_025_migration.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/models.py apps/api/alembic/versions/0042_psychometric_result_fields.py apps/api/tests/test_enh_027_migration.py apps/api/tests/test_enh_025_migration.py
git commit -m "feat(enh-027): add psychometric result columns (migration 0042)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `PsychometricResultFields` validation model

**Files:**
- Modify: `apps/api/app/schemas.py` — insert after `validation_message` (~line 735)
- Test: `apps/api/tests/test_enh_027_schemas.py`

**Interfaces:**
- Consumes: `_clean_list`, `_clean_multiline_text`, `validation_message` (existing, `schemas.py`).
- Produces: `PSYCHOMETRIC_LIST_KEYS: tuple[str, ...]`, `PSYCHOMETRIC_DATE_KEYS: tuple[str, ...]`, `PSYCHOMETRIC_RESULT_KEYS: tuple[str, ...]` (the 10 keys, in column order), `class PsychometricResultFields(BaseModel)`, `COUNSELLOR_REMARKS_MAX = 4000`, `PARENT_DISCUSSION_NOTES_MAX = 2000`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-027 -- PsychometricResultFields (spec §4.1)."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import PSYCHOMETRIC_RESULT_KEYS, PsychometricResultFields, validation_message


def _error(data: dict) -> str:
    with pytest.raises(ValidationError) as exc:
        PsychometricResultFields.model_validate(data)
    return validation_message(exc.value)


def test_keys_are_the_ten_columns_in_order():
    assert PSYCHOMETRIC_RESULT_KEYS == (
        "test_date", "strengths", "interest_areas", "personality_indicators", "career_recommendations",
        "recommended_streams", "counsellor_remarks", "parent_discussion_on", "parent_discussion_notes", "follow_up_on",
    )


def test_valid_full_input_is_normalised():
    fields = PsychometricResultFields.model_validate({
        "test_date": "2026-09-10", "strengths": ["  Logic ", "logic", "", "Verbal"], "counsellor_remarks": "  Line 1\nLine 2  ",
        "parent_discussion_on": "", "follow_up_on": None,
    })
    assert fields.test_date == date(2026, 9, 10)
    assert fields.strengths == ["Logic", "Verbal"]  # trimmed, case-insensitive de-dup, blanks dropped
    assert fields.counsellor_remarks == "Line 1\nLine 2"
    assert fields.parent_discussion_on is None  # blank string -> None
    assert fields.model_fields_set == {"test_date", "strengths", "counsellor_remarks", "parent_discussion_on", "follow_up_on"}


def test_empty_list_and_blank_text_become_none():
    fields = PsychometricResultFields.model_validate({"interest_areas": [" ", ""], "parent_discussion_notes": "   "})
    assert fields.interest_areas is None and fields.parent_discussion_notes is None


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"strengths": "Logic"}, "strengths"),
        ({"strengths": [f"s{i}" for i in range(21)]}, "strengths"),
        ({"interest_areas": ["x" * 81]}, "interest_areas"),
        ({"personality_indicators": ["ok", "bad\x00"]}, "personality_indicators"),
        ({"recommended_streams": ["a‮b"]}, "recommended_streams"),
        ({"counsellor_remarks": "x" * 4001}, "counsellor_remarks"),
        ({"parent_discussion_notes": "x" * 2001}, "parent_discussion_notes"),
        ({"counsellor_remarks": "a‮b"}, "counsellor_remarks"),
        ({"counsellor_remarks": 42}, "counsellor_remarks"),
        ({"test_date": "2026-02-30"}, "test_date"),
        ({"test_date": "10/09/2026"}, "test_date"),
        ({"test_date": "2026-09-10T00:00:00"}, "test_date"),
        ({"test_date": "20260910"}, "test_date"),
        ({"follow_up_on": 1700000000}, "follow_up_on"),
        ({"parent_discussion_on": "2026-W37-1"}, "parent_discussion_on"),
    ],
)
def test_invalid_values_name_the_field_and_never_echo_the_value(data, field):
    message = _error(data)
    assert message.startswith(f"{field} "), message
    assert "x" * 81 not in message and "Logic" not in message


def test_multiline_remarks_keep_line_breaks_but_list_items_do_not():
    assert PsychometricResultFields.model_validate({"counsellor_remarks": "a\n\tb"}).counsellor_remarks == "a\n\tb"
    assert _error({"strengths": ["a\nb"]}).startswith("strengths ")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_027_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'PSYCHOMETRIC_RESULT_KEYS'`.

- [ ] **Step 3: Implement**

In `apps/api/app/schemas.py`, after `validation_message`:

```python
# --- ENH-027: psychometric record result fields (docs/superpowers/specs/2026-09-28-enh-027-psychometric-result-fields-design.md §4.1) ---

PSYCHOMETRIC_LIST_KEYS: tuple[str, ...] = ("strengths", "interest_areas", "personality_indicators", "career_recommendations", "recommended_streams")
PSYCHOMETRIC_DATE_KEYS: tuple[str, ...] = ("test_date", "parent_discussion_on", "follow_up_on")
PSYCHOMETRIC_RESULT_KEYS: tuple[str, ...] = (
    "test_date", *PSYCHOMETRIC_LIST_KEYS, "counsellor_remarks", "parent_discussion_on", "parent_discussion_notes", "follow_up_on",
)
COUNSELLOR_REMARKS_MAX = 4000
PARENT_DISCUSSION_NOTES_MAX = 2000
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _iso_date_or_none(value) -> date | None:
    """Only None, "" (an emptied <input type="date">) or exactly YYYY-MM-DD. Pydantic's lax date parsing would also accept
    a Unix timestamp or a datetime string; `strict` would reject the ISO string itself when validating a dict."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, str) and _ISO_DATE.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("must be a date in YYYY-MM-DD format")


class PsychometricResultFields(BaseModel):
    """The ten ENH-027 fields, validated at the API boundary. Fed only the keys the client sent (so PATCH gets
    absent = unchanged / null = clear through `model_fields_set`); every other request key keeps its existing handling."""

    test_date: date | None = None
    strengths: list[str] | None = None
    interest_areas: list[str] | None = None
    personality_indicators: list[str] | None = None
    career_recommendations: list[str] | None = None  # ENH-026 reuses this shape (DEC-SCOPE-031 Q3)
    recommended_streams: list[str] | None = None
    counsellor_remarks: str | None = Field(default=None, max_length=COUNSELLOR_REMARKS_MAX)
    parent_discussion_on: date | None = None
    parent_discussion_notes: str | None = Field(default=None, max_length=PARENT_DISCUSSION_NOTES_MAX)
    follow_up_on: date | None = None

    @field_validator(*PSYCHOMETRIC_LIST_KEYS, mode="before")
    @classmethod
    def _lists(cls, value):
        return _clean_list(value)

    @field_validator(*PSYCHOMETRIC_DATE_KEYS, mode="before")
    @classmethod
    def _dates(cls, value):
        return _iso_date_or_none(value)

    @field_validator("counsellor_remarks", "parent_discussion_notes", mode="before")
    @classmethod
    def _text(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError("must be text")
        return _clean_multiline_text(value)
```

(`re`, `date`, `Field`, `field_validator`, `BaseModel` are already imported at the top of `schemas.py`.)

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/api && pytest tests/test_enh_027_schemas.py -v`
Expected: all PASS. If the `"x" * 4001` case's message reads `counsellor_remarks string should have at most 4000 characters`, that is the expected `validation_message` shape.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas.py apps/api/tests/test_enh_027_schemas.py
git commit -m "feat(enh-027): validate psychometric result fields at the API boundary

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Write and read paths

**Files:**
- Modify: `apps/api/app/api/schools.py` — import line 64; helpers next to `_master_subset` (~619); `create_psychometric_record` (~1945); `update_psychometric_record` (~1973); `list_psychometric_team_records` (~1998); `list_readable_psychometric_records` (~2010); `_overview_payload` psychometric assessments (~1208)
- Modify: `apps/api/app/api/portfolio.py:17,128`
- Test: `apps/api/tests/test_enh_027_psychometric_results.py`

**Interfaces:**
- Consumes: `PsychometricResultFields`, `PSYCHOMETRIC_RESULT_KEYS` (Task 3); existing `_master_fields_or_422(model, data)`, `_apply_master_fields(obj, fields) -> list[str]`.
- Produces: `_psychometric_subset(payload: dict) -> dict`, `_psychometric_result_out(record: SchoolPsychometricRecord) -> dict` (in `schools.py`, imported by `portfolio.py`). Every psychometric read shape gains the 10 keys.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/test_enh_027_psychometric_results.py`:

```python
"""ENH-027 -- structured psychometric result fields through the API (spec §7: AC01-AC06, AC10)."""

from datetime import date, timedelta
from uuid import UUID

import pytest
from enh005_helpers import login, mk_school, mk_staff
from sqlalchemy import func, select

from app.models import AuditLog, Notification, SchoolPsychometricRecord

RECORDS = "/api/v1/school/psychometric-team/records"
FULL = {
    "test_date": "2026-09-10",
    "strengths": ["Logical reasoning", "Verbal ability"],
    "interest_areas": ["Engineering", "Design"],
    "personality_indicators": ["Analytical", "Reflective"],
    "career_recommendations": ["Software engineer", "Product designer"],
    "recommended_streams": ["Science (PCM)"],
    "counsellor_remarks": "Strong analytical profile.\nDiscuss design electives.",
    "parent_discussion_on": "2026-09-15",
    "parent_discussion_notes": "Parents agreed to explore design camps.",
    "follow_up_on": "2026-10-15",
}
KEYS = tuple(FULL)


async def _world(db, students: int = 1) -> dict:
    w = await mk_school(db, label="E27", students=students)
    w["psych"] = await mk_staff(db, w["school"], w["admin"], role="psychometric_team")
    w["student"] = w["students"][0]
    return w


async def _create(client, w, **extra) -> dict:
    r = await client.post(RECORDS, json={"school_student_id": str(w["student"].id), "assessment_type": "Aptitude Test", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _results(row: dict) -> dict:
    return {k: row[k] for k in KEYS}


async def _count(db, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where))


async def _team_row(client, record_id: str) -> dict:
    return next(r for r in (await client.get(RECORDS)).json() if r["id"] == record_id)


# --- AC01 ---
@pytest.mark.asyncio
async def test_create_with_all_twelve_fields_round_trips(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    body = await _create(client, w, report_url="/r.pdf", **FULL)
    assert (body["assessment_type"], body["report_url"], body["status"]) == ("Aptitude Test", "/r.pdf", "completed")
    assert _results(body) == FULL
    assert _results(await _team_row(client, body["id"])) == FULL


# --- AC02 ---
@pytest.mark.asyncio
async def test_patch_changes_only_sent_keys_and_null_clears(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w, **FULL)
    r = await client.patch(f"{RECORDS}/{created['id']}", json={"strengths": ["Numerical"], "follow_up_on": None})
    assert r.status_code == 200, r.text
    assert _results(r.json()) == {**FULL, "strengths": ["Numerical"], "follow_up_on": None}


@pytest.mark.asyncio
async def test_result_only_patch_keeps_status_and_sends_no_notification(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w)
    parent_notes = await _count(db_session, Notification, Notification.user_id == w["parent"].id)
    r = await client.patch(f"{RECORDS}/{created['id']}", json=FULL)
    assert (r.status_code, r.json()["status"]) == (200, "assigned")
    assert await _count(db_session, Notification, Notification.user_id == w["parent"].id) == parent_notes
    r = await client.patch(f"{RECORDS}/{created['id']}", json={"report_url": "/r.pdf"})
    assert r.json()["status"] == "completed"
    assert _results(r.json()) == FULL
    assert await _count(db_session, Notification, Notification.user_id == w["parent"].id) == parent_notes + 1


# --- AC03 ---
@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"strengths": "Logic"}, "strengths"),
        ({"strengths": [f"s{i}" for i in range(21)]}, "strengths"),
        ({"interest_areas": ["x" * 81]}, "interest_areas"),
        ({"personality_indicators": ["ok", "bad\x00"]}, "personality_indicators"),
        ({"counsellor_remarks": "x" * 4001}, "counsellor_remarks"),
        ({"parent_discussion_notes": "x" * 2001}, "parent_discussion_notes"),
        ({"counsellor_remarks": "a‮b"}, "counsellor_remarks"),
        ({"counsellor_remarks": 42}, "counsellor_remarks"),
        ({"test_date": "2026-02-30"}, "test_date"),
        ({"follow_up_on": 1700000000}, "follow_up_on"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_result_patch_is_422_and_changes_nothing(client, db_session, patch, field):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w, **FULL)
    audits = await _count(db_session, AuditLog, AuditLog.entity_id == created["id"])
    r = await client.patch(f"{RECORDS}/{created['id']}", json={"report_url": "/r.pdf", **patch})
    assert r.status_code == 422, r.text
    assert r.json()["detail"].startswith(f"{field} ")
    row = await _team_row(client, created["id"])
    assert _results(row) == FULL and (row["report_url"], row["status"]) == (None, "assigned")  # report_url not half-applied
    assert await _count(db_session, AuditLog, AuditLog.entity_id == created["id"]) == audits


@pytest.mark.asyncio
async def test_invalid_result_on_create_creates_nothing(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    r = await client.post(RECORDS, json={"school_student_id": str(w["student"].id), "assessment_type": "Aptitude Test", "strengths": "Logic"})
    assert (r.status_code, r.json()["detail"].startswith("strengths ")) == (422, True)
    assert await _count(db_session, SchoolPsychometricRecord, SchoolPsychometricRecord.school_student_id == w["student"].id) == 0


@pytest.mark.asyncio
async def test_existing_create_messages_are_unchanged(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    r = await client.post(RECORDS, json={"school_student_id": str(w["student"].id), "strengths": "Logic"})
    assert (r.status_code, r.json()["detail"]) == (422, "assessment_type is required")


# --- AC04 ---
@pytest.mark.asyncio
async def test_other_roles_cannot_write_results(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w)
    counselor = await mk_staff(db_session, w["school"], w["admin"], role="career_counselor")
    for user in (w["coordinator"], w["principal"], w["teacher"], w["parent"], counselor):
        await login(client, user.email)
        assert (await client.patch(f"{RECORDS}/{created['id']}", json={"strengths": ["x"]})).status_code == 403, user.role
        r = await client.post(RECORDS, json={"school_student_id": str(w["student"].id), "assessment_type": "X", **FULL})
        assert r.status_code == 403, user.role


@pytest.mark.asyncio
async def test_out_of_portfolio_member_gets_403_before_validation(client, db_session):
    w = await _world(db_session)
    other = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w)
    await login(client, other["psych"].email)
    for body in ({"strengths": ["x"]}, {"strengths": "not a list"}):
        assert (await client.patch(f"{RECORDS}/{created['id']}", json=body)).status_code == 403
    r = await client.post(RECORDS, json={"school_student_id": str(w["student"].id), "assessment_type": "X", "strengths": "not a list"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_expired_partnership_blocks_a_result_patch_and_changes_nothing(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w)
    w["school"].tier_valid_until = date.today() - timedelta(days=2)
    await db_session.commit()
    r = await client.patch(f"{RECORDS}/{created['id']}", json=FULL)
    assert r.status_code == 403
    record = await db_session.get(SchoolPsychometricRecord, UUID(created["id"]))
    await db_session.refresh(record)
    assert record.strengths is None and record.test_date is None


# --- AC05 ---
@pytest.mark.asyncio
async def test_readers_see_result_fields_in_every_read_path(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w, report_url="/r.pdf", **FULL)
    sid = w["student"].id

    await login(client, w["coordinator"].email)
    row = next(r for r in (await client.get("/api/v1/school/psychometric-records")).json() if r["id"] == created["id"])
    assert _results(row) == FULL
    assert "report_url" not in row  # Client Question #20: unchanged

    await login(client, w["parent"].email)
    overview = (await client.get(f"/api/v1/school/students/{sid}/overview")).json()
    assert _results(overview["psychometric"]["assessments"][0]) == FULL

    await login(client, w["teacher"].email)
    portfolio = (await client.get(f"/api/v1/school/students/{sid}/portfolio")).json()
    assert _results(portfolio["psychometric_report"][0]) == FULL

    await login(client, w["principal"].email)
    view = (await client.get(f"/api/v1/school/students/{sid}/360-view")).json()
    assert _results(view["tabs"]["psychometric_assessment"]["data"]["assessments"][0]) == FULL


# --- AC06 ---
@pytest.mark.asyncio
async def test_legacy_record_serializes_nulls_everywhere(client, db_session):
    w = await _world(db_session)
    legacy = SchoolPsychometricRecord(school_student_id=w["student"].id, psychometric_team_user_id=w["psych"].id, assessment_type="Legacy Test", status="assigned")
    db_session.add(legacy)
    await db_session.commit()
    nulls = dict.fromkeys(KEYS)

    await login(client, w["psych"].email)
    assert _results(await _team_row(client, str(legacy.id))) == nulls
    await login(client, w["coordinator"].email)
    row = next(r for r in (await client.get("/api/v1/school/psychometric-records")).json() if r["id"] == str(legacy.id))
    assert _results(row) == nulls
    await login(client, w["principal"].email)
    view = (await client.get(f"/api/v1/school/students/{w['student'].id}/360-view")).json()
    assert _results(view["tabs"]["psychometric_assessment"]["data"]["assessments"][0]) == nulls


# --- AC10 ---
@pytest.mark.asyncio
async def test_patch_ignores_ownership_student_and_status_keys(client, db_session):
    w = await _world(db_session, students=2)
    await login(client, w["psych"].email)
    created = await _create(client, w)
    r = await client.patch(f"{RECORDS}/{created['id']}", json={
        "school_student_id": str(w["students"][1].id), "psychometric_team_user_id": str(w["coordinator"].id),
        "status": "completed", "assessment_type": "Changed", "strengths": ["Kept"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["school_student_id"], body["status"], body["assessment_type"], body["strengths"]) == (str(w["student"].id), "assigned", "Aptitude Test", ["Kept"])
    record = await db_session.get(SchoolPsychometricRecord, UUID(created["id"]))
    await db_session.refresh(record)
    assert record.psychometric_team_user_id == w["psych"].id


@pytest.mark.asyncio
async def test_audit_metadata_names_fields_never_values(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w, **FULL)
    await client.patch(f"{RECORDS}/{created['id']}", json={"strengths": ["Secret strength"], "report_url": "/r.pdf"})
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == created["id"]).order_by(AuditLog.created_at))).all()
    create_row, update_row = rows[0], rows[-1]
    assert create_row.metadata_json == {"assessment_type": "Aptitude Test", "fields": sorted(KEYS)}
    assert update_row.metadata_json == {"fields": ["report_url", "strengths"]}
    assert "Secret strength" not in str([r.metadata_json for r in rows])


@pytest.mark.asyncio
async def test_blank_date_clears_and_markup_is_stored_as_plain_text(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w, test_date="2026-09-10")
    r = await client.patch(f"{RECORDS}/{created['id']}", json={"test_date": "", "counsellor_remarks": "<script>alert(1)</script>"})
    assert (r.json()["test_date"], r.json()["counsellor_remarks"]) == (None, "<script>alert(1)</script>")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && pytest tests/test_enh_027_psychometric_results.py -v`
Expected: FAIL — `KeyError: 'test_date'` in `_results` (responses lack the new keys); `test_existing_create_messages_are_unchanged`, `test_other_roles_cannot_write_results`, `test_out_of_portfolio_member_gets_403_before_validation`, `test_expired_partnership…`, `test_invalid_result_on_create_creates_nothing` may already pass or fail on the missing validation — note which.

- [ ] **Step 3: Implement the helpers**

`schools.py` line 64 import — add `PSYCHOMETRIC_RESULT_KEYS, PsychometricResultFields` to the existing `from app.schemas import …` line (keep it sorted as today).

Next to `_master_subset` (~line 619):

```python
def _psychometric_subset(payload: dict) -> dict:
    """ENH-027: only the ten result keys; `report_url`/`assessment_type`/`school_student_id` keep their existing handling
    and every other key stays ignored (no mass assignment, spec §4.2)."""
    return {key: payload[key] for key in PSYCHOMETRIC_RESULT_KEYS if key in payload}


def _psychometric_result_out(record: SchoolPsychometricRecord) -> dict:
    """ENH-027: the ten result fields for every psychometric read shape (null = not recorded)."""
    return {key: getattr(record, key) for key in PSYCHOMETRIC_RESULT_KEYS}
```

- [ ] **Step 4: Change `create_psychometric_record`**

After the existing `if not assessment_type: raise HTTPException(422, "assessment_type is required")` and **before** `record = SchoolPsychometricRecord(`:

```python
    result = _master_fields_or_422(PsychometricResultFields, _psychometric_subset(payload))
```

After the `record = SchoolPsychometricRecord(...)` statement:

```python
    fields = _apply_master_fields(record, result)
```

Change the audit line's metadata to `metadata_json={"assessment_type": assessment_type, "fields": fields}`. After `await db.commit()` and before `return`:

```python
    if fields:
        logger.info("psychometric_results_saved", extra={"extra_fields": {"action": "create", "record_id": str(record.id), "actor_id": str(user.id), "fields": fields}})
```

Change the return to `return {"id": record.id, "school_student_id": record.school_student_id, "assessment_type": record.assessment_type, "report_url": record.report_url, "status": record.status, "created_at": record.created_at, **_psychometric_result_out(record)}`.

- [ ] **Step 5: Change `update_psychometric_record`**

After the existing `await require_school_entitlement(...)` line and **before** `became_completed = False`:

```python
    result = _master_fields_or_422(PsychometricResultFields, _psychometric_subset(payload))
    fields = _apply_master_fields(record, result)
```

Change the audit line's metadata to `metadata_json={"fields": sorted({*fields, *(["report_url"] if "report_url" in payload else [])})}`. After `await db.commit()`:

```python
    if fields:
        logger.info("psychometric_results_saved", extra={"extra_fields": {"action": "update", "record_id": str(record.id), "actor_id": str(user.id), "fields": fields}})
```

Change the return to `return {"id": record.id, "school_student_id": record.school_student_id, "assessment_type": record.assessment_type, "report_url": record.report_url, "status": record.status, **_psychometric_result_out(record)}`.

(Transactions: validation happens before any mutation; the record change, audit row and any notification commit together in the route's single existing `db.commit()`; an exception before it leaves nothing written. `_apply_master_fields` assigns the validated list object, so SQLAlchemy marks only changed columns dirty — spec §4.3.)

- [ ] **Step 6: Change the four read shapes**

- `list_psychometric_team_records` return dict: append `**_psychometric_result_out(r)`.
- `list_readable_psychometric_records` return dict: append `**_psychometric_result_out(r)` (still no `report_url`).
- `_overview_payload` (~1208): `"assessments": [{"id": r.id, "assessment_type": r.assessment_type, "status": r.status, "created_at": r.created_at, **_psychometric_result_out(r)} for r in psych_rows]`.
- `portfolio.py:17`: `from app.api.schools import _load_student_for_reader, _psychometric_result_out, require_school_entitlement`; line 128: `"psychometric_report": [{"id": r.id, "assessment_type": r.assessment_type, "report_url": r.report_url, "created_at": r.created_at, **_psychometric_result_out(r)} for r in psychometric],`.

`student_360.py` is not changed: it spreads the portfolio rows (`{**a, "status": …}`).

- [ ] **Step 7: Run to verify pass**

Run: `cd apps/api && pytest tests/test_enh_027_psychometric_results.py -v`
Expected: all PASS.

- [ ] **Step 8: Regression for everything that reads or writes this table**

Run: `cd apps/api && pytest tests/test_sch_005_psychometric_assessment.py tests/test_sch_007_parent_portal.py tests/test_sch_008_student_timeline.py tests/test_sch_011_entitlements.py tests/test_sch_reports.py tests/test_enh_012_digital_portfolio.py tests/test_enh_013_360_view.py tests/test_enh_013_refactor.py tests/test_enh_013_career_goal.py tests/test_enh_022_tier_enforcement.py tests/test_enh_022_tier_rules.py tests/test_enh_023_tier_change.py tests/test_enh_005_approve.py -q`
Expected: all PASS, no existing test edited.

- [ ] **Step 9: Refactor check, then commit**

Re-read the diff: no duplicated dict literals beyond the existing per-route shapes, no value in any log/audit call. Rerun Step 7 + 8 if anything changed.

```bash
git add apps/api/app/api/schools.py apps/api/app/api/portfolio.py apps/api/tests/test_enh_027_psychometric_results.py
git commit -m "feat(enh-027): record and read structured psychometric results

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Seed demo values + shared web module `lib/psychometric.ts`

**Files:**
- Modify: `apps/api/app/seed.py` (~741, the `student_a` "Aptitude Test" record)
- Create: `apps/web/lib/psychometric.ts`
- Test: `apps/web/tests/lib/psychometric.test.ts`

**Interfaces:**
- Produces (TS): `type ResultKey`, `type ResultListKey`, `type PsychometricResult`, `type ResultDraft = Record<ResultKey, string>`, `RESULT_LIST_FIELDS: readonly {key: ResultListKey; label: string}[]`, `RESULT_KEYS: readonly ResultKey[]`, `LIST_MAX_ITEMS = 20`, `LIST_ITEM_MAX = 80`, `REMARKS_MAX = 4000`, `NOTES_MAX = 2000`, `hasResults(r: PsychometricResult): boolean`, `toDraft(r: PsychometricResult): ResultDraft`, `splitLines(text: string): string[]`, `changedFields(initial: ResultDraft, draft: ResultDraft): Partial<Record<ResultKey, string | string[] | null>>`, `listError(text: string): string | null`.

- [ ] **Step 1: Seed**

In `seed.py`, the `student_a` record gains (keep every existing argument):

```python
test_date=(journey_base - timedelta(days=9)).date(),
strengths=["Logical reasoning", "Numerical ability"], interest_areas=["Engineering", "Design"],
personality_indicators=["Analytical", "Reflective"], career_recommendations=["Software engineer", "Product designer"],
recommended_streams=["Science (PCM)"], counsellor_remarks="Strong analytical profile; explore design electives alongside PCM.",
parent_discussion_on=(journey_base - timedelta(days=5)).date(), parent_discussion_notes="Parents keen on engineering; agreed to a design summer camp.",
follow_up_on=(journey_base + timedelta(days=30)).date(),
```

The two `assigned` records stay as they are (legacy shape — they exercise the empty state).
Run: `cd apps/api && python -c "import app.seed"` — Expected: no error. (Do not run the seed against the user's DB unless they ask.)

- [ ] **Step 2: Write the failing lib tests**

`apps/web/tests/lib/psychometric.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { changedFields, hasResults, listError, RESULT_KEYS, splitLines, toDraft, type PsychometricResult } from "@/lib/psychometric";

const full: PsychometricResult = {
  test_date: "2026-09-10", strengths: ["Logic", "Verbal"], interest_areas: null, personality_indicators: null,
  career_recommendations: ["Engineer"], recommended_streams: null, counsellor_remarks: "Line 1\nLine 2",
  parent_discussion_on: null, parent_discussion_notes: null, follow_up_on: "2026-10-15",
};

describe("lib/psychometric", () => {
  it("lists the ten result keys in API order", () => {
    expect(RESULT_KEYS).toEqual(["test_date", "strengths", "interest_areas", "personality_indicators", "career_recommendations", "recommended_streams", "counsellor_remarks", "parent_discussion_on", "parent_discussion_notes", "follow_up_on"]);
  });

  it("hasResults is false for a legacy record and true once any field is set", () => {
    expect(hasResults({})).toBe(false);
    expect(hasResults(Object.fromEntries(RESULT_KEYS.map((k) => [k, null])))).toBe(false);
    expect(hasResults({ strengths: [] })).toBe(false);
    expect(hasResults({ follow_up_on: "2026-10-15" })).toBe(true);
  });

  it("toDraft joins lists one per line and turns nulls into empty strings", () => {
    const draft = toDraft(full);
    expect(draft.strengths).toBe("Logic\nVerbal");
    expect(draft.interest_areas).toBe("");
    expect(draft.counsellor_remarks).toBe("Line 1\nLine 2");
  });

  it("splitLines trims, drops blanks and keeps commas inside an item", () => {
    expect(splitLines("  Logic, Maths \r\n\r\n Verbal \n")).toEqual(["Logic, Maths", "Verbal"]);
  });

  it("changedFields sends only what changed; emptied fields become null", () => {
    const initial = toDraft(full);
    expect(changedFields(initial, initial)).toEqual({});
    expect(changedFields(initial, { ...initial, strengths: "Logic\nVerbal\nSpatial", follow_up_on: "" })).toEqual({ strengths: ["Logic", "Verbal", "Spatial"], follow_up_on: null });
    expect(changedFields(initial, { ...initial, interest_areas: "Design" })).toEqual({ interest_areas: ["Design"] });
  });

  it("changedFields ignores CRLF and blank-line differences", () => {
    const initial = toDraft(full);
    expect(changedFields(initial, { ...initial, strengths: "Logic\r\n\r\nVerbal  " })).toEqual({});
    expect(changedFields(initial, { ...initial, counsellor_remarks: "  Line 1\nLine 2 " })).toEqual({});
  });

  it("listError enforces 20 items of 80 characters", () => {
    expect(listError("a\nb")).toBeNull();
    expect(listError(Array.from({ length: 21 }, (_, i) => `s${i}`).join("\n"))).toBe("Up to 20 items.");
    expect(listError("x".repeat(81))).toBe("Each item must be 80 characters or fewer.");
  });
});
```

- [ ] **Step 3: Run to verify failure**

Run: `cd apps/web && npx vitest run tests/lib/psychometric.test.ts`
Expected: FAIL — `Failed to resolve import "@/lib/psychometric"`.

- [ ] **Step 4: Implement `apps/web/lib/psychometric.ts`**

```ts
// ENH-027 -- the ten structured psychometric result fields (docs/superpowers/specs/2026-09-28-enh-027-psychometric-result-fields-design.md §5).
// Shared by the server-rendered details and the client editor so neither imports the other. Limits mirror the API
// (app/schemas.py PsychometricResultFields); the API stays the authority.

export const RESULT_LIST_FIELDS = [
  { key: "strengths", label: "Strengths" },
  { key: "interest_areas", label: "Interest areas" },
  { key: "personality_indicators", label: "Personality indicators" },
  { key: "career_recommendations", label: "Career recommendations" },
  { key: "recommended_streams", label: "Recommended streams" },
] as const;

export type ResultListKey = (typeof RESULT_LIST_FIELDS)[number]["key"];
type ResultTextKey = "test_date" | "counsellor_remarks" | "parent_discussion_on" | "parent_discussion_notes" | "follow_up_on";
export type ResultKey = ResultListKey | ResultTextKey;
export type PsychometricResult = Partial<Record<ResultListKey, string[] | null> & Record<ResultTextKey, string | null>>;
export type ResultDraft = Record<ResultKey, string>;

export const RESULT_KEYS: readonly ResultKey[] = [
  "test_date", "strengths", "interest_areas", "personality_indicators", "career_recommendations", "recommended_streams",
  "counsellor_remarks", "parent_discussion_on", "parent_discussion_notes", "follow_up_on",
];
const LIST_KEYS: ReadonlySet<ResultKey> = new Set(RESULT_LIST_FIELDS.map((f) => f.key));

export const LIST_MAX_ITEMS = 20;
export const LIST_ITEM_MAX = 80;
export const REMARKS_MAX = 4000;
export const NOTES_MAX = 2000;

export function hasResults(r: PsychometricResult): boolean {
  return RESULT_KEYS.some((k) => {
    const v = r[k];
    return Array.isArray(v) ? v.length > 0 : v !== null && v !== undefined && v !== "";
  });
}

export function splitLines(text: string): string[] {
  return text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
}

export function toDraft(r: PsychometricResult): ResultDraft {
  return Object.fromEntries(RESULT_KEYS.map((k) => {
    const v = r[k];
    return [k, Array.isArray(v) ? v.join("\n") : (v ?? "")];
  })) as ResultDraft;
}

/** Only the fields the user changed (spec §4.3: last write wins per field, so unchanged fields are never re-sent). */
export function changedFields(initial: ResultDraft, draft: ResultDraft): Partial<Record<ResultKey, string | string[] | null>> {
  const out: Partial<Record<ResultKey, string | string[] | null>> = {};
  for (const k of RESULT_KEYS) {
    if (LIST_KEYS.has(k)) {
      const before = splitLines(initial[k]);
      const after = splitLines(draft[k]);
      if (JSON.stringify(before) !== JSON.stringify(after)) out[k] = after.length ? after : null;
    } else {
      const before = initial[k].trim();
      const after = draft[k].trim();
      if (before !== after) out[k] = after || null;
    }
  }
  return out;
}

export function listError(text: string): string | null {
  const items = splitLines(text);
  if (items.length > LIST_MAX_ITEMS) return `Up to ${LIST_MAX_ITEMS} items.`;
  if (items.some((i) => i.length > LIST_ITEM_MAX)) return `Each item must be ${LIST_ITEM_MAX} characters or fewer.`;
  return null;
}
```

- [ ] **Step 5: Run to verify pass**

Run: `cd apps/web && npx vitest run tests/lib/psychometric.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/seed.py apps/web/lib/psychometric.ts apps/web/tests/lib/psychometric.test.ts
git commit -m "feat(enh-027): seed demo results and add the shared psychometric web module

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Display — `PsychometricResultDetails`, 360° tab, parent overview

**Files:**
- Create: `apps/web/components/PsychometricResultDetails.tsx`
- Modify: `apps/web/app/globals.css` (append after the `.s360-list li p` rule, ~line 70)
- Modify: `apps/web/components/Student360Panels.tsx:109-110`
- Modify: `apps/web/components/SchoolChildOverview.tsx:15` (type) and `:154-167` (render)
- Modify: `apps/web/lib/portfolio.ts:18` (type)
- Test: `apps/web/tests/components/PsychometricResultDetails.test.tsx` (create), `apps/web/tests/components/Student360Panels.test.tsx` (extend), `apps/web/tests/components/SchoolChildOverview.psychometric.test.tsx` (create)

**Interfaces:**
- Consumes: `PsychometricResult`, `RESULT_LIST_FIELDS`, `hasResults` (Task 5); `formatCalendarDate` (`lib/formatDate.ts:41`).
- Produces: default export `PsychometricResultDetails({ result }: { result: PsychometricResult })`; named `PsychometricResultsList({ assessments }: { assessments: (PsychometricResult & { id: string; assessment_type: string })[] })`.

- [ ] **Step 1: Write the failing tests**

`apps/web/tests/components/PsychometricResultDetails.test.tsx`:

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import PsychometricResultDetails, { PsychometricResultsList } from "@/components/PsychometricResultDetails";

afterEach(cleanup);

const FULL = {
  test_date: "2026-09-10", strengths: ["Logical reasoning", "Verbal ability"], interest_areas: ["Design"], personality_indicators: null,
  career_recommendations: ["Software engineer"], recommended_streams: ["Science (PCM)"], counsellor_remarks: "Line one\nLine two",
  parent_discussion_on: "2026-09-15", parent_discussion_notes: "Agreed on a design camp.", follow_up_on: "2026-10-15",
};

describe("PsychometricResultDetails", () => {
  it("shows every recorded field with its label and omits empty ones", () => {
    render(<PsychometricResultDetails result={FULL} />);
    const term = (name: string) => screen.getByText(name, { selector: "dt" }).closest("div") as HTMLElement;
    expect(within(term("Strengths")).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Logical reasoning", "Verbal ability"]);
    expect(within(term("Recommended streams")).getByText("Science (PCM)")).toBeTruthy();
    expect(term("Counsellor remarks").textContent).toContain("Line one\nLine two");
    expect(within(term("Parent discussion")).getByText("Agreed on a design camp.")).toBeTruthy();
    expect(screen.getByText("Test date", { selector: "dt" })).toBeTruthy();
    expect(screen.getByText("Follow-up", { selector: "dt" })).toBeTruthy();
    expect(screen.queryByText("Personality indicators")).toBeNull();
  });

  it("renders markup as literal text", () => {
    const { container } = render(<PsychometricResultDetails result={{ strengths: ["<img src=x onerror=alert(1)>"], counsellor_remarks: "<script>alert(1)</script>" }} />);
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeTruthy();
    expect(screen.getByText("<script>alert(1)</script>")).toBeTruthy();
    expect(container.querySelector("img, script")).toBeNull();
  });
});

describe("PsychometricResultsList", () => {
  it("renders a disclosure per assessment with results and a plain line for one without", () => {
    render(<PsychometricResultsList assessments={[{ id: "a", assessment_type: "Aptitude Test", ...FULL }, { id: "b", assessment_type: "Interest Inventory" }]} />);
    expect(screen.getByText("Aptitude Test — results", { selector: "summary" })).toBeTruthy();
    expect(screen.getByText("Interest Inventory: no results recorded yet.")).toBeTruthy();
    expect(screen.getAllByRole("group")).toHaveLength(1); // <details> has the implicit "group" role
  });
});
```

Append to `apps/web/tests/components/Student360Panels.test.tsx` (inside the existing top-level `describe`, reusing its `view()` helper):

```tsx
  it("shows structured psychometric results under the table, and an empty line for a legacy record (ENH-027)", () => {
    const tab: Tab360 = { status: "has_data", count: 2, not_tracked: [], data: { assessments: [
      { id: "a", assessment_type: "Aptitude Test", status: "completed", created_at: "2026-09-01T00:00:00Z", strengths: ["Logical reasoning"] },
      { id: "b", assessment_type: "Interest Inventory", status: "assigned", created_at: "2026-09-02T00:00:00Z" },
    ] } };
    render(<>{renderPanel("psychometric_assessment", tab, view())}</>);
    expect(screen.getByRole("table", { name: "Psychometric assessments" })).toBeTruthy();
    expect(screen.getByText("Aptitude Test — results", { selector: "summary" })).toBeTruthy();
    expect(screen.getByText("Logical reasoning")).toBeTruthy();
    expect(screen.getByText("Interest Inventory: no results recorded yet.")).toBeTruthy();
  });
```

(If the existing file's top-level block has a different name, add the test inside it; `Tab360`, `renderPanel`, `view`, `screen`, `render` are already imported there.)

`apps/web/tests/components/SchoolChildOverview.psychometric.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolChildOverview, { type ChildOverview } from "@/components/SchoolChildOverview";

vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));
afterEach(cleanup);

const base: ChildOverview = {
  student: { id: "s1", student_code: "A1B2C3D4", full_name: "Asha R", date_of_birth: null, grade_or_class: "Grade 8-A", school_name: "Sunrise School", assigned_teacher_name: null },
  career_guidance: { status: "not_started", sessions: [] },
  counselling: { status: "not_started", notes: [] },
  recommended_careers: [],
  psychometric: { status: "completed", assessments: [
    { id: "a", assessment_type: "Aptitude Test", status: "completed", created_at: "2026-09-01T00:00:00Z", recommended_streams: ["Science (PCM)"] },
    { id: "b", assessment_type: "Interest Inventory", status: "assigned", created_at: "2026-09-02T00:00:00Z" },
  ] },
  results: [],
  activities: { attended: [], upcoming: [] },
};

describe("Parent child overview — psychometric results (ENH-027)", () => {
  it("keeps the status table and adds the structured results", () => {
    render(<SchoolChildOverview overview={base} />);
    expect(screen.getByRole("columnheader", { name: "Assigned on" })).toBeTruthy();
    expect(screen.getByText("Aptitude Test — results", { selector: "summary" })).toBeTruthy();
    expect(screen.getByText("Science (PCM)")).toBeTruthy();
    expect(screen.getByText("Interest Inventory: no results recorded yet.")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && npx vitest run tests/components/PsychometricResultDetails.test.tsx tests/components/Student360Panels.test.tsx tests/components/SchoolChildOverview.psychometric.test.tsx`
Expected: FAIL — missing module `@/components/PsychometricResultDetails`; the two extended suites fail on "Aptitude Test — results" not found.

- [ ] **Step 3: Implement the component**

`apps/web/components/PsychometricResultDetails.tsx`:

```tsx
import type { ReactNode } from "react";

import { formatCalendarDate } from "@/lib/formatDate";
import { hasResults, RESULT_LIST_FIELDS, type PsychometricResult } from "@/lib/psychometric";

// ENH-027 -- one psychometric result as structured data (spec §5.1). Presentational and server-safe; everything renders as
// text (React escaping), never HTML. Shared by the 360° Psychometric tab and the Parent child overview.

function Fact({ label, wide, children }: { label: string; wide?: boolean; children: ReactNode }) {
  return <div className={wide ? "psy-result-wide" : undefined}><dt className="muted">{label}</dt><dd>{children}</dd></div>;
}

export default function PsychometricResultDetails({ result }: { result: PsychometricResult }) {
  const discussed = result.parent_discussion_on || result.parent_discussion_notes;
  return (
    <dl className="s360-facts psy-result-facts">
      {result.test_date ? <Fact label="Test date">{formatCalendarDate(result.test_date)}</Fact> : null}
      {discussed ? (
        <Fact label="Parent discussion">
          {result.parent_discussion_on ? formatCalendarDate(result.parent_discussion_on) : null}
          {result.parent_discussion_notes ? <p className="psy-result-text">{result.parent_discussion_notes}</p> : null}
        </Fact>
      ) : null}
      {result.follow_up_on ? <Fact label="Follow-up">{formatCalendarDate(result.follow_up_on)}</Fact> : null}
      {RESULT_LIST_FIELDS.map(({ key, label }) => {
        const items = result[key];
        return items?.length ? <Fact key={key} label={label}><ul>{items.map((item) => <li key={item}>{item}</li>)}</ul></Fact> : null;
      })}
      {result.counsellor_remarks ? <Fact label="Counsellor remarks" wide><p className="psy-result-text">{result.counsellor_remarks}</p></Fact> : null}
    </dl>
  );
}

export function PsychometricResultsList({ assessments }: { assessments: (PsychometricResult & { id: string; assessment_type: string })[] }) {
  if (assessments.length === 0) return null;
  return (
    <div className="psy-results">
      {assessments.map((a) => hasResults(a) ? (
        <details key={a.id} className="psy-result">
          <summary>{a.assessment_type} — results</summary>
          <PsychometricResultDetails result={a} />
        </details>
      ) : (
        <p key={a.id} className="muted">{a.assessment_type}: no results recorded yet.</p>
      ))}
    </div>
  );
}
```

(List items are unique per record — the API de-duplicates case-insensitively — so `key={item}` is stable.)

- [ ] **Step 4: CSS**

Append to `apps/web/app/globals.css` after the `.s360-list li p` rule:

```css
/* ENH-027 -- psychometric results: existing tokens only; the facts grid already collapses to one column on a phone. */
.psy-results { display: grid; gap: 8px; margin-top: 12px; }
.psy-result { border: 1px solid var(--line); border-radius: 12px; padding: 10px 14px; }
.psy-result summary { cursor: pointer; font-weight: 800; }
.psy-result .s360-facts { margin-top: 12px; }
.psy-result-facts dd ul { margin: 0; padding-left: 18px; font-weight: 400; }
.psy-result-wide { grid-column: 1 / -1; }
.psy-result-text { white-space: pre-wrap; overflow-wrap: anywhere; font-weight: 400; margin: 4px 0 0; }
```

- [ ] **Step 5: Use it in the two views**

`Student360Panels.tsx` — add `import { PsychometricResultsList } from "@/components/PsychometricResultDetails";` and change the `psychometric_assessment` case to:

```tsx
    case "psychometric_assessment":
      return (
        <Card>
          <Table caption="Psychometric assessments" head={["Assessment", "Status", "Date"]} rows={d.assessments.map((a: Row) => [a.assessment_type, a.status ? <StatusChip status={a.status} /> : null, formatDate(a.created_at, false, SCHOOL_TIME_ZONE)])} />
          <PsychometricResultsList assessments={d.assessments} />
        </Card>
      );
```

`SchoolChildOverview.tsx` — add `import { PsychometricResultsList } from "@/components/PsychometricResultDetails";` and `import type { PsychometricResult } from "@/lib/psychometric";`; line 15 becomes `type Assessment = { id: string; assessment_type: string; status: string; created_at: string } & PsychometricResult;`; in the psychometric card's non-empty branch, wrap the existing `<div className="table-wrap">…</div>` in a fragment followed by `<PsychometricResultsList assessments={overview.psychometric.assessments} />`.

`lib/portfolio.ts:18` — `psychometric_report: ({ id: string; assessment_type: string; report_url: string | null; created_at: string } & PsychometricResult)[];` with `import type { PsychometricResult } from "@/lib/psychometric";`.

- [ ] **Step 6: Run to verify pass**

Run: `cd apps/web && npx vitest run tests/components/PsychometricResultDetails.test.tsx tests/components/Student360Panels.test.tsx tests/components/SchoolChildOverview.psychometric.test.tsx tests/components/SchoolChildOverview.skills.test.tsx tests/components/Student360Page.test.tsx tests/components/PortfolioPanel.test.tsx && npm run typecheck`
Expected: all PASS; typecheck clean.

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/PsychometricResultDetails.tsx apps/web/app/globals.css apps/web/components/Student360Panels.tsx apps/web/components/SchoolChildOverview.tsx apps/web/lib/portfolio.ts apps/web/tests/components/PsychometricResultDetails.test.tsx apps/web/tests/components/Student360Panels.test.tsx apps/web/tests/components/SchoolChildOverview.psychometric.test.tsx
git commit -m "feat(enh-027): show structured psychometric results in the 360 view and parent overview

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The editor — `PsychometricResultsForm`

**Files:**
- Create: `apps/web/components/PsychometricResultsForm.tsx`
- Test: `apps/web/tests/components/PsychometricResultsForm.test.tsx`

**Interfaces:**
- Consumes: Task 5 exports; `sendJson` (`lib/apiErrors.ts`), `FormMessage`.
- Produces: default export `PsychometricResultsForm({ record, studentName, onDone }: { record: PsychometricResult & { id: string; assessment_type: string }; studentName: string; onDone: (saved: boolean) => void })`. Heading text `Results — {studentName} · {assessment_type}`. Control ids: `psy-result-test-date`, `psy-result-strengths`, `psy-result-interest-areas`, `psy-result-personality-indicators`, `psy-result-career-recommendations`, `psy-result-recommended-streams`, `psy-result-counsellor-remarks`, `psy-result-parent-discussion-on`, `psy-result-parent-discussion-notes`, `psy-result-follow-up-on`. Buttons: "Save results" (busy: "Saving…"), "Cancel".

- [ ] **Step 1: Write the failing tests**

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PsychometricResultsForm from "@/components/PsychometricResultsForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const RECORD = { id: "r1", assessment_type: "Aptitude Test", strengths: ["Logic", "Verbal"], counsellor_remarks: "Keep going", test_date: "2026-09-10" };
const ok = () => vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "r1" }) });

function renderForm(onDone = vi.fn()) {
  render(<PsychometricResultsForm record={RECORD} studentName="Asha" onDone={onDone} />);
  return onDone;
}

describe("PsychometricResultsForm", () => {
  it("focuses its heading and prefills every field", () => {
    renderForm();
    expect(screen.getByRole("heading", { name: "Results — Asha · Aptitude Test" })).toHaveFocus();
    expect(screen.getByLabelText("Strengths")).toHaveValue("Logic\nVerbal");
    expect(screen.getByLabelText("Test date")).toHaveValue("2026-09-10");
    expect(screen.getByLabelText("Counsellor remarks")).toHaveValue("Keep going");
    expect(screen.getByLabelText("Interest areas")).toHaveValue("");
  });

  it("sends only the changed fields, emptied ones as null", async () => {
    const fetchMock = ok();
    vi.stubGlobal("fetch", fetchMock);
    const onDone = renderForm();
    fireEvent.change(screen.getByLabelText("Strengths"), { target: { value: "Logic\nVerbal\nSpatial" } });
    fireEvent.change(screen.getByLabelText("Counsellor remarks"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    await vi.waitFor(() => expect(onDone).toHaveBeenCalledWith(true));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/psychometric-team/records/r1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ strengths: ["Logic", "Verbal", "Spatial"], counsellor_remarks: null });
  });

  it("sends nothing when nothing changed", () => {
    const fetchMock = ok();
    vi.stubGlobal("fetch", fetchMock);
    renderForm();
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("No changes to save.");
  });

  it("blocks an over-long list on the client, marks the field and focuses it", () => {
    const fetchMock = ok();
    vi.stubGlobal("fetch", fetchMock);
    renderForm();
    const field = screen.getByLabelText("Interest areas");
    fireEvent.change(field, { target: { value: "x".repeat(81) } });
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription(/80 characters or fewer/);
    expect(field).toHaveFocus();
  });

  it("keeps the card open with the input on a failed save", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: "This school's partnership expired on 22 Sep 2026." }) }));
    const onDone = renderForm();
    fireEvent.change(screen.getByLabelText("Recommended streams"), { target: { value: "Commerce" } });
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("partnership expired");
    expect(onDone).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Recommended streams")).toHaveValue("Commerce");
    expect(screen.getByRole("button", { name: "Save results" })).toBeEnabled();
  });

  it("disables both buttons while saving", async () => {
    let resolve: (v: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise((r) => { resolve = r; })));
    renderForm();
    fireEvent.change(screen.getByLabelText("Follow-up date"), { target: { value: "2026-10-15" } });
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    resolve({ ok: true, status: 200, json: async () => ({}) });
  });

  it("warns before leaving only while there are unsaved changes, and Cancel reports not saved", () => {
    const add = vi.spyOn(window, "addEventListener");
    const onDone = renderForm();
    expect(add.mock.calls.some(([type]) => type === "beforeunload")).toBe(false);
    fireEvent.change(screen.getByLabelText("Strengths"), { target: { value: "Logic" } });
    expect(add.mock.calls.some(([type]) => type === "beforeunload")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onDone).toHaveBeenCalledWith(false);
    add.mockRestore();
  });

  it("shows a character count for the remarks", () => {
    renderForm();
    expect(screen.getByText("10 / 4000")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && npx vitest run tests/components/PsychometricResultsForm.test.tsx`
Expected: FAIL — cannot resolve `@/components/PsychometricResultsForm`.

- [ ] **Step 3: Implement**

`apps/web/components/PsychometricResultsForm.tsx`:

```tsx
"use client";

import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from "react";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { sendJson } from "@/lib/apiErrors";
import {
  changedFields, listError, LIST_ITEM_MAX, LIST_MAX_ITEMS, NOTES_MAX, REMARKS_MAX, RESULT_LIST_FIELDS, toDraft,
  type PsychometricResult, type ResultDraft, type ResultKey, type ResultListKey,
} from "@/lib/psychometric";

// ENH-027 -- record/edit one assessment's structured result (spec §5.3). Patterns reused from ActivityFeedbackForm (ENH-018):
// heading focus on open, beforeunload while dirty, counters, field-level aria-invalid. Only changed fields are sent, so two
// team members editing different fields never overwrite each other (spec §4.3). The API is the authority; the client checks
// are for usability only.

type Props = { record: PsychometricResult & { id: string; assessment_type: string }; studentName: string; onDone: (saved: boolean) => void };

const id = (key: ResultKey) => `psy-result-${key.replaceAll("_", "-")}`;
const LIST_HINT_ID = "psy-result-lists-hint";

export default function PsychometricResultsForm({ record, studentName, onDone }: Props) {
  const [initial] = useState<ResultDraft>(() => toDraft(record));
  const [draft, setDraft] = useState<ResultDraft>(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const [errors, setErrors] = useState<Partial<Record<ResultListKey, string>>>({});
  const headingRef = useRef<HTMLHeadingElement>(null);
  const listRefs = useRef<Partial<Record<ResultListKey, HTMLTextAreaElement | null>>>({});
  const dirty = Object.keys(changedFields(initial, draft)).length > 0;

  useEffect(() => headingRef.current?.focus(), []);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const bind = (key: ResultKey) => ({
    id: id(key),
    name: key,
    value: draft[key],
    disabled: busy,
    onChange: (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setDraft((d) => ({ ...d, [key]: e.target.value })),
  });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found: Partial<Record<ResultListKey, string>> = {};
    for (const { key } of RESULT_LIST_FIELDS) {
      const error = listError(draft[key]);
      if (error) found[key] = error;
    }
    setErrors(found);
    const first = RESULT_LIST_FIELDS.find(({ key }) => found[key]);
    if (first) {
      listRefs.current[first.key]?.focus();
      return;
    }
    const payload = changedFields(initial, draft);
    if (Object.keys(payload).length === 0) {
      setMessage({ text: "No changes to save.", failed: false });
      return;
    }
    setBusy(true);
    setMessage(null);
    const result = await sendJson(`/api/v1/school/psychometric-team/records/${record.id}`, "PATCH", payload);
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true });
      return;
    }
    onDone(true);
  }

  return (
    <div className="action-card">
      <h3 ref={headingRef} tabIndex={-1}>Results — {studentName} · {record.assessment_type}</h3>
      <form className="form" onSubmit={submit} aria-busy={busy} noValidate>
        <fieldset className="question">
          <legend>Assessment</legend>
          <div className="field">
            <label htmlFor={id("test_date")}>Test date</label>
            <input type="date" {...bind("test_date")} />
          </div>
        </fieldset>

        <fieldset className="question">
          <legend>Findings</legend>
          <p id={LIST_HINT_ID} className="muted">One per line — up to {LIST_MAX_ITEMS} items of {LIST_ITEM_MAX} characters each.</p>
          {RESULT_LIST_FIELDS.map(({ key, label }) => {
            const errorId = `${id(key)}-error`;
            return (
              <div className="field" key={key}>
                <label htmlFor={id(key)}>{label}</label>
                <textarea
                  {...bind(key)}
                  ref={(el) => { listRefs.current[key] = el; }}
                  rows={3}
                  aria-invalid={errors[key] ? true : undefined}
                  aria-describedby={errors[key] ? `${LIST_HINT_ID} ${errorId}` : LIST_HINT_ID}
                />
                {errors[key] ? <p id={errorId} className="form-error">{errors[key]}</p> : null}
              </div>
            );
          })}
        </fieldset>

        <fieldset className="question">
          <legend>Counselling &amp; follow-up</legend>
          <div className="field">
            <label htmlFor={id("counsellor_remarks")}>Counsellor remarks</label>
            <textarea {...bind("counsellor_remarks")} maxLength={REMARKS_MAX} aria-describedby={`${id("counsellor_remarks")}-count`} />
            <small id={`${id("counsellor_remarks")}-count`} className="muted">{draft.counsellor_remarks.length} / {REMARKS_MAX}</small>
          </div>
          <div className="form-grid">
            <div className="field">
              <label htmlFor={id("parent_discussion_on")}>Parent discussion date</label>
              <input type="date" {...bind("parent_discussion_on")} />
            </div>
            <div className="field">
              <label htmlFor={id("follow_up_on")}>Follow-up date</label>
              <input type="date" {...bind("follow_up_on")} />
            </div>
          </div>
          <div className="field">
            <label htmlFor={id("parent_discussion_notes")}>Parent discussion notes</label>
            <textarea {...bind("parent_discussion_notes")} maxLength={NOTES_MAX} aria-describedby={`${id("parent_discussion_notes")}-count`} />
            <small id={`${id("parent_discussion_notes")}-count`} className="muted">{draft.parent_discussion_notes.length} / {NOTES_MAX}</small>
          </div>
        </fieldset>

        <div className="actions">
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Save results"}</button>
          <button type="button" className="btn secondary" disabled={busy} onClick={() => onDone(false)}>Cancel</button>
        </div>
      </form>
      {message && <FormMessage message={message} />}
    </div>
  );
}
```

Note: the test uses the label "Follow-up date" — keep that label text exactly.

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && npx vitest run tests/components/PsychometricResultsForm.test.tsx && npm run typecheck && npx eslint components/PsychometricResultsForm.tsx`
Expected: PASS; no type or lint errors.

- [ ] **Step 5: Refactor check, then commit**

The file must stay under ~200 lines; if it grew beyond, extract the Findings fieldset into a local component in the same file (no new file). Rerun Step 4.

```bash
git add apps/web/components/PsychometricResultsForm.tsx apps/web/tests/components/PsychometricResultsForm.test.tsx
git commit -m "feat(enh-027): add the psychometric results editor

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Wire the editor into the dashboard panel

**Files:**
- Modify: `apps/web/components/SchoolPsychometricRecordsPanel.tsx`
- Modify: `apps/web/app/school/psychometric-team/dashboard/page.tsx:10`
- Test: `apps/web/tests/components/SchoolPsychometricRecordsPanel.test.tsx` (extend; existing tests untouched)

**Interfaces:**
- Consumes: `PsychometricResultsForm` (Task 7), `hasResults`, `PsychometricResult` (Task 5).
- Produces: per-row button, visible text "Record results" / "Edit results", accessible name `"{Record|Edit} results for {student} — {assessment_type}"`.

- [ ] **Step 1: Write the failing tests** (append a new `describe` to the existing file; reuse its `STUDENTS`, `RECORDS`, `card`, imports)

```tsx
describe("SchoolPsychometricRecordsPanel results editor (ENH-027)", () => {
  it("labels the button by whether results exist, naming the student and assessment", () => {
    render(<SchoolPsychometricRecordsPanel records={[RECORDS[0], { ...RECORDS[0], id: "r2", assessment_type: "Interest", strengths: ["Logic"] }]} students={STUDENTS} />);
    expect(screen.getByRole("button", { name: "Record results for Asha — Aptitude" })).toHaveTextContent("Record results");
    expect(screen.getByRole("button", { name: "Edit results for Asha — Interest" })).toHaveTextContent("Edit results");
  });

  it("opens one card at a time with the attach card", () => {
    render(<SchoolPsychometricRecordsPanel records={RECORDS} students={STUDENTS} />);
    fireEvent.click(screen.getByRole("button", { name: "Attach report" }));
    fireEvent.click(screen.getByRole("button", { name: "Record results for Asha — Aptitude" }));
    expect(screen.queryByRole("heading", { name: "Attach report" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Results — Asha · Aptitude" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Attach report" }));
    expect(screen.queryByRole("heading", { name: "Results — Asha · Aptitude" })).toBeNull();
  });

  it("returns focus to the row button on Cancel", () => {
    render(<SchoolPsychometricRecordsPanel records={RECORDS} students={STUDENTS} />);
    const trigger = screen.getByRole("button", { name: "Record results for Asha — Aptitude" });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(trigger).toHaveFocus();
  });

  it("closes the card and announces success under the assign form after a save", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "r1" }) }));
    render(<SchoolPsychometricRecordsPanel records={RECORDS} students={STUDENTS} />);
    fireEvent.click(screen.getByRole("button", { name: "Record results for Asha — Aptitude" }));
    fireEvent.change(screen.getByLabelText("Strengths"), { target: { value: "Logic" } });
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Results saved.");
    expect(card("Assign an assessment")).toContainElement(status);
    expect(screen.queryByRole("heading", { name: "Results — Asha · Aptitude" })).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/web && npx vitest run tests/components/SchoolPsychometricRecordsPanel.test.tsx`
Expected: the 4 new tests FAIL (no "Record results" button); the 5 existing tests PASS.

- [ ] **Step 3: Implement**

In `SchoolPsychometricRecordsPanel.tsx`:

1. Imports: `import { FormEvent, useEffect, useRef, useState } from "react";`, `import PsychometricResultsForm from "@/components/PsychometricResultsForm";`, `import { hasResults, type PsychometricResult } from "@/lib/psychometric";`.
2. `type Record_ = { id: string; school_student_id: string; assessment_type: string; report_url: string | null; status: string; created_at: string } & PsychometricResult;`
3. Replace `const [uploadingId, setUploadingId] = useState<string | null>(null);` with:

```tsx
  // One action card at a time (ENH-027): the attach card or the results editor.
  const [open, setOpen] = useState<{ kind: "attach" | "results"; id: string } | null>(null);
  const uploadingId = open?.kind === "attach" ? open.id : null;
  const resultsRecord = open?.kind === "results" ? records.find((r) => r.id === open.id) ?? null : null;
  const triggers = useRef<Record<string, HTMLButtonElement | null>>({});
  const [returnFocusTo, setReturnFocusTo] = useState<string | null>(null);

  useEffect(() => {
    if (!returnFocusTo) return;
    triggers.current[returnFocusTo]?.focus();
    setReturnFocusTo(null);
  }, [returnFocusTo]);
```

4. `setUploadingId(null)` in `attachReport` → `setOpen(null)`; `startAttach` body → `clearAttachMessage(); setOpen({ kind: "attach", id: recordId });`; `stopAttach` body → `clearAttachMessage(); setOpen(null);`.
5. Add:

```tsx
  function startResults(recordId: string) {
    clearAttachMessage();
    setOpen({ kind: "results", id: recordId });
  }

  function finishResults(saved: boolean) {
    const recordId = open?.id ?? null;
    setOpen(null);
    if (saved) {
      setMessage({ text: "Results saved.", failed: false, form: "assign" });
      router.refresh();
    }
    setReturnFocusTo(recordId);
  }
```

6. Actions cell becomes:

```tsx
                    <td>
                      <div className="actions">
                        {r.status === "assigned" ? (
                          <button className="btn ghost small" onClick={() => startAttach(r.id)}>Attach report</button>
                        ) : (
                          <span className="muted" style={{ fontSize: 13 }}>Report attached</span>
                        )}
                        <button
                          ref={(el) => { triggers.current[r.id] = el; }}
                          className="btn ghost small"
                          aria-label={`${hasResults(r) ? "Edit" : "Record"} results for ${studentName(r.school_student_id)} — ${r.assessment_type}`}
                          onClick={() => startResults(r.id)}
                        >
                          {hasResults(r) ? "Edit results" : "Record results"}
                        </button>
                      </div>
                    </td>
```

7. After the `{uploadingId && (…attach card…)}` block:

```tsx
      {resultsRecord && (
        <PsychometricResultsForm key={resultsRecord.id} record={resultsRecord} studentName={studentName(resultsRecord.school_student_id)} onDone={finishResults} />
      )}
```

8. `dashboard/page.tsx:10`: `type Record_ = { id: string; school_student_id: string; assessment_type: string; report_url: string | null; status: string; created_at: string } & PsychometricResult;` with `import type { PsychometricResult } from "@/lib/psychometric";`.

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && npx vitest run tests/components/SchoolPsychometricRecordsPanel.test.tsx tests/components/PsychometricResultsForm.test.tsx && npm run typecheck && npm run lint`
Expected: all 9 panel tests PASS (5 existing unchanged + 4 new); typecheck and lint clean.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/SchoolPsychometricRecordsPanel.tsx apps/web/app/school/psychometric-team/dashboard/page.tsx apps/web/tests/components/SchoolPsychometricRecordsPanel.test.tsx
git commit -m "feat(enh-027): open the results editor from the psychometric dashboard

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Browser flow (Playwright)

**Files:**
- Create: `apps/web/tests/e2e/enh-027-psychometric-results.spec.ts`

**Interfaces:** Consumes the running stack (user-started) and `tests/e2e/helpers/welcome` (`E2E_PASSWORD`, `createAndActivate`), same as `enh-013-student-360.spec.ts`.

- [ ] **Step 1: Write the spec**

```ts
import { expect, request as playwrightRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ENH-027 -- structured psychometric results (docs/superpowers/specs/2026-09-28-enh-027-psychometric-result-fields-design.md, AC07).
// API-only setup (like enh-013): a throwaway school, a psychometric-team member, one student with a linked parent and one assigned
// assessment. The feature is driven through the real UI: keyboard-only entry, the 360° tab, the parent's child page, a 320 px phone.

const INVITE_PASSWORD = "Sup3r-Secret-Pass!";
const unique = Date.now();
const email = (who: string) => `enh027-e2e-${who}-${unique}@example.local`;
const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";
const ctx = { studentId: "", parentEmail: email("parent") };
const BUTTON = "Record results for Asha 027 — Aptitude Test";

async function apiAs(emailAddress: string, password: string): Promise<APIRequestContext> {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post("/api/v1/auth/login", { data: { email: emailAddress, password, division: "overseas" } });
  if (!res.ok()) throw new Error(`login ${emailAddress}: ${res.status()} ${await res.text()}`);
  return api;
}

async function signIn(page: Page, emailAddress: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/overseas/login");
  await page.fill("#login-email", emailAddress);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test.describe.serial("ENH-027 psychometric results", () => {
  test.beforeAll(async () => {
    test.setTimeout(120_000);
    const admin = await apiAs("overseasadmin@edusphere.local", "Demo@123");
    const school = await createAndActivate(admin, "/api/v1/overseas-admin/schools", { name: `E2E 027 School ${unique}`, coordinator_full_name: "E2E 027 Coordinator", coordinator_email: email("coord") });
    await createAndActivate(admin, "/api/v1/overseas-admin/school-staff", { role: "psychometric_team", full_name: "E2E 027 Psych", email: email("psych"), school_ids: [school.id] });
    await admin.dispose();

    const coord = await apiAs(email("coord"), E2E_PASSWORD);
    const created = await coord.post("/api/v1/school/students", { data: { full_name: "Asha 027", grade_or_class: "Grade 9", parent_name: "E2E 027 Parent", parent_email: ctx.parentEmail } });
    expect(created.status()).toBe(201);
    const student = await created.json();
    ctx.studentId = student.id;
    await coord.dispose();
    const invite = await playwrightRequest.newContext({ baseURL });
    expect((await invite.post(`/api/v1/school/invites/${student.development_invite_token}/accept`, { data: { password: INVITE_PASSWORD } })).ok()).toBe(true);
    await invite.dispose();

    const psych = await apiAs(email("psych"), E2E_PASSWORD);
    expect((await psych.post("/api/v1/school/psychometric-team/records", { data: { school_student_id: ctx.studentId, assessment_type: "Aptitude Test" } })).status()).toBe(201);
    await psych.dispose();
  });

  test("the team records results with the keyboard only", async ({ page }) => {
    await signIn(page, email("psych"), E2E_PASSWORD, "/school/psychometric-team/dashboard");
    await page.getByRole("button", { name: BUTTON }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Results — Asha 027 · Aptitude Test" })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.locator("#psy-result-test-date")).toBeFocused();
    await page.locator("#psy-result-test-date").fill("2026-09-10");
    await page.locator("#psy-result-strengths").fill("Logical reasoning\nVerbal ability");
    await page.locator("#psy-result-recommended-streams").fill("Science (PCM)");
    await page.locator("#psy-result-counsellor-remarks").fill("Strong analytical profile.");
    await page.locator("#psy-result-follow-up-on").fill("2026-10-15");
    await page.getByRole("button", { name: "Save results" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText("Results saved.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Edit results for Asha 027 — Aptitude Test" })).toBeVisible();
  });

  test("the 360° Psychometric tab shows the structured results", async ({ page }) => {
    await signIn(page, email("psych"), E2E_PASSWORD, "/school/psychometric-team/dashboard");
    await page.goto(`/school/psychometric-team/students/${ctx.studentId}/360?tab=psychometric_assessment`);
    const panel = page.getByRole("tabpanel");
    await panel.getByText("Aptitude Test — results").click();
    await expect(panel).toContainText("Logical reasoning");
    await expect(panel).toContainText("Science (PCM)");
    await expect(panel).toContainText("Strong analytical profile.");
  });

  test("the parent sees them on the child page", async ({ page }) => {
    await signIn(page, ctx.parentEmail, INVITE_PASSWORD, "/school/parent/dashboard");
    await page.goto(`/school/parent/children/${ctx.studentId}`);
    await page.getByText("Aptitude Test — results").click();
    await expect(page.getByText("Verbal ability")).toBeVisible();
  });

  test("the editor fits a 320 px phone without page overflow", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 800 });
    await signIn(page, email("psych"), E2E_PASSWORD, "/school/psychometric-team/dashboard");
    await page.getByRole("button", { name: "Edit results for Asha 027 — Aptitude Test" }).click();
    await expect(page.locator("#psy-result-strengths")).toBeVisible();
    const widths = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, view: window.innerWidth }));
    expect(widths.doc).toBeLessThanOrEqual(widths.view);
  });
});
```

- [ ] **Step 2: Run it (stack must be up — ask the user; never start it)**

Run: `cd apps/web && npx playwright test tests/e2e/enh-027-psychometric-results.spec.ts`
Expected: 4 passed. If the stack is not up, record the spec as "written, not yet run" and continue; Task 12 runs it.

If the `?tab=psychometric_assessment` deep link does not select the tab (check `enh-013` for the query key), click the tab instead: `await page.getByRole("tab", { name: /^Psychometric Assessment/ }).click();`.

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/enh-027-psychometric-results.spec.ts
git commit -m "test(enh-027): browser flow for recording and viewing psychometric results

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Migration round trip preserves data (AC09)

**Files:** none changed (evidence recorded in Task 11's RTM row).

- [ ] **Step 1: Snapshot existing psychometric rows** (stack up; user's DB)

Run from the repo root:
`docker compose exec -T postgres psql -U edusphere -d edusphere -At -c "SELECT id, school_student_id, assessment_type, coalesce(report_url,''), status, created_at FROM school_psychometric_records ORDER BY id" > "$SCRATCH/enh027_before.txt"`
(`$SCRATCH` = this session's scratchpad directory.) Expected: one line per existing row (the seed has at least 3).

- [ ] **Step 2: Round trip**

Run: `cd apps/api && alembic downgrade -1 && alembic upgrade head`
Expected: no error; `alembic current` shows `0042_psychometric_result_fields (head)`.

- [ ] **Step 3: Compare**

Rerun Step 1's command into `enh027_after.txt`, then `diff "$SCRATCH/enh027_before.txt" "$SCRATCH/enh027_after.txt"`.
Expected: no output (identical). Note: the downgrade drops the 10 new columns, so any result values entered before the round trip are gone by design — the check covers the pre-existing columns only, which is what AC09 states.

---

### Task 11: Documentation and traceability

**Files:**
- Modify: `docs/architecture/DATA_MODEL.md` (§6.18 `SchoolPsychometricRecord` — dated addendum)
- Modify: `docs/architecture/API_CONTRACT.md` (psychometric rows — addendum row in the ENH-025 style, line ~266)
- Modify: `docs/architecture/SECURITY_CONTROLS.md` (new ENH-027 row after the ENH-023 row, ~line 102)
- Modify: `docs/features/FEATURE_ACCEPTANCE_CRITERIA.md` (under `SCH-005`, an `ENH-027` addendum listing AC01–AC10 by reference to the spec §7)
- Modify: `docs/quality/RTM.md` (ENH-027 row: DEC-SCOPE-031 → spec → tests → code; results filled in by Task 12)
- Modify: `docs/delivery/ENHANCEMENT_BACKLOG.md` (ENH-027 section: status line "Built on `feature/enh-027-psychometric-full-record`, pending browser validation and independent review"; correct "4 that exist today" to "3 plus `created_at` as an assignment-date proxy")

- [ ] **Step 1: Write each addendum** with these exact facts:
  - DATA_MODEL: the 10 columns and types from Global Constraints; nullable, no backfill; migration `0042`; `DEC-SCOPE-031`.
  - API_CONTRACT: the four psychometric endpoints + `/students/{id}/overview`, `/portfolio`, `/360-view` gain the 10 keys (`null` = not recorded; dates `YYYY-MM-DD`; lists never empty). Request: optional on POST and PATCH; PATCH absent = unchanged, `null`/`""`/`[]` = clear; limits; 422 `"<field> <reason>"`; 403 precedence; `report_url` exposure unchanged (Client Question #20); audit metadata `fields` (names only).
  - SECURITY_CONTROLS: one row summarising spec §6 (mass-assignment allow-list, validation, text rendering, names-only audit/logs, no new endpoint/role, rate limiting unchanged open item).
- [ ] **Step 2: Commit**

```bash
git add docs/architecture docs/features/FEATURE_ACCEPTANCE_CRITERIA.md docs/quality/RTM.md docs/delivery/ENHANCEMENT_BACKLOG.md
git commit -m "docs(enh-027): data model, API contract, security controls and traceability

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Full regression and hand-off (not completion)

- [ ] **Step 1: Backend suite** — `cd apps/api && pytest -q` → record pass/fail counts.
- [ ] **Step 2: Web unit + static** — `cd apps/web && npm test && npm run typecheck && npm run lint && npm run build` → record results.
- [ ] **Step 3: E2E** (stack up) — `cd apps/web && npx playwright test` → record results; failures investigated with `superpowers:systematic-debugging`, never by editing a test to pass.
- [ ] **Step 4: Update the RTM row** with the exact counts and commit (`docs(enh-027): record regression results`).
- [ ] **Step 5: Refresh the knowledge graph** — `/graphify --update` (no confirmation needed).
- [ ] **Step 6: Report** — state results with evidence. ENH-027 is **not** complete: browser validation and the independent Codex review are still required (user instruction).
