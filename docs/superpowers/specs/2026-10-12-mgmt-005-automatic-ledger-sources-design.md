# mgmt-005 — Automatic ledger sources — design

- **Feature:** `mgmt-005` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-005). Depends on mgmt-004 (PR #246, merged on `main@737efcf9`).
  rec-031 (`RecruiterPayment`, PR merged) and upc-019 (`UniversityCommissionReceipt`, merged) both exist on main, so both optional sources
  are wired.
- **Evidence:** `DEC-SCOPE-186` M4 (`EXPLICIT_APPROVAL`): "Income: paid `Payment` rows by vertical (agent deposits excluded as pass-through),
  plus rec-031 and upc-019 receipts … Expenses: … automatic lines from paid agent commissions and BDM trip expenses". `EVID-017` §22
  ("connected to every module", `DERIVED_BLUEPRINT`). mgmt-004 `DEC-SCOPE-189` (ML5 INR only, ML10 figures).
- **Decision:** one new DEC-SCOPE (number taken at merge). MA1–MA12 below answer Q-06 (auto-line part), Q-07 and Q-08 with **recommended
  defaults, `UNVERIFIED`**, on the owner's instruction to proceed with recommended answers. Q-32 (student PII in drill-downs) stays open:
  auto lines carry **no student or agent names** until it is answered.

## 1. Intent

The management ledger shows, next to the manual entries, every automatic money line the platform already records — computed on read,
nothing copied — so the finance tier sees one income/expense picture. Auto lines are read-only, carry a source badge and a source link
(type + id) for mgmt-033's drill-down. `services/ledger.py` exposes the UNION (`lines`) that mgmt-006 … mgmt-013 reuse.

## 2. Decisions (MA1–MA12)

| # | Point | Answer |
|---|---|---|
| MA1 | Sources | (1) manual entries (mgmt-004); (2) paid `Payment` rows except `agent_deposit`; (3) paid `AgentCommission`; (4) `BdmTripExpense` of approved trips; (5) rec-031 `RecruiterPayment`; (6) upc-019 `UniversityCommissionReceipt` |
| MA2 | Recognition (Q-07) | **Cash basis** on the IST day money moved. Payment: the receipt's `issued_at` (created on the move to paid), else the payment's `updated_at` (a paid payment never moves again, AGN-011 D2). Commission: `paid_at`. Trip expense: `expense_date`. Recruiter payment and university receipt: `received_on` |
| MA3 | Paid | Payment `status` ∈ `PAID_STATUSES` (`paid`, `succeeded`); commission `status = 'paid'` and amount > 0; trip `approval_status = 'approved'`. Every rec-031 / upc-019 row is money received |
| MA4 | Refunds and EMI (Q-07) | A payment that is not paid (pending, failed, refunded by the provider) is excluded. No payment is ever shown negative: the payments module has no refund state on a paid payment. Each EMI instalment is its own payment and counts once, when paid |
| MA5 | Verticals (Q-08) | Payment by `division`: `it` → IT Training, `overseas` → Abroad Education, anything else → Other. Commission → Abroad. Trip expense by the BDM's type: `college` → IT, `agent` → Abroad, `school` → School projects, no profile → Shared. Recruiter payment → Recruitment. University receipt → Abroad |
| MA6 | Labels | Category label (not a ledger category; auto lines have none): payment → the income head of its vertical ("IT training", "Abroad education", "Other"); commission → "Agent commissions"; trip → "Travel"; recruiter → "Recruitment"; university → "University commission" |
| MA7 | Description (Q-32 interim) | No person names. Payment: "Enrolment fee" / "Service fee" / "Payment" (+ " · instalment N") + " · receipt RCP-…" when issued. Commission: "Agent commission" + " · claim REF" when claimed. Trip: "Trip TRP-… · travel/stay/food/local/other". Recruiter: "Invoice INV-… payment". University: "University name · reference" |
| MA8 | Currency (Q-06) | The ledger counts **INR only** (ML5). A non-INR auto line is listed in its own currency, marked **Not counted**, and summed per currency in `totals.not_counted`. No conversion |
| MA9 | API | `GET /management/ledger?include=auto`. Without `include` the response is exactly mgmt-004's (every item now also says `source: "manual"`). With it, items are the UNION, newest first, paged as before |
| MA10 | Filters | `month`, `kind`, `vertical` apply to every line. `category` and `status` are manual-entry fields: with either set, auto lines drop out (they have neither) |
| MA11 | Totals | With `include=auto`: approved manual entries (reversals negative, ML10) + counted (INR) auto lines, over every filter but status; plus `not_counted [{currency, kind, amount, count}]` |
| MA12 | Access | Finance tier only (partner, accountant) — the existing `require_finance`. `super_admin` and every other role `403` |

## 3. Data

No migration. The UNION reads indexed columns (`payments.status`, `receipts.payment_id`, `agent_commissions.status`,
`bdm_trip_expenses.trip_id`, `recruiter_payments.invoice_id`, `university_commission_receipts.university_id/received_on`). The paid-day
expressions are computed, so the month filter scans the paid rows of each source; volumes are small (risk noted for mgmt-013).

## 4. Components

- `services/ledger.py`: `lines(include_auto)` — the UNION subquery with columns `source, id, entry_date, kind, vertical, category_id,
  category_label, status, amount, signed_amount, currency, label, counted, created_at`; `line_filters(...)`; `lines_page(...)` and
  `lines_totals(...)`. The mgmt-004 path (`page`, `totals`, `list_filters`) is unchanged.
- `api/management_ledger.py`: `include: Literal["auto"] | None` on `GET ""`.
- `schemas.py`: `LedgerAutoLine` (source, id, entry_date, kind, vertical, category_label, amount, currency, description, counted);
  `LedgerEntryOut.source = "manual"`; `LedgerPage.items: list[LedgerEntryOut | LedgerAutoLine]` discriminated on `source`;
  `LedgerTotals.not_counted: list[...] | None`.
- Web: `lib/managementLedger.ts` (`include` filter, auto types, source labels, `formatMoney`); `ManagementLedger.tsx` ("Lines" select:
  Manual entries / Manual + automatic; auto rows show a source badge, no link, "Not counted" for non-INR; totals labels and the
  not-counted note). Ledger page intro mentions automatic lines.

## 5. Error handling

`401` signed out; `403` no finance tier; `422` an unknown `include` value. The page drops a malformed `include` from the address (as for
other filters) and keeps its existing access card / "The ledger is unavailable" states.

## 6. Testing

- Backend `tests/test_mgmt_005_auto_lines.py`: AC1 a paid IT enrolment fee appears once under IT income; AC2 a paid agent deposit never
  appears; AC3 a paid commission appears as an expense (an unpaid one does not); AC4 totals reconcile with the source tables for a month;
  trip expenses of approved trips only, by BDM type; rec-031 and upc-019 receipts; pending/failed payments excluded; EMI instalments
  counted separately; non-INR not counted + `not_counted`; category/status filters drop auto lines; kind/vertical/month filters; paging;
  mgmt-004 response unchanged without `include`; super_admin 403; no names in descriptions.
- Web vitest: `managementLedger.test.ts` (include filter, href/url), `ManagementLedger.test.tsx` (auto row badge, no link, not counted).
- Playwright `mgmt-005-auto-lines.spec.ts`: accountant switches to "Manual + automatic", sees the seeded paid IT fee as an automatic IT
  income line with its badge and no deposit line; super_admin refused.
