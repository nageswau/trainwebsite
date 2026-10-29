# nehn-017 — HR access to permitted student progress, attendance and documents, plus HR reports (design)

Decision: `DEC-SCOPE-310` · API §12HH · RBAC §2.221 · migration `0219_hr_student_grants` (seed only).
Source: `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` §E `nehn-017` (DERIVED_BLUEPRINT over the ORIGINAL_REQUIREMENT
§13 L277-286, §5 L116-121, §15 L337-347). Dependencies nehn-003 (private serving), nehn-005 (permission engine), nehn-008 (field
policy) and nehn-010 (training reports) are merged.

The session ran in autonomous mode: the owner asked for recommended defaults instead of questions. Every choice marked
**(builder's default)** is `NEEDS_CONFIRMATION` by the client (OD-09) and is listed in the decision register.

## 1. Intent

HR (`hr_team`) checks a candidate's training before hiring: progress, completion, attendance and selected documents. HR also downloads
HR reports. Every view is read-only and gated by permission-matrix grants (nehn-005), so an administrator can switch off any part per
role or per user (nehn-007 overrides). HR never receives financial or unrelated recruitment data.

**Non-goals.** No HR write paths. No recruiter requirements module for HR (Q-28 stays). No certificate PDF downloads. No new
document storage. No change to the student's own document routes.

## 2. Builder's defaults (NEEDS_CONFIRMATION, OD-09)

- **H1 Population.** HR sees the IT students in the active placement pool: `it_student`, division `it`, not withdrawn from placement.
  This is the same population HR's existing *Candidate Database* section already lists, so no new person is exposed. Overseas students
  are excluded. The rule lives in one helper, `services/hr_students.population()`, and the Candidate Database section reads it too.
- **H2 Allowed document types.** A `ProfileDocument` is open to HR when its free-text `document_type`, trimmed and lower-cased, is one
  of `resume`, `cv`, `curriculum vitae`, `portfolio`, `certificate`, `certificates`. Every other type (ID proof, Aadhaar, bank, fee
  receipts, …) is closed: it is left out of the list, and a direct download returns 403. Unknown types fail closed.
- **H3 Grants.** There are three new catalogue resources, each named after the data it opens:
  - `student_progress` (view, download): the HR Students pages, plus the `hr-progress` and `hr-completions` reports.
  - `attendance` (view, download): the attendance block on a student and the `hr-attendance` report.
  - `student_documents` (view, download): the allowed-type document list and its downloads.

  `hr_team` holds all six keys by default (migration 0219 seeds them). No other role gets a default grant. super_admin holds every key
  implicitly.
- **H4 Seats shown.** A seat is shown when its status is counted or dropped. `pending_consent` and `rejected` never took the seat and
  are not shown (nehn-010 C2). *Completed* means a counted seat with progress ≥ 100 (C1).

## 3. Backend

### Reports (`services/reports/training.py`)
- `_scope` gains an HR rule: for a role in `HR_ROLES = {"hr_team"}`, a batch is in scope when one of its seats belongs to a student in
  the population. `_seats` adds the student-level condition, so HR seat rows are only population students.
- Three reports are registered with the training columns and queries:
  - `hr-progress` (resource `student_progress`): the columns of report (a).
  - `hr-completions` (resource `student_progress`): the columns of report (d).
  - `hr-attendance` (resource `attendance`): the columns of report (e).

  None of them has a `financial` column. Payments and discounts are never joined (AC3).
- HR does not get `reports.training`. If an administrator grants it anyway, the HR rule applies to those reports too (scope is by role).

### HR student API (`api/hr_students.py`, prefix `/hr/students`)
Each route checks the grant first (403), then the role scope (H1; another granted role gets 403, deny by default), then the student
(404 outside the population, so nothing confirms that a student exists).

| Route | Grant | Returns |
|---|---|---|
| `GET /hr/students?q=&page=` | `student_progress.view` | `{items:[{id, student_code, full_name, courses, completed}], total, page, page_size}`, ordered by name; `q` matches code, name or email (max 100 chars); 25 per page |
| `GET /hr/students/{id}` | `student_progress.view` | `{student, seats:[{course, batch, trainer, status, progress, completed, certificate, attendance?}], documents?, can:{attendance, documents, download}}` |
| `GET /hr/students/{id}/documents/{doc}/download` | `student_documents.download` | `{url, expires_in}` (nehn-003 presigned/private). The audit row `hr.student_document_download` commits before the URL is returned. A closed type returns 403. |

- `attendance` is present on each seat only with `attendance.view`; `documents` is present only with `student_documents.view`. The
  keys are omitted, not set to null.
- Attendance figures come from `training_progress.attendance` (the same SQL as eligibility and report (e)).
- Logging: ids and the route only, never names or document types' values.

### Portal (`services/portal.py`)
- The HR exclusion on the `reports` section is removed, as the backlog asks. HR now gets the existing Placement Reports summary: job
  and offer counts, nothing financial.
- The Candidate Database section uses `hr_students.population()`. Its behaviour is unchanged.

## 4. Frontend

- The `it/hr` nav adds: Students (`/it/hr/students`, tagged `student_progress` so a revoked grant hides it), Reports (`/it/hr/reports`)
  and Report library (`/it/hr/report-library`).
- `/it/hr/report-library` uses the existing `ReportLibraryPage` (`roles=["hr_team"]`).
- `/it/hr/students` is a server page with a search box (GET form), a table (Student ID, name, courses, completed, open link) and
  pagination. It has empty and error states and uses the access card on 401/403.
- `/it/hr/students/[id]` is a server page with a seats table (course, batch, trainer, status, progress %, completed, certificate,
  attendance % when present), an attendance breakdown when present, and a documents list with a client "Download" button (busy state,
  inline error). "Not available to your role" is shown when a block is withheld. On a phone the tables use `.table.stack`.

## 5. Acceptance criteria → tests

1. HR sees a student's attendance %, progress % and completion state, and nothing financial. Tested by pytest (detail keys; no
   payment, fee or discount keys) and by browser checks.
2. HR opens only the allowed document types: the list hides closed types, and downloading a closed type returns 403. A document of
   another student returns 404. A download writes an audit row. Tested by pytest and the browser.
3. HR downloads the HR attendance report, and it has no payment or discount column. Tested by pytest (CSV header) and the browser.
4. With HR's `attendance.view` revoked (a role grant or a user deny override), the attendance block is absent and
   `GET /reports/hr-attendance` returns 403. The library and the UI hide them. Tested by pytest and the browser.
5. Population: a withdrawn or overseas student returns 404 and is absent from the list and the reports. A placement_team user given
   the grant gets 403. Tested by pytest.
6. Regression: the nehn-010 training report tests, the nehn-005 grant tests and the HR portal section tests stay green. Tested by
   pytest.
7. Negative: HR opening `/admin/payments` gets 403 (the existing route). Tested by pytest.

## 6. Risks
- The `_scope` change touches every training report. The trainer and admin branches stay first and unchanged, and the nehn-010 tests
  guard them.
- Free-text document types make H2 conservative: a resume typed as "My CV 2026" stays closed until the client confirms the list.
- nehn-016 (recruiter) is being built in parallel and edits the same `_scope`. Merge it main-first.
