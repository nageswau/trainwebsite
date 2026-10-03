# AGN-020 — Agency reports (7 new + Commission) and CSV export — design

**Status:** design approved in-session 2026-10-03 (`EXPLICIT_APPROVAL` — answers to eight structured questions and five design-section
reviews), recorded as `DEC-SCOPE-066` (drafted as `063`; renumbered on merging `main` @ `cf356ca`, where `063`–`065` are bdm-010,
AGN-022 and bdm-003).
Source item: `docs/delivery/AGENT_CRM_BACKLOG.md` ang-020 (`DERIVED_BLUEPRINT`). Depends on AGN-003/004/005, AGN-008 … AGN-014 and AGN-018,
all on `main`. Branch: `feature/agn-020-reports`. **GATE-09:** no code until this spec and its plan are approved.

## 1. Requirement and acceptance

Business requirement (`EVID-015` §2 Reports, §6 "Reports ✅ Full / ❌/Limited"): Student, Application, University, Country, Intake,
Staff performance, Enrollment and Commission reports; Staff reports "❌/Limited". The source names the reports only; their content is
decided here (R1).

Owner acceptance: each report matches fixture data; the CSV opens with correct headers; Staff without the toggle → 403.

## 2. Decisions (`DEC-SCOPE-066`, answered by the owner 2026-10-03)

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
| R10 | **Export throttle** (security review, owner-approved): at most 30 new-report CSV exports per user per 10 minutes, counted from the caller's own `agent_report.export` audit rows (the AGN-008/009/011 no-new-table pattern); over the budget → 429 with `Retry-After`. JSON reads are not throttled. |

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
- `GET /reports/{kind}` — query (all declared `str | None`, validated in the handler **after** authorization, as AGN-014 does, so an
  int-typed `Query` cannot answer a refused caller with 422 first):

| Param | Kinds | Value |
|---|---|---|
| `date_from`, `date_to` | all | strict `YYYY-MM-DD` (`_report_date`) |
| `member` | all but `staff`; Master only | a member code of the caller's org (`ABC-S001`) or `unassigned` |
| `country` | students (preferred-country text, exact after trim, case-insensitive — no `LIKE`), applications, universities, intakes, enrollments | catalogue `countries.slug` (students: the free text, ≤ 120 chars) |
| `university` | applications, enrollments | catalogue `universities.slug` (names are not unique; slugs are) |
| `intake` | applications | `YYYY-MM` or `unstructured` |
| `status` | students (`active`/`archived`/`all`), applications (a stage or `withdrawn`) | enum |
| `limit`, `offset` | list kinds (JSON only) | `limit` 1–100, default 50; `offset` 0–9,950 (the CSV cap bounds paging too) — the codebase's `Page` convention |

Every value is length-capped (≤ 120 chars) before use; no value reaches SQL except as a bound parameter.

Check order (first failure wins; a refused caller never sees 404/422):

1. `_gate(user)` → 403 (existing texts; super_admin and non-agents refused).
2. `agent_may(user, "can_view_reports")` false → 403 `REPORTS_REFUSED`.
3. `kind == "staff"` and staff → 403 "Only an agency Master can view staff performance".
4. `kind` not in `REPORT_KINDS` → 404 "Report not found".
5. Dates via `_report_date` (AGN-014 messages: format, `date_to` before `date_from`, `9999-12-31`) → 422.
6. Filters: a filter the kind does not support, `member` from staff, an unknown member code (including another org's — same message,
   no cross-tenant oracle) / country / university / status / intake key, `limit`/`offset` out of range → 422.
7. CSV only: export throttle (R10) → 429 + `Retry-After`.

422 body: FastAPI's list shape, `{"detail": [{"loc": ["query", "<param>"], "msg": "<message>", "type": "value_error"}]}`, so the panel
maps the error to its field by `loc` (the existing `detailMessage` already reads this shape). Date messages keep AGN-014's wording.
403/404/429 keep the codebase's string `detail`.

Both responses: `Cache-Control: private, no-store`; one structured log line `agent_report.read` / `agent_report.export` (org id,
actor id, kind, scope, filter **keys** set, rows, duration — no filter values, no names).

