# ENH-004 — Student Promotion to Next Academic Year / Grade — Design

**Status:** Design approved by the user in-session, 2026-09-19 (six decisions in §3, each taken with the
recommended option; design sections 1–7 approved with "yes"). API review revisions (§5.4: Pydantic
typed boundary, unknown and foreign IDs both `403`, role gate as a dependency, bounded lock wait,
renamed reason code) accepted in-session the same day. Implementation not started.

**Traceability:** `EVID` user instruction ("promoted to upper grade in next year if required", recorded
in `docs/delivery/ENHANCEMENT_BACKLOG.md` ENH-004, `DERIVED_BACKLOG`) → `DEC-SCOPE-020` (proposed by this
spec, to be registered — see §12) → ENH-004 → this spec → plan (`docs/superpowers/plans/`) → tests → code.
Hard dependency `ENH-001` (`AcademicYear`, `SchoolStudent.academic_year_id`/`grade_level`) is already built.

**Acceptance-criteria numbering:** `AC-nn` below is local to this spec. Do not cite it from
`API_CONTRACT.md`/`RTM.md` as a source-document ID; cite `DEC-SCOPE-020` and `ENH-004`.

## 1. Problem (audit result, gap confirmed)

Nothing in the codebase advances a student. `SchoolStudent.grade_or_class` (free text) and
`grade_level` (int 1–12) are set at creation and edited one student at a time through
`PATCH /school/students/{id}` (`schools.py:1028`), which overwrites both in place. There is no
promotion action, no bulk action, and no record of a student's prior grade or year. The parent
dashboard (`parent/dashboard/page.tsx:54`), the parent child page, the principal and teacher pages and
the coordinator pages all render `grade_or_class`; only the dashboard KPI counts read `grade_level`
(`schools.py:303-410`). `SchoolStudent` has no section field: "section" exists only as free text inside
`grade_or_class`, for example "Grade 10-A".

## 2. Goals and non-goals

**Goals.** A School Coordinator can promote or hold back one student or many in a single request,
scoped to their own school. Every transition is preserved in retrievable history. Parent views show the
new grade immediately. A coordinator can never affect another school's students.

**Non-goals (do not do here).**
- A real `section` field, or any change to `grade_or_class`'s free-text nature.
- A graduated/alumni status, or any change to what happens after Grade 12 (`422` row error only).
- Promotion by `overseas_admin`/`super_admin`, or any client-supplied school identifier.
- A student-facing view. `DEC-ROLE-004`: school-affiliated students never log in, so "student
  dashboard" in the backlog's third acceptance criterion maps to the **parent view only**.
- Parent notifications on promotion, and promotion events in the SCH-008 timeline (both are possible
  follow-ups; the timeline change in §8 is limited to the one correctness fix it forces).
- Any change to `create_student`, `update_student`, `bulk_upload_students`, `seed.py`, the dashboard
  KPI logic, the `AcademicYear` endpoints or `get_current_user`/RBAC helpers.
- Fixing pre-existing issues noticed during the audit: `school_reports` (`schools.py:610` onward)
  contains dead code after its `return`; `DEC-DATA-004`, cited in `models.py`, is not in the decision
  register; the ENH-001 spec cited in `models.py` is absent from this branch.
- An `Idempotency-Key` header. Safe retry comes from the skip rule in §5, so no batch table is needed.

## 3. Decisions confirmed in-session (2026-09-19)

| # | Question | Decision |
|---|---|---|
| D1 | How does bulk pick students, with no section field? | **Explicit student IDs.** The API takes a list; the UI filters and ticks. No selector logic on the server. |
| D2 | How is `grade_or_class` updated? | **Auto-swap the number, allow per-item override.** A row that cannot be swapped fails with a clear reason unless an override is supplied. |
| D3 | Grade 12? | **Reject that row.** Graduation is out of scope. |
| D4 | Who promotes? | **`school_coordinator` only.** The school comes from the caller's own profile. |
| D5 | Target year, and held-back students? | **The active academic year, server-resolved; hold-back is a recorded action** (same grade, moved into the new year, history row written). |
| D6 | Some rows fail a business rule? | **Commit the valid rows and report the rest** (SCH-002-AC04 discipline). A foreign-school student aborts the whole request with `403`. |

## 4. Approach

