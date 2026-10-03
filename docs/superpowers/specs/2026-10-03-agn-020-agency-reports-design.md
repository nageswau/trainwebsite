# AGN-020 — Agency reports (7 new + Commission) and CSV export — design

**Status:** design approved in-session 2026-10-03 (`EXPLICIT_APPROVAL` — answers to eight structured questions and five design-section
reviews), to be recorded as `DEC-SCOPE-063` (provisional: free on `main` @ `3bde879`; renumber on merge if a parallel branch, e.g.
AGN-019, reaches `main` with `063` first).
Source item: `docs/delivery/AGENT_CRM_BACKLOG.md` ang-020 (`DERIVED_BLUEPRINT`). Depends on AGN-003/004/005, AGN-008 … AGN-014 and AGN-018,
all on `main`. Branch: `feature/agn-020-reports`. **GATE-09:** no code until this spec and its plan are approved.

## 1. Requirement and acceptance

Business requirement (`EVID-015` §2 Reports, §6 "Reports ✅ Full / ❌/Limited"): Student, Application, University, Country, Intake,
Staff performance, Enrollment and Commission reports; Staff reports "❌/Limited". The source names the reports only; their content is
decided here (R1).

Owner acceptance: each report matches fixture data; the CSV opens with correct headers; Staff without the toggle → 403.

## 2. Decisions (`DEC-SCOPE-063`, answered by the owner 2026-10-03)

| ID | Decision |
|---|---|
| R1 | **Mixed shape.** Student, Application and Enrollment are row-level lists; University, Country, Intake and Staff performance are grouped summaries with stage counts; Commission is the existing AGN-014 report, unchanged. |
| R2 | **Staff access.** Staff with `can_view_reports` see Student, Application, University, Country, Intake and Enrollment, own scope (G4 of `DEC-SCOPE-042`). Staff performance and Commission → 403 for all staff. Without the toggle → 403 on every kind (`DEC-SCOPE-044` P1). |
| R3 | **Audit CSV exports only.** One `AuditLog` row per new-report CSV; on-screen reads unaudited. The commission CSV keeps `DEC-SCOPE-051` R7 (no audit row). |
| R4 | **Intake** is parsed to month + year with the existing `intake_end` parser (AGN-013 E2); unreadable text → one "Unstructured" group. No migration (every intake column is free text). |
| R5 | **Staff performance** is AGN-020's own summary built from AGN-018's shared queries, in a new module; AGN-019 keeps its funnel and page. Whichever merges second reconciles. |
| R6 | **Per-report date basis** (inclusive UTC days, `DEC-SCOPE-051` R7 semantics): students by record created; applications and summaries by application created; enrollments by `enrollment_date`; commission unchanged. Staff filter Master only. |
| R7 | **Row cap 10,000 + paged screen.** Lists show 50 rows per page; a CSV over 10,000 rows is refused with 422 (never silently truncated). Built in memory like every existing CSV. |
| R8 | **Old portal summary:** the portal `reports` API payload, its 403 and its tests stay byte-identical; the page stops rendering that table and shows the tabbed reports (as AGN-018 did for the dashboard). |
| R9 | **Approach A:** one gated route pair `/crm/reports/{kind}` and `/crm/reports/{kind}.csv`, a new `agent_reports` service, a column-driven response; Commission tab = the existing AGN-014 panel. |

Facts that shaped the design (verified in code, `main` @ `3bde879`): agency student records have no reference code and no passport field;
agencies have no branch list (so no branch filter); `overseas_applications.intake` (String 80, default "Next intake") and
`agent_students.preferred_intake` (String 40) are free text; no `/agent/reports` route exists; no CSV in the codebase streams.

## 3. Existing behaviour (verified in code)

- `GET /api/v1/portal/overseas/agent/reports` (`api/portal.py:38-39`): staff without `can_view_reports` → 403 `REPORTS_REFUSED`
  (`core/rbac.py:118`). Payload (`services/portal.py:817-827`): Students (inner join on users — no-login students dropped),
  Applications (withdrawn included), Offers (O5), and "Paid commission" for Masters. Rendered by the generic `PortalSection`.
- `WorkflowPanel.tsx:467-476` mounts `AgentCommissionReportPanel` (AGN-014) on the reports section for non-staff.
- AGN-018 `services/agent_dashboard.py`: `agency_applications`, `offer_clause`, `_visa`, `staff_rows`; scope helpers
  `student_scope` / `application_scope` (`services/agent_students.py`), `org_member_ids` (`services/agent_orgs.py:166`).
