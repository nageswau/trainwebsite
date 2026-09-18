# ENH-003 — First-Time Provisioning (Welcome Email + Set-Password Link) — Design

**Status:** Design approved by the user in-session, 2026-09-19 (Approach A; `422` on a stray password
field; API review revisions accepted). Security review of the same day folded in (see §13; the user
approved the auth change, the 60-second Re-send cooldown and the remaining hardening). Implementation
not started.

**Traceability:** `EVID` user instruction ("send an email for first time user creation and updates the
password from mail link") → `DEC-SCOPE-014` (routing constraint) + `DEC-SCOPE-019` (this feature's
five confirmed decisions, `EXPLICIT_APPROVAL`) → `docs/delivery/ENHANCEMENT_BACKLOG.md` ENH-003 → this
spec → plan (`docs/superpowers/plans/`) → tests → code.

**Acceptance-criteria numbering:** `AC-nn` below is local to this spec. Do not cite it from
`API_CONTRACT.md`/`RTM.md` as if it were a source-document ID (the ENH-001 review already removed one
set of fabricated citation IDs). Cite `DEC-SCOPE-019` and `ENH-003` instead.

## 1. Problem (audit result, gap confirmed)

Three routes in `apps/api/app/api/admin.py` create accounts with the hard-coded fallback password
`ChangeMe@12345` and send no email: `POST /admin/users` (`create_user`), `POST /overseas-admin/schools`
(Coordinator seed via `coordinator_password`) and `POST /overseas-admin/school-staff`
(`create_school_staff`, the route `DEC-SCOPE-014` actually mandates for `academic_team`/
`career_counselor`/`psychometric_team`). Two admin panels display the default password; `WorkflowPanel`
asks for a "Temporary password". `forgot_password()` only posts to the generic webhook and
`services/mailer.py` has no password-link template.

## 2. Goals and non-goals

**Goals.** No admin ever knows or chooses a credential for an account they provision. Every
admin-provisioned account receives a single-use, hashed-at-rest, 72-hour set-password link by email.
Admins can see links that expired unused, and Re-send.

**Non-goals (do not do here).**
- Any change to `SchoolAccountInvite`/`accept_invite()` (`DEC-SCOPE-014`).
- Any change to self-registration, employer/agent registration, `forgot_password`'s response shape, or
  `get_current_user`/`ensure_admin`.
- Fixing pre-existing issues noticed during review: `create_user` raises `KeyError` (→ `500`) when
  `role` is missing; `GET /admin/users` is capped at 500 rows with no pagination; `forgot_password`
  never revokes earlier unused tokens.
- Migrating existing accounts that still hold the `ChangeMe@12345` password. `NEEDS_CONFIRMATION`: a
  read-only script listing such accounts was offered; the user has not yet asked for it.
- A retry/backoff policy for failed sends (`PRD_OPEN_ITEMS.md` item 13). Recovery is admin Re-send.
- An `Idempotency-Key` header (no idempotency contract exists; see §7).

## 3. Approach

**Chosen: extend `PasswordResetToken` + one small service.** Rejected: a new
`AdminProvisionedAccountToken` table with its own endpoint/page (duplicates hashing/expiry/consumption,
adds public attack surface); generalizing the invite flow so the account is created on accept
(violates `DEC-SCOPE-014`, breaks directory rows and `school-staff` portfolio assignment at creation).

**Existing-convention choices (deliberate deviations from generic API guidance):** snake_case fields;
lowercase enum values; errors are FastAPI `{"detail": "<string>"}`; raw `dict` payloads with inline
validation (no Pydantic layer for these routes); no new Pydantic response models.

## 4. Data model

Migration `0032_welcome_token_purpose` (additive; guarded with the same `sa.inspect` checks `0030`
uses; downgrade drops both columns):

| Column (`password_reset_tokens`) | Type | Notes |
|---|---|---|
| `purpose` | `String(20)`, NOT NULL, `server_default 'reset'` | `reset` \| `welcome`. Default backfills all existing rows. **No index** (two values, no selectivity; `user_id` index already serves the queries). **No CHECK** (matches sibling status columns). |
| `superseded_at` | `DateTime(timezone=True)`, nullable | Set when Re-send replaces an unused token. |

