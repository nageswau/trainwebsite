# AGN-011 — Deposit collection through Razorpay (Step 7) — Design

**Status:** design approved in-session 2026-10-02 (owner: "Proceed with agn-011 using the approved Superpowers plan").
**Decision:** `DEC-SCOPE-057` (provisional number — renumber on merge if another branch reaches `main` first; AGN-012 is open in
parallel). **Migration:** `0063_application_deposits` on `0062_agent_offer_details` (provisional, same rule).
**Backlog:** `docs/delivery/AGENT_CRM_BACKLOG.md` §4 ang-011 (`DERIVED_BLUEPRINT`).

## 1. Evidence and authority

| Item | Source | Classification |
|---|---|---|
| Deposit fields: required, amount, payment status, payment date, receipt | `EVID-015` §5 Step 7 via backlog ang-011 | `DERIVED_BLUEPRINT` |
| Money collected through EduSphere Razorpay; Master or Staff pays at checkout for the student; finance remits off-system; Overseas Admin records remittance and refunds by hand | Backlog Q-06/Q-06b ("D11/D12"), **restated by the owner as this feature's requirement, 2026-10-02** | `EXPLICIT_APPROVAL` (the owner's own statement) |
| Acceptance criteria AC1–AC6 (§6) | Owner's AGN-011 statement, 2026-10-02 | `EXPLICIT_APPROVAL` |
| D1–D8 (§2) | Owner's answers in-session, 2026-10-02 | `EXPLICIT_APPROVAL` |
| Razorpay is the only payment provider | `DEC-PAY-001` (CONFIRMED_CURRENT 2026-09-03) | `EXPLICIT_APPROVAL` |

**Mis-citation recorded, not silently corrected:** the backlog cites the deposit answers as "`DEC-SCOPE-035` D11/D12". `DEC-SCOPE-035`
is ENH-027's psychometric decision, and `DEC-SCOPE-038` D11/D12 are AGN-001's admin-created agents and notifications. The deposit
answers had no register entry; `DEC-SCOPE-057` records them (the AGN-004 / AGN-007 precedent).

**Not decided here (`NEEDS_CONFIRMATION`, unchanged):** `DEC-PAY-002` multi-currency coverage by Razorpay; D1 avoids it by being INR only.

## 2. Decisions (owner, 2026-10-02)

- **D1 — INR only.** `currency` is stored and always `INR`; the request cannot set it.
- **D2 — Webhook paid-guard for all payments.** A payment in `paid`/`succeeded` never changes status again (verify or webhook). The paid
  side effects (receipt, deposit) run only on the change into `paid`. Student-fee behaviour changes only in refusing paid → other.
