# AGN-018 — Exploratory browser QA (first pass, 2026-10-03)

**Build:** `feature/agn-018-master-dashboard-impl` @ `df1d702` (the stack was built from this worktree). **Stack:** isolated compose
project `agn018qa` — web http://localhost:13018, API http://localhost:18018, migration head `0065_agent_notifications` (AGN-018 adds
none), `python -m app.seed` applied, worker and beat running; the override's Caddy service was stopped (not needed). Local `.env`
(gitignored) from `.env.example` with `FRONTEND_URL`/ports changed and a throw-away `SECRET_KEY`.
**Browser:** Browser Use 0.13.10 (`uvx`), attached over CDP (port 9318) to an isolated headless Chrome 154 with a fresh throw-away
profile. Trusted input was verified (`mousedown.isTrusted === true`). A page probe recorded console errors/warnings, page errors,
unhandled rejections, failed resources and every `fetch` with its status; the document status and broken images were read per page.
**No product code was changed during this pass.**

**Harness notes (not product defects).** (1) The daemon attaches tabs in the background, where Chrome pauses `requestAnimationFrame`;
React 19.2 reveals streamed Suspense content on a frame, so in a *hidden* tab the board stayed behind its skeleton until the tab became
visible. With the page lifecycle set to `active` the board replaces the skeleton immediately (0.0–0.02 s after load). A real foreground
tab is not affected. (2) `activate_tab` and timed-out screenshots broke input delivery in that tab; fresh tabs were used instead.

**Data.** Created through the running app's API only: seeded Master `agent@edusphere.local` (`EDU-M001`); staff `QA Staff One/Two/Three`
(`EDU-S004/5/6`, activated through the Overseas Admin welcome link; an aborted first seeding run also left `EDU-S001/2/3` with a few
students); no-login students assigned to each staff member, one unassigned, one archived, one with a 66-character name; applications at
enquiry, offer (conditional), offer + visa case, enrolled, withdrawn-after-offer, unassigned and archived; two pending documents; two open
tasks; a second **empty** approved agency; a **pending** (unapproved) agency. Hand counts were cross-checked against each list endpoint's
`total` for the Master and Staff One (all equal).

## Results by check

