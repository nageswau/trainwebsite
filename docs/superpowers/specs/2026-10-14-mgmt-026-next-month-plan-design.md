# mgmt-026 — Next month plan + target vs actual (design)

NO-ASSUMPTION MODE. 2026-10-14, `feature/mgmt-026`. Backlog item: `docs/delivery/MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-026.

## 1. Understanding

- **Source:** `EVID-017` (`DERIVED_BLUEPRINT`) §25 "Next month plan" ("a dedicated module"; the October 2026 plan per vertical:
  Abroad Education / IT Training / Schools / Recruitment with example items), §26 "Target vs actual" ("Every plan should automatically
  become a target"; the 8-row Department / Target / Actual / Achievement table), §33 "Next month plan / Long-term strategy".
- **Scope authority:** `DEC-SCOPE-186` M11 (`EXPLICIT_APPROVAL`). Plan items are typed per vertical, with an optional KPI from a fixed
  catalogue and a target. KPI-linked items get a live Actual, and free-text items are tracked done / not done. Module targets (BDM,
  telecaller, partnership) stay separate. M13 makes plans and targets operational tier (partner, super_admin), with no finance figures for
  the super admin.
- **Dependencies:** mgmt-003 (`management_metrics`), mgmt-009 (the revenue figure), mgmt-028 (tasks; `source='plan'` + `source_id`
  already in its CHECK). All three are merged on `main`.
- **Backlog acceptance criteria:**
  - AC1: the source's October 2026 plan is representable.
  - AC2: "Agents 30 → 27 = 90%" is computed from data.
  - AC3: a free-text item toggles done.
  - Negative: a KPI not in the catalogue gets a `422`.
  - Edge: editing targets after the month starts is audited ("who changed a target").
- **Open questions answered here:** Q-25 (the KPI catalogue and the plan lock) and Q-35 (long-term strategy). The answers below are
  **recommended defaults, `UNVERIFIED`**, taken on the owner's standing instruction to proceed with recommended answers (registered as
  `DEC-SCOPE-211`).

## 2. Approaches considered

1. **Recommended: item-level resources.** A plan has items; each item is created, changed and removed on its own, and actuals are
   computed on read.
   - Every target change is one audited write.
   - Item ids stay stable, so the tasks created from them keep their `source_id`.
2. **Whole-plan replace (PUT the item list).** Simpler for the client.
   - Item ids churn, so task links break.
   - "Who changed a target" is lost in a bulk diff.
   - Rejected.
3. **Stored snapshots of the actual (computed nightly).** No live figure. A job and a cache are needed. M11 says "live Actual".
   Rejected.

## 3. Decisions (PN1–PN16)

| # | Point | Answer |
|---|---|---|
| PN1 | Horizon (Q-35) | Monthly plans only. "Long-term strategy" is **not** built here and stays a "coming soon" Command Center entry, `NEEDS_CONFIRMATION` |
| PN2 | Plan | One plan per IST calendar month (`month` = its 1st day, unique). Status `draft` (default) / `active` / `closed`. A plan can be created for the current IST month up to 12 months ahead; an earlier or later month gets a field `422`, and a second plan for a month gets `409` |
| PN3 | Status | Any change between the three statuses is allowed and audited (closing and reopening alike). A **closed** plan is read-only for its items and tasks: `409` "This plan is closed. Reopen it to change it." |
| PN4 | Item | `vertical` ∈ abroad / it / school / recruitment / other (the source's four, in source order, plus Other). `text` 2–200. `kpi` is optional, from the catalogue. `target` is required with a `kpi` and refused without one. A count target is a whole number 1–1 000 000; a revenue target is rupees > 0, at most 2 decimals, at most 1 000 000 000 000. `done` applies to free-text items only (`422` on a KPI item); turning an item into a KPI item clears `done` |
| PN5 | KPI catalogue (Q-25) | Eleven KPIs, each counted over the plan's IST month. See §4 |
| PN6 | Actual | Computed live on every read, never stored. Achievement = actual ÷ target × 100, rounded half-up to a whole per cent (the source shows 90%, 83%). Month state: `upcoming` / `running` (to date) / `ended`. An upcoming month's actual is 0 |
| PN7 | Revenue KPI | Partner only (M13: the super admin sees no finance figures). For a non-partner, revenue items are left out of the plan, the progress table and the counts. Setting `kpi=revenue` gets `403` "Only partners can set a revenue target". Another tier's request for a revenue item id gets `404` |
| PN8 | Access | Operational tier (partner, super_admin) through `management_discussions.require_operational`. The accountant gets `403` "Operational management access required", other roles get `403` "Management access required", and a signed-out caller gets `401` |
| PN9 | Edits after the month starts (Q-25) | Allowed while the plan is not closed. Every write adds a `mgmt.plan` audit row (operational, so field names only, MA3), so Management activity shows who changed `target`. Verbs: `create`, `update`, and `delete` (new, for removing an item) |
| PN10 | Tasks from items | `POST …/items/{id}/tasks {owner_user_id, priority?, deadline}` creates a mgmt-028 task: `source=plan`, `source_id` = item id, title = the item text. It uses mgmt-028's checks, notification and `mgmt.task` audit. Each item shows `task_count` |
| PN11 | Concurrency | Every plan or item write locks the plan row (`FOR UPDATE`). A concurrent create of the same month hits the unique index and gets `409` |
| PN12 | Order | Items in vertical order (PN4), then `position` (append order, max + 1 under the plan lock) |
| PN13 | Remove an item | `DELETE` gets `204` and is audited. Tasks created from the item stay, with their title |
| PN14 | UI | `/management/plans` lists the plans and has a "Plan a month" form. `/management/plans/[month]` shows Target vs actual (§26) first, then the plan by vertical (§25): add / edit / remove, done toggles, "Create task", status. The Command Center "Next month plan & targets" entry goes live |
| PN15 | Logs | Ids and field names only, never item text |
| PN16 | Numbering | Migration `0159_management_plans`; `DEC-SCOPE-211`; API §12DY; RBAC §2.136 |

## 4. KPI catalogue (PN5, all counts in the plan's IST month `[start, next start)`)

| key | Label (§26 row) | Definition | Reuses |
|---|---|---|---|
| `agents` | New agents (Agents) | Agency organisations created in the month that are active now | `AgentOrg` (S7's "active") |
| `applications` | Applications | Overseas applications created in the month | mgmt-024 `applications()` "created" with the month as date filter |
| `enrollments` | Enrollments | Applications moved to Enrolled in the month (distinct applications) | `ApplicationStatusHistory` |
| `universities` | University partners (Universities) | Universities moved into a partner-group stage in the month (distinct) | `UniversityStageHistory`, S9's `UNIVERSITY_PARTNER_STAGES` |
| `it_students` | New IT students (IT Students) | Distinct students with an IT enrolment created in the month that was taken up (not pending consent / rejected) | `Enrollment`, mgmt-017 `NOT_TAKEN` |
| `batches` | New batches | Batches starting in the month (not cancelled) | `Batch.start_date` |
| `school_mous` | School MoUs (Schools) | School-organisation MoUs moved to Signed in the month (distinct MoUs) | bdm M-09 rule (`BdmMouEvent`) |
| `school_students` | School students onboarded | School students added in the month | `SchoolStudent.created_at` |
| `companies` | New companies | Companies that first moved past Interested in the month | rec-034 B4 `first_past_interested()` (mgmt-025) |
| `placements` | Placements | Offers joined with an actual joining date in the month | rec-033 "joined" |
| `revenue` | Revenue (₹) — partner only | The month's counted ledger income, equal to mgmt-009's P&L total revenue for the month | `management_pnl.dashboard(…, "month")` |

The count KPIs a plan uses are one SELECT of scalar subqueries. Revenue is the P&L read. Both are bounded by the catalogue.

## 5. Data model (migration `0159_management_plans`)

- `management_plans`:
  - `id`;
  - `month` (Date, unique, CHECK day = 1);
  - `status` (CHECK draft/active/closed, default draft);
  - `created_by_user_id`, `updated_by_user_id` (FK users RESTRICT);
  - timestamps.
- `management_plan_items`:
  - `id`;
  - `plan_id` (FK plans, CASCADE);
  - `vertical` (CHECK);
  - `text` String(200);
  - `kpi` String(20), nullable;
  - `target` Numeric(16,2), nullable;
  - `done` bool, default false;
  - `position` int;
  - `created_by_user_id`, `updated_by_user_id`;
  - timestamps.
  - CHECKs: `(kpi IS NULL) = (target IS NULL)`, `target IS NULL OR target > 0`, `kpi IS NULL OR NOT done`.
  - Index: `(plan_id, vertical, position)`.
  - The `kpi` value is validated by the schema (`Literal`), not by a CHECK, so the catalogue can grow without a migration.
- `downgrade()` refuses while any plan exists (the 0153 idiom).

## 6. API (`/api/v1`)

| Method/Path | Notes |
|---|---|
| `GET /management/plans` | `{items[{id, month, status, label, item_count, done_count, kpi_count}]}`, newest month first |
| `GET /management/plans/options` | `{kpis[{key, label, unit (count/inr), definition}], verticals[{key,label}], users[...], current_month, max_month}`; revenue listed for partners only |
| `POST /management/plans` | `{month: "YYYY-MM", status?}` gets `201` plan. Month out of window gets a field `422`; a duplicate gets `409` |
| `GET /management/plans/{month}` | Plan + items (`id, vertical, text, kpi, target, done, task_count, updated_at`), `month` malformed gets `422`, unknown gets `404` |
| `PATCH /management/plans/{month}` | `{status}` gets `200` plan |
| `POST /management/plans/{month}/items` | `{vertical, text, kpi?, target?}` gets `201` item; `409` closed |
| `PATCH /management/plans/{month}/items/{id}` | Partial `{vertical?, text?, kpi?, target?, done?}`; no change means nothing recorded |
| `DELETE /management/plans/{month}/items/{id}` | `204` |
| `POST /management/plans/{month}/items/{id}/tasks` | `{owner_user_id, priority?, deadline}` gets `201` mgmt-028 task |
| `GET /management/plans/{month}/progress` | `{month, label, state, start, end, rows[{item_id, vertical, text, kpi, kpi_label, unit, target, actual, achievement}], free_text{total, done}}` |

## 7. Frontend

- `lib/managementPlans.ts` holds the types, URLs, vertical labels, and the money and percentage display.
- Pages:
  - `app/management/plans/page.tsx` (list and the create form);
  - `app/management/plans/[month]/page.tsx` (progress table, plan editor, status).
- Components:
  - `ManagementPlans` (list);
  - `ManagementPlanForm` (month picker);
  - `ManagementPlanProgress` (the §26 table);
  - `ManagementPlanEditor` (the client component: items by vertical, add/edit/remove, done, status, create task with the
    mgmt-028 fields).
- Reused: `DiscussionsShell` (`section="Next month plan"`), `sendJson`, `fieldErrors`, `useHydrated`, and the existing `.table` / `.status`
  / `.form` classes.
- Loading, empty and error states:
  - The server pages show an access card on `401`/`403` and an "unavailable" message otherwise.
  - Empty states read "No plans yet" and "No items in this vertical".
  - Every button has a busy state, and a ref guards against a double submit.
  - Narrow screens keep the table inside a horizontal-scroll wrapper.

## 8. Testing

- **Backend** (`tests/test_mgmt_026_plans.py`, `tests/test_mgmt_026_migration.py`):
  - AC1: the October plan's 16 items are stored;
  - AC2: 30 agent target, 27 agencies created in the month, gives 90%;
  - AC3: done toggles;
  - the catalogue `422`, the access matrix and revenue visibility;
  - the closed `409`, the duplicate `409` and the month window;
  - audit rows and the task link;
  - each KPI counts only inside the month.
- **Web:** vitest for `managementPlans.ts` and for the progress and editor components. Playwright `tests/e2e/mgmt-026-plans.spec.ts`.
