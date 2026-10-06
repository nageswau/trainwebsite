# Discovery: School Coordinator portal (role `school_coordinator`)

> **Evidence appendix** for `docs/school-crm/documentation-analysis.md` — raw read-only source discovery (master planning session S1, 2026-10-05, code `main` @ `ce1f07c2`). Field-level detail for module sessions. Not browser-verified; where this file and the browser disagree, the browser wins and this file is annotated, not silently trusted.

Read-only source discovery, code = `main` @ ce1f07c2 (branch `docs/school-crm-user-guide`). Nothing was run; every statement is from source.
Paths are relative to the repo root. `W:` = `apps/web/`, `A:` = `apps/api/app/`. All API paths are mounted under `/api/v1` (`A:main.py:79-80`).

---

## 0. Cross-cutting facts (read first)

### 0.1 Sign-in and landing
- Coordinator account is created by an Overseas Admin together with the School (`POST /overseas-admin/schools`, `A:api/admin.py:1421-1437`, provisioning `A:api/admin.py:1380-1416`). Password hash is unusable; a welcome link is issued and delivered (`issue_welcome_token` / `deliver_welcome_link`). Coordinator sets their own password from that link (welcome-link flow is outside this area -- VERIFICATION REQUIRED for exact screens).
- Login form: the role's dashboard is `ROLE_DASHBOARD_PATH.school_coordinator = "/school/coordinator/dashboard"` (`W:lib/navigation.ts:31`); `LoginForm` pushes there after login (`W:components/LoginForm.tsx:40`). Which login URL a coordinator should use is not stated in UI; every coordinator error card links to `/overseas/login` (`W:components/AccessUnavailable.tsx:40,45`). Account is `division="overseas"`.
- Seed/demo account: `school.coordinator@edusphere.local`, password = seed `PASSWORD` constant (not reproduced in docs), "Fatima School Coordinator", school "Sunrise Public School" (Hyderabad), tier **platinum** valid 365 days (`A:seed.py:14,620-640`).
- Middleware does NOT protect `/school/*` (matcher is only `/it`, `/overseas`, `/admin`, `/bdm` -- `W:middleware.ts:18`). A signed-out user who opens a coordinator URL gets the page's own "Access unavailable" card (401 from the API) with a "Return to login" link, not a redirect.

### 0.2 Shell / sidebar
- Every coordinator page renders `PortalShell` with `roleLabel="School Coordinator"` and `nav={SCHOOL_NAV.coordinator}` (`W:components/PortalShell.tsx:17`).
- Sidebar items (labels are generated: hyphen -> space, title case), in order (`W:lib/navigation.ts:72`):
  **Dashboard, Students, Promotion, Transfers, Activities, Feedback, Team, Reports, Global Education, Entitlements, Notifications** -> `/school/coordinator/<slug>`.
- Sidebar footer: "Change password" (`/account/password`), "My profile" (`/account/profile`), "Sign out". Top bar: "EduSphere Portal" + user name; below 980 px a menu (`PortalMobileNav`) replaces the sidebar.
- Active item is marked only on an exact path match (`aria-current` when `pathname===x.href`), so sub-pages (`/students/[id]`, `/students/bulk-upload`, `/students/[id]/360`) highlight nothing.
- No unread badge is wired for the school Notifications item (no `badge` set on SCHOOL_NAV).

### 0.3 Authorization model (as built)
- `A:core/rbac.py:40` maps `school_coordinator` -> `{"school:coordinator:own_institution"}` but the school routes do **not** use it; every route checks `user.role` inline.
- Coordinator gate helpers: `_require_coordinator` (role must be `school_coordinator`, `profile.school_id` must exist; 403 "School Coordinator role required" / 403 "This account is not linked to a school") `A:api/schools.py:128-134`; dependency form `_require_coordinator_user` `A:api/schools.py:1677`; `_own_school_id` (any of the 4 school roles; 403 "School role required") `A:api/schools.py:348-354`; feedback/analytics/global-ed/school-summary reader `_require_school_reader` (coordinator or principal; 403 "School Coordinator or Principal role required") `A:api/school_feedback.py:105-110`.
- School scope always comes from the server-side `profile.school_id` -- never from the request.
- **Frontend role guard is inconsistent** (see 9.1): Feedback, Notifications, Promotion, Reports, Transfers, Student detail, Global Education check `user.role === "school_coordinator"` and show "Access unavailable / School Coordinator role required"; Dashboard, Students, Bulk upload, Activities, Team, Entitlements, Student 360 do **not** and rely on the API.

### 0.4 Partnership tier (entitlement) model -- applies to several features
- Tiers are cumulative: bronze < silver < gold < platinum (`A:api/schools.py:979-1020`).
  - Bronze: Career seminar; Student career awareness session; Parent orientation; Psychometric test; Soft skills.
  - Silver adds: Individual counselling; Digital skills (key `web_designing`).
  - Gold adds: Application support; Scholarship assistance; IELTS coaching; SAT coaching; Foreign language classes; Digital portfolio creation.
  - Platinum adds: Dedicated EduSphere counselor; Monthly campus visits; Internships; Visa support; Loan assistance; Alumni network; Parent help desk.
- Enforcement `require_school_entitlement` (`A:api/schools.py:1122-1149`), messages from `_entitlement_denial` (`A:api/schools.py:1075-1088`), all **HTTP 403**:
  - no/unknown tier: `This school has no active partnership tier.`
  - expired (`tier_valid_until` before today, India calendar): `This school's partnership expired on DD Mon YYYY.`
  - not included: `This school's <Tier> partnership does not include <Service label> (requires <MinTier> or higher).`
  - A denial writes an `AuditLog` `school.tier_access_denied` (outcome denied) and is committed.
  - "Grandfathering" (ENH-023): finishing work created before a downgrade/removal is allowed (`school.tier_grandfathered` audit), never for an expired partnership (`A:api/schools.py:1093-1119`).
- Coordinator-reachable gated writes: **Schedule activity** (typed -> its service; untyped -> just needs a valid tier), **Mark attendance** (same, grandfathered from activity creation), **Portfolio entries** on student page (Gold `digital_portfolio_creation`; internship tracking = Platinum `internships`) -- `A:api/schools.py:1797,1819`, `A:api/portfolio.py:57-60,189,230,276,295`.
- Nothing in the coordinator UI is *hidden* by tier; the UI lets you try and shows the 403 text. Exceptions: Entitlements page lists only included services; Scorecard areas outside the plan read "Not in plan" (`A:api/school_analytics.py:407-412`).

---

## 1. Dashboard  — `/school/coordinator/dashboard`
- Sidebar: **Dashboard**. Also the post-login landing page.
- Frontend: `W:app/school/coordinator/dashboard/page.tsx:19-67`. No frontend role check (a Principal opening this URL gets data and the coordinator shell -- see 9.1).
- Backend: `GET /school/dashboard` `A:api/schools.py:900-905` -- roles coordinator **or** principal; else 403 "School Coordinator or Principal role required". Payload builder `_school_dashboard_payload` `A:api/schools.py:404-573`.
- Also calls (via `SchoolServiceDeliverySummary`, `W:components/SchoolServiceDeliverySummary.tsx`): `GET /school/results` (`A:api/schools.py:2665`), `GET /school/career-records` (`:2219`), `GET /school/psychometric-records` (`:2311`) -- each allows the 4 school roles.

