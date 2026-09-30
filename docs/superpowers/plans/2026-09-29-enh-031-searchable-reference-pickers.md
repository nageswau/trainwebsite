# ENH-031 Searchable Reference Pickers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every student and application reference in EduSphere's forms becomes a searchable dropdown that can only submit a valid, role-scoped value.

**Architecture:** One read-only FastAPI router (`/api/v1/lookups/*`) whose five endpoints each reuse the scope rule of the write endpoint they feed, plus one accessible React combobox (`SearchableSelect`) with a load-once mode (existing, already-scoped option lists) and a server-search mode (the lookups). The chosen id travels in a hidden input under the field's existing `name`, so no write endpoint or request body changes.

**Tech Stack:** FastAPI + SQLAlchemy 2 async + Postgres (pytest, httpx ASGI client); Next.js App Router + React (Vitest + Testing Library); Playwright.

**Spec:** `docs/superpowers/specs/2026-09-29-enh-031-searchable-reference-pickers-design.md` (D1–D5, AC01–AC10). Read it before any task.

## Global Constraints

- Branch: `feature/agn-001-multi-tenant-agent-crm` (worktree `.claude/worktrees/agn-001`). Do not create another branch.
- No new dependency (web or API). No migration, table, column or index.
- No write endpoint's request or response changes. Every converted field keeps its `name` and submitted value.
- Lookup response shape: `{"items": [{"id", "label", "detail"}], "truncated": bool}`; `q` ≤ 100 chars, matched literally and case-insensitively (escaped `ILIKE`); `limit` default 20, range 1–50.
- Agent link (`purpose=link`): agent only; `q` ≥ 3 chars (else 422); at most 10 items; `detail` = masked email (`first char + "***@" + domain`); students already linked to the caller's agency excluded.
- Wrong role → 403 `"This role cannot use this lookup"`; pending/suspended/deactivated agents → the existing `rbac.agent_denial_reason` message.
- Lookup logging: logger `app.lookups`, message `lookup`, `extra_fields` exactly `{lookup, role, count, truncated}`; never the search text; never an `AuditLog` row.
- Field error text: `Choose a student from the list.` / `Choose an application from the list.` / `Choose a school from the list.` / `Choose a candidate from the list.`
- Status text: `Loading…`, `No matching students.` (per noun plural), `Type at least 3 characters.`, `Keep typing to narrow the list.`, `Could not load the students.` + a `Retry` button.
- Load-once mode renders at most 50 options; server mode debounces 250 ms and ignores stale replies.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Commands (run from the worktree root; the test images bake the source, so **rebuild before every run**):
  - API: `docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn001 --profile ci build api-test` then `docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn001 --profile ci run --rm api-test python -m pytest -q -p no:cacheprovider <files>`
  - Web: `docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn001 --profile ci build web-test` then `docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn001 --profile ci run --rm --no-deps web-test npx vitest run <files>`
  - The user controls the running app stack (`api`/`web` containers); ask them to rebuild it before E2E/browser work.

## Review Focus

1. **A form reset or a successful save leaves a stale pick behind** — after `ActionForm` resets, or a host clears its own state, the combobox must be empty and its hidden value blank. Pinned: Task 4 (form `reset` test), Task 7 (`AgentApplicationCreatePanel` remount-after-success test).
2. **Text that looks like a choice but was never picked** (user types a full name and presses Save) must not submit and must show the field error — also for the optional application field in document upload. Pinned: Task 4 (optional-field test).
3. **A student with a `%`/`_` in the name, or a search for `100%`** must match literally, not as a wildcard. Pinned: Task 1 (`test_q_is_matched_literally`).
4. **Bridged (School) applications have no `student_id`** — the applications lookup must still label them with the school student's name and must not drop them. Pinned: Task 2 (`test_bridged_application_uses_school_student_name`).
5. **Host pages already use `getByRole("status")`** — the combobox's live region must not add a second `role="status"` element. Pinned: Task 4 (`test`: no `role="status"` inside the component).

---

### Task 1: Lookups router and the overseas-students lookup

**Files:**
- Create: `apps/api/app/api/lookups.py`
- Modify: `apps/api/app/main.py` (import list and router tuple)
- Create: `apps/api/tests/enh031_helpers.py`
- Test: `apps/api/tests/test_enh_031_lookups_students.py`

**Interfaces:**
- Consumes: `app.api.deps.get_current_user`, `app.core.rbac.agent_denial_reason`, `app.services.agent_orgs.org_member_ids(user) -> Select`, test helpers `tests.agn001_helpers.{login, mk_active_org, mk_user, register_agent, uniq}`.
- Produces: `router` (prefix `/lookups`); module helpers `_pattern(q) -> str | None`, `_like(column, pattern)`, `_allow(user, roles: set[str]) -> None`, `_page(db, stmt, limit, to_item, lookup, user) -> dict`, `mask_email(email) -> str`; endpoint `GET /api/v1/lookups/overseas-students?q=&limit=&purpose=link`. Test helpers `mk_university(db, name=None) -> University`, `mk_application(db, *, student, university, counselor=None, agent=None, status="enquiry", course=None, reference=None) -> OverseasApplication`.

- [ ] **Step 1: Write the test helpers**

`apps/api/tests/enh031_helpers.py`:

```python
"""ENH-031 -- fixtures for the lookup tests."""

from app.models import Country, OverseasApplication, OverseasCourse, University
from tests.agn001_helpers import uniq


async def mk_university(db, name: str | None = None) -> University:
    country = Country(slug=uniq("e31-c"), name="Testland", overview="", tuition="", living_expenses="", visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[])
    db.add(country)
    await db.flush()
    university = University(country_id=country.id, slug=uniq("e31-u"), name=name or uniq("E31 Uni"), city="", overview="", eligibility="", requirements=[], deadlines=[], scholarships=[])
    db.add(university)
    await db.commit()
    return university


async def mk_course(db, university: University, title: str) -> OverseasCourse:
    course = OverseasCourse(university_id=university.id, title=title, level="Masters", category="Engineering", duration="1 year", tuition_fee="", intake="Sep")
    db.add(course)
    await db.commit()
    return course


async def mk_application(db, *, student=None, university, counselor=None, agent=None, status="enquiry", course=None, reference=None, school_student=None) -> OverseasApplication:
    application = OverseasApplication(
        student_id=student.id if student else None, school_student_id=school_student.id if school_student else None,
        university_id=university.id, course_id=course.id if course else None, counselor_id=counselor.id if counselor else None,
        agent_id=agent.id if agent else None, intake="Sep 2027", status=status, application_reference=reference,
    )
    db.add(application)
    await db.commit()
    return application
```

- [ ] **Step 2: Write the failing tests**

`apps/api/tests/test_enh_031_lookups_students.py`:

```python
"""ENH-031 (DEC-SCOPE-039) -- GET /lookups/overseas-students: scope per role, the agent link rules, q/limit, logging."""

import logging

import pytest
from sqlalchemy import func, select

from app.models import AgentStudent, AuditLog
from tests.agn001_helpers import login, mk_active_org, mk_user, register_agent, uniq
from tests.enh031_helpers import mk_application, mk_university

URL = "/api/v1/lookups/overseas-students"


async def students(db, tag: str, n: int) -> list:
    return [await mk_user(db, role="overseas_student", full_name=f"{tag} Student {i:02d}") for i in range(n)]


def ids(response) -> set[str]:
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


@pytest.mark.asyncio
async def test_admin_sees_every_overseas_student_matching_q_and_nobody_else(client, db_session):
    tag = uniq("e31")
    a, b = await students(db_session, tag, 2)
    await mk_user(db_session, role="counselor", full_name=f"{tag} Counselor")
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    assert ids(await client.get(URL, params={"q": tag})) == {str(a.id), str(b.id)}


@pytest.mark.asyncio
async def test_item_is_name_with_email_detail(client, db_session):
    tag = uniq("e31")
    (a,) = await students(db_session, tag, 1)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    response = await client.get(URL, params={"q": tag})
    assert response.json() == {"items": [{"id": str(a.id), "label": a.full_name, "detail": a.email}], "truncated": False}


@pytest.mark.asyncio
async def test_counselor_sees_only_students_on_own_applications(client, db_session):
    tag = uniq("e31")
    mine, other = await students(db_session, tag, 2)
    counselor = await mk_user(db_session, role="counselor")
    university = await mk_university(db_session)
    await mk_application(db_session, student=mine, university=university, counselor=counselor)
    await mk_application(db_session, student=other, university=university)
    await login(client, counselor.email)
    assert ids(await client.get(URL, params={"q": tag})) == {str(mine.id)}


@pytest.mark.asyncio
async def test_agent_sees_only_students_linked_to_its_agency(client, db_session):
    tag = uniq("e31")
    mine, theirs = await students(db_session, tag, 2)
    a = await mk_active_org(db_session, name=f"{tag} A")
    b = await mk_active_org(db_session, name=f"{tag} B")
    db_session.add_all([AgentStudent(agent_id=a["master"].id, student_id=mine.id), AgentStudent(agent_id=b["master"].id, student_id=theirs.id)])
    await db_session.commit()
    await login(client, a["master"].email)
    assert ids(await client.get(URL, params={"q": tag})) == {str(mine.id)}


@pytest.mark.asyncio
@pytest.mark.parametrize("q", [None, "ab", "  ab  "])
async def test_link_needs_three_characters(client, db_session, q):
    a = await mk_active_org(db_session)
    await login(client, a["master"].email)
    params = {"purpose": "link"} | ({"q": q} if q is not None else {})
    assert (await client.get(URL, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_link_masks_email_and_excludes_only_own_agency_links(client, db_session):
    tag = uniq("e31")
    linked_here, linked_elsewhere, free = await students(db_session, tag, 3)
    a = await mk_active_org(db_session, name=f"{tag} A")
    b = await mk_active_org(db_session, name=f"{tag} B")
    db_session.add_all([AgentStudent(agent_id=a["master"].id, student_id=linked_here.id), AgentStudent(agent_id=b["master"].id, student_id=linked_elsewhere.id)])
    await db_session.commit()
    await login(client, a["master"].email)
    items = (await client.get(URL, params={"purpose": "link", "q": tag})).json()["items"]
    assert {i["id"] for i in items} == {str(linked_elsewhere.id), str(free.id)}
    by_id = {i["id"]: i for i in items}
    assert by_id[str(free.id)]["detail"] == f"{free.email[0]}***@example.local"


@pytest.mark.asyncio
async def test_link_returns_at_most_ten(client, db_session):
    tag = uniq("e31")
    await students(db_session, tag, 12)
    a = await mk_active_org(db_session)
    await login(client, a["master"].email)
    body = (await client.get(URL, params={"purpose": "link", "q": tag, "limit": 50})).json()
    assert len(body["items"]) == 10 and body["truncated"] is True


@pytest.mark.asyncio
async def test_link_is_for_agents_only(client, db_session):
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    response = await client.get(URL, params={"purpose": "link", "q": "abc"})
    assert response.status_code == 403
    assert response.json()["detail"] == "This role cannot use this lookup"


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("university_rep", "overseas"), ("overseas_student", "overseas"), ("it_student", "it"), ("placement_team", "it")])
async def test_other_roles_are_refused(client, db_session, role, division):
    user = await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division)
    response = await client.get(URL, params={"q": "abc"})
    assert response.status_code == 403
    assert response.json()["detail"] == "This role cannot use this lookup"


@pytest.mark.asyncio
async def test_pending_agent_is_refused_by_the_agent_gate(client):
    await register_agent(client)
    response = await client.get(URL, params={"q": "abc"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Agent registration is pending approval"


@pytest.mark.asyncio
async def test_q_is_matched_literally(client, db_session):
    tag = uniq("e31")
    await mk_user(db_session, role="overseas_student", full_name=f"{tag} 1000 Plain")
    percent = await mk_user(db_session, role="overseas_student", full_name=f"{tag} 100% Sure")
    underscore = await mk_user(db_session, role="overseas_student", full_name=f"{tag} a_b")
    await mk_user(db_session, role="overseas_student", full_name=f"{tag} axb")
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    assert ids(await client.get(URL, params={"q": f"{tag} 100%"})) == {str(percent.id)}
    assert ids(await client.get(URL, params={"q": f"{tag} a_b"})) == {str(underscore.id)}


@pytest.mark.asyncio
async def test_limit_and_truncated(client, db_session):
    tag = uniq("e31")
    await students(db_session, tag, 3)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    two = (await client.get(URL, params={"q": tag, "limit": 2})).json()
    three = (await client.get(URL, params={"q": tag, "limit": 3})).json()
    assert (len(two["items"]), two["truncated"]) == (2, True)
    assert (len(three["items"]), three["truncated"]) == (3, False)
    assert [i["label"] for i in three["items"]] == sorted(i["label"] for i in three["items"])


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 51}, {"q": "x" * 101}, {"purpose": "browse"}])
async def test_bad_query_parameters_are_422(client, db_session, params):
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    assert (await client.get(URL, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_lookup_logs_counts_never_the_text_and_writes_no_audit_row(client, db_session, caplog):
    tag = uniq("e31")
    await students(db_session, tag, 1)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    audit_before = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id == admin.id))
    caplog.set_level(logging.INFO, logger="app.lookups")
    await client.get(URL, params={"q": tag})
    records = [r for r in caplog.records if r.name == "app.lookups"]
    assert records and records[-1].getMessage() == "lookup"
    assert records[-1].extra_fields == {"lookup": "overseas-students", "role": "overseas_admin", "count": 1, "truncated": False}
    assert tag not in caplog.text
    audit_after = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id == admin.id))
    assert audit_after == audit_before
```

