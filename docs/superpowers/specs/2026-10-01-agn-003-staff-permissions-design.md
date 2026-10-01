# AGN-003 — Agent Staff Permissions (Master vs Staff matrix): Design

**Status:** draft for owner review (2026-10-01). **Branch:** `feature/agn-003-staff-permissions` (from `origin/main` 1a0177c).
**Decision:** `DEC-SCOPE-044` (P1–P9). **Backlog:** `ENHANCEMENT_BACKLOG.md` §AGN-003 (AGN-003-AC01…AC09).
**Builds on:** `AGN-001` (`DEC-SCOPE-038`, migration `0046_agent_orgs`) and `AGN-002` (`DEC-SCOPE-040`, migration
`0047_agent_org_staff`, spec `2026-09-30-agn-002-staff-logins-design.md`).
**Evidence:** `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §2 "Set permissions", §3 "Permission Level",
§4 "Staff Login – Student Journey Only", §6 "Master vs Staff Permissions". The approval is the owner's, not the document's.
**Reviewed with:** api-and-interface-design, frontend-ui-engineering, security-and-hardening (in-session, 2026-10-01; findings
folded into §6–§11, summary in §14).

## 1. Intent

Staff are limited to the student journey with no admin modules, per `EVID-015` §6. Two §6 rows are optional: **Verify Documents**
(⚠️ Optional) and **Reports** (❌/Limited). A Master switches them on or off **per staff member**. Masters are never limited.

**Owner's acceptance criteria (in-session, 2026-10-01):**
- Every ❌ cell in §6 returns `403` for Staff, with a test.
- Every ✅ cell succeeds.
- The toggles flip the two optional rows.
- A toggle change applies on the next request.

**Owner's answers (in-session 2026-10-01, `EXPLICIT_APPROVAL`) — recorded as `DEC-SCOPE-044`:**
- **P1 — Toggles.** Verify Documents and Reports are the two optional rows. Both are **off by default** for Staff.
- **P2 — Granularity.** Toggles are stored **per staff member**, set by a Master from the staff row ("Set permissions").
- **P3 — Reach.** The matrix is enforced on routes that exist today. Rows with no capability for anyone are recorded **N/A**
  (§3) and stay parked. The one new capability is agent document verification, so that the Verify toggle has something to switch.
- **P4 — Student scope.** Staff keep agency-wide students and applications (`DEC-SCOPE-040` S1). Assignment/ownership (§7 of
  the source) stays parked under `C-10`.
  *(Superseded 2026-10-01 when `main` was merged: the owner adopted `DEC-SCOPE-042` G4 (`AGN-004`) for AGN-003 -- staff reach only their assigned students, their applications and documents, including the agent document review (attached or not).)*
- **P5 — Agent review only on pending documents.** An agent (Master, or Staff with Verify) may decide only a document whose
  `verification_status` is `pending`. A counselor's or Overseas Admin's decision is never overwritten by an agent. They can still
  re-review anything an agent decided.
- **P6 — Staff outcome.** Staff with Verify may record `verified` only. `rejected` and `changes_required` → `403`. Masters may
  record all three.

**Assumptions stated by design (owner may correct):**
- **P7** "Permission Level" is not a create-form field. New staff start with both toggles off; the Master sets them afterwards.
- **P8** Toggles can be set on a deactivated staff member and survive reactivation. Setting them sends no email, so there is no
  throttle. Every change is audited.
- **P9** Staff with Verify may verify a document they uploaded themselves (no maker-checker in §6). The decision is attributed and
  counselors and Overseas Admins can still re-review (§10).

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
| View Students | `GET /workflows/overseas/agent/students`, `GET /portal/overseas/agent/students`, `GET /lookups/overseas-students` | ✅ agency | ✅ assigned only (`DEC-SCOPE-042` G4) |
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

## 5. Data model — migration `0052_agent_staff_permissions` (additive)

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
- `down_revision = "0050_notification_channels"` (re-chained when `main` was merged, 2026-10-01; drafted after `0047_agent_org_staff`). The single-head tests (`test_agn_001_schema.py:13`, `test_agn_002_schema.py:24`) do not pin
  the head and stay green.

## 6. Authorization (`core/rbac.py`)

```python
STAFF_PERMISSIONS = ("can_verify_documents", "can_view_reports")  # the column names are also the API keys (§8)

