# ENH-010 — Account Activation / Deactivation (School Master Capability) — Design

> **Scope note, read first:** this is not a build. An audit (this branch, 2026-09-22) found
> ENH-010's entire functional scope already shipped, under `SCH-003` addendum, before the
> ENH-010 backlog entry was even written. This spec covers **verification + documentation
> reconciliation only** — user-confirmed scope. No production code changes except the one test
> function in §8.

## 1. Problem (audit result, not a build gap)

`docs/delivery/ENHANCEMENT_BACKLOG.md` ENH-010 and `docs/quality/RTM.md` row `B2` both say the
School Master "Activate/deactivate users" capability (`School CRM.md` Part B §2,
`docs/sources/School CRM.md:1361`) is **not confirmed**. That is stale. The capability exists,
tested, at:

- Backend: `PATCH /api/v1/school/team/accounts/{user_id}` (`apps/api/app/api/schools.py:176-203`,
  `update_team_account`), shipped in the initial School-domain commit and documented in its own
  docstring as `"SCH-003 addendum -- Coordinator activate/deactivate for their own school's
  Principal/Teacher/Parent accounts (EVID-014 "School Master" §33/§2 -- treated as the same role
  as school_coordinator per direct user confirmation)"`.
- Frontend: `apps/web/components/SchoolTeamPanel.tsx` (`toggleActive()`), rendered at
  `/school/coordinator/team` (`apps/web/app/school/coordinator/team/page.tsx`).
- Tests: `apps/api/tests/test_sch_team_account_activation.py` (7 cases), plus
  `apps/web/tests/e2e/sch-team-management.spec.ts` (2 scenarios).

