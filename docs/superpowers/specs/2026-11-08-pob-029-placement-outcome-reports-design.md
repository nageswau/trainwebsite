# pob-029 — Placement outcome reports (design)

`DEC-SCOPE-438`, API §12ME, RBAC §2.328. No migration. Backlog: `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` §pob-029.

## Goal
§13.2's five report groups for the Team Lead and management: placements by company, vendor, role, source, recruiter and PO; the
requirement → submission → interview → offer conversions; offer acceptance, joining rate and time to fill; revenue generated, invoiced,
collected and outstanding; replacements, early dropouts and satisfaction; filters and export.

## Design (builder's calls R1-R12, `NEEDS_CONFIRMATION`)
- **R1 Readers:** `placement_manager` (Team Lead: their team + Unassigned, rec-007 `caller_scope`) and `super_admin` (everything). Others 403.
- **R2 Period:** rec-033's range rules (IST days; 1st of the month → today; never in the future; ≤ 366 days).
- **R3 Cohort:** the placements whose offer was accepted (pob-024 record created) in the period. The totals, every group row and the
  drill-down come from the same rows (one statement), so each figure ties out to the placements behind it (AC).
- **R4 Groups:** company, vendor ("Direct" when none), role, source (application's submitted source, else the candidate's; "No source"),
  recruiter, PO owner ("Unassigned").
- **R5 Filters:** company, vendor, recruiter, PO, source (ids). Company and vendor also narrow the conversions; the others belong to a placement.
- **R6 Conversions:** the period's own events in the same scope: requirements opened, candidates first submitted (pob-021 share items),
  candidates interviewed (not cancelled), offers made (`offered_on`), accepted and declined; each step as a % of the one before.
- **R7 Rates:** offer acceptance = accepted ÷ (accepted + declined); joining rate = joined ÷ (joined + did not join);
  time to fill = mean days from the requirement's creation (IST date) to the actual joining date, a negative (legacy) span counting 0 (QA-03).
- **R8 Revenue:** only behind the rec-031 / pob-001 revenue gate (`placements.commercial`). Generated = expected fee of the joined
  placements; invoiced = their issued, uncancelled rec-031 invoices; collected = payments on them; outstanding = invoiced − collected.
  Without the gate the money figures are null and their columns are left out.
- **R9 Dropouts:** dropouts; early dropouts = inside the guarantee (pob-025 G5); replacements owed / filled.
- **R10 Satisfaction:** mean pob-026 rating per respondent, with the response count.
- **R11 Export:** `.csv` / `.xlsx` of the group table, Total last, through `agent_reports.export_response` (formula-safe cells);
  one audit row `placement_outcomes.export` (period, grouping, filter ids, row count, format) committed before the file is returned.
- **R12 Drill-down:** the newest 100 cohort rows on the page (the totals count all), each linking to its placement; a group row links to
  the same report filtered to that group (company, vendor, recruiter, PO, source).

## +/−/E
A period with placements but no invoices: invoiced, collected and outstanding are ₹0.00. A period with nothing: zeros, "—" rates and an
empty-state sentence.

## UI
`/recruiter/manager/placement-outcomes` (Team Lead and super admin sidebars): a GET form (from, to, group by), the outcome tiles, the
conversion tiles, the group table with its Total and export buttons, and the placements behind the figures. Reuses `.tel-tiles` /
`.money-tiles`, `SpreadsheetButtons` and the rec-033 page pattern.

## Not built
Per-PO performance beyond the grouping, scheduled report delivery, charts.
