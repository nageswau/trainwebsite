# bdm-007 — Independent exploratory QA, pass 1 (2026-10-05)

**No code was changed in this pass.** Build under test: `feature/bdm-007-meeting-outcomes` @ `f76dc7b2`, compose project `bdm007qa`
(web `localhost:3107`, API `localhost:8107`, DB at `0072_bdm_meeting_reports`, seeded).
**Tools:** Browser Use is not installed on this machine; per the owner's choice the pass used throwaway Playwright scripts in the
`web-test` container — an isolated Chromium per scenario (base URL `http://host.docker.internal:3107`) recording console errors, page
errors, 4xx/5xx responses, failed requests and main-frame navigations, with screenshots. Scripts deleted afterwards.
**Accounts** (real admin API + welcome tokens): BDM Manager A (team: College BDM1, College BDM2, Agent BDM3), BDM Manager B (no team),
seeded IT admin. Organizations "QA Lotus College" (BDM1) and "QA Banyan Agency" (BDM3). 15 past appointments for BDM1 + 1 for BDM3
(start times moved into the past by SQL, because the API never books in the past), 1 future appointment. SQL was also used to close
an edit window (`submitted_at` − 1 day), to make one report legacy, and to age one pending appointment by 3 days.
Evidence (screenshots, per-scenario JSON) is in `artifacts/ci/qa7/` (git-ignored).

## Coverage

| # | Area | Result |
|---|---|---|
| 1 | Happy path | Pass — list "Outcome pending" filter shows the past appointments with a text badge; detail shows "Outcome pending — file the meeting report, or mark it as a no-show." + header badge; Complete → every field + follow-up → "Appointment completed.", report shows all fields (line breaks kept), follow-up `open` on the chosen date, history Scheduled → Completed, removed from the pending list; same-day Edit → "Meeting report saved.", focus to the status; clearing the date → follow-up `cancelled`, Next follow-up "—" |
| 2 | Invalid inputs | Pass — Save disabled with no outcome / no discussion / whitespace-only discussion; Discussion capped at 4000, Responsible person at 200; past follow-up date blocked by the browser (`min`), no request sent; API: control character 422 on the field, Agent outcome for a College BDM 422, `legacy` field 422 (extra forbidden), `2026-02-30` 422 "Enter a valid follow-up date", future appointment 422; mocked 422 shows "Check the highlighted fields." + field error with `aria-invalid`. Focus: **QA7-05** |
| 3 | Empty states | Pass — BDM2 and Manager B with the pending filter: "No appointments match these filters." + Clear filters; Manager A sees the team's pending rows with the BDM column. Older pending rows: **QA7-04** |
| 4 | Server errors (mocked) | Pass — complete 500: "We couldn't update the appointment. Please try again." text kept; offline: "The request did not complete… your entry is kept."; 409: "This appointment changed elsewhere — copy your notes, then reload." text kept + Reload (**QA7-03**); PATCH 503: "We couldn't save the report… your text is kept."; PATCH 409 (**QA7-02**) |
| 5 | Loading states | Pass — "Saving…" disabled during a 2.5 s save; other actions disabled; Cancel stays enabled |
| 6 | Cancel / back | Cancel and Escape close the form, focus returns to Complete / Edit report, reopening starts empty. Dirty form + Back / in-app link: **QA7-06** |
| 7 | Refresh | Pass for saved data (report persists after reload, Back/Forward keep it). Dirty form + reload: **QA7-06** |
| 8 | Duplicate submission | Pass — double-click "Save report and complete" → one POST (200), one follow-up; Enter twice on Edit → one PATCH; second complete via API → 409 "Appointment is already completed" |
| 9 | Unauthenticated | Pass — `/bdm/appointments/{id}` and the pending list → `/bdm/sign-in?next=…`; manager detail → `/admin/login?next=…`; API complete / PATCH report / list → 401 |
| 10 | Incorrect role / other users | Pass — Manager A reads the report (no Edit, no Book link, only "Sign out" button), pending note "the BDM hasn't filed the meeting report yet", API PATCH/complete 403; Manager A on the BDM URL → "Access unavailable — BDM role required"; Manager B and peer BDM2 → "Appointment not found" (API 404); IT admin → "Access unavailable — BDM role required", API 403; Agent BDM sees the 8 Agent outcomes, College BDM the 9 common ones; Agent BDM API with a college outcome 422; cross-type GET 404 |
| 11–13 | Desktop / tablet / mobile | Pass for overflow — 1440, 1024, 768, 390, 320 px: report form, report view and pending list have no horizontal overflow; a 600-char unbroken discussion and a 300-char URL wrap. Layout defect: **QA7-01** |
| 14 | Navigation | Pass — "Book the next meeting" after a Reschedule outcome → `/bdm/appointments/new?organization=…` with the contact prefilled; Back to appointments; organization link. Filter round-trip: **QA7-04** |
| 15–16 | Success / error messages | See above; **QA7-02**, **QA7-03** |
| 17 | Broken images | None on any page / width |
| 18 | Console errors | No JavaScript exceptions (`pageerror`) in any scenario. Only the browser's "Failed to load resource" lines for intentional 4xx/5xx (validation 422s, mocked 5xx/409, refusals) |
| 19 | Failed network calls | Only intentional ones (mocked, offline) and `net::ERR_ABORTED` on Next.js link prefetches (benign) |
| 20 | Unexpected redirects | None — signed-out redirects carry `next=` back to the requested page |

