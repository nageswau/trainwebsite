# itc-020 — Batch timetable and session calendar (design + plan)

**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-020 (classification `UNVERIFIED` PDF §4 "timetable, class link/room, session
calendar", §6, §8 Faculty "Today's classes"; owner-approved for build in waves by Q-01, 2026-11-01). **Decision:** `DEC-SCOPE-342`.
**Dependencies:** none (backlog). Blocks itc-021 (session link), itc-024, itc-025. Q-18 is open; built with the recommended answers
below (owner: "proceed with recommended answers"), each `NEEDS_CONFIRMATION`.

## Intent

`Batch.schedule` is a 160-character free-text string, so nobody — student, trainer, counselor — can see *when the next class is*, where
it is (room or link), or that one was called off. itc-020 gives each IT batch a structured weekly timetable and shows the dated classes it
produces in one calendar for every role that needs it.

## Behaviour

1. **Table** `batch_timetable_slots` (`id`, `batch_id` → batches indexed, `weekday` 0=Mon…6=Sun, `start_time`, `end_time` (local time
   in the batch's timezone), `mode` `online|offline`, `room` (≤120), `meeting_url` (≤500, http/https), `topic` (≤160), timestamps).
   CHECKs: weekday range, `end_time > start_time`, mode values, offline ⇒ room. **Table** `batch_timetable_cancellations` (`id`,
   `slot_id` → slots ON DELETE CASCADE, `occurs_on` date, `reason` text, `cancelled_by_user_id`, timestamps; UNIQUE (`slot_id`,
   `occurs_on`)). Migration `0226_batch_timetable` (additive; downgrade drops both).
2. **Edit (IT Admin, Super Admin)** — `GET/POST /it/batches/{id}/timetable`, `PUT/DELETE /it/batches/{id}/timetable/{slot_id}` (PUT replaces the whole slot):
   unknown batch/slot → 404; other roles → 403; validation → 422; a slot overlapping another slot of the same batch on the same weekday,
   or a slot of **another batch with the same trainer** whose date range overlaps → **409** naming the clash. The batch row (and the
   trainer row, when set) is locked `FOR UPDATE` so two concurrent edits cannot both pass the overlap check. Audited
   `batch.timetable.create|update|delete` (ids + changed field names only).
3. **Cancel one class** — `POST /it/batches/{id}/timetable/{slot_id}/cancellations {occurs_on, reason}` (IT Admin): the date must be a
   real occurrence of the slot inside the batch dates (422), today or later (422), not already cancelled (409). Audited
   `batch.timetable.cancel`; the batch's active students get the itc-002 `it.batch.changed` notice (fixed preview-safe text, link
   `/it/student/timetable`). Counselor notices are itc-025.
4. **Calendar feed** — `GET /it/timetable?from=&to=&batch_id=` (inclusive dates, default today…today+13, max 62 days → 422):
   occurrences are **computed**, never stored: each slot × each matching weekday inside `[batch.start_date, batch.end_date] ∩ window`,
   `starts_at`/`ends_at` in the batch timezone (IST by default). Dated `LiveSession`s of the same batches in the window are merged in as
   `kind: "live_session"`. Sorted by `starts_at`. Scope:
   - `it_student`: batches with an **active** enrolment; cancelled classes are omitted; `meeting_url` withheld while the nehn-018
     `live_classes` feature is locked.
   - `trainer`: batches they train; cancelled ones shown with reason.
   - IT `counselor`: batches of their itc-003 linked students' active enrolments; no `meeting_url` (not a batch member).
   - `it_admin`/`super_admin`: every batch (or `batch_id`).
   - anyone else 403; a `batch_id` outside the caller's scope → 404.
5. **UI** — a **Timetable** nav entry for IT student, trainer, counselor and admin. All four get the `TimetableCalendar` agenda (week
   navigation, grouped by day, Today marker, loading / empty / error states, join link or room). The admin page adds
   `BatchTimetableEditor` (pick a batch, list / add / edit / delete slots) and a **Cancel class** action on future class occurrences.

## Calls made under "proceed with recommended answers" (`NEEDS_CONFIRMATION`)

T1 (Q-18a) occurrences are computed from slots, not materialised as `LiveSession` rows; existing live sessions are shown alongside.
`LiveSession.room` is therefore not added. T2 (Q-18b) no holiday calendar: the admin cancels single classes. T3 (Q-18c) overlap = same
weekday, time ranges intersect, batch date ranges intersect; same batch or same trainer → 409. A batch trainer change (PATCH batch) is not
re-checked (itc-025 / follow-up). T4 editing is IT Admin + Super Admin only (the certificate `coordinator` has no batch grants today).
T5 no restore of a cancelled class (admin re-adds by contacting students; follow-up). T6 the iCal feed is deferred (backlog "optional").
T7 `Batch.schedule` free text is untouched.

## Non-goals

Attendance by session (itc-021), at-risk (itc-023), faculty "Today's classes" dashboard (itc-024), counselor/batch-change notices (itc-025),
iCal, holidays, recurring exceptions other than single-class cancel.

## Plan (TDD)

1. Models + migration 0226 + migration test (upgrade, CHECKs, cascade, downgrade).
2. `services/batch_timetable.py`: `validate`, `overlaps`, `occurrences(slots, cancellations, batches, window)` — unit tests for IST
   occurrences, mid-week batch end, cancellations.
3. `api/batch_timetable.py`: CRUD + cancel + feed; tests for 200/201/204/403/404/409/422, scope per role, notice + audit.
4. Portal payload headers for `timetable` in student/trainer/IT counselor/admin; nav entries.
5. Web: `lib/timetable.ts`, `TimetableCalendar`, `BatchTimetableEditor`, PortalPage wiring; vitest.
6. Docs: DEC-SCOPE-342, API §12IN, RBAC §2.242, RTM, backlog status. Playwright spec + browser QA.
