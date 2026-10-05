# ENH-013a Student 360° View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One per-role, 16-tab Student 360° view (`GET /school/students/{id}/360-view`) plus a counselor-set `career_goal`, with no new data exposure for any role.

**Architecture:** A new `app/api/student_360.py` builds the tabs from behavior-preserving extractions of the existing `/overview`, `/portfolio` and `/grade-history` read code, gated by the ENH-012 7-role loader (moved into `schools.py`). The Next.js frontend adds thin per-role `/360` routes: server-rendered panels passed as children into a small client ARIA-tabs component.

**Tech Stack:** FastAPI + SQLAlchemy async + Pydantic v2 + Alembic + Postgres; Next.js 15 / React 19; pytest (asyncio, strict), vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md`

## Global Constraints

- No new dependencies (backend or frontend).
- `/overview`, `/portfolio`, `/students/{id}`, `/grade-history` responses stay byte-identical; their existing tests are not edited.
- `_load_readable_student`, `_student_in_portfolio`, `_scoped_students_query`, `_student_out`, `get_current_user` are not modified.
- Results: published only, for every role.
- `career_goal`: ≤120 chars, single line, no control/bidi chars; empty → null. Only `career_counselor` (own portfolio) may write.
- Tab keys, in order: `overview, personal_details, academic_records, attendance, examination_results, career_guidance, psychometric_assessment, skills, foreign_languages, english_testing, activities, certificates, documents, teacher_remarks, parent_communication, edusphere_programs`.
- Tab envelope: `{status: "has_data"|"empty"|"restricted", count: int|null, not_tracked: [str], data: {...}}`.
- Logs carry IDs and role only, never free text or payloads.
- Client components never import `@/lib/api`, `@/components/SchoolChildOverview`, `@/components/SchoolGradeHistory`, `next/headers` (guarded by `tests/lib/clientBoundary.test.ts`).
- Backend tests need the user-run docker Postgres; never start/stop docker yourself. Run pytest from `apps/api`: `python -m pytest tests/<file> -q`.
- Frontend tests: from `apps/web`: `npx vitest run <path>`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

## File map

Backend
- Modify `apps/api/app/api/schools.py`: add `_load_student_for_reader`; extract `_overview_payload`, `_grade_history_rows`.
- Modify `apps/api/app/api/portfolio.py`: use the moved loader; extract `portfolio_payload`; drop `PORTFOLIO_SCOPED_ROLES`.
- Create `apps/api/app/api/student_360.py`: GET 360-view + PATCH career-goal.
- Modify `apps/api/app/schemas.py`: `CareerGoalUpdate`, `CareerGoalOut`, `Tab360`, `Student360Header`, `Student360Out`.
- Modify `apps/api/app/models.py`: `SchoolStudent.career_goal`.
- Create `apps/api/alembic/versions/0039_student_career_goal.py`.
- Modify `apps/api/app/main.py`: register router.
- Tests: `apps/api/tests/test_enh_013_refactor.py`, `test_enh_013_360_view.py`, `test_enh_013_career_goal.py`, `test_enh_013_migration.py`.

Frontend
- Create `apps/web/lib/student360.ts` (types, `loadStudent360`, `student360Href`, `safeHref`, `TAB_LABELS`).
- Create `apps/web/components/Student360Tabs.tsx` (client), `Student360Panels.tsx` (server), `Student360View.tsx` (server), `CareerGoalForm.tsx` (client), `Student360Directory.tsx` (server).
- Create 7 routes `.../[id]/360/page.tsx` + `loading.tsx`.
- Modify `SchoolChildOverview.tsx` (export `SkillsCard`), `SchoolStudentDetailPanel.tsx` (+ link + `role` prop), 3 `students/[id]` pages + parent child page (pass role / link), 3 service dashboards (+ directory), `app/globals.css` (tab styles).
- Tests: `tests/lib/student360.test.ts`, `tests/components/Student360Tabs.test.tsx`, `Student360Panels.test.tsx`, `CareerGoalForm.test.tsx`, `tests/e2e/enh-013-student-360.spec.ts`.

Docs: `docs/quality/RTM.md`, screen catalogue, `docs/delivery/RAID.md`, `docs/delivery/ENHANCEMENT_BACKLOG.md`.

---

### Task 1: Consolidate the 7-role reader loader

**Files:**
- Modify: `apps/api/app/api/schools.py` (after `_readable_students`, ~line 1610)
- Modify: `apps/api/app/api/portfolio.py:17,45-56,95,140,166,196,211`
- Test: `apps/api/tests/test_enh_013_refactor.py`

**Interfaces:**
- Produces: `schools._load_student_for_reader(db: AsyncSession, user: User, student_id: UUID) -> SchoolStudent`.

- [ ] **Step 1: Write the failing test**

```python
"""ENH-013 -- behavior-preserving refactors (spec §7)."""
import uuid

import pytest
from fastapi import HTTPException

from tests.enh005_helpers import mk_school, mk_staff, mk_user


@pytest.mark.asyncio
async def test_reader_loader_allows_the_seven_roles_and_keeps_existing_denials(db_session):
    from app.api.schools import _load_student_for_reader

    a = await mk_school(db_session, label="E13-LoaderA")
    b = await mk_school(db_session, label="E13-LoaderB", admin=a["admin"])
    kid = a["students"][0]
    for who in (a["coordinator"], a["principal"], a["teacher"], a["parent"]):
        assert (await _load_student_for_reader(db_session, who, kid.id)).id == kid.id
    for role in ("academic_team", "career_counselor", "psychometric_team"):
        member = await mk_staff(db_session, a["school"], a["admin"], role=role)
        assert (await _load_student_for_reader(db_session, member, kid.id)).id == kid.id
        outsider = await mk_staff(db_session, b["school"], a["admin"], role=role)
        with pytest.raises(HTTPException) as exc:
            await _load_student_for_reader(db_session, outsider, kid.id)
        assert (exc.value.status_code, exc.value.detail) == (403, "This student is at a school outside your own portfolio")
    with pytest.raises(HTTPException) as exc:
        await _load_student_for_reader(db_session, b["coordinator"], kid.id)
    assert (exc.value.status_code, exc.value.detail) == (403, "This student is at a different institution")
    admin = await mk_user(db_session, role="overseas_admin", name="Admin")
    with pytest.raises(HTTPException) as exc:
        await _load_student_for_reader(db_session, admin, kid.id)
    assert (exc.value.status_code, exc.value.detail) == (403, "School role required")
    with pytest.raises(HTTPException) as exc:
        await _load_student_for_reader(db_session, a["coordinator"], uuid.uuid4())
    assert exc.value.status_code == 404


def test_portfolio_module_no_longer_defines_its_own_role_set():
    from app.api import portfolio
    assert not hasattr(portfolio, "PORTFOLIO_SCOPED_ROLES")
    assert not hasattr(portfolio, "_load_portfolio_student")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_enh_013_refactor.py -q`
Expected: FAIL — `ImportError: cannot import name '_load_student_for_reader'`.

- [ ] **Step 3: Implement**

In `schools.py`, directly after `_readable_students`:

```python
async def _load_student_for_reader(db: AsyncSession, user: User, student_id: UUID) -> SchoolStudent:
    """Read-scope loader for every role that may read one student's record (ENH-012 portfolio, ENH-013 360-view): the 3
    portfolio-scoped service roles go through `_student_in_portfolio`, everyone else through `_load_readable_student` (which
    403s any non-School role). Moved here from portfolio.py unchanged so both features share one loader (ENH-013 spec §4)."""
    if user.role in SERVICE_DELIVERY_ROLES:
        return await _student_in_portfolio(db, user, student_id)
    return await _load_readable_student(db, user, student_id)
