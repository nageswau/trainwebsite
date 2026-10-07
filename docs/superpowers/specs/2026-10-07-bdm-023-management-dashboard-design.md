# bdm-023 — Management dashboard: overview + alerts (design)

Decision: `DEC-SCOPE-108` (R1–R10 below). Backlog: `BDM_CRM_BACKLOG.md` §bdm-023; definitions Appendix B.4 (T-M01…T-M08,
AL-1…AL-7). Evidence: `EVID-016` §13 lines 413–434 (`DERIVED_BLUEPRINT`); scope approved under `DEC-SCOPE-055` D1.

**Status of the R-answers:** agent-recommended defaults, **not** `EXPLICIT_APPROVAL`. The owner told this session to "proceed with
recommended answers" and ask only on real blockers; the owner may override any of them.

## 1. Dependencies (hard-stop check, 2026-10-07)

| Item | State on `main` @ `cbc6157a` | Counted as done because |
|---|---|---|
| bdm-005 MoUs | merged (PR #77), "VERIFIED — not yet COMPLETE" | `DEC-SCOPE-082` L1: merged on `main` with verified QA evidence |
| bdm-006 Appointments | merged (PR #58), stale status line | L1 |
| bdm-008 Follow-ups | merged (PR #71), "VERIFIED — ready for owner sign-off" | L1 |
| bdm-010 Travel | COMPLETE | — |
| bdm-016 Targets | merged (PR #117) | backlog marks it "target progress optional"; not used here (R10) |

## 2. Scope

In: `GET /api/v1/bdm/manager/dashboard`, the `/bdm/manager/dashboard` page (8 tiles + an alert list), a super_admin manager filter,
a "BDM Dashboard" entry in the super_admin sidebar. Out: target progress (R10), any write, any new table, caching.

## 3. Decisions (recommended defaults)

| # | Question | Default |
|---|---|---|
| R1 | Who reads | `bdm_manager` (own team) and `super_admin` (all teams). Others `403` "BDM manager role required" (`require_manager`) |
| R2 | Manager filter | `manager_user_id` query parameter, super_admin only. A `bdm_manager` sending it gets `422` "Only a super admin can choose a manager". An id that is not a `bdm_manager` user → `404` "Manager not found" (inactive managers allowed: their team still has records) |
| R3 | Team | BDMs whose `reporting_manager_user_id` is the manager (`team_filter`, D4), active or not, for record counts. T-M01 and AL-7 count active BDMs only |
| R4 | Clock | Database clock, read once; "today" and "this month" are IST (Appendix B conventions) |
| R5 | AL-5 "completed today" | Appointments whose move to `completed` (an appointment event) happened today IST — what a manager means by "completed today", even for a meeting that started yesterday |
| R6 | AL-7 "previous working day" | **No working-day calendar** (same rule as `DEC-SCOPE-080` G1): the previous IST calendar day. A BDM whose profile was created after that day is not listed (bdm-015's `not_started` rule) |
| R7 | AL-4 threshold | Current MoU in `proposal_sent` / `draft_shared` whose `status_changed_at` is ≥ 5 days ago (D19); archived organizations excluded (as My Day T-S7) |
| R8 | Alert list size | Each alert kind: total `count` + the first 10 items (oldest / most urgent first). The page says "Showing 10 of N" and links to the full list page |
| R9 | Links | The API returns record ids, the web builds the links: appointment → `/bdm/manager/appointments/{id}`, trip → `/bdm/manager/trips/{id}`, follow-up → its organization (or `/bdm/manager/follow-ups` when it has none), MoU → its organization, daily report → `/bdm/manager/daily-reports/{bdm}?date=` |
| R10 | Target progress | Not shown (backlog: optional). bdm-024 or a later item may add it |

## 4. Definitions (Appendix B.4, exact rules)

Scope `T` = `SELECT user_id FROM bdm_profiles WHERE reporting_manager_user_id = :manager` (super_admin without a filter: no
restriction). `today`, `[day_start, day_end)`, `[month_start, month_end)` are IST.

| ID | Rule |
|---|---|
| T-M01 Total BDMs | active users with a profile in `T` |
| T-M02 Today's Appointments | appointments of `T`, status ≠ `cancelled`, `starts_at` in today |
| T-M03 Upcoming Appointments | appointments of `T`, status in `scheduled`/`confirmed`/`rescheduled`, `starts_at ≥ day_end` |
| T-M04 BDMs Travelling | distinct `bdm_user_id` of `T` with a trip `approval_status = approved`, `travel_status` in `planned`/`in_progress`, `travel_date ≤ today ≤ return_date` |
| T-M05 Trips This Month | trips of `T`, `travel_date` in the month, `travel_status ≠ cancelled`, `approval_status ≠ rejected` |
| T-M06 Meetings Completed | M-06 over `T` for the month (`bdm_metrics._completed`) |
| T-M07 MoUs in Progress | current MoUs of non-archived organizations assigned to `T`, status `discussion_started` … `draft_shared` |
| T-M08 MoUs Signed | M-11 over `T` for the month (`bdm_metrics._mou_moved_to("signed")`) |
| AL-1 Appointment not confirmed | `T`, status `scheduled`/`rescheduled`, `now < starts_at ≤ now + 24 h`; soonest first |
| AL-2 Travel approval pending | trips of `T`, `approval_status = submitted`, `travel_status = planned`; earliest travel date first |
| AL-3 Follow-up overdue | tasks of `T` (assignee), kind `follow_up`, status `open`, `due_on < today`; oldest due first |
| AL-4 MoU pending | R7; longest waiting first |
| AL-5 Appointment completed | R5; latest first. Informational (green) |
| AL-6 Outcome missing | `T`, status open and `starts_at ≤ now` (bdm-007 `pending_filter`); oldest first |
| AL-7 Daily report not submitted | R6; by name |

An alert with `count = 0` is still returned (the page hides it; "alerts disappear when resolved" — AC2 — follows from live rules).

## 5. API

`GET /api/v1/bdm/manager/dashboard[?manager_user_id=<uuid>]` → `200`

```json
{
  "today": "2026-10-07", "month": "2026-10-01",
  "manager": {"id": "…", "full_name": "…"} | null,
  "tiles": [{"key": "T-M01", "label": "Total BDMs", "definition": "…", "value": 8}],
  "alerts": [{"key": "AL-1", "label": "Appointment not confirmed", "tone": "warning", "record": "appointment", "count": 2,
              "items": [{"id": "…", "title": "APT-00012 · Sunrise College", "bdm": {"id": "…", "full_name": "…"},
                          "at": "2026-10-08T04:30:00Z", "organization_id": "…"}]}]
}
```

`tone` ∈ `danger` / `warning` / `success`; `record` ∈ `appointment` / `trip` / `task` / `mou` / `daily_report`; `at` is an ISO
instant or date (the item's time: start, travel date, due date, waiting since, completed at, report date); `organization_id` may be
null. Read-only: no write, no audit, no log line. Query count is constant: one SELECT of scalar subqueries for the 8 tiles and 7
counts, then one query per alert list (8 statements), plus one manager lookup when filtered.

Module: `app/api/bdm_manager_dashboard.py` (route + queries, the My Day pattern). `bdm_metrics._completed` / `_mou_moved_to` accept a
team sub-select as well as one BDM id (one helper `_owned`), so T-M06/T-M08 reuse the M-06/M-11 builders unchanged in meaning.

## 6. Web

- `lib/bdmManagerDashboard.ts`: types, `isManagerDashboard` guard, `alertHref(alert, item)`, `ALERT_LIST_HREF`, tone → CSS class
  and text word (`danger` "Urgent" / `warning` "Attention" / `success` "Done") — colour is never the only signal (AC4).
- `components/BdmManagerDashboard.tsx`: the tiles (`kpi-grid` / `kpi-tile`, as My Day and `SchoolKpiBoard`), then "Alerts": one
  section per non-empty kind with a heading, a text status chip, the count, up to 10 linked items (BDM name + time) and "View all".
  Empty: "No alerts right now." A team with no BDMs: the summary "No BDMs report to you yet.", zero tiles and "No alerts right now."
- Page `app/bdm/manager/dashboard/page.tsx`: keeps the existing team summary + "View team" for a manager; super_admin gets the
  admin sidebar, "All teams" or the chosen manager, and a GET form with a manager `<select>` (from `/admin/bdm-managers`). A
  dashboard that fails to load after the gate shows an inline alert with "Try again" (My Day pattern), plus "Show all teams" when
  super_admin had chosen a manager (QA23-02). `loading.tsx` added.
- `SUPER_ADMIN_NAV`: "BDM Dashboard" → `/bdm/manager/dashboard`.

## 7. Security

Scope comes from the session; the only parameter (`manager_user_id`) is super_admin-only and validated as a UUID; a manager can never
widen scope (R2). Items carry no contact phone/email, no report text, no MoU notes. No new dependency, no secrets.

## 8. Tests

Backend `tests/test_bdm_023_dashboard.py`: roles (BDM 403, manager 200, super_admin all + filter, manager with filter 422, unknown
manager 404); each tile and alert rule on seeded rows with near-miss rows that must not count; team isolation (another team's rows
never appear); alert disappears after resolution (confirm / decide / complete / submit); empty team; constant statement count.
Web: lib unit tests, component tests (tiles, tones with text, links, empty, truncation), page tests. Playwright
`tests/e2e/bdm-023-manager-dashboard.spec.ts`: seeded manager sees tiles + an alert linking to its record; phone width no overflow.
