# ENH-010 — browser QA record (2026-09-22)

Feature: School Coordinator account activation/deactivation (`ENH-010`, `School CRM.md` Part B
§2, `DEC-SCOPE-023` drafted). Tool: Browser Use (CDP) against the running web app — local Chrome,
relaunched with `--remote-debugging-port` (user-approved) after the daemon's default auto-launch
failed to find an existing debug port.

**Status of this record: NOT a completion record.** An independent Codex review followed this
pass; two of its findings (audit-log and deactivated-login coverage) were closed by automated
tests added afterward, not by this browser pass — see the AC table below for what this pass
itself did and did not establish.

## Method and environment

- **Stack:** this worktree's own isolated compose project (`enh-010-*`: web `:3000`, API `:8000`,
  its own Postgres/Redis/Caddy), seeded via `python -m app.seed` (demo password `Demo@123`).
- **Roles exercised:** School Coordinator (actor, `school.coordinator@edusphere.local`),
  Principal, Teacher, Parent (same seeded school), and unauthenticated.
- **Viewports:** desktop (default), tablet (768px), mobile (375px).
- **Not covered:** browsers other than Chrome, screen readers, real touch devices, a production
  build behind a real proxy, or a second freshly-provisioned school — so the true empty-roster
  state and a *live* cross-institution deactivation attempt were not re-verified in the browser;
  both are covered instead by the automated backend suite
  (`apps/api/tests/test_sch_team_account_activation.py`).

## Findings

| ID | Severity | Role | Page | Finding | Status |
|---|---|---|---|---|---|
| ENH010-QA-01 | Medium | Coordinator | `/school/coordinator/team` | Rapid repeat clicks on Deactivate/Reactivate fired multiple redundant `PATCH` requests (3 clicks → 3 requests), because `busyId`'s re-render hadn't committed yet when a 2nd/3rd click landed in the same tick. The duplicate requests were idempotent server-side (each computed the same target value from the same pre-click render), so the real exposure was duplicate `AuditLog` rows, not a state flip. | Fixed (`fbf401b`, corrected `4c5128b`): a `useRef<Set<string>>` per-row re-entrancy guard, mirroring `ChangePasswordForm`'s `submitting` ref pattern. Verified with a genuine RED (guard removed → 3 fetch calls) / GREEN (guard present → 1 fetch call) test — the first test attempt didn't actually discriminate the bug (jsdom's native disabled-button click suppression already blocked clicks 2–3 regardless of the guard) and was corrected during task review. |
| ENH010-QA-02 | Low | Coordinator | `/school/coordinator/team` | Roster row order isn't stable across a refresh — `list_team`'s query (`schools.py:160-166`) has no `ORDER BY`. | Not fixed — pre-existing `SCH-003` query, unrelated to account activation, out of ENH-010's scope. |
| ENH010-QA-03 | Info | — (layout) | `/school/coordinator/team` at 375px | Deactivate/Reactivate buttons measure ~38px tall, under the 44px touch-target guideline. | Not fixed — systemic to the shared `.btn.small` class used app-wide, not introduced by ENH-010. |

**False positive ruled out:** the sidebar logo briefly read as broken (`naturalWidth === 0` via
`[...document.images]`) — it is `loading="lazy"` and hadn't decoded yet; a direct fetch confirmed
`200 OK`.

**Clean:** console errors (instrumented `window.onerror`/`unhandledrejection` for the whole
session), failed/unexpected network calls (only intentional test probes seen), broken images
(after the false positive above), unexpected redirects, tablet overflow (`.table-wrap` scrolls
correctly), mobile page-level overflow.

## Acceptance criteria — observed live, not read from code

| AC | Result |
|---|---|
| 1. Coordinator can deactivate/reactivate a user within their own institution | **PASS** — toggled Teacher Active→Inactive→Active, correct success copy both times |
| 2. A deactivated user cannot authenticate | **PASS** — deactivated teacher's login returned generic "Invalid credentials," which doesn't leak that the account is specifically deactivated |
| 3. Action is audit-logged (actor, target, timestamp) | **Not observable from a browser** — closed instead by `test_coordinator_deactivates_and_reactivates_a_teacher`'s `AuditLog` assertion, added after this pass |
| 4. Cannot deactivate own account or above own authority | **PASS** for the authority half — own account blocked (`403`, UI hides the toggle entirely); Principal/Parent get `403` both on the page and on a direct API call; unauthenticated gets `401`. Cross-institution half not re-verified live in this pass — covered by `test_coordinator_cannot_toggle_another_schools_account`. |

**Bonus, confirmed live:** malformed body → `422`; malformed UUID → `422`; well-formed but
nonexistent UUID → `404`; wrong-role callers (Principal, Parent) → `403`.
