# mgmt-024 — Applications funnel dashboard — exploratory browser QA (2026-10-13)

- **Build:** `feature/mgmt-024`, Docker Compose project `mgmt024` (web `localhost:13024`, api `127.0.0.1:18024`), seeded demo data plus
  the rows the backend tests left in the shared stack DB (616 applications at the time of the pass).
- **Tools:** Playwright Chromium scripts: desktop 1366×900, tablet 820×1180, mobile 390×844. Console, page-error, failed-request and
  5xx listeners on every page. Full-page screenshots, kept outside the repo. The first pass changed no code.

## Scenarios (first pass)

| # | Scenario | Role | Result |
|---|---|---|---|
| 1 | Command Center → Students → "Applications" → page | partner | Pass. 11 stages in source order; Under Review / Accepted / CAS/COE "Not tracked" with no bar; withdrawn note; ~120 ms load |
| 2 | Each of the 8 filters, Apply | partner | Pass. Every filter narrows (Created ≤ unfiltered) and the select keeps its value |
| 3 | Reload; Back after changing a filter; double-click Apply | partner | Pass. Reload is stable; Back restores `status=enquiry`, its select and counts; a double submit is an idempotent GET |
| 4 | `?date_from=2026-05-01&date_to=2026-04-01` | partner | Pass. The API's 422 "The end date must be on or after the start date", no funnel |
| 5 | `?date_from=2026-02-30`, `?agency=zzz&status=<60 chars>` | partner | Pass. Dropped by the page; the unfiltered funnel |
| 6 | `?university=<unknown id>` | partner | Pass. Zeros and "No applications match these filters." |
| 7 | Keyboard | partner | Pass. Apply reached by Tab (16 stops; date inputs have three each), Enter submits, focus ring visible |
| 8 | Same page | super_admin | Pass. The funnel, in the super admin's own sidebar |
| 9 | Same page; API | accountant, counselor, overseas_admin | Pass. API `403`; "Access unavailable" |
| 10 | Signed out | — | Pass. `/admin/login?next=%2Fmanagement%2Fapplications%3Fstatus%3Doffer` |
| 11 | Console errors, failed requests, broken images, page overflow | all | None at all three widths (0 px horizontal overflow) |

## Issues found (all caused by mgmt-024, all in scope)

| ID | Severity | Role / page | Steps | Expected | Actual |
|---|---|---|---|---|---|
| QA24-01 | Low | partner, `/management/applications` | Choose Status = Offer, Apply | A short, shareable address `?status=offer` | `?date_from=&date_to=&agency=&counselor=&country=&university=&course=&intake=&staff=&status=offer` (every empty field) |
| QA24-02 | Low | partner, desktop + mobile | Open the page | Filter controls in an even grid; full width on a phone | Each select is as wide as its longest option, so the rows are ragged (mobile screenshot) |
| QA24-03 | Low | partner | Unfiltered funnel (Submitted = 2 of 616) | A non-zero stage never reads 0% | "0% of applications created" next to a visible bar |
| QA24-04 | Cosmetic | partner | Funnel with withdrawn applications | Space between the last bar and the note | The note touches the Enrollment bar |

No console or network evidence: every issue is presentational. Not issues: an earlier "Back keeps url: false" reading was the probe
reading the URL before the navigation settled (rechecked with an explicit wait: scenario 3); one cold-start e2e failure did not recur
in 15 repeated runs.

## Fixes (phase 6, test first) and second pass

| ID | Fix | Test (RED first) | Second pass |
|---|---|---|---|
| QA24-01 | The page redirects once to `applicationsHref(filters)` when the address holds an empty field | `ManagementApplications.test.tsx` (redirect), `managementApplications.test.ts` (`applicationsHref`), e2e waits for `?status=enquiry$` | Apply → `/management/applications?status=offer` |
| QA24-02 | `.funnel-filters` grid (`auto-fill, minmax(min(100%, 190px), 1fr)`), full-width controls | class asserted | Desktop: two even rows of five; mobile: one full-width column; 0 px overflow |
| QA24-03 | `shareText`: a non-zero stage that rounds to 0% reads "Less than 1%" | lib + component | Submitted 2 of 616 → "Less than 1% of applications created" |
| QA24-04 | `.funnel-note` top margin | class asserted | Note spaced from the Enrollment bar |

Second pass, all other scenarios unchanged: no console errors, failed requests or 5xx for partner, super_admin, accountant, counselor and
overseas_admin; Playwright `mgmt-024`, `mgmt-001`, `mgmt-003` specs 12/12. No open issue.
