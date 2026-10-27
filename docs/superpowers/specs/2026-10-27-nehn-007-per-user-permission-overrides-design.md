# nehn-007 — Per-user permission overrides (design)

- **Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-007` (§5 L92 "control individual permissions for
  individual users or roles"; `MEETING_TRANSCRIPT_REQUEST`, `UNVERIFIED` backlog). `CLIENT_QUESTIONS.md` D-09 §3 / OD-03 is **open**.
- **Dependencies:** nehn-005 engine (`DEC-SCOPE-281`, #347) and nehn-006 matrix screen (`DEC-SCOPE-295`, #362), both merged.
- **Decision:** `DEC-SCOPE-298`. **RBAC:** §2.209. **API:** §12GV. **Migration:** `0205_user_permission_overrides`.

## Intent

A Super Admin grants or denies one catalogue permission to one user on top of that user's role, with a reason and an optional expiry,
and can see every override in force. Overrides are easy to forget, so they are visible, reasoned, audited and can lapse on their own.

## Goals

- Table `user_permission_overrides` (user, resource, action, effect allow|deny, reason, expires_at?, who/when).
- Effective permission = (role grants ∪ active allows) − active denies. A deny beats the role grant and beats nothing else.
- Every grant check that today reads the role (`require_permission`, the portal payments / certificates sections) and
  `GET /auth/me/permissions` (nav and controls) resolve the effective set, so the web app follows overrides with no further change.
- `GET/PUT /admin/users/{user_id}/permissions` and a report `GET /admin/permissions/overrides`.
- `/admin/permissions` gains a "By user" tab: pick a user, see each permission's origin (role / allowed / denied), edit overrides;
  the tab lists every active override.

## Non-goals

- New catalogue resources. The backlog's AC keys `reports.placement.download` and `documents.view` are not in the catalogue (no wired
  route yet — nehn-005 P1); the same rules are proven with existing keys (below).
- Custom roles, column policy (nehn-008), overrides on the coarse `rbac.PERMISSIONS` bundles or `UserRoleAssignment`.
- A new column on the `/admin/users` grid (the "badge" — see U6).

## Anti-goals

- An override that silently outlives its purpose (hence reason required, expiry honoured at read time, a report of all overrides).
- A deny that can lock out super_admin.
- Any drop in the day-one behaviour: with no override rows every check answers exactly as before.

## Builder's defaults (owner pre-authorised recommended answers; each `NEEDS_CONFIRMATION`)

| # | Open question | Default in place |
|---|---|---|
| U1 | Are per-user overrides needed this release? (OD-03 / D-09 §3) | Built, behind no flag; with no rows nothing changes. |
| U2 | super_admin users | Cannot carry overrides (PUT → 409, GET `editable:false`); super_admin always holds everything. |
| U3 | Reason | Required, 1–500 characters after trimming. |
| U4 | Expiry | Optional; must be in the future when saved. An override past `expires_at` stops applying at once (read-time filter, no job) and is not returned as current; the next save of that user drops the expired row. History stays in `audit_logs`. |
| U5 | Edit model | Replace the user's whole override set in one PUT (as nehn-005 does for a role); one audit row per real change (`user_permission_overrides.update`, before/after/added/removed/changed); a no-op writes nothing; a racing insert → 409. |
| U6 | "Badge on the user profile" | There is no per-user profile page for admins; the "By user" tab's **Active overrides** list (user, permission, effect, reason, expiry; count per user) is the badge and the report the backlog asks for. A grid column is deferred. |
| U7 | Allow that the role already has / deny the role lacks | Accepted (stable if the role grants change later); the UI shows the origin so it is visible. |
| U8 | Which users can be picked | Any user, found through the existing `GET /admin/users?q=` (server search). Inactive users are allowed (their sign-in is refused anyway). |
| U9 | Cache | None (nehn-005 P7): a check is at most two primary-key lookups, so a change applies on the next request. |

## Design

### Data — migration `0205_user_permission_overrides`

`id` UUID PK; `user_id` FK users CASCADE (indexed); `resource` String(60); `action` String(20); `effect` String(10) CHECK in
(`allow`,`deny`); `reason` String(500) NOT NULL; `expires_at` timestamptz NULL; `created_by_id` FK users SET NULL; `created_at`
default now. UNIQUE (`user_id`, `resource`, `action`). No seed; no existing data changes. Downgrade drops the table.

### Service — `services/permissions.py`

- `has_grant(db, role, …)` unchanged (role level; used by the role matrix and tests).
- `user_has_grant(db, user, resource, action)`: catalogue check → super_admin True → the user's active override for the key decides
  (allow True / deny False) → else `has_grant(role)`.
- `user_grants(db, user)`: sorted effective keys (role ∪ allows − denies), catalogue-filtered.
- `active_overrides(db, user_id=None)`: active rows (`expires_at IS NULL OR > now()`), joined to the user for the report.
- `replace_user_overrides(db, actor_id, user, items)`: 409 for a super_admin target; diff against active rows; delete all of the
  user's rows (expired ones too) and insert the new set; audit + commit in one transaction; IntegrityError → rollback + 409.
- `deps.require_permission` and `services/portal.py` (payments, certificates sections) call `user_has_grant`.
- `GET /auth/me/permissions` returns `user_grants` (shape unchanged).

### API (super_admin only, nehn-005's `_super_admin` guard; order caller → target 404 → body 422 → target 409)

- `GET /admin/users/{user_id}/permissions` → `{user:{id,full_name,email,role}, editable, role_permissions:[keys],
  overrides:[{permission, effect, reason, expires_at, created_at}], effective:[keys]}`.
- `PUT /admin/users/{user_id}/permissions` body `{overrides:[{permission, effect, reason, expires_at?}]}` (extra=forbid, ≤ 200 items,
  unique permission, catalogue key, reason 1–500 trimmed, expires_at timezone-aware and future) → same body as GET.
- `GET /admin/permissions/overrides` → `[{user_id, full_name, email, role, permission, effect, reason, expires_at, created_at}]`,
  ordered by user name then permission.

### Web

- `/admin/permissions?tab=user[&user=<id>]` — server page renders two tab links ("By role", "By user", `aria-current="page"`), the
  role tab unchanged (`PermissionMatrix`).
- `UserPermissionOverrides` (client): user search (`/admin/users?q=`, results as links to `?tab=user&user=<id>`), the active-overrides
  list (links too); for a picked user a table: Permission | Role | Override (select: None / Allow / Deny) | Reason | Expires |
  Effective. Save / Discard, unsaved-changes guard (`useLeaveGuard`), loading / error+retry / empty states, `role="status"` success,
  `role="alert"` error with Reload on 409. Table inside the labelled `table-scroll` region; native labelled controls.

## Acceptance criteria (testable)

1. AC1 A deny override on one telecaller_manager for `reports.telecaller.download` refuses that user's download (403) while another
   telecaller_manager still downloads, and the first still views the JSON report. (Backlog's recruiter/`reports.placement.download`
   is not a catalogue key.)
2. AC2 An allow override grants one hr_team user `payments.view` (GET `/admin/payments` 200, nav shows Payments via
   `/auth/me/permissions`); another hr_team user is still refused.
3. AC3 An override whose `expires_at` has passed stops applying with no action, and is not reported as active.
4. AC4 Only super_admin reads/edits overrides (others 403, anonymous 401); unknown user 404; invalid body 422; a super_admin target
   409; each real change writes one audit row with before/after; a no-op writes none.
5. AC5 The "By user" tab shows each permission's origin, saves overrides, lists every active override, is keyboard operable with
   labelled controls, and at 375 px the page has no horizontal scroll.

## Regression risks

- `require_permission` (all grant-gated routes) — same answer with no override rows; covered by nehn-005's seed-equivalence tests.
- `/auth/me/permissions` drives tagged navs — shape unchanged.
- Migration chain is linear; a sibling landing 0203 first means re-chaining in Phase 9.

## Security review

- New writes are super_admin only; the target id is a path UUID (404 when absent); no IDOR because the actor is global admin.
- Deny wins over role; allow cannot exceed the catalogue; super_admin cannot be overridden (no lockout).
- Reason rendered as text (no XSS); SQL through ORM; CSRF unchanged (existing cookie model). Every change audited with actor.

## Engineering review (Phase 3) folded in

- API: PUT is a full replace (idempotent); `expires_at` must be timezone-aware (`AwareDatetime`, naive → 422); the web sends the end
  of the chosen local day as ISO. 404 before 422 so a body error never confirms an id is valid for a refused caller (the caller check
  runs first anyway). Response shape of `/auth/me/permissions` unchanged.
- Frontend: tabs are links (refresh/back keep the tab and the picked user); one `<select>` per row, labelled "<Resource>: <Action>
  override"; reason and expiry inputs appear only for a row with an override; Save disabled while clean or invalid (a row with an
  override but no reason shows the field-level message).
- Security: no new public route; overrides cannot target super_admin; logging carries ids and keys, never reasons.

## Plan (TDD, one slice at a time)

1. Model + migration 0203 + migration test (chain, round trip).
2. Service resolution (`user_has_grant`, `user_grants`, `active_overrides`) + wire `deps.require_permission`, portal sections,
   `/auth/me/permissions` — tests AC1/AC2/AC3 against real routes.
3. Admin endpoints + schema — tests AC4 (authz matrix, 404/422/409, audit, no-op).
4. Web: `UserPermissionOverrides` + page tabs — vitest (origin column, save body, validation, 409, states).
5. Docs: DEC-SCOPE-298, API §12GV, RBAC §2.209, DATA_MODEL, backlog/tracker status. Playwright e2e for the user tab.
