# itc-032 — Management IT reports and dashboard filters (design)

**Status:** builder's design under the owner's "proceed with the recommended answers" (backlog Q-01: all phases approved for build in
waves). Every call marked **Rn** is `NEEDS_CONFIRMATION`. Source: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-032 (PDF §8 Management
dashboard, §12 AC10; PDF classified `UNVERIFIED`). Dependencies merged: itc-013 (`DEC-SCOPE-346`), itc-017 (`DEC-SCOPE-368`), itc-023
(`DEC-SCOPE-352`), itc-027 (`DEC-SCOPE-354`), itc-031 (`DEC-SCOPE-359`), itc-005 (`DEC-SCOPE-362`).
**Decision:** `DEC-SCOPE-369`. No migration. API §12JO (additive). RBAC §2.269 (no new grant).

## Intent
Management and the IT Admin need one IT view answering "how many leads came in and from where, how many converted, what was billed,
collected and is still owed, how the students attend and complete, how they are placed, and what the team did" — with the **same five
filters** (course, batch, owner, date range, status) on every report, a written definition for every figure, and every figure tying out
to the rows below it (AC1/AC2).

## Non-goals
- No stored or materialised figures (measure first: every report is a fixed number of queries); no new write path; no migration.
- No change to the existing management dashboards (mgmt-007 IT revenue, mgmt-016 funnel, mgmt-017 training), itc-017 or itc-030.
- No student or lead names, emails or phones (mgmt-007 IR11 / Q-32 precedent): rows carry codes, course, batch and staff names.
- No commission (IT has none; the accountant never sees university commission — unchanged).

## Builder's calls (`NEEDS_CONFIRMATION`)
- **R1 — reports.** Six tabs, two populations:

  | Report | Population ("the cohort") | Groups | Drill-down rows |
  |---|---|---|---|
  | `funnel` | IT leads (`division='it'`, not merged) **created** in the range | course × source | one per lead |
  | `conversions` | the same leads | course | one per **converted** lead |
  | `activity` | calls logged, follow-ups completed and conversions on IT leads, **at** a time in the range | staff member | one per event |
  | `revenue` | IT enrolments (not `pending_consent`/`rejected`) **enrolled** in the range | course | one per enrolment |
  | `training` | the same enrolments | course | one per enrolment |
  | `placement` | the same enrolments | course | one per enrolment |

  A cohort (not activity within the period) is used for leads and enrolments, so every figure of a report counts the same records and
  sums exactly to its rows (AC1). The lead "funnel" is the cohort's current stage distribution (no stage-history replay: the history
  only exists for some moves).
