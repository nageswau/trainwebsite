# ENH-025 — Student Master: mandatory full field coverage — Design

**Status:** Design approved in-session, 2026-09-23, section by section (data model, backend/API,
frontend, tests). Superpowers architectural path: brainstorming → this design doc → `writing-plans`
next. Written spec awaiting user review.

**Source requirement:** `School CRM.md §3` Student Master (`docs/sources/School CRM.md:118-177`,
byte-identical to `functionalities/edusphere_markdown/School CRM.md`; `EVID-014`, `DERIVED_BLUEPRINT`).
**Backlog item:** `docs/delivery/ENHANCEMENT_BACKLOG.md:2220-2330` (`ENH-025`).
**Decision record:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` → `DEC-SCOPE-029` (to be added by
the implementation plan's first task; records the in-session answers in §9 below as
`EXPLICIT_APPROVAL`, user, 2026-09-23). If another branch claims `DEC-SCOPE-029` first, renumber on
merge (precedent: `DEC-SCOPE-024`/`025`).
**Branch:** `feature/enh-025-student-master-field-coverage`.

## 1. Scope

The backlog's field-by-field audit of `SchoolStudent` against §3's 26 fields stands, with one
correction: the backlog describes `SchoolStudent` as pre-ENH-001. **`grade_level` (integer, 1-12)
already exists** (`ENH-001`, migration `0030`, `models.py:1031`) and is the "Grade" half of the
Grade/Section split. The split therefore reduces to adding `section`.

**In scope — 10 new value fields + Photo (Grade reuses the existing `grade_level`):**

| §3 field | Delivered as |
|---|---|
| Photo | `photo_key`/`photo_content_type` (internal) + authorized photo endpoints; API exposes `has_photo` |
| Gender | `gender` (fixed list) |
| Grade | existing `grade_level` (ENH-001) — unchanged |
| Section | `section` (new, backfilled) |
| Roll Number | `roll_number` (new, unique within school+year+grade+section) |
| Student Mobile | `student_mobile` |
| City | `city` |
| Subjects | `subjects` (JSON list) |
| Career interests | `career_interests` (JSON list) |
| Global education interest | `global_education_interest` (nullable boolean) |
| Preferred countries | `preferred_countries` (JSON list) |
| Preferred courses | `preferred_courses` (JSON list) |

"All 12 additive fields" in the acceptance criterion = the 10 value fields + Photo + the Grade/Section
split (satisfied by existing `grade_level` + new `section`).

**Explicit exception (user-approved):** Photo is settable via single-student edit only, **not** bulk
upload — a CSV cannot carry an image. Documented in the template column reference, `API_CONTRACT.md`
§12A, and `RTM.md`. A bulk photo import (e.g. ZIP keyed by `student_code`) would be a separate item.

**Out of scope (unchanged, owned elsewhere or deliberately absent):** Student ID, Name, DOB, School
(covered); Parent Name/Contact/Email (relational via `SchoolParentLink`); Academic performance
(`SCH-006`); Academic Year (`ENH-001`); Skills (`ENH-011`/`013`); Extracurricular, Achievements
(`ENH-013`); Certifications (`ENH-012`/`013`/`024`); Student Email (`DEC-ROLE-004` — school students
have no login identity).

**`grade_or_class` is kept unchanged** (user decision): it remains the free-text display label that
ENH-004 promotion rewrites and the grade-history ledger stores. `grade_level` + `section` are the
independently queryable pair. The two can drift if edited separately; the forms present them together
and neither is derived from the other.

## 2. Data model

### 2.1 `SchoolStudent` — new columns (all nullable; existing rows stay valid)

| Column | Type | Rules |
|---|---|---|
| `section` | `String(20)` | trimmed; display keeps typed case |
| `roll_number` | `String(20)` | trimmed |
| `gender` | `String(20)`, `CHECK (gender IN ('female','male','other','prefer_not_to_say'))` | |
| `student_mobile` | `String(20)` | `^[0-9+\-() ]{7,20}$`, must contain ≥7 digits |
| `city` | `String(120)` | |
| `subjects`, `career_interests`, `preferred_countries`, `preferred_courses` | `JSON` (list of strings) | NULL = not recorded; ≤20 items; each item trimmed, 1-80 chars; case-insensitive de-dup keeping first spelling |
| `global_education_interest` | `Boolean` | NULL = not recorded |
| `photo_key` | `String(200)` | internal storage key, never serialized |
| `photo_content_type` | `String(40)` | `image/jpeg` or `image/png` |

All free-text values reject control characters and Unicode bidi overrides (same rule as
`PromotionItem.grade_or_class`, `schemas.py:523-531`). Empty string / empty list → stored NULL (one
"not recorded" representation).

### 2.2 Roll-number uniqueness

```sql
CREATE UNIQUE INDEX uq_school_students_roll ON school_students
  (school_id, academic_year_id, grade_level, lower(section), roll_number) NULLS NOT DISTINCT
  WHERE roll_number IS NOT NULL;
