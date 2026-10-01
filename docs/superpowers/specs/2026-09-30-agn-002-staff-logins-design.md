# AGN-002 — Agent Staff Logins: Design

**Status:** draft for owner review (2026-09-30). **Branch:** `feature/agn-002-staff-logins`.
**Decision:** `DEC-SCOPE-040` (S1–S6). **Backlog:** `ENHANCEMENT_BACKLOG.md` §AGN-002 (AGN-002-AC01…AC10).
**Builds on:** `AGN-001` (`DEC-SCOPE-038`, spec `2026-09-28-agn-001-multi-tenant-agent-crm-design.md`, migration `0046_agent_orgs`).
**Reviewed with:** api-and-interface-design, frontend-ui-engineering, security-and-hardening (in-session, 2026-09-30).

## 1. Intent

An agency's Master creates, edits, deactivates, reactivates and resets staff logins. A staff member gets an
auto-generated code `<PREFIX>-S###` and works on the organisation's students and applications, but never on the
team or on commissions.

**From the owner (`DEC-SCOPE-040`, EXPLICIT_APPROVAL):** S1 organisation-wide student/application access for
staff, team + commissions Master-only; S2 `role='agent'` + member role `staff`, own staff counter; S3 reset =
unusable password + emailed set-password link + existing sessions end; S4 name/email/phone, email fixed, no staff
cap, per-agency throttle; S5 Master deactivates/reactivates staff; S6 other organisation's Master gets nothing,
every action audited.

**Design answers (owner, in-session 2026-09-30):**
- **E1 — Sessions:** a `users.session_version` counter carried in every token (not a timestamp).
- **E2 — Throttle:** staff creations + resets have their own budget, **20 per agency per rolling 24 h**, separate
  from the Master-invite budget (10).
- **E3 — Reactivation:** only restores the login. A staff member who never set a password shows "Link expired";
  the Master presses **Reset** to send a new link.
- **E4 — Admin `PATCH /users`:** left unchanged (known limitation, §10).

