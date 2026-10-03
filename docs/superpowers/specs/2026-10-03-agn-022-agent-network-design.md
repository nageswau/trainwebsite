# AGN-022 — Overseas Admin agent network oversight — design

NO-ASSUMPTION MODE. Status: **design, awaiting the owner's written-spec review.** No code written. Branch
`feature/agn-022-agent-network` (from `main` @ `3bde8796`). Decision: `DEC-SCOPE-063` (this spec §2).

---

## 1. Requirement and acceptance

- **Requirement (owner, in-session 2026-10-03, quoting `EVID-015` "Best approach" / §9 and `AGENT_CRM_BACKLOG.md` ang-022):**
  "Edusphere's central admin can see the overall agent network and student/application data according to the permissions you
  define."
- **Owner's acceptance criteria:** counts match fixtures; suspend blocks the org immediately (ang-001 AC4); non-admin → 403.
- **Source status:** `EVID-015` and the backlog are `DERIVED_BLUEPRINT`. The backlog's "D17 — read-all, limited actions"
  (`AGENT_CRM_BACKLOG.md:164`) is cited there as `DEC-SCOPE-035`, which on `main` is ENH-027 (known mis-citation). The owner's
  answers in §2 are the authority for this feature.

## 2. Decisions (`DEC-SCOPE-063`, answered by the owner 2026-10-03)

| ID | Decision |
|---|---|
| N1 | **Drill depth = counts + lists.** Org list with counts; an org detail page with that agency's students and applications as read-only lists. No per-student record pages; no email, phone or date of birth in admin rows. |
| N2 | **Read audit = one `AuditLog` row per drill-down list request**, written before the data is returned (fail closed). List and summary are not audited (no student records in them). |
| N3 | **super_admin = read-only in the UI.** Suspend/Reinstate buttons are shown to `overseas_admin` only (as the AGN-011 deposits page). The backend action route keeps admitting super_admin (no contract change). |
| N4 | **Money = the existing buckets.** Commissions: AGN-018's Claimable (`estimated`+`eligible`) per currency, Claims count (`claimed`), Paid revenue per currency; never summed across currencies. Deposits (INR): count and amount collected (`paid`+`remitted`+`refunded`), amount remitted (`remitted`), amount refunded (`refund_amount` of `refunded`); not netted; `pending`/`not_required` excluded. Shown on the org detail only. |
| N5 | **Approach A.** Extend the shipped `GET /overseas-admin/agent-orgs` additively; add `GET /agent-orgs/{id}`, `/{id}/students`, `/{id}/applications`; reuse `POST /agent-orgs/{id}/suspend|reinstate` unchanged. The backlog's `/agent-organizations` + `reactivate` naming is **superseded** by the shipped AGN-001 routes. |
| N6 | **Admin powers stay limited (D17):** no admin edits to agent students, applications or staff. Approve/reject stay on the Agent Approvals page. |

## 3. Existing behaviour (verified in code, `main` @ `3bde8796`)

- `apps/api/app/api/admin.py` `agents_router` (prefix `/overseas-admin`): `list_agent_orgs` `:1140` (status/q filter, `limit` 25
  ≤100, `offset`, newest first, `{items,total,limit,offset}`, items `{id,name,prefix,status,created_at,masters}`);
  `act_on_agent_org` `:1172` → `services/agent_orgs.transition_org` `:154` (row lock, TRANSITIONS, 409, audit
  `agent_org.{action}`); gate `_require_overseas_admin` `:1135` (`overseas_admin`, `super_admin`).
- Suspension enforcement: `deps.get_current_user` (`:41`) eager-loads `agent_membership.org` per request;
  `rbac.agent_denial_reason` (`:83`) → `workflows._require` (`:119`) 403; agency writes re-check under
  `agent_orgs.lock_active_org` (`:129`). Proven by `test_agn_001_registration_and_gate.py:117` (AC04).
- Org linkage: `agent_org_members(org_id, user_id unique, role, status)`. Students, applications and commissions link by
  `agent_id ∈ {member user ids of the org}`; applications also `school_student_id IS NULL` (`with_owner`, A12); deposits via
  `application_deposits.application_id` → application (`agent_deposits.admin_rows` `:156`).
