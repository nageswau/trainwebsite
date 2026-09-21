# ENH-005 — Student School Transfer / Reassignment — Design

**Status:** Design approved by the user in-session, 2026-09-21 (`EXPLICIT_APPROVAL`): four policy
decisions in §3 plus the section-by-section design with "yes". The same day, an
`api-and-interface-design` review of the backend was applied (§5.5) and three further decisions
(D5–D7) were confirmed; a `frontend-ui-engineering` review of the UI was applied (§7.1); a
`security-and-hardening` review was applied (§6.1) with two further decisions (D8, D9). Written spec
awaiting the user's review. Implementation not started.

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
| D5 | Who sees a pending request | **Only the filing school.** A coordinator lists only requests their own school filed. The other school learns of it when the admin decides (approval notice). |
| D6 | Pagination of the two growing lists (admin queue, coordinator list) | **`limit`/`offset` with `{items, total, limit, offset}`**, default 25, max 100. A deliberate deviation from the contract's cursor convention (§0.1), which no endpoint implements; recorded in `API_CONTRACT.md`. |
| D7 | Open-request cap | **50 open (`pending`) requests per filing school**; the 51st is `409`. |
| D8 | Filing throttle (security review S3) | **30 filing attempts per coordinator per rolling hour**, valid or not, counted from the `AuditLog` rows the filing endpoints already write (so it holds across several server instances); the 31st is `429` with `Retry-After`. New endpoints only. |
| D9 | Email HTML escaping (security review S1) | **Escape the interpolated values in `mailer._parent_notification_html`** (`title`, `recipient_name`, `body`, `school_name`, and the URL with `quote=True`), as its own commit with its own test. |

Assumptions made by the design and confirmed with the user's approval of it:

- **A1.** "Admin" means `overseas_admin` and `super_admin` — the actors that already manage cross-school
  data in `admin.py` (`school-staff`, `school-students/lookup`). `counselor` and every School role are
  denied.
- **A2.** "One action" (backlog acceptance criterion 1) means the admin's approval performs the entire
  move; the coordinator's request is a separate earlier step.
- **A3.** The incoming-request endpoint returns the same `202 {"accepted": true}` for every well-formed
  input, to avoid a cross-school existence oracle (§6).

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
| `filed_by_school_id` | UUID FK `schools.id`, indexed | the filing coordinator's school, always taken from their profile; CHECK `filed_by_school_id IN (from_school_id, to_school_id)`. `direction` is derived: `outgoing` when it equals `from_school_id`, else `incoming`. It scopes the coordinator list, the cancel check and the open-request cap. |
| `status` | String(20), default `pending` | `pending` / `approved` / `rejected` / `cancelled` |
| `reason` | Text, nullable | coordinator free text, length-capped in the schema |
| `decided_by_user_id` | UUID FK `users.id`, nullable | admin (approve/reject) or coordinator (cancel) |
| `decided_at` | DateTime(tz), nullable | |
| `decision_note` | Text, nullable | admin reject note |
| `outcome` | JSON, nullable | set on approval: `parents_moved`, `parents_kept`, `results_withdrawn`, `teacher_cleared`, `pending_parent_email_cleared` |
| `created_at`/`updated_at` | `TimestampMixin` | |

- **Partial unique index** `uq_school_transfer_pending_student` on `(school_student_id) WHERE status = 'pending'`
  (SQLAlchemy `Index(..., unique=True, postgresql_where=text("status = 'pending'"))`): at most one open
  request per student, enforced by the database. The index and both CHECK constraints are declared in
  **both** the SQLAlchemy model (dev startup can build the schema with `create_all`) and migration
  `0034` (Docker runs `alembic upgrade head`; backend tests run against that migrated database).
- **Other indexes:** `school_student_id` and `filed_by_school_id`. The admin queue filters on `status` of
  a small table and needs no further index (YAGNI); revisit only if the table grows.
- **Non-destructive migration:** creates one table and indexes; no backfill; no existing row is touched.
  Downgrade drops the table. Any `withdrawn` result rows written after upgrade stay in
  `school_academic_results` as plain strings (documented in the plan; the downgrade note says so).
- `school_academic_results.status` gains the value `withdrawn` (String(20), no schema change).
  `SchoolResultStatusHistory` records the transition (`from_status` = `draft`|`verified`,
  `to_status` = `withdrawn`, `changed_by_user_id` = the admin).

### 5.2 Coordinator endpoints (`/school`)

**Boundary conventions (all endpoints in §5.2–5.3).** Typed Pydantic request models with
`extra="forbid"` and `str_strip_whitespace` (a client-supplied `school_id`, `from_school_id`,
`filed_by_school_id`, `status` or `student_id` in a body is a loud `422`); free text is capped
(`reason` ≤ 500, `note` ≤ 500) and rejects control characters (a NUL byte would otherwise surface as a
`500` from PostgreSQL text, as noted in ENH-004's `PromotionItem`); typed `UUID` fields, so a malformed
ID is `422`, never a `500`; `response_model` on every route so the generated OpenAPI matches the
contract. `snake_case` fields, lowercase enum values, `{"detail": …}` errors. Role gates are
dependencies (`403` precedes `422`, as `_require_coordinator_user` does for ENH-004). The caller's school
always comes from their profile.

**One response shape for requests, `TransferRequestOut`** (no field appears or disappears by condition;
redacted values are `null`): `id`, `direction` (`outgoing` = filed by the losing school, `incoming` =
filed by the gaining school), `status`, `student_id`, `student_code`, `student_name`, `from_school
{id,name}`, `to_school {id,name}`, `reason`, `decision_note`, `created_at`, `decided_at`. **Redaction
rule:** a request whose `direction` is `incoming` and whose `status` is not `approved` has `student_id`,
`student_name` and `from_school` set to `null` (the gaining coordinator knows only the code they typed);
every other row is complete. A coordinator sees only requests **filed by their own school** (decision D5).

**List envelope:** `{items: [...], total, limit, offset}`; `limit` default 25, `1..100`; `offset` ≥ 0;
ordered `created_at DESC, id DESC` (decision D6).

- `GET /school/transfer-destinations` → `[{id, name}]`, every school except the caller's own. Id and name
  only. Not paginated: bounded by the number of partner schools (a `<select>` source, like
  `GET /overseas-admin/academic-years`); marked explicitly as contract §0.1 requires.
- `POST /school/students/{student_id}/transfer-requests` (**outgoing**), body `{to_school_id, reason?}`,
  `201 TransferRequestOut`. Check order: role (`403`) → body (`422`) → filing throttle (`429`, D8) → the student must exist **and** be
  at the caller's school, otherwise one identical `403` "This student is not at your institution" for
  an unknown ID and another school's ID alike (ENH-004's "same absence" rule, contract §0.3) →
  `to_school_id` exists and differs from the caller's school (`422`) → open-request cap (`409`) → a
  pending request for the student already exists (`409`, also caught as `IntegrityError` from the partial
  index).