```

In `portfolio.py`: change the import to `from app.api.schools import _load_student_for_reader`; delete `PORTFOLIO_SCOPED_ROLES` and `_load_portfolio_student`; replace every `_load_portfolio_student(` with `_load_student_for_reader(`; update `_can_edit_portfolio`'s docstring reference.

- [ ] **Step 4: Run to verify it passes, plus the ENH-012 suite unmodified**

Run: `python -m pytest tests/test_enh_013_refactor.py tests/test_enh_012_digital_portfolio.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit** — `refactor(enh-013): share the 7-role reader loader between portfolio and 360-view`

---

### Task 2: Extract the overview, grade-history and portfolio payload builders

**Files:**
- Modify: `apps/api/app/api/schools.py:959-1041` (`student_overview`), `:1124-1152` (`student_grade_history`)
- Modify: `apps/api/app/api/portfolio.py:91-135` (`get_portfolio`)
- Test: `apps/api/tests/test_enh_013_refactor.py` (append)

**Interfaces:**
- Produces: `schools._overview_payload(db, student) -> dict` (exact old `/overview` body); `schools._grade_history_rows(db, student) -> list[dict]` (the old `history` list); `portfolio.portfolio_payload(db, user, student) -> dict` (exact old `/portfolio` body).

- [ ] **Step 1: Write the failing test (append)**

```python
@pytest.mark.asyncio
async def test_payload_helpers_return_exactly_what_the_routes_return(client, db_session):
    from fastapi.encoders import jsonable_encoder

    from app.api.portfolio import portfolio_payload
    from app.api.schools import _grade_history_rows, _overview_payload
    from tests.enh005_helpers import login

    a = await mk_school(db_session, label="E13-Payload")
    kid = a["students"][0]
    await login(client, a["coordinator"].email)
    base = f"/api/v1/school/students/{kid.id}"
    overview = (await client.get(f"{base}/overview")).json()
    portfolio = (await client.get(f"{base}/portfolio")).json()
    history = (await client.get(f"{base}/grade-history")).json()["history"]
    assert jsonable_encoder(await _overview_payload(db_session, kid)) == overview
    assert jsonable_encoder(await portfolio_payload(db_session, a["coordinator"], kid)) == portfolio
    assert jsonable_encoder(await _grade_history_rows(db_session, kid)) == history
```

- [ ] **Step 2: Run** — `python -m pytest tests/test_enh_013_refactor.py -q` → FAIL, ImportError `_overview_payload`.

- [ ] **Step 3: Implement (pure moves)**

`schools.py`: rename the body of `student_overview` (everything after the loader line) into:

```python
async def _overview_payload(db: AsyncSession, student: SchoolStudent) -> dict:
    """SCH-007's overview for an already scope-checked student. Extracted unchanged so ENH-013's 360-view can reuse it."""
    school = await db.get(School, student.school_id)
    ...  # the existing body, unchanged, ending in the existing `return {...}`


@router.get("/students/{student_id}/overview")
async def student_overview(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """<existing docstring kept verbatim>"""
    student = await _load_readable_student(db, user, student_id)
    return await _overview_payload(db, student)
```

Same for grade history:

```python
async def _grade_history_rows(db: AsyncSession, student: SchoolStudent) -> list[dict]:
    """ENH-004's history list for an already scope-checked student, newest first (extracted for ENH-013)."""
    from_year = aliased(AcademicYear)
    to_year = aliased(AcademicYear)
    rows = (...existing query...).all()
    return [ ...existing list comprehension... ]


@router.get("/students/{student_id}/grade-history", response_model=GradeHistoryResponse)
async def student_grade_history(...):
    """<existing docstring>"""
    student = await _load_readable_student(db, user, student_id)
    return {"student": {"id": student.id, "full_name": student.full_name}, "history": await _grade_history_rows(db, student)}
```

`portfolio.py`:

```python
async def portfolio_payload(db: AsyncSession, user: User, student: SchoolStudent) -> dict:
    """The ENH-012 portfolio for an already scope-checked student. Extracted unchanged so ENH-013 can reuse it."""
    can_edit = _can_edit_portfolio(user, student)
    ...  # existing body, unchanged


@router.get("/students/{student_id}/portfolio")
async def get_portfolio(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """<existing docstring>"""
    student = await _load_student_for_reader(db, user, student_id)
    return await portfolio_payload(db, user, student)
```

- [ ] **Step 4: Run new test + every suite pinning these routes (unmodified)**

Run: `python -m pytest tests/test_enh_013_refactor.py tests/test_sch_007_parent_portal.py tests/test_sch_009_test_prep_language.py tests/test_sch_010_overseas_bridge.py tests/test_enh_005_scope.py tests/test_enh_011_read_surfaces.py tests/test_enh_012_digital_portfolio.py tests/test_enh_004_student_promotion.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit** — `refactor(enh-013): extract overview, grade-history and portfolio payload builders`

---

### Task 3: `career_goal` column + migration 0039

**Files:**
- Modify: `apps/api/app/models.py` (`SchoolStudent`, after `grade_level`)
- Create: `apps/api/alembic/versions/0039_student_career_goal.py`
- Test: `apps/api/tests/test_enh_013_migration.py`

- [ ] **Step 1: Write the failing test**

```python
"""ENH-013 -- school_students.career_goal (spec §5): additive, nullable, no backfill."""
import pytest
from sqlalchemy import text

from tests.enh005_helpers import mk_school


@pytest.mark.asyncio
async def test_career_goal_column_is_nullable_varchar_120(db_session):
    row = (await db_session.execute(text(
        "SELECT data_type, character_maximum_length, is_nullable, column_default FROM information_schema.columns "
        "WHERE table_name = 'school_students' AND column_name = 'career_goal'"
    ))).one_or_none()
    assert row is not None, "migration 0039 not applied"
    assert tuple(row) == ("character varying", 120, "YES", None)


@pytest.mark.asyncio
async def test_new_and_existing_students_default_to_no_career_goal(db_session):
    ctx = await mk_school(db_session, label="E13-Mig")
    assert ctx["students"][0].career_goal is None
```

- [ ] **Step 2: Run** — FAIL (`row is None` / `AttributeError: career_goal`).

- [ ] **Step 3: Implement**

`models.py`, in `SchoolStudent` after `grade_level`:

```python
    # ENH-013: the counsellor-set Career Passport goal (spec §5). Free text, single line, nullable -- no backfill.
    career_goal: Mapped[str | None] = mapped_column(String(120), nullable=True)
```

`0039_student_career_goal.py`:

```python
"""ENH-013 -- school_students.career_goal.

Revision ID: 0039_student_career_goal
Revises: 0038_portfolio

docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §5. Add-column only: nullable, no default, no
backfill, so no existing row is read or rewritten (a metadata-only change on Postgres). `downgrade()` drops the column.
"""

import sqlalchemy as sa

from alembic import op

revision = "0039_student_career_goal"
down_revision = "0038_portfolio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("school_students", sa.Column("career_goal", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("school_students", "career_goal")
```

Apply: run `alembic upgrade head` the same way prior features did (inside the running api container or locally against the dev DB). Then verify reversibility once: `alembic downgrade -1`, `alembic upgrade head`, and `alembic heads` shows a single head `0039_student_career_goal`.

- [ ] **Step 4: Run** — `python -m pytest tests/test_enh_013_migration.py -q` → PASS.

- [ ] **Step 5: Commit** — `feat(enh-013): add nullable school_students.career_goal (migration 0039)`

---

### Task 4: Schemas

**Files:**
- Modify: `apps/api/app/schemas.py` (append after the ENH-012 portfolio schemas)
- Test: `apps/api/tests/test_enh_013_career_goal.py`

**Interfaces:**
- Produces: `CareerGoalUpdate(career_goal: str | None)`, `CareerGoalOut(school_student_id: UUID, career_goal: str | None, updated_at: datetime)`, `Tab360(status, count, not_tracked, data)`, `Student360Header`, `Student360Out(student, career_goal, can_edit_career_goal, tabs: dict[str, Tab360])`, `TAB_360_KEYS: tuple[str, ...]`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-013 -- PATCH /school/students/{id}/career-goal (spec §6.2)."""
import pytest
from pydantic import ValidationError

from app.schemas import CareerGoalUpdate


@pytest.mark.parametrize("raw, expected", [("  Technology  ", "Technology"), ("", None), ("   ", None), (None, None), ("a" * 120, "a" * 120)])
def test_career_goal_update_cleans_and_clears(raw, expected):
    assert CareerGoalUpdate(career_goal=raw).career_goal == expected


@pytest.mark.parametrize("payload", [{"career_goal": "a" * 121}, {"career_goal": "Line\nbreak"}, {"career_goal": "Bad\x00byte"}, {"career_goal": "Rev‮ersed"}, {}, {"career_goal": "x", "school_id": "y"}])
def test_career_goal_update_rejects(payload):
    with pytest.raises(ValidationError):
        CareerGoalUpdate(**payload)


def test_tab_keys_are_the_sixteen_in_display_order():
    from app.schemas import TAB_360_KEYS
    assert TAB_360_KEYS == ("overview", "personal_details", "academic_records", "attendance", "examination_results", "career_guidance", "psychometric_assessment", "skills", "foreign_languages", "english_testing", "activities", "certificates", "documents", "teacher_remarks", "parent_communication", "edusphere_programs")
```

- [ ] **Step 2: Run** — FAIL, ImportError.

- [ ] **Step 3: Implement (append to `schemas.py`)**

```python
# --- ENH-013: Student 360° view (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §6) ---

CAREER_GOAL_MAX = 120
TAB_360_KEYS: tuple[str, ...] = (
    "overview", "personal_details", "academic_records", "attendance", "examination_results", "career_guidance",
    "psychometric_assessment", "skills", "foreign_languages", "english_testing", "activities", "certificates",
    "documents", "teacher_remarks", "parent_communication", "edusphere_programs",
)


class CareerGoalUpdate(BaseModel):
    # `extra="forbid"`: this PATCH writes one column; a client-supplied school_id/assigned_teacher is a loud 422 (spec §9).
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}
    career_goal: str | None = Field(...)

    @field_validator("career_goal")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        # clean_free_text: blank -> None, length cap, no bidi/NUL; _no_control_characters: single line (no \n/\t).
        return _no_control_characters(clean_free_text(value, CAREER_GOAL_MAX))


class CareerGoalOut(BaseModel):
    school_student_id: UUID
    career_goal: str | None
    updated_at: datetime


class Tab360(BaseModel):
    status: Literal["has_data", "empty", "restricted"]
    count: int | None
    not_tracked: list[str]
    data: dict


class Student360Header(BaseModel):
    id: UUID
    full_name: str
    school_name: str | None
    student_code: str | None
    grade_or_class: str | None
    date_of_birth: date | None
    assigned_teacher_name: str | None


class Student360Out(BaseModel):
    student: Student360Header
    career_goal: str | None
    can_edit_career_goal: bool
    tabs: dict[str, Tab360]
```

(If `_no_control_characters` is defined below this point in the file, place this block after it.)

- [ ] **Step 4: Run** — `python -m pytest tests/test_enh_013_career_goal.py -q` → PASS.

- [ ] **Step 5: Commit** — `feat(enh-013): 360-view and career-goal schemas`

---

### Task 5: `GET /360-view` — authorization, envelope, school-role tabs

**Files:**
- Create: `apps/api/app/api/student_360.py`
- Modify: `apps/api/app/main.py:9,33` (import + router tuple)
- Test: `apps/api/tests/test_enh_013_360_view.py`

**Interfaces:**
- Consumes: `_load_student_for_reader`, `_overview_payload`, `_grade_history_rows`, `portfolio_payload`, `SCHOOL_ROLES`, `Student360Out`, `TAB_360_KEYS`.
- Produces: `student_360.router`; `student_360.build_360(db, user, student) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-013 -- GET /school/students/{id}/360-view (spec §6.1, §6.3, AC-01..AC-06, AC-09)."""
import logging
import uuid

import pytest
from sqlalchemy import event

from app.core.database import engine
from app.models import PortfolioEntry, SchoolActivity, SchoolActivityAttendance, SchoolCareerRecord, SchoolLanguageRecord, SchoolPsychometricRecord, SchoolTestPrepRecord
from app.schemas import TAB_360_KEYS
from tests.enh005_helpers import login, mk_result, mk_school, mk_staff, mk_user

URL = "/api/v1/school/students/{sid}/360-view"


async def _fill(db, ctx, n: int = 1):
    """n rows in every source for ctx's first student."""
    from datetime import UTC, datetime
    kid, coord = ctx["students"][0], ctx["coordinator"]
    staff = await mk_staff(db, ctx["school"], ctx["admin"], role="academic_team")
    for i in range(n):
        db.add(SchoolCareerRecord(school_student_id=kid.id, career_counselor_user_id=coord.id, record_type="guidance_session", notes=f"note {i}"))
        db.add(SchoolPsychometricRecord(school_student_id=kid.id, psychometric_team_user_id=coord.id, assessment_type=f"Aptitude {i}", report_url="/local-files/uploads/r.pdf", status="completed"))
        db.add(SchoolTestPrepRecord(school_student_id=kid.id, academic_team_user_id=staff.id, test_type="ielts"))
        db.add(SchoolLanguageRecord(school_student_id=kid.id, academic_team_user_id=staff.id, language="French"))
        act = SchoolActivity(school_id=ctx["school"].id, title=f"Seminar {i}", scheduled_at=datetime.now(UTC), created_by_user_id=coord.id)
        db.add(act)
        await db.flush()
        db.add(SchoolActivityAttendance(activity_id=act.id, school_student_id=kid.id, present=True, marked_by_user_id=coord.id))
        for section in ("award", "certification", "skill", "project"):
            db.add(PortfolioEntry(school_student_id=kid.id, section=section, title=f"{section} {i}", created_by_user_id=coord.id, updated_by_user_id=coord.id))
        await db.commit()
        result = await mk_result(db, kid, staff, status="published", subject=f"Subject {i}")
        result.teacher_remarks = f"Remark {i}"
        await db.commit()
    return kid


@pytest.mark.asyncio
async def test_coordinator_sees_all_sixteen_tabs_populated(client, db_session):  # AC-01
    ctx = await mk_school(db_session, label="E13-Full")
    kid = await _fill(db_session, ctx)
    await login(client, ctx["coordinator"].email)
    body = (await client.get(URL.format(sid=kid.id))).json()
    assert tuple(body["tabs"]) == TAB_360_KEYS
    statuses = {k: t["status"] for k, t in body["tabs"].items()}
    assert statuses["parent_communication"] == "empty"
    assert all(s == "has_data" for k, s in statuses.items() if k not in {"parent_communication", "academic_records"}), statuses
    assert body["student"]["student_code"] == kid.student_code
    assert body["can_edit_career_goal"] is False


@pytest.mark.asyncio
async def test_new_enrolment_renders_every_tab_as_empty_not_error(client, db_session):  # AC-04
    ctx = await mk_school(db_session, label="E13-Empty")
    kid = ctx["students"][0]
    for who in ("coordinator", "principal", "teacher", "parent"):
        await login(client, ctx[who].email)
        r = await client.get(URL.format(sid=kid.id))
        assert r.status_code == 200, (who, r.text)
        for key, tab in r.json()["tabs"].items():
            if key == "personal_details":
                assert tab["status"] == "has_data"
            else:
                assert tab["status"] == "empty", (who, key, tab)


@pytest.mark.asyncio
async def test_teacher_outside_assignment_is_rejected(client, db_session):  # AC-02
    ctx = await mk_school(db_session, label="E13-Teach", students=2)
    await login(client, ctx["teacher"].email)
    r = await client.get(URL.format(sid=ctx["students"][1].id))
    assert (r.status_code, r.json()["detail"]) == (403, "This student is not assigned to you")


@pytest.mark.asyncio
async def test_scope_matrix_rejections(client, db_session):  # AC-03
    a = await mk_school(db_session, label="E13-ScopeA", students=2)
    b = await mk_school(db_session, label="E13-ScopeB", admin=a["admin"])
    kid, sibling = a["students"]
    cases = [
        (a["parent"], sibling.id, 403), (b["coordinator"], kid.id, 403), (b["principal"], kid.id, 403),
        (await mk_staff(db_session, b["school"], a["admin"], role="psychometric_team"), kid.id, 403),
        (await mk_user(db_session, role="overseas_admin", name="Admin"), kid.id, 403),
        (a["coordinator"], uuid.uuid4(), 404),
    ]
    for who, sid, status in cases:
        await login(client, who.email)
        assert (await client.get(URL.format(sid=sid))).status_code == status, who.role
    client.cookies.clear()
    assert (await client.get(URL.format(sid=kid.id))).status_code == 401
    await login(client, a["coordinator"].email)
    assert (await client.get("/api/v1/school/students/not-a-uuid/360-view")).status_code == 422


@pytest.mark.asyncio
async def test_unpublished_results_never_appear(client, db_session):  # AC-06
    ctx = await mk_school(db_session, label="E13-Draft")
    kid = ctx["students"][0]
    staff = await mk_staff(db_session, ctx["school"], ctx["admin"])
    await mk_result(db_session, kid, staff, status="draft", subject="Hidden draft")
    await mk_result(db_session, kid, staff, status="verified", subject="Hidden verified")
    for who in (ctx["coordinator"], staff):
        await login(client, who.email)
        assert "Hidden" not in (await client.get(URL.format(sid=kid.id))).text


@pytest.mark.asyncio
async def test_query_count_does_not_grow_with_rows(client, db_session):  # AC-09
    one = await mk_school(db_session, label="E13-Q1")
    many = await mk_school(db_session, label="E13-Q20", admin=one["admin"])
    kid1 = await _fill(db_session, one, 1)
    kid20 = await _fill(db_session, many, 20)

    async def count(ctx, kid) -> int:
        await login(client, ctx["coordinator"].email)
        seen = []
        listener = lambda conn, cursor, statement, *a: seen.append(statement)  # noqa: E731
        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            assert (await client.get(URL.format(sid=kid.id))).status_code == 200
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        return len(seen)

    assert await count(one, kid1) == await count(many, kid20)


@pytest.mark.asyncio
async def test_each_read_logs_ids_only(client, db_session, caplog):
    ctx = await mk_school(db_session, label="E13-Log")
    kid = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    with caplog.at_level(logging.INFO, logger="app.student_360"):
        await client.get(URL.format(sid=kid.id))
    records = [r for r in caplog.records if r.getMessage() == "student_360_view"]
    assert len(records) == 1
    assert records[0].extra_fields == {"actor_id": str(ctx["coordinator"].id), "role": "school_coordinator", "student_id": str(kid.id)}
```

- [ ] **Step 2: Run** — `python -m pytest tests/test_enh_013_360_view.py -q` → FAIL, 404 on every call (route missing).

- [ ] **Step 3: Implement `student_360.py`** (the complete module, incl. the per-role projection that Task 6 tests)

```python
"""ENH-013a -- Student 360° view / Career Passport (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md).

A read aggregation over already-built modules. Every tab is built from the payload builders the existing endpoints use
(`_overview_payload`, `portfolio_payload`, `_grade_history_rows`), then projected per role so no role sees anything here it
cannot already read through an existing endpoint (spec §6.3, "no new exposure"). The loader runs before any query, and every
query below uses the loaded `student`, never the raw path id.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.portfolio import portfolio_payload
from app.api.schools import SCHOOL_ROLES, _grade_history_rows, _load_student_for_reader, _overview_payload, _portfolio_school_ids, _student_in_portfolio
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, School, SchoolStudent, User
from app.schemas import TAB_360_KEYS, CareerGoalOut, CareerGoalUpdate, Student360Out

router = APIRouter(prefix="/school", tags=["school-360"])
logger = get_logger("app.student_360")

NOT_TRACKED = {
    "attendance": "Daily and period attendance is not tracked yet (ENH-030).",
    "personal_details": "Additional profile fields are not tracked yet (ENH-025).",
    "documents": "A student document registry is not tracked yet (ENH-013b).",
    "teacher_remarks": "A standalone teacher remarks log is not tracked yet (ENH-013b).",
    "parent_communication": "A parent communication log is not tracked yet (ENH-013b / ENH-014).",
}
RESTRICTED = {"status": "restricted", "count": None, "not_tracked": [], "data": {}}
ACTIVITY_SECTIONS = ("project", "internship", "sport", "leadership", "volunteering", "extracurricular")
ACHIEVEMENT_SECTIONS = ("award", "competition")


def _tab(key: str, data: dict, count: int | None, *, has_data: bool | None = None) -> dict:
    status = "has_data" if (has_data if has_data is not None else bool(count)) else "empty"
    return {"status": status, "count": count, "not_tracked": [NOT_TRACKED[key]] if key in NOT_TRACKED else [], "data": data}


def _programme_status(records: list[dict], field: str, done: str) -> str:
    values = {r[field] for r in records}
    return done if done in values else ("in_progress" if records else "not_started")


async def build_360(db: AsyncSession, user: User, student: SchoolStudent) -> dict:
    role = user.role
    school_role = role in SCHOOL_ROLES
    academic, counselor, psych = role == "academic_team", role == "career_counselor", role == "psychometric_team"

    overview = await _overview_payload(db, student)
    portfolio = await portfolio_payload(db, user, student)
    history = await _grade_history_rows(db, student) if school_role else []
    school = await db.get(School, student.school_id)  # identity-mapped: _overview_payload already loaded it
    entries = portfolio["entries"]

    header = {"id": student.id, "full_name": student.full_name, "school_name": school.name if school else None,
              "student_code": None, "grade_or_class": None, "date_of_birth": None, "assigned_teacher_name": None}
    if school_role:
        o = overview["student"]
        header.update(student_code=o["student_code"], grade_or_class=o["grade_or_class"], date_of_birth=o["date_of_birth"], assigned_teacher_name=o["assigned_teacher_name"])

    results_full = overview["results"]
    psych_by_id = {a["id"]: a for a in overview["psychometric"]["assessments"]}
    skills = overview["skills"]
    if counselor:  # only this student's batches at their current (portfolio) school -- an old school's batch is not the counselor's
        skills = {m: {**v, "enrollments": [e for e in v["enrollments"] if not e["frozen"]]} for m, v in skills.items()}
    skill_enrolments = [e for m in skills.values() for e in m["enrollments"]]
    languages = overview["foreign_language"]["records"] if (school_role or academic) else portfolio["languages"]
    achievements = [e for s in ACHIEVEMENT_SECTIONS for e in entries[s]]
    activity_entries = {s: entries[s] for s in ACTIVITY_SECTIONS}
    attended = overview["activities"]["attended"]

    tabs: dict[str, dict] = {}
    tabs["personal_details"] = _tab("personal_details", dict(header), None, has_data=True)
    tabs["academic_records"] = _tab("academic_records", {"grade_or_class": header["grade_or_class"], "grade_history": history}, len(history)) if school_role else RESTRICTED
    tabs["attendance"] = (
        _tab("attendance", {"activities": attended, "skill_sessions": [{"batch_title": e["batch_title"], **e["attendance"]} for e in skill_enrolments if e["attendance"]["marked"]]},
             len(attended) + sum(1 for e in skill_enrolments if e["attendance"]["marked"]))
        if school_role else RESTRICTED
    )
    if school_role or academic:
        tabs["examination_results"] = _tab("examination_results", {"results": results_full}, len(results_full))
    else:
        tabs["examination_results"] = _tab("examination_results", {"results": portfolio["academic_achievements"]}, len(portfolio["academic_achievements"]))
    tabs["career_guidance"] = _tab("career_guidance", {"records": portfolio["career_guidance"]}, len(portfolio["career_guidance"]))
    if school_role or psych:
        assessments = [{**a, "status": psych_by_id.get(a["id"], {}).get("status")} for a in portfolio["psychometric_report"]]
    else:
        assessments = portfolio["psychometric_report"]
    tabs["psychometric_assessment"] = _tab("psychometric_assessment", {"assessments": assessments}, len(assessments))
    batches = skills if (school_role or counselor) else None
    tabs["skills"] = _tab("skills", {"batches": batches, "portfolio_entries": entries["skill"]}, (len(skill_enrolments) if batches else 0) + len(entries["skill"]))
    tabs["foreign_languages"] = _tab("foreign_languages", {"records": languages}, len(languages))
    test_prep = overview["test_prep"]["records"]
    tabs["english_testing"] = _tab("english_testing", {"records": test_prep}, len(test_prep)) if (school_role or academic) else RESTRICTED
    tabs["activities"] = _tab(
        "activities",
        {"attended": attended if school_role else None, "upcoming": overview["activities"]["upcoming"] if school_role else None, "portfolio_entries": activity_entries},
        (len(attended) if school_role else 0) + sum(len(v) for v in activity_entries.values()),
    )
    tabs["certificates"] = _tab("certificates", {"entries": entries["certification"]}, len(entries["certification"]))
    reports = [{"assessment_type": a["assessment_type"], "report_url": a["report_url"], "created_at": a["created_at"]} for a in portfolio["psychometric_report"] if a["report_url"]]
    tabs["documents"] = _tab("documents", {"psychometric_reports": reports}, len(reports))
    remarks = [{"id": r["id"], "academic_year": r["academic_year"], "term": r["term"], "subject": r["subject"], "teacher_remarks": r["teacher_remarks"]} for r in results_full if r["teacher_remarks"]]
    tabs["teacher_remarks"] = _tab("teacher_remarks", {"remarks": remarks}, len(remarks)) if (school_role or academic) else RESTRICTED
    tabs["parent_communication"] = _tab("parent_communication", {}, 0)

    programmes = []
    if school_role or counselor:
        programmes += [{"key": m, "status": v["status"]} for m, v in skills.items()]
    if school_role or academic:
        programmes.append({"key": "test_prep", "status": overview["test_prep"]["status"]})
    programmes.append({"key": "foreign_language", "status": _programme_status(languages, "certification_status", "certified")})
    if school_role:
        programmes.append({"key": "global_education", "status": overview["global_education"]["status"], "applications": overview["global_education"]["applications"]})
    active = sum(1 for p in programmes if p["status"] not in ("not_started",))
    tabs["edusphere_programs"] = _tab("edusphere_programs", {"programmes": programmes}, active)

    tabs["overview"] = _tab("overview", {"achievements": achievements, "portfolio_completion_percentage": portfolio["completion_percentage"]},
                            len(achievements), has_data=bool(student.career_goal or achievements))
    return {
        "student": header,
        "career_goal": student.career_goal,
        "can_edit_career_goal": counselor,
        "tabs": {key: tabs[key] for key in TAB_360_KEYS},
    }


@router.get("/students/{student_id}/360-view", response_model=Student360Out)
async def student_360_view(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_student_for_reader(db, user, student_id)
    body = await build_360(db, user, student)
    logger.info("student_360_view", extra={"extra_fields": {"actor_id": str(user.id), "role": user.role, "student_id": str(student.id)}})
    return body
```

Note on `global_education` status values: overview uses `"linked"`/`"not_started"`, so `active` counts it when linked. `skills` rollup statuses are `not_started|in_progress|completed|certified`; `test_prep` is `not_started|in_progress|completed`.

`main.py`: add `student_360` to the `from app.api import ...` line and `student_360.router` to the router tuple.

- [ ] **Step 4: Run** — `python -m pytest tests/test_enh_013_360_view.py -q` → PASS. If `test_coordinator_sees_all_sixteen_tabs_populated` fails only on `academic_records` (no promotion history), that is the expected carve-out already in the assertion.

- [ ] **Step 5: Commit** — `feat(enh-013): GET /school/students/{id}/360-view`

---

### Task 6: No new exposure for the service roles

**Files:**
- Test: `apps/api/tests/test_enh_013_360_view.py` (append)
- Modify: `apps/api/app/api/student_360.py` only if a test fails

- [ ] **Step 1: Write the tests (append)**

```python
RESTRICTED_FOR = {
    "academic_team": {"academic_records", "attendance"},
    "career_counselor": {"academic_records", "attendance", "english_testing", "teacher_remarks"},
    "psychometric_team": {"academic_records", "attendance", "english_testing", "teacher_remarks"},
}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", sorted(RESTRICTED_FOR))
async def test_service_roles_get_no_new_exposure(client, db_session, role):  # AC-05
    ctx = await mk_school(db_session, label=f"E13-{role}")
    kid = await _fill(db_session, ctx)
    member = await mk_staff(db_session, ctx["school"], ctx["admin"], role=role)
    await login(client, member.email)
    body = (await client.get(URL.format(sid=kid.id))).json()
    for key, tab in body["tabs"].items():
        if key in RESTRICTED_FOR[role]:
            assert tab == {"status": "restricted", "count": None, "not_tracked": [], "data": {}}, key
        else:
            assert tab["status"] != "restricted", key
    s = body["student"]
    assert (s["student_code"], s["grade_or_class"], s["date_of_birth"], s["assigned_teacher_name"]) == (None, None, None, None)
    assert body["tabs"]["activities"]["data"]["attended"] is None
    programmes = {p["key"] for p in body["tabs"]["edusphere_programs"]["data"]["programmes"]}
    assert "global_education" not in programmes
    results = body["tabs"]["examination_results"]["data"]["results"]
    if role != "academic_team":
        assert set(results[0]) == {"id", "term", "subject", "grade", "published_at"}
        assert body["tabs"]["skills"]["data"]["batches"] is None if role == "psychometric_team" else True
        langs = body["tabs"]["foreign_languages"]["data"]["records"]
        assert set(langs[0]) == {"id", "language", "level", "certification_status", "created_at"}
    else:
        assert "teacher_remarks" in results[0]
        assert body["tabs"]["skills"]["data"]["batches"] is None
    psych = body["tabs"]["psychometric_assessment"]["data"]["assessments"][0]
    assert ("status" in psych) == (role == "psychometric_team")
    assert body["can_edit_career_goal"] is (role == "career_counselor")


@pytest.mark.asyncio
async def test_school_roles_see_nothing_the_overview_does_not_already_give_them(client, db_session):
    ctx = await mk_school(db_session, label="E13-SchoolEq")
    kid = await _fill(db_session, ctx)
    await login(client, ctx["parent"].email)
    overview = (await client.get(f"/api/v1/school/students/{kid.id}/overview")).json()
    view = (await client.get(URL.format(sid=kid.id))).json()
    assert view["tabs"]["examination_results"]["data"]["results"] == overview["results"]
    assert view["tabs"]["english_testing"]["data"]["records"] == overview["test_prep"]["records"]
```

- [ ] **Step 2: Run** — `python -m pytest tests/test_enh_013_360_view.py -q`. Expected: PASS if Task 5's projection is right. **RED discipline:** before running, temporarily change `tabs["english_testing"] = ... if (school_role or academic) else RESTRICTED` to drop the `else RESTRICTED` guard (always build the tab); run; confirm `test_service_roles_get_no_new_exposure[career_counselor]` FAILS on `english_testing`; restore the guard; rerun → PASS. This proves the test actually guards the projection.

- [ ] **Step 3: Commit** — `test(enh-013): per-role no-new-exposure matrix for the 360-view`

---

### Task 7: `PATCH /career-goal` — role, scope, audit, rollback, transfer race

**Files:**
- Modify: `apps/api/app/api/student_360.py` (append the route)
- Test: `apps/api/tests/test_enh_013_career_goal.py` (append)

- [ ] **Step 1: Write the failing tests (append)**

```python
import asyncio

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models import AuditLog, SchoolStudent
from tests.enh005_helpers import login, mk_school, mk_staff

GOAL = "/api/v1/school/students/{sid}/career-goal"


async def _goal_of(sid):
    async with SessionLocal() as s:
        return await s.scalar(select(SchoolStudent.career_goal).where(SchoolStudent.id == sid))


@pytest.mark.asyncio
async def test_counselor_sets_and_clears_goal_with_audit(client, db_session):  # AC-07
    ctx = await mk_school(db_session, label="E13-Goal")
    kid = ctx["students"][0]
    cc = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    await login(client, cc.email)
    r = await client.patch(GOAL.format(sid=kid.id), json={"career_goal": "  Technology "})
    assert r.status_code == 200, r.text
    assert r.json()["career_goal"] == "Technology" and r.json()["school_student_id"] == str(kid.id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.career_goal_update", AuditLog.entity_id == str(kid.id)))
    assert audit.metadata_json == {"old": None, "new": "Technology"} and audit.user_id == cc.id
    await login(client, ctx["parent"].email)
    assert (await client.get(f"/api/v1/school/students/{kid.id}/360-view")).json()["career_goal"] == "Technology"
    await login(client, cc.email)
    assert (await client.patch(GOAL.format(sid=kid.id), json={"career_goal": ""})).json()["career_goal"] is None
    assert await _goal_of(kid.id) is None


@pytest.mark.asyncio
async def test_only_an_in_scope_counselor_may_write(client, db_session):  # AC-07
    a = await mk_school(db_session, label="E13-GoalA")
    b = await mk_school(db_session, label="E13-GoalB", admin=a["admin"])
    kid = a["students"][0]
    others = [a["coordinator"], a["principal"], a["teacher"], a["parent"],
              await mk_staff(db_session, a["school"], a["admin"], role="academic_team"),
              await mk_staff(db_session, a["school"], a["admin"], role="psychometric_team")]
    for who in others:
        await login(client, who.email)
        r = await client.patch(GOAL.format(sid=kid.id), json={"career_goal": "X"})
        assert (r.status_code, r.json()["detail"]) == (403, "Career Counselor role required"), who.role
    outsider = await mk_staff(db_session, b["school"], a["admin"], role="career_counselor")
    await login(client, outsider.email)
    assert (await client.patch(GOAL.format(sid=kid.id), json={"career_goal": "X"})).status_code == 403
    for bad in ({"career_goal": "a" * 121}, {"career_goal": "x", "school_id": str(b["school"].id)}, {}):
        assert (await client.patch(GOAL.format(sid=kid.id), json=bad)).status_code in (403, 422)
    assert await _goal_of(kid.id) is None


@pytest.mark.asyncio
async def test_validation_is_422_for_an_in_scope_counselor(client, db_session):
    ctx = await mk_school(db_session, label="E13-Goal422")
    kid = ctx["students"][0]
    cc = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    await login(client, cc.email)
    for bad in ({"career_goal": "a" * 121}, {"career_goal": "a\nb"}, {"career_goal": "x", "school_id": "y"}, {}):
        assert (await client.patch(GOAL.format(sid=kid.id), json=bad)).status_code == 422, bad


@pytest.mark.asyncio
async def test_a_failed_audit_write_rolls_back_the_goal(client, db_session, monkeypatch):
    from app.api import student_360

    ctx = await mk_school(db_session, label="E13-GoalRollback")
    kid = ctx["students"][0]
    cc = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    await login(client, cc.email)
    real = student_360.AuditLog
    monkeypatch.setattr(student_360, "AuditLog", lambda **kw: real(**{**kw, "user_id": uuid.uuid4()}))  # FK violation at commit
    with pytest.raises(Exception):
        await client.patch(GOAL.format(sid=kid.id), json={"career_goal": "Medicine"})
    assert await _goal_of(kid.id) is None


@pytest.mark.asyncio
async def test_a_write_racing_a_transfer_is_refused(client, db_session):  # AC-08
    a = await mk_school(db_session, label="E13-RaceA")
    b = await mk_school(db_session, label="E13-RaceB", admin=a["admin"])
    kid = a["students"][0]
    cc = await mk_staff(db_session, a["school"], a["admin"], role="career_counselor")
    await login(client, cc.email)
    mover = SessionLocal()
    try:
        await mover.execute(select(SchoolStudent).where(SchoolStudent.id == kid.id).with_for_update())
        pending = asyncio.create_task(client.patch(GOAL.format(sid=kid.id), json={"career_goal": "Law"}))
        await asyncio.sleep(0.5)  # the PATCH has passed its first scope check and is now queued on the row lock
        assert not pending.done()
        await mover.execute(update(SchoolStudent).where(SchoolStudent.id == kid.id).values(school_id=b["school"].id))
        await mover.commit()
    finally:
        await mover.close()
    r = await pending
    assert r.status_code == 403
    assert await _goal_of(kid.id) is None
```

Add `import uuid` at the top of the file.

- [ ] **Step 2: Run** — `python -m pytest tests/test_enh_013_career_goal.py -q` → the HTTP tests FAIL with 405 (no PATCH route).

- [ ] **Step 3: Implement (append to `student_360.py`)**

```python
@router.patch("/students/{student_id}/career-goal", response_model=CareerGoalOut)
async def update_career_goal(student_id: UUID, payload: CareerGoalUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Spec §6.2. One transaction: scope check, lock the student row (the lock transfer approval takes), re-check scope under
    it, write + audit, commit. Any failure before the commit leaves nothing written (the session closes without committing)."""
    if user.role != "career_counselor":
        raise HTTPException(403, "Career Counselor role required")
    await _student_in_portfolio(db, user, student_id)
    # populate_existing: the identity map still holds the pre-lock row from the check above -- re-read it under the lock.
    student = await db.scalar(select(SchoolStudent).where(SchoolStudent.id == student_id).with_for_update().execution_options(populate_existing=True))
    if student is None:
        raise HTTPException(404, "Student not found")
    if student.school_id not in await _portfolio_school_ids(db, user):
        raise HTTPException(403, "This student is at a school outside your own portfolio")
    old = student.career_goal
    student.career_goal = payload.career_goal
    db.add(AuditLog(user_id=user.id, action="school.career_goal_update", entity_type="school_student", entity_id=str(student.id), metadata_json={"old": old, "new": payload.career_goal}))
    await db.commit()
    await db.refresh(student)
    logger.info("career_goal_update", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id), "cleared": payload.career_goal is None}})
    return {"school_student_id": student.id, "career_goal": student.career_goal, "updated_at": student.updated_at}
```

- [ ] **Step 4: Run** — `python -m pytest tests/test_enh_013_career_goal.py tests/test_enh_013_360_view.py -q` → PASS.

- [ ] **Step 5: Commit** — `feat(enh-013): counsellor-set career goal with row lock and audit`

---

### Task 8: Frontend library — types, loader, links, safe hrefs

**Files:**
- Create: `apps/web/lib/student360.ts`, `apps/web/lib/student360Links.ts`
- Test: `apps/web/tests/lib/student360.test.ts`

`student360.ts` is server-only (it imports `serverApi`); the link/label helpers live in `student360Links.ts`, which has no server imports, so client components may use them.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it, vi } from "vitest";

const serverApi = vi.fn();
vi.mock("@/lib/api", () => ({ serverApi }));

import { loadStudent360 } from "@/lib/student360";
import { safeHref, student360Href, TAB_KEYS, TAB_LABELS } from "@/lib/student360Links";

describe("student360 library", () => {
  it("loads through serverApi (per-request, never cached)", async () => {
    serverApi.mockResolvedValue({ ok: true });
    await loadStudent360("abc");
    expect(serverApi).toHaveBeenCalledWith("/api/v1/school/students/abc/360-view");
  });

  it("has sixteen labelled tabs in display order", () => {
    expect(TAB_KEYS).toHaveLength(16);
    expect(TAB_KEYS[0]).toBe("overview");
    expect(TAB_KEYS[15]).toBe("edusphere_programs");
    for (const k of TAB_KEYS) expect(TAB_LABELS[k]).toBeTruthy();
  });

  it.each([
    ["school_coordinator", "/school/coordinator/students/s1/360"],
    ["school_principal", "/school/principal/students/s1/360"],
    ["school_teacher", "/school/teacher/students/s1/360"],
    ["school_parent", "/school/parent/children/s1/360"],
    ["academic_team", "/school/academic-team/students/s1/360"],
    ["career_counselor", "/school/career-counselor/students/s1/360"],
    ["psychometric_team", "/school/psychometric-team/students/s1/360"],
  ])("builds the %s route", (role, href) => {
    expect(student360Href(role, "s1")).toBe(href);
  });

  it.each([
    ["/local-files/uploads/r.pdf", "/local-files/uploads/r.pdf"],
    ["https://files.example.org/r.pdf", "https://files.example.org/r.pdf"],
    ["javascript:alert(1)", null],
    ["JavaScript:alert(1)", null],
    ["data:text/html,<b>x</b>", null],
    ["//evil.example/r.pdf", null],
    ["/\\evil.example", null],
    ["http://plain.example/r.pdf", null],
    ["", null],
  ])("safeHref(%j) -> %j", (input, expected) => {
    expect(safeHref(input)).toBe(expected);
  });
});
```

- [ ] **Step 2: Run** — `npx vitest run tests/lib/student360.test.ts` → FAIL (module not found).

- [ ] **Step 3: Implement**

`lib/student360Links.ts`:

```ts
// ENH-013 -- client-safe helpers for the Student 360° view (no server imports, so "use client" components may use them).

export const TAB_KEYS = [
  "overview", "personal_details", "academic_records", "attendance", "examination_results", "career_guidance",
  "psychometric_assessment", "skills", "foreign_languages", "english_testing", "activities", "certificates",
  "documents", "teacher_remarks", "parent_communication", "edusphere_programs",
] as const;
export type TabKey = (typeof TAB_KEYS)[number];

export const TAB_LABELS: Record<TabKey, string> = {
  overview: "Overview", personal_details: "Personal Details", academic_records: "Academic Records", attendance: "Attendance",
  examination_results: "Examination Results", career_guidance: "Career Guidance", psychometric_assessment: "Psychometric Assessment",
  skills: "Skills", foreign_languages: "Foreign Languages", english_testing: "English Testing", activities: "Activities",
  certificates: "Certificates", documents: "Documents", teacher_remarks: "Teacher Remarks",
  parent_communication: "Parent Communication", edusphere_programs: "Edusphere Programs",
};

const ROLE_BASE: Record<string, string> = {
  school_coordinator: "/school/coordinator/students", school_principal: "/school/principal/students",
  school_teacher: "/school/teacher/students", school_parent: "/school/parent/children",
  academic_team: "/school/academic-team/students", career_counselor: "/school/career-counselor/students",
  psychometric_team: "/school/psychometric-team/students",
};

export function student360Href(role: string, studentId: string): string | null {
  const base = ROLE_BASE[role];
  return base ? `${base}/${studentId}/360` : null;
}

export function isTabKey(value: string | null | undefined): value is TabKey {
  return !!value && (TAB_KEYS as readonly string[]).includes(value);
}

// report_url is stored unvalidated upstream (SCH-005, RAID finding). Only a same-origin path or an https URL becomes a link;
// anything else (javascript:, data:, protocol-relative //host, backslash tricks, plain http) is rendered as text by the caller.
export function safeHref(value: string | null | undefined): string | null {
  if (!value) return null;
  const v = value.trim();
  if (v.startsWith("/") && !v.startsWith("//") && !v.startsWith("/\\")) return v;
  try {
    const url = new URL(v);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}
```

`lib/student360.ts`:

```ts
import { serverApi } from "@/lib/api";
import type { TabKey } from "@/lib/student360Links";

// ENH-013 -- server-only loader + response types for GET /school/students/{id}/360-view (spec §6.1).
// serverApi fetches with cache: "no-store" -- never use publicApi here (it caches for 60s across users).

export type TabStatus = "has_data" | "empty" | "restricted";
export type Tab360<D = Record<string, unknown>> = { status: TabStatus; count: number | null; not_tracked: string[]; data: D };
export type Student360Header = {
  id: string; full_name: string; school_name: string | null; student_code: string | null;
  grade_or_class: string | null; date_of_birth: string | null; assigned_teacher_name: string | null;
};
export type Student360 = { student: Student360Header; career_goal: string | null; can_edit_career_goal: boolean; tabs: Record<TabKey, Tab360> };

export function loadStudent360(studentId: string): Promise<Student360> {
  return serverApi<Student360>(`/api/v1/school/students/${studentId}/360-view`);
}
```

- [ ] **Step 4: Run** — same command → PASS.

- [ ] **Step 5: Commit** — `feat(enh-013): 360-view frontend library and safe links`

---

### Task 9: `Student360Tabs` — accessible tabs (client)

**Files:**
- Create: `apps/web/components/Student360Tabs.tsx`
- Modify: `apps/web/app/globals.css` (append `.s360-*` rules)
- Test: `apps/web/tests/components/Student360Tabs.test.tsx`

**Interfaces:**
- Produces: `<Student360Tabs tabs={{key, label, status, count}[]} initialTab={TabKey}>{panels: ReactNode[] in the same order}</Student360Tabs>`.

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }), usePathname: () => "/school/coordinator/students/s1/360" }));

import Student360Tabs from "@/components/Student360Tabs";

afterEach(() => { cleanup(); replace.mockReset(); });

const TABS = [
  { key: "overview", label: "Overview", status: "has_data", count: null },
  { key: "skills", label: "Skills", status: "has_data", count: 3 },
  { key: "attendance", label: "Attendance", status: "restricted", count: null },
  { key: "documents", label: "Documents", status: "empty", count: 0 },
] as const;

function setup(initial = "overview") {
  return render(
    <Student360Tabs tabs={[...TABS]} initialTab={initial as never}>
      {TABS.map((t) => <p key={t.key}>{t.label} panel</p>)}
    </Student360Tabs>,
  );
}

describe("Student360Tabs", () => {
  it("renders the ARIA tabs pattern with only the selected tab focusable", () => {
    setup();
    expect(screen.getByRole("tablist", { name: /student record sections/i })).toBeInTheDocument();
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(4);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[0]).toHaveAttribute("tabindex", "0");
    expect(tabs[1]).toHaveAttribute("tabindex", "-1");
    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute("aria-labelledby", tabs[0].id);
    expect(panel).toHaveTextContent("Overview panel");
  });

  it("states count, empty and restricted in the accessible name, not by colour alone", () => {
    setup();
    expect(screen.getByRole("tab", { name: /skills.*3 records/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /documents.*no records yet/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /attendance.*not available for your role/i })).toBeInTheDocument();
  });

  it("moves with arrow keys, wraps, and supports Home/End", () => {
    setup();
    const tabs = screen.getAllByRole("tab");
    fireEvent.keyDown(tabs[0], { key: "ArrowRight" });
    expect(screen.getAllByRole("tab")[1]).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(screen.getAllByRole("tab")[1]);
    fireEvent.keyDown(screen.getAllByRole("tab")[1], { key: "ArrowUp" });
    expect(screen.getAllByRole("tab")[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getAllByRole("tab")[0], { key: "ArrowLeft" });
    expect(screen.getAllByRole("tab")[3]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getAllByRole("tab")[3], { key: "Home" });
    expect(screen.getAllByRole("tab")[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getAllByRole("tab")[0], { key: "End" });
    expect(screen.getAllByRole("tab")[3]).toHaveAttribute("aria-selected", "true");
  });

  it("keeps the selection in ?tab= without scrolling", () => {
    setup();
    fireEvent.click(screen.getByRole("tab", { name: /skills/i }));
    expect(replace).toHaveBeenCalledWith("/school/coordinator/students/s1/360?tab=skills", { scroll: false });
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Skills panel");
  });

  it("starts on the initial tab", () => {
    setup("documents");
    expect(screen.getByRole("tab", { name: /documents/i })).toHaveAttribute("aria-selected", "true");
  });
});
```

- [ ] **Step 2: Run** — `npx vitest run tests/components/Student360Tabs.test.tsx` → FAIL (module not found).

- [ ] **Step 3: Implement**

```tsx
"use client";

import { usePathname, useRouter } from "next/navigation";
import { Children, type ReactNode, useRef, useState } from "react";

import type { TabKey } from "@/lib/student360Links";

// ENH-013 -- WAI-ARIA tabs for the Student 360° view. Only the selection lives here: the panels arrive already rendered by
// the server (Student360View), so this client component never needs server-only imports (tests/lib/clientBoundary.test.ts).
// Roving tabindex; arrows in both axes (the list is vertical on desktop, a scrolling row on mobile), Home/End; the choice is
// mirrored into ?tab= with replace + scroll:false so deep links and reloads land on the same tab without a scroll jump.

export type TabSummary = { key: TabKey; label: string; status: "has_data" | "empty" | "restricted"; count: number | null };

function stateText(t: TabSummary): string {
  if (t.status === "restricted") return ", not available for your role";
  if (t.status === "empty") return ", no records yet";
  return t.count ? `, ${t.count} record${t.count === 1 ? "" : "s"}` : "";
}

export default function Student360Tabs({ tabs, initialTab, children }: { tabs: TabSummary[]; initialTab: TabKey; children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const panels = Children.toArray(children);
  const [selected, setSelected] = useState(Math.max(0, tabs.findIndex((t) => t.key === initialTab)));
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function select(index: number, focus: boolean) {
    setSelected(index);
    router.replace(`${pathname}?tab=${tabs[index].key}`, { scroll: false });
    if (focus) {
      const el = refs.current[index];
      el?.focus();
      el?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    }
  }

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    const last = tabs.length - 1;
    const next = { ArrowRight: index + 1, ArrowDown: index + 1, ArrowLeft: index - 1, ArrowUp: index - 1, Home: 0, End: last }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    select(next > last ? 0 : next < 0 ? last : next, true);
  }

  const id = (key: string) => `s360-tab-${key}`;
  return (
    <div className="s360-layout">
      <div role="tablist" aria-label="Student record sections" aria-orientation="vertical" className="s360-tablist">
        {tabs.map((t, i) => (
          <button
            key={t.key}
            ref={(el) => { refs.current[i] = el; }}
            id={id(t.key)}
            type="button"
            role="tab"
            aria-selected={i === selected}
            aria-controls="s360-panel"
            tabIndex={i === selected ? 0 : -1}
            className={`s360-tab ${t.status}`}
            onClick={() => select(i, false)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            <span>{t.label}</span>
            {t.status === "has_data" && t.count ? <span className="s360-count" aria-hidden="true">{t.count}</span> : null}
            {t.status === "restricted" ? <span className="s360-lock" aria-hidden="true">Restricted</span> : null}
            <span className="visually-hidden">{stateText(t)}</span>
          </button>
        ))}
      </div>
      <div id="s360-panel" role="tabpanel" aria-labelledby={id(tabs[selected].key)} tabIndex={0} className="s360-panel">
        {panels[selected]}
      </div>
    </div>
  );
}
```

`globals.css` (append; tokens from `:root`, breakpoints 980/640 as elsewhere):

```css
/* ENH-013 Student 360° view */
.visually-hidden{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.s360-layout{display:grid;grid-template-columns:240px minmax(0,1fr);gap:20px;align-items:start}
.s360-tablist{display:flex;flex-direction:column;gap:4px;position:sticky;top:16px}
.s360-tab{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:44px;padding:10px 14px;border:1px solid transparent;border-radius:10px;background:transparent;font:inherit;font-weight:700;font-size:14px;color:var(--ink);text-align:left;cursor:pointer}
.s360-tab:hover{background:var(--soft)}
.s360-tab:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.s360-tab[aria-selected="true"]{background:var(--soft);border-color:var(--line);color:var(--blue)}
.s360-tab.empty,.s360-tab.restricted{color:var(--muted);font-weight:600}
.s360-count{font-size:12px;font-weight:800;border-radius:99px;padding:2px 8px;background:#e8f0fb;color:var(--blue)}
.s360-lock{font-size:11px;font-weight:700;color:var(--muted)}
.s360-panel{min-width:0}
.s360-panel:focus-visible{outline:2px solid var(--blue);outline-offset:4px;border-radius:var(--radius)}
.s360-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
.s360-tile{display:grid;gap:6px;min-height:44px;padding:14px;border:1px solid var(--line);border-radius:12px;background:#fff;font:inherit;text-align:left;cursor:pointer}
.s360-tile:hover,.s360-tile:focus-visible{border-color:var(--blue)}
.s360-list{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.s360-list li{padding:12px 14px;border:1px solid var(--line);border-radius:12px}
@media(max-width:980px){.s360-layout{grid-template-columns:1fr}.s360-tablist{flex-direction:row;overflow-x:auto;scroll-snap-type:x proximity;position:static;padding-bottom:4px}.s360-tab{flex:0 0 auto;scroll-snap-align:start;white-space:nowrap}}
```

(Check first whether a `.visually-hidden`/`.sr-only` rule already exists in `globals.css`/`controls.css`; reuse it instead of adding one.)

- [ ] **Step 4: Run** — PASS.

- [ ] **Step 5: Commit** — `feat(enh-013): accessible 360-view tabs`

---

### Task 10: Panels + view (server)

**Files:**
- Create: `apps/web/components/Student360Panels.tsx`, `apps/web/components/Student360View.tsx`
- Modify: `apps/web/components/SchoolChildOverview.tsx:80` (`function SkillsCard` → `export function SkillsCard`)
- Test: `apps/web/tests/components/Student360Panels.test.tsx`

**Interfaces:**
- Consumes: `Student360`, `Tab360` (Task 8), `Student360Tabs` (Task 9), `CareerGoalForm` (Task 11: `<CareerGoalForm studentId goal />`).
- Produces: `Student360View({ data: Student360, initialTab: string | undefined, backHref: string, backLabel: string })`; `renderPanel(key, tab, data) -> ReactNode`.

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }), usePathname: () => "/x" }));
vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));