**Data model.** An append-only **transition ledger** in a new table; `school_students` remains the
source of *current* grade/year, so every existing reader keeps working. Rejected: deriving current
state from history (rewrites every reader, risks data), and overwrite-plus-`AuditLog` (a log is not a
retrievable read model).

**API.** One endpoint taking a list of items; a single-student promotion is a list of one. Rejected:
separate single and bulk endpoints (duplicated authorization, locking and rules).

## 5. Data model and behavior

### 5.1 New table `school_student_grade_history` (migration `0033`)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `school_student_id` | UUID FK `school_students.id`, indexed, not null | |
| `action` | String(20), not null | `promoted` or `held_back` |
| `from_academic_year_id` | UUID FK `academic_years.id`, nullable | |
| `from_grade_level` | Integer, nullable | |
| `from_grade_or_class` | String(60), nullable | |
| `to_academic_year_id` | UUID FK `academic_years.id`, not null | |
| `to_grade_level` | Integer, nullable | |
| `to_grade_or_class` | String(60), nullable | |
| `performed_by_user_id` | UUID FK `users.id`, not null | |
| `created_at`, `updated_at` | via `TimestampMixin` | |

`UNIQUE (school_student_id, to_academic_year_id)` (`uq_school_student_grade_history_year`) is the
database backstop against double promotion.

Each row records its own "from" state, so **no backfill is needed** and no existing row is read or
written by the migration. The migration is create-table only, guarded with the inspector as `0030`
is, and its `downgrade()` drops only this table. Revision `0033_student_grade_history`, revises
`0032_welcome_token_purpose`.

### 5.2 `POST /school/students/promotions`

Request: `{"items": [{"student_id": "<uuid>", "action": "promote" | "hold_back", "grade_or_class": "<optional>"}]}`.

**Typed boundary.** Request and response are Pydantic models in `apps/api/app/schemas.py` (the module
`auth`, `workflows` and `admin` already use), not `payload: dict`: `PromotionItem` (`student_id: UUID`,
`action: Literal["promote", "hold_back"]`, `grade_or_class: str | None`, stripped, non-empty, at most
60 characters) and `StudentPromotionRequest` (`items: list[PromotionItem]`, 1–500 entries). A model
validator rejects a duplicated `student_id` and a `grade_or_class` combined with `hold_back`. Any
violation is a `422` in FastAPI's standard list-shaped `detail`, with nothing written; a malformed UUID
is therefore a `422`, never an uncaught `ValueError`/`500`. The response is typed by
`StudentPromotionResponse`.

Check order (authorization before validation before state): no session `401` → caller is not a
`school_coordinator` `403` (a `Depends(...)` gate wrapping the existing `_require_coordinator`, so it
runs **before** body validation: a non-coordinator with a malformed body gets `403`, not `422`) →
payload `422` → lock and load students → **any ID that is unknown or belongs to another school `403`
with one generic message** (unknown and foreign are deliberately indistinguishable, so a coordinator
cannot probe which student IDs exist at other schools) → no active academic year `409` → per-item
rules.

**Locking.** After payload validation the endpoint runs `SET LOCAL lock_timeout = '5s'` and then
`SELECT … FROM school_students WHERE id IN (…) ORDER BY id FOR UPDATE`, the row-lock style already used
by `update_academic_year_status` (`admin.py:1149`), always in `id` order so two requests cannot
deadlock. A concurrent duplicate request waits for the first to commit, then sees the students as
already in the active year; if the wait exceeds the timeout the lock error maps to `409`
("Another promotion is in progress; retry"). It then compares row count and `school_id` to the
caller's own school.

**Per-item rules** (`active` = `_current_academic_year_id`, reused unchanged):

| Condition | Result |
|---|---|
| `student.academic_year_id == active` | `skipped`, reason `already_in_active_year` (covers retries, concurrent duplicates, and students created this year) |
| `hold_back` | `held_back`: `academic_year_id = active`; grade and label untouched (permitted even when `grade_level` is NULL or 12) |
| `promote`, `grade_level is None` | `failed`, reason `grade_level_not_set` |
| `promote`, `grade_level >= 12` | `failed`, reason `terminal_grade` |
| `promote`, label swap impossible and no override | `failed`, reason `label_unparseable` |
| `promote`, otherwise | `promoted`: `grade_level += 1`, `grade_or_class` = override or swapped label, `academic_year_id = active` |