- `POST /school/transfer-requests/incoming` (**incoming**), body `{student_code, reason?}`. The code is
  stripped, uppercased and must be 8 hex characters (`422` otherwise: a format error says nothing about
  existence). Then the filing throttle (`429`, D8) and the cap check (`409`), both evaluated **before**
  the lookup so the response never depends on the code, then the lookup. **Always `202 {"accepted": true}`** — the same reply shape as
  `POST /auth/forgot-password` (`auth.py:175`) — for every well-formed code. A row is created only when
  the code resolves to a student at a *different* school with no pending request; unknown code, own
  school and duplicate create nothing and return the identical body (a duplicate lost to a race
  (`IntegrityError`) is rolled back and answered the same way). **Every attempt that passes validation
  writes exactly one `AuditLog` row** (`school.transfer_request_filed`, or `school.transfer_request_denied`
  with `outcome="denied"` for unknown code, own school, duplicate, and a foreign or unknown student on the
  outgoing route), whose metadata holds a reason token, the school ID and the request ID only — never
  the attempted code, the reason text, or a student name. These rows are what the throttle counts.
- `GET /school/transfer-requests?status=pending&limit=&offset=` → list envelope of `TransferRequestOut`,
  the caller's own school's filed requests. `status` is the same `Literal` as the admin list (`pending`
  default, `approved`, `rejected`, `cancelled`, `all`; anything else `422`). It is an additive filter the
  UI needs (§7.1): the transfers page defaults to pending, and a student's "already pending" banner
  reads `status=pending`, which is complete in one page because the cap (D7) means a school has at most
  50 pending requests.
- `POST /school/transfer-requests/{id}/cancel` → `200 TransferRequestOut`. The request is locked
  `FOR UPDATE` (so a concurrent approve serializes with it). A request that does not exist **or** was not
  filed by the caller's school → one identical `403`; not `pending` → `409`.
