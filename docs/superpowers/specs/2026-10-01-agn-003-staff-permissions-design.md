# AGN-003 — Agent Staff Permissions (Master vs Staff matrix): Design

**Status:** draft for owner review (2026-10-01). **Branch:** `feature/agn-003-staff-permissions` (from `origin/main` 1a0177c).
**Decision:** `DEC-SCOPE-041` (P1–P8). **Backlog:** `ENHANCEMENT_BACKLOG.md` §AGN-003 (AGN-003-AC01…AC09).
**Builds on:** `AGN-001` (`DEC-SCOPE-038`, migration `0046_agent_orgs`) and `AGN-002` (`DEC-SCOPE-040`, migration
`0047_agent_org_staff`, spec `2026-09-30-agn-002-staff-logins-design.md`).
**Evidence:** `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §2 "Set permissions", §3 "Permission Level",
§4 "Staff Login – Student Journey Only", §6 "Master vs Staff Permissions". The approval is the owner's, not the document's.

## 1. Intent

Staff are limited to the student journey with no admin modules, per `EVID-015` §6. Two §6 rows are optional: **Verify Documents**
(⚠️ Optional) and **Reports** (❌/Limited). A Master switches them on or off **per staff member**. Masters are never limited.

**Owner's acceptance criteria (in-session, 2026-10-01):**
- Every ❌ cell in §6 returns `403` for Staff, with a test.
- Every ✅ cell succeeds.
- The toggles flip the two optional rows.
- A toggle change applies on the next request.

**Owner's answers (in-session 2026-10-01, `EXPLICIT_APPROVAL`) — recorded as `DEC-SCOPE-041`:**
- **P1 — Toggles.** Verify Documents and Reports are the two optional rows. Both are **off by default** for Staff.
- **P2 — Granularity.** Toggles are stored **per staff member**, set by a Master from the staff row ("Set permissions").
- **P3 — Reach.** The matrix is enforced on routes that exist today. Rows with no capability for anyone are recorded **N/A**
  (§3) and stay parked. The one new capability is agent document verification, so that the Verify toggle has something to switch.
- **P4 — Student scope.** Staff keep agency-wide students and applications (`DEC-SCOPE-040` S1). Assignment/ownership (§7 of
  the source) stays parked under `C-10`.
- **P5 — Agent review only on pending documents.** An agent (Master, or Staff with Verify) may decide only a document whose
  `verification_status` is `pending`. A counselor's or Overseas Admin's decision is never overwritten by an agent. They can still
  re-review anything an agent decided.
- **P6 — Staff outcome.** Staff with Verify may record `verified` only. `rejected` and `changes_required` → `403`. Masters may
  record all three.

**Assumptions stated by design (owner may correct):**
- **P7** "Permission Level" is not a create-form field. New staff start with both toggles off; the Master sets them afterwards.
- **P8** Toggles can be set on a deactivated staff member and survive reactivation. Setting them sends no email, so there is no
  throttle. Every change is audited.

## 2. Out of scope

Each of these stays parked under `C-10`:
- Staff assignment/ownership and assigned-only views.
- Staff performance and staff activity.
- CRM settings.
- Create / Edit / Delete Student as new records.
- Agent Edit Application and Change Application Status.
- Add University by agents.
- "Limited" dashboards beyond today's commission-free staff dashboard.

Also out of scope, recorded in §10 as known security debt:
- The agency gate is missing on `/files/*`, notifications, support and communications.
- `/files/download` presigns any key.

## 3. The §6 matrix as built

Legend:
- ✅ = succeeds (tested).
- ❌ = `403` (tested).
- T = follows the staff member's toggle (tested both ways).
- N/A = no route for any agent, so no test is possible. Recorded here and parked.

| §6 row | Route(s) | Master | Staff |
|---|---|---|---|
| Dashboard | `GET /portal/overseas/agent/dashboard` | ✅ full | ✅ limited (no commission figures, AGN-002) |
| Create Student | `POST /workflows/overseas/agent/students` (links an existing student) | ✅ | ✅ |
| View Students | `GET /workflows/overseas/agent/students`, `GET /portal/overseas/agent/students`, `GET /lookups/overseas-students` | ✅ agency | ✅ agency (P4) |
| Edit Student | — | N/A | N/A |
| Delete Student | — | N/A | N/A |
| Assign Student / Assign Students | — | N/A | N/A |
| Create Application | `POST /workflows/overseas/applications` | ✅ | ✅ |
| Edit Application | — (counselor/rep/admin only) | N/A | N/A |
| View Applications | `GET /workflows/overseas/applications`, `GET /portal/overseas/agent/applications`, `GET /lookups/overseas-applications` | ✅ | ✅ |
| Change Application Status | — (counselor/admin only) | N/A | N/A |
| Upload Documents | `POST /workflows/overseas/documents`; `GET /portal/overseas/agent/documents` | ✅ | ✅ |
| Verify Documents | `PATCH /workflows/overseas/documents/{id}/verify` with `verified` (**new for agents**, §6) | ✅ | **T** |
| Reject Documents | same route with `rejected` or `changes_required` | ✅ | ❌ (even with Verify on) |
| University Database | `GET /public/universities`, `GET /public/universities/{slug}` | ✅ view | ✅ view |
| Add University | `POST /admin/universities` (admin only) | ❌ | ❌ |
| Staff Management | `GET /workflows/overseas/agent/team/staff`, `PATCH …/staff/{id}`, `PUT …/staff/{id}/permissions` (**new**), `GET /workflows/overseas/agent/team`, `GET /portal/overseas/agent/team` | ✅ | ❌ |
| Create Staff Login | `POST /workflows/overseas/agent/team/staff`, `POST …/staff/{id}/reset` | ✅ | ❌ |
| Deactivate Staff | `POST …/staff/{id}/deactivate`, `POST …/staff/{id}/reactivate` | ✅ | ❌ |
| Staff Performance | — | N/A | N/A |
| Reports | `GET /portal/overseas/agent/reports` | ✅ full | **T** (when on: today's staff report, no commission row) |
| Commission | `GET /workflows/overseas/agent/commissions`, `POST …/commissions/{id}/claim`, `GET /portal/overseas/agent/commissions` | ✅ | ❌ |
| CRM Settings | — | N/A | N/A |

The Master-team routes (`POST …/team/masters`, `POST …/team/masters/{id}/deactivate`) sit under Staff Management. They are ❌ for Staff,
as AGN-002 already does.

**"Add University" ❌ for Masters** is a deliberate departure from §6's ✅. The route belongs to the admin console and no agent has
ever had it (P3). It is tested as `403` for both member roles and recorded here so the gap is visible.

## 4. Approaches considered

**Storage.**
- **(A) chosen: two booleans on `agent_org_members`.**
  - Typed and one row per member.
  - Read with the membership `get_current_user` already eager-loads on every request, so no extra query and no cache.
- **(B) a JSON `permissions` column.** Untyped, needs its own validation, and nothing calls for more toggles (YAGNI).
- **(C) an `agent_member_permissions` table.** Normalised, but adds a join and relationship to every request for two flags.

**Authorization style.**
- **Chosen: an inline helper in `core/rbac.py` next to `is_agent_staff`.** This follows the owner's 2026-09-28 rule that new routes
  use the inline checks, not the unused `require_*` dependencies.
- A FastAPI `require_agent_permission()` dependency was rejected for consistency.

**Agent verification.**
- **Chosen: widen the existing `PATCH /workflows/overseas/documents/{id}/verify` with an agent-only branch.**
  - The counselor and admin statements are unchanged.
  - One route per resource.
  - The frontend reuses the existing review panel.
- A separate `/agent/documents/{id}/review` route was rejected. It would duplicate the notification and audit code, and two routes
  could disagree on the same document.

**UI.** Generalise `CounselorDocumentReviewPanel` with optional props, defaults unchanged, rather than writing a second review panel.

## 5. Data model — migration `0048_agent_staff_permissions` (additive)

`agent_org_members` gains:

| Column | Type | Default |
|---|---|---|
| `can_verify_documents` | `BOOLEAN NOT NULL` | `server_default false` |
| `can_view_reports` | `BOOLEAN NOT NULL` | `server_default false` |

- **Upgrade:** add both columns. No backfill is needed; every existing row reads `false`.
- **Downgrade:** drop both columns.
- No constraint, index or data rewrite.
- Every existing member is kept.
- **Visible effect on upgrade:** existing staff lose the Reports page until a Master switches it on (P1). This is intended, and the
  RTM records it.
- On Master rows the columns are stored but never read (§6).
- The model docstring states that the columns apply to staff only.
- `down_revision = "0047_agent_org_staff"`. The single-head tests (`test_agn_001_schema.py:13`, `test_agn_002_schema.py:24`) do not pin
  the head and stay green.

## 6. Authorization (`core/rbac.py`)

```python
STAFF_PERMISSIONS = {"verify_documents": "can_verify_documents", "reports": "can_view_reports"}

def agent_may(user, permission: str) -> bool:
    """AGN-003 (DEC-SCOPE-041 P1/P2): whether an agent may use an optional §6 row. Masters always may; staff follow their own
    toggle. Reads the membership get_current_user eager-loads, so a change applies on the next request."""

def agent_permissions(user) -> dict | None:
    """{"verify_documents": bool, "reports": bool} for an agent member (Masters: both True); None otherwise."""
```

- An unknown permission name raises `KeyError`, a programming error that is never reached from user input.
- **Call sites:**
  - `api/portal.py` section check. After the existing `{team, commissions}` rule:
    `if section == "reports" and not agent_may(user, "reports")` → `403 "Your agency Master hasn't given you access to reports"`.
  - The agent branch of `verify_document` (§7).
- `services/portal.py` `_agent` is unchanged. A staff member with Reports on sees today's staff report (no commission row).

**Why no caching.** `get_current_user` (`api/deps.py:41-58`) re-selects the user with `agent_membership → org` on every request.
The flags are read there. Nothing is copied into the JWT, so there is no session bump and no stale window.

## 7. Agent document review — `PATCH /workflows/overseas/documents/{id}/verify`

`_require` gains `"agent"`: `{"counselor", "overseas_admin", "agent"}`. **Every statement for counselor and admin is unchanged.** A new
`if user.role == "agent":` block runs first, then reaches the same notify, audit and commit tail.

1. **Toggle.** Staff without Verify → `403 "Your agency Master hasn't given you permission to verify documents"`. A refused role gets
   `403` before any validation, which is the project's rule.
2. **Decision validation.** `payload.get("verification_status")` must be one of `verified|rejected|changes_required` → else `422`
   `"Choose verified, rejected or changes required"`. This applies to agents only; the counselor and admin path keeps today's
   behaviour.
3. **Outcome (P6).** Staff with any decision other than `verified` → `403 "Only an agency Master can reject documents or request changes"`.
   Steps 1–3 come before the document is read, so a refused caller learns nothing about whether the document exists.
4. **Row lock.** `select(StudentDocument).where(id).with_for_update()` → `404 "Document not found"`.
5. **Scope (agency).**
   - Attached to an application: `_assigned_application` (agency members' referrals).
   - Not attached: an `AgentStudent` link with `agent_id IN org_member_ids(user)` must exist.
   - Otherwise → `403 "Document is outside your assigned scope"`.
   - Today's route has no agent branch for unattached documents, so this closes a gap before it opens.
6. **Pending only (P5).** `verification_status != "pending"` → `409 "This document has already been reviewed"`.
7. **Tail (existing).**
   - Set the status, `verified_by_id` and `reviewer_notes`.
   - Notify the student ("Document reviewed").
   - Write the `document.verify` audit row with the payload.
   - Commit.

**Concurrency.**
- The row lock serialises two agents deciding the same document. The second sees a non-pending status → `409`.
- A counselor acting at the same moment is not locked. Either the counselor commits first, and the agent then sees non-pending →
  `409`; or the agent commits first, and the counselor's later decision overwrites it, which P5 allows.

**Transaction boundary.** The whole decision, its notification row and its audit row commit together, or nothing does (unchanged).

## 8. Toggle API (`api/agent_team.py`, `services/agent_orgs.py`, `schemas.py`)

`PUT /workflows/overseas/agent/team/staff/{member_id}/permissions`

| | |
|---|---|
| Body | `AgentStaffPermissions {verify_documents: StrictBool, reports: StrictBool}`, both required, `extra="forbid"`. Anything else → `422`. |
| Caller | `_staff_org` → `_require_master` (Staff `403 "Only an agency Master can manage the team"`; pending/suspended org `403`) + organisation row lock + active re-check |
| Target | `_staff_member` → `404 "Staff member not found"` for another agency's member, a Master's id or an unknown id |
| Effect | `set_staff_permissions(db, org, member_id, actor, verify_documents=, reports=)`: sets both columns and writes `AuditLog(action="agent_org.staff_permissions", entity_type="agent_org", entity_id=org.id, outcome="updated", metadata={member_id, code, verify_documents, reports})`. No commit inside; `_commit_staff_change(..., "agent_org_staff_permissions_updated", ...)` commits and logs ids/codes only. |
| Response | `200 {"member": <staff shape>}` |

- `PUT` replaces the whole permission set (idempotent). A repeat with the same values still writes an audit row.
- **Allowed on deactivated staff (P8).** No throttle, because no email is sent.
- **Race:** two Masters saving at once are serialised by the organisation lock; last write wins, and both are audited.

**Additive response fields** (existing fields unchanged):
- The staff member shape (`_staff_out`, also used by list, create, edit, deactivate, reactivate and reset) gains
  `"permissions": {"verify_documents": bool, "reports": bool}`.
- `UserOut.agent_permissions: dict | None`, set by `GET /auth/me` only, like `agent_member_role`. Masters get both `true`, staff get
  their toggles, non-agents get `null`.

## 9. Frontend (`apps/web`)

- **`lib/types.ts`:** `User.agent_permissions?: { verify_documents: boolean; reports: boolean } | null`.
- **`lib/agentStaff.ts`:** `StaffMember.permissions`.
- **`lib/navigation.ts`:** `agentNavFor(nav, memberRole, permissions?)`.
  - Staff: hide Team and Commissions as before, and also Reports unless `permissions?.reports`.
  - Masters and null are unchanged.
  - The optional third argument keeps existing callers compiling.
- **`components/PortalPage.tsx`:** passes `user.agent_permissions`. A typed `/overseas/agent/reports` URL still renders, and the
  server's `403` shows `AccessUnavailable` with "Go to your dashboard" (existing behaviour).
- **`components/CounselorDocumentReviewPanel.tsx`:** optional props, with defaults that reproduce today's counselor panel exactly:
  - `queueUrl` (default `/api/v1/portal/overseas/counselor/documents`)
  - `decisions` (default all three)
  - `pendingOnly` (default `false`)
  - **New load-error state:** a non-OK or failed load shows "Could not load documents. Refresh the page to try again." instead of the
    misleading "No documents…". This applies to counselors too; it is a deliberate small fix.
  - With `pendingOnly`, "Review" shows only on `pending` rows; decided rows show their status only.
- **`components/WorkflowPanel.tsx`:** on `section === "documents"` for `role === "agent"` with `agent_permissions?.verify_documents`,
  render the panel with:
  - `queueUrl="/api/v1/portal/overseas/agent/documents"`
  - `pendingOnly`
  - `decisions = staff ? ["verified"] : all three`
  - The upload form stays as it is.
- **`components/AgentStaffRow.tsx`:** a new mode `"permissions"` opened by a **Permissions** button, shown for active and
  deactivated members.
  - A form with two checkboxes ("Verify documents", "View reports"), pre-set from `member.permissions`.
  - Save sends `PUT …/permissions` through `sendJson`, with "Saving…" and buttons disabled while busy, and a double-submit guard
    (`inFlight`).
  - Cancel and Escape close the form; focus returns to the Permissions button.
  - Success announces `"<CODE> permissions saved."`. Errors appear in the always-mounted status region via `staffFailure`.
  - The row shows a one-line summary: "Student journey only", or "Can verify documents", "Can view reports" (joined with " · ").
- **`components/AgentStaffPanel.tsx`:** help text becomes "Staff work on your agency's students and applications. Only Masters see the
  team and commissions. Use Permissions to let a staff member verify documents or view reports."

**Loading, empty and error states:**
- The staff list keeps its existing loading, empty and error handling.
- The review panel has loading ("Loading your review queue…"), empty ("No documents are awaiting your review yet."), the new load
  error, and per-row action errors (server `detail`: `403`/`409`/`422` text).
- A toggle switched off while a staff member has the page open: their next click gets the server's `403` message in that row.

## 10. Security review

- **Privilege escalation.**
  - Every permission is decided on the server from the database row per request.
  - The UI only hides links.
  - Staff can never reach `PUT …/permissions` (`_require_master`).
  - Strict booleans and `extra="forbid"` block payload smuggling.
- **Tenancy.**
  - Toggles: `_staff_member` filters by the caller's `org_id` and `role='staff'`, so another agency's member or a Master id → `404`
    (no disclosure).
  - Verification: scoped through `_assigned_application` / `org_member_ids`.
- **Existence disclosure.** Staff permission refusals happen before the document read.
- **Integrity of the counselor review.** Agents act only on `pending` (P5) under a row lock.
- **Audit.** Every toggle change and every agent decision is audited in the same transaction. Logs carry ids and codes only, never
  email or notes.
- **Known limitations (unchanged, recorded):**
  - `/files/download` presigns any key.
  - Notifications, support and communications skip the agency gate.
  - Admin `PATCH /users` (AGN-002 E4).

## 11. Acceptance criteria → tests (written before the code)

| AC | Statement | Tests |
|---|---|---|
| AGN-003-AC01 | Every ❌ cell (§3) returns `403` for Staff with both toggles off | `test_agn_003_matrix.py::test_staff_refused[...]` (parametrised over every ❌ route) |
| AGN-003-AC02 | Every ✅ cell succeeds for Staff and for Master; Masters also succeed on Verify, Reject and Reports | `test_agn_003_matrix.py::test_staff_allowed[...]`, `::test_master_allowed[...]` |
| AGN-003-AC03 | Reports: Staff off → `403`, on → `200` (no commission row); Masters always `200` | `test_agn_003_permissions.py` |
| AGN-003-AC04 | Verify: Staff off → `403`; on + `verified` → `200`; on + `rejected`/`changes_required` → `403` | `test_agn_003_verify.py` |
| AGN-003-AC05 | A toggle change applies on the staff member's next request in the same session (off→403, on→200, off→403 with one cookie jar) | `test_agn_003_permissions.py::test_toggle_applies_on_next_request` |
| AGN-003-AC06 | Only a Master of the staff member's agency sets toggles; another agency or a Master id → `404`; Staff → `403`; bad body → `422`; deactivated staff allowed; audited | `test_agn_003_permissions.py` |
| AGN-003-AC07 | Agents decide only `pending` documents in agency scope: non-pending `409`, out of scope `403`, unknown `404`, bad decision `422`; unattached document via `AgentStudent` works; a counselor can still overwrite an agent decision; student notified; audit row | `test_agn_003_verify.py` |
| AGN-003-AC08 | `/auth/me` returns `agent_permissions` (Master both true, staff toggles, non-agent `null`); the staff shape returns `permissions` | `test_agn_003_permissions.py` |
| AGN-003-AC09 | Migration `0048` follows `0047`, single head, defaults `false`, existing members preserved | `test_agn_003_schema.py` |

**Existing tests changed deliberately (behaviour change P1, not to make a test pass):**
- `test_agn_002_staff_access.py::test_staff_dashboard_and_reports_leave_out_commission_figures` and
  `test_agn_002_qa_messages.py::test_staff_pages_never_mention_commissions[reports]` create the staff member with Reports **on**. Their
  intent ("no commission figures") is kept.
- `agn002_helpers.mk_staff` gains `can_verify_documents=False, can_view_reports=False`.

**Frontend unit:**
- `navigation.test.ts`: staff default hides Reports; Reports toggle shows it; Masters unchanged.
- `AgentStaffRow.test.tsx`: Permissions mode (pre-set, save body, Escape, focus, error, button set per status).
- A new `CounselorDocumentReviewPanel.test.tsx`: counselor defaults first (locks today's behaviour before the change), load error, agent
  `pendingOnly`, staff decisions.
- `WorkflowPanel` agent documents gating.
- `AgentStaffPanel.test.tsx`: help text.

**Playwright** `agn-003-staff-permissions.spec.ts`, reusing the `agn-002` helpers:
1. Staff see no Reports link, and `/reports` shows the access message.
2. The Master opens Permissions and turns both on.
3. Staff reload: Reports visible, the Documents review offers "Verified" only.
4. The Master turns both off; the staff member's next load shows the access message.

**Lite regression set (per `test-regression-cadence`):**
- `test_agn_00*`
- `test_agt_00*`
- `test_ovs_005_documents.py`
- `test_enh_031_*`
- The web unit tests above
- `agn-002` and `agn-003` Playwright

## 12. Regression risks and mitigations

| Risk | Mitigation |
|---|---|
| Staff lose Reports on upgrade | Intended (P1); recorded in DEC-SCOPE-041, RTM and release notes |
| Counselor/admin verify path changed by accident | Agent-only branch; counselor/admin statements untouched; `test_ovs_005_documents.py` plus a counselor-overwrite test |
| Shared review panel changes the counselor UI | Defaults reproduce today's panel; tests for counselor defaults written first |
| Every agent route slowed or broken | No new query per request (the flags ride on the already-loaded membership); `test_agt_00*`, `test_enh_031_*` in the lite set |
| Nav regressions | `navigation.test.ts`, `agn-002-staff.spec.ts` unchanged and green |
| Staff shape consumers | Additive field only; `AgentStaffPanel` and `AgentStaffRow` tests |
| Migration on existing data | Additive columns with server default; schema test on a database with members |

## 13. Documentation to update with the code

- `PRODUCT_DECISION_REGISTER.md`: `DEC-SCOPE-041`, plus a cross-reference on `DEC-SCOPE-038` D13 and `DEC-SCOPE-040` S1.
- `CONFLICT_MATRIX.md` `C-10` (EVID-015 row).
- `ENHANCEMENT_BACKLOG.md` (Revision 8, table row, §AGN-003, decision table, Appendix B row).
- `RBAC_MATRIX.md` §2.8 (AGN-003 block, the matrix above).
- `API_CONTRACT.md` §8 (the PUT, the verify-route agent addendum, `agent_permissions`, the staff shape).
- `DATA_MODEL.md` §6.8c.
- `SCREEN_CATALOG.md` SCR-AGT-005 (documents review) and SCR-AGT-007 (Permissions).
- `ROLE_NAVIGATION.md` (agent staff Reports).
- `RTM.md` (AGN-003 row).
