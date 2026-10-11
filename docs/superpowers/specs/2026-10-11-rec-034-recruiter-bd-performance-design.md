# rec-034 — Recruiter/BDM performance per recruiter (design)

Status: DRAFT, built under the user's standing instruction to proceed on recommended answers (2026-10-11). Every BPn default below is
**UNVERIFIED** until confirmed and is registered as `DEC-SCOPE-183` (number re-checked against `main` before merge).

## 1. Sources and authority
- `EVID-018` §25 "Recruiter/BDM Performance" (L973–L1005: 6 business-development + 6 recruitment metrics, "This prevents management from
  measuring a recruiter only on calls") — `DERIVED_BLUEPRINT`.
- Backlog `rec-034` + Appendix B B1–B12 (`DERIVED_WORKBOOK`): "credit = the actor or assignee at the event"; AC "each column equals its
  definition; credit after reassignment follows the actor of the event (Q-25)"; "a recruiter sees their own row"; "a recruiter requesting
  another recruiter's row → 403"; edge case "a deactivated recruiter in the period".
- R10 (BDM is reference + read-only; §25 metrics are per recruiter, from their own activity). Q-24 (revenue = expected revenue), Q-25 open
  → answered by the defaults below.
- Builds on rec-033 (`DEC-SCOPE-182`, `services/recruiter_metrics.py`) and rec-031 (`DEC-SCOPE-176`, fee per hire).

## 2. Intent
A placement manager opens **Recruiter Comparison** and sees, for a period (the current IST month by default), one row per recruiter in
their team with the twelve §25 figures side by side — business development and recruitment — and a Total row. `super_admin` sees every
recruiter. A recruiter opens **My Performance** and sees only their own row. Every figure is credited to the person who did the work
(the actor of the event), so a reassignment never moves past credit.

## 3. Recommended defaults (BP1–BP8, UNVERIFIED)
| # | Topic | Default |
|---|---|---|
| BP1 | Roles (Q-25) | `placement_team` (own row only; `recruiter=<another id>` → 403), `placement_manager` (direct reports; a recruiter outside the team → 404), `super_admin` (every recruiter). `it_admin` and every other role → 403: the table carries revenue, which rec-031 RV10 keeps from everyone but recruiters, their managers and super_admin. |
| BP2 | Credit (AC) | The actor of each event (table §4), never today's assignment. Work done by someone who is not a recruiter (a manager, an admin, an employer, the system) is in no row. |
| BP3 | Rows | Recruiters (`placement_team` with a recruiter profile) in scope, by name. An **inactive** recruiter appears only when they have a non-zero figure in the period (edge case: deactivated mid-period keeps their credit; long-gone people do not pile up as zero rows). No Unassigned row (credit is by actor). |
| BP4 | Total | Σ of the rows shown (counts and revenue). Shown for a manager / super_admin; a recruiter's view is their one row. |
| BP5 | Period | rec-033 PF3: `from`/`to` IST dates; default the 1st of the current IST month → today; `from ≤ to ≤ today`, ≤ 366 days (tel-023's `date_range`). |
| BP6 | "First" events | B4, B5 count an entity once, at its first qualifying event ever (a company moved back and forward again is not new twice); B10 counts an application once, at its first Selected in the period (as P7). |
| BP7 | Revenue (Q-24) | Expected revenue: Σ fee per hire over B11's hires, with rec-031's rule (requirement override, else the company's current contract; a percentage needs the offer's INR compensation, else the hire is unpriced and adds 0). Two decimals, as a string. |
| BP8 | Export | None (not in the backlog's scope; rec-033's CSV covers §24). |

## 4. Figures (Appendix B, as built; period [start, end) in IST)
| ID | Key | Counted | Credited to |
|---|---|---|---|
| B1 | `companies_contacted` | distinct companies with a contact call (`occurred_at`), a contact message (`sent_at`) or a completed meeting (`completed_at`) in the period | the caller / sender / completer |
| B2 | `meetings` | meetings completed in the period (`status = completed`, `completed_at`) | `completed_by_user_id` |
| B3 | `new_leads` | companies created in the period | `created_by_user_id` |
| B4 | `new_companies` | companies whose first stage move from New Lead / Contacted / Interested to a later stage is in the period | that history row's actor |
| B5 | `new_contracts` | contracts whose first event reaching Signed or Active is in the period | that event's actor |
| B6 | `new_requirements` | requirements created in the period | `created_by_user_id` |
| B7 | `candidates_sourced` | applications created in the period | `added_by_user_id` |
| B8 | `profiles_shared` | share items created in the period | the share's `shared_by_user_id` |
| B9 | `interviews` | rec-033 P6's interviews (Completed / Selected / Rejected, `scheduled_at` in the period) | the actor of the interview's latest status event, else its creator |
| B10 | `selections` | applications with a → Selected history row in the period (first such row) | that row's `changed_by_user_id` |
| B11 | `joining` | rec-033 P8's offers (Joined, actual joining date in [from, to]) | the actor of the offer's latest `joined` event |
| B12 | `revenue` | BP7 over B11's hires | as B11 |

## 5. API — `GET /api/v1/recruiter/performance/by-recruiter?from&to&recruiter`
Response `{date_from, date_to, recruiter: {id, full_name} | null, items: [row], totals: row | null}`; a row is
`{user_id, full_name, active, <B1–B11 ints>, revenue: "0.00"}`. `totals` is null for a recruiter's own view. `recruiter=<id>` narrows a
manager / super_admin view to one recruiter (items = that row, totals = it). `Cache-Control: no-store`.
Errors: 401 anonymous; 403 other roles / a recruiter asking for someone else; 404 recruiter outside the caller's scope or not a recruiter;
422 bad uuid/date or range rules. Performance: the people lookup, one `UNION ALL` statement of grouped counts, one hires query → fixed.

## 6. Web
- `/recruiter/performance` — recruiter: "My performance" (`RECRUITER_NAV` "My Performance"); manager: "Recruiter comparison"
  (`RECRUITER_MANAGER_NAV` "Comparison"); super_admin: `SUPER_ADMIN_NAV` "Recruiter Comparison".
- A GET period form (rec-033's pattern), then one table: a grouped header row ("Business development" ×6, "Recruitment" ×6), one row per
  recruiter (Inactive badge), Total footer. Empty team → a status line. 403 → `accessUnavailable`; 404 → "That recruiter is not in your
  team."; 422 → the API's sentence; else "Recruiter performance is unavailable right now.". Revenue as ₹ (en-IN).

## 7. Security
Server-side scope only; `recruiter` only narrows and is checked against the caller's scope. Read-only, no audit row (no export). Staff
names and counts only; revenue gated by BP1. Parameters bound by SQLAlchemy.

## 8. Tests
- pytest `test_rec_034_by_recruiter.py`: each B figure on fixtures; actor credit after reassignment (AC); B4/B5 first-ever; B12 fixed +
  percent + unpriced; Total = Σ rows; inactive recruiter shown only with figures; roles (recruiter own 200 / other 403, manager out of team
  404, it_admin/hr 403, super_admin 200); period 422; no-store; fixed statement count.
- vitest: formatting, table + grouped header + Total, own view without Total, errors; nav lists.
- Playwright e2e: manager sees the comparison, a recruiter sees only their own row.
