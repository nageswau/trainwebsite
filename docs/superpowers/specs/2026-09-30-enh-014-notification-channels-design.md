# ENH-014 — Multi-Channel Notifications (WhatsApp / SMS), Slice 1 — Design

Status: design approved in-session 2026-09-30 (approach A plus design parts 1–3).
Backlog: `docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-014. Evidence: `School CRM.md` §32, Part B §11.
Decision: `DEC-NOT-001`, extension of 2026-09-30 (D1–D14), `PRODUCT_DECISION_REGISTER.md`.

## 1. Problem

Every notification in the product is delivered in-app plus email. WhatsApp and SMS exist only as generic
JSON webhooks (`services/integrations.send_notification`), reachable from `_notify_user` and
`POST /communications/notify` but never from the School path, which is hard-coded to email
(`schools._notify_parent`). There is no user preference, no consent record, no real Twilio integration, and
every send runs inline inside the request (10 s webhook timeout each), in some paths before the business
write commits.

## 2. Goals and non-goals

Goals (slice 1):
- Users opt in to WhatsApp and/or SMS; email and in-app stay always on.
- Every trigger that sends email today also delivers on the recipient's opted-in channels, via Twilio.
- All deliveries (email included) are queued after commit and sent by Celery, so a provider can never delay,
  fail or roll back the business write.
- Existing email content and routing are preserved exactly.

Non-goals (recorded, not faked):
- Push notifications (D3), the Platinum `parent_help_desk` (D12, later slice).
- Student/Teacher recipients for result publish (D6); students have no login or contact fields (`DEC-ROLE-004`).
- Twilio delivery-receipt callbacks (`delivered`/`undelivered`): `sent` means Twilio accepted the message.
- Per-event templates and WhatsApp/SMS template management in `ADM-011` (D13).
- OTP phone verification (D14).
- Changing in-app-only triggers (chat messages, IT live sessions, coordinator-only transfer notices).
- Any change to password-reset, set-password, invite or welcome email flows (D7).

## 3. Decisions confirmed in-session (2026-09-30)

See `DEC-NOT-001` extension D1–D14. Design choices made in this brainstorm:

| # | Question | Decision |
|---|---|---|
| X1 | Delivery architecture | Approach A: one dispatch helper; every channel queued after commit (alternatives: queue only new channels; send inline — rejected) |
| X2 | Where preferences live | New `notification_preferences` table, one row per user; no row = WhatsApp/SMS off |
| X3 | Phone validation point | Only when turning a channel on and at send time; `PATCH /auth/me` is unchanged |
| X4 | Email render context in the worker | New nullable `notification_deliveries.context` JSON |
| X5 | Twilio client | Direct REST calls over the existing `httpx` dependency; no Twilio SDK |
| X6 | Stuck `sending` rows | Marked `failed` ("worker interrupted"), never resent — no duplicate messages to parents |

## 4. Data model — migration `0046_notification_channels`

Additive only. No existing row is modified; downgrade drops only what it adds.

`notification_preferences` (new):

| column | type | notes |
|---|---|---|
| `user_id` | UUID PK, FK `users.id` ON DELETE CASCADE | |
| `whatsapp_opt_in` | bool, not null, default false | |
| `sms_opt_in` | bool, not null, default false | |
| `whatsapp_opted_in_at` | timestamptz, nullable | set on opt-in, cleared on opt-out |
| `sms_opted_in_at` | timestamptz, nullable | same |
| `created_at`, `updated_at` | `TimestampMixin` | |

`notification_deliveries.context` (new, JSON, nullable): `{"kind": "school", "school_name": "..."}` for the
School path; null for the generic path and every pre-existing row.

`NotificationDelivery.status` values (column already `String(30)`; no schema change):
`queued`, `sending`, `retrying`, `sent`, `failed`, `not_configured`, `skipped`.
New queued rows set `attempt_count=0`; each claim increments it. The column default (1) is untouched for the
inline auth paths that still construct rows directly.

Index (for the sweeper, §6.5): `ix_notification_deliveries_status_updated_at` on `(status, updated_at)`.

Data classification: preferences are personal data (consent state) with no free text; retention = life of the
account, deleted on erasure (§6.2). `context.school_name` is not personal data. The phone number stays only in
`users.phone`; nothing new stores it.

## 5. API

Conventions follow the existing API, not a new style: snake_case fields, FastAPI's `{"detail": ...}` error
body, Pydantic input/output models on the route (`schemas.py`).

### 5.1 `GET /api/v1/account/notification-preferences`
Any signed-in user; own data only (user from session, no id in path). `401` when signed out.
`response_model=NotificationPreferencesOut`:

```json
{ "whatsapp": false, "sms": false, "phone_valid": true }
```
`phone_valid` is whether `User.phone` normalises (§6.3). The phone itself is not echoed (the page already has
it from `/auth/me`), and "email/in-app always on" is UI copy, not API fields — nothing observable is added
that a client could come to depend on without need.

### 5.2 `PUT /api/v1/account/notification-preferences`
Body `NotificationPreferencesIn`: `{ "whatsapp": StrictBool, "sms": StrictBool }`, both required,
`extra="forbid"` (so `"yes"`, `1`, or a smuggled `user_id`/`*_opted_in_at` is a 422). Returns `200` with the
§5.1 shape. Full replacement of a two-field resource, so PUT (idempotent: repeating it is harmless).
- `422` `{"detail": "Add a valid mobile number to your profile first"}` when turning either on while
  `phone_valid` is false; nothing is written.
- Upsert on `user_id` (`INSERT … ON CONFLICT DO UPDATE`, SQLAlchemy `postgresql.insert`, parameterised), so
  concurrent requests cannot create two rows; last write wins.
- `*_opted_in_at` set to now on a false→true change, kept on true→true, cleared on →false.
- Audit only when a value changes: `AuditLog(action="notification_preference.update",
  metadata={"before": {...}, "after": {...}, "consent_text": "enh014-v1"})` — booleans and the consent-copy
  version only, never the phone number. Preference upsert and audit row commit in one transaction.
- No admin override: consent must be the user's own.
- CSRF: the session cookie is `SameSite=Lax` (`auth.py:88`) and the method is PUT with a JSON body, which a
  cross-site HTML form cannot send; no new CSRF mechanism is needed.
- Rate limiting: none added. Opting in sends nothing (no confirmation message), so there is no cost or spam
  amplification to limit; audit rows are written only on change.

### 5.3 Unchanged / adjusted contracts
- `PATCH /auth/me`: unchanged.
- `POST /communications/notify`: request/response shape unchanged. Per-channel statuses become `"queued"`;
  WhatsApp/SMS are dropped for recipients who have not opted in; the delivery rows attach to the notification
  this request created (removes the existing UUID-ordering lookup). The no-recipient branch is unchanged.
- `GET /workflows/notifications`, `PATCH /workflows/notifications/{id}/read`, `GET /admin/notifications`:
  unchanged.
- `GET /account/data-requests/{id}/export`: adds a `notification_preferences` object.

## 6. Backend components

### 6.1 `app/notifications/dispatch.py`
- `async queue_deliveries(db, notification, recipient, *, context=None, channels=None) -> list[NotificationDelivery]`
  - Allowed channels = `email` + `whatsapp`/`sms` where the recipient's preference row opts in.
  - `channels` (admin `/notify` only) is intersected with the allowed set.
  - Adds one `NotificationDelivery(status="queued", attempt_count=0, context=context)` per channel, flushes,
    and appends the ids to `db.sync_session.info["enh014_pending"]`.
- SQLAlchemy `Session` event listeners, registered once on import:
  - `after_commit`: pop the pending ids and call `enqueue(id)` for each.
  - `after_rollback` / `after_soft_rollback`: discard pending ids.
- `enqueue(delivery_id, countdown=0)`: `deliver_notification_task.apply_async((str(id),), countdown=countdown,
  retry=False)`; `retry=False` makes a broker outage fail fast instead of blocking the request in Celery's
  publish-retry loop. Any exception is logged (`notification_enqueue_failed`, delivery id only) and swallowed —
  the row stays `queued` for the sweeper.
- `normalise_phone(raw: str | None) -> str | None` (§6.3).

### 6.2 Changed helpers (bodies only; signatures unchanged, so the ~35 trigger sites do not change)
- `schools._notify_parent`: create the `Notification`, then
  `queue_deliveries(..., context={"kind": "school", "school_name": school_name})`.
- `workflows._notify_user`: create the `Notification`, then `queue_deliveries(..., channels=channels)`.
  The two callers passing `["email"]` (certificate issued, Q&A reply) drop the argument (D5).
- `inbound._notify_student`: `queue_deliveries(...)`.
- `communications.notify`: use `queue_deliveries` for the recipient branch.
- `admin` GDPR erasure: delete the user's `NotificationPreference` row alongside the existing PII redaction.
- Unchanged: `auth.forgot_password`, invite/welcome/set-password senders, `mailer.py`,
  `post_optional_webhook`, `send_message`, IT live-session notice, transfer coordinator notices.

### 6.3 Phone normalisation (no new dependency)
Strip spaces, `-`, `(`, `)`, `.`. Then:
- `+` followed by 8–15 digits → kept as `+digits`.
- 10 digits starting 6–9 → `+91` + digits.
- `0` + 10 digits (6–9 lead) → `+91` + the 10 digits.
- `91` + 10 digits (6–9 lead) → `+91` + the 10 digits.
- Anything else → `None`.

### 6.4 `app/notifications/twilio.py`
- Settings (all default `None` = not configured): `twilio_account_sid`, `twilio_auth_token`,
  `twilio_whatsapp_from`, `twilio_sms_from`, `twilio_whatsapp_content_sid`. Added empty to
  `docker-compose.ci.yml`.
- `async send_whatsapp(to, title, body, link)`: `POST https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json`
  (basic auth), `From=whatsapp:{from}`, `To=whatsapp:{to}`, `ContentSid`, `ContentVariables={"1": title, "2": body, "3": link}`.
- `async send_sms(to, text)`: same endpoint, `From`, `To`, `Body` (text = `"{title} — {body} {link}"`, capped at
  320 characters).
- Link = `settings.frontend_url` + `action_url`, only when `action_url` starts with a single `/` (an internal
  path). Absolute, protocol-relative (`//…`) or `javascript:` values — reachable through the admin
  `/communications/notify` form — are dropped, so messages never carry an off-site link.
