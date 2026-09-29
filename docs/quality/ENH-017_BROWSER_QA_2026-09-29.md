# ENH-017 — Browser QA record (2026-09-29)

**Scope:** first exploratory QA pass of ENH-017 (School-visible Global Education pipeline, `DEC-SCOPE-036`,
`SCR-SCH-038`) on branch `feature/enh-017-school-application-visibility` at `edaf768` (no code changed during that
pass), then one fix pass for QA17-01/QA17-02 and a browser re-test — see the end of this record.

**Environment:** isolated Compose project `enh017` (web :3017 rebuilt at `edaf768`, API :8017, own Postgres). The API
runs on a locally pinned image (`sqlalchemy[asyncio]<2.1`) because the stock image cannot start (RAID `I-42`). Headless
Chromium (Playwright 1.62, fresh browser context per scenario) driven by a throwaway script. Throwaway data written
straight into the isolated database with the ENH-016 test builders: School A (Platinum: coordinator, principal, teacher,
parent + Edusphere roles; 31 bridged students across all seven application stages, grades 9–12 / label-only
"Grade 12" / none, visa cases in all five stages, one student with two applications, one name containing markup, and
application notes / next action / reference / offer letter / intake / university / counselor / visa tracking reference
all set to `PLANTED-*` values; 5 unbridged students), School B (Gold, one bridged student), School C (Silver, no bridged
students), and a coordinator account with no linked school.

**Covered:** happy path (real UI sign-in → sidebar → page), funnel vs API counts, not-tracked tiles, §19 boundary
(rendered page and raw API body), markup in a student name, paging, back/forward, refresh, grade filter by mouse and by
keyboard only, double-click submission, nine tampered URLs, past-end offset, empty school, empty grade, principal,
cross-role URLs, other school, unlinked account, six wrong roles (page + direct API), signed-out access, loading under
1.5 s latency, API outage, desktop 1440 / laptop 1024 / tablet 768 / mobile 390 / 320, mobile menu, sticky first
column, broken images, console errors, failed network calls, unexpected redirects. **Not covered:** a pipeline-only 500
while the session read succeeds (not inducible without a code change; covered by `GlobalEducationPage.test.tsx`),
browsers other than Chromium, screen readers. **Not applicable:** success messages (read-only page, no writes).

**Result:** 76 scripted checks, 75 pass, 1 fail (PAGE-02 → QA17-01), plus three targeted probes (anchor landing vs
ENH-016, grade-submit landing, API outage on this and two existing pages). QA17-02/03 came from reviewing screenshots,
QA17-04 from the outage probe.

## Findings (as found in the first pass — resolution for QA17-01/02 in the re-test section below)

| ID | Sev. | Role / page | Finding | Reproduction | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA17-01 | Medium | Coordinator, Principal / `/school/{role}/global-education` | Paging and the grade filter do not bring the student table into view | 1. Sign in as a coordinator of a school with >25 bridged students. 2. Open Global Education. 3. Click "Next →" (or choose a grade and press "Show"). | The page opens at the `#students` card with its heading visible below the sticky top bar, as ENH-016's `#scorecards` does (card top = 88 px) | URL gains `#students` but the page stays at the top: `scrollY=0`, `#students` top at 884 px in a 900 px viewport, so the user sees no change except funnel counts. On one client-side run the card landed at top = 0 px, under the 68 px sticky top bar | `qa017/anchor-students-viewport.png` vs `qa017/anchor-scorecards-viewport.png`; `qa017/grade-submit-landing.png`; probe: `{"elTop":884,"scrollMargin":"88px","winScrollY":0}` vs ENH-016 `{"elTop":88,"winScrollY":2613}`. Console: none. Network: no failures. Suspected cause (`NEEDS_CONFIRMATION`): the route's `loading.tsx` streams a fallback first, so `#students` is not in the document when the browser performs the fragment scroll; the ENH-016 reports route has no `loading.tsx` |
| QA17-02 | Low | Coordinator, Principal / same page | Heading sizes are inverted | Open the page at 1440 px | The page title (h1) is at least as prominent as section headings | h1 "Global education" renders at 28 px (`.pipeline-page h1`), the card h2s "Pipeline" and "Students" at ~44 px (global `h2`) | `qa017/happy-coordinator-1440.png`, `qa017/anchor-students-viewport.png` |
| QA17-03 | Low (inherited pattern) | Coordinator, Principal / navigation into the page | While loading, the whole portal shell (sidebar, top bar, nav) disappears and only the skeleton card shows | Throttle to 1.5 s latency, click "Global Education" in the sidebar | Shell stays; only the content area shows the skeleton | Full-screen skeleton card, no sidebar | `qa017/loading-skeleton.png`. Same pattern as ENH-018's `coordinator/feedback/loading.tsx` |
| QA17-04 | Low (pre-existing, shared) | Any signed-in school role / any school page | API unreachable shows a technical message and a login link to a signed-in user | Stop the API container, reload the page while signed in | A plain "service unavailable, try again" message; no suggestion to sign in again | "Access unavailable · fetch failed · Return to login" | `qa017/api-down.png`. Identical on `/school/coordinator/entitlements` and `/reports` — comes from the shared `accessUnavailable` helper, not an ENH-017 regression |