- `_gate` (`api/agent_students.py:40`): agents of an active agency only; super_admin refused; reused by AGN-018.
- CSV precedent: AGN-014 `report.csv` (`api/workflows.py:2536`), `_safe_cell` (`api/school_bulk.py:544`, crashes on `None`),
  `_report_date` (`api/workflows.py:2441`).

## 4. Report definitions

### 4.1 Shared counting rules (AGN-018 G3, reused)

Applications = non-withdrawn. Submitted = `submitted_on IS NOT NULL` (D7). Offers = O5 (`offer_clause`; an application withdrawn after
its offer still counts). Visa apps = distinct applications with a `visa_cases` row; Visa approved = `decision = 'approved'`.
Enrolled = `status = 'enrolled'`. School-bridged applications (`school_student_id` set) are always excluded. Scope: Master = agency
(`org_member_ids`); Staff = `student_scope` / `application_scope`.

### 4.2 List reports (one row per record; 50 per page on screen)

| Kind | Rows | Columns (CSV header = on-screen label) | Date basis | Filters |
|---|---|---|---|---|
| `students` | `agent_students` in scope; default `status=active`, also `archived`, `all` | Name · Assigned staff ("CODE Name" or "Unassigned") · Preferred country · Preferred intake · Status · Created · Applications (non-withdrawn) | `agent_students.created_at` | member\*, country (preferred, trimmed, case-insensitive), status |
| `applications` | every application in scope, withdrawn included | Student · University · Country · Course · Intake · Application ref · Stage (label) · Submitted · Offer (Yes/No, O5) · Visa (None / In progress / Approved / Refused / Withdrawn) · Created | `overseas_applications.created_at` | member\*, country, university, intake, status (a stage or `withdrawn`) |
| `enrollments` | `status = 'enrolled'` | Student · University · Country · Course · Intake · Enrollment date · University student ID | `enrollment_date` (rows with no date appear only when no date filter is set) | member\*, country, university |

Order: lists by date basis descending, then id (stable paging). Student names use `OWNER_NAME` (account name, else record name);
missing → "—".

### 4.3 Summary reports (one row per group + a Total row; no paging)

Columns: Applications · Submitted · Offers · Visa apps · Visa approved · Enrolled. Date basis: application `created_at`.

| Kind | Group | Order | Filters |
|---|---|---|---|
| `universities` | university (+ its country) | Applications desc, then name | member\*, country |
| `countries` | the application university's country | Applications desc, then name | member\* |
| `intakes` | `intake_end(intake)` → `YYYY-MM` (label "Sep 2027"); `None` → "Unstructured" | month ascending, Unstructured last | member\*, country |
| `staff` (Master only) | the application student record's `assigned_member_id` (same join as `staff_rows`), plus "Unassigned"; extra first column **Students** = active records assigned, created in range | member `seq`, Unassigned last | none |

Intake folding: SQL groups by raw `intake` text with the six counts; Python folds the rows by parsed key. The `intake` filter
(`YYYY-MM` or `unstructured`) selects the distinct raw texts in scope, parses them, and filters with `IN (…)`.

Staff performance: a deactivated member is listed if they have any non-zero count in range; a reassigned student counts for the
current assignee (as AGN-018).

\* `member` filter (a member code, or `unassigned`) is Master only.

### 4.4 Data minimisation

No student email, phone, date of birth, passport or UUIDs in any report or CSV.

## 5. Backend

### 5.1 Routes — `apps/api/app/api/agent_reports.py` (new)

`APIRouter(prefix="/workflows/overseas/agent/crm", tags=["agent-reports"])`, registered in `app/main.py`.

- `GET /reports/{kind}.csv` — registered **before** the JSON route.
- `GET /reports/{kind}` — query: `date_from`, `date_to` (str, strict `YYYY-MM-DD`), `member`, `country`, `university`, `intake`,
  `status`, `page` (≥ 1).

Check order (first failure wins; a refused caller never sees 404/422):

1. `_gate(user)` → 403 (existing texts; super_admin and non-agents refused).
2. `agent_may(user, "can_view_reports")` false → 403 `REPORTS_REFUSED`.
3. `kind == "staff"` and staff → 403 "Only an agency Master can view staff performance".
4. `kind` not in `REPORT_KINDS` → 404 "Report not found".
5. Dates via `_report_date` (AGN-014 messages: format, `date_to` before `date_from`, `9999-12-31`) → 422.
6. Filters: a filter the kind does not support, `member` from staff, an unknown member code / country / university / status / intake
   key, `page < 1` → 422 naming the parameter.

