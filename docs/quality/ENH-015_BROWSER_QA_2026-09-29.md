# ENH-015 — Browser QA record (2026-09-29)

**Scope:** first exploratory QA pass of ENH-015 slice 1 (School Summary PDF, Student Progress Report PDF;
`DEC-SCOPE-037` provisional) on branch `feature/enh-015-student-school-reports` at `286e758`. **No code was changed
during this pass.**

**Environment:** isolated Compose project `enh015` (web :3015, API :8015, own Postgres/Redis). The API image is the
branch build plus `greenlet` (the stock image cannot start — RAID `I-42`). Headless Chromium (Playwright 1.62.1, a fresh
browser context per scenario) driven by a throwaway script outside the repo. Throwaway data written with the ENH-016 test
builders: School A (Platinum; 26 students across grades 8–12 / label-only "Grade 12" / none; a fully populated child with
markup in counsellor notes, a bell control character, a draft and a verified result, a psychometric report URL and
application notes all set to `PLANTED-*` values; a Devanagari-named child; a child whose name contains markup; an
unlinked sibling; a student with no records), School B (Gold, one child linked to School A's parent), School C (empty),
School D (1,200 students), and a coordinator with no linked school. The shared database also holds rows from the earlier
pytest run (e.g. the active academic year "2034-35-b643", which the School Summary correctly prints).

**Covered:** happy path via the sidebar (coordinator, principal) and the child page (parent); PDF content (figures vs the
on-screen dashboard, redaction, escaping, empty and large schools); loading state (2 s latency); server errors (500, 502,
403, 200-HTML, network drop — browser-side interception) and a real API outage (container stopped); real session expiry
(401); duplicate submission (double-click); keyboard (Enter, Space, Tab); refresh; back/forward; unauthorized (signed out)
and seven wrong roles (page + direct API, including 403-before-422); unlinked coordinator; other-school and unlinked-child
URLs; malformed/unknown ids; tampered `school_id` query; response headers; audit rows; layouts 1440/1024/768/390/320 on
three pages; broken images; console errors; failed network calls; unexpected redirects.
**Not covered:** a real (non-intercepted) 5xx from the report endpoint while the session works (needs a code change);
browsers other than Chromium; screen readers; PDF accessibility tooling.

**Result:** 101 scripted checks, 99 pass, 2 fail (both → QA15-01); plus probes for history (QA15-07), outage, PDF
content, and audit rows. The other findings come from reviewing screenshots and the PDFs.

## Findings

| ID | Sev. | Role / page | Finding | Reproduction | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA15-01 | Medium | Coordinator, Principal, Parent / every page with a download button | Keyboard focus is lost after a download | 1. Tab to "Download school report (PDF)". 2. Press Enter. 3. Wait for "Report downloaded." 4. Press Tab or Enter again | Focus stays on the button (WCAG 2.4.3; ENH-021 QA-06 precedent) | `document.activeElement` is `<body>`; a second Enter/Space does nothing; Tab restarts from the top of the page. Same after a mouse click. Cause (observed): the button is `disabled` while busy, and a disabled element loses focus | Checks COORD-05, COORD-11a; probe: before Enter `BUTTON:Download school report (PDF)`, right after the download event `BODY` |
| QA15-02 | Medium | Parent (any reader) / progress report PDF | A non-Latin (Devanagari) student name is unreadable in the PDF | Parent → child "आशा राव" → Download progress report | The student's name is legible | Name row prints `■■■ ■■■` (built-in Helvetica has no Devanagari glyphs). Recorded as a known limitation in spec §12, but the lost field is the student's name, likely common for Indian schools | PDF `out/1790693683921-progress-report.pdf` page 1 |
| QA15-03 | Low | Parent / `/school/parent/children/{id}` at ≥ 768 px | A download message inside the action row stretches the neighbouring buttons and shifts the page | Force any message (success or error) at 1440 or 768 px | The message appears without resizing "Open 360° view" / "Back to my children" | Both neighbours grow to ~2× height; the row pushes the page down | `out/layout-parent-1440.png`, `out/layout-parent-768.png` |
| QA15-04 | Low | Coordinator, Principal / Reports page | The new card dominates the page | Open Reports at 1440×900 | The report stays the page's focus; the download is a secondary action | "Download reports" is the first and largest heading on a page with no `h1` (h2 at the global 28–44 px size), and a double gap (~60 px) separates it from the KPI tiles (two `.portal-content` wrappers) | `out/coord-reports-1440.png` |
| QA15-05 | Low | Any reader / progress report PDF | Page-break layout | Download a populated report (and one with no records) | Record tables and headings stay with their content | The "Academic results" record splits across pages 1–2 (Subject/Term on p1); on an empty report the "Digital skills" heading is stranded at the foot of p1 | `out/1790693666889-progress-report.pdf`, `out/1790693683921-progress-report.pdf` |
| QA15-06 | Low | Any reader / progress report PDF | Wording/formatting | Download the populated report | Readable labels, no apparent contradictions | Raw enum "ielts" for the test type; the section line "Status: Completed" sits directly above a record whose Status row is "Follow up required" (same rule as the on-screen tile, but adjacent in print it reads as a contradiction); "Status:" line touches the table below it | `out/1790693666889-progress-report.pdf` |

### Observations — pre-existing, not introduced by ENH-015 (recorded, not in scope for the fix pass without a decision)

| ID | Sev. | Finding | Evidence |
|---|---|---|---|
| QA15-07 | Medium (shared) | Open any school page from the sidebar → reload → Back → Forward: within ~3 s the content reverts to the Dashboard while the URL stays on the page. Reproduced on Reports and on ENH-017 Global Education with no interaction at all. The download button disappears as a consequence | Probe `debug_history.mjs`: "after forward: Download reports …" → "after 3 s idle: School at a glance …"; screenshot `out/debug-before-space.png` |
| QA15-08 | Low | A principal can open `/school/coordinator/reports` and gets the coordinator shell and nav (the page has no role check). No data exposure — the principal may read the same report — but the new download button appears there too | Check PRIN-03 |
| QA15-09 | Low | "Grade/Class" shows "-" for a student with only `grade_level` set (screen and PDF alike), and the on-screen "Students by grade" chart (by `grade_or_class`: Grade 12 = 1, Unspecified = 25) disagrees with the ENH-016 grade-wise table that the PDF uses (by `grade_level`: 4/6/5/5/5/1) | `out/coord-reports-1440.png`; school PDF |
| QA15-10 | Low / `NEEDS_CONFIRMATION` | The generated PDFs are untagged (no document structure), so screen readers get no headings or table semantics. No accessibility requirement for documents has been decided | reportlab default output |

## Passed checks (summary)

- **Happy path:** coordinator and principal reach Reports from the sidebar, download `school-report.pdf` (0.2–0.9 s);
  coordinator and principal download a student's `progress-report.pdf` from the student page; the parent downloads
  their own child's report, a Devanagari-named child's, a markup-named child's and a linked child at another school.
  "Report downloaded." is announced (`role=status`); the URL never changes.
- **PDF content:** School Summary figures equal the on-screen dashboard (26 / 12 / 8 / 7 / 1 / 1); grade table
  8–12 + "No grade"; D5 estimates footnoted; empty school → zeros + "No students on the roster yet."; 1,200-student
  school → 1200 / 400 in 230 ms. Progress report: published result only; no `PLANTED` value anywhere in the PDF bytes
  (draft, verified, report URL, application notes); `<b>`, `&`, `<font>`, `<reasoning>`, a lone `<` render literally;
  the bell character is stripped; line breaks kept.
- **Errors:** 500 / 502 / 200-HTML / network drop → "Something went wrong on our side. Please try again."; 403 → the
  server's detail; real 401 → "Your session has expired. Sign in again." (no redirect); real API outage → the generic
  message after ~5.7 s; the button is re-enabled after every error and a retry succeeds.
- **Loading / duplicate:** "Preparing PDF…", disabled, `aria-busy="true"`; a double-click sends one request and saves
  one file.
- **Refresh / back / forward:** refresh clears the message and never re-downloads; back → dashboard, forward → Reports
  (see QA15-07 for the reload-then-history case).
- **Authorization:** teacher, academic team, career counselor, psychometric team, overseas admin, super admin, IT admin →
  403 on both endpoints (403 also for `not-a-uuid`) and no button on the Reports URL; signed out → 401/401 and no button;
  unlinked coordinator → 403 "This account is not linked to a school"; coordinator on another school's student → page
  without a button, API 403; unlinked sibling (parent) → access card, API 403; parent on the school summary → 403;
  malformed id → 422 (allowed role), unknown id → 404; a `school_id` query parameter is ignored.
- **Headers:** `application/pdf`, `attachment; filename="school-report.pdf"`, `private, no-store`, `nosniff`.
- **Audit:** exactly one `school.progress_report_download` row per real download (coordinator 1, principal 1, parent 1),
  metadata `{"role": …}` only; intercepted error paths wrote nothing.
- **Layouts:** no page-level horizontal overflow and the button and its message within the viewport at
  1440/1024/768/390/320 on the Reports page, the parent child page and the coordinator student page.
- **Console / network / images / redirects:** no console errors in normal use (the only errors are the deliberately
  injected 4xx/5xx and the real 401); no failed requests other than aborted Next.js link prefetches during navigation;
  no broken images; no unexpected redirects.

## Fix pass and browser re-test (2026-09-30)

Fixed test-first (a failing unit/API test for each before the change): QA15-01 at `be8c217` (`aria-disabled` plus an
in-flight ref instead of `disabled`); QA15-03, QA15-04, QA15-05, QA15-06 and QA15-08 at `dd0ed71`.

| ID | Fix | Re-test (web and API rebuilt at `dd0ed71`; same isolated stack and data) |
|---|---|---|
| QA15-01 | Button stays focusable while busy; a ref blocks a second request | Focus stays on the button after mouse and keyboard downloads at 1440 and 768 (COORD-05 and COORD-11a now pass) |
| QA15-03 | Parent action row `align-items: flex-start` | "Open 360° view" / "Back to my children" stay 49.25 px tall with the message shown, at 1440 and 768 |
| QA15-04 | `.report-downloads`: 22 px heading, no second `.portal-content` bottom padding | Card 169 px tall; a single 30 px gap; the report's KPI tiles start at y = 297 (was ~360) |
| QA15-05 | Each record in `KeepTogether`; a section heading and its status stay with the first record / "No records yet." | No record split across pages; no heading at a page foot (a unit test sweeps 0–20 results; populated and empty PDFs inspected) |
| QA15-06 | "Overall status: …" section line with spacing below it; test type in capitals, as on screen | PDFs read "Overall status: Completed" above the record's own "Status" row; "IELTS" |
| QA15-08 | Each Reports page refuses the other school role with the access card (`accessDenied`) before reading the report | Principal on the coordinator URL → "Access unavailable · School Coordinator role required", with a link to the principal dashboard; the reverse → "Principal role required" |

**Regression:** the full first-pass script re-run → 101/101 pass (after correcting one script locator that picked Next.js's
hidden route announcer instead of the form message). Backend ENH-015 tests: 53 pass. Web unit suite: 1058 pass.
Typecheck and lint clean.

### Second fix pass (2026-09-30, `398e240`)

- **"Career guidance" mismatch — fixed on the PDF side.** The on-screen `/school/reports` panel's "Career guidance"
  counts students with any career record; the PDF's figure counts completed guidance sessions. The two counts are both
  correct under their own rules. The PDF now uses the wording of the dashboard KPI tiles that count exactly the same
  students ("Career Guidance Completed", "Psychometric Tests Completed", "Individual Counselling Completed", "Students in
  Global Education Pathway", plus "Students in Skills Programs"). A new API test pins each PDF figure to the dashboard
  tile of the same name.
- **QA15-09 — fixed on the PDF side.** "Grade / class" falls back to "Grade N" when only `grade_level` is stored. The
  on-screen "Grade/Class: -" and the Reports panel's "Students by grade" chart (by `grade_or_class`) belong to SCH-007
  and SCH reports, whose API shapes are pinned. They are unchanged here and stay open for their owners.
- **QA15-07 — root cause found; external; downgraded to Low.** Instrumented trace (history API, popstate, RSC requests):
  1. Back → Next.js starts fetching the dashboard's RSC payload (its client cache is empty after the reload).
  2. Forward, 5 ms later, while that fetch is in flight → Reports renders correctly.
  3. ~280 ms later the stale dashboard response arrives. Next.js 15.5.24 commits it anyway (`replaceState` with the
     dashboard tree at the `/reports` URL).

  It is a router race in the framework, reproducible only when Forward follows Back before the Back target has loaded.
  With a 1.5 s pause between Back and Forward it does not occur (verified). No app code is involved; there is no app-side
  fix worth its risk. A framework upgrade is a separate decision.

### Third fix pass (2026-09-30) — the two decisions

- **QA15-02 — fixed (user chose font + `uharfbuzz`).**
  - Devanagari is set in the bundled Noto Sans Devanagari (SIL OFL) and shaped by `uharfbuzz` 0.56.2. That is the
    one new dependency, a manylinux wheel that installs through the project Dockerfile.
  - Found while checking by eye: a Devanagari `<font>` run inside a Helvetica paragraph is **not** shaped (vowel
    signs land in the wrong place). So a paragraph containing Devanagari is based on the Devanagari font, and its
    Latin runs go back to Helvetica. A unit test pins that mechanism.
  - Re-test:
    - The parent downloads "आशा राव"'s report through the UI. The name and mixed notes ("छात्रा ने विज्ञान में
      रुचि दिखाई। Likes <robotics> & क्षेत्रीय प्रतियोगिता") render correctly.
    - Latin-only PDFs embed no extra font.
  - Remaining limitations (spec §12): other Indian scripts; copy/paste of Devanagari out of the PDF.
- **QA15-10 — accepted with a pointer (user decision).**
  - Each download button shows a hint, which is also its `aria-describedby` description, naming where the same content
    can be read accessibly:
    - Reports pages: the dashboard and the grade-wise comparison.
    - Coordinator/principal student pages: the 360° view.
    - Parent child page: this page.
  - Re-test: the description is read from the button; no overflow at 1440 or 320 px.

All QA findings are now resolved, except QA15-07 (Low, a Next.js framework race, documented above). The on-screen
grade display and the Reports panel's "Students by grade" chart (QA15-09, screen side) belong to SCH-007 and SCH reports,
not ENH-015.

## Final browser verification (2026-09-30, at `48e9db5`; no source code changed)

**Setup and scope**
- **Environment:** web and API rebuilt at `48e9db5` (`uharfbuzz` 0.56.2 installed from `requirements.txt`, plus the local
  `greenlet` addition — RAID `I-42`); same isolated stack and data. Headless Chromium, a fresh context per role.
- **Checks run:**
  - A new acceptance-criteria script: 28 browser checks, plus 17 checks on the downloaded PDFs and the API logs.
  - The full first-pass regression: 101 checks.
  - The two fix re-tests: 7 and 6 checks. The QA15-10 re-test first failed on a stale script locator (`.report-hint`,
    replaced by `.field-hint` in `48e9db5`). After the locator was corrected, all 6 checks pass.

| AC | Result | Browser evidence |
|---|---|---|
| AC01 | **PASS** | Coordinator: sidebar → Reports → `school-report.pdf`. PDF figures equal the dashboard tiles of the same name (26 / 12 / 8 / 7 / 1). Every grade-table cell equals `GET /school/analytics/grade-performance`. |
| AC02 | **PASS** | The principal downloads the same figures. Teacher, parent, academic_team, career_counselor, psychometric_team, overseas_admin, super_admin and it_admin all get 403, and no button appears on the Reports URL. A coordinator with no school gets 403 "This account is not linked to a school". Signed out: 401/401. |
| AC03 | **PASS** | School B's PDF: its own name and 1 student, nothing from School A. Empty school: zeros and "No students on the roster yet." A tampered `school_id` query parameter is ignored. |
| AC04 | **PASS** | Parent: own child and a linked child at another school → 200. Unlinked sibling → no button, API 403. Coordinator/principal: own-school students → 200; other school 403; unknown 404; malformed 422. Wrong roles get 403 even for `not-a-uuid`. |
| AC05 | **PASS** | Each PDF holds only that child's data and published Mathematics (92.5 / 100). No `PLANTED` value (draft result, verified result, report URL, application notes) appears anywhere in the PDF bytes. |
| AC06 | **PASS** — fail-closed clause **NOT TESTABLE** | The audit-row delta equals the real downloads: kid 4, sibling 1, other-school child 1; refusals wrote none. Metadata is `{"role": …}` only. A failed audit write cannot be induced from the browser; the API tests cover it. |
| AC07 | **PASS** | Both endpoints return `application/pdf`, the fixed attachment filename, `private, no-store`, `nosniff` and `default-src 'none'; sandbox`. |
| AC08 | **PASS** | `<b>engineering</b>`, `<font color=red>ok</font>`, `Strong <reasoning>` and a lone `<` print literally in the PDF. |
| AC09 | **NOT TESTABLE** | The query count is not observable from a browser; the API test covers it. Observed: the 1,200-student school's PDF in 169 ms and the 26-student school's in about 150 ms. |
| AC10 | **PASS** | Busy state ("Preparing PDF…", `aria-disabled`, `aria-busy`). Success message. Error messages for 500, 502, 403, a 200 HTML page, a network drop and a real 401. Retry works. Enter and Space download, and focus stays on the button. Double-click → one request. No overflow at 1440, 1024, 768, 390 and 320. |
| AC11 | **PASS** | Coordinator, principal and parent sidebars are unchanged. The Reports panel and analytics render. `/school/reports` and `/overview` keep their shapes (no `report_url`). |
| AC12 | **PASS** | The API container's 13 `school_report_*` log lines hold ids and counts only; no student or school names. |

**Previous defects:** QA15-01, 02, 03, 04, 05, 06, 08, 09 (PDF side) and 10 all **PASS** on re-test. QA15-07 still
reproduces 5 out of 5 times when Forward follows Back with no pause (known framework race, Low, outside the ACs).

**Console and network:** in normal use, no console errors, no failed requests and no unexpected redirects. Every error
recorded was either one deliberately injected by the test (6 × 500, 11 × 403, 1 × 502, the network drop) or the real
session-expiry 401.

**New, Low — QA15-11:** on the coordinator and principal Reports cards (and the student cards), the hint's `max-width:
42ch` (meant for the parent's button row) wraps it into three short lines, with a break inside "grade-wise". That makes
the card about 67 px taller (236 px vs 169 px), so the report starts at y ≈ 364. Suggested fix: apply the 42ch cap only
inside the parent action row. Not changed in this pass.

**QA15-11 — fixed (2026-09-30).** The 42ch cap now applies only inside the parent child page's action row (a new
`child-page-actions` class; a placement test pins it). Elsewhere the hint runs at full card width.

Browser re-test, with only the web image rebuilt:
- **Cards (coordinator/principal Reports and student pages):** `max-width: none`.
- **1440 px:** the hint is one line on all four cards; the Reports card is 195 px (was 236), and the report starts at
  y = 323 (was 364).
- **768 px:** the longer Reports hint wraps naturally at the full card width (658 px, 2 lines); the student cards stay
  at one line.
- **390 and 320 px:** natural wrapping, no overflow.
- **Parent row:** still capped (294 px, 2 lines); QA15-03 neighbour heights unchanged (49.25 px).
- **Regression:** the layout section (30/30) and the QA15-01/03/04/08/10 re-tests all pass. Web unit suite: 1066 pass.

## Completion verification (2026-09-30, at `d38dff6`; every item re-run fresh)

**Tests**

| Check | Result |
|---|---|
| Backend, full suite | 1890 passed, 15 failed. All 15 are outside ENH-015: 11 Razorpay and 3 Zoho tests need real credentials, and 1 `test_enh_003` user-count check was disturbed by concurrent Playwright runs on the shared DB. That file passes 96/96 when run alone. |
| Web unit tests | 1066/1066 |
| `tsc --noEmit` | exit 0 |
| `eslint` | exit 0: 0 errors; 31 pre-existing warnings, none in ENH-015 files (`--max-warnings 0` on them passes) |
| `next build` | exit 0 |

**Code quality, compared with `main`**

| Check | Result |
|---|---|
| ruff | 37 = 37 errors |
| ruff format | 98 = 98 files |
| mypy | 221 = 221 errors |
| ENH-015 modules | clean on all three |

**Playwright**

| Spec | Result |
|---|---|
| `enh-015-reports-downloads` | passes |
| `sch-reports`, `enh-016-analytics`, `enh-017-global-education` | pass |
| `sch-007-parent-portal` | fails, identically on a production build of `main` (`407cbd7`) on a side port: a strict-mode violation on two "Career guidance" headings (`SchoolChildOverview` `<h3>` and ENH-012 `PortfolioPanel` `<h4>`). Pre-existing; neither component is changed by ENH-015. |

**Browser verification**
- AC checks: 28/28 in the browser and 17/17 on PDF contents and API logs.
- Regression: 101/101; fix re-tests 7/7 and 6/6.
- QA15-11: re-test passes. Its two 768 px flags are the script's one-line threshold; the width cap is gone, and two lines at the full card width is natural wrapping.

**Accessibility:** axe-core WCAG 2.0/2.1 A+AA, 20 scans (5 pages × 1440/390, plus success and error states at 1440).
0 violations in ENH-015 elements. Existing page violations are all in untouched components:
- `color-contrast` on SCH-008 timeline badges;
- `scrollable-region-focusable` on ENH-016 analytics tables and overview tables.

**Safety and hygiene**
- No skipped, focused or disabled tests; no debugging code; no secret-like strings; no `.env` tracked.
- No migration. `alembic check` reports `remove_index ix_schools_school_code`, which is identical on `main`: pre-existing drift.
- All 33 changed files belong to ENH-015. Shared-file edits: `grade_table` extraction, the `_active_academic_year`
  helper, router registration, the `uharfbuzz` requirement.

**Verdict:** ENH-015 **slice 1 is complete**. §30's other report types, the per-year Annual report and scholarship
figures are later slices (`NEEDS_CONFIRMATION`). Open, outside ENH-015: QA15-07 (Next.js router race), the pre-existing
`sch-007` spec and `alembic check` drift, and the existing axe findings above.
