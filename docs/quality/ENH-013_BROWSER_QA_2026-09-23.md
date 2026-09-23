# ENH-013 — Browser QA and fixes (2026-09-23)

**Scope:** first exploratory QA pass of ENH-013a (`DEC-SCOPE-027`, Student 360° view / Career Passport), then test-first fixes.
No code was changed during the QA pass itself.

**Environment:**
- **Build:** branch `feature/enh-013-student-360-view`. QA ran on `2705f90`; fixes are `c7b5050`; the E2E spec is `57d3354`.
- **Stack:** isolated Compose project `enh013` built from the branch — web on :3013, API on :8013, its own migrated
  (`0039_student_career_goal`) and seeded Postgres. The Caddy override was not used.
- **Browser:** a separate local Chrome 153 with a throwaway profile, driven over CDP (Browser Use), launched with
  `--disable-backgrounding-occluded-windows --disable-features=CalculateNativeWinOcclusion` so a covered window still
  receives input. Console, exceptions and network (≥400 / failed loads) were captured on every page.

**Accounts:** the seeded "Sunrise Public School" (coordinator, principal, teacher, parent of two, academic team, career
counselor, psychometric team; five students), plus one newly enrolled student created through the API for the empty
states. Sign-in for scenario setup used the same endpoint the login form posts to; login itself was not under test.

**Not committed:** the raw screenshots and scripts.

## Findings and resolution

| ID | Severity | Finding | Status | Evidence of the fix |
|---|---|---|---|---|
| QA-01 | High | At ≤980 px every `/360` page was ~2,200 px wide (390 px phone: `scrollWidth` 2,193; swiping sideways showed blank space). Cause: each tab's absolutely positioned `.visually-hidden` state text escaped the tab strip's overflow (the strip is `position: static`). | **Fixed** `c7b5050` | `.s360-tab { position: relative }`. Chrome: page width = viewport at 390 and 768, `scrollX` stays 0. E2E asserts `scrollWidth <= innerWidth`; mutation-checked (removing the rule fails it at 2,052 px). |
| QA-02 | Medium | Every tab click ran `router.replace('?tab=…')`, re-rendering the whole server page and re-running the 360 aggregation (16 API reads for ~16 clicks); `?tab=` only updated after the round trip. | **Fixed** `c7b5050` | `history.replaceState`. Chrome: 5 tab clicks → 0 requests, URL updates immediately, reload keeps the tab. Unit test + E2E (no request to the page while switching); mutation-checked. |
| QA-03 | Medium | Desktop, scrolled: the sticky tab list (`top: 16px`) slid under the 68 px sticky portal top bar — Overview covered (`elementFromPoint` → `.portal-topbar`). | **Fixed** `c7b5050` | Sticks at `top: 84px`, `max-height: calc(100vh - 100px)`, scrolls on its own. Chrome at 1440×805 and 1366×620: no tab covered; every tab reachable by wheel+click and by Home/End. E2E asserts Overview is clickable after scrolling. |
| QA-04 | Low | Career goal save → 500: "Something went wrong." and focus fell to `<body>` (a `refocus()` on a still-disabled input). | **Fixed** `c7b5050` | "The career goal could not be saved. Please try again."; the input is read-only (still focusable) while saving; Escape still cannot close it mid-save. Unit tests (the old focus test was intermittently red in jsdom). Chrome: focus returns to the input. |
| QA-05 | Low | Documents tab links the seeded psychometric report `/demo/aarav-aptitude-report.pdf`, which 404s. | **Not changed** (owner decision) | Seed data only; logged as `RAID.md` I-34. The link itself is safe (`safeHref`). |
| QA-06 | Low | Activities: upcoming school activities were sent but never shown; "School activities attended" announced twice (heading + hidden caption). | **Fixed** `c7b5050` | Upcoming table added; tables named once via `aria-labelledby`. Unit tests; Chrome shows both tables with one name each. |
| QA-07 | Medium (pre-existing) | A teacher can open `/school/coordinator/...` routes (incl. `/360`) and sees the coordinator label and navigation; data stays scoped by the API. Same on the pre-ENH-013 student page. | **Not changed** (outside ENH-013) | `RAID.md` I-35. |
| QA-08 | Low (pre-existing) | A malformed student id shows "[object Object]" (`serverApi` passes FastAPI's list `detail` through). Same on the pre-ENH-013 page. | **Not changed** | `RAID.md` I-36. |
| QA-09 | Low (pre-existing) | API outage → "Access unavailable — fetch failed — Return to login". | **Not changed** | `RAID.md` I-37. |
| QA-10 | Info (pre-existing) | Signed-out visit shows the card with a login link instead of redirecting. | **Not changed** (existing convention) | `RAID.md` I-37. |

## What passed in the QA pass (unchanged by the fixes)

- **Access:** unassigned student (teacher), unlinked child (parent), other school, wrong role (overseas admin), random id
  (404 "Student not found") — each refused with the server's own message; signed out → login link.
- **Per role:** service roles see exactly their restricted tabs ("not available for your role", never "empty"), the header
  shows name + school only, and their dashboards list the portfolio's students with working links; only the Career
  Counselor sees the career-goal editor.
- **Empty states:** a newly enrolled student shows an empty-state message on every data tab, naming who records the data.
- **Career goal:** Escape and Cancel close the editor and return focus; 120-character cap with a live counter; "Career goal
  saved." and persistence after reload; a double-click sends exactly one PATCH; a dropped connection keeps the entry; the
  parent sees the goal read-only.
- **Navigation:** deep links and reload keep the tab; a hostile `?tab=` falls back to Overview with nothing injected; the
  header's back link and browser Back behave; the loading skeleton shows on client navigation with the right portal.
- **Keyboard:** Tab lands on the selected tab; arrows (both axes), Home/End with wrap; Tab into the panel, Shift+Tab back;
  visible 2 px focus outlines.
- **Console / network / images:** no console errors, exceptions or failed requests in normal use; no broken images.

## Harness notes (not product defects)

Early "lost clicks" were artefacts: the automation tab was reported `hidden` (Windows occlusion) so Chrome dropped
synthetic input, and later clicks were measured mid smooth-scroll (`html { scroll-behavior: smooth }`). With the Chrome
flags above and instant scrolling before measuring, 12/12 timed tab clicks landed correctly.
