# ENH-027 — Browser QA record (2026-09-28)

**Scope:** exploratory QA of ENH-027 (psychometric record: structured result fields) on branch
`feature/enh-027-psychometric-full-record`, then one fix pass and a browser re-test.

**Environment:** isolated Compose project `enh027` (web :3027, API :8027, own Postgres on 127.0.0.1:5427), an isolated
Chrome (throwaway profile, CDP :9227) driven by Browser Use. Throwaway data created through the API only: School A
(Platinum: coordinator, Psychometric Team, Academic Team, Career Counsellor, assigned teacher, a student with a linked
parent and an assigned assessment, a second student with no records), School B (Platinum: another portfolio's
Psychometric Team and parent), School C (Bronze, its partnership expired mid-edit through the admin API).

**Covered:** happy path, invalid inputs, empty states, a real 403 (expired partnership) plus an injected 500 and a
connection reset, loading under 3 s latency, cancel/back, refresh, triple-click duplicate submission, signed-out
access, wrong roles (other school's parent and Psychometric Team, coordinator, teacher — UI and direct API writes),
desktop 1440 / tablet 768 / mobile 375, navigation, success and error messages, broken images, console errors,
failed network calls, unexpected redirects, markup in fields, a long unbroken word at 375 px, two editors on one
record (different fields). **Not covered:** a real backend outage (simulated by interception), browsers other than
Chrome, screen readers.

## Findings and resolution

| ID | Sev. | Finding | Resolution | Commit | Test |
|---|---|---|---|---|---|
| QA27-01 | Low | Stale success messages ("No changes to save.", "Results saved.") stayed on screen next to a new field error / after a new card opened | A blocked save clears the editor status; opening either card clears an old success message (a failed assign message stays with its form) | `ea67e59` | form + panel unit tests |
| QA27-02 | Medium | In-app links (sidebar, 360° links) discarded unsaved results with no warning; only reload/close were guarded | While dirty, a same-origin link click asks "Leave without saving your results?"; No keeps page and text | `13247e8` | form unit test; browser: dialog seen, Cancel stays, OK navigates |
| QA27-03 | Low | A server 500 showed only "Something went wrong." | Editor-only wording: "Something went wrong on our side. Your entry is kept — try again in a moment." (`sendJson` failures now also carry `status`; other screens' wording unchanged) | `96fb421` | form + `sendJson` unit tests |
| QA27-04 | Low | An ended session showed the raw "Not authenticated", with no way back that keeps the typed text | Editor-only: "Your session has ended. Sign in again in a new tab, then press Save here — your entry is kept." + a "Sign in again (opens a new tab)" link | `96fb421` | form unit test; browser: signed in in a new tab, Save in the original tab → 200 |
| QA27-05 | Medium | At 375 px the Status/Actions columns were off-screen; scrolling to the results button hid the student's name | ≤640 px: each assessment row is a card (Student, Assessment, Status, Actions); desktop/tablet keep the table | `6d39700` | panel unit test; E2E at 375 px (button right edge was 664 px before, inside 375 after) |
| QA27-06 | Low | The 360° table's "Date" column (assignment day) read as the new Test date | Renamed "Assigned on", matching the parent page | `479cfac` | 360° panel unit test |

**Observations, not defects (by design):** status stays "Assigned" when results exist but no report is attached
(`DEC-SCOPE-034` Q6); a test date earlier than the assignment date is accepted (no cross-field rule specified); long
comma lists are truncated inside single-line inputs on phones (Q9 convention); signed-out pages show "Access
unavailable / Return to login" rather than redirecting (existing app pattern).

**Harness notes (not app issues):** Chrome's date inputs ignore CDP text insertion (real key presses used); the site's
`scroll-behavior: smooth` requires waiting before measuring click targets; the isolated window needed focus emulation
for clicks to focus inputs.

## Re-test after the fix pass (rebuilt `web`, same isolated browser)

All six fixed and re-verified in the browser. Web: vitest **91 files / 971 tests**; `tsc` exit 0; `eslint .` 0 errors /
31 warnings (baseline); `npm run build` exit 0. E2E `enh-027-psychometric-results.spec.ts` **5/5** (adds the 375 px card
check). `enh-013-student-360.spec.ts` still fails in its own setup (tierless school → 403), pre-existing on `main` and
unrelated to these changes.
