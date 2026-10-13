# mgmt-024 — Applications funnel dashboard (design)

Date: 2026-10-13 · Backlog: `docs/delivery/MANAGEMENT_COMMAND_CENTER_BACKLOG.md` mgmt-024, Appendix B "Funnels (§20)" · Source: `EVID-017`
§20 lines 787–849 (`DERIVED_BLUEPRINT`), scope authority M9/M13 (`EXPLICIT_APPROVAL`, 2026-10-08, registered as `DEC-SCOPE-186`).
Dependency mgmt-003: merged to `main` (PR #244). No migration.

## 1. What the item asks for

§20: "Show the entire application funnel" — Applications Created → Documents Complete → Submitted → Under Review → Offer → Accepted →
Deposit → CAS/COE → Visa → Visa Approved → Enrollment — and "Management should be able to filter by" Agent, Counselor, Country,
University, Course, Intake, Staff, Status.

M9: map to existing data, show "not tracked" otherwise. Created, Submitted, Offer, Deposit, Visa, Visa Approved and Enrollment are
computed; Documents Complete is derived where possible; Under Review, Accepted and CAS/COE show "not tracked". **No change to the overseas
workflow.**

Acceptance criteria (backlog): (AC1) each stage matches its definition; (AC2) filters narrow consistently. Edge: withdrawn applications.
Roles: partner, super_admin (operational tier, M13). Security: counts only. Performance: grouped.

## 2. Discovery (Graphify + code, `main@19b22fcc`)

| Class | Items |
|---|---|
| MUST CHANGE | `services/management_metrics.py` (`applications()`); `api/management.py` (`GET /management/applications`); `schemas.py` (`ApplicationFunnelOut`); web new `lib/managementApplications.ts`, `components/ManagementApplications.tsx`, `app/management/applications/page.tsx`; `lib/management.ts` (the "Applications" entry gets its `href`) |
| MAY CHANGE | `API_CONTRACT.md`, `RBAC_MATRIX.md`, `PRODUCT_DECISION_REGISTER.md`, backlog status line |
| SHOULD NOT CHANGE | `application_filters.py` (reused: its `apply()` only; `parse()` is the overseas-admin scope and stays theirs), `agent_applications.py` (its `OFFER_COUNTED_STATUSES` is reused), the overseas workflow, `snapshot()` |
| HIGH REGRESSION RISK | `MANAGEMENT_PILLARS` (mgmt-001 tests compute live links from it; they read it dynamically) |

Data: `overseas_applications` (owner: `student_id` / `agent_student_id` / `school_student_id`; `university_id`, `course_id`,
`counselor_id`, `agent_id`, `intake` text, `status`, `submitted_on`, `offer_type`, `created_at`), `universities.country_id`,
`student_documents` (`application_id`, `verification_status` pending|verified|rejected|changes_required), `document_requests`
(per **agent student**, not per application; open|fulfilled|cancelled), `application_deposits` (one per application; status),
`visa_cases` (`application_id`, `decision`), `application_status_history.changed_by_id`.

**Finding:** Appendix B says Documents Complete = "all `DocumentRequest`s for the application verified", but document requests belong to
an agency student, not an application, and are fulfilled/cancelled rather than verified. MF4 derives it from the application's own
documents plus the student's open requests.

## 3. Decisions (recommended answers, owner's standing instruction to proceed with recommended answers; `UNVERIFIED`)

| # | Point | Decision |
|---|---|---|
| MF1 | Population | Every overseas application: student-owned, school-bridged and agency. Withdrawn ones included (they were created, and reached the stages they reached) |
| MF2 | Period | Optional `date_from` / `date_to` on `created_at` as India calendar days (Appendix B "created in the period"); both empty = all applications. `date_to < date_from` → 422 |
| MF3 | Cohort | Each stage counts the filtered applications that meet its definition today (a cohort funnel, not dated events). Stages are not forced to be monotonic: each one is exactly its definition (AC1) |
| MF4 | Documents Complete (derived) | ≥ 1 document linked to the application, every linked document `verified`, and — for an agency application — no `open` document request for its agency student |
| MF5 | Submitted | `submitted_on` set |
| MF6 | Offer | The existing O5 rule (`agent_applications.counts_as_offer`): status in `OFFER_COUNTED_STATUSES` or an offer recorded (`offer_type`) |
| MF7 | Deposit | The application's deposit is `paid` or `remitted` (Appendix B, literally; `refunded` not counted) |
| MF8 | Visa / Visa Approved | A visa case exists / a visa case with decision `approved` |
| MF9 | Enrollment | Status `enrolled` |
| MF10 | Not tracked | Under Review, Accepted, CAS/COE: `value: null`, shown "Not tracked", never 0 |
| MF11 | Withdrawn | Reported separately as a count of the filtered applications with status `withdrawn` |
| MF12 | Filters | Agency (an agency org id or `none` = no agency; `application_filters.apply` semantics), Counselor (id or `none`), Country (university's country), University, Course, Intake (exact text), Staff, Status (exact). All AND-combined |
| MF13 | Staff | The EduSphere staff member (role `super_admin`, `overseas_admin` or `counselor`) who recorded a status change on the application (`application_status_history.changed_by_id`). Counselor = assigned; Staff = acted |
| MF14 | Filter values | Malformed id or `date` → 422; an unknown well-formed id narrows to 0 (counts only, nothing leaks). Options list only values present on applications (staff: those in history), sorted by label; inactive counselors/staff labelled "(inactive)" |
| MF15 | Query shape | The 9 computed figures (8 stages + withdrawn) are one `SELECT` of `count(*) FILTER (...)` (tested); options are a fixed number of grouped queries |
| MF16 | Access | Operational tier: partner, super_admin. Accountant and others 403 "Operational access required" / "Management access required"; signed out 401 |
| MF17 | Privacy | Counts only. No student names or ids. Option labels name agencies, counselors, staff, universities, courses |
| MF18 | Page | `/management/applications`: GET filter form (URL-held, so refresh/back/share keep it), funnel with count and % of Created, "Not tracked" rows, withdrawn note; "Applications" entry in the Students pillar goes live. super_admin keeps `SUPER_ADMIN_NAV` (as the snapshot page) |

## 4. Design

Backend
- `management_metrics.FUNNEL`: ordered `(key, label, tracked)` for the 11 stages.
- `management_metrics.applications(db, filters) -> dict`: builds the filtered `WHERE` (MF2, MF12, MF13) and one `select()` of
  `func.count().filter(<stage>)` per computed stage plus withdrawn. Stage predicates are correlated `EXISTS` on documents, document
  requests, deposits and visa cases.
- `management_metrics.application_options(db) -> dict`: the dropdown values (MF14).
- Route `GET /management/applications` with query params `date_from, date_to, agency, counselor, country, university, course, intake,
  staff, status`; parses `agency`/`counselor` (`none` or UUID), validates dates; returns `{filters, options, stages, withdrawn}`.

Frontend
- `lib/managementApplications.ts`: types, `applicationFilters(searchParams)` (drops repeated/malformed values), `applicationsUrl()`,
  `stageShare(value, created)`.
- `components/ManagementApplications.tsx`: the form (labelled selects + dates, Apply, Clear link) and the funnel (AGN-019 `.funnel`
  styles, untracked rows as upc-018's `.funnel-untracked`).
- `app/management/applications/page.tsx`: server page; 401/403 → access card; 422 → its message; other errors → "unavailable".

Error/empty states: zero applications → the funnel shows 0s and an "No applications match these filters" note.

## 5. Tests
- `tests/test_mgmt_024_applications.py`: access (partner/super_admin 200; accountant, overseas_admin, trainer 403; 401); each stage as a
  delta on fixtures (AC1) incl. withdrawn and refunded deposit; every filter narrows to its fixture (AC2); date validation; one
  statement for the stage counts.
- `tests/lib/managementApplications.test.ts`, `tests/components/ManagementApplications.test.tsx`, `tests/e2e/mgmt-024-applications.spec.ts`.
