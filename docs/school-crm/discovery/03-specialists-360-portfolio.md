# School CRM — Specialist portals discovery (Academic Team, Career Counselor, Psychometric Team, Student 360°, Digital Portfolio)

> **Evidence appendix** for `docs/school-crm/documentation-analysis.md` — raw read-only source discovery (master planning session S1, 2026-10-05, code `main` @ `ce1f07c2`). Field-level detail for module sessions. Not browser-verified; where this file and the browser disagree, the browser wins and this file is annotated, not silently trusted.

Source: repo `edusphere`, code = main ce1f07c2 (read-only discovery, branch docs/school-crm-user-guide).
Paths: `web/` = `apps/web/`, `api/` = `apps/api/app/`. All API paths are mounted under `/api/v1` (`main.py:79` router loop; every module here has `prefix="/school"` except admin `/overseas-admin`).
Every endpoint below uses `Depends(get_current_user)` (cookie session) unless noted; role checks are inline `user.role` comparisons (no `rbac.py` permission check — `core/rbac.py:47-49` only declares `school:<role>:portfolio` permission strings, not used by these routes).

---

## 0. Cross-cutting facts (apply to all three portals)

### 0.1 Roles, sign-in, landing
- Roles: `academic_team`, `career_counselor`, `psychometric_team` = `SERVICE_DELIVERY_ROLES` (`api/api/schools.py:95`).
- Accounts are division `overseas` (`api/api/admin.py:1688-1696`), created only by Overseas Admin / Super Admin (see 0.3). Welcome link emailed (`deliver_welcome_link`, admin.py:1708); password is never set by admin (`_reject_supplied_password`, admin.py:1672).
- Landing after login: `ROLE_DASHBOARD_PATH` (`web/lib/navigation.ts:36-38`):
  - academic_team → `/school/academic-team/dashboard`
  - career_counselor → `/school/career-counselor/dashboard`
  - psychometric_team → `/school/psychometric-team/dashboard`
- Sign-in page: VERIFICATION REQUIRED — `AccessUnavailable` links signed-out users to `/overseas/login` (`web/components/AccessUnavailable.tsx:40,45`), consistent with division `overseas`; confirm in browser.
- **No middleware protection for `/school/*`** — `web/middleware.ts:6,18` matcher covers only `/it`, `/overseas`, `/admin`, `/bdm`. A signed-out visitor is not redirected; the page renders the "Access unavailable" card with the API's 401 text (e.g. "Not authenticated", `api/api/deps.py:43`) and a "Return to login" link (AccessUnavailable.tsx:29).
- **No frontend role guard** on any specialist page except Funding (`web/app/school/career-counselor/funding/page.tsx:20`, message "Career Counselor role required"). All other pages rely on the API refusing (403) → "Access unavailable" card with the API message + "Go to your dashboard" + Sign out (AccessUnavailable.tsx:19-35).

### 0.2 Sidebar (PortalShell) — `web/lib/navigation.ts:77-80`
| Portal | Sidebar items (label → href) |
|---|---|
| Academic Team | Dashboard → `/school/academic-team/dashboard` (only item) |
| Career Counselor | Dashboard → `/school/career-counselor/dashboard`; Skills → `/school/career-counselor/skills`; Funding → `/school/career-counselor/funding` |
| Psychometric Team | Dashboard → `/school/psychometric-team/dashboard` (only item) |

Sidebar chrome (all portals, `web/components/PortalShell.tsx:74`): EduSphere logo, role pill (role label + user full name), nav, footer buttons "Change password" (`/account/password`), "My profile" (`/account/profile`), "Sign out". Top bar: "EduSphere Portal" + user name; below 980 px a mobile menu (PortalMobileNav) lists "Change password", "My profile" + nav items.

### 0.3 How a specialist gets a "portfolio" of schools
- Portfolio = rows in `SchoolStaffAssignment` (user_id, school_id) read by `_portfolio_school_ids` (`api/api/schools.py:2034-2036`).
- Created by Overseas Admin / Super Admin:
  - `POST /api/v1/overseas-admin/school-staff` (admin.py:1666) — body `role`, `full_name`, `email`, `school_ids[]`; errors: 403 "Overseas Admin role required"; 422 "role must be one of ['academic_team', 'career_counselor', 'psychometric_team']"; 422 "email and full_name are required"; 409 "Email already exists"; 422 "One or more school_ids do not exist". UI: `web/components/AdminSchoolStaffPanel.tsx` shown on `/overseas/admin/school-staff` (WorkflowPanel.tsx:470) — fields "Role", "Full name", "Email", "School portfolio" (multi-select with "Select all (N)", "Clear visible", "Clear all"; hint "Hold Ctrl (Windows) or Cmd (Mac) to select more than one. A portfolio can be left empty and filled in later, but the account can't act on any student until at least one school is assigned."), button "Create account"/"Creating…".
  - `GET /api/v1/overseas-admin/school-staff` (admin.py:1711) — list with school_ids.
  - `POST /api/v1/overseas-admin/school-staff/{staff_id}/portfolio` (admin.py:1829) — add one school later; errors 404 "Specialized-role staff account not found", 422 "A valid school_id is required", 409 "This school is already in this staff member's portfolio".
- **As-built gap:** no web UI calls the add-to-portfolio endpoint (grep of web/ for `school-staff/` = no hits) → "filled in later" is API-only. No endpoint to REMOVE a school from a portfolio. VERIFICATION REQUIRED with owner for the user guide.
- Out-of-portfolio access: 403 "This student is at a school outside your own portfolio" (`OUTSIDE_PORTFOLIO`, schools.py:2039); unknown student 404 "Student not found".
- Empty portfolio: lists return `[]`; dashboards show "No students in your portfolio yet. Contact your Overseas Admin."
- Shared list: `GET /api/v1/school/portfolio-students` (schools.py:2072) — 403 "Academic Team, Career Counselor, or Psychometric Team role required"; returns id, full_name, school_id, school_name sorted by name. No pagination.

### 0.4 Partnership-tier (entitlement) gating — `require_school_entitlement` (schools.py:1122)
Tiers cumulative bronze < silver < gold < platinum (`TIER_SERVICES`, schools.py:978-1010). 403 messages (schools.py:1075-1091):
- "This school has no active partnership tier."
- "This school's partnership expired on DD Mon YYYY." (India date)
- "This school's {Tier} partnership does not include {Service label} (requires {MinTier} or higher)."
Denials are audited (`school.tier_access_denied`). Work started before a downgrade is "grandfathered" for edits (ENH-023) but never for an expired partnership.

| Feature (write) | Service key / label | Minimum tier |
|---|---|---|
| Academic results (create/verify/publish/bulk) | **none — not gated** (schools.py:2514-2620; school_bulk.py:131 `service_key=None`) | — |
| Psychometric assessment assign/report/results | psychometric_test "Psychometric test" | Bronze |
| Soft Skills batch writes | soft_skills "Soft skills" | Bronze |
| Digital Skills batch writes | web_designing "Digital skills" | Silver |
| Career records (create/update), Career goal (360) | individual_counselling "Individual counselling" | Silver |
| Career preferences card | **not gated** (school_student_profile.py:136-145) | — |
| IELTS / SAT test prep | ielts_coaching / sat_coaching | Gold |
| Foreign language classes | foreign_language_classes | Gold |
| Digital Portfolio entries / personal statement | digital_portfolio_creation "Digital portfolio creation" | Gold |
| Internship entry create / tracking fields / certificate upload & remove | internships "Internships" | Platinum |
| Funding — scholarship | scholarship_assistance "Scholarship assistance" | Gold |
| Funding — education loan, financial assistance, funding guidance | loan_assistance "Loan assistance" | Platinum |
Reads (lists, 360, portfolio GET, funding list) are never gated.

