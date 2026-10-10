# upc-029 Global partnership dashboard Implementation Plan

> **For agentic workers:** executed natively (superpowers:executing-plans) in the upc-029 session. Steps use checkbox syntax.

**Goal:** the §31 management dashboard — three columns with their sub-views, the Management §19 pipeline, the funnel totals and the
commission totals (GD1–GD17).
**Architecture:** one pure fold (`global_figures`) plus two small reads in `services/partnership_metrics.py`; a read route in a new
`api/partnership_global_dashboard.py` that reuses upc-018's period / funnel / commission helpers; a server-rendered Next page under
`/partnership/head/`. No migration.
**Tech Stack:** FastAPI, SQLAlchemy async, Next.js (app router), vitest, Playwright.
**Spec:** `docs/superpowers/specs/2026-10-10-upc-029-global-partnership-dashboard-design.md`

## Global Constraints
- Scope = `scope_filter(user, team)`; groups = `partnership_stages.GROUPS`; not lost; `University.active`.
- Readers: partnership_head, super_admin only (manager 403).
- Funnel / commission for the period exactly as `/partnership/performance` (same helpers, no copies).
- Fixed statement count whatever the data size.

## Review Focus
- Column counts == upc-022 overview D2–D4; Σ pipeline + lost == D1.
- Expected buckets add up to the In Progress count (undated, overdue, last day of the month / next month).
- Next action = earliest-due **open** task; done / cancelled ignored; ties by due date then name.
- Target with two `course_levels` counts in both; empty list → "not stated".
- A lost university appears in no column and in `lost` only.

---

### Task 1: Fold + reads + GET /partnership/global-dashboard
**Files:** `app/services/partnership_metrics.py`, `app/api/partnership_global_dashboard.py`, `app/api/partnership_performance.py`
(export helpers only if needed), `app/main.py`, `app/schemas.py`, `tests/test_upc_029_global_dashboard.py`
- [ ] RED: roles (head/super 200, manager/counselor/overseas_admin 403, 401); scope vs another head; every sub-view on a fixture;
  reconciliation with `/partnership/dashboard` and `/partnership/performance`; 422 period; statement count.
- [ ] GREEN: implement; RED → GREEN verified in the api container.

### Task 2: Web lib + page + nav
**Files:** `lib/partnershipGlobal.ts`, `components/PartnershipGlobalColumns.tsx`, `app/partnership/head/global-dashboard/page.tsx`,
`lib/navigation.ts`, `app/globals.css` (column grid), tests `tests/components/PartnershipGlobalDashboard.test.tsx`,
`tests/lib/navigation.partnership.test.ts` (+ super_admin nav test if exact).
- [ ] RED vitest → GREEN; tsc + eslint on touched files.

### Task 3: E2E + docs
**Files:** `tests/e2e/upc-029-global-dashboard.spec.ts`; DEC-SCOPE, API §, RBAC §, backlog status, screen catalog.