Also verified: closed window (`submitted_at` yesterday) → no Edit report, no hint, API PATCH 409; legacy report → "Recorded before
meeting reports — outcome only.", read-only.

## Issues

### QA7-01 — Low — An empty card appears between "Meeting report" and "History" after completion
- **Role:** BDM (owner, on the filing day). **Page:** `/bdm/appointments/{id}` (completed).
- **Steps:** complete an appointment with a report → look below the Meeting report section (any width).
- **Expected:** no Actions card when there are no actions (as for a manager or a cancelled appointment).
- **Actual:** an empty bordered card (the `Actions` section, `aria-label="Actions"`) renders with no buttons. The only true permission
  is `can_edit_report`, whose button lives in the report section, so the Actions bar's "any permission" check renders an empty group;
  screen readers announce an empty "Actions" region.
- **Evidence:** no console / network error. Screenshots `11-desktop-report.png`, `11-mobile-report.png`.

### QA7-02 — Medium — After the edit window closes on an open page, the page keeps offering edits and says it is still editable
- **Role:** BDM. **Page:** `/bdm/appointments/{id}` (report section).
- **Steps:** open a report filed today → Edit report → type → the IST day ends (reproduced by moving `submitted_at` back a day while
  the form was open) → Save changes → Save again → Cancel.
- **Expected:** after the 409 the page switches to read-only: the Edit report button and the "until midnight IST today" hint go away
  (the typed text can stay visible to copy).
- **Actual:** the 409 message "Meeting reports can only be changed on the day they were filed" shows and the text is kept, but Save
  stays enabled (a second PATCH → 409 again), and after Cancel the "Edit report" button and the hint "You can change this report
  until midnight IST today." are still shown. Focus goes to `<body>` after the 409.
- **Evidence:** `409 PATCH /api/v1/bdm/appointments/{id}/report` ×2; `document.activeElement` = BODY. Screenshot `B4-stale-409.png`.

### QA7-03 — Low — After "Reload" the "changed elsewhere" error and its Reload button stay on screen
- **Role:** BDM. **Page:** `/bdm/appointments/{id}`.
- **Steps:** Complete → fill → Save while the server answers 409 (mocked: another tab completed it) → Reload.
- **Expected:** the error clears once the page shows the fresh appointment.
- **Actual:** the status reads "This appointment is now Scheduled." (fresh data) but the alert "This appointment changed elsewhere —
  copy your notes, then reload." and the Reload button remain, next to the restored Complete button.
- **Evidence:** `409 POST …/complete` (mocked), then `GET /api/v1/bdm/appointments/{id}` 200. Screenshot `B5-after-reload.png`.