- **R2 — the five filters apply everywhere (AC2), one rule each:**
  - **Course** — a lead through its product's course (`tel_products.program_id`); an enrolment through its batch's course.
  - **Batch** — an enrolment's batch; a lead is not in a batch, so lead reports narrow to the batch's course (itc-030's rule).
  - **Owner** — a lead's owner; an activity event's actor; an enrolment's student's IT counselor (itc-003 link).
  - **Date range** — the cohort anchor above (inclusive IST days). Default: this IST month to today. From after to → 422; more than 366
    days → 422, so a whole financial year (or any range across 31 March) is allowed and is never split by year (backlog E).
  - **Status** — a lead stage (`lead_stages.STAGES`) on lead reports (the lead's current stage; activity: the stage of the lead acted on);
    an itc-031 lifecycle stage (`IT_LIFECYCLE_STAGES`, derived on read) on enrolment reports. A status from the other family → 422.
  - Unknown course / batch / owner, or a batch outside the chosen course → 422 with an actionable message. The owner list is the staff who
    own an IT lead, log a call on one, or counsel an IT student.
- **R3 — figure definitions (Appendix B where it speaks):**

  | Report | Figure | Definition |
  |---|---|---|
  | funnel | Leads | Cohort leads. |
  | funnel | Open / Nurture / Converted / Closed | Cohort leads now at an open stage before Converted / at Nurture / at Converted / at a closed stage. |
  | funnel | By stage | Cohort leads now at each stage (sums to Leads). |
  | conversions | Converted | Cohort leads with a conversion recorded (`converted_at`). |
  | conversions | Conversion rate | Converted ÷ Leads of the same cohort. |
  | activity | Calls / Connected calls | Calls logged in the range / of those, outcome not in `telecaller_metrics.NOT_CONNECTED`. |
  | activity | Follow-ups completed | Follow-ups marked done in the range (by `completed_by`). |
  | activity | Conversions | Leads converted in the range (by `converted_by`). |
  | revenue | Billed | Σ total payable (itc-013 fee account). |
  | revenue | Collected | Σ confirmed payments to date (`paid`/`succeeded`; Appendix B "Paid to date"). |
  | revenue | Outstanding | Σ positive balances of **active** enrolments (Appendix B "Outstanding", itc-017 F5). |
  | revenue | Overdue | Σ owed installments due before today (IST) of active enrolments (itc-016). |
  | training | Attendance % | Σ attended ÷ Σ counted attendance of the cohort's seats (Appendix B, itc-021 policy). |
  | training | Completed / Completion % | Enrolments whose itc-031 training component is Completed (status completed or certificate issued) ÷ enrolments. |
  | placement | Placed / Interview / HR screening / Resume submitted / Not placed / Not started | The itc-031 stage Placed or Not placed, else its placement component, else Not started. |
- **R4 — who reads.** Operational reports (funnel, conversions, activity, training, placement): `partner`, `super_admin` (the operational
  tier) and the IT Admin (`it_admin`, division IT). Revenue: `partner`, or an itc-017 accounts reader (IT/all-division user with
  `payments.view`: the IT Admin, the accountant, super_admin). Anyone else 403 "You do not have access to this IT report".
  `GET …/reports` returns the reports the caller may open, so the accountant's page shows the Revenue tab only.
- **R5 — export.** `GET …/{report}/export`: every drill-down row of the filtered report as CSV (≤ 10,000, else 422 "Narrow the
  filters"), each text cell through `_safe_cell` (formula injection), audited `management.it_reports.export` (report + filters + row count,
  no figures).
- **R6 — pages.** One body, two shells (itc-017 pattern): `/management/it-reports` (Students pillar "IT reports"; Finance pillar "IT revenue
  & outstanding" → `?report=revenue`; super admin nav "Management IT reports") and `/it/admin/management-reports` (IT Admin nav).

## API (API_CONTRACT §12JO)
- `GET /api/v1/management/it/reports` → `{reports: [{key, label}]}` (the caller's).
- `GET /api/v1/management/it/reports/{report}` → `{report, filters, options{courses, batches, owners, statuses}, definitions[{key, label,
  definition}], totals, groups[], items[], total, limit, offset}`; `limit` 1–200 (50), `offset`. Unknown report 404.
- `GET /api/v1/management/it/reports/{report}/export` → `text/csv`, `it-<report>-<today>.csv`.

`totals` are over the whole filtered cohort; `Σ groups = totals`; `total` (the drill-down count) equals the report's headline count
(leads, converted, events, enrolments), and money/attendance sums of the rows equal the totals (AC1, by construction: one row list feeds
all three).

## UI
Tab strip (links, `aria-current`); a GET filter form — Course, Batch, Owner, Status (the tab's family), From, To, Apply / Clear — so refresh,
Back and shared links keep the view; the course, batch, owner and dates carry across tabs (status only within its family). Total tiles;
"What these figures mean" (a `<details>` list of the definitions); the groups table with a "Show rows" link per course row (sets the course
filter: the drill-down); the rows table (stacks on a phone) with paging and "Download CSV". Empty: "Nothing matches these filters."
422 text above the form; other failures an "unavailable" panel; 401/403 the access card.

## Acceptance
1. Each figure ties out to its drill-down (totals = Σ groups = Σ rows; headline count = rows total).
2. All five filters apply on every report (each narrows each report; wrong-family status and unknown values 422).
E. A range across 31 March (and a full financial year) is accepted and counted whole. − A counselor or student → 403; the accountant →
403 on operational reports, 200 on revenue.

## Plan (TDD)
1. `services/management_it_reports.py` + `api/management_it_reports.py`, tests `tests/test_itc_032_management_it_reports.py` first (access
   matrix, filters 422, each report's figures and tie-out, each filter on each report, FY range, export + audit + injection).
2. Frontend: `lib/itReports.ts`, `components/ItReportsWorkspace.tsx`, `components/ItReportsPage.tsx`, two pages, nav entries; vitest.
3. Playwright e2e `itc-032-management-it-reports.spec.ts`; docs (DEC-SCOPE-369, API §12JO, RBAC §2.269, backlog status, RTM).

## Regression risks
`test_mgmt_*` (unchanged services; nav entries added), management nav vitest (`pillarsFor`/`managementNavFor` lists), IT Admin nav tests.
