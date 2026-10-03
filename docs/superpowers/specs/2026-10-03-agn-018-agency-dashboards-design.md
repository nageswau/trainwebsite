# AGN-018 — Agency Master / Staff dashboards and role-specific navigation — design

**Status:** design approved in-session 2026-10-03 (`EXPLICIT_APPROVAL` — answers to structured questions and three design-section
reviews), recorded as `DEC-SCOPE-060` (the next free number on `main` @ `e1c2084`; renumber on merge if another branch takes it first).
Source item: `docs/delivery/AGENT_CRM_BACKLOG.md` ang-018 (`DERIVED_BLUEPRINT`). Depends on AGN-004/005, AGN-008 … AGN-014 and AGN-016,
all on `main`. Branch: `feature/agn-018-master-dashboard-impl`. **GATE-09:** no code until this spec and its plan are approved.

## 1. Requirement and acceptance

Business requirement (`EVID-015` §2, §4, §6): Master dashboard with 14 KPIs (§2); Staff "Dashboard ✅ Limited" and the Staff sidebar
(§4, §6).

Owner acceptance: each KPI equals a hand-computed fixture count; Staff numbers include only their own students; offers are counted by
stage and by offer record, consistently.

## 2. Decisions (`DEC-SCOPE-060`, answered by the owner 2026-10-03)

| ID | Decision |
|---|---|
| G1 | **Agency only.** `RAID.md` I-48 (non-agent offer counts in `portal.py` and `OFFER_ONWARD_STATUSES`) stays out of scope and open. |
| G2 | **Staff performance summary** = a compact Master-only per-member table (Students / Applications / Offers / Enrollments, all-time, no filters). Funnel, date range and branch filters stay with ang-019. |
| G3 | **KPI definitions** as in §4 (accepted as listed). |
| G4 | **Navigation: relabel and link existing pages only** (§6). No access is removed; no Journey link until a route exists. |
| G5 | **One offer rule.** O5 (`DEC-SCOPE-056`) expressed once in SQL (`offer_clause`) beside the Python `counts_as_offer`; a parity test pins them. The Offers tile is not linked to the sidebar "Offer received" filter, which keeps its AGN-008 meaning (applications currently at stage `offer`). |
| G6 | **Approach A:** a new typed read-only endpoint and a dashboard panel on the existing page; the portal payload keeps its contract. |

Design details fixed by this spec (within the approved sections): D1 visa and offer counts use the milestone base (withdrawn
included); D2 breakdowns top 10 + "Other"; D3 deactivated members appear in the staff table only while they still have active
assigned students; D4 the "Claimable commission" INR label (it sums every currency) is unchanged and logged in `RAID.md`.

## 3. Existing behaviour (verified in code, `main` @ `e1c2084`)

- The agency dashboard is `GET /api/v1/portal/overseas/agent/dashboard` → `services/portal.py` `_agent()` (L692–743): rows loaded and
  counted in Python. Metrics in order: Students, Applications (non-withdrawn), Pending actions, [Master: Claimable commission, Claims,
  Revenue], Offers, Your code.
- **Defect:** the Students metric inner-joins `AgentStudent` to `users` (L693), so students with no login (AGN-004) are not counted.
- Offers: `services/agent_applications.py` `OFFER_COUNTED_STATUSES` / `counts_as_offer` (L197–204). The sidebar filter
  `group_clause("offer")` is `status == 'offer'`.
- Scope helpers (reused, unchanged): `agent_students.student_scope` / `application_scope`, `agent_documents.document_scope`,
  `agent_tasks.task_scope` / `pending_count`, `agent_orgs.org_member_ids`, `rbac.is_agent_staff` / `agent_may`.
- Frontend: `/overseas/agent/dashboard` → `PortalPage` → `PortalSection` (generic tiles + table). One nav,
  `PORTAL_NAV["overseas/agent"]`, filtered for Staff by `agentNavFor`.
- There is no `/agent/dashboard` route, no `SchoolDashboardPanel` (the backlog name; the real component is `SchoolKpiBoard`), and the
  application column is `submitted_on` (a date), not `submitted_at`.

## 4. KPI definitions (G3)

