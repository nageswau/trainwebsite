# hrc-028 — Interview model completion, cancellation, link history and calendar (design)

**Decision:** `DEC-SCOPE-398` (builder's calls, `NEEDS_CONFIRMATION`). **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` hrc-028
(PDF §10.1 interview fields, §10.2 sync rules, §16 calendar, §17 QA #13/#14; PDF classified `UNVERIFIED`). Scope approved by the owner
2026-11-01 (backlog Q-00); the owner said to proceed with the recommended answers. Dependency hrc-004 (`DEC-SCOPE-376`) merged.

## Intent
A recruiter records everything a candidate needs to attend an interview (round number, end time, the candidate's time zone, platform,
phone details, instructions, documents to bring), can cancel an interview with a reason, and can replace a meeting link without the old
link ever reaching the candidate again. The candidate gets a calendar invite on schedule, reschedule, detail change and cancel, and sees
the times in their own time zone.

## Builder's calls (I1–I10)
- **I1 Fields** on `interviews` (all nullable unless said): `round_number` (1–20), `ends_at` (after `scheduled_at`, at most 12 h later),
  `time_zone` (IANA name, NOT NULL, default `Asia/Kolkata`; any name `zoneinfo` knows), `platform` (`google_meet`, `microsoft_teams`,
  `zoom`, `zoho_meeting`, `other`), `phone_details` (≤200), `instructions` (≤2000, multi-line), `documents_required` (≤1000, multi-line),
  `cancel_reason` (≤500), `calendar_sequence` (NOT NULL, default 0 — the iCalendar SEQUENCE). Create and PATCH take the new fields;
  legacy/employer creators keep their payloads (defaults apply).
- **I2 Times.** Stored in UTC (as today). Recruiters keep entering times in IST (their working zone); `time_zone` is the zone the
  candidate reads them in — the notices, the invite text and the student portal show both start and end in that zone with its UTC offset.
  A reschedule keeps the duration (`ends_at` moves with the start). Rescheduling into the past stays 422 (rec-020 IV4).
- **I3 Cancel.** New status `cancelled` (CHECK: cancelled ⇔ `cancel_reason` set). `POST /recruiter/interviews/{id}/cancel
  {reason (required, ≤500), notify}` from Scheduled, Confirmed, Rescheduled or On Hold; anything else 409. Written as a `status` event
  (note = reason) so history and the candidate timeline read it unchanged. A cancelled interview is final: no edit, reschedule, status or
  feedback; it leaves the clash check (not open) and lists under Closed. The application does not move (another round can be scheduled).
- **I4 Link history.** A PATCH that changes `meeting_url` or `location` writes an `InterviewEvent` `details` row with the old and new
  values (new columns `old_meeting_url`, `new_meeting_url`, `old_location`, `new_location`). The audit keeps redacting the URL (hrc-004);
  the event is the internal record. Staff history reads "Meeting link replaced" / "Location changed"; no candidate surface reads events,
  and every candidate surface shows only the current link (none once cancelled).
- **I5 Notices.** Schedule, reschedule, cancel and a PATCH that changes a candidate-visible detail (round, round number, mode, platform,
  link, location, phone, instructions, documents, end time, time zone, interviewer) notify the candidate and the chosen contact when
  `notify` (default true) — the rec-020 IV9 channels (student: in-app + email delivery; external candidate and contact: queued recruiter
  email). PATCH replies with the interview as before plus a `notifications` key when it notified. Interviewers become users only in
  hrc-029, so they are not notified here.
- **I6 Calendar invite.** Every notice carries an `.ics` (`calendar_ics`, UID `interview-<id>@edusphere`, METHOD REQUEST / CANCEL,
  SEQUENCE bumped on every change after the first invite, end = `ends_at` or start + 60 min, LOCATION = link, else location, else mode).
  Built when queued (a later change never alters a queued email). Student: delivery context `interview_invite` (the ccrm-038 mailer
  path). Email rows: new nullable `recruiter_messages.calendar_ics`, attached by the recruiter-email worker.
- **I7 Student portal** (`/it/student/interview-schedule`): Round, Role, Company, When (in the interview's zone), Mode, Meeting (an Open
  link only while not cancelled), Details (platform, phone, location, instructions, documents), Status — "Cancelled — <reason>";
  decisions still read Completed (hrc-001 H3).
- **I8 Recruiter UI.** The schedule/edit form gains the fields (time zone as a select of common zones plus the stored one); the item shows
  them, the candidate-zone time when it differs from IST, a Cancel action with a required reason, and the new history lines.
- **I9 Auth.** Unchanged: rec-017 writers (`rec`, `super`) write, out of scope 404, other roles 403 (RBAC §2.291 adds the cancel row).
- **I10 Not built:** auto-creating Google/Zoho meetings (Q-29), interviewer users and their notices (hrc-029), result release (hrc-030),
  a candidate-chosen time zone on the profile.

## Numbering
Migration `0274_interview_completion` (after `0273_candidate_privacy`); API §12KQ; RBAC §2.291.

## Acceptance criteria
1. After a link replacement the portal shows only the new link; the old one is kept on a `details` event.
2. A cancel shows "Cancelled — reason" in the portal and the recruiter item and notifies (in-app / email) with a CANCEL invite.
3. Schedule, reschedule, detail change and cancel notices carry an `.ics`.
4. A non-IST candidate (e.g. `Asia/Dubai`) reads the time in their zone (notice, invite text, portal).
5. Rescheduling into the past is 422; cancelling a decided or cancelled interview is 409; a reason is required (422).
6. Matrix: cancel is 200 for writers, 403 for readers, 404 out of scope.

## Plan (TDD, one slice each)
1. Migration + models + checks (migration test; narrow rec-020's frozen-copy test).
2. Schemas + service: fields on create/update, `details` events, cancel, sequence; recruiter route `cancel`; reschedule keeps duration.
3. Notices + ICS (student context, recruiter message column + worker attach, mailer).
4. Student portal section.
5. Web: types, form fields, item (cancel form, facts, history), timeline title; vitest.
6. e2e spec hrc-028; docs (register, API, RBAC, RTM, backlog status).
