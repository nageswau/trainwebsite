# ENH-006 — Self-Service Change Password (Authenticated) — Design

**Status:** Design approved by the user in-session, 2026-09-21 (rate limit by counting audit rows, no
migration; other sessions not invalidated; API-review revisions accepted). **Implemented and verified 2026-09-21** (evidence in the `RTM.md` `ENH-006` row; browser-QA follow-ups in §13).

**Traceability:** `EVID` user instruction ("change password") → `DEC-SCOPE-021` (`EXPLICIT_APPROVAL`) →
`docs/delivery/ENHANCEMENT_BACKLOG.md` ENH-006 → this spec → plan (`docs/superpowers/plans/`) → tests →
code.

**Acceptance-criteria numbering:** `AC-nn` below is local to this spec. Do not cite it from
`API_CONTRACT.md`/`RTM.md` as if it were a source-document ID. Cite `DEC-SCOPE-021` and `ENH-006`.

## 1. Problem (audit result, gap confirmed)

`apps/api/app/api/auth.py` has `forgot_password` (line 175) and `reset_password` (line 198) but no route
for a user who is already signed in. Such a user must log out and use the emailed link, which also never
asks for the current password. (The backlog's line numbers 155/179 and its reference to `accept_invite`'s
rule are stale.)

## 2. Goals and non-goals

**Goals.** A signed-in user of any role can change their own password by supplying the current and a new
one. A wrong current password is refused with one generic error and is rate-limited. The change and the
failures are audit-logged.

