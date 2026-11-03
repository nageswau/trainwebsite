# itc-014 — Discount and waiver approval: design and plan

Source: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` §itc-014 (AC1–AC3, +/−/E). Dependency itc-013 merged (DEC-SCOPE-346, PR #408 chain).
Owner direction: "proceed with recommended answers" — every answer below is the builder's call, recorded as `DEC-SCOPE-363`,
`NEEDS_CONFIRMATION`.

## Q-14 taken with the recommended answer
**Maker-checker** for IT enrolment fees: a request never changes payable; only an approval by a `discounts.approve` holder who is not the
requester does. The nehn-021 direct discount (`POST /admin/payments/{id}/discount`, `discounts.add`) is left exactly as it is (every
division; its tests and the accountant's grant depend on it). Whether to retire it for IT is `NEEDS_CONFIRMATION`.

## Decisions (D1–D8)
| # | Decision |
|---|---|
| D1 | New table `fee_discount_requests` (`0245_fee_discount_requests`, on itc-005's `0244_it_status_labels`): enrolment, amount (> 0), reason (1–500), status `pending/approved/rejected`, requester, decider, decided_at, decision_note (≤ 500). A partial unique index allows **one pending request per enrolment** (a second → 409). |
| D2 | **Who requests:** the IT counselor linked to the student (itc-003), or a `discounts.add` holder in IT (or every division). Others 403; another counselor's student 404. |
| D3 | **Who approves/rejects:** the new grant `discounts.approve` (catalogue `discounts` gains `approve`), default IT Admin (0245 seeds it; super_admin implicit). The requester can never decide their own request → **403** (AC3). Must be in IT (or every division). |
| D4 | **Amount:** rupees off the enrolment's **owed balance** (Σ owed rows). 0 < amount ≤ owed balance at request time (422 otherwise; a full waiver is allowed). Re-checked under row locks at approval (E: a payment may have arrived) → 409 naming the current owed balance. |
| D5 | **Applying an approval:** taken off the owed bills **latest due first** (the agreed next due date and amount stay where possible). Each touched row: `amount −= x`, `discount_amount += x`, `discount_reason`/`discounted_by_id` set (nehn-019 columns), its invoice reissued and any stale online checkout cleared (nehn-021/itc-013 rule). A row brought to 0 becomes status **`waived`**, so it can never be "paid" for ₹0; `fee_accounts` counts `waived` rows in the gross so `course_fee` never changes. |
| D6 | **Audit (AC2):** `audit_change` on the enrolment: `it.fee.discount_requested`, `it.fee.discount_approved` (before/after `discount_approved`, `total_payable`, `balance`), `it.fee.discount_rejected`. Ids-only metadata (request id). No amounts in notifications (none are sent). |
| D7 | **Lifecycle:** an approval runs `it_lifecycle.sync(..., cause="fee")` like a recorded payment (a full waiver moves the enrolment to Paid). |
| D8 | **Pending request (AC1):** never touches `Payment`; the fee account is unchanged until approval. |

## API (§12JI)
- `GET /it/enrollments/{id}/discount-requests` — the enrolment's requests, newest first. Readers per itc-013 `_readable` (linked counselor;
  `payments.view` holder in IT); an IT student → 403.
- `POST /it/enrollments/{id}/discount-requests` `{amount, reason}` → 201 the request.
- `GET /it/discount-requests?status=pending|approved|rejected` (default pending) — the approval queue; `discounts.approve` in IT.
- `POST /it/discount-requests/{id}/approve` `{note?}`, `POST /it/discount-requests/{id}/reject` `{note}` (note required to reject) →
  the request (+ `account` on approve). Not pending → 409.

Each request item: `id, enrollment_id, enrollment_code, student {id, full_name}, course, amount, reason, status, requested_by {id,
full_name}, created_at, decided_by {id, full_name} | null, decided_at, decision_note, own` (`own` = the caller made it).

## UI
- **Student record** (`/it/{counselor|admin}/students/[id]/profile`), under each fee account card: `FeeDiscountRequests` — the
  enrolment's requests (status badge, amount, reason, requester, decision) and a "Request a discount" form (amount, reason) while the
  balance is > 0 and none is pending. Loading, empty, error and success states.
- **IT Admin → Payments**: `DiscountApprovalQueue` (shown to `discounts.approve` holders in IT): pending requests with Approve and Reject
  (reject asks for a note); the caller's own requests show "Your request — another approver must decide" instead of buttons.

## Non-goals
Notifications for requests, multi-level approval, percentage discounts, tax, refunds (itc-015), retiring nehn-021.

## Regression risks
nehn-005 catalogue tests (a new key), nehn-021 tests, `fee_accounts` readers (a `waived` status only appears through this feature; ledger,
revenue and `student_access` read paid/owed statuses only, so a waived row is invisible to them, as a zero bill should be).

## Tasks (TDD)
1. Migration 0245 + model + catalogue/default grant; migration test.
2. Service `fee_discounts.py` (request, list, approve, reject) + `fee_accounts` `waived`; API tests for AC1–AC3, +, −, E, access.
3. Router in `api/fee_accounts.py`, wired in `main.py`.
4. FE `FeeDiscountRequests` + `DiscountApprovalQueue`, mounts, vitest.
5. Playwright e2e; docs (DEC-SCOPE-363, API §12JI, RBAC §2.263, RTM, backlog status).
