# hrc-033: Operational recruitment dashboards -- design

**Decision:** `DEC-SCOPE-414` (builder's recommended calls, `NEEDS_CONFIRMATION`). **Source:** `HR_RECRUITMENT_CRM_BACKLOG.md` hrc-033, Appendix B
(`UNVERIFIED`, a requirements draft). **Depends on:** hrc-021, 024, 026, 028, 030, all merged.

## Intent

§14 asks for five operational dashboards -- recruitment funnel, vacancy, recruiter, placement officer, interview -- each filterable, each
figure defined, and each figure opening the records it counted. The AC: **every figure equals its drill-down count; the funnel is monotonic
for one cohort.**

## Non-goals

- hrc-034's three dashboards (skill demand, portal analytics, data quality).
- pob-028's nine-widget Placement Officer dashboard. This feature gives the shared metric source and hrc-033's figures only.
- Changing the existing recruiter tiles, performance, management recruitment or interview views. They keep their numbers and routes.
- Money. No figure or drill-down column carries compensation, fee or revenue.

## Design

### One figure, one predicate (D1)
`services/recruitment_dashboards.py` declares every figure once: key, label, definition, record kind and its SQL predicate. The figure's
value and its drill-down are built by **the same function** from that predicate, so they cannot disagree. Alternative rejected: adding
figures to `recruiter_metrics.dashboard` with separate list queries, which is how tile and list drift.

Record kinds: `candidate`, `job`, `application`, `interview`. Each row is one record, so `count(*)` is the figure (D2).

### The five boards (D3)

| Board | Figures |
|---|---|
| Funnel | Registered → Applied → Screened → Shortlisted → Profile shared → Interview → Selected → Joined |
| Vacancy | Total; status buckets (Not yet open, Open, On hold, Selected or filled, Closed, Cancelled); open-job ageing bands 0-15, 16-30, 31-60, 60+ |
| Recruiter | Website registrations, assigned, unassigned, contacted, contact SLA met/pending/breached; open requirements, candidates added, interviews scheduled, selected, joined |
| Placement officer | Open requirements, candidates assigned, not yet contacted, candidates added, interviews upcoming, awaiting update, selected, joined |
| Interview | Upcoming, awaiting update, on hold, results awaiting approval (right now); held, cancelled, no-show (in the period) |

### Definitions (D4, adding to Appendix B)

- **Funnel cohort** = the candidates registered (`Candidate.created_at`) in the chosen IST range, in the pool (`pool_filter`), not archived. One
  calendar month is one Appendix B cohort. **Stage reached** = the candidate has an application whose current status or status history is
  that stage *or any later one*, so a skipped stage still counts and each stage is a subset of the one before: monotonic by construction.
  A rejected or withdrawn candidate keeps the stages already reached. An employer or job filter restricts the cohort to candidates with an
  application on it, and every stage to those applications.
- **Applied** = at least one `JobApplication`, whoever added it. A `CareerApplication` alone is an intake row and not a job-specific application.
- **Vacancy opened on** = `requirement_date`, else the IST date of `created_at` (`Job` has no `opened_on`). A future date ages as 0.
- **Vacancy buckets** partition all 13 `JOB_STATUSES`: Not yet open (`new`, `pending_approval`), Open (`JOB_OPEN_STATUSES`), On hold, Selected or filled
  (`selected`, `joined`, `filled`), Closed, Cancelled. Ageing bands partition Open.
- **Contact SLA** = hrc-025's `contact_sla` and `first_contact` expressions, unchanged (24 h, Q-26). Met + pending + breached = registrations.
- **Results awaiting approval** = interviews with an `InterviewResult` in `pending_approval` (Appendix B; `interview_id` is unique). The outcome is never shown.
- **Upcoming / awaiting update / on hold** = `interviews.views(now)`, so they equal the Interviews page.
- **Selected / joined in the period** = the first application history row into that status inside the period's scope (rec-032's `entered`).

