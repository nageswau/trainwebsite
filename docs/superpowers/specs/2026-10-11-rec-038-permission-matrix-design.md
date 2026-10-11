# rec-038 — Recruiter CRM permission matrix + cross-role 403/404 sweep (design)

Date: 2026-10-11 · Backlog: `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-038 · Source: R2, R10, R11, R12 together; "with appropriate
permissions" (S2-§12). Precedents: tel-026 (`DEC-SCOPE-115`, `test_tel_026_matrix.py`) and upc-033 (`DEC-SCOPE-174`, `test_upc_033_matrix.py`).
Dependencies: rec-001 … rec-037, each merged to `main` through its own pull request (checked at `9b5b7369`).
Numbering: `DEC-SCOPE-185`, RBAC §2.111. No migration, no API contract section, no frontend change.

## 1. What the item asks for

1. RBAC_MATRIX rows for every recruiter route.
2. A route-inventory test with one row per route (the tel-026 idiom) asserting `403` for roles with no access, `404` out of scope, the
   employer and student exclusions, and BDM read-only.

Acceptance criteria: (AC1) every `/recruiter/*` route is in the inventory; (AC2) the test fails on an unlisted route. Backend: tests only.

## 2. Decisions (recommended answers, applied under the owner's standing build-session instruction; `NEEDS_CONFIRMATION` at sign-off)

| # | Point | Decision |
|---|---|---|
| RM1 | Which routes are inventoried | Every operation under `/recruiter/`, plus the recruiter-owned operations outside it: `/admin/recruiters` and `/admin/placement-managers` (rec-001 pickers), `/admin/programs/skill-options` and `/admin/programs/{id}/skills` (rec-036), `/account/placement-pool*` (rec-010 consent), `/workflows/it/student/offers*` (rec-022), `/employer/shared-profiles*` and `/public/shared-resume/{token}` (rec-019). 170 operations at `9b5b7369`. The test reads `app.openapi()` and fails on a route without a row **or** a row without a route. Shared legacy routes the items extended (`/workflows/it/*`, `/employer/jobs`, `PATCH /admin/users/{id}`) keep their own tests. |
| RM2 | Roles called | `anon`; `rec` (recruiter with a profile, assigned to the world's company and requirement, reporting to `mgr`) and `rec_out` (a recruiter of another manager); `mgr` and `mgr_out` (`placement_manager`); `super`; `it_admin`; `ovs_admin`; `hr` (`hr_team`, Q-28); `bdm` (the company's assigned BDM, R10) and `bdm_out`; `employer` (the company's employer user, R12); `student` (an opted-in IT student, R4). |
| RM3 | A cell's expected status | The owning item's as-built, owner-approved rule (RBAC §2.42–§2.110, checked against the code). Unlisted signed-in roles are `403`, anonymous `401`. A surprising cell is checked against code **and** docs before it is written, and is never adjusted just to pass. |
| RM4 | 403 vs 404 | Role first: a role with no access is `403` before any lookup. Scope second: a record outside the caller's scope reads as missing (`404`, `load_scoped`), so another team's company, requirement or their children never confirm that they exist. |
| RM5 | Worlds | One world per row for refused cells and every `GET` cell; each non-`GET` 2xx cell runs on its own fresh world. Users are inserted directly with a minted session cookie; records are inserted directly with the fields their items' tests use. Four row modules (profile/companies, candidates/requirements, hiring, activity) keep each group's rows next to the records they need. |
| RM6 | A gap found by the sweep | Fixed inside rec-038 only when it breaks the documented rule and the fix is local (tel-026 PM4, upc-033 PX7). Otherwise recorded in RBAC §2.111 as `NEEDS_CONFIRMATION`. |
| RM7 | Frontend | None (backlog). Browser QA checks the UI as built: recruiter pages refuse the other roles, and the BDM's view is read-only. A Playwright spec records that check. |

## 3. Design

- `apps/api/tests/rec038_helpers.py`: `ROLES`, `Row` / `R` / `allow`, `core(client, db)` (users and the core records).
- `apps/api/tests/rec038_rows_{profile,candidates,hiring,activity}.py`: each group's `ROWS`, `PATH_VALUES` and `build(client, db, w)`.
- `apps/api/tests/test_rec_038_matrix.py`: the inventory test (AC1/AC2) and the per-row cell test.
- Docs: RBAC §2.111, `DEC-SCOPE-185`, the backlog status line, this spec.

## 4. Risks

Tests only apart from RM6, so the risk sits in the shared test database (every value is unique per call and nothing is truncated) and in
run time (170 rows × 13 roles: 80 s on a fresh database). The talent pool is made once per run: the pool list counts every active pool's
members, so a pool per world made that row grow with every run. RM6 changes only the status a non-template role gets from render (`403`
before the party's `404`).

## 5. Outcome

- 170 rows pass; the inventory test fails on a missing row (AC2).
- RM6, found by the sweep: `GET /recruiter/messages/render` did not check the template reader's role, so the assigned BDM (contact party)
  and `hr_team` (candidate party) read a template's name, kind and text. Fixed in `api/recruiter_messages.py`, as the preview does.
- As-built notes left `NEEDS_CONFIRMATION`, and the rec-033 metrics follow-up, are in RBAC §2.111. QA evidence:
  `docs/quality/REC-038_EXPLORATORY_QA_2026-10-11.md`.
