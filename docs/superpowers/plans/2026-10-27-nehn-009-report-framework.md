# nehn-009 — Report framework (plan)

Spec: `docs/superpowers/specs/2026-10-27-nehn-009-report-framework-design.md`. TDD per task (RED → GREEN → refactor); focused tests only.

## Tasks
1. **Catalogue + seed.** `rbac.CATALOGUE["reports.training"] = view, download`; `DEFAULT_GRANTS` it_admin/trainer; migration
   `0210_training_report_grants` (frozen SEED, insert-only, downgrade deletes grants + overrides). Tests: `test_nehn_009_migration.py`
   (chain, SEED == DEFAULT_GRANTS keys, round trip); update `test_nehn_005_permissions` catalogue set.
2. **Registry + filters.** `services/reports/{__init__,registry,training}.py`: `Column`, `Report`, `Filters`, `parse_filters`,
   `register`, `REPORTS`; pilot `enrollments`. Unit tests on parsing (every 422 rule, empties ignored, unknown/undeclared → 422).
3. **Router.** `api/reports.py` mounted in `main.py`: catalogue, JSON read (paged, latest, field policy, no-store), CSV/xlsx (lock,
   throttle, cap, audit, commit, fail-closed). Tests `test_nehn_009_reports.py`: AC1-AC6.
4. **Web.** `lib/reports.ts`, `components/ReportLibraryPage.tsx`, `components/ReportView.tsx`, three pages, nav entries. vitest for
   the URL helpers and the view (states, filters, paging, download buttons); update pinned nav/seed lists in tests.
5. **e2e.** `apps/web/tests/e2e/nehn-009-report-library.spec.ts`: it_admin library → report → filter → page → Excel download;
   trainer sees own rows only; 422 message kept with the form; phone layout without page scroll.
6. **Docs.** DEC-SCOPE-303 (decision register), API §12HA, RBAC §2.214, backlog status, FEEDBACK_TRACKER row, user manual page.

## Phase 3 review notes (applied)
**API.** GET-only, plain-string query params validated after authorization (the house order: 404 → 403 → 422). The 422 detail is a
sentence naming the field (as telecaller reports). Paging metadata in the body (`total`, `page`, `page_size`). Exports are refused over
the cap, never truncated. Same `{columns, items, totals}` payload for JSON and files, so `export_response` and `field_policy.strip`
are reused untouched. Export transaction: lock the user row → throttle → count → rows → render → audit → commit.
**Frontend.** Reuse `PortalShell`, `.action-card`, `.analytics-form`, `.table compact stack` (`data-label` cells for phones),
`.table-scroll` region, `SpreadsheetButtons`, `accessDenied`/`accessUnavailable`, `visually-hidden` caption. GET form with
`autoComplete="off"` and a `key` from the address (Chrome restores stale selects on Back, upc-031). Pager links carry the filters;
`aria-current` on the library list; the error is `.form-error role=alert` above the kept form; empty state `role=status`.
**Security.** Row scope inside every query **and** inside `options` (a trainer's pickers list only their own batches/courses and
themself, so no other trainer's names leak). `student` uses bound `ilike` with autoescape (no wildcard injection, no SQL injection).
CSV/xlsx formula injection handled by the shared writers. Filenames come from the registry id + server date only. Throttle 30/10 min per
user; audit row per download with filter values (accountability), logs carry filter names only. No new secrets, no CSRF surface (GET,
the only side effect is the audit row). Deny by default for roles outside a report's scope.
