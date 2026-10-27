# nehn-015 — Internal CRM delta matrix (readiness template)

**Status (2026-10-27): template only — waiting for the client CRM workflow document (CI-01).**
Evidence class of everything below: as-built code on `main` at `64161f18` (verifiable) and `MEETING_TRANSCRIPT_REQUEST` for the item
list. Nothing here is an `EXPLICIT_APPROVAL`, and no stage, source, distribution or permission is changed by this document.

## Why this exists

nehn-015's acceptance criteria (`CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md`, nehn-015) are:

1. A delta matrix exists, with every client-flow line mapped to built / changed / new.
2. The owner approves the delta.
3. Build items are created with their own DECs.

AC1 needs the client's document. This file prepares the "as built" half now, so that when CI-01 arrives the work is filling in the
**Client flow** and **Delta** columns, not re-surveying the code. Until then every client column is `NEEDS_CONFIRMATION`.

## How to complete it when CI-01 arrives

1. Store the client document under `docs/sources/` (immutable evidence) and add it to the source manifest.
2. For each row, copy the client's wording (with page/line) into **Client flow**.
3. Set **Delta** to `BUILT` (as built already matches), `CHANGED` (built, but the client differs) or `NEW` (not built).
4. A client line that contradicts a confirmed tel-* / ccrm-* decision is marked `CONFLICT` and raised to the owner — never silently
   overridden (backlog edge case).
5. Add rows for client lines that fit no row below.
6. After owner sign-off (AC2), each `CHANGED` / `NEW` / `CONFLICT` row becomes a build item with its own DEC (AC3).

## Matrix

Source lines: §16 L424–L448 (what the client flow should define) and §26 L760–L783 (client inputs), from the review transcript mapped in
the consolidated backlog. "As built" cites the code and the decision that governs it.

