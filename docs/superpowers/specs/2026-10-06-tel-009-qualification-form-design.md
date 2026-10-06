# tel-009 — Lead qualification form (design)

Backlog: `docs/delivery/TELECALLER_CRM_BACKLOG.md` tel-009 (EVID-019 §4, Appendix A L144–L196). Dependency tel-008 is merged (PR #85).
The branch is `feature/tel-009`, cut from `main` @ `126b454b` (tel-006 merged). Decision `DEC-SCOPE-092`, migration `0088_lead_qualifications`
(after tel-006's `0087_lead_import_batches`), API contract §12O. §12M is still claimed by the open AGN-023 branch.

## 1. Owner answers (2026-10-06, `EXPLICIT_APPROVAL`, in-session) and recorded defaults

| # | Question | Answer |
|---|---|---|
| QF1 | Where is "Course interested in" / "Destination" (both are `enquiries.product_id`) picked? | **In Lead details only.** The form shows the product read-only and the product is changed through tel-008's "Edit details" (a single write path, D2). The IT or overseas section follows the saved product. The other group's stored values are kept but hidden (AC3) |
| QF2 | Field types | **Selects plus free text.** Selects: `it_skill_level` beginner/intermediate/advanced, `preferred_mode` online/offline, `study_level` ug/masters, `passport_status` none/applied/valid. Free text: `english_test_status` (it can hold a score), `preferred_batch`, `budget_range`, `intake`, `preferred_course`, `career_objective`, `current_org`. `work_experience_years` is a whole number 0–50, `academic_percentage` is 0–100 with 2 decimals, and `passing_year` is 1950–2100 (the existing lead CHECK) |
| QF3 | Counselor read after handover | **Deferred to tel-018**, which builds the counselor's lead screens. tel-009 serves the `/telecaller` scope: a telecaller on their own lead (read-only once handed over), a manager (reports plus team queue) and `super_admin` |
| QD1 (default) | Shared fields | `qualification`, `passing_year`, `city` and `state` live on `enquiries` (tel-003), and the PUT writes them there. `name` is shown in the page header and edited in Lead details, not here. `work_experience_years` and `budget_range` are single columns that both groups share (Appendix A L192, L194) |
| QD2 (default) | PUT semantics | PUT replaces the fields that **apply** to the lead's current product: the basic fields always, plus the IT fields (product group `it`) or the overseas fields (`overseas`). An omitted applicable field is cleared. Sending a field that does not apply is `422` (this also catches a product changed while the form was open), and the other group's stored values are untouched. A lead with no product or an `other` product takes basic fields only |
| QD3 (default) | Audit | Only fields that actually changed are written. One `lead.qualification_update {fields}` audit row is written per save, holding field names only, never values. No change means no audit. The stage never moves (backlog: the telecaller marks Qualified through tel-004) |
| QD4 (default) | Concurrency | The lead row is locked `FOR UPDATE` within scope (tel-008's `locked_lead`), so two first saves can't both insert the `lead_id` primary key. A lead reassigned while the form was open is 404 |

## 2. Data (`lead_qualifications`, migration `0088_lead_qualifications`)

| Column | Type |
|---|---|
| `lead_id` | UUID PK, FK `enquiries.id` ON DELETE CASCADE |
| `current_org` | varchar(200) null |
| `work_experience_years` | smallint null, CHECK 0–50 |
| `it_skill_level` | varchar(20) null, CHECK in beginner/intermediate/advanced |
| `career_objective` | varchar(500) null |
| `preferred_batch` | varchar(120) null |
| `budget_range` | varchar(120) null |
| `preferred_mode` | varchar(10) null, CHECK in online/offline |
| `study_level` | varchar(10) null, CHECK in ug/masters |
| `preferred_course` | varchar(200) null |
| `intake` | varchar(40) null |
| `academic_percentage` | numeric(5,2) null, CHECK 0–100 |
| `english_test_status` | varchar(120) null |
| `passport_status` | varchar(10) null, CHECK in none/applied/valid |
| `updated_by_user_id` | UUID FK `users.id` ON DELETE RESTRICT, not null |
| `created_at`, `updated_at` | timestamptz (TimestampMixin) |

The upgrade is guarded (0001 builds a fresh database from the models, which is 0086's idiom), and the downgrade drops the table. Existing data is untouched.

## 3. API (`app/api/telecaller.py`, service `app/services/lead_qualification.py`)

Scope is `lead_pipeline.scope(user)` (§12H): other roles get 403, signed out gets 401, and a missing or out-of-scope lead is 404.

| Route | Behaviour |
|---|---|
| `GET /telecaller/leads/{id}/qualification` | `200 {lead_id, product: {id, name, group} or null, product_group: it/overseas/other or null, qualification, passing_year, city, state, current_org, work_experience_years, it_skill_level, career_objective, preferred_batch, budget_range, preferred_mode, study_level, preferred_course, intake, academic_percentage, english_test_status, passport_status, read_only, updated_by: {id, full_name} or null, updated_at or null}`. Every stored value is returned, the hidden group's included. With no saved row, the shared values come from the lead and the rest are null |
| `PUT /telecaller/leads/{id}/qualification` | Body `LeadQualificationIn` (extra keys 422; text trimmed, control characters refused, blank = null). It is 422 for a field that doesn't apply (QD2) or an out-of-range value (percentage 120, year 1900). A telecaller on a handed-over lead gets 403. `200` returns the GET shape. Audit `lead.qualification_update {fields}` |

## 4. Web

- `lib/telecallerLeads.ts`: `LeadQualification` type, `qualificationUrl`, option labels and the field groups (`BASIC_FIELDS`, `IT_FIELDS`,
  `OVERSEAS_FIELDS`).
- `components/LeadQualificationForm.tsx` (client): the "Qualification" section of the lead detail. It loads by GET and re-reads when the
  lead's product changes, so it has loading, error-with-retry, view and edit states. View is a `dl`, with "Not recorded" for blanks. Edit is one
  form with `fieldset.form-section`s: "Basic qualification", then "IT training requirement" or "Overseas requirement" by `product_group`, with
  the product shown read-only plus the hint "Change it in Lead details". Client checks (percentage 0–100, year 1950–2100, experience 0–50)
  set `aria-invalid` with field messages, and the server's 422 shows in the form. `useLeaveGuard` runs while the form is dirty. A read-only
  lead shows the view only. A save hands the shared values back to the panel, so Lead details shows the new city/state/qualification/year.
- `LeadDetailPanel.tsx` renders the section after Lead details for both the telecaller and the manager detail pages.

## 5. Acceptance criteria (testable)

1. The IT section shows (and the PUT accepts its fields) only for an IT product, and the overseas section only for an overseas product. An
   `other` product or no product shows basic fields only.
2. Academic percentage is 0–100 (120 gives 422). The passing year is 1950–2100. Work experience is 0–50.
3. When the product group changes, the other group's values are kept (GET still returns them) but hidden, and a PUT never clears them.
4. The shared fields write through to the lead (`qualification`, `passing_year`, `city`, `state`).
5. Saving never changes the stage. It writes one `lead.qualification_update {fields}` row only when something changed.
6. Another telecaller's lead or a random id gives 404, another role gets 403, and a telecaller on a handed-over lead gets 403 on PUT (GET is allowed,
   `read_only: true`).

## 6. Risks

`LeadDetailPanel` is shared by the telecaller and manager pages, so tel-008's vitest and e2e run again. The PUT writes `city`/`state`/
`qualification`/`passing_year` that tel-008's PATCH also writes. Both lock the lead row, so last write wins with no lost update inside one
transaction.
