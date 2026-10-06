# tel-006 — CSV lead import per campaign (design)

- **Backlog:** `docs/delivery/TELECALLER_CRM_BACKLOG.md` § tel-006 (EVID-019 §2, T12, T15). Dependencies tel-005 (PR #92) and tel-007 (PR #90) are merged.
- **Decision:** `DEC-SCOPE-091` (main holds 089 = bdm-020; 090 / §12M are claimed by the open AGN-023 branch) · **Migration:** `0087_lead_import_batches` (after tel-005's `0086_lead_enquiries`) · **API contract:** §12N. Numbers are provisional and re-chain at merge if main moves.

## 1. Owner answer (2026-10-06)

| ID | Question | Answer |
|---|---|---|
| IM1 (Q-06) | Columns, cap, failure behaviour | **Per-row report.** The manager picks one active campaign (it gives the source, the product and so the team), then uploads. Columns: `name`*, `phone`* (a valid mobile), `email`, `whatsapp_number`, `city`, `state`, `qualification`, `passing_year`, `institution`, `priority`, `subject`, `message`. At most 1 MB and 500 filled-in rows. A bad file (encoding, missing/unknown/repeated header, no rows, too many rows) is 422 and nothing is created. Otherwise each row stands alone: **created**, **attached** (a known person, T12: the row becomes an enquiry on their newest lead — including a lead created by an earlier row of the same file) or **rejected** with its line number and reason. The Idempotency-Key replays the stored report. |

Recorded defaults (no owner question needed):

- **R1 (roles):** `telecaller_manager` and `super_admin` import (`require_manager`); every other role 403, anonymous 401.
- **R2 (campaign):** the campaign must be active and its product active (422 before any row). The division is the product's team; an `other` product without a team needs a `division` form field (422 otherwise), exactly like tel-005 R5.
- **R3 (lead fields):** source = campaign source, `product_id` = campaign product, `campaign_id` = campaign. `subject` defaults to the product name and `message` to `""` (tel-005 R6). `priority` defaults to `warm`.
- **R4 (ownership):** an imported lead is a manager's lead: unassigned, then `lead_distribution.on_intake` (tel-007 / tel-005 I6). Nobody eligible → the team's unassigned queue.
- **R5 (attach):** the enquiry row carries the campaign's source and id, the uploader as `created_by_user_id`, and the row's subject (default: product name) and message. The lead's stage does not move (tel-005 I5).
- **R6 (CRM):** each created lead is queued for the CRM webhook after the commit; an attached row queues nothing (tel-005 I4, R10).
- **R7 (races):** the batch is one transaction with a SAVEPOINT per row. Each row takes tel-005's advisory locks on its phone/email keys before matching, so a concurrent manual create or website enquiry of the same person serialises. A lock wait over `lock_timeout` (5 s) rejects only that row ("This row conflicts with a change made at the same time; upload it again").
- **R8 (idempotency):** unique `(uploaded_by_user_id, idempotency_key)`. Same key + same file bytes + same campaign/division → the stored report (nothing created). Same key with anything else → 422 `Idempotency-Key was already used for a different file`.
- **R9 (PII):** the uploaded file is never stored. The batch keeps counts, the file SHA-256 and per-row outcomes `{row_number, status, lead_id, error}` — no names, phones or emails. Row errors come from `validation_message` (never echoes the value). Logs carry ids and counts only.
- **R10 (traceability):** created leads and attached enquiries carry `metadata_json.import_batch_id`. One audit row `lead.import` per batch with the counts.
- **R11 (history):** `GET /telecaller/imports` lists the caller's own batches (super_admin: all), newest first; `GET /telecaller/imports/{id}` returns one report (another manager's → 404).
- **R12 (formula injection):** the report is JSON on screen, not a CSV export; CSV-export escaping belongs to tel-024. The template is a static header row.

## 2. Data — `0087_lead_import_batches`

`lead_import_batches`: `id` uuid PK; `campaign_id` → `tel_campaigns.id`; `division` varchar(20) CHECK it/overseas; `uploaded_by_user_id` → `users.id`; `idempotency_key` varchar(120); `file_sha256` varchar(64); `total_rows`, `created_count`, `attached_count`, `rejected_count` int (CHECK the three add up to total); `results_json` JSON default `[]`; `created_at`, `updated_at`. Unique `(uploaded_by_user_id, idempotency_key)`; index `(uploaded_by_user_id, created_at)`. Downgrade drops the table.

## 3. Backend

- `schemas.LeadImportRow` — the row model (tel-005's field types: `BdmLeadName`, `LeadMobile`, `LeadOptionalEmail`, …), `extra="forbid"`.
- `services/lead_intake.import_row(db, user, campaign, product, division, row, batch_id) -> (lead, attached)` — lock, match newest (limit 1), attach as `LeadEnquiry` or insert the lead + `on_intake`. Never commits.
- `api/telecaller_import.py` (router prefix `/telecaller`), reusing `school_bulk._read_upload` / `_read_csv` / `_lock_timed_out` / `LOCK_TIMEOUT`:

| Method | Path | Result |
|---|---|---|
| GET | `/telecaller/imports/template` | `text/csv` header row (the 12 columns) |
| POST | `/telecaller/imports` (multipart `file`, `campaign_id`, optional `division`; header `Idempotency-Key`) | 201 report `{id, campaign, division, total_rows, created_count, attached_count, rejected_count, rows: [{row_number, status, lead_id, lead_code, error}], created_at}`; 413 > 1 MB; 422 file/campaign/key; 409 a racing upload with the same key still running |
| GET | `/telecaller/imports?limit=&offset=` | `{items, total, limit, offset}` of batch summaries |
| GET | `/telecaller/imports/{id}` | the report; 404 when not the caller's (super_admin: any) |

## 4. Frontend

`/telecaller/manager/imports` ("Lead import" in the manager nav), inside `TelecallerCataloguePage`:

- `TelecallerLeadImportPanel`: 1. pick an active campaign (Division picker appears for an `other` product), 2. download the template + column reference (`BulkColumnReference`), 3. choose the file and upload. A new Idempotency-Key per chosen file + campaign, so a retry after a dropped connection replays. Busy/disabled state, `role="alert"` errors, a summary (created / attached / rejected) and a result table (Row, Result, Lead ID, Detail) whose heading takes focus.
- `TelecallerImportHistory`: the past batches table with loading / error + Retry / empty states; refreshed after an upload.

## 5. Acceptance criteria → tests

1. A valid file creates leads tagged with the campaign, its source and product, distributed (or queued) → `test_tel_006_import.py`, Playwright.
2. Duplicate rows (an existing lead, or an earlier row of the same file) attach as enquiries; no new lead → `test_tel_006_import.py`.
3. Invalid rows are reported with line number and reason; valid rows in the same file still land → `test_tel_006_import.py`, vitest, Playwright.
4. Re-uploading with the same key creates nothing and replays the report; same key + other file → 422 → `test_tel_006_import.py`.
5. Wrong headers → 422 before any row; a deactivated campaign → 422 → `test_tel_006_import.py`.
6. Security: telecaller/other roles 403, anonymous 401, another manager's batch 404, no PII in `results_json` → `test_tel_006_import.py`.
7. Migration up/down → `test_tel_006_migration.py`.

## 6. Regression risk

`lead_intake` (manual create, website attach) — `import_row` is additive and reuses the helpers unchanged; `school_bulk` helpers are imported, not changed. Run tel-005 / tel-007 / tel-003 intake tests.
