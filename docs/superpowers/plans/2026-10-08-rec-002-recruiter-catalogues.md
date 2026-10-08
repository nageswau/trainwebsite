# rec-002 implementation plan

Spec: `docs/superpowers/specs/2026-10-08-rec-002-recruiter-catalogues-design.md`. TDD for every task: write the test, see it fail,
implement, see it pass. Lite backend runs in the api-test container. Web runs in the web-test container.

| # | Task | Tests first | Files |
|---|---|---|---|
| 1 | Models + migration 0101 (seven tables, idempotent seeds, guarded downgrade) | `test_rec_002_migration.py` | `models.py`, `alembic/versions/0101_rec_catalogues.py` |
| 2 | Schemas + `services/recruiter_catalogue.py` + `api/recruiter_catalogue.py` + main.py | `test_rec_002_catalogue.py`, `test_rec_002_campaigns.py` | `schemas.py`, services, api, `main.py` |
| 3 | Web lib + navigation entry | `navigation.recruiter.test.ts` | `lib/recruiterCatalogue.ts`, `lib/navigation.ts` |
| 4 | Web: catalogue shell + tabs + list panel + campaigns panel | `RecruiterCatalogueListPanel.test.tsx`, `RecruiterCampaignsPanel.test.tsx` | `app/recruiter/manager/catalogue/**`, components |
| 5 | e2e `rec-002-catalogue.spec.ts` | e2e | `tests/e2e` |
| 6 | Docs: DEC-SCOPE-117, API §12AJ, RBAC §2.43, backlog status, SCREEN_CATALOG, ROLE_NAVIGATION | — | `docs/**` |

## Phase 3 review notes (folded into the tasks)
- **API:**
  - Reuse the tel-002 helpers (`_parse`, `flush_unique`, `apply_changes`, `audit`, `active_filters`-style rule) instead of copying
    them.
  - An unknown kind or id is 404; validation is 422; a duplicate is 409; a wrong role is 403. Every refusal happens before any
    write.
  - Each route has one commit.
  - A PATCH locks the row `FOR UPDATE`. The campaign's lead source is locked `FOR SHARE`.
- **Security:**
  - There is no per-row scope, because the catalogue is global. The role checks happen at the top of every route.
  - Writers are limited to `placement_manager` and `super_admin`.
  - Audit metadata holds field names only.
  - React escapes the output.
  - CSRF uses the existing SameSite cookie with POST/PATCH only.
  - No new dependency.
- **Frontend:**
  - Reuse `PortalShell`, `sendJson`, `CreateJumpLink`, `useFocusAfterRender`, `toneClass`, the `formText`/`pageOffset`/`statusLabel`
    helpers, and `getPage`.
  - Labelled mobile cards (`.telecaller-list`).
  - Tab links carry `aria-current`.
