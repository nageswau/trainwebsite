# ENH-005 — Student School Transfer / Reassignment — Design

**Status:** Design approved by the user in-session, 2026-09-21 (`EXPLICIT_APPROVAL`): four policy
decisions in §3 plus the section-by-section design with "yes". Written spec awaiting the user's review.
Implementation not started.

**Traceability:** user instruction ("changing of schools etc.", recorded in
`docs/delivery/ENHANCEMENT_BACKLOG.md` ENH-005, `DERIVED_BACKLOG`) → `DEC-SCOPE-021` (proposed by this
spec, to be registered — see §12) → ENH-005 → this spec → plan (`docs/superpowers/plans/`) → tests → code.
ENH-005 has no hard dependency, but the backlog (§2 ordering, ENH-008 note, ENH-009 note) recommends
resolving multi-school parents (ENH-008) and Branch scope (ENH-009) first. Neither is built; §3 D1 and
§13 record how this design copes without them.

**Acceptance-criteria numbering:** `AC-nn` below is local to this spec. Do not cite it from
`API_CONTRACT.md`/`RTM.md` as a source-document ID; cite `DEC-SCOPE-021` and `ENH-005`.

## 1. Problem (audit result, gap confirmed)

`SchoolStudent.school_id` is a plain FK set at creation and never changed. No endpoint moves a student
between schools. Three facts make a naive "update `school_id`" unsafe:

1. **Parents are pinned to one school.** Every School-role scope check trusts a single
   `user.profile["school_id"]` (`schools.py:264` `_own_school_id`). `_load_readable_student`
   (`schools.py:864-880`) returns `403` when `student.school_id != profile.school_id`, and
   `_scoped_students_query` (`schools.py:643-656`) filters parents by school *and* link. A moved
   student's parent would be locked out of their own child.
2. **ENH-004's promotion lock assumes `school_id` is immutable.** `schools.py:1234-1237` (and the
   ENH-004 plan) says "`school_id` never changes after creation (DATA_MODEL.md §6.11), so there is no
   check/use gap". Transfer removes that invariant.
3. **Most student-linked data is keyed by student only.** `SchoolAcademicResult`, `SchoolCareerRecord`,
   `SchoolPsychometricRecord`, `SchoolTestPrepRecord`, `SchoolLanguageRecord`,
   `SchoolActivityAttendance` and `OverseasApplication.school_student_id` carry no `school_id`. The
   staff-portfolio scope (`SchoolStaffAssignment`, `_student_in_portfolio`, `_portfolio_school_ids`) and
   every reader scope resolve through the student's *current* `school_id`, so a bare update silently
   re-homes all of it, including unpublished work, to the new school.

## 2. Goals and non-goals

**Goals**
- A student can move from one school to another through a coordinator-initiated, admin-approved
  request.
- Every dependent relationship is handled by an explicit, tested policy (§3), never left dangling or
  silently cross-visible.
- Transfer history is retrievable per student.
- Neither school's coordinator can change a student's school unilaterally.
- Existing behavior, contracts and data are preserved (§8 lists the only forced changes).

