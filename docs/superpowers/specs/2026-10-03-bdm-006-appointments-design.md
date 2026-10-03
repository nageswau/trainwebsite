# bdm-006 — Appointments (types per BDM type, status lifecycle, reschedule) — Design

- **Feature ID:** bdm-006 (`docs/delivery/BDM_CRM_BACKLOG.md` §4)
- **Evidence:** `EVID-016` BDM Functionalities §2 (lines 27–93), Agent §C (615–653), School §C (873–895), College §C (1110–1134), §8 outcomes (250–275) — `ORIGINAL_REQUIREMENT`
- **Decisions:** `DEC-SCOPE-055` (D1–D32, esp. D3, D11, D16, D20, D26, D29); bdm-002 `DEC-SCOPE-060` (AC5b); this item's owner answers A1–A8 (§3), recorded as a new DEC (number rule in §10)
- **Depends on:** bdm-001 (merged, `0061`), bdm-002 (merged, `0066`)
- **Branch:** `feature/bdm-006-appointments` from `origin/main` @ `3bde879`
- **Status:** design approved in-session 2026-10-03; awaiting written-spec review

---

## 1. Scope

BDMs create and manage appointments with every §2 field: Appointment ID, BDM, Organization, Contact Person, Designation, Mobile,
Email, Date, Time, Type, Location, Purpose, Status, Remarks, Next Follow-up.

| In scope | Out of scope (owner item) |
|---|---|
| `bdm_appointments` + `bdm_appointment_events` tables, code sequence | `trip_id` and trip counts (bdm-011) |
| Create / read / list / edit; confirm, reschedule, cancel, no-show, complete | Full meeting report, editable-window rules (bdm-007) |
| Minimal outcome + next follow-up date on Complete (A1) | Follow-up / task records created from the date (bdm-008) |
| Type list per BDM type; outcome list per BDM type | Reminders (bdm-012); calendar views (bdm-013); My Day tiles (bdm-014) |
| Status history, transition matrix enforced | Portfolio handover on deactivation / reassignment (bdm-025) |
| Overlap warning (409 + confirm) | External calendar sync (Q-11 / D20: internal only) |
| `last_meeting_at` / `next_meeting_at` on organizations (bdm-002 AC6 contract) | Any message to organization contacts (Q-20 / D29: none) |
| BDM pages; manager / super_admin read-only pages; "Add appointment" on organization detail | |

"Pending" in the §4 example is a display of `scheduled` next to confirmed ones, not a seventh status (backlog). This item labels it
"Scheduled"; bdm-014 may render it as "Pending".

## 2. Approaches considered

| Topic | Chosen | Rejected and why |
|---|---|---|
| Status history | Status column + `bdm_appointment_events` row per transition | Event-sourced status (derived from the last event): harder lists, no gain. `AuditLog` as history: generic JSON, not shaped or indexed for display — audit is still written in addition |
| Transition API | One POST per action (`confirm`, `reschedule`, `cancel`, `no-show`, `complete`) | One `POST /transition {to,…}`: polymorphic payload, weaker validation and messages |
| Last / next meeting | Read-time scalar subqueries on an `(organization_id, starts_at)` index | Denormalized columns on `bdm_organizations`: cross-table writes, lock ordering, drift |
| Catalogues | Python constants beside `BDM_ORG_TYPES`; web mirror for labels only | A lookup table / admin-editable list: no requirement, more surface |

## 3. Decisions (owner, in-session, 2026-10-03, `EXPLICIT_APPROVAL`)

