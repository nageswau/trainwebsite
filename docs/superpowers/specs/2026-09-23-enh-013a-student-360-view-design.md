# ENH-013a — Student 360° View / Career Passport — Design

Status: design approved in-session 2026-09-23 (sections 1–3 plus the API, frontend and security passes).
Backlog: `docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-013. Evidence: `School CRM.md` §8, §35, Part B §8.

## 1. Problem

There is no single aggregated student view. The data for most of the requirement's tabs already exists across
SCH-004/005/006/007/009/010, ENH-004, ENH-011 and ENH-012, but only as separate screens. Two read endpoints come
close: `GET /school/students/{id}/overview` (SCH-007, school roles only) and `GET /school/students/{id}/portfolio`
(ENH-012, 7 roles). §8's "Career Goal" does not exist anywhere.

## 2. Goals and non-goals

Goals (ENH-013a):
- One read endpoint and one screen presenting all 16 named tabs for one student, per viewing role.
- A `career_goal` field on the Overview, set by the Career Counselor.
- Every tab renders an empty state, never an error, for a student with no data.
- No role sees anything through this view that it cannot already read through an existing endpoint.

Non-goals (deferred, recorded rather than faked):
- ENH-013b: new Documents / Teacher Remarks log / Parent Communication log entities.
- Daily attendance (ENH-030), extra personal fields (ENH-025), communication centre (ENH-014).
- Grade/section-based teacher assignment.
- Parent notification on career-goal change.
- Fixing SCH-005's unvalidated `report_url` write (logged in `RAID.md` as a separate finding).

## 3. Decisions confirmed in-session (2026-09-23)

| # | Question | Decision |
|---|---|---|
| D1 | Scope | Split: 013a = view + `career_goal`; 013b = the missing entities, later |
| D2 | "15 tabs" vs 16 listed names | Keep all 16; the source inconsistency is documented, no tab silently dropped |
| D3 | Teacher rejection "outside assigned grade/section" | Existing per-student rule (`assigned_teacher_user_id`); AC reworded to "not assigned to them" |
| D4 | Roles | The same 7 read roles as ENH-012 Portfolio, reusing its loader (no third loader) |
| D5 | Career goal | Career Counselor (own portfolio) sets free text, ≤120 characters; audited |
| D6 | "Edusphere Programs" | Roll-up of the programmes the student is in: skills, test prep, languages, overseas |
| D7 | Tabs without a source | Show the real partial data plus a fixed "not tracked yet" note naming the future item |
| D8 | Parent Communication | "Not tracked yet" only: no URL string-matching, no parents' inbox/read-state exposed to staff, no parent names (no existing endpoint exposes a student's linked parents) |
| D9 | Results gate | Published only, for every role (SCH-006-AC02 unchanged) |
| D10 | UI placement | New `/360` route per role, linked from existing pages; existing pages otherwise untouched |
| D11 | Service-role exposure | "No new exposure": per-role tab building; unreadable tabs are `restricted` |
| D12 | Read trail | Structured log line per read (IDs only); no DB write on GET |

## 4. Approach

Chosen: **a new endpoint that shares the existing read code.** A new module `app/api/student_360.py` exposes
`GET /school/students/{id}/360-view` and `PATCH /school/students/{id}/career-goal`. It reuses the bodies of
`student_overview` and `get_portfolio`, pulled out into shared helpers with identical output, plus the
existing `skills_overview`.

Rejected:
- Having the frontend call `/overview`, `/portfolio` and `/grade-history` one by one. `/overview` rejects the
  service roles, so this would need an authorization change to an existing endpoint, and it would mean 4+
  calls, each able to fail separately.
- Extending `/overview`. That changes the contract and the access rules of an endpoint pinned by 5 backend
  test files and 2 Playwright specs.

Duplicate cleanup (in scope because the 360° view needs it): `_load_portfolio_student` moves from `portfolio.py`
to `schools.py` as `_load_student_for_reader`, and `PORTFOLIO_SCOPED_ROLES` (an exact copy of
`SERVICE_DELIVERY_ROLES`) is deleted. `portfolio.py` imports the moved loader. Behavior is identical.

## 5. Data model

`school_students.career_goal VARCHAR(120) NULL`. Migration `0039_student_career_goal` (revises
`0038_portfolio`): `op.add_column` only. No default, no backfill, no existing row read or written. On Postgres
a nullable column without a default only updates table metadata. `downgrade()` drops the column. The dev
`create_all` path picks it up from the model. `_student_out` is **not** changed, so `/students/{id}` keeps
its contract.

## 6. API contract

Errors use FastAPI's existing `{"detail": ...}` shape; there are no custom handlers. Field names are
snake_case, matching the codebase.

### 6.1 `GET /api/v1/school/students/{student_id}/360-view`

| Case | Status | Detail |
|---|---|---|
| No or invalid session | 401 | `get_current_user` (unchanged) |
| Role outside the 7 | 403 | "School role required" (existing `_own_school_id` text) |
| Student not found | 404 | "Student not found" |
| Other institution / not assigned / not linked / outside portfolio | 403 | existing message for each case |
| Malformed UUID | 422 | FastAPI path validation |

Response (Pydantic `Student360Out`):

```
{
  "student": {"id", "full_name", "school_name",
              # school roles only, null for service roles:
              "student_code", "grade_or_class", "date_of_birth", "assigned_teacher_name"},
  "career_goal": str | null,
  "can_edit_career_goal": bool,
  "tabs": { <16 keys, always present, in display order> : Tab }
}
Tab = {"status": "has_data" | "empty" | "restricted", "not_tracked": [str], "data": {...}}
```

Tab keys, in order: `overview, personal_details, academic_records, attendance, examination_results,
career_guidance, psychometric_assessment, skills, foreign_languages, english_testing, activities,
certificates, documents, teacher_remarks, parent_communication, edusphere_programs`.

- `restricted`: `data` is `{}`, and `not_tracked` is empty. The UI shows "Not available for your role".
- `empty`: every list in `data` is empty.
- `not_tracked` holds fixed server-side text only (see §6.4), never user input.
- No pagination: this is a single-resource aggregate, and its lists are bounded by one student's history
  (the same as `/overview` and `/portfolio`).
- Read-only: no commit, no locks, no AuditLog. One `logger.info("student_360_view", actor_id, role,
  student_id)` per successful read, with IDs only.

### 6.2 `PATCH /api/v1/school/students/{student_id}/career-goal`

Body `CareerGoalUpdate`: `{"career_goal": str | null}`, `extra="forbid"`, `str_strip_whitespace`,
`max_length=120`, cleaned by the existing single-line `clean_free_text` rule; empty or null clears it. A
missing key is a 422.

200 → `{"school_student_id", "career_goal", "updated_at"}`.

| Case | Status |
|---|---|
| Role ≠ `career_counselor` | 403 "Career Counselor role required" |
| Student not found | 404 |
| Student outside the counselor's portfolio | 403 (existing `_student_in_portfolio` text) |
| Validation failure | 422 |

The transaction runs as one unit:
1. `_student_in_portfolio` checks scope.
2. `SELECT … FOR UPDATE` on the student row (the same lock transfer approval takes, `school_transfers.py:398`).
3. Re-check `school_id ∈ portfolio` under the lock (403 if a transfer committed in between).
4. Set the column and add `AuditLog(action="school.career_goal_update", entity_type="school_student",
   metadata_json={"old": …, "new": …})`, then commit.

Any exception rolls the whole unit back. A retry is naturally safe (it sets a value): no idempotency key and
no ETag. Concurrent counselors are last-write-wins, with both writes kept in the audit log. Log line
`career_goal_update` with IDs only.

### 6.3 Role × tab matrix ("no new exposure")

S = the school roles (Coordinator/Principal/Teacher/Parent, already scoped by `_load_readable_student`).
AT = academic_team, CC = career_counselor, PT = psychometric_team. Each cell comes from what that role can
already read through an existing endpoint.

| Tab | S | AT | CC | PT |
|---|---|---|---|---|
| overview | career goal, status tiles, achievements (portfolio `award`+`competition`) | goal, tiles for visible tabs, achievements | same | same |
| personal_details | code, name, DOB, grade, school, assigned teacher | name, school | name, school | name, school |
| academic_records | current grade/year + grade history | restricted | restricted | restricted |
| attendance | activity attendance, skill-session attendance summary; not_tracked: daily attendance | restricted | restricted | restricted |
| examination_results | published results incl. marks/remarks (`_result_out`) | same as S | term, subject, grade, published_at | same as CC |
| career_guidance | guidance, counselling, recommendations | same | same | same |
| psychometric_assessment | type, status, report link, date | type, report link, date | same as AT | same as S |
| skills | skills batches summary (`skills_overview`) + portfolio `skill` entries | portfolio entries only | batches + entries | portfolio entries only |
| foreign_languages | full records | full records | language, level, certification_status | same as CC |
| english_testing | test prep records | same | restricted | restricted |
| activities | attended activities + portfolio project/internship/sport/leadership/volunteering/extracurricular | portfolio part only | portfolio part only | portfolio part only |
| certificates | portfolio `certification` entries | same | same | same |
| documents | psychometric report links; not_tracked: document registry (ENH-013b) | same | same | same |
| teacher_remarks | remarks on published results | same | restricted | restricted |
| parent_communication | not_tracked only (ENH-013b / ENH-014) | same | same | same |
| edusphere_programs | skills, test prep, languages, overseas applications | programmes from tabs it can see | same | same |

`can_edit_career_goal` is true only for CC. It is a UI hint only; the PATCH enforces the rule itself.

### 6.4 Fixed `not_tracked` text

- attendance: "Daily and period attendance is not tracked yet (ENH-030)."
- personal_details: "Additional profile fields are not tracked yet (ENH-025)."
- documents: "A student document registry is not tracked yet (ENH-013b)."
- teacher_remarks: "A standalone teacher remarks log is not tracked yet (ENH-013b)."
- parent_communication: "A parent communication log is not tracked yet (ENH-013b / ENH-014)."

## 7. Reuse and refactors (behavior-preserving)

- `schools.py`: extract `_overview_payload(db, student)` from the body of `student_overview`. The route becomes
  loader + helper. Output identical.
- `portfolio.py`: extract `portfolio_payload(db, user, student)` from the body of `get_portfolio`. Output identical.
- `schools.py`: add `_load_student_for_reader` (moved from `portfolio.py`); delete `PORTFOLIO_SCOPED_ROLES`.
- Unchanged: `_load_readable_student`, `_student_in_portfolio`, `_scoped_students_query`, `_student_out`,
  every write path, `get_current_user`.
- `student_360.py` builds the tabs by calling those helpers plus one grade-history query. Every query uses the
  **loaded** `student.id`, never the raw path value. Fixed query count (§11 test).

## 8. Frontend

- Routes (thin, per role, existing convention), each with a `loading.tsx`:
  `/school/{coordinator,principal,teacher}/students/[id]/360`, `/school/parent/children/[id]/360`,
  `/school/{academic-team,career-counselor,psychometric-team}/students/[id]/360`.
- Entry links: "Open 360° view" in `SchoolStudentDetailPanel` and on the parent child page; a per-row link on
  the three service-role dashboards' student lists.
- `lib/student360.ts` (server-only): types + `loadStudent360()` through `serverApi` (`cache: "no-store"`;
  never `publicApi`, which caches for 60 seconds).
- `Student360View.tsx` (server): header card and tab shell.
- `Student360Tabs.tsx` (client): the ARIA tabs pattern. Roving tabindex; arrow keys (all four), Home/End,
  Enter/Space. Vertical above 980px, a horizontally scrolling row with scroll-snap below. Tabs at least 44px
  tall. `?tab=` kept in sync via `router.replace({scroll:false})`; an unknown value falls back to `overview`.
  Tab label shows a count when it has data. For empty/restricted tabs a visually hidden suffix says ", no
  records yet" / ", not available for your role", so state is never shown by color alone.
- `Student360Panels.tsx`: one small presentational function per tab, plus the shared empty / restricted /
  not-tracked blocks (`.empty`, `role="status"`).
- `CareerGoalForm.tsx` (client): the same interaction shape as ENH-012's `PersonalStatementSection`: `inFlight`
  guard, "Saving…", `.form-error role="alert"` with `detailMessage`, `refocus()`, Escape cancels, a live n/120
  counter, `router.refresh()` on success, no optimistic update.
- Safe links: `report_url` becomes a link only when it is a same-origin path (`/`, not `//`) or `https:`;
  otherwise it is plain text.