def agent_may(user, permission: str) -> bool:
    """AGN-003 (DEC-SCOPE-044 P1/P2): whether an agent may use an optional §6 row. Masters always may; staff follow their own
    toggle. Reads the membership get_current_user eager-loads, so a change applies on the next request."""

def agent_permissions(user) -> dict | None:
    """{"can_verify_documents": bool, "can_view_reports": bool} for an agent member (Masters: both True); None otherwise."""
```

- An unknown permission name is a programming error (`assert permission in STAFF_PERMISSIONS`). It is never reached from user input.
- **Call sites:**
  - `api/portal.py` section check. After the existing `{team, commissions}` rule:
    `if section == "reports" and not agent_may(user, "can_view_reports")` → `403 "Your agency Master hasn't given you access to reports"`.
  - The agent branch of `verify_document` (§7).
- `services/portal.py` `_agent` is unchanged. A staff member with Reports on sees today's staff report (no commission row).

**Why no caching.** `get_current_user` (`api/deps.py:41-58`) re-selects the user with `agent_membership → org` on every request.
The flags are read there. Nothing is copied into the JWT, so there is no session bump and no stale window.

## 7. Agent document review — `PATCH /workflows/overseas/documents/{id}/verify`

`_require` gains `"agent"`: `{"counselor", "overseas_admin", "agent"}`. **Every statement for counselor and admin is unchanged.** A new
`if user.role == "agent":` block runs first, then reaches the same notify, audit and commit tail.

1. **Toggle.** Staff without Verify → `403 "Your agency Master hasn't given you permission to verify documents"`. A refused role gets
   `403` before any validation, which is the project's rule.
2. **Decision validation.** `AgentDocumentReview.model_validate(payload)`, a new schema in `schemas.py`:
   - `verification_status: Literal["verified", "rejected", "changes_required"]` (required)
   - `notes: str | None = Field(None, max_length=10000)`, the same cap as `OverseasApplicationAdvance.notes`
   - `model_config = {"extra": "forbid"}`

   A `ValidationError` is re-raised as FastAPI's `RequestValidationError`, so agents get the project's standard `422`
   `detail`-list shape. This applies to agents only. The route signature stays `payload: dict`, so the counselor and admin path keeps
   today's behaviour (default `verified`, unvalidated). Hardening that path is out of scope.
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
   - Write the `document.verify` audit row.
   - Commit.

   For agents the audit metadata is the **validated** model dump plus `{"member_role": "master"|"staff"}`, never the raw payload, so
   unknown client keys never reach the audit table. Counselor and admin rows are unchanged.

**Retry semantics.** The call is safe to retry. A repeat after success returns `409` and changes nothing, and the student is
notified once. No idempotency key is needed.

**Status codes for out-of-scope documents.** These keep the route's and `_assigned_application`'s existing `403` rather than `404`, so
one route never answers two ways. Document ids are random UUIDv4 and the AGN-001 application routes already behave this way. This is
recorded as an accepted limitation (§10).

**Concurrency.**
- The row lock serialises two agents deciding the same document. The second sees a non-pending status → `409`.
- A counselor acting at the same moment is not locked. Either the counselor commits first, and the agent then sees non-pending →
  `409`; or the agent commits first, and the counselor's later decision overwrites it, which P5 allows.

**Transaction boundary.** The whole decision, its notification row and its audit row commit together, or nothing does (unchanged).

## 8. Toggle API (`api/agent_team.py`, `services/agent_orgs.py`, `schemas.py`)

`PUT /workflows/overseas/agent/team/staff/{member_id}/permissions`

| | |
|---|---|
| Body | `AgentStaffPermissions {can_verify_documents: StrictBool, can_view_reports: StrictBool}`, both required, `extra="forbid"`. Anything else → `422` (standard shape). |
| Caller | `_staff_org` → `_require_master` (Staff `403 "Only an agency Master can manage the team"`; pending/suspended org `403`) + organisation row lock + active re-check |
| Target | `_staff_member` → `404 "Staff member not found"` for another agency's member, a Master's id or an unknown id |
| Effect | `set_staff_permissions(db, org, member_id, actor, can_verify_documents=, can_view_reports=)` sets both columns. **Only when a value changes** it writes `AuditLog(action="agent_org.staff_permissions", entity_type="agent_org", entity_id=org.id, outcome="updated", metadata={member_id, code, before: {…}, after: {…}})`. No commit inside; `_commit_staff_change(..., "agent_org_staff_permissions_updated", ...)` commits and logs ids/codes only. |
| Response | `200 {"member": <staff shape>}` |

- `PUT` replaces the whole permission set (idempotent). A repeat with the same values returns `200`, writes nothing and adds no audit
  row, so a repeated click cannot flood the audit table.
- **Allowed on deactivated staff (P8).** No throttle, because no email is sent and a no-op writes nothing.
- **Race:** two Masters saving at once are serialised by the organisation lock; last write wins, and each real change is audited with
  its before/after values.
- **Naming.** The keys are the column names (`can_*`), matching the codebase's existing boolean style (e.g. `can_edit_career_goal` in
  the 360 view) and the skill's is/has/can rule. The API uses snake_case, like every other EduSphere response.

**Additive response fields** (existing fields unchanged):
- The staff member shape (`_staff_out`, also used by list, create, edit, deactivate, reactivate and reset) gains
  `"permissions": {"can_verify_documents": bool, "can_view_reports": bool}`.
- `UserOut.agent_permissions: dict | None`, set by `GET /auth/me` only, like `agent_member_role`. These are **effective** permissions:
  Masters get both `true`, staff get their toggles, non-agents get `null`. This is documented in `API_CONTRACT.md`, because clients
  will depend on it (Hyrum's law).

## 9. Frontend (`apps/web`)

- **`lib/types.ts`:** `User.agent_permissions?: AgentPermissions | null`, with
  `type AgentPermissions = { can_verify_documents: boolean; can_view_reports: boolean }`.
- **`lib/agentStaff.ts`:** `StaffMember.permissions: AgentPermissions`.
- **`lib/navigation.ts`:** `agentNavFor(nav, memberRole, permissions?)`.
  - Staff: hide Team and Commissions as before, and also Reports unless `permissions?.can_view_reports`.
  - Masters and null are unchanged.
  - The optional third argument keeps existing callers compiling.
- **`components/PortalPage.tsx`:** passes `user.agent_permissions`. A typed `/overseas/agent/reports` URL still renders, and the
  server's `403` shows `AccessUnavailable` with "Go to your dashboard" (existing behaviour).
- **`components/CounselorDocumentReviewPanel.tsx`:** optional props, with defaults that reproduce today's counselor panel exactly:
  - `queueUrl` (default `/api/v1/portal/overseas/counselor/documents`)
  - `decisions` (default all three)
  - `pendingOnly` (default `false`)
  - `emptyText` (default "No documents are awaiting your review yet."; agent: "No documents have been uploaded for your agency's
    applications yet.")
  - **New load-error state:** a non-OK or failed load shows "Couldn't load documents." with a **Try again** button that re-runs the load.
    It replaces the misleading "No documents…" and is announced through `role="alert"`. This applies to counselors too; it is a
    deliberate small fix.
  - The loading text gets `role="status"`, so screen readers hear it.
  - With `pendingOnly`, **Review** shows only on `pending` rows; decided rows show their status badge as text.
  - **One decision only** (staff): no single-option `<select>`. The form shows the notes field and one **Mark verified** submit button,
    sending `verification_status: "verified"`.
  - After a submit, focus moves to the row's status message, so keyboard users are not dropped to the top of the page when the row
    re-renders.
- **`components/WorkflowPanel.tsx`:** on `section === "documents"` for `role === "agent"` with `agent_permissions?.can_verify_documents`,
  render the panel with:
  - `queueUrl="/api/v1/portal/overseas/agent/documents"`
  - `pendingOnly`
  - `emptyText` as above
  - `decisions = staff ? ["verified"] : all three`
  - The upload form stays as it is.
- **New `components/AgentStaffPermissionsForm.tsx`** (about 60 lines). It is extracted so that `AgentStaffRow` (144 lines) stays well
  under 200 and the form is testable on its own.
  - A `<fieldset className="form-section">` with `<legend>What {full_name} can do</legend>`, reusing the existing ENH-025 style.
  - Two native checkboxes, each with a `<label>` and a hint linked by `aria-describedby`:
    - "Verify documents": "Mark pending documents as verified. Only Masters can reject or request changes."
    - "View reports": "See the agency's application summary."
  - The first checkbox has `autoFocus`; Escape cancels.
  - Save and Cancel use the row's existing `btn small` / `btn secondary small` and `flexWrap` gap 8 pattern, so the controls wrap on
    narrow screens.
- **`components/AgentStaffRow.tsx`:** a new mode `"permissions"` opened by a **Permissions** button (`aria-label="Permissions for
  {name}"`), shown for active and deactivated members.
  - It renders the form pre-set from `member.permissions`.
  - Save calls the row's existing `run()` with `method: "PUT"`, path `/permissions` and `focusNext: "permissions"`. This gives the
    "Saving…" state, disabled buttons, the `inFlight` double-submit guard, the status region and `staffFailure` errors that
    AGN-002's actions already have.
  - Success announces `"<CODE> permissions saved."`.
  - The row shows a text summary (not colour): "Student journey only", or "Can verify documents" / "Can view reports" joined with " · ".
  - The `Action.method` type widens to `"POST" | "PATCH" | "PUT"`.
