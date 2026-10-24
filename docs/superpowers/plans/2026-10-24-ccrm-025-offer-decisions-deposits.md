# ccrm-025 Offer decisions and deposits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Counselor/Admin record the student's decision on the current offer (accept / decline, auto-expire) and a manual university
deposit record on any application.

**Architecture:** Decision columns on `application_offers` written by `services/application_offers.py`; decline delegates to
`services/application_outcomes.record`; a daily beat job expires undecided offers; a new `application_deposit_records` table with
GET/PUT routes beside the offer routes. Web: the existing `ApplicationOffersPanel` plus a new `ApplicationDepositPanel`.

**Tech Stack:** FastAPI + async SQLAlchemy + Alembic + Celery beat; Next.js/React + vitest + Playwright.

**Spec:** `docs/superpowers/specs/2026-10-24-ccrm-025-offer-decisions-deposits-design.md`

## Global Constraints

- Numbers: migration `0178_offer_decisions_deposits` (down `0177_visa_lifecycle`), `DEC-SCOPE-255`, API §12FH, RBAC §2.170.
- Nothing in `services/agent_deposits.py`, `api/agent_deposits.py` or payments changes.
- Never return `file_url`; audit metadata carries no amounts or free text.
- Tests run in docker (`api-test` / `web-test`, memory worktree-api-test-mount-path); lite set only.

## Review Focus

- Decline when the application is on hold → 409 (on hold refuses stage moves) — test in Task 3.
- Accept a superseded offer id → 409, other application's offer id → 404 — Task 3.
- Job on an application whose row another session holds → skipped, no error (SKIP LOCKED) — covered by rerun test in Task 4.
- Deposit `required=false` with an amount → 422; paid status without `paid_on` → 422 — Task 5.
- Agency application with an AGN-011 deposit → PUT 409, GET shows `agency_deposit` — Task 5.

---

### Task 1: Fix the shadowed `_not_future`
**Files:** Modify `apps/api/app/schemas.py` (rename the 2-arg profile helper to `_profile_not_future`, its 2 callers).
- [ ] RED: run `tests/test_ccrm_023_offers.py` → fails with TypeError/500. GREEN: rename, rerun → pass. Commit.

### Task 2: Model + migration
**Files:** `app/models.py` (ApplicationOffer `decision`, `decision_date`, `decided_by_id` + CHECKs; `APPLICATION_OFFER_DECISIONS`;
`ApplicationDepositRecord`, `DEPOSIT_RECORD_STATUSES`), `alembic/versions/0178_offer_decisions_deposits.py` (create-if-missing idiom,
repeats the constants), `tests/test_ccrm_025_migration.py` (chains after 0177, single head, constants equal, round trip; the previous
single-head test in `test_ccrm_026_migration.py` keeps passing).

### Task 3: Decision route
**Interfaces produced:** `offers.decide(user, app, offer, decision_date) -> None` (accept), `offers.other_accepted(db, app) -> list[dict]`,
view keys `decision`, `decision_label`, `decision_date`, `decided_by`; schema `OfferDecisionSet`; route
`POST /{application_id}/offers/{offer_id}/decision`; `application_outcomes.record` sets the active offer's decision on `offer_declined`.
**Tests** `tests/test_ccrm_025_decisions.py`: accept (decision, sub-status, history, audit, student notice), idempotent repeat,
decline → outcome + decision + terminal, `/outcome` offer_declined also sets the decision, D1 warning lists the other application,
superseded 409, foreign offer 404, future/before-issue date 422, decline without reason 422, other counselor 403, student 403,
on hold 409, agency application notifies the agency.

### Task 4: Expiry job
**Interfaces:** `offers.expire_offers(db, today: date) -> int`, `offers.run_offer_expiry() -> int`, `close(user: User | None, …)`,
`agent_notifications.offer_changed(db, app, actor: User | None, title)`; worker task `expire_offers_task` + beat entry.
**Tests** (same file): past-deadline considering offer expires once (rerun 0), accepted / no-deadline / future-deadline / on-hold
untouched, counselor + student notified.

### Task 5: Deposit record
**Interfaces:** `services/application_deposit_records.py` (`values_of`, `save`, `view`, `summary`), schema `DepositRecordSave`,
routes `GET/PUT /{id}/deposit`, `POST /{id}/deposit-receipts` (shared upload helper with offer letters).
**Tests** `tests/test_ccrm_025_deposits.py`: GBP record on a direct app with receipt, prefill from offer, identical 200 unchanged,
validation 422s, foreign receipt 422, AGN-011 deposit 409 + read-only GET, on hold allowed, closed 409, scope 403s, no `file_url`.

### Task 6: Web
**Files:** `lib/applicationOffers.ts` (decision types/labels/urls, deposit types/urls), `components/ApplicationOffersPanel.tsx`
(decision line + accept/decline forms), `components/ApplicationDepositPanel.tsx`, vitest `tests/components/ApplicationOfferDecision.test.tsx`,
`tests/components/ApplicationDepositPanel.test.tsx`, e2e `tests/e2e/ccrm-025-offer-decision-deposit.spec.ts`. tsc + eslint + build.

### Task 7: Docs
DEC-SCOPE-255 in `PRODUCT_DECISION_REGISTER.md`, API §12FH, RBAC §2.170, data model, RTM, backlog status line.
