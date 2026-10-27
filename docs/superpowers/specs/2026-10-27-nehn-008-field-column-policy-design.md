# nehn-008 — Role-based field (column) policy for views and downloads (design)

- **Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-008` (§15 L324-350; §5 L104-121; action 3;
  `MEETING_TRANSCRIPT_REQUEST`, `UNVERIFIED` backlog).
- **Dependencies:** nehn-005 engine (`DEC-SCOPE-281`, #347), nehn-004 xlsx writer (`DEC-SCOPE-282`, #349), nehn-007 per-user
  overrides (`DEC-SCOPE-299`, #366). All merged.
- **Decision:** `DEC-SCOPE-300`. **RBAC:** §2.211. **API:** §12GX. **Migration:** `0207_field_financial_grant`.

## Intent

"A user may not download what they cannot see." A report declares which of its columns belong to a sensitive field class; a catalogue
permission per class (`field.<class>.view`) decides whether the caller gets those columns. One function applies the policy to the
report payload that both the JSON view and the CSV/xlsx download are rendered from, so the screen and the file can never differ.

## Current state (Phase 1 evidence)

- Every report router renders the download from the same `{columns, items, totals}` payload as the JSON (`agent_reports.export_response`).
- Columns are fixed per report kind. No field-level policy exists.
- The **only** existing report or export that carries a financial column is the partnership **Performance** report
  (`commission_expected`, `commission_received`), hard-gated today to the upc-001 U2 roles (`partnership_access.COMMISSION_ROLES` =
  super_admin, partnership_manager, partnership_head), which are also exactly the report's readers (`READERS`).
- Telecaller, agency, recruiter-performance and lead exports hold no fee, discount, payment, commission or salary columns.
- Recruiter (placement_team / placement_manager) and HR (hr_team) have **no** student report today; nehn-016 and nehn-017 build them.

## Goals

- `services/field_policy.py`: `strip(db, user, payload, classes)` removes every column whose class the user may not view, from
  `columns`, from each item and from `totals`.
- Catalogue resource `field.financial` with action `view`; it appears in the nehn-006 matrix and the nehn-007 per-user tab
  automatically, and resolves through `permissions.user_has_grant` (role grant ± active override; super_admin always).
- The partnership reports declare `commission_expected` / `commission_received` as `financial`, and `build()` applies the policy, so the
  JSON, CSV and xlsx follow it together.
- Seed = today's behaviour: partnership_manager and partnership_head hold `field.financial.view` (super_admin implicitly).

## Non-goals

- The recruiter/HR student reports (nehn-016/017) and the report registry (nehn-009). They must declare their columns through this
  policy; this item ships the policy they plug into.
- Classes other than `financial` in the catalogue: an unwired catalogue key would be a toggle that does nothing (nehn-005 P1). The other
  backlog classes (`identity`, `contact`, `academic`, `attendance`, `placement`, `admin`, `document`) join when a report first tags one.
- Commission figures on the partnership pages and dashboards (`can_see_commission`, U2): unchanged. They are not downloads.
- Frontend changes: the report tables already render the columns the API returns.

## Anti-goals

- Any change in what a current role sees on day one (pinned by tests).
- A download whose columns differ from its screen.
- Widening: the column still needs the existing U2 rule **and** the field grant.

## Builder's defaults (owner pre-authorised recommended answers; each `NEEDS_CONFIRMATION`)

| # | Question | Default in place |
|---|---|---|
| F1 | Pilot report | Partnership reports (the only report with a financial column today). |
| F2 | Untagged column | Unrestricted: the report's own gate and row scope already apply. Only tagged columns are filtered. |
| F3 | Seed | `field.financial.view` → partnership_manager, partnership_head. it_admin/overseas_admin are **not** seeded: they do not read partnership commission today (DEC-SCOPE-118 U2). |
| F4 | AC1/AC2 (recruiter, HR) | Satisfied by the seed (no recruiter or HR role holds `field.financial.view`) and proven on the engine; the reports themselves arrive with nehn-016/017. |
| F5 | Denied columns | Removed, not blanked or masked: the header is absent from screen and file. |
| F6 | Audit | The export audit row is unchanged; grant changes are audited by nehn-005/007. |

## Design

- `rbac.CATALOGUE["field.financial"] = {"label": "Financial columns", "actions": ("view",)}`; `DEFAULT_GRANTS` adds the key for the two
  roles.
- `field_policy.strip(db, user, payload, classes: Mapping[str, str]) -> dict`: for each distinct class present in the payload's columns,
  one `user_has_grant(db, user, f"field.{class}", "view")`; returns the payload with the denied keys dropped (new dicts, no mutation).
- `partnership_reports.FIELD_CLASSES = {"commission_expected": "financial", "commission_received": "financial"}`; `build()` returns
  `await field_policy.strip(db, user, payload, FIELD_CLASSES)`.
- Migration `0207`: insert the two grants `ON CONFLICT DO NOTHING`; downgrade deletes `resource = 'field.financial'` rows (role grants and
  overrides). No existing row changes.

## API (§12GX)

`GET /partnership/reports/performance` and its `.csv` / `.xlsx`: the two commission columns are present only when the caller holds
`field.financial.view` (and is a U2 role, as before). Response shape otherwise unchanged. `GET /admin/permissions/catalogue` lists
`field.financial`.

## Acceptance criteria (made testable)

1. Recruiter and HR roles (placement_team, placement_manager, hr_team) do not hold `field.financial.view`; admin (super_admin) does.
2. With the seed, each partnership reader's performance report (JSON, CSV, xlsx) keeps its commission columns (regression pin).
3. For every reader role × report kind × (granted, revoked), the JSON column keys equal the CSV header keys and the xlsx header.
4. Revoking `field.financial.view` from partnership_head removes the commission columns from JSON and both downloads on the next
   request; restoring it adds them back. A nehn-007 deny override does the same for one user.
5. A payload with a denied financial column has the key in neither items nor totals.
