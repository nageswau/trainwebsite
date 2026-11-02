# itc-007 — Merge duplicate leads (design)

**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` `itc-007` (PDF §9 "let authorized users merge duplicates", §3 step 1;
`UNVERIFIED` source, build approved in waves by the owner's Q-01 answer 2026-11-01). **Dependency:** itc-001 (merged, PR #408).
**Decision:** `DEC-SCOPE-338`. API §12IJ, RBAC §2.240, migration `0223_lead_merge`.

## Intent
Duplicates are blocked at intake (tel-005), but older rows, imports and edits still leave two leads for one person. Closing one as
`duplicate` (ccrm-006) keeps its calls, follow-ups and notes on the closed lead, where nobody works them. A merge moves the work to the
lead that stays, so the person has one history.

## Behaviour
- **Who:** a telecaller manager (their T23 scope) and super_admin on `/telecaller`; an IT/overseas admin (their division) and super_admin
  on `/admin`. A telecaller gets 403. *(Q-07, Claude's call: managers and admins only — `NEEDS_CONFIRMATION`.)*
- **Pick:** the survivor is the open lead's page; the manager enters the victim's Lead ID. `GET …/{id}/merge-preview?victim=LD-…`
  returns both leads' mergeable fields side by side and the counts that would move. `POST …/{id}/merge`
  `{victim, use_victim: [field…], reason?}` merges.
- **Refusals (all before any write):** victim not found in the caller's scope → 404; victim = survivor → 422 (`victim`); different
  division (team) → 409; either lead closed → 409; victim linked to a student, or at Application/Enrollment or Converted → 409
  (AC3); a bad `use_victim` field → 422.
- **Locks:** both leads `FOR UPDATE` in id order (two merges of crossing pairs can't deadlock); then the victim's open appointment.
- **Moves to the survivor** (`lead_id` update): calls, follow-ups, notes, messages, meetings, appointments, further enquiries
  (`lead_enquiries`), counselor tasks. The victim's own enquiry becomes a `lead_enquiries` row on the survivor (subject, message,
  source, campaign; metadata `{"merged_from": <code>}`) so it is not lost. Leads closed as a duplicate *of the victim* now point at the
  survivor (no duplicate chain).
- **Both have an open appointment** (one open appointment per lead, `uq_appointments_lead_open`): the survivor's stays; the victim's is
  cancelled ("Lead merged") with its history and audit row, then moved, so it still shows on the survivor's timeline.
- **Qualification fill-empty-only:** survivor fields that are empty take the victim's value (`lead_qualifications` row and the shared
  `enquiries` answers). If the survivor has no qualification row the victim's row moves. English tests move only if the survivor has none.
- **Field picker:** `name, email, phone, whatsapp_number, city, state, qualification, passing_year, institution`. Empty survivor
  values are filled from the victim; a field in `use_victim` takes the victim's value even when the survivor has one.
- **Not moved:** the victim's stage history and audit rows (they are the victim's record); the survivor's stage, priority, telecaller
  and counselor (Claude's call, `NEEDS_CONFIRMATION`: the manager picks the lead further along as survivor).
- **The victim:** closed as `duplicate` with `duplicate_of_id` = survivor, a stage-history row (event `merge`, reason
  "Merged into LD-…"), and `merged_at` / `merged_by_user_id` (migration). A merged lead is **read only**: no reopen, no stage move,
  no contact/qualification edit (409). Notes stay allowed (history, ccrm-002 N1).
- **Audit (AC4):** one `lead.merge` row on the survivor: `{victim_id, victim_code, moved: {calls, follow_ups, …}, use_victim,
  changes}` — `changes` is itc-001's `{field: [old, new]}` of the survivor's fields, PII fields as `"changed"`.
- **Timeline (AC1):** the survivor's timeline lists every moved activity (it reads by `lead_id`) plus a `merge` row "Merged from LD-…".
- **Logs:** ids and counts only.

## UI
- Manager lead page (`/telecaller/manager/leads/[id]`): a "Merge a duplicate" button on an open lead opens a form: Lead ID → "Compare"
  → a side-by-side table (this lead | the other lead | keep) with a radio per differing field, the counts to move, an optional reason
  and "Merge into this lead". Loading, error and success states; on success the page re-reads the lead and the timeline.
- A merged victim's page reads "Merged into LD-…" and shows no controls.
- Admin leads table: the same form in the row's action cell (`/admin/leads/{id}/merge…`).

## Non-goals
No undo/unmerge. No automatic duplicate detection. No merge across divisions. No change to intake duplicate blocking.

## Risks
Timeline/metrics/reports that count leads (the victim is closed `duplicate`, as ccrm-006 already counts it); the appointment unique
index; tests asserting exact `admin_out` keys (additive `merged_at` only).

## Plan (TDD, small steps)
1. Migration `0223_lead_merge` + model columns + CHECKs; migration test.
2. `services/lead_merge.py`: `preview`, `merge` (locks, refusals, moves, fill, close, audit). Tests per rule.
3. Routes: `/telecaller/leads/{id}/merge-preview|merge` and `/admin/leads/{id}/merge-preview|merge`. Route tests (RBAC, 404/409/422).
4. Read-only guard for merged leads (reopen, stage, PATCH, qualification, admin PATCH).
5. Timeline `merge` row (API + web label).
6. Web: `LeadMergeForm` + wiring on the manager detail page and the admin row; `merged_at` read-only display. Vitest tests.
7. Playwright e2e for the manager merge.
8. Docs: DEC-SCOPE-338, API §12IJ, RBAC §2.240, backlog status.