import { renderPanel } from "@/components/Student360Panels";
import type { Tab360 } from "@/lib/student360";

afterEach(cleanup);

const empty = (data: Record<string, unknown> = {}, not_tracked: string[] = []): Tab360 => ({ status: "empty", count: 0, not_tracked, data });
const restricted: Tab360 = { status: "restricted", count: null, not_tracked: [], data: {} };
const base = { student: { id: "s1", full_name: "Asha", school_name: "S", student_code: null, grade_or_class: null, date_of_birth: null, assigned_teacher_name: null }, career_goal: null, can_edit_career_goal: false, tabs: {} as never };

describe("Student360Panels", () => {
  it("renders a restricted tab as 'not available', never as 'no records'", () => {
    render(<>{renderPanel("attendance", restricted, base)}</>);
    expect(screen.getByRole("status")).toHaveTextContent(/not available for your role/i);
    expect(screen.queryByText(/no .* yet/i)).not.toBeInTheDocument();
  });

  it("renders an empty state with who records it, plus the not-tracked note", () => {
    render(<>{renderPanel("attendance", empty({ activities: [], skill_sessions: [] }, ["Daily and period attendance is not tracked yet (ENH-030)."]), base)}</>);
    expect(screen.getByRole("status")).toHaveTextContent(/no attendance recorded yet/i);
    expect(screen.getByText(/not tracked yet \(ENH-030\)/)).toBeInTheDocument();
  });

  it("links only safe document URLs", () => {
    const tab: Tab360 = { status: "has_data", count: 2, not_tracked: [], data: { psychometric_reports: [
      { assessment_type: "Aptitude", report_url: "/local-files/uploads/r.pdf", created_at: "2026-09-01T00:00:00Z" },
      { assessment_type: "Interest", report_url: "javascript:alert(1)", created_at: "2026-09-01T00:00:00Z" },
    ] } };
    render(<>{renderPanel("documents", tab, base)}</>);
    expect(screen.getByRole("link", { name: /aptitude report/i })).toHaveAttribute("href", "/local-files/uploads/r.pdf");
    expect(screen.queryByRole("link", { name: /interest/i })).not.toBeInTheDocument();
    expect(screen.getByText("javascript:alert(1)")).toBeInTheDocument();
  });

  it("shows 'No career goal set yet' on an empty overview", () => {
    render(<>{renderPanel("overview", empty({ achievements: [], portfolio_completion_percentage: 0 }), base)}</>);
    expect(screen.getByText(/no career goal set yet/i)).toBeInTheDocument();
  });

  it("renders every tab key without throwing for an empty student", () => {
    const shapes: Record<string, Record<string, unknown>> = {
      overview: { achievements: [], portfolio_completion_percentage: 0 }, academic_records: { grade_or_class: null, grade_history: [] },
      attendance: { activities: [], skill_sessions: [] }, examination_results: { results: [] }, career_guidance: { records: [] },
      psychometric_assessment: { assessments: [] }, skills: { batches: null, portfolio_entries: [] }, foreign_languages: { records: [] },
      english_testing: { records: [] }, activities: { attended: null, upcoming: null, portfolio_entries: {} }, certificates: { entries: [] },
      documents: { psychometric_reports: [] }, teacher_remarks: { remarks: [] }, parent_communication: {}, edusphere_programs: { programmes: [] },
    };
    for (const [key, data] of Object.entries(shapes)) {
      const { unmount } = render(<>{renderPanel(key as never, empty(data), base)}</>);
      unmount();
    }
    const { unmount } = render(<>{renderPanel("personal_details", { status: "has_data", count: null, not_tracked: [], data: base.student }, base)}</>);
    unmount();
  });
});
```

- [ ] **Step 2: Run** — FAIL (module not found).

- [ ] **Step 3: Implement `Student360Panels.tsx`** (server-renderable; no `"use client"`)

```tsx
import CareerGoalForm from "@/components/CareerGoalForm";
import { formatDate, SkillsCard, StatusChip } from "@/components/SchoolChildOverview";
import SchoolGradeHistory from "@/components/SchoolGradeHistory";
import type { Student360, Tab360 } from "@/lib/student360";
import { safeHref, TAB_LABELS, type TabKey } from "@/lib/student360Links";

