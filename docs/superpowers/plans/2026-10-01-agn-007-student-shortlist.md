# AGN-007 Student University Shortlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an agency's Masters and Staff keep a paged university shortlist per agency student. An entry is either catalogue-backed or agency-private. Masters also get a private "Universities" list that only Masters can add to.

**Architecture:**
- Two new tables: `agent_universities` (tenant key `org_id`) and `agent_student_shortlist_entries` (scope inherited from `agent_students`).
- A new router and service pair that reuses AGN-004's gate, lock, scoped load and audit helpers unchanged.
- The shared catalogue tables and `/public` are never written.
- Frontend:
  - a shortlist card list inside the AGN-004 student detail view;
  - a new agent nav section, "Universities", mounted by `PortalPage` the same way Students is.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Pydantic v2, Alembic, PostgreSQL; Next.js (App Router) and React client components; vitest with Testing Library; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-01-agn-007-student-shortlist-design.md` (read it first; §n references below point there).

## Global Constraints

- The tables `universities`, `overseas_courses` and `countries`, and the file `app/api/public.py`, are **not modified**.
- `app/api/agent_students.py` is **not modified**; its helpers are imported. The detail GET contract is unchanged.
- Error bodies use FastAPI `{"detail": ...}`. Fields are snake_case. Validation failures are 422.
- Caps: `MAX_ENTRIES_PER_STUDENT = 50`, `MAX_UNIVERSITIES_PER_AGENCY = 500`.
- Text limits:
  - `name` 200, `country` 120, `city` 120;
  - `course_title` 200, `intake` 120, `tuition_fee` 120;
  - `entry_requirements` 2000.
  - All go through `clean_free_text`.
- Course mismatch detail, verbatim: `"Course does not belong to selected university"`.
- Every write follows one order:
  1. `_gate`
  2. `lock_active_org`
  3. scoped `FOR UPDATE` load(s)
  4. validate
  5. write
  6. audit (same transaction)
  7. one `commit`
- Service functions never commit.
- Audit and log metadata hold ids, field names and counts only, never free-text values.
- No new npm or PyPI dependency.
- No edits to shared components (`SearchableSelect`, `DataTable`, `PortalSection`, `WorkflowPanel`).
- Numbering is provisional:
  - `DEC-SCOPE-048`;
  - migration `0055_agent_shortlist`, `down_revision` = the real head at execution (Task 0).
- Tests run for real. Run the lite backend set only; the owner runs the full suite. The user controls docker: give them commands and wait for confirmation.

## Review Focus

1. **A university switch on PATCH leaves a stale catalogue course.** Expect 422, not a silent mismatch. Test: `test_patch_switching_university_with_a_stale_course_is_422` (Task 3).
2. **An agency university id from another agency in a shortlist body.** Expect the same 422 "University not found" as an unknown id. Test: `test_other_agencys_university_id_reads_as_not_found` (Task 4).
3. **Deleting an agency university while another request shortlists it.** Expect no orphan entry, one 409 or a clean order. Test: `test_delete_university_racing_an_add_never_orphans` (Task 4).
4. **The Escape key inside the shortlist form must not also close the student detail view.** Test: `closes the form on Escape without closing the detail` (Task 8).
5. **Whitespace-only or NUL text.** Expect blank to become null (so a whitespace-only `name` is 422) and NUL to be 422. Test: `test_text_is_cleaned_and_controls_rejected` (Task 1).

---

## File map

**Backend (`apps/api/`)**

| File | Change | Responsibility |
|---|---|---|
| `app/models.py` | modify (append after `AgentOrgMember`) | `AgentUniversity`, `AgentStudentShortlistEntry` |
| `alembic/versions/0055_agent_shortlist.py` | create | create-if-missing tables, constraints, indexes; downgrade drops them |
| `app/schemas.py` | modify (after `AgentStudentAssign`) | `AgentUniversityCreate/Update`, `ShortlistEntryCreate/Update` |
| `app/services/agent_shortlist.py` | create | queries, shapes, validation, caps (never commits) |
| `app/api/agent_shortlist.py` | create | routes: gate, lock, scope, role, audit, commit |
| `app/main.py` | modify | register `agent_shortlist.router` |
| `app/services/staff_activity.py` | modify | three new whitelist actions |
| `app/services/portal.py` | modify | `universities` section header payload |
| `tests/agn007_helpers.py` | create | catalogue factory and URL constants |
| `tests/test_agn_007_schema.py` | create | model, migration and constraint tests |
| `tests/test_agn_007_universities.py` | create | agency university CRUD, roles, caps, paging |
| `tests/test_agn_007_shortlist.py` | create | entry CRUD, rules, scope, archive, paging |
| `tests/test_agn_007_isolation.py` | create | cross-agency and `/public` invisibility, races, audit and activity |
| `tests/test_agn_003_matrix.py` | modify | the University DB and Add University rows |

**Frontend (`apps/web/`)**

| File | Change | Responsibility |
|---|---|---|
| `lib/agentShortlist.ts` | create | URLs, types, payload builders, client checks |
| `lib/navigation.ts` | modify | the `universities` agent nav item |
| `components/AgentUniversityForm.tsx` | create | Master add/edit form |
| `components/AgentUniversitiesPanel.tsx` | create | paged, searchable list; Master actions; Staff read-only |
| `components/PortalPage.tsx` | modify | mount the panel for `overseas/agent` `universities` |
| `components/AgentShortlistForm.tsx` | create | add/edit an entry (university, course, prefill) |
| `components/AgentShortlistPanel.tsx` | create | paged card list, remove confirm, states |
| `components/AgentStudentDetailPanel.tsx` | modify | one mount line |
| `tests/lib/agentShortlist.test.ts`, `tests/lib/navigation.agent.test.ts` | create / modify | |
| `tests/components/AgentUniversitiesPanel.test.tsx`, `AgentShortlistForm.test.tsx`, `AgentShortlistPanel.test.tsx` | create | |
| `tests/e2e/agn-007-shortlist.spec.ts` | create | |

**Docs:** see Task 11.

## Test commands (used by every task)

The user starts the isolated stack. Give them this and wait for "up":

```bash
# from the worktree root; copy .env from the main checkout first, set API_PORT=8007 WEB_PORT=3007 FRONTEND_URL=http://localhost:3007 (check the ports are free)
docker compose -p agn007 -f docker-compose.yml up -d --build
```

Backend tests run as a one-off `api-test` container. The mount **must** be the Windows-form absolute path:

```bash
API_TEST() { docker compose -p agn007 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/agn-007/apps/api:/app" \
  api-test sh -c "alembic upgrade head && python -m pytest -q $*"; }
```

If `alembic upgrade head` fails on a stale stamp, run `alembic stamp --purge <real head before 0055>` and then `upgrade head`.

Web: `cd apps/web && npx vitest run <files>`, then `npx tsc --noEmit` and `npx eslint <changed files>`.

E2E: `cd apps/web && E2E_BASE_URL=http://localhost:3007 npx playwright test tests/e2e/agn-007-shortlist.spec.ts --workers=1`.

---

### Task 0: Pre-flight (numbering and stack)

**Files:** none.

- [ ] **Step 1: Recheck `main` for parallel AGN work.**

```bash
git fetch origin
git log --oneline -5 origin/main
git ls-tree --name-only origin/main apps/api/alembic/versions/ | sort | tail -3
grep -o "### DEC-SCOPE-0[0-9][0-9]" docs/decisions/PRODUCT_DECISION_REGISTER.md | sort -u | tail -2
```

Then decide the numbers:
- The migration is the next number after the real head. Expect `0055` if AGN-006's `0054` landed, otherwise `0054`. The `revision` id stays `0055_agent_shortlist` unless the number is free lower; then use `0054_agent_shortlist` and replace it everywhere in this plan.
- `DEC-SCOPE` is the next free number. Expect `048` (047 is reserved by AGN-006).
- If `main` moved, `git merge origin/main` first.

- [ ] **Step 2: Ask the user to start the `agn007` stack** (command above) and wait for confirmation. Then run `API_TEST tests/test_agn_004_students.py` once as a baseline. Expected: all pass.

---

### Task 1: Data layer (models, migration, schemas)

**Files:**
- Modify: `apps/api/app/models.py` (append after class `AgentOrgMember`)
- Create: `apps/api/alembic/versions/0055_agent_shortlist.py`
- Modify: `apps/api/app/schemas.py` (append after `class AgentStudentAssign`)
- Test: `apps/api/tests/test_agn_007_schema.py`

**Interfaces:**
- Produces:
  - Models `AgentUniversity(id, org_id, name, country, city, entry_requirements, created_by_user_id, updated_by_user_id, created_at, updated_at)` and `AgentStudentShortlistEntry(id, agent_student_id, university_id, agent_university_id, course_id, course_title, intake, tuition_fee, entry_requirements, created_by_user_id, updated_by_user_id, created_at, updated_at)`.
  - Schemas `AgentUniversityCreate`, `AgentUniversityUpdate`, `ShortlistEntryCreate`, `ShortlistEntryUpdate`.
  - `UNIVERSITY_LIMITS`, `ENTRY_LIMITS` dicts in `schemas.py`.

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_agn_007_schema.py`:

```python
"""AGN-007 -- models, migration 0055_agent_shortlist and request schemas (spec §4, §5.3; AC03 DB-level, Review Focus 5)."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.models import AgentStudentShortlistEntry, AgentUniversity
from app.schemas import AgentUniversityCreate, AgentUniversityUpdate, ShortlistEntryCreate
from tests.agn001_helpers import mk_active_org
from tests.agn004_helpers import mk_record
from tests.agn007_helpers import mk_catalogue

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_007_migration", VERSIONS / "0055_agent_shortlist.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def test_migration_is_the_single_head():
    assert _migration.revision == "0055_agent_shortlist"
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((l.split("=", 1)[1].strip().strip("\"'") for l in lines if l.startswith("revision =")), None)
        if rev:
            parents[rev] = next((l.split("=", 1)[1].strip().strip("\"'") for l in lines if l.startswith("down_revision =")), None)
    assert set(parents) - set(parents.values()) == {"0055_agent_shortlist"}


@pytest.mark.asyncio
async def test_tables_constraints_and_indexes_exist(db_session):
    conn = await db_session.connection()

    def _read(sync):
        i = inspect(sync)
        return (
            {c["name"] for c in i.get_check_constraints("agent_student_shortlist_entries")},
            {x["name"] for x in i.get_indexes("agent_student_shortlist_entries")} | {x["name"] for x in i.get_indexes("agent_universities")},
        )

    checks, indexes = await conn.run_sync(_read)
    assert {"ck_shortlist_one_university", "ck_shortlist_catalogue_course", "ck_shortlist_one_course_form"} <= checks
    assert {"ix_shortlist_student_created", "uq_agent_universities_org_name_country", "ix_agent_universities_org_id"} <= indexes


async def _student(db):
    ctx = await mk_active_org(db, name="Schema Agency")
    return ctx, await mk_record(db, agent=ctx["master"], full_name="Schema Student")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["both_universities", "no_university", "catalogue_course_with_agency", "both_course_forms"])
async def test_check_constraints_reject_invalid_rows(db_session, bad):  # AGN-007-AC03 (database level)
    ctx, student = await _student(db_session)
    cat = await mk_catalogue(db_session)
    agency_uni = AgentUniversity(org_id=ctx["org"].id, name=f"U {uuid.uuid4().hex[:6]}", country="Ireland")
    db_session.add(agency_uni)
    await db_session.commit()
    values = {
        "both_universities": {"university_id": cat["university"].id, "agent_university_id": agency_uni.id},
        "no_university": {},
        "catalogue_course_with_agency": {"agent_university_id": agency_uni.id, "course_id": cat["course"].id},
        "both_course_forms": {"university_id": cat["university"].id, "course_id": cat["course"].id, "course_title": "Typed"},
    }[bad]
    db_session.add(AgentStudentShortlistEntry(agent_student_id=student.id, **values))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_agency_university_name_and_country_are_unique_per_agency_case_insensitive(db_session):
    ctx = await mk_active_org(db_session, name="Unique Agency")
    other = await mk_active_org(db_session, name="Unique Other")
    db_session.add_all([AgentUniversity(org_id=ctx["org"].id, name="Trinity", country="Ireland"), AgentUniversity(org_id=other["org"].id, name="Trinity", country="Ireland")])
    await db_session.commit()
    db_session.add(AgentUniversity(org_id=ctx["org"].id, name="TRINITY", country="ireland"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


def test_text_is_cleaned_and_controls_rejected():  # Review Focus 5
    assert AgentUniversityCreate(name="  Trinity  ", country="Ireland", city="   ").model_dump() == {"name": "Trinity", "country": "Ireland", "city": None, "entry_requirements": None}
    for bad in ({"name": "   ", "country": "Ireland"}, {"name": "A\x00B", "country": "Ireland"}, {"name": "x" * 201, "country": "Ireland"}):
        with pytest.raises(ValidationError):
            AgentUniversityCreate(**bad)
    with pytest.raises(ValidationError):
        ShortlistEntryCreate(entry_requirements="y" * 2001)
    with pytest.raises(ValidationError):
        ShortlistEntryCreate(org_id=str(uuid.uuid4()))  # mass assignment (extra="forbid")


def test_university_update_cannot_clear_name_or_country():
    assert AgentUniversityUpdate(city=None).model_dump(exclude_unset=True) == {"city": None}
    for bad in ({"name": None}, {"country": "  "}):
        with pytest.raises(ValidationError):
            AgentUniversityUpdate(**bad)
```

Also create the helper `apps/api/tests/agn007_helpers.py`:

```python
"""AGN-007 test helpers: a catalogue university with two courses, a second catalogue university with one, and URL builders."""

import uuid

from app.models import Country, OverseasCourse, University

UNIVERSITIES = "/api/v1/workflows/overseas/agent/crm/universities"


def shortlist(student_id) -> str:
    return f"/api/v1/workflows/overseas/agent/crm/students/{student_id}/shortlist"


async def mk_catalogue(db) -> dict:
    tag = uuid.uuid4().hex[:8]
    country = Country(slug=f"agn007-country-{tag}", name=f"Catalogland {tag}", overview="", tuition="", living_expenses="", visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[])
    db.add(country)
    await db.flush()
    unis = []
    for label in ("a", "b"):
        u = University(country_id=country.id, slug=f"agn007-{label}-{tag}", name=f"AGN007 Uni {label.upper()} {tag}", city="Catalog City", overview="", eligibility="", requirements=["IELTS 6.5", "Transcript"], deadlines=[], scholarships=[])
        db.add(u)
        unis.append(u)
    await db.flush()
    course = OverseasCourse(university_id=unis[0].id, title=f"MSc Data {tag}", level="PG", category="Tech", duration="1 year", tuition_fee="EUR 20,000", intake="Sep 2027")
    other_course = OverseasCourse(university_id=unis[1].id, title=f"MBA {tag}", level="PG", category="Business", duration="1 year", tuition_fee="EUR 30,000", intake="Jan 2028")
    db.add_all([course, other_course])
    await db.commit()
    return {"country": country, "university": unis[0], "course": course, "other_university": unis[1], "other_course": other_course}
```

- [ ] **Step 2: Run the tests and confirm they fail.**

Run: `API_TEST tests/test_agn_007_schema.py`
Expected: collection error `ImportError: cannot import name 'AgentStudentShortlistEntry'`.

- [ ] **Step 3: Add the models.** Append to `apps/api/app/models.py` after `class AgentOrgMember`:

```python
class AgentUniversity(Base, TimestampMixin):
    """AGN-007 / DEC-SCOPE-048 D1: an agency's private university ("Add University", Master only). Never part of the shared
    catalogue (`universities`) and never on /public; `org_id` is the tenant key every read filters on."""

    __tablename__ = "agent_universities"
    __table_args__ = (
        Index("uq_agent_universities_org_name_country", "org_id", text("lower(name)"), text("lower(country)"), unique=True),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_orgs.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    entry_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class AgentStudentShortlistEntry(Base, TimestampMixin):
    """AGN-007 / DEC-SCOPE-048: one university on an agency student's shortlist. The university is exactly one of a catalogue
    university or the agency's own (D6); a catalogue course needs a catalogue university (D4). Country is read from the university,
    never stored (D7). Scope is the parent student's (AGN-004 `load_scoped`)."""

    __tablename__ = "agent_student_shortlist_entries"
    __table_args__ = (
        CheckConstraint("(university_id IS NULL) <> (agent_university_id IS NULL)", name="ck_shortlist_one_university"),
        CheckConstraint("course_id IS NULL OR university_id IS NOT NULL", name="ck_shortlist_catalogue_course"),
        CheckConstraint("course_id IS NULL OR course_title IS NULL", name="ck_shortlist_one_course_form"),
        Index("ix_shortlist_student_created", "agent_student_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agent_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_students.id", ondelete="RESTRICT"))
    university_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"), nullable=True)
    agent_university_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_universities.id", ondelete="RESTRICT"), nullable=True, index=True)
    course_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_courses.id", ondelete="RESTRICT"), nullable=True)
    course_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    intake: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tuition_fee: Mapped[str | None] = mapped_column(String(120), nullable=True)
    entry_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
```

`index=True` on `org_id` creates `ix_agent_universities_org_id`, SQLAlchemy's default name. `TimestampMixin.created_at` has `server_default=func.now()`, so the paging order is the insert transaction's time with the `id` tiebreak.

- [ ] **Step 4: Create the migration** `apps/api/alembic/versions/0055_agent_shortlist.py`. Set `down_revision` to the head found in Task 0.

```python
"""AGN-007 -- agency universities and a student's university shortlist (DEC-SCOPE-048).

Revision ID: 0055_agent_shortlist
Revises: <HEAD FROM TASK 0>

docs/superpowers/specs/2026-10-01-agn-007-student-shortlist-design.md §4. Creates two tables only; no existing table or row changes.
0001/0003 run Base.metadata.create_all from the CURRENT models, so a database built from scratch already has both tables when this
runs: each table is created only when missing. downgrade() drops the two new tables (entries first) -- it touches nothing else.
"""

import sqlalchemy as sa

from alembic import op

revision = "0055_agent_shortlist"
down_revision = "<HEAD FROM TASK 0>"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    if op.get_context().as_sql:
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    existing = _tables()
    if "agent_universities" not in existing:
        op.create_table(
            "agent_universities",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("org_id", sa.Uuid(), sa.ForeignKey("agent_orgs.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("country", sa.String(120), nullable=False),
            sa.Column("city", sa.String(120), nullable=True),
            sa.Column("entry_requirements", sa.Text(), nullable=True),
            *_audit_columns(),
        )
        op.create_index("ix_agent_universities_org_id", "agent_universities", ["org_id"])
        op.create_index("uq_agent_universities_org_name_country", "agent_universities", ["org_id", sa.text("lower(name)"), sa.text("lower(country)")], unique=True)
    if "agent_student_shortlist_entries" not in existing:
        op.create_table(
            "agent_student_shortlist_entries",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("agent_student_id", sa.Uuid(), sa.ForeignKey("agent_students.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("university_id", sa.Uuid(), sa.ForeignKey("universities.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("agent_university_id", sa.Uuid(), sa.ForeignKey("agent_universities.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("course_id", sa.Uuid(), sa.ForeignKey("overseas_courses.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("course_title", sa.String(200), nullable=True),
            sa.Column("intake", sa.String(120), nullable=True),
            sa.Column("tuition_fee", sa.String(120), nullable=True),
            sa.Column("entry_requirements", sa.Text(), nullable=True),
            *_audit_columns(),
            sa.CheckConstraint("(university_id IS NULL) <> (agent_university_id IS NULL)", name="ck_shortlist_one_university"),
            sa.CheckConstraint("course_id IS NULL OR university_id IS NOT NULL", name="ck_shortlist_catalogue_course"),
            sa.CheckConstraint("course_id IS NULL OR course_title IS NULL", name="ck_shortlist_one_course_form"),
        )
        op.create_index("ix_shortlist_student_created", "agent_student_shortlist_entries", ["agent_student_id", "created_at", "id"])
        op.create_index("ix_agent_student_shortlist_entries_agent_university_id", "agent_student_shortlist_entries", ["agent_university_id"])


def downgrade() -> None:
    op.drop_table("agent_student_shortlist_entries")
    op.drop_table("agent_universities")
```

`_audit_columns` matches `TimestampMixin` (models.py L14, verified: `DateTime(timezone=True)`, `server_default=func.now()`, NOT NULL), so the model-built database (create_all) and the migrated database agree.

- [ ] **Step 5: Add the schemas.** Append to `apps/api/app/schemas.py` after `class AgentStudentAssign`:

```python
# AGN-007 (DEC-SCOPE-048, spec §5.3): agency universities and shortlist entries. Server-owned fields (agency, student, authors) are
# never accepted -- `extra="forbid"` answers 422 (mass assignment). Text goes through clean_free_text (NUL/bidi refused, blank -> None).
UNIVERSITY_LIMITS = {"name": 200, "country": 120, "city": 120, "entry_requirements": 2000}
ENTRY_LIMITS = {"course_title": 200, "intake": 120, "tuition_fee": 120, "entry_requirements": 2000}


class _AgentUniversityFields(BaseModel):
    model_config = {"extra": "forbid"}
    name: str | None = None
    country: str | None = None
    city: str | None = None
    entry_requirements: str | None = None

    @field_validator("name", "country", "city", "entry_requirements")
    @classmethod
    def _text(cls, value, info):
        return clean_free_text(value, UNIVERSITY_LIMITS[info.field_name])


class AgentUniversityCreate(_AgentUniversityFields):
    name: str
    country: str

    @model_validator(mode="after")
    def _required(self):
        if not self.name or not self.country:
            raise PydanticCustomError("required", "Name and country are required")
        return self


class AgentUniversityUpdate(_AgentUniversityFields):
    """Omitted = unchanged; null clears city / entry requirements; name and country cannot be cleared."""

    @model_validator(mode="after")
    def _not_cleared(self):
        for field in ("name", "country"):
            if field in self.model_fields_set and not getattr(self, field):
                raise PydanticCustomError("required", "Name and country cannot be empty")
        return self


class _ShortlistEntryFields(BaseModel):
    model_config = {"extra": "forbid"}
    university_id: UUID | None = None
    agent_university_id: UUID | None = None
    course_id: UUID | None = None
    course_title: str | None = None
    intake: str | None = None
    tuition_fee: str | None = None
    entry_requirements: str | None = None

    @field_validator("course_title", "intake", "tuition_fee", "entry_requirements")
    @classmethod
    def _text(cls, value, info):
        return clean_free_text(value, ENTRY_LIMITS[info.field_name])


class ShortlistEntryCreate(_ShortlistEntryFields):
    """The university rules (exactly one source, course belongs) need the database: services/agent_shortlist.validate_entry."""


class ShortlistEntryUpdate(_ShortlistEntryFields):
    """Omitted = unchanged; null clears. The merged row is validated as a whole (spec §5.4)."""
```

`clean_free_text` raises `ValueError`, which Pydantic turns into a 422. A whitespace-only `name` becomes `None` and then fails `_required`. `PydanticCustomError` and `model_validator` are already imported in `schemas.py` (the AGN-004 block uses them).

- [ ] **Step 6: Run the tests and confirm they pass.**

Run: `API_TEST tests/test_agn_007_schema.py tests/test_agn_004_migration.py`
Expected: all pass. `test_agn_004_migration.py` still asserts one head.

- [ ] **Step 7: Prove the migration round trip on a throwaway database.**

Append to `test_agn_007_schema.py` (the AGN-004 throwaway-database pattern; plain tests, because alembic's env.py calls `asyncio.run` itself):

```python
import asyncio

import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
BASE = _migration.down_revision
NEW_TABLES = {"agent_universities", "agent_student_shortlist_entries"}


def _sql(url: str, sql: str, params: dict | None = None, *, autocommit: bool = False):
    async def _inner():
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT") if autocommit else create_async_engine(url)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(sa.text(sql), params or {})
                return result.fetchall() if result.returns_rows else None
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def _tables(url: str) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


def test_round_trip_keeps_existing_rows_and_drops_only_new_tables():
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"agn007_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)  # 0001/0003 create_all from the CURRENT models, so the new tables may already exist here
        before = _sql(url, "SELECT count(*) FROM agent_students")
        command.upgrade(cfg, "0055_agent_shortlist")
        assert NEW_TABLES <= _tables(url)
        assert _sql(url, "SELECT count(*) FROM agent_students") == before
        command.downgrade(cfg, BASE)
        assert not NEW_TABLES & _tables(url)
        assert _sql(url, "SELECT count(*) FROM agent_students") == before
        command.upgrade(cfg, "0055_agent_shortlist")
        assert NEW_TABLES <= _tables(url)
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)
```

This proves that upgrade creates the tables (or finds them), downgrade removes only them, and re-upgrade works, all while existing rows stay. Run it and expect PASS.

- [ ] **Step 8: Commit.**

```bash
git add apps/api/app/models.py apps/api/app/schemas.py apps/api/alembic/versions/0055_agent_shortlist.py apps/api/tests/agn007_helpers.py apps/api/tests/test_agn_007_schema.py
git commit -m "feat(agn-007): agency university and shortlist tables, migration and request schemas"
```

---

### Task 2: Agency universities API (list, create, edit, delete)

**Files:**
- Create: `apps/api/app/services/agent_shortlist.py` (university part)
- Create: `apps/api/app/api/agent_shortlist.py` (university routes)
- Modify: `apps/api/app/main.py` (import `agent_shortlist` next to `agent_students`; add `agent_shortlist.router` to the router tuple right after `agent_students.router`)
- Test: `apps/api/tests/test_agn_007_universities.py`

**Interfaces:**
- Consumes:
  - from Task 1: the models and schemas;
  - from AGN-004: `app.api.agent_students._gate(user) -> AgentOrgMember`, `_require_master_action(user, message)`, `_log(event, membership, user, student_id, **extra)`;
  - `app.services.agent_orgs.lock_active_org(db, org_id)`;
  - `app.services.agent_students._contains(column, term)`.
- Produces (service):
  - `university_item(row) -> dict`
  - `university_page(db, org_id, *, q, limit, offset) -> dict`
  - `load_university(db, org_id, university_id, *, lock=False) -> AgentUniversity` (404)
  - `ensure_university_capacity(db, org_id)` (422)
  - `ensure_unique_university(db, org_id, name, country, exclude_id=None)` (409)
  - `university_usage(db, university_id) -> int`
  - `apply_changes(row, changes: dict, user) -> list[str]`
  - constants `MAX_UNIVERSITIES_PER_AGENCY = 500`, `DUPLICATE_UNIVERSITY`
- Produces (router): `router = APIRouter(prefix="/workflows/overseas/agent/crm", tags=["agent-shortlist"])`.

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_agn_007_universities.py`:

```python
"""AGN-007 -- the agency's own universities (spec §5.1; AC06, AC09, AC10 universities cap, AC11)."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentStudentShortlistEntry, AgentUniversity, AuditLog
from app.services import agent_shortlist as service
from tests.agn001_helpers import client_for, mk_active_org
from tests.agn004_helpers import mk_record, mk_staff
from tests.agn007_helpers import UNIVERSITIES


@pytest_asyncio.fixture
async def agency(db_session):
    ctx = await mk_active_org(db_session, name="Uni Agency")
    other = await mk_active_org(db_session, name="Uni Other Agency")
    staff = await mk_staff(db_session, ctx["org"], full_name="Uni Staff")
    return ctx | {"other": other, "staff": staff, "tag": uuid.uuid4().hex[:8]}


async def _add(client, name: str, country: str = "Ireland", **extra):
    return await client.post(UNIVERSITIES, json={"name": name, "country": country, **extra})


@pytest.mark.asyncio
async def test_master_adds_edits_and_deletes_with_audit(db_session, agency):  # AGN-007-AC06
    async with client_for(agency["master"].email) as m:
        created = await _add(m, f"Trinity {agency['tag']}", city="Dublin", entry_requirements="IELTS 6.5")
        assert created.status_code == 201, created.text
        body = created.json()["university"]
        assert set(body) == {"id", "name", "country", "city", "entry_requirements", "created_at", "updated_at"}
        uid = body["id"]
        edited = await m.patch(f"{UNIVERSITIES}/{uid}", json={"city": None})
        assert edited.status_code == 200 and edited.json()["university"]["city"] is None
        assert (await m.delete(f"{UNIVERSITIES}/{uid}")).status_code == 204
        assert (await m.delete(f"{UNIVERSITIES}/{uid}")).status_code == 404
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == uid).order_by(AuditLog.created_at))).all()
    assert actions == ["agent_university.create", "agent_university.update", "agent_university.delete"]
    meta = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == uid, AuditLog.action == "agent_university.update"))).one()
    assert meta == {"fields": ["city"]}  # field names, never values


@pytest.mark.asyncio
async def test_staff_view_but_cannot_write(db_session, agency):  # AGN-007-AC06
    async with client_for(agency["master"].email) as m:
        uid = (await _add(m, f"Staff Visible {agency['tag']}")).json()["university"]["id"]
    async with client_for(agency["staff"]["user"].email) as s:
        listing = await s.get(UNIVERSITIES)
        assert listing.status_code == 200 and uid in [u["id"] for u in listing.json()["items"]]
        refused = [
            (await _add(s, "Staff Made"), "Only an agency Master can add universities"),
            (await s.patch(f"{UNIVERSITIES}/{uid}", json={"city": "X"}), "Only an agency Master can edit universities"),
            (await s.delete(f"{UNIVERSITIES}/{uid}"), "Only an agency Master can delete universities"),
        ]
    for response, detail in refused:
        assert response.status_code == 403 and response.json()["detail"] == detail
    assert await db_session.scalar(select(func.count()).select_from(AgentUniversity).where(AgentUniversity.name == "Staff Made")) == 0
    row = await db_session.get(AgentUniversity, uuid.UUID(uid), populate_existing=True)
    assert row.city is None
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == uid)) == 1  # the create only


@pytest.mark.asyncio
async def test_other_agency_cannot_see_or_touch(agency):  # AGN-007-AC04 (universities)
    async with client_for(agency["master"].email) as m:
        uid = (await _add(m, f"Private {agency['tag']}")).json()["university"]["id"]
    async with client_for(agency["other"]["master"].email) as o:
        assert uid not in [u["id"] for u in (await o.get(UNIVERSITIES, params={"limit": 100})).json()["items"]]
        assert (await o.patch(f"{UNIVERSITIES}/{uid}", json={"city": "X"})).status_code == 404
        assert (await o.delete(f"{UNIVERSITIES}/{uid}")).status_code == 404
        assert (await _add(o, f"Private {agency['tag']}")).status_code == 201  # same name in another agency is fine


@pytest.mark.asyncio
async def test_duplicate_name_and_country_is_409(agency):  # AGN-007-AC09
    async with client_for(agency["master"].email) as m:
        assert (await _add(m, f"Dup {agency['tag']}")).status_code == 201
        twin = await _add(m, f"DUP {agency['tag']}".upper(), "IRELAND")
        assert twin.status_code == 409 and twin.json()["detail"] == "This university is already in your agency's list"
        other = (await _add(m, f"Other {agency['tag']}")).json()["university"]["id"]
        renamed = await m.patch(f"{UNIVERSITIES}/{other}", json={"name": f"dup {agency['tag']}"})
        assert renamed.status_code == 409


@pytest.mark.asyncio
async def test_delete_in_use_is_409_and_keeps_everything(db_session, agency):  # AGN-007-AC09
    async with client_for(agency["master"].email) as m:
        uid = (await _add(m, f"In Use {agency['tag']}")).json()["university"]["id"]
    student = await mk_record(db_session, agent=agency["master"], full_name="In Use Student")
    db_session.add(AgentStudentShortlistEntry(agent_student_id=student.id, agent_university_id=uuid.UUID(uid)))
    await db_session.commit()
    async with client_for(agency["master"].email) as m:
        response = await m.delete(f"{UNIVERSITIES}/{uid}")
    assert response.status_code == 409
    assert response.json()["detail"] == "This university is on 1 shortlist entry; remove it from them first"
    assert await db_session.get(AgentUniversity, uuid.UUID(uid), populate_existing=True) is not None


@pytest.mark.asyncio
async def test_university_cap_is_422(db_session, agency, monkeypatch):  # AGN-007-AC10 (agency cap)
    monkeypatch.setattr(service, "MAX_UNIVERSITIES_PER_AGENCY", 2)
    async with client_for(agency["master"].email) as m:
        assert (await _add(m, f"Cap1 {agency['tag']}")).status_code == 201
        assert (await _add(m, f"Cap2 {agency['tag']}")).status_code == 201
        third = await _add(m, f"Cap3 {agency['tag']}")
    assert third.status_code == 422 and third.json()["detail"] == "Your agency has reached the limit of 2 universities"


@pytest.mark.asyncio
async def test_list_pages_searches_and_bounds(agency):  # AGN-007-AC11
    async with client_for(agency["master"].email) as m:
        for n in ("Beta", "alpha", "Gamma"):
            await _add(m, f"{n} {agency['tag']}", city="Cork" if n == "Gamma" else None)
        page = (await m.get(UNIVERSITIES, params={"q": agency["tag"], "limit": 2})).json()
        assert [u["name"] for u in page["items"]] == [f"alpha {agency['tag']}", f"Beta {agency['tag']}"] and page["total"] == 3
        assert (await m.get(UNIVERSITIES, params={"q": "Cork"})).json()["total"] >= 1
        assert (await m.get(UNIVERSITIES, params={"q": agency["tag"], "offset": 50})).json() == {"items": [], "total": 3, "limit": 20, "offset": 50}
        assert (await m.get(UNIVERSITIES, params={"q": "100%_"})).status_code == 200  # escaped, not a wildcard
        for bad in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
            assert (await m.get(UNIVERSITIES, params=bad)).status_code == 422


@pytest.mark.asyncio
async def test_inactive_agency_and_non_agents_are_refused(db_session, agency):
    from app.models import AgentOrg
    from tests.agn001_helpers import mk_user

    org = await db_session.get(AgentOrg, agency["other"]["org"].id, populate_existing=True)
    org.status = "suspended"
    await db_session.commit()
    async with client_for(agency["other"]["master"].email) as o:
        assert (await o.get(UNIVERSITIES)).status_code == 403
    admin = await mk_user(db_session, role="super_admin", division="global")
    async with client_for(admin.email) as a:
        assert (await a.get(UNIVERSITIES)).status_code == 403
```

The pluralised in-use message: `"…on 1 shortlist entry…"` for one and `"…on N shortlist entries…"` for more. The service builds it from the count.

- [ ] **Step 2: Run the tests and confirm they fail.**

Run: `API_TEST tests/test_agn_007_universities.py`
Expected: FAIL. `ImportError` on `app.services.agent_shortlist`, or 404s.

- [ ] **Step 3: Write the service (university part)** `apps/api/app/services/agent_shortlist.py`:

```python
"""AGN-007 / DEC-SCOPE-048 -- an agency's own universities and a student's university shortlist.

Functions only (the shape of services/agent_students.py); write functions never commit -- the router locks the agency, writes,
audits and commits once. Spec: docs/superpowers/specs/2026-10-01-agn-007-student-shortlist-design.md.
"""

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentStudentShortlistEntry, AgentUniversity, User
from app.services.agent_students import _contains

MAX_UNIVERSITIES_PER_AGENCY = 500
DUPLICATE_UNIVERSITY = "This university is already in your agency's list"


def university_item(row: AgentUniversity) -> dict:
    return {"id": row.id, "name": row.name, "country": row.country, "city": row.city, "entry_requirements": row.entry_requirements, "created_at": row.created_at, "updated_at": row.updated_at}


async def university_page(db: AsyncSession, org_id, *, q: str | None, limit: int, offset: int) -> dict:
    filters = [AgentUniversity.org_id == org_id]
    term = (q or "").strip()
    if term:
        filters.append(or_(_contains(AgentUniversity.name, term), _contains(AgentUniversity.country, term), _contains(AgentUniversity.city, term)))
    total = await db.scalar(select(func.count()).select_from(AgentUniversity).where(*filters))
    rows = (await db.scalars(select(AgentUniversity).where(*filters).order_by(func.lower(AgentUniversity.name), AgentUniversity.id).limit(limit).offset(offset))).all()
    return {"items": [university_item(r) for r in rows], "total": total or 0, "limit": limit, "offset": offset}


async def load_university(db: AsyncSession, org_id, university_id, *, lock: bool = False) -> AgentUniversity:
    """The caller's agency's university or 404 -- the agency is in the WHERE clause, never checked after loading."""
    stmt = select(AgentUniversity).where(AgentUniversity.id == university_id, AgentUniversity.org_id == org_id).execution_options(populate_existing=True)
    row = await db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise HTTPException(404, "University not found")
    return row


async def ensure_university_capacity(db: AsyncSession, org_id) -> None:
    count = await db.scalar(select(func.count()).select_from(AgentUniversity).where(AgentUniversity.org_id == org_id))
    if count >= MAX_UNIVERSITIES_PER_AGENCY:
        raise HTTPException(422, f"Your agency has reached the limit of {MAX_UNIVERSITIES_PER_AGENCY} universities")


async def ensure_unique_university(db: AsyncSession, org_id, name: str, country: str, exclude_id=None) -> None:
    stmt = select(AgentUniversity.id).where(AgentUniversity.org_id == org_id, func.lower(AgentUniversity.name) == name.lower(), func.lower(AgentUniversity.country) == country.lower())
    if exclude_id is not None:
        stmt = stmt.where(AgentUniversity.id != exclude_id)
    if await db.scalar(stmt.limit(1)) is not None:
        raise HTTPException(409, DUPLICATE_UNIVERSITY)


async def university_usage(db: AsyncSession, university_id) -> int:
    return await db.scalar(select(func.count()).select_from(AgentStudentShortlistEntry).where(AgentStudentShortlistEntry.agent_university_id == university_id)) or 0


def in_use_message(count: int) -> str:
    return f"This university is on {count} shortlist {'entry' if count == 1 else 'entries'}; remove it from them first"


def apply_changes(row, changes: dict, user: User) -> list[str]:
    """Sets only the fields whose value differs; returns their names (sorted). Nothing changed -> [] and no audit (AGN-004)."""
    changed = sorted(k for k, v in changes.items() if getattr(row, k) != v)
    for key in changed:
        setattr(row, key, changes[key])
    if changed:
        row.updated_by_user_id = user.id
    return changed
```

The cap message must read the module constant at call time, because the test monkeypatches it. The f-string above does that.

- [ ] **Step 4: Write the router (university part)** `apps/api/app/api/agent_shortlist.py`:

```python
"""AGN-007 -- an agency's own universities and a student's university shortlist (DEC-SCOPE-048; spec §5).

Reuses AGN-004's gate, lock order and scoped load unchanged (api/agent_students.py is imported, not edited). Every write locks the
agency, loads its rows FOR UPDATE, validates, writes, audits in the same transaction and commits once, so the caps, the duplicate
check and in-use deletes hold under concurrency. Another agency's rows are 404 (or 422 when named inside a body), never 403.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_students import _gate, _log, _require_master_action
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AgentUniversity, AuditLog, User
from app.schemas import AgentUniversityCreate, AgentUniversityUpdate
from app.services.agent_orgs import lock_active_org
from app.services.agent_shortlist import (
    DUPLICATE_UNIVERSITY,
    apply_changes,
    ensure_unique_university,
    ensure_university_capacity,
    in_use_message,
    load_university,
    university_item,
    university_page,
    university_usage,
)

router = APIRouter(prefix="/workflows/overseas/agent/crm", tags=["agent-shortlist"])


def _university_audit(db: AsyncSession, user: User, action: str, university_id, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed, SEC-001); ids and field names only."""
    db.add(AuditLog(user_id=user.id, action=f"agent_university.{action}", entity_type="agent_university", entity_id=str(university_id), metadata_json=metadata or {}))


async def _commit(db: AsyncSession, conflict: str) -> None:
    """The unique index and RESTRICT foreign keys back the locked checks; a violation is the matching 409, never a 500."""
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, conflict) from None


@router.get("/universities")
async def list_universities(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    membership = _gate(user)
    return await university_page(db, membership.org_id, q=q, limit=limit, offset=offset)


@router.post("/universities", status_code=201)
async def create_university(payload: AgentUniversityCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    _require_master_action(user, "Only an agency Master can add universities")
    await lock_active_org(db, membership.org_id)
    await ensure_university_capacity(db, membership.org_id)
    await ensure_unique_university(db, membership.org_id, payload.name, payload.country)
    data = payload.model_dump()
    row = AgentUniversity(org_id=membership.org_id, **data, created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(row)
    await db.flush()
    _university_audit(db, user, "create", row.id, {"fields": sorted(k for k, v in data.items() if v is not None)})
    await _commit(db, DUPLICATE_UNIVERSITY)
    _log("agent_university_created", membership, user, "-", university_id=str(row.id))
    return {"university": university_item(row)}


@router.patch("/universities/{university_id}")
async def update_university(university_id: UUID, payload: AgentUniversityUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    await lock_active_org(db, membership.org_id)
    row = await load_university(db, membership.org_id, university_id, lock=True)  # 404 before the role check
    _require_master_action(user, "Only an agency Master can edit universities")
    changes = payload.model_dump(exclude_unset=True)
    if {"name", "country"} & changes.keys():
        await ensure_unique_university(db, membership.org_id, changes.get("name", row.name), changes.get("country", row.country), exclude_id=row.id)
    changed = apply_changes(row, changes, user)
    if changed:
        _university_audit(db, user, "update", row.id, {"fields": changed})
    await _commit(db, DUPLICATE_UNIVERSITY)
    return {"university": university_item(row)}


@router.delete("/universities/{university_id}", status_code=204)
async def delete_university(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    await lock_active_org(db, membership.org_id)
    row = await load_university(db, membership.org_id, university_id, lock=True)
    _require_master_action(user, "Only an agency Master can delete universities")
    used = await university_usage(db, row.id)
    if used:
        raise HTTPException(409, in_use_message(used))
    _university_audit(db, user, "delete", row.id)
    await db.delete(row)
    await _commit(db, in_use_message(1))
    return Response(status_code=204)
```

In `apps/api/app/main.py`, add `agent_shortlist,` to the `from app.api import (...)` block next to `agent_students,`. Add `agent_shortlist.router` immediately after `agent_students.router` in the router tuple on line 63.

- [ ] **Step 5: Run the tests and confirm they pass.**

Run: `API_TEST tests/test_agn_007_universities.py`
Expected: all pass.

- [ ] **Step 6: Commit.**

```bash
git add apps/api/app/services/agent_shortlist.py apps/api/app/api/agent_shortlist.py apps/api/app/main.py apps/api/tests/test_agn_007_universities.py
git commit -m "feat(agn-007): agency university database -- Master full, Staff view"
```

---

### Task 3: Shortlist API (list, add, edit, remove)

**Files:**
- Modify: `apps/api/app/services/agent_shortlist.py` (append the entry part)
- Modify: `apps/api/app/api/agent_shortlist.py` (append the shortlist routes)
- Test: `apps/api/tests/test_agn_007_shortlist.py`

**Interfaces:**
- Consumes: Task 2's `router`, `_commit`, `apply_changes`; AGN-004's `_audit(db, user, action, student_id, metadata)`, `_locked_row(db, user, membership, student_id)`, `load_scoped(db, user, student_id)`.
- Produces (service):
  - `MAX_ENTRIES_PER_STUDENT = 50`, `ENTRY_FIELDS`, `COURSE_MISMATCH`
  - `entry_item(...)`
  - `entry_page(db, student_id, *, limit, offset) -> dict`
  - `entry_detail(db, entry_id) -> dict`
  - `load_entry(db, student_id, entry_id, *, lock=False)` (404)
  - `entry_values(entry) -> dict`
  - `validate_entry(db, org_id, values: dict)` (422)
  - `ensure_entry_capacity(db, student_id)` (422)
- Produces (routes): `GET/POST /students/{student_id}/shortlist`, `PATCH/DELETE /students/{student_id}/shortlist/{entry_id}`.

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_agn_007_shortlist.py`:

```python
"""AGN-007 -- a student's university shortlist (spec §5.2, §5.4; AC01, AC02, AC03, AC07, AC08, AC11, Review Focus 1)."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentStudent, AgentStudentShortlistEntry, AuditLog, UserRoleAssignment
from app.services import agent_shortlist as service
from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn004_helpers import mk_record, mk_staff
from tests.agn007_helpers import UNIVERSITIES, mk_catalogue, shortlist


@pytest_asyncio.fixture
async def world(db_session):
    ctx = await mk_active_org(db_session, name="List Agency")
    s1 = await mk_staff(db_session, ctx["org"], full_name="List Staff One")
    s2 = await mk_staff(db_session, ctx["org"], full_name="List Staff Two")
    mine = await mk_record(db_session, agent=ctx["master"], full_name="Assigned To S1", assigned_member=s1["member"])
    theirs = await mk_record(db_session, agent=ctx["master"], full_name="Assigned To S2", assigned_member=s2["member"])
    cat = await mk_catalogue(db_session)
    async with client_for(ctx["master"].email) as m:
        agency_uni = (await m.post(UNIVERSITIES, json={"name": f"Agency U {uuid.uuid4().hex[:6]}", "country": "Malta", "entry_requirements": "Interview"})).json()["university"]
    return ctx | {"s1": s1, "s2": s2, "mine": mine, "theirs": theirs, "cat": cat, "agency_uni": agency_uni}


def _catalogue_body(w) -> dict:
    return {"university_id": str(w["cat"]["university"].id), "course_id": str(w["cat"]["course"].id), "intake": "Sep 2027", "tuition_fee": "EUR 20,000", "entry_requirements": "IELTS 6.5"}


@pytest.mark.asyncio
async def test_catalogue_entry_saves(world):  # AGN-007-AC01
    async with client_for(world["s1"]["user"].email) as s:
        response = await s.post(shortlist(world["mine"].id), json=_catalogue_body(world))
        assert response.status_code == 201, response.text
        entry = response.json()["entry"]
        listed = (await s.get(shortlist(world["mine"].id))).json()
    assert entry["university"] == {"source": "catalogue", "id": str(world["cat"]["university"].id), "name": world["cat"]["university"].name, "slug": world["cat"]["university"].slug, "country": world["cat"]["country"].name}
    assert entry["course"] == {"id": str(world["cat"]["course"].id), "title": world["cat"]["course"].title}
    assert (entry["intake"], entry["tuition_fee"], entry["entry_requirements"]) == ("Sep 2027", "EUR 20,000", "IELTS 6.5")
    assert entry["created_by"] == "List Staff One"
    assert listed["total"] == 1 and listed["items"][0]["id"] == entry["id"]


@pytest.mark.asyncio
async def test_free_text_entry_saves(world):  # AGN-007-AC02
    async with client_for(world["master"].email) as m:
        response = await m.post(shortlist(world["mine"].id), json={"agent_university_id": world["agency_uni"]["id"], "course_title": "BA Typed", "intake": "Feb 2028"})
    assert response.status_code == 201, response.text
    entry = response.json()["entry"]
    assert entry["university"] == {"source": "agency", "id": world["agency_uni"]["id"], "name": world["agency_uni"]["name"], "slug": None, "country": "Malta"}
    assert entry["course"] == {"id": None, "title": "BA Typed"}


@pytest.mark.asyncio
async def test_catalogue_university_with_typed_course_saves(world):  # D4
    async with client_for(world["master"].email) as m:
        response = await m.post(shortlist(world["mine"].id), json={"university_id": str(world["cat"]["university"].id), "course_title": "Not in catalogue"})
    assert response.status_code == 201 and response.json()["entry"]["course"] == {"id": None, "title": "Not in catalogue"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("make_body", "detail"),
    [
        (lambda w: {"university_id": str(w["cat"]["university"].id), "course_id": str(w["cat"]["other_course"].id)}, "Course does not belong to selected university"),
        (lambda w: {"agent_university_id": w["agency_uni"]["id"], "course_id": str(w["cat"]["course"].id)}, "Catalogue courses can only be chosen with a catalogue university"),
        (lambda w: {"university_id": str(w["cat"]["university"].id), "agent_university_id": w["agency_uni"]["id"]}, "Choose a catalogue university or one of your agency's universities"),
        (lambda w: {"intake": "Sep"}, "Choose a catalogue university or one of your agency's universities"),
        (lambda w: {"university_id": str(w["cat"]["university"].id), "course_id": str(w["cat"]["course"].id), "course_title": "Both"}, "Choose a catalogue course or type a course, not both"),
        (lambda w: {"university_id": str(uuid.uuid4())}, "University not found"),
        (lambda w: {"university_id": str(w["cat"]["university"].id), "course_id": str(uuid.uuid4())}, "Course does not belong to selected university"),
    ],
)
async def test_invalid_entries_are_422_and_write_nothing(db_session, world, make_body, detail):  # AGN-007-AC03
    async with client_for(world["master"].email) as m:
        response = await m.post(shortlist(world["mine"].id), json=make_body(world))
    assert response.status_code == 422 and response.json()["detail"] == detail
    assert await db_session.scalar(select(func.count()).select_from(AgentStudentShortlistEntry).where(AgentStudentShortlistEntry.agent_student_id == world["mine"].id)) == 0
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(world["mine"].id))) == 0


@pytest.mark.asyncio
async def test_edit_and_remove_with_audit(db_session, world):  # AGN-007-AC07 (+ AC12 shape)
    async with client_for(world["s1"]["user"].email) as s:
        eid = (await s.post(shortlist(world["mine"].id), json=_catalogue_body(world))).json()["entry"]["id"]
        edited = await s.patch(f"{shortlist(world['mine'].id)}/{eid}", json={"intake": "Jan 2028", "tuition_fee": None})
        assert edited.status_code == 200 and (edited.json()["entry"]["intake"], edited.json()["entry"]["tuition_fee"]) == ("Jan 2028", None)
        same = await s.patch(f"{shortlist(world['mine'].id)}/{eid}", json={"intake": "Jan 2028"})
        assert same.status_code == 200
        assert (await s.delete(f"{shortlist(world['mine'].id)}/{eid}")).status_code == 204
        assert (await s.delete(f"{shortlist(world['mine'].id)}/{eid}")).status_code == 404
    rows = (await db_session.execute(select(AuditLog.action, AuditLog.metadata_json).where(AuditLog.entity_id == str(world["mine"].id)).order_by(AuditLog.created_at))).all()
    assert [a for a, _ in rows] == ["agent_student.shortlist_add", "agent_student.shortlist_update", "agent_student.shortlist_remove"]
    assert rows[0][1] == {"entry_id": eid, "university_source": "catalogue", "fields": ["course_id", "entry_requirements", "intake", "tuition_fee", "university_id"]}
    assert rows[1][1] == {"entry_id": eid, "fields": ["intake", "tuition_fee"]}
    assert rows[2][1] == {"entry_id": eid}


@pytest.mark.asyncio
async def test_patch_switching_university_with_a_stale_course_is_422(world):  # Review Focus 1
    async with client_for(world["master"].email) as m:
        eid = (await m.post(shortlist(world["mine"].id), json=_catalogue_body(world))).json()["entry"]["id"]
        url = f"{shortlist(world['mine'].id)}/{eid}"
        stale = await m.patch(url, json={"university_id": str(world["cat"]["other_university"].id)})
        assert stale.status_code == 422 and stale.json()["detail"] == "Course does not belong to selected university"
        to_agency = await m.patch(url, json={"university_id": None, "agent_university_id": world["agency_uni"]["id"], "course_id": None, "course_title": "Typed"})
        assert to_agency.status_code == 200 and to_agency.json()["entry"]["university"]["source"] == "agency"


@pytest.mark.asyncio
async def test_staff_scope_is_404_before_any_role_check(world):  # AGN-007-AC07
    async with client_for(world["master"].email) as m:
        eid = (await m.post(shortlist(world["theirs"].id), json={"agent_university_id": world["agency_uni"]["id"]})).json()["entry"]["id"]
    async with client_for(world["s1"]["user"].email) as s:
        for response in (
            await s.get(shortlist(world["theirs"].id)),
            await s.post(shortlist(world["theirs"].id), json={"agent_university_id": world["agency_uni"]["id"]}),
            await s.patch(f"{shortlist(world['theirs'].id)}/{eid}", json={"intake": "X"}),
            await s.delete(f"{shortlist(world['theirs'].id)}/{eid}"),
        ):
            assert response.status_code == 404 and response.json()["detail"] == "Student not found"
        # an entry id of another student, under my own student, is not found
        assert (await s.patch(f"{shortlist(world['mine'].id)}/{eid}", json={"intake": "X"})).status_code == 404


@pytest.mark.asyncio
async def test_archived_is_read_only_and_linked_is_writable(db_session, world):  # AGN-007-AC08
    archived = await mk_record(db_session, agent=world["master"], full_name="Archived One", status="archived")
    student_user = await mk_user(db_session, role="overseas_student")
    linked = AgentStudent(agent_id=world["master"].id, student_id=student_user.id, status="active")
    db_session.add(linked)
    await db_session.commit()
    body = {"agent_university_id": world["agency_uni"]["id"]}
    async with client_for(world["master"].email) as m:
        assert (await m.get(shortlist(archived.id))).status_code == 200
        refused = await m.post(shortlist(archived.id), json=body)
        assert refused.status_code == 409 and refused.json()["detail"] == "Unarchive this student first"
        assert (await m.post(shortlist(linked.id), json=body)).status_code == 201


@pytest.mark.asyncio
async def test_entry_cap_is_422(world, monkeypatch):  # AGN-007-AC10
    monkeypatch.setattr(service, "MAX_ENTRIES_PER_STUDENT", 2)
    body = {"agent_university_id": world["agency_uni"]["id"]}
    async with client_for(world["master"].email) as m:
        assert [(await m.post(shortlist(world["mine"].id), json=body)).status_code for _ in range(2)] == [201, 201]
        third = await m.post(shortlist(world["mine"].id), json=body)
    assert third.status_code == 422 and third.json()["detail"] == "This student's shortlist is full (2 entries)"


@pytest.mark.asyncio
async def test_paging_is_stable_and_bounded(world):  # AGN-007-AC11
    body = {"agent_university_id": world["agency_uni"]["id"]}
    async with client_for(world["master"].email) as m:
        ids = [(await m.post(shortlist(world["mine"].id), json=body | {"intake": str(i)})).json()["entry"]["id"] for i in range(3)]
        first = (await m.get(shortlist(world["mine"].id), params={"limit": 2})).json()
        second = (await m.get(shortlist(world["mine"].id), params={"limit": 2, "offset": 2})).json()
        assert [e["id"] for e in first["items"] + second["items"]] == ids and first["total"] == 3
        assert (await m.get(shortlist(world["mine"].id), params={"offset": 10})).json() == {"items": [], "total": 3, "limit": 20, "offset": 10}
        for bad in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
            assert (await m.get(shortlist(world["mine"].id), params=bad)).status_code == 422
```

The paging test relies on insertion order. `created_at` comes from `func.now()` per transaction, so three separate commits get increasing timestamps. Ties fall back to `id`. If `TimestampMixin` uses a server default, the order still holds across commits.

- [ ] **Step 2: Run the tests and confirm they fail.**

Run: `API_TEST tests/test_agn_007_shortlist.py`
Expected: FAIL with 404/405 on the shortlist routes.

- [ ] **Step 3: Append the entry part to the service** `apps/api/app/services/agent_shortlist.py`. Extend the imports to `from app.models import AgentStudentShortlistEntry, AgentUniversity, Country, OverseasCourse, University, User`.

```python
MAX_ENTRIES_PER_STUDENT = 50
ENTRY_FIELDS = ("university_id", "agent_university_id", "course_id", "course_title", "intake", "tuition_fee", "entry_requirements")
COURSE_MISMATCH = "Course does not belong to selected university"  # verbatim from workflows.py (OVS-002)
Entry = AgentStudentShortlistEntry


def _entry_stmt():
    return (
        select(Entry, University, Country, AgentUniversity, OverseasCourse, User)
        .outerjoin(University, University.id == Entry.university_id)
        .outerjoin(Country, Country.id == University.country_id)
        .outerjoin(AgentUniversity, AgentUniversity.id == Entry.agent_university_id)
        .outerjoin(OverseasCourse, OverseasCourse.id == Entry.course_id)
        .outerjoin(User, User.id == Entry.created_by_user_id)
    )


def entry_item(entry: Entry, university: University | None, country: Country | None, agency: AgentUniversity | None, course: OverseasCourse | None, creator: User | None) -> dict:
    """Explicit allowlist. Country comes from the university, never from the entry (D7)."""
    if university is not None:
        uni = {"source": "catalogue", "id": university.id, "name": university.name, "slug": university.slug, "country": country.name if country else None}
    else:
        uni = {"source": "agency", "id": agency.id, "name": agency.name, "slug": None, "country": agency.country}
    if course is not None:
        course_out = {"id": course.id, "title": course.title}
    elif entry.course_title:
        course_out = {"id": None, "title": entry.course_title}
    else:
        course_out = None
    return {
        "id": entry.id, "university": uni, "course": course_out, "intake": entry.intake, "tuition_fee": entry.tuition_fee,
        "entry_requirements": entry.entry_requirements, "created_by": creator.full_name if creator else None,
        "created_at": entry.created_at, "updated_at": entry.updated_at,
    }


async def entry_page(db: AsyncSession, student_id, *, limit: int, offset: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(Entry).where(Entry.agent_student_id == student_id))
    rows = (await db.execute(_entry_stmt().where(Entry.agent_student_id == student_id).order_by(Entry.created_at, Entry.id).limit(limit).offset(offset))).all()
    return {"items": [entry_item(*r) for r in rows], "total": total or 0, "limit": limit, "offset": offset}


async def entry_detail(db: AsyncSession, entry_id) -> dict:
    return entry_item(*(await db.execute(_entry_stmt().where(Entry.id == entry_id).execution_options(populate_existing=True))).one())


async def load_entry(db: AsyncSession, student_id, entry_id, *, lock: bool = False) -> Entry:
    stmt = select(Entry).where(Entry.id == entry_id, Entry.agent_student_id == student_id).execution_options(populate_existing=True)
    row = await db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise HTTPException(404, "Shortlist entry not found")
    return row


def entry_values(entry: Entry) -> dict:
    return {k: getattr(entry, k) for k in ENTRY_FIELDS}


async def validate_entry(db: AsyncSession, org_id, values: dict) -> None:
    """Spec §5.4 steps 1-6 on the complete (created or merged) entry. Another agency's university reads exactly like an unknown id."""
    if (values["university_id"] is None) == (values["agent_university_id"] is None):
        raise HTTPException(422, "Choose a catalogue university or one of your agency's universities")
    if values["university_id"] is not None and await db.get(University, values["university_id"]) is None:
        raise HTTPException(422, "University not found")
    if values["agent_university_id"] is not None:
        found = await db.scalar(select(AgentUniversity.id).where(AgentUniversity.id == values["agent_university_id"], AgentUniversity.org_id == org_id))
        if found is None:
            raise HTTPException(422, "University not found")
    if values["course_id"] is not None and values["course_title"] is not None:
        raise HTTPException(422, "Choose a catalogue course or type a course, not both")
    if values["course_id"] is not None:
        if values["university_id"] is None:
            raise HTTPException(422, "Catalogue courses can only be chosen with a catalogue university")
        course = await db.get(OverseasCourse, values["course_id"])
        if course is None or course.university_id != values["university_id"]:
            raise HTTPException(422, COURSE_MISMATCH)


async def ensure_entry_capacity(db: AsyncSession, student_id) -> None:
    count = await db.scalar(select(func.count()).select_from(Entry).where(Entry.agent_student_id == student_id))
    if count >= MAX_ENTRIES_PER_STUDENT:
        raise HTTPException(422, f"This student's shortlist is full ({MAX_ENTRIES_PER_STUDENT} entries)")
```

- [ ] **Step 4: Append the shortlist routes** to `apps/api/app/api/agent_shortlist.py`. Extend its imports:

```python
from app.api.agent_students import _audit, _gate, _locked_row, _log, _require_master_action
from app.models import AgentStudent, AgentStudentShortlistEntry, AgentUniversity, AuditLog, User
from app.schemas import AgentUniversityCreate, AgentUniversityUpdate, ShortlistEntryCreate, ShortlistEntryUpdate
from app.services.agent_shortlist import (..., ensure_entry_capacity, entry_detail, entry_page, entry_values, load_entry, validate_entry)
from app.services.agent_students import load_scoped
```

Then the routes:

```python
SHORTLIST = "/students/{student_id}/shortlist"
ENTRY = SHORTLIST + "/{entry_id}"


def _require_active(student: AgentStudent) -> None:
    if student.status == "archived":
        raise HTTPException(409, "Unarchive this student first")


@router.get(SHORTLIST)
async def list_shortlist(
    student_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _gate(user)
    await load_scoped(db, user, student_id)  # 404 outside the caller's scope (staff: assigned students only)
    return await entry_page(db, student_id, limit=limit, offset=offset)


@router.post(SHORTLIST, status_code=201)
async def add_entry(student_id: UUID, payload: ShortlistEntryCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    student = await _locked_row(db, user, membership, student_id)
    _require_active(student)
    values = payload.model_dump()
    await validate_entry(db, membership.org_id, values)
    await ensure_entry_capacity(db, student.id)
    entry = AgentStudentShortlistEntry(agent_student_id=student.id, **values, created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(entry)
    await db.flush()
    source = "catalogue" if values["university_id"] else "agency"
    _audit(db, user, "shortlist_add", student.id, {"entry_id": str(entry.id), "university_source": source, "fields": sorted(k for k, v in values.items() if v is not None)})
    await db.commit()
    _log("agent_shortlist_added", membership, user, student.id, entry_id=str(entry.id))
    return {"entry": await entry_detail(db, entry.id)}


@router.patch(ENTRY)
async def update_entry(student_id: UUID, entry_id: UUID, payload: ShortlistEntryUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    student = await _locked_row(db, user, membership, student_id)
    _require_active(student)
    entry = await load_entry(db, student.id, entry_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    await validate_entry(db, membership.org_id, {**entry_values(entry), **changes})
    changed = apply_changes(entry, changes, user)
    if changed:
        _audit(db, user, "shortlist_update", student.id, {"entry_id": str(entry.id), "fields": changed})
    await db.commit()
    if changed:
        _log("agent_shortlist_updated", membership, user, student.id, entry_id=str(entry.id), fields=changed)
    return {"entry": await entry_detail(db, entry.id)}


@router.delete(ENTRY, status_code=204)
async def remove_entry(student_id: UUID, entry_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    student = await _locked_row(db, user, membership, student_id)
    _require_active(student)
    entry = await load_entry(db, student.id, entry_id, lock=True)
    _audit(db, user, "shortlist_remove", student.id, {"entry_id": str(entry.id)})
    await db.delete(entry)
    await db.commit()
    _log("agent_shortlist_removed", membership, user, student.id, entry_id=str(entry.id))
    return Response(status_code=204)
```

`ShortlistEntryCreate.model_dump()` returns `UUID` objects for the id fields, and `validate_entry` and the model accept them. The `fields` list for a create is sorted names of the non-null values, which matches the test.

- [ ] **Step 5: Run the tests and confirm they pass.**

Run: `API_TEST tests/test_agn_007_shortlist.py tests/test_agn_007_universities.py`
Expected: all pass.

- [ ] **Step 6: Commit.**

```bash
git add apps/api/app/services/agent_shortlist.py apps/api/app/api/agent_shortlist.py apps/api/tests/test_agn_007_shortlist.py
git commit -m "feat(agn-007): student university shortlist -- catalogue or agency entries, course rule, paging"
```

---

### Task 4: Isolation, /public, concurrency, staff activity

**Files:**
- Modify: `apps/api/app/services/staff_activity.py:16-24` (`STAFF_ACTIVITY_ACTIONS`)
- Test: `apps/api/tests/test_agn_007_isolation.py`

**Interfaces:** Consumes Tasks 2–3. Produces three new entries in `STAFF_ACTIVITY_ACTIONS`.

- [ ] **Step 1: Write the failing tests** in `apps/api/tests/test_agn_007_isolation.py`:

```python
"""AGN-007 -- invisible to other agencies and to /public; races; staff activity (AC04, AC05, AC10 race, AC12; Review Focus 2, 3)."""

import asyncio
import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import func, select

from app.main import app
from app.models import AgentStudentShortlistEntry, AgentUniversity
from app.services import agent_shortlist as service
from tests.agn001_helpers import client_for, mk_active_org
from tests.agn004_helpers import mk_record, mk_staff
from tests.agn007_helpers import UNIVERSITIES, mk_catalogue, shortlist

ACTIVITY = "/api/v1/workflows/overseas/agent/team/staff/{member}/activity"  # AGN-021 (api/agent_team.py; items carry "action")


@pytest_asyncio.fixture
async def two(db_session):
    a = await mk_active_org(db_session, name="Iso A")
    b = await mk_active_org(db_session, name="Iso B")
    tag = uuid.uuid4().hex[:8]
    async with client_for(a["master"].email) as m:
        uni = (await m.post(UNIVERSITIES, json={"name": f"Secret Uni {tag}", "country": "Atlantis"})).json()["university"]
    student_a = await mk_record(db_session, agent=a["master"], full_name="Iso Student A")
    student_b = await mk_record(db_session, agent=b["master"], full_name="Iso Student B")
    async with client_for(a["master"].email) as m:
        entry = (await m.post(shortlist(student_a.id), json={"agent_university_id": uni["id"], "course_title": f"Secret Course {tag}"})).json()["entry"]
    return {"a": a, "b": b, "tag": tag, "uni": uni, "student_a": student_a, "student_b": student_b, "entry": entry}


@pytest.mark.asyncio
async def test_other_agencys_university_id_reads_as_not_found(two):  # AGN-007-AC04, Review Focus 2
    async with client_for(two["b"]["master"].email) as o:
        used = await o.post(shortlist(two["student_b"].id), json={"agent_university_id": two["uni"]["id"]})
        unknown = await o.post(shortlist(two["student_b"].id), json={"agent_university_id": str(uuid.uuid4())})
        assert (used.status_code, used.json()) == (unknown.status_code, unknown.json()) == (422, {"detail": "University not found"})
        assert (await o.get(shortlist(two["student_a"].id))).status_code == 404
        assert (await o.delete(f"{shortlist(two['student_a'].id)}/{two['entry']['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_public_never_shows_agency_universities_or_entries(db_session, two):  # AGN-007-AC05
    cat = await mk_catalogue(db_session)
    secret = two["tag"]
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:  # no login: the public site
        bodies = [
            (await anon.get("/api/v1/public/universities")).text,
            (await anon.get("/api/v1/public/universities", params={"q": "Secret"})).text,
            (await anon.get(f"/api/v1/public/universities/{cat['university'].slug}")).text,
            (await anon.get(f"/api/v1/public/countries/{cat['country'].slug}")).text,
            (await anon.get("/api/v1/public/overseas-courses")).text,
            (await anon.get("/api/v1/public/countries")).text,
        ]
        by_id = await anon.get(f"/api/v1/public/universities/{two['uni']['id']}")  # an agency id is not a catalogue slug
    for body in bodies:
        assert secret not in body and "Atlantis" not in body
    assert by_id.status_code == 404


@pytest.mark.asyncio
async def test_concurrent_adds_never_pass_the_cap(db_session, two, monkeypatch):  # AGN-007-AC10 (race)
    monkeypatch.setattr(service, "MAX_ENTRIES_PER_STUDENT", 2)  # one entry exists from the fixture
    body = {"agent_university_id": two["uni"]["id"]}
    async with client_for(two["a"]["master"].email) as c1, client_for(two["a"]["master"].email) as c2:
        results = await asyncio.gather(c1.post(shortlist(two["student_a"].id), json=body), c2.post(shortlist(two["student_a"].id), json=body))
    assert sorted(r.status_code for r in results) == [201, 422]
    assert await db_session.scalar(select(func.count()).select_from(AgentStudentShortlistEntry).where(AgentStudentShortlistEntry.agent_student_id == two["student_a"].id)) == 2


@pytest.mark.asyncio
async def test_delete_university_racing_an_add_never_orphans(db_session, two):  # Review Focus 3
    async with client_for(two["a"]["master"].email) as m:
        fresh = (await m.post(UNIVERSITIES, json={"name": f"Racy {two['tag']}", "country": "Nowhere"})).json()["university"]
    async with client_for(two["a"]["master"].email) as c1, client_for(two["a"]["master"].email) as c2:
        add, delete = await asyncio.gather(
            c1.post(shortlist(two["student_a"].id), json={"agent_university_id": fresh["id"]}),
            c2.delete(f"{UNIVERSITIES}/{fresh['id']}"),
        )
    still_there = await db_session.get(AgentUniversity, uuid.UUID(fresh["id"]), populate_existing=True)
    if add.status_code == 201:
        assert delete.status_code == 409 and still_there is not None
    else:
        assert (add.status_code, delete.status_code) == (422, 204) and still_there is None


@pytest.mark.asyncio
async def test_shortlist_work_shows_in_staff_activity(db_session):  # AGN-007-AC12
    ctx = await mk_active_org(db_session, name="Activity Agency")
    staff = await mk_staff(db_session, ctx["org"], full_name="Activity Staff")
    student = await mk_record(db_session, agent=ctx["master"], full_name="Activity Student", assigned_member=staff["member"])
    async with client_for(ctx["master"].email) as m:
        uni = (await m.post(UNIVERSITIES, json={"name": f"Act {uuid.uuid4().hex[:6]}", "country": "Peru"})).json()["university"]
    async with client_for(staff["user"].email) as s:
        eid = (await s.post(shortlist(student.id), json={"agent_university_id": uni["id"]})).json()["entry"]["id"]
        await s.patch(f"{shortlist(student.id)}/{eid}", json={"intake": "Sep"})
        await s.delete(f"{shortlist(student.id)}/{eid}")
    async with client_for(ctx["master"].email) as m:
        items = (await m.get(ACTIVITY.format(member=staff["member"].id))).json()["items"]
    actions = [i["action"] for i in items]
    assert {"agent_student.shortlist_add", "agent_student.shortlist_update", "agent_student.shortlist_remove"} <= set(actions)
    assert not any(a.startswith("agent_university.") for a in actions)
```

- [ ] **Step 2: Run the tests and confirm the activity test fails.**

Run: `API_TEST tests/test_agn_007_isolation.py`
Expected: `test_shortlist_work_shows_in_staff_activity` FAILS (the actions aren't whitelisted). The others pass.

- [ ] **Step 3: Whitelist the shortlist actions** in `apps/api/app/services/staff_activity.py`:

```python
STAFF_ACTIVITY_ACTIONS = (
    "agent_student.create",
    "agent_student.update",
    "agent_student.duplicate_override",
    # AGN-007 (DEC-SCOPE-048): shortlist work on a student; the agent_student subject resolver already names the student.
    "agent_student.shortlist_add",
    "agent_student.shortlist_update",
    "agent_student.shortlist_remove",
    "agent.student_link",
    "overseas.application.create",
    "document.upload",
    "document.verify",
)
```

- [ ] **Step 4: Run the tests and confirm they pass.**

Run: `API_TEST tests/test_agn_007_isolation.py tests/test_agn_021_activity.py`
Expected: all pass. AGN-021 asserts exact item counts for its own fixtures, which don't include shortlist rows.

- [ ] **Step 5: Commit.**

```bash
git add apps/api/app/services/staff_activity.py apps/api/tests/test_agn_007_isolation.py
git commit -m "feat(agn-007): shortlist actions in staff activity; isolation, /public and race tests"
```

---

### Task 5: §6 matrix rows and the Universities portal section

**Files:**
- Modify: `apps/api/tests/test_agn_003_matrix.py` (lists `STAFF_REFUSED`, `BOTH_ALLOWED`, `MASTER_ALLOWED`; test `test_add_university_is_refused_to_masters_too`)
- Modify: `apps/api/app/services/portal.py` (`_agent`, before `if section == "students":`)
- Test: the same matrix file, plus `apps/api/tests/test_agn_007_universities.py` (add one portal test)

**Interfaces:** Produces `GET /portal/overseas/agent/universities`, which returns 200 with the header payload for Master and Staff.

- [ ] **Step 1: Update the matrix (failing first).**

In `test_agn_003_matrix.py`, add `AGENCY_UNIS = "/api/v1/workflows/overseas/agent/crm/universities"` next to `TEAM`. Then make these changes:
- Append to `STAFF_REFUSED`: `("Add University", "post", AGENCY_UNIS, {"name": "Matrix Uni", "country": "Testland"}, "Only an agency Master can add universities"),`. Keep the existing `/admin/universities` row: the shared catalogue stays admin-only.
- Append to `BOTH_ALLOWED`: `("University Database", "get", AGENCY_UNIS, None, 200),` and `("University Database", "get", PORTAL + "/universities", None, 200),`.
- Append to `MASTER_ALLOWED`: `("Add University", "post", AGENCY_UNIS, {"name": "{fresh_email}", "country": "Testland"}, 201),`. The `{fresh_email}` placeholder is unique per world, so the duplicate rule can't fire.
- Rename `test_add_university_is_refused_to_masters_too` to `test_the_shared_catalogue_stays_admin_only_for_masters`. Replace its comment with: `# DEC-SCOPE-048 supersedes DEC-SCOPE-044 P3 for "Add University": a Master adds to their agency's own list (AGENCY_UNIS, MASTER_ALLOWED); the shared catalogue route stays admin-only.` Keep the body unchanged.
- Update the module docstring with one sentence: `AGN-007 (DEC-SCOPE-048): "University Database" adds the agency list for both roles and "Add University" is now Master-only on the agency list.`

- [ ] **Step 2: Run the matrix and confirm the new rows fail.**

Run: `API_TEST tests/test_agn_003_matrix.py`
Expected: the `PORTAL + "/universities"` rows FAIL with 404 "Workspace not found". The rest pass.

- [ ] **Step 3: Add the portal section** in `apps/api/app/services/portal.py`, inside `_agent`, immediately before `if section == "students":`:

```python
    if section == "universities":
        # AGN-007 (DEC-SCOPE-048): header only -- PortalPage mounts AgentUniversitiesPanel for this section (the Students precedent).
        return _payload("Universities", "Your agency's own universities. Browse the public catalogue for the rest.")
```

In `apps/api/tests/test_agn_007_universities.py`, add:

```python
@pytest.mark.asyncio
async def test_portal_section_exists_for_both_roles(agency):
    for email in (agency["master"].email, agency["staff"]["user"].email):
        async with client_for(email) as c:
            body = (await c.get("/api/v1/portal/overseas/agent/universities")).json()
        assert body["title"] == "Universities" and body["rows"] == []
```

- [ ] **Step 4: Run the tests and confirm they pass.**

Run: `API_TEST tests/test_agn_003_matrix.py tests/test_agn_007_universities.py`
Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add apps/api/app/services/portal.py apps/api/tests/test_agn_003_matrix.py apps/api/tests/test_agn_007_universities.py
git commit -m "feat(agn-007): Universities portal section; §6 matrix rows for University DB and Add University"
```

---

### Task 6: Frontend client library and navigation

**Files:**
- Create: `apps/web/lib/agentShortlist.ts`
- Modify: `apps/web/lib/navigation.ts` (the `"overseas/agent"` list)
- Test: `apps/web/tests/lib/agentShortlist.test.ts`, `apps/web/tests/lib/navigation.agent.test.ts`

**Interfaces:**
- Consumes: `Page` from `@/lib/apiErrors`; `University`, `Country` from `@/lib/types`.
- Produces:
  - `UNIVERSITIES_URL`, `CATALOGUE_URL`, `COUNTRIES_URL`, `shortlistUrl(studentId)`
  - types `AgentUniversity`, `ShortlistEntry`, `CatalogueCourse`, `EntryDraft`, `UniversityDraft`
  - `LIMITS`, `emptyEntryDraft()`, `draftFromEntry(e)`, `buildEntryPayload(d)`, `changedOnly(payload, original)`, `validateEntryDraft(d)`
  - `buildUniversityPayload(d)`, `validateUniversityDraft(d)`
  - `universityKey(source, id)` → `"c:<id>" | "a:<id>"`, `parseUniversityKey(key)`

- [ ] **Step 1: Write the failing tests** in `apps/web/tests/lib/agentShortlist.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { buildEntryPayload, buildUniversityPayload, changedOnly, draftFromEntry, emptyEntryDraft, shortlistUrl, validateEntryDraft, validateUniversityDraft } from "@/lib/agentShortlist";

describe("agentShortlist (AGN-007)", () => {
  it("builds a catalogue payload: course id wins over typed text", () => {
    const d = { ...emptyEntryDraft(), university: "c:u1", courseId: "k1", courseTitle: "ignored", intake: " Sep 2027 ", tuitionFee: "", entryRequirements: "IELTS" };
    expect(buildEntryPayload(d)).toEqual({ university_id: "u1", agent_university_id: null, course_id: "k1", course_title: null, intake: "Sep 2027", tuition_fee: null, entry_requirements: "IELTS" });
  });

  it("builds an agency payload: never a catalogue course", () => {
    const d = { ...emptyEntryDraft(), university: "a:x9", courseId: "k1", courseTitle: " BA Typed " };
    expect(buildEntryPayload(d)).toMatchObject({ university_id: null, agent_university_id: "x9", course_id: null, course_title: "BA Typed" });
  });

  it("sends only changed fields on edit", () => {
    const original = { university_id: "u1", agent_university_id: null, course_id: null, course_title: "A", intake: "Sep", tuition_fee: null, entry_requirements: null };
    expect(changedOnly({ ...original, intake: "Jan" }, original)).toEqual({ intake: "Jan" });
  });

  it("round-trips an entry into a draft", () => {
    const entry = { id: "e1", university: { source: "agency" as const, id: "x9", name: "N", slug: null, country: "Malta" }, course: { id: null, title: "BA" }, intake: "Sep", tuition_fee: null, entry_requirements: null, created_by: null, created_at: "", updated_at: "" };
    expect(draftFromEntry(entry)).toEqual({ university: "a:x9", courseId: "", courseTitle: "BA", intake: "Sep", tuitionFee: "", entryRequirements: "" });
  });

  it("validates the university and lengths", () => {
    expect(validateEntryDraft(emptyEntryDraft())).toBe("Choose a university.");
    expect(validateEntryDraft({ ...emptyEntryDraft(), university: "a:x", intake: "x".repeat(121) })).toBe("Intake must be 120 characters or fewer.");
    expect(validateEntryDraft({ ...emptyEntryDraft(), university: "a:x" })).toBeNull();
    expect(validateUniversityDraft({ name: " ", country: "Ireland", city: "", entryRequirements: "" })).toBe("Name is required.");
    expect(buildUniversityPayload({ name: " Trinity ", country: "Ireland", city: "", entryRequirements: "" })).toEqual({ name: "Trinity", country: "Ireland", city: null, entry_requirements: null });
  });

  it("builds the shortlist URL", () => {
    expect(shortlistUrl("s1")).toBe("/api/v1/workflows/overseas/agent/crm/students/s1/shortlist");
  });
});
```

In `apps/web/tests/lib/navigation.agent.test.ts`, insert `"/overseas/agent/universities",` after `"/overseas/agent/students",` in **both** staff expectations, and add:

```ts
  it("shows Universities to both roles (AGN-007)", () => {
    expect(nav.map((i) => i.href)).toContain("/overseas/agent/universities");
    expect(agentNavFor(nav, "staff").map((i) => i.href)).toContain("/overseas/agent/universities");
  });
```

- [ ] **Step 2: Run the tests and confirm they fail.**

Run: `cd apps/web && npx vitest run tests/lib/agentShortlist.test.ts tests/lib/navigation.agent.test.ts`
Expected: FAIL (module not found; the nav doesn't have the item).

- [ ] **Step 3: Implement** `apps/web/lib/agentShortlist.ts`:

```ts
import type { Page } from "@/lib/apiErrors";

// AGN-007 (DEC-SCOPE-048): an agency's own universities and a student's university shortlist. The server is the authority; the
// checks here only spare a round trip (spec §6.3).
export const UNIVERSITIES_URL = "/api/v1/workflows/overseas/agent/crm/universities";
export const CATALOGUE_URL = "/api/v1/public/universities";
export const COUNTRIES_URL = "/api/v1/public/countries";
export const shortlistUrl = (studentId: string) => `/api/v1/workflows/overseas/agent/crm/students/${studentId}/shortlist`;
export const PAGE_SIZE = 20;

export type AgentUniversity = { id: string; name: string; country: string; city: string | null; entry_requirements: string | null; created_at: string; updated_at: string };
export type ShortlistEntry = {
  id: string;
  university: { source: "catalogue" | "agency"; id: string; name: string; slug: string | null; country: string | null };
  course: { id: string | null; title: string } | null;
  intake: string | null;
  tuition_fee: string | null;
  entry_requirements: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};
export type CatalogueCourse = { id: string; title: string; level: string; tuition_fee: string; intake: string };
export type { Page };

// A university choice travels as "c:<id>" (catalogue) or "a:<id>" (agency) so one <select> holds both groups.
export type EntryDraft = { university: string; courseId: string; courseTitle: string; intake: string; tuitionFee: string; entryRequirements: string };
export type UniversityDraft = { name: string; country: string; city: string; entryRequirements: string };
type Payload = Record<string, string | null>;

export const LIMITS = { name: 200, country: 120, city: 120, course_title: 200, intake: 120, tuition_fee: 120, entry_requirements: 2000 } as const;

export const universityKey = (source: "catalogue" | "agency", id: string) => `${source === "catalogue" ? "c" : "a"}:${id}`;
export function parseUniversityKey(key: string): { source: "catalogue" | "agency"; id: string } | null {
  const [kind, id] = key.split(":");
  if (!id || (kind !== "c" && kind !== "a")) return null;
  return { source: kind === "c" ? "catalogue" : "agency", id };
}

const clean = (value: string) => (value.trim() === "" ? null : value.trim());

export const emptyEntryDraft = (): EntryDraft => ({ university: "", courseId: "", courseTitle: "", intake: "", tuitionFee: "", entryRequirements: "" });

export function draftFromEntry(e: ShortlistEntry): EntryDraft {
  return {
    university: universityKey(e.university.source, e.university.id),
    courseId: e.course?.id ?? "",
    courseTitle: e.course && !e.course.id ? e.course.title : "",
    intake: e.intake ?? "",
    tuitionFee: e.tuition_fee ?? "",
    entryRequirements: e.entry_requirements ?? "",
  };
}

export function buildEntryPayload(d: EntryDraft): Payload {
  const choice = parseUniversityKey(d.university);
  const catalogue = choice?.source === "catalogue";
  const courseId = catalogue && d.courseId ? d.courseId : null;
  return {
    university_id: catalogue ? choice!.id : null,
    agent_university_id: choice?.source === "agency" ? choice.id : null,
    course_id: courseId,
    course_title: courseId ? null : clean(d.courseTitle),
    intake: clean(d.intake),
    tuition_fee: clean(d.tuitionFee),
    entry_requirements: clean(d.entryRequirements),
  };
}

export function changedOnly(payload: Payload, original: Payload): Payload {
  return Object.fromEntries(Object.entries(payload).filter(([k, v]) => original[k] !== v));
}

const LABELS: Record<string, string> = { course_title: "Course", intake: "Intake", tuition_fee: "Tuition fee", entry_requirements: "Entry requirements", name: "Name", country: "Country", city: "City" };
function tooLong(fields: Record<string, string>): string | null {
  for (const [key, value] of Object.entries(fields)) {
    const limit = LIMITS[key as keyof typeof LIMITS];
    if (value.trim().length > limit) return `${LABELS[key]} must be ${limit} characters or fewer.`;
  }
  return null;
}

export function validateEntryDraft(d: EntryDraft): string | null {
  if (!parseUniversityKey(d.university)) return "Choose a university.";
  return tooLong({ course_title: d.courseTitle, intake: d.intake, tuition_fee: d.tuitionFee, entry_requirements: d.entryRequirements });
}

export function buildUniversityPayload(d: UniversityDraft): Payload {
  return { name: clean(d.name), country: clean(d.country), city: clean(d.city), entry_requirements: clean(d.entryRequirements) };
}

export function validateUniversityDraft(d: UniversityDraft): string | null {
  if (!d.name.trim()) return "Name is required.";
  if (!d.country.trim()) return "Country is required.";
  return tooLong({ name: d.name, country: d.country, city: d.city, entry_requirements: d.entryRequirements });
}
```

In `apps/web/lib/navigation.ts`, change the `"overseas/agent"` list to `["dashboard","students","universities","applications","documents","commissions","reports","team"]`.

- [ ] **Step 4: Run the tests and confirm they pass.**

Run: `cd apps/web && npx vitest run tests/lib/agentShortlist.test.ts tests/lib/navigation.agent.test.ts tests/lib/navigation.test.ts`
Expected: all pass. If `navigation.test.ts` pins the full agent list, insert `"universities"` there too: the change is the deliberate new nav item.

- [ ] **Step 5: Commit.**

```bash
git add apps/web/lib/agentShortlist.ts apps/web/lib/navigation.ts apps/web/tests/lib/agentShortlist.test.ts apps/web/tests/lib/navigation.agent.test.ts apps/web/tests/lib/navigation.test.ts
git commit -m "feat(agn-007): shortlist client library and Universities nav item"
```

---

### Task 7: University Database screen

**Files:**
- Create: `apps/web/components/AgentUniversityForm.tsx`, `apps/web/components/AgentUniversitiesPanel.tsx`
- Modify: `apps/web/components/PortalPage.tsx` (the `main=` expression)
- Test: `apps/web/tests/components/AgentUniversitiesPanel.test.tsx`

**Interfaces:**
- Consumes: Task 6; `detailMessage`, `isPage` from `@/lib/apiErrors`.
- Produces:
  - `<AgentUniversitiesPanel memberRole={"master"|"staff"|null|undefined} />`
  - `<AgentUniversityForm mode="add"|"edit" university? onCancel onSaved(u: AgentUniversity) />`

- [ ] **Step 1: Write the failing tests** in `apps/web/tests/components/AgentUniversitiesPanel.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentUniversitiesPanel from "@/components/AgentUniversitiesPanel";

const uni = (over: Record<string, unknown> = {}) => ({ id: "u1", name: "Trinity", country: "Ireland", city: "Dublin", entry_requirements: "IELTS 6.5", created_at: "", updated_at: "", ...over });
const page = (items: unknown[], total = items.length) => ({ items, total, limit: 20, offset: 0 });
const res = (body: unknown, status = 200) => new Response(body === null ? null : JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentUniversitiesPanel (AGN-007)", () => {
  it("shows loading, then the agency's universities as a list", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([uni()])))));
    render(<AgentUniversitiesPanel memberRole="master" />);
    expect(screen.getByText("Loading universities…")).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Agency universities" });
    expect(within(list).getByText("Trinity")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse the university catalogue" })).toHaveAttribute("href", "/overseas/universities");
  });

  it("gives Masters Add, Edit and Delete; Staff see none", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([uni()])))));
    const { unmount } = render(<AgentUniversitiesPanel memberRole="master" />);
    await screen.findByText("Trinity");
    expect(screen.getByRole("button", { name: "Add university" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Trinity" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete Trinity" })).toBeInTheDocument();
    unmount();
    render(<AgentUniversitiesPanel memberRole="staff" />);
    await screen.findByText("Trinity");
    expect(screen.queryByRole("button", { name: /Add university|Edit|Delete/ })).toBeNull();
  });

  it("shows the empty state (with Add only for Masters)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([])))));
    render(<AgentUniversitiesPanel memberRole="staff" />);
    expect(await screen.findByText("Your agency hasn't added any universities yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add university" })).toBeNull();
  });

  it("shows an error with Retry", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res(page([uni()])));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentUniversitiesPanel memberRole="master" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    fireEvent.click(screen.getByRole("button", { name: "Retry loading universities" }));
    expect(await screen.findByText("Trinity")).toBeInTheDocument();
  });

  it("explains an in-use delete inline and keeps the row", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "DELETE" ? res({ detail: "This university is on 2 shortlist entries; remove it from them first" }, 409) : res(page([uni()]))),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentUniversitiesPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Delete Trinity" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(await screen.findByText(/on 2 shortlist entries/)).toBeInTheDocument();
    expect(screen.getByText("Trinity")).toBeInTheDocument();
  });

  it("adds a university and shows it", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST" ? res({ university: uni({ id: "u2", name: "UCD" }) }, 201) : res(page([]))),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentUniversitiesPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add university" }));
    const form = screen.getByRole("form", { name: "Add university" });
    fireEvent.change(within(form).getByLabelText("Name (required)"), { target: { value: "UCD" } });
    fireEvent.change(within(form).getByLabelText("Country (required)"), { target: { value: "Ireland" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save university" }));
    expect(await screen.findByText("UCD added.")).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body))).toEqual({ name: "UCD", country: "Ireland", city: null, entry_requirements: null });
  });
});
```

- [ ] **Step 2: Run the tests and confirm they fail.**

Run: `cd apps/web && npx vitest run tests/components/AgentUniversitiesPanel.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement** `apps/web/components/AgentUniversityForm.tsx` (markup mirrors `AgentStudentForm`: `form`/`field`/`form-error`):

