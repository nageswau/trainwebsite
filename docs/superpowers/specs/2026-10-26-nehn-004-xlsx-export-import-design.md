# nehn-004 — Shared Excel (`.xlsx`) export and import helper — design

Source: `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-004` (`DERIVED_WORKBOOK`/`UNVERIFIED` backlog). Dependencies: none.
The owner asked for an autonomous run with recommended answers; every default below is `NEEDS_CONFIRMATION` (DEC-SCOPE-282).

## Intent
Every report that downloads as CSV can also download as Excel, and future imports (nehn-025 trainer questions) can read `.xlsx` as well
as `.csv` through one hardened reader.

## Current state (Graphify discovery)
- ccrm-035 already ships a standard-library one-sheet writer `app/services/tabular.py::to_xlsx(payload, sheet_name)` (frozen header,
  numbers typed, text through `school_bulk._safe_cell`), used by `api/crm_exports.py` and `api/management.py`, with `?format=csv|xlsx`.
- Six CSV-only report exports: `telecaller_reports /{kind}.csv`, `telecaller_dashboard /manager/performance.csv`,
  `recruiter_dashboard /performance.csv`, `agent_reports /{kind}.csv`, `partnership_reports /{kind}.csv`, and the agency commission
  report `workflows.py /overseas/agent/commissions/report.csv`. The first five render `agent_reports.to_csv(payload)`; the commission
  CSV writes its own rows.
- Every import is CSV (`school_bulk._read_csv`, reused by the telecaller and onboarding imports). `openpyxl` is not a runtime dependency.

## Decisions (recommended defaults)
- **X1 Writer stays standard-library** (ccrm-035's, extended): no rewrite of a tested writer and no streaming dependency. Extended with
  a `styles.xml`: a bold header row, **date cells** (`date` → `yyyy-mm-dd`, `datetime` → IST `yyyy-mm-dd hh:mm`, and an ISO
  `YYYY-MM-DD` string — the form every report payload already uses for days — is written as a date), `Decimal` typed as a number, an
  **auto-filter** over the header and item rows (never the Total row), and **column widths** from the longest value (8–60 chars).
  Text stays an inline string through `_safe_cell`, so leading-zero phone numbers stay text and `=HYPERLINK(...)` is literal (AC3).
- **X2 Reader uses `openpyxl`** (`>=3.1,<4`): shared strings, styles and date serials are not worth re-implementing. `read_tabular(filename,
  raw, *, required, known=None, max_rows=5000, max_bytes=1 MB)` → `[(sheet row, {column: trimmed text})]` for rows with any cell filled,
  the `_read_csv` contract. Errors raise `TabularError(status, messages)`.
  - `.xlsx` and `.csv` only (by extension); `.xlsm`, `.xls`, anything else → 415 "Upload a .xlsx or .csv file".
  - Size over `max_bytes` → 413. Not a zip / encrypted / corrupt → 422 "not a valid Excel file".
  - Hardening before openpyxl sees the bytes: at most 200 zip entries and 20 MB declared uncompressed in total (zip-bomb guard;
    `zipfile` never inflates past the declared size); a `vbaProject.bin` or a `macroEnabled` content type → 415; any XML part with a
    `<!DOCTYPE`/`<!ENTITY` → 422 (no entity expansion is ever parsed). Then `load_workbook(read_only=True, data_only=True,
    keep_links=False)`: no formula is evaluated, a formula cell gives Excel's saved value.
  - Header names lower-cased and trimmed. **Every** missing required column is reported, one message each (AC4); with `known`,
    unknown and repeated headers are reported too. More than `max_rows` filled rows → 422.
  - Cells to text: dates ISO, a midnight datetime as a date, an integral float without `.0`, booleans `TRUE`/`FALSE`.
  - No existing CSV import is switched over (regression risk, not asked); nehn-025 is the first consumer.
- **X3 Each CSV route gains an `.xlsx` sibling path** (`/{kind}.xlsx`, `/manager/performance.xlsx`, `/performance.xlsx`,
  `/report.xlsx`) — the backlog's first option, and the CSV routes stay unchanged (CSV stays). Same dependency, scope function, caps,
  throttle, audit and `no-store` as the CSV twin; the query parameters are shared through one dependency per module so the two routes
  cannot drift. A shared `agent_reports.export_response(payload, fmt, stem, sheet_name)` renders either format.
- **X4 Audit parity (AC5):** the xlsx route writes exactly the audit row its CSV twin writes, committed before the file; the audit
  metadata of both gains `"format"`. The commission report CSV is not audited today (AGN-014: logged only, with `format`), so its xlsx
  twin is logged the same way — adding an audit there is a separate decision (`NEEDS_CONFIRMATION`).
- **X5 Row caps:** each xlsx route keeps its CSV twin's cap and refusal message (agency 10,000, partnership `CSV_ROWS`, CRM 5,000);
  aggregate reports are bounded by their groups. No new global cap.
- **X6 Frontend:** a `SpreadsheetButtons` pair next to ccrm-035's `ExportButtons` (same file, same rendering): "Download CSV" and
  "Download Excel" for a `.csv` URL whose `.xlsx` twin differs only in the extension. The six panels swap their single CSV button for
  it; ReportDownloadButton is unchanged.

## Non-goals
Switching existing CSV imports to xlsx; multi-sheet workbooks; the import UI (nehn-025); exports beyond the six report routes
(templates and import reports stay CSV).

## Tests
Unit: writer styles/dates/filter/widths/Decimal/empty; reader csv+xlsx happy path, Unicode, leading zeros, dates, per-column missing
headers, unknown/duplicate, xlsm/xls/too large/not a zip/macro/DTD/zip bomb/row cap. Route: each `.xlsx` sibling 200 + typed content +
audit row (format xlsx), refused roles same as CSV; matrix inventories gain the new rows. Web: vitest for `SpreadsheetButtons`.
