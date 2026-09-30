# ENH-017 Global Education Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only "Global Education" page for School Coordinator and Principal showing a §17-shaped funnel and a paged
per-student list of their own school's bridged students — high-level stage only (§19), enforced in the API payload.

**Architecture:** One new FastAPI module (`school_global_education.py`) with one GET route that selects named columns only
(never overseas ORM rows) and maps existing application/visa statuses to funnel stages; additive Pydantic output models;
two new presentational server components and two thin pages that share one renderer. No migrations, no edits to
`schools.py`, `school_analytics.py`, `workflows.py`, `student_360.py`.

**Tech Stack:** FastAPI, Pydantic v2, async SQLAlchemy, pytest (+pytest-asyncio); Next.js 15 App Router server components,
React 19, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-29-enh-017-global-education-pipeline-design.md` (decisions D1–D10, AC01–AC18).

## Global Constraints

- No new dependencies. No migrations. No data changes.
- Zero edits to `apps/api/app/api/schools.py`, `school_analytics.py`, `school_feedback.py`, `workflows.py`, `student_360.py`,
  `admin.py`; import from them only.
- Existing API contracts unchanged (`/school/dashboard`, `/reports`, `/students/{id}/overview`, `/timeline`, `/360-view`,
  `/analytics/*`, `/entitlements`).
- snake_case JSON; errors are FastAPI `{"detail": ...}`.
- Roles: `school_coordinator`, `school_principal` only, via `_require_school_reader`.
- Allowed per-student fields exactly: `school_student_id, full_name, student_code, grade, furthest_stage, furthest_stage_label,
  visa_stage_label, application_count`.
- Log line name `school_global_education_view`; ids and counts only.
- UI copy (verbatim): boundary note "High-level stage only. Application details are handled by EduSphere's application team.";
  empty "No students from this school are on the global education pathway yet. Students appear here once an EduSphere
  counselor links their application."; empty grade "No students in this grade are on the global education pathway.";
  past end "This page is past the end of the list."
- API tests run against the shared PostgreSQL DB: from `apps/api`, `python -m pytest -q <file>` (or
  `docker compose exec api python -m pytest -q <file>`). Never run the whole suite casually (AGENTS.md).

## Review Focus

1. A student with **several applications at different stages** — counted once per stage, furthest stage = best of all.
2. A student with an application whose status is **outside the enum** (legacy `offer_received`, `withdrawn`) — counts toward
   pathway (and offer if in `OFFER_ONWARD_STATUSES`), never crashes the label lookup.
3. **Grade stored only as a label** (`grade_level` NULL, `grade_or_class` "Grade 12") — must match `grade=12`.
4. **Empty-string offer letter** (`offer_letter_url = ""`) — must NOT count as an offer (dashboard uses truthiness).
5. **Direct URL tampering** on the page (`?grade=abc`, `?offset=-5`) — page renders unfiltered instead of an error card.

Each is pinned by a test in Task 2 (1, 2, 4), Task 3 (3) and Task 5 (5).

---

### Task 1: Endpoint skeleton — access control and response shape

**Files:**
- Create: `apps/api/app/api/school_global_education.py`
- Modify: `apps/api/app/schemas.py` (append at end of file)
- Modify: `apps/api/app/main.py:18-30` (import) and `:55` (router tuple)
- Test: `apps/api/tests/test_enh_017_global_education_pipeline.py`

**Interfaces:**
- Produces: `GET /api/v1/school/global-education/pipeline` → `GlobalEducationPipelineOut`; schema classes
  `PipelineStage{key,label,count}`, `PipelineUntracked{key,label,note}`, `PipelineStudentRow{…8 fields…}`,
  `PipelineStudentPage{items,total,limit,offset}`, `GlobalEducationPipelineOut{grade,students_in_scope,bridged_students,funnel,not_tracked,students}`;
  module constants `FUNNEL: tuple[tuple[str, str], ...]`, `router`, `logger`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_enh_017_global_education_pipeline.py`:

```python
"""ENH-017 School-visible Global Education pipeline (spec 2026-09-29; DEC-SCOPE-036). High-level stage only (§19)."""

import pytest
from enh016_helpers import _user, login, make_school, make_student, make_university

from app.models import OverseasApplication, VisaCase

URL = "/api/v1/school/global-education/pipeline"
TOP_KEYS = {"grade", "students_in_scope", "bridged_students", "funnel", "not_tracked", "students"}
FUNNEL_KEYS = ["pathway", "profile_evaluation", "shortlisted", "offer", "visa", "admitted"]


async def bridge(db, student, university, *, status="enquiry", **fields) -> OverseasApplication:
    application = OverseasApplication(student_id=None, school_student_id=student.id, university_id=university.id, intake="Fall 2027", status=status, **fields)
    db.add(application)
    await db.flush()
    return application


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_coordinator", "school_principal"])
async def test_coordinator_and_principal_read_their_own_school(client, db_session, role):  # AC01
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx[role])

    response = await client.get(URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == TOP_KEYS
    assert [s["key"] for s in body["funnel"]] == FUNNEL_KEYS
    assert set(body["students"]) == {"items", "total", "limit", "offset"}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_teacher", "school_parent", "academic_team", "career_counselor", "psychometric_team", "overseas_admin", "super_admin", "it_admin"])
async def test_every_other_role_is_refused(client, db_session, role):  # AC02
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx[role])
    assert (await client.get(URL)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["counselor", "overseas_student"])
async def test_overseas_counselor_and_student_are_refused(client, db_session, role):  # AC02
    user = _user(role, "overseas")
    db_session.add(user)
    await db_session.commit()
    await login(client, user)
    assert (await client.get(URL)).status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client):  # AC02
    assert (await client.get(URL)).status_code == 401


@pytest.mark.asyncio
async def test_coordinator_without_a_linked_school_is_403(client, db_session):  # AC03
    user = _user("school_coordinator", "overseas")  # profile {} -- no school_id
    db_session.add(user)
    await db_session.commit()
    await login(client, user)
    assert (await client.get(URL)).status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `apps/api`): `python -m pytest -q tests/test_enh_017_global_education_pipeline.py`
Expected: FAIL — the 200 test gets 404 (route missing); the 401/403 tests also get 404.

- [ ] **Step 3: Add the output schemas**

Append to `apps/api/app/schemas.py`:

```python
# --- ENH-017 (DEC-SCOPE-036): School-visible Global Education pipeline -- an allowlist; §19 keeps application detail out --------


class PipelineStage(BaseModel):
    key: str
    label: str
    count: int


class PipelineUntracked(BaseModel):
    key: str
    label: str
    note: str


class PipelineStudentRow(BaseModel):
    school_student_id: UUID
    full_name: str
    student_code: str
    grade: str
    furthest_stage: str
    furthest_stage_label: str
    visa_stage_label: str | None
    application_count: int


class PipelineStudentPage(BaseModel):
    items: list[PipelineStudentRow]
    total: int
    limit: int
    offset: int


class GlobalEducationPipelineOut(BaseModel):
    grade: int | None
    students_in_scope: int
    bridged_students: int
    funnel: list[PipelineStage]
    not_tracked: list[PipelineUntracked]
    students: PipelineStudentPage
```

(`UUID` and `BaseModel` are already imported at the top of `schemas.py`; verify with `grep -n "^from uuid\|^from pydantic" apps/api/app/schemas.py`.)

- [ ] **Step 4: Write the minimal module**

Create `apps/api/app/api/school_global_education.py`:

```python
"""ENH-017 (`DEC-SCOPE-036`; spec docs/superpowers/specs/2026-09-29-enh-017-global-education-pipeline-design.md): the
`School CRM.md` §17 Global Education funnel for a school's bridged (SCH-010) students, high-level stage only (§19). Read-only:
it selects named columns, never an `OverseasApplication`/`VisaCase` row, so application detail cannot reach the response."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.school_feedback import _require_school_reader
from app.api.schools import _own_school_id
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import User
from app.schemas import GlobalEducationPipelineOut, PipelineStage, PipelineStudentPage

router = APIRouter(prefix="/school", tags=["school-global-education"])
logger = get_logger("app.school.global_education")

# Spec §5.1, in funnel order. A student reaches a stage on any of their bridged applications (D3).
FUNNEL = (
    ("pathway", "Global education pathway"),
    ("profile_evaluation", "Profile evaluation"),
    ("shortlisted", "University shortlisted"),
    ("offer", "Offer received"),
    ("visa", "Visa"),
    ("admitted", "Admitted"),
)


@router.get("/global-education/pipeline", response_model=GlobalEducationPipelineOut)
async def global_education_pipeline(user: User = Depends(_require_school_reader), db: AsyncSession = Depends(get_db)):
    _own_school_id(user)
    return GlobalEducationPipelineOut(
        grade=None, students_in_scope=0, bridged_students=0,
        funnel=[PipelineStage(key=key, label=label, count=0) for key, label in FUNNEL],
        not_tracked=[], students=PipelineStudentPage(items=[], total=0, limit=25, offset=0),
    )
```

- [ ] **Step 5: Register the router**

In `apps/api/app/main.py`, add `school_global_education,` to the `from app.api import (...)` list (alphabetically next to
`school_feedback`) and append `school_global_education.router` to the end of the tuple on line 55:

```python
..., school_analytics.school_router, school_analytics.admin_router, school_global_education.router):
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_enh_017_global_education_pipeline.py`
Expected: PASS (all tests in the file).

- [ ] **Step 7: Lint and commit**

```bash
cd apps/api && python -m ruff check app/api/school_global_education.py app/schemas.py app/main.py tests/test_enh_017_global_education_pipeline.py
git add apps/api/app/api/school_global_education.py apps/api/app/schemas.py apps/api/app/main.py apps/api/tests/test_enh_017_global_education_pipeline.py
git commit -m "feat(enh-017): school global-education pipeline endpoint skeleton with role guard"
```

---

### Task 2: Stage rules, per-student rows and the §19 allowlist

**Files:**
- Modify: `apps/api/app/api/school_global_education.py`
- Test: `apps/api/tests/test_enh_017_global_education_pipeline.py` (append)

**Interfaces:**
- Consumes: Task 1 `router`, `FUNNEL`, schemas.
- Produces: pure functions `application_stages(status: str, has_offer_letter: bool) -> set[str]`,
  `visa_stage_label(statuses: list[str]) -> str | None`, `furthest_stage(reached: set[str]) -> str`; constants
  `NOT_TRACKED`, `VISA_STAGE_LABELS`, `VISA_UNKNOWN_LABEL = "In progress"`.

- [ ] **Step 1: Write the failing tests** (append to the test file)

```python
from app.api.school_global_education import visa_stage_label


def _funnel(body):
    return {s["key"]: s["count"] for s in body["funnel"]}


def _rows(body):
    return {r["full_name"]: r for r in body["students"]["items"]}


@pytest.mark.asyncio
async def test_funnel_counts_each_student_once_per_stage_reached(client, db_session):  # AC05, AC06, Review Focus 1/2/4
    ctx = await make_school(db_session)
    uni = await make_university(db_session)
    many = await make_student(db_session, ctx, name="Asha Many")
    await bridge(db_session, many, uni, status="enquiry")
    await bridge(db_session, many, uni, status="offer")
    await bridge(db_session, many, uni, status="university_selection")
    legacy = await make_student(db_session, ctx, name="Bala Legacy")
    await bridge(db_session, legacy, uni, status="offer_received")  # outside the enum, but in OFFER_ONWARD_STATUSES
    withdrawn = await make_student(db_session, ctx, name="Chen Withdrawn")
    await bridge(db_session, withdrawn, uni, status="withdrawn")  # pathway only
    blank_offer = await make_student(db_session, ctx, name="Dina Blank")
    await bridge(db_session, blank_offer, uni, status="eligibility_evaluation", offer_letter_url="")  # "" is not an offer
    visa_student = await make_student(db_session, ctx, name="Esa Visa")
    visa_app = await bridge(db_session, visa_student, uni, status="enrolled")
    db_session.add(VisaCase(application_id=visa_app.id, status="interview_prep"))
    await make_student(db_session, ctx, name="Farah NotBridged")
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    body = (await client.get(URL)).json()

    assert body["students_in_scope"] == 6
    assert body["bridged_students"] == 5
    assert _funnel(body) == {"pathway": 5, "profile_evaluation": 3, "shortlisted": 2, "offer": 3, "visa": 1, "admitted": 1}
    assert "Farah NotBridged" not in _rows(body)
    assert body["students"]["total"] == 5


@pytest.mark.asyncio
async def test_not_tracked_stages_are_listed_with_reasons(client, db_session):  # AC08
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx["school_principal"])

    body = (await client.get(URL)).json()

    assert [s["key"] for s in body["not_tracked"]] == ["applications_started", "applications_submitted", "deposit", "scholarship", "top_100", "alumni"]
    assert all(s["note"] and set(s) == {"key", "label", "note"} for s in body["not_tracked"])
    assert not {s["key"] for s in body["not_tracked"]} & {s["key"] for s in body["funnel"]}


@pytest.mark.asyncio
async def test_each_row_shows_furthest_stage_visa_label_and_count(client, db_session):  # AC09
    ctx = await make_school(db_session)
    uni = await make_university(db_session)
    s = await make_student(db_session, ctx, name="Gita Row", grade_level=12)
    first = await bridge(db_session, s, uni, status="offer")
    second = await bridge(db_session, s, uni, status="enquiry")
    db_session.add_all([VisaCase(application_id=first.id, status="documentation"), VisaCase(application_id=second.id, status="checklist")])
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    row = _rows((await client.get(URL)).json())["Gita Row"]

    assert row["furthest_stage"] == "visa" and row["furthest_stage_label"] == "Visa"
    assert row["visa_stage_label"] == "Documentation"
    assert row["application_count"] == 2
    assert row["grade"] == "12"
    assert row["student_code"] == s.student_code


def test_visa_stage_label_rules():  # AC09
    assert visa_stage_label([]) is None
    assert visa_stage_label(["checklist", "decision", "tracking"]) == "Decision"
    assert visa_stage_label(["interview_prep"]) == "Interview preparation"
    assert visa_stage_label(["approved"]) == "In progress"  # not a modelled stage
    assert visa_stage_label(["approved", "checklist"]) == "Checklist"  # a known stage wins over an unknown one


@pytest.mark.asyncio
async def test_funnel_matches_the_dashboard_kpis(client, db_session):  # AC07
    ctx = await make_school(db_session)
    uni = await make_university(db_session)
    for status in ("enquiry", "university_selection", "offer", "enrolled"):
        s = await make_student(db_session, ctx)
        application = await bridge(db_session, s, uni, status=status)
        if status in ("offer", "enrolled"):
            db_session.add(VisaCase(application_id=application.id))
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    funnel = _funnel((await client.get(URL)).json())
    kpis = {k["key"]: k["value"] for k in (await client.get("/api/v1/school/dashboard")).json()["school_crm_kpis"]}

    assert funnel["pathway"] == kpis["students_in_global_education_pathway"]
    assert funnel["shortlisted"] == kpis["university_shortlisting"]
    assert funnel["visa"] == kpis["visa_applications"]
    assert funnel["admitted"] == kpis["students_admitted"]


@pytest.mark.asyncio
async def test_another_schools_bridged_students_never_appear(client, db_session):  # AC04
    mine = await make_school(db_session)
    other = await make_school(db_session)
    uni = await make_university(db_session)
    await bridge(db_session, await make_student(db_session, mine, name="Mine One"), uni)
    await bridge(db_session, await make_student(db_session, other, name="Other One"), uni, status="enrolled")
    await db_session.commit()
    await login(client, mine["school_coordinator"])

    body = (await client.get(URL)).json()

    assert set(_rows(body)) == {"Mine One"}
    assert _funnel(body)["admitted"] == 0


ROW_KEYS = {"school_student_id", "full_name", "student_code", "grade", "furthest_stage", "furthest_stage_label", "visa_stage_label", "application_count"}


@pytest.mark.asyncio
async def test_response_carries_only_the_allowlisted_keys_and_no_planted_detail(client, db_session):  # AC10, AC11
    ctx = await make_school(db_session)
    counselor = _user("counselor", "overseas")
    counselor.full_name = "PLANTED-COUNSELOR-NAME"
    db_session.add(counselor)
    uni = await make_university(db_session)
    uni.name = "PLANTED-UNIVERSITY"
    s = await make_student(db_session, ctx, name="Hana Safe")
    application = await bridge(
        db_session, s, uni, status="offer", counselor_id=counselor.id, intake="PLANTED-INTAKE",
        notes="PLANTED-NOTES", next_action="PLANTED-NEXT-ACTION", application_reference="PLANTED-REF", offer_letter_url="https://x/PLANTED-OFFER.pdf",
    )
    db_session.add(VisaCase(application_id=application.id, status="tracking", tracking_reference="PLANTED-VISA-REF"))
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    response = await client.get(URL)

    body = response.json()
    assert set(body) == TOP_KEYS
    assert all(set(s) == {"key", "label", "count"} for s in body["funnel"])
    assert set(body["students"]) == {"items", "total", "limit", "offset"}
    assert all(set(r) == ROW_KEYS for r in body["students"]["items"])
    assert "PLANTED" not in response.text
    assert str(application.id) not in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_enh_017_global_education_pipeline.py`
Expected: FAIL — `ImportError: cannot import name 'visa_stage_label'` (collection error for the whole file).

- [ ] **Step 3: Implement the stage rules and queries**

Replace the body of `school_global_education.py` below the `FUNNEL` constant, and extend the imports:

```python
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.school_analytics import grade_key, students_in
from app.api.school_feedback import _require_school_reader
from app.api.schools import OFFER_ONWARD_STATUSES, _own_school_id, _stage_at_or_after
from app.api.workflows import VISA_CASE_STAGES
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import OverseasApplication, SchoolStudent, User, VisaCase
from app.schemas import GlobalEducationPipelineOut, PipelineStage, PipelineStudentPage, PipelineStudentRow, PipelineUntracked
```

```python
FUNNEL_LABELS = dict(FUNNEL)
# Spec §5.2 (D1): §17/§19 stages with no data source yet -- shown as not tracked, never as a fabricated 0.
NOT_TRACKED = (
    ("applications_started", "Applications started", "Application status does not distinguish started from submitted."),
    ("applications_submitted", "Applications submitted", "Application status does not distinguish started from submitted."),
    ("deposit", "Deposit", "No deposit stage is recorded."),
    ("scholarship", "Scholarships", "No school-student scholarship link exists yet."),
    ("top_100", "Top 100 universities", "Universities carry no ranking yet."),
    ("alumni", "Alumni", "Alumni tracking is not built yet."),
)
VISA_STAGE_LABELS = {"checklist": "Checklist", "documentation": "Documentation", "interview_prep": "Interview preparation", "tracking": "Tracking", "decision": "Decision"}
VISA_UNKNOWN_LABEL = "In progress"
ROSTER_COLUMNS = (SchoolStudent.id, SchoolStudent.full_name, SchoolStudent.student_code, SchoolStudent.grade_level, SchoolStudent.grade_or_class)


def application_stages(status: str, has_offer_letter: bool) -> set[str]:
    """The funnel stages one application has reached (spec §5.1). Visa is added from `VisaCase` rows (D10)."""
    reached = {"pathway"}
    if _stage_at_or_after(status, "eligibility_evaluation"):
        reached.add("profile_evaluation")
    if _stage_at_or_after(status, "university_selection"):
        reached.add("shortlisted")
    if status in OFFER_ONWARD_STATUSES or has_offer_letter:
        reached.add("offer")
    if status == "enrolled":
        reached.add("admitted")
    return reached


def furthest_stage(reached: set[str]) -> str:
    return next(key for key, _ in reversed(FUNNEL) if key in reached)


def visa_stage_label(statuses: list[str]) -> str | None:
    """The most advanced modelled visa stage across a student's cases; "In progress" when none is a modelled stage."""
    if not statuses:
        return None
    known = [s for s in statuses if s in VISA_STAGE_LABELS]
    return VISA_STAGE_LABELS[max(known, key=VISA_CASE_STAGES.index)] if known else VISA_UNKNOWN_LABEL


@router.get("/global-education/pipeline", response_model=GlobalEducationPipelineOut)
async def global_education_pipeline(user: User = Depends(_require_school_reader), db: AsyncSession = Depends(get_db)):
    school_id = _own_school_id(user)
    roster = (await db.execute(select(*ROSTER_COLUMNS).where(SchoolStudent.school_id == school_id).order_by(SchoolStudent.full_name, SchoolStudent.id))).all()
    scope = students_in([school_id])
    reached: dict = defaultdict(set)
    application_count: dict = defaultdict(int)
    # The offer letter is reduced to a boolean in SQL; "" is not an offer (matches the dashboard's truthiness test).
    has_offer_letter = and_(OverseasApplication.offer_letter_url.is_not(None), OverseasApplication.offer_letter_url != "")
    applications = select(OverseasApplication.school_student_id, OverseasApplication.status, has_offer_letter).where(OverseasApplication.school_student_id.in_(scope))
    for sid, status, offer in (await db.execute(applications)).tuples():
        reached[sid] |= application_stages(status, bool(offer))
        application_count[sid] += 1
    visa_statuses: dict = defaultdict(list)
    visas = select(OverseasApplication.school_student_id, VisaCase.status).join(VisaCase, VisaCase.application_id == OverseasApplication.id).where(OverseasApplication.school_student_id.in_(scope))
    for sid, status in (await db.execute(visas)).tuples():
        reached[sid].add("visa")
        visa_statuses[sid].append(status)

    bridged = [s for s in roster if s.id in reached]
    rows = [
        PipelineStudentRow(
            school_student_id=s.id, full_name=s.full_name, student_code=s.student_code, grade=grade_key(s.grade_level, s.grade_or_class),
            furthest_stage=(stage := furthest_stage(reached[s.id])), furthest_stage_label=FUNNEL_LABELS[stage],
            visa_stage_label=visa_stage_label(visa_statuses[s.id]), application_count=application_count[s.id],
        )
        for s in bridged
    ]
    return GlobalEducationPipelineOut(
        grade=None, students_in_scope=len(roster), bridged_students=len(bridged),
        funnel=[PipelineStage(key=key, label=label, count=sum(1 for s in bridged if key in reached[s.id])) for key, label in FUNNEL],
        not_tracked=[PipelineUntracked(key=key, label=label, note=note) for key, label, note in NOT_TRACKED],
        students=PipelineStudentPage(items=rows, total=len(bridged), limit=25, offset=0),
    )
```

Note: a bridged application whose student moved to another school follows the student (`students_in` is the current roster),
which is the SCH-010/ENH-005 transfer behaviour.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_enh_017_global_education_pipeline.py`
Expected: PASS.

- [ ] **Step 5: Lint, type-check, commit**

```bash
cd apps/api && python -m ruff check app/api/school_global_education.py tests/test_enh_017_global_education_pipeline.py && python -m mypy app/api/school_global_education.py
git add apps/api/app/api/school_global_education.py apps/api/tests/test_enh_017_global_education_pipeline.py
git commit -m "feat(enh-017): funnel stage rules and allowlisted per-student rows"
```

---

### Task 3: Grade filter, validation, paging, logging, no writes, constant queries

**Files:**
- Modify: `apps/api/app/api/school_global_education.py`
- Test: `apps/api/tests/test_enh_017_global_education_pipeline.py` (append)

**Interfaces:**
- Consumes: Task 2 route.
- Produces: query params `grade: int | None (8–12)`, `limit: int (1–100, default 25)`, `offset: int (0–MAX_OFFSET)`;
  log record `school_global_education_view` with `extra_fields` keys `actor_id, role, school_id, grade, bridged, returned`.

- [ ] **Step 1: Write the failing tests** (append)

```python
import logging
from contextlib import contextmanager

from sqlalchemy import event, func, select

from app.core.database import engine
from app.models import AuditLog


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    """Order-proofing (ENH-016 precedent): an in-process Alembic run disables existing `app.*` loggers."""
    logging.getLogger("app.school.global_education").disabled = False
    yield


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


@pytest.mark.asyncio
async def test_grade_filters_funnel_and_list_including_label_only_grades(client, db_session):  # AC12, Review Focus 3
    ctx = await make_school(db_session)
    uni = await make_university(db_session)
    await bridge(db_session, await make_student(db_session, ctx, name="Level Twelve", grade_level=12), uni)
    await bridge(db_session, await make_student(db_session, ctx, name="Label Twelve", grade_or_class="Grade 12"), uni)
    await bridge(db_session, await make_student(db_session, ctx, name="Eleven", grade_level=11), uni, status="enrolled")
    await make_student(db_session, ctx, name="Twelve Unbridged", grade_level=12)
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    body = (await client.get(URL, params={"grade": 12})).json()

    assert body["grade"] == 12
    assert body["students_in_scope"] == 3
    assert set(_rows(body)) == {"Level Twelve", "Label Twelve"}
    assert _funnel(body)["admitted"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"grade": 7}, {"grade": 13}, {"grade": "abc"}, {"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10_001}])
async def test_invalid_query_is_422(client, db_session, params):  # AC12
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx["school_coordinator"])
    assert (await client.get(URL, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_wrong_role_with_invalid_query_is_still_403(client, db_session):  # AC12
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx["school_teacher"])
    assert (await client.get(URL, params={"grade": "abc", "limit": 0})).status_code == 403


@pytest.mark.asyncio
async def test_paging_is_stable_and_past_the_end_is_empty_with_the_real_total(client, db_session):  # AC13
    ctx = await make_school(db_session)
    uni = await make_university(db_session)
    for name in ("Cara", "Abe", "Bea"):
        await bridge(db_session, await make_student(db_session, ctx, name=name), uni)
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    first = (await client.get(URL, params={"limit": 2})).json()["students"]
    second = (await client.get(URL, params={"limit": 2, "offset": 2})).json()["students"]
    past = (await client.get(URL, params={"limit": 2, "offset": 50})).json()

    assert [r["full_name"] for r in first["items"]] == ["Abe", "Bea"]
    assert [r["full_name"] for r in second["items"]] == ["Cara"]
    assert (first["total"], first["limit"], first["offset"]) == (3, 2, 0)
    assert past["students"]["items"] == [] and past["students"]["total"] == 3
    assert _funnel(past)["pathway"] == 3  # the funnel is never paged


@pytest.mark.asyncio
async def test_a_read_writes_nothing_and_logs_ids_and_counts_only(client, db_session, caplog):  # AC14
    ctx = await make_school(db_session)
    uni = await make_university(db_session)
    await bridge(db_session, await make_student(db_session, ctx, name="Secretname Student"), uni)
    await db_session.commit()
    await login(client, ctx["school_coordinator"])
    audit_before = await db_session.scalar(select(func.count()).select_from(AuditLog))

    with caplog.at_level(logging.INFO, logger="app.school.global_education"):
        assert (await client.get(URL, params={"grade": 12})).status_code == 200

    assert await db_session.scalar(select(func.count()).select_from(AuditLog)) == audit_before
    records = [r for r in caplog.records if r.getMessage() == "school_global_education_view"]
    assert len(records) == 1
    fields = records[0].extra_fields
    assert set(fields) == {"actor_id", "role", "school_id", "grade", "bridged", "returned"}
    assert fields["school_id"] == str(ctx["school"].id)
    assert "Secretname" not in repr(fields)


@pytest.mark.asyncio
async def test_query_count_does_not_grow_with_students(client, db_session):  # spec §6.1 (three reads + auth)
    ctx = await make_school(db_session)
    uni = await make_university(db_session)
    await bridge(db_session, await make_student(db_session, ctx), uni)
    await db_session.commit()
    await login(client, ctx["school_coordinator"])
    with count_queries() as few:
        assert (await client.get(URL)).status_code == 200
    for _ in range(15):
        s = await make_student(db_session, ctx)
        application = await bridge(db_session, s, uni, status="offer")
        db_session.add(VisaCase(application_id=application.id))
    await db_session.commit()
    with count_queries() as many:
        assert (await client.get(URL)).status_code == 200
    assert many["n"] == few["n"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_enh_017_global_education_pipeline.py -k "grade or invalid or paging or logs or wrong_role"`
Expected: FAIL — grade test (`grade` is `None`, list not filtered), `test_invalid_query_is_422` (200 returned: params
ignored), paging test (`limit` ignored), logging test (no record). `test_wrong_role_with_invalid_query_is_still_403` already
passes (guard test, dependency order) and `test_query_count_does_not_grow_with_students` already passes (guard) — both are
kept as regression pins.

- [ ] **Step 3: Implement params, filter, paging and the log line**

In `school_global_education.py` add `Query` to the FastAPI import and `MAX_OFFSET` to the `school_analytics` import:

```python
from fastapi import APIRouter, Depends, Query
from app.api.school_analytics import MAX_OFFSET, grade_key, students_in
```

Replace the whole route function with:

```python
@router.get("/global-education/pipeline", response_model=GlobalEducationPipelineOut)
async def global_education_pipeline(
    user: User = Depends(_require_school_reader),  # a dependency, so a wrong role is 403 before any 422
    grade: int | None = Query(None, ge=8, le=12),  # an int range, not Literal: query strings never coerce into Literal[int]
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
    db: AsyncSession = Depends(get_db),
):
    """Read-only (spec §8): nothing is added to the session or committed. Own school only -- the school comes from the
    session, never from the request, so there is no id to tamper with (AC04)."""
    school_id = _own_school_id(user)
    roster = (await db.execute(select(*ROSTER_COLUMNS).where(SchoolStudent.school_id == school_id).order_by(SchoolStudent.full_name, SchoolStudent.id))).all()
    if grade is not None:  # D7: the ENH-016 `grade_key` rule, so a grade means the same students on every page
        roster = [s for s in roster if grade_key(s.grade_level, s.grade_or_class) == str(grade)]
    scope = students_in([school_id])
    reached: dict = defaultdict(set)
    application_count: dict = defaultdict(int)
    # The offer letter is reduced to a boolean in SQL; "" is not an offer (matches the dashboard's truthiness test).
    has_offer_letter = and_(OverseasApplication.offer_letter_url.is_not(None), OverseasApplication.offer_letter_url != "")
    applications = select(OverseasApplication.school_student_id, OverseasApplication.status, has_offer_letter).where(OverseasApplication.school_student_id.in_(scope))
    for sid, status, offer in (await db.execute(applications)).tuples():
        reached[sid] |= application_stages(status, bool(offer))
        application_count[sid] += 1
    visa_statuses: dict = defaultdict(list)
    visas = select(OverseasApplication.school_student_id, VisaCase.status).join(VisaCase, VisaCase.application_id == OverseasApplication.id).where(OverseasApplication.school_student_id.in_(scope))
    for sid, status in (await db.execute(visas)).tuples():
        reached[sid].add("visa")
        visa_statuses[sid].append(status)

    bridged = [s for s in roster if s.id in reached]
    rows = [
        PipelineStudentRow(
            school_student_id=s.id, full_name=s.full_name, student_code=s.student_code, grade=grade_key(s.grade_level, s.grade_or_class),
            furthest_stage=(stage := furthest_stage(reached[s.id])), furthest_stage_label=FUNNEL_LABELS[stage],
            visa_stage_label=visa_stage_label(visa_statuses[s.id]), application_count=application_count[s.id],
        )
        for s in bridged[offset : offset + limit]  # the list is paged; the funnel below never is
    ]
    logger.info("school_global_education_view", extra={"extra_fields": {
        "actor_id": str(user.id), "role": user.role, "school_id": str(school_id), "grade": str(grade), "bridged": len(bridged), "returned": len(rows),
    }})
    return GlobalEducationPipelineOut(
        grade=grade, students_in_scope=len(roster), bridged_students=len(bridged),
        funnel=[PipelineStage(key=key, label=label, count=sum(1 for s in bridged if key in reached[s.id])) for key, label in FUNNEL],
        not_tracked=[PipelineUntracked(key=key, label=label, note=note) for key, label, note in NOT_TRACKED],
        students=PipelineStudentPage(items=rows, total=len(bridged), limit=limit, offset=offset),
    )
```

- [ ] **Step 4: Run the file, then the regression neighbours**

Run: `python -m pytest -q tests/test_enh_017_global_education_pipeline.py`
Expected: PASS.
Run: `python -m pytest -q tests/test_sch_010_overseas_bridge.py tests/test_enh_016_contracts.py tests/test_enh_016_scorecard.py tests/test_enh_016_cross_school.py tests/test_enh_016_scope.py tests/test_enh_016_school_analytics.py tests/test_enh_016_performance.py tests/test_enh_013_360_view.py tests/test_sch_reports.py tests/test_enh_022_tier_enforcement.py tests/test_enh_001_academic_year.py`
Expected: PASS, no file modified (AC15).

- [ ] **Step 5: Lint, type-check, commit**

```bash
cd apps/api && python -m ruff check . && python -m mypy app
git add apps/api/app/api/school_global_education.py apps/api/tests/test_enh_017_global_education_pipeline.py
git commit -m "feat(enh-017): grade filter, paging, validation and view logging for the pipeline"
```

---

### Task 4: Web types and the two presentational components

**Files:**
- Modify: `apps/web/lib/types.ts` (append)
- Create: `apps/web/components/GlobalEducationFunnel.tsx`
- Create: `apps/web/components/GlobalEducationStudentTable.tsx`
- Modify: `apps/web/app/globals.css` (append)
- Test: `apps/web/tests/components/GlobalEducationPipeline.test.tsx`

**Interfaces:**
- Consumes: API shape from Task 3.
- Produces: `type GlobalEducationPipeline`, `type PipelineStudentRow`; `<GlobalEducationFunnel data={GlobalEducationPipeline} />`;
  `<GlobalEducationStudentTable page={GlobalEducationPipeline["students"]} grade={string} basePath={string} />`.

- [ ] **Step 1: Write the failing tests**

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import GlobalEducationFunnel from "@/components/GlobalEducationFunnel";
import GlobalEducationStudentTable from "@/components/GlobalEducationStudentTable";
import type { GlobalEducationPipeline } from "@/lib/types";

const row = (n: number) => ({ school_student_id: `id-${n}`, full_name: `Student ${n}`, student_code: `C0DE000${n}`, grade: "12", furthest_stage: "offer", furthest_stage_label: "Offer received", visa_stage_label: n === 1 ? "Documentation" : null, application_count: 2 });
const data = (over: Partial<GlobalEducationPipeline> = {}): GlobalEducationPipeline => ({
  grade: 12, students_in_scope: 150, bridged_students: 80,
  funnel: [{ key: "pathway", label: "Global education pathway", count: 80 }, { key: "offer", label: "Offer received", count: 18 }],
  not_tracked: [{ key: "scholarship", label: "Scholarships", note: "No school-student scholarship link exists yet." }],
  students: { items: [row(1), row(2)], total: 80, limit: 25, offset: 0 },
  ...over,
});

afterEach(cleanup);

describe("GlobalEducationFunnel", () => {
  it("states the scope, the §19 boundary and every stage count as text", () => {
    render(<GlobalEducationFunnel data={data()} />);
    expect(screen.getByText("150 students in Grade 12 · 80 students on the global education pathway")).toBeTruthy();
    expect(screen.getByText("High-level stage only. Application details are handled by EduSphere's application team.")).toBeTruthy();
    const funnel = screen.getByRole("list", { name: "Global education funnel" });
    expect(within(funnel).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Global education pathway80", "Offer received18"]);
  });

  it("shows untracked stages as not tracked, never as zero", () => {
    render(<GlobalEducationFunnel data={data()} />);
    const group = screen.getByRole("region", { name: "Not tracked yet" });
    expect(within(group).getByText("Scholarships")).toBeTruthy();
    expect(within(group).getByText("No school-student scholarship link exists yet.")).toBeTruthy();
  });

  it("drops the grade from the scope line when no grade is chosen", () => {
    render(<GlobalEducationFunnel data={data({ grade: null })} />);
    expect(screen.getByText("150 students · 80 students on the global education pathway")).toBeTruthy();
  });
});

describe("GlobalEducationStudentTable", () => {
  const base = "/school/coordinator/global-education";

  it("renders a captioned table with row headers and the high-level columns only", () => {
    render(<GlobalEducationStudentTable page={data().students} grade="12" basePath={base} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Student", "Student ID", "Grade", "Furthest stage", "Visa", "Applications"]);
    expect(within(table).getByRole("rowheader", { name: "Student 1" })).toBeTruthy();
    expect(within(table).getByText("Documentation")).toBeTruthy();
    expect(within(table).getAllByText("—")).toHaveLength(1); // no visa case
    expect(within(table).getByText(/Global education students, 80 students/)).toBeTruthy();
  });

  it("has a labelled grade select inside a GET form that keeps the page URL", () => {
    render(<GlobalEducationStudentTable page={data().students} grade="12" basePath={base} />);
    const select = screen.getByLabelText("Grade") as HTMLSelectElement;
    expect(select.value).toBe("12");
    expect(select.closest("form")?.getAttribute("method")).toBe("get");
    expect(select.closest("form")?.getAttribute("action")).toBe(`${base}#students`);
  });

  it("pages forward with the grade kept", () => {
    render(<GlobalEducationStudentTable page={data().students} grade="12" basePath={base} />);
    expect(screen.getByRole("link", { name: "Next page" }).getAttribute("href")).toBe(`${base}?grade=12&offset=25#students`);
    expect(screen.queryByRole("link", { name: "Previous page" })).toBeNull();
  });

  it("empty school, empty grade and past-end each say so", () => {
    const empty = { items: [], total: 0, limit: 25, offset: 0 };
    const { rerender } = render(<GlobalEducationStudentTable page={empty} grade="" basePath={base} />);
    expect(screen.getByText("No students from this school are on the global education pathway yet. Students appear here once an EduSphere counselor links their application.")).toBeTruthy();
    rerender(<GlobalEducationStudentTable page={empty} grade="11" basePath={base} />);
    expect(screen.getByText("No students in this grade are on the global education pathway.")).toBeTruthy();
    rerender(<GlobalEducationStudentTable page={{ items: [], total: 30, limit: 25, offset: 100 }} grade="" basePath={base} />);
    expect(screen.getByText("This page is past the end of the list.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Previous page" }).getAttribute("href")).toBe(`${base}?offset=25#students`);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run (from `apps/web`): `npx vitest run tests/components/GlobalEducationPipeline.test.tsx`
Expected: FAIL — cannot resolve `@/components/GlobalEducationFunnel`.

- [ ] **Step 3: Append the types** to `apps/web/lib/types.ts`

```ts
// ENH-017 (DEC-SCOPE-036): GET /school/global-education/pipeline -- high-level stage only (School CRM.md §19).
export type PipelineStudentRow = { school_student_id: string; full_name: string; student_code: string; grade: string; furthest_stage: string; furthest_stage_label: string; visa_stage_label: string | null; application_count: number };
export type GlobalEducationPipeline = {
  grade: number | null;
  students_in_scope: number;
  bridged_students: number;
  funnel: { key: string; label: string; count: number }[];
  not_tracked: { key: string; label: string; note: string }[];
  students: { items: PipelineStudentRow[]; total: number; limit: number; offset: number };
};
```

- [ ] **Step 4: Create `apps/web/components/GlobalEducationFunnel.tsx`**

```tsx
import { plural } from "@/lib/plural";
import type { GlobalEducationPipeline } from "@/lib/types";

// ENH-017 (School CRM.md §17/§19, DEC-SCOPE-036): the school's bridged students by the furthest high-level stage they reached.
// The count is the text; the bar is decoration sized against the pathway count, so nothing is conveyed by length alone. Stages
// with no data source say so -- never a fabricated 0 (DATA_MODEL.md §8).
const pct = (count: number, total: number) => (total > 0 ? Math.round((count / total) * 100) : 0);

export default function GlobalEducationFunnel({ data }: { data: GlobalEducationPipeline }) {
  const scope = `${plural(data.students_in_scope, "student")}${data.grade === null ? "" : ` in Grade ${data.grade}`}`;
  return (
    <div className="card">
      <h2>Pipeline</h2>
      <p>{scope} · {plural(data.bridged_students, "student")} on the global education pathway</p>
      <p className="muted">High-level stage only. Application details are handled by EduSphere&apos;s application team.</p>
      <ol className="pipeline-funnel" aria-label="Global education funnel">
        {data.funnel.map((stage) => (
          <li key={stage.key} className="pipeline-stage">
            <span className="pipeline-label">{stage.label}</span>
            <span className="pipeline-count">{stage.count.toLocaleString("en-IN")}</span>
            <span className="pipeline-track" aria-hidden="true"><span className="pipeline-fill" style={{ width: `${pct(stage.count, data.bridged_students)}%` }} /></span>
          </li>
        ))}
      </ol>
      {data.not_tracked.length > 0 && (
        <section aria-label="Not tracked yet" className="kpi-group">
          <h3>Not tracked yet</h3>
          <dl className="kpi-grid">
            {data.not_tracked.map((s) => (
              <div className="kpi-tile" key={s.key}>
                <dt>{s.label}</dt>
                <dd><span className="badge">Not tracked yet</span><span className="kpi-note muted">{s.note}</span></dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Create `apps/web/components/GlobalEducationStudentTable.tsx`**

```tsx
import { plural } from "@/lib/plural";
import type { GlobalEducationPipeline } from "@/lib/types";

// ENH-017: the per-student stage list, filtered and paged through the URL so it works without client JS (the ENH-016
// SchoolScorecardGrid pattern, including QA-016-06: Previous from past the end goes to the real last page). Names are plain
// text -- this view adds no new links into student records.
type Props = { page: GlobalEducationPipeline["students"]; grade: string; basePath: string };

export default function GlobalEducationStudentTable({ page, grade, basePath }: Props) {
  const pageHref = (offset: number) => {
    const params = new URLSearchParams();
    if (grade) params.set("grade", grade);
    if (offset > 0) params.set("offset", String(offset));
    const query = params.toString();
    return `${basePath}${query ? `?${query}` : ""}#students`;
  };
  const lastOffset = Math.max(0, Math.floor((page.total - 1) / page.limit) * page.limit);
  const pastEnd = page.items.length === 0 && page.total > 0;
  const prev = page.offset === 0 ? null : pastEnd ? lastOffset : Math.max(0, page.offset - page.limit);
  const next = page.offset + page.limit < page.total ? page.offset + page.limit : null;
  const empty = pastEnd
    ? "This page is past the end of the list."
    : grade
      ? "No students in this grade are on the global education pathway."
      : "No students from this school are on the global education pathway yet. Students appear here once an EduSphere counselor links their application.";
  const shown = page.items.length === 0 ? plural(page.total, "student") : `${page.offset + 1}–${page.offset + page.items.length} of ${page.total}`;
  return (
    <div className="card" id="students">
      <h2>Students</h2>
      <form method="get" action={`${basePath}#students`} className="analytics-form">
        <div className="field">
          <label htmlFor="pipeline-grade">Grade</label>
          <select id="pipeline-grade" name="grade" defaultValue={grade}>
            <option value="">All grades</option>
            {["8", "9", "10", "11", "12"].map((g) => <option key={g} value={g}>Grade {g}</option>)}
          </select>
        </div>
        <button className="btn secondary" type="submit">Show</button>
      </form>
      {page.items.length === 0 ? (
        <p className="muted" role="status">{empty}</p>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <caption className="visually-hidden">Global education students, {plural(page.total, "student")}</caption>
            <thead>
              <tr><th scope="col">Student</th><th scope="col">Student ID</th><th scope="col">Grade</th><th scope="col">Furthest stage</th><th scope="col">Visa</th><th scope="col">Applications</th></tr>
            </thead>
            <tbody>
              {page.items.map((r) => (
                <tr key={r.school_student_id}>
                  <th scope="row">{r.full_name}</th>
                  <td>{r.student_code}</td>
                  <td>{/^\d+$/.test(r.grade) ? r.grade : "—"}</td>
                  <td>{r.furthest_stage_label}</td>
                  <td>{r.visa_stage_label ?? "—"}</td>
                  <td>{r.application_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <nav className="pager" aria-label="Student pages">
        {prev !== null && <a href={pageHref(prev)} aria-label="Previous page">← Previous</a>}
        <span className="muted">{shown}</span>
        {next !== null && <a href={pageHref(next)} aria-label="Next page">Next →</a>}
      </nav>
    </div>
  );
}
```

- [ ] **Step 6: Append the CSS** to `apps/web/app/globals.css` (existing variables only)

```css
/* ENH-017 Global Education pipeline (SCR-SCH-038) */
.pipeline-page h1 { font-size: 28px; margin-bottom: 16px; }
.pipeline-funnel { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 10px; }
.pipeline-stage { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 12px; align-items: baseline; }
.pipeline-label { color: var(--ink); font-weight: 600; min-width: 0; }
.pipeline-count { font-weight: 800; color: var(--ink); font-variant-numeric: tabular-nums; }
.pipeline-track { grid-column: 1 / -1; height: 8px; border-radius: 99px; background: var(--soft); border: 1px solid var(--line); overflow: hidden; }
.pipeline-fill { display: block; height: 100%; background: var(--blue); }
```

- [ ] **Step 7: Run to verify pass**

Run: `npx vitest run tests/components/GlobalEducationPipeline.test.tsx`
Expected: PASS. If the `within(table).getAllByText("—")` count differs, check the fixture grade — only the visa column of row 2
should render "—".

- [ ] **Step 8: Commit**

```bash
git add apps/web/lib/types.ts apps/web/components/GlobalEducationFunnel.tsx apps/web/components/GlobalEducationStudentTable.tsx apps/web/app/globals.css apps/web/tests/components/GlobalEducationPipeline.test.tsx
git commit -m "feat(enh-017): global education funnel and student table components"
```

---

### Task 5: Pages, loading states and navigation

**Files:**
- Create: `apps/web/components/GlobalEducationPage.tsx` (shared async renderer)
- Create: `apps/web/app/school/coordinator/global-education/page.tsx`, `.../loading.tsx`
- Create: `apps/web/app/school/principal/global-education/page.tsx`, `.../loading.tsx`
- Modify: `apps/web/lib/navigation.ts:37-38`
- Test: `apps/web/tests/components/GlobalEducationPage.test.tsx`

**Interfaces:**
- Consumes: Task 4 components and types; `serverApi`, `ApiError` (`@/lib/api`); `accessDenied`, `accessUnavailable`
  (`@/components/AccessUnavailable`); `SectionUnavailable`; `PortalShell`; `SCHOOL_NAV`.
- Produces: `renderGlobalEducationPage(role: "coordinator" | "principal", searchParams: Record<string, string | string[] | undefined>)`.

- [ ] **Step 1: Write the failing tests**

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CoordinatorPage from "@/app/school/coordinator/global-education/page";
import PrincipalPage from "@/app/school/principal/global-education/page";
import { ApiError, serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";

vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children, roleLabel }: { children: React.ReactNode; roleLabel: string }) => <div data-testid="shell" data-role={roleLabel}>{children}</div> }));

const user = (role: string) => ({ id: "u1", email: "u@example.local", full_name: "Test User", role, division: "overseas", profile: { school_id: "s1" } });
const pipeline = { grade: null, students_in_scope: 0, bridged_students: 0, funnel: [], not_tracked: [], students: { items: [], total: 0, limit: 25, offset: 0 } };
const params = (p: Record<string, string> = {}) => ({ searchParams: Promise.resolve(p) });

function serve(role: string, pipelineResult: unknown = pipeline) {
  const requested: string[] = [];
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    requested.push(path);
    if (path === "/api/v1/auth/me") return user(role) as never;
    if (path.startsWith("/api/v1/school/global-education/pipeline")) {
      if (pipelineResult instanceof Error) throw pipelineResult;
      return pipelineResult as never;
    }
    throw new Error(`unexpected request ${path}`);
  });
  return requested;
}

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

describe("Global education pages", () => {
  it("coordinator page renders inside the coordinator shell with an h1", async () => {
    serve("school_coordinator");
    render(await CoordinatorPage(params()));
    expect(screen.getByTestId("shell").dataset.role).toBe("School Coordinator");
    expect(screen.getByRole("heading", { level: 1, name: "Global education" })).toBeTruthy();
  });

  it("principal page renders inside the principal shell", async () => {
    serve("school_principal");
    render(await PrincipalPage(params()));
    expect(screen.getByTestId("shell").dataset.role).toBe("Principal");
  });

  it("each page refuses the other school role instead of a mislabelled shell", async () => {
    serve("school_principal");
    render(await CoordinatorPage(params()));
    expect(screen.getByText("School Coordinator role required")).toBeTruthy();
    cleanup();
    serve("school_coordinator");
    render(await PrincipalPage(params()));
    expect(screen.getByText("Principal role required")).toBeTruthy();
  });

  it("forwards digit-only grade/offset and drops anything else (Review Focus 5)", async () => {
    const requested = serve("school_coordinator");
    render(await CoordinatorPage(params({ grade: "12", offset: "25" })));
    expect(requested).toContain("/api/v1/school/global-education/pipeline?grade=12&offset=25");
    cleanup();
    const again = serve("school_coordinator");
    render(await CoordinatorPage(params({ grade: "abc", offset: "-5" })));
    expect(again).toContain("/api/v1/school/global-education/pipeline");
  });

  it("a pipeline failure keeps the shell and shows the section error", async () => {
    serve("school_coordinator", new ApiError("boom", 500));
    render(await CoordinatorPage(params()));
    expect(screen.getByTestId("shell")).toBeTruthy();
    expect(screen.getByText("This section couldn't load. Refresh to try again.")).toBeTruthy();
  });

  it("a 403 from the pipeline shows the access card", async () => {
    serve("school_coordinator", new ApiError("School Coordinator or Principal role required", 403));
    render(await CoordinatorPage(params()));
    expect(screen.getByText("Access unavailable")).toBeTruthy();
    expect(screen.queryByTestId("shell")).toBeNull();
  });

  it("nav lists Global Education for coordinator and principal only", () => {
    expect(SCHOOL_NAV.coordinator.map((i) => i.href)).toContain("/school/coordinator/global-education");
    expect(SCHOOL_NAV.principal.map((i) => [i.label, i.href])).toContainEqual(["Global Education", "/school/principal/global-education"]);
    expect(SCHOOL_NAV.teacher.map((i) => i.href)).not.toContain("/school/teacher/global-education");
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run tests/components/GlobalEducationPage.test.tsx`
Expected: FAIL — cannot resolve `@/app/school/coordinator/global-education/page`.

