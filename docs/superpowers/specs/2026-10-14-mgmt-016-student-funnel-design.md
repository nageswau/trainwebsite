# mgmt-016 — Student funnel dashboard (design)

**Source:** `EVID-017` §11 "STUDENT DASHBOARD" (lines 409–467, `DERIVED_BLUEPRINT`): the Total Student Funnel Leads → Telecalling →
Counseling → Registration → Training / Abroad Education → Application → Offer / Certification → Visa / Placement → Enrollment / Joining,
broken down by Country, Course, Agent, School, Counselor, Marketing source, BDM, Intake and Branch. Backlog
`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-016. It depends on mgmt-003, which was merged in PR #244. Open question Q-18. M9 and M10 apply.

**Authority:** every SF answer below is a **recommended default, `UNVERIFIED`**. It was taken on the owner's standing instruction to
proceed with recommended answers. SF2–SF15 answer Q-18. It is registered as a DEC-SCOPE when it merges, with the number taken at merge.

## What the data supports (verified in code)

- Leads are `Enquiry` rows (`created_at`, `division`, `source` ∈ the 13 tel-002 sources, `owner_id`, `bdm_user_id`). Each lead has one
  value per lead-side dimension.
- Telecaller calls are `LeadCall` rows (`occurred_at`). Counseling is an `Appointment` with a `lead_id` and status `completed`, dated by
  `scheduled_at`. A lead's conversion is `telecaller_metrics.first_conversions()` (T5): mgmt-018 conversions, mgmt-019 "Registration".
- IT: `Enrollment` (`enrolled_on`, status, `Batch.program_id`), `JobApplication` (`student_id`, `created_at`), `Certificate`
  (`issued_on`, `program_id`), `JobOffer` (`offered_on`, `joining_status = 'joined'` + `actual_joining_date`, the rec-023 rule).
- Abroad: `OverseasApplication` (`created_at`, `submitted_on`, university → country, `course_id`, `agent_id` → agency,
  `school_student_id` → school, `counselor_id`, `intake`). An offer or enrolment has no date column of its own, but every status change
  writes an `ApplicationStatusHistory` row (`created_at`). A visa decision is dated by `VisaCase.decided_at`.
- **Not linked:** a lead and the IT or abroad records of the student it became are joined only through `converted_user_id`. An
  application or enrolment may never have had a lead (agency, school or direct). So the stages cannot form one cohort.
- No branch exists anywhere (M10).

## Decisions (SF1–SF16)

| # | Point | Answer |
|---|---|---|
| SF1 | Period | `from` / `to`, inclusive IST dates, default this IST month. Start after end, or more than 366 days → 422 (`bdm_performance.period`, as mgmt-017/018) |
| SF2 | Funnel shape | **Activity in the period.** Each stage counts the records that *reached* that stage within the period. It is not a cohort (see "Not linked"), so a later stage can be larger than an earlier one, and no stage-to-stage conversion % is shown. There are three paths: the shared **lead journey** (Leads → Registration), then the **IT training** and **Abroad education** paths side by side. Each source pair "X / Y" is split: Training/Abroad, Certification/Offer, Placement/Visa, Joining/Enrollment. "Application" exists on both paths |
| SF3 | Leads | Leads created in the period (any division and source) |
| SF4 | Telecalling | Distinct leads with at least one telecaller call logged in the period |
| SF5 | Counseling | Distinct leads with a counseling appointment completed that was scheduled in the period |
| SF6 | Registration | Leads first converted in the period and still converted (T5 = mgmt-019 Registration, mgmt-018 Conversions) |
| SF7 | Training (IT) | Enrolments dated (`enrolled_on`) in the period whose seat was taken: not `pending_consent` or `rejected`, in a batch that is not cancelled. A student who later dropped still reached the stage |
| SF8 | Application (IT) | Job applications of EduSphere students (`student_id` set) created in the period. External candidates are not students |
| SF9 | Certification (IT) | Certificates issued in the period |
| SF10 | Placement (IT) | Job offers to EduSphere students made (`offered_on`) in the period |
| SF11 | Joining (IT) | Job offers to EduSphere students joined with an actual joining date in the period (rec-023; TR14's event) |
| SF12 | Abroad Education | Overseas applications created in the period, from students, schools and agencies, including any later withdrawn (mgmt-024 "Created") |
| SF13 | Application (Abroad) | Overseas applications submitted (`submitted_on`) in the period (mgmt-024 MF5) |
| SF14 | Offer | Applications whose first move into an offer status (`OFFER_COUNTED_STATUSES`, mgmt-024 O5) is recorded in the period |
| SF15 | Visa / Enrollment | Visa: applications with a visa case decided **approved** in the period (the abroad outcome that pairs with a placement). Enrollment: applications whose first move to `enrolled` is recorded in the period |
| SF16 | Breakdowns (`by`) | One dimension at a time. Every counted record carries at most one value per dimension, so **the rows plus "Unknown" equal the stage total** (AC2). A dimension applies only to the stages whose records carry it. The other stages are listed as "not broken down by this". Mapping: **Country** = the application's university country (abroad stages). **Course** = the batch's program (Training), the certificate's program (Certification), the application's course (abroad stages). **Agent** = the agency of the application's agent user. **School** = the school of a school student's application. **Counselor** = the lead's current owner when that is a counselor (lead stages), or the application's counselor (abroad stages). **Marketing source** = the lead source (lead stages, tel-002 labels). **BDM** = the lead's BDM. **Intake** = the application's intake (blank = Unknown). **Branch** = not tracked (M10): no stage applies, and the UI says so. Rows are ordered largest first, then by label. A deactivated person is labelled "(inactive)" |

**Access and shape (SF16 cont.):** operational tier (partner, super_admin). The accountant gets 403 "Operational access required",
everyone else 403 "Management access required", and signed out is 401. An unknown `by` → 422. The response is `from`, `to`, `as_of`,
`paths` (key, label), `stages` (key, label, path, definition, value), `dimensions` (key, label, tracked, stages it applies to), and
`breakdown` (null without `by`; otherwise by, label, stages, rows of value + label + counts, unknown counts). The endpoint is read-only
and writes no audit row. It returns counts and organisation or staff names only. No student is named.

The edge case "a student in both IT and abroad" is handled because each path counts its own records. The student appears on both
paths, and the lead journey counts the lead once.

## Architecture

- `services/management_funnel.py`:
  - `STAGES`, each a builder of a select of *one row per counted record* with labelled dimension columns.
  - `DIMENSIONS`.
  - `dashboard(db, start, end, now, by)`: one query per stage (a count, or a count grouped by the chosen dimension), plus at most two
    label lookups. The query count is fixed and does not grow with the data.
  - It reuses `first_conversions`, `OFFER_COUNTED_STATUSES`, `SOURCE_LABELS` and `_instants`.
- `api/management.py`: `GET /management/funnel?from&to&by` runs `_operational(user)` then `period()`.
- `schemas.py`: `StudentFunnelOut` and its parts.
- Web:
  - `lib/managementFunnel.ts`, `components/ManagementFunnel.tsx`, `app/management/funnel/page.tsx`. The page is server-rendered with a
    GET form (period plus a breakdown select).
  - The bars reuse GlobalEducationFunnel's `pipeline-*` styles. The count is the text, and the bar is decoration.
  - `lib/management.ts` puts the "Student funnel" link live. `lib/navigation.ts` adds the super admin entry.

## UI

Period + "Break down by" form → note (period, IST, activity-not-cohort) → "Lead journey" stage list → "IT training" and "Abroad education"
side by side (stacked on a phone) → when `by` is set, a breakdown table (rows × applicable stages, an Unknown row and a Total row) that
scrolls in its own box. 422 message shown; 401/403 → access card. With nothing in the period every stage shows 0, which is a real count.

## Testing

- **Backend** (`test_mgmt_016_funnel.py`):
  - The access matrix.
  - The period default and the 422 cases, plus an unknown `by` → 422.
  - Each stage counts exactly its definition over a random 19xx month (shared DB): in-period and out-of-period records, a taken seat
    against a pending one, the first offer move, an approved visa against a refused one.
  - Each breakdown's rows + unknown equal the stage totals, with exact per-value counts.
  - Branch is untracked.
- **Web:** vitest for the lib and the component, and a Playwright e2e test for the page.
