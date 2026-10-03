# AGN-020 Agency Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seven new agency reports (Students, Applications, Enrollments lists; Universities, Countries, Intakes, Staff performance
summaries) plus the existing Commission report, as a tabbed Reports page with filters and audited, throttled CSV export.

**Architecture:** One read-only service (`services/agent_reports.py`) builds column-driven reports over AGN-018's scope helpers;
one router (`api/agent_reports.py`) exposes `GET …/crm/reports/{kind}` and `{kind}.csv` with a fixed authorization order. The
frontend replaces the generic table on `/overseas/agent/reports` with `AgentReportsPanel` (tabs → filters → table), embedding
the unchanged AGN-014 commission panel as the last tab.

**Tech Stack:** FastAPI, async SQLAlchemy 2, PostgreSQL, pytest-asyncio; Next.js 15 / React 19, Vitest + Testing Library,
Playwright.

**Spec:** `docs/superpowers/specs/2026-10-03-agn-020-agency-reports-design.md` (read it; this plan argues from it).

## Global Constraints

- No migration, no new dependency, no edit to `services/agent_dashboard.py`, `services/agent_students.py`, `services/agent_orgs.py`,
  `core/rbac.py`, `api/portal.py`, `services/portal.py`, `AgentCommissionReportPanel.tsx`, `ReportDownloadButton.tsx`, `navigation.ts`.
- Check order: `_gate` 403 → `REPORTS_REFUSED` 403 → staff on `staff` 403 → unknown kind 404 → 422 → (CSV) 429.
- 422 for inputs: `{"detail": [{"loc": ["query", "<param>"], "msg": "...", "type": "value_error"}]}`; 403/404/429 string `detail`.
- Page convention `items/total/limit/offset`; `limit` 1–100 default 50; `offset` 0–9,950.
- `CSV_ROW_CAP = 10_000`; export throttle 30 per user per 10 minutes; audit action `agent_report.export`.
- Dates: strict `YYYY-MM-DD`, inclusive UTC days; messages as AGN-014.
- No ids, email, phone, DOB, passport in JSON or CSV. Logs: ids, kind, filter keys, counts, timing.
- Comments cite AGN-020 / DEC-SCOPE-067 and spec sections, in the surrounding style.
- **Lite testing (owner instruction 2026-10-03):** run only the new test files and the directly affected existing files named in
  each task; the owner runs full suites separately.

## Review Focus

1. A staff member whose toggle is switched off between page load and Apply → the next request is 403 and the panel shows the
   refusal, not stale data (Task 2 access test + Task 9 panel 403 test).
2. An application of a student with no login, and one linked only by login (pre-AGN-008) → both counted and attributed to the
   right assignee (Task 3 fixture rows r1/r2).
3. A filter value with formula characters or Unicode (`=cmd`, `Zoë`) → escaped in CSV, intact in JSON (Task 6).
4. `offset` beyond the end → empty items with the correct `total` (Task 4).
5. Rapid tab switching → only the last response renders (Task 9 stale-drop test).

---

## File map

| File | Responsibility |
|---|---|
| `apps/api/app/services/agent_reports.py` (new) | kinds, filter parsing, intake folding, report queries, options |
| `apps/api/app/api/agent_reports.py` (new) | routes, authorization order, 422 shaping, CSV, audit, throttle, logs |
| `apps/api/app/schemas.py` (modify, additive) | `AgentReportColumn`, `AgentReportOption`, `AgentReportOut` |
| `apps/api/app/main.py` (modify) | register the router |
| `apps/api/tests/agn020_helpers.py` (new) | `reports_world` fixture + hand counts |
| `apps/api/tests/test_agn_020_reports.py` (new) | filters, folding, report values, parity, paging, options |
| `apps/api/tests/test_agn_020_reports_access.py` (new) | authorization matrix and check order |
| `apps/api/tests/test_agn_020_reports_csv.py` (new) | CSV format, escaping, cap, audit, throttle |
| `apps/web/lib/agentReports.ts` (new) | URLs, kinds, query/URL state, filename, shape guard |
| `apps/web/lib/types.ts` (modify, additive) | report types |
| `apps/web/components/AgentReportTable.tsx` (new) | table + pager presentation |
| `apps/web/components/AgentReportFilters.tsx` (new) | filter form |
| `apps/web/components/AgentReportsPanel.tsx` (new) | tabs, URL state, fetch, states |
| `apps/web/components/PortalPage.tsx` (modify) | agent reports branch renders the panel |
| `apps/web/components/WorkflowPanel.tsx` (modify) | stop mounting the commission panel on reports |
| `apps/web/app/globals.css` (modify) | `.num`, `.report-busy` rules |
| web tests (new/rewritten) | see Tasks 7–10 |
| docs | DEC-SCOPE-067 and the §11 list (Task 11) |