### 0.5 Parent notifications (side effect)
`_notify_student_parents` (schools.py:744-757) creates an in-app `Notification` for every active parent linked to that student and calls `queue_deliveries` (channel(s) e.g. email — VERIFICATION REQUIRED which channels are enabled in the target environment). Action URL always `/school/parent/children/{student_id}`. Triggers are listed per feature below.

---

## 1. ACADEMIC TEAM portal

### 1.1 Academic Team Dashboard — `/school/academic-team/dashboard`
- File: `web/app/school/academic-team/dashboard/page.tsx` (1-56). Sidebar "Dashboard". Role label "Academic Team".
- Data loaded in parallel (page.tsx:33-41): `/auth/me`, `GET /school/academic-team/results`, `GET /school/portfolio-students`, `GET /school/academic-team/test-prep-records`, `GET /school/academic-team/language-records`, `GET /school/academic-team/progress` (optional — failure tolerated).
- Any failing required read (e.g. wrong role → 403 "Academic Team role required") → "Access unavailable" card.
- Page sections in order (page.tsx:47-53):
  1. Portfolio progress card
  2. Results card + "Upload a result" form
  3. "Bulk entry — results (CSV)" (collapsed `<details>`)
  4. Test preparation card + "Start test preparation" form; Foreign language classes card + "Start language classes" form
  5. "Bulk entry — test preparation (CSV)", "Bulk entry — language classes (CSV)"
  6. "Students" directory card
- **ROLE_NAVIGATION mismatch:** `docs/ux/ROLE_NAVIGATION.md:228-230` lists `/school/academic-team` (bare), `/results/new`, `/results/[id]`. None exist (`app/school/academic-team/` contains only `dashboard/` and `students/`). Result entry, verify and publish are all folded into the dashboard Results card. No "status history" screen exists (history rows `SchoolResultStatusHistory` are written, schools.py:2540/2596, but no endpoint/UI reads them).

#### 1.1.a Portfolio progress card — `web/components/SchoolAcademicProgressPanel.tsx`
- Heading "Portfolio progress". Table columns: Student | School | Results | Avg %. Avg shows "No results yet" when none, else "NN%".
- Empty: "No students in your portfolio yet. Contact your Overseas Admin." Failure: "Portfolio progress is unavailable right now. The rest of your workspace is unaffected."
- No search/filter/sort controls/pagination (server order = student full name asc, schools.py:2646).
- Average counts ALL statuses (draft/verified/published), excludes withdrawn (schools.py:2634-2662).
- Endpoint: `GET /school/academic-team/progress` (schools.py:2634), 403 "Academic Team role required".

#### 1.1.b Results (Draft → Verified → Published) — `web/components/SchoolAcademicResultsPanel.tsx`
- Card "Results". Empty "No results uploaded yet." Table columns: Student | Subject | Marks | Status | Actions. Subject cell = "Subject (Year, Term)" + teacher remarks (muted) underneath. Marks = "obtained/max (pct%)". Status shown as raw lowercase value (`draft` / `verified` / `published`) — as-built.
- No search, filter, sort control, pagination (server order = newest first, schools.py:2630; withdrawn results hidden).
- Actions column (panel.tsx:111-125):
  - draft + you uploaded it → text "Ask another Academic Team member to verify"
  - draft + someone else uploaded → button "Verify"
  - verified + you uploaded → "Ask another Academic Team member to publish"
  - verified + someone else uploaded → button "Publish"
  - published → "-"
  - NOTE: the verifier may also publish (only the uploader is barred) — `_advance_result` checks uploader only (schools.py:2586-2587).
- Success messages: "Result verified." / "Result published." (panel.tsx:81). Errors shown inline (role=status) from server detail.
- Workflow (who can do it):
  | Transition | Who | Endpoint |
  |---|---|---|
  | (none) → Draft | any Academic Team member with student in portfolio | `POST /school/academic-team/results` (schools.py:2514) |
  | edit Draft | only the uploader (API only — **no edit UI**) | `PATCH /school/academic-team/results/{id}` (schools.py:2546) |
  | Draft → Verified | Academic Team member ≠ uploader | `POST .../results/{id}/verify` (schools.py:2609) |
  | Verified → Published | Academic Team member ≠ uploader | `POST .../results/{id}/publish` (schools.py:2615) |
- Server errors (exact): 403 "Academic Team role required"; 422 "school_student_id is required"; 422 "max_marks and marks_obtained must be numbers"; 422 "academic_year, term, and subject are required"; 422 "teacher_remarks must be a string"; 422 "teacher_remarks must be 2000 characters or fewer"; 404 "Result not found"; 403 "Only the Academic Team member who uploaded this result can edit it"; 409 "Only a Draft result can be edited"; 409 "A result must be draft before it can be moved to verified -- no skip-stage transition" (or "...verified before it can be moved to published..."); 403 "A different Academic Team member must perform this step -- you cannot verify or publish your own upload"; 403 OUTSIDE_PORTFOLIO; 404 "Student not found".
- Network failure text: "Could not reach the server. Check your connection and try again." (panel.tsx:15).
- Visibility: School roles (coordinator/principal/teacher/parent) see **Published only** via `GET /school/results` (schools.py:2665-2680).
- Side effects: Publish → parent notification "{Term} {Subject} result published for {Name}" / "{Name}'s {Year} {Term} result for {Subject} is now available." (schools.py:2601-2604). Draft/Verify never notify. Audit `school.result_create/_update/_verified/_published`.

#### 1.1.c "Upload a result" form (SchoolAcademicResultsPanel.tsx:136-175)
| Label | Type | Required | Notes |
|---|---|---|---|
| Student | searchable combobox (SearchableSelect) | yes | invalid → browser message "Choose a student from the list."; no match "No matching students." |
| Academic year | text, placeholder "2026" | yes (HTML required) | DB width 20 |
| Term | text, placeholder "Term 1" | yes | DB width 40 |
| Subject | text | yes | DB width 80 |
| Maximum marks | number step 0.01 | yes | |
| Marks obtained | number step 0.01 | yes | |
| Grade | text, placeholder "Optional" | no | DB width 10 |
| Teacher remarks | textarea, max 2000, placeholder "Optional" | no | hint "Optional, up to 2000 characters. Shown to the school once the result is published." |
- Button "Save as Draft" / "Saving…". Success: "{Subject} result saved as Draft." Form resets.
- Empty portfolio: "No students in your portfolio yet. Contact your Overseas Admin."
- As-built oddities: single-entry API does NOT check marks_obtained ≤ max_marks, non-negative, or max > 0 (schools.py:2522-2531) — bulk CSV does. Single-entry has no duplicate check (bulk rejects duplicates by year+term+subject). Over-length year/term/subject/grade are not length-checked by the API before insert → VERIFICATION REQUIRED (probably 500 "Something went wrong.").

