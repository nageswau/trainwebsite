# ENH-024 Skill India Certification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Numbering note (2026-09-28, merge with `main`):** this plan was written and executed as `DEC-SCOPE-031` with migration `0042_skill_india_certification`. ENH-026/ENH-021 reached `main` first with those numbers, so they are now **`DEC-SCOPE-033`** and **`0044_skill_india_certification`** (on `0043_portfolio_internship`). The task text below keeps the original numbers as a record of what was run.

**Goal:** Record a Skill India certification (status, certificate number, issuing body, issue date) on a school student's Digital Portfolio and show it on the Portfolio and the Student 360° Certificates tab.

**Architecture:** Four nullable columns + four CHECKs on the existing `portfolio_entries` table (migration `0042`); the existing ENH-012 portfolio endpoints gain the fields additively; the update route locks the entry row. Frontend reuses `PortfolioEntryForm` / `PortfolioPanel` / 360° `Entries`, with one new hook-free `CertificationDetails` component.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, PostgreSQL 16; Next.js (App Router), React, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md` (read it with this plan).

## Global Constraints

- Scope is ENH-024 only. No change to `Certificate`, `Program.certification`, `SchoolSkillEnrollment`, `SchoolLanguageRecord`, `build_360`, the 360° role projection, or any other ENH item.
- Additive API only: no endpoint added or removed, no field renamed or retyped; a request without the new fields behaves exactly as today.
- No new dependency (Python or npm).
- Tag value: `skill_india`. Status values: `enrolled`, `in_progress`, `certified`. Certificate number max 100 characters.
- Messages (verbatim): "Only a certification can be marked as Skill India" · "Choose a status for the Skill India certification" · "Status, certificate number and issue date apply only to Skill India certifications" · "A certified Skill India certification needs a certificate number and issue date".
- The certificate number never appears in application logs or `AuditLog` metadata (D16).
- Audit metadata keys are added **only for tagged entries**, so untagged entries' audit rows are byte-for-byte as today.
- A client component must not import `@/components/SchoolChildOverview` or `@/lib/api` directly **or transitively** (`tests/lib/clientBoundary.test.ts`; a transitive import breaks `next build`). Hence `CertificationDetails` renders status with the `.status` / `.status pending` classes itself instead of importing `StatusChip` (spec §6 deviation, recorded in Task 5).
- Existing tests are never edited to make them pass (AC-12).
- Imports shown mid-file in a task's test code (`# noqa: E402`) are moved into the test module's top import block when appended, keeping `ruff check` clean without suppressions.

## Test commands (PowerShell, from the worktree root)

The running `enh021-026` Docker stack serves a different worktree with its code baked in; it must not be used or migrated. This worktree uses its own isolated Compose project `enh024` (postgres/redis publish no host ports, so no clash). **The user starts the stack** (standing preference); one-off `run --rm` test containers mount this worktree's source.

```powershell
# User, once:
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh024 --profile ci build api-test web-test
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh024 --profile ci up -d --wait postgres redis

# Agent: migrate, then run API tests (source mounted)
function dc { docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh024 --profile ci @args }
dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test alembic upgrade head
dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test python -m pytest -q tests/test_enh_024_skill_india.py
# Web unit tests (mount source folders, keep the image's node_modules)
dc run --rm --no-deps -v "${PWD}\apps\web\components:/app/components" -v "${PWD}\apps\web\lib:/app/lib" -v "${PWD}\apps\web\tests:/app/tests" -v "${PWD}\apps\web\app:/app/app" web-test npx vitest run tests/components/PortfolioEntryForm.test.tsx
```

Below, **API(x)** means the pytest command with `x` as its arguments, **WEB(x)** the vitest command with `x`.

## Review Focus

1. **Two editors saving the same certificate at once** — must never surface as a 500; the later save validates against the earlier one's committed result (Task 4, race test).
2. **Old client / plain certification entries** — sending the full shape with `null`s, or no new fields, must behave exactly as today (Tasks 2, 3, 4: explicit-null and plain-entry tests).
3. **Tier downgrade mid-life** — a Skill India entry created before a downgrade stays editable/deletable; a new one is refused (Task 4).
4. **A certificate number with odd characters or huge length** (pasted newline, 101+ chars, whitespace only) — rejected or normalised, never stored raw (Task 2).
5. **The Skill India form on a phone / keyboard only** — fieldset reachable, errors announced and focused, layout wraps at 320 px (Tasks 6, 7).

---

### Task 1: Decision record, model columns, CHECKs and migration `0042`

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append `DEC-SCOPE-031`)
- Modify: `apps/api/app/models.py:1133-1152` (`PortfolioEntry`)
- Create: `apps/api/alembic/versions/0042_skill_india_certification.py`
- Test: `apps/api/tests/test_enh_024_skill_india.py` (create)

**Interfaces:**
- Produces: `PortfolioEntry.certification_type: str | None`, `.certification_status: str | None`, `.certificate_number: str | None`, `.issued_on: date | None`; DB constraints `ck_portfolio_cert_type`, `ck_portfolio_cert_status`, `ck_portfolio_cert_fields`, `ck_portfolio_cert_certified`; test helpers `ENTRIES`, `ENTRY`, `_row(ctx, **overrides)` in the test module.

- [ ] **Step 1: Append `DEC-SCOPE-031` to the decision register**

```markdown
### DEC-SCOPE-031 — Skill India certification tracking on the Digital Portfolio (`ENH-024`)

**ID note:** provisional. If another branch reaches `main` first holding `DEC-SCOPE-031`, renumber on merge (precedent: `DEC-SCOPE-024`/`025`/`027`/`029`/`030`).

**Question:** `docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-024 (`DERIVED_BLUEPRINT`; source: brochure page 2, "Skill India Certification", no `School CRM.md` section): how is a Skill India certification recorded per student and shown on the Portfolio / 360° view?

**Evidence:** Graphify-oriented investigation, 2026-09-28: ENH-012's `PortfolioEntry` already has a `certification` section; ENH-013's 360° Certificates tab renders exactly those entries (`student_360.py:102`). No field identifies Skill India, and none holds status, certificate number or issue date.

**Resolution:** User confirmed in-session, 2026-09-28 (`EXPLICIT_APPROVAL`), D1–D16 in `docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md` §3: tag on the existing `certification` section (no new section; completion % unchanged); status (`enrolled`/`in_progress`/`certified`, any-to-any), certificate number, issuing body (= `organization`), issue date — accepted only on tagged entries; `certified` requires number and issue date; no uniqueness; tag set at creation only; no external integration; existing writers, tier gate and transfer behaviour; certificate number kept out of logs and audit metadata; no rate limit added.

**Consequences:** migration `0042_skill_india_certification` (four nullable columns, four CHECKs, no backfill); `PortfolioEntryCreate`/`Update`/`Out` gain fields additively; the entry PATCH locks its row; new `CertificationDetails.tsx`; no new endpoint, table or dependency.
```

- [ ] **Step 2: Write the failing DB tests** — create `apps/api/tests/test_enh_024_skill_india.py`:

```python
"""ENH-024 -- Skill India certification tracking.
docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md
"""
import asyncio
import uuid
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models import AuditLog, PortfolioEntry
from tests.enh005_helpers import login, mk_school, mk_staff

ENTRIES = "/api/v1/school/students/{sid}/portfolio/entries"
ENTRY = ENTRIES + "/{eid}"


def _row(ctx, **overrides) -> PortfolioEntry:
    fields = {"section": "certification", "title": "Retail Sales Associate", "created_by_user_id": ctx["coordinator"].id, "updated_by_user_id": ctx["coordinator"].id, **overrides}
    return PortfolioEntry(school_student_id=ctx["students"][0].id, **fields)


# --- Task 1: schema -----------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_columns_are_nullable_and_sized(db_session):  # AC-10
    rows = (await db_session.execute(text(
        "SELECT column_name, data_type, character_maximum_length, is_nullable FROM information_schema.columns "
        "WHERE table_name = 'portfolio_entries' AND column_name IN ('certification_type', 'certification_status', 'certificate_number', 'issued_on') "
        "ORDER BY column_name"
    ))).all()
    assert [tuple(r) for r in rows] == [
        ("certificate_number", "character varying", 100, "YES"),
        ("certification_status", "character varying", 20, "YES"),
        ("certification_type", "character varying", 30, "YES"),
        ("issued_on", "date", None, "YES"),
    ]


@pytest.mark.asyncio
async def test_alembic_is_at_head_and_includes_0042(db_session):  # AC-10
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    script = ScriptDirectory.from_config(config)
    version = await db_session.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == script.get_current_head()
    assert "0042_skill_india_certification" in {rev.revision for rev in script.iterate_revisions(version, "base")}


