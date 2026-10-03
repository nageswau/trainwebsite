# AGN-019 — Staff performance and student funnel — design

**Status:** design approved in-session 2026-10-03 (`EXPLICIT_APPROVAL` — answers to seven structured questions and three
design-section reviews), recorded as `DEC-SCOPE-063` (next free on `main` @ `3bde879`; renumber on merge if taken).
Source item: `docs/delivery/AGENT_CRM_BACKLOG.md` ang-019 (`DERIVED_BLUEPRINT`). Depends on AGN-018 (`DEC-SCOPE-062`), on `main`.
Branch: `feature/agn-019-staff-funnel`. **GATE-09:** no code until this spec and its plan are approved.

## 1. Requirement and acceptance

Business requirement (`EVID-015` §8, via the backlog): per-staff Students, Applications, Offers, Visa Applications, Visa Approvals,
Enrollments, and the funnel Students → Applications → Submitted → Offers → Visa → Enrolled.

Owner acceptance: funnel stages are monotonic non-increasing for a fixture; a reassigned student counts for the current owner (or the
owner at the time: spec decision — resolved as P1 below).

## 2. Decisions (`DEC-SCOPE-063`, answered by the owner 2026-10-03)

| ID | Decision |
|---|---|
| P1 | **Current owner.** A student and all of their applications and stages count for the staff member assigned now (`agent_students.assigned_member_id`). No ownership history is reconstructed; matches AGN-018 G2. |
| P2 | **No branch filter.** There is no branch data (`DEC-SCOPE-040` S4 did not take Branch; the D10 branch list was never built). Deferred and logged in `RAID.md`; no schema change. |
| P3 | **"Reached at least" stages.** A student counts at a stage if any of their applications reached that stage or a later one (§4.2). The funnel is non-increasing by construction. |
| P4 | **Student cohort date range.** `from`/`to` select students by the day their agency record was created; everything those students did, at any time, counts. |
| P5 | **History counts in the funnel.** The funnel includes archived students and withdrawn applications. The per-staff table keeps AGN-018's G3 column definitions, so with no dates it equals the dashboard's staff table. |
| P6 | **Rows:** every active staff member (zeros included); a deactivated member only when any count is non-zero, marked; an "Unassigned" row only when non-zero. The funnel can be shown for the agency, one row, or Unassigned. |
| P7 | **Placement:** a new Master-only sidebar page "Staff Performance" (`/overseas/agent/performance`) reading its own endpoint; the dashboard's staff table links to it. |
| P8 | **Approach A:** a new service `services/agent_performance.py`; the application→agency-student join in `agent_dashboard.staff_rows` is extracted as `owner_join()` and shared; a parity test pins AGN-019 to AGN-018. |

## 3. Existing behaviour (verified in code, `main` @ `3bde879`)

- `services/agent_dashboard.py` (AGN-018): `agency_applications(user)` = `application_scope(user)` + not School-bridged;
  `offer_clause()` = O5 in SQL, pinned to `counts_as_offer` by `test_agn_018_offer_parity.py`; `_visa()` counts distinct applications
  with a visa case; `staff_rows()` is the Master's all-time per-member table (Students active / Applications non-withdrawn / Offers O5 /
  Enrollments), owner by `or_(app.agent_student_id == AgentStudent.id, and_(AgentStudent.student_id IS NOT NULL, app.student_id ==
  AgentStudent.student_id))`; deactivated members drop out once they hold no active students (AGN-018 D3).
- Assignment targets active staff only (`api/agent_students.py` assign → `active_staff_member`), so Masters never hold students.
- Stage data: `overseas_applications.status` (`OVERSEAS_APPLICATION_STAGES`, `withdrawn` terminal), `submitted_on` (Date),
  `offer_type`/`offer_date`, `enrollment_date`; `visa_cases.decision` (`approved`/`refused`/`withdrawn`).
- Gates: `api/agent_students._gate` (agents of an active agency; super admin refused) admits staff; `_require_master_action(user, msg)`
  refuses staff.
- Date range precedent (AGN-014): `api/workflows._report_date` (strict `YYYY-MM-DD`, 422 `"<name> must be a date (YYYY-MM-DD)"`),
  inclusive UTC days, `"date_to must be on or after date_from"`; web `lib/agentCommissionReport.ts` `readRange`/`writeRange`/
  `reportQuery` keep the range in the URL.
