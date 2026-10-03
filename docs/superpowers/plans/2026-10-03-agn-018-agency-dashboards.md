# AGN-018 Agency Master / Staff Dashboards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A typed agency dashboard endpoint with the 14 KPIs (Master: whole agency; Staff: assigned students only), rendered as a
KPI board on the existing agency dashboard page, plus the §4 role-specific sidebar labels.

**Architecture:** One new read-only router + aggregate service built on the existing scope helpers (`student_scope`,
`application_scope`, `document_scope`, `task_scope`); the portal payload keeps its labels/order and takes its Students /
Applications / Pending actions / Offers values from the same service. Frontend: an async server component streamed into the
existing `PortalSection` through an additive `lead` slot; nav edits in `lib/navigation.ts`.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Pydantic v2, PostgreSQL; Next.js App Router (server components), React, vitest,
Playwright.

**Spec:** `docs/superpowers/specs/2026-10-03-agn-018-agency-dashboards-design.md` (decision `DEC-SCOPE-062`).

## Global Constraints

- Agency only (G1): no change to other roles' dashboards, `OFFER_ONWARD_STATUSES`, or the sidebar "Offer received" filter meaning.
- No migration, no new dependency, no new auth flow, no write, no cache.
- Route: `GET /api/v1/workflows/overseas/agent/crm/dashboard`; gate = `agent_students._gate`; super admin 403.
- Response header `Cache-Control: private, no-store`; log event `agent_dashboard.read` with `org_id`, `actor_id`, `scope`,
  `duration_ms` only.
- Response: one shape; `staff`, `unassigned_students`, `commission` are `null` for Staff; no UUIDs in the body.
- Portal dashboard: labels, order and commission strings unchanged; Students now counts no-login students (deliberate fix).
- O5 offers rule only: `status IN OFFER_COUNTED_STATUSES OR offer_type IS NOT NULL` (withdrawn included).
- Breakdowns: top 10 by count desc, then label; `other` = the rest.
- UI copy: "Whole agency" / "Your assigned students"; error "Dashboard figures are unavailable right now." + "Try again"; Offers /
  Visa note "Includes later stages and withdrawn applications"; nav "My Students" (All, Add), "All applications",
  "Tasks & Follow-ups".
- Lite tests only (the owner runs the full suites separately): the AGN-018 test files plus the regression files each task names;
  web typecheck + lint + touched vitest files. Playwright is written here and run in the browser-validation phase.

## Test commands

API (project `agn018`, from the worktree root):

```
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn018 --profile ci run --rm \
  -v "$PWD/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <files>"
```

Web: `cd apps/web && npx vitest run <files>`, then `npx tsc --noEmit` and `npm run lint`.

## Review Focus

1. A student linked with a login **and** an agency record for the same person in one agency: an application must count once per
   member (COUNT DISTINCT) — Task 3 test `test_staff_row_counts_an_application_once`.
2. A deactivated staff member who still has active assigned students stays visible to the Master, marked inactive; one with none
   disappears — Task 3 test `test_deactivated_staff_row`.
3. A Staff caller adding `?scope=agency` gets own scope — Task 2 test `test_staff_cannot_select_the_agency_variant`.
4. Commission in two currencies is never summed across currencies on the board — Task 3 test
   `test_commission_is_per_currency` and Task 5 board test.
5. The board failing must not take the page down (title, table, nav still render) — Task 5 error test + Task 6 wiring test.

---

### Task 1: Offer clause, pending-actions statement, offer parity

**Files:**
- Create: `apps/api/app/services/agent_dashboard.py`
- Modify: `apps/api/app/services/agent_tasks.py:121-124`
- Test: `apps/api/tests/test_agn_018_offer_parity.py`

**Interfaces:**
- Produces: `offer_clause() -> ColumnElement[bool]`; `agency_applications(user) -> list[ColumnElement]`;
  `agent_tasks.pending_stmt(user) -> Select` (count of open tasks of active students in scope).

- [ ] **Step 1: Write the failing test**

```python
"""AGN-018 AC04 / G5 -- the SQL offer rule is the twin of `counts_as_offer` (O5): every stage, with and without a recorded offer."""

from datetime import date

import pytest
from sqlalchemy import select

from app.models import OverseasApplication
from app.services.agent_applications import OVERSEAS_APPLICATION_STAGES, WITHDRAWN, counts_as_offer
from app.services.agent_dashboard import offer_clause
from tests.agn008_helpers import agency_world, mk_application

STATUSES = [*OVERSEAS_APPLICATION_STAGES, WITHDRAWN, "offer_received", "accepted", "legacy free text"]


@pytest.mark.asyncio
async def test_sql_offer_clause_matches_counts_as_offer(db_session):
    w = await agency_world(db_session)
    rows = []
    for status in STATUSES:
        for recorded in (False, True):
            fields = {"offer_type": "conditional", "offer_date": date(2026, 9, 1), "offer_conditions": "IELTS 6.5"} if recorded else {}
            rows.append(await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"], status=status, **fields))
    ids = [r.id for r in rows]
    matched = set((await db_session.scalars(select(OverseasApplication.id).where(OverseasApplication.id.in_(ids), offer_clause()))).all())
    assert matched == {r.id for r in rows if counts_as_offer(r)}
    assert len(matched) == 6 + len(STATUSES)  # six offer statuses without a record, every status with one
```

- [ ] **Step 2: Run it — expect FAIL** (`ModuleNotFoundError: app.services.agent_dashboard`)

Run: API command with `tests/test_agn_018_offer_parity.py`

- [ ] **Step 3: Minimal implementation**

`apps/api/app/services/agent_dashboard.py`:

```python
"""AGN-018 -- the agency dashboard aggregates (DEC-SCOPE-062; spec §4-§5).

Every count is SQL over the existing scope helpers, so a Master counts the agency and a staff member only their assigned students
(G4) with no new scope logic. Read-only: nothing here writes, locks or commits."""

from sqlalchemy import ColumnElement, or_

from app.models import OverseasApplication
from app.services.agent_applications import OFFER_COUNTED_STATUSES
from app.services.agent_students import application_scope


def offer_clause() -> ColumnElement[bool]:
    """O5 (DEC-SCOPE-056) in SQL -- `counts_as_offer`'s twin (a parity test pins them): the stage reached `offer` (legacy values
    included) or an offer is recorded, so an application withdrawn after its offer still counts."""
    return or_(OverseasApplication.status.in_(OFFER_COUNTED_STATUSES), OverseasApplication.offer_type.is_not(None))


def agency_applications(user) -> list[ColumnElement]:
    """The applications the caller may see, School-bridged rows left out exactly as `with_owner` leaves them out (A12)."""
    return [*application_scope(user), OverseasApplication.school_student_id.is_(None)]
```

`apps/api/app/services/agent_tasks.py` — replace `pending_count` with:

```python
def pending_stmt(user: User) -> Select:
    """T5 "Pending actions": open tasks of active students in the caller's scope, as one COUNT statement (AGN-018 embeds it in
    the dashboard's single snapshot)."""
    stmt = select(func.count()).select_from(AgentTask).join(AgentStudent, AgentStudent.id == AgentTask.agent_student_id)
    return stmt.where(*task_scope(user), AgentTask.status == "open", AgentStudent.status == "active")


async def pending_count(db: AsyncSession, user: User) -> int:
    """T5 "Pending actions" -- one SQL COUNT, no rows loaded."""
    return await db.scalar(pending_stmt(user)) or 0
```

(`Select` is imported from `sqlalchemy` if the module does not already import it.)

- [ ] **Step 4: Run it — expect PASS**, plus `tests/test_agn_016_dashboard.py` (pending_count unchanged).
- [ ] **Step 5: Commit** — `feat(agn-018): SQL offer rule twin of counts_as_offer; pending-actions statement`

---

### Task 2: Headline counts, route, schema, gate, header, log

**Files:**
- Modify: `apps/api/app/services/agent_dashboard.py`
- Create: `apps/api/app/api/agent_dashboard.py`
- Modify: `apps/api/app/schemas.py` (after `CommissionReportOut`), `apps/api/app/main.py:9-46,70`
- Create: `apps/api/tests/agn018_helpers.py`
- Test: `apps/api/tests/test_agn_018_dashboard.py`