Commands (from `apps/api`, isolated DB on port 5440):
`$env:DATABASE_URL="postgresql+asyncpg://edusphere:edusphere@localhost:5440/edusphere"` then `.venv/Scripts/python -m pytest -q <file>`.
Web (from `apps/web`): `npx vitest run <file>`, `npm run typecheck`, `npm run lint`.

---

### Task 1: Report kinds, filter parsing and intake folding

**Files:**
- Create: `apps/api/app/services/agent_reports.py`
- Create: `apps/api/tests/agn020_helpers.py`
- Test: `apps/api/tests/test_agn_020_reports.py`

**Interfaces:**
- Produces: `REPORT_KINDS: dict[str, ReportKind]`, `ReportKind(title, summary, filters: frozenset[str], master_only=False)`,
  `Filters` dataclass, `ReportInputError(param, message)`, `async parse_filters(db, user, kind: str, raw: dict[str, str | None]) -> Filters`,
  `parse_page(limit: str | None, offset: str | None) -> tuple[int, int]`, `intake_key(text) -> tuple[str, str]`,
  `CSV_ROW_CAP = 10_000`, `PAGE_SIZE = 50`; helper `reports_world(db) -> dict`.

- [ ] **Step 1: Write the failing tests** — `fold`/`intake_key` (pure), `parse_page`, and `parse_filters` cases: unsupported filter,
  staff sending `member`, another org's member code (same text as unknown), unknown slug, bad intake, bad status, date errors with
  AGN-014 wording, over-long value.

```python
from app.services.agent_reports import ReportInputError, intake_key, parse_filters, parse_page

@pytest.mark.parametrize(("text", "key"), [("Sep 2027", "2027-09"), ("September 2027", "2027-09"), ("09/2027", "2027-09"), ("2027-09", "2027-09"), ("Next intake", "unstructured"), ("", "unstructured")])
def test_intake_key_folds_spellings(text, key):
    assert intake_key(text)[0] == key

@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "raw", "param"), [
    ("countries", {"university": "x"}, "university"),          # not offered by this kind
    ("applications", {"intake": "2027-13"}, "intake"),
    ("applications", {"status": "nope"}, "status"),
    ("students", {"status": "enquiry"}, "status"),
    ("applications", {"country": "no-such-slug"}, "country"),
    ("applications", {"date_from": "20260101"}, "date_from"),
    ("applications", {"date_from": "2026-02-02", "date_to": "2026-02-01"}, "date_to"),
    ("applications", {"date_to": "9999-12-31"}, "date_to"),
    ("applications", {"member": "x" * 121}, "member"),
])
async def test_bad_filters_name_their_param(db_session, kind, raw, param): ...
```

- [ ] **Step 2: Run** `pytest -q tests/test_agn_020_reports.py` → FAIL (`ModuleNotFoundError: app.services.agent_reports`).
- [ ] **Step 3: Implement** the module header, `Column`, `ReportKind`, `REPORT_KINDS` (filters per spec §4/§5.1), `Filters`,
  `ReportInputError`, `parse_page`, `intake_key` (wraps `agent_applications.intake_end`), `parse_filters` (member codes resolved
  inside `user.agent_membership.org_id`; `country`/`university` by catalogue slug; students' `country` = trimmed lower text;
  intake key → the distinct raw texts in scope whose key matches, stored as `intake_texts`).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(agn-020): report kinds, filter parsing and intake folding`.

### Task 2: JSON route, schema and the authorization order

**Files:**
- Create: `apps/api/app/api/agent_reports.py`
- Modify: `apps/api/app/schemas.py` (append after `AgentDashboardOut`), `apps/api/app/main.py` (router tuple)
- Modify: `apps/api/app/services/agent_reports.py` (`report()` dispatcher + `countries` summary)
- Test: `apps/api/tests/test_agn_020_reports_access.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `async report(db, user, kind, filters, *, limit, offset) -> dict` returning the `AgentReportOut` shape;
  route functions `read_report`, `export_report`; `STAFF_REPORT_REFUSED`.