| # | Question | Answer |
|---|---|---|
| A1 | Completed needs an outcome, but outcomes are bdm-007 | **Minimal outcome in bdm-006:** `complete` takes `outcome` (validated per BDM type) + optional `next_follow_up_on`, stored on the appointment. bdm-007 layers the meeting report on top |
| A2 | Allowed transitions | **Terminal-end matrix** (§5.4). Completed / Cancelled / No Show are terminal. Completed and No Show only after the start time. Cancel and No Show need a reason |
| A3 | Who may book and manage | **The organization's assigned BDM only.** Managers and super_admin read only (Q-17 / D26: managers don't own appointments) |
| A4 | Archived organization | **Blocks create only → 422.** Existing appointments can still be edited, cancelled, marked no-show or completed. (Supersedes the "409" wording in the bdm-002 spec §5.3 AC5b note; the backlog and this item's AC say 422.) |
| A5 | Contact deleted (bdm-002 hard delete) | **Keep the snapshot:** `contact_id` → NULL (`ON DELETE SET NULL`); the copied name / designation / phone / email remain as the meeting record. bdm-002's delete route is unchanged |
| A6 | Overlap for the same BDM | **409 `possible_overlap` + `confirm_overlap`** (the bdm-002 duplicate pattern). Needs `duration_minutes` (default 60) |
| A7 | Past start time | **Future only** on create and reschedule |
| A8 | Outcome lists | **Agent §C (8) for agent BDMs; §8 common (9) for school and college BDMs** |

Design defaults (approved with the design, not separately asked):
- **Type list per BDM type** = §2 common (8) ∪ that module's §C list, deduplicated by key. "Seminar / Workshop" stays a common type
  distinct from School/College "Seminar" and "Workshop".
- **Contact source:** picked from the organization's contacts only (no free-text contact). The snapshot is re-copied when the
  contact is changed by PATCH.
- **Ownership is fixed:** an appointment stays with its BDM if the organization is later reassigned (bdm-025 moves portfolios).
- **Location, purpose, remarks** are optional (online meetings have no location; the source marks nothing mandatory beyond the
  organization, contact, date/time and type).

## 4. Data model — migration `0068_bdm_appointments` (additive only)

### 4.1 Catalogues (`models.py`, after `BDM_CONTACT_ROLES`)

```python
BDM_APPOINTMENT_STATUSES = ("scheduled", "confirmed", "rescheduled", "completed", "cancelled", "no_show")
BDM_APPOINTMENT_OPEN = ("scheduled", "confirmed", "rescheduled")
BDM_APPOINTMENT_COMMON_TYPES = ("college_meeting", "agent_meeting", "school_meeting", "mou_discussion",
    "student_institution_meeting", "seminar_workshop", "corporate_meeting", "other")
BDM_APPOINTMENT_MODULE_TYPES = {
    "agent": ("agent_meeting", "new_agent_presentation", "product_training", "agreement_discussion", "performance_review",
              "agent_onboarding", "agent_visit", "commission_discussion", "business_review"),
    "school": ("principal_meeting", "management_meeting", "career_guidance_presentation", "psychometric_presentation",
               "profile_building_presentation", "parent_orientation", "teacher_orientation", "seminar", "workshop",
               "mou_discussion", "renewal_meeting"),
    "college": ("principal_meeting", "hod_meeting", "placement_cell_meeting", "course_promotion", "it_training_presentation",
                "student_seminar", "workshop", "internship_discussion", "placement_discussion", "mou_discussion",
                "corporate_connect", "faculty_meeting"),
}
BDM_APPOINTMENT_COMMON_OUTCOMES = ("interested", "mou_discussion_required", "student_leads_expected",
    "course_promotion_interested", "follow_up_required", "commercial_discussion", "not_interested", "reschedule", "other")
BDM_APPOINTMENT_AGENT_OUTCOMES = ("interested", "agreement_required", "product_training_required", "follow_up",
    "documents_required", "onboarding_required", "active_business_expected", "not_interested")
```

Helpers `appointment_types(bdm_type)` (common + module, order-preserving dedupe) and `appointment_outcomes(bdm_type)` live in the
service. The CHECK constraints accept the union of all keys; per-type validation is the service's job (the database cannot see the
owner's type).

### 4.2 `bdm_appointments`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `code` | varchar(20) NOT NULL, unique `uq_bdm_appointments_code` | `APT-000001` from `bdm_appointment_code_seq` (gaps accepted) |
| `bdm_user_id` | uuid NOT NULL → `users.id` RESTRICT | Owner = creator (A3) |
| `organization_id` | uuid NOT NULL → `bdm_organizations.id` RESTRICT | |
| `contact_id` | uuid NULL → `bdm_organization_contacts.id` **SET NULL** | A5 |
| `contact_name` | varchar(200) NOT NULL | Snapshot |
| `contact_designation` | varchar(120) NULL | Snapshot |
| `contact_phone` | varchar(30) NULL | Snapshot (§2 "Mobile") |
| `contact_email` | varchar(255) NULL | Snapshot |
| `starts_at` | timestamptz NOT NULL | §2 Date + Time (stored UTC, shown IST) |
| `duration_minutes` | int NOT NULL default 60, CHECK 15–720 | |
| `appointment_type` | varchar(40) NOT NULL, CHECK in all type keys | |
| `location` | varchar(255) NULL | |
| `purpose` | varchar(1000) NULL | |
| `remarks` | varchar(2000) NULL | |
| `status` | varchar(20) NOT NULL default `scheduled`, CHECK six statuses | |
| `outcome` | varchar(40) NULL, CHECK in all outcome keys | A1 |
| `next_follow_up_on` | date NULL | A1 (§2 "Next Follow-up") |
| `expected_leads` | int NULL, CHECK ≥ 0 | Q-07 / D16 |
| `expected_revenue` | numeric(12,2) NULL, CHECK ≥ 0 | INR, Q-07 / D16 |
| `created_at`, `updated_at` | timestamptz | `TimestampMixin` |

CHECK `ck_bdm_appointments_outcome_completed`: `(status = 'completed') = (outcome IS NOT NULL)`.
CHECK `ck_bdm_appointments_follow_up`: `next_follow_up_on IS NULL OR status = 'completed'`.
Indexes: `ix_bdm_appointments_bdm_starts (bdm_user_id, starts_at)`, `ix_bdm_appointments_org_starts (organization_id, starts_at)`,
`ix_bdm_appointments_contact (contact_id)` (keeps the SET NULL on contact delete off a sequential scan).

### 4.3 `bdm_appointment_events`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `appointment_id` | uuid NOT NULL → `bdm_appointments.id` RESTRICT | |
| `actor_user_id` | uuid NOT NULL → `users.id` RESTRICT | |
| `from_status` | varchar(20) NULL | NULL on creation |
| `to_status` | varchar(20) NOT NULL | CHECK six statuses |
| `old_starts_at` | timestamptz NULL | Reschedule only |
| `new_starts_at` | timestamptz NULL | Reschedule only |
| `reason` | varchar(500) NULL | Required for cancel / no-show (service), optional for reschedule |
| `created_at` | timestamptz NOT NULL default now() | |
| `position` | bigint identity | Stable order for events created in one transaction |

Index `ix_bdm_appointment_events_appointment (appointment_id, position)`. Rows are never updated or deleted.

### 4.4 Migration style (as `0066_bdm_organizations`)

- `CREATE SEQUENCE IF NOT EXISTS bdm_appointment_code_seq`; the sequence is also on `Base.metadata` so 0001's `create_all` builds a
  fresh database.
- Guarded create (skip when the table exists and not `--sql`); no existing row is read or written.
- `downgrade()` refuses while any appointment exists (they are the only record of each meeting), otherwise drops both tables and
  the sequence.
- Chains on `0067_audit_entity_index`. Renumbering rule in §10.

## 5. Backend

### 5.1 Schemas (`schemas.py`, after the bdm-002 block; `extra="forbid"` everywhere)

- `BdmAppointmentCreate`: `organization_id`, `contact_id`, `starts_at` (aware datetime; naive → 422), `duration_minutes`
  (15–720, default 60), `appointment_type` (Literal of all keys), `location`, `purpose`, `remarks` (reuse the bdm-002 text
  validators: strip, control characters rejected, max lengths = columns), `expected_leads` (StrictInt ≥ 0), `expected_revenue`
  (Decimal ≥ 0, 2 dp, ≤ 9 999 999 999.99), `confirm_overlap: bool = False`.
- `BdmAppointmentUpdate`: the same editable fields minus `organization_id` and `starts_at`, all optional, plus `confirm_overlap`.
  Sending `starts_at`, `status`, `outcome`, `code`, `bdm_user_id`, `organization_id` → 422 "Unknown field: …".
- `BdmAppointmentReschedule`: `starts_at`, `duration_minutes?`, `reason?` (≤ 500), `confirm_overlap`.
- `BdmAppointmentReason` (cancel, no-show): `reason` required, 1–500 after strip.
- `BdmAppointmentComplete`: `outcome` (Literal of all outcome keys), `next_follow_up_on: date | None`.
- Output: `BdmAppointmentRow` (id, code, starts_at, duration_minutes, appointment_type, status, organization {id, code, name,
  archived}, contact_name, bdm {id, full_name, active}), `BdmAppointmentOut` (row + all §2 fields, outcome, next_follow_up_on,
  expected_*, events[], permissions, created_at, updated_at), `BdmAppointmentEventOut` (from/to, old/new starts_at, reason,
  actor_name, created_at), `BdmAppointmentPermissions` (`can_edit`, `can_confirm`, `can_reschedule`, `can_cancel`, `can_no_show`,
  `can_complete`), `BdmAppointmentPage` ({items, total, limit, offset}), `BdmAppointmentEnvelope` ({appointment}).

The "future only" (A7) and "after the start" rules are checked in the service against the database clock (`now()` taken once per
request), not in the schema, so tests can control time by editing `starts_at`.

### 5.2 Service — new `app/services/bdm_appointments.py` (never commits)

- `appointment_types(bdm_type)`, `appointment_outcomes(bdm_type)`.
- `TRANSITIONS: dict[str, frozenset[str]]` — §5.4, the single source for enforcement and `permissions`.
- `caller_filters(db, user)` — `bdm` → `bdm_user_id == user.id` (requires `bdm_context`); `bdm_manager` →
  `bdm_user_id IN (team sub-select)`; `super_admin` → none; other roles → 403 "BDM role required".
- `load_scoped(db, user, appt_id, *, lock=False)` — out of scope = 404 "Appointment not found"; `lock` = `FOR UPDATE OF
  bdm_appointments` + `populate_existing`.
- `require_owner(user, appt, action)` — 403 "Only the appointment's BDM can change it" (logged) for anyone but the owning `bdm`.
- `require_transition(appt, to_status)` — 409 "Appointment is already <status>" (terminal) or "Cannot <action> a <status>
  appointment".
- `require_future(starts_at, now)` → 422 "Choose a time in the future"; `require_started(appt, now)` → 422 "You can only <complete
  | mark no-show> after the start time".
- `snapshot(contact)` → the four contact columns.
- `find_overlaps(db, bdm_user_id, starts_at, duration, exclude_id)` — the owner's open appointments whose
  `[starts_at, starts_at + duration)` intersects; max 10 returned + total. `overlap_conflict(...)` → 409 `{message, code:
  "possible_overlap", matches, total}`.
- `record(db, appt, actor, from_status, to_status, **extra)` — adds the event row.
- `permissions(user, appt, now)` — owner and state based; all-false for managers / super_admin.
- `appointment_out(db, user, appt)` / `row_out(...)`; `audit(db, user, action, appt_id, metadata)` → `AuditLog`
  `bdm_appointment.<action>` (ids, field names, statuses only); `log(event, user, appt_id, **extra)` (no names, phones, emails).
- `meeting_columns()` — the two correlated scalar subqueries used by the organization outputs (§5.6).

### 5.3 Router — new `app/api/bdm_appointments.py`, prefix `/bdm/appointments`, registered in `main.py`

| Method / path | Who | Behaviour |
|---|---|---|
| `GET ""` | bdm, bdm_manager, super_admin | Filters (ANDed with scope): `from`, `to` (IST dates → UTC half-open range; `from > to` → 422), `status` (repeatable), `appointment_type`, `organization_id`, `bdm_user_id` (manager / super_admin only; a `bdm` sending it → 422), `q` (code or organization name, literal substring via `lookups._pattern`), `limit` (1–100, default 50), `offset`. Order `starts_at, id`. One query joining organization + owner (no N+1) |
| `POST ""` → 201 | bdm | §5.5 create flow |
| `GET /{id}` | in scope | Detail + events + permissions |
| `PATCH /{id}` | owner | Open statuses only (else 409). Values equal to stored ones are not changes. A changed `contact_id` must belong to the appointment's organization (else 422) and re-copies the snapshot. A changed `duration_minutes` re-runs the overlap check. Audit lists changed field names; no event (not a transition) |
| `POST /{id}/confirm` | owner | `scheduled`/`rescheduled` → `confirmed` |
| `POST /{id}/reschedule` | owner | Open → `rescheduled`; `starts_at` future (A7); overlap check; event carries old/new time and optional reason |
| `POST /{id}/cancel` | owner | Open → `cancelled`; reason required |
| `POST /{id}/no-show` | owner | Open → `no_show`; start passed; reason required |
| `POST /{id}/complete` | owner | Open → `completed`; start passed; `outcome` in the owner's list (else 422); stores `outcome`, `next_follow_up_on` |

Every write returns `{appointment}` (the full detail), like bdm-002.

### 5.4 Transition matrix (A2)

| From \ To | confirmed | rescheduled | cancelled | no_show | completed |
|---|---|---|---|---|---|
| scheduled | ✓ | ✓ | ✓ (reason) | ✓ (reason, after start) | ✓ (outcome, after start) |
| confirmed | — | ✓ | ✓ (reason) | ✓ (reason, after start) | ✓ (outcome, after start) |
| rescheduled | ✓ | ✓ | ✓ (reason) | ✓ (reason, after start) | ✓ (outcome, after start) |
| completed / cancelled / no_show | terminal | terminal | terminal | terminal | terminal |

Creation records an event `NULL → scheduled`. Every transition records exactly one event. Reschedule always sets `rescheduled`
(even from `rescheduled`), so "reschedule twice" gives two events, each with its own old time.

### 5.5 Create flow (one transaction)

1. `bdm_context` (403 for non-BDMs and BDMs without a profile).
2. `bdm_organizations.load_scoped(db, user, organization_id, lock=True)` — out of type scope → 404 "Organization not found".
3. Assigned check → 403 "Only the assigned BDM can book appointments for this organization" (A3).
4. `archived_at` set → **422** "This organization is archived — restore it before booking" (A4, AC6).
5. Contact belongs to the organization → else 422 "Choose a contact of this organization".
6. `appointment_type` in `appointment_types(profile.bdm_type)` → else 422 "This appointment type is not available for <Type>
   BDMs".
7. `starts_at` in the future → else 422.
8. Overlaps (unless `confirm_overlap`) → 409 `possible_overlap`.
9. Insert with `code = next_code()`, the snapshot, `status = scheduled`; event; audit (`create`, plus `overlap_override` when
   confirmed past a warning); one commit.

Validation order is fixed so each negative test hits exactly one rule.

### 5.6 Organization outputs (bdm-002 contract, AC6 of bdm-002)

- `last_meeting_at` = `max(starts_at)` of the organization's `completed` appointments.
- `next_meeting_at` = `min(starts_at)` of its open appointments with `starts_at > now()`.
- Across **all** BDMs' appointments at that organization (an organization reader sees dates only, never other BDMs' details).
- `GET /bdm/organizations` adds both as correlated scalar subqueries to the existing single statement; `organization_out` runs one
  extra two-column query. `row_out` gains two parameters instead of hard-coded `None`. Field names, types and nullability are
  unchanged; no other field changes.

