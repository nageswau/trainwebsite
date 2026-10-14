# mgmt-031 — Partner home dashboard (design)

- **Feature ID:** `mgmt-031` · **Decision:** `DEC-SCOPE-219` (HM1–HM14, recommended defaults, `UNVERIFIED`; answers backlog Q-30).
- **Evidence:** `EVID-017` §31 (L1205–L1239: greeting, month, "Today's Business Snapshot" with 7 figures, 9 panels) and §2
  (L59–L129: the partner dashboard's 15 items). Scope authority `DEC-SCOPE-186` M13 (`EXPLICIT_APPROVAL`).
- **Backlog:** `MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-031. Acceptance: *every panel matches its page's figure; super_admin sees
  no money.* Edge case: *the first month with no data.*
- **Dependencies (all merged to main):** mgmt-003 (#244), 009 (#264), 013 (#253), 026 (#272), 027 (#248), 028 (#250), 029 (#273),
  030 (#276).
- **Approval:** the owner's standing instruction for feature sessions is to proceed with the recommended answers, so every HM point
  is a recommended default, `UNVERIFIED` until confirmed.

## Understanding

When a partner signs in they land on `/management` (MG3). Today that page lists only the Command Center pillars. §31 asks that the
landing page first answer "how is the business today": a greeting and the month, 7 headline figures, then 9 panels. Each panel is a
read-through of a dashboard that already exists, and it links to that dashboard. The super admin (operational tier) gets the same
home without any money (M13). The accountant's Command Center stays exactly as it is.

## Approaches

1. **One composite `GET /management/home` (chosen).** A new `services/management_home.py` calls the existing service functions
   and returns one document. The server decides the tiers, there is one round-trip, and the query count is fixed (the backlog's
   performance note).
2. Fan out from the page to the 8 existing endpoints. This puts M13 branching in the UI, adds 8 round-trips and 8 partial-failure
   paths, and the accountant would need special casing. Rejected.
3. A stored or materialised home snapshot. This needs a migration and staleness rules, and nothing asks for it. Rejected (YAGNI).

## Decisions (HM1–HM14, `UNVERIFIED`)

| # | Point | Recommended default |
|---|---|---|
| HM1 | Where | The panels sit on `/management` (the Command Center home), above the existing pillars, for the operational tier (partner, super_admin). The accountant's page is unchanged (pillars only; the home endpoint is never called) |
| HM2 | Access | `GET /management/home`: partner → `scope: "business"`; super_admin → `scope: "operational"` with every money figure and panel **absent from the response** and never queried. Accountant `403` "Operational access required"; others `403` "Management access required"; signed out `401` |
| HM3 | Header | "Good morning / afternoon / evening, {first name}" by the IST hour (before 12, before 17, else), and the IST month ("October 2026") |
| HM4 | Snapshot (7) | **Revenue, Expenses, Profit**: this IST month to date, the mgmt-009 P&L total (revenue, expenses, contribution), same as `/management/pnl` by default. **Cash**: the mgmt-013 cash/bank balance of the latest month entered up to this month, with that month named, same as `/management/accounts?month=`. Not entered → "Not entered". **Students**: S1 Total Students (mgmt-003), same as `/management/snapshot`. **Applications**: applications created this month to date, the mgmt-024 "Applications Created" for `date_from` = the 1st, `date_to` = today. **Enrollments**: applications that reached Enrolled this month (the mgmt-026 PN5 KPI), the same as the mgmt-030 Enrollment factor's current value for this month. super_admin: Students, Applications, Enrollments only |
| HM5 | Urgent issues (Q-30) | Conditions with a count above 0, each linking to its list. **Overdue tasks**: open management tasks past their deadline (mgmt-028 "overdue" band, everyone's). **Overdue decisions**: pending decisions (MD12) past their deadline. **Red health factors**: factors in Red for the last complete month (mgmt-030, tier-filtered). **Partner only: overdue receivables**, the mgmt-013 receivables overdue amount when above 0. None → "No urgent issues" |
| HM6 | Pending decisions | The first 5 of the mgmt-027 pending list (MD12 order: by deadline, none last) and the total. Links to `/management/discussions#pending-decisions` |
| HM7 | Today's meetings | The mgmt-029 calendar for today (IST), as `/management/meetings` shows it by default: time, title, kind, status |
| HM8 | Target vs actual | This month's mgmt-026 plan progress: the first 5 KPI rows (target, actual, achievement %) and the free-text done tally. Revenue rows are partners' only (PN7, already enforced). No plan → "No plan for {month}", linking to `/management/plans` |
| HM9 | Financial position (partner) | The mgmt-013 figures: receivables total and overdue (today), pending invoices (count, amount), and the cash/bank, payables and tax liabilities of the balance month in HM4. Links to `/management/accounts?month=` that month |
| HM10 | Business growth (MoM) | The mgmt-030 score for the last complete month: overall score and RAG, plus each factor's month-on-month change % where there is one. Tier-filtered by mgmt-030 itself (BH1) |
| HM11 | My tasks | The caller's own open tasks (mgmt-028 owner = me): the band counts and the first 5, as `/management/tasks` (default view "mine") |
| HM12 | Recent discussions | The 5 newest discussions (MD12 default order). Links to `/management/discussions` |
| HM13 | Next month plan | Next IST month's plan summary (status, item count, KPI item count) or "No plan yet". Links to `/management/plans/{YYYY-MM}` or `/management/plans` |
| HM14 | Nav, writes, performance | The BI entry "This month's performance" (mgmt-031) becomes live, linking to `/management#this-month`, operational tier. Read-only: nothing stored, logged or audited. A fixed number of statements (each reused service call is bounded; lists are `LIMIT 5`). No migration |

**First month with no data (edge case):** money reads ₹0.00 as the P&L page does, cash reads "Not entered", counts read 0, every
list panel shows its empty state, and the growth panel reads "Not enough data" (score null).

## Architecture

- **API:** `GET /management/home` in `api/management.py`, gated by the existing `_operational`. `ManagementHomeOut` in `schemas.py`.
  Money fields are optional and left unset for super_admin (`response_model_exclude_unset`, as mgmt-023 does).
- **Service:** `services/management_home.py`, `async def home(db, user, today)`. It composes `management_pnl.dashboard`,
  `accounts.receivables` / `pending_invoices`, `FinanceBalance`, `management_metrics.snapshot` / `applications` / `plan_actuals`,
  `management_health.health`, `management_discussions.page`, `management_meetings.calendar`, `management_tasks.page` / `counts`, and
  `management_plans.progress` / `_plans`. It copies no data and adds no new metric definitions.
- **Web:** `app/management/page.tsx` fetches `/management/home` only when `me.tiers.operational`. If the call fails, it shows a
  `form-error` alert and the pillars still render. `components/ManagementHome.tsx` renders the server-side markup (no client
  state). `lib/managementHome.ts` holds the types and the greeting/format helpers.
- **Errors:** an API failure on the home call never blocks the Command Center. A `401`/`403` follows the existing
  `accessUnavailable` path.

## Testing

- **API (pytest):** access matrix (401, accountant 403, it_admin 403, partner 200, super_admin 200 with no money keys). Each panel
  equals its page's endpoint read in the same test (P&L, accounts, snapshot, applications, health, discussions pending, meetings,
  tasks, plan progress). Urgent issues appear for an overdue task or decision. The next-month plan summary is checked.
- **Web (vitest):** the greeting by hour; the component for partner versus operational (no ₹ anywhere); empty states; the urgent
  "No urgent issues" state; links.
- **e2e (Playwright):** a partner sees the snapshot and the 9 panels; super_admin sees no money panels and no ₹; the accountant
  sees no home.
