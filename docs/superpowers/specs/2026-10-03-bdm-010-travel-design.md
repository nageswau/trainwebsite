# bdm-010 — BDM Travel Requests, Approval, Modes, Costs, Expenses — Design

**Status:** design approved in-session on 2026-10-03, in five sections: (1) data model, (2) lifecycle, authorization and
concurrency, (3) API, (4) frontend, (5) acceptance criteria, tests and regression. No code has been written.

**Branch:** `worktree-bdm-010`, fast-forwarded to `origin/main` @ `e1c2084` (after AGN-017 #49).

**Backlog:** `docs/delivery/BDM_CRM_BACKLOG.md` §4 bdm-010 (line 548). Depends only on bdm-001 (merged, PR #45).

**Source:** `functionalities/edusphere_markdown/BDM Functionalities.md` (`EVID-016`, `DERIVED_BLUEPRINT`) §3 (95–147),
§4 Common "Travel" (1270–1286), Agent §D (655–683).

**Decision record:** **`DEC-SCOPE-060`**, written in this change (next free on `main` @ `e1c2084`; `059` is AGN-017).
If bdm-002 (in flight, also claiming `0064`/`058`) merges first, this becomes `DEC-SCOPE-061` / `0067_bdm_trips`.
Recheck `origin/main` before building and before the PR.

**Gate:** `APPROVAL_GATES.md` GATE-09.

**Scope note:** the label "bdm-010" was once pasted with the calendar requirement (bdm-013). The owner confirmed on
2026-10-03 that bdm-010 is travel. The calendar is bdm-013 and is out of scope here.

---

## 1. Scope

In scope:
- A BDM creates, edits, submits, withdraws, resubmits, starts, completes and cancels their own trips (§3 fields, 6 modes).
- The BDM's reporting manager approves or rejects a submitted trip (with a reason). A `super_admin` may decide only when
  that manager is inactive.
- Itemized expense lines once the trip is approved; actual cost = sum of lines.
- Remarks stay editable in every state; every change is audited.
- In-app notifications on submit (to the approver) and on decision (to the BDM).
- Pages: BDM travel list / new / detail; manager approvals queue and trip view; admin fallback queue.

Out of scope (later items):
- Trip ↔ appointment linking, itinerary, travel report, productivity metrics — **bdm-011**.
- Travel reminder — **bdm-012**. Calendar — **bdm-013**. My Day tiles — **bdm-014**. Alerts — **bdm-023**.
- Receipts (Q-06 mentions an optional receipt; the owner dropped it on 2026-10-03 — no file storage in bdm-010).
- Reimbursement payout (Q-06: none in EduSphere).
- Multi-city trips (owner: one From/To per trip; a tour is several trips).

The §3 fields "Organization/College/Agent" and "Appointment Date/Time" are **not stored on the trip** (backlog). They come
from appointments linked in bdm-011, so bdm-010 alone shows neither.

## 2. Approaches considered

- **A. Flat feature module (chosen).** New `app/api/bdm_travel.py` + `app/services/bdm_travel.py`; schemas appended to
  `schemas.py`; one migration. Reuses bdm-001's `bdm_context`, `require_manager`, `team_filter`, the
  `{items,total,limit,offset}` page shape, `_notify_user` and `AuditLog`. The backlog names `app/api/bdm/travel.py`, but a
  `bdm/` package would shadow the existing `app/api/bdm.py` module, so the flat name is a deliberate deviation.
- **B. Shared approval engine** for travel, commissions and results — rejected: redesigns working, unrelated modules for one
  new consumer.
- **C. Extend `app/api/bdm.py`** — rejected: that router is read-only by design, and bdm-002 is editing it in parallel.

Inside A, status is **two columns** (A1, chosen) rather than one combined status (A2): the source lists Approval Status and
Travel Status as separate fields, and "cancelled after approval, with expenses" must keep both facts.

## 3. Decisions

Owner answers (2026-10-03):

| ID | Decision |
|---|---|
| T1 | One From/To per trip; no multi-city legs. |
| T2 | Nothing about the approver is stored. The approver is resolved at decision time from `bdm_profiles.reporting_manager_user_id`. `admin.update_user` is not touched. |
| T3 | Any `super_admin` may decide a trip only when the BDM's reporting manager is inactive. |
| T4 | Submit notice is in-app only (no email). |
| T5 | Expenses are allowed once approved (planned, in progress, completed, or cancelled after approval). Draft, submitted and rejected trips take none. |
| T6 | Trip codes are sequential `TRV-000123` (a Postgres sequence; gaps are possible on a rolled-back create). |
| T7 | Expense line = category (`travel`/`stay`/`food`/`local`/`other`) + INR amount + date + optional note. No receipt upload. |
| T8 | Fallback UI: a new `/admin/bdm-travel-approvals` page with a `SUPER_ADMIN_NAV` link, listing only trips whose manager is inactive. |
| T9 | A BDM may withdraw a submitted trip back to draft; a rejected trip can be edited and resubmitted (reason kept in the audit). |
| T10 | Approach A, two status columns (A1). |
| T11 | Submit when the manager is already inactive → the in-app notice goes to every active `super_admin`. |
| T12 | On approve/reject the BDM also gets an in-app notice (an addition to the backlog). |
| T13 | Expense amount must be > 0 (zero is refused as well as negative). |

Backlog decisions applied: D4 (manager = reporting manager, team scope), D15 (actual cost = sum of lines),
Q-05 (every trip needs approval before it starts; reject needs a reason; edit and resubmit), Q-06 (itemized lines, INR).

## 4. Data model — migration `0066_bdm_trips`

Additive only: two tables and one sequence. No existing row is read or written. Creation is guarded (0061's idiom, because
`0001` builds a fresh database from the current models). `downgrade()` refuses while trips exist.

### 4.1 `bdm_trips`

| Column | Type | Rule |
|---|---|---|
| `id` | UUID PK | `default=uuid4` (`test_uuid_contracts.py`) |
| `code` | String(20), unique `uq_bdm_trips_code` | `TRV-` + 6-digit zero-padded `nextval('bdm_trip_code_seq')`; wider numbers are not truncated |
| `bdm_user_id` | UUID FK users | set from the session only |
| `travel_date`, `return_date` | Date | `ck_bdm_trips_dates`: `return_date >= travel_date` |
| `from_place`, `to_place` | String(120) | required, trimmed, no control characters |
| `purpose` | Text | required, ≤ 1000 |
| `mode` | String(10) | `ck_bdm_trips_mode`: `flight, train, bus, car, cab, local` |
| `accommodation_required` | Boolean | default false |
| `estimated_cost` | Numeric(14,2) | `ck_bdm_trips_estimated_cost`: ≥ 0 |
| `currency` | String(3) | default `INR`; `ck_bdm_trips_currency`: = `INR` |
| `approval_status` | String(12) | `ck_bdm_trips_approval_status`: `draft, submitted, approved, rejected`; default `draft` |
| `travel_status` | String(12) | `ck_bdm_trips_travel_status`: `planned, in_progress, completed, cancelled`; default `planned` |
| `rejection_reason` | Text, nullable | set on reject, cleared on resubmit |
| `decided_by_user_id` | UUID FK users, nullable | |
| `submitted_at`, `decided_at`, `completed_at`, `cancelled_at` | timestamptz, nullable | |
| `remarks` | Text, nullable | ≤ 2000 |
| `created_at`, `updated_at` | timestamptz | `TimestampMixin` |

Consistency: `ck_bdm_trips_status_pair`: `travel_status IN ('planned','cancelled') OR approval_status = 'approved'`.

Indexes: `ix_bdm_trips_bdm_travel_date (bdm_user_id, travel_date)`; partial
`ix_bdm_trips_submitted (bdm_user_id) WHERE approval_status = 'submitted'` (manager queue, bdm-023).

### 4.2 `bdm_trip_expenses`

| Column | Type | Rule |
|---|---|---|
| `id` | UUID PK | |
| `trip_id` | UUID FK `bdm_trips.id`, indexed | |
| `category` | String(10) | `ck_bdm_trip_expenses_category`: `travel, stay, food, local, other` |
| `amount` | Numeric(14,2) | `ck_bdm_trip_expenses_amount`: > 0 |
| `expense_date` | Date | |
| `note` | String(500), nullable | |
| `created_by_user_id` | UUID FK users | |
| `created_at`, `updated_at` | timestamptz | |

Actual cost is **never stored**: `COALESCE(SUM(amount), 0)` is computed on read (one grouped subquery for lists, so no N+1).

### 4.3 Sequence

`Sequence("bdm_trip_code_seq", metadata=Base.metadata)` in `models.py`, so `create_all` (0001) creates it on a fresh
database; 0066 creates it guarded (`CREATE SEQUENCE IF NOT EXISTS`). The downgrade drops it after the tables.

## 5. Backend

### 5.1 Schemas — appended to `schemas.py`

- `BdmTripCreate` / `BdmTripUpdate` (`extra="forbid"`; update = omitted means unchanged). Text through a `BdmText`-style
  annotated type (trimmed, control characters refused). `mode` and statuses are `Literal`s. A model validator enforces
  `return_date >= travel_date` with the message "Return date must be on or after the travel date".
- `BdmTripAmount`: a Decimal with ≤ 2 decimal places, ≥ 0 for estimated cost, > 0 for expenses, ≤ 1,00,00,000; plain-word
  messages in the `DepositAmount` style.
- `BdmTripReject` (`reason`: 1–1000 after trimming). `BdmTripExpenseCreate` / `BdmTripExpenseUpdate`.
- Outputs: `BdmTripRow` (list), `BdmTripOut` (detail: adds `expenses`, `rejection_reason`, `can_*` flags), `BdmTripPage`,
  `BdmTripExpenseOut`, `BdmPersonRef {id, full_name}`. Money serializes as a 2-dp string.
- `BDM_TRIP_FIELD_LABELS` for readable 422s, reusing `services/bdm._readable`'s approach.

### 5.2 Service — new `app/services/bdm_travel.py`

Functions only; nothing commits (the route owns the transaction). Logs carry ids and the route, never free text.

- **Transition table** — one dict, the single source for both enforcement and the `can_*` flags:

| Action | From (approval / travel) | To |
|---|---|---|
| edit fields | draft or rejected / planned | unchanged |
| edit remarks | any | unchanged |
| submit | draft or rejected / planned | submitted; `submitted_at`; `rejection_reason` cleared |
| withdraw | submitted / planned | draft |
| approve | submitted / planned | approved; `decided_by_user_id`, `decided_at` |
| reject | submitted / planned | rejected; reason; decided by/at |
| start | approved / planned | in_progress |
| complete | approved / planned or in_progress | completed; `completed_at` |
| cancel | any / planned or in_progress | cancelled; `cancelled_at` |
| expense add/edit/delete | approved / any | — |

  Refusals: editing fields while submitted → **409** "Withdraw the trip to edit it"; editing fields when approved or later →
  **422** "An approved trip's details can't be changed" (backlog case); any other action outside its row → **409** naming the
  current state; expense on a non-approved trip → **409**.
- `load_own_trip(db, user, trip_id, lock=False)` — `bdm_context`, then `WHERE id = :id AND bdm_user_id = :me`; else **404**.
- `load_team_trip(db, user, trip_id, lock=False)` — `require_manager`, join the owner's `BdmProfile` with `team_filter(user)`;
  else **404**.
- `decide(db, user, trip_id, approve, reason)`:
  1. `require_manager(user)`; lock the trip `FOR UPDATE` (scope as `load_team_trip`; **404** out of scope).
  2. Lock the owner's `BdmProfile` and the reporting manager's `User` row `FOR SHARE`.
  3. `bdm_manager`: must be that reporting manager, else **404**. `super_admin`: the manager must be inactive, else **403**
     "The reporting manager is active and decides this trip".
  4. `user.id == trip.bdm_user_id` → **403** (defence in depth).
  5. `approval_status != submitted` → **409**.
  6. Apply and write the audit row. The router then notifies the BDM (T12).
- `approvals_filter(user)` — the queue: submitted, still `planned` trips the caller may decide (a manager: their team's; a
  `super_admin`: those whose manager is inactive). A trip cancelled while submitted keeps `approval_status = submitted` for
  the record but leaves the queue, and `decide` refuses it with 409 (its row needs travel `planned`).
- `submit_recipients(db, trip) -> (users, action_url)` — the active manager with `/bdm/manager/approvals`, or, when the
  manager is inactive, every active `super_admin` with `/admin/bdm-travel-approvals` (T11).
- `next_code(db)` — `SELECT nextval('bdm_trip_code_seq')` → `TRV-{n:06d}`.
- `actual_cost_subquery()` — the grouped sum, for the list and the detail.

`_notify_user` and `_audit` are private helpers in `app/api/workflows.py`. Only api modules import `_notify_user`
(e.g. `agent_applications.py:22`), so the **router** sends notices with `_notify_user(..., channels=[])` — `channels=[]`
means in-app only; the default `None` would also queue email. The service writes `AuditLog` rows directly with the fields
`_audit` uses. No shared helper is changed, and no service imports from `app/api`.

### 5.3 Router — new `app/api/bdm_travel.py`, registered at `main.py:70`

| Method and path | Who | Notes |
|---|---|---|
| `GET /bdm/trips` | bdm | filters `approval_status`, `travel_status`; ordered `travel_date DESC, code DESC`; `limit` ≤ 100 |
| `POST /bdm/trips` | bdm | 201 → `BdmTripOut` |
| `GET /bdm/trips/{id}` | bdm (own) | |
| `PATCH /bdm/trips/{id}` | bdm (own) | fields and/or `remarks` |
| `POST /bdm/trips/{id}/{submit,withdraw,start,complete,cancel}` | bdm (own) | no body |
| `POST /bdm/trips/{id}/expenses` | bdm (own) | 201 |
| `PATCH`, `DELETE /bdm/trips/{id}/expenses/{eid}` | bdm (own) | the expense must belong to the trip, else 404 |
| `GET /bdm/manager/trips` | bdm_manager, super_admin | team scope; filters `bdm_user_id`, statuses |
| `GET /bdm/manager/trips/{id}` | bdm_manager, super_admin | read-only detail |
| `GET /bdm/manager/approvals` | bdm_manager, super_admin | `approvals_filter`, ordered `submitted_at` |
| `POST /bdm/manager/trips/{id}/approve`, `/reject` | approver | §5.2 `decide` |

No existing route or response changes.

### 5.4 Audit

`AuditLog(action, entity_type="bdm_trip", entity_id=<trip id>, outcome, metadata_json)`, written in the same transaction:
`bdm.trip_create`, `bdm.trip_update` (changed fields before/after; remarks included), `bdm.trip_submit`,
`bdm.trip_withdraw`, `bdm.trip_approve` (outcome `approved`), `bdm.trip_reject` (outcome `rejected`, the reason),
`bdm.trip_start`, `bdm.trip_complete`, `bdm.trip_cancel`, `bdm.trip_expense_add|update|delete` (category, amount, date).
Metadata carries ids, code, statuses and amounts; the rejection reason and remarks are the only free text (both needed).

### 5.5 Transactions, races and authorization

- Every state or expense change locks the trip row `FOR UPDATE` and re-checks state after the lock. Approve vs reject vs
  withdraw vs cancel therefore serialize; the loser gets 409 and the trip changes once.
- `decide` holds `FOR SHARE` on the profile and the manager row, so a concurrent deactivation or reassignment (each an
  `UPDATE` of one of those rows) waits until the decision commits — the rule from bdm-001 §5.8.
- `nextval` is safe under concurrent creates. The client disables the submit button while a request is pending; no
  idempotency key is added.
- Scope always comes from the session; the only ids in a path are the trip and expense ids, both scope-checked in SQL
  (404, never 403, for an out-of-scope id).
- `super_admin`'s read-all (`team_filter`) never grants decide-all: `decide` checks T3 explicitly.
- Inactive users can't sign in (`get_current_user`), so the inactive-manager test reads `User.active` of the reporting
  manager, never the caller.

## 6. Frontend

### 6.1 Navigation (`lib/navigation.ts`)

`BDM_NAV` gains "Travel" (`/bdm/travel`); `BDM_MANAGER_NAV` gains "Approvals" (`/bdm/manager/approvals`);
`SUPER_ADMIN_NAV` gains "BDM travel approvals" (`/admin/bdm-travel-approvals`). `middleware.ts` already guards
`/bdm*`, `/bdm/manager*` and `/admin*`.

### 6.2 Pages (async server components: `serverApi` → `accessUnavailable` → `PortalShell`, as bdm-001)

| Route | Content |
|---|---|
| `/bdm/travel` | `TripTable`: code, dates, From → To, mode, estimated and actual cost (INR), approval and travel status as text badges; status filter; link paging (`?offset=`) as `BdmTeamTable`; "New trip" link |
| `/bdm/travel/new` | `TripForm` (client); on save, go to the trip detail |
| `/bdm/travel/[id]` | detail list, `TripActions`, `TripExpenses`, remarks editor, rejection reason when rejected |
| `/bdm/manager/approvals` | `TripApprovalQueue` |
| `/bdm/manager/trips/[id]` | read-only detail + approve/reject when the caller may decide |
| `/admin/bdm-travel-approvals` | `TripApprovalQueue` (super_admin; inactive-manager trips only) |

### 6.3 Components and client

- New: `TripTable` (server), `TripForm` (create and edit), `TripActions` (confirm only on cancel), `TripExpenses`
  (table + add/edit/delete row form), `TripApprovalQueue` (modelled on `AgentApprovalPanel`; reject opens a labelled
  reason textarea).
- New `lib/bdmTravel.ts`: types, label maps (modes, statuses, categories), URL builders, `formatInr` reused from
  `lib/agentApplications.ts` (not moved).
- Reused: `FormMessage`, `PortalShell`, `formatCalendarDate`, `refocus` / `useFocusAfterRender`, `sendJson` / `sendRequest`.

### 6.4 States

- Loading: the acting button is disabled and reads "Saving…"; server pages render complete.
- Empty: "No trips yet — create your first trip"; queue: "Nothing waiting for approval"; expenses: "No expenses yet".
- Error: the API `detail` in `FormMessage` (`role="alert"`); the form keeps its input; page 404/403 → the existing
  access-unavailable state.
- After any action: `router.refresh()`. A 409 shows its message and refreshes, so the user sees the new state.

### 6.5 Responsive and accessible

- No page-level horizontal scroll at 375 px: tables sit in the existing `.table-wrap` (`role="region"`, labelled,
  `tabIndex=0`), which scrolls inside itself; forms are single-column below 640 px.
- Every input has a `<label>`; field errors use `aria-describedby`; focus moves to the alert or result; statuses are text,
  not colour alone; every action is reachable and operable by keyboard.

## 7. Acceptance criteria

| ID | Criterion |
|---|---|
| AC1 | All §3 stored fields and the 6 modes are accepted and returned; an unknown mode → 422. |
| AC2 | Submit → one in-app notification to the active reporting manager, or to every active `super_admin` when the manager is inactive; no email delivery row. |
| AC3 | Approve and reject each write an audit row; reject without a reason → 422. The BDM gets an in-app notice. |
| AC4 | Self-approval is impossible; another team's manager → 404; `super_admin` while the manager is active → 403; `super_admin` when the manager is inactive → allowed. |
| AC5 | Actual cost = the sum of expense lines (0.00 with none); expenses only on approved trips (else 409); amount ≤ 0 → 422. |
| AC6 | Currency is INR (stored, CHECKed, returned). |
| AC7 | Return date before travel date → 422; editing an approved trip's dates → 422; remarks stay editable in every state and each edit is audited. |
| AC8 | The transition table holds for every action and state; a disallowed transition → 409; withdraw and resubmit work. |
| AC9 | Concurrent approve and withdraw on one trip: exactly one succeeds, the other gets 409. |
| AC10 | Migration 0066 is additive, leaves one head, creates the sequence, and its downgrade refuses while trips exist. |
| AC11 | Pages show loading, empty and error states; no page-level horizontal scroll at 375 px; keyboard-only flow works. |
| AC12 | E2E: a BDM creates and submits Hyderabad → Vijayawada; the manager approves; the BDM adds expenses and completes the trip; actual cost shows the sum. |

## 8. Tests (written before the code, per task)

Backend (`apps/api/tests/`), unique values on the shared, never-truncated database:
- `bdm010_helpers.py` — a manager + BDM pair (via `bdm001_helpers`), a `trip_payload()`, and a direct-DB trip factory.
- `test_bdm_010_migration.py` — one head; tables, CHECKs and sequence exist; downgrade refusal (AC10).
- `test_bdm_010_schemas.py` — dates, amounts (2 dp, > 0 / ≥ 0, cap), modes, text rules (AC1, AC5, AC7).
- `test_bdm_010_service.py` — the transition table, table-driven (AC8); code format.
- `test_bdm_010_trips.py` — BDM CRUD, scope 404s, remarks audit, actual cost (AC1, AC5–AC7).
- `test_bdm_010_approvals.py` — decide rules, fallback, notices without email rows, audit (AC2–AC4).
- `test_bdm_010_expenses.py` — expense CRUD and state rules (AC5).
- `test_bdm_010_concurrency.py` — two sessions, approve vs withdraw (AC9).

Web (`apps/web/tests/`): `lib/bdmTravel.test.ts`; components `TripForm`, `TripExpenses`, `TripActions`,
`TripApprovalQueue`, `TripTable`; `BdmTravelPages.test.tsx` (empty, error, 404 states).

E2E: `apps/web/tests/e2e/bdm-010-travel.spec.ts` — users created through `/api/v1/admin/users` as bdm-001's spec does;
the AC12 flow, a reject + resubmit, a 375 px no-scroll check and a keyboard-only pass (AC11, AC12).

Lite set per task: the `test_bdm_010_*` and `test_bdm_001_*` files. The owner runs the full backend suite.

Existing tests updated:
- `test_agn_017_migration.py:27,46` pins `0065_agent_notifications` as the only head → assert exactly one head.
- `navigation.bdm.test.ts:12-13` lists the exact BDM nav hrefs → add Travel and Approvals.

## 9. Regression risks

| Risk | Mitigation |
|---|---|
| Shared files (`models.py`, `schemas.py`, `main.py:70`, `navigation.ts`) conflict with parallel work | append-only edits; recheck `origin/main` before building and before the PR |
| Migration / DEC numbers collide (bdm-002 also claims 0064/058) | re-chain on merge; one-head test |
| `super_admin` read-all leaks into decide-all | explicit T3 check + test |
| `channels=None` would send email | `channels=[]` + a test asserting no delivery row |
| A pending trip whose manager is reassigned | approver resolved at decision time (T2); bdm-025 needs no migration |
| Existing BDM pages | not edited apart from nav entries |

## 10. Documentation (updated in the same change)

- `docs/decisions/PRODUCT_DECISION_REGISTER.md` — `DEC-SCOPE-060` (T1–T13).
- `docs/architecture/RBAC_MATRIX.md` §2.13 — the travel routes and who may call them.
- `docs/ux/ROLE_NAVIGATION.md` — the three new nav entries.
- `docs/delivery/BDM_CRM_BACKLOG.md` — a status block under bdm-010.
- `docs/quality/RTM.md`, `API_CONTRACT.md`, `DATA_MODEL.md` — rows and addenda, as the AGN stories do.

## 11. Completion gates

Complete only when: AC1–AC12 pass; the lite backend set and the web unit tests are green; build and type check pass;
migration up/down verified; Playwright `bdm-010-travel.spec.ts` passes; responsive (375 px) and keyboard checks pass;
the documentation in §10 is updated; the owner's full backend run is green.
