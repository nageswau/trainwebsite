# pob-027 — Intake automations and an escalation framework (design)

- **Date:** 2026-11-08. **Feature:** `pob-027` (backlog `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md`).
- **Evidence:** the `UNVERIFIED` Placement Officer & BD CRM requirements draft, §16 rows "New requirement received", "Requirement
  assigned to recruiter" and "Feedback overdue → escalation rules". No approval record: every call below is the builder's
  (`NEEDS_CONFIRMATION`); the owner asked for the recommended answers instead of questions.
- **Dependencies (built):** itc-002 (notification events, DEC-SCOPE-336), hrc-016 (tasks pattern, DEC-SCOPE-387), hrc-012/hrc-006
  (requirement owners), pob-022 (Team Lead automation panel, DEC-SCOPE-421), pob-008 (follow-up reminders, DEC-SCOPE-423).
- **Numbering:** DEC-SCOPE-434, migration `0315_intake_automation` (after `0314_vendor_bills`), API §12MA, RBAC §2.325.

## Intent

A requirement that arrives should never sit without an owner who knows about it, the owner should start with the standard sourcing and
screening work in front of them, and work that stalls should reach the Team Lead without someone having to look for it.

## Acceptance criteria (backlog)

1. A new requirement has an owner and a notification within the same request (or, with no eligible owner, it is in the Team Lead queue
   and the Team Leads are notified in that request).
2. Assignment creates the configured tasks once.
3. Escalations fire per rule (once per rule and item).

## Calls (I1–I12)

- **I1 Owner rule (Q-18 → "company owner by default").** Every create path (recruiter route, employer portal, legacy staff route) goes
  through `record_created`. A requirement created without an owner takes the company's assigned recruiter. An owner is *eligible* when it is
  an active `placement_team` user; otherwise the requirement is left unassigned (the existing "Unassigned" filter is the Team Lead queue).
  The hrc-024-style distributor is not built (`NEEDS_CONFIRMATION`).
- **I2 Notifications (same transaction).** An owner gets `it.requirement.assigned` (existing event; not when they created it themselves).
  No eligible owner: every active `placement_manager` gets the new `it.requirement.unowned`. The assign route (primary change) now also
  notifies the new primary.
- **I3 Task template.** One `requirement_automation_settings` row (id 1): `task_template`, a list of 0–10 items
  `{kind: sourcing|screening, title (1–200), due_in_hours (1–720)}`. Seeded with "Prepare the sourcing plan" (sourcing, 24 h) and
  "Screen the first shortlisted profiles" (screening, 72 h). Read and written by `placement_manager` / super_admin only
  (pob-001: the Team Lead), audited `requirement_automation.settings`.
- **I4 Requirement tasks.** A new `requirement_tasks` table (job, kind, title, due, assignee, open/done/cancelled). Not rec-024 follow-ups
  (company-scoped, no assignee: a reassigned owner who does not own the company would not see them) and not hrc-016 candidate tasks
  (a candidate is required).
- **I5 Once.** When a requirement first gets a primary owner (create or assign) and has no tasks, the template is copied (due = now +
  hours, assignee = owner). It runs under the job row (new row or `FOR UPDATE`), so it is once. A reassignment moves the open tasks to the
  new primary; nothing is copied again.
- **I6 Task API.** `GET /recruiter/requirements/{id}/tasks` (requirement readers, the rec-007 scope incl. officers) and
  `POST /recruiter/requirements/{id}/tasks/{task_id}/complete` (the assignee or a requirement writer with `can_edit`; 409 when not open;
  audited `requirement_task.complete`).
- **I7 Escalation rules.** `escalation_rules` {event_type, after_hours 1–720, notify `reporting_manager|all_team_leads`, active}; at most
  20. Event types: `requirement_unowned` (no primary N hours after creation, open statuses only), `requirement_task_overdue` (an open
  task N hours past due), `follow_up_overdue` (an open rec-024 follow-up N hours past due; the pob-008 area). No delete: a rule is switched
  off. API: `GET/POST /recruiter/escalation-rules`, `PATCH /recruiter/escalation-rules/{id}`; audited `escalation_rule.*`.
- **I8 Evaluator.** Beat `pob027-escalations` every 15 minutes. Per active rule, up to 200 items whose threshold (due/created + N h) has
  passed *and* is not earlier than the rule's creation (no backlog flood), with no `escalation_events` row for (rule, item). The row is
  inserted with `ON CONFLICT DO NOTHING` (unique (rule_id, entity_id)) and the notice `it.recruiter.escalated` sent only when inserted —
  once, also under concurrent runs. Recipients: `reporting_manager` = the item owner's reporting manager when an active Team Lead, else
  every active one (pob-022's rule); `all_team_leads`; `requirement_unowned` has no owner, so every active Team Lead.
- **I9 pob-022 unchanged.** The interview feedback escalation keeps its own settings (DEC-SCOPE-421 A6); moving it onto the rules is a
  follow-up (`NEEDS_CONFIRMATION`). pob-025 is not built; it can add an event type later.
- **I10 UI.** A Team Lead page `/recruiter/automation` ("Intake automation": the task template and the escalation rules; Team Lead and
  super_admin only) linked from their navs; a "Tasks" section on the requirement page with "Mark done".
- **I11 Migration.** `0315_intake_automation`: four new tables, settings row seeded; additive; downgrade drops them.
- **I12 Privacy.** Logs and audit carry ids, kinds and counts only.

## Non-goals

Round-robin distribution; per-user settings; task editing/creation by hand; escalation by email-only channels beyond the standard
notification fan-out; changing pob-008/pob-022 behaviour.

## Regression risks

rec-007/037 (requirement create/assign), hrc-006 (owners history), employer job posting, the legacy staff create route: a manager- or
employer-created requirement now gets the company's recruiter as owner.