- [ ] **Step 3: Create `apps/web/components/GlobalEducationPage.tsx`**

```tsx
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import GlobalEducationFunnel from "@/components/GlobalEducationFunnel";
import GlobalEducationStudentTable from "@/components/GlobalEducationStudentTable";
import PortalShell from "@/components/PortalShell";
import SectionUnavailable from "@/components/SectionUnavailable";
import { ApiError, serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { GlobalEducationPipeline, User } from "@/lib/types";

// ENH-017 (SCR-SCH-038): one renderer for the Coordinator and Principal pages -- identical data, each page refusing the other
// role (QA-018-12 pattern). Only digit strings are forwarded from the URL, so a tampered ?grade= shows the unfiltered page
// rather than a 422 error card. A 401/403 is an access problem; any other failure keeps the shell and nav usable.
const ROLES = {
  coordinator: { role: "school_coordinator", label: "School Coordinator", denied: "School Coordinator role required" },
  principal: { role: "school_principal", label: "Principal", denied: "Principal role required" },
} as const;

const digits = (value: string | string[] | undefined) => (typeof value === "string" && /^\d+$/.test(value) ? value : "");

export async function renderGlobalEducationPage(key: keyof typeof ROLES, searchParams: Record<string, string | string[] | undefined>) {
  const { role, label, denied } = ROLES[key];
  const grade = digits(searchParams.grade);
  const offset = digits(searchParams.offset);
  const query = new URLSearchParams();
  if (grade) query.set("grade", grade);
  if (offset) query.set("offset", offset);
  const qs = query.toString();
  const url = `/api/v1/school/global-education/pipeline${qs ? `?${qs}` : ""}`;
  const [me, pipeline] = await Promise.allSettled([serverApi<User>("/api/v1/auth/me"), serverApi<GlobalEducationPipeline>(url)]);
  if (me.status === "rejected") return accessUnavailable(me.reason);
  const user = me.value;
  if (user.role !== role) return accessDenied(user, denied);
  if (pipeline.status === "rejected" && pipeline.reason instanceof ApiError && [401, 403].includes(pipeline.reason.status)) return accessUnavailable(pipeline.reason);
  return (
    <PortalShell nav={SCHOOL_NAV[key]} roleLabel={label} userName={user.full_name}>
      <div className="portal-content pipeline-page">
        <h1>Global education</h1>
        {pipeline.status === "fulfilled" ? (
          <>
            <GlobalEducationFunnel data={pipeline.value} />
            <GlobalEducationStudentTable page={pipeline.value.students} grade={grade} basePath={`/school/${key}/global-education`} />
          </>
        ) : (
          <SectionUnavailable title="Global education pipeline" />
        )}
      </div>
    </PortalShell>
  );
}
```