- [ ] **Step 3: Run the tests to see them fail**

Run (API command from Global Constraints) with `tests/test_enh_031_lookups_students.py`.
Expected: every test FAILS with 404 (no `/lookups` route); the 422 parameter tests fail with 404 too.

- [ ] **Step 4: Implement the router**

`apps/api/app/api/lookups.py`:

```python
"""ENH-031 (DEC-SCOPE-039) -- read-only lookups behind the searchable reference pickers.

Every lookup applies the scope of the write endpoint it feeds (spec §5), so a picker never offers a value that write would
refuse. Reads only: one structured log line per call (counts, never the search text) and no AuditLog row (ENH-016 D15).
"""

import logging
from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rbac import agent_denial_reason
from app.models import AgentStudent, OverseasApplication, User
from app.services.agent_orgs import org_member_ids

logger = logging.getLogger("app.lookups")
router = APIRouter(prefix="/lookups", tags=["lookups"])

LINK_MIN_CHARS = 3
LINK_LIMIT = 10
FORBIDDEN = "This role cannot use this lookup"


def _pattern(q: str | None) -> str | None:
    """A literal, case-insensitive substring pattern for `ILIKE ... ESCAPE '\\'`, or None for no filter."""
    term = (q or "").strip()
    if not term:
        return None
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _like(column, pattern: str):
    return column.ilike(pattern, escape="\\")


def _allow(user: User, roles: set[str]) -> None:
    if user.role != "super_admin" and user.role not in roles:
        raise HTTPException(403, FORBIDDEN)
    reason = agent_denial_reason(user)
    if reason:
        raise HTTPException(403, reason)


async def _page(db: AsyncSession, stmt: Select, limit: int, to_item: Callable, lookup: str, user: User) -> dict:
    rows = (await db.execute(stmt.limit(limit + 1))).all()
    truncated = len(rows) > limit
    items = [to_item(row) for row in rows[:limit]]
    logger.info("lookup", extra={"extra_fields": {"lookup": lookup, "role": user.role, "count": len(items), "truncated": truncated}})
    return {"items": items, "truncated": truncated}


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


@router.get("/overseas-students")
async def overseas_students(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    purpose: Literal["link"] | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: every overseas student. Counselor: students of their own applications. Agent: students linked to their agency.
    `purpose=link` (agent only, D2): search-only (q >= 3 chars), at most 10, masked email, own agency's links left out."""
    stmt = select(User).where(User.role == "overseas_student")
    pattern = _pattern(q)
    if purpose == "link":
        if user.role != "agent":
            raise HTTPException(403, FORBIDDEN)
        _allow(user, {"agent"})
        if len((q or "").strip()) < LINK_MIN_CHARS:
            raise HTTPException(422, f"Type at least {LINK_MIN_CHARS} characters")
        limit = min(limit, LINK_LIMIT)
        stmt = stmt.where(User.id.not_in(select(AgentStudent.student_id).where(AgentStudent.agent_id.in_(org_member_ids(user)))))
    else:
        _allow(user, {"overseas_admin", "counselor", "agent"})
        if user.role == "counselor":
            stmt = stmt.where(User.id.in_(select(OverseasApplication.student_id).where(OverseasApplication.counselor_id == user.id)))
        elif user.role == "agent":
            stmt = stmt.where(User.id.in_(select(AgentStudent.student_id).where(AgentStudent.agent_id.in_(org_member_ids(user)))))
    if pattern:
        stmt = stmt.where(or_(_like(User.full_name, pattern), _like(User.email, pattern)))
    stmt = stmt.order_by(User.full_name, User.id)
    masked = purpose == "link"
    return await _page(
        db, stmt, limit,
        lambda row: {"id": row[0].id, "label": row[0].full_name, "detail": mask_email(row[0].email) if masked else row[0].email},
        "overseas-students", user,
    )
```

In `apps/api/app/main.py` add `lookups,` to the `from app.api import (...)` list (alphabetical, after `inbound,`) and add `lookups.router` to the router tuple right after `agent_team.router`.

- [ ] **Step 5: Run the tests to see them pass**

Run the same command. Expected: all tests in `test_enh_031_lookups_students.py` PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/lookups.py apps/api/app/main.py apps/api/tests/enh031_helpers.py apps/api/tests/test_enh_031_lookups_students.py
git commit -m "feat(enh-031): role-scoped overseas-students lookup, incl. the agent link search (DEC-SCOPE-039 D2)"
```

---

### Task 2: Overseas-applications and IT job-applications lookups

**Files:**
- Modify: `apps/api/app/api/lookups.py`
- Test: `apps/api/tests/test_enh_031_lookups_applications.py`

**Interfaces:**
- Consumes: Task 1 helpers (`_allow`, `_pattern`, `_like`, `_page`, `FORBIDDEN`), `app.core.identifiers.uuid_reference`, `tests.enh031_helpers`, `tests.enh016_helpers.{make_school, make_student}`.
- Produces: `GET /api/v1/lookups/overseas-applications?q=&limit=&student_id=` and `GET /api/v1/lookups/it-job-applications?q=&limit=`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/test_enh_031_lookups_applications.py`:

```python
"""ENH-031 (DEC-SCOPE-039) -- GET /lookups/overseas-applications (the _assigned_application scope) and /lookups/it-job-applications."""

import pytest

from app.models import Company, Job, JobApplication
from tests.agn001_helpers import login, mk_active_org, mk_user, uniq
from tests.enh016_helpers import make_school, make_student
from tests.enh031_helpers import mk_application, mk_course, mk_university

APPS = "/api/v1/lookups/overseas-applications"
JOBS = "/api/v1/lookups/it-job-applications"


def ids(response) -> set[str]:
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


async def two_applications(db, tag):
    """Two students, two universities; returns (student_a, app_a, student_b, app_b, uni_a)."""
    a = await mk_user(db, role="overseas_student", full_name=f"{tag} Alpha")
    b = await mk_user(db, role="overseas_student", full_name=f"{tag} Beta")
    uni_a = await mk_university(db, name=f"{tag} Uni A")
    uni_b = await mk_university(db, name=f"{tag} Uni B")
    return a, await mk_application(db, student=a, university=uni_a), b, await mk_application(db, student=b, university=uni_b), uni_a


@pytest.mark.asyncio
async def test_admin_sees_all_with_student_label_and_university_course_status_detail(client, db_session):
    tag = uniq("e31")
    student = await mk_user(db_session, role="overseas_student", full_name=f"{tag} Alpha")
    university = await mk_university(db_session, name=f"{tag} Uni")
    course = await mk_course(db_session, university, "MSc Data")
    with_course = await mk_application(db_session, student=student, university=university, course=course, status="offer")
    without = await mk_application(db_session, student=student, university=university)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    items = {i["id"]: i for i in (await client.get(APPS, params={"q": tag})).json()["items"]}
    assert items[str(with_course.id)] == {"id": str(with_course.id), "label": f"{tag} Alpha", "detail": f"{tag} Uni · MSc Data · offer"}
    assert items[str(without.id)]["detail"] == f"{tag} Uni · enquiry"


@pytest.mark.asyncio
async def test_q_matches_student_university_course_and_reference(client, db_session):
    tag = uniq("e31")
    student = await mk_user(db_session, role="overseas_student", full_name="Plain Name")
    university = await mk_university(db_session)
    course = await mk_course(db_session, university, f"{tag} Course")
    by_course = await mk_application(db_session, student=student, university=university, course=course)
    by_reference = await mk_application(db_session, student=student, university=university, reference=f"REF-{tag}")
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    assert ids(await client.get(APPS, params={"q": tag})) == {str(by_course.id), str(by_reference.id)}


@pytest.mark.asyncio
async def test_counselor_sees_only_own_applications(client, db_session):
    tag = uniq("e31")
    counselor = await mk_user(db_session, role="counselor")
    a = await mk_user(db_session, role="overseas_student", full_name=f"{tag} Alpha")
    university = await mk_university(db_session)
    mine = await mk_application(db_session, student=a, university=university, counselor=counselor)
    await mk_application(db_session, student=a, university=university)
    await login(client, counselor.email)
    assert ids(await client.get(APPS, params={"q": tag})) == {str(mine.id)}


@pytest.mark.asyncio
async def test_university_rep_sees_only_own_university(client, db_session):
    tag = uniq("e31")
    _, app_a, _, _, uni_a = await two_applications(db_session, tag)
    rep = await mk_user(db_session, role="university_rep", profile={"university_id": str(uni_a.id)})
    await login(client, rep.email)
    assert ids(await client.get(APPS, params={"q": tag})) == {str(app_a.id)}


@pytest.mark.asyncio
async def test_university_rep_without_a_university_sees_nothing(client, db_session):
    tag = uniq("e31")
    await two_applications(db_session, tag)
    rep = await mk_user(db_session, role="university_rep")
    await login(client, rep.email)
    assert ids(await client.get(APPS, params={"q": tag})) == set()


@pytest.mark.asyncio
async def test_agent_sees_only_its_agency_applications(client, db_session):
    tag = uniq("e31")
    a = await mk_active_org(db_session, name=f"{tag} A")
    b = await mk_active_org(db_session, name=f"{tag} B")
    student = await mk_user(db_session, role="overseas_student", full_name=f"{tag} Alpha")
    university = await mk_university(db_session)
    mine = await mk_application(db_session, student=student, university=university, agent=a["master"])
    await mk_application(db_session, student=student, university=university, agent=b["master"])
    await login(client, a["master"].email)
    assert ids(await client.get(APPS, params={"q": tag})) == {str(mine.id)}


@pytest.mark.asyncio
async def test_overseas_student_sees_only_own_applications(client, db_session):
    tag = uniq("e31")
    a, app_a, _, _, _ = await two_applications(db_session, tag)
    await login(client, a.email)
    assert ids(await client.get(APPS, params={"q": tag})) == {str(app_a.id)}


@pytest.mark.asyncio
async def test_student_id_narrows_to_that_student(client, db_session):
    tag = uniq("e31")
    a, app_a, _, _, _ = await two_applications(db_session, tag)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    assert ids(await client.get(APPS, params={"q": tag, "student_id": str(a.id)})) == {str(app_a.id)}


@pytest.mark.asyncio
async def test_bridged_application_uses_school_student_name(client, db_session):
    tag = uniq("e31")
    ctx = await make_school(db_session)
    school_student = await make_student(db_session, ctx, name=f"{tag} School Kid")
    await db_session.commit()
    university = await mk_university(db_session)
    bridged = await mk_application(db_session, school_student=school_student, university=university)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    items = (await client.get(APPS, params={"q": tag})).json()["items"]
    assert [(i["id"], i["label"]) for i in items] == [(str(bridged.id), f"{tag} School Kid")]


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("it_student", "it"), ("placement_team", "it"), ("trainer", "it")])
async def test_applications_lookup_refuses_other_roles(client, db_session, role, division):
    user = await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division)
    assert (await client.get(APPS)).status_code == 403


async def job_application(db, tag, *, candidate_name, title, company_name, status="applied"):
    candidate = await mk_user(db, role="it_student", division="it", full_name=candidate_name)
    company = Company(name=f"{company_name} {uniq('co')}")
    db.add(company)
    await db.flush()
    job = Job(company_id=company.id, title=title, location="Remote", description="", skills=[], status="open")
    db.add(job)
    await db.flush()
    application = JobApplication(job_id=job.id, student_id=candidate.id, status=status)
    db.add(application)
    await db.commit()
    return application, company


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["placement_team", "hr_team", "it_admin"])
async def test_it_team_sees_job_applications_with_title_company_status(client, db_session, role):
    tag = uniq("e31")
    application, company = await job_application(db_session, tag, candidate_name=f"{tag} Candidate", title="Backend Engineer", company_name="Acme")
    user = await mk_user(db_session, role=role, division="it")
    await login(client, user.email, "it")
    items = (await client.get(JOBS, params={"q": tag})).json()["items"]
    assert items == [{"id": str(application.id), "label": f"{tag} Candidate", "detail": f"Backend Engineer · {company.name} · applied"}]


@pytest.mark.asyncio
async def test_job_applications_match_title_and_company(client, db_session):
    tag = uniq("e31")
    by_title, _ = await job_application(db_session, tag, candidate_name="Someone", title=f"{tag} Role", company_name="Acme")
    by_company, _ = await job_application(db_session, tag, candidate_name="Other", title="Role", company_name=f"{tag} Corp")
    user = await mk_user(db_session, role="placement_team", division="it")
    await login(client, user.email, "it")
    assert ids(await client.get(JOBS, params={"q": tag})) == {str(by_title.id), str(by_company.id)}


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("it_student", "it"), ("trainer", "it"), ("overseas_admin", "overseas"), ("counselor", "overseas")])
async def test_job_applications_lookup_refuses_other_roles(client, db_session, role, division):
    user = await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division)
    assert (await client.get(JOBS)).status_code == 403
```

