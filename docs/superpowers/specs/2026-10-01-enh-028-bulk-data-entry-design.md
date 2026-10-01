# ENH-028 — Bulk data entry: Academic Results, Psychometric, Test Prep, Language — design

**Status:** DRAFT — awaiting user review (Superpowers brainstorming gate). Not `EXPLICIT_APPROVAL` until the user approves
this file. **Feature:** `ENH-028` (`docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-028). **Branch:** `feature/enh-028-bulk-entry`.
**Decision:** proposed `DEC-SCOPE-042` (provisional number; §12), recorded in the register only once this spec is approved.

## 1. Evidence and intent

- **Request (MEETING_TRANSCRIPT_REQUEST, quoted in the backlog):** *"check for the possibility of bulk uploads for various pages
  like results, exams, psychometrics tests etc."* — an Academic Team member enters a whole class's exam marks, a Psychometric
  Team member a whole batch's assessments, in one action instead of one row at a time.
- **Backlog acceptance:** each module gets a bulk-entry path with idempotent replay on a repeated key, per-row validation that
  never blocks the batch, and a batch/row audit trail matching the roster upload's shape.
- **Existing authority:** `DEC-SCOPE-010` part 2 (CONFIRMED_CURRENT 2026-09-14) put academic-results bulk upload in scope;
  `DEC-SCOPE-018` (Test Prep/Language), `DEC-ROLE-006/007` (roles, Draft→Verified→Published, uploader ≠ verifier),
  `DEC-SCOPE-030` (tier gates), `DEC-SCOPE-035` (ENH-027 psychometric fields; "ENH-028 bulk entry reuses this shape").
- **Design answers given by the user in-session (2026-10-01):** D1–D6 below.

## 2. Decisions

| # | Decision | Source |
|---|---|---|
| D1 | **Create-only.** Each accepted row creates one new record exactly like the module's single `POST`. No updates by bulk. | User |
| D2 | Rows identify students by **`student_code`** (`school_students.student_code`, unique, non-null). | User |
| D3 | Parents get **the same per-record notice the single create sends, after the batch commits**; a rejected row never notifies; a failed send never undoes a record. Results notify nothing (only Publish does, unchanged). | User |
| D4 | Limits: **≤ 1 MB file, 1–500 filled-in rows**, new endpoints only (roster upload unchanged). | User |
| D5 | Modules: **Results (SCH-006), Psychometric (SCH-005/ENH-027), Test Prep and Language (SCH-009)**. Career records (SCH-004) and trainer assessments (TRN-007) are out. "Exams" = exam marks entered as Results. | User |
| D6 | **Duplicates are rejected (that row only), bulk only**: against existing records and earlier rows of the same file. Single `POST`s unchanged. | User |
| D7 | One generalized `school_bulk_upload_batches` / `school_bulk_upload_rows` table pair with a `target_type` discriminator (backlog's preferred option). The roster tables are not touched. | Design (approved §1) |
| D8 | New router module `app/api/school_bulk.py` (precedent: `school_attendance.py`, `school_skills.py`), reusing `schools.py` helpers by import. | Design (approved §1) |
| D9 | Idempotency key scoped to **(uploader, target_type, key)**, file SHA-256 stored; same key + different file = 422. | Design (approved §3) |
| D10 | 20 new uploads per user per hour (replays exempt), counted from the batch table. | Design (§3, flagged optional — user may drop) |

## 3. Scope

**In:** four bulk-upload endpoints, four pre-filled template downloads, one batch-report read, one migration (two new tables),
one new React panel mounted on the Academic Team and Psychometric Team dashboards, tests, contract/data-model docs.

**Out (unchanged):** every existing single-record endpoint and response; the roster upload (`/school/students/bulk-upload`,
`SchoolRosterUploadBatch/Row`); Draft→Verified→Published and its rules; `require_school_entitlement`; readers (analytics,
transfers, portfolio, 360, reports/PDF, parent portal); attendance; career records; updates via bulk; async/background
processing; XLSX.

## 4. Data model (migration `0049_school_bulk_uploads`, create-table only)

`school_bulk_upload_batches`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `target_type` | String(30) | CHECK in (`academic_result`, `psychometric_record`, `test_prep_record`, `language_record`) |
| `uploaded_by_user_id` | UUID FK users | from the session only |
| `idempotency_key` | String(120) | |
| `file_sha256` | String(64) | hex digest of the raw bytes |
| `total_rows`, `accepted_count`, `rejected_count` | Integer | `accepted + rejected = total` once `completed` |
| `status` | String(20) | `processing` → `completed` (same commit; `processing` is never visible to another session) |
| `created_at`, `updated_at` | timestamptz | `TimestampMixin` |

UNIQUE `(uploaded_by_user_id, target_type, idempotency_key)` named `uq_school_bulk_upload_key`; index on
`(uploaded_by_user_id, created_at)` for the throttle count. No `school_id`: a portfolio spans schools.

`school_bulk_upload_rows`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `batch_id` | UUID FK batches, indexed | |
| `row_number` | Integer | file line number (header = line 1) |
| `status` | String(20) | `accepted` / `rejected` |
| `error_message` | Text, nullable | never echoes a submitted value |
| `student_code` | String(8), nullable | as typed (normalized upper-case), for the report |
| `school_student_id` | UUID FK school_students, nullable | set when the code resolved |
| `created_record_id` | UUID, nullable, **no FK** | id in the target table (polymorphic) |

No existing table is altered; no existing row read or written; `downgrade()` drops both tables.

## 5. API contract

All under `/api/v1/school`, authenticated by the existing session cookie (`get_current_user`).

| Method & path | Role |
|---|---|
| `GET /academic-team/results/bulk-template` · `POST /academic-team/results/bulk-upload` | `academic_team` |
| `GET /psychometric-team/records/bulk-template` · `POST /psychometric-team/records/bulk-upload` | `psychometric_team` |
| `GET /academic-team/test-prep-records/bulk-template` · `POST /academic-team/test-prep-records/bulk-upload` | `academic_team` |
| `GET /academic-team/language-records/bulk-template` · `POST /academic-team/language-records/bulk-upload` | `academic_team` |
| `GET /bulk-uploads/{batch_id}` | the uploader only |

Static `bulk-*` segments are registered before any dynamic `/{id}` route on the same prefix (roster-template precedent).

### 5.1 Upload responses (multipart field `file`, header `Idempotency-Key`)

Checked in this order; every non-201 writes nothing (except the tier-denial audit, which only rides the 201 commit).

| # | Condition | Status / `detail` |
|---|---|---|
| 1 | no session | 401 (existing) |
| 2 | wrong role | 403 `<Team> role required` (existing message per module) |
| 3 | key missing / not 1–120 chars of `[A-Za-z0-9._:-]` | 422 `Idempotency-Key header is required` / `Idempotency-Key must be 1-120 letters, digits or . _ : -` |
| 4 | file > 1 MB (read stops at 1 MB + 1 byte) | 413 `The file is larger than 1 MB` |
| 5 | key already used by this user for this module: same SHA-256 | **201** + stored report (replay) |
| 5b | … different SHA-256 | 422 `Idempotency-Key was already used for a different file` |
| 5c | same key still processing in another request (> 5 s) | 409 `This upload is still being processed; retry shortly` |
| 6 | > 20 new uploads in the last hour by this user | 429 `Too many bulk uploads; try again in N seconds` + `Retry-After` |
| 7 | not UTF-8 (BOM allowed) / contains NUL / malformed CSV | 422 `The file must be a UTF-8 CSV` |
| 8 | a required header missing | 422 `Missing required column: <name>` |
| 9 | 0 filled-in rows / > 500 | 422 `The file has no filled-in rows` / `The file has more than 500 filled-in rows` |
| 10 | student-row lock not acquired in 5 s | 409 `These students are being updated by another request; retry shortly` |
| 11 | otherwise | **201** + report |

Report (upload, replay and `GET /bulk-uploads/{id}` — identical shape):

```json
{"id": "…", "target_type": "academic_result", "status": "completed", "total_rows": 3,
 "accepted_count": 2, "rejected_count": 1,
 "rows": [{"row_number": 2, "status": "accepted", "error_message": null, "student_code": "A1B2C3D4", "created_record_id": "…"},
          {"row_number": 4, "status": "rejected", "error_message": "marks_obtained must not exceed max_marks", "student_code": "…", "created_record_id": null}]}
```

`GET /bulk-uploads/{id}`: 404 `Upload batch not found` for an unknown id **and** for another user's batch (no existence
oracle); 401/403 as usual (any School service-delivery role may call; ownership decides).

### 5.2 Templates

`text/csv; charset=utf-8`, `Content-Disposition: attachment; filename=<module>-bulk-template.csv`,
`Cache-Control: private, no-store`. Header row, then one row per student in the caller's portfolio (all portfolio schools,
ordered by school name, then student name): `student_code, student_name, school_name, <module columns blank>`. Any cell
written from stored text that starts with `=`, `+`, `-`, `@`, TAB or CR is prefixed with `'` (CSV formula injection).
Empty portfolio → header only.

## 6. Row rules

### 6.1 Shared

- A row whose module columns are all blank is **not filled in**: skipped, not counted, not reported (lets the template's
  untouched students pass). A fully blank line likewise. A row with module values but blank `student_code` is rejected
  `student_code is required`.
- `student_name` / `school_name` are ignored on upload; unknown extra columns are ignored (so a `status`, `uploaded_by_user_id`
  or `school_id` column has no effect).
- Cells are trimmed; `student_code` upper-cased. Lists split on `;` then go through `_clean_list` (ENH-025/027). Dates exactly
  `YYYY-MM-DD` (`_iso_date_or_none`). Single-line text refuses control/bidi characters (existing helpers); multi-line text
  uses `_clean_multiline_text`.
- **Rejection order (first failure wins, one message):** unknown code `student_code does not match a student` → outside
  portfolio `OUTSIDE_PORTFOLIO` (existing text) → tier denial (existing `_entitlement_denial` message) → field validation
  `<field> <reason>` → duplicate `this student already has a <noun> for the same <key fields>` (e.g. `this student already
  has a result for the same academic_year, term and subject`) / `same student and <key fields> as row N of this file`.
- Messages never echo submitted values (ENH-025 rule).

### 6.2 Results — `academic_result` (no tier gate, unchanged from single create)

Required `academic_year` (≤ 20), `term` (≤ 40), `subject` (≤ 80), `max_marks` (finite number, 0 < x ≤ 9999.99),
`marks_obtained` (finite number, 0 ≤ x ≤ `max_marks`); optional `grade` (≤ 10), `teacher_remarks` (`_clean_teacher_remarks`,
≤ 2000). Creates `status="draft"`, `uploaded_by_user_id` = uploader, `SchoolResultStatusHistory(none→draft)`, AuditLog
`school.result_create` `{subject, bulk_batch_id}`. Duplicate key: student + lower(year) + lower(term) + lower(subject).
*Bounds other than marks ≤ max exist only so a bad cell rejects a row instead of overflowing a column; marks ≤ max is the
one new business rule and applies to bulk only.*

### 6.3 Psychometric — `psychometric_record` (tier `psychometric_test`)

Required `assessment_type` (≤ 120); optional `report_url` (≤ 500, must start `http://` or `https://`) and the ten ENH-027
columns via `PsychometricResultFields`. `status = completed if report_url else assigned` (as single create). AuditLog
`school.psychometric_record_create` `{assessment_type, fields, bulk_batch_id}`. Duplicate key: student +
lower(assessment_type) + test_date (blank date is its own value).

### 6.4 Test Prep — `test_prep_record` (tier per row: `ielts_coaching` / `sat_coaching`)

Required `test_type` (`ielts`|`sat`, case-insensitive; else `test_type must be one of ielts, sat`); optional `target_score`
(≤ 20). AuditLog `school.test_prep_record_create` `{test_type, bulk_batch_id}`. Duplicate key: student + test_type.

### 6.5 Language — `language_record` (tier `foreign_language_classes`)

Required `language` (≤ 60); optional `level` (≤ 30). AuditLog `school.language_record_create` `{language, bulk_batch_id}`.
Duplicate key: student + lower(language).

## 7. Processing, transactions, concurrency

One request = one DB transaction, then post-commit notifications:

1. Role → key format → read file (bounded) → SHA-256.
2. `SET LOCAL lock_timeout = '5s'`. Claim the key: `INSERT` the batch in a savepoint. `IntegrityError` on
   `uq_school_bulk_upload_key` → roll back the savepoint, load the committed batch → replay (same hash) or 422 (different);
   lock timeout while the other request holds the key → 409 (5c). The unique index is the arbiter — no select-then-insert.
3. Throttle count (rows of this user in the last hour, excluding the just-claimed one) → 429 (the transaction rolls back, so
   the claimed key is released).
4. Parse/validate the file shape (7–9) → 422 (rollback releases the key).
5. One query resolves every distinct `student_code`; `SELECT … FOR UPDATE` on those students **ordered by id** (promotions
   pattern; lock order student → result matches transfer approval's request → student → parent → result, so no cycle);
   lock timeout → 409 (10).
6. Per filled-in row: rules §6 in order; tier decision cached per (school, service_key) using the pure `_entitlement_denial`
   (never `require_school_entitlement`, which commits on denial); one `TIER_DENIED` AuditLog per denied (school, key) per batch,
   added to the same transaction. Duplicates checked against one pre-loaded set per module (existing rows for the locked
   students) plus the keys accepted earlier in this file.
7. Insert records + per-record audit/history + row reports; batch counts, `status="completed"`, AuditLog `school.bulk_upload`
   `{target_type, total, accepted, rejected, file_sha256}`; **commit**.
8. Read everything the response needs, then notify parents per accepted row (Psychometric/Test Prep/Language only), each in
   `try: notify; commit / except: rollback; log warning` (ENH-026 pattern, `schools.py:2181-2196`).

**Failure guarantees:** any exception before step 7's commit rolls back everything (no batch, no records, key free → a
retry reprocesses cleanly). After the commit, nothing can undo records. Throttle is count-then-insert: two exactly
simultaneous first uploads can both pass — accepted, it is a load guard, not a business rule.

**Race notes:** two uploads of the same file under *different* keys serialize on the student row locks; the second sees the
first's records and rejects them as duplicates (D6). A single `POST` racing a bulk upload is not serialized (single creates
take no lock and allow duplicates today) — parity, documented. A transfer approval racing the upload waits on (or is waited
on by) the same student lock, so the portfolio check always sees the committed `school_id`.