**Non-goals (recorded, not built)**
- Bulk transfer (one student per request).
- Reversal as a distinct feature. A reverse transfer is a new request in the opposite direction.
- Branch moves inside one school entity (ENH-009).
- Full multi-school parent management (ENH-008): see the limit in §13.
- Graduation/alumni handling (ENH-004's open item).
- Freezing career/psychometric/test-prep/language records as old-school history (decision D4).
- Any change to `student_code`, `AcademicYear`, attendance rows, or bridged Overseas applications.

## 3. Decisions confirmed in-session (2026-09-21)

| # | Question | Decision |
|---|---|---|
| D1 | Parent access after transfer | **Link-based scope.** `SchoolParentLink` is preserved. A parent's access to a student and their child list are decided by the link alone, not by the parent's school. **Additionally**, if a linked parent has no other child still at the losing school after the transfer, that parent's account moves to the gaining school (`profile.school_id` rewritten). A parent who still has a child at the losing school stays there. |
| D2 | Authority | **Coordinator requests, admin approves.** Either school's coordinator may file a request. Approval and rejection are admin-only. The approval is the single action that performs the move. |
| D3 | In-flight academic results | **Withdraw and freeze.** Draft and Verified results become `withdrawn` (kept, never deleted), hidden from every list and average, uneditable. Published results stay with the student. |
| D4 | Career / psychometric / test-prep / language records | **Follow the student, unchanged.** No schema change, no data movement. |

Assumptions made by the design and confirmed with the user's approval of it:

- **A1.** "Admin" means `overseas_admin` and `super_admin` — the actors that already manage cross-school
  data in `admin.py` (`school-staff`, `school-students/lookup`). `counselor` and every School role are
  denied.
- **A2.** "One action" (backlog acceptance criterion 1) means the admin's approval performs the entire
  move; the coordinator's request is a separate earlier step.
- **A3.** The incoming-request endpoint returns the same `202` for every input, to avoid a cross-school
  existence oracle (§6).

Decisions taken by the design without a separate question (consequences of D1–D4):

- Approval clears `assigned_teacher_user_id` (the teacher belongs to the losing school) and
  `pending_parent_email` (the pending invite belongs to the losing school and `accept_invite`
  only links students at the invite's own school, `schools.py:245-247`, so it could never resolve).
- Notifications are sent **after** the commit; a send failure is logged, never raised.

## 4. Approach

Chosen: **one table, `school_student_transfer_requests`, that is both the request workflow and the
per-student transfer history.** Approval is a single transaction that changes the student and its
dependents and stamps the request `approved` with an outcome summary.

Rejected:
- *Request table plus a separate append-only ledger (ENH-004 style).* An approved request row already
  carries from/to, actor, time and outcome, so a ledger duplicates columns and adds a table.
- *No table; the "request" is only a notification and the admin edits the student directly.* No audit of
  who asked, nothing to cancel or track, no per-student history.

A new module `apps/api/app/api/school_transfers.py` holds the feature, with two routers: `/school`
(coordinator routes) and `/overseas-admin` (admin routes), both registered in `main.py`. `schools.py`
(2,032 lines) and `admin.py` (1,348 lines) do not grow. The module imports existing helpers
(`_require_coordinator`, `_own_school_id`, `_load_readable_student`, `_notify_parent`), as `admin.py`
already imports `_notify_student_parents` from `schools.py`. No new dependency.

## 5. Data model and behavior

### 5.1 New table `school_student_transfer_requests` (migration `0034`, down-revision `0033`)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `school_student_id` | UUID FK `school_students.id`, indexed | |
| `from_school_id` | UUID FK `schools.id` | the student's school at filing time |
| `to_school_id` | UUID FK `schools.id` | never equal to `from_school_id` (CHECK) |
| `requested_by_user_id` | UUID FK `users.id` | the filing coordinator |
| `requested_side` | String(10) | `losing` or `gaining` |
| `status` | String(20), default `pending` | `pending` / `approved` / `rejected` / `cancelled` |
| `reason` | Text, nullable | coordinator free text, length-capped in the schema |
| `decided_by_user_id` | UUID FK `users.id`, nullable | admin (approve/reject) or coordinator (cancel) |
| `decided_at` | DateTime(tz), nullable | |
| `decision_note` | Text, nullable | admin reject note |
| `outcome` | JSON, nullable | set on approval: `parents_moved`, `parents_kept`, `results_withdrawn`, `teacher_cleared`, `pending_parent_email_cleared` |
| `created_at`/`updated_at` | `TimestampMixin` | |

- **Partial unique index** `uq_school_transfer_pending_student` on `(school_student_id) WHERE status = 'pending'`
  (SQLAlchemy `Index(..., unique=True, postgresql_where=text("status = 'pending'"))`): at most one open
  request per student, enforced by the database.
- **Non-destructive migration:** creates one table and indexes; no backfill; no existing row is touched.
  Downgrade drops the table. Any `withdrawn` result rows written after upgrade stay in
  `school_academic_results` as plain strings (documented in the plan; the downgrade note says so).
- `school_academic_results.status` gains the value `withdrawn` (String(20), no schema change).
  `SchoolResultStatusHistory` records the transition (`from_status` = `draft`|`verified`,
  `to_status` = `withdrawn`, `changed_by_user_id` = the admin).

### 5.2 Coordinator endpoints (`/school`)

All require `user.role == "school_coordinator"` with a linked school, via a dependency (so `403` precedes
any `422`, matching ENH-004 §5.2). The caller's school always comes from their profile.

- `GET /school/transfer-destinations` → `[{id, name}]`, every school except the caller's own. Id and name
  only.
- `POST /school/students/{student_id}/transfer-requests` (**outgoing**), body `{to_school_id, reason?}`,
  `extra="forbid"`. The student must be at the caller's school (`403` otherwise, same message as
  `update_student`). `to_school_id` must exist and differ from the caller's school (`422`). A pending
  request for the student already exists → `409` (also caught as `IntegrityError` from the partial index).
  `201` with the request.
- `POST /school/transfer-requests/incoming` (**incoming**), body `{student_code, reason?}`,
  `extra="forbid"`. Always `202 {"status": "submitted"}`. A row is created only when the code resolves
  to a student at a *different* school with no pending request; every other case (unknown code, own
  school, duplicate) creates nothing and returns the identical body. Unknown code and own-school
  attempts write an `AuditLog` row with `outcome="denied"` (no student data in the row).
- `GET /school/transfer-requests` → the caller's school's requests, both sides, newest first. Incoming
  rows that are not yet approved expose only `student_code`, `status`, `reason`, timestamps — **no
  student name and no source school**. Outgoing rows, and incoming rows once approved, expose the full
  view.
- `POST /school/transfer-requests/{id}/cancel` → only a coordinator of the school that filed
  (`requested_side` school), only while `pending`; otherwise `403` / `409`.
- `GET /school/students/{student_id}/transfer-history` → approved transfers for the student, newest first,
  through `_load_readable_student` (own institution; assigned-only Teacher; own-child-only Parent). Each
  entry: `id`, `created_at`/`decided_at`, `from_school {id,name}`, `to_school {id,name}`, `reason`. No
  staff user IDs, so a Parent never receives one. Bounded by the number of transfers per student, not
  paginated.

### 5.3 Admin endpoints (`/overseas-admin`)

All require `user.role in {"overseas_admin", "super_admin"}`, via a dependency.

- `GET /overseas-admin/school-transfer-requests?status=pending` (default `pending`; also `all`,
  `approved`, `rejected`, `cancelled`) → each request with student name/code, both school names,
  requester name and side, reason, and a **preview**: `linked_parents`, `in_flight_results`
  (draft+verified), and `to_school_has_portfolio_staff` (so an admin is warned when the destination has
  no staff portfolio and the student would be invisible to service-delivery roles).
- `POST /overseas-admin/school-transfer-requests/{id}/approve` → `200` with the request and its
  `outcome`.
- `POST /overseas-admin/school-transfer-requests/{id}/reject`, body `{note?}` → `200`.
- `GET /overseas-admin/school-students/{student_id}/transfer-history` → every request for the student
  (all statuses) with performer/requester names. Admin-only, so staff names are allowed here.

### 5.4 The approval transaction

One transaction (`READ COMMITTED`, as the rest of the codebase), started with
`SELECT set_config('lock_timeout', :timeout, true)` from a module constant `TRANSFER_LOCK_TIMEOUT = "5s"`
(same bound-parameter form as ENH-004; never request input). A lock timeout (`sqlstate 55P03`) →
`409 "Another change to this student is in progress; retry"`. **Lock order is fixed** to keep the
transaction deadlock-free: request → student → parent users (by id) → in-flight results (by id).

1. Lock the request `FOR UPDATE`. Missing → `404`. Not `pending` → `409`.
2. Lock the student `FOR UPDATE`. If `student.school_id != request.from_school_id` the request is stale →
   `409`, request left `pending` (the admin can reject it). Load `to_school`; missing → `422`.
3. **Parents (D1).** Lock the `users` rows of the student's linked parents `FOR UPDATE`, ordered by id.
   For each parent with `role == "school_parent"` and `profile.school_id == from_school_id`: count that
   parent's links to *other* students whose `school_id == from_school_id`. If none, reassign
   `parent.profile = {**profile, "school_id": str(to_school_id)}` (whole-dict reassignment so the JSON
   change is detected); count as `parents_moved`, else `parents_kept`. Links themselves are never
   deleted. The count runs after the parent lock, so two sibling transfers sharing a parent serialize
   and both evaluate correctly.
4. **In-flight results (D3).** Select the student's results with `status IN ('draft','verified')`
   `FOR UPDATE` ordered by id; set each to `withdrawn` and add a `SchoolResultStatusHistory` row. A
   result that a concurrent `verify` published a moment earlier is no longer `draft`/`verified` once
   the lock is granted and is left alone.
5. **Student.** `school_id = to_school_id`; `assigned_teacher_user_id = None`;
   `pending_parent_email = None`. Grade, year, `student_code`, attendance, other records and bridged
   applications are untouched (D4).
6. Request: `status = approved`, `decided_by_user_id`, `decided_at`, `outcome` counts.
7. `AuditLog` (`school.student_transfer`, entity `school_student`, metadata from/to school IDs and
   outcome counts). `commit`. `IntegrityError` → rollback, `409`.
8. **After the commit**, in a second short step: in-app `Notification` rows for both schools'
   coordinators and the requester, and parent notifications via the existing `_notify_student_parents`
   (in-app plus the existing email channel). A failure here is logged and swallowed; the approval has
   already committed (SCH-007-AC04 discipline).

**Reject:** lock the request, must be `pending` (`409`), set `rejected`, `decided_by_user_id`,
`decided_at`, `decision_note`, audit, commit, then notify the requester. No student or dependent row is
touched. **Cancel:** the same shape with `cancelled`.

**Concurrency, stated once**
- Two approvals of one request: the request lock serializes them; the second sees `approved` → `409`.
- Approve versus a concurrent promotion (`schools.py:1221`): the promotion's locking query filters
  `school_id`. While a transfer holds the student, the promotion waits up to its 5s bound; once the
  transfer commits, the moved student no longer matches the filter, the promotion's count check fails
  and it returns its existing generic `403` having written nothing. Safe, and tested. The now-false
  comment at `schools.py:1234-1237` is corrected (§8).
- Approve versus a concurrent `verify`/`publish`: `_advance_result` locks the result, then reads the
  student without locking, so it never waits on the student lock — no cycle. It either finishes first
  (the result is published and left alone) or runs after and gets `409` on status.

## 6. Authorization and security

| Action | Allowed | Otherwise |
|---|---|---|
| File outgoing | `school_coordinator` of the student's school | `403` |
| File incoming | any `school_coordinator` (creates only for another school's student) | same `202`, nothing created |
| List / cancel own requests | coordinator of the filing side's school | `403` |
| Approve / reject / admin list / admin history | `overseas_admin`, `super_admin` | `403`; unauthenticated `401` |
| Read transfer history | same own-scope rule as the student itself | `403` |

- Neither coordinator has any path that changes `school_id`; only `approve` does, and it is admin-only.
  `update_student` still ignores `school_id` and `academic_year_id`, unchanged.
- Request models use `extra="forbid"`: a client-supplied `school_id`, `from_school_id`, `status`,
  `requested_side`, or `student_id` in a body is a loud `422`, never silently ignored. The from-school
  is always read from the student row, the requester's school from their profile, `requested_side`
  derived server-side.
- **No cross-school existence oracle.** The incoming endpoint's identical `202`, the redacted
  incoming rows, and the id-and-name-only destination list are the only cross-school exposure.
- **Parent scope is now link-only** (§8). The link is created only by same-school coordinator paths
  (`link_parent`, `_link_or_invite_parent`, `accept_invite`), unchanged, so no new way to acquire a
  link is introduced.
- `AuditLog` rows for request, cancel, approve, reject and denied attempts. Counts and IDs only; no
  names, no free-text `reason` copied into audit metadata.
- `reason`, `decision_note`: length-capped in the schema, stored as text, rendered as text (no HTML).
- Same class of risk as `RBAC_MATRIX.md` §2.12 (cross-tenant isolation): a dedicated security-review
  pass is a plan task before the branch is called complete.

## 7. Frontend

Every screen has loading, empty and error states (retry on error, no silent failure), follows the
existing school-portal components and CSS, and adds no dependency.

- **`SchoolTransferRequestForm`** inside `SchoolStudentDetailPanel` (coordinator only): destination
  `<select>` fed by `GET /school/transfer-destinations` (loading → disabled; none → "No other schools";
  error → retry), optional reason, submit. Shows a pending-request banner (and hides the form) when the
  student already has one; success confirmation; `409`/`422` messages inline.
- **`/school/coordinator/transfers`** page + `SchoolTransfersPanel` (new nav item): the school's
  requests with status badges, **cancel** on pending own-filed rows, and a "Request an incoming
  student" form (student code + reason) that shows the generic "submitted for review" message.
- **`AdminSchoolTransferPanel`** wired into `WorkflowPanel.tsx` (a new `showSchoolTransfers` flag beside
  `showSchoolApplications`, overseas-admin/super-admin sections only): pending queue with the preview
  counts and the destination-has-no-portfolio warning; **approve** and **reject** each behind a confirm
  step that states the consequences (parents moved, results withdrawn, teacher unassigned); disabled
  buttons while in flight; the result `outcome` shown after approval; `409` (stale or already decided)
  refreshes the list.
- **`SchoolTransferHistory`** modelled on `SchoolGradeHistory`, shown in the student detail and parent
  child overview: loading / empty ("No transfers") / error; no staff names.
- Type additions in `lib/types.ts`, calls in `lib/api.ts`; `lib/i18n.ts` and `lib/navigation.ts` only
  where the existing screens already use them. (`WorkflowPanel.tsx`/`navigation.ts` wiring was not read
  in the research pass; the plan's first frontend task reads them before editing.)

## 8. Forced changes to existing behavior (the only ones)

1. **Parent scope is link-only.** `_scoped_students_query` (`schools.py:643`): the `school_parent`
   branch drops the `school_id` filter and keeps the link filter. `_load_readable_student`
   (`schools.py:864`): the `school_parent` branch skips the institution check and keeps the link
   check. `_own_school_id(user)` is still called, so a parent with no school still gets `403`. Every
   reader that goes through `_readable_students` (results, career, psychometric, test-prep, language)
   inherits this. Effect: none for any existing parent, because links were only ever created
   same-school; the difference appears only after a transfer. An unlinked student is still `403`.
2. **`withdrawn` filter** on the two result queries that include unpublished rows:
   `list_academic_team_results` (`schools.py:1982`) and `academic_team_progress` (`schools.py:2001`).
   Every other result query is already `status == "published"` (`schools.py:338, 705, 910, 1016, 2029`);
   `update_academic_result` and `_advance_result` already reject non-draft / wrong-stage rows with `409`.
3. **Comment correction** at `schools.py:1234-1237` (and a note in the ENH-004 plan): `school_id` can now
   change, and the concurrency reasoning in §5.4 replaces the "no check/use gap" claim. No code change
   to the promotion logic.

Nothing else changes: existing endpoint shapes, `student_code`, the promotion flow, the results
workflow's actor-separation (DEC-ROLE-007), `SchoolStaffAssignment` (portfolio follows `school_id`
automatically), `admin.py` bridge endpoints (global, not school-scoped), attendance and activities.

## 9. Error states and edge cases

| Situation | Behavior |
|---|---|
| Same-school destination | `422` |
| Unknown destination school | `422` |
| Outgoing request for another school's student | `403` |
| Pending request already exists (outgoing) | `409` (application check, backed by the partial index) |
| Incoming: unknown code / own school / duplicate | identical `202`, nothing created |
| Approve a non-pending request | `409` |
| Approve a stale request (student moved since filing) | `409`, request stays `pending` |
| Lock wait exceeds 5s | `409` retry message |
| Destination school has no staff portfolio | approval allowed; the admin preview warns; the student is invisible to service-delivery roles until a portfolio is assigned |
| Parent account has `profile.school_id` not equal to the losing school | untouched (`parents_kept`) |
| Student has no linked parents / no results / no teacher | counts are zero; approval succeeds |
| Notification send fails | logged, approval stands |
| Mid-transaction failure | full rollback: student, parents, results, request unchanged |
| Cancel/reject an already decided request | `409` |

## 10. Acceptance criteria (local IDs)

- **AC-01** A coordinator can file an outgoing request for their own school's student; a `pending` row
  is created with `requested_side="losing"` and the server-derived from-school.
- **AC-02** Outgoing filing is rejected: other school's student `403`; same-school or unknown
  destination `422`; non-coordinator `403`; a client-supplied `from_school_id`/`status`/`school_id`
  `422`.
- **AC-03** A second pending request for the same student is `409` (also proven at the DB level).
- **AC-04** Incoming filing returns the identical `202` body for valid, unknown, own-school and duplicate
  inputs; a row is created only for a valid other-school student; unknown/own-school attempts are audited
  `denied`.
- **AC-05** Not-yet-approved incoming rows expose only the code, status, reason and timestamps.
- **AC-06** Only a coordinator of the filing side's school can cancel, only while `pending`.
- **AC-07** Neither school's coordinator, nor teacher, parent, principal, counselor, nor an
  unauthenticated caller can approve or reject (`403`/`401`); `overseas_admin` and `super_admin` can.
- **AC-08** Approval changes `school_id` to the destination in one transaction; afterwards the losing
  school's coordinator gets `403` on the student and the gaining school's coordinator can read it.
- **AC-09** Approval clears `assigned_teacher_user_id` and `pending_parent_email`.
- **AC-10** Parent links are all preserved. A parent with no other child at the losing school is moved to
  the gaining school; a parent with another child there stays; both can read the transferred child; a
  parent still cannot read an unlinked student.
- **AC-11** Draft and Verified results become `withdrawn` with a status-history row each, disappear from
  the academic-team list and progress average, and cannot be edited, verified or published (`409`).
  Published results are unchanged and remain readable to gaining-school readers.
- **AC-12** Career, psychometric, test-prep and language rows are unchanged and follow the student.
- **AC-13** Rejecting changes only the request. A stale or already-decided approve is `409` and changes
  nothing.
- **AC-14** Transfer history: a gaining-school reader gets approved transfers for their own-scope
  student with no staff IDs; an admin gets all statuses with names.
- **AC-15** Audit rows exist for request, cancel, approve, reject and denied attempts; notifications are
  sent after the commit; a notification failure does not fail or undo the approval.
- **AC-16** A failure injected mid-approval leaves student, parents, results and request exactly as
  before.
- **AC-17** Concurrency: two simultaneous approvals of one request → exactly one succeeds; a promotion
  racing a transfer of one of its students → the promotion gets `403` and writes nothing, the transfer
  succeeds; two sibling transfers sharing a parent → the parent's final school and link set are correct.
- **AC-18** Existing behavior preserved: the ENH-004, SCH-001, SCH-003, SCH-006, SCH-007 and SCH-008
  suites pass unchanged.
- **AC-19** Frontend: each new screen renders loading, empty, error and success states; destructive
  actions require confirmation and disable while pending.

## 11. Regression risks and test plan (written before code)

| Risk | Where | Guard |
|---|---|---|
| Promotion locking assumed immutable `school_id` | `schools.py:1221-1297` | AC-17 concurrency test; existing `test_enh_004_student_promotion.py` unchanged |
| Parent scope change leaks an unlinked student | `_scoped_students_query`, `_load_readable_student` | tests: unlinked student `403`, other-school parent `403`, linked child after transfer `200`; existing `test_sch_001`/`test_sch_007` |
| Withdrawn results leak or break averages | `schools.py:1982, 2001` | AC-11; existing `test_sch_006` (multi-school portfolio fixtures at `:365-441` stay green) |
| Old portfolio keeps or new portfolio gains wrong visibility | `_student_in_portfolio`, `list_portfolio_students`, `academic_team_progress` | test: staff of A `403`, staff of B `200` after transfer |
| Timeline shows old-school context | `student_timeline`/`student_overview` (`schools.py:889-1050`) | test: upcoming activities come from the new school; attendance history stays |
| Dashboard/report/entitlement counts | `_school_dashboard_payload`, `school_reports`, `school_entitlements` | test: counts of both schools change by exactly one student; entitlement usage is activity-based and unchanged |
| Bridged Overseas applications | `admin.py` bridge endpoints | test: an existing bridged application still lists and notifies |
| Migration | `0034` | migration applies on a copy of the seeded DB; existing rows untouched; downgrade drops only the new table |
| Existing E2E specs | `sch-001`, `sch-003`, `sch-007`, `sch-008`, `enh-004` | rerun the affected specs (Docker stack brought up by the user) |

**Test files (to be written first, per task):** `apps/api/tests/test_enh_005_school_transfer.py` (real
Postgres, following `test_enh_004_student_promotion.py`, including its raw-SQL concurrency helper);
vitest component tests `SchoolTransferRequestForm`, `SchoolTransfersPanel`, `AdminSchoolTransferPanel`,
`SchoolTransferHistory`; Playwright `apps/web/tests/e2e/enh-005-school-transfer.spec.ts`. The full
backend/E2E regression is run at the standing cadence, not after every task; targeted suites run per
task.

## 12. Documentation deliverables

- `DEC-SCOPE-021` in `docs/decisions/PRODUCT_DECISION_REGISTER.md` (D1–D4, A1–A3, non-goals).
- `docs/architecture/DATA_MODEL.md`: the new table and the `withdrawn` result status.
- `docs/architecture/API_CONTRACT.md` §12A: the ten endpoints (six coordinator, four admin).
- `docs/architecture/RBAC_MATRIX.md` §2.12: the transfer rows and the parent link-based scope note.
- `docs/delivery/ENHANCEMENT_BACKLOG.md`: ENH-005 status line.
- The ENH-004 spec/plan note about the immutability claim.
- An implementation plan at `docs/superpowers/plans/2026-09-21-enh-005-student-school-transfer.md`.

## 13. Open items (`NEEDS_CONFIRMATION`, not decided here)

- **Multi-school parents (ENH-008).** A parent kept at the losing school (because of another child
  there) reads the transferred child through the link, but does not appear in the gaining school's
  team list and cannot be linked by the gaining coordinator (same-school rule in `link_parent`).
  Dashboard `parent_count` counts by profile school. Full multi-school parent management is ENH-008.
- Whether gaining-school staff should be shown the losing school's name in transfer history (the
  design shows it to every role with own-scope access, as school names are partner-level data).
- Branch moves within a school (ENH-009).
- Whether a rejected/cancelled request should be re-fileable immediately (the design allows it: the
  partial index only covers `pending`).
- Bulk transfer for whole-cohort moves.
