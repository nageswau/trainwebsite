# itc-004 — Lead stages "Assigned to Counselor" and "Nurture" (design + plan)

Source: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` `itc-004` (PDF §3 lead status examples). Scope approved by the owner 2026-11-01
(backlog Q-01: all phases, built in waves). Q-04 is open; the builder default below is `NEEDS_CONFIRMATION`. Decision: `DEC-SCOPE-338`.
Dependencies: none.

## Intent

The PDF lists "Assigned to Counselor" and "Nurture" among the lead statuses. Telecallers need a place to park a lead that is not ready
now (Nurture) without it nagging them as overdue, and everyone needs to see at a glance that a lead is with a counselor.

## Decisions (builder defaults)

- **N1 — Assigned to Counselor is a derived badge (Q-04), not a stored stage.** Shown when the lead has a counselor (`counselor` /
  `owner_id`) and is open (not closed, not converted). It replaces the tel-018 "With counselor" note in the telecaller lead list and is added
  to the admin lead list's stage cell. A stored stage would re-key every from-set, the counselor's moves, the funnel and the telecaller
  metrics (which count by stage) across both IT and overseas — high regression for a display need. No API or DB change for N1.
- **N2 — `nurture` ("Nurture") is a stored open stage outside the linear pipeline `ORDER`.** It is in `STAGES` (so the status CHECK,
  filters and labels pick it up) but not in `ORDER`, so funnel ranks ("reached Qualified") and event chains never treat parking as
  progress. Migration `0223_lead_nurture_stage` widens `ck_enquiries_status`; downgrade moves Nurture leads to Follow-up first.
  Available to every team on the shared pipeline (IT and overseas) — one catalogue, no per-team gate.
- **N3 — who moves a lead to Nurture:** the telecaller, their manager and the admin (the `MANUAL` set), from any open stage before the
  student link; **a reason is required** (backlog "+" case). The counselor's list (ccrm-003 CC8) is unchanged.
- **N4 — re-activation:** a manual move out of Nurture to Qualified / Interested / Follow-up (existing rules), and the system events
  `appointment_booked`, `student_linked` and `returned` also accept a Nurture lead (it then moves on as from any early stage).
  Calls do not move a Nurture lead. A Nurture lead can be handed over (it is before the link). It is not offered the overseas one-step
  conversion (ccrm-008) until re-activated.
- **N5 — excluded from overdue:** a Nurture lead's open follow-ups are kept (not cancelled) and still get the "due soon" reminder, but are
  never overdue: not in the overdue list or its count (telecaller and counselor), not flagged `overdue`, not matched by My Leads'
  `follow_up=overdue` filter, not in the counselor performance overdue count or the follow-ups report's Overdue column, no tel-020
  "missed" alert; the lead's `next_action_overdue` is false; the counselor dashboard does not flag them overdue. One predicate
  (`lead_follow_ups.overdue`) carries the rule.
- **N6 — Nurture filter:** the existing stage filters (telecaller list, admin list, counselor list) accept `nurture` automatically.
- **N7 — history:** the move is written by `lead_pipeline._record` → `LeadStageHistory` (actor, time, reason) as every move.
- **N8 — the backlog "−" case (converted → Nurture = 409):** served as the endpoint's existing **422** "past the counselor handover" refusal
  that every past-link move returns, to keep one contract. `NEEDS_CONFIRMATION`.
- **N9 — (c) PDF display names for IT** (Contact Attempted, Connected, Course Interested, Unreachable) are **deferred to itc-005**, whose
  per-team configurable labels are exactly this (its "+" case renames Interested to Course Interested). Hard-coding them now would be
  replaced by itc-005. Not in itc-004's AC list.

## Acceptance criteria (testable)

1. Handover yields the agreed state: the stage is unchanged and the lead shows "Assigned to Counselor" (lists) — N1.
2. A Nurture lead's past-due follow-up is excluded from every overdue surface (N5); `?status=nurture` / `?stage=nurture` lists it (N6).
3. The move records actor, time and reason in the stage history (N7).
- + telecaller moves a lead to Nurture with a reason; without one → 422 at `reason`.
- − a converted (or linked) lead → Nurture → 422 (N8).
- E: a Nurture lead whose follow-up is due → the due reminder fires, never "missed"/overdue; a returned lead from Nurture → Follow-up.

## Plan (TDD, small steps)

1. **Catalogue** — `lead_stages.py`: `PARKED_STAGES`, `NURTURE`, `MANUAL += nurture`, `REASON_STAGES`, from-sets for the three events.
   Tests: catalogue counts, events from Nurture, migration-model match (move the "model matches" assertion from the ccrm-006 test,
   which pins 0186's frozen list, to the new migration test).
2. **Migration 0223** + test (chain, model match, downgrade turns Nurture into Follow-up).
3. **person_move / handover** — guard `ORDER.index` for Nurture; Nurture needs a reason. Tests: move with/without reason, from Nurture back,
   converted → 422, handover of a Nurture lead.
4. **Overdue exclusion** — `lead_follow_ups.overdue`, `_out` flag, `next_action_out`, tel-020 missed alert, counselor dashboard flag,
   follow-ups report. Tests per surface through the API.
5. **Frontend** — `leadStages.ts` (stage, manual target, reason, `assignedToCounselor`), telecaller and admin list badge. Vitest.
6. **E2E** — `itc-004-nurture.spec.ts`: telecaller moves a lead to Nurture with a reason, filters by Nurture, badge after handover;
   desktop + phone.
7. **Docs** — DEC-SCOPE-338, API §12IJ, RTM rows, backlog status.

## Regression risks

Shared pipeline (overseas telecaller, BDM leads, counselor flows), the tel-026 route matrix, the fixed-query-count tests (no new
queries are added: only predicates), the frontend stage-picker tests that enumerate targets (Nurture is a new manual target).
