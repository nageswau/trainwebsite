# ENH-026 Career Counselling Record + ENH-021 Internship Management — Design

**Status:** design approved section-by-section in-session 2026-09-27 (`EXPLICIT_APPROVAL`, user); decisions recorded as
`DEC-SCOPE-031` (ENH-026) and `DEC-SCOPE-032` (ENH-021) in `docs/decisions/PRODUCT_DECISION_REGISTER.md`.
One spec, two independent parts (user choice "A"): Part 1 ENH-026, Part 2 ENH-021. Each part has its own migration
and can be committed and verified on its own; they share only the aggregation code in `schools.py`/`student_360.py`.

## 1. Problem

- **ENH-026.** `School CRM.md §7` (`docs/sources/School CRM.md:302-344`, `ORIGINAL_REQUIREMENT`) specifies a 17-field
  Counselling Record and the lifecycle **Not Started → Scheduled → Completed → Follow-up Required → Completed**.
  `SchoolCareerRecord` (`apps/api/app/models.py:1257`) stores only student, counsellor, `record_type` and one free-text
  `notes`; there is no status, no dates beyond `created_at`, and no update endpoint
  (`apps/api/app/api/schools.py:1892-1940`).
- **ENH-021.** `School CRM.md §22` (`:715-741`) lists Student, Internship company, Role, Start/End date, Mentor,
  Attendance, Completion, Certificate, Feedback, Skills acquired; `§1` has an "Internships" dashboard KPI and `§35` an
  "Internship: Not started" status. Today internships exist only as a basic ENH-012 portfolio section
  (`PortfolioEntry`, `models.py:1133`: title/organization/dates), the KPI and chart are hard-coded "untracked"
  (`schools.py:86-94, 487`), and the Platinum `internships` service is never enforced or counted.

## 2. Goals and non-goals

**Goals:** every §7 and §22 field recorded in a structured, queryable form; the §7 lifecycle enforced; internships
tracked to completion with a certificate; dashboard KPI/chart, entitlement usage and Student 360° reflect real data;
existing data, API contracts and behaviour preserved.

**Non-goals:** timeline events for status changes or internships (the timeline only derives events from rows' own
timestamps); rendering the KPI board in the web UI (it is API-only today — `SchoolReportsPanel` does not render
`school_crm_kpis`); §28 scorecard and §30 Internship Report (ENH-015/ENH-016); ENH-019 calendar feed; ENH-027
(psychometric) — it will reuse this spec's recommendation-list shape; the `digital_portfolios_created` KPI.

## 3. Decisions confirmed in-session (2026-09-27)

### 3.1 ENH-026 (`DEC-SCOPE-031`)

| ID | Decision |
|---|---|
| C1 | §7 "Counselling type" is the existing `record_type`. Status + structured fields apply to `guidance_session` and `counselling_note`; `recommendation` stays notes-only (status/structured fields rejected). |
| C2 | Lifecycle: create → `not_started` \| `scheduled` \| `completed`; `not_started → scheduled`; `scheduled → completed`; `completed → follow_up_required`; `follow_up_required → scheduled` \| `completed`. No skipping; anything else 422; re-sending the current status is a no-op. |
| C3 | Status omitted on create of a `guidance_session`/`counselling_note` ⇒ `completed`, `completed_on` = today (Asia/Kolkata). Keeps legacy callers and KPIs unchanged. A `recommendation` always has status NULL. |
| C4 | Legacy rows (status NULL) are never backfilled. They may move only to `completed` or `follow_up_required`; field-only edits keep status NULL. UI label: "No status (recorded before tracking)". |
| C5 | `counts_as_completed(r)` ⇔ status ∈ {`completed`, `follow_up_required`} or NULL. Used for both dashboard KPIs, the completion rows, overview status and `individual_counselling` usage. |
| C6 | Dates: `scheduled_for` (timestamptz) required on entering `scheduled`; `completed_on` (date) required on entering `completed`, defaulting to today IST; on a loop the columns are overwritten and every change is audited old → new. |
| C7 | `next_follow_up_date` required and ≥ today (IST) on entering `follow_up_required`; cleared when leaving that state. |
| C8 | Existing `notes` = §7 "Counsellor notes". Stays NOT NULL; empty string allowed at `not_started`/`scheduled`; must be non-empty at `completed`/`follow_up_required`. |
| C9 | Per-record snapshots: `career_interests` (list), `global_education_interest` (bool) — ENH-025 student fields are not touched. `academic_strengths`, `weak_areas`, `recommended_careers`, `recommended_courses`, `recommended_stream`, `recommended_skills`: JSON lists of short strings. `parent_participated` (bool) + `parent_participation_note`. |
| C10 | Grade is derived from the student at display time and shown **only to School roles** (DEC-SCOPE-028 keeps service roles to name + school). |
| C11 | Any `career_counselor` whose portfolio covers the student may update; `career_counselor_user_id` stays the creator; new `updated_by_user_id`. |
| C12 | Parents notified on creation (unchanged) and on **status change only**. |
| C13 | PATCH gated on `individual_counselling` with `grandfathered_since=record.created_at` (ENH-023 D8 pattern). |
| C14 | Overview: new status value `in_progress` (records exist, none counted); `recommended_careers` unchanged; new key `structured_recommendations`. |