## 8. Security

| Concern | Control |
|---|---|
| AuthN / session | unchanged `get_current_user`; no new tokens |
| CSRF | `samesite=lax` session cookie not sent on cross-site POST; custom `Idempotency-Key` header forces CORS preflight, allowed only for `settings.frontend_url` |
| AuthZ / role escalation | role first; actor from session; CSV can't set school, owner, status, verifier, publisher; Results always Draft so DEC-ROLE-007 still needs a different verifier/publisher |
| IDOR | per-row portfolio check on the locked student; batch read owner-only with 404; keys scoped per user |
| Tier bypass | same denial rules as `require_school_entitlement`, per school |
| Input validation | server-side per cell (§6); strict UTF-8, NUL refused, size/row caps; extension/MIME not trusted |
| SQL injection | ORM only; codes bound in an `IN` list |
| XSS | React escaping; errors rendered as text; `report_url` http(s)-only server-side (+ existing safe-href guard in `Student360Panels.tsx`) |
| CSV injection | template cells sanitized (§5.2) |
| DoS | 1 MB / 500 rows / 20 per hour; bounded read |
| Logs | ids and counts only — never cell values, marks, names, codes or keys |
| Audit | `school.bulk_upload` per batch + unchanged per-record actions with `bulk_batch_id` + `TIER_DENIED`; `school.bulk_upload_throttled` on 429 is **not** added (log line only) |

