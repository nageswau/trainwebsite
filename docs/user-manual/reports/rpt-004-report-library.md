# Report library

> Doc ID: DOC-RPT-004 · Verified 2026-10-27 against `worktree-nehn-009` (`DEC-SCOPE-303`) and `worktree-nehn-010` (`DEC-SCOPE-305`) · Roles: Super Admin; IT Admin; Trainer

## Purpose
Open a report, filter it, page through the rows and download every matching row as CSV or Excel.

## Who Can Use This Feature
- **Super Admin** and **IT Admin**: every enrolment in the Enrollments report.
- **Trainer**: only the students in the batches you train.
- Other roles see a report only after an administrator grants it in the permission matrix (Training reports → View / Download).

## Prerequisites
Your role holds *Training reports — View*. Downloading also needs *Training reports — Download*.

## How to Access
Sidebar > **Report library** (Super Admin: `/admin/report-library`; IT Admin: `/it/admin/report-library`; Trainer:
`/it/trainer/report-library`).

## Steps

### Step 1 — Pick a report
The library lists the reports you may open. Click **Enrollments**.

### Step 2 — Filter
Open **Filters**, fill any of the fields below and click **Apply**. The summary then reads "Filters (N applied)". **Clear filters** resets
the report. Each report shows only the filters it supports.

### Step 3 — Page and download
"Showing 1–50 of N" tells you where you are; use **Previous** / **Next**. **Download CSV** or **Download Excel** saves every row that
matches the filters (not only the page on screen), for example `enrollments-2026-10-27.xlsx`.

## Fields
| Field | Meaning |
|---|---|
| From / To | Enrolment date range; both days included. |
| Course / Batch / Trainer / Status | Pick one from the list (only those you can see are offered). |
| Student | A student code, or part of a name or email. |
| Latest | Only the N most recent enrolments (1–1,000). |
| Completion from / to | The batch end date range. |

## Training reports (nehn-010, `DEC-SCOPE-305`)
Field lists are provisional until the client's report template arrives.

| Report | One row per | Notes |
|---|---|---|
| Student-wise course report | enrolment | Progress, attendance %, assignments graded, assessments passed, certificate. |
| Students per trainer | enrolment | Sorted by trainer, batch, student. |
| Course completion | batch | Students, completed (progress 100%), completion %, certificates. |
| Completions in a period | completed enrolment | Use **Completion from / to** (the batch end date). |
| Attendance | enrolment | Classes marked, present, absent, late, excused, attendance % — the same % certificate eligibility uses. Here **From / To** is the class date. |
| Trainer report | trainer | Batches, students, attendance %, average progress, submissions waiting to be graded. |
| Course-wise report | course | Enrolments, active, completed, dropped; **Revenue (INR)** shows only to roles allowed to see financial columns. |

"—" means there is nothing to measure yet (for example no attendance marked), not 0%.

## Expected Result
The table and the files hold the same columns and rows. Every download is recorded in the audit log with the filters used.

## Errors
- "'From' must be on or before 'To'" — swap the dates.
- "This report has more than 10,000 rows; narrow the filters" — add a filter or a shorter date range.
- "You've downloaded a lot of reports in a short time…" — wait a few minutes (30 downloads per 10 minutes).
- "This page is past the last row." — use **Go to the first page**.
