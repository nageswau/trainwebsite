# AGN-019 Staff Performance and Student Funnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Master-only Staff Performance page: per-staff Students / Applications / Offers / Visa applications / Visa approvals /
Enrollments and a Students → Applications → Submitted → Offers → Visa → Enrolled funnel, filtered by a student-cohort date range.

**Architecture:** A new read-only `GET /api/v1/workflows/overseas/agent/crm/performance` (router `api/agent_performance.py`, service
`services/agent_performance.py`) built on AGN-018's scope helpers (`agency_applications`, `offer_clause`, and `owner_join` extracted
from `staff_rows`). A new sidebar page renders `AgentPerformanceSection` (server frame) → `AgentPerformancePanel` (client, the
AGN-014 report panel's data flow).

**Tech Stack:** FastAPI, Pydantic v2, async SQLAlchemy 2, PostgreSQL 16, pytest-asyncio; Next.js 15 / React, vitest + Testing Library,
Playwright.

**Spec:** `docs/superpowers/specs/2026-10-03-agn-019-staff-performance-funnel-design.md` (`DEC-SCOPE-063`).

## Global Constraints

- No migration, no new dependency (backend or web), no change to `AgentDashboardOut`, `/dashboard`, `services/portal.py` or models.
- Guards before dates: a refused caller gets 401/403, never 422.
- Staff refusal message, verbatim: `Only an agency Master can view staff performance`.
- Date messages, verbatim (AGN-014): `<name> must be a date (YYYY-MM-DD)`, `date_to must be on or after date_from`,
  `date_to must be before 9999-12-31`. Days are inclusive UTC days on `agent_students.created_at`.
- Response: no ids, emails or phones; `Cache-Control: private, no-store`; snake_case.
- Log line `agent_performance.read` extra fields exactly: `org_id`, `actor_id`, `filtered`, `rows`, `duration_ms`.
- Funnel levels (spec §4.2): 5 enrolled; 4 visa case exists; 3 `offer_clause()`; 2 `submitted_on` set; 1 any application; 0 none.
- UI copy: page `Staff performance`; nav `Staff Performance`; empty `No students were added in this period.` / `Your agency has no
  students yet.`; non-Master `Staff performance is available to agency Masters.`; error `Couldn't load staff performance.`.
- Lite tests only (owner, 2026-10-03): run the changed/new test files and the directly affected module tests; the owner runs full
  suites separately. Backend tests run against this worktree's own Postgres (`agn019-pg`, port 5439).

Backend test command (from `apps/api`, PowerShell or bash):
`DATABASE_URL=postgresql+asyncpg://edusphere:edusphere@localhost:5439/edusphere .venv/Scripts/python -m pytest -q <files>`
Web test command (from `apps/web`): `npx vitest run <files>`.

## Review Focus

1. An agency student whose application is reachable both through the agency record and through the linked login counts that
   application once per row — covered in Task 3 (`test_application_reachable_two_ways_counts_once`).
2. A student with only a withdrawn, offer-less application still reaches "Applications" (funnel) but not the table's Applications
   column — covered in Task 3/4 hand counts (r1's a10).
3. A deactivated member holding only an **archived** student (table zeros, funnel 1) is still listed — Task 3
   (`test_deactivated_member_with_only_archived_student_is_listed`).
4. Applying a range then switching the funnel select, then applying another range, resets the select to the agency — Task 7.
5. A range whose `date_to` equals the boundary day includes a student created at 23:59:59Z that day and excludes 00:00:00Z the next —
   Task 5.

---

### Task 1: Extract `owner_join()` from `staff_rows` (behaviour-preserving)

**Files:**
- Modify: `apps/api/app/services/agent_dashboard.py` (the `.join(AgentStudent, or_(...))` inside `staff_rows`)
- Test (existing, unchanged): `apps/api/tests/test_agn_018_dashboard.py`, `apps/api/tests/test_agn_018_offer_parity.py`

**Interfaces:** Produces `owner_join() -> ColumnElement[bool]` in `app.services.agent_dashboard`.

- [ ] **Step 1: Run the guarding tests (green baseline)** — `pytest -q tests/test_agn_018_dashboard.py tests/test_agn_018_offer_parity.py` → 19 passed.
- [ ] **Step 2: Refactor**

```python
def owner_join() -> ColumnElement[bool]:
    """An application belongs to an agency student by the agency record, or by the student's login (AGN-008 A6); used where the two
    tables are joined (AGN-018 staff table, AGN-019 performance)."""
    return or_(OverseasApplication.agent_student_id == AgentStudent.id, and_(AgentStudent.student_id.is_not(None), OverseasApplication.student_id == AgentStudent.student_id))
```
and in `staff_rows`: `.join(AgentStudent, owner_join())`.
- [ ] **Step 3: Re-run** the same command → 19 passed.
- [ ] **Step 4: Commit** `refactor(agn-019): share AGN-018's application-owner join`.

### Task 2: Route, gate, schemas, dates (security and contract)

**Files:**
- Create: `apps/api/app/api/agent_performance.py`, `apps/api/app/services/agent_performance.py`
- Modify: `apps/api/app/schemas.py` (after `AgentDashboardOut`), `apps/api/app/main.py` (import + router tuple),
  `apps/api/app/api/workflows.py` (extract `_report_range` from `_commission_report_items`)
- Test: `apps/api/tests/test_agn_019_security.py` (new), `apps/api/tests/test_agn_003_matrix.py` (one STAFF_REFUSED and one
  MASTER_ALLOWED row; docstring: Staff Performance is no longer N/A)

**Interfaces:**
- Produces `report_range(date_from: str | None, date_to: str | None) -> tuple[date | None, date | None]` in `app.api.workflows`
  (renamed from inline checks; raises the three 422s).
- Produces `performance(db, user, start: date | None, end: date | None) -> dict` (shape = `AgentPerformanceOut`).
- Schemas `AgentFunnelOut`, `AgentPerformanceCountsOut`, `AgentPerformanceRowOut`, `AgentPerformanceOut` (spec §5.3).

- [ ] **Step 1: Write failing tests** (`test_agn_019_security.py`): 401 without session; 403 for super admin and counselor; staff
  403 with the verbatim message, with and without `can_view_reports`; suspended org 403; deactivated Master 401/403; staff with
  `date_from=bad` still 403; Master `date_from=bad` → 422 `date_from must be a date (YYYY-MM-DD)`; `to<from` → 422; `date_to=9999-12-31`
  → 422; Master 200 with `Cache-Control: private, no-store`; empty org → `rows == []`, `unassigned is None`, all-zero `total`;
  the log record's `extra_fields` keys are exactly the five listed. Matrix rows added.
- [ ] **Step 2: Run** → FAIL (404 route not found).
- [ ] **Step 3: Implement** the schemas, `report_range` (and use it in `_commission_report_items`), the router (spec §5.1 order),
  and a service whose `performance()` returns the full shape (Task 3/4 fill the counts; here the queries already exist but are only
  exercised for the empty org).
- [ ] **Step 4: Run** the new file, the matrix file and `tests/test_agn_014_commission_reports.py` → PASS.
- [ ] **Step 5: Commit** `feat(agn-019): Master-only performance endpoint, gate and date validation`.

### Task 3: Per-staff table counts and rows

**Files:**
- Create: `apps/api/tests/agn019_helpers.py` (`performance_world`, hand counts), `apps/api/tests/test_agn_019_performance.py`,
  `apps/api/tests/test_agn_019_parity.py`
- Modify: `apps/api/app/services/agent_performance.py` (`table_counts`, row rules)

**Fixture** `performance_world` = `dashboard_world` + r6 (s2, `eligibility_evaluation`, `submitted_on` set), r7 (s2, `enrolled`, no
visa case), r8 (s3, no application). Hand counts (table):

| owner | students | applications | offers | visa_applications | visa_approvals | enrollments |
|---|---|---|---|---|---|---|
| s1 (r1 r2 r4) | 2 | 5 | 3 | 1 | 1 | 1 |
| s2 (r3 r6 r7) | 3 | 3 | 3 | 1 | 0 | 1 |
| s3 (r8) | 1 | 0 | 0 | 0 | 0 | 0 |
| unassigned (r5) | 1 | 1 | 1 | 0 | 0 | 0 |
| total | 7 | 9 | 7 | 2 | 1 | 2 |

- [ ] **Step 1: Write failing tests:** table hand counts per row/unassigned/total; rows ordered by `seq` with codes; no uuids in the
  response; noise org absent; active zero staff listed; deactivated member with only an archived student listed `active: false`;
  deactivated all-zero member absent; application reachable two ways counts once; parity file: with no dates, each staff row's four
  AGN-018 fields equal `/dashboard`'s `staff` rows (using `dashboard_world`).
- [ ] **Step 2: Run** → FAIL (counts are zero / rows missing).
- [ ] **Step 3: Implement** `cohort`, `_visa_by_application`, `_from_cohort`, `table_counts`, row building (spec §5.2).
- [ ] **Step 4: Run** the three files → PASS.
- [ ] **Step 5: Commit** `feat(agn-019): per-staff counts by current owner`.

### Task 4: Funnel ("reached at least") and reassignment

**Files:** Modify `apps/api/app/services/agent_performance.py` (`funnel_counts`); Test `apps/api/tests/test_agn_019_performance.py`.

Hand counts (funnel: students, applications, submitted, offers, visa, enrolled) — levels r1 3, r2 5, r3 4, r4 1, r5 3, r6 2, r7 5, r8 0:
s1 `3,3,2,2,1,1`; s2 `3,3,3,2,2,1`; s3 `1,0,0,0,0,0`; unassigned `1,1,1,1,0,0`; total `8,7,6,5,3,2`.

- [ ] **Step 1: Write failing tests:** funnel hand counts; every funnel non-increasing; after `POST .../crm/students/{r7}/assign`
  `{"member_id": s1}` (as the Master) s1 = `4,4,3,3,2,2`, s2 = `2,2,2,1,1,0` and table rows move by r7's numbers.
- [ ] **Step 2: Run** → FAIL (funnel zeros).
- [ ] **Step 3: Implement** `_level`, `funnel_counts`, wire into `performance()`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(agn-019): student funnel by furthest stage reached`.

### Task 5: Cohort date range

**Files:** Test `apps/api/tests/test_agn_019_performance.py`; implementation already in `cohort()` (Task 3) — this task proves it.

- [ ] **Step 1: Write tests:** set `created_at` of r1 = `2026-01-01T00:00:00Z`, r3 = `2026-01-31T23:59:59Z`, r5 =
  `2026-02-01T00:00:00Z`; `date_from=2026-01-01&date_to=2026-01-31` → total funnel `2,2,2,2,1,0`, table total students 2,
  applications 3, offers 3, visa_applications 1; `date_from=2026-02-01&date_to=2026-02-01` → only r5; `date_to=2026-01-31` alone → r1, r3;
  echoed `date_from`/`date_to`.
- [ ] **Step 2: Run** — if they pass at once (the code exists from Task 3), break `cohort()` temporarily (drop the `end` clause),
  confirm the boundary test fails, restore.
- [ ] **Step 3: Commit** `test(agn-019): cohort date range boundaries`.

### Task 6: Web contract helpers

**Files:** Create `apps/web/lib/agentPerformance.ts`; Test `apps/web/tests/lib/agentPerformance.test.ts`.

**Interfaces (produced):** `PERFORMANCE_URL`, types `AgentFunnel`, `AgentPerformanceCounts`, `AgentPerformanceRow`,
`AgentPerformance`, `FunnelStage`; `funnelStages(f: AgentFunnel): FunnelStage[]`; `isPerformance(body: unknown): body is AgentPerformance`.

- [ ] **Step 1: Failing tests:** six stages in order with labels Students, Applications, Submitted, Offers, Visa, Enrolled; percent
  rounded of students; `null` percents when students = 0; `isPerformance` true for a full body, false for `null`, `{}`, `{rows: []}`.
- [ ] **Step 2: Run** → FAIL (module missing). **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit.**

### Task 7: Panel

**Files:** Create `apps/web/components/AgentPerformancePanel.tsx`; Modify `apps/web/components/AgentDashboardPanel.tsx` (export
`TableRegion`, `headingId`, `n` — no behaviour change) and `apps/web/app/globals.css` (`.staff-performance` rules); Test
`apps/web/tests/components/AgentPerformancePanel.test.tsx`.

- [ ] **Step 1: Failing tests:** loading text then funnel + table; fetch URL with range from `?from=&to=`; table rows with
  "Deactivated" badge and Unassigned + total rows; funnel select switches to a staff member without another fetch and resets after
  Apply; empty filtered/unfiltered texts; `—` percent when 0 students; 401 → "Sign in again" link; 403 → server message; 500 →
  "Couldn't load staff performance." + Try again refetches; client `to < from` error focuses To with no fetch; server 422 on
  `date_from` is shown on From; a stale earlier response does not overwrite a newer one.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (spec §6.4). **Step 4: Run** the new test and
  `tests/components/AgentDashboardPanel.test.tsx` → PASS. **Step 5: Commit.**

### Task 8: Navigation, page wiring, section, dashboard link

**Files:** Modify `apps/web/lib/navigation.ts`, `apps/web/components/PortalPage.tsx`, `apps/web/components/AgentDashboardPanel.tsx`
(link); Create `apps/web/components/AgentPerformanceSection.tsx`; Tests `apps/web/tests/lib/navigation.agent.test.ts` (staff lists
unchanged; Master nav has `/overseas/agent/performance` labelled "Staff Performance" after Reports),
`apps/web/tests/components/AgentPerformanceSection.test.tsx` (Master → panel; staff → message, no fetch),
`apps/web/tests/components/AgentDashboardPanel.test.tsx` (link present for Masters).

- [ ] Steps: failing tests → run (FAIL) → implement → run (PASS, plus `tests/lib/navigation.test.ts`,
  `tests/components/PortalShell.allChildren.test.tsx`, `tests/components/PortalPage.agentDashboard.test.tsx`) → typecheck the changed
  files (`npx tsc --noEmit -p .`) → commit.

### Task 9: E2E spec (written now, run in the owner's browser-validation session)

**Files:** Create `apps/web/tests/e2e/agn-019-performance.spec.ts` following `agn-018-dashboard.spec.ts` (Master: nav item, filter,
funnel switch, 320 px no horizontal scroll, axe; staff: no nav item, the Masters-only message).

- [ ] Write; `npx tsc --noEmit -p .` type-checks it; not run here (needs the full stack). Commit.

### Task 10: Documentation and lite verification

**Files:** `docs/delivery/ENHANCEMENT_BACKLOG.md` (§AGN-019), `docs/delivery/AGENT_CRM_BACKLOG.md` (status table + ang-019
status), `docs/quality/RTM.md`, `docs/architecture/RBAC_MATRIX.md` (Staff Performance row), `docs/architecture/API_CONTRACT.md`,
`docs/ux/SCREEN_CATALOG.md` + `screen_catalog.json`, `docs/ux/ROLE_NAVIGATION.md`, `docs/delivery/RAID.md` (branch filter deferred;
R-14 measured), `docs/decisions/PRODUCT_DECISION_REGISTER.md` (DEC-SCOPE-063 status).

- [ ] Seeded timing check: 1 org, 20 staff, 2,000 students, 4,000 applications → record the endpoint time in RAID R-14.
- [ ] Lite run: all AGN-019 files + AGN-018 + AGN-014 + matrix (backend); new + touched web tests; ruff on changed Python; `tsc`.
- [ ] Status everywhere: "implemented, lite-tested; browser QA, full suites and Codex review pending" — **not complete**.
