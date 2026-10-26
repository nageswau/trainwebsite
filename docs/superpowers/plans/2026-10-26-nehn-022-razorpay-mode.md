# nehn-022 implementation plan — Razorpay test/live mode

Design: `docs/superpowers/specs/2026-10-26-nehn-022-razorpay-mode-design.md`. TDD for each task: RED, then GREEN, then refactor.

1. **Config check (M1-M3).** `apps/api/tests/test_nehn_022_razorpay_mode.py` builds `Settings(_env_file=None, ...)` directly and covers:
   the default is test; live with `rzp_test_` fails; test with `rzp_live_` fails; live without the secret or webhook secret fails;
   an unknown mode fails; live with all three passes; test with no keys passes; and the error text never contains the key or secret.
   Implement it with a `model_validator(mode="after")` in `app/core/config.py`.
2. **Mode read (M4).** Tests: anonymous gets 401, and a signed-in student gets `{"mode": ...}` that follows `settings.razorpay_mode`.
   Implement `GET /payments/mode` in `app/api/payments.py`, declared before any `/{payment_id}` route.
3. **Admin row (M5).** Test: system-status has a `Razorpay mode` row, `test mode` or `live mode`. Add it in `app/api/admin.py`.
4. **Banner (M6).** Vitest for `components/PaymentModeBanner.tsx`: it shows in test, hides in live, and renders nothing while loading
   or on a failed read. Render it in `FeePaymentPanel` and in `AgentApplicationDeposit` when Pay is offered.
5. **Config surfaces.** Add `RAZORPAY_MODE=test` to `.env.example` and `RAZORPAY_MODE: "test"` to `docker-compose.ci.yml`.
6. **Docs.** The runbook (M8), a `DEPLOYMENT.md` link, a DEC-SCOPE entry, an API § addendum, an RBAC § entry and the backlog status.
   Write them after merging main, so the numbers are free.
7. **E2E.** `tests/e2e/nehn-022-razorpay-mode.spec.ts`: a student sees the banner on fees (stack in test mode), and the admin Settings
   page shows `Razorpay mode` / `test mode`. Live-hidden is covered by vitest, because flipping the stack to live needs real live keys.