### 5.2 Service — `apps/api/app/services/agent_reports.py` (new)

- `REPORT_KINDS`: kind → `{master_only, date_column, filters, columns, kind: "list"|"summary"}`.
- `parse_filters(db, user, kind, raw) -> Filters` (validation of §5.1 step 6; resolves country/university slugs against the catalogue
  and member codes within the caller's org only). Raises a `ReportInputError(param, message)` the route turns into the 422 list shape.
- `list_rows(db, user, kind, filters, limit, offset, cap=None) -> (rows, total)` — one statement: rows plus `count(*) OVER ()`, so the
  page and its total come from one snapshot. `summary_rows(db, user, kind, filters) -> (rows, totals)` — one statement.
- `filter_options(db, user, kind) -> dict` — members (Master only), countries, universities, intakes, statuses present in the caller's
  scope, for the kinds that support them.
- `fold_intakes(rows)` — pure function, unit-tested.
- Imports AGN-018 / scope helpers read-only; **does not edit** `agent_dashboard.py`, `agent_students.py`, `agent_orgs.py`.

### 5.3 Schema — `schemas.py` (additive)

`AgentReportColumn {key, label, numeric: bool}`; `AgentReportOption {value, label}`; `AgentReportOut {kind, scope: "agency"|"own",
columns, items: list[dict[str, str | int | None]], totals: dict | None, total, limit, offset, options: dict[str, list[AgentReportOption]],
as_of}`. `items/total/limit/offset` follow the codebase's `Page` convention (`schemas.TransferRequestPage`, web `lib/apiErrors.ts`
`Page`/`isPage`); summaries return every group with `limit = total`, `offset = 0`. Every item's keys are exactly the column keys.
Option values are slugs and member codes, never ids.

### 5.4 CSV

UTF-8 with BOM; `text/csv; charset=utf-8`; `Content-Disposition: attachment; filename=agency-{kind}-{from|all}-to-{to|all}.csv`; header
row = column labels; dates ISO; Yes/No; labels for stage and visa; summary CSV ends with the Total row; empty result = header only.
Every text cell through `_cell(v) = _safe_cell("" if v is None else str(v))`; integers are written as integers (never escaped, never
negative). Cap check without a count/fetch race: the list query runs with `LIMIT CSV_ROW_CAP + 1`; more than `CSV_ROW_CAP` (10,000)
rows → 422 "This report has more than 10,000 rows; narrow the filters" and nothing is audited or returned. `Content-Disposition:
attachment; filename="agency-{kind}-{from|all}-to-{to|all}.csv"` (quoted; built only from the validated kind and dates).

### 5.5 Audit, throttle, transactions, races, performance

CSV sequence, one transaction:

1. checks 1–6 (§5.1);
2. `SELECT … FOR UPDATE` on the caller's own `agent_org_members` row — serialises one user's exports so the throttle count cannot be
   raced by parallel downloads; other users are not blocked;
3. throttle: the caller's `agent_report.export` audit rows in the last 10 minutes (`audit_logs.user_id` and `action` are indexed),
   newest first, `LIMIT 30`; 30 present → 429 with `Retry-After` = seconds until the oldest leaves the window (a local
   `EXPORT_WINDOW`; `agent_orgs.retry_after` is fixed to 24 h and is not changed);
4. the rows (`LIMIT cap + 1`) and the CSV text, built in memory;
5. `db.add(AuditLog(user_id, action="agent_report.export", entity_type="agent_report", entity_id=kind, metadata_json={scope, filters:
   {param: value}, rows}))` — filter values are slugs, codes, dates and enums only; no student names;
6. `await db.commit()`, then return the file. A failed audit write → 500 and no file (fail closed); a refused export (403/404/422/429)
   writes nothing.

- JSON: read-only; no lock, no write, no commit.
- HTTP semantics: the CSV stays a `GET` (a download link, the AGN-014 precedent, and `ReportDownloadButton` fetches with GET); the
  audit row is a log of the read, not a state change of the report. A retried download writes a second audit row, by design.
- A report is a point-in-time read (`as_of`); concurrent edits may shift rows between pages — paging order is stable (date basis,
  then id).
