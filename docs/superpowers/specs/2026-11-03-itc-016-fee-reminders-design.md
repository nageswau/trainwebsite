# itc-016 — Overdue marking and fee reminders (design + plan)

**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-016 (classification `UNVERIFIED` PDF §6 "paid/unpaid/overdue status, and
reminder history", §9 "Send reminders for upcoming/overdue installments"; owner-approved for build in waves by Q-01, 2026-11-01).
**Decision:** `DEC-SCOPE-358`. **Dependencies:** itc-002 (merged, DEC-SCOPE-336), itc-003 (merged, DEC-SCOPE-338), itc-013 (merged,
DEC-SCOPE-346). Q-16 is open; built with the recommended answers below (owner: "proceed with recommended answers"), each
`NEEDS_CONFIRMATION`.

## Discovery (graphify-led)

| Class | Item |
|---|---|
| MUST CHANGE | `models.py` (+`FeeReminderSetting`, `FeeReminderLog`, payments `(status, due_date)` index); new migration `0240_fee_reminders`; new `services/fee_reminders.py` (settings, sweep); `services/fee_accounts.py` (+`installments` on each account, additive); `notifications/events.py` (+2 events); `worker.py` (`itc016-fee-reminders` beat); `api/fee_accounts.py` (+settings router) + `main.py`; FE `FeeAccountSummary.tsx` (installments + badge + history), `ItStudentProfilePage.tsx` (staff fee card), new `FeeReminderSettingsPanel.tsx`, `WorkflowPanel.tsx` (mount on IT Admin Payments) |
| MAY CHANGE | `lib/` URL constant for the settings endpoint |
| SHOULD NOT CHANGE | `Payment.status` values (no stored `overdue`); `student_access`; `accounts.py` dashboard's derived late; `record_payment`; `/payments/mine`; EMI endpoints; the itc-002 `notify` contract |
| HIGH REGRESSION RISK | fee-account response consumers (itc-013/018 tests pin exact dicts — the new key is additive, tests that compare whole dicts must be checked); the event catalogue test (preview-safe text); the single alembic head (sibling itc-027 holds `0237`) |

Existing behaviour: nothing sets `status="overdue"`; installments are IT `enrollment_fee` `Payment` rows (an EMI installment is also a
`Payment` row with `installment_no`); no reminder job or history exists.

## Decisions (Claude's calls under "proceed with recommended answers", `NEEDS_CONFIRMATION`)

- **F1 overdue is derived** — an owed fee row (`pending`/`overdue`) with `due_date` before today's IST date is overdue; nothing is
  stored, so `student_access`, the accounts dashboard and `record_payment` are untouched (backlog recommendation, no drift).
- **F2 installments** — the rows of the itc-013 fee account (IT, `enrollment_fee`/`enrollment`, billing statuses, `amount > 0`). An
  EMI installment counts when it bills the enrolment the same way; other IT payment types are out of scope.
- **F3 schedule (Q-16)** — one settings row: `days_before` (0–30, 0 = off, default 3) and `overdue_days` (up to 6 distinct values 1–90,
  empty = off, default 1, 7, 14). A rule fires on the IST calendar day it names (due − N, or due + N); a missed day is not caught up
  (no flood after an outage or on deploy). Holidays are ordinary days (no holiday calendar exists — `NEEDS_CONFIRMATION`).
- **F4 recipients and channels** — the student gets `it.fee.payment_due` (before) or `it.fee.payment_overdue` (overdue); on an overdue
  rule the itc-003 linked counselor gets `it.fee.student_overdue`. Channels are itc-002's: in-app + email always, WhatsApp/SMS only when
  opted in. Fixed, amount-free text (source §7).
- **F5 idempotency** — `fee_reminder_log` UNIQUE `(payment_id, kind, offset_days, reminder_date)`; each reminder's log row and its
  notices share one savepoint, so a failure sends nothing and a second run (or a concurrent one) hits the unique index and sends
  nothing twice (AC1). A deactivated student is skipped (no log row).
- **F6 job** — Celery beat `itc016-fee-reminders`, daily 03:00 UTC (08:30 IST); one bounded query over the target due dates, served by
  `ix_payments_status_due_date`.
- **F7 history** — every fee account (`GET /it/enrollments/{id}/fee-account`, `GET /it/student/fee-accounts`) gains `installments`:
  `{id, installment_no, amount, due_date, status, overdue, reminders: [{kind, offset_days, sent_on}]}` (additive). Readers are itc-013's:
  the student (own), the IT counselor (linked), a `payments.view` holder in IT ("accounts", Q-17 open → itc-017).
- **F8 settings API** — `GET/PUT /admin/it/fee-reminder-settings`, IT Admin only (403 others), 422 on bad values, PUT audited
  before/after (itc-001 `audit_change`).

## Acceptance criteria (testable)

1. AC1 exactly one reminder per (installment, rule, day): a rerun the same day logs and notifies nothing new.
2. AC2 paid installments get none; an installment due in 3 days produces one student reminder (+ email delivery queued).
3. AC3 overdue on day 1/7/14 reminds the student and notifies the linked counselor; other days nothing.
4. AC4 a student without a WhatsApp opt-in gets no WhatsApp delivery; with it, they do.
5. AC5 notices carry no amount (catalogue test + body check).
6. AC6 settings: defaults without a row; PUT changes the schedule (0 / [] switch rules off); IT Admin only; 422 bad values; audited.
7. AC7 the fee account lists installments with `overdue` derived and the reminder history; visible to the student, the linked
   counselor and the IT Admin; not to another student (404, unchanged).
8. AC8 FE: the student's fee summary shows each installment with a Paid / Overdue / Due badge and reminders sent; the IT student record
   (admin, counselor) shows the same fee card; the IT Admin Payments page edits the schedule.

## Plan (TDD, small tasks)

1. RED `tests/test_itc_016_migration.py`, `tests/test_itc_016_fee_reminders.py` → migration `0240_fee_reminders` + models.
2. Events, `services/fee_reminders.py` sweep + settings → GREEN AC1–AC6; worker task + beat.
3. `fee_accounts.accounts` installments + history → AC7; settings router.
4. FE (vitest RED/GREEN): `FeeAccountCard` installments, `FeeReminderSettingsPanel`, staff fee card on the record page.
5. Playwright e2e; docs: DEC-SCOPE-358, API §12JD, RBAC §2.258, backlog status, RTM; graphify update.

## Phase 3 review notes

- **API:** additive response field; settings PUT is idempotent (full replacement), validation in Pydantic (list de-duplicated and
  sorted); no new list endpoint (itc-017 owns the overdue list) so no pagination contract.
- **Security:** settings are admin-only; history rides the existing itc-013 read gate (IDOR stays 404); notices are fixed text; logs carry
  ids and counts only; no new public route; no new secret.
- **Frontend:** reuse `FeeAccountCard`; badges use the existing `status`/`badge` classes; loading/empty/error states on the new panel;
  labels and `aria-describedby` on inputs; the list wraps on mobile.
- **Concurrency:** unique index + savepoint per reminder; settings row locked on save (last write wins).
