# upc-029 — Complete global partnership dashboard (design)

**Date:** 2026-10-10 · **Branch:** `feature/upc-029` · **Gate:** GATE-09 (EVID-020 in scope, U1) · **Migration:** none

## 1. Source and intent

- `EVID-020` §31 (L1004–L1058): "🌍 EDUSPHERE GLOBAL PARTNERSHIPS" — three columns, **Active Partners** (Country-wise, University-wise,
  Course-wise), **In Progress** (Expected Date, Probability, Next Action) and **Target List** (Priority, Country, Course); then the
  partnership pipeline (Contact → Meeting → Proposal → MoU → Partner Active), the student recruitment funnel (Applications, Offer → Visa →
  Enrolment) and University Commission. Numbers are not given.
- Backlog §upc-029: a management page for `super_admin` and `partnership_head`; `partnership_metrics`; `GET /partnership/global-dashboard`;
  no database change; acceptance *the totals reconcile with upc-022 and upc-018*; negative *a manager → 403 (or own scope; design)*.
  It feeds Management §19 (mgmt-023, Q-31), whose eight-step pipeline is Appendix B's "Management §19 pipeline".
- Dependencies upc-018, upc-022, upc-023 are merged on main (and upc-019, which the commission figures reuse).

## 2. Decisions (recommended answers, `NEEDS_CONFIRMATION` at sign-off — registered as one DEC-SCOPE)