#### 1.1.d Bulk entry (CSV) — `web/components/SchoolBulkEntryPanel.tsx`, `web/lib/bulkEntry.ts`, `api/api/school_bulk.py`
Three panels on Academic dashboard (results, test preparation, language classes) + one on Psychometric dashboard (assessments). Each is a collapsed `<details>` card titled:
- "Bulk entry — results (CSV)" / "Bulk entry — test preparation (CSV)" / "Bulk entry — language classes (CSV)" / "Bulk entry — assessments (CSV)".
Steps inside:
1. "1. Download the template" — "One row per student in your portfolio. Fill in only the students you are entering; rows you leave blank are skipped." Button "Download the pre-filled template (.csv)" + "Column reference" table (Column | Required | Format | Example).
2. "2. Upload the filled-in file" — file input label "Filled-in {noun} file" (accept .csv), help "CSV, up to 1 MB and 500 filled-in rows.", button "Upload {noun}" / "Uploading…".
- Client error: "Choose a filled-in CSV file first."; network: "The connection dropped. Upload again — the same file won't be added twice."
- Result: heading "Upload result"; "{accepted} of {total} row(s) added[, N rejected]. Rows that succeeded are kept."; table Row | Student ID | Result (Added/Rejected) | Detail.
- No students: "No students in your portfolio yet. Bulk entry becomes available once a school is assigned to you."
- Columns (lib/bulkEntry.ts): student_code (required, pre-filled 8-char Student ID), student_name & school_name (reference only), then:
  - results: academic_year* (≤20), term* (≤40), subject* (≤80), max_marks* (>0, ≤9999.99), marks_obtained* (0..max_marks), grade (≤10), teacher_remarks (≤2000)
  - test prep: test_type* (`ielts` or `sat`), target_score (≤20)
  - language: language* (≤60), level (≤30)
  - assessments: assessment_type* (≤120), report_url (http/https; marks completed), test_date, strengths, interest_areas, personality_indicators, recommended_careers, recommended_stream (lists "Items separated by ; (up to 20)"), counsellor_remarks (≤4000), parent_discussion_on, parent_discussion_notes (≤2000), follow_up_on (dates YYYY-MM-DD)
- Server file errors (school_bulk.py:52-56, 285-339): 422 "Idempotency-Key header is required"; 413 "The file is larger than 1 MB"; 422 "The file must be a UTF-8 CSV"; 422 "Missing required column: {col}"; 422 "The file has no filled-in rows"; 422 "The file has more than 500 filled-in rows"; 422 "Idempotency-Key was already used for a different file"; 409 "This upload is still being processed; retry shortly"; 409 "These students are being updated by another request; retry shortly"; 403 role error.
- Row errors: "student_code is required"; "student_code does not match a student"; OUTSIDE_PORTFOLIO; validation text; tier denial text; "this student already has {a result} for the same {academic_year, term and subject}"; "same student and {keys} as row N of this file".
- Endpoints: GET templates `/school/academic-team/results/bulk-template` (574), `/psychometric-team/records/bulk-template` (579), `/academic-team/test-prep-records/bulk-template` (584), `/academic-team/language-records/bulk-template` (589); POST uploads (594, 601, 608, 615), all in `school_bulk.py`. Template file name `{target}-bulk-template.csv`.
- Side effects: results rows → Draft (no notification); psychometric, test prep, language rows → parent notifications after the batch commits (school_bulk.py:177, 218, 256, 535).

#### 1.1.e Test preparation (IELTS/SAT) — `web/components/SchoolTestPrepLanguagePanel.tsx:93-158`
- Card "Test preparation". Empty "No test preparation started yet." Table: Student | Test | Target | Actual | Status | Actions. Status raw (`in_progress`/`completed`). Actions: inline input (aria-label "Actual score for {name}") + "Record score" button; completed → "-". Blank score → click does nothing.
- Form "Start test preparation": Student (combobox, required); Test (select "Select test" / IELTS / SAT, required); Target score (text, placeholder "Optional"). Button "Start preparation"/"Starting…". Success "{IELTS|SAT} preparation started." ; score success "Result recorded."
- Endpoints: `POST /school/academic-team/test-prep-records` (schools.py:2331), `PATCH .../{id}` (2352), `GET` (2379). Errors: 403 "Academic Team role required"; 422 "school_student_id is required"; 422 "test_type must be one of ielts, sat"; 404 "Record not found"; tier 403.
- Recording an actual score sets status completed (schools.py:2364-2367). API also accepts `mock_scores` — no UI.
- Notifications: start → "{TEST} preparation started for {Name}"; completed → "{TEST} result recorded for {Name}".

#### 1.1.f Foreign language classes — SchoolTestPrepLanguagePanel.tsx:160-213
- Card "Foreign language classes". Empty "No language classes started yet." Table: Student | Language | Level | Classes attended | Certification | Actions ("Mark certified" button; certified → "-"). Certification shown raw (`not_started`/`certified`).
- Form "Start language classes": Student (required), Language (text, required), Level (text, placeholder "Optional"). Button "Start classes"/"Starting…". Success "{Language} classes started."; certify success "Marked certified."
- Endpoints: `POST /school/academic-team/language-records` (2408), `PATCH .../{id}` (2429), `GET` (2459). Errors: 422 "language is required"; 422 "certification_status must be one of not_started, in_progress, certified"; 404 "Record not found".
- API accepts classes_attended, assessment_score, in_progress — no UI (Classes attended always 0 from UI).
- Notifications: start → "{Language} classes started for {Name}"; certified → "{Language} certification earned by {Name}".

#### 1.1.g Students directory — `web/components/Student360Directory.tsx`
- Heading "Students" (academic team), list of student names (links to `/school/academic-team/students/{id}`) + school name. Hidden when no students. No search/filter/pagination.

### 1.2 Academic Team student page (editable Digital Portfolio) — `/school/academic-team/students/[id]`
- File `web/app/school/academic-team/students/[id]/page.tsx` (1-36). Reached from dashboard "Students" list.
- Header card: student full name (h1), buttons "Open 360° view" → `/school/academic-team/students/{id}/360`, "Back to dashboard".
- Body: `PortfolioPanel` (see §4.3) — editable (`can_edit` true for academic_team via `WRITE_ROLES`, portfolio.py:53, 78-87).
- Data: `GET /school/students/{id}/portfolio` (portfolio.py:121) using `_load_student_for_reader` (schools.py:2062-2069): service roles → portfolio scope.
- As-built: no frontend role guard; any School role (e.g. coordinator) that can read the student could open this URL and get an "Academic Team"-chromed page with their own permissions. Not harmful (API decides) but odd.

### 1.3 Academic Team Student 360° — `/school/academic-team/students/[id]/360`
- `web/app/school/academic-team/students/[id]/360/page.tsx`; back link "Back to student" → `/school/academic-team/students/{id}`. See §4.

---

## 2. CAREER COUNSELOR portal