The gap is in the **paper trail**, not the code: the docstring's "per direct user confirmation"
claim has no corresponding entry in `docs/decisions/PRODUCT_DECISION_REGISTER.md`. `DEC-SCOPE-011`
confirms Coordinator "write access" broadly ("add/manage students… monitor services") but never
names account activation, and the register elsewhere warns that `EVID-014`'s own claims are not
`EXPLICIT_APPROVAL` on their own (`CLAUDE.md`'s rule). This spec closes that gap by drafting the
missing Decision entry for the user's explicit approval — never self-approving it.

## 2. Goals and non-goals

**Goals:**
- Prove, with a fresh real test run (not code-reading), that the existing implementation still
  satisfies all four ENH-010 acceptance criteria.
- Close the one honest test gap found during this audit (§8).
- Record the evidence → decision → feature → AC → test → code chain that this project's own
  constitution requires, without inventing an approval that was never actually given.
- Correct `ENHANCEMENT_BACKLOG.md` and `RTM.md` to stop contradicting the shipped code, by
  superseding the stale text in place (never deleting it — this project's own convention).

**Non-goals (explicitly out of scope, per user decision):**
- No typed Pydantic schema for `update_team_account` (currently raw `dict`). Real, optional
  hardening — not done here.
- No frontend unit tests for `SchoolTeamPanel.tsx` (currently only E2E-covered). Not done here.
- No fix for the frontend network-failure gap found in §9. Documented as a residual finding only.
- No change to `update_team_account`, `get_current_user`, `_require_coordinator`,
  `INVITABLE_ROLES`, `_assignment_is_usable`, or any other existing authorization/session code.

## 3. Decision to draft (`DEC-SCOPE-023`)

**Question:** Is `School CRM.md` Part B §2's "School Master" role the same actor as the already-
confirmed `school_coordinator` role (`DEC-SCOPE-011`), and is "Activate/deactivate users" confirmed
in scope for that role, scoped to their own institution?

**Evidence:** `School CRM.md` (`EVID-014`, `DERIVED_BLUEPRINT`, unattributed) Part B §2, quoted
verbatim: *"School Master can: … Activate/deactivate users."* Per `CLAUDE.md`, this document's own
claim is not `EXPLICIT_APPROVAL` by itself.

**Current state:** the code (`schools.py:178-180`) asserts this was resolved "per direct user
confirmation," but no matching entry exists in `PRODUCT_DECISION_REGISTER.md`. This may be an
undocumented decision from an earlier session, or an inference that was never actually put to the
user. This spec does not assume which.

**Proposed resolution (drafted, not self-approved):** adopt "School Master" (§2) as the same actor
as `school_coordinator` (§33, `DEC-SCOPE-011`) — consistent with `DEC-SCOPE-011` already treating
Part B §33's School Coordinator as having broad "write access" over the school's accounts and data
— and confirm "Activate/deactivate users" as in-scope write access, scoped to the coordinator's own
institution, excluding the coordinator's own account and any peer Coordinator account. This matches
exactly what the shipped code already does.

**Status:** `PENDING_CONFIRMATION` — the implementation task is to add this entry to
`PRODUCT_DECISION_REGISTER.md` with this status; it becomes `CONFIRMED_CURRENT` only when the user
explicitly says so in-session, at which point the status line and approval date are updated in a
follow-up edit, not assumed now.

## 4. Evidence → traceability chain being recorded

```
School CRM.md Part B §2 (EVID-014, DERIVED_BLUEPRINT)
  -> DEC-SCOPE-023 (drafted here, PENDING_CONFIRMATION)
  -> DEC-SCOPE-011 (BRD/role structure, CONFIRMED_CURRENT, already covers school_coordinator write access)
  -> SCH-003 (Feature ID, MASTER_FEATURE_CATALOG.md, CURRENT)
  -> ENH-010 (backlog cross-reference, this spec)
  -> Acceptance criteria (§7)
  -> UX/Screen: /school/coordinator/team (SchoolCoordinatorTeamPage, SchoolTeamPanel.tsx)
  -> API: PATCH /api/v1/school/team/accounts/{user_id}
  -> DB: users.active (apps/api/app/models.py:27)
  -> RBAC: _require_coordinator() + INVITABLE_ROLES guard (schools.py:94-100, 193-196)
  -> Test: apps/api/tests/test_sch_team_account_activation.py (+ one new function, §8)
  -> Code: unchanged, already shipped
  -> Release evidence: this round's real test-run output (§8)
```

## 5. Acceptance criteria (unchanged from the backlog)

1. Coordinator can deactivate/reactivate a user within their own institution.
2. A deactivated user cannot authenticate.
3. Action is audit-logged with actor, target, timestamp.
4. Coordinator cannot deactivate a user outside their institution or above their own authority
   level.

## 6. AC → test mapping

| AC | Test | Status before this spec |
|---|---|---|
| 1. Deactivate/reactivate within own institution | `test_coordinator_deactivates_and_reactivates_a_teacher` | Covered |
| 3. Audit-logged (actor, target, timestamp) | same test + `AuditLog.user_id`/`entity_id`/`created_at` (structural, `models.py:790-799`) | Covered |
| 4a. Cannot target another institution | `test_coordinator_cannot_toggle_another_schools_account` | Covered |
| 4b. Cannot target own/peer Coordinator | `test_coordinator_cannot_toggle_a_coordinator_account`, `test_non_coordinator_cannot_toggle_team_accounts` | Covered |
| 2. Deactivated user cannot authenticate | — | **Gap.** `login()` (`auth.py:95`) and `get_current_user` (`deps.py:24-25`) both filter `User.active.is_(True)`, generically, always-on — but no test deactivates a user via this endpoint and then asserts their next `/auth/login` is refused. Structurally true, not behaviorally proven for this feature. Closed by §8. |

Also implicitly exercised, not a stated AC but relevant regression coverage:
`test_deactivating_a_teacher_leaves_existing_student_assignment_unchanged` (existing
`assigned_teacher_user_id` links survive deactivation, by design — no cascade),
`test_toggle_rejects_missing_or_non_boolean_active` (422 on malformed body),
`test_unauthenticated_cannot_toggle_team_account` (401).

## 7. Findings — checked, no code change needed

- **Race conditions:** two concurrent `PATCH` requests on the same account have no row lock
  (`with_for_update`); last write wins, both attempts audited independently. Acceptable for an
  admin action with human-driven pacing and no data-corruption path. No change.
- **Transaction boundaries:** `target.active = payload["active"]` and the `AuditLog` insert commit
  together in one transaction (`schools.py:197-202`). Already atomic. No change.
- **Authorization:** own-institution scoping, self/peer-Coordinator exclusion, and non-coordinator
  rejection are each independently tested (§6). No change.
- **Frontend loading/empty states:** `SchoolTeamPanel.tsx` already shows per-row "Saving…" /
  disabled state while a toggle is in flight, and "It's just you so far…" for an empty roster. No
  change.

## 8. Findings — residual, documented but not fixed in this round

- **Frontend network-failure handling.** `SchoolTeamPanel.tsx`'s `toggleActive()` has no
  `try`/`catch` around its `fetch` call. An HTTP error response (4xx/5xx) is handled correctly
  (`rowMessage` shows the server's error text), but a *thrown* exception — an actual network
  failure — is unhandled: the row stays on "Saving…" indefinitely with `busyId` never cleared, and
  no error is shown. `ChangePasswordForm` (`ENH-006`) has a deliberate, tested pattern for exactly
  this case ("…could not confirm whether your password was changed…"). Out of scope for this
  round (user chose verification + docs only); left here so it is not silently lost.

## 9. Test plan (executed, not just read)

Run for real, on the `feature/enh-010-account-activation` worktree, once the user confirms the
Docker stack is up:

1. **New test — closes the §6 gap.** Append to
   `apps/api/tests/test_sch_team_account_activation.py`:

   ```python
   @pytest.mark.asyncio
   async def test_deactivated_teacher_cannot_log_in_and_reactivation_restores_access(client, db_session):
       ctx = await _create_school_with_roles(db_session)
       await _login(client, ctx["school_coordinator"].email)
       teacher = ctx["school_teacher"]

       deactivated = await client.patch(f"/api/v1/school/team/accounts/{teacher.id}", json={"active": False})
       assert deactivated.status_code == 200

       blocked = await client.post("/api/v1/auth/login", json={"email": teacher.email, "password": PASSWORD, "division": "overseas"})
       assert blocked.status_code == 401

       reactivated = await client.patch(f"/api/v1/school/team/accounts/{teacher.id}", json={"active": True})
       assert reactivated.status_code == 200

       restored = await client.post("/api/v1/auth/login", json={"email": teacher.email, "password": PASSWORD, "division": "overseas"})
       assert restored.status_code == 200
   ```

   Placed after `test_coordinator_deactivates_and_reactivates_a_teacher` (same fixtures, same
   style — `_login` uses the coordinator's session for the `PATCH` calls; the teacher's own
   `/auth/login` call is unauthenticated, matching how `_login` itself calls the endpoint).

2. **Full existing file:** `docker compose exec api python -m pytest -q
   tests/test_sch_team_account_activation.py` — expect 8/8 PASS (7 existing + 1 new).

3. **Adjacent regression suites** (same pattern ENH-006's plan used — confirm nothing this touches
   broke): `docker compose exec api python -m pytest -q tests/test_role_assignments.py
   tests/test_sec_001_audit_trail.py tests/test_sch_001_school_portal_access.py` — expect PASS,
   unchanged counts.

4. **E2E:** `cd apps/web && npx playwright test tests/e2e/sch-team-management.spec.ts --workers=1`
   — expect 2/2 PASS. Requires the `web` image already built for this branch (no frontend changes
   in this round, so no rebuild needed unless the image predates the worktree).

5. **Record the actual output** (pass/fail counts, not a summary) as this round's Release Evidence
   (§4's chain, last link).

## 10. Documentation to update (after §9 passes)

- `docs/decisions/PRODUCT_DECISION_REGISTER.md` — add `DEC-SCOPE-023` (§3), status
  `PENDING_CONFIRMATION`.
- `docs/delivery/ENHANCEMENT_BACKLOG.md` — ENH-010 entry: mark the "Existing behavior" line
  `SUPERSEDED` in place (append, don't delete), add a resolution note citing this spec, the test
  run, and `DEC-SCOPE-023`.
- `docs/quality/RTM.md` — row `B2`: same treatment, plus the §6 AC→test table.
- `docs/product/PRD_OPEN_ITEMS.md` — check whether ENH-010/`B2` appears there; close if so (not
  yet confirmed either way — verify before editing).

## 11. Open, not decided here

- Whether `DEC-SCOPE-023` is actually confirmed — the user's call, not made by writing this spec.
- The §8 frontend network-failure gap — left open for a future round.
- The two non-goals in §2 (typed schema, frontend unit tests) — available as future hardening if
  wanted, not committed to.
