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