`models.PasswordResetToken` mirrors both with `default="reset"`/`server_default="reset"`. No change to
`users`. New accounts get a hash of a random secret that is discarded (never a constant).

## 5. Service — `apps/api/app/services/provisioning.py` (new; functions only)

- `WELCOME_EXPIRY_HOURS = 72`; `DEV_TOKEN_ENVIRONMENTS = ("development", "test")`.
- `unusable_password_hash() -> str` — `hash_password(secrets.token_urlsafe(48))`.
- `issue_welcome_token(db, *, user, issued_by) -> IssuedWelcome(raw, expires_at, token_id)` — no commit.
  Revokes (sets `superseded_at` on) the user's open welcome tokens, inserts the new token
  (SHA-256 hash, `purpose="welcome"`), writes a `user.welcome_link_issue` audit row (token id + expiry,
  never the raw token), flushes. Does not lock (the create path has a brand-new row; the Re-send route
  locks).
- `deliver_welcome_link(db, *, user, issued, issued_by) -> dict` — called **after** the caller's
  commit. Runs `mailer.send_welcome_email` and the existing generic webhook (`send_notification`,
  parity with the invite flow) concurrently via `asyncio.gather`; records a
  `user.welcome_link_delivery` audit row (`smtp_status`, `smtp_error`, `webhook_status`,
  `webhook_error`; errors are URL-redacted); commits. **Never raises:** a sender that raises counts as a
  failed send, and an audit-write failure is logged via `logging.getLogger("app.provisioning")` while the
  computed send status is still returned. Returns
  `{"email_status": "sent"|"failed"|"not_configured", "expires_at": ...}` plus
  `"development_welcome_token"` iff `settings.environment in DEV_TOKEN_ENVIRONMENTS`.
- `provisioning_statuses(db, user_ids) -> dict[UUID, Provisioning(status, expires_at)]` — derived from
  each user's **latest** welcome token (superseded ones included). Absent (⇒ `active`) if that token was
  used, or any token was used at/after its creation (e.g. forgot-password). Otherwise `pending_setup` if
  it is unsuperseded and unexpired, `link_expired` if it expired **or was revoked/superseded with
  nothing newer**. Two queries per call; no N+1.
- `revoke_welcome_tokens(db, user_id)` and `resend_wait_seconds(db, user_id)` — see §13.
- `user_ids_with_status(db, actor, status) -> list[UUID]` — active users whose derived status equals
  `status` (`pending_setup` | `link_expired`), division-scoped like `GET /admin/users` (`super_admin`
  unrestricted); the exact set, so the directory filter is not hidden by the 500-row cap.

`services/mailer.py` gains `send_welcome_email(*, to_email, recipient_name, role, set_password_url,
expires_at, invited_by_name) -> (status, error)` with the same `not_configured`/`sent`/`failed`
contract, HTML + text parts, names passed through `html.escape`. Link:
`{frontend_url}/{overseas|it}/reset-password?token=<raw>` (`overseas` iff the account's division is
`overseas`, else `it`, as `super_admin` already logs in via `/it`).

## 6. Endpoints and transaction flow

### 6.1 Create routes — `POST /admin/users`, `/overseas-admin/schools`, `/overseas-admin/school-staff`

Order: authentication → authorization (existing `403`s) → **`422`** if the payload contains `password`
(`coordinator_password` on schools) — `"password is not accepted; the user sets their own via the
emailed link"` → existing validation → duplicate-email `409` fast path.

Transaction 1: create user (`unusable_password_hash()`), role assignment / school links as today,
`issue_welcome_token`, existing creation audit rows; `flush` wrapped so an `IntegrityError` on the
unique email returns `409` (precedent `admin.py:1011`) rather than `500`; `commit`. Then
`deliver_welcome_link`. Response = existing fields **plus** `email_status`, `expires_at`,
(dev/test) `development_welcome_token`. No key in any response contains "password".