- **`components/AgentStaffPanel.tsx`:** help text becomes "Staff work on your agency's students and applications. Only Masters see the
  team and commissions. Use Permissions to let a staff member verify documents or view reports."

**Loading, empty and error states:**
- The staff list keeps its existing loading, empty and error handling.
- The review panel has loading (`role="status"`), empty (`emptyText`), load error with Try again, and per-row action errors (server
  `detail`: `403`/`409`/`422` text).
- A toggle switched off while a staff member has the page open: their next click gets the server's `403` message in that row. The
  sidebar updates on their next navigation.

**Responsive, keyboard and perceived performance:**
- No new layout. Rows and forms reuse `flexWrap` and `.grid.two`, which collapses to one column at ≤640px.
- The nav is computed on the server in `PortalPage`, so Reports never flashes in and out.
- Every control is a native `button`, `input` or `select`.
- The existing `.action-grid` has no mobile breakpoint. That predates AGN-003 and is left unchanged; no unrelated redesign.

## 10. Security review (security-and-hardening, 2026-10-01)

**Trust boundaries.**
- `PUT …/permissions`: body and path id.
- `PATCH …/documents/{id}/verify`: body and path id.
- `GET /portal/overseas/agent/reports`.
- `/auth/me` output.

**Assets.**
- Document review decisions, which the student sees and which feed the counselor's workflow.
- Staff privileges.
- The audit trail.