// ENH-013 -- one small presentational function per tab (spec §8). Every tab has three shapes: restricted (the viewer's role
// cannot read this source anywhere else, so neither can it here), empty (a friendly state naming who records the data), or
// data. Rendered on the server and handed to Student360Tabs as children.

type Row = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
type Entry = { id: string; title: string; organization: string | null; date_from: string | null; date_to: string | null; description: string | null };

const EMPTY_TEXT: Record<TabKey, string> = {
  overview: "No career goal or achievements recorded yet.",
  personal_details: "",
  academic_records: "No grade history yet. It appears after the student's first promotion.",
  attendance: "No attendance recorded yet. The School Coordinator marks activity attendance.",
  examination_results: "No published results yet. Results appear after the Academic Team publishes them.",
  career_guidance: "No career guidance recorded yet. The Career Counselor adds sessions and notes.",
  psychometric_assessment: "No psychometric assessments yet.",
  skills: "No skills recorded yet.",
  foreign_languages: "No foreign language classes recorded yet.",
  english_testing: "No English test preparation recorded yet.",
  activities: "No activities recorded yet.",
  certificates: "No certificates recorded yet. Staff add them in the Digital Portfolio.",
  documents: "No documents yet.",
  teacher_remarks: "No teacher remarks on published results yet.",
  parent_communication: "No parent communication log yet.",
  edusphere_programs: "Not enrolled in any EduSphere programme yet.",
};

