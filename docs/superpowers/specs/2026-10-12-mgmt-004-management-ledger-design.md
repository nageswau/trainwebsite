# mgmt-004 — Management ledger: categories, manual income/expense, approval, tags — design

- **Feature:** `mgmt-004` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-004). Depends on mgmt-001 (PR #243) and mgmt-002 (PR #245),
  both merged on `main@13e9e360`.
- **Evidence:** `EVID-017` §8 (one centralised expense module; 8 fixed + 9 variable categories), §22 (income heads), §2 ("who approved
  an expense"); Management M4, M5, M7, M13 (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`); mgmt-002 audit helper (`DEC-SCOPE-187`).
- **Decision:** one new DEC-SCOPE (number taken at merge). ML1–ML16 below answer Q-04 (ledger part), Q-05, Q-06 (ledger part), Q-11
  and Q-33 (interim) with **recommended defaults, `UNVERIFIED`**, on the owner's instruction to proceed with recommended answers.
  Q-23 (school tag vs school columns) stays `NEEDS_CONFIRMATION` for mgmt-022. Shared-cost allocation (Q-04 second half) stays with mgmt-009.

## 1. Intent

The accountant records manual income and expenses; a partner approves them; only approved entries count in the money figures. Every
change is audited (mgmt-002) and kept as entry history. Approved entries are never edited: a correction is a reversing entry.
mgmt-005 later adds the automatic lines (payments, commissions, trips) on read; mgmt-010/013 build the dashboards on `services/ledger.py`.

## 2. Decisions (ML1–ML16)

| # | Point | Answer |
|---|---|---|
| ML1 | Categories (Q-04) | A managed list `ledger_categories` (kind `income`/`expense`; `nature` `fixed`/`variable` for expenses, none for income). Seeded by the migration: the 17 §8 expense categories (8 fixed, 9 variable) and the 5 §22 income heads (Abroad education, IT training, Recruitment, School projects, Other). The §22 expense heads (Rent, Technology, Operations, …) are dashboard groupings for mgmt-010/013, not extra categories |
| ML2 | Managing categories | Partner and accountant add, rename and deactivate/reactivate. Name 2–80 characters, unique per kind ignoring case (`409`). Kind and nature are fixed after creation. No delete |
| ML3 | Deactivated category | Existing entries keep it and still count. It can't be chosen for a new entry or a change of category (`422`); an entry already on it may be edited otherwise |
| ML4 | Entry fields | `entry_date` (IST day, not in the future, not before 2000-01-01), `kind`, `category` (same kind), `amount`, `description` (2–500), `vertical` ∈ abroad / it / recruitment / school / other / shared (required) |
| ML5 | Currency (Q-06) | **INR only.** `amount` > 0, at most 2 decimals, ≤ 99,99,99,99,999.99 (`Numeric(14,2)`). A negative or zero amount → `422` |
| ML6 | Tags (M7, Q-11) | Optional: marketing `channel` (one of the 13 `TEL_SOURCES`; **expenses only**), `program_id` (course) and `batch_id` (must belong to the program; a batch alone sets its program). School tag deferred (Q-23) |
| ML7 | Statuses | `draft` → `submitted` → `approved` / `rejected`. Create makes a draft; submit is a separate action (the form offers "Save and submit"). Editing a rejected entry returns it to draft |
| ML8 | Who writes | Finance tier (partner, accountant) creates, edits (draft/rejected only), submits, uploads the receipt and reverses. Partners can also edit (M5) |
| ML9 | Approval (Q-05) | **Every** manual entry (income and expense) needs **one** partner's approval; no threshold. A partner can't decide an entry they created (`403`), so a partner's own entry waits for another partner. Reject needs a reason (2–500). Only `submitted` entries are decided (`409` otherwise) |
| ML10 | Figures | Only `approved` entries count (AC1/AC2). A reversal counts as the negative of its amount. The list returns `totals {income, expense, net}` of the approved entries matching the other filters |
| ML11 | Reversal | `POST /{id}/reverse {reason}` on an approved, non-reversal entry creates a **submitted** reversing entry dated today (IST), with the original's kind, category, vertical, tags and amount and `reversal_of_id` set. It needs a partner's approval like any entry. One live reversal per entry (partial unique index, rejected reversals excluded → `409`). A reversal can't itself be reversed |
| ML12 | Immutability | `approved`, `submitted` entries can't be edited or have their receipt replaced (`409`). No delete route |
| ML13 | Receipt | One optional attachment per entry: PDF/JPEG/PNG through `read_upload` (type by bytes, size cap, metadata stripped), stored under `ledger-receipts/`, replaceable while editable. Download for the finance tier; the download is audited |
| ML14 | History + audit | Every write adds a `ledger_entry_events` row (event, from/to status, changed fields, reason, actor, time) and a `management_audit.record` row (kind `mgmt.ledger` / `mgmt.ledger_category`; values for amount/status, per MA3). New verbs: `submit`, `reject`, `reverse` |
| ML15 | List | Filters `month` (YYYY-MM, IST), `kind`, `category`, `vertical`, `status`; `limit` 1–100 (25), `offset` ≤ 10 000; newest date first. The approval queue is the list with `status=submitted` |
| ML16 | Access (M13) | Every route: finance tier only. `super_admin` and every other role `403`. Approve/reject: partner only (an accountant → `403`) |

## 3. Data (migration `0150_management_ledger`)

- `ledger_categories`: id, kind, nature, name, active, created_by, updated_by, timestamps. Unique index `(kind, lower(name))`.
- `ledger_entries`: id, entry_date, kind, category_id → categories, amount `Numeric(14,2)` CHECK > 0, description, vertical, channel,
  program_id, batch_id, status, reversal_of_id → entries, receipt key/content type/name, created_by, updated_by, submitted_at,
  decided_by, decided_at, rejection_reason, timestamps. CHECKs on kind, vertical, status, channel-only-on-expense. Indexes
  `(entry_date)`, `(category_id, entry_date)`, `(vertical, entry_date)`, `(status)`; partial unique `reversal_of_id WHERE status <> 'rejected'`.
- `ledger_entry_events`: id, entry_id, actor, event, from_status, to_status, fields (JSON), reason, receipt key (replaced), created_at.

## 4. Components

- `services/ledger.py` (owner): rules, `totals`, list query, event + audit writes, store/discard of receipts. Frozen after mgmt-005.
- `api/management_ledger.py`: `GET/POST /management/ledger`, `GET/PATCH /management/ledger/{id}`, `POST …/{id}/submit|approve|reject|reverse`,
  `PUT|GET …/{id}/receipt`, `GET /management/ledger/options`, `GET/POST /management/ledger/categories`, `PATCH …/categories/{id}`.
  Every write locks the entry row (`FOR UPDATE`), checks status after the lock, writes event + audit, commits once.
- `services/management_audit.py`: kind `mgmt.ledger_category` (finance), verbs `submit`, `reject`, `reverse`.
- Web: `lib/managementLedger.ts` (types, filters, URLs, labels); pages `/management/ledger` (list, filters, totals, queue link),
  `/management/ledger/new`, `/management/ledger/[id]` (detail, history, actions), `/management/ledger/[id]/edit`,
  `/management/ledger/categories`; components `LedgerEntryForm`, `LedgerEntryActions`, `LedgerCategories`. The Command Center's
  "Ledger" entry gets its `href`.

## 5. Error handling

`401` signed out; `403` no finance tier / accountant approving / own entry; `404` unknown entry or category; `409` wrong status,
duplicate category name, second reversal; `413/415/422` receipt; `422` validation (field-located messages). Pages show the access card
on 401/403, the server message on 4xx actions, and "The ledger is unavailable right now" otherwise.

## 6. Testing

- Backend `tests/test_mgmt_004_ledger.py`: AC1 (accountant records rent → partner approves → in expense totals), AC2 (draft/submitted/
  rejected excluded), AC3 (super_admin 403 on every route), negative amount 422, accountant approve 403, own-entry 403, reject reason,
  status machine 409s, edit after rejection → draft, reversal (+ totals net to zero, one live reversal, no reversal of a reversal),
  deactivated category, channel on income 422, batch/program mismatch 422, category CRUD + duplicates, receipt upload/download + types,
  events + audit rows, filters/paging/totals.
- Web vitest: `managementLedger.test.ts` (filters, URLs), `LedgerEntryForm.test.tsx`, `LedgerEntryActions.test.tsx`, `LedgerCategories.test.tsx`.
- Playwright `mgmt-004-ledger.spec.ts`: accountant records Office rent ₹1,20,000 (shared) and submits; partner approves; expense total
  includes it; super_admin is refused.
