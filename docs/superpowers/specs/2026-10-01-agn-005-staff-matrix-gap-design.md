# AGN-005 — Close the §6 Staff Matrix Gap for Agency Student Records: Design

**Status:** draft for owner review (2026-10-01). **Branch:** `feature/agn-005-staff-permission-matrix` (from `origin/main` 6360dc0).
**Decision:** none new — no behaviour changes. Scope set by the owner in-session (2026-10-01): "close the matrix gap", tests and docs only.
**Backlog:** `ENHANCEMENT_BACKLOG.md` §AGN-005 (AGN-005-AC01…AC06, added with the tests).
**Builds on:** `AGN-003` (`DEC-SCOPE-044`, spec `2026-10-01-agn-003-staff-permissions-design.md`, COMPLETE) and `AGN-004`
(`DEC-SCOPE-042`, spec `2026-09-30-agn-004-agent-students-design.md`, COMPLETE).
**Evidence:** `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §6 "Master vs Staff Permissions". The approval is the
owner's, not the document's.
**Oriented with:** Graphify query (graph refreshed 2026-10-01; the earlier graph had no AGN-001…004 nodes) and targeted reads.
**Reviewed with:** api-and-interface-design, frontend-ui-engineering, security-and-hardening (in-session, 2026-10-01; findings in §10 and
folded into §5–§7).

## 1. Intent

The owner's `AGN-005` statement (in-session, 2026-10-01) repeats `AGN-003`'s word for word: "the §6 matrix: Staff are limited to the
student journey, with no admin modules; 'Set permissions' / 'Permission Level'." Acceptance: every ❌ cell in §6 returns 403 for Staff
with a test; every ✅ cell succeeds; toggles flip the two optional rows; a toggle change applies on the next request.

`AGN-003` built and proved all of that on `main`, **except** for the student rows. Its matrix (spec §3, `RBAC_MATRIX.md` §2.8,
`test_agn_003_matrix.py`) was drafted before `AGN-004`'s `/workflows/overseas/agent/crm/students` routes reached `main`, and still marks
Edit Student, Delete Student and Assign Student **N/A** ("no route"). Those routes now exist and already behave as §6 requires; they are
just not in the matrix, and one cell — unarchive by the assigned staff member — has no test anywhere.

**Owner answers (in-session 2026-10-01):**
- **Q1 — Scope.** AGN-005 closes the matrix gap: tests and docs only, no production code change.
- **Q2 — Delete Student.** There is no delete route (`DEC-SCOPE-042` D5: agencies archive only). The row maps to **archive and
  unarchive**: Staff `403`, Master `200`.
- **Q3 — Where.** Extend `test_agn_003_matrix.py` so the §6 matrix stays in one file.
- **Q4 — AGN-021.** The parallel `feature/agn-021-staff-permission-matrix` branch (docs only, a different per-agency design) is left
  alone.

The toggle and "next request" criteria are already proven by `AGN-003` (`test_agn_003_permissions.py`, `test_agn_003_verify.py`) and
are cited, not repeated.

## 2. Out of scope

- Any change to `app/` code, migrations, API contracts or web components (one web **test** is added, §5).
- AGN-004's validation-before-role order on `PATCH` and `…/assign` (§10, recorded, not changed).
- Edit Application, Change Application Status, Staff Performance, CRM Settings — still no agent route; they stay N/A.
- Editing a linked student (one with a login): AGN-004 answers `409 "Linked students are edited in their own account"` for every agent;
  that is AGN-004 behaviour, tested there.
- `AGN-021`.

## 3. The student rows as they will be tested

`RECORDS = /api/v1/workflows/overseas/agent/crm/students`. `{record}` is an active student with no login, belonging to the agency and
assigned to the calling staff member; `{archived_record}` is the same, archived.

| §6 row | Call | Staff | Master |
|---|---|---|---|
| Create Student | `POST RECORDS` `{"full_name": "Matrix New Student"}` | 201 | 201 |
| View Students | `GET RECORDS` | 200 | 200 |
| View Students | `GET RECORDS/{record}` | 200 | 200 |
| Edit Student | `PATCH RECORDS/{record}` `{"full_name": "Edited Student"}` | 200 | 200 |
| Delete Student | `POST RECORDS/{record}/archive` | 403 "Only an agency Master can archive students" | 200 |
| Delete Student | `POST RECORDS/{archived_record}/unarchive` | 403 "Only an agency Master can archive students" | 200 |
| Assign Student | `POST RECORDS/{record}/assign` `{"member_id": "{other_staff}"}` | 403 "Only an agency Master can assign students" | 200 |

**Why the records are assigned to the caller.** In `api/agent_students.py` the scoped load (`_locked_row` → `load_scoped`) runs before
`_require_master_action`. On a student not assigned to them, staff get AGN-004's existence mask `404 "Student not found"`
(`RBAC_MATRIX.md` §2.8), so the test would be passing on the wrong gate. Each refusal therefore asserts the exact `detail`.

**Why assign names another staff member.** If the guard were missing, the record's `assigned_member_id` would visibly change, which the
"nothing changed" check (§4) catches.

## 4. Approach

**Approaches considered.**
- **(A) chosen: extend `test_agn_003_matrix.py`'s three parametrised lists.** One matrix in one file; reuses `_world`, `_call`, `_fill`
  and the `agn004_helpers.mk_record` helper; no new helper.
- **(B) a new `test_agn_005_matrix.py`.** Leaves AGN-003's file untouched but splits the matrix (owner chose A).
- **(C) docs only, citing AGN-004's tests.** Unarchive by the assigned staff member has no test anywhere, so C cannot meet "each ❌ cell
  with a test".

**Changes to `test_agn_003_matrix.py`.**
1. `_world` adds `record` (`mk_record(db, agent=ctx["master"], full_name="Matrix Record", assigned_member=caller["member"])`) and
   `archived_record` (same, `status="archived"`), and puts both ids in `ids`. Both have no email or phone, so AGN-004's duplicate check
   never fires.
2. `STAFF_REFUSED` gains the three `403` rows, `BOTH_ALLOWED` the four ✅ rows, `MASTER_ALLOWED` the three Master rows (§3).
3. `test_staff_refused`'s "a refused call changes nothing" block also reloads both records and asserts: `record` is `active`, assigned to
   the caller and named "Matrix Record"; `archived_record` is `archived`; and no `AuditLog` row with an `agent_student.` action exists for
   either record id.
4. The module docstring stops listing Edit/Delete/Assign Student as N/A and points to AGN-005.

Every existing row, assertion and expected value is unchanged.

**Proving the new tests can fail.** The behaviour already exists, so the new rows pass on first run — there is no natural red phase. As a
one-off mutation check, `_require_master_action`'s two call sites in `api/agent_students.py` are commented out in the working copy, the
three new refusal cases are run and must fail, then the file is restored and `git diff --exit-code apps/api/app` must be clean. The
observed result is recorded in the RTM. Nothing from the mutation is committed.

## 5. Transactions, races, authorization, errors, frontend

- **Transactions.** No production code changes. The refused calls take the organisation row lock (`lock_active_org`) and then raise
  `403`; the request's session rolls back and releases the lock — AGN-004 behaviour, already exercised by
  `test_agn_004_student_actions.py::test_assigned_staff_cannot_archive_or_assign`.
- **Races.** None introduced. Each test builds its own organisation (`mk_active_org` with a unique name), so cases do not share rows.
- **Authorization.** Unchanged: `is_agent_staff` in `_require_master_action`, scope in `services/agent_students.load_scoped`. The tests
  pin the exact refusal text so a `404` or another gate's `403` cannot pass.
- **Error states.** `403` refusals asserted by exact `detail`; no new error path.
- **Frontend.** No component change, so no new loading, empty or error state, layout, form or keyboard path.
  `AgentStudentsPanel.tsx` gates every Master-only control on `isMaster` (the filter at line 224, Archive/Unarchive at 346, Assign at
  378), and the server enforces the same rules. The existing test "hides Master-only controls from staff" checks an **active** card
  only (Archive, Assign, the Assigned-to filter). The UI mirror of the backend gap is that no test checks that staff who tick
  **Show archived** see no **Unarchive** button. One vitest case is added to `apps/web/tests/components/AgentStudentsPanel.test.tsx`:
  staff, Show archived on (URL `?archived=1`, the panel's QA-06 pattern) and the list returning `item({ status: "archived" })` → no
  `Unarchive Asha Rao` button, `View Asha Rao` present. It uses the file's existing `res`/`page`/`item` fixtures.
- **Data.** No migration; test data only, in the test database.

## 6. Acceptance criteria

- **AGN-005-AC01** On a student assigned to them, staff get `403` with the exact message on archive, unarchive and assign; the record is
  unchanged and no `agent_student.*` audit row is written. → `test_agn_003_matrix.py::test_staff_refused[Delete Student-…]`,
  `[Assign Student-…]`
- **AGN-005-AC02** Staff create (`201`), list, open and edit (`200`) their assigned student with no login through `crm/students`.
  → `test_agn_003_matrix.py::test_staff_allowed[Create Student-post-…crm…]`, `[View Students-…crm…]`, `[Edit Student-…]`
- **AGN-005-AC03** A Master succeeds on every AC02 row plus archive, unarchive and assign (`200`). → `test_master_allowed[…]`
- **AGN-005-AC04** In `RBAC_MATRIX.md` §2.8 no §6 row that has an agent route is N/A; only Edit Application, Change Application Status,
  Staff Performance and CRM Settings remain N/A.
- **AGN-005-AC05** No change under `apps/api/app`, `apps/api/alembic`, `apps/web/components`, `apps/web/lib` or `apps/web/app`; every
  pre-existing `test_agn_003_matrix.py` and `AgentStudentsPanel.test.tsx` case is unchanged and passing; the lite regression set is green.
  *Superseded in part (owner, in-session 2026-10-01, "Fix them"):* browser QA findings QA5-01, 02, 03 and 05 were fixed on this branch,
  so the "no production change" clause no longer holds for those four (`docs/quality/AGN-005_BROWSER_QA_2026-10-01.md`; RTM AGN-005
  row). The test clause still holds, except the one deliberate change recorded there
  (`test_agn_004_students.py::test_phone_formats_match_on_digits_only`, 4-digit phone now `422`).
- **AGN-005-AC06** Staff who show archived students see no Unarchive control on an archived card (the UI follows the server's `403`).
  → `AgentStudentsPanel.test.tsx` "hides Unarchive from staff on an archived student"

## 7. Tests (decided before writing them)

- **New / extended (backend):** `apps/api/tests/test_agn_003_matrix.py` (3 refused + 4 × 2 allowed + 3 Master-only = 14 new cases).
- **New (web):** one case in `apps/web/tests/components/AgentStudentsPanel.test.tsx` (AC06). Mutation check: flip line 346's
  `isMaster &&` locally, see the case fail, restore, `git diff --exit-code apps/web/components` clean.
- **Mutation check (backend):** §4.
- **Lite regression set** (per `test-regression-cadence`): `test_agn_00*` (all AGN-001…004 files, including `test_agn_003_matrix.py`),
  `test_agt_00*`, `test_ovs_005_documents.py`, `test_enh_031_*`; web `vitest run tests/components/AgentStudentsPanel.test.tsx`.
- **Not needed:** Playwright (no component change; `agn-004-agent-students.spec.ts` already drives the staff UI); migration tests.

## 8. Regression risks

| Risk | Mitigation |
|---|---|
| `_world`'s new records affect every existing matrix case | No login, email or phone, so no duplicate or uniqueness clash; the full matrix file runs in the lite set; about two extra inserts per case |
| A new case passes on the wrong gate (`404` mask, another `403`) | Exact `detail` asserted; records assigned to the caller |
| A refusal silently mutates data | Extended "nothing changed" block (§4 item 3) |
| The tests could never fail | Mutation check (§4) |
| The new web case leaks URL state into later cases | The file's `afterEach` already resets `window.history` (QA-06) |
| Docs drift again | `RBAC_MATRIX.md` §2.8 updated; a dated note in AGN-003 spec §3 points here |

## 9. Documentation to update with the tests

- `RBAC_MATRIX.md` §2.8 AGN-003 matrix: Edit, Delete and Assign Student rows get their routes; Create and View list the `crm/students`
  routes; the N/A bullet and "Proved by" line updated; an AGN-005 note.
- `2026-10-01-agn-003-staff-permissions-design.md` §3: a dated note pointing here (the historical table stays as designed).
- `ENHANCEMENT_BACKLOG.md`: revision note, summary table row and §AGN-005 entry.
- `RTM.md`: AGN-005 row with the evidence.
- Not changed: `API_CONTRACT.md`, `DATA_MODEL.md`, `SCREEN_CATALOG.md` (nothing in them changes).

## 10. Review log (2026-10-01)

**api-and-interface-design**
- **Contract check.** Every status and `detail` the new rows assert matches `API_CONTRACT.md` lines 236–241 (AGN-004 table):
  create `201 {student}`; list `{items, total, limit, offset}`; detail `{student}`; `PATCH` `200`; archive/unarchive Master `200`, staff
  `403 "Only an agency Master can archive students"` after the scope `404`; assign Master `200`, staff
  `403 "Only an agency Master can assign students"`. No contract text changes; `API_CONTRACT.md` is not edited.
- **HTTP semantics.** `403` for an in-scope Master-only action, `404` for out of scope (existence mask), `409` for state conflicts —
  consistent with AGN-004. The matrix uses in-scope, state-valid rows (active record for archive/assign, archived record for unarchive)
  so each Master `200` and each staff `403` is caused by the role, not by state.
- **Hyrum's law.** The tests pin the `detail` strings, as `test_agn_003_matrix.py` already does for every other ❌ row. These strings
  are documented in the contract, so pinning them adds no new commitment.
- **Backward compatibility, validation, transactions, database usage.** No route, schema, query or transaction changes.

**frontend-ui-engineering**
- No component change, so visual hierarchy, responsive behaviour, loading, empty and error states, forms, keyboard support and perceived
  performance are as AGN-004 shipped and browser-verified them (`docs/quality/AGN-004_BROWSER_QA_2026-10-01.md`). Improving them is
  outside AGN-005 (owner: no speculative changes).
- Finding: no test covers the staff view of an **archived** card. Added as AC06 (§5); a test only.

**security-and-hardening**

| Check | Finding |
|---|---|
| Authentication | Unchanged (`get_current_user`, cookie JWT + `session_version`). Every new case signs in as a real member through `client_for`. |
| Authorization / role escalation | The three staff escalation paths for student records (archive, unarchive, assign) are each proven `403`, with the record unchanged and no audit row. Assign names another staff member, so a missing guard would show as a reassignment. |
| IDOR / cross-tenant | Unchanged and already proven by AGN-004: another staff member's student → `404` on every action (`test_agn_004_student_actions.py::test_other_staff_get_404_on_every_action`); another agency's Master → `404` (`::test_other_agency_master_gets_404_on_every_action`, `test_agn_004_students.py::test_other_agency_master_gets_404_and_never_sees_rows`). Cited, not repeated. |
| Input validation | **Observation, not changed:** `PATCH /crm/students/{id}` and `POST …/assign` declare typed bodies, so FastAPI answers a malformed body with `422` before the handler can refuse staff with `403`. This differs from AGN-003's "a refused role gets `403` before any validation" rule. It reveals nothing (the schemas are public and the scope `404` still applies before any data is read). It is AGN-004 behaviour; recorded here and in the RTM as a follow-up candidate. The matrix uses valid bodies so it tests the role check. |
| XSS / CSRF / SQL injection | No new rendering, endpoint or query. Unchanged: React text rendering; `SameSite=lax` httpOnly cookies + credentialed CORS to `frontend_url` only; SQLAlchemy ORM. |
| Token/session, secrets, sensitive logs | No change. Fixtures use `@example.local` addresses and no secrets; the new records carry no email or phone. |
| Rate limiting | No change; none of these routes send email. |
| Audit | Allowed writes audit as AGN-004 designed; refused calls write no `agent_student.*` row (asserted, §4 item 3). Refusals are not audited anywhere in the agent routes today; unchanged. |
