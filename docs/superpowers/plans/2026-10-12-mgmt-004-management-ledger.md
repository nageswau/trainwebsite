# mgmt-004 — Management ledger — implementation plan

Spec: `docs/superpowers/specs/2026-10-12-mgmt-004-management-ledger-design.md`. TDD for each task: test first (RED), minimum code
(GREEN), refactor. Focused tests only; full regression is deferred to its own session.

| # | Task | Test first | Files |
|---|---|---|---|
| 1 | Models + migration `0150`: three tables, CHECKs, indexes, ML1 seed (17 expense + 5 income categories) | `test_migration_seeds_categories` | `models.py`, `alembic/versions/0150_*.py` |
| 2 | Audit catalogue: kind `mgmt.ledger_category`, verbs `submit`/`reject`/`reverse` | `test_audit_catalogue_*` | `services/management_audit.py` |
| 3 | Categories: list (all, with active flag), create (ML2 name rules, 409 duplicate), rename / (de)activate; finance tier only | `test_category_*` | `services/ledger.py`, `api/management_ledger.py`, `schemas.py` |
| 4 | Entries create/read/edit: ML4–ML6 validation, ML3 inactive category, ML7 edit-of-rejected → draft, ML12 locked statuses; event + audit rows | `test_entry_*` | same |
| 5 | Submit / approve / reject: ML9 (partner only, not own entry, reason), 409 status machine, row lock | `test_submit_*`, `test_approve_*`, `test_reject_*` | same |
| 6 | List + totals: ML10, ML15 filters, paging; AC1, AC2 | `test_list_*`, `test_ac1_*`, `test_ac2_*` | same |
| 7 | Reversal: ML11 (submitted, today IST, one live reversal, no reversal of a reversal), totals net to zero | `test_reverse_*` | same |
| 8 | Receipt upload/download: ML13 (`read_upload`, store/discard, editable only, audited download) | `test_receipt_*` | same |
| 9 | Options endpoint (categories, channels, programs + batches, verticals) and AC3 sweep: super_admin and other roles 403 on every route | `test_ac3_*` | same |
| 10 | Web lib `managementLedger.ts`: types, filters from search params, list URL/href, labels, INR formatting; Command Center "Ledger" href | `managementLedger.test.ts`, `management.test.ts` | `lib/` |
| 11 | Web list page (filters GET form, totals, table, paging, queue link, empty/error/403) | `ManagementLedger.test.tsx` | `app/management/ledger/page.tsx`, `components/ManagementLedger.tsx` |
| 12 | Entry form (create/edit, save draft / save and submit, receipt, field errors) + new/edit pages | `LedgerEntryForm.test.tsx` | `components/LedgerEntryForm.tsx`, pages |
| 13 | Detail page + actions (submit, approve, reject with reason, reverse, receipt link, history) | `LedgerEntryActions.test.tsx` | `components/LedgerEntryActions.tsx`, `app/management/ledger/[id]/page.tsx` |
| 14 | Categories page (add, rename, deactivate/reactivate) | `LedgerCategories.test.tsx` | `components/LedgerCategories.tsx`, page |
| 15 | Playwright: accountant rent → submit → partner approves → total; super_admin refused | `mgmt-004-ledger.spec.ts` | `tests/e2e/` |
| 16 | Docs: DEC-SCOPE, API §, RBAC §, backlog status, QA report (numbers taken after merging main) | — | `docs/` |

Regression watch: mgmt-001/002/003 tests (`test_mgmt_00*.py`, `management.test.ts`, `ManagementCommandCenter.test.tsx`, nav tests);
`models.py`/`schemas.py`/`main.py` append conflicts; alembic head chain.

## Phase 3 review notes (applied above)

- **API:** nouns + action sub-resources (`/submit`, `/approve`, `/reject`, `/reverse`) like bdm-010 trips; `201` on create; `PATCH`
  partial with `exclude_unset`; field-located `422` (`field_validator`, not `model_validator`); `409` for state conflicts; one commit per
  write after the row lock (`FOR UPDATE`) so two partners approving at once serialise and the second gets `409`.
- **Frontend:** reuse `PortalShell`, `accessUnavailable`, `portal-title`, `table-wrap`, `form-error[role=alert]`, `sendJson`/`sendRequest`;
  GET filter form keyed on its href with `autoComplete="off"`; `noValidate` forms with own messages; buttons disabled while sending
  (duplicate submit); `router.refresh()` after each action; status pills reuse the milestone-table nowrap style; INR via `Intl.NumberFormat("en-IN")`.
- **Security:** finance tier checked first on every route (super_admin 403 — M13); approve/reject partner-only + separation of duties;
  receipt type decided by bytes, server-generated keys, download name built server-side with `nosniff` headers; logs carry ids and
  statuses only; amounts and descriptions are validated server-side; no raw SQL; audit rows commit with the write.