- `PortalPage.tsx` renders agency pages that read their own API (Applications, Documents, Tasks, Notifications) behind the portal
  payload fetch, tolerating its 404. `agentNavFor` hides `STAFF_HIDDEN` hrefs from staff.
- No `branch` on `AgentOrgMember`; no assignment history table (only `audit_logs` `agent_student.create`/`assign` JSON).

## 4. Definitions

### 4.1 Cohort

Students in scope: `student_scope(user)` (a Master = every agency record of the org), with `AgentStudent.created_at >= from 00:00Z`
and `< (to + 1 day) 00:00Z` when given (inclusive UTC days, as AGN-014). Open bound = unbounded. Applications in scope: those joined to
a cohort student by `owner_join()` and within `agency_applications(user)`.

### 4.2 Funnel levels (P3)

Per application, its level is the highest true of:

| Level | Stage | Application condition |
|---|---|---|
| 1 | Applications | the application exists (any status, withdrawn included) |
| 2 | Submitted | `submitted_on IS NOT NULL`, or level ≥ 3 |
| 3 | Offers | `offer_clause()` (O5), or level ≥ 4 |
| 4 | Visa | a `visa_cases` row exists for it, or level 5 |
| 5 | Enrolled | `status = 'enrolled'` |

A student's level is `MAX` over their in-scope applications, `0` with none. Funnel stage *k* = count of cohort students with level ≥
*k*; Students = count of all cohort students (archived included). Status `visa_documentation` without a visa case is level 3, not 4
(the Visa stage means a visa application was recorded, as the Visa Applications column).

### 4.3 Per-staff columns (P5 — AGN-018 G3 over the cohort)

| Column | Definition |
|---|---|
| Students | cohort students with `status = 'active'` |
| Applications | distinct in-scope applications with `status != 'withdrawn'` |
| Offers | distinct in-scope applications matching `offer_clause()` |
| Visa applications | distinct in-scope applications with a visa case |
| Visa approvals | distinct in-scope applications with a visa case whose `decision = 'approved'` |
| Enrollments | distinct in-scope applications with `status = 'enrolled'` |

Owner of a row = the cohort student's current `assigned_member_id` (P1); `NULL` = Unassigned. Inherited from AGN-018 and unchanged: if
two members of one org each link the same login student, that student's applications count for both rows.

## 5. Backend

### 5.1 Route — `apps/api/app/api/agent_performance.py` (new)

`GET /api/v1/workflows/overseas/agent/crm/performance?date_from=&date_to=` → `AgentPerformanceOut`.

1. `membership = _gate(user)`; `_require_master_action(user, "Only an agency Master can view staff performance")` → 403 for staff
   (with or without `can_view_reports`).
2. `start, end = _report_date(date_from, "date_from"), _report_date(date_to, "date_to")`; `end < start` → 422
   `"date_to must be on or after date_from"`.
3. `payload = await performance(db, user, start, end)`; `Cache-Control: private, no-store`; one log line `agent_performance.read`
   with `org_id`, `actor_id`, `rows`, `duration_ms` (ids and timing only). No audit row (reads are not audited, `DEC-SCOPE-051` R7).
4. Registered in `main.py` beside `agent_dashboard.router`.

Unauthenticated → 401 (`get_current_user`). Errors carry no counts.

### 5.2 Service — `apps/api/app/services/agent_performance.py` (new)

- `owner_join()` — moved from `staff_rows` into `agent_dashboard.py` (returns the existing `or_(...)` expression); `staff_rows` calls
  it; no behaviour change.
- `cohort(user, start, end) -> list[ColumnElement]` — §4.1 student filters.
- `table_counts(db, user, start, end) -> dict[member_id | None, (students, applications, offers, visa_applications, visa_approvals,
  enrollments)]` — one statement: cohort `AgentStudent` LEFT JOIN applications on `owner_join()` and `agency_applications(user)`, LEFT
  JOIN a per-application visa subquery (`application_id`, `bool_or(decision = 'approved')`), `GROUP BY assigned_member_id`;
  `count(distinct case(...))` per column, students via `count(distinct case(status='active', AgentStudent.id))`.
- `funnel_counts(db, user, start, end) -> dict[member_id | None, (students, applications, submitted, offers, visa, enrolled)]` — one
  statement: inner subquery = per cohort student `MAX(level)` (§4.2, `CASE` over the joined application/visa subquery, `coalesce(…, 0)`);
  outer `GROUP BY assigned_member_id` with `count(*)` and `sum(case((level >= k, 1), else_=0))` per stage.