### Screen elements (top to bottom)
1. **"School at a glance"** card (`W:components/SchoolKpiBoard.tsx`) -- 20 KPI tiles in 4 groups. Values formatted `en-IN`. If `tracked=false`, tile shows badge "Not tracked yet" + note (currently none are untracked: `UNTRACKED_SCHOOL_DASHBOARD_KPIS = {}` `A:api/schools.py:112`). Empty: "No figures to show yet."
   - **Students**: Total Students (all roster rows); Grade 8 / 9 / 10 / 11 / 12 (by `grade_level`, falling back to a number parsed from Grade/Class text "grade|class 8..12" -- `A:api/schools.py:378-391`). Grades 1-7 are not shown as tiles.
   - **Career & assessment**: Career Guidance Completed (distinct students with a `guidance_session` career record whose status counts as completed -- completed / follow-up required / legacy null); Psychometric Tests Completed (distinct students with a psychometric record `status=completed`); Individual Counselling Completed (distinct students with a completed `counselling_note`).
   - **Skills & languages**: IELTS Training / SAT Preparation (distinct students with any IELTS / SAT test-prep record, any status); Foreign Language Students (any language record); Digital Portfolios Created (students with a started portfolio).
   - **Global pathway**: Students in Global Education Pathway (students with >=1 linked overseas application); University Shortlisting (application at `university_selection` or later); Applications in Progress (**count of applications**, not students, status not withdrawn/rejected/enrolled); Offers Received (**count of applications** in an offer-onward status or with an offer letter URL); Visa Applications (distinct students with a visa case); Students Admitted (status `enrolled`); Internships (distinct students with an internship portfolio entry).
2. **"Your school"** card: empty text "No students yet. Add your first student, or upload your roster in bulk." else "`N` student(s) on your roster." Buttons: **Go to student roster**, **Go to bulk upload**, **Go to activities**, **Go to reports**.
3. **"Upcoming activities"** table: columns Title, When (IST, `formatSchoolDateTime`). Max 10, soonest first, only activities with `scheduled_at >= now` (`A:api/schools.py:485-489`). Empty: "Nothing scheduled yet." No search/filter/sort/pagination.
4. **"Results & guidance"** card: "`n` published result(s), `n` career guidance/counselling record(s), `n` psychometric assessment(s)." Hidden entirely if all three are 0 **or if any of the three calls fails** (`W:components/SchoolServiceDeliverySummary.tsx:65-68`).

Side effects: none (read-only). Test data: students across grade levels 8-12 plus some with only text grades; career/psych/test-prep/language records; overseas applications at various statuses; future activities. Screenshots: `coord-01-dashboard-overview`, `coord-01-dashboard-kpis`, `coord-01-dashboard-empty-school`.

---

## 2. Student roster, add one student, edit, link parent — `/school/coordinator/students`
- Sidebar: **Students**. Also from Dashboard "Go to student roster", Transfers/Promotion empty states.
- Frontend: `W:app/school/coordinator/students/page.tsx:10-23` + `W:components/SchoolStudentsPanel.tsx` + fields `W:components/SchoolStudentFields.tsx`, helpers `W:lib/schoolStudents.ts`. **No frontend role check.**
- `/school/coordinator/students/new` (listed as SCR-SCH-004 in `docs/ux/ROLE_NAVIGATION.md:196` and `docs/ux/SCREEN_CATALOG.md:2073,2157`) **does not exist** as a route. "Add one student" was folded into the roster page as an inline card. Opening `/students/new` resolves to the `[id]` route with id `new`; the API's UUID validation fails (422), and the page shows "Access unavailable" with the error message -- because `serverApi` passes a list `detail` straight into `Error(...)`, the text is likely "[object Object]" (VERIFICATION REQUIRED in browser) (`W:lib/api.ts:26-29`, `W:app/school/coordinator/students/[id]/page.tsx:38-47`).

### Backend endpoints
| Method/path | File:line | Guard |
|---|---|---|
| GET `/school/students` | `A:api/schools.py:1248-1253` | any of 4 school roles (own-scope query); coordinator = whole own school, ordered by full name |
| GET `/school/team` (teacher picker) | `A:api/schools.py:218-232` | coordinator only |
| POST `/school/students` | `A:api/schools.py:1538-1590` | coordinator only, 403 "School Coordinator role required" |
| PATCH `/school/students/{id}` | `A:api/schools.py:1593-1644` | coordinator only; 404 "Student not found"; 403 "This student is at a different institution" |
| POST `/school/students/{id}/parents` | `A:api/schools.py:1647-1669` | coordinator only; other school's student -> 404 "Student not found" |

### Roster table (`SchoolStudentsPanel.tsx:182-213`)
- Heading "Student roster". Columns: **Student ID** (8-char hex code), **Name**, **Grade/Class**, **Section**, **Roll no.**, **Parent**, **Actions**. Missing values show "-".
- Parent column shows only a *pending* invite: badge "Invite sent to <email>"; a linked parent is NOT shown (always "-").
- Actions per row: **Edit**, **Link parent**, **Profile & timeline** (-> `/school/coordinator/students/{id}`).
- Empty: "No students yet. Add one below, or use bulk upload for many at once." (link to bulk upload).
- **No search, no filters, no sorting control, no pagination** (all rows rendered; server orders by name). No teacher column, no delete/archive.

### "Add one student" form (card heading "Add one student"; also used, pre-filled, for "Edit <name> (<code>)")
Groups/fields (`SchoolStudentFields.tsx`):
- **Identity**: "Full name" (text, **required** HTML), "Date of birth" (date, optional), "Gender" (select: Not recorded / Female / Male / Other / Prefer not to say).
- **Class placement**: "Grade/Class" (text, max 60, optional), "Grade level (1-12, optional)" (number 1-12 step 1), "Section" (max 20), "Roll number" (max 20; help "Unique within the grade, section and academic year."), "Assigned Teacher" (select: "Unassigned" + own-school teachers; Add shows active teachers only, Edit also shows inactive ones suffixed " (inactive)").
- **Contact**: "Student mobile" (tel, max 20), "City" (max 120), "Parent's name" (placeholder "Only used if this parent has no account yet"), "Parent's email" (email; placeholder "Sends an invite if they don't have an account yet"; Edit pre-fills the pending invite email).
- **Studies & interests**: help "Separate multiple values with commas." -- "Subjects", "Career interests", "Preferred countries", "Preferred courses" (comma lists), "Interested in studying abroad" (Not recorded / Yes / No).
- Buttons: Add: **Add student** ("Saving…"). Edit: **Save changes** / **Cancel**. Footer: "Adding many students at once? Use bulk upload instead."
- Client validation: only native HTML (`required` on Full name, `type=email`, number range, maxLength). No custom client messages.
- Server validation (all 422 unless noted; the UI rewrites API field names to labels via `friendlyMessage`, `W:lib/schoolStudents.ts:116-124`, and focuses/marks the field):
  - `full_name is required` -> shown "Full name is required" (`A:api/schools.py:1544-1545`).
  - `grade_level must be an integer between 1 and 12` (`A:api/schools.py:575-580`).
  - `assigned_teacher_user_id must be an existing Teacher at your own school` (`:1555`).
  - `parent_email '<x>' belongs to an existing account that is not a Parent` (`:843`).
  - Master fields (`A:schemas.py:1567-1694`): text fields "must be at most N characters", "must not contain control or bidirectional-override characters"; gender "must be one of: …"; mobile "must be 7-20 characters of digits, spaces, +, -, ( or ) with at least 7 digits"; lists "must have at most 20 items", each item max 80 chars; duplicates (case-insensitive) silently dropped. Output e.g. "Student mobile must be 7-20 characters …".
  - **409** roll clash: `roll_number '<r>' is already used in this grade and section for this academic year` -> shown "Roll number <r> is already used …" (`A:api/schools.py:676,717-727`).
  - Not validated server-side (VERIFICATION REQUIRED -- likely 500): Full name > 160 chars (column String(160), no client maxLength); Grade/Class > 60 via API; malformed `date_of_birth` (`date.fromisoformat` unguarded, `A:api/schools.py:1567`).