### 5.7 Transactions, races, authorization

- Each write: scope → lock → validate → change → event → audit → one `commit()` in the route. Services never commit.
- **Lock order is always organization → appointment.** Create locks the organization row (`FOR UPDATE`). A PATCH that changes
  `contact_id` first locks the organization (bdm-002 `load_scoped(lock=True)`), then the appointment, so a concurrent bdm-002
  contact delete (which locks the organization, then — through `ON DELETE SET NULL` — appointment rows) cannot remove the new
  contact between the check and the write. Every other appointment write locks only the appointment row. No path locks an
  appointment and then an organization, so there is no cycle with bdm-002 (organization → user, organization → appointment).
- **Concurrent transitions** on one appointment serialize on its row lock; the loser re-reads the new status and gets 409.
- **Create vs archive** serialize on the organization row: an archive committed first makes the create 422; a create committed first
  leaves a valid appointment on a now-archived organization (allowed by A4).
- **Create vs contact delete:** create reads the contact after locking the organization, and bdm-002's contact delete locks the same
  organization row first, so the contact cannot vanish mid-create.
- **Overlap** is warn-only and unlocked: two simultaneous bookings may both succeed (same trade-off as Q-18 duplicates).
- **IDOR:** every `{id}` resolves through `load_scoped`; out of scope = 404 before any permission check. `organization_id` /
  `contact_id` in bodies resolve through bdm-002's scope and the organization-ownership check.
