# rec-037 — Exploratory QA (2026-10-11)

**Stack:** isolated Docker Compose project `rec037` (`localhost:13237` web, `127.0.0.1:18237` api), seeded demo data plus QA fixtures
(Nisha's team: Kiran with 12 live + 1 archived company, 3 requirements of which 1 closed, 1 open + 1 done follow-up; Meera active, Ravi
inactive; outsider manager Omar with Zara). Browser: Playwright Chromium. Independent pass first; no code changed during it.

| ID | Role | Page / route | Check | Result |
|---|---|---|---|---|
| QA-14 | signed out | `/recruiter/manager/team` | redirect | `/admin/login?next=%2Frecruiter%2Fmanager%2Fteam` ✓ |
| QA-02 | super_admin | `/admin/recruiter-staff` Deactivate Kiran | 422 sentence shown | "This recruiter has 12 companies and 2 open requirements. A placement manager must reassign them (Team page) before deactivation." ✓ |
| QA-01 | placement_manager | Team | counts per row; Reassign only with work | Kiran 13 / 3 / 1; no button for Meera (0) or Ravi (inactive, 0) ✓ |
| QA-03 | placement_manager | Team → Reassign | text, focus, disabled until pick, Escape | "Kiran Placement has 13 companies, 3 requirements and 1 open follow-up."; focus to the group; Escape returns focus to the button ✓ |
| QA-04 | placement_manager | picker | options | only Meera (not Kiran, inactive Ravi, outsider Zara) ✓ |
| QA-05 | placement_manager | injected 500 / network abort | error wording + focus | plain words on 500, the standard connection message on abort; the error takes focus ✓ |
| QA-06 | placement_manager | double click Reassign | duplicate submission | one POST ✓ |
| QA-07 | placement_manager | happy path, refresh, reload | notice + moved counts | "Moved to Meera QA Recruiter: 13 companies, 3 requirements and 1 open follow-up."; Meera 13 / 3 / 1, Kiran 0 / 0 / 0 after reload ✓ |
| QA-08 | placement_manager | stale second POST | 409 | "This recruiter has no companies or requirements to reassign" ✓ |
| QA-09 | placement_team (Kiran) | company read; Team page | access lost; wrong role | company `404`; Team page "Access unavailable — Placement manager role required" ✓ |
| QA-10 | it_admin; other manager | POST reassign | 403 | `403` / `403` "This recruiter is not in your team" ✓ |
| QA-11 | super_admin | Deactivate Kiran again | succeeds | Reactivate shown (then reactivated to restore the demo account) ✓ |
| QA-12 | placement_manager | Team at 1366 / 820 / 375 | no page side-scroll; group usable | overflow 0 at all three; below 640 px rows become labelled cards ✓ |
| QA-13 | — | console / network | unexpected errors | only the resource errors of the deliberate 422 / 500 / abort; aborted `?_rsc=` requests are Next prefetches ✓ |
| QA-15 | — | images | broken | none ✓ |

**Defects in scope:** none. **Known, not rec-037:** `RecruiterCompanies.test.tsx` "archives after confirming" (the rec-030 contracts
fetch) and `test_rec_006_migration` round trip (downgrade blocked by later FKs) fail on main too.

**Automated:** `test_rec_037_reassign.py` 18 passed; affected API suites (rec-001…007, rec-024, tel-025, upc-032, bdm-025, adm-001) 383
passed + the pre-existing rec-006 migration failure; web `RecruiterReassign.test.tsx` + `RecruiterTeamTable.test.tsx` 8 passed; e2e
`rec-037-recruiter-reassign.spec.ts` 2 passed and `rec-001-recruiter-roles.spec.ts` 4 passed.
