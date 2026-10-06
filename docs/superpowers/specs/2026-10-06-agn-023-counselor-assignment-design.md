# AGN-023 — EduSphere counselor assignment for overseas applications: Design

**Status:** Built on `feature/agn-023` (2026-10-06); lite backend set and vitest green; the AGN-023 e2e spec is pending (Task 7); full backend suite deferred to the owner. Sections 1–3 approved by the owner in-session 2026-10-06; H11–H12 (filters, counselor screen limits) added at the spec review the same day.
**Branch:** `feature/agn-023` (rebased on `origin/main` `4e5730ee`). **Decision:** `DEC-SCOPE-090` (drafted as `089`; bdm-020 took `089` on `main` @ `4e5730ee`).
**API contract:** §12M. **Migration:** none (`overseas_applications.counselor_id` exists).
**Resolves:** `PRD_OPEN_ITEMS.md` item 84 (hand-off of an agency application to an EduSphere counselor).
**Builds on:** AGN-008 (`DEC-SCOPE-050`, agency applications, A6 visibility), AGN-012 (`DEC-SCOPE-057`, agency visa,
`agent_visa.update_case`), AGN-013 (`DEC-SCOPE-054`, Master-only enrollment), AGN-017 (`DEC-SCOPE-059`, agency notices),
OVS-003 (counselor `/advance`), VISA-001–003 (counselor visa routes), tel-017 (`DEC-SCOPE-076`, `_require_overseas_counselor`).
**Evidence:** the owner's in-session answers below (`EXPLICIT_APPROVAL`); the code as built on `main` @ `2b22158b`.

## 1. Intent

**Problem (item 84):** an application an agency creates has no `counselor_id`, and nobody at EduSphere is notified. A counselor
sees only applications where `counselor_id` is their own. The Overseas Admin can set `counselor_id` only through the generic
`PATCH /workflows/overseas/applications/{id}`, and no screen does it.

**Owner's answers (in-session, 2026-10-06, `EXPLICIT_APPROVAL`; H11–H12 added at the spec review):**

| # | Decision |
|---|---|
| H1 | **Purpose: the counselor supports the agency.** The agency keeps ownership of the application; the counselor is EduSphere's point of contact. |
| H2 | **The Overseas Admin assigns**, and can change the counselor later. |
| H3 | **At any open stage.** Not on a `withdrawn` or `enrolled` application. No stage gate. |
| H4 | **On an agency application the counselor may move stages forward and edit the visa case**, under the agency's own visa rules, and verify documents. **Never `enrolled`**: enrollment stays with the agency Master (`DEC-SCOPE-054` E1). |
| H5 | **Notify** the new counselor, the agency (AGN-017 recipient rule) and, on a change, the previous counselor. |
| H6 | **The counselor sees the application only**: no agency counseling record, budget, shortlist, student email or phone. |
| H7 | **The agency sees the counselor's name only** on the application detail. |
| H8 | **Swap only.** Once set, the counselor can be changed but not cleared. |
| H9 | **The assign action covers every overseas application** (agency, self-service, school-bridged). H4 and H6 apply to agency applications only. |
| H10 | **Approach A:** a dedicated Admin-only assign route; `counselor_id` leaves the generic update. |
| H11 | **Filters** on the Students and Applications lists: the Overseas Admin filters by Agency and by Counsellor; a counselor filters by Agency only. |
| H12 | **On an agency application the counselor's screens offer only what is allowed:** the stage list hides **Enrolled** (with the note "Enrollment is confirmed by the agency"), and the visa stage list offers forward stages only. |

**Definition:** an *agency application* is an `OverseasApplication` with `agent_id IS NOT NULL`.

## 2. Out of scope

- Automatic or per-agency default counselors; counselor self-claim from a queue.
- Recording the visa decision (Approved/Refused) by a counselor. It stays with the agency (AGN-012).
- Changing how the Overseas Admin or a university_rep sets `enrolled` through the generic update (`DEC-SCOPE-054` E4 tolerates it).
- Counselor appointments or counselor-chat for agency students with no login (both need a `student_id`; unchanged).
- Choosing a counselor at creation (`POST /workflows/overseas/applications`, school bridge): unchanged.

## 3. API

### 3.1 `PUT /workflows/overseas/applications/{id}/counselor` (new, §12M)

Body: `{ "counselor_id": "<uuid>" }` (required, not null). Response `200`:
`{ "id", "counselor_id", "counselor_name", "changed": bool }`.

Order of checks (inline pattern: role, division, then scope; never `require_role`):

