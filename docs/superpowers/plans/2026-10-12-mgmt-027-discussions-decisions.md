# mgmt-027 — Discussions & decisions — implementation plan

Spec: `docs/superpowers/specs/2026-10-12-mgmt-027-discussions-decisions-design.md` (MD1–MD14). TDD per task; focused tests only.

## Review notes (Phase 3)

- **API:** PATCH is partial (`exclude_unset`); an explicit `null` clears an optional field; `participant_ids` replaces the set. Field rules
  that need the database (staff, active) raise FastAPI's field-located 422 shape, like `services/ledger.field_error`.
- **Security:** operational tier checked first on every management route; `/me` routes filter by `responsible_user_id = caller` inside
  the query, so another user's id is a 404 (IDOR). Storage keys are server-generated; download names are built server-side. The
  assignee serializer is a separate function that never reads the notes fields (MD14). Email body = the decision line only.
- **Transactions:** one commit per route after the row lock; notifications are queued in the same transaction (ENH-014 publishes after
  commit). A stored attachment is discarded if the write fails; a removed attachment's object is deleted after commit.
- **Frontend:** reuse `PortalShell`, `accessUnavailable`, `sendJson`/`sendRequest`, `fieldErrors`, the ledger form idioms (labels,
  `aria-invalid`, `.form-error`, disabled fieldset while busy). Loading = server render; empty states as `<p className="empty">`.

## Tasks

1. Migration 0151 + models (`ManagementDiscussion`, `…Participant`, `…Attachment`) + migration test.
2. `management_access.STAFF_ROLES`; service + schemas; `POST/GET/PATCH /management/discussions`, options, list filters/pending
   (tests: AC1, 403s, 422s, list).
3. `/me/management-decisions` list + status PATCH (AC2, AC3, 404/409) + notifications (assign/change/reassign) + audit verbs.
4. Attachments upload/download/remove (management) + shareable download on `/me`.
5. Web lib + vitest; pages + components; Command Center href; `/account/management-decisions`.
6. Playwright spec; docs (DEC-SCOPE, API §, RBAC §, backlog status).