| Check | Finding |
|---|---|
| **Authentication** | Unchanged: `get_current_user` cookie JWT + `session_version`. Deactivated staff get `401` before any AGN-003 check. |
| **Authorization** | Every decision is taken on the server from the database row on each request (§6); the UI only hides links. The portal Reports page and the verify route are refused server-side even when a URL is typed. |
| **Role escalation** | Staff cannot reach `PUT …/permissions` (`_require_master`) and so cannot change their own flags. A Master cannot set flags on another Master (`_staff_member` filters `role='staff'` → `404`). The body is a closed two-key schema, so no other privilege can be named. The flags never widen beyond §3: Verify gives `verified` only, and Reports gives today's commission-free staff report. |
| **IDOR** | Toggles: `member_id` is resolved only inside the caller's organisation (`404` otherwise, no disclosure). Documents: `_assigned_application` or the agency `AgentStudent` link. An out-of-scope document is `403` (accepted, §7). Ids are UUIDv4. |
| **Input validation** | `StrictBool`, `Literal` decisions, `notes` ≤ 10000, `extra="forbid"` on both new bodies. Path ids are `UUID`-typed (`422`). |
| **XSS** | `reviewer_notes`, names and statuses render as React text. No `dangerouslySetInnerHTML` is added. The agent queue shows the existing portal rows. |
| **CSRF** | Unchanged and sufficient. Cookies are `httpOnly` + `SameSite=lax` (`auth.py:90`) and CORS allows only `frontend_url` with credentials (`main.py:58`). The new endpoints are JSON `PUT`/`PATCH`, which browsers cannot send cross-site with cookies. |
| **SQL injection** | SQLAlchemy ORM only; no raw SQL. |
| **Token/session** | The flags are not put in the JWT, so there is no stale grant. Switching a toggle off takes effect on the next request with no session bump. |
| **Secret exposure** | None. No token or link is involved; `_deliver` is untouched. |
| **Sensitive logs** | Structured logs carry ids and codes only. Audit metadata holds the validated decision, the member role and the before/after flags. It never holds an email or the raw payload. Reviewer notes stay in the audit row exactly as the counselor path already stores them (database, not logs). |
| **Rate limiting** | `PUT` is not throttled: a no-op writes nothing and each real change is one row under the organisation lock. Agent verify cannot repeat because `pending` is single-use (`409`). No new email path. |
| **Audit** | Every real toggle change (`agent_org.staff_permissions`, before/after) and every agent decision (`document.verify`, with `member_role`) is audited in the same transaction as the change. |
| **Integrity of the counselor review** | Agents act only on `pending` (P5) under a row lock. Counselors and Overseas Admins can still re-review. |