## Passed checks (summary)

- **Happy path / data:** funnel equals the API (`31/25/21/18/10/4`); scope line "36 students · 31 students on the global
  education pathway"; six not-tracked tiles; 25 rows then 6 on page 2; "1–25 of 31"; the two-application student shows
  "2"; the other school sees only its own student.
- **§19 boundary:** no `PLANTED` value on the rendered page or in the raw API body; none of the 32 application ids in
  the API body; the markup name renders as literal text and no dialog fires.
- **Invalid input:** `?grade=abc|13|7`, `?offset=-5|99999|25.5`, `?grade=12&grade=11`, `?limit=0`, `?grade=<script>` all
  render the unfiltered page (HTTP 200, no error card); past-end offset shows "This page is past the end of the list."
  with Previous → real last page; API `?grade=abc` → 422.
- **Empty states:** empty school shows the verbatim message and a zero funnel; empty grade shows the verbatim grade
  message.
- **Keyboard / duplicate:** select focused, End, Tab reaches "Show", Enter submits; double-click "Show" lands once on
  `?grade=8` with no error; the select keeps its value.
- **Back / forward / refresh:** each restores the expected page and rows.
- **Roles:** principal nav "Reports | Global Education"; principal on the coordinator URL and coordinator on the
  principal URL are refused; teacher, parent, overseas admin, super admin, career counsellor and IT admin see the
  access card with a correct "Go to your dashboard" link, and their direct API call returns 403; the unlinked
  coordinator sees "This account is not linked to a school"; teacher nav has no Global Education.
- **Signed out:** access card with "Return to login"; no redirect (existing app pattern).
- **Layouts:** no page-level horizontal scroll at 1440/1024/768/390/320; KPI tiles 4/4/2/1/1 columns; the table scrolls
  inside its card; at 320 px the student-name column stays pinned (x = 39 px) while the table scrolls; the mobile menu
  exposes Global Education.
- **Loading:** skeleton appears during a throttled navigation (see QA17-03 for the shell).
- **Console / network / images:** no console errors or page errors in any scenario; no failed requests other than
  Next.js cancelling `?_rsc=` prefetches on navigation (`net::ERR_ABORTED`, framework behaviour); no broken images.

**Observations, not defects:** refused and signed-out pages return HTTP 200 with an access card (app-wide pattern); the
"Not tracked yet" wording repeats as region label, heading and per-tile badge; a hand-edited out-of-range URL is
silently ignored (by design, spec §7).

## Fix pass and re-test (same isolated stack, `web` rebuilt with the fixes)