**Label swap.** Find the first match of `\b(?:grade|class)\s*(\d{1,2})\b|\b(\d{1,2})\b` in
`grade_or_class` (the same pattern family as migration `0030` and `_grade_level_from_label`). Swap only
if the matched number equals the student's current `grade_level`; replace exactly the matched digits
with the new level. "Grade 8-A" → "Grade 9-A"; "Class 10" → "Class 11". If the label is `None`, the new
label stays `None` (not a failure). A label with no match, or whose number disagrees with
`grade_level` (including "8A", which has no word boundary), is `label_unparseable` and needs an
override. A swapped label that would exceed 60 characters (the column width; "Grade 9" becoming
"Grade 10" adds a character) also fails that row as `label_unparseable`, with a message saying the
label is too long, rather than reaching the database and returning `500`. An override always wins over
the swap.

**Writes and transaction.** One request, one transaction. For each `promoted`/`held_back` item the
endpoint updates the `SchoolStudent` and adds one history row. Rows that are `failed` or `skipped`
write nothing, so no savepoints are needed. If at least one row was written it adds one `AuditLog`
(`school.student_promotion`, `entity_type="academic_year"`, `entity_id=<active year id>`,
`metadata_json={academic_year_id, promoted, held_back, failed, skipped}`) and commits once; if none was
written, nothing is added and nothing is committed. An `IntegrityError` on the unique backstop rolls
back and returns `409` ("A concurrent promotion was detected; reload and retry").

**Response** (`200`, including when every row failed):

```json
{
  "academic_year": {"id": "…", "label": "2026-27"},
  "counts": {"promoted": 0, "held_back": 0, "failed": 0, "skipped": 0},
  "results": [
    {"student_id": "…", "status": "promoted|held_back|failed|skipped", "reason": null, "message": null,
     "grade_level": 9, "grade_or_class": "Grade 9-A"}
  ]
}
```

`grade_level`/`grade_or_class` report the student's state after the request (unchanged for
`failed`/`skipped`). `reason` is a machine-readable code and `message` its human text; both are `null`
for `promoted`/`held_back`. The reason codes are a stable contract (clients may branch on them):
`already_in_active_year`, `grade_level_not_set`, `terminal_grade`, `label_unparseable`. New codes may
be added later; existing ones are never renamed or repurposed.

### 5.3 `GET /school/students/{student_id}/grade-history`

Uses `_load_readable_student`, so the scope is inherited unchanged: own school for every school role,
assigned students only for a teacher, own children only for a parent (`403` otherwise, `404` for an
unknown ID). Returns
`{"student": {"id", "full_name"}, "history": [{"id", "action", "from": {"academic_year_id",
"academic_year_label", "grade_level", "grade_or_class"}, "to": {…same…}, "created_at"}]}`, newest first
(`created_at DESC, id DESC`). A never-promoted student returns `"history": []`. The performer is stored
but deliberately not returned, so a parent never receives a staff user ID.

### 5.4 API design notes (result of the `api-and-interface-design` review, 2026-09-19)

- **Conventions follow the existing API, not generic style guides:** `snake_case` fields, lowercase
  enum values (`promoted`, `held_back`), plural-noun hyphenated paths (`/students/promotions`,
  `/students/{id}/grade-history`, like `bulk-upload`/`roster-template`), errors as FastAPI
  `{"detail": …}`. `POST /students/promotions` is registered beside the other student writes: the
  static-before-dynamic ordering comment at `schools.py:769` concerns two routes with the *same method*
  (`GET /students/roster-template` vs `GET /students/{student_id}`), and no `POST /students/{student_id}`
  route exists, so declaration order is immaterial here (Starlette skips method-mismatched matches).
- **Error shapes:** `401`/`403`/`404`/`409` use `{"detail": "<string>"}` as every other route does;
  request-validation `422` uses FastAPI's `{"detail": [{loc, msg, type}]}`. The web client's
  `detailMessage()` already renders both. Per-row failures are not HTTP errors: they are `200`
  results with `reason`/`message`.
- **Why `200`, not `201`:** `bulk-upload` returns `201` because it always creates a batch record. A
  promotion request may create nothing (every row failed or was skipped), so `201` would misreport it.
  `200` with `counts` is used consistently, including when nothing changed.
