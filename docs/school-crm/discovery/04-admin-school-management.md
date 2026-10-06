# School CRM: Overseas Admin and Super Admin screens that manage schools (source discovery)

> **Evidence appendix** for `docs/school-crm/documentation-analysis.md` — raw read-only source discovery (master planning session S1, 2026-10-05, code `main` @ `ce1f07c2`). Field-level detail for module sessions. Not browser-verified; where this file and the browser disagree, the browser wins and this file is annotated, not silently trusted.

Code baseline: `main` @ ce1f07c2 (branch docs/school-crm-user-guide). Read-only discovery. All paths are relative to the repo root.
Where this says "VERIFICATION REQUIRED", the behaviour was not run in a browser. Code alone could not settle it.

---

## 0. How these screens are wired (shared mechanics)

### 0.1 Sidebar (Overseas Admin)
`apps/web/lib/navigation.ts:118`. The `"overseas/admin"` nav comes from slugs, and each label is generated as title case of the slug with hyphens replaced:
`Dashboard, Users, Students, Counselors, Agents, Commissions, Universities, **Schools**, **School Staff**, **School Applications**, **School Transfers**, **Activity Feedback**, **School Analytics**, Applications, Leads, Payments, Reports, BDMs, Agent deposits, Agent network`.
- The sidebar labels for the School CRM items are therefore **"Schools"**, **"School Staff"**, **"School Applications"**, **"School Transfers"**, **"Activity Feedback"** and **"School Analytics"**.
- The Overseas Admin's home is `/overseas/admin/dashboard` (`navigation.ts:28`).

### 0.2 Sidebar (Super Admin)
`apps/web/lib/navigation.ts:147`. `SUPER_ADMIN_NAV` contains only one school item: **"School Analytics"** → `/overseas/admin/school-analytics`. Schools, School Staff, School Applications, School Transfers and Activity Feedback are **not** in the Super Admin sidebar.

### 0.3 Middleware (sign-in gate)
`apps/web/middleware.ts:6-14`. Any `/overseas/admin/...` request without the `edusphere_access` cookie redirects to `/overseas/login?next=<path>`.

### 0.4 "Generic section" pages: `schools`, `school-staff`, `school-applications`
- Route `apps/web/app/overseas/admin/[section]/page.tsx:2` renders `PortalPage division="overseas" role="admin" section={section}`.
- `apps/web/components/PortalPage.tsx:3`: a section that is not in `PORTAL_NAV["overseas/admin"]` returns `notFound()`.
- `PortalPage.tsx:17` makes two calls: `GET /api/v1/auth/me` and `GET /api/v1/portal/overseas/admin/<section>`. Any error falls through to `accessUnavailable(e)`, which shows a card with heading **"Access unavailable"** and the server's `detail` as its text (`apps/web/components/AccessUnavailable.tsx:19-33`).
- The page then renders:
  1. `PortalSection` (`apps/web/components/PortalSection.tsx`): eyebrow "Workspace", the payload's title and subtitle, and a box headed `<title>` with a badge **"N role-scoped records"**. Below that is a `DataTable`, or the empty state **"No records yet"** / "When this workflow has data, permitted records will appear here. Use the relevant action above to begin."
  2. `WorkflowPanel` (`apps/web/components/WorkflowPanel.tsx:476`), an "action center". Its header reads **"Actions"** / "Changes are validated, permission checked, and written to the live workflow." with badge **"Operational"**. The school panels sit inside it:
     - `showSchoolCreate = ["overseas_admin","super_admin"] && section==="schools"` (`WorkflowPanel.tsx:469`) renders `AdminSchoolCreatePanel`, `AdminSchoolEditPanel` and `AdminSchoolBulkOnboardPanel`.
     - `showSchoolStaffCreate` (`:470`) on `school-staff` renders `AdminSchoolStaffPanel`.
     - `showSchoolApplications = ["overseas_admin","counselor","super_admin"]` (`:474`) on `school-applications` renders `AdminSchoolApplicationsPanel`.
- Backend gate for the portal payload (`apps/api/app/api/portal.py:14-43`): `user.role != "super_admin" and (user.division != division or user.role != route_role)` gives **403 "Role/division mismatch"**. A payload of `None` gives **404 "Workspace not found"**.

### 0.5 Generic `DataTable` controls (apply to the Schools / School Staff / School Applications tables)
`apps/web/components/DataTable.tsx:59-113`. All of these controls are client-side and work only on rows the server has already sent:
- **Search records** (placeholder "Search all columns…") searches every column.
- **Filter by**: a column select (default "Any column") plus **Filter value** (placeholder "Contains…", or "Choose a column" while disabled).
- **Rows per page** offers 10 / 25 / 50, with a default of 10.
- **Clear** appears once any search or filter is set.
- Every column header is a sort button (↕ / ↑ / ↓).
- Pagination: «, Previous, page numbers, Next, ». The footer reads "Showing a–b of N records".
- When nothing matches, the table shows **"No matching records"** / "Change or clear the search and filter values to see more records." with a **Clear controls** button.
- Values: null or empty shows "—". Objects show as JSON. Everything else shows as the raw string, so ISO timestamps and enum values appear exactly as stored.

### 0.6 Can Super Admin reach each screen? (division-guard finding)
In `apps/api/app/services/portal.py:1253-1254` the admin block sets `division = user.division if user.role != "super_admin" else None`.
- `schools` (`portal.py:1429`) and `school-staff` (`portal.py:1441`) are guarded by `division == "overseas"`. For a Super Admin `division` is `None`, so neither branch matches and `section_payload` returns `None`. The API answers **404 "Workspace not found"**, `serverApi` throws `ApiError("Workspace not found", 404)`, and `PortalPage.tsx:17` catches it and returns the **"Access unavailable / Workspace not found"** card. The `!data && super_admin` exemption on line 18 is never reached, because the 404 is only swallowed for the agent sections.
- `school-applications` (`portal.py:1231`) is inside the `{"counselor","university_rep","overseas_admin"}` block (`portal.py:986`) and requires `user.role in {"counselor","overseas_admin"}`. The admin block has no `school-applications` branch, so a Super Admin also gets **"Workspace not found"**.
- **Result: a Super Admin cannot open `/overseas/admin/schools`, `/overseas/admin/school-staff` or `/overseas/admin/school-applications`.** This is the same failure as the earlier finding. The panels are not rendered, even though `WorkflowPanel` and the backend `/overseas-admin/*` routes both allow `super_admin`. A Super Admin can still call those APIs directly. VERIFICATION REQUIRED: confirm in a browser (expected text "Access unavailable" + "Workspace not found").
- `school-transfers`, `activity-feedback` and `school-analytics` are standalone pages that check `["overseas_admin","super_admin"]` themselves, so a Super Admin **can** open them by typed URL. Only School Analytics is in the Super Admin sidebar.

---

## 1. Feature: Partner Schools list (view all schools)

- **Roles.**
  - Frontend: the section is in the Overseas Admin nav (`navigation.ts:118`), and the page relies on the portal payload as its gate (`PortalPage.tsx:17-18`).
  - Backend:
    - `portal.py:41-42` requires role `overseas_admin` with division `overseas`. Any other non-super role gets 403 "Role/division mismatch".
    - `services/portal.py:1429` builds the payload only when `division == "overseas"`.
  - **Overseas Admin: yes. Super Admin: no** ("Workspace not found", §0.6).
