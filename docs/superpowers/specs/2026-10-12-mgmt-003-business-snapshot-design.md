# mgmt-003 — Business snapshot + `management_metrics` foundation (design)

Date: 2026-10-12 · Backlog: `docs/delivery/MANAGEMENT_COMMAND_CENTER_BACKLOG.md` mgmt-003, Appendix B S1–S15 · Source: `EVID-017` §3
(`DERIVED_BLUEPRINT`), scope authority M1/M13 (`EXPLICIT_APPROVAL`, 2026-10-08), `DEC-SCOPE-186`. Dependency mgmt-001: merged to `main`
(PR #243, `1a79d4cc`). No migration.

## 1. What the item asks for

§3 "Business snapshot": 15 counts "from your database", on a page for the operational tier (partner + super_admin).
`services/management_metrics.py` is born here as the single owner of management figures.

Acceptance criteria (backlog): (AC1) each KPI equals its Appendix B definition in fixtures; (AC2) missing modules show "not available
yet", not 0. Negative: an accountant → 403. Edge: deactivated users excluded. Performance: a fixed query count, tested.

## 2. Discovery (Graphify + code, `main@1a79d4cc`)

| Class | Items |
|---|---|
| MUST CHANGE | new `services/management_metrics.py`; `api/management.py` (`GET /management/snapshot`); `schemas.py` (`ManagementSnapshotOut`); web `lib/management.ts` (types, labels, live entry), new `app/management/snapshot/page.tsx`, new `components/ManagementSnapshot.tsx` |
| MAY CHANGE | `docs/architecture/API_CONTRACT.md`, `RBAC_MATRIX.md`, `PRODUCT_DECISION_REGISTER.md`, the backlog status line |
| SHOULD NOT CHANGE | `management_access.py` (reused as is), every module's own metrics service, `admin.py` `/admin/dashboard` (its figures stay as they are) |
| HIGH REGRESSION RISK | `MANAGEMENT_PILLARS` (mgmt-001 tests assert the pillar titles and the sidebar); the mgmt-001 home page |

Data sources (all read-only): `users` (role, active), `enrollments` + `batches` (status `upcoming|active|completed|cancelled`),
`overseas_applications` (student_id / agent_student_id / school_student_id; `withdrawn`, `enrolled`), `agent_students` + `agent_org_members`
+ `agent_orgs` (status `pending|active|rejected|suspended`), `school_students` (+ `academic_years.status`), `schools` (tier,
tier_valid_until), `candidates` (rec-010 `opted_in`, `user_id`, `archived_at`), `universities` (upc stage → `partnership_stages.GROUPS`,
`lost_at`, `active`), `companies` (rec-005 stage order, `lost_at`, `archived_at`), `recruiter_profiles`.

**Finding:** the backlog (2026-10-08) expected S9, S10, S15 to be "not available yet". UPC (upc-025 groups), the Recruiter company
pipeline (rec-005) and recruiter profiles (rec-001) have all merged since, so all 15 figures are computable today.

## 3. Decisions (recommended answers to Q-03, applied under the owner's standing build-session instruction; `UNVERIFIED`)

| # | Point | Decision |
|---|---|---|
| MS1 | S1 Total Students | Active users with role `it_student` or `overseas_student` + every `school_students` row + agency students without a login (`agent_students.student_id IS NULL`) in S5's set. An agency student who has a login is already counted as the user (no double count) |
| MS2 | S2 Active Students | Of S1: users with an enrolment (not withdrawn) in an `active` batch or an open application; school students in an `active` academic year; login-less agency students with an open application. **Open** = not `withdrawn` and not `enrolled` |
| MS3 | S3 IT Training | Distinct active users with an enrolment (not withdrawn) in an `active` batch |
| MS4 | S4 Abroad Education | Distinct students with ≥ 1 non-withdrawn application, keyed agency student → school student → user (in that order), so one agency student is one person; a deactivated user's own applications are excluded |
| MS5 | S5 Agent Students | `agent_students.status = active` whose `agent_id` is a member of an `active` organisation |
| MS6 | S6 Placement Students | rec-010 is built: opted-in candidates (`opted_in`, `user_id` set, not archived) whose user is active |
| MS7 | S7 Active Agents | Organisations with status `active` |
| MS8 | S8 Partner Schools | Schools with a tier and `tier_valid_until` ≥ today (IST) |
| MS9 | S9 University Partners | upc built: active, not lost universities whose stage is in the `partner` group (`partnership_stages.GROUPS`, the upc-025 G1 rule) |
| MS10 | S10 Partner Companies | rec-005 built: companies not archived, not lost, at a stage after "Interested" in `recruiter_stages.ORDER` |
| MS11–14 | Staff counts | Active users with role `trainer` / `counselor` (any division; school `career_counselor` is not a counselor here) / `telecaller` / `bdm`. Managers (`telecaller_manager`, `bdm_manager`) are not counted |
| MS15 | S15 Recruiters | Active `placement_team` users with a `RecruiterProfile` (the rec-033 PF1 rule) |
| MS16 | AC2 | No source module is missing today, so no figure is "not available yet". The response carries plain integers. A later figure whose module is unbuilt adds that state then (YAGNI) |
| MS17 | One query | All 15 counts are scalar subqueries of **one** `SELECT` (fixed query count = 1, tested) |
| MS18 | Page | `/management/snapshot`, a live "Business snapshot" entry (operational tier) at the top of the Business Intelligence pillar. Accountant → the API's 403 → "Access unavailable" |
| MS19 | Freshness | Live on each request; `as_of` = today (IST). No caching (counts on indexed columns) |

## 4. Design

Backend
- `services/management_metrics.py`: `SNAPSHOT` = ordered `(id, key, label)` for S1–S15; `async def snapshot(db, today) -> dict`
  builds one `select(<15 scalar subqueries>)` and returns `{key: int}`.
- `api/management.py`: `GET /management/snapshot` → `require_management` then `can_view_operational` else 403 (`NO_ACCESS`
  wording: "Operational access required"). Returns `{as_of, kpis: [{id, key, label, value}]}`.
- `schemas.py`: `ManagementKpi`, `ManagementSnapshotOut`.

Frontend
- `app/management/snapshot/page.tsx` (server): `Promise.all([me, snapshot])`; a failure → `accessUnavailable(e, "/admin/login")`.
  Shell as the home (super_admin keeps `SUPER_ADMIN_NAV`).
- `components/ManagementSnapshot.tsx`: the existing `.metric-grid` / `.metric` tiles in a `<ul aria-label>`; "As of" date.
- `lib/management.ts`: types; the entry gets `href: "/management/snapshot"`.

Security: counts only, no PII; tier checked at the route; GET only (no CSRF surface); no new logging of data.

## 5. Tests

- `tests/test_mgmt_003_snapshot.py`: tiers (partner/super_admin 200; accountant/it_admin 403; signed out 401); one SQL statement; per
  KPI a **delta** fixture (the shared test DB has seed data): add counted rows and excluded rows (deactivated user, withdrawn, inactive
  org, expired tier, lost, archived, manager roles…) and assert the exact increase.
- vitest: the page (partner, super_admin nav, 403 → access unavailable) and the tiles; `management.test.ts` live entry.
- Playwright `mgmt-003-business-snapshot.spec.ts`: partner opens the entry, sees 15 tiles; accountant sees no entry and a direct URL
  shows "Access unavailable".