### 2.1 Career Counselor Dashboard — `/school/career-counselor/dashboard`
- File `web/app/school/career-counselor/dashboard/page.tsx` (1-34). Loads `/auth/me`, `GET /school/career-counselor/records`, `GET /school/portfolio-students`.
- Sections: Records card, (inline Edit record card), "Add a record" card, "Career preferences" card, "Student 360° view" directory (names link straight to `/school/career-counselor/students/{id}/360`).
- **ROLE_NAVIGATION mismatch:** `/school/career-counselor/students/[id]/records` (ROLE_NAVIGATION.md:238) does not exist; records live on the dashboard.

#### 2.1.a Records table — `web/components/SchoolCareerRecordsPanel.tsx`
- Heading "Records". Empty "No career guidance or counselling recorded yet." Columns: Student | Type | Status | Next follow-up | Notes | (Actions, hidden header). Type labels "Guidance session"/"Counselling note"/"Recommendation". Status pill; recommendation shows "—"; legacy rows "No status (recorded before tracking)". Each row "Edit" button.
- No search/filter/sort/pagination (server order newest first, schools.py:2215).
- Edit opens inline card "Edit record for {Student}" with the same form (no Student/Type fields) + "Save changes"/"Cancel"; Escape cancels.

#### 2.1.b Add / edit a counselling record — `web/components/CareerRecordForm.tsx`, `web/lib/careerRecords.ts`
Fields:
| Label | Type | Required / rules |
|---|---|---|
| Student (create only) | combobox | required ("Choose a student from the list.") |
| Type (create only) | select "Select type" / Guidance session / Counselling note / Recommendation | required |
| *Session* fieldset (Guidance session & Counselling note only) | | |
| Status | select; create offers Not Started / Scheduled / Completed (default Completed); edit offers current + next | help "Not Started → Scheduled → Completed → Follow-up Required → Completed" |
| Scheduled for | datetime-local (only when Scheduled) | required |
| Completed on (defaults to today) | date (only when Completed) | optional |
| Next follow-up | date, min today (only when Follow-up Required) | required |
| *Assessment* fieldset: Career interests, Academic strengths, Weak areas | text, comma-separated | optional; help "Separate items with commas." |
| Interested in global education | select Not recorded / Yes / No | optional |
| *Recommendations* fieldset: Recommended careers, Recommended courses, Recommended subjects/stream, Recommended skills | text, comma-separated | optional |
| *Parent participation*: Parent participated (Not recorded/Yes/No); Participation note (optional) max 500 | | |
| *Counsellor notes*: Notes | textarea | required for Recommendation, and when status Completed / Follow-up Required |
- Buttons: "Save record" (create) / "Save changes" + "Cancel" (edit); busy "Saving…". Success "Record saved." 409 shows button "Discard my changes and reload". 5xx text "Something went wrong on our side. Please try again; your entry is kept." Network: "The request did not complete. Check your connection and try again; your entry is kept."
- Status workflow (api/schemas.py:1706-1712; UI mirror careerRecords.ts:327-330), all by the Career Counselor only:
  - create: Not Started | Scheduled | Completed
  - Not Started → Scheduled; Scheduled → Completed; Completed → Follow-up Required; Follow-up Required → Scheduled or Completed; legacy (no status) → Completed or Follow-up Required.
- Server errors (schools.py:2090-2205; schemas.py): 403 "Career Counselor role required"; 422 "school_student_id is required"; 422 "record_type must be one of guidance_session, counselling_note, recommendation"; 422 "recommendation records take notes only"; 422 "notes is required"; 422 "status must be one of not_started, scheduled, completed when creating a record"; 422 "A scheduled session needs a date and time."; 422 "Choose the next follow-up date."; 422 "The next follow-up date must be today or later."; 422 "A next follow-up date can only be set when the status is Follow-up Required."; 422 "Cannot change status from {X} to {Y}"; 409 "This record was changed by someone else (now {Status}). Reload to see the latest."; 404 "Career record not found"; list items ≤20, each ≤80 chars ("must have at most 20 items", "items must be at most 80 characters"); tier 403 (Silver individual_counselling).
- Notifications: create → "{Career guidance session recorded|Counselling note added|Career recommendation added} for {Name}" / "A Career Counselor has added a new {type} to {Name}'s career profile."; status change → "{Status} — career record for {Name}" / "A Career Counselor updated {Name}'s career record to {Status}." Audit `school.career_record_create/update`.
- Readers: School roles via `GET /school/career-records` (schools.py:2219) — visible immediately (no draft gate).

#### 2.1.c Career preferences card — `web/components/CareerPreferencesCard.tsx`
- Heading "Career preferences". Student combobox (no "required"); loads `GET /school/students/{id}/career-preferences`. Loading "Loading…"; failure "Could not load this student's preferences." + "Retry".
- Fields: Career interests, Preferred countries, Preferred courses (comma lists; help "Separate multiple values with commas."); "Interested in studying abroad" (Not recorded/Yes/No). Button "Save preferences"/"Saving…". Success "Career preferences saved."; fallback error "Could not save; please try again."
- Empty portfolio: "Career preferences can be recorded once a student is in your portfolio."
- Endpoints: `GET/PATCH /school/students/{id}/career-preferences` (school_student_profile.py:131,136); 403 "Career Counselor role required"; extra fields → 422 "{field} is not an accepted field". Not tier-gated. Audit `school.student_career_preferences_update`. No notification.
- Note: "Career interests" here is a student master field — different from the "Career interests" list on a counselling record (two separate stores).

### 2.2 Skills batches (Soft Skills / Digital Skills) — `/school/career-counselor/skills`
- File `web/app/school/career-counselor/skills/page.tsx`; panel `web/components/SchoolSkillBatchesPanel.tsx`; sidebar "Skills".
- Schools offered = schools of portfolio students (page.tsx:26) — a school in the portfolio with **zero students** cannot get a batch (as-built).
- No school: "You are not assigned to any school yet." / "Ask an admin to add you to a school's team. That school's students can then be enrolled in skills batches here."
- Header "Skills batches" + "Soft Skills and Digital Skills batches at the schools you support."
- Filters: "Module" (All modules / Soft Skills / Digital Skills); "Status" (Open and closed / Open / Closed). No text search, no sort control (newest first).
- Pagination: 25 per page, "Showing X of Y", "Load more"/"Loading…" (server `limit` 1-100, `offset`).
- List rows: title (link to batch), "{Module} · {School} · [from ]{dates}[ · topic]", "{n} enrolled", status pill Open/Closed.
- Empty: "No skills batches yet." / "Create one below, then enrol students, add sessions to take attendance, and record assessments." + "Create a batch" (focuses Title). Filtered empty: "No batches match these filters." Load failure: "Could not load skills batches." + "Try again"; 401 "Your session has expired." + "Sign in again".
- **Create a batch** form (`web/components/SchoolSkillBatchForm.tsx`):
  | Label | Required | Notes |
  |---|---|---|
  | School (select, only if >1 school; else "School: **name**") | yes | "Choose a school" |
  | Skills module | yes | Soft Skills (default) / Digital Skills |
  | Title | yes, ≤160 | "Enter a title" |
  | Topic (optional) | ≤120, placeholder "e.g. Public speaking, Coding" | |
  | Trainer name (optional) | ≤120 | |
  | Start date | yes | "Choose a start date" |
  | End date (optional) | min = start | "The end date must be on or after the start date" |
  - Button "Create batch"/"Creating…"; success navigates to the new batch page. Server 422 marks fields; alert "Check the highlighted fields."
