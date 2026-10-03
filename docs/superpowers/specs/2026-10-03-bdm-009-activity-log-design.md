# bdm-009 — BDM Activity Log (call / WhatsApp / email / visit / meeting / other) — Design

**Status:** design approved in-session on 2026-10-03 in five sections: (1) data model and rules, (2) API, authorization,
transactions and races, (3) frontend, (4) acceptance criteria and tests, (5) regression risks. No code has been written.

**Branch:** `feature/bdm-009-activities`, created from `origin/main` @ `65a8ece0` (after bdm-010 #53).

**Backlog:** `docs/delivery/BDM_CRM_BACKLOG.md` §4 bdm-009 (line 520). Depends only on bdm-002 (merged, PR #50).

**Source:** `functionalities/edusphere_markdown/BDM Functionalities.md` (`EVID-016`, `DERIVED_BLUEPRINT`) §4 Common
"Activity" (1288–1298), §11 Daily Activity Report (371–397), Agent §G (759–781), School §G (1000–1022).
Decisions already in force: `DEC-SCOPE-055` D9 (derived report + manual activity log), Q-02/D11 (read own type, edit
assigned), Q-13/D22 (submitting a daily report locks that day's activity edits), Q-20/D29 (nothing is sent to contacts).

**Decision record:** **`DEC-SCOPE-064`**, written in this change (next free on `main` @ `65a8ece0`; `063` is bdm-010).
Migration **`0069_bdm_activities`** (single head on `main` is `0068_bdm_trips`). bdm-006 and bdm-003 are in flight and
also claim `0068` / `063`; whichever merges after another renumbers. Recheck `origin/main` before building and before the PR.

**Gate:** `APPROVAL_GATES.md` GATE-09.

---

## 1. Scope

In scope:
- The assigned BDM logs an activity against an organization: channel, direction (call / WhatsApp / email), optional
  contact, when it happened, short note. Nothing is sent from the system (D9, D29).
- The logger edits or deletes their own activity on the IST day it happened.
- An organization's activity timeline, visible to everyone who can read the organization.
- "My activities" for a chosen IST day with exact per-channel counts; a manager's team view with the same counts.
- `day_counts()` — the reusable counting function bdm-015 will import.

Out of scope (owned elsewhere):
- Link to an appointment (bdm-006 adds `appointment_id` + FK) and to a task (bdm-008 adds `task_id` + FK).
- The daily report, its snapshot and the "report submitted" lock (bdm-015). bdm-009 leaves one gate, `editable()`, for it.
- "Log activity" from My Day (bdm-014) and from a completed follow-up (bdm-008).
- Organizations contacted **by type** and every other §11 count (bdm-015's metrics package).
- Any dialer, WhatsApp or email integration.

## 2. Approaches considered

| | Approach | Verdict |
|---|---|---|
| **A** | One `bdm_activities` table; flat `api/bdm_activities.py` + `services/bdm_activities.py` (same shape as bdm-002/006/010); counts computed live by one grouped query | **Chosen.** Exact by construction, smallest change, follows the existing modules |
| B | A per-day counter table updated on every write | Rejected: write races and drift between counters and rows; volume is tiny |
| C | One generic "BDM timeline events" table shared by activities, appointment events and tasks | Rejected: fights bdm-006's `bdm_appointment_events`, redesigns other modules (YAGNI) |

## 3. Decisions (owner answers 2026-10-03, `EXPLICIT_APPROVAL`, recorded in `DEC-SCOPE-064`)

| # | Question | Answer |
|---|---|---|
| V1 | Who may log against an organization | **The assigned BDM only** (same rule as edit and bdm-006 booking). Out of type scope → 404; in scope but not assigned → 403; archived → 422 |
| V2 | Channels | **`call`, `whatsapp`, `email`, `visit`, `meeting`, `other`.** No `follow_up` channel — follow-ups are bdm-008 tasks. The daily report counts meetings from completed appointments (bdm-015); `meeting` / `visit` activities count only under their own channel |
| V3 | Appointment / task links | **Deferred** to bdm-006 / bdm-008, each with its own migration and real FK |
| V4 | Time rules | `occurred_at` not in the future and **at most 7 IST days back**; edit / delete **only on the IST day it happened**, through one gate bdm-015 extends with "report not submitted" |
| V5 | Timeline visibility | **Everyone who can read the organization** (same-type BDMs, the team manager, `super_admin`), so history survives reassignment |
| V6 | Direction | **Required (`outbound` / `inbound`) for call, WhatsApp and email; must be empty for visit, meeting, other.** "Calls made" = outbound calls |
| V7 | Screens | Org timeline + Log activity on the org profile, **`/bdm/activities`** (my day + counts) and **`/bdm/manager/activities`** (team, BDM filter) |
| V8 | Delete | **Hard delete + audit row** (ids and channel, no note) |

Design defaults (presented in the approved sections, not asked separately):
- `super_admin` reads everything and cannot write (an activity is a BDM's own record); `it_admin` / `overseas_admin` have
  no access (bdm-002).
- The contact must belong to the same organization. The contact's name is copied at save (`contact_name`), so a later
  contact delete (bdm-002 hard delete, `contact_id` → NULL) leaves "Name (removed)" on the activity, as bdm-006 A5.
- The organization of an activity is fixed after create (delete and re-log to move it).
- An edit cannot move `occurred_at` off today (IST); otherwise an edit could reach a day bdm-015 has locked.
- After a reassignment the original logger can still correct that day's entries but cannot log new ones.
- Archiving does not block same-day corrections (as bdm-006: existing appointments can still be closed out).
- No idempotency key (as bdm-010): Save is disabled while busy; a double POST makes a duplicate the BDM can delete the
  same day. Recorded as accepted.

## 4. Data model — migration `0069_bdm_activities`

### 4.1 `bdm_activities` (model `BdmActivity`, appended to the BDM CRM section of `models.py` after `BdmOrganizationContact`)

| Column | Type / rule |
|---|---|
| `id` | UUID PK |
| `bdm_user_id` | FK `users.id` `ON DELETE RESTRICT`, NOT NULL — the logger and owner |
| `organization_id` | FK `bdm_organizations.id` `ON DELETE RESTRICT`, NOT NULL |
| `contact_id` | FK `bdm_organization_contacts.id` `ON DELETE SET NULL`, nullable |
| `contact_name` | `String(200)`, nullable — copied from the contact at save; NULL when no contact |
| `channel` | `String(20)` NOT NULL, `ck_bdm_activities_channel` IN the six values (`BDM_ACTIVITY_CHANNELS`) |
| `direction` | `String(10)` nullable, `ck_bdm_activities_direction` IN (`outbound`, `inbound`) |
| — | `ck_bdm_activities_direction_channel`: `(channel IN ('call','whatsapp','email')) = (direction IS NOT NULL)` |
| `occurred_at` | `DateTime(timezone=True)` NOT NULL |
| `note` | `Text` nullable (≤ 500 chars, validated in the schema) |
| `created_at`, `updated_at` | `TimestampMixin` |

Indexes: `ix_bdm_activities_bdm_user_id_occurred_at` (my day, counts, bdm-015) and
`ix_bdm_activities_organization_id_occurred_at` (timeline).

Migration style follows `0068_bdm_trips.py`: CHECK constraints (no PG enums), "table exists → return" guard, and
`downgrade()` refuses while any row exists (they are the only record of each activity). No existing table or row changes.

### 4.2 Time rules (service, against `db_now()` read once per request)

- `occurred_at > now` → 422 "When can't be in the future".
- IST date of `occurred_at` < IST today − 7 days → 422 "Activities can be logged up to 7 days back".
- Day boundaries are IST: a day `D` is `[D 00:00 IST, D+1 00:00 IST)`, queried as a UTC range (index-friendly).
- `editable(activity, now)` = IST date of `activity.occurred_at` == IST date of `now`. False → 409 "Only today's activities
  can be changed". On PATCH, a new `occurred_at` must also fall on IST today → 422 "An activity can only be moved within
  today". bdm-015 adds "and that day's report is not submitted" inside `editable()`.

## 5. Backend

### 5.1 Schemas — appended to `schemas.py` (BDM section)

- `BdmActivityChannel = Literal[...]`, `BdmActivityDirection = Literal["outbound", "inbound"]`.
- `BdmActivityCreate` (`extra="forbid"`): `organization_id`, `channel`, `direction | None`, `contact_id | None`,
  `occurred_at` (timezone-aware; naive → 422), `note` (reuses `TripNote` rules: trimmed, ≤ 500, newlines allowed, other
  control characters refused). A model validator enforces V6.
- `BdmActivityUpdate` (`extra="forbid"`, all optional, no `organization_id`): the same fields; the V6 rule is checked in the
  service on the merged result (a channel change can make the stored direction invalid).
- `BdmActivityOut`: `id`, `organization {id, code, name, org_type}`, `bdm {user_id, full_name}`, `contact_id`,
  `contact_name`, `contact_removed` (snapshot present, FK NULL), `channel`, `direction`, `occurred_at`, `note`,
  `created_at`, `updated_at`, `permissions {can_change}`.
- `BdmActivityDayCounts`: `day` (the IST date; not `date`, which would shadow the type in Pydantic), `by_channel` (all six keys, 0 when none), `calls_made`, `organizations_contacted`.
- `BdmActivityPage`: `items`, `total`, `limit`, `offset`; `BdmActivityDayPage` adds `counts: BdmActivityDayCounts`.

### 5.2 Service — new `app/services/bdm_activities.py`

Functions only; nothing commits. Reuses `services.bdm.bdm_context` / `require_manager` / `team_filter`,
`services.bdm_organizations.load_scoped` / `caller_scope`, and `services.bdm_travel.INDIA` / `india_today`.

- `day_range(day) -> (start_utc, end_utc)`.
- `check_time(occurred_at, now)` and `editable(activity, now)` (§4.2).
- `load_readable(db, user, activity_id, lock=False)` — the activity joined to an organization in `caller_scope`; absent →
  404 "Activity not found".
- `rows(filters)` — one query: activity + organization + logger name (no N+1), newest first.
- `day_counts(db, filters, day) -> dict` — one grouped query over the same filters within `day_range(day)`:
  count per channel, outbound calls, `count(distinct organization_id)`.
- `out(activity, user, now)` — output with `can_change` = owner and `editable()`.
- `audit(db, user, action, activity, fields=None)` — `AuditLog(action=f"bdm_activity.{action}",
  entity_type="bdm_activity", entity_id=…)`, metadata: `organization_id`, `channel`, changed field names. Never the note,
  contact name or phone.

### 5.3 Router — new `app/api/bdm_activities.py` (prefix `/bdm`), registered in `main.py`'s router tuple

| Route | Caller | Behaviour |
|---|---|---|
| `GET /bdm/activities?date=&channel=&organization_id=&limit=&offset=` | `bdm` | Own activities on IST `date` (default today; future → 422). Returns `BdmActivityDayPage`; `counts` covers the whole day and the same filters, not the page |
| `POST /bdm/activities` | `bdm` | 201 `BdmActivityOut` |
| `PATCH /bdm/activities/{id}` | owner | 200 `BdmActivityOut` |
| `DELETE /bdm/activities/{id}` | owner | 204 |
| `GET /bdm/organizations/{org_id}/activities?limit=&offset=` | any reader of the org | `BdmActivityPage`, every BDM's activities on that org, newest first |
| `GET /bdm/manager/activities?date=&bdm_user_id=&channel=&limit=&offset=` | `bdm_manager` (team), `super_admin` (all) | `BdmActivityDayPage`; `bdm_user_id` is ANDed with team scope, so it only narrows (outside the team → empty) |

`LIMIT` / `OFFSET` come from `api/bdm.py` (default 50, max 100).

### 5.4 Authorization order (404 → 403 → 422 / 409, as bdm-006)

- **Create:** `bdm_context` (non-BDM → 403 "BDM role required"); `load_scoped(org, lock=True)` (out of type → 404);
  not assigned → 403 "Only the organization's assigned BDM can log activity"; archived → 422 "This organization is
  archived"; contact not on this org → 422; V6 and time rules → 422.
- **Patch / delete:** `load_readable` (404); not the owner → 403 "Only the BDM who logged this activity can change it";
  re-read `FOR UPDATE`; not `editable()` → 409; field rules → 422.
- **Manager / super_admin writes** → 403. **Reads:** `caller_scope` decides which organizations are readable.

### 5.5 Transactions and races

- One transaction per write: service flushes, route commits once; the audit row is in the same transaction; the log line
  is written after the commit.
- **Lock order: organization, then activity** (bdm-006 §5.7). Create, and a PATCH that sets a contact, take the
  organization's `FOR UPDATE` via `load_scoped(lock=True)`. bdm-002's archive, assign and contact delete take the same
  lock, so log-vs-archive, log-vs-reassign and pick-vs-delete-contact are serialized; the assigned and archived checks are
  made after the lock.
- PATCH / DELETE re-read the activity `FOR UPDATE` (`populate_existing`) after the scope check: two concurrent deletes →
  one 204, one 404; a concurrent patch and delete never leave a half write.
- Every time rule in a request uses the same `db_now()` value; near midnight the database clock decides.

## 6. Frontend

### 6.1 Navigation (`lib/navigation.ts`)

`BDM_NAV` gains "Activities" → `/bdm/activities`; `BDM_MANAGER_NAV` gains "Activities" → `/bdm/manager/activities`.
`bdmNav()` badge wrapping is unchanged.

### 6.2 Pages (async server components: `serverApi` → `accessUnavailable` → `PortalShell`, as bdm-001/002/010)

- `app/bdm/organizations/[id]/page.tsx` and `app/bdm/manager/organizations/[id]/page.tsx`: also fetch the first 20 timeline
  items. If only that call fails, the profile renders and the Activity section shows its own error.
- `app/bdm/activities/page.tsx` (+ `loading.tsx`): `?date=` (default IST today), counts strip, list, Log activity.
- `app/bdm/manager/activities/page.tsx` (+ `loading.tsx`): `?date=&bdm=` filters (team from `/bdm/manager/team`), counts
  strip, read-only list.

### 6.3 Components and client

- `lib/bdmActivities.ts`: types, `CHANNEL_LABEL`, `DIRECTION_LABEL`, URL builders, `needsDirection(channel)`.
- `BdmActivityForm`: channel select; direction radio group (shown only for call / WhatsApp / email, cleared on channel
  change); When (`datetime-local`, default now, `max` now; sent via `localToIso` imported from `lib/agentTasks.ts`);
  contact select (optional); note with a 500-character counter. Organization fixed (org profile) or picked with
  `SearchableSelect` over `GET /bdm/organizations?assigned=me&q=` (activities page), which then loads that organization's
  contacts. Writes through `sendJson` / `sendRequest`; 422 → `fieldErrors(detail)` from `lib/bdmTravel.ts`; busy-disabled
  Save; `useLeaveGuard` for a dirty form.
- `BdmActivityItem`: channel label (+ direction), contact or "Name (removed)", `LocalTime`, logger name, note,
  organization link (lists); Edit / Delete only when `permissions.can_change` (Delete confirms with `BdmConfirm`).
- `BdmActivityTimeline` (org profile section "Activity", `SchoolStudentTimeline` markup pattern): Log activity when
  `org.permissions.can_edit` (already means assigned and not archived — no contract change) and the BDM base path; "Load
  more" by offset.
- `BdmActivityCounts`: six channel tiles + "Calls made" + "Organizations contacted".
- A write applies the returned activity locally (no `router.refresh`, avoiding bdm-010 QA10-16). On the activities pages a
  write re-reads that day's page so the counts stay exact. A 403 / 409 on edit or delete shows the reason and makes that item read-only (Edit / Delete hidden); a 404 removes it from the
  list. There is no single-activity GET, so nothing is re-read.

### 6.4 States

- Loading: `loading.tsx` skeletons for the two new pages; busy buttons for writes.
- Empty: "No activity logged yet." (timeline), "No activities on this day." (lists); counts show zeros.
- Error: access → `accessUnavailable`; timeline load failure → "Activity couldn't be loaded. Reload the page to try
  again." inside the section; write failures → field errors or one top message in a status region.

### 6.5 Responsive and accessible

Items are stacked cards; the counts strip wraps; no horizontal overflow at 375 px. Labelled controls, a fieldset/legend for
direction, a polite status region, focus moved to the result (`useFocusAfterRender`), full keyboard use, Escape cancels the
delete confirm.

## 7. Acceptance criteria

| AC | Criterion |
|---|---|
| AC1 | Each of the six channels is loggable against an organization by its assigned BDM; direction required for call / WhatsApp / email and refused for the others (422) |
| AC2 | Future `occurred_at` → 422; older than 7 IST days → 422; exactly 7 days back accepted; naive datetime → 422 |
| AC3 | The day's counts are exact: per channel, outbound calls, distinct organizations; IST boundaries (18:29:59Z vs 18:30:00Z); independent of pagination and of other BDMs / days |
| AC4 | Edit / delete only on the activity's IST day (409 otherwise); a PATCH cannot move it off today (422); `editable()` is the single gate (bdm-015 extends it) |
| AC5 | Authorization: out-of-type org → 404; not assigned → 403; archived → 422 on create; non-owner patch / delete → 403; activity on an unreadable org → 404; manager reads team only (`bdm_user_id` outside team → empty), manager / super_admin writes → 403; it_admin / overseas_admin → 403 |
| AC6 | The organization timeline shows every BDM's activities on it to every reader of the organization, newest first, paginated |
| AC7 | A contact from another organization → 422; deleting the contact keeps the activity with `contact_id` NULL and its `contact_name` |
| AC8 | `bdm_activity.created/updated/deleted` audit rows exist and carry no note or contact name |
| AC9 | Log vs archive is serialized (no activity on an archived organization); two concurrent deletes → one 204 and one 404 |
| AC10 | Migration: chains after `0068_bdm_trips`, single head, upgrade / downgrade round trip, downgrade refuses while rows exist |
| AC11 | UI: timeline, Log / Edit / Delete, counts strip, date and BDM filters, loading / empty / error states |
| AC12 | End to end: a BDM logs, sees it on the timeline and in the counts; the manager sees it; keyboard-only; no overflow at 375 px |

## 8. Tests (written before the code, per task)

Backend (`apps/api/tests/`, helpers `bdm009_helpers.py` reusing `bdm001/002/010_helpers`):
- `test_bdm_009_migration.py` — AC10 (pattern of `test_bdm_010_migration.py`).
- `test_bdm_009_schemas.py` — V6, note rules, naive datetime, `extra="forbid"`.
- `test_bdm_009_service.py` — `day_range`, `check_time`, `editable`, `day_counts` (AC2, AC3, AC4).
- `test_bdm_009_activities.py` — create / list / patch / delete / timeline / manager list (AC1, AC4, AC6, AC7, AC8).
- `test_bdm_009_scope.py` — AC5.
- `test_bdm_009_concurrency.py` — AC9.
- `test_bdm_010_migration.py:38` — the single-head assertion becomes `len(heads) == 1` (the only edit to an existing test).

Web (`apps/web/tests/`): `components/BdmActivityForm.test.tsx`, `BdmActivityTimeline.test.tsx`,
`BdmActivityItem.test.tsx`, `BdmActivityPages.test.tsx`, `lib/bdmActivities.test.ts`, the existing
`BdmOrganizationDetail.test.tsx` / `BdmOrganizationPages.test.tsx` extended, `lib/navigation.bdm.test.ts` updated (AC11).

E2E: `tests/e2e/bdm-009-activities.spec.ts` (AC12), then a Browser Use check of AC1–AC12.

Gates: lite backend set (bdm-001 / 002 / 010 / 009 + ENH-027 schemas), web BDM set, `tsc`, `eslint`, `ruff`, `mypy` (no
new errors over `main`'s 342), `next build`, Playwright. The owner runs the full suites.

## 9. Regression risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | `test_bdm_010_migration.py:38` pins the head to `0068` | Relaxed to one head (§8) |
| R2 | `BdmOrganizationDetail.tsx`, `main.py`, `navigation.ts`, `models.py`, `schemas.py` are also changed by unmerged bdm-006 / bdm-003 | Append-only edits; keep both sides on merge |
| R3 | Migration / DEC numbers collide with in-flight branches | Renumber on whichever merges later; `alembic heads` must print one line |
| R4 | bdm-002's contact delete would fail on a RESTRICT FK | `ON DELETE SET NULL` + AC7 test through bdm-002's route |
| R5 | A timeline fetch failure breaking the org profile | Section-level error; page test |
| R6 | Read-only import of `localToIso` from the agent tasks module | Accepted; no change to that file |
| R7 | Duplicate on double POST | Busy-disabled Save; same-day delete; recorded |

No existing route, field or response changes. bdm-002 organization output is unchanged.

## 10. Documentation (updated in the same change)

`docs/decisions/PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-064`), `docs/delivery/BDM_CRM_BACKLOG.md` (bdm-009 status line),
`docs/architecture/DATA_MODEL.md` (`bdm_activities`), `docs/quality/RTM.md` (bdm-009 rows).

## 11. Completion gates

bdm-009 is complete only when AC1–AC12 pass with the §8 tests, the build and type checks are clean, the migration round
trip passes, responsive and accessibility checks pass in the browser, and the documentation above is updated.
