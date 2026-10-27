# nehn-013 — CRM report gaps: lost, conversion rate, counselor-wise, date-wise, follow-ups (design)

Source: `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` §nehn-013 (EVID §16 L405-419, §14 L304-305). Decision: `DEC-SCOPE-301`.
Dependency nehn-004 (xlsx) is Done (PR #349), so every new report gets the CSV and Excel downloads for free.
The owner asked that the build proceed on the recommended answers. Every open definition below is therefore an implementer's call and is
marked `NEEDS_CONFIRMATION` until the client CRM workflow document (CI-01 / nehn-015) arrives.

## Intent

Telecaller managers and admins already have six reports on the Telecaller CRM reports page. They cannot yet see how many leads were
lost, the conversion rate, figures per counselor, figures over time, or how the follow-ups stand. This feature adds those to the
existing report framework (`services/telecaller_reports.py`) without changing anything the current reports return. New columns go at
the end, and the existing reports keep their kinds and URLs.

## Decisions (implementer's calls, `NEEDS_CONFIRMATION` where marked)

| # | Call |
|---|---|
| R1 | **Lost** = cohort leads whose *current* stage is a loss stage (`lost`, `not_interested`, i.e. `LOSS_STAGES`, the same as the ccrm-006 Lost Reasons report). A reopened lead is no longer lost. `NEEDS_CONFIRMATION` |
| R2 | **Conversion rate (%)** = Enrolled ÷ Leads × 100, rounded to 1 decimal (Enrolled = still converted now, RP2). The Total row recomputes it from the totals instead of summing it. `NEEDS_CONFIRMATION` |
| R3 | **Date anchor**: the lead's creation date, as in every cohort report today. A lead created in the range but converted after it counts as enrolled. A lead created before the range is not counted. `NEEDS_CONFIRMATION` |
| R4 | `lost` and `conversion_rate` are appended to the funnel reports: source, course (product), campaign and the two new ones. Handover, telecaller (activity) and lost-reasons keep their columns. |
| R5 | **Counselor report** (`counselor`): cohort leads with an owner, grouped by `Enquiry.owner_id`. Columns: Counselor · Leads · Counselling done · Enrolled · Lost · Conversion rate (%). |
| R6 | **Date-wise report** (`date`): cohort leads grouped by IST creation day, week (Monday start) or month. A new `group` parameter takes `day` (the default), `week` or `month`, and any other value is a 422. Rows are in calendar order, and periods with no leads are left out. Columns: Period + the funnel + Lost + Conversion rate. |
| R7 | **Follow-up status** (`follow_ups`): telecaller-side follow-ups (`TELECALLER_FOLLOW_UP`, the dashboard's definition) on leads in the caller's scope, **due in the range**, grouped by the lead's telecaller. Columns: Follow-ups · Completed · Open · Overdue (open and due before now) · Cancelled. |
| R8 | **Pending follow-ups** (`pending_follow_ups`): one row per open follow-up due in the range and before now. Columns: Lead · Telecaller · Due date · Reason · Days overdue (today minus the due date, in IST calendar days). The most overdue come first. The Total row leaves days overdue blank. This is the only report that names a lead, because a manager cannot act on a pending follow-up without the name. The caller already sees these leads on their Leads list. Mobile and email never appear. |
| R9 | The product, campaign, source and team filters apply to every new report, since all of them are per lead. |
| R10 | Access is unchanged: the `reports.telecaller` view and download grants (nehn-005). Telecallers, counselors and other roles get 403. Counselors reading their own figures is `NEEDS_CONFIRMATION` and not built. |

## Non-goals

No schema or migration changes. No change to existing kinds' rows or columns beyond appending (R4). No counselor-facing access.
No charts. The client's final report list (§16 L419) may still change these definitions.

## Phase 3 review (API, frontend, security)

- **API**: the new `kind` values are additive. The `group` query parameter is a plain string, validated after authorization (AGN-020
  order: 403, then 404, then 422). It is accepted, and ignored, on the other kinds. Reads are not audited; exports are audited as today.
- **Performance**: every report is one grouped query, bounded to at most 366 days. Follow-ups use `ix_lead_follow_ups_open_due` and
  `ix_lead_follow_ups_lead`. The pending list is bounded by the range.
- **Security**: scope comes from `lead_scope(user)`, the caller's own Leads list, so there is no IDOR. Output is text nodes only (no
  XSS). The CSV export neutralises formulas (existing `export_response`). Lead names appear only in R8, and mobile and email never do.
- **Frontend**: four new tabs. A Group-by select appears on the Date-wise tab only. Each new tab has its own empty-state message. The
  existing `.table.stack` keeps the table usable on phones, and the GET form needs no client JS.

## Plan (TDD)

1. Backend RED: `tests/test_nehn_013_crm_reports.py` hand-computes fixtures for R1 to R10, plus 403, 422 (`group`) and the CSV header.
2. Backend GREEN: `services/telecaller_reports.py` (columns, kinds, grouping, rate totals) and `api/telecaller_reports.py` (`group`).
3. Update the tel-024 column assertions, which are append-only by design (R4).
4. Frontend RED/GREEN: `lib/telecallerReports.ts` (tabs, `group` param) and `TelecallerReportView.tsx` (group select, empty messages),
   with a vitest test.
5. e2e: `tests/e2e/nehn-013-crm-reports.spec.ts` covers tabs, date grouping, pending list and a phone layout.
6. Docs: decision register, API contract, RBAC, tracker and backlog status.
