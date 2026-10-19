# csc-003 — Resend link and fix pending details (plan)

Spec: `docs/superpowers/specs/2026-10-19-csc-003-walk-in-resend-and-edit-design.md`. TDD per task.

| # | Task | Test first | Files |
| --- | --- | --- | --- |
| 1 | `CounselorStudentUpdate` schema | validation cases | `schemas.py` |
| 2 | Shared guard: own linked, pending, active-flag; budget counts resend + email change | 404/409/403 cases, budget case | `services/counselor_students.py` |
| 3 | `POST /counselor/students/{id}/welcome-links` | resend, cooldown, old link dead | `services/…`, `api/counselor_students.py` |
| 4 | `PATCH /counselor/students/{id}` | name/phone, email change, duplicate, case-only, empty body | same |
| 5 | Row actions | vitest `CounselorWalkInStudentRow.test.tsx`; panel test still green | `components/CounselorWalkInStudentRow.tsx`, `components/CounselorWalkInStudents.tsx` |
| 6 | Docs | — | DEC-SCOPE-228, API §12EN, RBAC §2.150, RTM, backlog |
| 7 | e2e | `csc-003-walk-in-resend-edit.spec.ts` | web e2e |

Lite regression: `test_csc_002_walk_in_students.py`, `test_csc_001_*`, `test_enh_003_first_time_provisioning.py`, `test_agn_002_staff.py`;
vitest `CounselorWalkInStudents`, `WorkflowPanel*`; e2e `csc-002`, `csc-001`, `enh-003`.

**Phase 3 review (2026-10-19).** API: PATCH (partial update, 200) and POST (creates a new link, 201) match the ENH-003 Re-send and AGN-002
edit semantics; 404 for anything not the caller's (no disclosure); 409 for state conflicts; 429 with Retry-After. Transactions: one per
request; delivery after commit; the duplicate-email refusal audits and commits before raising (csc-002 pattern); a concurrent unique
violation is caught by `flush_unique_email`. Frontend: AgentStaffRow's accessible inline-form pattern; actions hidden on active rows;
mobile wraps. Security: IDOR by link ownership; no role/flag fields; token never returned; budget covers every mail-sending action;
ids and field names only in logs/audit. No plan change.
