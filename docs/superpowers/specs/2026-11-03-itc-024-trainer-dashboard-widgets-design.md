# itc-024 — Trainer dashboard widgets (design)

**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` `itc-024` (PDF §8 Faculty dashboard, §11 Faculty workspace), Appendix B.
**Dependencies:** itc-020 (`DEC-SCOPE-344`, batch timetable, merged #417) and itc-023 (`DEC-SCOPE-352`, at-risk flags, merged #425).
**Decision:** `DEC-SCOPE-355`. No migration. API §12JA (additive). RBAC §2.255 (unchanged grants). (Siblings itc-018/itc-027 hold
353/354 and §12IY/§12IZ.)

## 1. Behaviour

`GET /portal/it/trainer/dashboard` keeps its four tiles (Assigned batches, Assignments, Upcoming sessions, Pending reviews) and its
batch table, and gains four tiles and one panel:

| Widget | Definition (Claude's call where Appendix B is silent — `NEEDS_CONFIRMATION`, Q-21) |
|---|---|
| **Today's classes** (tile + panel) | The non-cancelled classes of the trainer's batches dated today (IST): itc-020 timetable classes plus live sessions, read through `batch_timetable.occurrences(today, today)` (one definition with the Timetable page). The panel lists each `HH:MM–HH:MM · batch · topic` with its attendance state; empty → "No classes today". |
| **Attendance completion** (Appendix B) | Classes held today with attendance marked ÷ classes held today. *Held* = a listed class whose start time has passed (W2a). *Marked* = the batch has ≥1 attendance row dated today — attendance is stored per batch-day (itc-021 L4), so two classes of one batch on one day share their marking (W2b). Shown `marked/held · pct %`; no class held yet → `—`. |
| **Assessment completion** | Over the batch's counted assessments (`training_progress.COUNTED_ASSESSMENTS`) whose `scheduled_at` has passed: distinct (student, assessment) pairs with a submitted or graded attempt by an **active** enrolled student ÷ (active students × those assessments) (W3). Shown `done/expected · pct %`; nothing due → `—`. |
| **At-risk students** (Appendix B / itc-023) | Open `StudentRiskFlag`s (`cleared_at IS NULL`) of the trainer's batches — the same rows the "Students at risk" list shows. |

**Batch filter (W5):** an optional `?batch=<uuid>` narrows every figure and the batch table to that one batch (one rule for the whole
dashboard). The payload carries `batch_filter: {value, options}` (the trainer's own batches) so the page renders a "Batch" select;
the at-risk list on the page is narrowed client-side to the same batch so the tile and the list agree. The value lives in the URL.

## 2. Errors and authorization

- Only the trainer's own batches (`Batch.trainer_id == user.id`) are read; the existing role/division gate is unchanged.
- `batch` that is not a UUID, or not one of the trainer's batches (another trainer's or non-existent) → **422** "Choose one of your
  batches" (same answer either way — no existence leak). The page falls back to the unfiltered dashboard with the message (the AGN-023
  precedent).
- `batch` on any other role/section → **422** "The batch filter applies to the trainer dashboard only" (a filter is never ignored).

## 3. Performance

Fixed query count whatever the number of batches: batches, assignments, pending reviews, upcoming sessions, occurrences (3), attendance
marked today (1), assessment completion (1), at-risk (1).

## 4. Alternatives considered

- *A separate `/it/trainer/dashboard` endpoint and React panel* — rejected: the backlog places the widgets in the portal payload, and
  the tiles already render generically (`PortalSection`).
- *Count attendance completion per scheduled (not yet held) class* — rejected: Appendix B says "held"; a 7 pm class would read 0 % at 9 am.
- *Assessment completion = attempts graded ÷ attempts submitted* — rejected: MCQ attempts auto-grade, so it would read ~100 % always.

## 5. Tests

Backend `tests/test_itc_024_trainer_dashboard.py`: tiles present with definitions; today's classes (slot + live session, cancelled
excluded, other-day excluded); "No classes today"; attendance completion (held/not held, marked/unmarked); assessment completion
(due/not due, inactive student excluded); at-risk count (open only, own batches only); batch filter narrows; 422 on foreign/invalid
batch and on other sections; existing `test_trn_001` stays green. Frontend component test for the batch filter + panel empty text;
e2e `itc-024-trainer-dashboard.spec.ts`.