@pytest.mark.asyncio
async def test_a_plain_entry_stays_untagged(db_session):  # AC-10, AC-12
    ctx = await mk_school(db_session, label="E24-Plain")
    entry = _row(ctx)
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    assert (entry.certification_type, entry.certification_status, entry.certificate_number, entry.issued_on) == (None, None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [
    {"section": "award", "certification_type": "skill_india", "certification_status": "enrolled"},
    {"certification_type": "nsdc", "certification_status": "enrolled"},
    {"certification_type": "skill_india"},
    {"certification_status": "enrolled"},
    {"certificate_number": "SI-1"},
    {"issued_on": date(2026, 5, 1)},
    {"certification_type": "skill_india", "certification_status": "passed"},
    {"certification_type": "skill_india", "certification_status": "certified", "issued_on": date(2026, 5, 1)},
    {"certification_type": "skill_india", "certification_status": "certified", "certificate_number": "SI-1"},
])
async def test_database_rejects_every_invalid_combination(db_session, overrides):  # AC-09
    ctx = await mk_school(db_session, label="E24-Check")
    db_session.add(_row(ctx, **overrides))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_database_accepts_a_certified_skill_india_row(db_session):  # AC-09
    ctx = await mk_school(db_session, label="E24-CheckOK")
    db_session.add(_row(ctx, certification_type="skill_india", certification_status="certified", certificate_number="SI-1", issued_on=date(2026, 5, 1)))
    await db_session.commit()
```

- [ ] **Step 3: Run — expect FAIL.** API(`tests/test_enh_024_skill_india.py -k "columns or head or plain or database"`). Expected: `TypeError: 'certification_type' is an invalid keyword argument for PortfolioEntry` / empty column list / head assertion.

- [ ] **Step 4: Add the model columns and CHECKs** in `PortfolioEntry` (`models.py`):

```python
    __tablename__ = "portfolio_entries"
    __table_args__ = (
        Index("ix_portfolio_entries_student_section", "school_student_id", "section"),
        # ENH-024 (spec §4): mirrored verbatim in migration 0042 -- the API rejects each of these first; the CHECKs are the last line.
        CheckConstraint("certification_type IS NULL OR (certification_type = 'skill_india' AND section = 'certification')", name="ck_portfolio_cert_type"),
        CheckConstraint("certification_status IS NULL OR certification_status IN ('enrolled', 'in_progress', 'certified')", name="ck_portfolio_cert_status"),
        CheckConstraint(
            "(certification_type IS NULL AND certification_status IS NULL AND certificate_number IS NULL AND issued_on IS NULL) "
            "OR (certification_type IS NOT NULL AND certification_status IS NOT NULL)",
            name="ck_portfolio_cert_fields",
        ),
        CheckConstraint("certification_status IS DISTINCT FROM 'certified' OR (certificate_number IS NOT NULL AND issued_on IS NOT NULL)", name="ck_portfolio_cert_certified"),
    )
    ...existing columns unchanged...
    # ENH-024 -- Skill India certification details; all NULL on every other entry (spec §4, DEC-SCOPE-031).
    certification_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    certification_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    certificate_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
```

Check first whether `Base.metadata` has a `naming_convention` (`grep -n naming_convention apps/api/app`); if it does, confirm the constraint names above are kept as given.

- [ ] **Step 5: Create the migration** `apps/api/alembic/versions/0042_skill_india_certification.py`:

```python
"""ENH-024 -- Skill India certification details on portfolio_entries.

Revision ID: 0042_skill_india_certification
Revises: 0041_student_master_fields

docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md §4 (DEC-SCOPE-031). Additive only: four nullable
columns and four CHECKs. Every existing row is all-NULL in the new columns, which satisfies every CHECK, so nothing is backfilled
or rewritten. `downgrade()` drops only what this adds (entries survive as plain certifications).
"""

import sqlalchemy as sa

from alembic import op

revision = "0042_skill_india_certification"
down_revision = "0041_student_master_fields"
branch_labels = None
depends_on = None

TABLE = "portfolio_entries"
COLUMNS = (
    ("certification_type", sa.String(30)), ("certification_status", sa.String(20)),
    ("certificate_number", sa.String(100)), ("issued_on", sa.Date()),
)
# Verbatim copies of PortfolioEntry.__table_args__ (a migration never imports the live models).
CHECKS = (
    ("ck_portfolio_cert_type", "certification_type IS NULL OR (certification_type = 'skill_india' AND section = 'certification')"),
    ("ck_portfolio_cert_status", "certification_status IS NULL OR certification_status IN ('enrolled', 'in_progress', 'certified')"),
    ("ck_portfolio_cert_fields", "(certification_type IS NULL AND certification_status IS NULL AND certificate_number IS NULL AND issued_on IS NULL) "
     "OR (certification_type IS NOT NULL AND certification_status IS NOT NULL)"),
    ("ck_portfolio_cert_certified", "certification_status IS DISTINCT FROM 'certified' OR (certificate_number IS NOT NULL AND issued_on IS NOT NULL)"),
)


def upgrade() -> None:
    # Guarded: on a fresh database 0001_initial's Base.metadata.create_all() has already built portfolio_entries from the *current*
    # models (columns and CHECKs included) -- same reason 0041 guards.
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns(TABLE)}
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints(TABLE)}
    for name, condition in CHECKS:
        if name not in checks:
            op.create_check_constraint(name, TABLE, condition)


def downgrade() -> None:
    for name, _ in CHECKS:
        op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {name}")
    for name, _ in COLUMNS:
        op.drop_column(TABLE, name)
```

- [ ] **Step 6: Migrate and run — expect PASS.** `alembic upgrade head`, then API(`tests/test_enh_024_skill_india.py`), then API(`tests/test_enh_012_digital_portfolio.py tests/test_enh_013_migration.py`) (regression: still green, unedited).

- [ ] **Step 7: Manual migration round-trip (AC-10).** `alembic downgrade -1`, then `alembic upgrade head`; both exit 0; rerun API(`tests/test_enh_024_skill_india.py -k "columns or head"`) — PASS. Note the outputs for the RTM (Task 8).

- [ ] **Step 8: Commit**

```bash
git add docs/decisions/PRODUCT_DECISION_REGISTER.md apps/api/app/models.py apps/api/alembic/versions/0042_skill_india_certification.py apps/api/tests/test_enh_024_skill_india.py
git commit -m "feat(enh-024): Skill India columns and CHECKs on portfolio_entries (migration 0042)"
```

---

### Task 2: Schemas — create/update/out fields and the shared rule

**Files:**
- Modify: `apps/api/app/schemas.py` (ENH-012 block, after `date_range_is_invalid`; `PortfolioEntryCreate`, `PortfolioEntryUpdate`, `PortfolioEntryOut`)
- Test: `apps/api/tests/test_enh_024_skill_india.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: `CERT_TYPE_SECTION_ERROR`, `CERT_STATUS_REQUIRED_ERROR`, `CERT_FIELDS_UNTAGGED_ERROR`, `CERT_CERTIFIED_ERROR: str`; `skill_india_error(certification_type: str | None, certification_status: str | None, certificate_number: str | None, issued_on: date | None) -> str | None`; the three models' new fields.

- [ ] **Step 1: Write the failing tests** (append):

