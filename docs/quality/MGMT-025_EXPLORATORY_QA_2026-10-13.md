# MGMT-025 — Recruitment dashboard: exploratory QA (2026-10-13)

- **Stack:** isolated Docker Compose project `mgmt025` (web `http://localhost:13025`, api `127.0.0.1:18025`), seeded demo accounts, and
  the shared test DB, which also holds backend-test rows.
- **Browser:** Playwright Chromium, running a scripted exploratory pass plus `mgmt-025-recruitment.spec.ts`.
- **Spec:** `docs/superpowers/specs/2026-10-13-mgmt-025-recruitment-dashboard-design.md`.

## Coverage

| Area | Result |
|---|---|
| Happy path: partner from the Command Center → Students "Recruitment"; People "Recruiters" → `#recruitment-kpis`; Partnerships "Companies" → `#company-pipeline` | Pass |
| Desktop 1440 / tablet 820 / mobile 390 | Pass: no page-level horizontal overflow (0 px at each width); tiles reflow to 4 / 2 columns |
| Invalid input: start after end, more than 366 days, future end | Pass: the API's wording is shown in `.form-error`, and no tiles appear |
| Malformed or repeated date in the address (`garbage`, `2026-02-30`, two `date_from`s); empty dates | Pass: the malformed date is dropped (defaults shown); empty dates are removed by one redirect |
| Refresh / Back / "This month" | Pass: refresh keeps the period; Back and "This month" reset the inputs to the shown period |
| Duplicate submission | Not applicable (read-only GET form) |
| Roles: partner (11 tiles, with revenue) | Pass |
| Roles: super_admin (10 tiles, "Revenue is shown to partners.") | Pass |
| Roles: accountant, `placement_team` (access card, API 403) | Pass |
| Roles: signed out | Pass: redirected to `/admin/login?next=%2Fmanagement%2Frecruitment` |
| AC: KPIs equal `GET /recruiter/management` totals (super admin, same default period) | Pass (e2e + pytest) |
| Console errors, 5xx / failed requests, broken images | None. The only console error is the expected 403 resource load for the refused recruiter |
| Keyboard | Labelled date inputs; Tab moves through the native date segments, then to Apply (the same as mgmt-019) |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual (before fix) | Status |
|---|---|---|---|---|---|---|---|
| QA25-01 | Low | partner, super_admin | `/management/recruitment`, desktop | Scroll to the company pipeline | The "Requirement closed · Lost" line is spaced from the last step | The line sat flush under "Joining" | Fixed: uses the existing `.funnel-note` margin; covered by vitest; re-checked in the browser |

No issue outside mgmt-025 was changed. Two failures were seen that are unrelated to this feature: the vitest `RecruiterCompanies.test.tsx` "archives after confirming" case and the known `dateZoneSweep` case. Neither touches a mgmt-025 file.