```

Postgres 16 (`docker-compose.yml:3`). `NULLS NOT DISTINCT`: a blank section (or grade/year) is its
own group — two students with no section in Grade 5 cannot share roll `12`. `lower(section)`: `A` and
`a` are the same section. Students with no roll number are never constrained. The index is the sole
arbiter of uniqueness (no read-then-check).

### 2.3 `SchoolStudentGradeHistory` — new columns (nullable)

`from_section String(20)`, `from_roll_number String(20)`, `to_section String(20)`. Written by
promotion in the same insert it already performs. Pre-existing history rows keep NULL and display
"-". Preserves the previous class details that clearing `roll_number` (§2.4) would otherwise lose.

### 2.4 Lifecycle side effects

- **ENH-004 promotion** (`schools.py:1341-1358`): both `promoted` **and** `held_back` move the student
  into the active academic year, so **both clear `roll_number`** (history records it first). `section`
  is carried over. `failed`/`skipped` rows are untouched. Clearing to NULL can never violate the
  index, so promotion's single transaction cannot fail on roll numbers.
- **ENH-005 transfer approval** (`school_transfers.py:443`): clears `section` and `roll_number` in the
  same statement that already clears `assigned_teacher_user_id`/`pending_parent_email`. Every other
  new field carries over.

### 2.5 Migration `0039_student_master_fields` (revises `0038_portfolio`)

1. Add columns (guarded "add if missing", same style as `0030`), including the grade-history columns
   and the gender CHECK constraint.
2. Backfill `section` from `grade_or_class` with one conservative pattern — a grade number, then an
   optional `-`, `/`, space, or the word "section", then 1-2 letters at the end of the label:
   `"10-A"`→`A`, `"Grade 8-A"`→`A`, `"Class 7 Section C"`→`C`, `"9B"`→`B`, `"Grade 5"`→NULL,
   `"Nursery"`→NULL. Unparseable rows are left NULL (never guessed) and their `student_code`s are
   printed, as `0030` does.
3. Create `uq_school_students_roll` (no roll numbers exist yet, so no conflict is possible).
4. `downgrade()` drops the index, the constraint and the columns. `grade_or_class` is never written.

**Numbering:** unmerged `ENH-013` plans `0039_student_career_goal`, also revising `0038`. Decided
2026-09-23 (`DEC-SCOPE-029` item 11): ENH-025 merges first and keeps `0039`; ENH-013 renames its file to
`0040` and re-chains onto `0039_student_master_fields` (precedent: commit `6c66f9a`, ENH-012). A test
asserts a single Alembic head.

## 3. Backend / API

### 3.1 Conventions preserved

snake_case fields; errors as FastAPI `{"detail": "<string>"}` via `HTTPException`; existing
403/404/409/422 meanings; every existing request key, response key and error message unchanged
(additive only). `GET /school/students` stays unpaginated (pre-existing; out of scope).

### 3.2 Validation — one boundary model

`StudentMasterFields` (Pydantic, `schemas.py`): all fields optional, `extra="forbid"`, implements
§2.1's rules. Handlers extract only the new keys from their existing raw `payload: dict` and validate
them with this model; existing keys keep their current hand-written handling so their behavior and
messages stay byte-identical. `model_fields_set` drives PATCH semantics (absent = unchanged, `null` =
clear). A `ValidationError` becomes `HTTPException(422, "<field> <reason>")` — one string, matching
existing handlers. One helper, `_apply_master_fields(student, fields)`, is used by create, update,
bulk upload and the counselor route.

`CareerPreferencesUpdate` is the 4-field subset (`career_interests`, `global_education_interest`,
`preferred_countries`, `preferred_courses`), also `extra="forbid"`.

### 3.3 Changed endpoints (additive)

| Endpoint | Change |
|---|---|
| `POST /school/students` (`schools.py:1155`) | accepts the 10 new optional value keys |
| `PATCH /school/students/{id}` (`:1208`) | same keys, PATCH semantics above |
| `_student_out` (`:584`) → list, detail, overview, create, update | adds the 10 value fields + `has_photo: bool`; never `photo_key`/`photo_content_type` |
| `GET /school/students/roster-template` (`:899`) | new columns **appended after** the existing 7 (existing positions unchanged): `section, roll_number, gender, student_mobile, city, subjects, career_interests, global_education_interest, preferred_countries, preferred_courses`; example row updated |
| `POST /school/students/bulk-upload` (`:1467`) | parses new columns when present; absent column = not set. CSV list cells split on `;`; boolean accepts `yes/no/true/false/1/0` (case-insensitive) or blank |
| `GET /school/students/{id}/grade-history` (`:1124`) | `from`/`to` objects gain `section` (+ `from.roll_number`); additive |

### 3.4 New endpoints

| Endpoint | Role / scope | Behavior |
|---|---|---|
| `PUT /school/students/{id}/photo` (multipart `file`) | `school_coordinator`, own school | Replace semantics (idempotent). Type from magic bytes (JPEG `FF D8 FF`, PNG `89 50 4E 47 0D 0A 1A 0A`), not the client header → else 415. >2 MB → 413. Empty → 422. Returns `{"has_photo": true}` |
| `DELETE /school/students/{id}/photo` | `school_coordinator`, own school | 204, also when no photo exists |
| `GET /school/students/{id}/photo` | `_load_readable_student` (coordinator/principal own school, teacher assigned, parent linked) | streams bytes; `Content-Type` = stored type; `Cache-Control: private, no-store`; `X-Content-Type-Options: nosniff`; `Content-Disposition: inline`; 404 when none |
| `GET /school/students/{id}/career-preferences` | `career_counselor`, `_student_in_portfolio` | returns `{student_id, career_interests, global_education_interest, preferred_countries, preferred_courses}` |
| `PATCH /school/students/{id}/career-preferences` | same | body = `CareerPreferencesUpdate`; any other key → 422; returns same shape |

Static segments are registered before `/students/{student_id}` where they share a prefix (existing
note at `schools.py:899-904`).

### 3.5 Authorization

Unchanged for existing behavior. Coordinator: all writes, own school. Principal / Teacher (assigned
only) / Parent (linked only): read the new fields and the photo through existing scopes. Career
counselor: only the career-preferences route, own portfolio — no access to mobile, city, photo or
roll number (least privilege). All other roles: 403.

### 3.6 Transactions and concurrency

- **Create / update:** one transaction, as today. The flush that can violate `uq_school_students_roll`
  runs inside `begin_nested()`; an `IntegrityError` naming that constraint → 409 `"roll_number '<r>'
  is already used in this grade and section for this academic year"`; any other `IntegrityError` is
  re-raised (idiom: `portfolio.py:208-225`, `school_transfers.py:277-284`).