**Interfaces:**
- Consumes: Task 1 `offer_clause`, `agency_applications`, `pending_stmt`.
- Produces: `headline_counts(db, user) -> dict[str, int]` with keys `students, applications, offers, visa_applications,
  visa_approvals, enrollments, pending_documents, pending_actions`; `dashboard(db, user) -> dict` (Task 3 extends it);
  `AgentDashboardOut`; test helper `dashboard_world(db) -> dict` and `DASHBOARD_API`.

- [ ] **Step 1: Write the fixture helper** `apps/api/tests/agn018_helpers.py`

```python
"""AGN-018 fixture: one agency (Master + three staff) and a noise agency, with every case the KPI definitions distinguish
(spec §4, §8 AC01). The expected numbers are hand counts written next to the rows that produce them."""

import uuid
from datetime import date

from app.models import AgentCommission, AgentStudent, Country, University
from tests.agn001_helpers import mk_active_org, mk_user, uniq
from tests.agn004_helpers import mk_record, mk_staff
from tests.agn008_helpers import mk_application, mk_school_student
from tests.agn009_helpers import mk_doc
from tests.agn012_helpers import mk_case
from tests.agn016_helpers import mk_task

DASHBOARD_API = "/api/v1/workflows/overseas/agent/crm/dashboard"
PORTAL_DASHBOARD = "/api/v1/portal/overseas/agent/dashboard"
OFFERED = {"offer_type": "unconditional", "offer_date": date(2026, 9, 1)}


async def mk_place(db, *, university: str, country: str) -> University:
    suffix = uuid.uuid4().hex[:8]
    c = Country(slug=f"agn018-c-{suffix}", name=country, overview="", tuition="", living_expenses="", visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[])
    db.add(c)
    await db.flush()
    u = University(country_id=c.id, slug=f"agn018-u-{suffix}", name=university, city="Testville", overview="", eligibility="", requirements=[], deadlines=[], scholarships=[])
    db.add(u)
    await db.commit()
    return u


async def mk_commission(db, *, agent, application, status: str, amount: float, currency: str = "INR") -> AgentCommission:
    row = AgentCommission(agent_id=agent.id, application_id=application.id, amount=amount, currency=currency, status=status, created_by="system_trigger",
                          claim_reference=None if status in {"estimated", "eligible"} else f"CLM-{uniq()}")
    db.add(row)
    await db.commit()
    return row


async def dashboard_world(db) -> dict:
    ctx = await mk_active_org(db, name=f"Dash {uniq()}")
    other = await mk_active_org(db, name=f"Noise {uniq()}")
    master = ctx["master"]
    s1 = await mk_staff(db, ctx["org"], full_name="Staff One")
    s2 = await mk_staff(db, ctx["org"], full_name="Staff Two")
    s3 = await mk_staff(db, ctx["org"], full_name="Staff Three")
    u1 = await mk_place(db, university="Alpha University", country="Aland")
    u2 = await mk_place(db, university="Beta University", country="Betaland")

    r1 = await mk_record(db, agent=master, full_name=f"R1 {uniq()}", assigned_member=s1["member"])            # s1, no login
    login = await mk_user(db, role="overseas_student", full_name=f"R2 {uniq()}")
    r2 = AgentStudent(agent_id=master.id, student_id=login.id, status="active", assigned_member_id=s1["member"].id)  # s1, login
    db.add(r2)
    await db.commit()
    r3 = await mk_record(db, agent=master, full_name=f"R3 {uniq()}", assigned_member=s2["member"])            # s2
    r4 = await mk_record(db, agent=master, full_name=f"R4 {uniq()}", assigned_member=s1["member"], status="archived")  # s1, archived
    r5 = await mk_record(db, agent=master, full_name=f"R5 {uniq()}")                                          # unassigned

    def app(record, university, status, **fields):
        return mk_application(db, agent=master, university=university, record=record, status=status, **fields)

    a1 = await app(r1, u1, "enquiry")
    a2 = await app(r1, u1, "offer")
    a3 = await app(r2, u2, "visa_documentation")
    a4 = await app(r2, u2, "enrolled")
    a5 = await app(r3, u1, "withdrawn", **OFFERED)            # withdrawn after its offer: an offer, not an application
    a6 = await app(r3, u1, "university_selection", **OFFERED)  # offer recorded before the stage moved
    a7 = await app(r4, u1, "enquiry")                          # archived student's application stays
    a8 = await app(r5, u2, "offer_received")                   # legacy offer value, unassigned student
    await app(r1, u1, "withdrawn")                             # a10: withdrawn, no offer -- counted nowhere
    await mk_application(db, agent=master, university=u1, school_student=await mk_school_student(db), status="offer")  # bridged: nowhere

    await mk_case(db, a3, status="decision", decision="approved")
    await mk_case(db, a3, status="checklist")                 # a second case on a3: still one visa application
    await mk_case(db, a5, status="decision", decision="refused")

    await mk_doc(db, record=r1)                               # pending, unattached (s1)
    await mk_doc(db, record=r1, status="verified")
    await mk_doc(db, record=r2, application=a3)               # pending, attached (s1)
    await mk_doc(db, record=r3)                               # pending (s2)
    await mk_doc(db, record=r5)                               # pending (unassigned)

    await mk_task(db, record=r1, author=master)               # open (s1)
    await mk_task(db, record=r1, author=master, status="done")
    await mk_task(db, record=r3, author=master)               # open (s2)
    await mk_task(db, record=r4, author=master)               # open but archived student: not pending
    await mk_task(db, record=r5, author=master, status="cancelled")

    await mk_commission(db, agent=master, application=a1, status="estimated", amount=200, currency="USD")
    await mk_commission(db, agent=master, application=a2, status="eligible", amount=1000)
    await mk_commission(db, agent=master, application=a3, status="claimed", amount=500)
    await mk_commission(db, agent=master, application=a4, status="paid", amount=12000)
    await mk_commission(db, agent=master, application=a8, status="paid", amount=500, currency="USD")

    # Noise agency: never counted.
    nr = await mk_record(db, agent=other["master"], full_name=f"Noise {uniq()}")
    na = await mk_application(db, agent=other["master"], university=u1, record=nr, status="enrolled")
    await mk_case(db, na, status="decision", decision="approved")
    await mk_doc(db, record=nr)
    await mk_task(db, record=nr, author=other["master"])
    await mk_commission(db, agent=other["master"], application=na, status="paid", amount=999)

    return ctx | {"other": other, "s1": s1, "s2": s2, "s3": s3, "u1": u1, "u2": u2, "apps": {"a1": a1, "a3": a3, "a4": a4}}


MASTER = {"students": 4, "applications": 7, "offers": 6, "visa_applications": 2, "visa_approvals": 1, "enrollments": 1, "pending_documents": 4, "pending_actions": 2}
S1 = {"students": 2, "applications": 5, "offers": 3, "visa_applications": 1, "visa_approvals": 1, "enrollments": 1, "pending_documents": 2, "pending_actions": 1}
S2 = {"students": 1, "applications": 1, "offers": 2, "visa_applications": 1, "visa_approvals": 0, "enrollments": 0, "pending_documents": 1, "pending_actions": 1}
S3 = dict.fromkeys(MASTER, 0)
```

- [ ] **Step 2: Write the failing tests** `apps/api/tests/test_agn_018_dashboard.py` (headline part)

