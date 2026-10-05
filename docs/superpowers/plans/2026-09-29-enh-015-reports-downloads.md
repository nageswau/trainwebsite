# ENH-015 Reports & Downloads (slice 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coordinators/Principals download a School Summary PDF of their own school; Parents (and own-school
Coordinators/Principals) download a Student Progress Report PDF of one student.

**Architecture:** A pure renderer (`app/reporting/pdf.py`, dict → PDF bytes, reportlab Platypus) behind a new router
(`app/api/school_reports.py`) that reuses the existing scope loaders and read helpers. Nothing stored; generated per
request. One behaviour-preserving extraction (`grade_table`) in `school_analytics.py`. Frontend: one client
`ReportDownloadButton` placed on four existing pages.

**Tech Stack:** FastAPI, SQLAlchemy async, reportlab 4 (existing), pytest + httpx ASGI, Next.js 15 / React 19, vitest,
Playwright.

**Spec:** `docs/superpowers/specs/2026-09-29-enh-015-reports-downloads-design.md`

## Global Constraints

- No new dependency (backend or frontend). No migration. No stored files.
- `/school/reports`, `/school/dashboard`, `/school/analytics/grade-performance`, `/school/students/{id}/overview` responses
  byte-for-byte unchanged; `SCHOOL_NAV` and `PORTAL_NAV` unchanged.
- Roles: summary = `school_coordinator`, `school_principal`; progress report = those two + `school_parent`.
- Filenames fixed: `school-report.pdf`, `progress-report.pdf`.
- Response headers = `portfolio_certificates.HEADERS` + `Content-Disposition: attachment; filename="..."`.
- Audit: `AuditLog(action="school.progress_report_download", entity_type="school_student", entity_id=<student id>,
  metadata_json={"role": <role>})` committed before the response. Summary: log line only.
- Logs: ids, role, counts, bytes, ms, exception type — never names or record text.
- UI copy: "Download school report (PDF)", "Download progress report (PDF)", "Preparing PDF…", "Report downloaded.",
  "Your session has expired. Sign in again.", "Something went wrong on our side. Please try again."
- Test runner (local): the `enh015-api-test-greenlet` image (see "Environment" below).

## Environment

The CI image resolved SQLAlchemy 2.1.1, which no longer pulls `greenlet`; a local derived image adds it (repo unchanged —
reported separately as a pre-existing CI risk). Run backend tests from the worktree root:

```bash
MSYS_NO_PATHCONV=1 docker run --rm --network enh015_default --env-file <scratchpad>/ci.env \
  -v "<worktree>/apps/api:/app" enh015-api-test-greenlet python -m pytest -q -p no:cacheprovider <files>
```

Frontend: `cd apps/web && npm ci` once, then `npx vitest run <files>`, `npm run typecheck`, `npm run lint`.

## Review Focus

1. Stored text containing `<`, `&`, `<font>` or a lone `<` (counsellor notes, remarks) → rendered literally, no 500.
   Pinned in Task 1 (`test_markup_in_text_is_rendered_literally`).
2. Non-Latin names (Devanagari) → generation must not crash (glyphs may be boxes — known limitation). Pinned in Task 1
   (`test_non_latin_text_does_not_break_generation`).
3. A school with zero students / a student with no records → a valid PDF saying so, not a 500. Pinned in Tasks 1, 3.
4. A parent linked to children at two schools → only the requested linked child; an unlinked child at the same school
   → 403. Pinned in Task 4.
5. Draft/Verified results or `report_url` leaking into the PDF. Pinned in Task 4.

---

### Task 1: PDF renderer

**Files:**
- Create: `apps/api/app/reporting/pdf.py`
- Create: `apps/api/tests/pdf_text.py` (test helper: text extraction from reportlab output, stdlib `zlib` only)
- Test: `apps/api/tests/test_enh_015_pdf.py`

**Interfaces:**
- Produces: `render_school_summary(data: dict) -> bytes`; `render_progress_report(overview: dict, as_of: date) -> bytes`;
  test helper `pdf_text(data: bytes) -> str`.
- Summary `data` keys: `school_name: str`, `as_of: date`, `academic_year: str | None`, `total_students: int`,
  `kpis: list[tuple[str, int]]`, `grades: list[str]`, `students: dict[str, int]`,
  `metrics: list[dict]` (each `{"label", "is_proxy", "definition", "cells": {grade: {"count", "pct"}}}`).