### 3.2 ENH-021 (`DEC-SCOPE-032`)

| ID | Decision |
|---|---|
| I1 | Extend `PortfolioEntry` (`section='internship'`); no new table. `organization` = company (required for internship writes), `title` = role, `date_from`/`date_to` = start/end. |
| I2 | Writers = existing portfolio write roles (coordinator, assigned teacher, academic_team). Readers = existing portfolio readers. |
| I3 | New fields: `mentor_name`, `mentor_designation` (no contact data), `attendance_percent` 0–100, `completion_status` ∈ {`not_started`, `in_progress`, `completed`, `discontinued`}, `feedback` (text), `skills_acquired` (list). |
| I4 | Legacy internship entries keep new fields NULL ("No status"); they count toward the KPI but not as completed. `completed` requires `date_to`; a certificate only on `completed` entries; status cannot leave `completed` while a certificate is attached. |
| I5 | Certificate: PDF/JPEG/PNG detected from content, ≤ 5 MB, downloadable by every portfolio reader; replaced/removed/entry-deleted files are deleted after commit; generated download name. |
| I6 | Tier: Platinum `internships` for **creating** an internship entry, **setting any tracking field**, and **certificate upload/delete**. Editing only basic fields or deleting an internship entry keeps the Gold `digital_portfolio_creation` gate (grandfathered as today), so Gold schools keep control of existing entries. |
| I7 | KPI `internships` and `usage["internships"]` = distinct students with ≥ 1 internship entry, any status. Chart `internship_status` = entries per completion status, fixed order `not_started, in_progress, completed, discontinued, no_status`, zeros included. |
| I8 | Student-level status (§35) = best progress: `completed` if any completed, else `in_progress` if any in progress, else `not_started`; shown in the 360° `edusphere_programs` tab. |

## 4. Data model

### 4.1 Migration `0042_career_record_structured_fields` (down_revision `0041_student_master_fields`)

`school_career_records` — add, all nullable, no backfill:

| Column | Type |
|---|---|
| `status` | `String(30)`, `CHECK (status IS NULL OR status IN ('not_started','scheduled','completed','follow_up_required'))` name `ck_career_record_status` |
| `scheduled_for` | `DateTime(timezone=True)` |
| `completed_on`, `next_follow_up_date` | `Date` |
| `career_interests`, `academic_strengths`, `weak_areas`, `recommended_careers`, `recommended_courses`, `recommended_stream`, `recommended_skills` | `JSON` |
| `global_education_interest`, `parent_participated` | `Boolean` |
| `parent_participation_note` | `String(500)` |
| `updated_by_user_id` | `Uuid`, FK `users.id` |

Index `ix_school_career_records_student_type_status (school_student_id, record_type, status)`.
Downgrade drops exactly these. Rejected: Postgres ENUM (harder to evolve; house precedent is String + CHECK);
1:1 side table (extra join on 6+ read paths); status backfill (user rejected, C4).