- **Mass assignment:** `extra="forbid"` rejects `code`, `status`, `bdm_user_id`, `outcome` (except on complete), `organization_id`
  on PATCH.
- **Manager visibility follows the BDM** (team by sub-select), as bdm-002.

### 5.8 Errors

| Status | When |
|---|---|
| 403 | Not `bdm`/`bdm_manager`/`super_admin`; BDM without profile; create by a non-BDM or a non-assignee; any write by a non-owner (manager, super_admin, other BDM in scope) |
| 404 | Unknown / out-of-scope appointment; unknown / out-of-type-scope organization |
| 409 | Illegal or terminal transition; PATCH on a closed appointment; `possible_overlap` (structured body) |
| 422 | Validation (readable, names the field); unknown field; past `starts_at` (A7); complete / no-show before start; type or outcome not in the owner's list; contact not of this organization; **archived organization on create** (A4); `bdm_user_id` filter sent by a BDM; `from > to` |

## 6. Frontend

### 6.1 Pages (server components; the API is the gate)

| Path | Gate | Renders |
|---|---|---|
| `/bdm/appointments` | `/api/v1/bdm/me` | `PortalShell` (`BDM_NAV`) + `<Suspense><BdmAppointmentsPanel basePath="/bdm/appointments" isBdm/></Suspense>` |
| `/bdm/appointments/new` | `/bdm/me`; optional `?organization=<id>` | `BdmAppointmentForm` (create), `bdmType` from the profile |
| `/bdm/appointments/[id]` | `/bdm/me` + `GET /bdm/appointments/{id}` | `BdmAppointmentDetail`; 404/422 → "Appointment not found" + link back |
| `/bdm/manager/appointments` | `/api/v1/auth/me` (manager / super_admin else `accessDenied`) | Panel with BDM filter, no create |
| `/bdm/manager/appointments/[id]` | `/auth/me` + detail | Detail (actions absent: permissions all false) |