- **Route and navigation:** `/overseas/admin/schools`, sidebar **"Schools"**.
- **Page title and subtitle** (`services/portal.py:1436-1437`): **"Partner Schools"** / **"Every School partner record. Create a new one to seed its Coordinator account."**
- **Table columns** (`services/portal.py:1438-1439`): `reference` (the raw School UUID), **School ID** (the `school_code`, or "-"), **Name**, **Branch**, **City**, **State**, **Board**, **Tier** (raw lowercase such as `gold`, or "-"), **Created** (raw ISO timestamp).
  - Sort order: newest first (`order_by(School.created_at.desc())`, `portal.py:1434`).
  - Search, filter, sorting and pagination are the client-side DataTable controls (§0.5). The server does no pagination and has no cap: every school is returned.
- **Endpoint:** `GET /api/v1/portal/overseas/admin/schools` (`api/portal.py:13`, `Depends(get_current_user)`).
- **Oddities:**
  - The column header **"reference"** is lowercase and shows a raw UUID.
  - Tier is shown in lowercase.
  - "Created" is an unformatted ISO string.
  - The "-" placeholder comes from the server, so the DataTable's "—" never shows for these fields.
  - The rows are not clickable. Editing is done by typing the School ID into the separate Edit panel (§3).

## 2. Feature: Create a school and seed its School Coordinator

- **Panel:** `apps/web/components/AdminSchoolCreatePanel.tsx`, heading **"Create school"**, shown below the Partner Schools table.
- **Roles.**
  - Frontend: `WorkflowPanel.tsx:469` (`overseas_admin`, `super_admin`), but a Super Admin never reaches the page (§0.6).
  - Backend: `apps/api/app/api/admin.py:1424-1427`. A role outside `{"overseas_admin","super_admin"}` gets **403 "Overseas Admin role required"**.
- **Endpoint:** `POST /api/v1/overseas-admin/schools` (`admin.py:1424`, `status_code=201`, `Depends(get_current_user)`). The router is `agents_router` with prefix `/overseas-admin` (`admin.py:1119`), mounted at `/api/v1` (`apps/api/app/main.py:79-80`).

### Form fields
Labels are quoted exactly from `AdminSchoolCreatePanel.tsx:75-136`.

| Fieldset | Label | name | Type | Required (client) | Server rule (`schemas.py:2799-2823` SchoolCreate) |
|---|---|---|---|---|---|
| Identity | "School name" | name | text | **yes** (HTML `required`) | 1–200 chars |
| Identity | "Branch" | branch | text | no | ≤200 |
| Identity | "Address" | address | text | no | ≤500 |
| Identity | "City" | city | text | no | ≤120 |
| Identity | "State" | state | text | no | ≤120 |
| Identity | "Contact number" | contact_number | text | no | ≤30 (no format check) |
| Identity | "Email" | email | `type=email` | no | regex `^[^\s@]+@[^\s@]+\.[^\s@]+$`, ≤255 |
| Identity | "Website" | website | text | no | ≤255 (no URL check) |
| Academic | "Grades available" | grades_available | text | no | ≤200 |
| Academic | "Board" | board | select: "Not set", CBSE, ICSE, State, IB, Other | no | Literal CBSE/ICSE/State/IB/Other |
| Partnership | "Partnership tier" | tier | select: "Not set", Bronze, Silver, Gold, Platinum | no | must be bronze/silver/gold/platinum |
| Partnership | "Partnership date" | partnership_date | `type=date` | no | date |
| Partnership | "Agreement / MoU reference" | mou_reference | text | no | ≤255 |
| Partnership | "Edusphere BDM" | edusphere_bdm | text (free text, not linked to a BDM user) | no | ≤200 |
| Partnership | "Vice Principal" | vice_principal_name | text | no | ≤200 |
| Partnership | "Monthly visit schedule" | monthly_visit_schedule | text | no | ≤200 |
| (no fieldset) | "Coordinator full name" | coordinator_full_name | text | **yes** | 1–160 |
| (no fieldset) | "Coordinator email" | coordinator_email | `type=email` | **yes** | validated by `_valid_email` |

- **Button:** **"Create school + seed Coordinator"**. While busy it reads **"Creating…"** (`:137-139`).
- **Client validation:** browser-native only (`required`, `type=email`). The panel has no custom messages, so the browser supplies the text (VERIFICATION REQUIRED for exact browser wording).
- **Server errors** are shown as `detail`. A 422 list is joined with "; ", and an unknown shape falls back to **"Unable to create school."** (`:8-12`).
  - 409 **"Email already exists"** when the Coordinator email already has an account (`admin.py:1383-1384`, and the race path `services/provisioning.py:56-63`).
  - 422 **"A valid email address is required"** for a bad Coordinator email (`admin.py:107-111`).
  - 422 **"tier must be one of bronze, silver, gold, platinum"** (`admin.py:1385-1386`). The select makes this unreachable from the UI.
  - 422 **"Coordinator name must be at most 160 characters"** via `_fit` (`admin.py:114-119`). Pydantic's `max_length=160` normally fires first, with the Pydantic wording "String should have at most 160 characters".
  - 422 Pydantic messages for other length or pattern failures, shown raw (for example "String should have at most 200 characters", or the pattern message for the school Email). VERIFICATION REQUIRED for exact Pydantic text. This panel does **not** strip the "Value error," prefix (its local `detailMessage` differs from `lib/apiErrors.ts`).
  - 403 **"Overseas Admin role required"**.
  - Network failure: **"Network error -- it is not known whether the school was created. Check the schools list before trying again."** (`:57`)
- **Success message** (`:66` + `apps/web/lib/welcomeLink.ts:11-20`):
  - Email delivered (green): **"School created. School code {CODE}. Coordinator account ready for {email}. A set-password link was emailed and is valid for 72 hours."**
  - Email not delivered (amber warning): **"School created. School code {CODE}. Coordinator account ready for {email}. The email was not delivered (email is not configured on this server | the email could not be sent). Re-send the link from the Users page or dashboard once email works, or ask the user to use "Forgot your password?" on the sign-in page."**
  - On success the form resets and the page refreshes (`router.refresh()`), so the new row appears in the table.
- **Side effects** (`admin.py:1366-1418` `_provision_school`, then `create_school` at `:1428-1437`):
  - A School row is created with a generated **School ID**: 8-character uppercase hex (`apps/api/app/core/identifiers.py:11-31`, `unique_student_code`).
  - A **School Coordinator** user is created: `role="school_coordinator"`, `division="overseas"`, `active=True`, `email_verified=False`, `profile={"school_id": ...}`, with an unusable password.
  - A `UserRoleAssignment` is created with `approval_status="approved"`. There is no approval gate.
  - A welcome or set-password token is issued, valid for 72 hours (`services/provisioning.py:37,97-102`).
  - Audit logs `school.create` and `school.coordinator_seed`.
  - After the commit, `deliver_welcome_link` (`provisioning.py:112-168`) sends an SMTP email (template `welcome_set_password`) and the generic webhook in parallel. The link is `{frontend_url}/overseas/reset-password?token=...` (`provisioning.py:66-70`). An audit row `user.welcome_link_delivery` is written. In dev environments the response also carries `development_welcome_token`, which the UI does not show.
  - Response: the full `SchoolOut` plus `coordinator_id`, `coordinator_email` and `email_status`.