**Assumptions stated by design (owner may correct):**
- **E5** A deactivated staff member can still be edited (name/phone); reset of a deactivated staff member is `409`.
- **E6** Deactivation also increments `session_version` (security review, §8): reactivation must not revive
  sessions from before the deactivation (e.g. a lost device's 7-day refresh cookie).
- **E7** Reset also respects the existing per-account 60-second link cooldown (`RESEND_COOLDOWN_SECONDS`).

## 2. Out of scope

Staff assignment/ownership and "assigned students only" visibility, staff performance, permission levels,
designation/branch/joining date/username fields, CRM settings (all still blocked under `C-10`). Master reset or
reactivation (D8 unchanged). Admin management of agency members. Changes to change-password / forgot-password.

## 3. Approaches considered

| Concern | Chosen | Rejected and why |
|---|---|---|
| Staff numbering | `agent_orgs.staff_seq`, incremented under the existing organisation row lock (mirrors `master_seq`) | `max(seq)+1` — relies on member rows never being deleted |
| Master-only enforcement | `rbac.is_agent_staff(user)` checked at the few Master-only points | A permission in `ROLE_PERMISSIONS` — staff share `role='agent'`, the role table cannot tell them apart |
| Session end | `session_version` claim (`sv`) | `sessions_valid_after` + `iat` — second granularity can reject a login made in the same second |
| Staff list API | New paginated `GET /team/staff` | Adding `staff` to `GET /team` — unbounded list, and changes an existing response |
| Nav for staff | `agent_member_role` on `GET /auth/me` only | On shared `UserOut` — login/refresh do not load `agent_membership` (`lazy="raise"`) |
| UI | Three small components beside `AgentTeamPanel` | Growing `AgentTeamPanel` (188 lines, own confirm/focus state) past 400 lines |

No new dependencies.

## 4. Data model — migration `0047_agent_org_staff` (additive)

- `agent_orgs.staff_seq INTEGER NOT NULL DEFAULT 0`, `CHECK (staff_seq >= 0)` (`ck_agent_orgs_staff_seq`).
- `agent_org_members`:
  - `ck_agent_org_members_role`: `role = 'master'` → `role IN ('master', 'staff')`.
  - `uq_agent_org_members_org_seq (org_id, seq)` → `uq_agent_org_members_org_role_seq (org_id, role, seq)`.
  - `uq_agent_org_members_code`, `uq_agent_org_members_user` and the status check unchanged (`active|deactivated`
    already allows staff to move both ways; D8's "Masters cannot be reactivated" stays a service rule).
- `users.session_version INTEGER NOT NULL DEFAULT 0` (server default, so existing rows need no backfill).
- **Data:** no existing row changes. **Downgrade:** raises if any `role = 'staff'` member exists (never silently
  deletes logins); otherwise restores the old constraints and drops the two columns.
- Models: `AgentOrg.staff_seq`, `User.session_version`, `AgentOrgMember` constraints and docstring.

Codes: `staff_code(prefix, seq) = f"{prefix}-S{seq:03d}"` (`ABC-S001`; `ABC-S1000` after 999; fits `String(16)`
with the 8-char prefix maximum).

## 5. Sessions (`core/security.py`, `api/deps.py`, `api/auth.py`)

- `create_token(..., session_version: int = 0)` adds claim `"sv"`. `_set_auth_cookies` passes
  `user.session_version`.
- `get_current_user` and `/auth/refresh`: after loading the active user, `p.get("sv", 0) != user.session_version`
  → `401 "Session ended"` (reworded after browser QA-03 to "Your session has ended. Please sign in again."; a deactivated staff
  member is told "Your account was deactivated by your agency. Contact your agency's Master." — QA-02). A token without `sv`
  counts as `0`, so the deploy logs nobody out.
- Incremented by: staff **reset** (S3) and staff **deactivation** (E6). Nothing else changes it.
- Window: a request that already passed the check when the reset commits may complete; the next one is refused.
- Login issues tokens carrying the current version, so signing in again after a reset works immediately.

## 6. API (`api/agent_team.py`, `schemas.py`)

Conventions kept from the codebase: FastAPI `{"detail": "..."}` errors, snake_case fields, action sub-resources
for state changes (as AGN-001 `POST /masters/{id}/deactivate` and `/agent-orgs/{id}/{action}`), `{items, total,
limit, offset}` pagination (as `GET /overseas-admin/agent-orgs`).

**Guard.** `_require_master(user)` additionally requires `user.agent_membership.role == "master"`; staff →
`403 "Only an agency Master can manage the team"`. It already requires role `agent`, division `overseas` and
`agent_denial_reason` = none (active organisation, active membership). This also closes the existing Master
routes (`GET /team`, invite, deactivate) to staff.

**Member shape (staff):**
`{id, code, full_name, email, phone, status: "active"|"deactivated", setup: "pending_setup"|"link_expired"|null}`
(`setup` from `provisioning_statuses`; `null` = password set).

| Method + path | Body | Success | Errors |
|---|---|---|---|
| `GET /team` | — | unchanged shape; `masters` now filtered to `role='master'` | as today |
| `GET /team/staff?limit=1..100 (25)&offset>=0` | — | `200 {items, total, limit, offset}`, ordered by `seq` | `403` staff / not Master |
| `POST /team/staff` | `AgentStaffCreate` | `201 {member, email_status, expires_at}` | `409` email exists; `422` validation; `429` throttle |
| `PATCH /team/staff/{member_id}` | `AgentStaffUpdate` | `200 {member}` | `404`; `422` empty body / unknown field (incl. `email`) |
| `POST /team/staff/{member_id}/deactivate` | — | `200 {member}` | `404`; `409 "Already deactivated"` |
| `POST /team/staff/{member_id}/reactivate` | — | `200 {member}` | `404`; `409 "Already active"` |
| `POST /team/staff/{member_id}/reset` | — | `200 {member, email_status, expires_at}` | `404`; `409 "Reactivate this staff member first"`; `429` |

- `404 "Staff member not found"` for an unknown id, another organisation's member, **or a Master's id** — the
  lookup is `id = :id AND org_id = caller's org AND role = 'staff'`, so nothing is disclosed across tenants.
- `development_welcome_token` is always removed from responses (as AGN-001 invite).
- **Schemas:** `AgentStaffCreate` = the `AgentMasterInvite` fields and validators (subclass, own docstring:
  `full_name` 1–160 trimmed non-blank, `email` pattern + ≤ 320 lowercased server-side, `phone` ≤ 40 optional).
  `AgentStaffUpdate`: `full_name` (same rules) and `phone` (≤ 40; `null` or `""` clears), both optional,
  `model_config = {"extra": "forbid"}`; no field supplied → `422 "Nothing to update"`.
- **Retry semantics:** none of these is idempotent by key. Create retried with the same email → `409` (natural
  key). Deactivate/reactivate repeated → `409`. Reset repeated within 60 s → `429`. The UI blocks double submits.
- `GET /auth/me` adds `agent_member_role: "master"|"staff"|null` (additive; login/refresh/`PATCH /me` omit it →
  `null` default in `UserOut`).

## 7. Service layer (`services/agent_orgs.py`) — functions, no commit, caller holds `lock_org`

- `STAFF_ACTION_LIMIT = 20`; `_invite_wait_seconds` becomes `_wait_seconds(db, org_id, actions, limit)`; Master
  invites call it with the two invite actions and `INVITE_LIMIT` (behaviour unchanged); staff create/reset with
  `("agent_org.staff_create", "agent_org.staff_create_rejected", "agent_org.staff_reset")` and 20.
- `create_staff(db, org, actor, *, full_name, email, phone)` → `(member, user, issued)`:
  throttle → existing email → audited `agent_org.staff_create_rejected` (committed, counted, then `409`, as
  `_reject_invite`) → `User(role="agent", division="overseas", password=unusable, active=True,
  email_verified=False, profile={"registration_source": "agent_staff_create"})` → `flush_unique_email` (race →
  same rejected path) → approved `UserRoleAssignment` → `org.staff_seq += 1` → `AgentOrgMember(role="staff",
  seq, code, status="active", invited_by_user_id=actor)` → `issue_welcome_token` → audit `agent_org.staff_create`.
- `update_staff(db, org, member_id, actor, changes)` → sets `full_name`/`phone` on the user; audit
  `agent_org.staff_update` with `fields: [...]` (names only, no values).
- `deactivate_staff` → member `deactivated` + `deactivated_at/by`; `user.active = False`;
  `user.session_version += 1`; `revoke_welcome_tokens`; audit `agent_org.staff_deactivate`.
- `reactivate_staff` → member `active`, clear `deactivated_at/by`; `user.active = True`; `revoke_welcome_tokens`
  (a link must not come back to life, as admin reactivation); audit `agent_org.staff_reactivate`.
- `reset_staff` → deactivated → `409`; throttle; `resend_wait_seconds(user)` → `429`; `password_hash =
  unusable_password_hash()`; `session_version += 1`; `issue_welcome_token` (revokes the old link); audit
  `agent_org.staff_reset`.
- `_staff_member(db, org, member_id)`: `select … where id, org_id, role='staff'` with `populate_existing`, `404`
  when absent; the target `User` loaded with `populate_existing`.
- Master-only rules filter `role == "master"`: `count_active_masters`, `deactivate_master` (target lookup and the
  "another Master can sign in" query), `notification_recipients` (D12).
- Audit rows: `user_id=actor`, `entity_type="agent_org"`, `entity_id=org.id`, `outcome`, `metadata_json =
  {"member_id", "code", …}` — never an email address, password or token.

**Transactions and races.** Each route: `_locked_active_org` (row lock, re-checks `active`) → service → build the
response → `commit` → (create/reset only) `deliver_welcome_link` after the commit, so an SMTP failure never rolls
back the account and no transaction is held across SMTP. The organisation lock serialises codes, throttle counts
and state changes for one agency; two concurrent creates get `S001`/`S002`. Lock order is organisation → user
row; `reset-password` locks user → token and never the organisation, so no cycle. A Master deactivated or an
organisation suspended mid-request is caught by the re-check under the lock.

## 8. Authorization outside the team routes

| Where | Change |
|---|---|
| `core/rbac.py` | `is_agent_staff(user)`: `role == "agent"` and membership role `staff` |
| `workflows.py` `GET /overseas/agent/commissions`, `POST …/{id}/claim` | after `_require`: staff → `403 "Only an agency Master can view commissions"` |
| `api/portal.py` | agent sections `team`, `commissions` → `403` for staff (before `section_payload`) |
| `services/portal._agent` | for staff: dashboard leaves out "Claimable commission"/"Claims", reports leaves out "Paid commission", commissions not queried |
| `admin.py` `list_agent_orgs` | `masters` and the `q` member match filter `role='master'` |
| `admin.py` legacy `list_agents`, `_pending_agent_assignment` | staff excluded from the list; approve/reject of a staff id → `422 "Staff accounts are managed by their agency"` |

Unchanged on purpose: every `org_member_ids` scope (S1 organisation-wide), `agent_denial_reason`, organisation
transitions (staff exist only in organisations that were `active`).

## 9. Frontend (`apps/web`)

Design language kept: `action-card`, `card` list items (stack on mobile, no wide tables), `badge`, `btn` /
`btn secondary small`, `field` forms, `form-error` / `form-message`, `muted`; inline confirmation groups with
`autoFocus` and focus return; `detailMessage` for server errors; pager from `AgentApprovalPanel`.

- **`components/AgentStaffPanel.tsx`** (container, < 200 lines): fetches `GET /team/staff` (20 per page);
  states — loading (`aria-busy`, "Loading staff…"), load error (`role="alert"` + Retry), empty ("No staff yet.
  Add your first staff member below."), list + pager ("Showing x–y of z", Previous/Next, disabled at the ends,
  `aria-label`s); an always-mounted `aria-live="polite"` notice for results; reloads the page after each change
  and steps back a page when a page empties.
- **`components/AgentStaffRow.tsx`**: code, name, email, phone; status as text badges ("Deactivated",
  "Set-up pending", "Link expired") — never colour alone; actions with per-row busy state ("Working…") and an
  in-flight guard:
  - **Edit** → inline form (name, phone; email read-only text) with Save/Cancel, Escape cancels, focus returns
    to Edit;
  - **Deactivate** / **Reset** → inline confirmation ("They will be signed out…" / "Their password stops working
    and a new set-password link is emailed…"), focus to Confirm, Cancel returns focus;
  - **Reactivate** (no confirmation; message reminds to use Reset when set-up was never finished);
  - row-level error message (`role="status"`), including `409`/`429` text with the wait time.
- **`components/AgentStaffCreateForm.tsx`**: name, email, phone (optional) with `<label>`s, `maxLength`s,
  `type="email"`/`type="tel"`, `autoComplete="off"`; submit disabled + "Adding…" while in flight; success message
  names the new code and says whether the email was sent, else "use Reset to send a new link"; the form resets on
  success and keeps values on failure; focus moves to the message.
- **`WorkflowPanel.tsx`**: the Team section renders `<AgentStaffPanel/>` after `<AgentTeamPanel/>`.
- **`lib/types.ts`**: `User.agent_member_role?: "master" | "staff" | null`.
- **`PortalPage.tsx`**: for `overseas/agent` with `agent_member_role === "staff"`, nav drops `team` and
  `commissions` (a direct URL still reaches the server's `403`, rendered by `accessUnavailable`), role label
  "Agency Staff".
- Responsive: long names/emails wrap (`overflowWrap: "anywhere"`); action buttons wrap on narrow screens; checked
  at 320/768/1024/1440 px. No new CSS classes unless a wrap cannot be done with existing ones.

## 10. Security review (security-and-hardening)

| Threat | Control |
|---|---|
| Authentication | Deactivation → `User.active=False` → `401` on every API (`get_current_user`, login, refresh). Reset and deactivation increment `session_version` → old access/refresh tokens `401`. Tokens stay HS256-signed, httpOnly, `SameSite=Lax`. |
| Authorization / role escalation | Staff blocked from every team route (`_require_master` member-role check), commission routes and portal sections. Staff cannot reach Master routes by id. A Master can never reset a Master. Nothing lets staff change their role or membership (`PATCH /auth/me` has no role field). |
| IDOR | Every member lookup is `id + org_id (caller's) + role='staff'` under the organisation lock → `404` otherwise. |
| Account takeover by a Master | The Master never receives a password or token (dev token stripped); the link goes to the staff member's own email, which the Master **cannot change** after creation. |
| Input validation | Pydantic at the boundary (lengths, email pattern, trim, `extra="forbid"`); `limit`/`offset` bounded. |
| XSS | React escaping only; no `dangerouslySetInnerHTML`; names/emails also shown in admin lists, same escaping. |
| CSRF | Cookie auth with `SameSite=Lax` and CORS restricted to `frontend_url` (existing); body-less action POSTs match the built AGN-001 routes. No change. |
| SQL injection | SQLAlchemy expressions only; no raw SQL. |
| Secrets / sensitive logs | No token, password or email address in audit metadata or logs (ids, codes, field names, statuses only); delivery errors already redacted by `provisioning`. |
| Enumeration | Create with an existing email → `409`, audited and counted in the 20/24 h budget (same trade-off as AGN-001 QA-10). |
| Rate limiting / mail abuse | 20 staff creations + resets per agency per rolling 24 h, counted from audit rows in the database (shared across API instances), `429` + `Retry-After`; per-account 60 s reset cooldown. |
| Audit / repudiation | Every create, rejected create, edit, deactivate, reactivate, reset written in the same transaction (fail closed); link issue and delivery already audited by `provisioning`. |
| Data minimisation | Only name, email, phone collected (S4). |

**Known limitation (E4):** an admin's `PATCH /users/{id}` can still flip `active` on any agent user (pre-existing
AGN-001 gap). A staff member reactivated that way reaches `/auth/me` but no agent data (`agent_denial_reason`
denies a deactivated membership). Recorded, not changed.

## 11. Acceptance criteria → tests (written before the code)

**`apps/api/tests/test_agn_002_staff.py`** (reuses `agn001_helpers.py`):

| AC | Tests |
|---|---|
| AC01 | codes S001, S002; independent of Masters (M002 after S001); not reused after deactivation; two organisations each start at S001; concurrent creates → distinct codes |
| AC02 | `201` with `email_status` and `expires_at`; no `development_welcome_token`; welcome token row exists; staff sets a password with it and signs in |
| AC03 | name/phone edit; `email` in body → `422`; empty body → `422`; phone cleared by `null` |
| AC04 | after deactivation the staff member's cookie → `401` on `/auth/me`, an agent route, `/auth/refresh`; login `401`; open link revoked |
| AC05 | reactivation → login works; pre-deactivation cookies still `401` (E6); link stays revoked; reset then sends a new one |
| AC06 | reset → old password fails, old access and refresh cookies `401`, new link works; second reset within 60 s → `429`; reset of deactivated → `409` |
| AC07 | other organisation's Master: list excludes, PATCH/deactivate/reactivate/reset → `404`; Master id on staff routes → `404`; staff → `403` on team routes, commission list/claim, portal `team`/`commissions`; staff → `200` organisation students/applications; staff dashboard has no commission figures |
| AC08 | one audit row per action with `entity_type='agent_org'`, member id and code, no email/token |
| AC09 | staff don't count toward the 3-Master limit or the last-Master rule; commission notifications reach Masters only; admin organisation list shows Masters only; legacy approve with a staff id → `422` |
| AC10 | 21st create/reset → `429` + `Retry-After`; Master invite still allowed |
| Sessions | a token without `sv` still works; login after reset works immediately |

**`apps/api/tests/test_agn_002_migration.py`**: upgrade keeps existing members/orgs; constraints accept staff and
reject other roles; downgrade refused while staff exist, succeeds otherwise (pattern: `test_enh_027_migration.py`).

**`apps/web/tests/components/AgentStaffPanel.test.tsx`** (+ row/form cases): loading, load error + Retry, empty,
list + badges, pager, create success (sent / not sent), create `409`/`429`/network error, double-submit blocked,
edit save/cancel/Escape, deactivate confirm/cancel focus return, reactivate, reset confirm, row error text.
**`PortalPage`/nav test:** staff nav has no Team/Commissions.

**`apps/web/tests/e2e/agn-002-staff.spec.ts`**: Master adds staff → staff sets password (welcome helper) →
staff sees organisation students, no Team/Commissions nav → Master deactivates → staff's next navigation lands on
login → reactivate → reset → old password rejected, new link works.

**Regression runs:** during the build, `test_agn_001_*`, `test_enh_003_*`, `test_enh_006_*` (auth), agent
workflow/portal/lookup tests, `AgentTeamPanel.test.tsx`, `AgentApprovalPanel.test.tsx`; at the end one full
backend run (the session check touches every route), the frontend unit suite, and the `agn-001` + `agn-002`
Playwright specs.

## 12. Regression risks and mitigations

| Risk | Mitigation |
|---|---|
| Session check logs everyone out | `sv` defaults to 0 on both sides; explicit test with a legacy token |
| Staff counted as Masters | role filters + AC09 tests; existing AGN-001 limit tests re-run |
| Staff reaching Master-only data | guard at routes + portal; AC07 tests |
| Changed `GET /team` | shape unchanged; `masters` filter is a no-op for existing data |
| Admin agent lists | staff excluded; `AgentApprovalPanel` tests re-run |
| Migration on existing data | additive; migration test with pre-existing orgs/members |

## 13. Documentation to update with the code

`DATA_MODEL.md` (columns, constraints), `API_CONTRACT.md` (§6 routes, `/auth/me` field, `sv` claim),
`RBAC_MATRIX.md` (staff row), `SCREEN_CATALOG.md` (`SCR-AGT-007` staff section, staff nav),
`RTM.md` (AGN-002 row), backlog status.