Both responses: `Cache-Control: private, no-store`; one structured log line `agent_report.read` / `agent_report.export` (org, actor,
kind, scope, rows, duration — ids only).

### 5.2 Service — `apps/api/app/services/agent_reports.py` (new)

- `REPORT_KINDS`: kind → `{master_only, date_column, filters, columns, kind: "list"|"summary"}`.
- `parse_filters(user, kind, raw) -> Filters` (validation of §5.1 step 6; resolves country/university by name against the catalogue).
- `list_rows(db, user, kind, filters, page) -> (rows, total)` and `summary_rows(db, user, kind, filters) -> (rows, totals)`.
- `filter_options(db, user, kind) -> dict` — members (Master only), countries, universities, intakes, statuses present in the caller's
  scope, for the kinds that support them.
- `fold_intakes(rows)` — pure function, unit-tested.
- Imports AGN-018 / scope helpers read-only; **does not edit** `agent_dashboard.py`, `agent_students.py`, `agent_orgs.py`.

### 5.3 Schema — `schemas.py` (additive)

`AgentReportColumn {key, label}`, `AgentReportOut {kind, scope: "agency"|"own", columns, rows: list[dict[str, str|int|None]], totals:
dict|None, total, page, page_size, options, as_of}`. Codes and names only, no ids.

### 5.4 CSV

UTF-8 with BOM; `text/csv; charset=utf-8`; `Content-Disposition: attachment; filename=agency-{kind}-{from|all}-to-{to|all}.csv`; header
row = column labels; dates ISO; Yes/No; labels for stage and visa; summary CSV ends with the Total row; empty result = header only.
Every text cell through `_cell(v) = _safe_cell("" if v is None else str(v))`. Count first: `> CSV_ROW_CAP` (10,000) → 422 "This report
has N rows; narrow the filters (limit 10,000)" before any row is loaded.

### 5.5 Audit, transactions, races, performance

- CSV: `db.add(AuditLog(user_id, action="agent_report.export", entity_type="agent_report", entity_id=kind, metadata_json={scope,
  filters, rows}))`, `await db.commit()` before building the response — audit failure → 500, no file (fail closed).
- JSON: read-only; no lock, no write. One statement per summary; list = rows + `COUNT(*)` of the same filtered query.
- A report is a point-in-time read (`as_of`); concurrent edits may shift rows between pages — paging order is stable.
- `page` past the end → empty `rows`, not an error. No new index (existing ones cover `agent_id`, `student_id`, `agent_student_id`,
  `assigned_member_id`); revisit only if tests show a need, as a separate decision.

## 6. Frontend

### 6.1 Page — `components/PortalPage.tsx`

Reports branch for `role === "agent"`: `PortalSection` with `lead={<AgentReportsPanel role={…} />}` and the metrics table hidden on the
page side. The portal fetch, its 403 card and the `serverApi` call order are unchanged. Navigation unchanged.

### 6.2 `components/AgentReportsPanel.tsx` (new, client)

- Tabs (`Student360Tabs` ARIA pattern): Master — Students, Applications, Universities, Countries, Intakes, Staff performance,
  Enrollments, Commission; Staff — Students, Applications, Universities, Countries, Intakes, Enrollments. Only the active tab panel is
  mounted.
- URL state via `replaceState`: `?report=<kind|commission>&from&to&member&country&university&intake&status&page`.
- Commission tab renders the existing `AgentCommissionReportPanel` unchanged. `WorkflowPanel` no longer mounts it.
- Filter form: From / To + selects from `options`, only those the kind supports; Apply with `aria-disabled` while busy; client check
  To ≥ From.
- Table: `.table-scroll` region `aria-labelledby` the tab heading; `table compact stack` with `data-label`; Total row on summaries;
  "Showing a–b of N" + Previous/Next (`aria-disabled` at the ends); "As of" time.
- CSV: `ReportDownloadButton` (`contentType="text/csv"`, `busyLabel="Preparing CSV…"`), shown when `total > 0`.

### 6.3 `lib/agentReports.ts` (new)

URLs, `reportQuery`, `readState` / `writeState`, `csvFilename`, `isAgentReport` shape guard; types in `lib/types.ts` (additive).

### 6.4 States