- **Oddities:**
  - The create UI has **no "Valid until" (tier_valid_until) field**, although the API accepts one (`schemas.py:2808`). It can only be set later via Edit, or through bulk upload.
  - The single create does **not** check for duplicate school names. Bulk upload rejects a duplicate name + city (§4).
  - Name, City and State cannot be edited after creation (§3).
  - Setting a tier on create sends **no** tier notification. Only an edit notifies (§3).

## 3. Feature: Edit school profile and change the partnership tier (entitlements)

- **Panel:** `apps/web/components/AdminSchoolEditPanel.tsx`, heading **"Edit school profile"**, on `/overseas/admin/schools`.
- **Roles.**
  - Frontend: `WorkflowPanel.tsx:469`.
  - Backend: each endpoint checks `{"overseas_admin","super_admin"}` and otherwise returns **403 "Overseas Admin role required"** (`admin.py:1505-1506, 1560-1561, 1732-1733`).

### Step 1, look up the school
- One field, label **"School ID"** (name `code`, required). Button **"Look up"**, which reads "Looking up…" while busy (`:181-187`).
- Endpoint: `GET /api/v1/overseas-admin/schools/lookup?code=` (`admin.py:1725-1737`). The code is trimmed and upper-cased.
- Errors:
  - 404 **"No school found with that School ID"**.
  - Network failure: **"Network error -- check your connection and try again."**
  - Fallback: **"Unable to look up that school."**

### Step 2, edit the form
Shown after a successful lookup, with the caption "{name} ({school_code})". Fields come from `:191-240`, and all are optional.
- "Branch", "Address", "Contact number", "Email" (`type=email`), "Website", "Grades available".
- "Board": select, "Not set" / CBSE / ICSE / State / IB / Other.
- "Partnership date" (date), "Agreement / MoU reference", "Edusphere BDM", "Vice Principal", "Monthly visit schedule".
- Fieldset **"Partnership"**:
  - **"Partnership tier"**: select, Not set / Bronze / Silver / Gold / Platinum.
  - **"Valid until"** (date), with help text **"Leave empty for no end date."**
  - Help line: **"Currently {Tier | no partnership tier}. Changing it notifies the school; a downgrade asks you to confirm first."**
- Not editable: **name, city, state, coordinator** (`SchoolUpdate` has no such fields; `extra="forbid"`, `schemas.py:2826-2846`).
- Button **"Save changes"**. While busy it reads **"Checking tier change…"** or **"Saving…"** (`:241`).

### Save logic (`:141-175`)
- Only changed fields are sent. An emptied field is sent as `null`, which clears it.
- If nothing changed, the panel shows **"No changes to save."**
- If the tier changed, it first calls `GET /api/v1/overseas-admin/schools/{id}/tier-change-preview?tier=` (`admin.py:1554-1569`, read-only).
  - For a **downgrade or removal** it shows an inline confirmation (`apps/web/components/TierDowngradeConfirm.tsx:8-24`):
    - **"Downgrading {School} from {From} to {To}."**
    - **"These services will no longer be available for new work:"** followed by a list of the lost services.
    - **"Work already started can still be completed. The school will be notified."**
    - Buttons **"Confirm downgrade"** (reads "Saving…" while busy) and **"Cancel"**. Escape also cancels. Any change to the form cancels a pending confirmation.
  - An upgrade saves directly.
- The save is `PATCH /api/v1/overseas-admin/schools/{id}` (`admin.py:1497-1551`). Every tier save carries `expected_tier`.

### Messages
- **Success:** **"School profile updated."**, or **"School profile updated. Partnership is now {Tier}; newly available: {labels}."** for an upgrade. A downgrade gives "School profile updated. Partnership is now {Tier}." (`:27-31`)
- **Errors:**
  - Any 4xx is shown as **"Not saved: {detail}"**. A 5xx or unconfirmable response is shown as **"The save could not be confirmed. Look the school up again to check before retrying."** (`:130`)
  - Network failure: **"Network error -- it is not known whether the changes saved. Look the school up again before retrying."**
  - A 200 response without an id: **"The save could not be confirmed. Look the school up again before changing anything else."**
  - Preview failure: **"Unable to check the tier change. Nothing was saved."**
  - Preview network failure: **"Network error -- nothing was saved. Check your connection and try again."**
- **Server messages:**
  - 404 **"School not found"**.
  - 422 **"tier must be one of bronze, silver, gold, platinum"** (`admin.py:1448,1514-1515`).
  - 409 **"This school's tier changed to {Tier} since you looked it up. Look it up again before changing the tier."** (`admin.py:1516-1518`), when another admin changed the tier in the meantime.

### Tier model (entitlements)
Defined in `apps/api/app/api/schools.py:978-1019`. Tiers are cumulative.
- **Bronze:** Career seminar; Student career awareness session; Parent orientation; Psychometric test; Soft skills.
- **Silver** adds: Individual counselling; Digital skills.
- **Gold** adds: Application support; Scholarship assistance; IELTS coaching; SAT coaching; Foreign language classes; Digital portfolio creation.
- **Platinum** adds: Dedicated EduSphere counselor; Monthly campus visits; Internships; Visa support; Loan assistance; Alumni network; Parent help desk.

**Enforcement** (`schools.py:1076-1163` `require_school_entitlement`), for school-side users and also for the admin bridge (§6). The 403 messages are:
- **"This school has no active partnership tier."**
- **"This school's partnership expired on {DD Mon YYYY}."** (India calendar, `TIER_TIMEZONE` Asia/Kolkata)
- **"This school's {Tier} partnership does not include {Service} (requires {MinTier} or higher)."**

Work already started is exempt ("grandfathered") after a downgrade, but not after expiry (`schools.py:1089-1120`).

### Side effects (`admin.py:1519-1551`)
- Row lock on the school.
- Audit `school.tier_update` with from/to/direction/gained/lost/valid-until metadata, written whenever tier **or** valid-until is in the body.
- Audit `school.profile_update` with `changed_fields`.
- After the commit, for a real upgrade or downgrade only, `_notify_tier_change` (`admin.py:1474-1494`) sends:
  - To every **active School Coordinator and Principal** of the school: an in-app notification plus queued email, and WhatsApp/SMS if they opted in (`schools.py:731-741`).
    - Upgrade: title **"Your partnership is now {After}"**, body "{School} has moved from {Before} to {After}. Newly available: {labels}."
    - Downgrade: title **"Your partnership changed from {Before} to {After}"**, body "These services are no longer available for new work: {labels}. Work already started for them can still be completed."
    - The action link goes to `/school/coordinator/entitlements` or `/school/principal/entitlements`.
  - To the **acting admin**: an in-app notification titled **"Tier change recorded: {School}, {Before} → {After}"**.
  - A notification failure is logged and never undoes the change.