- Endpoints (`api/api/school_skills.py`, guard `_require_career_counselor` line 80 → 403 "Career Counselor role required"): `POST /school/career-counselor/skill-batches` (206) — 403 "This school is outside your own portfolio", tier 403; `GET .../skill-batches` (222).

### 2.3 Skills batch detail — `/school/career-counselor/skills/[id]`
- File `web/app/school/career-counselor/skills/[id]/page.tsx`. Link "← All skills batches". 404/422 → "Batch not found" / "This skills batch does not exist, or it belongs to a school outside your portfolio." + "Back to skills batches".
- **Header** (`SchoolSkillBatchHeader.tsx`): "{Module} · {School}", title, dates, "Topic:", "Trainer:", Open/Closed pill. Closed warning "This batch is closed. Reopen it to add students, sessions, attendance or scores." Buttons "Edit details", "Close batch"/"Reopen batch". Edit form: Title, Topic (optional), Trainer name (optional), Start date, End date (optional); "Save details"/"Cancel". Success "Details saved." / "Batch closed." / "Batch reopened." Server: 422 "title must not be blank", 422 "The end date must be on or after the start date", 404 "Skills batch not found". `PATCH .../skill-batches/{id}` (261).
- **Students** (`SchoolSkillEnrolments.tsx`): table Student | Status | Attendance | Change. Status labels Enrolled/Completed/Certified/Withdrawn or "Transferred out" (frozen: "Moved to another school; read-only here."). Attendance "No attendance yet" / "Attended X of Y session(s)". Change buttons by status: Enrolled → "Mark completed", "Certify", "Withdraw"; Completed → "Certify", "Re-enrol"; Withdrawn → "Re-enrol"; Certified → "No further changes". Certify asks "Certify {name}? A certificate cannot be undone." Confirm/Cancel. Success "{name}: {Status}."
  - Enrol (open batch only): "Enrol students" — "Filter students" search box + checkbox list of the batch school's not-yet-enrolled portfolio students; button "Enrol N student(s)"/"Enrolling…"; success "N student(s) enrolled.". Messages: "No students at {school} yet.", "Every student at {school} is already enrolled.", "No student matches “{filter}”."
  - Server: 409 "This batch is closed. Reopen it to make this change."; 404 "Student not found"; 403 OUTSIDE (school variant); 422 "A student in this request is at a different school than this batch"; 409 "A student in this request is already enrolled in this batch"; 409 "A batch can hold at most 200 students"; 409 "An enrolment cannot change from {old} to {new}"; 409 "This student has moved to another school; their record in this batch is read-only"; 404 "Enrolment not found". Max 100 students per enrol request (schema). Status change allowed on closed batch.
  - Endpoints: `POST .../skill-batches/{id}/enrollments` (319), `PATCH .../skill-enrollments/{id}` (362).
  - Notifications: enrolled / completed / certified → parent "{Name} enrolled in {batch}" / "{Name} completed {batch}" / "{Name} certified in {batch}" (school_skills.py:301-307). Withdraw / re-enrol: none.
- **Sessions and attendance** (`SchoolSkillAttendance.tsx`): add form "Session date" (required, within batch dates) + "Session topic (optional)" ≤160, button "Add session" (success "Session on {date} added."). "Session" select. Roster: checkbox per markable student (enrolled/completed, not frozen), "Mark all present", "Save attendance" (success "Attendance saved for {date}."), "Unsaved changes" + leave-page prompt "You have unsaved attendance. Leave this page without saving it?". Empty "No sessions yet. Add one to start taking attendance."; "No student in this batch can be marked: they are certified, withdrawn or have moved school." Closed batch → read-only list "{name}: Present/Absent/Not marked".
  - Server: 422 "The session date must be within the batch's dates"; 409 "This batch already has a session on DD Mon YYYY"; 404 "Session not found"; 422 "An enrolment in this request is not in this batch"; 409 "A withdrawn or certified enrolment cannot be changed". Endpoints `POST .../skill-batches/{id}/sessions` (443), `PUT .../skill-sessions/{id}/attendance` (463).
- **Assessments and scores** (`SchoolSkillScores.tsx`): add "Assessment name" (required ≤120) + "Maximum score" (0.01–1000), "Add assessment" (success "{name} added."). "Assessment" select "{name} (out of {max})". Grid per student: "Score for {name} (out of {max})", "Remarks for {name} (optional)" ≤2000; "Save scores" (success "Scores saved for {name}."). Client error "Enter a score from 0 to {max}". Empty "No assessments yet. Add one to record scores." Closed → read-only list.
  - Server: 409 "This batch already has an assessment with that name"; 404 "Assessment not found"; 422 "Scores must be out of {max}". Endpoints `POST .../skill-batches/{id}/assessments` (492), `PUT .../skill-assessments/{id}/scores` (510).
- Generic skills errors: 5xx "The change was not saved because of a problem on our side. Your entry is kept; please try again in a moment."; 401 "Your session has expired." + "Sign in again"; success messages auto-clear after 8 s.
- Tier: every write gated (soft_skills Bronze / web_designing Silver); list/detail reads not gated.

### 2.4 Funding support — `/school/career-counselor/funding`
- Files `web/app/school/career-counselor/funding/page.tsx` (frontend role check line 20), `web/components/SchoolFundingRecordsPanel.tsx`, `FundingRecordForm.tsx`, `web/lib/fundingRecords.ts`; sidebar "Funding".
- Card "Funding support" + "Education loans, financial assistance, scholarships and funding guidance for your students."
- "Open cases" table: Student | Support type | Stage | Since | Provider | (Edit). Stage text "Stage N of 6 · {Label}" or "Closed". Empty: "No funding support cases yet. Add one below when a student needs a loan, scholarship or funding guidance." / "No open cases."
- "Finished cases (N)" collapsible: Student, Support type, Outcome "{stage} on {date}", Reason.
- No search/filter/pagination (server order: open first, then updated desc).
- **Add a case** form: Student (combobox, required), Support type (Education loan / Financial assistance / Scholarship / Funding guidance, required), Provider or institution (optional, ≤200), Amount (optional, ≤120, help "As written by the provider, e.g. ₹5,00,000 or 50% of tuition."), Notes (≤4000, optional). Button "Add case". Success "Case saved." (shown in the form).
- **Update case** ("Update {name}'s {type} case"): Stage select (current "(current)" + next stage + Closed; help "Required → Counselling → Documents → Application → Approved → Completed, one stage at a time. Close a case that will not go ahead."), Reason for closing (only when Closed, required ≤500, help "For example: loan not approved, family withdrew. A closed case cannot be reopened."), Provider, Amount, Notes; "Save changes"/"Cancel". Panel notice "Case saved."
- Workflow (schemas FUNDING_STATUS_NEXT): Required → Counselling → Documents → Application → Approved → Completed; any open stage → Closed; Completed/Closed final. Career Counselor only.
- Server (school_funding.py): 403 "Career Counselor role required"; 404 "Student not found"; 403 OUTSIDE_PORTFOLIO; tier 403; 409 "{Name} already has an open {type} case. Open it from the list to update it."; 404 "Funding support case not found"; 403 "This case belongs to the student's previous school and can no longer be changed."; 409 "This case was changed by someone else (now {Stage}). Reload to see the latest."; 422 "This case is {Completed|Closed} and can no longer be changed."; 422 "Cannot change status from {X} to {Y}"; 422 "Give a reason for closing this case."; 422 "A closure reason can only be given when closing the case."; field 422 messages use labels (Student, Support type, Stage, Provider or institution, Amount, Notes, Reason for closing).
- Endpoints: `GET /school/career-counselor/funding-records` (108), `GET /school/students/{id}/funding-records` (128, readers incl. counselor; teachers refused "Funding support cases are not visible to teachers."), `POST /school/funding-records` (148), `PATCH /school/funding-records/{id}` (195).
- Notifications: create → "Funding support update for {Name}" / "{Type} support is now being tracked (Required)."; stage change → "{Type} support is now at {Stage}." Denials audited `school.funding_record_denied`.

