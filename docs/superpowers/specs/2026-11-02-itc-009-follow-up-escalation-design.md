# itc-009 — Overdue follow-up escalation for the IT team (design + plan)

Source: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` §itc-009 (business requirement §9 "Alert the owner when a follow-up is overdue;
optionally escalate after a configurable period"; §3 step 3). Dependencies: itc-002 (`notifications/events.notify`, event
`it.followup.overdue`, migration 0221) and itc-004 (Nurture stage, `lead_pipeline.follow_up_overdue`) — both on main.
Decision: DEC-SCOPE-342. API §12IN. RBAC §2.243. Migration `0226_follow_up_escalation`.

The user asked for autonomous execution with recommended answers; every choice below marked **(our call)** is recorded in
DEC-SCOPE-342 as `NEEDS_CONFIRMATION` until a client confirms it.

## Behaviour

- **Setting.** `tel_settings.escalate_after_hours` — whole hours, `0..168`, one value per team (`it`, `overseas`). `0` = escalation off
  (AC3). Server default and migration value for both rows: **0** **(our call: opt-in, so deploying changes nothing until a manager
  turns it on; the backlog says "optionally escalate")**.
- **Who may set it.** Unchanged: the tel-020 rule — any `telecaller_manager` or `super_admin` (`require_manager`); everyone else 403.
- **API.** `GET /telecaller/settings` items gain `escalate_after_hours` (additive). `PUT /telecaller/settings/{team}` accepts it as an
  **optional** key: omitted keeps the stored value, so existing two-field clients keep working. The audit row's `from`/`to` carry all
  three fields.
- **Which follow-ups.** Open, not on a Nurture lead (itc-004 N5, via `follow_up_overdue`), `escalated_at IS NULL`, and overdue by at
  least the team's hours: `due_at <= now - hours`.
  - *Telecaller follow-up* (`TELECALLER_FOLLOW_UP`: not created by a counselor), lead of team T (`Enquiry.division`), lead has a
    telecaller → recipient = that telecaller's reporting manager (`telecaller_profiles.reporting_manager_user_id`) if active, else every
    active division admin of T (`it_admin` / `overseas_admin`) (backlog E: "manager deactivated → IT admin"; overseas analogue is
    **our call**). Threshold: team T's row.
  - *IT counselor follow-up* (created by a counselor) on an `it` lead → every active `it_admin` of division `it`. Threshold: the `it` row.
    Overseas counselor follow-ups are **not** touched: ccrm-031 already escalates them.
  - A lead with no telecaller and a telecaller follow-up has no owner to escalate about — skipped.
- **Once per follow-up (AC1).** `lead_follow_ups.escalated_at` is claimed with
  `UPDATE … SET escalated_at = now WHERE id = :id AND escalated_at IS NULL RETURNING id` inside a savepoint, and the notices are written
  in the same savepoint: two overlapping beat runs cannot both claim; a failed notify rolls the claim back. No recipient → not claimed
  (retried next run, counted `skipped`).
- **Completing stops it (AC2).** Only `status = 'open'` rows qualify. A completed/cancelled follow-up is never escalated.
- **Backlog flood guard (our call, mirrors tel-020 AL10).** Only follow-ups that crossed the threshold within the last 24 h
  (`due_at > now - hours - 24h`) are escalated, so turning the setting on never mass-notifies about months-old follow-ups.
- **Notice.** `notify(db, recipients, "it.followup.overdue", fu.id, action_url=…)` — fixed preview-safe catalogue text ("A follow-up is
  past its due time. Open EduSphere to act on it."): no phone, name, note (Security row). In-app + consented channels (itc-002).
  `action_url`: manager → `/telecaller/manager/leads/{lead_id}`; division admin → `None` (no admin lead page exists; a link that 403s
  is worse than none).
- **Beat.** New `itc009-escalations` task every 15 minutes (`900.0`), own session, logs counts and ids only.
- **Index.** The existing partial index `ix_lead_follow_ups_open_due (due_at) WHERE status='open'` bounds the sweep; no new index.

## Frontend

`TelecallerAlertSettingsPanel` (Telecaller manager → Alert settings) gains a third field per team card: "Escalate overdue follow-ups
after (hours)", `min=0 max=168`, hint "Notify the telecaller's manager (or the division admin) once when a follow-up is this overdue.
0 turns escalation off." Same form, same save, same loading/error/success states. Page intro text mentions escalation.

**Added during implementation (discovery gap):** neither the telecaller manager nor the IT admin had an in-app notifications list, so
the "alert appears in the recipient's alerts list" requirement had nowhere to land. Added, reusing existing patterns only:
`/telecaller/manager/notifications` (the bdm-010 manager page, with the unread badge) and an IT admin `notifications` portal section
(itc-002's header-only section + shared `SchoolNotificationList`). Both get a "Notifications" nav entry.

## Non-goals

No change to tel-020 alert kinds, ccrm-031, the notification centre, or follow-up create/complete flows. No new admin page.

## Review (Phase 3)

- **API:** additive response field; optional request field keeps backward compatibility; 0..168 StrictInt (422 readable sentence like
  the others); row lock already serialises saves. Transaction: per-follow-up savepoint, commit per chunk.
- **Security:** no new endpoint; authz unchanged (manager/super_admin); IDOR n/a; recipients resolved server-side; preview text fixed
  (no PII); logs ids/counts only; no new secrets.
- **Frontend:** reuses the existing card/field/hint pattern; `inputMode="numeric"`, labelled, hinted, keyboard-native.

## Plan (TDD)

1. Migration 0226 + model columns — test chain, columns, CHECK `0..168`, round trip (throwaway DB, itc-006 pattern).
2. Settings API — tests: GET includes field; PUT with field saves + audits; PUT without it keeps value; 169 / -1 / "2" → 422; 0 OK.
3. Service `services/follow_up_escalations.py` — tests: 25 h overdue with 24 h → manager once (rerun = no new notice); 0 → none;
   completed → none; nurture → none; inactive manager → IT admin; IT counselor follow-up → IT admins; overseas counselor → none;
   inside threshold → none; older than the guard → none.
4. Worker beat entry + task.
5. Frontend panel field + vitest; e2e spec on the alerts page.
6. Docs: DEC-SCOPE-342, API §12IN, RBAC §2.243, RTM, backlog status.