- [ ] **Step 2: Run to see them fail**

Run the API command with `tests/test_enh_031_lookups_applications.py`. Expected: FAIL with 404 on every request.

- [ ] **Step 3: Implement both endpoints** (append to `apps/api/app/api/lookups.py`; extend the imports)

Change the imports to:

```python
from uuid import UUID

from sqlalchemy import Select, false, func, or_, select

from app.core.identifiers import uuid_reference
from app.models import AgentStudent, Company, Job, JobApplication, OverseasApplication, OverseasCourse, SchoolStudent, University, User
```

Append:

```python
def _join(*parts) -> str:
    return " · ".join(part for part in parts if part)


@router.get("/overseas-applications")
async def overseas_applications(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    student_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """workflows._assigned_application's rule: student own; counselor own; university_rep own university; agent own agency;
    admin all. Bridged (School) applications have no student_id and are labelled with the school student's name."""
    _allow(user, {"overseas_student", "counselor", "university_rep", "agent", "overseas_admin"})
    student_name = func.coalesce(User.full_name, SchoolStudent.full_name)
    stmt = (
        select(OverseasApplication, student_name, University.name, OverseasCourse.title)
        .join(University, University.id == OverseasApplication.university_id)
        .outerjoin(OverseasCourse, OverseasCourse.id == OverseasApplication.course_id)
        .outerjoin(User, User.id == OverseasApplication.student_id)
        .outerjoin(SchoolStudent, SchoolStudent.id == OverseasApplication.school_student_id)
    )
    if user.role == "overseas_student":
        stmt = stmt.where(OverseasApplication.student_id == user.id)
    elif user.role == "counselor":
        stmt = stmt.where(OverseasApplication.counselor_id == user.id)
    elif user.role == "agent":
        stmt = stmt.where(OverseasApplication.agent_id.in_(org_member_ids(user)))
    elif user.role == "university_rep":
        university_id = uuid_reference(user.profile.get("university_id"), "university reference", required=False)
        stmt = stmt.where(OverseasApplication.university_id == university_id if university_id else false())
    if student_id:
        stmt = stmt.where(OverseasApplication.student_id == student_id)
    pattern = _pattern(q)
    if pattern:
        stmt = stmt.where(or_(_like(student_name, pattern), _like(University.name, pattern), _like(OverseasCourse.title, pattern), _like(OverseasApplication.application_reference, pattern)))
    stmt = stmt.order_by(student_name, University.name, OverseasApplication.id)
    return await _page(
        db, stmt, limit,
        lambda row: {"id": row[0].id, "label": row[1] or "Unnamed student", "detail": _join(row[2], row[3], row[0].status)},
        "overseas-applications", user,
    )


@router.get("/it-job-applications")
async def it_job_applications(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every job application -- the scope schedule_interview / create offer accept today."""
    _allow(user, {"placement_team", "hr_team", "it_admin"})
    stmt = (
        select(JobApplication, User.full_name, Job.title, Company.name)
        .join(User, User.id == JobApplication.student_id)
        .join(Job, Job.id == JobApplication.job_id)
        .join(Company, Company.id == Job.company_id)
    )
    pattern = _pattern(q)
    if pattern:
        stmt = stmt.where(or_(_like(User.full_name, pattern), _like(Job.title, pattern), _like(Company.name, pattern)))
    stmt = stmt.order_by(User.full_name, JobApplication.id)
    return await _page(
        db, stmt, limit,
        lambda row: {"id": row[0].id, "label": row[1], "detail": _join(row[2], row[3], row[0].status)},
        "it-job-applications", user,
    )
```

- [ ] **Step 4: Run to see them pass**

Run the API command with `tests/test_enh_031_lookups_applications.py tests/test_enh_031_lookups_students.py`. Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/lookups.py apps/api/tests/test_enh_031_lookups_applications.py
git commit -m "feat(enh-031): overseas-applications and it-job-applications lookups with their write scopes"
```

---

### Task 3: Schools and school-students lookups (the bridge, D4)

**Files:**
- Modify: `apps/api/app/api/lookups.py`
- Test: `apps/api/tests/test_enh_031_lookups_schools.py`

**Interfaces:**
- Consumes: Task 1/2 helpers; `tests.enh016_helpers.{make_school, make_student}`.
- Produces: `GET /api/v1/lookups/schools?q=&limit=` and `GET /api/v1/lookups/school-students?school_id=&q=&limit=` (roles overseas_admin, counselor, super_admin — the existing bridge lookup's roles).

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/test_enh_031_lookups_schools.py`:

```python
"""ENH-031 (DEC-SCOPE-039 D4) -- pick a school, then search only that school's students."""

import uuid

import pytest

from tests.agn001_helpers import login, mk_active_org, mk_user, uniq
from tests.enh016_helpers import make_school, make_student

SCHOOLS = "/api/v1/lookups/schools"
STUDENTS = "/api/v1/lookups/school-students"


@pytest.mark.asyncio
async def test_schools_match_name_or_code_with_code_detail(client, db_session):
    tag = uniq("e31")
    ctx = await make_school(db_session, name=f"{tag} Hill School", school_code="E31H0001")
    await db_session.commit()
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    by_name = (await client.get(SCHOOLS, params={"q": tag})).json()["items"]
    by_code = (await client.get(SCHOOLS, params={"q": "e31h0001"})).json()["items"]
    expected = [{"id": str(ctx["school"].id), "label": f"{tag} Hill School", "detail": "E31H0001"}]
    assert by_name == expected and by_code == expected


@pytest.mark.asyncio
async def test_school_students_only_from_the_chosen_school(client, db_session):
    tag = uniq("e31")
    here = await make_school(db_session)
    there = await make_school(db_session)
    kid = await make_student(db_session, here, name=f"{tag} Kid", grade_or_class="Grade 5")
    await make_student(db_session, there, name=f"{tag} Other Kid")
    await db_session.commit()
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    items = (await client.get(STUDENTS, params={"school_id": str(here["school"].id), "q": tag})).json()["items"]
    assert items == [{"id": str(kid.id), "label": f"{tag} Kid", "detail": f"Grade 5 · {kid.student_code}"}]


@pytest.mark.asyncio
async def test_school_students_match_student_code(client, db_session):
    here = await make_school(db_session)
    kid = await make_student(db_session, here)
    await db_session.commit()
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    items = (await client.get(STUDENTS, params={"school_id": str(here["school"].id), "q": kid.student_code.lower()})).json()["items"]
    assert [i["id"] for i in items] == [str(kid.id)]


@pytest.mark.asyncio
async def test_school_id_is_required_and_must_exist(client, db_session):
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    assert (await client.get(STUDENTS)).status_code == 422
    missing = await client.get(STUDENTS, params={"school_id": str(uuid.uuid4())})
    assert missing.status_code == 404 and missing.json()["detail"] == "School not found"


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [SCHOOLS, STUDENTS])
@pytest.mark.parametrize("role, division", [("university_rep", "overseas"), ("overseas_student", "overseas"), ("it_admin", "it")])
async def test_bridge_lookups_refuse_other_roles(client, db_session, url, role, division):
    user = await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division)
    response = await client.get(url, params={"school_id": str(uuid.uuid4())})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_bridge_lookups_refuse_agents(client, db_session):
    a = await mk_active_org(db_session)
    await login(client, a["master"].email)
    assert (await client.get(SCHOOLS)).status_code == 403
```

- [ ] **Step 2: Run to see them fail**

Run the API command with `tests/test_enh_031_lookups_schools.py`. Expected: FAIL with 404.

- [ ] **Step 3: Implement** (append to `lookups.py`; add `School` to the `app.models` import)

```python
@router.get("/schools")
async def schools(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The School->Overseas bridge's first step (D4): every partner school, for the bridge's roles."""
    _allow(user, {"overseas_admin", "counselor"})
    stmt = select(School)
    pattern = _pattern(q)
    if pattern:
        stmt = stmt.where(or_(_like(School.name, pattern), _like(School.school_code, pattern)))
    stmt = stmt.order_by(School.name, School.id)
    return await _page(db, stmt, limit, lambda row: {"id": row[0].id, "label": row[0].name, "detail": row[0].school_code}, "schools", user)


@router.get("/school-students")
async def school_students(
    school_id: UUID,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The bridge's second step (D4): students of ONE chosen school only -- no cross-school name browsing."""
    _allow(user, {"overseas_admin", "counselor"})
    if await db.get(School, school_id) is None:
        raise HTTPException(404, "School not found")
    stmt = select(SchoolStudent).where(SchoolStudent.school_id == school_id)
    pattern = _pattern(q)
    if pattern:
        stmt = stmt.where(or_(_like(SchoolStudent.full_name, pattern), _like(SchoolStudent.student_code, pattern)))
    stmt = stmt.order_by(SchoolStudent.full_name, SchoolStudent.id)
    return await _page(
        db, stmt, limit,
        lambda row: {"id": row[0].id, "label": row[0].full_name, "detail": _join(row[0].grade_or_class, row[0].student_code)},
        "school-students", user,
    )
```

- [ ] **Step 4: Run to see them pass**