- `GET /school/students/{student_id}/transfer-history` →
  `{student: {id, full_name}, history: [{id, decided_at, from_school {id,name}, to_school {id,name}}]}`,
  approved transfers only, newest first, through `_load_readable_student` (own institution; assigned-only
  Teacher; own-child-only Parent). **No `reason`** (a coordinator's free text is for the admin's review,
  not for the other school's staff or a Parent), **no staff user IDs**. Bounded by the number of transfers
  per student, so not paginated (marked explicitly). After a transfer the losing school can no longer
  read the student, so this endpoint is the gaining side's and the parent's view; the losing side is
  informed by notification and the admin has the full view below.

### 5.3 Admin endpoints (`/overseas-admin`)

All require `user.role in {"overseas_admin", "super_admin"}`, via a dependency — a direct `user.role` check
like the neighbouring admin routes, not the assignment-based `require_role`.

- `GET /overseas-admin/school-transfer-requests?status=pending&limit=&offset=` → list envelope of
  `AdminTransferRequestOut`. `status` is a `Literal` (`pending` default, `approved`, `rejected`,
  `cancelled`, `all`; anything else `422`). `AdminTransferRequestOut` is always complete: everything in
  `TransferRequestOut` unredacted plus `filed_by_school`, `requester {id,name}`, `decided_by
  {id,name}|null`, `outcome`, and a **preview** `{linked_parents, in_flight_results, to_school_has_portfolio_staff}`
  (`in_flight_results` = draft+verified; the flag warns when the destination has no staff portfolio and
  the student would be invisible to service-delivery roles). The preview is computed with **one grouped
  query per count over the page's IDs**, never per row.
- `POST /overseas-admin/school-transfer-requests/{id}/approve` → `200 AdminTransferRequestOut` including
  `outcome`. Unknown ID `404` (admin-only, so no masking concern).
- `POST /overseas-admin/school-transfer-requests/{id}/reject`, body `{note?}` → `200`.
- `GET /overseas-admin/school-students/{student_id}/transfer-history` → every request for the student, all
  statuses, unredacted with staff names. Bounded per student, not paginated.

### 5.3a Error catalogue (stable `detail` strings; a client may match on them — Hyrum's Law)

| Status | When | `detail` |
|---|---|---|
| `401` | no/invalid session | existing |
| `403` | wrong role | "School Coordinator role required" / "Overseas Admin role required" (existing wording) |
| `403` | outgoing filing for an unknown or foreign student | "This student is not at your institution" |
| `403` | cancel of an unknown or not-yours request | "Not permitted for this transfer request" |
| `409` | second pending request for a student | "A transfer request is already pending for this student" |
| `409` | school has 50 open requests | "Too many open transfer requests; wait for a decision or cancel one" |
| `429` | more than 30 filing attempts in the last hour by this coordinator (`Retry-After` set) | "Too many transfer requests; try again in N seconds" |
| `409` | approve/reject/cancel of a decided request | "This transfer request has already been decided" |
| `409` | approve when the student has since moved | "The student is no longer at the school this request was filed for; reject it and file a new one" |
| `409` | lock wait exceeded | "Another change to this student is in progress; retry" |
| `422` | validation | FastAPI's `{"detail": [{loc, msg, type}]}` or a string, as elsewhere |

Retry semantics (contract §0.2: no `Idempotency-Key`, since this is not a financial action): every write
is naturally safe to retry. A duplicate filing, approve, reject or cancel after a lost response answers
`409` with a message that tells the client the state has already changed; the UI refetches the request
instead of retrying blindly. The incoming endpoint is idempotent by construction (identical `202`).

### 5.4 The approval transaction

One transaction (`READ COMMITTED`, as the rest of the codebase), started with
`SELECT set_config('lock_timeout', :timeout, true)` from a module constant `TRANSFER_LOCK_TIMEOUT = "5s"`
(same bound-parameter form as ENH-004; never request input). A lock timeout (`sqlstate 55P03`) →
`409 "Another change to this student is in progress; retry"`. **Lock order is fixed** to keep the
transaction deadlock-free: request → student → parent users (by id) → in-flight results (by id).

1. Lock the request `FOR UPDATE`. Missing → `404`. Not `pending` → `409` "already decided".
2. Lock the student `FOR UPDATE`. If `student.school_id != request.from_school_id` the request is stale →
   `409` (stale message, §5.3a), request left `pending` (the admin can reject it). Load `to_school`;
   missing → `422`.
3. **Parents (D1).** Lock the `users` rows of the student's linked parents `FOR UPDATE`, ordered by id.
   For each parent with `role == "school_parent"` and `profile.school_id == from_school_id`: count that
   parent's links to *other* students whose `school_id == from_school_id`. If none, reassign
   `parent.profile = {**profile, "school_id": str(to_school_id)}` (whole-dict reassignment so the JSON
   change is detected); count as `parents_moved`, else `parents_kept`. Links themselves are never
   deleted. The count runs after the parent lock, so two sibling transfers sharing a parent serialize
   and both evaluate correctly. **The only field ever written on a parent is `profile.school_id`, and
   only on an account whose `role` is `school_parent`**; `role`, `division`, `UserRoleAssignment`,
   `active`, `email` and `password_hash` are never touched (security review S5). Each moved parent gets
   **its own `AuditLog` row** in the same transaction (`school.user_school_scope_changed`, entity `user`,
   metadata from/to school and the transfer request ID), because `school_id` is an authorization scope
   key (`SERVER_OWNED_PROFILE_KEYS`) and every change to one must be attributable (S4).
4. **In-flight results (D3).** Select the student's results with `status IN ('draft','verified')`
   `FOR UPDATE` ordered by id; set each to `withdrawn` and add a `SchoolResultStatusHistory` row. A
   result that a concurrent `verify` published a moment earlier is no longer `draft`/`verified` once
   the lock is granted and is left alone.
5. **Student.** `school_id = to_school_id`; `assigned_teacher_user_id = None`;
   `pending_parent_email = None`. Grade, year, `student_code`, attendance, other records and bridged
   applications are untouched (D4).
6. Request: `status = approved`, `decided_by_user_id`, `decided_at`, `outcome` counts.
7. `AuditLog` (`school.student_transfer`, entity `school_student`, metadata from/to school IDs and
   outcome counts). `commit`. `IntegrityError` → explicit `rollback`, `409`.
8. **After the commit**, in a second short transaction: in-app `Notification` rows for both schools'
   coordinators and the requester, and parent notifications via the existing `_notify_student_parents`
   (in-app plus the existing email channel). A failure here is logged and swallowed; the approval has
   already committed (SCH-007-AC04 discipline).

**Transaction boundaries (why this shape).**
- `set_config('lock_timeout', …, true)` is transaction-local and takes effect for the transaction that the
  request's earlier queries (`get_current_user`) already opened; it lasts until the commit. After the
  commit the notification step is a new transaction with no lock timeout, which is fine because it takes
  no contended locks.
- `get_db` has no explicit rollback: closing the session rolls back uncommitted work and releases every
  lock, so any `HTTPException` after the locks is safe. The `55P03` and `IntegrityError` paths still call
  `db.rollback()` explicitly first, as ENH-004 and `create_academic_year` do.
- `expire_on_commit=False`, so the response is built after the commit without re-reading rows.
- Structured logs (`student_transfer_approved`, `..._rejected`, `..._lock_timeout`) carry IDs and counts
  only, never names or free text, with the `extra_fields` pattern ENH-004 uses.

**Reject:** lock the request, must be `pending` (`409`), set `rejected`, `decided_by_user_id`,
`decided_at`, `decision_note`, audit, commit, then notify the requester (student code only if the request
was incoming; see §6). No student or dependent row is touched. **Cancel:** the same shape with
`cancelled`, `decided_by_user_id` the cancelling coordinator, no notification.

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

### 5.5 API design notes (result of the `api-and-interface-design` review, 2026-09-21)

- **Conventions follow the existing API, not generic style guides:** `snake_case` fields, lowercase enum
  values, hyphenated plural paths (`school-transfer-requests` beside `school-staff`/`school-students`),
  verb sub-resources for state transitions (`/approve`, `/reject`, `/cancel`, as `/verify` and `/publish`
  already are), errors as FastAPI `{"detail": …}`. `API_CONTRACT.md` §0.3 documents a different error
  shape (`{error_code, message, field_errors}`) that no route emits; that pre-existing drift is not
  fixed here (ENH-004 recorded the same).
- **Typed boundary:** Pydantic request and response models (§5.2), unlike the older `payload: dict`
  routes whose `UUID(str(x))` turns a garbage ID into a `500`.
- **No shape-shifting responses:** one `TransferRequestOut` with nullable redacted fields, one
  always-complete admin model.
- **Existence masking:** an unknown ID and another school's ID get the same `403` on file and cancel;
  the incoming endpoint answers every well-formed code identically. Unknown request IDs are `404` only on
  admin routes.
- **Backward compatibility:** no existing endpoint, field, status code or message changes. `withdrawn`
  is filtered out of every response that could carry it (`_result_out` is reached only through the two
  filtered lists and `409`-guarded writes), so no client-visible enum gains a value. The parent
  message precedence is preserved (§8).
- **Retry safety:** natural, per §5.3a; no `Idempotency-Key`, per contract §0.2.
- **Pagination:** D6. Per-student history and the destination list are bounded and marked explicitly
  "not paginated", as contract §0.1 requires.
- **Database use:** the coordinator list is one indexed query (`filed_by_school_id`) with two aliased
  `schools` joins plus a `count`; the admin list adds one grouped query per preview count over the page's
  IDs (no per-row queries); approval is a fixed number of statements independent of result/parent count
  except one `UPDATE`-equivalent per withdrawn result (bounded by one student's unpublished results).
- **Routing:** both new routers are added to the tuple in `main.py`. No path collides with an existing
  route: `POST /school/students/{student_id}/transfer-requests` and `GET
  /school/students/{student_id}/transfer-history` have distinct suffixes, and
  `/school/transfer-requests/incoming` (static) and `/school/transfer-requests/{id}/cancel` cannot be
  confused.
- **Environment:** backend tests run against the migrated Docker database, so migration `0034` must be
  applied (by the user, who controls the stack) before the new tests can pass.

## 6. Authorization and security

| Action | Allowed | Otherwise |
|---|---|---|
| File outgoing | `school_coordinator` of the student's school | `403` |
| File incoming | any `school_coordinator` (creates only for another school's student) | same `202`, nothing created |
| List / cancel requests | coordinator of the school that filed them (`filed_by_school_id`) | list: only own-filed rows; cancel: one identical `403` |
| Approve / reject / admin list / admin history | `overseas_admin`, `super_admin` | `403`; unauthenticated `401` |
| Read transfer history | same own-scope rule as the student itself | `403` |

- Neither coordinator has any path that changes `school_id`; only `approve` does, and it is admin-only.
  `update_student` still ignores `school_id` and `academic_year_id`, unchanged.
- Request models use `extra="forbid"`: a client-supplied `school_id`, `from_school_id`,
  `filed_by_school_id`, `status`, or `student_id` in a body is a loud `422`, never silently ignored. The
  from-school is always read from the student row and the filing school from the caller's profile.
- **Notification privacy.** Approval notices name the student to both coordinators and the parents (the
  student is now, or was, theirs). A rejection or cancellation notice to an *incoming* requester carries
  the student code only, never the name or the source school. `decision_note` is returned to the filing
  coordinator, so the admin panel warns "visible to the requesting coordinator; do not include student
  details".
- **Open-request cap.** At most `MAX_OPEN_TRANSFER_REQUESTS_PER_SCHOOL = 50` `pending` requests per
  `filed_by_school_id` (decision D7). It is a guard against flooding the admin queue, not a security
  boundary: it is a count-then-insert, so two simultaneous filings may exceed it by a few, which is
  acceptable and documented. Over the cap → `409`. For the incoming endpoint the cap is checked before
  the student lookup, so it cannot be used as an oracle (it reveals only the caller's own count).
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

### 6.1 Security review (`security-and-hardening`, 2026-09-21)

Scope: ENH-005 only. Anything found outside it is listed as *reported, not changed*.

**Threat model.** *Trust boundaries:* coordinator browser → API (file, cancel, list, history); admin
browser → API (approve, reject); API → SMTP and the email webhook (notification text); API → PostgreSQL.
*Assets:* minors' records and results; cross-school isolation; the authorization scope key
`profile.school_id`; the admin approval authority. *Abuse cases (each is a test in §11):* a coordinator
pulls a student without approval; a coordinator probes student codes; a coordinator floods the queue; a
user changes their own school scope; a moved parent gains other students; markup in a student, school
or parent name reaches an admin screen or a parent's inbox; a cross-site page triggers an approval; an
approval runs on stale data; an authorization change goes unrecorded; personal data reaches a log.

**Findings and resolutions**

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| S1 | High | **HTML injection in parent emails (pre-existing, newly exposed).** `mailer._parent_notification_html` (`mailer.py:126`) interpolates `title`, `recipient_name`, `body` and (via callers) school and student names into an HTML email with no escaping. Those values are coordinator-, admin- or invite-controlled (`create_student` only strips `full_name`). ENH-005's approval notice routes a student name and a school name through it, and the mail comes from EduSphere's own sender, so it is a phishing vector against parents. | **D9:** escape the values in that function (`html.escape`; the URL with `quote=True`). Behaviour-preserving for ordinary text, its own commit and test. It also closes the hole for the existing SCH-007 callers. Notification `action_url` is always a server-built relative path from a UUID and constants, never user text (test). |
| S2 | High | **The parent read filter no longer double-checks the school.** §8 makes a parent's scope link-only, so "every `SchoolParentLink` joins a parent and a student at the same school" stops being defence in depth and becomes the only thing keeping a parent out of another school's students. | The three link creators were read and all enforce it today: `link_parent` (`schools.py:1196`, parent's and student's school both checked against the coordinator's), `_link_or_invite_parent` via `_parent_email_conflict` (`:600-631`), and `accept_invite` (`:245-249`, students filtered to the invite's own school); `seed.py` is demo data. **Tests pin each one** (a cross-school link is refused). A **read-only pre-release data check** counts existing links whose parent's `profile.school_id` differs from the student's `school_id`; it must return 0 before the migration ships. A comment on `_scoped_students_query` states the invariant for future link creators. |
| S3 | Medium | **Code-probing oracle.** The identical `202` hides the response, but a filer can see whether a row appeared in their own list, so student codes (32 bits) can be tested. The app has no rate limiting at all. | **D8:** 30 filing attempts per coordinator per rolling hour, counted from the audit rows; `429` + `Retry-After` + a warning log (the ENH-003 resend-throttle shape). Combined with the 50-open cap (D7) and auditing of every attempt, enumeration costs about 480 probes a day per coordinator against a 1-in-10⁵ hit rate. **Residual, stated honestly:** a determined coordinator can still learn that a code exists, slowly, and is recorded doing so. The DB-based count works across instances (an in-process limiter would not). |
| S4 | Medium | **An authorization-scope change would go unrecorded.** Approval rewrites another user's `profile.school_id`, a key `PATCH /auth/me` treats as server-owned and audits when refused. | One `AuditLog` row per moved parent, in the same transaction (§5.4 step 3). |
| S5 | Medium | **Approval must not be a general write path to accounts.** | It writes `profile.school_id` on `school_parent` accounts only; a test proves `role`, `division`, role assignments, `active`, `email` and `password_hash` of every linked user are unchanged, and that a link whose user is not a `school_parent` is left alone. |
| S6 | Medium (consequence, not a defect) | **A moved parent comes under the gaining coordinator's account authority.** `list_team` shows the account (name, email) and `update_team_account` lets that coordinator activate or deactivate it (`schools.py:160-203`); the losing coordinator loses both. This follows directly from decision D1 ("the account moves"). | Accepted and recorded in `DEC-SCOPE-021`; the actions are already audited (`school.team_account_update`). A parent kept at the losing school (another child there) is not affected. |
| S7 | Low | **Bidirectional-control characters in free text** (`reason`, `note`) could visually reorder text shown to a privileged reviewer. | The validators reject `Cc` (as ENH-004 does) **and** U+202A–U+202E and U+2066–U+2069. Zero-width joiners (U+200C/U+200D) stay allowed: Indic-script text needs them. |
| S8 | Low | **Sensitive data in logs and audit rows.** `JsonFormatter` redacts only a fixed key list, so a careless `extra_fields` value would be logged verbatim. | Logs and audit metadata carry IDs, counts and reason tokens only; never `student_code`, `reason`, `note` or a name. A `caplog` test (the ENH-003 pattern) asserts it across every ENH-005 route. `student_code` travels in a POST body, never a path or query string, so it cannot reach the request-path access log. Audit metadata also carries the `request_id` so a row correlates with its log lines. |
| S9 | Info | **CSRF.** Sessions are `httponly`, `SameSite=Lax` cookies; CORS allows only `frontend_url`. | Every ENH-005 mutation is a `POST`; **none is a `GET`**, so Lax (which sends cookies on top-level cross-site *GET* navigations only) protects them. A test enumerates the new routes and asserts the method. The two filing endpoints and reject take typed JSON bodies. No CSRF token is added: none exists app-wide, and one endpoint family cannot be secured that way. |

**Checked and unchanged (no ENH-005 action needed)**

- **Authentication:** every new route depends on `get_current_user` (cookie JWT, `type == "access"`, active
  user re-read from the database). No new login, token or refresh flow, no public endpoint. The JWT's
  `role`/`division` claims are not used for authorization, so the parent re-scoping in §5.4 takes effect
  on the next request with no re-issue and no stale-token window.
- **Authorization and IDOR:** see the matrix below.
- **Role escalation:** filers (`school_coordinator`) and approvers (`overseas_admin`, `super_admin`) are
  disjoint roles, so no user can file and approve; `filed_by_school_id` comes from the server-owned
  `profile.school_id`, whose only user-facing write path (`PATCH /auth/me`) is already refused
  (ENH-004); approval never touches `role`/`division`/assignments (S5).
- **Input validation:** typed models, `extra="forbid"`, `student_code` stripped, upper-cased and matched
  against an explicit ASCII `[0-9A-F]{8}` (so Unicode digits and look-alikes fail), typed UUIDs, `Literal`
  filters, bounded `limit`/`offset`, capped free text.
- **XSS:** React escapes everything rendered; the web app contains no `dangerouslySetInnerHTML` or
  `innerHTML`; `reason`, `note`, names and school names are rendered as text only. The one HTML surface
  is the email (S1).
- **SQL injection:** all access is through SQLAlchemy with bound parameters; the lock timeout is
  `set_config(..., :timeout, true)` with a bound value; the partial-index predicate and CHECKs are
  constants in DDL; `status` is a `Literal`, never interpolated. No `text()` with string building is
  introduced (a review-checklist item for the plan).
- **Secrets:** no new setting, key or token; no response carries one; the `development_*_token`
  exposure pattern is not used.
- **Errors:** no stack trace or internal detail reaches a client; the `409` texts are the fixed strings in
  §5.3a.

**Authorization / IDOR matrix (every object reference, and where it is checked)**

| Route | Object reference | Check | On failure |
|---|---|---|---|
| `POST /school/students/{id}/transfer-requests` | `student_id` | exists and `school_id ==` caller's profile school, in the query | identical `403` (audited) |
| same | `to_school_id` | exists and differs from the caller's school | `422` |
| `POST /school/transfer-requests/incoming` | `student_code` | resolved server-side; never returned | identical `202` |
| `GET /school/transfer-requests` | none (list) | `WHERE filed_by_school_id = caller's school` in the query, not filtered afterwards | empty page |
| `POST /school/transfer-requests/{id}/cancel` | `request_id` | `filed_by_school_id ==` caller's school, request locked | identical `403` (audited) |
| `GET /school/students/{id}/transfer-history` | `student_id` | `_load_readable_student` (institution; assigned-only Teacher; linked-only Parent) | `403` |
| `GET /school/transfer-destinations` | none | coordinator role; returns `id` + `name` only (new disclosure to a coordinator of the partner-school list, accepted in the approved design) | `403` |
| `/overseas-admin/...` (list, approve, reject, history) | `request_id`, `student_id` | role in `{overseas_admin, super_admin}`; approve re-checks the student's current school under lock | `403` / `404` / `409` |

**Audit requirements** (`SECURITY_CONTROLS.md` §10, fail-closed School-domain rule): filing, cancel,
reject and approve each write their `AuditLog` row **in the same transaction as the change**, so a failed
audit write aborts it; per-moved-parent scope-change rows (S4); a refused probe writes its `denied` row
and commits before the `403` is raised (the ENH-004 pattern); actor, outcome and timestamp are always
present; the throttle's `429` is logged, not audited (no feedback loop). Approve, reject and cancel also
leave the request row itself (`decided_by_user_id`, `decided_at`) as a second record.

**Privacy.** A request's `reason` is free text about a minor: optional, capped, shown only to the
filing coordinator and admins, never to the other school, a parent, or a log. Requests are kept with the
student record; no student-deletion path exists today, and when one does it must include
`school_student_transfer_requests` (recorded for `DATA_MODEL.md`). The only personal data sent outside
the platform is what SCH-007 already sends parents (their child's name in a notice); coordinator notices
are in-app only.

**Reported, not changed (outside ENH-005):** the API has no rate limiting on login or anywhere else; no
CSRF token exists (SameSite=Lax only, which does not cover a hostile sibling subdomain); `secret_key`
defaults to `"change-me"` and `cookie_secure` to `False` (production configuration must override both);
admin routes gate on the `users.role` column rather than active role assignments;
`PATCH /admin/users/{id}` can write `profile` (an admin power).

## 7. Frontend

Every screen has loading, empty and error states (retry on error, no silent failure), follows the
existing school-portal components and CSS, and adds no dependency.

- **`SchoolTransferRequestForm`** inside `SchoolStudentDetailPanel` (coordinator only): destination
  `<select>` fed by `GET /school/transfer-destinations` (loading → disabled; none → "No other schools";
  error → retry), optional reason, submit. Shows a pending-request banner (and hides the form) when the
  student already has one; success confirmation; `409`/`422` messages inline.
- **`/school/coordinator/transfers`** page + `SchoolTransfersPanel` (new nav item): the school's own
  filed requests (paginated, "Load more"; redacted incoming rows show the code only) with status
  badges, **cancel** on pending rows, and a "Request an incoming student" form (student code + reason)
  that shows the generic "submitted for review" message, and a clear message when the open-request cap
  is hit.
- **`AdminSchoolTransferPanel`** wired into `WorkflowPanel.tsx` (a new `showSchoolTransfers` flag beside
  `showSchoolApplications`, overseas-admin/super-admin sections only): pending queue with the preview
  counts and the destination-has-no-portfolio warning; **approve** and **reject** each behind a confirm
  step that states the consequences (parents moved, results withdrawn, teacher unassigned); disabled
  buttons while in flight; the result `outcome` shown after approval; `409` (stale or already decided)
  refreshes the list; the queue is paginated and the reject note field carries the "visible to the
  requesting coordinator" hint (§6).
- **`SchoolTransferHistory`** modelled on `SchoolGradeHistory`, shown in the student detail and parent
  child overview: loading / empty ("No transfers") / error; no staff names.
- Type additions in `lib/types.ts`, calls in `lib/api.ts`; `lib/i18n.ts` and `lib/navigation.ts` only
  where the existing screens already use them. (`WorkflowPanel.tsx`/`navigation.ts` wiring was not read
  in the research pass; the plan's first frontend task reads them before editing.)

### 7.1 Frontend revisions (result of the `frontend-ui-engineering` review, 2026-09-21)

Where this section differs from the bullets above, **this section wins**. It applies
`docs/ux/RESPONSIVE_RULES.md` and `docs/ux/ACCESSIBILITY_RULES.md` (both baseline good-practice rules, not a
conformance claim) and reuses the design language ENH-003 and ENH-004 already established. No new
dependency, and no new global CSS.

**Reuse map (nothing is rebuilt that already exists)**

| Need | Reused from | Notes |
|---|---|---|
| Admin queue rows, coordinator request rows | `.link-list` (`.who` / `.meta`) from `AdminExpiredLinksPanel` | Already wraps and stacks on mobile; buttons go full-width, 44px at ≤640px. **No `<table>`**: `RESPONSIVE_RULES.md` forbids a horizontally scrolling table as the only mobile option, and `AdminSchoolApplicationsPanel`'s table is the counter-example. |
| Loading | `.skeleton-line` (with its `prefers-reduced-motion` rule) + a visible "Loading…" line + `aria-busy` | The `AdminExpiredLinksPanel` pattern. No spinner for content. |
| Errors | `.form-error` with `role="alert"` and a "Try again" button; per-row errors beside the row | Never the silent `res.ok ? res.json() : []` of `AdminSchoolApplicationsPanel` (reported, not changed). |
| Warnings | `.form-warning` (ENH-003) | For "destination has no staff portfolio". Text carries the meaning, not the amber colour. |
| Status | `.status` (+ `.pending`, `.error`) and `.badge` | Always a text label, never colour alone. |
| Filters | `.table-controls` + `.select` + label; "Showing X of Y" `aria-live` line (ENH-004) | A `<select>` status filter, not a new tab widget. |
| Pagination | A "Load more" `.btn secondary small` appending the next `limit`/`offset` page, under the "Showing X of Y" line | The `.pagination` numbered buttons suit page-number APIs, not `offset` + `total`. |
| Two-step confirm | ENH-004's inline confirm (`SchoolPromotionPanel`): text → Confirm/Cancel, focus to Confirm, Escape cancels, focus returns to the trigger | No `window.confirm`, no dialog library. |
| History | the Journey Timeline rail `.jtl-*`, as `SchoolGradeHistory` does | Outcome as a text badge plus a sentence. |
| Focus after a control disappears | `refocus()` from `lib/focus.ts`; programmatic focus target styled like `.summary:focus` | |
| Dates | `formatDate` from `SchoolChildOverview` | |
| Detail-message parsing | one small new `lib/apiErrors.ts` (`detailMessage`, a list-envelope shape check) | `detailMessage` is copy-pasted in three components already; the new components share one copy. The three existing copies are not touched. |
| Portal chrome | `PortalShell`, `SCHOOL_NAV`, `PORTAL_NAV["overseas/admin"]`, `WorkflowPanel` flags | |

**Screens and states**

- **Coordinator: request a transfer (`SchoolTransferRequestForm`, client).** Rendered by
  `SchoolStudentDetailPanel` only when a new `showTransfer` prop is set (default off, exactly like
  `showGradeHistory`, so the Principal and Teacher pages are byte-for-byte unchanged). It sits **last**, in
  a native `<details>` ("Request a transfer") so a rare, consequential action does not compete with the
  student's record; `<details>` gives keyboard and screen-reader behaviour with no script. The destinations
  and this student's pending request are fetched **on the server in the same `Promise.all`** as the
  timeline and history, so the form opens with no client waterfall and no loading state. Fields: a
  `<select>` (placeholder "Select a school", disabled first option), an optional `<textarea>`
  ("Reason", `maxLength` 500), each with a real `<label>` and helper text tied by `aria-describedby`.
  States: **no other schools** → "No other partner schools are available." and submit disabled; **request
  already pending** → the form is replaced by a status line ("Transfer to <School> requested,
  <date>. Waiting for admin review") and the same badge appears in the header card so the state is visible
  without opening the disclosure; **destinations failed to load** → "Transfers are unavailable right now."
  Submitting: button disabled and reads "Sending request…", inputs disabled, one request in flight;
  `422`/`409`/`403` render inline in a `role="alert"` region that takes focus; `401` shows a "Sign in
  again" link; success shows a `role="status"` confirmation, focus moves to it, and `router.refresh()`
  runs in a transition. Filing is reversible (cancel) so it has **no** confirm step; confirmation is kept
  for the irreversible admin actions.
- **Coordinator: `/school/coordinator/transfers` (`SchoolTransfersPanel` + `SchoolIncomingTransferForm`,
  client; the page is a server page like `promotion/page.tsx`: role check first, first page fetched on
  the server, so first paint has no spinner).** A `<select>` status filter (Pending default, All, Approved,
  Rejected, Cancelled), the request list in `.link-list`, "Showing X of Y", "Load more", and Cancel on
  pending rows (disabled while in flight, focus restored with `refocus`). Filter changes and "Load
  more" fetch on the client with `AbortController`; the previous rows stay visible (`aria-busy`) while the
  next page loads, and only a first or filter-change load shows skeleton rows. Redacted incoming rows show
  the Student ID and status plus "Student details are shown once approved", never blank cells or the
  word `null`. Empty: "No pending requests." with the two ways to start one (a link to the roster, and
  the Student ID form below); a filtered-empty state offers "Show pending". The incoming form: a
  labelled Student ID input (`maxLength` 8, `autoCapitalize`, `autoComplete="off"`, `spellCheck={false}`),
  format hint, client-side format validation with `aria-invalid` + `aria-describedby`, and, on `202`, the
  **same** neutral message for every input ("If that Student ID belongs to a student at another school, your
  request has been sent to an admin for review."), so the UI never confirms existence; the field clears and
  keeps focus. The cap (`409`) shows its own message.
- **Admin: `AdminSchoolTransferPanel` + `AdminTransferRow` (client), wired as
  `showSchoolTransfers` for `section === "school-transfers"` in `WorkflowPanel.tsx` and one new item in
  `PORTAL_NAV["overseas/admin"]`.** It loads after first paint (like `AdminExpiredLinksPanel`, so nothing
  else on the page is blocked), heading "Transfer requests (n)" from `total`, a `<select>` status filter,
  `.action-card wide`. Each row: who (`Name (Student ID)`), "From <A> → To <B>", requester and date, the
  reason as text, an "If approved" line built from the preview counts, and the `.form-warning` when the
  destination has no portfolio staff. **Approve** and **Reject** are two-step and inline: Approve shows the
  consequences ("Moves <name> to <B>. Up to N linked parent accounts move to <B> if they have no other
  child at <A>. M unpublished results are withdrawn. The teacher assignment is cleared. This cannot be
  undone here.") with Confirm/Cancel; Reject shows an optional labelled note `<textarea>` with the hint
  "Visible to the requesting coordinator. Do not include student details." and a Confirm reject button.
  Focus goes to Confirm when it opens, Escape or Cancel returns it to the row's trigger, and after a
  decision the row leaves the pending list and focus moves to the always-mounted `role="status"` feedback
  region ("Moved <name> to <B>. 1 parent moved, 2 kept, 3 results withdrawn."). `409` (already decided,
  stale, lock busy) shows the server's message and refetches. Every button carries an `aria-label` that
  names the student and school and contains its visible text.
- **`SchoolTransferHistory` (server-safe presentational + `loadTransferHistory`).** Rendered by
  `SchoolStudentDetailPanel` (coordinator) and the parent child page, loaded in the same `Promise.all`
  as the timeline and grade history. **It renders a card only when there is at least one transfer, or
  when the load failed ("Transfer history is unavailable right now.")**: an empty "Transfer history" card
  on every student page would add clutter for the common case, so the empty state is the absence of
  the card. Text badge "Transferred" + "Moved from <A> to <B>" + date.
- **Parent dashboard (one small change to an existing page).** After a transfer a parent can have
  children at two schools, and the child card does not name the school. Each child's overview is already
  loaded there, so the card shows a "School: <name>" line **only when the parent's children span more
  than one school**; a single-school parent's page is unchanged.

**Responsive (320 / 768 / 1024 / 1440px).** Single column below 768px with labels visible; `.link-list`
rows wrap; buttons full-width at ≤640px with 44px minimum height; controls at 16px on coarse pointers so
iOS does not zoom on focus (the ENH-004 precedent). Long school and student names use `overflow-wrap:
anywhere`. The only permitted new CSS is a small `AdminSchoolTransferPanel.module.css` for the inline
confirm block and the focus outline on programmatic focus targets (the `SchoolPromotionPanel.module.css`
precedent), and only if the reused classes prove insufficient in the browser run.

**Accessibility.** Real `<label>`s; errors identified in text and tied to fields; live regions mounted
from the start so results are announced; `role="alert"` for request errors and `role="status"` for
results; visible focus from the existing `:focus-visible` rules; lists are lists (`role="list"` with an
`aria-label`); headings follow the existing `h2` card / `h3` section pattern with none skipped; status is
always text plus badge; no interaction is pointer-only or hover-only.

**Perceived performance.** Server-first pages with parallel fetches (no client waterfall, no spinner on
first paint); the admin panel loads after paint; **no optimistic updates** (the server decides and a
decision can fail); after an action the affected row is updated from the server's response immediately and
`router.refresh()` runs in a transition; refetches keep old rows on screen instead of blanking; row
components are `memo`'d with primitive props. No `loading.tsx` (no route has one and there is no shared
`school/layout.tsx`, so it would render without the portal shell; the ENH-004 finding).

**Component size.** Each new component stays under about 200 lines: `SchoolTransferRequestForm`,
`SchoolIncomingTransferForm`, `SchoolTransfersPanel`, `SchoolTransferHistory`, `AdminSchoolTransferPanel`,
`AdminTransferRow`; shared types, the status label/badge map and the fetch helpers in one `lib/transfers.ts`.

**Frontend tests (written before the code they cover).** vitest + Testing Library, one file per component:
loading (skeleton, `aria-busy`), empty, error with retry, success announcement, double-submit blocked,
field errors tied by `aria-describedby`, Escape cancels a confirm and focus returns to the trigger, focus
moves to Confirm, `409` refetches, `401` shows the sign-in link, a redacted row never renders `null` or a
blank, the incoming form's message is identical for every input, `SchoolStudentDetailPanel` with
`showTransfer` off renders exactly as before, the history card is absent when empty and present when
entries or a failure exist, and the parent dashboard shows the school line only for a multi-school parent.
The Playwright spec adds a keyboard-only approve path and a no-horizontal-overflow check at 320/768/1024/
1440px; a manual screen-reader and reduced-motion pass is recorded in the plan. No new dependency
(axe-core is not added).

**Reported, not changed (outside ENH-005):** `AdminSchoolApplicationsPanel` swallows load failures and
renders a horizontally scrolling table; `SUPER_ADMIN_NAV` has no entry for the school admin panels
(a super admin reaches them by URL only).

## 8. Forced changes to existing behavior (the only ones)

1. **Parent scope is link-only.** `_scoped_students_query` (`schools.py:643`): the `school_parent`
   branch drops the `school_id` filter and keeps the link filter. `_load_readable_student`
   (`schools.py:864`): the `school_parent` branch skips the institution check and keeps the link
   check, and keeps today's message precedence for parents (an unlinked student at a different school
   still answers "This student is at a different institution", an unlinked student at the parent's
   own school still answers "This student is not linked to your account"), so no status code or
   message a client sees today changes. `_own_school_id(user)` is still called, so a parent with no
   school still gets `403`. Every
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

4. **Two small frontend changes to existing screens (§7.1):** `SchoolStudentDetailPanel` gains an
   opt-in `showTransfer` prop (default off), and the parent dashboard child card shows a school line only
   for a parent whose children span more than one school. No other existing component is modified.

5. **Mailer escaping (D9, security review S1):** `_parent_notification_html` in `mailer.py` escapes the
   values it interpolates. Output changes only for text containing `<`, `>`, `&` or quotes, which a mail
   client renders as the same characters. Its own commit and test.

Nothing else changes: existing endpoint shapes, `student_code`, the promotion flow, the results
workflow's actor-separation (DEC-ROLE-007), `SchoolStaffAssignment` (portfolio follows `school_id`
automatically), `admin.py` bridge endpoints (global, not school-scoped), attendance and activities.

## 9. Error states and edge cases

| Situation | Behavior |
|---|---|
| Same-school destination | `422` |
| Unknown destination school | `422` |
| Outgoing request for another school's or an unknown student | identical `403` |
| Pending request already exists (outgoing) | `409` (application check, backed by the partial index) |
| School already has 50 open requests | `409`, checked before any student lookup |
| Incoming: unknown code / own school / duplicate | identical `202 {"accepted": true}`, nothing created |
| Incoming: malformed code | `422` (format only) |
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
  is created with `filed_by_school_id` equal to the caller's school and the server-derived from-school.
- **AC-02** Outgoing filing is rejected: another school's student and an unknown student ID both give the
  identical `403`; same-school or unknown destination `422`; non-coordinator `403`; a client-supplied
  `from_school_id`/`filed_by_school_id`/`status`/`school_id` `422`; a malformed UUID or a control
  character in `reason` `422`, never `500`.
- **AC-03** A second pending request for the same student is `409` (also proven at the DB level).
- **AC-04** Incoming filing returns the identical `202 {"accepted": true}` for valid, unknown, own-school
  and duplicate inputs; a row is created only for a valid other-school student; unknown/own-school
  attempts are audited `denied`; a malformed code is `422`.
- **AC-05** A not-yet-approved incoming row has `student_id`, `student_name` and `from_school` all `null`
  and exposes the code, status, reason and timestamps; once approved it is complete. The response schema
  is identical either way.
- **AC-06** Only a coordinator of the filing school (`filed_by_school_id`) can cancel, only while
  `pending`; an unknown request ID and another school's request give the identical `403`. A coordinator
  never sees another school's requests in the list.
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
  student with no staff IDs and no `reason`; an admin gets all statuses with names.
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
- **AC-20** A school with 50 open requests gets `409` on the 51st (outgoing and incoming alike, the
  incoming one before any lookup); cancelling or deciding one frees a slot.
- **AC-21** The two paginated lists honour `limit` (default 25, `1..100`) and `offset` (≥ 0), reject
  out-of-range values with `422`, order `created_at DESC, id DESC`, and return `total`; the `status`
  filter on both lists defaults to `pending` and rejects an unknown value with `422`.
- **AC-22** Notices to an incoming requester on rejection carry the student code only, never the name or
  the source school; approval notices name the student to both coordinators and the parents.
- **AC-23** The admin preview counts are computed without per-row queries (asserted by a query-count
  test over a page of requests).
- **AC-24** Frontend design-language and accessibility: the new screens reuse the existing classes
  (§7.1 reuse map), render no table, do not overflow horizontally at 320/768/1024/1440px, are fully
  operable by keyboard (Tab order, Enter/Space, Escape closes a confirm, focus lands on Confirm and
  returns to the trigger), announce results through mounted live regions, and never convey status by
  colour alone.
- **AC-25** `SchoolStudentDetailPanel` without `showTransfer`, and the Principal/Teacher pages, render
  exactly as before; the parent dashboard shows a school line for a child only when the parent's
  children span more than one school; the transfer-history card is absent when a student has no transfer
  and shows an "unavailable" line (not nothing) when its load fails.
- **AC-26** The 31st filing attempt by one coordinator within a rolling hour is `429` with `Retry-After`
  and a warning log, for outgoing and incoming alike, valid or not; attempts that fail validation (`422`)
  do not count; another coordinator is unaffected; the count is read from `AuditLog`, so it holds across
  processes; after the window it lapses.
- **AC-27** Audit completeness: every filing attempt that passes validation writes exactly one row;
  cancel, reject and approve each write one in the same transaction as the change (an injected audit
  failure aborts the change); each moved parent gets its own `school.user_school_scope_changed` row; a
  refused probe's `denied` row is committed before the `403`; no audit metadata contains a student code,
  reason, note or name.
- **AC-28** Approval writes only `profile.school_id`, and only on `school_parent` accounts: `role`,
  `division`, role assignments, `active`, `email` and `password_hash` of every linked user are unchanged,
  and a linked non-parent user is untouched.
- **AC-29** Same-school link invariant (S2): `link_parent`, `_link_or_invite_parent` and `accept_invite`
  each refuse (or skip) a parent/student pair from different schools; a parent still cannot read a
  student they are not linked to. A read-only pre-release query over existing data finds 0 links whose
  parent's school differs from the student's.
- **AC-30** Email safety (S1): with `<script>` / `"><img …>` / `&` in a student name, a school name and a
  parent name, the HTML part of `send_parent_notification_email` contains the escaped text and no live
  tag; notification `action_url`s for ENH-005 match `^/school/[a-z-]+(/[a-z-]+)*(/[0-9a-f-]{36})?$`.
- **AC-31** Logging hygiene (S8): a `caplog` test across every ENH-005 route asserts no log record
  contains a student code, reason, note, student or parent name, or email; the `429` and lock-timeout
  warnings carry IDs and counts only.
- **AC-32** Input hardening (S7, S9): a `student_code` of Unicode digits or look-alikes is `422`; a
  `reason`/`note` with U+202E or U+2066 is `422` while one with U+200D is accepted; every ENH-005
  mutation route is registered as `POST` and no ENH-005 route is a state-changing `GET`.

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
| Migration | `0034` | migration applies on a copy of the seeded DB; existing rows untouched; downgrade drops only the new table; the partial unique index and CHECKs exist in both the model and the migration |
| Security (S1–S9): mailer injection, link invariant, probing throttle, scope-change audit, approval write set, log hygiene, POST-only | `mailer.py`, `school_transfers.py`, link creators in `schools.py` | AC-26 – AC-32, plus a read-only pre-release data query (parent/student school mismatch count = 0) run by the user against the Docker database |
| New-endpoint contract (validation, masking, redaction, pagination, cap, privacy) | `school_transfers.py` | AC-02, AC-04, AC-05, AC-06, AC-20 – AC-23: table-driven tests over the §5.3a error catalogue, the redacted/complete response schema, and a query-count test for the admin preview |
| Existing E2E specs | `sch-001`, `sch-003`, `sch-007`, `sch-008`, `enh-004` | rerun the affected specs (Docker stack brought up by the user) |

**Test files (to be written first, per task):** `apps/api/tests/test_enh_005_school_transfer.py` (real
Postgres, following `test_enh_004_student_promotion.py`, including its raw-SQL concurrency helper);
vitest component tests `SchoolTransferRequestForm`, `SchoolIncomingTransferForm`, `SchoolTransfersPanel`,
`AdminSchoolTransferPanel` (covering `AdminTransferRow`), `SchoolTransferHistory`, plus the
`SchoolStudentDetailPanel` and parent-dashboard changes (AC-24/AC-25); Playwright `apps/web/tests/e2e/enh-005-school-transfer.spec.ts`. The full
backend/E2E regression is run at the standing cadence, not after every task; targeted suites run per
task.

## 12. Documentation deliverables

- `DEC-SCOPE-021` in `docs/decisions/PRODUCT_DECISION_REGISTER.md` (D1–D7, A1–A3, non-goals).
- `docs/architecture/DATA_MODEL.md`: the new table and the `withdrawn` result status.
- `docs/architecture/API_CONTRACT.md` §12A: the ten endpoints (six coordinator, four admin), the error
  catalogue (§5.3a), the redaction rule, and a note that these two lists use `limit`/`offset` rather than
  §0.1's cursor (D6).
- `docs/architecture/RBAC_MATRIX.md` §2.12: the transfer rows and the parent link-based scope note,
  including the same-school-link invariant (S2) and the moved-parent account authority (S6).
- `docs/architecture/SECURITY_CONTROLS.md` §6A (cross-institution isolation now includes transfer) and
  §10 (School-domain fail-closed audit rows for transfer, scope-change rows), and a School-domain entry in
  `THREAT_MODEL.md` for the code-probing and email-injection abuse cases.
- `docs/delivery/ENHANCEMENT_BACKLOG.md`: ENH-005 status line.
- The ENH-004 spec/plan note about the immutability claim.
- An implementation plan at `docs/superpowers/plans/2026-09-21-enh-005-student-school-transfer.md`.

## 13. Open items (`NEEDS_CONFIRMATION`, not decided here)

- **A pending parent invitation does not survive a transfer (found by the browser E2E, 2026-09-21).** §5.4 step 5 clears the student's
  `pending_parent_email`, because the pending `SchoolAccountInvite` belongs to the losing school and `accept_invite` links only students at
  the invite's own school. A parent who was invited but had not yet accepted therefore ends up, after accepting, with an account at the
  losing school and **no linked child**, and the gaining coordinator cannot link them (`link_parent` requires a parent at their own school).
  Active links are unaffected (D1). Options: carry the pending intent to the gaining school (an S2 change: a link creator would then need a
  cross-school exception), show the admin a "pending parent invitations" count in the approval preview so it is a conscious choice, or accept
  it and tell coordinators to confirm invites are accepted before requesting a transfer.
  **Mitigated, not resolved (2026-09-21).** The second option was built, as a boolean rather than a count (a student has one pending parent
  email): the admin's preview carries `pending_parent_invite`, and the queue row and the confirm step both warn in words before the irreversible
  approval. The behavior itself is unchanged: an invite still does not survive a transfer. Whether to carry it to the gaining school (option 1)
  is still an owner decision.

- **The other school is not told of a pending request** (D5). The losing school learns of a
  gaining-filed request, and the gaining school of a losing-filed one, only when the admin decides.
  Whether either should be consulted first (a consent step) is not decided.

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

## 14. Implementation notes (deviations from this spec, recorded 2026-09-21)

Where the code differs from what §5–§7 say, the code is what shipped and this list is the honest record. None changes a decision in §3.

- **Free text (§5.2, S7):** `reason`/`note` reject control characters **except line breaks and tabs** (they are `<textarea>` fields), plus U+202A–U+202E and U+2066–U+2069; zero-width joiners stay allowed.
- **Destinations:** `GET /school/transfer-destinations` returns `SchoolRef` items; no separate `TransferDestination` type was created.
- **Admin preview:** `preview` is present only on `pending` rows (it describes what approval would touch) and `null` on decided rows.
- **Cancel refusal and the throttle:** the identical `403` for cancelling an unknown or not-yours request is audited with the same `denied` action the filing refusals use, so it counts toward the hourly throttle.
- **Conflicts:** an `IntegrityError` or a lock wait past the bound on approve/reject both answer `409` with the "Another change to this student is in progress; retry" message.
- **Admin workspace payload:** `GET /portal/overseas/admin/school-transfers` was added (a table of the 200 most recent requests). `PortalPage` needs both a `PORTAL_NAV` entry and a backend payload or an admin section is a 404; browser QA found this before it shipped.
- **Redaction on cancel:** cancelling a request the school filed as *incoming* returns the redacted view, like the list.
- **Routing:** on this FastAPI version (0.141) `app.routes` does not flatten included routers, so route-shape tests introspect the two routers directly.
- **The detail-panel wiring** passes `pending` from a single `?status=pending&limit=100` read (a school has at most 50 open requests), and offers the form even if that lookup fails, because the server refuses a duplicate.
