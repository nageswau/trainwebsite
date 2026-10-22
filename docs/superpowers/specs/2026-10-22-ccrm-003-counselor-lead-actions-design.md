# ccrm-003 — Counselor lead actions: stage, next action, follow-ups (design + plan)

**Source:** `docs/delivery/COUNSELOR_CRM_BACKLOG.md` `ccrm-003` (supersedes nehn-014 part 2; owner CC1–CC10, CC8, 2026-10-22).
**Decision:** `DEC-SCOPE-243`. **API:** `API_CONTRACT.md` §12EV. **RBAC:** `RBAC_MATRIX.md` §2.158. **Migration:** `0169_lead_next_action`
(chained after ccrm-014's `0168_application_sub_status`; ccrm-014 / ccrm-010 hold 240–241 / 12ER–12ET / 2.154–2.156 in parallel sessions and
re-chain when they merge).

## Intent

A counselor works the leads handed to them: moves the stage within the CC8 allow-list, keeps a next action with a due date on every open
lead, and schedules / completes / cancels follow-ups. Telecallers keep read-only access to those leads (tel-008 D1 / T19) and their
metrics, lists and alerts are not touched by the counselor's work.

## Builder's calls (the owner pre-authorised recommended defaults for this session)

- **A1** Counselor stage targets (CC8): Follow-up, Counselling Scheduled, Counselling Completed, Qualified (open) and Not Interested,
  Not Eligible, Lost (closed, reason required). Wrong Number / No Response stay telecaller outcomes. Any other stage → 422 `STAGE_SYSTEM`
  (Application/Enrollment and Converted stay event-driven). As for the telecaller, manual open moves stop once the lead is at
  Application/Enrollment or later (`MANUAL_BEFORE`) → 422; a closed lead cannot be reopened by the counselor (403, as a telecaller —
  only a manager / admin reopens).
- **A2** "Next action required" applies to counselor-owned leads only (backlog default); telecaller leads are unchanged. Fields
  `enquiries.next_action` (trimmed text 1–200) and `enquiries.next_action_due` (date). The counselor stage move takes optional
  `next_action` / `next_action_due`; after applying them, a move to an open stage with either still missing → 422 on that field. A closing
  move needs neither (and keeps any stored value as it was). Existing counselor leads are not back-filled: the detail shows "No next action
  set" until the counselor sets one.
- **A3** `PUT /counselor/leads/{id}/next-action` sets both at once (both required) on an open lead (closed → 409). A changed due date
  must be today (IST) or later → 422; an unchanged one may already be past, so the text of an overdue action can still be edited.
- **A4** Follow-ups: the tel-011 service with a counselor writer. `GET|POST /counselor/leads/{id}/follow-ups`,
  `PATCH /counselor/follow-ups/{id}`, `POST /counselor/follow-ups/{id}/complete|cancel` — the same bodies, answers and rules (future due
  time, 12-month horizon, cap 20, closed lead 409, done / cancelled 409). Scope: `counselor_scope` (owner + division; anyone else 403,
  another counselor's lead 404). `move_to_follow_up` from a counselor goes through the counselor move, so the A2 rule applies (the web
  does not offer the checkbox to a counselor). `can_change` is true for the owning counselor on an open follow-up.
- **A5** A counselor's follow-up is never the telecaller's work: every telecaller-side follow-up query (day / overdue lists, My Leads
  "Due follow-up", tel-020 due / missed alerts, tel-021 dashboard counts, the tel-021/024 snapshot "follow-ups pending", tel-025 open-work
  counts) excludes follow-ups created by a counselor. The telecaller's per-lead list still shows them, read-only (D1).
- **A6** Returning a lead (T19) cancels its open follow-ups ("Returned to telecaller", as the appointment) and clears the next action, so a
  later handover starts clean. Handover already cancels open follow-ups (tel-018).
- **A7** Admin `PATCH /admin/leads/{id}` `owner_id`: a non-null value must be an active `counselor` of the lead's division → 422 on
  `owner_id` otherwise; `null` stays allowed (un-assign), as today. Two existing tests that set an admin as owner change to a counselor —
  the backlog changes that behaviour on purpose.
- **A8** Logs and audit carry ids, stage keys and field names — never the reason or the next-action text (backlog "reason text not
  logged"). The next-action update writes `AuditLog` `lead.next_action` with `{fields}`.

## Design

- **DB (0168):** `enquiries.next_action varchar(200) NULL`, `enquiries.next_action_due date NULL`, check
  `ck_enquiries_next_action_len` (`next_action IS NULL OR length(next_action) BETWEEN 1 AND 200`). Additive; downgrade drops them.
- **Stage engine:** `lead_stages.COUNSELOR_MANUAL = {follow_up, counselling_scheduled, counselling_completed, qualified}`,
  `COUNSELOR_CLOSED = {not_interested, not_eligible, lost}`. `lead_pipeline.person_move` gains `kind="counselor"` (allowed sets chosen by
  kind; the rest of the checks unchanged) and enforces A2 after the stage checks, before recording.
- **Follow-ups service:** `require_writer(user, lead)` replaces `require_telecaller` in `load_for_write` (telecaller as before; a
  counselor in `counselor_scope` passes); `create` takes the move kind; `can_change` adds the owning counselor; `TELECALLER_WORK`
  (creator is not a counselor) for A5.
- **Routes:** in `api/lead_handover.py`: `POST /counselor/leads/{id}/stage` (→ `LeadStageOut` + `next_action`, `next_action_due`),
  `PUT /counselor/leads/{id}/next-action`, the follow-up routes of A4. The counselor detail adds `next_action`, `next_action_due` and
  `permissions.stage` / `permissions.follow_up` (open lead).
- **Web:** `CounselorLeadDetail` gets a "Next action" section (shows / edits both; overdue badge), the stage control (reusing
  `LeadStageControl` with a counselor `move` and `targets`, plus the two next-action fields when the target is open and none is stored),
  and `LeadFollowUps` with counselor URLs. `lib/leadStages.counselorTargets` mirrors A1. `FollowUpForm` / `FollowUpItem` / `LeadFollowUps`
  take optional URL builders (default: the telecaller ones) and `offerMove`.

## Non-goals

Counselor dashboard follow-up tiles (ccrm-032), counselor alerts, activity logging (ccrm-004), loss reason lists (ccrm-006).

## Plan (TDD, focused tests)

1. Migration 0168 + model columns + migration test (round trip, length check).
2. Stage engine: counselor kind + A2 — API tests: allowed moves, disallowed 422, past-link 422, closed reopen 403, next-action 422 / ok,
   close cancels follow-ups + appointments, another counselor 404, telecaller 403 on the counselor route.
3. Next-action PUT — tests: set, validation, past date 422, closed 409, audit without text.
4. Counselor follow-ups — tests: create / list / reschedule / complete / cancel, another counselor 404, telecaller still read-only,
   `can_change`; A5 exclusions (telecaller day list, alerts, dashboard counts); A6 return cancels + clears.
5. Admin owner validation — tests: non-counselor 422, other division 422, inactive 422, counselor ok, null ok; update adm-002 / tel-004.
6. Web: lib targets test, `CounselorLeadDetail` tests (next action, stage control, follow-ups), then typecheck / lint / build.
7. Docs: DEC-SCOPE-243, API §12EV, RBAC §2.158, RTM row, backlog status.
