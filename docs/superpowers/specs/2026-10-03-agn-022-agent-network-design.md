# AGN-022 — Overseas Admin agent network oversight — design

NO-ASSUMPTION MODE. Status: **design, awaiting the owner's written-spec review.** No code written. Branch
`feature/agn-022-agent-network` (from `main` @ `3bde8796`). Decision: `DEC-SCOPE-064` (this spec §2).

---

## 1. Requirement and acceptance

- **Requirement (owner, in-session 2026-10-03, quoting `EVID-015` "Best approach" / §9 and `AGENT_CRM_BACKLOG.md` ang-022):**
  "Edusphere's central admin can see the overall agent network and student/application data according to the permissions you
  define."
- **Owner's acceptance criteria:** counts match fixtures; suspend blocks the org immediately (ang-001 AC4); non-admin → 403.
- **Source status:** `EVID-015` and the backlog are `DERIVED_BLUEPRINT`. The backlog's "D17 — read-all, limited actions"
  (`AGENT_CRM_BACKLOG.md:164`) is cited there as `DEC-SCOPE-035`, which on `main` is ENH-027 (known mis-citation). The owner's
  answers in §2 are the authority for this feature.

## 2. Decisions (`DEC-SCOPE-064`, answered by the owner 2026-10-03)

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
| `GET /overseas-admin/agent-orgs/{org_id}` | 404 "Organisation not found" if absent. Returns `{id, name, prefix, status, created_at, status_changed_at, masters, staff_count, counts, commission, deposits, as_of}`. `masters` uses `org_masters` (same shape as the list). **No staff list** (review R-API-3: the requirement asks for a staff count; an unbounded, unpaginated name list adds PII for no stated purpose). |
| `GET /overseas-admin/agent-orgs/{org_id}/students` | `status: Literal["active","archived"] = "active"`, `limit` 25 (1–100), `offset ≥ 0`. 404 if org absent. `{items, total, limit, offset}`. Audits (5.3). |
| `GET /overseas-admin/agent-orgs/{org_id}/applications` | optional `status` (one of `OVERSEAS_APPLICATION_STAGES` + `withdrawn`, else 422), same paging, 404 if absent. Audits (5.3). |
| `POST /overseas-admin/agent-orgs/{org_id}/{action}` | **Unchanged.** |

All three new routes set `Cache-Control: private, no-store` (as `agent_dashboard.py:29`). Errors use the app's existing
FastAPI `{"detail": ...}` shape, like every neighbouring route (the `API_CONTRACT.md` §0.3 `error_code` shape is not what the
code returns; not changed here). Field names stay snake_case like the rest of the API.

Response models: the three new routes get Pydantic models in `schemas.py` (as AGN-018 G6). The existing list keeps returning a
dict (unchanged style); the two new keys are documented in `API_CONTRACT.md`.

Route order: the new `GET` paths do not collide with `POST /agent-orgs/{org_id}/{action}` (different method).

### 5.3 Read audit (N2)

After the rows and total are fetched: `db.add(AuditLog(user_id=user.id, action="agent_network.students_read" |
"agent_network.applications_read", entity_type="agent_org", entity_id=str(org_id), outcome="read", metadata_json={"status":
status, "limit": limit, "offset": offset, "returned": len(rows)}))`, then `await db.commit()`, then return. A failed audit
write raises → 500, no data returned (SEC-001 fail-closed; pattern `lookups.py:120`). A 403/404/422 writes no audit row.
The response is built into plain dicts/models **before** the commit (the session uses `expire_on_commit=False`, but the order
keeps the route independent of that setting). The audit metadata carries no names or other PII. A GET that writes an audit row
is an access record, not a state change: a client retry writes a second row, which is correct (two reads happened). No
idempotency key (`API_CONTRACT.md` §0.2: reads need none).

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

Pattern of `AgentApprovalPanel` (URL-held tab/page/q, 20 per page, Previous/Next, `aria-pressed` status buttons in a
`role="group"`, `role="search"` form with a visible label), but heading **"Agent network"** (`h2`, as the deposits page) and no
`.action-card` class (keeps the e2e "Agent Approvals" locators unambiguous). Status buttons All (default) / Active / Suspended /
Pending / Rejected; search by agency, prefix, Master code/email (the existing `q`, `maxLength=100`).

