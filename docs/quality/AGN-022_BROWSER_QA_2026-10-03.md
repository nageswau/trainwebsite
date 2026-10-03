# AGN-022 — Exploratory browser QA (first pass, 2026-10-03)

**Build:** `feature/agn-022-agent-network` @ `b246c52` (stack built from this worktree). **Stack:** isolated compose project
`agn022qa` from `docker-compose.yml` only (no Caddy override) — web http://localhost:13022, API http://localhost:18022, migration head
`0067_audit_entity_index` (AGN-022 adds none), `python -m app.seed` applied. Local `.env` (gitignored) from `.env.example` with
`FRONTEND_URL`/ports changed and a throw-away `SECRET_KEY`.
**Browser:** Browser Use 0.13.10 (`uvx`) over CDP (port 9322) to an isolated headless Chrome 154 with a fresh throw-away profile.
Trusted input verified (`mousedown.isTrusted === true`). A page probe recorded console errors/warnings, page errors, unhandled
rejections and every `fetch` with status and duration; broken images and page/table overflow were measured per page.
**No product code was changed during this pass.**

**Harness notes (not product defects).** In the background tab `scrollIntoView`/`window.scrollTo` did not scroll and tall or
full-page screenshots timed out, so taller emulated viewports were used for clicks; one timed-out input event broke input delivery in
that tab, and fresh tabs were used afterwards.