### Oddities
- Changing only "Valid until" writes a `school.tier_update` audit row with direction "unchanged", sends **no** notification, and skips the preview.
- Extending or shortening the validity date is the only way to renew. The Analytics "Renewal due" flag is based on it (§8).
- There is no list or table action to edit a school. The admin must copy the School ID from the table.

## 4. Feature: Onboard several schools by CSV (bulk onboarding)

- **Panel:** `apps/web/components/AdminSchoolBulkOnboardPanel.tsx`, title **"Onboard several schools (CSV)"** (`apps/web/lib/bulkEntry.ts:86-113`), on `/overseas/admin/schools`.
- **Roles.**
  - Frontend: `WorkflowPanel.tsx:469`.
  - Backend: `apps/api/app/api/school_onboarding_bulk.py:35,46-48`, `{"overseas_admin","super_admin"}`, otherwise **403 "Overseas Admin role required"**.
- **Intro text:** **"Add many partner schools at once. Each school gets its own coordinator account and set-password email, exactly like Create school."**

### Step 1, "1. Download the template"
- Button **"Download the template (.csv)"** calls `GET /api/v1/overseas-admin/schools/bulk-template` (`school_onboarding_bulk.py:207-216`).
- The file is `school-onboarding-bulk-template.csv` and contains a header row only. The columns are the SchoolCreate fields in order: `name, city, state, tier, tier_valid_until, coordinator_full_name, coordinator_email, branch, address, contact_number, email, website, grades_available, board, partnership_date, mou_reference, edusphere_bdm, monthly_visit_schedule, vice_principal_name`.
- A collapsible **"Column reference"** table (`apps/web/components/BulkColumnReference.tsx`) has the columns Column / Required / Format / Example:
  - Required = Yes for `name`, `coordinator_full_name` and `coordinator_email`.
  - Formats: "Text, up to N characters"; "YYYY-MM-DD"; "bronze, silver, gold or platinum"; "CBSE, ICSE, State, IB or Other"; "Email; must not already have an account"; "School email address".
  - Examples include "Sunrise Public School", "Pune", "gold", "2027-03-31", "Meera Iyer", "meera@sunrise.edu.in".

### Step 2, "2. Upload the filled-in file"
- File input label **"Filled-in schools file"** (accepts `.csv,text/csv`), help text **"CSV, up to 1 MB and 100 schools. One school per row."**
- Button **"Upload schools"**, which reads "Uploading…" while busy.
- Screen-reader status while busy: "Uploading — creating schools and sending set-password emails. Large files can take up to a minute."
- **Client checks** (`:28-33`):
  - **"Choose a filled-in CSV file first."**
  - **"Choose a .csv file."**
  - **"The file is larger than 1 MB."**
- **Endpoint:** `POST /api/v1/overseas-admin/schools/bulk-upload` (multipart `file` + `Idempotency-Key` header, generated per chosen file) (`school_onboarding_bulk.py:219-270`).
- **File-level server errors** (`apps/api/app/api/school_bulk.py:53-55, 278-345, 359-381`). The panel shows `detail`, or "Unable to process this upload." if there is none.
  - 413 **"The file is larger than 1 MB"**
  - 422 **"The file must be a UTF-8 CSV"**
  - 422 **"Duplicate column: {name}"**
  - 422 **"Unknown column: {name}"**
  - 422 **"Missing required column: {name}"**
  - 422 **"The file has no filled-in rows"**
  - 422 **"The file has more than 100 filled-in rows"**
  - 422 **"Idempotency-Key header is required"** / **"Idempotency-Key must be 1-120 letters, digits or . _ : -"** (not reachable from the UI)
  - 422 **"Idempotency-Key was already used for a different file"**
  - 409 **"This upload is still being processed; retry shortly"**
  - Network failure: **"The connection dropped. Upload again — the same file won't be added twice."**
- **Row-level rejections** (`school_onboarding_bulk.py:72-96, 115-151`). Each row succeeds or fails on its own.
  - Pydantic message as "<field> <reason>" (`schemas.py:1686-1694`), for example "name string should have at most 200 characters". VERIFICATION REQUIRED for exact text.
  - "A valid email address is required"
  - **"same coordinator_email as row {n}"**
  - **"Email already exists"**
  - **"a school with this name and city already exists"** (whitespace and case normalised)
  - **"same school name and city as row {n}"**
  - "tier must be one of bronze, silver, gold, platinum"
  - **"This row conflicts with a record created at the same time; upload it again"**
- **Result report** (`AdminSchoolBulkOnboardPanel.tsx:42-82`): heading **"Upload result"**, a summary line, then a table with the columns **Row, Result ("Added"/"Rejected"), School ID, School, Coordinator, Detail**. The Detail column shows one of:
  - "Set-password link emailed"
  - "Email not delivered — re-send from the Users page"
  - "Check the Users page for set-password status" (on a replay)
  - the rejection message

  The summary line is one of:
  - all rejected: **"No schools were onboarded. Fix the rows below and upload again."** (error)
  - all accepted: **"{n} school(s) onboarded."** plus " {m} welcome email(s) was/were not delivered — re-send from the Users page." when some emails failed
  - mixed: **"{a} of {t} schools onboarded, {r} rejected. Schools that succeeded are kept — fix the rejected rows and upload just those."** (warning)

  The report table has no search or pagination (100 rows at most).
- **Side effects:**
  - Each accepted row does exactly what Create does (`_provision_school`): a school, a Coordinator, an approved role, a welcome token, and audits `school.create` / `school.coordinator_seed`.
  - One audit `school.bulk_upload` per batch.
  - Batch and row records go to `SchoolBulkUploadBatch` / `SchoolBulkUploadRow` with `target_type="school_onboarding"`.
  - An advisory lock serialises onboarding uploads.
  - Welcome emails are sent after the commit, at most 5 at a time.
  - Re-uploading the **same file with the same key** replays the first report instead of creating duplicates.
- **Oddities:**
  - Bulk can set `tier_valid_until`, but single Create cannot.
  - Bulk rejects a duplicate name+city, but single Create does not.

## 5. Feature: School service-delivery staff accounts (Academic Team / Career Counselor / Psychometric Team)

- **Roles.**
  - Frontend: the section is in the Overseas Admin nav, and `WorkflowPanel.tsx:470` shows the panel to `overseas_admin` and `super_admin`. A Super Admin gets "Workspace not found" (§0.6).
  - Backend: `admin.py:1666-1670` returns **403 "Overseas Admin role required"** to anyone else.
- **Route and navigation:** `/overseas/admin/school-staff`, sidebar **"School Staff"**.
- **Table** (`services/portal.py:1441-1456`):
  - Title **"Academic Team / Career Counselor / Psychometric Team"**, subtitle **"Every specialized School service-delivery staff account and how many schools are in their portfolio."**
  - Columns: `reference` (raw UUID), **Name**, **Email**, **Role** (raw value `academic_team` / `career_counselor` / `psychometric_team`), **Schools in portfolio** (a count).
  - Sorted by newest account first.
  - Client-side DataTable controls (§0.5).
  - The table does **not** show which schools are in a portfolio, or whether the account has set its password.

### Create panel (`apps/web/components/AdminSchoolStaffPanel.tsx`)
Heading **"Create Academic Team / Career Counselor / Psychometric Team account"**.

