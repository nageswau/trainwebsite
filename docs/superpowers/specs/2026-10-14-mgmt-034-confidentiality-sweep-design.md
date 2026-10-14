# mgmt-034 — Confidentiality + permission sweep (design)

Date: 2026-10-14 · Backlog: `docs/delivery/MANAGEMENT_COMMAND_CENTER_BACKLOG.md` mgmt-034 · Source: `EVID-017` §2/§24 ("permission-controlled"),
backlog M2, M3, M13, M14 (`DEC-SCOPE-186`, `EXPLICIT_APPROVAL`) · Precedents: tel-026 (`DEC-SCOPE-115`), upc-033 (`DEC-SCOPE-174`),
rec-038 (`DEC-SCOPE-185`).
Dependencies: mgmt-001 … mgmt-033, all merged to `main` (one `feature/mgmt-0NN` merge each, checked at `cfaf81ab`).
Numbering: `DEC-SCOPE-221`, RBAC §2.146, API §12EI. No migration.

## 1. What the item asks for

1. RBAC_MATRIX rows for every `/management/*` route.
2. A route-inventory test.
3. A tier sweep: every endpoint called as partner, accountant, super_admin, division admins, module managers and staff, asserting
   partner-only → partner; finance → partner + accountant; operational → partner + super_admin; the university commission rule (U2 as
   amended by M3); assignees see only their own tasks/decisions.
4. upc-016/033 expectations updated for the partner role (M3).

Acceptance criteria: (AC1) every route is in the inventory; (AC2) the sweep fails on any extra field or extra role.
Frontend: none. Backend: tests only, unless the sweep finds a gap (CS4).

## 2. Decisions (recommended answers under the owner's standing build-session instruction; `UNVERIFIED`, `NEEDS_CONFIRMATION` at sign-off)

| # | Point | Decision |
|---|---|---|
| CS1 | University commission and the accountant | M3 (explicit) makes commission visible to `super_admin`, the partnership roles and **partner**; the accountant is not named. mgmt-006 (MR7), mgmt-009 (PL7) and mgmt-033 (DD5) already leave it out for the accountant; §2.123 handed the remaining places to this item. Every management read the accountant can open leaves university commission out: the ledger list (rows and totals), the accounts dashboard (income, receivables), the salary employee-cost ratio, and any other read the sweep finds. The partner sees it everywhere. Applied with the existing `can_view_university_commission` helper and the `c.source != "university_commission"` clause (PL7/DD5 pattern). |
| CS2 | Salaries: M2 "partner-only" vs M5/M13 | M5 and M13 are the specific rules (the accountant enters and reads department salary totals); mgmt-011 built that. Kept as built; the backlog line "partner-only (… salaries …)" is read as "never `super_admin`". Recorded as `NEEDS_CONFIRMATION`. |
| CS3 | Inventory | Every operation under `/management` and `/me/management-` read from `app.openapi()` (97 at `cfaf81ab`). Fails on a route without a row **or** a row without a route. |
| CS4 | Roles called | `anon`; `partner`; `partner2` (another partner, for "not the creator" rules); `accountant`; `super`; `it_admin`; `ovs_admin`; `bdm_manager`; `tel_manager`; `p_head` (partnership head); `counselor`; `trainer`; `owner` (a telecaller named owner / responsible / participant of the world's task, decision and meeting); `student`; `agent`. Unlisted signed-in roles must get `403`, anonymous `401`. |
| CS5 | Cell expectations | The owning item's as-built rule (RBAC §2.112–§2.145), checked against the code. A wrong expectation is checked against code **and** docs; never adjusted to make a cell pass. |
| CS6 | Worlds | upc-033 PX5: refused cells and `GET` cells share one world per row; every non-`GET` 2xx cell gets a fresh world. Users inserted directly with a minted session cookie; management records made through their real routes as the partner/accountant. |
| CS7 | "Extra field" — the delta sweep | Every inventoried `GET` (plus filter variants that select the planted rows) is read as each management role, then the world plants (a) partner-only data: an investment, a capital entry, a university commission receipt; (b) finance data: an approved manual income entry, a department salary month, the month's balances — directly in the DB, today, with no audit row. Each read is repeated: a role that may not see a plant must get a **byte-identical** body (after removing nothing but documented clocks). A positive control proves the plants are reachable: the partner's bodies change. This catches a leak inside a total, which a key or sentinel scan cannot. |
| CS8 | Assignee slices (M14) | The owner's `/me/management-tasks`, `/me/management-decisions`, `/me/management-meetings` items carry exactly their documented keys (an extra key fails), another staff member's list does not contain them, and another user's id is `404`. |
| CS9 | upc-033 for the partner (M3) | `partner` and `accountant` are added to upc-033's non-commission roles: every partnership route `403` (MG2: `COMMISSION_ROLES` unchanged), and no commission in any body they receive. Partners read commission only through the management pages (CS1). |
| CS10 | A gap found by the sweep | Fixed inside mgmt-034 when it breaks a documented rule and the fix is local (tel-026 PM4 / upc-033 PX7). Each is listed in RBAC §2.146 and API §12EI. |

## 3. Components

- `apps/api/tests/mgmt034_helpers.py` — roles, `world()`, `plant_partner_only()`, `plant_finance()`.
- `apps/api/tests/test_mgmt_034_matrix.py` — `MATRIX`, inventory test, `test_matrix_row`.
- `apps/api/tests/test_mgmt_034_confidentiality.py` — the delta sweep (CS7), assignee slices (CS8).
- `apps/api/tests/upc033_helpers.py`, `test_upc_033_*` — the two management roles (CS9).
- Service fix (CS1): the accountant-reachable `ledger.lines()` consumers.
- Docs: RBAC §2.146, `DEC-SCOPE-221`, API §12EI, backlog status, QA evidence.

## 4. Error handling and risk

No new route or schema. The CS1 clause runs inside the existing query, so the accountant's figures are computed without commission rather
than masked afterwards (no value ever leaves the database). Regression risk: `services/ledger.py` and `services/accounts.py` feed many
dashboards; the partner's figures must not change (existing mgmt-005/013/011 tests + the positive control).
