# ENH-029 — Bulk school partner onboarding (Admin, multiple schools at once) — design

**Status:** design sections 1–4 approved by the user in-session 2026-10-01; this written spec is AWAITING USER REVIEW.
**Feature:** `ENH-029` (`docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-029). **Branch:** `feature/enh-029-bulk-school-onboarding`.
**Decision:** `DEC-SCOPE-044` (§12) — to be recorded in `PRODUCT_DECISION_REGISTER.md` once this spec is approved.

## 1. Evidence and intent

- **Request (user, in-session, quoted in the backlog):** *"Admin also may on-board multiple schools at a time."*
- **Backlog acceptance:** an Overseas Admin can onboard N schools in one upload; each row creates its school + coordinator pair
  independently, with per-row failure isolated per the never-block-the-batch discipline; a batch report shows accepted/rejected
  counts per row.
- **Existing authority:** `SCH-003` / `DEC-SCOPE-012` (Admin creates a School + seed Coordinator, active immediately, no approval
  gate); `ENH-003` / `DEC-SCOPE-019`/`DEC-SCOPE-025` (admin-provisioned accounts get an unusable password + a 72 h set-password
  link, never a known password); `ENH-009` (School profile fields, generated `school_code`); `ENH-028` / `DEC-SCOPE-043`
  (generalized bulk batch/row tables, idempotency, file limits, single-transaction processing).
- **Backlog correction:** the backlog entry's security note (default password `"ChangeMe@12345"`, `admin.py:920`) and line
  references (`admin.py:900-939`) are stale. `create_school` (`admin.py:1171`) already uses `unusable_password_hash()` +
  `issue_welcome_token` / `deliver_welcome_link`; the ENH-003 dependency is satisfied. The backlog entry is corrected as part
  of this work.
- **Graph evidence:** `graphify explain` on `create_school()`, `SchoolCreate`, `SchoolBulkUploadPanel.tsx`,
  `test_sch_003_school_onboarding.py` (graph built before ENH-028's merge; line numbers re-verified against the source).

## 2. Decisions

| # | Decision | Source |
|---|---|---|
| D1 | **Columns = every `SchoolCreate` field.** Required: `name`, `coordinator_full_name`, `coordinator_email`; all ENH-009 profile fields optional. The row is validated by `SchoolCreate` itself — one rule set, no drift. | User |
| D2 | **Duplicate schools rejected, bulk only:** a row whose normalized (name, city) matches an existing school or an earlier row of the same file is rejected (that row only). The single create is unchanged (it does not check names). Coordinator email: existing or repeated in the file → rejected. | User |
| D3 | **Limits: ≤ 1 MB, 1–100 filled-in rows.** Welcome links sent after commit, **at most 5 at a time**, reusing `deliver_welcome_link` unchanged. No worker/queue. | User |
| D4 | **Approach A:** one request = one transaction; each row's create inside its own savepoint; ENH-028's `school_bulk_upload_*` tables with `target_type = 'school_onboarding'`; post-commit welcome delivery. | User (chosen over B: commit-per-row, C: client-side loop) |
| D5 | Create-only. No update/deactivate by bulk. | Design (backlog scope) |
| D6 | Idempotency exactly as ENH-028 (D9 there): key scoped to (uploader, target_type, key), file SHA-256 stored; same key + same file = replay; same key + different file = 422. | Design (approved §1) |
| D7 | New router module `app/api/school_onboarding_bulk.py` (prefix `/overseas-admin`, precedent: `school_feedback.admin_router`, `school_transfers.admin_router`), so `admin.py` does not grow. | Design (approved §2) |

## 3. Scope

**In:** one upload endpoint, one header-only template endpoint, one migration (constraint change only), a behaviour-preserving
extraction of `create_school`'s body, a small parameterization of three private `school_bulk.py` helpers, one new React panel on
the existing Admin Schools page, tests, docs.

**Out (unchanged):** `POST /overseas-admin/schools` request/response/audit; `GET /overseas-admin/schools`, `PATCH
/overseas-admin/schools/{id}`, tier preview, lookup; the four ENH-028 endpoints and reports; the SCH-002 roster upload;
`provisioning.py` (`issue_welcome_token`, `deliver_welcome_link`, `flush_unique_email`, `provisioning_statuses`); tier
entitlements; navigation; XLSX; async/background processing; editing schools by bulk.

## 4. Data model (migration `0052_school_onboarding_bulk_target`, constraint-only)

- `ck_school_bulk_upload_target_type` is dropped and recreated as
  `target_type IN ('academic_result','psychometric_record','test_prep_record','language_record','school_onboarding')`.
- `BULK_TARGET_TYPES` (`models.py:1401`) gains `"school_onboarding"`.
- No columns are added; no existing row is read or written. `school_bulk_upload_rows.student_code` stays `NULL` for onboarding
  rows; `created_record_id` holds the created `schools.id`.
- `downgrade()`: if any `school_onboarding` batch exists, raise (refuse to silently delete data); otherwise restore the 0051
  constraint.
- `down_revision = "0051_school_bulk_uploads"`; must be the single head.

## 5. API contract

Both routes on `school_onboarding_bulk.router` (`prefix="/overseas-admin"`), registered in `main.py` after `admin.agents_router`.
No existing route shadows them: `/schools/{school_id}` exists only for `PATCH`, and Starlette keeps looking for a full
method+path match (a test hits both new paths to prove it).

**Authorization (both):** `user.role in {"overseas_admin", "super_admin"}`, else `403 "Overseas Admin role required"` —
identical to `create_school`. Authentication via `get_current_user` (unchanged).

### 5.1 `GET /api/v1/overseas-admin/schools/bulk-template`

`text/csv`, `Content-Disposition: attachment; filename=school-onboarding-bulk-template.csv`, `Cache-Control: private, no-store`.
Header row only, in this order:

`name, city, state, tier, tier_valid_until, coordinator_full_name, coordinator_email, branch, address, contact_number, email,
website, grades_available, board, partnership_date, mou_reference, edusphere_bdm, monthly_visit_schedule, vice_principal_name`

### 5.2 `POST /api/v1/overseas-admin/schools/bulk-upload`

Multipart field `file`, header `Idempotency-Key` (1–120 of `[A-Za-z0-9._:-]`).

| Status | When | Body `detail` |
|---|---|---|
| 201 | processed (any mix of accepted/rejected rows) | — (report) |
| 201 | replay: same key + same file | — (stored report, `email_status: null`) |
| 403 | wrong role | `Overseas Admin role required` |
| 409 | another onboarding upload holds the lock, or the same key is mid-flight (> 5 s) | `This upload is still being processed; retry shortly` |
| 413 | file > 1 MB | `The file is larger than 1 MB` |
| 422 | key missing / malformed | ENH-028 messages |
| 422 | not UTF-8 CSV, NUL byte, malformed CSV | `The file must be a UTF-8 CSV` |
| 422 | missing required header | `Missing required column: <name>` |
| 422 | header not in §5.1 | `Unknown column: <name>` |
| 422 | no filled-in rows / > 100 | `The file has no filled-in rows` / `The file has more than 100 filled-in rows` |
| 422 | same key, different file | `Idempotency-Key was already used for a different file` |

**Report:**

```json
{
  "id": "uuid", "target_type": "school_onboarding", "status": "completed",
  "total_rows": 3, "accepted_count": 2, "rejected_count": 1,
  "rows": [
    {"row_number": 2, "status": "accepted", "error_message": null, "created_record_id": "school uuid",
     "school_code": "AB12CD34", "school_name": "Sunrise Public School", "coordinator_email": "c@x.in",
     "email_status": "sent"},
    {"row_number": 3, "status": "rejected", "error_message": "Email already exists", "created_record_id": null,
     "school_code": null, "school_name": null, "coordinator_email": null, "email_status": null}
  ]
}
```

- `row_number` is the CSV file line (header = line 1), as in ENH-028. Rows in file order.
- `school_code`/`school_name`/`coordinator_email` come from the created records (on replay: `school_code`/`school_name` joined
  from `schools` via `created_record_id`; `coordinator_email` from the coordinator whose `profile.school_id` is that school and
  `role = 'school_coordinator'`, the earliest-created one).
- `email_status` (`sent` | `not_configured` | `failed`, from `deliver_welcome_link`) only on the first response; `null` on
  replay and on rejected rows.
- In `development`/`test` environments only, an accepted row of the first response also carries `development_welcome_token`
  (exact parity with the single create's `DEV_TOKEN_ENVIRONMENTS` rule). Never on replay, never in production.

## 6. Row rules (in order; the first failure wins; one message per row)

A row is "filled in" when at least one §5.1 column has a non-blank cell; fully blank rows are skipped, never reported. Cells are
trimmed; a blank cell is "not provided" (omitted before validation, so optional fields become `None`).

1. `SchoolCreate.model_validate(cells)` — failure → `validation_message(exc)` (existing helper; never echoes the value).
2. Coordinator email normalized with `_valid_email` (lower-case, trimmed; an invalid address → its existing message
   `A valid email address is required`), then equal to an earlier row's (that passed this rule) → `same coordinator_email as row N`.
3. Email already exists in `users` (pre-loaded in one query) → `Email already exists`.
4. Normalized (name, city) equals an existing school's → `a school with this name and city already exists`.
   Normalization: `casefold()`, whitespace runs collapsed to one space, trimmed; `None` city ≡ empty city.
5. Normalized (name, city) equals an earlier row's in this file → `same school name and city as row N`.
6. Create via `_provision_school` inside `db.begin_nested()`:
   - `HTTPException` raised by the helper's own checks (tier, email format, length via `_fit`) → its `detail`.
   - `IntegrityError` (a concurrent single create took the email, or a `school_code` collision) → savepoint rolled back →
     `This row conflicts with a record created at the same time; upload it again`.

Rules 2 and 5 compare only against earlier rows that got that far (a row rejected at rule 1 claims neither its email nor its
name). A row rejected at rule 6 still claims both, so a later copy is reported as a repeat of it rather than attempted twice.

## 7. Processing, transactions, concurrency

**Shared creation helper (behaviour-preserving extraction, `admin.py`):**

```python
async def _provision_school(db, payload: SchoolCreate, actor: User, *, flush_coordinator=flush_unique_email
                            ) -> tuple[School, User, IssuedWelcome]:
    # exactly create_school's current body from `_valid_email` through the two AuditLog adds; no commit, no delivery
```

`create_school` becomes: role check → `_provision_school(db, payload, user)` → `commit` → `deliver_welcome_link` → same response.
Bulk passes `flush_coordinator=lambda db: db.flush()`: `flush_unique_email` calls `db.rollback()`, which would discard the whole
batch transaction, not just the row; inside the savepoint a plain flush lets the `IntegrityError` roll back only that row.

**Parameterized `school_bulk.py` private helpers (ENH-028 behaviour unchanged):**
- `_file_error(target_type: str, user, reason, message, status=422)` — was `target: BulkTarget`.
- CSV parsing split into `_read_csv(raw, *, target_type, user, required, columns, max_rows, known=None)`; ENH-028's
  `_filled_rows(raw, target, user)` becomes a one-line call with `required=("student_code", *target.required)`,
  `columns=target.columns`, `max_rows=MAX_ROWS`, `known=None` (no unknown-column check — unchanged). Onboarding passes
  `known=` the §5.1 columns.
- `_claim(db, target_type: str, user, key, digest) -> SchoolBulkUploadBatch | tuple[SchoolBulkUploadBatch, list[SchoolBulkUploadRow]]`
  — returns the new batch, or the existing batch + rows on replay; each caller builds its own report (ENH-028 keeps `_report`).

**One request = one transaction, then post-commit delivery:**

1. Role → key format → read ≤ 1 MB + 1 byte → SHA-256 → parse (§6 header/row-count rules) → 413/422 before any DB write.
2. `SELECT set_config('lock_timeout', '5s', true)` (bound parameter, ENH-028 value).
3. `_claim` the key (unique index arbitrates racing requests; lock timeout → 409; replay → stored report).
4. `SELECT pg_advisory_xact_lock(:key)` with a fixed constant `SCHOOL_ONBOARDING_LOCK` (a bound integer) — serializes
   onboarding uploads so two uploads cannot both pass rules 4–5 for the same school; lock timeout → 409. Released at commit/
   rollback, i.e. before any email is sent.
5. Pre-load: existing users among the file's normalized emails (one `IN` query); all schools' (name, city) (one query,
   normalized in Python).
6. Per row: §6 rules; build a `SchoolBulkUploadRow` (`status`, `error_message`, `created_record_id`).
7. Batch counts; `AuditLog(action="school.bulk_upload", entity_type="school_bulk_upload_batch", metadata_json={target_type,
   total, accepted, rejected, file_sha256})`; **commit**. Per accepted row the helper has already added `school.create`,
   `school.coordinator_seed`, `user.welcome_link_issue` audits and the `UserRoleAssignment` — identical to the single create.
8. Build the report from memory; `asyncio.Semaphore(5)` + `asyncio.gather` over accepted rows calling `deliver_welcome_link`
   (never raises; audits delivery in its own session; touches no request-session state — `expire_on_commit=False`, so reading
   `coordinator.email/full_name/role` after commit is safe, as in the single create today). Attach `email_status` (+ dev token).
9. Log `bulk_upload_completed` {batch_id, target_type, actor_id, total, accepted, rejected, duration_ms} — ids and counts only,
   never emails or names.

**Failure guarantees:** any exception before step 7's commit rolls back everything (no batch, no schools, no users, no tokens;
the key is free, so a retry reprocesses cleanly). After commit nothing undoes a school; an undelivered link leaves the
coordinator `pending_setup`, re-sendable from the Users page (existing ENH-003 flow).

**Race notes:**
- Same key, concurrent: the second request waits on the unique index, then replays (or 409 after 5 s).
- Different keys, concurrent: serialized by the advisory lock; the second sees the first's committed schools/emails and rejects
  duplicates (rules 3–4), or gets 409 after 5 s.
- Bulk vs single create: email protected by `users.email` unique + savepoint (rule 6). School name not serialized — the single
  create never checks names (parity, documented).
- `school_code` generation (`unique_student_code`) sees the batch's own flushed rows; a collision with a concurrent create is a
  rule-6 `IntegrityError` for that row only.

## 8. Security

- Authorization identical to `create_school`; no new role, no scope widening. `super_admin`/`overseas_admin` only.
- No password is ever set or returned; coordinators get the existing unusable hash + one welcome token each.
- Dev tokens only under `DEV_TOKEN_ENVIRONMENTS`, never on replay.
- Idempotency key scoped per uploader: one admin can never replay another's report.
- Input bounded: 1 MB, 100 rows, `csv` strict mode, NUL rejected, unknown columns rejected; `SchoolCreate` `extra="forbid"` +
  length limits; `_fit` on coordinator name.
- Logs: no email addresses, names or tokens (ids/counts/reasons only); file-level rejections logged via `_file_error`
  (`bulk_upload_rejected_file` with `target_type`, `reason`).
- Template is header-only (no stored data, so no CSV formula-injection surface from the download). Stored values have the
  same exposure as the single create (parity).
- Email volume: ≤ 100 welcome emails per upload, 5 concurrent — admin-only action.

## 9. Frontend

**New `apps/web/components/AdminSchoolBulkOnboardPanel.tsx`**, rendered in `WorkflowPanel.tsx` under the existing
`showSchoolCreate` condition, directly after `<AdminSchoolCreatePanel/>`. No new route, nav entry or role logic. Follows
`SchoolBulkEntryPanel`'s structure and CSS classes (separate component: the ENH-028 panel's copy, empty state and report
columns are student-specific; generalizing it would risk ENH-028).

**New `SCHOOL_ONBOARDING_COLUMNS: BulkColumn[]`** in `apps/web/lib/bulkEntry.ts` (reuses the `BulkColumn` type; documentation
only — the server is authoritative).

**States:**
- Collapsed `<details>` card: "Onboard several schools (CSV)".
- Step 1: "Download the template (.csv)" link + "Column reference" table (Column / Required / Format / Example).
- Step 2: file input (`.csv,text/csv`, help text "CSV, up to 1 MB and 100 schools") + "Upload schools" button.
  - No file → inline error "Choose a filled-in CSV file first."
  - Uploading → button "Uploading…", input + button disabled, `aria-busy`, polite live region.
  - File-level 4xx → server `detail` in `role="alert"`; chosen file + key kept.
  - Network error → "The connection dropped. Upload again — the same file won't be added twice." (same key resent).
- Report (heading focused): "N of M schools onboarded, K rejected. Schools that succeeded are kept." + responsive table (`data-label`
  pattern): Row · Result (Added/Rejected) · School ID · School · Coordinator · Detail.
  - Rejected → `error_message`.
  - Accepted, `email_status === "sent"` → "Set-password link emailed".
  - Accepted, `email_status` `not_configured`/`failed` → "Welcome email not delivered — re-send from the Users page".
  - Accepted, `email_status === null` (replay) → "Check the Users page for this coordinator's set-password status".
- After success: `router.refresh()` (Partner Schools list and edit-panel lookup pick up new schools), file input cleared; choosing a
  new file generates a new `crypto.randomUUID()` key.
- Accessibility: labelled controls, table headers, live region, focus moved to the report, result conveyed by text not colour.
  Responsive at 360 px via the existing `table-wrap` / `data-label` card layout.

## 10. Acceptance criteria

| ID | Criterion |
|---|---|
| ENH-029-AC01 | Overseas Admin / Super Admin uploads N valid rows → 201; N schools (unique `school_code`), N active `school_coordinator` users with unusable passwords, N `UserRoleAssignment`s, one welcome token each, per-row audits identical to the single create; report `accepted_count = N`. |
| ENH-029-AC02 | Mixed file → each invalid row rejected with its own message, each valid row created; `accepted + rejected = total_rows`; batch audit `school.bulk_upload` recorded. |
| ENH-029-AC03 | Row rejected (only that row) for: invalid field (tier, board, date, length, missing required); coordinator email existing or repeated earlier in the file; normalized (name, city) existing or repeated earlier in the file. |
| ENH-029-AC04 | Same key + same file → same report, nothing created; same key + different file → 422. |
| ENH-029-AC05 | File-level rejections create nothing: 403 role, key missing/malformed, 413 > 1 MB, non-CSV, missing required / unknown column, 0 rows, > 100 rows. |
| ENH-029-AC06 | Welcome links sent after commit, ≤ 5 concurrent; a failed / unconfigured send leaves the row accepted with that `email_status`; dev token only in development/test. |
| ENH-029-AC07 | A database-level email conflict during a row's create rolls back only that row; the rest of the batch commits. |
| ENH-029-AC08 | Concurrent onboarding uploads never both create the same (name, city); the later one waits (then rejects duplicates) or gets 409. |
| ENH-029-AC09 | Template is header-only with every §5.1 column; admin-only (403 otherwise); `no-store`. |
| ENH-029-AC10 | `POST /overseas-admin/schools` and all ENH-028 endpoints behave and respond exactly as before. |
| ENH-029-AC11 | Panel: collapsed default, no-file, uploading, file-error, network-retry (same key), report (sent / not delivered / replay wording) states; accessible; usable at 360 px. |

## 11. Tests (written before code — TDD)

**API (`apps/api/tests/`, real Postgres via existing fixtures):**
- `test_enh_029_bulk_onboarding.py` — AC01–AC09: happy path with full audit/role-assignment/token assertions; one test per row
  rule; file-level rejections; replay and key reuse; welcome delivery mocked (sent / not_configured / raises) with a concurrency
  probe proving ≤ 5 in flight; savepoint isolation (rule-6 `IntegrityError` forced by inserting the user between pre-load and
  create via a monkeypatched hook); advisory-lock 409 (second connection holds the lock); dev token present in `test`, absent on
  replay; template contents/headers/403; both new paths reachable (no shadowing).
- `test_enh_029_migration.py` — `0052` follows `0051` and is the single head; constraint accepts `school_onboarding` and still
  rejects an unknown value; only the constraint changes; downgrade refuses when onboarding batches exist.
- `test_enh_029_provision_refactor.py` — single create response keys/values and audit actions unchanged; single-create email
  race still → 409 (flush_unique_email path intact).
- Regression (must pass unchanged): `test_sch_003_*`, `test_enh_003_*`, `test_enh_009_*`, `test_enh_023_*`, `test_sch_011_*`,
  `test_enh_028_*`, `test_sch_002_*`.

**Web (`apps/web/tests/`):**
- `components/AdminSchoolBulkOnboardPanel.test.tsx` (Vitest + Testing Library) — every AC11 state; same key on retry after a
  network error; new key on new file; report wording for sent / not delivered / replay; focus moves to the report.
- `e2e/enh-029-bulk-school-onboarding.spec.ts` (Playwright) — admin uploads 3 rows (2 valid, 1 duplicate email) → report 2/1;
  new school visible in Partner Schools; a new coordinator sets a password via the dev token and signs in; 360 px viewport check.
- Regression: `sch-003-school-onboarding.spec.ts`, `enh-028-bulk-entry.spec.ts`, `AdminSchoolCreatePanel.test.tsx`,
  `SchoolBulkEntryPanel.test.tsx`.

## 12. Decision record (`DEC-SCOPE-044`, to be recorded in `PRODUCT_DECISION_REGISTER.md`)

"ENH-029 bulk school onboarding: Overseas Admin/Super Admin CSV upload, all `SchoolCreate` columns (D1), bulk-only rejection of
duplicate (name, city) and duplicate/existing coordinator emails (D2), 1 MB / 100 rows with post-commit welcome links ≤ 5
concurrent (D3), one transaction with per-row savepoints on ENH-028's generalized tables (`target_type = 'school_onboarding'`)
(D4), create-only (D5), ENH-028 idempotency (D6)." Status `CONFIRMED_CURRENT` only once the user approves this spec.

## 13. Regression risks and mitigations

| Risk | Mitigation |
|---|---|
| Extracting `create_school`'s body changes the single create | pure move, default `flush_coordinator=flush_unique_email`; SCH-003/ENH-003/ENH-009/ENH-023/SCH-011 tests + ~30 e2e specs that create schools through it; dedicated refactor test |
| `flush_unique_email`'s `db.rollback()` discarding a batch | bulk passes a plain flush inside a savepoint; AC07 test |
| Parameterizing ENH-028 private helpers | signatures only; ENH-028 suite (core, results, migration) + e2e must pass unchanged |
| Migration on the shared CHECK constraint | constraint-only, no data touched, data-guarded downgrade; migration + single-head tests |
| Welcome email volume / request latency | 100-row cap, Semaphore(5), delivery never raises and runs after commit (locks released) |
| Advisory lock contention | held only for the DB phase (≤ 100 rows); 5 s timeout → 409 with retry wording |
| Route shadowing under `/overseas-admin/schools/…` | only `PATCH /schools/{id}` is parameterized; tests hit both new paths |
| Shared Admin Schools page (`WorkflowPanel.tsx:475`) | panel appended after existing ones, collapsed by default; `sch-003` e2e re-run |
| Import cycles | `school_onboarding_bulk.py` imports from `admin.py` and `school_bulk.py`; neither imports it |

## 14. Docs to update (with the code)

`PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-044`), `API_CONTRACT.md` §12A, `DATA_MODEL.md` (bulk tables target list),
`RBAC_MATRIX.md`, `SECURITY_CONTROLS.md`, `SCREEN_CATALOG.md`, `USER_FLOW_MAP.md`, `MASTER_FEATURE_CATALOG.md`, `RTM.md`,
`ENHANCEMENT_BACKLOG.md` §ENH-029 (status + stale security note / line references corrected).