### 4.2 Migration `0043_portfolio_internship_tracking` (down_revision `0042_…`)

`portfolio_entries` — add, all nullable:

| Column | Type |
|---|---|
| `mentor_name`, `mentor_designation` | `String(200)` |
| `attendance_percent` | `Integer`, `CHECK (attendance_percent IS NULL OR attendance_percent BETWEEN 0 AND 100)` |
| `completion_status` | `String(20)`, `CHECK (completion_status IS NULL OR completion_status IN ('not_started','in_progress','completed','discontinued'))` |
| `feedback` | `Text` |
| `skills_acquired` | `JSON` |
| `certificate_key` | `String(300)` (never returned by the API) |
| `certificate_content_type` | `String(50)` |

`CHECK ck_portfolio_internship_fields`: `section = 'internship' OR (all eight columns IS NULL)`. The existing
`ix_portfolio_entries_student_section` serves every new query. Downgrade drops these; certificate objects already in
storage become orphans and need manual cleanup (noted in the migration docstring). Rejected: `internship_details` side
table (user chose I1); storing the uploaded original filename (untrusted, may carry personal data).

Both migrations: before authoring, run `alembic heads` — if a parallel branch has taken `0042`/`0043`, renumber
(same later-branch-moves precedent as DEC-SCOPE-024/025/027/029/030).

## 5. API

### 5.1 ENH-026

**`POST /api/v1/school/career-counselor/records`** — existing; contract extended only.
Order unchanged: role (`career_counselor`, 403) → `school_student_id` present (422 "school_student_id is required") →
`_student_in_portfolio` → `require_school_entitlement(..., "individual_counselling")` → body validation. Body validated
with new `CareerRecordCreate` via `_master_fields_or_422` (string 422 detail, as today). The three existing messages
("school_student_id is required", "record_type must be one of guidance_session, counselling_note, recommendation",
"notes is required" — the last now only when the resulting status requires notes) stay verbatim. Status defaults per C3.
Structured fields/status on `recommendation` → 422. Response = existing keys + `status`, dates, structured fields,
`updated_by_user_id`.

**`PATCH /api/v1/school/career-counselor/records/{record_id}`** — new. Body `CareerRecordUpdate`
(`extra="forbid"`, presence-aware merge via `model_fields_set`; `record_type`, `school_student_id` not updatable).
One transaction:
1. role `career_counselor` else 403;
2. `SELECT … FOR UPDATE` the record (404 "Career record not found");
3. re-check the record's student is in the caller's portfolio **under the lock** (403, `_student_in_portfolio` wording);
4. `require_school_entitlement(..., "individual_counselling", grandfathered_since=record.created_at)`;
5. optional precondition `expected_status` (a status value or `null` for legacy rows): if sent and ≠ the locked status
   ⇒ **409** `"This record was changed by someone else (now <Current>). Reload to see the latest."` (ENH-023 D12
   `expected_tier` precedent; the web client always sends it, other clients that omit it behave as without it);
6. if `status` sent and ≠ locked status: validate transition (C2/C4) else **422**
   `"Cannot change status from <Current> to <Requested>"`;
7. merge fields; validate post-merge rules (C6–C8, list limits); if nothing actually changed, return 200 with the
   record and write nothing (no audit, no notification — repeat PATCHes are safe to retry);
8. set `updated_by_user_id`; `AuditLog` `school.career_record_update`, metadata `{changed_fields (names only),
   status: {old,new}, scheduled_for/completed_on/next_follow_up_date: {old,new} when changed}` — never field contents;
9. **commit** (releases the row lock);
10. if status changed: `_notify_student_parents` (title "<Status label> — career record for <name>") then commit again.
    Notification is deliberately **after** the record commit: `_notify_parent` sends email inline
    (`schools.py:662`), so doing it before would hold the row lock across SMTP latency and could email parents about a
    change whose commit then failed. A notification failure is logged (`career_record_notify_failed`, ids only) and does
    not undo the record change. `POST` keeps its existing notify-then-commit order (no lock is held there; unchanged
    behaviour).