function Empty({ tabKey }: { tabKey: TabKey }) {
  return <p className="empty" role="status">{EMPTY_TEXT[tabKey]}</p>;
}

function NotTracked({ notes }: { notes: string[] }) {
  return notes.length ? <p className="muted">{notes.join(" ")}</p> : null;
}

function EntryList({ entries }: { entries: Entry[] }) {
  return (
    <ul className="s360-list">
      {entries.map((e) => (
        <li key={e.id}>
          <strong>{e.title}</strong>{e.organization ? <span className="muted"> — {e.organization}</span> : null}
          {e.date_from ? <span className="muted"> ({formatDate(e.date_from)}{e.date_to ? ` – ${formatDate(e.date_to)}` : ""})</span> : null}
          {e.description ? <p>{e.description}</p> : null}
        </li>
      ))}
    </ul>
  );
}

function Table({ head, rows }: { head: string[]; rows: (string | number | null)[][] }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c ?? "-"}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function Body({ tabKey, d, view }: { tabKey: TabKey; d: Row; view: Student360 }) {
  switch (tabKey) {
    case "overview":
      return (
        <>
          <div className="card">
            <h3>Career goal</h3>
            {view.can_edit_career_goal ? <CareerGoalForm studentId={view.student.id} goal={view.career_goal} /> : <p>{view.career_goal ?? <span className="muted">No career goal set yet.</span>}</p>}
          </div>
          <div className="card">
            <h3>Achievements</h3>
            {d.achievements.length ? <EntryList entries={d.achievements} /> : <p className="muted">No achievements recorded yet.</p>}
            <p className="muted">Digital Portfolio {d.portfolio_completion_percentage}% complete.</p>
          </div>
        </>
      );
    case "personal_details":
      return (
        <dl className="s360-grid">
          {([["Name", d.full_name], ["Student ID", d.student_code], ["Grade/Class", d.grade_or_class], ["Date of birth", d.date_of_birth ? formatDate(d.date_of_birth) : null], ["School", d.school_name], ["Assigned teacher", d.assigned_teacher_name]] as const)
            .filter(([, v]) => v !== null)
            .map(([k, v]) => <div key={k}><dt className="muted">{k}</dt><dd>{v}</dd></div>)}
        </dl>
      );
    case "academic_records":
      return (<><p><strong>Current grade/class:</strong> {d.grade_or_class ?? "-"}</p>{d.grade_history.length ? <SchoolGradeHistory history={d.grade_history} /> : <Empty tabKey={tabKey} />}</>);
    case "attendance":
      return (
        <>
          {d.activities.length ? <Table head={["Activity", "Date", "Attendance"]} rows={d.activities.map((a: Row) => [a.title, formatDate(a.scheduled_at), a.present ? "Present" : "Absent"])} /> : null}
          {d.skill_sessions.length ? <Table head={["Skills batch", "Sessions attended"]} rows={d.skill_sessions.map((s: Row) => [s.batch_title, `${s.present} of ${s.marked}`])} /> : null}
        </>
      );
    case "examination_results":
      return <Table head={["Year", "Term", "Subject", "Marks", "Grade"]} rows={d.results.map((r: Row) => [r.academic_year ?? null, r.term, r.subject, r.max_marks !== undefined ? `${r.marks_obtained}/${r.max_marks}` : null, r.grade])} />;
    case "career_guidance":
      return <ul className="s360-list">{d.records.map((r: Row) => <li key={r.id}><StatusChip status={r.record_type} /> <span className="muted">{formatDate(r.created_at)}</span><p>{r.notes}</p></li>)}</ul>;
    case "psychometric_assessment":
      return <Table head={["Assessment", "Status", "Date"]} rows={d.assessments.map((a: Row) => [a.assessment_type, a.status ?? null, formatDate(a.created_at)])} />;
    case "skills":
      return (<>{d.batches ? <SkillsCard skills={d.batches} /> : null}{d.portfolio_entries.length ? <><h3>Skills in the Digital Portfolio</h3><EntryList entries={d.portfolio_entries} /></> : null}</>);
    case "foreign_languages":
      return <Table head={["Language", "Level", "Certification"]} rows={d.records.map((r: Row) => [r.language, r.level, r.certification_status])} />;
    case "english_testing":
      return <Table head={["Test", "Target", "Result", "Status"]} rows={d.records.map((r: Row) => [String(r.test_type).toUpperCase(), r.target_score, r.actual_score, r.status])} />;
    case "activities":
      return (
        <>
          {d.attended?.length ? <><h3>School activities attended</h3><Table head={["Activity", "Date"]} rows={d.attended.filter((a: Row) => a.present).map((a: Row) => [a.title, formatDate(a.scheduled_at)])} /></> : null}
          {Object.entries(d.portfolio_entries as Record<string, Entry[]>).filter(([, v]) => v.length).map(([section, v]) => <div key={section}><h3>{section[0].toUpperCase() + section.slice(1)}</h3><EntryList entries={v} /></div>)}
        </>
      );
    case "certificates":
      return <EntryList entries={d.entries} />;
    case "documents":
      return (
        <ul className="s360-list">
          {d.psychometric_reports.map((r: Row, i: number) => {
            const href = safeHref(r.report_url);
            return <li key={i}>{href ? <a href={href} target="_blank" rel="noopener noreferrer">{r.assessment_type} report</a> : <><span>{r.assessment_type} report: </span><span className="muted">{r.report_url}</span></>} <span className="muted">{formatDate(r.created_at)}</span></li>;
          })}
        </ul>
      );
    case "teacher_remarks":
      return <ul className="s360-list">{d.remarks.map((r: Row) => <li key={r.id}><strong>{r.subject}</strong> <span className="muted">{r.academic_year} {r.term}</span><p>{r.teacher_remarks}</p></li>)}</ul>;
    case "edusphere_programs":
      return <ul className="s360-list">{d.programmes.map((p: Row) => <li key={p.key}><strong>{PROGRAMME_LABEL[p.key] ?? p.key}</strong> <StatusChip status={p.status} /></li>)}</ul>;
    default:
      return null;
  }
}

