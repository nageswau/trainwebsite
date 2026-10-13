# mgmt-025 — Recruitment dashboard — design

- **Feature:** `mgmt-025` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-025). It depends on mgmt-003 (PR #244), rec-033 (PR #239) and
  rec-035 (PR #241). All three are merged on `main`, so the backlog's "not available yet" state never applies.
- **Evidence:** `EVID-017` §21 "Recruitment Dashboard" (lines 851–879, `DERIVED_BLUEPRINT`) lists 11 Recruiter KPIs (Recruiters,
  Employer partners, New companies, Job openings, Internship openings, Candidates, Interviews, Selections, Joining, Placement rate,
  Revenue) and the company pipeline Lead → Meeting → Requirement → Candidate → Interview → Selection → Joining.
- **Built on:** Management M4/M13 (`DEC-SCOPE-186`); rec-035 M1–M7 (`recruiter_metrics.management`); rec-033 P4/P8
  (`recruiter_metrics.performance`); rec-034 B4 (new companies); rec-005 company stages (`recruiter_stages.py`); mgmt-003 S15
  (Recruiters); mgmt-008 RR2/RR7 (recruitment revenue, placement %).
- **Decision:** one new DEC-SCOPE, numbered at merge. RC1–RC12 below are **recommended defaults, `UNVERIFIED`**. They follow the
  owner's instruction to proceed with recommended answers.

## 1. Intent

The operational tier (partner, super_admin) sees the recruitment business on one page for a period: the 11 §21 KPIs and the company
pipeline. The page reads through the Recruiter CRM's own counts, so its totals equal rec-035's (AC). Only the partner, as the finance
tier, sees revenue. The page is read-only and stores nothing.

## 2. Decisions (RC1–RC12)

| # | Point | Answer |
|---|---|---|
| RC1 | Period | `date_from` / `date_to` (IST dates) follow rec-033/035's range rules (`telecaller_performance.date_range`): the default is the 1st of this month to today; the start may not be after the end; the range may not end in the future or run past 366 days. A violation is a `422` carrying the rule's words |
| RC2 | Scope | Company-wide, the same as rec-035 for an administrator: every recruiter plus Unassigned. `recruiter_metrics.management` takes the allowed roles as a keyword argument (default MG1's), the same pattern mgmt-008 RR10 used for `performance` |
| RC3 | KPIs from rec-035 (AC) | Employer partners = M1 companies; Candidates = M4 candidates in the pipeline (now); Interviews = M5, Selections = M6, Joining = M7 (in the period) |
| RC4 | Recruiters | S15 (`management_metrics.recruiters()`): active `placement_team` users with a recruiter profile. This matches the snapshot and mgmt-008 |
| RC5 | New companies | Companies that first moved past "Interested" in the period. This is rec-034 B4 counted for any actor, so a company is new once, whoever moved it. The B4 sub-query is shared, not copied |
| RC6 | Job / Internship openings | rec-035 M3 (open requirements) split by `employment_type`: `internship` counts as an Internship opening; any other value, or none, counts as a Job opening. The two always sum to M3 |
| RC7 | Placement rate | Joining ÷ candidates sourced in the period (rec-033 P4) × 100, to one decimal. This is mgmt-008 RR7, so the two pages agree for the same range. It is `null` ("—") when nobody was sourced |
| RC8 | Revenue | Finance tier only (`can_view_finance`; on this page that is the partner): Σ counted `ledger.lines()` recruitment income over the period, the same total as mgmt-008. For the super admin `revenue_visible` is false, `revenue` is `null`, and the ledger is never queried |
| RC9 | Company pipeline | Live companies (not archived, not lost), grouped by their current rec-005 stage. Lead = New Lead / Contacted / Interested; Meeting = Meeting Scheduled / Requirement Discussion; Requirement = Requirement Received / JD Received; Candidate = Candidates Sourcing / Profiles Shared; Interview, Selection and Joining = their own stages. Requirement Closed companies and lost companies are listed under the steps. All are counted now |
| RC10 | Access | Operational tier (`partner`, `super_admin`). The accountant and every other role get `403` ("Operational access required" for the accountant, "Management access required" for the rest); a signed-out caller gets `401` |
| RC11 | Navigation | Command Center: the Students "Recruitment" entry goes live (`/management/recruitment`), and People "Recruiters" links to `/management/recruitment#recruitment-kpis`. The super admin's sidebar gets "Management recruitment figures" |
| RC12 | Data exposure | Counts only: no names, no per-recruiter rows. Revenue follows RC8 |

## 3. API

`GET /management/recruitment?date_from&date_to` → `200`

```
{date_from, date_to, revenue_visible,
 kpis{recruiters, employer_partners, new_companies, job_openings, internship_openings, candidates, interviews, selections, joining,
      placement_rate, revenue},
 pipeline[{key, label, value}], requirement_closed, lost}
```

`revenue` is a decimal string, or `null` (RC8). `placement_rate` is a number or `null`. Pipeline keys are `lead`, `meeting`,
`requirement`, `candidate`, `interview`, `selection` and `joining`.

## 4. Web

`/management/recruitment` is server-rendered, with the period in the address (a GET form, like mgmt-019). The page shows the KPI
tiles in §21 order under `id="recruitment-kpis"`; Revenue is omitted for the super admin, and a note says it is for partners. The
company pipeline is an ordered funnel with Requirement Closed and Lost below it. A 401/403 shows the access card (`accessUnavailable`);
a 422 shows the API's message. The page has no empty state of its own: zero counts read as 0.

## 5. Tests

- **Backend** (`test_mgmt_025_recruitment.py`): access per role (partner, super_admin 200; accountant, recruiter 403; signed out 401);
  the 422 range rules; AC — rec-035's totals equal the KPIs (super_admin reads both for the same range); job + internship = rec-035's
  open requirements; placement rate = joined ÷ rec-033 candidates sourced; new companies counts a past-Interested crossing in the
  period exactly once; the pipeline groups a fresh company per stage and leaves lost and archived companies out; revenue for the
  partner equals mgmt-008's for the same month, and is `null` for the super admin. Re-run `test_rec_034*`, `test_rec_035*` and
  `test_mgmt_008*` after touching `recruiter_metrics`.
- **Web:** `managementRecruitment.test.ts` (filters/urls), `ManagementRecruitment.test.tsx` (tiles, "—", super-admin view, pipeline),
  the nav tests, and the e2e `mgmt-025-recruitment.spec.ts`.

## 6. Risks

- `recruiter_metrics.management` and the B4 sub-query serve rec-034/035: the keyword defaults to today's roles, and their tests are
  re-run.
- The stack DB is shared and never emptied, so company-wide figures are asserted as deltas or against the rec-035 endpoint read in the
  same test.