```python
"""AGN-018 (DEC-SCOPE-062) -- the agency dashboard endpoint: hand-counted KPIs, staff scope, gate, header (spec §8)."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn017_helpers import deactivate, set_org_status
from tests.agn018_helpers import DASHBOARD_API, MASTER, S1, S2, S3, dashboard_world

KEYS = list(MASTER)


@pytest_asyncio.fixture
async def world(db_session):
    return await dashboard_world(db_session)


async def _get(email, url=DASHBOARD_API, **params):
    async with client_for(email) as c:
        response = await c.get(url, params=params)
    assert response.status_code == 200, response.text
    return response


def _counts(body):
    return {k: body[k] for k in KEYS}


@pytest.mark.asyncio
async def test_master_counts_equal_hand_counts(world):
    body = (await _get(world["master"].email)).json()
    assert body["scope"] == "agency" and _counts(body) == MASTER


@pytest.mark.asyncio
@pytest.mark.parametrize("who,expected", [("s1", S1), ("s2", S2), ("s3", S3)])
async def test_staff_counts_only_their_students(world, who, expected):
    body = (await _get(world[who]["user"].email)).json()
    assert body["scope"] == "own" and _counts(body) == expected


@pytest.mark.asyncio
async def test_staff_response_has_no_master_fields(world):
    response = await _get(world["s1"]["user"].email)
    body = response.json()
    assert body["staff"] is None and body["unassigned_students"] is None and body["commission"] is None
    assert "commission" not in response.text.replace('"commission":null', "")


@pytest.mark.asyncio
async def test_staff_cannot_select_the_agency_variant(world):
    body = (await _get(world["s1"]["user"].email, scope="agency", role="master")).json()
    assert body["scope"] == "own" and _counts(body) == S1


@pytest.mark.asyncio
async def test_no_store_and_no_uuids(world):
    response = await _get(world["master"].email)
    assert response.headers["cache-control"] == "private, no-store"
    for value in (world["master"].id, world["s1"]["member"].id, world["apps"]["a1"].id):
        assert str(value) not in response.text


@pytest.mark.asyncio
async def test_empty_agency_is_zeros(db_session):
    ctx = await mk_active_org(db_session)
    body = (await _get(ctx["master"].email)).json()
    assert _counts(body) == dict.fromkeys(KEYS, 0)
    assert body["by_country"] == {"items": [], "other": 0} and body["staff"] == [] and body["unassigned_students"] == 0


@pytest.mark.asyncio
async def test_refusals(db_session, client):
    assert (await client.get(DASHBOARD_API)).status_code == 401
    for role, division in (("super_admin", "overseas"), ("counselor", "overseas")):
        user = await mk_user(db_session, role=role, division=division)
        async with client_for(user.email) as c:
            assert (await c.get(DASHBOARD_API)).status_code == 403
    ctx = await mk_active_org(db_session)
    async with client_for(ctx["master"].email) as c:
        await set_org_status(db_session, ctx["org"], "suspended")
        assert (await c.get(DASHBOARD_API)).status_code == 403


@pytest.mark.asyncio
async def test_deactivated_member_is_refused(world, db_session):
    async with client_for(world["s1"]["user"].email) as c:
        await deactivate(db_session, world["s1"]["member"])
        assert (await c.get(DASHBOARD_API)).status_code in (401, 403)


@pytest.mark.asyncio
async def test_linked_kpis_equal_their_list_totals(world):
    crm = "/api/v1/workflows/overseas/agent/crm"
    for email in (world["master"].email, world["s1"]["user"].email):
        body = (await _get(email)).json()
        total = lambda url, **p: _get(email, f"{crm}/{url}", limit=1, **p)  # noqa: E731
        assert (await total("students")).json()["total"] == body["students"]
        assert (await total("applications")).json()["total"] == body["applications"]
        assert (await total("applications", status="enrolled")).json()["total"] == body["enrollments"]
        assert (await total("documents", view="pending")).json()["total"] == body["pending_documents"]
        assert (await total("tasks", view="open")).json()["total"] == body["pending_actions"]
```

(If `super_admin` login requires `division="overseas"`, `client_for` already passes it; if super admin logs in elsewhere, use
`client_for(user.email, division=...)` as `test_agn_001_tenancy.py:164` does.)

- [ ] **Step 3: Run — expect FAIL** (404 on the route)
- [ ] **Step 4: Implement**

Schemas (`apps/api/app/schemas.py`, after `CommissionReportOut`):

```python
class AgentBreakdownItem(BaseModel):
    label: str
    count: int


class AgentBreakdownOut(BaseModel):
    items: list[AgentBreakdownItem]
    other: int


class AgentStaffRowOut(BaseModel):
    code: str
    name: str
    active: bool
    students: int
    applications: int
    offers: int
    enrollments: int


class AgentCommissionSummaryOut(BaseModel):
    claimable: list[CommissionReportTotal]
    claims: int
    revenue: list[CommissionReportTotal]


class AgentDashboardOut(BaseModel):
    """AGN-018 (DEC-SCOPE-062): one shape for Masters and staff; the Master-only fields are null for staff."""

    scope: Literal["agency", "own"]
    member_code: str | None
    students: int
    applications: int
    offers: int
    visa_applications: int
    visa_approvals: int
    enrollments: int
    pending_documents: int
    pending_actions: int
    by_country: AgentBreakdownOut
    by_university: AgentBreakdownOut
    staff: list[AgentStaffRowOut] | None
    unassigned_students: int | None
    commission: AgentCommissionSummaryOut | None
    reports_available: bool
    as_of: datetime
```

Service additions (`agent_dashboard.py`):

```python
from datetime import UTC, datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import agent_may, is_agent_staff
from app.models import AgentStudent, StudentDocument, User, VisaCase
from app.services.agent_applications import WITHDRAWN
from app.services.agent_documents import document_scope
from app.services.agent_students import student_scope
from app.services.agent_tasks import pending_stmt


def _count(model, *where):
    return select(func.count()).select_from(model).where(*where).scalar_subquery()


def _visa(user: User, *extra):
    """Distinct applications with a visa case -- a second case on one application is not a second visa application."""
    stmt = select(func.count(distinct(VisaCase.application_id))).join(OverseasApplication, OverseasApplication.id == VisaCase.application_id)
    return stmt.where(*agency_applications(user), *extra).scalar_subquery()


async def headline_counts(db: AsyncSession, user: User) -> dict[str, int]:
    """The eight headline KPIs (spec §4) as scalar subqueries of ONE statement, so they come from one snapshot."""
    apps = agency_applications(user)
    columns = {
        "students": _count(AgentStudent, *student_scope(user), AgentStudent.status == "active"),
        "applications": _count(OverseasApplication, *apps, OverseasApplication.status != WITHDRAWN),
        "offers": _count(OverseasApplication, *apps, offer_clause()),
        "visa_applications": _visa(user),
        "visa_approvals": _visa(user, VisaCase.decision == "approved"),
        "enrollments": _count(OverseasApplication, *apps, OverseasApplication.status == "enrolled"),
        "pending_documents": _count(StudentDocument, *document_scope(user), StudentDocument.verification_status == "pending"),
        "pending_actions": pending_stmt(user).scalar_subquery(),
    }
    row = (await db.execute(select(*(column.label(key) for key, column in columns.items())))).one()
    return {key: int(value or 0) for key, value in row._mapping.items()}


async def dashboard(db: AsyncSession, user: User) -> dict:
    staff = is_agent_staff(user)
    return {
        "scope": "own" if staff else "agency",
        "member_code": user.agent_membership.code if user.agent_membership else None,
        **await headline_counts(db, user),
        "by_country": {"items": [], "other": 0},
        "by_university": {"items": [], "other": 0},
        "staff": None if staff else [],
        "unassigned_students": None if staff else 0,
        "commission": None,
        "reports_available": agent_may(user, "can_view_reports"),
        "as_of": datetime.now(UTC),
    }
```

Router `apps/api/app/api/agent_dashboard.py`:

```python
"""AGN-018 -- the agency dashboard: one read-only aggregate (DEC-SCOPE-062; spec §5).

AGN-004's gate (agency members of an active agency; super admin refused), no input, no write, no audit row (reads are not
audited, DEC-SCOPE-051 R7). The body is per-user, so it is never cached. The log line carries ids and timing only."""

import logging
import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_students import _gate
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import AgentDashboardOut
from app.services.agent_dashboard import dashboard

logger = logging.getLogger("app.agent_dashboard")

router = APIRouter(prefix="/workflows/overseas/agent/crm", tags=["agent-dashboard"])


@router.get("/dashboard", response_model=AgentDashboardOut)
async def get_dashboard(response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    started = time.perf_counter()
    payload = await dashboard(db, user)
    response.headers["Cache-Control"] = "private, no-store"
    logger.info(
        "agent_dashboard.read",
        extra={"extra_fields": {"org_id": str(membership.org_id), "actor_id": str(user.id), "scope": payload["scope"], "duration_ms": round((time.perf_counter() - started) * 1000)}},
    )
    return payload
```

`main.py`: import `agent_dashboard` with the other `agent_*` routers and add `agent_dashboard.router` after `agent_tasks.router` in
the registration tuple.

- [ ] **Step 5: Run — expect PASS** (`test_agn_018_dashboard.py`, `test_agn_018_offer_parity.py`). `test_empty_agency_is_zeros` and
  breakdown/staff assertions that depend on Task 3 may still fail on `by_country`/`staff` contents only if data exists — the
  empty agency passes with the placeholders.
