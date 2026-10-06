# bdm-008 — Follow-ups and tasks (design)

- **Item:** `bdm-008` (`docs/delivery/BDM_CRM_BACKLOG.md` §4). Depends on bdm-002 (organizations) and bdm-007 (merged,
  `0072_bdm_meeting_reports`, which created the minimal `bdm_tasks` table and the one-follow-up-per-appointment sync).
- **Decision:** `DEC-SCOPE-075`. **Migration:** `0077_bdm_tasks_followups` (down_revision `0076_tel_catalogue`; renumbered from `0076` on merging `main` @ `784738e7`, where tel-002 holds `DEC-SCOPE-074` / `0076`).
- **Branch:** `feature/bdm-008-follow-ups` from `origin/main` @ `e73dfa60`.
- **Evidence:** `EVID-016` `BDM Functionalities.md` (`DERIVED_BLUEPRINT`) §5 Calendar (172–196: "Follow-ups", "Tasks"), §13
  Management dashboard alerts (413–434: "Follow-up overdue"), §15 My Day (476–506: "4 College follow-ups, 2 Agent follow-ups,
  1 MoU follow-up"), §4 Common reminders (1254–1334: "Follow-up reminder", "Task reminder"); backlog D18 (09:00 IST on the due day).
- **Skills applied:** superpowers:brainstorming, api-and-interface-design, frontend-ui-engineering, security-and-hardening.

## 1. Goal

A BDM sees every follow-up and task they owe in one place — Today, Overdue, Upcoming, Done, Cancelled — counted by organization
type. Follow-ups filed on a meeting report (bdm-007) appear automatically; the BDM can add their own follow-ups and tasks, complete
any open item, and edit or cancel their own. Overdue is decided on IST dates. Nothing is ever deleted. Managers read their team's.
The later items (reminders bdm-012, calendar bdm-013, My Day bdm-014, the "Follow-up overdue" tile bdm-023, MoU follow-ups bdm-005)
read the list and filters built here.

## 2. Scope

| In | Out (owner item) |
|---|---|
| Migration `0076`: `notes`, `cancelled_at`, `cancel_reason` on `bdm_tasks` (+ backfill) | MoU-sourced follow-ups — `source='mou'` stays reserved (bdm-005) |
| `GET/POST /bdm/tasks`, `PATCH /bdm/tasks/{id}`, `POST …/complete`, `POST …/cancel` | Task / follow-up reminders (bdm-012) |
| Buckets today / overdue / upcoming / open / done / cancelled on IST dates; counts by bucket and by organization type | Calendar (bdm-013), My Day tiles (bdm-014) |
| `/bdm/follow-ups`, `/bdm/manager/follow-ups`, "Follow-ups & tasks" on the organization profile | "Follow-up overdue" alert tile (bdm-023) |
| Archiving an organization cancels its open items (reason "Organization archived") | Deactivated BDM's items (bdm-025) |
| After Done: "Log activity" / "Book appointment" links | A stored activity → task link (bdm-009's deferred V3) |

## 3. Owner decisions (2026-10-05/06, in-session, `EXPLICIT_APPROVAL`)

| # | Question | Answer |
|---|---|---|
| F1 | How much of §4/§5/§13/§15 does bdm-008 deliver? | **Data + pages only.** MoU source reserved for bdm-005; reminder, calendar and alert tile read bdm-008's filters later |
| F2 | What can the page do to a follow-up created by a meeting report? | **Complete only.** Its date is changed or cleared through the meeting report (bdm-007 R7: the date lives on the appointment) |
| F3 | Manual items | **Lean set:** kind (follow-up / task), title ≤ 200, due date (IST, today or later), optional organization (one the BDM may edit, not archived), optional notes ≤ 2000. Edit title / notes / due date while open; complete; cancel with a required reason. Done and cancelled are final (no reopen). Date only, no time |
| F4 | Manager | **Read the team.** Only the assignee writes; super_admin reads all (D26: managers never own BDM work) |
| F5 | Counts grouping | **The 7 organization types + "No organization".** Counts use the list's own filters, so they add up to the list |
| F6 | Organization archived with open items | **Cancel them** in the archive's transaction with reason "Organization archived"; restore does not reopen them |
| F7 | After completing | **Links only:** "Log activity" (the organization's activity section) and "Book appointment" (prefilled booking). No server change |

**Defaults taken (not asked; consistent with bdm-006/007/009):** no idempotency key (row lock + state check make a repeat a 409);
no ETag (not contracted; one writer per row); no general rate limiter — a create cap of 200 manual items per BDM per IST day
(bdm-009 V10's 409 pattern). Query parameters keep the API's snake_case; action sub-paths (`/complete`, `/cancel`) follow
`/archive`, `/assign`, `/confirm`.

## 4. Data model (migration `0077_bdm_tasks_followups`)

`bdm_tasks` gains three nullable columns; nothing is dropped or retyped.

| Column | Type | Rule |
|---|---|---|
| `notes` | varchar(2000) NULL | manual items only (the API never writes it on an outcome follow-up) |
| `cancelled_at` | timestamptz NULL | `ck_bdm_tasks_cancelled`: `(status = 'cancelled') = (cancelled_at IS NOT NULL)` |
| `cancel_reason` | varchar(500) NULL | `ck_bdm_tasks_cancel_reason`: `cancel_reason IS NULL OR status = 'cancelled'` |

- **Backfill (before the CHECK is added; set-based, idempotent):** rows already `cancelled` (bdm-007's "date cleared") get
  `cancelled_at = updated_at`, `cancel_reason = 'Follow-up date removed from the meeting report'`.
- **Fresh database guard (0072's idiom):** when `0001`'s `create_all` already built the columns from the models, skip the DDL but
  still run the backfill.
- **Downgrade** refuses while a `manual` task exists ("Cannot downgrade 0077_bdm_tasks_followups: manual tasks exist …") — their
  notes and reasons would be lost; otherwise drops the two CHECKs and three columns (outcome follow-ups lose only derivable data).
- `BdmTask` in `models.py` gains the same columns and CHECKs. `BDM_TASK_CANCEL_REASON_*` constants live in `services/bdm_tasks.py`.

### 4.1 bdm-007's sync (one targeted change)

`services/bdm_appointments.sync_follow_up` keeps its behaviour table (bdm-007 spec §4.3) and only fills the new columns:

| Event | Change |
|---|---|
| Date cleared (row `open` → `cancelled`) | also `cancelled_at = db now`, `cancel_reason = 'Follow-up date removed from the meeting report'` |
| Date set again (row `cancelled` → `open`) | also `cancelled_at = None`, `cancel_reason = None` (this includes a follow-up cancelled by an archive: the BDM's explicit report edit, allowed only on the filing day, wins) |

## 5. Rules

- **Today** (IST) = `today_ist(db_now())`, read once per request.
- **Buckets:** `today` = open and `due_on = today`; `overdue` = open and `due_on < today`; `upcoming` = open and `due_on > today`;
  `open` = open (the organization section); `done`; `cancelled`. Every row carries `overdue: bool` (open and `due_on < today`).
- **Create (manual only):** caller is a `bdm` with a profile; `due_on ≥ today`; organization, when given, resolves through
  `bdm_organizations.load_scoped(lock=True)` (out of scope → 404), must be assigned to the caller (403 "Only the assigned BDM can add
  tasks for this organization") and not archived (422 "This organization is archived — restore it before adding tasks"); daily cap;
  assignee = caller, `source = 'manual'`, `status = 'open'`.
- **Edit:** open + manual + assignee. `title`, `notes`, `due_on`. A **changed** `due_on` must be ≥ today (an unchanged past date
  is accepted). Values equal to the stored ones are not changes (no audit, no `updated_at` bump).
- **Complete:** any open item of the assignee. `status = done`, `completed_at = db now`.
- **Cancel:** open + manual + assignee; `reason` required (bdm-006's `BdmAppointmentReason`, ≤ 500). `cancelled_at = db now`.
- **Archive (bdm-002 route):** after the existing checks, one `UPDATE bdm_tasks SET status='cancelled', cancelled_at=now(),
  cancel_reason='Organization archived', updated_at=now() WHERE organization_id = :org AND status = 'open'` — every assignee's items.
  Audit metadata gains `tasks_cancelled: n` **only when n > 0** (an archive with nothing open writes the same audit as today).
- **Reassignment (bdm-002)** does not move items: they stay with the BDM who owes them.
- Done and cancelled rows are never deleted or reopened by this API (F3).

## 6. API (`app/api/bdm_tasks.py`, `app/services/bdm_tasks.py`; registered in `main.py`)

### 6.1 `GET /api/v1/bdm/tasks`

| Param | Rule |
|---|---|
| `bucket` | `today` (default) \| `overdue` \| `upcoming` \| `open` \| `done` \| `cancelled`; else 422 |
| `kind` | `follow_up` \| `task` |
| `org_type` | one of the 7 organization types \| `none` (no organization) |
| `organization_id` | uuid |
| `bdm_user_id` | uuid; managers / super_admin only (a `bdm` → 422 "bdm_user_id is only for managers", bdm-006's rule); ANDed with scope |
| `limit`, `offset` | `app.api.bdm.LIMIT` / `OFFSET` (default 50, 1–100) |

Scope (`caller_filters`): `bdm` → own (`assignee_user_id = me`, needs a profile); `bdm_manager` → team (sub-select of
`bdm_profiles.reporting_manager_user_id`); `super_admin` → all; any other role 403 "BDM role required".

Response `BdmTaskPage`:

```
{ items: BdmTaskOut[], total, limit, offset, today: "YYYY-MM-DD",
  counts: { buckets: {today, overdue, upcoming, done, cancelled}, by_org_type: [{org_type: str|null, count}] } }
```

- `counts.buckets` = every filter **except** `bucket` (the tab badges).
- `counts.by_org_type` = every filter **except** `org_type`; non-zero groups only, in `BDM_ORG_TYPES` order then `null`.
  Without an `org_type` filter they sum to `total`; with one, that group's count equals `total` (AC4).
- Order: open buckets `due_on, created_at, id`; `done` `completed_at desc, id`; `cancelled` `cancelled_at desc, id`.
- One page query joins organization (outer), assignee and source appointment (outer) — no N+1. Count queries use the same filter list.

`BdmTaskOut`:

```
id, kind, title, notes, due_on, status, source, overdue,
organization: {id, code, name, org_type, archived} | null,
appointment: {id, code} | null,
assignee: {id, full_name, active},
completed_at, cancelled_at, cancel_reason, created_at, updated_at,
permissions: {can_edit, can_complete, can_cancel}
```

`can_complete` = caller is the assigned `bdm` and status open; `can_edit` = `can_cancel` = that and `source = 'manual'`.

### 6.2 `POST /api/v1/bdm/tasks` → 201 `BdmTaskOut`

Body `BdmTaskCreate` (`extra="forbid"`): `kind` (required), `title` (required, trimmed, 1–200, single line), `due_on` (required,
YYYY-MM-DD, bdm-010's strict date parser), `organization_id` (optional), `notes` (optional, trimmed, ≤ 2000, multi-line; blank → null).
Order: role/profile → 403; organization (404 / 403 / 422, §5); `due_on` → 422 "Due date can't be in the past"; cap → 409
"You've added 200 tasks today"; insert; audit; commit; log.

### 6.3 `PATCH /api/v1/bdm/tasks/{id}` → 200 `BdmTaskOut`

Body `BdmTaskUpdate` (`extra="forbid"`): any of `title` (non-null), `notes` (null clears), `due_on` (non-null). Omitted = unchanged.

### 6.4 `POST /api/v1/bdm/tasks/{id}/complete` → 200 `BdmTaskOut` (no body)

### 6.5 `POST /api/v1/bdm/tasks/{id}/cancel` → 200 `BdmTaskOut`; body `{reason}`

### 6.6 Order of every write on `{id}` (each refusal is one rule)

1. scope → 404 "Task not found" (another BDM's id is indistinguishable from a missing one);
2. lock: an outcome follow-up locks its **appointment first**, then the task (bdm-007's order); a manual task locks the task;
3. owner (caller is a `bdm` and the assignee) → 403 "Only the assigned BDM can change this task" (logged `bdm_task_write_refused`);
4. state: not open → 409 "This task is already done" / "This task was cancelled";
5. source (edit / cancel only): not manual → 409 "Change this follow-up from its meeting report";
6. validation → 422; then the change, audit, one commit, log.

### 6.7 Errors

`{"detail": str}` for 403/404/409/service 422; FastAPI's list for schema 422 (custom validator messages: "Title is required",
"Title contains invalid characters", "Notes contains invalid characters", "Enter a valid due date", "Reason is required").

### 6.8 Compatibility

Additive only. Unchanged: `BdmAppointmentOut.follow_up {id, due_on, status}`, `/bdm/appointments/*`, the organization envelope and
the archive / restore response. The archive gains a side effect on `bdm_tasks` (F6) and conditional audit metadata.

## 7. Transactions, concurrency, failure

- One commit per route; services never commit; audit in the same transaction (fail closed). Any exception before commit writes
  nothing.
- **Lock order (deadlock-free):** organization → task (create, archive); appointment → report → task (report edit, unchanged);
  appointment → task (complete an outcome follow-up); task (manual edit / complete / cancel). No path locks a task before an
  organization or an appointment.
- Races: complete ∥ complete → the loser re-reads `done` → 409. Complete ∥ report date edit → serialized on the appointment; the
  edit then meets `done` → bdm-007's 409, or the complete meets the moved date and completes it. Complete ∥ archive → the archive's
  `WHERE status='open'` skips a done row; a complete after the archive meets `cancelled` → 409. Create ∥ archive → serialized on the
  organization lock; a create after the archive → 422.
- Midnight IST: every rule uses the one `db_now()` of the request.
- The daily cap is soft (two concurrent creates may pass it by one) — bdm-009's accepted bound.

## 8. Security (security-and-hardening review)

| Concern | Control |
|---|---|
| Authentication | `get_current_user` (httpOnly `SameSite=Lax` session cookie); unchanged |
| Authorization / IDOR | every `{id}` resolves through `load_scoped` (scope filter in SQL; out of scope = 404); writes need the assignee (403, logged); list filters only narrow scope; `organization_id` on create resolves through the organization scope |
| Role escalation / mass assignment | `extra="forbid"`; assignee, source, status, timestamps, appointment link, `cancelled_*` are server-owned; managers / super_admin never write |
| Input validation | lengths, enums, strict dates, control characters (single-line title; multi-line notes); IST date rules on the server clock |
| XSS | React text rendering only (`white-space: pre-wrap` for notes); no `dangerouslySetInnerHTML` |
| CSRF | JSON `POST`/`PATCH` under `SameSite=Lax`; no form-encoded endpoint |
| SQL injection | ORM / bound parameters; the migration SQL has no input |
| Token / session / secrets | none added or changed |
| Sensitive logs | logs and audit carry ids, kind, source, field names, counts — **never** title, notes or reason text (tested) |
| Rate limiting | the per-day create cap (409); reads are paginated (≤ 100) |
| Audit | `bdm_task.create` `{kind, organization: bool}`, `.update` `{fields}`, `.complete` `{source}`, `.cancel` `{}`; `bdm_organization.archive` `{tasks_cancelled}` when > 0 |

## 9. Frontend (frontend-ui-engineering)

- **Navigation:** "Follow-ups" after Appointments in `BDM_NAV` (`/bdm/follow-ups`) and `BDM_MANAGER_NAV` (`/bdm/manager/follow-ups`).
- **Pages** (server components; `accessUnavailable` gate; `loading.tsx` with `PortalLoading`): `/bdm/follow-ups` ("Your follow-ups
  and tasks", "Dates are India time (IST).") and `/bdm/manager/follow-ups` ("Your team's follow-ups and tasks").
- **`BdmTasksPanel`** (client; `BdmAppointmentsPanel`'s URL-state pattern: `?bucket=&kind=&org_type=&bdm=&offset=`; every URL value
  checked before it reaches the API):
  - Tabs: a `<nav aria-label="Follow-up lists">` of buttons with `aria-current="page"` on the active one and the count in text
    ("Overdue (2)"); the Overdue count is the only one styled as a warning, and it is also words.
  - Organization type chips: buttons with `aria-pressed`, "College 4", "No organization 1", wrapping; pressing one filters, pressing
    it again clears. Kind select (All / Follow-ups / Tasks). Managers get the BDM `SearchableSelect` (`teamMemberSearch`).
  - "Add follow-up or task" (BDM only) opens `BdmTaskForm`; the new item is shown with a notice in the panel's one live region.
  - Rows (`BdmTaskItem`, a `<ul>` of cards, single column on mobile): title (kind as a text badge), organization link + type + "Archived"
    badge, "Due 22 Sep 2026" + "Overdue" text badge, "From APT-000123" (link to the appointment) or "Added by you", notes
    (`pre-wrap`), done / cancelled time and reason, assignee (manager view). Actions from `permissions` only: **Done**, **Edit**,
    **Cancel** (bdm-006's `BdmAppointmentReasonForm`).
  - After Done: the row leaves the open tab; the live region says "Marked done." and, when the item has an organization that isn't
    archived, offers **Log activity** (`/bdm/organizations/{id}#org-{id}-activity`) and **Book appointment**
    (`/bdm/appointments/new?organization={id}`).
  - States: first load "Loading follow-ups…" (`role=status`); tab / filter switches keep the current list at reduced opacity with
    `aria-busy` and "Updating…"; failed read → `role=alert` + **Retry**; per-tab empty text ("Nothing due today.", "No overdue
    follow-ups.", "Nothing upcoming.", "Nothing done yet.", "Nothing cancelled.") + Add for the BDM, or "No items match these
    filters." + Clear filters; past the end → "Go to the first page". A write's 409 → "This item changed elsewhere." and the list
    reloads; 403/404 → the message and reload; network drop → `NOT_COMPLETED` and the form keeps its text.
  - Pagination: Previous / Next with "Showing 1–50 of 120" (`BdmAppointmentsPanel`'s).
- **`BdmTaskForm`** (create / edit): Kind (radio group, create only), Title (required), Due date (`type=date`, `min` = IST today,
  "(IST)"), Organization (`SearchableSelect` + `myOrganizationSearch()`, optional, create only; prefilled and fixed on the organization
  section), Notes (textarea, `maxLength` 2000, character count). "(required)" labels; `autoFocus` on Title; Escape cancels and focus
  returns to the opener (`useFocusAfterRender`); submit disabled while busy ("Saving…"); 422s placed on their field
  (`aria-invalid` + `aria-describedby`); text kept on failure.
- **`BdmOrganizationTasks`** (organization profile, after Activity): the organization's **open** items (`bucket=open&organization_id=`),
  "Add task" when the BDM view may edit the organization; read-only on the manager view. First page read on the server alongside the
  organization (`firstTaskPage`, never rejects → "Try again"); notices go to the profile's live region; reloads when the organization
  is archived on the page (the archive cancelled them).
- No new dependency; existing classes (`action-card`, `btn`, `badge`, `field`, `form-error`, `muted`, `empty`); no colour-only state;
  works at 320 px (wrapping flex, no fixed widths).

## 10. Acceptance criteria (testable)

| AC | Criterion | Verified by |
|---|---|---|
| AC1 | Follow-ups come from meeting outcomes (bdm-007 sync, listed here) and can be created manually; `source='mou'` is accepted by the table for bdm-005 | API tests; migration test |
| AC2 | Overdue / today / upcoming use the IST date: a task due on the IST day that has just started is "today", not "overdue", at 18:31 UTC of the previous UTC day | service + API tests with a pinned `db_now` |
| AC3 | Completed and cancelled items are kept, listed under Done / Cancelled with their time (and reason) and never reopened by this API | API tests |
| AC4 | `counts.by_org_type` sums to `total` without an `org_type` filter; with one, that group's count equals `total`; `counts.buckets[b]` equals the `total` of `bucket=b` | API tests |
| AC5 | Scope: another BDM's task → 404; a manager reads the team and gets 403 on every write; super_admin reads all; `bdm_user_id` can't widen scope | API tests |
| AC6 | An outcome follow-up can be completed here but not edited / cancelled (409); its date still moves only through the report | API tests |
| AC7 | Archiving an organization cancels its open items with "Organization archived" in the same transaction; restore leaves them cancelled | API tests |
| AC8 | Task text never appears in logs or audit metadata | API test inspecting audit rows / caplog |
| AC9 | The pages show tabs with counts, type chips that filter, the list and its loading / empty / error states; managers read only | component tests; e2e |

Negative: due date before IST today on create → 422; a changed past due date on edit → 422; unknown field → 422; organization
assigned to another BDM → 403; archived organization → 422; complete twice → 409; edit / cancel a done item → 409.

## 11. Regression risks

1. `models.py` / `schemas.py` are shared single files (bdm-004 / bdm-017 / tel-001 also edit them) — additive edits only.
2. `test_bdm_007_migration.test_models_match_the_migration` pins `bdm_tasks`' exact column set → extended.
3. Migration chain: `test_tel_001_migration` (and any test asserting a single head = `0075`) → "on the chain"; isolated-db fixtures
   that drop `bdm_tasks` keep working (the table is dropped whole).
4. `sync_follow_up` gains the `cancelled_*` writes → `test_bdm_007_reports` follow-up tests must stay green (+ new assertions).
5. The archive route gains a side effect → `test_bdm_002_organizations` audit list stays exactly the same when nothing is open.
6. `BdmOrganizationDetail` gains a section and a prop → `BdmOrganizationDetail.test.tsx`, both organization pages.
7. Navigation arrays gain an entry → `navigation.bdm.test.ts` and any snapshot of the BDM nav.

## 12. Testing (lite only; the owner runs the full suites)

- Backend new: `test_bdm_008_migration.py`, `test_bdm_008_schemas.py`, `test_bdm_008_service.py`, `test_bdm_008_tasks.py`,
  `test_bdm_008_scope.py`, `test_bdm_008_concurrency.py`, `test_bdm_008_archive.py`; helpers `tests/bdm008_helpers.py`.
- Backend updated: `test_bdm_007_migration.py`, `test_bdm_007_reports.py`, `test_tel_001_migration.py` (head), any other single-head
  assertion found by grep.
- LITE = `tests/test_bdm_008_*.py tests/test_bdm_007_*.py tests/test_bdm_002_organizations.py tests/test_tel_001_migration.py`.
- Web: `tests/lib/bdmTasks.test.ts`, `BdmTasksPanel.test.tsx`, `BdmTaskForm.test.tsx`, `BdmTaskItem.test.tsx`,
  `BdmOrganizationTasks.test.tsx`, `BdmOrganizationDetail.test.tsx`, `navigation.bdm.test.ts`; `tsc --noEmit`; eslint on changed files.
- E2E: `bdm-008-follow-ups.spec.ts` written; run during browser validation.
- Not claimed complete until browser validation and the independent Codex review.
