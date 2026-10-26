# Razorpay go-live runbook (`nehn-022`, `DEC-SCOPE-283`)

This runbook moves the payment gateway from Razorpay **test** mode to **live** mode. Linked from `DEPLOYMENT.md`.

- **Who:** the operations owner (super_admin), with the client's finance contact for steps 6 and 7.
  Who performs the live verification is `NEEDS_CONFIRMATION` (backlog open question).
- **Before you start:** the client's Razorpay account must be **activated for live payments** (KYC done). This is client-owned.
- **Never** paste a key or secret into a ticket, a chat, a log or a screenshot. They live only in the server `.env`.

## What the application enforces

- `RAZORPAY_MODE` is `test` (the default) or `live`. The API, worker and beat check it against the keys **at startup** and refuse to start
  when they do not match:
  - `test`: `RAZORPAY_KEY_ID` must start with `rzp_test_`, or be empty (payments then show "not configured").
  - `live`: `RAZORPAY_KEY_ID` must start with `rzp_live_`, and `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET` must both be set.
  - The error names the variable and the expected prefix, for example
    `RAZORPAY_MODE=live needs a RAZORPAY_KEY_ID starting with rzp_live_`. It never prints a value.
- In test mode, the student **Fee Payments** card and an agency application's **Deposit** section show
  "Test mode: payments here use Razorpay test mode and no real money is charged." Live mode hides it.
- **Admin → Settings** (`/admin/settings`) shows the `Razorpay mode` row (`test mode` / `live mode`) next to the `Razorpay` row
  (`configured` / `not configured`).

## Steps

1. **Verify test mode end to end first.** With `RAZORPAY_MODE=test` and `rzp_test_` keys, pay one student fee and one agency deposit
   with a Razorpay test card. Confirm the receipt and that the webhook marked the payment paid.
2. **Generate live keys.** In the Razorpay Dashboard, switch to **Live Mode** → *Account & Settings → API Keys* → generate a key.
   You get `rzp_live_…` and its secret.
3. **Register the live webhook.** In Live Mode, go to *Account & Settings → Webhooks → Add new webhook*.
   - URL: `https://<production API host>/api/v1/payments/webhooks/razorpay`.
   - Secret: a new random value (for example `openssl rand -hex 32`), different from the test one.
   - Events: `payment.captured` and `order.paid`. These are the two the API marks as paid; other events are stored but not acted on.
4. **Set the server `.env`:**
   ```
   RAZORPAY_MODE=live
   RAZORPAY_KEY_ID=rzp_live_...
   RAZORPAY_KEY_SECRET=...
   RAZORPAY_WEBHOOK_SECRET=<the secret from step 3>
   ```
5. **Recreate the api, worker and beat containers** (prod: `docker compose up -d --no-deps api worker beat`).
   - If one exits at once, read its log (`docker compose logs api | tail`). A mode/key mismatch is reported there by name.
   - Fix the `.env` and recreate again. The old containers are gone, so payments are down until this succeeds; keep step 9 to hand.
6. **Check the indicators.** In Admin → Settings, `Razorpay mode` must say `live mode` and `Razorpay` must say `configured`.
   On a student Fee Payments card the test-mode banner must be gone.
7. **₹1 live test and refund.**
   - As super_admin, create a ₹1 payment due for a staff-owned test student account (`POST /admin/payments`, or the "Create payment
     due" form).
   - Pay it with a real card or UPI. Confirm the receipt in the app and that the payment shows **Captured** in the Razorpay Dashboard.
   - Refund it from the Razorpay Dashboard (*Payments → the payment → Issue refund*).
   - Record the payment id, refund id and time in the QA evidence.
8. **Reconcile.** Compare the day's captured payments in the Razorpay Dashboard (Live) with the app's paid rows.
   - Payments are not tagged test/live (open question, below), so **record the go-live time** in the QA evidence. Every gateway
     payment marked paid before that time was a test payment and must be excluded from revenue, or cleared before launch with the
     owner's approval.
   - Settlement reports come from *Reports → Settlements* in the Razorpay Dashboard.
9. **Rollback.** Set `RAZORPAY_MODE=test` with the `rzp_test_` keys and test webhook secret, then recreate the containers as in step 5.
   Live payments already captured stay in the live Razorpay account; refund them there if needed.

## Open questions (`NEEDS_CONFIRMATION`)

- Should each Payment row record the mode (a `payments.mode` column) so test rows can be filtered from revenue automatically?
  Deferred; step 8 covers it manually.
- Who performs the live verification (step 7), and which card or account is used?
