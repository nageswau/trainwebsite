# upc-033 — Permission matrix + commission-stripping sweep (design)

Date: 2026-10-10 · Backlog: `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` upc-033 · Source: `EVID-020` line 1129 ("Commissions should
not be seen by anyone."), backlog U2, U3, U13, U14 · Precedent: tel-026 (`DEC-SCOPE-115`, `test_tel_026_matrix.py`).
Dependencies: upc-001 … upc-032, all merged to `main` (one `feature/upc-0NN` merge each, checked at `0002d078`).
Numbering: `DEC-SCOPE-174`, RBAC §2.100. No migration, no API contract section (the API is unchanged except the PX7 order fix).

## 1. What the item asks for

1. RBAC_MATRIX rows for every partnership route.
2. A route-inventory test (one row per route) asserting 403/404 per role.
3. A commission sweep: every endpoint that can return university, course, agreement or performance data is called as each
   non-commission role, and the response must contain no commission key or value. Public endpoints included.

Acceptance criteria: (AC1) every `/partnership/*` route is in the inventory; (AC2) the sweep covers every serializer that includes
commission. Frontend: none. Backend: tests only, unless the sweep finds a gap (PX7).

## 2. Decisions (recommended answers, applied under the owner's standing build-session instruction; `NEEDS_CONFIRMATION` at sign-off)

| # | Point | Decision |
|---|---|---|
| PX1 | Which routes are inventoried | Every operation under `/partnership/`, `/admin/partnership-` (upc-001 pickers) and `/universities/` (upc-030's 360 view): 127 at `0002d078`. The inventory test reads `app.openapi()` and fails on a route without a row **or** a row without a route. |
| PX2 | Roles called | `anon`; `pm` (manager, primary manager of the world's universities) and `pm_out` (manager of another head); `head` (pm's head) and `head_out`; `super`; `ovs_admin` (overseas division); `it_admin`; `bdm` (college BDM with a profile); `cns` (overseas counselor); `rep` (`university_rep` of the world's university); `agent`; `student` (overseas student). |
| PX3 | A cell's expected status | The owning item's as-built, owner-approved rule (RBAC §2.44–§2.99, checked against the code). Unlisted signed-in roles are `403`, anonymous `401`. A wrong expectation is checked against code **and** docs before it is written; never adjusted to make a cell pass. |
| PX4 | 403 vs 404 out of scope | This module refuses out-of-scope writes with `403` (upc-003 UM convention, "This university belongs to another partnership team"), and reads are not team-filtered (U14: one record for all partnership roles). `404` only where the owning item hides: another uploader's import (upc-005), another manager's target sheet (upc-021), a calendar `user_id` out of scope (upc-011), the 360 view out of slice (upc-030). |
| PX5 | Worlds | One world per row for refused cells and **all** `GET` cells (reads do not change state); every non-`GET` 2xx cell gets its own fresh world. Users are inserted directly with a minted session cookie (no bcrypt); universities, courses, agreements, terms and documents are made through their real routes so each is valid; the remaining rows are inserted directly. |
| PX6 | Commission sweep | The world plants sentinels in every commission column: course `commission_percent` and `commission_amount`, a commission term's percent and conditions, a receipt's amount, reference and note, and a `commission_agreement` document's title. Every sweep endpoint (each inventoried `GET`, plus the public catalogue, the 360 view and the other university/course reads of other roles) is called as every non-commission role (`anon`, `ovs_admin`, `it_admin`, `bdm`, `cns`, `rep`, `agent`, `student`). Whatever the status, the body must hold no key containing `commission`, no `factors` key (the health breakdown) and no sentinel. A positive control proves the sentinels are reachable: the commission roles see each one where its item says. |
| PX7 | A gap found by the sweep | Fixed inside upc-033 when it breaks the documented rule and the fix is local (tel-026 PM4). Found: `POST /partnership/universities/{id}/courses/import` (upc-017) read and parsed the upload before any role check, so a counselor got `422`/`413` instead of `403` (a validation oracle, and work done for a refused caller). Fix: `require_reader` first, as upc-005's university import does. |
| PX8 | AC2 "every serializer" | A source net: every module under `app/api` and `app/services` that emits university commission data (`strip_commission`, `can_see_commission`, `commission_terms`, the term/receipt models, `commission_expected/received`, a `"commission":` key) must be mapped to the sweep endpoints that exercise it. A new emitter without a mapping fails the test. |
| PX9 | As-built notes, not changed | Recorded in RBAC §2.100 as `NEEDS_CONFIRMATION`, not changed here: a head records / removes receipts on **any** university (upc-019 CL9 names no team scope); an event may link any active university (upc-011); pm_out / head_out read any university's performance, commission included (upc-018 PF "any university"); typed query/body validation (`422`) runs before the role check (FastAPI, repo-wide), so the matrix sends valid inputs. |
| PX11 | Second gap (found by the sweep) | `GET /workflows/overseas/applications` (the overseas student / counselor / rep / agent application list) failed with a 500 on `main`: `join(University)` without an ON clause became ambiguous ("multiple FROMS which can join"), and 5 agn/ovs tests failed with it. The sweep cannot verify an endpoint that crashes, so the join names its ON clause, as its five sibling queries do (`admin.py`, `portal.py`, `schools.py`). |
| PX10 | Frontend | None (backlog). Browser QA checks the UI as built: overseas_admin's and counselor's university pages show no commission, and the partnership pages refuse other roles. A Playwright spec records that check (tests only). |

## 3. Design

- `apps/api/tests/upc033_helpers.py`: `ROLES`, `headers`, `world(client, db)`.
- `apps/api/tests/test_upc_033_matrix.py`: `MATRIX` (one `R(...)` row per route, cells as in tel-026), the inventory test (AC1), the
  per-row cell test, and the course-import order test (PX7).
- `apps/api/tests/test_upc_033_commission_sweep.py`: `SWEEP` (endpoints), the sweep test per endpoint, the positive control, and the
  serializer net (AC2, PX8).
- `apps/api/app/api/university_course_import.py`: `require_reader` before reading the upload (PX7).
- Docs: RBAC §2.100, `DEC-SCOPE-174`, the backlog status line, a QA report.

## 4. Risks

Tests only apart from PX7, so the risk is in the shared test database (every value unique per call; nothing truncated) and in run time
(about 130 rows × 14 roles). PX7 changes only the status a refused role gets on a bad upload (`403` before `422`/`413`).

## 5. QA evidence (2026-10-10)

Isolated stack `upc033` (web 13233 / api 18233), Chromium via Playwright. Super admin planted commission (a course percentage `73.19`, a course
amount `24,681.35`, a term `61.83` with planted conditions, a `commission_agreement` document) on a new published university and on the seeded
rep's university. Then: signed out, overseas_admin, counselor, university_rep, agent, overseas student, it_admin and college BDM opened
their university / course / application / dashboard pages and the partnership pages (36 page visits); desktop 1366, tablet 820, phone 390.

- Positive control: the super admin's university page shows every planted value.
- No planted value on any non-commission page; overseas_admin's partnership university page lists the course without a commission
  column and without the commission ledger; the public catalogue and the counselor's university page show no "commission" at all.
- Commercial Terms / Agreements answer "Access unavailable" to overseas_admin; every partnership page answers it to counselor, rep, agent,
  student, it_admin and BDM; signed out redirects to `/overseas/login`.
- PX7: counselor's bad course-import upload → `403`. PX11: `/workflows/overseas/applications` → `200` for student and counselor.
- No sideways scroll and no broken images at any width; no 5xx. Console: `401`s on public pages right after a sign-out (the stale-cookie
  session check, pre-existing, not upc-033).
- No defect attributable to upc-033. `apps/web/tests/e2e/upc-033-commission-visibility.spec.ts` records the check (only overseas_admin's own
  menu says "Commissions" -- the agent-commission module, `DEC-SCOPE-005`, PX8 -- so the word check reads the page's `main`).
