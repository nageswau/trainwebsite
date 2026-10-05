# bdm-009 — Browser QA pass 1 (2026-10-05)

**Build:** `feature/bdm-009-activities` @ `5de59d95` (migration `0070_bdm_activities`, `DEC-SCOPE-068`).
**Stack:** compose project `bdm009` (web `localhost:3009`, API `localhost:8009`), seeded; database at `0070_bdm_activities (head)`.
**Browser:** isolated Chrome (own profile, CDP 9333) driven by Browser Use; viewport 1280 px, emulated 375 px and 320 px.
**Accounts:** created through the real admin API and activated with the welcome token — one BDM Manager, two College BDMs on
that manager's team; one College organization assigned to BDM1 with two contacts (Dr Rao, Ms Iyer).

## Playwright (same stack)

| Run | Result |
|---|---|
| `bdm-009-activities.spec.ts --repeat-each=2` (parallel, stack just started) | 1 passed, 1 failed — super admin sign-in `waitForURL` timed out on the cold stack |
| same, serial, warm | **2 passed** (16.8 s) |
| same, parallel, warm | **2 passed** (12.2 s) — the first failure was a cold-start timeout, not a defect |
| `bdm-010-travel.spec.ts` | **6 passed** |
| `bdm-002-organization-crm.spec.ts` | **main journey FAILED** — strict mode: `getByRole('status')` resolves to 2 elements on the organization profile → **QA9-01** |

## Acceptance criteria observed in the browser

| AC | Observation | Result |
|---|---|---|
| AC1 | BDM1 logs a Call (Outgoing, note) and a Visit (contact Ms Iyer) on the profile; an Email from the activities page through the organization picker | Pass |
| AC2 | Form defaults When to now (`max` = now); hint "Your local time. Up to 7 days back."; API rules covered by backend tests | Pass |
| AC3 | `/bdm/activities`: Calls made 1, Organizations contacted 1, Call 1, Visit 1 → after deleting the visit Visit 0; manager view Call 1, Email 1 | Pass |
| AC4 | Today's call edited ("Activity saved."); visit deleted after the inline confirm ("Activity deleted.") | Pass |
| AC5 | Peer BDM2 (same type, not assigned) sees the timeline with no Log / Edit / Delete; archived org: Log hidden, API 422 "This organization is archived", today's entries still editable | Pass |
| AC6 | Timeline newest first, logger and contact shown ("Ms Iyer · Logged by QA Asha BDM1") | Pass |
| AC7 | Contact select lists the organization's contacts after the picker choice | Pass |
| AC11 | Empty states ("No activity logged yet.", "No activities on this day.", "No activities from QA Asha BDM2 on this day."); focus to Channel on open, to Organization picker on the activities page; client validation "Check the highlighted fields." + "Choose outgoing or incoming." with focus on Outgoing; status announcements with focus on the status region; note markup shown as text; leave guard prompts on a dirty edit form | Pass, with QA9-01..05 |
| AC12 | No horizontal overflow at 375 / 320 px on `/bdm/activities`, the org profile (form closed and open — single column, 246 px) and `/bdm/manager/activities`; keyboard: channel by arrows, direction by Space, submit / delete / confirm by Enter | Pass |
| W4 | Logging from `?date=2026-10-04` announces "Activity logged for 2026-10-05. Change the day to see it." | Pass, with QA9-04 |

## Findings

| ID | Severity | Where | Finding | Fix |
|---|---|---|---|---|
| QA9-01 | **Medium** | Org profile (`BdmOrganizationDetail` + `BdmActivityTimeline`) | Two `role="status"` live regions on one page (the profile's and the timeline's). Breaks bdm-002's existing Playwright journey (strict mode) and gives screen-reader users two competing live regions | The timeline reports its notices through the profile's existing status region (an `onNotice` callback); remove the timeline's own region. bdm-002's spec stays unchanged |
| QA9-02 | **Medium** | `BdmActivityForm` in `.form-grid` | Controls stretch to the grid row: Channel and Contact selects render ~76–120 px tall, Save / Cancel become ~220 px tall tiles, the Direction fieldset shows the browser's default border; the layout jumps when Direction appears / disappears | Follow the existing `.funding-panel .form-grid` / `fieldset.form-section` pattern: `align-items: start` on the form, actions and the top message span both columns, the direction fieldset uses the app's fieldset style (no default border) |
| QA9-03 | Low | Timeline / day list | A success notice ("Activity logged.") stays visible after the next action starts (e.g. a new form is opened) and next to later refusals | Clear the notice when a form opens and on `onLocked` |
| QA9-04 | Low | `BdmActivityDay` past-day notice | Uses the ISO date ("2026-10-05") while the rest of the UI writes "05 Oct 2026" | Format the day with the existing date formatter |
| QA9-05 | Low | Timeline | The empty status region leaves a visible gap between the Activity heading and the list | Render the status region without spacing when empty (as the profile's region does) — resolved by QA9-01 |

Observed, not bdm-009 defects (recorded only): a click in the first ~1.5 s after navigation is lost before hydration (all App Router pages);
"Loading…" text from the streaming fallback stays in the DOM (hidden).

## Parked items from the final review, checked

- Focus after an edit refusal: needs a day change or a concurrent delete to trigger — covered by component tests; not reproducible in this pass.
- Stale notice on lock: observed as QA9-03.
- `services/bdm_activities.py` docstring wording: folded into the fix pass.

## Status

Not complete: QA9-01..05 to fix, then rebuild `web` (owner) and rerun Playwright (bdm-009 ×2, bdm-002, bdm-010); independent Codex review and
the owner's full suites remain.