- [ ] **Step 6: Commit** — `feat(agn-018): agency dashboard endpoint with hand-counted headline KPIs`

---

### Task 3: Breakdowns, staff table, commission summary

**Files:**
- Modify: `apps/api/app/services/agent_dashboard.py`
- Test: `apps/api/tests/test_agn_018_dashboard.py` (append)

**Interfaces:**
- Consumes: Task 2 `dashboard`, `agency_applications`, `offer_clause`.
- Produces: `breakdown(db, user, label, key) -> dict`, `staff_rows(db, user) -> tuple[list[dict], int]`,
  `commission_summary(db, user) -> dict`; `dashboard()` fills `by_country`, `by_university`, `staff`, `unassigned_students`,
  `commission`.

- [ ] **Step 1: Append failing tests**

```python
@pytest.mark.asyncio
async def test_breakdowns_by_country_and_university(world):
    body = (await _get(world["master"].email)).json()
    assert body["by_country"] == {"items": [{"label": "Aland", "count": 4}, {"label": "Betaland", "count": 3}], "other": 0}
    assert body["by_university"] == {"items": [{"label": "Alpha University", "count": 4}, {"label": "Beta University", "count": 3}], "other": 0}
    s2 = (await _get(world["s2"]["user"].email)).json()
    assert s2["by_country"] == {"items": [{"label": "Aland", "count": 1}], "other": 0}


@pytest.mark.asyncio
async def test_breakdown_keeps_ten_and_sums_the_rest(db_session):
    from tests.agn004_helpers import mk_record
    from tests.agn008_helpers import mk_application
    from tests.agn018_helpers import mk_place

    ctx = await mk_active_org(db_session)
    record = await mk_record(db_session, agent=ctx["master"], full_name="Many")
    for i in range(12):
        place = await mk_place(db_session, university=f"Uni {i:02d}", country=f"Country {i:02d}")
        for _ in range(2 if i < 3 else 1):
            await mk_application(db_session, agent=ctx["master"], university=place, record=record)
    body = (await _get(ctx["master"].email)).json()
    items = body["by_university"]["items"]
    assert len(items) == 10 and [i["label"] for i in items[:3]] == ["Uni 00", "Uni 01", "Uni 02"]
    assert body["by_university"]["other"] == 2 and sum(i["count"] for i in items) + 2 == body["applications"] == 15


@pytest.mark.asyncio
async def test_staff_rows_equal_each_members_own_dashboard(world):
    body = (await _get(world["master"].email)).json()
    rows = {r["name"]: r for r in body["staff"]}
    assert list(rows) == ["Staff One", "Staff Two", "Staff Three"] and body["unassigned_students"] == 1
    for key in ("s1", "s2", "s3"):
        own = (await _get(world[key]["user"].email)).json()
        row = rows[world[key]["user"].full_name]
        assert row["code"] == world[key]["member"].code and row["active"] is True
        assert {k: row[k] for k in ("students", "applications", "offers", "enrollments")} == {k: own[k] for k in ("students", "applications", "offers", "enrollments")}


@pytest.mark.asyncio
async def test_staff_row_counts_an_application_once(db_session):
    """Review Focus 1: an application reachable through the agency record AND the linked login counts once."""
    from tests.agn008_helpers import agency_world, mk_application

    w = await agency_world(db_session)
    await mk_application(db_session, agent=w["master"], university=w["university"], record=w["linked_record"], status="offer")
    body = (await _get(w["master"].email)).json()
    row = next(r for r in body["staff"] if r["code"] == w["staff"]["member"].code)
    assert row["applications"] == 1 and row["offers"] == 1


@pytest.mark.asyncio
async def test_deactivated_staff_row(world, db_session):
    """Review Focus 2: shown (inactive) while they still hold active students; gone once they hold none."""
    from tests.agn017_helpers import deactivate

    await deactivate(db_session, world["s1"]["member"])
    await deactivate(db_session, world["s3"]["member"])
    rows = {r["name"]: r for r in (await _get(world["master"].email)).json()["staff"]}
    assert rows["Staff One"]["active"] is False and "Staff Three" not in rows


@pytest.mark.asyncio
async def test_commission_is_per_currency(world):
    commission = (await _get(world["master"].email)).json()["commission"]
    assert commission == {
        "claimable": [{"currency": "INR", "count": 1, "amount": 1000.0}, {"currency": "USD", "count": 1, "amount": 200.0}],
        "claims": 1,
        "revenue": [{"currency": "INR", "count": 1, "amount": 12000.0}, {"currency": "USD", "count": 1, "amount": 500.0}],
    }
```

- [ ] **Step 2: Run — expect FAIL** (empty breakdowns / staff / null commission)
- [ ] **Step 3: Implement**

```python
from sqlalchemy import and_, case

from app.models import AgentCommission, AgentOrgMember, Country, University
from app.services.agent_orgs import org_member_ids

BREAKDOWN_SIZE = 10  # D2: top ten, the rest summed into `other`
CLAIMABLE = ("eligible", "estimated")  # the portal's "Claimable commission" statuses


async def breakdown(db: AsyncSession, user: User, label, key) -> dict:
    """Open applications grouped by `key` (shown as `label`). The window total comes from the same statement, so `other` can
    never disagree with the items."""
    count = func.count()
    stmt = (
        select(label, count, func.sum(count).over())
        .select_from(OverseasApplication)
        .join(University, University.id == OverseasApplication.university_id)
        .join(Country, Country.id == University.country_id)
        .where(*agency_applications(user), OverseasApplication.status != WITHDRAWN)
        .group_by(key, label)
        .order_by(count.desc(), label)
        .limit(BREAKDOWN_SIZE)
    )
    rows = (await db.execute(stmt)).all()
    items = [{"label": name, "count": n} for name, n, _ in rows]
    total = int(rows[0][2]) if rows else 0
    return {"items": items, "other": total - sum(i["count"] for i in items)}


async def staff_rows(db: AsyncSession, user: User) -> tuple[list[dict], int]:
    """Master only (G2): per staff member, exactly what that member's own dashboard shows -- students by assignment (active),
    applications by `application_scope`'s two paths (the agency record, or the linked login), each application once. Plus the
    agency's unassigned active students."""
    agency = org_member_ids(user)
    students = dict(
        (await db.execute(select(AgentStudent.assigned_member_id, func.count()).where(AgentStudent.agent_id.in_(agency), AgentStudent.status == "active").group_by(AgentStudent.assigned_member_id))).all()
    )
    app_id = OverseasApplication.id

    def distinct_apps(condition):
        return func.count(distinct(case((condition, app_id))))

    link = AgentStudent
    per_member = (
        select(link.assigned_member_id, distinct_apps(OverseasApplication.status != WITHDRAWN), distinct_apps(offer_clause()), distinct_apps(OverseasApplication.status == "enrolled"))
        .select_from(OverseasApplication)
        .join(link, or_(OverseasApplication.agent_student_id == link.id, and_(link.student_id.is_not(None), OverseasApplication.student_id == link.student_id)))
        .where(*agency_applications(user), link.agent_id.in_(agency), link.assigned_member_id.is_not(None))
        .group_by(link.assigned_member_id)
    )
    apps = {member_id: counts for member_id, *counts in (await db.execute(per_member)).all()}
    members = (
        await db.execute(
            select(AgentOrgMember, User.full_name).join(User, User.id == AgentOrgMember.user_id)
            .where(AgentOrgMember.org_id == user.agent_membership.org_id, AgentOrgMember.role == "staff").order_by(AgentOrgMember.seq)
        )
    ).all()
    rows = []
    for member, name in members:
        active = member.status == "active"
        if not active and not students.get(member.id):
            continue  # D3: a deactivated member drops out once they hold no active students
        applications, offers, enrollments = apps.get(member.id, (0, 0, 0))
        rows.append({"code": member.code, "name": name, "active": active, "students": students.get(member.id, 0), "applications": applications, "offers": offers, "enrollments": enrollments})
    return rows, students.get(None, 0)


async def commission_summary(db: AsyncSession, user: User) -> dict:
    """Master only (DEC-SCOPE-040 S1): the portal's three commission figures, per currency and never summed across currencies."""
    stmt = (
        select(AgentCommission.status, AgentCommission.currency, func.count(), func.sum(AgentCommission.amount))
        .where(AgentCommission.agent_id.in_(org_member_ids(user)))
        .group_by(AgentCommission.status, AgentCommission.currency)
    )
    claimable: dict[str, list] = {}
    revenue: dict[str, list] = {}
    claims = 0
    for status, currency, count, amount in (await db.execute(stmt)).all():
        claims += count if status == "claimed" else 0
        bucket = claimable if status in CLAIMABLE else revenue if status == "paid" else None
        if bucket is not None:
            totals = bucket.setdefault(currency, [0, 0.0])
            totals[0] += count
            totals[1] += float(amount or 0)

    def rows(bucket):
        return [{"currency": currency, "count": count, "amount": amount} for currency, (count, amount) in sorted(bucket.items())]

    return {"claimable": rows(claimable), "claims": claims, "revenue": rows(revenue)}
```

