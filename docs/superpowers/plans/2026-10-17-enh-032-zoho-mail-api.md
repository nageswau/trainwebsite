# ENH-032 Zoho Mail API email transport — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send all app email through the Zoho Mail REST API over HTTPS when `EMAIL_TRANSPORT=zoho_api`, keep SMTP unchanged as the default, and give password reset and generic/inbound notifications a real email.

**Architecture:**
- Every email is still built as a stdlib `EmailMessage`.
- `mailer._send_sync` becomes a dispatcher:
  - `smtp` runs today's smtplib code, untouched.
  - `zoho_api` calls `zoho_mail.send(msg)`. That function converts the message to the API's JSON, holds a cached OAuth token, and raises `EmailTransientError` or `EmailPermanentError`.
- Retry callers map those two errors: `lead_email._send` directly, and `delivery._send_email` through a `"permanent: "` error prefix.

**Tech Stack:** FastAPI, pydantic-settings, httpx (sync `httpx.Client`, `httpx.MockTransport` in tests), pytest.

**Spec:** `docs/superpowers/specs/2026-10-17-enh-032-zoho-mail-api-design.md` (owner-approved 2026-10-17, E1–E10)

## Global Constraints

- IDs: **ENH-032**, **DEC-SCOPE-225**. `origin/main` @ b47e7a80 was rechecked on 2026-10-17 and neither ID is used. Recheck again before the final commit.
- No migration, no new routes, no RBAC row.
- `EMAIL_TRANSPORT` defaults to `smtp`. With `smtp`, behaviour is byte-for-byte today's, including the Reply-To headers (AC2).
- From address: `settings.smtp_from_email` for both transports. Never send a Reply-To on the API path (E4/E6).
- Zoho send: `POST {ZOHO_MAIL_API_BASE}/api/accounts/{ZOHO_MAIL_ACCOUNT_ID}/messages`, header `Authorization: Zoho-oauthtoken <token>`.
- Token: `POST {ZOHO_ACCOUNTS_URL}/oauth/v2/token`, secrets as a **form body** (`data=`), `grant_type=refresh_token`.
- Never put the access token, client secret, refresh token or the Authorization header in an exception message, a log line or a stored error.
- Retry only when Zoho certainly did not accept the email (E9). Never retry the daily-limit response (E10).
- Tests: run the lite backend set only (listed in Task 6). Never the full suite; the owner runs that.
- Worktree test command (Git Bash, from `../enh-032`; copy the main repo's `.env` into the worktree first if it is missing):
  `docker compose -p enh032 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/enh-032/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <paths>"`
  Below, `PYTEST <paths>` means that command.

## Review Focus

1. **A Zoho token refresh that returns HTTP 200 with `{"error": "invalid_code"}`** (Zoho's shape for a bad refresh token) must fail permanently with a clear, secret-free message. It must not crash on `KeyError` or be retried forever. Test in Task 2.
2. **Two near-simultaneous sends in one worker process** (bulk roster invite) must share one token refresh, not each refresh. Test in Task 2.
3. **An email with only a plain-text part** (the lead email has both parts; a future one may not) must send as `mailFormat=plaintext`, not crash. Test in Task 2.
4. **`EMAIL_TRANSPORT=zoho_api` with `SMTP_HOST` unset**, which is the dev and prod setup, must count as configured. Lead email, interviews, profile sharing and the rest must not report `not_configured`. Test in Task 1.
5. **A forgot-password request for an unknown email** must still return 202 with no email and no webhook call, exactly as today. Test in Task 4.

---

### Task 1: Settings, `email_configured()`, and the system-status row

**Files:**
- Modify: `apps/api/app/core/config.py` (after the SMTP block, about line 44)
- Modify: `apps/api/app/services/mailer.py`:
  - the inline checks at lines 122, 204, 302 and 371
  - `smtp_configured` at line 391
- Modify: `apps/api/app/api/admin.py` (`system_status`, about line 405)
- Test: create `apps/api/tests/test_enh_032_zoho_mail.py`

**Interfaces:**
- Produces:
  - Settings fields:
    - `email_transport: Literal["smtp", "zoho_api"] = "smtp"`
    - `zoho_mail_client_id: str | None = None`
    - `zoho_mail_client_secret: str | None = None`
    - `zoho_mail_refresh_token: str | None = None`
    - `zoho_mail_account_id: str | None = None`
    - `zoho_mail_api_base: str = "https://mail.zoho.com"`
  - `mailer.email_configured() -> bool`
  - `mailer.smtp_configured = email_configured`, kept as an alias so the six existing callers stay correct untouched.

- [ ] **Step 1: Write the failing tests** in `test_enh_032_zoho_mail.py`:
  - `test_smtp_mode_needs_host_and_from`:
    - transport `smtp`, host and from set → `email_configured()` is True
    - host None → False
  - `test_zoho_mode_needs_from_and_all_four_credentials`:
    - transport `zoho_api`, `smtp_host=None`, from + 4 `zoho_mail_*` set → True
    - each of the 5 values set to None in turn (parametrised) → False
  - `test_smtp_configured_is_the_same_check`: `mailer.smtp_configured is mailer.email_configured`.
  - `test_unknown_transport_is_rejected`: `Settings(email_transport="sendgrid")` raises `pydantic.ValidationError`.
  - `test_zoho_mode_without_smtp_host_is_not_reported_not_configured` (Review Focus 4):
    - zoho mode configured, `smtp_host=None`, `mailer._send_sync` monkeypatched to record
    - `await mailer.send_welcome_email(...)` returns `("sent", None)`
  - `test_system_status_reports_the_email_transport`:
    - admin client (follow an existing admin-route test's fixture)
    - `GET /api/v1/admin/system-status` has the row `{"service": "Email delivery", "status": ...}`
    - expected statuses: `"Zoho Mail API"` (zoho configured), `"SMTP"` (smtp configured), `"not configured"` (neither)
- [ ] **Step 2: Run** `PYTEST tests/test_enh_032_zoho_mail.py`. Expected: FAIL (no `email_configured`, no setting).
- [ ] **Step 3: Implement.**
  - Add the settings, with a one-line comment block in the file's style citing ENH-032 / DEC-SCOPE-225.
  - `email_configured()`:
    - `smtp`: `bool(smtp_host and smtp_from_email)`
    - `zoho_api`: `bool(smtp_from_email and all four zoho_mail_* values)`
  - Replace the four inline `if not settings.smtp_host or not settings.smtp_from_email` checks with `if not email_configured()`.
  - Replace the `smtp_configured` def with the alias.
  - Add the system-status row after "Inbound university email".
- [ ] **Step 4: Run** `PYTEST tests/test_enh_032_zoho_mail.py tests/test_mailer.py tests/test_tel_014_email.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(enh-032): EMAIL_TRANSPORT setting, email_configured(), system-status email row`

### Task 2: Zoho Mail transport module

**Files:**
- Create: `apps/api/app/services/zoho_mail.py`
- Test: `apps/api/tests/test_enh_032_zoho_mail.py` (append)

**Interfaces:**
- Consumes: the Task 1 settings.
- Produces:
  - `class EmailTransientError(Exception)`: definitely not accepted; safe to retry.
  - `class EmailPermanentError(Exception)`: do not retry.
  - `def send(msg: EmailMessage, *, client: httpx.Client | None = None) -> None`: raises only the two errors above.
  - `def payload_from_message(msg: EmailMessage) -> dict`
  - `def reset_token_cache() -> None`: for tests.

Decisions the implementer cannot infer:
- **`fromAddress`** is the bare `settings.smtp_from_email`. It does not carry the display name, because whether Zoho accepts one is unverified (spec §4.3). Task 6 may switch to `msg["From"]` after the live check.
- **`toAddress`** is `msg["To"]`; **`subject`** is `msg["Subject"]`.
- **`content`:**
  - If the message has an HTML part: that HTML, with `mailFormat="html"` and every `<img ... src="cid:...">` tag removed (regex on `<img\b[^>]*\bsrc="cid:[^"]*"[^>]*>`).
  - Otherwise the plain-text part, with `mailFormat="plaintext"`.
- **No `replyTo` key,** whatever headers the message has.
- **Token:**
  - Module-level cache `(token, expires_at_monotonic)` behind a `threading.Lock`. Refresh while holding the lock, and re-check the cache after acquiring it.
  - Valid until `expires_in - 60` seconds.
  - Refresh response handling:
    - HTTP 200 with an `"error"` key, or a missing `access_token` → `EmailPermanentError("zoho_mail token refresh refused: <error value>")`
    - connect errors and timeouts → `EmailTransientError`
    - 5xx → `EmailTransientError`
- **Send mapping:**
  - `httpx.ConnectError`, `httpx.ConnectTimeout` → transient
  - any other `httpx.TransportError` (`ReadTimeout`, `WriteTimeout`, `ReadError`, `RemoteProtocolError`; outcome unknown) → **permanent**, message `"zoho_mail outcome unknown: <ExcType>"`
  - HTTP 401 → clear the cache, refresh, retry the POST **once**; a second 401 → permanent
  - HTTP 429 → **permanent**. Zoho's daily-limit response is not distinguished in the docs, so 429 is never retried (E10 is safer). Note this in Task 5's contract doc. If the implementer finds a documented limit code that is distinct from a plain rate limit, keep 429 permanent anyway.
  - HTTP 5xx → transient
  - other 4xx → permanent
  - 2xx → return
- **Error messages:** `"zoho_mail HTTP <code>: <status.description or data.errorCode>"`, capped at 200 characters. They never include the URL query, the headers or the request body.
- **Timeouts:** `httpx.Client(timeout=15)`. A passed-in `client` is used as-is (tests).

- [ ] **Step 1: Write the failing tests** (`httpx.MockTransport`, as in `test_enh_014_twilio.py`; an autouse fixture calls `reset_token_cache()` and sets zoho-mode settings with `zoho_mail_api_base="https://mail.zoho.test"`):
  - `test_payload_is_from_the_system_address_with_html_and_no_reply_to`:
    - input: a message built by `mailer.lead_email_message(...)`, which has a Reply-To, run through `payload_from_message`
    - `fromAddress == settings.smtp_from_email`
    - `toAddress` and `subject` match the message
    - `mailFormat == "html"`
    - `"replyTo" not in payload` and no key containing "reply"
  - `test_the_logo_image_is_stripped_from_html`:
    - input: a welcome-email message after `_attach_logo`
    - `"cid:" not in payload["content"]`
    - `'alt="EduSphere"'` (the img) is absent; the rest of the HTML is present
  - `test_a_text_only_message_sends_as_plaintext` (Review Focus 3).
  - `test_send_posts_to_the_account_messages_url_with_the_oauth_header`:
    - the handler records requests
    - the token POST goes to `{zoho_accounts_url}/oauth/v2/token` with form fields `grant_type=refresh_token`, `client_id`, `client_secret` and `refresh_token`, and **an empty URL query**
    - the send goes to `https://mail.zoho.test/api/accounts/<id>/messages` with `Authorization: Zoho-oauthtoken tok1`
  - `test_the_token_is_cached_across_sends`: two sends → one token request.
  - `test_concurrent_sends_refresh_once` (Review Focus 2): two threads with a token endpoint that sleeps briefly → one token request.
  - `test_a_401_refreshes_once_and_retries`:
    - send returns 401, then 200 → two token requests, two sends, no error
    - 401 twice → `EmailPermanentError`
  - `test_a_refused_refresh_token_is_permanent_and_secret_free` (Review Focus 1):
    - the token endpoint returns 200 `{"error": "invalid_code"}` → `EmailPermanentError`
    - `"invalid_code" in str(exc)`
    - neither the refresh token value nor the client secret appears in `str(exc)`
  - `test_error_classification`, parametrised:
    - `ConnectError` → transient
    - `ConnectTimeout` → transient
    - `ReadTimeout` → permanent
    - `RemoteProtocolError` → permanent
    - 500 → transient
    - 503 → transient
    - 429 → permanent
    - 400 → permanent
    - 403 → permanent
  - `test_errors_never_carry_secrets`: for each failing case, neither `"tok1"` nor the secret values appear in `str(exc)`.
- [ ] **Step 2: Run** `PYTEST tests/test_enh_032_zoho_mail.py`. Expected: the new tests FAIL (module missing).
- [ ] **Step 3: Implement** `zoho_mail.py` per the decisions above. Module docstring cites ENH-032 / DEC-SCOPE-225, E4/E9/E10.
- [ ] **Step 4: Run** `PYTEST tests/test_enh_032_zoho_mail.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(enh-032): Zoho Mail API transport with cached OAuth token and E9/E10 error mapping`

### Task 3: Dispatch in `_send_sync` and retry mapping in callers

**Files:**
- Modify: `apps/api/app/services/mailer.py`:
  - `_send_sync` (line 109)
  - the `except` blocks of the four `send_*` functions
- Modify: `apps/api/app/notifications/lead_email.py` (`_send`, lines 58–76)
- Modify: `apps/api/app/notifications/delivery.py` (`_send_email`, about line 120)
- Test: `apps/api/tests/test_enh_032_zoho_mail.py` (append)

**Interfaces:**
- Consumes: `zoho_mail.send`, `EmailTransientError`, `EmailPermanentError` (Task 2).
- Produces:
  - `mailer.PERMANENT_PREFIX = "permanent: "`
  - `mailer.failure_text(exc: BaseException) -> str`: returns `PERMANENT_PREFIX + str(exc)[:480]` for `EmailPermanentError`, otherwise `str(exc)[:500]`
  - `mailer.is_permanent(error: str | None) -> bool`
  - `mailer` re-exports both error classes

- [ ] **Step 1: Write the failing tests:**
  - `test_send_sync_dispatches_by_transport`:
    - `zoho_api` → the monkeypatched `zoho_mail.send` is called and `smtplib.SMTP` is not
    - `smtp` → `smtplib.SMTP` is called (monkeypatch it with a recording fake) and `zoho_mail.send` is not
  - `test_lead_email_retries_transient_and_fails_permanent`, parametrised:
    - follow `tests/test_tel_014_delivery.py` (`outbox`-style fixture, with `_send_sync` raising)
    - `EmailTransientError` → row `retrying` and re-enqueued with the countdown
    - `EmailPermanentError` → `failed` and not re-enqueued
  - `test_a_permanent_mailer_failure_is_not_a_transient_delivery`:
    - `_send_sync` raises `EmailPermanentError("x")`
    - `send_bdm_reminder_email` returns `("failed", "permanent: x")`
    - `delivery._send_email` for a `bdm_reminder` snapshot returns a `SendResult` with `transient is False`
    - with `EmailTransientError` instead: `transient is True`
  - `test_smtp_failures_keep_todays_transient_behaviour`: an `OSError` from `_send_sync` → `failed` and `transient is True` (AC2).
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - `_send_sync`: `if settings.email_transport == "zoho_api": return zoho_mail.send(msg)`, then the existing smtplib body unchanged.
  - The four `except Exception as exc: return "failed", str(exc)[:500]` blocks become `return "failed", failure_text(exc)`.
  - `lead_email._send`: add `except EmailTransientError: return "retry", "EmailTransientError"` and `except EmailPermanentError: return "failed", "EmailPermanentError"` **before** the smtplib branches.
  - `delivery._send_email`: `transient=status == "failed" and not is_permanent(error)`.
- [ ] **Step 4: Run** `PYTEST tests/test_enh_032_zoho_mail.py tests/test_mailer.py tests/test_tel_014_delivery.py tests/test_tel_014_email.py tests/test_enh_014_delivery.py tests/test_bdm_012_email.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(enh-032): route _send_sync by EMAIL_TRANSPORT; map transient/permanent errors in lead email and delivery`

### Task 4: Password-reset and generic notification emails (E8)

**Files:**
- Modify: `apps/api/app/services/mailer.py` (add two senders and their templates)
- Modify: `apps/api/app/services/provisioning.py:71-75` (make the portal-URL rule public)
- Modify: `apps/api/app/api/auth.py` (forgot-password, about line 383)
- Modify: `apps/api/app/notifications/delivery.py` (`_send_email`, the `inbound` and `else` branches)
- Test: `apps/api/tests/test_enh_032_zoho_mail.py` (append)

**Interfaces:**
- Produces:
  - `provisioning.portal_password_url(user: User, raw: str) -> str`: the body of today's `_set_password_url`. Keep `_set_password_url = portal_password_url` as an alias.
  - `mailer.send_password_reset_email(*, to_email: str, recipient_name: str, reset_url: str, expires_minutes: int) -> tuple[str, str | None]`
  - `mailer.send_generic_notification_email(*, to_email: str, recipient_name: str, title: str, body: str, action_url: str | None) -> tuple[str, str | None]`
- Both senders have the same structure as `send_welcome_email`:
  - `email_configured()` gate
  - message built inside `try`
  - `_attach_logo`
  - `_send_sync`
  - `failure_text`
- Both use `From: EduSphere <smtp_from_email>`. Escape all interpolated text with `html.escape` (see `test_enh_005_mailer_escaping.py`).
- Fixed copy:
  - Reset subject: `Reset your EduSphere password`
  - Reset text: `Hi {name},\n\nWe received a request to reset your EduSphere password. Use this link within {expires_minutes} minutes:\n{reset_url}\n\nIf you did not ask for this, ignore this email; your password stays the same.\n`
  - The reset HTML shows the same text, with the link as a button.
  - Generic subject: `{title} -- EduSphere`
  - Generic body: like `send_parent_notification_email`, without the school name; `action_url` is used as the parent email uses it.

- [ ] **Step 1: Write the failing tests:**
  - `test_forgot_password_emails_the_portal_reset_link`:
    - smtp-mode outbox fixture; an overseas student user
    - `POST /api/v1/auth/forgot-password` → 202
    - one message to the user, subject `Reset your EduSphere password`
    - the text contains `{frontend_url}/overseas/reset-password?token=`
    - an admin-portal role gets `/admin/reset-password?token=`
    - the `NotificationDelivery` row is `sent`
  - `test_forgot_password_falls_back_to_the_webhook_when_email_is_not_configured`:
    - `smtp_host=None`; monkeypatch `auth.send_notification` to record
    - the webhook is called with `template == "password_reset"`
    - no mailer send
  - `test_forgot_password_for_an_unknown_email_sends_nothing` (Review Focus 5): 202, no outbox message, no webhook call.
  - `test_the_reset_token_appears_only_in_the_link`:
    - `_send_sync` raises `EmailPermanentError`
    - the delivery row's `error` does not contain the raw token
  - `test_generic_and_inbound_notifications_use_the_mailer_then_the_webhook`, parametrised over context `None` and `{"kind": "inbound"}`:
    - configured → `send_generic_notification_email` sends, and `send_notification` is not called
    - not configured → `send_notification` is called with today's payload (inbound without `phone`, generic with `phone`)
  - `test_new_emails_escape_html`: a `<script>` title or name is escaped in both senders.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Senders and the provisioning rename as above.
  - `auth.py`:
    - call `send_password_reset_email` with `reset_url=portal_password_url(user, raw)` and `recipient_name=user.full_name`
    - if it returns `not_configured`, run today's `send_notification` call
    - record whichever result in the existing `NotificationDelivery`
    - the response and the dev-token exposure are unchanged
  - `delivery._send_email`: the `inbound` and `else` branches follow the school-branch pattern (mailer first, webhook on `not_configured`).
  - The webhook copies in `schools.py:161` and `provisioning.py:122` are **unchanged**.
- [ ] **Step 4: Run** `PYTEST tests/test_enh_032_zoho_mail.py tests/test_enh_003_first_time_provisioning.py tests/test_bdm_001_reset_portal.py tests/test_enh_014_triggers.py tests/test_not_001_email_notifications.py tests/test_enh_005_mailer_escaping.py tests/test_sch_007_parent_portal.py`. Expected: PASS. If an existing test asserted the webhook-only forgot-password path, update it only where the new E8 behaviour is the intended change, and say so in the commit body.
- [ ] **Step 5: Commit** `feat(enh-032): real password-reset and generic/inbound notification emails with webhook fallback (E8)`

### Task 5: Test-send command, env examples, and docs

**Files:**
- Create: `apps/api/app/send_test_email.py`. It runs as `python -m app.send_test_email --to <addr>`, in the same style as `app/bootstrap_admin.py`.
- Modify: `.env.example`, `apps/api/.env.example`
- Modify:
  - `docs/architecture/INTEGRATION_CONTRACTS.md`
  - `docs/architecture/DEPLOYMENT.md`
  - `docs/architecture/API_CONTRACT.md` (the system-status row)
  - `docs/decisions/PRODUCT_DECISION_REGISTER.md` (DEC-SCOPE-225)
  - `docs/delivery/ENHANCEMENT_BACKLOG.md` (an ENH-032 item)
  - `docs/quality/RTM.md`
  - the spec's Status line
- Test: `apps/api/tests/test_enh_032_zoho_mail.py` (append)

**Interfaces:**
- Produces: `send_test_email.main(argv: list[str] | None = None) -> int`.
  - It builds one plain "EduSphere test email" through `mailer.send_generic_notification_email` and prints the status and transport.
  - Exit codes: 0 if sent, 1 if failed, 2 if not configured.
  - It never prints settings values.

- [ ] **Step 1: Write the failing test** `test_send_test_email_reports_status_without_secrets`:
  - with `_send_sync` faked: exit code 0 when sent, 2 when not configured
  - captured stdout contains `Zoho Mail API` or `SMTP`
  - stdout contains none of the zoho secret values
- [ ] **Step 2: Run** it. Expected: FAIL.
- [ ] **Step 3: Implement** the command.
- [ ] **Step 4: Run** it. Expected: PASS.
- [ ] **Step 5: Write the docs** (mirror the ENH-031 entries' format in each file):
  - **Env examples:** `EMAIL_TRANSPORT=smtp`, the four `ZOHO_MAIL_*` values (empty), `ZOHO_MAIL_API_BASE=https://mail.zoho.com`, each with a comment.
  - **INTEGRATION_CONTRACTS:**
    - the endpoint, scope, token flow and caching
    - error mapping, including **"429 is never retried"** and **"outcome-unknown timeouts are not retried"**
    - no Reply-To; logo stripped; the bare From address
  - **DEPLOYMENT:** the owner setup steps from spec §6, plus `python -m app.send_test_email --to <addr>` after recreating api, worker and beat (`--no-deps` on prod).
  - **Decision register:** DEC-SCOPE-225 citing E1–E10 and the DigitalOcean SMTP block evidence (spec §3.1).
  - **Backlog, RTM, API contract:** the ENH-032 item with AC1–AC8 + AC1a/AC4a, RTM rows, and the system-status row.
- [ ] **Step 6: Commit** `docs(enh-032): DEC-SCOPE-225, Zoho Mail contract, deploy steps, env examples; test-send command`

### Task 6: Lite regression, static checks, and the live check on dev

**Files:** none (verification); the spec gets an **As built** note if anything differs.

- [ ] **Step 1: Lite backend set:**
  `PYTEST tests/test_enh_032_zoho_mail.py tests/test_mailer.py tests/test_enh_005_mailer_escaping.py tests/test_tel_014_email.py tests/test_tel_014_delivery.py tests/test_rec_026_delivery.py tests/test_upc_012_delivery.py tests/test_enh_014_delivery.py tests/test_enh_014_triggers.py tests/test_not_001_email_notifications.py tests/test_bdm_012_email.py tests/test_sch_007_parent_portal.py tests/test_enh_003_first_time_provisioning.py tests/test_bdm_001_reset_portal.py`
  Expected: all pass. Report exactly this list, and that the full suite was not run (owner's standing choice).
- [ ] **Step 2: Static checks** in the api-test container: `ruff check app tests` and `mypy app`. Expected: clean for the touched files.
- [ ] **Step 3: Recheck `origin/main`** for DEC-SCOPE-225 / ENH-032 collisions; re-number everywhere if one was taken.
- [ ] **Step 4: Hand off the live check to the owner. Do not deploy or touch Docker yourself.** Give them:
  1. the push command `git -C ../enh-032 push -u origin feature/enh-032`
  2. the dev `.env` lines to add
  3. the container-recreate command
  4. `python -m app.send_test_email --to <their address>`
- [ ] **Step 5: With the owner's result, record it in `docs/quality/` QA evidence (AC8):**
  - arrived from `info@`
  - no broken logo
  - a reply goes to `info@`
  If the owner also wants display names, test `fromAddress = msg["From"]` in one send. Switch `payload_from_message` only if Zoho accepts it, and update the Task 2 test and the contract doc.