### Dates (D5)
`telecaller_performance.date_range` rules: default this IST month to today, at most 366 days, never future. The Vacancy board is a snapshot:
with no dates it covers all vacancies, because a one-month default would always leave 60+ empty; with dates it covers vacancies opened in
the range. Queue figures on the Interview, Recruiter and Officer boards are "right now" and say so in their definition.

### Filters (D6)
`from`, `to`, `owner`, `employer`, `job` are all ANDed with the caller's scope, so a value outside it yields zero, never a 403 that reveals
it exists. Owner means the candidate's owner on candidate figures and the requirement's owner (assigned recruiter, else its company's, PF2)
on the others. On the Placement Officer board it means the officer.

**Branch is not offered as a working filter.** No job, candidate or recruiter records a branch (mgmt-016 M10, hrc-002 Q-04, hrc-024 record the
same); `company_branches` is unlinked from jobs. The form shows it disabled with that reason. `NEEDS_CONFIRMATION`: Q-04. A chosen employer or job also binds candidate figures to the caller's requirement scope.

### Access (D7)
New catalogue resource `reports.recruitment` (`view`, `download`), seeded by migration `0292_recruitment_report_grants` (a seed only, no schema):
`placement_team`, `placement_manager`, `hr_manager`, `placement_officer`, `it_admin`, `partner`; `super_admin` implicitly. `reports.placement` is
not reused, because it also opens student rows in the report library.

The grant opens the route; scope is per role, and a role with a grant but no defined scope is refused:

| Role | Requirements | Candidates |
|---|---|---|
| `placement_team` | `caller_scope` | `mine` + unassigned (hrc-025 N2) |
| `placement_manager` | `caller_scope` (team + unassigned) | the whole pool (hrc-025 N2) |
| `placement_officer` | `caller_scope(officers=True)`; on the officer board, only where they are the officer | `mine`, including on application and interview records |
| `hr_manager`, `it_admin`, `partner`, `super_admin` | everything | everything |

### API (D8) -- `/api/v1/recruiter/recruitment-dashboards`

- `GET /{board}`: sections of figures, the applied filters, the scoped filter options. `no-store`.
- `GET /{board}/drill/{figure}?limit&offset`: the same filters; `total`, `columns`, `items`. Unknown figure 404.
- `GET /{board}.csv` and `.xlsx`: `reports.recruitment.download`, the figures with their definitions, one audit row committed before the file
  is returned. Cells pass `to_csv`'s formula guard.

Fixed query count: one statement for all figures, one per option list, plus the scope's. Reads only.

### Drill-down rows (D9)
Identifiers, names, status and dates only: no phone, email, compensation or result. A decided interview reads Held, so its status cannot reveal the outcome. A row links to its record only when the caller's role can
open that screen (`candidates.READERS`; requirement scope), mirroring hrc-025's `can_open`.

### Frontend (D10)
`/recruiter/recruitment-dashboards/[board]` is server-rendered from a GET form, so refresh, back and shared links keep the state. Tabs for the five
boards, tiles as links to `?drill=<figure>`, a labelled table with paging, `SpreadsheetButtons` for the download grant, and existing classes
(`kpi-grid`, `pipeline-funnel`, `table compact stack`). A nav entry in each affected role's menu, tagged with the resource.

## Risks

Regression: rec-032…035 and mgmt-016 are untouched because their services are not edited. hrc-002's key test and the rec-038 route matrix get rows.
Performance: subqueries use existing indexes; drill pages are limited to 100.

## Plan

1. Catalogue key, grant defaults, migration 0292 and its test.
2. Service plus board and drill tests (tie-out for every figure, monotonic funnel, partitions, scope, empty period, query count).
3. Router, export, rec-038 rows.
4. Web lib and component tests, pages, navigation.
5. e2e and browser QA at three widths. 6. Register docs (DEC, API, RBAC, RTM, backlog, Appendix B).