- **Retry safety without an `Idempotency-Key`.** The natural key is (student, target year): the row
  lock plus `UNIQUE (school_student_id, to_academic_year_id)` is an atomic claim, the constraint picks
  the winner, and there is no check-then-act race. A duplicate in flight waits (bounded by
  `lock_timeout`) and then reports `skipped`. Consequence, documented in `API_CONTRACT.md`: a retry
  after a lost response reports `skipped: already_in_active_year`, not a replay of `promoted`, so a
  client should read `results[].grade_level`/`grade_or_class` or `GET …/grade-history` to confirm.
  A key/replay store (as `bulk-upload` needs, having no natural key) would add a table for no gain here.
- **No pagination:** the request is capped at 500 items (`422` above that); `grade-history` is bounded
  by one row per academic year per student, and `list_students` is unpaginated too.
- **Database use:** one locked `SELECT` (≤500 rows), one active-year lookup, `add_all` for history
  rows, no per-row queries; `grade-history` is one query joining `academic_years` twice via aliases.
  `get_db` has no explicit rollback: closing the session rolls back uncommitted work and releases
  locks, so any `HTTPException` after the lock is safe; the `IntegrityError` path still calls
  `db.rollback()` explicitly, as `create_academic_year` does. `expire_on_commit=False`, so the response
  is built after commit without re-reading.
- **Placement:** models and helpers live in `models.py`, `schemas.py` and `schools.py`, where the
  neighbouring code lives. The label swap and the per-item rule decision are pure module-level
  functions (no database), so they are unit-tested without a session. No service layer is added.

## 6. Authorization summary

| Caller | `POST …/promotions` | `GET …/grade-history` |
|---|---|---|
| No session | 401 | 401 |
| `school_coordinator`, own school | allowed | allowed |
| `school_coordinator`, any listed student unknown or at another school | 403 (one generic message), nothing written | 403 (unknown ID: `404`, the existing `_load_readable_student` behavior) |
| `school_principal` / `school_teacher` / `school_parent` | 403 | own scope only (principal: own school; teacher: assigned; parent: own child) |
| `overseas_admin` / `super_admin` / service-delivery roles | 403 | 403 (`_own_school_id` requires a school role, as for every other student read) |

The school identifier is never read from the request.

## 7. Frontend

- **Route** `/school/coordinator/promotion`: a server page that loads `/api/v1/auth/me`,
  `/api/v1/school/students` and `/api/v1/school/academic-years/active` (all existing), following the
  neighbouring `coordinator/students/page.tsx`, plus a `SCHOOL_NAV` entry for the coordinator.
- **`SchoolPromotionPanel`** (new client component, not a growth of `SchoolStudentsPanel.tsx`): active
  year banner; grade-level filter; select-all-in-view; per-row checkbox, a Promote/Hold back toggle and
  an optional "override label" input; a submit button.
- **States.** Loading: the button is disabled and reads "Promoting…". Empty: "No students match this
  filter", and "No active academic year. Ask an Overseas Admin to activate one" with submit disabled.
  Error: `403`, `404`, `409`, `422` and network failures each render a message (the
  `detailMessage()` pattern in `SchoolStudentsPanel`). Success: counts plus a per-row results table
  in an `aria-live` region; failed rows keep their reason so the coordinator can correct and resubmit.
  The list refreshes with `router.refresh()`.
- **`SchoolGradeHistory`** (new, read-only): shown on the parent child page next to the existing
  timeline, and on the coordinator student detail page. It follows `SchoolStudentTimeline`'s
  server-fetch pattern and shows a "No promotions recorded yet" empty state and an "unavailable" error
  state.
- **Parent dashboard: no code change.** `serverApi` uses `cache: "no-store"` (`api.ts:11`), so the
  next render after a promotion reads the new grade. A Playwright test proves it.
- Accessibility and layout reuse the existing table, form and button classes and `scope="col"`
  headers. Exact class names and the `SCHOOL_NAV` shape are read at plan time.

### 7.1 Frontend revisions (result of the `frontend-ui-engineering` review, 2026-09-19)

Where this section differs from the bullets above, **this section wins**. It applies the confirmed
`NFR-RESP-001` (`docs/ux/RESPONSIVE_RULES.md`) and the baseline in `docs/ux/ACCESSIBILITY_RULES.md`,
and reuses the existing design language instead of introducing a new one.

