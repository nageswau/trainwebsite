# rec-012 — Resume text + rule-based skill extraction (plan)

Spec: `docs/superpowers/specs/2026-10-09-rec-012-resume-extraction-design.md`. Branch `feature/rec-012`. Each task uses TDD (red, then
green, then refactor) and runs only the focused tests.

1. **Dependencies.** Pin `pypdf` and `python-docx` in `requirements.txt` and rebuild the api image.
2. **Pure extractor.** Add `services/resume_extract.py`.
   - `test_rec_012_resume_extract.py`: AC1 sentence, plurals, longest match, stop words and casing, DOCX with tables, "3 years",
     scanned PDF → no text, encrypted PDF, corrupt file, the zip guard, the page and character caps, qualification, location, titles,
     certifications, industry.
3. **Data.** Add three columns to `CandidateResume` and migration `0135_resume_extraction`.
   - `test_rec_012_migration.py`: the columns, single head, an upgrade that keeps existing resume rows.
4. **Schemas and API.** Add `ResumeApply` (+ labels), the routes `POST …/resume/{v}/extract` and `…/apply` in `api/recruiter_candidates.py`,
   and the glue in `services/resume_extraction.py` (terms query, thread and timeout, output, apply).
   - `test_rec_012_resume_extraction_api.py`: extract stores the text and changes nothing else (AC2), the response shape and `on_profile`,
     no text (AC3), encrypted 422, apply skills and fields, all or nothing, 409 duplicate, 422 unknown, duplicate ids or empty, 409 not
     extracted, roles (hr_team 403), pool 404, archived 409.
5. **Web.** Add `lib/recruiterResumeExtract.ts` and `RecruiterResumeExtraction`; wire them into `RecruiterCandidateResumes` and
   `RecruiterCandidateDetail` (reload the candidate and the Skills card after Apply).
   - vitest for the lib and the panel.
6. **e2e.** Add `rec-012-resume-extraction.spec.ts`.
7. **Docs.** API_CONTRACT §12BR, RBAC_MATRIX §2.76, DATA_MODEL, DEC-SCOPE-150, the backlog status, SCREEN_CATALOG.
8. **Checks.** Lite backend (rec-009, rec-011, rec-012), vitest, tsc, eslint, next build, then e2e and browser QA.
