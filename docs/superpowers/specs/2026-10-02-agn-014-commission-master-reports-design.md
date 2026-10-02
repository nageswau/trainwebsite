# AGN-014 — Commission is Master-only: Revenue on the Master dashboard and commission reports: Design

**Status:** draft for owner review (2026-10-02). **Branch:** `feature/agn-014-commission-master-only` (from `origin/main` 8f0000d).
**Decision:** `DEC-SCOPE-051` (provisional number: `049` is held by `AGN-007` and `050` by `AGN-008` on their unmerged branches).
**Builds on:** `AGT-003`/`AGT-004` (commission accrual and payout), `RPT-002` (Overseas Admin commission summary), `AGN-001`
(`DEC-SCOPE-038`, migration `0046_agent_orgs`), `AGN-002` (`DEC-SCOPE-040` S1: commissions Master-only), `AGN-003`
(`DEC-SCOPE-044`: §6 matrix, Reports toggle).
**Evidence:** `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §2 Dashboard "Commission / Revenue", §2 Reports
"Commission reports", §6 row "Commission ✅ / ❌". The approval is the owner's, not the document's.

## 1. Intent

**Owner's requirement (in-session, 2026-10-02):** "Commission is Master only (§6); Commission/Revenue on the Master dashboard;
commission reports."

**Owner's acceptance criteria:** existing commissions are visible to the migrated Master; Staff → `403` on every commission route;
the same-admin payout rules are unchanged.

**Owner's answers (in-session, 2026-10-02, `EXPLICIT_APPROVAL`):**
- **R1 — Revenue** = the total of `paid` commissions.
- **R2 — Reports** = breakdowns by status and by university / country / intake, with a date-range filter and a CSV export. No
  per-staff breakdown.
- **R3 — Date basis:** the filter applies to the commission's created date.
- **R4 — CSV:** one row per commission.
- **R5 — Authorization style:** reuse the existing inline Master checks; no shared-helper refactor.
- **R6 — Approach A** (§4).
- **R7 — Days are UTC calendar days; reading or exporting the report writes no audit row** (owner accepted the recommendation).

**What is already true on `main` (impact analysis, 2026-10-02):**
- Every agent-side commission route is Master-only: `workflows._require_agent_master` (`GET …/agent/commissions`,
  `POST …/commissions/{id}/claim`) and `api/portal.py` `{team, commissions}`. Tests: `test_agn_003_matrix.py`,
  `test_agn_002_staff_access.py`, `test_agn_004_staff_guards.py`.
- Migration `0046` turned every legacy agent into Master M001 of its own organisation and did not touch `agent_commissions`.
  Commissions are scoped by `agent_id IN org_member_ids(user)`, so the migrated Master already sees them. No test exercises the
  real backfill path; AGN-014 adds one.
- The Master dashboard shows "Claimable commission" and "Claims"; the Master reports page shows "Paid commission". There is no
  Revenue figure and no agent commission report.

## 2. Out of scope

- Per-staff commission breakdown (R2), staff performance, CRM settings: stay parked under `CONFLICT_MATRIX.md` `C-10`.
- Any change to commission creation, amount setting, claim, or payout approval (`admin.py` `approve_commission_payout`).
- The Overseas Admin's `RPT-002` report and `GET /admin/reports/summary`.
- Fixing the existing "Claimable commission" figure, which sums all currencies under an "INR" label. Recorded as a known issue
  (§11); left unchanged to preserve behavior.
- Gating the "Claim commission" form in `WorkflowPanel.agentSpecs` by member role. Staff cannot reach that page (server `403`).
- Any migration, new dependency, or shared Master-check helper.

## 3. Data used (no schema change)

`agent_commissions` (`amount`, `currency`, `status`, `created_at`, `claimed_at`, `paid_at`, `claim_reference`,
`application_id`, `agent_id`) → `overseas_applications` (`intake`, `university_id`, `student_id` nullable,
`school_student_id` nullable) → `universities` (`name`, `country_id`) → `countries` (`name`).
Student name: `users.full_name` if `student_id`, else `school_students.full_name`, else "—" (outer joins; bridged school-student
applications have no `student_id`).

## 4. Approaches considered

- **A — chosen.** Two read-only Master-only routes in `workflows.py` beside the existing commission routes, one added dashboard
  metric in `services/portal.py`, and a client panel mounted through `WorkflowPanel` on the agent `reports` section. Reuses
  `_require`, `_require_agent_master`, `org_member_ids`, `_safe_cell`, `DataTable`, `FormMessage`, `ReportDownloadButton`.
- **B — rejected.** Put the breakdowns in the generic portal `reports` payload. `PortalPage` → `section_payload` carries no query
  parameters; filtering would change the portal contract every role uses.
- **C — rejected.** Same as A in a new router module. Splits the commission routes over two files and needs the private
  `_require` / `_require_agent_master` imported or duplicated.

## 5. API

Both routes live in `apps/api/app/api/workflows.py`, directly after `agent_commissions` (`GET /overseas/agent/commissions`).
There is no `GET /overseas/agent/commissions/{id}`, so the new literal paths cannot collide with a path parameter.

### 5.1 Authorization (order matters)

1. `Depends(get_current_user)` → `401` when unauthenticated.
2. `_require(user, {"agent"}, "overseas")` → `403` for non-agents and for pending / rejected / suspended organisations or
   deactivated members (existing `agent_denial_reason` messages). `super_admin` passes `_require` as today and, with no
   membership, gets the self-scope of `org_member_ids` (an empty report).
3. `_require_agent_master(user)` → `403 "Only an agency Master can view commissions"` for staff.
4. Only then are `date_from` / `date_to` validated, so a refused caller never sees a `422`.

FastAPI validates typed query parameters before the route body runs, which would put `422` ahead of steps 2–3. The routes
therefore take `date_from: str | None = None` and `date_to: str | None = None` and parse them in the body, after step 3, with
`date.fromisoformat`. A parse failure or `date_to < date_from` raises `HTTPException(422, "<message>")`, returned as
`{"detail": "<message>"}` like every other refusal in this API (there is no custom exception handler).

### 5.2 Scope and filter

- Rows: `AgentCommission.agent_id IN org_member_ids(user)` — the whole agency, including commissions whose application a staff
  member created (their `agent_id` is the staff user id; staff are organisation members).
- `date_from` (inclusive) → `created_at >= date_from 00:00 UTC`; `date_to` (inclusive) → `created_at < (date_to + 1 day) 00:00 UTC`.
  Either may be omitted; both omitted = all time.
- One SELECT per request (commission + joins in §3), ordered by `created_at, id`.

### 5.3 `GET /api/v1/workflows/overseas/agent/commissions/report` → `200 CommissionReportOut`

```json
{
  "date_from": "2026-09-01" | null,
  "date_to":   "2026-09-30" | null,
  "totals":        [{"currency": "INR", "count": 3, "amount": 45000.0}],
  "by_status":     [{"status": "paid", "currency": "INR", "count": 1, "amount": 15000.0}],
  "by_university": [{"university": "…", "country": "…", "currency": "INR", "count": 2, "amount": 30000.0}],
  "by_country":    [{"country": "…", "currency": "INR", "count": 2, "amount": 30000.0}],
  "by_intake":     [{"intake": "Sep 2026", "currency": "INR", "count": 2, "amount": 30000.0}]
}
```
- Grouping is done in Python over the single result set (per-agency volume is small; one snapshot for every breakdown).
- Amounts are summed **per currency**; never across currencies. `amount` is a float rounded to 2 places.
- `by_status` is in lifecycle order: `estimated, eligible, claimed, payout_pending, paid`, then currency. Other lists: amount
  descending, then name, then currency.
- Only groups that have rows appear. No commissions → every list empty (no fabricated zeros, per `DATA_MODEL.md` §8).
- Pydantic response models in `schemas.py`: `CommissionReportTotal`, `CommissionReportStatusRow`, `CommissionReportUniversityRow`,
  `CommissionReportCountryRow`, `CommissionReportIntakeRow`, `CommissionReportOut`.

### 5.4 `GET /api/v1/workflows/overseas/agent/commissions/report.csv` → `200 text/csv`

- Same authorization, parameters and rows as §5.3.
- Columns: `Student, University, Country, Intake, Status, Amount, Currency, Created, Claimed, Paid, Claim reference`.
- Amount as `1234.50`; dates as `YYYY-MM-DD` (UTC) or empty.
- Every text cell passes through `_safe_cell` (imported unchanged from `api/school_bulk.py`), so values starting with
  `= + - @ \t \r` cannot run as spreadsheet formulas.
- Headers: `Content-Type: text/csv; charset=utf-8`,
  `Content-Disposition: attachment; filename=agency-commissions-<date_from|all>-to-<date_to|all>.csv`,
  `Cache-Control: private, no-store`.
- No commissions → header row only.

### 5.5 Errors

| Case | Status | Body |
|---|---|---|
| Not signed in | 401 | existing |
| Non-agent role, inactive organisation or member | 403 | existing `_require` messages |
| Staff | 403 | "Only an agency Master can view commissions" |
| `date_from` / `date_to` not an ISO date | 422 | "date_from must be a date (YYYY-MM-DD)" (resp. `date_to`) |
| `date_to` before `date_from` | 422 | "date_to must be on or after date_from" |

### 5.6 Transactions and concurrency

Each request is one read; it sees one consistent snapshot, takes no locks and writes nothing (no audit row, R7). A claim or payout
committed concurrently appears in the before or the after state. The JSON report and the CSV are separate requests and may differ
if data changes between them; accepted and documented.

## 6. Master dashboard Revenue (`services/portal.py` `_agent`)

Inside the existing `if not staff:` block of the `dashboard` branch, after "Claims", append
`{"label": "Revenue", "value": <paid total>}`. The value groups `paid` commissions by currency and formats each as
`f"{currency} {amount:,.0f}"`, joined with ` · `, currency-sorted; with nothing paid it is `"INR 0"`.
Unchanged: every existing metric, order and label, the subtitle, the staff branch, the `reports` and `commissions` branches.

## 7. Frontend (`apps/web`)

- **`lib/agentCommissionReport.ts` (new):** response types mirroring §5.3, `REPORT_URL`, `CSV_URL`,
  `reportQuery(from, to)` (omits empty values), `csvFilename(from, to)`, `STATUS_LABELS`
  (`payout_pending` → "Payout pending", …).
- **`components/AgentCommissionReportPanel.tsx` (new, client):**
  - Filters: labelled "From" and "To" `<input type="date">`, an "Apply" button. If both are set and To < From, an inline error
    ("'To' must be on or after 'From'.") and no request.
  - Loads the all-time report on mount; Apply loads the filtered report.
  - **Loading:** "Loading commission report…" with `aria-busy`; Apply is `aria-disabled` while a request runs.
  - **Stale responses:** each request takes an increasing id held in a ref; a response whose id is not the latest is dropped.
  - **Error:** `FormMessage` alert. `401` → "Your session has expired. Sign in again."; `403`/`422` → server message via
    `detailMessage`; network or `5xx` → "Something went wrong on our side. Please try again."
  - **Empty:** "No commissions in this period."
  - **Data:** totals line per currency; four headed tables (By status, By university, By country, By intake) using `DataTable`
    with Count, Amount, Currency columns.
  - **CSV:** `ReportDownloadButton` with the URL of the **applied** filters, `filename=csvFilename(...)`,
    `contentType="text/csv"`, `busyLabel="Preparing CSV…"`, label "Download CSV".
- **`components/ReportDownloadButton.tsx`:** two optional props, `contentType` (default `"application/pdf"`) and `busyLabel`
  (default `"Preparing PDF…"`). The five existing PDF call sites pass neither and behave exactly as before.
- **`components/WorkflowPanel.tsx`:** `showAgentCommissionReport = user.role === "agent" && section === "reports" &&
  user.agent_member_role !== "staff"`; added to the early-return guard and rendered in the action grid.
- No change to `PortalPage`, `PortalSection`, `lib/navigation.ts`, `lib/types.ts`.
- Responsive/accessibility: existing `.action-card`, form grid (stacks on narrow screens), `DataTable`; headings per table;
  outcomes announced by `FormMessage`.

## 8. Security review

| Threat | Control |
|---|---|
| Staff read commissions through the new routes | `_require_agent_master` before any query; AC02 tests both routes. |
| Cross-agency read | `org_member_ids` scope; AC05 test with a second organisation. |
| Information leak through validation errors | Dates parsed after authorization (§5.1); AC02 sends bad dates as staff and expects `403`. |
| CSV formula injection (student / university / intake / claim reference are user-entered) | `_safe_cell` on every text cell; AC07 test. |
| Cached export on a shared machine | `Cache-Control: private, no-store`. |
| Unbounded export | Per-agency volume is small; a single scoped query. No cap added (YAGNI); revisit if an agency exceeds ~10k commissions. |

## 9. Acceptance criteria → tests (written before the code)

| ID | Criterion | Test |
|---|---|---|
| AGN-014-AC01 | A Master created by the real `0046` backfill (legacy agent with a commission, no membership → `_backfill` via `run_sync`) sees the old commission in the list, the dashboard Revenue, the report and the CSV. | `test_agn_014_commission_reports.py` |
| AGN-014-AC02 | Staff → `403` on list, claim, report, report.csv and the portal `commissions` page; `403` (not `422`) with invalid dates. | same + `test_agn_003_matrix.py` rows added |
| AGN-014-AC03 | Same-admin payout rules unchanged. | `test_agt_004_commission_payout.py` passes **unedited** |
| AGN-014-AC04 | Master dashboard Revenue = paid total per currency; `INR 0` when nothing is paid; other agencies excluded; staff dashboard has no Revenue and no "commission" wording. | `test_agn_014_commission_reports.py`; existing `test_agn_002_qa_messages.py` |
| AGN-014-AC05 | Report breakdowns correct per currency; lifecycle status order; staff-created application's commission included; other agency excluded. | `test_agn_014_commission_reports.py` |
| AGN-014-AC06 | Created-date filter inclusive at both UTC-day boundaries; optional bounds; `date_to < date_from` → `422`; malformed date → `422`. | same |
| AGN-014-AC07 | CSV: header + one row per commission, same filter, `_safe_cell` applied, `text/csv` attachment, `no-store`, header-only when empty. | same |
| AGN-014-AC08 | New routes: unauthenticated → `401`; non-agent (overseas_admin, overseas_student) → `403`; pending / suspended organisation → `403`. | same |
| AGN-014-AC09 | Panel: loading, empty, error (401 / 403 / 5xx), data; client-side range error sends no request; stale response ignored; CSV URL follows applied filters; not mounted for staff. | `AgentCommissionReportPanel.test.tsx`, `WorkflowPanel.agentCommissionReport.test.tsx` |
| AGN-014-AC10 | `ReportDownloadButton` PDF behavior unchanged; CSV accepted with `contentType="text/csv"`. | existing ENH-015 tests + new case |
| AGN-014-AC11 | End to end: Master sees Revenue on the dashboard, filters the report and downloads the CSV; staff get the "Access unavailable" card on `/overseas/agent/commissions` and no Revenue. | `tests/e2e/agn-014-commission-master.spec.ts` |

**Note on AC01:** `_backfill` processes every agent without a membership in the test database, as a real upgrade does. The test
creates its legacy agent without a membership, runs `_backfill`, and asserts only on its own organisation.

## 10. Regression risks and mitigations

| Risk | Mitigation |
|---|---|
| Edits to `_agent` leak commission wording to staff | Only the `not staff` dashboard block changes; `test_agn_002_qa_messages.py`, `test_agn_002_staff_access.py` re-run. |
| PDF downloads change | Defaults preserved; five call sites untouched; ENH-015 unit tests and specs re-run. |
| New GET paths shadow or are shadowed by `/commissions/{id}` | No GET by id exists; AC02/AC05 hit both new paths. |
| Payout rules change | `admin.py` not touched; AC03 runs the suite unedited. |
| Migration chain | No migration. |
| DEC number clash | Provisional `DEC-SCOPE-051`; re-checked against `origin/main` and sibling branches at merge. |

**Lite regression set per feature:** backend `test_agt_003_*`, `test_agt_004_*`, `test_agn_001_tenancy`,
`test_agn_001_registration_and_gate`, `test_agn_002_staff_access`, `test_agn_002_qa_messages`, `test_agn_003_matrix`,
`test_agn_003_permissions`, `test_agn_004_staff_guards`, `test_rpt_002_*`, `test_sec_001_audit_trail`, `test_enh_028_templates`
(`_safe_cell`'s existing caller); vitest full; Playwright `agt-003`, `agt-004`, `agn-002`, `agn-003`, `rpt-002`,
`enh-015-reports-downloads`, and the new AGN-014 spec. The full backend suite stays with the owner's 4–5-story cadence.

## 11. Known issue recorded, not fixed

"Claimable commission" on the Master dashboard adds amounts across currencies and labels the sum "INR". All seeded and created
commissions default to INR, so it is correct today; a non-INR commission would make it wrong. Left unchanged by design (§2).

## 12. Documentation to update with the code

`PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-051`), `ENHANCEMENT_BACKLOG.md` (§AGN-014), `MASTER_FEATURE_CATALOG.md` /
`feature_catalog.json`, `API_CONTRACT.md` (the two report routes beside the existing Master-only commission row),
`RBAC_MATRIX.md` (agent commission report rows), `CONFLICT_MATRIX.md` `C-10` (commission reports leave the
parked list; per-staff breakdown stays), `docs/quality/RTM.md`, `SCREEN_CATALOG.md` (agent Reports panel),
`ROLE_NAVIGATION.md` (no nav change; note the panel).

## 13. Review log (2026-10-02, after implementation)

**Whole-branch review (fresh reviewer):** "with fixes". Fixed test-first: a `date_to` of `9999-12-31` (offered by a date input)
overflowed to a 500 — now `422 "date_to must be before 9999-12-31"`; the bridged school-student name gained a test (proved by
mutation). Minors deferred (RTM row).

**api-and-interface-design:**
- **A1 (fixed)** — `date.fromisoformat` also accepted `20260930` and ISO week dates; the contract is `YYYY-MM-DD` only, now enforced
  by a full match before parsing (same 422 message).
- **A2 (fixed)** — both date parameters carry OpenAPI descriptions (format, inclusive UTC day, the `9999-12-31` bound).
- Kept as built: GET (safe, idempotent); the codebase's `{"detail": "…"}` error shape; 401 → 403 → 422 order; additive contracts
  only; one read-only parameterised SELECT per request (one snapshot, no transaction to manage); no pagination — an aggregate report
  and a file export, not a list endpoint. The JSON report sets no `Cache-Control` (consistent with every other JSON route; it has no
  validators, so browsers do not cache it heuristically); the CSV keeps `private, no-store`.

**frontend-ui-engineering:**
- **F1 (fixed)** — the panel spans the action grid (`.commission-report`, the AGN-004 pattern) so its five-column tables are not
  half width; 44 px buttons on phones.
- **F2 (fixed)** — a load error offers **Try again**, which reloads the requested range.
- **F3 (fixed)** — Apply keeps the current figures (and their CSV) on screen with "Updating commission report…" instead of blanking.
- **F4 (fixed)** — the range error marks "To" `aria-invalid`, describes it, moves focus to it, and clears when either date changes.
- **F5 (fixed)** — empty state: "Your agency has no commissions yet." unfiltered, "No commissions in this period." filtered.
- **F6 (fixed)** — lakh/crore digit grouping for INR only; other currencies use 1,000s.
- For browser validation: a multi-currency Revenue value on the metric card at 390 / 820 / 1440 px.

**security-and-hardening (threat model: one trust boundary — the authenticated request; assets — the agency's commission amounts
and student names):**
- Authentication: the existing httpOnly, `SameSite=Lax` cookie session (`get_current_user`, session version, deactivation).
- Authorization / IDOR / escalation: Master check before any read; scope from the session (`org_member_ids`), no id in the path;
  nothing written, no role reachable. Tested: staff, other agency, non-agents, suspended agency, unauthenticated.
- Input validation: dates only (strict format, bounds); unknown parameters ignored. SQL injection: ORM-parameterised.
- XSS: React escaping; the CSV is a download, never rendered; its filename is built from parsed dates. CSV formula injection:
  `_safe_cell` on every text cell.
- CSRF: read-only GETs; a cross-site link can make a Master's browser download their own CSV but cannot read it.
- Secrets / sensitive logs: none added; the log line carries ids, format, row count and range — no names or amounts.
- **Residuals (recorded, not changed):** no rate limit on the two reads (project-wide residual; changing throttling is an
  owner decision); no audit row on report reads/exports (owner decision R7); `_safe_cell` does not treat leading whitespace before
  `=` (existing helper shared with ENH-028).
