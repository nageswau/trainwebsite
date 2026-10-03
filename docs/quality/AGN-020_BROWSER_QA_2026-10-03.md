# AGN-020 — Exploratory browser QA (first pass, 2026-10-03)

**Build:** `feature/agn-020-reports` @ `ba6cea9` (the stack was built from this worktree). **Stack:** isolated compose project `agn020qa`
(`docker compose -p agn020qa -f docker-compose.yml`, Caddy override not used) — web http://localhost:13020, API http://localhost:18020,
migration head `0067_audit_entity_index` (AGN-020 adds none), `python -m app.seed` applied, worker and beat running. Local `.env`
(gitignored) from `.env.example` with `FRONTEND_URL`/ports changed and a throw-away `SECRET_KEY`.
**Browser:** Browser Use 0.13.10 (`uvx`), named daemon `agn020qa` attached over CDP (port 9320) to an isolated headless Chrome 154 with a
fresh throw-away profile. Trusted input verified (`mousedown.isTrusted === true`). A page probe recorded console errors/warnings, page
errors, unhandled rejections, failed resources and every client `fetch` with status and time; broken images were read per page.
**No product code was changed during this pass.**

**Harness notes (not product defects).** (1) `html { scroll-behavior: smooth }` makes `scrollIntoView` animate, so coordinates read
straight after it miss their target; early "clicks that did nothing" were this (fixed in the harness with `behavior: 'instant'`).
(2) Screenshots of a background tab time out; the tab was activated only for the final screenshot block. (3) "View reports" on the
dashboard sits in AGN-018's streamed board; it navigated correctly once clicked with instant scrolling.

**Data.** Created through the running app's API only. Seeded Master `agent@edusphere.local` (`EDU-M001`); staff `QA Reports One`
(`EDU-S013`, Reports on), `QA Reports Two` (`EDU-S014`, Reports on), `QA Reports Off` (`EDU-S015`, Reports off), activated through
the Overseas Admin welcome link (aborted first data runs also left `EDU-S001…S012` and a few students/applications — they appear in
every report consistently). Students: `Zoë Ünïcode QA` (S013, preferred Canada / Sep 2027), `=cmd|' /C calc'!A0 QA` (S013), a
66-character name (S014), one unassigned, one archived, 55 bulk students for paging. Applications at enquiry; offer (conditional,
submitted); offer + visa case taken to an approved decision; enrolled (2027-09-15, `UNI-QA-4`); withdrawn after an unconditional offer;
withdrawn without offer; unassigned enquiry; intakes "Sep 2027", "September 2027", "09/2027", "2027-09", "Jan 2028", "Next intake".
A second **empty** approved agency (`qa020-empty-…`).

## Results by check