- Count definitions to reuse: `services/agent_dashboard.py` — students = `AgentStudent.status == "active"`; applications =
  `status != WITHDRAWN`; enrollments = `status == "enrolled"`; `CLAIMABLE`; `commission_summary` buckets. All its functions
  are user-scoped (they take a `User`), so they are not called directly.
- Frontend: `AgentApprovalPanel.tsx` on `/overseas/admin/agents` (heading "Agent Approvals", `.action-card`), used by five e2e
  flows and `tests/e2e/helpers/agency.ts`. Standalone admin page template: `app/overseas/admin/agent-deposits/page.tsx`.
  Nav: `lib/navigation.ts:103` `PORTAL_NAV["overseas/admin"]`.
- graphify: the committed graph predates AGN-001; a fresh AST graph was built in a scratch directory for this analysis.

## 4. Definitions

| Figure | Definition (per org `O`; `M(O)` = user ids of all members of `O`, any member status) |
|---|---|
| `staff_count` | `agent_org_members` with `org_id = O`, `role = 'staff'`, `status = 'active'` |
| `students` | `agent_students` with `agent_id ∈ M(O)`, `status = 'active'` (login or not) |
| `applications` | `overseas_applications` with `agent_id ∈ M(O)`, `school_student_id IS NULL`, `status != 'withdrawn'` |
| `enrollments` | same base as `applications`, `status = 'enrolled'` |
| `commission` | `agent_commissions` with `agent_id ∈ M(O)`, N4 buckets |
| `deposits` | `application_deposits` joined to applications with `agent_id ∈ M(O)` and `school_student_id IS NULL`, N4 figures |

These equal what the same agency's Master sees on its AGN-018 dashboard for students, applications, enrollments and commission.

## 5. Backend

### 5.1 Service — `apps/api/app/services/agent_network.py` (new)

Read-only: no writes, locks or commits. Every function takes org ids, never a user. Imports `WITHDRAWN`, `CLAIMABLE`; no
definition is restated.

- `org_counts(db, org_ids) -> dict[UUID, dict]` — three grouped statements (active staff; active students; applications and
  enrollments with `count(case …)` in one pass), each joined `AgentOrgMember.user_id == <entity>.agent_id` and grouped by
  `AgentOrgMember.org_id`. Every requested org gets zeros by default. Empty `org_ids` → `{}` with no query.
- `org_money(db, org_id) -> {"commission": {...}, "deposits": {...}}` — commission in the `commission_summary` shape
  (`claimable: [{currency,count,amount}]`, `claims: int`, `revenue: [{currency,count,amount}]`); deposits
  `{currency:"INR", count, collected, remitted, refunded}` (amounts as numbers, 0 when none).
- `org_students(db, org_id, *, status, limit, offset) -> (rows, total)` — rows `{id, full_name, status, assigned_code,
  has_login, applications, created_at}`; `assigned_code` from `AgentOrgMember.code` via `assigned_member_id` (null when
  unassigned); `applications` = non-withdrawn applications linked by `agent_student_id` or by the linked login (the
  `staff_rows` join). Order `created_at desc, id desc`.
