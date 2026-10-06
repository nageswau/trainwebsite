# bdm-008 — Independent exploratory QA, pass 2 (2026-10-06)

**No code was changed in this pass.** Build under test: `feature/bdm-008-follow-ups` @ `d66de2d6` (web image built from `d5604c04`; the
later commits change only tests and docs), compose project `bdm008qa` (web `localhost:3108`, API `localhost:8108`, DB at
`0077_bdm_tasks_followups`, seeded).
**Tools:** Browser Use is **not installed** on this machine (`browser_use` not importable, no CLI). As in the bdm-007 pass, throwaway
Playwright scripts ran in the `web-test` container — an **isolated Chromium context per scenario** (base URL
`http://host.docker.internal:3108`) recording console errors, page errors, every 4xx/5xx response, failed requests, main-frame
navigations, browser dialogs and broken images, with screenshots. Scripts kept outside the repository. Evidence (screenshots, per-scenario
JSON logs): `artifacts/ci/qa8b/` (git-ignored).
**Accounts and data** (real admin API + welcome tokens; fresh for this pass): BDM Manager "Meera" (team: College BDMs "Asha" and "Ravi",
Agent BDM "Anil"), BDM Manager "Bala" (team: College BDM "Pagi"), seeded IT admin. Asha: St Mary College, KTU University, Old Partner
College; five items (one with multi-line notes), one moved two days into the past by SQL (the API never accepts a past due date), and
one meeting-report follow-up (appointment moved into the past by SQL, completed through the API with a follow-up date). Anil: one agency
follow-up. Pagi: 55 items (paging). Mocked failures used Playwright routing (500 / 503 / offline / delays).

## Coverage

| # | Area | Result |
|---|---|---|
| 1 | Happy path | Pass — sidebar "Follow-ups" (`aria-current`), tabs `Today (2) · Overdue (1) · Upcoming (3)`; add with the organization picker → "Added.", row shows the organization; Done → "Marked done." + Log activity / Book appointment; Log activity lands with the Activity section in view; Book appointment opens the booking form with the organization prefilled; meeting-report follow-up shows "From APT-…" (opens the appointment), Done only |
| 2 | Invalid inputs | Pass — whitespace title refused client-side; title capped at 200, notes at 2000 (counter 2000/2000), reason at 500; a typed past due date → 422 shown on the due field (`aria-invalid`), text kept; edit to a past date → same; whitespace reason → "Enter a reason."; API: bad kind, control character, bad date format, server-owned field, malformed UUID → 422; another module's organization → 404; `PATCH title: null` → 422; `bucket=soon` → 422; junk URL params fall back to Today |
| 3 | Empty states | Pass — each tab's own text ("Nothing due today.", "No overdue follow-ups.", "Nothing upcoming.", "Nothing done yet.", "Nothing cancelled."), no chips when nothing to count, "No items match these filters." + Clear filters (resets the URL); org section "No open follow-ups or tasks." |
| 4 | Server errors | List 503 → "Unable to load follow-ups." + Retry recovers; offline cancel → the connection message with the reason kept. **QA8B-01**, **QA8B-03** |
| 5 | Loading states | Pass — first load shows the route skeleton; tab switch keeps the old rows dimmed with "Updating…" and `aria-busy`; Done → "Saving…" disabled. **QA8B-06** |
| 6 | Cancel / back | Pass — Cancel on edit leaves the item unchanged; "Keep it" closes the reason form; dirty add form + nav link → "Discard this task?" (dismiss keeps the draft); Back with a dirty form returns to the previous filter with the draft kept |
| 7 | Refresh | Pass — tab and chip survive a reload (URL state); dirty form + reload → the browser's leave prompt. **QA8B-05** (manager BDM filter) |
| 8 | Duplicate submission | Pass — double-click Done → 1 request; double-click Save changes → 1 PATCH; double-click "Cancel it" → 1 request; Enter twice on Add → 1 create |
| 9 | Unauthorized | Pass — `/bdm/follow-ups(?bucket=…)` → `/bdm/sign-in?next=…`; College BDM link keeps `next`; signing in returns to `/bdm/follow-ups?bucket=overdue`; `/bdm/manager/follow-ups` → `/admin/login?next=…`; API GET / POST / complete → 401. Expired session mid-page: **QA8B-02** |
| 10 | Incorrect role | Pass — manager / IT admin on `/bdm/follow-ups` → "Access unavailable — BDM role required" + dashboard link; IT admin / BDM on `/bdm/manager/follow-ups` → "This page is for BDM managers."; IT admin API → 403; manager API complete → 403; peer BDM completing another's task → 404; manager sees no write controls (list and organization section); manager B sees nothing of A's team |
| 11 | Desktop (1440 / 1280) | Pass — no overflow on the list, the form and the organization page. **QA8B-07** |
| 12 | Tablet (1024 / 768) | Pass — no overflow; at 768 the sidebar collapses and "Follow-ups" is reachable from the menu |
| 13 | Mobile (390 / 320) | Pass — no overflow on the list, open form and organization page; menu reaches "Follow-ups" |
| 14 | Navigation | Pass — paging "Showing 1–50 of 55", Next → `offset=50`, count stays 55, Back → page 1, `offset=500` → "This page is past the end of the list." + Go to the first page; organization / appointment links; manager links go to the manager views |
| 15 | Success messages | "Added.", "Changes saved.", "Cancelled.", "Marked done." in a polite status region; organization section notices in the profile's status line. **QA8B-04** |
| 16 | Error messages | Field-level 422s are clear; see **QA8B-01**, **QA8B-02**, **QA8B-03** |
| 17 | Broken images | None on any page or width |
| 18 | Console errors | No page errors (`pageerror`) in any scenario. Console only shows "Failed to load resource" for intentional 4xx/5xx/offline |
| 19 | Failed network calls | Only the intentional ones, and `net::ERR_ABORTED` on Next.js link prefetches (benign) |
| 20 | Unexpected redirects | None — signed-out redirects carry `next=` and land back on the requested page; wrong-role pages stay put with "Access unavailable" |

