# ENH-032 — Send app email through the Zoho Mail API (HTTPS) — design

- **Feature ID:** ENH-032 (next free after ENH-031 on `origin/main` @ b47e7a80) — *tentative, recheck `main` before building*
- **Decision:** DEC-SCOPE-225 (tentative; `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` also names 225 as the next free number, so recheck) · extends DEC-NOT-001 (email channel) · **Migration:** none · **New routes:** none (no RBAC row) · **API contract:** `GET /admin/system-status` gains one row
- **Branch / worktree:** `feature/enh-032` in `../enh-032`
- **Status:** DRAFT design, written 2026-10-17 for owner review. Not approved; no code yet.
- **Evidence:** owner request and answers E1–E7 given in a Claude Code session on 2026-10-17 (below), plus connectivity tests run from the dev droplet the same day (§3.1).

## 1. Purpose

Dev (168.144.221.81) and prod (edusphere-prod) cannot send any email: DigitalOcean blocks outbound SMTP on the account (§3.1). App email must instead go out over HTTPS (port 443, which is open) through the **Zoho Mail REST API**, from the existing Zoho Mail mailbox. SMTP stays in the code as the other transport, chosen in `.env`, so local, CI and the Mailpit docs stacks are unchanged and SMTP can be switched back on if DigitalOcean ever lifts the block.

## 2. Owner answers (2026-10-17)

| # | Question | Answer |
|---|---|---|
| E1 | Scope | Add an HTTPS email-API path; the addresses are configurable in `.env`. SMTP stays. |
| E2 | Provider | **Zoho Mail API** (the existing mailbox), not ZeptoMail. |
| E3 | Sender | `info@edusphere.org.uk` is the no-reply sender for all app email, set in `.env`. |
| E4 | Reply-To | **Dropped.** "From and reply same now": no Reply-To setting, no reply hint in the body. Replies go to the From address. |
| E5 | School invites | Keep current behaviour (on SMTP they still carry the Coordinator Reply-To; see E6 for the API). |
| E6 | Per-person replies over the API | The Zoho Mail send API has no documented Reply-To field. Owner **accepted the loss**: over the API, school invites and staff-written emails no longer reply to the Coordinator / staff member. |
| E7 | Staff-written emails (telecaller → lead, recruiter → candidate, partnership → university) | Keep current behaviour (same as E5/E6). |
| E8 | Email that today goes **only** to the empty `EMAIL_WEBHOOK_URL` (password reset, generic and inbound notification emails) | **Include it.** Add real password-reset and generic-notification emails to the mailer so they also send via Zoho. |
| E9 | A Zoho request that times out after the email was handed over (outcome unknown) | **Don't retry; mark failed.** Retry only when the email certainly was not accepted. A duplicate is worse than a visible failure. |
| E10 | Zoho Mail's daily sending limit | **Stop retries at the limit:** a "limit reached" response is a permanent failure with no retry. Document the limit. No counters or pacing. |

## 3. Current state (verified on `origin/main` @ b47e7a80)

### 3.1 Why email fails today (dev droplet, 2026-10-17)

- `~/edusphere/.env` is the file compose loads, and the containers were recreated after each edit, so settings were not the problem.
- ufw is inactive. No DO Cloud Firewall is attached to the dev droplet. `edusphere-prod-fw` (prod only) allows all outbound traffic.
- TCP to ports 25/465/587 timed out for `smtppro.zoho.in` (103.103.197.104), `smtppro.zoho.com` (204.141.43.24) and `smtp.gmail.com` (192.178.211.109). TCP 443 to `www.google.com` and `mail.zoho.in` connected.
- Conclusion: DigitalOcean's account-level SMTP block. Prod is in the same account; not tested there, but assumed blocked.

### 3.2 Code