- Errors: `accessUnavailable(e)` (a signed-out user gets a login link, anyone else their dashboard).
- Reused: `PortalShell`, `SCHOOL_NAV`, `StatusChip`, `formatDate`, `SchoolGradeHistory`, `SkillsCard` (made
  exported, additive), `MODULE_LABEL`, the existing CSS tokens and classes. No new dependencies.

## 9. Security summary

Authentication is unchanged (httponly, samesite=lax cookie + JWT). IDOR is handled by the loader running
before any query, which then uses only the loaded student. Mass assignment is blocked by `extra="forbid"`.
XSS: React escaping plus safe links; no `dangerouslySetInnerHTML`. CSRF: samesite=lax + CORS allowlist. SQL
injection: ORM only. Logs carry IDs only. No rate limiter is added (none exists for reads; noted). Existing
404-vs-403 existence disclosure is kept for consistency (UUIDv4 IDs).

## 10. Acceptance criteria

- AC-01 Given a student with data in every source, when their Coordinator opens the 360° view, then all 16
  tabs appear in order and each is `has_data`, except `parent_communication`.
- AC-02 Given a teacher at the same school, when they request the 360° view of a student not assigned to
  them, then the response is 403 "This student is not assigned to you" and the page shows Access Unavailable.
- AC-03 An unlinked parent, a principal or coordinator at another school, a service role outside its
  portfolio, and any other role → 403; a missing student → 404; no session → 401.
