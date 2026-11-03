# itc-030 IT counselor dashboard: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A filtered IT counselor and IT Admin dashboard with 9 widgets, served by `GET /counselor/it/dashboard` and rendered on
`/it/counselor/dashboard` and `/it/admin/counselor-dashboard`.

**Architecture:** One read-only service (`services/it_counselor_dashboard.py`) builds a lead book and a student book from the caller's
scope and the filters. Each widget is one SQL statement, and its count and first 10 rows come from the same statement. A thin router
does the role gate. A Next server component renders the board, and a client filter form keeps its values in the URL.

**Tech Stack:** FastAPI, SQLAlchemy async, Postgres, Next.js (App Router) and React, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-03-itc-030-it-counselor-dashboard-design.md`

## Global Constraints
- No migration. No new dependency. The portal payload of `/it/counselor/dashboard` is unchanged.
- Messages: `FORBIDDEN = "Only an IT counselor or the IT Admin has this dashboard"`, `BATCH_OUTSIDE = "The batch is not in that course"`,
  `OWNER_ADMIN_ONLY = "The owner filter is for the IT Admin"`, `CHOOSE_COUNSELOR = "Choose an IT counselor"`, and
  `application_filters.UNKNOWN_VALUE` / `DATE_ORDER`.
- `LIMIT = 10`. Dates are India time. Numbering: DEC-SCOPE-367, API §12JM, RBAC §2.267.

## Review Focus
- A follow-up due later today counts as "today", not overdue. A follow-up due at 00:00 IST tomorrow is excluded (test in Task 1).
- A merged lead (`merged_at` set) never counts (Task 1).
- A student with two active enrolments counts once in Enrolled students (Task 1).
- An IT Admin `owner` that is an overseas counselor → 422 (Task 1).
- A 422 on the page falls back to the unfiltered board with the message, not the error card (Task 3, e2e).

---

### Task 1: Service and route

**Files:**
- Create: `apps/api/app/services/it_counselor_dashboard.py`, `apps/api/app/api/it_counselor_dashboard.py`
- Modify: `apps/api/app/main.py` (import + router tuple)
- Test: `apps/api/tests/test_itc_030_it_counselor_dashboard.py`

**Interfaces:**
- Produces: `async def dashboard(db, user, now: datetime, *, program: str|None, batch: str|None, date_from: str|None, date_to: str|None,
  stage: str|None, owner: str|None) -> dict` (shape per spec §2). Route: `GET /counselor/it/dashboard` with query params
  `program, batch, from, to, stage, owner`.

- [ ] Write the tests: the 403 matrix, the scope, the definitions of every widget, each filter, the 422s, admin with owner, an empty
  counselor, `count == len(items)` while ≤ LIMIT, and the Review Focus cases.
- [ ] Run them; they fail with a 404 (no route).
- [ ] Implement it, reusing `application_filters.date_range`, `bdm_appointments.today_ist`, `lead_handover.convertible_stage`,
  `fee_accounts.balance_for`, `lead_stages` and `it_status_labels.labels(db, "lead")` for the stage labels.
- [ ] Run the tests (pass), plus `test_tel_017_it_counselor.py` and `test_ccrm_032*` (pass).
- [ ] Commit.

### Task 2: Admin portal section and nav

**Files:** `apps/api/app/services/portal.py` (a header-only `counselor-dashboard` section for it_admin) and `apps/web/lib/navigation.ts`
(`"counselor-dashboard"` in the it/admin list). Test: append to the Task 1 test file (the admin portal section returns its title) and
`apps/web/tests/lib/navigation*.test.ts` if it pins the admin nav.
- [ ] Test, then implement, then verify, then commit.

### Task 3: Frontend board and filters

**Files:**
- Create: `apps/web/components/ItCounselorDashboardPanel.tsx` (server: fetch, error/401 states, and the board),
  `apps/web/components/ItCounselorDashboardFilters.tsx` (client: a GET form)
- Modify: `apps/web/lib/types.ts` (`ItCounselorDashboard` types), `apps/web/components/PortalPage.tsx` (it/counselor dashboard lead →
  panel with query; it/admin counselor-dashboard → panel)
- Test: `apps/web/tests/components/ItCounselorDashboard.test.tsx`, `apps/web/tests/e2e/itc-030-it-counselor-dashboard.spec.ts`

- [ ] Vitest for the board's empty texts, overdue badge, stage note, "Showing 10 of N" and the filter Clear link. Watch it fail, then
  implement.
- [ ] Run `npx vitest run`, `npx tsc --noEmit` and `npx eslint` on the changed files.
- [ ] Write the e2e (it runs in Phase 5).
- [ ] Commit.

### Task 4: Docs
Add DEC-SCOPE-367 to `PRODUCT_DECISION_REGISTER.md`, API §12JM to `API_CONTRACT.md`, RBAC §2.267 to `RBAC_MATRIX.md`, an RTM row,
and the backlog status line for itc-030. Then commit.
