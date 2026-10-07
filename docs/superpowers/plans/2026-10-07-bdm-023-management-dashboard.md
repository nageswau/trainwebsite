# bdm-023 — Management dashboard: implementation plan

Spec: `docs/superpowers/specs/2026-10-07-bdm-023-management-dashboard-design.md`. TDD for every task (red → green → refactor).
Focused tests only; the full suites are the dedicated regression session's.

## Task 1 — API: `GET /bdm/manager/dashboard`
1. Red: `apps/api/tests/test_bdm_023_dashboard.py` — roles and the manager filter (R1, R2).
2. Green: `BdmManagerDashboard*` schemas in `app/schemas.py`; `app/api/bdm_manager_dashboard.py`; router in `app/main.py`.
3. Red → green: tiles T-M01…T-M08 with near-miss rows; `bdm_metrics._owned` so M-06 / M-11 take a team sub-select.
4. Red → green: alerts AL-1…AL-7, ordering, the 10-item cap, team isolation, resolution removes an alert.
5. Statement-count test (1 vs many rows).

## Task 2 — Web lib + component
1. Red: `tests/lib/bdmManagerDashboard.test.ts` (guard, hrefs, tone text); `tests/components/BdmManagerDashboard.test.tsx`.
2. Green: `lib/bdmManagerDashboard.ts`, `components/BdmManagerDashboard.tsx`.

## Task 3 — Page + nav
1. Red: page tests (manager, super_admin with filter, inline error, no team); navigation test for `SUPER_ADMIN_NAV`.
2. Green: `app/bdm/manager/dashboard/page.tsx`, `loading.tsx`, `lib/navigation.ts`.

## Task 4 — E2E
`tests/e2e/bdm-023-manager-dashboard.spec.ts`: seeded manager + BDM; tiles visible; an AL-1 item links to its appointment; BDM
gets the access card; phone width without horizontal overflow.

## Task 5 — Docs
API contract §12AB, RBAC §2.34, `DEC-SCOPE-108`, ROLE_NAVIGATION line, backlog status, RTM row, browser QA log
`docs/quality/BDM-023_BROWSER_QA_2026-10-07.md`.

## Phase 3 review notes (API / frontend / security)
- HTTP: `GET` only, `200`/`403`/`404`/`422`; `manager_user_id: UUID | None` so FastAPI rejects a malformed id with `422`.
- No transaction concerns (read-only); one DB clock read per request so all rules agree (R4).
- IDOR: a manager cannot pass another manager's id (R2); items expose only code, organization name, BDM name, time.
- XSS: React escapes text; no `dangerouslySetInnerHTML`. CSRF: GET only. SQLi: SQLAlchemy expressions only.
- Accessibility: every tone has a text word; sections have headings and `aria-labelledby`; links have visible text; the manager
  filter has a `<label>`. Responsive: `kpi-grid` and wrapping rows; checked at 375 / 768 / 1280 px.
- Rate limiting: as every authenticated read (no new limiter). No sensitive logging (no log line at all).
