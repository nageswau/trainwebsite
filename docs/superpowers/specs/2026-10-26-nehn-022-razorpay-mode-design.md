# nehn-022 — Razorpay test/live mode switch and go-live checklist (design)

**Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-022` (§7 L153-156; `UNVERIFIED` backlog).
**Dependencies:** none (backlog §6.2 Group 1). The live switch itself needs the client's live Razorpay account and KYC (client-owned).
The owner pre-authorised the builder's recommended answers; every default below is `NEEDS_CONFIRMATION`.

## Intent

Moving payments from Razorpay test to live must be one explicit, checked step, not something implied by whichever keys someone pasted.
Today the mode is only implied by the key prefix (`rzp_test_` / `rzp_live_`), nobody on a payment screen can tell test from live, and
there is no go-live procedure.

## Goals (the backlog's acceptance criteria)

1. `RAZORPAY_MODE=live` with `rzp_test_` keys stops the API at startup with a clear error (and the reverse).
2. Test mode shows a banner on the payment screens, and live mode hides it.
3. A go-live runbook exists and is linked from the deployment docs.
4. An admin system-status indicator shows the mode.

## Non-goals and anti-goals

- No change to checkout, verify, webhook or receipt behaviour, and no new payment provider.
- A key, secret or webhook secret never appears in a response, a log line or a startup error (anti-goal: a failed boot that prints secrets).
- No provider-specific infrastructure (`DEC-INFRA-001` still governs).

## Builder's defaults (`NEEDS_CONFIRMATION`)

- **M1. Setting.** `RAZORPAY_MODE` is `test` or `live` and defaults to `test`, so dev, CI and every existing `.env` keep working.
  Any other value fails startup.
- **M2. Startup check.** In `test` mode, a configured `RAZORPAY_KEY_ID` must start with `rzp_test_`, and no keys at all is fine.
  In `live` mode, `RAZORPAY_KEY_ID` must start with `rzp_live_`, and `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET` must be set,
  because a live switch with no webhook secret leaves payments unconfirmed when the browser verify step never returns.
  A mismatch raises during `Settings()`, so the API, worker and beat all refuse to start.
- **M3. No secrets in errors.** `Settings` sets `hide_input_in_errors=True`, and the messages name only variables and prefixes,
  never values.
- **M4. Mode read.** `GET /api/v1/payments/mode` returns `{"mode": "test"|"live"}` to any signed-in user (401 without a session).
  It is non-secret, read-only and has no side effects. The browser cannot reach `/health`, which is outside the `/api` proxy.
- **M5. Admin indicator.** `GET /api/v1/admin/system-status` gains a `Razorpay mode` row (`test mode` / `live mode`). It renders on the
  existing Settings table (`/admin/settings`), so no new UI is needed.
- **M6. Banner.** A shared `PaymentModeBanner` reads the mode once and renders a `.form-warning` line only when the mode is `test`:
  "Test mode: payments here use Razorpay test mode and no real money is charged."
  - It shows in the student Fee Payments card, and in an agency application's Deposit section whenever *Pay deposit* is offered.
  - While the mode is loading, or if the read fails, it renders nothing. The server-side startup check is the real guarantee.
  - It is a plain `<p>` with no live-region role, so other specs' page-wide `getByRole("status")` checks don't collide with it.
- **M7. No `payments.mode` column (deferred).** The backlog marks the column optional. Test-mode rows in a production DB are handled by
  the runbook's cut-over step instead: record the go-live time and exclude earlier gateway rows, or clear them before launch.
  Adding the column is a later decision.
- **M8. Runbook.** The runbook lives at `docs/architecture/RAZORPAY_GO_LIVE.md` and is linked from `DEPLOYMENT.md`. It covers live keys,
  the webhook secret, webhook URL registration, a ₹1 live payment and refund, reconciliation, and rollback to test.
  Who performs the live verification is the client's call (open question).

## Regression risks

- The check runs when `app.core.config` is imported. Every existing environment either has no keys or has `rzp_test_` keys and the
  default `test` mode, so it is unaffected. CI sets `RAZORPAY_MODE: "test"` explicitly.
- Tests that `monkeypatch.setattr(settings, ...)` bypass validation, because `validate_assignment` is off. That is unchanged.
