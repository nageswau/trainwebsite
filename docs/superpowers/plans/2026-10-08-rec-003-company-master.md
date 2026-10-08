# rec-003 implementation plan

Spec: `docs/superpowers/specs/2026-10-08-rec-003-company-master-design.md`. TDD per task: failing test first, then code.

| # | Task | Files | Tests (written first) |
|---|---|---|---|
| 1 | Schema: `Company` columns, `COMPANY_CODE_SEQ`, `CompanyAssignmentHistory`; migration `0106_rec_companies` (guarded, backfill, refusing downgrade) | `models.py`, `alembic/versions/0106_rec_companies.py` | `test_rec_003_migration.py`: round trip in a throwaway DB, backfill order, NOT NULL, downgrade refusal |
| 2 | Service: scope, permissions, duplicates, lookups (`FOR SHARE`), reassign target, output, audit | `services/recruiter_companies.py`, `schemas.py` | through task 3's API tests |
| 3 | API: list/create/get/patch/archive/restore/assign/bdm-options; router registered | `api/recruiter_companies.py`, `main.py` | `test_rec_003_companies.py` (AC1–AC4, AC6, AC7, roles, BDM read, 404s) |
| 4 | Employer registration sets lead source Website (D3) | `api/employer.py` | `test_rec_003_companies.py::employer` + existing `test_emp_001*` |
| 5 | Web lib + components + pages + nav | `lib/recruiterCompanies.ts`, `components/RecruiterCompany*.tsx`, `app/recruiter/companies/**`, `lib/navigation.ts` | `tests/components/RecruiterCompanies.test.tsx`, `navigation.recruiter.test.ts` |
| 6 | Playwright | `tests/e2e/rec-003-companies.spec.ts` | recruiter create → detail; manager reassign; mobile layout |
| 7 | Docs | DEC register (`DEC-SCOPE-121`), API_CONTRACT §12AO, RBAC §2.47, DATA_MODEL, SCREEN_CATALOG, backlog status | — |

Lite regression set: rec-001/002 tests, `test_emp_00*`, `test_adm_007_placement.py`, `test_adm_008_hr_shortlists.py`,
`test_rpt_001_reporting.py`, `test_enh_031_lookups_applications.py`, `test_bdm_021_business.py` (all create `Company` rows).
