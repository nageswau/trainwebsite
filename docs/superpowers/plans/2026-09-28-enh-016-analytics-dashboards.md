# ENH-016 School & Edusphere Analytics Dashboards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Role-scoped, read-only dashboards for `School CRM.md` §1, §27, §28, §29, §34 and Part B §14, computed live from existing School-domain rows.

**Architecture:** One new module `apps/api/app/api/school_analytics.py` (a `/school` router + an `/overseas-admin` router, the ENH-018 shape) with grouped SQL aggregation over a *student scope* (`select` of ids or a list), so every endpoint runs a fixed number of queries. `schools.py` gains a batched `service_usage()` (extracted from `/school/entitlements`) and the D8/D11 dashboard fixes; `portfolio.py` exposes ENH-012's completion formula as a pure helper; `school_skills.py` gains `skill_usage_many()`. Frontend adds five server-rendered presentational components on existing pages plus one admin page. No migration, no dependency, no writes.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 async + asyncpg, pytest/pytest-asyncio/httpx; Next.js App Router, React, vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-28-enh-016-analytics-dashboards-design.md`

## Global Constraints

- Read-only: no `db.add`, `flush` or `commit` anywhere in ENH-016 code; no migration; no model change; no new dependency (backend or frontend).
- Existing responses change only as spec §5: `digital_portfolios_created` tracked (D11 count), `skills_training` removed from `untracked_charts` and added as a key, `/school/entitlements` `digital_portfolio_creation.used` = D11 count. Nothing renamed or removed.
- Roles: school analytics `school_coordinator`, `school_principal` (via `school_feedback._require_school_reader`); cross-school `overseas_admin`, `super_admin` (new `_require_school_admin`). Never `ensure_admin`.
- School id only from `_own_school_id(user)`; no school/role/user id request parameter anywhere.
- Paging: `limit=Query(25, ge=1, le=100)`, `offset=Query(0, ge=0)`, body `{items, total, limit, offset}`; stable order `full_name`/`name`, then `id`.
- Thresholds: `at_risk_below=Query(40, ge=0, le=100)`, `top_from=Query(85, ge=0, le=100)`; `at_risk_below >= top_from` → 422 `"at_risk_below must be less than top_from"`.
- `detail` strings (exact): `"Student not found"`, `"Overseas Admin role required"`, `"at_risk_below must be less than top_from"`; existing `"School Coordinator or Principal role required"`, `"This account is not linked to a school"` reused.
- Academic figures use `status == "published"` rows only.
- Logs: one `logger.info("school_analytics_view", …)` per request with `actor_id`, `role`, `view`, and `school_id` or `school_count` — never names, marks or free text. No `AuditLog` for reads.
- Grade columns: `"8"…"12"`, plus `"other"` (a `grade_level` outside 8–12) and `"unspecified"` (no grade), each only when non-zero. *(Refines spec §6.2, which only named `unspecified`; Task 5 updates the spec text.)*
- Backend DB tests need the Postgres stack (user-run `docker compose up`, per project practice the user starts it) with `alembic upgrade head` applied. Run backend tests with `cd apps/api && python -m pytest <file> -q`; web unit tests with `cd apps/web && npx vitest run <file>`; e2e with `cd apps/web && npx playwright test <spec>`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A school with **zero students** (new partner) must return 200 with zeros/empty lists and `null` percentages on every endpoint, never 500 or divide-by-zero — pinned in Tasks 5, 6, 7, 8.
2. A student whose `grade_level` is NULL but `grade_or_class` says "Class 10" must land in column `"10"`; one in grade 5 in `"other"` — pinned in Task 5.
3. A personal statement of only whitespace/newlines must **not** count as a started portfolio (ENH-012 uses Python `strip()`) — pinned in Task 2.
4. `offset` beyond the last page returns an empty `items` with the true `total`, and the UI shows "No students match this grade." with a Previous link — pinned in Tasks 7 and 11.
5. A partnership whose `tier_valid_until` was yesterday counts as renewal due (expired included), and a school with `tier = NULL` shows 0 included services and `utilization_pct = null` — pinned in Task 8.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/app/api/school_analytics.py` (new) | Student-scope primitives, indicators, the six ENH-016 routes, role dependency, logging |
| `apps/api/app/api/schools.py` | `service_usage()` (extracted), `_school_account_counts()` (extracted), D8/D11 dashboard fields |
| `apps/api/app/api/portfolio.py` | `portfolio_completion()` pure helper; `portfolio_payload` calls it |
| `apps/api/app/api/school_skills.py` | `skill_usage_many()`; `skill_usage` delegates |
| `apps/api/app/schemas.py` | ENH-016 response models |
| `apps/api/app/main.py` | register the two routers |
| `apps/api/tests/enh016_helpers.py` (new) | test builders |
| `apps/api/tests/test_enh_016_*.py` (new) | API tests per task |
| `apps/web/lib/types.ts` | response types |
| `apps/web/components/SectionUnavailable.tsx` (new) | shared per-section error card |
| `apps/web/components/SchoolKpiBoard.tsx` (new) | §1 KPI board |
| `apps/web/components/SchoolGradePerformance.tsx` (new) | §29 |
| `apps/web/components/SchoolStudentDevelopment.tsx` (new) | Part B §14 |
| `apps/web/components/StudentScorecard.tsx` (new) | §28 card + `ScorecardStateBadge` |
| `apps/web/components/SchoolScorecardGrid.tsx` (new) | §28 grid |
| `apps/web/components/CrossSchoolAnalytics.tsx` (new) | §34 + §27 table |
| `apps/web/app/school/{coordinator,principal}/…` | dashboards, reports, student pages |
| `apps/web/app/overseas/admin/school-analytics/{page,loading}.tsx` (new) | admin page |
| `apps/web/lib/navigation.ts`, `apps/web/app/globals.css` | nav items, styles |
| `apps/web/tests/components/*.test.tsx` (new) | component tests |
| `apps/web/tests/e2e/enh-016-analytics.spec.ts` (new) | browser flow |

---

### Task 1: Extract ENH-012's completion formula (`portfolio_completion`)

**Files:**
- Modify: `apps/api/app/api/portfolio.py:91-133`
- Test: `apps/api/tests/test_enh_016_portfolio_completion.py`

**Interfaces:**
- Produces: `portfolio_completion(*, profile_complete: bool, has_academic: bool, has_psychometric: bool, has_career: bool, has_language: bool, sections: Collection[str], has_statement: bool) -> int`

- [ ] **Step 1: Write the failing test**

```python
"""ENH-016 Task 1 -- ENH-012's completion formula as a pure helper, so the scorecard (§28) can compute it in bulk without
drifting from GET /school/students/{id}/portfolio (spec §6.3, AC14)."""

from app.api.portfolio import portfolio_completion
from app.schemas import PORTFOLIO_SECTIONS

BASE = dict(profile_complete=False, has_academic=False, has_psychometric=False, has_career=False, has_language=False, sections=set(), has_statement=False)
TOTAL = 5 + len(PORTFOLIO_SECTIONS) + 1


def test_empty_portfolio_is_zero():
    assert portfolio_completion(**BASE) == 0


def test_everything_present_is_100():
    assert portfolio_completion(**{**BASE, "profile_complete": True, "has_academic": True, "has_psychometric": True, "has_career": True, "has_language": True, "sections": set(PORTFOLIO_SECTIONS), "has_statement": True}) == 100


def test_each_component_weighs_the_same_and_unknown_sections_are_ignored():
    assert portfolio_completion(**{**BASE, "profile_complete": True}) == round(1 / TOTAL * 100)
    assert portfolio_completion(**{**BASE, "sections": {"project", "not-a-section"}}) == round(1 / TOTAL * 100)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_enh_016_portfolio_completion.py -q`
Expected: FAIL — `ImportError: cannot import name 'portfolio_completion'`

- [ ] **Step 3: Implement** — in `portfolio.py`, add above `portfolio_payload` and replace its inline formula:

```python
from collections.abc import Collection


def portfolio_completion(*, profile_complete: bool, has_academic: bool, has_psychometric: bool, has_career: bool, has_language: bool, sections: Collection[str], has_statement: bool) -> int:
    """ENH-012's completion percentage, extracted unchanged from `portfolio_payload` so ENH-016's scorecard computes the same
    number in bulk (spec §6.3). One equal-weight component each; a section counts once it has any entry, unknown sections never."""
    components = [profile_complete, has_academic, has_psychometric, has_career, has_language, *(s in sections for s in PORTFOLIO_SECTIONS), has_statement]
    return round(sum(components) / len(components) * 100)
```

and inside `portfolio_payload` replace the `completion_components = [...]` / `completion_percentage = …` lines with:

```python
    completion_percentage = portfolio_completion(
        profile_complete=profile_complete, has_academic=bool(academic), has_psychometric=bool(psychometric), has_career=bool(career),
        has_language=bool(languages), sections={s for s, rows in entries_by_section.items() if rows},
        has_statement=bool(personal_statement and personal_statement.strip()),
    )
```

- [ ] **Step 4: Run the new test and ENH-012/ENH-013 regressions**

Run: `cd apps/api && python -m pytest tests/test_enh_016_portfolio_completion.py tests/test_enh_012_digital_portfolio.py tests/test_enh_013_360_view.py -q`
Expected: all PASS (if the ENH-012 test file has a different name, run `python -m pytest -q -k "enh_012 or enh_013"`).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/portfolio.py apps/api/tests/test_enh_016_portfolio_completion.py
git commit -m "refactor(enh-016): extract ENH-012 portfolio completion formula"
```

---

### Task 2: Analytics module skeleton, student scope and portfolio/skill primitives

**Files:**
- Create: `apps/api/app/api/school_analytics.py`
- Create: `apps/api/tests/enh016_helpers.py`
- Test: `apps/api/tests/test_enh_016_primitives.py`

**Interfaces:**
- Produces: `students_in(school_ids: Collection[UUID]) -> Select`; `Scope = Select | Collection[UUID]`; `async portfolio_sections(db, scope) -> dict[UUID, set[str]]`; `async statement_ids(db, scope) -> set[UUID]`; `async portfolio_started_ids(db, scope) -> set[UUID]`; `async skill_statuses(db, scope) -> dict[str, dict[UUID, list[str]]]` (keys `"soft_skills"`, `"digital_skills"`); test helpers `make_school`, `make_student`, `login`, `make_university`.

- [ ] **Step 1: Write the helpers**

```python
"""ENH-016 test builders. Every school/user/student gets a random suffix, so tests never collide on the shared database."""

import uuid

from app.core.identifiers import unique_student_code
from app.core.security import hash_password
from app.models import Country, School, SchoolStudent, University, User, UserRoleAssignment

PASSWORD = "Sup3r-Secret-Pass!"
SCHOOL_ROLES = ("school_coordinator", "school_principal", "school_teacher", "school_parent")
OTHER_ROLES = {"academic_team": "overseas", "career_counselor": "overseas", "psychometric_team": "overseas", "overseas_admin": "overseas", "super_admin": "global", "it_admin": "it"}


def _user(role: str, division: str, school_id=None) -> User:
    return User(
        email=f"enh016-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name=f"Test {role}",
        role=role, division=division, active=True, profile={"school_id": str(school_id)} if school_id else {},
    )


async def make_school(db, *, tier: str | None = "platinum", **fields) -> dict:
    """A school plus one account per school role (linked by profile.school_id) and one per Edusphere role. Not committed."""
    ctx: dict = {name: _user(name, division) for name, division in OTHER_ROLES.items()}
    db.add_all(ctx.values())
    await db.flush()
    school = School(name=fields.pop("name", f"ENH016 School {uuid.uuid4().hex[:6]}"), created_by_user_id=ctx["overseas_admin"].id, tier=tier, **fields)
    db.add(school)
    await db.flush()
    ctx["school"] = school
    for role in SCHOOL_ROLES:
        user = _user(role, "overseas", school.id)
        db.add(user)
        await db.flush()
        db.add(UserRoleAssignment(user_id=user.id, division="overseas", role=role, is_active=True, assigned_by_user_id=ctx["overseas_admin"].id, approval_status="approved"))
        ctx[role] = user
    await db.flush()
    return ctx


async def make_student(db, ctx: dict, *, name: str | None = None, grade_level: int | None = None, grade_or_class: str | None = None, **fields) -> SchoolStudent:
    student = SchoolStudent(
        school_id=ctx["school"].id, student_code=await unique_student_code(db, SchoolStudent.student_code), full_name=name or f"Student {uuid.uuid4().hex[:6]}",
        grade_level=grade_level, grade_or_class=grade_or_class, created_by_user_id=ctx["school_coordinator"].id, **fields,
    )
    db.add(student)
    await db.flush()
    return student


async def make_university(db) -> University:
    suffix = uuid.uuid4().hex[:8]
    country = Country(slug=f"enh016-c-{suffix}", name="C", overview="o", tuition="t", living_expenses="l", visa_process=[], work_opportunities="w", post_study_work="p", pr_opportunities="r", faq=[])
    db.add(country)
    await db.flush()
    university = University(country_id=country.id, slug=f"enh016-u-{suffix}", name="U", city="c", overview="o", eligibility="e", requirements=[], deadlines=[], scholarships=[])
    db.add(university)
    await db.flush()
    return university


async def login(client, user: User) -> None:
    division = "it" if user.division == "it" else "overseas"
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD, "division": division})
    assert response.status_code == 200, response.text
```

- [ ] **Step 2: Write the failing test**

```python
"""ENH-016 Task 2 -- scope primitives: D11 'portfolio started' and ENH-011 skill statuses per student (spec §6.1, AC13)."""

from datetime import date

import pytest

from app.api.school_analytics import portfolio_started_ids, skill_statuses, students_in
from app.models import PortfolioEntry, PortfolioProfile, SchoolSkillBatch, SchoolSkillEnrollment
from tests.enh016_helpers import make_school, make_student


@pytest.mark.asyncio
async def test_portfolio_started_counts_entries_and_non_blank_statements_only(db_session):
    ctx = await make_school(db_session)
    coord = ctx["school_coordinator"].id
    profile_only = await make_student(db_session, ctx, grade_level=9, grade_or_class="Grade 9")  # has DOB/grade only
    with_entry = await make_student(db_session, ctx)
    with_statement = await make_student(db_session, ctx)
    blank_statement = await make_student(db_session, ctx)
    db_session.add_all([
        PortfolioEntry(school_student_id=with_entry.id, section="project", title="Robot", created_by_user_id=coord, updated_by_user_id=coord),
        PortfolioProfile(school_student_id=with_statement.id, personal_statement="I love physics."),
        PortfolioProfile(school_student_id=blank_statement.id, personal_statement=" \n\t "),
    ])
    await db_session.flush()

    started = await portfolio_started_ids(db_session, students_in([ctx["school"].id]))

    assert started == {with_entry.id, with_statement.id}
    assert profile_only.id not in started and blank_statement.id not in started
    await db_session.rollback()


@pytest.mark.asyncio
async def test_skill_statuses_group_non_withdrawn_enrolments_by_module(db_session):
    ctx = await make_school(db_session)
    a = await make_student(db_session, ctx)
    b = await make_student(db_session, ctx)
    soft = SchoolSkillBatch(school_id=ctx["school"].id, module_type="soft_skills", title="Soft", start_date=date(2026, 1, 1), created_by_user_id=ctx["career_counselor"].id)
    digital = SchoolSkillBatch(school_id=ctx["school"].id, module_type="digital_skills", title="Web", start_date=date(2026, 1, 1), created_by_user_id=ctx["career_counselor"].id)
    db_session.add_all([soft, digital])
    await db_session.flush()
    enrol = ctx["career_counselor"].id
    db_session.add_all([
        SchoolSkillEnrollment(batch_id=soft.id, school_student_id=a.id, status="completed", enrolled_by_user_id=enrol),
        SchoolSkillEnrollment(batch_id=digital.id, school_student_id=a.id, status="withdrawn", enrolled_by_user_id=enrol),
        SchoolSkillEnrollment(batch_id=digital.id, school_student_id=b.id, status="enrolled", enrolled_by_user_id=enrol),
    ])
    await db_session.flush()

    statuses = await skill_statuses(db_session, [a.id, b.id])

    assert statuses["soft_skills"] == {a.id: ["completed"]}
    assert statuses["digital_skills"] == {b.id: ["enrolled"]}
    await db_session.rollback()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_enh_016_primitives.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.school_analytics'`

- [ ] **Step 4: Implement the module skeleton**

```python
"""ENH-016 -- School & Edusphere analytics dashboards (docs/superpowers/specs/2026-09-28-enh-016-analytics-dashboards-design.md).

Read-only aggregations for `School CRM.md` §1/§27/§28/§29/§34 and Part B §14. Two routers, like `school_feedback.py`, so
`schools.py` and `admin.py` do not grow. Every query filters on a *student scope* -- a `select` of student ids or a plain id
list -- and groups in SQL, so an endpoint runs the same number of queries for one school or for all of them (spec §10).
Nothing here writes: no add, flush or commit."""

from collections import defaultdict
from collections.abc import Collection
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import Select, func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import PortfolioEntry, PortfolioProfile, SchoolSkillBatch, SchoolSkillEnrollment, SchoolStudent

school_router = APIRouter(prefix="/school", tags=["school-analytics"])
admin_router = APIRouter(prefix="/overseas-admin", tags=["school-analytics"])
logger = get_logger("app.school.analytics")

Scope = Select | Collection[UUID]
BLANKS = " \t\r\n\f\v"  # what Python's str.strip() removes for ASCII -- ENH-012 treats a whitespace-only statement as empty


def students_in(school_ids: Collection[UUID]) -> Select:
    return select(SchoolStudent.id).where(SchoolStudent.school_id.in_(list(school_ids)))


async def portfolio_sections(db: AsyncSession, scope: Scope) -> dict[UUID, set[str]]:
    rows = await db.execute(select(PortfolioEntry.school_student_id, PortfolioEntry.section).where(PortfolioEntry.school_student_id.in_(scope)).distinct())
    out: dict[UUID, set[str]] = defaultdict(set)
    for student_id, section in rows.tuples():
        out[student_id].add(section)
    return out


async def statement_ids(db: AsyncSession, scope: Scope) -> set[UUID]:
    stmt = select(PortfolioProfile.school_student_id).where(
        PortfolioProfile.school_student_id.in_(scope), func.length(func.btrim(PortfolioProfile.personal_statement, BLANKS)) > 0
    )
    return set((await db.scalars(stmt)).all())


async def portfolio_started_ids(db: AsyncSession, scope: Scope) -> set[UUID]:
    """D11: at least one portfolio entry, or a non-blank personal statement. Profile fields alone never count. One query."""
    entries = select(PortfolioEntry.school_student_id).where(PortfolioEntry.school_student_id.in_(scope))
    statements = select(PortfolioProfile.school_student_id).where(
        PortfolioProfile.school_student_id.in_(scope), func.length(func.btrim(PortfolioProfile.personal_statement, BLANKS)) > 0
    )
    return set((await db.scalars(union(entries, statements))).all())


async def skill_statuses(db: AsyncSession, scope: Scope) -> dict[str, dict[UUID, list[str]]]:
    """Non-withdrawn ENH-011 enrolment statuses per module and student -- the input `school_skills._rollup` expects."""
    rows = await db.execute(
        select(SchoolSkillEnrollment.school_student_id, SchoolSkillBatch.module_type, SchoolSkillEnrollment.status)
        .join(SchoolSkillBatch, SchoolSkillBatch.id == SchoolSkillEnrollment.batch_id)
        .where(SchoolSkillEnrollment.school_student_id.in_(scope), SchoolSkillEnrollment.status != "withdrawn")
    )
    out: dict[str, dict[UUID, list[str]]] = {"soft_skills": defaultdict(list), "digital_skills": defaultdict(list)}
    for student_id, module, status in rows.tuples():
        out[module][student_id].append(status)
    return {module: dict(by_student) for module, by_student in out.items()}
```

Also register the routers in `apps/api/app/main.py`: add `school_analytics` to the `from app.api import …` line and append `school_analytics.school_router, school_analytics.admin_router` to the `for r in (...)` tuple.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd apps/api && python -m pytest tests/test_enh_016_primitives.py -q`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/school_analytics.py apps/api/app/main.py apps/api/tests/enh016_helpers.py apps/api/tests/test_enh_016_primitives.py
git commit -m "feat(enh-016): analytics module skeleton with portfolio and skill primitives"
```

---

### Task 3: Batched `service_usage()` extracted from `/school/entitlements` (+ D13)

**Files:**
- Modify: `apps/api/app/api/school_skills.py:638-652` (`skill_usage`)
- Modify: `apps/api/app/api/schools.py:1020-1062` (`school_entitlements`)
- Test: `apps/api/tests/test_enh_016_contracts.py`

**Interfaces:**
- Consumes: `school_analytics.portfolio_started_ids`, `school_analytics.students_in` (lazy import inside the function — `school_analytics` imports `schools`).
- Produces: `school_skills.skill_usage_many(db, school_ids: Collection[UUID]) -> dict[UUID, dict[str, int]]`; `schools.service_usage(db, school_ids: Collection[UUID]) -> dict[UUID, dict[str, int | bool | None]]` (keys: every counted service; absent keys mean "not tracked").

- [ ] **Step 1: Write the characterization + D13 test** (it pins today's exact `used` values for every tracked service and adds D13; on `main` only the `digital_portfolio_creation` assertion fails)

```python
"""ENH-016 Task 3 -- /school/entitlements is byte-identical after the service_usage() extraction except D13 (AC11)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import (
    OverseasApplication, PortfolioEntry, SchoolActivity, SchoolCareerRecord, SchoolLanguageRecord, SchoolPsychometricRecord,
    SchoolSkillBatch, SchoolSkillEnrollment, SchoolStaffAssignment, SchoolTestPrepRecord, VisaCase,
)
from tests.enh016_helpers import login, make_school, make_student, make_university


async def _seed_every_source(db, ctx):
    s1 = await make_student(db, ctx)
    s2 = await make_student(db, ctx)
    cc, psych, acad, coord = ctx["career_counselor"].id, ctx["psychometric_team"].id, ctx["academic_team"].id, ctx["school_coordinator"].id
    school_id = ctx["school"].id
    db.add_all([
        SchoolPsychometricRecord(school_student_id=s1.id, psychometric_team_user_id=psych, assessment_type="A", status="completed"),
        SchoolPsychometricRecord(school_student_id=s2.id, psychometric_team_user_id=psych, assessment_type="A"),
        SchoolCareerRecord(school_student_id=s1.id, career_counselor_user_id=cc, record_type="counselling_note", notes="n"),
        SchoolCareerRecord(school_student_id=s1.id, career_counselor_user_id=cc, record_type="guidance_session", notes="n"),
        SchoolTestPrepRecord(school_student_id=s1.id, academic_team_user_id=acad, test_type="ielts"),
        SchoolTestPrepRecord(school_student_id=s2.id, academic_team_user_id=acad, test_type="sat"),
        SchoolTestPrepRecord(school_student_id=s2.id, academic_team_user_id=acad, test_type="sat"),
        SchoolLanguageRecord(school_student_id=s1.id, academic_team_user_id=acad, language="French"),
        SchoolActivity(school_id=school_id, title="Seminar", scheduled_at=datetime.now(UTC) - timedelta(days=1), created_by_user_id=coord, activity_type="career_seminar"),
        SchoolActivity(school_id=school_id, title="Visit", scheduled_at=datetime.now(UTC) + timedelta(days=1), created_by_user_id=coord, activity_type="campus_visit"),
        SchoolActivity(school_id=school_id, title="Free text", scheduled_at=datetime.now(UTC), created_by_user_id=coord),
        SchoolStaffAssignment(school_id=school_id, user_id=cc, assigned_by_user_id=ctx["overseas_admin"].id),
        PortfolioEntry(school_student_id=s2.id, section="award", title="Prize", created_by_user_id=coord, updated_by_user_id=coord),
    ])
    university = await make_university(db)
    application = OverseasApplication(student_id=None, school_student_id=s1.id, university_id=university.id, intake="Fall 2027", status="offer")
    db.add(application)
    await db.flush()
    db.add(VisaCase(application_id=application.id, status="checklist"))
    batch = SchoolSkillBatch(school_id=school_id, module_type="soft_skills", title="Soft", start_date=date(2026, 1, 1), created_by_user_id=cc)
    db.add(batch)
    await db.flush()
    db.add(SchoolSkillEnrollment(batch_id=batch.id, school_student_id=s2.id, enrolled_by_user_id=cc))
    await db.commit()


@pytest.mark.asyncio
async def test_entitlements_usage_is_unchanged_except_digital_portfolio(client, db_session):
    ctx = await make_school(db_session, tier="platinum")
    await _seed_every_source(db_session, ctx)
    await login(client, ctx["school_coordinator"])

    response = await client.get("/api/v1/school/entitlements")

    assert response.status_code == 200, response.text
    used = {s["key"]: s["used"] for s in response.json()["services"]}
    assert used == {
        "career_seminar": 1, "career_awareness_session": 0, "parent_orientation": 0, "psychometric_test": 2, "soft_skills": 1,
        "individual_counselling": 1, "web_designing": 0,
        "application_support": 1, "scholarship_assistance": None, "ielts_coaching": 1, "sat_coaching": 2, "foreign_language_classes": 1,
        "digital_portfolio_creation": 1,  # D13 -- was None before ENH-016
        "dedicated_counselor": True, "monthly_campus_visits": 1, "internships": None, "visa_support": 1, "loan_assistance": None,
        "alumni_network": None, "parent_help_desk": None,
    }
    assert [s["key"] for s in response.json()["services"]][:3] == ["career_seminar", "career_awareness_session", "parent_orientation"]


@pytest.mark.asyncio
async def test_service_usage_keeps_schools_apart(db_session):
    from app.api.schools import service_usage

    a = await make_school(db_session)
    b = await make_school(db_session)
    await _seed_every_source(db_session, a)

    usage = await service_usage(db_session, [a["school"].id, b["school"].id])

    assert usage[a["school"].id]["psychometric_test"] == 2
    assert usage[b["school"].id]["psychometric_test"] == 0
    assert usage[b["school"].id]["dedicated_counselor"] is False
    assert usage[b["school"].id]["digital_portfolio_creation"] == 0
    assert await service_usage(db_session, []) == {}
```

(Check `SchoolStaffAssignment`'s required columns in `models.py:1248` before running; if it has no `assigned_by_user_id`, drop that kwarg.)

- [ ] **Step 2: Run to verify the expected failure**

Run: `cd apps/api && python -m pytest tests/test_enh_016_contracts.py -q`
Expected: first test FAILS only on `digital_portfolio_creation` (`None != 1`); second FAILS with `ImportError: cannot import name 'service_usage'`. If any *other* key differs, stop: the fixture or the pinned value is wrong — fix the test to today's behaviour before changing code.

- [ ] **Step 3: Implement `skill_usage_many`** in `school_skills.py`, and make `skill_usage` delegate:

```python
async def skill_usage_many(db: AsyncSession, school_ids: Collection[UUID]) -> dict[UUID, dict[str, int]]:
    """`skill_usage` for many schools in ONE grouped query (ENH-016 §5.2): non-withdrawn enrolments per batch school and module."""
    ids = list(school_ids)
    counted: dict[UUID, dict[str, int]] = {school_id: {} for school_id in ids}
    if ids:
        rows = await db.execute(
            select(SchoolSkillBatch.school_id, SchoolSkillBatch.module_type, func.count())
            .join(SchoolSkillEnrollment, SchoolSkillEnrollment.batch_id == SchoolSkillBatch.id)
            .where(SchoolSkillBatch.school_id.in_(ids), SchoolSkillEnrollment.status != "withdrawn")
            .group_by(SchoolSkillBatch.school_id, SchoolSkillBatch.module_type)
        )
        for school_id, module, count in rows.tuples():
            counted[school_id][module] = count
    return {school_id: {key: modules.get(module, 0) for module, key in USAGE_KEYS.items()} for school_id, modules in counted.items()}


async def skill_usage(db: AsyncSession, school_id: UUID) -> dict[str, int]:
    """Non-withdrawn enrolments in this school's batches, per entitlement service key (spec §5.2)."""
    return (await skill_usage_many(db, [school_id]))[school_id]
```

(add `from collections.abc import Collection` at the top if missing.)

- [ ] **Step 4: Implement `service_usage`** in `schools.py`, directly above `school_entitlements`:

```python
async def service_usage(db: AsyncSession, school_ids: Collection[UUID]) -> dict[UUID, dict[str, int | bool | None]]:
    """DEC-SCOPE-017 usage per school and service, extracted from `school_entitlements` for ENH-016's cross-school rollup (spec
    §5.2). One grouped query per source, so the query count does not depend on how many schools are asked for. A key that is
    absent here is "not yet tracked" (`used: None`). ENH-016 D13 adds `digital_portfolio_creation` (students with a started
    portfolio, D11). No writes."""
    from app.api.school_analytics import portfolio_started_ids, students_in  # noqa: PLC0415 -- school_analytics imports this module

    ids = list(school_ids)
    if not ids:
        return {}
    usage: dict[UUID, dict[str, int | bool | None]] = {school_id: {} for school_id in ids}
    in_schools = SchoolStudent.school_id.in_(ids)

    async def _per_school(key: str, stmt) -> None:
        counts = dict((await db.execute(stmt)).tuples().all())
        for school_id in ids:
            usage[school_id][key] = counts.get(school_id, 0)

    def _student_rows(model, *conditions):
        return (
            select(SchoolStudent.school_id, func.count(model.id))
            .join(SchoolStudent, SchoolStudent.id == model.school_student_id)
            .where(in_schools, *conditions)
            .group_by(SchoolStudent.school_id)
        )

    await _per_school("psychometric_test", _student_rows(SchoolPsychometricRecord))
    await _per_school("individual_counselling", _student_rows(SchoolCareerRecord, SchoolCareerRecord.record_type == "counselling_note"))
    await _per_school("ielts_coaching", _student_rows(SchoolTestPrepRecord, SchoolTestPrepRecord.test_type == "ielts"))
    await _per_school("sat_coaching", _student_rows(SchoolTestPrepRecord, SchoolTestPrepRecord.test_type == "sat"))
    await _per_school("foreign_language_classes", _student_rows(SchoolLanguageRecord))
    await _per_school("application_support", _student_rows(OverseasApplication))
    await _per_school(
        "visa_support",
        select(SchoolStudent.school_id, func.count(VisaCase.id))
        .join(OverseasApplication, OverseasApplication.id == VisaCase.application_id)
        .join(SchoolStudent, SchoolStudent.id == OverseasApplication.school_student_id)
        .where(in_schools)
        .group_by(SchoolStudent.school_id),
    )
    activity_counts = await db.execute(
        select(SchoolActivity.school_id, SchoolActivity.activity_type, func.count())
        .where(SchoolActivity.school_id.in_(ids), SchoolActivity.activity_type.in_(list(ACTIVITY_SERVICE_KEYS)))
        .group_by(SchoolActivity.school_id, SchoolActivity.activity_type)
    )
    for school_id in ids:
        usage[school_id].update({service: 0 for service in ACTIVITY_SERVICE_KEYS.values()})
    for school_id, activity_type, count in activity_counts.tuples():
        usage[school_id][ACTIVITY_SERVICE_KEYS[activity_type]] = count
    staffed = set((await db.scalars(select(SchoolStaffAssignment.school_id).where(SchoolStaffAssignment.school_id.in_(ids)).distinct())).all())
    skills = await _skills().skill_usage_many(db, ids)
    started = await portfolio_started_ids(db, students_in(ids))
    student_school = dict((await db.execute(select(SchoolStudent.id, SchoolStudent.school_id).where(SchoolStudent.id.in_(started)))).tuples().all()) if started else {}
    for school_id in ids:
        usage[school_id]["dedicated_counselor"] = school_id in staffed
        usage[school_id].update(skills[school_id])
        usage[school_id]["digital_portfolio_creation"] = sum(1 for owner in student_school.values() if owner == school_id)
    return usage
```

(`Collection` from `collections.abc` and `func` from `sqlalchemy` — add to `schools.py` imports if not present.)

Then replace the body of `school_entitlements` after `services = _cumulative_services(...)` / the early `return` with:

```python
    usage = (await service_usage(db, [school_id]))[school_id]
    return {
        "tier": school.tier if school else None,
        "tier_valid_until": school.tier_valid_until if school else None,
        "services": [{"key": key, "label": label, "included": True, "used": usage.get(key)} for key, label in services],
    }
```

and delete the now-unused inline `_activity_count` helper and usage block.

- [ ] **Step 5: Run the new tests and the entitlement/tier/skills regressions**

Run: `cd apps/api && python -m pytest tests/test_enh_016_contracts.py tests/test_sch_011_entitlements.py tests/test_enh_022_tier_enforcement.py tests/test_enh_023_tier_change.py -q && python -m pytest -q -k enh_011`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/app/api/school_skills.py apps/api/tests/test_enh_016_contracts.py
git commit -m "refactor(enh-016): batch service_usage for entitlements; count digital portfolios (D13)"
```

---

### Task 4: §1 dashboard — portfolios and skills tracked (D8/D11), account counts extracted

**Files:**
- Modify: `apps/api/app/api/schools.py:86-94` (`UNTRACKED_*`), `:353-508` (`_school_dashboard_payload`)
- Modify: `apps/api/tests/test_sch_reports.py:300-305` (assertions that encoded the old, now-superseded untracked state — changed by approved decision D8, not to make a test pass)
- Test: `apps/api/tests/test_enh_016_contracts.py` (append)

**Interfaces:**
- Consumes: `school_analytics.portfolio_started_ids`, `skill_statuses`, `students_in`.
- Produces: `schools._school_account_counts(db, school_id) -> dict[str, int]` with keys `teachers`, `parents`, `principals`; payload keys `skills_training = {"soft_skills": int, "digital_skills": int, "total_students": int}`.

- [ ] **Step 1: Write the failing test** (append to `test_enh_016_contracts.py`)

```python
@pytest.mark.asyncio
async def test_dashboard_tracks_portfolios_and_skills_and_keeps_every_key(client, db_session):
    from app.models import PortfolioProfile

    ctx = await make_school(db_session)
    await _seed_every_source(db_session, ctx)  # s2 has a portfolio entry and a soft-skills enrolment
    only_profile = await make_student(db_session, ctx, grade_level=8, grade_or_class="Grade 8")
    db_session.add(PortfolioProfile(school_student_id=only_profile.id, personal_statement="   "))
    await db_session.commit()
    await login(client, ctx["school_principal"])

    data = (await client.get("/api/v1/school/dashboard")).json()
    kpis = {k["key"]: k for k in data["school_crm_kpis"]}

    assert kpis["digital_portfolios_created"] == {"key": "digital_portfolios_created", "label": "Digital Portfolios Created", "value": 1, "tracked": True, "note": None}
    assert kpis["internships"]["tracked"] is False
    assert data["skills_training"] == {"soft_skills": 1, "digital_skills": 0, "total_students": 3}
    assert {c["key"] for c in data["untracked_charts"]} == {"internships", "student_participation_by_program"}
    for key in ("student_count", "teacher_count", "parent_count", "principal_count", "pending_invite_count", "grade_breakdown", "career_guidance",
                "psychometric", "results_published", "activities", "attendance", "upcoming_activities", "completion", "global_education",
                "application_pipeline", "visa_status"):
        assert key in data
    assert data["teacher_count"] == 1 and data["principal_count"] == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_enh_016_contracts.py::test_dashboard_tracks_portfolios_and_skills_and_keeps_every_key -q`
Expected: FAIL — `digital_portfolios_created` value `None`, tracked `False`.

- [ ] **Step 3: Implement**

In `schools.py`:

```python
UNTRACKED_SCHOOL_DASHBOARD_KPIS = {
    "internships": "No confirmed School internship model exists yet.",
}
UNTRACKED_SCHOOL_DASHBOARD_CHARTS = [
    {"key": "internships", "label": "Internships", "note": "No confirmed School internship model exists yet."},
    {"key": "student_participation_by_program", "label": "Student participation by program", "note": "No confirmed School program-participation model exists yet."},
]
```

Add above `_school_dashboard_payload`:

```python
async def _school_account_counts(db: AsyncSession, school_id: UUID) -> dict[str, int]:
    """Teacher/parent/principal accounts of one school -- extracted unchanged from `_school_dashboard_payload` so ENH-016's
    Part B §14 headcounts use exactly the same rule (ENH-008 parent membership via links)."""
    accounts = (await db.scalars(select(User).where(User.role.in_(("school_principal", "school_teacher", "school_parent"))))).all()
    parent_ids_at_school = await _parent_ids_at_school(db, school_id)
    accounts = [a for a in accounts if _account_belongs_to_school(a, school_id=school_id, parent_ids_at_school=parent_ids_at_school)]
    return {
        "teachers": sum(1 for a in accounts if a.role == "school_teacher"),
        "parents": sum(1 for a in accounts if a.role == "school_parent"),
        "principals": sum(1 for a in accounts if a.role == "school_principal"),
    }
```

In `_school_dashboard_payload`, replace the `school_accounts = …` through `principal_count = …` lines with:

```python
    account_counts = await _school_account_counts(db, school_id)
    teacher_count, parent_count, principal_count = account_counts["teachers"], account_counts["parents"], account_counts["principals"]
```

and, after `language_students = …`, add:

```python
    from app.api.school_analytics import portfolio_started_ids, skill_statuses, students_in  # noqa: PLC0415 -- imports this module
    scope = students_in([school_id])
    portfolio_students = await portfolio_started_ids(db, scope)
    skills = await skill_statuses(db, scope)
```

In the returned dict: replace the `digital_portfolios_created` KPI with `_school_dashboard_kpi("digital_portfolios_created", "Digital Portfolios Created", len(portfolio_students))`, and add
`"skills_training": {"soft_skills": len(skills["soft_skills"]), "digital_skills": len(skills["digital_skills"]), "total_students": total_students},`.

In `tests/test_sch_reports.py` replace lines 300–305's two `digital_portfolios_created` assertions and the `untracked_charts` set with:

```python
    assert kpis["digital_portfolios_created"]["tracked"] is True  # ENH-016 D8/D11: ENH-012 portfolios are tracked now
    assert kpis["digital_portfolios_created"]["value"] == 0
    assert kpis["internships"]["tracked"] is False
    assert {stage["key"]: stage["count"] for stage in data["application_pipeline"]}["offer"] == 1
    assert data["visa_status"] == [{"status": "checklist", "count": 1}]
    assert {chart["key"] for chart in data["untracked_charts"]} == {"internships", "student_participation_by_program"}
```

- [ ] **Step 4: Run tests**

Run: `cd apps/api && python -m pytest tests/test_enh_016_contracts.py tests/test_sch_reports.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_enh_016_contracts.py apps/api/tests/test_sch_reports.py
git commit -m "feat(enh-016): track digital portfolios and skills on the school dashboard (D8, D11)"
```

---

### Task 5: Student indicators and §29 grade performance endpoint

**Files:**
- Modify: `apps/api/app/api/school_analytics.py`
- Modify: `apps/api/app/schemas.py` (append ENH-016 section)
- Modify: `docs/superpowers/specs/2026-09-28-enh-016-analytics-dashboards-design.md` §6.2 (add `other` column)
- Test: `apps/api/tests/test_enh_016_school_analytics.py`, `apps/api/tests/test_enh_016_scope.py`

**Interfaces:**
- Produces: `async student_indicators(db, scope) -> dict[str, set[UUID]]` with keys `career_any, guidance, counselling, psych_started, psych_completed, test_prep_started, test_prep_completed, ielts, sat, language_started, language_certified, soft_skills_completed, soft_skills_in_progress, digital_skills_completed, digital_skills_in_progress, skills_enrolled, portfolio_started, published_results, global, shortlisted, applied_active, offer, admitted, visa_started, awareness_attended`; `grade_key(level: int | None, label: str | None) -> str`; `_log_view(user, view, **fields) -> None`; `_require_school_admin` dependency; schemas `MetricCell`, `GradeMetricRow`, `GradePerformanceOut`.

- [ ] **Step 1: Write the failing tests**

`test_enh_016_school_analytics.py`:

```python
"""ENH-016 school-side analytics (spec §6, AC01, AC06-AC08, AC13-AC15)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    OverseasApplication, SchoolActivity, SchoolActivityAttendance, SchoolCareerRecord, SchoolPsychometricRecord, VisaCase,
)
from tests.enh016_helpers import login, make_school, make_student, make_university


@pytest.mark.asyncio
async def test_grade_performance_counts_per_grade_with_proxies_and_fallbacks(client, db_session):
    ctx = await make_school(db_session)
    g10 = await make_student(db_session, ctx, grade_level=10, grade_or_class="Grade 10-A")
    g10_label_only = await make_student(db_session, ctx, grade_level=None, grade_or_class="Class 10")  # Review Focus 2
    g5 = await make_student(db_session, ctx, grade_level=5, grade_or_class="Grade 5")
    await make_student(db_session, ctx)  # no grade at all
    cc, psych = ctx["career_counselor"].id, ctx["psychometric_team"].id
    db_session.add_all([
        SchoolCareerRecord(school_student_id=g10.id, career_counselor_user_id=cc, record_type="guidance_session", notes="n"),
        SchoolPsychometricRecord(school_student_id=g10.id, psychometric_team_user_id=psych, assessment_type="A", status="completed"),
        SchoolPsychometricRecord(school_student_id=g10_label_only.id, psychometric_team_user_id=psych, assessment_type="A", status="completed"),
    ])
    university = await make_university(db_session)
    db_session.add(OverseasApplication(student_id=None, school_student_id=g10.id, university_id=university.id, intake="Fall 2027", status="university_selection"))
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    body = (await client.get("/api/v1/school/analytics/grade-performance")).json()

    assert body["grades"] == ["10", "other", "unspecified"]
    assert body["students"] == {"10": 2, "other": 1, "unspecified": 1}
    rows = {row["key"]: row for row in body["metrics"]}
    assert rows["career_readiness"]["cells"]["10"] == {"count": 1, "pct": 50.0}
    assert rows["career_readiness"]["is_proxy"] is True and rows["career_readiness"]["definition"]
    assert rows["assessment_completion"]["cells"]["10"] == {"count": 2, "pct": 100.0}
    assert rows["assessment_completion"]["is_proxy"] is False
    assert rows["application_readiness"]["cells"]["10"]["count"] == 1
    assert rows["admissions"]["cells"]["other"] == {"count": 0, "pct": 0.0}
    assert g5.id  # used


@pytest.mark.asyncio
async def test_grade_performance_for_an_empty_school_is_empty_not_an_error(client, db_session):  # Review Focus 1
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx["school_principal"])

    response = await client.get("/api/v1/school/analytics/grade-performance")

    assert response.status_code == 200
    assert response.json()["grades"] == [] and response.json()["students"] == {}
```

`test_enh_016_scope.py`:

```python
"""ENH-016 authorization and isolation (AC02-AC05, AC16)."""

import uuid

import pytest

from tests.enh016_helpers import login, make_school, make_student

SCHOOL_ENDPOINTS = [
    "/api/v1/school/analytics/grade-performance",
    "/api/v1/school/analytics/student-development",
    "/api/v1/school/analytics/scorecards",
]
ADMIN_ENDPOINTS = ["/api/v1/overseas-admin/analytics/summary", "/api/v1/overseas-admin/analytics/schools"]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_teacher", "school_parent", "academic_team", "career_counselor", "psychometric_team", "it_admin", "overseas_admin"])
async def test_only_coordinator_and_principal_reach_school_analytics(client, db_session, role):
    ctx = await make_school(db_session)
    student = await make_student(db_session, ctx)
    await db_session.commit()
    await login(client, ctx[role])
    for path in [*SCHOOL_ENDPOINTS, f"/api/v1/school/students/{student.id}/scorecard"]:
        response = await client.get(path)
        if response.status_code == 404:  # route not built yet in this task -- later tasks make every path 403
            continue
        assert response.status_code == 403, (path, response.text)


@pytest.mark.asyncio
async def test_school_account_without_a_school_is_refused(client, db_session):
    ctx = await make_school(db_session)
    ctx["school_coordinator"].profile = {}
    await db_session.commit()
    await login(client, ctx["school_coordinator"])
    response = await client.get("/api/v1/school/analytics/grade-performance")
    assert response.status_code == 403
    assert response.json()["detail"] == "This account is not linked to a school"


@pytest.mark.asyncio
async def test_one_school_never_sees_another_schools_students(client, db_session):
    mine = await make_school(db_session)
    theirs = await make_school(db_session)
    await make_student(db_session, mine, grade_level=9)
    for _ in range(3):
        await make_student(db_session, theirs, grade_level=9)
    await db_session.commit()
    await login(client, mine["school_coordinator"])
    body = (await client.get("/api/v1/school/analytics/grade-performance")).json()
    assert body["students"] == {"9": 1}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && python -m pytest tests/test_enh_016_school_analytics.py tests/test_enh_016_scope.py -q`
Expected: FAIL — 404 on `/school/analytics/grade-performance`.

- [ ] **Step 3: Add schemas** (append to `schemas.py`)

```python
# --- ENH-016: analytics dashboards (docs/superpowers/specs/2026-09-28-enh-016-analytics-dashboards-design.md §7) ---


class MetricCell(BaseModel):
    count: int
    pct: float | None


class GradeMetricRow(BaseModel):
    key: str
    label: str
    is_proxy: bool
    definition: str | None
    cells: dict[str, MetricCell]


class GradePerformanceOut(BaseModel):
    grades: list[str]
    students: dict[str, int]
    metrics: list[GradeMetricRow]
```

- [ ] **Step 4: Implement indicators, grade key, dependencies, route** (append to `school_analytics.py`; extend its imports)

```python
from fastapi import Depends, HTTPException  # add to the fastapi import

from app.api.deps import get_current_user
from app.api.school_feedback import _require_school_reader
from app.api.school_skills import _rollup
from app.api.schools import OFFER_ONWARD_STATUSES, _grade_level_from_label, _own_school_id, _stage_at_or_after
from app.models import (  # extend
    OverseasApplication, SchoolAcademicResult, SchoolActivity, SchoolActivityAttendance, SchoolCareerRecord, SchoolLanguageRecord,
    SchoolPsychometricRecord, SchoolTestPrepRecord, User, VisaCase,
)
from app.schemas import GradeMetricRow, GradePerformanceOut, MetricCell

GRADE_COLUMNS = ["8", "9", "10", "11", "12"]
AWARENESS_ACTIVITY_TYPES = ("career_awareness_session", "career_seminar")


def grade_key(level: int | None, label: str | None) -> str:
    """`grade_level`, else the label fallback the dashboard already uses; outside 8-12 is "other", nothing is "unspecified"."""
    key = str(level) if level is not None else _grade_level_from_label(label)
    if key is None:
        return "unspecified"
    return key if key in GRADE_COLUMNS else "other"


def _ordered_grades(present: Collection[str]) -> list[str]:
    return [g for g in (*GRADE_COLUMNS, "other", "unspecified") if g in present]


def _pct(count: int, total: int) -> float | None:
    return round(count / total * 100, 1) if total else None


def _log_view(user: User, view: str, **fields) -> None:
    logger.info("school_analytics_view", extra={"extra_fields": {"actor_id": str(user.id), "role": user.role, "view": view, **{k: str(v) for k, v in fields.items()}}})


async def _require_school_admin(user: User = Depends(get_current_user)) -> User:
    """D1: the existing cross-school pair only. Not `ensure_admin`, which also admits `it_admin`."""
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    return user


async def student_indicators(db: AsyncSession, scope: Scope) -> dict[str, set[UUID]]:
    """Every §6.1 indicator as a set of student ids, in a fixed number of queries (one per source table)."""
    ind: dict[str, set[UUID]] = defaultdict(set)
    for sid, record_type in (await db.execute(select(SchoolCareerRecord.school_student_id, SchoolCareerRecord.record_type).where(SchoolCareerRecord.school_student_id.in_(scope)).distinct())).tuples():
        ind["career_any"].add(sid)
        if record_type == "guidance_session":
            ind["guidance"].add(sid)
        elif record_type == "counselling_note":
            ind["counselling"].add(sid)
    for sid, status in (await db.execute(select(SchoolPsychometricRecord.school_student_id, SchoolPsychometricRecord.status).where(SchoolPsychometricRecord.school_student_id.in_(scope)).distinct())).tuples():
        ind["psych_started"].add(sid)
        if status == "completed":
            ind["psych_completed"].add(sid)
    prep_statuses: dict[UUID, set[str]] = defaultdict(set)
    for sid, test_type, status in (await db.execute(select(SchoolTestPrepRecord.school_student_id, SchoolTestPrepRecord.test_type, SchoolTestPrepRecord.status).where(SchoolTestPrepRecord.school_student_id.in_(scope)).distinct())).tuples():
        ind["test_prep_started"].add(sid)
        ind[test_type].add(sid)  # "ielts" / "sat"
        prep_statuses[sid].add(status)
    ind["test_prep_completed"] = {sid for sid, statuses in prep_statuses.items() if statuses == {"completed"}}  # as _overview_payload
    for sid, status in (await db.execute(select(SchoolLanguageRecord.school_student_id, SchoolLanguageRecord.certification_status).where(SchoolLanguageRecord.school_student_id.in_(scope)).distinct())).tuples():
        ind["language_started"].add(sid)
        if status == "certified":
            ind["language_certified"].add(sid)
    for module, by_student in (await skill_statuses(db, scope)).items():
        for sid, statuses in by_student.items():
            ind["skills_enrolled"].add(sid)
            state = _rollup(statuses)
            if state in {"completed", "certified"}:
                ind[f"{module}_completed"].add(sid)
            elif state == "in_progress":
                ind[f"{module}_in_progress"].add(sid)
    ind["portfolio_started"] = await portfolio_started_ids(db, scope)
    ind["published_results"] = set((await db.scalars(select(SchoolAcademicResult.school_student_id).where(SchoolAcademicResult.school_student_id.in_(scope), SchoolAcademicResult.status == "published").distinct())).all())
    for sid, status, offer_url in (await db.execute(select(OverseasApplication.school_student_id, OverseasApplication.status, OverseasApplication.offer_letter_url).where(OverseasApplication.school_student_id.in_(scope)))).tuples():
        ind["global"].add(sid)
        if _stage_at_or_after(status, "university_selection"):
            ind["shortlisted"].add(sid)
        if status not in {"withdrawn", "rejected"}:
            ind["applied_active"].add(sid)
        if status in OFFER_ONWARD_STATUSES or offer_url:
            ind["offer"].add(sid)
        if status == "enrolled":
            ind["admitted"].add(sid)
    ind["visa_started"] = set((await db.scalars(select(OverseasApplication.school_student_id).join(VisaCase, VisaCase.application_id == OverseasApplication.id).where(OverseasApplication.school_student_id.in_(scope)).distinct())).all())
    ind["awareness_attended"] = set((await db.scalars(
        select(SchoolActivityAttendance.school_student_id).join(SchoolActivity, SchoolActivity.id == SchoolActivityAttendance.activity_id)
        .where(SchoolActivityAttendance.school_student_id.in_(scope), SchoolActivityAttendance.present.is_(True), SchoolActivity.activity_type.in_(AWARENESS_ACTIVITY_TYPES)).distinct()
    )).all())
    return ind


async def _roster(db: AsyncSession, school_ids: Collection[UUID]) -> list:
    return (await db.execute(select(SchoolStudent.id, SchoolStudent.school_id, SchoolStudent.grade_level, SchoolStudent.grade_or_class).where(SchoolStudent.school_id.in_(list(school_ids))))).all()


# (key, label, rule, definition-if-proxy) -- spec §6.2 (D5)
GRADE_METRICS = [
    ("career_readiness", "Career readiness", lambda i: i["guidance"] & i["psych_completed"], "Students with a career guidance session and a completed psychometric test"),
    ("assessment_completion", "Assessment completion", lambda i: i["psych_completed"], None),
    ("counselling_completion", "Counselling completion", lambda i: i["counselling"], None),
    ("skills_development", "Skills development", lambda i: i["skills_enrolled"], "Students enrolled in a soft-skills or digital-skills batch"),
    ("global_education_interest", "Global education interest", lambda i: i["global"], "Students with any overseas application"),
    ("application_readiness", "Application readiness", lambda i: i["shortlisted"], "Students whose application has reached university selection or later"),
    ("university_applications", "University applications", lambda i: i["applied_active"], None),
    ("admissions", "Admissions", lambda i: i["admitted"], None),
]


@school_router.get("/analytics/grade-performance", response_model=GradePerformanceOut)
async def grade_performance(user: User = Depends(_require_school_reader), db: AsyncSession = Depends(get_db)):
    """§29: the same metrics side by side for Grade 8 -> 12, own school only (D5 proxies are flagged)."""
    school_id = _own_school_id(user)
    roster = await _roster(db, [school_id])
    by_grade: dict[str, set[UUID]] = defaultdict(set)
    for sid, _school, level, label in roster:
        by_grade[grade_key(level, label)].add(sid)
    indicators = await student_indicators(db, students_in([school_id]))
    grades = _ordered_grades(by_grade)
    metrics = []
    for key, label, rule, definition in GRADE_METRICS:
        chosen = rule(indicators)
        cells = {g: MetricCell(count=len(by_grade[g] & chosen), pct=_pct(len(by_grade[g] & chosen), len(by_grade[g]))) for g in grades}
        metrics.append(GradeMetricRow(key=key, label=label, is_proxy=definition is not None, definition=definition, cells=cells))
    _log_view(user, "grade_performance", school_id=school_id)
    return GradePerformanceOut(grades=grades, students={g: len(by_grade[g]) for g in grades}, metrics=metrics)
```

(`get_db` from `app.core.database`.) Update spec §6.2's first line to: *"Columns: grades 8–12, plus `other` (a `grade_level` outside 8–12) and `unspecified` (no grade), each only if non-zero."*

- [ ] **Step 5: Run tests**

Run: `cd apps/api && python -m pytest tests/test_enh_016_school_analytics.py tests/test_enh_016_scope.py -q`
Expected: all PASS (scope test skips paths that still 404).

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/school_analytics.py apps/api/app/schemas.py apps/api/tests/test_enh_016_school_analytics.py apps/api/tests/test_enh_016_scope.py docs/superpowers/specs/2026-09-28-enh-016-analytics-dashboards-design.md
git commit -m "feat(enh-016): student indicators and grade-wise performance (§29)"
```

---

### Task 6: Part B §14 student development endpoint

**Files:**
- Modify: `apps/api/app/api/school_analytics.py`, `apps/api/app/schemas.py`
- Test: `apps/api/tests/test_enh_016_school_analytics.py` (append), `test_enh_016_scope.py` (append)

**Interfaces:**
- Consumes: `student_indicators`, `grade_key`, `_roster`, `schools._school_account_counts`, `schools._percentage`.
- Produces: schemas `Headcounts`, `ActivityProgressRow`, `AverageRow`, `PerformerRow`, `PerformerList`, `StudentDevelopmentOut`; constant `THRESHOLD_ORDER = "at_risk_below must be less than top_from"`; `PERFORMER_CAP = 50`.

- [ ] **Step 1: Write the failing tests** (append)

```python
from app.models import SchoolAcademicResult, SchoolLanguageRecord, SchoolTestPrepRecord  # add to imports


def _result(student, uploader, *, subject, marks, status="published", term="Term 1", year="2026-27"):
    return SchoolAcademicResult(school_student_id=student.id, academic_year=year, term=term, subject=subject, max_marks=100, marks_obtained=marks, status=status, uploaded_by_user_id=uploader)


@pytest.mark.asyncio
async def test_student_development_pending_is_total_minus_completed_and_published_only(client, db_session):
    ctx = await make_school(db_session)
    acad = ctx["academic_team"].id
    weak = await make_student(db_session, ctx, name="Asha Weak", grade_level=9)
    strong = await make_student(db_session, ctx, name="Ben Strong", grade_level=9)
    middle = await make_student(db_session, ctx, name="Cara Middle", grade_level=10)
    db_session.add_all([
        _result(weak, acad, subject="Maths", marks=30), _result(weak, acad, subject="Science", marks=35),
        _result(strong, acad, subject="Maths", marks=95), _result(strong, acad, subject="Maths", marks=20, status="draft"),  # draft ignored (AC06)
        _result(middle, acad, subject="Maths", marks=60, term="Term 2"),
        _result(middle, acad, subject="Maths", marks=10, status="withdrawn"),
        SchoolLanguageRecord(school_student_id=middle.id, academic_team_user_id=acad, language="German", certification_status="certified"),
        SchoolTestPrepRecord(school_student_id=strong.id, academic_team_user_id=acad, test_type="ielts", status="completed"),
    ])
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    body = (await client.get("/api/v1/school/analytics/student-development")).json()

    assert body["headcounts"] == {"students": 3, "teachers": 1, "parents": 1}
    rows = {r["key"]: r for r in body["activities"]}
    assert rows["foreign_language"] == {"key": "foreign_language", "label": "Foreign Language", "completed": 1, "pending": 2}
    assert rows["english_testing"]["completed"] == 1 and rows["english_testing"]["pending"] == 2
    assert all(r["completed"] + r["pending"] == 3 for r in body["activities"])  # AC08
    assert [p["full_name"] for p in body["at_risk"]["items"]] == ["Asha Weak"]
    assert body["at_risk"]["items"][0]["average_pct"] == 32.5
    assert [p["full_name"] for p in body["top_performers"]["items"]] == ["Ben Strong"]
    assert body["top_performers"]["items"][0]["average_pct"] == 95.0  # the 20-mark draft never counted
    subjects = {r["key"]: r for r in body["by_subject"]}
    assert subjects["Maths"]["count"] == 3 and subjects["Maths"]["average_pct"] == round((30 + 95 + 60) / 3, 1)
    assert [r["key"] for r in body["by_term"]] == ["2026-27 · Term 1", "2026-27 · Term 2"]
    assert {r["key"]: r["average_pct"] for r in body["by_grade"]} == {"9": 63.8, "10": 60.0}


@pytest.mark.asyncio
async def test_thresholds_are_configurable_and_validated(client, db_session):
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx["school_principal"])
    ok = await client.get("/api/v1/school/analytics/student-development", params={"at_risk_below": 50, "top_from": 90})
    assert ok.status_code == 200 and ok.json()["at_risk_below"] == 50 and ok.json()["top_from"] == 90
    assert (await client.get("/api/v1/school/analytics/student-development", params={"at_risk_below": 101})).status_code == 422
    same = await client.get("/api/v1/school/analytics/student-development", params={"at_risk_below": 60, "top_from": 60})
    assert same.status_code == 422 and same.json()["detail"] == "at_risk_below must be less than top_from"
    assert ok.json()["at_risk"] == {"items": [], "total": 0}  # empty school (Review Focus 1)
```

Append to `test_enh_016_scope.py`:

```python
@pytest.mark.asyncio
async def test_wrong_role_with_bad_thresholds_gets_403_not_422(client, db_session):  # AC07
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx["school_teacher"])
    response = await client.get("/api/v1/school/analytics/student-development", params={"at_risk_below": 999})
    assert response.status_code == 403
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && python -m pytest tests/test_enh_016_school_analytics.py tests/test_enh_016_scope.py -q`
Expected: new tests FAIL with 404.

- [ ] **Step 3: Add schemas**

```python
class Headcounts(BaseModel):
    students: int
    teachers: int
    parents: int


class ActivityProgressRow(BaseModel):
    key: str
    label: str
    completed: int
    pending: int


class AverageRow(BaseModel):
    key: str
    label: str
    average_pct: float | None
    count: int


class PerformerRow(BaseModel):
    school_student_id: UUID
    full_name: str
    grade: str
    average_pct: float
    result_count: int


class PerformerList(BaseModel):
    items: list[PerformerRow]
    total: int


class StudentDevelopmentOut(BaseModel):
    headcounts: Headcounts
    activities: list[ActivityProgressRow]
    by_grade: list[AverageRow]
    by_subject: list[AverageRow]
    by_term: list[AverageRow]
    at_risk: PerformerList
    top_performers: PerformerList
    at_risk_below: int
    top_from: int
```

- [ ] **Step 4: Implement the route**

```python
from statistics import mean

from fastapi import Query  # add to the fastapi import

from app.api.schools import _percentage, _school_account_counts  # extend

THRESHOLD_ORDER = "at_risk_below must be less than top_from"
PERFORMER_CAP = 50
DEVELOPMENT_ROWS = [  # Part B §14 table (D2: pending = total - completed)
    ("career_guidance", "Career Guidance", lambda i: i["guidance"]),
    ("psychometric_test", "Psychometric Test", lambda i: i["psych_completed"]),
    ("foreign_language", "Foreign Language", lambda i: i["language_certified"]),
    ("english_testing", "English Testing", lambda i: i["ielts"] & i["test_prep_completed"]),
    ("university_guidance", "University Guidance", lambda i: i["shortlisted"]),
]


def _average_rows(groups: dict[str, list[float]], order: list[str], label=lambda key: key) -> list[AverageRow]:
    return [AverageRow(key=k, label=label(k), average_pct=round(mean(groups[k]), 1) if groups[k] else None, count=len(groups[k])) for k in order]


@school_router.get("/analytics/student-development", response_model=StudentDevelopmentOut)
async def student_development(
    at_risk_below: int = Query(40, ge=0, le=100),
    top_from: int = Query(85, ge=0, le=100),
    user: User = Depends(_require_school_reader),
    db: AsyncSession = Depends(get_db),
):
    """Part B §14: headcounts, Completed/Pending per activity, and published-only academic performance (SCH-006-AC02)."""
    if at_risk_below >= top_from:
        raise HTTPException(422, THRESHOLD_ORDER)
    school_id = _own_school_id(user)
    students = {row.id: row for row in (await db.execute(select(SchoolStudent.id, SchoolStudent.full_name, SchoolStudent.grade_level, SchoolStudent.grade_or_class).where(SchoolStudent.school_id == school_id))).all()}
    total = len(students)
    indicators = await student_indicators(db, students_in([school_id]))
    accounts = await _school_account_counts(db, school_id)
    results = (await db.execute(
        select(SchoolAcademicResult.school_student_id, SchoolAcademicResult.academic_year, SchoolAcademicResult.term, SchoolAcademicResult.subject, SchoolAcademicResult.max_marks, SchoolAcademicResult.marks_obtained)
        .where(SchoolAcademicResult.school_student_id.in_(list(students)), SchoolAcademicResult.status == "published")
    )).all() if students else []

    per_student: dict[UUID, list[float]] = defaultdict(list)
    per_subject: dict[str, list[float]] = defaultdict(list)
    per_term: dict[str, list[float]] = defaultdict(list)
    for sid, year, term, subject, max_marks, obtained in results:
        pct = _percentage(float(max_marks), float(obtained))
        if pct is None:
            continue
        per_student[sid].append(pct)
        per_subject[subject].append(pct)
        per_term[f"{year} · {term}"].append(pct)
    averages = {sid: round(mean(values), 1) for sid, values in per_student.items()}
    per_grade: dict[str, list[float]] = defaultdict(list)
    for sid, average in averages.items():
        per_grade[grade_key(students[sid].grade_level, students[sid].grade_or_class)].append(average)

    def _performers(chosen: list[UUID]) -> PerformerList:
        rows = [PerformerRow(school_student_id=sid, full_name=students[sid].full_name, grade=grade_key(students[sid].grade_level, students[sid].grade_or_class), average_pct=averages[sid], result_count=len(per_student[sid])) for sid in chosen]
        return PerformerList(items=rows[:PERFORMER_CAP], total=len(rows))

    at_risk = sorted((sid for sid, a in averages.items() if a < at_risk_below), key=lambda sid: (averages[sid], students[sid].full_name))
    top = sorted((sid for sid, a in averages.items() if a >= top_from), key=lambda sid: (-averages[sid], students[sid].full_name))
    _log_view(user, "student_development", school_id=school_id)
    return StudentDevelopmentOut(
        headcounts=Headcounts(students=total, teachers=accounts["teachers"], parents=accounts["parents"]),
        activities=[ActivityProgressRow(key=k, label=label, completed=len(rule(indicators)), pending=total - len(rule(indicators))) for k, label, rule in DEVELOPMENT_ROWS],
        by_grade=_average_rows(per_grade, _ordered_grades(per_grade)),
        by_subject=_average_rows(per_subject, sorted(per_subject)),
        by_term=_average_rows(per_term, sorted(per_term)),
        at_risk=_performers(at_risk),
        top_performers=_performers(top),
        at_risk_below=at_risk_below,
        top_from=top_from,
    )
```

Note: `rule(indicators)` only counts students in scope, so `completed ≤ total` always holds. The 403-before-422 order holds because FastAPI resolves `Depends(_require_school_reader)` before validating `Query` params only when the dependency is declared first — keep the dependency parameter **before** the query params if the AC07 test fails, or move the range checks into the body; the test decides.

- [ ] **Step 5: Run tests**

Run: `cd apps/api && python -m pytest tests/test_enh_016_school_analytics.py tests/test_enh_016_scope.py -q`
Expected: all PASS. If `test_wrong_role_with_bad_thresholds_gets_403_not_422` fails with 422, change the two params to `at_risk_below: int = 40, top_from: int = 85` and validate in the body *after* the dependency: `if not (0 <= at_risk_below <= 100 and 0 <= top_from <= 100): raise HTTPException(422, "Thresholds must be between 0 and 100")` — and add that string to the Global Constraints list in this plan.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/school_analytics.py apps/api/app/schemas.py apps/api/tests/test_enh_016_school_analytics.py apps/api/tests/test_enh_016_scope.py
git commit -m "feat(enh-016): Part B §14 student development and academic performance"
```

---

### Task 7: §28 scorecards — bulk builder, grid and single student

**Files:**
- Modify: `apps/api/app/api/school_analytics.py`, `apps/api/app/schemas.py`
- Test: `apps/api/tests/test_enh_016_scorecard.py`, `test_enh_016_scope.py` (append)

**Interfaces:**
- Consumes: `student_indicators`, `portfolio_sections`, `statement_ids`, `portfolio.portfolio_completion`, `schools._cumulative_services`, `grade_key`.
- Produces: `ScorecardState = Literal["completed","in_progress","not_started","not_in_plan","not_tracked"]`; schemas `ScorecardArea`, `ScorecardOut`, `ScorecardPage`; `async build_scorecards(db, school_tier: str | None, students: list) -> list[ScorecardOut]`; `STUDENT_NOT_FOUND = "Student not found"`.

- [ ] **Step 1: Write the failing tests** — `test_enh_016_scorecard.py`:

```python
"""ENH-016 §28 scorecard (AC05, AC14, AC15, Review Focus 4)."""

from datetime import date

import pytest

from app.models import (
    OverseasApplication, PortfolioEntry, PortfolioProfile, SchoolCareerRecord, SchoolLanguageRecord, SchoolPsychometricRecord,
    SchoolSkillBatch, SchoolSkillEnrollment, VisaCase,
)
from tests.enh016_helpers import login, make_school, make_student, make_university


def _areas(card):
    return {a["key"]: a["state"] for a in card["areas"]}


@pytest.mark.asyncio
async def test_each_area_reports_its_state_and_plan_limits_not_started(client, db_session):
    ctx = await make_school(db_session, tier="silver")  # bronze + silver only
    s = await make_student(db_session, ctx, name="Dev", grade_level=11, grade_or_class="Grade 11", date_of_birth=date(2010, 1, 1))
    psych, cc, acad, coord = ctx["psychometric_team"].id, ctx["career_counselor"].id, ctx["academic_team"].id, ctx["school_coordinator"].id
    batch = SchoolSkillBatch(school_id=ctx["school"].id, module_type="soft_skills", title="Soft", start_date=date(2026, 1, 1), created_by_user_id=cc)
    db_session.add(batch)
    await db_session.flush()
    db_session.add_all([
        SchoolPsychometricRecord(school_student_id=s.id, psychometric_team_user_id=psych, assessment_type="A"),  # assigned -> in progress
        SchoolCareerRecord(school_student_id=s.id, career_counselor_user_id=cc, record_type="counselling_note", notes="n"),
        SchoolLanguageRecord(school_student_id=s.id, academic_team_user_id=acad, language="French", certification_status="certified"),
        SchoolSkillEnrollment(batch_id=batch.id, school_student_id=s.id, enrolled_by_user_id=cc),  # enrolled -> in progress
        PortfolioEntry(school_student_id=s.id, section="project", title="P", created_by_user_id=coord, updated_by_user_id=coord),
    ])
    university = await make_university(db_session)
    application = OverseasApplication(student_id=None, school_student_id=s.id, university_id=university.id, intake="Fall 2027", status="eligibility_evaluation")
    db_session.add(application)
    await db_session.flush()
    db_session.add(VisaCase(application_id=application.id))
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    card = (await client.get(f"/api/v1/school/students/{s.id}/scorecard")).json()

    assert _areas(card) == {
        "career_awareness": "not_started", "psychometric": "in_progress", "career_counselling": "completed", "soft_skills": "in_progress",
        "foreign_language": "completed",  # done even though not in a silver plan
        "digital_portfolio": "in_progress", "ielts_sat": "not_in_plan", "university_shortlisting": "in_progress", "scholarship": "not_tracked",
        "application": "in_progress", "visa": "in_progress", "internship": "not_tracked",
    }
    assert card["grade"] == "11" and card["full_name"] == "Dev"


@pytest.mark.asyncio
async def test_scorecard_portfolio_percentage_matches_the_portfolio_endpoint(client, db_session):  # AC14
    ctx = await make_school(db_session)
    s = await make_student(db_session, ctx, grade_or_class="Grade 9", grade_level=9, date_of_birth=date(2011, 5, 5))
    coord = ctx["school_coordinator"].id
    db_session.add_all([
        PortfolioEntry(school_student_id=s.id, section="award", title="A", created_by_user_id=coord, updated_by_user_id=coord),
        PortfolioProfile(school_student_id=s.id, personal_statement="Hello"),
        SchoolPsychometricRecord(school_student_id=s.id, psychometric_team_user_id=ctx["psychometric_team"].id, assessment_type="A"),
    ])
    await db_session.commit()
    await login(client, ctx["school_coordinator"])
    card = (await client.get(f"/api/v1/school/students/{s.id}/scorecard")).json()
    portfolio = (await client.get(f"/api/v1/school/students/{s.id}/portfolio")).json()
    assert card["portfolio_completion_pct"] == portfolio["completion_percentage"]


@pytest.mark.asyncio
async def test_grid_filters_by_grade_and_pages_stably(client, db_session):
    ctx = await make_school(db_session)
    for name in ("Cy", "Ab", "Bo"):
        await make_student(db_session, ctx, name=name, grade_level=10)
    await make_student(db_session, ctx, name="Zed", grade_level=12)
    await db_session.commit()
    await login(client, ctx["school_principal"])

    first = (await client.get("/api/v1/school/analytics/scorecards", params={"grade": 10, "limit": 2})).json()
    second = (await client.get("/api/v1/school/analytics/scorecards", params={"grade": 10, "limit": 2, "offset": 2})).json()
    beyond = (await client.get("/api/v1/school/analytics/scorecards", params={"grade": 10, "offset": 50})).json()

    assert [c["full_name"] for c in first["items"]] == ["Ab", "Bo"] and first["total"] == 3
    assert [c["full_name"] for c in second["items"]] == ["Cy"]
    assert beyond == {"items": [], "total": 3, "limit": 25, "offset": 50}  # Review Focus 4
    assert (await client.get("/api/v1/school/analytics/scorecards", params={"grade": 7})).status_code == 422
```

Append to `test_enh_016_scope.py`:

```python
@pytest.mark.asyncio
async def test_scorecard_of_another_schools_student_is_the_same_404_as_a_missing_one(client, db_session):  # AC05
    mine = await make_school(db_session)
    theirs = await make_school(db_session)
    foreign = await make_student(db_session, theirs)
    await db_session.commit()
    await login(client, mine["school_coordinator"])
    other = await client.get(f"/api/v1/school/students/{foreign.id}/scorecard")
    missing = await client.get(f"/api/v1/school/students/{uuid.uuid4()}/scorecard")
    assert other.status_code == missing.status_code == 404
    assert other.json() == missing.json() == {"detail": "Student not found"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && python -m pytest tests/test_enh_016_scorecard.py tests/test_enh_016_scope.py -q`
Expected: FAIL with 404 route-not-found on scorecard routes (detail `"Not Found"`).

- [ ] **Step 3: Add schemas**

```python
ScorecardState = Literal["completed", "in_progress", "not_started", "not_in_plan", "not_tracked"]


class ScorecardArea(BaseModel):
    key: str
    label: str
    state: ScorecardState


class ScorecardOut(BaseModel):
    school_student_id: UUID
    full_name: str
    grade: str
    portfolio_completion_pct: int
    areas: list[ScorecardArea]


class ScorecardPage(BaseModel):
    items: list[ScorecardOut]
    total: int
    limit: int
    offset: int
```

- [ ] **Step 4: Implement**

```python
from typing import Literal

from app.api.portfolio import portfolio_completion
from app.api.schools import _cumulative_services  # extend
from app.models import School  # extend
from app.schemas import ScorecardArea, ScorecardOut, ScorecardPage  # extend

STUDENT_NOT_FOUND = "Student not found"
NONE: set[UUID] = set()
# (key, label, plan service keys, completed rule, in-progress rule); rules take (indicators, portfolio_complete). Spec §6.3.
SCORECARD_AREAS = [
    ("career_awareness", "Career Awareness", ("career_awareness_session",), lambda i, p: i["awareness_attended"] | i["guidance"], lambda i, p: NONE),
    ("psychometric", "Psychometric", ("psychometric_test",), lambda i, p: i["psych_completed"], lambda i, p: i["psych_started"]),
    ("career_counselling", "Career Counselling", ("individual_counselling",), lambda i, p: i["counselling"], lambda i, p: NONE),
    ("soft_skills", "Soft Skills", ("soft_skills",), lambda i, p: i["soft_skills_completed"], lambda i, p: i["soft_skills_in_progress"]),
    ("foreign_language", "Foreign Language", ("foreign_language_classes",), lambda i, p: i["language_certified"], lambda i, p: i["language_started"]),
    ("digital_portfolio", "Digital Portfolio", ("digital_portfolio_creation",), lambda i, p: p, lambda i, p: i["portfolio_started"]),
    ("ielts_sat", "IELTS/SAT", ("ielts_coaching", "sat_coaching"), lambda i, p: i["test_prep_completed"], lambda i, p: i["test_prep_started"]),
    ("university_shortlisting", "University Shortlisting", ("application_support",), lambda i, p: i["shortlisted"], lambda i, p: i["global"]),
    ("scholarship", "Scholarship", None, None, None),  # not tracked: no school-student scholarship link (ENH-017)
    ("application", "Application", ("application_support",), lambda i, p: i["offer"], lambda i, p: i["applied_active"]),
    ("visa", "Visa", ("visa_support",), lambda i, p: i["admitted"], lambda i, p: i["visa_started"]),  # NEEDS_CONFIRMATION: visa status is free text
    ("internship", "Internship", None, None, None),  # not tracked: no model (ENH-020)
]


def _area_state(sid: UUID, plan: set[str], keys, done: set[UUID], started: set[UUID]) -> str:
    if keys is None:
        return "not_tracked"
    if sid in done:
        return "completed"
    if sid in started:
        return "in_progress"
    return "not_started" if plan.intersection(keys) else "not_in_plan"


async def build_scorecards(db: AsyncSession, school_tier: str | None, students: list) -> list[ScorecardOut]:
    """Scorecards for already scope-checked student rows (id, full_name, grade_level, grade_or_class, date_of_birth), in a fixed
    number of queries. The plan check uses the same inclusion rule as /school/entitlements (tier, not expiry)."""
    ids = [s.id for s in students]
    if not ids:
        return []
    indicators = await student_indicators(db, ids)
    sections = await portfolio_sections(db, ids)
    statements = await statement_ids(db, ids)
    plan = {key for key, _ in _cumulative_services(school_tier)}
    completion = {
        s.id: portfolio_completion(
            profile_complete=s.date_of_birth is not None and s.grade_or_class is not None, has_academic=s.id in indicators["published_results"],
            has_psychometric=s.id in indicators["psych_started"], has_career=s.id in indicators["career_any"],
            has_language=s.id in indicators["language_started"], sections=sections.get(s.id, set()), has_statement=s.id in statements,
        )
        for s in students
    }
    complete = {sid for sid, pct in completion.items() if pct == 100}
    cards = []
    for s in students:
        areas = []
        for key, label, keys, done, started in SCORECARD_AREAS:
            state = "not_tracked" if keys is None else _area_state(s.id, plan, keys, done(indicators, complete), started(indicators, complete))
            areas.append(ScorecardArea(key=key, label=label, state=state))
        cards.append(ScorecardOut(school_student_id=s.id, full_name=s.full_name, grade=grade_key(s.grade_level, s.grade_or_class), portfolio_completion_pct=completion[s.id], areas=areas))
    return cards


SCORECARD_COLUMNS = (SchoolStudent.id, SchoolStudent.full_name, SchoolStudent.grade_level, SchoolStudent.grade_or_class, SchoolStudent.date_of_birth)


@school_router.get("/analytics/scorecards", response_model=ScorecardPage)
async def scorecard_grid(
    grade: Literal[8, 9, 10, 11, 12] | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(_require_school_reader),
    db: AsyncSession = Depends(get_db),
):
    """§28 school-wide grid (D10), own school, ordered by name then id. `grade` filters on `grade_level` only."""
    school_id = _own_school_id(user)
    conditions = [SchoolStudent.school_id == school_id]
    if grade is not None:
        conditions.append(SchoolStudent.grade_level == grade)
    total = await db.scalar(select(func.count()).select_from(SchoolStudent).where(*conditions)) or 0
    students = (await db.execute(select(*SCORECARD_COLUMNS).where(*conditions).order_by(SchoolStudent.full_name, SchoolStudent.id).limit(limit).offset(offset))).all()
    tier = await db.scalar(select(School.tier).where(School.id == school_id))
    _log_view(user, "scorecard_grid", school_id=school_id, count=len(students))
    return ScorecardPage(items=await build_scorecards(db, tier, students), total=total, limit=limit, offset=offset)


@school_router.get("/students/{student_id}/scorecard", response_model=ScorecardOut)
async def student_scorecard(student_id: UUID, user: User = Depends(_require_school_reader), db: AsyncSession = Depends(get_db)):
    """§28 card (D9). The school is part of the lookup, so another school's student is the same 404 as a missing one."""
    school_id = _own_school_id(user)
    student = (await db.execute(select(*SCORECARD_COLUMNS).where(SchoolStudent.id == student_id, SchoolStudent.school_id == school_id))).first()
    if student is None:
        raise HTTPException(404, STUDENT_NOT_FOUND)
    tier = await db.scalar(select(School.tier).where(School.id == school_id))
    _log_view(user, "student_scorecard", school_id=school_id, student_id=student_id)
    return (await build_scorecards(db, tier, [student]))[0]
```

Route-order check: `schools.py` has `GET /school/students/{student_id}` — a longer path `/students/{id}/scorecard` does not collide. If any existing `/school/students/{id}/{something}` catch-all exists, register `school_analytics.school_router` before `schools.router` in `main.py`.

- [ ] **Step 5: Run tests**

Run: `cd apps/api && python -m pytest tests/test_enh_016_scorecard.py tests/test_enh_016_scope.py -q`
Expected: all PASS; scope test now exercises the scorecard path with 403 for every non-reader role.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/school_analytics.py apps/api/app/schemas.py apps/api/tests/test_enh_016_scorecard.py apps/api/tests/test_enh_016_scope.py
git commit -m "feat(enh-016): student progress scorecards, grid and per-student (§28)"
```

---

### Task 8: §34 cross-school summary and §27 per-school utilization

**Files:**
- Modify: `apps/api/app/api/school_analytics.py`, `apps/api/app/schemas.py`
- Test: `apps/api/tests/test_enh_016_cross_school.py`, `test_enh_016_scope.py` (append)

**Interfaces:**
- Consumes: `schools.service_usage`, `schools._cumulative_services`, `schools._today_ist`, `schools.TIER_TIMEZONE`, `student_indicators`, `_roster`, `grade_key`.
- Produces: `utilization(tier: str | None, usage: dict) -> dict` (keys `services_included, delivered, pending, not_tracked, utilization_pct`); schemas `TrackedValue`, `SchoolCounts`, `StudentCounts`, `ServiceTotals`, `CrossSchoolSummaryOut`, `SchoolUtilizationRow`, `SchoolUtilizationPage`; constants `NEW_SCHOOL_DAYS = 90`, `RENEWAL_DUE_DAYS = 60`.

- [ ] **Step 1: Write the failing tests** — `test_enh_016_cross_school.py`:

```python
"""ENH-016 §34 / §27 (AC04, AC09, AC10, AC16)."""

from datetime import timedelta

import pytest

from app.api.school_analytics import utilization
from app.api.schools import _today_ist
from app.models import SchoolPsychometricRecord
from tests.enh016_helpers import login, make_school, make_student


def test_utilization_counts_delivered_pending_and_untracked():
    usage = {"career_seminar": 2, "career_awareness_session": 0, "parent_orientation": 0, "psychometric_test": 5, "soft_skills": 0}
    assert utilization("bronze", usage) == {"services_included": 5, "delivered": 2, "pending": 3, "not_tracked": 0, "utilization_pct": 40.0}
    assert utilization(None, usage) == {"services_included": 0, "delivered": 0, "pending": 0, "not_tracked": 0, "utilization_pct": None}  # Review Focus 5
    gold = utilization("gold", {"dedicated_counselor": True})
    assert gold["not_tracked"] > 0 and gold["delivered"] == 0


@pytest.mark.asyncio
async def test_summary_windows_at_their_edges(client, db_session):  # AC09
    today = _today_ist()
    tagged = {}
    for days in (89, 90, 91):
        tagged[f"new{days}"] = (await make_school(db_session, partnership_date=today - timedelta(days=days)))["school"]
    for days in (-1, 59, 60, 61):
        tagged[f"renew{days}"] = (await make_school(db_session, partnership_date=today - timedelta(days=400), tier_valid_until=today + timedelta(days=days)))["school"]
    ctx = await make_school(db_session, partnership_date=today - timedelta(days=400), status="inactive")
    await db_session.commit()
    await login(client, ctx["overseas_admin"])

    rows = []
    offset = 0
    while True:
        page = (await client.get("/api/v1/overseas-admin/analytics/schools", params={"limit": 100, "offset": offset})).json()
        rows += page["items"]
        offset += 100
        if offset >= page["total"]:
            break
    by_id = {r["school_id"]: r for r in rows}
    assert by_id[str(tagged["new90"].id)]["is_new"] is True and by_id[str(tagged["new91"].id)]["is_new"] is False
    assert by_id[str(tagged["renew60"].id)]["renewal_due"] is True and by_id[str(tagged["renew61"].id)]["renewal_due"] is False
    assert by_id[str(tagged["renew-1"].id)]["renewal_due"] is True  # expired counts (Review Focus 5)
    summary = (await client.get("/api/v1/overseas-admin/analytics/summary")).json()
    assert summary["schools"]["total"] >= 8 and summary["schools"]["active"] <= summary["schools"]["total"] - 1


@pytest.mark.asyncio
async def test_summary_and_rows_hold_no_student_level_fields(client, db_session):  # AC16
    ctx = await make_school(db_session)
    s = await make_student(db_session, ctx, name="Secret Name", grade_level=8)
    db_session.add(SchoolPsychometricRecord(school_student_id=s.id, psychometric_team_user_id=ctx["psychometric_team"].id, assessment_type="A", status="completed"))
    await db_session.commit()
    await login(client, ctx["super_admin"])
    for path in ("/api/v1/overseas-admin/analytics/summary", "/api/v1/overseas-admin/analytics/schools"):
        text = (await client.get(path)).text
        assert "Secret Name" not in text and "school_student_id" not in text and "full_name" not in text
    summary = (await client.get("/api/v1/overseas-admin/analytics/summary")).json()
    assert summary["outcomes"]["scholarships"] == {"value": None, "tracked": False, "note": "No school-student scholarship link exists yet (ENH-017)."}
    assert summary["students"]["psychometric"] >= 1
```

Append to `test_enh_016_scope.py`:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_coordinator", "school_principal", "school_teacher", "school_parent", "academic_team", "career_counselor", "psychometric_team", "it_admin"])
async def test_cross_school_is_admin_only(client, db_session, role):  # AC04
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx[role])
    for path in ADMIN_ENDPOINTS:
        response = await client.get(path)
        assert response.status_code == 403 and response.json()["detail"] == "Overseas Admin role required"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["overseas_admin", "super_admin"])
async def test_cross_school_admins_are_allowed(client, db_session, role):
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx[role])
    for path in ADMIN_ENDPOINTS:
        assert (await client.get(path)).status_code == 200
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && python -m pytest tests/test_enh_016_cross_school.py tests/test_enh_016_scope.py -q`
Expected: FAIL — `ImportError: cannot import name 'utilization'`.

- [ ] **Step 3: Add schemas**

```python
class TrackedValue(BaseModel):
    value: int | None
    tracked: bool
    note: str | None = None


class SchoolCounts(BaseModel):
    total: int
    active: int
    new: int
    renewal_due: int


class StudentCounts(BaseModel):
    total: int
    by_grade: dict[str, int]
    career_guidance: int
    psychometric: int
    counselling: int
    global_education: int


class ServiceTotals(BaseModel):
    services_included: int
    delivered: int
    pending: int
    not_tracked: int
    utilization_pct: float | None


class CrossSchoolSummaryOut(BaseModel):
    schools: SchoolCounts
    students: StudentCounts
    services: ServiceTotals
    outcomes: dict[str, TrackedValue]


class SchoolUtilizationRow(ServiceTotals):
    school_id: UUID
    name: str
    tier: str | None
    tier_valid_until: date | None
    status: str
    is_new: bool
    renewal_due: bool
    students: int
    student_participation: int
    pending_activities: int


class SchoolUtilizationPage(BaseModel):
    items: list[SchoolUtilizationRow]
    total: int
    limit: int
    offset: int
```

- [ ] **Step 4: Implement**

```python
from datetime import UTC, date, datetime, timedelta

from app.api.schools import TIER_TIMEZONE, _today_ist, service_usage  # extend
from app.schemas import CrossSchoolSummaryOut, SchoolCounts, SchoolUtilizationPage, SchoolUtilizationRow, ServiceTotals, StudentCounts, TrackedValue  # extend

NEW_SCHOOL_DAYS = 90       # D6
RENEWAL_DUE_DAYS = 60      # D6
PARTICIPATION_KEYS = ("career_any", "psych_started", "test_prep_started", "language_started", "skills_enrolled", "portfolio_started", "global", "awareness_attended")
UNTRACKED_OUTCOMES = {
    "scholarships": "No school-student scholarship link exists yet (ENH-017).",
    "internships": "No confirmed School internship model exists yet (ENH-020).",
}


def utilization(tier: str | None, usage: dict) -> dict:
    """§27 per school over the services its tier includes: delivered (used > 0 / True), pending (0 / False), not tracked (absent)."""
    values = [usage.get(key) for key, _ in _cumulative_services(tier)]
    not_tracked = sum(1 for v in values if v is None)
    delivered = sum(1 for v in values if v is not None and v is not False and v != 0)
    pending = len(values) - not_tracked - delivered
    return {"services_included": len(values), "delivered": delivered, "pending": pending, "not_tracked": not_tracked, "utilization_pct": _pct(delivered, len(values) - not_tracked)}


def _is_new(school: School, today: date) -> bool:
    start = school.partnership_date or school.created_at.astimezone(TIER_TIMEZONE).date()
    return (today - start).days <= NEW_SCHOOL_DAYS


def _renewal_due(school: School, today: date) -> bool:
    return school.tier_valid_until is not None and school.tier_valid_until <= today + timedelta(days=RENEWAL_DUE_DAYS)


@admin_router.get("/analytics/summary", response_model=CrossSchoolSummaryOut)
async def cross_school_summary(user: User = Depends(_require_school_admin), db: AsyncSession = Depends(get_db)):
    """§34 Edusphere dashboard over every partner school. Aggregates only -- no student-level field (spec §12)."""
    today = _today_ist()
    schools = (await db.scalars(select(School))).all()
    ids = [s.id for s in schools]
    roster = await _roster(db, ids)
    all_students = select(SchoolStudent.id)
    indicators = await student_indicators(db, all_students)
    usage = await service_usage(db, ids)
    per_school = [utilization(s.tier, usage.get(s.id, {})) for s in schools]
    totals = {k: sum(p[k] for p in per_school) for k in ("services_included", "delivered", "pending", "not_tracked")}
    by_grade: dict[str, int] = defaultdict(int)
    for _sid, _school, level, label in roster:
        by_grade[grade_key(level, label)] += 1
    active_apps = await db.scalar(select(func.count()).select_from(OverseasApplication).where(OverseasApplication.school_student_id.is_not(None), OverseasApplication.status.not_in(("withdrawn", "rejected")))) or 0
    offers = await db.scalar(select(func.count()).select_from(OverseasApplication).where(OverseasApplication.school_student_id.is_not(None), (OverseasApplication.status.in_(list(OFFER_ONWARD_STATUSES))) | (OverseasApplication.offer_letter_url.is_not(None)))) or 0
    _log_view(user, "cross_school_summary", school_count=len(ids))
    return CrossSchoolSummaryOut(
        schools=SchoolCounts(total=len(schools), active=sum(1 for s in schools if s.status == "active"), new=sum(1 for s in schools if _is_new(s, today)), renewal_due=sum(1 for s in schools if _renewal_due(s, today))),
        students=StudentCounts(total=len(roster), by_grade={g: by_grade[g] for g in _ordered_grades(by_grade)}, career_guidance=len(indicators["guidance"]), psychometric=len(indicators["psych_completed"]), counselling=len(indicators["counselling"]), global_education=len(indicators["global"])),
        services=ServiceTotals(**totals, utilization_pct=_pct(totals["delivered"], totals["services_included"] - totals["not_tracked"])),
        outcomes={
            "applications": TrackedValue(value=active_apps, tracked=True), "offers": TrackedValue(value=offers, tracked=True),
            "visas": TrackedValue(value=len(indicators["visa_started"]), tracked=True), "admissions": TrackedValue(value=len(indicators["admitted"]), tracked=True),
            **{key: TrackedValue(value=None, tracked=False, note=note) for key, note in UNTRACKED_OUTCOMES.items()},
        },
    )


@admin_router.get("/analytics/schools", response_model=SchoolUtilizationPage)
async def cross_school_rows(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(_require_school_admin),
    db: AsyncSession = Depends(get_db),
):
    """§27 "school-wise" rows, ordered by name then id; every figure is a count."""
    today = _today_ist()
    total = await db.scalar(select(func.count()).select_from(School)) or 0
    schools = (await db.scalars(select(School).order_by(School.name, School.id).limit(limit).offset(offset))).all()
    ids = [s.id for s in schools]
    roster = await _roster(db, ids)
    students_by_school: dict[UUID, set[UUID]] = defaultdict(set)
    for sid, school_id, _level, _label in roster:
        students_by_school[school_id].add(sid)
    indicators = await student_indicators(db, students_in(ids)) if ids else defaultdict(set)
    participating = set().union(*(indicators[k] for k in PARTICIPATION_KEYS))
    usage = await service_usage(db, ids)
    upcoming = dict((await db.execute(select(SchoolActivity.school_id, func.count()).where(SchoolActivity.school_id.in_(ids), SchoolActivity.scheduled_at >= datetime.now(UTC)).group_by(SchoolActivity.school_id))).tuples().all()) if ids else {}
    items = [
        SchoolUtilizationRow(
            school_id=s.id, name=s.name, tier=s.tier, tier_valid_until=s.tier_valid_until, status=s.status, is_new=_is_new(s, today), renewal_due=_renewal_due(s, today),
            students=len(students_by_school[s.id]), student_participation=len(students_by_school[s.id] & participating), pending_activities=upcoming.get(s.id, 0),
            **utilization(s.tier, usage.get(s.id, {})),
        )
        for s in schools
    ]
    _log_view(user, "cross_school_rows", school_count=len(ids))
    return SchoolUtilizationPage(items=items, total=total, limit=limit, offset=offset)
```

Also add the `schools` shape of the spec (§6.5) change: rows now carry `is_new`/`renewal_due` flags — update spec §6.5's per-school field list in this commit.

- [ ] **Step 5: Run tests**

Run: `cd apps/api && python -m pytest tests/test_enh_016_cross_school.py tests/test_enh_016_scope.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/school_analytics.py apps/api/app/schemas.py apps/api/tests/test_enh_016_cross_school.py apps/api/tests/test_enh_016_scope.py docs/superpowers/specs/2026-09-28-enh-016-analytics-dashboards-design.md
git commit -m "feat(enh-016): cross-school dashboard and school-wise utilization (§34, §27)"
```

---

### Task 9: Fixed query count (AC17) and log content

**Files:**
- Test: `apps/api/tests/test_enh_016_performance.py`
- Modify (only if a test fails): `apps/api/app/api/school_analytics.py`

- [ ] **Step 1: Write the test**

```python
"""ENH-016 AC17: query count does not grow with schools; logs carry ids, never names (spec §10, §12)."""

import logging
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from app.core.database import engine
from app.models import SchoolPsychometricRecord
from tests.enh016_helpers import login, make_school, make_student


@contextmanager
def count_queries():
    counter = {"n": 0}

    def _count(*_args, **_kwargs):
        counter["n"] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _count)
    try:
        yield counter
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)


async def _seed(db, ctx, n):
    for i in range(n):
        s = await make_student(db, ctx, name=f"Kid {i}", grade_level=8 + i % 5)
        db.add(SchoolPsychometricRecord(school_student_id=s.id, psychometric_team_user_id=ctx["psychometric_team"].id, assessment_type="A", status="completed"))


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/overseas-admin/analytics/summary", "/api/v1/overseas-admin/analytics/schools"])
async def test_admin_query_count_is_independent_of_school_count(client, db_session, path):
    first = await make_school(db_session)
    await _seed(db_session, first, 3)
    await db_session.commit()
    await login(client, first["super_admin"])
    with count_queries() as one:
        assert (await client.get(path)).status_code == 200
    for _ in range(4):
        await _seed(db_session, await make_school(db_session), 5)
    await db_session.commit()
    with count_queries() as five:
        assert (await client.get(path)).status_code == 200
    assert five["n"] == one["n"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/school/analytics/grade-performance", "/api/v1/school/analytics/student-development", "/api/v1/school/analytics/scorecards"])
async def test_school_query_count_is_independent_of_student_count(client, db_session, path, caplog):
    ctx = await make_school(db_session)
    await _seed(db_session, ctx, 1)
    await db_session.commit()
    await login(client, ctx["school_coordinator"])
    with count_queries() as few:
        await client.get(path)
    await _seed(db_session, ctx, 20)
    await db_session.commit()
    with caplog.at_level(logging.INFO, logger="app.school.analytics"), count_queries() as many:
        await client.get(path)
    assert many["n"] == few["n"]
    assert "Kid" not in caplog.text and "school_analytics_view" in caplog.text
```

- [ ] **Step 2: Run**

Run: `cd apps/api && python -m pytest tests/test_enh_016_performance.py -q`
Expected: PASS. If a count differs, find the per-row query (e.g. a lazy relationship load or a loop issuing `db.get`) and replace it with a grouped query; if the logging assertion fails because the app logger does not propagate to `caplog`, assert on a handler attached to `logging.getLogger("app.school.analytics")` instead.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_enh_016_performance.py apps/api/app/api/school_analytics.py
git commit -m "test(enh-016): fixed query count and id-only logging"
```

---

### Task 10: Web types, shared section error, KPI board on both dashboards

**Files:**
- Modify: `apps/web/lib/types.ts` (append), `apps/web/app/globals.css` (append), `apps/web/app/school/coordinator/dashboard/page.tsx`, `apps/web/app/school/principal/dashboard/page.tsx`
- Create: `apps/web/components/SectionUnavailable.tsx`, `apps/web/components/SchoolKpiBoard.tsx`
- Test: `apps/web/tests/components/SchoolKpiBoard.test.tsx`

**Interfaces:**
- Produces (types): `SchoolKpi`, `MetricCell`, `GradeMetricRow`, `GradePerformance`, `StudentDevelopment`, `PerformerRow`, `AverageRow`, `ScorecardState`, `ScorecardArea`, `Scorecard`, `ScorecardPage`, `TrackedValue`, `CrossSchoolSummary`, `SchoolUtilizationRow`, `SchoolUtilizationPage`; components `SectionUnavailable({ title })`, `SchoolKpiBoard({ kpis })`.

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import SchoolKpiBoard from "@/components/SchoolKpiBoard";
import SectionUnavailable from "@/components/SectionUnavailable";

afterEach(cleanup);

const kpi = (key: string, label: string, value: number | null, tracked = true, note: string | null = null) => ({ key, label, value, tracked, note });

describe("SchoolKpiBoard", () => {
  it("groups KPIs under h3 headings and formats numbers", () => {
    render(<SchoolKpiBoard kpis={[kpi("total_students", "Total Students", 1250), kpi("psychometric_tests_completed", "Psychometric Tests Completed", 720)]} />);
    expect(screen.getByRole("heading", { level: 2, name: "School at a glance" })).toBeInTheDocument();
    const students = screen.getByRole("region", { name: "Students" });
    expect(within(students).getByText("1,250")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Career & assessment" })).toHaveTextContent("720");
  });

  it("shows an untracked KPI as 'Not tracked yet' with its note, never 0", () => {
    render(<SchoolKpiBoard kpis={[kpi("internships", "Internships", null, false, "No confirmed School internship model exists yet.")]} />);
    expect(screen.getByText("Not tracked yet")).toBeInTheDocument();
    expect(screen.getByText("No confirmed School internship model exists yet.")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("renders an honest empty state", () => {
    render(<SchoolKpiBoard kpis={[]} />);
    expect(screen.getByText("No figures to show yet.")).toBeInTheDocument();
  });
});

describe("SectionUnavailable", () => {
  it("announces the failure politely and keeps its heading", () => {
    render(<SectionUnavailable title="Grade-wise comparison" />);
    expect(screen.getByRole("heading", { name: "Grade-wise comparison" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("This section couldn't load. Refresh to try again.");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/web && npx vitest run tests/components/SchoolKpiBoard.test.tsx`
Expected: FAIL — cannot resolve `@/components/SchoolKpiBoard`.

- [ ] **Step 3: Implement**

`components/SectionUnavailable.tsx`:

```tsx
// ENH-016: one section of a dashboard failed to load -- the rest of the page still renders (spec §8 error state).
export default function SectionUnavailable({ title }: { title: string }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      <p className="muted" role="status">This section couldn&apos;t load. Refresh to try again.</p>
    </div>
  );
}
```

`components/SchoolKpiBoard.tsx`:

```tsx
import type { SchoolKpi } from "@/lib/types";

// ENH-016 (School CRM.md §1): the KPI board /school/dashboard already computes, grouped so the first screen reads top-down.
// An untracked KPI says so in words -- never a fabricated 0 (DATA_MODEL.md §8).
const GROUPS: { title: string; keys: string[] }[] = [
  { title: "Students", keys: ["total_students", "grade_8", "grade_9", "grade_10", "grade_11", "grade_12"] },
  { title: "Career & assessment", keys: ["career_guidance_completed", "psychometric_tests_completed", "individual_counselling_completed"] },
  { title: "Skills & languages", keys: ["ielts_training", "sat_preparation", "foreign_language_students", "digital_portfolios_created"] },
  { title: "Global pathway", keys: ["students_in_global_education_pathway", "university_shortlisting", "applications_in_progress", "offers_received", "visa_applications", "students_admitted", "internships"] },
];

export default function SchoolKpiBoard({ kpis }: { kpis: SchoolKpi[] }) {
  const byKey = new Map(kpis.map((k) => [k.key, k]));
  const groups = GROUPS.map((g) => ({ ...g, items: g.keys.map((key) => byKey.get(key)).filter((k): k is SchoolKpi => Boolean(k)) })).filter((g) => g.items.length > 0);
  return (
    <div className="card">
      <h2>School at a glance</h2>
      {groups.length === 0 ? (
        <p className="muted">No figures to show yet.</p>
      ) : (
        groups.map((group) => (
          <section key={group.title} aria-label={group.title} className="kpi-group">
            <h3>{group.title}</h3>
            <dl className="kpi-grid">
              {group.items.map((k) => (
                <div className="kpi-tile" key={k.key}>
                  <dt>{k.label}</dt>
                  {k.tracked && k.value !== null ? (
                    <dd className="kpi-value">{k.value.toLocaleString("en-IN")}</dd>
                  ) : (
                    <dd><span className="badge">Not tracked yet</span>{k.note && <span className="kpi-note muted">{k.note}</span>}</dd>
                  )}
                </div>
              ))}
            </dl>
          </section>
        ))
      )}
    </div>
  );
}
```

(`toLocaleString("en-IN")` formats 1250 as "1,250"; the test's 1,250 matches.)

Append to `lib/types.ts`:

```ts
// --- ENH-016 analytics dashboards (spec §7) ---
export type SchoolKpi = { key: string; label: string; value: number | null; tracked: boolean; note: string | null };
export type MetricCell = { count: number; pct: number | null };
export type GradeMetricRow = { key: string; label: string; is_proxy: boolean; definition: string | null; cells: Record<string, MetricCell> };
export type GradePerformance = { grades: string[]; students: Record<string, number>; metrics: GradeMetricRow[] };
export type AverageRow = { key: string; label: string; average_pct: number | null; count: number };
export type PerformerRow = { school_student_id: string; full_name: string; grade: string; average_pct: number; result_count: number };
export type StudentDevelopment = {
  headcounts: { students: number; teachers: number; parents: number };
  activities: { key: string; label: string; completed: number; pending: number }[];
  by_grade: AverageRow[]; by_subject: AverageRow[]; by_term: AverageRow[];
  at_risk: { items: PerformerRow[]; total: number }; top_performers: { items: PerformerRow[]; total: number };
  at_risk_below: number; top_from: number;
};
export type ScorecardState = "completed" | "in_progress" | "not_started" | "not_in_plan" | "not_tracked";
export type ScorecardArea = { key: string; label: string; state: ScorecardState };
export type Scorecard = { school_student_id: string; full_name: string; grade: string; portfolio_completion_pct: number; areas: ScorecardArea[] };
export type ScorecardPage = { items: Scorecard[]; total: number; limit: number; offset: number };
export type TrackedValue = { value: number | null; tracked: boolean; note: string | null };
export type ServiceTotals = { services_included: number; delivered: number; pending: number; not_tracked: number; utilization_pct: number | null };
export type CrossSchoolSummary = {
  schools: { total: number; active: number; new: number; renewal_due: number };
  students: { total: number; by_grade: Record<string, number>; career_guidance: number; psychometric: number; counselling: number; global_education: number };
  services: ServiceTotals;
  outcomes: Record<string, TrackedValue>;
};
export type SchoolUtilizationRow = ServiceTotals & {
  school_id: string; name: string; tier: string | null; tier_valid_until: string | null; status: string; is_new: boolean; renewal_due: boolean;
  students: number; student_participation: number; pending_activities: number;
};
export type SchoolUtilizationPage = { items: SchoolUtilizationRow[]; total: number; limit: number; offset: number };
```

Append to `app/globals.css`:

```css
/* ENH-016 analytics dashboards */
.kpi-group { margin-top: 16px; }
.kpi-grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin: 8px 0 0; }
@media (min-width: 768px) { .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (min-width: 1024px) { .kpi-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
.kpi-tile { border: 1px solid #e7edf6; border-radius: 8px; padding: 12px; }
.kpi-tile dt { color: #61728a; font-size: 0.875rem; }
.kpi-tile dd { margin: 4px 0 0; }
.kpi-value { font-size: 1.5rem; font-weight: 800; color: #0b1f3a; }
.kpi-note { display: block; font-size: 0.8125rem; margin-top: 4px; }
.table-scroll { overflow-x: auto; max-width: 100%; }
.table-scroll table th:first-child, .table-scroll table td:first-child { position: sticky; left: 0; background: #fff; }
.state-badge { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.analytics-form { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
.pager { display: flex; gap: 12px; align-items: center; margin-top: 12px; }
```

Coordinator dashboard: extend `DashboardPayload` with `school_crm_kpis: SchoolKpi[]` and render `<SchoolKpiBoard kpis={data.school_crm_kpis} />` as the first child of `.portal-content` (above "Your school"). Principal dashboard: fetch `/api/v1/school/dashboard` alongside the existing calls as `serverApi<{ school_crm_kpis: SchoolKpi[] }>("/api/v1/school/dashboard").catch(() => null)` and render `{dashboard ? <SchoolKpiBoard kpis={dashboard.school_crm_kpis} /> : <SectionUnavailable title="School at a glance" />}` first in its content.

- [ ] **Step 4: Run tests**

Run: `cd apps/web && npx vitest run tests/components/SchoolKpiBoard.test.tsx && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/types.ts apps/web/app/globals.css apps/web/components/SectionUnavailable.tsx apps/web/components/SchoolKpiBoard.tsx apps/web/app/school/coordinator/dashboard/page.tsx apps/web/app/school/principal/dashboard/page.tsx apps/web/tests/components/SchoolKpiBoard.test.tsx
git commit -m "feat(enh-016): School CRM §1 KPI board on coordinator and principal dashboards"
```

---

### Task 11: Reports sections — grade comparison, student development, scorecard grid

**Files:**
- Create: `apps/web/components/SchoolGradePerformance.tsx`, `apps/web/components/SchoolStudentDevelopment.tsx`, `apps/web/components/StudentScorecard.tsx` (exports default `StudentScorecard` and named `ScorecardStateBadge`), `apps/web/components/SchoolScorecardGrid.tsx`
- Modify: `apps/web/app/school/coordinator/reports/page.tsx`, `apps/web/app/school/principal/reports/page.tsx`
- Test: `apps/web/tests/components/SchoolAnalyticsSections.test.tsx`

**Interfaces:**
- Consumes: Task 10 types, `SectionUnavailable`.
- Produces: `SchoolGradePerformance({ data })`, `SchoolStudentDevelopment({ data, basePath })`, `SchoolScorecardGrid({ page, grade, basePath, studentHref })`, `ScorecardStateBadge({ state })`, `StudentScorecard({ card })`.

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import SchoolGradePerformance from "@/components/SchoolGradePerformance";
import SchoolScorecardGrid from "@/components/SchoolScorecardGrid";
import SchoolStudentDevelopment from "@/components/SchoolStudentDevelopment";
import StudentScorecard, { ScorecardStateBadge } from "@/components/StudentScorecard";
import type { Scorecard, StudentDevelopment } from "@/lib/types";

afterEach(cleanup);

const card: Scorecard = {
  school_student_id: "s1", full_name: "Asha", grade: "10", portfolio_completion_pct: 40,
  areas: [
    { key: "psychometric", label: "Psychometric", state: "completed" },
    { key: "visa", label: "Visa", state: "not_in_plan" },
    { key: "internship", label: "Internship", state: "not_tracked" },
  ],
};
const development: StudentDevelopment = {
  headcounts: { students: 3, teachers: 1, parents: 2 },
  activities: [{ key: "career_guidance", label: "Career Guidance", completed: 1, pending: 2 }],
  by_grade: [], by_subject: [], by_term: [],
  at_risk: { items: [{ school_student_id: "s2", full_name: "Ben", grade: "9", average_pct: 32.5, result_count: 2 }], total: 1 },
  top_performers: { items: [], total: 0 }, at_risk_below: 40, top_from: 85,
};

describe("ENH-016 report sections", () => {
  it("grade comparison: a captioned table with a column per grade and proxy definitions", () => {
    render(<SchoolGradePerformance data={{ grades: ["9", "10"], students: { "9": 2, "10": 1 }, metrics: [{ key: "career_readiness", label: "Career readiness", is_proxy: true, definition: "Guidance and psychometric done", cells: { "9": { count: 1, pct: 50 }, "10": { count: 0, pct: 0 } } }] }} />);
    const table = screen.getByRole("table", { name: "Grade-wise comparison" });
    expect(within(table).getByRole("columnheader", { name: "Grade 10" })).toBeInTheDocument();
    expect(within(table).getByText("1 (50%)")).toBeInTheDocument();
    expect(screen.getByText("Guidance and psychometric done")).toBeInTheDocument();
  });

  it("grade comparison: empty roster", () => {
    render(<SchoolGradePerformance data={{ grades: [], students: {}, metrics: [] }} />);
    expect(screen.getByText("No students on the roster yet.")).toBeInTheDocument();
  });

  it("student development: completed/pending table, labelled threshold form, at-risk list", () => {
    render(<SchoolStudentDevelopment data={development} basePath="/school/coordinator/reports" />);
    expect(within(screen.getByRole("table", { name: "Student development" })).getByText("2")).toBeInTheDocument();
    expect(screen.getByLabelText("At risk below (%)")).toHaveValue(40);
    expect(screen.getByLabelText("Top performer from (%)")).toHaveValue(85);
    expect(screen.getByRole("list", { name: "At-risk students" })).toHaveTextContent("Ben");
    expect(screen.getByText("No students at or above 85% yet.")).toBeInTheDocument();
  });

  it("state badge always pairs an icon with words", () => {
    render(<ScorecardStateBadge state="in_progress" />);
    expect(screen.getByText("In progress")).toBeInTheDocument();
  });

  it("student scorecard lists every area and the portfolio percentage", () => {
    render(<StudentScorecard card={card} />);
    expect(screen.getByRole("heading", { name: "Progress scorecard" })).toBeInTheDocument();
    expect(screen.getByText("Not in plan")).toBeInTheDocument();
    expect(screen.getByText("Not tracked yet")).toBeInTheDocument();
    expect(screen.getByText("Portfolio 40% complete")).toBeInTheDocument();
  });

  it("scorecard grid: grade filter form, student links, and paging links that keep the filter", () => {
    render(<SchoolScorecardGrid page={{ items: [card], total: 30, limit: 25, offset: 0 }} grade="10" basePath="/school/coordinator/reports" studentHref={(id) => `/school/coordinator/students/${id}`} />);
    expect(screen.getByLabelText("Grade")).toHaveValue("10");
    expect(screen.getByRole("link", { name: "Asha" })).toHaveAttribute("href", "/school/coordinator/students/s1");
    expect(screen.getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/school/coordinator/reports?grade=10&offset=25#scorecards");
    expect(screen.queryByRole("link", { name: "Previous page" })).not.toBeInTheDocument();
  });

  it("scorecard grid: offset past the end shows the empty message and a way back (Review Focus 4)", () => {
    render(<SchoolScorecardGrid page={{ items: [], total: 3, limit: 25, offset: 50 }} grade="" basePath="/r" studentHref={(id) => id} />);
    expect(screen.getByText("No students match this grade.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Previous page" })).toHaveAttribute("href", "/r?offset=25#scorecards");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/web && npx vitest run tests/components/SchoolAnalyticsSections.test.tsx`
Expected: FAIL — cannot resolve the four components.

- [ ] **Step 3: Implement**

`components/StudentScorecard.tsx`:

```tsx
import type { Scorecard, ScorecardState } from "@/lib/types";

// ENH-016 (School CRM.md §28). Every state is an icon AND words -- never colour or emoji alone (spec §8).
const STATES: Record<ScorecardState, { icon: string; label: string }> = {
  completed: { icon: "✅", label: "Completed" },
  in_progress: { icon: "🔄", label: "In progress" },
  not_started: { icon: "⏳", label: "Not started" },
  not_in_plan: { icon: "—", label: "Not in plan" },
  not_tracked: { icon: "—", label: "Not tracked yet" },
};

export function ScorecardStateBadge({ state }: { state: ScorecardState }) {
  const { icon, label } = STATES[state];
  return <span className="state-badge"><span aria-hidden="true">{icon}</span>{label}</span>;
}

export default function StudentScorecard({ card }: { card: Scorecard }) {
  return (
    <div className="card">
      <h2>Progress scorecard</h2>
      <p className="muted">Portfolio {card.portfolio_completion_pct}% complete</p>
      <table className="table">
        <caption className="sr-only">Progress by area for {card.full_name}</caption>
        <thead><tr><th scope="col">Area</th><th scope="col">Status</th></tr></thead>
        <tbody>
          {card.areas.map((a) => (
            <tr key={a.key}><th scope="row">{a.label}</th><td><ScorecardStateBadge state={a.state} /></td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

(If `.sr-only` does not exist in `globals.css`, add `.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}` in this task.)

`components/SchoolGradePerformance.tsx`:

```tsx
import type { GradePerformance } from "@/lib/types";

// ENH-016 (School CRM.md §29): the same metrics side by side for each grade. Estimated metrics show their definition.
const gradeLabel = (g: string) => (g === "other" ? "Other grades" : g === "unspecified" ? "No grade" : `Grade ${g}`);

export default function SchoolGradePerformance({ data }: { data: GradePerformance }) {
  return (
    <div className="card">
      <h2>Grade-wise comparison</h2>
      {data.grades.length === 0 ? (
        <p className="muted">No students on the roster yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <caption className="sr-only">Grade-wise comparison</caption>
            <thead>
              <tr><th scope="col">Metric</th>{data.grades.map((g) => <th scope="col" key={g}>{gradeLabel(g)}</th>)}</tr>
            </thead>
            <tbody>
              <tr><th scope="row">Students</th>{data.grades.map((g) => <td key={g}>{data.students[g]}</td>)}</tr>
              {data.metrics.map((m) => (
                <tr key={m.key}>
                  <th scope="row">{m.label}{m.is_proxy && <span className="kpi-note muted">Estimate: {m.definition}</span>}</th>
                  {data.grades.map((g) => {
                    const cell = m.cells[g];
                    return <td key={g}>{cell.pct === null ? cell.count : `${cell.count} (${Math.round(cell.pct)}%)`}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

Adjust the test's expected proxy text to `"Estimate: Guidance and psychometric done"` if `getByText` needs the exact node text (keep the test and component consistent; the definition must be visible).

`components/SchoolStudentDevelopment.tsx`:

```tsx
import type { AverageRow, PerformerRow, StudentDevelopment } from "@/lib/types";

// ENH-016 (School CRM.md Part B §14). Pending = total - completed (D2). Academic figures are published results only.
function Averages({ title, rows }: { title: string; rows: AverageRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="table-scroll">
      <table className="table">
        <caption>{title}</caption>
        <thead><tr><th scope="col">Group</th><th scope="col">Average</th><th scope="col">Results</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.key}><th scope="row">{r.label}</th><td>{r.average_pct === null ? "—" : `${r.average_pct}%`}</td><td>{r.count}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function Performers({ label, rows, total, empty }: { label: string; rows: PerformerRow[]; total: number; empty: string }) {
  return (
    <section aria-label={label}>
      <h3>{label} ({total})</h3>
      {rows.length === 0 ? <p className="muted">{empty}</p> : (
        <ul aria-label={label}>{rows.map((p) => <li key={p.school_student_id}>{p.full_name} · Grade {p.grade} · {p.average_pct}% ({p.result_count} results)</li>)}</ul>
      )}
      {total > rows.length && <p className="muted">Showing the first {rows.length}.</p>}
    </section>
  );
}

export default function SchoolStudentDevelopment({ data, basePath }: { data: StudentDevelopment; basePath: string }) {
  const hasResults = data.by_subject.length > 0;
  return (
    <div className="card">
      <h2>Student development</h2>
      <p>{data.headcounts.students} students · {data.headcounts.teachers} teachers · {data.headcounts.parents} parents</p>
      <div className="table-scroll">
        <table className="table">
          <caption className="sr-only">Student development</caption>
          <thead><tr><th scope="col">Activity</th><th scope="col">Completed</th><th scope="col">Pending</th></tr></thead>
          <tbody>{data.activities.map((a) => <tr key={a.key}><th scope="row">{a.label}</th><td>{a.completed}</td><td>{a.pending}</td></tr>)}</tbody>
        </table>
      </div>
      <h3>Academic performance</h3>
      {!hasResults ? <p className="muted">No published results yet.</p> : (
        <>
          <Averages title="By grade" rows={data.by_grade.map((r) => ({ ...r, label: `Grade ${r.label}` }))} />
          <Averages title="By subject" rows={data.by_subject} />
          <Averages title="By term" rows={data.by_term} />
        </>
      )}
      <form method="get" action={`${basePath}#development`} className="analytics-form">
        <div className="field"><label htmlFor="at_risk_below">At risk below (%)</label><input id="at_risk_below" name="at_risk_below" type="number" min={0} max={100} defaultValue={data.at_risk_below} /></div>
        <div className="field"><label htmlFor="top_from">Top performer from (%)</label><input id="top_from" name="top_from" type="number" min={0} max={100} defaultValue={data.top_from} /></div>
        <button className="btn secondary" type="submit">Update thresholds</button>
      </form>
      <Performers label="At-risk students" rows={data.at_risk.items} total={data.at_risk.total} empty={`No students below ${data.at_risk_below}%.`} />
      <Performers label="Top performers" rows={data.top_performers.items} total={data.top_performers.total} empty={`No students at or above ${data.top_from}% yet.`} />
    </div>
  );
}
```

`components/SchoolScorecardGrid.tsx`:

```tsx
import type { ScorecardPage } from "@/lib/types";
import { ScorecardStateBadge } from "@/components/StudentScorecard";

// ENH-016 (School CRM.md §28, D10): every student × area, filtered and paged through the URL so it works without client JS.
function href(basePath: string, grade: string, offset: number) {
  const params = new URLSearchParams();
  if (grade) params.set("grade", grade);
  if (offset > 0) params.set("offset", String(offset));
  const query = params.toString();
  return `${basePath}${query ? `?${query}` : ""}#scorecards`;
}

export default function SchoolScorecardGrid({ page, grade, basePath, studentHref }: { page: ScorecardPage; grade: string; basePath: string; studentHref: (id: string) => string }) {
  const areas = page.items[0]?.areas ?? [];
  const prev = page.offset > 0 ? Math.max(0, page.offset - page.limit) : null;
  const next = page.offset + page.limit < page.total ? page.offset + page.limit : null;
  return (
    <div className="card" id="scorecards">
      <h2>Student progress scorecards</h2>
      <form method="get" action={`${basePath}#scorecards`} className="analytics-form">
        <div className="field">
          <label htmlFor="scorecard-grade">Grade</label>
          <select id="scorecard-grade" name="grade" defaultValue={grade}>
            <option value="">All grades</option>
            {["8", "9", "10", "11", "12"].map((g) => <option key={g} value={g}>Grade {g}</option>)}
          </select>
        </div>
        <button className="btn secondary" type="submit">Show</button>
      </form>
      {page.items.length === 0 ? <p className="muted">No students match this grade.</p> : (
        <div className="table-scroll">
          <table className="table">
            <caption className="sr-only">Progress scorecards, {page.total} students</caption>
            <thead><tr><th scope="col">Student</th>{areas.map((a) => <th scope="col" key={a.key}>{a.label}</th>)}</tr></thead>
            <tbody>
              {page.items.map((c) => (
                <tr key={c.school_student_id}>
                  <th scope="row"><a href={studentHref(c.school_student_id)}>{c.full_name}</a></th>
                  {c.areas.map((a) => <td key={a.key}><ScorecardStateBadge state={a.state} /></td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <nav className="pager" aria-label="Scorecard pages">
        {prev !== null && <a href={href(basePath, grade, prev)} aria-label="Previous page">← Previous</a>}
        <span className="muted">{page.total === 0 ? "0 students" : `${Math.min(page.offset + 1, page.total)}–${Math.min(page.offset + page.limit, page.total)} of ${page.total}`}</span>
        {next !== null && <a href={href(basePath, grade, next)} aria-label="Next page">Next →</a>}
      </nav>
    </div>
  );
}
```

Reports pages (coordinator shown; principal identical with `principal` paths and `SCHOOL_NAV.principal`): change the signature to `export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> })`, then after the existing `user`/`report` load:

```tsx
  const sp = await searchParams;
  const grade = /^(8|9|10|11|12)$/.test(sp.grade ?? "") ? sp.grade! : "";
  const offset = Math.max(0, Number.parseInt(sp.offset ?? "0", 10) || 0);
  const thresholds = new URLSearchParams();
  for (const key of ["at_risk_below", "top_from"]) if (/^\d{1,3}$/.test(sp[key] ?? "")) thresholds.set(key, sp[key]!);
  const grid = new URLSearchParams({ offset: String(offset) });
  if (grade) grid.set("grade", grade);
  const [grades, development, scorecards] = await Promise.all([
    serverApi<GradePerformance>("/api/v1/school/analytics/grade-performance").catch(() => null),
    serverApi<StudentDevelopment>(`/api/v1/school/analytics/student-development?${thresholds}`).catch(() => null),
    serverApi<ScorecardPage>(`/api/v1/school/analytics/scorecards?${grid}`).catch(() => null),
  ]);
```

and render after `<SchoolReportsPanel report={report} />`:

```tsx
      {grades ? <SchoolGradePerformance data={grades} /> : <SectionUnavailable title="Grade-wise comparison" />}
      <div id="development">{development ? <SchoolStudentDevelopment data={development} basePath="/school/coordinator/reports" /> : <SectionUnavailable title="Student development" />}</div>
      {scorecards ? <SchoolScorecardGrid page={scorecards} grade={grade} basePath="/school/coordinator/reports" studentHref={(id) => `/school/coordinator/students/${id}`} /> : <SectionUnavailable title="Student progress scorecards" />}
```

(Out-of-range thresholds such as `at_risk_below=90&top_from=10` make the API return 422 → that section shows `SectionUnavailable`; acceptable, and the form's `min`/`max` prevent most of them.)

- [ ] **Step 4: Run tests**

Run: `cd apps/web && npx vitest run tests/components/SchoolAnalyticsSections.test.tsx && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/SchoolGradePerformance.tsx apps/web/components/SchoolStudentDevelopment.tsx apps/web/components/StudentScorecard.tsx apps/web/components/SchoolScorecardGrid.tsx apps/web/app/school/coordinator/reports/page.tsx apps/web/app/school/principal/reports/page.tsx apps/web/app/globals.css apps/web/tests/components/SchoolAnalyticsSections.test.tsx
git commit -m "feat(enh-016): grade comparison, student development and scorecard grid on reports"
```

---

### Task 12: Scorecard card on student detail pages

**Files:**
- Modify: `apps/web/app/school/coordinator/students/[id]/page.tsx`, `apps/web/app/school/principal/students/[id]/page.tsx`

- [ ] **Step 1: Implement** — in each page, after the student is loaded (inside the existing `try`, after `student = …`), add:

```tsx
    scorecard = await serverApi<Scorecard>(`/api/v1/school/students/${id}/scorecard`).catch(() => null);
```

with `let scorecard: Scorecard | null = null;` declared beside `student`, and render inside `PortalShell` after `SchoolStudentDetailPanel`:

```tsx
      <div className="portal-content">{scorecard ? <StudentScorecard card={scorecard} /> : <SectionUnavailable title="Progress scorecard" />}</div>
```

(The principal page's own role guard, if any, stays as it is; the API returns 403 for anyone else and the section shows `SectionUnavailable`.)

- [ ] **Step 2: Verify**

Run: `cd apps/web && npx tsc --noEmit && npx vitest run`
Expected: types clean; full unit suite PASS.

- [ ] **Step 3: Commit**

```bash
git add "apps/web/app/school/coordinator/students/[id]/page.tsx" "apps/web/app/school/principal/students/[id]/page.tsx"
git commit -m "feat(enh-016): progress scorecard on the student page"
```

---

### Task 13: Cross-school admin page and navigation

**Files:**
- Create: `apps/web/components/CrossSchoolAnalytics.tsx`, `apps/web/app/overseas/admin/school-analytics/page.tsx`, `apps/web/app/overseas/admin/school-analytics/loading.tsx`
- Modify: `apps/web/lib/navigation.ts:74,77`
- Test: `apps/web/tests/components/CrossSchoolAnalytics.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import CrossSchoolAnalytics from "@/components/CrossSchoolAnalytics";
import { PORTAL_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { CrossSchoolSummary } from "@/lib/types";

afterEach(cleanup);

const summary: CrossSchoolSummary = {
  schools: { total: 4, active: 3, new: 1, renewal_due: 2 },
  students: { total: 120, by_grade: { "9": 60, "10": 60 }, career_guidance: 40, psychometric: 30, counselling: 20, global_education: 10 },
  services: { services_included: 30, delivered: 12, pending: 8, not_tracked: 10, utilization_pct: 60 },
  outcomes: { applications: { value: 9, tracked: true, note: null }, scholarships: { value: null, tracked: false, note: "No link yet." } },
};
const row = { school_id: "a", name: "Alpha School", tier: "gold", tier_valid_until: "2026-10-01", status: "active", is_new: false, renewal_due: true, students: 50, student_participation: 20, pending_activities: 2, services_included: 12, delivered: 6, pending: 3, not_tracked: 3, utilization_pct: 66.7 };

describe("CrossSchoolAnalytics", () => {
  it("shows the four KPI groups, untracked outcomes in words, and the school table", () => {
    render(<CrossSchoolAnalytics summary={summary} page={{ items: [row], total: 1, limit: 25, offset: 0 }} basePath="/overseas/admin/school-analytics" />);
    for (const name of ["Schools", "Students", "Services", "Outcomes"]) expect(screen.getByRole("region", { name })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Outcomes" })).toHaveTextContent("Not tracked yet");
    const table = screen.getByRole("table", { name: "Service utilization by school" });
    expect(within(table).getByText("Alpha School")).toBeInTheDocument();
    expect(within(table).getByText("66.7%")).toBeInTheDocument();
    expect(within(table).getByText("Renewal due")).toBeInTheDocument();
  });

  it("empty and failed sections", () => {
    render(<CrossSchoolAnalytics summary={null} page={{ items: [], total: 0, limit: 25, offset: 0 }} basePath="/x" />);
    expect(screen.getByRole("status")).toHaveTextContent("This section couldn't load.");
    expect(screen.getByText("No partner schools yet.")).toBeInTheDocument();
  });
});

describe("navigation", () => {
  it("links School Analytics for overseas and super admins", () => {
    expect(PORTAL_NAV["overseas/admin"].some((i) => i.href === "/overseas/admin/school-analytics")).toBe(true);
    expect(SUPER_ADMIN_NAV.some((i) => i.href === "/overseas/admin/school-analytics")).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/web && npx vitest run tests/components/CrossSchoolAnalytics.test.tsx`
Expected: FAIL — cannot resolve `@/components/CrossSchoolAnalytics`.

- [ ] **Step 3: Implement**

`components/CrossSchoolAnalytics.tsx`:

```tsx
import SectionUnavailable from "@/components/SectionUnavailable";
import type { CrossSchoolSummary, SchoolUtilizationPage, TrackedValue } from "@/lib/types";

// ENH-016 (School CRM.md §34 + §27 school-wise): aggregates only -- no student-level data reaches this page (spec §12).
const OUTCOME_LABELS: Record<string, string> = { applications: "Applications", offers: "Offers", scholarships: "Scholarships", visas: "Visas", admissions: "Admissions", internships: "Internships" };
const pct = (v: number | null) => (v === null ? "—" : `${v}%`);

function Group({ title, items }: { title: string; items: [string, React.ReactNode][] }) {
  return (
    <section aria-label={title} className="kpi-group">
      <h3>{title}</h3>
      <dl className="kpi-grid">{items.map(([label, value]) => <div className="kpi-tile" key={label}><dt>{label}</dt><dd className="kpi-value">{value}</dd></div>)}</dl>
    </section>
  );
}

const tracked = (t: TrackedValue) => (t.tracked && t.value !== null ? t.value.toLocaleString("en-IN") : <span className="badge" title={t.note ?? undefined}>Not tracked yet</span>);

export default function CrossSchoolAnalytics({ summary, page, basePath }: { summary: CrossSchoolSummary | null; page: SchoolUtilizationPage | null; basePath: string }) {
  const next = page && page.offset + page.limit < page.total ? page.offset + page.limit : null;
  const prev = page && page.offset > 0 ? Math.max(0, page.offset - page.limit) : null;
  return (
    <>
      {summary ? (
        <div className="card">
          <h2>All partner schools</h2>
          <Group title="Schools" items={[["Total", summary.schools.total], ["Active", summary.schools.active], ["New (90 days)", summary.schools.new], ["Renewal due (60 days)", summary.schools.renewal_due]]} />
          <Group title="Students" items={[["Total", summary.students.total.toLocaleString("en-IN")], ["Career guidance", summary.students.career_guidance], ["Psychometric", summary.students.psychometric], ["Counselling", summary.students.counselling], ["Global education", summary.students.global_education]]} />
          <Group title="Services" items={[["Delivered", summary.services.delivered], ["Pending", summary.services.pending], ["Not tracked", summary.services.not_tracked], ["Utilization", pct(summary.services.utilization_pct)]]} />
          <Group title="Outcomes" items={Object.entries(summary.outcomes).map(([k, v]) => [OUTCOME_LABELS[k] ?? k, tracked(v)])} />
        </div>
      ) : <SectionUnavailable title="All partner schools" />}
      {page ? (
        <div className="card">
          <h2>Service utilization by school</h2>
          {page.items.length === 0 ? <p className="muted">No partner schools yet.</p> : (
            <div className="table-scroll">
              <table className="table">
                <caption className="sr-only">Service utilization by school</caption>
                <thead><tr>{["School", "Tier", "Students", "Participating", "Delivered", "Pending", "Not tracked", "Utilization", "Upcoming activities", "Flags"].map((h) => <th scope="col" key={h}>{h}</th>)}</tr></thead>
                <tbody>
                  {page.items.map((r) => (
                    <tr key={r.school_id}>
                      <th scope="row">{r.name}</th><td>{r.tier ?? "No tier"}</td><td>{r.students}</td><td>{r.student_participation}</td>
                      <td>{r.delivered}</td><td>{r.pending}</td><td>{r.not_tracked}</td><td>{pct(r.utilization_pct)}</td><td>{r.pending_activities}</td>
                      <td>{[r.is_new && "New", r.renewal_due && "Renewal due", r.status !== "active" && "Inactive"].filter(Boolean).map((f) => <span className="badge" key={String(f)}>{f}</span>)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <nav className="pager" aria-label="School pages">
            {prev !== null && <a href={`${basePath}?offset=${prev}`} aria-label="Previous page">← Previous</a>}
            {next !== null && <a href={`${basePath}?offset=${next}`} aria-label="Next page">Next →</a>}
          </nav>
        </div>
      ) : <SectionUnavailable title="Service utilization by school" />}
    </>
  );
}
```

`app/overseas/admin/school-analytics/page.tsx`:

```tsx
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import CrossSchoolAnalytics from "@/components/CrossSchoolAnalytics";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import type { CrossSchoolSummary, SchoolUtilizationPage, User } from "@/lib/types";

// ENH-016 (School CRM.md §34, D1): Edusphere's cross-school view. Admin-only like the API; the role is checked first so no one
// else is shown a screen that can only fail. Static route wins over `[section]`, like school-transfers.
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function SchoolAnalyticsPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e);
  }
  if (!ADMIN_ROLES.includes(user.role)) return accessDenied(user, "Overseas Administrator role required");
  const offset = Math.max(0, Number.parseInt((await searchParams).offset ?? "0", 10) || 0);
  const [summary, page] = await Promise.all([
    serverApi<CrossSchoolSummary>("/api/v1/overseas-admin/analytics/summary").catch(() => null),
    serverApi<SchoolUtilizationPage>(`/api/v1/overseas-admin/analytics/schools?offset=${offset}`).catch(() => null),
  ]);
  return (
    <PortalShell nav={PORTAL_NAV["overseas/admin"]} roleLabel={user.role === "super_admin" ? "Super Administrator" : "Overseas Administrator"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title"><div><div className="eyebrow">Workspace</div><h1>School Analytics</h1><p className="muted">Every partner school at a glance, and how much of each partnership is being used.</p></div></div>
        <CrossSchoolAnalytics summary={summary} page={page} basePath="/overseas/admin/school-analytics" />
      </div>
    </PortalShell>
  );
}
```

`loading.tsx`:

```tsx
// ENH-016: shown while the server reads every school's figures, so navigation is never a blank screen (ENH-018 pattern).
export default function Loading() {
  return (
    <div className="portal-content" aria-busy="true" aria-label="Loading school analytics">
      <div className="card">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}</div>
    </div>
  );
}
```

`lib/navigation.ts`: in the `"overseas/admin"` array insert `"school-analytics"` after `"school-transfers"`; change `SUPER_ADMIN_NAV` to append the item:

```ts
export const SUPER_ADMIN_NAV:NavItem[] = [...["dashboard", /* …existing list unchanged… */ "backups"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:x==="dashboard"?"/admin":`/admin/${x}`})), {label:"School Analytics",href:"/overseas/admin/school-analytics"}];
```

(Keep the original array literal verbatim inside the spread.) The `PortalShell` heading level: if other portal pages use `<h2>` in `.portal-title`, use `h2` to match (school-transfers does) — follow the existing page, not this snippet.

- [ ] **Step 4: Run tests**

Run: `cd apps/web && npx vitest run && npx tsc --noEmit`
Expected: all PASS (includes `SuperAdminDashboard.test.tsx` and navigation tests).

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/CrossSchoolAnalytics.tsx apps/web/app/overseas/admin/school-analytics apps/web/lib/navigation.ts apps/web/tests/components/CrossSchoolAnalytics.test.tsx
git commit -m "feat(enh-016): cross-school School Analytics page for Edusphere admins"
```

---

### Task 14: End-to-end browser spec

**Files:**
- Create: `apps/web/tests/e2e/enh-016-analytics.spec.ts`

- [ ] **Step 1: Write the spec** (requires the running stack with `python -m app.seed` applied, as ENH-018's spec)

```ts
import { expect, test, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-016 -- coordinator sees the §1 KPI board and the three report sections; principal sees the KPI board; an admin sees the
// cross-school page; a coordinator who opens the admin URL is refused. Builds a throwaway school per run.
const ADMIN_EMAIL = "overseasadmin@edusphere.local";
const ADMIN_PASSWORD = "Demo@123";

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(landing);
}

test("school dashboards, reports sections and cross-school analytics are role-scoped (ENH-016)", async ({ page }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(String(error).slice(0, 140)));

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  const coordinatorEmail = `enh016-e2e-coord-${unique}@example.local`;
  const schoolName = `E2E ENH-016 School ${unique}`;
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.fill("#school-coordinator-name", "E2E ENH-016 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.selectOption("#school-tier", "gold");
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "**/school/coordinator/dashboard");
  expect((await page.request.post("/api/v1/school/students", { data: { full_name: "E2E Student", grade_level: 10, grade_or_class: "Grade 10" } })).status()).toBe(201);
  await page.reload();
  await expect(page.getByRole("heading", { name: "School at a glance" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Students" })).toContainText("1");

  await page.goto("/school/coordinator/reports");
  await expect(page.getByRole("heading", { name: "Grade-wise comparison" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Student development" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Student progress scorecards" })).toBeVisible();
  // keyboard: choose a grade and submit the filter
  await page.getByLabel("Grade").focus();
  await page.keyboard.press("ArrowDown");
  await page.getByRole("button", { name: "Show" }).press("Enter");
  await expect(page).toHaveURL(/grade=/);

  // phone width: the scorecard table scrolls inside its card, the page does not
  await page.setViewportSize({ width: 320, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });

  await page.goto("/overseas/admin/school-analytics");
  await expect(page.getByText("Access unavailable")).toBeVisible();

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  await page.goto("/overseas/admin/school-analytics");
  await expect(page.getByRole("heading", { name: "School Analytics" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Outcomes" })).toContainText("Not tracked yet");
  expect(pageErrors).toEqual([]);
});
```

Before running, confirm the student-create payload against `POST /api/v1/school/students` (`schemas.StudentMasterFields` / `create_student`) and adjust the JSON keys if needed; confirm the principal path by adding a principal via the coordinator's Team page only if time allows — the principal KPI board is already covered by the unit test and the API test.

- [ ] **Step 2: Run** (the user starts the stack)

Run: `cd apps/web && npx playwright test tests/e2e/enh-016-analytics.spec.ts`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/enh-016-analytics.spec.ts
git commit -m "test(enh-016): end-to-end analytics dashboards flow"
```

---

### Task 15: Decision record, RTM, backlog, regression run

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append `DEC-SCOPE-031`, same heading format as `DEC-SCOPE-030` at line 2457)
- Modify: the RTM file that holds the ENH-023 row (find with `grep -rln "ENH-023" docs --include=*.md | grep -i rtm`), add an ENH-016 row in the same column format
- Modify: `docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-016 status line and the coverage rows at lines 911, 935, 937–939, 944, 960

- [ ] **Step 1: Write `DEC-SCOPE-031`** — title "School & Edusphere analytics dashboards (`ENH-016`)", body: the D1–D16 table copied verbatim from spec §3, source `EXPLICIT_APPROVAL` (user, 2026-09-28), and the follow-ups list from spec §15.
- [ ] **Step 2: Add the RTM row** — Evidence (`School CRM.md` §1/§27/§28/§29/§34/B14) → `DEC-SCOPE-031` → ENH-016 → AC01–AC18 → screens (coordinator/principal dashboard + reports + student page; `/overseas/admin/school-analytics`) → API (six routes) → tests (the `test_enh_016_*` files, component tests, e2e) → code (files in this plan). Status `IMPLEMENTED — pending browser validation and independent review` (not COMPLETE).
- [ ] **Step 3: Update the backlog** coverage rows from `⚠️ Partial`/`❌ Gap` to `Implemented in ENH-016 (pending validation)`; leave §25 (Edusphere School Counsellor tracking) unchanged — not in ENH-016's spec.
- [ ] **Step 4: Regression run**

Run:
```bash
cd apps/api && python -m pytest -q tests/test_enh_016_* tests/test_sch_reports.py tests/test_sch_011_entitlements.py tests/test_enh_022_tier_enforcement.py tests/test_enh_023_tier_change.py tests/test_enh_013_360_view.py tests/test_sch_001_school_portal_access.py tests/test_enh_005_scope.py tests/test_rbac.py tests/test_adm_014_super_admin_console.py tests/test_rpt_001_reporting.py tests/test_rpt_002_overseas_reporting.py -k "" && python -m pytest -q -k "enh_011 or enh_012"
cd ../web && npx vitest run && npx tsc --noEmit && npx next lint
npx playwright test tests/e2e/sch-reports.spec.ts tests/e2e/sch-011-entitlements.spec.ts tests/e2e/enh-013-student-360.spec.ts tests/e2e/enh-022-tier-enforcement.spec.ts tests/e2e/enh-023-tier-change.spec.ts tests/e2e/rpt-001-reporting.spec.ts tests/e2e/rpt-002-overseas-reporting.spec.ts tests/e2e/adm-014-super-admin-console.spec.ts tests/e2e/auth-002-rbac-ui.spec.ts tests/e2e/desktop-nav-dropdown.spec.ts tests/e2e/enh-016-analytics.spec.ts
```
Expected: all PASS. Record the counts in the RTM row. Any failure → `superpowers:systematic-debugging`, never edit a test to pass unless an approved decision changed the behaviour (as in Task 4).

- [ ] **Step 5: Commit**

```bash
git add docs/decisions/PRODUCT_DECISION_REGISTER.md docs/delivery/ENHANCEMENT_BACKLOG.md <rtm-file>
git commit -m "docs(enh-016): DEC-SCOPE-031, RTM row and backlog coverage"
```

ENH-016 is **not** complete after this task: browser validation and the independent Codex review follow.