- **Bulk upload:** field validation happens before any write; each row's student insert + flush runs
  in its own savepoint. The parent link/invite (which can send an email) runs only after that
  savepoint succeeds, so a rolled-back row never produces an invite. A roll clash or validation
  failure rejects that row only (`SCH-002-AC04`). In-file duplicates are
  caught because earlier rows are flushed. The batch still commits once.
- **Photo:** student row loaded `with_for_update()`. New object written via `storage.write_bytes`
  under `school-student-photos/<uuid4 hex>` before commit; if the commit fails the new object is
  deleted. The previous object is deleted after commit, best-effort (failure logged; worst case an
  orphan file, never lost data). `StorageService` gains `read_bytes(key)` and `delete(key)` (local +
  S3).
- **PATCH:** last-write-wins, as today (no ETag contracted — not introduced).
- **Promotion / transfer:** new field changes ride in their existing single transactions.

### 3.7 Audit

`school.student_create`/`school.student_update` metadata gains `changed_fields` (names only). New
actions: `school.student_photo_set`, `school.student_photo_remove`,
`school.student_career_preferences_update`. Values are never logged (PII).

### 3.8 Error states

| Case | Response |
|---|---|
| invalid new field (create/update/counselor) | 422 string detail naming the field |
| unknown key on counselor route | 422 |
| roll-number clash | 409 |
| wrong role / out of scope | 403 (existing messages) |
| student or photo missing | 404 |
| photo wrong type / too big / empty | 415 / 413 / 422 |
| bulk row invalid | row `status: rejected`, `error_message` = same text; batch continues |

