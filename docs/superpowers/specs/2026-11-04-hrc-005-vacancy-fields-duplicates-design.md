# hrc-005 — Vacancy fields completion and job duplicate detection (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-005` (PDF §4.1 "unique Job ID. Detect likely duplicates by employer,
  title, location and requisition reference", "Display … Last Updated By"; §4.2 field groups, Appendix A; PDF `UNVERIFIED`).
  Dependencies hrc-003 (stale guard) and hrc-004 (audit history) are merged.
- **Decision:** `DEC-SCOPE-380`. The owner said to proceed with the recommended answers, so V1–V10 are **the builder's calls
  (`NEEDS_CONFIRMATION`)**, including Q-06.

## Intent

A recruiter records a vacancy completely (requisition reference, source, certifications, country/state/city, relocation and travel,
pay currency and period, benefits, hiring manager, expected joining date) and sees who last changed it. Before a second copy of an
existing live vacancy is saved, the recruiter is shown the likely duplicates and must either cancel or proceed with a reason, which
is audited.

Non-goals: co-owners / placement-officer owner (hrc-006), approval and Filled (hrc-007), visibility (hrc-008), the employer and legacy
`/workflows/it/jobs` forms (V9), parsing legacy free-text locations (V3).

## Builder's calls

- **V1 fields** (`jobs`, all nullable, migration `0256`): `requisition_reference` (80), `source_id` → `rec_lead_sources` (the existing
  recruiter source catalogue; must be active when set or changed, the `check_category` rule), `certifications` (1000, multi-line),
  `country`/`state`/`city` (120 each, as on `companies`), `relocation_required` (bool; null = not stated), `travel_requirement` (120,
  free text such as "Up to 25%"), `salary_currency` (ISO-like three letters, hrc-011's validator; null = INR), `salary_period`
  (`year`/`month`, hrc-011's `SALARY_PERIODS`; null = a year), `benefits` (1000, multi-line), `hiring_manager_user_id` → users,
  `expected_joining_date`, `updated_by_user_id` → users. CHECKs `ck_jobs_salary_currency`, `ck_jobs_salary_period` (migration repeats
  them; the migration test asserts they stay identical).
- **V2 hiring manager** = an **active `interviewer`** user (hrc-002's internal Hiring Manager/Interviewer role), checked `FOR SHARE` on
  set/change (422 "Choose an active hiring manager"); keeping a since-deactivated one is allowed. Picker:
  `GET /recruiter/requirements/hiring-managers?q=&limit=` → `{items:[{id, full_name, email}], total}`, same role gate as the list.
- **V3 location (Q-06)** `location` stays the NOT NULL display string every reader uses (public card, student list, employer). It is
  no longer required when a city, state or country is given: blank `location` is derived as "City, State, Country" (non-empty parts,
  cut to 120). On edit, a location that equalled the old derived string follows the new parts; a typed location is never overwritten.
  Neither, after the merge = 422 "Enter the job location or its city". Existing rows are **not** migrated (free text stays as is).
- **V4 duplicate rule.** Same company (the company is already in the caller's scope, so no cross-scope leak), another job not
  `closed`/`cancelled`, and either (a) the same normalised title (trim, collapse spaces, lower) and the same place key —
  `coalesce(city, location)` normalised, so a new job with city "Pune" matches a legacy row whose location is "Pune" — or (b) the same
  normalised requisition reference. Index `ix_jobs_company_title_key (company_id, <title key>)`.
- **V5 warn, not block (Q-06).** No separate pre-check endpoint: `POST` and `PATCH` (when title, city, location or requisition
  reference changes) run the check in the write transaction and answer 409 `{code: "possible_duplicate", message, matches:[{id, code,
  title, location, status_label, requisition_reference}], total}` (the rec-003 company shape, first 10). Re-sending with
  `duplicate_reason` (1–500 chars) saves and writes `recruiter_requirement.duplicate_override` `{match_count, match_codes, reason}` in the
  same transaction (AC3). A reason with no match is ignored. Order: scope/role → stale token → duplicate → business rules.
- **V6 Last Updated By.** `updated_by_user_id` is set by every recruiter write that changes the row (edit, status, assign, weights)
  and by the employer and legacy job PATCH. Detail shows "Last updated by X on <time>" (null updater = "—").
- **V7 visibility.** Job salary is not behind hrc-001's candidate grant; the new pay fields follow the job's read scope. The hrc-004
  history redacts `salary_currency`, `salary_period` and `benefits` like `salary_min/max` ("changed", no values).
- **V8 UI.** The recruiter form gains sections Identification, Location, Compensation, Hiring plan; Job location loses "(required)"
  with a hint "Leave empty to use the city, state and country". The duplicate 409 shows a "Possible duplicate" alert panel listing the
  matches (links open in a new tab), a required reason field and "Save anyway" / "Go back" — the entry is never cleared. The detail page
  shows every new field and "Last updated by".
- **V9 other forms.** Employer and legacy create/edit keep their payloads (S6 precedent from hrc-003); a follow-up can add the fields
  there. They only set `updated_by_user_id`.
- **V10 numbering.** DEC-SCOPE-380, API §12JY, migration 0256 (renumber at merge if main moved).

## Acceptance criteria

1. Every V1 field can be saved on create and edit, cleared on edit, and is returned by GET (API + form + detail).
2. Same company + title (case/space-insensitive) + city → 409 `possible_duplicate`; a closed/cancelled match does not count; another
   company never matches; a legacy row with only a free-text location equal to the city matches.
3. Same requisition reference on a live job of the company → 409; with `duplicate_reason` → 201 and one `duplicate_override` audit row
   with the reason.
4. Location derived from city/state/country when blank; 422 when neither is given; legacy rows read unchanged.
5. `updated_by` shows the last editor (recruiter edit, status move, employer edit).
6. Hiring manager must be an active interviewer (422 otherwise); the picker lists only active interviewers.
7. History shows "changed" without values for currency/period/benefits.

## Regression risks

Public job card / student list read `location` (unchanged column, still always set); rec-007 tests that create two requirements with
the same title for one company (titles are tagged per test — verify); hrc-003 409 `record_changed` must still win before the duplicate
check; the employer/legacy routes.
