# itc-015 — Refunds, adjustments and payment correction: design and plan

Source: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` §itc-015. Dependencies itc-001 (PR #408) and itc-013 (PR #419) merged; itc-014 is
a dependency only "if a shared approval engine is used" — none is used here. Owner direction (Q-01 log): "proceed with recommended
answers"; the calls below are the builder's, recorded as `DEC-SCOPE-362`, every one `NEEDS_CONFIRMATION`.

## Open questions taken with the recommended answer
- **Q-15 (gateway):** manual only. No Razorpay refund API call; a refund records how the money went back (cash, UPI, card, bank
  transfer, cheque) and its reference. A gateway payment's credit is refunded the same manual way.
- **Q-15 (revenue):** yes, refunds reduce reported revenue. A refund is an automatic IT income line of minus its amount in
  `ledger.lines()` (source `fee_refund`), dated its IST day, attributed to the enrolment's course and batch in the IT revenue dashboard.
- **Q-14 (maker-checker):** not yet (itc-014 is unbuilt). A `payments.refund` holder records an adjustment directly and is stored as
  its approver — the nehn-021 direct-grant pattern. No self-approval check exists because there is no second step.
- **F1 (meaning of "credits"):** `credits` = credit notes + write-offs (they lower what is owed). A refund is money paid back out of a
  credit, so it is a separate figure `refunded` that raises the balance back. Formula:
  `balance = total_payable − paid_confirmed − credits + refunded`. The backlog's "+" case (₹5,000 back after a batch change) is a
  ₹5,000 credit note (balance −5,000, shown as "Credit") then a ₹5,000 refund (balance 0).
- **F2 (correction):** a correction of a manually recorded payment (amount, mode or reference typo) never edits or deletes the row:
  the original is marked `reversed` (its amount, mode, reference and receipt stay as recorded), its bill is reopened as a new pending
  row (same amount, discount and due date), and the corrected payment is recorded on it through itc-013's `record_payment` (new row,
  new receipt). A `reversal` adjustment links original and replacement. A gateway payment cannot be corrected (credit note + refund).
- **F3 (API path):** `/it/enrollments/{id}/…`, matching itc-013, rather than the backlog's `/accounts/…` (Q-17, the accounts route, is
  still open). The list is part of the fee account response (`adjustments`), so every reader of the account sees it.

## Data (`fee_adjustments`, migration `0244_fee_adjustments` on `0243_it_conversion`)
| Column | Notes |
|---|---|
| id, enrollment_id (FK), created_at | |
| kind | `credit_note`, `write_off`, `refund`, `reversal` (CHECK) |
| amount | > 0 (CHECK) |
| applied_amount | the part of a credit note / write-off that lowered owed bills (0 ≤ applied ≤ amount) |
| reason | required, ≤ 500, shown to the student |
| payment_mode, reference | refund: mode required (offline modes, CHECK); reference optional |
| payment_id, replacement_payment_id | reversal only; a partial unique index makes one reversal per payment |
| document_no | credit note `CN-`, write-off `WO-`, refund `RF-` + year + hex; a reversal has none |
| approved_by_id | the recorder (Q-14) |

Rows are never updated or deleted (no such endpoint). The grant `payments.refund` (new action `refund`) is seeded for `it_admin`.

## Account (`services/fee_accounts.py`)
Billed rows now include `waived` (a bill fully covered by a credit: amount 0, kept so its gross and discount still count); `reversed`
rows bill nothing. A second grouped query sums the adjustments.

| Field | Definition |
|---|---|
| course_fee | Σ (amount + discount) of billed rows + Σ applied_amount (the gross before credits lowered bills) |
| credits | Σ amount of credit notes and write-offs |
| refunded | Σ amount of refunds (new, additive) |
| balance | total_payable − paid_confirmed − credits + refunded |
| adjustments | each: id, kind, amount, reason, mode, reference, document_no, created_at (new, additive) |

## Operations (`services/fee_adjustments.py`, no commit; the enrolment row is locked first, then its owed bills)
- **credit note** — needs a billed account; amount ≤ total_payable − credits (else 422). Lowers owed bills, latest due first; a bill
  lowered to 0 becomes `waived`; each lowered bill's invoice is reissued and a stale checkout cleared (the discount endpoint's rule).
  What no bill absorbs becomes a credit (balance < 0).
- **write-off** — amount ≤ the balance still owed (else 422); always fully applied to owed bills.
- **refund** — amount ≤ the credit on the account (−balance), so never more than was paid (else 422); mode required.
- **correction** — the payment must be this enrolment's, paid, manual (else 404/409); something must change (else 422); then F2.
  If the corrected amount exceeds the reopened bill, `record_payment`'s 422 rolls the whole correction back.
- Each writes `audit_change` (itc-001) with the balance before/after; a correction also records old and new amount, mode and
  reference (AC3); `it_lifecycle.sync` follows (itc-031). Credit notes, write-offs and refunds get a PDF (`generate_receipt_pdf`'s
  label/value layout, titled "Credit note" / "Write-off" / "Refund receipt").

## API (API_CONTRACT §12JH, RBAC §2.262)
- `POST /it/enrollments/{id}/adjustments` `{kind, amount, reason, payment_mode?, reference?}` → 201 `{adjustment, account}` —
  `payments.refund`, IT division (or every division).
- `POST /it/enrollments/{id}/payments/{payment_id}/correction` `{amount, payment_mode, provider_reference?, reason}` → 201
  `{payment, account}` — same gate.
- `GET /it/fee-adjustments/{id}/document` → `{url, expires_in}` — whoever may read the enrolment's fee account (itc-013's gate).
- `GET /it/enrollments/{id}/fee-account` and `/it/student/fee-accounts` gain `refunded` and `adjustments` (additive).

## UI
- `FeeAccountCard`: a "Refunded" figure and a "Credits and refunds" list (kind, amount, date, mode/reference, reason, document
  download). Shown on the student's Fees page and the staff student record.
- IT Admin Payments page: "Record fee adjustment" and "Correct a recorded payment" forms (`payments.refund`).

## Non-goals
Razorpay refund API; maker-checker (itc-014); accounts workspace refunds list (itc-017); tax.

## Regression risks
`balance_for` readers (portal columns, receipts, lifecycle, student 360); `record_payment`; IT revenue and the management ledger
(new line source); `student_access` (waived rows are not owed, so it agrees with the account); the itc-013/016/018/031 suites.

## Tasks (TDD)
1. Migration 0244 + model + grant (catalogue, default grants); migration/permission tests.
2. Account figures with adjustments (credits, refunded, applied, waived, reversed) — unit tests.
3. Adjustment service + endpoint (credit note, write-off, refund; limits; audit; lifecycle) — API tests.
4. Correction service + endpoint — API tests (never deletes, audit old/new, gateway 409, double 409, over-amount rollback).
5. Document endpoint + access tests.
6. Ledger `fee_refund` line + IT revenue attribution — tests.
7. FE: `FeeAccountCard` additions, WorkflowPanel specs; vitest.
8. Playwright e2e; docs (DEC-SCOPE-362, API §12JH, RBAC §2.262, backlog status).
