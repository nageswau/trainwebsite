# rec-029 Campus recruitment drives — exploratory browser QA (2026-10-11)

## Setup
- **Stack:** compose project `rec029` (web `:13029`, API `:18029`) from `docker-compose.yml`, seeded with `python -m app.seed`, plus a
  scratch QA seed (company "XYZ Technologies QA" for the seeded recruiter with two live requirements, the BDM college org "ABC College of
  Engineering", six pool candidates).
- **Browser:** headless Chromium (Playwright from `apps/web/node_modules`), driven by scratch QA scripts; plus the committed spec
  `tests/e2e/rec-029-drives.spec.ts`.
- **Accounts:** `placement@edusphere.local` (recruiter), `placement.manager@edusphere.local` (manager), `hr@edusphere.local` (hr_team),
  signed out.
- **Viewports:** 1366×900, 820×1180 and 390×844.

## First pass (no code changed): 3 issues found

| ID | Severity | Role | Page | Steps | Expected | Actual | Fixed |
|---|---|---|---|---|---|---|---|
| QA29-01 | Low | recruiter | `/recruiter/drives` → + New drive (also Edit) | Look at the date / role / vacancies / registered / attended row at 1366 px | Inputs aligned, same height | "Students attended" (which has a hint) sat higher and shorter than its neighbours: the grid stretched every cell to the tallest | Yes: the grid aligns to the start; every input measured at the same top (773 px) and height |
| QA29-02 | Low | recruiter | same form | Compare "Job requirements" / "College" with the other labels | The same weight and size as `.field label` | Lighter (600) and larger | Yes: legends use 800 / 13 px |
| QA29-03 | Low | recruiter, manager | `/recruiter/drives/{id}` | Open a drive with candidates at 390 px | Each candidate readable without sideways scrolling | The candidates table (`.table`, min-width 650 px) scrolled sideways inside its card; requirement names cut off | Yes: stacked items (rec-017's phone-width pattern); a vitest asserts the list and no table; 0 px overflow, no table at 390 px |

## Checks (after the fixes): all passed

| Area | Check | Result |
|---|---|---|
| Navigation | "Campus Drives" in the recruiter, manager and super admin menus | PASS |
| Happy path | Create with a BDM college + two requirements → the drive page with the funnel 200 / 100 / 0 / 0 / 0 / 0 | PASS |
| Validation | Empty submit → "Choose the company."; attended 200 > registered 100 → the AC2 message, no request; the same on edit | PASS |
| API | `PATCH` attended 9999 → `422` on `students_attended` (AC2) | PASS |
| Duplicate submit | A double click on Create sends one `POST` | PASS |
| Add through drive | Three candidates added (Shortlisted / Sourced / Sourced) → "Candidate added through this drive.", Shortlisted 1 (AC1); the same candidate again → the API's 409 message in the form | PASS |
| Refresh / back | The funnel and candidates survive a reload; Back returns to the drive | PASS |
| Edit | Status → Completed, attended 150 → "Drive saved.", badge Completed | PASS |
| List | Search by college finds the drive; a search with no match → "No drives match these filters."; the card shows college, company, date, counts | PASS |
| Not found | Unknown id and a malformed id → "Drive not found" | PASS |
| Roles | Manager: funnel visible, no Edit, no Add, no "+ New drive"; hr_team: the access card ("Recruiter role required") on both pages; signed out → `/it/login?next=…` | PASS |
| States | "Loading drives…" while the list loads; a routed 500 → "Unable to load drives." + Try again → the list | PASS |
| Errors | A routed 500 on Create shows the message and keeps the typed form; an aborted request shows the connection message and keeps it; a routed 500 on Add shows "Something went wrong." | PASS |
| Keyboard | Enter on "+ New drive", Tab into the company picker, type + ArrowDown + Enter picks the company | PASS |
| Layout | No page overflow at 820 and 390 px on the list, the form and the drive page; funnel tiles wrap two per row on phones | PASS |
| Hygiene | No broken images, no page errors, no 5xx; the only console error is the browser's log of the deliberate 409 | PASS |

## Automated evidence
- `tests/e2e/rec-029-drives.spec.ts`: 1 passed (`--workers=1`).
- vitest `RecruiterDrives.test.tsx` (6), `recruiterDrives.test.ts` (6), `navigation.recruiter.test.ts` (3): 15 passed.
- pytest `test_rec_029_drives.py` (19) and `test_rec_029_migration.py` (4), with rec-017 tracking/legacy: 64 passed; RBAC / hardening /
  tel-026 + upc-033 matrices, rec-017 migration, rec-020, rec-028, rec-030 migration: 335 passed (one upc-033 row needed `app.seed` first).