- Template variables and SMS text are plain text: whitespace runs (including newlines, which WhatsApp template
  variables reject) collapsed to one space, each variable capped at 500 characters.
- The Twilio response is untrusted: only `sid` (string, `^(SM|MM)[0-9a-f]{32}$`) and the numeric error `code`
  are read; anything else is ignored.
- Returns `SendResult(status, provider_reference, error, transient)`: 2xx with a valid `sid` → `sent`;
  timeout/connection error/5xx/429 → `failed`, transient; other 4xx → `failed`, permanent. Stored error is
  `twilio:{code}` plus Twilio's message with any run of 6+ digits replaced by `…` (Twilio messages can echo
  the recipient number), truncated to 500. The auth token is sent only in the basic-auth header and never
  appears in errors or logs.

### 6.5 Worker — `app/worker.py`
`deliver_notification_task(delivery_id)` — thin Celery wrapper (`asyncio.run`) around
`app.notifications.dispatch.deliver(delivery_id)`:
1. Claim: `UPDATE notification_deliveries SET status='sending', attempt_count=attempt_count+1
   WHERE id=:id AND status IN ('queued','retrying') RETURNING …`; commit. No row → exit (already handled).
2. Load the notification and recipient; missing or inactive recipient → `skipped`.
3. Send by channel:
   - `email`, `context.kind == "school"`: `send_parent_notification_email(...)`; if `not_configured`, fall back to
     `send_notification("email", ...)` — identical to today's `_notify_parent`.
   - `email`, otherwise: `send_notification("email", {...})` — identical to today's `_notify_user` payload.
   - `whatsapp`/`sms`: preference re-read → not opted in → `skipped`; `normalise_phone` fails → `failed`,
     `error="invalid_phone"`, permanent; Twilio configured → Twilio adapter; else legacy webhook URL set →
     `send_notification(channel, ...)` with the normalised phone; else `not_configured`.