| # | Check | Result |
|---|---|---|
| 1 | Happy path | PASS — Master: "Whole agency · Your code EDU-M001", groups Students / Pipeline / Documents / Commission, both breakdowns, Staff performance, "View reports"; every number equals its list total (students 12, applications 8, enrolled 1, pending documents 3, open tasks 2) and the hand count (offers 4 incl. withdrawn-after-offer, visa 2, approvals 0; claimable INR 15,000). Staff One: "Your assigned students · Your code EDU-S004", own numbers only (3 / 4 / 2 offers / 1 visa / 1 pending document / 1 task — all equal to their list totals), no Commission group, no staff table, no reports link, no "commission" anywhere on the page. |
| 2 | Invalid inputs | PASS — the board takes no input. `?scope=agency&role=master` from a Staff session → 200, `scope: "own"`, `Cache-Control: private, no-store`; `?x=<script>` ignored; `students?new=2` / `new=` do not open the form; `new=1&new=1` opens it once and strips the parameter. |
| 3 | Empty states | PASS with QA18-05 — empty agency: zeros in every tile (never blank), "INR 0", "No applications yet" in both breakdowns, "No staff yet — add staff from Team". |
| 4 | Server errors | PASS (pre-existing behaviour) — API stopped: the page answers after ~5–6 s with "Access unavailable — fetch failed — Return to login" (same as QA17-08). A failure of the dashboard endpoint alone cannot be produced black-box (the board's read is server-side); its inline alert is covered by component tests. |
| 5 | Loading states | PASS — the streamed HTML carries the skeleton (`aria-busy="true"`, "Loading dashboard figures") ahead of the board content in a hidden holder; title and table render at once; locally the board replaced it immediately. A slow board read cannot be produced black-box. |
| 6 | Cancel / back | **FAIL — QA18-01.** Add → form opens with focus in Full name, `new=1` stripped; Cancel → focus back on "Add student"; **Add again → URL `?new=1`, no form.** Back/Forward after a successful Add do not reopen the form. |
| 7 | Refresh | PASS — refresh after Add does not reopen the form; dashboard refresh re-renders the board with the same numbers. |
| 8 | Duplicate submission | PASS — double-click "Save student" in the form opened from the sidebar: one `201`, "QA Double Click … added.", students 3 → 4 and the dashboard shows 4 on next visit. |
| 9 | Unauthorized user | PASS — signed out → `/overseas/login?next=%2Foverseas%2Fagent%2Fdashboard` (and `…students%3Fnew%3D1`); API 401. Deactivated staff's open session → "Your account was deactivated by your agency…", API 401; the deactivated member drops out of the Master's table (no active students). Pending agency → "Agent registration is pending approval", API 403. |
| 10 | Incorrect role | PASS — counselor, overseas student, Overseas Admin → "Access unavailable — Role/division mismatch", API 403. Staff on Team / Commissions → "Only an agency Master can open this page"; Reports (not permitted) → "Your agency Master hasn't given you access to reports". Super Admin → API 403 and no board; the page shows the Super Admin's own "Administration Dashboard" payload (pre-existing portal behaviour, unchanged by AGN-018). |
| 11 | Desktop layout | PASS with QA18-03 — 1280×900: groups read top-down, 4-column tile grid, no overflow (screenshot `t-desktop.png`). |
| 12 | Tablet layout | PASS with QA18-04 — 768: 2-column grid, no page overflow; the 2-column breakdown tables still scroll by a few pixels (643 / 650). |
| 13 | Mobile layout | **FAIL — QA18-04** (and QA18-02) — 375 / 320: single column, no page overflow, but the breakdown tables hide the count column off-screen (`05-master-375-tables.png`). |
| 14 | Navigation | PASS with QA18-02, QA18-07 — tile links land on Students (current "All"), Applications, `?status=enrolled` (current "Enrolled"), Documents `?view=pending` (current "Pending"), Tasks `?view=open`; Staff sidebar: Dashboard, My Students (All, Add), Universities, Applications (All applications + filters), Documents (Pending/Uploaded/Additional), Tasks & Follow-ups, Notifications with badge. Keyboard: Tab order View students → Open tasks → View applications → View enrolled → Review pending → the three table regions → View reports, each with a visible focus style. |
| 15 | Success messages | PASS — "{name} added." after saving from the sidebar's Add. The board itself has no forms. |
| 16 | Error messages | See 4, 9, 10 — every refusal shows a specific message; no error detail leaks. |
| 17 | Broken images | PASS — none on any page visited. |
| 18 | Console errors | PASS — none (production build: React key warnings are not printed — see QA18-02). |
| 19 | Failed network calls | PASS — none outside the injected API outage (all `fetch`es 200/201; the page's own document 200). |
| 20 | Unexpected redirects | PASS — only the expected sign-in redirects with `next=`, and the "Access unavailable" cards. |

## Issues

### QA18-01 — Sidebar "Add" does nothing the second time (High)
- **Role / page:** Agency Staff · sidebar My Students → Add (`/overseas/agent/students?new=1`).
- **Steps:** 1. Sign in as Staff One. 2. Sidebar → Add (from the dashboard or from My Students) — the form opens. 3. Cancel (or save a
  student). 4. Sidebar → Add again.
- **Expected:** the add form opens again with focus in Full name, and `new=1` leaves the URL.
- **Actual:** the URL becomes `/overseas/agent/students?new=1`; no form; focus stays on the link. Only a full page load (or a navigation
  away and back) makes Add work again. A refresh at that point does open the form (the `new=1` is still in the URL).
- **Evidence:** probe after step 4: `url /overseas/agent/students?new=1 | form False | focus A`; console and network clean (the click
  is a client navigation; no request fails).
- **Note (no fix attempted):** this is the final-review finding the branch tried to fix in `61a6dae`. The panel strips `new` with
  `window.history.replaceState(window.history.state, …)`; passing Next's own history state appears to stop the App Router from syncing
  `useSearchParams`, so `wantsNew` stays `true` and the next push to `?new=1` changes nothing. The vitest test mocks `useSearchParams`, so
  it cannot catch this.

### QA18-02 — Mobile menu marks two items as the current page (Medium, accessibility)
- **Role / page:** Agency Staff · mobile menu (≤ 980 px) on My Students (`/overseas/agent/students`).
- **Steps:** 1. Staff, viewport 375. 2. Open My Students. 3. Open the menu.
- **Expected:** one link with `aria-current="page"`.
- **Actual:** `["My Students", "My Students: All"]` both carry `aria-current="page"` (screen readers announce two current pages). The
  same flat list holds the href `/overseas/agent/students` twice, which React keys by href (no console warning in the production
  build).
- **Note:** `PortalShell` flattens children into `{label: "Parent: Child"}` items before `MobileNavToggle`; the review fix in `61a6dae`
  handled a nested-children shape the app never passes (its unit test renders `MobileNavToggle` directly).

### QA18-03 — Tile links are not visually links (Low–Medium, accessibility)
- **Role / page:** Master and Staff · dashboard tiles ("View students", "Open tasks", "View applications", "View enrolled", "Review
  pending").
- **Expected:** links distinguishable from text (colour + underline or another non-colour cue, WCAG 1.4.1).
- **Actual:** computed `color: rgb(11, 31, 58)` (body text colour), `text-decoration-line: none` — they read as plain text under the
  number (`t-desktop.png`).

### QA18-04 — Breakdown tables hide their counts on phones (Medium, mobile layout)
- **Role / page:** Master and Staff · "Applications by country / by university" (and Staff performance) at 375 / 320 px; slight at 768.
- **Expected:** a 2-column table fits a phone; the number is visible next to each name.
- **Actual:** the shared `.table` `min-width: 650px` forces a horizontal scroll region (242 px wide at 320, 643 at 375); only the
  names are visible, the "Applications" column is off-screen (`05-master-375-tables.png`). The page itself does not overflow.

### QA18-05 — Empty staff section shows a message and an empty table (Low)
- **Role / page:** Master of an agency with no staff · Staff performance.
- **Actual:** "No staff yet — add staff from Team" followed by the table header and an "Unassigned 0" row.
- **Expected:** the message alone (or the table alone), not both.

### QA18-06 — Each table is named three times for screen readers (Low, accessibility)
- **Role / page:** both · breakdown and staff tables.
- **Actual:** visible `h3` "Applications by country", then the scroll region `aria-label` and the visually-hidden `<caption>` with the
  same text — announced repeatedly.

### QA18-07 — Current-link marking for the "All" children (Low, navigation)
- **Role / page:** Staff sidebar.
- **Actual:** on `/overseas/agent/applications` (bare, e.g. from "View applications") the parent "Applications" is current, not "All
  applications"; on `?new=1` the "All" child, not "Add", is current. (Recorded as a deferred minor in the final review.)

## Not reproducible black-box (covered by component tests)
- Dashboard endpoint failing while the rest of the page works (inline alert + "Try again").
- A slow board read (skeleton visible for a measurable time).

## Evidence files (session scratchpad, not committed)
`qa/shots/t-desktop.png`, `qa/shots/05-master-375-tables.png`; probe outputs above; data script `qa/seed_qa.py`, cross-check `qa/totals.py`.
