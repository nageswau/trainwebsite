# bdm-021 browser QA — College business tracking (2026-10-06)

**Environment:** isolated compose project `bdm021` (web :13021, API :18021, production `next build`); isolated Playwright Chromium in the
`bdm021` web-test container. Browser Use is not installed in this environment (the same as for bdm-005 / 017 / 018). Driver: an exploratory
Playwright pass written as a QA engineer would test it, kept outside the repository. Seed: `python -m app.seed`, then per-run accounts (manager,
College BDM, School BDM, IT admin, three IT students), a College organization with a long name and five leads (three linked), a Corporate
organization of the College module, one paid fee (₹1,23,456.78) and one failed fee.

## Pass 1 (no code changes)

| # | Check | Result |
|---|---|---|
| 1 | Happy path: assigned BDM | Contacted 5, Leads 5, Registrations 3, Training 0, Certification 0, Internship "Not tracked yet", Placement 0; Training fees ₹1,23,456.78 (the failed fee is excluded) |
| 2 | Invalid input: `/bdm/manager/organizations/not-a-uuid` | "Organization not found", with a way back |
| 3 | Empty state (no leads) | "No leads yet. The funnel fills in as leads are added and linked to student accounts." (scripted spec) |
| 4 / 5 | Server error / loading | The first read fails → alert with "Try again" → retry (component test; the server-rendered page can't be failed on demand) |
| 7 | Refresh | Business section re-renders with the same figures |
| 9 | Unauthenticated | API 401; the page redirects to `/bdm/sign-in?next=…` |
| 10 | Wrong role | `it_admin` API 403; School BDM: API 404 and "Organization not found"; the School BDM's own School organization has no Business section (API 404) |
| — | B1: Corporate organization of the College module | Business section shown |
| — | B3: another College BDM / manager | Funnel without revenue and the restricted note (scripted spec) / revenue shown |
| 11–13 | 1280 / 768 / 375 / 320 px | No horizontal overflow; the funnel and the revenue tiles reflow |
| 18 / 19 | Console errors / failed calls | None / no 4xx–5xx beyond the deliberate role checks. `net::ERR_ABORTED` RSC prefetches, cancelled by the script's fast navigation, are unrelated to bdm-021 |
| 17 | Broken images | None |
| — | Keyboard | No controls inside the section in the loaded state (read-only); "Try again" is a native button |

### Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA21-01 | Low | all | Organization profile → Business | Open a College organization; read the Internship stage or any untracked revenue line | The badge says "Not tracked yet" and the note says why | The note repeated "Not tracked yet: …" after the badge | **Fixed** test-first (`test_untracked_stages_and_lines_are_labelled_not_zero` RED → GREEN); re-verified in the browser |

## Pass 2 (after the fix)

The pass 1 scenario was repeated with the same results, and the notes now read "Internships are not recorded in EduSphere." / "No internship revenue
is recorded in EduSphere." No console errors. Playwright: `bdm-021-college-business.spec.ts`, `bdm-017`, `bdm-002` (2), `bdm-018`: 5 passed.
