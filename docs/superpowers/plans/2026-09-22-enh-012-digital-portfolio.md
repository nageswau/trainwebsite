# ENH-012 — Digital Portfolio Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the per-student Digital Portfolio (ENH-012) — a computed completion-percentage view over
4 auto-populated sections plus 10 staff/teacher-entered self-entry sections and a personal statement,
readable by 7 School-domain roles and writable by 3 of them.

**Architecture:** One new FastAPI router (`apps/api/app/api/portfolio.py`) reusing the existing
`_load_readable_student()`/`_student_in_portfolio()` scoping helpers unchanged; two new additive tables
(`PortfolioEntry`, `PortfolioProfile`); one new read-rendering frontend component (`PortfolioPanel.tsx`)
wired into the two existing composition points that already reach every relevant role
(`SchoolStudentDetailPanel.tsx` for coordinator/principal/teacher, `parent/children/[id]/page.tsx` for
parent); one new write-form component (`PortfolioEntryForm.tsx`) mirroring `SchoolTransferRequestForm.tsx`
exactly.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Pydantic v2 + Alembic (backend); Next.js App Router Server
Components + vanilla `fetch` (frontend); pytest + pytest-asyncio + httpx (backend tests); Playwright
(e2e).

**Spec:** `docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md`

## Global Constraints

- No `PUT` — every update endpoint in this API uses `PATCH` (spec §3.7).
- JSON keys stay snake_case; error responses stay plain `HTTPException(status, "message")` — no new
  envelope (spec §3.7).
- No pagination, no Idempotency-Key — out of scope per spec §3.7.
- `description` ≤ 2000 chars, `personal_statement` ≤ 4000 chars (spec §5, security review).
- Every write endpoint calls `AuditLog` with `metadata_json` that never contains `title`/`description`/
  `personal_statement` content (spec §6).
- Role/scope check happens before any entry-existence check on every write endpoint (spec §6).
- No existing table, endpoint, model, or shared helper is modified — only called (spec §8).
- `PortfolioEntry` deletes are hard deletes → `204` (spec §13.2, confirmed).

---

### Task 1: `PortfolioEntry` / `PortfolioProfile` models + migration

**Files:**
- Modify: `apps/api/app/models.py` (append after the `SchoolStudentTransferRequest` class)
- Create: `apps/api/alembic/versions/0035_portfolio.py`
- Test: `apps/api/tests/test_enh_012_digital_portfolio.py` (new file)

**Interfaces:**
- Produces: `PortfolioEntry` (id, school_student_id, section, title, description, organization,
  date_from, date_to, created_by_user_id, updated_by_user_id, created_at, updated_at),
  `PortfolioProfile` (id, school_student_id [unique], personal_statement, updated_by_user_id, created_at,
  updated_at) — both importable from `app.models`.

**Field audit (resolves spec §13.1 — do this first, not a guess):** `SchoolStudent`
(`apps/api/app/models.py:985-1017`) has exactly two nullable, profile-shaped fields today:
`date_of_birth` and `grade_or_class` (`full_name`/`student_code` are always non-null, so they'd make
"profile" permanently 100%; `grade_level`/`academic_year_id` are internal promotion-tracking fields, not
profile fields a viewer would recognize). **Decision: "profile complete" = both `date_of_birth` and
`grade_or_class` are non-null.**

- [ ] **Step 1: Write the failing test**

```python
"""ENH-012 -- Digital Portfolio Module.
docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md
"""
import uuid
from datetime import date

import pytest

from app.models import PortfolioEntry, PortfolioProfile
from tests.enh005_helpers import mk_school, mk_staff


@pytest.mark.asyncio
async def test_portfolio_entry_and_profile_roundtrip(db_session):
    ctx = await mk_school(db_session, label="ENH012-Model")
    student = ctx["students"][0]
    entry = PortfolioEntry(
        school_student_id=student.id, section="project", title="Robotics club build",
        description="Built a line-following robot.", organization="School STEM Club",
        date_from=date(2026, 1, 10), date_to=date(2026, 3, 1),
        created_by_user_id=ctx["coordinator"].id, updated_by_user_id=ctx["coordinator"].id,
    )
    profile = PortfolioProfile(school_student_id=student.id, personal_statement="I want to study engineering.", updated_by_user_id=ctx["coordinator"].id)
    db_session.add_all([entry, profile])
    await db_session.commit()
    await db_session.refresh(entry)
    await db_session.refresh(profile)
    assert entry.id is not None
    assert entry.section == "project"
    assert profile.school_student_id == student.id


@pytest.mark.asyncio
async def test_portfolio_profile_school_student_id_is_unique(db_session):
    ctx = await mk_school(db_session, label="ENH012-Unique")
    student = ctx["students"][0]
    db_session.add(PortfolioProfile(school_student_id=student.id, personal_statement="First."))
    await db_session.commit()
    db_session.add(PortfolioProfile(school_student_id=student.id, personal_statement="Second."))
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v`
Expected: FAIL — `ImportError: cannot import name 'PortfolioEntry' from 'app.models'`

- [ ] **Step 3: Add the models**

In `apps/api/app/models.py`, immediately after the `SchoolStudentTransferRequest` class (`Index` is
already imported at the top of this file — no new import needed):

```python
class PortfolioEntry(Base, TimestampMixin):
    """ENH-012 -- self-entry Digital Portfolio content
    (docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md §5). One generic table with
    a `section` discriminator covers every list-shaped section (project/internship/competition/sport/
    leadership/volunteering/extracurricular/award/certification/skill) -- per-section tables were
    rejected in the spec's Approach section as unnecessary duplication of one shared shape. Net-new."""

    __tablename__ = "portfolio_entries"
    __table_args__ = (Index("ix_portfolio_entries_student_section", "school_student_id", "section"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    section: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization: Mapped[str | None] = mapped_column(String(200), nullable=True)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class PortfolioProfile(Base, TimestampMixin):
    """ENH-012 -- one row per student holding the free-text personal statement; separate from
    `PortfolioEntry` because it isn't list-shaped (spec §5). Net-new."""

    __tablename__ = "portfolio_profiles"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), unique=True, index=True)
    personal_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
```

Create `apps/api/alembic/versions/0035_portfolio.py` (mirrors `0034_school_transfer_requests.py`'s exact
structure — dev-startup guard, `op.create_table`, indexed FKs, clean `downgrade()`):

```python
"""ENH-012 -- portfolio_entries and portfolio_profiles.

Revision ID: 0035_portfolio
Revises: 0034_school_transfer_requests

docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md §5. Create-table only: no existing
table is altered and no existing row is read or written. `downgrade()` drops both tables.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0035_portfolio"
down_revision = "0034_school_transfer_requests"
branch_labels = None
depends_on = None

ENTRIES_TABLE = "portfolio_entries"
PROFILES_TABLE = "portfolio_profiles"


def upgrade() -> None:
    if not op.get_context().as_sql and ENTRIES_TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        ENTRIES_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
        sa.Column("section", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("organization", sa.String(200), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_portfolio_entries_student_section", ENTRIES_TABLE, ["school_student_id", "section"])
    op.create_table(
        PROFILES_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False, unique=True),
        sa.Column("personal_statement", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_portfolio_profiles_student", PROFILES_TABLE, ["school_student_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_portfolio_profiles_student", table_name=PROFILES_TABLE)
    op.drop_table(PROFILES_TABLE)
    op.drop_index("ix_portfolio_entries_student_section", table_name=ENTRIES_TABLE)
    op.drop_table(ENTRIES_TABLE)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v`
Expected: 2 passed (dev startup's `auto_create_schema` builds the new tables from the models directly;
running `alembic upgrade head` against a real deploy target is covered in Task 11's checklist, not by
this unit test).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/models.py apps/api/alembic/versions/0035_portfolio.py apps/api/tests/test_enh_012_digital_portfolio.py
git commit -m "feat(enh-012): add PortfolioEntry/PortfolioProfile models and migration"
```

---

### Task 2: Pydantic schemas + validation

**Files:**
- Modify: `apps/api/app/schemas.py` (append at end of file)
- Test: `apps/api/tests/test_enh_012_digital_portfolio.py`

**Interfaces:**
- Consumes: nothing from Task 1 directly (schemas are independent of the ORM models).
- Produces: `PORTFOLIO_SECTIONS: frozenset[str]`, `PortfolioEntryCreate`, `PortfolioEntryUpdate`,
  `PortfolioEntryOut`, `PersonalStatementUpdate`, `PersonalStatementOut` — all importable from
  `app.schemas`, used by Tasks 3-7.

- [ ] **Step 1: Write the failing test**

```python
import pytest as _pytest  # only if not already imported at module top; otherwise reuse the existing `import pytest`
from pydantic import ValidationError

from app.schemas import PortfolioEntryCreate, PORTFOLIO_SECTIONS


def test_portfolio_entry_create_rejects_unknown_section():
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="not_a_real_section", title="X")


def test_portfolio_entry_create_rejects_empty_title():
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="project", title="")


def test_portfolio_entry_create_rejects_date_to_before_date_from():
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="project", title="X", date_from="2026-06-01", date_to="2026-01-01")


def test_portfolio_entry_create_rejects_description_over_length_cap():
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="project", title="X", description="a" * 2001)


def test_portfolio_entry_create_accepts_a_valid_payload():
    entry = PortfolioEntryCreate(section="award", title="Regional Science Fair — 1st place", organization="State Science Council", date_from="2026-02-01")
    assert entry.section == "award"
    assert entry.date_to is None


