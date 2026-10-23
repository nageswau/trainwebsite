# ccrm-023 application offers — implementation plan

Spec: `docs/superpowers/specs/2026-10-23-ccrm-023-application-offers-design.md`. TDD per task: write the test, watch it fail, implement,
watch it pass. Lite tests only; the full suite is run by the owner.

| # | Task | Tests first |
| --- | --- | --- |
| 1 | Model `ApplicationOffer` + constants; widen `ck_overseas_applications_offer_type`; migration `0171_application_offers` (after 0170, create, backfill, downgrade) | `tests/test_ccrm_023_migration.py`: single head; backfill row; CHECK widened; constants repeated |
| 2 | Schemas `ApplicationOfferCreate`, `ApplicationOfferClose` | inside the API tests (422 cases) |
| 3 | `services/application_offers.py` (record / apply_stage / close / views) + `agent_notifications.offer_changed` | exercised through the routes |
| 4 | `api/application_offers.py`: GET, offer-letters upload, POST, withdraw; register the router | `tests/test_ccrm_023_offers.py`: AC1–AC7, AC9, authz matrix, idempotent retry, document mismatch, closed apps |
| 5 | Agency PUT/PATCH write rows + sub-status + counselor notice | the same file (AC4) and the existing `test_agn_010_*.py` stay green |
| 6 | nehn-001 portal predicates + student offer columns | `tests/test_ccrm_023_offers.py::test_nehn_001_*` |
| 7 | Web: `lib/applicationOffers.ts`, `ApplicationOffersPanel.tsx`, counselor card toggle, agency type labels | `tests/components/ApplicationOffersPanel.test.tsx`; the AgentApplicationOffer tests stay green |
| 8 | e2e `tests/e2e/ccrm-023-application-offers.spec.ts` (counselor records with an uploaded letter, supersedes, withdraws; student sees it) | |
| 9 | Docs: DEC-SCOPE-245, API §12EX, RBAC §2.160, RTM row, backlog status | |

## Phase 3 review notes (applied to the spec)

- **API:** POST returns 201, or 200 on an identical retry; withdraw is a POST action on a sub-resource (state transition, not DELETE);
  every body has `extra=forbid`; amounts are Decimal with 2 places; currency is `^[A-Z]{3}$`, upper-cased.
- **Security:** every route goes through `_assigned_application` (IDOR) and then `_recheck_counselor_scope` on the locked row. The
  document id is checked against the application and type (no cross-application letter). The upload sniffs bytes (AGN-009 G8) and the
  key is server-generated (G7). Views never return `file_url`; downloads go through the existing audited route. Audit metadata holds
  ids, fields and statuses only, never reasons or amounts.
- **Concurrency:** the application `FOR UPDATE` lock serialises every offer write; the partial unique index backs it.
- **Frontend:** reuse `sendJson`, `form`/`field`/`btn` classes and the card toggle pattern. Labels on every input, `role="status"`
  messages, a loading/empty/error state, an in-flight ref, and wrapping layout for mobile.