## 4. Frontend

Reuses existing classes (`.card`, `.action-card`, `.form`, `.field`, `.form-grid`, `.btn`, `.status`,
`.muted`, `.table-wrap`, `.form-error`, `.form-message`). One CSS addition: `fieldset.form-section`,
mirroring `fieldset.question`'s tokens. No new dependencies.

### 4.1 New modules

- `apps/web/lib/schoolStudents.ts` — shared `SchoolStudent` type (replaces three local copies),
  `GENDER_OPTIONS`, `toMasterPayload(form, mode)` (comma-split lists, trim, empty → `null`; create
  omits empties, edit sends `null`), `ROSTER_COLUMNS` (bulk column reference data).
- `apps/web/components/SchoolStudentFields.tsx` — the grouped fields, shared by create and edit.
- `apps/web/components/SchoolStudentPhoto.tsx` — photo display + coordinator controls.
- `apps/web/components/CareerPreferencesCard.tsx` — counselor card.

### 4.2 Roster forms (`SchoolStudentsPanel.tsx`)

- `<fieldset class="form-section">` groups with legends — *Identity* (name, DOB, gender), *Class
  placement* (grade label, grade level, section, roll number, teacher), *Contact* (student mobile,
  city, parent name/email), *Studies & interests* (subjects, career interests, global education
  interest, preferred countries, preferred courses). Each group uses `.form-grid` (1 column ≤640px).
- Gender and Global interest: `<select>` with "Not recorded". Mobile: `type="tel" inputMode="tel"`.
  List inputs: helper "Separate with commas" linked by `aria-describedby`.
- Edit form gains Date of birth (PATCH already supports it; the form omitted it).
- Busy: wrapping `<fieldset disabled>` (also blocks double submit), `aria-busy` on the form, button
  text "Saving…".
- Messages render inside the active form's card: failure `role="alert"`, success `role="status"`.
- Focus: Edit moves focus to the edit heading (`tabIndex={-1}`) and scrolls it into view; Save/Cancel
  return focus to that row's Edit button.
- Table adds "Section" and "Roll no." columns (inside `.table-wrap`). Empty state links to *Add one
  student* and *Bulk upload*.

### 4.3 Photo (`SchoolStudentPhoto.tsx`)

96×96 image, explicit width/height, `object-fit: cover`, `alt="Photo of {name}"`,
`src=/api/v1/school/students/{id}/photo?v=<n>`. No photo, or `onError` → initials placeholder with
text "No photo" (never an error message). Coordinator mode: file input (`accept="image/jpeg,image/png"`),
client pre-check type/size ≤2 MB with immediate message (server re-validates), Upload/Replace with busy
text, two-step "Remove photo → Confirm remove / Cancel" (ENH-012 delete-confirm pattern), `?v=` bump
after success.

### 4.4 Read views

- `SchoolStudentDetailPanel.tsx` (coordinator/principal/teacher pages): "Profile" `<dl>` — photo,
  gender, section, roll number, mobile, city, subjects, career fields; empty → muted "Not recorded".
  New prop `canEditPhoto` (default `false`; coordinator page passes `true`), same pattern as
  `showGradeHistory`.
- `SchoolChildOverview.tsx` (parent): photo, section, roll number in the child header.
- `SchoolGradeHistory.tsx`: shows previous section / roll number; "-" when absent.