```python
# --- Task 2: schemas ----------------------------------------------------------------------------------------------

from pydantic import ValidationError  # noqa: E402

from app.schemas import (  # noqa: E402
    CERT_CERTIFIED_ERROR,
    CERT_FIELDS_UNTAGGED_ERROR,
    CERT_STATUS_REQUIRED_ERROR,
    CERT_TYPE_SECTION_ERROR,
    PortfolioEntryCreate,
    PortfolioEntryUpdate,
    skill_india_error,
)

SKILL_INDIA = {"section": "certification", "title": "Retail Sales Associate", "certification_type": "skill_india"}


def test_create_accepts_a_skill_india_certification():
    entry = PortfolioEntryCreate(**SKILL_INDIA, certification_status="enrolled")
    assert (entry.certification_type, entry.certification_status, entry.certificate_number, entry.issued_on) == ("skill_india", "enrolled", None, None)


@pytest.mark.parametrize(("payload", "message"), [
    ({"section": "award", "certification_type": "skill_india", "certification_status": "enrolled"}, CERT_TYPE_SECTION_ERROR),
    ({"section": "certification", "certification_type": "skill_india"}, CERT_STATUS_REQUIRED_ERROR),
    ({"section": "certification", "certification_status": "enrolled"}, CERT_FIELDS_UNTAGGED_ERROR),
    ({"section": "certification", "certificate_number": "SI-1"}, CERT_FIELDS_UNTAGGED_ERROR),
    ({"section": "certification", "issued_on": "2026-05-01"}, CERT_FIELDS_UNTAGGED_ERROR),
    ({"section": "certification", "certification_type": "skill_india", "certification_status": "certified", "issued_on": "2026-05-01"}, CERT_CERTIFIED_ERROR),
    ({"section": "certification", "certification_type": "skill_india", "certification_status": "certified", "certificate_number": "SI-1"}, CERT_CERTIFIED_ERROR),
])
def test_create_rejects_with_a_plain_message(payload, message):  # AC-04
    with pytest.raises(ValidationError) as exc:
        PortfolioEntryCreate(title="Retail Sales Associate", **payload)
    assert message in exc.value.errors()[0]["msg"]


def test_create_accepts_explicit_nulls_on_an_untagged_entry():  # Review Focus 2
    entry = PortfolioEntryCreate(section="project", title="X", certification_type=None, certification_status=None, certificate_number=None, issued_on=None)
    assert entry.certification_type is None


def test_certificate_number_is_trimmed_and_blank_becomes_none():  # Review Focus 4
    assert PortfolioEntryCreate(**SKILL_INDIA, certification_status="enrolled", certificate_number="  SI-9 ").certificate_number == "SI-9"
    assert PortfolioEntryCreate(**SKILL_INDIA, certification_status="enrolled", certificate_number="   ").certificate_number is None


@pytest.mark.parametrize("bad", ["SI\n1", "SI\x001", "a" * 101])
def test_certificate_number_rejects_control_characters_and_overlength(bad):  # Review Focus 4
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(**SKILL_INDIA, certification_status="enrolled", certificate_number=bad)


@pytest.mark.parametrize("payload", [{"certification_type": "nsdc", "certification_status": "enrolled"}, {"certification_type": "skill_india", "certification_status": "passed"}])
def test_unknown_tag_or_status_is_rejected(payload):
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="certification", title="X", **payload)


def test_update_accepts_detail_fields_but_never_the_tag():  # AC-05
    update_ = PortfolioEntryUpdate(certification_status="certified", certificate_number="SI-1", issued_on="2026-05-01")
    assert update_.model_fields_set == {"certification_status", "certificate_number", "issued_on"}
    with pytest.raises(ValidationError):
        PortfolioEntryUpdate(certification_type="skill_india")


def test_skill_india_error_covers_every_rule():
    assert skill_india_error(None, None, None, None) is None
    assert skill_india_error(None, "enrolled", None, None) == CERT_FIELDS_UNTAGGED_ERROR
    assert skill_india_error("skill_india", None, None, None) == CERT_STATUS_REQUIRED_ERROR
    assert skill_india_error("skill_india", "certified", "SI-1", None) == CERT_CERTIFIED_ERROR
    assert skill_india_error("skill_india", "certified", "SI-1", date(2026, 5, 1)) is None
    assert skill_india_error("skill_india", "in_progress", None, None) is None
```

- [ ] **Step 2: Run — expect FAIL.** API(`tests/test_enh_024_skill_india.py -k "create or update or number or tag or skill_india_error"`). Expected: `ImportError: cannot import name 'CERT_CERTIFIED_ERROR'` (collection error for the whole module — also run the Task 1 tests once green to confirm).

- [ ] **Step 3: Implement** in `schemas.py` (after `date_range_is_invalid`; `Literal` is already imported — verify with `grep -n "^from typing" apps/api/app/schemas.py`, add `Literal` there if missing):

```python
# --- ENH-024: Skill India certification (docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md §5) ---
# Declared once and shared by PortfolioEntryCreate and portfolio.py's post-merge PATCH check (the DATE_RANGE_ERROR precedent).
CertificationType = Literal["skill_india"]
CertificationStatus = Literal["enrolled", "in_progress", "certified"]
CERT_TYPE_SECTION_ERROR = "Only a certification can be marked as Skill India"
CERT_STATUS_REQUIRED_ERROR = "Choose a status for the Skill India certification"
CERT_FIELDS_UNTAGGED_ERROR = "Status, certificate number and issue date apply only to Skill India certifications"
CERT_CERTIFIED_ERROR = "A certified Skill India certification needs a certificate number and issue date"


def skill_india_error(certification_type: str | None, certification_status: str | None, certificate_number: str | None, issued_on: date | None) -> str | None:
    """Spec D3/D6 on a complete state (a create payload, or a PATCH merged onto the stored entry); None when valid. Explicit
    nulls on an untagged entry are valid -- only a non-null detail is refused."""
    if certification_type is None:
        has_detail = certification_status is not None or certificate_number is not None or issued_on is not None
        return CERT_FIELDS_UNTAGGED_ERROR if has_detail else None
    if certification_status is None:
        return CERT_STATUS_REQUIRED_ERROR
    if certification_status == "certified" and (certificate_number is None or issued_on is None):
        return CERT_CERTIFIED_ERROR
    return None


def _clean_certificate_number(value: str | None) -> str | None:
    # `str_strip_whitespace` has already trimmed it; blank means "not given". Single-line, like title/organization.
    return _no_control_characters(value) if value else None
```

`PortfolioEntryCreate` — add fields after `date_to`, a field validator, and a model validator after `_date_range_is_ordered`:

```python
    certification_type: CertificationType | None = None
    certification_status: CertificationStatus | None = None
    certificate_number: str | None = Field(default=None, max_length=100)
    issued_on: date | None = None

    @field_validator("certificate_number")
    @classmethod
    def _clean_certificate_number(cls, value: str | None) -> str | None:
        return _clean_certificate_number(value)

    @model_validator(mode="after")
    def _skill_india_rules(self):
        if self.certification_type is not None and self.section != "certification":
            raise ValueError(CERT_TYPE_SECTION_ERROR)
        error = skill_india_error(self.certification_type, self.certification_status, self.certificate_number, self.issued_on)
        if error:
            raise ValueError(error)
        return self
```

`PortfolioEntryUpdate` — add (no `certification_type`: `extra="forbid"` makes it a 422, D8):

```python
    certification_status: CertificationStatus | None = None
    certificate_number: str | None = Field(default=None, max_length=100)
    issued_on: date | None = None

    @field_validator("certificate_number")
    @classmethod
    def _clean_certificate_number(cls, value: str | None) -> str | None:
        return _clean_certificate_number(value)
```

`PortfolioEntryOut` — add:

```python
    certification_type: str | None = None
    certification_status: str | None = None
    certificate_number: str | None = None
    issued_on: date | None = None
```

- [ ] **Step 4: Run — expect PASS.** API(`tests/test_enh_024_skill_india.py tests/test_enh_012_digital_portfolio.py`).

- [ ] **Step 5: Refactor check.** The module-level `_clean_certificate_number` and the two same-named classmethods: keep one module function, both validators call it (already so). Rerun Step 4.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/schemas.py apps/api/tests/test_enh_024_skill_india.py
git commit -m "feat(enh-024): Skill India fields and rules on the portfolio entry schemas"
```

---

### Task 3: Create, read (Portfolio + 360°), authorization, audit and logging

**Files:**
- Modify: `apps/api/app/api/portfolio.py` (`_entry_out`, `create_portfolio_entry`)
- Test: `apps/api/tests/test_enh_024_skill_india.py` (append)

**Interfaces:**
- Consumes: Task 1 columns; Task 2 `PortfolioEntryCreate` fields.
- Produces: `_entry_out(entry)` including the four fields; test helpers `_create(client, sid, **fields)`, `CERT`, `_cert_fields(body)`, `_app_loggers_enabled` fixture.

- [ ] **Step 1: Write the failing tests** (append):

```python
# --- Task 3: create + read ----------------------------------------------------------------------------------------

import json  # noqa: E402
import logging  # noqa: E402

CERT = {"certification_type": "skill_india", "certification_status": "enrolled", "certificate_number": "SI-2026-0001", "issued_on": None}
CERT_KEYS = ("certification_type", "certification_status", "certificate_number", "issued_on")


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    """Same order-proofing as test_enh_003: an in-process Alembic run disables existing `app.*` loggers."""
    logging.getLogger("app.portfolio").disabled = False
    yield


async def _create(client, sid, **fields):
    body = {"section": "certification", "title": "Retail Sales Associate", "organization": "Retailers Association's Skill Council of India", **CERT, **fields}
    return await client.post(ENTRIES.format(sid=sid), json=body)


def _cert_fields(body: dict) -> tuple:
    return tuple(body[k] for k in CERT_KEYS)


@pytest.mark.asyncio
async def test_coordinator_creates_a_skill_india_certification(client, db_session):  # AC-01
    ctx = await mk_school(db_session, label="E24-Create")
    await login(client, ctx["coordinator"].email)
    r = await _create(client, ctx["students"][0].id)
    assert r.status_code == 201, r.text
    assert _cert_fields(r.json()) == ("skill_india", "enrolled", "SI-2026-0001", None)
    assert r.json()["organization"] == "Retailers Association's Skill Council of India"


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", ["teacher", "academic_team"])
async def test_the_other_writers_can_create_too(client, db_session, writer):  # AC-01, D10
    ctx = await mk_school(db_session, label="E24-Writers")
    user = ctx["teacher"] if writer == "teacher" else await mk_staff(db_session, ctx["school"], ctx["admin"], role="academic_team")
    await login(client, user.email)
    assert (await _create(client, ctx["students"][0].id)).status_code == 201