| # | Question | Answer |
|---|---|---|
| GD1 | Readers | `partnership_head` and `super_admin`. A `partnership_manager` is a **403** (their own figures are upc-022's dashboard); every other role 403; signed out 401 |
| GD2 | Scope | upc-018 PF6 (`scope_filter`), as upc-022: head = direct reports' universities + unowned; super_admin = all. Active (non-deactivated) universities only |
| GD3 | Columns | Appendix B groups, not lost: Active Partners = G1, In Progress = G2, Target List = G3. Each column carries its count, so the three equal upc-022 D2–D4 for the same caller |
| GD4 | Active · Country-wise | Partners per country (name), largest first, then name |
| GD5 | Active · University-wise | The partners, with country and active course count, most courses first then name; the first 10 (`TOP`), the column count says how many in all |
| GD6 | Active · Course-wise | Active courses (`overseas_courses.active`) of the partners, per level (UG, PG, PhD, Diploma, Foundation; any other stored level as stored), with the number of partners offering it |
| GD7 | In Progress · Expected Date | G2 rows by `expected_agreement_date` (upc-008/023): Overdue (< today), This month, Next month, Later, Not dated. The buckets add up to the column count |
| GD8 | In Progress · Probability | G2 rows per effective probability (upc-023 EX1: override, else the stage band), highest first, plus the weighted forecast Σp/100 (E4) over the column |
| GD9 | In Progress · Next Action | Per G2 university its earliest-due **open** task (upc-020), overdue flagged; the first 10 by due date, then name; plus the count of G2 universities with no open task |
| GD10 | Target · Priority | G3 rows per `priority` A / B / C / Not set (UM priorities) |
| GD11 | Target · Country | G3 rows per country, as GD4 |
| GD12 | Target · Course | G3 rows per declared `course_levels` level (a target has no course master yet); a university declaring two levels counts in both; plus "Not stated" |
| GD13 | Pipeline | Management §19 (Appendix B, Q-31): Identified = K1, Contacted = K2–K3, Meeting = K4, Proposal = K5, Negotiation = K6, Agreement = K7, Signed = K8, Active Partner = K9; current counts of active, not-lost universities in scope, plus `lost`. Σ steps + lost = upc-022 D1 |
| GD14 | Funnel | upc-018 F1–F9 totals over the scope for a period (`from`/`to`, default this IST month to date, PF1 limits); Leads, Counselling, Eligible are `null` ("Not tracked", U8). Equal to `/partnership/performance` `totals` for the same caller and period |
| GD15 | Commission | upc-019 F10/F11 for the period, per currency (no FX), over the same universities; present only for the commission roles (U2) via `response_model_exclude_unset` — both readers are U2 roles today, the strip keeps Management M3 safe. Equal to `/partnership/performance` `commission` |
| GD16 | Links | Column headings open the pipeline column (`?column=active_partners`, `target`; In Progress the whole board); universities and next actions open the university page; Target priority opens `/partnership/universities?priority=X`. No new list filters |
| GD17 | Page / nav | `/partnership/head/global-dashboard` (signed-out → `/admin/login`, where both readers sign in). Head nav gains **Global Dashboard** after Dashboard; super_admin nav gains **Partnership Global Dashboard**. Not a §32 menu entry (the managers' menu is unchanged) |

## 3. API

`GET /partnership/global-dashboard?from=YYYY-MM-DD&to=YYYY-MM-DD` → `200`

```
{ today, from, to,
  active:      {count, countries: [{name, count}], universities: [{id, university_code, name, country, courses}], courses: [{level, courses, universities}]},
  in_progress: {count, expected: {overdue, this_month, next_month, later, undated}, probability: [{probability, count}], weighted,
                next_actions: [{university: {id, university_code, name}, task_id, title, due_on, overdue}], without_action},
  target:      {count, priorities: [{priority, count}], countries: [{name, count}], course_levels: [{level, count}], no_course_levels},
  pipeline:    {steps: [{key, label, count}], lost, total},
  funnel:      {steps: [{key, label, tracked}], totals: {leads: null, …, enrolled}},
  commission?: {expected: [{currency, amount}], received: [{currency, amount}]} }
```

Read-only; 401 / 403 from the dependencies; a bad period 422 (upc-018's messages). A fixed number of statements: the scoped university
rows (one), the active courses (one), the open tasks (one, `DISTINCT ON`), funnel (one per tracked step), commission (two), the clock.
Lists are computed in Python over the one scoped university query, so every sub-view adds up to its column.

## 4. UI

Server page; `PortalShell` with `shellFor(role)`. Title "🌍 EduSphere Global Partnerships", a period form (reuse `PerformancePeriodForm`)
that drives the funnel and commission only (the columns are "now"). Then:
1. **Three columns** (`global-columns`: one column on phones, three from 900 px) — a section per column with its count as the heading,
   and three small tables/lists (`<table>` with caption for the counts; `<ol>` for University-wise and Next Action).
2. **Partnership pipeline** — the eight steps as `kpi-tile`s in order (`PartnershipDashboardTiles` markup), lost noted.
3. **Student recruitment** — `PartnershipFunnel` with the totals.
4. **University commission** — Expected / Received per currency, "No commission recorded for this period" when empty; not rendered when
   the key is absent.
Empty column: "No universities in this column." Read failure: the shell still renders with "The global dashboard is unavailable right
now." (`role="status"`). Wrong role: `accessDenied`.

## 5. Security

Scope from the caller in SQL (no client ids; IDOR-free). Counts, names and codes of universities the reader may already read in the
University Master. GD9 shows a task title (never its notes) only for universities in the reader's scope, whose tasks the head already
reads on the university page. Commission per U2. No writes, no audit, no CSRF surface.

## 6. Tests

- API (pytest): readers (head 200, super_admin 200, manager 403, counselor/overseas_admin 403, signed out 401); every sub-view on a seeded
  fixture in a fresh head's scope; columns equal `/partnership/dashboard` D2–D4 and pipeline + lost equals D1; funnel equals
  `/partnership/performance` totals and commission equals its `commission` for the same period; a bad period 422; head excludes another
  head's university; fixed statement count.
- Web (vitest): the page renders the three columns, pipeline, funnel and commission; empty column text; commission absent → no section;
  failed read → status; manager → access denied; nav lists.
- e2e (Playwright): a head signs in at `/admin/login`, opens Global Dashboard from the nav, sees the three columns and the pipeline, and
  follows a column heading; phone width has no horizontal scroll.

## 7. Regression risks

Exact nav-list tests for the head and super_admin. No shared service changes beyond new functions in `partnership_metrics`.