```tsx
"use client";

import { type FormEvent, type KeyboardEvent, useEffect, useId, useState } from "react";

import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { type AgentUniversity, buildUniversityPayload, changedOnly, LIMITS, UNIVERSITIES_URL, type UniversityDraft, validateUniversityDraft } from "@/lib/agentShortlist";

// AGN-007 (DEC-SCOPE-048 D1): a Master adds or edits one of the agency's own universities. The server re-checks everything.
const FIELDS: { key: keyof UniversityDraft; label: string; limit: number }[] = [
  { key: "name", label: "Name (required)", limit: LIMITS.name },
  { key: "country", label: "Country (required)", limit: LIMITS.country },
  { key: "city", label: "City", limit: LIMITS.city },
];

const toDraft = (u?: AgentUniversity): UniversityDraft => ({ name: u?.name ?? "", country: u?.country ?? "", city: u?.city ?? "", entryRequirements: u?.entry_requirements ?? "" });

export default function AgentUniversityForm({ mode, university, onCancel, onSaved }: { mode: "add" | "edit"; university?: AgentUniversity; onCancel: () => void; onSaved: (u: AgentUniversity) => void }) {
  const idPrefix = `uni-${useId().replace(/:/g, "")}`;
  const [draft, setDraft] = useState<UniversityDraft>(() => toDraft(university));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const title = mode === "add" ? "Add university" : `Edit ${university?.name}`;

  useEffect(() => {
    document.getElementById(`${idPrefix}-title`)?.focus();
  }, [idPrefix]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const problem = validateUniversityDraft(draft);
    if (problem) return setFailure(problem);
    const payload = buildUniversityPayload(draft);
    const body = mode === "add" ? payload : changedOnly(payload, buildUniversityPayload(toDraft(university)));
    setBusy(true);
    setFailure(null);
    try {
      const response = await fetch(mode === "add" ? UNIVERSITIES_URL : `${UNIVERSITIES_URL}/${university!.id}`, {
        method: mode === "add" ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.university) return setFailure(detailMessage(data?.detail, "Unable to save the university."));
      onSaved(data.university);
    } catch {
      setFailure(NOT_COMPLETED);
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape" && !busy) {
      e.stopPropagation();
      onCancel();
    }
  }

  return (
    <form className="form card" onSubmit={submit} onKeyDown={onKeyDown} aria-busy={busy} noValidate aria-label={mode === "add" ? "Add university" : "Edit university"}>
      <h4 id={`${idPrefix}-title`} tabIndex={-1}>
        {title}
      </h4>
      {FIELDS.map((f) => (
        <div className="field" key={f.key}>
          <label htmlFor={`${idPrefix}-${f.key}`}>{f.label}</label>
          <input id={`${idPrefix}-${f.key}`} value={draft[f.key]} maxLength={f.limit} aria-required={f.label.includes("required") || undefined} onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })} />
        </div>
      ))}
      <div className="field">
        <label htmlFor={`${idPrefix}-req`}>Entry requirements</label>
        <textarea id={`${idPrefix}-req`} rows={3} maxLength={LIMITS.entry_requirements} value={draft.entryRequirements} onChange={(e) => setDraft({ ...draft, entryRequirements: e.target.value })} />
      </div>
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
      <button type="submit" className="btn small" disabled={busy}>
        {busy ? "Saving…" : "Save university"}
      </button>{" "}
      <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>
        Cancel
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Implement** `apps/web/components/AgentUniversitiesPanel.tsx`. Its loading, paging and confirm behaviour follows `AgentStudentsPanel`.

```tsx
"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import AgentUniversityForm from "./AgentUniversityForm";
import { detailMessage, isPage, type Page } from "@/lib/apiErrors";
import { type AgentUniversity, PAGE_SIZE, UNIVERSITIES_URL } from "@/lib/agentShortlist";

