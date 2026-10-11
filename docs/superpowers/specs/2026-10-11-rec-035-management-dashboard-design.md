# rec-035 — Management dashboard, recruiter business view (design)

Status: DRAFT, built under the user's standing instruction to proceed on recommended answers (2026-10-11). Every MGn default below is
**UNVERIFIED** until confirmed and is registered as a `DEC-SCOPE` (number taken after merging `main`).

## 1. Sources and authority
- `EVID-018` §26 "Management Dashboard" (L1007–L1034: "The CEO/Manager should get one view": 7 totals, Top Companies, Top Job
  Categories; the counts and company names are illustrative) — `DERIVED_BLUEPRINT`.
- Backlog `rec-035` + Appendix B M1–M9 (`DERIVED_WORKBOOK`): AC "top companies are ordered by joined count (ties by name); top job
  categories are by open requirements or hires (Q-25)"; negative: a recruiter → 403; edge: no data.
- Builds on rec-032 (`DEC-SCOPE-180`, `services/recruiter_metrics.py`, the single source of counts) and rec-033 (`DEC-SCOPE-182`, PF1 roles,
  PF2 credit, PF3 period). Q-25 (meanings, roles) is still open → answered by the recommended defaults below.

## 2. Intent
The CEO (`super_admin`) or a placement manager opens **Management Dashboard** and sees, on one page, the recruiter business at a glance:
seven totals, the top companies by hires and the top job categories, for a period (the current IST month by default). A recruiter (and
every other role) is refused (403).

## 3. Recommended defaults (MG1–MG8, UNVERIFIED)
| # | Topic | Default |
|---|---|---|
| MG1 | Roles (Q-25) | rec-033 PF1: `placement_manager` (their direct reports + the Unassigned queue), `super_admin` and `it_admin` (every recruiter + Unassigned). `placement_team` and every other role → 403. |
| MG2 | Scope | rec-033 PF2 owners: company figures (M1, M2) by the company's assigned recruiter; requirement figures (M3–M9) by the requirement's assigned recruiter, else its company's; no owner = Unassigned (in scope). So M6 / M7 equal rec-033's Total Selected / Joined for the same period. |
| MG3 | Period | rec-033 PF3 (`from`/`to` IST dates, default the 1st of the month → today, tel-023's rules and messages). M1–M4 and M9 are snapshots now; M5–M8 count the period. |
| MG4 | M1 Companies (Q-25) | Non-archived companies whose stage is past New Lead (Lost included: still a company the business has worked). |
| MG5 | M2 Active Recruiters (Q-25) | Active company contacts (rec-004: the §2 "recruiter" is the person at the company) at active companies (D5: not archived, ≥ 1 requirement not On Hold / Closed / Cancelled). Not internal `placement_team` users — "Recruiter" in EVID-018 is the hiring side (D1 "Recruiter Leads", D3 "Hot Recruiters" are companies). |
| MG6 | M3 / M4 / M5 | M3 = requirements not On Hold / Closed / Cancelled (D5's open set). M4 = distinct candidates with ≥ 1 application not Joined / Rejected / Withdrawn. M5 = interviews scheduled in the period, any status ("scheduled + completed"). |
| MG7 | M8 Top Companies | Companies by Joined count (rec-033 P8: offers joined with actual joining date in the period), descending, ties by name (case-insensitive), top 10, ≥ 1 hire. |
| MG8 | M9 Top Job Categories (Q-25) | Job categories by open requirements (M3's set), descending, ties by name, top 10, ≥ 1 open requirement (the backlog's primary reading; inactive categories still count — their requirements are live). |

## 4. API — `GET /api/v1/recruiter/management?from&to`
Response `{date_from, date_to, totals: {companies, active_recruiters, open_requirements, candidates_in_pipeline, interviews, selected,
joined}, top_companies: [{id, name, joined}], top_categories: [{id, name, open_requirements}]}`. `Cache-Control: no-store`.
Errors: 401 anonymous; 403 other roles; 422 bad date or range rules. Read-only; no audit. Performance: the people lookup, one statement of
seven scalar sub-selects, two grouped top-10 statements → a fixed statement count.

## 5. Web
- `/recruiter/manager/business` — nav: manager "Management Dashboard"; super_admin and it_admin "Recruiter Management Dashboard".
- A GET period form (From, To; keyed, `autoComplete="off"`), the seven totals as tiles (`metric-grid`), two ranked lists (`<ol>`) with
  their counts, each with an empty-state line ("No hires in this period yet." / "No open requirements with a job category."). 403 →
  `accessUnavailable`; 422 → the API's sentence; other failures → "The management dashboard is unavailable right now.".

## 6. Security
Server-side scope only (no client-chosen recruiter). Company names and counts only — no candidate PII. Parameters bound by SQLAlchemy.

## 7. Tests and plan
1. pytest `test_rec_035_management.py` (RED first): each total on fixtures as a delta for a fresh manager's team (shared DB); M6/M7 = rec-033
   Total; top lists ordered by count then name in an isolated past period / fresh categories; roles (recruiter 403, hr_team 403,
   super_admin / it_admin 200); period 422; no-store; fixed statement count; empty past period → zeros and empty lists.
2. Service `recruiter_metrics.management` + route in `api/recruiter_dashboard.py` (GREEN).
3. vitest: lib params/query/error; panel tiles, lists, empty states, error; page role gate; nav lists.
4. Playwright e2e `rec-035-management.spec.ts`: manager opens the page from the menu, 7 tiles, M7 equals rec-033's Total Joined; recruiter refused.
5. Docs: DEC-SCOPE, API §, RBAC §, backlog status (after merging `main`).