Check before writing: `grep -n "role:" apps/web/lib/types.ts | head -3` to confirm `User.role` is a string, and confirm the
coordinator feedback page's role label is `"School Coordinator"` and principal pages use `"Principal"` (both verified in the
spec audit).

- [ ] **Step 4: Create the pages**

`apps/web/app/school/coordinator/global-education/page.tsx`:

```tsx
import { renderGlobalEducationPage } from "@/components/GlobalEducationPage";

// ENH-017 (DEC-SCOPE-036, SCR-SCH-038): the Coordinator's Global Education pipeline.
export default async function SchoolCoordinatorGlobalEducationPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return renderGlobalEducationPage("coordinator", await searchParams);
}
```

`apps/web/app/school/principal/global-education/page.tsx`:

```tsx
import { renderGlobalEducationPage } from "@/components/GlobalEducationPage";

// ENH-017 (DEC-SCOPE-036, SCR-SCH-038): the Principal's read-only Global Education pipeline -- same data as the Coordinator's.
export default async function SchoolPrincipalGlobalEducationPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return renderGlobalEducationPage("principal", await searchParams);
}
```

`apps/web/app/school/coordinator/global-education/loading.tsx`:

```tsx
// ENH-017: shown while the server reads the pipeline, so navigation is never a blank screen (ENH-018 pattern).
export default function Loading() {
  return (
    <div className="portal-content" aria-busy="true" aria-label="Loading global education pipeline">
      <div className="card">
        {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
      </div>
    </div>
  );
}
```

