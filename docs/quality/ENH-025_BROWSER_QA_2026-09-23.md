# ENH-025 — Browser QA record (2026-09-23)

**Feature:** ENH-025 Student Master field coverage (`DEC-SCOPE-027`).
**Build under test:** branch `feature/enh-025-student-master-field-coverage`, code at `88d14b2` plus the CSS fixes below.
**Environment:** isolated Docker stack `enh025` (web `http://localhost:3025`, API `:8025`), `python -m app.seed` applied,
Chromium (Playwright, headless), desktop 1280×900 and phone 375×800.
**Method:** `docs/quality/ENH-025_browser_qa.py`. Setup (a new school, coordinator, teacher, parent and career
counsellor per run) goes through the same API calls the e2e helpers use; every ENH-025 behaviour is then exercised
through the real UI. Console errors, page errors and every HTTP response ≥ 400 are captured. Screenshots were
reviewed by eye as well as asserted.

## Result: 18 / 18 checks PASS (final run)

| # | Check | AC | Result | Evidence |
|---|---|---|---|---|
| 1 | Coordinator creates a student with the new fields | AC1 | PASS | section/roll/gender/mobile/city/subjects saved; row shows Section A, Roll 7; parent linked; Add button keeps natural width |
| 2 | Edit form: grouped, prefilled, keyboard focus | AC1/AC11 | PASS | four legends; values prefilled (teacher kept); heading focused on open; Tab → Full name; save → message on roster; focus returns to Edit; Section and Roll inputs same height |
| 3 | Saving the edit form untouched keeps every value | AC7 | PASS | city, subjects, career interests, teacher unchanged (read back from the API) |
| 4 | Roll-number clash reported in the form | AC5 | PASS | 409 text shown as an alert in the Add card; section "a" treated as "A" |
| 5 | Invalid field rejected with a field-named message | AC2 | PASS | `student_mobile must be 7-20 characters…`; typed value not echoed |
| 6 | Profile + photo upload (coordinator) | AC1/AC8 | PASS | Female / Maths, Physics shown; initials placeholder before upload; PNG rendered (naturalWidth > 0) |
| 7 | Photo response headers, no key leak | AC8/AC12 | PASS | `image/png`, `private, no-store`, `nosniff`, `default-src 'none'; sandbox`; student JSON carries `has_photo` only |
| 8 | Wrong photo type rejected before upload | AC12 | PASS | GIF → "Choose a JPEG or PNG image." and no request sent |
| 9 | Photo removal needs confirmation | AC8 | PASS | Cancel keeps it; Confirm remove → initials placeholder |
| 10 | Bulk upload with the new columns | AC1/AC2/AC6 | PASS | Column reference incl. the photo note; 1 accepted / 1 rejected (gender message); roster shows section B |
| 11 | Teacher (assigned) reads profile and photo | AC8 | PASS | profile + photo visible; no upload control |
| 12 | Teacher scope unchanged | AC8 | PASS | unassigned student absent from the teacher's list |
| 13 | Parent (linked) sees photo, section, roll | AC8 | PASS | photo + "Section / Roll number: A / 7" |
| 14 | Counsellor records career preferences | AC9 | PASS | loads the coordinator's interests, saves countries; 16 px field spacing; counsellor gets 403 on the photo |
| 15 | Counsellor edit visible to the coordinator | AC9 | PASS | "Germany, Canada" on the coordinator's profile |
| 16 | Photo requires a session | AC12 | PASS | no cookie → 401 |
| 17 | Roster edit form at 375 px | AC11 | PASS | fields stacked; `scrollWidth` 375 |
| 18 | Student profile at 375 px | AC11 | PASS | photo above the profile list; `scrollWidth` 375 |

**Console:** two entries, both the browser's automatic "Failed to load resource" line for the deliberately provoked
409 (check 4) and 422 (check 5). No page errors. **Network:** no unexpected HTTP ≥ 400.

## Defects found by this QA and fixed (each reproduced by a failing browser check first)

1. **Section input taller than Roll number** (62 px vs 49 px): the Roll field's help text stretched its grid row.
   Fix: `fieldset.form-section .form-grid { align-items: start; }`.
2. **No spacing between counsellor-card fields** (0 px): the busy-state `fieldset` wrapper swallowed `.form`'s gap.
   Fix: `fieldset.form-busy-wrap { display: grid; gap: 16px; }` and the section fieldsets' bottom margin removed
   (the gap now spaces them).
3. **Submit buttons stretched full width** (904 px) — a side effect of fix 2. Fix:
   `fieldset.form-busy-wrap > .btn { justify-self: start; }`.

After the fixes: browser QA 18/18; Playwright `enh-025` 2/2, `sch-002` 2/2, `sch-team-management` 2/2.

## Harness issues (not product defects)

- The first run's `print` crashed on "→"/"≤" in the Windows console (fixed with `PYTHONIOENCODING=utf-8`).
- An unscoped `get_by_role("alert")` also matched Next.js's own route-announcer alert; the check is now scoped to the
  photo block. The screenshot showed the product message correctly both times.

## Not tested in the browser (and why)

- **Grade history after promotion / hold-back (AC10):** needs a new active academic year, which no UI in this stack
  creates; covered by `test_enh_025_lifecycle.py` and `SchoolGradeHistory.test.tsx`.
- **Migration backfill (AC3):** database-level; covered by `test_enh_025_migration.py` and the recorded
  `grade_or_class` fingerprint.
- **Concurrent roll-number creates (AC5):** one browser cannot race itself; covered by the backend concurrency test.
- Browsers other than Chromium, screen readers, real touch devices, S3 storage mode.

## Observations (pre-existing, not changed)

- The roster's "Parent" column shows "-" for a student linked to an existing parent account; it only ever showed
  pending invites (SCH-001 behaviour).
- Full-page screenshots draw the fixed sidebar/top bar at the scroll position — a screenshot artefact, not a layout bug.

**Status:** browser validation for ENH-025 **PASS**. ENH-025 is still **not complete** — the independent Codex
review is pending.