Run the API command with all three `tests/test_enh_031_lookups_*.py` files. Expected: all PASS. Then `ruff check app/api/lookups.py` inside the api-test container: `... run --rm api-test ruff check app/api/lookups.py` → `All checks passed!`.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/lookups.py apps/api/tests/test_enh_031_lookups_schools.py
git commit -m "feat(enh-031): schools and school-students lookups for the School->Overseas bridge (D4)"
```

---

### Task 4: `SearchableSelect` component and the lookups client

**Files:**
- Create: `apps/web/lib/lookups.ts`
- Create: `apps/web/components/SearchableSelect.tsx`
- Modify: `apps/web/app/globals.css` (append the `.combo` rules)
- Create: `apps/web/tests/helpers/pickOption.ts`
- Test: `apps/web/tests/components/SearchableSelect.test.tsx`, `apps/web/tests/lib/lookups.test.ts`

**Interfaces:**
- Produces (`lib/lookups.ts`): `type PickOption = { id: string; label: string; detail?: string | null }`, `type LookupPage = { items: PickOption[]; truncated: boolean }`, `type LookupName = "overseas-students" | "overseas-applications" | "it-job-applications" | "schools" | "school-students"`, `optionText(option: PickOption): string`, `lookupSearch(name: LookupName, params?: Record<string, string | undefined>): (q: string, signal: AbortSignal) => Promise<LookupPage>`.
- Produces (`components/SearchableSelect.tsx`): default export `SearchableSelect(props: { label: string; noun: Noun; id?: string; name?: string; required?: boolean; disabled?: boolean; options?: PickOption[]; search?: (q, signal) => Promise<LookupPage>; minChars?: number; onChange?: (option: PickOption | null) => void })`; `type Noun = "student" | "application" | "school" | "candidate"`; `filterOptions(options, text): LookupPage`; `MAX_RENDERED = 50`; `DEBOUNCE_MS = 250`. Each option `<li>` carries `data-value={option.id}`; the listbox id is `${id}-list`.
- Produces (`tests/helpers/pickOption.ts`): `pickOption(scope: Pick<typeof screen, "getByRole">, label: string, value: string): void`.

- [ ] **Step 1: Write the failing tests**

`apps/web/tests/lib/lookups.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { lookupSearch, optionText } from "@/lib/lookups";

afterEach(() => vi.unstubAllGlobals());

describe("lookups client (ENH-031)", () => {
  it("builds the lookup URL with q, limit and non-empty params", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], truncated: false })));
    vi.stubGlobal("fetch", fetchMock);
    await lookupSearch("overseas-applications", { student_id: "s1", empty: undefined })("Asha", new AbortController().signal);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/lookups/overseas-applications?limit=20&q=Asha&student_id=s1");
  });

  it("omits q when blank and throws on a failed response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(lookupSearch("schools")("", new AbortController().signal)).rejects.toThrow("Lookup failed (403)");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/lookups/schools?limit=20");
  });

  it("joins label and detail for display", () => {
    expect(optionText({ id: "1", label: "Asha", detail: "asha@example.local" })).toBe("Asha — asha@example.local");
    expect(optionText({ id: "1", label: "Asha" })).toBe("Asha");
  });
});
```

`apps/web/tests/components/SearchableSelect.test.tsx`:

```tsx
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SearchableSelect, { DEBOUNCE_MS } from "@/components/SearchableSelect";
import type { LookupPage } from "@/lib/lookups";

const OPTIONS = [
  { id: "s1", label: "Asha Rao", detail: "Hill School" },
  { id: "s2", label: "Ravi Iyer", detail: "Lake School" },
  { id: "s3", label: "Meera Das", detail: "Hill School" },
];

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function inForm(ui: React.ReactNode) {
  render(<form data-testid="form">{ui}</form>);
  return { form: screen.getByTestId("form") as HTMLFormElement, input: screen.getByRole("combobox") as HTMLInputElement };
}

const hidden = (form: HTMLFormElement, name: string) => new FormData(form).get(name);