`dashboard()` becomes:

```python
async def dashboard(db: AsyncSession, user: User) -> dict:
    """The AGN-018 payload (spec §5.3). Staff get the Master-only fields as null; they are never queried for staff."""
    staff = is_agent_staff(user)
    result = {
        "scope": "own" if staff else "agency",
        "member_code": user.agent_membership.code if user.agent_membership else None,
        **await headline_counts(db, user),
        "by_country": await breakdown(db, user, Country.name, Country.id),
        "by_university": await breakdown(db, user, University.name, University.id),
        "staff": None,
        "unassigned_students": None,
        "commission": None,
        "reports_available": agent_may(user, "can_view_reports"),
        "as_of": datetime.now(UTC),
    }
    if not staff:
        result["staff"], result["unassigned_students"] = await staff_rows(db, user)
        result["commission"] = await commission_summary(db, user)
    return result
```

- [ ] **Step 4: Run — expect PASS** (both AGN-018 test files)
- [ ] **Step 5: Refactor** — keep `agent_dashboard.py` imports grouped at the top; rerun.
- [ ] **Step 6: Commit** — `feat(agn-018): breakdowns, Master staff table and per-currency commission`

---

### Task 4: Portal dashboard compatibility (AC08)

**Files:**
- Modify: `apps/api/app/services/portal.py` (`_agent` dashboard branch, ~L716-735; drop the now-unused `pending_count` import if
  nothing else uses it)
- Test: `apps/api/tests/test_agn_018_portal_compat.py`; possibly `apps/api/tests/test_agn_004_staff_scope.py:93`

- [ ] **Step 1: Write the failing test**

```python
"""AGN-018 AC08 -- the portal dashboard keeps its labels, order and commission strings, and its counts now equal the AGN-018
endpoint (Students includes students with no login: the deliberate DEC-SCOPE-062 fix)."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for
from tests.agn018_helpers import DASHBOARD_API, PORTAL_DASHBOARD, dashboard_world


@pytest_asyncio.fixture
async def world(db_session):
    return await dashboard_world(db_session)


async def _both(email):
    async with client_for(email) as c:
        portal = (await c.get(PORTAL_DASHBOARD)).json()
        api = (await c.get(DASHBOARD_API)).json()
    return {m["label"]: m["value"] for m in portal["metrics"]}, [m["label"] for m in portal["metrics"]], api


@pytest.mark.asyncio
async def test_master_portal_metrics(world):
    metrics, labels, api = await _both(world["master"].email)
    assert labels == ["Students", "Applications", "Pending actions", "Claimable commission", "Claims", "Revenue", "Offers", "Your code"]
    assert metrics["Students"] == api["students"] == 4  # was 1: only the linked login was counted
    assert metrics["Applications"] == api["applications"] and metrics["Offers"] == api["offers"] and metrics["Pending actions"] == api["pending_actions"]
    assert metrics["Claimable commission"] == "INR 1,200" and metrics["Claims"] == 1 and metrics["Revenue"] == "INR 12,000 · USD 500"


@pytest.mark.asyncio
async def test_staff_portal_metrics(world):
    metrics, labels, api = await _both(world["s1"]["user"].email)
    assert labels == ["Students", "Applications", "Pending actions", "Offers", "Your code"]
    assert (metrics["Students"], metrics["Applications"], metrics["Offers"]) == (api["students"], api["applications"], api["offers"]) == (2, 5, 3)
```

(The Revenue separator is `" · "` with a no-break space after `·`, exactly as `_paid_per_currency` builds it — copy the string
from that function when writing the assertion.)

- [ ] **Step 2: Run — expect FAIL** on `Students` (1 ≠ 4 / 1 ≠ 2)
- [ ] **Step 3: Implement** — in `_agent`'s dashboard branch, after `staff = is_agent_staff(user)`:

```python
    if section == "dashboard":
        # AGN-018 (DEC-SCOPE-062): the counts come from the dashboard endpoint's service, so the two never disagree; Students now
        # includes students with no login (the inner join on users above dropped them).
        counts = await headline_counts(db, user)
        open_applications = [(a, u, s) for a, u, s in applications if a.status != WITHDRAWN]
        metrics = [
            {"label": "Students", "value": counts["students"]},
            {"label": "Applications", "value": counts["applications"]},
            {"label": "Pending actions", "value": counts["pending_actions"]},
        ]
        ... (commission metrics unchanged) ...
        metrics.append({"label": "Offers", "value": counts["offers"]})
```

Import `headline_counts` from `app.services.agent_dashboard`. The table rows, subtitle, and every other section stay as they are.

- [ ] **Step 4: Run** `test_agn_018_portal_compat.py` plus the regression files: `test_agn_004_staff_scope.py`,
  `test_agn_008_dashboard.py`, `test_agn_010_counts.py`, `test_agn_014_commission_reports.py`, `test_agn_016_dashboard.py`,
  `test_agn_002_staff_access.py`, `test_agn_001_tenancy.py`. If `test_agn_004_staff_scope.py:93` fails only because its staff
  member also has a student with no login in scope, update the expected `Students` value to the hand count and add the comment
  `# AGN-018 (DEC-SCOPE-062): Students now includes students with no login`. Any other failure is a regression — fix the code.
- [ ] **Step 5: Commit** — `fix(agn-018): portal dashboard counts from the shared service; Students counts no-login students`

---

### Task 5: Web types, URL and the dashboard panel

**Files:**
- Modify: `apps/web/lib/types.ts` (after `SchoolKpi`)
- Create: `apps/web/lib/agentDashboard.ts`
- Create: `apps/web/components/AgentDashboardPanel.tsx`
- Test: `apps/web/tests/components/AgentDashboardPanel.test.tsx`

**Interfaces:**
- Produces: `type AgentDashboard`; `DASHBOARD_URL`, `formatMoney(totals)`; default export `AgentDashboardPanel()` (async server
  component), named exports `AgentDashboardBoard({ data })`, `AgentDashboardSkeleton()`.

- [ ] **Step 1: Types and URL**

`lib/types.ts`:

```ts
// --- AGN-018 agency dashboard (DEC-SCOPE-062; spec §5.3) ---
export type CurrencyTotal = { currency: string; count: number; amount: number };
export type AgentBreakdown = { items: { label: string; count: number }[]; other: number };
export type AgentStaffRow = { code: string; name: string; active: boolean; students: number; applications: number; offers: number; enrollments: number };
export type AgentDashboard = {
  scope: "agency" | "own"; member_code: string | null;
  students: number; applications: number; offers: number; visa_applications: number; visa_approvals: number; enrollments: number;
  pending_documents: number; pending_actions: number;
  by_country: AgentBreakdown; by_university: AgentBreakdown;
  staff: AgentStaffRow[] | null; unassigned_students: number | null;
  commission: { claimable: CurrencyTotal[]; claims: number; revenue: CurrencyTotal[] } | null;
  reports_available: boolean; as_of: string;
};
```

`lib/agentDashboard.ts`:

```ts
import type { CurrencyTotal } from "./types";

export const DASHBOARD_URL = "/api/v1/workflows/overseas/agent/crm/dashboard";

// AGN-014 QA14-01: the portal's Revenue format -- per currency, thousands separators like Python's `:,.0f`, a no-break space
// after the separator so a narrow card wraps between currencies; "INR 0" when none.
export function formatMoney(totals: CurrencyTotal[]): string {
  return totals.map((t) => `${t.currency} ${Math.round(t.amount).toLocaleString("en-US")}`).join(" · ") || "INR 0";
}
```