- AC-04 A new student with no records → 200 for every allowed role, and every visible tab is `empty` and
  renders an empty state.
- AC-05 For each service role, restricted tabs carry no source data and limited tabs carry only the allowed
  fields (§6.3).
- AC-06 Draft/verified results never appear in any tab, for any role.
- AC-07 An in-scope Career Counselor can set/clear the goal (200, audit row, visible to every viewer). Any other
  role → 403; an out-of-scope counselor → 403; more than 120 characters, control characters or extra fields →
  422.
- AC-08 A career-goal write that races an approved transfer never writes once the student has left the
  counselor's portfolio.
- AC-09 The query count is identical for 1 and for 20 rows per source.
- AC-10 `/overview`, `/portfolio` and `/students/{id}` responses are unchanged (their existing tests stay green
  unmodified).
- AC-11 The tabs follow the ARIA tabs pattern with arrow/Home/End keys, and the page works at 320px with no page
  horizontal scroll.
- AC-12 A `report_url` that is `javascript:`, `data:` or `//host` renders as plain text, never a link.

## 11. Test plan (written before code)

- `tests/test_enh_013_360_view.py`: scope matrix (7 roles × in/out, 404, 401); the 16-key envelope; empty
  student; per-role redaction; published-only; query count; the log line carries no payload.
