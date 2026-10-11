# rec-029 — Campus recruitment drives (design)

- **Feature:** `rec-029` (`docs/delivery/RECRUITER_CRM_BACKLOG.md` §rec-029). **Dependencies:** rec-007 (PR #166) and rec-017 (PR #178),
  both merged. rec-017 A4 moved `job_applications.drive_id` to this item, so it is added here.
- **Evidence:** `EVID-018` §21 (lines 838–886): Drive ID, College, Company, Date, Job Role, Vacancies, Eligibility, Students Registered,
  Students Attended, Shortlisted, Interviewed, Selected, Joined; the ABC College + XYZ Technologies funnel example (illustrative only).
  Appendix B C1–C7 defines every figure. R15 (`EXPLICIT_APPROVAL`, 2026-10-07): college = BDM college org or free text; registered and
  attended typed; shortlisted → joined computed from drive-tagged applications.
- **Decision:** `DEC-SCOPE-177`. DR1–DR10 are **recommended defaults** taken on the owner's standing instruction ("proceed with the
  recommended answers; ask only if blocking"). They stay `UNVERIFIED` until the owner confirms them. DR3 answers Q-30.
- **Numbering (FINAL unless main moves):** migration `0148_recruitment_drives`, API §12CR, RBAC §2.103. Drafted as `0146` / 175 / §12CP / §2.101, then `0147` / 176 / §12CQ / §2.102; rec-021 and then rec-031 merged first and took those numbers.

## 1. Decisions (UNVERIFIED defaults)

| # | Point | Answer |
|---|---|---|
| DR1 | Drive ID | `DRV-000001` from the sequence `recruitment_drive_code_seq`, unique, server-owned |
| DR2 | College | Exactly one of `college_org_id` (a non-archived BDM organisation of type `college` or `university`) or `college_name` (free text ≤ 200). Both or neither → `422` on `college_org_id`. A picked org later archived stays shown |
| DR3 | Q-30 | **One drive per application** (`job_applications.drive_id`, a single nullable FK). The tag is set when a candidate is added through the drive and never changes. A candidate already on the requirement is the existing `409` (no re-tagging). A drive is **closed by hand**: `status` `planned` → `completed` or `cancelled`, set by PATCH; `completed` ↔ `planned` allowed, `cancelled` is final. A cancelled drive takes no edits and no candidates (`409`) |
| DR4 | Requirements | 1–10 requirements, each a requirement **of the drive's company**, not closed/cancelled when added (`422` on `requirement_ids`). PATCH replaces the set; removing one that has drive-tagged applications → `409`. The company never changes after create |
| DR5 | Fields | `drive_date` (date, required), `job_role` (≤ 150, required), `vacancies` (1–100000, required), `eligibility` (≤ 1000, optional), `students_registered` / `students_attended` (0–1000000, default 0) |
| DR6 | AC2 | `students_attended ≤ students_registered`, checked on the merged values (PATCH of one side too) → `422` on `students_attended`; a DB CHECK backs it |
| DR7 | Funnel (C4–C7) | Over the drive's tagged applications, in **one query**: **Shortlisted** = current status or any history status in shortlisted/profile_shared/interview/selected/joined; **Interviewed** = ≥ 1 interview in completed/selected/rejected; **Selected** = reached selected or joined; **Joined** = status joined. Also `tagged` (all tagged applications) |
| DR8 | Who | Scope = the drive's company (rec-003 `caller_scope`): recruiter own companies, manager team + unassigned, `super_admin` all, assigned BDM of the company read. Writes = the company's `can_edit` (assigned recruiter, `super_admin`); manager/BDM read only (`403`); archived company `409`. Out of scope = `404`. **The college's BDM gets no access** (Q-30 "read?" → no, not in this item). Other roles `403` |
| DR9 | Adding candidates | `POST /recruiter/requirements/{id}/candidates` gains optional `drive_id`. The drive must be in scope, not cancelled and include this requirement (`422` on `drive_id`); everything else is rec-017's add (pool candidate, duplicate `409`, requirement ended `409`) |
| DR10 | Audit/log | Create/update audit rows (`recruitment_drive.create/update`, field names only); logs carry ids only |

## 2. Data (`0147`)

- `recruitment_drives`: `id`, `drive_code` (unique), `company_id` (FK), `college_org_id` (FK `bdm_organizations`, nullable), `college_name`
  (nullable), `drive_date`, `job_role`, `vacancies`, `eligibility`, `students_registered`, `students_attended`, `status` (CHECK 3),
  `created_by_user_id`, `created_at`, `updated_at`. CHECKs: exactly one college; counts ≥ 0; attended ≤ registered; vacancies ≥ 1.
  Indexes `(company_id, drive_date)`, `(drive_date)`.
- `drive_requirements`: `drive_id`, `job_id`, PK both; index `job_id`.
- `job_applications.drive_id` nullable FK + index. Additive; no backfill. Every FK RESTRICT. `downgrade()` refuses while a drive exists.

## 3. API (§12CR)

| Method/Path | Notes |
|---|---|
| `GET /recruiter/drives?q&status&limit&offset` | Scoped list `{items, total, limit, offset, can_create}`, newest drive date first. `q` matches code, job role, college, company |
| `GET /recruiter/drives/college-options?q&limit` | Non-archived BDM college/university orgs: id, code, name, city. For creators |
| `POST /recruiter/drives` | `{company_id, college_org_id?, college_name?, requirement_ids[], drive_date, job_role, vacancies, eligibility?, students_registered?, students_attended?}` → `201` detail |
| `GET /recruiter/drives/{id}` | Detail: fields, college, company, requirements, funnel, permissions |
| `PATCH /recruiter/drives/{id}` | Partial; DR3/DR4/DR6 |
| `GET /recruiter/drives/{id}/funnel` | DR7 |
| `GET /recruiter/drives/{id}/candidates` | Tagged applications: candidate name/code, requirement, status label |

## 4. Web

- `/recruiter/drives` (nav "Campus Drives" for recruiter, manager, super_admin): list cards with code, college, company, date, role,
  registered/attended; "+ New drive" inline form (company picker → requirement pickers of that company, college picker or free text).
- `/recruiter/drives/[id]`: details + Edit form, funnel (registered → attended → shortlisted → interviewed → selected → joined as a
  list), requirements, tagged candidates, and per requirement "Add candidate" (reuses rec-017's `AddCandidate` with the drive id).
- Loading / empty / error / 403 / not found states follow the pools and meetings pages.

## 5. Tests

- `test_rec_029_migration.py`: tables, CHECKs, `drive_id` column.
- `test_rec_029_drives.py`: create (org / free text / both / neither), requirement of another company, AC2 (create + PATCH one side),
  list scope (other recruiter 404, manager read, BDM read, hr_team 403), writes refused for manager, funnel equals counts (AC1, the
  source example shape), add candidate with drive tag (wrong requirement 422, cancelled 409), removal of a requirement with tagged
  applications 409, funnel statement count = 1.
- Vitest for the lib helpers and the list/detail components; Playwright `rec-029-drives.spec.ts` happy path.