### 4.5 Counselor (`CareerPreferencesCard.tsx` in `SchoolCareerRecordsPanel.tsx`)

Student `<select>` → loading "Loading…" (`aria-busy`) → 4-field form. Load failure → message +
**Retry** button. Save shows busy state and `role="status"`/`role="alert"` result. Existing "No
students in your portfolio yet" empty state is reused.

### 4.6 Bulk upload (`SchoolBulkUploadPanel.tsx`)

"Column reference" `<details>` table from `ROSTER_COLUMNS`: column, required/optional, format,
example — including the Photo exception note. Same table in `API_CONTRACT.md` §12A.

## 5. Security review

Reviewed with `security-and-hardening`, 2026-09-23. Scope: ENH-025 surfaces only; pre-existing issues
are listed in §10, not changed.

**Trust boundaries:** photo multipart upload; JSON bodies (create, update, counselor); bulk CSV;
`student_id` path parameter. **Assets:** personal data about **minors** (photo, gender, mobile, city,
interests) — treated as the *sensitive* class.

| Area | Existing control (verified) | ENH-025 design |
|---|---|---|
| Authentication | httpOnly cookie `edusphere_access` → `get_current_user` (`deps.py:14`) | Every new route depends on `get_current_user`; no public route |
| Authorization / IDOR | school match, teacher assigned-only, parent linked-only, counselor portfolio | Photo GET → `_load_readable_student`; photo PUT/DELETE → coordinator + `student.school_id == own`; counselor → `_student_in_portfolio`. Storage key is never client-supplied. Existing 403-vs-404 messages kept as-is (pre-existing behavior) |
| Role escalation / mass assignment | ENH-001 "system-assigned only" (`models.py:1028`) | `extra="forbid"` on `StudentMasterFields` and `CareerPreferencesUpdate` rejects `school_id`, `academic_year_id`, `photo_key`, `photo_content_type`, `student_code`, `created_by_user_id`; counselor cannot write any non-career field |
| Input validation | raw `dict` handlers | §2.1 rules at the boundary; list caps (≤20 × ≤80 chars) bound JSON size. Photo read is bounded: `await file.read(MAX_PHOTO_BYTES + 1)` — never an unbounded read. (The Next proxy buffers bodies, `app/api/[...path]/route.ts:9` — pre-existing, unchanged.) |
| XSS | React auto-escaping | No `dangerouslySetInnerHTML`. Only JPEG/PNG by magic bytes (no SVG); stored content type comes from detection, never the client. Photo response headers: `Content-Type` (detected), `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; sandbox`, `Content-Disposition: inline`, `Cache-Control: private, no-store` — an image/HTML polyglot cannot execute as a document |
| CSRF | `SameSite=Lax` cookies (`auth.py:88`); CORS allowlist = `frontend_url` with credentials (`main.py:32`) | Cross-site PUT/PATCH/DELETE/POST carry no cookie under Lax; the only new GET (photo) is side-effect free. No new CSRF mechanism (would be an app-wide change outside ENH-025) |
| SQL injection | SQLAlchemy ORM | ORM only; migration backfill uses `sa.text()` with bound parameters exclusively (no f-string SQL); index DDL is static; section parsing is Python regex |
| CSV / formula injection | no student CSV export exists | Not applicable now; see §10 |
| Token / session | unchanged | No new tokens; photo URL carries no credential (`?v=` is a cache-buster); `no-store` keeps minors' photos out of shared/proxy caches |
| Secret exposure | S3 credentials from env | No new secrets. `photo_key` is never serialized **or logged** (in local mode it is the only barrier, see residual risk). Storage exceptions → generic 500, never a key or path |
| Sensitive logs | request logs record path/method only (`core/middleware.py`) | Audit metadata = field names only. New 422 messages name the field and never echo the value (e.g. no mobile number in a response or a bulk `error_message`); exception: `roll_number` in the 409 (not personal data, and needed to resolve the clash) |
| Rate limiting | no global limiter; ENH-005 uses an audit-count throttle | None added (new infrastructure = speculative). Photo writes are coordinator-only, ≤2 MB, replace-semantics (one stored object per student) |
| Audit | `AuditLog` | `changed_fields` on create/update; `school.student_photo_set` / `_remove`; `school.student_career_preferences_update`; promotion roll clearing captured in grade history; transfer already audited |
| Privacy — photo metadata | none | **EXIF/metadata stripped before storage** (user decision): pure-Python function drops JPEG APP1–APP15 and COM segments and PNG `tEXt`/`iTXt`/`zTXt`/`eXIf`/`tIME` chunks; pixels are not decoded (no decompression-bomb surface); no new dependency. A malformed file that cannot be walked is rejected with 422 |
| Privacy — consent | STU-009 consent exists for other domains | **Resolved 2026-09-23 (user, `DEC-SCOPE-029` item 10):** the school, as data controller, obtains consent through its own enrolment process; Photo ships optional and school-entered with no EduSphere consent gate |

