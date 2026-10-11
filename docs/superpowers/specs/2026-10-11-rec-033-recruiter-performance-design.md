# rec-033 — Recruiter performance dashboard (design)

Status: DRAFT, built under the user's standing instruction to proceed on recommended answers (2026-10-11). Every PFn default below is
**UNVERIFIED** until confirmed and is registered as `DEC-SCOPE-181` (number re-checked against `main` before merge).

## 1. Sources and authority
- `EVID-018` §24 "Recruiter Performance Dashboard" (L942–L971: 8 KPIs + 7 ratios, "Management should see") — `DERIVED_BLUEPRINT`.
- Backlog `rec-033` + Appendix B P1–P15 (`DERIVED_WORKBOOK`); R2 (own-assignment scope, `EXPLICIT_APPROVAL` 2026-10-07).
- Q-25 (metric meanings, roles) and Q-26 (CSV export) are still open → answered by the recommended defaults below.
- Builds on rec-031 (`DEC-SCOPE-176`) and rec-032 (`DEC-SCOPE-180`, `services/recruiter_metrics.py`, the single source of counts).

## 2. Intent
A placement manager opens **Recruiter Performance** and sees, for a period (the current IST month by default), the fifteen §24 figures
for their team, a table of the same figures per recruiter (with a Total row equal to the sum of the rows, AC2), and can drill down to
one recruiter. `super_admin` and `it_admin` see every recruiter. Ratios whose denominator is 0 show "—" (AC1). The table downloads as CSV.
A recruiter (and every other role) is refused (403).

## 3. Recommended defaults (PF1–PF9, UNVERIFIED)
| # | Topic | Default |
|---|---|---|
| PF1 | Roles (Q-25) | `placement_manager` (direct reports + the Unassigned row), `super_admin` and `it_admin` (every recruiter + Unassigned; `it_admin` because recruiters are IT staff, R2 / `recruiter.ADMIN_ROLES`). `placement_team` and every other role → 403. |
| PF2 | Credit (AC2) | Every figure is credited to exactly one owner so the Total is the sum of the rows. Company figures (P1, P2): the company's assigned recruiter. Requirement figures (P3–P8, P14, P15): the requirement's assigned recruiter, else its company's (rec-007's scope rule). No owner → the **Unassigned** row. Credit follows today's assignment (event-actor credit is rec-034's, Q-25). |
| PF3 | Period | `from`/`to` IST dates; default the 1st of the current IST month → today; `from ≤ to ≤ today`, ≤ 366 days (tel-023's `date_range`, same messages). Instants are the IST day bounds (half-open). |
| PF4 | P2 at period end | A company not archived before the period end with ≥ 1 requirement created before the end whose status at the end is not On Hold / Closed / Cancelled. Status at the end = the latest `job_status_history` row before the end (else the current status); when the period ends today it is the current status, so P2 = rec-032's D5 for the same scope. |
| PF5 | P6 Interviews | Interviews that took place in the period: `scheduled_at` in the period and status Completed, Selected or Rejected (an outcome recorded). |
| PF6 | P9 Selection % (Q-25) | P7 ÷ P4 × 100 (the backlog's primary reading). |
| PF7 | P14 / P15 | P15 = distinct requirements with a status-history row → Closed in the period. P14 = mean whole days from the requirement date (else its IST created date) to its last Closed in the period (IST date), over P15's requirements. |
| PF8 | Rounding | Percentages 1 decimal, ratios 2 decimals, days 1 decimal; `null` when the denominator is 0 (shown "—"; blank in CSV). Total ratios are recomputed from the Total counts. |
| PF9 | CSV (Q-26) | `GET /recruiter/performance.csv` = the table (same rows, Unassigned and Total last). Counts and recruiter names only — no candidate data, so nothing to mask. One `recruiter_performance.export` audit row, committed before the file (fail closed). |

## 4. Figures (Appendix B, as built; period [start, end))
| ID | Key | Definition |
|---|---|---|
| P1 | `recruiter_leads` | companies created in the period |
| P2 | `active_companies` | PF4 |
| P3 | `requirements` | requirements created in the period |
| P4 | `candidates_sourced` | applications created in the period (= D7) |
| P5 | `profiles_shared` | `profile_share_items` created in the period (= D8) |
| P6 | `interviews` | PF5 |
| P7 | `selected` | distinct applications with a history row → Selected in the period (= D10) |
| P8 | `joined` | offers `joining_status = joined`, actual joining date in [from, to] (= D11) |
| P9 | `selection_pct` | P7 ÷ P4 × 100 |
| P10 | `joining_pct` | P8 ÷ P7 × 100 |
| P11 | `profile_to_interview` | P6 ÷ P5 |
| P12 | `interview_to_selection` | P7 ÷ P6 |
| P13 | `selection_to_joining` | P8 ÷ P7 |
| P14 | `avg_closure_days` | PF7 |
| P15 | `requirements_closed` | PF7 |

## 5. API — `GET /api/v1/recruiter/performance?from&to&recruiter`
Response `{date_from, date_to, recruiter: {id, full_name} | null, columns, items: [row], totals: row}`; a row is
`{user_id | null, full_name, active, status, <P1–P15>}` (Unassigned: `user_id` null, "Unassigned"). With `recruiter=<id>` (drill-down) the
items are that recruiter only and the totals equal their row. `Cache-Control: no-store`.
Errors: 401 anonymous; 403 other roles; 404 recruiter outside the caller's scope or not a recruiter; 422 bad uuid/date or range rules.
Performance: the role/scope lookups, one row query, then **one** `UNION ALL` statement of grouped counts → a fixed statement count.

## 6. Web
- `/recruiter/manager/performance` (manager → `RECRUITER_MANAGER_NAV`; super_admin → `SUPER_ADMIN_NAV`; it_admin → IT admin nav).
  Nav entries: manager "Performance", super_admin "Recruiter Performance", it_admin "Recruiter Performance".
- A GET filter form (From, To, Recruiter), the fifteen figures as tiles (the `metric-grid` pattern), the per-recruiter table (row name →
  drill-down; Total footer) and the CSV download (`ReportDownloadButton`). 403 → `accessUnavailable`; 422 → the API's sentence; other
  failures → "Recruiter performance is unavailable right now."; no recruiters → an empty-state line.

## 7. Security
Server-side scope only; the `recruiter` filter only narrows (checked against the caller's team). Read-only apart from the export audit.
No PII beyond staff names. Parameters bound by SQLAlchemy.

## 8. Tests
- pytest `test_rec_033_performance.py`: each figure on fixtures for a fresh manager's team (AC1 ratios, "—" = null on zero); Total = Σ
  rows incl. Unassigned (AC2); drill-down; PF4 at a past period end; PF7 reopen-and-close; period validation; roles (recruiter 403,
  hr_team/bdm 403, it_admin/super_admin 200, out-of-team 404); CSV + audit; no-store; fixed statement count; empty period → zeros/nulls.
- vitest: formatting ("—"), params, tiles, table + Total, drill-down links, CSV button, errors; nav lists.
- Playwright e2e: manager opens the page, sees tiles + table, drills down, a recruiter is refused.