- Progress `overview` = the dict `_overview_payload` returns.

- [ ] **Step 1: Write the test helper** `tests/pdf_text.py`:

```python
"""Plain text of a reportlab PDF, for assertions (stdlib only -- no PDF library is a dependency)."""
import re
import zlib

_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
_SHOW = re.compile(rb"\(((?:\\.|[^\\)])*)\)\s*Tj")


def pdf_text(data: bytes) -> str:
    out = []
    for raw in _STREAM.findall(data):
        try:
            content = zlib.decompress(raw)
        except zlib.error:
            content = raw
        for text in _SHOW.findall(content):
            out.append(re.sub(rb"\\(.)", rb"\1", text).decode("latin-1"))
    return "\n".join(out)
```

- [ ] **Step 2: Write the failing tests** `tests/test_enh_015_pdf.py`: summary renders title/school/KPIs/grade table;
  empty roster message; progress report renders student + sections + "No records yet"; markup rendered literally;
  non-Latin text does not raise; result starts with `%PDF-`.
- [ ] **Step 3: Run** — expect `ModuleNotFoundError: app.reporting.pdf`.
- [ ] **Step 4: Implement** `app/reporting/pdf.py`: Platypus `SimpleDocTemplate(A4)`; single escape choke point
  `_p(value, style)` = `Paragraph(escape(_text(value)).replace("\n", "<br/>"), style)`; `_text` formats None/bool/date/
  datetime/float/list; control characters stripped; field lists per overview section; `_record_table` of label/value rows
  for non-empty values only.
- [ ] **Step 5: Run** — all pass. **Refactor**, re-run. **Commit** `feat(enh-015): PDF renderer for school summary and progress report`.

### Task 2: Extract `grade_table` (behaviour-preserving)

**Files:**
- Modify: `apps/api/app/api/school_analytics.py` (`grade_performance`)
- Test: existing `tests/test_enh_016_school_analytics.py`, `tests/test_enh_016_scope.py`

**Interfaces:**
- Produces: `grade_table(roster: Sequence, indicators: dict[str, set[UUID]]) -> GradePerformanceOut`.

- [ ] **Step 1:** Run the two existing files — green (baseline).
- [ ] **Step 2:** Move the loop body into `grade_table`; the route becomes
  `roster = await _roster(...)`, `indicators = await student_indicators(...)`, `out = grade_table(roster, indicators)`, log,
  `return out`.
- [ ] **Step 3:** Re-run — green, no test edits. **Commit** `refactor(enh-015): extract grade_table from grade_performance`.

### Task 3: School Summary endpoint

**Files:**
- Create: `apps/api/app/api/school_reports.py`
- Modify: `apps/api/app/main.py` (import + router tuple)
- Test: `apps/api/tests/test_enh_015_school_summary.py`

**Interfaces:**
- Consumes: `render_school_summary`, `grade_table`, `_roster`, `student_indicators`, `students_in`,
  `_require_school_reader`, `_own_school_id`, `_today_ist`, `portfolio_certificates.HEADERS`.
- Produces: `GET /api/v1/school/reports/school-summary`; `school_summary_data(db, school_id) -> dict`.

- [ ] **Step 1: Failing tests:** 200 + headers + `%PDF-` for coordinator and principal; 403 for teacher, parent,
  academic_team, career_counselor, psychometric_team, it_admin, overseas_admin, super_admin; 403 unlinked account; 401
  anonymous; figures in text equal seeded counts; other school's student not counted; grade table equals
  `/school/analytics/grade-performance`; empty school renders "No students on the roster yet."; statement count equal for
  1 and 15 students; one `school_report_generated` log with ids/counts only; OpenAPI documents `application/pdf`.
- [ ] **Step 2: Run** — 404 Not Found (route absent).
- [ ] **Step 3: Implement** router + `school_summary_data` + registration.
- [ ] **Step 4: Run** — pass; re-run Task 2 files. **Commit** `feat(enh-015): school summary PDF endpoint`.

### Task 4: Student Progress Report endpoint

**Files:**
- Modify: `apps/api/app/api/school_reports.py`
- Test: `apps/api/tests/test_enh_015_progress_report.py`

