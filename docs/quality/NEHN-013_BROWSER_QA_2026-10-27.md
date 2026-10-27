# nehn-013 — Browser QA, 2026-10-27

Stack: isolated compose project `nehn013` (web `http://localhost:13213`, api `127.0.0.1:18213`), built from `worktree-nehn-013`.
Tools: Playwright (Chromium, headless) exploratory scripts plus the e2e specs `nehn-013-crm-reports.spec.ts` and `tel-024-reports.spec.ts`.
Roles: `telecaller.manager@edusphere.local` (demo data), `superadmin@edusphere.local` (e2e fixtures, populated tables), `telecaller.it@`
(wrong role), and anonymous.

## First pass (no code changes)

| Check | Result |
|---|---|
| Happy path: Counselor, Date-wise (day / week / month), Follow-ups, Pending Follow-ups, funnel Lost + Conversion rate | Pass (QA-01, QA-04 below) |
| Invalid inputs: `group=year`, reversed range, bad date | Pass: a sentence above the form ("Choose day, week or month", …), and the form keeps the inputs |
| Empty states | Pass: "No leads with a counselor in this range.", "No follow-ups due in this range.", "No overdue follow-ups in this range." |
| Refresh / Back / Forward | Pass: the report and its filters (including `group`) follow the address |
| Unauthorized / wrong role | Pass: telecaller page shows "Telecaller Manager role required"; API 403; anonymous API 401 |
| Desktop 1280 / tablet 820 / mobile 390 | No horizontal page overflow on any new report (QA-02 is the tab strip's own scroller) |
| Console errors, failed network calls (≥500), broken images | None |
| Duplicate submission | N/A: read-only GET reports |
| Keyboard | The Group by select is reachable and operable by keyboard |
| Pending list privacy | Lead name only: no mobile or email in the table or CSV |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual |
|---|---|---|---|---|---|---|
| QA-01 | Medium | super_admin, manager | any funnel report | Open Date-wise with a rate of 2.0% | The screen shows `2.0`, the same as the CSV / Excel | The screen shows `2` (`0` for 0.0). The JSON number loses its decimal, so the screen and the CSV disagree |
| QA-02 | Medium | all | reports page at 1280px | Open any report on a desktop | All ten report tabs are visible | The strip scrolls sideways and clips at "Fo". Follow-ups and Pending Follow-ups are hidden, with no cue that they exist |
| QA-03 | Low | all | Follow-ups tab | Open Follow-ups | The heading matches the report title (and the export's) | The heading is "Follow-ups Report", but the CSV / Excel title is "Follow-up Status Report" |
| QA-04 | Low | all | Pending Follow-ups | Open a populated list | The Total row says something useful | The Total row is "Total — — — —" and says nothing |

All four are caused by nehn-013 and within its scope, so they are fixed in Phase 6 (TDD). No unrelated defects were found.
Screenshots: the session scratchpad (`qa/sa-*-desktop.png`, `qa/sa-*-mobile.png`).

## Re-test after fixes (Phase 6, TDD: each fix had a failing test first)

| ID | Fix | Test (RED → GREEN) | Browser re-test |
|---|---|---|---|
| QA-01 | The view shows `conversion_rate` with one decimal | `nehn013.crmReports.test.tsx` "shows the conversion rate with one decimal"; e2e `0.0` cells | Date-wise shows `1.4`, equal to the CSV |
| QA-02 | The tab strip reuses the existing `.report-tablist.wrap` | vitest "wraps the report tabs"; e2e `toBeInViewport` for five tabs at 1280px | All ten tabs visible at 1280px and 390px |
| QA-03 | The tab is "Follow-up Status" (the heading matches the title) | vitest tab labels; e2e heading | Heading "Follow-up Status Report" |
| QA-04 | A list with nothing to sum counts its rows: "Total (n)" | `test_pending_follow_ups_lists_open_overdue_ones_most_overdue_first` | "Total (72)" |

The second pass found no console errors, no ≥500 responses, no page overflow at 1280 / 820 / 390, and correct refusals (telecaller 403,
anonymous 401). Back, forward and refresh keep the report and `group`.

**Observed once, not reproduced:** a React #418 (hydration) console error in the first e2e run straight after an API container restart.
It did not recur in 2 single-spec runs, a 13-test group run, or a 45-load stress script over old and new report kinds. The feature's
report view is a server component, and its one client child (`SpreadsheetButtons`) renders deterministically, so nothing ties the error to
nehn-013. The e2e still fails on any console error, and it now records the page URL with the error so a recurrence can be placed.