| # | Check | Result |
|---|---|---|
| 1 | Happy path | PASS — Master: 8 tabs (Students … Commission); every report loads with its columns; summaries end with a Total row and have no pager; lists show "N rows · As of hh:mm", the pager and Download CSV. Totals agree across reports (applications 11, submitted 5, offers 4, visa 2 / approved 1, enrolled 1). Intakes fold the four spellings into "Sep 2027"; "Next intake" is Unstructured. Staff member filter (S013) narrows to 4 applications. CSV: "Report downloaded.", file `agency-students-all-to-all.csv`, UTF-8 BOM (`ef bb bf`), header row = screen labels, `'=cmd…` escaped, `Zoë Ünïcode` intact; one `agent_report.export` audit row per export (`{"scope": "agency", "filters": {}, "rows": 18}`, no names). |
| 2 | Invalid inputs | PASS with **QA20-02**, **QA20-03** — To before From: inline "'To' must be on or after 'From'", focus to To, no request. Tampered address: unknown member / status / intake, impossible date, 130-character member → 422 shown at the field with focus; `university` on Countries and an out-of-range `offset` are dropped from the address; `offset=500` lands on the last page; `<script>` as a country renders as text and matches nothing. |
| 3 | Empty states | PASS with **QA20-04**, **QA20-05** — empty agency: "No students yet.", "No applications yet." (Applications, Universities, Countries, Intakes), "No enrollments yet.", Commission "Your agency has no commissions yet."; filters matching nothing: "No records match these filters." + Clear filters. |
| 4 | Server errors | PASS — API stopped, tab switch: proxy 500 after ~4–5 s → "Couldn't load this report." + Try again; no CSV button; API restarted → Try again loads the report. Full reload while the API is down → the existing "Access unavailable — fetch failed" card (pre-existing portal behaviour, as QA17-08 / AGN-018). |
| 5 | Loading states | PASS — 2.5 s latency: tab switch shows 5 skeleton rows + "Loading report…" (`aria-busy`), Apply `aria-disabled`; refetch keeps the table, region `aria-busy="true"`, class `report-busy` (opacity 0.55). |
| 6 | Cancel / back | PASS (by design) — tabs and filters replace the history entry, so Back leaves Reports for the previous page (dashboard) and Forward returns to the last tab. Clear filters resets dates and filters. |
| 7 | Refresh | PASS — refresh keeps report, filters (form shows `EDU-S014`), caption and page (`offset=50` → "Showing 51–73 of 73"). |
| 8 | Duplicate submission | PASS — Apply clicked 3× during a 2.5 s request → one request; Download CSV clicked twice → one request (button "Preparing CSV…", `aria-disabled`). |
| 9 | Unauthorized user | PASS — signed out → `/overseas/login?next=%2Foverseas%2Fagent%2Freports%3Freport%3Dstaff`; API 401. |
| 10 | Incorrect role | PASS — Staff with Reports: 6 tabs, own 2 students, filters From/To/Country/Status (no Staff member); typed `?report=staff` / `?report=commission` / `member=` fall back or are ignored; API `staff` → 403 "Only an agency Master can view staff performance", `member` → 422, commission CSV → 403. Toggle switched off mid-session → next tab: "Your agency Master hasn't given you access to reports", table and CSV gone; reload → refusal card; nav link gone. Staff without Reports: no nav link, refusal card, API 403. Counselor, Overseas Admin → "Role/division mismatch", API 403. Super Admin → no tabs, API 403 (the page shows its own "IT Reports" payload — pre-existing portal behaviour). |
| 11 | Desktop layout | PASS with **QA20-06** — 1440 / 1280 / 1024: no page overflow; tab strip fits; Applications table wider than the card. |
| 12 | Tablet layout | PASS with **QA20-06** — 768: no page overflow; tab strip scrolls sideways (873 / 722); filters wrap to two rows; tables scroll inside their region. |
| 13 | Mobile layout | **FAIL — QA20-01** — 375 / 320: no page overflow, tables stack into labelled blocks, touch targets ≥ 44 px; but the Applications blocks (and very long unbroken names) clip values at the right edge. Applications filter form is 600–670 px tall on a phone (observation O-2). |
| 14 | Navigation | PASS — sidebar Reports and dashboard "View reports" → `?report=students`, nav item `aria-current`; arrow keys / Home / End move and open tabs (wrap-around); Tab leaves the tab strip into the form; after Next/Previous focus moves to the table region. |
| 15 | Success messages | PASS — "Report downloaded." after a CSV. |
| 16 | Error messages | PASS with **QA20-02** — throttle after 30 exports: "You've downloaded a lot of reports in a short time. Try again in a few minutes." (429, `Retry-After: 597`); refusal and outage messages as above. |
| 17 | Broken images | PASS — none on any page visited. |
| 18 | Console errors | PASS — no console errors or warnings, page errors or unhandled rejections in any run. |
| 19 | Failed network calls | PASS — only the intended ones (422 on tampered input, 403 on refusals, 500 while the API was stopped, 429 on the throttle). |
| 20 | Unexpected redirects | PASS — none; only the sign-in redirect for a signed-out visit. |

## Issues

### QA20-01 — Medium — Mobile: the Applications report's stacked rows cut values off
- **Role / page:** Master (and Staff with Reports) · `/overseas/agent/reports?report=applications` at 375 px and 320 px (also any list with a long unbroken name).
- **Steps:** set a phone viewport (375×812) → open Reports → Applications.
- **Expected:** each application is a block of "label — value" lines that fit the screen (as the 8-column Staff performance table does).
- **Actual:** values are cut at the right edge — "Ire", "Sep", "Withd", "Technical University of Mu", "Gern", "2026-1"; reading them needs a sideways swipe inside the table region.
- **Evidence:** region `scrollWidth/clientWidth` 369/329 (375 px) and 369/274 (320 px); the elements past the edge are the visually-hidden column headers (`th` Course, Intake, Application ref, Stage, Submitted, Offer), whose widths still set the table width; Staff performance (fewer columns) measures 329/329. No console errors. Screenshot `shots/04-mobile-375-applications.png`.

