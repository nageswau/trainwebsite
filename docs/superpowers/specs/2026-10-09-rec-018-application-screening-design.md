# rec-018 — Screening form + result (design)

- **Backlog:** `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-018. **Evidence:** `EVID-018` §13 (lines 556–592): 11 checklist items and 4
  results. **Dependency:** rec-017 (PR #178), merged. The module scope is `DEC-SCOPE-116`.
- **Decision:** `DEC-SCOPE-149`. **Migration:** `0134_application_screenings` on `0133_interview_management`. **API:** §12BQ.
  **RBAC:** §2.75.
  - Drafted as 0125 / DEC-SCOPE-140 / §12BH / §2.66 on `0122_candidate_skills`, then 0126 / 141 / §12BI / §2.67. rec-010, upc-026,
    upc-012, the upc items through 0132 and rec-020 (0133 / 148 / §12BP / §2.74) merged first, so this item was re-numbered.
- **Answers.** SC1–SC8 are **recommended defaults**. They were taken on the owner's standing instruction for build sessions ("proceed with
  the recommended answers; ask only if blocking"). They stay `UNVERIFIED` until the owner confirms them. SC1 and SC2 answer the backlog's
  Q-18.
  - **SC1 (Q-18a):** screening is **not** required before Shortlisted. rec-017's permissive moves (A2) and "add at Shortlisted" stay as
    they are.
  - **SC2 (Q-18b):** Hold and Need More Information **do not pause** the application. Its status stays, and the board shows the screening
    result as a flag (A1 has no `on_hold` status).
  - **SC3:** the effect of each result on the status:
    - **Shortlisted** moves the application to `shortlisted`, but only from `sourced` or `screened`. Moves are forward only, so an
      application already at shortlisted, profile_shared or interview keeps its status.
    - **Rejected** moves the application to `rejected`.
    - **Hold** and **Need More Information** never move it.
    - A move goes through `applications.change_status`, which writes the history row with the note `Screening: <result>`. It also
      notifies the student, as the status route does.
  - **SC4:** a screening can be saved only while the application is open (sourced, screened, shortlisted, profile_shared or interview).
    Otherwise the save is a 409. A rejected application is reopened to Sourced first; that is the edge case "re-screening after Hold".
  - **SC5:** there is **one current screening per application**, and each save overwrites it.
    - The PUT replaces every field; a field left out is cleared.
    - A save writes one audit row, `recruiter_application.screening`, holding the changed field **names** and the result, never the
      values (salary is internal).
    - A save with no change is a no-op 200 that writes no audit row.
  - **SC6:** the field types:
    - Qualification, experience and skills verified are booleans, false by default.
    - Expected salary is a number from 0 to 9,999,999,999.99, matching `candidates.expected_salary`.
    - Notice period is 0 to 365 days.
    - Location preference is text of up to 200 characters.
    - Communication and technical are ratings from 1 to 5, and are optional.
    - Availability is text of up to 120 characters, for example "Immediate".
    - Willingness to relocate is yes, no or unknown.
    - Remarks are text of up to 2,000 characters.
    - The result is required, and is one of shortlisted, hold, rejected or need_more_info.
  - **SC7:** a result of Rejected requires remarks, otherwise the save is a 422 (AC2).
  - **SC8:** readers are the requirement's readers: the recruiter on their own requirements, the manager on the team's, `super_admin`,
    and the assigned BDM. Writers are rec-017's `WRITERS` (`placement_team` in scope and `super_admin`). The employer, students and
    `hr_team` never see a screening ("salary data internal only").

## 1. Data (migration 0134)

New table `application_screenings`:

| Column | Type |
|---|---|
| `application_id` | PK, FK to `job_applications`, RESTRICT |
| `qualification_verified`, `experience_verified`, `skills_verified` | boolean, NOT NULL, default false |
| `expected_salary` | numeric(12,2), NULL |
| `notice_days` | smallint, NULL |
| `location_preference` | varchar(200), NULL |
| `communication_rating`, `technical_rating` | smallint, NULL |
| `availability` | varchar(120), NULL |
| `willing_to_relocate` | boolean, NULL |
| `remarks` | varchar(2000), NULL |
| `result` | varchar(20), NOT NULL |
| `screened_by_user_id` | FK to `users`, RESTRICT |
| `created_at`, `updated_at` | timestamps |

The CHECKs are the result set, the ratings 1–5, notice 0–365, salary ≥ 0, and "rejected ⇒ remarks present". `SCREENING_CHECKS` lives in
the models and the migration repeats it; the migration test asserts the two are equal. The table is created only when missing (the 0001
`create_all` idiom). Downgrade refuses while any row exists.

## 2. Service: `services/application_screening.py`

- `read(db, user, application)`: returns the screening or None, the results catalogue, and `can_edit`, which is `can_write` and the
  application being open.
- `save(db, user, application, fields)`:
  - It is a 409 when the application is not open (SC4).
  - It upserts the row, keyed by `application_id`, and writes the audit of the changed names.
  - It applies SC3 through `applications.change_status`, and returns whether the status moved.
  - Nothing in it commits; the route has already locked the application (rec-017's `load_scoped(lock=True)`), so concurrent saves
    serialise.

## 3. API (§12BQ), in `api/recruiter_applications.py`

| Route | Who | Rules |
|---|---|---|
| `GET /recruiter/applications/{id}/screening` | the requirement's readers | 404 out of scope. Returns `{screening \| null, results, can_edit}`. |
| `PUT /recruiter/applications/{id}/screening` | writers in scope | 403 for the wrong role, 404 out of scope, 409 when the application is not open, 422 on a bad body (a rating out of range, or Rejected without remarks). Returns `{screening, application}`. |

The rec-017 list item gains `screening_result: {key, label} | null`, so the board can show the flag. The field is additive; the guards
ignore unknown keys.

## 4. Web

- `lib/recruiterApplications.ts`: the types, the URL suffix `/screening`, and the guard.
- `RecruiterApplicationScreening` (new): the form inside the candidate's item on the requirement board.
  - It loads with GET and shows loading and error states.
  - The verified items are checkboxes. Salary and notice are number fields. The ratings and relocate are selects ("Not rated",
    "Not asked"). Location and availability are text fields; remarks is a textarea. The result is a required select.
  - When Rejected is chosen, the remarks are marked required.
  - When `can_edit` is false, it shows a read-only summary.
- `RecruiterRequirementCandidates`: a "Screening" toggle on each item, and a `Screening: <result>` badge when a screening exists. A save
  re-reads the list and announces "Screening saved — <name> is now <status>."

## 5. Tests

- **Backend `test_rec_018_*`:**
  - The migration: the CHECKs equal the models, the chain, and the downgrade refusal.
  - AC1: Shortlisted moves the status and writes history.
  - AC2: Rejected without remarks is a 422.
  - A rating out of range is a 422.
  - Hold keeps the status and shows the flag, and re-screening after Hold works.
  - A save on a closed application is a 409.
  - A save with no change writes no audit row.
  - The audit has no values.
  - Roles and scope: the manager and BDM read, `hr_team` is refused, and out of scope is a 404.
  - A student is notified when the status moves.
- **Web:** vitest for the form (Rejected requires remarks, and the read-only mode) and the badge; a Playwright e2e for screening → Shortlisted
  and Hold → re-screen.

## 6. Risks

Low. This is a new table only. The rec-017 item shape is extended, not changed. The status still moves only through the single writer.