1. Role `overseas_admin` and division `overseas`, else `403`.
2. Body validation: `counselor_id` missing or null → `422` (H8, swap only).
3. Load the application under a row lock (`with_for_update`); none → `404 "Application not found"`.
4. `withdrawn` or `enrolled` → `409 "This application is closed"` (H3).
5. The chosen user: `role == "counselor"`, `division == "overseas"`, `active` → else `422 "Choose an active overseas counselor"`.
   This extends `_require_overseas_counselor` with the `active` check, used by this route only.
6. Same counselor as now → `200` with `changed: false`; no write, no notice, no audit.
7. Write `counselor_id`; add an `ApplicationStatusHistory` row with `from_status == to_status` (the current stage) and
   `notes = "EduSphere counsellor assigned"` (first assignment) or `"EduSphere counsellor changed"`; audit
   `overseas.application.counselor_assign` with `{from_counselor_id, to_counselor_id}`; send the §5 notices; commit.

### 3.2 Generic update loses `counselor_id`

`PATCH /workflows/overseas/applications/{id}`: a body that sets `counselor_id` → `422 "Use Assign counselor to change the
counselor"`, for every caller (counselor, university_rep, overseas_admin). `counselor_id` leaves the `allowed` set.
`OverseasApplicationUpdate` keeps the field so the refusal is explicit, not a silent drop.

### 3.3 Application list data and filters (H11)

The "Application Tracking" payload in `portal.py` backs both the **Students** and **Applications** sections for
`overseas_admin` and `counselor` (one table, `section in {"students", "applications", ...}`), so every change here shows on both.

**Columns:**

