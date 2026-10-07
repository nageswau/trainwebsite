# tel-016 Lead Appointment Booking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, chosen by the owner's session instructions) to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a telecaller books a counselling appointment for a lead (no student account needed), and the counselor confirms, completes,
no-shows, reschedules or cancels it. The lead's stage follows these actions.

**Architecture:**
- Extend `appointments` with a lead link (T10).
- Put the rules in a new functions-only service, `services/lead_appointments.py`, following bdm-006's split: the service holds the rules, the route owns the transaction.
- Add new routes in `api/lead_appointments.py` (telecaller lead routes, the counselor list and the shared action routes).
- On the frontend, add a lead-detail section and a counselor panel. Both read their own API.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic + PostgreSQL; Next.js App Router + TypeScript; pytest; vitest; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-07-tel-016-lead-appointments-design.md`

## Global Constraints

- Migration `0091_lead_appointments`, revises `0089_lead_qualifications`. Re-chain at merge if tel-011's 0090 lands first.
- Register the decision as `DEC-SCOPE-095`, the API as §12Q and RBAC as §2.23. Re-check these numbers at merge.
- Lead appointment status values: `scheduled`, `confirmed`, `rescheduled`, `completed`, `cancelled`, `no_show`. Open = the first three.
- Mode values: `Online`, `Phone`, `In person`. Fixed duration: 60 minutes. Booking horizon: 366 days.
- Types by division:
  - `it` → `career_counselling`, `it_course_counselling`.
  - `overseas` → `career_counselling`, `overseas_counselling`, `university_counselling`.
- Code format: `CAP-` followed by 6 digits.
- An out-of-scope id is 404. An action the role may not take is 403. A finished appointment is 409.
- Logs and audit rows carry ids, statuses and times only.
- Do not change the shape or behaviour of `workflows.create_appointment` for students.

## Review Focus

1. Two telecallers book the same counselor at the same time. Expected: one gets 409 (the counselor row lock serialises the clash check).
2. A counselor reschedules onto their own student appointment. Expected: 409 clash (student rows count).
3. A booking at the exact boundary (11:00 directly after a 10:00–11:00 booking). Expected: no clash (half-open intervals).
4. The legacy overseas PATCH on a lead appointment id. Expected: 404 (it can't bypass the stage rules).
5. A `javascript:` meeting link. Expected: 422, and it never renders as an href.

---

### Task 1: Data — model, migration, stage event

**Files:**
- Modify: `apps/api/app/models.py` (`Appointment`, add `AppointmentEvent`, `APPOINTMENT_CODE_SEQ`, constants)
- Modify: `apps/api/app/lead_stages.py` (event `appointment_released`)
- Create: `apps/api/alembic/versions/0091_lead_appointments.py`
- Test: `apps/api/tests/test_tel_016_migration.py`

**Produces:**
- `LEAD_APPOINTMENT_OPEN = ("scheduled","confirmed","rescheduled")`
- `LEAD_APPOINTMENT_TYPES: dict[str, tuple[str, ...]]` (keyed by division)
- `LEAD_APPOINTMENT_TYPE_LABELS`
- `APPOINTMENT_MODES`
- `APPOINTMENT_CODE_SEQ`
- `Appointment.{lead_id, appointment_code, purpose, meeting_link, location, remarks, booked_by_user_id, duration_minutes}`
- `AppointmentEvent`

Steps:
- [ ] Write the migration test. It checks:
  - the columns, CHECK `ck_appointments_subject`, the indexes `ix_appointments_staff_scheduled`, `ix_appointments_lead` and `uq_appointments_lead_open`, the sequence and the `appointment_events` table all exist in the DB
  - the migration's frozen `OPEN` matches `LEAD_APPOINTMENT_OPEN`
  - `EVENTS["appointment_released"] == ({"counselling_scheduled"}, "follow_up")`
- [ ] Run it and confirm it fails.
- [ ] Implement the model, migration (guarded upgrade; downgrade refuses while lead rows exist) and lead_stages.
- [ ] Run `alembic upgrade head` and the test; confirm it passes.
- [ ] Commit.

### Task 2: Service + booking routes (telecaller)

**Files:**
- Create: `apps/api/app/services/lead_appointments.py`, `apps/api/app/api/lead_appointments.py`
- Modify: `apps/api/app/schemas.py` (`LeadAppointmentCreate`, `LeadAppointmentReschedule`, `LeadAppointmentCancel`), `apps/api/app/main.py` (register `lead_appointments.router`)
- Test: `apps/api/tests/test_tel_016_booking.py`, `apps/api/tests/tel016_helpers.py`

**Produces (service):**
- `db_now(db)`
- `types_for(division)`
- `async active_counselors(db, division)`
- `async lock_counselor(db, counselor_id, division) -> User`
- `async find_clashes(db, staff_id, start, minutes, exclude_id=None) -> list[dict]`
- `require_schedulable(start, now)`
- `async open_for_lead(db, lead_id)`
- `async next_code(db)`
- `record(db, appt, actor, from_status, to_status, old=None, new=None, reason=None)`
- `audit(db, user, action, appt_id, meta)`
- `permissions(user, appt, lead, now)`
- `async appointment_out(db, user, appt)`

**Routes:**
- `GET /telecaller/leads/{id}/appointment-options`
- `GET /telecaller/leads/{id}/appointments`
- `POST /telecaller/leads/{id}/appointments`

Tests (RED first):
- AC1: a lead without a student books → 201, `CAP-` code, stage `counselling_scheduled`, history event `appointment_booked`, one event row, an audit row.
- AC3: a past time → 422; beyond 366 days → 422.
- AC4: an IT lead with an overseas counselor → 422; an inactive counselor → 422; a non-counselor → 422.
- A type that doesn't fit the division (an IT lead with `university_counselling`) → 422.
- A clash with an open lead appointment → 409 `counselor_busy`; a clash with a student appointment → 409.
- Back-to-back (start = previous end) → 201.
- A second open booking on the same lead → 409.
- A handed-over lead → 403.
- A closed lead → 409.
- A manager posting → 403.
- Another telecaller's lead → 404.
- A `javascript:` link → 422.
- The options list returns only active same-division counselors and the division's types.

Steps: write the tests → run (fail) → implement → run (pass) → commit.

### Task 3: Counselor list + action routes + legacy guard + IT portal section

**Files:**
- Modify: `apps/api/app/api/lead_appointments.py` (`counselor_router` `GET /counselor/appointments`; `action_router` `POST /lead-appointments/{id}/{confirm|complete|no-show|cancel|reschedule}`)
- Modify: `apps/api/app/api/workflows.py` (`update_appointment`: `lead_id` → 404)
- Modify: `apps/api/app/services/portal.py` (`_it_counselor` `appointments` header-only payload)
- Test: `apps/api/tests/test_tel_016_actions.py`

Tests (RED first):
- Confirm, then complete after start → stage `counselling_completed` (AC2).
- Complete before start → 422.
- A no-show → stage `follow_up` via `appointment_released`.
- A telecaller cancel with a reason → `cancelled`, stage `follow_up`; a cancel without a reason → 422.
- A reschedule keeps the old and new times in the events, sets status `rescheduled`, and doesn't move the stage; a reschedule clash → 409.
- A finished appointment → 409.
- Counselor B on A's appointment → 404; a telecaller confirm → 403; a manager → 404.
- The counselor list shows only their own rows with lead contact details.
- The legacy PATCH on a lead appointment → 404.
- The IT counselor `GET /portal/it/counselor/appointments` → 200.
- Regression: run `test_cns_001_counselor_workspace.py` and `test_tel_017_it_counselor.py` and confirm they still pass (AC5).

Steps: write the tests → run (fail) → implement → run (pass) → commit.

### Task 4: Frontend — lead detail section + booking form

**Files:**
- Create: `apps/web/lib/leadAppointments.ts`, `apps/web/components/LeadAppointmentsSection.tsx`, `apps/web/components/BookCounsellingForm.tsx`
- Modify: `apps/web/components/LeadDetailPanel.tsx` (render the section; pass a `manager` flag and an `onStage` callback)
- Test: `apps/web/tests/leadAppointments.test.ts`

**`lib/leadAppointments.ts` produces:**
- `LeadAppointment`, `AppointmentOptions` types
- `STATUS_LABEL`, `OPEN_STATUSES`
- `appointmentsUrl(leadId)`, `optionsUrl(leadId)`, `actionUrl(id, action)`, `COUNSELOR_APPOINTMENTS_URL`
- `safeLink(url)`, which returns the URL only if it is http(s)
- `bookingBody(values)`

Vitest:
- `safeLink` refuses `javascript:`.
- `bookingBody` drops blanks and builds the IST ISO time.

Steps: test → fail → implement → pass; then tsc and eslint in the web-test container → commit.

### Task 5: Frontend — counselor appointments panel

**Files:**
- Create: `apps/web/components/CounselorAppointmentsPanel.tsx`
- Modify: `apps/web/components/PortalPage.tsx` (the `appointments` section for `it/counselor` and `overseas/counselor`), `apps/web/lib/navigation.ts` (`it/counselor` gets `appointments`)
- Test: covered by the Playwright spec in Task 6; plus tsc and eslint.

### Task 6: Playwright e2e

**Files:**
- Create: `apps/web/e2e/tel-016-lead-appointments.spec.ts`

**Flow:**
1. The telecaller opens their lead and books IT course counselling with an IT counselor tomorrow.
2. They see the Counselling Scheduled stage.
3. The counselor signs in, opens Appointments, sees the booking and confirms it.

Mobile viewport check: there is no horizontal scroll.

### Task 7: Docs

- `docs/decisions/PRODUCT_DECISION_REGISTER.md`: `DEC-SCOPE-095` (AP1–AP14)
- `docs/architecture/API_CONTRACT.md`: §12Q
- `docs/architecture/RBAC_MATRIX.md`: §2.23
- `docs/delivery/TELECALLER_CRM_BACKLOG.md`: tel-016 status
- the QA report