Operational logs: `bulk_upload_completed` (batch_id, target_type, actor_id, total, accepted, rejected, duration_ms),
`bulk_upload_replayed`, `bulk_upload_rejected_file` (reason token), `bulk_upload_throttled`, `bulk_upload_lock_timeout`,
`bulk_upload_notify_failed` (batch_id, record_id).

## 9. Frontend

**One new client component `components/SchoolBulkEntryPanel.tsx`** (< 200 lines) + column definitions in
`lib/bulkEntry.ts`. Props: `{ target: BulkTarget; hasStudents: boolean }`, where `BulkTarget` holds the title, record noun,
template URL, upload URL and column reference. Reuses existing classes (`card`, `action-card`, `form`, `field`, `btn`,
`btn secondary`, `form-error`, `table-wrap`, `table`, `muted`, `field-help`), `detailMessage` behaviour and `friendlyMessage`
from `lib/schoolStudents.ts`. `SchoolBulkUploadPanel` (roster) is **not** modified.

Mounting (inside a native `<details>` per module, collapsed by default, so the dashboards don't grow; keyboard and screen
reader support come with the element):
- Academic Team dashboard: "Bulk entry — results" after `SchoolAcademicResultsPanel`; "Bulk entry — test prep" and
  "Bulk entry — language" after `SchoolTestPrepLanguagePanel`.
