# mgmt-028 — Management to-do + staff "Management tasks" — implementation plan

Spec: `docs/superpowers/specs/2026-10-12-mgmt-028-management-tasks-design.md` (MT1–MT14). TDD per task; focused tests only.

## Review notes (Phase 3)

- **API:** mirrors mgmt-027. `PATCH /management/tasks/{id}` is partial (`exclude_unset`); title, owner, priority, deadline and status
  can't be sent as `null` (`422`). `band` is a `Literal` query param (unknown → `422`); `owner` is `me` or a user id. Create is `201`.
  The owner check needs the database, so it raises `services/ledger.field_error`'s field-located `422`. No pagination on `/me` (the
  owner's own, bounded by the 7-day Completed window; a hard cap of 200 rows guards the response).
- **Security:** operational tier is checked first on every `/management/tasks*` route (accountant gets mgmt-027's "Operational
  management access required"). `/me` routes filter by `owner_user_id = caller` inside the query and re-check after the row lock, so
  another user's id is a `404` (IDOR, AC3). The client never sets `source`, `created_by` or `completed_at`. Logs carry ids, status and
  field names only — never task titles. React escapes every string (no `dangerouslySetInnerHTML`); writes go through `sendJson` with the
  app's cookie session like every other form. No rate limit: management-only writes, owner writes are a status change.
- **Transactions:** one commit per route after the row lock; notification + audit rows are added in the same transaction.
- **Frontend:** reuse `PortalShell` (via a `TasksShell` like `DiscussionsShell`), `accessUnavailable`, `sendJson`, `fieldErrors`, the
  `DiscussionForm` idioms (labels, `aria-invalid`, `.form-error`, disabled fieldset while busy, one save per double click). Bands are
  `<section>`s with an `<h2>` and a count; colour never carries meaning alone (the band name is text; the 🔴🟠🟡🟢 markers are
  `aria-hidden`). Empty band → not rendered; no tasks at all → `<p className="empty">`. Cards wrap (`overflowWrap: anywhere`) for 320 px.
- **Regression:** nav arrays gain one entry each (append, existing order unchanged); check nav tests that compare arrays.

## Tasks

1. Migration `0153_management_tasks` + `ManagementTask` model + migration test.
2. Service bands (`week_end`, `band_of`, `band_filter`) — pure tests with fixed IST days (AC1).
3. Schemas + `POST/GET/PATCH /management/tasks`, options, list (owner/band, counts) — tests: 403s, 422s, list bands (AC1), audit.
4. `/me/management-tasks` list + status PATCH (AC2, AC3 404, 409) + notifications (assign / change / reassign / none on own).
5. Web `lib/managementTasks.ts` + vitest; components (`ManagementTaskBands`, `ManagementTasks`, `ManagementTaskForm`,
   `MyManagementTasks`, `TasksShell`) + vitest; pages; `lib/management.ts` To-do live; `lib/navigation.ts` staff entries.
6. Seed demo tasks (optional, for QA); Playwright `mgmt-028-tasks.spec.ts`; docs (DEC-SCOPE, API §, RBAC §, backlog status).