**Residual risk (local storage mode only):** photo objects live in the shared uploads volume that
`/local-files` also serves (`main.py:35`); reaching one requires guessing a 128-bit random key that is
never serialized or logged. A dedicated private volume is an infrastructure change blocked by
`DEC-INFRA-001`. S3 buckets are private.

**Abuse cases (each becomes a test first):** coordinator of school B reads/writes a school-A student's
photo or fields; teacher reads an unassigned student's photo; parent reads an unlinked child's photo;
counselor edits a student outside their portfolio, or sends `roll_number`/`school_id`; any role sends
`academic_year_id`/`photo_key`; upload of SVG, HTML renamed `.jpg`, a PNG with a JPEG content type, a
2 MB + 1 byte file, an empty file, a truncated JPEG; a JPEG with GPS EXIF comes back without it; a
bulk row carrying a mobile number fails without echoing it.

## 6. Acceptance criteria (testable)

- **AC1** Each of the 10 value fields can be set, changed and cleared via `POST`/`PATCH
  /school/students`, and set via bulk upload; Photo can be set, replaced and removed via the photo
  endpoints.
- **AC2** Invalid values are rejected with a 422 naming the field (single edit) or a rejected row with
  the same message (bulk); valid rows in the same batch are still accepted.
- **AC3** `section` exists as its own column; migration `0039` backfills it for parseable labels,
  leaves unparseable ones NULL and logs their `student_code`s; `grade_or_class` is byte-identical
  before and after upgrade and downgrade.
- **AC4** `grade_level` and `section` can each be filtered on independently (SQL-level test).
- **AC5** Two students cannot share a roll number within the same school + academic year + grade +
  section (case-insensitive section, blank section is a group); a clash returns 409 on single edit
  and rejects only that row in bulk; concurrent duplicate creates yield exactly one success.
- **AC6** The template's first 7 columns are unchanged in name and order; the 10 new columns follow;
  a CSV with only the original columns uploads exactly as before; the column reference is shown in
  the UI and in `API_CONTRACT.md` §12A.
- **AC7** Existing request payloads produce the same results and every existing response key; the new
  keys are additions.
- **AC8** Photo is readable only by roles that can read the student; `photo_key` never appears in any
  response; a missing photo renders a placeholder everywhere.
- **AC9** A career counselor can read/write only the 4 career fields, only for students in their
  portfolio; any other key → 422.
- **AC10** Promotion (promote and hold-back) clears `roll_number` and records previous section, roll
  number and new section in grade history; transfer approval clears `section` and `roll_number`.
- **AC11** Forms are keyboard-operable, labelled, grouped, single-column at ≤640px, show busy /
  error / success states, and return focus correctly.
- **AC12** Every abuse case in §5 is rejected with the stated status; stored photos contain no EXIF /
  text metadata; photo responses carry the §5 headers; audit rows and logs contain no field values
  and never the photo key.

## 7. Testing strategy (detail in the implementation plan)

- **Backend (pytest, real Postgres):** migration backfill table + round-trip; `StudentMasterFields`
  rules; create/update set/clear/absent + compatibility; roll uniqueness incl. case, NULL group, other
  year, concurrency (pattern: `test_enh_005_concurrency.py`); bulk new columns, old CSV, row-level
  rejection, `;` lists, template order; every §5 abuse case; metadata stripping (JPEG GPS EXIF, PNG text chunks, malformed file → 422);
  bounded read; photo type/size/scope/headers/idempotent delete/replacement
  cleanup/no key leak; counselor route authz and key allowlist; promotion + history; transfer;
  audit metadata; single Alembic head.