- **Layout:** a table (counts scan better in columns than in cards) using the existing `.table compact stack` classes inside a
  focusable `.table-scroll` region named by the heading (AGN-018 `TableRegion` pattern): on phones each row becomes a labelled
  block via `data-label`, so nothing scrolls sideways at 320–375 px. Columns: Agency (name + prefix; the name is the link to the
  detail, with no separate "View" button), Status (text in a `.status` pill — never colour alone), Masters (codes), Staff,
  Students, Applications, Enrollments. Numbers right-aligned.
- **Loading:** first load shows "Loading agencies…" (`role="status"`); paging/searching keeps the current rows visible, dimmed
  with `aria-busy="true"` (the `AgentStudentsPanel` pattern), and a stale response is dropped by request sequence so a slow
  older page never overwrites a newer one.
- **Empty:** "No agencies match “q”." for a search, otherwise per-status text ("No suspended agencies.").
- **Error:** `role="alert"` with the server `detail` (or "Unable to load agencies.") and a Retry button.
- **Keyboard/focus:** after Previous/Next or a status change, focus moves to the results heading (`tabIndex={-1}`) so keyboard
  and screen-reader users land on the new page; "Showing a–b of n" text beside the pager.

### 6.3 `components/AgentOrgDetailPanel.tsx` (new, client)

- Header: plain back link "← Agent network", `h2` agency name + prefix, status pill + "since <date>".
- Summary: counts in the existing `.metric-grid` / `.metric` tiles (4 per row → 2 at ≤980 px → 1 at ≤640 px, already in
  `globals.css`); commission buckets per currency and deposit figures (`formatInr`) as small `.table compact` tables with
  `scope="row"` headers; Masters (code, name, email, status — the fields the list already exposes). Zero values render as "0",
  never blank.
- Actions (only when `canAct`): Suspend (active) with inline confirm ("Every member loses access on their next request."),
  Reinstate (suspended). Buttons disable while in flight and an in-flight guard blocks double submits; focus returns to the
  action button; result announced in an always-mounted `role="status"` region; 409 → show the server message and refetch the
  summary; network error → "Network error. Check your connection and try again." Pending/rejected → link "Review in Agent
  Approvals" (`/overseas/admin/agents`). super_admin: no buttons, no link.
- Students / Applications: two `aria-pressed` buttons (the same toggle pattern as the status buttons; no new ARIA tablist widget),
  nothing selected on first view; each list is fetched only when chosen (so audit rows reflect actual views), paged 20 with the
  same loading/dimming/stale-drop/focus rules as 6.2, `.table compact stack` layout; empty "No students yet" / "No applications
  yet"; error + Retry; read-only, no edit controls. Students filter Active/Archived; applications show the stage label.
- Summary loading: "Loading agency…" status text; error + Retry; 404 → "Organisation not found" + link back to the list.
- The page validates `orgId` as a UUID before rendering the panel (`notFound()` otherwise), and the panel builds request URLs
  with `encodeURIComponent`, so a crafted path segment can never address a different API route.
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
| AC7 | Drill-down rows contain no email/phone/date of birth and only `O`'s rows; the detail has no staff list; all three new routes send `Cache-Control: private, no-store`. | backend |
| AC8 | Existing `/agent-orgs` behaviour unchanged (existing suite green); new keys present and correct. | `test_agn_001_org_admin.py` + new test |
| AC9 | UI loading/empty/error states; paging keeps rows dimmed and drops stale responses; super_admin sees no Suspend/Reinstate; pending org links to Approvals; 409 shows the message and refetches; a double click sends one request; drill-down lists are not fetched until chosen. | vitest `AgentNetworkPanel.test.tsx`, `AgentOrgDetailPanel.test.tsx` |
| AC10 | Nav entry present; pages usable at 320 and 375 px with no sideways scroll; one `h2` per page, focus moves to the results heading after paging and back to the action button after suspend/reinstate; status shown as text. | `navigation.test.ts`, Playwright `agn-022-agent-network.spec.ts`, browser QA |
| AC11 | A non-UUID `orgId` in the page URL renders not-found without calling the API; agency names containing markup render as text. | vitest + Playwright |

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

## 11. Engineering reviews (2026-10-03, at the owner's request)

### 11.1 API and interface design