Concurrency: concurrent PATCHes serialize on the row lock; the second validates against the committed status
(409 when `expected_status` is stale, 422 when the transition is simply not allowed). Field edits are last-write-wins,
every write audited (same stance as `update_career_goal`).

**List endpoints** (`GET /career-counselor/records`, `GET /career-records`) — existing keys + new fields.

**Validation constants** (`schemas.py`): `CAREER_STATUSES`, `CAREER_STATUS_NEXT` (C2 map, with `None` key for create
and a separate legacy set C4), lists ≤ 20 items × ≤ 100 chars, trimmed, `_no_control_characters`;
`parent_participation_note` ≤ 500 single-line. Dates checked against `today` in Asia/Kolkata (the existing `_today_ist`).

### 5.2 ENH-021

**`POST/PATCH/DELETE /api/v1/school/students/{sid}/portfolio/entries[/{eid}]`** — existing; contract extended only.
`PortfolioEntryCreate`/`Update` gain the I3 fields; accepted only when the (stored) section is `internship`, else 422.
Gate selection (I6), evaluated after role/scope and entry lookup:
- create with `section='internship'` → `internships`;
- PATCH on an internship entry that sets any I3 field → `internships`, `grandfathered_since=entry.created_at`;
- any other create/PATCH/DELETE → `digital_portfolio_creation` exactly as today.
PATCH and DELETE lock the entry (`FOR UPDATE`). Post-merge rules for internship: `organization` non-empty,
`completed` ⇒ `date_to`, status ≠ `completed` while `certificate_key` set ⇒ 422 "Remove the certificate first".
DELETE of an entry with a certificate deletes the object after commit (failures logged with a key digest).
`PortfolioEntryOut` adds the I3 fields + `has_certificate: bool`.

**New module `apps/api/app/api/portfolio_certificates.py`** (router mounted like `school_student_profile.py`):
- `PUT /school/students/{sid}/portfolio/entries/{eid}/certificate` (multipart `file`): `_load_student_for_reader` +
  `_require_portfolio_write` → lock entry → 404 unless `section='internship'` → 422 unless `completion_status='completed'`
  → `require_school_entitlement(..., "internships", grandfathered_since=entry.created_at)` → read ≤ 5 MB + 1
  (empty 422, oversize 413) → `%PDF-` prefix ⇒ `application/pdf` unchanged; else `detect_image_type` +
  `strip_metadata` for JPEG/PNG; else 415 → `storage.write_bytes("portfolio-certificates/<uuid4hex>")` → set columns,
  audit `school.internship_certificate_set` → commit (on failure discard new object) → discard old object.
- `GET …/certificate`: `_load_student_for_reader` (every portfolio reader, I2/I5) → 404 if none or object missing
  (warning log, key digest only) → add `AuditLog` `school.internship_certificate_download` (entry id, student id, reader
  role; S13) and commit **before** returning the bytes, so no document leaves without its audit row (a failed audit
  commit ⇒ 500, nothing served) → bytes with `Content-Disposition: attachment; filename="internship-certificate.<pdf|jpg|png>"`,
  `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; sandbox`, `Cache-Control: private, no-store`.
- `DELETE …/certificate`: write role/scope → lock → gate as PUT → clear, audit `school.internship_certificate_remove`
  → commit → discard object. 204 also when none attached.
Concurrent uploads serialize on the entry lock; each commit discards its predecessor, so no orphan objects.

### 5.3 Aggregates (`schools.py`, `student_360.py`)

