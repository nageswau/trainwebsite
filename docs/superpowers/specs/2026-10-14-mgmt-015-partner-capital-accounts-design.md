# mgmt-015 — Partner capital accounts — design

- **Feature:** `mgmt-015` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-015). Depends on mgmt-014 (merged, PR #247; ordering only) and
  mgmt-009 (merged, PR #264; net profit).
- **Evidence:** `EVID-017` §24 (lines 971–995, `DERIVED_BLUEPRINT`): per partner — capital invested, additional investment, withdrawals,
  share %, profit share, returns, outstanding contribution, capital balance; "permission-controlled". Management M8 and M13
  (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`): partners record capital transactions and share %, the balance is computed, profit share =
  share % × net profit **as an indicative figure only** (no automatic distribution), outstanding contribution = commitment − invested,
  every entry audited, partner-only.
- **Decision:** a new DEC-SCOPE (number taken at merge time). Answers CP1–CP15 below are **recommended defaults, `UNVERIFIED`**, taken on
  the owner's instruction to proceed with recommended answers. Q-17 (commitment amounts, share % change history, how distributions are
  recorded) is answered by CP3, CP5 and CP2 as interim defaults.

## 1. Intent

Partners record each partner's capital movements and share %, and see the eight §24 figures for every partner side by side. There is
one page, `/management/capital`, backed by `GET /management/capital`, `POST /management/capital/entries` and
`PUT /management/capital/shares`. The data is partner-only: `super_admin`, the accountant and every other role are refused at the
route, so no capital figure ever reaches them. Every write goes into the management audit trail (the mgmt-002 kind `mgmt.capital`,
which is already registered as partner-only and already hidden from `/admin/audit`).

## 2. Decisions (CP1–CP15)

| # | Point | Answer |
|---|---|---|
| CP1 | Who has an account | Every user whose role is `partner`. The page lists active partners plus any former partner who has entries or shares. Both partners see both accounts (§2 "same data"; backlog Q-17 note) |
| CP2 | Entry kinds | `initial` (Initial capital), `additional` (Additional investment), `withdrawal` (Withdrawal), `profit_distribution` (Profit distribution). A distribution is money paid out to a partner from profits. It is recorded as an entry and counts as "Returns"; it does **not** change the capital balance (AC2) |
| CP3 | Entry fields | partner, `entry_date` (1 January 2000 to today, IST), kind, `amount` (INR, > 0, 2 decimals, `Numeric(12,2)`, the mgmt-014 money rules), `note` (optional, single line, ≤ 500) |
| CP4 | Entries are never edited or deleted | This is a capital record. A mistake is corrected with an opposing entry that carries a note (e.g. a withdrawal noted "corrects an additional investment entered twice"). A wrong distribution has no opposite kind, so a void/reverse action is a follow-up (`NEEDS_CONFIRMATION`) |
| CP5 | Share % and commitment | `partner_shares`: one row per (partner, `effective_from` month). `share_pct` is 0–100 with 2 decimals (0 = no longer shares in profit); `commitment` is the optional total capital the partner committed (INR ≥ 0). The share in force on a day is the partner's latest row with `effective_from` ≤ that day. Rows are kept as the history; saving a partner again for the same month replaces that month's row (audited before → after) |
| CP6 | Setting shares | `PUT /management/capital/shares` `{effective_from: "YYYY-MM", shares: [{partner_id, share_pct, commitment}]}` sets the rows for the partners sent, from the first day of that month. Partners not sent keep theirs. Each partner may appear once and must be an active partner. The month can be January 2000 up to 12 months ahead (a planned change) |
| CP7 | Share total ≠ 100% (AC1) | **Warn, never block.** `share_total` = the sum of the shares in force today for the listed partners. The page shows "Shares in force total X%, not 100%" whenever it is not exactly 100.00 (also when no share is set) |
| CP8 | The eight figures (as of today) | Capital invested = Σ `initial`; Additional = Σ `additional`; Withdrawals = Σ `withdrawal`; **Capital balance = invested + additional − withdrawals** (AC2); Returns = Σ `profit_distribution`; Share % = in force today (none → "—"); Outstanding contribution = max(commitment − (invested + additional), 0) using the commitment in force today ("—" without a commitment); Profit share — CP9. A Total column sums the money figures and the share % |
| CP9 | Indicative profit share (AC3) | For the chosen period: Σ over each month in the period of (that month's **net profit** from mgmt-009 `management_pnl.dashboard(…, "month").total.contribution`) × (the partner's share in force on the 1st of that month) ÷ 100, rounded half-up to 2 decimals. With one share for the whole period this is exactly share % × net profit; a mid-year share change is applied from its month (backlog edge case). A loss gives a negative share (shown in red). "—" when the partner had no share in force in any month of the period. Partners see university commission in P&L (M3), so net profit is the partner P&L figure. Indicative only: nothing is distributed |
| CP10 | Period | `month` (YYYY-MM, January 2000 to this IST month, default this month; mgmt-009's `_past_month`) and `period` = `month` / `quarter` / `year` (financial year to date), **default `year`** — profit share is a yearly figure. The response echoes the period label and its net profit |
| CP11 | Withdrawal over the balance | **Warn, never block** (backlog negative scenario). Before sending, the form says "This withdrawal is more than {partner}'s capital balance of ₹X. Record it anyway?" and needs a second click. The API accepts it. A negative balance is shown in red with "Withdrawals exceed the capital put in" |
| CP12 | Audit | Entry → `mgmt.capital.create` with partner, kind, entry date, amount and note (values kept: partner-only kind, MA3). Share row → `mgmt.capital.create` for a new row, `mgmt.capital.update` with only the changed fields (before → after) when that month's row is replaced, nothing when it is unchanged. Same transaction as the write (MA10). `created_by` is kept on every row |
| CP13 | Access (M13) | Partner → `200`/`201`. `super_admin` and accountant → `403` "Only partners can open this". Any other role → `403` "Management access required". Signed out → `401` (mgmt-014's `_partner`) |
| CP14 | Concurrency | Entries are plain inserts. Share rows are unique per (partner, `effective_from`). The partner's row for that month is read `FOR UPDATE`, and a concurrent first insert that loses the unique race gets `409` "The shares were changed at the same time. Reload and try again." |
| CP15 | Page and demo data | `/management/capital`: a period form, a capital-accounts table (figure rows × partner columns + Total), warnings, "Record a capital entry" and "Set share %" forms (closed until asked for), the entries history (newest first, 25 per page, `offset`) and the share history. The Command Center entry "Partner capital accounts" goes live (partner-only). `app.seed` adds once (shares only while neither demo partner has a share row; the entries only while no "Demo: opening capital." entry exists): 50% / 50% from April 2024 with a ₹10,00,000 commitment each, and ₹5,00,000 initial capital each on 1 April 2024 |

## 3. Components

- `models.py`: `CAPITAL_ENTRY_KINDS`, `PartnerCapitalEntry` (`partner_capital_entries`; CHECKs: kind, amount > 0; index on
  `(partner_user_id, entry_date)`), `PartnerShare` (`partner_shares`; CHECKs: 0 ≤ share_pct ≤ 100, commitment ≥ 0, effective_from is
  the 1st of a month; unique `(partner_user_id, effective_from)`).
- Migration `0158_partner_capital` (after `0157_direct_tieups`), guarded like 0151; `downgrade()` refuses while either table has rows.
- `schemas.py`: `CapitalEntryCreate`, `CapitalSharesIn` (+ row), `CapitalEntryOut`, `CapitalShareOut`, `CapitalAccountOut`, `CapitalOut`.
- `services/partner_capital.py`: `figures`, `profit_shares`, `view`, `add_entry`, `set_shares`. It reuses `management_pnl.dashboard`
  (unchanged), `management_audit.record` and the investments helpers for people.
- `api/management.py`: three routes appended after the investments block, all behind `_partner`.
- Web: `lib/partnerCapital.ts` (types, labels, query/URLs, form checks and bodies), `components/PartnerCapital.tsx` (accounts table,
  warnings, histories; server), `components/CapitalEntryForm.tsx` and `components/CapitalSharesForm.tsx` (client), page
  `app/management/capital/page.tsx`, and the `lib/management.ts` entry `href`.

## 4. Data flow

GET: route → `_partner` → `_past_month` → `partner_capital.view(db, user, month, period, offset)`:
1. List the partners (CP1).
2. Run one grouped `SUM(amount)` per (partner, kind).
3. Read all share rows, newest first, for the in-force shares and the history.
4. Call `management_pnl.dashboard` once per month in the period (≤ 12 calls) to get each month's net profit.
5. Compute the figures and totals.
6. Page the entries.

POST and PUT validate (schemas and the active-partner check), write, audit and commit in one transaction. The client then calls
`router.refresh()`.

## 5. Error handling

- `401` signed out; `403` shows the access card.
- `422` names the problem ("Choose an active partner", "Enter the amount in rupees…", "A partner can be listed only once", "The entry
  date can't be in the future", "Choose a month from January 2000 to 12 months ahead"), and the form keeps the entry.
- `409` on the share race.
- A dropped network keeps the entry; a double click sends once.
- A failed GET shows "Capital accounts are unavailable right now".

## 6. Testing

- Backend `tests/test_mgmt_015_partner_capital.py`:
  - AC2 balance; AC3 profit share (one share and a mid-period change); AC1 share-total warning; AC4 403 for super_admin and the
    accountant (every route).
  - Other roles 403, 401, a withdrawal over the balance accepted and flagged, audit rows with values, an unchanged share writing no
    audit, validation 422s, entries paging, a former partner listed.
- `tests/test_mgmt_015_migration.py`: model ↔ migration CHECKs, the downgrade refusal.
- Web: `partnerCapital.test.ts` (query, form problems/bodies, money text), `PartnerCapital.test.tsx` (table, warnings, red),
  `CapitalEntryForm.test.tsx` (overdraw confirm, double click), `CapitalSharesForm.test.tsx`, and `management.test.ts` (the live entry is
  for partners only).
- Playwright `mgmt-015-partner-capital.spec.ts`: a partner records an entry and sets shares and sees the figures; the accountant and the
  super admin get "Access unavailable".