**Fields:**
- **"Role"**: required select with placeholder "Select role" (disabled) and options **Academic Team**, **Career Counselor**, **Psychometric Team**.
- **"Full name"**: required text.
- **"Email"**: required, `type=email`.
- **"School portfolio"**, with "({n} selected)" when any are chosen.
  - When there are no schools the panel shows **"No partner schools yet -- create one first."**
  - Otherwise there is a search box (placeholder **"Search schools…"**), client-side and by name only.
  - Buttons **"Select all ({N})"**, **"Select visible"** ("Select visible ({n})" while searching), **"Clear visible"** and **"Clear all"**.
  - A multi-select list shows up to 8 rows tall. When the search finds nothing: "No schools match "{q}"."
  - Help text: **"Hold Ctrl (Windows) or Cmd (Mac) to select more than one. A portfolio can be left empty and filled in later, but the account can't act on any student until at least one school is assigned."**
  - The school list comes from `GET /api/v1/overseas-admin/schools` (`admin.py:1440-1445`, all schools with the full profile). If that call fails, the list is silently empty.

**Button and endpoint:**
- Button **"Create account"**, which reads "Creating…" while busy.
- Endpoint: `POST /api/v1/overseas-admin/school-staff` (`admin.py:1666-1708`), body `{role, full_name, email, school_ids}`.

**Server errors** (shown raw; fallback "Unable to create this account."):
- 422 **"role must be one of ['academic_team', 'career_counselor', 'psychometric_team']"**
- 422 **"email and full_name are required"**
- 422 **"Full name must be at most 160 characters"**
- 422 **"A valid email address is required"**
- 409 **"Email already exists"**
- 422 **"One or more school_ids do not exist"**
- 422 **"A password cannot be supplied; the user sets their own via the emailed set-password link"** (only if a `password` key is sent; not reachable from the UI)
- Network failure: **"Network error -- it is not known whether the account was created. Check the Users list before trying again."**

**Success messages** (`welcomeLink.ts`):
- **"Account created for {email}. A set-password link was emailed and is valid for 72 hours."**
- When the email was not delivered, the amber variant: "Account created for {email}. The email was not delivered (...). Re-send the link from the Users page or dashboard once email works, or ask the user to use "Forgot your password?" on the sign-in page."

**Side effects:**
- A User is created with the chosen role, division overseas, active, and an unusable password.
- Welcome token.
- `UserRoleAssignment` with approval status approved.
- One `SchoolStaffAssignment` per selected school.
- Audit `school.staff_create`.
- Welcome email after the commit (same mechanism as §2).

### Adding schools to an existing portfolio
- An API exists, `POST /api/v1/overseas-admin/school-staff/{staff_id}/portfolio` with body `{school_id}` (`admin.py:1829-1850`). It returns 404 "Specialized-role staff account not found", 422 "A valid school_id is required", or 409 "This school is already in this staff member's portfolio", and writes the audit `school.staff_portfolio_add`.
- **No frontend calls it**, which a grep of `apps/web` confirmed. **There is no remove-from-portfolio endpoint at all.**
- So after creation the portfolio **cannot be changed from the UI**, despite the help text "can be left empty and filled in later". VERIFICATION REQUIRED with the product owner. This is an as-built gap.
- `GET /api/v1/overseas-admin/school-staff` (`admin.py:1711-1722`, which returns `school_ids` per staff member) also has no UI caller.

### Resending a set-password link
- The Overseas Admin **"Users"** page (`/overseas/admin/users`) shows the Manage users panel (`WorkflowPanel.tsx:446`, `user.role === "overseas_admin" && section === "users"`), which has setup status and Re-send.
- This is where the "Re-send the link from the Users page" advice points, for Coordinators and staff. The endpoint is `POST /api/v1/admin/users/{id}/welcome-links` (`welcomeLink.ts:26-35`). Not inspected in depth here, because it belongs to the user-management area.

## 6. Feature: School Applications (start an Overseas application for a School student, the School→Overseas bridge)

- **Is it School CRM?** Yes. It works only on `SchoolStudent` records, which are school-affiliated students who have no user login.
  - The payload joins `OverseasApplication.school_student_id → SchoolStudent` (`services/portal.py:1231-1251`).
  - The create endpoint takes a `SchoolStudent` id (`admin.py:1766`).
  - It consumes the school's Gold-tier **"Application support"** entitlement (`admin.py:1778`).
  - It notifies the student's linked School Parents.
- **Roles.**
  - Frontend: `WorkflowPanel.tsx:474` admits `overseas_admin`, `counselor` and `super_admin`. The section is also in the **Counselor** nav as "School Applications" (`navigation.ts:116`).
  - Backend payload: `services/portal.py:1231` requires `counselor` or `overseas_admin`, so a **Super Admin gets "Workspace not found"**.
  - Backend endpoints: `{"overseas_admin","counselor","super_admin"}`, otherwise **403 "Overseas Admin or Counselor role required"** (`admin.py:1771-1772, 1813-1814`).
  - Lookups: `apps/api/app/api/lookups.py:52-57,212-245` allow `overseas_admin`, `counselor` and `super_admin`, otherwise 403 "This role cannot use this lookup".
  - A Counselor sees only the applications where `counselor_id` is their own id.
- **Route and navigation:** `/overseas/admin/school-applications`, sidebar **"School Applications"**. For counselors, `/overseas/counselor/school-applications`.

### Screen
**Generic table** (`services/portal.py:1247-1251`):
- Title **"School-Linked Overseas Applications"**, subtitle **"Overseas applications started for School-affiliated students. Start a new one below by Student ID."**
- Columns: `reference` (raw UUID), **Student**, **Student ID**, **University**, **Status** (raw value, e.g. `enquiry`).
- Sorted newest first. DataTable controls (§0.5).

**Panel** (`apps/web/components/AdminSchoolApplicationsPanel.tsx`), heading **"Start an Overseas application for a School student"**:
1. **"School"**, a searchable combobox (`SearchableSelect`). It calls `GET /api/v1/lookups/schools?q=&limit=20` (`lookups.py:212-226`) and searches name or School ID. Each option shows the name, with the School ID as detail.
2. Once a school is chosen, **"Student"**, a searchable combobox over that school only. It calls `GET /api/v1/lookups/school-students?school_id=&q=&limit=20` (`lookups.py:229-245`, which returns 404 "School not found") and searches name or Student ID. The detail shows grade and Student ID.
   - Combobox status texts: "Loading…", "Could not load the schools/students.", "No matching schools/students.", "Keep typing to narrow the list." (`SearchableSelect.tsx:151-157`).
3. Once a student is chosen, a form appears:
   - **"University"**: required select, placeholder "Select university", options "{name} ({city})" from `GET /api/v1/public/universities` (`public.py:138`).
   - **"Intake"**: required text, placeholder **"e.g. Fall 2027"**.
   - Button **"Start application"**, which reads "Starting…" while busy.
4. **"Linked applications"**, a second table with columns **Student, Student ID, University, Status**. It loads from `GET /api/v1/overseas-admin/school-applications` (`admin.py:1809-1826`) and shows "No School-linked applications yet." when empty. It has no search, sort or pagination.

