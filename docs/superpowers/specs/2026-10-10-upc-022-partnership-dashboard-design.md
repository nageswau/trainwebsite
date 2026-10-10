# upc-022 — Partnership manager dashboard (design)

**Date:** 2026-10-10 · **Branch:** `feature/upc-022` · **Gate:** GATE-09 (EVID-020 in scope, U1) · **Migration:** none

## 1. Source and intent

- `EVID-020` §22 (L721–L752): the manager's home page shows a *Global Partnership Overview* (Total Universities, Active Partners,
  Partnership in Progress, Target Universities, At Risk) and *This Month* (nine figures + overdue follow-ups). Numbers in the source are
  illustrative. §20 (L688–L693): the dashboard shows the follow-up bands Overdue / Due Today / Due Tomorrow / Upcoming.
- Backlog §upc-022 + Appendix B D1–D14. Acceptance: *each tile equals its definition; a manager sees their own scope and the head sees
  their team; a counselor → 403; month boundary in IST.*
- Dependencies upc-007, 009, 010, 014, 020, 023 are merged on main.

## 2. Decisions (recommended answers, `NEEDS_CONFIRMATION` at sign-off — registered as DEC-SCOPE-165)

| # | Question | Answer |
|---|---|---|
| DB1 | Scope of the university figures | upc-018 PF6, the rule `/partnership/expected` and `/partnership/performance` use: manager = primary **or** backup; head = their direct reports' universities + unowned; super_admin = all |
| DB2 | Whose events count this month | Events of the universities **currently** in scope (the tile's list), not upc-021's credit-at-the-time. A reassignment moves a university's month figures with it; the Targets page keeps the per-manager history |
| DB3 | "This month" | The current IST calendar month, half-open (`bdm_metrics.month_range`); today from the DB clock in IST |
| DB4 | D1 | Active universities in scope, Lost/Closed included. The response also carries `lost` so D1 = D2 + D3 + D4 + lost reconciles |
| DB5 | D2–D4 | Active, not lost, stage group G1 partner / G2 in progress / G3 target (`partnership_stages.GROUPS`) |
| DB6 | D5 | Active universities with `relationship_strength = at_risk` (Q-08) |
| DB7 | D6 | Universities whose first stage-history entry into Initial Contact or later falls in the month (upc-021 T2's rule) |
| DB8 | D7 | Meetings with status completed and `completed_at` in the month (T3) |
| DB9 | D8 | Distinct visits with a status event into `visit_completed` in the month |
| DB10 | D9 / D12 | Distinct universities with a stage move into Proposal Sent / Partner Activated in the month (T4 / T7) |
| DB11 | D10 | Agreements of active in-scope universities whose status is now `sent`, `under_review` or `negotiation` (a current figure, shown under This Month as in the source) |
| DB12 | D11 | Distinct agreements with a status event into `signed` in the month (T5) |
| DB13 | D13 | upc-023 E1 exactly: the same scoped rows as `/partnership/expected`, raw count + weighted (Σ probability) for this month |
| DB14 | Follow-up bands, D14 | Open tasks per upc-020 band (overdue / today / tomorrow / upcoming), assignee scope = the Tasks page default: manager = own, head = own + direct reports, super_admin = all. D14 = the overdue band |
| DB15 | Readers | `partnership_manager` (with a profile), `partnership_head`, `super_admin`; others `403`; signed out `401` |
| DB16 | Links | Each tile links to the closest existing list (no new list filters): Universities (manager: `?manager=me`; At Risk: `relationship_strength=at_risk`), Pipeline, Meetings, Visits (`status=visit_completed`), Agreements, Expected (`window=this_month`), Tasks (`band=…`) |

## 3. API

`GET /partnership/dashboard` → `200`

```
{ today, month: {first, last},
  overview: {total, partners, in_progress, targets, at_risk, lost},
  this_month: {contacted, meetings, visits, proposals, mous_negotiating, mous_signed, activated, expected_count, expected_weighted},
  followups: {overdue, today, tomorrow, upcoming} }
```

Read-only; no body, no parameters. A fixed number of SQL statements whatever the data size (one grouped overview query, one per month
figure, one for the expected rows, one for the bands). The E1 query is shared with `/partnership/expected` (extracted, not copied).

## 4. UI

`/partnership/dashboard` (server page): managers keep the welcome, the profile card and "Coming soon"; heads and super_admin reach it
too (`shellFor`), and the head nav gains **Dashboard** first (head landing stays Team, U3). Under the title:
1. *Follow-ups* — four band tiles (🔴 Overdue, 🟠 Due Today, 🟡 Due Tomorrow, 🟢 Upcoming), each a link to Tasks for that band.
2. *Global Partnership Overview* — Total + four group tiles.
3. *This Month* — nine tiles + Overdue follow-ups; the month named in the heading.

Tiles reuse `metric-grid` / `metric` markup (the `TelecallerDashboardTiles` pattern) as a list of links. If the dashboard read fails the
page still renders with "The dashboard figures are unavailable right now." (`role="status"`).

## 5. Security

Scope is applied in SQL from the caller (no client-supplied ids — no IDOR surface). Counts only, no names, no commission data. No writes,
so no audit row or CSRF surface. Errors: 401 / 403 from the shared dependencies.

## 6. Tests

- API (pytest, fresh manager's scope): every figure for a seeded fixture; month boundary (event at IST 00:00 of the 1st counts, 23:59 of
  the last day of the previous month does not); head sees a team member's university and not another head's; super_admin 200; counselor,
  overseas_admin 403; signed out 401; a manager without a profile 403; D13 equals `/partnership/expected`'s this-month window; fixed
  statement count.
- Web (vitest): tiles render values and links; failed read shows the status; head shell; nav lists.
- e2e (Playwright): a manager signs in, sees the three sections and follows a tile; a head opens the dashboard from the nav.

## 7. Regression risks

The dashboard is the manager's landing page used by many e2e sign-ins (upc-001 asserts the profile card and "Coming soon"); both stay.
The head nav exact-list test and the alert-badge test change by one entry / one stub.
