# nehn-037 part 4 — Admission interviews (design)

Backlog: `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-037` part 4 (parts 1, 2, 3 and 5 are superseded by ccrm-020,
ccrm-018/019, ccrm-013 and ccrm-010). Source §19 L540 "Schedule/track interviews or appointments", §17 L468 "View interview/appointment
information" (`UNVERIFIED`). The tracker's open question "Are admission interviews needed?" has no owner answer; the owner asked to
proceed with recommended answers, so every I-call below is a recommended default, `NEEDS_CONFIRMATION`, recorded as `DEC-SCOPE-296`.
Dependencies: none open (nehn-003 is merged and is not used: an interview carries no upload).

## Intent

Universities interview some applicants before an offer. The counselor needs to record each admission interview (when, how, where) and
its result, and the student needs to see it on their own page — with the result once the interview has happened (AC3). Not to be
confused with the recruitment `interviews` table (rec-020, IT placements) or the visa case's `interview_date` (agency-only).

## What is built

- **Table** `application_interviews` (migration `0203_application_interviews`, additive): `id`, `application_id` (FK
  `overseas_applications`, cascade), `scheduled_at` (timestamptz), `mode` (`online` / `in_person` / `phone`), `location` (≤300,
  optional: the meeting link or the address), `student_note` (≤500, optional, shown to the student), `outcome` (null = awaiting,
  `passed` / `not_successful` / `cancelled`), `created_by_id`, `updated_by_id`, timestamps. CHECKs on mode and outcome. Index on
  `(application_id, scheduled_at)`.
- **Routes** under `/workflows/overseas/applications` (new router `app/api/application_interviews.py`):
  - `GET /{id}/interviews` — the offers' readers: counselor (own), Overseas Admin, the student (own), the agency (its applications);
    scope through `_assigned_application`.
  - `POST /{id}/interviews` (201) and `PATCH /{id}/interviews/{interview_id}` — counselor (own applications, direct **and agency**,
    CC4) or Overseas Admin, through the offers' write entry (scope, row lock, swapped-counselor re-check, closed → 409, archived agency
    record → 409). An interview of another application is 404.
- **Student read** `GET /workflows/overseas/student/interviews` — every interview on the student's own applications, newest first,
  with the university name.
- **FE**: counselor "Evaluate Applications" card gets an "Interviews" toggle opening `ApplicationInterviewsPanel` (list, add, edit,
  record outcome). Student `/overseas/student/applications` gets a "My interviews" card (`StudentInterviewsPanel`).

## Calls (I1–I9, recommended defaults, `NEEDS_CONFIRMATION`)

- **I1 Needed:** yes — built as a small, separate entity; it moves no stage, so removing it later touches nothing else.
- **I2 Fields:** date-time, mode (online / in person / phone), optional link-or-address, optional note for the student. No panel or
  interviewer names (not in the source).
- **I3 Outcome after the date (AC3):** `passed` and `not_successful` are accepted only once `scheduled_at` is in the past (server
  clock); `cancelled` any time. Moving a decided interview into the future is refused (422). Clearing the outcome (null) is allowed.
- **I4 Several per application:** yes (rounds), at most 20 per application (422 beyond).
- **I5 No delete:** a mistaken or called-off interview is marked `cancelled`; the audit keeps every change.
- **I6 Closed applications:** withdrawn or terminal applications refuse writes (409, the offers' rule); on hold allows them (no stage
  move). Reads always work.
- **I7 Notices (CC5):** the student (with a login) is told when an interview is added, rescheduled (time, mode or place changed) or its
  outcome changes; on an agency application the agency gets "Application details updated" (no values). Every write is audited with the
  changed fields.
- **I8 Visibility:** the student sees everything on the entry (there is no internal field; internal notes stay in ccrm-010). The
  counselor sees who recorded it. The stage and sub-status are untouched.
- **I9 Times:** `scheduled_at` must carry an offset and fall in 2000–2100; the browser sends the viewer's local time as an instant and
  shows it back in the viewer's zone (`LocalTime`).

## Concurrency and errors

Writes lock the application row, so two saves on one application queue (last write wins, both audited). A PATCH that changes nothing
answers 200 with `changed: false` and writes nothing (a retry is safe). Unknown mode/outcome or a bad `location` length is 422.

## Non-goals

No calendar invite or email beyond the in-app notice; no reminders; no agent UI (the agency can read via the API); no change to the stage
machine, the recruitment interviews, the visa case or appointments.

## Tests

API: role/scope (other counselor 403, agent write 403, admin ok, agency app ok for counselor, student reads own only, other student 403),
outcome-after-date rule, cancelled any time, reschedule into the future with an outcome → 422, 20-cap, closed application 409, unchanged
PATCH writes nothing, notices (student on add / reschedule / outcome; not on a note-only change), audit, foreign interview 404. Migration
upgrade/downgrade. Web: component tests for both panels. Playwright: counselor records an interview and its outcome; the student sees it.
