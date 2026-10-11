# rec-038 — Exploratory QA (2026-10-11)

**Stack:** isolated Docker Compose project `rec038` (`localhost:13038` web, `127.0.0.1:18038` api), seeded demo accounts. Browser:
Playwright Chromium. Independent pass first (roles × 9 recruiter pages × 1366 / 820 / 390 px), no code changed during it.

rec-038 adds no screen (RM7), so the pass checks the recruiter CRM's access rules as the browser shows them. Forms, duplicate submission,
success messages and cancel/back belong to the owning items and are unchanged here (N/A).

| ID | Role | Page / route | Check | Result |
|---|---|---|---|---|
| QA-01 | recruiter (`placement@`) | dashboard, companies, candidates, requirements, pipeline, interviews, follow-ups, performance | reads its workspace | all render; Team (`/recruiter/manager/team`) "Access unavailable" ✓ |
| QA-02 | placement manager, super_admin | the 9 pages | full workspace | all render ✓ |
| QA-03 | college BDM (assigned) | companies, requirements, pipeline, interviews, follow-ups | read only (R10) | render; dashboard, candidates, Team and performance refused ✓. Company page: none of Edit, Archive, Add contact, Log call, Add follow-up, Schedule meeting, Start contract (super_admin sees all seven on the same company) ✓ |
| QA-04 | hr_team | the 9 pages | pool read only (R11, Q-28) | candidates render with "You can view candidates and download resumes." and no "+ Add candidate"; the other 8 refused ✓ |
| QA-05 | it_admin, overseas_admin, IT student | the 9 pages | refused | "Access unavailable" + "Go to your dashboard" on every page ✓ |
| QA-06 | signed out | the 9 pages | sign-in | redirect to `/it/login` (Team to `/admin/login`) ✓ |
| QA-07 | recruiter | another recruiter's company by URL | out of scope = missing (RM4) | "Company not found" ✓ |
| QA-08 | every role | layout at 1366 / 820 / 390 | page side-scroll; broken images | overflow 0 everywhere; no broken images ✓ |
| QA-09 | every role | console / network | unexpected errors | no 5xx. Aborted `?_rsc=` requests are Next prefetches cancelled by navigation. See QA-10 |
| QA-10 | college BDM | companies list | console | two `403`s: the list's filter pickers read the lead-source and industry catalogues, which §2.43 refuses to a BDM. The list still renders. Pre-existing (rec-003 QA-04 UI), not rec-038; noted, not changed |
| QA-11 | assigned BDM, hr_team | `GET /recruiter/messages/render` | templates refused (§2.61) | **defect, fixed (RM6)**: `200` with the template's name and text before; `403` after (`test_render_refuses_a_role_that_cannot_read_templates`, matrix row) |
| QA-12 | super_admin, it_admin | `GET /recruiter/performance[.csv]` | all recruiters | on the long-lived test database (≈3,600 recruiters) the read failed `500` (the 32,767-parameter limit: rec-033 binds every recruiter id per figure). Passes on a fresh database. Pre-existing rec-033/034/035 design, not rec-038: follow-up recorded in RBAC §2.111 |

**Defects in scope:** QA-11, fixed. **Known, not rec-038:** QA-10, QA-12; `rec-026-messages.spec.ts`'s email step needs SMTP, which this
isolated stack's `.env` (from `.env.example`) does not configure ("Email is not set up"). Its WhatsApp step, which uses the render route,
passes.

**Automated:** `test_rec_038_matrix.py` 173 passed in 80 s on a fresh database (170 rows + inventory + 2 render cases); the inventory test
fails when a row is removed (AC2, checked by hand); rec-026/027 API suites 45 passed; e2e `rec-038-recruiter-access.spec.ts` 7 passed.
