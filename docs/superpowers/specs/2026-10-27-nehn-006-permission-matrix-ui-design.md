# nehn-006 — Admin permission-matrix UI, permission-driven navigation and page guard (design)

- **Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-006` (§5 L122-128, L126; `MEETING_TRANSCRIPT_REQUEST`,
  `UNVERIFIED` backlog).
- **Dependency:** nehn-005 permission engine (`DEC-SCOPE-281`), merged (#347). nehn-030 (`DEC-SCOPE-293`) added `certificates.view`.
- **Decision:** `DEC-SCOPE-295`. **RBAC:** §2.206. **API:** §12GS. **Migration:** none.

## Intent

A Super Admin switches a role's permissions on and off on one screen, and every portal reflects it: a menu entry the role can no longer
use disappears, its page (typed URL) shows the access-unavailable card, and Add/Download controls the role lacks are not rendered. The
API (nehn-005) stays the authority; the UI is convenience plus defence in depth.

## Goals

- `/admin/permissions`: role selector, rows = catalogue resources, columns = the nine actions, a labelled checkbox per applicable cell,
  Save / Discard, an unsaved-changes guard.
- `GET /auth/me/permissions` drives the sidebar items and action controls that map to a catalogue resource.
- A page whose `view` grant is missing is refused by the API and shows the existing access card.

## Non-goals

- Per-user overrides (nehn-007), column policy (nehn-008), custom roles, new catalogue resources.
- Replacing the ~200 role-literal checks in web code. Only surfaces backed by a catalogue resource are permission-driven.
- Any change to who may edit grants (super_admin only, nehn-005 P6).

## Anti-goals

- A toggle that changes nothing (every catalogue key already gates a route — nehn-005 P1).
- A nav that hides items the role *does* hold (e.g. a failed permissions fetch must not blank the menu).
- A page that leaks data the toggle was meant to close.

## Builder's defaults (owner pre-authorised recommended answers; each `NEEDS_CONFIRMATION`)

| # | Open question | Default in place |
|---|---|---|
| M1 | Matrix per role or per user? | Per role only. Per-user is nehn-007. |
| M2 | Show non-applicable actions? | Yes, as a "—" cell (visually hidden "not applicable"), not focusable or clickable, so the nine columns line up. |
| M3 | Where does the role list come from? | `GET /admin/permissions/catalogue` gains an additive `roles` field (`rbac.ROLES`, all 29). Labels via the existing `roleLabel()`. |
| M4 | "Grouped by module" | The catalogue has one entry per module resource; rows follow catalogue order, labelled by the resource label. No extra grouping level. |
| M5 | Two admins editing at once | nehn-005's last-write-wins replace; a racing insert is its 409, shown with a "Reload" action. |
| M6 | "One audit entry per changed cell" (AC3) | nehn-005 writes one `audit_logs` row per save whose `added`/`removed` list every changed cell (so each changed cell is recorded). Splitting into one row per cell would change nehn-005's audited contract (its AC5); kept. |
| M7 | Revoking the editor's own access | The editor is super_admin, whose grants cannot change (nehn-005 P5); the super_admin role is shown read-only, every cell ticked. |
| M8 | "403 page" | The existing access-unavailable card (`AccessUnavailable`), which every portal already shows for an API 403. |
| M9 | While permissions are loading or the fetch fails | Nav/controls render as before (the API still refuses). Once the set is known, ungranted items are removed. With the seed grants nothing is removed, so there is no flash for default roles. |
| M10 | Caching | Module-level cache in the client (one fetch per full page load) plus a revalidating fetch on each portal mount, so a revoked item goes on the next navigation. |

## Design

### Backend (small, additive)

- `GET /admin/permissions/catalogue` response gains `"roles": [...]` (29 keys). Existing fields unchanged.
- `services/portal.py` admin `payments` section (`/portal/it/admin/payments`, `/portal/overseas/admin/payments`): requires
  `payments.view` (`permissions.has_grant`), else 403 "You do not have permission to view payments". Today only `/admin/payments` was
  grant-gated, so revoking `payments.view` left the portal page listing payments. Day-one equivalent: it_admin and overseas_admin hold
  the key by seed; super_admin holds everything.

### Web

- `lib/navigation.ts`: `NavItem.resource?: string`. Tagged items:
  - it/admin and overseas/admin **Payments** → `payments`
  - it/admin and overseas/admin **Telecaller Reports**, the telecaller manager's **Reports** → `reports.telecaller`
  - it/coordinator **Certificates** → `certificates`
  - The super-admin nav is not tagged (super_admin holds everything). The it/admin **Certificates** is *not* tagged: it is governed by
    its own role check, not `certificates.view`.
  - `navForPermissions(nav, permissions)` drops a tagged item whose `<resource>.view` is missing (children too).
- `lib/usePermissions.ts`: `usePermissions(enabled)` → `string[] | null`; module cache + revalidate on mount.
- `PortalShell`: filters `nav` with the hook only when some item is tagged (no extra request elsewhere).
- `WorkflowPanel`: `ActionSpec.permission?`; "Create payment due" = `payments.add`, "Apply discount" = `discounts.add`; a spec whose
  permission is known-missing is not rendered.
- `TelecallerReportsPage` (server): reads `/auth/me/permissions` beside the report; `TelecallerReportView` hides the export buttons
  without `reports.telecaller.download`.
- `/admin/permissions` page (server): super_admin check (others → access card), reads the catalogue, renders `PortalShell` +
  `PermissionMatrix` (client). `SUPER_ADMIN_NAV` gains "Permissions" after "Roles".
- `PermissionMatrix`: `<select>` role picker; fetches `GET /admin/roles/{role}/permissions` (loading / error with Retry); table inside
  a focusable, labelled scroll region (`overflow-x:auto`) so the page never scrolls sideways; `<th scope>` headers; checkbox
  `aria-label="<Resource>: <Action>"`; Save (disabled when clean, "Saving…") → `PUT`; `role="status"` success ("Saved — 2 changes"),
  `role="alert"` error; Discard; `useLeaveGuard` while dirty; switching role while dirty asks first.

## Acceptance criteria (testable)

1. AC1 Super admin unticks `it_admin → payments.view` and saves; the IT admin's sidebar no longer shows Payments on the next page, and
   `/it/admin/payments` shows the access card (API 403). Re-granting restores both. (The backlog's `recruiter` holds no payments page;
   it_admin is the role that does.)
2. AC2 The matrix shows every catalogue resource × the nine actions; non-applicable cells have no checkbox.
3. AC3 A save writes an audit row naming every changed cell (`added`/`removed`); a no-op save is not possible (button disabled).
4. AC4 Toggles are native, labelled checkboxes (keyboard + screen reader); at 375 px the page has no horizontal scroll and the matrix
   scrolls inside its own region.
5. AC5 A non-super-admin opening `/admin/permissions` gets the access card.
6. AC6 Without `payments.add` / `discounts.add` the payment forms are not shown; without `reports.telecaller.download` the export
   buttons are not shown while the report still renders.
7. AC7 Unsaved changes: switching role or following a link asks first; Discard restores the saved set.

## Regression risks

- Every portal's nav (only tagged items can change; untagged navs never fetch).
- Vitest suites that count `fetch` calls on pages with tagged navs.
- e2e specs that click Payments / Telecaller Reports / Certificates (default grants keep them).

## Security review

- No new write path; the matrix uses nehn-005's super_admin-only endpoints (401/403/404/409/422 unchanged).
- Hidden UI is not security: every hidden surface is also refused by the API (the portal payments section is closed here).
- No grant logic in the web app beyond "is this key in my set". XSS: labels rendered as text. CSRF: existing cookie model.