| Location | Change |
|---|---|
| `_school_dashboard_payload` (`schools.py:353`) | `guidance_students`/`counselling_students` filtered by `counts_as_completed`; KPI `internships` tracked (I7); `internship_status` key added; `internships` removed from both `UNTRACKED_*` constants |
| `school_entitlements` (`schools.py:1020`) | `individual_counselling` usage uses `counts_as_completed`; `internships` usage per I7 |
| `_overview_payload` (`schools.py:1153`) | statuses per C5/C14; `_career()` items gain new fields (grade never added — School roles already get it from `student`); `structured_recommendations` added |
| `portfolio_payload` (`portfolio.py:91`) | `career_guidance` items gain `status` |
| `build_360` (`student_360.py:52`) | `edusphere_programs` gains `{"key": "internship", "status": internship_progress(entries["internship"])}` |

Shared helpers in `schools.py`: `counts_as_completed(record)` and `internship_progress(entries)` — one definition each.

## 6. Security

- Authorization reuses existing scope functions only: `_student_in_portfolio`, `_portfolio_school_ids`,
  `_load_student_for_reader`, `_can_edit_portfolio`, `_readable_students`. No new role grants.
- Transfer race: career PATCH re-checks scope under the row lock (as `update_career_goal`).
- DEC-SCOPE-028 boundary: no counsellor-facing payload gains grade or other student master fields (C10).
- Uploads: content-sniffed type allowlist, size cap before full read, metadata stripped from images, storage key never
  exposed, download served as attachment with nosniff + sandbox CSP.
- Every write audited; tier denials audited by the existing helper.
- Input: `extra="forbid"`, control/bidi characters rejected, lengths capped.

## 7. Frontend

- `SchoolCareerRecordsPanel.tsx`: form extracted to new `CareerRecordForm.tsx` (create + edit), status select limited
  to allowed next states from `lib/careerRecords.ts` (`CAREER_STATUS_NEXT`, labels), date input per status, §7 fields
  (lists via ENH-025 `splitList`); `recommendation` stays notes-only. Table gains Status, Next follow-up, Edit.
  New `app/school/career-counselor/dashboard/loading.tsx`.
- `SchoolChildOverview.tsx`: status chip, dates, structured fields when present, grade (School roles), "Structured
  recommendations" list next to the existing list.
- `Student360Panels.tsx`: career tab status + structured fields; `PROGRAMME.internship = "Internship"`; activities tab
  internship entries show status.
- `PortfolioEntryForm.tsx`: internship ⇒ "Company" required + new `InternshipFields.tsx`.
  New `InternshipCertificate.tsx` (modelled on `SchoolStudentPhoto.tsx`): shown on editable completed internship
  entries; accept `.pdf,.jpg,.jpeg,.png`; client-side 5 MB pre-check; busy state; 413/415/422/403 messages.
- `PortfolioPanel.tsx`: internship entries show status chip, mentor, attendance, "Download certificate (PDF|image)".
- States: loading (route `loading.tsx`), empty (existing muted messages, "No status" label, absent fields omitted),
  error (`FormMessage` with API text incl. tier 403), forbidden (`accessUnavailable`). Status conveyed as text; all
  inputs labelled; Edit buttons' accessible names include the student name.
- Types: optional additions only in `lib/portfolio.ts`, the counsellor page's `Record_`, overview types.

## 8. Acceptance criteria

ENH-026: **AC26-1** create with all §7 fields and any allowed initial status; read back complete. **AC26-2** only C2
transitions succeed; skips/others 422. **AC26-3** C6–C8 rules enforced. **AC26-4** legacy rows unchanged, only
→ completed/follow_up_required, field edits keep NULL. **AC26-5** legacy 3-field POST behaves as today (status
completed, response has all old keys); recommendation rejects structured fields. **AC26-6** KPIs, overview status and
usage follow C5. **AC26-7** 403 for other roles/outside portfolio; tier denial below Silver; transfer race blocked.
**AC26-8** parents notified only on status change; every PATCH audited old → new. **AC26-9** no grade in
counsellor-facing payloads.

