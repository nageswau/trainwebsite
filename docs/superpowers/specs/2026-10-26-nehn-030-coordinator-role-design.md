# nehn-030 — IT Coordinator role and account model (design)

- **Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-030` (`UNVERIFIED` backlog); `DEC-ROLE-003`
  (CONFIRMED_CURRENT 2026-09-12: a new distinct role with exclusive issuance; account model and duties open = OD-05).
- **Dependency:** nehn-005 permission engine (`DEC-SCOPE-281`), merged. The coordinator is "born on the matrix".
- **Decision:** `DEC-SCOPE-293`. **RBAC:** §2.204. **Migration:** `0201_coordinator_role` (data only).

## Intent

Certificates are to be issued by a Coordinator, not by trainers or admins (`DEC-ROLE-003`). This item makes the role itself exist: an
admin can create one, the coordinator signs in to its own portal with a Certificates section, and sees nothing else. nehn-031 then
moves issuance onto it; nehn-032 adds its signature.

## Builder's defaults (owner pre-authorised the recommended answers; `NEEDS_CONFIRMATION`, OD-05)

| # | Open question | Default in place |
|---|---|---|
| C1 | New account type, or a permission on existing staff? | A new account type: role `coordinator`, one role per user, like every other role. |
| C2 | IT only, or overseas too? | IT only (division `it`). Certificates are IT programme certificates. |
| C3 | Duties beyond certificates? | None yet. The portal has Dashboard and Certificates, plus the shared Management tasks link every staff portal has. |
| C4 | Who creates one? | `it_admin` and `super_admin`, through the existing `POST /admin/users` welcome-link provisioning (no password chosen by the admin). |
| C5 | Sign-in, MFA | `/it/login`, standard login; it lands on `/it/coordinator/dashboard`. No MFA exists in the product, so none is added. |
| C6 | One person who is both trainer and coordinator | Not supported: two accounts (one role per user, the existing model). |
| C7 | Trainer/Admin issuance | Unchanged here. `DEC-ROLE-003` forbids removing it before the replacement exists; nehn-031 cuts it over. |

## Design

**Role.** `core/rbac.py`: `PERMISSIONS["coordinator"] = {"it:certificates:read"}` (the coarse bundle). `ROLES` grows to 29.

**On the matrix (nehn-005).** The catalogue gains the resource `certificates` with the action `view` only (nehn-031 adds `issue`).
`DEFAULT_GRANTS["coordinator"] = ("certificates.view",)`. Migration `0201` inserts that one `role_permissions` row (frozen copy, as 0196
did); downgrade deletes it. No other role gains the key: the admin Certificates page keeps its own role check, unchanged. A Super
Admin can revoke or restore the grant through the existing `PUT /admin/roles/coordinator/permissions`.

**Portal.** The existing `GET /portal/it/coordinator/{section}` route already matches a role whose segment equals its name.
`services/portal.section_payload` dispatches `coordinator` to a new `_coordinator`:
- any section other than `dashboard`/`certificates` → `None` (404), as the IT counselor does;
- `certificates`: with `certificates.view` the issued-certificate table (same query and columns as the admin Certificates page:
  number, student, programme, issued, status, override); without it 403 "You do not have permission to view certificates";
- `dashboard`: with the grant, metrics (certificates issued, issued via override) and the five latest certificates; without it a
  header-only payload saying the Certificates permission is off. Read-only either way.

Every other route keeps deny-by-default. The coordinator holds no `users:*`, `it:*` or finance bundle and no admin role-set, so
`/admin/*`, `/portal/it/admin/*`, `/admin/payments` etc. answer 403 (AC2).

**Provisioning.** `api/admin.py` `allowed_by_division["it"]` gains `coordinator`. The welcome link goes to `/it/reset-password`
(division it, not an admin-portal role). `seed.py` adds `coordinator@edusphere.local` ("Meera Coordinator", it).

**Web.** `ROLE_DASHBOARD_PATH.coordinator = "/it/coordinator/dashboard"`; `PORTAL_NAV["it/coordinator"]` = Dashboard, Certificates,
Management tasks; `app/it/coordinator/{dashboard,[section]}/page.tsx` (the HR pages' two-liners); `PortalPage` label "Coordinator";
`middleware.ts` protects `/it/coordinator`; the user-creation dropdown (`WorkflowPanel` `ROLES_BY_DIVISION.it`) offers it; the Super
Admin static roles list gains a row. `WorkflowPanel` returns no action forms for the role (its default).

## Acceptance criteria (testable)

1. AC1 An it_admin (and super_admin) creates a coordinator in division it (201); an overseas_admin cannot (403 other division /
   422 overseas). The coordinator sets a password, signs in at `/it/login` and lands on `/it/coordinator/dashboard`.
2. AC2 The coordinator gets 403 on `/admin/users`, `/admin/payments`, `/portal/it/admin/dashboard`, `/portal/it/trainer/dashboard`,
   the trainer issue route; a typed `/it/admin/users` URL shows the access-unavailable card; unknown sections 404.
3. AC3 `rbac.ROLES` includes coordinator (29); the nehn-005 role-equivalence test runs for it; RBAC_MATRIX §2.204 documents it.
4. AC4 Certificates section lists issued certificates with the grant; revoking `certificates.view` gives 403 there and a header-only
   dashboard; restoring it brings them back on the next request.
5. AC5 Fresh migration: the seeded grant table equals `DEFAULT_GRANTS` (includes the coordinator row); downgrade removes only that row.

## Review notes (Phase 3)

- **API:** no new route or schema; existing portal payload shape reused. Status codes follow the route's existing order
  (401 → role/division 403 → grant 403 → 404 section).
- **Security:** a new privileged-adjacent role with read-only certificate data (student names). Least privilege: only one key; no
  users/content bundles. No IDOR surface (no id parameters). Role escalation: only it_admin/super_admin create it, within their
  division check; the role cannot create users. Read-only, so no CSRF concern beyond the existing cookie/bearer model.
- **Frontend:** reuses PortalShell/PortalSection (existing loading, empty "No records" and error/access-unavailable states, responsive
  table). No new components.
- **Regression risk:** literal role lists that assume a closed set; the `ROLES == 28` and catalogue-set assertions in
  `test_nehn_005_permissions.py` are updated deliberately (the catalogue is meant to grow per module slice).