- **D3 — One refund, from `paid` or `remitted`.** Date, amount (> 0, ≤ paid amount), reason; `refunded` is final.
- **D4 — `GET /payments/mine` excludes agent-deposit payments.** Admin revenue totals and admin payment lists are unchanged.
- **D5 — Remit/refund: `overseas_admin` only** (AC4's wording). `super_admin` can read the deposits list but not act.
- **D6 — Approach A.** A new `application_deposits` table; every pay attempt is an ordinary `Payment` owned by the payer, so the existing
  Self-only checkout/verify rule, signature check, dedup, invoice and receipt are reused.
- **D7 — Who sets and pays.** Master, and Staff for students assigned to them (the AGN-008 application scope), both set the deposit and
  pay. No new permission flag. Recorded in the AGN-003 matrix as `BOTH_ALLOWED`.
- **D8 — One active checkout at a time.** Another member's checkout younger than 15 minutes blocks a new one (409); after that it can
  be replaced. At most 10 checkouts per deposit per rolling hour (429).

## 3. Data model

New table `application_deposits` (UUID ids, `TimestampMixin`):

| Column | Type | Rule |
|---|---|---|
| `id` | UUID PK | |
| `application_id` | UUID FK → `overseas_applications.id` `ON DELETE RESTRICT`, **unique** | one deposit per application |
| `required` | bool not null | |
| `amount` | Numeric(12,2) null | not null and > 0 when `required`; null when not required |
| `currency` | String(3) not null default `INR` | CHECK `= 'INR'` (D1) |
| `due_date` | Date null | null when not required |
| `status` | String(20) not null | CHECK in `not_required, pending, paid, remitted, refunded`; `required` ⇔ status ≠ `not_required` |
| `active_payment_id` | UUID FK → `payments.id` null | the open checkout |
| `paid_payment_id` | UUID FK → `payments.id` null | set exactly when status ∈ paid/remitted/refunded |
| `paid_at` | timestamptz null | with `paid_payment_id` |
| `remitted_at` (date), `remittance_reference` (String(100)) | null | set together; only by Overseas Admin |
| `refunded_at` (date), `refund_amount` (Numeric(12,2)), `refund_reason` (Text) | null | set together; only by Overseas Admin |
| `created_by_user_id`, `updated_by_user_id` | UUID FK → users | |

CHECKs: status set; currency; `(status = 'not_required') = (NOT required)`; `required` ⇒ `amount > 0`; `(paid_payment_id IS NULL) =
(status IN ('not_required','pending'))`; refund columns all-or-nothing; refund amount > 0.

`payments`: **no schema change.** One new status value `cancelled`, used only for `agent_deposit` payments (a superseded or failed checkout).
`Payment.reference_type = "agent_deposit"`, `reference_id = deposit.id`.

Migration `0063`: create-if-missing (0059 idiom, because 0001/0003 run `create_all`); downgrade refuses while a row exists. No backfill;
no existing row changes.

**Status machine:** `not_required ⇄ pending` (agent PUT) · `pending → paid` (paid hook only) · `paid → remitted` (admin) ·
`paid|remitted → refunded` (admin, final).

## 4. API (errors keep `{"detail": "<message>"}`)

Agent prefix `/api/v1/workflows/overseas/agent/crm/applications`; admin prefix `/api/v1/overseas-admin`. New router module
`app/api/agent_deposits.py` (`router` with the agent prefix, `admin_router` with the admin prefix), rules in
`app/services/agent_deposits.py` (functions only; never commits — the AGN-008 shape).

### 4.1 Existing endpoints (additive / guarded)

- `GET …/applications/{id}`: adds `deposit` (null or the §4.3 shape) and `payment_available` (both Razorpay keys set). Nothing removed.
- `GET /payments/mine`: excludes `reference_type = 'agent_deposit'` (D4).
- `POST /payments/{id}/checkout` on an `agent_deposit` payment → 409 `Pay this deposit from its application`.
- `POST /admin/payments` with `reference_type = 'agent_deposit'` → 422 `Agent deposits are created from the application`.
- `POST /admin/payments/{id}/discount` on an `agent_deposit` payment → 409 `An agent deposit's amount is set on its application`.
- `POST /payments/{id}/verify` and the webhook: unchanged contract; both call the paid hook (§4.4).

### 4.2 `PUT …/applications/{id}/deposit`

Body (`extra="forbid"`): `required: bool`, `amount: Decimal | None` (0.01–99,999,999.99, 2 dp), `due_date: date | None` (2000–2100).
`required=false` ⇒ amount and due_date must be null (422 `A deposit that is not required has no amount or due date`); `required=true` ⇒
amount required (422 `Enter the deposit amount`).

Flow: `_gate` → org lock → scoped application row lock (404 outside scope) → `_refuse_closed` (409 archived / withdrawn) → deposit row
lock → if status ∈ paid/remitted/refunded → 409 `This deposit is already paid and can no longer be changed` → no change → 200, nothing
written → otherwise create/update; if an active checkout exists and the amount changed or `required` became false, its Payment becomes
`cancelled` and `active_payment_id` is cleared → audit `overseas.application.deposit` (`fields`, `required`; no amount) → one commit →
log `agent_deposit_saved`. Response `{"application": detail}`.

### 4.3 Deposit shape in the detail

`{id, required, amount (string, 2 dp), currency, due_date, status, paid_at, paid_by (name), receipt_available, remitted_at,
remittance_reference, refunded_at, refund_amount, refund_reason, checkout_in_progress (bool)}`. No payment ids, no order ids, no keys.

### 4.4 `POST …/applications/{id}/deposit/checkout`

Header `Idempotency-Key` required (1–200 chars; else 422). No body is read (amount tampering is impossible).

1. **Short locked transaction:** `_gate` → org lock → application lock → `_refuse_closed` → deposit lock.
   - no deposit / `not_required` → 409 `No deposit is required for this application`
   - paid/remitted/refunded → **409** `This deposit is already paid` (AC3)
   - Razorpay keys missing → **200 `{"status": "configuration_required"}`**, nothing written (AC6; same contract as today's checkout)
   - active payment with this key and payer: order id set → 200 replay `{status:"ready", payment_id, key_id, provider_order_id, amount,
     currency, replayed:true}`; order id not yet set → 409 `A checkout is already being opened for this deposit`
   - active payment of another member, pending and younger than 15 min → 409 `Another team member is paying this deposit -- try again in a few minutes`
   - ≥ 10 payments for this deposit created in the last hour → 429 with `Retry-After`
   - else: an older active payment becomes `cancelled`; create `Payment(user_id=payer, division="overseas", reference_type="agent_deposit",
     reference_id=deposit.id, amount=deposit.amount, currency="INR", provider="razorpay", due_date=deposit.due_date,
     checkout_idempotency_key=key)`; `deposit.active_payment_id` = it; commit.
2. **No locks held:** `payments.create_checkout("razorpay", amount, "INR", f"PAY-{payment.id}")` (20 s timeout).
3. **Short transaction:** re-load the payment and deposit (locked, deposit first).
   - success → store `checkout_provider_order_id`; `_ensure_invoice`; audits `payment.checkout` and `overseas.application.deposit_checkout`;
     commit; 200 `{status:"ready", payment_id, key_id, provider_order_id, amount, currency}`; log `agent_deposit_checkout_opened`.
   - provider error (`httpx.HTTPError`) → payment `cancelled`, `active_payment_id` cleared (if still this payment); commit; **502**
     `The payment provider is unavailable -- nothing was charged. Try again shortly`; log warning `agent_deposit_checkout_provider_error`
     (no response body logged).

Concurrency: two members at once → the deposit lock serialises step 1; the second gets the 15-minute 409. A crash between steps leaves a
pending payment with no order id: the same payer's next checkout (new key) replaces it; another member waits out the 15 minutes.

### 4.5 Paid hook (verify + webhook), D2

`payments.py` gains `_lock_for_update(db, item)` and `_mark_paid(db, item, payer, *, provider_amount=None, source)`:

- Lock order everywhere: **deposit row, then payment row** (checkout also locks the deposit before touching payments) — no deadlock.
- Verify and webhook re-read the payment `FOR UPDATE` (and, for `agent_deposit`, the deposit first) before deciding.
- If the payment is already `paid`/`succeeded`: no status change; the webhook event is still marked processed; response unchanged in shape.
- Moving into `paid`: set status (+ provider reference), `_ensure_receipt`, then for `agent_deposit`:
  - deposit `pending` **and** `active_payment_id == payment.id` **and** (webhook) the Razorpay amount in paise equals `amount × 100` →
    deposit `paid`, `paid_payment_id`, `paid_at = now`, `active_payment_id = null`; audit `overseas.application.deposit_paid`
    (actor = payer, metadata `source`); log `agent_deposit_paid`.
  - otherwise (stale/cancelled checkout paid, deposit already paid, amount mismatch) → the payment is still recorded `paid` (it was
    charged), the deposit is untouched; audit `overseas.deposit.unlinked_payment`; warning log `agent_deposit_unlinked_payment`. The
    admin list shows `unlinked_paid_payments` so finance refunds it by hand.
- Non-deposit payments: unchanged apart from the paid-guard.

### 4.6 `GET …/applications/{id}/deposit/receipt`

Any in-scope Master/Staff (scope through the application, never a raw payment id). 404 `Receipt not available` unless the deposit has a
`paid_payment_id` with a receipt. Returns `{"url", "expires_in"}` exactly like `GET /payments/{id}/receipt`.
Receipt PDF: `generate_receipt_pdf(..., student_name=None)` gains an optional keyword; when set, a `Student: <name>` line is drawn
(`drawString` — literal text). `_ensure_receipt` passes the application's owner name for `agent_deposit` payments (AC5). The payer line
(`Billed to:`) is unchanged.

### 4.7 Admin

- `GET /overseas-admin/deposits?status=paid|remitted|refunded|pending|all&limit=1..100(25)&offset` → `{items,total,limit,offset}`,
  newest paid first. Roles: `overseas_admin`, `super_admin` (read). Item: `{id, application_id, agency, student, university, amount,
  currency, status, due_date, paid_at, paid_by, remitted_at, remittance_reference, refunded_at, refund_amount, refund_reason,
  unlinked_paid_payments}`.
- `POST /overseas-admin/deposits/{id}/remit` `{remitted_on: date, reference: str 1–100}` — `overseas_admin` only (else 403
  `Only an Overseas Admin can record remittances and refunds`); 404 unknown; 409 unless `paid`; 422 date in the future or before the paid date.
- `POST /overseas-admin/deposits/{id}/refund` `{refunded_on: date, amount: Decimal, reason: str 1–500}` — `overseas_admin` only; 409
  unless `paid`/`remitted`; **422** `A refund cannot exceed the paid amount` (AC4); 422 date rules as remit.
- Both: deposit row lock; audit `overseas.deposit.remit|refund` (admin actor; ids and amounts only) in the same transaction; return the
  item. Retry-safe through the state machine (a repeat → 409).

## 5. Frontend

- `lib/razorpayCheckout.ts`: the `window.Razorpay` types, `loadRazorpayCheckout()` and `openRazorpayCheckout(order, {description,
  onPaid, onDismiss})` moved from `FeePaymentPanel.tsx`, which keeps identical behaviour.
- `lib/agentApplications.ts`: `AgentDeposit` type, `depositUrl`, labels; `AgentApplicationDetail` gains `deposit` and `payment_available`.
- `AgentApplicationDeposit.tsx` (section "Deposit", after Offer): empty state "No deposit recorded yet." + Record deposit; not required;
  pending (₹ amount, due date, **Pay deposit**, Edit); paid (paid date, paid by, Download receipt); remitted/refunded read-only.
  `payment_available=false` → the Pay button is replaced by "Online payment is unavailable right now. Nothing has been charged."
  (`role="status"`). Pay: in-flight guard, `aria-busy`, "Opening checkout…"; dismissed → "Payment not completed. You can try again.";
  verified → "Payment received. Confirming…" then reload; still pending → "If you were charged, it will appear shortly." + Refresh.
  409 → reload with a notice; 429 → the wait; 502/5xx/401 → existing wording. Read-only when `read_only_reason` is set.
- `AgentApplicationDepositForm.tsx`: Yes/No radios, amount (`inputMode="decimal"`, ₹ prefix), due date; 422 messages at the fields; focus
  first error; Escape cancels; focus returns to the section heading after save, to the button after cancel.
- `/overseas/admin/agent-deposits` page (the `school-transfers` template) + `AdminAgentDepositsPanel.tsx` (the `AgentApprovalPanel`
  pattern): status tabs synced to the URL, pagination, inline remit and refund forms (refund confirms and shows the max), cards stack at
  320 px; loading, empty ("No deposits with this status."), and error-with-Retry (`role="alert"`) states. Nav entry "Agent deposits".
- No new dependency.

## 6. Acceptance criteria → tests

| AC | Statement | Pinned by |
|---|---|---|
| AC1 | Master/Staff start a checkout only for a deposit in their scope; the order amount equals the stored amount | `test_agn_011_checkout.py` (scope 404 for other org / unassigned staff; `create_checkout` called with the stored amount; body amount ignored) |
| AC2 | A signed webhook marks the payment and deposit paid exactly once; a replay is a no-op | `test_agn_011_paid.py` (one receipt, one `deposit_paid` audit; same event id → `already_processed`; a second event id and a later `payment.failed` change nothing) |
| AC3 | A second checkout on a paid deposit → 409 | `test_agn_011_checkout.py` |
| AC4 | Only Overseas Admin sets remitted/refunded; refund ≤ paid | `test_agn_011_admin.py` (Master/Staff/super_admin 403; over-refund 422) |
| AC5 | The receipt shows the payer and the student | `test_agn_011_paid.py` via `tests/pdf_text.py` |
| AC6 | Razorpay unconfigured → UI "payment unavailable", nothing marked paid | `test_agn_011_checkout.py` (200 `configuration_required`, no Payment row); `AgentApplicationDeposit.test.tsx`; Playwright `agn-011-deposit.spec.ts` |

Plus: migration/constraints (`test_agn_011_migration.py`), schemas (`test_agn_011_schemas.py`), PUT rules (`test_agn_011_deposit.py`),
concurrency (`test_agn_011_concurrency.py`), shared-path regressions (`test_agn_011_payments_regression.py`: `/payments/mine`, generic
checkout and admin guards, paid-guard on a student fee), matrix rows in `test_agn_003_matrix.py`. Existing suites that must stay green:
`test_pay_001_stu_010_payment_gateway.py` (needs real Razorpay test secrets — run by the owner), `test_admin_payment_discount.py`,
`test_provider_services.py`, `test_agn_010_*`, `test_agn_013_*`, `test_agn_003_matrix.py`.

## 7. Security

| Threat | Control |
|---|---|
| IDOR | Agent routes resolve through `load_scoped` (404 outside scope); receipt via the application; admin routes role-gated. |
| Role escalation | No agent body carries a status; remit/refund only on the admin router, `overseas_admin` only; matrix tests. |
| Amount tampering | Checkout reads no body; amount from the deposit row; webhook amount cross-checked for deposits. |
| Replay / double credit | Event-id dedup (existing) + paid-guard + deposit `active_payment_id` match under row locks. |
| Double charge | Deposit lock + 15-minute rule; residual (a stale order paid) recorded as an unlinked payment for manual refund. |
| Input | Pydantic `extra="forbid"`, Decimal bounds, date ranges, `clean_free_text` on reference/reason. |
| XSS | React escaping; PDF `drawString`. |
| CSRF | Unchanged (SameSite=Lax cookies, JSON, CORS allowlist; the Idempotency-Key header forces a preflight). |
| SQL injection | ORM only. |
| Secrets | Only `key_id` returned; secrets server-side; provider response bodies not logged. |
| Logs | ids, statuses, field names only — no student names, amounts in audit metadata only. |
| Rate limiting | 10 checkouts / deposit / hour, counted in PostgreSQL (multi-instance safe). |
| Audit | set, checkout, paid, unlinked, remit, refund — each in its write's transaction. |

## 8. Regression risks

1. Paid-guard in the shared webhook/verify (student fees) — covered by the existing PAY-001 tests (owner's full run) and a new student-fee
   regression test that runs without real secrets (monkeypatched settings).
2. `_ensure_receipt` signature unchanged (student name looked up inside); 3 callers untouched.
3. `/payments/mine` filter — student fee rows unaffected (test).
4. AGN-008/010/013 detail shape — additive keys only; existing vitest fixtures tolerate a missing `deposit`.
5. `FeePaymentPanel` refactor — `plainHttpIdempotencyKey.test.tsx` must stay green.

## 9. Out of scope

Partial payments, several refunds, a refund API to Razorpay, deposit notifications/reminders (ang-017), deposit totals on the agent
network page (ang-022), revenue reclassification, multi-currency.
