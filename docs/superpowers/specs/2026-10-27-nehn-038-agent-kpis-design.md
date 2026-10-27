# nehn-038 — Agent Performance Dashboard: KPI completion (design)

**Decision:** `DEC-SCOPE-306` · **Source:** backlog `nehn-038` (§20 L553-560, §26 L810-811) · **Status of KPI list:** client input CI-06
is still pending. The owner asked us to proceed with the recommended definitions. Every definition below is therefore marked
`NEEDS_CONFIRMATION` and can be changed without a migration.

## Intent
Source §20 asks for an agent performance dashboard with these KPIs: students referred, applications submitted, offers received,
conversions and visa outcomes. AGN-018 already serves `GET /workflows/overseas/agent/crm/dashboard` with most of them. Three are missing:

- applications submitted;
- conversion;
- the visa outcomes split into approved, refused and withdrawn.

The dashboard also has no date filter. This feature is **additive**.

## Goals
1. Add these response fields:
   - `applications_submitted`
   - `visa_refusals`, `visa_withdrawals` and `visa_decisions`
   - `conversions` and `conversion_rate`
   - `date_from` and `date_to`
   - per staff row: `conversions` and `conversion_rate`
2. Add an optional `date_from` / `date_to` filter on the same endpoint. It uses the same semantics as AGN-019: inclusive UTC days on
   the date the student's agency record was created, i.e. "students referred in the period".
3. Add dashboard tiles for the new KPIs and a From/To filter (a GET form, so refresh, Back and shared links keep the range).
4. Write the KPI definitions down (an appendix in the decision).

## Non-goals and anti-goals
- No admin cross-agent ranking. That is an open question in the backlog and stays out of scope.
- No schema change and no migration.
- AGN-018's unfiltered figures must not change. The `funnel_columns` contract shared with bdm-022 must not change either.
- A staff member must never see agency-wide figures.

## KPI definitions (`NEEDS_CONFIRMATION` — CI-06)

| KPI | Definition |
|---|---|
| Students referred | Unchanged: the active agency student records in scope. |
| Applications submitted | Applications in scope with `submitted_on` set. Withdrawn applications count, because the submission happened. School-bridged rows are excluded, as everywhere else. |
| Offers received | Unchanged (O5 / `offer_clause`). |
| Visa outcome of an application | The strongest decision across its visa cases: approved > refused > withdrawn. |
| `visa_approvals` | Unchanged. It already equals "any case approved". |
| `visa_refusals` | Applications whose strongest decision is refused. |
| `visa_withdrawals` | Applications whose strongest decision is withdrawn. |
| `visa_decisions` | Applications with any decision. Approvals + refusals + withdrawals = `visa_decisions` (AC3). |
| Conversions | Counted **per student**, which answers the backlog's edge case. A conversion is an active student (the same set as Students referred) with at least one enrolled application in scope. |
| `conversion_rate` | `round(100 × conversions ÷ students, 1)`, or `null` when there are no students. |

## Date filter (AC2)
The range selects a cohort: the agency student records created in the range, archived records included (AGN-019 P4). These figures
are restricted to that cohort's students, or to applications owned by a cohort student (`owner_join`):

- every Students, Pipeline, Visa and Conversion tile;
- both breakdowns;
- the staff table, including the unassigned count.

My call: three figures are **not** date-filtered. Each is labelled "Current — not filtered by date":

- Pending documents and Pending actions are work queues. Each links to a list page that shows everything open, and filtering only the
  count would make the tile disagree with that list.
- Commission is a ledger with its own dated report.

With a range set, an application that has no agency student record (made before AGN-008) cannot be dated, so it is excluded. With no
range, nothing changes.

Validation reuses `report_range`: 422 if `to` < `from` or `to` = 9999-12-31, and the guards run first. On the frontend, malformed URL
values are dropped, which is the `readRange` pattern.

## Authorization (AC4)
Nothing new. Scope still comes only from membership: `student_scope` / `application_scope`. Staff always get `scope: "own"`, and the
Master-only fields stay null for them. Another agency's rows are excluded by `org_member_ids`.

## Frontend
- `app/overseas/agent/dashboard/page.tsx` passes `searchParams` → `PortalPage` `query` → `AgentDashboardPanel`.
- The panel shows a small `<form method="get">` with From/To date inputs, Apply, and a "Clear" link when a range is set.
- `<Suspense key={range}>` shows the skeleton while a new range loads.
- A 422 renders an inline error and keeps the form.
- Tiles:
  - Pipeline gains "Applications submitted".
  - A new "Visa outcomes" group holds Approved / Refused / Withdrawn / Decided.
  - A new "Conversion" group holds Conversions and Conversion rate.
  - The staff table gains a "Conversion" column (count and rate).

## Alternatives considered
- **A separate `/crm/kpis` endpoint.** Rejected: it duplicates the scopes and the tile wiring.
- **Reusing `/crm/performance`.** Rejected: it is Master-only, and staff need their own figures (AC4).
- **Filtering by application `created_at` per tile.** Rejected: conversion would mix cohorts. The student cohort matches AGN-019.

## Risks
- AGN-018/019 tests and the bdm-022 shared `funnel_columns`. Mitigation: unfiltered output stays byte-identical except for the new
  keys, and the existing tests are re-run.