`apps/web/app/school/principal/global-education/loading.tsx` (S1 — one skeleton, not a copy):

```tsx
// ENH-017: the Principal's page loads the same pipeline as the Coordinator's, so it shows the same skeleton.
export { default } from "@/app/school/coordinator/global-education/loading";
```

- [ ] **Step 5: Add the nav entries** in `apps/web/lib/navigation.ts`

```ts
  coordinator: ["dashboard", "students", "promotion", "transfers", "activities", "feedback", "team", "reports", "global-education", "entitlements", "notifications"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/coordinator/${x}` })),
  principal: ["dashboard", "reports", "global-education", "feedback", "entitlements", "notifications"].map(x => ({ label: x.replaceAll("-", " ").replace(/\b\w/g, c => c.toUpperCase()), href: `/school/principal/${x}` })),
```

(Only the string arrays change; the `.map(...)` expression stays byte-identical. The label becomes "Global Education".)

- [ ] **Step 6: Run to verify pass, then neighbours**

Run: `npx vitest run tests/components/GlobalEducationPage.test.tsx tests/components/GlobalEducationPipeline.test.tsx tests/components/PortalShell.test.tsx tests/lib/skills.test.ts tests/components/SchoolFeedbackPages.test.tsx tests/components/AccessUnavailable.test.tsx`
Expected: PASS. If any existing test snapshots the full coordinator/principal nav list, update only that expected array
and note it in the commit message.

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/GlobalEducationPage.tsx apps/web/app/school/coordinator/global-education apps/web/app/school/principal/global-education apps/web/lib/navigation.ts apps/web/tests/components/GlobalEducationPage.test.tsx
git commit -m "feat(enh-017): coordinator and principal global education pages with nav"
```

