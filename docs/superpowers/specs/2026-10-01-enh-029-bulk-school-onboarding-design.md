# ENH-029 — Bulk school partner onboarding (Admin, multiple schools at once) — design

**Status:** design sections 1–4 approved by the user in-session 2026-10-01; revised the same day after an API-design,
security-hardening and frontend-engineering review (§15) with the user's answers D8/D9; approved for implementation by the user
("Proceed with ENH-029", 2026-10-01) and recorded as `DEC-SCOPE-044`. Final-review addendum: §16.
**Feature:** `ENH-029` (`docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-029). **Branch:** `feature/enh-029-bulk-school-onboarding`.
**Decision:** `DEC-SCOPE-044` (§12) — recorded in `PRODUCT_DECISION_REGISTER.md` once this spec is approved.

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
| D1 | **Columns = every `SchoolCreate` field.** Required: `name`, `coordinator_full_name`, `coordinator_email`; all others optional. The row is validated by `SchoolCreate` itself — one rule set, no drift. | User |
| D2 | **Duplicate schools rejected, bulk only:** a row whose normalized (name, city) matches an existing school or an earlier row of the same file is rejected (that row only). The single create is unchanged (it does not check names). Coordinator email: existing or repeated in the file → rejected. | User |
| D3 | **Limits: ≤ 1 MB, 1–100 filled-in rows.** Welcome links sent after commit, **at most 5 at a time**, reusing `deliver_welcome_link` unchanged. No worker/queue. | User |
| D4 | **Approach A:** one request = one transaction; each row's create inside its own savepoint; ENH-028's `school_bulk_upload_*` tables with `target_type = 'school_onboarding'`; post-commit welcome delivery. | User (chosen over B: commit-per-row, C: client-side loop) |
| D5 | Create-only. No update/deactivate by bulk. | Design (backlog scope) |
| D6 | Idempotency exactly as ENH-028: key scoped to (uploader, target_type, key), file SHA-256 stored; same key + same file = replay; same key + different file = 422; in-flight duplicate waits ≤ 5 s, then 409. | Design (approved §1) |
| D7 | New router module `app/api/school_onboarding_bulk.py` (prefix `/overseas-admin`, precedent: `school_feedback.admin_router`, `school_transfers.admin_router`), so `admin.py` does not grow. | Design (approved §2) |
| D8 | **`school_bulk_upload_rows.created_user_id`** (nullable FK `users.id`) records the coordinator an onboarding row created; a replay names that exact account. ENH-028 rows leave it `NULL`. | User (chosen over a `profile.school_id` lookup) |
| D9 | **No extra rate limit.** Parity with the single create and ENH-028 S1; the 1 MB / 100-row caps bound a request, the advisory lock serializes uploads, everything is audited. Accepted risk, recorded in `SECURITY_CONTROLS.md`. | User |
| D10 | **One CSV parser for every bulk surface:** ENH-028's private parsing/claim helpers are parameterized (not copied), so file hardening (size, UTF-8, NUL, strict CSV, row cap) cannot drift between surfaces. | Design (review §15) |

## 3. Scope

**In:** one upload endpoint, one header-only template endpoint, one migration (constraint + one nullable column), a
behaviour-preserving extraction of `create_school`'s body, a small parameterization of three private `school_bulk.py` helpers,
one new React panel on the existing Admin Schools page, tests, docs.

**Out (unchanged):** `POST /overseas-admin/schools` request/response/audit; `GET /overseas-admin/schools`, `PATCH
/overseas-admin/schools/{id}`, tier preview, lookup; the four ENH-028 endpoints and their reports; the SCH-002 roster upload;
`provisioning.py`; tier entitlements; navigation; XLSX; async/background processing; editing schools by bulk; rate limiting.

## 4. Data model (migration `0052_school_onboarding_bulk`)

- `ck_school_bulk_upload_target_type` dropped and recreated as
  `target_type IN ('academic_result','psychometric_record','test_prep_record','language_record','school_onboarding')`.
- `school_bulk_upload_rows.created_user_id UUID NULL REFERENCES users(id)` added. No default, no backfill, no index (read only by
  batch id, which is already indexed).
- `BULK_TARGET_TYPES` (`models.py:1401`) gains `"school_onboarding"`; `SchoolBulkUploadRow` gains `created_user_id`.
- No existing row is read or written. Onboarding rows: `student_code = NULL`, `created_record_id = schools.id`,
  `created_user_id = users.id` (the coordinator).
- `downgrade()`: if any `school_onboarding` batch exists, raise (never silently delete onboarding history); otherwise drop the
  column and restore the 0051 constraint.
- `down_revision = "0051_school_bulk_uploads"`; must be the single head. Both statements are metadata-only on Postgres (adding a
  nullable column without a default does not rewrite the table; re-adding the CHECK validates the existing, small table once).

## 5. API contract

Both routes on `school_onboarding_bulk.router` (`prefix="/overseas-admin"`), registered in `main.py` after `admin.agents_router`.
No existing route shadows them: under `/overseas-admin/schools/…` only `PATCH /schools/{school_id}` and
`GET /schools/{school_id}/tier-change-preview` are parameterized, neither matches `GET bulk-template` / `POST bulk-upload`
(tests hit both new paths).

**Authentication:** `get_current_user` (httpOnly `edusphere_access` cookie, unchanged). **Authorization (both routes):**
`user.role in {"overseas_admin", "super_admin"}`, else `403 "Overseas Admin role required"` — identical to `create_school`;
checked first, before the body is read. **Error shape:** FastAPI's `{"detail": "<message>"}`, as every existing endpoint.

### 5.1 `GET /api/v1/overseas-admin/schools/bulk-template`

`200 text/csv; charset=utf-8`, `Content-Disposition: attachment; filename=school-onboarding-bulk-template.csv`,
`Cache-Control: private, no-store`. Header row only, in this order:

`name, city, state, tier, tier_valid_until, coordinator_full_name, coordinator_email, branch, address, contact_number, email,
website, grades_available, board, partnership_date, mou_reference, edusphere_bdm, monthly_visit_schedule, vice_principal_name`

The column list is one module constant (`SCHOOL_ONBOARDING_COLUMNS`), asserted by a test to equal `SchoolCreate`'s field set,
so a future `SchoolCreate` field cannot be silently missing from the template.

### 5.2 `POST /api/v1/overseas-admin/schools/bulk-upload`

Multipart field `file`, header `Idempotency-Key` (1–120 of `[A-Za-z0-9._:-]`). The key is generated by the client once per
chosen file and reused on every retry of that file (intent, not attempt).

| Status | When | `detail` |
|---|---|---|
| 201 | processed — any mix of accepted/rejected rows, including all rejected | — (report) |
| 201 | replay: same key + same file | — (stored report; `email_status: null`) |
| 401 | no/invalid session | existing messages |
| 403 | wrong role | `Overseas Admin role required` |
| 409 | the same key is mid-flight, or another onboarding upload holds the lock, for > 5 s | `This upload is still being processed; retry shortly` |
| 413 | file > 1 MB | `The file is larger than 1 MB` |
| 422 | key missing / malformed | `Idempotency-Key header is required` / `Idempotency-Key must be 1-120 letters, digits or . _ : -` |
| 422 | not UTF-8, NUL byte, malformed CSV | `The file must be a UTF-8 CSV` |
| 422 | missing required header | `Missing required column: <name>` |
| 422 | header not in §5.1 | `Unknown column: <name>` (name truncated to 40 chars) |
| 422 | a header repeated | `Duplicate column: <name>` |
| 422 | no filled-in rows / > 100 | `The file has no filled-in rows` / `The file has more than 100 filled-in rows` |
| 422 | same key, different file | `Idempotency-Key was already used for a different file` |

`201` on replay matches ENH-028 (the route's declared status); the report is identical except `email_status`, which describes
a delivery attempt that happened once.

**Report:**

```json
{
  "id": "uuid", "target_type": "school_onboarding", "status": "completed",
  "total_rows": 3, "accepted_count": 2, "rejected_count": 1,
  "rows": [
    {"row_number": 2, "status": "accepted", "error_message": null, "created_record_id": "school uuid",
     "school_code": "AB12CD34", "school_name": "Sunrise Public School",
     "coordinator_id": "user uuid", "coordinator_email": "c@x.in", "email_status": "sent"},
    {"row_number": 3, "status": "rejected", "error_message": "Email already exists", "created_record_id": null,
     "school_code": null, "school_name": null, "coordinator_id": null, "coordinator_email": null, "email_status": null}
  ]
}
```

- Every row object always has every key (no conditional shapes). `row_number` = CSV file line (header = line 1), file order.
- `school_code`/`school_name`/`coordinator_email` come from the created records; on replay one query joins `schools` by
  `created_record_id` and `users` by `created_user_id`.
- `email_status` (`sent` | `not_configured` | `failed`) only on the first response; `null` on replay and on rejected rows.
- `development_welcome_token`: present on accepted rows of the first response **only** when
  `settings.environment in DEV_TOKEN_ENVIRONMENTS` (exact parity with the single create); never on replay, never in production.

## 6. Row rules (in order; the first failure wins; one message per row)

A row is "filled in" when at least one §5.1 column has a non-blank cell; fully blank rows are skipped, never reported. Cells are
trimmed; a blank cell is "not provided" (omitted before validation, so optional fields become `None`).

1. `SchoolCreate.model_validate(cells)` — failure → `validation_message(exc)` (existing helper; never echoes the value).
2. Coordinator email normalized with `_valid_email` (lower-case, trimmed; an invalid address → its existing message
   `A valid email address is required`), then equal to an earlier row's (that passed this rule) → `same coordinator_email as row N`.
3. Email already exists in `users` (pre-loaded in one query, case-insensitive as stored) → `Email already exists`.
4. Normalized (name, city) equals an existing school's → `a school with this name and city already exists`.
   Normalization: `casefold()`, whitespace runs collapsed to one space, trimmed; `None` city ≡ empty city.
5. Normalized (name, city) equals an earlier row's in this file → `same school name and city as row N`.
6. Create via `_provision_school` inside `db.begin_nested()`:
   - `HTTPException` raised by the helper's own checks (tier, length via `_fit`) → its `detail`.
   - `IntegrityError` (a concurrent create took the email, or a `school_code` collision) → savepoint rolled back →
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
Bulk passes a plain flush: `flush_unique_email` calls `db.rollback()`, which would discard the whole batch transaction, not just
the row; inside the savepoint a plain flush lets the `IntegrityError` roll back only that row.

**Parameterized `school_bulk.py` private helpers (D10; ENH-028 behaviour and messages unchanged):**
- `_file_error(target_type: str, user, reason, message, status=422)` — was `target: BulkTarget`.
- `_read_csv(raw, *, target_type, user, required, columns, max_rows, known=None)` holds today's parsing; ENH-028's
  `_filled_rows(raw, target, user)` becomes a one-line call (`required=("student_code", *target.required)`,
  `columns=target.columns`, `max_rows=MAX_ROWS`, `known=None` → no unknown/duplicate-column checks, exactly as today).
  Onboarding passes `known=SCHOOL_ONBOARDING_COLUMNS`, enabling the unknown- and duplicate-column 422s.
- `_claim(db, target_type: str, user, key, digest)` → the new batch, or `(existing_batch, rows)` on replay; ENH-028's `_upload`
  builds `_report(...)` from that tuple exactly as `_claim` does today.

**One request = one transaction, then post-commit delivery:**

1. Role → key format → read ≤ 1 MB + 1 byte → SHA-256 → parse → any 403/413/422 before the first DB write.
2. `SELECT set_config('lock_timeout', :timeout, true)` (bound parameter, ENH-028's 5 s).
3. `_claim` the key (the unique index arbitrates; lock timeout → 409; replay → stored report, nothing else runs).
4. `SELECT pg_advisory_xact_lock(:key)` with a fixed module constant `SCHOOL_ONBOARDING_LOCK_KEY` (bound integer) — serializes
   onboarding uploads so two cannot both pass rules 4–5 for the same school; lock timeout → 409. Released at commit/rollback,
   before any email is sent.
5. Pre-load: existing users among the file's normalized emails (one parameterized `IN` query); all schools' (name, city) (one
   query, normalized in Python).
6. Per row: §6 rules → `SchoolBulkUploadRow(status, error_message, created_record_id, created_user_id)`.
7. Batch counts; `AuditLog(action="school.bulk_upload", entity_type="school_bulk_upload_batch", metadata_json={target_type,
   total, accepted, rejected, file_sha256})`; **commit**. Per accepted row the helper has already added the `UserRoleAssignment`
   and the `school.create`, `school.coordinator_seed`, `user.welcome_link_issue` audits — identical to the single create.
8. Build the report from memory; `asyncio.Semaphore(5)` + `asyncio.gather` over accepted rows calling `deliver_welcome_link`
   (never raises; audits delivery in its own session; `expire_on_commit=False`, so reading `coordinator.email/full_name/role`
   after commit is safe, as in the single create). Attach `email_status` (+ dev token where allowed).
9. Log `bulk_upload_completed` {batch_id, target_type, actor_id, total, accepted, rejected, duration_ms} — ids and counts only.

**Failure guarantees:** any exception before step 7's commit rolls back everything (no batch, schools, users, tokens or audits;
the key is free, so a retry reprocesses cleanly). Unexpected errors surface as the app's generic 500 — no SQL or stack text in
the body. After commit nothing undoes a school; an undelivered link leaves the coordinator `pending_setup`, re-sendable from the
Users page (existing ENH-003 flow). A client that loses the response retries with the same key and gets the replay.

**Race notes:**
- Same key, concurrent: the second request waits on the unique index, then replays (or 409 after 5 s).
- Different keys, concurrent: serialized by the advisory lock; the second sees the first's committed schools/emails and rejects
  duplicates (rules 3–4), or gets 409 after 5 s.
- Bulk vs single create: email protected by the `users.email` unique index + savepoint (rule 6). School name not serialized —
  the single create never checks names (parity, documented).
- `school_code` generation (`unique_student_code`) sees the batch's own flushed rows; a collision with a concurrent create is a
  rule-6 `IntegrityError` for that row only.

## 8. Security (threat model and controls)

**Trust boundary:** the uploaded file and its header row, the `Idempotency-Key` header, the session cookie. **Assets:**
login-capable Coordinator accounts, set-password tokens, school records, the audit trail.

| Concern | Control |
|---|---|
| Authentication | `get_current_user`: httpOnly `edusphere_access` cookie, `type == "access"`, active user only. Unchanged. |
| Authorization / role escalation | Exact `create_school` role set, checked before reading the body. The file cannot choose a role, division or status: the helper hard-codes `school_coordinator` / `overseas` / active / unusable password. Unknown columns (e.g. `role`, `password`, `coordinator_password`) are a file-level 422, and `SchoolCreate` is `extra="forbid"`. |
| IDOR | No id is accepted from the client. Replays are keyed by (uploader, target_type, key): one admin can never read another's report. No `GET batch/{id}` endpoint. |
| Account takeover via existing email | An existing email is rejected (rule 3 / unique index); bulk never modifies or re-invites an existing user. |
| Input validation | 1 MB / 100-row caps; UTF-8 only; NUL rejected; `csv` strict mode; header allowlist + duplicate detection; per-field `SchoolCreate` limits/enums/dates; `_fit` on the coordinator name; `_valid_email`. |
| SQL injection | ORM / bound parameters only (`set_config`, advisory-lock key, `IN` list). No string-built SQL. |
| XSS | Error messages never echo cell values (`validation_message`); echoed header names are truncated and rendered by React as text (no `dangerouslySetInnerHTML`). |
| CSRF | `SameSite=Lax` session cookie (not sent on cross-site POST) + the required custom `Idempotency-Key` header (a cross-site form cannot set it; a cross-site `fetch` needs a CORS preflight). The template GET is read-only and contains no data. |
| Token / session handling | One welcome token per coordinator via `issue_welcome_token` (hash stored, 72 h, raw never logged or audited). Raw token only in the dev/test-only `development_welcome_token`; never on replay. |
| Secret exposure / sensitive logs | Logs carry ids, counts, reasons and `target_type` only — never emails, names, file contents or tokens. Audit metadata: counts + `file_sha256`. |
| Rate limiting | D9: none added (parity); bounded per request, serialized by the advisory lock, audited. Recorded as an accepted risk. |
| DoS | 1 MB read cap (`file.read(MAX + 1)`), 100 rows, 5 s lock timeout, ≤ 5 concurrent SMTP sends, emails sent after locks are released. |
| Audit (repudiation) | Batch: `school.bulk_upload`. Per row: `school.create`, `school.coordinator_seed`, `user.welcome_link_issue`, `user.welcome_link_delivery`. Batch/row tables keep the per-row outcome. |
| CSV formula injection | The template is header-only. Stored values have the same exposure as the single create (parity; out of scope). |

## 9. Frontend

**Placement:** new `apps/web/components/AdminSchoolBulkOnboardPanel.tsx`, rendered in `WorkflowPanel.tsx` under the existing
`showSchoolCreate` condition after `<AdminSchoolCreatePanel/>` and `<AdminSchoolEditPanel/>` (browser QA-029-02/09: those two keep
sharing a row, as before ENH-029), spanning the full action grid. No new route, nav entry or role logic.

**Design language:** an `action-card` with an `h3`, like its sibling panels on the Admin Schools page (`AdminSchoolCreatePanel`,
`AdminSchoolEditPanel`), using existing classes only — `form`, `field`, `field-help`, `btn`/`btn secondary`, `muted`,
`table-wrap`/`table` with `data-label` cells, `form-message`/`form-warning`/`form-error` via `toneClass`, `visually-hidden`.
No new CSS unless a gap is proven.

**Reuse:** `BulkColumn` type and a new `SCHOOL_ONBOARDING_COLUMNS` list in `lib/bulkEntry.ts` (documentation only — the server is
authoritative); `toneClass` and `errorText` from `lib/welcomeLink.ts`; ENH-028's file-plus-key pattern. A separate component,
not a generalized `SchoolBulkEntryPanel`: that panel's copy, empty state and report columns are student-specific, and changing
it would put ENH-028 at risk. The report table is a small local subcomponent so each piece stays under ~150 lines.

**Visual hierarchy:** `h3` "Onboard several schools (CSV)" + one-line purpose; two numbered steps ("1. Download the template",
"2. Upload the filled-in file") as `h4`; the column reference collapsed in a `<details>` so the card stays compact next to the
single-school form; the result summary above the table.

**Form and keyboard:** native `<input type="file" accept=".csv,text/csv">` with a visible `<label>` and `aria-describedby` help
("CSV, up to 1 MB and 100 schools. One school per row."); native `<button>`; `<details>/<summary>`. Tab order: template link →
column reference → file → Upload. Enter submits. No custom key handling.

**States:**
- **Idle:** template link + file input; Upload enabled.
- **Client pre-checks (instant, not a security boundary):** no file → "Choose a filled-in CSV file first."; > 1 MB → "The file
  is larger than 1 MB."; not `.csv` → "Choose a .csv file." Shown in `role="alert"`; nothing is sent.
- **Uploading:** button "Uploading…", file input + button disabled (no double submit), form `aria-busy`, polite live region:
  "Uploading — creating schools and sending set-password emails. Large files can take up to a minute." The previous report
  stays hidden until the new one arrives.
- **File-level error (4xx):** server `detail` (via `errorText`) in `role="alert"`; the chosen file and its key are kept so the
  admin can retry or choose a corrected file (a new file → new key).
- **Network error:** "The connection dropped. Upload again — the same file won't be added twice." (same key re-sent → replay).
- **Report:** heading "Upload result" receives focus. Summary via `toneClass`: all accepted → success "N schools onboarded.";
  some rejected → warning "N of M schools onboarded, K rejected. Schools that succeeded are kept — fix the rejected rows and
  upload just those."; all rejected → error "No schools were onboarded. Fix the rows below and upload again." Undelivered
  emails add: "K welcome emails were not delivered — re-send from the Users page." Table (file order): Row · Result
  (Added/Rejected) · School ID · School · Coordinator · Detail. Detail: rejected → `error_message`; `sent` → "Set-password link
  emailed"; `not_configured`/`failed` → "Email not delivered — re-send from the Users page"; replay (`null`) → "Check the Users
  page for set-password status". Result is text, never colour alone.
- **After success:** `router.refresh()` so the Partner Schools list and the edit panel's lookup include the new schools; file
  input cleared.
- **Empty:** not applicable (no list is loaded); an upload whose rows are all blank gets the server's "no filled-in rows" 422.

**Responsive / mobile:** the card spans the full `action-grid` (`.action-grid > .bulk-onboarding`), so the six-column report
fits on a desktop. Below 760 px — where the table's 650 px minimum no longer fits — the report (`table.bulk-report`) becomes one
labelled card per row from each cell's `data-label` (the QA27-05 pattern), with `overflow-wrap: anywhere`. Browser QA-029-02/03
found the earlier half-width card hid the Detail column on desktop and never stacked on phones; pinned by Playwright at 1440,
820, 390 and 320 px.

**Perceived performance:** instant client pre-checks; immediate busy state with honest duration copy; no full-page reload
(`router.refresh()` only).

## 10. Acceptance criteria

| ID | Criterion |
|---|---|
| ENH-029-AC01 | Overseas Admin / Super Admin uploads N valid rows → 201; N schools (unique `school_code`), N active `school_coordinator` users with unusable passwords, N `UserRoleAssignment`s, one welcome token each, per-row audits identical to the single create; report `accepted_count = N` with `created_record_id`/`coordinator_id` set. |
| ENH-029-AC02 | Mixed file → each invalid row rejected with its own message, each valid row created; `accepted + rejected = total_rows`; batch audit `school.bulk_upload` recorded; all-rejected file is still 201. |
| ENH-029-AC03 | Row rejected (only that row) for: invalid field (tier, board, date, length, missing required, bad email); coordinator email existing or repeated earlier in the file; normalized (name, city) existing or repeated earlier in the file. |
| ENH-029-AC04 | Same key + same file → same report (names/codes/emails from `created_record_id`/`created_user_id`, `email_status` null, no dev token), nothing created, no email sent; same key + different file → 422. |
| ENH-029-AC05 | File-level rejections create nothing: 401, 403, key missing/malformed, 413 > 1 MB, non-UTF-8/NUL/malformed CSV, missing required / unknown / duplicate column, 0 rows, > 100 rows. A `role`/`password` column is rejected as unknown. |
| ENH-029-AC06 | Welcome links sent after commit, ≤ 5 concurrent; a failed / unconfigured send leaves the row accepted with that `email_status`; dev token only in development/test. |
| ENH-029-AC07 | A database-level email conflict during a row's create rolls back only that row; the rest of the batch commits. |
| ENH-029-AC08 | Concurrent onboarding uploads never both create the same (name, city); the later one waits (then rejects duplicates) or gets 409. |
| ENH-029-AC09 | Template is header-only with exactly the `SchoolCreate` fields in §5.1 order; admin-only; `no-store`. |
| ENH-029-AC10 | `POST /overseas-admin/schools` and all ENH-028 endpoints behave and respond exactly as before; migration 0052 preserves every existing batch/row. |
| ENH-029-AC11 | Panel: idle, client pre-check, uploading, file-error, network-retry (same key), report (all/some/none accepted; sent / not delivered / replay wording) states; keyboard-operable; screen-reader announcements; focus to report; usable at 320 px. |
| ENH-029-AC12 | No email address, name, file content or token appears in application logs for any upload outcome. |

## 11. Tests (written before code — TDD)

**API (`apps/api/tests/`, real Postgres via existing fixtures):**
- `test_enh_029_bulk_onboarding.py` — AC01–AC09, AC12: happy path with full audit/role-assignment/token assertions; one test per
  row rule; every file-level rejection (incl. `role`/`password` columns, duplicate header); replay (shape identical, no dev token,
  no second delivery) and key reuse; delivery mocked (sent / not_configured / raises) with an in-flight counter proving ≤ 5;
  savepoint isolation (rule-6 `IntegrityError` forced by inserting the user after pre-load); advisory-lock 409 (a second
  connection holds the lock); dev token present in `test`; template contents equal `SchoolCreate.model_fields` order / headers
  / 403; both new paths reachable (no shadowing); `caplog` shows no emails/names/tokens.
- `test_enh_029_migration.py` — `0052` follows `0051` and is the single head; constraint accepts `school_onboarding`, still
  rejects an unknown value; `created_user_id` nullable FK; existing 0051 rows survive upgrade; downgrade refuses when onboarding
  batches exist and succeeds otherwise.
- `test_enh_029_provision_refactor.py` — single create response keys/values and audit actions unchanged; single-create email
  race still → 409 (the `flush_unique_email` path intact).
- Regression (must pass unchanged): `test_sch_003_*`, `test_enh_003_*`, `test_enh_009_*`, `test_enh_023_*`, `test_sch_011_*`,
  `test_enh_028_*`, `test_sch_002_*`.

**Web (`apps/web/tests/`):**
- `components/AdminSchoolBulkOnboardPanel.test.tsx` (Vitest + Testing Library) — every AC11 state; client pre-checks send no
  request; same key on retry after a network error; new key on a new file; three summary tones; per-row Detail wording; focus on
  the report heading; busy state disables controls.
- `e2e/enh-029-bulk-school-onboarding.spec.ts` (Playwright) — admin uploads 3 rows (2 valid, 1 duplicate email) → report 2/1;
  new school visible in Partner Schools; a new coordinator sets a password via the dev token and signs in; re-upload of the same
  file object replays; keyboard-only upload; 360 px viewport check.
- Regression: `sch-003-school-onboarding.spec.ts`, `enh-028-bulk-entry.spec.ts`, `AdminSchoolCreatePanel.test.tsx`,
  `SchoolBulkEntryPanel.test.tsx`.

## 12. Decision record (`DEC-SCOPE-044`, recorded in `PRODUCT_DECISION_REGISTER.md`)

"ENH-029 bulk school onboarding: Overseas Admin/Super Admin CSV upload, all `SchoolCreate` columns (D1), bulk-only rejection of
duplicate (name, city) and duplicate/existing coordinator emails (D2), 1 MB / 100 rows with post-commit welcome links ≤ 5
concurrent (D3), one transaction with per-row savepoints on ENH-028's generalized tables (`target_type = 'school_onboarding'`)
(D4), create-only (D5), ENH-028 idempotency (D6), `created_user_id` on row reports (D8), no extra rate limit (D9), one shared
CSV parser (D10)." Status `CONFIRMED_CURRENT` only once the user approves this spec.

## 13. Regression risks and mitigations

| Risk | Mitigation |
|---|---|
| Extracting `create_school`'s body changes the single create | pure move, default `flush_coordinator=flush_unique_email`; SCH-003/ENH-003/ENH-009/ENH-023/SCH-011 tests + ~30 e2e specs that create schools through it; dedicated refactor test |
| `flush_unique_email`'s `db.rollback()` discarding a batch | bulk passes a plain flush inside a savepoint; AC07 test |
| Parameterizing ENH-028 private helpers | signatures only, `known=None` keeps today's header behaviour; ENH-028 suite (core, results, migration) + e2e unchanged |
| Migration on the shared table | CHECK swap + nullable column, no backfill, data-guarded downgrade; migration test asserts 0051 rows survive |
| `SchoolBulkUploadRow` model gains a column | ENH-028 never sets it (NULL); its `_report` does not expose it — ENH-028 response unchanged |
| Welcome email volume / request latency | 100-row cap, Semaphore(5), delivery never raises and runs after commit (locks released) |
| Advisory lock contention | held only for the DB phase; 5 s timeout → 409 with retry wording |
| Route shadowing under `/overseas-admin/schools/…` | no parameterized GET/POST at that depth; tests hit both new paths |
| Shared Admin Schools page (`WorkflowPanel.tsx:475`) | panel appended after existing ones; `sch-003` e2e re-run |
| Import cycles | `school_onboarding_bulk.py` imports from `admin.py` and `school_bulk.py`; neither imports it |

## 14. Docs to update (with the code)

`PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-044`), `API_CONTRACT.md` §12A, `DATA_MODEL.md` (bulk tables: target list +
`created_user_id`), `RBAC_MATRIX.md`, `SECURITY_CONTROLS.md` (controls + D9 accepted risk), `SCREEN_CATALOG.md`,
`USER_FLOW_MAP.md`, `MASTER_FEATURE_CATALOG.md`, `RTM.md`, `ENHANCEMENT_BACKLOG.md` §ENH-029 (status + stale security note /
line references corrected).

## 15. Review findings applied (2026-10-01)

**API and interface design:** every report row now has a fixed shape (no conditional keys); `coordinator_id` added so the row is
self-describing; replay rebuilt from stored ids (D8) instead of a heuristic; duplicate-header and unknown-header 422s; echoed
header names truncated; all-rejected file explicitly 201 (row outcomes are data, not a request failure); replay status 201
kept for ENH-028 consistency; key claimed atomically via the unique index, same-key-different-file 422, in-flight duplicate
bounded wait → 409 — all reused from ENH-028; template columns pinned to `SchoolCreate` by a test.

**Security and hardening:** STRIDE table (§8); role/password columns rejected at the header; existing-account takeover ruled out;
CSRF analysis recorded (Lax cookie + custom header); log/audit content pinned by AC12; rate limiting explicitly decided (D9)
rather than omitted; single shared parser so file hardening cannot drift (D10).

**Frontend UI engineering:** `action-card` instead of a collapsed card, matching sibling panels; `h3`/`h4` hierarchy; instant
client pre-checks; honest long-running busy copy; three summary tones with a fix-and-re-upload instruction; per-row email
outcome wording; `errorText`/`toneClass` reused instead of a new `detailMessage`; keyboard-only and 320 px checks added.

## 16. Final-review addendum (2026-10-01, after implementation)

- **Password hashing off the event loop.** `unusable_password_hash()` (bcrypt, cost 12, synchronous) ran once per row on the event
  loop while the onboarding lock was held. Bulk now computes one hash per filled-in row in worker threads after claiming the key
  and **before** taking the advisory lock, and passes it to `_provision_school(..., password_hash=...)` (optional; the single
  create still computes its own). Pinned by `test_password_hashing_never_runs_on_the_event_loop` and a 100-row success test.
- **Row lock timeout.** A row insert that waits past `lock_timeout` on another request's uncommitted create of the same email is
  rejected with the rule-6 conflict message instead of failing the batch (`DBAPIError` with SQLSTATE 55P03 joins
  `IntegrityError`). Pinned by `test_a_row_waiting_on_an_uncommitted_create_of_its_email_is_rejected_alone`.
- **Migration evidence.** §11's round-trip and downgrade-refusal tests now run against a throwaway database (the AGN-004
  harness), not only the migration source text.
- **Plain-HTTP origins (browser QA-029-01).** `crypto.randomUUID` exists only in secure contexts, so on a plain-HTTP page reached by
  IP or hostname choosing a file threw and the panel reported "Choose a filled-in CSV file first.". The panel's key now comes from
  `lib/idempotencyKey.newIdempotencyKey()`: `randomUUID` when present, otherwise a version-4 UUID from `crypto.getRandomValues`
  (available in every context). Pinned by `idempotencyKey.test.ts` and a panel test without `randomUUID`; re-verified in a browser
  on an insecure origin. The same defect existed in the app's four other `Idempotency-Key` senders (`SchoolBulkEntryPanel`,
  `SchoolBulkUploadPanel`, `FeePaymentPanel`, `DataPrivacyPanel`); they use the same helper now, pinned by
  `plainHttpIdempotencyKey.test.tsx`, and the ENH-028 / SCH-002 / ENH-029 Playwright specs pass on a plain-HTTP origin.
