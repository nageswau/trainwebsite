# itc-013 — Per-enrolment fee account: design and plan

Source: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` §itc-013. Dependency itc-001 merged (PR #408). Owner direction (Q-01 log):
"proceed with recommended answers" — the answers below are the builder's calls, recorded as `DEC-SCOPE-344`.

## Open questions taken with the recommended answer
- **Q-12 (GST):** out of scope until confirmed. `tax` is part of the account and is always `0`; `NEEDS_CONFIRMATION`.
- **Q-13 (stored or computed; overpayment):** computed from `Payment` rows — no `fee_accounts` table, so it can never drift. Recording
  more than the balance is refused (422), so an overpayment cannot be created; `balance < 0` can only arise from future credits
  (itc-015) and is then shown as a credit.

## The one definition (`services/fee_accounts.py`)
An enrolment's fee rows are the `Payment`s with `division='it'`, `reference_type IN ('enrollment_fee','enrollment')`,
`reference_id = enrollment.id`, `status IN ('pending','overdue','paid','succeeded')` (failed/cancelled rows bill nothing).

| Field | Definition |
|---|---|
| `course_fee` | Σ (amount + discount_amount) of the rows (the gross billed) |
| `discount_approved` | Σ discount_amount (nehn-021 direct discount; itc-014 may add approval later) |
| `tax` | 0 (Q-12) |
| `total_payable` | course_fee − discount_approved + tax |
| `paid_confirmed` | Σ amount where status ∈ PAID_STATUSES (paid, succeeded) |
| `credits` | 0 (itc-015) |
| `balance` | total_payable − paid_confirmed − credits |
| `state` | `not_billed` (no rows), `fully_paid` (balance ≤ 0), `partially_paid` (paid > 0), `enrolled_pending_payment` |

`balance_for(db, enrollment_ids)` is one grouped SQL query (fixed query count for list pages). The student-level `student_access`
state already sums the same owed rows, so the account and the access state agree (AC5); a test pins that.

## Recording a payment (AC3)
`POST /it/enrollments/{id}/payments` `{amount, payment_mode, provider_reference?}` — `payments.add` grant, IT division (or every
division). Under a row lock on the enrolment's owed rows, the oldest-due owed row is the bill:
- `amount` must be > 0 and ≤ that row's amount (otherwise 422 naming the maximum);
- equal → that row becomes paid (mode, reference, `paid_at`, receipt);
- less → the row's amount drops by `amount` (its invoice is reissued, a stale Razorpay order on it is cleared) and a new paid row of
  `amount` is created (invoice + receipt). Gross is preserved, so `course_fee` never changes.
- `payment_mode` ∈ cash, upi, card, bank_transfer, cheque (razorpay is set only by the gateway). Audit via itc-001 `audit_change`.

## Payment mode and receipt (AC4)
- Mig `0228`: `payments.payment_mode` nullable + CHECK (6 values); backfill `razorpay` on paid gateway rows.
- `_mark_paid` sets `razorpay` for a gateway payment; `POST /admin/payments` accepts an optional validated `payment_mode`.
- Receipt PDF gains "Payment mode" and "Transaction reference"; an enrolment-fee receipt's remaining balance is the account balance.
- `/payments/mine` and `/admin/payments` gain `payment_mode`, `provider_reference` (additive).

## Read API and access
- `GET /it/enrollments/{id}/fee-account`: the student (own only), the IT counselor (linked students only, itc-003), a `payments.view`
  holder in IT/every division. Otherwise 404 for another's record, 403 for a role with no access.
- `GET /it/student/fee-accounts`: the IT student's own accounts (for the Fees page).

## UI
- `FeeAccountSummary` (new, small): course fee, discount, tax, total payable, paid, credits, balance, state; on the student Fees page
  above the payment cards (loading, empty "No fee has been billed yet", and error states).
- IT counselor "My Students" table and IT admin "Enrollments" table gain a "Fee balance" column (batched).
- IT admin Payments page gains a "Record enrolment payment" action form; "Create payment due" gains "Payment mode".

## Non-goals
Tax computation, refunds/credits, discount approval, installment plans/reminders (itc-014…018), notifications with amounts.

## Regression risks
Payment readers (ledger, management IT revenue, bdm metrics, reports): a split keeps total paid + owed unchanged, the new paid row is a
normal `enrollment_fee` row, so revenue counts it once. Webhook/verify unchanged except `payment_mode`. nehn-018/019/021 tests.

## Tasks (TDD)
1. Migration 0228 + model column + CHECK; migration test.
2. `fee_accounts.balance_for`/`account` + unit tests (45k → 20k → 25k; pending razorpay; discount after partial; legacy; agreement
   with `student_access`).
3. Record-payment endpoint + tests (split, full, over-amount 422, wrong mode 422, grant 403, other division 403, audit row).
4. Fee-account GET endpoints + access tests (student own/other, counselor linked/unlinked, admin, trainer 403).
5. Payment mode on `_mark_paid`, `create_payment`, `/payments/mine`, `/admin/payments`; receipt lines + balance.
6. Portal columns (counselor students, admin enrollments).
7. FE: `FeeAccountSummary`, `FeePaymentPanel` mount, WorkflowPanel specs; vitest.
8. Playwright e2e; docs (DEC-SCOPE-344, API §12IP, RBAC §2.244, RTM, backlog status).
