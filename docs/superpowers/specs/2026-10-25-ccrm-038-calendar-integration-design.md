# ccrm-038 — Calendar integration, phase 1 (design)

**Feature:** `ccrm-038` (docs/delivery/COUNSELOR_CRM_BACKLOG.md, CC6). **Decision:** DEC-SCOPE-271. **API:** §12FX. **RBAC:** §2.185.
**Migration:** `0190_calendar_feeds`. **Dependencies:** none (backlog).

## Requirement (backlog, UNVERIFIED spec §11 "email, calendar"; Phase 6)

> phase 1: `.ics` invite attached to appointment emails (student and counselor) and a per-counselor read-only iCal feed of
> appointments and visa appointments. Phase 2 (Google/Outlook two-way sync) only after a provider decision.
> Security: feed URL is a revocable secret token.

## Discovery facts

- No appointment email exists today. Overseas student appointments: `POST/PATCH /workflows/overseas/appointments` (workflows.py).
  Lead appointments (tel-016): booked by the telecaller, lifecycle in `api/lead_appointments.py::_act`.
- Notification email = `Notification` + `NotificationDelivery` (context dict) -> worker `notifications/delivery.py::_send_email`
  -> `mailer`. The Zoho Mail API transport (`zoho_mail.payload_from_message`, production) sends no attachments today.
- Visa appointment = `visa_cases.appointment_date` (+ `appointment_place`), date only. Counselor of an application =
  `coalesce(application.counselor_id, direct student's csc-001 counselor)` (ccrm-030 RM4).
- The browser reaches the API through the web proxy `/api/v1/...`, so the feed URL is `FRONTEND_URL/api/v1/calendar/feeds/<token>.ics`.

## Builder's defaults (owner pre-authorised recommended answers; NEEDS_CONFIRMATION)

- **CA1 Which emails.** An overseas appointment that is **booked**, **re-timed** or **cancelled** sends an in-app notification plus an
  email with an `.ics` attachment (`METHOD:REQUEST`, or `METHOD:CANCEL` for a cancellation) to:
  the student and the assigned counselor (student appointments); the assigned counselor (lead appointments; the lead is not a user and
  lead email waits for ccrm-040 consent). The person who made the change is included: the invite is for their own calendar.
  Confirm / complete / no-show and other status edits send nothing.
- **CA2 Invite content.** UID `appointment-<id>@edusphere`, `SEQUENCE` = `appointments.calendar_sequence` (new column, +1 per re-time
  or cancel), UTC start, end = start + `duration_minutes`, summary "Counselling appointment — EduSphere" (+ code), location = meeting
  link / location / mode. Never the purpose, remarks or outcome notes. The `.ics` text is built when the change is committed and kept
  in the delivery context, so a later change cannot alter an earlier email.
- **CA3 Transports.** SMTP: a `text/calendar; method=...` attachment `invite.ics`. Zoho Mail API: the attachment is uploaded first
  (`POST /api/accounts/{id}/messages/attachments`) and referenced in the send (live Zoho check NEEDS_CONFIRMATION).
- **CA4 Feed token.** One active feed per overseas counselor. 32 random bytes (url-safe); only the SHA-256 is stored
  (`calendar_feeds.token_hash`). The full URL is shown once, on create/regenerate; regenerate replaces it, revoke deletes it.
  Both are audited (no token in the audit or log).
- **CA5 Feed content.** The counselor's own appointments (staff = counselor, not cancelled) and the visa appointments of the
  applications they counsel (CA-RM4 rule, application not withdrawn), from 90 days ago onward, at most 500 events. Visa
  appointments are all-day events. Event text = type + student/lead name + code; never refusal reason, notes or remarks.
- **CA6 Feed serving.** `GET /calendar/feeds/{token}.ics` is public (the token is the credential), `text/calendar`,
  `Cache-Control: private, no-store`. An unknown token, an inactive user, or a user who is no longer an overseas counselor -> 404.
- **CA7 Who.** Only an overseas counselor manages a feed (`/counselor/calendar-feed`); everyone else 403.
- **CA8 Phase 2** (two-way Google/Outlook/Zoho sync) is out: it needs DEC provider selection.

## Design

- `services/calendar_ics.py` — pure: `event(...)`, `all_day_event(...)`, `calendar(events, method=None)` (RFC 5545 escaping,
  CRLF, 75-octet folding). No new dependency.
- `services/appointment_invites.py` — `queue(db, appt, method)`: builds the `.ics`, the recipients (CA1), one `Notification` per
  recipient and `queue_deliveries(..., channels=["email"], context={"kind": "appointment_invite", "ics": ..., "method": ...})`.
  Called inside the route's transaction (the publish happens after the root commit).
- `notifications/delivery.py` — the `appointment_invite` kind passes the `.ics` to `send_generic_notification_email(ics=..., ics_method=...)`.
- `mailer.send_generic_notification_email` — optional `ics` attachment. `zoho_mail.send` uploads non-inline attachments.
- `services/calendar_feeds.py` + `api/calendar_feeds.py` — create/rotate, status, revoke, the feed body.
- Web: `/overseas/counselor/calendar` page + `CounselorCalendarFeed` client component (status, create/regenerate with confirm,
  copy URL, revoke with confirm); nav link "Calendar".

## Security review

- Token: 256-bit random, hash-only at rest, constant-time lookup by hash (unique index), revocable, never logged or audited.
- IDOR: the feed has no ids in the URL; management routes act on the session user only.
- Public route leaks: minimal event text (CA5); no-store; 404 for every refusal (no oracle).
- Injection: every ICS text value is escaped (`\\ ; , \n`) and CR/LF stripped, so a crafted name cannot add properties.
- No rate limit is added: guessing a 256-bit token is infeasible (no repo-wide limiter exists).

## Tests

pytest `tests/test_ccrm_038_calendar.py`: ICS escaping/folding; invites queued on book/re-time/cancel (student + lead) with recipients,
sequence and method; no invite on status-only edits; SMTP attachment; Zoho upload + reference; feed create/rotate/revoke/RBAC;
feed content and scope (other counselor's rows absent, cancelled absent, visa all-day, revoked/deactivated -> 404).
vitest component test; Playwright e2e for the page.