- **No horizontally scrolling table.** Every existing table is `min-width: 650px` inside `overflow: auto`,
  which `RESPONSIVE_RULES.md` forbids as the only mobile option. The promotion list is one `<ul>` of
  student rows: stacked cards below 768px (labels visible), a columned row with a header above it from
  768px. The only new CSS is `SchoolPromotionPanel.module.css` (precedent: `ProgramCatalogue.module.css`).
  `DataTable` is not reusable here (it renders plain values only), but its `table-controls`/`select`/`empty`
  classes and its "Showing X of Y" live-region pattern are reused.
- **Explicit confirmation.** A bulk change to many students' current grade is high-consequence
  (`ACCESSIBILITY_RULES.md`). "Review changes (N)" opens an inline confirm step ("Promote A and hold back
  B into <year>?") with Confirm and Cancel, following the two-step pattern already used in
  `AdminUserManagementPanel`/`AdminProgramManagementPanel`; focus moves to Confirm, Escape or Cancel returns
  it to Review, and after the result it moves to the summary. No `window.confirm`.
- **Errors tied to the field.** A failed or skipped row shows "Not changed"/"Skipped" and its reason beside
  that row's own controls (`aria-describedby`), not in a separate table. Rows known to fail (Grade 12, no
  grade level) carry an advisory hint before submit; the server stays authoritative. Request-level errors use
  `role="alert"`, results `role="status"`.
- **Client-side cap.** More than 500 selected disables "Review changes" with an explanation, so the API's
  `422` is never the first the coordinator hears of it.
- **Perceived performance.** No optimistic update (the server decides and rows can fail); instead the
  per-row outcome the server returns is shown immediately and `router.refresh()` runs in a transition. Rows are
  memoised with primitive props and stable callbacks, so ticking a box does not re-render the roster. The
  grade-history read starts in parallel with the timeline read. No `loading.tsx`: no route has one and there is
  no shared `school/layout.tsx`, so it would render without the portal shell.
- **Empty states are actionable:** no roster (link to the roster), no filter match ("Show all grades"), no
  active year (nothing to act on until an Overseas Admin activates one).
- **Grade history reuses the Journey Timeline rail** (`.jtl-*`): a short dated list that stacks on mobile
  with no new CSS; the outcome is a text badge plus a sentence ("Moved from X to Y" / "Kept in X"), never
  colour alone. `SchoolStudentTimeline` is not modified.
- **Verification** adds keyboard steps (Space, Enter, Escape, focus placement) and a no-horizontal-overflow
  check at 320/768/1024/1440px to the Playwright spec, plus a manual screen-reader/reduced-motion pass. No
  new dependency (axe-core is not added).

## 8. One forced change to existing behavior

`student_timeline` (`schools.py:923`) writes `Added to {student.grade_or_class}` from the *current*
label. After a promotion that would misreport where the student was added. Change: if the student has
any history rows, use the **earliest** row's `from_grade_or_class` for that one event's `detail`;
otherwise keep today's behavior exactly. No other timeline event, no response shape, and no other route
changes.

## 9. Error states and edge cases

- No active year: `409` (after authorization). `_current_academic_year_id` picks the latest
  `start_date` among active years, so overlapping active years are tolerated as they are today.
- A student with `academic_year_id = NULL` is processable. A student already in the active year is
  `skipped`.
- Unknown, foreign or duplicated IDs never produce a partial write: they fail before any student row
  changes (unknown and foreign both `403`, duplicates `422`).
- 500-item cap keeps lock time bounded; larger sections are submitted in several requests, each safe to
  retry.
- Parent/child scope across schools (a saved user requirement that guardian links must not be assumed
  single-school) is unaffected: promotion never changes `school_id`.

## 10. Acceptance criteria (local IDs)

- **AC-01** A coordinator promotes one student or many in one request; each result reports the new
  `grade_level` and `grade_or_class`, and `school_students` holds them.
- **AC-02** Every promoted or held-back student gets a history row holding both the prior and new
  year/grade/label; a second promotion adds a second row and rewrites nothing. `GET …/grade-history`
  returns them newest first.
