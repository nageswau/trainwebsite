# csc-002 — Counselor walk-in student account (plan)

Spec: `docs/superpowers/specs/2026-10-19-csc-002-counselor-walk-in-student-design.md`. TDD per task.

| # | Task | Test first | Files |
| --- | --- | --- | --- |
| 1 | Schema `CounselorStudentCreate` (extra forbid, name/email/phone rules) | `test_csc_002_walk_in_students.py` validation cases | `schemas.py` |
| 2 | `POST /counselor/students`: user + student_code + role assignment + link + token + audit, then delivery; token stripped | create, set-password-and-sign-in, no-token, role gates, mail-failure cases | `services/counselor_students.py`, `api/counselor_students.py`, `main.py` |
| 3 | Duplicate email 409 audited; throttle 20/24 h counting rejections | duplicate (case-insensitive), throttle with a lowered limit | same |
| 4 | `GET /counselor/students` paged, own links, setup status | list cases | same |
| 5 | Panel on the counselor Students section | vitest component test (render, submit, error, empty) | `components/CounselorWalkInStudents.tsx` (types inline; reuses `sendJson`, `isPage`, `staffFailure`), `WorkflowPanel.tsx` |
| 6 | Docs | — | decision register DEC-SCOPE-227, API §12EM, RBAC §2.149, RTM, backlog status |
| 7 | e2e | `csc-002-walk-in-student.spec.ts`: create → activate (admin Re-send helper) → student signs in; counselor sees "Active" and books them | web e2e |

Lite regression: `test_agn_002_staff.py`, `test_enh_003_first_time_provisioning.py`, `test_csc_001_*`, `test_enh_031_lookups_students.py`,
`test_tel_026_matrix.py`; vitest `WorkflowPanel*`; e2e `csc-001`, `cns-001`.

**Phase 3 review (2026-10-19).** API: 201/409/422/429/403/401 as specified; the response is built before the commit (the commit
expires ORM objects, AGN-002 pattern); lock order counselor row → new user → tokens (as ENH-003 Re-send). Frontend: the AGN-002 form
markup (labels, `required`, `type=email`, `maxLength`, aria-live result focused after submit), loading / error-with-Retry / empty
states, no new dependency. Security: server-set role/flags + `extra="forbid"`; raw token never returned; throttle C2; ids-only
logs and audit; email template already escapes names (ENH-003 tests) and labels the role "Overseas Student". No plan change.