- `overseas_admin`: two new columns, **Agency** (the agency's org name for an agency application, blank otherwise) and
  **EduSphere counsellor** (the counselor's name, or "Not assigned").
- `counselor`: a new **Agency** column (blank for a non-agency application). No counsellor column, because every row is their own.
- `university_rep`: unchanged.

**Filters** (H11) are optional query parameters on `GET /portal/{division}/{role}/{section}`. They are applied in SQL
**before** the existing 500-row limit, so a filtered list is complete up to that limit:

| Parameter | Values | Who may use it |
|---|---|---|
| `agency` | an agency org id; `any` (every agency application); `none` (not from an agency) | `overseas_admin`, `counselor` |
| `counselor` | an overseas counselor's user id; `none` (not assigned) | `overseas_admin` only |

- The filters combine with AND. For example, `agency=any&counselor=none` gives agency applications still waiting for a counselor.
- A malformed value, or an id that doesn't resolve to an agency org or an overseas counselor, gets `422 "Unknown filter value"`.
- `counselor=` sent by a counselor or a university_rep, or `agency=` sent by a university_rep, gets `422 "Filter not available"`.
- On any other section, either parameter also gets `422 "Filter not available"`. It is never silently ignored.
- Each row carries `is_agency: bool`, so the counselor's screens can apply H12 without a second request.
- The filters only narrow the caller's existing scope and never widen it. A counselor filtering on an agency still sees only
  their own applications.
- The payload carries `filters`: the applied values plus the **option lists** for the dropdowns.
  - Admin agency options: every agency org with at least one overseas application.
  - Counselor agency options: only the agencies on the counselor's own applications, so no agency names outside their caseload leak.
  - Admin counsellor options: every overseas counselor, including inactive ones, because past assignments can still name them.
    Inactive counselors are marked "(inactive)".

## 4. Counselor on an agency application (H4, H6)

All checks below run only when `agent_id IS NOT NULL`; other applications keep today's behavior exactly.

| Route | Change |
|---|---|
| `POST /overseas/applications/{id}/advance` | `to_status == "enrolled"` → `403 "Only the agency's Master confirms enrollment"`, checked before any write. Every other forward move is unchanged and keeps the AGN-017 `status_changed` notice. |
| `POST /overseas/visa` | Agency rules from AGN-012: the application must be at an offer stage or later (`OFFER_STAGES_ON`, else `422 "An offer is needed before a visa case"`); `enrolled` → `409` `VISA_ENROLLED`; the case starts at `checklist` (another `status` → `422`); one case per application (`409` `VISA_EXISTS`, as today). The application row is locked first, as the agency route does. |
| `PATCH /overseas/visa/{id}` | Lock the application row, then: `enrolled` → `409` `VISA_ENROLLED`; then route the change through `agent_visa.update_case` with `expected_stage` = the stage read under the lock, `to_stage` = the requested `status` (when it differs), and `checklist`. That applies the decided lock, forward only, checklist-stage-only edits and the checklist verification gate. `tracking_reference` and `appointment_date` keep their current handling. No decision field is accepted from a counselor. |
| `PATCH /overseas/documents/{id}/verify` | Unchanged (already scoped through the application; the agency notice already fires). |
| Counselor **Document Verification** queue (`portal.py` documents section) | The inner join on `User` becomes an outer join, and the name falls back to the agency student record (`OWNER_NAME`), so agency documents for a student with no login appear. |

**Application-only view (H6):** no counselor-facing payload, lookup or route returns `AgentStudent` email, phone,
counseling, budget or shortlist fields. The existing list shape already carries only the owner's name; tests pin this.

## 5. Notifications (H5)

In-app plus email through the existing helpers. None on a same-counselor re-pick.

| Recipient | Title | Body | Link |
|---|---|---|---|
| New counselor (`_notify_user`) | "Application assigned to you" | "{student name} — {university}" (internal staff; already visible to them) | `/overseas/counselor/applications` |
| Previous counselor, on a change | "Application reassigned" | "An application has moved to another counselor." (no student name; access ends) | `/overseas/counselor/applications` |
| Agency, agency applications only (`agency_notices`, AGN-017 `recipients()`: the assigned member, else active Masters; never the actor; active org only) | "EduSphere counsellor assigned" / "EduSphere counsellor changed" | No names, as AGN-017 bodies | the agency application detail |

A send failure never rolls back the assignment (existing `_notify_user` / `queue_deliveries` behavior).

## 6. Frontend

**Overseas Admin, Overseas → Applications and Students** (the same table):

- The §3.3 columns.
- An **Assign counsellor** action on each row (it reads **Change counsellor** when one is set). It opens a picker of
  **active** overseas counselors, taken from `GET /admin/users?role=counselor` with inactive users dropped client-side.
  It calls §3.1 and shows "{name} assigned." or the API's message. There is no option to clear the counsellor.

**Filter bar** (H11), above the table:

- **Agency:** All · Any agency · Not from an agency · each agency. Both the Admin and the counselor get this.
- **Counsellor:** All · Not assigned · each counselor. Admin only.
- The chosen values live in the page URL (`?agency=…&counselor=…`), so a filtered view can be bookmarked or shared and
  survives a reload.
- A **Clear filters** link resets them.
- The table's empty state reads "No applications match these filters".
- After an assignment, the list reloads with the same filters.

**Agency application detail** (Master and Staff):

- A line **EduSphere counsellor: {name}**, or *Not assigned yet*.
- The agency application detail payload gains `counselor_name` (name only).

**Counselor screens:** no new page. Agency applications appear in the existing Applications, Students, Visa and Document
Verification sections once assigned. On a row with `is_agency` (H12):

- **Advance stage** (`CounselorEvaluationPanel`): the stage list leaves out **Enrolled** and shows the note "Enrollment is
  confirmed by the agency". Other forward stages are offered as today.
- **Visa:** the stage list offers only the stages after the case's current stage. No stage is offered once a decision is
  recorded or the application is enrolled; the panel shows the matching message ("The visa decision is recorded…" /
  "This application is enrolled…") instead. The checklist editor is shown only at the checklist stage.
- The server still enforces every rule in §4. The screens only stop offering choices that would be refused.

## 7. Security

- Only `overseas_admin` can change `counselor_id` after creation (§3.1, §3.2). A counselor can no longer hand a case to another
  counselor with no notice or history.
- An IT counselor or an inactive user can never be assigned (§3.1 step 5).
- A counselor's reach into an agency application stays limited to `counselor_id == self` (`_assigned_application`, unchanged);
  the previous counselor loses access on a change.
- The counselor cannot reach `enrolled` on an agency application, so the commission is created only through the Master's
  enrollment route with its date and university student ID (`DEC-SCOPE-054`).
- Agency notice bodies carry no names (AGN-017). The agency sees the counselor's name only, never email or phone (H7).
- Every assignment is audited with the old and new counselor.

## 8. Acceptance criteria

| ID | Criterion |
|---|---|
| AC01 | The Overseas Admin assigns an active overseas counselor to an unassigned application; it appears in that counselor's Applications list; a history row and audit entry are written. |
| AC02 | Changing to another counselor moves access: the previous counselor gets `403` on the application; the new one sees it. |
| AC03 | Any role other than `overseas_admin` gets `403` on §3.1; an unknown application `404`. |
| AC04 | A null or missing `counselor_id`, an IT counselor, a non-counselor or an inactive counselor → `422`; nothing changes. |
| AC05 | A `withdrawn` or `enrolled` application → `409`; nothing changes. |
| AC06 | Re-picking the same counselor → `200`, `changed: false`, no history, audit or notice. |
| AC07 | `PATCH /overseas/applications/{id}` with `counselor_id` → `422` for counselor, university_rep and overseas_admin. |
| AC08 | Notices: the new counselor always; the previous counselor on a change; the agency (AGN-017 recipients) on an agency application only; agency bodies contain no names. |
| AC09 | On an agency application the counselor's `/advance` to `enrolled` → `403`; no commission row is created; a forward move to another stage works. |
| AC10 | On an agency application the counselor's visa create/update obeys the AGN-012 rules (offer needed, starts at checklist, enrolled lock, decided lock, forward only, checklist lock, checklist gate). |
| AC11 | A non-agency application keeps today's counselor visa and advance behavior (regression). |
| AC12 | The counselor's Document Verification queue lists documents of an assigned agency application whose student has no login; verify/reject works. |
| AC13 | No counselor-facing response contains an agency student's email, phone, counseling, budget or shortlist. |
| AC14 | The agency application detail shows the counselor's name, or "Not assigned yet"; no email or phone. |
| AC15 | The Admin screen shows the Agency and EduSphere counsellor columns; the picker lists active overseas counselors only. |
| AC16 | Admin filters: `agency=<id>`, `any` and `none`, and `counselor=<id>` and `none`, each return exactly the matching rows. Combined, they AND together (`agency=any&counselor=none` = agency applications with no counselor). Filtering happens before the 500-row limit. |
| AC17 | A counselor's `agency=` filter returns only their own matching applications. Their agency options list only agencies on their own applications. Their `counselor=` → `422`. |
| AC18 | A malformed or unknown filter value → `422 "Unknown filter value"`. A filter on another section, or from a university_rep → `422 "Filter not available"`. |
| AC19 | The filter bar keeps its values in the URL, survives a reload, and **Clear filters** resets it. The empty state reads "No applications match these filters". |
| AC20 | On an agency application the counselor's stage list has no **Enrolled** and shows "Enrollment is confirmed by the agency". A non-agency application still offers **Enrolled**. |
| AC21 | On an agency application the counselor's visa stage list offers only forward stages. It offers none once the decision is recorded or the application is enrolled, and shows the matching message instead. |

## 9. Tests (lite runs per task; the owner runs full suites)

- **API (pytest):** real HTTP calls through the test client, never reasoning alone.
  - `test_agn_023_assign.py`: AC01–AC08.
  - `test_agn_023_counselor_scope.py`: AC09–AC13.
  - `test_agn_023_filters.py`: AC16–AC18, including a case with more than 500 rows.
  - AC14 goes in the agency detail tests.
- **Web (vitest):**
  - The picker and action (AC15).
  - The filter bar with URL state (AC19).
  - The counselor stage and visa lists (AC20–AC21).
  - The agency counselor line (AC14).
- **E2E (Playwright), one flow:**
  1. The Admin filters to "Any agency / Not assigned" and assigns a counselor.
  2. The counselor filters by that agency, sees no **Enrolled** option, and advances the application.
  3. The agency sees the counselor's name.
- **Regression to re-run (lite):** `test_agn_008_*`, `test_agn_012_*`, `test_agn_013_*`, `test_agn_017_*`, the OVS-003 and
  VISA-001–003 counselor tests, `test_agn_003_matrix.py`.

## 10. Regression risks

- Existing tests or scripts that set `counselor_id` through the generic PATCH now get `422`: find and move them to §3.1.
- The counselor visa PATCH now needs the application row lock on agency applications; keep the lock order (application, then
  visa case) the same as the agency route to avoid deadlocks.
- The documents queue outer join must not widen the counselor's scope: it stays filtered by the counselor's `app_ids`.
- The portal section route gains query parameters. Callers that send none must get exactly today's payload, apart from
  the new columns, `is_agency` and `filters`. The dashboard and the other sections that share the same application query
  must not pick up a filter by accident.

## 11. Documents to update

`PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-090`), `API_CONTRACT.md` §12M, `RBAC_MATRIX.md` (§2.7 counselor and the AGN-008
notes), `MASTER_FEATURE_CATALOG.md` / `AGENT_CRM_BACKLOG.md` (AGN-023), `PRD_OPEN_ITEMS.md` item 84 (resolved by `DEC-SCOPE-090`),
the RTM.