- Success messages (`SchoolStudentsPanel.tsx:23-28,119,150,171`):
  - Add: "`<Full name>` added to the roster." + parent note: " Parent linked immediately (they already had an account)." | " Invite email sent to <email>." | " <email> already has a pending invite from another child -- they'll be linked to both once they accept."
  - Edit: "Student updated." + same parent note (shown under the roster table; edit card closes).
- Network failure: generic "Something went wrong." (fallback in `detailMessage`).

### "Link a parent to <name>" form
- Field "Parent's email" (email, required). Help: "Must already be an accepted Parent account at your own school." Buttons **Link parent** ("Linking…") / **Cancel**.
- Errors: 422 `parent_email must belong to an existing Parent account`; 422 "…belongs to an existing account that is not a Parent"; 409 `This parent is already linked to this student`.
- Success: "Parent linked to this student."
- Side effects: `SchoolParentLink` row; audit `school.parent_link`.

### Side effects (add/edit)
- Student code auto-generated (8 hex chars), academic year = current active year (`A:api/schools.py:1565,1570`).
- Parent email: existing Parent account -> linked immediately, no email; else `pending_parent_email` set and a Parent invite is created and emailed (7-day expiry), unless a pending Parent invite for that email at this school already exists ("invite_reused") (`A:api/schools.py:847-874`). On acceptance the new parent is linked to **every** student at that school naming that email (`A:api/schools.py:315-324`).
- Audit: `school.student_create` / `school.student_update` (changed field names only).
- In dev/test the API returns `development_invite_token` (not shown in UI).

Test data: 1 active + 1 inactive teacher at own school; an existing Parent account; an email that belongs to a non-parent (e.g. a teacher) to trigger the conflict; an active academic year; a student with a roll number to trigger 409. Screenshots: `coord-02-roster-list`, `coord-02-roster-empty`, `coord-02-add-student-form`, `coord-02-add-student-success-invite`, `coord-02-add-student-roll-conflict`, `coord-02-edit-student`, `coord-02-link-parent`, `coord-02-link-parent-error`.

---

## 3. Bulk roster upload — `/school/coordinator/students/bulk-upload`
- Not in sidebar. Reached from Dashboard "Go to bulk upload", roster empty state and roster footer links.
- Frontend: `W:app/school/coordinator/students/bulk-upload/page.tsx:10-22` (only calls `/auth/me` -- **no role check, so any signed-in user sees the page**), panel `W:components/SchoolBulkUploadPanel.tsx`.
- Backend: GET `/school/students/roster-template` `A:api/schools.py:1256-1268` (coordinator only); POST `/school/students/bulk-upload` `A:api/schools.py:1894-2013` (coordinator only; header `Idempotency-Key` **required**, else 422 "Idempotency-Key header is required"); GET `/school/roster-uploads/{batch_id}` `A:api/schools.py:2016-2024` (coordinator; 404 "Upload batch not found") -- **not used by the UI**.

### Screen
- Card "1. Download the template": text "Fill it in offline, then upload it below. Only the full name is required; a parent email invites that parent (or links them, if they already have an account)." Button **Download template (.csv)** (opens new tab; file `school-roster-template.csv`).
  - Expandable "**Column reference**" table (Column / Required / Format / Example) + note "Photos can't be uploaded in the CSV — add them from each student's page after the upload."
- Card "2. Upload your filled-in roster": field "Filled-in roster file" (file input, `accept=".csv"`, required). Button **Upload roster** ("Processing…").
  - Client error if no file: "Choose a filled-in roster file first."
- Result card "Upload result": "`A` of `T` row(s) accepted[, `R` rejected]. Rows that succeeded are kept even though others failed." Table Row / Result ("Added" | "Rejected") / Detail (reason, field names reworded to labels).

### Template columns (`A:api/schools.py:1849-1853`, documented `W:lib/schoolStudents.ts:126-144`), in order
`full_name` (required), `date_of_birth` (YYYY-MM-DD), `grade_or_class`, `assigned_teacher_email`, `parent_name`, `parent_email`, `grade_level` (1-12), `section`, `roll_number`, `gender` (female/male/other/prefer_not_to_say), `student_mobile`, `city`, `subjects` (`;`-separated), `career_interests` (`;`), `global_education_interest` (yes/no/true/false/1/0), `preferred_countries` (`;`), `preferred_courses` (`;`).
- Template contains one **example row** ("Jane Doe", Grade 5-A …). If left in, it is imported as a real student (VERIFICATION REQUIRED that users are warned -- the UI does not warn).
- Note: list separator in CSV is `;`, but in the on-screen form it is `,`.

### Row-level validation messages (each rejects only that row; `A:api/schools.py:1931-1999`)
- `full_name is required`
- `date_of_birth '<v>' is not a valid date (expected YYYY-MM-DD)`
- `assigned_teacher_email '<v>' is not an existing Teacher at your own school`
- `parent_email '<v>' belongs to an existing account that is not a Parent`
- `grade_level '<v>' must be an integer between 1 and 12`
- `global_education_interest must be yes or no`
- any Student Master field rule (same texts as §2)
- roll-number clash: `roll_number '<r>' is already used in this grade and section for this academic year`
- Row numbers count **data rows** (row 1 = first row after the header = spreadsheet line 2).

