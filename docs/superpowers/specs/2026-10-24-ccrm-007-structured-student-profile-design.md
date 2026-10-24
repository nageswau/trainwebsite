# ccrm-007 — Structured overseas student profile (design)

NO-ASSUMPTION MODE. Backlog item `ccrm-007` (`docs/delivery/COUNSELOR_CRM_BACKLOG.md`), spec §5 (Academic, Study preferences,
English tests tabs) and §15 (Student record). Source class: `UNVERIFIED` spec + owner request (backlog header). Dependencies: none.
Numbers at write time: migration `0174_student_profiles`, `DEC-SCOPE-249`, API §12FB, RBAC §2.164.

## 1. Owner answers (2026-10-24, clarifying-question prompt)

| ID | Question | Answer |
| --- | --- | --- |
| P1 | Which profile fields may the student edit? | **All fields** — personal, passport, qualifications, work experience, preferences, English tests. Last write wins (as CC5); each save audited with its author; the page shows who saved last. |
| P2 | Agency student (an `AgentStudent` row exists) | **Profile editable; agent reads.** The profile is the single student record; the counselor and the student edit it; the agent sees it read-only on the agency student detail; `AgentStudent` fields stay the agency's own record, nothing is synced. |

Recommended defaults (`NEEDS_CONFIRMATION`, not asked): P3 the agent's read never includes passport number/expiry (restricted until
ccrm-022); P4 the old `users.profile` keys are copied once and left in place (never deleted); P5 save = full replace of the profile and
its child rows (AGN-006 counseling idiom), no version check (CC5 last write wins); P6 limits 10 qualifications, 5 English tests,
5 preferred countries.

## 2. Existing behaviour (verified on main @ bf9b5684)

- `User.profile` JSON; the overseas student portal "profile" section reads `education`, `preferred_countries`, `preferred_intake`,
  `english_test` (`services/portal.py` `_overseas_student`), seeded on the demo student (`seed.py`).
- The student edits those keys through the generic "Update profile" form (`WorkflowPanel.tsx` profile section → `PATCH /auth/me`,
  shared with `it_student`).
- Structured academic fields exist only on `AgentStudent` (agency record).
- Counselor scope helper: `services/counselor_students.is_visible_student` (csc-001); notes (ccrm-010) is the route/page pattern.

## 3. Data model (migration `0174_student_profiles`)

`overseas_student_profiles` (PK `student_user_id` → users, cascade): `date_of_birth`, `nationality`, `city`, `state`,
`passport_number`, `passport_expiry`, `work_experience_months` (0–600), `work_experience_details`, `preferred_country_ids` (JSON list of
country ids), `preferred_course`, `preferred_level` (CHECK `COURSE_LEVELS`), `preferred_intake`, `study_mode` (CHECK full_time /
part_time / online), `budget_min`, `budget_max`, `budget_currency` (CHECK `COUNSELING_CURRENCIES`), `updated_by_user_id`, timestamps.

`overseas_student_qualifications`: `id`, `student_user_id` → profile (cascade), `position` (unique per student), `level` (CHECK
class_10 / class_12 / diploma / bachelor / master / phd / other), `qualification_name`, `institution`, `board_university`,
`year_completed`, `score_type` (percentage / cgpa), `score`, `backlogs`.

`overseas_student_english_tests`: `id`, `student_user_id` → profile (cascade), `position`, `test_type` (IELTS / PTE / TOEFL / Duolingo /
other), `status` (nullable; not_taken / booked / taken), `overall_score`, `test_date`, `valid_until`, `remarks`.

Data copy (P4): each `overseas_student` with any of the four JSON keys and no profile row gets one: `preferred_countries` names →
country ids (case-insensitive name match; unmatched names dropped), `preferred_intake` → `preferred_intake`, `education` → one
qualification (level `other`, `qualification_name`), `english_test` → one test (type detected from the text, else `other`; status
NULL; the text in `remarks`). Downgrade drops the three tables (the JSON is untouched, so nothing is lost).

## 4. API (§12FB)

- `GET/PUT /api/v1/counselor/students/{id}/profile` — overseas counselor in csc-001 scope; Overseas Admin any overseas student. Out of
  scope / unknown / not an overseas student → 404; any other role → 403.
- `GET/PUT /api/v1/overseas/me/profile` — the `overseas_student` themselves; other roles 403.
- `GET /api/v1/workflows/overseas/agent/crm/students/{agent_student_id}/profile` — agency scope (`load_scoped`); passport omitted;
  `{"profile": null}` for a record with no login.
- GET with no row returns the empty profile (`exists: false`). PUT validates and replaces; 422 on validation; writes an
  `overseas_student_profile.update` audit row (field names only, never values) in the same transaction. The student row is locked
  (`FOR UPDATE`) first so two first saves cannot race to a duplicate key.

Validation: dates not in the future for DOB/test date (DOB ≥ 1900); passport `^[A-Z0-9]{5,20}$` (upper-cased); score percentage 0–100,
CGPA 0–10, score needs a score type; year 1950..now+6; English overall score in the test's range (IELTS 0–9, PTE 10–90, TOEFL 0–120,
Duolingo 10–160, other 0–999); `valid_until ≥ test_date`; `budget_min ≤ budget_max`; currency required when a budget is set;
preferred countries distinct, ≤5, must exist (422 "Choose a listed country"). Response adds `expired` per test (valid_until < today),
`preferred_countries` [{id, name}], `updated_by_name`, `updated_at`.

## 5. UI

- `OverseasStudentProfileForm` (client): Personal, Passport, Academic (qualification rows add/remove), Work experience, Study
  preferences, English tests; read-only mode for the agent. Loading / error / saved states; in-flight guard; errors announced.
- Counselor `/overseas/counselor/students/[id]/profile`, admin `/overseas/admin/students/[id]/profile` (server page like ccrm-010's
  notes, same 404/403/redirect rules). "Profile" link beside "Notes" in the counselor Students table, the walk-in list and the
  admin Users directory.
- Student "Profile" section renders the form against `/overseas/me/profile`; the generic "Update profile" form keeps only name and
  phone for `overseas_student` (it_student unchanged).
- Agency student detail: read-only "Student profile" card when the record has a login.
- ccrm-009 will host the same form in its Academic / Preferences / English tabs.

## 6. Security review

IDOR: every route resolves the student through the caller's scope and returns the same 404 for unknown and out-of-scope. Role
escalation: the student route ignores any id (self only); no route writes `users.profile` server-owned keys. Passport (PII): never in
the agent read, never in audit metadata or logs. Input: Pydantic `extra="forbid"`, length caps, enums, numeric ranges. XSS: React
escapes text. CSRF: the existing cookie + same-origin middleware covers PUT. SQL: ORM only.

## 7. Regression risks

Student portal profile section payload (now from the table), `PATCH /auth/me` (unchanged server-side), it_student profile form
(unchanged), the counselor Students and admin Users tables (one added column), agency student detail (new card only).

## 8. Tests

Backend `tests/test_ccrm_007_student_profiles.py` (counselor two qualifications + IELTS → student sees them; another counselor 404;
admin; student self-edit; validation 422s; agent read without passport; audit; portal section) and
`tests/test_ccrm_007_migration.py` (chain, constants, data copy, round trip). Web vitest for the form; Playwright e2e for the counselor →
student flow.