- Psychometric Team dashboard: "Bulk entry — assessments" after `SchoolPsychometricRecordsPanel`.

States:
- **Empty** (`hasStudents=false`): "No students in your portfolio yet. Bulk entry becomes available once a school is assigned
  to you." — no form.
- **Ready:** step 1 "Download the pre-filled template" (`btn secondary`, a real `<a download>` link, not `window.open`);
  "Column reference" table; step 2 labelled file input (`accept=".csv,text/csv"`) + submit.
- **Loading:** submit and file input disabled, button text "Uploading…", form `aria-busy="true"`, polite `role="status"`.
- **Request error** (`role="alert"`): API `detail` via `friendlyMessage`; 413/422/409/429 messages as sent (429 adds the wait);
  network failure → "The connection dropped. Upload again — the same file won't be added twice." The idempotency key is
  generated when a file is chosen and **kept across retries of that file**; a new file or a success resets it.
- **Result:** heading "Upload result" receives focus (`tabIndex={-1}`); summary "N of M rows added, K rejected. Rows that
  succeeded are kept." (text, not colour); table Row · Student ID · Result ("Added"/"Rejected") · Detail; rejected rows first
  when any exist; `router.refresh()` so the lists above update.
- **Responsive:** existing `.table-wrap` horizontal scroll; form fields stack; tested at 320/768/1024/1440.

