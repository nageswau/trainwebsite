# bdm-012 — Browser QA (2026-10-07)

- Stack: isolated Docker Compose project `bdm012` (web `127.0.0.1:13012`, api `127.0.0.1:18012`) with **worker and beat running**, built from
  `worktree-bdm-012`; demo data seeded with `python -m app.seed`. SMTP unset (the delivery path for `not_configured`).
- Browser: isolated Playwright Chromium (fresh context per role). Browser Use is **not installed** on this machine (as recorded by the
  earlier BDM items); the scripted Playwright pass stands in for it.
- Roles: College BDM (owner), a second College BDM, BDM Manager, signed-out visitor.

## Exploratory pass (no code changed before it was recorded)

| # | Area | Result |
|---|---|---|
| 1 | Beat → worker | `bdm012-reminders` sent every 5 min; worker log `bdm012_reminders_done` with counts only. A second run: `created 0, duplicate 11` (AC4, live) |
| 2 | Hour-before (real time) | A meeting booked 30 min ahead got "Appointment in 1 hour" on the next run; body has organization, time, location, no phone |
| 3 | Day-before / travel / follow-up (same-day catch-up, R4) | Booked at 12:10 IST for tomorrow 10:00 → "Appointment reminder" with source wording; approved trip tomorrow → "Travel reminder"; follow-up due today → "Follow-up due today" |
| 4 | Text safety | An organization named `QA <b>College</b>` shows as literal text in the list and detail; a purpose ending in "." gives no double full stop; contact phone / email absent from every body |
| 5 | Email | Every reminder has one `email` delivery, status `not_configured` (SMTP unset), attempt 1; in-app row present (R9) |
| 6 | In-app links | Notice → appointment, trip, `/bdm/follow-ups?kind=follow_up` (the task listed) |
| 7 | Anchors | `#trip-appointments`, `#trip-costs`, `#trip-remarks`, `#org-mou` each scrolled into view |
| 8 | `?action=reschedule` / `cancel` | Form open, first field focused; Escape closes and returns focus to its button; `?action` dropped — refresh and Back do not reopen it |
| 9 | `?action=confirm` | Confirm focused, note "Check the details, then select Confirm."; status stays Scheduled until clicked; afterwards the link says "already confirmed" |
| 10 | Unknown action | `?action=delete` ignored |
| 11 | Signed out | Link → BDM sign-in chooser → College BDM login → back on the appointment with the Cancel form open (`next` kept); nothing changed |
| 12 | Wrong user | Another BDM: "Appointment not found", no form; a manager: "Access unavailable" |
| 13 | Layout | Notifications at 1280 / 820 / 375 px and the appointment at 375 px: no horizontal scroll |
| 14 | Console / network | 0 console errors, 0 page errors, 0 responses ≥ 500 |

## Issues

None caused by bdm-012. Notes:

- An appointment Purpose containing a newline is refused by bdm-006's existing validation (422) — expected behaviour, unchanged.
- First e2e attempt failed on super-admin sign-in because the fresh `bdm012` database had no demo seed (environment, fixed by seeding).
- The e2e spec's signed-out assertion was wrong (expected a "sign in" link; the app correctly redirects to the chooser) — the spec now
  follows the full sign-in round trip.

## Automated

`tests/e2e/bdm-012-reminders.spec.ts` — 1 passed (3.8 min, real beat).