### 6.2 `POST /auth/reset-password` (existing)

Order unchanged: length check (`422`) first, so a too-short password never burns the link. Then one
atomic `UPDATE password_reset_tokens SET used_at = now WHERE token_hash = :h AND used_at IS NULL AND
superseded_at IS NULL AND expires_at > now RETURNING user_id, purpose`. Zero rows → the existing
`400 "Reset token is invalid or expired"` (same message for used/expired/superseded/unknown, so callers
cannot distinguish). If the user is missing after the update, the raised error rolls the update back.
`purpose == "welcome"` additionally sets `users.email_verified = True`. Audit action
`auth.welcome_password_set` (welcome) or `auth.password_reset` (reset).

### 6.3 `POST /admin/users/{user_id}/welcome-links` (new) → `201`

`ensure_admin`; `SELECT … FOR UPDATE` on the user row; then `404` (missing) → `403` (other division,
same rule as `update_user`) → `409` "no pending invitation (password already set)" if
`provisioning_statuses` has no entry → `409` if the account is deactivated. Then
`issue_welcome_token`, commit, `deliver_welcome_link`. Returns `{id, email_status, expires_at}`
(+ dev token in dev/test). Works only on accounts that never set a password and sends only to that
account's own email, so it cannot reset an active account.

### 6.4 `GET /admin/users` and `GET /admin/dashboard` (existing, additive)

`GET /admin/users` rows gain `provisioning_status` (`active`|`pending_setup`|`link_expired`). New
optional `?provisioning_status=` filter (`pending_setup`|`link_expired`; other value → `422`), applied by
resolving the exact user-id set first so the existing 500-row cap cannot hide matches. `GET
/admin/dashboard` gains integer `expired_welcome_links` (division-scoped). No test currently pins the
dashboard shape.

## 7. Concurrency, retries, errors

- **Single-use under concurrency:** atomic consume (6.2); two simultaneous submissions → exactly one `200`.
- **Concurrent Re-send:** serialized by the user-row lock; the second supersedes the first; only one open
  welcome token per user.
- **Accepted residual race:** Re-send read at the same instant the user completes setup can leave one
  spare welcome token that shows `pending_setup`. It only ever goes to the account owner's own email;
  not mitigated further (YAGNI).
- **Unknown outcome:** an issue-audit row with no delivery-audit row means the process died between
  commit and send; Re-send resolves it.
- **Retry semantics (documented, no header):** repeating a create → `409` (no duplicate account);
  Re-send is intentionally not idempotent — each call supersedes the previous link. The UI disables the
  button while a request is in flight.
- **Send failure / `not_configured`:** never blocks or rolls back account creation; response carries
  `email_status`; audit keeps the truncated error; the raw error text is not returned to the client.
- **Raw token exposure:** only in the e-mail body/webhook payload and, in dev/test only, the response.
  Never in the database, audit metadata, logs or any production response.

## 8. Frontend

- `AdminSchoolStaffPanel`, `AdminSchoolCreatePanel`: replace the default-password message with "set-password
  link emailed, valid 72 hours"; if `email_status !== "sent"` show a warning naming the status and pointing
  to Re-send. Keep existing `role="status"`/`aria-live` semantics.
- `WorkflowPanel`: remove the "Temporary password" field from the create-user spec; mount the new
  `AdminExpiredLinksPanel` when `section === "dashboard"` and role ∈ {`it_admin`,`overseas_admin`,`super_admin`}.
- `AdminUserManagementPanel`: status badge from `provisioning_status`; "Link expired" filter; Re-send
  button (busy / success / failure message; extra warning when `email_status !== "sent"`).
- `AdminExpiredLinksPanel` (new, client): fetches `/api/v1/admin/users?provisioning_status=link_expired`;
  **loading**, **empty** ("No expired links"), **error** (message + retry) states; per-row Re-send.
- Super Admin dashboard (`apps/web/app/admin/page.tsx`, server-rendered, separate from `PortalPage`):
  metric tile from `expired_welcome_links` + link to `/admin/users`; users table (`admin/[module]/page.tsx`
  `userColumns`) gains a "Setup" column from `provisioning_status`.
