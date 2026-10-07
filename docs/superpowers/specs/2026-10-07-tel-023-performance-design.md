# tel-023 — Manager performance comparison — design

- **Backlog:** `docs/delivery/TELECALLER_CRM_BACKLOG.md` tel-023 (EVID-019 §16; T23, T24; Appendix B P1–P6). Depends on tel-021 (merged, PR #118).
- **Decision:** `DEC-SCOPE-109` (PF1–PF4, owner answers 2026-10-07, all recommended). API §12AC, RBAC §2.35. **No migration.**
- Numbering: main has bdm-019 (0098 / 107 / §12AA / 2.33) and bdm-023 (108 / §12AB / 2.34); tel-020 and tel-024 (in flight, drafted as 107 / 108) renumber after tel-023.

## 1. Owner answers (DEC-SCOPE-109)

| # | Question | Answer |
|---|---|---|
| PF1 | Who sees it; where rows link | `telecaller_manager` (direct reports), `it_admin` / `overseas_admin` (their team's telecallers), `super_admin` (all, optional team). Rows link to the tel-021 activity page only where the viewer may open it (manager, super_admin); division admins see plain rows — tel-021's scope is unchanged. |
| PF2 | P1 "Leads" | Distinct leads that **became the telecaller's** during the range — the B1/DB8 rule: a `lead.assign` audit row to them, or a lead they created already assigned (`lead.create`, `assigned: true`). A lead later reassigned away still counts for the range it was received in. |
| PF3 | Q-19 credit after reassignment | **Whoever did it** — calls, connected, qualified and appointments are tel-021's actor-based flow counts; conversions follow DB2 (the lead's telecaller when conversion was first recorded). |
| PF4 | Rows, sort, defaults | Every telecaller in scope, inactive ones included and marked. A Total row. Default range: the 1st of the current IST month → today. Sort by a column-header link (`?sort=calls&dir=desc`, default Calls desc, ties by name); the CSV uses the same order. Range ≤ 366 days. |

## 2. Columns (Appendix B)

| Key | Label | Definition |
|---|---|---|
| `leads` | Leads | P1 (PF2) |
| `calls` | Calls | P2 = ΣD2 |
| `connected` | Connected | P3 = ΣD3 |
| `qualified` | Qualified | P4 = ΣD11 |
| `appointments` | Appointments | P5 = ΣD7 (counselling bookings + BDM meeting requests) |
| `conversions` | Conversions | P6 = ΣD13 |

P2–P6 are `telecaller_metrics.flow_counts` over the whole range (one instant range, `day_range(from)[0]` → `day_range(to)[1]`). Because
flow counts are additive over half-open IST-day ranges, each equals the sum of the tel-021 daily figures (AC1). P1 is a new
`telecaller_metrics.leads_received(db, user_id, start, end)`, the B1 expression without B1's "still mine now" condition; `tiles()` reuses it.

`flow_counts` is called once per telecaller (no grouped variant): tel-024, in flight, adds `flow_counts_by_user` to the same module, so
tel-023 leaves that code untouched to avoid a conflict. Follow-up once tel-024 merges: switch to the grouped call.

## 3. API (§12AC)

`GET /api/v1/telecaller/manager/performance` and `GET /api/v1/telecaller/manager/performance.csv` (`.csv` registered first), in the
existing `telecaller_dashboard` router.

Query: `date_from`, `date_to` (ISO dates; default the 1st of `date_to`'s month → today, IST), `team` (`it`/`overseas`), `sort`
(`name`|`leads`|`calls`|`connected`|`qualified`|`appointments`|`conversions`, default `calls`), `dir` (`asc`|`desc`, default `desc`).

Order of checks: malformed values (FastAPI **422** list — the page passes only well-formed ones) → authenticated → role allowed (else **403** "Telecaller performance is for managers and administrators") → a division
admin's `team` must be their own (else **403**, `admin_team_filter`) → the range (**422**: `date_from > date_to`,
`date_to` after today, a span over 366 days).

```json
{ "date_from": "2026-10-01", "date_to": "2026-10-07", "team": null, "sort": "calls", "dir": "desc", "teams": ["it", "overseas"],
  "columns": [{"key": "full_name", "label": "Telecaller"}, {"key": "team", "label": "Team"}, {"key": "status", "label": "Status"},
              {"key": "leads", "label": "Leads"}, ...],
  "items": [{"user_id": "…", "full_name": "Asha", "team": "IT", "active": true, "status": "Active", "leads": 4, "calls": 80, ...}],
  "totals": {"full_name": "Total", "team": "", "status": "", "leads": 4, "calls": 80, ...} }
```

`teams` lists the teams the caller may filter by (manager: both; division admin: own; super_admin: both). `Cache-Control: private, no-store`.
Reads are not audited. The CSV reuses `agent_reports.to_csv` (BOM, on-screen labels, Total row last, `_safe_cell` against CSV injection),
writes one `AuditLog` `telecaller_performance.export` (entity `telecaller_performance` / `performance`; metadata: filters, sort, rows)
committed before the file is returned. Filename `telecaller-performance-{from}-to-{to}.csv`.

## 4. Scope (T23, T24, RBAC §2.35)

| Role | Telecallers listed |
|---|---|
| `telecaller_manager` | direct reports (`team_filter`), optionally narrowed by `team` |
| `it_admin` / `overseas_admin` | their team (`admin_team_filter`; another team → 403) |
| `super_admin` | all, optionally narrowed by `team` |
| `telecaller` and every other role | **403** |

## 5. Frontend

- `lib/telecallerPerformance.ts`: types, column list, `performanceQuery`, `sortHref`.
- `components/TelecallerPerformancePage.tsx` (server component): a GET filter form (From, To, Team when more than one team is offered),
  a `<table>` in `.table-wrap` with header sort links (`aria-sort`), names linked to `/telecaller/manager/team/[id]/activity?date={to}` for
  managers/super_admin, an "Inactive" badge, a `<tfoot>` Total row, `ReportDownloadButton` (CSV), empty state "No telecallers in your scope
  yet.", and an error note for a refused input (422 detail) or a failed read.
- Routes: `/telecaller/manager/performance` (manager, super_admin; manager nav), `/it/admin/telecaller-performance`,
  `/overseas/admin/telecaller-performance`, `/admin/telecaller-performance` (super_admin). Nav: "Performance" in `TELECALLER_MANAGER_NAV`;
  "Telecaller Performance" in the IT / Overseas admin and super admin navs.

## 6. Acceptance criteria

1. Each figure equals the sum of the tel-021 daily figures over the range (P2–P6), and P1 follows PF2.
2. A manager sees only their direct reports; a division admin only their team; super_admin all; `team` only narrows.
3. Telecaller and other roles → 403 on the JSON and the CSV; a division admin naming another team → 403.
4. CSV matches the screen: same columns, rows, order and Total; BOM; formula cells neutralised; one audit row; `text/csv`.
5. 422 on a malformed date, reversed range, future `date_to`, span > 366 days, bad team/sort/dir.
6. Sort by any column, both directions; ties by name. Inactive telecallers listed and marked.
7. Page: loading-free server render; empty and error states; keyboard-reachable sort links; responsive table (scrolls in `.table-wrap`).

## 7. Risks

- Per-telecaller loop: ~8 queries per row. A manager's direct reports are tens at most; super_admin "all" is bounded by staff size. Switch to
  tel-024's grouped counts after it merges.
- `tiles()` now calls `leads_received` — guarded by the tel-021 metrics tests.
- `navigation.ts` will conflict textually with tel-024's nav entries; resolve at merge.
