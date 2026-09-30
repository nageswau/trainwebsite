# ENH-030 — Daily Class Attendance for School Students: Design

**Status:** Draft for review, 2026-09-30. Branch `feature/enh-030-class-attendance` (from `main` @ `32e76a1`).
**Feature ID:** ENH-030. **Decision:** `DEC-SCOPE-038` (provisional number; renumber on merge if taken).
**Source:** `docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-030 (`DERIVED_BLUEPRINT`, from `School CRM.md` = `EVID-014`).

## 1. Problem (audit result, 2026-09-30, Graphify-led, verified against the files)

`School CRM.md` treats "Attendance" as a routine, always-shown metric (Teacher Dashboard Part B §3, Parent Dashboard §23,
Student Dashboard Part B §5, Student 360° §35 / Part B §8). The code has no School-domain daily attendance:

- `Attendance` / `AttendanceCorrection` (`models.py:145-165`) are the IT training domain's per-batch attendance (`student_id` → `users`).
- `SchoolActivityAttendance` (`models.py:1219`) is attendance at a one-off scheduled activity; `SchoolSkillAttendance` is per skills session.
- The Student 360° Attendance tab shows the fixed note "Daily and period attendance is not tracked yet (ENH-030)."
  (`student_360.py:38`, ENH-013 D7).

Facts that shape the design (each verified):

| Fact | Evidence |
|---|---|
| No class/section entity and no teacher-to-class assignment. A teacher is assigned per student. | `SchoolStudent.assigned_teacher_user_id` `models.py:1037`; `_scoped_students_query` `schools.py:873-893`; ENH-013 D3 ("grade/section assignment is a future decision, not built") |
| `grade_or_class` is free text ("Grade 5-A"); `grade_level`/`section` are structured but optional | `models.py:1032,1046,1052` |
| School routers are prefixed `/school`; the school comes from the user's profile, never the path | `main.py:58`; `_own_school_id` `schools.py:340` |
| School students have no login; there is no `school_student` role or student portal | `SchoolStudent` docstring (DEC-ROLE-004); `web/lib/navigation.ts` |
| Teacher RBAC bundle is read-only today | `core/rbac.py:41` `school:teacher:assigned:read` |
| DEC-SCOPE-011: Teacher "view … attendance"; Coordinator "track attendance" | `PRODUCT_DECISION_REGISTER.md` §DEC-SCOPE-011 |
| IT `Attendance.status` ∈ present/absent/late/excused (schema regex only) | `schemas.py:168,180` |
| Transfer approval locks the student row `FOR UPDATE` and clears `assigned_teacher_user_id`/`section` | `school_transfers.py:398,443-445` |
| 360 tabs are built from `_overview_payload`, so an additive overview key reaches the Parent card, the 360 view and the progress report reader set with one query | `student_360.py:69,94`; `schools.py:1320` |

## 2. Decisions (user, in-session, 2026-09-30: "go with your recommendations for all six" — `EXPLICIT_APPROVAL`)

| ID | Decision |
|---|---|
| D1 | **"Class" = the teacher's currently assigned students** in their own school (existing `assigned_teacher_user_id` rule). No class/section model; ENH-013 D3 stands. |
| D2 | **Writer = `school_teacher`, assigned students only.** Coordinator/Principal read only in v1 (Coordinator keeps activity attendance). Coordinator marking is a possible follow-up. Additive to DEC-SCOPE-011 (a new teacher write, scoped like the portfolio's teacher write, `portfolio.py:78-92`). |
| D3 | **"Student dashboard" = the Student 360° Attendance tab.** No student login or portal is built. |
| D4 | **Status ∈ `present` \| `absent` \| `late` \| `excused`**, mirroring IT `Attendance`; enforced by a DB `CHECK` and the schema. A missing row = "not marked", never absent (the STU-006-AC02 invariant). |
| D5 | **One record per student per day**: `UNIQUE (school_student_id, session_date)`; re-marking updates. Period-level is out of scope. |
| D6 | **Tier gate = `require_school_entitlement(..., service_key=None)`** (any valid, unexpired tier — the rule free-text activities use). No new `TIER_SERVICES` key. |

Design choices made here (reviewable, not user decisions):

| ID | Choice | Why |
|---|---|---|
| C1 | Records carry `school_id` stamped at mark time; **readers see only records whose `school_id` equals the student's current school** | After a transfer, the new school's staff must not see the old school's register (no cross-institution exposure); old rows are kept (data preserved). Parents lose the old school's history in the UI — accepted for v1. |
| C2 | Unmarked rows start with **no selection** in the UI; "Mark all present" fills only unselected rows; Save sends the selected rows | Never defaults a student to a status the teacher did not choose (STU-006-AC02 spirit); still one Save for the whole class. |
| C3 | Read summary = the **30 most recent marked days** (counts per status + the list), not a percentage | One definition for every surface; avoids deciding what "attended" means (IT counts late/excused as attended). |
| C4 | A future `session_date` (school time zone, `Asia/Kolkata`) is rejected; past dates are allowed (corrections), every write audited | No school calendar exists to bound it; the audit row is the control. |

## 3. Alternatives considered

1. **Endpoint shape** — (a) `POST /schools/{school_id}/classes/{grade_or_class}/attendance` (backlog): rejected — no `school_id` path
   convention, free-text class in the URL. (b) **`PUT /school/attendance` scoped by the caller** — chosen: matches `/school` routing and
   the ENH-011 `PUT … /attendance` upsert. (c) Per-student `PUT /school/students/{id}/attendance`: rejected — not one action.
2. **Where the code lives** — (a) extend `schools.py` (already ~2,000 lines, shared by six ENH items); (b) **a new `school_attendance.py`
   router** — chosen, the ENH-005/011/013 precedent. Read summary helper lives there too and is imported by `schools._overview_payload`
   via a lazy import (the `_skills()` precedent, `schools.py`) to avoid a circular import.
3. **Write template** — (a) `schools.mark_attendance` (raw `dict`, select-then-insert loop, 422 for scope); (b) **`school_skills.mark_skill_attendance`**
   (typed schema, `extra="forbid"`, `pg_insert … on_conflict_do_update`) — chosen: typed, one statement, race-free on the unique key.
4. **Reuse IT `Attendance`** — rejected: its `student_id` references `users`; school students are not users.
5. **Reuse `SchoolActivityAttendance` with a synthetic daily "activity"** — rejected: boolean `present` only, pollutes activity counts in
   `/school/dashboard`, `/school/reports`, ENH-016 and ENH-018.
6. **Frontend write helper** — (a) `lib/skills.ts` `send` (skills-specific); (b) **widen `sendJson`'s method type to include `"PUT"`** —
   chosen: one-word, backwards-compatible change; no new helper.

## 4. Data model

New table `school_attendance_records` (model `SchoolAttendanceRecord`, migration `0046_school_attendance_records`, create-table only):

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `school_student_id` | UUID FK `school_students.id`, not null | |
| `school_id` | UUID FK `schools.id`, not null | stamped from the student at mark time (C1) |
| `session_date` | `Date`, not null | |
| `status` | `String(20)`, not null | `CHECK status IN ('present','absent','late','excused')` (`ck_school_attendance_status`) |
| `marked_by_user_id` | UUID FK `users.id`, not null | last writer |
| `created_at`, `updated_at` | timestamptz, `server_default now()` | `updated_at` set on upsert |

`UNIQUE (school_student_id, session_date)` named `uq_school_attendance_student_date`; its index serves every query in this spec (roster: student IN (...) AND date; summary: student ORDER BY date DESC), so no other index is created (review A4). No existing table is altered; no existing row is read
or written; `downgrade()` drops indexes then the table. The migration follows `0040_school_activity_feedback.py` (skip if the table already
exists, for `create_all` dev databases).

## 5. API

Router `apps/api/app/api/school_attendance.py`, `APIRouter(prefix="/school", tags=["school-attendance"])`, registered in `main.py`.

### 5.1 `GET /school/attendance?date=YYYY-MM-DD` — the teacher's roster for a day

- Role: `school_teacher` only → else `403 "Teacher role required"`. School: `_own_school_id(user)`.
- `date` optional → defaults to today (IST, `_today_ist()`); a future date → `422 "Attendance cannot be marked for a future date"`.
- Students = `_scoped_students_query(db, user, school_id)` (own school AND assigned to this teacher), ordered by `grade_or_class`, `full_name`.
- Response `{"session_date", "today", "students": [{"id", "full_name", "grade_or_class", "status": <str|null>}]}` where `status` is that day's
  record **for the student's current school** or `null`. `today` lets the UI cap the date picker without client time-zone logic.
- Pure read: no DB write, one `logger.info("school_attendance_roster_read")`.

### 5.2 `PUT /school/attendance` — mark the class in one action

Body `SchoolAttendanceIn`: `{"session_date": date, "records": [{"student_id": UUID, "status": "present"|"absent"|"late"|"excused"}]}`,
`extra="forbid"`, 1–500 records (the IT `AttendanceBulkIn` limit, review A2), unique `student_id`s (an `AfterValidator` calling the existing `_unique_ids`, like `_unique_enrollments`, `schemas.py:1408`).

One transaction, in this order:
1. Role `school_teacher` → else 403. `school_id = _own_school_id(user)`.
2. `session_date > _today_ist()` → 422.
3. **Lock and re-check scope:** records are sorted by `student_id` first (one lock order for every save, review A3); `SELECT … FROM school_students WHERE id IN (:ids) ORDER BY id FOR SHARE`. If any id is missing, not in
   `school_id`, or not `assigned_teacher_user_id == user.id` → `403 "One or more students are not assigned to you"`; nothing written.
   (`FOR SHARE` blocks a concurrent transfer approval / reassignment — both take the row for update — until this commits; ordered by id so
   two concurrent calls cannot deadlock.)
4. `await require_school_entitlement(db, user, school_id, None)` — after scope, before any write (its denial commits only its audit row).
5. Read the day's existing statuses for the listed students (under the lock) to build the audit `changes` list (review A5).
   Then `pg_insert(SchoolAttendanceRecord).values([...]).on_conflict_do_update(constraint="uq_school_attendance_student_date",
   set_={status, school_id, marked_by_user_id, updated_at=now()})`.
6. `AuditLog(action="school.daily_attendance_mark", entity_type="school", entity_id=str(school_id),
   metadata_json={"session_date", "count", "statuses": {status: n}, "changes": [{"student_id", "from", "to"}]})` — `changes` lists only
   rows whose status actually changed (`from` is null for a first mark), so "who marked this child absent, and when" is answerable (review S5).
7. `commit`; `logger.info("school_attendance_marked", …ids and counts only)`.
8. Return the same body as §5.1 for `session_date`.

Idempotent: a retry of the same body leaves the same rows (one extra audit row). Two tabs of the same teacher: last write wins per row,
never a duplicate (unique key + upsert). Students not listed stay as they were (partial rosters allowed).

### 5.3 Read surfaces (additive keys only)

- **`_overview_payload`** (`/school/students/{id}/overview`, same reader scope as today) gains
  `"daily_attendance": {"counts": {"present","absent","late","excused"}, "recent": [{"session_date","status"}]}` — the 30 most recent
  records for the student at their current school, newest first; counts over those same records (C3). Built by
  `school_attendance.daily_attendance_summary(db, student)`.
- **360 Attendance tab** (`build_360`): data gains `"daily": overview["daily_attendance"]`; tab count = activities + skill sessions +
  `len(daily.recent)`; `NOT_TRACKED["attendance"]` is deleted. School roles only, service roles stay `restricted` (unchanged).
- **Unchanged on purpose:** `/school/dashboard` and `/school/reports` `attendance` (activity attendance), ENH-016 analytics, timeline,
  progress-report PDF body (the PDF renders named sections, not every overview key).

## 6. Frontend

- **`app/school/teacher/attendance/page.tsx`** (server): reads `searchParams.date`, loads `/auth/me` + `GET /school/attendance?date=`,
  errors → `accessUnavailable(e)` (a 422 for a bad/future date shows that message). Renders `PortalShell nav={SCHOOL_NAV.teacher}` +
  `<SchoolDailyAttendance roster={…} />`. Plus `loading.tsx` (skeleton, `aria-busy`), following `parent/dashboard/loading.tsx`.
- **`components/SchoolDailyAttendance.tsx`** (client), modelled on `SchoolSkillAttendance`'s roster:
  - Date input (`max={roster.today}`); changing it navigates to `?date=` (confirm first when there are unsaved changes).
  - One `fieldset` per student (legend = name + grade) with four labelled radios (≥44 px targets, wraps on a phone — no horizontal scroll);
    saved status preselected; unmarked rows unselected with a "Not marked" badge (C2).
  - "Mark all present" (fills unselected rows only), one **Save attendance** button, "Unsaved changes" flag, `beforeunload` + link-click guard.
  - Save → `sendJson("/api/v1/school/attendance", "PUT", {session_date, records})` for selected rows. Busy: controls disabled, "Saving…".
    Success: `FormMessage` "Attendance saved for N students on <date>." (+ " M left unmarked." when any), `router.refresh()`.
    Failure: `FormMessage` with the server `detail` (403 scope, tier 403, 422) or `NOT_COMPLETED`; marks are kept.
  - Empty roster: "No students assigned to you yet. Your School Coordinator assigns students to teachers."
- **`lib/navigation.ts`**: `SCHOOL_NAV.teacher` = `["dashboard", "attendance"]`.
- **`lib/apiErrors.ts`**: `sendJson` method type `"POST" | "PATCH" | "PUT"`.
- **`components/SchoolChildOverview.tsx`**: optional `daily_attendance?` on `ChildOverview`; `ChildStatusRow` shows a metric
  "Attendance (last N marked days)": "18 present · 1 late · 1 absent · 0 excused", or "Not marked yet" when `recent` is empty; nothing when
  the key is absent (older API).
- **`components/Student360Panels.tsx`**: attendance body adds a "Daily attendance" summary line + table (Date, Status) when
  `d.daily?.recent.length`; `EMPTY_TEXT.attendance` = "No attendance recorded yet. Teachers mark daily attendance; the School Coordinator
  marks activity attendance." (still starts with "No ", as `enh-013-student-360.spec.ts:116` requires).

## 7. Acceptance criteria

| AC | Criterion |
|---|---|
| AC01 | A teacher opens Attendance, sees exactly their assigned students for the chosen day, and saves the whole class with one Save; `PUT` writes one row per listed student. |
| AC02 | Re-marking the same student and day updates the row (status, marked_by, updated_at); never a second row. |
| AC03 | A `PUT` listing any student not assigned to the teacher (unassigned, other teacher's, other school's, unknown id) returns 403 and writes nothing (no record, no mark audit row). |
| AC04 | Non-teacher roles (coordinator, principal, parent, service roles, IT roles) get 403 on `GET` and `PUT`. |
| AC05 | A future `session_date` → 422; an invalid status, duplicate `student_id`, empty or >500 records, an extra field, or a non-JSON body → 422. |
| AC06 | An expired or missing tier → the existing tier 403 and `school.tier_access_denied` audit row; no record written. |
| AC07 | Each successful `PUT` writes one `school.daily_attendance_mark` audit row with date, count and status tally. |
| AC08 | The linked parent's dashboard card and child overview show the student's daily attendance counts; the overview `daily_attendance` key is present for all current readers. |
| AC09 | The Student 360° Attendance tab shows daily records to School roles; the ENH-030 "not tracked yet" note is gone; a brand-new student's tab is still `empty`; service roles still `restricted`. |
| AC10 | After a transfer, the new school's readers do not see records marked at the old school; the old rows still exist. |
| AC11 | `/school/dashboard`, `/school/reports`, ENH-016 analytics and the parent nav are unchanged. |
| AC12 | The teacher page has loading, empty, error, busy, success and failure states; works at 320 px without horizontal scroll; radios are labelled and keyboard-operable; unsaved marks are guarded. |
| AC13 | Migration `0046` is the single head, creates only the new table, and round-trips downgrade/upgrade; model and migration match. |

## 8. Regression risks and guards

| Risk | Guard |
|---|---|
| `/school/reports` `attendance == {"present":2,"total":3}` (`test_sch_reports.py:139`), dashboard key contract (`test_enh_016_contracts.py:119`) | Daily attendance never touches that key; both tests run unchanged. |
| ENH-013 AC-01/AC-04: fresh student tabs `empty`; service roles `restricted` with `not_tracked: []` | Count adds `len(recent)` only (0 for a fresh student); existing tests run unchanged; new test for the note removal. |
| e2e `enh-013-student-360.spec.ts:109-116` (16 tabs, empty text `^(No |Not enrolled)`) | New empty text starts with "No "; no tab added. |
| Migration head test `test_enh_027_migration.py:31` pins 0045 | Relax like `test_enh_025_migration.py` (one head; 0045 in the parents). |
| Tier-count tests (`test_enh_016_cross_school.py:16-19`) | No `TIER_SERVICES` key added (D6). |
| Parent nav snapshot (`Enh015ReportPlacement.test.tsx:127`) | Only `SCHOOL_NAV.teacher` changes. |
| `sendJson` callers | Type widening only; runtime unchanged. |
| Circular import `schools` ↔ `school_attendance` | `school_attendance` imports from `schools`; `schools._overview_payload` uses a function-level import (the `_skills()` precedent). |
| Transfer / reassignment race | `FOR SHARE` on the listed student rows + scope re-check under the lock (§5.2 step 3); test with a pre-moved student. |
| Hot shared files (`schools.py`, `models.py`) | `schools.py` gets a 2-line additive change; new code in its own router. |

## 9. Test plan (written before code)

- **Backend (pytest, real Postgres via `conftest.py`), new files:** `test_enh_030_model.py` (table, constraints, CHECK),
  `test_enh_030_migration.py` (0046 single head, create-only), `test_enh_030_mark.py` (AC01–AC07, AC05 validation matrix, idempotent retry,
  partial roster), `test_enh_030_reads.py` (AC08–AC10: overview key per reader, 360 tab, transfer rule, fresh student empty).
  Builders: `enh005_helpers.mk_school/mk_student/mk_user/login`, `move_student_directly`.
- **Existing suites that must stay green unchanged:** `test_enh_013_*`, `test_sch_007_parent_portal.py`, `test_sch_reports.py`,
  `test_enh_016_*`, `test_enh_022_*`, `test_enh_023_*`, `test_sch_001_*`, `test_enh_005_*`. One edit: `test_enh_027_migration.py` head relax.
- **Vitest, new:** `SchoolDailyAttendance.test.tsx` (prefill, no default, mark-all-present fills unselected only, PUT body, success/failure
  messages, busy state, unsaved guard, empty roster, date max). Updated: `Student360Panels.test.tsx` (note fixture removed; daily table;
  new empty text), `SchoolChildOverview.*` (metric shown / "Not marked yet" / absent key renders as before), a nav test for teacher.
- **Playwright, new:** `enh-030-daily-attendance.spec.ts` — throwaway school via API (the `enh-013` setup), teacher marks the class in the
  UI, parent dashboard shows the counts, 360 tab shows the row, teacher at 320 px has no horizontal overflow.
- **Gates:** `ruff`, `pytest`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, targeted Playwright against the rebuilt stack.

## 10. Out of scope (v1)

Coordinator marking; period-level attendance; correction/appeal workflow; timeline events; dashboard/report/analytics KPIs (ENH-016
follow-up); parent absence notifications; seed data; a school calendar/holiday model.

## 11. Engineering review (2026-09-30): api-and-interface-design, frontend-ui-engineering, security-and-hardening

Applied to this design before any code. Each finding either changed the design (**changed**) or is recorded as deliberately kept.

### 11.1 API and interface

| ID | Finding | Resolution |
|---|---|---|
| A1 | Both routes returned untyped dicts; the skill wants typed output schemas | **changed**: `SchoolAttendanceRosterOut` / `SchoolAttendanceRosterStudent` as `response_model` on both routes (the OpenAPI contract; `status` typed as the four-value literal or null) |
| A2 | A 200-record cap is lower than a class the roster can return (the roster is every assigned student, unpaginated) | **changed**: cap 500, the existing IT `AttendanceBulkIn` limit; the roster stays unpaginated on purpose (a teacher's own class, the same as `/school/students` for a teacher) |
| A3 | Two saves of overlapping students (two tabs) insert in payload order and could deadlock on the attendance rows | **changed**: records sorted by `student_id` before the lock and the insert |
| A4 | Three single-column indexes had no query that needs them | **changed**: dropped; the unique index covers every query here. ENH-016 KPIs add their own index when they exist |
| A5 | The audit row said how many, not which | **changed**: `changes` list (see S5) |
| A6 | HTTP semantics | kept: `GET` is safe (no DB write, ENH-013 D12); `PUT` is an idempotent upsert of the listed marks, the ENH-011 `PUT …/attendance` precedent. The date stays in the body/query (not the path) so `GET` can default to the school's today |
| A7 | Error shape | kept: the codebase's `{"detail": str}` (and FastAPI's list for schema errors), which `detailMessage` already renders. snake_case fields, as every School endpoint |
| A8 | Backward compatibility | kept: only additive keys (`daily_attendance`, `data.daily`); the 360 envelope (`Student360Out`) and the 16 tab keys are unchanged; the frontend treats both new keys as optional |
| A9 | Enumeration | kept: unknown, unassigned, other-school and moved-away ids all get the same 403 text, so the call cannot probe which student ids exist |

### 11.2 Frontend

| ID | Finding | Resolution |
|---|---|---|
| F1 | Changing the date is a server round trip with no feedback, and a second change can race the first | **changed**: `router.push` inside `useTransition`; while pending the form is disabled, `aria-busy`, and shows "Loading <date>…" |
| F2 | On a 40-student list the teacher cannot see progress | **changed**: a tally line under the date — "12 of 40 marked" — from the current selections |
| F3 | "Mark all present" sat beside Save at the bottom of a long list | **changed**: "Mark all present" above the list (the first thing a teacher does); Save and the unsaved flag below it |
| F4 | Sticky save bar | not added: not in the design system; the unsaved-changes guard covers leaving the page |
| F5 | Reuse | kept: `FormMessage`, `sendJson`, `PortalShell`, `accessUnavailable`, the `SchoolSkillAttendance` guard pattern, `.card/.form/.field/.badge/.btn`, `formatCalendarDate`; one new component, one new plain module (`lib/attendance.ts`) |
| F6 | Keyboard and screen readers | kept: native radio groups (Tab between students, arrow keys within one), each `fieldset` named by its `legend`; status is text, never colour alone; results announced through `FormMessage` (`status`/`alert`) |

### 11.3 Security (threat model: trust boundary = the two new routes' query/body; assets = a minor's attendance record and its integrity)

| ID | Check | Result |
|---|---|---|
| S1 | Authentication | Existing `get_current_user` (httpOnly `edusphere_access` cookie, inactive users → 401) on both routes. No change to auth |
| S2 | Authorization / IDOR / role escalation | Teacher-only dependency; school from the session profile, never input; every listed id re-checked under a row lock against own school + `assigned_teacher_user_id`; `extra="forbid"` rejects smuggled `school_id`/`marked_by`; `marked_by_user_id` comes from the session. Reads reuse the existing loaders unchanged. Tests: AC03 (four outsider kinds), AC04 (three other roles), smuggled field |
| S3 | Input validation / SQL injection | Pydantic at the boundary (date, UUIDs, four-value literal, 1–500, unique ids); SQLAlchemy parameters only; ordering by fixed columns. The page passes `?date` on only when it matches `^\d{4}-\d{2}-\d{2}$` |
| S4 | CSRF | Session cookies are `SameSite=Lax` (`auth.py:88`); the write is a `PUT` with a JSON body, which a cross-site page cannot send without a CORS preflight, and CORS allows only `settings.frontend_url`; FastAPI ≥0.115 refuses a non-JSON body. **Pinned by a test** (a `text/plain` body → 422, nothing written). `GET` writes nothing |
| S5 | Audit / repudiation | One audit row per save with the changed students (`from`→`to`), actor from the session, school id; a tier denial keeps its own `school.tier_access_denied` row |
| S6 | Sensitive logs | Log lines carry ids, date and counts only — no names, no per-student statuses. Audit metadata carries student ids, never names |
| S7 | XSS | All values rendered through React escaping; no `dangerouslySetInnerHTML`; no URL built from stored data |
| S8 | Rate limiting | Not added: the codebase has no general limiter (only a DB-counted limit on transfers), the routes need an authenticated teacher, and a save is capped at 500 rows. Adding a limiter is an "ask first" change outside ENH-030 |
| S9 | Secrets / tokens / session | None introduced; no new cookie, header, or config |
| S10 | Data minimisation | The roster returns name, grade/class and status only, for the teacher's own students; the overview adds dates and statuses only |

**Still `NEEDS_CONFIRMATION` (defaults shown, not blocking):** a lower bound on how far back a teacher may mark (default: none; every write is audited); whether attendance history from a previous school should be visible to parents (default: hidden, C1).
