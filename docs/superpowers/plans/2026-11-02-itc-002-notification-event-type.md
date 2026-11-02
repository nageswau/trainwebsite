# itc-002 — Notification event type and record link (plan)

Source: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` §itc-002 (UNVERIFIED source PDF; owner Q-01 answered "all 5 phases, W0 first").
Decision: `DEC-SCOPE-336`. Dependencies: none.

## Design (calls made by the builder; owner answers were "proceed with recommended answers")
- **N1 DB** — migration `0221_notification_event_type`: nullable `event_type` (String 80), `entity_type` (String 50), `entity_id`
  (String 80, same as `audit_logs.entity_id`) on `notifications`, plus index `ix_notifications_user_read_created`
  on `(user_id, read, created_at)` (did not exist: only `user_id` is indexed). Existing rows keep NULLs.
- **N2 Catalogue** — `app/notifications/events.py`: `EVENTS[event_type] = Event(entity_type, title, body)`. Title/body are fixed,
  preview-safe text; callers cannot pass free text, so AC4 holds by construction (a test lints the catalogue for digits and
  currency). The PDF §7 rows are not in the repo, so the catalogue is derived from the backlog's references
  (`NEEDS_CONFIRMATION`: each blocked item confirms its own row).
- **N3 `notify(db, recipients, event_type, entity_id, *, action_url)`** — bulk-adds one row per recipient, one preference query,
  queues email + opted-in WhatsApp/SMS through the same outbox (`queue_deliveries` semantics: publish after root commit, rollback
  discards). Skips `None` and deactivated recipients; dedupes per (recipient, event, entity) within the transaction (a
  `session.info` set cleared by the existing root commit/rollback listeners). Unknown event type → `ValueError`.
- **N4 API** — `GET /workflows/notifications` items gain `event_type`, `entity_type`, `entity_id` (additive; null for old rows).
- **N5 Reference emitter** — `_ensure_receipt` issuing a NEW receipt for an IT-division student emits `it.fee.payment_received`
  (entity `payment`, link `/it/student/fees`). Covers the manual "paid" record and Razorpay verify/webhook. Overseas, agents,
  non-students: unchanged.
- **N6 FE** — the shared `SchoolNotificationList` gains a "Type" filter shown only when the list has typed notices (option label =
  the type's fixed title; client-side over the newest 100). IT students get a `Notifications` section (header-only portal payload,
  `PortalPage` mounts the list), never fee-locked.

## Tasks (TDD each)
1. Migration + model columns/index (`test_itc_002_migration.py`).
2. Catalogue + `notify()` (`test_itc_002_notify.py`): typed row; consent; rollback sends nothing; dedupe; inactive skipped;
   unknown type refused; catalogue preview-safe; batch of 40 in one call.
3. API additive fields (same file).
4. Payment emitter: paid manual payment → one typed notice; pending → none; overseas → none; second receipt call → no duplicate.
5. Portal section + nav + PortalPage + list filter (vitest + backend portal test).
6. Docs: decision register, API contract §12IH, RBAC §2.239 (no grant change), backlog status.

## Regression risks
`test_enh_014_*`, `test_not_001_*`, payment/receipt tests (nehn-019), every page that renders `SchoolNotificationList`
(agent, school, BDM, telecaller): the filter must not appear for untyped lists.
