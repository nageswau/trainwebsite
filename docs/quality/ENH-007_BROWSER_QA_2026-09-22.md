# ENH-007 — Browser QA Evidence, 2026-09-22

Two passes, real Chrome via `browser-use`, against this worktree's own stack (`api` :8020, `web` :3020).
Recorded per this project's ENH-004/ENH-006 precedent, after an independent review (Codex) correctly
found no dedicated QA-evidence file existed for this feature — the passes happened, but were only
reported in-session and summarized inline in `RTM.md`/`ENHANCEMENT_BACKLOG.md`.

## Pass 1 — confirmatory (shared local Chrome)

All 7 School-domain roles (`school.coordinator`, `school.principal`, `school.teacher`, `school.parent`,
`school.academic1`, `school.careercounselor`, `school.psychometric`, all `@edusphere.local` /
`Demo@123`): login → dashboard → sidebar "My profile" link (front-loaded after "Change password") →
`/account/profile` renders with current name/phone → edit → save → reload-persistence → restored to
seeded value. Zero defects. Plus: mobile menu at 375px (front-loaded, not buried), a real 1-character
name submission (genuine 422, nothing saved, verified via the API), a simulated offline network
("Network error. Try again.", no false success), and the signed-out state ("Sign in required", working
links).

**Environmental note, not an app defect:** this pass ran in a Chrome instance apparently shared with
other concurrent sessions on this machine. Twice, the CDP "current tab" attachment silently drifted to
another worktree's tab (observed on ports `:3010`, `:3030`), and the test session was unexpectedly signed
out twice with no action taken — most likely because Chrome does not partition cookies by port for the
bare `localhost` hostname, so a concurrent session's login/logout on a *different* worktree's dev server
cleared cookies also sent to this one's origin. Worked around by explicitly re-pinning the tab and
re-authenticating before every subsequent action; all findings from this pass were independently
reproduced in Pass 2's fully isolated environment.

## Pass 2 — adversarial/exploratory (isolated Chrome instance)

Per an explicit request for independence from any prior confirmatory bias, and to eliminate Pass 1's
environmental noise: launched a dedicated Chrome instance (`chrome.exe --remote-debugging-port=9333
--user-data-dir=%LOCALAPPDATA%\enh007-chrome-profile`), connected via a separately named `browser-use`
daemon (`BU_NAME=enh007`). Confirmed isolated — its own empty tab set, its own cookie jar, no
cross-session interference for the remainder of the pass.

Covered: happy path (re-verified, all 7 roles), invalid inputs, empty states, simulated server errors,
loading/busy state, duplicate submission, unauthorized/signed-out access, cross-role access (a non-target
role, IT student, also works correctly — the route is intentionally shared, not role-gated), desktop/
tablet/375px-mobile layouts, navigation (back button, back-to-dashboard link), success/error messaging,
broken images, console errors, failed network calls, unexpected redirects.

### Findings

| ID | Severity | Role | Page | Repro | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| ENH007-QA-01 | High | Any (repro'd as `school_coordinator`) | `/account/profile` | Clear "Full name", type only spaces (e.g. 5), click "Save changes" | Rejected with a visible error; nothing saved | UI shows "Your profile was updated." (false success); `GET /api/v1/auth/me` confirms `full_name` saved as `""` | **Fixed, 2026-09-22** — see below |
| ENH007-QA-02 | Low | Any | `/account/profile` | Force `PATCH /auth/me` to return a real FastAPI-shaped `500 {"detail":"Internal Server Error"}` | The component's own friendly fallback ("Unable to update your profile. Try again in a moment.") | Raw string `"Internal Server Error"` shown verbatim | **Open** — cosmetic, not fixed in this pass (see Disposition) |

Both reproduced identically in the isolated Chrome (Pass 2), confirming they are genuine application
defects, not artifacts of Pass 1's environmental contamination. Confirmed clean in both passes: zero
console errors, zero uncaught exceptions, zero unhandled promise rejections throughout. One pre-existing,
already-documented (`docs/superpowers/specs/2026-09-21-enh-006-change-password-design.md` §13, "Pre-existing,
observed and not changed") top-announcement-bar clipping at 375px — unrelated to this feature, not
re-reported as new.

Test-account hygiene: every edited seeded account was restored to its exact original `full_name`/`phone`
after each check (verified via a follow-up `GET /api/v1/auth/me`, not just the UI's own claim), including
after ENH007-QA-01's whitespace-corruption in both passes.

## Disposition

- **ENH007-QA-01**: root cause was `ProfileUpdate.full_name`'s `min_length=2` counting raw string length
  (whitespace included) and the field's only validator checking for `None` only, not blank. Fixed
  alongside the Codex review's findings (`apps/api/app/schemas.py`) — see
  `docs/superpowers/specs/2026-09-22-enh-007-profile-self-service-design.md` for the design record and
  `apps/api/tests/test_enh_007_profile_self_service.py` for the regression test.
- **ENH007-QA-02**: left open. Cosmetic only (no data loss, no false success), and fixing it well means
  deciding a message-mapping policy for every raw-string `detail` this endpoint could ever return — a
  slightly bigger decision than this pass's scope. Tracked here rather than silently dropped.
