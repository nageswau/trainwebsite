# ENH-007 — Profile Self-Service: Cross-Role Completion Audit — Design

**Status:** Design approved by the user in-session, 2026-09-22 (uniform `full_name`/`phone` scope; single
shared `/account/profile` route linked from `PortalShell`, approach A of three presented). Reviewed against
`api-and-interface-design` (§4a — one small, additive validation fix approved), `frontend-ui-engineering`
(§6 — nav-ordering and post-save value-sync findings folded in), and `security-and-hardening` (§10a — no
plan changes beyond the §4a fix). Ready for `writing-plans`.

**Traceability:** `EVID` user instruction ("user profile, updating profile") →
`docs/delivery/ENHANCEMENT_BACKLOG.md` ENH-007 (lines 690-734) → cross-role completion audit (this
session, chat record) → this spec → plan (`docs/superpowers/plans/`) → tests → code.

**Acceptance-criteria numbering:** `AC-nn` below is local to this spec.

## 1. Problem (audit result, gap confirmed)

A full-repo audit (this session, preceding this spec) found: `GET/PATCH /auth/me`
(`apps/api/app/api/auth.py:165-199`) is a working, generic, self-only profile-update endpoint already
used correctly for every role and division — it server-owns `school_id`/`university_id`
(`SERVER_OWNED_PROFILE_KEYS`), audits every change (`profile.update`/`profile.update_denied`), and has
no authorization gap. **But no frontend anywhere calls it.** `apps/web/lib/api.ts` has zero references to
`/auth/me` beyond session bootstrap; no page exists under `apps/web/app` named or containing "profile"
for any role, including the two the backlog cites as already confirmed (student's `GET/PATCH
/student/profile` from `API_CONTRACT.md:105` does not exist in code either — only document upload,
`/it/student/profile/documents`, does). All 7 real School-domain login roles (`school_coordinator`,
`school_principal`, `school_teacher`, `school_parent`, `academic_team`, `career_counselor`,
`psychometric_team`) are affected identically: backend-complete, frontend-absent. `school_partnership_manager`
has no RBAC grants and is explicitly deferred (`RBAC_MATRIX.md:239-241`, `PRD_OPEN_ITEMS.md` item 75) — out
of scope for this item.

## 2. Goals and non-goals

**Goals.** Every School-domain role can find, view, and edit its own `full_name` and `phone` through a
real UI, using the existing `PATCH /auth/me`. Reachable from the same shared portal chrome every role
already uses.

**Non-goals (do not do here).**
- Any new backend route, new Pydantic field, database column, migration, or RBAC change. The user
  confirmed scope is the uniform baseline already supported by `ProfileUpdate` (`full_name`, `phone`) — no
  per-role fields this pass. (One narrow exception, added after backend review: a validator on the
  existing `full_name` field — see §4a/§5. Not a new field, route, column, migration, or RBAC change.)
- Anything touching `User.profile` (the JSON blob) from this new UI. The form never sends a `profile`
  key at all (see §4) — this is a design constraint, not an oversight.
- `school_partnership_manager` — no role, no grant, no screen. Blocked on `PRD_OPEN_ITEMS.md` item 75.
- Fixing the `API_CONTRACT.md:105` vs. code drift on `/student/profile` — flagged as `NEEDS_CONFIRMATION`
  in the audit, not resolved here; STU-011's own scope, not ENH-007's.
- Per-role extended fields (subjects, designation, portfolio, etc.) — explicitly deferred by the user to
  a later pass.
- Any change to `PATCH /admin/users/{id}`, `AdminUserManagementPanel.tsx`, or `ensure_admin` — that is
  admin-editing-others (ADM-004), a different feature.

## 3. Decisions taken

No new Decision ID is required — `PRODUCT_DECISION_REGISTER.md` line 2765 already lists ENH-007 as
operating entirely within already-`CONFIRMED_CURRENT` scope. One scope decision was made in-session with
the user (recorded here since it narrows the backlog's open question):

| # | Decision |
|---|---|
| 1 | Field scope for this pass is `full_name` + `phone` only (the existing `ProfileUpdate` shape), identical across all 7 roles — not a per-role field design. |
| 2 | One shared route (`/account/profile`) reused by every role via the existing `PortalShell`, not 7 per-role pages — matches the established pattern already used for `/account/password` and `/account/privacy` (pages that "belong to no one role's portal nav"). |

## 4. API contract (unchanged — reused as-is)

`PATCH /api/v1/auth/me` — no change. Documenting the exact request this feature sends, since that shape
is itself a safety property:

```json
{ "full_name": "string, 2-160 chars", "phone": "string, <=40 chars, or null" }
```

The request **never includes a `profile` key**. Because `ProfileUpdate.profile` defaults to `None` and
`update_me()` reads `changes = payload.model_dump(exclude_unset=True)`, omitting the key entirely means
`"profile" not in changes` — `user.profile` (containing `school_id`, `university_id`, and any admin-set
`education`/`skills`) is left completely untouched by this feature, by construction, not by a runtime
check. This is the load-bearing safety property that makes this a purely additive frontend change: there
is no code path in `update_me()` this feature can newly trigger.

Existing response contract reused as-is: `200` (updated `UserOut`), `401` (no/expired session), `422`
(validation — `full_name` 2-160 chars, `phone` <=40 chars). `403` (`SERVER_OWNED_PROFILE_KEYS`) is
unreachable from this form since it only fires when `profile.school_id`/`profile.university_id` is
present in the request, which this form never sends.

**Safe to retry?** Yes, unconditionally. Unlike `change-password`, this is a flat field overwrite with no
rate limiter, no one-shot side effect, and no ordering dependency on prior state — retrying an identical
request produces an identical end state. `API_CONTRACT.md`'s `Idempotency-Key` requirement (§0.2) applies
only to financial/record-creating endpoints and does not apply here.

### 4a. Backend/API review (`api-and-interface-design`, 2026-09-22)

Checked against contracts, validation, HTTP semantics, authorization, backward compatibility,
transactions, error handling, and database usage. Sound as-is on every axis except one:

**Finding — explicit `full_name: null` crashes `update_me()` today.** `schemas.py:71`
(`full_name: str | None = Field(default=None, min_length=2, max_length=160)`) accepts an *explicit*
`null` as a valid value (Pydantic's `min_length` only constrains strings, not `None`); `auth.py:190-191`
then unconditionally calls `changes["full_name"].strip()`, which raises `AttributeError` on `None` →
unhandled `500`. `User.full_name` is also non-nullable (`models.py:23`), so persisting `None` was never a
valid outcome either. Pre-existing, reachable by any direct API caller today — not introduced by this
feature, but this feature is the first real UI to drive traffic at this route, so it is being fixed
alongside it (user-approved, 2026-09-22) rather than shipped over a known crash. `phone` has no equivalent
bug (nullable column, direct assignment, no `.strip()`).

Everything else — self-only authorization via `get_current_user` with no role check needed, single-commit
transaction with no locking requirement (flat overwrite, not a read-modify-merge like the `profile` path),
database usage, and snake_case naming (kept, over the skill's generic camelCase default, to match this
codebase's existing convention) — required no change.

## 5. Backend design

No new route, database column, migration, or RBAC change. One small, additive fix per §4a:

- `apps/api/app/schemas.py`: add a `field_validator` on `ProfileUpdate.full_name` rejecting an explicit
  `None` when the key is present (mirroring the existing `new_password_is_not_blank` validator pattern
  already in the same file on `ChangePasswordRequest`), so `{"full_name": null}` becomes a `422` instead
  of a `500`. Omitting the key entirely is unaffected — still means "don't change `full_name`."
- No change to `auth.py`'s route logic; the validator alone closes the gap before `update_me()` ever sees
  the bad value.

The audit found `PATCH /auth/me`'s general `full_name`/`phone` path has zero existing test coverage (only
the `school_id`/`university_id` denial path is tested, in `test_enh_004_student_promotion.py`). Since a
real UI will now depend on this path, add one test-only file:
`apps/api/tests/test_enh_007_profile_self_service.py` covering the success/validation/auth cases in §8.

## 6. Frontend design

Reuses the existing design language and two already-reviewed sibling implementations verbatim: no new UI
primitive, no new client-side API-wrapper abstraction (the codebase's convention for these self-service
forms is a direct `fetch` inside the client component, as `ChangePasswordForm.tsx` does — matched here,
not replaced with a new `lib/api.ts` helper).

**Entry point.** `apps/web/components/PortalShell.tsx` (every portal role, all 7 School-domain dashboards
confirmed to render through it): one new link, "My profile", added immediately after the existing "Change
password" link in both places it appears — the desktop sidebar footer, and the front of the array passed
to the mobile `MobileNavToggle` (currently `nav={[{href:"/account/password",...}, ...nav]}`). **Frontend
review finding (2026-09-22):** appending "My profile" after `...nav` instead would reintroduce QA-004
(ENH-006) — "Change password" was deliberately moved to position 1 of ~18 mobile items after it was found
buried at the bottom; a naive append puts the new link right back there. Both links must stay front-loaded,
in the same relative order on desktop and mobile. Confirmed safe against the desktop layout too: `.sidebar{height:100vh;overflow:auto}`
(`globals.css`) scrolls rather than clips if the footer grows. Additive only — `.portal-nav` and each
role's own `nav` array are unchanged.

**Page** `apps/web/app/account/profile/page.tsx` (server component), modelled directly on
`apps/web/app/account/password/page.tsx`:
- `serverApi<User>("/api/v1/auth/me")` gates it; an explicit `401` (via `ApiError`) shows a "Sign in
  required" card with both division login links (`?next=` round-trip); any other failure (5xx, network)
  shows "Temporarily unavailable" instead of misreporting a signed-in user as signed out (the same
  distinction `account/password/page.tsx` already makes).
- Renders inside `PublicShell`, division-aware, with a "← Back to dashboard"
  (`ROLE_DASHBOARD_PATH[user.role]`) link and its own page title ("Your profile").
- Passes the loaded `user.full_name`/`user.phone` into the form as initial values.

**Form** `apps/web/components/ProfileForm.tsx` (client component), props `{ fullName, phone }`:
- Fields: `full_name` (text, required, `minLength=2 maxLength=160`, matching the Pydantic rule) and
  `phone` (text, optional, `maxLength=40`).
- `PATCH`es `/api/v1/auth/me` with exactly `{ full_name, phone: phone || null }` — no other key.
- Double-submit guard, `aria-busy`/`aria-disabled` pattern, and outcome handling mirror
  `ChangePasswordForm.tsx`:

| Outcome | UI |
|---|---|
| 200 | "Your profile was updated." (`role=status`); fields are set from the response body's `full_name`/`phone` (the canonical, server-trimmed values `UserOut` already returns), not left as raw DOM input — **frontend review finding (2026-09-22):** `auth.py:191` calls `.strip()` server-side, so a typed `" John "` would otherwise show untrimmed until reload; syncing from the response avoids that drift |
| 401 | "Your session has expired…" banner with both division sign-in links |
| 422 | inline error under the offending field (`full_name` too short/long, or general `detail` message), focus moves there |
| network failure | "Network error — try again." (safe to retry; unlike password-change this request has no rate-limiter/one-shot side effect that a retry could disturb) |
| other | server `detail` message or generic fallback |

- **Loading:** button label + `aria-busy`, no skeleton (server-rendered from one fast request, matching
  the rest of the codebase's convention). **Empty:** an unset `phone` renders as a blank input, never
  "N/A". **Errors:** table above.
- **Accessibility/responsive:** labelled inputs, errors tied to the field via `aria-describedby`, fully
  keyboard-completable, no horizontal scroll at 375px, tap targets >=44px — same bar `ChangePasswordForm`
  already meets.

## 7. Acceptance criteria

- **AC-01** Every one of the 7 School-domain roles (`school_coordinator`, `school_principal`,
  `school_teacher`, `school_parent`, `academic_team`, `career_counselor`, `psychometric_team`) sees "My
  profile" in their portal sidebar and mobile menu.
- **AC-02** The page loads showing the signed-in user's current `full_name` and `phone` (blank if unset).
- **AC-03** A valid edit to `full_name` and/or `phone` persists via `PATCH /auth/me` and is reflected
  after a reload.
- **AC-04** `full_name` under 2 characters (or blank) is rejected with a visible field-level error;
  nothing is saved.
- **AC-05** An expired/missing session shows a sign-in prompt with working links back to the page, not a
  crash or a false "temporarily unavailable".
- **AC-06** The PATCH request body sent by the form contains exactly `full_name` and `phone` — never a
  `profile` key — verified by an assertion on the exact payload shape, not just on the response.
- **AC-07** No other user's data changes; `school_id`, `university_id`, and any admin-set
  `profile.education`/`profile.skills` are unchanged after using this form (verified by re-fetching the
  user's full record after a profile-form update and diffing against its pre-update state, restricted to
  the `profile` JSON key).
- **AC-08** `school_partnership_manager` gets no new UI, route, or RBAC grant from this change.
- **AC-09** Existing behavior is unchanged: `login`, `register`, `/auth/me` GET, `PATCH /admin/users/{id}`,
  and the `school_id`/`university_id` denial path all behave exactly as before.
- **AC-10** `PATCH /auth/me` with an explicit `{"full_name": null}` returns `422`, not `500`, and changes
  nothing; omitting `full_name` from the request entirely still leaves it unchanged (the "omit to skip"
  contract is unaffected by the new null check).

## 8. Test plan (written first, seen failing)

- **pytest** `apps/api/tests/test_enh_007_profile_self_service.py`: successful `full_name`+`phone`
  update (AC-03), `full_name` too short → 422 unchanged (AC-04), explicit `full_name: null` → 422 unchanged,
  not 500 (AC-10), `full_name` omitted entirely → unchanged (AC-10's negative case), phone omitted →
  `full_name` alone changes, `phone` untouched, unauthenticated → 401 (AC-05), a request with only
  `full_name`/`phone` never alters `profile.school_id`/`profile.university_id`/other profile keys
  (AC-06/AC-07), run once per a School-domain role (parametrized, not one test per role — the code path
  does not branch on role).
- **vitest** `apps/web/tests/components/ProfileForm.test.tsx`: mocked fetch, asserts the exact 2-key
  request payload (AC-06), initial-value rendering (AC-02), success/401/422/network rendering, focus
  management, double-submit guard. `apps/web/tests/components/PortalShell.test.tsx`: extend for the new
  sidebar link and mobile-menu item (AC-01), asserting the existing "Change password" link and desktop nav
  array are unchanged.
- **Playwright** `apps/web/tests/e2e/enh-007-profile-self-service.spec.ts`: log in as one representative
  School-domain role (e.g. `school_coordinator` — sufficient since all 7 share the identical
  shell/route/component with no role-conditional logic), reach the page via the portal sidebar link, edit
  and save `full_name`/`phone`, verify persistence after reload, verify the field-level 422 case, verify
  the signed-out state.
- **Regression scope (targeted):** `test_enh_004_student_promotion.py` (school_id/university_id denial
  path, must be unaffected), `test_role_assignments.py` and `test_stu_011_profile_documents.py` (both
  exercise `/auth/me`, must be unaffected by the new validator), `AccountPasswordPage.test.tsx`/
  `ChangePasswordForm.test.tsx` (unaffected by `PortalShell`'s footer edit, but the shared component means
  they must still pass), the portal E2E specs that assert on `PortalShell`'s mobile menu
  (`stu-011-profile-documents`, any `trn-*` nav spec).

## 9. Regression risks and mitigations

| Risk | Mitigation |
|---|---|
| `PortalShell` is shared by every portal role; a layout/selector change could regress all of them | Additive only (one sidebar link, one mobile-menu item; existing nav arrays untouched); extend `PortalShell.test.tsx`; run existing portal E2E specs that touch its mobile menu |
| `PATCH /auth/me` is shared by every division/role in the system, not just School-domain | This feature sends only `{full_name, phone}`, never `profile` — by construction it cannot exercise any code path other roles' existing behavior doesn't already exercise; new backend test (§8) covers the previously-untested general path without touching route code |
| Untyped `User.profile` JSON blob could be clobbered by a naive "send the whole profile" implementation | Explicitly designed against in §4/§6: the form never reads or sends `profile` |
| The new `full_name` null-validator changes shared, division-wide `PATCH /auth/me` behavior | Strictly additive: only a request that was already crashing (`500`) is affected, and it now gets a correct `422`; no request that succeeded before still succeeds and produces a different result. Covered by AC-10 and the targeted regression run below. |
| Confusing this feature's scope with STU-011's documented-but-missing `/student/profile` route | Out of scope (§2); flagged separately as `NEEDS_CONFIRMATION`, not silently folded in here |

## 10. Documentation to update with the code

`docs/delivery/ENHANCEMENT_BACKLOG.md` (ENH-007 status, record the uniform-baseline scope decision);
`RTM.md` (ENH-007 row) if this project maintains one at implementation time.

## 10a. Security review (`security-and-hardening`, 2026-09-22)

Checked against authentication, authorization, IDOR, role escalation, input validation, XSS, CSRF, SQL
injection, token/session handling, secret exposure, sensitive logs, rate limiting, and audit requirements.
No new attack surface — self-only by construction (no id in path/body, so no IDOR surface exists to
check); `ProfileUpdate` declares only `full_name`/`phone`/`profile` and drops unknown fields by default,
and `update_me()` assigns via an explicit allowlist (`auth.py:190-195`), so body-stuffing `role`/`division`/
`active` cannot escalate privilege; no raw SQL (ORM assignment only); no new logging of field values (only
field *names* are ever logged/audited, `auth.py:188,196`); cookies are already `HttpOnly`/`SameSite=Lax`
app-wide, covering this form the same as every other authenticated one. **Deliberately not adding:** a
rate limiter (nothing secret is being verified here, unlike `change-password`; singling out this route
would be scope creep past a cross-cutting, already-tracked, open item), a phone-format validator (data
quality, not a security control), or CSRF tokens (existing cookie policy already covers this). The
already-approved `full_name: null` fix (§4a/§5) additionally closes an unhandled-exception path as
defense in depth.

## 11. Open, not decided here

Per-role extended profile fields beyond `full_name`/`phone`; whether `API_CONTRACT.md:105`'s
`/student/profile` route should be built or the contract doc corrected; `school_partnership_manager`'s
eventual duties (`PRD_OPEN_ITEMS.md` item 75).
