# nehn-005 — Permission engine: role × resource × action, DB-backed, enforced on the API

Source: `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-005` (§5 L89-128; `MEETING_TRANSCRIPT_REQUEST`, `UNVERIFIED`
backlog). Decision: `DEC-SCOPE-281`. Numbering: migration `0196_role_permissions`, API §12GG, RBAC §2.195. Dependencies: none upstream.

## Intent

An administrator decides, per role, which resource actions (View, Add, Edit, Delete, Download, Approve, Review, Issue, Manage) the role
may use, and the API enforces it, so a hidden button or a direct URL cannot bypass it. The backlog scopes this item to **the engine plus
1–2 pilot modules**. Every other module keeps its inline role checks and moves over in a later slice once tests prove the new check is
equivalent.

## Goals

- A permission catalogue in code, a DB table of role grants, and `require_permission(resource, action)`, which denies by default.
- The day-one grants reproduce today's behaviour exactly (a seeded-equivalence test proves it for every role on every pilot route).
- Admin endpoints to read the catalogue and to read and replace a role's grants, plus `GET /auth/me/permissions`.
- Every grant change is audited with who changed it, and the before and after.
- The two pilot modules use `require_permission` only, and their inline role checks are removed.

## Non-goals

- No UI (that is nehn-006), no per-user overrides (nehn-007) and no column policy (nehn-008).
- No retrofit of the other ~125 routers.
- The coarse `PERMISSIONS` bundles and `has_permission` are unchanged (tests and the read-only admin roles view use them).
- No change to the JWT.

## Anti-goals

- A mis-seed that widens or narrows access on day one.
- A route whose record scope (division, own team) is weakened: the engine says *may*, and the service still says *which rows*.
- Lock-out: super_admin always holds everything.

## Builder's defaults (owner pre-authorised recommended answers; each is `NEEDS_CONFIRMATION`)

- **P1 Catalogue granularity: per module, and grown slice by slice.** The catalogue lists only the resources whose routes are wired.
  An unwired resource in the catalogue would show nehn-006 a toggle that does nothing. Today it holds:
  - `payments`: `view`, `add`
  - `discounts`: `add`
  - `reports.telecaller`: `view`, `download`

  Keys are `<resource>.<action>`.
- **P2 Pilot modules.**
  - **Admin payments:**
    - `GET /admin/payments` needs `payments.view`.
    - `POST /admin/payments` and `POST /admin/payments/emi-schedule` need `payments.add`.
    - `POST /admin/payments/{id}/discount` needs `discounts.add`.
  - **Telecaller reports:**
    - `GET /telecaller/reports/{kind}` needs `reports.telecaller.view`.
    - `GET /telecaller/reports/{kind}.csv` needs `reports.telecaller.download`.
  - Each route checks only its own action.
- **P3 Seed.**
  - Admin payments: `it_admin` and `overseas_admin` hold `payments.view`, `payments.add` and `discounts.add`. This was the
    `ensure_admin` set.
  - Telecaller reports: `telecaller_manager`, `it_admin` and `overseas_admin` hold `reports.telecaller.view` and
    `reports.telecaller.download`. This was `REPORT_ROLES`.
  - super_admin is implicit, as below.
- **P4 Role source.** The caller's legacy `users.role` column, which every inline check reads today, so the behaviour stays equivalent.
  A union across several `UserRoleAssignment` rows is deferred (`NEEDS_CONFIRMATION`).
- **P5 super_admin.**
  - super_admin holds every permission in code and has no rows.
  - `PUT /admin/roles/super_admin/permissions` returns 409.
- **P6 Who edits.** Only super_admin reads or edits grants (the three `/admin/...permission...` endpoints). Division admins are not
  allowed (open question 2), and nobody can grant something they lack, because super_admin holds everything.
- **P7 Caching.**
  - There is no in-process cache. Each check is one primary-key lookup on `role_permissions`.
  - That makes a change effective on the very next request on every API worker, with no restart and no cross-worker invalidation
    to get wrong.
  - The table is tiny, so the cost is under a millisecond.
- **P8 Storage.**
  - One table, `role_permissions(role, resource, action, granted_by_id, granted_at)`, keyed on `(role, resource, action)`.
  - The catalogue lives in code, so a separate `permissions` table would only duplicate it.
  - History goes to the existing `audit_logs` (`action="role_permissions.update"`, `entity_type="role"`, `entity_id=<role>`,
    metadata `before`/`after`/`added`/`removed`). There is no separate `permission_audit` table.
- **P9 Refusal text.** Each pilot route keeps its existing 403 detail, so the API contract and its tests stay unchanged:
  - Admin payments: "Admin role required".
  - Telecaller reports: "Telecaller reports are for managers and administrators".
  - Exception (browser QA-01): the CSV download's refusal is now "You don't have permission to download telecaller reports". A manager
    whose download alone is revoked still reads the report, so "for managers" would be wrong.
- **P10 Concurrency.**
  - `PUT` replaces the set by computing a diff, deleting the removed grants and inserting the added ones in one transaction.
  - A concurrent insert of the same key raises an IntegrityError, which returns 409 "changed by someone else, reload".
  - A no-op `PUT` writes no audit row.
- **P11 Agent Master → Staff flags** (`can_verify_documents`/`can_view_reports`) stay organisation-level and separate (open question 3).
- **P12 Custom roles:** none. Roles are the 28 keys of `PERMISSIONS` (open question 4).

## API (§12GG)

| Method | Path | Who | Result |
|---|---|---|---|
| GET | `/admin/permissions/catalogue` | super_admin | `{"actions": [...], "resources": [{"key", "label", "actions": [...]}]}` |
| GET | `/admin/roles/{role}/permissions` | super_admin | `{"role", "permissions": ["payments.view", ...], "editable": bool}`; unknown role → 404 |
| PUT | `/admin/roles/{role}/permissions` | super_admin | body `{"permissions": [...]}` → same shape; unknown key → 422; super_admin → 409; unknown role → 404 |
| GET | `/auth/me/permissions` | any signed-in user | `{"role", "permissions": [...]}` (super_admin → the whole catalogue) |

Other signed-in roles get 403 on the admin endpoints, and anonymous callers get 401.

## Acceptance criteria (from the backlog, made testable)

1. With the seed only, every role × pilot route returns the same status as before (equivalence test). The existing tel-024, tel-026,
   payment and discount suites pass unchanged.
2. `PUT` without `payments.view` for it_admin makes `GET /admin/payments` return 403. Restoring it returns 200 on the next request, with
   no restart.
3. A direct API call to a revoked resource returns 403.
4. `PUT /admin/roles/super_admin/permissions` returns 409, and super_admin still reaches every pilot route.
5. A grant change writes one `audit_logs` row with the actor, the role, and the before and after.
6. The pilot routes declare `require_permission`, and `ensure_admin` and `REPORT_ROLES` are gone from them.
7. Removing `reports.telecaller.download` from telecaller_manager gives 403 on `.csv`, while the JSON report still returns 200.
8. A non-super-admin `PUT` returns 403, and an unknown key returns 422.

## Migration 0196

- 0001 builds a fresh database from the current models, which already include the table. So the table is created only when it is
  missing, and the seed is inserted `ON CONFLICT DO NOTHING`.
- The downgrade drops the table.
- No existing row changes.

## Regression risks

- `ensure_admin` stays for every other admin route.
- Record scope stays in each route.
- The tel-026 matrix and the payment and discount suites are the oracle.