4. Persist: `sent` (+ `sent_at`, `provider_reference`); transient failure with `attempt_count < 4` →
   `retrying` and re-enqueue with countdown 60 / 300 / 1500 s for attempts 1 / 2 / 3; otherwise `failed`.
   Error truncated to 500 characters. Webhook-channel failures (email webhook, legacy WhatsApp/SMS webhooks)
   are treated as transient; SMTP failures as transient.
5. Log `notification_delivery` with delivery id, channel, status, attempt — never phone, email or text.

`sweep_stale_deliveries` (Celery beat, every 5 minutes):
- `queued`/`retrying` rows whose `updated_at` is older than 30 minutes (longer than the largest retry
  countdown, 25 min) → re-enqueue. A duplicate enqueue is harmless: the claim lets only one run.
- `sending` rows whose `updated_at` is older than 15 minutes → `failed`, `error="worker interrupted"`.

## 7. Frontend — `/account/profile`

Reuse first: the page's existing `PublicShell`, `.action-card`, `.form`/`.field`, `.btn`, `.muted`,
`FormMessage` (alert for failure, status for success) and `ProfileForm`'s patterns (double-submit ref guard,
visually-hidden "Saving…" status, focus return to the submit button, 401 "session expired" block). The only
new component is `components/NotificationPreferencesForm.tsx`; no new CSS tokens or libraries.