### 2.5 Career Counselor Student 360° — `/school/career-counselor/students/[id]/360`
- Back "Back to dashboard". Career goal is editable here (see §4.2). See §4.

---

## 3. PSYCHOMETRIC TEAM portal

### 3.1 Psychometric Team Dashboard — `/school/psychometric-team/dashboard`
- File `web/app/school/psychometric-team/dashboard/page.tsx`. Loads `/auth/me`, `GET /school/psychometric-team/records`, portfolio students.
- Sections: Assessments card, (Attach report card / Results editor), "Assign an assessment" card, "Bulk entry — assessments (CSV)", "Student 360° view" directory (links to `/school/psychometric-team/students/{id}/360`).
- **ROLE_NAVIGATION mismatch:** `/school/psychometric-team/students/[id]/assessments` (ROLE_NAVIGATION.md:248) does not exist; all on dashboard.

#### 3.1.a Assessments table — `web/components/SchoolPsychometricRecordsPanel.tsx`
- Heading "Assessments". Empty "No assessments assigned yet." Columns: Student | Assessment | Status (raw `assigned`/`completed`) | Actions. Actions: "Attach report" (assigned) or text "Report attached"; plus "Record results"/"Edit results".
- No search/filter/sort/pagination (newest first).
- **Assign an assessment**: Student (combobox, required), Assessment type (text, required, placeholder "e.g. Aptitude Test"); "Assign assessment"/"Saving…"; success "Assessment assigned."
- **Attach report** card: "Report URL" (text, required, placeholder "/local-files/uploads/report.pdf"); "Attach"/"Cancel"; success "Report attached." — a URL/text, **not a file upload**; any string accepted by the API (no validation on single entry; bulk requires http/https). In the 360 Documents tab only a same-origin path or https URL becomes a link (`web/lib/student360Links.ts:51-61`). No UI to change the URL after attaching.
- Status: Assigned → Completed (set when a non-empty report_url is saved). Psychometric Team only.
- **Record/Edit results** (`web/components/PsychometricResultsForm.tsx`, `web/lib/psychometric.ts`): heading "Results — {Student} · {Assessment}".
  - Assessment: Test date (date).
  - Findings (help "Separate items with commas (use / or ; inside an item) — up to 20 items of 80 characters each."): Strengths, Interest areas, Personality indicators, Career recommendations, Recommended streams.
  - Counselling & follow-up: Counsellor remarks (≤4000, counter "n / 4000"), Parent discussion date, Follow-up date, Parent discussion notes (≤2000).
  - Buttons "Save results"/"Saving…", "Cancel". Messages: "No changes to save."; field errors "Up to 20 items.", "Each item must be 80 characters or fewer.", "Enter a complete date, or clear the field."; 401 "Your session has ended. Sign in again in a new tab, then press Save here — your entry is kept." + link "Sign in again (opens a new tab)"; 5xx "Something went wrong on our side. Your entry is kept — try again in a moment."; leave prompt "Leave without saving your results?". Success "Results saved." (shown under the assign card). Only changed fields sent.
- Endpoints (schools.py): `POST /school/psychometric-team/records` (2234), `PATCH .../{id}` (2267), `GET` (2299); readers `GET /school/psychometric-records` (2311). Errors: 403 "Psychometric Team role required"; 422 "school_student_id is required"; 422 "assessment_type is required"; 404 "Record not found"; date "must be a date in YYYY-MM-DD format"; tier 403 (Bronze psychometric_test).
- Notifications: assign → "Psychometric assessment assigned to {Name}" / "{Name} has been assigned a {type}."; report → "Psychometric report ready for {Name}" / "The {type} report for {Name} is now available." Results edits never notify.

### 3.2 Psychometric Team Student 360° — `/school/psychometric-team/students/[id]/360`
- Back "Back to dashboard". Read-only. See §4.

---

## 4. STUDENT 360° VIEW / Career Passport (ENH-013) and Digital Portfolio (ENH-012)

### 4.1 Routes (all 7 share `renderStudent360Route`, `web/components/Student360Route.tsx:18-32`)
`/school/{coordinator|principal|teacher}/students/[id]/360`, `/school/parent/children/[id]/360`, `/school/academic-team/students/[id]/360`, `/school/career-counselor/students/[id]/360`, `/school/psychometric-team/students/[id]/360`.
- API: `GET /school/students/{id}/360-view` (`api/api/student_360.py:141`), scope via `_load_student_for_reader` (service roles: portfolio; School roles: own school / assigned / own child). Not tier-gated.
- Header card (`web/components/Student360View.tsx`): "Student 360° view", name (+ Student ID for School roles), facts (school · grade · "Born {date}"), "**Career goal:** {goal | Not set}", back button.
- Service-role header shows only name + school (student_360.py:76-77).
- Tabs (`Student360Tabs.tsx`): vertical tablist "Student record sections"; badge count when has data, "Restricted" label when restricted; arrow/Home/End keys; selection kept in `?tab=` (deep-linkable, e.g. `?tab=career_guidance`). Empty tab: role-specific empty text; restricted tab: "This section is not available for your role."
- Loading skeleton per route (`loading.tsx`).

### 4.2 The 16 tabs — visibility per role (`api/api/student_360.py:61-138`) and editability
School = coordinator/principal/teacher/parent. AT = academic_team, CC = career_counselor, PT = psychometric_team.

