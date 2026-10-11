# rec-032 — Recruiter dashboard + quick actions + one-click skill search (design)

Status: DRAFT, built under the user's standing instruction to proceed on recommended answers (2026-10-11). Every DBn default below is
**UNVERIFIED** until confirmed and is registered as `DEC-SCOPE-180` (number re-checked against `main` before merge).

## 1. Sources and authority
- `EVID-018` §1 (14 tiles, 6 quick actions; L9–L48) and S2-§9 (one-click skill search; L1381–L1425) — `DERIVED_BLUEPRINT`.
- Backlog `rec-032` + Appendix B D1–D14 (`DERIVED_WORKBOOK`); R2/R3/R11 (`EXPLICIT_APPROVAL`, 2026-10-07).
- Q-25 (metric meanings) is still open → answered by the recommended defaults DB3–DB5 below.

## 2. Intent
A recruiter opens `/recruiter/dashboard` and sees, for **their own scope**, the 14 §1 figures, each linking to the list it summarises,
the §1 quick actions and a "Find Candidates by Skill" box that opens rec-013 with the skill (facets are rec-013's). A placement manager
sees the same for their team (+ the unassigned queue) and can narrow to one recruiter; `super_admin` sees everything. Nothing is typed:
every number is computed live in `services/recruiter_metrics.py`, the single source that rec-033…035 extend.

## 3. Recommended defaults (DB1–DB10, UNVERIFIED)
| # | Topic | Default |
|---|---|---|
| DB1 | Scope | Company-side tiles (D1–D5, D13) use rec-003's `companies.caller_scope`; requirement-side tiles (D6–D12, D14) use rec-007's `requirements.caller_scope` — exactly the lists the tiles open, so a tile and its list agree. |
| DB2 | Roles | `placement_team` (own), `placement_manager` (direct reports + unassigned queue), `super_admin` (all). Every other role → 403 (`hr_team` keeps the legacy placement dashboard; `bdm` has no dashboard). |
| DB3 | Recruiter filter | `?recruiter=<id>`: manager → one direct report (else 404); super_admin → any recruiter (else 404); a recruiter → only their own id (else 403). The filtered scope = that recruiter's own scope (no unassigned queue). |
| DB4 | Period | Flow tiles (D7, D8, D10, D11, D12) count the current IST calendar month to now. "Today" = IST date (`today_ist(db_now)`). |
| DB5 | Q-25 meanings | D1 = New Lead companies created in the last 7 days; D3 "Hot Recruiters" = companies with priority Hot (client companies are "recruiters" in §1); D5 = companies with ≥1 requirement not On Hold/Closed/Cancelled. |
| DB6 | D2 | No follow-up reason is a call (rec-024 FU reasons), so D2 = active New Lead companies with **no call logged** (rec-025). |
| DB7 | D14 | rec-007's `deadline_filter("expiring") ∪ ("expired")` (J4, N = 7 days); the tile shows how many are already past their deadline. |
| DB8 | Tile links | Each tile opens its nearest existing list with the matching filter (table §4). No new list endpoints (rec-032 owns no lists). When a manager filters to one recruiter, Companies/Requirements links carry `assigned=<id>`. |
| DB9 | Quick actions | All six §1 actions. "+ Add Recruiter" reuses rec-004's meaning (a company and its first contact: `/recruiter/companies/new?with=contact`, the companies page's own button); "+ Add Company" the plain company form; "+ Add Job Requirement" / "+ Add Candidate" their create forms (recruiter, manager, super_admin). Schedule Meeting / Interview open the Companies / Job Requirements lists (both are scheduled from a company / a candidate on a requirement) and show only for roles that can write them (recruiter, super_admin). |
| DB10 | Skill box | Comma-separated skills → `/recruiter/find-candidates?all=<skill>&all=…` (rec-013 AND search; its facets F1–F3 show on the results). |