Before writing it, copy the exact separator from `_paid_per_currency` in `services/portal.py` (the comment there says a no-break
space follows `·`); the test string must use the same characters.

- [ ] **Step 2: Write the failing tests**

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentDashboardPanel, { AgentDashboardBoard, AgentDashboardSkeleton } from "@/components/AgentDashboardPanel";
import { ApiError, serverApi } from "@/lib/api";
import type { AgentDashboard } from "@/lib/types";

vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
const api = vi.mocked(serverApi);
afterEach(() => { cleanup(); api.mockReset(); });

const breakdown = (items: [string, number][], other = 0) => ({ items: items.map(([label, count]) => ({ label, count })), other });
const master: AgentDashboard = {
  scope: "agency", member_code: "ABC-M001", students: 4, applications: 7, offers: 6, visa_applications: 2, visa_approvals: 1, enrollments: 1,
  pending_documents: 4, pending_actions: 2, by_country: breakdown([["Aland", 4], ["Betaland", 3]]), by_university: breakdown([["Alpha University", 4]], 3),
  staff: [{ code: "ABC-S001", name: "Staff One", active: true, students: 2, applications: 5, offers: 3, enrollments: 1 },
          { code: "ABC-S002", name: "Staff Two", active: false, students: 1, applications: 1, offers: 2, enrollments: 0 }],
  unassigned_students: 1,
  commission: { claimable: [{ currency: "INR", count: 1, amount: 1000 }, { currency: "USD", count: 1, amount: 200 }], claims: 1, revenue: [{ currency: "INR", count: 1, amount: 12000 }] },
  reports_available: true, as_of: "2026-10-03T00:00:00Z",
};
const staff: AgentDashboard = { ...master, scope: "own", member_code: "ABC-S001", staff: null, unassigned_students: null, commission: null, reports_available: false };

describe("AgentDashboardBoard (AGN-018)", () => {
  it("shows the Master's KPIs, links, breakdowns, staff table and commission per currency", () => {
    render(<AgentDashboardBoard data={master} />);
    expect(screen.getByText("Whole agency")).toBeInTheDocument();
    expect(screen.getByText("Your code ABC-M001")).toBeInTheDocument();
    for (const [label, value] of [["Total students", "4"], ["Applications", "7"], ["Offers", "6"], ["Visa applications", "2"], ["Visa approvals", "1"], ["Enrollments", "1"], ["Pending documents", "4"], ["Pending actions", "2"]]) {
      const tile = screen.getByText(label, { selector: "dt" }).closest(".kpi-tile") as HTMLElement;
      expect(within(tile).getByText(value)).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: "View students" })).toHaveAttribute("href", "/overseas/agent/students");
    expect(screen.getByRole("link", { name: "View enrolled" })).toHaveAttribute("href", "/overseas/agent/applications?status=enrolled");
    expect(screen.getByRole("link", { name: "Review pending" })).toHaveAttribute("href", "/overseas/agent/documents?view=pending");
    expect(screen.getByRole("link", { name: "Open tasks" })).toHaveAttribute("href", "/overseas/agent/tasks?view=open");
    expect(screen.getAllByText("Includes later stages and withdrawn applications")).toHaveLength(3);
    expect(screen.getByText("INR 1,000 · USD 200")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Applications by university" })).toHaveTextContent("Other3");
    const team = screen.getByRole("table", { name: "Staff performance" });
    expect(within(team).getByText("Deactivated")).toBeInTheDocument();
    expect(within(team).getByRole("rowheader", { name: "Unassigned" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View reports" })).toHaveAttribute("href", "/overseas/agent/reports");
  });

  it("shows Staff their own scope with no commission, staff table or reports link", () => {
    const { container } = render(<AgentDashboardBoard data={staff} />);
    expect(screen.getByText("Your assigned students")).toBeInTheDocument();
    expect(container.textContent?.toLowerCase()).not.toContain("commission");
    expect(screen.queryByRole("table", { name: "Staff performance" })).toBeNull();
    expect(screen.queryByRole("link", { name: "View reports" })).toBeNull();
  });

  it("shows zeros and empty notes for an empty agency", () => {
    render(<AgentDashboardBoard data={{ ...master, students: 0, applications: 0, by_country: breakdown([]), by_university: breakdown([]), staff: [], unassigned_students: 0 }} />);
    expect(screen.getAllByText("No applications yet")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "add staff from Team" })).toHaveAttribute("href", "/overseas/agent/team");
  });
});

