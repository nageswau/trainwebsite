# AGN-019 — Exploratory browser QA (first pass, 2026-10-03)

**Build:** `feature/agn-019-staff-funnel` @ `910fa4bc` (the stack was built from this worktree). **Stack:** isolated compose project
`agn019qa` (`docker-compose.yml` only; the override's Caddy was not started) — web http://localhost:13019, API http://localhost:18019,
migration head `0067_audit_entity_index` (AGN-019 adds none), `python -m app.seed` applied, worker and beat running. Local `.env`
(gitignored) from `.env.example` with `FRONTEND_URL`/ports changed and a throw-away `SECRET_KEY`.
**Browser:** Browser Use 0.13.10 (`uvx browser-use`, `BU_CDP_URL`) attached over CDP (port 9319) to an isolated headless Chrome 154
with a fresh throw-away profile. Trusted input was verified (`mousedown.isTrusted === true`). A page probe recorded console
errors/warnings, page errors, unhandled rejections and every `fetch` with its status; the document status, broken images and horizontal
overflow were read per page. Failures were injected with CDP `Fetch` (500, 401, 403, 502 HTML, an unexpected 200 body, connection
refused, a held request); the whole API was stopped once. **No product code was changed during this pass.**

**Harness notes (not product defects).** (1) As in AGN-018, input delivery can stall in a long-lived headless tab (after a timed-out
screenshot or many navigations): clicks and keys stop arriving (`isTrusted` never set). Every scenario and every login used a fresh
tab. (2) The app sets `scroll-behavior: smooth`; the headless tab did not animate it, so the harness scrolled instantly before clicking.
(3) Chrome's segmented date input ignores inserted text; dates were typed as real key events (day, month, year), as a user does.
(4) An aborted first seeding run left five staff (`EDU-S001…S005`) and two students; they appear as extra rows (zeros or a few counts).

**Data** (created through the running app's API only; no direct database writes), tag `160255`: seeded Master `agent@edusphere.local`
(`EDU-M001`, agency already holding seed students/applications); staff `QA Perf One/Two/Three 160255` (`EDU-S006/7/8`; One and Two
activated through the Overseas Admin welcome link), `QA Perf Archived Holder 160255` (`EDU-S009`, holds one archived student, then
deactivated) and a staff member named `<img src=x onerror=window.__xss=1> QA Perf XSS 160255` (`EDU-S010`). Students: enquiry only;
submitted + conditional offer + visa case moved to decision and approved; unconditional offer + enrolled (S006); submitted only; withdrawn
only (S007); no application, 66-character name (S008); unassigned with an offer; archived (S009). A second **empty** approved agency
and a **pending** (unapproved) agency. The API's numbers matched hand counts for the new batch (S006 table 3/3/2/1/1/1, funnel
3/3/2/2/2/1; S007 table 2/1/0/0/0/0, funnel 2/2/1/0/0/0).

## Results by check

| # | Check | Result |
|---|---|---|
| 1 | Happy path | PASS — Master: sidebar "Staff Performance" (after Reports) and the dashboard's "View staff performance" link both open the page (trusted click). One `GET …/crm/performance` → 200 (29–38 ms). h2 "Staff performance", h3 "Funnel" and "By staff member"; funnel 12 / 10 / 6 / 4 / 3 / 1 with "% of students"; table rows by code with a "Deactivated" tag on `EDU-S009`, "Unassigned", "All staff and unassigned"; UI numbers equal the API. |
| 2 | Invalid inputs | PASS with **QA19-01**, **QA19-02** — To before From (typed) → "'To' must be on or after 'From'." on To, `aria-invalid`, focus moved to To, no request. `?from=abc` is ignored. The staff name `<img onerror>` renders as text in the table and the select (`window.__xss` undefined, no `img` created). `?from=2026-13-01` → **stuck (QA19-01)**. A year with more than four digits (Chrome allows up to six) → 422 shown as "'From' must be a date (YYYY-MM-DD)" (QA19-02). `?from=2026-02-01&to=2026-01-01` → the ordering message lands on From (QA19-02). |
| 3 | Empty states | PASS — empty agency: "Your agency has no students yet.", no funnel, no table (it has no staff). A past range with no students: "No students were added in this period."; the table still lists active staff with zeros. |
| 4 | Server errors | PASS — 500, 502 HTML and an unexpected 200 body → "Couldn't load staff performance." (`role=alert`) + Try again, which recovers. Connection refused during an update → "Staff performance could not load. Check your connection and try again." + Try again, figures kept. API container stopped → after ~7 s "Access unavailable — fetch failed — Return to login" (pre-existing, same as AGN-018 #4 / QA17-08). |
| 5 | Loading states | PASS — held first load: "Loading staff performance…" (`role=status`), card `aria-busy="true"`. Held update: "Updating staff performance…" with the funnel and table kept on screen. See QA19-05 for the end of an update. |
| 6 | Cancel / back | PASS — no cancel control on this page. Dashboard → page → Apply → Back returns to the dashboard (the range is written with `replaceState`, as AGN-014); Forward restores `?from=2020-01-01` with its figures. |
| 7 | Refresh | PASS — reload with `?from=&to=` keeps the inputs and the same figures. |
| 8 | Duplicate submission | PASS — double-click Apply → one request. Apply is `aria-disabled` while loading. |
| 9 | Unauthorized user | PASS — signed out → `/overseas/login?next=%2Foverseas%2Fagent%2Fperformance`; API 401; signing in returns to the page. Pending agency → "Access unavailable — Agent registration is pending approval"; API 403. |
| 10 | Incorrect role | PASS with **QA19-06** — staff: no sidebar item, no dashboard link, the address shows "Staff performance is available to agency Masters." and no data request; a direct API call → 403. Counselor and Overseas Admin → "Access unavailable — Role/division mismatch"; API 403. Super Admin → Masters-only note; API 403 (sidebar shows the item: QA19-06). |
| 11 | Desktop layout | PASS with **QA19-04** — 1280×900: no overflow; filter row, as-of line, funnel bars, table fit (`01-master-desktop-top.png`, `05-desktop.png`). |
| 12 | Tablet layout | **FAIL — QA19-03** — 768×1024: no page overflow, but the 7-column table is 845 px inside a 647 px region; Visa approvals and Enrollments are off-screen behind a horizontal scrollbar (`05-tablet-table.png`). |
| 13 | Mobile layout | PASS — 375×812 and 320×640: no page overflow; date inputs and select full width (301 / 246 px), Apply 82×49; the table stacks into labelled rows (`td::before` = column name); funnel rows fit (`05-mobile-320*.png`). |
| 14 | Navigation | PASS — sidebar item with `aria-current="page"`; dashboard link; mobile menu ("Open menu") lists Staff Performance and closes on navigation. Keyboard: From (day/month/year) → To → Apply → funnel select → table region (focusable), each with a visible focus outline. |
| 15 | Success messages | PASS (no success message by design: a read-only page). After Apply the as-of line changes to "Students added in this period. Figures as of …" — see QA19-05 / QA19-07. |
| 16 | Error messages | PASS with QA19-01/02 — every error is a fixed string in `role=alert`; 401 offers "Sign in again" (`next` = this page); 403 shows the server's message with no retry. |
| 17 | Broken images | PASS — none on any page visited. |
| 18 | Console errors | PASS — no console errors, page errors or unhandled rejections on any AGN-019 page (injected failures included). |
| 19 | Failed network calls | PASS — only the injected ones (500/401/403/502/refused) and the expected 422s from QA19-01/02; every RSC prefetch 200. |
| 20 | Unexpected redirects | PASS — none; the only redirect is signed-out → login with `next`, which returns to the page. |

## Issues

### QA19-01 — A bad date in the address leaves the page stuck on an error the user cannot clear (Medium)
- **Role / page:** Agency Master — `/overseas/agent/performance`.
- **Steps:** open `/overseas/agent/performance?from=2026-13-01` (a stale or hand-edited link); then press Apply.
- **Expected:** the impossible date is ignored (or shown so it can be corrected); Apply with a blank From loads all time.
- **Actual:** From looks blank (a date input cannot display `2026-13-01`) but the panel's draft still holds it; the page shows only
  "'From' must be a date (YYYY-MM-DD)" with no figures. Apply re-sends the same value → 422 again. Clearing the visibly blank field fires no
  change, so the user is stuck unless they type a date into From or edit the address.
- **Evidence:** `GET …/crm/performance?date_from=2026-13-01` → 422 twice (initial load and after Apply), no console errors;
  screenshot `05-bad-url-stuck.png`. Cause (read, not changed): `readRange` accepts any `\d{4}-\d{2}-\d{2}` shape, so an impossible
  calendar date reaches the draft; the same helper serves AGN-014's commission report.

### QA19-02 — Date error messages use a format the user never sees, and the ordering message lands on From (Low)
- **Role / page:** Agency Master — `/overseas/agent/performance`.
- **Steps:** (a) type a five- or six-digit year into From (Chrome's date field accepts up to 275760) and Apply; (b) open
  `?from=2026-02-01&to=2026-01-01`.
- **Expected:** a message in the user's terms (e.g. "Enter a valid From date"); the To-before-From message on To (as the client check does).
- **Actual:** (a) "'From' must be a date (YYYY-MM-DD)" while the field shows dd-mm-yyyy; (b) "'To' must be on or after 'From'" shown
  under the form with From marked `aria-invalid` and focused.
- **Evidence:** `…?date_from=61003-02-20…` → 422; `…?date_from=2026-02-01&date_to=2026-01-01` → 422; field error id
  `staff-performance-from`. (b) is the final review's deferred minor #4 (same in AGN-014's panel).

### QA19-03 — Tablet: the staff table hides two columns behind a horizontal scroll (Low–Medium)
- **Role / page:** Agency Master — `/overseas/agent/performance` at 768×1024.
- **Steps:** open the page on a tablet-width screen; scroll to "By staff member".
- **Expected:** all seven columns readable without horizontal scrolling (e.g. stacked rows, as on phones, until a width where the table fits).
- **Actual:** the table is 845 px in a 647 px region; "Visa approvals" and "Enrollments" are off-screen; a horizontal scrollbar is the
  only cue. The region is keyboard-scrollable (no WCAG failure), and the page itself does not overflow.
- **Evidence:** region `scrollWidth 845 / clientWidth 647`; rows `display: table-row` at 768 (stacking starts below 640);
  screenshot `05-tablet-table.png`.

### QA19-04 — Desktop: the "Show funnel for" select spans the full card width (Low, cosmetic)
- **Role / page:** Agency Master — desktop 1280.
- **Expected:** a control sized to its content (like the date inputs, 160 px).
- **Actual:** 889 px wide select for short labels; it reads as a banner rather than a control (`01-master-desktop-top.png`).

### QA19-05 — The end of an update is not announced to screen-reader users (Low, accessibility)
- **Role / page:** Agency Master — any Apply.
- **Steps:** with a screen reader, change the range and press Apply.
- **Expected:** after "Updating staff performance…", an announcement that the figures changed (or the empty result).
- **Actual:** the `role=status` element exists only while loading and is removed; the new as-of line and "No students were added in this
  period." are plain paragraphs, so nothing is announced when the update completes (focus stays on Apply).
- **Evidence:** DOM after an update: no live region holds the result. Same pattern as AGN-014's report panel.

### QA19-06 — Super Admin sees "Staff Performance" in the agency sidebar, which only leads to a Masters-only note (Low)
- **Role / page:** Super Admin — agency portal view `/overseas/agent/*`.
- **Expected:** no link to a page the role can never use (or the AGN-016 Tasks precedent, if intended).
- **Actual:** the item is listed; the page shows "Staff performance is available to agency Masters."; API 403. `agentNavFor` hides it
  for staff only. Same behaviour as the Tasks page for a Super Admin (QA16-01), so this may be acceptable — owner's call.

### QA19-07 — After an update fails, the old figures stay under the new dates without saying so (Low)
- **Role / page:** Agency Master.
- **Steps:** load all time; type From = 2026-10-01; Apply while the connection fails.
- **Expected:** a clear cue that the figures still belong to the previous range.
- **Actual:** the offline alert appears, the inputs show 2026-10-01, the address keeps the old range, and the figures/as-of line still
  describe "Students added at any time" — the as-of line never restates the applied dates, so the mismatch is easy to miss. (The final
  review set this aside as the AGN-014 pattern; recorded here for the owner.)

## Not AGN-019 (pre-existing)
- API unavailable → ~7 s, then "Access unavailable — fetch failed" (raw `fetch failed` text) — AGN-018 #4 / QA17-08.
- Native date inputs expose their picker buttons as "Show date picker" twice in the accessibility tree (Chrome).

## Screenshots
Session scratchpad `qa/shots/` (not committed, as earlier passes): `01-master-desktop-top.png`, `02-to-before-from.png`, `03-loading.png`,
`03-500.png`, `04-staff.png`, `04-empty-agency.png`, `05-desktop*.png`, `05-tablet*.png`, `05-mobile-375*.png`, `05-mobile-320*.png`,
`05-bad-url-stuck.png`, `08-api-down.png`.
