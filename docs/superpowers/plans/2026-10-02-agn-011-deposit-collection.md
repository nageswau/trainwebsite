# AGN-011 Deposit collection through Razorpay — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline, owner's choice in-session). Steps use `- [ ]`.

**Goal:** an agency Master/Staff records a deposit on an application and pays it through EduSphere's Razorpay checkout; the signed
webhook (or verify) marks it paid exactly once; the receipt names payer and student; Overseas Admin records remittance and refunds.

**Architecture:** new `application_deposits` table; every pay attempt is a payer-owned `Payment` (`reference_type="agent_deposit"`);
the existing checkout service, verify, webhook, invoice and receipt are reused through one paid hook in `payments.py`.

**Spec:** `docs/superpowers/specs/2026-10-02-agn-011-deposit-collection-design.md` (decisions D1–D8, AC1–AC6).

## Global constraints

- Errors are FastAPI `{"detail": "..."}` with the exact messages of spec §4.
- Agent writes: org lock → application lock → deposit lock → payment lock; one commit per transaction; nothing written on a no-op.
- Audit/log metadata: ids, statuses, field names; amounts only in deposit audit rows; never names, signatures, provider bodies.
- No new dependency. No `payments` schema change. Existing response shapes only gain keys.
- Lite tests only (the owner runs the full suites). Backend:

```bash
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn011 --profile ci run --rm \
  -v "$PWD/apps/api:/app" api-test sh -c "alembic upgrade head >/dev/null && python -m pytest -q <files>"
```

  Web: `cd apps/web && npx vitest run <files>`, `npx tsc --noEmit`, `npx eslint <files>`.
- Tests that need Razorpay monkeypatch `settings.razorpay_key_id/_key_secret/_webhook_secret` and `payments.create_checkout`; none
  calls Razorpay.

## Review focus

1. Webhook for a deposit whose checkout was replaced → payment `paid`, deposit unchanged, unlinked audit (spec §4.5).
2. `payment.failed` after `payment.captured` (different event id) → still `paid` (D2) — for a student fee too.
3. Two members' checkouts at once → one `ready`, one 409; no deadlock with a concurrent webhook.
4. Provider error → 502, payment `cancelled`, deposit's `active_payment_id` cleared, nothing charged.
5. Staff of the same agency for an unassigned student → 404 on every deposit route.

---

### Task 1: Model, constraints, migration 0063
**Files:** `apps/api/app/models.py` (`ApplicationDeposit`), `apps/api/alembic/versions/0064_application_deposits.py`,
test `apps/api/tests/test_agn_011_migration.py`.
- [ ] RED: chain/head (0063 on 0062, single head); table + unique application FK exist; CHECKs reject: status `maybe`, currency `USD`,
  required with null amount, amount 0, not_required with required=true, paid without `paid_payment_id`, partial refund columns.
- [ ] GREEN: model + guarded create-if-missing migration; downgrade refuses while rows exist.
- [ ] Commit `feat(agn-011): application_deposits table and migration 0063`.

### Task 2: Schemas
**Files:** `apps/api/app/schemas.py` (`AgentDepositSave`, `DepositRemit`, `DepositRefund`), test `test_agn_011_schemas.py`.
- [ ] RED: extra keys (`currency`, `status`) → error; not required with amount → error; required without amount → error; 0, 3 dp,
  > 99,999,999.99 → error; reference/reason blank or too long → error; refund amount 0 → error.
- [ ] GREEN: models with `extra="forbid"`, `Decimal` `Field`, `_application_date`, `clean_free_text`.
- [ ] Commit.

### Task 3: Deposit service, PUT route, detail block
**Files:** create `apps/api/app/services/agent_deposits.py`, `apps/api/app/api/agent_deposits.py`; modify
`services/agent_applications.py` (`detail` gains `deposit`, `payment_available`), `main.py` (register routers),
`services/staff_activity.py` (allowlist); helper `tests/agn011_helpers.py`; test `test_agn_011_deposit.py`.
- [ ] RED: Master and assigned Staff create/update (200, audit `overseas.application.deposit`, no amount in metadata); unchanged → no
  audit; other org / unassigned staff → 404; withdrawn/archived → 409; paid → 409; amount change cancels the active payment; detail
  carries `deposit` null before, shape after, `payment_available` follows settings.
- [ ] GREEN: implement per spec §4.2–4.3.
- [ ] Commit.

### Task 4: Shared payments path — paid hook, guards, receipt student name
**Files:** `apps/api/app/api/payments.py`, `apps/api/app/api/admin.py` (two guards), `apps/api/app/services/billing_documents.py`;
test `test_agn_011_payments_regression.py`.
- [ ] RED (secrets monkeypatched): student-fee webhook `payment.captured` then `payment.failed` (new event id) → stays `paid`, one
  receipt; verify on a paid payment → no second receipt; `/payments/mine` hides `agent_deposit`, keeps fees; generic checkout on a
  deposit payment → 409; admin create with `agent_deposit` → 422; discount on it → 409; receipt PDF text has `Student:` only when given.
