# nehn-005 — Permission engine: implementation plan

Design: `docs/superpowers/specs/2026-10-26-nehn-005-permission-engine-design.md` (DEC-SCOPE-280).

## Tasks (TDD: red → green → refactor)

1. **Model and migration.**
   - Add the `RolePermission` model (`role_permissions`, PK `(role, resource, action)`, `granted_by_id` FK users `ON DELETE SET NULL`,
     `granted_at`) and migration `0195_role_permissions` (create if missing, seed `ON CONFLICT DO NOTHING`, downgrade drops it).
   - Tests: chain/single head; round trip in a throwaway database; the seed rows equal `rbac.DEFAULT_GRANTS`.
2. **Catalogue and checks.**
   - In `core/rbac.py`: `ACTIONS`, `CATALOGUE` (resource → label, actions), `ROLES = tuple(PERMISSIONS)`, `DEFAULT_GRANTS`
     (role → keys) and `permission_key`/`parse_key`.
   - New `services/permissions.py`: `has_grant(db, role, resource, action)` (super_admin → True; key not in catalogue → False; else
     a PK lookup), `role_grants(db, role)` and `replace_role_grants(db, actor, role, keys)` (diff, audit row, IntegrityError → 409).
   - Tests: unknown key → deny; super_admin → allow; the seed equals the old sets.
3. **Dependency.** Replace the unused `deps.require_permission(permission)` with `require_permission(resource, action, detail=...)`.
   Drop `rbac.user_has_permission`, which no longer has a caller.
4. **Admin endpoints and `/auth/me/permissions`** (a new router `api/permissions.py`, mounted at the `/admin` and `/auth` prefixes).
   - Tests: 401 anonymous, 403 for other roles, 404 for an unknown role, 422 for an unknown key, 409 for super_admin; the audit row;
     no audit row on a no-op.
5. **Pilot wiring.**
   - The admin payment routes and the telecaller reports routes use `require_permission`.
   - Remove `REPORT_ROLES` and the inline role check.
   - Tests: the 28-role equivalence matrix on all six pilot routes; revoke/restore without a restart (AC2/AC3); download revoked while
     the view still works (AC7).
6. **Docs:** DEC-SCOPE-280, API §12GF, RBAC §2.194, the DATA_MODEL table, and the backlog status line.

## Phase 3 review notes (folded in)

- **API.** `PUT` is a full replace, and so idempotent. Keys are strings `resource.action`. Unknown keys and duplicates are validated
  with Pydantic, which gives 422.
  - **Check order:** auth (401), then caller is super_admin (403), then role known (404), then body (422), then super_admin target
    (409).
  - A non-super-admin therefore never learns which role names exist.
- **Transactions.** The diff and the audit row commit together. On an IntegrityError: roll back, then 409.
- **Security.**
  - **Escalation:** only super_admin edits.
  - **IDOR:** n/a (role-level).
  - **Input:** `role` is checked against a fixed set, and the keys against the catalogue.
  - **SQL:** ORM only.
  - **Logging:** an info line with the actor, the role, and the added and removed keys (no PII).
- **Frontend.** No change in this item. Browser QA checks that the existing admin payments page and telecaller reports page still work
  for their roles, and that a revoked grant shows the page's existing error state.
