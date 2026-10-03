# bdm-010 — Browser QA, pass 1 (2026-10-03)

**Scope:** bdm-010 travel requests, approval, expenses. Exploratory QA only; **no code was changed** in this pass.

**Build under test:** branch `worktree-bdm-010` @ `377e898e`.

**Environment:**
- isolated compose project `bdm010qa`: web `http://localhost:3010`, API `http://localhost:8010`, migration `0066_bdm_trips` (head), seeded;
- isolated Chrome (its own temporary profile, CDP port 9333) driven by Browser Use;
- Playwright run from the `web-test` container against the same stack.

**Test users** were created through the real admin API:
- `QA Manager One` (m1) and `QA Manager Two` (m2);
- `QA Asha BDM` (College, reports to m1);
- `QA Ravi BDM` (Agent, reports to m1);
- `QA Other BDM` (School, reports to m2);
- the seeded `superadmin@edusphere.local`.

**Evidence capture:**
- a page probe recorded console errors and warnings, uncaught errors, unhandled rejections, non-OK responses and failed fetches on every page;
- screenshots are in the session scratchpad (`qa/*.png`), named in the issues below.

## Summary

| Area | Result |
|---|---|
| Happy path (create → submit → approve → expenses → start → complete → remarks) | Pass |
| Reject with reason → BDM sees it → edit → resubmit | Pass |
| Super-admin fallback (manager inactive) | Pass |
| Authorization (signed out, other BDM, other team, wrong role) | Pass — every case gives the right redirect or "Trip not found" / role message |
| Duplicate submission (double-click Submit) | Pass — one `POST`, 200 |
| Refresh, Back / Forward, filter, past-the-end offset | Pass |
| Loading skeletons (2.5 s latency) | Pass |
| Server down → page Retry panel | Pass |
| Responsive 1366 / 768 / 375 / 320 px | No page-level horizontal scroll anywhere |
| Console errors / broken images | None seen in the whole run |
| Issues | 0 Critical, 0 High, 6 Medium, 11 Low (QA10-16/17 found by the Playwright fix pass) |

## Issues

### QA10-01 — In-app notices are stored but never shown · Medium

- **Role:** BDM Manager, BDM.
- **Page:** every BDM and manager page (no notifications entry anywhere).
- **Steps:**
  1. As a BDM, submit a trip.
  2. Sign in as their manager.
  3. Look for the "Travel approval needed" notice.
  4. Approve the trip, then sign in as the BDM and look for "Trip approved".
- **Expected:** the manager is notified in-app (AC2) and can open the approvals queue from the notice. The BDM sees the decision notice (T12).
- **Actual:** neither nav has a notifications item, bell or badge, so the notices can't be seen.
- **Evidence:**
  - `GET /api/v1/workflows/notifications` as m1 → 200 `[["Travel approval needed","TRV-000001: Hyderabad → Vijayawada, 03 Oct 2026","/bdm/manager/approvals",false]]`;
  - as b1 → `[["Trip approved","/bdm/travel/9184f803-…"]]`;
  - no notifications page exists for these roles in the app tree (only the School roles have one).

### QA10-02 — Focus is lost after adding an expense, and the save isn't announced · Medium (accessibility)

- **Role:** BDM.
- **Page:** `/bdm/travel/{id}` (approved trip).
- **Steps:**
  1. Click Add expense.
  2. Fill the line and press Save expense.
- **Expected:** focus lands on a result ("Expense added.") or on a stable control.
- **Actual:** focus falls to `<body>`, and no success message is shown or announced. The cost summary does update.
- **Evidence:** `POST …/expenses` → 201; `document.activeElement` = `BODY`; no `role=status` text. (Delete and Edit do move focus to their result message.)

### QA10-03 — Reject form stays open after the trip changed, and the 409 wording is awkward · Medium

- **Role:** BDM Manager.
- **Page:** `/bdm/manager/trips/{id}`.
- **Steps:**
  1. The manager opens Reject and types a reason.
  2. Meanwhile the BDM withdraws the trip.
  3. The manager presses Confirm reject.
- **Expected:** the message explains that the trip was withdrawn, and the decision form closes, because the trip is no longer decidable.
- **Actual:** the alert reads "This trip is draft and can't be decided". The page refreshes to "Approval: Draft", but the reason box and Confirm reject stay on screen, and every retry gets another 409.
- **Evidence:** `POST …/reject` → 409 `{"detail":"This trip is draft and can't be decided"}`. Screenshot `12-conflict-reject-after-withdraw.png`.

### QA10-04 — A malformed trip link shows "Travel is not available right now" · Medium