"Scope" is the caller's: a Master the whole agency, Staff their assigned students (the existing helpers). Every application count
excludes School-bridged rows (`school_student_id IS NOT NULL`), as `with_owner` does today.

| Key | Label | Definition | Must equal |
|---|---|---|---|
| `students` | Total students | `agent_students` in `student_scope`, `status='active'`; no join to `users` | Students list (default view) total |
| `applications` | Applications | `application_scope`, not bridged, `status <> 'withdrawn'` | Applications "All" total |
| `offers` | Offers | `application_scope`, not bridged, `offer_clause()` (O5: stage in `OFFER_COUNTED_STATUSES` OR `offer_type IS NOT NULL`; withdrawn included) | Reports "Offers" row; `counts_as_offer` over the same rows |
| `visa_applications` | Visa applications | `COUNT(DISTINCT visa_cases.application_id)` over applications in `application_scope`, not bridged (withdrawn included, D1) | — |
| `visa_approvals` | Visa approvals | as above with `visa_cases.decision = 'approved'` | — |
| `enrollments` | Enrollments | `application_scope`, not bridged, `status = 'enrolled'` | Applications "Enrolled" total |
| `pending_documents` | Pending documents | `document_scope`, `verification_status = 'pending'` | Documents "Pending" total |
| `pending_actions` | Pending actions | existing `agent_tasks.pending_count` (unchanged) | Tasks "Open" total |
| `by_country` | Applications by country | the `applications` base grouped by `countries.name` (university's country; "Unknown" when none) | sums to `applications` |
| `by_university` | Applications by university | the `applications` base grouped by `universities.name` | sums to `applications` |
| `staff` | Staff performance / Students by staff | Master only: one row per member — `students`, `applications`, `offers`, `enrollments` each equal to what that member's own Staff-scope dashboard shows | each row = that member's own dashboard |
| `unassigned_students` | Unassigned | Master only: active students with `assigned_member_id IS NULL` | — |
| `commission` | Claimable commission, Claims, Revenue | Master only: today's three values and strings, unchanged | portal metrics |
| `reports_available` | View reports | Master: true; Staff: `agent_may(user, "can_view_reports")` | the Reports nav link |

Breakdowns: sorted by count desc then label; the first 10 are returned and the rest are summed into `other` (D2).

## 5. Backend

### 5.1 Route — `apps/api/app/api/agent_dashboard.py` (new)

`GET /api/v1/workflows/overseas/agent/crm/dashboard` → `AgentDashboardOut`. Router prefix `/workflows/overseas/agent/crm`, registered
in `main.py` beside the other agent routers. Gate: the same rule as `agent_students._gate` (role `agent`, division `overseas`,
`agent_denial_reason` → 403). Super admin is refused here (agency-internal, as every CRM route). Read-only: no audit row, no
commit, no query parameters.

### 5.2 Service — `apps/api/app/services/agent_dashboard.py` (new)

- `offer_clause()` — the SQL form of O5, built from `OFFER_COUNTED_STATUSES`.
- `dashboard(db, user) -> dict` —
  1. one `SELECT` of scalar subqueries for the eight counts (one statement ⇒ one snapshot);
  2. two `GROUP BY` queries for the breakdowns;
  3. Master only: the staff table and unassigned count, and the commission values.
- Staff table: students grouped by `assigned_member_id`; applications attributed to a member through the agency record
  (`agent_student_id`) or the linked account (`student_id` of an `agent_students` row of the agency), `COUNT(DISTINCT application id)`
  per member — mirroring `application_scope` for that member (archived links included, as `application_scope` includes them).
  Members listed: active members, plus deactivated members with ≥1 active assigned student (D3), ordered by member code.
- Commission: the three existing values move into a shared helper (`commission_metrics(commissions)`, including today's
  `_paid_per_currency`) in this module; `portal._agent` imports it, so both print identical strings. No change to the values.
- For Staff, the staff table, unassigned count and commission are never queried (`null` in the response).

### 5.3 Schema — `schemas.py`

`AgentDashboardOut`: `scope: Literal["agency","own"]`, `member_code: str | None`, the eight integer counts,
`by_country` / `by_university: AgentBreakdownOut {items: list[{label: str, count: int}], other: int}`,
`staff: list[AgentStaffRowOut] | None` (`member_id`, `code`, `name`, `role`, `active`, `students`, `applications`, `offers`,
`enrollments`), `unassigned_students: int | None`, `commission: AgentCommissionSummaryOut | None` (`claimable`, `claims`, `revenue`
— display strings as today), `reports_available: bool`, `as_of: datetime`.

### 5.4 Portal compatibility — `services/portal.py`

The dashboard branch keeps its labels, order and strings. Its Students, Applications and Offers values come from the new service's
counts (same scope, so unchanged except the Students fix). Other sections are not touched.

### 5.5 Transactions, races, errors, performance

- Read-only; the scalar counts share one statement snapshot. Breakdowns and the staff table are separate statements and may differ
  from the headline counts by an in-flight write under concurrency — accepted for a dashboard, stated in `API_CONTRACT.md`.
  No locks, no caching.
- 403: non-agent role, super admin, pending/suspended agency, deactivated member (existing `agent_denial_reason` messages). 401:
  no session. An empty agency → 200 with zeros, empty lists, `other: 0`.
- Uses existing indexes (`agent_students` agent/status and assigned member; `overseas_applications` agent, agent student, student,
  university; `visa_cases.application_id`; tasks). `student_documents.application_id` is unindexed; not added (no migration) —
  logged in `RAID.md` for ang-019/020 if measurements warrant.

## 6. Frontend

### 6.1 Page

`/overseas/agent/dashboard` keeps `PortalPage` and its fetch list (the portal payload stays the page's gate). When
`section === "dashboard"` and `user.role === "agent"`: render `<Suspense fallback={<AgentDashboardSkeleton/>}><AgentDashboardPanel/></Suspense>`
above `PortalSection`, and pass `PortalSection` the payload with `metrics: []` (no duplicated tiles; the open-applications table
stays). Super admin: unchanged.

### 6.2 `components/AgentDashboardPanel.tsx` (new, async server component)

Fetches `DASHBOARD_URL` (`lib/agentDashboard.ts`, new) with `serverApi`. Reuses the `kpi-group` / `kpi-grid` / `kpi-tile` classes and
`<dl>` markup of `SchoolKpiBoard` (not the component: its keys are school-specific).

- Heading "Agency at a glance" (Master) / "Your students at a glance" (Staff); "Your code M001".
- Groups: **Students** (Total students, Pending actions); **Pipeline** (Applications, Offers, Visa applications, Visa approvals,
  Enrollments); **Documents** (Pending documents); **Commission** (Master: Claimable commission, Claims, Revenue).
- Tile links: Total students → `/overseas/agent/students`; Applications → `/overseas/agent/applications`; Enrollments →
  `?status=enrolled`; Pending documents → `/overseas/agent/documents?view=pending`; Pending actions → `/overseas/agent/tasks?view=open`.
  Offers / Visa tiles: no link, a short note ("includes later stages and withdrawn").
- Tables (each with a `<caption>`, in a horizontal-scroll wrapper): Applications by country; Applications by university (+ "Other"
  row when `other > 0`); Master only: Staff performance (Member, Role, Students, Applications, Offers, Enrollments; deactivated
  members labelled) + an "Unassigned" students row.
- "View reports →" when `reports_available`.
- States: loading skeleton (`aria-busy="true"`, same footprint); empty (zeros; "No applications yet"; "No staff yet — add staff from
  Team"); error (`role="alert"` "Dashboard figures are unavailable right now" + Retry link to the same URL; the rest of the page
  works); 401 → the existing access-unavailable card. Works at 320 px and by keyboard.
- Staff variant renders no commission group, staff table or the word "commission".

### 6.3 Navigation — `lib/navigation.ts` (G4)

- Both roles: Applications children start with "All applications" (`/overseas/agent/applications`); "Tasks" is labelled
  "Tasks & Follow-ups".
- Staff only: "Students" → "My Students" with children All (`/overseas/agent/students`) and Add (`/overseas/agent/students?new=1`).
  Master keeps "Students" without children.
- Unchanged: Universities, the Withdrawn filter, Reports gating, Team/Commissions hiding, the unread badge, `PortalPage`'s
  section allow-list (all hrefs stay on existing sections).
- `AgentStudentsPanel`: opens its existing add form when the URL has `new=1` (focus on the first field), so the Add link works.

### 6.4 Types

`AgentDashboard` (and row/breakdown types) in `lib/types.ts`.

## 7. Authorization and security

- Scope comes only from the existing helpers in the WHERE clause; nothing is filtered after loading.
- Staff never receive another member's numbers: the staff table, unassigned count and commission are not computed for them.
- Tenant isolation: every clause is bounded by `org_member_ids(user)`; a second agency's data never changes a count.
- No free text in the response beyond university / country / member names already visible to the same caller.

## 8. Acceptance criteria and tests

| ID | Criterion | Test |
|---|---|---|
| AGN-018-AC01 | Every KPI equals a hand count from one fixture: Master + 3 staff + a second agency; students with/without login, archived, unassigned; applications at every stage, withdrawn, withdrawn-after-offer, offer recorded before the stage moved, School-bridged; two visa cases on one application, one approved; pending/verified/unattached documents; open/done/cancelled tasks; commissions in two currencies | `apps/api/tests/test_agn_018_dashboard.py` |
| AGN-018-AC02 | Staff numbers include only their assigned students; other staff's and the other agency's data change nothing | same |
| AGN-018-AC03 | Each staff-table row equals that member's own Staff dashboard | same |
| AGN-018-AC04 | Offers: each application counted once whether by stage, by record or both; KPI = Reports "Offers" row = `counts_as_offer`; SQL/Python parity for every stage ± recorded offer | same + `test_agn_018_offer_parity.py` |
| AGN-018-AC05 | Linked KPIs equal their list totals (students, applications All/Enrolled, documents Pending, tasks Open) | `test_agn_018_dashboard.py` |
| AGN-018-AC06 | Staff response: `staff`, `unassigned_students`, `commission` null; "commission" absent | same |
| AGN-018-AC07 | 403 for non-agent, super admin, suspended agency, deactivated member; 401 without session; empty agency → zeros | same |
| AGN-018-AC08 | Portal dashboard keeps labels, order and commission strings; Students now counts no-login students | `test_agn_018_portal_compat.py` |
| AGN-018-AC09 | UI: Master/Staff variants, links, empty, error, loading; nav as §6.3; keyboard; 320 px | `apps/web/tests/components/AgentDashboardPanel.test.tsx`, nav unit tests, `apps/web/tests/e2e/agn-018-dashboard.spec.ts` |

Tests are written first (TDD).

## 9. Regression risks and deliberate test updates

- Must pass unchanged: `test_agn_010_counts.py`, `test_agn_014_commission_reports.py`, `test_agn_016_dashboard.py`,
  `test_agn_008_dashboard.py`, `test_agn_002_staff_access.py`, `test_agn_003_*`, `test_agn_001_tenancy.py`, `test_agn_004_staff_guards.py`,
  `test_agn_009_existing_routes.py`, `test_agn_017_*`, `PortalShell.badge.test.tsx`, e2e agn-010/014/016/017.
- Deliberate updates (each named in the commit and `RTM.md`): any test pinning the old Students count where a no-login student is in
  scope (e.g. `test_agn_004_staff_scope.py:93` if its fixture has one); `navigation.agent.test.ts` / `navigation.test.ts` (labels,
  children, Master nav); `PortalShell.children.test.tsx` and e2e label assertions for "Tasks" / Applications children.
- `PortalPage.agentApplications.test.tsx`'s fetch list is unchanged by design (the panel fetches separately).

## 10. Out of scope

RAID I-48 (non-agent offer counts); the "Claimable commission" INR label (D4, RAID); the "Offer received" filter meaning; Journey
link; ang-019 funnel and filters; ang-020 reports; ang-022 network oversight; caching; migrations; other roles' dashboards.

## 11. Documentation

`PRODUCT_DECISION_REGISTER.md` `DEC-SCOPE-060`; `API_CONTRACT.md` §8 (new route, snapshot note); `RBAC_MATRIX.md` Dashboard row;
`RTM.md`; `ENHANCEMENT_BACKLOG.md` §AGN-018; `AGENT_CRM_BACKLOG.md` status table; `ROLE_NAVIGATION.md` Agent; `SCREEN_CATALOG.md`
SCR-AGT-003; `RAID.md` (I-48 carried on as its own item; new: INR label, `student_documents.application_id` index).
