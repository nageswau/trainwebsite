# ccrm-035 — Export of CRM reports and the counselor's own lists (design)

NO-ASSUMPTION MODE. Source: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` `ccrm-035` (source PDF §13 export, §16 "restrict bulk exports to
authorized roles and log exports", §18 AC 11; the PDF is `UNVERIFIED` and not in the repository — only the backlog's wording is used).
Dependency ccrm-034 (management CRM reports, `DEC-SCOPE-267`) is merged on `origin/main` (`1b703ac2`, PR #329).

## Requirement (backlog, verbatim scope)

CSV and xlsx export of the management reports (ccrm-034) and the counselor's own lists; role-restricted; every export logged (who, report,
filters, row count); sensitive columns never exported. Reuse the logged-report pattern and the nehn-004 xlsx helper "if built" (it is not).

## Alternatives considered

1. **Add `openpyxl` (the nehn-004 plan)** — rejected for this item: a new runtime dependency (and image rebuild on the 2 GB droplet) for a
   write-only, single-sheet file. A standard-library writer (`zipfile` + SpreadsheetML, typed number/text cells) is ~50 lines and testable by
   unzipping. nehn-004 can still swap it for openpyxl later behind the same `to_xlsx(payload)` call.
2. **Export every ccrm-034 report in one file** — rejected: CSV holds one table; one report per file keeps CSV and xlsx identical in shape
   and matches the existing `/{kind}.csv` exports.
3. **Reuse the portal payload (`section_payload`) for the counselor's applications** — rejected: it caps silently at 500 rows and carries
   the outcome *reason* (internal). A dedicated query reuses `application_filters.parse/apply` (same filters, same 422s) with an explicit cap.
4. **Chosen:** `services/tabular.py` (`to_xlsx`) beside the existing `agent_reports.to_csv` (same `{columns, items, totals}` payload);
   `services/crm_exports.py` (the shared export step: lock, throttle, audit, file); one management route and two counselor routes.

## Recommended defaults (`NEEDS_CONFIRMATION`; the owner asked for an autonomous run with recommended answers)

- **E1 Formats.** `csv` (UTF-8 with BOM, the on-screen labels as header — the existing `to_csv`) and `xlsx` (one sheet, header row frozen,
  numbers as numbers). Any other `format` → 422.
- **E2 Management reports.** `GET /management/crm-reports/export?report=<ageing|universities|visa|readiness|leads|forecast>&format=` plus
  ccrm-034's filters (same validation). One report per file: its rows, then a Total row (ccrm-034's counted total). Ageing bands are one
  column each. Access exactly ccrm-034 R1: partner, super_admin, overseas_admin; everyone else 403. Counts only — no personal data exists
  in these reports.
- **E3 Counselor's own lists.** Overseas counselor only (`role=counselor`, `division=overseas`; IT counselor and everyone else 403):
  - `GET /counselor/exports/applications?format=` + the Students/Applications filters (ccrm-012 QS6: country, university, intake, stage,
    sub_status, from, to — the same parser, so the same 422s). Scope `counselor_id = me`, agency students without a login included,
    school-bridged rows out (the list's own rule). Offered on both the Students and Applications pages (they are the same table).
  - `GET /counselor/exports/leads?format=` + the leads filters (QS7: stage, priority, from, to). Scope `lead_handover.counselor_scope`.
- **E4 Sensitive columns never exported (allowlist).** Applications: EduSphere ID, Student, University, Agency, Intake, Status, Sub-status,
  Outcome (label only — never the internal reason), Next action, Last updated. Leads: Lead ID, Name, Interest, Stage, Priority, Source,
  Telecaller, Lead date. **Never:** email, phone, WhatsApp, address/city, date of birth, passport/identity, documents, notes, consent,
  referral contact, refusal/loss/outcome reasons, money, internal UUIDs. Whether contact details may ever be exported is `NEEDS_CONFIRMATION`.
- **E5 Logging.** Every export writes one `AuditLog` (`action="crm.export"`, `entity_type` `crm_report` or `counselor_list`, `entity_id`
  the report/list key, metadata `{format, filters: {set filters and their values}, rows}`) and commits it **before** the file is returned —
  an audit write that fails means no file. A structured log line carries ids, the key, the format, the filter *names* and the row count.
  Filter values are ids, dates, intakes and stage keys — no personal data. Views are not audited (ccrm-034 / DEC-SCOPE-051 R7).
- **E6 Throttle.** 30 exports per user per 10 minutes, counted from the caller's own `crm.export` audit rows under a lock on the caller's
  user row (AGN-020 R10 pattern) → 429 with `Retry-After`. A refused export writes nothing.
- **E7 Row cap.** Counselor lists: 5,000 rows; more → 422 "narrow the filters" (AGN-020 precedent, cap + 1 fetch). Management reports are
  grouped (tens of rows) and uncapped.
- **E8 Formula injection.** Every text cell goes through `_safe_cell` in both formats (nehn-004's rule); numbers are written as numbers.
- **E9 Filenames.** `crm-<report>-<as_of>.<ext>`, `my-applications-<today>.<ext>`, `my-leads-<today>.<ext>` (IST date). Headers
  `Content-Disposition: attachment` and `Cache-Control: private, no-store`.

## UI

`ReportDownloadButton` (existing; fetches first so a refusal shows as a message, never a saved file) through one small `ExportButtons`
(Download CSV / Download Excel side by side). Placed: on each ccrm-034 report card that has rows (filters as applied); under the filter bar
on the counselor's Students and Applications pages; on the overseas counselor's leads panel (current filters). Busy, success and error
states come from `ReportDownloadButton`; buttons wrap on narrow screens.

## Security review (Phase 3)

Role check before parsing or querying; scope is the counselor's own records (no id in the path, so no IDOR surface); only allowlisted
columns leave; formula escaping; no-store; throttled; audit fail-closed. GET with no state change other than the audit row (the existing
export precedent; cookies are same-site). SQL through SQLAlchemy with bound parameters.

## Tests

`apps/api/tests/test_ccrm_035_exports.py`: access matrix for each route; CSV and xlsx content (header, rows, total, typed numbers);
filters honoured; allowlist (no email/phone/reason in the bytes); audit row with who/report/filters/rows; throttle 429; cap 422; bad
`format`/`report` 422. `tabular.to_xlsx` unit test (valid zip, escaping, control characters). Frontend: `ExportButtons` and the
ManagementCrmReports buttons (vitest); e2e `ccrm-035-exports.spec.ts` (download from the management page and the counselor pages).

## Regression risks

`agent_reports._export_wait` gains an `action` parameter (default unchanged — AGN-020 tests pin it). `management_crm_reports.reports()`
keeps its output; one-report building is a split of the same functions. Portal payload, filter bar and leads panel behaviour unchanged
apart from the added buttons.