- **Role:** BDM, BDM Manager.
- **Page:** `/bdm/travel/not-a-uuid` and `/bdm/manager/trips/not-a-uuid`.
- **Steps:** open a trip URL with a malformed id, e.g. a truncated link.
- **Expected:** "Trip not found", the same as an unknown id.
- **Actual:** the temporary-outage panel "Travel is not available right now … Retry" appears, and Retry can never succeed.
- **Evidence:** `GET /api/v1/bdm/trips/not-a-uuid` → 422 `uuid_parsing`. The page's error handler treats any status other than 401/403/404 as an outage.

### QA10-05 — The empty-state link isn't recognisable as a link · Medium (accessibility, WCAG 1.4.1)

- **Role:** BDM.
- **Page:** `/bdm/travel` with no trips.
- **Steps:** look at "No trips yet — create your first trip."
- **Expected:** "create your first trip" looks like a link (colour and/or underline).
- **Actual:** it has the same colour as the surrounding text and no underline. The same applies to "Clear filter" and "Go to the first page" inside `.empty`.
- **Evidence:** computed style — link `rgb(97,114,138)`, `text-decoration: none`; paragraph `rgb(97,114,138)`. Screenshot `01-bdm-travel-empty-desktop.png`.

### QA10-06 — An unreachable API gives a generic error, loses focus, and shows no progress · Low

- **Role:** BDM.
- **Page:** `/bdm/travel/{id}`.
- **Steps:** with the page loaded, stop the API and press Submit for approval.
- **Expected:** a clear "didn't complete, try again" message, a "Saving…" label while waiting, and focus kept on the page.
- **Actual:**
  - for about 4 s the buttons are disabled but their labels don't change;
  - then "Something went wrong." appears;
  - focus ends on `<body>`.
- **Evidence:** `POST …/submit` → 500 with an empty body (from the Next proxy). Screenshot `16-action-api-down.png`.

### QA10-07 — Date-rule errors appear only at the bottom of the form · Low

- **Role:** BDM.
- **Page:** `/bdm/travel/new` and the edit form.
- **Steps:** set a return date 32 days after the travel date and save.
- **Expected:** the error sits next to Return date, and ideally the picker blocks it with a `max`.
- **Actual:** "A trip can last at most 31 days" appears only in the summary under the Save button. No field is marked invalid, and the client doesn't check the span.
- **Evidence:** `POST /api/v1/bdm/trips` → 422 `{"detail":"A trip can last at most 31 days"}`, a string rather than a field-mapped list.

### QA10-08 — A 5- or 6-digit year reaches the API and shows raw validator text · Low

- **Role:** BDM.
- **Page:** `/bdm/travel/new`.
- **Steps:** in Chrome's date picker, keep typing in the year segment (Chrome accepts up to 6 digits), then save.
- **Expected:** a plain message, such as "Enter a valid date".
- **Actual:** both date fields show "Input should be a valid date or datetime, invalid date separator, expected `-`".
- **Evidence:** `POST /api/v1/bdm/trips` → 422, `input: "61008-02-20"`.
- **Note:** I reached this through the harness's typed input. I couldn't reproduce it with plain key presses, so please confirm manually.

### QA10-09 — Success messages pile up on the trip page · Low

- **Role:** BDM.
- **Page:** `/bdm/travel/{id}`.
- **Steps:** delete an expense, complete the trip, then save remarks.
- **Expected:** one current result at a time.
- **Actual:** "Trip completed.", "Expense deleted." and "Remarks saved." are all visible together, each in its own panel.

### QA10-10 — Misleading cost and expense copy · Low

- **Role:** BDM, BDM Manager.
- **Page:** trip pages.
- **Actual:**
  - a draft with no expenses shows "Difference: ₹2,500.00 under the estimate";
  - "Expenses can be added once the trip is approved." also shows on a **cancelled** draft, where expenses never become possible, and on the **manager's** view.
- **Expected:** no difference until money is spent; the expense hint only for the owner of a trip that can still be approved.

### QA10-11 — "Mode of travel" select is taller than the other inputs · Low (visual)

- **Page:** `/bdm/travel/new` and the edit form, desktop and tablet.
- **Actual:** the select box is 84 px tall against 49 px for the inputs. It stretches to the grid row whose neighbour shows an error or hint.
- **Evidence:** `getBoundingClientRect().height` 83.75 vs 49.25. Screenshot `02-new-trip-required-errors.png`.

### QA10-12 — On phones the trip list hides Actual and Status without a cue · Low

- **Role:** BDM, manager.
- **Page:** `/bdm/travel` and the queues at 320–375 px.
- **Actual:**
  - the table scrolls sideways inside its own box (good: the page never scrolls);
  - the Actual and Status columns sit off-screen, with no visual hint that more columns exist;
  - the table has no header row styling or borders.
- **Evidence:** screenshot `14-mobile320-list.png`.

### QA10-13 — A super admin gets no explanation when they can't decide · Low