// AGN-007 (DEC-SCOPE-048): the agency's own universities. §6 "University Database": Masters full, Staff view; "Add University" is
// Master only. The server enforces both; the controls here only follow it. Paging and the inline confirm follow AgentStudentsPanel.
type Editing = { mode: "add" } | { mode: "edit"; university: AgentUniversity } | null;

export default function AgentUniversitiesPanel({ memberRole }: { memberRole: "master" | "staff" | null | undefined }) {
  const isMaster = memberRole !== "staff";
  const [data, setData] = useState<Page<AgentUniversity> | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [draftQuery, setDraftQuery] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Editing>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ id: string; text: string } | null>(null);
  const [notice, setNotice] = useState("");
  const request = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setLoadError(null);
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (query) params.set("q", query);
    fetch(`${UNIVERSITIES_URL}?${params}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (controller.signal.aborted) return;
        if (!response.ok || !isPage<AgentUniversity>(body)) return setLoadError(detailMessage(body?.detail, "Unable to load universities."));
        if (body.items.length === 0 && body.offset > 0) return setOffset(Math.max(0, body.offset - PAGE_SIZE));
        setData(body);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadError("Unable to load universities.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [offset, query]);

  useEffect(load, [load]);
  useEffect(() => () => request.current?.abort(), []);

  function search(e: FormEvent) {
    e.preventDefault();
    setQuery(draftQuery.trim());
    setOffset(0);
  }

  async function remove(u: AgentUniversity) {
    setRowError(null);
    try {
      const response = await fetch(`${UNIVERSITIES_URL}/${u.id}`, { method: "DELETE" });
      if (response.status === 204 || response.status === 404) {
        setConfirmId(null);
        setNotice(`${u.name} deleted.`);
        return load();
      }
      const body = await response.json().catch(() => null);
      setRowError({ id: u.id, text: detailMessage(body?.detail, "Unable to delete the university.") });
    } catch {
      setRowError({ id: u.id, text: "Network error. Check your connection and try again." });
    }
    setConfirmId(null);
  }

  return (
    <div className="portal-content">
      <h2>Universities</h2>
      <p className="muted">
        Your agency&apos;s own universities. Masters add and edit them; everyone in your agency can use them on a student&apos;s shortlist.{" "}
        <Link href="/overseas/universities">Browse the university catalogue</Link>
      </p>
      <form role="search" onSubmit={search} className="field">
        <label htmlFor="agent-universities-q">Search universities</label>
        <input id="agent-universities-q" type="search" maxLength={100} value={draftQuery} onChange={(e) => setDraftQuery(e.target.value)} />
      </form>
      <p aria-live="polite">{notice}</p>
      {isMaster &&
        (editing ? (
          <AgentUniversityForm
            mode={editing.mode}
            university={editing.mode === "edit" ? editing.university : undefined}
            onCancel={() => setEditing(null)}
            onSaved={(u) => {
              setNotice(`${u.name} ${editing.mode === "add" ? "added" : "saved"}.`);
              setEditing(null);
              load();
            }}
          />
        ) : (
          <button type="button" className="btn small" onClick={() => setEditing({ mode: "add" })}>
            Add university
          </button>
        ))}
      <section aria-busy={loading} style={{ marginTop: 16, opacity: loading && data ? 0.6 : 1 }}>
        {loadError ? (
          <>
            <p className="form-error" role="alert">
              {loadError}
            </p>
            <button type="button" className="btn secondary small" aria-label="Retry loading universities" onClick={load}>
              Retry
            </button>
          </>
        ) : data === null ? (
          <p className="muted">Loading universities…</p>
        ) : data.items.length === 0 ? (
          <p className="muted">Your agency hasn&apos;t added any universities yet.</p>
        ) : (
          <>
            <ul aria-label="Agency universities" className="grid two" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {data.items.map((u) => (
                <li key={u.id} className="card">
                  <h3>{u.name}</h3>
                  <p className="muted">{[u.country, u.city].filter(Boolean).join(" · ")}</p>
                  {u.entry_requirements && (
                    <details>
                      <summary>Entry requirements</summary>
                      <p style={{ whiteSpace: "pre-line" }}>{u.entry_requirements}</p>
                    </details>
                  )}
                  {isMaster &&
                    (confirmId === u.id ? (
                      <span role="group" aria-label={`Confirm delete ${u.name}`}>
                        <button type="button" className="btn small" autoFocus onClick={() => void remove(u)}>
                          Confirm delete
                        </button>{" "}
                        <button type="button" className="btn secondary small" onClick={() => setConfirmId(null)}>
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <>
                        <button type="button" className="btn secondary small" aria-label={`Edit ${u.name}`} onClick={() => setEditing({ mode: "edit", university: u })}>
                          Edit
                        </button>{" "}
                        <button type="button" className="btn secondary small" aria-label={`Delete ${u.name}`} onClick={() => setConfirmId(u.id)}>
                          Delete
                        </button>
                      </>
                    ))}
                  {rowError?.id === u.id && (
                    <p className="form-error" role="status" aria-live="polite">
                      {rowError.text}
                    </p>
                  )}
                </li>
              ))}
            </ul>
            <p className="muted">
              Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}
            </p>
            <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Previous
            </button>{" "}
            <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total || loading} onClick={() => setOffset(offset + PAGE_SIZE)}>
              Next
            </button>
          </>
        )}
      </section>
    </div>
  );
}
```

`grid two` plus the inline list reset are what `AgentStudentsPanel` uses for its cards (L332). The grid's responsive collapse to one column comes from the existing stylesheet.

- [ ] **Step 5: Mount it in `PortalPage.tsx`.**

Add `import AgentUniversitiesPanel from "./AgentUniversitiesPanel";` and change the `main` expression to:

```tsx
const main=agent&&section==="students"?<>
<AgentStudentsSection user={user}/>
<PortalSection data={{...data,title:"Application status",subtitle:"Students who have a login, with each one's current application (AGT-002)."}}/>
</>:agent&&section==="universities"?<AgentUniversitiesPanel memberRole={user.agent_member_role}/>:<PortalSection data={data}/>;
```

Precede it with the comment `// AGN-007 (DEC-SCOPE-048): the agency's own universities -- the panel is the page (the payload is header-only).`. If `user.agent_member_role` is typed wider than the prop, check the type in `lib/types.ts` and narrow it the way `AgentStudentsSection` L26 does.

- [ ] **Step 6: Run the tests and confirm they pass.**

Run: `cd apps/web && npx vitest run tests/components/AgentUniversitiesPanel.test.tsx && npx tsc --noEmit`
Expected: all pass and `tsc` exits 0.

- [ ] **Step 7: Commit.**

```bash
git add apps/web/components/AgentUniversityForm.tsx apps/web/components/AgentUniversitiesPanel.tsx apps/web/components/PortalPage.tsx apps/web/tests/components/AgentUniversitiesPanel.test.tsx
git commit -m "feat(agn-007): Universities page -- agency list, Master add/edit/delete, Staff read-only"
```

---

### Task 8: Shortlist entry form

**Files:**
- Create: `apps/web/components/AgentShortlistForm.tsx`
- Test: `apps/web/tests/components/AgentShortlistForm.test.tsx`

**Interfaces:**
- Consumes: Task 6; `University`, `Country` from `@/lib/types`.
- Produces: `<AgentShortlistForm studentId mode="add"|"edit" entry? onCancel onSaved(e: ShortlistEntry) onGone() onConflict() />`.
  - `onGone` is the student 404.
  - `onConflict` is a 409, for example the student was archived meanwhile.

**Behaviour:**
- **Data loading:**
  - On mount, it fetches `CATALOGUE_URL`, `COUNTRIES_URL` and `${UNIVERSITIES_URL}?limit=100` in parallel. Use a module-level `let catalogueCache: Promise<…> | null` so a reopened form doesn't refetch. Export a `resetCatalogueCache()` for tests.
  - While loading, the University select is disabled and reads "Loading universities…".
  - If loading fails, a `role="alert"` with "Retry" appears.
- **University:** a native `<select id="shortlist-university">` labelled "University (required)", with `<optgroup label="Catalogue">` (values `c:<id>`, text `name — city`) and `<optgroup label="Your agency">` (values `a:<id>`, text `name — country`). The "Your agency" group is omitted when empty.
- **Course:**
  - For a catalogue university, fetch `${CATALOGUE_URL}/${slug}` and show `<select>` "Course" with "— No course —", each course, and "Other (type a course)" (value `__other__`). `__other__` shows a text input labelled "Course name".
  - Drop a stale course response when the university changes again, using a ticket ref like `openDetail` in `AgentStudentsPanel`.
  - For an agency university, show only the text input labelled "Course".
  - Changing the university resets `courseId` and `courseTitle`.
- **Prefill:**
  - When a catalogue course is chosen, fill `intake` and `tuitionFee` from the course, and `entryRequirements` from `university.requirements.join("\n")`.
  - When an agency university is chosen, fill `entryRequirements` from its `entry_requirements`.
  - A field the user has typed in (tracked in a `touched` Set) is never overwritten.
- **Country:** a read-only `<p>` labelled "Country": the catalogue country name from the countries map, or the agency university's country.
- **Submit:**
  - `validateEntryDraft` runs first.
  - POST `shortlistUrl(studentId)`, or PATCH `${shortlistUrl}/${entry.id}` with `changedOnly(buildEntryPayload(draft), buildEntryPayload(draftFromEntry(entry)))`.
  - 201/200 → `onSaved(body.entry)`; 404 → `onGone()`; 409 → `onConflict()`; 422 and others → inline `role="alert"` with `detailMessage`; a network failure shows `NOT_COMPLETED`.
- **Keyboard:** Escape on the form calls `onCancel()` and `e.stopPropagation()`, so the detail panel's own Escape handler doesn't also close the student. Focus moves to the form heading `h6` on mount.

- [ ] **Step 1: Write the failing tests** in `apps/web/tests/components/AgentShortlistForm.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AgentShortlistForm, { resetCatalogueCache } from "@/components/AgentShortlistForm";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const catalogue = [{ id: "u1", country_id: "c1", slug: "uni-one", name: "Uni One", city: "Dublin", overview: "", eligibility: "", requirements: ["IELTS 6.5", "Transcript"], deadlines: [], scholarships: [] }];
const countries = [{ id: "c1", slug: "ireland", name: "Ireland" }];
const agency = { items: [{ id: "a1", name: "Agency U", country: "Malta", city: null, entry_requirements: "Interview", created_at: "", updated_at: "" }], total: 1, limit: 100, offset: 0 };
const detail = { university: catalogue[0], courses: [{ id: "k1", title: "MSc Data", level: "PG", tuition_fee: "EUR 20,000", intake: "Sep 2027" }] };
const saved = { id: "e1", university: { source: "catalogue", id: "u1", name: "Uni One", slug: "uni-one", country: "Ireland" }, course: { id: "k1", title: "MSc Data" }, intake: "Sep 2027", tuition_fee: "EUR 20,000", entry_requirements: "IELTS 6.5\nTranscript", created_by: "M", created_at: "", updated_at: "" };

function stubApi(onWrite: (url: string, init: RequestInit) => Response = () => res({ entry: saved }, 201)) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method && init.method !== "GET") return Promise.resolve(onWrite(url, init));
    if (url.endsWith("/public/universities")) return Promise.resolve(res(catalogue));
    if (url.endsWith("/public/countries")) return Promise.resolve(res(countries));
    if (url.includes("/public/universities/uni-one")) return Promise.resolve(res(detail));
    if (url.includes("/crm/universities")) return Promise.resolve(res(agency));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => resetCatalogueCache());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const props = { studentId: "s1", mode: "add" as const, onCancel: vi.fn(), onSaved: vi.fn(), onGone: vi.fn(), onConflict: vi.fn() };

describe("AgentShortlistForm (AGN-007)", () => {
  it("offers catalogue and agency universities in two groups", async () => {
    stubApi();
    render(<AgentShortlistForm {...props} />);
    const select = await screen.findByLabelText("University (required)");
    await waitFor(() => expect(select).not.toBeDisabled());
    expect(select.querySelector('optgroup[label="Catalogue"] option[value="c:u1"]')).toHaveTextContent("Uni One — Dublin");
    expect(select.querySelector('optgroup[label="Your agency"] option[value="a:a1"]')).toHaveTextContent("Agency U — Malta");
  });

  it("prefills from a catalogue course, never over typed text, and saves the catalogue payload", async () => {
    const fetchMock = stubApi();
    render(<AgentShortlistForm {...props} />);
    const select = await screen.findByLabelText("University (required)");
    await waitFor(() => expect(select).not.toBeDisabled());
    fireEvent.change(screen.getByLabelText("Tuition fee"), { target: { value: "My own fee" } });
    fireEvent.change(select, { target: { value: "c:u1" } });
    expect(await screen.findByText("Ireland")).toBeInTheDocument();
    fireEvent.change(await screen.findByLabelText("Course"), { target: { value: "k1" } });
    expect(screen.getByLabelText("Intake")).toHaveValue("Sep 2027");
    expect(screen.getByLabelText("Tuition fee")).toHaveValue("My own fee");
    expect(screen.getByLabelText("Entry requirements")).toHaveValue("IELTS 6.5\nTranscript");
    fireEvent.click(screen.getByRole("button", { name: "Save to shortlist" }));
    await waitFor(() => expect(props.onSaved).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body))).toEqual({ university_id: "u1", agent_university_id: null, course_id: "k1", course_title: null, intake: "Sep 2027", tuition_fee: "My own fee", entry_requirements: "IELTS 6.5\nTranscript" });
  });

  it("uses a typed course for an agency university and resets the course on change", async () => {
    stubApi();
    render(<AgentShortlistForm {...props} />);
    const select = await screen.findByLabelText("University (required)");
    await waitFor(() => expect(select).not.toBeDisabled());
    fireEvent.change(select, { target: { value: "c:u1" } });
    fireEvent.change(await screen.findByLabelText("Course"), { target: { value: "k1" } });
    fireEvent.change(select, { target: { value: "a:a1" } });
    const course = screen.getByLabelText("Course");
    expect(course.tagName).toBe("INPUT");
    expect(course).toHaveValue("");
    expect(screen.getByText("Malta")).toBeInTheDocument();
  });

  it("shows the server's 422 detail inline", async () => {
    stubApi(() => res({ detail: "Course does not belong to selected university" }, 422));
    render(<AgentShortlistForm {...props} />);
    const select = await screen.findByLabelText("University (required)");
    await waitFor(() => expect(select).not.toBeDisabled());
    fireEvent.change(select, { target: { value: "a:a1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save to shortlist" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Course does not belong to selected university");
  });

  it("requires a university before sending", async () => {
    const fetchMock = stubApi();
    render(<AgentShortlistForm {...props} />);
    await waitFor(() => expect(screen.getByLabelText("University (required)")).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Save to shortlist" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a university.");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("closes the form on Escape without closing the detail", async () => {  // Review Focus 4
    stubApi();
    const outer = vi.fn();
    render(<div onKeyDown={outer}><AgentShortlistForm {...props} /></div>);
    fireEvent.keyDown(await screen.findByLabelText("University (required)"), { key: "Escape" });
    expect(props.onCancel).toHaveBeenCalled();
    expect(outer).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the tests and confirm they fail.**

Run: `cd apps/web && npx vitest run tests/components/AgentShortlistForm.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement** `apps/web/components/AgentShortlistForm.tsx`:

```tsx
"use client";

import { type FormEvent, type KeyboardEvent, useEffect, useId, useRef, useState } from "react";

import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import {
  type AgentUniversity, buildEntryPayload, CATALOGUE_URL, type CatalogueCourse, changedOnly, COUNTRIES_URL, draftFromEntry, emptyEntryDraft,
  type EntryDraft, LIMITS, parseUniversityKey, type ShortlistEntry, shortlistUrl, UNIVERSITIES_URL, validateEntryDraft,
} from "@/lib/agentShortlist";
import type { Country, University } from "@/lib/types";

// AGN-007 (DEC-SCOPE-048 D4/D6): one shortlist entry. The university is a catalogue one or the agency's own; a catalogue course is offered
// only under its own catalogue university, otherwise the course is typed. Picking a course pre-fills intake, fee and requirements but
// never overwrites what the user typed. The server re-checks every rule (spec §5.4).
type Options = { catalogue: University[]; countries: Map<string, string>; agency: AgentUniversity[] };
let catalogueCache: Promise<Options> | null = null;
export function resetCatalogueCache() {
  catalogueCache = null;
}
async function json<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(String(response.status));
  return response.json();
}
function loadOptions(): Promise<Options> {
  catalogueCache ??= Promise.all([json<University[]>(CATALOGUE_URL), json<Country[]>(COUNTRIES_URL), json<{ items: AgentUniversity[] }>(`${UNIVERSITIES_URL}?limit=100`)])
    .then(([catalogue, countries, agency]) => ({ catalogue, countries: new Map(countries.map((c) => [c.id, c.name])), agency: agency.items }))
    .catch((error) => {
      catalogueCache = null; // a failed load is retried, not cached
      throw error;
    });
  return catalogueCache;
}
const OTHER = "__other__";
type Field = "intake" | "tuitionFee" | "entryRequirements";

export default function AgentShortlistForm(props: { studentId: string; mode: "add" | "edit"; entry?: ShortlistEntry; onCancel: () => void; onSaved: (e: ShortlistEntry) => void; onGone: () => void; onConflict: () => void }) {
  const { studentId, mode, entry, onCancel, onSaved, onGone, onConflict } = props;
  const idPrefix = `sl-${useId().replace(/:/g, "")}`;
  const [options, setOptions] = useState<Options | null>(null);
  const [optionsFailed, setOptionsFailed] = useState(false);
  const [draft, setDraft] = useState<EntryDraft>(() => (entry ? draftFromEntry(entry) : emptyEntryDraft()));
  const [courses, setCourses] = useState<CatalogueCourse[] | null>(null);
  const [typedCourse, setTypedCourse] = useState(Boolean(entry?.course && !entry.course.id));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const touched = useRef(new Set<Field>(entry ? ["intake", "tuitionFee", "entryRequirements"] : []));
  const courseTicket = useRef(0);
  const choice = parseUniversityKey(draft.university);
  const catalogueUni = choice?.source === "catalogue" ? options?.catalogue.find((u) => u.id === choice.id) : undefined;
  const agencyUni = choice?.source === "agency" ? options?.agency.find((u) => u.id === choice.id) : undefined;
  const country = catalogueUni ? options?.countries.get(catalogueUni.country_id) : agencyUni?.country;

  const retryOptions = () => {
    setOptionsFailed(false);
    loadOptions().then(setOptions, () => setOptionsFailed(true));
  };
  useEffect(retryOptions, []);
  useEffect(() => document.getElementById(`${idPrefix}-title`)?.focus(), [idPrefix]);

  // A catalogue university's courses; a reply for an earlier choice is dropped (the openDetail ticket pattern).
  useEffect(() => {
    setCourses(null);
    if (!catalogueUni) return;
    const ticket = ++courseTicket.current;
    json<{ courses: CatalogueCourse[] }>(`${CATALOGUE_URL}/${catalogueUni.slug}`)
      .then((d) => ticket === courseTicket.current && setCourses(d.courses))
      .catch(() => ticket === courseTicket.current && setCourses([]));
  }, [catalogueUni]);

  const prefill = (values: Partial<Record<Field, string>>) =>
    setDraft((d) => ({ ...d, ...Object.fromEntries(Object.entries(values).filter(([k, v]) => v && !touched.current.has(k as Field))) }));
  const type = (field: Field, value: string) => {
    touched.current.add(field);
    setDraft((d) => ({ ...d, [field]: value }));
  };

  function chooseUniversity(key: string) {
    setDraft((d) => ({ ...d, university: key, courseId: "", courseTitle: "" }));
    setTypedCourse(false);
    const picked = parseUniversityKey(key);
    if (picked?.source === "agency") prefill({ entryRequirements: options?.agency.find((u) => u.id === picked.id)?.entry_requirements ?? "" });
  }
  function chooseCourse(value: string) {
    if (value === OTHER) return (setTypedCourse(true), setDraft((d) => ({ ...d, courseId: "" })));
    setTypedCourse(false);
    setDraft((d) => ({ ...d, courseId: value, courseTitle: "" }));
    const course = courses?.find((c) => c.id === value);
    if (course) prefill({ intake: course.intake, tuitionFee: course.tuition_fee, entryRequirements: (catalogueUni?.requirements ?? []).join("\n") });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const problem = validateEntryDraft(draft);
    if (problem) return setFailure(problem);
    const payload = buildEntryPayload(draft);
    const body = entry ? changedOnly(payload, buildEntryPayload(draftFromEntry(entry))) : payload;
    setBusy(true);
    setFailure(null);
    try {
      const response = await fetch(entry ? `${shortlistUrl(studentId)}/${entry.id}` : shortlistUrl(studentId), {
        method: entry ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => null);
      if (response.ok && data?.entry) return onSaved(data.entry);
      if (response.status === 404) return onGone();
      if (response.status === 409) return onConflict();
      setFailure(detailMessage(data?.detail, "Unable to save the shortlist entry."));
    } catch {
      setFailure(NOT_COMPLETED);
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape" && !busy) {
      e.stopPropagation(); // the detail panel closes on Escape too; only the form closes here (Review Focus 4)
      onCancel();
    }
  }

  const field = (key: Field, label: string, limit: number, multiline = false) => (
    <div className="field">
      <label htmlFor={`${idPrefix}-${key}`}>{label}</label>
      {multiline ? (
        <textarea id={`${idPrefix}-${key}`} rows={3} maxLength={limit} value={draft[key]} onChange={(e) => type(key, e.target.value)} />
      ) : (
        <input id={`${idPrefix}-${key}`} maxLength={limit} value={draft[key]} onChange={(e) => type(key, e.target.value)} />
      )}
    </div>
  );

  return (
    <form className="form card" onSubmit={submit} onKeyDown={onKeyDown} aria-busy={busy} noValidate aria-label={mode === "add" ? "Add to shortlist" : "Edit shortlist entry"}>
      <h6 id={`${idPrefix}-title`} tabIndex={-1}>{mode === "add" ? "Add a university" : `Edit ${entry?.university.name}`}</h6>
      <div className="field">
        <label htmlFor={`${idPrefix}-uni`}>University (required)</label>
        <select id={`${idPrefix}-uni`} value={draft.university} disabled={!options} aria-required onChange={(e) => chooseUniversity(e.target.value)}>
          <option value="">{options ? "— Choose a university —" : "Loading universities…"}</option>
          {options && (
            <optgroup label="Catalogue">
              {options.catalogue.map((u) => <option key={u.id} value={`c:${u.id}`}>{`${u.name} — ${u.city}`}</option>)}
            </optgroup>
          )}
          {options && options.agency.length > 0 && (
            <optgroup label="Your agency">
              {options.agency.map((u) => <option key={u.id} value={`a:${u.id}`}>{`${u.name} — ${u.country}`}</option>)}
            </optgroup>
          )}
        </select>
      </div>
      {optionsFailed && (
        <p className="form-error" role="alert">
          Unable to load universities.{" "}
          <button type="button" className="btn secondary small" onClick={retryOptions}>Retry</button>
        </p>
      )}
      {country && <p className="muted" aria-label="Country">{country}</p>}
      {catalogueUni && courses && (
        <div className="field">
          <label htmlFor={`${idPrefix}-course`}>Course</label>
          <select id={`${idPrefix}-course`} value={typedCourse ? OTHER : draft.courseId} onChange={(e) => chooseCourse(e.target.value)}>
            <option value="">— No course —</option>
            {courses.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
            <option value={OTHER}>Other (type a course)</option>
          </select>
        </div>
      )}
      {(agencyUni || typedCourse) && (
        <div className="field">
          <label htmlFor={`${idPrefix}-course-title`}>{agencyUni ? "Course" : "Course name"}</label>
          <input id={`${idPrefix}-course-title`} maxLength={LIMITS.course_title} value={draft.courseTitle} onChange={(e) => setDraft((d) => ({ ...d, courseTitle: e.target.value }))} />
        </div>
      )}
      {field("intake", "Intake", LIMITS.intake)}
      {field("tuitionFee", "Tuition fee", LIMITS.tuition_fee)}
      {field("entryRequirements", "Entry requirements", LIMITS.entry_requirements, true)}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save to shortlist"}</button>{" "}
      <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
    </form>
  );
}
```

Two interactions in the tests:
- When a catalogue university is chosen, the "Course" label only appears once its courses have loaded, so the test uses `findByLabelText("Course")`.
- When the user switches to an agency university, the "Course" label belongs to the text input, and its value is reset to empty.

The country appears as a `muted` paragraph, so `findByText("Ireland")` finds it. Run `npx prettier --check` and `eslint` on the file. If the file is over 200 lines after formatting, move `loadOptions`/`json`/the cache into `lib/agentShortlist.ts` (export `loadShortlistOptions` and `resetShortlistOptionsCache`) and update the test import.

- [ ] **Step 4: Run the tests and confirm they pass.**

Run: `cd apps/web && npx vitest run tests/components/AgentShortlistForm.test.tsx && npx tsc --noEmit`
Expected: all pass and `tsc` exits 0.

- [ ] **Step 5: Commit.**

```bash
git add apps/web/components/AgentShortlistForm.tsx apps/web/tests/components/AgentShortlistForm.test.tsx
git commit -m "feat(agn-007): shortlist entry form -- catalogue or agency university, course rule, prefill"
```

---

### Task 9: Shortlist panel in the student detail view

**Files:**
- Create: `apps/web/components/AgentShortlistPanel.tsx`
- Modify: `apps/web/components/AgentStudentDetailPanel.tsx` (one import, one mount line)
- Test: `apps/web/tests/components/AgentShortlistPanel.test.tsx`; re-run `AgentStudentsPanel.test.tsx`

**Interfaces:**
- Consumes: Tasks 6 and 8.
- Produces: `<AgentShortlistPanel studentId={string} archived={boolean} onStudentGone={() => void} onStudentChanged={() => void} />`.

**Behaviour:**
- `h5` "University shortlist".
- Loading with `aria-busy`.
- A list `<ul aria-label="Shortlist">` of `card` items: university name (plus a text badge "Agency" for `source === "agency"`), then `country`, course title, `Intake: …`, `Tuition fee: …`, and `<details>` with entry requirements (`pre-line`).
- Each item has "Edit {university}" and "Remove {university}" buttons, except when `archived`.
- Remove uses the inline confirm: Confirm and Cancel, with `autoFocus` on **Cancel**. A 204, or a 404 after the user's own delete, counts as success and refreshes.
- The empty state is "No universities shortlisted yet.", with an "Add university to shortlist" button unless archived.
- An archived student shows a note, "This student is archived; the shortlist is read-only.", with no write controls.
- An error shows `role="alert"` with a "Retry loading the shortlist" button.
- Paging matches `AgentStudentsPanel`: Showing x–y of N, Previous/Next, and stepping back when a page empties.
- The form opens in place of the Add button. After a save, the message "Saved to shortlist." appears in `aria-live` and the list reloads; focus returns to the Add or Edit button.
- `onGone` → `onStudentGone()`; `onConflict` → `onStudentChanged()`.

- [ ] **Step 1: Write the failing tests** in `apps/web/tests/components/AgentShortlistPanel.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentShortlistPanel from "@/components/AgentShortlistPanel";

const entry = (over: Record<string, unknown> = {}) => ({
  id: "e1", university: { source: "agency", id: "a1", name: "Agency U", slug: null, country: "Malta" }, course: { id: null, title: "BA Typed" },
  intake: "Sep 2027", tuition_fee: "EUR 9,000", entry_requirements: "Interview", created_by: "M", created_at: "", updated_at: "", ...over,
});
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });
const res = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status });
const props = { studentId: "s1", archived: false, onStudentGone: vi.fn(), onStudentChanged: vi.fn() };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentShortlistPanel (AGN-007)", () => {
  it("lists entries with an Agency badge and paging text", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([entry()])))));
    render(<AgentShortlistPanel {...props} />);
    const list = await screen.findByRole("list", { name: "Shortlist" });
    expect(within(list).getByText("Agency U")).toBeInTheDocument();
    expect(within(list).getByText("Agency")).toBeInTheDocument();
    expect(within(list).getByText("Malta")).toBeInTheDocument();
    expect(screen.getByText("Showing 1–1 of 1")).toBeInTheDocument();
  });

  it("shows the empty state with an Add button", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([])))));
    render(<AgentShortlistPanel {...props} />);
    expect(await screen.findByText("No universities shortlisted yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add university to shortlist" })).toBeInTheDocument();
  });

  it("is read-only for an archived student", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([entry()])))));
    render(<AgentShortlistPanel {...props} archived />);
    await screen.findByText("Agency U");
    expect(screen.getByText("This student is archived; the shortlist is read-only.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add university|Edit|Remove/ })).toBeNull();
  });

  it("shows an error with Retry", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "Nope" }, 500)).mockResolvedValueOnce(res(page([entry()])));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentShortlistPanel {...props} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Nope");
    fireEvent.click(screen.getByRole("button", { name: "Retry loading the shortlist" }));
    expect(await screen.findByText("Agency U")).toBeInTheDocument();
  });

  it("removes after confirmation; Cancel has focus; a 404 after own delete counts as done", async () => {
    let listed = [entry()];
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        listed = [];
        return Promise.resolve(res(null, 404));
      }
      return Promise.resolve(res(page(listed)));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentShortlistPanel {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove Agency U" }));
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    expect(await screen.findByText("No universities shortlisted yet.")).toBeInTheDocument();
  });

  it("tells the parent when the student is gone", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Student not found" }, 404))));
    render(<AgentShortlistPanel {...props} />);
    await waitFor(() => expect(props.onStudentGone).toHaveBeenCalled());
  });
});
```

- [ ] **Step 2: Run the tests and confirm they fail.**

Run: `cd apps/web && npx vitest run tests/components/AgentShortlistPanel.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement** `apps/web/components/AgentShortlistPanel.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import AgentShortlistForm from "./AgentShortlistForm";
import { detailMessage, isPage, type Page } from "@/lib/apiErrors";
import { PAGE_SIZE, type ShortlistEntry, shortlistUrl } from "@/lib/agentShortlist";

// AGN-007 (DEC-SCOPE-048 D2/D3/D5): a student's university shortlist inside the AGN-004 detail view. Masters and staff (in scope) add,
// edit and remove; an archived student's shortlist is read-only. Paging and the inline confirm follow AgentStudentsPanel.
type Editing = { mode: "add" } | { mode: "edit"; entry: ShortlistEntry } | null;
const ADD_ID = "shortlist-add";

export default function AgentShortlistPanel({ studentId, archived, onStudentGone, onStudentChanged }: { studentId: string; archived: boolean; onStudentGone: () => void; onStudentChanged: () => void }) {
  const [data, setData] = useState<Page<ShortlistEntry> | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<Editing>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const request = useRef<AbortController | null>(null);
  const returnFocusTo = useRef<string>(ADD_ID);
  // The parent's callbacks are re-created on each of its renders; a ref keeps them out of `load`'s dependencies (no refetch loop).
  const gone = useRef(onStudentGone);
  gone.current = onStudentGone;

  const load = useCallback(() => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setLoadError(null);
    fetch(`${shortlistUrl(studentId)}?limit=${PAGE_SIZE}&offset=${offset}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (controller.signal.aborted) return;
        if (response.status === 404) return gone.current();
        if (!response.ok || !isPage<ShortlistEntry>(body)) return setLoadError(detailMessage(body?.detail, "Unable to load the shortlist."));
        if (body.items.length === 0 && body.offset > 0) return setOffset(Math.max(0, body.offset - PAGE_SIZE));
        setData(body);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadError("Unable to load the shortlist.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [studentId, offset]);

  useEffect(load, [load]);
  useEffect(() => () => request.current?.abort(), []);

  function closeForm() {
    setEditing(null);
    requestAnimationFrame(() => document.getElementById(returnFocusTo.current)?.focus());
  }

  async function remove(e: ShortlistEntry) {
    try {
      const response = await fetch(`${shortlistUrl(studentId)}/${e.id}`, { method: "DELETE" });
      if (response.status === 409) return onStudentChanged();
      if (response.ok || response.status === 404) setNotice(`${e.university.name} removed from the shortlist.`); // 404 after our own delete = done
      else setLoadError(detailMessage((await response.json().catch(() => null))?.detail, "Unable to remove the entry."));
    } catch {
      setLoadError("Network error. Check your connection and try again.");
    }
    setConfirmId(null);
    load();
  }

  const writable = !archived;
  return (
    <section aria-labelledby={`shortlist-${studentId}`} style={{ marginTop: 16 }}>
      <h5 id={`shortlist-${studentId}`}>University shortlist</h5>
      {archived && <p className="muted">This student is archived; the shortlist is read-only.</p>}
      <p aria-live="polite">{notice}</p>
      {writable &&
        (editing ? (
          <AgentShortlistForm
            studentId={studentId}
            mode={editing.mode}
            entry={editing.mode === "edit" ? editing.entry : undefined}
            onCancel={closeForm}
            onGone={onStudentGone}
            onConflict={onStudentChanged}
            onSaved={() => {
              setNotice("Saved to shortlist.");
              closeForm();
              load();
            }}
          />
        ) : (
          <button id={ADD_ID} type="button" className="btn small" onClick={() => ((returnFocusTo.current = ADD_ID), setEditing({ mode: "add" }))}>
            Add university to shortlist
          </button>
        ))}
      <div aria-busy={loading} style={{ marginTop: 12, opacity: loading && data ? 0.6 : 1 }}>
        {loadError ? (
          <>
            <p className="form-error" role="alert">{loadError}</p>
            <button type="button" className="btn secondary small" aria-label="Retry loading the shortlist" onClick={load}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted">Loading the shortlist…</p>
        ) : data.items.length === 0 ? (
          <p className="muted">No universities shortlisted yet.</p>
        ) : (
          <>
            <ul aria-label="Shortlist" className="grid two" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {data.items.map((e) => (
                <li key={e.id} className="card">
                  <strong>{e.university.name}</strong> {e.university.source === "agency" && <span className="badge">Agency</span>}
                  <p className="muted">
                    <span>{e.university.country ?? "—"}</span>
                    {e.course && <> · <span>{e.course.title}</span></>}
                  </p>
                  {e.intake && <p>Intake: {e.intake}</p>}
                  {e.tuition_fee && <p>Tuition fee: {e.tuition_fee}</p>}
                  {e.entry_requirements && (
                    <details>
                      <summary>Entry requirements</summary>
                      <p style={{ whiteSpace: "pre-line" }}>{e.entry_requirements}</p>
                    </details>
                  )}
                  {writable &&
                    (confirmId === e.id ? (
                      <span role="group" aria-label={`Confirm remove ${e.university.name}`}>
                        <button type="button" className="btn small" onClick={() => void remove(e)}>Confirm remove</button>{" "}
                        <button type="button" className="btn secondary small" autoFocus onClick={() => setConfirmId(null)}>Cancel</button>
                      </span>
                    ) : (
                      <>
                        <button id={`shortlist-edit-${e.id}`} type="button" className="btn secondary small" aria-label={`Edit ${e.university.name}`} onClick={() => ((returnFocusTo.current = `shortlist-edit-${e.id}`), setEditing({ mode: "edit", entry: e }))}>
                          Edit
                        </button>{" "}
                        <button type="button" className="btn secondary small" aria-label={`Remove ${e.university.name}`} onClick={() => setConfirmId(e.id)}>
                          Remove
                        </button>
                      </>
                    ))}
                </li>
              ))}
            </ul>
            <p className="muted">Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</p>
            <button type="button" className="btn secondary small" aria-label="Previous page of the shortlist" disabled={data.offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>{" "}
            <button type="button" className="btn secondary small" aria-label="Next page of the shortlist" disabled={data.offset + data.items.length >= data.total || loading} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
          </>
        )}
      </div>
    </section>
  );
}
```

The paging buttons have distinct aria-labels ("… of the shortlist") because the student list's Previous/Next sit on the same page. Using the same label twice would make the AGN-004 tests' `getByRole("button", { name: "Next page" })` ambiguous.

The parent passes `onStudentGone={onClose}`, which is re-created on each render of `AgentStudentsPanel`. The `gone` ref keeps it out of `load`'s dependencies, so typing in the student search doesn't refetch the shortlist.

In the remove test, the list GET returns the entry until DELETE runs and an empty page afterwards. `load()` after the delete then shows the empty state.

The empty state is shown on its own; the separate Add button above it is the action. The empty-state test finds both.

Format with prettier and lint the file. Keep it under 200 lines after formatting; if it's over, move the `<li>` body into a `ShortlistCard` function in the same file.

- [ ] **Step 4: Mount the panel** in `AgentStudentDetailPanel.tsx`.

Add `import AgentShortlistPanel from "./AgentShortlistPanel";`. Inside the non-editing branch (`<>…</>`), after the Close button, add:

```tsx
          <AgentShortlistPanel studentId={detail.id} archived={detail.status === "archived"} onStudentGone={onClose} onStudentChanged={onClose} />
```

Add the comment `{/* AGN-007 (DEC-SCOPE-048): the student's university shortlist; hidden while the record is being edited. */}` above it. `onClose` closes the detail view. The parent list already handles a student that is gone or changed on its next load; this is the AGN-004 behaviour for a missing student.

- [ ] **Step 5: Run the tests and confirm they pass**, including the AGN-004 panel suite.

Run: `cd apps/web && npx vitest run tests/components/AgentShortlistPanel.test.tsx tests/components/AgentStudentsPanel.test.tsx tests/components/AgentStudentForm.test.tsx && npx tsc --noEmit`
Expected: all pass.

If an `AgentStudentsPanel` test fails because its `fetch` stub now also receives the shortlist GET, change **only** that test's stub to answer `/shortlist` URLs with an empty page. Record it as a test-only deviation in the RTM; don't change any assertion.

- [ ] **Step 6: Commit.**

```bash
git add apps/web/components/AgentShortlistPanel.tsx apps/web/components/AgentStudentDetailPanel.tsx apps/web/tests/components/AgentShortlistPanel.test.tsx apps/web/tests/components/AgentStudentsPanel.test.tsx
git commit -m "feat(agn-007): university shortlist in the agency student detail view"
```

---

### Task 10: End-to-end spec

**Files:**
- Create: `apps/web/tests/e2e/agn-007-shortlist.spec.ts`

**Interfaces:**
- Consumes the whole feature.
- Reuses `tests/e2e/helpers/agency.ts` (`signIn`, `adminActivate`, `registerApprovedAgency`, moved there by AGN-003). Open it and use its exact exports.

- [ ] **Step 1: Write the spec.**

```ts
import { expect, test, type Page } from "@playwright/test";

import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";
import { E2E_PASSWORD } from "./helpers/welcome";

// AGN-007 -- a Master adds an agency university; Staff shortlist a catalogue entry and an agency entry; /public never shows the
// agency university; Staff get no write controls on Universities; 375 px. A fresh agency (the AGN-004 AC09 flow) keeps it independent
// of earlier runs; unique names per run (the E2E database is shared and keeps rows).
const MASTER_PASSWORD = "Sup3r-Secret-Pass!";
const stamp = () => Date.now() + Math.floor(Math.random() * 1e4);

async function addStudent(page: Page, name: string) {
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  await form.getByRole("button", { name: "Save student" }).click();
  await expect(page.getByText(`${name} added.`)).toBeVisible();
}

test("Master adds a university; Staff shortlist catalogue and agency entries (AGN-007-AC01/02/05/06/13)", async ({ page, browser }) => {
  test.setTimeout(150_000);
  const id = stamp();
  const uniName = `E2E Agency Uni ${id}`;
  const student = `Shortlist Me ${id}`;
  const staffEmail = `agn007-s-${id}@example.local`;
  const masterEmail = await registerApprovedAgency(page, id, "agn007");

  // Master: a staff member, an agency university, and a student assigned to the staff member.
  await signIn(page, masterEmail, MASTER_PASSWORD);
  await page.goto("/overseas/agent/team");
  const staffForm = page.getByRole("form", { name: "Add a staff member" });
  await staffForm.getByLabel("Full name").fill("Upsilon Staff");
  await staffForm.getByLabel("Email").fill(staffEmail);
  await staffForm.getByRole("button", { name: "Add staff" }).click();
  const code = (await page.getByText(/-S001 created/).textContent())!.match(/(\S+-S001)/)![1];

  await page.goto("/overseas/agent/universities");
  await page.getByRole("button", { name: "Add university" }).click();
  const form = page.getByRole("form", { name: "Add university" });
  await form.getByLabel("Name (required)").fill(uniName);
  await form.getByLabel("Country (required)").fill("Atlantis");
  await form.getByRole("button", { name: "Save university" }).click();
  await expect(page.getByText(`${uniName} added.`)).toBeVisible();

  await page.goto("/overseas/agent/students");
  await addStudent(page, student);
  await page.getByRole("button", { name: `Assign ${student}`, exact: true }).click();
  const choice = page.getByRole("group", { name: `Assign ${student}` });
  await choice.getByLabel("Assign to").selectOption({ label: `${code} · Upsilon Staff` });
  await choice.getByRole("button", { name: "Save assignment" }).click();
  await expect(page.getByText(`${student} assigned to ${code} · Upsilon Staff.`)).toBeVisible();

  // Staff: view-only Universities; shortlist a catalogue entry and the agency entry from the student detail view.
  const staffPage = await (await browser.newContext()).newPage();
  await adminActivate(staffPage.request, staffEmail);
  await signIn(staffPage, staffEmail, E2E_PASSWORD);
  await staffPage.goto("/overseas/agent/universities");
  await expect(staffPage.getByRole("list", { name: "Agency universities" }).getByText(uniName)).toBeVisible();
  await expect(staffPage.getByRole("button", { name: "Add university" })).toHaveCount(0);
  await staffPage.goto("/overseas/agent/students");
  await staffPage.getByRole("button", { name: `View ${student}`, exact: true }).click();
  await staffPage.getByRole("button", { name: "Add university to shortlist" }).click();
  await staffPage.getByLabel("University (required)").selectOption({ index: 1 }); // first catalogue university
  await staffPage.getByLabel("Course").selectOption({ index: 1 });
  await staffPage.getByRole("button", { name: "Save to shortlist" }).click();
  await expect(staffPage.getByText("Saved to shortlist.")).toBeVisible();
  await staffPage.getByRole("button", { name: "Add university to shortlist" }).click();
  await staffPage.getByLabel("University (required)").selectOption({ label: `${uniName} — Atlantis` });
  await staffPage.getByLabel("Course").fill("BA Typed E2E");
  await staffPage.keyboard.press("Enter");
  await expect(staffPage.getByRole("list", { name: "Shortlist" }).getByText(uniName)).toBeVisible();

  // /public never shows it.
  const anon = await (await browser.newContext()).newPage();
  await anon.goto("/overseas/universities");
  await expect(anon.getByText(uniName)).toHaveCount(0);

  // 375 px: no horizontal scroll on the detail view.
  await staffPage.setViewportSize({ width: 375, height: 800 });
  const overflow = await staffPage.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
```

The catalogue step picks `{ index: 1 }`, the first catalogue university, which assumes the seed has at least one catalogue university with a course. If the seeded first university has no courses, pick by the label of a seeded university that does: check `seed.py:318`.

- [ ] **Step 2: Run the spec.** First ask the user to confirm the stack is up and seeded.

Run: `cd apps/web && E2E_BASE_URL=http://localhost:3007 npx playwright test tests/e2e/agn-007-shortlist.spec.ts --workers=1`
Expected: 1 passed. On failure, open only that test's trace and screenshot.

- [ ] **Step 3: Run the neighbouring specs.**

Run: `cd apps/web && E2E_BASE_URL=http://localhost:3007 npx playwright test tests/e2e/agn-004-agent-students.spec.ts tests/e2e/agn-003-staff-permissions.spec.ts tests/e2e/ovs-001-discovery.spec.ts tests/e2e/ovs-002-application.spec.ts --workers=1`
Expected: all pass.

- [ ] **Step 4: Commit.**

```bash
git add apps/web/tests/e2e/agn-007-shortlist.spec.ts
git commit -m "test(agn-007): end-to-end shortlist flow, /public invisibility and 375 px"
```

---

### Task 11: Documentation and traceability

**Files (modify unless noted):**
- `docs/delivery/ENHANCEMENT_BACKLOG.md`: a new `## AGN-007` section after AGN-021, holding the requirement, AC01–AC14 copied from spec §8, and the source citations.
- `docs/decisions/PRODUCT_DECISION_REGISTER.md`: `### DEC-SCOPE-048 — Agent student university shortlist and agency university database (AGN-007)`. Use the AGN-021 entry's structure:
  - Status `CONFIRMED_CURRENT`, resolved in-session 2026-10-01 (`EXPLICIT_APPROVAL`).
  - D1–D10 from spec §1.
  - "Conflicts recorded, not silently resolved": the `DEC-SCOPE-035 D4` citation; superseding `DEC-SCOPE-044` P3 for the two rows.
  - An ID note: provisional number, skipping 047 for AGN-006.
  - Also append a dated note to `DEC-SCOPE-038` D13 and `DEC-SCOPE-044` P3, in the parenthetical style used there.
- `docs/evidence/CONFLICT_MATRIX.md` C-10: an update line saying EVID-015 §5 Step 3 and the §6 "University Database"/"Add University" rows are decided by `DEC-SCOPE-048`.
- `docs/architecture/API_CONTRACT.md` §8: an `AGN-007 / DEC-SCOPE-048` block with the route tables from spec §5.1–§5.2, the entry shape, the errors and D10.
- `docs/architecture/DATA_MODEL.md`: `### 6.8d AgentUniversity, AgentStudentShortlistEntry (AGN-007, migration 0055_agent_shortlist)`.
- `docs/architecture/RBAC_MATRIX.md` §2.8: University Database (Master ✅ full on the agency list plus view of the catalogue; Staff 👁 view) and Add University (Master ✅ agency list; Staff ❌ 403; shared catalogue admin-only). Point to `test_agn_003_matrix.py`.
- `docs/architecture/SECURITY_CONTROLS.md`: one row with the controls from spec §7.
- `docs/architecture/THREAT_MODEL.md`: a threat entry covering an agency-private university leaking to another agency or `/public`, and staff writing outside their scope, with the mitigations and tests.
- `docs/ux/SCREEN_CATALOG.md` + `screen_catalog.json`: an `SCR-AGT-008` update (the shortlist panel) and a new `SCR-AGT-009` Universities (`/overseas/agent/universities`). Check the next free SCR number first.
- `docs/ux/ROLE_NAVIGATION.md`: the Agent nav gains Universities, visible to both roles.
- `docs/delivery/RAID.md`: a new issue for `create_bridged_application` (`admin.py:1577`) storing `course_id` without the course-belongs-to-university check. It's out of scope for AGN-007 and needs a follow-up ticket.
- `docs/quality/RTM.md`: an `AGN-007` row in the AGN-021 row's format, with the chain from requirement to decision to backlog to spec and plan to docs to code to tests (AC to test mapping from spec §8). Status `IMPLEMENTED, NOT COMPLETE` until browser QA.
- `docs/superpowers/specs/2026-10-01-agn-007-student-shortlist-design.md`: final numbers, if Task 0 changed them.

- [ ] **Step 1: Write all of the above.** Use the real numbers from Task 0 and the real test names from Tasks 1–10.
- [ ] **Step 2: Check the cross-references.** Every `DEC-SCOPE-048` and `0055_agent_shortlist` mention matches across code and docs: `grep -rn "DEC-SCOPE-048\|0055_agent_shortlist" apps docs | wc -l`, then eyeball the list for a stale number.
- [ ] **Step 3: Commit.**

```bash
git add docs
git commit -m "docs(agn-007): decision, backlog, contracts, data model, RBAC, security, screens, RTM"
```

---

### Task 12: Verification (lite set) and evidence

**Files:** `docs/quality/RTM.md` (evidence only).

- [ ] **Step 1: Run the lite backend set** and read the output.

```bash
API_TEST tests/test_agn_007_schema.py tests/test_agn_007_universities.py tests/test_agn_007_shortlist.py tests/test_agn_007_isolation.py \
  tests/test_agn_001_tenancy.py tests/test_agn_002_staff_access.py tests/test_agn_003_matrix.py tests/test_agn_003_permissions.py \
  tests/test_agn_004_students.py tests/test_agn_004_student_actions.py tests/test_agn_004_staff_scope.py tests/test_agn_004_staff_guards.py \
  tests/test_agn_004_migration.py tests/test_agn_005_qa_fixes.py tests/test_agn_021_activity.py \
  tests/test_ovs_001_discovery.py tests/test_ovs_002_application.py tests/test_pub_003_catalogue.py
```

List the files explicitly: globs don't expand in the container. Expected: 0 failed. Note the pass count.

- [ ] **Step 2: Run the backend lint** on the changed Python files: `ruff check $(git diff --name-only origin/main -- 'apps/api/*.py')`. It must be clean for the changed files.
- [ ] **Step 3: Run the web checks.**

```bash
cd apps/web && npx vitest run && npx tsc --noEmit && npx eslint components lib tests/components tests/lib && npm run build
```

Expected: 0 failures. Pre-existing time-zone failures in untouched files (`LocalTime.test.tsx`, `formatDate.test.ts::viewerTimeZone`) are reported as such, not fixed.
- [ ] **Step 4: Run the E2E** for AGN-007 and its neighbours (Task 10 steps 2–3).
- [ ] **Step 5: Check the diff.** `git diff origin/main --stat` lists only AGN-007 files. Run `git diff origin/main | grep -n "console.log\|debugger\|\.only(\|skip("` and expect no hits.
- [ ] **Step 6: Record the evidence** in the AGN-007 RTM row: commands, counts, and "full backend suite not run (owner's standing choice)". Then commit with `git commit -m "docs(agn-007): verification evidence"`.
- [ ] **Step 7: Hand over** to the owner for browser QA and the decision on the independent review. Don't mark COMPLETE before that.