@pytest.mark.asyncio
async def test_it_shows_on_portfolio_and_360_for_every_reader(client, db_session):  # AC-02
    ctx = await mk_school(db_session, label="E24-Read")
    sid = ctx["students"][0].id
    await login(client, ctx["coordinator"].email)
    created = (await _create(client, sid, certification_status="certified", issued_on="2026-05-01")).json()
    staff = [await mk_staff(db_session, ctx["school"], ctx["admin"], role=r) for r in ("academic_team", "career_counselor", "psychometric_team")]
    for reader in [ctx["coordinator"], ctx["teacher"], ctx["principal"], ctx["parent"], *staff]:
        await login(client, reader.email)
        portfolio = (await client.get(f"/api/v1/school/students/{sid}/portfolio")).json()
        view = (await client.get(f"/api/v1/school/students/{sid}/360-view")).json()
        [p] = portfolio["entries"]["certification"]
        [v] = view["tabs"]["certificates"]["data"]["entries"]
        assert p["id"] == v["id"] == created["id"], reader.role
        assert _cert_fields(p) == _cert_fields(v) == ("skill_india", "certified", "SI-2026-0001", "2026-05-01"), reader.role


@pytest.mark.asyncio
async def test_plain_certifications_and_completion_are_unchanged(client, db_session):  # AC-12
    ctx = await mk_school(db_session, label="E24-Plain", students=2)
    plain_kid, tagged_kid = ctx["students"]
    await login(client, ctx["coordinator"].email)
    plain = await client.post(ENTRIES.format(sid=plain_kid.id), json={"section": "certification", "title": "First aid"})
    assert plain.status_code == 201
    assert _cert_fields(plain.json()) == (None, None, None, None)
    assert (await _create(client, tagged_kid.id)).status_code == 201
    pct = [(await client.get(f"/api/v1/school/students/{k.id}/portfolio")).json()["completion_percentage"] for k in (plain_kid, tagged_kid)]
    assert pct[0] == pct[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["principal", "parent", "career_counselor", "psychometric_team"])
async def test_readers_who_are_not_writers_get_403(client, db_session, role):  # AC-06
    ctx = await mk_school(db_session, label="E24-NoWrite")
    user = ctx[role] if role in ctx else await mk_staff(db_session, ctx["school"], ctx["admin"], role=role)
    await login(client, user.email)
    assert (await _create(client, ctx["students"][0].id)).status_code == 403


@pytest.mark.asyncio
async def test_an_unassigned_teacher_gets_403(client, db_session):  # AC-06
    ctx = await mk_school(db_session, label="E24-Unassigned", students=2)
    await login(client, ctx["teacher"].email)
    assert (await _create(client, ctx["students"][1].id)).status_code == 403


@pytest.mark.asyncio
async def test_another_schools_coordinator_cannot_create(client, db_session):  # AC-06
    ctx = await mk_school(db_session, label="E24-Mine")
    other = await mk_school(db_session, label="E24-Other", admin=ctx["admin"])
    await login(client, other["coordinator"].email)
    r = await _create(client, ctx["students"][0].id)
    assert r.status_code in (403, 404)
    assert await db_session.scalar(select(PortfolioEntry).where(PortfolioEntry.school_student_id == ctx["students"][0].id)) is None


@pytest.mark.asyncio
async def test_below_gold_create_is_refused(client, db_session):  # AC-07
    ctx = await mk_school(db_session, label="E24-Silver", tier="silver")
    await login(client, ctx["coordinator"].email)
    r = await _create(client, ctx["students"][0].id)
    assert r.status_code == 403
    assert "Digital portfolio creation" in r.json()["detail"]


@pytest.mark.asyncio
async def test_create_audit_and_log_carry_the_tag_but_never_the_number(client, db_session, caplog):  # AC-11, D16
    ctx = await mk_school(db_session, label="E24-Audit")
    await login(client, ctx["coordinator"].email)
    with caplog.at_level(logging.INFO, logger="app.portfolio"):
        created = (await _create(client, ctx["students"][0].id)).json()
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.portfolio_entry_create", AuditLog.entity_id == created["id"]))
    assert row.metadata_json["certification_type"] == "skill_india"
    assert row.metadata_json["certification_status"] == "enrolled"
    assert "SI-2026-0001" not in json.dumps(row.metadata_json)
    records = [r for r in caplog.records if r.name == "app.portfolio"]
    assert any(getattr(r, "extra_fields", {}).get("certification_type") == "skill_india" for r in records)
    assert "SI-2026-0001" not in " ".join(r.getMessage() + json.dumps(getattr(r, "extra_fields", {}), default=str) for r in records)


@pytest.mark.asyncio
async def test_plain_entry_audit_metadata_is_exactly_as_before(client, db_session):  # AC-12
    ctx = await mk_school(db_session, label="E24-AuditPlain")
    await login(client, ctx["coordinator"].email)
    created = (await client.post(ENTRIES.format(sid=ctx["students"][0].id), json={"section": "project", "title": "Robot"})).json()
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.portfolio_entry_create", AuditLog.entity_id == created["id"]))
    assert set(row.metadata_json) == {"section", "school_student_id"}
```

- [ ] **Step 2: Run — expect FAIL.** API(`tests/test_enh_024_skill_india.py -k "create or shows or plain or 403 or refused or audit"`). Expected: 201 body lacks `certification_type` (`KeyError`), audit keys missing. Authorization tests may already pass (existing gates) — that is correct; they pin behaviour.

- [ ] **Step 3: Implement** in `portfolio.py`:

```python
def _entry_out(entry: PortfolioEntry) -> dict:
    return {
        "id": entry.id, "school_student_id": entry.school_student_id, "section": entry.section,
        "title": entry.title, "description": entry.description, "organization": entry.organization,
        "date_from": entry.date_from, "date_to": entry.date_to,
        "certification_type": entry.certification_type, "certification_status": entry.certification_status,
        "certificate_number": entry.certificate_number, "issued_on": entry.issued_on,
        "created_by_user_id": entry.created_by_user_id, "updated_by_user_id": entry.updated_by_user_id,
        "created_at": entry.created_at, "updated_at": entry.updated_at,
    }


def _cert_audit(entry: PortfolioEntry) -> dict:
    """ENH-024 D16: the tag (and, where given, status) for a Skill India entry's audit row; nothing for any other entry, so their
    audit rows stay exactly as before. Never the certificate number."""
    return {"certification_type": entry.certification_type} if entry.certification_type else {}
```

In `create_portfolio_entry`: pass the four fields to the constructor; audit and log:

```python
    entry = PortfolioEntry(
        school_student_id=student.id, section=payload.section, title=payload.title,
        description=payload.description, organization=payload.organization,
        date_from=payload.date_from, date_to=payload.date_to,
        certification_type=payload.certification_type, certification_status=payload.certification_status,
        certificate_number=payload.certificate_number, issued_on=payload.issued_on,
        created_by_user_id=user.id, updated_by_user_id=user.id,
    )
    ...
    audit = {"section": entry.section, "school_student_id": str(student.id), **_cert_audit(entry)}
    if entry.certification_type:
        audit["certification_status"] = entry.certification_status
    db.add(AuditLog(..., metadata_json=audit))
    ...
    logger.info("portfolio_entry_create", extra={"extra_fields": {"actor_id": ..., "student_id": ..., "entry_id": ..., "section": entry.section, **_cert_audit(entry)}})
```

- [ ] **Step 4: Run — expect PASS.** API(`tests/test_enh_024_skill_india.py tests/test_enh_012_digital_portfolio.py tests/test_enh_013_refactor.py tests/test_enh_013_360_view.py`).

- [ ] **Step 5: Refactor.** Fold the `certification_status` audit addition into `_cert_audit` only if it reads more simply; the log line must still carry the tag only (status in logs is fine; number never). Rerun Step 4.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/portfolio.py apps/api/tests/test_enh_024_skill_india.py
git commit -m "feat(enh-024): create and read Skill India certifications on the portfolio and 360 view"
```

---

### Task 4: Update (merge + rules + row lock), delete audit, transaction failure

**Files:**
- Modify: `apps/api/app/api/portfolio.py` (`_load_portfolio_entry`, `update_portfolio_entry`, `delete_portfolio_entry`)
- Test: `apps/api/tests/test_enh_024_skill_india.py` (append)

**Interfaces:**
- Consumes: Task 2 `skill_india_error`, `CERT_*`; Task 3 `_cert_audit`, `_create`.
- Produces: `_load_portfolio_entry(db, student_id, entry_id, *, lock: bool = False) -> PortfolioEntry`.

- [ ] **Step 1: Write the failing tests** (append):