- **AC-03** `GET /school/students` (the parent dashboard's source) returns the new grade immediately
  after the promotion request returns.
- **AC-04** A request naming any student at another school, or any unknown student ID, returns `403`
  with the same message for both, and changes no student and no history row, including when the list
  mixes own and foreign students.
- **AC-05** Principal, teacher and parent get `403`; no session gets `401`; admin roles get `403`. The
  role check precedes body validation: a non-coordinator sending a malformed body gets `403`, not `422`.
- **AC-06** A Grade 12 student, a student with NULL `grade_level`, and a student with an
  unswappable label each fail only their own row with the documented reason; all other rows commit; an
  override resolves `label_unparseable`.
- **AC-07** Submitting the same request twice, or two concurrent identical requests, promotes each
  student exactly once (second attempt is `skipped: already_in_active_year`); the database never
  contains two rows for the same student and target year. A request that cannot obtain the row locks
  within the lock timeout returns `409`.
- **AC-08** With no active year the endpoint returns `409`; empty, oversized (>500), duplicated,
  malformed (including a non-UUID `student_id`) or wrong-action payloads return `422`, never `500`.
  A swapped label longer than 60 characters fails only its own row.
- **AC-09** Hold-back leaves grade and label unchanged, moves the student into the active year and
  writes a `held_back` history row.
- **AC-10** Existing endpoint shapes are unchanged; the SCH-008 timeline "profile created" detail
  shows the pre-promotion label once history exists and is unchanged otherwise; the dashboard KPI
  counts follow `grade_level` after a promotion (expected, asserted).
- **AC-11** Grade history is readable only within the caller's existing scope (foreign school, an
  unassigned student for a teacher, and an unlinked child for a parent are all `403`).

## 11. Regression risks and test plan (written before code)

**Risks.** Dashboard KPIs shift after promotion (expected; asserted). The `sch_008` timeline test,
given §8. The `enh_001` column-shape and migration tests must stay green. Parent own-child scope
(`sch_007`). Roster, bulk upload and PATCH tests must be untouched. Lock ordering and deadlock. The
`update_student` PATCH can still overwrite grade fields directly; that is unchanged existing behavior,
noted here so it is not mistaken for a hole in the history.

**Backend, `apps/api/tests/test_enh_004_student_promotion.py`** (pattern: `test_enh_001_academic_year.py`):
model and unique constraint; migration `0033` upgrade/downgrade cycle preserving existing rows; single
promote with label swap; bulk promote; hold-back; label swap unit cases (`Grade 8-A`, `Class 10`, `8A`,
mismatch, `None`); override; terminal, NULL and unswappable rows with other rows committing; `403`
cross-school with nothing written, including a mixed list; role matrix and `401`; repeat submit;
two concurrent requests via `asyncio.gather` (feasibility against the real Postgres test database is
confirmed at plan time); lock-timeout `409`; `409` no active year; `422` cases (including a non-UUID
ID, a duplicate ID, `hold_back` with a label, 501 items); `403` for an unknown ID with the same body as
a foreign ID; a non-coordinator with a malformed body gets `403`; label-too-long row; pure-function
unit tests for the label swap and the per-item rule; history scoping for coordinator,
teacher, parent and a foreign school; timeline detail after promotion; audit row written only when
something changed; dashboard KPI shift.

**Playwright, `apps/web/tests/e2e/enh-004-student-promotion.spec.ts`**: promote one and promote bulk
through the UI; parent dashboard shows the new grade; history visible on the parent child page and the
coordinator detail page; API `403` cross-school; failed-row display and retry with an override; the
no-active-year state.

**Gates before "complete":** targeted suites plus the directly affected ones (`enh_001`, `sch_007`,
`sch_008`, `sch_reports`, `sch_002` and their e2e specs), API lint/type checks, web type-check/lint/
build. The full regression suite is not run for this feature alone (the user's cadence is every 3–4
features). Tests are executed with real scripts; the user starts and stops the docker stack, and the
e2e run waits for their say-so.

## 12. Documentation deliverables

- Register `DEC-SCOPE-020` in `docs/decisions/PRODUCT_DECISION_REGISTER.md` recording D1–D6 as
  `EXPLICIT_APPROVAL` (in-session, 2026-09-19).
- `docs/architecture/API_CONTRACT.md`: the two new endpoints, including both `422` shapes, the reason
  code table, the `200`-always rule, and the retry semantics from §5.4.
