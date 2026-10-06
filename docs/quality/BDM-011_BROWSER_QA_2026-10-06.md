# bdm-011 — Exploratory browser QA (2026-10-06)

Feature: trip ↔ appointment linking, itinerary, productivity, travel report (`DEC-SCOPE-083`, migration `0083_bdm_appointment_trip`).

## Setup

- Stack: compose project `bdm011qa` built from the `worktree-bdm-011` branch (merged with `main` @ `3986958c`), web
  `http://localhost:13011`, api `127.0.0.1:18011`, demo seed (`python -m app.seed`).
- Browser: isolated Playwright Chromium (fresh contexts per role). Browser Use is **not installed** on this machine (as recorded by
  bdm-004…bdm-008); the scripted Playwright pass stands in for it.
- People (throwaway, through the admin API): `QA Meera` (bdm_manager M1), `QA Other Manager` (M2, no team), `QA Iqbal Khan` (College
  BDM A, reports to M1), `QA Peer` (College BDM B, reports to M1).
- Data: T1 tomorrow Hyderabad → Vijayawada with the §4 example (10:00 ABC Course Promotion Confirmed, 1:00 XYZ MoU Discussion
  Confirmed, 4:00 PQR Principal Meeting Scheduled), T2 today → tomorrow approved, two expenses, completed, remarks; T3 empty.
- Script: `qa011.cjs` (session scratchpad); console errors, page errors, HTTP ≥ 400 and failed requests captured per role.

## Pass 1 — independent, no code changes

| Area | Result |
|---|---|
| Happy path (§4 table, AC4) | Rows `10:00 am ABC College Course Promotion Confirmed`, `1:00 pm XYZ … MoU Discussion Confirmed`, `4:00 pm PQR … Principal Meeting Scheduled` |
| Productivity (AC2) | Planned 3, Completed 0, Estimated ₹2,500.00, Actual ₹0.00, Cost per completed "No completed meetings yet", Expected leads 60, Expected revenue ₹50,000.00, Actual leads 0, Actual revenue "Not tracked yet" |
| Invalid input (AC1) | API create on a date outside T1 → 422 "This appointment is on 11 Oct 2026, outside TRV-000005 (07 Oct 2026 – 07 Oct 2026)"; the form offers no trip for that date ("None of your open trips covers this date.") and is disabled until a date is chosen ("Choose the date first.") |
| Empty state | T3: "No appointments are linked to this trip yet. Link one from an appointment's Edit form, or Book an appointment." |
| Server error | The trip choice read failing → covered by unit test (form note; booking still works); not reproducible in the browser (server-side read) |
| Loading | Pages are server-rendered under the existing `travel/[id]/loading.tsx`; the report route sits under it |
| Cancel / back | Edit → Cancel returns focus to Edit; report "Back to the trip" returns to the trip |
| Refresh | Trip page reload keeps the URL and hash |
| Duplicate submission | Double click on Book appointment → one appointment (itinerary 3 → 4) |
| Unauthorized | Signed out → `/bdm/sign-in?next=…/report`; malformed id → sign-in card without asking the API for the trip |
| Wrong role / scope | Peer BDM: another BDM's trip, report and the manager report URL → "Access unavailable"; PATCH another BDM's appointment → 404; other-team manager → "Access unavailable" |
| Layout | Trip page, both reports, booking form, appointment detail: no sideways scroll at 1366 / 768 / 375 / 320; no broken images; no unlabelled control |
| Navigation | Completed trip → "View travel report" (owner and manager); appointment Trip row → trip `#trip-appointments`; manager appointment → manager trip |
| Messages | Unlink "Changes saved." with Trip "—"; reschedule outside → "Appointment rescheduled. It is now outside TRV-000005's dates, so it was removed from that trip."; report before completion → "The travel report is available once the trip is completed" |
| Console / network | No console errors, no page errors, no failed API call. Only `_rsc` prefetches aborted by navigation (Next.js, not errors) |

### Findings

| ID | Severity | Role | Page | Steps | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA11-01 | Medium | BDM | `/bdm/travel/{id}#trip-appointments` | Open the trip with the reminder's deep link (View Appointments) | The Appointments section is scrolled into view | The page opens at the top; the section is below the fold (`getBoundingClientRect().top` outside the viewport) | qa011 "deep link #trip-appointments in view after load: false" |
| QA11-02 | Medium | BDM, manager | Trip page / report, 375 px | Open a trip with appointments on a phone | Each meeting's status visible without sideways scrolling | Time / Organization / Meeting fill the width; Status is cut off and needs a horizontal scroll inside the table | `report-owner-375.png` |
| QA11-03 | Low | BDM, manager | Travel report | Open a completed trip's report | "Total" aligned with the category names | "Total" (`<th>`) is centred | `report-owner-375.png` |
| QA11-04 | Low | BDM, manager | Trip page / report | Look at the itinerary's organization names | They read as links (they open the appointment) | Plain text colour, no underline (the global `a` reset; bdm-013 QA13-01 fixed the same) | `trip-owner-1366.png` |

All four are caused by bdm-011 and in scope; they are fixed test-first below.

## Fix pass (Phase 6) — each fixed with a failing test first, then re-checked in the browser on the rebuilt web container

| ID | Test (RED first) | Fix | Browser re-check |
|---|---|---|---|
| QA11-01 | `TripItinerary.test.tsx` "QA11-01: a deep link … scrolls its section into view"; a foreign hash scrolls nothing | `TripWorkspace` scrolls `#trip-appointments` / `#trip-costs` / `#trip-remarks` into view on mount (the streamed page has no anchor when the browser first looks) | All three deep links open with their section in view |
| QA11-02 | "QA11-02: every cell carries its column name …" | Itinerary table `table trip-itinerary` + `data-label` cells; `globals.css` stacks rows as labelled cards ≤ 640 px (the QA27-05 pattern) | 375 px: Status cell inside the viewport (x 54 + w 267 ≤ 375); `recheck-trip-375.png` |
| QA11-03 | `TripReport.test.tsx` Total row header `text-align: left` | `th scope="row"` left-aligned | computed `text-align: left` |
| QA11-04 | "QA11-04: organization names look like links" | `LINK_STYLE` on the itinerary links | computed `underline rgb(7, 85, 185)` |

Pass 2 (the full script again on fresh data, after the fixes): every pass-1 observation repeated unchanged; no console errors, page
errors or failed API calls; no sideways scroll at 1366 / 768 / 375 / 320 on the trip page, both reports, the booking form and the
appointment detail. Note: the owner's report headings read empty only in the instant after a client navigation (the loading state);
read after load (and on the manager's report) they are Trip details, Appointments, Productivity, Expenses by category, Remarks.

**Open issues:** none in bdm-011 scope.