- [ ] **Step 1: Failing tests** — matrix over kinds × {json, csv} for: staff toggle off → 403 `REPORTS_REFUSED` even with
  bad params and an unknown kind; staff toggle on → `staff` 403 `STAFF_REPORT_REFUSED`; super_admin and counselor → 403;
  Master unknown kind → 404 "Report not found"; Master bad date → 422 list shape with `loc == ["query", "date_from"]`;
  `students.csv` is not swallowed by `{kind}`; `Cache-Control: private, no-store`; toggle switched off then next request → 403.
- [ ] **Step 2: Run** → FAIL (404 on the route).
- [ ] **Step 3: Implement** the router (`.csv` route first), `_authorize`, `_invalid`, the schema, registration, and `report()` for
  `countries` (enough for 200s).
- [ ] **Step 4: Run** → PASS. Also run `tests/test_agn_018_dashboard.py` (shared helpers imported) → PASS.
- [ ] **Step 5: Commit** `feat(agn-020): report routes with the fixed authorization order`.

### Task 3: Summary reports — universities, countries, intakes, staff (+ parity)

**Files:** Modify `services/agent_reports.py`; `tests/agn020_helpers.py` (hand counts); test `tests/test_agn_020_reports.py`.

- [ ] **Step 1: Failing tests** — on `reports_world`: Countries rows/totals equal hand counts; Countries total applications /
  offers / visa / enrolled equal the AGN-018 dashboard headline for Master and s1 (parity); Universities include country; Intakes
  fold the four spellings to "Sep 2027" + "Unstructured" last; Staff rows per member + Unassigned with Students column; staff
  (toggle on) see only their own counts; date filter is inclusive UTC days on application `created_at`; `member` narrows.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `_stage_counts()` (FILTER aggregates: applications = non-withdrawn, submitted, offers = `offer_clause()`,
  visa apps / approved via `EXISTS`, enrolled), `_assignee()` (record's assignee, else the login's record's), `_app_where()`,
  `_summary()` for the four kinds, totals summed in Python.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(agn-020): summary reports with dashboard parity`.

### Task 4: List reports — students, applications, enrollments (+ paging)

**Files:** Modify `services/agent_reports.py`; test `tests/test_agn_020_reports.py`.

- [ ] **Step 1: Failing tests** — Students default active, `status=all|archived`, Applications column = non-withdrawn count,
  country text match case-insensitive; Applications list includes withdrawn, Offer Yes/No per O5, Visa label priority
  (Approved > Refused > Withdrawn > In progress > None), `intake=unstructured`; Enrollments by `enrollment_date` (undated row only
  without a date filter); paging `limit=2` → `total` correct, `offset` past end → `items == []` and `total` correct; no UUID, email or
  phone anywhere in `response.text`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `_students()`, `_applications()`, `_enrollments()` with `count(*) OVER ()`; fallback count when a page
  is empty and `offset > 0`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(agn-020): list reports with single-snapshot paging`.

### Task 5: Filter options

**Files:** Modify `services/agent_reports.py`; test `tests/test_agn_020_reports.py`.

- [ ] **Step 1: Failing tests** — Master options: members (codes + Unassigned), countries/universities present in scope (slugs),
  intakes folded, statuses; staff options have no `members` key and only their own countries; noise agency's country absent.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** `_options()`; include in `report()`. **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(agn-020): filter options from the caller's scope`.

### Task 6: CSV export — format, escaping, cap, audit, throttle

**Files:** Modify `api/agent_reports.py`; test `tests/test_agn_020_reports_csv.py`.

- [ ] **Step 1: Failing tests** — header row equals column labels per kind; BOM; rows equal JSON items; summary ends with Total;
  `=cmd` / `+1` / `@x` names escaped with `'`; `Zoë` round-trips; empty = header only; filename
  `agency-{kind}-{from|all}-to-{to|all}.csv`; cap monkeypatched to 2 → 422 string detail, no audit row; one audit row per export
  with metadata `{scope, filters, rows}` and no student names; JSON read writes no audit row; 30 seeded export rows → 31st → 429 with
  `Retry-After`, no audit row, another user unaffected; commission CSV still writes none.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** `to_csv`, `_cell`, lock on own membership row, `_export_wait`, audit + commit,
  logs. **Step 4: Run** → PASS; also `tests/test_agn_014_commission_reports.py` → PASS.
- [ ] **Step 5: Commit** `feat(agn-020): audited, throttled CSV export`.

### Task 7: Frontend library and types

**Files:** Create `apps/web/lib/agentReports.ts`; modify `apps/web/lib/types.ts`; test `apps/web/tests/lib/agentReports.test.ts`.

- [ ] **Step 1: Failing tests** — `tabsFor("master")` 8 tabs, `tabsFor("staff")` 6 (no staff/commission); `readState` drops
  unsupported filters and malformed dates, unknown/forbidden report → first tab; `reportQuery` omits empty values;
  `csvFilename("countries", "", "2026-09-30")`; `isAgentReport` rejects `{}` and accepts a page.
- [ ] **Step 2–4:** run → FAIL, implement, run → PASS. **Step 5: Commit** `feat(agn-020): reports client library`.

### Task 8: AgentReportTable

**Files:** Create `apps/web/components/AgentReportTable.tsx`; test `apps/web/tests/components/AgentReportTable.test.tsx`.

- [ ] **Step 1: Failing tests** — region labelled by heading; `<th scope="col">` labels; first cell row header; numeric cells
  `.num`; totals in `<tfoot>`; every `<td>` has `data-label`; pager text "Showing 51–100 of 312", Previous `aria-disabled` on the
  first page, Next calls `onPage(100)`; values rendered as text (`<b>x</b>` shows literally).
- [ ] **Step 2–4.** **Step 5: Commit** `feat(agn-020): report table`.

### Task 9: AgentReportFilters and AgentReportsPanel

**Files:** Create `AgentReportFilters.tsx`, `AgentReportsPanel.tsx`; tests `AgentReportFilters.test.tsx`, `AgentReportsPanel.test.tsx`.

- [ ] **Step 1: Failing tests** — filters render only supported controls with labels; To < From blocks submit with the server's
  text; Clear resets; panel: tabs per role, arrow keys move and activate, URL written via `replaceState`, first-load skeleton
  (`aria-busy`), refetch keeps the old table dimmed, stale response dropped, empty-without-filters vs empty-with-filters (Clear),
  401 sign-in link, 403 server detail, 422 message under the named field with focus, 5xx Try again, CSV button hidden when total 0,
  Commission tab renders the commission panel (mocked).
- [ ] **Step 2–4.** **Step 5: Commit** `feat(agn-020): reports panel with filters and states`.

### Task 10: Page wiring

**Files:** Modify `PortalPage.tsx`, `WorkflowPanel.tsx`, `globals.css`; rewrite `tests/components/WorkflowPanel.agentCommissionReport.test.tsx`;
create `tests/components/PortalPage.agentReports.test.tsx`.

- [ ] **Step 1: Failing tests** — agent (master/staff) on reports → panel rendered, generic table absent, `serverApi` calls
  unchanged (`/auth/me`, portal payload, unread count); super_admin keeps `PortalSection`; WorkflowPanel no longer renders the
  commission heading on reports for any agent.
- [ ] **Step 2–4.** Run the two files + `PortalPage.agentDashboard.test.tsx`, `AgentCommissionReportPanel.test.tsx`; typecheck; lint.
- [ ] **Step 5: Commit** `feat(agn-020): the Reports page renders the tabbed reports`.

### Task 11: Playwright spec and documentation

**Files:** Create `apps/web/tests/e2e/agn-020-reports.spec.ts`; modify `apps/web/tests/e2e/agn-014-commission-master.spec.ts`
(open `?report=commission`); docs per spec §11 with `DEC-SCOPE-067`.

- [ ] **Step 1:** write the spec (Master tabs + CSV headers; staff toggle on: 6 tabs; toggle off: refusal text; 375 px no
  horizontal overflow). It runs in the owner's browser-validation session (full stack required).
- [ ] **Step 2:** docs. **Step 3: Commit** `docs(agn-020): DEC-SCOPE-067, contracts, RBAC, screens, RTM; e2e spec`.