const PROGRAMME_LABEL: Record<string, string> = { soft_skills: "Soft Skills", digital_skills: "Digital Skills", test_prep: "Test preparation", foreign_language: "Foreign languages", global_education: "Global education" };

export function renderPanel(tabKey: TabKey, tab: Tab360, view: Student360) {
  const heading = <h2>{TAB_LABELS[tabKey]}</h2>;
  if (tab.status === "restricted") {
    return <div className="card">{heading}<p className="empty" role="status">This section is not available for your role.</p></div>;
  }
  const alwaysShowBody = tabKey === "overview" || tabKey === "personal_details" || tabKey === "academic_records";
  return (
    <div className="card">
      {heading}
      {tab.status === "empty" && !alwaysShowBody ? <Empty tabKey={tabKey} /> : <Body tabKey={tabKey} d={tab.data as Row} view={view} />}
      <NotTracked notes={tab.not_tracked} />
    </div>
  );
}
```

Note: `StatusChip` maps known statuses; if `record_type` values (`guidance_session`, …) have no label it renders the raw value — check `SchoolChildOverview.tsx:49` `STATUS_LABEL` during implementation and use a local label map for record types if needed.

`Student360View.tsx`:

```tsx
import Student360Tabs, { type TabSummary } from "@/components/Student360Tabs";
import { formatDate } from "@/components/SchoolChildOverview";
import { renderPanel } from "@/components/Student360Panels";
import type { Student360 } from "@/lib/student360";
import { isTabKey, TAB_KEYS, TAB_LABELS } from "@/lib/student360Links";