**Interfaces:**
- Consumes: `render_progress_report`, `_load_readable_student`, `_overview_payload`.
- Produces: `GET /api/v1/school/students/{student_id}/progress-report`; dependency `_require_report_reader`.

- [ ] **Step 1: Failing tests:** parent linked → 200; parent unlinked (same school) → 403; coordinator/principal own
  school → 200, other school → 403; unknown id → 404; teacher/service/admin roles → 403 and 403 (not 422) for
  `not-a-uuid`; PDF contains the student's name and a published subject, not a draft subject, not `report_url` value,
  not another student's name; exactly one audit row with `{"role": ...}`; audit write failure (monkeypatch `AuditLog`)
  → request raises and no PDF; render failure (monkeypatch renderer) → 500 `{"detail": "Could not generate the report;
  please try again"}` and no audit row; headers; one log line ids-only.
- [ ] **Step 2: Run** — 404 Not Found.
- [ ] **Step 3: Implement** route: role dependency → loader → overview → render (try/except → log type, 500) →
  `db.add(AuditLog)` → `commit` → response; log line.
- [ ] **Step 4: Run** Tasks 1–4 files + `test_sch_007_parent_portal.py`, `test_sch_001_school_portal_access.py`,
  `test_sch_reports.py`, `test_uuid_contracts.py`. **Commit** `feat(enh-015): student progress report PDF endpoint`.

### Task 5: `ReportDownloadButton`

**Files:**
- Create: `apps/web/components/ReportDownloadButton.tsx`
- Test: `apps/web/tests/components/ReportDownloadButton.test.tsx`

**Interfaces:**
- Produces: `default function ReportDownloadButton({ url, label, filename }: { url: string; label: string; filename: string })`.

- [ ] **Step 1: Failing tests** (mock `global.fetch`, `URL.createObjectURL`/`revokeObjectURL`): success → anchor clicked
  with `download=filename`, "Report downloaded." status, URL revoked; busy → button disabled + "Preparing PDF…" +
  `aria-busy`; 401 → session message; 403 → server detail; 500 → generic; network reject → generic; 200 non-PDF → generic;
  button re-enabled after an error.
- [ ] **Step 2: Run** — cannot resolve module.
- [ ] **Step 3: Implement** (client component; `detailMessage`, `FormMessage`).
- [ ] **Step 4: Run** — pass; typecheck + lint. **Commit** `feat(enh-015): report download button`.

### Task 6: Place the buttons

**Files:**
- Modify: `apps/web/app/school/coordinator/reports/page.tsx`, `apps/web/app/school/principal/reports/page.tsx`,
  `apps/web/app/school/parent/children/[id]/page.tsx`, `apps/web/app/school/coordinator/students/[id]/page.tsx`,
  `apps/web/app/school/principal/students/[id]/page.tsx`
- Test: `apps/web/tests/components/Enh015ReportPlacement.test.tsx`

- [ ] **Step 1: Failing tests** (existing page-test pattern: `vi.mock("@/lib/api")`, stub `PortalShell`): each page
  renders the button with the right label and URL.
- [ ] **Step 2: Run** — fail (button absent).
- [ ] **Step 3: Implement** placements (card with `<h2>Download reports</h2>` on Reports pages; button in existing action
  rows elsewhere).
- [ ] **Step 4: Run** the new test + existing page tests (`SchoolAnalyticsSections`, `Enh016QaFixes`, `PortalShell`,
  `skills`), typecheck, lint. **Commit** `feat(enh-015): report download buttons on school pages`.

### Task 7: E2E + documentation

**Files:**
- Create: `apps/web/tests/e2e/enh-015-reports-downloads.spec.ts`
- Modify: docs listed in spec §14; `docs/delivery/ENHANCEMENT_BACKLOG.md` status "IMPLEMENTED — NOT YET COMPLETE
  (browser validation + independent review pending)".

- [ ] **Step 1:** E2E: coordinator clicks "Download school report (PDF)" → `page.waitForEvent("download")` filename
  `school-report.pdf`; parent on child page downloads `progress-report.pdf`; teacher API request to the summary → 403.
- [ ] **Step 2:** Run only if the full stack is up (browser validation phase); otherwise record as pending.
- [ ] **Step 3:** Docs. **Commit** `docs(enh-015): contracts, RBAC, security, AC addendum, RTM`.