**Self-verification (recorded, owner may change).** A staff member with Verify could mark verified a document they uploaded themselves.
§6 does not ask for maker-checker. The decision is attributed (`verified_by_id`, audit `member_role`) and the counselor or Overseas
Admin can still re-review, so this is accepted as **P9** unless the owner decides otherwise.

**Known limitations (unchanged, recorded, out of AGN-003 scope):**
- `/files/download` presigns any key.
- Notifications, support and communications skip the agency gate.
- Admin `PATCH /users` (AGN-002 E4).
- The counselor/admin verify body is still an unvalidated `dict`.

## 11. Acceptance criteria → tests (written before the code)

| AC | Statement | Tests |
|---|---|---|
| AGN-003-AC01 | Every ❌ cell (§3) returns `403` for Staff with both toggles off | `test_agn_003_matrix.py::test_staff_refused[...]` (parametrised over every ❌ route) |
| AGN-003-AC02 | Every ✅ cell succeeds for Staff and for Master; Masters also succeed on Verify, Reject and Reports | `test_agn_003_matrix.py::test_staff_allowed[...]`, `::test_master_allowed[...]` |
| AGN-003-AC03 | Reports: Staff off → `403`, on → `200` (no commission row); Masters always `200` | `test_agn_003_permissions.py` |
| AGN-003-AC04 | Verify: Staff off → `403`; on + `verified` → `200`; on + `rejected`/`changes_required` → `403` | `test_agn_003_verify.py` |
| AGN-003-AC05 | A toggle change applies on the staff member's next request in the same session (off→403, on→200, off→403 with one cookie jar) | `test_agn_003_permissions.py::test_toggle_applies_on_next_request` |
| AGN-003-AC06 | Only a Master of the staff member's agency sets toggles; another agency or a Master id → `404`; Staff → `403`; bad body (missing key, extra key, `"true"` string) → `422`; deactivated staff allowed; a real change writes one audit row with before/after; a no-op writes none | `test_agn_003_permissions.py` |
| AGN-003-AC07 | Agents decide only `pending` documents in agency scope: non-pending `409`, out of scope `403`, unknown `404`, bad decision `422`; unattached document via `AgentStudent` works; a counselor can still overwrite an agent decision; student notified; audit row | `test_agn_003_verify.py` |
| AGN-003-AC08 | `/auth/me` returns `agent_permissions` (Master both true, staff toggles, non-agent `null`); the staff shape returns `permissions` | `test_agn_003_permissions.py` |
| AGN-003-AC09 | Migration `0052` follows ENH-028 `0051_school_bulk_uploads` (re-chained on merging `main` twice, 2026-10-01), single head, defaults `false`, existing members preserved | `test_agn_003_schema.py` |

**Existing tests changed deliberately (behaviour change P1, not to make a test pass):**
- `test_agn_002_staff_access.py::test_staff_dashboard_and_reports_leave_out_commission_figures` and
  `test_agn_002_qa_messages.py::test_staff_pages_never_mention_commissions[reports]` create the staff member with Reports **on**. Their
  intent ("no commission figures") is kept.