Page (`app/account/profile/page.tsx`):
- Loads `/auth/me` and `/account/notification-preferences` in parallel (`Promise.allSettled` — no added
  latency; the page is server-rendered, so there is no client loading state to design for first paint).
- Hierarchy: `h1` "Your profile" (unchanged) → existing profile card → `h2` "Notifications" with a one-line
  `muted` intro ("Choose where we send updates about results, sessions and applications.") → a second
  `.action-card` holding the form.
- A `/auth/me` failure keeps today's behaviour. A preferences-only failure renders, in the second card only,
  "We couldn't load your notification settings right now." with a "Try again" link (`href="/account/profile"`);
  the profile form still works.

Form (`NotificationPreferencesForm`, props `{ initial, phone, phoneValid }`):
- `<fieldset>` with `<legend>` "Send me updates by". Four rows, each a native checkbox inside its `<label>`
  (whole row is the click/touch target, at least 44 px tall):
  - Email — checked, disabled, hint "Always on".
  - In-app — checked, disabled, hint "Always on".
  - WhatsApp — "Messages go to {phone}".
  - SMS — "Texts go to {phone}".
- No valid phone (empty state): WhatsApp/SMS disabled, and a hint (linked by `aria-describedby`) "Add a mobile
  number in your profile above to turn on WhatsApp or SMS." with an in-page link to `#profile-phone`.
- Consent copy under the channels: "By turning on WhatsApp or SMS you agree to receive these messages from
  EduSphere. You can turn them off here at any time." (version `enh014-v1`, recorded in the audit, §5.2).
- Explicit "Save notification settings" button — consent is a deliberate act, so toggles do not autosave.
- Saving: button text "Saving…", `aria-disabled`, `aria-busy` on the form, visually-hidden status, second
  submit ignored. Success: `FormMessage` "Notification settings saved." Failure: `FormMessage` alert with the
  server's 422 `detail`, or "Couldn't save your settings. Check your connection and try again." for network
  or 5xx; the checkboxes revert to the last saved values. 401: the same "session expired" block as
  `ProfileForm`.
- Keyboard: Tab order follows the visual order; Space toggles; focus returns to the Save button after a save.
  Colour is never the only signal (disabled rows carry text hints).
- Responsive: single column at every width; labels wrap; tested at 320, 768, 1024 and 1440 px.

`ProfileForm` gets one change: `router.refresh()` after a successful save, so a newly added phone enables the
WhatsApp/SMS toggles without a manual reload (client state in both forms is kept across the refresh).

Types added to `lib/types.ts`. No admin UI change.

## 8. Transactions, races, authorization, errors

- Enqueue only in `after_commit`: a rolled-back write queues nothing, and the worker never reads an
  uncommitted row. Triggers that notify before their commit (result publish, activity create) and after it
  (skills, tier change) both work unchanged.
- Duplicate task delivery / concurrent workers: the conditional claim update lets exactly one proceed.
- Opt-out between queue and send: re-checked at send → `skipped`.
- Concurrent preference writes: upsert on the primary key.
- Redis down at enqueue: request still succeeds; the sweeper re-enqueues.
- Worker crash mid-send: `sending` → `failed` by the sweeper, not resent.
- Unknown outcome: if a worker dies after Twilio accepted a message but before recording it, the row stays
  `sending` and the sweeper marks it `failed` ("worker interrupted") — never resent, because Twilio's Messages
  API has no idempotency key and a duplicate to a parent is worse than a missed copy (email and in-app still
  exist).
- Preferences are self-only; the worker runs without a user context; no new public endpoint.
- PII: phone numbers go only to Twilio (D9); never logged; erasure deletes preferences.

### 8.1 Security review (security-and-hardening)

Trust boundaries: browser → preference endpoints; trigger code → Celery/Redis → worker; worker → Twilio/SMTP/
webhooks; Twilio responses → worker.