| ID | Root cause (confirmed) | Resolution | Test |
|---|---|---|---|
| QA17-01 | The route's `loading.tsx` makes Next.js stream the page: the served HTML carries the skeleton first and the real content — `#students` included — inside a hidden stream chunk (`<div hidden id="S:1">`). The browser's fragment scroll runs while the target is hidden, so nothing scrolls. The ENH-016 reports route has no `loading.tsx`, so its `#scorecards` target is visible at parse time | New client component `ScrollIntoViewOnHash` (rendered inside the Students card) scrolls the card into view once it is on screen, only when the URL hash is `#students`; `scrollIntoView` honours the existing 88 px `scroll-margin-top`. The loading skeleton (AC17) stays; paging and the grade form still work without JS | 2 Vitest cases (scrolls when the hash targets `#students` — RED before the fix; no scroll otherwise); browser re-test below |
| QA17-02 | Global `h2` is `clamp(28px, 3.5vw, 44px)` while the page's `h1` is fixed at 28 px | `.pipeline-page .card h2 { font-size: 22px }` — page title 28 px > section headings 22 px > sub-headings 20 px, scoped to this page | Browser computed sizes below |

QA17-03 (loading skeleton replaces the shell; ENH-018 pattern) and QA17-04 (shared `accessUnavailable` wording on an API
outage) remain open by decision: both are patterns shared with other pages, to be fixed outside ENH-017.

**Browser re-test** (97 scripted checks, all pass, including every first-pass scenario as a regression run):

| Check | 1440 | 768 | 390 |
|---|---|---|---|
| Plain visit (no hash) stays at the top | `y=0` | `y=0` | `y=0` |
| "Next →" lands on Students | card at 322 px — page at its maximum scroll (`y=maxY=538`; 6 rows) | 280 px, `y=maxY` | 109 px, `y=maxY` |
| "← Previous" lands on Students | card at 88 px | 88 px | 88 px |
| Grade "Show" lands on Students | 176 px, `y=maxY` (9 rows) | 88 px | 88 px |
| Refresh on `#students` keeps the landing | ✓ | ✓ | ✓ |
| Heading sizes h1 / h2 / h3 | 28 / 22 / 20 | 28 / 22 / 20 | 28 / 22 / 20 |
| Console errors / failed requests | none | none | none |

On short pages the card cannot reach 88 px because the document ends; it is fully visible below the 68 px top bar at
the maximum scroll. Evidence: `qa017/retest-next-landing-1440.png`, `qa017/retest-show-landing-390.png`,
`qa017/retest-headings-1440.png`. The first-pass PAGE-02 check (card below the top bar after "Next →", measured after
the smooth scroll settles) failed before the fix (`scrollY=0`) and passes after it.

**Other verification after the fix:** Vitest 99 files / 1033 tests pass; `tsc` clean; ESLint 0 errors (warnings all in
files outside ENH-017); `next build` compiles both routes; Playwright `enh-017-global-education.spec.ts` 1 passed.

## Final verification (verification-before-completion, HEAD `b288162`)

| ID | Sev. | Finding | Resolution | Commit | Test |
|---|---|---|---|---|---|
| QA17-05 | Serious (a11y) | axe-core `scrollable-region-focusable` (WCAG 2.1.1) at 390 px: the student table scrolls sideways and its cells hold no links, so keyboard users could not reach the hidden columns. The ENH-016 scorecard table passes the same rule because its rows contain links | The `.table-scroll` wrapper is now a labelled region that takes focus (`tabIndex=0`, `role="region"`, `aria-label="Global education students"`) | `b288162` | Vitest (RED before the fix); browser: Tab after "Show" focuses the region (visible outline), ArrowRight scrolls it 320 px |

**Fresh evidence at `b288162`:** axe-core WCAG 2.0/2.1 A+AA on five states (coordinator all grades 1440, grade 12 at
390, principal, empty school, past end) — 0 violations; browser suite 97/97; Playwright ENH-017 + SCH-010 + ENH-016 +
SCH-001 5/5 (quiet stack); API ENH-017 + 15 neighbour files 231 passed; ruff and mypy clean on ENH-017 files; Vitest
99 files / 1034 tests; `tsc` clean; ESLint `--max-warnings=0` clean on ENH-017 files; `next build` compiles both routes.
Evidence: `qa017/a11y-table-focus-390.png`, `qa017/final-run-2.log`.
