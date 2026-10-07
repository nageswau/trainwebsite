# bdm-024 — Browser QA (2026-10-07)

**Build under test:** `worktree-bdm-024` @ `d281e183`, Docker Compose project `bdm024` (web `localhost:13024`, api `127.0.0.1:18024`),
images rebuilt from that commit. **Browser:** Browser Use is not installed here. An isolated Playwright Chromium (1.62) drove the app,
with a scripted exploratory walk-through (`qa24.cjs`, kept outside the repo) plus the Playwright spec `tests/e2e/bdm-024-performance.spec.ts`.
**Data:** each run builds its own team through the API: a manager with one Agent, one School and one College BDM; two organizations
each (one with a very long name); three College leads; plus a manager with no BDMs. Demo super admin from `app.seed`.

## First pass (independent, no code changes)

| # | Check | Result |
|---|---|---|
| 1 | Happy path: L1 table → College Leads 3 → College BDMs (row 3, Total 3) → BDM → organizations (3 + 0 = Total 3) → org page | Pass: the counts agree at every level |
| 2 | Invalid input: `from > to`, more than 366 days, 2026-02-30, `from=yesterday`, unknown type, malformed BDM id | Pass: the API's reason inline (or "Choose valid dates for the period."); junk `from` is dropped; unknown type and malformed id give a 404 page |
| 3 | Empty: a manager with no BDMs; a BDM with no organization figures; no trips | Partly: see QA24-04 |
| 4 | Server / scope errors: another team's BDM; super_admin with a non-manager id | Pass ("BDM not found" / "Manager not found" inline); see QA24-03 |
| 5 | Loading | `loading.tsx` skeleton seen while the master view loaded |
| 6 | Cancel / back / refresh | Back from the drill-down returns to L1; reload keeps the page |
| 7 | Duplicate submission | N/A (read-only GET form) |
| 8 | Unauthorized / wrong role | Signed out → `/admin/login?next=…`; a BDM → "Access unavailable — BDM manager role required" |
| 9 | Desktop 1280 / tablet 768 / phone 375 | Manager pages: no horizontal page scroll; super_admin at 375: see QA24-01 |
| 10 | Navigation | Manager sidebar "Performance" / "Master view"; super_admin "BDM Performance" / "BDM Master View"; breadcrumbs keep the period |
| 11 | Console errors / failed network calls / broken images | None / none (no 4xx/5xx other than the deliberate ones) / none |
| 12 | Period form, "This month" | Submits as GET with `from`/`to`; "This month" resets |

### Issues found

| ID | Severity | Role | Page | Steps | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA24-01 | Medium | super_admin | `/bdm/manager/performance` (and every page with the team picker) | Sign in as super admin, open BDM Performance at 375 px | No sideways page scroll (AC5) | The Team `<select>` sizes to its longest "name (email)" option: the page is 134 px wider than the screen | `scrollWidth - innerWidth = 134`; `qa1/sa-L1-375.png` |
| QA24-02 | Medium (accessibility / visual) | all | all four pages | Open any table | The table caption is for screen readers only | The caption ("BDM performance by type, 1 Oct 2026 – …") shows as stray text above the table: `sr-only` is not a class in this app (it uses `visually-hidden`) | `qa1/sa-L1-375.png`, `qa1/L3-375.png` |
| QA24-03 | Low | super_admin | `/bdm/manager/performance?manager=<not a manager>` | Open an old or wrong team link | A way out of the error (bdm-023 QA23-02) | Only "Try again", which repeats the failing URL ("Show this month" is hidden because it equals that URL) | log `sa-bad-manager` |
| QA24-04 | Low | bdm_manager | `/bdm/manager/performance` | A manager with no BDMs opens Performance | An empty state that says why every figure is 0 | A table of zeros with no explanation | log `empty-L1` |

Not an issue: an unknown type or malformed BDM id shows Next's 404 page, as the other manager detail pages do (`notFound()`). The keyboard
check on the master view in this pass ran before the page had loaded (a script timing bug), so it is repeated in the re-check below.
