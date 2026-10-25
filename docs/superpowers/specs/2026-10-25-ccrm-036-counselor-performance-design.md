# ccrm-036 — Counselor's own performance report (design)

NO-ASSUMPTION MODE. Source: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` `ccrm-036` (source PDF §1 "measure counselor performance", §4
conversion rate by counselor; the PDF is `UNVERIFIED` and not in the repository — only the backlog's wording is used). Dependencies
ccrm-029 (counselor tasks, `DEC-SCOPE-250`, PR #312) and ccrm-034 (management CRM reports, `DEC-SCOPE-267`, PR #329) are merged on
`origin/main`.

## Requirement (backlog, verbatim scope)

The counselor sees own leads assigned, follow-up completion, overdue tasks, conversions, applications by sub-status, offers, visas,
enrolments — using the same definitions as `management_counseling.py`, no revenue. Existing behaviour: "My Caseload Report" counts
applications only (`services/portal.py`, the counselor `reports` section).

## Alternatives considered

1. **Grow the portal `reports` section payload** (`{columns, rows, stats}`) — rejected: one table plus flat stats cannot carry a period, the
   definitions or two table shapes, and the CNS-001 tests pin that payload.
2. **Call `/management/counseling` for the counselor** — rejected: that route lists every counselor (names and figures) and is the
   operational tier only; filtering it would still widen the route's audience.
3. **Chosen:** one read-only route `GET /counselor/performance?from&to`, a service `services/counselor_performance.py` that reuses the
   `management_counseling` builders (for one counselor id) and ccrm-034's application predicates, and a dedicated page at
   `/overseas/counselor/reports` (the existing sidebar "Reports" link; a static route wins over `[section]`). Nothing stored, no migration.

## Recommended defaults (`NEEDS_CONFIRMATION`; the owner asked for an autonomous run with recommended answers)

- **P1 Access.** The overseas counselor (`role=counselor`, `division=overseas`) reads their own figures only; there is no counselor id in
  the request, so there is nothing to tamper with. The IT counselor (no Reports link, leads only), admins (they have `/management/counseling`
  and the CRM reports) and everyone else → 403; anonymous → 401.
- **P2 Period.** `from`/`to` inclusive IST dates, each defaulting to the current IST month's; end before start or longer than the
  management maximum → 422 (the `/management/counseling` rule, `bdm_performance.period`).
- **P3 Same definitions.** Leads assigned, calls, counseling sessions, follow-ups (repeat sessions), conversions and conversion % are
  computed by the very `management_counseling` builders for the counselor's id, with the same labels and definitions. Revenue is never
  computed or returned.
- **P4 Lead follow-up completion (period).** Follow-ups on the leads handed to the counselor (`lead_handover.counselor_scope`: owner and
  division) due in the period, cancelled ones excluded: due, completed (status done), completion % = completed ÷ due (none due → no %).
- **P5 Tasks.** Tasks completed in the period (ccrm-029, status done, completed in the period) and, now, overdue tasks (ccrm-029 T6's
  Overdue band: open, due before today IST).
- **P6 Overdue follow-ups (now).** Open follow-ups on the counselor's leads due before now — the tasks page's "Overdue follow-ups" count.
- **P7 Caseload (now).** Every application whose counselor is the counselor, any stage and any created date: applications, students
  (ccrm-034 R3, distinct people), offers (the funnel's Offer predicate), visas pending / approved / refused (ccrm-034 R7), enrolments
  (enrolment confirmed, ccrm-027 E4) and documents pending verification (current versions — kept from "My Caseload Report").
- **P8 Applications by stage and sub-status (now).** The same caseload grouped by stage then sub-status ("Not set" when none), in stage
  order, with applications and students per row and a total row. Closed stages are listed too (it is the whole caseload).
- **P9 Not audited.** Reads are not audited (ccrm-034 / DEC-SCOPE-051 R7). Only counts, percentages and stage names leave.

## API (§12FV)

`GET /api/v1/counselor/performance?from&to` → `{from, to, as_of, period: [Figure], now: [Figure], applications: {rows, total,
definitions}}`. `Figure = {key, label, definition, unit: "count" | "percent", value: int | float | null}`; a row =
`{stage, stage_label, sub_status, sub_status_label, applications, students}`.

## Frontend

`lib/counselorPerformance.ts` (types, URL builder; reuses `counselingQuery`, `formatCount`, `formatPct`),
`components/CounselorPerformance.tsx` (period form, "In the period" tiles, "Now" tiles, the stage/sub-status table with a scroll region,
empty and error states), page `app/overseas/counselor/reports/page.tsx` (server-rendered; GET form, so refresh, back and shared links keep
the period). A 422 shows its message with the form; any other failure shows a retry message with the form.

## Security (Phase 3)

Role and division checked before any query; scope is the caller's id only (no IDOR surface); no names, contact details, reasons or money;
SQL through SQLAlchemy with bound parameters; read-only GET (no CSRF surface).

## Tests

`apps/api/tests/test_ccrm_036_performance.py`: access matrix; period figures equal the `/management/counseling` row for the same counselor;
no revenue anywhere; follow-up completion; tasks; caseload counts; grouping and order; another counselor's records excluded; 422s.
`apps/web/tests/lib/counselorPerformance.test.ts`, `tests/components/CounselorPerformance.test.tsx`,
`tests/e2e/ccrm-036-counselor-performance.spec.ts`.

## Regression risks

`management_counseling` gains a one-counselor entry point that calls the same builders; `dashboard()` output is unchanged (mgmt-018 tests).
The portal `reports` payload stays as it is (API compatibility); the overseas counselor's Reports link now opens the new page.
