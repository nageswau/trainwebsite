# ENH-017 — School-Visible Global Education Pipeline — Design

**Status:** Design approved in-session 2026-09-29 (sections 1–3 presented and approved by the user; decisions D1–D10 below).
**Backlog:** `docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-017 (`DERIVED_BLUEPRINT`).
**Source:** `functionalities/edusphere_markdown/School CRM.md` (EVID-014) §16, §17, §19, §20 (and §18/§36 for the untracked stages).
**Decision record:** `DEC-SCOPE-036` (provisional number — renumber on merge if taken).
**Screen:** `SCR-SCH-038` (provisional).

## 1. Problem (audit result)

The Graphify-led audit (2026-09-29) found:

- The SCH-010 bridge (`overseas_applications.school_student_id`, migration `0029`) is built, and `GET /school/dashboard`
  (`schools.py:_school_dashboard_payload`) already computes bridged-student KPI counts and an application-count pipeline.
  The UI renders only the KPI tiles; there is no school-facing view of *which* students are at *which* stage, and no §17
  funnel.
- The only data behind the pipeline is `OverseasApplication.status` (enum `OVERSEAS_APPLICATION_STAGES`) and the existence/
  stage of a `VisaCase`. There is **no** data source for: Applications started vs submitted, Deposit, Scholarship
  (`ScholarshipApplication` links to `users` only), Top-100 ranking (no field on `University`), Alumni (no model).
- §19 explicitly limits the school to high-level status. The existing dashboard function loads full application ORM rows;
  a new view must not.

## 2. Goals and non-goals

**Goals**
- G1. A read-only Global Education page for School Coordinator and Principal showing a §17-shaped funnel of their own
  school's **bridged** students, plus a paged per-student list of each student's high-level stage.
- G2. The §19 boundary enforced at the API layer: the response can only contain the allowlisted high-level fields.
- G3. Stages without a data source are shown honestly as *not tracked*, never as a fabricated 0.

**Non-goals** (explicit — do not implement under ENH-017)
- New tables, columns or migrations (scholarship link, university ranking, alumni, visa outcomes) — follow-up items.
- Changes to `/school/dashboard`, `/school/reports`, `/school/students/{id}/overview`, `/timeline`, `/360-view`.
- Changes to ENH-016 scorecard/cross-school "scholarship not tracked" rows or `/school/entitlements` usage figures.
- A Platinum-only gate or `alumni_network` usage tracking.
- `school_partnership_manager` / `edusphere_school_manager` access (PRD open item 75).
- AuditLog rows for reads; rate limiting.

## 3. Decisions confirmed in-session (2026-09-29) — `DEC-SCOPE-036` (provisional)

| ID | Decision |
|---|---|
| D1 | **Scope: present-only.** Build over existing data; no migrations. Scholarship, Top 100, Alumni, Applications started/submitted and Deposit render as *not tracked* with a reason. |
| D2 | **Granularity:** funnel counts **plus** a per-student row: name, student code, grade, furthest stage, visa stage label, application count. No university/course/country, no overseas record ids, no notes/references/offer letters/documents/counselor/agent. |
| D3 | **Counting:** cumulative, per **student** — a student counts once in every stage they have reached on any of their applications. |
| D4 | **Roles:** `school_coordinator` and `school_principal` only (DEC-SCOPE-011; reuses `_require_school_reader`). Every other role 403. |
| D5 | **Existing exposure unchanged:** overview/timeline/360 `global_education` fields stay as confirmed under DEC-SCOPE-018 (they are already stage-level). |
| D6 | **Placement:** a new "Global Education" page for coordinator and principal (`SCR-SCH-038`); no existing page changes. |
| D7 | **Grade filter:** optional (All grades default, Grades 8–12), same `grade_key` rule as ENH-016 so a grade means the same students everywhere. |
| D8 | **Tier:** no read gate (DEC-SCOPE-027 D3 keeps reads open). `require_school_entitlement` is not called. |
| D9 | **Audit:** one structured log line per request (ids and counts only); no AuditLog row — the ENH-016 precedent for read-only school analytics. |
| D10 | **Visa stage** = a `VisaCase` exists (matches the "Visa Applications" KPI tile). The funnel is therefore not forced monotonic at Visa → Admitted (§17's own example is not monotonic either). |

## 4. Architecture

### 4.1 Module layout

- **New** `apps/api/app/api/school_global_education.py` — one `APIRouter(prefix="/school", tags=["school-global-education"])`,
  one route, pure helper functions for the stage rules.
- **Edit** `apps/api/app/main.py` — add the router to the registration tuple (additive).
- **Edit** `apps/api/app/schemas.py` — append the output models (additive).
- **New** web pages `apps/web/app/school/{coordinator,principal}/global-education/{page,loading}.tsx`.
- **New** components `apps/web/components/GlobalEducationFunnel.tsx`, `GlobalEducationStudentTable.tsx`.
- **Edit** `apps/web/lib/navigation.ts` (two nav arrays), `apps/web/lib/types.ts` (append types), `apps/web/app/globals.css`
  (append a few `.pipeline-*` rules using existing variables).

### 4.2 Reused, imported read-only (never edited)

`school_feedback._require_school_reader`; `schools._own_school_id`, `OVERSEAS_APPLICATION_STAGES`, `OFFER_ONWARD_STATUSES`,
`_stage_at_or_after`; `school_analytics.grade_key`, `students_in`, `MAX_OFFSET`; `workflows.VISA_CASE_STAGES`;
`core.logging.get_logger`. Web: `serverApi`, `accessUnavailable`, `PortalShell`, `SectionUnavailable`, `plural`, the
`SchoolScorecardGrid` form/pager pattern, `.kpi-*`/`.badge`/`.table-scroll`/`.pager`/`.skeleton-line` CSS.

## 5. Stage rules

### 5.1 Funnel (tracked) — per student, cumulative (D3)

| Key | Label | A student has reached it when any of their bridged applications… |
|---|---|---|
| `pathway` | Global education pathway | exists |
| `profile_evaluation` | Profile evaluation | status at or after `eligibility_evaluation` |
| `shortlisted` | University shortlisted | status at or after `university_selection` |
| `offer` | Offer received | status in `OFFER_ONWARD_STATUSES`, or has an offer letter (evaluated as `IS NOT NULL` in SQL) |
| `visa` | Visa | has a `VisaCase` (D10) |
| `admitted` | Admitted | status `enrolled` |

Statuses outside `OVERSEAS_APPLICATION_STAGES` (e.g. legacy/withdrawn/rejected) count toward `pathway` only.
`shortlisted`, `visa` and `admitted` equal the dashboard KPI tiles for the same scope.

### 5.2 Not tracked (D1) — fixed list, in this order

| Key | Label | Note |
|---|---|---|
| `applications_started` | Applications started | Application status does not distinguish started from submitted. |
| `applications_submitted` | Applications submitted | Application status does not distinguish started from submitted. |
| `deposit` | Deposit | No deposit stage is recorded. |
| `scholarship` | Scholarships | No school-student scholarship link exists yet. |
| `top_100` | Top 100 universities | Universities carry no ranking yet. |
| `alumni` | Alumni | Alumni tracking is not built yet. |

### 5.3 Per-student row

- `furthest_stage` / `furthest_stage_label`: the last key in §5.1 order the student has reached (always ≥ `pathway`).
- `visa_stage_label`: across the student's visa cases, the most advanced by `VISA_CASE_STAGES` order, labelled
  `checklist`→"Checklist", `documentation`→"Documentation", `interview_prep`→"Interview preparation",
  `tracking`→"Tracking", `decision`→"Decision"; a value outside the list → "In progress"; no case → `null`.
- `application_count`: integer.
- `grade`: `grade_key(grade_level, grade_or_class)` (`"8"`–`"12"`, `"other"`, `"unspecified"`).
- Only bridged students are listed (a student with no bridged application never appears, D2/backlog edge case).
- Order: `full_name`, then `id` (stable paging).

## 6. Endpoint

`GET /api/v1/school/global-education/pipeline`

| Param | Type | Rule |
|---|---|---|
| `grade` | int, optional | 8–12 (`Query(None, ge=8, le=12)`) |
| `limit` | int | 1–100, default 25 |
| `offset` | int | 0–`MAX_OFFSET` |

**Response 200** (`GlobalEducationPipelineOut`, snake_case like every school endpoint):

```json
{
  "grade": 12,
  "students_in_scope": 150,
  "bridged_students": 80,
  "funnel": [{"key": "pathway", "label": "Global education pathway", "count": 80}],
  "not_tracked": [{"key": "scholarship", "label": "Scholarships", "note": "No school-student scholarship link exists yet."}],
  "students": {
    "items": [{"school_student_id": "…", "full_name": "…", "student_code": "…", "grade": "12",
               "furthest_stage": "offer", "furthest_stage_label": "Offer received",
               "visa_stage_label": null, "application_count": 2}],
    "total": 80, "limit": 25, "offset": 0
  }
}
```

`students_in_scope` = roster size after the grade filter; `bridged_students` = `students.total` = `funnel[pathway].count`.
An offset past the end returns `items: []` with the real `total`.

**Errors** (FastAPI `{"detail": …}`): 401 no/expired session; 403 wrong role or account not linked to a school (raised in
the dependency, before any 422); 422 invalid query. No 404 (the resource is always "my school").

### 6.1 Queries (all parameterised SQLAlchemy; no ORM rows of overseas models)

1. Roster: `select(SchoolStudent.id, full_name, student_code, grade_level, grade_or_class).where(school_id == own)
   .order_by(full_name, id)`; grade filter in Python via `grade_key` (ENH-016 scorecard-grid precedent).
2. Applications: `select(OverseasApplication.school_student_id, OverseasApplication.status,
   OverseasApplication.offer_letter_url.is_not(None)).where(school_student_id.in_(students_in([school_id])))`.
3. Visa: `select(OverseasApplication.school_student_id, VisaCase.status).join(VisaCase, …)
   .where(school_student_id.in_(students_in([school_id])))`.

## 7. Frontend (`SCR-SCH-038`)

- **Pages** (server components, one per role, identical data): `Promise.all([serverApi("/api/v1/auth/me"),
  serverApi(pipelineUrl)])`. If `auth/me` fails or the pipeline returns 401/403 → `return accessUnavailable(e)`. Any other
  pipeline failure → `PortalShell` + `<h1>` + `SectionUnavailable title="Global education pipeline"` (nav stays usable).
  `searchParams` `grade`/`offset` are forwarded only when they are digit strings (anything else is dropped, so a bad URL
  shows the unfiltered page instead of a 422 error card).
- **`loading.tsx`**: skeleton lines, `aria-busy="true"`, following `coordinator/feedback/loading.tsx`.
- **`GlobalEducationFunnel`** (`{data}`): `<h2>`, summary "N students[ in Grade G] · M on the global education pathway",
  boundary note "High-level stage only. Application details are handled by EduSphere's application team.", an `<ol>` of
  tracked stages (label, count as text, decorative `aria-hidden` bar sized count ÷ bridged), and a "Not tracked yet" group
  reusing `.kpi-tile`/`.badge`/`.kpi-note`.
- **`GlobalEducationStudentTable`** (`{page, grade, basePath}`): GET form with labelled native `<select>` (All grades,
  8–12) + Show button; `.table-scroll` table with `<caption>` and row headers (Student, Code, Grade, Furthest stage, Visa,
  Applications); `.pager` with the QA-016-06 past-end rule. Names are plain text (no new links).
- **Empty states:** no bridged students — "No students from this school are on the global education pathway yet.
  Students appear here once an EduSphere counselor links their application."; grade filter — "No students in this grade are
  on the global education pathway."; past end — "This page is past the end of the list."
- **Nav:** `"global-education"` appended after `"reports"` in `SCHOOL_NAV.coordinator` and `SCHOOL_NAV.principal`.
- **Responsive/a11y:** single-column funnel, fluid bars, horizontal table scroll with sticky first column, h1→h2→h3 order,
  counts never conveyed by colour/length alone, native controls for keyboard support, no client JS.

## 8. Transactions, concurrency, data

Read-only: nothing is added to the session and nothing is committed, so a failed request leaves no partial state and
needs no rollback. Funnel and list derive from the same three result sets in one request, so they are mutually
consistent; a concurrent status change is reflected on the next load. No locking or idempotency concerns. No schema or
data change.

## 9. Operational logging

One `logger.info("school_global_education_view", extra={"extra_fields": {actor_id, role, school_id, grade, bridged,
returned}})` per successful request. Never names, codes, statuses or universities.

## 10. Acceptance criteria (local IDs)

| ID | Criterion |
|---|---|
| AC01 | Coordinator and principal get 200 with the §6 shape for their own school. |
| AC02 | Teacher, parent, academic_team, career_counselor, psychometric_team, it_admin, overseas_admin, super_admin, counselor, overseas_student get 403; unauthenticated gets 401. |
| AC03 | A coordinator/principal account without a linked school gets 403. |
| AC04 | Only the caller's own school's students are counted/listed; another school's bridged students never appear. |
| AC05 | A student with no bridged application is excluded from the list and from `bridged_students`, but counted in `students_in_scope`. |
| AC06 | Funnel counts follow §5.1 cumulatively per student; a student with several applications counts once per stage. |
| AC07 | `shortlisted`, `visa`, `admitted` equal the `/school/dashboard` KPI values for the same school (no grade filter). |
| AC08 | `not_tracked` lists exactly the §5.2 keys, in order, each with a note; none appears in `funnel`. |
| AC09 | Per-student `furthest_stage`, `visa_stage_label`, `application_count` follow §5.3. |
| AC10 | Every object in the response has exactly the allowlisted keys (exact key-set assertions at every level). |
| AC11 | Seeded sensitive values (application notes, next_action, application_reference, offer_letter_url, university name, course, counselor name, visa tracking_reference, document filenames) never appear in the raw response body. |
| AC12 | `grade` filters both funnel and list using `grade_key` (label fallback included); invalid `grade`/`limit`/`offset` → 422; a wrong role with invalid params still gets 403. |
| AC13 | Paging: stable name/id order; `total` is the bridged count; past-end offset → empty items with real total. |
| AC14 | The endpoint writes nothing (no AuditLog or other row added) and emits one `school_global_education_view` log line without names. |
| AC15 | Existing contracts unchanged: dashboard, overview, timeline, 360, scorecards, cross-school, entitlements tests all pass untouched. |
| AC16 | UI: coordinator and principal nav show "Global Education"; page renders funnel, not-tracked group and student table. |
| AC17 | UI states: loading skeleton; empty, empty-grade and past-end messages; section error keeps the shell; 401/403 → access card. |
| AC18 | UI: grade form and pager work without client JS, keyboard-operable, labelled; table has caption and row headers; usable at 320/768/1024/1440 px. |

## 11. Security review (`security-and-hardening`, 2026-09-29)

| Concern | Control |
|---|---|
| AuthN | Unchanged `get_current_user` (httpOnly, sameSite=lax cookie). |
| AuthZ / escalation | `_require_school_reader` dependency (coordinator/principal) + `_own_school_id`; no writes; no new roles. |
| IDOR | School derived from the session; no id parameter; two-school tests. |
| Disclosure | Column-level selects; offer letter reduced to a boolean in SQL; allowlisted response models; key-set and planted-value tests; minors' fields never selected. |
| Injection | Bounded `Query` params; SQLAlchemy expressions only. |
| XSS | React escaping; no `dangerouslySetInnerHTML`. |
| CSRF | GET only; no state change. |
| Logs | ids and counts only. |
| Rate limiting | None in the API generally; endpoint is single-school and row-capped. Residual risk, out of scope. |
| Audit | Log line only (D9). |

## 12. Regression risks

| Risk | Mitigation |
|---|---|
| Editing shared constants/helpers in `schools.py`/`school_analytics.py` | Import only; zero edits to those files. |
| Import cycle (`school_analytics` imports `schools`) | New module imports both at module level; neither imports it. |
| Nav change breaks nav/PortalShell tests | Additive array entries; run nav/PortalShell tests. |
| Funnel disagrees with KPI tiles | AC07 test. |
| `require_school_entitlement` committing on a read path | Not called (D8). |

## 13. Test plan (written before code)

- **API** `apps/api/tests/test_enh_017_global_education_pipeline.py` (helpers from `enh016_helpers.py`): AC01–AC14.
- **API regression**: `test_sch_010_overseas_bridge.py`, `test_enh_016_*`, `test_enh_013_360_view.py`,
  `test_sch_reports.py`, `test_enh_022_tier_enforcement.py`, then the full API suite.
- **Vitest** `apps/web/tests/components/GlobalEducationPipeline.test.tsx` (funnel, not-tracked, table, empty/past-end,
  grade form/pager hrefs, a11y roles) and page tests for error/section-unavailable paths; navigation test for the new entry.
- **Playwright** `apps/web/tests/e2e/enh-017-global-education.spec.ts`: coordinator sees a bridged student's stage (bridge
  created via the overseas-admin API as in `sch-010`), principal sees the page, teacher is refused, grade filter, and the
  network response contains no planted sensitive value.
- **Browser QA** (separate step, after implementation): `docs/quality/ENH-017_BROWSER_QA_*.md`, then independent review.

## 14. Documentation deliverables

`PRODUCT_DECISION_REGISTER.md` (DEC-SCOPE-036), `API_CONTRACT.md` addendum, `RBAC_MATRIX.md` §2.12 row,
`SECURITY_CONTROLS.md` §6A row, `THREAT_MODEL.md` entry, `SCREEN_CATALOG.md` + `screen_catalog.json` (SCR-SCH-038),
`ROLE_NAVIGATION.md`, `FEATURE_ACCEPTANCE_CRITERIA.md` addendum, `docs/quality/RTM.md` addendum,
`ENHANCEMENT_BACKLOG.md` (L120 status, §16–§20 rows, ENH-017 entry "delivered scope / follow-ups").

**Follow-ups (not ENH-017):** scholarship↔school-student link; university ranking/Top-100; alumni definition +
`alumni_network` usage + Platinum read gate; visa outcomes; started/submitted/deposit statuses;
`school_partnership_manager` (item 75).