- `ResetPasswordForm`: on a `400`, append "Ask your administrator to re-send your invitation, or use
  'Forgot your password?' on the sign-in page."

## 9. Acceptance criteria (each is a test)

| ID | Criterion |
|---|---|
| AC-01 | Each of the 3 create routes returns `422` when `password` (`coordinator_password` for schools) is present, and creates no user row. |
| AC-02 | A newly created account cannot log in with `ChangeMe@12345` or any supplied password (`401`); `apps/api/app` contains no `ChangeMe@12345` literal. |
| AC-03 | Exactly one welcome token per account: `purpose="welcome"`, stored as SHA-256 of the raw value (raw never stored), `expires_at` = creation + 72 h (±1 min). |
| AC-04 | Create response is `201` with `email_status` ∈ {`sent`,`failed`,`not_configured`} and `expires_at`; no key contains "password"; `development_welcome_token` present iff environment ∈ {development, test}. |
| AC-05 | The composed e-mail goes to the account's address, contains the `/{overseas|it}/reset-password?token=` link and a 72-hour statement, and no password. |
| AC-06 | A `failed`/`not_configured` send still returns `201`, keeps the account and token, and writes a delivery audit row with the status; no audit `metadata_json` contains the raw token. |
| AC-07 | Submitting the link with a ≥10-char password returns `200`, the user can then log in, `email_verified` is `True`, and the token is `used_at`-stamped. |
| AC-08 | A second use returns the same `400`; two concurrent uses yield exactly one `200`. |
| AC-09 | An expired welcome token returns the same `400`. `reset`-purpose tokens keep the 30-minute expiry and do not set `email_verified`. |
| AC-10 | Re-send returns `201`, sets `superseded_at` on the old token (now `400` on use), issues a token valid for 72 h; only one open welcome token remains. |
| AC-11 | Re-send: `404` unknown user; `403` other division; `409` account already active; `409` deactivated; non-admin is refused. |
| AC-12 | `provisioning_status` is `pending_setup` / `link_expired` / `active` correctly, including: password set via forgot-password ⇒ `active`; a Re-send's older superseded token never makes the account read expired (the newest token wins); deactivated users excluded from the expired filter. |
| AC-13 | `GET /admin/users?provisioning_status=link_expired` returns exactly the in-scope expired users, `it_admin` never sees overseas users, `super_admin` sees all, an unknown value returns `422`, and every row carries `provisioning_status`. |
| AC-14 | `GET /admin/dashboard` includes integer `expired_welcome_links`, division-scoped. |
| AC-15 | Backward compatibility: all existing `SchoolAccountInvite`, forgot-password, reset-password, `test_sch_*` and admin-CRUD tests pass unchanged (helpers that logged in with a supplied password move to the dev-token flow). |
| AC-16 | Two simultaneous creates for one email return one `201` and one `409` (no `500`). |
| AC-17 | Migration `0032`: upgrade adds both columns, existing rows read `purpose='reset'`; downgrade restores; no row is lost. |
| AC-18 | UI: no password text/field on the three surfaces; warning shown when `email_status !== "sent"`; directory shows status/filter/Re-send with busy/success/error; expired panel shows loading/empty/error; reset form shows the re-send hint on `400`; labels and live regions accessible; usable at 375 px. |
| AC-19 | E2E: create staff → activate with dev token → log in → reach dashboard; Re-send from the directory works; `grep -r "ChangeMe@12345" apps/web` returns nothing. |
| AC-20 | Audit rows exist for issue, delivery, Re-send and password-set, none containing the raw token or any password. |
| AC-21 | Each create route returns `422` and creates no user for a malformed email: no `@`, whitespace, no dot after `@`, embedded CR/LF, longer than 255 characters, or blank. |
| AC-22 | A sender that raises (e.g. `ValueError`) never turns a committed creation into a `500`: the response is `201` with `email_status: "failed"` and the delivery audit row records `failed`. |
| AC-23 | Welcome links are refused (same generic `400`, token not consumed) for inactive accounts; any real change of `active` revokes the account's open welcome links; reactivation needs an explicit Re-send; a PATCH that leaves `active` unchanged revokes nothing. |
| AC-24 | Re-send: the first call after creation is allowed; a second within 60 s returns `429` with a positive integer `Retry-After` ≤ 60 and issues nothing; it succeeds once the cooldown has passed. |
| AC-25 | Stored delivery errors contain no URL (replaced by `[redacted-url]`). |
| AC-26 | `POST /auth/reset-password` rejects a password over 128 characters with `422` without consuming the token; exactly 128 succeeds. |
| AC-27 | The reset page is never configured in Google Analytics (`gtag('config')` skipped on `/reset-password` paths) and is served with `Referrer-Policy: no-referrer`. |
| AC-28 | A revoked welcome link with nothing newer reads `link_expired` and stays Re-sendable (never stuck). |
| AC-29 | Deployment: the API's `ENVIRONMENT` is `production` outside local development (release checklist in `SECURITY_CONTROLS.md`); a `production` API never returns `development_welcome_token`. |

