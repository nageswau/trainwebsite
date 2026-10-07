# tel-016 — Counselor appointment booking for leads (design)

**Status:** approved in session 2026-10-07. Owner answers AP1–AP4 are `EXPLICIT_APPROVAL`; AP5–AP14 are defaults recorded in
`DEC-SCOPE-095`. **Evidence:** `EVID-019` §9 (L332–L384); backlog `docs/delivery/TELECALLER_CRM_BACKLOG.md` tel-016; T10 (extend
`appointments` with a lead link, booked straight to the counselor). **Dependencies (all merged):** tel-004 (stage engine), tel-008 (lead
workspace), tel-017 (IT counselors).
**Numbers (re-check at merge):** migration `0091_lead_appointments` (after tel-011's `0090_lead_follow_ups`), `DEC-SCOPE-095`, API §12Q,
RBAC §2.23.

## 1. Owner answers (2026-10-07)

| # | Question | Answer |
|---|---|---|
| AP1 | Q-11 clash, length | **Refuse with 409** when the time overlaps any open appointment of that counselor, lead or student. Every booking lasts a **fixed 60 minutes**. No override |
| AP2 | Who acts after booking | **Counselor** (the assigned one): confirm, complete, no-show, reschedule, cancel. **The lead's telecaller:** reschedule and cancel while the appointment is open. **Managers and super_admin:** read only |
| AP3 | Stage on no-show/cancel | The lead returns to **Follow-up** (system event `appointment_released`) if it is still at Counselling Scheduled. A reschedule never moves the stage |
| AP4 | Counselors and types (Q-12) | **Any active counselor in the lead's division**, with no application needed. Booking is **not** a handover (`owner_id` untouched; tel-018). Types: IT lead → Career counselling, IT course counselling; overseas lead → Career, Overseas, University counselling |

Defaults:
- **AP5:** a lead has at most one open appointment (`scheduled`, `confirmed`, `rescheduled`). A second booking is 409, backed by a partial unique index.
- **AP6:** `appointment_code` = `CAP-000001` from `appointment_code_seq`, given to lead bookings only. Legacy student rows stay NULL; the code is unique.
- **AP7:** mode is one of the student flow's own values `Online` / `Phone` / `In person`. `meeting_link` (http/https URL, ≤ 500) and `location` (≤ 200) are both optional. `purpose` ≤ 500 and `remarks` ≤ 1000 are optional.
- **AP8:** a booking or reschedule must be in the future (422) and within 366 days (422).
- **AP9:** complete and no-show are allowed only after the start time (422). A cancel needs a reason (≤ 500); a reschedule's reason is optional.
- **AP10:** history is the append-only `appointment_events` table (bdm-006 pattern). A reschedule keeps the old and new times.
- **AP11:** a telecaller can't book on a handed-over lead (403, D1) or a closed lead (409). Booking is allowed at any open stage, but only stages up to Follow-up move (tel-004 event from-set).
- **AP12:** legacy student statuses are left as stored, with no CHECK on `status`. `PATCH /overseas/appointments/{id}` returns 404 for a lead appointment, so it can't bypass the lifecycle. The student create flow is unchanged.
- **AP13:** the counselor sees a lead booking's lead name, Lead ID, mobile and email. These are needed to hold the session; the counselor gets no other access to the lead.
- **AP14:** `Appointments` is added to the IT counselor nav, and the overseas counselor's existing Appointments page gains a "Lead appointments" panel above the unchanged student table.

## 2. Data (migration 0091)

`appointments` gains these columns (all nullable, so no existing row changes):
- `lead_id` → `enquiries.id` (RESTRICT)
- `appointment_code` (String 20, unique)
- `purpose` (500), `meeting_link` (500), `location` (200), `remarks` (1000)
- `booked_by_user_id` → `users.id`
- `duration_minutes` (Integer, default 60, NOT NULL with server default 60)

CHECK constraints and indexes:
- CHECK `ck_appointments_subject`: `student_id IS NOT NULL OR lead_id IS NOT NULL`.
- Index `ix_appointments_staff_scheduled` on `(staff_id, scheduled_at)`.
- Index `ix_appointments_lead` on `(lead_id)`.
- Partial unique index `uq_appointments_lead_open` on `(lead_id)` WHERE `lead_id IS NOT NULL AND status IN ('scheduled','confirmed','rescheduled')`.

New sequence `appointment_code_seq`.

New table `appointment_events`:
- `id`, `appointment_id` (FK, RESTRICT), `actor_user_id`, `from_status` (NULL on create), `to_status`, `old_scheduled_at`, `new_scheduled_at`, `reason` (500), `created_at`, and `position` (identity, orders rows).
- Index on `(appointment_id, position)`.

The upgrade is guarded the way 0074 and 0089 are (0001 builds from current models). Downgrade drops the new objects; it is refused (`RuntimeError`) if lead appointments exist, so lead rows are never silently orphaned. The CHECK must hold for existing rows: every legacy row has a `student_id` (the seed and the API both require one); adding the CHECK would fail on any row without one, and the migration test upgrades over a legacy row.

`lead_stages.EVENTS` gains `appointment_released: ({counselling_scheduled}, follow_up)`.

## 3. API (§12Q)

All writes run in a single transaction. The lock order is lead row → counselor user row → appointment row, so concurrent bookings of one counselor serialise and the clash check can't race.

| Route | Who | Behaviour |
|---|---|---|
| `GET /telecaller/leads/{id}/appointment-options` | telecaller / manager / super_admin, lead in scope | `{types: [{key,label}], counselors: [{id, full_name}], modes, duration_minutes: 60}`. Counselors are the active counselors of the lead's division, ordered by name |
| `GET /telecaller/leads/{id}/appointments` | same | The lead's appointments, newest first, each with its events and `permissions` |
| `POST /telecaller/leads/{id}/appointments` | `telecaller` only (a manager gets 403) | Body `{appointment_type, counselor_id, scheduled_at, mode, meeting_link?, location?, purpose?, remarks?}`. Checks in order: 404 scope; 403 handed over; 409 closed; 422 type not for the lead's division, counselor not an active counselor of the lead's division, past/horizon; 409 lead already has an open appointment; 409 clash `{message, code:"counselor_busy", matches}`. On success: 201 with the appointment, stage event `appointment_booked`, event row `from NULL → scheduled`, audit `lead_appointment.create` |
| `GET /counselor/appointments?status=&limit=&offset=` | `counselor` (IT or overseas) | Their own lead appointments, soonest first (open first, then the rest by time desc), with the lead summary (AP13) and `permissions`. Other roles get 403 |
| `POST /lead-appointments/{id}/confirm` | counselor (owner) | `scheduled`/`rescheduled` → `confirmed` |
| `POST /lead-appointments/{id}/complete` | counselor | open → `completed`, after the start time. Stage event `appointment_completed` |
| `POST /lead-appointments/{id}/no-show` | counselor | open → `no_show`, after the start time. Stage event `appointment_released` |
| `POST /lead-appointments/{id}/cancel` `{reason}` | counselor, or the lead's telecaller (not handed over) | open → `cancelled`. Stage event `appointment_released` |
| `POST /lead-appointments/{id}/reschedule` `{scheduled_at, reason?}` | counselor, or the lead's telecaller | open → `rescheduled` with the new time. Future, horizon and clash checks (excluding itself). The event keeps old and new |

Scope for `/lead-appointments/{id}`: the counselor where `staff_id` = them, or the telecaller where the lead's `telecaller_user_id` = them. Anything else is 404, which covers IDOR, managers and other roles. An action the role may not take is 403. A finished appointment is 409 ("Appointment is already completed"). Every write adds an audit row (`lead_appointment.<action>`, ids and statuses only) and an event row. Logs carry ids only.

The response for every write and each list row is: `{id, code, lead: {id, lead_code, name, phone, email}, appointment_type, type_label, counselor: {id, full_name}, booked_by: {id, full_name}, scheduled_at, duration_minutes, mode, meeting_link, location, purpose, remarks, status, events: [...], permissions: {can_confirm, can_complete, can_no_show, can_cancel, can_reschedule}}`.

`PATCH /overseas/appointments/{id}` on a row with `lead_id` returns 404 (AP12).

The portal changes:
- `_it_counselor` accepts `appointments` and returns a header-only payload.
- The overseas counselor `appointments` payload is unchanged.
- The student portal filters by `student_id`, so lead rows never appear there.

## 4. Frontend

- `lib/leadAppointments.ts` holds the types, labels, URLs and the IST helpers (reusing `istInputToIso` / `isoToIstInput` from `bdmAppointments`).
- `LeadAppointmentsSection` sits on the lead detail (telecaller and manager pages). It shows the lead's appointments, including the history and the reschedule and cancel actions where `permissions` allow. A "Book counselling" button opens `BookCounsellingForm`, which is hidden when the lead is read-only, closed or already has an open appointment, or when the viewer is a manager. The form has type, counselor, date and time (datetime-local, IST), mode, link, location, purpose and remarks. Field errors are inline and focused; a 409 clash lists the clashing times; the page shows loading and empty states. On success the stage line updates (the API returns the lead's stage) and the activity list reloads.
- `CounselorAppointmentsPanel` is rendered by `PortalPage` for `it/counselor` and `overseas/counselor` on the `appointments` section. The overseas page keeps the existing table below it. Each row has Confirm, Complete, No-show, Reschedule and Cancel per `permissions`; a reason dialog appears for cancel; there is a status filter and loading, empty and error states.
- The `it/counselor` nav gains `appointments`.