- **Role:** Super Admin.
- **Page:** `/bdm/manager/trips/{id}` while the BDM's manager is active.
- **Actual:** no Approve or Reject buttons and no text saying why (the reporting manager is active and decides).

### QA10-14 — "Remarks" heading repeats as the field label · Low

- **Page:** the BDM trip page.
- **Actual:** the section heading "Remarks" is followed immediately by a field label "Remarks".

### QA10-15 — The loading skeleton shows a generic role label · Low (cosmetic)

- **Page:** `/bdm/travel` and the trip page while loading.
- **Actual:** the sidebar briefly shows "BDM" before the real page shows "College BDM".

### QA10-16 — Two quick expense saves can leave the page showing stale data · Medium (intermittent)

- **Role:** BDM.
- **Page:** `/bdm/travel/{id}` (approved trip).
- **Steps:** add an expense, then immediately add a second one. Playwright saved them 0.6 s apart under a parallel load of 4 workers.
- **Expected:** after the second save, both lines are listed and Actual is ₹1,650.50.
- **Actual:** once in about 9 runs, the page kept showing only the first line and Actual ₹450.50 for more than 5 s.
- **Evidence:**
  - the database holds both lines (`TRV-000025`: food 450.50 at 04:31:24.959, stay 1200.00 at 04:31:25.585);
  - Playwright `toContainText("₹1,650.50")` read "Actual ₹450.50" 13 times;
  - screenshot `apps/web/test-results/qa/…-repeat1/test-failed-1.png`.
- **Likely cause:** each save calls `router.refresh()`, and with two refreshes overlapping, the older render can land last.
- **Reproduction:** not reproduced in 6 isolated repeats, so it depends on load.

### QA10-17 — Typing before the form hydrates can be lost · Low (observation)

- **Role:** BDM.
- **Page:** `/bdm/travel/new`.
- **Actual:** on a busy machine, Playwright filled "Travel date" immediately after navigation; React hydration then reset it to empty and the save failed with "Travel date is required". The fields filled after hydration kept their values.
- **Impact:** a fast user on a slow device could lose the first field they typed. The spec now waits for the page to settle before filling.

## Playwright (`bdm-010-travel.spec.ts`; `bdm-001-bdm-profile.spec.ts` as its neighbour)

- **bdm-001:** 7/7 pass.
- **bdm-010, first run:** 3/5 pass when run serially. Every failure was a defect in the spec itself. They were fixed in `9a005693`:
  - **Ambiguous locators:** `getByRole('region', { name: 'Expenses' })` and `getByLabel('Remarks')` also matched the "Costs and expenses" and "Remarks" sections. They now use `exact: true` and the textbox role.
  - **Navigation waits:** `waitForURL` waited for a `load` event that a client-side `router.push` never fires. It now waits for the URL to commit.
  - **Hydration race:** form fills now happen after the page settles (`networkidle`), with the date value asserted (see QA10-17).
  - **Colliding test users:** `Date.now()` stamps collided across parallel workers and `--repeat-each`, so stamps now get a random suffix.
  - **Timeout:** the 15 s per-test timeout was too short for two-portal flows; it is now 90 s, as the AGN specs use.
- **After the fix:** `bdm-010` + `bdm-001` with `--repeat-each=2` in parallel: **24/24 pass**. AC12 alone with `--repeat-each=6`: 6/6.
- **One product finding:** one parallel run found QA10-16.

## Checked and passing

- **Required-field validation:** all six fields marked `aria-invalid`, focus on the first, summary shown. Return-before-travel, amount format, negative, comma, over the cap, whitespace-only places, and travel date more than 30 days back are all caught on the client.
- **Create:** redirects to `TRV-000001`; `POST` 201; no console errors.
- **Submit, withdraw, start, complete, cancel:**
  - one request each;
  - focus moves to the result message;
  - only the allowed buttons show;
  - the edit form disappears once submitted;
  - cancel uses an inline confirm (focus on Confirm; Keep trip / Escape return focus to Cancel trip, with no request).
- **Expenses:**
  - zero and non-numeric amounts are blocked on the client;
  - add, edit and delete update the actual cost (₹450.50 → ₹1,650.50 → ₹1,700.00 → ₹500.00);
  - delete needs confirmation.
- **Remarks:** editable after completion; state survives a reload.
- **Manager:**
  - queue → trip → Reject with an empty reason shows "Reason is required";
  - Escape returns focus to Reject;
  - Approve sends one request, shows a message and moves focus;
  - "Approved by QA Manager One" appears.
- **Signed-out visits:** `/bdm/*` → `/bdm/sign-in?next=…`; `/bdm/manager/*` and `/admin/bdm-travel-approvals` → `/admin/login?next=…`.
- **Wrong person or role:**
  - BDM → another BDM's trip: "Trip not found";
  - BDM → manager or admin pages: "BDM manager role required" / "Super Administrator role required";
  - other-team manager → trip: "Trip not found";
  - manager → `/bdm/travel`: "BDM role required".
