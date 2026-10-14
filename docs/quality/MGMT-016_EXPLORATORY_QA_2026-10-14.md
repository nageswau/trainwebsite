# mgmt-016 — Student funnel dashboard — exploratory browser QA (2026-10-14)

- **Build:** `feature/mgmt-016`, Docker Compose project `mgmt016` (web `localhost:13016`, api `127.0.0.1:18016`), seeded demo data plus
  the rows the backend tests left in the shared stack DB.
- **Tools:** Playwright Chromium scripts: desktop 1366×900, tablet 820×1180, mobile 390×844. Console, page-error, failed-request and
  5xx listeners on every page. Full-page screenshots, kept outside the repo. The first pass changed no code.

## Scenarios (first pass)

| # | Scenario | Role | Result |
|---|---|---|---|
| 1 | Command Center → "Student funnel" → page | partner | Pass. Lead journey (4), IT training (5) and Abroad education (5) stages, each with its definition; ~200–430 ms load |
| 2 | Each of the 9 breakdowns over 2026 | partner | Pass. For every column, rows + Unknown = the Total row = the stage's own count (AC2); "Not broken down by …" lists the other stages |
| 3 | `by=branch` | partner | Pass. "Branch is not tracked in EduSphere yet…", no table |
| 4 | `by=bdm` with no BDM on any lead | partner | Pass. "No BDM recorded on anything in this period." and an Unknown-only table that adds up |
| 5 | `from` after `to`; a 2-year period | partner | Pass. The API's 422 message ("The period must start on or before its end" / "…at most 366 days"), no funnel |
| 6 | `from=2026-02-30`, `by=zzz`, `by=country&by=course`, `from=abc&to=<script>` | partner | Pass. Dropped by the page; the default month, no breakdown, nothing reflected |
| 7 | Only `from` or only `to` | partner | Pass. The other end defaults to this month's |
| 8 | An empty period (Feb 1901) | partner | Pass. Every stage reads 0 (a real count); empty-breakdown status |
| 9 | Double-click Show; Back; Forward; "This month"; reload | partner | Pass. One GET address; Back restores no breakdown, Forward restores `source`; reload keeps the choice |
| 10 | Keyboard; empty required date | partner | Pass. Show is reached by Tab with a visible focus ring; the browser blocks an empty date |
| 11 | Same page from the super admin sidebar | super_admin | Pass |
| 12 | Same page | accountant, counselor | Pass. "Access unavailable", no funnel (API 403) |
| 13 | Signed out | — | Pass. `/admin/login?next=%2Fmanagement%2Ffunnel%3Fby%3Dcountry` |
| 14 | Console errors, 5xx, page overflow | all | None at all three widths (0 px horizontal overflow). The paths stack on a phone; the table scrolls in its own box |

Not issues: the "failed" `?_rsc=` requests are Next.js link prefetches cancelled by the next navigation. The hidden sidebar logo
reported as "not loaded" on tablet and mobile is lazy-loaded inside the closed menu (shared `PortalShell`, not mgmt-016).

## Issues found (both caused by mgmt-016, both in scope)

| ID | Severity | Role / page | Steps | Expected | Actual |
|---|---|---|---|---|---|
| QA16-01 | Cosmetic | partner, `/management/funnel?by=bdm` | Break down by BDM | "Their records carry no BDM value." | "Their records carry no bdm." (the label was lowercased) |
| QA16-02 | Low | partner, `/management/funnel?by=course` | Break down by Course when two programs share a title | Each row can be told apart | Two identical "Python" rows (program titles are not unique; only the slug is) |

No console or network evidence: both are presentational.

## Fixes (phase 6, test first) and second pass

| ID | Fix | Test (RED first) | Second pass |
|---|---|---|---|
| QA16-01 | The note keeps the dimension's own spelling: "…carry no {label} value." | `ManagementFunnel.test.tsx` "keeps the dimension's own spelling…" | Pass |
| QA16-02 | A label repeated within a breakdown carries the record's short id: "Python (0b5d4b34)". Applies to every dimension (two people can share a name) | `test_mgmt_016_funnel.py::test_rows_with_the_same_label_are_told_apart` | Pass: "Python (0b5d4b34)", "Python (9d735ed0)" |

After the fixes: backend 16/16, focused vitest 55/55, `mgmt-016-funnel.spec.ts` 4/4.
