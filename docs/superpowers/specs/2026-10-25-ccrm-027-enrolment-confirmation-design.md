# ccrm-027 — Enrolment confirmation and post-offer outcomes (design)

Status: design, 2026-10-25. Backlog item `ccrm-027` (`docs/delivery/COUNSELOR_CRM_BACKLOG.md`). Source class: owner request on an
`UNVERIFIED` spec (see the backlog header; the PDF is not in the repository, so only the backlog's quotes of §10 / §13 / Appendix B are
used). Decision `DEC-SCOPE-259`, migration `0181_enrollment_confirmation`, API §12FL, RBAC §2.173. Depends on ccrm-015
(`application_outcomes`, DEC-SCOPE-244, PR #306) and ccrm-026 (visa lifecycle, DEC-SCOPE-254, PR #316), both merged.

## 1. Requirement (backlog)

- The counselor records: pre-enrolment checklist complete, enrolment confirmation (**document required**), university student number,
  course start date. **Enrolled only after confirmation** -- reaching `enrolled` without it → 422.
- Separate outcomes **Deferred (post-visa), Non-arrival, Cancelled**, so reports stay accurate.
- Acceptance: Appendix B final row (the student enrols); the management funnel counts enrolments only with confirmation.
- Regression: tel-018 conversion sweep (Converted relies on `enrolled`), management revenue.

No owner questions were asked in this session; the defaults below are recorded as `NEEDS_CONFIRMATION` in `DEC-SCOPE-259`.

## 2. Existing behaviour (verified on main @ 6941d5dc)

- Three counselor/admin routes write `enrolled` with nothing recorded: the generic `PATCH /overseas/applications/{id}` (counselor on
  direct, university rep, Overseas Admin), `POST …/advance` (counselor, direct only) and `POST …/sub-status` with `enrolled`
  (counselor direct; Admin any). The AGT-003 commission trigger runs on each.
- The agency Master's `PUT /agent/applications/{id}/enrollment` (AGN-013, DEC-SCOPE-054) is the only confirmation: from an offer onwards,
  `expected_status` against a stale screen, sets `enrollment_date`, `university_student_id`, `enrollment_confirmed_at`, one history row,
  the commission trigger. No document.
- `course_start_date` exists (ccrm-013, edited through `…/details`).
- Outcomes (ccrm-015): `deferred` already continues the application at any stage, visa stages included; `record` refuses an enrolled one.
- Funnel stage `enrollment`: "first move to enrolled recorded in the period" -- any history row, confirmed or not.

## 3. Decisions (defaults, `NEEDS_CONFIRMATION`)

| ID | Question | Default |
| --- | --- | --- |
| E1 | Who confirms, on which applications | Counselor (own applications, **direct and agency**: CC4) and Overseas Admin (any), through a new `PUT …/enrollment`. The agency Master's AGN-013 route stays as it is. |
| E2 | What confirming needs | From an offer onwards (AGN-013 E6), not on hold / closed / archived agency; `expected_status` (stale → 409); `enrollment_date`; an "Enrolment confirmation" document of this application; `pre_enrollment_checklist_complete = true`. `university_student_id`, `course_start_date`, a note: optional. |
| E3 | Other ways into `enrolled` | `PATCH` status, `/advance` and `/sub-status` to `enrolled` → **422** for every role ("Confirm enrolment with the confirmation document"). Existing 403s for a counselor on an agency application keep their order. |
| E4 | What "confirmed" means for reports | `enrollment_confirmed_at IS NOT NULL` -- set by this route and by the agency route. The funnel's `enrollment` stage additionally requires it. Old unconfirmed `enrolled` rows are **not backfilled** and drop out of that funnel stage. |
| E5 | Deferred (post-visa) | The existing `deferred` outcome (it already works at visa stages and continues the application). No new value. |
| E6 | Non-arrival, Cancelled | Two new ccrm-015 outcomes `non_arrival`, `cancelled`: **terminal** (Overseas Admin reopens), reason required, only once there is an offer (the `offer_declined` rule), refused once enrolled (unchanged rule). |
| E7 | Once enrolled | The same route corrects the date, student number, course start date and document (audit row only, no history row, no commission -- the AGN-013 precedent); an unchanged save writes nothing. |
| E8 | Pre-enrolment checklist | A counselor attestation stored as a boolean; no ccrm-018 template kind exists for it. |
| E9 | Commission on an agency application | Confirming by the counselor/Admin runs the AGT-003 trigger (at most one commission) and tells the agency (CC5), as the agency route does. |

## 4. Design

**DB (`0181_enrollment_confirmation`).** `overseas_applications.enrollment_document_id` (FK `student_documents`, `ON DELETE SET NULL`,
`use_alter` like `offer_document_id`), `pre_enrollment_checklist_complete BOOLEAN NOT NULL DEFAULT false`. The three outcome CHECKs
(`ck_overseas_applications_outcome`, `ck_application_outcomes_outcome`, `ck_application_status_history_outcome`) are recreated with the
two new values. No data is changed.

**API (`api/application_offers.py`, the post-offer router: `_writable`, `_letters`, `_upload` reused).**
- `GET …/{id}/enrollment` -- readers as the deposit: `{enrollment, documents}`; the document picker goes to writers only.
- `POST …/{id}/enrollment-documents` -- upload an "Enrolment confirmation" document (offer letter rules; allowed on hold).
- `PUT …/{id}/enrollment` -- body `ApplicationEnrollmentSave`. Confirm: stage → `enrolled` (sub-status `enrolled` by the validator),
  `enrollment_confirmed_at`, history row "Enrolment confirmed", commission trigger, student + agency told, audit. Correct: audit only.
- `POST …/outcome` accepts `non_arrival` / `cancelled` (reason required).

**Gate (`api/workflows.py`).** One constant `CONFIRM_ENROLLMENT` and a 422 in PATCH / `/advance` / `/sub-status`.

**Funnel.** `_first_moved(("enrolled",), …)` joined with `enrollment_confirmed_at IS NOT NULL`; definition text updated.

**Web.** `lib/applicationEnrollment.ts` (types, URLs); `ApplicationEnrollmentPanel` on the counselor card (load / empty / error states,
pick or upload the document, checkbox, an explicit confirm step, focus on errors); `Advance to` and the sub-status list stop at status
tracking for every card; the "Enrollment is confirmed by the agency" line goes. `lib/applicationOutcome.ts` gains the two outcomes
(offer-stage only, terminal). The agency enrolment view's "Confirmed by the agency" reads "Confirmed".

## 5. Acceptance criteria (tests)

1. PUT confirms an offer-stage application with document + checklist → `enrolled`, `enrollment_confirmed_at`, fields saved, one history row.
2. Missing document / checklist false / document of another application or another type → 422; before an offer → 422; stale → 409; on hold → 409.
3. PATCH, `/advance`, `/sub-status` to `enrolled` → 422 (no history row).
4. A counselor confirms an agency application → one commission; a repeat from the same (now stale) screen → 409; another counselor's application → 403 (the `_assigned_application` scope).
5. Once enrolled, a correction changes fields with no new history row.
6. `non_arrival` / `cancelled` need a reason and an offer; they close the application; an enrolled one → 409.
7. Funnel `enrollment` counts a confirmed enrolment and not an unconfirmed legacy one.
8. Migration: model and migration CHECK values match; upgrade/downgrade.
9. Web: the panel confirms, shows refusals, and the card no longer offers `enrolled` in Advance or sub-status.

## 6. Regression risks

- Tests that drove `enrolled` through the three gated routes are updated to the new route or to assert the 422 (behaviour change by
  requirement, not to make a test pass).
- tel-018 Converted keys on `status = 'enrolled'`, still written by the confirmation; unaffected.
- Management metrics other than the funnel still count `status = 'enrolled'` (follow-up: ccrm-034 report definitions).
