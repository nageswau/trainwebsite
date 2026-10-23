# ccrm-015 — Application exception outcomes (plan)

Spec: `docs/superpowers/specs/2026-10-23-ccrm-015-application-outcomes-design.md`. TDD per task; focused tests only.

1. **Model + migration** — `OverseasApplication.outcome` + CHECK, `ApplicationOutcome` model; `0170_application_outcomes` (merge of
   both 0169 heads, backfill withdrawn). Test: `tests/test_ccrm_015_migration.py` (columns, CHECK, backfill, single head).
2. **Rules module** — `app/application_outcome.py` (values, terminal set, labels) and `app/services/application_outcomes.py`
   (`refuse_closed`, `refuse_on_hold`, `open_clause`, `record`, `reopen`, views). Schemas `ApplicationOutcomeSet`, `ApplicationOutcomeReopen`.
3. **Routes** — `POST …/outcome`, `POST …/outcome/reopen` in `api/workflows.py`; guards in PATCH, `/advance`, `/sub-status`, assign,
   agency visa; agency route withdraw records the outcome + `requested_by`; duplicate checks use `open_clause`. Test:
   `tests/test_ccrm_015_outcomes.py` (AC 9 A/B/C, on-hold 422, terminal 409, reopen admin-only, re-apply, agency withdraw, notices, reads).
4. **Reads** — `GET …/status`, agent `detail` (`outcome`, `read_only_reason`), portal rows (counselor/admin/student).
5. **Web** — `lib/applicationOutcome.ts`, `ApplicationOutcomeForm.tsx`, counselor card, admin reopen column, agent detail block +
   withdraw "requested by", student column. Vitest for the form and lib.
6. **Docs** — DEC-SCOPE-244, API §12EW, RBAC §2.159, DATA_MODEL, RTM, backlog status, PRD open item closed.
7. **E2E** — `tests/e2e/ccrm-015-application-outcomes.spec.ts`.