- [ ] GREEN: `_mark_paid` + row locks (deposit then payment); `student_name` keyword; filters and guards.
- [ ] Commit.

### Task 5: Checkout route
**Files:** `api/agent_deposits.py`, `services/agent_deposits.py`; tests `test_agn_011_checkout.py`, `test_agn_011_concurrency.py`.
- [ ] RED: unconfigured → 200 `configuration_required`, no Payment; ready → Payment owned by payer with stored amount, `create_checkout`
  called with it (a body amount is ignored), invoice, audits; same key replay → same order, `key_id` present; same key in flight → 409;
  other member < 15 min → 409, ≥ 15 min → replaces (old `cancelled`); paid → 409; not required → 409; no key → 422; 10/hour → 429;
  provider `httpx.HTTPError` → 502, payment `cancelled`, `active_payment_id` null; scope 404s. Concurrency: two members gathered →
  [200, 409].
- [ ] GREEN: three-step flow of spec §4.4.
- [ ] Commit.

### Task 6: Paid path for deposits + receipt route
**Files:** `services/agent_deposits.py` (`on_payment_paid`), `api/agent_deposits.py` (receipt); test `test_agn_011_paid.py`.
- [ ] RED: signed webhook → payment and deposit paid, one `deposit_paid` audit, receipt PDF has payer and student (AC2, AC5); same event
  id → `already_processed`; another event id → no second audit; verify path same; replaced checkout paid → unlinked audit, deposit
  pending; amount mismatch → unlinked; receipt route: in-scope Staff 200, other org 404, unpaid 404.
- [ ] GREEN.
- [ ] Commit.

### Task 7: Admin list, remit, refund; matrix
**Files:** `api/agent_deposits.py` (`admin_router`), `services/agent_deposits.py`; tests `test_agn_011_admin.py`,
`test_agn_003_matrix.py` (rows).
- [ ] RED: list paginated + status filter, `unlinked_paid_payments`; remit from paid; refund from paid and remitted; over-refund 422;
  wrong state 409; future/before-paid date 422; Master, Staff, super_admin → 403 on remit/refund; super_admin list 200; agent list 403;
  audits with the admin actor. Matrix: PUT deposit and checkout in `BOTH_ALLOWED`.
- [ ] GREEN.
- [ ] Commit.

### Task 8: Web — shared Razorpay checkout lib
**Files:** create `apps/web/lib/razorpayCheckout.ts`; modify `components/FeePaymentPanel.tsx`; tests
`tests/lib/razorpayCheckout.test.ts`, existing `tests/components/plainHttpIdempotencyKey.test.tsx`.
- [ ] RED: lib test (loader resolves when `window.Razorpay` exists; open passes order fields; dismiss calls back).
- [ ] GREEN: move code; FeePaymentPanel imports it; idempotency test still green.
- [ ] Commit.

### Task 9: Web — deposit block and form
**Files:** `lib/agentApplications.ts`, create `components/AgentApplicationDeposit.tsx`, `components/AgentApplicationDepositForm.tsx`,
modify `components/AgentApplicationDetail.tsx`; test `tests/components/AgentApplicationDeposit.test.tsx`.
- [ ] RED: empty state; pending shows amount/due/Pay; `payment_available=false` → unavailable text, no Pay button; Pay sends a UUID
  `Idempotency-Key`; `configuration_required` → unavailable text; 409 → notice; paid → receipt button; read-only hides actions; form
  422 shows the field message; Escape cancels.
- [ ] GREEN.
- [ ] Commit.

### Task 10: Web — admin Agent deposits
**Files:** create `app/overseas/admin/agent-deposits/page.tsx`, `components/AdminAgentDepositsPanel.tsx`; modify `lib/navigation.ts`;
test `tests/components/AdminAgentDepositsPanel.test.tsx`.
- [ ] RED: loads list, empty state, error + Retry, tab change refetches, remit posts and updates the row, refund over max shows the 422
  message, confirm step.
- [ ] GREEN.
- [ ] Commit.

### Task 11: Playwright
**Files:** `apps/web/tests/e2e/agn-011-deposit.spec.ts`.
- [ ] Record deposit as Master → "payment unavailable" in CI (no keys) → admin page lists nothing paid; 320 px layout check.
- [ ] Commit (run by the owner / browser QA session).

### Task 12: Docs and traceability
**Files:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-058`), `docs/architecture/API_CONTRACT.md`, `DATA_MODEL.md`,
`RBAC_MATRIX.md`, `THREAT_MODEL.md`, `SECURITY_CONTROLS.md`, `INTEGRATION_CONTRACTS.md`, `docs/quality/RTM.md`,
`docs/delivery/AGENT_CRM_BACKLOG.md` (status: implemented, pending browser QA + review — **not COMPLETE**).
- [ ] Commit.