### Limits / formats
- Accepted: CSV, UTF-8 (BOM tolerated, undecodable bytes replaced). Server does **not** check file type, size or row count (no limit found). Unknown columns are ignored; a wrong header name (e.g. "Full Name") makes every row fail "full_name is required". Header-only file -> "0 of 0 rows accepted."
- `grade_or_class` length not validated server-side (>60 likely DB error/500 for the whole batch -- VERIFICATION REQUIRED).
- Idempotency: the UI sends a fresh key per click (`newIdempotencyKey()`); a repeated key replays the earlier batch result (403 "This upload batch belongs to a different institution" if another school's key).

### Side effects
- Student created per accepted row (code, active academic year). Parent link or invite email per row with `parent_email` (same rules as §2; one invite per new email). Audit `school.roster_bulk_upload` with totals; batch + per-row records stored (`SchoolRosterUploadBatch/Row`).

Test data: a CSV with a mix of good rows, a bad date, an unknown teacher email, a non-parent email, grade_level 13, duplicate roll numbers, a new parent email, an existing parent email. Screenshots: `coord-03-bulk-template-card`, `coord-03-bulk-column-reference`, `coord-03-bulk-upload-result-mixed`, `coord-03-bulk-no-file-error`.

---

## 4. Student profile & journey timeline — `/school/coordinator/students/[id]`
- Reached from roster "Profile & timeline", scorecard grid names on Reports, notification "has joined" links. Not in sidebar.
- Frontend: `W:app/school/coordinator/students/[id]/page.tsx:22-64` -- frontend role check: non-coordinator -> "Access unavailable" "School Coordinator role required". Load failure shows its own card "Access unavailable" + API message (e.g. "This student is at a different institution" / "Student not found") + button **Back to students**.
- Panel `W:components/SchoolStudentDetailPanel.tsx` with `showGradeHistory showTransfer canEditPhoto`.

### Backend endpoints
- GET `/school/students/{id}` `A:api/schools.py:1310-1313` (scope loader `_load_readable_student` `:1283-1307`).
- GET `/school/students/{id}/timeline` `A:api/schools.py:1430-1500`.
- GET `/school/students/{id}/grade-history` `A:api/schools.py:1503-1510`.
- GET `/school/students/{id}/transfer-history` `A:api/school_transfers.py:228-247`.
- GET `/school/transfer-destinations` `A:api/school_transfers.py:168-173` (coordinator).
- GET `/school/transfer-requests?status=pending&limit=100` `A:api/school_transfers.py:176-204`.
- POST `/school/students/{id}/transfer-requests` `A:api/school_transfers.py:250-288`.
- GET/PUT/DELETE `/school/students/{id}/photo` `A:api/school_student_profile.py:59-118` (PUT/DELETE coordinator-own-school only; GET any reader in scope).
- GET `/school/students/{id}/portfolio` (+ writes) `A:api/portfolio.py:121,185,221,270,286` and certificate routes `A:api/portfolio_certificates.py:45,85,105`.
- GET `/school/students/{id}/scorecard` `A:api/school_analytics.py:469-479` (coordinator/principal; other school -> 404).
- GET `/school/students/{id}/funding-records` `A:api/school_funding.py:128-146` (read only for coordinator).
- GET `/school/students/{id}/progress-report` (PDF) `A:api/school_reports.py:111-123`.

### Screen elements
1. Header card: "<Full name> (<code>)". Photo block (`W:components/SchoolStudentPhoto.tsx`): photo or initials placeholder. Coordinator controls: file input labelled "Upload a photo (JPEG or PNG, up to 2 MB)" / "Replace photo (JPEG or PNG, up to 2 MB)", **Remove photo** -> **Confirm remove** / **Cancel**.
   - Client errors: "Photo must be a JPEG or PNG image", "Photo must be at most 2 MB". Server: 422 "photo file is empty", 413 "photo must be at most 2 MB", 415 "photo must be a JPEG or PNG image", 422 "photo could not be read as a valid JPEG or PNG image", 500 "Could not store the photo; please try again". Success "Photo saved." / "Photo removed."; remove failure "Could not remove the photo; please try again."
   - Metadata stripped from uploads; audit `school.student_photo_set` / `school.student_photo_remove`.
   - Profile list (read-only; empty = "Not recorded"): Grade/Class, Date of birth, Gender, Section, Roll number, Student mobile, City, Subjects, Career interests, Interested in studying abroad, Preferred countries, Preferred courses. **Not shown here: assigned teacher, parent(s), grade level, academic year.**
   - If a pending outgoing transfer exists: badge "Transfer requested" to <school>.
   - Buttons **Open 360° view**, **Back to students**.
   - Edits to profile fields are only possible from the roster "Edit" (comment `page.tsx:17-18`).
2. Collapsed disclosure "**Request a transfer**" (see §6 for form).
3. "**Grade history**" card (`W:components/SchoolGradeHistory.tsx`): entries newest first with badge Promoted/Held back, "Moved from X to Y" / "Kept in Y", "Academic year: A to B", "Previous section …, roll number …". Empty "No promotions recorded yet."; failure "Grade history is unavailable right now."
4. "**Transfer history**" card -- rendered only if the student has approved transfers: "Moved from <A> to <B>" with badge "Transferred"; failure "Transfer history is unavailable right now."
5. "**Journey timeline**" (`W:components/SchoolStudentTimeline.tsx`): chronological (oldest first) events with category badge (Profile, Career, Psychometric, Academic, Activity, Test prep, Foreign language, Global education, Soft skills, Digital skills). Event titles (`A:api/schools.py:1448-1499`): "Student profile created" ("Added to <grade>"), career record titles, "Psychometric assessment assigned", "Psychometric report uploaded", "Academic result published" (published only), "Attended <activity>" (present only), "<IELTS|SAT> preparation started" / "… result recorded", "<Language> classes started" / "… certification earned", "Overseas application started: <University>", "Visa status: <status>", skills events. Empty "No journey events recorded yet."; failure "Timeline is unavailable right now."
6. "**Digital Portfolio**" (`PortfolioPanel`) -- coordinator is a write role (`A:api/portfolio.py:53`); tier-gated (Gold for entries, Platinum for internship tracking). Failure "Portfolio is unavailable right now." Detailed portfolio behaviour: VERIFICATION REQUIRED / likely covered by the portfolio/360 agent.
7. "**Progress report**" card: text "A PDF of this student's profile and progress to date." Button **Download progress report (PDF)** ("Preparing PDF…"), hint "PDFs are not screen-reader friendly. The same information is in this student's 360° view." Success "Report downloaded."; errors "Your session has expired. Sign in again." / "Something went wrong on our side. Please try again." / API detail. Audit `school.progress_report_download` (committed before the file is sent).
8. "**Progress scorecard**" (`W:components/StudentScorecard.tsx`): "Portfolio N% complete"; table Area/Status with states Completed / In progress / Not started / Not in plan (service not in tier) / Not tracked yet. Areas: Career Awareness, Psychometric, Career Counselling, Soft Skills, Foreign Language, Digital Portfolio, IELTS/SAT, University Shortlisting, Scholarship (always Not tracked yet), Application, Visa, Internship (`A:api/school_analytics.py:388-403`). Failure: `SectionUnavailable` "Progress scorecard".
9. "**Funding support**" (read-only, `W:components/FundingRecordsCard.tsx`): Support type, Stage "since <date>", Provider, Amount, Reason closed, Notes, Updated by. Empty "No funding support cases for this student."; failure "Funding support cases couldn't be loaded. Reload the page to try again." Only cases opened at the student's current school are shown to staff.

Test data: student with photo, grade history (after a promotion), approved transfer, timeline events across categories, portfolio entries, funding case, published results. Screenshots: `coord-04-student-header`, `coord-04-photo-upload`, `coord-04-grade-history`, `coord-04-timeline`, `coord-04-scorecard`, `coord-04-progress-report-download`, `coord-04-access-other-school`.

---

## 5. Student 360° view — `/school/coordinator/students/[id]/360`
- From student page **Open 360° view**. Frontend `W:app/school/coordinator/students/[id]/360/page.tsx:5-9`, `W:components/Student360Route.tsx:18-32`. **No frontend role check** (API scopes it). Back link "Back to student".
- Backend GET `/school/students/{id}/360-view` `A:api/student_360.py:141`, projection `:62-138`.
- Coordinator (a `SCHOOL_ROLES` member) gets all **16 tabs unrestricted**: overview, personal_details, academic_records (incl. grade history), attendance, examination_results, career_guidance, psychometric_assessment, skills, foreign_languages, english_testing, activities (attended + upcoming), certificates, documents, teacher_remarks, parent_communication (always empty, `{}`), edusphere_programs.
- Editable: **nothing** for the coordinator -- `can_edit_career_goal` is true only for career_counselor (`:138`, PATCH career-goal `:153-160` is counselor-only). Details: covered by the 360 agent.

---

## 6. Transfers — `/school/coordinator/transfers` (+ outgoing request on student page)
- Sidebar: **Transfers**. Frontend `W:app/school/coordinator/transfers/page.tsx:13-28` (role-checked), panel `W:components/SchoolTransfersPanel.tsx`, incoming form `W:components/SchoolIncomingTransferForm.tsx`, outgoing form `W:components/SchoolTransferRequestForm.tsx`, labels `W:lib/transfers.ts`.
- All coordinator transfer routes use `_require_coordinator_user` (403 "School Coordinator role required").

### Transfer requests list (card "Transfer requests")
- Intro: "Requests your school has filed. An admin reviews each one; nothing changes until it is approved."
- Filter "Status": Pending review (default) / All / Approved / Rejected / Cancelled. Server pagination 25/page, newest first; "Showing X of Y"; **Load more**. No search, no sort control.
- Row: student name, or "Student ID <code>" for an incoming request not yet approved (then "Student details are shown once approved."); "<code> · to <school>" / "from <school>"; "Admin note: …" if rejected with note; status badge (text); filed date (IST); **Cancel** on pending rows ("Cancelling…").
- Empty (pending): "No pending requests." + "To move a student out, open their page and choose “Request a transfer”. To bring a student in, use the form below." + **Go to the student roster**. Empty (other): "No transfer requests yet." / "No <status> requests." + **Show pending**.
- Errors: "Your session has expired. " + "Sign in again"; "Could not load transfer requests." + **Try again**; cancel network: "The cancel did not complete. Check your connection and try again."; "The cancel could not be confirmed. Reload the list to see where the request stands."
- Cancel success: "Request cancelled." Server: 403 "Not permitted for this transfer request" (unknown/other school, audited), 409 "This transfer request has already been decided". No confirmation dialog.
- Endpoint: GET `/school/transfer-requests` `A:api/school_transfers.py:176-204`; POST `/school/transfer-requests/{id}/cancel` `:207-225`.

### "Request a student from another school" (incoming) form
- Text: "Ask for a student to join your school using their Student ID. An admin reviews every request; nothing changes until it is approved."
- Fields: "Student ID" (max 8, hint "For example A3F9C21B."), "Reason (optional)" (textarea, max 500). Button **Request student** ("Sending request…").
- Client validation: "Enter all 8 characters of the Student ID (digits 0-9 and letters A-F)."
- Success (always the same, deliberately): "If that Student ID belongs to a student at another school, your request has been sent to an admin for review." (HTTP 202 `{accepted:true}` for every well-formed code -- unknown code, own-school code and duplicates create nothing but get the same answer).
- Server: 422 "student_code must be 8 characters, 0-9 and A-F"; 429 "Too many transfer requests; try again in N seconds" (30 filings/hour per coordinator); 409 "Too many open transfer requests; wait for a decision or cancel one" (50 open per school) (`A:api/school_transfers.py:58-59,104-132`). Network: "The request did not complete. Check your connection and try again; your entry is kept."
- Endpoint: POST `/school/transfer-requests/incoming` `A:api/school_transfers.py:291-330`.

### Outgoing request (on student page, disclosure "Request a transfer")
- Field "Destination school" (select "Select a school" + every other school, sorted by name), "Reason (optional)" (max 500). Button **Request transfer** ("Sending request…"). No confirm step.
- Client: "Choose a school." States: "Transfers are unavailable right now." (destinations failed); "No other partner schools are available."; pending: "Transfer to <school> requested <date>. Waiting for admin review."
- Success: "Transfer request sent for review. An admin decides; nothing changes until it is approved."
- Server: 403 "This student is not at your institution"; 422 "Choose a different school"; 422 "Unknown destination school"; 409 "A transfer request is already pending for this student"; 429/409 limits as above; reason > 500 chars / control chars -> 422 list message ("must be 500 characters or fewer" -- VERIFICATION REQUIRED of FREE_TEXT_MAX value, not read). Expired session: "Your session has expired. Your entry is kept. " + Sign in again. Unconfirmed reply: "The reply could not be confirmed as a filed request. Your entry is kept; repeating it is safe (a student can have only one pending request)."

### Side effects
- Filing / denial / cancel audited (`school.transfer_request_filed|denied|cancelled`).
- Decision is by Overseas Admin (outside this area). On **approve** (`A:api/school_transfers.py:387-449,452-485`): student moves school; assigned teacher, pending parent email, section and roll number cleared; draft/verified results withdrawn; parent links kept. Notifications (in-app only for coordinators): losing coordinator(s) "Transfer approved: <name> moved to <school>" -> `/school/coordinator/transfers`; gaining coordinator(s) "<name> has joined <school>" -> `/school/coordinator/students/{id}`; linked parents notified (in-app + email/WhatsApp/SMS deliveries). On **reject**: requester gets "Transfer of <name> to <school> was not approved" or, for incoming, "Transfer request for Student ID <code> was not approved", body "An admin reviewed the request and did not approve it. Nothing has changed." (`:540-556`).

Test data: two schools with coordinators; a student at the other school (know its Student ID); requests in each status incl. a rejected one with admin note. Screenshots: `coord-06-transfers-pending-list`, `coord-06-transfers-empty`, `coord-06-transfers-filter-all`, `coord-06-incoming-request-form`, `coord-06-incoming-neutral-success`, `coord-06-outgoing-request-form`, `coord-06-outgoing-pending-state`.

---

## 7. Promotion (academic-year rollover) — `/school/coordinator/promotion`
- Sidebar: **Promotion**. Frontend `W:app/school/coordinator/promotion/page.tsx:15-34` (role-checked), `W:components/SchoolPromotionPanel.tsx`, `W:components/SchoolPromotionRow.tsx`.
- Backend: GET `/school/students`; GET `/school/academic-years/active` `A:api/schools.py:1271-1280` (school-domain roles); POST `/school/students/promotions` `A:api/schools.py:1684-1767` (coordinator dependency, body max 500 items, no duplicates).

### Screen
- No active year: "Promote students" / "No active academic year" / "Promotion becomes available once an Overseas Admin activates the new academic year."
- Intro: "Move students into <Year>, the active academic year. **Promote** advances the grade by one; **Hold back** keeps the grade and records the new year."
- Controls: "Grade level" filter (All grades / Grade N for each level present / Grade level not set), "Select all shown" checkbox, "Showing X of Y students". Changing the filter clears the selection. No search, no pagination.
- Rows: checkbox + name, "<code> · <grade label or 'Grade not set'> (level N)"; "Action" (Promote / Hold back); "New label (optional)" (placeholder "automatic", max 60, only for Promote); Status/hints. Rows already in the active year are locked: "Already in <Year>"; after success "Promoted"/"Held back" + "Now in <Year>".
- Hints: "Grade level is not set. Set it on the roster before promoting."; "Grade 12 is the highest grade and cannot be promoted. Choose Hold back."
- Bar: "<n> selected" (+ ". Select at most 500 at a time."), **Review changes (n)** -> confirm: "Promote X and hold back Y into <Year>? This changes the current grade of each selected student." **Confirm promotion** ("Promoting…") / **Cancel** (Esc also cancels).
- Result: "Done for <Year>: a promoted, b held back, c not changed, d skipped." Failed rows stay selected with reason: "Already in the active academic year." / "Grade level is not set. Set it on the roster before promoting." / "Grade 12 is the highest grade; graduation is not supported yet." / "This student's grade label can't be advanced automatically. Type the new grade in \"New label\", then try again."
- Errors: 403 "One or more students are not at your institution" (whole request refused, audited `school.student_promotion_denied`); 409 "No active academic year. Ask an Overseas Admin to activate one."; 409 "Another promotion is in progress; retry"; 409 "A concurrent promotion was detected; reload and retry"; 422 "student_id … appears more than once" / "grade_or_class is only allowed with action 'promote'"; network: "The request did not complete. Your selection is kept. Refresh to check the current state, then try again; repeating it is safe."; unreadable: "The server's response could not be read, …"; 401: "Your session has expired. Your selection is kept. " + Sign in again.
- Rules (`A:api/schools.py:622-643`): Promote = grade_level+1 and the number inside the Grade/Class text advanced ("Grade 8-A" -> "Grade 9-A"); label must contain the same number as grade_level, else row fails; resulting label <= 60 chars.
- Side effects: grade-history row per moved student; academic year set to active; **roll number cleared** for every promoted/held-back student; audit `school.student_promotion` (counts). No notifications.

Test data: active academic year (Overseas Admin), students in previous year with grade levels 8-12, one with no grade level, one with label not matching level (e.g. level 9, label "Class X"), one already in the active year. Screenshots: `coord-07-promotion-no-active-year`, `coord-07-promotion-list`, `coord-07-promotion-confirm`, `coord-07-promotion-result-mixed`.

---

## 8. Activities (schedule + attendance) — `/school/coordinator/activities`
- Sidebar: **Activities**; also Dashboard "Go to activities". Frontend `W:app/school/coordinator/activities/page.tsx:12-30` (no frontend role check; API 403 for others), panel `W:components/SchoolActivitiesPanel.tsx`.
- Backend: GET `/school/activities` `A:api/schools.py:1770-1778` (coordinator); POST `/school/activities` `:1781-1808`; POST `/school/activities/{id}/attendance` `:1811-1837`; GET `/school/students` for the attendance list.

### Activities table (card "Activities")
- Columns: Title, When (IST), Actions. Newest scheduled first. Empty "Nothing scheduled yet." No search/filter/pagination; **no edit, cancel or delete of an activity**; activity type not displayed.
- Actions: **Mark attendance**; **Give feedback** / **View feedback** (link to `/school/coordinator/feedback?activity=<id>`) shown only for typed activities whose time has passed, or that already have feedback.

### "Schedule an activity" form
- "Title" (required), "Date & time" (datetime-local, required), "Entitlement category (optional)": None / Career seminar / Student career awareness session / Parent orientation / Monthly campus visit. Button **Schedule activity** ("Scheduling…").
- Server: 422 "title and scheduled_at are required"; 422 "activity_type must be one of career_seminar, career_awareness_session, parent_orientation, campus_visit"; **403 tier messages** (§0.4) -- typed activity needs its service (campus visit = Platinum "Monthly campus visits"; others Bronze); untyped needs any valid, unexpired tier. Past dates are accepted (no check). Title > 200 chars not validated (VERIFICATION REQUIRED).
- Success: "<Title> scheduled."
- Side effects: audit `school.activity_create`; **every active linked Parent at the school** gets notification "Upcoming session: <title>" / "<title> is scheduled for <dd Mon YYYY, HH:MM>." (in-app + queued email/WhatsApp/SMS) with link `/school/parent/dashboard` (`A:api/schools.py:1802-1806`). Typed activities count toward Entitlements usage.

### "Mark attendance" card
- Lists **every roster student** as a checkbox, **all pre-ticked as present** (it does not load previously saved attendance). Buttons **Save attendance** ("Saving…") / **Cancel**. Empty: "No students on your roster yet."
- Server: 404 "Activity not found"; tier 403 (grandfathered for activities created before a downgrade); 422 "records must be a non-empty list of {student_id, present}"; 422 "One or more students are not on your own institution's roster".
- Success: "Attendance recorded for N student(s)." (shown under the schedule form). Re-saving overwrites. Audit `school.attendance_mark`.

Test data: tier set (try Bronze school to see campus-visit 403; expired tier; no tier), linked parents, past typed activity, future activity. Screenshots: `coord-08-activities-list`, `coord-08-schedule-form`, `coord-08-schedule-tier-denied`, `coord-08-mark-attendance`, `coord-08-attendance-saved`.

---

## 9. Activity feedback — `/school/coordinator/feedback`
- Sidebar: **Feedback**; also per-activity links from Activities (`?activity=<uuid>`), filter in URL `?status=all|awaiting|submitted`.
- Frontend `W:app/school/coordinator/feedback/page.tsx:16-36` (role-checked; principal has own read-only page), panel `W:components/SchoolActivityFeedbackPanel.tsx`, form `W:components/ActivityFeedbackForm.tsx`, labels `W:lib/activityFeedback.ts`. Loading skeleton `feedback/loading.tsx`.
- Backend: GET `/school/activity-feedback` `A:api/school_feedback.py:113-…` (coordinator/principal); POST `/school/activities/{id}/feedback` `A:api/school_feedback.py:69-102` (coordinator).

### Screen
- Heading "Activity feedback", text "Rate each completed Edusphere activity once. Edusphere uses it to improve the next session."
- "Show" filter: All / Awaiting feedback / Submitted. List lists only **typed activities already held**; 25 per page, **Load more**, "Showing X of Y". Row: title, "<type label> · <date time> · <present> of <marked> present | Not marked", badge "Submitted"/"Awaiting feedback", **Give feedback**, expandable "View feedback".
- Focused view (`?activity=`): **Show all activities** link; empty "This activity is not open for feedback." + "Feedback opens once a career seminar, career awareness session, parent orientation or campus visit has taken place."
- Empty: "No completed Edusphere activities yet." (+ "Feedback opens after …" + **Go to Activities**) / "Nothing awaiting feedback." / "No feedback submitted yet."
- Form "Feedback: <title>": "Overall rating" and "School satisfaction" (radios 1–5: "1 – Poor", "2 – Fair", "3 – Good", "4 – Very good", "5 – Excellent", required), "Trainer / Counsellor (optional)" (max 200, hint "Up to 200 characters."), "Feedback" (required, max 5000, hint "Describe the session. Please don't include students' personal details.", counter "n / 5000 characters[ — limit reached]"), "Suggestions (optional)" (max 5000). Buttons **Submit feedback** ("Saving…") / **Cancel** (confirm "Discard your unsent feedback?" if dirty; leaving page also warns).
- Client: "Feedback: Must not be blank". Server: 404 "Activity not found"; 422 "Feedback is only collected for Edusphere activities"; 422 "Feedback opens once the activity has taken place"; 409 "Feedback has already been submitted for this activity" -> UI: "Feedback had already been submitted for this activity; your text was not saved. You can copy it below."; 422 field list worded "<Field label>: <reason>"; 401 "Your session has expired. Your entry is kept; sign in again in a new tab, then submit."
- Success: "Feedback saved for <title>." Feedback is **immutable** after submit (no edit). Audit `school.activity_feedback_submit`. No tier check on feedback.

Test data: past typed activity with/without attendance, past untyped activity (never listed), future typed activity. Screenshots: `coord-09-feedback-list-awaiting`, `coord-09-feedback-form`, `coord-09-feedback-submitted-view`, `coord-09-feedback-duplicate`.

---

## 10. Team (invite Principal/Teacher/Parent; activate/deactivate) — `/school/coordinator/team`
- Sidebar: **Team**. Frontend `W:app/school/coordinator/team/page.tsx:15-28` (no frontend role check; API 403), panel `W:components/SchoolTeamPanel.tsx`.
- Backend: GET `/school/team` `A:api/schools.py:218-232`; POST `/school/team/invites` `:176-193`; PATCH `/school/team/accounts/{user_id}` `:235-272`; invitee accepts at `/school/invite/[token]/accept` -> POST `/school/invites/{token}/accept` `:275-326` (public, token-based).

### "Your team" table
- Columns Name, Email, Role (Coordinator/Principal/Teacher/Parent), Status ("Active" | badge "Inactive"), Action (**Deactivate** / **Reactivate**, "Saving…"; coordinator rows show "—"). No search/filter/sort/pagination; no confirmation before deactivate.
- Membership: principal/teacher/coordinator by `profile.school_id`; **parents only if linked to a student at this school** (or legacy profile) (`A:api/schools.py:210-215`).
- Empty (only you): "It's just you so far. Invite your Principal, teachers, or parents to give them their own login."
- Row messages: "<name> deactivated." / "<name> reactivated."; errors 422 "active (boolean) is required", 404 "Account not found", 403 "Can only activate/deactivate Principal, Teacher, or Parent accounts", 403 "This account is not at your institution". Audit `school.team_account_update`. Deactivated users cannot sign in (`A:api/auth.py:99`); a deactivated teacher keeps existing student assignments but disappears from the Add-student picker.

### "Pending invites" table (only when any): Name, Email, Role, Expires (IST date). **No resend, revoke or copy-link actions.**

### "Invite a team member" form
- "Role" (select: Select role / Principal / Teacher / Parent, required), "Full name" (required), "Email" (email, required). Button **Send invite** ("Sending…").
- Server: 422 "role must be one of ['school_parent', 'school_principal', 'school_teacher']"; 422 "email and full_name are required"; 409 "Email already exists" (any existing user).
- Success: "Invite sent to <email>. It's valid for 7 days." plus, if email not sent: " (email sending isn't configured yet -- share the link manually)" or " (the email could not be sent -- share the link manually)".
- Side effects: `SchoolAccountInvite` (pending, 7-day expiry, token hashed); email subject "You're invited to join <school> on EduSphere", From "<coordinator> via EduSphere", Reply-To coordinator (`A:services/mailer.py:97-121`); generic webhook notification; audit `school.invite_create` (with SMTP status).
- Acceptance: invitee chooses password (min 10; "Password must be at least 10 characters"); 409 "This invite has already been used, expired, or was revoked"; 409 "Email already exists". Creates account (non-parent gets `school_id`; parent gets none) and signs them in; parent invites created from the roster link all students naming that email.

### Teacher-student assignment / parent-child links
- There is **no** separate assignment screen. Teacher assignment = "Assigned Teacher" select on roster Add/Edit (§2) or `assigned_teacher_email` in the CSV (§3). Parent-child link = "Parent's email" on Add/Edit/CSV or the roster "Link parent" action (§2). There is no UI to **unlink** a parent or view existing parent links.

Test data: pending invites of each role; an email already registered; inactive teacher; parent linked to a student. Screenshots: `coord-10-team-list`, `coord-10-team-just-you`, `coord-10-invite-form`, `coord-10-invite-sent`, `coord-10-pending-invites`, `coord-10-deactivate-teacher`, `coord-10-invite-accept-page`.

---

## 11. Reports — `/school/coordinator/reports`
- Sidebar: **Reports**; Dashboard "Go to reports". Frontend `W:app/school/coordinator/reports/page.tsx:30-56` (role-checked). Query params: `grade` (8-12), `offset`, `at_risk_below`, `top_from`.
- Backend: GET `/school/reports` `A:api/schools.py:908-919` (coordinator/principal) -- returns the same payload as `/school/dashboard`; GET `/school/reports/school-summary` (PDF) `A:api/school_reports.py:90-98`; GET `/school/analytics/grade-performance` `A:api/school_analytics.py:266-272`; GET `/school/analytics/student-development` `:311-…` (422 "at_risk_below must be less than top_from"); GET `/school/analytics/scorecards` `:448-466` (25/page).

### Screen, top to bottom
1. "**Download reports**": "A PDF of your school's summary figures and grade-by-grade table, as of today." Button **Download school report (PDF)** -> `school-report.pdf`; hint "PDFs are not screen-reader friendly. The same figures are on your dashboard and in the grade-wise comparison on this page." No audit row (log only).
2. Metric tiles: Students, Teachers, Parents, Pending invites.
3. "**Students by grade**" bar chart by Grade/Class text ("Unspecified" for blank); "x of y students have an assigned Teacher." Empty "No students on the roster yet."
4. "**Service delivery completion**" ("Share of students with at least one record in each area."): rings Career guidance (any career record), Psychometric completed, Results published; "n more assessment(s) assigned, awaiting completion."
5. "**Activities & attendance**": Total activities, Upcoming, Completed (= past, not attendance-based), Attendance rate (present/marked, "-" if none).
6. "**Grade-wise comparison**" table (grades 8-12, "Other grades", "No grade"): Students row + metrics Career readiness*, Assessment completion, Counselling completion, Skills development*, Global education interest*, Application readiness*, University applications, Admissions; cells "count (pct%)"; *estimates show "Estimate: <definition>" (`A:api/school_analytics.py:253-262`).
7. "**Student development**": headcounts; table Activity/Completed/Pending (Career Guidance, Psychometric Test, Foreign Language, English Testing, University Guidance); "Academic performance" by grade/subject/term from published results ("No published results yet."); threshold form "At risk below (%)" (default 40) / "Top performer from (%)" (default 85) / **Update thresholds**; client messages "Thresholds must be between 0 and 100. Showing the defaults." / "At-risk must be below the top-performer threshold. Showing the defaults."; lists "At-risk students (n)" / "Top performers (n)" (max 50 named, "Showing the first N.").
8. "**Student progress scorecards**": Grade filter (All grades / Grade 8-12) + **Show**; table Student (link to student page) × 12 areas with state badges; pager "← Previous" / "x–y of N" / "Next →"; empties "No students on the roster yet." / "No students match this grade." / "This page is past the end of the list."
- Any analytics section that fails shows `SectionUnavailable` with its title.
Screenshots: `coord-11-reports-top`, `coord-11-reports-download-pdf`, `coord-11-grade-comparison`, `coord-11-student-development`, `coord-11-scorecards-grid`.

---

## 12. Global Education — `/school/coordinator/global-education`
- Sidebar: **Global Education**. Frontend `W:app/school/coordinator/global-education/page.tsx` -> `W:components/GlobalEducationPage.tsx:23-52` (role-checked "School Coordinator role required"), funnel `GlobalEducationFunnel.tsx`, table `GlobalEducationStudentTable.tsx`.
- Backend GET `/school/global-education/pipeline` `A:api/school_global_education.py:74-120` (coordinator/principal; read-only; grade 8-12; 25/page).
- Screen: H1 "Global education". Card "Pipeline": "N students[ in Grade g] · M students on the global education pathway"; "High-level stage only. Application details are handled by EduSphere's application team."; funnel Global education pathway → Profile evaluation → University shortlisted → Offer received → Visa → Admitted (counts + decorative bars). "Not tracked yet" tiles: Applications started, Applications submitted, Deposit, Scholarships, Top 100 universities, Alumni (each with a note).
- Card "Students": Grade filter + **Show**; table Student, Student ID, Grade, Furthest stage, Visa (Checklist / Documentation / Interview preparation / Tracking / Decision / In progress / —), Applications (count). Names are plain text (no links). Pager. Empties: "No students from this school are on the global education pathway yet. Students appear here once an EduSphere counselor links their application." / "No students in this grade are on the global education pathway." Failure: "Global education pipeline" unavailable section.
- Coordinator cannot link applications (only Overseas Admin/Counselor). Test data: overseas applications linked to school students at several statuses + visa cases. Screenshots: `coord-12-global-ed-funnel`, `coord-12-global-ed-students`, `coord-12-global-ed-empty`.

---

## 13. Entitlements — `/school/coordinator/entitlements`
- Sidebar: **Entitlements**. Frontend `W:app/school/coordinator/entitlements/page.tsx:11-24` (no frontend role check), `W:components/SchoolEntitlementsPanel.tsx`.
- Backend GET `/school/entitlements` `A:api/schools.py:1224-1245` (coordinator/principal), usage `service_usage` `:1152-1221`.
- Screen: "Partnership entitlements". No tier: "No partnership tier has been set for your school yet. Contact your EduSphere Overseas Admin." Else "Plan: <Tier> Partner — valid until <date>"; table Service / Included (always ✓) / Used (number; "Assigned"/"Not assigned" for Dedicated counselor; "Not tracked" for Alumni network, Parent help desk). Only included services are listed; services of higher tiers are not shown at all (no "upgrade" view).
- **Expired** tier still lists services with no "expired" warning on this page (only the date). VERIFICATION REQUIRED whether intended.
- Usage definitions: counts of students/records per service (e.g. activities by type, psychometric records, counselling notes, test-prep by type, language records, applications, internships, visa cases, funding cases, skills, portfolios).
- Tier change notifications go to the school's coordinator(s) and principal(s): upgrade "Your partnership is now <Tier>" / "<school> has moved from A to B. Newly available: …"; downgrade "Your partnership changed from A to B" / "These services are no longer available for new work: … Work already started for them can still be completed." link `/school/coordinator/entitlements` (`A:api/admin.py:1453-1491`).
Screenshots: `coord-13-entitlements-platinum`, `coord-13-entitlements-no-tier`.

---

## 14. Notifications — `/school/coordinator/notifications`
- Sidebar: **Notifications**. Frontend `W:app/school/coordinator/notifications/page.tsx:10-30` (role-checked), list `W:components/SchoolNotificationList.tsx`.
- Backend GET `/workflows/notifications` (own, newest 100, no pagination) `A:api/workflows.py:2633-2636`; PATCH `/workflows/notifications/{id}/read` `:2646-2653` (404 "Notification not found").
- Screen: H1 "Notifications"; rows: title + text badge "new" if unread, body, date-time (IST), **Open** (if link; marks read). Empty: "No notifications yet. You will be told here when a transfer request is decided, a student joins your school, or your school's partnership changes."
- No "mark all read", no filter. Notices a coordinator receives: transfer approved / joined / not approved (§6), tier change (§13). VERIFICATION REQUIRED: any other source targeting coordinators (none found in this sweep).
Screenshots: `coord-14-notifications-list`, `coord-14-notifications-empty`.

---

## 15. Endpoint inventory used by the coordinator portal (≈49)
GET /auth/me; GET /school/dashboard; GET /school/results; GET /school/career-records; GET /school/psychometric-records; GET /school/students; POST /school/students; PATCH /school/students/{id}; POST /school/students/{id}/parents; GET /school/team; POST /school/team/invites; PATCH /school/team/accounts/{id}; POST /school/invites/{token}/accept; GET /school/students/roster-template; POST /school/students/bulk-upload; GET /school/roster-uploads/{id} (unused by UI); GET /school/students/{id}; GET …/timeline; GET …/grade-history; GET …/transfer-history; GET/PUT/DELETE …/photo; GET …/portfolio (+ POST/PATCH/DELETE entries, PATCH personal-statement, certificate PUT/GET/DELETE); GET …/scorecard; GET …/funding-records; GET …/progress-report; GET …/360-view; GET /school/transfer-destinations; GET /school/transfer-requests; POST /school/students/{id}/transfer-requests; POST /school/transfer-requests/incoming; POST /school/transfer-requests/{id}/cancel; GET /school/academic-years/active; POST /school/students/promotions; GET/POST /school/activities; POST /school/activities/{id}/attendance; GET /school/activity-feedback; POST /school/activities/{id}/feedback; GET /school/reports; GET /school/reports/school-summary; GET /school/analytics/grade-performance|student-development|scorecards; GET /school/global-education/pipeline; GET /school/entitlements; GET /workflows/notifications; PATCH /workflows/notifications/{id}/read.

Routes: 14 coordinator page routes (dashboard, students, students/bulk-upload, students/[id], students/[id]/360, promotion, transfers, activities, feedback, team, reports, global-education, entitlements, notifications) + invite-accept page for invitees.

---

## 16. As-built oddities a product owner should know (not fixed)
1. **Inconsistent frontend role guards.** Dashboard, Students, Bulk upload, Activities, Team, Entitlements, Student 360 have no `user.role` check. A Principal opening `/school/coordinator/dashboard` or `/entitlements` sees real data inside a "School Coordinator" shell; on `/students` a Principal/Teacher/Parent sees the roster with Add/Edit/Link buttons that only fail on submit; `/students/bulk-upload` renders for **any** signed-in user.
2. **`/students/new` does not exist** though docs list SCR-SCH-004; it falls into the `[id]` route and shows an "Access unavailable" card with a probably unreadable message.
3. `/school/reports` returns the dashboard payload; the original report code after `return` in `A:api/schools.py:921-975` is dead code.
4. Roster has no search/filter/sort/pagination, no teacher column, no delete/archive; Parent column shows only *pending* invites, never linked parents; there is no way to see or remove existing parent links.
5. Team list hides a parent who accepted a **Team-page** invite (no student link) -- they only appear after being linked from the roster. The Link-parent help says "accepted Parent account at your own school", but the API accepts any Parent account at any school.
6. No resend/revoke of pending invites; success text says "share the link manually" but the UI never shows the link. Duplicate pending invites for the same email are possible from the Team page (only existing *accounts* are blocked).
7. Activities cannot be edited, cancelled or deleted; activity type is not displayed in the list; past dates can be scheduled.
8. Attendance card always opens with **everyone ticked present**, ignoring saved attendance; saving overwrites prior marks.
9. Parent "Upcoming session" notification formats the time from the UTC value (`strftime` on `scheduled_at`), so it may show UTC, not IST (VERIFICATION REQUIRED in a delivered notice).
10. Dashboard "Applications in Progress" and "Offers Received" count **applications**, while neighbouring tiles count **students**. Reports "Career guidance" ring counts any career record, while the dashboard "Career Guidance Completed" counts completed guidance sessions only.
11. Promotion clears every moved student's roll number (by design, but silent to the user).
12. Bulk upload: no file-size/row cap, no server file-type check, template's example row is importable, CSV lists use `;` while the form uses `,`; row numbers exclude the header.
13. Server-side length checks missing for Full name (160), Grade/Class (60) via API/CSV, activity title (200) -> probable 500 instead of a message (VERIFICATION REQUIRED).
14. Tier gating is enforced only server-side; the UI never pre-hides gated options (e.g. "Monthly campus visit" is selectable on Bronze). Entitlements page does not warn about an expired partnership.
15. Student profile page shows no assigned teacher, no parents, no grade level/academic year; editing requires going back to the roster.
16. Sidebar highlights nothing on sub-pages (exact-match only); school Notifications has no unread badge.
17. Error-card links always point to `/overseas/login` ("Sign in again") regardless of how the coordinator signed in.

## 17. VERIFICATION REQUIRED (cannot be confirmed from code)
- Exact login URL and welcome-link screens for a newly provisioned coordinator.
- Rendered text of `/school/coordinator/students/new` (list `detail` stringification).
- Behaviour/HTTP status for over-length full name / grade text / activity title, and malformed DOB via API.
- Delivered email/WhatsApp content and timezone of parent "Upcoming session" notices; whether SMTP is configured in the target environment (affects invite success text).
- `FREE_TEXT_MAX` value for transfer reason (UI caps at 500; server constant not read).
- Portfolio panel behaviour for the coordinator (write role, tier-gated) -- not inspected in depth here.
- Whether any other notification types reach coordinators.

## 18. Required test data (summary)
- Two partner schools (A: Platinum valid; B: Bronze or expired) each with a coordinator; one school with no tier.
- Active academic year + students in the previous year at grade levels 8-12, one without grade level, one with mismatched label, one already in active year.
- Teachers (one inactive), principal, parents (one linked to 2 children), one non-parent account email for conflicts.
- Students with photo, roll numbers/sections, published results, career/psych/test-prep/language records, portfolio entries, funding case, overseas applications at several stages + visa case.
- Activities: future typed, past typed with attendance, past untyped; feedback submitted for one.
- Transfer requests in each status (incl. rejected with note) and a known Student ID at school B.
- Notifications: transfer approved/rejected/joined + tier change.
- CSV fixture with mixed valid/invalid rows.
