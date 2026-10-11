# rec-021 Interview feedback — exploratory browser QA (2026-10-11)

## Setup
- **Stack:** compose project `rec021` (web `:13021`, API `:18021`) from `docker-compose.yml`, seeded with `python -m app.seed`.
- **Browser:** headless Chromium (Playwright 1.x from `apps/web/node_modules`), driven by a scratch QA script; plus the committed spec
  `tests/e2e/rec-021-interview-feedback.spec.ts`.
- **Accounts:** `placement@edusphere.local` (recruiter), `placement.manager@edusphere.local` (manager), `hr@edusphere.local` (hr_team),
  signed out.
- **Viewports:** 1280×900, 768×1024 and 375×812.
- **Making a Completed interview:** the recruiter API refuses a past time (rec-020 IV5), so the interview is moved into the past through
  the legacy `PATCH /workflows/it/interviews/{id}` (IV11 records it as a reschedule), then marked Completed in the UI.

## First pass (no code changed): 21 checks passed, 1 issue found

| ID | Severity | Role | Page | Steps | Expected | Actual | Fixed |
|---|---|---|---|---|---|---|---|
| QA21-01 | Medium | recruiter | requirement → interviews; `/recruiter/interviews` | Open "Edit feedback" at 375 px | Every field inside the card | The four textareas ran 24 px past the card's right edge (grid `minmax(16rem, 1fr)` wider than the card); no console or network error | Yes: the form's grids use `minmax(min(…, 100%), 1fr)`; a QA check (every control's right edge ≤ the form's) failed before, passes after at 768 and 375 px |

## Checks (second pass, after the fix): 23 / 23 passed

| Area | Check | Result |
|---|---|---|
| API | Feedback on a Scheduled interview → `409` | PASS |
| API | Signed out → `401`; `hr_team` → `403`; manager → `403`; overall 6 → `422` | PASS |
| Keyboard | "Record feedback" opens with Enter; Escape closes the form | PASS |
| Errors | A routed `500` shows "We couldn't save this. Please try again." and keeps the typed text; an aborted request shows the connection message | PASS |
| Happy path | Overall 4, decision On Hold, next round Final Round → status On Hold, summary shown, the schedule draft opens with Final Round (AC2) | PASS |
| Refresh / back | After a reload the summary and "+ Schedule Final Round (suggested)" are still there; Back / Forward land without errors | PASS |
| List page | The card under On hold shows the summary; "Edit feedback" → Selected; a double click sends one `PUT`; the card moves to Closed | PASS |
| Layout | No horizontal scroll and every control inside the form at 768 and 375 px (QA21-01) | PASS |
| Hygiene | No broken images; no console errors or 5xx besides the two deliberately injected ones | PASS |

## Automated evidence
- `tests/e2e/rec-021-interview-feedback.spec.ts` and `tests/e2e/rec-020-interviews.spec.ts`: 2 passed (`--workers=1`).
- vitest `RecruiterInterviewFeedback.test.tsx` (8) and `RecruiterInterviews.test.tsx` (12): 20 passed.
- pytest `test_rec_021_feedback.py`, `test_rec_021_migration.py`, `test_rec_020_interviews.py`: 58 passed; neighbours (EMP-004/005,
  rec-017, rec-022, rec-023): 131 passed.