**Client message:** **"Choose a school, then a student, first."**

**Endpoint:** `POST /api/v1/overseas-admin/school-students/{school_student_id}/applications` (`admin.py:1766-1806`), body `{university_id, intake}`.

**Server errors** (via `sendJson` / `detailMessage`):
- 404 **"School student not found"**
- 403 entitlement messages (§3), for example **"This school's Silver partnership does not include Application support (requires Gold or higher)."**
- 404 **"University not found"**
- 422 **"A valid university is required"** (`core/identifiers.py:34-47`)
- 422 **"intake is required"**
- 409 **"An application for this university already exists for this student"**
- Network failure: **"The request did not complete. Check your connection and try again; your entry is kept."** (`apiErrors.ts:24`)

**Success:** **"Application started for {student label}."** Both pickers reset and the panel's list reloads.

**Side effects:**
- An `OverseasApplication` is created with `student_id=None`, `school_student_id` set, status `enquiry`, `next_action` "Complete profile and required document checklist", and `counselor_id` = the actor if a counselor.
- An `ApplicationStatusHistory` row.
- Audit `school.overseas_application_link`.
- Every active linked School Parent is notified (in-app plus queued email/WhatsApp/SMS): "Overseas application started for {name}" / "An application to {University} has been started for {name}."

### Oddities
- Two tables on one page list the same applications: the generic DataTable and the panel's "Linked applications". The generic table only updates after a page refresh.
- The subtitle says "Start a new one below by Student ID", but the panel actually uses a School → Student picker.
- The `course_id` field is accepted by the API but not offered in the UI.
- `GET /overseas-admin/school-students/lookup` (`admin.py:1740-1754`) no longer has a UI caller.

## 7. Feature: School Transfers (approve or reject student transfer requests)

- **Page:** `apps/web/app/overseas/admin/school-transfers/page.tsx`. This is a static route and takes precedence over `[section]`.
- **Roles.**
  - Frontend: `ADMIN_ROLES = ["overseas_admin","super_admin"]` (`:13,22`). Anyone else gets **"Access unavailable"** with **"Overseas Administrator role required"** and a "Go to your dashboard" button.
  - Backend: the dependency `_require_transfer_admin` (`apps/api/app/api/school_transfers.py:333-338`) returns **403 "Overseas Admin role required"**.
  - **Super Admin can open it** by typed URL. It is not in the Super Admin sidebar.
- **Route and navigation:** `/overseas/admin/school-transfers`, sidebar **"School Transfers"**.
- **Header:** eyebrow "Workspace", **"School Transfers"**, **"Student transfer requests from School Coordinators. Approve or reject pending ones; approving moves the student in one step."**

### Panel (`apps/web/components/AdminSchoolTransferPanel.tsx`)
- Heading **"Transfer requests ({total})"** and sub-line **"Coordinators ask; you decide. Approving moves the student in one step."**
- **"Status"** filter: a select with **Pending review** (default), **All**, **Approved**, **Rejected**, **Cancelled** (`apps/web/lib/transfers.ts:49`). The filter is applied on the server.
- **Pagination:** 25 per page, with a **"Load more"** button ("Loading…" while busy) and "Showing {n} of {total}". There is no search and no sort; the order is newest first (`school_transfers.py:364`).
- **States:**
  - "Loading transfer requests…"
  - Empty: **"No pending transfer requests."** / **"No transfer requests yet."** (All) / **"No {status} requests."**, with a **"Show pending"** button.
  - Load error: **"Could not load transfer requests."** with **"Try again"**.
  - 401: **"Your session has expired. "** with a **"Sign in again"** link to `/overseas/login`.
- **Each row** (`apps/web/components/AdminTransferRow.tsx:93-145`) shows:
  - Student name, Student ID, **"From {A} → To {B}"**.
  - **"Requested by {name} (the losing | the gaining school) · {local time}"**.
  - "Reason: …" and "Note: …" when present.
  - A status badge: Pending review / Approved / Rejected / Cancelled.
  - For pending requests, a preview: **"If approved: up to {n} linked parent account(s) may move, and {n} unpublished result(s) will be withdrawn."**
  - A warning when the destination has no portfolio staff: **"{To} has no assigned staff portfolio, so the student will be invisible to the Academic Team, Career Counselor and Psychometric Team until one is assigned."**
  - A warning when a parent invite is pending: **"A parent has been invited but has not accepted yet. Approving clears that invite, so they will not be linked to {student}. Consider asking them to accept it first."**
  - For decided requests, the outcome text: "{n} parent(s) now only at the new school, {k} still also at the previous school, {r} result(s) withdrawn".
- **Approve** (button "Approve") opens an inline confirmation:
  - "Moves {student} to {To}."
  - "Up to {n} linked parent account(s) move(s) to {To} if they have no other child at {From}. Each parent keeps access to their child."
  - "{n} unpublished result(s) is/are withdrawn. The teacher assignment is cleared. This cannot be undone here."
  - Buttons **"Confirm approval"** ("Approving…" while busy) and **"Cancel"**. Escape also cancels.
- **Reject** (button "Reject") opens a textarea **"Note for the requesting coordinator (optional)"** (maxLength 500) with hint **"Visible to the requesting coordinator. Do not include student details."** Buttons are **"Confirm rejection"** ("Rejecting…" while busy) and **"Cancel"**.
- **Success messages:**
  - Approve: **"Moved {student} to {To}. {outcome}."**
  - Reject: **"Request rejected for {student}."**
  - On the Pending filter the decided row is removed from the list.
- **Errors:**
  - Network failure: **"The decision did not complete. Check your connection and refresh the queue before trying again."**
  - 2xx without a body: **"The decision could not be confirmed. The queue is being reloaded; check it before deciding again."**
  - Server `detail` messages:
    - 404 **"Transfer request not found"**
    - 409 **"This transfer request has already been decided"**
    - 404 **"Student not found"**
    - 409 **"The student is no longer at the school this request was filed for; reject it and file a new one"**
    - 409 **"Another change to this student is in progress; retry"**
    - 422 note validation: "must be 500 characters or fewer" or "must not contain control or bidirectional-override characters" (`schemas.py:2077-2092`, wrapped by Pydantic; VERIFICATION REQUIRED for the exact displayed text)
  - A 409 reloads the queue automatically.
- **Endpoints:**
  - `GET /api/v1/overseas-admin/school-transfer-requests?status=&limit=25&offset=` (`school_transfers.py:564-614`, limit 1–100)
  - `POST /api/v1/overseas-admin/school-transfer-requests/{id}/approve` (`:490-515`)
  - `POST .../{id}/reject`, with optional body `{note}` (`:518-561`)
- **Side effects of approval** (`school_transfers.py:387-448`), all in one transaction:
  - The student's `school_id` changes.
  - The assigned teacher, pending parent email, section and roll number are cleared.
  - Draft and verified results are set to `withdrawn`, with a status history.
  - Parent links are untouched. Parents "move" conceptually when they have no other child at the old school.
  - Audit `school.student_transfer`.
  - After the commit:
    - linked parents get in-app plus queued delivery: "{name} has moved to {To}"
    - the losing school's coordinators get in-app only: "Transfer approved: {name} moved to {To}"
    - the gaining school's coordinators get in-app only: "{name} has joined {To}"