- `org_applications(db, org_id, *, status, limit, offset) -> (rows, total)` — rows `{id, student_name, university, country,
  status, enrollment_date, created_at, updated_at}`; `student_name` = `OWNER_NAME` (account name, else agency record's). Order
  `created_at desc, id desc`.

### 5.2 Routes — `apps/api/app/api/admin.py` `agents_router`

All call `_require_overseas_admin(user)` before any lookup.

| Route | Behaviour |
|---|---|
| `GET /overseas-admin/agent-orgs` | **Additive only:** each item gains `staff_count` and `counts: {students, applications, enrollments}` from `org_counts` for the page's org ids. Existing fields, params, ordering, paging, errors unchanged. |
| `GET /overseas-admin/agent-orgs/{org_id}` | 404 "Organisation not found" if absent. Returns `{id, name, prefix, status, created_at, status_changed_at, masters, staff: [{id, code, full_name, status}], staff_count, counts, commission, deposits, as_of}`. `masters` uses `org_masters` (same shape as the list). No member email for staff. |
| `GET /overseas-admin/agent-orgs/{org_id}/students` | `status: Literal["active","archived"] = "active"`, `limit` 25 (1–100), `offset ≥ 0`. 404 if org absent. `{items, total, limit, offset}`. Audits (5.3). |
| `GET /overseas-admin/agent-orgs/{org_id}/applications` | optional `status` (one of `OVERSEAS_APPLICATION_STAGES` + `withdrawn`, else 422), same paging, 404 if absent. Audits (5.3). |
| `POST /overseas-admin/agent-orgs/{org_id}/{action}` | **Unchanged.** |

Response models: the three new routes get Pydantic models in `schemas.py` (as AGN-018 G6). The existing list keeps returning a
dict (unchanged style); the two new keys are documented in `API_CONTRACT.md`.

Route order: the new `GET` paths do not collide with `POST /agent-orgs/{org_id}/{action}` (different method).

### 5.3 Read audit (N2)

After the rows and total are fetched: `db.add(AuditLog(user_id=user.id, action="agent_network.students_read" |
"agent_network.applications_read", entity_type="agent_org", entity_id=str(org_id), outcome="read", metadata_json={"status":
status, "limit": limit, "offset": offset, "returned": len(rows)}))`, then `await db.commit()`, then return. A failed audit
write raises → 500, no data returned (SEC-001 fail-closed; pattern `lookups.py:120`). A 403/404/422 writes no audit row.

### 5.4 Transactions, races, errors, performance

- List/summary: reads only, no commit. Drill-down: read, add audit, one commit.
- Suspend/reinstate: `transition_org` unchanged (row lock + status + audit + commit in one transaction). Concurrent admin
  actions serialise on `lock_org`; the loser gets the existing 409. Members are denied on their next request (per-request
  reload); an in-flight request completes.
- Counts are a few statements under READ COMMITTED; a concurrent write can shift one figure by one within a response. Accepted
  for an oversight screen; `as_of` is returned on the detail.
- Paging uses stable `created_at desc, id desc`.
- Errors: non-admin 403 (before lookup, no existence leak); unauthenticated 401; unknown org 404; malformed UUID / bad
  `status` / `limit` > 100 / `offset` < 0 → 422; audit failure 500; zero-student org → 200 with zeros/empty lists; orgs of
  every status are readable.
- Performance: list adds three grouped queries bounded by ≤100 org ids; detail adds three counts plus two money queries.
  Existing indexes: `agent_org_members.org_id`, `agent_students.agent_id`, `overseas_applications.agent_id`,
  `agent_commissions.agent_id`, `application_deposits.application_id` (unique). No new index.

## 6. Frontend

### 6.1 Pages (standalone, copied from `app/overseas/admin/agent-deposits/page.tsx`)

- `app/overseas/admin/agent-network/page.tsx` → `<AgentNetworkPanel />` inside `PortalShell` with
  `PORTAL_NAV["overseas/admin"]`; `ADMIN_ROLES = ["overseas_admin","super_admin"]`; `accessUnavailable` / `accessDenied`.
- `app/overseas/admin/agent-network/[orgId]/page.tsx` → `<AgentOrgDetailPanel orgId={orgId} canAct={user.role ===
  "overseas_admin"} />`.

### 6.2 `components/AgentNetworkPanel.tsx` (new, client)

Pattern of `AgentApprovalPanel` (URL-held tab/page/q, 20 per page, Previous/Next), but heading **"Agent network"** and no
`.action-card` class (keeps the e2e "Agent Approvals" locators unambiguous). Status tabs All (default) / Active / Suspended /
Pending / Rejected; search by agency, prefix, Master code/email (the existing `q`). Each row: name + prefix, status, Master
codes, staff, students, applications, enrollments, link "View" → `/overseas/admin/agent-network/{id}`. States: loading
(`role="status"` "Loading agencies…"), empty ("No agencies match."), error (server `detail` + Retry).

### 6.3 `components/AgentOrgDetailPanel.tsx` (new, client)

- Summary: status + last change date, counts, commission buckets per currency, deposit figures (`formatInr`), Masters, staff.
- Actions (only when `canAct`): Suspend (active) with inline confirm, Reinstate (suspended); focus returns to the button; 409 →
  show message and refetch; pending/rejected → link "Review in Agent Approvals" (`/overseas/admin/agents`).
- Tabs Students / Applications: each fetched only when opened (so audit rows reflect actual views), paged 20, own
  loading/empty ("No students yet" / "No applications yet")/error states; read-only, no edit controls.
- 404 → "Organisation not found" + link back to the network list.
- Types local to the components (as `AgentApprovalPanel`); reuse `lib/apiErrors` (`Page`, `isPage`, `detailMessage`,
  `sendJson`), `lib/formatDate`, `formatInr`, `useFocusAfterRender`.

### 6.4 Navigation

Append `{label: "Agent network", href: "/overseas/admin/agent-network"}` to `PORTAL_NAV["overseas/admin"]` after "Agent
deposits". Not added to `SUPER_ADMIN_NAV`. No existing entry moves.

## 7. Authorization and security

- Gate before lookup on all routes; read-only for admins on agent data (N6).
- PII minimisation: admin rows exclude email, phone, date of birth, notes, counseling, documents.
- Cross-org isolation: every query is bound to `M(O)` from `agent_org_members` for the path's `org_id`; tests seed a second
  agency and assert none of its rows or counts leak.
- Audit: drill-down reads (N2); suspend/reinstate audit unchanged (`agent_org.suspend|reinstate`).
- No change to agent-side routes, `_require`, `agent_denial_reason`, `transition_org`, or the approval routes.

## 8. Acceptance criteria and tests

| AC | Criterion | Test |
|---|---|---|
| AC1 | List and detail `staff_count`, `students`, `applications`, `enrollments` equal hand-computed fixture values; archived students, withdrawn and School-bridged applications, deactivated staff and another agency's rows excluded. | `test_agn_022_network.py` with `agn022_helpers.network_world` |
| AC2 | Commission buckets per currency (mixed INR/USD fixture, never summed) and deposit figures equal fixture values. | same |
| AC3 | Zero-student org → zeros and empty lists. | backend + vitest |
| AC4 | Suspend from the network flow denies every member on their next request; reinstate restores. | existing `test_agn_001_registration_and_gate.py:117` kept green + new backend test calling the action then a Master and a staff agent route + Playwright |
| AC5 | Each new route: Master, staff, counselor, overseas_student → 403; unauthenticated → 401; overseas_admin and super_admin → 200. | backend (parametrized) |
| AC6 | Each drill-down request writes exactly one audit row with the §5.3 metadata; list/summary/403/404/422 write none; audit failure → 500 with no body data. | backend |
| AC7 | Drill-down rows contain no email/phone/date of birth and only `O`'s rows. | backend |
| AC8 | Existing `/agent-orgs` behaviour unchanged (existing suite green); new keys present and correct. | `test_agn_001_org_admin.py` + new test |
| AC9 | UI loading/empty/error states; super_admin sees no Suspend/Reinstate; pending org links to Approvals; 409 refetches. | vitest `AgentNetworkPanel.test.tsx`, `AgentOrgDetailPanel.test.tsx` |
| AC10 | Nav entry present; pages usable at 375px; headings, status regions, focus return. | `navigation.test.ts`, Playwright `agn-022-agent-network.spec.ts`, browser QA |

Tests are written before implementation (TDD).

## 9. Regression risks

- `/agent-orgs` consumers: `AgentApprovalPanel` (+ vitest), `test_agn_001_org_admin.py`, `test_agn_002_staff_access.py:78` —
  additive keys only; no field renamed or removed.
- E2E: `agt-001`, `agt-002`, `agn-001`, `agn-004` specs and `helpers/agency.ts` locate "Agent Approvals" / `.action-card` —
  the new page uses neither; `/overseas/admin/agents` untouched.
- `agn-011-deposit.spec.ts:88` clicks the first "Agent deposits" link — new label "Agent network" does not match.
- `navigation.bdm.test.ts:20` — entries only appended.
- Suspension gate suites (AGN-001…021) — gate code untouched; run them.
- Count drift from the agency dashboard — definitions imported, and AC1 compares against the same fixture semantics.

## 10. Out of scope

Approve/reject on the network page; per-student detail pages; admin edits; offers/visa counts on the network; money on the
list; CSV export; `SUPER_ADMIN_NAV` entry; caching; migrations; ang-019/020.

## 11. Documentation

`PRODUCT_DECISION_REGISTER.md` `DEC-SCOPE-063`; `API_CONTRACT.md` (new keys + three routes); `RBAC_MATRIX.md` (admin
read-only drill-down, audit); `RTM.md` AGN-022 row with AC1–AC10; `ENHANCEMENT_BACKLOG.md` and the `AGENT_CRM_BACKLOG.md`
status table (AGN-022 in progress).
