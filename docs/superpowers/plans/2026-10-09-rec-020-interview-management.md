# rec-020 — Interview management (plan)

Spec: `docs/superpowers/specs/2026-10-09-rec-020-interview-management-design.md` (DEC-SCOPE-139, IV1–IV12). TDD per task: write the
failing test, run it (RED), implement the minimum (GREEN), then refactor and re-run.

1. **Model + migration `0124`.** `Interview` gains `interview_code`, `round`, `status`, `interviewer`, `location`, `contact_id`,
   `created_by_user_id` + CHECKs. Add `InterviewEvent` and `interview_code_seq`; backfill codes and statuses. Test:
   `test_rec_020_migration.py` (the CHECKs equal the model, the head, the backfill, the downgrade refusal).
2. **Service `services/interviews.py`.** The catalogues, `check_time` (reused from rec-028), the clash check (candidate lock), `create`,
   `create_legacy`, `update`, `reschedule`, `change_status` and the side effects (rec-017 `follow`, rec-005 `interview_scheduled`). Also
   the notifications (in-app for students, `recruiter_messages` email for external candidates and the contact), the lists and the item
   output.
3. **Recruiter routes `api/recruiter_interviews.py`** + schemas `RecInterviewCreate/Update/Reschedule/StatusChange`. Test:
   `test_rec_020_interviews.py`.
4. **Legacy delegation.** `workflows.py` POST/PATCH and `employer.py` POST go through the service. Run EMP-004, EMP-005, ADM-007 and
   ADM-008 plus a new legacy test (code, event, clash, reschedule event).
5. **Web lib `lib/recruiterInterviews.ts`** with its vitest.
6. **Components.** `RecruiterInterviewForm` (schedule/edit), `RecruiterInterviewItem` (status, reschedule, history),
   `RecruiterApplicationInterviews` (the section on the candidate row) and `RecruiterInterviewsPanel` + `/recruiter/interviews` page + nav.
   vitest for each.
7. **e2e** `rec-020-interviews.spec.ts`.
8. **Docs.** DEC-SCOPE-139 in the register, API_CONTRACT §12BG, DATA_MODEL, RBAC_MATRIX §2.65, SCREEN_CATALOG and the backlog status.

Focused test set (lite): `test_rec_020_*`, `test_emp_004*`, `test_emp_005*`, `test_adm_007*`, `test_adm_008*`, `test_rec_017*`,
`test_rec_005_pipeline.py`, `test_rec_026*`, plus the route-inventory/RBAC tests that enumerate routes.