| Check | Finding / control |
|---|---|
| Authentication | Both endpoints use `get_current_user` (session cookie); 401 when absent |
| Authorization / IDOR | No resource id in the path; user always from the session; no admin route can set anyone's consent |
| Role escalation | `extra="forbid"` input; only two booleans writable; role/profile untouched; `PATCH /auth/me` guard unchanged |
| Input validation | `StrictBool` body; phone normalised with an allow-list pattern before any send; `action_url` link allow-list (§6.4) |
| XSS | React escaping on the page; email HTML path unchanged (ENH-005 escaping); WhatsApp/SMS are plain text |
| CSRF | `SameSite=Lax` cookie + PUT/JSON (§5.2) |
| SQL injection | ORM / `postgresql.insert` / `update()` constructs only; no raw SQL strings |
| Token / session | No new tokens or session handling; auth/invite links stay email-only (AC11) |
| Secret exposure | Twilio SID/token from env only, empty in CI compose, sent only as basic auth, never in errors/logs/responses |
| Sensitive logs | Logs carry delivery id, channel, status, attempt only; stored Twilio errors have 6+-digit runs redacted |
| Rate limiting | Not added for preferences (nothing sent on opt-in); outbound volume bounded by existing trigger RBAC; admin `/notify` stays role-gated and audited |
| Audit | Preference changes audited with before/after and consent-copy version; admin `/notify` audit unchanged |
| SSRF | Twilio base URL is a constant; legacy webhook URLs come from env only, as today |
| Third-party data | Twilio response parsed for `sid` and `code` only, both shape-checked |
| Privacy / DPDP | Opt-in with timestamp; minimal data; erasure deletes; export includes (AC13); Twilio as processor (D9) |

## 9. Acceptance criteria

- **ENH-014-AC01** A signed-in user can view and change their WhatsApp/SMS opt-in; defaults are off; email and
  in-app cannot be turned off.
- **ENH-014-AC02** Turning a channel on without a phone that normalises returns 422 and changes nothing.
- **ENH-014-AC03** Every opt-in/opt-out is timestamped and audited; a user can change only their own.
- **ENH-014-AC04** Every trigger that sends email today queues email plus the recipient's opted-in channels, one
  row per channel; a rolled-back write queues and sends nothing.
- **ENH-014-AC05** Sending happens after commit; a provider outage or failure never fails or reverts the
  business request.
- **ENH-014-AC06** A parent opted in to WhatsApp receives the result-published message on WhatsApp; a parent not
  opted in receives no WhatsApp or SMS.
- **ENH-014-AC07** An invalid number or a Twilio rejection fails only that delivery; other recipients and channels
  in the batch are sent.
- **ENH-014-AC08** Transient failures retry up to 3 times (60 s, 5 min, 25 min) and then become `failed` with the
  error kept; permanent failures do not retry.
- **ENH-014-AC09** A delivery is never sent twice, including on duplicate task delivery or a worker crash.
- **ENH-014-AC10** Opting out after queueing but before sending results in `skipped`.
- **ENH-014-AC11** Password reset, set-password and invite messages stay email-only regardless of preferences.
- **ENH-014-AC12** Email content and routing are unchanged (School SMTP HTML with webhook fallback; generic
  email webhook for IT/Overseas).
- **ENH-014-AC13** GDPR erasure deletes the preferences row; the data export includes preferences.
- **ENH-014-AC14** With Twilio unconfigured, WhatsApp/SMS deliveries are `not_configured`; the legacy
  `WHATSAPP_WEBHOOK_URL`/`SMS_WEBHOOK_URL` still work when set.
- **ENH-014-AC15** The preference endpoint accepts only two strict booleans; any other field or type is 422 and
  writes nothing.
- **ENH-014-AC16** WhatsApp/SMS messages carry a link only for internal paths; phone numbers, message text and
  the Twilio token never appear in logs, and stored Twilio errors have phone-like digit runs redacted.

## 10. Tests (written first)

Backend (`apps/api/tests/`):
- `conftest.py`: autouse fixture replacing `dispatch.enqueue` with a capture list (no Redis in tests), plus a
  `drain_deliveries` helper that awaits `deliver()` for captured ids until empty (retries captured, not slept).
- `test_enh_014_phone.py` — normalisation table (AC02 inputs).
- `test_enh_014_preferences.py` — 401 on both; defaults; 422 without valid phone (nothing written); 422 on
  `"yes"`/`1`/extra `user_id`/`whatsapp_opted_in_at` (AC15); opt-in/out timestamps; audit only on change with
  `consent_text`; a second user's row untouched; concurrent PUTs leave one row (AC01–AC03).
