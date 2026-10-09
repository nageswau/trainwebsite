# rec-023 — Joining management: implementation plan

The design is in `docs/superpowers/specs/2026-10-09-rec-023-joining-management-design.md`. Every task follows TDD: a failing test first, then the code, then the focused tests again.

1. **Model + migration 0140.** Write `test_rec_023_migration` first: the CHECKs equal the model's, the backfill and the guarded downgrade. Then add the `JobOffer` columns, the event catalogue and `0140_joining_management`.
2. **Accept starts the joining.** Tests: recruiter Accepted → `pending`, and legacy accepted → `joined`. Then add the hook in `offers._apply_status`.
3. **`PUT …/joining`.** Tests cover:
   - AC1: actual date + proof/confirmation;
   - AC2: reason;
   - JN6: dates;
   - not Accepted 409, final 409, unchanged = no write;
   - roles 403/404;
   - JN7: application Joined, company `candidate_joined`, vacancies → Closed;
   - JN8: Withdrawn.

   Then write `services/joinings.py` and the route.
4. **Proof upload/download.** Tests for the type 415, Did Not Join 409, the audit, and the reader download. Then the routes; the storage helpers take a prefix.
5. **JN9 guard.** A test that rec-017's status route to `joined` with an offer is 409, and without one is unchanged.
6. **List `GET /recruiter/joinings`.** Tests for the views, counts, overdue flag and scope.
7. **Web.** Write `lib/recruiterOffers.ts` (the joining types and the history text) and a vitest for the Joining section and the joinings panel. Then the components, the `/recruiter/joinings` page and the nav (with its test).
8. **E2E.** Write `tests/e2e/rec-023-joining.spec.ts`: accept → joining due → Joined with proof → the requirement closes; Did Not Join; mobile.
9. **Docs.** DEC-SCOPE-158, API §12BZ, RBAC §2.84, SCREEN_CATALOG and the backlog status line.
10. **Lite verification.** Run:
    - the rec-022, rec-017 and rec-007 tests, `test_rec_017_legacy` and `test_bdm_016`/`021` metrics;
    - vitest, tsc, eslint and the next build;
    - the e2e for rec-023 and rec-022.