def test_all_ten_section_values_are_defined():
    assert PORTFOLIO_SECTIONS == {"project", "internship", "competition", "sport", "leadership", "volunteering", "extracurricular", "award", "certification", "skill"}


def test_personal_statement_rejects_payload_over_length_cap():
    from app.schemas import PersonalStatementUpdate
    with pytest.raises(ValidationError):
        PersonalStatementUpdate(personal_statement="a" * 4001)
```

(Add these as new top-level test functions in `test_enh_012_digital_portfolio.py`; remove the throwaway
`import pytest as _pytest` line — the file already imports `pytest` from Task 1.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v -k portfolio_entry_create`
Expected: FAIL — `ImportError: cannot import name 'PortfolioEntryCreate' from 'app.schemas'`

- [ ] **Step 3: Write the schemas**

Append to `apps/api/app/schemas.py` (the file already imports `field_validator`, `model_validator`,
`BaseModel`, `Field` at the top — no new imports needed beyond `date` and `datetime`, which are already
used elsewhere in this file):

```python
PORTFOLIO_SECTIONS: frozenset[str] = frozenset({
    "project", "internship", "competition", "sport", "leadership", "volunteering",
    "extracurricular", "award", "certification", "skill",
})


def _no_control_characters(value: str | None) -> str | None:
    # Same rule as PromotionItem.grade_or_class (line ~501 above): a NUL byte cannot be stored in
    # PostgreSQL text and would surface as a 500; other control characters have no place in text that
    # is later rendered.
    if value is not None and any(unicodedata.category(ch) == "Cc" for ch in value):
        raise ValueError("must not contain control characters")
    return value


class PortfolioEntryCreate(BaseModel):
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}
    section: str
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    organization: str | None = Field(default=None, max_length=200)
    date_from: date | None = None
    date_to: date | None = None

    @field_validator("section")
    @classmethod
    def _known_section(cls, value: str) -> str:
        if value not in PORTFOLIO_SECTIONS:
            raise ValueError(f"section must be one of {sorted(PORTFOLIO_SECTIONS)}")
        return value

    @field_validator("title", "description", "organization")
    @classmethod
    def _clean_text(cls, value: str | None) -> str | None:
        return _no_control_characters(value)

    @model_validator(mode="after")
    def _date_range_is_ordered(self):
        if self.date_from is not None and self.date_to is not None and self.date_to < self.date_from:
            raise ValueError("date_to must not be before date_from")
        return self


class PortfolioEntryUpdate(BaseModel):
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    organization: str | None = Field(default=None, max_length=200)
    date_from: date | None = None
    date_to: date | None = None

    @field_validator("title", "description", "organization")
    @classmethod
    def _clean_text(cls, value: str | None) -> str | None:
        return _no_control_characters(value)

    @model_validator(mode="after")
    def _date_range_is_ordered(self):
        if self.date_from is not None and self.date_to is not None and self.date_to < self.date_from:
            raise ValueError("date_to must not be before date_from")
        return self


class PortfolioEntryOut(BaseModel):
    id: UUID
    school_student_id: UUID
    section: str
    title: str
    description: str | None
    organization: str | None
    date_from: date | None
    date_to: date | None
    created_by_user_id: UUID
    updated_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class PersonalStatementUpdate(BaseModel):
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}
    personal_statement: str | None = Field(default=None, max_length=4000)

    @field_validator("personal_statement")
    @classmethod
    def _clean_text(cls, value: str | None) -> str | None:
        return _no_control_characters(value)


class PersonalStatementOut(BaseModel):
    personal_statement: str | None
    updated_at: datetime
```

Check the top of `apps/api/app/schemas.py` for an existing `import unicodedata` (the `grade_or_class`
validator at line ~501 already uses `unicodedata.category`) — reuse it; do not add a second import.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v -k portfolio_entry_create or portfolio_sections or personal_statement_rejects`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas.py apps/api/tests/test_enh_012_digital_portfolio.py
git commit -m "feat(enh-012): add portfolio Pydantic schemas with validation"
```

---

### Task 3: Router skeleton + `GET /school/students/{id}/portfolio` + registration

**Files:**
- Create: `apps/api/app/api/portfolio.py`
- Modify: `apps/api/app/main.py:9,33` (import + register the router)
- Test: `apps/api/tests/test_enh_012_digital_portfolio.py`

**Interfaces:**
- Consumes: `PortfolioEntry`, `PortfolioProfile` (Task 1); `PORTFOLIO_SECTIONS` (Task 2); existing
  `_load_readable_student`, `_student_in_portfolio` from `app.api.schools` (imported, never modified);
  existing `get_current_user` (`app.api.deps`), `get_db` (`app.core.database`).
- Produces: `router` (FastAPI `APIRouter`), `_load_portfolio_student(db, user, student_id) -> SchoolStudent`,
  `_can_edit_portfolio(user, student) -> bool` — both reused by Tasks 4-7.

- [ ] **Step 1: Write the failing test**

```python
async def _add_academic_team(db_session, admin, school):
    from tests.enh005_helpers import mk_staff
    return await mk_staff(db_session, school, admin, role="academic_team")


@pytest.mark.asyncio
async def test_coordinator_reads_their_own_institution_students_portfolio(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-GET")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    response = await client.get(f"/api/v1/school/students/{student.id}/portfolio")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["student"]["id"] == str(student.id)
    assert body["completion_percentage"] == 0
    assert body["can_edit"] is True
    assert set(body["entries"].keys()) == {"project", "internship", "competition", "sport", "leadership", "volunteering", "extracurricular", "award", "certification", "skill"}


@pytest.mark.asyncio
async def test_principal_can_read_but_can_edit_is_false(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-GET-Principal")
    student = ctx["students"][0]
    await login(client, ctx["principal"].email)
    response = await client.get(f"/api/v1/school/students/{student.id}/portfolio")
    assert response.status_code == 200
    assert response.json()["can_edit"] is False


@pytest.mark.asyncio
async def test_coordinator_at_a_different_institution_gets_403(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx_a = await mk_school(db_session, label="ENH012-GET-A")
    ctx_b = await mk_school(db_session, label="ENH012-GET-B")
    await login(client, ctx_b["coordinator"].email)
    response = await client.get(f"/api/v1/school/students/{ctx_a['students'][0].id}/portfolio")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_academic_team_reads_via_their_portfolio_scope(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-GET-Academic")
    member = await _add_academic_team(db_session, ctx["admin"], ctx["school"])
    await login(client, member.email)
    response = await client.get(f"/api/v1/school/students/{ctx['students'][0].id}/portfolio")
    assert response.status_code == 200
    assert response.json()["can_edit"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v -k portfolio`
