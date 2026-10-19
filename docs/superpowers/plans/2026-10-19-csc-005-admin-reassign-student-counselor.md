# csc-005 — Admin reassigns a student's counselor (plan)

Spec: `docs/superpowers/specs/2026-10-19-csc-005-admin-reassign-student-counselor-design.md`. TDD per task.

| # | Task | Test first | Files |
| --- | --- | --- | --- |
| 1 | `assign_counselor` service + `PUT /admin/users/{id}/counselor` | reassign / first assign / no-op / 422 / 404 / 403 / 401 / scope-after cases | `services/counselor_students.py`, `api/counselor_students.py`, `main.py` |
| 2 | Students section: counsellor column + `assign_student_counselor` (Overseas Admin) | portal section test | `services/portal.py` |
| 3 | Web: `AssignCounselorButton` `url` prop; DataTable column type | vitest | `components/AssignCounselorButton.tsx`, `components/DataTable.tsx` |
| 4 | Docs | — | DEC-SCOPE-230, API §12EP, RBAC §2.152, RTM, backlog |
| 5 | e2e | `csc-005-reassign-student-counselor.spec.ts` | web e2e |

Lite regression: `test_csc_001_*`, `test_csc_002_*`, `test_csc_003_*`, `test_agn_023_*`, `test_enh_003_first_time_provisioning.py`;
vitest `AssignCounselorButton`, `DataTable`; e2e `agn-023`, `csc-002`.

**Phase 3 review (2026-10-19).** API: PUT is idempotent by design (`changed:false` for the same counselor), 403/404/422 as AGN-023;
one transaction with the student row locked, notifications queued in it (sent after commit by the dispatcher). Frontend: one shared
picker (no new component), server-declared column like AGN-023, no change for other sections. Security: role + division gate, target
must be an overseas student (no reassigning staff), counselor validated, audit from/to ids only. No plan change.