describe("SearchableSelect load-once mode", () => {
  it("filters by label or detail and submits only the picked id", () => {
    const { form, input } = inForm(<SearchableSelect label="Student" name="school_student_id" noun="student" options={OPTIONS} />);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "hill" } });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Asha Rao — Hill School", "Meera Das — Hill School"]);
    fireEvent.click(screen.getByRole("option", { name: "Meera Das — Hill School" }));
    expect(input.value).toBe("Meera Das — Hill School");
    expect(hidden(form, "school_student_id")).toBe("s3");
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it("supports the keyboard: ArrowDown moves, Enter picks, Escape closes", () => {
    const { form, input } = inForm(<SearchableSelect label="Student" name="sid" noun="student" options={OPTIONS} />);
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input.getAttribute("aria-activedescendant")).toBe(screen.getAllByRole("option")[1].id);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(hidden(form, "sid")).toBe("s2");
    fireEvent.change(input, { target: { value: "a" } });
    expect(input).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it("wires the combobox to its listbox", () => {
    const { input } = inForm(<SearchableSelect id="psych-student" label="Student" noun="student" options={OPTIONS} />);
    expect(input.id).toBe("psych-student");
    expect(input.getAttribute("aria-controls")).toBe("psych-student-list");
    fireEvent.focus(input);
    expect(screen.getByRole("listbox", { name: "Student" }).id).toBe("psych-student-list");
  });

  it("a required field without a pick is invalid and shows the field error", () => {
    const { form, input } = inForm(<SearchableSelect label="Student" name="sid" required noun="student" options={OPTIONS} />);
    let valid = true;
    act(() => { valid = form.checkValidity(); });
    expect(valid).toBe(false);
    expect(screen.getByText("Choose a student from the list.")).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("an optional field is valid when empty but not with unpicked text", () => {
    const { form, input } = inForm(<SearchableSelect label="Application" name="aid" noun="application" options={OPTIONS} />);
    let valid = false;
    act(() => { valid = form.checkValidity(); });
    expect(valid).toBe(true);
    fireEvent.change(input, { target: { value: "Asha Rao" } });
    act(() => { valid = form.checkValidity(); });
    expect(valid).toBe(false);
    expect(screen.getByText("Choose an application from the list.")).toBeInTheDocument();
  });

  it("editing after a pick clears the pick and tells the host", () => {
    const onChange = vi.fn();
    const { form, input } = inForm(<SearchableSelect label="Student" name="sid" noun="student" options={OPTIONS} onChange={onChange} />);
    fireEvent.focus(input);
    fireEvent.click(screen.getByRole("option", { name: "Asha Rao — Hill School" }));
    expect(onChange).toHaveBeenLastCalledWith(OPTIONS[0]);
    fireEvent.change(input, { target: { value: "Asha Ra" } });
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(hidden(form, "sid")).toBe("");
  });

  it("a form reset clears the text and the pick", () => {
    const { form, input } = inForm(<SearchableSelect label="Student" name="sid" noun="student" options={OPTIONS} />);
    fireEvent.focus(input);
    fireEvent.click(screen.getByRole("option", { name: "Asha Rao — Hill School" }));
    act(() => form.reset());
    expect(input.value).toBe("");
    expect(hidden(form, "sid")).toBe("");
  });

  it("renders at most 50 options and asks to keep typing", () => {
    const many = Array.from({ length: 60 }, (_, i) => ({ id: `s${i}`, label: `Student ${i}` }));
    const { input } = inForm(<SearchableSelect label="Student" noun="student" options={many} />);
    fireEvent.focus(input);
    expect(screen.getAllByRole("option")).toHaveLength(50);
    expect(screen.getByText("Keep typing to narrow the list.")).toBeInTheDocument();
  });

  it("says when nothing matches, and never adds a role=status element", () => {
    const { input } = inForm(<SearchableSelect label="Student" noun="student" options={OPTIONS} />);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "zzz" } });
    expect(screen.getByText("No matching students.")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("SearchableSelect server mode", () => {
  const page = (...labels: string[]): LookupPage => ({ items: labels.map((label, i) => ({ id: `r${i}`, label })), truncated: false });

  it("waits for minChars, then searches once after the debounce", async () => {
    vi.useFakeTimers();
    const search = vi.fn().mockResolvedValue(page("Asha Rao"));
    const { input } = inForm(<SearchableSelect label="Overseas student reference" noun="student" search={search} minChars={3} />);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "as" } });
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    expect(search).not.toHaveBeenCalled();
    expect(screen.getByText("Type at least 3 characters.")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "ash" } });
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    expect(search).toHaveBeenCalledTimes(1);
    expect(search.mock.calls[0][0]).toBe("ash");
    expect(screen.getByRole("option", { name: "Asha Rao" })).toBeInTheDocument();
  });

  it("ignores a slow reply for an older query", async () => {
    vi.useFakeTimers();
    let resolveOld: (value: LookupPage) => void = () => {};
    const search = vi.fn()
      .mockImplementationOnce(() => new Promise<LookupPage>((resolve) => { resolveOld = resolve; }))
      .mockResolvedValueOnce(page("New Result"));
    const { input } = inForm(<SearchableSelect label="Student" noun="student" search={search} />);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "old" } });
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    fireEvent.change(input, { target: { value: "new" } });
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    await act(async () => { resolveOld(page("Old Result")); });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["New Result"]);
  });

  it("shows a failure with Retry, and Retry searches again", async () => {
    vi.useFakeTimers();
    const search = vi.fn().mockRejectedValueOnce(new Error("down")).mockResolvedValueOnce(page("Asha Rao"));
    const { input } = inForm(<SearchableSelect label="Student" noun="student" search={search} />);
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "ash" } });
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    expect(screen.getByText("Could not load the students.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    expect(search).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("option", { name: "Asha Rao" })).toBeInTheDocument();
  });

  it("reports a truncated result", async () => {
    vi.useFakeTimers();
    const search = vi.fn().mockResolvedValue({ ...page("Asha Rao"), truncated: true });
    const { input } = inForm(<SearchableSelect label="Student" noun="student" search={search} />);
    fireEvent.focus(input);
    await act(async () => { vi.advanceTimersByTime(DEBOUNCE_MS); });
    expect(screen.getByText("Keep typing to narrow the list.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to see them fail**

Run the web command with `tests/lib/lookups.test.ts tests/components/SearchableSelect.test.tsx`. Expected: FAIL — `Failed to resolve import "@/lib/lookups"` / `"@/components/SearchableSelect"`.

- [ ] **Step 3: Implement `lib/lookups.ts`**

```ts
// ENH-031 (DEC-SCOPE-039): the client side of the role-scoped read-only lookups (GET /api/v1/lookups/*) behind
// SearchableSelect. The server decides what each role may see; this only builds the request.
export type PickOption = { id: string; label: string; detail?: string | null };
export type LookupPage = { items: PickOption[]; truncated: boolean };
export type LookupName = "overseas-students" | "overseas-applications" | "it-job-applications" | "schools" | "school-students";

export function optionText(option: PickOption): string {
  return option.detail ? `${option.label} — ${option.detail}` : option.label;
}

export function lookupSearch(name: LookupName, params: Record<string, string | undefined> = {}) {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: "20" });
    if (q) query.set("q", q);
    for (const [key, value] of Object.entries(params)) if (value) query.set(key, value);
    const response = await fetch(`/api/v1/lookups/${name}?${query}`, { signal });
    if (!response.ok) throw new Error(`Lookup failed (${response.status})`);
    return (await response.json()) as LookupPage;
  };
}
```

- [ ] **Step 4: Implement `components/SearchableSelect.tsx`**

```tsx
"use client";

import { type ChangeEvent, type KeyboardEvent, useEffect, useId, useRef, useState } from "react";

import { type LookupPage, optionText, type PickOption } from "@/lib/lookups";

// ENH-031 (DEC-SCOPE-039): an accessible searchable dropdown (WAI-ARIA 1.2 combobox) that only ever submits a picked value.
// Load-once mode filters `options` in the browser; server mode calls `search` (debounced; a reply for an older query is
// dropped). The chosen id travels in a hidden input under `name`, so the host form's FormData and its API are unchanged.
// Validity uses the constraint API: an unpicked required field, or text that is not a pick, blocks the form's submit and
// shows a field error. Status text uses aria-live (not role="status"): host pages already query their own status region.

export type Noun = "student" | "application" | "school" | "candidate";
const PLURAL: Record<Noun, string> = { student: "students", application: "applications", school: "schools", candidate: "candidates" };
export const MAX_RENDERED = 50;
export const DEBOUNCE_MS = 250;

type Props = {
  label: string;
  noun: Noun;
  id?: string;
  name?: string;
  required?: boolean;
  disabled?: boolean;
  options?: PickOption[];
  search?: (q: string, signal: AbortSignal) => Promise<LookupPage>;
  minChars?: number;
  onChange?: (option: PickOption | null) => void;
};

export function filterOptions(options: PickOption[], text: string): LookupPage {
  const needle = text.trim().toLowerCase();
  const matches = needle ? options.filter((option) => optionText(option).toLowerCase().includes(needle)) : options;
  return { items: matches.slice(0, MAX_RENDERED), truncated: matches.length > MAX_RENDERED };
}

export default function SearchableSelect({ label, noun, id, name, required = false, disabled = false, options, search, minChars = 0, onChange }: Props) {
  const autoId = useId();
  const inputId = id ?? `combo-${autoId}`;
  const listId = `${inputId}-list`;
  const statusId = `${inputId}-status`;
  const errorId = `${inputId}-error`;
  const inputRef = useRef<HTMLInputElement>(null);
  // Hosts often pass inline functions; refs keep a re-render from restarting the search or firing stale callbacks.
  const searchRef = useRef(search);
  searchRef.current = search;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const serverMode = search !== undefined;

  const [text, setText] = useState("");
  const [selected, setSelected] = useState<PickOption | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [remote, setRemote] = useState<LookupPage | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "failed">("idle");
  const [retries, setRetries] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const query = selected ? "" : text.trim();
  const tooShort = serverMode && query.length < minChars;
  const page: LookupPage | null = serverMode ? (tooShort ? null : remote) : filterOptions(options ?? [], query);
  const items = page?.items ?? [];
  const invalidMessage = `Choose ${noun === "application" ? "an" : "a"} ${noun} from the list.`;
  const invalid = !selected && (required || text.trim() !== "");

  useEffect(() => {
    inputRef.current?.setCustomValidity(invalid ? invalidMessage : "");
  }, [invalid, invalidMessage]);

  useEffect(() => {
    if (!serverMode || !open || tooShort) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoadState("loading");
      searchRef.current!(query, controller.signal)
        .then((result) => {
          if (controller.signal.aborted) return;
          setRemote(result);
          setLoadState("idle");
        })
        .catch(() => {
          if (!controller.signal.aborted) setLoadState("failed");
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [serverMode, open, tooShort, query, retries]);

  useEffect(() => {
    const form = inputRef.current?.form;
    if (!form) return;
    const onReset = () => {
      setText("");
      setSelected(null);
      setError(null);
      setOpen(false);
      onChangeRef.current?.(null);
    };
    form.addEventListener("reset", onReset);
    return () => form.removeEventListener("reset", onReset);
  }, []);

  function pick(option: PickOption) {
    setSelected(option);
    setText(optionText(option));
    setOpen(false);
    setActive(-1);
    setError(null);
    onChangeRef.current?.(option);
  }

  function edit(event: ChangeEvent<HTMLInputElement>) {
    setText(event.target.value);
    setOpen(true);
    setActive(-1);
    setError(null);
    if (selected) {
      setSelected(null);
      onChangeRef.current?.(null);
    }
  }

  function keyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((index) => Math.min(index + 1, items.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter" && open && items[active]) {
      event.preventDefault();
      pick(items[active]);
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
      setActive(-1);
    }
  }

  let status = "";
  if (open && !selected) {
    if (tooShort) status = `Type at least ${minChars} characters.`;
    else if (serverMode && loadState === "loading") status = "Loading…";
    else if (serverMode && loadState === "failed") status = `Could not load the ${PLURAL[noun]}.`;
    else if (page && items.length === 0) status = `No matching ${PLURAL[noun]}.`;
    else if (page?.truncated) status = "Keep typing to narrow the list.";
  }
  const showList = open && items.length > 0;

  return (
    <div className="field combo">
      <label htmlFor={inputId}>{label}</label>
      <input
        ref={inputRef}
        id={inputId}
        type="text"
        role="combobox"
        autoComplete="off"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${errorId} ${statusId}` : statusId}
        value={text}
        disabled={disabled}
        onChange={edit}
        onKeyDown={keyDown}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          setOpen(false);
          setActive(-1);
        }}
        onInvalid={(event) => {
          event.preventDefault();
          setError(invalidMessage);
          event.currentTarget.focus();
        }}
      />
      {name && <input type="hidden" name={name} value={selected?.id ?? ""} />}
      <ul id={listId} role="listbox" aria-label={label} className="combo-list" hidden={!showList}>
        {items.map((option, index) => (
          <li
            key={option.id}
            id={`${listId}-${index}`}
            role="option"
            aria-selected={index === active}
            data-value={option.id}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => pick(option)}
          >
            {optionText(option)}
          </li>
        ))}
      </ul>
      {error && <p id={errorId} className="form-error">{error}</p>}
      <p id={statusId} aria-live="polite" className="muted combo-status">{status}</p>
      {serverMode && loadState === "failed" && (
        <button
          type="button"
          className="btn ghost small"
          onClick={() => {
            setOpen(true);
            setRetries((count) => count + 1);
            inputRef.current?.focus();
          }}
        >
          Retry
        </button>
      )}
    </div>
  );
}
```

Note: the option text is rendered as one string (`optionText`) so an option's accessible name equals the label the old `<select>` showed (`"Asha Rao — Hill School"`); E2E specs rely on that.

- [ ] **Step 5: Append the CSS** to `apps/web/app/globals.css`

```css
/* ENH-031 -- SearchableSelect: the list opens under its input, scrolls inside itself, and never widens the page. */
.combo { position: relative; }
.combo-list { position: absolute; left: 0; right: 0; z-index: 30; max-height: 18rem; overflow-y: auto; margin: 4px 0 0; padding: 4px; list-style: none; background: #fff; border: 1px solid var(--line); border-radius: 10px; box-shadow: 0 10px 24px rgba(15, 23, 42, .12); }
.combo-list[hidden] { display: none; }
.combo-list [role="option"] { padding: 8px 10px; border-radius: 8px; cursor: pointer; overflow-wrap: anywhere; }
.combo-list [role="option"][aria-selected="true"], .combo-list [role="option"]:hover { background: #eef4fc; }
.combo-status:empty { display: none; }
```

- [ ] **Step 6: Add the test helper** `apps/web/tests/helpers/pickOption.ts`

```ts
import { fireEvent, type screen } from "@testing-library/react";

// ENH-031: pick an option in a SearchableSelect by its value (the id the old <select> used), as a user would: open, click.
export function pickOption(scope: Pick<typeof screen, "getByRole">, label: string, value: string): void {
  const input = scope.getByRole("combobox", { name: label });
  fireEvent.focus(input);
  const list = document.getElementById(input.getAttribute("aria-controls") ?? "");
  const option = list?.querySelector<HTMLElement>(`[data-value="${value}"]`);
  if (!option) throw new Error(`No option with value "${value}" in "${label}"`);
  fireEvent.click(option);
}
```

- [ ] **Step 7: Run to see them pass**

Run the web command with `tests/lib/lookups.test.ts tests/components/SearchableSelect.test.tsx`. Expected: all PASS. Then `npx tsc --noEmit` and `npx eslint components/SearchableSelect.tsx lib/lookups.ts tests/helpers/pickOption.ts` in the web-test container → no errors.

- [ ] **Step 8: Commit**

```bash
git add apps/web/lib/lookups.ts apps/web/components/SearchableSelect.tsx apps/web/app/globals.css apps/web/tests/helpers/pickOption.ts apps/web/tests/lib/lookups.test.ts apps/web/tests/components/SearchableSelect.test.tsx
git commit -m "feat(enh-031): accessible SearchableSelect (load-once and server search) and the lookups client"
```

---

### Task 5: Free-text references in `WorkflowPanel` become lookups (F1–F10)

**Files:**
- Modify: `apps/web/components/WorkflowPanel.tsx` (imports; `Field` type; new `lookupField`; `ActionForm` field rendering; `DocumentUpload`; `appointmentSpec`; `placementSpecs`; `agentSpecs`; `overseasOperationsSpecs`; `adminSpecs`)
- Test: `apps/web/tests/components/WorkflowPanel.lookups.test.tsx`

**Interfaces:**
- Consumes: `SearchableSelect`, `Noun` (Task 4); `lookupSearch`, `LookupName` (Task 4).
- Produces: `Field.type` gains `"lookup"`; `Field.lookup?: { name: LookupName; noun: Noun; minChars?: number; params?: Record<string, string> }`; `lookupField(name, label, lookup, required = true): Field`.

- [ ] **Step 1: Write the failing tests**

`apps/web/tests/components/WorkflowPanel.lookups.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const user = (role: string, division = "overseas") => ({ id: "u1", email: "u@example.local", full_name: "U", role, division, profile: {} }) as unknown as User;

function stub(lookups: Record<string, unknown>) {
  const mock = vi.fn((url: string, init?: RequestInit) => {
    const lookup = Object.keys(lookups).find((key) => url.startsWith(`/api/v1/lookups/${key}?`));
    if (lookup) return Promise.resolve(json(lookups[lookup]));
    if (init?.method && init.method !== "GET") return Promise.resolve(json({ id: "new" }, 201));
    return Promise.resolve(json([]));
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WorkflowPanel reference fields (ENH-031)", () => {
  it("Create visa case picks an application from the lookup and posts its id", async () => {
    const mock = stub({ "overseas-applications": { items: [{ id: "a1", label: "Asha Rao", detail: "Uni X · offer" }], truncated: false } });
    render(<WorkflowPanel user={user("overseas_admin")} section="visa" />);
    const input = await screen.findByRole("combobox", { name: "Application reference" });
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "Asha" } });
    fireEvent.click(await screen.findByRole("option", { name: "Asha Rao — Uni X · offer" }));
    expect(mock.mock.calls.some(([url]) => String(url) === "/api/v1/lookups/overseas-applications?limit=20&q=Asha")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Create visa case" }));
    await waitFor(() => {
      const post = mock.mock.calls.find(([url, init]) => url === "/api/v1/workflows/overseas/visa" && init?.method === "POST");
      expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({ application_id: "a1" });
    });
  });

  it("a path-parameter reference (University Rep admission update) fills the URL from the pick", async () => {
    const mock = stub({ "overseas-applications": { items: [{ id: "a9", label: "Ravi Iyer", detail: "Uni Y · offer" }], truncated: false } });
    render(<WorkflowPanel user={user("university_rep")} section="student-communication" />);
    const input = await screen.findByRole("combobox", { name: "Application reference" });
    fireEvent.focus(input);
    fireEvent.click(await screen.findByRole("option", { name: "Ravi Iyer — Uni Y · offer" }));
    fireEvent.change(screen.getByLabelText("Update message"), { target: { value: "Offer is on the way" } });
    fireEvent.click(screen.getByRole("button", { name: "Post admission update" }));
    await waitFor(() => expect(mock.mock.calls.some(([url]) => url === "/api/v1/workflows/overseas/university-rep/applications/a9/updates")).toBe(true));
  });

  it("Schedule interview searches job applications", async () => {
    const mock = stub({ "it-job-applications": { items: [], truncated: false } });
    render(<WorkflowPanel user={user("placement_team", "it")} section="interviews" />);
    const input = await screen.findByRole("combobox", { name: "Job application reference" });
    fireEvent.focus(input);
    await waitFor(() => expect(mock.mock.calls.some(([url]) => String(url).startsWith("/api/v1/lookups/it-job-applications?"))).toBe(true));
  });

  it("the agent's Link student needs 3 characters and searches with purpose=link", async () => {
    const mock = stub({ "overseas-students": { items: [{ id: "s1", label: "Asha Rao", detail: "a***@example.local" }], truncated: false } });
    render(<WorkflowPanel user={user("agent")} section="students" />);
    const input = await screen.findByRole("combobox", { name: "Overseas student reference" });
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "as" } });
    expect(await screen.findByText("Type at least 3 characters.")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "ash" } });
    await screen.findByRole("option", { name: "Asha Rao — a***@example.local" });
    expect(mock.mock.calls.some(([url]) => String(url) === "/api/v1/lookups/overseas-students?limit=20&q=ash&purpose=link")).toBe(true);
  });

  it("document upload narrows the application lookup to the chosen student", async () => {
    const mock = stub({
      "overseas-students": { items: [{ id: "s1", label: "Asha Rao", detail: "asha@example.local" }], truncated: false },
      "overseas-applications": { items: [], truncated: false },
    });
    render(<WorkflowPanel user={user("agent")} section="documents" />);
    const student = await screen.findByRole("combobox", { name: "Student reference" });
    fireEvent.focus(student);
    fireEvent.click(await screen.findByRole("option", { name: "Asha Rao — asha@example.local" }));
    fireEvent.focus(screen.getByRole("combobox", { name: "Application reference (optional)" }));
    await waitFor(() => expect(mock.mock.calls.some(([url]) => String(url) === "/api/v1/lookups/overseas-applications?limit=20&student_id=s1")).toBe(true));
  });

  it("no student or application reference is a plain text box any more", async () => {
    stub({});
    for (const [role, section, division] of [["counselor", "appointments", "overseas"], ["overseas_admin", "applications", "overseas"], ["placement_team", "offers", "it"]] as const) {
      const { unmount } = render(<WorkflowPanel user={user(role, division)} section={section} />);
      await waitFor(() => expect(screen.getAllByRole("combobox").length).toBeGreaterThan(0));
      expect(document.querySelector('input[type="text"][name="student_id"], input[type="text"][name="application_id"], input:not([type])[name="student_id"], input:not([type])[name="application_id"]')).toBeNull();
      unmount();
    }
  });
});
```

- [ ] **Step 2: Run to see them fail**

Run the web command with `tests/components/WorkflowPanel.lookups.test.tsx`. Expected: FAIL — `Unable to find role="combobox"`.

- [ ] **Step 3: Implement in `WorkflowPanel.tsx`**

Imports (after the `announceUsersChanged` import):

```tsx
import { type LookupName, lookupSearch } from "@/lib/lookups";
import SearchableSelect, { type Noun } from "./SearchableSelect";
```

`Field` type — replace the `type?:` line and add `lookup`:

```tsx
  type?: "text" | "number" | "date" | "datetime-local" | "textarea" | "select" | "checkbox" | "password" | "lookup";
  // ENH-031: a searchable dropdown fed by a role-scoped lookup; the picked id is submitted under `name`.
  lookup?: { name: LookupName; noun: Noun; minChars?: number; params?: Record<string, string> };