| # | Tab (label) | School | AT | CC | PT | What is shown | Editable? |
|---|---|---|---|---|---|---|---|
| 1 | Overview | ✔ | ✔ | ✔ | ✔ | Career goal card; Achievements (portfolio Award + Competition entries); "Digital Portfolio N% complete." | Career goal: **CC only** (Set/Edit) |
| 2 | Personal Details | ✔ full (Name, Student ID, Grade/Class, Date of birth, School, Assigned teacher) | name+school only | name+school | name+school | facts list; note "Additional profile fields are not tracked yet (ENH-025)." | no |
| 3 | Academic Records | ✔ (current grade + grade history) | Restricted | Restricted | Restricted | | no |
| 4 | Attendance | ✔ (daily, activities, skills sessions) | Restricted | Restricted | Restricted | | no |
| 5 | Examination Results | ✔ published, Year/Term/Subject/Marks/Grade | ✔ published, full | ✔ published, Year & Marks show "-" (portfolio subset) | same as CC | table "Published results" | no |
| 6 | Career Guidance | ✔ | ✔ | ✔ | ✔ | records with type, date, notes + details | no (edit on CC dashboard) |
| 7 | Psychometric Assessment | ✔ with Status | ✔ (Status "-") | ✔ (Status "-") | ✔ with Status | Assessment / Status / Assigned on + results list | no (edit on PT dashboard) |
| 8 | Skills | ✔ batches + portfolio skills | portfolio skill entries only | ✔ batches (transferred-out enrolments hidden) + portfolio skills | portfolio skill entries only | | no |
| 9 | Foreign Languages | ✔ | ✔ | ✔ (portfolio subset) | ✔ (portfolio subset) | Language / Level / Certification | no |
| 10 | English Testing | ✔ | ✔ | Restricted | Restricted | Test / Target / Result / Status | no |
| 11 | Activities | ✔ attended + upcoming school activities + portfolio entries | portfolio entries only | portfolio only | portfolio only | sections Projects, Internships, Sports, Leadership, Volunteering, Extracurriculars | no |
| 12 | Certificates | ✔ | ✔ | ✔ | ✔ | portfolio Certification entries incl. Skill India badge/status/number/issued | no |
| 13 | Documents | ✔ | ✔ | ✔ | ✔ | psychometric report links; "A student document registry is not tracked yet (ENH-013b)." | no |
| 14 | Teacher Remarks | ✔ | ✔ | Restricted | Restricted | remarks on published results | no |
| 15 | Parent Communication | ✔ (always empty) | ✔ | ✔ | ✔ | "No parent communication log yet." + "A parent communication log is not tracked yet (ENH-013b / ENH-014)." | no |
| 16 | Edusphere Programs | ✔ Soft/Digital Skills, Test preparation, Foreign languages, Internship, Global education | Test prep, Foreign languages, Internship | Soft/Digital Skills, Foreign languages, Internship | Foreign languages, Internship | programme + status chip | no |

- Only write action inside the 360: **Career goal** (`web/components/CareerGoalForm.tsx`, shown when `can_edit_career_goal` = role is career_counselor, student_360.py:138). Button "Set career goal"/"Edit career goal"; input "Career goal" max 120 with counter "{n} of 120 characters"; "Save"/"Saving…", "Cancel" (Escape). Success "Career goal saved."; failure fallback "The career goal could not be saved. Please try again."; network NOT_COMPLETED. Empty value clears the goal. Endpoint `PATCH /school/students/{id}/career-goal` (student_360.py:153): 403 "Career Counselor role required", OUTSIDE_PORTFOLIO, 404 "Student not found", tier 403 (Silver individual_counselling); single-line text, no control chars. Audit `school.career_goal_update`. No notification.
- Empty-state texts per tab (`web/components/Student360Panels.tsx:24-41`), e.g. "No published results yet. Results appear after the Academic Team publishes them.", "No career guidance recorded yet. The Career Counselor adds sessions and notes.", "No psychometric assessments yet. The Psychometric Team assigns them.", "No certificates recorded yet. Staff add them in the Digital Portfolio.".

### 4.3 Digital Portfolio panel (editable by Academic Team on its student page; also coordinator/assigned teacher elsewhere)
- Component `web/components/PortfolioPanel.tsx`; API `api/api/portfolio.py`. Writers `WRITE_ROLES = {school_coordinator, school_teacher (assigned only), academic_team}` (portfolio.py:53, 78-87). Career Counselor and Psychometric Team are readers only.
- Card "Digital Portfolio", progress bar + "{N}% complete" (equal weight: profile complete [DOB + grade], has published result, has psychometric, has career record, has language, each of 10 sections has ≥1 entry, personal statement — portfolio.py:129-133).
- Read-only sections: Profile ("Profile complete"/"Profile incomplete"), Academic achievements (published results "Subject — Term (Grade)"), Psychometric report (assessment type), Career guidance (**raw record_type**, e.g. `guidance_session` — as-built), Languages.
- Editable sections (alphabetical by key, PortfolioPanel.tsx:349): Awards, Certifications, Competitions, Extracurriculars, Internships, Leadership, Projects, Skills, Sports, Volunteering; then Personal statement.
  - Each: entries (title — organization (dates), Skill India details, description, internship details), buttons "Edit {title}", "Delete {title}" → "Confirm delete {title}"; "Add {singular}" (e.g. "Add certification"). One form open at a time. Empty "No entries yet."
  - Confirmations: "{Section} added." / "{Section} updated." / "{Section} deleted." / "Personal statement saved." Delete failure "Delete failed." or server text.
- **Entry form** (`web/components/PortfolioEntryForm.tsx`):
  | Label | Rules |
  |---|---|
  | Title (Role for internship) | required ≤200 — "Enter a title." / "Enter the role." |
  | ☐ Skill India certification (checkbox; only when ADDING a Certification) | tag fixed after create; on edit shown as text "Skill India certification" |
  | Skill India details: Status (Choose status / Enrolled / In progress / Certified) | required when tagged — "Choose a status." |
  | Certificate number ≤100 (hint "Required once certified.") | "Enter the certificate number." when Certified |
  | Issue date (hint "Required once certified.") | "Enter the issue date." when Certified |
  | Organization (optional) / "Issuing body (optional)" for Skill India / "Company" for internship | Company required — "Enter the company." |
  | Start date (optional), End date (optional) | server "End date must not be before start date" |
  | Internship tracking (Platinum only): Mentor name (optional), Mentor designation (optional), Completion (No status/Not started/In progress/Completed/Discontinued; help "A completed internship needs an end date."), Attendance % (optional, 0-100 — "Attendance must be a whole number from 0 to 100."), Skills acquired (optional, commas), Feedback (optional ≤2000) | |
  | Description (optional) ≤2000 | |
  - Buttons "Save"/"Saving…", "Cancel" (Escape). Failure "The save could not be confirmed. Please check the list before retrying." or server text.
  - Server rules (api/schemas.py:2297-2351): "Only a certification can be marked as Skill India"; "Choose a status for the Skill India certification"; "Status, certificate number and issue date apply only to Skill India certifications"; "A certified Skill India certification needs a certificate number and issue date"; "Company is required for an internship"; "An internship marked completed needs an end date"; "internship fields are only accepted for the internship section"; "title must not be null"; "Remove the certificate first" (changing completion away from Completed while a certificate is attached); 403 "You do not have write access to this student's portfolio"; 404 "Portfolio entry not found"; tier 403 (Gold / Platinum for internships).
  - Without Platinum, Internships section shows "Internship tracking is part of the Platinum partnership. Existing entries can still be edited or removed." and no Add button.
