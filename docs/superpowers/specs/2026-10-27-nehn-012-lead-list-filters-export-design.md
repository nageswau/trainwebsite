# nehn-012 — Lead list: date-range and counselor filters, filtered Excel export

Source: `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-012` (`UNVERIFIED` backlog; §14 L322-323, §16 L363/L375,
§23 L598-605). Dependency nehn-004 (Excel writer, `DEC-SCOPE-282`) is merged. nehn-008 (column policy) is not built, so this ships the
backlog's fallback: a fixed admin / manager column set. The owner pre-authorised the recommended answers; every builder's default
below is `NEEDS_CONFIRMATION`.

## Intent

"50 website enquiries today": an admin or telecaller manager filters the lead list to a day (or a range) and a counselor, and downloads
exactly that list as one Excel file. Contact data leaves the system, so every download is audited and throttled.

## Goals

- `GET /admin/leads` and `GET /telecaller/leads` take `created_from` / `created_to` (ISO dates, inclusive **India-time** days on
  `enquiries.created_at`) and `owner_id` (the assigned counselor). Additive; everything existing is unchanged.
- `GET /admin/leads.xlsx` (admin roles, same division scope as the list) and `GET /telecaller/leads.xlsx` (telecaller manager and
  super_admin, the manager's scope) return every row the list would return for the same filters (all pages), newest first.
- One audit row per download (`crm.export`, `entity_type="lead_list"`, metadata: format, filters, row count); the same per-user
  throttle (30 / 10 min) and row cap (5,000 → 422 "narrow the filters") as ccrm-035, by reusing `crm_exports.export`.
- UI: "Created from", "Created to" and (admin) "Counselor" filters on the admin lead list; the date filters on the telecaller lead
  list; a "Download Excel" button beside each list for the roles that may export.
- Indexes `ix_enquiries_created` (`created_at`, `id`) and `ix_enquiries_owner` (`owner_id`) — migration `0203` (none existed).

## Non-goals

- No CSV twin (the item asks for Excel). No reason prompt. No counselor or plain-telecaller export (the overseas counselor already has
  ccrm-035 "Export my leads"). No per-role column policy (nehn-008). No permission-engine resource for leads (the list's own gate,
  `ensure_admin` / `lead_pipeline.scope`, is the twin's gate).

## Builder's defaults (`NEEDS_CONFIRMATION`)

| # | Question | Default |
|---|---|---|
| L1 | Day boundary | India time (IST) calendar days, half-open instant range (index-friendly). |
| L2 | Bad dates | Malformed → 422 (typed `date` query); `created_from > created_to` → 422 "The start date must be on or before the end date". |
| L3 | One row per lead or per enquiry | Per lead (repeat `LeadEnquiry` rows are not separate rows). |
| L4 | Telecaller (not manager) calls the export | 403 "Telecaller manager role required". |
| L5 | Columns | Lead ID, Name, Phone, Email, Source, Course interest (product, else subject), Stage, Telecaller, Counselor, Created, Last contact (latest logged call or message), Next follow-up (earliest open follow-up). |
| L6 | Audit filters | Ids, dates and keys as given; the search text `q` is recorded only as set (`"q": true`) — never personal data in audit metadata (ccrm-035 E5). |
| L7 | Counselor picker for the telecaller manager | Not added (no manager-readable counselor list exists); the API accepts `owner_id` there too. |

## Design

- `services/lead_list.py` (new, small): `created_range(created_from, created_to)` → WHERE clauses (IST, 422 on reversed), and
  `export_table(db, filters)` → the fixed-column table (one query for the rows via `bdm_leads.admin_rows()`, two grouped queries for last
  contact / next follow-up — no N+1).
- Each route builds its filter list once (a small local helper per router so list and export cannot drift), then the list pages and
  the export calls `crm_exports.export(..., fmt="xlsx")`. That step already locks the caller's user row (throttle cannot be raced),
  checks the cap, writes the audit row and commits before the file is returned.
- Frontend: `ExportButtons`' `Pair` is CSV+Excel; a single `ReportDownloadButton` with the xlsx type is used instead (it already shows
  refusals — 429/422/403 — as a message, not a file). The download URL is the list's request URL without `limit`/`offset`.

## Risks

Existing admin / telecaller lead tests and pages (filters are additive; row keys unchanged). The export shares ccrm-035's throttle
budget (one `crm.export` action) — intended: one budget per person for CRM downloads.