// ENH-013 -- the Student 360° page body shared by all 7 role routes: a header card, then the tabs. Server component.
export default function Student360View({ data, initialTab, backHref, backLabel }: { data: Student360; initialTab?: string; backHref: string; backLabel: string }) {
  const s = data.student;
  const summaries: TabSummary[] = TAB_KEYS.map((key) => ({ key, label: TAB_LABELS[key], status: data.tabs[key].status, count: data.tabs[key].count }));
  return (
    <div className="portal-content">
      <div className="card">
        <h1>{s.full_name}{s.student_code ? <span className="muted" style={{ fontSize: 14 }}> ({s.student_code})</span> : null}</h1>
        <p className="muted">
          Student 360° view{s.school_name ? ` · ${s.school_name}` : ""}{s.grade_or_class ? ` · ${s.grade_or_class}` : ""}{s.date_of_birth ? ` · Born ${formatDate(s.date_of_birth)}` : ""}
        </p>
        <p><strong>Career goal:</strong> {data.career_goal ?? <span className="muted">Not set</span>}</p>
        <a className="btn secondary" href={backHref}>{backLabel}</a>
      </div>
      <Student360Tabs tabs={summaries} initialTab={isTabKey(initialTab) ? initialTab : "overview"}>
        {TAB_KEYS.map((key) => <div key={key}>{renderPanel(key, data.tabs[key], data)}</div>)}
      </Student360Tabs>
    </div>
  );
}
```

`SchoolChildOverview.tsx`: `function SkillsCard(` → `export function SkillsCard(`.

- [ ] **Step 4: Run** — `npx vitest run tests/components/Student360Panels.test.tsx tests/lib/clientBoundary.test.ts` → PASS (Task 11 must exist first for the `CareerGoalForm` import — implement Task 11 before running Step 4 here, or run Task 11 first).

- [ ] **Step 5: Commit** — `feat(enh-013): 360-view panels and page body`

---

### Task 11: `CareerGoalForm` (client)

**Files:**
- Create: `apps/web/components/CareerGoalForm.tsx`
- Test: `apps/web/tests/components/CareerGoalForm.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

import CareerGoalForm from "@/components/CareerGoalForm";

afterEach(() => { cleanup(); vi.restoreAllMocks(); refresh.mockReset(); });

function ok(body: unknown) { return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } })); }