- `apps/api/app/services/mailer.py` composes every email as a stdlib `EmailMessage` and sends it through **one** function, `_send_sync(msg)` (`smtplib.SMTP` → optional STARTTLS → login → `send_message`).
- The emails that go through it:
  - `send_school_invite_email`: From is "Coordinator via EduSphere"; Reply-To is the Coordinator.
  - `send_parent_notification_email`: From is "School via EduSphere".
  - `send_welcome_email`: From is "EduSphere".
  - `send_bdm_reminder_email`: From is "EduSphere".
  - `lead_email_message`, the shared builder for staff-written email: From is "Staff via EduSphere"; Reply-To is the staff member. It is used by `notifications/lead_email.py`. `recruiter_email.py` and `university_email.py` reuse that module's `_send`.
- The four `send_*` functions return `("not_configured" | "sent" | "failed", error)` and catch every exception as `failed` with `str(exc)[:500]`, which is persisted.
- `notifications/lead_email._send` classifies errors for retries:
  - transient → `retry`: `OSError`, `SMTPException`, SMTP 4xx
  - permanent → `failed`: SMTP 5xx, refused recipient, `ValueError`
  - no SMTP configured → `("failed", "not_configured")`
- The "is email configured" check is repeated:
  - inline as `settings.smtp_host and settings.smtp_from_email` in the four `send_*` functions
  - as `mailer.smtp_configured()` in `lead_email`, `interviews`, `lead_messages`, `profile_sharing`, `recruiter_messages` and `university_comms`
- Every HTML email embeds the logo as an inline `cid:edusphere-logo` part (`_attach_logo`). The comment says a hosted URL was rejected because dev hosts are not publicly reachable.
- `services/meetings.py::_zoho_access_token` already refreshes a Zoho OAuth token. It uses `httpx`, posts the secrets as a **form body** and turns errors into a generic message. It uses `ZOHO_CLIENT_ID/SECRET/REFRESH_TOKEN` and `ZOHO_ACCOUNTS_URL` (`https://accounts.zoho.in` on dev).
- **Webhook-only email.** These never reach `mailer.py`. They go to `integrations.send_notification("email", payload)`, which POSTs JSON to `EMAIL_WEBHOOK_URL` (empty on dev, so they never send):
  - **Password reset:** `api/auth.py:383`, template `password_reset`, a 30-minute `PasswordResetToken`. The reset pages are `/admin`, `/it` and `/overseas` + `/reset-password`. `provisioning._set_password_url` already picks the right portal segment.
  - **Generic and inbound notification emails:** `notifications/delivery.py::_send_email`. The `else` branch handles generic `_notify_user` items; `kind == "inbound"` handles inbound university email. The school branch already tries the mailer first and falls back to the webhook when it reports `not_configured`.
  - **Parallel webhook copies:** `api/schools.py:161` (school invite) and `services/provisioning.py:122` (welcome). Each runs alongside the mailer send, for parity.
- `delivery.py` marks every `failed` result as `transient=True`, so the four direct mailers' failures are retried by the delivery sweeper.
- `GET /admin/system-status` (`api/admin.py`) lists integrations, but has no email row.
- `httpx` is already a dependency. `tests/test_enh_014_twilio.py` shows the existing pattern for faking HTTP.

### 3.3 Zoho Mail API (docs, 2026-10-17)

- **Send:** `POST {mail base}/api/accounts/{accountId}/messages`
  - Header: `Authorization: Zoho-oauthtoken <access token>`
  - Scope: `ZohoMail.messages.CREATE`
  - JSON body: `fromAddress` (must belong to the authenticated account, i.e. the mailbox or one of its aliases), `toAddress`, `ccAddress`, `bccAddress`, `subject`, `content`, `mailFormat` (`html` | `plaintext`), `askReceipt`, `encoding`, scheduling fields, and `attachments` (`storeName` / `attachmentPath` / `attachmentName`, from a separate Upload Attachment call).
- **No Reply-To field** is documented, and no inline-image option is documented.
- Sources: https://www.zoho.com/mail/help/api/post-send-an-email.html, https://www.zoho.com/mail/help/api/post-send-email-attachment.html

## 4. Design

### 4.1 Configuration (`core/config.py`, `.env.example`, `apps/api/.env.example`)