- Add the new route to the screen catalogue and the new table to the data-model doc, and add the RBAC
  rows if `RBAC_MATRIX.md` lists per-endpoint school grants. Confirm each file's structure at plan
  time.
- `docs/delivery/ENHANCEMENT_BACKLOG.md` ENH-004: mark status and correct its stale line references
  (`models.py:992` is `985`, `schools.py:1145` is `1193`).

## 13. Open items (`NEEDS_CONFIRMATION`, not decided here)

- Graduate/alumni handling after Grade 12.
- A real section field.
- Whether admin roles should ever promote, and the school-selection design that would require.
- Parent notification on promotion and promotion events in the SCH-008 timeline.
- Whether `grade-history` should also appear on the principal and teacher detail pages (this spec
  places it on the parent child page and the coordinator detail page only).
- Security follow-ups outside ENH-004 (see §14.3): `profile.university_id` mass-assignment (UNI-001);
  a school-student erasure path; an app-wide rate limiter and CSRF token.

## 14. Security review (2026-09-19)

Method: a threat model of ENH-004's trust boundaries (the request body, the session cookie, `profile.school_id`
(the value every school authorization check rests on), the free-text `grade_or_class`, the database), a STRIDE
pass, and a check of each item against the code rather than against the design. Only items that concern
ENH-004 are changed; everything else is reported. **Where this section differs from §5.2, this section wins.**

### 14.1 Findings

