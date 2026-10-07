# tel-026 — §22 permission matrix + cross-role 403/404 sweep (design)

Date: 2026-10-07 · Backlog: `docs/delivery/TELECALLER_CRM_BACKLOG.md` tel-026 · Source: `EVID-019` §22 (lines 688–713)
Dependencies: tel-001 … tel-025, all merged to `main` (checked against the backlog status lines at `050e6671`).

## 1. What the item asks for (backlog, verbatim intent)

1. A documented telecaller / manager / counselor matrix in `RBAC_MATRIX.md`.
2. A parametrised test that calls every telecaller-reachable route as each role, and as an out-of-scope user of the same role, plus each
   §22 denied capability (payments, documents, application status, counselor records, delete, reports, targets).
3. No behaviour change unless a gap is found (then a fix).

Acceptance criteria: (AC1) every route × role cell has an expected status and a passing test; (AC2) every §22 denied line has a 403 test;
(AC3) no lead delete endpoint exists. Frontend: nav visibility checks only.

## 2. Decisions taken with the recommended answer (no owner question was needed)

| # | Point | Decision |
|---|---|---|
| PM1 | Which routes are "telecaller-reachable" | Every route under `/telecaller/*`, `/counselor/leads*`, `/counselor/appointments`, `/lead-appointments/*`, `/admin/telecallers*`, `/admin/telecaller-managers*`, `/admin/leads*`, `/bdm/meeting-requests*` and `/public/telecaller-assets/*`. A route-inventory test fails when a route appears under these prefixes without a matrix row, so the suite grows with each later item (backlog: "a growing suite"). |
| PM2 | The backlog edge "super_admin passes everywhere by design" | Not true as built: `DEC-SCOPE-094` F2, `-096`, `-100`, `-106` make super_admin **read-only** on calls, follow-ups, messages, email and bookings. The matrix records the as-built, owner-approved behaviour, not the backlog's draft line. |
| PM3 | Expected status of a cell | The exact status of the route's own decision: `2xx` allowed (run against a fresh fixture world so writes don't interfere), `403` role refused, `404` out of scope (no IDOR oracle), `401` anonymous. |
| PM4 | A gap found by the sweep | Fixed inside tel-026 when it is a §22 / documented-matrix violation and the fix is local; recorded in the QA report either way. |
| PM5 | §22 denied lines outside the telecaller routes | Represented by the real routes that perform them: payments (`/admin/payments*`), application documents (`/workflows/overseas/documents*`), application status (`/workflows/overseas/applications/{id}` PATCH and `/advance`), counselor records (the `/counselor/*` writes, `/lead-appointments/{id}/confirm|complete|no-show`, `PATCH /admin/users/{counselor}`), reports (`/telecaller/reports/*`, `/telecaller/manager/performance*`), targets (`POST /telecaller/targets`), delete (route introspection: no `DELETE` on a lead path). |

## 3. Design

- `apps/api/tests/tel026_helpers.py` builds one **world** directly in the database (no bcrypt: users get a fixed unusable hash and the
  session cookie is minted with `core.security.create_token`, the same token `/auth/login` issues):
  - users: telecaller `tel` (IT, reports to `mgr`), `tel_out` (IT, reports to `mgr_out`), `mgr`, `mgr_out` (no shared reports),
    IT counselors `cns` and `cns_out`, `it_admin`, `ovs_admin` (overseas admin), `super`, an `it_student`;
  - rows: `tel`'s open lead with a call, a follow-up, a WhatsApp send, a counselling appointment with `cns`, a qualification; a lead
    handed over to `cns`; a meeting request by `tel`; catalogue/content rows (product, campaign, script, template, brochure), a
    distribution rule, a target, an import batch.
- `apps/api/tests/test_tel_026_matrix.py`:
  - `MATRIX`: one row per route — method, path template, body (template), and the non-`403` cells; every unlisted signed-in role is `403`,
    anonymous is `401`. Placeholders (`{lead}`, `{call}`, …) are filled from the world.
  - `test_every_route_has_a_row` (AC1, PM1) — introspects `app.routes`.
  - `test_matrix_cell` parametrised by row: runs every cell; refused / hidden cells share one world, every `2xx` cell gets its own.
  - `DENIED_22` rows (AC2) — the seven §22 lines × `tel` → `403`.
  - `test_no_lead_delete_route` (AC3).
- Frontend (nav visibility only): a vitest check that the telecaller nav holds none of the manager-only pages (§22 reports / targets), and
  a Playwright spec that signs in as each role and checks the sidebar plus the access card on a page of the other role.
- Docs: `RBAC_MATRIX.md` §2.41 (the consolidated §22 matrix, one line per §22 capability → routes → test), `DEC-SCOPE-115` (PM1–PM5),
  backlog status line, QA report. No migration, no API change.

## 4. Risks

Tests only, so the regression risk is in the shared test database (rows are unique per call; nothing is truncated). A wrong expectation
must be checked against the code **and** the documented matrix before it is written down — never adjusted just to make a cell pass.
