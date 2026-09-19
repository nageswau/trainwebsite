# ENH-004 — Student Promotion to Next Academic Year / Grade — Design

**Status:** Design approved by the user in-session, 2026-09-19 (six decisions in §3, each taken with the
recommended option; design sections 1–7 approved with "yes"). Implementation not started.

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

Request-level validation (`422`, nothing written): `items` present, 1–500 entries; each `student_id` a
valid UUID and unique within the request; `action` one of the two values; `grade_or_class`, when present,
a non-empty string of at most 60 characters after stripping, and only allowed with `promote`.

Check order (authorization before state): no session `401` → role is not `school_coordinator` `403`
→ payload `422` → lock and load students → unknown ID `404` → any student at another school `403`
→ no active academic year `409` → per-item rules.

**Locking.** After payload validation the endpoint runs
`SELECT … FROM school_students WHERE id IN (…) ORDER BY id FOR UPDATE`, the row-lock style already used
by `update_academic_year_status` (`admin.py:1149`), always in `id` order so two requests cannot
deadlock. It then compares row count and `school_id` to the caller's own school.

**Per-item rules** (`active` = `_current_academic_year_id`, reused unchanged):

| Condition | Result |
|---|---|
| `student.academic_year_id == active` | `skipped`, reason `already_processed` (covers retries, concurrent duplicates, and students created this year) |
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
override. An override always wins over the swap.

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
    {"student_id": "…", "status": "promoted|held_back|failed|skipped", "reason": null,
     "grade_level": 9, "grade_or_class": "Grade 9-A"}
  ]
}
```

`grade_level`/`grade_or_class` report the student's state after the request (unchanged for
`failed`/`skipped`).

### 5.3 `GET /school/students/{student_id}/grade-history`

Uses `_load_readable_student`, so the scope is inherited unchanged: own school for every school role,
assigned students only for a teacher, own children only for a parent (`403` otherwise, `404` for an
unknown ID). Returns
`{"student": {"id", "full_name"}, "history": [{"id", "action", "from": {"academic_year_id",
"academic_year_label", "grade_level", "grade_or_class"}, "to": {…same…}, "created_at"}]}`, newest first
(`created_at DESC, id DESC`). A never-promoted student returns `"history": []`. The performer is stored
but deliberately not returned, so a parent never receives a staff user ID.

## 6. Authorization summary

| Caller | `POST …/promotions` | `GET …/grade-history` |
|---|---|---|
| No session | 401 | 401 |
| `school_coordinator`, own school | allowed | allowed |
| `school_coordinator`, any listed student at another school | 403, nothing written | 403 |
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
  changes.
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
- **AC-04** A request naming any student at another school returns `403` and changes no student and
  no history row, including when the list mixes own and foreign students.
- **AC-05** Principal, teacher and parent get `403`; no session gets `401`; admin roles get `403`.
- **AC-06** A Grade 12 student, a student with NULL `grade_level`, and a student with an
  unswappable label each fail only their own row with the documented reason; all other rows commit; an
  override resolves `label_unparseable`.
- **AC-07** Submitting the same request twice, or two concurrent identical requests, promotes each
  student exactly once (second attempt is `skipped: already_processed`); the database never contains
  two rows for the same student and target year.
- **AC-08** With no active year the endpoint returns `409`; empty, oversized, duplicated, malformed or
  wrong-action payloads return `422`; an unknown ID returns `404`.
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
confirmed at plan time); `409` no active year; `422` cases; `404`; history scoping for coordinator,
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
- `docs/architecture/API_CONTRACT.md`: the two new endpoints.
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