**Non-goals (do not do here).**
- Invalidating other sessions, a token version, a `password_changed_at` column, any change to
  `get_current_user`, `create_token` or the JWT claims (`DEC-SCOPE-021` #3).
- Throttling `login`, `forgot_password` or `reset_password` (still the open item in
  `SECURITY_CONTROLS.md` §1).
- A migration, a new table, Redis, or any new dependency.
- A notification email, password history, strength or breach checks beyond the existing 10–128 rule (plus the all-whitespace refusal added by QA-007), a
  confirm-password field.
- An `Idempotency-Key` (§0.2 of the API contract requires one only for financial/record-creating
  endpoints; no idempotency contract exists here).
- Fixing pre-existing drift noticed during review: `API_CONTRACT.md` §0.3 documents an
  `{error_code, message, field_errors}` error body that the code never emits (FastAPI's `{"detail": …}`
  is what every route returns and what the web forms read).

## 3. Decisions taken (`DEC-SCOPE-021`)

| # | Decision |
|---|---|
| 1 | 5 failed attempts / 15 minutes / user; then `429` + `Retry-After`, even for a correct password. Keyed on user id. |
| 2 | The limiter counts `auth.change_password_failed` rows in `audit_logs`; no schema change. |
| 3 | Other sessions are not invalidated. |
| 4 | New password equal to the current one → `422`; no confirm field; failures audited as denied. |
| 5 | A successful change revokes the user's unused password-reset links (`superseded_at`, same transaction; `reset` purpose only). |
| 6 | Accepted risk: other sessions survive a change — a stolen refresh cookie stays usable for up to 14 days (access tokens 60 minutes). Documented, not fixed. |

Alternatives considered for the limiter store: a dedicated attempts table (migration `0034`), counter
columns on `users`, Redis. Rejected because the audit rows are already written, need no schema change and
follow the ENH-003 Re-send precedent (a throttle derived from existing rows). The one real cost is that
the control depends on audit rows not being purged (nothing purges them today; GDPR redaction only edits
the `User` row) and that `audit_logs` has no composite index — the query is per-user and bounded to five
rows, which is adequate at this scale.

**Measured (independent-review follow-up, 2026-09-21).** With 200,009 `audit_logs` rows for one user (far beyond any real account; 4,000 of them `auth.change_password_failed`),
`EXPLAIN (ANALYZE, BUFFERS)` shows the limiter query combining `ix_audit_logs_user_id` and `ix_audit_logs_action` (BitmapAnd) and finishing in about 10 ms
(2.8k buffers hit, sort of 0–5 rows), both when the user is blocked and when not, before the ~250 ms bcrypt call. A composite index
`(user_id, action, created_at)` would shave that further but needs a migration on a growing audit table, which `DEC-SCOPE-021` #2 (no schema change) deliberately
avoids. Accepted; revisit if `audit_logs` growth or a limiter latency budget ever demands it.

## 4. API contract

`POST /api/v1/auth/change-password` — authenticated (access cookie), self only.

Request body (Pydantic `ChangePasswordRequest`, snake_case like the sibling auth routes; passwords are
never stripped or normalised):

| Field | Rule |
|---|---|
| `current_password` | string, 1–1024 characters (bounded so a legacy long password still works and the input is not unbounded) |
| `new_password` | string, 10–128 characters (the rule in `RegistrationRequest`, `reset_password` and the reset form), and **not only whitespace** (QA-007: ten spaces are refused; spaces inside or around real characters are kept exactly) |

Responses (FastAPI `{"detail": …}` body, as everywhere else):

| Status | When | `detail` |
|---|---|---|
| 200 | changed | `{"ok": true}` (same shape as `logout`, `reset-password`) |
| 400 | current password wrong | `"Incorrect current password"` (one message, no other hint) |
| 401 | no/invalid/expired session, inactive account | existing `get_current_user` messages |
| 422 | body shape/length invalid | FastAPI validation list |
| 422 | `new_password` is only whitespace | validation list, `msg` = `"Password must not consist only of spaces"` |
| 422 | `new_password == current_password` | `"New password must be different from the current password"` |
| 429 | 5 failures in the last 15 min | `"Too many incorrect attempts; try again in N seconds"` + `Retry-After: N` (integer, 1–900) |

**Order of checks (part of the contract):**
1. authenticate → 401 (an unauthenticated caller never learns anything about the body shape);
2. body validation → 422 (malformed requests never consume an attempt or run bcrypt);
3. plain string compare `new_password == current_password` → 422 (compares the two inputs only, so it
   reveals nothing about the stored hash and is not an oracle);
4. lock the user row `FOR UPDATE` and refresh its hash in one statement —
   `db.refresh(user, attribute_names=["password_hash"], with_for_update=True)` — because
   `get_current_user` already loaded the row into the session without a lock, so without the refresh a
   waiting request would verify against a stale hash;
5. limiter → 429 (before bcrypt, so a locked-out caller cannot burn CPU);
6. `verify_password(current_password, user.password_hash)` → 400 on failure;
7. write the new hash, revoke the user's unused reset links, add the audit row, commit.

**Safe to retry?** No. If the response is lost after the commit, a retry carries the old password, which
no longer matches: it returns 400 and counts one failure. This is documented in the contract row and the
form's network-error copy tells the user to sign in with the new password rather than resubmit. A shortcut
that treats "current fails but new matches the stored hash" as success was rejected: it would let a caller
check guesses through the new-password field and defeats the re-verification the requirement exists for.

**Authorization.** Self-only by construction (no id in the path or body). Any authenticated, active user
of any role/division; no `require_role`. Cross-user access is impossible, so no resource-scope test beyond
"a change never touches another account" is needed.

## 5. Backend design

- `apps/api/app/schemas.py`: add `ChangePasswordRequest`.
- `apps/api/app/api/auth.py`: add the route plus a small helper
  `_change_password_wait_seconds(db, user_id) -> int` and two module constants
  (`CHANGE_PASSWORD_MAX_FAILURES = 5`, `CHANGE_PASSWORD_WINDOW = timedelta(minutes=15)`). No new module;
  the helper mirrors `resend_wait_seconds` in `services/provisioning.py`.
- Limiter: select the newest `LIMIT` `created_at` values of `AuditLog` rows with this `user_id`,
  `action == "auth.change_password_failed"` and `created_at > now - WINDOW`, newest first. Fewer than
  `LIMIT` rows → 0. Otherwise the wait is `ceil(oldest_of_those + WINDOW − now)` clamped to 1–900 seconds
  (app-side `now(UTC)`, clamped like the Re-send throttle so skew can never produce an absurd wait). A
  successful change does **not** reset the count (YAGNI; the window slides).
- **Failure path:** `db.add(AuditLog(user_id, action="auth.change_password_failed", entity_type="user",
  entity_id, outcome="denied", metadata_json={"reason": "incorrect_current_password"}))`, **commit, then
  raise 400** — the `update_me` denial pattern, so the count survives the error.
- **Blocked path (429):** no audit failure row (otherwise a lockout would extend itself forever), only
  `logger.warning("change_password_throttled", extra_fields={user_id, wait_seconds})`. No writes.
- **Success path:** `user.password_hash = hash_password(new_password)`; `AuditLog(action=
  "auth.change_password", entity_type="user", entity_id, metadata_json={})` in the same transaction;
  the user's unused `reset` password-reset tokens get `superseded_at = now` in the same transaction
  (`DEC-SCOPE-021` #5; welcome, used and other users' tokens are untouched); commit; `logger.info("password_changed", extra_fields={user_id})`. No cookie or token is reissued.
- **Transactions and races.** One transaction, one lock (the user row). Parallel wrong guesses serialize
  on the lock, so two requests cannot both pass the count at attempt 5. A change racing `reset_password`
  cannot deadlock (both lock the user row first). `get_db` closes the session on any exit, releasing the
  lock on the 422/429 paths; `expire_on_commit=False` keeps the user object usable after the failure
  commit. bcrypt runs while the lock is held (as in `reset_password`); acceptable at ~100–300 ms.
- **Logging/secrets.** Only `user_id` and `wait_seconds` are logged; no password, hash or request body.
  Audit `metadata_json` never holds a secret.
- **No existing route, schema, model or migration changes.** New audit action strings are additive (they
  appear in `GET /admin/audit` and the ADM-014 export).

## 6. Frontend design

Reuses the existing design language and helpers; adds no UI primitive. Approved in-session 2026-09-21
(including the two entry-point/form choices marked ★). The repo has no shared Button/Field component, no
`loading.tsx` and no skeleton styles, so none is introduced: forms use `.form`/`.field`/`.btn`/
`.form-error`/`.form-message`, cards use `.action-card`, chrome is `PublicShell`, focus uses `lib/focus.ts`
`refocus`.

**Entry points (a signed-in user must be able to find the page).** The public site header
(`HeaderAuthActions`) renders only on public pages; portal pages use `PortalShell`, which has no header, its
sidebar is hidden at ≤980 px and its mobile menu shows only the role's nav items. So:
- ~~`HeaderAuthActions.tsx`: one new link, "Password", beside "Privacy".~~ **Removed after browser QA (QA-001):** a fifth header button pushed the
  signed-in header past the viewport (Logout off-screen at 1440 px and narrower; 3 px at 1600, 83 px at 1440, 120 px at 1366, 101 px at 768).
  The portal entry points below make it redundant, so the header keeps its original four actions. This reverses one element of the
  2026-09-21 design approval; restoring it needs a header layout change first.
- `apps/web/app/it/employer/dashboard/page.tsx` (QA-003): the Employer dashboard is a standalone page (no `PortalShell`, no site header), so it
  gets its own "Change password" link.
- ★ `PortalShell.tsx` (every portal role): a "Change password" link in the desktop sidebar footer above
  "Sign out", and the same link as the **first** item of the array given to the mobile `MobileNavToggle` (QA-004: last of 17 items meant scrolling
  the menu to find it). Additive only: the desktop `.portal-nav` and each role's `nav` array are unchanged.

**Page** `apps/web/app/account/password/page.tsx` (server), modelled on `/account/privacy` but not a dead end:
renders inside `PublicShell` (skip link, site header, footer; QA-008 added the skip link and a focusable `main#main-content` to `PublicShell`, so every public page
gains one Tab-press access to its content); `serverApi("/api/v1/auth/me")` gates it. Signed-out →
"Sign in required" card — shown **only for an explicit `401`** (QA-002) — whose links are `/it/login?next=%2Faccount%2Fpassword` and the overseas
equivalent (`LoginForm` already honours `?next=`), so the visitor returns to the page after signing in. Any other failure (API down, `5xx`, network)
shows "Temporarily unavailable — your password has not been changed — Try again" instead; `serverApi` now throws an `ApiError` carrying the status
(still an `Error` with the same message, so existing callers are unaffected). The page has its own title, "Change your password" (QA-005). Signed-in →
"← Back to dashboard" (`ROLE_DASHBOARD_PATH[role]`), `h1` "Change your password", "Signed in as …", and the
form inside `.action-card`. `middleware.ts` is unchanged (`/account` is outside its matcher).

**Form** `apps/web/components/ChangePasswordForm.tsx` (client), props `{email, forgotPasswordHref?}`:
- Fields `current_password` (`autocomplete="current-password"`) and `new_password`
  (`autocomplete="new-password"`, `minLength 10`, `maxLength 128`, persistent hint "Use at least 10
  characters."), each with a label; a visually hidden, read-only, non-focusable `username` field carrying the
  email so password managers update the right saved login (never sent). ★ A native "Show passwords"
  checkbox switches both inputs between `password` and `text` (no confirm-password field was chosen, so this
  is the typo safeguard).
- Posts JSON to `/api/v1/auth/change-password`. A second submit event while one is pending is ignored (a
  repeat after success would be a `400` and burn an attempt); the button is `aria-disabled` (not `disabled`, which drops
  keyboard focus to `<body>`, QA-009), the form is `aria-busy`, and a visually hidden polite status announces "Changing your password…".
- Outcomes and focus (a control disabled while busy loses focus, so `refocus` puts it back):

| Outcome | Message | Field / focus | Extras |
|---|---|---|---|
| 200 | "Your password was changed." (`role=status`) | fields cleared; focus → submit button | |
| 400 | server's "Incorrect current password" (`role=alert`) | current field `aria-invalid`, cleared, focused; new password kept | "Forgot your current password?" → `/it/forgot-password` or `/overseas/forgot-password` (none for the global division) |
| 422 | server message (string or list) | new field `aria-invalid`, focused | |
| 429 | "Too many incorrect attempts. Try again in N minutes." from `Retry-After` (static text, not a live countdown; server message if the header is unusable) | focus → submit button | |
| 401 | "Your session has expired…" | focus → submit button | links to both login pages with `?next=` |
| network failure | "…could not confirm whether your password was changed. Sign in with your new password; if that fails, try again." | focus → submit button | never claims success |
| other | server message or "Unable to change password. Try again in a moment." | focus → submit button | |

- A muted note states the limitation of `DEC-SCOPE-021` #3: "You stay signed in on this device. Other
  devices stay signed in until their sessions expire."
- **Loading:** the button label and `aria-busy` (no skeleton: the page is server-rendered from one fast
  request and the repo has no loading pattern). **Empty:** not applicable; the signed-out card is the
  unauthenticated state. **Errors:** the table above.
- **Tap targets (QA-006):** the back link, the "Show passwords" row and the recovery link are at least 24 px tall (WCAG 2.5.8).
- **Responsive/accessible:** works at 375 px with no horizontal scroll, touch target ≥ 44 px, labelled inputs,
  errors announced and tied to the field at fault, fully keyboard-completable (Tab order: current → new →
  show passwords → submit; Enter submits), no animation added (so nothing to gate on
  `prefers-reduced-motion`). Copy must not contain the retired default password or the string "Temporary
  password" (`no-default-password.test.ts`).

## 7. Acceptance criteria

- **AC-01** A signed-in user (any role) with the correct current password and a valid new one gets `200`;
  the new password logs in, the old one no longer does.
- **AC-02** A wrong current password gets `400 "Incorrect current password"`, changes nothing, and writes
  an `auth.change_password_failed` row with `outcome="denied"`.
- **AC-03** After 5 failures in 15 minutes the next attempt — even with the correct password — is `429`
  with an integer `Retry-After`, and the password is unchanged. Failures older than the window do not
  count; the block lifts when the fifth-newest failure ages out; another user is unaffected; a blocked
  attempt writes no new failure row.
- **AC-04** `new_password` under 10 or over 128 characters, only whitespace, or equal to `current_password`, is `422` and
  changes nothing and consumes no attempt.
- **AC-05** A successful change writes exactly one `auth.change_password` row. No password or hash appears
  in any audit row or log record.
- **AC-06** With no session the endpoint is `401` even when the body is also invalid. It only ever changes
  the caller's own account.
- **AC-07** Two simultaneous wrong guesses at attempt 5 yield one `400` and one `429`, never two `400`s;
  a change racing `reset_password` completes without deadlock or `500`.
- **AC-08** The form works at 375 px (no horizontal scroll, touch target ≥ 44 px), is labelled and
  completable by keyboard alone, marks and focuses the field at fault, and shows the submitting, 400, 422, 429,
  401, network-failure and success states; "Show passwords" reveals and hides both fields without losing
  input; a second submit while pending sends no second request; the signed-out page shows the sign-in card
  and returns the visitor to the page after signing in; a portal user (desktop sidebar and mobile menu) and an
  employer (a link on their dashboard) can reach the page, the page links back to the role's dashboard, and the public header still fits the
  viewport (no `Password` link there); an API outage is reported as "Temporarily unavailable", never "Sign in required"; the page has its own
  title; progress is announced and keyboard focus stays on the button while a request runs.
- **AC-09** Existing behaviour is unchanged: login, register, refresh, forgot/reset, `PATCH /auth/me`,
  RBAC/role dependencies and the JWT claims behave exactly as before.
- **AC-10** A successful change leaves the user's unused `reset` links unusable (`reset-password` answers the
  same generic `400`), and does not touch used links, welcome links or another user's links; a refused change
  (400/422/429) revokes nothing.
- **AC-11** Abuse cases: extra body fields cannot change role, division, email, active state or anything but
  the password; a refresh token is not accepted as a session; non-string password values are `422`, never
  coerced; SQL/markup/NUL/astral strings are ordinary wrong passwords (`400`, never echoed, never a `500`);
  such characters round-trip as a new password; a non-JSON content type is `422`; the success response sets
  no cookie.

## 8. Test plan (written first, seen failing)

- **pytest** `apps/api/tests/test_enh_006_change_password.py` — each test creates its own user (never a
  seeded account): AC-01 (login before/after), AC-02, AC-03 (5-then-429; correct password while blocked;
  window expiry by back-dating audit rows; per-user isolation; blocked attempt adds no row), AC-04,
  AC-05 (caplog + audit rows scanned for the secrets), AC-06 (no cookie + invalid body → 401; a change
  never alters another user), AC-07 (`asyncio.gather` of two wrong guesses at attempt 5; a change racing
  `reset_password`), roles (student, admin, school role), inactive account → 401.
- **pytest, security (Task 3b):** revocation of unused `reset` links and its exclusions; mass assignment;
  token-type confusion; type coercion; hostile strings; odd characters as a new password; non-JSON content
  type; no `Set-Cookie` on success.
- **vitest** `apps/web/tests/components/ChangePasswordForm.test.tsx`: request body, busy state and
  `aria-busy`, double-submit guard, 400/422/429/401/network/other rendering with `aria-invalid`, clearing and
  focus, the forgot-password link (and its absence), hidden username field, show-passwords toggle, the
  other-devices note; `apps/web/tests/components/PortalShell.test.tsx`: the sidebar link, the mobile-menu
  item, the untouched desktop nav.
- **Playwright** `apps/web/tests/e2e/enh-006-change-password.spec.ts`: register a throwaway user (never
  change a seeded account's password — other specs log in with it), change through the real page, log out
  and in with the new password; a wrong current password shows the generic error; a 429 after five
  failures; keyboard-only completion; show-passwords; the signed-out card returning to the page after login;
  the signed-in header fitting the viewport at 1600/1440/1366/768 px; the portal sidebar link and back-to-dashboard; the employer dashboard link;
  the page title; 24 px tap targets; focus and announcement while pending; the mobile portal menu at 375 px (no
  horizontal scroll, touch target ≥ 44 px).
- **Regression scope (targeted, not the full backend run — `deps.py` and the JWT are untouched):**
  `test_role_assignments.py`, `test_enh_003_first_time_provisioning.py`, `test_sec_001_audit_trail.py`,
  `test_sec_002_gdpr_data_requests.py`; `ResetPasswordForm.test.tsx`, `no-default-password.test.ts`,
  `auth-001-login.spec.ts`, `auth-002-rbac-ui.spec.ts`, the SEC-002 header e2e, and the portal specs
  `sch-001-school-portal-access`, `adm-014-super-admin-console`, `desktop-nav-dropdown`,
  `stu-011-profile-documents`, `trn-001-mobile-nav` (the `PortalShell` change; it asserts on the portal
  mobile menu).
- Never alter product behaviour merely to make a draft test pass; tests run through real scripts.

## 9. Regression risks and mitigations

| Risk | Mitigation |
|---|---|
| Header layout: a fifth action overflowed the viewport (found by browser QA) | Header link removed; `HeaderAuthActions` unit test asserts exactly two links + Logout; E2E asserts no horizontal overflow at 1600/1440/1366/768 px |
| `PortalShell` is used by every portal role; a layout or selector regression would hit all of them | Additive only (one link, one appended menu item; desktop nav array untouched); unit test on the shell; run the portal E2E specs above |
| New audit actions surface in `/admin/audit` and the ADM-014 export | Additive strings; run `test_sec_001_audit_trail.py` |
| Editing `auth.py` next to the security-reviewed `reset_password` | Add the route below `reset_password`; do not edit existing routes |
| Revoking reset links could disturb ENH-003's welcome/reset state | Only unused `purpose='reset'` rows of the caller; welcome/used/other users' rows asserted untouched; run `test_enh_003_first_time_provisioning.py` |
| E2E/pytest changing a shared seeded password and breaking other suites | Throwaway users only |
| `populate_existing` forgotten → stale user object | Covered by the success test (hash actually changes) |
| A lockout extending itself | Blocked attempts write no failure row (tested) |

## 10. Documentation to update with the code

`API_CONTRACT.md` §1 (new row, incl. "not safe to retry blindly"); `SECURITY_CONTROLS.md` §1 (new
change-password limiter row; the existing "Rate limiting on auth endpoints" row keeps its open status for
login/forgot/reset) and §10 (new audit actions); `RTM.md` (ENH-006 row); `ENHANCEMENT_BACKLOG.md` (ENH-006
status, correct the stale line numbers and the `accept_invite` reference); `PRODUCT_DECISION_REGISTER.md`
(`DEC-SCOPE-021`, already recorded).

## 11. Open, not decided here

Other sessions survive a password change; login/forgot/reset are unthrottled; no notification email; no
password history or strength rules; the `API_CONTRACT.md` §0.3 error-shape drift.

**Found during plan research (2026-09-21), and how it is handled:** the public header renders only on public
pages, `globals.css` hides `.header-actions .btn.secondary` at ≤ 640 px (so "Dashboard", "Privacy" and the new
"Password" are hidden on phones), and `PortalShell` has neither a header nor, at ≤ 980 px, a sidebar. ENH-006
therefore also adds the portal entry point (§6). **Still open, not changed here:** the existing "Privacy" link
has the same reachability gap; inputs render at 15 px, so iOS Safari zooms on focus (site-wide); the header
hiding its actions on phones is a cross-cutting UX question, `NEEDS_CONFIRMATION` whether to address separately.

## 12. Security review (2026-09-21, `security-and-hardening`)

**Threat model.** Boundary: an authenticated browser posting two passwords to one endpoint. Assets: the
account's password hash and its sessions. Attackers: (1) a holder of a stolen session or a forged token,
(2) a cross-site page, (3) a signed-in user probing the endpoint. Verified against the code, plus throwaway
local probes (bcrypt 4.3.0; a bare FastAPI 0.141 / pydantic 2.13 app).

| Area | Evidence | Verdict |
|---|---|---|
| Authentication | `get_current_user`: HS256 only, `type == "access"` (a refresh token is refused), active user; bcrypt cost 12; the current-password check protects even against a forged or hijacked session | OK |
| Authorization / IDOR | no id in the path or body; the target is always the token's user; the lock/refresh targets that same row | OK |
| Role escalation | only `password_hash` is written; unknown JSON fields are dropped (probed) | OK; AC-11 test |
| Input validation | Pydantic bounds; int/bool/list/object are `422`, not coerced (probed); form-encoded and `text/plain` bodies are `422` (probed on FastAPI 0.141 — the container's version is verified by a test); bcrypt 4.3 accepts NUL bytes without raising | OK; AC-11 tests |
| XSS | React escapes; only Pydantic `msg` and fixed strings reach the UI; no `dangerouslySetInnerHTML`; `?next=` is a constant on our side | OK |
| CSRF | cookies `HttpOnly` + `SameSite=Lax` (no cross-site POST carries them); JSON body required; the current password is required. No CSRF token exists app-wide (already recorded in the decision register) | OK, low residual |
| SQL injection | SQLAlchemy expressions and a constant action string only | OK; AC-11 test |
| Token / session | change reissues nothing; other sessions survive by decision | Accepted risk B |
| Secret exposure / logs | response is `{"ok": true}`; the request middleware logs path/method/status/duration only; the logger drops `password`/`token`-named keys; audit metadata is a fixed reason string | OK; log-scan test |
| Rate limiting | shared across instances (database); runs before bcrypt; malformed bodies and the same-password check never count | OK, two accepted trade-offs below |
| Audit | success row in the same transaction (fail-closed); failure row committed before the `400`; nothing purges `audit_logs` (no deletion code, no Celery job) | OK |

**Finding A (fixed in this design):** `forgot_password` never revokes older tokens and `reset_password`
honours any unused, unsuperseded, unexpired one, so a reset link still in the mail could overwrite a freshly
changed password for up to 30 minutes. A successful change now revokes the user's unused `reset` links
(`DEC-SCOPE-021` #5; AC-10).

**Accepted risks (recorded, not changed).**
- **B — session survival.** Access tokens last 60 minutes, refresh tokens 14 days, and `/auth/refresh` does
  not consult the password, so a stolen refresh cookie survives a change for up to 14 days
  (`DEC-SCOPE-021` #6). The smaller alternative that was offered and declined: a `password_changed_at` column
  checked only in `/auth/refresh` (migration; exposure would drop to about 60 minutes).
- A holder of a stolen session can lock the victim out of this route for 15 minutes at a time; forgot-password
  is unaffected.
- Blocked (`429`) attempts are logged, not audited, so a flood cannot grow `audit_logs`; the audit trail has
  no IP or user agent (no audit row does).
- The route limiter covers only this route; `login` is still unthrottled (open item in `SECURITY_CONTROLS.md`).
- bcrypt uses only the first 72 bytes, so a "new" password differing from the current one only after byte 72
  is a string change but the same effective password (pre-existing across register/reset; not addressed here).

**Noted, not changed (pre-existing, outside ENH-006):** no CSP/`X-Frame-Options`/HSTS is set anywhere (the
password page's clickjacking exposure is low: a frame cannot read the fields and a change needs the current
password); `LoginForm` pushes an unvalidated `?next=` (ENH-006 only adds links with a constant `next`);
deployment prerequisites `COOKIE_SECURE=true`, a real `SECRET_KEY` and `ENVIRONMENT=production` are already in
`SECURITY_CONTROLS.md`'s release checklist.

## 13. Browser QA follow-ups (2026-09-21, browser-use, isolated stack `enh006-e2e`)

Exploratory pass over the 20 requested areas. Every fix below was written test-first (the E2E tests were seen failing in the browser first). Round 1 fixed QA-001/002/003/005/006/009; round 2 ("fix the 2", the three low findings left for a decision) fixed QA-004/007/008.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| QA-001 | High | Signed-in header overflowed the viewport because of the new fifth button | **Fixed** — header link removed (see §6) |
| QA-002 | Medium | An API outage rendered "Sign in required" to a signed-in user | **Fixed** — `ApiError` status; "Temporarily unavailable" state |
| QA-003 | Medium | Employers (standalone dashboard) had no entry point | **Fixed** — link on the employer dashboard |
| QA-005 | Low | Page title was the site default | **Fixed** — `metadata.title` |
| QA-006 | Low | Back link / Show passwords row ~20 px tall | **Fixed** — ≥ 24 px |
| QA-009 | Low | Focus dropped to `<body>` while pending; progress not announced | **Fixed** — `aria-disabled` + polite status |
| QA-004 | Low | On a phone "Change password" is the last of 17 portal menu items | **Fixed** — first item of the mobile menu (only this feature's own item moves; no role's menu is reordered) |
| QA-007 | Low | A 10-space password is accepted | **Fixed** for change-password (all-whitespace refused, `422`). **Open, `NEEDS_CONFIRMATION`:** registration and reset still accept it, so the three entry points now differ |
| QA-008 | Low | 17 Tab stops through the site header before the form; no skip link | **Fixed** — skip link + focusable `main` in `PublicShell` (a shared component: every public page gains it) |
| QA-010 | Info | A stale second tab gets "Incorrect current password" with no hint the password changed elsewhere | Accepted, correct by design |

Pre-existing, observed and not changed: the public header already overflowed at 1280 px and below without the new link (43 px at 1280, 277 px at
1024); at 320 px it overflows by 43 px; inputs render at 15 px so iOS Safari zooms on focus; the top announcement bar is clipped at 375 px; the
existing student dashboard shows "Access unavailable / fetch failed" during an outage. Verified fine: no console errors or exceptions across about
40 page loads, no broken images, no unexpected redirects, 17 seeded roles plus a registered employer and agent, a cross-site request could not
change a password (`SameSite=Lax`), garbage and refresh-token cookies were refused.