- `agn002_helpers.mk_staff` gains `can_verify_documents=False, can_view_reports=False`.

**Frontend unit:**
- `navigation.test.ts`: staff default hides Reports; Reports toggle shows it; Masters unchanged.
- `AgentStaffPermissionsForm.test.tsx`: labels and hints (`aria-describedby`), pre-set values, Escape cancels, first-checkbox focus.
- `AgentStaffRow.test.tsx`: Permissions button per status, `PUT` body `{can_verify_documents, can_view_reports}`, "Saving…",
  focus returns to Permissions, server error in the status region, summary text. The existing button-set assertion (`:162`) is
  extended deliberately for the new button.
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
| Staff lose Reports on upgrade | Intended (P1); recorded in DEC-SCOPE-044, RTM and release notes |
| Counselor/admin verify path changed by accident | Agent-only branch; counselor/admin statements untouched; `test_ovs_005_documents.py` plus a counselor-overwrite test |
| Shared review panel changes the counselor UI | Defaults reproduce today's panel; tests for counselor defaults written first |
| Every agent route slowed or broken | No new query per request (the flags ride on the already-loaded membership); `test_agt_00*`, `test_enh_031_*` in the lite set |
| Nav regressions | `navigation.test.ts`, `agn-002-staff.spec.ts` unchanged and green |
| Staff shape consumers | Additive field only; `AgentStaffPanel` and `AgentStaffRow` tests |
| Migration on existing data | Additive columns with server default; schema test on a database with members |

## 13. Documentation to update with the code

- `PRODUCT_DECISION_REGISTER.md`: `DEC-SCOPE-044`, plus a cross-reference on `DEC-SCOPE-038` D13 and `DEC-SCOPE-040` S1.
- `CONFLICT_MATRIX.md` `C-10` (EVID-015 row).
- `ENHANCEMENT_BACKLOG.md` (Revision 8, table row, §AGN-003, decision table, Appendix B row).
- `RBAC_MATRIX.md` §2.8 (AGN-003 block, the matrix above).
- `API_CONTRACT.md` §8 (the PUT, the verify-route agent addendum, `agent_permissions`, the staff shape).
- `DATA_MODEL.md` §6.8c.
- `SCREEN_CATALOG.md` SCR-AGT-005 (documents review) and SCR-AGT-007 (Permissions).
- `ROLE_NAVIGATION.md` (agent staff Reports).
- `RTM.md` (AGN-003 row).

## 14. Review log (2026-10-01)

**api-and-interface-design**
- Permission keys renamed to the `can_*` column names (`can_verify_documents`, `can_view_reports`) in the body, the staff shape and
  `/auth/me`. This matches `can_edit_career_goal` and the boolean naming rule.
- The agent review body is a typed `AgentDocumentReview` (Literal decisions, notes cap, `extra="forbid"`). It returns the standard
  `422` shape. The counselor path is untouched.
- `PUT` is a full replacement and idempotent. A no-op writes no audit row, and a real change records before/after.
- Agent verify retry semantics are documented (a repeat gets `409` with no second effect). The out-of-scope `403` is kept for
  consistency with the route.
- All new fields are additive; no existing field changes. `agent_permissions` is documented as effective permissions.

**frontend-ui-engineering**
- `AgentStaffPermissionsForm` is extracted, keeping `AgentStaffRow` under 200 lines. It reuses `fieldset.form-section` with a legend
  and has hints linked by `aria-describedby`.
- Staff get one **Mark verified** button instead of a single-option select.
- The review panel gets a load error with **Try again** (`role="alert"`), loading `role="status"`, an agent `emptyText`, and focus on
  the row message after a submit.
- Responsive behaviour reuses existing wrap and grid classes. `.action-grid`'s missing breakpoint is noted and left as is (unrelated).

**security-and-hardening**
- §10 rewritten as a checklist covering authentication, authorization, escalation, IDOR, validation, XSS, CSRF, SQL injection,
  session, secrets, logs, rate limits and audit.
- Audit metadata for agents uses the validated dump plus `member_role`, never the raw payload.
- Self-verification is recorded as P9.
