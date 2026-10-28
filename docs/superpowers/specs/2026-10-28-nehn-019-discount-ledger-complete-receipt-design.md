# nehn-019 — Payment discount ledger and complete receipt (design)

**Source:** `CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` §`nehn-019` (§7 "Payment Receipt" L157-166, "Discounts" L169-172).
**Decision:** `DEC-SCOPE-312`. **API:** `API_CONTRACT.md` §12HJ. **Migration:** `0215_payment_discount_ledger`.
**Dependencies:** nehn-003 (private storage, #345) and nehn-020 (student invoices retired, #357) are merged.

## Intent

A student's receipt is their payment document (nehn-020). Today it shows only the receipt no, the generation date, the payer, a
reference type and the amount. A discount overwrites `Payment.amount`, so the original fee survives only in the audit log. The
receipt must show: student details, course, receipt number, payment date, amount paid, discount (if any), remaining balance (if
any) and payment status.

## Goals

1. A discount is recorded on the payment. Applying it no longer loses the original (gross) amount.
2. A new receipt shows every listed field, and "—" wherever a value is unknown.
3. The student's fee panel shows the original amount, the discount and the payable amount, plus the paid date.

## Non-goals and anti-goals

- No change to what anyone pays. `Payment.amount` stays the **net payable** amount, so Razorpay orders, `pending_fee` (certificate
  eligibility), the ledger and revenue sums keep reading net figures without any change.
- No GST/tax breakdown (OD-11 / `DEC-PAY-002` still open), no change to invoices (nehn-020) and no new authorization rules.

## Design (builder's calls, marked as such: the user asked to proceed with the recommended answers)

| # | Topic | Call |
|---|---|---|
| D1 | Columns | `payments` gains `discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0`, `discount_reason VARCHAR(500) NULL`, `discounted_by_id UUID NULL → users.id` and `paid_at TIMESTAMPTZ NULL`. **Gross is derived** (`amount + discount_amount`), not stored: the backlog's `gross_amount` column would duplicate it and could drift. The API still returns `gross_amount`. |
| D2 | Repeat discounts | Cumulative: `discount_amount += old amount − new amount`. `discount_reason` and `discounted_by_id` hold the latest discount. The audit log keeps each step, unchanged (`payment.discount` with original/discounted/reason). |
| D3 | Payment date | `paid_at` is set (DB `now()`) by `_mark_paid` (verify and webhook) and by the paid-at-creation branch of `POST /admin/payments`. The receipt's "Payment date" is `paid_at`. |
| D4 | Issued receipts (open question) | **Immutable.** A receipt is generated once, at payment, and is never regenerated. Receipts issued before this feature keep their old layout. The receipt is a snapshot: the balance is the balance just after this payment. |
| D5 | Balance and status | For an EMI instalment: the balance is the sum of the net amounts of the schedule's instalments not yet paid. For any other payment, the balance is 0 once paid. Status is "Paid" when the balance is 0, otherwise "Partially paid". |
| D6 | Course / batch | Resolved when `reference_type` ∈ {`enrollment_fee`, `enrollment`} and `reference_id` is an `Enrollment`: program name and batch name. Otherwise "—". |
| D7 | Student details | Name, student code (`users.student_code`), email and phone. Each one shows "—" when missing. |
| D8 | Agent deposit (AGN-011) | Unchanged: it is still billed to the agent and names the student it was paid for. It cannot be discounted (existing 409). |
| D9 | 100 % discount | Allowed as today (`0 ≤ new < current`). The receipt is issued only when the payment is marked paid, and then shows 0.00. Checkout of a zero amount is unchanged existing behaviour (out of scope). |
| D10 | Authorization | Unchanged. Another user's receipt stays **403** (the existing contract and tests). The backlog's "404" is recorded as `NEEDS_CONFIRMATION`, not changed silently. |
| D11 | Exposure | `discount_reason` is an internal justification. It appears on the admin list, not in the student's `/payments/mine`. |
| D12 | Backfill | `discount_amount` = (the largest `original_amount` in the payment's `payment.discount` audit rows) − the current amount, when that is positive. Reason and actor come from the latest of those rows. `paid_at` = the receipt's `issued_at` for paid payments that have a receipt. Everything else stays NULL / 0 and renders as "—". The downgrade drops the four columns. |

## API (additive only)

- `GET /payments/mine`: each row gains `gross_amount`, `discount_amount` and `paid_at`.
- `GET /payments/emi-schedule`: each instalment gains `discount_amount` and `paid_at`; each schedule gains `paid_amount` and
  `balance`.
- `GET /admin/payments`: each row gains `gross_amount`, `discount_amount`, `discount_reason` and `paid_at`.
- `POST /admin/payments/{id}/discount`: the response gains `gross_amount` and `discount_amount`. The request is unchanged.

## Acceptance criteria

1. A discounted, partially paid EMI enrolment's receipt shows the gross amount, the discount, the amount paid, the remaining
   balance, status "Partially paid", the course, the batch, the student code, the email and the payment date.
2. Applying a discount keeps the gross amount (`amount + discount_amount`) and records the reason and the admin.
3. Existing payments (no discount, no `paid_at`, no enrolment) render without errors, with "—" for missing values. This holds for
   the receipt, the panel and the APIs.
4. `Payment.amount` stays the net amount: checkout and `pending_fee` are unchanged.
5. The student panel shows the original amount, the discount and the payable amount when a discount exists, and the paid date when
   it is known.

## Regression risks

`test_admin_payment_discount`, `test_pay_001_stu_010_payment_gateway` (it needs real Razorpay keys, so it is skipped in worktrees),
the AGN-011 paid/receipt tests, `test_nehn_003_private_storage`, `FeePaymentPanel.test.tsx` and the migration round-trip test.

## Plan

1. RED/GREEN: model columns + migration 0215 (with backfill) + a migration test.
2. RED/GREEN: the discount route writes the ledger fields; existing discount tests stay green.
3. RED/GREEN: `paid_at` is set in `_mark_paid` and in admin create-paid.
4. RED/GREEN: the receipt content: a pure `receipt_lines()` builder plus `_ensure_receipt` gathering the context (student,
   course/batch, balance, status). Tested through the PDF text (`rl_config.pageCompression=0`).
5. RED/GREEN: the additive API fields.
6. RED/GREEN: `FeePaymentPanel` shows the breakdown and the paid date (vitest).
7. Docs: DEC-SCOPE-312, §12HJ, backlog status, tracker, RTM.