Archive flow also verified: Archive on the organization profile → the section reloads empty; the items are under Cancelled with the
organization marked "Archived" and "— Organization archived"; a manager restore leaves them cancelled (not reopened).

## Issues

### QA8B-01 — A server error is reported as "This item changed elsewhere"
- **Severity:** Medium · **Role:** BDM · **Page:** `/bdm/follow-ups` (also the organization profile section)
- **Steps:** open Today → make `POST /api/v1/bdm/tasks/{id}/complete` fail with 500 (any server fault) → press Done.
- **Expected:** a failure message that says the save didn't work and to try again (the bdm-007 pattern: "We couldn't update … Please try again."), the row left as it was.
- **Actual:** status line "Internal Server Error. This item changed elsewhere — the list has been reloaded." — the item did not change elsewhere; the list reloads as if it had. Same wording path for edit / cancel 5xx.
- **Evidence:** network `500 POST /api/v1/bdm/tasks/5dd16320-…/complete`; console "Failed to load resource: … 500"; screenshot `artifacts/ci/qa8b/06-server-errors-done-500.png`.

### QA8B-02 — Expired session: wrong message, no way back to sign-in
- **Severity:** Medium · **Role:** BDM · **Page:** `/bdm/follow-ups`
- **Steps:** sign in, open Follow-ups → the session ends (cookie cleared / expired) → press Done.
- **Expected:** "Your session has ended — sign in again" with a sign-in link that returns here (the `ReturnToLoginLink` pattern), no misleading conflict text.
- **Actual:** "Not authenticated. This item changed elsewhere — the list has been reloaded." plus "Unable to load follow-ups." with a Retry that can never succeed; the stale tab counts and "Add follow-up or task" stay on screen; no sign-in link.
- **Evidence:** network `401 POST /api/v1/bdm/tasks/5dd16320-…/complete`, `401 GET /api/v1/bdm/tasks?bucket=today…`; screenshot `artifacts/ci/qa8b/07-session-expired-expired.png`.