- `offset` past the end → empty `items`, not an error. No new index (existing ones cover `agent_id`, `student_id`,
  `agent_student_id`, `assigned_member_id`, `audit_logs.user_id`/`action`); revisit only if tests show a need, as a separate decision.

## 6. Frontend

### 6.1 Page — `components/PortalPage.tsx`

Reports branch for `role === "agent"`: `PortalSection` with `lead={<AgentReportsPanel role={…} />}` and the metrics table hidden on the
page side. The portal fetch, its 403 card and the `serverApi` call order are unchanged. Navigation unchanged.

### 6.2 Components (new, client; each under ~200 lines, composed — no new design primitives)

| Component | Job |
|---|---|
| `AgentReportsPanel.tsx` | container: role → tab list, URL state, fetch + stale-drop, state machine; renders the two below or the Commission panel |
| `AgentReportFilters.tsx` | the filter form for one kind |
| `AgentReportTable.tsx` | presentation only: columns + items + totals → table; pager |

Existing pieces reused: `.s360-tab` styling (already a horizontal scroll strip with scroll-snap under 980 px, QA-01 overflow fix
included), `.analytics-form` (filter row), `.pager`, `.kpi-skeleton`, `.table-scroll` + `table compact stack` (phone layout,
QA18-04), `SearchableSelect` (ENH-031) for the university filter (long list), `FormMessage`, `ReportDownloadButton`,
`AgentCommissionReportPanel` (unchanged), `detailMessage`, `isPage`, `SESSION_EXPIRED` / `SIGN_IN_PATH`.

**Hierarchy.** `PortalSection` keeps the page `h1`. The panel is one full-width `action-card` (spans the grid like
`.commission-report`) with `h2` "Reports"; each tab panel has an `h3` (the report name, e.g. "Applications by country") and a one-line
description of what is counted ("Applications created in the selected dates; withdrawn excluded"). Summary result → toolbar row:
"N rows · As of 14:05" left, Download CSV right.

