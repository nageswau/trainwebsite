# bdm-011 — Trip ↔ appointment linking, itinerary, productivity, travel report (design)

Status: design for `DEC-SCOPE-079` (owner answers L1–L4, in-session 2026-10-06). Migration `0080_bdm_appointment_trip` after
`0079_bdm_mous`. Backlog: `docs/delivery/BDM_CRM_BACKLOG.md` § bdm-011.

## 1. Evidence and authority

| Item | Source | Class |
|---|---|---|
| "connect travel and appointments"; itinerary table Time / Organization / Meeting / Status; 3 appointments on 18 Sep | `EVID-016` §4 (149–170) | DERIVED_BLUEPRINT, in scope by `DEC-SCOPE-055` D1 |
| Agent trip shows agents to be visited | Agent §D (655–683) | same |
| School trip lists its appointments | School §F (982–998) | same |
| College trip auto-calculates Total Meetings, Travel Cost, Expected Leads, Expected Revenue | College §F (1224–1252) | same |
| Travel reminder buttons View Appointments / View Expenses / Add Remarks (deep links) | §7 (229–248) | same; the reminder itself is bdm-012 |
| Expected figures = BDM estimate per appointment, summed per trip | Q-07 / D16 | EXPLICIT_APPROVAL |
| Revenue = paid fees of attributed students only; others not tracked | Q-08 / D17 | EXPLICIT_APPROVAL |
| Rejected trip: linked appointments stay, shown "trip not approved" | Q-05 / D14 | EXPLICIT_APPROVAL |
| Actual cost = sum of expense lines | Q-06 / D15 | EXPLICIT_APPROVAL |

Dependencies: bdm-006 (merged, PR #58, browser QA closed) and bdm-010 (COMPLETE) — satisfied. bdm-017 (lead attribution) is on `main`.

## 2. Owner decisions (DEC-SCOPE-079)

- **L1 Actual leads:** leads (`enquiries`) the trip's BDM attributed (`bdm_user_id`) to organizations met in the trip's **completed**
  linked appointments, created from the travel date 00:00 IST up to the end of return date + 7 days (IST).
- **L2 Link rules:** link / unlink only while the appointment is open (scheduled / confirmed / rescheduled — the existing PATCH rule),
  to the BDM's own trip whose travel status is planned or in progress (any approval state; draft / submitted / rejected show "trip not
  approved yet"). The appointment's start (IST date) must lie within [travel date, return date], else 422.
- **L3 Meetings planned:** linked appointments that are not cancelled (no-shows count as planned, not completed). Expected leads /
  revenue sum the same set.
- **L4 Cancelled trip:** links stay (the record); no new link to a cancelled or completed trip; the BDM can still unlink.

Spec decisions (no new product choice): actual revenue shows "Not tracked yet" (D17: only College training fees are computable,
and that is bdm-021); a trip date edit that would leave a linked appointment outside the new range is refused (422) rather than
silently unlinking; a reschedule outside the trip range unlinks automatically (backlog edge case) with an audit row and an on-screen
notice; the report is the trip detail behind a "completed" gate.

## 3. Data

`bdm_appointments.trip_id UUID NULL REFERENCES bdm_trips(id) ON DELETE RESTRICT` + index `ix_bdm_appointments_trip`. Additive;
no row written. Trips are never deleted, so RESTRICT never fires. downgrade drops the index and column (links are lost — the
migration says so; nothing else depends on them).

## 4. API (all additive)

| Route | Change |
|---|---|
| `POST /bdm/appointments` | optional `trip_id` (L2 rules) |
| `PATCH /bdm/appointments/{id}` | optional `trip_id`; `null` unlinks; unset = unchanged |
| `POST /bdm/appointments/{id}/reschedule` | a linked appointment moved outside its trip's dates is unlinked (audit `bdm_appointment.trip_unlinked`) |
| `GET /bdm/appointments/{id}` (+ every envelope) | `trip`: `{id, code, from_place, to_place, travel_date, return_date, approval_status, travel_status}` or null |
| `GET /bdm/trips` | `linkable=true`: own trips, planned / in progress, not ended before India's today (the form's trip choices; the form narrows them to the chosen date) |
| `GET /bdm/trips/{id}`, `/bdm/manager/trips/{id}` and every trip write | `itinerary[]` and `metrics` |
| `PATCH /bdm/trips/{id}` | date change leaving a linked appointment outside → 422 |
| `GET /bdm/trips/{id}/report`, `GET /bdm/manager/trips/{id}/report` | the trip (`BdmTripOut`) when completed; 409 otherwise |