| # | Item (§16 / §26) | As built today | Governing decision | Key code / tests | Client flow | Delta |
|---|---|---|---|---|---|---|
| 1 | Lead sources (L424 / L760) | Fixed list of 13 sources (instagram, facebook, google, website, whatsapp, walk_in, college, school, agent, referral, exhibition_event, bdm, other); not manager-editable. Campaigns and products are manager-maintained. | DEC-SCOPE-074 (tel-002) | `apps/api/app/tel_sources.py`; `test_tel_002_*` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 2 | Lead creation process (L425) | Five intake paths, all through `lead_intake`: public website enquiry (`POST /public/enquiries`), telecaller/manager manual lead, CSV import (tel-006), overseas counselor walk-in (csc-004), BDM lead. Each is distributed on intake. | DEC-SCOPE-088 (tel-005), DEC-SCOPE-229 (csc-004), DEC-SCOPE-087 | `services/lead_intake.py`, `api/telecaller_import.py`, `api/counselor_walk_in_leads.py`, `api/bdm_leads.py`; `test_tel_005_*`, `test_tel_006_import.py`, `test_csc_004_walk_in_leads.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 3 | Lead stages (L426 / L761) | 11 ordered open stages (New Lead → Converted) and 6 closed outcomes (Not Interested, Not Eligible, Invalid Contact, No Response, Lost, Duplicate). *The backlog's "16 stages" predates ccrm-006's Duplicate.* | DEC-SCOPE-081 (tel-004), DEC-SCOPE-264 (ccrm-006) | `apps/api/app/lead_stages.py`; `test_tel_004_*`, `test_ccrm_006_*` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 4 | Stage transitions (L427 / L762) | System events move leads (assigned, call connected/unconnected, appointment booked/completed/released, student linked/unlinked, returned, converted). Telecaller may set Qualified / Interested / Follow-up and closed outcomes; counselor a narrower set; manager reopens closed leads to Follow-up. Manual moves stop at Application/Enrollment. | DEC-SCOPE-081, DEC-SCOPE-243 (ccrm-003) | `lead_stages.EVENTS`, `MANUAL`, `COUNSELOR_MANUAL`; `services/lead_pipeline.py`; `test_tel_004_pipeline.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 5 | Counselor roles / workflow (L428 / L763) | `counselor` role works handed-over leads: notes, follow-ups, its own stage moves, return to telecaller, convert to student. | DEC-SCOPE-101 (tel-018), DEC-SCOPE-243, DEC-SCOPE-252 (ccrm-008) | `services/lead_handover.py`, `services/lead_conversion.py`; `test_tel_018_*`, `test_ccrm_003_*`, `test_ccrm_008_convert.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 6 | Counselor assignment process / rules (L429 / L764) | Manual only: the lead's telecaller or their manager hands the lead to a chosen active counselor. Admin can change the counselor owner with a reason. No automatic counselor allocation. | DEC-SCOPE-101, DEC-SCOPE-271 (ccrm-033) | `lead_handover.handover`, `lead_handover.reassign_owner`; `test_tel_018_handover.py`, `test_ccrm_033_reassignment_reason.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 7 | Telecaller assignment (§16 L385–L395, "possible approaches") | Automatic on intake: team product rule → team city rule → round robin among active telecallers → unassigned queue. Manager manual / bulk (re)assignment to direct reports. **Not built: workload-based and source-based allocation** (rule `kind` is CHECK-limited to `product`, `city`). | DEC-SCOPE-087 (tel-007) | `services/lead_distribution.py`; `TelDistributionRule` (`models.py`, `ck_tel_distribution_rules_kind`); `test_tel_007_*` | NEEDS_CONFIRMATION | Candidate NEW (workload, source) |
| 8 | Follow-up workflow (L430 / L766) | Follow-ups per lead with reason and due time; complete / cancel / edit; a follow-up queue; Follow-up Due and Missed Follow-up alerts. | tel-0xx follow-ups, DEC-SCOPE-111 (alerts) | `api/telecaller_follow_ups.py`, `services/lead_follow_ups.py`; `test_tel_020_alerts.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 9 | Lead ownership (L431 / L765) | Two owners: `telecaller_user_id` (the telecaller) and `owner_id` (the counselor after handover). Telecaller loses edit rights once handed over. | DEC-SCOPE-077 (tel-003), DEC-SCOPE-084 (tel-008), DEC-SCOPE-101 | `Enquiry` (`models.py`); `test_tel_008_workspace.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 10 | Reassignment rules / process (L432 / L767) | Manager reassigns to direct reports; telecaller deactivation hands open work over; team move; manager deactivation; admin counselor change requires a reason (both counselors notified). | DEC-SCOPE-087, tel-025, DEC-SCOPE-271 | `api/telecaller_distribution.py` (`/leads/assign`), `api/telecaller_lifecycle.py`; `test_tel_007_assign.py`, `test_tel_025_*` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 11 | Escalation requirements (L433 / L768) | Threshold alerts (Lead Not Contacted, Hot Lead Pending; per-team hours, editable by managers) go **to the lead's telecaller only**. Counselor overdue work escalates once to every active Overseas Admin. **Not built: an escalation chain to the manager, or SLA-driven automatic reassignment.** | DEC-SCOPE-111 (tel-020), DEC-SCOPE-272 (ccrm-031) | `services/telecaller_alerts.py` (`_not_contacted`, `_hot_pending`), `services/counselor_reminders.py` (`overdue_escalation`); `test_tel_020_*`, `test_ccrm_031_escalation.py` | NEEDS_CONFIRMATION | Candidate NEW (chain / SLA) |
| 12 | Communication tracking (L434 / L769) | Call log (type, outcome, duration, remarks), templated messages per lead, notes, one merged lead timeline (calls, messages, follow-ups, appointments, stage history). | DEC-SCOPE-114 (tel-015 timeline); nehn-014 → ccrm-002 notes | `api/telecaller_calls.py`, `api/telecaller_messages.py`, `services/lead_timeline.py`, `services/lead_notes.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 13 | Conversion criteria (L435 / L770) | Converted is computed: Application/Enrollment (student linked) → Converted when the linked student has an active IT enrolment or an enrolled overseas application (HO3); a sweep and observers keep it in sync. | DEC-SCOPE-101 (T19/T20) | `lead_handover.sync_conversion`, `sweep_conversions`; `test_tel_018_link.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 14 | Lost / rejected lead handling (L436 / L771) | Lost and Not Interested need a reason from the manager-maintained lost-reason list (plus optional "lost to"); Lost Reasons report; manager reopen. | DEC-SCOPE-264 (ccrm-006) | `lead_stages.LOSS_STAGES`, `api/telecaller_catalogue.py` (`/lost-reasons`); `test_ccrm_006_loss_capture.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 15 | Duplicate-lead handling (L437 / L772) | One person = normalised mobile OR lower-cased email, matched across all leads (closed included), serialised by advisory locks; duplicate check before manual create; a repeat website/import enquiry attaches to the existing lead; a lead can be closed as Duplicate of a surviving lead. | DEC-SCOPE-088, DEC-SCOPE-264 | `services/lead_intake.py`; `Enquiry.duplicate_of_id`; `test_tel_005_intake.py`, `test_ccrm_006_*` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 16 | Student conversion process (L438 / L776) | Counselor links an existing student or converts in one step (creates the overseas student account, prefilled, and links it). Only an admin unlinks a converted lead. | DEC-SCOPE-101, DEC-SCOPE-252 | `lead_handover.link_student`, `services/lead_conversion.py`; `test_ccrm_008_convert.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 17 | Agent-related lead flow (L439 / L775) | `agent` exists only as a lead **source** value. Agent-portal students (`AgentStudent`) are a separate record with no link to CRM leads (`enquiries`). **Not built: an agent ↔ CRM lead link.** | — (scope: CLAUDE.md "Agent Portal" undecided) | `models.AgentStudent`; `tel_sources.py` | NEEDS_CONFIRMATION | Candidate NEW / CONFLICT check |
| 18 | Overseas Education lead flow (L440 / L774) | Team `overseas`: same pipeline; handover to overseas counselors; conversion to overseas student. | DEC-SCOPE-073 (tel-001) | `services/telecaller.py` (`TEAMS`) | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 19 | IT Training lead flow (L441 / L773) | Team `it`: same pipeline and stages as overseas. | DEC-SCOPE-073 | `services/telecaller.py` (`TEAMS`) | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 20 | Required notifications (L442 / L779) | Nine telecaller alerts (in-app + email): assigned, appointment completed, returned, follow-up due, missed follow-up, appointment tomorrow, appointment in 1 hour, not contacted, hot pending. Counselor reminder rules (configurable). | DEC-SCOPE-111, DEC-SCOPE-272 | `services/telecaller_alerts.py`, `services/counselor_reminders.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 21 | Required dashboards (L443 / L777) | Telecaller dashboard + activity; manager performance (with CSV/xlsx); counselor dashboard. | tel-021, ccrm-0xx | `api/telecaller_dashboard.py`, `api/counselor_dashboard.py`; `test_tel_021_*` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 22 | Required CRM reports (L444 / L778) | Telecaller reports: source, course, telecaller, handover, campaign, lost reasons, counselor, date-wise, follow-up status, pending follow-ups (JSON/CSV/xlsx). Management CRM reports (ccrm-034). nehn-013 definitions are builder defaults pending CI-01. | tel-024, DEC-SCOPE-267, DEC-SCOPE-301 (nehn-013) | `services/telecaller_reports.py` (`REPORTS`), `services/management_crm_reports.py`; `test_tel_024_reports.py`, `test_nehn_013_crm_reports.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 23 | Required filters (L445 / L780) | Lead lists filter by stage, priority, created range (India time), counselor; admin lead filters. | DEC-SCOPE-298 (nehn-012) | `services/lead_list.py`, `lead_handover.list_filters`; `test_nehn_012_lead_list.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 24 | Required export fields (L446 / L781) | Fixed-column lead Excel (admin / manager column set; per-role columns of nehn-008 not built); CRM exports for leads and applications; report CSV/xlsx. | DEC-SCOPE-298 | `api/telecaller.py` (`/leads.xlsx`), `api/crm_exports.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 25 | Required / role-based permissions (L447 / L782) | Role scopes are fixed (`telecaller:self`, `telecaller:team`, counselor, admins). In the nehn-005 permission engine the only CRM resource is `reports.telecaller` (view / download). | DEC-SCOPE-281 (nehn-005), DEC-SCOPE-299 (nehn-007) | `app/core/rbac.py` (`CATALOGUE`), `services/permissions.py`; `test_nehn_005_permissions.py` | NEEDS_CONFIRMATION | NEEDS_CONFIRMATION |
| 26 | Approval workflow (L448 / L783) | **None.** Lead reassignment, reopen and counselor change are role-gated actions with audit rows, not approval requests. | — | — | NEEDS_CONFIRMATION | Candidate NEW (if the client requires one) |

## Known candidate deltas (from the code, before CI-01)

These are gaps against the transcript's "possible approaches"; none is approved, and the backlog forbids building them before the client
flow is reconciled.

| Candidate | Rows | Likely impact if confirmed |
|---|---|---|
| Workload-based telecaller allocation | 7 | New rule kind or mode; open-lead count per telecaller at assign time (indexed); migration on `ck_tel_distribution_rules_kind` |
| Source-based telecaller allocation | 7 | New rule kind `source` keyed on `tel_sources`; migration on the kind CHECK and a unique index |
| Escalation chain / SLA reassignment | 11 | Manager-level alert and/or automatic reassignment on threshold; settings per team |
| Agent ↔ CRM lead link | 17 | Scope decision first (Agent Portal current/future is undecided); then a link between `AgentStudent` and `enquiries` |
| Approval workflow | 26 | Only if the client flow requires one |

## Open questions for the client (carried from the backlog)

- When will the CRM workflow document (CI-01) be provided?
- Should agent-portal leads merge into `enquiries`?
- Is the optional `crm_webhook_url` (Zoho-era webhook) still wanted alongside the internal CRM? (`NEEDS_CONFIRMATION`)
