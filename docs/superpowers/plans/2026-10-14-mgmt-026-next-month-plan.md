# mgmt-026 Next month plan + target vs actual — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (native, chosen by the owner's "proceed without prompts").
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** Monthly management plans whose items are typed per vertical. KPI-linked items get a live actual and achievement %; free-text
items toggle done; items can spawn mgmt-028 tasks.

**Architecture:** Two new tables (`management_plans`, `management_plan_items`).
- `services/management_plans.py` holds the rules, reads and the KPI evaluation.
- The KPI catalogue lives in `management_metrics.py`.
- `api/management_plans.py` holds the routes: operational tier; each write commits once.
- Next.js server pages + one client editor.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic v2, pytest; Next.js App Router, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-14-mgmt-026-next-month-plan-design.md`

## Global Constraints

- IST calendar months. A month is written `YYYY-MM` on the wire and stored as its 1st day.
- Operational tier only (partner, super_admin). The revenue KPI is partner only (PN7).
- Audit kind `mgmt.plan`, field names only. Logs carry ids and field names, never item text.
- Migration `0159_management_plans` after `0158_social_proof`; `DEC-SCOPE-211`, API §12DY, RBAC §2.136.
- No new dependencies.

## Review Focus

1. A super admin must never see a revenue target or actual anywhere: plan, progress, counts, or a by-id PATCH/DELETE (PN7).
2. A KPI count must include only rows inside `[month start, next month start)` in IST. Data from the last IST day of the previous month must
   not leak in.
3. A closed plan refuses item writes and task creation with `409`, but can be reopened.
4. A double-clicked "Add item" or "Plan a month" must not create duplicates: the client guards with a ref, and the server's unique month
   returns `409`.
5. Changing an item's KPI to none must clear its target in the same PATCH. Otherwise the CHECK fails with a `500`, so the service must
   reject the PATCH as a `422`.

---

### Task 1: Model + migration
**Files:**
- Modify: `apps/api/app/models.py` (after `ManagementTask`).
- Create: `apps/api/alembic/versions/0159_management_plans.py`, `apps/api/tests/test_mgmt_026_migration.py`.

**Produces:**
- `ManagementPlan`, `ManagementPlanItem`.
- `PLAN_STATUSES = ("draft","active","closed")`, `PLAN_VERTICALS = ("abroad","it","school","recruitment","other")`, `PLAN_ITEM_CHECKS`.

- [ ] Write the migration test, modelled on `test_mgmt_028_migration.py`:
  - single head, chained after 0158;
  - the model columns match;
  - CHECKs reject a target without a KPI, and done on a KPI item;
  - the downgrade refuses while plans exist.
- [ ] Run it and watch it fail. Implement. Run it and watch it pass. Commit.

### Task 2: KPI catalogue
**Files:** Modify `apps/api/app/services/management_metrics.py`. Test in `tests/test_mgmt_026_plans.py`.

**Produces:**
- `PLAN_KPIS: dict[str, tuple[label, unit, definition]]`.
- `async def plan_actuals(db, keys: set[str], start: date, end: date) -> dict[str,int]` (the count KPIs, one SELECT).

- [ ] Tests: each KPI counts a row inside the month and ignores one created on the previous month's last IST day; AC2 (27 agencies
  against a target of 30 gives 90).
- [ ] Implement with scalar subqueries, using IST datetimes from `_ist_start`.

### Task 3: Service + routes
**Files:**
- Create: `services/management_plans.py`, `api/management_plans.py`.
- Modify: `schemas.py`, `main.py`, `services/management_audit.py` (verb `delete`).

**Tests** (`test_mgmt_026_plans.py`):
- the access matrix (partner, super_admin, accountant, trainer, anonymous);
- create, duplicate `409`, month window `422`;
- AC1: the October plan's 16 items;
- AC3: done toggles; done on a KPI item `422`;
- an unknown KPI `422`; a target without a KPI `422`; a KPI without a target `422`;
- revenue hidden from the super admin (`403` on create, `404` by id, absent from progress); revenue equals the P&L for a partner;
- closed `409`, then reopen;
- a target change writes a `mgmt.plan` update audit row with fields `["target"]`;
- a task from an item: `source=plan`, `source_id`, `task_count` 1;
- delete `204` with an audit row;
- `progress` state and achievement.

- [ ] RED, GREEN, refactor; commit.

### Task 4: Web lib + components + pages
**Files:**
- Create:
  - `lib/managementPlans.ts`;
  - `components/ManagementPlans.tsx`, `ManagementPlanForm.tsx`, `ManagementPlanProgress.tsx`, `ManagementPlanEditor.tsx`;
  - `app/management/plans/page.tsx`, `app/management/plans/[month]/page.tsx`;
  - tests `tests/lib/managementPlans.test.ts`, `tests/components/ManagementPlanProgress.test.tsx`,
    `tests/components/ManagementPlanEditor.test.tsx`.
- Modify: `lib/management.ts` (the entry href, `/management/plans`); `lib/management.ts` VERB_LABEL `delete: "removed"`.

- [ ] Vitest:
  - month label and percentage formatting;
  - the progress table rows and an empty state;
  - the editor adds an item (POST body), toggles done, and blocks a double submit.
- [ ] Implement; `tsc` and `eslint`; commit.

### Task 5: E2E + docs
- Playwright `tests/e2e/mgmt-026-plans.spec.ts`: a partner plans a month, adds a KPI item and a free-text item, toggles done, sees Target vs
  actual.
- Docs:
  - `DEC-SCOPE-211` in `PRODUCT_DECISION_REGISTER.md`;
  - API §12DY;
  - RBAC §2.136;
  - backlog status line;
  - a QA evidence file.
