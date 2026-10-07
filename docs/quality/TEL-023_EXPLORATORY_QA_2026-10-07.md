# tel-023 — Exploratory QA (2026-10-07)

Stack: isolated compose project `tel023` (web :3023, API :8023), seeded; Chromium via Playwright in the `web-test` container. A temporary
exploratory spec drove the checks below and was deleted after the pass; the lasting coverage is `tests/e2e/tel-023-performance.spec.ts`.

| Check | Role | Result |
|---|---|---|
| Happy path: default range (1st of month → today), Calls desc, counts per Appendix B, Total row | manager | Pass |
| Another manager's telecaller never listed | manager | Pass |
| Sort by name (header link, `aria-sort`), team filter keeps the sort | manager | Pass |
| CSV download (filename, "Report downloaded.") | manager | Pass |
| CSV = screen: BOM, header labels, 68 rows + Total, `text/csv` | super_admin | Pass |
| Range > 366 days / reversed / future end → API sentence in the panel; dates kept in the form | manager | Pass |
| Junk URL params (`date_from=garbage`, `sort=evil`, `team=moon`) → defaults, no error | manager | Pass |
| Empty scope → "No telecallers in your scope yet.", no CSV button | manager with no reports | Pass |
| Name → `/telecaller/manager/team/{id}/activity?date={to}` | manager, super_admin (68 links) | Pass |
| IT admin: IT telecallers only, plain names, no team picker; `team=overseas` → 403 (API test) | it_admin | Pass |
| Overseas admin: Overseas only; IT admin page → "IT Administrator role required" | overseas_admin | Pass |
| Telecaller: page "Telecaller Manager role required"; API 403 | telecaller | Pass |
| Signed out → `/admin/login?next=…` / `/it/login?next=…` | — | Pass |
| Refresh keeps sort (`aria-sort` ascending after reload) | super_admin | Pass |
| Desktop 1280 / tablet 820 / phone 375: no page side-scroll; the table scrolls in its region | super_admin | Pass |
| Console errors / 5xx responses | all | None |
| API time, super_admin, 68 telecallers | super_admin | 0.8 s |

## Issues

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA-01 | Low (test) | manager / Performance | `getByLabel("To")` | the To field | also matched the "Telecaller: sort A to Z" link | Spec uses `exact: true` |
| QA-02 | Low (a11y) | manager, super_admin / Performance | Inspect the Team select's name | "Team" | "Team All teams IT Overseas" (select nested in its label) | **Fixed**: explicit `htmlFor`/`id` labels; e2e selects by exact label |
| QA-03 | Info | — | super_admin "all" with many telecallers | — | one set of queries per telecaller (0.8 s for 68) | Follow-up: tel-024's grouped `flow_counts_by_user` once merged |
