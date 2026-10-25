# ccrm-031 — Overdue escalation to the Overseas Admin (design)

- **Feature:** `ccrm-031` (docs/delivery/COUNSELOR_CRM_BACKLOG.md). **Decision:** `DEC-SCOPE-271`. **Migration:** `0190_overdue_escalation`.
  **API:** §12FX. **RBAC:** §2.185.
- **Source:** Counselor CRM Specification (UNVERIFIED) §11 "Task overdue → escalate to team lead", §14 escalation; owner answer CC3
  (no teams — the Overseas Admin is the escalation point).
- **Dependencies (merged):** ccrm-029 (counselor tasks, bands), ccrm-030 (reminder rule catalogue, log, daily job, admin page), ccrm-003
  (counselor follow-ups via tel-011).
- **Owner instruction:** proceed with recommended answers. Every E-n below is the builder's call, `NEEDS_CONFIRMATION`.

## Intent

A counselor's overdue tasks and follow-ups are visible only to that counselor. The backlog asks that work overdue past a configurable
threshold reaches the Overseas Admin once, and that the admin can see who is behind ("Overdue by counselor").

## Decisions

- **E1 — one more reminder rule.** `overdue_escalation` joins the ccrm-030 catalogue: action `notify`, timing `escalate` ("days overdue
  before the Overseas Admin is told"), default **2 days**, range 0–30, no student column. The admin switches it and sets the threshold on
  the existing Reminder rules page; the daily 08:15 IST job and "Run now" run it.
- **E2 — what is overdue.** (a) an open counselor task (any source) whose `due_on` is more than *threshold* days before today (IST), and
  (b) an open lead follow-up on an overseas lead owned by an overseas counselor whose due day (IST) is more than *threshold* days before
  today. Threshold 0 = overdue since yesterday. No 30-day lookback (unlike RM2): an item overdue for months still needs the admin, and
  E5 keeps the first run to one notice per counselor.
- **E3 — once.** Each item claims a `counselor_reminder_log` row with `dedupe_key = overdue_escalation:<item id>:<task|follow_up>-<due day>`
  (ccrm-030 RM3). A re-run or "Run now" never repeats; a changed due date that becomes overdue again escalates again.
- **E4 — recipients.** Every active `overseas_admin` (not Super Admin, CC3). No active Overseas Admin → the items are skipped (counted,
  not logged, so they escalate once an admin exists). The counselor is not told (they already see the Overdue band).
- **E5 — one notice per counselor per run.** The newly escalated items are grouped by counselor: one notification per admin per counselor,
  title "Overdue work escalated", body "<counselor name>: N tasks and M follow-ups overdue by more than D days.", link
  `/overseas/admin/counselor-tasks#overdue`. The counselor's name is staff data shown to staff; no task titles, notes or lead names
  (RM7 otherwise holds). In-app + email + opted-in channels through `queue_deliveries`. One savepoint per counselor group; a failure is
  counted and logged with ids only.
- **E6 — inactive counselors included.** Tasks or follow-ups of a deactivated counselor still escalate and are listed, marked inactive —
  the admin is the one who must reassign them.
- **E7 — the list.** `GET /counselor/tasks/overdue-by-counselor` (overseas_admin, super_admin; counselor 403): one row per counselor with
  at least one overdue item — `overdue_tasks` (band overdue), `overdue_follow_ups` (open, past due time), `past_threshold` (items of E2),
  `oldest_due` (date), `active` — ordered by past_threshold desc, total desc, name. Also returns `threshold_days`, `enabled`, `today`.
  Computed live; two grouped queries, no N+1.
- **E8 — the page.** An "Overdue by counselor" section (id `overdue`) at the top of `/overseas/admin/counselor-tasks`, a table with a
  "View tasks" link to `?counselor=<id>&band=overdue`, an empty state ("No counselor has overdue work.") and the threshold sentence with
  a link to Reminder rules.

## Out of scope

Escalating to Super Admin or management, escalation of anything other than tasks and follow-ups (leads without a next action → ccrm-032),
repeated escalation of the same item, an admin follow-up list, counselor-facing changes.

## Data

No new table. Migration `0190_overdue_escalation`: re-creates `ck_counselor_reminder_rules_key` with the 11 keys (drop-if-exists, so a
fresh database built by 0001 from the models passes too) and seeds `('overdue_escalation', 2, false)` ON CONFLICT DO NOTHING. Downgrade
deletes the row and the rule's log rows, then restores the 10-key CHECK.

## API (§12FX)

- `GET /overseas-admin/reminder-rules` lists the new rule (timing `escalate`); `PUT .../overdue_escalation` takes 0–30;
  `notify_student: true` → 422. Run counts include `rules.overdue_escalation` (items escalated).
- `GET /counselor/tasks/overdue-by-counselor` → `{today, threshold_days, enabled, items: [{counselor: {id, full_name}, active,
  overdue_tasks, overdue_follow_ups, past_threshold, oldest_due}]}`. 403 for anyone but overseas_admin / super_admin.

## Tests

Backend (`test_ccrm_031_escalation.py`): a task and a follow-up past the threshold notify every active Overseas Admin once in one grouped
notice; a re-run sends nothing; inside the threshold nothing; done/cancelled tasks never; a changed due date escalates again; disabled
rule sends nothing; threshold edits apply; no admin → skipped; the list counts and orders correctly and is 403 for a counselor.
Migration test for 0190 (chain, CHECK, seed, round trip); the ccrm-030 migration test now pins 0189's frozen 10 keys.
Frontend: vitest for the overdue section and the `escalate` unit; Playwright: admin sees the section, follows "View tasks", sees the rule.

## Plan

1. Backend RED: escalation + list tests; migration test. 2. GREEN: catalogue/model keys, migration 0190, `_overdue_escalation`,
`overdue_by_counselor`, route. 3. Frontend RED/GREEN: `lib` type + unit, `OverdueByCounselor` component, page section. 4. e2e spec.
5. Docs: decision register, API contract §12FX, RBAC §2.185, RTM, backlog status.