```python
# --- Task 4: update + delete --------------------------------------------------------------------------------------

from app.api import portfolio as portfolio_api  # noqa: E402


async def _entry(entry_id) -> PortfolioEntry:
    async with SessionLocal() as s:
        return await s.get(PortfolioEntry, UUID(entry_id))


async def _setup(client, db_session, label, **fields):
    ctx = await mk_school(db_session, label=label)
    sid = ctx["students"][0].id
    await login(client, ctx["coordinator"].email)
    created = await _create(client, sid, **fields)
    assert created.status_code == 201, created.text
    return ctx, sid, created.json()


@pytest.mark.asyncio
async def test_patch_moves_to_certified_and_audits_the_transition(client, db_session):  # AC-03, AC-11
    ctx, sid, e = await _setup(client, db_session, "E24-Patch")
    r = await client.patch(ENTRY.format(sid=sid, eid=e["id"]), json={"certification_status": "certified", "issued_on": "2026-06-30"})
    assert r.status_code == 200, r.text
    assert _cert_fields(r.json()) == ("skill_india", "certified", "SI-2026-0001", "2026-06-30")
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.portfolio_entry_update", AuditLog.entity_id == e["id"]))
    assert (row.metadata_json["old_status"], row.metadata_json["new_status"]) == ("enrolled", "certified")
    assert "SI-2026-0001" not in json.dumps(row.metadata_json)


@pytest.mark.asyncio
async def test_status_can_move_back_and_title_only_edits_keep_details(client, db_session):  # D5, AC-03
    ctx, sid, e = await _setup(client, db_session, "E24-Back", certification_status="certified", issued_on="2026-05-01")
    url = ENTRY.format(sid=sid, eid=e["id"])
    assert (await client.patch(url, json={"certification_status": "in_progress"})).status_code == 200
    r = await client.patch(url, json={"title": "Retail Sales Associate (Level 4)"})
    assert r.status_code == 200
    assert _cert_fields(r.json()) == ("skill_india", "in_progress", "SI-2026-0001", "2026-05-01")


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "patch", "message"), [
    ({}, {"certification_status": None}, CERT_STATUS_REQUIRED_ERROR),
    ({"certification_status": "certified", "issued_on": "2026-05-01"}, {"certificate_number": None}, CERT_CERTIFIED_ERROR),
    ({"certification_status": "certified", "issued_on": "2026-05-01"}, {"issued_on": None}, CERT_CERTIFIED_ERROR),
    ({"certificate_number": None}, {"certification_status": "certified", "issued_on": "2026-05-01"}, CERT_CERTIFIED_ERROR),
])
async def test_patch_rules_apply_to_the_merged_entry(client, db_session, start, patch, message):  # AC-03, AC-04
    ctx, sid, e = await _setup(client, db_session, "E24-Merge", **start)
    r = await client.patch(ENTRY.format(sid=sid, eid=e["id"]), json=patch)
    assert (r.status_code, r.json()["detail"]) == (422, message)
    assert _cert_fields(_entry_out_like(await _entry(e["id"]))) == _cert_fields(e)  # nothing written


def _entry_out_like(row: PortfolioEntry) -> dict:
    return {"certification_type": row.certification_type, "certification_status": row.certification_status,
            "certificate_number": row.certificate_number, "issued_on": row.issued_on.isoformat() if row.issued_on else None}


@pytest.mark.asyncio
async def test_untagged_entry_refuses_details_but_accepts_nulls(client, db_session):  # D3, Review Focus 2
    ctx = await mk_school(db_session, label="E24-Untagged")
    sid = ctx["students"][0].id
    await login(client, ctx["coordinator"].email)
    e = (await client.post(ENTRIES.format(sid=sid), json={"section": "certification", "title": "First aid"})).json()
    url = ENTRY.format(sid=sid, eid=e["id"])
    r = await client.patch(url, json={"certification_status": "enrolled"})
    assert (r.status_code, r.json()["detail"]) == (422, CERT_FIELDS_UNTAGGED_ERROR)
    ok = await client.patch(url, json={"title": "First aid (renewed)", "certification_status": None, "certificate_number": None, "issued_on": None})
    assert ok.status_code == 200
    assert _cert_fields(ok.json()) == (None, None, None, None)


@pytest.mark.asyncio
async def test_the_tag_cannot_be_changed_by_patch(client, db_session):  # AC-05
    ctx, sid, e = await _setup(client, db_session, "E24-Tag")
    r = await client.patch(ENTRY.format(sid=sid, eid=e["id"]), json={"certification_type": None})
    assert r.status_code == 422
    assert (await _entry(e["id"])).certification_type == "skill_india"


@pytest.mark.asyncio
async def test_another_students_entry_is_404(client, db_session):  # AC-06 (IDOR)
    ctx = await mk_school(db_session, label="E24-IDOR", students=2)
    mine, other = ctx["students"]
    await login(client, ctx["coordinator"].email)
    e = (await _create(client, other.id)).json()
    r = await client.patch(ENTRY.format(sid=mine.id, eid=e["id"]), json={"certification_status": "in_progress"})
    assert r.status_code == 404
    assert (await _entry(e["id"])).certification_status == "enrolled"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["principal", "parent"])
async def test_non_writers_cannot_patch_or_delete(client, db_session, role):  # AC-06
    ctx, sid, e = await _setup(client, db_session, "E24-NoPatch")
    await login(client, ctx[role].email)
    assert (await client.patch(ENTRY.format(sid=sid, eid=e["id"]), json={"certification_status": "in_progress"})).status_code == 403
    assert (await client.delete(ENTRY.format(sid=sid, eid=e["id"]))).status_code == 403


@pytest.mark.asyncio
async def test_after_a_downgrade_existing_certificates_stay_editable_but_new_ones_are_refused(client, db_session):  # AC-07, Review Focus 3
    ctx, sid, e = await _setup(client, db_session, "E24-Downgrade")
    await login(client, ctx["admin"].email)
    assert (await client.patch(f"/api/v1/overseas-admin/schools/{ctx['school'].id}", json={"tier": "silver"})).status_code == 200
    await login(client, ctx["coordinator"].email)
    assert (await client.patch(ENTRY.format(sid=sid, eid=e["id"]), json={"certification_status": "in_progress"})).status_code == 200
    assert (await _create(client, sid)).status_code == 403
    assert (await client.delete(ENTRY.format(sid=sid, eid=e["id"]))).status_code == 204


@pytest.mark.asyncio
async def test_a_concurrent_edit_is_validated_against_its_committed_result(client, db_session):  # AC-08, Review Focus 1
    ctx, sid, e = await _setup(client, db_session, "E24-Race", issued_on="2026-05-01")
    other = SessionLocal()
    try:
        # Stand-in for a second editor's PATCH: hold the entry's row lock, clear the number, commit.
        await other.execute(select(PortfolioEntry).where(PortfolioEntry.id == UUID(e["id"])).with_for_update())
        pending = asyncio.create_task(client.patch(ENTRY.format(sid=sid, eid=e["id"]), json={"certification_status": "certified"}))
        await asyncio.sleep(0.5)
        assert not pending.done()  # queued on the row lock
        await other.execute(update(PortfolioEntry).where(PortfolioEntry.id == UUID(e["id"])).values(certificate_number=None))
        await other.commit()
    finally:
        await other.close()
    r = await pending
    assert (r.status_code, r.json()["detail"]) == (422, CERT_CERTIFIED_ERROR)
    row = await _entry(e["id"])
    assert (row.certification_status, row.certificate_number) == ("enrolled", None)


@pytest.mark.asyncio
async def test_a_failed_commit_writes_nothing(client, db_session, monkeypatch):  # transaction failure
    ctx, sid, e = await _setup(client, db_session, "E24-TxFail")
    real = portfolio_api.AuditLog
    monkeypatch.setattr(portfolio_api, "AuditLog", lambda **kw: real(**{**kw, "user_id": uuid.uuid4()}))  # FK violation at commit
    with pytest.raises(IntegrityError):
        await client.patch(ENTRY.format(sid=sid, eid=e["id"]), json={"certification_status": "in_progress"})
    assert (await _entry(e["id"])).certification_status == "enrolled"


@pytest.mark.asyncio
async def test_delete_audit_records_the_tag(client, db_session):  # AC-11
    ctx, sid, e = await _setup(client, db_session, "E24-Delete")
    assert (await client.delete(ENTRY.format(sid=sid, eid=e["id"]))).status_code == 204
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.portfolio_entry_delete", AuditLog.entity_id == e["id"]))
    assert row.metadata_json["certification_type"] == "skill_india"
    assert "SI-2026-0001" not in json.dumps(row.metadata_json)
```

- [ ] **Step 2: Run — expect FAIL.** API(`tests/test_enh_024_skill_india.py -k "patch or untagged or tag_cannot or 404 or downgrade or concurrent or failed or delete"`). Expected: PATCH ignores the new fields (200 with unchanged values / missing audit keys); the race test raises `IntegrityError` (the CHECK fires because the unlocked read validated stale data) — the expected reason.

- [ ] **Step 3: Implement** in `portfolio.py` (import `skill_india_error` from `app.schemas`):

