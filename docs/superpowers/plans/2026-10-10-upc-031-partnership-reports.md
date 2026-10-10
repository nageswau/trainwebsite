# upc-031 Partnership Reports Implementation Plan

> **For agentic workers:** executed natively in the build session (superpowers:executing-plans). Steps use checkbox syntax.

**Goal:** Five partnership reports (pipeline, expected, performance, agreements, targets) as on-screen tables + CSV.
**Architecture:** One read route `GET /partnership/reports/{kind}(.csv)`; `services/partnership_reports.py` builds `{columns, items,
totals}` from the existing metric code; tel-024's `to_csv` writes the file. One server page `/partnership/reports`.
**Tech Stack:** FastAPI + SQLAlchemy async, pytest (in the api container); Next.js server components, vitest, Playwright.
**Spec:** `docs/superpowers/specs/2026-10-10-upc-031-partnership-reports-design.md`

## Global Constraints
- Readers: partnership_manager (with profile), partnership_head, super_admin; others 403. Order role → kind → inputs.
- Screen rows ≤ 500 (`truncated`), CSV ≤ 5,000 rows else 422. No migration. No new dependency.
- Commission columns only when `can_see_commission(user)`.
- Every CSV text cell through `_safe_cell` (via `to_csv`); export audited `partnership_report.export`, committed before the response.

## Review Focus
- A performance period that is impossible (`2025-02-30`) or reversed → 422 naming the field (test in Task 1).
- A university name starting with `=` → CSV cell prefixed with `'` (Task 2).
- An empty period → 200 with no items and zero totals (Task 1).
- `?report=nonsense` on the page → falls back to Pipeline, no crash (Task 3).
- A month like `2025-13` for targets → 422 (Task 1).

---

### Task 1: Report service + read route (TDD)
**Files:** Create `apps/api/app/services/partnership_reports.py`, `apps/api/app/api/partnership_reports.py`; modify
`apps/api/app/api/partnership_performance.py` (extract `ranked(db, user, first, last)` → `(rows, totals)` without behaviour change),
`apps/api/app/main.py` (register router); Test `apps/api/tests/test_upc_031_reports.py`.
**Produces:** `REPORTS: dict[str, str]` (kind → title), `async build(db, user, kind, raw: dict[str, str | None]) -> dict` raising
`ReportInputError(field, message)`; payload `{kind, title, as_of, filters, columns[{key,label,numeric}], items, totals, total, truncated, notes}`.
- [ ] RED: role matrix, 404, 422s, reconciliation per report, manager scope, empty period, commission strip → run, see failures.
- [ ] GREEN: implement builders and the route; run the file + `test_upc_018*`, `test_upc_022*`, `test_upc_023*` (performance refactor).
- [ ] Commit.

### Task 2: CSV export (TDD)
**Files:** `api/partnership_reports.py` (`/{kind}.csv`, before `/{kind}`); same test file.
- [ ] RED: BOM + header labels, Total row last, `=` cell guarded, audit row, attachment filename, cap → 422 (monkeypatch cap to 1).
- [ ] GREEN; run; commit.

### Task 3: Web lib + view + page (TDD)
**Files:** Create `apps/web/lib/partnershipReports.ts`, `apps/web/components/PartnershipReportView.tsx`,
`apps/web/app/partnership/reports/page.tsx`; tests `apps/web/tests/lib/partnershipReports.test.ts`,
`apps/web/tests/components/PartnershipReportView.test.tsx`.
**Produces:** `REPORT_TABS`, `reportKind(raw)`, `reportParams(search)`, `reportUrl(kind, params)`, `csvUrl(kind, params)`, `tabHref(kind, params)`.
- [ ] RED: lib helpers (unknown kind → pipeline, only the kind's filters are sent), view (columns, numeric cells, tfoot, empty status,
  error alert, truncated note, filters per kind, CSV button only with rows).
- [ ] GREEN; `npx vitest run` on those files + `npx tsc --noEmit`; commit.

### Task 4: Navigation
**Files:** `apps/web/lib/navigation.ts` (Reports live; head nav; super-admin "Partnership Reports"); tests
`tests/lib/navigation.partnership.test.ts`, `tests/components/PartnershipTeamTable.test.tsx` (18 of 19 live).
- [ ] RED (update expectations) → GREEN → commit.

### Task 5: E2E + docs
**Files:** `apps/web/tests/e2e/upc-031-partnership-reports.spec.ts`; docs: DEC-SCOPE (register), API §12 addendum, RBAC §2 addendum,
SCREEN_CATALOG addendum, backlog status line, QA evidence.
- [ ] Spec runs green against the isolated stack; commit docs.
