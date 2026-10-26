# nehn-023 — Attendance correction usability and notifications (design + plan)

Source: `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-023` (§8 L173-182). Dependencies: none.

## Intent
Students raise a correction without ever seeing a UUID; the trainer gets a pending queue with Approve/Reject and an
optional comment; the trainer hears about new requests and the student hears the outcome.

## Current state (verified 2026-10-26)
- `POST /workflows/it/student/attendance-corrections` (typed `AttendanceCorrectionIn`) — built, no notification.
- `PATCH /workflows/it/attendance-corrections/{id}` takes `payload: dict`; it can re-review an already decided request.
- `GET /workflows/it/trainer/attendance-corrections` — trainer-scoped list (unchanged).
- Student UI: `WorkflowPanel` `studentSpecs("attendance")` asks for an "Attendance record reference" (UUID); the portal
  table shows a "Record reference" column and the panel lists `Request <uuid>`.
- Trainer UI: IT trainers get `TeacherWorkspaceActions` (a pending dropdown + decision select). `WorkflowPanel`'s
  `trainerSpecs("attendance")` UUID form is unreachable for them (`PortalPage`: `teacherWorkspace = it && trainer`).
- `attendance_corrections.review_notes` already exists, so there is **no migration**.

## Decisions (D1, D2 and D5 are my calls under "proceed with recommended answers"; recorded as DEC-SCOPE-284)
- **D1 Channels:** in-app + an instant email through the existing `queue_deliveries(..., channels=["email"])`. The
  worker sends it after commit, never inline. Digest vs instant stays `NEEDS_CONFIRMATION` (instant ships).
- **D2 Request recipients:** the batch's trainer if active. If the batch has no active trainer, every active `it_admin`
  gets the notification, pointing at `/it/admin/batches` (the admin's action is to assign a trainer; admins have no
  attendance page). The actor is never notified about their own action.
- **D3 Decision recipient:** the student (if active), with a link to `/it/student/attendance`; the body names the
  session, the outcome and the reviewer's comment, if there is one.
- **D4 Typed review body:** `AttendanceCorrectionReviewIn{status: Literal["approved","rejected"], review_notes: str|None
  (max 2000, blank → null)}`. The JSON shape is the same; a malformed body returns 422 (AC4).
- **D5 Review only while pending:** re-reviewing a decided request returns 409. This prevents a double attendance flip
  and a duplicate student notification on a double submit. Existing callers only ever review pending items.
- **D6 Additive read field:** `GET /it/student/attendance` rows gain `correction_pending: bool`.
- **D7 Student UI:** a new `AttendanceCorrectionPanel` (replaces the UUID spec). It shows a table of sessions
  (date, batch, status) with a "Request correction" button on each row. The button opens an inline form: correct
  status (excludes the current status), reason (5-2000 characters), Submit/Cancel. A pending row shows "Correction
  pending" instead of the button. It has loading, empty and error states.
- **D8 Portal payload (student):** drop the "Record reference" column. The panel items read
  `<date> · <batch>: <requested> — <status>[ (comment)]`.
- **D9 Trainer UI:** replace the dropdown form with a queue. Each item shows the student, batch, date,
  current → requested status and reason, an optional comment, and Approve/Reject buttons. Remove the unreachable
  UUID `trainerSpecs("attendance")`.

Non-goals: digest emails, an it_admin attendance page, notification preferences, a schema/migration change.

## Review (Phase 3)
- **API:** a stricter body, and the same paths, verbs and response shapes. 409 for a non-pending request matches the
  existing 409 "already pending" on create. The notification rows are written in the same transaction as the decision
  (atomic). The email is published only after commit (`dispatch` after_commit).
- **AuthZ:** unchanged. The student is scoped to their own record (404 otherwise). The trainer is scoped to the
  current `batch.trainer_id`, so a reassigned trainer's successor can review and the old trainer gets 403. it_admin
  can review any request.
- **Security:** notification text holds only names, dates and statuses (no secrets). React escapes the comment and
  reason. No new routes, so RBAC route inventory is unchanged. CSRF is handled by the existing same-origin cookie
  proxy. No new logging of personal data.
- **Frontend:** reuses `.table`, `.table-wrap`, `.action-card`, `.form`, `.btn`, `.form-error/.form-message`. The table
  uses `.table.stack` with `data-label` for phones. Buttons have accessible names that include the date. Focus moves
  to the inline form and feedback is announced through role=status/alert.

## Acceptance → tests
| AC | Test |
|---|---|
| 1 No UUID for the student | vitest `AttendanceCorrectionPanel` (row button, payload); pytest portal columns; Playwright student flow |
| 2 Trainer in-app (+email) on new request | pytest: Notification for the trainer + email delivery queued; no trainer → it_admin |
| 3 Approve updates attendance + notifies student | pytest approve/reject; vitest trainer queue buttons; Playwright trainer approves |
| 4 Malformed review → 422 | pytest (bad status, missing status, notes too long) |
| Neg: duplicate pending refused | existing rule, pytest |
| Neg: other batch's trainer | pytest 403 |
| Neg: re-review | pytest 409 |

## Plan
1. pytest RED: review schema 422, 409 re-review, notifications on request/decision, the no-trainer route, the
   `correction_pending` flag, and the portal columns.
2. GREEN: schema in `schemas.py`; route changes + a small `_notify_correction` helper in `workflows.py`; `portal.py`.
3. vitest RED → GREEN: `AttendanceCorrectionPanel`, and the `TeacherWorkspaceActions` queue; `WorkflowPanel` wiring.
4. Playwright e2e `nehn-023-attendance-correction.spec.ts` (student requests → trainer approves).
5. Docs: backlog status line, and a DEC-SCOPE entry.