| Setting | Default | Notes |
|---|---|---|
| `EMAIL_TRANSPORT` | `smtp` | `smtp` or `zoho_api`. Any other value fails fast at startup with a clear message. |
| `SMTP_FROM_EMAIL` | (existing) | **The From address for both transports** (E3: `info@edusphere.org.uk`). Kept under its current name so existing `.env` files keep working. *My call.* |
| `ZOHO_MAIL_CLIENT_ID` | none | Separate from the Zoho Meeting client. *My call:* a Meeting token problem must not stop email, and the scopes stay minimal. |
| `ZOHO_MAIL_CLIENT_SECRET` | none | secret |
| `ZOHO_MAIL_REFRESH_TOKEN` | none | secret; scope `ZohoMail.messages.CREATE` |
| `ZOHO_MAIL_ACCOUNT_ID` | none | the mailbox's numeric account ID |
| `ZOHO_MAIL_API_BASE` | `https://mail.zoho.com` | `https://mail.zoho.in` on dev/prod (India data centre) |
| — | — | The OAuth host reuses the existing `ZOHO_ACCOUNTS_URL`. *My call:* one Zoho org, one data centre. |

SMTP settings are unchanged.

### 4.2 One "is email configured" check

Replace the inline checks and `smtp_configured()` with a single `mailer.email_configured()`:
- `smtp`: `smtp_host` and `smtp_from_email` are both set (today's rule).
- `zoho_api`: `smtp_from_email` and all four `ZOHO_MAIL_*` credentials are set.

Keep `smtp_configured` as an alias of it so the six call sites still read correctly, or rename them all. That's the builder's choice. The `not_configured` outcome is unchanged.

### 4.3 One transport seam

`_send_sync(msg)` becomes the dispatcher:
- `smtp` → today's `smtplib` code, unchanged. This includes Reply-To headers, so SMTP behaviour is exactly as now (E5/E7).
- `zoho_api` → `_zoho_send(msg)`, which turns the `EmailMessage` into the API payload:
  - `fromAddress` ← the `From` header. Whether Zoho accepts a display name (`"Name <addr>"`) is **to verify live** (§5.3). If it rejects one, send only the bare `SMTP_FROM_EMAIL`.
  - `toAddress` ← `To`; `subject` ← `Subject`.
  - `content` / `mailFormat` ← the HTML part (`html`), or else the plain-text part (`plaintext`).
  - `Reply-To` is **dropped** (E4/E6).
  - **Logo:** the HTML references `cid:edusphere-logo`, which no API part will satisfy. Unless the live check (§5.3) finds that an inline upload works, strip the logo `<img>` from the HTML on this path so recipients never see a broken image. *My call;* the builder may implement inline upload if it is proven.
- No automatic SMTP-to-API failover. *My call:* on DigitalOcean the SMTP attempt would only add a timeout to every send.
- The function stays synchronous (callers already wrap it in `asyncio.to_thread`). Use `httpx.Client` with a timeout around 15 s.

### 4.3a New mailer emails for webhook-only paths (E8)

- **Password reset:** add `send_password_reset_email(to_email, recipient_name, reset_url, expires_minutes)`.
  - It uses the same HTML/text and logo pattern as `send_welcome_email`, with From "EduSphere".
  - `reset_url` is built from configuration via the same portal-segment rule as `_set_password_url`, never from the request Host. Factor that rule out and share it.
  - `auth.py` forgot-password calls it. If it returns `not_configured`, fall back to today's webhook call. This is the school-branch pattern in `delivery.py`.
  - The `NotificationDelivery` row records the result of whichever path ran.
  - The response body and the development-only token exposure are unchanged. The reset token appears only in the emailed link, never in logs or stored errors.
- **Generic and inbound notification email:** add `send_generic_notification_email(to_email, recipient_name, title, body, action_url)` with From "EduSphere". It renders like the parent notification, but without a school name.
  - In `delivery._send_email`, both the `inbound` branch and the generic `else` branch call it first and fall back to the webhook on `not_configured`, as the school branch already does.
  - `action_url` handling copies the parent-notification email.
- **Parallel webhook copies** (`schools.py:161`, `provisioning.py:122`) are **unchanged.** They are a separate integration, and the mailer send beside them already covers the email. *My call.*
- These new emails go through `_send_sync`, so they work on both transports.

### 4.4 OAuth token

- Refresh at `{ZOHO_ACCOUNTS_URL}/oauth/v2/token` with `grant_type=refresh_token`. Send the secrets as a **form body, never as query parameters**, so they cannot appear in an error URL.
- Cache the access token in-process until shortly before `expires_in`, guarded by a lock. Zoho rate-limits token refreshes, so don't refresh per email. The api and each worker process keep their own cache; that's fine.
- If a send gets 401 or an invalid-token response, drop the cache, refresh once and retry once.

### 4.5 Errors and retries

Rule (E9): retry **only** when Zoho certainly did not accept the email.

The API path raises one of two exception types:
- `EmailTransientError` — the email was definitely not accepted:
  - a connect error or connect timeout (the request never reached Zoho)
  - HTTP 5xx or a non-limit 429 response (Zoho answered and refused)
  - a transient failure while refreshing the token (no send was attempted)
- `EmailPermanentError` — no retry:
  - a **read/write timeout or dropped connection after the request was sent** (the outcome is unknown, so a retry could duplicate: E9)
  - other 4xx
  - Zoho's daily-limit / "limit reached" response (E10). The exact code or message is **to verify** against Zoho's error docs or a live response; match narrowly and record it in INTEGRATION_CONTRACTS.
  - a malformed payload
  - a token refresh refused with `invalid_grant` / `invalid_client`

Callers:
- `lead_email._send`: add `EmailTransientError` → `retry` and `EmailPermanentError` → `failed`, next to the existing smtplib branches. Recruiter and university email inherit this.
- The four existing `send_*` functions and the two new ones still return `failed` for any exception. They must also expose whether that failure may be retried, so `delivery._send_email` sets `transient` only for `EmailTransientError`. Today it sets it for every `failed`. The mechanism is the builder's call: for example a third tuple element, or a retryable flag the caller reads. It must not change the persisted status values.
- **SMTP path: unchanged** (AC2). Today's retry behaviour stays as it is.

Stored error text must never contain the token, client secret, refresh token or the `Authorization` header. Record only the exception type and Zoho's error code/message.

### 4.6 Admin system status

Add a row to `GET /admin/system-status`: `{"service": "Email delivery", "status": "Zoho Mail API" | "SMTP" | "not configured"}`. *My call;* it lets an admin see the mode without SSH.

### 4.7 Out of scope / NEEDS_CONFIRMATION

- Out of scope:
  - Reply-To in any form (E4)
  - ZeptoMail, SES and other providers
  - attachments other than the logo
  - bounce/open tracking
  - inbound email
- Also out of scope:
  - send counters, pacing of bulk sends (E10)
  - changing the parallel webhook copies (§4.3a)
- **Risk (NEEDS_CONFIRMATION):** Zoho Mail limits how many emails a mailbox may send per day. The limit depends on the plan and was not confirmed. A large bulk send (for example a school roster invite) could hit it, and Zoho may then throttle or suspend the mailbox, which would also stop the owner's own mail on `info@`. The build only stops retries piling on (E10). Owner to check the plan's limit; the deploy notes record it.
- The DigitalOcean SMTP-unblock ticket is still worth filing. If it is approved, `EMAIL_TRANSPORT=smtp` works again with no code change.

## 5. Testing

### 5.1 Backend (fake Zoho over HTTP, following `test_enh_014_twilio.py`)

1. Under `zoho_api`, each of the 5 email types posts one request to `/api/accounts/{id}/messages` carrying `fromAddress` = `SMTP_FROM_EMAIL`, the right `toAddress`/`subject`, `mailFormat=html`, an HTML body with no `cid:` reference, and no reply-to anywhere.
2. Token: the first send refreshes; later sends reuse the cached token. A 401 triggers one refresh plus one retry, and a second 401 → permanent failure.
3. Error mapping (E9, E10):
   - connect error, connect timeout, non-limit 429 and 5xx → lead email `retrying`, and delivery `transient`
   - read timeout after sending, 400, and the limit-reached response → `failed` with no retry, and delivery not transient
   - every `send_*` → `failed` with a sanitised error
3a. New emails (E8):
   - Forgot-password sends `send_password_reset_email` with the right portal link. With email not configured it falls back to the webhook, and the response is unchanged.
   - Generic and inbound notifications go through the mailer, with the webhook fallback when email isn't configured.
   - The parallel webhook copies in invite and welcome are still called.
4. A stored error never contains the token or secrets.
5. `email_configured()`:
   - `zoho_api` with a missing `ZOHO_MAIL_*` value → `not_configured`, with no HTTP call
   - `smtp` follows today's rule
6. An invalid `EMAIL_TRANSPORT` fails at startup.
7. **SMTP regression:** under `EMAIL_TRANSPORT=smtp`, the existing mailer and lead-email tests pass unchanged (Reply-To still set).
8. System status shows the right email row for each mode.

Per the regression cadence, run the lite backend set for this feature, not the full suite.

### 5.2 Static checks

ruff, mypy, and the web build (it isn't affected, but run it anyway).

### 5.3 Live check on dev (after the owner adds the credentials)

1. One real send to an address the owner chooses.
2. Confirm it arrives from `info@edusphere.org.uk` with the expected display name, or note that Zoho drops it.
3. Check the logo: either embedded or cleanly absent.
4. Reply to it and confirm the reply goes to `info@`.
5. Record the result in the QA evidence.

## 6. Setup and docs to update

- **Owner setup**, written into `docs/architecture/DEPLOYMENT.md` and the prod setup guide:
  1. In `https://api-console.zoho.in`, create a Server-based client.
  2. Generate a refresh token with the scopes `ZohoMail.messages.CREATE,ZohoMail.accounts.READ`.
  3. Find the account ID with `GET https://mail.zoho.in/api/accounts`.
  4. Make sure `info@edusphere.org.uk` is that mailbox or one of its aliases.
  5. Set `EMAIL_TRANSPORT=zoho_api`, the four `ZOHO_MAIL_*` values and `ZOHO_MAIL_API_BASE=https://mail.zoho.in`.
  6. Recreate the api, worker and beat containers.
- Other docs to update:
  - `docs/architecture/INTEGRATION_CONTRACTS.md`: an email transport section
  - `ADRS.md` or the decision register: DEC-SCOPE-225
  - `API_CONTRACT.md`: the system-status row
  - both `.env.example` files
  - the backlog item, catalog and RTM entries, as for earlier ENH items

## 7. Acceptance criteria (draft)

- **AC1** With `EMAIL_TRANSPORT=zoho_api` and the credentials set, every mailer email is delivered through the Zoho Mail API over HTTPS, from `SMTP_FROM_EMAIL`. That covers the existing five types plus password reset and generic/inbound notifications.
- **AC1a** Password reset and generic/inbound notifications send a real email whenever email is configured, on either transport. When it isn't, they keep today's webhook behaviour (E8).
- **AC4a** An outcome-unknown timeout and Zoho's limit-reached response are never retried (E9, E10).
- **AC2** With `EMAIL_TRANSPORT=smtp` (the default), behaviour is identical to today, including Reply-To headers.
- **AC3** Missing API credentials give the existing `not_configured` outcome and never crash the triggering action.
- **AC4** Transient API errors retry and permanent ones fail, both through the existing lead-email retry logic. The four direct mailers record `failed`.
- **AC5** The access token is cached and refreshed once on a 401. No secret ever appears in logs, stored errors or responses.
- **AC6** No email sent through the API shows a broken logo image.
- **AC7** `GET /admin/system-status` reports the email transport.
- **AC8** A live send on dev is verified and recorded (§5.3).