Errors: another BDM's trip → 404 "Trip not found"; another BDM's appointment → 404 (existing); cancelled / completed trip → 409
"This trip is cancelled and can't take appointments"; out of range → 422 "This appointment is on 18 Sep 2026, outside TRV-000123
(20 Sep 2026 – 21 Sep 2026)".

`itinerary[]`: `{id, code, starts_at, duration_minutes, appointment_type, status, organization: {id, name}, expected_leads,
expected_revenue}`, ordered by start then id.

`metrics`: `meetings_planned`, `meetings_completed`, `estimated_cost`, `actual_cost`, `cost_per_completed_meeting` (actual cost ÷
completed, 2 dp, null when none completed), `expected_leads` / `expected_revenue` (sums over L3, null when no appointment has an
estimate), `actual_leads` (L1), `actual_revenue` (always null = not tracked).

Authorization: owner routes scope trips by `bdm_user_id = caller` (404); manager routes by team (existing `load_team_trip`);
the appointment and its trip must belong to the same BDM because the trip is loaded with the caller's id. Managers never link.

Concurrency: the link takes the appointment lock (existing), then the trip `FOR SHARE`; trip date edit / cancel hold the trip
`FOR UPDATE` — so a link and a date edit / cancel serialise and the second sees the first's result. Order appointment → trip is
never reversed (trip writes take no appointment lock), so no deadlock.

Logs: ids and counts only.

## 5. Web

- Trip page (`TripWorkspace`, owner + manager): new **Appointments** section (`id="trip-appointments"`) — itinerary table (Date /
  Time / Organization / Meeting / Status, each row links to the appointment), empty state with "Book an appointment" (owner), and
  notices for "trip not approved yet" and "trip cancelled". New **Productivity** tiles (`kpi-grid` / `kpi-tile`, as
  `SchoolKpiBoard`), "Not tracked yet" for actual revenue. Sections `trip-costs` / `trip-remarks` get ids: the reminder deep links are
  `/bdm/travel/{id}#trip-appointments|#trip-costs|#trip-remarks`. A completed trip shows "View travel report".
- Report pages `/bdm/travel/[id]/report` and `/bdm/manager/trips/[id]/report`: read-only summary — details, itinerary, productivity,
  expenses by category with total, remarks (the browser's own print serves for paper; `ReportPreview` is a static placeholder, not
  reused); 409 → "available once the trip is completed" + back link.
- Appointment form (create + edit): optional **Trip** select. The server page reads `GET /bdm/trips?linkable=true` once (beside its
  own data; a failure only hides the choice with a note) and the form offers the trips covering the chosen IST date ("No trip"
  first; a date change that leaves the chosen trip clears it); the current trip stays listed even when no longer linkable. No
  client fetch is added to the form. Detail page: a "Trip" row linking to the trip's appointments section.
- Reschedule that unlinked: "Appointment rescheduled. It is now outside TRV-… so it was removed from that trip."

## 6. Acceptance criteria → tests

| AC | Test |
|---|---|
| AC1 linking outside the trip's dates → 422 | `test_bdm_011_links.py` |
| AC2 counts and costs exact; actual revenue not tracked; actual leads per L1 | `test_bdm_011_metrics.py` |
| AC3 report only after completion | `test_bdm_011_report.py` |
| AC4 §4 example (3 appointments, 18 Sep-style day) renders | web component test + Playwright `bdm-011-trip-itinerary.spec.ts` |
| Negative: another BDM's appointment / trip → 404 | `test_bdm_011_links.py` |
| Edge: reschedule outside → unlinked + audit; cancelled trip keeps links, refuses new | `test_bdm_011_links.py` |
| Trip date edit leaving an appointment outside → 422 | `test_bdm_011_links.py` |
| Migration additive, one head | `test_bdm_011_migration.py` |

## 7. Out of scope

Reminder delivery (bdm-012), calendar (bdm-013), My Day (bdm-014), revenue computation (bdm-021), linking closed appointments.
