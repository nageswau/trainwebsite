# AGN-023 — EduSphere counselor assignment for overseas applications: Design

**Status:** Sections 1–3 approved by the owner in-session 2026-10-06; this written spec is for the owner's review.
**Branch:** `feature/agn-023` (from `origin/main` `2b22158b`). **Decision:** `DEC-SCOPE-089` (next free on `main` @ `2b22158b`).
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

**Owner's answers (in-session, 2026-10-06, `EXPLICIT_APPROVAL`):**

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

### 3.3 Admin list data

`portal.py` "Application Tracking" payload, `overseas_admin` only: two new columns, **Agency** (the org name for an agency
application, blank otherwise) and **EduSphere counsellor** (the counselor's name, or "Not assigned"), and a filter
**Agency, no counsellor** (`agent_id IS NOT NULL AND counselor_id IS NULL`). The counselor and university_rep payloads are
unchanged.

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

- **Admin, Overseas → Applications:** the two §3.3 columns and filter; an **Assign counsellor** action per row (**Change
  counsellor** when one is set) that opens a picker of active overseas counselors (from `GET /admin/users?role=counselor`,
  inactive users dropped client-side), calls §3.1, and shows "{name} assigned." or the API's message. No clear option.
- **Agency application detail** (Master and Staff): a line **EduSphere counsellor: {name}**, or *Not assigned yet*. The
  agency application detail payload gains `counselor_name` (name only).
- **Counselor:** no new screen. Agency applications appear in the existing Applications, Visa and Document Verification
  sections once assigned.

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
| AC15 | The Admin screen shows the Agency and EduSphere counsellor columns and the "Agency, no counsellor" filter; the picker lists active overseas counselors only. |

## 9. Tests (lite runs per task; the owner runs full suites)

- **API (pytest):** `test_agn_023_assign.py` (AC01–AC08), `test_agn_023_counselor_scope.py` (AC09–AC13), plus AC14 in the
  agency detail tests. Real HTTP calls through the test client, never reasoning alone.
- **Web (vitest):** the picker and action (AC15), the agency counselor line (AC14).
- **E2E (Playwright), one flow:** Admin assigns → counselor sees and advances (not to Enrolled) → agency sees the name.
- **Regression to re-run (lite):** `test_agn_008_*`, `test_agn_012_*`, `test_agn_013_*`, `test_agn_017_*`, the OVS-003 and
  VISA-001–003 counselor tests, `test_agn_003_matrix.py`.

## 10. Regression risks

- Existing tests or scripts that set `counselor_id` through the generic PATCH now get `422`: find and move them to §3.1.
- The counselor visa PATCH now needs the application row lock on agency applications; keep the lock order (application, then
  visa case) the same as the agency route to avoid deadlocks.
- The documents queue outer join must not widen the counselor's scope: it stays filtered by the counselor's `app_ids`.

## 11. Documents to update

`PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-089`), `API_CONTRACT.md` §12M, `RBAC_MATRIX.md` (§2.7 counselor and the AGN-008
notes), `MASTER_FEATURE_CATALOG.md` / `AGENT_CRM_BACKLOG.md` (AGN-023), `PRD_OPEN_ITEMS.md` item 84 (resolved by `DEC-SCOPE-089`),
the RTM.
