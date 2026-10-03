# AGN-019 — Staff performance and student funnel — design

**Status:** design approved in-session 2026-10-03 (`EXPLICIT_APPROVAL` — answers to seven structured questions and three
design-section reviews), recorded as `DEC-SCOPE-065` (drafted as `DEC-SCOPE-063`; renumbered on merging `main` @ `39c119b`, where `063` is bdm-010 and `064` is AGN-022).
Source item: `docs/delivery/AGENT_CRM_BACKLOG.md` ang-019 (`DERIVED_BLUEPRINT`). Depends on AGN-018 (`DEC-SCOPE-062`), on `main`.
Branch: `feature/agn-019-staff-funnel`. **GATE-09:** no code until this spec and its plan are approved.

## 1. Requirement and acceptance

Business requirement (`EVID-015` §8, via the backlog): per-staff Students, Applications, Offers, Visa Applications, Visa Approvals,
Enrollments, and the funnel Students → Applications → Submitted → Offers → Visa → Enrolled.

Owner acceptance: funnel stages are monotonic non-increasing for a fixture; a reassigned student counts for the current owner (or the
owner at the time: spec decision — resolved as P1 below).

## 2. Decisions (`DEC-SCOPE-065`, answered by the owner 2026-10-03)

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

Order matters: **guards first, then the dates** (AGN-014's rule), so a refused caller never sees a 422 and cannot probe validation.

1. `get_current_user` → 401 when there is no valid session.
2. `membership = _gate(user)` → 403 for non-agents, super admin, and pending/suspended agencies or deactivated members
   (`agent_denial_reason`). Then `_require_master_action(user, "Only an agency Master can view staff performance")` → 403 for staff,
   with or without `can_view_reports`.
3. `start, end = _report_date(date_from, "date_from"), _report_date(date_to, "date_to")` (strict `YYYY-MM-DD`, else 422
   `"<name> must be a date (YYYY-MM-DD)"`); both given and `end < start` → 422 `"date_to must be on or after date_from"`;
   `end == date.max` → 422 `"date_to must be before 9999-12-31"` (the exclusive bound would overflow; AGN-014's guard). Query
   parameters are declared with `Query(None, description=...)` like `REPORT_DATE_FROM`/`REPORT_DATE_TO`; unknown parameters are
   ignored (FastAPI default).
4. `payload = await performance(db, user, start, end)`; `Cache-Control: private, no-store`; one log line `agent_performance.read`
   with `org_id`, `actor_id`, `filtered` (bool), `rows`, `duration_ms` — ids, flags and timing only; no names, codes or counts.
   No audit row (reads are not audited, `DEC-SCOPE-051` R7).
5. Registered in `main.py` beside `agent_dashboard.router`.

Errors use the app's existing shape (`{"detail": "<message>"}` via `HTTPException`) and carry no counts or names. `GET` only; no
other method is routed (405 from FastAPI).

### 5.1a Contract notes (API review)

- **Additive only.** A new route and new schemas; `AgentDashboardOut`, `/dashboard`, `/portal/...` are unchanged (Hyrum's law: the
  dashboard's field set, order and messages stay as they are).
- **Not a list endpoint, so no pagination.** One aggregate document per agency; `rows` is bounded by the org's staff count (the same
  unpaginated shape as AGN-018's `staff`). No pagination/sort/filter parameters beyond the date range — tests must not assert any.
- **Naming** follows the repo (snake_case fields and query params, as AGN-014 and AGN-018), not a new convention.
- **Same shape always:** counts are integers (zeros, never null); `unassigned` is null only when it has no counts; `date_from`/
  `date_to` echo the parsed bounds or null.
- **Percentages are not in the contract.** The client derives "% of students" from integers, so no float semantics are promised.
- **Idempotency/ETag:** not applicable (safe, read-only `GET`); no ETag is offered (`no-store`).
- **`total` is defined as the sum of `rows` and `unassigned`.** It can differ from the dashboard's headline KPIs, which also count
  applications not linked to an agency student record and count each application once across duplicate links (§4.3); the page
  labels it "All staff and unassigned".

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
  `seq`, as `staff_rows`), builds `rows` per P6 (staff only), `unassigned` from the `NULL` owner key (null when all zero), and `total` =
  the sum of `rows` and `unassigned`. Members of the org are matched by `AgentOrgMember.org_id == user.agent_membership.org_id`; owner
  keys belong to that org by construction (the cohort filter is `student_scope(user)`).

All user input reaches SQL only as bound parameters (SQLAlchemy expressions; no text SQL, no string building).

**Transactions and concurrency:** read-only — no writes, locks, commits or `FOR UPDATE`; the request's session is used as-is
(`get_db`), the same as `/dashboard`. Each statement is its own snapshot at READ COMMITTED. A reassignment or stage change committed
between the two statements can show one student in a different row in the table and the funnel for that one response; the next
request is consistent. Accepted (AGN-018 precedent); `as_of` tells the reader when the figures were taken. No isolation-level change
(the session has already read the user by then).
No migration: org filters use `ix_agent_students_agent_status` and `ix_agent_students_assigned_member`; `created_at` is a range filter
inside one org. `RAID.md` R-14 is re-measured with a seeded timing check; an index is proposed only if that shows a need.

### 5.3 Schema — `apps/api/app/schemas.py`

```python
class AgentFunnelOut(BaseModel):
    students: int; applications: int; submitted: int; offers: int; visa: int; enrolled: int

class AgentPerformanceCountsOut(BaseModel):
    students: int; applications: int; offers: int
    visa_applications: int; visa_approvals: int; enrollments: int
    funnel: AgentFunnelOut

class AgentPerformanceRowOut(AgentPerformanceCountsOut):
    code: str                 # the member code, e.g. ABC-S001
    name: str
    active: bool              # False = deactivated member (shown while they have counts)

class AgentPerformanceOut(BaseModel):
    """Master only. No ids, emails or phones: codes and names only (as AgentDashboardOut)."""
    date_from: date | None
    date_to: date | None
    rows: list[AgentPerformanceRowOut]
    unassigned: AgentPerformanceCountsOut | None   # top-level, like AgentDashboardOut.unassigned_students
    total: AgentPerformanceCountsOut
    as_of: datetime
```

API review change: "Unassigned" is a top-level field, not a pseudo-row with a null code and a flag, so every row has the same
meaning and no field is overloaded.

`AgentDashboardOut` and the `/dashboard` route are unchanged.

## 6. Frontend

### 6.1 Navigation — `apps/web/lib/navigation.ts`

`"performance"` added to `PORTAL_NAV["overseas/agent"]` after `"reports"`; `AGENT_NAV_LABELS.performance = "Staff Performance"`;
`/overseas/agent/performance` added to `STAFF_HIDDEN`. Staff sidebars are otherwise unchanged.

### 6.2 Page — `apps/web/components/PortalPage.tsx`

`agentPerformance = key==="overseas/agent" && section==="performance"`, added to the portal-payload 404 tolerance and to `main`
(renders `<AgentPerformanceSection user={user}/>`). `services/portal.py` gets one header-only `performance` section (the Tasks precedent; see §12 — review finding #1).

### 6.2a `apps/web/components/AgentPerformanceSection.tsx` (new, server)

The page frame, the `AgentTasksSection` pattern: `.portal-content` → `.portal-title` (eyebrow "Workspace", `<h2>Staff performance</h2>`,
muted intro "Students added in a period, and how far they got."). A Master renders `<AgentPerformancePanel/>`. Anyone else who opens
the URL (staff, or a non-agent role the portal admits) sees "Staff performance is available to agency Masters." and **no request is
made** — a friendlier message than a 403, while the server still refuses them (§5.1).

### 6.3 `apps/web/lib/agentPerformance.ts` (new)

`PERFORMANCE_URL = "/api/v1/workflows/overseas/agent/crm/performance"`, the `AgentPerformance` types (mirroring §5.3), and
`isPerformance(body)` (shape guard, like `isReport`), and `funnelStages(f)` → the six `{label, count, percent}` items, where
`percent` = `Math.round(count / students * 100)` and `null` when `students == 0` (shown as "—", never `NaN`). Range helpers are
imported from `lib/agentCommissionReport.ts` (`readRange`, `writeRange`, `reportQuery`, `DateRange`), not copied.

### 6.4 `apps/web/components/AgentPerformancePanel.tsx` (new, client)

**Reuse first.** The data flow is `AgentCommissionReportPanel`'s, kept the same so the two date-filtered agency pages behave alike:
`draft`/`applied` range, a `latest` request counter (older responses dropped), `requested` for Try again, `FormMessage`,
`detailMessage`, `SESSION_EXPIRED`/`SIGN_IN_PATH`, `.action-card`, `.field`, `.btn`, `.actions`. The table reuses `.table-scroll`
(focusable region, `aria-labelledby` its heading) and `table compact stack` with `data-label` (AGN-018 QA18-04/06). No new
dependency; the existing panels are not refactored (a shared hook would have one new consumer and would touch AGN-014's tested code).

**Visual hierarchy** (top to bottom): filter form → as-of line ("Figures as of 3 Oct 2026, 10:42") → **Funnel** (`<h3>`, the
headline) → **By staff member** (`<h3>`, the detail table). One `h2` from the section, `h3`s below, no skipped levels.

- **Form:** `<form aria-label="Staff performance filters">` with labelled From and To `type="date"` inputs and an Apply submit
  (Enter submits). Client check `to < from` → field error "'To' must be on or after 'From'." with focus moved to To; a server 422 is
  mapped to the field it names (`date_from`/`date_to` → 'From'/'To'), `aria-invalid` + `aria-describedby`, focus moved there; the
  figures on screen stay. Clearing both fields and applying shows all time (no separate Clear button, as AGN-014). Apply is
  `aria-disabled` while loading (not `disabled`, so focus is not lost).
- **Funnel:** a labelled `<select>` "Show funnel for": "All staff and unassigned" (default), then each row as "Name (CODE)" with
  "— deactivated" when inactive, then "Unassigned" when present; switching is client-side (no request) and the selection resets to
  the default when a new range loads. An `<ol aria-label="Student funnel for <selection>">` of six `<li>`s; each shows the stage label,
  the count and "N% of students" as text; a decorative `aria-hidden` bar (`.funnel-track`/`.funnel-fill`, width = `percent`%, a
  minimum visible width when count > 0, none at 0). The text carries the meaning, so colour is never the only signal. Note below:
  "Includes archived students and withdrawn applications. A student counts at every stage up to the furthest one reached."
- **Staff table:** `th scope="row"` = name, with the code and a text "Deactivated" tag in `.kpi-note` style (not colour alone);
  numeric `td`s with `data-label`; an "Unassigned" row (from `unassigned`) last when present, then an "All staff and unassigned" total row
  (from `total`). Numbers use
  `toLocaleString("en-IN")` (as the dashboard).
- **Loading / perceived performance:** first load shows `<p role="status">Loading staff performance…</p>` with `aria-busy` on the
  card; a later load keeps the current figures on screen with "Updating staff performance…" (no layout jump, no blank flash).
- **Empty:** when `total.funnel.students == 0`: "No students were added in this period." (filtered) or "Your agency has no students
  yet." (unfiltered), in place of the funnel; the staff table still lists active staff (zeros are information).
- **Errors:** 401 → `SESSION_EXPIRED` + "Sign in again" link (next = this page with its range); 403 → the server's message, figures
  cleared; 5xx, unrecognised body or network failure → "Couldn't load staff performance." / the offline text, with a "Try again"
  button that reloads the last requested range; all in `role="alert"`.
- **Responsive / mobile:** the form wraps (`.actions` flex-wrap); inputs and the select are full-width below 640 px; touch targets
  ≥ 44 px (the existing `.commission-report .btn` rule extended with `.staff-performance`); the table stacks below 640 px; the funnel
  rows are label/number on one line and the bar below, so nothing overflows at 320 px. Checked at 320 / 768 / 1024 / 1440.
- **Styles:** a few rules in `globals.css` under `.staff-performance` (`.funnel`, `.funnel-row`, `.funnel-track`, `.funnel-fill`)
  using the existing palette (`#e7edf6` track, `var(--blue)` fill, `var(--muted)` text) and spacing; no inline styles beyond the
  computed bar width (a number clamped to 0–100).
- **Size:** the panel stays under ~200 lines by keeping `Funnel` and `StaffTable` as small functions in the same file.

### 6.5 Dashboard link — `apps/web/components/AgentDashboardPanel.tsx`

The Master staff-table heading gains a "View staff performance" link to `/overseas/agent/performance` (`.kpi-link` style). No other
change.

## 6a. Security review (security-and-hardening)

Trust boundary: the HTTP request (session cookie + two query strings). Assets: the agency's per-staff figures and staff names.

| Concern | Design answer |
|---|---|
| Authentication | Existing session via `get_current_user`; no change to login, cookies or tokens. 401 without a session. |
| Authorization | `_gate` (agent, active agency, active member; super admin refused) then Master-only; checked server-side on every request. Nav hiding and the section's message are UX only. |
| IDOR | No path or query identifiers at all; the org comes from the caller's own membership. Responses carry no ids. A two-org test proves isolation (AC6). |
| Role escalation | Read-only; no parameter selects scope or role; `can_view_reports` grants nothing here; a deactivated Master is refused by `agent_denial_reason` on the next request. |
| Input validation | Two optional strict dates (regex + `fromisoformat`), `9999-12-31` refused; validated only after authorization. |
| SQL injection | SQLAlchemy expressions with bound parameters only. |
| XSS | React escapes text; names are rendered as text; no `dangerouslySetInnerHTML`; the only inline style is a clamped number. |
| CSRF | Not applicable: a safe `GET` that changes nothing; same-origin `fetch` with the existing cookie policy. |
| Token/session | Unchanged; `Cache-Control: private, no-store` keeps per-agency figures out of shared caches and the back/forward cache. |
| Secrets | None introduced. |
| Sensitive logs | Ids, a `filtered` flag, row count and timing only — no names, codes, dates or counts. |
| Data minimisation | Names and member codes only; no emails, phones or student identities. |
| Rate limiting | None added: the app has no read-endpoint limiter (only a DB-backed one on school transfer filings), and AGN-014/AGN-018 aggregates have none. Cost is bounded to one org and two indexed statements; the seeded timing check records it. A limiter would be a cross-cutting change outside AGN-019. |
| Audit | No audit row: reads are not audited (`DEC-SCOPE-051` R7), as `/dashboard` and the commission report. |
| Information disclosure | Errors are fixed strings with no counts; a refused caller gets 403 before any date validation. |

## 7. Acceptance criteria

| ID | Criterion |
|---|---|
| AC1 | Monotonic: on a fixture with students stopping at each stage plus messy records (offer without `submitted_on`, enrolled without visa case, withdrawn after offer, archived student, no-login student), every funnel (total and each row) is non-increasing and equals hand-computed counts. |
| AC2 | Reassignment: a student moved S1 → S2 counts, with all applications and stages, for S2 only; S1's row drops by exactly those numbers. |
| AC3 | Columns: each of the six equals hand-counted values; a second visa case on one application is not double-counted; a refused decision counts as a visa application, not an approval. |
| AC4 | Cohort: only students created within the inclusive UTC days count; boundary days included; open bounds unbounded; bad date, `to < from` and `date_to=9999-12-31` → 422 with AGN-014's messages. |
| AC5 | Parity: with no dates, each staff row's Students / Applications / Offers / Enrollments equals the AGN-018 dashboard staff table. |
| AC6 | Authorization: Master 200; staff (with or without `can_view_reports`) 403; non-agent, super admin, pending/suspended agency, deactivated Master 403; unauthenticated 401; a refused caller with an invalid date still gets 403, not 422; a second org's data never appears. |
| AC7 | Rows: active zero-count staff listed; deactivated with non-zero counts listed and marked; deactivated all-zero absent; `unassigned` null when all zero; `total` = sum of rows + unassigned; empty org → zeros, 200. |
| AC8 | No ids, emails or phones in the payload; `Cache-Control: private, no-store`; the log line has no names, codes or counts. |
| AC9 | Navigation: Master sees "Staff Performance"; staff do not; staff opening the URL see the Masters-only message and no request is made. |
| AC10 | UI: first-load and updating states (figures kept); empty (filtered / unfiltered); errors (401 sign-in link, 403 message, 5xx/offline + Try again); 422 and client range errors on the right field with focus; stale responses dropped; range persists in the URL; funnel select switches without a request and resets on a new range; "—" instead of a percentage when there are no students; axe clean; keyboard-only operable; tables keyboard-scrollable; no horizontal page scroll at 320 px. |
| AC11 | No regressions: AGN-018, portal, nav and AGN-0xx suites pass, changed only for the new nav item. |

## 8. Tests (written before the code)

- `apps/api/tests/test_agn_019_performance.py` — AC1–AC4, AC7 (seeding via `agn018_helpers`).
- `apps/api/tests/test_agn_019_security.py` — AC6, AC8.
- `apps/api/tests/test_agn_019_parity.py` — AC5.
- `apps/api/tests/test_agn_003_matrix.py` — the route's §6 row (Master ✅, staff ❌).
- `apps/web/tests/components/AgentPerformancePanel.test.tsx` — AC10 states, range, select, stale responses.
- `apps/web/tests/components/AgentPerformanceSection.test.tsx` — Master renders the panel; staff get the message and no fetch (AC9).
- `funnelStages` / `isPerformance` unit tests, placed beside the existing `lib` tests (location fixed in the plan).
- Navigation / `NavGroup` / `PortalPage.agentDashboard` tests — AC9 and the dashboard link.
- `apps/web/tests/e2e/agn-019-performance.spec.ts` — Master flow (filter, funnel switch, 320 px, axe); staff URL shows the Masters-only message (and the API returns 403 to a direct call) and
  no nav item.

## 9. Regression risks and mitigations

1. `owner_join()` extraction from `staff_rows` → AGN-018 suites unchanged + AC5 parity.
2. Nav / `PortalPage` → one named flag; existing nav tests updated only for the new item; `agn-018` staff-sidebar E2E re-run.
3. Dashboard (all-time) vs page (filtered) → cohort meaning labelled; equal with no dates (AC5).
4. Table Students (active) vs funnel Students (incl. archived) → deliberate (P5), stated in the funnel note.
5. Query cost → seeded timing check; R-14 index only on evidence.

## 10. Out of scope

Branch filter (P2); owner-at-the-time attribution (P1); CSV export and the eight reports (ang-020); caching; staff access to any
performance data; changes to `AgentDashboardOut`, `services/portal.py` (beyond its header-only `performance` section), models or migrations.

## 11. Documentation

`PRODUCT_DECISION_REGISTER.md` `DEC-SCOPE-065`; `ENHANCEMENT_BACKLOG.md` §AGN-019; `AGENT_CRM_BACKLOG.md` status table; `RTM.md`;
`RBAC_MATRIX.md` (Staff Performance row); `API_CONTRACT.md`; `SCREEN_CATALOG.md` / `screen_catalog.json`; `ROLE_NAVIGATION.md`;
`RAID.md` (branch filter deferred; R-14 measurement).

## 12. Implementation notes (2026-10-03, rulings during execution)

- §6.4 "markup copied": `AgentDashboardPanel.tsx` imports server-only code (`lib/api` → `next/headers`), so a client component cannot
  import from it. Its `TableRegion`, `headingId` and `n` moved unchanged to `components/AgentTableRegion.tsx`, used by both panels.
- §6.5: the "View staff performance" link sits below the dashboard's staff table, not inside its heading — a link in the `h3` would
  change the heading's accessible name, which names the table's region (AGN-018 QA18-06).
- §5.1: the three date checks became `report_range()` in `api/workflows.py`, shared with AGN-014's commission report.
- §8: no axe check in the E2E spec (`@axe-core` is not a dependency; no new dependencies) — accessibility is asserted through roles,
  names and keyboard use; an axe pass belongs to browser validation.
- Screen ID: `SCR-AGT-011`.
- Final review fix pass (fresh-context reviewer, 2026-10-03):
  - #1 (Critical) the page showed "Workspace not found": PortalPage treats a missing portal payload as 404 for non-Super-Admins, so
    §6.2's "no new section" was wrong. Fixed with a header-only `performance` section in `services/portal.py` (no figures), the
    Tasks/Notifications precedent; tests `test_agn_019_security.py::test_portal_section_is_a_header_for_both_roles`,
    `PortalPage.agentPerformance.test.tsx`.
  - #2 (Important) the staff table was hidden for an agency with no staff rows; it now shows whenever there are rows or an Unassigned row.
  - #3 (re-graded Important) the visa summary is limited to the caller's agency applications (it grouped every agency's cases).
  - #5/#6 (re-graded Important) Review Focus 2 and 3 now have their own tests, each proven by a deliberate mutation.