describe("CareerGoalForm", () => {
  it("shows the goal with an Edit button, then a labelled input with a live counter", () => {
    render(<CareerGoalForm studentId="s1" goal="Technology" />);
    expect(screen.getByText("Technology")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /edit career goal/i }));
    const input = screen.getByLabelText(/career goal/i);
    expect(input).toHaveValue("Technology");
    expect(input).toHaveAttribute("maxLength", "120");
    expect(screen.getByText("10/120")).toBeInTheDocument();
  });

  it("PATCHes, announces success, refreshes and returns focus to Edit", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => ok({ school_student_id: "s1", career_goal: "Medicine", updated_at: "x" }));
    render(<CareerGoalForm studentId="s1" goal={null} />);
    fireEvent.click(screen.getByRole("button", { name: /set career goal/i }));
    fireEvent.change(screen.getByLabelText(/career goal/i), { target: { value: "Medicine" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/career goal saved/i));
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/school/students/s1/career-goal", expect.objectContaining({ method: "PATCH", credentials: "include", body: JSON.stringify({ career_goal: "Medicine" }) }));
    expect(refresh).toHaveBeenCalled();
  });

  it("keeps the typed value and shows the server's message on failure", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "This student is at a school outside your own portfolio" }), { status: 403 }));
    render(<CareerGoalForm studentId="s1" goal={null} />);
    fireEvent.click(screen.getByRole("button", { name: /set career goal/i }));
    fireEvent.change(screen.getByLabelText(/career goal/i), { target: { value: "Law" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/outside your own portfolio/));
    expect(screen.getByLabelText(/career goal/i)).toHaveValue("Law");
  });

  it("blocks a double submit while saving", async () => {
    let resolve!: (r: Response) => void;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise((r) => { resolve = r; }));
    render(<CareerGoalForm studentId="s1" goal={null} />);
    fireEvent.click(screen.getByRole("button", { name: /set career goal/i }));
    fireEvent.change(screen.getByLabelText(/career goal/i), { target: { value: "Arts" } });
    const save = screen.getByRole("button", { name: /save/i });
    fireEvent.click(save);
    fireEvent.click(save);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: /saving/i })).toBeDisabled();
    resolve(new Response(JSON.stringify({ career_goal: "Arts" }), { status: 200 }));
  });

  it("Escape cancels without saving", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    render(<CareerGoalForm studentId="s1" goal="Technology" />);
    fireEvent.click(screen.getByRole("button", { name: /edit career goal/i }));
    fireEvent.keyDown(screen.getByLabelText(/career goal/i), { key: "Escape" });
    expect(screen.queryByLabelText(/career goal/i)).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run** — FAIL (module not found).

- [ ] **Step 3: Implement** — first open `components/PortfolioPanel.tsx:104-190` (`PersonalStatementSection`) and `lib/apiErrors.ts` and mirror their fetch/`detailMessage` call signature exactly:

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { detailMessage } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";

// ENH-013 -- the Career Counselor's Career Passport goal editor (spec §6.2/§8). Same interaction shape as ENH-012's
// PersonalStatementSection: an in-flight guard, no optimistic UI, the server's own message on failure, router.refresh() on success.
const MAX = 120;

export default function CareerGoalForm({ studentId, goal }: { studentId: string; goal: string | null }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(goal ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const inFlight = useRef(false);

  function open() { setValue(goal ?? ""); setError(null); setSaved(false); setEditing(true); refocus("career-goal-input"); }
  function close() { setEditing(false); refocus("career-goal-edit"); }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/school/students/${studentId}/career-goal`, {
        method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ career_goal: value }),
      });
      if (!res.ok) {
        setError(await detailMessage(res));
        refocus("career-goal-input");
        return;
      }
      setSaved(true);
      setEditing(false);
      router.refresh();
      refocus("career-goal-edit");
    } catch {
      setError("Could not reach the server. Check your connection and try again.");
      refocus("career-goal-input");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  if (!editing) {
    return (
      <>
        <p>{goal ?? <span className="muted">No career goal set yet.</span>}</p>
        <button id="career-goal-edit" type="button" className="btn secondary small" onClick={open}>{goal ? "Edit career goal" : "Set career goal"}</button>
        {saved ? <p className="form-message" role="status">Career goal saved.</p> : null}
      </>
    );
  }
  return (
    <form onSubmit={save} className="field">
      <label htmlFor="career-goal-input">Career goal</label>
      <input
        id="career-goal-input" value={value} maxLength={MAX} aria-describedby="career-goal-count"
        onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); close(); } }}
      />
      <span id="career-goal-count" className="muted">{value.length}/{MAX}</span>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <div style={{ display: "flex", gap: 8 }}>
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        <button type="button" className="btn ghost small" onClick={close} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}
```

If `detailMessage` has a different signature (e.g. takes parsed JSON), adapt the one call site, keeping behavior.

- [ ] **Step 4: Run** — `npx vitest run tests/components/CareerGoalForm.test.tsx tests/components/Student360Panels.test.tsx tests/lib/clientBoundary.test.ts` → PASS.

- [ ] **Step 5: Commit** — `feat(enh-013): counsellor career-goal form`

---

### Task 12: Routes, loading states, entry links

**Files:**
- Create (7 × page + loading): `apps/web/app/school/{coordinator,principal,teacher}/students/[id]/360/{page,loading}.tsx`, `apps/web/app/school/parent/children/[id]/360/{page,loading}.tsx`, `apps/web/app/school/{academic-team,career-counselor,psychometric-team}/students/[id]/360/{page,loading}.tsx`
- Create: `apps/web/components/Student360Directory.tsx`
- Modify: `apps/web/components/SchoolStudentDetailPanel.tsx` (+ `role` prop, link), the three `students/[id]/page.tsx` (pass `role`), `apps/web/app/school/parent/children/[id]/page.tsx` (+ link), three service dashboards (+ directory)
- Test: `apps/web/tests/components/Student360Page.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }), usePathname: () => "/x" }));
const serverApi = vi.fn();
vi.mock("@/lib/api", () => ({ serverApi, ApiError: class extends Error { status = 403; } }));

import Page from "@/app/school/teacher/students/[id]/360/page";
import Student360Directory from "@/components/Student360Directory";

afterEach(() => { cleanup(); serverApi.mockReset(); });

describe("360 route", () => {
  it("shows Access unavailable with the server's own message when the API refuses", async () => {
    serverApi.mockImplementation((path: string) => path.endsWith("/auth/me") ? Promise.resolve({ role: "school_teacher", full_name: "T" }) : Promise.reject(new Error("This student is not assigned to you")));
    render(await Page({ params: Promise.resolve({ id: "s1" }), searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { name: /access unavailable/i })).toBeInTheDocument();
    expect(screen.getByText("This student is not assigned to you")).toBeInTheDocument();
  });
});

describe("Student360Directory", () => {
  it("links each portfolio student to the role's 360 route", () => {
    render(<Student360Directory role="psychometric_team" students={[{ id: "a", full_name: "Asha", school_id: "x", school_name: "North" }]} />);
    expect(screen.getByRole("link", { name: /asha/i })).toHaveAttribute("href", "/school/psychometric-team/students/a/360");
  });
  it("has an empty state", () => {
    render(<Student360Directory role="psychometric_team" students={[]} />);
    expect(screen.getByText(/no students in your portfolio yet/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** — FAIL (modules not found).

- [ ] **Step 3: Implement**

Teacher route (`app/school/teacher/students/[id]/360/page.tsx`); the other six differ only in the constants noted below:

```tsx
import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import Student360View from "@/components/Student360View";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import { loadStudent360, type Student360 } from "@/lib/student360";
import type { User } from "@/lib/types";

// ENH-013 -- Teacher's Student 360° view (assigned students only; the API enforces it, spec §6.1).
export default async function SchoolTeacherStudent360Page({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ tab?: string }> }) {
  const [{ id }, { tab }] = await Promise.all([params, searchParams]);
  let user: User;
  let data: Student360;
  try {
    [user, data] = await Promise.all([serverApi<User>("/api/v1/auth/me"), loadStudent360(id)]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.teacher} roleLabel="Teacher" userName={user.full_name}>
      <Student360View data={data} initialTab={tab} backHref={`/school/teacher/students/${id}`} backLabel="Back to student" />
    </PortalShell>
  );
}
```

| Route | nav key | roleLabel | backHref |
|---|---|---|---|
| coordinator | `coordinator` | School Coordinator | `/school/coordinator/students/${id}` |
| principal | `principal` | Principal | `/school/principal/students/${id}` |
| teacher | `teacher` | Teacher | `/school/teacher/students/${id}` |
| parent (`children/[id]/360`) | `parent` | Parent | `/school/parent/children/${id}` |
| academic-team | `"academic-team"` | Academic Team | `/school/academic-team/dashboard` |
| career-counselor | `"career-counselor"` | Career Counselor | `/school/career-counselor/dashboard` |
| psychometric-team | `"psychometric-team"` | Psychometric Team | `/school/psychometric-team/dashboard` |

Each route's `loading.tsx` (same shape as `app/school/parent/children/[id]/loading.tsx`, with that route's nav/role):

```tsx
import PortalShell from "@/components/PortalShell";
import { SCHOOL_NAV } from "@/lib/navigation";

export default function Loading() {
  return (
    <PortalShell nav={SCHOOL_NAV.teacher} roleLabel="Teacher" userName="">
      <div className="portal-content" aria-busy="true" aria-label="Loading the student 360° view">
        <div className="card"><div className="skeleton-line" style={{ marginBottom: 10 }} /><div className="skeleton-line" style={{ width: "40%" }} /></div>
        <div className="s360-layout">
          <div className="card">{Array.from({ length: 6 }, (_, i) => <div key={i} className="skeleton-line" style={{ marginBottom: 8 }} />)}</div>
          <div className="card"><div className="skeleton-line" style={{ marginBottom: 10 }} /><div className="skeleton-line" /></div>
        </div>
      </div>
    </PortalShell>
  );
}
```

`Student360Directory.tsx`:

```tsx
import type { PortfolioStudent } from "@/lib/skills";
import { student360Href } from "@/lib/student360Links";

// ENH-013 -- the service roles' way into a student's 360° view: their own portfolio's students (from /portfolio-students).
export default function Student360Directory({ role, students }: { role: string; students: PortfolioStudent[] }) {
  return (
    <div className="card">
      <h2>Student 360° view</h2>
      {students.length === 0 ? (
        <p className="empty" role="status">No students in your portfolio yet.</p>
      ) : (
        <ul className="s360-list">
          {students.map((s) => <li key={s.id}><a href={student360Href(role, s.id) ?? "#"}>{s.full_name}</a> <span className="muted">{s.school_name}</span></li>)}
        </ul>
      )}
    </div>
  );
}
```

Add `<Student360Directory role="career_counselor" students={students} />` (and the `academic_team` / `psychometric_team` equivalents) after the existing panel in each service dashboard; wrap both in a fragment. The data is already fetched there.

`SchoolStudentDetailPanel.tsx`: add prop `role: string` and, next to the back link in the header card:

```tsx
<a className="btn" href={student360Href(role, student.id) ?? "#"}>Open 360° view</a>
```

(import `student360Href` from `@/lib/student360Links`); pass `role="school_coordinator"` / `"school_principal"` / `"school_teacher"` from the three `students/[id]/page.tsx` files. Parent child page: add `<a className="btn" href={`/school/parent/children/${id}/360`}>Open 360° view</a>` next to "Back to my children".

- [ ] **Step 4: Run** — `npx vitest run` (whole web unit suite, to catch the changed `SchoolStudentDetailPanel` signature) → PASS; `npx tsc --noEmit` → clean.

- [ ] **Step 5: Commit** — `feat(enh-013): per-role 360 routes, loading states and entry links`

---

### Task 13: Playwright E2E

**Files:**
- Create: `apps/web/tests/e2e/enh-013-student-360.spec.ts`

- [ ] **Step 1: Read `apps/web/tests/e2e/enh-012-digital-portfolio.spec.ts` and `tests/helpers/`** for the login/seed helpers used to create a school, staff and students via the API, then write the spec:

Scenarios (one `test` each):
1. AC-01: coordinator opens `/school/coordinator/students/{id}` → clicks "Open 360° view" → 16 tabs visible; clicking "Certificates" shows the seeded certificate; URL has `?tab=certificates`.
2. AC-02: teacher navigates to an unassigned student's `/360` → heading "Access unavailable", text "This student is not assigned to you".
3. AC-04: a newly created student → every tab except Personal Details shows an empty-state `role=status`; no error text.
4. Counselor sets "Technology" on the Overview tab → parent opens own child's `/360` → sees "Technology".
5. Psychometric Team → "English Testing" tab shows "not available for your role".
6. Keyboard: focus the selected tab, press ArrowDown ×3, Enter; the 4th tab is selected and its panel visible; Tab moves focus into the panel.
7. Mobile 390×844: no horizontal page scroll (`document.documentElement.scrollWidth <= innerWidth`), tablist scrolls horizontally.

- [ ] **Step 2: Run against the running stack** — `npx playwright test tests/e2e/enh-013-student-360.spec.ts` → all PASS (user must have the docker stack + web dev server up).

- [ ] **Step 3: Commit** — `test(enh-013): end-to-end 360 view journeys`

---

### Task 14: Docs, full regression, and hand-off (not completion)

- [ ] **Step 1:** `docs/quality/RTM.md`: ENH-013a row (Evidence → Decision D1–D12 → AC-01..12 → tests → files).
- [ ] **Step 2:** Screen catalogue: 7 `/360` routes + the directory card.
- [ ] **Step 3:** `docs/delivery/RAID.md`: new issue, "SCH-005 `report_url` accepts any string at write time (no scheme validation); ENH-013 renders it safely via `safeHref`, but the write path itself remains unvalidated."
- [ ] **Step 4:** `docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-013: note the 013a/013b split, the 15-vs-16 tab and grade/section source inconsistencies, and the D8 parent-communication decision.
- [ ] **Step 5:** Full regression (the 3–4-feature cadence is due, and shared helpers changed): `python -m pytest -q` (apps/api), `npx vitest run`, `npx tsc --noEmit`, `npx playwright test`. Record the pass counts.
- [ ] **Step 6:** Commit — `docs(enh-013): RTM, screen catalogue, RAID finding, backlog note`.
- [ ] **Step 7:** Report status as **implemented, pending browser validation and independent Codex review** — do not mark ENH-013 complete.

---

## Self-review

- Spec coverage: §5 → T3; §6.1 → T5; §6.2 → T4/T7; §6.3 → T5/T6; §6.4 → T5 (`NOT_TRACKED`); §7 → T1/T2; §8 → T8–T12; §9 (XSS, IDOR, mass assignment, logs) → T5/T6/T7/T8/T10; §10 AC-01..12 → T5, T6, T7, T9, T10, T13; §11 → all test files; §12 regression → T2/T14; §13 docs → T14.
- AC-04 nuance: `personal_details` is always `has_data` (identity always exists) and `overview`/`academic_records` still render their body when empty; recorded in T5's test and T10's `alwaysShowBody`.
- Type consistency: `TAB_360_KEYS` (py) ↔ `TAB_KEYS` (ts) same 16 in the same order; `Tab360` shape identical on both sides; `student360Href(role, id)` used by T10/T12.
