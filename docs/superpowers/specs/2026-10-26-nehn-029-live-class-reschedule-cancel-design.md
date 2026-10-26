# nehn-029 — Live class reschedule and cancel (design)

**Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-029` (§10 "Schedule/manage live classes", L217;
`UNVERIFIED` backlog). Decision: `DEC-SCOPE-286` (builder's defaults, owner pre-authorised recommended answers; `NEEDS_CONFIRMATION`).
Dependencies: none hard. Provider sync depends on the open Zoho live-class decisions (`PENDING_ZOHO_LIVE_CLASSES.md`), so this item
uses the backlog's own fallback: the trainer is warned to update the provider manually.

## Intent
Trainers manage live classes, not only create them: move a class (time, link, title) or cancel it with a reason. Students see the
change and are notified in-app and by email.

## Current state (verified)
- `POST/GET /communications/it/live-sessions`, `PATCH …/{id}/recording` (`app/api/communications.py`).
- `live_sessions.status` exists (default `scheduled`); `cancel_reason` does not → migration `0198_live_session_cancel_reason`.
- Attendance is per batch + date (`attendance.session_date`), not per live session.
- Notifications: `queue_deliveries` (in-app row + email, WhatsApp/SMS on opt-in) publishes to the Celery worker after commit.

## Design
### API (additive; no existing contract changes)
- `PATCH /communications/it/live-sessions/{session_id}` — body `LiveSessionUpdate {title?, starts_at?, ends_at?, meeting_url?}`
  (at least one field; `meeting_url` must be `http(s)://`). Naive datetimes take the batch timezone (as on create).
  - 404 unknown session; 403 role not trainer/it_admin/super_admin, or a trainer outside the session's batch.
  - 409 the session is cancelled; 409 the session has already started (`starts_at <= now`) — "Past sessions cannot be rescheduled".
  - 422 new `starts_at` in the past; 422 `ends_at <= starts_at` (merged values).
  - No actual change → 200, nothing notified or audited.
  - Change → every active-enrollment student gets a Notification ("Live class rescheduled" when the time moved, else
    "Live class updated") queued through `queue_deliveries`; audit `live_session.update` with the changed field names.
- `POST /communications/it/live-sessions/{session_id}/cancel` — body `LiveSessionCancel {reason: 3..500 chars, trimmed}`.
  - Same 404/403; 409 already cancelled; 409 already started.
  - Sets `status="cancelled"`, `cancel_reason`; notifies students ("Live class cancelled" + reason); audit `live_session.cancel`.
  - Response includes `attendance_records`: attendance already marked for that batch on the session's date (kept, never deleted),
    so the UI can warn.
- Both lock the row (`SELECT … FOR UPDATE`) so a double submit cannot notify twice or cancel twice.
- Provider: `google_meet`/`zoho_meeting` sessions get `sync_status="manual_update_required"` and a response `warning`
  ("Update or cancel the event in Google Meet/Zoho Meeting yourself…"); the local change always succeeds. `manual` sessions: no warning.
- `GET /communications/it/live-sessions` and the student course payload gain `cancel_reason` (additive).
- Attendance: `POST /workflows/it/trainer/attendance` returns 409 when the batch has live sessions on that date (batch timezone) and
  **all** of them are cancelled. A date with no live session, or with at least one non-cancelled session, is unchanged.

### UI
- New `LiveSessionManagePanel` on the trainer "Live sessions" page: lists upcoming scheduled sessions with **Reschedule** (title,
  start, end, link; prefilled) and **Cancel** (reason required) inline forms, shows the provider warning and the attendance warning,
  lists cancelled sessions with their reason. Loading / empty / error states; keyboard and screen-reader friendly (labels, `role=alert`).
- `LiveClassesPanel` (students and trainer dashboard): a cancelled session shows a "Cancelled" badge and the reason; no join button.
- Trainer portal table (`portal.py` live-sessions section): adds a Status column ("Cancelled — reason"); a cancelled row has no join link.

## Non-goals
Automatic provider (Google/Zoho) update or cancel calls; recurrence; reinstating a cancelled session; deleting attendance.

## Builder's calls (`NEEDS_CONFIRMATION`)
C1 no automatic provider sync (manual warning). C2 a session that has started can be neither rescheduled nor cancelled. C3 cancel keeps
already-marked attendance and warns. C4 attendance is refused only when every live session that day is cancelled. C5 it_admin and
super_admin may manage any session (mirrors the recording route); there is no admin UI page (API only). C6 any real change notifies.