`middleware.ts` already protects `/bdm/:path*`; no change.

### 6.2 Components (client)

- **`BdmAppointmentsPanel`** — the `BdmOrganizationsPanel` pattern: URL state (`from` default today IST, `to`, `status`, `type`,
  `organization`, `bdm` for managers, `offset`), Back/Forward sync, `isPage` guard. States: loading (`role="status"`); error +
  Retry; empty ("No appointments yet" + "Add appointment" for a BDM); no matches + "Clear filters"; past the end + "Go to the first
  page"; table (Code link, Date & time IST, Organization, Contact, Type, Status badge, and BDM for managers) in a labelled scroll
  region; pager.
- **`BdmAppointmentForm`** — create and edit. Organization: `SearchableSelect` (server mode) over
  `/api/v1/bdm/organizations?assigned=me` (archived excluded by default), prefilled from `?organization=`; fixed on edit. Contact:
  select loaded from `GET /bdm/organizations/{id}` contacts, primary preselected; reloading on organization change. Date & time:
  `datetime-local`, interpreted as IST and sent as an ISO string with `+05:30` (helper in `lib/bdmAppointments.ts`, unit-tested
  across midnight). Type select = the BDM type's list. Duration, location, purpose, remarks, expected leads / revenue. `sendJson`;
  "Saving…" + disabled while busy; `FormMessage` with focus. `possible_overlap` 409 → alert (focus to heading) listing clashes as
  plain text (code, time, organization), "Save anyway" (resend with `confirm_overlap: true`) and "Cancel"; Save disabled while
  open. On create success → `router.push(/bdm/appointments/{id}?created=1)`.