## 5. Security

- Scope always comes from the session.
- An out-of-scope id is 404, the same as a missing one.
- An action the role may not take is 403.
- The link must be `http(s)://`, so a `javascript:` URL is refused with 422, and it is rendered with `rel="noopener noreferrer"`.
- Text fields refuse control characters (the existing `_clean` idiom in schemas).
- Audit rows and logs hold no PII.
- The counselor sees lead contact details only through their own appointments.

## 6. Tests

- **Backend** `test_tel_016_*`:
  - migration (CHECK, indexes, backfill-safety, downgrade guard)
  - booking happy path with no student account (AC1)
  - stage moves on book, complete, no-show and cancel (AC2, AP3)
  - past → 422 (AC3)
  - IT lead with an overseas counselor → 422 (AC4)
  - type/division mismatch
  - clash 409, including against a student appointment
  - second open appointment 409
  - handed-over 403 and closed 409
  - manager book 403
  - counselor A acting on B's appointment → 404 (backlog: "403"; out of scope reads as missing, the project rule)
  - telecaller confirm → 403
  - complete before start → 422
  - finished → 409
  - reschedule history
  - the legacy PATCH on a lead appointment → 404
  - the IT counselor portal appointments section
- **Regression:** `test_cns_001_counselor_workspace.py`, `test_tel_017_it_counselor.py`, `test_tel_004*`, `test_tel_008*` and the overseas appointment tests (AC5).
- **Web:** vitest for the form and panel helpers. Playwright `tel-016` books from the lead detail as a telecaller, then confirms and completes as the counselor.