| ID | Check | Result |
|---|---|---|
| R-API-1 | Backward compatibility | `/agent-orgs`: two **added** keys only; no field, param, order, status code or message changes. Suspend/reinstate untouched. |
| R-API-2 | Contract style | Follows the shipped neighbours, not a new style: limit/offset `{items,total,limit,offset}` (as `/agent-orgs`), snake_case, FastAPI `detail` errors, sub-resources `/{id}/students`, `/{id}/applications`, no verbs in new paths. |
| R-API-3 | Data exposure | Staff name list removed from the detail (count only). Drill-down fields are an allowlist (§5.1). |
| R-API-4 | Validation at the boundary | `org_id: UUID`; `status` as `Literal`; `limit` 1–100; `offset ≥ 0` → 422, all before the service. Internal service code trusts the typed values. |
| R-API-5 | HTTP semantics | GETs change no domain state; the audit row is an access record (retry = second row, intended). No idempotency key (reads, §0.2). 403 before lookup, 404 only to admins. |
| R-API-6 | Transactions / DB | One commit per drill-down request, after the reads; list/summary never commit. Grouped queries bounded by ≤100 ids; existing indexes suffice; no N+1 (no per-org loop). |
| R-API-7 | Typed outputs | Pydantic models for the three new routes; the existing list's new keys documented in `API_CONTRACT.md`. |

### 11.2 Frontend UI engineering

Reuses `PortalShell`, the agent-deposits page shell, `AgentApprovalPanel`'s URL-state/search/pager pattern,
`AgentStudentsPanel`'s dim-and-drop-stale paging, AGN-018's `.table compact stack` + `.table-scroll` region, `.metric-grid`,
`.status` pills, `lib/apiErrors`, `formatDate`, `formatInr`, `useFocusAfterRender`. No new CSS framework, component library or
dependency; new CSS only if browser QA finds a gap. Hierarchy: page `h2`, section `h3`; status always as text; every control a
native `button`/`a`/`input` with a visible or `aria-label` name; controls keep the existing `.btn.small` size used by every
admin panel (target size is checked in browser QA, not changed speculatively).

### 11.3 Security and hardening

| Area | Finding | Design response |
|---|---|---|
| Authentication | Unchanged: cookie JWT via `get_current_user` (per-request user reload). | None needed. |
| Authorization | `_require_overseas_admin` on every new route, before lookup. | AC5. |
| IDOR | Admins are global by design; agents cannot reach the routes. Every query is bound to `M(O)` of the path org, so one org's id never returns another org's rows. | AC1/AC7 seed a second agency. |
| Role escalation | No new writes; suspend/reinstate reuse `transition_org` (lock + audit). super_admin buttons hidden (N3). | — |
| Input validation | All params typed (R-API-4); `q` already escaped for LIKE in the shipped list. | AC8. |
| SQL injection | SQLAlchemy expressions only; no string-built SQL. | Code review. |
| XSS | React escaping; agency/student names are user-entered and rendered as text; no `dangerouslySetInnerHTML` (none exists in `components/` today). | AC11. |
| Path injection (client) | `orgId` validated as UUID in the page; URLs built with `encodeURIComponent`. | AC11. |
| CSRF | The only state change is the existing suspend/reinstate POST; protection is today's `SameSite=Lax` httpOnly cookie (`auth.py:92`). No CSRF token exists app-wide — **residual, already recorded in the register (ENH-005 security findings); not changed here.** | — |
| Token/session handling | Unchanged; no tokens in URLs, responses or logs. | — |
| Secret exposure | No new config or secrets. | — |
| Sensitive logs | No new log lines with names; audit metadata = status/limit/offset/count only. | AC6. |
| Caching of PII | `Cache-Control: private, no-store` on new routes. | AC7. |
| Rate limiting | None app-wide (recorded residual). Admin-only reads, `limit ≤ 100`, every drill-down audited. No new limiter (would be a speculative cross-cutting change). | — |
| Audit | Drill-down reads audited fail-closed (N2); suspend/reinstate already audited. | AC6. |
| Residual (recorded, not changed) | Admin routes gate on `users.role`, not active role assignments (register ENH-005 security findings). | — |

## 12. Documentation

`PRODUCT_DECISION_REGISTER.md` `DEC-SCOPE-064`; `API_CONTRACT.md` (new keys + three routes); `RBAC_MATRIX.md` (admin
read-only drill-down, audit); `RTM.md` AGN-022 row with AC1–AC10; `ENHANCEMENT_BACKLOG.md` and the `AGENT_CRM_BACKLOG.md`
status table (AGN-022 in progress).