| ID | Severity | Finding | Decision |
|---|---|---|---|
| **S1** | **Critical, pre-existing** | `PATCH /auth/me` (`auth.py:143`) merges a client-supplied, unrestricted `profile` dict into `user.profile`. Every school scope check reads `profile["school_id"]` (`_own_school_id`, `_require_coordinator`, ~16 sites in `schools.py`). Any logged-in user can set their own `school_id` to another school's and then read, edit and **promote** that school's students. AC-04 ("a coordinator cannot promote at another school, 403") is false while this holds, whatever the promotion endpoint does. | Fix in plan Task 3b: `profile.school_id` is read-only through `PATCH /auth/me` (an unchanged echo is still accepted, because the web form sends the whole profile); a refused change is 403 and audited (`profile.update_denied`); nothing else in that request is applied. **Changes authentication/profile logic, so it needed the user's approval: given and implemented 2026-09-20 (commit "fix(auth): make profile.school_id read-only via PATCH /auth/me").** The same class exists for `profile.university_id` (UNI-001: `workflows.py:158,1824`, `inbound.py:138`, `portal.py:929`); that is **not** changed here and is reported separately. |
| **H1** | Medium (ENH-004's own design) | §5.2 locked every listed student row *before* checking ownership, so a coordinator naming another school's IDs made the request wait on, and briefly hold, that school's rows (lock griefing, and an existence-timing signal). | The school filter is part of the locking query itself (`WHERE id IN (...) AND school_id = :own FOR UPDATE`). Another school's rows are never locked or read; an unknown ID and another school's ID are the same absence, so the generic 403 stays indistinguishable. `school_id` never changes after creation (`DATA_MODEL.md` §6.11), so there is no check/use gap. |
| **H2** | Low | `SET LOCAL lock_timeout = '{constant}'` builds SQL from an f-string. Safe today (a module constant) but the pattern is a scanner and future-edit hazard. | `SELECT set_config('lock_timeout', :timeout, true)` with a bound parameter (identical semantics to `SET LOCAL`). |
| **H3** | Low | Pydantic ignores unknown fields by default, so a client-supplied `school_id`/`academic_year_id` would be silently dropped. | `extra="forbid"` on the request models: it is refused with 422, consistent with ENH-001's rule that these are never read from a client payload. |
| **H4** | Low | A NUL byte in the override label passes Pydantic and cannot be stored in PostgreSQL text: a 500, and an unhandled SQLAlchemy error's text carries its parameters into the logs. Newlines and other control characters have no legitimate place in a grade label. | The override label rejects control characters (Unicode category `Cc`) with 422. |
| **H5** | Low | A refused cross-school attempt (probing, or a stale client) leaves no trace; today's audit trail records successes only. | The 403 is recorded as `school.student_promotion_denied` (`entity_type="school"`, `outcome="denied"`, metadata `{requested, not_in_school}`: counts only, no IDs or names) before it is raised. Nothing else has been written by then. |

### 14.2 Checked and unchanged

| Area | Result | Evidence |
|---|---|---|
| Authentication | No new flow; nothing to change. | `get_current_user` (`deps.py:14`) requires the `edusphere_access` cookie, `type == "access"`, and reloads the active user from the database on every request, so role and `profile` never come from the token and deactivation is immediate. |
| Token/session handling | No change. | Cookies are `httponly`, `secure` (config-driven), `samesite=lax` (`auth.py:61`); no token reaches JavaScript; the new UI only calls same-origin `/api/v1/...`. |
| Authorization | Sound, subject to S1 and H1. | The coordinator gate is a `Depends` that runs before body validation; the school comes from the caller's profile; the scoped query enforces it again. |
| IDOR | Promotion: closed (H1 and the generic 403). History read: reuses `_load_readable_student` (own institution; teacher assigned only; parent own child only). | The read route keeps that loader's existing 404-unknown/403-foreign behavior, documented in `API_CONTRACT.md`; changing it would alter existing contracts and is out of scope. |
| Role escalation | The endpoint takes no role, school or year input (H3). Tenant escalation is S1. | |
| Input validation | Typed at the boundary: UUIDs, `Literal` action, 1-500 items, no duplicates, label 1-60 chars stripped, no control characters (H4), unknown fields refused (H3). | |
| XSS | No new exposure. | Labels are stored raw and rendered only as React text nodes; the web app contains no `dangerouslySetInnerHTML`/`innerHTML`; nothing in ENH-004 builds HTML, email or CSV from a label; server messages are static strings that never echo input. |
| CSRF | No new exposure; no token added. | State change is POST only (the history GET is read-only). Cookies are `SameSite=Lax`, CORS allows one origin (`settings.frontend_url`), and the body is JSON, so a cross-site POST carries no session. Residual (unchanged, app-wide): a same-site sibling-subdomain attacker; a CSRF token would be an app-wide change. |
| SQL injection | None. | ORM-bound parameters throughout; IDs are typed UUIDs; the one raw statement is now parameterized (H2). |
| Secret exposure | None introduced. | No new secret, key or third-party call; tests and e2e reuse the existing seeded demo/test literals. |
| Sensitive logging | Clean. | The audit metadata is counts and a year ID; the denied row has no student IDs or names; the request middleware logs request IDs and exceptions, not bodies. |
| Rate limiting | **None exists app-wide** (only ENH-003's own resend throttle). A limiter is infrastructure and needs approval, so none is added. | ENH-004 bounds its own cost per request: coordinator only, at most 500 items, only own-school rows, a 5 s lock timeout, one transaction, at most 500 history rows plus one audit row. A valid coordinator can only load their own school. |
| Audit | Successes: one request-level row plus a per-student ledger row carrying the performer. Denied cross-school attempts: H5. Refused profile change: S1's `profile.update_denied`. | A role-denied 403 is not audited, matching every existing route. |
| Privacy | Grade/year history about minors, readable only within the existing student-read scope; the performer's user ID is stored but never returned; nothing is shared with a third party. | Retention is "kept with the student record" (append-only). |

### 14.3 Reported, not changed (outside ENH-004)

- `profile.university_id` has the same mass-assignment class as S1 (UNI-001). Recommend a separate fix.
- No school-student erasure path exists anywhere (data-subject handling covers users, `admin.py:887`). The new history table follows the codebase norm (a plain foreign key, no cascade), so it neither adds to nor closes that gap. `NEEDS_CONFIRMATION`.
- No app-wide rate limiter and no CSRF token; ENH-004 relies on `SameSite=Lax` and its own per-request bounds.
- `create_student`, `update_student` and bulk upload accept control characters in `grade_or_class` (a NUL there is a 500). Only the new promotion field is hardened.
- An unhandled SQLAlchemy error's text carries its SQL parameters into the server logs (a general logging setting).

### 14.4 Tests (all written before the code they cover)

`extra="forbid"` and control-character rejection (unit and endpoint); a rejected request never locks or waits on another school's rows (a foreign row is locked by another session and the request must return 403, not 409); a cross-school attempt writes exactly one `school.student_promotion_denied` row with counts only and changes nothing; `PATCH /auth/me` cannot change `school_id` (and the promotion boundary still holds afterwards), applies no partial change when refused, cannot give a schoolless user a school, and still accepts an unchanged echo.
