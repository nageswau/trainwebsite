# ccrm-014 — Application sub-status (CC1) — design

Backlog: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` `ccrm-014`. Decision: `DEC-SCOPE-240` (amends `DEC-WF-001` by adding a detail
level under the 7 stages; the stages themselves do not change). Owner answers SS1–SS4, 2026-10-22.

## Requirement

Each overseas application carries a `sub_status` from a fixed list keyed to its stage (CC1). Sub-status moves freely inside a stage;
picking a sub-status of a later stage advances the stage (forward-only rule unchanged). History records old/new stage and sub-status
and who changed it (spec AC 6). A change on one application never touches another (AC 9).

## Owner answers

| ID | Answer |
| --- | --- |
| SS1 | Mapping = the backlog list (below). `enquiry` and `eligibility_evaluation` have no sub-statuses. |
| SS2 | Backfill only where certain: `enrolled` → Enrolled; `offer` with `offer_type` → Conditional/Unconditional Offer; `university_selection` with `submitted_on` → Submitted; else not set. |
| SS3 | A stage change through any other route clears a sub-status that does not belong to the new stage; reaching `enrolled` sets Enrolled. Automatic offer/visa sub-statuses stay with ccrm-023/026. |
| SS4 | Counselor on their applications (direct and agency; on agency applications Enrolled stays with the agency Master, DEC-SCOPE-054); agent on agency applications up to `status_tracking` (A4); Overseas Admin on any; student read-only. |

## Mapping (SS1)

| Stage | Sub-statuses (code → label) |
| --- | --- |
| `university_selection` | `application_created` Application created · `documents_pending` Documents pending · `ready_for_submission` Ready for submission · `submitted` Submitted · `under_review` Under review |
| `offer` | `conditional_offer` Conditional offer · `unconditional_offer` Unconditional offer · `offer_accepted` Offer accepted |
| `visa_documentation` | `visa_preparation` Visa preparation · `visa_applied` Visa applied |
| `status_tracking` | `visa_decision_pending` Visa decision pending · `visa_approved` Visa approved |
| `enrolled` | `enrolled` Enrolled |

## Design

- **One definition:** `app/application_sub_status.py` (no model imports): `SUB_STATUSES`, `STAGE_OF`, `label()`, `fit(stage, sub)`.
  The web mirrors it in `lib/applicationSubStatus.ts` (the stage list is already mirrored the same way).
- **SS3 in one place:** `OverseasApplication.@validates("status")` calls `fit()` — every existing stage write (counselor advance, PATCH,
  agent status, offer, enrolment, seed) keeps the sub-status consistent without touching those routes.
- **Transition:** `services/application_sub_status.change(db, user, app, target, notes)` — validates the code (422), refuses an
  earlier stage (422), a same value is a no-op (no history, safe retry), sets stage then sub-status, writes one history row with
  `from/to_status` and `from/to_sub_status`. Callers own scope, locks, caps, notices and the commit (the services pattern).
- **Routes:**
  - `POST /workflows/overseas/applications/{id}/sub-status` — counselor (own, `_assigned_application`) and Overseas Admin.
    Row lock + counselor recheck as `/advance`; withdrawn → 409; counselor on an agency application to Enrolled → 403
    (`MASTER_ENROLLS`); archived agency record → 409. Stage change → AGT-003 commission trigger + AGN-017 agency notice; student
    notified; agency told of a sub-status-only change (CC5).
  - `POST /workflows/overseas/agent/crm/applications/{id}/sub-status` — agency gate + scoped lock + `_refuse_closed`; Enrolled → 403
    (A4). Returns the agency detail. The EduSphere counselor is notified (CC5).
- **Reads:** `sub_status` (+ label) on the overseas application list, `/status` history, portal application tables (counselor, admin,
  student) and the agency list/detail/history.
- **DB (0167, after ccrm-011's 0166):** `overseas_applications.sub_status VARCHAR(40) NULL`; `application_status_history.from_sub_status/to_sub_status
  VARCHAR(40) NULL`; SS2 backfill. Additive; downgrade drops the columns.
- **Web:** counselor Evaluate Applications card gets a sub-status badge and an "Update sub-status" form (grouped by stage); agency
  detail gets a badge, a sub-status form and sub-status in history; tables show a Sub-status column.

## Alternatives rejected

- Free-text sub-status: no reporting, no forward rule.
- A separate sub-status table: one current value per application is enough; history already exists.
- Explicit clearing in every stage route: 6+ write sites, easy to miss one; the validator covers them all.

## Risks

Shared state machine (high): the validator only ever clears/sets `sub_status`, never `status`. Regression set: AGN-008 status,
AGN-010 offer, AGN-013 enrolment, OVS-003 advance, AGN-023 filters/portal columns, mgmt funnel, AGT-003 commission.