- **Frontend (vitest):** payload builder; field groups render labelled inputs; create/edit send new
  keys; focus management; photo none/has/broken/uploading/rejected; counselor loading/error/retry/save;
  bulk column reference; "Not recorded" rendering; grade history new columns.
- **Playwright:** extend `sch-002-bulk-roster-upload.spec.ts` with new columns; new
  `enh-025-student-master-fields.spec.ts` (coordinator edit + photo, teacher read-only, counselor
  preferences, 375px viewport).
- **Targeted regression:** ENH-001, ENH-004, ENH-005, SCH-001, SCH-002, `test_sch_reports.py`,
  ENH-012 portfolio (reads `grade_or_class`), related Playwright specs.

## 8. Regression risks

| Risk | Mitigation |
|---|---|
| ENH-004 promotion / grade history | `grade_or_class` untouched; only additive history columns and `roll_number = NULL`; ENH-004 suites re-run |
| Dashboard grade KPIs (`schools.py:335-368`) | no change to `grade_level`/label logic; `test_sch_reports.py` re-run |
| Existing bulk CSVs / integrations | headers appended, absent columns ignored, old-CSV test |
| Response consumers | additive keys only; compatibility test |
| Promotion transaction failing on roll clash | roll cleared on every year move (NULL never conflicts) |
| Migration head collision with ENH-013 | single-head test; renumber on merge |
| Bulk upload per-row savepoints change timing | batch semantics unchanged; SCH-002 suite re-run |
| Photo storage leaks via `/local-files` | random unserialized key; documented residual risk |
| ~40 files display `grade_or_class` | not changed — no caller audit required for the label |

## 9. Decisions made in-session (to record as `DEC-SCOPE-029`)

1. Keep `grade_or_class`; add `section`; `grade_level` (ENH-001) is the Grade column.
2. Career interests, Global education interest, Preferred countries, Preferred courses live on
   `SchoolStudent`; written by the Coordinator (all paths) **and** the career counselor (own portfolio,
   dedicated route).
3. Photo via authorized upload/stream endpoints; not in bulk upload.
4. Gender fixed list; multi-value fields as JSON string lists; Global interest nullable boolean.
5. Roll number unique per school + academic year + grade + section, blank values forming a group.
6. Any academic-year move (promote or hold back) clears roll number; grade history records previous
   section/roll number and new section.
7. Transfer approval clears section and roll number.
8. All new fields optional (no field is made mandatory).
9. Photo metadata (EXIF etc.) stripped in pure Python before storage; no image library added.
10. Consent / legal basis for photos of minors: the school is responsible (resolved by the user 2026-09-23); Photo ships
    without a consent gate.

## 10. Carried forward (not blockers)

- Bulk photo import (ZIP keyed by `student_code`).
- Pre-existing: bulk upload's idempotency check is select-then-insert; two simultaneous uploads with
  the same key hit the unique constraint and return 500 instead of a replay.
- Pre-existing: `GET /school/students` unpaginated.
- `ENH-013`'s counselor `career_goal` and `ENH-026`'s career-record restructure should read, not
  duplicate, the §2 career fields.
- Controlled vocabularies for subjects/countries/courses (no source defines them).
- ~~`NEEDS_CONFIRMATION`: consent / legal basis for storing photos of minors~~ — resolved 2026-09-23: the school is
  responsible (`DEC-SCOPE-029` item 10).
- Migration order: ENH-025 merges first; ENH-013 renumbers its migration to 0040 (`DEC-SCOPE-029` item 11).
- Pre-existing: bulk upload has no file-size or row-count cap (DoS surface); ENH-025's per-row
  savepoints add round-trips but do not change the bound.
- Pre-existing: the Next API proxy buffers whole request bodies before forwarding.
- Future: any CSV/XLSX export of the new free-text fields must neutralise leading `= + - @`.
- Future: data-subject deletion/retention for school-student personal data (students are never
  deleted today).