- **`BdmAppointmentDetail`** — `<dl>` of every §2 field ("—" for blanks; times via `formatSchoolDateTime(v, true)`), outcome and
  next follow-up when completed, organization link (`archived` badge), Edit toggle when `can_edit`; hosts actions and history.
  Re-renders from each returned appointment (no refetch).
- **`BdmAppointmentActions`** — rendered from `permissions` only. Confirm (single button); Reschedule (inline group: new time,
  duration, optional reason, overlap flow); Cancel / No show (inline group, reason required, client-side empty check mirrors the
  422); Complete (outcome select for the BDM type, optional follow-up date). One group open at a time; focus returns to the trigger
  on Cancel and moves to the message on error; buttons have visible text.
- **`BdmAppointmentHistory`** — ordered list: actor, when (IST), "Scheduled → Confirmed", old → new time, reason.
- **`lib/bdmAppointments.ts`** — types, URLs, `APPOINTMENT_STATUS_LABEL`, `appointmentTypes(bdmType)` with labels,
  `appointmentOutcomes(bdmType)`, `istInputToIso()` / `isoToIstInput()`, `overlapMatches(detail)` parser. Display only; the API
  decides.
- **`BdmOrganizationDetail`** — "Add appointment" link (`/bdm/appointments/new?organization=<id>`) when `basePath` is the BDM
  portal and `permissions.can_edit` (assigned and not archived). Last / Next meeting rendering is unchanged (now real values); the
  "until bdm-006" comment is updated.

