# mgmt-002 — Management audit trail — implementation plan

Spec: `docs/superpowers/specs/2026-10-12-mgmt-002-management-audit-trail-design.md`. TDD for each task: test first (RED), minimum code
(GREEN), refactor. Focused tests only; full regression is deferred to its own session.

| # | Task | Test first | Files |
|---|---|---|---|
| 1 | `management_audit.record`: kind/verb catalogue, actor, field names, MA3 value guard, MA4 count; adds the row to the session, no commit | `test_mgmt_002_activity.py::test_record_*` | `services/management_audit.py` |
| 2 | `activity(db, user, …)`: MA5 tier filter, MA6 filters + paging, MA7 shape (kinds, actors) | `test_activity_*` (service-level via route) | `services/management_audit.py`, `schemas.py` |
| 3 | `GET /management/activity`: 401/403/422, query validation | `test_route_*` | `api/management.py` |
| 4 | MA8: `/admin/audit` + export leave out finance and partner-only `mgmt.*` rows | `test_admin_audit_hides_*` | `api/admin.py` |
| 5 | Seed demo entries (MA12): the seven §2 kinds by the two demo partners and the accountant, once | run seed twice in the stack | `seed.py` |
| 6 | Web lib: types, `activityUrl(params)`, `activityHref`, nav entry for partner/accountant | `management.test.ts` | `lib/management.ts` |
| 7 | Web page `/management/activity`: filter form (GET), rows "<verb> <kind> · fields · by X · date", empty/error/403 states, paging links; Command Center link | `ManagementActivity.test.tsx` | `components/ManagementActivity.tsx`, `app/management/activity/page.tsx`, `app/management/page.tsx` |
| 8 | Playwright: partner filters, accountant lacks partner-only kinds, super_admin reaches it from the Command Center | `mgmt-002-activity.spec.ts` | `tests/e2e/` |
| 9 | Docs: DEC-SCOPE-187, API §12DA, RBAC §2.113, backlog status, QA report | — | `docs/` |

Regression watch: `/admin/audit` (Security logs page) and export tests; mgmt-001 tests; `navigation`/`management` web tests.