- `tests/test_enh_013_career_goal.py`: validation; role and scope; audit row; rollback when the audit insert
  fails; transfer race (two sessions, the `test_enh_005_concurrency` pattern).
- `tests/test_enh_013_migration.py`: existing rows keep a null `career_goal`; downgrade works.
- Unmodified existing suites as the refactor proof: `test_sch_007/009/010`, `test_enh_005_scope`,
  `test_enh_011_read_surfaces`, `test_enh_012_digital_portfolio`.
- vitest: `Student360Tabs`, `Student360Panels`, `CareerGoalForm`, safe links, `lib/student360` uses
  `serverApi`, the client-boundary guard.
- Playwright `enh-013-student-360.spec.ts`: AC-01, AC-02, AC-04, a counselor sets the goal → the parent sees
  it, the psychometric team sees restricted tabs, keyboard-only navigation, 390px mobile.

## 12. Regression risks

1. Extracting the helpers: a pure move, pinned by 6+ unmodified test files.
2. Moving the loader: ENH-012's tests, plus a test that `portfolio.py`'s scope is unchanged.
3. Migration head collision with parallel ENH branches: check for a single alembic head at merge time.
4. `SchoolStudentDetailPanel` gains one link: covered by the SCH-008 and ENH-004/005 E2E suites.
5. `SkillsCard` export: additive.
6. Performance: the query-count test.

## 13. Documentation deliverables

RTM row; screen catalogue entries; `RAID.md` finding (SCH-005 `report_url` write validation); backlog ENH-013
note (split into 013a/013b; D2/D3 source inconsistencies).
