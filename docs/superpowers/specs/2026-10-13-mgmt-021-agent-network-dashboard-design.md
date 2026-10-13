# mgmt-021 — Agent network dashboard (design)

**Feature:** `mgmt-021` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-021). **Source:** `EVID-017` §17 "AGENT DASHBOARD" (lines 649–681,
`DERIVED_BLUEPRINT`): 12 figures, the chain "Agent → Staff → Student → Application → Enrollment → Revenue", "so the partners can identify
which agents are genuinely producing business". **Scope authority:** `DEC-SCOPE-186` M1/M13 (`EXPLICIT_APPROVAL`). **Dependency:** mgmt-003
(merged, PR #244).

Every AN answer below is a **recommended default, `UNVERIFIED`**. The owner told us to proceed with recommended answers. AN5–AN9 answer
**Q-22**.

## Understanding

- **Outcome:** a partner can see the agent network's figures for a period and a ranking of agencies along the chain.
- **Reader:** partners (all figures), and the super admin (counts only, M13).
- **Success:** each agency row's chain counts sum to the totals. The super admin never receives commission or revenue (backlog AC).
- **Constraints:** read-only, no migration, AGN-022 untouched. The agency CRM routes still refuse `super_admin`. This aggregate lives
  under `/management` (AGT-002 isolation is not weakened).

## Decisions (AN1–AN14)

| # | Point | Answer |
|---|---|---|
| AN1 | Agent | An agency organisation (`agent_orgs`), as on AGN-022. **Total agents** = status `active` or `suspended` (approved agencies). Pending and rejected applications are not agents |
| AN2 | Active / inactive | **Active** = status `active`; **Inactive** = status `suspended` (the AGN-001 approval gate). Total = active + inactive |
| AN3 | New agents | Total agents whose organisation was created in the period |
| AN4 | Agent staff | Active staff members right now (AGN-022 `staff_count`: role `staff`, member status `active`), summed over total agents |
| AN5 | Students | Agency student records (`agent_students`) any member added in the period, any status |
| AN6 | Applications / Offers / Visa / Enrollments | The cohort of the agency's applications **created in the period**, counted with mgmt-024's `FUNNEL_COUNTS` (`created`, `offer`, `visa`, `enrollment`). An agency row therefore equals the Applications funnel filtered by that agency over the same dates. School-bridged rows never have an `agent_id` |
| AN7 | Commission (Q-22) | Paid agent commission: the ledger's counted `agent_commission` lines (rupees, mgmt-005), dated in the period. A **cost** to EduSphere |
| AN8 | Revenue (Q-22) | What EduSphere earned from the agency's students: the ledger's counted Abroad `payment` lines dated in the period, attributed to the agency exactly as mgmt-006 MR5 does. This equals mgmt-006's Agency-wise row. University commission is received per university, not per application, so it **cannot be attributed to an agency** and is not included (said on the page) |
| AN9 | Money tier | Commission and revenue go to the finance tier within the operational route, which is the partner only (`can_view_finance`). The super admin gets `null`, and the ledger is never queried for them (M13) |
| AN10 | Ranking | Rows ordered by enrollments, applications and students (descending), then name. Every role gets the same order, so the order cannot reveal money to the super admin |
| AN11 | Suspended agency (edge) | Kept in the table, marked "Suspended", and its period activity still counted |
| AN12 | Totals | Each total is the sum of the agency rows (AC). Agent users with no organisation (legacy rows) are outside the network and are not counted |
| AN13 | Period | `from` / `to` are inclusive IST dates, defaulting to this IST month. A start after the end, or a period over 366 days, is a 422 (`bdm_performance.period`, as mgmt-018) |
| AN14 | Access / nav | Operational tier (partner, super_admin). The accountant gets 403 "Operational access required", other roles 403, and a signed-out caller 401. Command Center Partnerships → "Agents" goes live. The super admin sidebar gets "Management agent figures". No audit row (a read of counts and agency names only) |

## Approaches considered

1. **Recommended: a new `services/management_agents.py`.** It runs grouped queries over agency members and reuses mgmt-024's funnel
   predicates and the ledger. It has one statement per figure family, grouped by org.
2. Call AGN-022 `org_counts` and add to it. Rejected: its counts are "right now" snapshots (active students, non-withdrawn applications),
   so they cannot be scoped to a period. Changing it would put AGN-022 at risk.
3. Call mgmt-024 `applications()` once per agency. Rejected: it runs N queries.

## API

`GET /management/agents?from=&to=` returns `200`:

```
{from, to, as_of, money_visible,
 figures: [{key, label, definition}],                         # §17 order, 12 figures
 totals: {agents, new_agents, active_agents, inactive_agents, staff, students, applications, offers, visa, enrollments,
          commission, revenue},                               # money: decimal string or null
 chain: [{key, label, value}],                                # Agents → Staff → Students → Applications → Enrollments → Revenue (revenue step only when money_visible)
 agencies: [{id, name, prefix, status, new, staff, students, applications, offers, visa, enrollments, commission, revenue}]}
```

## UI

The page `/management/agents` follows the mgmt-018 page and component shape:
- a period form;
- 12 tiles, where money shows "Partners only" for the super admin;
- a chain card;
- the "Agency-wise performance" table in rank order, with an "All agencies" total row in `tfoot`, a "Suspended" marker, and an empty
  state ("No approved agencies yet.").

The table scrolls inside `.table-scroll` on a phone.

## Testing

- **Backend (`test_mgmt_021_agents.py`):** checks that only a test's own agencies are counted, over a fixed past period. It covers access
  per role, each definition (in-period vs out-of-period rows), the suspended/pending/rejected cases, ranking, totals = sum of rows,
  super_admin money null, the agency row matching the mgmt-024 funnel filtered by agency, and 422s.
- **Web:** `managementAgents.test.ts` (query and URL) and `ManagementAgents.test.tsx` (tiles, money hidden, empty state, suspended marker,
  error).
- **E2E:** `mgmt-021-agents.spec.ts` (partner with money, super admin without, accountant refused).
