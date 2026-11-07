# pob-004 — BD pipeline stages, client status and loss/inactive reasons (design)

- **Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-004 (§3.1 Status; §4 pipeline; "Record reasons when a prospect is lost
  or inactive"). Source classified `UNVERIFIED`; Q-00 (owner, 2026-11-01) approved the backlog for build in waves. The owner assigned pob-004
  on 2026-11-06 and said to proceed with recommended answers, so D1–D11 and the Q-04 answer are **the builder's calls
  (`NEEDS_CONFIRMATION`)**. Dependency pob-005 (the HR-contact event) is merged (#477). Decision `DEC-SCOPE-417`.

## Intent
A Placement Officer needs the company pipeline to read as the BD journey: from a target, through research and finding the HR contact, to
outreach, a meeting, vendor registration, the first requirement, and a client relationship. A lost or dormant prospect must carry a reason
that can be counted, and dormant companies must stop inflating "active" figures.

**Non-goals:** vendor registrations (pob-010, which can fire the same event); LinkedIn/visit activities (pob-007); reminder cadence (pob-008);
targets and reports (pob-009). **Anti-goals:** losing rec-005's requirement-driven moves; rewriting an existing company's stage; a company with
live work going inactive by itself.

## Rules (builder's calls)

**D1 — Three new stored stages, four display labels.** The ladder, in order (new ones marked +; keys of existing stages never change):
`new_lead` "Target Identified" → + `research_completed` → + `hr_contact_identified` → `contacted` "Outreach Sent" → `interested` →
`meeting_scheduled` "Meeting Booked" → `requirement_discussion` → + `vendor_registration` "Vendor Registration / Agreement" →
`requirement_received` → … → `requirement_closed` (unchanged). "Interested" and the requirement-side stages are not in §4's list but stay:
removing them would break rec-005 and every report on them. The three new stages are `manual` kind, so a person can also choose them.

**D2 — Active Client and Repeat Business are a client status, not ladder stages (Q-04).** The backlog lists them as stages, but it sets
`active_client` on the first requirement, while the driven stages only move forward: on the ladder, either it would sit after them and stop
JD/Sourcing/Interview/Joined ever firing, or before them and be overwritten at once (the board's "Active Client" would then count almost
nobody). So `companies.client_status` (`prospect` default, `active_client`, `repeat_business`; CHECK) is stored beside the stage. It only moves
forward, is written only by `company_pipeline`, and adds a stage-history row (`event` = the status, `from_stage` = `to_stage`, Lost's shape).

**D3 — Inactive is a flag beside the stage, as Lost is.** `inactive_at`, `inactive_reason_id`, `inactive_reason` (CHECK: at and reason both or
neither). The stage is kept, so reopening returns it to where it was. The board shows Active Client, Repeat Business, Inactive and Follow-up Due
as filter tiles beside the stages.

**D4 — Automatic moves** (each fires once: forward-only from-sets; a Lost, inactive or archived company never moves):
- `hr_contact_added` → `hr_contact_identified`, from `new_lead`/`research_completed`, when an **active contact has a role** (add, or an edit that
  sets one). The contact-role catalogue is the HR-contact list by origin (its seeds are HR Manager, HR Head, Talent Acquisition, Recruiter, Hiring
  Manager), so any role counts; matching names would break on a manager's own wording.
- `call_logged` now fires from every stage before `contacted`, so the new stages cannot strand a company.
- `contract_registration` → `vendor_registration`, from any earlier stage, when the **client-side** contract (pob-010 V8: a vendor agreement never counts) reaches `contract_sent`, `signed` or `active`. The
  contract has no "registration" status: `contract_sent` is the closest (pob-010 can add a trigger later).
- `active_client`: the first requirement reaching Requirement Received, or a contract reaching `signed`/`active`.
- `repeat_business`: a requirement reaching Requirement Received when **another** requirement of the company has a joined offer.

**D5 — Reason catalogues.** Two rec-002 managed lists, `rec_company_lost_reasons` and `rec_company_inactive_reasons`, so the existing manager
catalogue screen and API (`/recruiter/catalogue/lost-reasons`, `inactive-reasons`) serve them with no new routes. Seeded; a manager can add,
rename or deactivate.

**D6 — Lost needs a catalogue reason (AC2).** `POST .../lost` becomes `{reason_id, note?}` — the explicit contract change this item asks for (a
free-text `reason` is 422). An unknown, deactivated or other-list id is 422 on `reason_id`. `lost_reason` stays the display text, now a snapshot
("Name" or "Name: note", note ≤ 300), so `pipeline.lost.reason` keeps its shape, a later rename does not rewrite history and pre-upgrade free-text
reasons stay valid (`lost_reason_id` NULL). Check order stays 404 → 403 → 409 → 422.

**D7 — Marking inactive.** `POST .../inactive` `{reason_id, note?}`, same rules and same holders as Lost (`can_edit`). A Lost company cannot be
marked inactive, or the reverse (409 `company_lost` / `company_inactive`).

**D8 — Auto-inactive after 6 months (Q-04).** Daily beat task. Candidate: not archived/Lost/inactive, and for 6 months (`INACTIVE_AFTER_DAYS` =
182): not created, no stage change, no call/message/completed meeting (`last_contacted_at`), no requirement touched. Never when it has a live
requirement, an open follow-up, a meeting since the cutoff, or a signed/active unexpired contract. `inactive_reason` = "No activity for 6 months",
`reason_id` NULL, history actor NULL, audit row with no user. Batches of 500, `SKIP LOCKED`, so it is idempotent and safe to rerun.

**D9 — Reopen.** `POST .../reopen` clears either flag, manager or super_admin only with a typed reason, as today for Lost. Automatic moves that a
flag suppressed are not replayed.

**D10 — Inactive is out of active counts (AC3).** The board's stage tiles and default list; rec-032's open-company figures; rec-035 MG4/MG5;
management partner-company count and the RC9 pipeline (with `inactive` listed beside `lost`). Pre-outreach stages count as today's `new_lead`:
rec-032 D1/D2 use `new_lead`, `research_completed`, `hr_contact_identified`, and MG4 "past New Lead" means past those. RC9 groups:
Lead + research/HR, Meeting + vendor registration.

**D11 — Follow-up Due stays derived.** `follow_up_due` (an open follow-up due now or earlier) on the pipeline card and board rows as a badge, and a
board filter tile. Never stored.

## Migration `0303_company_bd_stages`
Guarded throughout (0001 builds from today's models). Creates and seeds the two lists; adds `client_status`, `lost_reason_id`, `inactive_at`,
`inactive_reason_id`, `inactive_reason`; replaces `ck_companies_stage` with the wider frozen list; adds the new CHECKs. **Backfill of
`client_status` only**, since current clients must not read as prospects: `active_client` where a requirement ever reached Requirement Received or
a contract is signed/active; `repeat_business` where a requirement reached Requirement Received at or after a joining on another requirement.
No stage or history row is rewritten. `downgrade()` refuses while a company sits at a new stage or is inactive.

## API
`POST /recruiter/companies/{id}/lost` (changed); `POST /recruiter/companies/{id}/inactive` (new). `GET /recruiter/pipeline?stage=` also takes
`inactive`, `active_client`, `repeat_business`, `follow_up_due`; response gains `buckets`, items gain `inactive`, `client_status`,
`client_status_label`, `follow_up_due`; `lost_count` stays. Company rows gain `inactive`, `client_status`, `client_status_label`; `pipeline` gains
`inactive`, `client_status`, `client_status_label`, `follow_up_due`. Management recruitment gains `inactive`. AuthZ unchanged: company scope (404),
`can_edit` (403), manager for reopen. Audits carry ids and keys, never reason text.

## Frontend
`RecruiterCompanyPipeline`: client-status and follow-up badges, Inactive banner, Mark lost / Mark inactive forms with a reason picker (loaded when
opened; loading, failed and empty states) and optional note; Reopen unchanged. `RecruiterPipelineBoard`: tiles from `buckets`, Inactive/client
badges. `RecruiterCompaniesPanel`: Inactive badge. `RecruiterStageHistory` and `recruiterTimeline`: wording for the new events. Catalogue: two new
tabs. Management: "Inactive: n".

## Acceptance criteria
1. AC1: each automatic move fires once (a repeated event adds no history row).
2. AC2: Lost requires a catalogue reason.
3. AC3: inactive companies are excluded from active counts.
4. E: only a manager or super_admin reopens an inactive company.
5. Labels match the spec; the catalogue is extended without moving an existing company.

## Regression risks
rec-005 tests and board; rec-007/017/019/020/022/023 driven moves; rec-032/035 and mgmt-008/025 counts; rec-027 timeline wording; rec-038 matrix
(the new route and `/lost` body); rec-002 catalogue kinds; label assertions in e2e specs.
