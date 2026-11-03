# itc-017 — Accounts role, workspace and collection reports (design)

**Status:** builder's design under the owner's "proceed with the recommended answers" (backlog Q-01: all phases approved for build in
waves). Every call marked **Fn** is `NEEDS_CONFIRMATION`. Source: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-017 (PDF §2
Accounts/Finance, §8 Accounts dashboard, §11 Accounts workspace, §12 AC10; PDF classified `UNVERIFIED`).
Dependencies merged: itc-013 (`DEC-SCOPE-346`), itc-015 (`DEC-SCOPE-364`), itc-016 (`DEC-SCOPE-358`).

## Intent
Accounts staff need one place to answer "what came in, what is still owed, what is late, which receipts were issued, what was refunded or
adjusted" for IT enrolment fees, filtered by course, batch, date range and status, and exportable to a spreadsheet. The per-enrolment
writes (record a payment, fee plan / installments, credit notes, refunds, corrections) already exist on the IT student record (itc-013,
itc-015, itc-016); the workspace links to them rather than duplicating them.

## Non-goals
- No new write path: recording, refunds and corrections stay on the student record (itc-013/015) and the IT Admin Payments page.
- No change to the fee-account math (`fee_accounts.balance_for`), the ledger, the management IT revenue dashboard or mgmt-013.
- No Overseas fees, no university commission (the accountant never sees it — unchanged), no GST.

## Builder's calls (`NEEDS_CONFIRMATION`)
- **F1 — Q-17 role:** "Accounts" is the existing global `accountant` role. Migration seeds its default grants `payments.view`,
  `payments.add`, `payments.refund` (PDF §2: "record payments and refunds"); not `discounts.*` (itc-014's checker stays the IT Admin).
  A super admin can still remove them on the Permissions page. No new role.
- **F2 — Q-17 route:** one workspace component, two pages: `/it/admin/accounts` (IT Admin nav, "Accounts") and
  `/management/it-accounts` (management nav for the finance tier, "IT fee accounts"). Both are tagged with the `payments` resource, so the
  menu hides them without `payments.view`.
- **F3 — who:** a `payments.view` holder in IT or every division (`_in_it`: it_admin, accountant, super_admin). Anyone else 403
  ("You do not have access to IT accounts") — a counselor, a student, an Overseas admin.
- **F4 — what counts:** IT `enrollment_fee`/`enrollment` payment rows (`fee_accounts.FEE_REFERENCES`). A collection is a row in
  `paid | succeeded`, dated on the **IST day of `paid_at`** (falling back to its receipt's `issued_at`, then `updated_at`, for legacy
  rows). A `reversed` (corrected) payment is not a collection; its correction is. Refunds are not subtracted from collections; they are
  listed under Refunds & adjustments.
- **F5 — outstanding:** Σ positive balances of `active` enrolments (backlog Appendix B), each balance from `fee_accounts.balance_for`;
  an unbilled or fully paid enrolment is not listed. "Overdue amount" = owed installments due before today (IST, itc-016's rule).
- **F6 — reports and filters:**

  | Report | Rows | Date filter | Status filter | Sort |
  |---|---|---|---|---|
  | `collections` | one per IST day / month / course (`group`) with count and amount | paid day | `mode` | key asc |
  | `outstanding` | one per enrolment owing; + per-course summary and total | none (as of today) | `state`: `enrolled_pending_payment`, `partially_paid`, `overdue` | balance desc |
  | `overdue` | one per overdue installment, with days overdue and reminders sent | none (as of today) | — | due date asc |
  | `receipts` | one per receipt of an IT enrolment fee (a reversed payment's receipt is flagged) | issued day | `mode` | newest first |
  | `adjustments` | one per credit note, write-off, refund, reversal | created day | `kind` | newest first |

  Common: `program_id`, `batch_id` (unknown → 422 "Choose a course/batch from the list"; a batch outside the course → 422),
  `date_from`/`date_to` (IST days; default the current month to today; from after to → 422; more than 366 days → 422),
  `limit` 1–200 (default 50), `offset`. Each list answers `{items, total, limit, offset, totals, ...}` plus the course and batch choices.
- **F7 — export:** `GET …/{report}/export` returns the whole filtered list (up to 10,000 rows, else 422 "Narrow the filters") as CSV;
  every text cell goes through `_safe_cell` (formula injection guard, AC4). Each export is audited (`it.accounts.export`, report and
  filters, no amounts).
- **F8 — index:** `ix_payments_paid_at` on `payments(paid_at)` (backlog performance note).
- **F9 — student names:** listed (the accounts staff already see them on Payments); no emails or phone numbers.

## API (API_CONTRACT §12JM)
- `GET /api/v1/it/accounts/reports/{report}` — JSON as above; unknown report 404.
- `GET /api/v1/it/accounts/reports/{report}/export` — `text/csv`, `Content-Disposition: attachment; filename="it-<report>-<today>.csv"`.

## UI
A tab strip (links, `aria-current`) for the five reports; a GET filter form (course, batch, from, to, report's status filter; Apply / Clear)
so refresh, back and shared links keep the view; total tiles; a responsive `table-wrap` table; Previous/Next paging; "Download CSV"
(`ReportDownloadButton`, CSV mode). Empty: "Nothing matches these filters." Error: 422 text above the form; other failures a plain
"unavailable" panel. Each outstanding/overdue row links to the student record (`/it/admin/students/<id>/profile`) for IT Admin only.

## Acceptance (from the backlog)
1. Collections by day equal the sum of confirmed payments on that IST day (E: confirmed 23:30 UTC counts on the next IST day).
2. Outstanding equals the sum of balances (and matches each enrolment's fee account).
3. Filters work (course, batch, date range, status).
4. The export is injection-safe.
+ Accounts filters by course "Java" for October. − A counselor opens the workspace and gets 403.

## Plan (TDD, one slice each)
1. Migration `0248_accounts_grants` + `rbac.DEFAULT_GRANTS["accountant"]` + `Payment` index; migration test.
2. `services/it_accounts.py` + `api/it_accounts.py`: access, filters, collections (AC1, E), outstanding (AC2), overdue, receipts,
   adjustments, export (AC4) — `tests/test_itc_017_accounts.py` first.
3. Frontend: `lib/itAccounts.ts` (filters/URLs), `components/ItAccountsWorkspace.tsx`, two pages, nav entries; vitest.
4. Playwright e2e `itc-017-accounts.spec.ts`; docs (DEC-SCOPE-367, API §12JM, RBAC §2.267, backlog status, RTM).

## Regression risks
nehn-005 / nehn-021 grant tests (the accountant's default set changes), the management nav tests, sibling migration-head tests.