ENH-021: **AC21-1** internship with all §22 fields created, tracked to completed, certificate attached and downloaded
by each reader role. **AC21-2** company required, completed ⇒ end date, attendance range, tracking fields rejected on
other sections (API 422 and DB CHECK). **AC21-3** certificate type/size/state rules (415/413/422), replace/remove/
entry-delete remove the old object after commit. **AC21-4** Platinum required for create/tracking/certificate; a Gold
school can still edit basic fields of and delete its existing internship entries. **AC21-5** KPI, chart, usage and 360°
status match I7/I8. **AC21-6** teacher not assigned to the student ⇒ 403. **AC21-7** legacy internship entries read
unchanged with "No status". **AC21-8** every successful certificate download writes one
`school.internship_certificate_download` audit row; a denied or 404 download writes none.

Review-derived (§11): **AC-R1** career PATCH with a stale `expected_status` ⇒ 409 and nothing written. **AC-R2** a
parent-notification failure after a status change leaves the record change committed. **AC-R3** attempts to set
owner ids, `record_type`, `section` or `certificate_key` through JSON ⇒ 422. **AC-R4** no API response or log line
contains `certificate_key`, notes, strengths, weak areas, feedback or mentor names (log assertions in tests).
**AC-R5** keyboard-only completion of the counselling and internship forms, with focus returned to the Edit button
after save/cancel (component test + E2E).

## 9. Tests (written before code, per task)

- Backend (pytest, real Postgres): `test_enh_026_counselling_record.py`, `test_enh_021_internship.py`,
  `test_enh_021_certificate.py`, plus migration up/down checks on seeded rows for 0042/0043; concurrency tests for the
  career-record transition race and simultaneous certificate uploads.
- Changed because the requirement changed (not to make a test pass): `test_sch_reports.py:302-305`,
  `test_sch_011_entitlements.py:137` (internships now tracked). **All other existing tests must pass unmodified.**
- Web (vitest): `CareerRecordForm`, `InternshipFields`, `InternshipCertificate`; additions to
  `SchoolCareerRecordsPanel`, `Student360Panels`, `PortfolioPanel` tests (loading/empty/error/forbidden).
- E2E (Playwright): `enh-026-counselling-record.spec.ts`, `enh-021-internship.spec.ts`.
- Full backend + E2E regression once at the end.

## 10. Regression risks

| Risk | Mitigation |
|---|---|
| KPI / status semantics change | C4/C5 keep legacy rows counted; existing `test_sch_reports`, `test_sch_007`, `test_sch_011` (except the untracked-internships assertion) pass unmodified |
| Response contract drift | additive fields only; existing tests pin old keys; new test for the 3-field POST |
| Gold schools locked out of existing internship entries | I6 split; AC21-4 test |
| Orphaned storage objects | commit-then-discard ordering; tests with storage failure |
| Migration head collision with parallel branches | `alembic heads` check before each migration task |
| Service roles seeing student master data | AC26-9 |
| ENH-005 transfer / ENH-004 promotion | untouched; `test_enh_005_approve.py` must pass unmodified |
| Parent emailed about a change that did not commit / lock held across SMTP | notify after commit (§5.1 step 10); test that a failing mailer leaves the record change committed |

## 11. Engineering reviews (2026-09-27)

Applied on the user's instruction: `api-and-interface-design` (backend), `frontend-ui-engineering` (web),
`security-and-hardening` (both features). Only ENH-021/ENH-026 surfaces are affected; nothing speculative.

### 11.1 API and interface design