## 10. Acceptance criteria

| ID | Criterion |
|---|---|
| AC1 | Each of the four modules accepts a CSV upload and creates one record per valid filled-in row, identical to the module's single create (Results as Draft with history row; Psychometric status by `report_url`; Test Prep/Language defaults). |
| AC2 | A repeated `Idempotency-Key` with the same file by the same user for the same module returns 201 with the original report and creates nothing; with a different file returns 422; concurrent duplicates never double-create. |
| AC3 | A row failing any rule (§6) is rejected with a specific message and never blocks other rows; `accepted + rejected = total`. |
| AC4 | A row naming a student outside the uploader's portfolio is rejected for that row only; the batch report never reveals data about that student. |
| AC5 | A row for a school whose tier lacks the service is rejected for that row only, with one `TIER_DENIED` audit per school/service per batch; Results are not tier-gated. |
| AC6 | Duplicates (existing record or earlier row) are rejected per §6 natural keys. |
| AC7 | Batch and row audit trail stored (§4); `GET /bulk-uploads/{id}` returns it to the uploader only (404 otherwise). |
| AC8 | Whole-file errors (§5.1 #2–#10) write nothing. |
| AC9 | Parents of accepted Psychometric/Test Prep/Language rows get the single-create notice after commit; a send failure keeps the records; Results upload notifies nobody. |
| AC10 | Bulk Results can't be verified/published by their uploader (DEC-ROLE-007 unchanged). |
| AC11 | Templates are role-gated, pre-filled with portfolio students only, formula-safe, `no-store`. |
| AC12 | UI: empty, loading, error (incl. retry with same key), result states; keyboard and screen-reader operable; usable at 320 px. |
| AC13 | Migration 0049 is the single head, create-table only, matches the model. |
| AC14 | Every existing single-record endpoint, the roster upload, and their tests are unchanged and green. |

## 11. Tests (written before code — TDD)

Backend (`apps/api/tests/`):
- `test_enh_028_migration.py` — AC13.
- `test_enh_028_bulk_core.py` — key format, replay, different-file 422, concurrent same-key (two sessions: one wins, other
  replays), size/encoding/header/row-count 4xx write nothing, throttle 429 + `Retry-After`, batch GET owner-only 404, report
  arithmetic, operational log fields contain no values.
- `test_enh_028_bulk_results.py` — AC1/3/4/6/10 for Results, incl. marks > max, overflow bounds, duplicate in file and in DB,
  outside-portfolio, unknown code, blank template rows skipped, no notification.
- `test_enh_028_bulk_psychometric.py` — AC1/3/5/9: ENH-027 fields, list/date parsing, `report_url` scheme, completed vs
  assigned notice, tier denial row + single audit, notify failure keeps records.
- `test_enh_028_bulk_test_prep_language.py` — AC1/3/5/6/9 for both.
- `test_enh_028_templates.py` — AC11 (roles, portfolio-only rows, formula sanitizing, headers).
- Regression: `test_sch_002`, `test_sch_005`, `test_sch_006`, `test_sch_009`, `test_sch_011_entitlements`, `test_enh_002`,
  `test_enh_022_*`, `test_enh_023_*`, `test_enh_027_*`, `test_sec_001_audit_trail`, `test_enh_005_*` (transfer interplay).

Frontend:
- `tests/components/SchoolBulkEntryPanel.test.tsx` (Vitest) — empty state; loading disables; result focus + rejected-first;
  error alert; retry reuses key, new file resets it; column reference.
- `tests/e2e/enh-028-bulk-entry.spec.ts` (Playwright) — Academic Team uploads results CSV (one bad row) → report → Draft rows
  visible; Psychometric Team upload; template download contains only portfolio students. Browser validation at 320/1440.

## 12. Proposed decision record (to add as `DEC-SCOPE-042` on approval)

"ENH-028 bulk data entry for Results/Psychometric/Test Prep/Language: create-only CSV, `student_code` key, same parent
notices after commit, 1 MB/500 rows, bulk-only duplicate rejection, generalized batch/row tables, user-scoped idempotency
keys, 20 uploads/user/hour." Status `CONFIRMED_CURRENT` only with the user's approval of this spec.

## 13. Regression risks and mitigations

| Risk | Mitigation |
|---|---|
| `require_school_entitlement` commits on deny | never called in the loop; pure `_entitlement_denial` + cached per school |
| Notification flood / SMTP latency inside the transaction | post-commit per record, failures isolated |
| Draft counts change transfer behaviour (`school_transfers.py:432,588`) | same records a single create would make; covered by running `test_enh_005_*` |
| Lock contention with promotions/transfers/edits | short transaction, 5 s timeout → 409, id-ordered locks |
| `schools.py` import cycles | `school_bulk.py` imports from `schools.py` only (one direction), like `school_analytics.py` |
| Route shadowing | static segments before dynamic; tests hit every new path |
| Roster upload regression | not modified; `test_sch_002` + `sch-002` e2e in the regression set |
