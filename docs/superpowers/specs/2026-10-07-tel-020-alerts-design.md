# tel-020 — Telecaller alerts & notifications (design)

- **Feature:** tel-020 (`docs/delivery/TELECALLER_CRM_BACKLOG.md` → tel-020; EVID-019 §20 lines 638–650; T14)
- **Decision:** `DEC-SCOPE-107` (AL1–AL4 owner answers 2026-10-07, `EXPLICIT_APPROVAL`; defaults AL5–AL12 below)
- **Numbers:** migration `0098_tel_settings` (after `0097_lead_message_email`), API contract §12AA, RBAC §2.33
- **Dependencies (all merged):** tel-007 (PR #90), tel-011 (PR #100), tel-016 (PR #103), tel-018 (PR #114)

## 1. Intent

§20 says the CRM "should automatically notify the telecaller" of nine things. Success means that a telecaller gets each alert once, both in-app and
by email, with a link to the lead or list it concerns. Managers set the two thresholds per team. Nothing is sent for a write that rolled back,
and a missed beat run catches up without duplicates.

## 2. Owner answers (AL1–AL4) and defaults (AL5–AL12)

| # | Decision |
|---|---|
| AL1 | Default thresholds per team: **Lead Not Contacted 24 h**, **Hot Lead Pending 4 h**. Whole hours 1–168, set by a manager |
| AL2 | **Per alert, in-app + email** (as bdm-012). No digest |
| AL3 | **No quiet hours** |
| AL4 | **Follow-up Due** fires in the 15 min before the due time. **Missed Follow-up** fires if it is still open 1 h after the due time. **Appointment Tomorrow** fires once, from 18:00 IST the day before |
| AL5 | The recipient is always the lead's telecaller (`enquiries.telecaller_user_id`), and only if that user is an **active** `telecaller` (backlog negative scenario). Event alerts skip the case where the actor is the recipient |
| AL6 | Once-only delivery reuses `notifications.dedupe_key` (bdm-012 R1 / AGN-017 N6): key `tel020:{kind}:{object}:{user}:{fire_key}`, where `fire_key` is the event time the alert is about. A new due time, a new appointment time, a new call or a new stage therefore re-arms the alert (backlog edge case). This replaces the backlog's proposed `tel_alert_log` table, because the unique partial index already exists |
| AL7 | Event alerts (New Lead Assigned, Counselor Appointment Completed, Lead Returned) are written in the caller's transaction, with no dedupe key. A rolled-back write leaves nothing, and the outbox publishes only after commit (AC3) |
| AL8 | **Lead Not Contacted:** the telecaller's own open lead (not handed over) still in Assigned or First Call Pending (tel-021 `FIRST_CALL`, never connected), with `stage_changed_at` at least the team's `not_contacted_hours` ago. `fire_key` = `stage_changed_at` |
| AL9 | **Hot Lead Pending:** own open hot lead (not handed over, not closed) with no call logged in the team's `hot_pending_hours`. The reference time is the latest `lead_calls.occurred_at`, or the lead's `created_at` if there is no call. `fire_key` = that reference time |
| AL10 | Catch-up windows: Due covers `now − 1 h < due ≤ now + 15 min`. Missed covers `now − 25 h < due ≤ now − 1 h`, so the first run never alerts about follow-ups older than a day. Appointment in 1 Hour covers `now < start ≤ now + 1 h`. Tomorrow covers the next IST day, from 18:00 IST |
| AL11 | Any `telecaller_manager` (and `super_admin`) reads and sets the thresholds of both teams, as tel-022 G3 does for team targets. A change applies from the next beat run (AC4). Audited `tel.settings.update` with the old and new values |
| AL12 | tel-021's B9 "Overdue" uses the team's `not_contacted_hours` in place of the fixed 24 h (DB1 said "until tel-020"); its stage filter is unchanged |

## 3. Architecture

```
write paths (route owns txn)                    beat every 15 min (Celery)
 lead_distribution.assign ─┐                     send_telecaller_alerts_task
 lead appointment complete ├─► telecaller_alerts.event(...)    │
 lead_handover.return_lead ┘     Notification + queue_deliveries ▼
                                                 telecaller_alerts.send_telecaller_alerts(db, now)
                                                   6 time-based kinds, keyset chunks of 200,
                                                   savepoint + INSERT .. ON CONFLICT (dedupe_key) DO NOTHING
                                                   → queue_deliveries(channels=["email"], context kind="tel_alert")
 notifications/delivery._send_email: kind "tel_alert" → mailer.send_bdm_reminder_email (generic SMTP with links)
```

- `app/services/telecaller_alerts.py` (new): `Alert` dataclass; the builders; `notify_assigned`, `notify_appointment_completed`,
  `notify_returned`; `send_telecaller_alerts(db, now)`; `run_telecaller_alerts()`; `thresholds(db)`.
- `app/models.py`: `TelSetting` (`tel_settings`: `team` PK `it|overseas`, `not_contacted_hours`, `hot_pending_hours` CHECK 1–168,
  `updated_by_user_id` nullable FK, timestamps). Migration `0098` creates it and seeds both teams with 24 / 4.
- `app/worker.py`: `send_telecaller_alerts_task` plus the beat entry `tel020-alerts` (900 s), through `_run_with_fresh_pool`.
- `app/api/telecaller_settings.py` (new): `GET /telecaller/settings`, `PUT /telecaller/settings/{team}`.
- Hooks: `lead_distribution.assign` (only when the telecaller changes), `api/lead_appointments._act` (action `complete`),
  `lead_handover.return_lead`.

### Bodies and links (security)

The title is the kind's label. The body carries the lead's name (cleaned and capped), its Lead ID and the relevant time in IST. It never
includes a phone number, an email address or free text such as a return reason or follow-up notes. The links are app paths with no token:
`/telecaller/leads/{id}` for lead-level alerts, `/telecaller/follow-ups` for follow-up alerts. Logs carry counts and ids only.

## 4. API (§12AA)

| Method | Path | Who | Result |
|---|---|---|---|
| GET | `/telecaller/settings` | `telecaller_manager`, `super_admin` | `{items: [{team, not_contacted_hours, hot_pending_hours, updated_at, updated_by: {id, full_name} \| null}]}` (both teams, a seeded row) |
| PUT | `/telecaller/settings/{team}` | same | body `{not_contacted_hours, hot_pending_hours}` (int 1–168, extra fields refused) → 200 item; unknown team 404; bad value 422 |

Every other role gets 403, and an anonymous caller gets 401. The PUT is an idempotent upsert, so it returns 200.

## 5. Frontend

- Telecaller: `/telecaller/notifications` uses the shared feed (`/workflows/notifications`) and `SchoolNotificationList readBeforeOpen`,
  as the BDM page does. A Notifications nav item with an unread badge comes from a `telecallerNav()` helper (the `bdmNav` pattern) on every
  telecaller page.
- Manager: `/telecaller/manager/alerts` ("Alert settings"). `TelecallerAlertSettingsPanel` shows one card per team with two number inputs
  and a Save button, along with loading, error and saved states and the last-updated note.

## 6. Acceptance criteria → tests

| AC | Test |
|---|---|
| AC1 each kind fires once | service tests: every kind creates one notification + one email delivery; a second run creates none |
| AC2 missed run catches up | a run 50 min late still sends Due; a Missed within 25 h is sent; nothing twice |
| AC3 rolled-back write sends nothing | assign / complete / return then rollback → no notification, no delivery |
| AC4 thresholds apply next run | PUT 2 h → a lead at 3 h alerts on the next run; at 24 h it didn't |
| Negatives | inactive telecaller gets none; handed-over lead gets no not-contacted / hot alert; actor = recipient gets none; telecaller / counselor PUT → 403 |
| Edge | rescheduled follow-up re-arms; a new call re-arms Hot Lead Pending |
| Browser | manager edits thresholds; telecaller sees a notice + badge, opens it to the lead |

## 7. Risks

- `lead_distribution.assign` is shared by intake, CSV import and manual assignment, and tel-025 (in flight) uses it too. The hook adds a
  notification only, inside the same transaction.
- Beat load: chunked keyset reads over the existing `ix_lead_follow_ups_open_due`, `ix_appointments_lead` and `ix_enquiries_telecaller_status`
  indexes.
- Volume: a CSV import of N leads sends N "New Lead Assigned" emails (AL2 accepted).