- **Personal statement**: "Add statement"/"Edit statement" → textarea "Personal statement" max 4000, "Save"/"Cancel". `PATCH .../portfolio/personal-statement` (portfolio.py:286).
- **Certificate uploads** (`web/components/InternshipCertificate.tsx`, `api/api/portfolio_certificates.py`):
  - **Only for Internship entries whose Completion = Completed** — there is NO file upload for Skill India certifications (they carry a certificate number/issue date only).
  - Label "Upload certificate (PDF, JPEG or PNG, up to 5 MB)" / "Replace certificate (…)"; "Uploading…"; "Download certificate (PDF|image)"; "Remove certificate" → "Confirm remove"/"Cancel" ("Removing…").
  - Client checks: "Certificate must be a PDF, JPEG or PNG file", "Certificate must be at most 5 MB". Success "Certificate saved." / "Certificate removed."; failures "Upload failed; please try again.", "Something went wrong on our side. Please try again.", "Could not remove the certificate; please try again."
  - Server (portfolio_certificates.py:24-118): max 5 MB (413 "Certificate must be at most 5 MB"); type sniffed from bytes — PDF/JPEG/PNG (415 "Certificate must be a PDF, JPEG or PNG file"); 422 "Certificate file is empty"; 422 "A certificate can only be attached to a completed internship"; 422 "Certificate could not be read as a valid JPEG or PNG image"; 500 "Could not store the certificate; please try again"; 404 "Internship entry not found" / "No certificate on file". Image metadata stripped; stored under `portfolio-certificates/<uuid>`; old object deleted after replace. Download is an attachment `internship-certificate.{pdf|jpg|png}`, audited `school.internship_certificate_download`. Upload/remove gated Platinum `internships`.
  - Endpoints: `PUT|GET|DELETE /school/students/{id}/portfolio/entries/{entry_id}/certificate` (lines 45, 85, 105).
- Portfolio endpoints: `GET /school/students/{id}/portfolio` (121), `POST .../portfolio/entries` (185), `PATCH .../entries/{entry_id}` (221), `DELETE .../entries/{entry_id}` (270), `PATCH .../personal-statement` (286). Audit `school.portfolio_entry_*`. No parent notifications.

---

## 5. Endpoint inventory (this area) — 56
schools.py: portfolio-students; career-counselor/records POST/PATCH/GET; career-records (readers); psychometric-team/records POST/PATCH/GET; psychometric-records (readers); academic-team/test-prep-records POST/PATCH/GET; test-prep-records (readers); academic-team/language-records POST/PATCH/GET; language-records (readers); academic-team/results POST/PATCH/verify/publish/GET; academic-team/progress; results (readers). school_student_profile.py: career-preferences GET/PATCH. student_360.py: 360-view GET, career-goal PATCH. portfolio.py: 5. portfolio_certificates.py: 3. school_skills.py: 10. school_funding.py: 4. school_bulk.py: 8. admin.py: school-staff POST/GET, portfolio POST.

## 6. As-built oddities (do not fix; document)
1. `/school/*` not covered by middleware — signed-out users see "Access unavailable" instead of a redirect.
2. No frontend role guard except Funding; wrong-role users get API text in the access card. Academic student page / 360 routes render with the URL's portal chrome for any role the API admits.
3. ROLE_NAVIGATION routes `/academic-team/results/new`, `/results/[id]`, `/career-counselor/students/[id]/records`, `/psychometric-team/students/[id]/assessments`, bare `/school/academic-team` etc. do not exist (folded into dashboards).
4. Result status, test-prep status, language certification and psychometric status shown as raw lowercase codes on dashboards.
5. Single-entry result API lacks marks range/duplicate/length validation (bulk has them). Results not tier-gated at all.
6. Draft results cannot be edited from the UI (API supports it for the uploader). Result status history recorded but never shown.
7. Test-prep mock scores; language classes attended / assessment score / in-progress: API-only, no UI.
8. Psychometric "Attach report" is a free-text URL, not an upload; cannot be changed from UI afterwards.
9. Digital Portfolio "Career guidance" list shows raw `record_type` codes.
10. Skills: schools without students never appear in the batch "School" list.
11. Add-school-to-portfolio endpoint exists without UI; no remove endpoint.
12. Skill India certifications have no file upload; only internship certificates do.
13. Career Counselor & Psychometric Team are read-only on the Digital Portfolio (not in WRITE_ROLES).

## 7. VERIFICATION REQUIRED
- Login URL for service roles (assumed `/overseas/login`) and post-login redirect — confirm in browser.
- Notification delivery channels (`queue_deliveries`) enabled in the documentation environment.
- Exact behaviour/text when a single-entry result or test-prep/language value exceeds DB column width (likely generic 500).
- Exact browser-native validation bubble texts for HTML `required` fields (browser-dependent).
- Whether the owner wants the doc to mention API-only capabilities (draft edit, add school to portfolio).

## 8. Test data needed
- Seed (api/seed.py:610-760): school "Sunrise Public School" (Platinum, valid 1 yr); users school.academic1@edusphere.local (Divya), school.academic2@edusphere.local (Suresh), school.careercounselor@edusphere.local (Anita), school.psychometric@edusphere.local (Manoj); password = seed `PASSWORD` constant (seed.py; not reproduced in docs); students Aarav Mehta, Isha Mehta, Kabir Nair, Priya Shah, Rohan Gupta; seeded draft/verified/published results by academic1, career records, psychometric records (one assigned).
- Additional: a second school at Bronze/Silver/Gold (or expired) to capture tier-denial messages; a parent linked to a student (to show notifications); an internship entry marked Completed with end date; a sample PDF ≤5 MB and a >5 MB file; a filled CSV per bulk module (+ one with a bad row); a student transferred out (frozen enrolment) optional; an Overseas Admin to create a specialist account.

## 9. Suggested screenshots (sequence-feature-step)
Academic Team:
- 01-at-dashboard-overview; 02-at-progress-card; 03-at-results-table-actions (uploader view: "Ask another…"); 04-at-upload-result-form; 05-at-upload-result-success; 06-at-verify-as-second-member; 07-at-publish-result; 08-at-bulk-results-expanded; 09-at-bulk-upload-report (accepted+rejected); 10-at-test-prep-start; 11-at-test-prep-record-score; 12-at-language-start; 13-at-language-mark-certified; 14-at-students-directory; 15-at-student-portfolio-page; 16-at-portfolio-add-certification-skill-india; 17-at-portfolio-skill-india-validation-errors; 18-at-portfolio-internship-form-tracking; 19-at-internship-certificate-upload; 20-at-personal-statement-edit; 21-at-portfolio-delete-confirm; 22-at-360-overview; 23-at-360-restricted-tab.
Career Counselor:
- 30-cc-dashboard-records; 31-cc-add-record-guidance-session; 32-cc-record-status-scheduled; 33-cc-edit-record-follow-up; 34-cc-record-409-reload; 35-cc-career-preferences; 36-cc-360-set-career-goal; 37-cc-skills-list-filters; 38-cc-skills-create-batch; 39-cc-batch-header-edit-close; 40-cc-batch-enrol-students; 41-cc-batch-certify-confirm; 42-cc-batch-session-attendance; 43-cc-batch-assessment-scores; 44-cc-batch-closed-readonly; 45-cc-funding-open-cases; 46-cc-funding-add-case; 47-cc-funding-update-stage; 48-cc-funding-close-with-reason; 49-cc-funding-finished-cases; 50-cc-tier-denied-message.
Psychometric Team:
- 60-pt-dashboard; 61-pt-assign-assessment; 62-pt-attach-report; 63-pt-record-results-form; 64-pt-results-validation; 65-pt-bulk-assessments; 66-pt-360-psychometric-tab.
Shared / admin:
- 70-admin-create-specialist-account-portfolio; 71-access-unavailable-wrong-role; 72-360-tab-list-mobile.