```

After `const applicationStatuses = …;` add:

```tsx
// ENH-031 (DEC-SCOPE-039): student/application references are picked, never typed.
const lookupField = (name: string, label: string, lookup: NonNullable<Field["lookup"]>, required = true): Field => ({ name, label, type: "lookup", required, lookup });
```

In `ActionForm`, replace the `spec.fields.map(field => <div className={…} key={field.name}>…</div>)` expression with:

```tsx
    <div className="form-grid">{spec.fields.map(field => field.type === "lookup" && field.lookup ? <SearchableSelect key={field.name} id={`${spec.title}-${field.name}`} label={field.label} name={field.name} required={field.required} noun={field.lookup.noun} minChars={field.lookup.minChars} search={lookupSearch(field.lookup.name, field.lookup.params)}/> : <div className={`field${field.type === "textarea" ? " full" : ""}`} key={field.name}>
```

(keep the rest of that `<div>` exactly as it is, closing `</div>)}</div>` unchanged).

Spec edits (exact replacements):

| Where | Replace | With |
|---|---|---|
| `appointmentSpec` | `...(staff ? [{ name: "student_id", label: "Student reference", type: "text" as const, required: true }] : [])` | `...(staff ? [lookupField("student_id", "Student reference", { name: "overseas-students", noun: "student" })] : [])` |
| `placementSpecs` "Schedule interview" and "Create offer" (2×) | `{ name: "application_id", label: "Job application reference", type: "text", required: true }` | `lookupField("application_id", "Job application reference", { name: "it-job-applications", noun: "application" })` |
| `agentSpecs` "students" | `{ name: "student_id", label: "Overseas student reference", type: "text", required: true }` | `lookupField("student_id", "Overseas student reference", { name: "overseas-students", noun: "student", minChars: 3, params: { purpose: "link" } })` |
| `overseasOperationsSpecs` "Update application", "Create visa case", "Post admission update" (3×) | `{ name: "application_id", label: "Application reference", type: "text", required: true }` | `lookupField("application_id", "Application reference", { name: "overseas-applications", noun: "application" })` |
| `adminSpecs` "applications" | `{ name: "application_id", label: "Overseas application reference", type: "text", required: true }` | `lookupField("application_id", "Overseas application reference", { name: "overseas-applications", noun: "application" })` |

`DocumentUpload`: add state after `const [failed, setFailed] = useState(false);`:

```tsx
  // ENH-031: the application picker is narrowed to the chosen student (the API refuses a mismatch anyway).
  const [studentId, setStudentId] = useState("");
```

and in its returned JSX replace

```tsx
{!ownsDocument && <div className="field"><label>Student reference</label><input name="student_id" required/></div>}<div className="field"><label>Application reference (optional)</label><input name="application_id"/></div>
```

with

```tsx
{!ownsDocument && <SearchableSelect label="Student reference" name="student_id" required noun="student" search={lookupSearch("overseas-students")} onChange={option => setStudentId(option?.id ?? "")}/>}<SearchableSelect key={studentId} label="Application reference (optional)" name="application_id" noun="application" search={lookupSearch("overseas-applications", { student_id: studentId || undefined })}/>
```

- [ ] **Step 4: Run to see them pass**

Run the web command with `tests/components/WorkflowPanel.lookups.test.tsx tests/components/WorkflowPanel.create-user.test.tsx tests/components/WorkflowPanel.expired-links.test.tsx`. Expected: all PASS. Then `npx tsc --noEmit` → exit 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/WorkflowPanel.tsx apps/web/tests/components/WorkflowPanel.lookups.test.tsx
git commit -m "feat(enh-031): student/application references in the generic action forms are searchable lookups (F1-F10)"
```

---

### Task 6: The School→Overseas bridge picks a school, then a student (F11, D4)

**Files:**
- Modify: `apps/web/components/AdminSchoolApplicationsPanel.tsx`
- Test: `apps/web/tests/components/AdminSchoolApplicationsPanel.test.tsx` (rewrite `stubApi` and `startApplication`; add two tests)

**Interfaces:**
- Consumes: `SearchableSelect` (Task 4), `lookupSearch`, `PickOption` (Task 4); lookups `schools`, `school-students` (Task 3).
- Produces: inputs `#bridge-school` ("School") and `#bridge-student` ("Student") — used by the E2E update in Task 8.

- [ ] **Step 1: Update the tests first**

In `AdminSchoolApplicationsPanel.test.tsx`, replace `stubApi` and `startApplication` with:

```tsx
/** The panel's reads succeed; the application POST gets `onPost`. */
function stubApi(onPost: () => Promise<unknown>) {
  const mock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return onPost();
    if (url.startsWith("/api/v1/public/universities")) return json(200, [{ id: "u1", name: "Test University", city: "Testville" }]);
    if (url.startsWith("/api/v1/overseas-admin/school-applications")) return json(200, []);
    if (url.startsWith("/api/v1/lookups/schools?")) return json(200, { items: [{ id: "sch1", label: "Hill School", detail: "HILL0001" }], truncated: false });
    if (url.startsWith("/api/v1/lookups/school-students?")) return json(200, { items: [{ id: "s1", label: "Asha", detail: "Grade 5 · A3F9C21B" }], truncated: false });
    return json(404, {});
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

async function pickSchoolAndStudent() {
  fireEvent.focus(screen.getByRole("combobox", { name: "School" }));
  fireEvent.click(await screen.findByRole("option", { name: "Hill School — HILL0001" }));
  fireEvent.focus(await screen.findByRole("combobox", { name: "Student" }));
  fireEvent.click(await screen.findByRole("option", { name: "Asha — Grade 5 · A3F9C21B" }));
}

async function startApplication() {
  render(<AdminSchoolApplicationsPanel />);
  await pickSchoolAndStudent();
  await screen.findByRole("option", { name: "Test University (Testville)" });
  fireEvent.change(screen.getByLabelText("University"), { target: { value: "u1" } });
  fireEvent.change(screen.getByLabelText("Intake"), { target: { value: "Fall 2027" } });
  fireEvent.click(screen.getByRole("button", { name: "Start application" }));
}
```

Add inside the `describe`:

```tsx
  it("searches students only within the chosen school and posts that student's id", async () => {
    const mock = stubApi(() => json(201, { id: "app1" }));
    await startApplication();
    expect(mock.mock.calls.some(([url]) => String(url) === "/api/v1/lookups/school-students?limit=20&school_id=sch1")).toBe(true);
    await waitFor(() => expect(mock.mock.calls.some(([url, init]) => url === "/api/v1/overseas-admin/school-students/s1/applications" && init?.method === "POST")).toBe(true));
  });

  it("offers no student search until a school is picked", () => {
    stubApi(() => json(201, {}));
    render(<AdminSchoolApplicationsPanel />);
    expect(screen.queryByRole("combobox", { name: "Student" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Start application" })).toBeNull();
  });
```

and add `waitFor` to the `@testing-library/react` import.

- [ ] **Step 2: Run to see them fail**

Run the web command with `tests/components/AdminSchoolApplicationsPanel.test.tsx`. Expected: FAIL — no combobox named "School".

- [ ] **Step 3: Rewrite the panel's student lookup**

In `AdminSchoolApplicationsPanel.tsx`:
- imports: add `import SearchableSelect from "@/components/SearchableSelect";` and `import { lookupSearch, type PickOption } from "@/lib/lookups";`; remove the now-unused `ResolvedStudent` type.
- replace the header comment's last two lines with: `// ENH-031 (DEC-SCOPE-039 D4): pick the school first, then search only that school's students by name or Student ID -- no cross-school name browsing.`
- replace the `studentCode`/`resolved` state and `lookupStudent` with:

```tsx
  const [school, setSchool] = useState<PickOption | null>(null);
  const [student, setStudent] = useState<PickOption | null>(null);
  // Bumped after a successful start so both pickers remount empty.
  const [version, setVersion] = useState(0);
