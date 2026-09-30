# ENH-015 — Reports & Downloads (slice 1) — Design

**Status:** Design approved in-session 2026-09-29 (sections 1–6 presented; user instructed "proceed"). Implementation in
progress on `feature/enh-015-student-school-reports`. **Not complete** until browser validation and the independent Codex
review are done.
**Backlog:** `docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-015 (`DERIVED_BLUEPRINT`).
**Source:** `functionalities/edusphere_markdown/School CRM.md` (EVID-014) §30 (lines 922–964) and the permission table
(line 1774, "Reports | Full | Limited | Child | Own | Full/Assigned" — `DERIVED_BLUEPRINT`).
**Decision record:** `DEC-SCOPE-037` (provisional number — renumber on merge if taken).
**Screens:** no new screen; a download control is added to existing screens (§7).

## 1. Problem (audit result)

The Graphify-led audit (2026-09-29) found:

- `GET /school/reports` (`schools.py`) and the pages `/school/{coordinator,principal}/reports` already exist, but only as
  on-screen JSON views (the SCH dashboard payload plus the ENH-016 analytics). **Nothing in the School domain produces a
  downloadable file.**
- Every figure §30's Management Report example asks for already exists as an ENH-016 indicator set
  (`school_analytics.student_indicators`): career guidance, psychometric, counselling, skills programs, global education.
- The per-student "Student Progress Report" data already exists as the SCH-007 overview (`_overview_payload`), which is
  already scope-checked for Parent / Coordinator / Principal by `_load_readable_student`.
- `reportlab` is already a dependency (certificates, invoices). No PDF library decision is needed.
- `/files/download` presigns **any** storage key for any authenticated user, and `/local-files` is an unauthenticated
  static mount. A stored report would be reachable outside its scope — so reports must never be stored.

## 2. Goals and non-goals

**Goals**
- G1. A Coordinator or Principal downloads a **School Summary** PDF for their own school: the §30 Management Report
  figures plus the §29 grade-wise comparison.
- G2. A Parent downloads a **Student Progress Report** PDF for their own linked child; a Coordinator or Principal for any
  student of their own school.
- G3. A PDF never shows more than the same reader already sees on screen.

**Non-goals** (explicit — do not implement under this slice)
- The other §30 report types (Individual Career, Psychometric, Counselling, Digital Portfolio, and the 11 School Reports
  other than grade-wise) — later slices, each with its own approval.
- A per-academic-year "Annual" report (no source record carries an academic year except results, as free text).
- Scholarship figures (no school-student link — ENH-016/017 "not tracked").
- CSV output, background generation, stored report files, a report-log table, any migration.
- Teacher, Academic Team, Career Counselor, Psychometric Team, Overseas Admin, Super Admin access (teacher "Limited" is
  undefined — `NEEDS_CONFIRMATION`).
- A student login / `school_student` role (does not exist, DEC-ROLE-004).
- Parent access to the psychometric report *file* (`report_url`) — Client Question #20 stays open.
- Tier gating; rate limiting; changes to `SCHOOL_NAV` / `PORTAL_NAV`.
- Non-Latin (e.g. Devanagari) glyphs in the PDF — known limitation, see §12.

## 3. Decisions confirmed in-session (2026-09-29) — `DEC-SCOPE-037` (provisional)

| ID | Decision |
|---|---|
| D1 | **Slice 1 = acceptance-criteria driven:** one school-wide report (School Summary) and one per-student report (Student Progress Report). |
| D2 | **Format: PDF only**, built with the existing `reportlab` (Platypus, part of the same package). No new dependency. |
| D3 | **Generation: synchronous, in memory**, streamed back. Nothing stored, no Celery job, no table, no migration. |
| D4 | **School Summary audience:** `school_coordinator`, `school_principal`, own school only (reuses `_require_school_reader`). |
| D5 | **Progress Report audience:** `school_parent` (linked children only), `school_coordinator`, `school_principal` (own institution). Every other role 403 — checked before the student is loaded. |
| D6 | **Progress Report content = the SCH-007 overview** (`_overview_payload`) exactly as that reader receives it today: includes the ENH-027 psychometric result fields (already parent-visible), published results only, **never `report_url`**. |
| D7 | **Period:** all records to date, headed "As of <date> (India time)"; the active academic year label is context only. |
| D8 | **Tier:** no gate (consistent with ENH-016 reads and `/school/reports`). |
| D9 | **Audit:** Progress Report download → one `AuditLog` row, committed **before** any byte is returned (fail closed). School Summary (aggregate counts only) → one structured log line, no AuditLog row (ENH-016 D15). |
| D10 | **Placement:** a download button on the existing coordinator/principal Reports pages, the parent child page and the coordinator/principal student pages. No nav changes. |

## 4. Architecture

### 4.1 Module layout

- **New** `apps/api/app/reporting/pdf.py` — pure rendering: `render_school_summary(data) -> bytes`,
  `render_progress_report(data) -> bytes`. No database, no I/O. All user text passes through one escape function before it
  reaches a `Paragraph` (reportlab parses `<`, `>`, `&` as markup).
- **New** `apps/api/app/api/school_reports.py` — `APIRouter(prefix="/school", tags=["school-reports"])`, two routes, one
  role dependency, one data builder for the summary.
- **Edit (refactor, behaviour-preserving)** `apps/api/app/api/school_analytics.py` — extract the body of
  `grade_performance` into a pure `grade_table(roster, indicators) -> GradePerformanceOut` so the report reuses it with the
  same indicator sets instead of duplicating the grade loop. The route keeps its signature, response and log line; guarded
  by the existing `test_enh_016_school_analytics.py`.
- **Edit** `apps/api/app/main.py` — register the router (additive).

### 4.2 Reused, imported read-only (never edited)

`schools._load_readable_student`, `schools._own_school_id`, `schools._overview_payload`, `schools._today_ist`,
`school_feedback._require_school_reader`, `school_analytics.{students_in, student_indicators, _roster, GRADE_METRICS}`.
Import direction: `school_reports` → those modules; nothing imports `school_reports` (no cycle).

## 5. Report content

### 5.1 School Summary (`school-report.pdf`)

1. Title "School Summary Report", school name, "As of <DD Mon YYYY> (India time)", "Academic year: <label>" (or "No active
   academic year").
2. **Management summary** (§30 "Annual School Career Development Report" figures) — distinct students:
   Total Students (`len(roster)`), Career Guidance Completed (`guidance`), Psychometric Tests Completed (`psych_completed`),
   Individual Counselling Completed (`counselling`), Students in Skills Programs (`skills_enrolled`), Students in Global
   Education Pathway (`global` — any overseas application). **Revised 2026-09-30 (browser QA):** labels are the dashboard
   KPI tiles' own wording for the same counts, so they are not confused with the Reports panel's broader "Career guidance"
   (students with any career record).
3. **Grade-wise comparison** — `grade_table(...)`: one row per `GRADE_METRICS` metric, one column per grade in
   `_ordered_grades` order, each cell "count (pct%)" or "count (—)" when the grade has no students; a "Students" row first.
   Metrics that are ENH-016 D5 estimates are marked "*" with their definition listed under the table.
4. Footnote: "Counts are distinct students. Academic results count only when published." Empty roster → the sections
   still render, with "No students on the roster yet." under the title and no grade table.

### 5.2 Student Progress Report (`progress-report.pdf`)

Rendered from the overview dict (D6), in the overview's own order:
student (name, student code, grade/class, school, assigned teacher) · career guidance (status + sessions) · counselling
(status + notes) · recommendations (structured lists) · psychometric (status + each assessment's type, status, date and
the ENH-027 result fields that are set) · academic results (published: subject/assessment, marks, percentage, year) ·
activities attended · test prep · foreign language · global education (university, status, visa status) · skills.
Every empty section prints "Not started" / "No records yet". Nothing outside the overview dict is read. `report_url` is
not in the overview dict and is therefore never rendered.

## 6. Endpoints

### 6.1 `GET /api/v1/school/reports/school-summary`

- Dependency `_require_school_reader` (403 "School Coordinator or Principal role required"; 403 "This account is not
  linked to a school"). School id from `_own_school_id(user)` — never from the request.
- No query parameters, no body.
- 200 `application/pdf`, headers §6.3, filename `school-report.pdf`.

### 6.2 `GET /api/v1/school/students/{student_id}/progress-report`

- Dependency `_require_report_reader`: role ∈ {school_parent, school_coordinator, school_principal} else 403
  "Parent, School Coordinator or Principal role required" — runs before path validation (403 before 422, ENH-016/017
  precedent).
- `_load_readable_student(db, user, student_id)` — **unchanged semantics, identical to `/students/{id}/overview`**:
  404 "Student not found" for an unknown id; 403 for an existing student outside scope ("This student is not linked to
  your account" / "This student is at a different institution"). (The in-chat design said "uniform 404"; the existing
  loader returns 403, and matching `/overview` exactly adds no new information to a reader who can already call it.)
- 200 `application/pdf`, headers §6.3, filename `progress-report.pdf`.

### 6.3 Shared response rules

| Status | When | Body |
|---|---|---|
| 200 | success | PDF bytes; `Content-Disposition: attachment; filename="<fixed>.pdf"`, `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; sandbox` (the ENH-021 certificate `HEADERS`) |
| 401 | no/expired session | existing `get_current_user` |
| 403 | role / scope (see above) | `{"detail": ...}` |
| 404 | unknown student | `{"detail": "Student not found"}` |
| 422 | malformed UUID (allowed role) | FastAPI default |
| 500 | render failure | `{"detail": "Could not generate the report; please try again"}` |
| 500 | audit write/commit failure | platform default 500 (the exception propagates, as every audited write in the codebase does — `test_sec_001` precedent); no PDF bytes |

OpenAPI: `response_class=Response`, `responses={200: {"content": {"application/pdf": {}}, "description": ...}}`.
Filenames never contain a student or school name (no PII in headers, no header injection).

## 7. Frontend

- **New** `apps/web/components/ReportDownloadButton.tsx` (client): props `url`, `label`, `filename`. `fetch(url)` → if
  `ok` and `content-type` starts with `application/pdf`: blob → object URL → temporary `<a download>` click → revoke.
  Reuses `.btn`, `.actions`, `FormMessage`, `detailMessage`.
- **States:** idle (a real `<button>`); busy (disabled, `aria-busy="true"`, label "Preparing PDF…"); success
  (FormMessage status "Report downloaded."); errors — 401 "Your session has expired. Sign in again.", 403/404 the server
  `detail`, 5xx / network / non-PDF "Something went wrong on our side. Please try again." — button re-enabled for retry.
  No empty state (the PDF always renders; emptiness is described inside it).
- **Placement:**
  - `app/school/{coordinator,principal}/reports/page.tsx` — a "Download reports" card (`<h2>`) before the existing panel,
    one button "Download school report (PDF)". Its wording avoids the exact texts `sch-reports.spec.ts` matches.
  - `app/school/parent/children/[id]/page.tsx` — a third button in the existing action row: "Download progress report (PDF)".
  - `app/school/{coordinator,principal}/students/[id]/page.tsx` — the same button in the page's action area.
- Responsive: the action rows are wrapping flex rows; messages sit under their button. Keyboard: native button, focus
  stays on it; messages are live regions.

## 8. Transactions, concurrency, data

- School Summary: read-only; no commit; no locks.
- Progress Report: read → render → `db.add(AuditLog)` → `commit` → return bytes. Render failure → 500, nothing written.
  Commit failure → exception, session rolled back by `get_db`, no bytes (fail closed, ENH-021 S13).
- Reads run at PostgreSQL READ COMMITTED; a concurrent write may land between two of the overview's queries — the same
  accepted behaviour as the on-screen overview. No locking (would block writers for a read).
- Double request (double click): the button is disabled while busy; if two requests still arrive, two audit rows — correct.
- No schema change; no data written other than the audit row.

## 9. Operational logging

- `school_report_generated` — `{actor_id, role, report: "school_summary"|"progress_report", school_id | school_student_id,
  student_count (summary), bytes, ms}`. ids and counts only.
- `school_report_failed` — `{actor_id, report, error_type}` via `logger.error` (the exception *type* only — never its
  message or traceback text, which could contain student data).

## 10. Acceptance criteria (local IDs)

- **ENH-015-AC01** Coordinator downloads the School Summary for their own school; its figures equal `student_indicators`
  over that school and the grade table equals `GET /school/analytics/grade-performance`.
- **ENH-015-AC02** Principal can download it; teacher, parent, academic_team, career_counselor, psychometric_team,
  overseas_admin, super_admin → 403; a school account with no school → 403; no session → 401.
- **ENH-015-AC03** School A's summary never includes school B's students or records.
- **ENH-015-AC04** Parent downloads the Progress Report for a linked child; an unlinked child (same or other school) → 403;
  coordinator/principal for an own-school student → 200, other school → 403; unknown id → 404; teacher and service roles
  → 403 (before 422 for a malformed id).
- **ENH-015-AC05** The Progress Report contains the overview's fields for that student only; Draft/Verified results never
  appear; `report_url` never appears.
- **ENH-015-AC06** Each Progress Report download writes exactly one AuditLog row (`school.progress_report_download`,
  entity `school_student`, metadata `{role}` only) before the response; if the commit fails, no PDF is returned.
- **ENH-015-AC07** Both responses carry `application/pdf`, the fixed attachment filename, `private, no-store`, `nosniff`
  and the sandbox CSP.
- **ENH-015-AC08** Markup-like stored text (`<b>`, `&`, `<font>`, unbalanced `<`) is rendered literally and never breaks
  generation.
- **ENH-015-AC09** The School Summary issues a fixed number of queries independent of the student count.
- **ENH-015-AC10** The download button shows busy, success and each error state; works by keyboard; usable at 320 px.
- **ENH-015-AC11** `/school/reports`, `/school/dashboard`, `/school/analytics/grade-performance`,
  `/students/{id}/overview`, `SCHOOL_NAV`, `PORTAL_NAV` unchanged; their existing tests pass unmodified.
- **ENH-015-AC12** Logs for both reports contain ids and counts only — no student names or record text.

## 11. Security review (`security-and-hardening`, 2026-09-29)

| Concern | Control |
|---|---|
| Authentication | Existing cookie session (`get_current_user`). |
| Authorization / escalation | Role allowlist dependencies; `super_admin`'s `"*"` permission is not consulted (school routes check roles inline). |
| IDOR | School from the session profile; student through `_load_readable_student`; tests for other-school and unlinked-child ids. |
| Input validation | UUID path parameter only. |
| XSS / content injection | Output is a PDF attachment with `nosniff` + sandbox CSP; all text escaped before `Paragraph`; UI renders only `detail` strings via React escaping. |
| CSRF | GET + `SameSite=Lax` cookie + CORS allowlist: a cross-site link can at most make a victim download their own report (one extra audit row). Accepted. |
| SQL injection | SQLAlchemy bound parameters only. |
| Tokens / secrets | Unchanged; nothing sensitive in URLs or filenames. |
| Sensitive logs | §9 — ids/counts; exception type only. Audit metadata `{role}` only. |
| Rate limiting | None platform-wide; ENH-016 D16 precedent — authenticated, bounded work. Accepted risk. |
| Storage exposure | Nothing is written to storage, so `/files/download` and `/local-files` cannot reach a report. |
| Caching | `private, no-store`. |
| Resource size | Progress Report grows with the student's records (the overview is already unbounded on screen). Accepted for slice 1. |

## 12. Regression risks

- `sch-reports.spec.ts` exact-text locators — new wording avoids "Students by grade", "Career guidance" (exact),
  "Activities & attendance".
- `grade_performance` refactor — covered by `test_enh_016_school_analytics.py` / `test_enh_016_scope.py`, run before and
  after.
- Scope helpers, `student_indicators`, `_overview_payload` are called, not edited.
- No migration → `alembic check` unaffected. No nav change → `skills.test.ts`, `AdminSchoolAnalyticsPage.test.tsx` safe.
- Known limitation: built-in PDF fonts (Helvetica) cannot draw non-Latin scripts; such characters render as boxes.
  Fix = embed a TTF font asset (a later decision).

## 13. Test plan (written before code)

Backend (`apps/api/tests/`):
- `test_enh_015_pdf.py` — renderer unit tests: valid PDF, text present, markup escaped, empty sections, grade table.
- `test_enh_015_school_summary.py` — role matrix, own-school isolation, figures = indicators, grade table = endpoint,
  empty school, headers, fixed query count, log line ids-only.
- `test_enh_015_progress_report.py` — role matrix (403 before 422), parent linked/unlinked, other-school 403, unknown 404,
  content = overview (published only, no `report_url`), audit row, audit-failure → no PDF, headers, logs.
- Existing: `test_enh_016_*`, `test_sch_reports.py`, `test_sch_007_parent_portal.py`, `test_sch_001_*`,
  `test_uuid_contracts.py`.

Frontend:
- `tests/components/ReportDownloadButton.test.tsx` — success download, busy state, 401/403/5xx/network/non-PDF messages.
- Page tests: button present on the reports/child/student pages.
- `tests/e2e/enh-015-reports-downloads.spec.ts` — coordinator downloads school report; parent downloads own child's
  report; teacher has no access.

## 14. Documentation deliverables

`API_CONTRACT` addendum, `RBAC_MATRIX` §2.12, `SECURITY_CONTROLS` §6A, `THREAT_MODEL`, `SCREEN_CATALOG` note,
`FEATURE_ACCEPTANCE_CRITERIA` addendum (ENH-015-AC01..AC12), RTM row, backlog status, `DEC-SCOPE-037` entry. Browser QA
record and independent review follow implementation.
