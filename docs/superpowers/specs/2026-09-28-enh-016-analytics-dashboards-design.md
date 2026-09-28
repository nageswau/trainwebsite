# ENH-016 — School & Edusphere Analytics Dashboards — Design

## 1. Problem (audit result)

`docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-016 (`DERIVED_BLUEPRINT`), sourced from `School CRM.md` §1, §27, §28, §29, §34 and
Part B §14 (`ORIGINAL_REQUIREMENT`, `functionalities/edusphere_markdown/School CRM.md`). Acceptance criterion (backlog):
*"Each dashboard renders correctly scoped aggregate data for its intended role; cross-school dashboard is inaccessible to
school-side roles."*

A Graphify-oriented investigation (2026-09-28, `origin/main` at `03d4408`) found:

1. **§1 is mostly built but not shown.** `GET /school/dashboard` (`schools.py:772`) returns `school_crm_kpis` (18 of 20 §1
   KPIs from live rows) via `_school_dashboard_payload` (`schools.py:353`). **No page renders `school_crm_kpis`**: the
   coordinator dashboard uses only `student_count` and `upcoming_activities`, and `SchoolReportsPanel` shows grade bars,
   three completion rings and activities.
2. **Two "untracked" flags are stale.** `digital_portfolios_created` (`schools.py:88`) — ENH-012 (`portfolio_entries`,
   `portfolio_profiles`) has since shipped. `skills_training` in `UNTRACKED_SCHOOL_DASHBOARD_CHARTS` (`schools.py:92`) —
   ENH-011 skill batches have shipped. `internships` stays untracked (no model).
3. **§27 exists for one school only.** `GET /school/entitlements` (`schools.py:1020`) counts usage inline in the route
   handler. `digital_portfolio_creation` still reports `used: null` although ENH-012 data now exists.
4. **Principal dashboard has no KPI board**: it fetches only `/school/students`.
5. **§28, §29, §34, Part B §14 do not exist.** The nearest reusable logic is `_overview_payload` (`schools.py:1153`,
   per-student status per area), `school_skills._rollup`/`skill_usage`, and ENH-012's `portfolio_payload`
   (`portfolio.py:91`, completion %).
6. **Conventions to follow** (ENH-005 `school_transfers.py`, ENH-018 `school_feedback.py`): a feature module with a
   `/school` router and an `/overseas-admin` router so `schools.py`/`admin.py` do not grow; role checks as FastAPI
   dependencies (403 before 422); `response_model`s in `schemas.py`; `limit=Query(25, ge=1, le=100)`/`offset` pages
   returning `{items, total, limit, offset}`; constant `detail` strings; reads logged with `logger.info` (ids only) and
   never written to `AuditLog` (`student_360.py:133`).
7. `edusphere_school_manager`/`school_partnership_manager` are **not modeled** (`RBAC_MATRIX.md:239`, open item 75).

## 2. Goals and non-goals

**Goals.** Role-scoped, read-only dashboards for §1, §27 (cross-school), §28, §29, §34 and Part B §14, computed live from
existing School-domain rows with a fixed number of queries per request, never showing a fabricated number, and never
leaking one school's data to another school.

**Non-goals.**
- Any write, migration, summary/materialized table, background job or cache (backlog: build simple, measure first).
- New roles or grants (`edusphere_school_manager` stays deferred).
- Teacher/Parent/service-role access to any ENH-016 view (they keep the ENH-013 360° view).
- Scholarship and internship tracking (owned by ENH-017 / ENH-020); they render as *not tracked*.
- A platform rate limiter; `AuditLog` rows for reads.
- Removing the unreachable code after `return` in `school_reports` (`schools.py:781`) — separate change (D8).
- Changes to `/admin/dashboard`, `services/portal.py`, `TIER_SERVICES`, `_cumulative_services`, ENH-022/023 enforcement.

## 3. Decisions confirmed in-session (2026-09-28) — `DEC-SCOPE-034` (provisional number)

> **Merge note (2026-09-28, `main` merged into this branch):** recorded in-session as `DEC-SCOPE-031`; `ENH-026`/`ENH-021`/
> `ENH-024` reached `main` first holding 031–033, so this is now **`DEC-SCOPE-034`**. The merge also brought two modules this
> spec treated as absent or simpler, and ENH-016 follows them rather than contradicting them: **internships** (`ENH-021`,
> `DEC-SCOPE-032`) are tracked — the scorecard's Internship row uses ENH-021's `internship_progress` (best progress wins; plan
> service `internships`), the §34 outcome counts students with any internship entry (the dashboard KPI's definition), and it
> joins the §27 participation set; **guidance/counselling** (`ENH-026` C5, `DEC-SCOPE-031`) count only delivered sessions
> (`counts_as_completed`), in the indicators and in `service_usage`'s `individual_counselling`, exactly as `main`'s dashboard
> and entitlements now do. Statements below that call internships untracked describe the pre-merge state.

Renumbered on merge if another branch lands `031` first (`DEC-SCOPE-024`/`025`/`030` precedent).

| # | Question | Decision (user, `EXPLICIT_APPROVAL`) |
|---|---|---|
| D1 | Cross-school audience | `overseas_admin` + `super_admin` only. `it_admin` and every school-side role → 403. |
| D2 | "Pending" | Total students − students who completed that activity. |
| D3 | Scorecard states | Derived from existing records: ✅ completed · 🔄 started, not completed · ⏳ service in the school's tier, not started · — not in tier / no module. Per-area rules §6.3. |
| D4 | At-risk / top performer | Configurable thresholds on published-result average %: at-risk `< 40`, top `≥ 85` by default (defaults `NEEDS_CONFIRMATION`). |
| D5 | §29 undefined metrics | Labelled proxies from existing data (§6.2). |
| D6 | §34 windows | New = `partnership_date` (else `created_at`) within the last 90 days; renewal due = `tier_valid_until` ≤ today + 60 days, expired included. "Today" is India time (`_today_ist`). **Revised 2026-09-28 (user):** `schools` has no status column, so active = a valid partnership tier — set and not past `tier_valid_until` — which is ENH-022's own `_entitlement_denial(tier, valid_until, None, today) is None`. |
| D7 | "School Master" (Part B §14) | Principal + Coordinator. Principal dashboard gains the KPI board. |
| D8 | Cleanup in scope | Mark digital portfolios and skills training tracked. Dead code in `/school/reports` stays out. |
| D9 | Scorecard audience | Coordinator + Principal only, own school. |
| D10 | Scorecard placement | Per-student card + paginated school-wide grid. |
| D11 | "Digital Portfolios Created" | Student has ≥ 1 `portfolio_entries` row or a non-blank `portfolio_profiles.personal_statement`. |
| D12 | Scorecard Digital Portfolio row | ✅ ENH-012 completion = 100 · 🔄 D11 true but < 100 · ⏳ `digital_portfolio_creation` in tier, D11 false · — not in tier. |
| D13 | Entitlement usage | `/school/entitlements` reports `used` for `digital_portfolio_creation` = D11 count. |
| D14 | Approach | **A**: one feature module, grouped SQL aggregation over a set of school ids; fixed query count. (B — loop per-school payloads — rejected: O(schools × rows). C — summary tables — rejected: migration, staleness, YAGNI.) |
| D15 | Read audit | Structured `logger.info` per request (ids/counts only); no `AuditLog` row (codebase convention: only writes are audited). |
| D16 | Rate limiting | No new limiter (none exists platform-wide; authenticated, bounded reads). Accepted risk, §12. |

## 4. Architecture

### 4.1 Module layout

- **New `apps/api/app/api/school_analytics.py`**: `school_router = APIRouter(prefix="/school", tags=["school-analytics"])`,
  `admin_router = APIRouter(prefix="/overseas-admin", tags=["school-analytics"])`, the aggregation functions, and one
  dependency `_require_school_admin` (same body as `school_feedback._require_feedback_admin`; not imported because of its
  feature-specific name). `_require_school_reader` is imported from `school_feedback` unchanged. Registered in `main.py`
  beside the other routers.
- **`schools.py`** (minimal, see §5): extract `service_usage`, flip D8 flags, compute `digital_portfolios_created`.
- **`portfolio.py`**: extract ENH-012's completion formula, unchanged, into a pure `portfolio_completion(...)`.
- **`school_skills.py`**: add `skill_usage_many(db, school_ids)`; `skill_usage` delegates to it (§5.2).
- **`schemas.py`**: response models (§7).

No new dependency, no migration, no model change.

### 4.2 Shared aggregation primitives (in `school_analytics.py`)

All take `school_ids: Collection[UUID]` and return dicts keyed by school id (and grade where relevant). Every query is a
SQLAlchemy expression with bound parameters; `COUNT(DISTINCT school_student_id)` / `GROUP BY school_id[, grade]` joined
through `school_students.school_id` (indexed). No function flushes or commits.

- `student_indicators(db, school_ids) -> dict[str, dict[UUID, set[UUID]]]` — for each indicator (§6.1), the set of
  student ids holding it, per school. One query per source table (career, psychometric, test prep, language, skill
  enrolments, portfolio entries, portfolio profiles, applications, visa cases, activity attendance) regardless of school
  count. Used by §1-derived views, §29, Part B §14 and §34.
- `grade_of(students)` — `grade_level`, else `schools._grade_level_from_label(grade_or_class)`, else `"unspecified"`.
- `service_usage(db, school_ids)` — see §5.2.

## 5. Changes to existing endpoints (the only contract changes)

### 5.1 `/school/dashboard` and `/school/reports` (`_school_dashboard_payload`)

- `digital_portfolios_created`: `{"value": <D11 count>, "tracked": true, "note": null}` (was `null`/`false`).
- `untracked_charts` no longer contains `skills_training`; a new key `skills_training`
  `{"soft_skills": n, "digital_skills": n, "total_students": N}` (non-withdrawn enrolments, distinct students) is **added**.
- `UNTRACKED_SCHOOL_DASHBOARD_KPIS` keeps `internships` only. No key is renamed or removed from the payload.

### 5.2 `/school/entitlements` — extraction

The inline usage block becomes `service_usage(db, school_ids) -> dict[UUID, dict[str, int | bool | None]]` in
`schools.py`, computed with one grouped query per source (`GROUP BY school_id[, type]`), so its query count does not
depend on the number of schools (AC17). For skills, `school_skills.py` gains `skill_usage_many(db, school_ids)` (the same
query as `skill_usage`, grouped additionally by `SchoolSkillBatch.school_id`); `skill_usage(db, school_id)` becomes a thin
call to it with an unchanged signature and result, guarded by the existing ENH-011 tests. The endpoint calls
`service_usage(db, [school_id])[school_id]`.

Response: byte-identical to today **except** `digital_portfolio_creation.used` = D11 count (D13) when the service is
included. Pinned by a snapshot test written before the extraction (§11).

## 6. Metric definitions

### 6.1 Indicators (per student)

| Indicator | Rule (source rows) |
|---|---|
| `guidance` | `school_career_records.record_type = 'guidance_session'` |
| `counselling` | `record_type = 'counselling_note'` |
| `psych_completed` / `psych_started` | `school_psychometric_records.status = 'completed'` / any row |
| `test_prep_completed` / `test_prep_started` | all of the student's `school_test_prep_records` have `status='completed'` / any row (mirrors `_overview_payload`) |
| `ielts` / `sat` | any test-prep row with `test_type` `ielts` / `sat` |
| `language_certified` / `language_started` | any `certification_status='certified'` / any row |
| `soft_skills_*`, `digital_skills_*` | `school_skills._rollup` statuses over non-withdrawn enrolments: `completed`(completed or certified) / `in_progress` |
| `skills_enrolled` | any non-withdrawn skill enrolment |
| `portfolio_started` | D11 |
| `awareness_attended` | present attendance at a `career_awareness_session` or `career_seminar` activity |
| `global` | any `overseas_applications` row with this `school_student_id` |
| `shortlisted` | an application at stage ≥ `university_selection` (`_stage_at_or_after`) |
| `applied_active` | an application not in `withdrawn`/`rejected` |
| `offer` | status in `OFFER_ONWARD_STATUSES` or `offer_letter_url` set |
| `visa_started` | a `visa_cases` row on one of the student's applications |
| `admitted` | an application with `status='enrolled'` |

### 6.2 §29 grade comparison (D5)

Columns: grades 8–12, plus `other` (a `grade_level` outside 8–12) and `unspecified` (no grade), each only if non-zero. Each metric is `{count, pct}` with `pct = null` when the grade
has 0 students.

| Metric (label shown) | Rule |
|---|---|
| Students | roster count |
| Career readiness *(estimate)* | `guidance ∧ psych_completed` |
| Assessment completion | `psych_completed` |
| Counselling completion | `counselling` |
| Skills development *(estimate)* | `skills_enrolled` |
| Global education interest *(estimate)* | `global` |
| Application readiness *(estimate)* | `shortlisted` |
| University applications | `applied_active` |
| Admissions | `admitted` |

"*(estimate)*" rows carry `"is_proxy": true` and a `definition` string; the UI shows the definition as helper text.

### 6.3 §28 scorecard (D3, D9, D10, D12)

State enum: `completed | in_progress | not_started | not_in_plan | not_tracked`. `not_started` is used only when the
area's service key is in `_cumulative_services(school.tier)` (same inclusion rule as `/school/entitlements`, which does not
apply expiry); otherwise `not_in_plan`. UI: ✅ Completed · 🔄 In progress · ⏳ Not started · — Not in plan · — Not tracked
yet (icon **and** text).

| Area | Service key (plan check) | completed | in_progress |
|---|---|---|---|
| Career Awareness | `career_awareness_session` | `awareness_attended ∨ guidance` | — |
| Psychometric | `psychometric_test` | `psych_completed` | `psych_started` |
| Career Counselling | `individual_counselling` | `counselling` | — |
| Soft Skills | `soft_skills` | soft_skills `completed` | soft_skills `in_progress` |
| Foreign Language | `foreign_language_classes` | `language_certified` | `language_started` |
| Digital Portfolio | `digital_portfolio_creation` | completion = 100 (D12) | `portfolio_started` |
| IELTS/SAT | `ielts_coaching` or `sat_coaching` | `test_prep_completed` | `test_prep_started` |
| University Shortlisting | `application_support` | `shortlisted` | `global` |
| Scholarship | — | `not_tracked` always (no school-student scholarship link; ENH-017) | |
| Application | `application_support` | `offer` | `applied_active` |
| Visa | `visa_support` | `admitted` *(NEEDS_CONFIRMATION: `visa_cases.status` is free text with no terminal value)* | `visa_started` |
| Internship | — | `not_tracked` always (no model; ENH-020) | |

Completion % for the Digital Portfolio row uses `portfolio.portfolio_completion(...)` (§4.1), fed in bulk. A test asserts
equality with `GET /school/students/{id}/portfolio` for the same fixture (§11).

### 6.4 Part B §14 student development (D2, D4, D7)

- Headcounts: students (roster), teachers, parents — reusing `_parent_ids_at_school` / `_account_belongs_to_school`
  exactly as `_school_dashboard_payload` counts them.
- Completed/Pending rows (`pending = total − completed`): Career Guidance (`guidance`), Psychometric Test
  (`psych_completed`), Foreign Language (`language_certified`), English Testing (`ielts` with `test_prep_completed`),
  University Guidance (`shortlisted`).
- Academic performance — **published results only**, `status='published'` (SCH-006-AC02; withdrawn excluded by
  definition). Percentage per result = `schools._percentage(max_marks, marks_obtained)`; a student's average = mean of
  their result percentages.
  - Grade-wise: average of student averages per grade, plus student count with results.
  - Subject-wise: average percentage per `subject`, result count.
  - Student progress: school average per (`academic_year`, `term`), ordered.
  - At-risk: students with average `< at_risk_below`; top performers: `≥ top_from`. Each list sorted (asc / desc by
    average, then name), capped at 50, with `total`. Fields: `school_student_id`, `full_name`, `grade`, `average_pct`,
    `result_count`.

### 6.5 §34 cross-school (D1, D6) and §27 rollup

- Schools: `total`, `active`, `new`, `renewal_due` (D6).
- Students: `total`, `by_grade` (8–12 + unspecified), `career_guidance`, `psychometric`, `counselling`, `global_education`.
- Services (summed over schools from `service_usage` + `_cumulative_services(tier)`): per school, over included services —
  `delivered` = used > 0 or `True`; `pending` = used 0 or `False`; `not_tracked` = used `None`;
  `utilization_pct = delivered / (included − not_tracked)` or `null` when the denominator is 0.
- Outcomes: `applications` (count of `applied_active` applications), `offers`, `visas` (students `visa_started`),
  `admissions`, `scholarships` and `internships` as `{"value": null, "tracked": false, "note": …}`.
- Per-school rows (§27 "school-wise"): `school_id`, `name`, `tier`, `tier_valid_until`, `is_active`, `is_new`, `renewal_due`, `students`,
  `services_included`, `delivered`, `pending`, `not_tracked`, `utilization_pct`, `student_participation`
  (students with ≥ 1 indicator of §6.1 other than roster), `pending_activities` (activities scheduled ≥ now). Ordered by
  `name`, then `id`. **No student-level field anywhere in the cross-school responses.**

## 7. Endpoints

All `GET`, no body, no side effects, safe to retry. `detail` strings are constants.

| Route | Dependency | Params | Response model |
|---|---|---|---|
| `/school/analytics/grade-performance` | `_require_school_reader` | — | `GradePerformanceOut` |
| `/school/analytics/student-development` | `_require_school_reader` | `at_risk_below: int = Query(40, ge=0, le=100)`, `top_from: int = Query(85, ge=0, le=100)` | `StudentDevelopmentOut` |
| `/school/analytics/scorecards` | `_require_school_reader` | `grade: Literal[8,9,10,11,12] \| None`, `limit=Query(25, ge=1, le=100)`, `offset=Query(0, ge=0)` | `ScorecardPage {items, total, limit, offset}` |
| `/school/students/{student_id}/scorecard` | `_require_school_reader` | path UUID | `ScorecardOut` |
| `/overseas-admin/analytics/summary` | `_require_school_admin` | — | `CrossSchoolSummaryOut` |
| `/overseas-admin/analytics/schools` | `_require_school_admin` | `limit`, `offset` as above | `SchoolUtilizationPage {items, total, limit, offset}` |

Errors:
- 401 unauthenticated (existing `get_current_user`).
- 403 `"School Coordinator or Principal role required"` / `"This account is not linked to a school"` (existing strings) /
  `"Overseas Admin role required"`. Dependencies run before query validation → 403 precedes 422.
- 404 `STUDENT_NOT_FOUND = "Student not found"` for a missing student **or** one at another school (looked up with
  `id = :sid AND school_id = :own`; no existence oracle).
- 422 FastAPI validation for out-of-range params; 422 `THRESHOLD_ORDER = "at_risk_below must be less than top_from"`.
- 500 via the existing handler; no internals in `detail`.

Scorecard grid ordering: `full_name`, then `id` (stable pagination). The school's tier is read once per request.

## 8. Frontend

Server components with `serverApi`; no client JS, no new npm dependency. Reuse: `PortalShell`, `.card`, `.table`,
`.muted`, `.badge`, `.eyebrow`, `GradeBarChart`, `CompletionRing`, `accessUnavailable`/`accessDenied`, the static-route
pattern of `overseas/admin/school-transfers/page.tsx`, the `loading.tsx` pattern of `coordinator/feedback/loading.tsx`.

| File | Change |
|---|---|
| `components/SchoolKpiBoard.tsx` (new) | Renders `school_crm_kpis` in four `h3` groups (Students · Career & assessment · Skills & languages · Global pathway). Untracked KPI → "Not tracked yet" + visible note. |
| `components/SchoolGradePerformance.tsx` (new) | `<table>` (grades as columns, metrics as rows, sticky first column, `<caption>`), proxy rows show definition helper text; a small grouped bar per metric using existing chart CSS. |
| `components/SchoolStudentDevelopment.tsx` (new) | Headcounts, Completed/Pending table, grade/subject/term averages tables, at-risk and top lists, threshold `<form method="get">` with two labelled `number` inputs (0–100). |
| `components/SchoolScorecardGrid.tsx` (new) | `<form method="get">` with labelled grade `<select>`, table student × 12 areas, Prev/Next links (`?grade=&offset=`), student name links to the student page. |
| `components/StudentScorecard.tsx` (new) | 12-row status list for one student. Shared `ScorecardState` badge (icon + text) lives here and is imported by the grid. |
| `app/school/coordinator/dashboard/page.tsx` | Add `<SchoolKpiBoard kpis={data.school_crm_kpis}/>`; extend its `DashboardPayload` type. Nothing removed. |
| `app/school/principal/dashboard/page.tsx` | Also fetch `/school/dashboard` (with `.catch(() => null)`), render `SchoolKpiBoard` or the section error card. |
| `app/school/{coordinator,principal}/reports/page.tsx` | After `SchoolReportsPanel`, fetch the three analytics endpoints in parallel, each `.catch(() => null)`; pass `searchParams` through for grid/threshold state. |
| `app/school/{coordinator,principal}/students/[id]/page.tsx` | Add `StudentScorecard` (own fetch, `.catch(() => null)`). |
| `app/overseas/admin/school-analytics/page.tsx` + `loading.tsx` (new) | Role check first (`accessDenied` unless `overseas_admin`/`super_admin`), then summary KPI groups and paginated per-school table. |
| `lib/navigation.ts` | `"school-analytics"` added to `PORTAL_NAV["overseas/admin"]`; `SUPER_ADMIN_NAV` gains a "School Analytics" item pointing to `/overseas/admin/school-analytics`. `SCHOOL_NAV` unchanged. |
| `lib/types.ts` | Response types. |

States for every new section:
- **Loading**: server-rendered; `loading.tsx` skeleton on the new admin page (`aria-busy="true"`).
- **Empty**: "No students on the roster yet." · "No published results yet." · "No students match this grade." ·
  "No partner schools yet."
- **Error**: per-section card "This section couldn't load. Refresh to try again." (`role="status"`); the rest of the page
  renders. Whole-page 401/403 via existing helpers.
- **Not tracked**: "Not tracked yet" + note, never 0.

Accessibility and responsive: `<table>` + `<caption>` + `<th scope>`; icon + text for every state (never colour alone);
charts carry an `aria-label` summary and sit beside their table; headings h2 section / h3 group with no skipped levels;
KPI grid 1 column at 320 px → 2 at 768 px → 4 at ≥ 1024 px; wide tables scroll inside their card (no page-level
horizontal scroll); forms are plain GET forms, keyboard-operable in default focus order, with visible labels.

## 9. Transactions, concurrency, data

- Read-only: no `add`, `flush` or `commit` in any ENH-016 route or helper; no data is created, changed or deleted.
- Each request runs its queries in the request's session under PostgreSQL's default READ COMMITTED. A concurrent write
  between two queries can make one figure differ by one within a response; accepted for dashboards (no REPEATABLE READ).
  No lost-update or write-race surface exists.
- `service_usage` keeps the single-session, non-committing semantics of the code it replaces.
- A student transferred (ENH-005) counts at their current `school_id`; their portfolio rows follow them.

## 10. Performance

- Fixed query count per endpoint, independent of the number of schools and students (asserted in tests with 1 vs 5
  schools via a SQLAlchemy `before_cursor_execute` counter).
- Grouping is by indexed FKs (`school_students.school_id`, every `school_student_id`, `school_skill_batches (school_id,
  module_type)`). No migration.
- Scorecard grid computes indicators only for the page's student ids.
- A seeded timing check (e.g. 20 schools × 200 students) is recorded in the RTM; a summary table is considered only if it
  fails a budget agreed then.

## 11. Acceptance criteria (local IDs)

- **AC01** Coordinator and Principal each receive their own school's §29, Part B §14 and §28 data; figures equal
  hand-computed fixture values.
- **AC02** No ENH-016 school endpoint ever includes another school's students, results, counts or names.
- **AC03** Teacher, Parent, `academic_team`, `career_counselor`, `psychometric_team`, `it_admin`, `overseas_student` → 403
  on every school analytics endpoint; a school account without `school_id` → 403.
- **AC04** Every school-side role → 403 on both `/overseas-admin/analytics/*`; `overseas_admin` and `super_admin` → 200.
- **AC05** `/school/students/{id}/scorecard` for a student at another school → 404 identical to a random UUID.
- **AC06** At-risk/top lists use published results only; a draft/verified/withdrawn result changes nothing.
- **AC07** Thresholds: out of range → 422; `at_risk_below >= top_from` → 422 `THRESHOLD_ORDER`; wrong role with bad
  params → 403.
- **AC08** Pending = total − completed for every Part B §14 row.
- **AC09** D6 windows at edges: `partnership_date` 89/90/91 days ago; `tier_valid_until` today+59/60/61, and yesterday.
- **AC10** Utilization: delivered/pending/not-tracked/pct correct, `null` pct when denominator 0; tierless school has 0
  services.
- **AC11** `/school/entitlements` byte-identical to the pre-change snapshot except `digital_portfolio_creation.used` = D11.
- **AC12** `/school/dashboard`: `digital_portfolios_created` tracked with D11 count; `skills_training` absent from
  `untracked_charts` and present as a key; every pre-existing key still present.
- **AC13** D11: a student with only profile fields (DOB, grade) is not counted; one entry or a non-blank statement is.
- **AC14** Scorecard Digital Portfolio completion % equals `GET /school/students/{id}/portfolio` for the same student.
- **AC15** Each scorecard area yields each of its reachable states from fixtures; `not_started` only when the service is
  in the tier.
- **AC16** Cross-school responses contain no `school_student_id`/`full_name` fields (schema test).
- **AC17** Query count is equal for 1 and 5 schools on each endpoint.
- **AC18** UI: coordinator and principal dashboards show the KPI board; reports pages show the three sections; each
  section's empty and error state renders; admin page denies a coordinator; grid filter and paging work by keyboard.

## 12. Security review (`security-and-hardening`, 2026-09-28)

| Area | Assessment |
|---|---|
| Authentication | Unchanged: `get_current_user`, httpOnly cookies, `samesite=lax` (`auth.py:88`). |
| Authorization / escalation | Dependencies enforce role before anything else. No role, school, division or user id parameter exists. `ensure_admin` is not used (it admits `it_admin`). |
| IDOR | School id from the server-held profile only; single-student lookup is scoped in the `WHERE` clause; 404 on miss. |
| Data minimisation | Cross-school: aggregates and per-school counts only. Named at-risk/top lists: own school's Coordinator/Principal only, published results only, capped at 50. |
| Input validation | Typed query params validated by FastAPI/Pydantic at the boundary; cross-field check with a constant message. |
| XSS | React escaping only; no `dangerouslySetInnerHTML`; names and school names rendered as text. |
| CSRF | GET-only, side-effect-free routes; SameSite=lax. Not applicable. |
| SQL injection | SQLAlchemy expressions with bound parameters; no `text()` built from input. |
| Tokens / secrets | None introduced. |
| Logs | One `logger.info` per request: `actor_id`, `role`, `school_id` or `school_count`, endpoint. Never names or marks. |
| Audit | No `AuditLog` for reads (D15), consistent with ENH-013/ENH-012 reads. |
| Rate limiting | Accepted risk (D16): authenticated, bounded, fixed-query reads; a limiter would be a new platform control outside ENH-016. |
| Commercial sensitivity | Per-school comparison visible only to Edusphere-internal admin roles (backlog security impact). |

## 13. Regression risks

1. `service_usage` extraction changes `/school/entitlements` beyond D13 → caught by the snapshot test (AC11), plus
   `test_sch_011_entitlements.py`, `test_enh_022*`, `test_enh_023_tier_change.py`, e2e `sch-011`, `enh-022`, `enh-023`.
2. `_school_dashboard_payload` changes break `test_sch_reports.py` / e2e `sch-reports` → additive-only rule (AC12).
3. `skill_usage` delegation changes ENH-011 usage → `test_enh_011*`, e2e `enh-011-skills`, AC11.
   `portfolio_completion` extraction changes ENH-012 numbers → `test_enh_012*`, `test_enh_013_360_view.py`, AC14.
4. Scoping regression / cross-school leak → AC02–AC05, AC16, `test_enh_005_scope.py`, `test_rbac.py`.
5. Published-only rule → AC06, `test_sch_006_academic_results.py`.
6. Principal dashboard new fetch failing blanks the page → `.catch(() => null)` + error card (AC18).
7. Navigation change → `desktop-nav-dropdown`, `adm-014`, `auth-002-rbac-ui` e2e.

## 14. Test plan (written before code)

- **API (pytest)**: `test_enh_016_school_analytics.py` (AC01, AC06–AC08, AC13–AC15), `test_enh_016_scope.py`
  (AC02–AC05), `test_enh_016_cross_school.py` (AC09, AC10, AC16, AC17), `test_enh_016_contracts.py` (AC11 snapshot taken
  on `main` before Task 1, AC12).
- **Web unit (vitest)**: one test file per new component — populated, empty, not-tracked, error; grid form labels and
  link hrefs; `SuperAdminDashboard`/navigation tests updated for the new nav item.
- **E2E (Playwright)**: `enh-016-analytics.spec.ts` (AC18).
- **Regression**: API suites and e2e specs in §13, then the full suites per the every-3–4-features cadence.

## 15. Documentation deliverables and follow-ups

- `DEC-SCOPE-034` entry (D1–D16) in `docs/decisions/PRODUCT_DECISION_REGISTER.md`; RTM row; backlog §ENH-016 status and
  the §1/§27/§28/§29/§34/B14 coverage rows.
- Follow-ups (not in ENH-016): delete dead code in `school_reports`; confirm D4 defaults and D5 proxies with the client;
  Visa `completed` rule once `visa_cases.status` has defined terminal values; `edusphere_school_manager` scoping when
  item 75 resolves; scholarship/internship tracking via ENH-017/ENH-020.
