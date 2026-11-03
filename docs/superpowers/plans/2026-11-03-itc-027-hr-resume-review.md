# itc-027 plan (design: `docs/superpowers/specs/2026-11-03-itc-027-hr-resume-review-design.md`)

TDD per task: failing test first, then the code, then rerun the focused files.

1. Migration `0237_hr_review_tasks` + models + `test_itc_027_migration.py` (tables, CHECK, unique, index, downgrade).
2. `services/hr_reviews.py`: `on_resume_shared` (create/update/re-open, H2), `_pick_owner` (rule → round-robin → none, H3),
   notifications (H8); hook from `student_resumes.upload`. Tests: AC1–3.
3. HR routes: queue, read, PATCH (stage machine + history + audit + notices, H1/H6). Tests: AC4, AC6, 409 closed, 422 bad stage.
4. Audience views: counselor, admin, student (H7). Tests: AC5, no notes leak (serialized payload scan).
5. Admin: task list, reassign, rules (H3/H5). Tests: 403 for non-admin, reassign notifies, inactive owner counts as unassigned.
6. Withdrawal hooks (rec-010 opt-out, placement profile `withdrawn`), H9. Tests: AC7.
7. Web: `lib/hrReviews.ts`, `HrReviewQueue`, `HrReviewCard`, `HrReviewStatusCard` (counselor/admin), `StudentHrReviewCard`,
   `AdminHrReviews` (+ rules panel), nav + routes. Vitest for the cards; Playwright e2e for upload → queue → stage → student label.
8. Docs: DEC-SCOPE-354, API §12IZ, RBAC §2.254, RTM, backlog status.