| State | UI |
|---|---|
| Loading | skeleton + `role="status"` "Loading report…"; stale responses dropped |
| Empty | "No records match these filters."; CSV hidden |
| 401 | "Your session has expired" + sign-in link with `?next=` |
| 403 | the server's detail |
| 422 | message at the named field, focus moved |
| 5xx / network | "Couldn't load this report" + "Try again" |

## 7. Authorization and security

| Caller | 7 new kinds JSON/CSV | `staff` kind | Commission (AGN-014) |
|---|---|---|---|
| Master | ✅ agency | ✅ | ✅ (unchanged) |
| Staff, toggle on | ✅ own scope (except `staff`) | ❌ 403 | ❌ 403 (unchanged) |
| Staff, toggle off | ❌ 403 `REPORTS_REFUSED` | ❌ 403 | ❌ 403 |
| super_admin / other roles / inactive agency / deactivated member | ❌ 403 | ❌ 403 | unchanged |

Staff cannot widen scope (no `member` filter, options built from own scope). CSV injection neutralised. Filename ASCII-only. Toggle
changes apply on the next request (`agent_may` reads the eager-loaded membership).

## 8. Acceptance criteria and tests

| AC | Criterion | Tests |
|---|---|---|
| AC1 | each new report equals a hand-computed fixture (`agn020_helpers.reports_world`: 2 staff, assigned/unassigned, no-login student, withdrawn-after-offer, school-bridged, visa approved/refused, enrolled with/without date, intakes "Sep 2027" / "September 2027" / "09/2027" / "Next intake") | `test_agn_020_reports.py` |
| AC2 | parity with AGN-018: Countries total Applications = dashboard Applications; Offers = O5 | `test_agn_020_reports.py` |
| AC3 | CSV header row exact per kind, BOM, rows equal JSON, formula cells escaped, unicode round-trip, empty = header only, filename | `test_agn_020_reports_csv.py` |
| AC4 | toggle off → 403 on every kind × format before 404/422; toggle on → own scope; `staff` → 403 for staff; super_admin / non-agent → 403 | `test_agn_020_reports_access.py` |
| AC5 | filters: inclusive UTC days per date basis; member (staff → 422); country, university, intake incl. `unstructured`, status; unknown → 422 | `test_agn_020_reports.py` |
| AC6 | paging 50, total, past-end empty; CSV > cap → 422, no audit row | `test_agn_020_reports_csv.py` (cap monkeypatched) |
| AC7 | one `agent_report.export` audit row per CSV, no names; JSON none; commission CSV none | `test_agn_020_reports_csv.py` |
| AC8 | tabs per role, URL state, all states, pagination, CSV button; 375 px; keyboard tabs; axe clean | `AgentReportsPanel.test.tsx`, `lib/agentReports.test.ts`, `PortalPage.agentReports.test.tsx`, `agn-020-reports.spec.ts` |
| AC9 | AGN-003 matrix, AGN-014, AGN-018 suites and the portal reports payload unchanged and green | full suites |

Unit: `fold_intakes`, `parse_filters`. Gates: full pytest, vitest, `tsc`, lint, Playwright agn-003 / agn-014 / agn-018 / agn-020.

## 9. Regression risks and deliberate test updates

| Risk | Mitigation |
|---|---|
| `PortalPage.tsx` / `WorkflowPanel.tsx` shared by every role | change only the agent-reports branch; existing call-list tests unchanged |
| `agent_dashboard.py` and scope helpers (AGN-019 may edit concurrently) | imported read-only, never edited |
| AGN-014 panel re-parented | component untouched; its unit tests unchanged |
| `{kind}` route swallowing `.csv` | `.csv` registered first; test `students.csv` |
| page vs dashboard numbers | AC2 parity |
| Decision ID collision | `DEC-SCOPE-063` provisional |

Deliberate updates (structure, not behaviour): `WorkflowPanel.agentCommissionReport.test.tsx` (panel now under the Commission tab);
`agn-014-commission-master.spec.ts` (opens `?report=commission`).

## 10. Out of scope

The funnel chart and branch filter (AGN-019); per-staff commission (`DEC-SCOPE-051` R2, parked); streaming exports; scheduled or emailed
reports; charts; changing the portal `reports` payload; a structured intake column.

## 11. Documentation

`PRODUCT_DECISION_REGISTER.md` `DEC-SCOPE-063`; `RBAC_MATRIX.md`; `API_CONTRACT.md`; `SCREEN_CATALOG.md` / `screen_catalog.json`;
`RTM.md`; `ENHANCEMENT_BACKLOG.md` §AGN-020; `CONFLICT_MATRIX.md` C-10 update (these reports lifted out of "parked").