**Tabs.** Horizontal `role="tablist"` `aria-label="Reports"`, roving `tabIndex`, Left/Right/Home/End move focus **and** activate
(Student360Tabs' automatic activation; the stale-drop makes rapid arrowing safe), visible focus ring, active tab scrolled into view.
Master: Students · Applications · Universities · Countries · Intakes · Staff performance · Enrollments · Commission. Staff:
Students · Applications · Universities · Countries · Intakes · Enrollments. An unknown or role-forbidden `?report=` falls back to the
first tab (the server refuses anyway). Only the active `role="tabpanel"` is mounted, so label text ("From", "To", "Download CSV") is
unique on the page.

**URL state.** `?report=<kind|commission>&from&to&member&country&university&intake&status&offset` via `replaceState` (no history
entries; refresh / Back / a shared link keep the view). Dates are shared by every tab, including Commission (its panel already reads
and writes `from`/`to` and keeps other params). Switching tab keeps the dates, drops filters the new kind does not support, resets
`offset`.

**Filters (form).** `<form>` with a visible `<label>` per control; native `<input type="date">` From / To; native `<select>` for
member, country, intake, status (each with an "All …" first option); `SearchableSelect` for university. Only the controls the kind
supports render. Enter submits; "Apply" (`aria-disabled` while loading) and "Clear filters" (resets to dates-only). Client check To ≥
From before fetching (same text as the server). A 422 puts the message under the control named by `detail[0].loc[1]`, links it via
`aria-describedby`, sets `aria-invalid`, and moves focus there. Controls wrap on phones (`.analytics-form` flex-wrap; QA-022-05
min-width fix applies).

**Table.** `<table className="table compact stack">` in a `.table-scroll` region (`tabIndex=0`, `role="region"`,
`aria-labelledby` the `h3`); `<caption className="visually-hidden">` with the applied filters; `<th scope="col">`; first cell
`<th scope="row">`; numeric columns right-aligned with `font-variant-numeric: tabular-nums` (one added rule, `.num`); summary Total
row in `<tfoot>`; every `<td>` has `data-label` for the phone layout. Values are rendered as text nodes only (no
`dangerouslySetInnerHTML`).

**Pager (lists).** `.pager`: "Showing 51–100 of 312" (`role="status"`, polite) + Previous / Next buttons (`aria-disabled` at the
ends). After a page change focus moves to the table region, so keyboard and screen-reader users land on the new rows.

**CSV.** `ReportDownloadButton` (`contentType="text/csv"`, `busyLabel="Preparing CSV…"`, filename from `lib/agentReports.ts`), with
the hint "Up to 10,000 rows". Hidden when `total === 0`. Its existing `failureText` shows the server's 422 (over the cap) and 429
(throttle) messages; nothing new in the button.

### 6.3 `lib/agentReports.ts` (new)

`REPORTS_URL`, `REPORT_KINDS` (labels, descriptions, which filters, Master-only), `reportQuery`, `readState` / `writeState`,
`csvFilename(kind, from, to)`, `isAgentReport` shape guard (uses `isPage`); types in `lib/types.ts` (additive).

### 6.4 States

| State | UI |
|---|---|
| First load | `.kpi-skeleton` blocks shaped like the toolbar and 5 table rows, `aria-busy="true"`, and `role="status"` "Loading report…" |
| Refetch (filter, page, tab) | previous table stays visible, dimmed, `aria-busy="true"` on the region; Apply `aria-disabled`; a response for an older request is dropped (`latest` ref) |
| Empty, no filters | "No students yet." / "No applications yet." (per kind) — `role="status"` |
| Empty, with filters | "No records match these filters." + "Clear filters" button; CSV hidden |
| 401 | `SESSION_EXPIRED` + sign-in link with `?next=` the current URL; table cleared |
| 403 | the server's detail (e.g. `REPORTS_REFUSED` when the toggle is switched off mid-session); table cleared |
| 422 | field message as above; the previous table stays |
| 5xx / network | "Couldn't load this report." + "Try again" (re-requests the last attempted query); previous table stays |

**Perceived performance.** No new dependencies or global state; the panel fetches only the active tab; the first request starts on
mount; dates persist across tabs so switching tabs is one request.

**Responsive / mobile.** Checked at 320, 375, 768, 1024 and 1440 px: tab strip scrolls horizontally without widening the page; filter
controls wrap one per row under 640 px; tables become labelled blocks (`stack`); the CSV button and pager wrap below the result line;
touch targets ≥ 44 px (`.s360-tab` min-height).

## 7. Authorization and security

| Caller | 7 new kinds JSON/CSV | `staff` kind | Commission (AGN-014) |
|---|---|---|---|
| Master | ✅ agency | ✅ | ✅ (unchanged) |
| Staff, toggle on | ✅ own scope (except `staff`) | ❌ 403 | ❌ 403 (unchanged) |
| Staff, toggle off | ❌ 403 `REPORTS_REFUSED` | ❌ 403 | ❌ 403 |
| super_admin / other roles / inactive agency / deactivated member | ❌ 403 | ❌ 403 | unchanged |

Staff cannot widen scope (no `member` filter, options built from own scope). CSV injection neutralised. Filename ASCII-only. Toggle
changes apply on the next request (`agent_may` reads the eager-loaded membership).

### 7.1 Threat review (security-and-hardening, 2026-10-03)

Trust boundary: the query string and path of two `GET` routes. Assets: agency student names, application and enrollment data, staff
performance. No new auth flow, secret, upload, outbound call or LLM.

| Area | Finding → control |
|---|---|
| Authentication | existing `get_current_user` (httpOnly, `SameSite=Lax`, `Secure` per config cookies); no new token or session handling. A deactivated member or suspended agency is refused by `_gate` on the next request (session version unchanged). |
| Authorization / role escalation | server-side on every request, in the fixed order of §5.1; nav and tab hiding are cosmetic. `staff` kind and commission routes stay Master-only. Toggle read per request. |
| IDOR / tenant isolation | no record ids in the API. Every query carries `org_member_ids` (and the staff clauses). `member` codes resolve inside the caller's org only; another org's code gets the same 422 as an unknown one. `country`/`university` are global catalogue slugs and only narrow an already-scoped query. Options lists come from the caller's scope, so they reveal nothing outside it. |
| Input validation | allowlisted kinds and params per kind; strict date regex; enums; slugs/codes resolved against the DB; ≤ 120 chars; `limit` 1–100, `offset` 0–9,950. Unknown params ignored (FastAPI default) — harmless, nothing reads them. |
| SQL injection | SQLAlchemy expressions and bound parameters only; no `text()`, no string-built SQL; the students country filter is equality on `lower(trim())`, never `LIKE` (no wildcard widening). |
| XSS | React text rendering only; no `dangerouslySetInnerHTML`; column labels come from the server's fixed list, cell values rendered as text. |
| CSV / formula injection | `_safe_cell` on every text cell (`= + - @ \t \r`), `None` coalesced first; numbers are integers. BOM + UTF-8 for safe Unicode. |
| CSRF | both routes are `GET`; JSON is unreadable cross-origin (CORS allows only `frontend_url`). A cross-site top-level navigation could trigger a CSV download onto the victim's own device and one audit row; nothing leaves to the attacker, and the throttle bounds the noise. Accepted, recorded. |
| Sensitive data / logs | no email, phone, DOB, passport, UUIDs in reports. Structured logs carry ids, kind, filter keys, counts and timing — no names or filter values. Audit metadata carries slugs/codes/dates/enums and the row count — no student names. Error bodies are fixed strings; 500s expose no internals (existing handler). |
| Rate limiting / DoS | R10 export throttle (30 / 10 min / user, 429 + `Retry-After`), 10,000-row cap, `limit ≤ 100`, `offset` bound; JSON summaries are single aggregate statements. |
| Caching | `Cache-Control: private, no-store` on JSON and CSV. |
| Audit / repudiation | one `agent_report.export` row per successful export, committed before the file is returned; fail closed. |
| Secrets / dependencies | none added. |

## 8. Acceptance criteria and tests

| AC | Criterion | Tests |
|---|---|---|
| AC1 | each new report equals a hand-computed fixture (`agn020_helpers.reports_world`: 2 staff, assigned/unassigned, no-login student, withdrawn-after-offer, school-bridged, visa approved/refused, enrolled with/without date, intakes "Sep 2027" / "September 2027" / "09/2027" / "Next intake") | `test_agn_020_reports.py` |
| AC2 | parity with AGN-018: Countries total Applications = dashboard Applications; Offers = O5 | `test_agn_020_reports.py` |
| AC3 | CSV header row exact per kind, BOM, rows equal JSON, formula cells escaped, unicode round-trip, empty = header only, filename | `test_agn_020_reports_csv.py` |
| AC4 | toggle off → 403 on every kind × format before 404/422; toggle on → own scope; `staff` → 403 for staff; super_admin / non-agent → 403 | `test_agn_020_reports_access.py` |
| AC5 | filters: inclusive UTC days per date basis; member (staff → 422; another org's code → 422, same text as unknown); country / university by slug; intake incl. `unstructured`; status; unsupported or unknown → 422 in the list shape with `loc` naming the param | `test_agn_020_reports.py` |
| AC6 | `items/total/limit/offset`; default 50, `limit` 1–100, past-end empty; CSV > cap → 422, no audit row, no file | `test_agn_020_reports_csv.py` (cap monkeypatched) |
| AC7 | one `agent_report.export` audit row per CSV, no names, filter values only slugs/codes/dates/enums; JSON none; refused export none; commission CSV none | `test_agn_020_reports_csv.py` |
| AC8 | tabs per role (keyboard Left/Right/Home/End), URL state incl. shared dates with Commission, every state in §6.4, 422 focus to the named field, pager focus, CSV button; 320 / 375 / 1024 px no page overflow; axe clean | `AgentReportsPanel.test.tsx`, `AgentReportFilters.test.tsx`, `AgentReportTable.test.tsx`, `lib/agentReports.test.ts`, `PortalPage.agentReports.test.tsx`, `agn-020-reports.spec.ts` |
| AC9 | AGN-003 matrix, AGN-014, AGN-018 suites and the portal reports payload unchanged and green | full suites |
| AC10 | 31st export in 10 minutes → 429 with `Retry-After`; a different user unaffected; no audit row for the refused export | `test_agn_020_reports_csv.py` |
| AC11 | security: formula payloads in name / intake / university escaped; no UUID, email, phone or DOB anywhere in JSON or CSV; logs carry no names | `test_agn_020_reports_csv.py`, `test_agn_020_reports_access.py` |

Unit: `fold_intakes`, `parse_filters`. Gates: full pytest, vitest, `tsc`, lint, Playwright agn-003 / agn-014 / agn-018 / agn-020.

## 9. Regression risks and deliberate test updates

| Risk | Mitigation |
|---|---|
| `PortalPage.tsx` / `WorkflowPanel.tsx` shared by every role | change only the agent-reports branch; existing call-list tests unchanged |
| `agent_dashboard.py` and scope helpers (AGN-019 may edit concurrently) | imported read-only, never edited |
| AGN-014 panel re-parented | component untouched; its unit tests unchanged |
| `{kind}` route swallowing `.csv` | `.csv` registered first; test `students.csv` |
| page vs dashboard numbers | AC2 parity |
| Decision ID collision | drafted as `063`, renumbered `066` on merging `main` @ `cf356ca` |

Deliberate updates (structure, not behaviour): `WorkflowPanel.agentCommissionReport.test.tsx` (panel now under the Commission tab);
`agn-014-commission-master.spec.ts` (opens `?report=commission`).

## 10. Out of scope

The funnel chart and branch filter (AGN-019); per-staff commission (`DEC-SCOPE-051` R2, parked); streaming exports; scheduled or emailed
reports; charts; changing the portal `reports` payload; a structured intake column.

## 11. Documentation

`PRODUCT_DECISION_REGISTER.md` `DEC-SCOPE-066`; `RBAC_MATRIX.md`; `API_CONTRACT.md`; `SCREEN_CATALOG.md` / `screen_catalog.json`;
`RTM.md`; `ENHANCEMENT_BACKLOG.md` §AGN-020; `CONFLICT_MATRIX.md` C-10 update (these reports lifted out of "parked").

## 12. Design reviews (2026-10-03, at the owner's request)

Three reviews applied to this spec before planning; changes are already folded into the sections above.

**API and interface design.**
- Pagination follows the codebase's `Page` convention (`items/total/limit/offset`), not `page/page_size`.
- Filters use catalogue **slugs** because university names are not unique; options carry slugs and member codes, never ids.
- 422s use FastAPI's list shape with `loc`, so the client maps errors to fields without parsing text. Date messages keep AGN-014's
  wording.
- Every query param is a string validated after authorization, so a refused caller never sees 422.
- The list page and its total come from one statement (`count(*) OVER ()`). The CSV cap uses `LIMIT cap + 1`, so there is no
  count/fetch race.
- CSV stays `GET` (precedent; the audit row logs a read). Retries write a second audit row.
- The response is additive-only; no existing contract changes.

**Frontend UI engineering.**
- The panel is split into container / filters / table.
- Reuses `.s360-tab`, `.analytics-form`, `.pager`, `.kpi-skeleton`, `stack` tables, `SearchableSelect` and `ReportDownloadButton`.
  One CSS rule is added: `.num`.
- Heading levels h2/h3 sit under the page h1, with a "what is counted" line per report.
- Refetches keep the previous table, dimmed, instead of flashing a skeleton.
- Empty states distinguish "no data yet" from "no matches" (with Clear filters).
- Errors are tied to their field with focus moved to them; after paging, focus moves to the table.
- Totals sit in `<tfoot>`, numbers in tabular figures, and there is a caption of the applied filters.
- Breakpoints 320–1440 px are checked.

**Security and hardening.**
- The §7.1 threat review was run.
- One owner decision came out of it: R10, the export throttle.
- Other controls: member codes resolve inside the org, with the same error text as an unknown code (no cross-tenant oracle).
  Inputs are length-capped. The students country filter uses equality, never `LIKE`. Logs carry filter keys only, never values.
- The CSRF residual risk (a cross-site GET download) is accepted and recorded.