---

### Task 6: Playwright end-to-end spec

**Files:**
- Create: `apps/web/tests/e2e/enh-017-global-education.spec.ts`

**Interfaces:**
- Consumes: running stack (`docker compose up -d --build`, seeded), helpers `E2E_PASSWORD`, `createAndActivateFromUi`
  from `./helpers/welcome`; APIs `POST /api/v1/admin/universities`, `POST /api/v1/overseas-admin/school-students/{id}/applications`,
  `PATCH /api/v1/workflows/overseas/applications/{id}`.

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-017 (DEC-SCOPE-036): a Coordinator sees a bridged student's high-level stage on the Global Education page, and neither the
// page nor its API response carries application detail planted by the Overseas side (§19). Fixture steps use the admin APIs,
// as sch-010 does; the page under test is driven through the UI.

async function signIn(page: import("@playwright/test").Page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("coordinator sees high-level stage only for a bridged student (ENH-017)", async ({ page }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const coordinatorEmail = `enh017-e2e-coord-${unique}@example.local`;
  const studentName = `E2E ENH-017 Student ${unique}`;

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E ENH-017 School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E ENH-017 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.selectOption("#school-tier", "platinum");
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();
  const university = await page.request.post("/api/v1/admin/universities", { data: { country_slug: "usa", slug: `e2e-enh017-${unique}`, name: `PLANTED-UNI-${unique}` } });
  expect(university.ok()).toBeTruthy();
  const universityId = (await university.json()).id as string;

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "/school/coordinator/dashboard");
  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", studentName);
  await page.click('button:has-text("Add student")');
  await expect(page.getByRole("row", { name: new RegExp(studentName) })).toBeVisible();
  const studentHref = await page.getByRole("row", { name: new RegExp(studentName) }).getByRole("link", { name: "Timeline" }).getAttribute("href");
  const studentId = studentHref!.split("/").pop()!;

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  const bridged = await page.request.post(`/api/v1/overseas-admin/school-students/${studentId}/applications`, { data: { university_id: universityId, intake: "Fall 2027" } });
  expect(bridged.status()).toBe(201);
  const applicationId = (await bridged.json()).id as string;
  const patched = await page.request.patch(`/api/v1/workflows/overseas/applications/${applicationId}`, {
    data: { application_reference: `PLANTED-REF-${unique}`, next_action: `PLANTED-NEXT-${unique}`, notes: `PLANTED-NOTES-${unique}` },
  });
  expect(patched.ok()).toBeTruthy();
  expect((await page.request.get("/api/v1/school/global-education/pipeline")).status()).toBe(403); // overseas admin is not a school reader

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "/school/coordinator/dashboard");
  await page.getByRole("link", { name: "Global Education" }).first().click();
  await page.waitForURL("**/school/coordinator/global-education");
  await expect(page.getByRole("heading", { level: 1, name: "Global education" })).toBeVisible();
  const row = page.getByRole("row", { name: new RegExp(studentName) });
  await expect(row).toContainText("Global education pathway");
  await expect(page.getByRole("list", { name: "Global education funnel" })).toContainText("Global education pathway1");
  await expect(page.locator("body")).not.toContainText("PLANTED");

  const api = await page.request.get("/api/v1/school/global-education/pipeline");
  expect(api.status()).toBe(200);
  const text = await api.text();
  expect(text).not.toContain("PLANTED");
  expect(text).not.toContain(applicationId);

  await page.selectOption("#pipeline-grade", "12");
  await page.getByRole("button", { name: "Show" }).click();
  await page.waitForURL(/\/school\/coordinator\/global-education\?grade=12/);
  await expect(page.getByText("No students in this grade are on the global education pathway.")).toBeVisible(); // student has no grade
});
```

- [ ] **Step 2: Run it (stack rebuilt with Tasks 1–5)**

```bash
docker compose build api web && docker compose up -d --force-recreate api worker beat web
cd apps/web && npx playwright test tests/e2e/enh-017-global-education.spec.ts --workers=1
```

Expected: PASS. If the `admin/universities` response has no top-level `id`, read the shape with
`grep -n "def create_university" -A25 apps/api/app/api/admin.py` and adjust only the fixture line. If the funnel text match
fails on whitespace, use `toContainText(/Global education pathway\s*1/)`.

- [ ] **Step 3: Run the neighbouring specs**

```bash
npx playwright test tests/e2e/sch-010-overseas-bridge.spec.ts tests/e2e/enh-016-analytics.spec.ts tests/e2e/sch-001-school-portal-access.spec.ts --workers=1
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/web/tests/e2e/enh-017-global-education.spec.ts
git commit -m "test(enh-017): end-to-end coordinator pipeline with planted-detail check"
```

---

### Task 7: Traceability and architecture documentation

**Files (all Modify):** `docs/decisions/PRODUCT_DECISION_REGISTER.md`, `docs/architecture/API_CONTRACT.md`,
`docs/architecture/RBAC_MATRIX.md`, `docs/architecture/SECURITY_CONTROLS.md`, `docs/architecture/THREAT_MODEL.md`,
`docs/ux/SCREEN_CATALOG.md`, `docs/ux/screen_catalog.json`, `docs/ux/ROLE_NAVIGATION.md`,
`docs/features/FEATURE_ACCEPTANCE_CRITERIA.md`, `docs/quality/RTM.md`, `docs/delivery/ENHANCEMENT_BACKLOG.md`.

- [ ] **Step 1: Decision record.** Append after `DEC-SCOPE-035` in `PRODUCT_DECISION_REGISTER.md`, following the
  `DEC-SCOPE-034` entry's layout (read it first: `grep -n "DEC-SCOPE-034" docs/decisions/PRODUCT_DECISION_REGISTER.md`):
  title "DEC-SCOPE-036 - ENH-017 School-visible Global Education pipeline (provisional number)", Status `EXPLICIT_APPROVAL`
  (user, in-session, 2026-09-29), Evidence EVID-014 §16/§17/§19/§20, the D1–D10 table copied verbatim from spec §3, and the
  follow-ups list from spec §14.
- [ ] **Step 2: API contract.** Add an "ENH-017 addendum" row next to the ENH-016 school analytics rows:
  `GET /school/global-education/pipeline` — Coordinator, Principal — own school — query `grade` (8–12), `limit` (1–100),
  `offset` — response per spec §6 — high-level stage only (§19).
- [ ] **Step 3: RBAC matrix §2.12.** Add a row "Global Education pipeline (ENH-017)": coordinator ✓ read, principal ✓ read,
  teacher ✗, parent ✗, Edusphere/overseas roles ✗; note "per-student high-level stage only; application detail never in
  payload".
- [ ] **Step 4: Security controls §6A and threat model.** SECURITY_CONTROLS §6A row: "School roles reading the Overseas
  domain — column-level selects, allowlisted response, key-set and planted-value tests (ENH-017)". THREAT_MODEL: new entry
  "School roles reading Overseas application data" — threats: over-disclosure (§19), cross-school leakage; mitigations as
  spec §11; residual: no rate limiting, no AuditLog for reads (D9).
- [ ] **Step 5: Screens and navigation.** `SCREEN_CATALOG.md`: add `SCR-SCH-038` after `SCR-SCH-037` in the same format
  (Route `/school/{coordinator,principal}/global-education`; Roles; Entry point: sidebar "Global Education"; States: loading,
  empty, empty grade, past end, section error, access denied; Feature ENH-017). Mirror it in `screen_catalog.json` (copy
  the `SCR-SCH-037` object's keys). `ROLE_NAVIGATION.md`: add "Global Education" to the coordinator and principal nav lists.
- [ ] **Step 6: Acceptance criteria and RTM.** `FEATURE_ACCEPTANCE_CRITERIA.md`: ENH-017 addendum listing AC01–AC18 from
  the spec. `RTM.md`: ENH-017 addendum row after the ENH-016/ENH-027 rows: Evidence EVID-014 → DEC-SCOPE-036 → ENH-017 →
  AC01–AC18 → SCR-SCH-038 → `school_global_education.py` → `test_enh_017_global_education_pipeline.py`,
  `GlobalEducationPipeline.test.tsx`, `GlobalEducationPage.test.tsx`, `enh-017-global-education.spec.ts` → release evidence
  "pending browser QA and independent review".
- [ ] **Step 7: Backlog.** `ENHANCEMENT_BACKLOG.md`: L120 status "Built — pending browser QA/review"; §16–§20 rows (L926-930)
  point to the delivered scope and the follow-ups (scholarship, Top 100, alumni not tracked); fix the stale
  `schools.py:664` reference in the ENH-017 entry to `schools.py:972`; add a "Delivered scope (2026-09-29)" paragraph under
  the ENH-017 entry citing DEC-SCOPE-036 and the follow-ups.
- [ ] **Step 8: Verify no source evidence was touched and commit**

```bash
git diff --name-only | grep -c "^docs/sources/" || true   # expected 0
git add docs
git commit -m "docs(enh-017): decision record, contracts, RBAC, security, screens and RTM"
```

---

### Task 8: Full verification (no completion claim)

- [ ] **Step 1: API quality gates**

```bash
cd apps/api && python -m ruff check . && python -m mypy app
python -m pytest -q tests/test_enh_017_global_education_pipeline.py tests/test_sch_010_overseas_bridge.py tests/test_enh_016_contracts.py tests/test_enh_016_scorecard.py tests/test_enh_016_cross_school.py tests/test_enh_016_scope.py tests/test_enh_016_school_analytics.py tests/test_enh_016_performance.py tests/test_enh_013_360_view.py tests/test_sch_reports.py tests/test_enh_022_tier_enforcement.py tests/test_enh_023_tier_change.py tests/test_sch_007_parent_portal.py tests/test_sch_008_student_timeline.py tests/test_sch_001_school_portal_access.py tests/test_enh_001_academic_year.py
```

Expected: all PASS.

- [ ] **Step 2: Web quality gates**

```bash
cd apps/web && npm test && npm run typecheck && npm run lint && npm run build
```

Expected: all PASS.

- [ ] **Step 3: Confirm scope**

```bash
git diff --stat main...HEAD
git diff main...HEAD -- apps/api/app/api/schools.py apps/api/app/api/school_analytics.py apps/api/app/api/workflows.py apps/api/app/api/student_360.py apps/api/app/api/admin.py apps/api/alembic
```

Expected: the second command prints nothing.

- [ ] **Step 4: Report status as "implemented; pending browser QA and independent (Codex) review"** — do not mark ENH-017
  complete. Browser QA (`docs/quality/ENH-017_BROWSER_QA_*.md`, 320/768/1024/1440 px, keyboard, screen-reader labels) and the
  independent review are separate follow-on steps.