| # | Finding | Resolution (compatible with existing architecture) |
|---|---|---|
| A1 | Error shape differs by endpoint family (Hyrum's law) | Career-record endpoints keep **string** `detail` (via `_master_fields_or_422`). Portfolio endpoints keep their current shapes: schema errors as FastAPI's list shape, post-merge rule errors as `HTTPException(422, "<text>")` exactly as `update_portfolio_entry` does today. No endpoint changes shape. |
| A2 | Stale view vs invalid request were both 422 | Optional `expected_status` precondition ⇒ 409 (§5.1 step 5); invalid transitions stay 422 (C2). |
| A3 | Several hand-built dicts for the same record | One serializer per resource: `_career_record_out(r)` used by POST, PATCH, both lists and `_overview_payload._career`; career routes keep returning the dict (no `response_model`, so timestamps serialize exactly as today) and validate against a documented `CareerRecordOut` like `student_360_view` does. Portfolio: `_entry_out` and `PortfolioEntryOut` stay aligned; `has_certificate` is a read-only ORM `@property` on `PortfolioEntry`; a test asserts both serializers expose the same keys and never `certificate_key`. |
| A4 | Two representations of "empty list" | `[]`, `null` and lists of blank strings are all stored as NULL and returned as `null`; items trimmed, blanks dropped, order kept. |
| A5 | Ambiguous datetime input | `scheduled_for` must be timezone-aware ISO 8601; a naive value ⇒ 422. Dates compared in Asia/Kolkata (`_today_ist`). |
| A6 | Retry safety | PATCH is idempotent (no-op writes nothing). Certificate PUT replaces; certificate DELETE returns 204 when absent. POST create stays non-idempotent (existing contract); the web client's `inFlight` guard prevents double submit. |
| A7 | HTTP semantics of new routes | PATCH 200 full record; certificate PUT 200 `{"has_certificate": true, "content_type": …}` (mirrors photo PUT); GET 200 bytes / 404; DELETE 204; 413/415/422 for upload faults; 409 only for `expected_status`. |
| A8 | List pagination | The two career-record lists are unpaginated today; changing that is a contract change outside this requirement — left as is, noted. |
| A9 | Database usage | KPI/chart/usage internship queries select only `school_student_id`/`completion_status` for `section='internship'` over the school's student ids; usage uses `COUNT(DISTINCT …)` in SQL; 360° reuses entries `portfolio_payload` already loaded (no extra query, no N+1). |
| A10 | Mass assignment | `extra="forbid"` on every new/extended body; `record_type`, `school_student_id`, `career_counselor_user_id`, `updated_by_user_id`, `section`, `certificate_*` are never writable through JSON. |

### 11.2 Frontend UI engineering (existing design language only)

| # | Area | Resolution |
|---|---|---|
| F1 | Forms / hierarchy | Reuse `fieldset.form-section` + `legend` to group the §7 form: *Session* (type, status, dates, next follow-up), *Assessment* (interests, global-education interest, strengths, weak areas), *Recommendations* (four lists), *Parent participation*, *Counsellor notes*. Internship fields grouped the same way (*Placement*, *Progress*, *Outcome*). `form-grid` gives two columns that collapse to one at 640 px; `form-busy-wrap` disables every field while saving; `aria-invalid` + `field-help` for field-level hints; `inFlight` ref guard as in `PortfolioEntryForm`. |
| F2 | Edit flow / keyboard | Inline edit in the existing action card (the `PortfolioPanel` `startEdit` pattern, no modal). Opening moves focus to the form heading; Cancel/Escape or a successful save return focus to the row's Edit button. Only native `button`/`input`/`select`/`textarea`; tab order follows visual order. |
| F3 | Status control | Select lists the current status plus allowed next states only (from `lib/careerRecords.ts`), with `field-help` describing the lifecycle; status always shown as text in the existing `.status` chip (never colour alone). |
| F4 | Responsive / mobile | Records table stays in `.table-wrap` (horizontal scroll, existing `min-width:650px`); detail views reuse `.student-profile dl`, which already collapses to one column at 640 px; the certificate control stacks under the entry. Checked at 320/768/1024/1440 px in E2E screenshots. |
| F5 | Loading | New `career-counselor/dashboard/loading.tsx` using the existing `skeleton-line` + `aria-busy` pattern (`career-counselor/skills/loading.tsx`); portfolio and 360° routes already have loading states. Upload shows "Uploading…" with `aria-live="polite"` (photo pattern). |
| F6 | Empty | Existing empty messages kept; structured sections render only when they have content; legacy records/entries show "No status (recorded before tracking)" / "No status". |
| F7 | Errors | `FormMessage` (`role="alert"`) shows the API text for 422/403/404; 409 shows the stale message plus a **Reload** button (`router.refresh()`); network failure uses the existing `NOT_COMPLETED` text and keeps the user's input. Certificate removal uses the existing two-step "Remove → Confirm remove" pattern. |
| F8 | Perceived performance | Server components + `router.refresh()` as today; no optimistic status updates (transitions are server-validated and can be refused). Client-side 5 MB and type pre-check avoids a wasted upload. |
| F9 | Component size | Keep each file under ~200 lines: `CareerRecordForm`, `InternshipFields`, `InternshipCertificate`; `lib/careerRecords.ts` holds labels and the transition map (one source for form and display). |
| F10 | Copy / accessibility | Every input labelled; Edit buttons named "Edit record for <student>"; certificate link "Download certificate (PDF)" / "(image)"; list inputs explain "Separate items with commas". |

### 11.3 Security and hardening

Threat model: trust boundaries are JSON bodies, the multipart upload, and path ids; assets are counselling data about
minors (sensitive), internship certificates and mentor names (personal data of students and third parties).

| # | Check | Resolution |
|---|---|---|
| S1 | Authentication | All routes use the existing cookie session via `get_current_user`; no new auth flow, no token changes. |
| S2 | Authorization / IDOR | Career PATCH: record → its student → caller's portfolio, re-checked under the row lock. Portfolio/certificate routes: `_load_student_for_reader` then `_load_portfolio_entry`, which requires the entry to belong to the path's student (blocks cross-student ids). Tests: other school's counsellor, other school's record id, entry id under another student, unassigned teacher, parent of another child, service role on a school outside its portfolio. |
| S3 | Role escalation | No new grants; `extra="forbid"` (A10); tests that attempt to set owner ids, `record_type`, `section`, `certificate_key`. |
| S4 | Input validation | Enums, lengths, list limits, control/bidi characters rejected, dates range-checked, attendance 0–100 (API + DB CHECK), tracking fields only on internship (API + DB CHECK). |
| S5 | File upload | Type decided by content (`%PDF-` / JPEG / PNG), never by name or client `Content-Type`; SVG/HTML impossible; ≤ 5 MB read cap; image metadata stripped; server-generated key; storage root guard already in `storage._local_path`; `_discard` additionally refuses keys not under `portfolio-certificates/`. PDFs are stored unmodified (may contain active content) and are therefore only ever served as attachments. |
| S6 | XSS | React escaping only; no `dangerouslySetInnerHTML` exists in the web app and none is added; downloads served `attachment` + `nosniff` + `default-src 'none'; sandbox`; download filename generated. |
| S7 | CSRF | Session cookie is `httponly` + `SameSite=Lax` (`auth.py:88`) and CORS allows only `settings.frontend_url` with credentials (`main.py:52`); every state change is POST/PUT/PATCH/DELETE; no GET mutates state. No new mechanism needed. |
| S8 | SQL injection | SQLAlchemy ORM expressions only; no raw SQL; JSON lists bound as parameters. |
| S9 | Secrets / exposure | No new secrets or config. `certificate_key` never serialized or logged (key digest only, as ENH-025). |
| S10 | Sensitive logs & audit | Logs carry ids, counts and status names only — never notes, strengths, weak areas, feedback, mentor names or file names. Audit rows: create/update/delete of records and entries, certificate set/remove, tier denials (existing helper); metadata holds field **names** and status/date old→new only. |
| S11 | Rate limiting | The API has no general limiter today. Upload abuse is bounded (authenticated write roles only, 5 MB, one object per entry, old object deleted on replace). **Accepted risk — user confirmed 2026-09-27**, consistent with DEC-SCOPE-030 D15; request-body limits belong at the reverse proxy (infrastructure, out of scope). |
| S12 | Privacy | Counselling fields about minors are visible only through existing read scopes (the same readers who see `notes` today); no scope widened; grade withheld from service roles (C10). Retention follows the student record; a certificate is deleted with its entry or on replacement. Mentor contact data deliberately not collected (I3). |
| S13 | Certificate download audit | **User confirmed 2026-09-27: audit downloads.** Each successful download writes `school.internship_certificate_download` (metadata: entry id, student id, reader role — no file content or key). This is new relative to the student-photo GET, deliberately, because the certificate is a document about a minor readable by several roles. |
