# ccrm-033 — Reassignment with a logged reason (design + plan)

NO-ASSUMPTION MODE. Backlog item `ccrm-033` (`docs/delivery/COUNSELOR_CRM_BACKLOG.md`); spec §2 "administrators can reassign ownership
and correct records with a logged reason", §11 student reassigned. Dependencies: none. Branch `worktree-ccrm-033`.
Numbers: `DEC-SCOPE-268`, API §12FU, RBAC §2.182, **no migration**.

## 1. Owner answers (2026-10-25, clarifying-question prompt)

| ID | Question | Answer |
| --- | --- | --- |
| RR1 | When is the reason required? | **Only when an existing owner is replaced or removed.** Optional (still stored) on a first assignment to an unowned record. Same owner = no change, no reason needed. |
| RR2 | Agent view of an agency application's history | **Hidden from the agent.** The agent still sees the "EduSphere counsellor changed" row, without the reason. Staff views show it; the student never sees reasons (ccrm-016 H2). |
| RR3 | Lead owner (admin API only, no UI, no notices today) | **Reason + notices, no UI.** Reason required on the API; new and previous counselor notified with the reason; the lead timeline shows the change and the reason. No owner picker. |

## 2. Existing behaviour (verified on `origin/main` @ `1b703ac2`)

| Path | Route | Today |
| --- | --- | --- |
| Application counselor | `PUT /workflows/overseas/applications/{id}/counselor` (`api/workflows.py` `assign_overseas_counselor`) | overseas_admin only; swap only; `ApplicationStatusHistory` row (notes "EduSphere counsellor assigned/changed"); audit `overseas.application.counselor_assign` {from, to}; new + previous counselor notified; agency notice. |
| Student counselor (csc-005) | `PUT /admin/users/{id}/counselor` (`services/counselor_students.py` `assign_counselor`) | overseas_admin only; audit `overseas.student.counselor_assign` {from, to}; new + previous notified; student 360 History lists the audit row ("Counselor assigned"). |
| Lead owner (ccrm-003 A7) | `PATCH /admin/leads/{id}` `owner_id` (`api/admin.py` `update_lead`) | ensure_admin; active counselor of the lead's division or null; audit `lead.update` {status, owner_id}; **no notices; not on the lead timeline**. |

Body today: `OverseasApplicationCounselorAssign {counselor_id}` (shared by the first two). The lead PATCH body is a dict whose `reason` is
already the **stage-move** reason (tel-004).

## 3. Design

**Body.** `OverseasApplicationCounselorAssign` gains `reason: BdmPipelineNote = None` (trimmed, ≤ 500, newlines normalised, control
characters refused, blank → None). The lead PATCH gains `owner_reason` (same type, validated through a `TypeAdapter`), a separate key so
a combined stage move + owner change keeps both reasons. Backward compatible for first assignments; a replace/remove without a reason is
now a 422 (the intended contract change).

**Rule (RR1).** A reason is required when the record has an owner and the request changes it (to another counselor, or — leads only —
to null). Message: `REASON_REQUIRED = "Give a reason for the reassignment"`. Checked after the existing 403/404/409/422 checks and the
same-owner no-op, so a no-op never needs a reason.

**Storage.**
- Application: the history row's existing `reason` column (ccrm-016) + `reason` in the audit metadata.
- Student: `reason` in the audit metadata (the student has no status history; the student 360 History reads this audit row).
- Lead: a dedicated audit row `lead.owner_change` {from_owner_id, owner_id, reason}; the existing `lead.update` row is unchanged (its
  consumers and tests keep their shape). `lead.handover` is **not** reused — `management_counseling` counts it as a telecaller handover.

**Display ("shown in History").**
- Application: counselor/admin status-history views already render `reason` for staff; student view already strips it (H2). Agent
  detail (`agent_applications.detail`, agent-only) strips the reason on the two counsellor rows (RR2): `status_history(..., agency=True)`.
- Student 360 History: the `overseas.student.counselor_assign` item carries `reason` from metadata (the UI already renders `reason`).
- Lead timeline: a new branch over `lead.owner_change` with kind `handover` (from/to names, reason) — the web client already renders
  "Counselor changed from A to B" + the reason detail; the unassign case (no `to`) gets the title "Counselor removed (was A)".

**Notices.** The reason is appended to both counselor notices ("… Reason: <text>") on the application and student paths. Lead path (RR3):
new owner "Lead assigned to you" (`/{division}/counselor/leads/{id}`), previous owner (if active) "Lead reassigned" (`/{division}/counselor/leads`).
The agency notice (`agency_notices.counselor_assigned`) is unchanged — no reason to the agent (RR2).

**UI.** `AssignCounselorButton` gains a "Reason" textarea (max 500). Required (`required` + label "Reason (required)") when `currentId`
is set; optional on a first assignment. Sent as `reason`. Server re-checks (the client rule is only a convenience).

**Transactions / concurrency.** Unchanged: every path already locks the record (application row FOR UPDATE, student row FOR UPDATE, lead
via `locked_for_admin`) before reading the current owner, so the "had an owner?" decision is made under the lock. Notices are queued in
the same transaction (sent after commit).

**Alternatives rejected.** A `reason` column on each owner table (migration, no gain over audit/history); reusing `lead.handover` (skews
counselling metrics); a generic "reassignment" service (three callers with different locks/scopes — premature).

## 4. Phase 3 review notes

- **API:** additive optional field; 422 only on replace-without-reason; HTTP semantics unchanged (PUT idempotent: same owner is
  `changed: false`). Field-shaped 422 for the lead (`owner_reason`), plain detail for the PUTs (as their other 422s).
- **Security:** RBAC unchanged (overseas_admin for the PUTs; ensure_admin + division for the lead). Reason text is stored and shown only
  to staff; never in structured logs (`logger.info` extra fields stay ids); never to the student (H2) or the agent (RR2). XSS: React
  escapes text; notification bodies are plain text. Control characters refused by the validator. Length capped at 500.
- **Frontend:** reuse the existing form, error/status regions and focus handling; textarea is labelled, `maxLength=500`, keyboard
  reachable; Escape/Cancel unchanged; Save disabled while busy (no duplicate submission).

## 5. Plan (TDD, focused tests)

1. Schema: `reason` on the assign body; `REASON_REQUIRED`. Tests: blank → None, > 500 → 422, control chars → 422.
2. Application path: replace without reason 422 (nothing changed); with reason → history `reason`, audit `reason`, both notices carry
   it; first assign without reason OK; agent detail hides the reason; counselor `/status` shows it.
3. Student path: replace without reason 422; with reason → audit `reason`, notices, student 360 History item `reason`.
4. Lead path: replace/remove without `owner_reason` 422; first assign OK; `lead.owner_change` row; notices; timeline row with reason.
5. Web: `AssignCounselorButton` reason field (required when replacing, sent in body); `leadTimeline` unassign title.
6. Update existing tests that swap without a reason (AGN-023, csc-005, ccrm-003) to send one — contract change, not a behaviour fudge.
7. Docs: DEC-SCOPE-268, API §12FU, RBAC §2.182, backlog status.