describe("AgentDashboardPanel (AGN-018)", () => {
  it("reads the dashboard endpoint", async () => {
    api.mockResolvedValue(staff);
    render(await AgentDashboardPanel());
    expect(api).toHaveBeenCalledWith("/api/v1/workflows/overseas/agent/crm/dashboard");
    expect(screen.getByText("Your assigned students")).toBeInTheDocument();
  });

  it("shows an inline error, not the error text, when the read fails", async () => {
    api.mockRejectedValue(new ApiError("boom: internal detail", 500));
    render(await AgentDashboardPanel());
    expect(screen.getByRole("alert")).toHaveTextContent("Dashboard figures are unavailable right now.");
    expect(screen.queryByText(/internal detail/)).toBeNull();
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/overseas/agent/dashboard");
  });

  it("shows the access card when the session has expired", async () => {
    api.mockRejectedValue(new ApiError("Not authenticated", 401));
    render(await AgentDashboardPanel());
    expect(screen.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeInTheDocument();
  });

  it("has a busy skeleton with a spoken label", () => {
    const { container } = render(<AgentDashboardSkeleton />);
    expect(container.querySelector("[aria-busy='true']")).not.toBeNull();
    expect(screen.getByText("Loading dashboard figures")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run — expect FAIL** (module not found)
- [ ] **Step 4: Implement** `apps/web/components/AgentDashboardPanel.tsx`

```tsx
import Link from "next/link";

import { accessUnavailable } from "./AccessUnavailable";
import { ApiError, serverApi } from "@/lib/api";
import { DASHBOARD_URL, formatMoney } from "@/lib/agentDashboard";
import type { AgentBreakdown, AgentDashboard } from "@/lib/types";

// AGN-018 (DEC-SCOPE-062; spec §6.2): the agency KPI board. A server component: it reads its own endpoint, so a failure here
// leaves the page's title, table and nav working. Reuses SchoolKpiBoard's tile markup and the .table-scroll region pattern.
const NOTE = "Includes later stages and withdrawn applications";
const n = (value: number) => value.toLocaleString("en-IN");

type Tile = { label: string; value: string; link?: [string, string]; note?: string };

function Group({ title, tiles }: { title: string; tiles: Tile[] }) {
  return (
    <section aria-label={title} className="kpi-group">
      <h3>{title}</h3>
      <dl className="kpi-grid">
        {tiles.map((t) => (
          <div className="kpi-tile" key={t.label}>
            <dt>{t.label}</dt>
            <dd className="kpi-value">{t.value}</dd>
            {t.link && <dd><Link href={t.link[1]}>{t.link[0]}</Link></dd>}
            {t.note && <dd className="kpi-note muted">{t.note}</dd>}
          </div>
        ))}
      </dl>
    </section>
  );
}

function Breakdown({ title, data }: { title: string; data: AgentBreakdown }) {
  return (
    <section className="kpi-group" aria-label={title}>
      <h3>{title}</h3>
      {data.items.length === 0 ? (
        <p className="muted">No applications yet</p>
      ) : (
        <div className="table-scroll" tabIndex={0} role="region" aria-label={title}>
          <table className="table">
            <caption className="visually-hidden">{title}</caption>
            <thead><tr><th scope="col">Name</th><th scope="col">Applications</th></tr></thead>
            <tbody>
              {data.items.map((i) => <tr key={i.label}><th scope="row">{i.label}</th><td>{n(i.count)}</td></tr>)}
              {data.other > 0 && <tr><th scope="row">Other</th><td>{n(data.other)}</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function AgentDashboardBoard({ data }: { data: AgentDashboard }) {
  const master = data.scope === "agency";
  return (
    <div className="card agent-dashboard">
      <p className="muted">
        {master ? "Whole agency" : "Your assigned students"}
        {data.member_code && <> · Your code {data.member_code}</>}
      </p>
      <Group title="Students" tiles={[
        { label: "Total students", value: n(data.students), link: ["View students", "/overseas/agent/students"] },
        { label: "Pending actions", value: n(data.pending_actions), link: ["Open tasks", "/overseas/agent/tasks?view=open"] },
      ]} />
      <Group title="Pipeline" tiles={[
        { label: "Applications", value: n(data.applications), link: ["View applications", "/overseas/agent/applications"] },
        { label: "Offers", value: n(data.offers), note: NOTE },
        { label: "Visa applications", value: n(data.visa_applications), note: NOTE },
        { label: "Visa approvals", value: n(data.visa_approvals), note: NOTE },
        { label: "Enrollments", value: n(data.enrollments), link: ["View enrolled", "/overseas/agent/applications?status=enrolled"] },
      ]} />
      <Group title="Documents" tiles={[{ label: "Pending documents", value: n(data.pending_documents), link: ["Review pending", "/overseas/agent/documents?view=pending"] }]} />
      {data.commission && (
        <Group title="Commission" tiles={[
          { label: "Claimable commission", value: formatMoney(data.commission.claimable) },
          { label: "Claims", value: n(data.commission.claims) },
          { label: "Revenue", value: formatMoney(data.commission.revenue) },
        ]} />
      )}
      <Breakdown title="Applications by country" data={data.by_country} />
      <Breakdown title="Applications by university" data={data.by_university} />
      {data.staff && <StaffTable rows={data.staff} unassigned={data.unassigned_students ?? 0} />}
      {data.reports_available && <p><Link href="/overseas/agent/reports">View reports</Link></p>}
    </div>
  );
}

function StaffTable({ rows, unassigned }: { rows: NonNullable<AgentDashboard["staff"]>; unassigned: number }) {
  const title = "Staff performance";
  return (
    <section className="kpi-group" aria-label={title}>
      <h3>{title}</h3>
      {rows.length === 0 && <p className="muted">No staff yet — <Link href="/overseas/agent/team">add staff from Team</Link></p>}
      <div className="table-scroll" tabIndex={0} role="region" aria-label={title}>
        <table className="table">
          <caption className="visually-hidden">{title}</caption>
          <thead><tr>{["Member", "Students", "Applications", "Offers", "Enrollments"].map((h) => <th scope="col" key={h}>{h}</th>)}</tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.code}>
                <th scope="row">{r.name} <span className="muted">{r.code}</span>{!r.active && <> <span className="badge">Deactivated</span></>}</th>
                <td>{n(r.students)}</td><td>{n(r.applications)}</td><td>{n(r.offers)}</td><td>{n(r.enrollments)}</td>
              </tr>
            ))}
            <tr><th scope="row">Unassigned</th><td>{n(unassigned)}</td><td colSpan={3} /></tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function AgentDashboardSkeleton() {
  return (
    <div className="card agent-dashboard" aria-busy="true">
      <span className="visually-hidden">Loading dashboard figures</span>
      {[2, 5, 1].map((count, g) => (
        <div className="kpi-group" key={g} aria-hidden="true">
          <dl className="kpi-grid">{Array.from({ length: count }, (_, i) => <div className="kpi-tile kpi-skeleton" key={i} />)}</dl>
        </div>
      ))}
    </div>
  );
}

export default async function AgentDashboardPanel() {
  let data: AgentDashboard;
  try {
    data = await serverApi<AgentDashboard>(DASHBOARD_URL);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return accessUnavailable(e, "/overseas/login");
    return (
      <div className="card agent-dashboard">
        <p className="form-error" role="alert">Dashboard figures are unavailable right now.</p>
        <p><Link href="/overseas/agent/dashboard">Try again</Link></p>
      </div>
    );
  }
  return <AgentDashboardBoard data={data} />;
}
```

Add to `apps/web/app/globals.css` (next to the `.kpi-*` rules): `.kpi-skeleton { min-height: 72px; background: #f1f5fa; }` and
`.agent-dashboard { margin-bottom: 24px; }` — existing colour/spacing values only.

- [ ] **Step 5: Run — expect PASS**; then `npx tsc --noEmit` and `npm run lint`
- [ ] **Step 6: Refactor** — if the file exceeds ~200 lines, nothing else changes; keep it one file (the spec allows it). Rerun.
- [ ] **Step 7: Commit** — `feat(agn-018): agency dashboard board with loading, empty and error states`

---

### Task 6: Wire the board into the dashboard page

**Files:**
- Modify: `apps/web/components/PortalSection.tsx` (optional `lead` prop)
- Modify: `apps/web/components/PortalPage.tsx` (dashboard branch for agents)
- Test: `apps/web/tests/components/PortalPage.agentDashboard.test.tsx`; rerun `PortalPage.agentApplications.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PortalPage from "@/components/PortalPage";
import { serverApi } from "@/lib/api";

vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("notFound"); }, useSearchParams: () => new URLSearchParams("") }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/WorkflowPanel", () => ({ default: () => null }));
vi.mock("@/components/RefreshOnHistoryNav", () => ({ default: () => null }));
vi.mock("@/components/AgentDashboardPanel", () => ({ default: () => <p>agent board</p>, AgentDashboardSkeleton: () => <p>board loading</p> }));

const api = vi.mocked(serverApi);
const payload = { title: "Agent Dashboard", subtitle: "s", actions: [], metrics: [{ label: "Students", value: 4 }], columns: [], rows: [], panels: [] };
const me = (role: string) => ({ id: "u", role, full_name: "U", email: "u@x", agent_member_role: role === "agent" ? "master" : null, agent_permissions: null });

beforeEach(() => api.mockReset());
afterEach(cleanup);

describe("PortalPage agency dashboard (AGN-018)", () => {
  it("puts the board under the title and drops the duplicate metric tiles for agents", async () => {
    api.mockImplementation((path: string) => Promise.resolve(path === "/api/v1/auth/me" ? me("agent") : path.endsWith("unread-count") ? { unread: 0 } : payload));
    render(await PortalPage({ division: "overseas", role: "agent", section: "dashboard" }));
    expect(await screen.findByText("agent board")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Agent Dashboard" })).toBeInTheDocument();
    expect(document.querySelector(".metric-grid")).toBeNull();
  });

  it("leaves a Super Admin's dashboard as it was", async () => {
    api.mockImplementation((path: string) => Promise.resolve(path === "/api/v1/auth/me" ? me("super_admin") : payload));
    render(await PortalPage({ division: "overseas", role: "agent", section: "dashboard" }));
    expect(screen.queryByText("agent board")).toBeNull();
    expect(document.querySelector(".metric-grid")).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run — expect FAIL**
- [ ] **Step 3: Implement**

`PortalSection.tsx` — signature `({data, lead}: {data: PortalPayload; lead?: React.ReactNode})`, render `{lead}` right after the
`portal-title` div (before the metric grid). Every other caller passes nothing, so nothing else changes.

`PortalPage.tsx` — in the `main` chain, before the final `<PortalSection data={data}/>`:

```tsx
:agent&&section==="dashboard"&&user.role==="agent"?<PortalSection data={{...data,metrics:[]}} lead={<Suspense fallback={<AgentDashboardSkeleton/>}><AgentDashboardPanel/></Suspense>}/>
```

with `import {Suspense} from "react";` and `import AgentDashboardPanel,{AgentDashboardSkeleton} from "./AgentDashboardPanel";`,
plus a one-line comment: `// AGN-018 (DEC-SCOPE-062): agents get the KPI board under the title; its own fetch, so the payload stays the gate.`

- [ ] **Step 4: Run — expect PASS**: the new test, `PortalPage.agentApplications.test.tsx` (its call list is unchanged because
  PortalSection is mocked there), `PortalPage.agentTasks.test.tsx`, `PortalPage.agentNotifications.test.tsx`; `tsc`; lint.
- [ ] **Step 5: Commit** — `feat(agn-018): agency dashboard page streams the KPI board under the title`

---

### Task 7: Role-specific navigation and the Add-student link

**Files:**
- Modify: `apps/web/lib/navigation.ts:85,103-114`
- Modify: `apps/web/components/AgentStudentsPanel.tsx:60-79`
- Test: `apps/web/tests/lib/navigation.agent.test.ts`, `apps/web/tests/components/AgentStudentsPanel.test.tsx` (append),
  rerun `navigation.test.ts`, `PortalShell.children.test.tsx`, `NavGroup.test.tsx`, `PortalShell.badge.test.tsx`

- [ ] **Step 1: Update the nav tests first (deliberate, G4)** in `navigation.agent.test.ts`:
  - `"shows Tasks to both roles…"`: label expectation becomes `"Tasks & Follow-ups"`.
  - Applications children expectation becomes `["all", "draft", "submitted", "offer", "visa", "enrolled", "withdrawn"]`, and add
    `expect(nav.find((i) => i.href === "/overseas/agent/applications")?.children?.[0].label).toBe("All applications")`.
  - New test:

```ts
  it("gives staff My Students with All and Add; a Master keeps Students (AGN-018 G4)", () => {
    const students = (items: ReturnType<typeof agentNavFor>) => items.find((i) => i.href === "/overseas/agent/students");
    expect(students(agentNavFor(nav, "staff"))?.label).toBe("My Students");
    expect(students(agentNavFor(nav, "staff"))?.children?.map((c) => [c.label, c.href])).toEqual([
      ["All", "/overseas/agent/students"],
      ["Add", "/overseas/agent/students?new=1"],
    ]);
    expect(students(agentNavFor(nav, "master"))).toEqual({ label: "Students", href: "/overseas/agent/students" });
  });
```

  - `"leaves a Master's nav unchanged"` stays (Master = `PORTAL_NAV` as defined).
  - Staff href lists are unchanged (no item added or removed).

- [ ] **Step 2: Write the Add-link test** (append to `AgentStudentsPanel.test.tsx`):

```tsx
  it("opens the add form from the sidebar's Add link and drops new=1 from the URL (AGN-018)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([])))));
    window.history.replaceState(null, "", "/overseas/agent/students?new=1");
    render(<AgentStudentsPanel memberRole="staff" />);
    expect(await screen.findByRole("form", { name: /add student/i })).toBeInTheDocument();
    await waitFor(() => expect(window.location.search).toBe(""));
  });
```

(Use the add form's accessible name as it is today — read `AgentStudentForm`'s `aria-label`/heading before writing the query.)

- [ ] **Step 3: Run — expect FAIL** (labels, children, form not open)
- [ ] **Step 4: Implement**

`navigation.ts`:

```ts
// AGN-018 (DEC-SCOPE-062 G4): "All applications" first, then the AGN-008 filters (?status=all is the list's own default view).
const AGENT_APPLICATION_FILTERS: NavItem[] = STATUS_GROUPS.map((g) => ({ label: GROUP_LABELS[g], href: `/overseas/agent/applications?status=${g}` }));
const NAV_LABELS: Record<string, string> = { tasks: "Tasks & Follow-ups" }; // EVID-015 §4 wording (AGN-018)
```

and in `"overseas/agent"` use `label: NAV_LABELS[x] ?? <existing title-case expression>`.

In `agentNavFor`, staff get the students item replaced:

```ts
// AGN-018 (DEC-SCOPE-062 G4): the EVID-015 §4 staff sidebar -- "My Students" with All and Add (Add opens the existing form). No
// Journey link until a route exists. Nothing is removed, so no access changes.
const STAFF_STUDENTS: NavItem = { label: "My Students", href: "/overseas/agent/students", children: [
  { label: "All", href: "/overseas/agent/students" },
  { label: "Add", href: "/overseas/agent/students?new=1" },
] };
export function agentNavFor(nav: NavItem[], memberRole?: string | null, permissions?: AgentPermissions | null): NavItem[] {
  if (memberRole !== "staff") return nav;
  return nav
    .filter((item) => !STAFF_HIDDEN.has(item.href) && (item.href !== STAFF_REPORTS || permissions?.can_view_reports === true))
    .map((item) => (item.href === STAFF_STUDENTS.href ? STAFF_STUDENTS : item));
}
```

`GROUP_LABELS.all` is already "All applications". Check `lib/agentApplications.ts` `parseGroup("all")` returns `"all"` (it does —
`all` is in `STATUS_GROUPS`).

`AgentStudentsPanel.tsx` — in the mount effect add `if (params.get("new") === "1") setAdding(true);`, and in the URL-sync effect add
`"new"` to the keys it deletes: `["q", "archived", "page", "new"].forEach(...)`. The form's existing `autoFocus` on Full name gives
focus; Cancel/save keep the QA5-02 focus return.

- [ ] **Step 5: Run — expect PASS**: `navigation.agent.test.ts`, `navigation.test.ts`, `AgentStudentsPanel.test.tsx`,
  `PortalShell.children.test.tsx`, `NavGroup.test.tsx`, `PortalShell.badge.test.tsx`. If `PortalShell.children.test.tsx` asserts the
  old Applications child list or "Tasks" label, update that expectation only (deliberate, G4) with an `AGN-018` comment. `tsc`; lint.
- [ ] **Step 6: Commit** — `feat(agn-018): staff My Students (All / Add), All applications, Tasks & Follow-ups`

---

### Task 8: Playwright spec (run in the browser-validation phase)

**Files:**
- Create: `apps/web/tests/e2e/agn-018-dashboard.spec.ts`
- Check: e2e specs that assert the "Tasks" nav label or the Applications children (`agn-008`, `agn-016`): update label text only.

- [ ] **Step 1: Write the spec** using `helpers/agency.ts` (`registerApprovedAgency`, `signIn`) and the staff-creation flow
  `agn-002-staff.spec.ts` already uses. Cases:
  1. Master lands on `/overseas/agent/dashboard`: headings "Students", "Pipeline", "Documents", "Commission"; text "Whole agency";
     table "Staff performance"; tile "Revenue".
  2. Staff: "Your assigned students"; no "Commission" text; sidebar link "My Students"; its "Add" link opens the add form with focus
     in Full name; `page.url()` has no `new=1`.
  3. 320 px viewport: `document.documentElement.scrollWidth <= 320`; the breakdown region is focusable by Tab.
- [ ] **Step 2: Do not run here** (lite tests only); record it for the browser-validation session.
- [ ] **Step 3: Commit** — `test(agn-018): Playwright spec for the agency dashboards (run at browser validation)`

---

### Task 9: Documentation and traceability

**Files:** `docs/architecture/API_CONTRACT.md` §8, `docs/architecture/RBAC_MATRIX.md` (Dashboard row ~L186), `docs/quality/RTM.md`,
`docs/delivery/ENHANCEMENT_BACKLOG.md` (new §AGN-018), `docs/delivery/AGENT_CRM_BACKLOG.md` (status table), `docs/ux/ROLE_NAVIGATION.md`
(Agent), `docs/ux/SCREEN_CATALOG.md` (SCR-AGT-003), `docs/delivery/RAID.md`, the spec (§5.3: drop `role` from the staff row — staff
rows are staff only).

- [ ] **Step 1:** API_CONTRACT: the route, gate, response schema, one-snapshot note for the headline counts, breakdown/staff
  statements separate, `Cache-Control: private, no-store`, 401/403 semantics, super admin 403.
- [ ] **Step 2:** RBAC Dashboard row: "✅ full (KPIs, staff table, commission) | ✅ limited (own students; no commission, no staff
  metrics) — AGN-018".
- [ ] **Step 3:** RTM rows AGN-018-AC01…AC09 → tests; ENHANCEMENT_BACKLOG §AGN-018 (status: implemented on
  `feature/agn-018-master-dashboard-impl`; **not COMPLETE** — browser validation, the owner's full suites and an independent Codex
  review pending); AGENT_CRM_BACKLOG status row.
- [ ] **Step 4:** ROLE_NAVIGATION and SCREEN_CATALOG: Master / Staff dashboard and the staff sidebar.
- [ ] **Step 5:** RAID: I-48 still open (non-agent offer counts, now its own item); new: portal "Claimable commission" INR label sums
  currencies (D4); portal Reports "Students" still drops no-login students (outside AGN-018's dashboard scope, for ang-020);
  `student_documents.application_id` unindexed (watch for ang-019/020).
- [ ] **Step 6: Commit** — `docs(agn-018): contract, RBAC, RTM, backlog, navigation, RAID`

---

## Verification before hand-off (lite)

- API: `tests/test_agn_018_*.py` + the Task 4 regression list.
- Web: the Task 5–7 vitest files + `tsc --noEmit` + lint.
- Not claimed: browser validation (Task 8 run), full suites, independent Codex review.
