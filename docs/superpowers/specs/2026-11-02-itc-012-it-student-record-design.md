# itc-012 — IT student record completion (design)

**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-012 (classification `UNVERIFIED` PDF §4, owner-approved for build in waves
by Q-01, 2026-11-01). **Decision:** `DEC-SCOPE-345`. **Dependency:** itc-003 (`DEC-SCOPE-337`, merged — migration
`0222_it_student_counselors`) gives the counselor scope. **Q-11 (who sees the emergency contact) is unanswered**; the builder's call is
below (C1) and is `NEEDS_CONFIRMATION`.

## Intent

An IT student's record today is name, email, phone and a free-form `profile` JSON (`education`, `skills`). There is no emergency contact,
no structured personal data, and start/end dates and delivery mode exist only on the batch. The PDF (§4) asks the student record to carry
personal details, an emergency contact, per-student start/end dates, delivery mode and enrolment documents.

## Behaviour

1. **Table `it_student_profiles`** (one row per IT student, PK `student_user_id` → users): `date_of_birth`, `address` (≤300),
   `city` (≤80), `qualification` (≤120), `graduation_year` (1950 … this year + 6), `emergency_contact_name` (≤120),
   `emergency_contact_relation` (≤60), `emergency_contact_phone` (the shared mobile rule `_is_mobile`), `updated_by_user_id`, timestamps.
   An unsaved profile reads as empty (`exists: false`). The legacy `users.profile` JSON (`education`, `skills`) is untouched.
2. **Enrolment overrides** — nullable `enrollments.start_date`, `end_date`, `delivery_mode` (`Online` | `Offline` | `Hybrid`). The
   *effective* value is the override, else the batch's (`batches.start_date/end_date/mode`). Nothing writes the override when a batch
   changes, so a batch date change never overwrites it (AC2). A `null` in the save clears the override (back to the batch default).
   The effective end date may not be before the effective start date (422).
3. **API** (`api/it_student_profiles.py`):
   - `GET /it/me/profile`, `PATCH /it/me/profile` — the IT student (role `it_student`, division `it`) only; 403 otherwise.
   - `GET|PATCH /counselor/it/students/{id}/profile` — the IT counselor, only for linked students (itc-003); 403 for any other role,
     404 for an unlinked or non-IT student.
   - `GET|PATCH /admin/it/students/{id}/profile` — the IT Admin, any IT student; 403 for anyone else; 404 for a non-IT student.
   - `PATCH /counselor/it/students/{id}/enrollments/{enrollment_id}` and the `/admin/...` twin — the overrides; same scope; an
     enrolment that is not this student's is 404.
   - PATCH is partial (`exclude_unset`); unknown fields 422 (`extra: forbid`). Response = the GET shape:
     `{student: {id, full_name, student_code}, profile: {...fields, exists, updated_at, updated_by_name}, enrollments: [{id,
     enrollment_code, program, batch, status, start_date, end_date, delivery_mode, start_date_override, end_date_override,
     delivery_mode_override, batch_start_date, batch_end_date, batch_mode}]}`. The student's own GET shows enrolments read-only.
4. **Writes** lock the student's user row (`with_for_update`) so two first saves cannot both insert; last write wins after that.
   Audit: profile save → `it.student_profile.update` with the changed **field names only** (never values — PII); enrolment override →
   `itc-001`'s `audit_change` (`it.enrollment.dates_update`) with before/after (dates and mode are not personal data). Logs carry ids.
5. **UI**
   - IT student → Profile: the existing section and its account form stay; a new "My details" card (`ItStudentProfileForm`) below
     edits the structured profile and lists the enrolments' effective dates and mode.
   - IT counselor → My Students and IT Admin → Students: a "Profile" link column (existing `student_profile` DataTable type) to
     `/it/{counselor|admin}/students/{id}/profile` — the same form plus, per enrolment, an override editor (dates, mode, "use batch").
   - Loading is server-rendered; a failed load shows a retry card; save shows inline success/error (`role="status"`/`role="alert"`).

## Calls made by the builder (`NEEDS_CONFIRMATION`)

- **C1 (Q-11):** the emergency contact (and every field of this profile) is visible to the student, their linked IT counselor and the
  IT Admin only. Trainers, HR, placement, overseas roles and super_admin get no route (403). Not added to any export.
- **C2:** the student edits all the structured profile fields (personal + emergency contact); enrolment overrides are staff-only.
- **C3:** the delivery-mode override is one of `Online` / `Offline` / `Hybrid` (batches use free text; the seed uses Online/Hybrid).
- **C4:** the **enrolment documents checklist is deferred** — the backlog defines it "from itc-011's template", and itc-011 is not built.
  It is not in itc-012's acceptance criteria.
- **C5:** super_admin is not given access (itc-003 C1 precedent).

## Non-goals

No change to overseas profiles, batches, or the legacy `users.profile` keys. No 360 page (itc-029). No document checklist (C4).

## Acceptance criteria (testable)

1. Fields save and validate: a bad emergency phone, a future DOB, an out-of-range graduation year, an over-long text → 422.
2. A batch date change does not overwrite a per-student override; clearing an override falls back to the batch dates.
3. + The student adds an emergency contact and sees it on reload.
4. − A trainer (and HR) requesting a student's profile gets 403 — no emergency contact anywhere.
5. E: a student with two enrolments sees both, each with its own effective dates.
6. Scope: an IT counselor gets 404 for an unlinked student; an overseas counselor 403.
7. Regression: the IT portal Profile section rows and the account form still work.

## Regression risks

`enrollments` model/migration (many tests create enrolments — new columns are nullable); portal payloads of the IT counselor Students
and IT Admin Students tables (one more column); the route-documentation matrices (every route documented in API §12IQ / RBAC §2.245).

## Plan (TDD, small tasks)

1. Model `ItStudentProfile` + `Enrollment` override columns; migration `0229_it_student_profiles` (additive, idempotent, downgrade
   refuses while profiles or overrides exist); migration test.
2. Schemas `ItStudentProfilePatch`, `ItEnrollmentOverridePatch` (validators: text limits, mobile rule, DOB not future, year range).
3. Service `services/it_student_profiles.py`: `require_student`, `staff_student` (counselor scope via itc-003 / admin), `read`,
   `save`, `save_enrollment` (effective-date check, audit).
4. Router `api/it_student_profiles.py` (me / counselor / admin) + `main.py` registration; API tests 200/403/404/422, audit, PII.
5. Portal: `profile` link column in IT counselor Students and IT Admin Students payloads.
6. Web: `lib/itStudentProfile.ts`, `ItStudentProfileForm` (+ enrolment override editor), student Profile mount, two staff pages; vitest.
7. Docs: DEC-SCOPE-345, API §12IQ, RBAC §2.245, backlog status; Playwright spec; browser QA.

## Phase 3 review notes (api / frontend / security)

- API: PATCH (partial) matches the backlog's "profile GET/PATCH"; 403 for a wrong role / 404 outside scope, as in itc-003; no ETag
  (none contracted).
- Security: IDOR — every staff route resolves the student through the scope check before any read; the enrolment id must belong to
  the student (404). PII never logged or stored as audit values. Text goes through `clean_free_text`; React escapes output. Auth is the
  existing `get_current_user` (CSRF posture unchanged). No new rate limiting (platform default).
- Frontend: reuse `.card` and the field markup of `StudentProfileForm`; a `<label>` per input, `type="date"`/`type="tel"`, inline
  errors, buttons disabled while saving (no duplicate submission), success/error announced (`role="status"`/`role="alert"`).