- **Side effects of rejection:**
  - The request is marked rejected with the note.
  - Audit `school.transfer_request_rejected`.
  - In-app notification to the requester: "Transfer of {name} to {To} was not approved", or for incoming requests "Transfer request for Student ID {code} was not approved", with body "An admin reviewed the request and did not approve it. Nothing has changed."
- **Oddities:**
  - When a Super Admin opens this page it shows the **Overseas Admin sidebar and the role label "Overseas Administrator"** (`page.tsx:24`). School Analytics fixed the same issue (QA-016-08); this page did not.
  - The admin transfer-history endpoint `GET /api/v1/overseas-admin/school-students/{id}/transfer-history` (`school_transfers.py:617-624`) has **no UI caller**.

## 8. Feature: School Analytics (cross-school dashboard and service utilization)

- **Page:** `apps/web/app/overseas/admin/school-analytics/page.tsx`, with a skeleton in `loading.tsx` ("Loading school analytics").
- **Roles.**
  - Frontend: `["overseas_admin","super_admin"]` (`:11,21`), otherwise "Access unavailable" with "Overseas Administrator role required".
  - Backend: `_require_school_admin` (`apps/api/app/api/school_analytics.py:163-167`) returns **403 "Overseas Admin role required"**.
  - **Super Admin: yes.** It is in the Super Admin sidebar, and the page shows `SUPER_ADMIN_NAV` with the label "Super Administrator" (`:32-35`).
- **Route and navigation:** `/overseas/admin/school-analytics`, sidebar **"School Analytics"** for both roles.
- **Header:** **"School Analytics"** / **"Every partner school at a glance, and how much of each partnership is being used."**

### Card "All partner schools" (`apps/web/components/CrossSchoolAnalytics.tsx:55-68`)
Four KPI groups:
- **Schools**: Total, Active, New (90 days), Renewal due (60 days).
- **Students**: Total, Career guidance, Psychometric, Counselling, Global education.
- **Services**: Delivered, Pending, Not tracked, Utilization (%; "—" when not applicable).
- **Outcomes**: Applications, Offers, Visas, Admissions, Internships, Scholarships. Scholarships shows the badge **"Not tracked yet"** with the note "No school-student scholarship link exists yet (ENH-017)." (`school_analytics.py:487-489`)

When this card's data fails to load, it shows **"This section couldn't load. Refresh to try again."** (`SectionUnavailable`).

### Card "Service utilization by school"
- A GET search form: **"Search schools"** (maxLength 200) with button **"Search"**. The search runs on the server by name, case-insensitive.
- Table columns: **School, Tier** (capitalised, or "No tier"), **Students, Participating, Delivered, Pending, Not tracked, Utilization, Upcoming activities, Flags**. The Flags column shows badges **"New"**, **"Renewal due"** and **"No active tier"**.
- Sorted by name. There are no sortable headers.
- Pagination: 25 per page via links **"← Previous"** / **"Next →"** and the text "{a}–{b} of {total}".
- Empty states: **"No partner schools yet."**, **"No schools match "{q}"."**, **"This page is past the end of the list."**

### Endpoints
- `GET /api/v1/overseas-admin/analytics/summary` (`school_analytics.py:517-553`)
- `GET /api/v1/overseas-admin/analytics/schools?offset=&q=` (`:556-591`, limit 25 by default, max 100, offset ≤ 10000)

### Definitions
- "Active" means a tier is set and not expired (`:507-509`).
- "New" means partnership date (or creation date) within 90 days.
- "Renewal due" means `tier_valid_until` within 60 days or already past.
- Utilization is computed over the services included in the tier and tracked by a module (`:492-499`).

### Side effects
A log line only (`school_analytics_view`). Read-only, aggregates only.

### Oddities
- `students.by_grade` is computed by the API but never displayed.
- VERIFICATION REQUIRED: which services count as "not tracked" depends on `schools.service_usage` (not read in full here).

## 9. Feature: Activity Feedback (read every school's post-activity feedback)

- **Is it School CRM?** Yes. It lists `SchoolActivityFeedback` that **School Coordinators** submit after EduSphere activities at their school, joined to `School` and `SchoolActivity` (`apps/api/app/api/school_feedback.py:162-192`). The admin side is read-only.
- **Page:** `apps/web/app/overseas/admin/activity-feedback/page.tsx`.
- **Roles.**
  - Frontend: `["overseas_admin","super_admin"]` (`:10,19`).
  - Backend: `_require_feedback_admin` (`school_feedback.py:155-159`) returns **403 "Overseas Admin role required"**.
  - **Super Admin can open it** by URL, but it is not in the Super Admin sidebar, and the page shows the Overseas Admin sidebar labelled "Overseas Administrator" (`:21`). This is the same oddity as §7.
- **Route and navigation:** `/overseas/admin/activity-feedback`, sidebar **"Activity Feedback"**.
- **Header:** **"Activity Feedback"** / **"Feedback School Coordinators recorded after each Edusphere activity, across every partner school."**

### Panel (`apps/web/components/AdminActivityFeedbackPanel.tsx`)
- Heading **"School activity feedback ({total})"** and the line "What School Coordinators said after each Edusphere activity."
- **Filters:**
  - **"Search schools"**, a client-side box that narrows the dropdown, with the hint "{n} of {N} schools match".
  - **"School"**, a select defaulting to "All schools", built from `GET /api/v1/overseas-admin/schools`. Filtering by school happens on the server.
- **List:** cards, not a table, newest submission first. Each card shows:
  - the activity title
  - "{School} · {activity type label} · {local date/time} · {participation}", where participation is "Not marked" or "{p} of {m} present"
  - a description list (`apps/web/components/ActivityFeedbackDetails.tsx`):
    - **Overall rating** ("n – Poor/Fair/Good/Very good/Excellent")
    - **School satisfaction**
    - **Trainer / Counsellor** ("Not recorded" when empty)
    - **Feedback**
    - **Suggestions** ("None" when empty)
    - **Submitted by** ("{name}, {local time}")
- **Pagination:** 25 per page, **"Load more"**, and "Showing {n} of {total}". There is no sort control.
- **States:**
  - "Loading activity feedback…"
  - Empty: **"No feedback submitted yet."**
  - Error: **"Could not load activity feedback."** with **"Try again"**.
  - 401: **"Your session has expired."** with "Sign in again".
- **Endpoint:** `GET /api/v1/overseas-admin/school-activity-feedback?school_id=&limit=25&offset=` (`school_feedback.py:162`).
- **Side effects:** none (read-only).

## 10. Admin-side endpoints with NO UI (as-built gaps)

| Endpoint | File:line | Notes |
|---|---|---|
| `POST /overseas-admin/school-staff/{staff_id}/portfolio` | admin.py:1829 | Add a school to a staff portfolio. No UI. No remove endpoint exists. |
| `GET /overseas-admin/school-staff` | admin.py:1711 | Staff with `school_ids`. No UI (the page uses the portal payload). |
| `GET /overseas-admin/school-students/lookup` | admin.py:1740 | Superseded by `/lookups/school-students`. |
| `GET /overseas-admin/school-students/{id}/transfer-history` | school_transfers.py:617 | Admin view of transfer history. No UI. |
| `POST/PATCH/GET /overseas-admin/academic-years` | admin.py:1590-1660 | Global academic-year calendar (draft→active→closed, forward-only). **No admin UI.** The coordinator promotion page reads `/school/academic-years/active`. VERIFICATION REQUIRED: how an operator creates the active academic year in production (API/seed only). |