## 10. Test plan (written before the code, per task)

- **Pytest** `apps/api/tests/test_enh_003_first_time_provisioning.py` (new) — AC-01…14, 16, 17, 20; the
  concurrency cases use `asyncio.gather`; e-mail content via monkeypatching `mailer._send_sync` with
  `settings.smtp_host` set (pattern of `test_mailer.py`); the source-guard test greps `apps/api/app`.
- **Existing suites migrated in the same task that changes behavior:** `_create_school` in
  `test_sch_003_school_onboarding.py` and `_create_school_with_coordinator` in
  `test_enh_001_academic_year.py` (both send `coordinator_password` and log in with it) → dev-token
  activation. `test_sch_school_staff_provisioning.py` needs re-checking, not assumed.
- **Playwright:** new `enh-003-first-time-provisioning.spec.ts` (AC-18/19); shared helper
  `tests/e2e/helpers/welcome.ts`; mechanical migration of the 37 `ChangeMe@12345` occurrences across 13
  specs (`sch-004-005-006` 7, `sch-008` 8, `sch-roster-parent-invite` 3, `sch-010` 3, `sch-009` 3,
  `sch-team-management` 2, `sch-reports` 2, `sch-007` 2, `sch-003` 2, `sch-001` 2, `sch-011` 1,
  `sch-002` 1, `enh-001` 1; the other 6 repo-wide hits are `admin.py` 3, the two admin panels, and the
  backlog). Specs that create the account through the UI form switch to the API (dev token) with the UI
  form covered once in the new spec.
- **Regression cadence:** targeted suites per task; **one** full backend run at the end because
  `admin.py`/`auth.py` are shared; Playwright only for touched specs.
- **Environment:** DB-dependent steps (migration, pytest, Playwright) run only when the user confirms
  their docker stack is up.

## 11. Regression-risk table

| Risk | Mitigation |
|---|---|
| 37 e2e occurrences (13 specs) and 2 pytest helpers depend on the default/supplied password | Dev-token helper; migrate in the same task as the behavior change; `grep` gate (AC-19). |
| `reset_password` is shared with forgot-password | Behavior for `purpose='reset'` unchanged; atomic-update rewrite covered by existing AUTH-001 tests + AC-08/09. |
| Admin response/`GET /admin/users` shape | Additive keys only (`email_status`, `expires_at`, `provisioning_status`); no test pins them. |
| A `422` for a stray `password` breaks a caller | Only our UI and tests call these routes; documented in `API_CONTRACT.md`; error text is explicit. |
| SMTP unset in the target environment ⇒ unreachable accounts | `email_status` + UI warning + Re-send; forgot-password remains a fallback. |
| Two external calls add latency to create | Sent after commit, concurrently (~10 s worst case). |
| Legacy accounts (default password) cannot be Re-sent | Re-send `409` message explains; read-only audit script pending the user's decision. |

## 12. Documents to update on completion