### QA8B-03 — Raw server text in the add form
- **Severity:** Low · **Role:** BDM · **Page:** `/bdm/follow-ups` add form (also edit)
- **Steps:** Add follow-up or task → fill → the create fails with 500.
- **Expected:** a plain message ("We couldn't save this. Please try again.") with the text kept.
- **Actual:** "Internal Server Error" (the server's raw detail); the typed text is kept (good).
- **Evidence:** `500 POST /api/v1/bdm/tasks`; screenshot `artifacts/ci/qa8b/06-server-errors-create-500.png`.

### QA8B-04 — The "Marked done." notice and its links outlive the context
- **Severity:** Low · **Role:** BDM · **Page:** `/bdm/follow-ups`
- **Steps:** Today → Done on an item → switch to Upcoming (or change a chip / page).
- **Expected:** the notice clears when the list context changes (or is scoped to the moment of the action).
- **Actual:** "Marked done." with Log activity / Book appointment stays above an unrelated list until the next action.
- **Evidence:** screenshot `artifacts/ci/qa8b/R01-add-with-org-notice-after-tab.png`; no network error.

### QA8B-05 — Manager's BDM filter is invisible after a reload or a shared link
- **Severity:** Low · **Role:** BDM Manager · **Page:** `/bdm/manager/follow-ups?bdm=<id>`
- **Steps:** as Meera, pick "Asha College" in the BDM filter → reload (or open the copied URL).
- **Expected:** the filter is visible ("Showing one BDM" + Show all, as on `/bdm/manager/appointments`, or the BDM name in the box).
- **Actual:** the BDM box is empty while the list and counts are filtered (here "No items match these filters." on Today); only "Clear filters" hints that something is applied.
- **Evidence:** URL `?bdm=a1926ebf-…`; screenshot `artifacts/ci/qa8b/E3-manager-filter-reload.png`; no network error.

### QA8B-06 — Edit / Cancel task stay enabled while Done is saving
- **Severity:** Low · **Role:** BDM · **Page:** `/bdm/follow-ups`
- **Steps:** slow network → press Done on a manual item → while "Saving…" shows, press Edit.
- **Expected:** the row's other actions are disabled until the save finishes.
- **Actual:** Edit and Cancel task stay enabled; opening Edit on an item that is being completed leads to a 409 on save.
- **Evidence:** observed with a 2.5 s delay on `/complete`; `08-loading` log entry "Edit / Cancel task during save enabled: true".

### QA8B-07 — Small link targets in the item's detail line (advisory)
- **Severity:** Low (accessibility advisory) · **Role:** BDM, BDM Manager · **Page:** `/bdm/follow-ups`, `/bdm/manager/follow-ups`
- **Steps:** measure the organization link and "From APT-…" link on a row.
- **Expected:** ≥ 24 × 24 px targets (WCAG 2.2 SC 2.5.8) or enough spacing; inline-text links are exempt.
- **Actual:** organization link 18 px tall, "From APT-…" 23 px, in a wrapped metadata line (arguably inline text, hence advisory).
- **Evidence:** `14-desktop-1440` … `18-mobile-320` log entries; screenshots `artifacts/ci/qa8b/17-mobile-390-list.png`.

## Not issues (checked)

- First load shows the route skeleton (`loading.tsx`), not the panel's "Loading follow-ups…" — expected.
- Booking form prefill after "Book appointment" — the organization combobox holds "St Mary College … — ORG-000021".
- Signing in from the chooser returns to the requested follow-ups URL.
- Wrong-role pages render "Access unavailable" with a dashboard link (no redirect loop).

## Fixes (2026-10-06, after this pass; commit `922d60e9`)

All seven fixed test-first (each new test seen failing first), then re-checked in the browser on a rebuilt web container:

| ID | Fix | Test | Browser re-check |
|---|---|---|---|
| QA8B-01 | `writeFailure()` in `lib/bdmTasks.ts`: only 403 / 404 / 409 mean "changed elsewhere"; a 5xx says "We couldn't save this. Please try again." and leaves the row | `BdmTaskItem.test.tsx` "says a server error didn't save…", `bdmTasks.test.ts` "sorts a failed write…" | Pass — `V01-done-500.png` |
| QA8B-02 | A 401 on a row action, the form or the list shows "Your session has ended — sign in again to continue." with `ReturnToLoginLink` (returns here); the list drops the useless Retry | `BdmTaskItem` / `BdmTaskForm` / `BdmTasksPanel` "…session has ended…" | Pass — link `/bdm/sign-in?next=%2Fbdm%2Ffollow-ups%3Fbucket%3Dupcoming`; `V02-session.png` |
| QA8B-03 | The form never shows a 5xx's raw text; typed text kept | `BdmTaskForm.test.tsx` "words a server error plainly…" | Pass |
| QA8B-04 | The notice clears when the list URL (tab / filter / page) changes; a reload after a write keeps it | `BdmTasksPanel.test.tsx` "clears the Done notice…" | Pass |
| QA8B-05 | Manager view: "Showing one BDM: <name>" + Show all when `?bdm=` is set | `BdmTasksPanel.test.tsx` "shows which BDM…" | Pass — `V05-manager-filter.png` |
| QA8B-06 | Edit / Cancel task disabled while a save is in flight | `BdmTaskItem.test.tsx` "disables the row's other actions…" | Pass |
| QA8B-07 | Detail-line links are `inline-block`, min 24 px tall | `BdmTaskItem.test.tsx` "gives the detail-line links a 24px target" | Pass — 24 / 24.25 px; no overflow at 320 px |

After the fixes: web BDM set 431 passed (47 files), `tsc` 0, eslint 0; Playwright `bdm-008-follow-ups.spec.ts` passed on the rebuilt
stack. **Not covered:** the full backend / web suites (owner), the independent Codex review.
