# mgmt-002 — Management audit trail ("who did what") — design

- **Feature:** `mgmt-002` (`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-002). Depends on mgmt-001 (merged, PR #243).
- **Evidence:** `EVID-017` §2 (seven "who did X" audit points), Management M2/M13 (`EXPLICIT_APPROVAL`, `DEC-SCOPE-186`).
- **Decision:** `DEC-SCOPE-187` (provisional number). Answers MA1–MA11 below are **recommended defaults, `UNVERIFIED`**, taken on the
  owner's instruction to proceed with recommended answers. Q-33 (masking and retention) stays open; MA3 is its interim default.

## 1. Intent

Partners must be able to see who on the management team did what: created a task, changed a target, approved an expense, added an
investment, changed a financial figure, made a decision, completed an action. No management record exists yet (mgmt-004 onward
build them), so mgmt-002 delivers the **one write helper** every later mgmt write calls, plus the **read side**: the
`GET /management/activity` endpoint and the Management Activity page, both filtered by the M13 tiers.

## 2. Decisions (MA1–MA11)

| # | Point | Answer |
|---|---|---|
| MA1 | Kinds | A fixed server catalogue `management_audit.KINDS`: `entity_type` → label + tier. Initial kinds: `mgmt.task` (operational), `mgmt.plan` (operational: plans and targets), `mgmt.decision` (operational), `mgmt.ledger` (finance: income, expenses, financial figures), `mgmt.investment` (partner-only), `mgmt.capital` (partner-only). Each later item registers its own kind here; the helper refuses an unregistered kind |
| MA2 | Verbs | `create`, `update`, `approve`, `complete`, `decide`, `import`. The action is `<entity_type>.<verb>` (e.g. `mgmt.ledger.approve`). The seven §2 points map to: task create, plan update, ledger approve, investment create, ledger update, decision decide, task complete |
| MA3 | Values (Q-33 interim) | Field **names** always. Before/after **values** only for finance and partner-only kinds, only for fields named in the same entry, stored as strings. Operational kinds never store values. No PII is passed by any caller |
| MA4 | Bulk | One entry with verb `import` and a `count` |
| MA5 | Visibility | An entry is visible when the caller can view its kind's tier: partner all; accountant finance; super_admin operational. A `kind` filter outside the caller's tiers returns an empty page (`200`), not `403`. An unknown kind → `422`. No management tier → `403` |
| MA6 | Filters and paging | `actor` (user id), `kind`, `date_from` / `date_to` (IST days, inclusive; `date_to` before `date_from` → `422`), `limit` 1–100 (default 25), `offset` 0–10 000. Newest first |
| MA7 | Response | `{items, total, limit, offset, kinds, actors}`. An item: `id, at, actor {id, full_name, role} | null, kind, kind_label, verb, entity_id, fields, values, count`. `kinds` and `actors` are the filter choices the caller may use (actors = people with at least one visible entry) |
| MA8 | Existing audit views | `GET /admin/audit` and `POST /admin/audit/export` leave out finance and partner-only `mgmt.*` entries (M13: super_admin sees no finance, investment or capital data). Every other row is unchanged |
| MA9 | Index | **No migration.** `ix_audit_logs_entity (entity_type, entity_id, created_at)` already leads with `entity_type`, and the query is `entity_type IN (visible kinds)` |
| MA10 | Immutability | No edit or delete route. The helper only adds a row in the caller's transaction (no commit), so the record and its audit row commit together or not at all |
| MA11 | "Created by / last changed by" | Each record-owning item (mgmt-004+) shows its own `created_by` / `updated_by` columns (backlog §4 convention). mgmt-002 shows "by <name> · <date>" on every activity row |

## 3. Components

- `apps/api/app/services/management_audit.py` (new): `KINDS`, `VERBS`, `record(db, actor, kind, verb, entity_id, *, fields, values, count)`,
  `visible_kinds(user)`, `hidden_from_admin_audit()` (the SQL clause MA8 uses), `activity(db, user, filters)`.
- `apps/api/app/api/management.py`: `GET /management/activity`.
- `apps/api/app/schemas.py`: `ManagementActivityOut` and its parts.
- `apps/api/app/api/admin.py`: `/audit` and `/audit/export` add the MA8 clause.
- Web: `lib/management.ts` (types, URL builder, nav entry), `app/management/activity/page.tsx` (server page, GET filter form, paging
  links, empty / error / 403 states), a link on the Command Center page.

## 4. Error handling

`401` signed out; `403` no tier (the page shows the access card); `422` bad filter (the page shows the message above the form and keeps
the filters); any other failure shows "Activity is unavailable right now" with the form still usable.

## 5. Testing

- Backend `tests/test_mgmt_002_activity.py`: AC1 (seven kinds produce an entry with the actor), AC2 (accountant cannot see an
  investment entry), Partner 2 sees Partner 1's approval, super_admin capital filter → none, bulk count, MA3 value guard, unknown kind
  and verb refused, filters (actor, kind, dates), paging, 403/401, `/admin/audit` and export hide finance and partner-only rows.
- Web `management.test.ts` (URL builder, nav), `ManagementActivity.test.tsx` (rows, empty state, filter form).
- Playwright `mgmt-002-activity.spec.ts`: partner sees seeded entries and filters; accountant does not see partner-only ones.
