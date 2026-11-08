# pob-028 — Placement Officer dashboard (design)

`DEC-SCOPE-436`. Source: `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-028 (§15, nine widgets; AC "each widget ties out to its
drill-down"; edge "a PO with no activity sees zeros, not errors"; performance "fixed query count"). Status of the source: `UNVERIFIED`;
the calls below are the builder's (`NEEDS_CONFIRMATION`).

## Dependency gate
pob-025 (replacement guarantee) is not built. The owner said to continue, so the replacement-deadline figure is left out until pob-025 lands.
pob-029 (outcome reports) is not built either, so the breakdowns by PO, recruiter, company, vendor, source and role (widget 9) are left to it.

## Options considered
1. **A sixth hrc-033 board (chosen).** `services/recruitment_dashboards.py` already declares each figure once, as a record kind and a predicate,
   and builds both the count and the drill-down from it. All figures of a board are one statement of scalar sub-selects, so the query count is
   fixed. The page, filters, export, scope and grants already exist.
2. Extend `recruiter_metrics` / `GET /recruiter/dashboard` (the 18 tiles). It has no drill-down or definitions, so the AC would need a second
   implementation of every figure.
3. A new page and endpoint. It would duplicate hrc-033.

## Design
- New record kinds: `company`, `follow_up` (joined to its company), `submission` (pob-021 `profile_share_items`), `placement` (pob-024).
- Scope: hrc-033's `_scope` gains a third list, the company scope (`recruiter_companies.caller_scope`; an officer: companies of their
  requirements; management: everything). Requirement-side kinds keep hrc-033's requirement and candidate scopes.
- `Section.commercial`: the invoicing section is dropped from the board and the export, and its drill is 403, outside the rec-031 revenue gate.
- Frontend: one more tab, "PO dashboard". The generic board component renders the sections.

## Sections (Appendix B definitions live in each figure's `definition`)
BD pipeline · Follow-ups · Requirements (status, vendor, ageing) · Sourcing funnel · Candidate actions · TPO partnerships · Interview tracker ·
Offers and joinings · Invoicing and collections (gated).

## Risks
- hrc-033's tests: `_scope` returns three lists; the existing boards ignore the company scope.
- Import cycles: the service must not import `recruiter_revenue`. A fresh-interpreter test guards this.