- **Super admin:**
  - "BDM Travel Approvals" in the nav;
  - empty while the manager is active;
  - lists the trip once the manager is deactivated;
  - Approve records "Approved by Global Super Admin";
  - admin navigation is kept on the trip page.
- **API down:** the list, the trip and the approvals queue all show "Travel is not available right now" with a Retry link back to the same page.
- **Slow network:** 2.5 s latency shows the skeleton (`aria-busy`) for the list and the trip page.
- **Layout:** desktop, 768, 375 and 320 px: `scrollWidth − clientWidth = 0` on the list, the trip, new trip, the queue and the manager's trip page.
- **Keyboard:** tab order on the new-trip form follows the visual order.
- **Broken images:** none.

## Notes on the harness (not product issues)

- Chrome pauses rendering in a hidden or occluded tab, and early clicks and fills silently missed. I restarted the isolated Chrome with background throttling disabled and the tab activated.
- The app sets `scroll-behavior: smooth`, so the harness scrolls with `behavior: 'instant'` before measuring.
- The harness's text entry drops `\n` in textareas. The missing line breaks in purpose and rejection reason come from the tool; multi-line input is covered by the backend tests.

## Fix pass (2026-10-03)

Owner decisions (added to `DEC-SCOPE-060` as T15 and T16):
- **QA10-01:** a Notifications nav item with an unread badge on every BDM and BDM-manager page, plus a list page for each role.
- **QA10-16:** the trip pages become one client workspace that applies each write's returned trip; a 409 re-reads the trip.

Every issue was fixed test-first: each test was seen failing, then passing.

| Issue | Fix | Commit |
|---|---|---|
| QA10-01 | `/bdm/notifications` and `/bdm/manager/notifications` (reusing `SchoolNotificationList`, mark-read on open). An unread badge through `lib/bdmNav.ts` on all BDM and manager pages. | `2f6dc23a` |
| QA10-02 | The expense list announces "Expense added." / "Expense updated." and takes focus. | `96579a90` |
| QA10-03 | Refusals in plain words ("is still a draft"); the reject form closes once the trip can't be decided. Also fixed: Start on an in-progress trip no longer blames the date. | `63e08010`, `bbce2b59` |
| QA10-04 | A non-UUID trip link is "Trip not found" without calling the API. | `96579a90` |
| QA10-05 | `.text-link` (blue, underlined) on the travel pages' in-text links. | `bbce2b59` |
| QA10-06 | A 5xx or dropped connection says the request did not complete; focus moves to the result; "Saving…" on the pressed action. | `96579a90`, `bbce2b59` |
| QA10-07 | The 31-day span is checked on the client, the return-date picker has a `max`, and the API's date sentences are mapped to their field. | `bbce2b59` |
| QA10-08 | Strict YYYY-MM-DD on the client and the API, with "Enter a valid travel/return/expense date". | `63e08010`, `bbce2b59` |
| QA10-09 | Starting a write clears every other panel's message. | `96579a90` |
| QA10-10 | No "Difference" before any expense; the expense hint only for the owner of a still-approvable trip. | `96579a90` |
| QA10-11 | The mode select keeps its height (`align-self: start`). | `bbce2b59` |
| QA10-12 | The Status column moved second, so it shows on a phone before the table scrolls. | `bbce2b59` |
| QA10-13 | A super admin gets a note explaining why they can't decide while the manager is active. | `96579a90` |
| QA10-14 | The remarks label is visually hidden under the "Remarks" heading. | `bbce2b59` |
| QA10-15 | Loading skeletons show "Loading…" instead of a guessed role. | `bbce2b59` |
| QA10-16 | `TripWorkspace` with `TripLiveContext`; no `router.refresh` on trip pages. | `96579a90` |
| QA10-17 | The trip form is server-rendered disabled until hydrated. | `bbce2b59` |

**Found during the re-test:** with a desktop scrollbar at 320 px, a long user name plus the new badge pushed the portal top bar 7 px past the edge. The shared `PortalShell` now truncates the name with an ellipsis (full name in a tooltip) (`fa31d4b8`).

**Re-verification on the rebuilt `bdm010qa` stack:**
- **Browser re-check:** QA10-01, -02, -03, -04, -05, -09 and -16 behave as fixed, and no page overflows at 320 px with long names and desktop scrollbars.
- **Playwright:** `bdm-010` + `bdm-001` with `--repeat-each=2` in parallel: **24/24**.
- **Backend lite set:** 199/199.
- **Web lite set:** 192/192 (BDM, travel, notifications, `PortalShell`, `PortalPage`, agent notifications). `tsc` and `eslint` are clean.
- **Not run:** the full backend and web suites (owner's standing choice).