## 4. Tiles (Appendix B, as built)
| ID | Key | Definition | Opens |
|---|---|---|---|
| D1 | `new_leads` | stage `new_lead`, not archived, not lost, created ≥ now − 7 days | `/recruiter/pipeline?stage=new_lead` |
| D2 | `contacts_pending` | stage `new_lead`, not archived, not lost, no `recruiter_calls` row on the company | `/recruiter/pipeline?stage=new_lead` |
| D3 | `hot_companies` | priority `hot`, not archived, not lost, stage ≠ `requirement_closed` | `/recruiter/companies?priority=hot` |
| D4 | `meetings_scheduled` | meeting status `scheduled`, now ≤ starts_at < now + 7 days | `/recruiter/meetings?view=upcoming` |
| D5 | `active_companies` | not archived, ≥1 requirement with status ∉ {on_hold, closed, cancelled} | `/recruiter/companies` |
| D6 | `new_requirements` | requirements created ≥ now − 7 days | `/recruiter/requirements` |
| D7 | `candidates_sourced` | applications created in the period | `/recruiter/requirements` |
| D8 | `profiles_shared` | `profile_share_items` created in the period | `/recruiter/requirements` |
| D9 | `interviews_scheduled` | interview status ∈ {scheduled, confirmed, rescheduled}, scheduled_at ≥ now | `/recruiter/interviews?view=upcoming` |
| D10 | `candidates_selected` | distinct applications with a history row → `selected` in the period | `/recruiter/requirements` |
| D11 | `candidates_joined` | offers `joining_status = joined`, actual_joining_date in the period (IST dates) | `/recruiter/joinings?view=joined` |
| D12 | `candidates_rejected` | distinct applications with a history row → `rejected` in the period | `/recruiter/requirements` |
| D13 | `follow_ups_due` | open follow-ups due before tonight's IST midnight (today + overdue; rec-024 "Today") | `/recruiter/follow-ups?due=today` |
| D14 | `requirements_expiring` | open requirements expiring within 7 days or already expired (+ `requirements_expired` sub-count) | `/recruiter/requirements?deadline=expiring` |

## 5. API — `GET /api/v1/recruiter/dashboard?recruiter=<uuid>`
Response `{day, period: {from, to}, recruiter: {id, full_name} | null, tiles: {<key>: int, …, requirements_expired: int}}`.
`Cache-Control: no-store`. Read-only; no audit row (a read of own figures, like tel-021). One aggregate statement for the 15 numbers
(scalar sub-selects), plus the scope lookups → a fixed statement count, asserted in a test.

## 6. Web
- `/recruiter/dashboard` (recruiter, manager, super_admin): `/auth/me` + the dashboard read; a failed read on a 403 renders
  `accessUnavailable`; any other failure shows "figures unavailable" while the quick actions and search still render.
- Components: `RecruiterDashboardTiles` (the `TelecallerDashboardTiles` pattern; each tile is a link), `RecruiterQuickActions`,
  `RecruiterSkillSearch` (client form), a manager/super_admin recruiter filter (GET form over `/recruiter/manager/team`).
- The recruiter keeps `RecruiterProfileCard`. Managers get "Dashboard" first in `RECRUITER_MANAGER_NAV` (their landing stays Team).

## 7. Errors, security, performance
- 401 unauthenticated; 403 other roles / recruiter filtering another id; 404 recruiter id out of scope; 422 malformed uuid.
- No IDs from the client widen scope (filter only narrows, checked server-side). No PII in the payload (counts only).
- Fixed statement count; every predicate uses existing indexes (companies stage/recruiter, follow-ups open/due, interviews status/time).

## 8. Tests
- pytest `test_rec_032_dashboard.py`: each tile = its definition on fixtures for a fresh recruiter (AC1); a second recruiter's data
  never shows (AC2); manager team + filter; super_admin filter; 403 for hr_team/bdm/recruiter-filtering-other; 404 out-of-team; IST
  day boundary (a follow-up due at 23:59 IST today counts, 00:00 IST tomorrow does not); fixed statement count.
- vitest: tiles render links with the right hrefs + `assigned` carry; quick actions per role; skill box builds the URL.
- Playwright e2e: recruiter sees tiles, a tile opens its list (AC3), the skill box lands on Find Candidates.

## 9. Plan (small tasks, TDD)
1. pytest RED for tiles/scope/roles → `services/recruiter_metrics.py` + `api/recruiter_dashboard.py` + router → GREEN.
2. vitest RED → `lib/recruiterDashboard.ts` + 3 components + page + manager nav → GREEN; update nav tests.
3. e2e spec; docker QA (desktop/tablet/mobile); docs: DEC-SCOPE, API §, RBAC §, backlog status.