Expected: FAIL — `httpx.ConnectError`-style 404 from the ASGI app (route doesn't exist yet), or a
collection error if `app.api.portfolio` doesn't exist. Confirm the failure is "route not found" (404 with
FastAPI's default `{"detail":"Not Found"}`), not an unrelated error.

- [ ] **Step 3: Write the router and the GET endpoint**

Create `apps/api/app/api/portfolio.py`:

```python
"""ENH-012 -- Digital Portfolio Module.

docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md. Kept out of schools.py
deliberately: schools.py already has an unrelated existing meaning for "portfolio"
(_student_in_portfolio/_portfolio_school_ids/list_portfolio_students -- a staff member's
assigned-schools caseload). This module only imports and calls those, never modifies them.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import _load_readable_student, _student_in_portfolio
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import (
    AuditLog,
    PortfolioEntry,
    PortfolioProfile,
    SchoolAcademicResult,
    SchoolCareerRecord,
    SchoolLanguageRecord,
    SchoolPsychometricRecord,
    SchoolStudent,
    User,
)
from app.schemas import (
    PORTFOLIO_SECTIONS,
    PersonalStatementOut,
    PersonalStatementUpdate,
    PortfolioEntryCreate,
    PortfolioEntryOut,
    PortfolioEntryUpdate,
)

router = APIRouter(prefix="/school", tags=["school-portfolio"])
logger = get_logger("app.portfolio")

PORTFOLIO_SCOPED_ROLES = {"academic_team", "career_counselor", "psychometric_team"}
WRITE_ROLES = {"school_coordinator", "school_teacher", "academic_team"}


async def _load_portfolio_student(db: AsyncSession, user: User, student_id: UUID) -> SchoolStudent:
    """Read-scope loader: the 4 institution/assigned/own-child roles reuse `_load_readable_student()`
    unchanged; the 3 portfolio-scoped service-delivery roles reuse `_student_in_portfolio()` unchanged.
    Neither existing helper is modified -- only called (spec §6, §8)."""
    if user.role in PORTFOLIO_SCOPED_ROLES:
        return await _student_in_portfolio(db, user, student_id)
    return await _load_readable_student(db, user, student_id)


def _can_edit_portfolio(user: User, student: SchoolStudent) -> bool:
    """Called only after `_load_portfolio_student` has already confirmed the caller can READ this
    student -- this narrows that to the 3 write-capable roles. `school_teacher` gets the extra
    assigned-only check `_load_readable_student` already enforced for read, repeated here because a
    boolean helper must not assume its caller re-derives it."""
    if user.role not in WRITE_ROLES:
        return False
    if user.role == "school_teacher":
        return student.assigned_teacher_user_id == user.id
    return True


def _require_portfolio_write(user: User, student: SchoolStudent) -> None:
    if not _can_edit_portfolio(user, student):
        raise HTTPException(403, "You do not have write access to this student's portfolio")


def _profile_complete(student: SchoolStudent) -> bool:
    # Field audit, spec §13.1 (resolved in Task 1): the only two nullable profile-shaped fields on
    # SchoolStudent today. ENH-025 (mandatory full field coverage) is a separate, not-yet-built item.
    return student.date_of_birth is not None and student.grade_or_class is not None


def _entry_out(entry: PortfolioEntry) -> dict:
    return {
        "id": entry.id, "school_student_id": entry.school_student_id, "section": entry.section,
        "title": entry.title, "description": entry.description, "organization": entry.organization,
        "date_from": entry.date_from, "date_to": entry.date_to,
        "created_by_user_id": entry.created_by_user_id, "updated_by_user_id": entry.updated_by_user_id,
        "created_at": entry.created_at, "updated_at": entry.updated_at,
    }


@router.get("/students/{student_id}/portfolio")
async def get_portfolio(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """No `response_model` -- matches `student_timeline()`'s own convention for a computed aggregate
    endpoint (schools.py:1040), the closest existing precedent this feature is modeled on."""
    student = await _load_portfolio_student(db, user, student_id)
    can_edit = _can_edit_portfolio(user, student)

    entries_by_section: dict[str, list[dict]] = {section: [] for section in sorted(PORTFOLIO_SECTIONS)}
    rows = (await db.scalars(select(PortfolioEntry).where(PortfolioEntry.school_student_id == student.id).order_by(PortfolioEntry.date_from.desc().nullslast(), PortfolioEntry.created_at.desc()))).all()
    for row in rows:
        entries_by_section[row.section].append(_entry_out(row))

    academic = (await db.scalars(select(SchoolAcademicResult).where(SchoolAcademicResult.school_student_id == student.id, SchoolAcademicResult.status == "published"))).all()
    psychometric = (await db.scalars(select(SchoolPsychometricRecord).where(SchoolPsychometricRecord.school_student_id == student.id))).all()
    career = (await db.scalars(select(SchoolCareerRecord).where(SchoolCareerRecord.school_student_id == student.id))).all()
    languages = (await db.scalars(select(SchoolLanguageRecord).where(SchoolLanguageRecord.school_student_id == student.id))).all()

    profile_row = await db.scalar(select(PortfolioProfile).where(PortfolioProfile.school_student_id == student.id))
    personal_statement = profile_row.personal_statement if profile_row else None

    filled = sum([
        _profile_complete(student),
        len(academic) > 0, len(psychometric) > 0, len(career) > 0, len(languages) > 0,
        *(len(entries_by_section[s]) > 0 for s in PORTFOLIO_SECTIONS),
        bool(personal_statement and personal_statement.strip()),
    ])
    completion_percentage = round(filled / 16 * 100)

    return {
        "student": {"id": student.id, "full_name": student.full_name},
        "completion_percentage": completion_percentage,
        "can_edit": can_edit,
        "profile_complete": _profile_complete(student),
        "academic_achievements": [{"id": r.id, "term": r.term, "subject": r.subject, "grade": r.grade, "published_at": r.published_at} for r in academic],
        "psychometric_report": [{"id": r.id, "assessment_type": r.assessment_type, "report_url": r.report_url, "created_at": r.created_at} for r in psychometric],
        "career_guidance": [{"id": r.id, "record_type": r.record_type, "notes": r.notes, "created_at": r.created_at} for r in career],
        "languages": [{"id": r.id, "language": r.language, "level": r.level, "certification_status": r.certification_status, "created_at": r.created_at} for r in languages],
        "entries": entries_by_section,
        "personal_statement": personal_statement,
    }
```

**Before running the test:** verify the exact attribute names used above
(`SchoolAcademicResult.grade`/`.published_at`, `SchoolPsychometricRecord.report_url`,
`SchoolCareerRecord.record_type`/`.notes`, `SchoolLanguageRecord.level`/`.certification_status`) against
`apps/api/app/models.py` before running — if any name differs, fix it there; these were read from the
existing endpoints' own field access in `schools.py` during design but must be confirmed against the
model source, not assumed twice.

Register the router in `apps/api/app/main.py`:

```python
# line 9 — add `portfolio` to the import list (alphabetical, matching the existing style):
from app.api import account, admin, auth, cms, communications, employer, files, inbound, payments, portal, portfolio, public, school_transfers, schools, workflows

# line 33 — add `portfolio.router` to the include loop:
for r in (auth.router, public.router, portal.router, admin.router, admin.agents_router, files.router, workflows.router, payments.router, cms.router, communications.router, inbound.router, account.router, employer.router, schools.router, school_transfers.coordinator_router, school_transfers.admin_router, portfolio.router):
    app.include_router(r, prefix="/api/v1")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v -k portfolio`
Expected: 4 passed (plus the earlier model/schema tests still passing)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/portfolio.py apps/api/app/main.py apps/api/tests/test_enh_012_digital_portfolio.py
git commit -m "feat(enh-012): add GET /school/students/{id}/portfolio"
```

---

### Task 4: `POST /school/students/{id}/portfolio/entries`

**Files:**
- Modify: `apps/api/app/api/portfolio.py`
- Test: `apps/api/tests/test_enh_012_digital_portfolio.py`

**Interfaces:**
- Consumes: `_load_portfolio_student`, `_require_portfolio_write`, `_entry_out` (Task 3);
  `PortfolioEntryCreate`, `PortfolioEntryOut` (Task 2).

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_coordinator_creates_an_entry(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-POST")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    response = await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "award", "title": "Regional Science Fair — 1st place", "organization": "State Science Council"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["section"] == "award"
    assert body["school_student_id"] == str(student.id)

    portfolio = (await client.get(f"/api/v1/school/students/{student.id}/portfolio")).json()
    assert len(portfolio["entries"]["award"]) == 1
    assert portfolio["completion_percentage"] == round(1 / 16 * 100)


@pytest.mark.asyncio
async def test_teacher_outside_assignment_cannot_create_an_entry(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-POST-Teacher", students=2, with_teacher=True)
    unassigned_student = ctx["students"][1]  # only students[0] is assigned to the teacher
    await login(client, ctx["teacher"].email)
    response = await client.post(f"/api/v1/school/students/{unassigned_student.id}/portfolio/entries", json={"section": "project", "title": "X"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_parent_cannot_create_an_entry(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-POST-Parent")
    await login(client, ctx["parent"].email)
    response = await client.post(f"/api/v1/school/students/{ctx['students'][0].id}/portfolio/entries", json={"section": "project", "title": "X"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_entry_writes_an_audit_log_without_free_text(client, db_session):
    from sqlalchemy import select as sa_select

    from app.models import AuditLog
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-POST-Audit")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "Secret project title should not be logged"})
    row = await db_session.scalar(sa_select(AuditLog).where(AuditLog.action == "school.portfolio_entry_create").order_by(AuditLog.created_at.desc()))
    assert row is not None
    assert row.metadata_json == {"section": "project", "school_student_id": str(student.id)}
    assert "Secret project title" not in str(row.metadata_json)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v -k create_an_entry or create_entry`
Expected: FAIL — 404 Not Found (route doesn't exist yet)

- [ ] **Step 3: Write the endpoint**

Append to `apps/api/app/api/portfolio.py`:

```python
@router.post("/students/{student_id}/portfolio/entries", status_code=201, response_model=PortfolioEntryOut)
async def create_portfolio_entry(student_id: UUID, payload: PortfolioEntryCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_portfolio_student(db, user, student_id)
    _require_portfolio_write(user, student)
    entry = PortfolioEntry(
        school_student_id=student.id, section=payload.section, title=payload.title,
        description=payload.description, organization=payload.organization,
        date_from=payload.date_from, date_to=payload.date_to,
        created_by_user_id=user.id, updated_by_user_id=user.id,
    )
    db.add(entry)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.portfolio_entry_create", entity_type="portfolio_entry", entity_id=str(entry.id), metadata_json={"section": entry.section, "school_student_id": str(student.id)}))
    await db.commit()
    await db.refresh(entry)
    logger.info("portfolio_entry_create", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id), "entry_id": str(entry.id), "section": entry.section}})
    return _entry_out(entry)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v -k create_an_entry or create_entry`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/portfolio.py apps/api/tests/test_enh_012_digital_portfolio.py
git commit -m "feat(enh-012): add POST .../portfolio/entries with audit logging"
```

---

### Task 5: `PATCH /school/students/{id}/portfolio/entries/{entry_id}`

**Files:**
- Modify: `apps/api/app/api/portfolio.py`
- Test: `apps/api/tests/test_enh_012_digital_portfolio.py`

**Interfaces:**
- Consumes: same helpers as Task 4, plus `PortfolioEntryUpdate` (Task 2).

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_coordinator_updates_their_own_entry(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-PATCH")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    created = (await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "Draft title"})).json()
    response = await client.patch(f"/api/v1/school/students/{student.id}/portfolio/entries/{created['id']}", json={"title": "Final title"})
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Final title"


@pytest.mark.asyncio
async def test_patching_an_entry_that_belongs_to_a_different_student_is_404(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx_a = await mk_school(db_session, label="ENH012-PATCH-A")
    ctx_b = await mk_school(db_session, label="ENH012-PATCH-B")
    await login(client, ctx_a["coordinator"].email)
    created = (await client.post(f"/api/v1/school/students/{ctx_a['students'][0].id}/portfolio/entries", json={"section": "project", "title": "A's entry"})).json()

    await login(client, ctx_b["coordinator"].email)
    response = await client.patch(f"/api/v1/school/students/{ctx_b['students'][0].id}/portfolio/entries/{created['id']}", json={"title": "Hijacked"})
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v -k updates_their_own_entry or belongs_to_a_different_student`
Expected: FAIL — 405 Method Not Allowed (the path exists for POST but not PATCH)

- [ ] **Step 3: Write the endpoint**

Append to `apps/api/app/api/portfolio.py`:

```python
async def _load_portfolio_entry(db: AsyncSession, student_id: UUID, entry_id: UUID) -> PortfolioEntry:
    entry = await db.get(PortfolioEntry, entry_id)
    if not entry or entry.school_student_id != student_id:
        raise HTTPException(404, "Portfolio entry not found")
    return entry


@router.patch("/students/{student_id}/portfolio/entries/{entry_id}", response_model=PortfolioEntryOut)
async def update_portfolio_entry(student_id: UUID, entry_id: UUID, payload: PortfolioEntryUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_portfolio_student(db, user, student_id)
    _require_portfolio_write(user, student)  # role/scope checked before the entry lookup below (spec §6)
    entry = await _load_portfolio_entry(db, student.id, entry_id)
    for field in ("title", "description", "organization", "date_from", "date_to"):
        value = getattr(payload, field)
        if value is not None:
            setattr(entry, field, value)
    entry.updated_by_user_id = user.id
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.portfolio_entry_update", entity_type="portfolio_entry", entity_id=str(entry.id), metadata_json={"section": entry.section, "school_student_id": str(student.id)}))
    await db.commit()
    await db.refresh(entry)
    logger.info("portfolio_entry_update", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id), "entry_id": str(entry.id)}})
    return _entry_out(entry)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v -k updates_their_own_entry or belongs_to_a_different_student`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/portfolio.py apps/api/tests/test_enh_012_digital_portfolio.py
git commit -m "feat(enh-012): add PATCH .../portfolio/entries/{entry_id} with ownership check"
```

---

### Task 6: `DELETE /school/students/{id}/portfolio/entries/{entry_id}`

**Files:**
- Modify: `apps/api/app/api/portfolio.py`
- Test: `apps/api/tests/test_enh_012_digital_portfolio.py`

**Interfaces:**
- Consumes: `_load_portfolio_entry` (Task 5), `_load_portfolio_student`, `_require_portfolio_write` (Task 3).

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_coordinator_deletes_their_own_entry(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-DELETE")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    created = (await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "To be deleted"})).json()
    response = await client.delete(f"/api/v1/school/students/{student.id}/portfolio/entries/{created['id']}")
    assert response.status_code == 204

    portfolio = (await client.get(f"/api/v1/school/students/{student.id}/portfolio")).json()
    assert portfolio["entries"]["project"] == []


@pytest.mark.asyncio
async def test_read_only_role_cannot_delete_an_entry(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-DELETE-RO")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    created = (await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "Should survive"})).json()

    await login(client, ctx["principal"].email)
    response = await client.delete(f"/api/v1/school/students/{student.id}/portfolio/entries/{created['id']}")
    assert response.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v -k deletes_their_own_entry or cannot_delete_an_entry`
Expected: FAIL — 405 Method Not Allowed

- [ ] **Step 3: Write the endpoint**

Append to `apps/api/app/api/portfolio.py`:

```python
@router.delete("/students/{student_id}/portfolio/entries/{entry_id}", status_code=204)
async def delete_portfolio_entry(student_id: UUID, entry_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_portfolio_student(db, user, student_id)
    _require_portfolio_write(user, student)
    entry = await _load_portfolio_entry(db, student.id, entry_id)
    section, entry_id_str = entry.section, str(entry.id)
    await db.delete(entry)
    db.add(AuditLog(user_id=user.id, action="school.portfolio_entry_delete", entity_type="portfolio_entry", entity_id=entry_id_str, metadata_json={"section": section, "school_student_id": str(student.id)}))
    await db.commit()
    logger.info("portfolio_entry_delete", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id), "entry_id": entry_id_str}})
```

(A `204` route must not return a body — FastAPI enforces this automatically for `status_code=204` when the
function returns `None`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v -k deletes_their_own_entry or cannot_delete_an_entry`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/portfolio.py apps/api/tests/test_enh_012_digital_portfolio.py
git commit -m "feat(enh-012): add DELETE .../portfolio/entries/{entry_id}"
```

---

### Task 7: `PATCH /school/students/{id}/portfolio/personal-statement` (upsert + race handling)

**Files:**
- Modify: `apps/api/app/api/portfolio.py`
- Test: `apps/api/tests/test_enh_012_digital_portfolio.py`

**Interfaces:**
- Consumes: `PersonalStatementUpdate`, `PersonalStatementOut` (Task 2); `_load_portfolio_student`,
  `_require_portfolio_write` (Task 3).

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_coordinator_sets_the_personal_statement(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-STMT")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    response = await client.patch(f"/api/v1/school/students/{student.id}/portfolio/personal-statement", json={"personal_statement": "I want to study engineering."})
    assert response.status_code == 200, response.text
    assert response.json()["personal_statement"] == "I want to study engineering."

    portfolio = (await client.get(f"/api/v1/school/students/{student.id}/portfolio")).json()
    assert portfolio["personal_statement"] == "I want to study engineering."


@pytest.mark.asyncio
async def test_setting_the_statement_twice_updates_the_same_row(client, db_session):
    from sqlalchemy import func, select as sa_select

    from app.models import PortfolioProfile
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-STMT-Twice")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    await client.patch(f"/api/v1/school/students/{student.id}/portfolio/personal-statement", json={"personal_statement": "First draft."})
    await client.patch(f"/api/v1/school/students/{student.id}/portfolio/personal-statement", json={"personal_statement": "Revised."})
    count = await db_session.scalar(sa_select(func.count()).select_from(PortfolioProfile).where(PortfolioProfile.school_student_id == student.id))
    assert count == 1
    row = await db_session.scalar(sa_select(PortfolioProfile).where(PortfolioProfile.school_student_id == student.id))
    assert row.personal_statement == "Revised."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v -k personal_statement or statement_twice`
Expected: FAIL — 405 Method Not Allowed

- [ ] **Step 3: Write the endpoint**

Append to `apps/api/app/api/portfolio.py`:

```python
@router.patch("/students/{student_id}/portfolio/personal-statement", response_model=PersonalStatementOut)
async def update_personal_statement(student_id: UUID, payload: PersonalStatementUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Upsert via the same begin_nested()/IntegrityError idiom as school_transfers.py:277-284, but
    resolved as an update-on-conflict rather than a 409: a second concurrent "set the statement" is not
    a duplicate-intent conflict like a transfer filing (spec §6)."""
    student = await _load_portfolio_student(db, user, student_id)
    _require_portfolio_write(user, student)
    statement = payload.personal_statement.strip() if payload.personal_statement else None
    row = None
    try:
        async with db.begin_nested():
            row = PortfolioProfile(school_student_id=student.id, personal_statement=statement, updated_by_user_id=user.id)
            db.add(row)
            await db.flush()
    except IntegrityError:
        row = await db.scalar(select(PortfolioProfile).where(PortfolioProfile.school_student_id == student.id))
        row.personal_statement = statement
        row.updated_by_user_id = user.id
        await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.portfolio_personal_statement_update", entity_type="portfolio_profile", entity_id=str(row.id), metadata_json={"school_student_id": str(student.id)}))
    await db.commit()
    await db.refresh(row)
    logger.info("portfolio_personal_statement_update", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id)}})
    return {"personal_statement": row.personal_statement, "updated_at": row.updated_at}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v -k personal_statement or statement_twice`
Expected: 2 passed. Then run the full file to confirm nothing regressed:

Run: `cd apps/api && pytest tests/test_enh_012_digital_portfolio.py -v`
Expected: all tests from Tasks 1-7 pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/portfolio.py apps/api/tests/test_enh_012_digital_portfolio.py
git commit -m "feat(enh-012): add PATCH .../portfolio/personal-statement with race-safe upsert"
```

**Backend is now feature-complete against the spec's API surface (§6, all 5 endpoints).** Run the full
existing backend suite once here to confirm no regression before moving to frontend work (spec AC-08):

Run: `cd apps/api && pytest tests/test_sch_004_career_guidance.py tests/test_sch_005_psychometric_assessment.py tests/test_sch_006_academic_results.py tests/test_sch_008_student_timeline.py tests/test_sch_009_test_prep_language.py -v`
Expected: all pass, unchanged.

---

### Task 8: `PortfolioEntryForm.tsx` — write form + `apiErrors.ts` addition

**Files:**
- Modify: `apps/web/lib/apiErrors.ts` (add `isPortfolioEntryBody`)
- Create: `apps/web/components/PortfolioEntryForm.tsx`
- Test: `apps/web/tests/components/PortfolioEntryForm.test.tsx` (new file)

**Interfaces:**
- Consumes: `detailMessage`, `NOT_COMPLETED` (existing, `apps/web/lib/apiErrors.ts`); `refocus` (existing,
  `apps/web/lib/focus.ts`).
- Produces: `PortfolioEntryForm` (default export) — consumed by Task 9's `PortfolioPanel`.

- [ ] **Step 1: Write the failing test**

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PortfolioEntryForm from "@/components/PortfolioEntryForm";

describe("PortfolioEntryForm", () => {
  it("requires a title before submitting", async () => {
    render(<PortfolioEntryForm studentId="s1" section="project" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText(/enter a title/i)).toBeInTheDocument();
  });

  it("shows a server error on failure", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: "date_to must not be before date_from" }) }) as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="project" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "A project" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("date_to must not be before date_from");
  });

  it("calls onDone after a successful save", async () => {
    const onDone = vi.fn();
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "e1", section: "project", title: "A project" }) }) as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="project" onDone={onDone} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "A project" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("PATCHes to the entry URL and omits section when editing an existing entry", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "e1", section: "project", title: "Updated" }) });
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="project" entryId="e1" initial={{ title: "Old", description: null, organization: null, date_from: null, date_to: null }} onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "Updated" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/school/students/s1/portfolio/entries/e1", expect.objectContaining({ method: "PATCH" })));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npx vitest run tests/components/PortfolioEntryForm.test.tsx`
Expected: FAIL — cannot resolve module `@/components/PortfolioEntryForm`

- [ ] **Step 3: Write the helper and the component**

Append to `apps/web/lib/apiErrors.ts`:

```ts
// ENH-012: same shape-check philosophy as isRequestBody() above -- a 2xx whose body isn't a real
// portfolio entry (a proxy page, an empty body) must not be reported as saved.
export function isPortfolioEntryBody(data: unknown): data is { id: string; section: string } {
  return !!data && typeof data === "object" && typeof (data as { id?: unknown }).id === "string" && typeof (data as { section?: unknown }).section === "string";
}
```

Create `apps/web/components/PortfolioEntryForm.tsx`:

```tsx
"use client";

import { FormEvent, useRef, useState } from "react";

import { detailMessage, isPortfolioEntryBody, NOT_COMPLETED } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";

// ENH-012 -- one form for all 10 self-entry sections (same shape: title/organization/dates/description),
// mirroring SchoolTransferRequestForm.tsx exactly: per-field useState, busy/inFlight guard, raw fetch(),
// no optimistic UI (waits for the confirmed response, matching this codebase's deliberately conservative
// pattern -- spec §3.8). Used both for create (no entryId) and edit (entryId + initial values) by
// PortfolioPanel.tsx (Task 9).

export default function PortfolioEntryForm({ studentId, section, entryId, initial, onDone, onCancel }: {
  studentId: string; section: string; entryId?: string;
  initial?: { title: string; description: string | null; organization: string | null; date_from: string | null; date_to: string | null };
  onDone: () => void; onCancel: () => void;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [organization, setOrganization] = useState(initial?.organization ?? "");
  const [dateFrom, setDateFrom] = useState(initial?.date_from ?? "");
  const [dateTo, setDateTo] = useState(initial?.date_to ?? "");
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [alert, setAlert] = useState<string | null>(null);
  const inFlight = useRef(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || inFlight.current) return;
    setAlert(null);
    if (!title.trim()) {
      setFieldError("Enter a title.");
      return;
    }
    setFieldError(null);
    inFlight.current = true;
    setBusy(true);
    const body = {
      ...(entryId ? {} : { section }),
      title: title.trim(),
      description: description.trim() || null,
      organization: organization.trim() || null,
      date_from: dateFrom || null,
      date_to: dateTo || null,
    };
    const url = entryId ? `/api/v1/school/students/${studentId}/portfolio/entries/${entryId}` : `/api/v1/school/students/${studentId}/portfolio/entries`;
    let response: Response;
    try {
      response = await fetch(url, { method: entryId ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } catch {
      inFlight.current = false;
      setBusy(false);
      setAlert(NOT_COMPLETED);
      refocus("pf-save-btn");
      return;
    }
    const data = await response.json().catch(() => null);
    inFlight.current = false;
    setBusy(false);
    if (!response.ok) {
      setAlert(detailMessage(data?.detail));
      refocus("pf-save-btn");
      return;
    }
    if (!isPortfolioEntryBody(data)) {
      setAlert("The save could not be confirmed. Please check the list before retrying.");
      refocus("pf-save-btn");
      return;
    }
    onDone();
  }

  return (
    <form className="form" onSubmit={submit} noValidate>
      <div className="field">
        <label htmlFor="pf-title">Title</label>
        <input id="pf-title" className="search" value={title} disabled={busy} aria-invalid={fieldError ? true : undefined} aria-describedby={fieldError ? "pf-title-error" : undefined} onChange={(e) => setTitle(e.target.value)} />
        {fieldError && <span id="pf-title-error" className="form-error">{fieldError}</span>}
      </div>
      <div className="field">
        <label htmlFor="pf-organization">Organization (optional)</label>
        <input id="pf-organization" className="search" value={organization} disabled={busy} onChange={(e) => setOrganization(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="pf-date-from">Start date (optional)</label>
        <input id="pf-date-from" type="date" className="search" value={dateFrom} disabled={busy} onChange={(e) => setDateFrom(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="pf-date-to">End date (optional)</label>
        <input id="pf-date-to" type="date" className="search" value={dateTo} disabled={busy} onChange={(e) => setDateTo(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="pf-description">Description (optional)</label>
        <textarea id="pf-description" className="search" rows={3} maxLength={2000} value={description} disabled={busy} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <button id="pf-save-btn" type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      <button type="button" className="btn secondary" disabled={busy} onClick={onCancel}>Cancel</button>
      {alert && <div role="alert" className="form-error">{alert}</div>}
    </form>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npx vitest run tests/components/PortfolioEntryForm.test.tsx`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/apiErrors.ts apps/web/components/PortfolioEntryForm.tsx apps/web/tests/components/PortfolioEntryForm.test.tsx
git commit -m "feat(enh-012): add PortfolioEntryForm write component"
```

- [ ] **Step 1: Write the failing test**

First check the exact test runner/import style used by `SchoolStudentTimeline.test.tsx` (likely Vitest,
given `WorkflowPanel.create-user.test.tsx` references `vitest` in the graph) — open that file and copy its
import/render/assert pattern exactly rather than guessing a different testing library. Then write:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PortfolioPanel, { type PortfolioData } from "@/components/PortfolioPanel";

const BASE: PortfolioData = {
  student: { id: "s1", full_name: "Test Student" },
  completion_percentage: 0,
  can_edit: false,
  profile_complete: false,
  academic_achievements: [], psychometric_report: [], career_guidance: [], languages: [],
  entries: { project: [], internship: [], competition: [], sport: [], leadership: [], volunteering: [], extracurricular: [], award: [], certification: [], skill: [] },
  personal_statement: null,
};

describe("PortfolioPanel", () => {
  it("shows the completion percentage as visible text", () => {
    render(<PortfolioPanel data={{ ...BASE, completion_percentage: 25 }} />);
    expect(screen.getByText(/25% complete/i)).toBeInTheDocument();
  });

  it("renders an empty-state message per empty section, matching Timeline's wording style", () => {
    render(<PortfolioPanel data={BASE} />);
    expect(screen.getAllByText("No entries yet.").length).toBeGreaterThan(0);
  });

  it("does not render any Add button for a read-only viewer", () => {
    render(<PortfolioPanel data={{ ...BASE, can_edit: false }} />);
    expect(screen.queryByRole("button", { name: /add/i })).not.toBeInTheDocument();
  });

  it("renders an Add button per self-entry section for a writer", () => {
    render(<PortfolioPanel data={{ ...BASE, can_edit: true }} />);
    expect(screen.getAllByRole("button", { name: /add/i }).length).toBe(10);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npx vitest run tests/components/PortfolioPanel.test.tsx`
Expected: FAIL — cannot resolve module `@/components/PortfolioPanel`

- [ ] **Step 3: Write the component**

```tsx
import { serverApi } from "@/lib/api";
import { formatDate } from "@/components/SchoolChildOverview";

// ENH-012 -- Digital Portfolio: docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md.
// Read-rendering only, styled after SchoolStudentTimeline.tsx (the closest existing precedent: a
// read-only aggregated per-student panel fed by one computed backend endpoint). Write affordances
// (Add/Edit/Delete) render conditionally from `data.can_edit`, which the backend computes from the
// viewer's actual role/scope -- never re-derived client-side.

export type PortfolioEntry = { id: string; section: string; title: string; description: string | null; organization: string | null; date_from: string | null; date_to: string | null; created_at: string; updated_at: string };
export type PortfolioData = {
  student: { id: string; full_name: string };
  completion_percentage: number;
  can_edit: boolean;
  profile_complete: boolean;
  academic_achievements: { id: string; term: string; subject: string; grade: string | null; published_at: string }[];
  psychometric_report: { id: string; assessment_type: string; report_url: string | null; created_at: string }[];
  career_guidance: { id: string; record_type: string; notes: string; created_at: string }[];
  languages: { id: string; language: string; level: string | null; certification_status: string; created_at: string }[];
  entries: Record<string, PortfolioEntry[]>;
  personal_statement: string | null;
};

export async function loadPortfolio(studentId: string): Promise<PortfolioData> {
  return serverApi<PortfolioData>(`/api/v1/school/students/${studentId}/portfolio`);
}

const SECTION_LABELS: Record<string, string> = {
  project: "Projects", internship: "Internships", competition: "Competitions", sport: "Sports",
  leadership: "Leadership", volunteering: "Volunteering", extracurricular: "Extracurriculars",
  award: "Awards", certification: "Certifications", skill: "Skills",
};

function EntryList({ section, entries, canEdit, onAdd }: { section: string; entries: PortfolioEntry[]; canEdit: boolean; onAdd?: (section: string) => void }) {
  return (
    <div className="pf-section">
      <h4>{SECTION_LABELS[section] ?? section}</h4>
      {entries.length === 0 ? (
        <p className="muted">No entries yet.</p>
      ) : (
        <ul className="pf-entry-list">
          {entries.map((e) => (
            <li className="pf-entry" key={e.id}>
              <strong>{e.title}</strong>
              {e.organization && <span className="pf-entry-org"> — {e.organization}</span>}
              {e.date_from && <span className="pf-entry-date"> ({formatDate(e.date_from)}{e.date_to ? ` – ${formatDate(e.date_to)}` : ""})</span>}
              {e.description && <p className="pf-entry-desc">{e.description}</p>}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <button type="button" className="btn secondary pf-add-btn" onClick={() => onAdd?.(section)}>Add {SECTION_LABELS[section]?.toLowerCase().replace(/s$/, "") ?? section}</button>
      )}
    </div>
  );
}

export default function PortfolioPanel({ data, onAdd }: { data: PortfolioData; onAdd?: (section: string) => void }) {
  return (
    <div className="card pf-panel">
      <h3>Digital Portfolio</h3>
      <div className="pf-meter" role="progressbar" aria-valuenow={data.completion_percentage} aria-valuemin={0} aria-valuemax={100} aria-label="Portfolio completion">
        <div className="pf-meter-fill" style={{ width: `${data.completion_percentage}%` }} />
      </div>
      <p className="pf-meter-label">{data.completion_percentage}% complete</p>

      <div className="pf-section">
        <h4>Academic achievements</h4>
        {data.academic_achievements.length === 0 ? <p className="muted">No entries yet.</p> : (
          <ul className="pf-entry-list">{data.academic_achievements.map((r) => <li className="pf-entry" key={r.id}>{r.subject} — {r.term}{r.grade ? ` (${r.grade})` : ""}</li>)}</ul>
        )}
      </div>
      <div className="pf-section">
        <h4>Psychometric report</h4>
        {data.psychometric_report.length === 0 ? <p className="muted">No entries yet.</p> : (
          <ul className="pf-entry-list">{data.psychometric_report.map((r) => <li className="pf-entry" key={r.id}>{r.assessment_type}</li>)}</ul>
        )}
      </div>
      <div className="pf-section">
        <h4>Career guidance</h4>
        {data.career_guidance.length === 0 ? <p className="muted">No entries yet.</p> : (
          <ul className="pf-entry-list">{data.career_guidance.map((r) => <li className="pf-entry" key={r.id}>{r.record_type}</li>)}</ul>
        )}
      </div>
      <div className="pf-section">
        <h4>Languages</h4>
        {data.languages.length === 0 ? <p className="muted">No entries yet.</p> : (
          <ul className="pf-entry-list">{data.languages.map((r) => <li className="pf-entry" key={r.id}>{r.language}{r.level ? ` — ${r.level}` : ""}</li>)}</ul>
        )}
      </div>

      {Object.keys(data.entries).sort().map((section) => (
        <EntryList key={section} section={section} entries={data.entries[section]} canEdit={data.can_edit} onAdd={onAdd} />
      ))}

      <div className="pf-section">
        <h4>Personal statement</h4>
        {data.personal_statement ? <p className="pf-statement">{data.personal_statement}</p> : <p className="muted">No entries yet.</p>}
      </div>
    </div>
  );
}
```

Append to `apps/web/app/globals.css`:

```css
.pf-panel { display: flex; flex-direction: column; gap: 0.75rem; }
.pf-meter { height: 8px; border-radius: 4px; background: #e2e8f0; overflow: hidden; }
.pf-meter-fill { height: 100%; background: #0755b9; }
.pf-meter-label { font-size: 0.875rem; color: #475569; margin: 0; }
.pf-section { border-top: 1px solid #e2e8f0; padding-top: 0.75rem; }
.pf-section h4 { margin: 0 0 0.5rem; font-size: 0.95rem; }
.pf-entry-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.5rem; }
.pf-entry-org, .pf-entry-date { color: #475569; font-size: 0.875rem; }
.pf-entry-desc { margin: 0.25rem 0 0; font-size: 0.9rem; }
.pf-add-btn { margin-top: 0.5rem; }
.pf-statement { white-space: pre-wrap; }
```

These are a first pass, meant to render correctly and pass the tests below — the required browser
validation step (not part of this plan's automated tests) should confirm visual alignment with the
existing `.card`/`.jtl-*` styling before this is called visually final.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npx vitest run tests/components/PortfolioPanel.test.tsx`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/PortfolioPanel.tsx apps/web/app/globals.css apps/web/tests/components/PortfolioPanel.test.tsx
git commit -m "feat(enh-012): add PortfolioPanel read-rendering component"
```

---

### Task 9: `PortfolioPanel.tsx` — interactive read+write panel

**Files:**
- Create: `apps/web/components/PortfolioPanel.tsx`
- Modify: `apps/web/app/globals.css` (append `.pf-*` rules)
- Test: `apps/web/tests/components/PortfolioPanel.test.tsx` (new file)

**Interfaces:**
- Consumes: backend response shape from Task 3's `GET /portfolio` (the `PortfolioData` type below);
  `PortfolioEntryForm` (Task 8).
- Produces: `PortfolioPanel` (default export), `loadPortfolio(studentId): Promise<PortfolioData>`,
  `PortfolioData`/`PortfolioEntry` types — all consumed by Task 10.

**Correction from the original draft of this plan:** an earlier version of this task made
`PortfolioPanel` a read-only Server Component and left "wiring `PortfolioEntryForm` into an add/edit
flow" for an unspecified follow-up. That's wrong — it would ship Add/Edit/Delete buttons that do nothing,
failing spec AC-03 ("coordinator/teacher/academic_team can create/edit/delete") in an actual browser.
Caught during this plan's own self-review, fixed here: `PortfolioPanel` is a Client Component (like
`SchoolTransferRequestForm.tsx`, which also receives server-fetched data as a prop and manages its own
interactive state) that owns which section's form is open and calls `router.refresh()` on save/delete —
no separate follow-up needed.

- [ ] **Step 1: Write the failing test**

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

import PortfolioPanel, { type PortfolioData } from "@/components/PortfolioPanel";

const BASE: PortfolioData = {
  student: { id: "s1", full_name: "Test Student" },
  completion_percentage: 0,
  can_edit: false,
  profile_complete: false,
  academic_achievements: [], psychometric_report: [], career_guidance: [], languages: [],
  entries: { project: [], internship: [], competition: [], sport: [], leadership: [], volunteering: [], extracurricular: [], award: [], certification: [], skill: [] },
  personal_statement: null,
};

describe("PortfolioPanel", () => {
  it("shows the completion percentage as visible text", () => {
    render(<PortfolioPanel data={{ ...BASE, completion_percentage: 25 }} />);
    expect(screen.getByText(/25% complete/i)).toBeInTheDocument();
  });

  it("renders an empty-state message per empty section", () => {
    render(<PortfolioPanel data={BASE} />);
    expect(screen.getAllByText("No entries yet.").length).toBeGreaterThan(0);
  });

  it("does not render any Add button for a read-only viewer", () => {
    render(<PortfolioPanel data={{ ...BASE, can_edit: false }} />);
    expect(screen.queryByRole("button", { name: /add/i })).not.toBeInTheDocument();
  });

  it("renders an Add button per self-entry section for a writer", () => {
    render(<PortfolioPanel data={{ ...BASE, can_edit: true }} />);
    expect(screen.getAllByRole("button", { name: /add/i }).length).toBe(10);
  });

  it("clicking Add opens the entry form for that section", () => {
    render(<PortfolioPanel data={{ ...BASE, can_edit: true }} />);
    fireEvent.click(screen.getAllByRole("button", { name: /add project/i })[0]);
    expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
  });

  it("shows Edit and Delete for each existing entry when can_edit is true", () => {
    const data: PortfolioData = { ...BASE, can_edit: true, entries: { ...BASE.entries, project: [{ id: "e1", section: "project", title: "Robotics", description: null, organization: null, date_from: null, date_to: null, created_at: "2026-01-01", updated_at: "2026-01-01" }] } };
    render(<PortfolioPanel data={data} />);
    expect(screen.getByRole("button", { name: /edit robotics/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete robotics/i })).toBeInTheDocument();
  });

  it("delete requires a second confirming click", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => null });
    global.fetch = fetchMock as unknown as typeof fetch;
    const data: PortfolioData = { ...BASE, can_edit: true, entries: { ...BASE.entries, project: [{ id: "e1", section: "project", title: "Robotics", description: null, organization: null, date_from: null, date_to: null, created_at: "2026-01-01", updated_at: "2026-01-01" }] } };
    render(<PortfolioPanel data={data} />);
    fireEvent.click(screen.getByRole("button", { name: /delete robotics/i }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /confirm delete/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/school/students/s1/portfolio/entries/e1", expect.objectContaining({ method: "DELETE" })));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npx vitest run tests/components/PortfolioPanel.test.tsx`
Expected: FAIL — cannot resolve module `@/components/PortfolioPanel`

- [ ] **Step 3: Write the component**

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import PortfolioEntryForm from "@/components/PortfolioEntryForm";
import { formatDate } from "@/components/SchoolChildOverview";
import { serverApi } from "@/lib/api";

// ENH-012 -- Digital Portfolio: docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md.
// Client Component (like SchoolTransferRequestForm.tsx) because it owns interactive state -- which
// section's Add/Edit form is open, and the Delete confirm step -- even though its data arrives already
// fetched from the server (loadPortfolio, called by the pages in Task 10). No optimistic UI: every
// mutation waits for a confirmed response, then calls router.refresh() to re-pull server data, matching
// this codebase's established pattern (spec §3.8).

export type PortfolioEntry = { id: string; section: string; title: string; description: string | null; organization: string | null; date_from: string | null; date_to: string | null; created_at: string; updated_at: string };
export type PortfolioData = {
  student: { id: string; full_name: string };
  completion_percentage: number;
  can_edit: boolean;
  profile_complete: boolean;
  academic_achievements: { id: string; term: string; subject: string; grade: string | null; published_at: string }[];
  psychometric_report: { id: string; assessment_type: string; report_url: string | null; created_at: string }[];
  career_guidance: { id: string; record_type: string; notes: string; created_at: string }[];
  languages: { id: string; language: string; level: string | null; certification_status: string; created_at: string }[];
  entries: Record<string, PortfolioEntry[]>;
  personal_statement: string | null;
};

export async function loadPortfolio(studentId: string): Promise<PortfolioData> {
  return serverApi<PortfolioData>(`/api/v1/school/students/${studentId}/portfolio`);
}

const SECTION_LABELS: Record<string, string> = {
  project: "Projects", internship: "Internships", competition: "Competitions", sport: "Sports",
  leadership: "Leadership", volunteering: "Volunteering", extracurricular: "Extracurriculars",
  award: "Awards", certification: "Certifications", skill: "Skills",
};

function singular(section: string): string {
  return (SECTION_LABELS[section] ?? section).toLowerCase().replace(/s$/, "");
}

export default function PortfolioPanel({ data }: { data: PortfolioData }) {
  const router = useRouter();
  const [openSection, setOpenSection] = useState<string | null>(null);
  const [editing, setEditing] = useState<PortfolioEntry | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function closeForm() {
    setOpenSection(null);
    setEditing(null);
  }

  function onFormDone() {
    closeForm();
    router.refresh();
  }

  async function deleteEntry(entry: PortfolioEntry) {
    if (confirmingId !== entry.id) {
      setConfirmingId(entry.id);
      return;
    }
    setDeleteError(null);
    let response: Response;
    try {
      response = await fetch(`/api/v1/school/students/${data.student.id}/portfolio/entries/${entry.id}`, { method: "DELETE" });
    } catch {
      setDeleteError("The request did not complete. Check your connection and try again; your entry is kept.");
      setConfirmingId(null);
      return;
    }
    setConfirmingId(null);
    if (!response.ok && response.status !== 204) {
      const body = await response.json().catch(() => null);
      setDeleteError(typeof body?.detail === "string" ? body.detail : "Delete failed.");
      return;
    }
    router.refresh();
  }

  function EntryList({ section, entries }: { section: string; entries: PortfolioEntry[] }) {
    const formOpenHere = openSection === section && !editing;
    return (
      <div className="pf-section">
        <h4>{SECTION_LABELS[section] ?? section}</h4>
        {entries.length === 0 ? (
          <p className="muted">No entries yet.</p>
        ) : (
          <ul className="pf-entry-list">
            {entries.map((e) => (
              <li className="pf-entry" key={e.id}>
                {editing?.id === e.id ? (
                  <PortfolioEntryForm studentId={data.student.id} section={e.section} entryId={e.id} initial={{ title: e.title, description: e.description, organization: e.organization, date_from: e.date_from, date_to: e.date_to }} onDone={onFormDone} onCancel={closeForm} />
                ) : (
                  <>
                    <strong>{e.title}</strong>
                    {e.organization && <span className="pf-entry-org"> — {e.organization}</span>}
                    {e.date_from && <span className="pf-entry-date"> ({formatDate(e.date_from)}{e.date_to ? ` – ${formatDate(e.date_to)}` : ""})</span>}
                    {e.description && <p className="pf-entry-desc">{e.description}</p>}
                    {data.can_edit && (
                      <div className="pf-entry-actions">
                        <button type="button" className="btn secondary" onClick={() => { setEditing(e); setOpenSection(null); }}>Edit {e.title}</button>
                        <button type="button" className="btn secondary" onClick={() => deleteEntry(e)}>{confirmingId === e.id ? `Confirm delete ${e.title}` : `Delete ${e.title}`}</button>
                      </div>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
        {data.can_edit && !formOpenHere && (
          <button type="button" className="btn secondary pf-add-btn" onClick={() => { setOpenSection(section); setEditing(null); }}>Add {singular(section)}</button>
        )}
        {formOpenHere && <PortfolioEntryForm studentId={data.student.id} section={section} onDone={onFormDone} onCancel={closeForm} />}
      </div>
    );
  }

  return (
    <div className="card pf-panel">
      <h3>Digital Portfolio</h3>
      <div className="pf-meter" role="progressbar" aria-valuenow={data.completion_percentage} aria-valuemin={0} aria-valuemax={100} aria-label="Portfolio completion">
        <div className="pf-meter-fill" style={{ width: `${data.completion_percentage}%` }} />
      </div>
      <p className="pf-meter-label">{data.completion_percentage}% complete</p>
      {deleteError && <div role="alert" className="form-error">{deleteError}</div>}

      <div className="pf-section">
        <h4>Academic achievements</h4>
        {data.academic_achievements.length === 0 ? <p className="muted">No entries yet.</p> : (
          <ul className="pf-entry-list">{data.academic_achievements.map((r) => <li className="pf-entry" key={r.id}>{r.subject} — {r.term}{r.grade ? ` (${r.grade})` : ""}</li>)}</ul>
        )}
      </div>
      <div className="pf-section">
        <h4>Psychometric report</h4>
        {data.psychometric_report.length === 0 ? <p className="muted">No entries yet.</p> : (
          <ul className="pf-entry-list">{data.psychometric_report.map((r) => <li className="pf-entry" key={r.id}>{r.assessment_type}</li>)}</ul>
        )}
      </div>
      <div className="pf-section">
        <h4>Career guidance</h4>
        {data.career_guidance.length === 0 ? <p className="muted">No entries yet.</p> : (
          <ul className="pf-entry-list">{data.career_guidance.map((r) => <li className="pf-entry" key={r.id}>{r.record_type}</li>)}</ul>
        )}
      </div>
      <div className="pf-section">
        <h4>Languages</h4>
        {data.languages.length === 0 ? <p className="muted">No entries yet.</p> : (
          <ul className="pf-entry-list">{data.languages.map((r) => <li className="pf-entry" key={r.id}>{r.language}{r.level ? ` — ${r.level}` : ""}</li>)}</ul>
        )}
      </div>

      {Object.keys(data.entries).sort().map((section) => (
        <EntryList key={section} section={section} entries={data.entries[section]} />
      ))}

      <div className="pf-section">
        <h4>Personal statement</h4>
        {data.personal_statement ? <p className="pf-statement">{data.personal_statement}</p> : <p className="muted">No entries yet.</p>}
      </div>
    </div>
  );
}
```

Append to `apps/web/app/globals.css`:

```css
.pf-panel { display: flex; flex-direction: column; gap: 0.75rem; }
.pf-meter { height: 8px; border-radius: 4px; background: #e2e8f0; overflow: hidden; }
.pf-meter-fill { height: 100%; background: #0755b9; }
.pf-meter-label { font-size: 0.875rem; color: #475569; margin: 0; }
.pf-section { border-top: 1px solid #e2e8f0; padding-top: 0.75rem; }
.pf-section h4 { margin: 0 0 0.5rem; font-size: 0.95rem; }
.pf-entry-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.5rem; }
.pf-entry-org, .pf-entry-date { color: #475569; font-size: 0.875rem; }
.pf-entry-desc { margin: 0.25rem 0 0; font-size: 0.9rem; }
.pf-entry-actions { display: flex; gap: 0.5rem; margin-top: 0.25rem; }
.pf-add-btn { margin-top: 0.5rem; }
.pf-statement { white-space: pre-wrap; }
```

These are a first pass, meant to render correctly and pass the tests below — the required browser
validation step (not part of this plan's automated tests) should confirm visual alignment with the
existing `.card`/`.jtl-*` styling before this is called visually final.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npx vitest run tests/components/PortfolioPanel.test.tsx`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/PortfolioPanel.tsx apps/web/app/globals.css apps/web/tests/components/PortfolioPanel.test.tsx
git commit -m "feat(enh-012): add interactive PortfolioPanel (read + add/edit/delete)"
```

---

### Task 10: Wire `PortfolioPanel` into the student-detail pages

**Files:**
- Modify: `apps/web/components/SchoolStudentDetailPanel.tsx` (covers coordinator, principal, and teacher —
  confirmed by this file's own comment: "reused across every School role that can open one student's page
  within their own SCH-001 scope: Teacher (assigned), School Coordinator and Principal (own institution)")
- Modify: `apps/web/app/school/parent/children/[id]/page.tsx` (parent does not use the shared panel above —
  confirmed by reading it; it composes its own layout)

**Interfaces:**
- Consumes: `PortfolioPanel`, `loadPortfolio` (Task 9).

- [ ] **Step 1: Write the failing test**

This task is verified by Task 11's Playwright spec (page-level composition is integration behavior, not
unit-testable in isolation the way Tasks 8-9's components are — matching how `SchoolTransferRequestForm`'s
own wiring into `SchoolStudentDetailPanel.tsx` has no dedicated unit test either, only e2e coverage). Skip
straight to the change; Task 11 is this task's test.

- [ ] **Step 2: N/A — see Task 11**

- [ ] **Step 3: Wire the panel into `SchoolStudentDetailPanel.tsx`**

```tsx
// Add to the import block at the top:
import PortfolioPanel, { loadPortfolio } from "@/components/PortfolioPanel";

// Add `loadPortfolio(student.id).catch(() => null)` to the existing Promise.all (keeps the "opens with
// no client round-trip" property every other panel here already has):
const [timeline, gradeHistory, transferHistory, destinations, pendingPage, portfolio] = await Promise.all([
  loadStudentTimeline(student.id).catch(() => null),
  showGradeHistory ? loadGradeHistory(student.id).catch(() => null) : Promise.resolve(null),
  showTransfer ? loadTransferHistory(student.id) : Promise.resolve([]),
  showTransfer ? serverApi<SchoolRef[]>("/api/v1/school/transfer-destinations").catch(() => null) : Promise.resolve([]),
  showTransfer ? serverApi<Page<TransferRequest>>("/api/v1/school/transfer-requests?status=pending&limit=100").catch(() => null) : Promise.resolve(null),
  loadPortfolio(student.id).catch(() => null),
]);

// Add, right after the "Journey timeline" card at the end of the returned JSX:
{portfolio ? <PortfolioPanel data={portfolio} /> : <div className="card"><h3>Digital Portfolio</h3><p className="muted">Portfolio is unavailable right now.</p></div>}
```

`PortfolioPanel` (Task 9) already owns its own Add/Edit/Delete interactivity internally — no extra prop
plumbing is needed here beyond passing `data`. Coordinator and teacher get working write controls because
`data.can_edit` is `true` for them (computed server-side); principal gets `false` and sees the same panel
with no write controls rendered, with no separate "read-only variant" needed.

Wire the panel into `apps/web/app/school/parent/children/[id]/page.tsx`:

```tsx
// Add to the import block at the top:
import PortfolioPanel, { loadPortfolio, type PortfolioData } from "@/components/PortfolioPanel";

// Extend the existing Promise.all's destructuring and type annotation:
const [timeline, gradeHistory, transferHistory, portfolio]: [StudentTimeline | null, StudentGradeHistory | null, TransferHistoryEntry[] | null, PortfolioData | null] = await Promise.all([
  loadStudentTimeline(id).catch(() => null),
  loadGradeHistory(id).catch(() => null),
  loadTransferHistory(id),
  loadPortfolio(id).catch(() => null),
]);

// Add, right after the "Journey timeline" card in the returned JSX:
{portfolio ? <PortfolioPanel data={portfolio} /> : <div className="card"><h3>Digital Portfolio</h3><p className="muted">Portfolio is unavailable right now.</p></div>}
```

- [ ] **Step 4: N/A — verified in Task 11**

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/SchoolStudentDetailPanel.tsx "apps/web/app/school/parent/children/[id]/page.tsx"
git commit -m "feat(enh-012): render PortfolioPanel on coordinator/principal/teacher/parent student pages"
```

---

### Task 11: Playwright e2e — the acceptance-criteria flow

**Files:**
- Create: `apps/web/tests/e2e/enh-012-digital-portfolio.spec.ts`

**Interfaces:**
- Consumes: the full stack from Tasks 1-10, running against a real (test) backend + frontend. Setup
  follows `sch-008-student-timeline.spec.ts`'s exact pattern (read there first): seed via
  `page.request` calls through the real onboarding APIs, verify via real UI navigation and clicks.

- [ ] **Step 1: Write the failing test**

```ts
import { expect, test } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-012 -- docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md AC-01..AC-07.
// Setup mirrors sch-008-student-timeline.spec.ts: seed a school/coordinator/teachers/student/parent
// through the real onboarding APIs, then drive the feature itself (adding an entry) through the real
// UI, since that's what this feature actually is.

test("coordinator adds a portfolio entry via the UI; parent sees it read-only; an unassigned teacher is denied (ENH-012)", async ({ page }) => {
  test.setTimeout(60_000);
  const unique = Date.now();
  const coordinatorEmail = `enh012-e2e-coord-${unique}@example.local`;
  const parentEmail = `enh012-e2e-parent-${unique}@example.local`;
  const assignedTeacherEmail = `enh012-e2e-teacher-assigned-${unique}@example.local`;
  const outsideTeacherEmail = `enh012-e2e-teacher-outside-${unique}@example.local`;

  // --- Overseas Admin: create the school + seed Coordinator (identical to sch-008's own setup).
  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E Portfolio School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E Portfolio Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();
  const schoolListRes = await page.request.get("/api/v1/overseas-admin/schools");
  const schools = await schoolListRes.json();
  const school = schools.find((s: { name: string }) => s.name === `E2E Portfolio School ${unique}`);
  expect(school).toBeTruthy();

  // --- Coordinator: invite an assigned teacher and an outside (unassigned) teacher, create the student.
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  const invitedAssigned = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_teacher", full_name: "E2E Assigned Teacher", email: assignedTeacherEmail } });
  const assignedToken = (await invitedAssigned.json()).development_invite_token;
  const invitedOutside = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_teacher", full_name: "E2E Outside Teacher", email: outsideTeacherEmail } });
  const outsideToken = (await invitedOutside.json()).development_invite_token;

  for (const token of [assignedToken, outsideToken]) {
    await page.request.post("/api/v1/auth/logout");
    await page.goto(`/school/invite/${token}/accept`);
    await page.fill("#invite-password", "Sup3r-Secret-Pass!");
    await page.click('button:has-text("Accept and set up login")');
    await page.waitForURL("**/school/teacher/dashboard");
  }

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  const studentRes = await page.request.post("/api/v1/school/students", {
    data: { full_name: "Portfolio Test Child", grade_or_class: "Grade 7", assigned_teacher_email: assignedTeacherEmail, parent_name: "E2E Portfolio Parent", parent_email: parentEmail },
  });
  expect(studentRes.status()).toBe(201);
  const student = await studentRes.json();
  const parentToken = student.development_invite_token;

  // --- Coordinator: reach the student via the real roster link (not a direct URL), read the starting
  // percentage, add an entry through the real form, confirm the list and percentage both update.
  await page.goto("/school/coordinator/students");
  await page.locator("tr", { hasText: "Portfolio Test Child" }).getByRole("link", { name: "Timeline" }).click();
  await page.waitForURL(`**/school/coordinator/students/${student.id}`);
  await expect(page.getByRole("heading", { name: "Digital Portfolio" })).toBeVisible();
  const startingPercent = Number((await page.locator(".pf-meter-label").textContent())?.match(/\d+/)?.[0] ?? "0");

  await page.getByRole("button", { name: "Add award" }).click();
  await page.getByLabel("Title").fill("Regional Science Fair — 1st place");
  await page.getByLabel("Organization (optional)").fill("State Science Council");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Regional Science Fair — 1st place")).toBeVisible();
  const updatedPercent = Number((await page.locator(".pf-meter-label").textContent())?.match(/\d+/)?.[0] ?? "0");
  expect(updatedPercent).toBeGreaterThan(startingPercent);

  // --- Parent: sees the same entry, with zero write controls anywhere in the portfolio card (AC-05).
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${parentToken}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");
  await page.click('a:has-text("View full profile & progress")');
  await page.waitForURL(`**/school/parent/children/${student.id}`);
  await expect(page.getByRole("heading", { name: "Digital Portfolio" })).toBeVisible();
  await expect(page.getByText("Regional Science Fair — 1st place")).toBeVisible();
  await expect(page.locator(".pf-panel").getByRole("button", { name: /add|edit|delete/i })).toHaveCount(0);

  // --- Outside teacher: not assigned to this student, denied the student's page entirely (AC-06/AC-07).
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", outsideTeacherEmail);
  await page.fill("#login-password", "Sup3r-Secret-Pass!");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/teacher/dashboard");
  await page.goto(`/school/teacher/students/${student.id}`);
  await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npx playwright test tests/e2e/enh-012-digital-portfolio.spec.ts`
Expected: FAIL at the first Task-1-through-10 gap that isn't actually done yet (or passes outright if all
prior tasks are complete and correct — this is the integration test for everything before it, so a
failure here means go back and check the specific step it failed on against Tasks 1-10, not that this
test itself is wrong).

- [ ] **Step 3: Fix whatever the failure points at**

If it fails on a selector (e.g. `getByLabel("Title")` finds nothing), check the actual rendered markup
from Task 8/9 against the test's expectation — fix the component if it's a real gap (e.g. a missing
`htmlFor`/`id` pairing), not the test's plain-language expectation. If it fails earlier, in the onboarding
setup itself, re-check against `sch-008-student-timeline.spec.ts`'s current behavior — that flow is
unrelated to this feature and should not need changes.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npx playwright test tests/e2e/enh-012-digital-portfolio.spec.ts`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add apps/web/tests/e2e/enh-012-digital-portfolio.spec.ts
git commit -m "test(enh-012): add Playwright e2e coverage for the digital portfolio flow"
```

---

## After all 11 tasks

This plan produces working, tested code but **does not itself constitute a completion claim** — per the
user's explicit instruction, browser validation (a real run through the golden path and edge cases in an
actual browser, not just Playwright's headless assertions) and an independent Codex review are still
required before this is considered done. Do not report ENH-012 as complete until both of those have run.
