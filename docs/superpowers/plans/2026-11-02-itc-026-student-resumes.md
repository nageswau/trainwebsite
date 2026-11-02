# itc-026 implementation plan

Spec: `docs/superpowers/specs/2026-11-02-itc-026-student-resumes-design.md` (DEC-SCOPE-350).

1. **Models + migration** — `StudentResume`, `StudentResumeSetting` in `models.py`; `0235_student_resumes.py`.
   Test first: `tests/test_itc_026_migration.py` (chain, single head, round trip, CHECKs, downgrade guard).
2. **Service** `services/student_resumes.py` — `read_upload` (size, sniff PDF/OLE2/DOCX, limit), `max_bytes`, `store/discard`,
   `create_version` (lock student row, max+1), `list_out`, `download` (audit committed first), `scope` helpers per portal, settings
   read/save. Test first: `tests/test_itc_026_student_resumes.py` covering AC1–AC7 and the R8 matrix.
3. **Router** `api/student_resumes.py` — me / counselor / admin / hr routers and `/admin/it/resume-settings`; register in `main.py`.
4. **Frontend** — `lib/studentResumes.ts`, `components/StudentResumeCard.tsx`, `components/ResumeLimitPanel.tsx`; mount in
   `WorkflowPanel` (student profile, IT Admin students), `ItStudentProfilePage`, `HrStudentPage`. Vitest:
   `tests/components/StudentResumeCard.test.tsx`.
5. **Playwright** `tests/e2e/itc-026-student-resumes.spec.ts` — student uploads, counselor uploads v2, HR downloads, bad file refused.
6. **Docs** — DEC-SCOPE-350 register entry, API_CONTRACT §12IV, RBAC_MATRIX §2.250, backlog status line.
