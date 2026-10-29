# nehn-017 HR student access — implementation plan

Spec: `docs/superpowers/specs/2026-10-28-nehn-017-hr-student-access-design.md`. TDD per task: RED (pytest/vitest fails for the expected
reason), GREEN, refactor. Focused tests only; the full regression runs in its own session.

| # | Task | Files | Test first |
|---|---|---|---|
| 1 | Catalogue + default grants (H3) and the seed migration 0219 | `core/rbac.py`, `alembic/versions/0219_hr_student_grants.py` | `tests/test_nehn_017_hr_student_access.py::test_catalogue_and_defaults`, migration SEED == DEFAULT_GRANTS |
| 2 | Population helper (H1) and the Candidate Database section reading it | `services/hr_students.py`, `services/portal.py` | population includes active and excludes withdrawn and overseas students; the existing portal candidate tests |
| 3 | HR scope in training reports + the three HR reports | `services/reports/training.py` | catalogue for HR lists exactly the 3; rows are population only; CSV header has no payment, fee or discount; a trainer/admin regression (nehn-010 suite) |
| 4 | HR student API (list, detail, document download + audit) | `api/hr_students.py`, `main.py` router | the AC1/AC2/AC4/AC5 cases |
| 5 | Remove the HR `reports` exclusion | `services/portal.py` | HR `GET /portal/it/hr/reports` returns the Placement Reports payload |
| 6 | Web: nav, report library page, students list + detail pages, download button | `lib/navigation.ts`, `app/it/hr/...`, `components/HrStudent*.tsx`, `lib/hrStudents.ts` | vitest for the download button and the nav tag; Playwright e2e `nehn-017-hr-students.spec.ts` |
| 7 | Docs: decision register DEC-SCOPE-310, API §12HH, RBAC §2.221, tracker row, backlog status | `docs/...` | — |

Order: 1 → 2 → 3 → 4 → 5 → 6 → 7. Each backend task is verified in the isolated `nehn017` Docker stack (ports 18217/13217).