### 6.3 Navigation

- `BDM_NAV`: My Day · Organizations · **Appointments** · Profile.
- `BDM_MANAGER_NAV`: Dashboard · Team · Organizations · **Appointments**.
- `tests/lib/navigation.bdm.test.ts` and nav snapshots in `BdmPages.test.tsx` are updated deliberately (a spec change).

### 6.4 Responsive and accessibility

No horizontal page scroll at 375 px (tables scroll in their own labelled region); every input labelled; errors `role="alert"`,
success `role="status"`; status shown as text, not colour alone; focus management as above.

## 7. Acceptance criteria

| AC | Criterion | Verified by |
|---|---|---|
| AC1 | All §2 fields are captured: code (Appointment ID), BDM, organization, contact person / designation / mobile / email (snapshot), date + time (`starts_at`, shown IST), type, location, purpose, status, remarks, next follow-up (`next_follow_up_on` via complete) | API create/detail tests; component test of the detail `<dl>`; E2E |
| AC2 | The type list depends on the BDM's type and includes the common types; a type from another module → 422 | Service catalogue tests; API 422 test per module; form test |
| AC3 | Every status transition (and creation) is recorded as an event; the §5.4 matrix is documented here and enforced — every illegal pair → 409 | Parametrized matrix test over all 6×6 pairs; history test |
| AC4 | Reschedule keeps the old time in history and sets the status to Rescheduled (also from Rescheduled) | Transition test "reschedule twice" (two events, both old times) |
| AC5 | Completed requires an outcome (valid for the owner's type) and a past start time; else 422 | Transition tests; DB CHECK test |
| AC6 | Creating an appointment on an archived organization → 422; existing appointments stay manageable | Scope test; E2E (no "Add appointment" on an archived organization) |
| AC7 | Only the assigned BDM books; only the owner writes; managers and super_admin read only; out of scope → 404 | Scope matrix tests |
| AC8 | Overlap for the same BDM warns with 409 `possible_overlap`; `confirm_overlap` saves | API + form tests |
| AC9 | Organization list and detail return real `last_meeting_at` / `next_meeting_at` with no N+1 | Org meetings tests (query-count assertion) |
| AC10 | Deleting an organization contact keeps appointment snapshots (`contact_id` → NULL) | API test through bdm-002's delete route |

## 8. Tests (written before the code)

### 8.1 Backend (`apps/api/tests`, shared DB, uuid-unique data; new `bdm006_helpers.py` on top of `bdm002_helpers`)

- `test_bdm_006_migration.py` — tables, columns, CHECKs (status, type, outcome, outcome-iff-completed, follow-up, duration, ≥ 0),
  indexes, FK `ON DELETE` rules, sequence, single head, guarded downgrade refusal.
- `test_bdm_006_schemas.py` — limits, control characters, naive datetime, unknown fields, reason required, money precision.
- `test_bdm_006_service.py` — `appointment_types` / `appointment_outcomes` per type (counts and dedupe), `TRANSITIONS` table,
  `permissions` per role and state, overlap interval maths.
- `test_bdm_006_appointments.py` — create (AC1, code format, snapshot, event), detail, list filters (`from`/`to` IST edges incl. an
  appointment at 23:30 IST, status multi, type, organization, `q`, paging bounds, ordering), PATCH (no-op = no audit, contact
  re-snapshot, contact of another organization 422, closed → 409), AC10.
- `test_bdm_006_transitions.py` — every action happy path; matrix over all pairs (AC3); terminal 409s; complete / no-show before
  start 422; complete without / with foreign outcome 422; cancel / no-show without reason 422; reschedule into the past 422;
  reschedule twice (AC4); overlap 409 + confirm (AC8).
- `test_bdm_006_scope.py` — AC6, AC7: non-assignee create 403; out-of-type organization 404; another BDM's appointment 404; manager
  writes 403, team read 200, other team 404; super_admin read all, write 403; other roles 403; BDM without profile 403; archived
  create 422 and existing-appointment cancel 200.
- `test_bdm_006_org_meetings.py` — AC9 values (completed vs open vs past-open vs cancelled), query count constant for 1 vs 5
  organizations; bdm-002 null case unchanged.
- `test_bdm_006_concurrency.py` — concurrent confirm + cancel (one 200, one 409, one event each); archive vs create serialize;
  PATCH contact change vs bdm-002 delete of that contact (never a 500: either 422 or the snapshot kept with `contact_id` NULL).

### 8.2 Web unit (vitest)

`bdmAppointments.test.ts` (catalogue keys per type, IST conversion both ways incl. midnight, overlap parser);
`BdmAppointmentsPanel.test.tsx` (every state, URL sync, manager BDM filter); `BdmAppointmentForm.test.tsx` (contact load and primary
preselect, type list per BDM type, overlap alert flow, busy state, error focus); `BdmAppointmentActions.test.tsx` (buttons from
permissions, reason required, complete outcome list, re-render from response); `BdmAppointmentDetail.test.tsx`;
`BdmAppointmentHistory.test.tsx`; `BdmOrganizationDetail.test.tsx` (Add appointment link shown / hidden); nav tests updated.

### 8.3 End to end (Playwright) — `tests/e2e/bdm-006-appointments.spec.ts`

A BDM books from the organization page → confirms → reschedules (history shows the old time) → (test helper moves `starts_at` into
the past) → completes with an outcome; an archived organization has no "Add appointment"; a manager sees the appointment read-only.
Evidence recorded under `docs/quality/`.

### 8.4 Regression runs

Per feature: the lite backend set (bdm-001/002/006 + migration-head tests) and the web BDM set; `tsc`, `eslint`, `next build`;
Playwright bdm-001/002/006. The owner runs the full suites on the usual cadence.

## 9. Regression risks

| Risk | Mitigation |
|---|---|
| bdm-002 organization outputs change (hot list endpoint) | Same field names / shapes; existing bdm-002 tests stay green (null when no appointments); query-count test |
| `Appointment` vs `BdmAppointment` in `models.py` | `Bdm*` names; legacy `appointments`, `/overseas/appointments`, `portal.py` untouched |
| bdm-002 contact delete breaks on the new FK | `ON DELETE SET NULL` + test through the bdm-002 route |
| Migration / DEC numbering vs unmerged bdm-010 (`0068_bdm_trips`, `DEC-SCOPE-063`) and bdm-003 | §10 rule; re-check `origin/main` before the plan and before executing |
| Shared files edited by bdm-010 (`models.py`, `schemas.py`, `main.py`, `navigation.ts`, `lib/bdm.ts`, `app/bdm/*`) | Append-only edits in separate blocks; no refactor of shared nav; resolve on merge |
| IST / UTC errors at day boundaries | Server converts IST dates to UTC ranges; tests at 23:30 IST and 00:30 IST |
| Deadlock with bdm-002 writes | Fixed lock order (§5.7) |

## 10. Documentation (same change)

- New DEC in `PRODUCT_DECISION_REGISTER.md` recording A1–A8. **Number rule:** the next free `DEC-SCOPE-NNN` on `origin/main` at merge
  time (`063` if this merges before bdm-010, else `064`, or later if others land). Migration likewise: `0068_bdm_appointments` on
  `0067`, re-chained to the current head if another migration merges first (the 0066 re-chain idiom, noted in the docstring).
- `BDM_CRM_BACKLOG.md` bdm-006 status line; bdm-002 spec AC5b note corrected to 422 with a pointer to A4.
- `DATA_MODEL.md` (two tables), `API_CONTRACT.md` (routes; bdm-002 org fields now populated), `RBAC_MATRIX.md` §2.13 (appointment
  rows), `RTM.md` (AC1–AC10 → tests), `ROLE_NAVIGATION.md` (Appointments entries).

## 11. Completion gates

Acceptance (AC1–AC10), security / RBAC / resource scope, backend lite + web tests, `tsc` / `eslint` / `next build`, migration
up / down on a fresh and an existing database, responsive (375 px) and accessibility checks, browser QA, documentation — per the
constitution's completion rule.
