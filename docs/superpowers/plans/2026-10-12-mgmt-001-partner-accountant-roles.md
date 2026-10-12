# mgmt-001 implementation plan

Spec: `docs/superpowers/specs/2026-10-12-mgmt-001-partner-accountant-roles-design.md`. TDD per task (RED → GREEN → refactor). Focused tests only.

## Phase 3 review notes folded in
- **API:** `GET /management/me` is a self read (no id → no IDOR); 401 before 403; response is a typed Pydantic model. `POST /admin/users`
  keeps its contract (201 body unchanged); the new refusals reuse the existing 403/422 shapes and order (creator → division → role set).
  MG6's 422 is not a 409 (the Users page reads 409 as the trainer cascade prompt).
- **Transactions/races:** MG6 locks every active partner row `FOR UPDATE` before counting, in the request's transaction.
- **Security:** no existing gate widened (AC5); partner-only tier excludes `super_admin` by construction and by test; the welcome token
  flow, cookie session and audit rows (`user.create` / `user.update`) are reused unchanged; no secrets or PII in new logs.
- **Frontend:** server page, no client state; reuse `PortalShell`, `accessUnavailable`, the `card`/`empty` classes and the PU8 "coming
  soon" idiom; headings per section (`aria-labelledby`), plain text for non-live entries, responsive `columns` list.

## Tasks
1. `management_access.py` tier helpers + `rbac.PERMISSIONS` (unit tests: truth table incl. super_admin partner-only = False).
2. `POST /admin/users`: partner/accountant creation (super_admin 201 + welcome link; it_admin/overseas_admin 403; non-global 422),
   `ADMIN_PORTAL_ROLES` (set-password URL + reset `login_portal`). AC1 end-to-end: create 2 partners + accountant, set password, login.
3. `PATCH /admin/users/{id}`: MG6 last-active-partner 422; deactivated partner → 401 on `/management/me`.
4. `GET /management/me` + router registration (per-role cases, 401, 403).
5. Seed demo partner ×2 + accountant.
6. Web: middleware `/management`; landing map; `MANAGEMENT_PILLARS` / `managementNavFor`; `SUPER_ADMIN_NAV` link; `ROLES_BY_DIVISION`;
   login / forgot copy (vitest first).
7. Web: `/management` page + `ManagementPillars` (vitest first).
8. Playwright e2e spec; docs (DEC-SCOPE, API §, RBAC §, backlog status, QA report) after merging main.