- `test_enh_014_twilio.py` — request shape (basic auth, `whatsapp:` prefixes, ContentVariables); whitespace
  collapsing and caps; link allow-list drops absolute/`//`/`javascript:` URLs; malformed `sid` treated as
  failure; error redaction; token absent from error text (AC16). Uses `httpx.MockTransport`, no network.
- `test_enh_014_dispatch.py` — result publish and school activity with opted-in vs not (AC04, AC06); rollback
  queues nothing and enqueue fires only after commit (AC04, AC05); `/communications/notify` filtering;
  certificate/Q&A follow preferences; forgot-password stays inline email-only (AC11).
- `test_enh_014_worker.py` — sent with SID; transient retry sequence then failed; permanent 4xx no retry;
  invalid phone isolated from other recipients (AC07, AC08); double claim sends once (AC09); opt-out → skipped
  (AC10); school vs generic email paths (AC12); not_configured and legacy webhook (AC14); sweeper rules.
- `test_enh_014_privacy.py` — erasure deletes preferences; export includes them (AC13).
- Updated on purpose (queued → drained): `test_sch_007_parent_portal.py:164`, `test_enh_023_tier_change.py:222`,
  `test_ovs_004_status_tracking.py:135` (monkeypatch target moves to the dispatch module).

Frontend:
- Vitest `NotificationPreferencesForm.test.tsx` — always-on rows disabled with text; no-phone empty state and
  `aria-describedby` hint; saving (`aria-busy`, double submit ignored); success status; 422 detail and network
  error alerts with checkbox revert; 401 session-expired block; focus returns to Save.
- Vitest `ProfileForm` — existing tests still pass with a mocked `useRouter`; `refresh()` called once after a
  successful save only.
- Playwright `enh-014-notification-preferences.spec.ts` — parent without phone sees toggles disabled; adds phone,
  toggles enable without reload; turns on WhatsApp, reloads, still on; preferences load failure shows the
  section error while the profile form works; keyboard-only run; 320 px and 1440 px viewports with no
  horizontal scroll; axe check on the page.

Regression: full pytest suite, full vitest, and the School/notification Playwright specs (`sch-007`, `enh-023`,
`enh-005`, `ovs-004`, `enh-007`, `sec-002`).

## 11. Regression risks

| Risk | Mitigation / test |
|---|---|
| All ~15 School email triggers route through `_notify_parent` | `test_sch_007`, `test_enh_014_dispatch`, school email-path test |
| ENH-023 per-recipient commit loop | `test_enh_023` drained; after_commit per iteration |
| OVS-004 forced-failure semantics | `test_ovs_004` drained, asserts `failed` + error |
| Email status now `queued` until the worker runs | worker in docker-compose; sweeper; drain fixture in tests |
| Auth emails accidentally queued | AC11 test; `auth.py` untouched |
| CRM webhook shares `post_optional_webhook` | function unchanged |

## 12. Plan-time refinements (2026-09-30)

Made while writing `docs/superpowers/plans/2026-09-30-enh-014-notification-channels.md`; they supersede the
sections cited:
- §6.1: `normalise_phone` lives in `app/notifications/phone.py`; `deliver`/sweeper in `app/notifications/delivery.py`
  (the worker imports dispatch, so keeping them apart avoids an import cycle).
- §5.2: the 422 applies only to a false→true change. A user whose phone was cleared can still turn channels off;
  the form keeps a checked channel enabled for that reason (§7).
- §6.4: a missing or non-internal link (including `/\…`) becomes the portal home link rather than being dropped,
  because Twilio rejects an empty template variable.
- §7: preferences are fetched after `/auth/me` succeeds (sequential), which keeps today's `/auth/me` error branches
  unchanged; the preferences body is shape-checked and a malformed one is treated as a load failure.
- §10: no axe dependency exists and none is added; the E2E asserts roles, names, 44 px rows and no horizontal
  scroll instead.

## 13. Traceability

Evidence (`School CRM.md` §32, Part B §11) → `DEC-NOT-001` (2026-09-30 extension) → `BR-NOT-001` →
`PRD-NOT-001/002/003` → ENH-014 → ENH-014-AC01…AC14 → `/account/profile` → §4–§6 (DB, API, integration) →
§10 tests → code → release evidence (Twilio sandbox run, test reports).