`docs/architecture/API_CONTRACT.md` (§1 auth, §5 admin, §12A school), `docs/quality/RTM.md`,
`docs/ux/SCREEN_CATALOG.md`, `docs/architecture/DATA_MODEL.md` (`password_reset_tokens`),
`docs/architecture/SECURITY_CONTROLS.md` (credential provisioning); `graphify update .` after code changes.

## 13. Security review (2026-09-19) — amendments to §5, §6 and §9

Method: `security-and-hardening` (threat model → STRIDE per boundary), each item checked against the
code. Boundaries: admin create/Re-send requests, the public reset endpoint, the emailed link, the
webhook/SMTP senders, the audit log, and the browser (analytics, Referer, history). Assets: the
set-password token (a credential), account ownership, admin/user mailboxes.

| # | Sev | Finding (evidence) | Change |
|---|---|---|---|
| S1 | High | `gtag('config')` (`Analytics.tsx`) reports the full URL, query string included → a live token would reach Google when `NEXT_PUBLIC_GA_ID` is set. | Skip `gtag('config')` on `/reset-password` paths; serve the reset routes with `Referrer-Policy: no-referrer` (+ `Cache-Control: no-store`, best effort). |
| S2 | High | `reset_password` never checked `users.active`; a link mailed to a mistyped address could be used, or revived by reactivation. | Refuse welcome links for inactive accounts (generic `400`, rolled back, token not consumed); `update_user` revokes open welcome links on any real change of `active`; the account then reads `link_expired` and needs an explicit Re-send. Status is derived from the **latest** welcome token so a revoked link never leaves the account stuck. |
| S3 | Med | Create routes accepted any email string; `mailer` built headers outside its `try` → `ValueError` → `500` after commit. | Validate email with the repo pattern (≤ 255) → `422`; build the message inside the mailer's `try`; `gather(..., return_exceptions=True)` so a raising sender is a failed send. |
| S4 | Med | No rate limiting anywhere in the API; Re-send could flood a mailbox. | Per-account 60-second cooldown: `429` + `Retry-After`; the first Re-send after creation is always allowed (approved by the user). |
| S5 | Med | httpx error text embeds the webhook URL (possibly with a secret); audit rows persisted it. | Redact `https?://\S+` from the stored SMTP/webhook errors. |
| S8 | Low | No upper bound on `new_password`; bcrypt 4.3 silently ignores bytes past 72. | `422` above 128 characters (the registration schemas' cap). |

**Checked, no change:** token 256-bit random, SHA-256 at rest, single-use atomic, expiring; bcrypt runs
only after a valid token (invalid requests cannot burn CPU); login of an unusable-hash account → `401`;
create/Re-send gates and division scoping (IDOR), row lock, no role/email mutation, Re-send only mails the
account's own address; SQLAlchemy parameterization and the filter allowlist; React escaping plus
`html.escape` in the email; link built from `settings.frontend_url`, never the `Host` header; cookies
`HttpOnly`/`SameSite=Lax`, CORS limited to `frontend_url`, JSON bodies required (no CSRF-token machinery,
none exists repo-wide); request log records path only, JSON formatter redacts token-like keys; audit rows
never hold the raw token.

**Accepted risks:** the raw token also goes to the configured `EMAIL_WEBHOOK_URL` (parity with
forgot-password/invites; some deployments rely on the webhook alone) — it must be HTTPS and trusted; the
one extra email a first Re-send can produce right after creation; a Re-send racing the user's completion
can leave one spare welcome token that only ever reaches the account owner's mailbox.

**Deployment checklist (not code):** the API's `ENVIRONMENT` must be `production` outside local
development. The API reads it from `.env`; the code default and `.env.example` are `development`; the
compose file's `production` default applies only to the *web* service. Left at `development`, responses
carry `development_welcome_token` and — pre-existing, unrelated to ENH-003 — `forgot_password` returns
`development_reset_token` to anonymous callers.

**Observed, out of scope (not changed):** no rate limiting on login/forgot-password/reset;
`secret_key` defaults to `"change-me"`; `cookie_secure` defaults to `False`; `SchoolAccountInvite` links
carry their token in the URL path and are reported to Google Analytics; issued JWTs are not revocable.