```python
async def _load_portfolio_entry(db: AsyncSession, student_id: UUID, entry_id: UUID, *, lock: bool = False) -> PortfolioEntry:
    if lock:
        # ENH-024 spec §5: a PATCH validates its merge against the stored row, so two concurrent PATCHes must not both read the
        # same version -- each would pass alone and together break a CHECK (500). One row; transfers never lock entries.
        entry = await db.scalar(select(PortfolioEntry).where(PortfolioEntry.id == entry_id).with_for_update().execution_options(populate_existing=True))
    else:
        entry = await db.get(PortfolioEntry, entry_id)
    if not entry or entry.school_student_id != student_id:
        raise HTTPException(404, "Portfolio entry not found")
    return entry
```

`update_portfolio_entry`:

```python
    entry = await _load_portfolio_entry(db, student.id, entry_id, lock=True)
    await require_school_entitlement(db, user, student.school_id, "digital_portfolio_creation", grandfathered_since=entry.created_at)
    old_status = entry.certification_status
    fields_set = payload.model_fields_set
    for field in ("title", "description", "organization", "date_from", "date_to", "certification_status", "certificate_number", "issued_on"):
        if field in fields_set:
            setattr(entry, field, getattr(payload, field))
    if date_range_is_invalid(entry.date_from, entry.date_to):
        raise HTTPException(422, DATE_RANGE_ERROR)
    # ENH-024: the same rule as a create, on the merged state (the tag itself is never in the payload -- D8).
    cert_error = skill_india_error(entry.certification_type, entry.certification_status, entry.certificate_number, entry.issued_on)
    if cert_error:
        raise HTTPException(422, cert_error)
    entry.updated_by_user_id = user.id
    await db.flush()
    audit = {"section": entry.section, "school_student_id": str(student.id), **_cert_audit(entry)}
    if entry.certification_status != old_status:
        audit.update(old_status=old_status, new_status=entry.certification_status)
    db.add(AuditLog(user_id=user.id, action="school.portfolio_entry_update", entity_type="portfolio_entry", entity_id=str(entry.id), metadata_json=audit))
    await db.commit()
    await db.refresh(entry)
    logger.info("portfolio_entry_update", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id), "entry_id": str(entry.id), **_cert_audit(entry)}})
    return entry
```

(Keep the existing comments on the merge loop and date check.) `delete_portfolio_entry`: capture `cert = _cert_audit(entry)` before `db.delete`, and use `metadata_json={"section": section, "school_student_id": str(student.id), **cert}`; add `**cert` to its log `extra_fields`.

- [ ] **Step 4: Run — expect PASS.** API(`tests/test_enh_024_skill_india.py tests/test_enh_012_digital_portfolio.py tests/test_enh_022_tier_enforcement.py tests/test_enh_023_tier_change.py`).

- [ ] **Step 5: Refactor.** Build the update/create/delete audit dict through one small helper only if three call sites read identically; otherwise leave inline. Rerun Step 4.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/portfolio.py apps/api/tests/test_enh_024_skill_india.py
git commit -m "feat(enh-024): edit Skill India details under a row lock; audit status changes"
```

---

### Task 5: `CertificationDetails` and its display on the Portfolio and 360°

**Files:**
- Create: `apps/web/components/CertificationDetails.tsx`
- Create: `apps/web/tests/components/CertificationDetails.test.tsx`
- Modify: `apps/web/lib/portfolio.ts` (`PortfolioEntry` type)
- Modify: `apps/web/components/PortfolioPanel.tsx:70-78` (render details; pass fields to edit `initial`)
- Modify: `apps/web/components/Student360Panels.tsx:14,44-55` (`Entry` type, `Entries`)
- Modify: `apps/web/app/globals.css` (after `.pf-statement`)
- Modify: `apps/web/tests/components/PortfolioPanel.test.tsx`, `apps/web/tests/components/Student360Panels.test.tsx` (append cases only)
- Modify: spec §6 (record the `StatusChip` deviation)

**Interfaces:**
- Produces: `export type CertificationFields = { certification_type?: string | null; certification_status?: string | null; certificate_number?: string | null; issued_on?: string | null }`; `export const CERT_STATUS_LABEL: Record<string, string>`; `export default function CertificationDetails({ entry }: { entry: CertificationFields })`.

- [ ] **Step 1: Write the failing tests** — `apps/web/tests/components/CertificationDetails.test.tsx`:

```tsx
import { readFileSync } from "node:fs";
import path from "node:path";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import CertificationDetails from "@/components/CertificationDetails";

afterEach(cleanup);

