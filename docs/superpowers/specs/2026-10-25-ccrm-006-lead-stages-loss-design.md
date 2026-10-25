# ccrm-006 — Lead stage additions and structured loss capture (design)

Backlog: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` § ccrm-006 (source: Counselor CRM Specification §3, UNVERIFIED). Decision:
`DEC-SCOPE-263`. Migration `0185_lead_loss_capture`. API §12FP. RBAC §2.177. Dependency ccrm-003 MERGED (PR #305).

The owner's standing instruction is "proceed with recommended answers". Every D-item below is a **recommended default**
(`NEEDS_CONFIRMATION`), not an explicit approval.

## Intent

The spec asks for the alternative statuses *Duplicate* and *Invalid Contact* and for "lost reason and competitor/destination
preference". Today a lead closes with free text only, so nobody can count why leads are lost.

## Decisions (defaults)

| ID | Decision |
|----|----------|
| D1 | *Invalid Contact* is the existing `wrong_number` stage relabelled (display label only; the key, history and call outcome "Wrong Number" stay). |
| D2 | New closed stage `duplicate` ("Duplicate"). Telecaller, telecaller manager and admins may choose it (tel-004 `CLOSED`). The counselor's CC8 list is unchanged (no Duplicate). |
| D3 | Closing as Duplicate requires `duplicate_of`: the surviving lead's Lead ID (`LD-000123`, case-insensitive). It must be a lead of the same team (division), not the lead itself, and not itself a Duplicate (point at the survivor). Missing → 422 on `duplicate_of`; unknown / other team / self / duplicate → 422 with one sentence. Stored as `enquiries.duplicate_of_id`. |
| D4 | Closing as Lost or Not Interested through a person's stage move (telecaller, manager, admin, counselor) requires `lost_reason_id` — an **active** row of the reason list — plus optional `lost_to` (≤160 chars: competitor or chosen destination). Sending either for another target → 422. |
| D5 | With a structured reason (D3/D4) the free-text reason becomes optional; the history row keeps the text, or else the reason name / "Duplicate of LD-…". Other closed outcomes still need text (unchanged). |
| D6 | Call-logged closes (tel-010 outcomes Not Interested / Already Joined Elsewhere) are unchanged and store no reason code; reports show them as "No reason recorded". |
| D7 | Reopening (manager, to Follow-up) clears `duplicate_of_id`, `lost_reason_id` and `lost_to`; the history keeps what happened. |
| D8 | The reason list `lead_lost_reasons` follows the tel-002 catalogue pattern: telecaller_manager and super_admin create / rename / reorder / deactivate; catalogue readers (incl. counselor, division admins) read active rows. Never deleted. Seeded with six reasons. |
| D9 | tel-024 gains a **Lost Reasons** report: leads created in the range, in scope, currently Lost or Not Interested, grouped by reason (columns: Leads, Lost, Not Interested). |
| D10 | The management telecalling "lost" figure (mgmt TC9) excludes moves to Duplicate — a duplicate is data hygiene, not a loss. Every other `CLOSED` consumer treats Duplicate as closed. |

## Data

* `lead_lost_reasons`: id, name (1–120, unique case-insensitive), active, sort_order, timestamps.
* `enquiries`: `duplicate_of_id` (FK enquiries, RESTRICT), `lost_reason_id` (FK lead_lost_reasons, RESTRICT), `lost_to` (String 160).
* CHECKs: status list + `duplicate`; `duplicate_of_id <> id`; `(duplicate_of_id IS NOT NULL) = (status = 'duplicate')`;
  `lost_reason_id` / `lost_to` NULL unless status is `lost` or `not_interested`.
* Downgrade maps `duplicate` leads to `lost` before restoring the old status CHECK.

## API

* `POST /telecaller/leads/{id}/stage`, `POST /counselor/leads/{id}/stage`, `PATCH /admin/leads/{id}`: optional `duplicate_of`,
  `lost_reason_id`, `lost_to` (additive).
* Lead rows (admin, telecaller, counselor lists and details) gain `duplicate_of {id, lead_code}`, `lost_reason {id, name}`, `lost_to`.
* `GET/POST /telecaller/lost-reasons`, `PATCH /telecaller/lost-reasons/{id}`.
* `GET /telecaller/reports/lost` (+ `.csv`).

## UI

* The shared stage control (`LeadStageControl`) shows a Lead ID field for Duplicate and a reason picker + "Lost to" for Lost / Not
  Interested; the reason text label switches to optional for those.
* Lead detail shows "Duplicate of LD-…" / "Lost reason · Lost to" when set.
* Manager page `/telecaller/manager/lost-reasons` (nav "Lost reasons"), the products page layout.
* Reports page gains the "Lost Reasons" tab.

## Out of scope

Merging duplicate leads' data, automatic duplicate closing, counselor Duplicate, consent opt-out (ccrm-040).