- `performance(db, user, start, end) -> dict` — loads org staff members (`AgentOrgMember` + `User.full_name`, role `staff`, ordered by
  `seq`, as `staff_rows`), builds rows per P6, the Unassigned row last, and `total` = the sum over every owner key returned by the two
  statements (all staff members and Unassigned), so it equals the agency-wide count.

Read-only: no writes, locks or commits; each statement is its own snapshot. A reassignment between the two statements can move one
student between rows across table and funnel for that request only (same trade-off as AGN-018's separate breakdown statements).
No migration: org filters use `ix_agent_students_agent_status` and `ix_agent_students_assigned_member`; `created_at` is a range filter
inside one org. `RAID.md` R-14 is re-measured with a seeded timing check; an index is proposed only if that shows a need.

### 5.3 Schema — `apps/api/app/schemas.py`

```python
class AgentFunnelOut(BaseModel):
    students: int; applications: int; submitted: int; offers: int; visa: int; enrolled: int

class AgentPerformanceRowOut(BaseModel):
    code: str | None          # None only for the Unassigned row
    name: str                 # "Unassigned" for that row
    active: bool              # True for Unassigned
    unassigned: bool
    students: int; applications: int; offers: int
    visa_applications: int; visa_approvals: int; enrollments: int
    funnel: AgentFunnelOut

class AgentPerformanceTotalOut(BaseModel):
    students: int; applications: int; offers: int
    visa_applications: int; visa_approvals: int; enrollments: int
    funnel: AgentFunnelOut

class AgentPerformanceOut(BaseModel):
    """Master only. No ids: codes and names only (as AgentDashboardOut)."""
    date_from: date | None
    date_to: date | None
    rows: list[AgentPerformanceRowOut]
    total: AgentPerformanceTotalOut
    as_of: datetime
```

`AgentDashboardOut` and the `/dashboard` route are unchanged.

## 6. Frontend

### 6.1 Navigation — `apps/web/lib/navigation.ts`

`"performance"` added to `PORTAL_NAV["overseas/agent"]` after `"reports"`; `AGENT_NAV_LABELS.performance = "Staff Performance"`;
`/overseas/agent/performance` added to `STAFF_HIDDEN`. Staff sidebars are otherwise unchanged.

### 6.2 Page — `apps/web/components/PortalPage.tsx`

`agentPerformance = key==="overseas/agent" && section==="performance"`, added to the portal-payload 404 tolerance and to `main`
(renders `<AgentPerformancePanel/>`). `services/portal.py` gets no new section.

### 6.3 `apps/web/lib/agentPerformance.ts` (new)

`PERFORMANCE_URL = "/api/v1/workflows/overseas/agent/crm/performance"`, the `AgentPerformance` types (mirroring §5.3), and
`funnelStages(f)` → the six `{label, count, percentOfStudents}` items. Range helpers are imported from `lib/agentCommissionReport.ts`
(`readRange`, `writeRange`, `reportQuery`, `DateRange`), not copied.

### 6.4 `apps/web/components/AgentPerformancePanel.tsx` (new, client)

- **Filter:** From / To date inputs, Apply and Clear; range read from and written to the URL (`?from=&to=`); a 422 shown beside the
  field it names (same mapping as `AgentCommissionReportPanel`). Lead text: "Students added between these dates, and how far they got."
- **Staff table:** Staff, Students, Applications, Offers, Visa applications, Visa approvals, Enrollments; "(deactivated)" suffix;
  "Unassigned" row; `.table-scroll` region labelled by its heading, `table compact stack` with `data-label` for phones (the AGN-018
  pattern, markup copied — `AgentDashboardPanel.tsx` is not refactored).
- **Funnel:** "Show funnel for" `<select>` (Agency, each row, Unassigned when present), client-side over the payload. An ordered list
  (`<ol aria-label="Student funnel">`) of six items; each shows its stage label, count and "% of students" as text, plus a decorative
  `aria-hidden` CSS bar whose width is relative to the Students stage (the `GradeBarChart` approach). The text is the accessible
  content, so there is no hidden duplicate table. Note: "Includes archived students and withdrawn applications. A student counts
  at every stage up to the furthest one reached." No chart library.
- **States:** loading skeleton; empty ("No students were added in this period." when `total.funnel.students == 0`); 401 → the
  existing session-expired message with a sign-in link; 403 → the server's message; other errors → "Couldn't load staff performance."
  with Retry; a request counter discards stale responses.

### 6.5 Dashboard link — `apps/web/components/AgentDashboardPanel.tsx`

The Master staff-table heading gains a "View staff performance" link to `/overseas/agent/performance`. No other change.

## 7. Acceptance criteria

| ID | Criterion |
|---|---|
| AC1 | Monotonic: on a fixture with students stopping at each stage plus messy records (offer without `submitted_on`, enrolled without visa case, withdrawn after offer, archived student, no-login student), every funnel (total and each row) is non-increasing and equals hand-computed counts. |
| AC2 | Reassignment: a student moved S1 → S2 counts, with all applications and stages, for S2 only; S1's row drops by exactly those numbers. |
| AC3 | Columns: each of the six equals hand-counted values; a second visa case on one application is not double-counted; a refused decision counts as a visa application, not an approval. |
| AC4 | Cohort: only students created within the inclusive UTC days count; boundary days included; open bounds unbounded; bad date and `to < from` → 422 with AGN-014's messages. |
| AC5 | Parity: with no dates, each staff row's Students / Applications / Offers / Enrollments equals the AGN-018 dashboard staff table. |
| AC6 | Authorization: Master 200; staff (with or without `can_view_reports`) 403; non-agent, super admin, pending/suspended agency 403; unauthenticated 401; a second org's data never appears. |
| AC7 | Rows: active zero-count staff listed; deactivated with non-zero counts listed and marked; deactivated all-zero absent; Unassigned only when non-zero; empty org → zeros, 200. |
| AC8 | No ids in the payload; `Cache-Control: private, no-store`. |
| AC9 | Navigation: Master sees "Staff Performance"; staff do not. |
| AC10 | UI: loading / empty / error (401, 403, other + Retry) / stale-response handling; range persists in the URL; funnel select switches; axe clean; tables keyboard-scrollable; no horizontal page scroll at 320 px. |
| AC11 | No regressions: AGN-018, portal, nav and AGN-0xx suites pass, changed only for the new nav item. |

## 8. Tests (written before the code)

- `apps/api/tests/test_agn_019_performance.py` — AC1–AC4, AC7 (seeding via `agn018_helpers`).
- `apps/api/tests/test_agn_019_security.py` — AC6, AC8.
- `apps/api/tests/test_agn_019_parity.py` — AC5.
- `apps/api/tests/test_agn_003_matrix.py` — the route's §6 row (Master ✅, staff ❌).
- `apps/web/tests/components/AgentPerformancePanel.test.tsx` — AC10 states, range, select, stale responses.
- `funnelStages` unit tests, placed beside the existing `lib` tests (location fixed in the plan).
- Navigation / `NavGroup` / `PortalPage.agentDashboard` tests — AC9 and the dashboard link.
- `apps/web/tests/e2e/agn-019-performance.spec.ts` — Master flow (filter, funnel switch, 320 px, axe); staff URL shows the 403 text and
  no nav item.

## 9. Regression risks and mitigations

1. `owner_join()` extraction from `staff_rows` → AGN-018 suites unchanged + AC5 parity.
2. Nav / `PortalPage` → one named flag; existing nav tests updated only for the new item; `agn-018` staff-sidebar E2E re-run.
3. Dashboard (all-time) vs page (filtered) → cohort meaning labelled; equal with no dates (AC5).
4. Table Students (active) vs funnel Students (incl. archived) → deliberate (P5), stated in the funnel note.
5. Query cost → seeded timing check; R-14 index only on evidence.

## 10. Out of scope

Branch filter (P2); owner-at-the-time attribution (P1); CSV export and the eight reports (ang-020); caching; staff access to any
performance data; changes to `AgentDashboardOut`, `services/portal.py`, models or migrations.

## 11. Documentation

`PRODUCT_DECISION_REGISTER.md` `DEC-SCOPE-063`; `ENHANCEMENT_BACKLOG.md` §AGN-019; `AGENT_CRM_BACKLOG.md` status table; `RTM.md`;
`RBAC_MATRIX.md` (Staff Performance row); `API_CONTRACT.md`; `SCREEN_CATALOG.md` / `screen_catalog.json`; `ROLE_NAVIGATION.md`;
`RAID.md` (branch filter deferred; R-14 measurement).