```

- in `submit`, replace `resolved` with `student`, the not-chosen message with `"Choose a school, then a student, first."`, the success message with ``Application started for ${student.label}.``, and the post-success resets with `setSchool(null); setStudent(null); setVersion((v) => v + 1);`.
- replace the whole "Student ID" `<div className="field">…</div>` block and the `{resolved && (<form …` condition with:

```tsx
      <SearchableSelect
        key={`school-${version}`}
        id="bridge-school"
        label="School"
        noun="school"
        search={lookupSearch("schools")}
        onChange={(option) => {
          setSchool(option);
          setStudent(null);
          setMessage(null);
        }}
      />
      {school && (
        <SearchableSelect
          key={`student-${school.id}-${version}`}
          id="bridge-student"
          label="Student"
          noun="student"
          search={lookupSearch("school-students", { school_id: school.id })}
          onChange={(option) => {
            setStudent(option);
            setMessage(null);
          }}
        />
      )}
      {student && (
```

(the `<form>` body and its closing stay as they are).

- [ ] **Step 4: Run to see them pass**

Run the web command with `tests/components/AdminSchoolApplicationsPanel.test.tsx`. Expected: all 5 PASS. `npx tsc --noEmit` → exit 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/AdminSchoolApplicationsPanel.tsx apps/web/tests/components/AdminSchoolApplicationsPanel.test.tsx
git commit -m "feat(enh-031): School->Overseas bridge picks a school, then searches that school's students (D4)"
```

---

### Task 7: Existing student dropdowns become searchable (§3.2)

**Files:**
- Modify: `apps/web/components/SchoolAcademicResultsPanel.tsx`, `SchoolPsychometricRecordsPanel.tsx`, `SchoolTestPrepLanguagePanel.tsx`, `CareerRecordForm.tsx`, `CareerPreferencesCard.tsx`, `CounselorChatPanel.tsx`, `AgentApplicationCreatePanel.tsx`, `EmployerInterviewsPanel.tsx`
- Modify tests: `CareerPreferencesCard.test.tsx`, `CareerRecordForm.test.tsx`, `SchoolCareerRecordsPanel.test.tsx`, `SchoolPsychometricRecordsPanel.test.tsx`, `SchoolTestPrepLanguagePanel.test.tsx`
- Test: `apps/web/tests/components/Enh031ExistingPickers.test.tsx`

**Interfaces:**
- Consumes: `SearchableSelect` (load-once mode), `pickOption` helper (Task 4).
- Produces: nothing new; every converted control keeps its `id` (so its listbox is `${id}-list`) and its submitted `name`/value.

- [ ] **Step 1: Write the new failing tests**

`apps/web/tests/components/Enh031ExistingPickers.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationCreatePanel from "@/components/AgentApplicationCreatePanel";
import SchoolPsychometricRecordsPanel from "@/components/SchoolPsychometricRecordsPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("existing student dropdowns are searchable (ENH-031 §3.2)", () => {
  it("the psychometric assign form filters its roster by typing", () => {
    const students = [
      { id: "s1", full_name: "Asha Rao", school_name: "Hill School" },
      { id: "s2", full_name: "Ravi Iyer", school_name: "Hill School" },
    ];
    render(<SchoolPsychometricRecordsPanel records={[]} students={students} />);
    const input = screen.getByRole("combobox", { name: "Student" });
    expect(input.id).toBe("psych-student");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "ravi" } });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Ravi Iyer — Hill School"]);
  });

  it("the agent's Create application picker empties after a successful create", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      if (url === "/api/v1/workflows/overseas/agent/students") return Promise.resolve(json([{ link_id: "l1", student_id: "s1", student: "Asha Rao", email: "asha@example.local", status: "active" }]));
      if (url === "/api/v1/public/universities") return Promise.resolve(json([{ id: "u1", slug: "u1", name: "Uni One", city: "X" }]));
      if (url.startsWith("/api/v1/public/universities/")) return Promise.resolve(json({ courses: [] }));
      if (init?.method === "POST") return Promise.resolve(json({ id: "app1" }, 201));
      return Promise.resolve(json({}));
    }));
    render(<AgentApplicationCreatePanel />);
    const input = await screen.findByRole("combobox", { name: "Linked student" });
    fireEvent.focus(input);
    fireEvent.click(screen.getByRole("option", { name: "Asha Rao — asha@example.local" }));
    fireEvent.change(screen.getByLabelText("University"), { target: { value: "u1" } });
    fireEvent.click(screen.getByRole("button", { name: /Create application/ }));
    await screen.findByText("Application created.");
    await waitFor(() => expect((screen.getByRole("combobox", { name: "Linked student" }) as HTMLInputElement).value).toBe(""));
  });
});
```

Update the existing tests (same meaning, new control) — add `import { pickOption } from "../helpers/pickOption";` to each file and replace:

| File:line | Replace | With |
|---|---|---|
| `CareerPreferencesCard.test.tsx` :20, :31, :41, :58 | `fireEvent.change(screen.getByLabelText("Student"), { target: { value: "s1" } });` | `pickOption(screen, "Student", "s1");` |
| `CareerRecordForm.test.tsx` :46 | same | `pickOption(screen, "Student", "s1");` |
| `SchoolCareerRecordsPanel.test.tsx` :20 | `fireEvent.change(card.getByLabelText("Student"), { target: { value: "s1" } });` | `pickOption(card, "Student", "s1");` |
| `SchoolPsychometricRecordsPanel.test.tsx` :23 | `fireEvent.change(screen.getByLabelText("Student"), { target: { value: "s1" } });` | `pickOption(screen, "Student", "s1");` |
| `SchoolTestPrepLanguagePanel.test.tsx` :29 | `fireEvent.change(within(section("Start test preparation")).getByLabelText("Student"), { target: { value: "s1" } });` | `pickOption(within(section("Start test preparation")), "Student", "s1");` |
| `SchoolTestPrepLanguagePanel.test.tsx` :63 | the same with `"Start language classes"` | `pickOption(within(section("Start language classes")), "Student", "s1");` |

- [ ] **Step 2: Run to see them fail**

Run the web command with `tests/components/Enh031ExistingPickers.test.tsx` and the five updated files. Expected: FAIL — no combobox named "Student" / "Linked student".

- [ ] **Step 3: Convert the controls** (add `import SearchableSelect from "@/components/SearchableSelect";` to each file)

`SchoolAcademicResultsPanel.tsx`, `SchoolPsychometricRecordsPanel.tsx`, `SchoolTestPrepLanguagePanel.tsx` (twice) — replace each whole block

```tsx
            <div className="field">
              <label htmlFor="result-student">Student</label>
              <select id="result-student" name="school_student_id" required defaultValue="">
                <option value="" disabled>Select student</option>
                {students.map((s) => (
                  <option key={s.id} value={s.id}>{s.full_name} — {s.school_name}</option>
                ))}
              </select>
            </div>
```

with (using that block's own id: `result-student`, `psych-student`, `testprep-student`, `language-student`):

```tsx
            <SearchableSelect id="result-student" label="Student" name="school_student_id" required noun="student" options={students.map((s) => ({ id: s.id, label: s.full_name, detail: s.school_name }))} />
```

`CareerRecordForm.tsx` — replace the `${prefix}-student` field block with:

```tsx
            <SearchableSelect id={`${prefix}-student`} label="Student" name="school_student_id" required noun="student" options={students.map((s) => ({ id: s.id, label: s.full_name, detail: s.school_name }))} />
```

`CareerPreferencesCard.tsx` — replace the `prefs-student` field block with:

```tsx
          <SearchableSelect
            id="prefs-student"
            label="Student"
            noun="student"
            options={students.map((s) => ({ id: s.id, label: s.full_name, detail: s.school_name }))}
            onChange={(option) => {
              setStudentId(option?.id ?? "");
              if (option) load(option.id);
            }}
          />
```

`CounselorChatPanel.tsx` — replace the `counselor-chat-student` field block with:

```tsx
      <SearchableSelect id="counselor-chat-student" label="Student" noun="student" options={uniqueStudents.map((row) => ({ id: row.student_id, label: row.student }))} onChange={(option) => loadConversation(option?.id ?? "")} />
```

`EmployerInterviewsPanel.tsx` — replace the `shortlist-candidate` field block with:

```tsx
        <SearchableSelect id="shortlist-candidate" label="Candidate" name="student_id" required noun="candidate" options={candidates.map((candidate) => ({ id: candidate.student_id, label: candidate.name }))} />
```

`AgentApplicationCreatePanel.tsx` — add `const [formVersion, setFormVersion] = useState(0);` after the `message` state; in `submit`'s success branch add `setFormVersion((v) => v + 1);` next to `setStudentId("");`; replace the `agent-app-student` field block with:

```tsx
        <SearchableSelect
          key={formVersion}
          id="agent-app-student"
          label="Linked student"
          required
          disabled={!students.length}
          noun="student"
          options={students.map((s) => ({ id: s.student_id, label: s.student, detail: s.email }))}
          onChange={(option) => setStudentId(option?.id ?? "")}
        />
```

(The old option text used ` -- ` between name and email; the combobox shows ` — ` like every other picker.)

- [ ] **Step 4: Run to see them pass, then the whole web suite**

Run the web command with `tests/components/Enh031ExistingPickers.test.tsx` and the five updated test files → PASS. Then run the full suite: `... run --rm --no-deps web-test npx vitest run`. Expected: everything passes except the 2 known time-zone tests (`tests/lib/formatDate.test.ts`, `tests/components/LocalTime.test.tsx`). If any other test fails because it drove one of these `<select>`s with `fireEvent.change(... { target: { value: X } })`, replace that line with `pickOption(<same scope>, "<same label>", X)` — the value is the same id — and re-run. Then `npx tsc --noEmit` → 0 and `npx eslint .` → 0 errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components apps/web/tests/components apps/web/tests/helpers
git commit -m "feat(enh-031): the existing student/candidate dropdowns become searchable (spec §3.2)"
```

---

### Task 8: End-to-end — shared helper, updated specs, one new ENH-031 spec

**Files:**
- Create: `apps/web/tests/e2e/helpers/pick.ts`
- Modify: `apps/web/tests/e2e/enh-002-academic-team-remarks-progress.spec.ts:52`, `sch-004-005-006-service-delivery.spec.ts:89,137`, `sch-009-test-prep-language.spec.ts:62,74`, `enh-025-student-master-fields.spec.ts:106`, `enh-026-counselling-record.spec.ts:62`, `i19-counselor-chat.spec.ts:32`, `emp-004-interview-scheduling.spec.ts:45`, `emp-005-interview-list.spec.ts:51`, `uni-001-university-rep-portal.spec.ts:51`, `sch-010-overseas-bridge.spec.ts:71-74`
- Create: `apps/web/tests/e2e/enh-031-searchable-pickers.spec.ts`

**Interfaces:**
- Consumes: the ids and labels from Tasks 4–7.
- Produces: `pickFromList(input: Locator, search: string, option?: string | RegExp)`, `pickByValue(input: Locator, value: string)`.

- [ ] **Step 1: Add the helper** `apps/web/tests/e2e/helpers/pick.ts`

```ts
import { expect, type Locator } from "@playwright/test";

// ENH-031: choose from a SearchableSelect as a user would -- type to search, then click the option.
export async function pickFromList(input: Locator, search: string, option: string | RegExp = search) {
  await input.click();
  await input.fill(search);
  const listId = await input.getAttribute("aria-controls");
  await input.page().locator(`[id="${listId}"]`).getByRole("option", { name: option }).first().click();
  await expect(input).toHaveAttribute("aria-expanded", "false");
}

// When a spec only knows the record id (e.g. from an API call), pick the option carrying that id.
export async function pickByValue(input: Locator, value: string) {
  await input.click();
  const listId = await input.getAttribute("aria-controls");
  await input.page().locator(`[id="${listId}"] [data-value="${value}"]`).click();
  await expect(input).toHaveAttribute("aria-expanded", "false");
}
```

- [ ] **Step 2: Update the existing specs** (add `import { pickByValue, pickFromList } from "./helpers/pick";` — only the names each file uses)

| Spec line | Replace | With |
|---|---|---|
| `enh-002…:52` | ``await page.selectOption("#result-student", { label: `${f.student} — ${schoolName}` });`` | ``await pickFromList(page.locator("#result-student"), f.student, `${f.student} — ${schoolName}`);`` |
| `sch-004-005-006…:89` | ``await page.selectOption("#result-student", { label: `E2E Service Student — ${schoolName}` });`` | ``await pickFromList(page.locator("#result-student"), "E2E Service Student", `E2E Service Student — ${schoolName}`);`` |
| `sch-004-005-006…:137` | the same with `#psych-student` | the same with `#psych-student` |
| `sch-009…:62` / `:74` | ``await page.selectOption("#testprep-student", { label: `E2E SCH-009 Student — ${schoolName}` });`` (and `#language-student`) | ``await pickFromList(page.locator("#testprep-student"), "E2E SCH-009 Student", `E2E SCH-009 Student — ${schoolName}`);`` (and `#language-student`) |
| `enh-025…:106` | `await page.selectOption("#prefs-student", { value: studentId });` | `await pickByValue(page.locator("#prefs-student"), studentId);` |
| `enh-026…:62` | ``await add.getByLabel("Student").selectOption({ label: `${ctx.studentName} — ${schoolName}` });`` | ``await pickFromList(add.getByRole("combobox", { name: "Student" }), ctx.studentName, `${ctx.studentName} — ${schoolName}`);`` |
| `i19…:32` | `await replyCard.getByLabel("Student").selectOption({ label: "Ananya Sharma" });` | `await pickFromList(replyCard.getByRole("combobox", { name: "Student" }), "Ananya Sharma");` |
| `emp-004…:45`, `emp-005…:51` | `await interviewsCard.getByLabel("Candidate").selectOption({ label: name });` | `await pickFromList(interviewsCard.getByRole("combobox", { name: "Candidate" }), name);` |
| `uni-001…:51` | ``await card.locator("input[name='application_id']").fill(applicationId);`` | ``await pickByValue(card.getByRole("combobox", { name: "Application reference" }), applicationId);`` |
| `sch-010…:71-74` | the `goto`, `fill("#bridge-student-code")`, `click("Look up")` and `expect(getByText(…))` lines | see below |

`sch-010-overseas-bridge.spec.ts` lines 71–74 become:

```ts
  await page.goto("/overseas/counselor/school-applications");
  await pickFromList(page.locator("#bridge-school"), schoolName);
  await pickFromList(page.locator("#bridge-student"), studentCode!, new RegExp(`^E2E SCH-010 Student — .*${studentCode}`));
```

Leave `enh-022…:87` and `sch-004-005-006…:122` (`#career-student`) untouched: that id was removed by ENH-026 before this work and those lines already fail on `main` (recorded in the RTM).

- [ ] **Step 3: Write the new spec** `apps/web/tests/e2e/enh-031-searchable-pickers.spec.ts`

```ts
import { expect, test } from "@playwright/test";

import { pickFromList } from "./helpers/pick";

// ENH-031 (DEC-SCOPE-039): an agent links a student through the 3-character search, creates an application with the
// load-once picker, and Overseas Admin finds that application by searching the student's name. Uses the seeded demo
// agent (active agency) and Overseas Admin.
async function signIn(page: import("@playwright/test").Page, email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("pick references instead of typing ids: agent link, agent application, admin update (ENH-031)", async ({ page }) => {
  test.setTimeout(60_000);
  const unique = Date.now();
  const name = `E2E ENH031 Student ${unique}`;

  await signIn(page, "overseasadmin@edusphere.local", "/overseas/admin/dashboard");
  const created = await page.request.post("/api/v1/admin/users", { data: { full_name: name, email: `enh031-${unique}@example.local`, division: "overseas", role: "overseas_student" } });
  expect(created.ok()).toBeTruthy();

  await signIn(page, "agent@edusphere.local", "/overseas/agent/dashboard");
  await page.goto("/overseas/agent/students");
  const link = page.getByRole("combobox", { name: "Overseas student reference" });
  await link.click();
  await link.fill("E2");
  await expect(page.getByText("Type at least 3 characters.")).toBeVisible();
  await pickFromList(link, name, new RegExp(`^${name} — e\\*\\*\\*@example\\.local$`));
  await page.getByRole("button", { name: "Link student" }).click();
  await expect(page.getByText("Student linked.")).toBeVisible();

  await page.goto("/overseas/agent/applications");
  await pickFromList(page.getByRole("combobox", { name: "Linked student" }), name, new RegExp(`^${name} — `));
  await page.locator("#agent-app-university").selectOption({ index: 1 });
  await page.getByRole("button", { name: /Create application/ }).click();
  await expect(page.getByText("Application created.")).toBeVisible();

  await signIn(page, "overseasadmin@edusphere.local", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/applications");
  // Overseas Admin's "applications" section is the operational "Update application" card (F5); F8 is Super Admin's.
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Update application" }) });
  await card.getByRole("button", { name: "Update application" }).click();
  await expect(card.getByText("Choose an application from the list.")).toBeVisible();
  await pickFromList(card.getByRole("combobox", { name: "Application reference" }), name, new RegExp(`^${name} — `));
  await card.getByLabel("Status").selectOption("eligibility_evaluation");
  await card.getByRole("button", { name: "Update application" }).click();
  await expect(card.getByText("Application updated and student notified.")).toBeVisible();
});

test("the open list never scrolls the page sideways at 320px (ENH-031 AC09)", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await signIn(page, "agent@edusphere.local", "/overseas/agent/dashboard");
  await page.goto("/overseas/agent/applications");
  const input = page.getByRole("combobox", { name: "Linked student" });
  await input.click();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
```

- [ ] **Step 4: Run the E2E specs**

Ask the user to rebuild the running stack (`docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn001 --profile ci up -d --build api web`) and wait for their go-ahead. Then rebuild `web-test` and run:
`docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn001 --profile ci run --rm -e CI=true -e E2E_BASE_URL=http://localhost:3000 -e PLAYWRIGHT_PROXY_TARGET=http://web:3000 web-test npx playwright test --workers=1 --reporter=line tests/e2e/enh-031-searchable-pickers.spec.ts tests/e2e/enh-002-academic-team-remarks-progress.spec.ts tests/e2e/sch-004-005-006-service-delivery.spec.ts tests/e2e/sch-009-test-prep-language.spec.ts tests/e2e/enh-025-student-master-fields.spec.ts tests/e2e/enh-026-counselling-record.spec.ts tests/e2e/i19-counselor-chat.spec.ts tests/e2e/emp-004-interview-scheduling.spec.ts tests/e2e/emp-005-interview-list.spec.ts tests/e2e/uni-001-university-rep-portal.spec.ts tests/e2e/sch-010-overseas-bridge.spec.ts tests/e2e/agn-001-multi-tenant.spec.ts tests/e2e/agt-001-registration-approval.spec.ts tests/e2e/agt-002-referrals.spec.ts`
Expected: all pass except the already-recorded `#career-student` lines (`sch-004-005-006…:122` test) and the `sch-004` "Search Alpha" reused-database failures. Record every failure with its cause.

- [ ] **Step 5: Commit**

```bash
git add apps/web/tests/e2e
git commit -m "test(enh-031): E2E picks references from the searchable dropdowns; new ENH-031 spec"
```

---

### Task 9: Traceability documents and the final verification

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append `DEC-SCOPE-039` after `DEC-SCOPE-038`)
- Modify: `docs/delivery/ENHANCEMENT_BACKLOG.md` (summary row after `AGN-001` at line 139; new `## ENH-031` section before `## 2. Dependency graph`)
- Modify: `docs/architecture/API_CONTRACT.md` (append an "ENH-031 lookups" section)
- Modify: `docs/ux/SCREEN_CATALOG.md` (append an "ENH-031 update" note)
- Modify: `docs/quality/RTM.md` (append an ENH-031 addendum after the AGN-001 addendum)

- [ ] **Step 1: Decision register** — append:

```markdown
### DEC-SCOPE-039 — Searchable reference pickers (`ENH-031`)

**ID note:** provisional; the later-merging branch renumbers (precedent: `DEC-SCOPE-024`…`036`).

**Question:** the owner asked (in-session, 2026-09-29): "all the student references and application references should be the drop down with valid values. drop down values should be able to search". Which fields, what may each role see, and how?

**Evidence:** read-only investigation, 2026-09-29: 11 forms take a typed student/application id (document upload, appointments, agent Link student, application updates, visa case, University Rep update, interviews, offers, School→Overseas bridge); 9 offer a plain `<select>`; no combobox component and no lookup endpoints exist.

**Resolution:** owner, in-session 2026-09-29 (`EXPLICIT_APPROVAL`), D1–D5 in `docs/superpowers/specs/2026-09-29-enh-031-searchable-reference-pickers-design.md` §2: D1 both groups of fields, other reference fields out of scope; D2 agent link = server search only (≥ 3 characters, ≤ 10 results, masked email, own agency's links left out); D3 own accessible combobox + role-scoped read-only lookups, no new dependency; D4 bridge = pick the school, then search only its students; D5 built on the AGN-001 branch.

**Consequences:** new `GET /api/v1/lookups/{overseas-students,overseas-applications,it-job-applications,schools,school-students}` (read-only, each with its write endpoint's scope); new `SearchableSelect` component; 20 form fields change control. No write endpoint, schema or migration changes.
```

- [ ] **Step 2: Backlog** — summary row:

```markdown
| ENH-031 | Searchable reference pickers — student/application references picked from role-scoped searchable dropdowns | Medium | Medium | No | AGN-001 (agency scope) |
```

and before `## 2. Dependency graph`:

```markdown
## ENH-031 — Searchable Reference Pickers (Student / Application References)

**Requirement:** the owner, in-session 2026-09-29 (`EXPLICIT_APPROVAL`): every student and application reference is a searchable dropdown of valid values. **Decision:** `DEC-SCOPE-039` (D1–D5). **Spec:** `docs/superpowers/specs/2026-09-29-enh-031-searchable-reference-pickers-design.md` (AC01–AC10). **Plan:** `docs/superpowers/plans/2026-09-29-enh-031-searchable-reference-pickers.md`.

**Status (2026-09-29):** implemented on `feature/agn-001-multi-tenant-agent-crm`; evidence in `docs/quality/RTM.md` (ENH-031 row).

---
```

- [ ] **Step 3: API contract** — append:

```markdown
## ENH-031 — Lookups (read-only, `DEC-SCOPE-039`)

`GET /api/v1/lookups/{name}` — query `q` (≤ 100 chars, literal case-insensitive substring), `limit` (1–50, default 20). Response `{"items": [{"id", "label", "detail"}], "truncated": bool}`, ordered by label. 403 `"This role cannot use this lookup"` for other roles; agent gate messages for pending/suspended/deactivated agents; 422 for bad parameters. One `app.lookups` log line per call (counts only), no audit row.

| name | Roles | Scope | `label` / `detail` |
|---|---|---|---|
| `overseas-students` | overseas_admin, super_admin, counselor, agent | admin all; counselor students of own applications; agent students linked to own agency | full name / email |
| `overseas-students?purpose=link` | agent | any overseas student not linked to own agency; `q` ≥ 3 else 422; ≤ 10 | full name / masked email |
| `overseas-applications` (`student_id=` optional) | overseas_student, counselor, university_rep, agent, overseas_admin, super_admin | `_assigned_application` rule | student / university · course · status |
| `it-job-applications` | placement_team, hr_team, it_admin, super_admin | all | candidate / job title · company · status |
| `schools` | overseas_admin, super_admin, counselor | all partner schools | name / school code |
| `school-students?school_id=` (required; 404 unknown) | overseas_admin, super_admin, counselor | that school only | full name / grade · student code |
```

- [ ] **Step 4: Screen catalog** — append:

```markdown
### ENH-031 update (2026-09-29, `DEC-SCOPE-039`)

Student, application and candidate references on these screens are searchable dropdowns (type to filter, arrow keys, Enter, Esc) that only accept a listed value: agent Students (Link student — search after 3 characters) and Documents; counselor/admin Appointments; University Rep/Admin Applications, Admission updates, Offer letters, Student communication; Admin Visa and Applications; Placement Interviews and Offers; the School→Overseas bridge (pick the school, then the student); the School academic results, psychometric, test-prep, language, career record and career preferences forms; counselor chat; agent Create application; employer Interviews.
```

- [ ] **Step 5: RTM** — append after the AGN-001 addendum a one-row table in the same format as the AGN-001 addendum:

```markdown
**Addendum, 2026-09-29 (`ENH-031`)** — one enhancement row.

| Feature ID | Contract documents | Old workbook cases | Status |
|---|---|---|---|
| `ENH-031` | Requirement (owner, 2026-09-29) → `PRODUCT_DECISION_REGISTER.md` `DEC-SCOPE-039` (D1–D5) → spec `docs/superpowers/specs/2026-09-29-enh-031-searchable-reference-pickers-design.md` (AC01–AC10) → plan `docs/superpowers/plans/2026-09-29-enh-031-searchable-reference-pickers.md`; `API_CONTRACT.md` ENH-031 lookups; `SCREEN_CATALOG.md` ENH-031 update | **Not audited** (an enhancement) | **IMPLEMENTED on `feature/agn-001-multi-tenant-agent-crm`, NOT complete — awaiting browser validation.** Evidence: <fill with the Step 6 results: API test counts, web counts, tsc/eslint/build, E2E results, and which existing specs changed because the control changed by decision D1> |
```

(Replace the angle-bracket text with the real numbers from Step 6 before committing — no placeholder may be committed.)

- [ ] **Step 6: Final verification (fresh runs)**

1. API: rebuild api-test; run `tests/test_enh_031_lookups_*.py` plus `tests/test_agn_001_*.py tests/test_agt_*.py tests/test_ovs_*.py tests/test_uni_001*.py` → record counts; then the full backend suite → expect only the 14 Razorpay/Zoho credential failures.
2. Web: rebuild web-test; `npx vitest run` (expect only the 2 known time-zone failures), `npx tsc --noEmit`, `npx eslint .`, `npm run build`.
3. E2E: Task 8 Step 4 list.
Fill the RTM row with these numbers.

- [ ] **Step 7: Commit**

```bash
git add docs/decisions/PRODUCT_DECISION_REGISTER.md docs/delivery/ENHANCEMENT_BACKLOG.md docs/architecture/API_CONTRACT.md docs/ux/SCREEN_CATALOG.md docs/quality/RTM.md
git commit -m "docs(enh-031): DEC-SCOPE-039, backlog entry, API contract, screen catalog and RTM evidence"
```