### QA7-04 — Low — `?status=outcome_pending` without `date_from=` hides older pending meetings; leaving the filter keeps From empty
- **Role:** BDM, BDM Manager. **Page:** `/bdm/appointments`, `/bdm/manager/appointments`.
- **Steps:** (a) open `/bdm/appointments?status=outcome_pending` (a shared / bookmarked link, or a future bdm-023 alert link) when a
  pending appointment started 3 days ago; (b) choose Status "Outcome pending" in the UI, then choose another status.
- **Expected:** (a) every pending meeting, whatever its date (pending meetings are by definition in the past); (b) From returns to its
  default (today) or the filter round-trip is otherwise predictable.
- **Actual:** (a) From defaults to today, so APT-000008 (3 days old) is not listed — only today's pending ones; choosing the filter
  in the UI does show it (it clears From). (b) After Outcome pending → Scheduled the URL is `?date_from=&status=scheduled` with From
  empty, listing every past scheduled appointment; "Clear filters" restores today.
- **Evidence:** no errors. Screenshot `B3-pending-no-datefrom.png`.

### QA7-05 — Low (accessibility) — Focus is lost after a validation error or refusal on the report
- **Role:** BDM. **Page:** `/bdm/appointments/{id}`.
- **Steps:** Complete (or Edit report) → Save when the server answers 422 with a field error (mocked) or 409.
- **Expected:** focus moves to the first invalid field (422) or the error message (409).
- **Actual:** the alert is announced and the field is marked `aria-invalid`, but focus falls to `<body>`.
- **Evidence:** `document.activeElement` = BODY after `422 POST …/complete`, `422 PATCH …/report`, `409 PATCH …/report`.

### QA7-06 — Medium — A typed meeting report is discarded without warning on Back, link navigation or reload
- **Role:** BDM. **Page:** `/bdm/appointments/{id}` with the report form open.
- **Steps:** Complete → type a discussion and next action → (a) browser Back, (b) "Back to appointments", (c) reload.
- **Expected:** a "Discard this report?" confirmation (or the browser's leave-page prompt), as the bdm-009 activity form does
  (QA9B coverage row 6) — a meeting report can be long.
- **Actual:** no prompt in any of the three; the text is lost.
- **Evidence:** no `dialog` event in (a), (b), (c); navigations `/bdm/appointments?date_from=` and `/bdm/appointments`.

### QA7-07 — Low — A stale field error survives Cancel and reappears when editing again
- **Role:** BDM. **Page:** `/bdm/appointments/{id}` (Edit report).
- **Steps:** Edit report → Save with a 422 field error on Next action (mocked) → Cancel → Edit report.
- **Expected:** a fresh form without errors.
- **Actual:** "Next action contains invalid characters" is still shown under the field, which is still `aria-invalid="true"`.
- **Evidence:** `422 PATCH …/report` (mocked). Screenshot `B1-stale-field-error.png`.

### QA7-08 — Info — A report whose window has closed gives no read-only explanation
- **Role:** BDM. **Page:** `/bdm/appointments/{id}`.
- **Observation:** the day after filing, the Edit report button and hint simply disappear; nothing says the report is now locked
  (legacy reports do say "outcome only"). A short "This report can no longer be changed." would explain the missing button.

## Summary

| ID | Severity | Area |
|---|---|---|
| QA7-02 | Medium | Stale edit window on an open page |
| QA7-06 | Medium | Unsaved report lost without a prompt |
| QA7-01 | Low | Empty Actions card |
| QA7-03 | Low | Stale "changed elsewhere" alert after Reload |
| QA7-04 | Low | Pending filter link hides older meetings; From round-trip |
| QA7-05 | Low | Focus after 422 / 409 |
| QA7-07 | Low | Stale field error after Cancel |
| QA7-08 | Info | No read-only explanation |

No Critical or High findings. Authorization, duplicate submission, server validation, the follow-up rules, the edit window on the
server and the layouts at 320–1440 px behaved as specified.