## 11. Counts

**Frontend routes (Overseas Admin, school-related): 6.**
- `/overseas/admin/schools`
- `/overseas/admin/school-staff`
- `/overseas/admin/school-applications`
- `/overseas/admin/school-transfers`
- `/overseas/admin/activity-feedback`
- `/overseas/admin/school-analytics`

Also relevant: `/overseas/counselor/school-applications`.

**Backend endpoints in this area: 26.**
- **UI-used (17):**
  - `GET /portal/overseas/admin/{section}`
  - `POST /overseas-admin/schools`, `GET /overseas-admin/schools`, `GET /overseas-admin/schools/lookup`
  - `GET /overseas-admin/schools/{id}/tier-change-preview`, `PATCH /overseas-admin/schools/{id}`
  - `GET /overseas-admin/schools/bulk-template`, `POST /overseas-admin/schools/bulk-upload`
  - `POST /overseas-admin/school-staff`
  - `POST /overseas-admin/school-students/{id}/applications`, `GET /overseas-admin/school-applications`
  - `GET /lookups/schools`, `GET /lookups/school-students`
  - `GET /public/universities` (third party to this area)
  - `GET /overseas-admin/school-transfer-requests`, `POST .../approve`, `POST .../reject`
- **Also UI-used, counted separately (3):** `GET /overseas-admin/analytics/summary`, `GET /overseas-admin/analytics/schools`, `GET /overseas-admin/school-activity-feedback`.
- **No UI (6, §10):** portfolio add, school-staff list, school-students lookup, transfer-history, and academic-years (3 methods, listed as one row in §10).

## 12. Test data needed to demonstrate

1. **Overseas Admin login.** Seed `overseasadmin@edusphere.local` (`apps/api/app/seed.py:22`). **Super Admin** is `superadmin@edusphere.local` (`seed.py:16`), used to show the "Workspace not found" behaviour and the Analytics access.
2. **Working SMTP** (or `email_status` not_configured) to show both the green and amber create messages. A dev environment also returns `development_welcome_token`.
3. **Schools:**
   - The seed has one school, "Sunrise Public School" (Hyderabad, platinum, valid for 365 days, with a School ID) (`seed.py:619-627`).
   - For demos, add **at least 3 more**: one with no tier, one Bronze or Silver (to show the entitlement 403 on School Applications), and one with a `tier_valid_until` within 60 days (Renewal due) or already past (expired).
   - A second school is **required for transfers**.
4. **A bulk CSV** with mixed rows: 2 valid, 1 duplicate coordinator email, 1 bad tier, 1 duplicate name+city. This shows the mixed-result report.
5. **Staff accounts.** Seeded: academic1/academic2, careercounselor and psychometric, all in Sunrise's portfolio (`seed.py:634-654`). Create one new staff account with a 2-school portfolio, and one with an empty portfolio.
6. **School students** at a Gold or Platinum school, and at least one university in `/public/universities`, for the bridge. Also a student at a Silver school to show the denial.
7. **Transfer requests:**
   - At least 1 pending request filed by a coordinator, ideally a student with a linked parent and a draft or verified result, plus a pending parent invite to show the warnings.
   - A pending request to a school with **no** staff portfolio, to show the portfolio warning.
   - Some already-decided requests (approved, rejected, cancelled) for the filters.
8. **Activity feedback.** The seeded activities have no `activity_type`, so they are not feedback-eligible (`seed.py:684-686`). A coordinator must create a typed activity (career seminar, etc.) dated in the past and submit feedback for it. Do this at 2 schools to show the school filter.

## 13. Suggested screenshots (sequence-feature-step)

1. `01-schools-01-sidebar` shows the Overseas Admin sidebar with the School items highlighted.
2. `01-schools-02-partner-schools-table` shows the table with search, filter and pagination.
3. `02-create-school-01-empty-form`, then `02-create-school-02-filled`, `02-create-school-03-success-emailed`, and `02-create-school-04-warning-email-not-delivered`.
4. `02-create-school-05-error-email-exists` shows the 409.
5. `03-edit-school-01-lookup`, then `03-edit-school-02-loaded-form`, `03-edit-school-03-upgrade-success`, `03-edit-school-04-downgrade-confirm`, `03-edit-school-05-downgrade-saved`, `03-edit-school-06-no-changes`, and `03-edit-school-07-not-found`.
6. `03-tier-08-coordinator-notification` shows the school side receiving the tier notice (cross-reference to the coordinator guide).
7. `04-bulk-01-panel`, then `04-bulk-02-column-reference-open`, `04-bulk-03-template-downloaded`, `04-bulk-04-mixed-result-report`, and `04-bulk-05-file-error`.
8. `05-staff-01-table`, then `05-staff-02-create-form-portfolio-search`, `05-staff-03-success`, and `05-staff-04-no-schools-message`.
9. `06-school-apps-01-page` (both tables), then `06-school-apps-02-pick-school`, `06-school-apps-03-pick-student`, `06-school-apps-04-form`, `06-school-apps-05-success`, and `06-school-apps-06-tier-denied`.
10. `07-transfers-01-pending-queue`, then `07-transfers-02-warnings`, `07-transfers-03-approve-confirm`, `07-transfers-04-approved-message`, `07-transfers-05-reject-note`, `07-transfers-06-status-filter-all`, and `07-transfers-07-empty`.
11. `08-analytics-01-kpis`, then `08-analytics-02-utilization-table-flags`, `08-analytics-03-search`, `08-analytics-04-pagination`, and `08-analytics-05-super-admin-nav`.
12. `09-feedback-01-list`, then `09-feedback-02-school-filter`, and `09-feedback-03-empty`.
13. `10-superadmin-01-schools-workspace-not-found` documents the access limitation.

## 14. Top unknowns and decisions for the product owner (VERIFICATION REQUIRED)

1. **Super Admin is blocked from Schools, School Staff and School Applications** ("Workspace not found"), even though the panels and APIs allow the role. Is this intended? (§0.6)
2. **Staff portfolios cannot be changed after creation from the UI.** There is no remove API at all, yet the help text promises "filled in later". (§5)
3. **The academic-year calendar has no admin UI.** How is the active year created in production? (§10)
4. **Single create allows duplicate school names, but bulk rejects them.** Single create has no "Valid until" field. (§2, §4)
5. Changing only "Valid until" does not notify the school. Is that intended? (§3)
6. The School Transfers and Activity Feedback pages show the Overseas Admin sidebar to a Super Admin. (§7, §9)
7. The School Applications page shows duplicate tables, and its subtitle wording ("by Student ID") does not match the School→Student picker. (§6)
8. The exact Pydantic 422 wording and browser-native validation text were not run. Capture them in a browser.
9. Raw values shown in the generic tables (UUID "reference" column, lowercase tier and role values, ISO timestamps): should the guide describe them as-is?