**Data (through the running app's API only).** Seeded Master `agent@edusphere.local` (EDU, "EduSphere Partner Agency"): 2 extra staff,
12 active + 1 archived no-login students (one 90-character name), applications at enquiry / offer / enrolled (via AGN-013 confirm,
which created an estimated commission) / withdrawn; 22 pending agencies (paging); approved agencies "QA Empty", "QA Suspended"
(then suspended), a 90-character name, and `<b>Bold</b> & <img src=x onerror=alert(1)> Agency`. Network figures for EDU equal the
Master's own AGN-018 dashboard: students 12, applications 4, enrollments 1, claimable INR 2 / ₹15,000.

## Results by check

| # | Check | Result |
|---|---|---|
| 1 | Happy path | PASS — sidebar "Agent network" (`aria-current="page"`) → list (27 agencies, 20/page); search "EduSphere Partner" → 1 row → detail: tiles Staff 4 / Students 12 / Applications 4 / Enrollments 1, commission per currency, deposits, Masters; Students / Archived / Applications lists; one audit row per list read (`agent_network.students_read` ×2, `applications_read` ×1, correct metadata) and 3 `agent_network.read` log lines. |
| 2 | Invalid inputs | PASS — `?page=99` → "No agencies on this page. Go to the first page"; `?page=abc`, `?page=-3`, `?tab=bogus` → defaults; `?q=` 300 chars → capped at 100; `%`, `_` literal; `<script>` shown as text. Detail `/not-a-uuid`, `/..%2Fagents` → 404 with **no API call**; unknown UUID → "Organisation not found"; uppercase UUID works. See QA22-06. |
| 3 | Empty states | PASS — "No rejected agencies."; empty agency: all tiles 0, commission rows 0/—, deposits ₹0.00, "No students yet.", "No archived students." |
| 4 | Server errors | PASS — API stopped with the detail open: "Unable to load applications." + Retry; failed suspend "Unable to suspend this agency."; refresh warning "Unable to load this agency. The figures below may be out of date." + Retry; recovers after restart. Full page load during the outage → "Access unavailable — fetch failed" (pre-existing). |
| 5 | Loading states | PASS with **QA22-03** — 2.5 s latency: list keeps old rows dimmed (`aria-busy="true"`, opacity 0.6); detail "Loading agency…"; lists "Loading students…". |
| 6 | Cancel / back | PASS with QA22-05, QA22-08 — Cancel closes the confirmation, focus returns to Suspend, status unchanged; browser Back/Forward restore tab + page. |
| 7 | Refresh | PASS — refresh keeps `?page=2` (21–27 of 27); detail after suspend shows Suspended, notice cleared. |
| 8 | Duplicate submission | PASS — double-click "Confirm suspend" → exactly one `POST …/suspend` (200), "QA Empty Agency … suspended.", focus on Reinstate. Stale screen (another admin reinstated) → `409` "Cannot reinstate an organisation that is active" (QA22-11), summary refetched, focus on Suspend. |
| 9 | Unauthorized user | PASS — signed out → `/overseas/login?next=…` for list and detail; API 401; signing in returns to the agency page. |
| 10 | Incorrect role | PASS — agency Master, counselor, overseas student, university rep, IT admin → "Access unavailable" on both pages, API 403 on all four routes. Super Admin → reads both pages, no Suspend/Reinstate (QA22-07 copy). Suspended agency's Master → "Your agency's account is suspended"; an active Master's **next request after suspension** → 403 (AC4). |
| 11 | Desktop layout | PASS with QA22-09, QA22-10 — 1280: no overflow; table readable (`q-01-list-desktop.png`, `q-02-detail-desktop.png`). |
| 12 | Tablet layout | **FAIL — QA22-01** — 768: no page overflow, but the Agency column is crushed and the table scrolls 35 px (`q-08-list-768.png`). Detail OK. |
| 13 | Mobile layout | **FAIL — QA22-02** — 375 / 320: list stacks into labelled blocks (good, `q-08-list-375.png`); detail Commission table overflows 62 / 117 px and hides Amount (`q-10-commission-375.png`). |
| 14 | Navigation | PASS — sidebar entry after "Agent deposits", active state correct; row name links to detail; "← Agent network" back link (QA22-05); Agent Approvals and Agent deposits pages unchanged. |
| 15 | Success messages | PASS — "<name> suspended." in a live `role="status"` region; cleared on refresh. |
| 16 | Error messages | PASS with QA22-11 — server `detail` shown in `role="alert"`; outage messages specific per area. |
| 17 | Broken images | PASS — none on any page (markup-named agency renders no `<img>`). |
| 18 | Console errors | PASS — no console errors/warnings, page errors or unhandled rejections in the whole pass. |
| 19 | Failed network calls | PASS — only intended non-2xx: 409 (stale), 404 (unknown org), 401/403 (role checks), 500 (API stopped). |
| 20 | Unexpected redirects | PASS — none; login `next=` honoured. |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA22-01 | Medium | Overseas Admin | `/overseas/admin/agent-network` | Viewport 768×1024 (tablet); open the list | Agency names readable; all 7 columns visible (or rows stacked as on phones) | Agency column ≈60 px: names break mid-word ("Excepti/onally", "Registe/red"); table scrolls sideways 35 px, "Enrollments" header clipped. The `.table.stack` phone layout only starts below 640 px. | `.table-scroll` scrollWidth−clientWidth = 35; no console errors; `q-08-list-768.png` |
| QA22-02 | Medium | Overseas Admin / Super Admin | `/overseas/admin/agent-network/{id}` | Viewport 375 or 320; scroll to Commission | Figure, currency, count and amount all visible | Table 363 px in a 301 px box (375) / +117 px (320): Amount column cut ("AM", "₹15…"); the scroll box has no `tabIndex`/role/name, so keyboard users cannot scroll to it. | measured overflow 62 / 117 px; `tabIndex -1`, `role null`; `q-10-commission-375.png` |
| QA22-03 | Medium | Overseas Admin | list | Throttle network (2.5 s); on All, click "Suspended" | Heading and table agree while loading (or a loading indicator names the pending tab) | Heading immediately reads "Suspended agencies" over the previous tab's 20 Active/Pending rows (dimmed) for the whole wait; the table region is named by that heading, so screen readers announce the wrong set. | `aria-busy=true`, 20 old rows, heading "Suspended agencies"; `q-06-loading-tab.png` |
| QA22-04 | Low | Overseas Admin | detail | Open EDU; compare the Applications tile with the Applications list | Same number, or a note that the tile excludes withdrawn | Tile 4, list "Showing 1–5 of 5" (the withdrawn row is listed); per-student counts also exclude it. Not explained on screen. | tiles `Applications4`; list 5 rows incl. "Withdrawn" |
| QA22-05 | Low | Overseas Admin | detail → list | List: Active tab (or page 2 / a search) → open an agency → click "← Agent network" | Back to the same filtered list | Plain link to the unfiltered "All" list; browser Back keeps the filter. | URL `/overseas/admin/agent-network` (no `tab`) |
| QA22-06 | Low | Overseas Admin | `/overseas/admin/agent-network/not-a-uuid` | Open a malformed agency URL | Not-found inside the portal with a way back | Bare Next.js "404 · This page could not be found." page, no sidebar or link (no API call — AC11 holds). | title "404: This page could not be found." |
| QA22-07 | Low | Super Admin | list | Sign in as Super Admin; open Agent network | Intro copy matches the read-only role | Intro says "…or to suspend it." but Super Admin has no suspend action. | page text |
| QA22-08 | Low | Overseas Admin | detail | Press Suspend; press Escape | Escape cancels the inline confirmation (common expectation) | Confirmation stays open (Cancel works; focus starts on "Confirm suspend", so an accidental Enter confirms). | `[aria-label="Confirm suspension"]` still present after Escape |
| QA22-09 | Low | Overseas Admin | list | Desktop/tablet; look at the Masters column | Codes stay on one line | Codes wrap at the hyphen ("QAA-" / "M001", "QAP22-" / "M001"). | `q-01-list-desktop.png`, `q-06-loading-tab.png` |
| QA22-10 | Low | Overseas Admin | detail | Desktop: look above Suspend; phone: first screen | Even spacing; compact figures | Empty always-mounted status region adds an extra grid gap above Suspend; on phones the four tiles stack one per row and fill the first screen. | `q-02-detail-desktop.png`, `q-09-detail-apps-375.png` |
| QA22-11 | Low | Overseas Admin | detail | Make the screen stale (another admin acts), then act | Plain-language message ("This agency is already active.") | Raw server text "Cannot reinstate an organisation that is active" (refetch and focus are correct). | `POST …/reinstate` 409 |

**Pre-existing / out of scope (recorded, not AGN-022 defects):** every page keeps the generic site title
"EduSphere | Empowering Careers…"; a full page load while the API is down shows "Access unavailable — fetch failed" after ~5 s; the web
proxy answers 500 (not 502/503) when the API is unreachable.

No Critical or High issues. Acceptance criteria observed in the running app: counts match the Master's own figures (AC1/AC2),
empty agency all zeros (AC3), suspend blocks the Master's next request (AC4), non-admins 403 / signed-out 401 (AC5), audited reads
(AC6), no contact fields in drill-down rows (AC7), approvals page unchanged (AC8), UI states (AC9 — QA22-03), layout (AC10 — QA22-01,
QA22-02 fail), crafted id and markup (AC11).