### QA20-02 — Low — Server field errors use API parameter names
- **Role / page:** Master · Reports with a tampered address (`?report=students&from=2026-02-30`, `member=<130 chars>`).
- **Expected:** wording that names the control ("'From' must be a real date", "Staff member is too long").
- **Actual:** "Date_from must be a date (YYYY-MM-DD)" and "Too long" (the server's text, capitalised).
- **Evidence:** `422 {"detail":[{"loc":["query","date_from"],"msg":"date_from must be a date (YYYY-MM-DD)"…}]}`.

### QA20-03 — Low — A refused filter from the address shows a different value in its control
- **Role / page:** Master · `?report=students&member=EDU-S999` (also `status=bogus`, `intake=2027-13`).
- **Expected:** the control shows what was refused, or the refused value is dropped with a note.
- **Actual:** the alert says "Unknown staff member" while the select (outlined invalid) reads "All staff"; no table is shown. Apply with "All staff" recovers.
- **Evidence:** 422 on `…/students?member=EDU-S999`; screenshot `shots/06-error-member.png`.

### QA20-04 — Low — Staff performance has no empty state for an agency without staff
- **Role / page:** Master of an empty agency · `?report=staff`.
- **Expected:** an empty state (as the dashboard's "No staff yet — add staff from Team").
- **Actual:** a table with one "Unassigned 0 0 0 0 0 0 0" row, a Total row and a Download CSV button.
- **Evidence:** `200 …/reports/staff` with `items: [Unassigned]`, `total: 1`.

### QA20-05 — Low — Two "Clear filters" buttons when filters match nothing
- **Role / page:** Master · `?report=students&country=Nowhere`.
- **Expected:** one Clear filters control.
- **Actual:** one in the filter form and one in the "No records match these filters." message (same name twice for screen readers).

### QA20-06 — Low — Wide reports need sideways scrolling on desktop and tablet; dates wrap
- **Role / page:** Master · Applications at 1024–1440 px; Students at 1280 px; tablet 768 px.
- **Expected:** the main columns fit a desktop card, or the table signals it scrolls.
- **Actual:** Applications (11 columns) measures 1329 px in a 1109 / 949 / 693 px region — Stage, Submitted, Offer, Visa, Created are off-screen with no visible cue (overlay scrollbar); the Created date breaks as "2026-10-" / "03".
- **Evidence:** region `scrollWidth/clientWidth` 1329/1109 (1440), 1329/949 (1280), 966/949 (Students, 1280); screenshot `shots/02-desktop-1280-applications.png`.

## Fix pass (2026-10-03, `d46e1189`) and re-check

Each fix was made test-first (a failing test, then the change), the stack was rebuilt at `d46e1189`, and every issue was re-checked
in the browser with the same probe:

| Issue | Fix | Unit test (RED → GREEN) | Browser re-check |
|---|---|---|---|
| QA20-01 | the stacked table's visually-hidden header row is a block (a row group ignores `overflow`), long values may wrap | CSS — not measurable in jsdom | region 329/329 (375 px), 274/274 (320 px), was 369; every value visible (`shots/07-mobile-375-applications-fixed.png`) — PASS |
| QA20-02 | the panel names the form's fields in date errors; the server's length error names the field and the limit | `AgentReportsPanel` "names the form's fields…"; `test_bad_filters_name_their_param` | "'From' must be a date (YYYY-MM-DD)"; "Member is too long (at most 120 characters)" — PASS |
| QA20-03 | a refused value from the address is kept as an option of its control | `AgentReportFilters` "shows a refused value…" | select shows `EDU-S999` beside "Unknown staff member" — PASS |
| QA20-04 | no rows when an agency has no staff and nothing unassigned; empty state "No staff yet — add staff from Team." | `test_staff_performance_of_an_agency_with_no_staff_is_empty`; panel test | empty agency: the message, no table, no CSV — PASS |
| QA20-05 | the empty-state message no longer repeats Clear filters | panel "offers one Clear filters…" | one Clear filters — PASS |
| QA20-06 | ISO dates do not wrap (`nowrap`); "Scroll sideways to see every column." on reports wider than 8 columns (hidden at ≥ 1600 px and on phones) | `AgentReportTable` "keeps a date on one line", "tells the reader…" | Created `white-space: nowrap`; hint shown at 1280, hidden at 375/320 — PASS |
| Z1 (verification) | the "As of" time uses `LocalTime` (the date-zone rule) instead of `toLocaleTimeString` | `dateZoneSweep` no longer lists `AgentReportsPanel`; panel "shows the report time with its zone" | "As of 03 Oct 2026, 17:11" in a `<time>` element — PASS |

## Observations (not AGN-020 defects)
- **O-1** Every agency page starts at `<h2>` (Universities, Dashboard, Applications, Reports) — no `<h1>`; pre-existing pattern.
- **O-2** On phones the Applications filter form is 600–670 px tall before any result (seven controls, one per row).
- **O-3** Back after switching tabs leaves Reports (tabs replace the history entry by design, spec §6.2).
- **O-4** Pre-existing: full reload with the API down → "Access unavailable — fetch failed"; Super Admin on `/overseas/agent/reports` sees its own IT Reports payload.

Screenshots are in the session scratchpad `shots/` (01 desktop Students, 02 desktop Applications, 03 tablet, 04 mobile 375 Applications,
05 mobile 320 Students, 06 refused-filter state).