describe("CertificationDetails", () => {
  it("renders nothing for an entry that is not Skill India", () => {
    const { container } = render(<CertificationDetails entry={{ certification_type: null, certification_status: null, certificate_number: null, issued_on: null }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the badge, status as text, certificate number and issue date", () => {
    render(<CertificationDetails entry={{ certification_type: "skill_india", certification_status: "certified", certificate_number: "SI-2026-0001", issued_on: "2026-05-01" }} />);
    expect(screen.getByText("Skill India")).toHaveClass("badge");
    expect(screen.getByText("Certified")).toHaveClass("status");
    expect(screen.getByText("Certificate no. SI-2026-0001")).toBeInTheDocument();
    expect(screen.getByText(/^Issued /)).toBeInTheDocument();
  });

  it("marks a not-yet-certified status as pending, still in words", () => {
    render(<CertificationDetails entry={{ certification_type: "skill_india", certification_status: "in_progress", certificate_number: null, issued_on: null }} />);
    expect(screen.getByText("In progress")).toHaveClass("status", "pending");
    expect(screen.queryByText(/Certificate no\./)).not.toBeInTheDocument();
  });

  it("is safe inside client components (no server-only import, directly)", () => {
    const source = readFileSync(path.resolve(__dirname, "../../components/CertificationDetails.tsx"), "utf8");
    expect(source).not.toMatch(/@\/components\/SchoolChildOverview|@\/lib\/api|next\/headers/);
  });
});
```

Append to `Student360Panels.test.tsx` (inside the existing `describe`):

```tsx
  it("shows Skill India details on the Certificates tab (ENH-024)", () => {
    const entry = { id: "c1", title: "Retail Sales Associate", organization: "RASCI", date_from: null, date_to: null, description: null, certification_type: "skill_india", certification_status: "enrolled", certificate_number: "SI-1", issued_on: null };
    const tab: Tab360 = { status: "has_data", count: 1, not_tracked: [], data: { entries: [entry] } };
    render(<>{renderPanel("certificates", tab, view())}</>);
    expect(screen.getByText("Skill India")).toBeInTheDocument();
    expect(screen.getByText("Enrolled")).toBeInTheDocument();
    expect(screen.getByText("Certificate no. SI-1")).toBeInTheDocument();
  });
```

Append to `PortfolioPanel.test.tsx` a case that renders the panel with one Skill India certification entry (build the `PortfolioData` the same way the file's existing cases do) and asserts `Skill India`, `Certified`, `Certificate no. SI-1` are shown, then clicks `Edit Retail Sales Associate` and asserts the Status select has value `certified` (the latter passes only after Task 6; mark it `it.todo` here and convert in Task 6 Step 1).

- [ ] **Step 2: Run — expect FAIL.** WEB(`tests/components/CertificationDetails.test.tsx tests/components/Student360Panels.test.tsx tests/components/PortfolioPanel.test.tsx`). Expected: "Failed to resolve import @/components/CertificationDetails"; the new 360/Portfolio cases fail on missing text.

- [ ] **Step 3: Implement** `apps/web/components/CertificationDetails.tsx`:

```tsx
import { formatCalendarDate } from "@/lib/formatDate";

// ENH-024 -- a Skill India certification's details (docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md §6).
// Hook-free, so the client PortfolioPanel and the server 360° panels share it; renders nothing for every other entry. Status is a
// text label plus the shared `.status` / `.status pending` classes (lib/skills.ts's convention) -- not StatusChip, whose module
// imports serverApi and would break a client component's build.

export type CertificationFields = { certification_type?: string | null; certification_status?: string | null; certificate_number?: string | null; issued_on?: string | null };

export const CERT_STATUS_LABEL: Record<string, string> = { enrolled: "Enrolled", in_progress: "In progress", certified: "Certified" };

export default function CertificationDetails({ entry }: { entry: CertificationFields }) {
  if (entry.certification_type !== "skill_india") return null;
  const status = entry.certification_status;
  return (
    <div className="pf-cert">
      <span className="badge">Skill India</span>
      {status ? <span className={status === "certified" ? "status" : "status pending"}>{CERT_STATUS_LABEL[status] ?? status}</span> : null}
      {entry.certificate_number ? <span className="muted">Certificate no. {entry.certificate_number}</span> : null}
      {entry.issued_on ? <span className="muted">Issued {formatCalendarDate(entry.issued_on)}</span> : null}
    </div>
  );
}
```

`lib/portfolio.ts`: extend the type:

```ts
export type PortfolioEntry = { id: string; section: string; title: string; description: string | null; organization: string | null; date_from: string | null; date_to: string | null; certification_type: string | null; certification_status: string | null; certificate_number: string | null; issued_on: string | null; created_at: string; updated_at: string };
```

`PortfolioPanel.tsx` (read view, after the date span; import `CertificationDetails`):

```tsx
                    {e.date_from && <span className="pf-entry-date"> ({formatCalendarDate(e.date_from)}{e.date_to ? ` – ${formatCalendarDate(e.date_to)}` : ""})</span>}
                    <CertificationDetails entry={e} />
```

`Student360Panels.tsx`:

```tsx
import CertificationDetails, { type CertificationFields } from "@/components/CertificationDetails";
type Entry = { id: string; title: string; organization: string | null; date_from: string | null; date_to: string | null; description: string | null } & CertificationFields;
// in Entries, after the date span:
          <CertificationDetails entry={e} />
```

`globals.css` (after `.pf-statement`):

```css
.pf-cert { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-top: 0.25rem; overflow-wrap: anywhere; }
```

Spec §6: replace "`StatusChip` (already labels …)" in the reuse list with "the `.status` / `.status pending` classes (not `StatusChip`: its module imports `serverApi`, which a client component must not reach even transitively)".

- [ ] **Step 4: Run — expect PASS.** WEB(`tests/components/CertificationDetails.test.tsx tests/components/Student360Panels.test.tsx tests/components/PortfolioPanel.test.tsx tests/lib/clientBoundary.test.ts`).

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/CertificationDetails.tsx apps/web/tests/components/CertificationDetails.test.tsx apps/web/lib/portfolio.ts apps/web/components/PortfolioPanel.tsx apps/web/components/Student360Panels.tsx apps/web/app/globals.css apps/web/tests/components/PortfolioPanel.test.tsx apps/web/tests/components/Student360Panels.test.tsx docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md
git commit -m "feat(enh-024): show Skill India details on the portfolio and 360 certificates"
```

---

### Task 6: Skill India capture in `PortfolioEntryForm`

**Files:**
- Modify: `apps/web/components/PortfolioEntryForm.tsx`
- Modify: `apps/web/components/PortfolioPanel.tsx:71` (edit `initial` carries the four fields)
- Test: `apps/web/tests/components/PortfolioEntryForm.test.tsx` (append), `PortfolioPanel.test.tsx` (convert the Task 5 `it.todo`)

**Interfaces:**
- Consumes: Task 5 `CertificationFields`, `CERT_STATUS_LABEL`.
- Produces: `initial?: { title; description; organization; date_from; date_to } & CertificationFields` prop.

- [ ] **Step 1: Write the failing tests** (append to `PortfolioEntryForm.test.tsx`):

```tsx
describe("PortfolioEntryForm — Skill India (ENH-024)", () => {
  const ok = () => vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "e1" }) });
  const bodyOf = (m: ReturnType<typeof vi.fn>) => JSON.parse(m.mock.calls[0][1].body as string);

  it("offers the Skill India checkbox only when adding a certification", () => {
    const { unmount } = render(<PortfolioEntryForm studentId="s1" section="award" onDone={() => {}} onCancel={() => {}} />);
    expect(screen.queryByLabelText(/skill india certification/i)).not.toBeInTheDocument();
    unmount();
    render(<PortfolioEntryForm studentId="s1" section="certification" onDone={() => {}} onCancel={() => {}} />);
    expect(screen.getByRole("checkbox", { name: /skill india certification/i })).not.toBeChecked();
    expect(screen.queryByRole("group", { name: /skill india details/i })).not.toBeInTheDocument();
  });

  it("reveals the details fieldset and relabels Organization as Issuing body", () => {
    render(<PortfolioEntryForm studentId="s1" section="certification" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /skill india certification/i }));
    const group = screen.getByRole("group", { name: /skill india details/i });
    expect(within(group).getByLabelText(/status/i)).toHaveValue("");
    expect(within(group).getByLabelText(/certificate number/i)).toHaveAccessibleDescription(/required once certified/i);
    expect(within(group).getByLabelText(/issue date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/issuing body/i)).toBeInTheDocument();
  });

  it("requires a status, and a number and issue date once certified, focusing the first problem", async () => {
    const fetchMock = ok();
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="certification" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "Retail Sales Associate" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /skill india certification/i }));
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText("Choose a status.")).toBeInTheDocument();
    expect(screen.getByLabelText(/status/i)).toHaveAttribute("aria-invalid", "true");
    await waitFor(() => expect(screen.getByLabelText(/status/i)).toHaveFocus());
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: "certified" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText("Enter the certificate number.")).toBeInTheDocument();
    expect(screen.getByText("Enter the issue date.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText(/certificate number/i)).toHaveFocus());
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("POSTs the tag and details when ticked", async () => {
    const fetchMock = ok();
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="certification" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "Retail Sales Associate" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /skill india certification/i }));
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: "certified" } });
    fireEvent.change(screen.getByLabelText(/certificate number/i), { target: { value: " SI-9 " } });
    fireEvent.change(screen.getByLabelText(/issue date/i), { target: { value: "2026-05-01" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(bodyOf(fetchMock)).toMatchObject({ section: "certification", certification_type: "skill_india", certification_status: "certified", certificate_number: "SI-9", issued_on: "2026-05-01" });
  });

  it("sends no Skill India fields when unticked again", async () => {
    const fetchMock = ok();
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="certification" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "First aid" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /skill india certification/i }));
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: "enrolled" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /skill india certification/i }));
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = bodyOf(fetchMock);
    for (const key of ["certification_type", "certification_status", "certificate_number", "issued_on"]) expect(body).not.toHaveProperty(key);
  });

  it("edits a tagged entry without a checkbox and never PATCHes the tag", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "e1" }) });
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="certification" entryId="e1" initial={{ title: "Retail", description: null, organization: null, date_from: null, date_to: null, certification_type: "skill_india", certification_status: "enrolled", certificate_number: null, issued_on: null }} onDone={() => {}} onCancel={() => {}} />);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText("Skill India certification")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: "in_progress" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = bodyOf(fetchMock);
    expect(body).not.toHaveProperty("certification_type");
    expect(body.certification_status).toBe("in_progress");
  });

  it("disables the Skill India fields while saving", async () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="certification" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "Retail" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /skill india certification/i }));
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: "enrolled" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByRole("button", { name: /saving/i })).toBeDisabled();
    expect(screen.getByLabelText(/status/i)).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /skill india certification/i })).toBeDisabled();
  });
});
```

(Add `within` to the file's existing `@testing-library/react` import.) Convert the Task 5 `it.todo` in `PortfolioPanel.test.tsx` into the real edit-prefill assertion.

- [ ] **Step 2: Run — expect FAIL.** WEB(`tests/components/PortfolioEntryForm.test.tsx tests/components/PortfolioPanel.test.tsx`). Expected: no checkbox found.

- [ ] **Step 3: Implement** in `PortfolioEntryForm.tsx` (import `{ CERT_STATUS_LABEL, type CertificationFields } from "@/components/CertificationDetails"`):

```tsx
type CertErrors = { status?: string; number?: string; issued?: string };

// props: initial?: { title: string; description: string | null; organization: string | null; date_from: string | null; date_to: string | null } & CertificationFields;

  const [skillIndia, setSkillIndia] = useState(initial?.certification_type === "skill_india");
  const [certStatus, setCertStatus] = useState(initial?.certification_status ?? "");
  const [certNumber, setCertNumber] = useState(initial?.certificate_number ?? "");
  const [issuedOn, setIssuedOn] = useState(initial?.issued_on ?? "");
  const [certErrors, setCertErrors] = useState<CertErrors>({});
  const offerSkillIndia = !entryId && section === "certification";

  // ENH-024 D6, mirrored for a fast answer; the server stays authoritative.
  function checkCertification(): CertErrors {
    if (!skillIndia) return {};
    const errors: CertErrors = {};
    if (!certStatus) errors.status = "Choose a status.";
    if (certStatus === "certified" && !certNumber.trim()) errors.number = "Enter the certificate number.";
    if (certStatus === "certified" && !issuedOn) errors.issued = "Enter the issue date.";
    return errors;
  }
```

In `submit`, replace the title-only check with:

```tsx
    const titleError = title.trim() ? null : "Enter a title.";
    const errors = checkCertification();
    setFieldError(titleError);
    setCertErrors(errors);
    const firstInvalid = titleError ? "pf-title" : errors.status ? "pf-cert-status" : errors.number ? "pf-cert-number" : errors.issued ? "pf-cert-issued" : null;
    if (firstInvalid) {
      refocus(firstInvalid);
      return;
    }
```

and build the body:

```tsx
    const certification = skillIndia
      ? { ...(entryId ? {} : { certification_type: "skill_india" }), certification_status: certStatus, certificate_number: certNumber.trim() || null, issued_on: issuedOn || null }
      : {};
    const body = { ...(entryId ? {} : { section }), title: title.trim(), description: description.trim() || null, organization: organization.trim() || null, date_from: dateFrom || null, date_to: dateTo || null, ...certification };
```

Markup — after the Title field:

```tsx
      {offerSkillIndia && (
        <div className="field">
          <label htmlFor="pf-skill-india">
            <input id="pf-skill-india" type="checkbox" checked={skillIndia} disabled={busy} onChange={(e) => setSkillIndia(e.target.checked)} /> Skill India certification
          </label>
        </div>
      )}
      {entryId && skillIndia && <p className="muted">Skill India certification</p>}
```

Organization label: `{skillIndia ? "Issuing body (optional)" : "Organization (optional)"}`. After the dates:

```tsx
      {skillIndia && (
        <fieldset className="field">
          <legend>Skill India details</legend>
          <div className="field">
            <label htmlFor="pf-cert-status">Status</label>
            <select id="pf-cert-status" className="search" value={certStatus} disabled={busy} aria-invalid={certErrors.status ? true : undefined} aria-describedby={certErrors.status ? "pf-cert-status-error" : undefined} onChange={(e) => setCertStatus(e.target.value)}>
              <option value="">Choose status</option>
              {Object.entries(CERT_STATUS_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            {certErrors.status && <span id="pf-cert-status-error" className="form-error">{certErrors.status}</span>}
          </div>
          <div className="field">
            <label htmlFor="pf-cert-number">Certificate number</label>
            <input id="pf-cert-number" className="search" maxLength={100} value={certNumber} disabled={busy} aria-invalid={certErrors.number ? true : undefined} aria-describedby={certErrors.number ? "pf-cert-number-hint pf-cert-number-error" : "pf-cert-number-hint"} onChange={(e) => setCertNumber(e.target.value)} />
            <span id="pf-cert-number-hint" className="muted">Required once certified.</span>
            {certErrors.number && <span id="pf-cert-number-error" className="form-error">{certErrors.number}</span>}
          </div>
          <div className="field">
            <label htmlFor="pf-cert-issued">Issue date</label>
            <input id="pf-cert-issued" type="date" className="search" value={issuedOn} disabled={busy} aria-invalid={certErrors.issued ? true : undefined} aria-describedby={certErrors.issued ? "pf-cert-issued-hint pf-cert-issued-error" : "pf-cert-issued-hint"} onChange={(e) => setIssuedOn(e.target.value)} />
            <span id="pf-cert-issued-hint" className="muted">Required once certified.</span>
            {certErrors.issued && <span id="pf-cert-issued-error" className="form-error">{certErrors.issued}</span>}
          </div>
        </fieldset>
      )}
```

`PortfolioPanel.tsx` edit form `initial`: add `certification_type: e.certification_type, certification_status: e.certification_status, certificate_number: e.certificate_number, issued_on: e.issued_on`.

- [ ] **Step 4: Run — expect PASS.** WEB(`tests/components/PortfolioEntryForm.test.tsx tests/components/PortfolioPanel.test.tsx tests/lib/clientBoundary.test.ts`), then the full WEB(`` ``) unit suite.

- [ ] **Step 5: Refactor.** The three field blocks share a shape; extract nothing unless a fourth appears (YAGNI). Check the component is still under ~200 lines of JSX logic; rerun Step 4.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/PortfolioEntryForm.tsx apps/web/components/PortfolioPanel.tsx apps/web/tests/components/PortfolioEntryForm.test.tsx apps/web/tests/components/PortfolioPanel.test.tsx
git commit -m "feat(enh-024): capture Skill India details in the portfolio entry form"
```

---

### Task 7: Playwright end-to-end

**Files:**
- Create: `apps/web/tests/e2e/enh-024-skill-india-certification.spec.ts`

**Interfaces:**
- Consumes: the whole feature; `E2E_PASSWORD`, `createAndActivateFromUi` from `./helpers/welcome`.

Needs the full app stack of **this** worktree (user starts it: `docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh024 --profile ci up -d --build --wait postgres redis api web` with `API_PORT=8024` / `WEB_PORT=3024` so it does not clash with the running `enh021-026` stack), then seed as `scripts/ci-local.ps1` step 14 does.

- [ ] **Step 1: Write the spec.** Setup = `enh-012-digital-portfolio.spec.ts` lines 9–72 (admin creates a Platinum school + coordinator; coordinator invites the assigned teacher, creates the student, invites and links the parent), with `enh012` → `enh024` in every email/name. Then:

```ts
  // --- Coordinator: add a Skill India certification (enrolled), then certify it (AC-01, AC-03, AC-13).
  await page.goto("/school/coordinator/students");
  await page.locator("tr", { hasText: "Portfolio Test Child" }).getByRole("link", { name: "Timeline" }).click();
  await page.getByRole("button", { name: "Add certification" }).click();
  await page.fill("#pf-title", "Retail Sales Associate");
  await page.getByRole("checkbox", { name: "Skill India certification" }).check();
  await page.fill("#pf-organization", "Retailers Association's Skill Council of India");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Choose a status.")).toBeVisible();
  await expect(page.locator("#pf-cert-status")).toBeFocused();
  await page.selectOption("#pf-cert-status", "enrolled");
  await page.getByRole("button", { name: "Save" }).click();
  const card = page.locator(".pf-entry", { hasText: "Retail Sales Associate" });
  await expect(card.getByText("Skill India")).toBeVisible();
  await expect(card.getByText("Enrolled")).toBeVisible();

  await card.getByRole("button", { name: "Edit Retail Sales Associate" }).click();
  await page.selectOption("#pf-cert-status", "certified");
  await page.fill("#pf-cert-number", "SI-2026-0001");
  await page.fill("#pf-cert-issued", "2026-05-01");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(card.getByText("Certified")).toBeVisible();
  await expect(card.getByText("Certificate no. SI-2026-0001")).toBeVisible();

  // --- 360°: Certificates tab shows the same details (AC-02, AC-14).
  await page.goto(`/school/coordinator/students/${student.id}/360?tab=certificates`);
  await expect(page.getByText("Certificate no. SI-2026-0001")).toBeVisible();

  // --- Mobile width: details wrap, no horizontal scroll (AC-14).
  await page.setViewportSize({ width: 320, height: 720 });
  await expect(page.getByText("Skill India").first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });

  // --- Parent: sees it read-only (AC-02).
  // (log in as the parent exactly as enh-012 lines 89-99 do)
  await expect(page.locator(".pf-entry", { hasText: "Retail Sales Associate" }).getByText("Certified")).toBeVisible();
  await expect(page.locator(".pf-panel").getByRole("button", { name: /add|edit|delete/i })).toHaveCount(0);
```

Verify the 360° URL's tab query parameter against `lib/student360Links.ts` before running (adjust `?tab=certificates` to its real form).

- [ ] **Step 2: Run — expect FAIL before Tasks 5–6 are deployed to the stack** (if run against an image built before them), PASS after. Run: `... run --rm --no-deps -e CI=true -e E2E_BASE_URL=http://localhost:3000 -e PLAYWRIGHT_PROXY_TARGET=http://web:3000 web-test npx playwright test tests/e2e/enh-024-skill-india-certification.spec.ts --workers=1`.

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/enh-024-skill-india-certification.spec.ts
git commit -m "test(enh-024): end-to-end Skill India certification flow"
```

---

### Task 8: Regression, quality gates, traceability (no completion claim)

**Files:**
- Modify: `docs/quality/RTM.md` (ENH-024 row), `docs/delivery/ENHANCEMENT_BACKLOG.md` (§ENH-024 status line)
- Refresh: `graphify-out/` (`graphify update .`)

- [ ] **Step 1: Backend regression.** API(`tests/test_enh_012_digital_portfolio.py tests/test_enh_013_360_view.py tests/test_enh_013_refactor.py tests/test_enh_013_career_goal.py tests/test_enh_013_migration.py tests/test_enh_022_tier_enforcement.py tests/test_enh_022_tier_rules.py tests/test_enh_023_tier_change.py tests/test_enh_024_skill_india.py`) — all PASS, no existing test edited.
- [ ] **Step 2: Static gates.** `ruff format --check app tests`, `ruff check .`, `mypy app` (api-test); `npm run lint`, `npm run typecheck` (web-test); `alembic check` (no drift).
- [ ] **Step 3: Frontend unit suite.** WEB(``) full run — PASS.
- [ ] **Step 4: E2E regression.** `enh-012`, `enh-013`, `enh-022`, `enh-023`, `enh-024` specs — PASS.
- [ ] **Step 5: Traceability.** Add the ENH-024 row to `docs/quality/RTM.md` in the existing ENH row format (Evidence: brochure p.2 → `DEC-SCOPE-031` → spec → AC-01…AC-14 → test ids → commits), including the Task 1 Step 7 migration round-trip result. Mark the backlog item "Implemented — pending browser validation and independent review".
- [ ] **Step 6: Graph.** `graphify update .`; commit `chore(enh-024): update graphify knowledge graph`.
- [ ] **Step 7: Report, do not claim completion.** Summarise test/gate evidence; list open gates: browser validation (responsive 320/768/1024/1440, keyboard, axe), independent Codex review, merge.
