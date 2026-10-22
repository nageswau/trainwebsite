# ccrm-010 — Student notes: implementation plan

Design: `docs/superpowers/specs/2026-10-22-ccrm-010-student-notes-design.md`. Branch `feature/ccrm-010` (worktree
`.claude/worktrees/ccrm-010`), cut from `origin/main` @ `50254ccc`.

1. **Migration + model (TDD).** `test_ccrm_010_migration.py` (chain, single head, model = table, round trip, downgrade refusal) → RED;
   `OverseasStudentNote` in `models.py` + `0166_overseas_student_notes.py` → GREEN.
2. **Service + routes (TDD).** `test_ccrm_010_student_notes.py` (scope, roles, validation, application link, paging, history after
   reassign) → RED; `services/student_notes.py`, `StudentNoteCreate` in `schemas.py`, `GET/POST /counselor/students/{id}/notes` in
   `api/counselor_students.py` → GREEN.
3. **Entry points (TDD).** Portal tests (students section, admin users directory, other sections unchanged) → RED; `student_notes` column
   in `services/portal.py` → GREEN.
4. **Frontend (TDD).** Vitest for `StudentNotesPanel` and the DataTable `student_notes` cell → RED; `lib/studentNotes.ts`,
   `StudentNotesPanel.tsx`, `StudentNotesPage.tsx`, two route pages, DataTable cell, walk-in row link → GREEN. tsc + eslint.
5. **e2e.** `ccrm-010-student-notes.spec.ts`: counselor writes a note on a walk-in student; the admin reads it.
6. **Docs.** API_CONTRACT 12ET, RBAC_MATRIX 2.156, DEC-SCOPE-241, backlog status line, RTM entry.

Lite backend set: the two new files + `test_csc_001_migration.py`, `test_csc_002*`, `test_csc_005*`, `test_agn_023_filters.py`,
`test_agn_023_final_review.py`.
