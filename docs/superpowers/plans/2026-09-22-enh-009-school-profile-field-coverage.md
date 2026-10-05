# ENH-009 School Profile Field Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 15 School Profile fields (`EVID-014`) the codebase is missing today, with Branch
modeled as a plain field, admin-only create/edit, and no changes to School-domain authorization
scoping.

**Architecture:** One additive, nullable-only migration on the existing `schools` table; new
`SchoolCreate`/`SchoolUpdate`/`SchoolOut` Pydantic schemas replacing today's untyped `payload: dict`
on three existing endpoints; one new admin-only lookup endpoint; a widened read-only list (an
existing generic mechanism, one function's columns changed); one new frontend edit panel reusing
the existing create-panel's form conventions.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Alembic + Pydantic v2 (backend, `apps/api`);
Next.js App Router + plain hand-rolled CSS, no component library (frontend, `apps/web`); pytest +
httpx `AsyncClient` (backend tests); Vitest + Testing Library (frontend unit tests); Playwright
(E2E).

**Spec:** `docs/superpowers/specs/2026-09-22-enh-009-school-profile-design.md`
**Decision record:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` → `DEC-SCOPE-025`

## Global Constraints

- Admin-only: every new/changed endpoint keeps the existing manual `if user.role not in
  {"overseas_admin","super_admin"}: raise HTTPException(403, "Overseas Admin role required")`
  in-handler check — do not refactor to `Depends(require_role(...))` (unrelated-module change).
- `GET /overseas-admin/schools/lookup?code=` is narrower than its sibling
  `school-students/lookup`: `{"overseas_admin","super_admin"}` only, **excluding `counselor`**.
- All new `schools` columns are nullable, no backfill, no data loss.
- `coordinator_email`'s existing in-handler `_valid_email()` call and its exact error text stay
  untouched (Hyrum's Law — existing callers may depend on that exact string). The new `email` field
  (School's own contact email) is brand new with no existing callers, so it uses plain Pydantic
  `EmailStr` directly — no need to preserve behavior that doesn't exist yet.
- `tier`'s existing manual validation (`if tier and tier not in {"bronze","silver","gold","platinum"}:
  raise HTTPException(422, "tier must be one of bronze, silver, gold, platinum")`) stays exactly as
  it is — not folded into a Pydantic `Literal`, to avoid changing its existing error text.
  `board` (a brand new field) uses a Pydantic `Literal["CBSE","ICSE","State","IB","Other"] | None`.
- `model_config = {"extra": "forbid"}` (plain dict, not `pydantic.ConfigDict` — verified against
  `schemas.py:614`) on `SchoolCreate`/`SchoolUpdate`.
- New string columns use the existing `_fit(value, label, limit)` helper (`admin.py:57-62`) for
  length capping — same 422-naming-the-field behavior as `name`/`full_name` today.
- `school_code` generation reuses `unique_student_code(db, School.school_code)`
  (`core/identifiers.py:23`) verbatim — no new ID-generation code.
- `AuditLog.metadata_json` for the new `school.profile_update` action logs **changed field names
  only**, never values (`DEC-SCOPE-025`).
- Running backend tests requires the project's own Postgres stack to be up (this session does not
  start/stop it — the user runs `docker compose` themselves). Confirm it's reachable before Task 1's
  RED step; if not, ask the user to start it rather than guessing.

---

### Task 1: Migration — 13 new nullable columns on `schools`

**Files:**
- Create: `apps/api/alembic/versions/0035_school_profile_fields.py`
- Test: `apps/api/tests/test_sch_003_school_onboarding.py` (new test appended to existing file)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `schools.school_code` (unique, indexed), `schools.branch`, `schools.address`,
  `schools.contact_number`, `schools.email`, `schools.website`, `schools.grades_available`,
  `schools.board`, `schools.partnership_date`, `schools.mou_reference`, `schools.edusphere_bdm`,
  `schools.monthly_visit_schedule`, `schools.vice_principal_name` — all nullable. Task 2 assigns
  these as SQLAlchemy `Mapped` attributes on the `School` model; Task 3+ read/write them.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_sch_003_school_onboarding.py -- append at end of file

@pytest.mark.asyncio
async def test_school_table_has_the_new_profile_columns(db_session):
    from sqlalchemy import text

    row = await db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'schools' AND column_name = ANY(:cols)"
    ), {"cols": [
        "school_code", "branch", "address", "contact_number", "email", "website",
        "grades_available", "board", "partnership_date", "mou_reference",
        "edusphere_bdm", "monthly_visit_schedule", "vice_principal_name",
    ]})
    found = {r[0] for r in row.fetchall()}
    assert found == {
        "school_code", "branch", "address", "contact_number", "email", "website",
        "grades_available", "board", "partnership_date", "mou_reference",
        "edusphere_bdm", "monthly_visit_schedule", "vice_principal_name",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py::test_school_table_has_the_new_profile_columns -v`
Expected: FAIL — the assertion fails because `found` is an empty set (none of the columns exist yet).

- [ ] **Step 3: Write the migration**

```python
# apps/api/alembic/versions/0035_school_profile_fields.py
"""Add School Profile fields (ENH-009, DEC-SCOPE-025).

Revision ID: 0035_school_profile_fields
Revises: 0034_school_transfer_requests

docs/superpowers/specs/2026-09-22-enh-009-school-profile-design.md §2. Additive only: 13 new
nullable columns on the existing `schools` table plus a unique index on `school_code`. No existing
column is altered, no existing row is read or written -- there is nothing to backfill.
`downgrade()` drops the index and all 13 columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0035_school_profile_fields"
down_revision = "0034_school_transfer_requests"
branch_labels = None
depends_on = None

_NEW_COLUMNS = [
    ("school_code", sa.String(8)),
    ("branch", sa.String(200)),
    ("address", sa.String(500)),
    ("contact_number", sa.String(30)),
    ("email", sa.String(255)),
    ("website", sa.String(255)),
    ("grades_available", sa.String(200)),
    ("board", sa.String(20)),
    ("partnership_date", sa.Date()),
    ("mou_reference", sa.String(255)),
    ("edusphere_bdm", sa.String(200)),
    ("monthly_visit_schedule", sa.String(200)),
    ("vice_principal_name", sa.String(200)),
]


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {c["name"] for c in inspector.get_columns("schools")}
    for name, col_type in _NEW_COLUMNS:
        if name not in existing:
            op.add_column("schools", sa.Column(name, col_type, nullable=True))
    existing_indexes = {i["name"] for i in inspector.get_indexes("schools")}
    if "ix_schools_school_code" not in existing_indexes:
        op.create_index("ix_schools_school_code", "schools", ["school_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_schools_school_code", table_name="schools")
    for name, _ in reversed(_NEW_COLUMNS):
        op.drop_column("schools", name)
```

Apply it to the running test database:

Run: `cd apps/api && python -m alembic upgrade head`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py::test_school_table_has_the_new_profile_columns -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/alembic/versions/0035_school_profile_fields.py apps/api/tests/test_sch_003_school_onboarding.py
git commit -m "feat(enh-009): add School Profile columns migration"
```

---

### Task 2: `School` model — map the 13 new columns

**Files:**
- Modify: `apps/api/app/models.py:928-948` (the `School` class)
- Test: `apps/api/tests/test_sch_003_school_onboarding.py`

**Interfaces:**
- Consumes: the 13 DB columns from Task 1.
- Produces: `School.school_code: str | None`, `.branch`, `.address`, `.contact_number`, `.email`,
  `.website`, `.grades_available`, `.board`, `.partnership_date: date | None`, `.mou_reference`,
  `.edusphere_bdm`, `.monthly_visit_schedule`, `.vice_principal_name: str | None` — all
  `Mapped[str | None]` (or `date | None` for `partnership_date`) SQLAlchemy attributes. Task 4+
  read/write these directly on `School` instances.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_sch_003_school_onboarding.py -- append at end of file

@pytest.mark.asyncio
async def test_school_model_exposes_the_new_profile_attributes(db_session):
    school = School(
        name="Attr Test School", created_by_user_id=uuid.uuid4(),
        school_code="ABCD1234", branch="North Campus", address="1 Test Rd",
        contact_number="+91-9000000000", email="school@example.local",
        website="https://example.local", grades_available="1-10", board="CBSE",
        mou_reference="MOU-2026-001", edusphere_bdm="Jane BDM",
        monthly_visit_schedule="2nd Tuesday monthly", vice_principal_name="John VP",
    )
    db_session.add(school)
    await db_session.commit()
    reloaded = await db_session.get(School, school.id)
    assert reloaded.school_code == "ABCD1234"
    assert reloaded.branch == "North Campus"
    assert reloaded.board == "CBSE"
    assert reloaded.vice_principal_name == "John VP"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py::test_school_model_exposes_the_new_profile_attributes -v`
Expected: FAIL with `TypeError: 'school_code' is an invalid keyword argument for School` (the
column exists in the DB from Task 1, but the ORM model doesn't know about it yet).

- [ ] **Step 3: Add the mapped attributes**

```python
# apps/api/app/models.py -- replace the School class (currently lines 928-948)

class School(Base, TimestampMixin):
    """School partner record (SCH-003, DATA_MODEL.md §6.11; profile fields added ENH-009,
    DEC-SCOPE-025). `EVID-014`'s full field list is now confirmed in scope -- see the
    design doc for what's stored here vs. computed at read time in `SchoolOut`."""

    __tablename__ = "schools"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tier_valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # ENH-009 / DEC-SCOPE-025: School Profile fields (EVID-014). All nullable, additive.
    school_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grades_available: Mapped[str | None] = mapped_column(String(200), nullable=True)
    board: Mapped[str | None] = mapped_column(String(20), nullable=True)
    partnership_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    mou_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    edusphere_bdm: Mapped[str | None] = mapped_column(String(200), nullable=True)
    monthly_visit_schedule: Mapped[str | None] = mapped_column(String(200), nullable=True)
    vice_principal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py::test_school_model_exposes_the_new_profile_attributes -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/models.py apps/api/tests/test_sch_003_school_onboarding.py
git commit -m "feat(enh-009): map School Profile columns onto the School model"
```

---

### Task 3: `SchoolCreate` / `SchoolUpdate` / `SchoolOut` schemas

**Files:**
- Modify: `apps/api/app/schemas.py` (append new section)
- Test: new file `apps/api/tests/test_enh_009_school_profile_schemas.py`

**Interfaces:**
- Consumes: nothing beyond stdlib/pydantic (schemas are pure data shapes).
- Produces: `SchoolCreate(BaseModel)` (fields: `name: str`, `city: str | None`, `state: str | None`,
  `tier: str | None`, `coordinator_full_name: str`, `coordinator_email: str`, `branch: str | None`,
  `address: str | None`, `contact_number: str | None`, `email: EmailStr | None`,
  `website: str | None`, `grades_available: str | None`,
  `board: Literal["CBSE","ICSE","State","IB","Other"] | None`, `partnership_date: date | None`,
  `mou_reference: str | None`, `edusphere_bdm: str | None`, `monthly_visit_schedule: str | None`,
  `vice_principal_name: str | None`); `SchoolUpdate(BaseModel)` (every field from `SchoolCreate`'s
  12 new profile fields, plus `tier: str | None` and `tier_valid_until: date | None`, all optional,
  no `name`/`city`/`state`/`coordinator_*`); `SchoolOut(BaseModel)` (all stored fields plus
  `id: UUID`, `student_count: int`, `teacher_count: int`, `principal_name: str | None`,
  `school_coordinator_name: str | None`, `career_counsellor_names: list[str]`,
  `created_at: datetime`). Task 4+ construct/consume these directly.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_enh_009_school_profile_schemas.py
"""ENH-009 / DEC-SCOPE-025 -- SchoolCreate/SchoolUpdate/SchoolOut schema behavior."""

import pytest
from pydantic import ValidationError

from app.schemas import SchoolCreate, SchoolUpdate


def test_school_create_rejects_an_unexpected_field():
    with pytest.raises(ValidationError):
        SchoolCreate(
            name="X", coordinator_full_name="Y", coordinator_email="y@example.local",
            role="super_admin",  # smuggled field -- must be a loud rejection, not silently dropped
        )


def test_school_create_rejects_an_invalid_board_value():
    with pytest.raises(ValidationError):
        SchoolCreate(
            name="X", coordinator_full_name="Y", coordinator_email="y@example.local",
            board="Cambridge",
        )


def test_school_create_accepts_a_valid_board_value():
    school = SchoolCreate(
        name="X", coordinator_full_name="Y", coordinator_email="y@example.local", board="IB",
    )
    assert school.board == "IB"


def test_school_update_allows_every_field_to_be_omitted():
    update = SchoolUpdate()
    assert update.model_dump(exclude_unset=True) == {}


def test_school_create_validates_the_new_contact_email_format():
    with pytest.raises(ValidationError):
        SchoolCreate(
            name="X", coordinator_full_name="Y", coordinator_email="y@example.local",
            email="not-an-email",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_enh_009_school_profile_schemas.py -v`
Expected: FAIL with `ImportError: cannot import name 'SchoolCreate' from 'app.schemas'`

- [ ] **Step 3: Write the schemas**

```python
# apps/api/app/schemas.py -- append at end of file

# --- ENH-009 / DEC-SCOPE-025: School Profile field coverage (EVID-014) ---

SchoolBoard = Literal["CBSE", "ICSE", "State", "IB", "Other"]


class SchoolCreate(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    tier: str | None = None
    coordinator_full_name: str = Field(min_length=1, max_length=160)
    coordinator_email: str
    branch: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    contact_number: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    website: str | None = Field(default=None, max_length=255)
    grades_available: str | None = Field(default=None, max_length=200)
    board: SchoolBoard | None = None
    partnership_date: date | None = None
    mou_reference: str | None = Field(default=None, max_length=255)
    edusphere_bdm: str | None = Field(default=None, max_length=200)
    monthly_visit_schedule: str | None = Field(default=None, max_length=200)
    vice_principal_name: str | None = Field(default=None, max_length=200)


class SchoolUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    tier: str | None = None
    tier_valid_until: date | None = None
    branch: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    contact_number: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    website: str | None = Field(default=None, max_length=255)
    grades_available: str | None = Field(default=None, max_length=200)
    board: SchoolBoard | None = None
    partnership_date: date | None = None
    mou_reference: str | None = Field(default=None, max_length=255)
    edusphere_bdm: str | None = Field(default=None, max_length=200)
    monthly_visit_schedule: str | None = Field(default=None, max_length=200)
    vice_principal_name: str | None = Field(default=None, max_length=200)


class SchoolOut(BaseModel):
    id: UUID
    name: str
    city: str | None
    state: str | None
    tier: str | None
    tier_valid_until: date | None
    school_code: str | None
    branch: str | None
    address: str | None
    contact_number: str | None
    email: str | None
    website: str | None
    grades_available: str | None
    board: str | None
    partnership_date: date | None
    mou_reference: str | None
    edusphere_bdm: str | None
    monthly_visit_schedule: str | None
    vice_principal_name: str | None
    student_count: int
    teacher_count: int
    principal_name: str | None
    school_coordinator_name: str | None
    career_counsellor_names: list[str]
    created_at: datetime
```

(`Literal`, `date`, `datetime`, `UUID`, `Field`, `EmailStr`, `BaseModel` are all already imported at
the top of `schemas.py` — no new imports needed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_enh_009_school_profile_schemas.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas.py apps/api/tests/test_enh_009_school_profile_schemas.py
git commit -m "feat(enh-009): add SchoolCreate/SchoolUpdate/SchoolOut schemas"
```

---

### Task 4: `_school_out()` helper — the shared computed-fields query

**Files:**
- Modify: `apps/api/app/api/admin.py` (add a module-level helper, near the other `_`-prefixed
  helpers around line 57)
- Test: `apps/api/tests/test_sch_003_school_onboarding.py`

**Interfaces:**
- Consumes: `School` (Task 2), `SchoolOut` (Task 3), `AsyncSession`.
- Produces: `async def _school_out(db: AsyncSession, school: School) -> SchoolOut` — builds the
  full response shape including the three computed role-derived names and the two computed counts.
  Tasks 5/6/7/8 all call this instead of hand-building response dicts, so the computed-field logic
  exists exactly once.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_sch_003_school_onboarding.py -- append at end of file

@pytest.mark.asyncio
async def test_school_out_computes_counts_and_role_derived_names(client, db_session):
    from app.api.admin import _school_out
    from app.models import SchoolStaffAssignment, SchoolStudent

    result = await _create_school(client, db_session)
    school = await db_session.get(School, result["id"])

    principal = User(
        email=f"vp-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
        full_name="Test Principal", role="school_principal", division="overseas", active=True,
        profile={"school_id": str(school.id)},
    )
    counsellor = User(
        email=f"cc-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
        full_name="Test Counsellor", role="career_counselor", division="overseas", active=True,
    )
    db_session.add_all([principal, counsellor])
    await db_session.flush()
    db_session.add(SchoolStaffAssignment(user_id=counsellor.id, school_id=school.id, role="career_counselor", assigned_by_user_id=result["admin"].id))
    db_session.add(SchoolStudent(school_id=school.id, full_name="A Student", grade_level=5))
    await db_session.commit()

    out = await _school_out(db_session, school)
    assert out.student_count == 1
    assert out.teacher_count == 0
    assert out.principal_name == "Test Principal"
    assert out.school_coordinator_name is not None  # the seed Coordinator from _create_school
    assert out.career_counsellor_names == ["Test Counsellor"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py::test_school_out_computes_counts_and_role_derived_names -v`
Expected: FAIL with `ImportError: cannot import name '_school_out' from 'app.api.admin'`

- [ ] **Step 3: Write the helper**

```python
# apps/api/app/api/admin.py -- add near the other module-level helpers (after _fit(), ~line 63)

async def _school_out(db: AsyncSession, school: "School") -> "SchoolOut":
    """ENH-009 / DEC-SCOPE-025: the one place that assembles a School's full profile response,
    including the fields that are deliberately computed rather than stored -- student/teacher
    counts, and the Principal/Coordinator/Career Counsellor names, all of which are derived from
    role assignments rather than duplicated onto `School` itself (see the design doc §2)."""
    from app.models import SchoolStaffAssignment, SchoolStudent

    student_count = await db.scalar(
        select(func.count()).select_from(SchoolStudent).where(SchoolStudent.school_id == school.id)
    )
    teacher_count = await db.scalar(
        select(func.count()).select_from(User).where(
            User.role == "school_teacher", User.profile["school_id"].as_string() == str(school.id)
        )
    )
    principal = await db.scalar(
        select(User).where(User.role == "school_principal", User.profile["school_id"].as_string() == str(school.id))
    )
    coordinator = await db.scalar(
        select(User).where(User.role == "school_coordinator", User.profile["school_id"].as_string() == str(school.id))
    )
    counsellor_rows = (await db.scalars(
        select(User).join(SchoolStaffAssignment, SchoolStaffAssignment.user_id == User.id)
        .where(SchoolStaffAssignment.school_id == school.id, SchoolStaffAssignment.role == "career_counselor")
    )).all()

    return SchoolOut(
        id=school.id, name=school.name, city=school.city, state=school.state,
        tier=school.tier, tier_valid_until=school.tier_valid_until,
        school_code=school.school_code, branch=school.branch, address=school.address,
        contact_number=school.contact_number, email=school.email, website=school.website,
        grades_available=school.grades_available, board=school.board,
        partnership_date=school.partnership_date, mou_reference=school.mou_reference,
        edusphere_bdm=school.edusphere_bdm, monthly_visit_schedule=school.monthly_visit_schedule,
        vice_principal_name=school.vice_principal_name,
        student_count=student_count or 0, teacher_count=teacher_count or 0,
        principal_name=principal.full_name if principal else None,
        school_coordinator_name=coordinator.full_name if coordinator else None,
        career_counsellor_names=[c.full_name for c in counsellor_rows],
        created_at=school.created_at,
    )
```

Add the two new imports this needs at the top of `admin.py`: `func` alongside the existing
`sqlalchemy` import, and `SchoolCreate, SchoolOut, SchoolUpdate` alongside the existing
`from app.schemas import ...` line (check the existing import line first — add to it, don't
duplicate it).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py::test_school_out_computes_counts_and_role_derived_names -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/admin.py apps/api/tests/test_sch_003_school_onboarding.py
git commit -m "feat(enh-009): add _school_out() shared computed-profile helper"
```

---

### Task 5: `create_school()` — accept the new fields, generate `school_code`

**Files:**
- Modify: `apps/api/app/api/admin.py:1005-1053` (`create_school`)
- Test: `apps/api/tests/test_sch_003_school_onboarding.py`

**Interfaces:**
- Consumes: `SchoolCreate` (Task 3), `_school_out()` (Task 4), `unique_student_code()`
  (`core/identifiers.py:23`, unchanged).
- Produces: `POST /overseas-admin/schools` now accepts and stores all `SchoolCreate` fields, and
  every response includes `school_code`. Task 9 (frontend create panel) depends on this.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_sch_003_school_onboarding.py -- append at end of file

@pytest.mark.asyncio
async def test_create_school_generates_a_unique_school_code_and_stores_new_fields(client, db_session):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    suffix = uuid.uuid4().hex[:8]
    response = await client.post(
        "/api/v1/overseas-admin/schools",
        json={
            "name": f"Full Profile School {suffix}", "city": "Testville",
            "coordinator_full_name": "Test Coordinator",
            "coordinator_email": f"sch009-coord-{suffix}@example.local",
            "branch": "North Campus", "address": "1 Test Road", "board": "CBSE",
            "email": "school-contact@example.local", "grades_available": "1-10",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["school_code"] is not None
    assert len(data["school_code"]) == 8

    school = await db_session.get(School, data["id"])
    assert school.branch == "North Campus"
    assert school.address == "1 Test Road"
    assert school.board == "CBSE"
    assert school.email == "school-contact@example.local"


@pytest.mark.asyncio
async def test_create_school_rejects_an_invalid_board_value(client, db_session):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    response = await client.post(
        "/api/v1/overseas-admin/schools",
        json={
            "name": "X", "coordinator_full_name": "Y",
            "coordinator_email": f"y-{uuid.uuid4().hex[:8]}@example.local",
            "board": "Cambridge",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_school_rejects_a_smuggled_role_field(client, db_session):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    response = await client.post(
        "/api/v1/overseas-admin/schools",
        json={
            "name": "X", "coordinator_full_name": "Y",
            "coordinator_email": f"y-{uuid.uuid4().hex[:8]}@example.local",
            "role": "super_admin",
        },
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py -k "generates_a_unique_school_code or rejects_an_invalid_board or rejects_a_smuggled_role" -v`
Expected: FAIL — `school_code` is `None`/missing (column exists but nothing generates it yet), and
the invalid-board/smuggled-role requests currently succeed with `201` since `create_school` still
takes an untyped `payload: dict` with no such checks.

- [ ] **Step 3: Rewrite `create_school()`**

```python
# apps/api/app/api/admin.py -- replace create_school() (currently lines 1005-1053)

@agents_router.post("/schools", status_code=201, response_model=SchoolOut)
async def create_school(payload: SchoolCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    _reject_supplied_password(payload.model_dump(), user, "/api/v1/overseas-admin/schools", "coordinator_password")
    email = _valid_email(payload.coordinator_email)
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    if payload.tier and payload.tier not in {"bronze", "silver", "gold", "platinum"}:
        raise HTTPException(422, "tier must be one of bronze, silver, gold, platinum")
    school_code = await unique_student_code(db, School.school_code)
    school = School(
        name=payload.name, city=payload.city, state=payload.state,
        created_by_user_id=user.id, tier=payload.tier, school_code=school_code,
        branch=payload.branch, address=payload.address, contact_number=payload.contact_number,
        email=payload.email, website=payload.website, grades_available=payload.grades_available,
        board=payload.board, partnership_date=payload.partnership_date,
        mou_reference=payload.mou_reference, edusphere_bdm=payload.edusphere_bdm,
        monthly_visit_schedule=payload.monthly_visit_schedule,
        vice_principal_name=payload.vice_principal_name,
    )
    db.add(school)
    await db.flush()
    coordinator = User(
        email=email, password_hash=unusable_password_hash(),
        full_name=_fit(payload.coordinator_full_name, "Coordinator name", 160),
        role="school_coordinator", division="overseas", active=True, email_verified=False,
        profile={"school_id": str(school.id)},
    )
    db.add(coordinator)
    await _flush_unique_email(db)
    issued = await issue_welcome_token(db, user=coordinator, issued_by=user)
    db.add(UserRoleAssignment(user_id=coordinator.id, division="overseas", role="school_coordinator", is_active=True, assigned_by_user_id=user.id, approval_status="approved"))
    db.add(AuditLog(user_id=user.id, action="school.create", entity_type="school", entity_id=str(school.id), metadata_json={"name": school.name, "school_code": school_code}))
    db.add(AuditLog(user_id=user.id, action="school.coordinator_seed", entity_type="user", entity_id=str(coordinator.id), metadata_json={"school_id": str(school.id)}))
    await db.commit()
    delivery = await deliver_welcome_link(user=coordinator, issued=issued, issued_by=user)
    out = await _school_out(db, school)
    return {**out.model_dump(mode="json"), "coordinator_id": coordinator.id, "coordinator_email": coordinator.email, **delivery}
```

Note: the return is a plain dict (not the declared `response_model=SchoolOut`) because the existing
`coordinator_id`/`coordinator_email`/`**delivery` fields must keep flowing through for
`AdminSchoolCreatePanel.tsx` and its `welcomeLinkFeedback()` helper — FastAPI's `response_model`
only validates/filters when the return value is coerced through it; returning a dict that is a
superset of `SchoolOut`'s fields plus these extras passes through unchanged as long as
`response_model` is not set to something that would strip them. **Remove `response_model=SchoolOut`
from the decorator** — the extra fields matter and there's no shared `Out` type in this codebase
that carries them all.

**Accepted, minor compatibility change:** today's custom `HTTPException(422, "School name and
Coordinator name/email are required")` for a missing required field is replaced by FastAPI's
standard Pydantic validation-error body (a `detail` list, not a flat string) once `payload` becomes
a typed `SchoolCreate`. No existing test asserts on that exact message text (verified by search), so
this is safe against the current suite, but it is a genuine response-shape change for that one error
case — flagging it explicitly rather than letting it pass silently, per this task's "preserve API
compatibility" constraint. If this matters, the alternative is keeping a manual pre-check before
Pydantic validation runs (FastAPI doesn't support that with a typed body param without a custom
exception handler) — not pursued here as it would reintroduce the untyped-dict pattern this task
exists to remove.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py -v`
Expected: PASS (every test in the file, including the three new ones and all pre-existing ones —
`test_overseas_admin_creates_school_and_seed_coordinator_active_immediately`,
`test_non_admin_role_cannot_create_a_school`, etc. must still pass unchanged).

- [ ] **Step 5: Refactor**

Re-read the new `create_school()` body: confirm `_fit()` is still used for `coordinator_full_name`
(preserved), and that `name`/`city`/`state` no longer need `_fit()` calls at the call site because
`SchoolCreate`'s `Field(max_length=...)` already enforces the length cap declaratively — this is a
genuine behavior-preserving simplification (a too-long `name` still gets a 422, just from Pydantic
instead of `_fit()`), not a functional change. No other refactor needed.

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py -v`
Expected: PASS (unchanged)

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/admin.py apps/api/tests/test_sch_003_school_onboarding.py
git commit -m "feat(enh-009): create_school accepts full profile, generates school_code"
```

---

### Task 6: `list_schools()` — return `SchoolOut`

**Files:**
- Modify: `apps/api/app/api/admin.py:1056-1061` (`list_schools`)
- Test: `apps/api/tests/test_sch_003_school_onboarding.py`

**Interfaces:**
- Consumes: `_school_out()` (Task 4).
- Produces: `GET /overseas-admin/schools` returns a list of full `SchoolOut`-shaped dicts.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_sch_003_school_onboarding.py -- append at end of file

@pytest.mark.asyncio
async def test_list_schools_includes_school_code_and_profile_fields(client, db_session):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    await client.post(
        "/api/v1/overseas-admin/schools",
        json={"name": f"List Test {uuid.uuid4().hex[:8]}", "coordinator_full_name": "C",
              "coordinator_email": f"list-{uuid.uuid4().hex[:8]}@example.local", "branch": "East Wing"},
    )
    response = await client.get("/api/v1/overseas-admin/schools")
    assert response.status_code == 200
    row = response.json()[0]
    assert "school_code" in row
    assert "branch" in row
    assert "student_count" in row
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py::test_list_schools_includes_school_code_and_profile_fields -v`
Expected: FAIL — `KeyError`/`assert "school_code" in row` fails; today's `list_schools()` only
returns `id`, `name`, `city`, `state`, `tier`, `tier_valid_until`, `created_at`.

- [ ] **Step 3: Rewrite `list_schools()`**

```python
# apps/api/app/api/admin.py -- replace list_schools() (currently lines 1056-1061)

@agents_router.get("/schools")
async def list_schools(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    rows = (await db.scalars(select(School).order_by(School.created_at.desc()))).all()
    return [await _school_out(db, s) for s in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py -v`
Expected: PASS (all tests, including the pre-existing suite)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/admin.py apps/api/tests/test_sch_003_school_onboarding.py
git commit -m "feat(enh-009): list_schools returns full SchoolOut"
```

---

### Task 7: `update_school()` — widen the PATCH, add `school.profile_update` audit

**Files:**
- Modify: `apps/api/app/api/admin.py:1064-1083` (`update_school_tier` → `update_school`)
- Test: `apps/api/tests/test_sch_003_school_onboarding.py`

**Interfaces:**
- Consumes: `SchoolUpdate` (Task 3), `_school_out()` (Task 4).
- Produces: `PATCH /overseas-admin/schools/{id}` now accepts every profile field (partial update),
  keeps updating `tier`/`tier_valid_until` exactly as before, and writes a new
  `school.profile_update` audit row (field names only) whenever any non-tier field changes. Task 10
  (frontend edit panel) depends on this.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_sch_003_school_onboarding.py -- append at end of file

@pytest.mark.asyncio
async def test_patch_school_updates_profile_fields_and_logs_changed_field_names_only(client, db_session):
    result = await _create_school(client, db_session)
    await _login(client, result["admin"].email)

    response = await client.patch(
        f"/api/v1/overseas-admin/schools/{result['id']}",
        json={"branch": "South Campus", "board": "ICSE", "email": "new-contact@example.local"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["branch"] == "South Campus"
    assert response.json()["board"] == "ICSE"

    school = await db_session.get(School, result["id"])
    assert school.branch == "South Campus"
    assert school.email == "new-contact@example.local"

    from app.models import AuditLog
    log = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "school.profile_update", AuditLog.entity_id == str(school.id))
    )
    assert log is not None
    assert set(log.metadata_json["changed_fields"]) == {"branch", "board", "email"}
    # field names only -- the actual new values are never written into the audit trail
    assert "South Campus" not in str(log.metadata_json)


@pytest.mark.asyncio
async def test_patch_school_tier_only_still_works_unchanged(client, db_session):
    result = await _create_school(client, db_session)
    await _login(client, result["admin"].email)
    response = await client.patch(
        f"/api/v1/overseas-admin/schools/{result['id']}",
        json={"tier": "gold", "tier_valid_until": "2027-01-01"},
    )
    assert response.status_code == 200
    assert response.json()["tier"] == "gold"

    from app.models import AuditLog
    tier_log = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "school.tier_update", AuditLog.entity_id == result["id"])
    )
    assert tier_log is not None
    assert tier_log.metadata_json == {"tier": "gold"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py -k "profile_fields_and_logs or tier_only_still_works" -v`
Expected: FAIL — the PATCH body's `branch`/`board`/`email` are silently ignored by today's
`update_school_tier()` (it only reads `payload["tier"]`/`payload["tier_valid_until"]`), and no
`school.profile_update` audit action exists yet.

- [ ] **Step 3: Rewrite the endpoint**

```python
# apps/api/app/api/admin.py -- replace update_school_tier() (currently lines 1064-1083)

@agents_router.patch("/schools/{school_id}")
async def update_school(school_id: UUID, payload: SchoolUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """DEC-SCOPE-017 / ENH-009 (DEC-SCOPE-025) -- Overseas Admin updates a School's partnership
    tier and/or profile fields. `name`/`city`/`state`/`coordinator_*` stay out of scope for this
    endpoint -- they were never editable before and no acceptance criterion asks for that."""
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    school = await db.get(School, school_id)
    if not school:
        raise HTTPException(404, "School not found")
    fields = payload.model_dump(exclude_unset=True)
    if "tier" in fields:
        tier = fields["tier"]
        if tier and tier not in {"bronze", "silver", "gold", "platinum"}:
            raise HTTPException(422, "tier must be one of bronze, silver, gold, platinum")
        school.tier = tier
    if "tier_valid_until" in fields:
        school.tier_valid_until = fields["tier_valid_until"]
    if "tier" in fields or "tier_valid_until" in fields:
        db.add(AuditLog(user_id=user.id, action="school.tier_update", entity_type="school", entity_id=str(school.id), metadata_json={"tier": school.tier}))
    profile_fields = [k for k in fields if k not in {"tier", "tier_valid_until"}]
    for key in profile_fields:
        setattr(school, key, fields[key])
    if profile_fields:
        db.add(AuditLog(user_id=user.id, action="school.profile_update", entity_type="school", entity_id=str(school.id), metadata_json={"changed_fields": sorted(profile_fields)}))
    await db.commit()
    return await _school_out(db, school)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/admin.py apps/api/tests/test_sch_003_school_onboarding.py
git commit -m "feat(enh-009): widen school PATCH to full profile, add school.profile_update audit"
```

---

### Task 8: `GET /overseas-admin/schools/lookup?code=`

**Files:**
- Modify: `apps/api/app/api/admin.py` (new endpoint, placed near `lookup_school_student_by_code`,
  ~line 1240)
- Test: `apps/api/tests/test_sch_003_school_onboarding.py`

**Interfaces:**
- Consumes: `_school_out()` (Task 4).
- Produces: `GET /overseas-admin/schools/lookup?code=<school_code>` → `SchoolOut`-shaped JSON, 404 if
  not found, 403 for any role outside `{"overseas_admin","super_admin"}` (deliberately excluding
  `counselor`, unlike the sibling student-lookup endpoint — `DEC-SCOPE-025`). Task 10 (frontend edit
  panel) depends on this.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_sch_003_school_onboarding.py -- append at end of file

@pytest.mark.asyncio
async def test_lookup_school_by_code_returns_the_school(client, db_session):
    result = await _create_school(client, db_session)
    await _login(client, result["admin"].email)
    school = await db_session.get(School, result["id"])

    response = await client.get(f"/api/v1/overseas-admin/schools/lookup?code={school.school_code}")
    assert response.status_code == 200
    assert response.json()["id"] == str(school.id)


@pytest.mark.asyncio
async def test_lookup_school_by_code_404_when_not_found(client, db_session):
    admin = await _create_overseas_admin(db_session)
    await _login(client, admin.email)
    response = await client.get("/api/v1/overseas-admin/schools/lookup?code=ZZZZZZZZ")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_lookup_school_by_code_excludes_counselor(client, db_session):
    result = await _create_school(client, db_session)
    counselor = User(
        email=f"counselor-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
        full_name="Test Counselor", role="counselor", division="overseas", active=True,
    )
    db_session.add(counselor)
    await db_session.commit()
    await _login(client, counselor.email)
    school = await db_session.get(School, result["id"])
    response = await client.get(f"/api/v1/overseas-admin/schools/lookup?code={school.school_code}")
    assert response.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py -k "lookup_school_by_code" -v`
Expected: FAIL with 404 (route not found / method not allowed) — the endpoint doesn't exist yet.

- [ ] **Step 3: Write the endpoint**

```python
# apps/api/app/api/admin.py -- new endpoint, placed directly above lookup_school_student_by_code (~line 1240)

@agents_router.get("/schools/lookup")
async def lookup_school_by_code(code: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ENH-009 / DEC-SCOPE-025 -- resolves a School's business-facing `school_code` to its full
    profile, for the admin edit panel. Deliberately narrower than the analogous
    `school-students/lookup` endpoint: Counselor has a real reason to look up a School *student*
    (the School->Overseas bridge, DEC-SCOPE-018) but no legitimate reason to see or edit a
    School's own profile."""
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    school = await db.scalar(select(School).where(School.school_code == code.strip().upper()))
    if not school:
        raise HTTPException(404, "No school found with that School ID")
    return await _school_out(db, school)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_sch_003_school_onboarding.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/admin.py apps/api/tests/test_sch_003_school_onboarding.py
git commit -m "feat(enh-009): add GET /overseas-admin/schools/lookup?code="
```

---

### Task 9: Widen the existing read-only "Partner Schools" list (`services/portal.py`)

**Files:**
- Modify: `apps/api/app/services/portal.py:1360-1371`
- Test: new file `apps/api/tests/test_enh_009_school_portal_list.py`

**Interfaces:**
- Consumes: `School` model (Task 2).
- Produces: `GET /api/v1/portal/overseas/admin/schools` response columns/rows now include
  `school_code`, `branch`, `board`, `tier`.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_enh_009_school_portal_list.py
"""ENH-009 / DEC-SCOPE-025 -- the existing read-only Partner Schools portal list gains
school_code/branch/board/tier columns (the acceptance criterion that School ID must be displayed
everywhere a school is currently identified only by name)."""

import uuid

import pytest

from app.core.security import hash_password
from app.models import User

PASSWORD = "Sup3r-Secret-Pass!"


@pytest.mark.asyncio
async def test_overseas_admin_schools_portal_section_includes_school_code_and_branch(client, db_session):
    admin = User(
        email=f"portal-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
        full_name="Portal Admin", role="overseas_admin", division="overseas", active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    login = await client.post("/api/v1/auth/login", json={"email": admin.email, "password": PASSWORD, "division": "overseas"})
    assert login.status_code == 200

    await client.post(
        "/api/v1/overseas-admin/schools",
        json={"name": f"Portal School {uuid.uuid4().hex[:8]}", "coordinator_full_name": "C",
              "coordinator_email": f"portal-{uuid.uuid4().hex[:8]}@example.local", "branch": "West Wing"},
    )

    response = await client.get("/api/v1/portal/overseas/admin/schools")
    assert response.status_code == 200
    payload = response.json()
    column_keys = {c["key"] for c in payload["columns"]}
    assert {"school_code", "branch", "board", "tier"}.issubset(column_keys)
    assert any(row.get("branch") == "West Wing" for row in payload["rows"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_enh_009_school_portal_list.py -v`
Expected: FAIL — `column_keys` today is only `{"id","name","city","state","created_at"}`.

- [ ] **Step 3: Widen the payload**

```python
# apps/api/app/services/portal.py -- replace lines 1360-1371

        if section == "schools" and division == "overseas":
            # SCH-003 / ENH-009 (DEC-SCOPE-025): Overseas Admin's own partner-school list --
            # creation/edit handled by AdminSchoolCreatePanel.tsx/AdminSchoolEditPanel.tsx, same
            # "read via the generic portal section, write via a dedicated panel" split already
            # established for `universities` (RAID.md I-32).
            rows = (await db.scalars(select(School).order_by(School.created_at.desc()))).all()
            return _payload(
                "Partner Schools",
                "Every School partner record. Create a new one to seed its Coordinator account.",
                (("id", "reference"), ("school_code", "School ID"), ("name", "Name"), ("branch", "Branch"), ("city", "City"), ("state", "State"), ("board", "Board"), ("tier", "Tier"), ("created_at", "Created")),
                ({"id": s.id, "school_code": s.school_code or "-", "name": s.name, "branch": s.branch or "-", "city": s.city or "-", "state": s.state or "-", "board": s.board or "-", "tier": s.tier or "-", "created_at": s.created_at} for s in rows),
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_enh_009_school_portal_list.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/portal.py apps/api/tests/test_enh_009_school_portal_list.py
git commit -m "feat(enh-009): widen the Partner Schools portal list with School ID/Branch/Board/Tier"
```

---

### Task 10: Frontend — extend `AdminSchoolCreatePanel.tsx`

**Files:**
- Modify: `apps/web/components/AdminSchoolCreatePanel.tsx`
- Test: `apps/web/tests/components/AdminSchoolCreatePanel.test.tsx`

**Interfaces:**
- Consumes: `POST /overseas-admin/schools` (Task 5).
- Produces: the form submits all 12 new profile fields alongside the existing 6.

- [ ] **Step 1: Write the failing test**

```typescript
// apps/web/tests/components/AdminSchoolCreatePanel.test.tsx -- append inside the first describe block

  it("submits the new profile fields alongside the existing ones", async () => {
    const mock = stubFetch(json({ coordinator_email: "coord@example.local", email_status: "sent", school_code: "ABCD1234" }, 201));
    render(<AdminSchoolCreatePanel />);
    fireEvent.change(screen.getByLabelText("School name"), { target: { value: "Test School" } });
    fireEvent.change(screen.getByLabelText("Coordinator full name"), { target: { value: "Coord One" } });
    fireEvent.change(screen.getByLabelText("Coordinator email"), { target: { value: "coord@example.local" } });
    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "North Campus" } });
    fireEvent.change(screen.getByLabelText("Board"), { target: { value: "CBSE" } });
    fireEvent.click(screen.getByRole("button", { name: "Create school + seed Coordinator" }));
    await screen.findByRole("status");
    const body = JSON.parse(mock.mock.calls[0][1].body);
    expect(body.branch).toBe("North Campus");
    expect(body.board).toBe("CBSE");
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm test -- AdminSchoolCreatePanel`
Expected: FAIL — `screen.getByLabelText("Branch")` throws (no such field exists yet).

- [ ] **Step 3: Extend the form**

```tsx
// apps/web/components/AdminSchoolCreatePanel.tsx -- replace the body of submit()'s fetch call and the <form> contents

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    let response: Response;
    try {
      response = await fetch("/api/v1/overseas-admin/schools", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.get("name"),
          city: form.get("city") || undefined,
          state: form.get("state") || undefined,
          coordinator_full_name: form.get("coordinator_full_name"),
          coordinator_email: form.get("coordinator_email"),
          tier: form.get("tier") || undefined,
          branch: form.get("branch") || undefined,
          address: form.get("address") || undefined,
          contact_number: form.get("contact_number") || undefined,
          email: form.get("email") || undefined,
          website: form.get("website") || undefined,
          grades_available: form.get("grades_available") || undefined,
          board: form.get("board") || undefined,
          partnership_date: form.get("partnership_date") || undefined,
          mou_reference: form.get("mou_reference") || undefined,
          edusphere_bdm: form.get("edusphere_bdm") || undefined,
          monthly_visit_schedule: form.get("monthly_visit_schedule") || undefined,
          vice_principal_name: form.get("vice_principal_name") || undefined,
        }),
      });
    } catch {
      setBusy(false);
      setMessage({ text: "Network error -- it is not known whether the school was created. Check the schools list before trying again.", tone: "error" });
      return;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), tone: "error" });
      return;
    }
    setMessage(welcomeLinkFeedback(`School created (ID ${data.school_code}). Coordinator account ready for ${data.coordinator_email}.`, data));
    formElement.reset();
    router.refresh();
  }

  return (
    <div className="action-card">
      <h3>Create school</h3>
      <form className="form" onSubmit={submit}>
        <fieldset className="question">
          <legend>Identity</legend>
          <div className="field"><label htmlFor="school-name">School name</label><input id="school-name" name="name" required /></div>
          <div className="field"><label htmlFor="school-branch">Branch</label><input id="school-branch" name="branch" /></div>
          <div className="field"><label htmlFor="school-address">Address</label><input id="school-address" name="address" /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="school-city">City</label><input id="school-city" name="city" /></div>
            <div className="field"><label htmlFor="school-state">State</label><input id="school-state" name="state" /></div>
          </div>
          <div className="form-grid">
            <div className="field"><label htmlFor="school-contact-number">Contact number</label><input id="school-contact-number" name="contact_number" /></div>
            <div className="field"><label htmlFor="school-email">Email</label><input id="school-email" name="email" type="email" /></div>
          </div>
          <div className="field"><label htmlFor="school-website">Website</label><input id="school-website" name="website" /></div>
        </fieldset>
        <fieldset className="question">
          <legend>Academic</legend>
          <div className="form-grid">
            <div className="field"><label htmlFor="school-grades">Grades available</label><input id="school-grades" name="grades_available" /></div>
            <div className="field">
              <label htmlFor="school-board">Board</label>
              <select id="school-board" name="board" defaultValue="">
                <option value="">Not set</option>
                <option value="CBSE">CBSE</option>
                <option value="ICSE">ICSE</option>
                <option value="State">State</option>
                <option value="IB">IB</option>
                <option value="Other">Other</option>
              </select>
            </div>
          </div>
        </fieldset>
        <fieldset className="question">
          <legend>Partnership</legend>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="school-tier">Partnership tier</label>
              <select id="school-tier" name="tier" defaultValue="">
                <option value="">Not set yet</option>
                <option value="bronze">Bronze</option>
                <option value="silver">Silver</option>
                <option value="gold">Gold</option>
                <option value="platinum">Platinum</option>
              </select>
            </div>
            <div className="field"><label htmlFor="school-partnership-date">Partnership date</label><input id="school-partnership-date" name="partnership_date" type="date" /></div>
          </div>
          <div className="field"><label htmlFor="school-mou">Agreement / MoU reference</label><input id="school-mou" name="mou_reference" /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="school-bdm">Edusphere BDM</label><input id="school-bdm" name="edusphere_bdm" /></div>
            <div className="field"><label htmlFor="school-vp">Vice Principal</label><input id="school-vp" name="vice_principal_name" /></div>
          </div>
          <div className="field"><label htmlFor="school-visits">Monthly visit schedule</label><input id="school-visits" name="monthly_visit_schedule" /></div>
        </fieldset>
        <div className="field">
          <label htmlFor="school-coordinator-name">Coordinator full name</label>
          <input id="school-coordinator-name" name="coordinator_full_name" required />
        </div>
        <div className="field">
          <label htmlFor="school-coordinator-email">Coordinator email</label>
          <input id="school-coordinator-email" name="coordinator_email" type="email" required />
        </div>
        <button className="btn" disabled={busy}>
          {busy ? "Creating…" : "Create school + seed Coordinator"}
        </button>
      </form>
      {message && (
        <div className={toneClass[message.tone]} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm test -- AdminSchoolCreatePanel`
Expected: PASS (all tests in the file, including every pre-existing one — the field IDs for
`name`/`coordinator_full_name`/`coordinator_email` are unchanged, so `fillAndSubmit()` in the
existing tests still works).

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/AdminSchoolCreatePanel.tsx apps/web/tests/components/AdminSchoolCreatePanel.test.tsx
git commit -m "feat(enh-009): extend AdminSchoolCreatePanel with the full profile field set"
```

---

### Task 11: Frontend — new `AdminSchoolEditPanel.tsx`

**Files:**
- Create: `apps/web/components/AdminSchoolEditPanel.tsx`
- Test: new file `apps/web/tests/components/AdminSchoolEditPanel.test.tsx`

**Interfaces:**
- Consumes: `GET /overseas-admin/schools/lookup?code=` (Task 8), `PATCH
  /overseas-admin/schools/{id}` (Task 7), `detailMessage`/`isRequestBody` (`lib/apiErrors.ts`,
  existing), `Feedback`/`toneClass` (`lib/welcomeLink.ts`, existing).
- Produces: `AdminSchoolEditPanel` component. Task 12 wires it into `WorkflowPanel.tsx`.

- [ ] **Step 1: Write the failing test**

```typescript
// apps/web/tests/components/AdminSchoolEditPanel.test.tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminSchoolEditPanel from "@/components/AdminSchoolEditPanel";

const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status });

function stubFetch(responses: Response[]) {
  const mock = vi.fn();
  responses.forEach((r) => mock.mockResolvedValueOnce(r));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminSchoolEditPanel", () => {
  it("looks up a school by code, then patches the fields the admin changes", async () => {
    stubFetch([
      json({ id: "11111111-1111-1111-1111-111111111111", school_code: "ABCD1234", name: "Test School", branch: null, board: null }, 200),
      json({ id: "11111111-1111-1111-1111-111111111111", school_code: "ABCD1234", name: "Test School", branch: "North Campus", board: "CBSE" }, 200),
    ]);
    render(<AdminSchoolEditPanel />);
    fireEvent.change(screen.getByLabelText("School ID"), { target: { value: "ABCD1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    await screen.findByLabelText("Branch");

    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "North Campus" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText(/updated/i);
  });

  it("shows a not-found message for an unknown code", async () => {
    stubFetch([json({ detail: "No school found with that School ID" }, 404)]);
    render(<AdminSchoolEditPanel />);
    fireEvent.change(screen.getByLabelText("School ID"), { target: { value: "ZZZZZZZZ" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    const outcome = await screen.findByText("No school found with that School ID");
    expect(outcome).toHaveClass("form-error");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm test -- AdminSchoolEditPanel`
Expected: FAIL with a module-not-found error — `AdminSchoolEditPanel.tsx` doesn't exist yet.

- [ ] **Step 3: Write the component**

```tsx
// apps/web/components/AdminSchoolEditPanel.tsx
"use client";

import { FormEvent, useState } from "react";

import { detailMessage, isRequestBody } from "@/lib/apiErrors";
import { type Feedback, toneClass } from "@/lib/welcomeLink";

type School = {
  id: string; school_code: string | null; name: string;
  branch: string | null; address: string | null; contact_number: string | null;
  email: string | null; website: string | null; grades_available: string | null;
  board: string | null; partnership_date: string | null; mou_reference: string | null;
  edusphere_bdm: string | null; monthly_visit_schedule: string | null; vice_principal_name: string | null;
};

// ENH-009 / DEC-SCOPE-025: lookup-by-code then PATCH, mirroring the existing
// GET .../school-students/lookup?code= convention (admin.py:1240) -- the codebase has no
// clickable-table-row-to-edit pattern anywhere, and the established convention is "read via the
// generic portal section, write via a dedicated panel" (same split as AdminSchoolCreatePanel.tsx).
export default function AdminSchoolEditPanel() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Feedback | null>(null);
  const [school, setSchool] = useState<School | null>(null);

  async function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = new FormData(event.currentTarget).get("code");
    setBusy(true);
    setMessage(null);
    setSchool(null);
    let response: Response;
    try {
      response = await fetch(`/api/v1/overseas-admin/schools/lookup?code=${encodeURIComponent(String(code))}`);
    } catch {
      setBusy(false);
      setMessage({ text: "Network error -- check your connection and try again.", tone: "error" });
      return;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail, "Unable to look up that school."), tone: "error" });
      return;
    }
    setSchool(data as School);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!school) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setMessage(null);
    let response: Response;
    try {
      response = await fetch(`/api/v1/overseas-admin/schools/${school.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          branch: form.get("branch") || undefined,
          address: form.get("address") || undefined,
          contact_number: form.get("contact_number") || undefined,
          email: form.get("email") || undefined,
          website: form.get("website") || undefined,
          grades_available: form.get("grades_available") || undefined,
          board: form.get("board") || undefined,
          partnership_date: form.get("partnership_date") || undefined,
          mou_reference: form.get("mou_reference") || undefined,
          edusphere_bdm: form.get("edusphere_bdm") || undefined,
          monthly_visit_schedule: form.get("monthly_visit_schedule") || undefined,
          vice_principal_name: form.get("vice_principal_name") || undefined,
        }),
      });
    } catch {
      setBusy(false);
      setMessage({ text: "Network error -- it is not known whether the changes saved. Look the school up again before retrying.", tone: "error" });
      return;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), tone: "error" });
      return;
    }
    if (!isRequestBody(data)) {
      setMessage({ text: "The save could not be confirmed. Look the school up again before changing anything else.", tone: "error" });
      return;
    }
    setSchool(data as School);
    setMessage({ text: "School profile updated.", tone: "success" });
  }

  return (
    <div className="action-card">
      <h3>Edit school profile</h3>
      <form className="form" onSubmit={lookup}>
        <div className="field">
          <label htmlFor="school-lookup-code">School ID</label>
          <input id="school-lookup-code" name="code" required />
        </div>
        <button className="btn" disabled={busy}>{busy ? "Looking up…" : "Look up"}</button>
      </form>
      {school && (
        <form className="form" onSubmit={save} style={{ marginTop: 16 }}>
          <p className="muted">{school.name} ({school.school_code})</p>
          <div className="field"><label htmlFor="edit-branch">Branch</label><input id="edit-branch" name="branch" defaultValue={school.branch ?? ""} /></div>
          <div className="field"><label htmlFor="edit-address">Address</label><input id="edit-address" name="address" defaultValue={school.address ?? ""} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="edit-contact-number">Contact number</label><input id="edit-contact-number" name="contact_number" defaultValue={school.contact_number ?? ""} /></div>
            <div className="field"><label htmlFor="edit-email">Email</label><input id="edit-email" name="email" type="email" defaultValue={school.email ?? ""} /></div>
          </div>
          <div className="field"><label htmlFor="edit-website">Website</label><input id="edit-website" name="website" defaultValue={school.website ?? ""} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="edit-grades">Grades available</label><input id="edit-grades" name="grades_available" defaultValue={school.grades_available ?? ""} /></div>
            <div className="field">
              <label htmlFor="edit-board">Board</label>
              <select id="edit-board" name="board" defaultValue={school.board ?? ""}>
                <option value="">Not set</option>
                <option value="CBSE">CBSE</option>
                <option value="ICSE">ICSE</option>
                <option value="State">State</option>
                <option value="IB">IB</option>
                <option value="Other">Other</option>
              </select>
            </div>
          </div>
          <div className="field"><label htmlFor="edit-partnership-date">Partnership date</label><input id="edit-partnership-date" name="partnership_date" type="date" defaultValue={school.partnership_date ?? ""} /></div>
          <div className="field"><label htmlFor="edit-mou">Agreement / MoU reference</label><input id="edit-mou" name="mou_reference" defaultValue={school.mou_reference ?? ""} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="edit-bdm">Edusphere BDM</label><input id="edit-bdm" name="edusphere_bdm" defaultValue={school.edusphere_bdm ?? ""} /></div>
            <div className="field"><label htmlFor="edit-vp">Vice Principal</label><input id="edit-vp" name="vice_principal_name" defaultValue={school.vice_principal_name ?? ""} /></div>
          </div>
          <div className="field"><label htmlFor="edit-visits">Monthly visit schedule</label><input id="edit-visits" name="monthly_visit_schedule" defaultValue={school.monthly_visit_schedule ?? ""} /></div>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button>
        </form>
      )}
      {message && (
        <div className={toneClass[message.tone]} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm test -- AdminSchoolEditPanel`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/AdminSchoolEditPanel.tsx apps/web/tests/components/AdminSchoolEditPanel.test.tsx
git commit -m "feat(enh-009): add AdminSchoolEditPanel (lookup-by-code, then PATCH)"
```

---

### Task 12: Wire `AdminSchoolEditPanel` into `WorkflowPanel.tsx`

**Files:**
- Modify: `apps/web/components/WorkflowPanel.tsx:455, 462`

**Interfaces:**
- Consumes: `AdminSchoolEditPanel` (Task 11).
- Produces: the panel renders on the `section === "schools"` workspace for
  `overseas_admin`/`super_admin`, alongside the existing create panel.

This task has no new automated test of its own — `WorkflowPanel`'s rendering logic is exercised by
the Playwright spec in Task 13. Verify manually via the component test suite staying green (no
existing `WorkflowPanel` test regresses) plus the E2E spec in Task 13.

- [ ] **Step 1: Add the import and render call**

```tsx
// apps/web/components/WorkflowPanel.tsx -- add the import near the other Admin*Panel imports (~line 40, alongside `import AdminSchoolCreatePanel from "./AdminSchoolCreatePanel";`)
import AdminSchoolEditPanel from "./AdminSchoolEditPanel";
```

```tsx
// apps/web/components/WorkflowPanel.tsx -- in the JSX return (line 462), immediately after
// `{showSchoolCreate && <AdminSchoolCreatePanel/>}`
{showSchoolCreate && <AdminSchoolEditPanel/>}
```

(Reuses the existing `showSchoolCreate` flag — the edit panel appears exactly where the create
panel does, for the same two roles, no new gating variable needed.)

- [ ] **Step 2: Run the full frontend unit suite to confirm no regression**

Run: `cd apps/web && npm test`
Expected: PASS (every existing test, plus Tasks 10/11's new tests)

- [ ] **Step 3: Commit**

```bash
git add apps/web/components/WorkflowPanel.tsx
git commit -m "feat(enh-009): render AdminSchoolEditPanel in the schools workspace"
```

---

### Task 13: Playwright — extend `sch-003-school-onboarding.spec.ts`

**Files:**
- Modify: `apps/web/tests/e2e/sch-003-school-onboarding.spec.ts`

**Interfaces:**
- Consumes: the full stack (Tasks 1-12) running end-to-end.

**Existing conventions confirmed by reading the file:** `page.goto("/overseas/login")` →
`#login-email`/`#login-password` → `"Sign in securely"` → `waitForURL("**/overseas/admin/dashboard")`
→ `page.goto("/overseas/admin/schools")` → fill `#school-name` etc. (the same field IDs Task 10
already uses) → `createAndActivateFromUi(page, 'button:has-text("...")', "/overseas-admin/schools")`
→ assert `page.getByText(/School created\./)` and `page.getByRole("cell", { name: ... })` for the
Partner Schools list row on the same page.

- [ ] **Step 1: Write the new spec cases (RED)**

```typescript
// apps/web/tests/e2e/sch-003-school-onboarding.spec.ts -- append two new tests at the end of the file

test("School ID is generated and shown on both the create panel and the Partner Schools list (ENH-009)", async ({ page }) => {
  const unique = Date.now();
  const coordinatorEmail = `sch009-e2e-coord-${unique}@example.local`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E Profile School ${unique}`);
  await page.fill("#school-branch", "North Campus");
  await page.selectOption("#school-board", "CBSE");
  await page.fill("#school-coordinator-name", "E2E Profile Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");

  const successMessage = page.getByText(/School created \(ID [A-Z0-9]{8}\)\./);
  await expect(successMessage).toBeVisible();
  const schoolIdText = await successMessage.textContent();
  const schoolId = schoolIdText!.match(/ID ([A-Z0-9]{8})/)![1];

  await expect(page.getByRole("cell", { name: `E2E Profile School ${unique}` })).toBeVisible();
  await expect(page.getByRole("cell", { name: schoolId })).toBeVisible();
  await expect(page.getByRole("cell", { name: "North Campus" })).toBeVisible();
});

test("admin can look up a school by its School ID and edit its profile (ENH-009)", async ({ page }) => {
  const unique = Date.now();
  const coordinatorEmail = `sch009-e2e-edit-${unique}@example.local`;

  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E Edit School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E Edit Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  const successMessage = page.getByText(/School created \(ID [A-Z0-9]{8}\)\./);
  const schoolIdText = await successMessage.textContent();
  const schoolId = schoolIdText!.match(/ID ([A-Z0-9]{8})/)![1];

  await page.fill("#school-lookup-code", schoolId);
  await page.click('button:has-text("Look up")');
  await expect(page.getByLabelText("Branch")).toBeVisible();
  await page.fill("#edit-branch", "South Campus");
  await page.click('button:has-text("Save changes")');
  await expect(page.getByText("School profile updated.")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("cell", { name: "South Campus" })).toBeVisible();
});
```

Run: `cd apps/web && npm run test:e2e -- sch-003-school-onboarding`
Expected: FAIL (new cases fail — the assertions reference the School ID column, which is real by
this point since Task 9 shipped it, but the E2E test itself doesn't exist yet before this step).

- [ ] **Step 2: Confirm GREEN**

Run: `cd apps/web && npm run test:e2e -- sch-003-school-onboarding`
Expected: PASS — by this point in the plan every layer (migration, API, both panels) is already
implemented and unit-tested; this is confirmation at the browser/E2E layer, not new implementation.

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/sch-003-school-onboarding.spec.ts
git commit -m "test(enh-009): extend Playwright coverage for School Profile fields"
```

---

## After this plan

Per the user's explicit instruction: **implementation is not completion.** Two steps remain outside
this plan's scope, to be run after all 13 tasks are green:

1. **Browser validation** — manually drive the app (not just Playwright) through the create and
   edit flows as `overseas_admin`, confirming visual hierarchy, loading/error states, and mobile
   layout (320px/768px/1024px/1440px) actually look right, not just that assertions pass.
2. **Independent Codex review** — a fresh review pass over the full diff, separate from this
   session's own work, before this branch is considered mergeable.

Do not report ENH-009 as complete until both of these have actually happened.
