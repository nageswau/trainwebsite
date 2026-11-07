# pob-006 — Company and contact import, and authorised merge (DEC-SCOPE-418)

**Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-006 (`UNVERIFIED` draft; Q-00 approved the backlog for build in waves).
**Depends on (merged):** hrc-013 (import pattern), hrc-014 (merge pattern), pob-005 (contact status, duplicates).
**Builder's calls** below are marked (B): recommended defaults taken without owner confirmation; the owner can reverse them.

## Goal

A Team Lead or authorised Placement Officer loads a spreadsheet of companies and their contacts without creating duplicates, and folds a
duplicate company (or a duplicate contact within a company) into the record that stays, with nothing orphaned and everything audited.

**Non-goals:** moving a contact between companies (pob-005 Q-05); a duplicate-review queue for companies; a bulk reassign of imported
companies; updating existing records from a file; un-merge; a shared engine rewrite of hrc-013 (the helpers are reused, its routes are left alone).

## Grants (G)

- G1 New catalogue resource `crm` with actions `import`, `merge`. Default holder: `placement_manager` (Team Lead, Q-01). An "authorised PO" is a
  `placement_team` user given a per-user allow override. `super_admin` always holds them. (B)
- G2 Both are additive to the role gate: `placement_team`, `placement_manager`, `super_admin` only. A grant never lets another role in (hrc-013 I1).
- G3 The grant does not widen company scope: every company still resolves through `caller_scope`.

## Import (I)

- I1 One file: one row = a company + optionally one of its contacts. Several rows may name one company. Only `company_name` is required. (B)
- I2 Columns: `company_name website linkedin_url industry company_size employee_count city state country head_office description lead_source
  priority contact_name contact_designation contact_department contact_role contact_mobile contact_email contact_linkedin contact_channel
  contact_source contact_verified_on contact_decision_maker contact_notes`. Unknown or missing columns are a 422 before any row. CSV/XLSX through
  `read_tabular`; 1 MB and 1,000 rows, as hrc-013.
- I3 Each row is validated by `RecCompanyCreate` / `RecContactIn`: an import accepts what the forms accept. Catalogue columns match an active value by
  name, case-insensitively; an unknown value is a row error.
- I4 Company match: the normalised name key (`name_key`), archived included, through to the survivor if merged. A match is never changed.
- I5 Contact match, within the matched company only: same normalised mobile or lower-cased email; with neither, the same name key. A merged-away contact
  matches its survivor, so a re-import cannot resurrect it. The same person at another company is created and the row notes it (pob-005 D8 warns, never refuses).
- I6 Writing to a matched company: the `crm.import` grant may add a contact to any non-archived company in the caller's scope, including a manager on a
  team's company (the manual route is recruiter-only). (B) Out of scope or archived + a contact in the row = a row error, nothing written. Without a
  contact it is `matched`. An out-of-scope match shows the code and name only (what `check_name` already discloses), no link.
- I7 New company owner: the recruiter's own; a manager's or super_admin's goes to the unassigned queue (`create_company`'s rule, no target chosen). (B)
- I8 `POST /preview` writes nothing. `POST ""` needs `Idempotency-Key`; takes the advisory lock; a repeated key or the same file by the same user replays
  the stored report; a key reused for another file is 422. Each row runs in a savepoint in one transaction. (B: "chunked" in the backlog is met by the 1,000-row cap
  and the batched lookup; AC1 is timed in a test.) A row's 409 from `contacts.add` (the 50-contact cap) is that row's error.
- I9 Tables `crm_import_batches`, `crm_import_rows`: hash, file name, counts, ids and reasons. No cell values are stored; names come from the linked records.
- I10 History: own batches; a manager also their team's; super_admin all. Other batches are 404. A report never names a contact of an out-of-scope company.
- I11 `report.csv` escapes every text cell (`_safe_cell`).

## Company merge (M)

- M1 `GET/POST /recruiter/companies/{survivor}/merge`. Both companies must be in the caller's scope (404 otherwise), locked in id order, rules re-checked once locked.
- M2 Refused: self (422); survivor archived; victim archived or already merged; victim an employer's account (`owner_type = employer`, `employer_user_id` or an
  `EmployerProfile`): the other direction is offered, both = refused (409).
- M3 Q-06: both have a current contract in effect (effective status `signed`/`active`) = 409 naming both. (B per backlog "block") If both have a current contract and only
  one is in effect, that one stays current; neither in effect, the survivor's stays. The other is kept as a previous contract.
- M4 Moves by `company_id`: contacts (primary cleared when the survivor has one), jobs, follow-ups, calls, messages, meetings, contracts, documents, profile shares, drives,
  stage history, assignment history. Branch rows move only if the survivor has none (no mix of guesses, hrc-010 P12); skill demand moves where the survivor lacks that skill.
- M5 Fields: `use_victim` picks from `website linkedin_url industry_id company_size_id employee_count city state country head_office description lead_source_id priority
  products_services`; an empty survivor field is filled. Silently filled when empty: `branches`, the three context lists, `assigned_bdm_user_id`, and `campaign_id` travels
  with `lead_source_id`. Assignee: filled through `record_assignment` when the survivor has none. Name and stage stay the survivor's.
- M6 Victim: archived, `merged_into_id/at/by` set, keeps its name (name is unique) and code. It cannot be restored or edited. Detail shows "Merged into CMP-x".
- M7 Audit: `recruiter_company.merge` on the survivor (moved counts, chosen fields, changes), `recruiter_company.merged_into` on the victim (survivor, reason). Then
  `refresh_last_contact` on the survivor.
- M8 `/workflows/it/jobs` finding a merged company by name uses its survivor.

## Contact merge (C)

- C1 `GET/POST /recruiter/contacts/{survivor}/merge`: both in one company, locked by the company, `can_edit` not required but `crm.merge` + scope. Self 422; merged 409; company archived 409.
- C2 Moves by `contact_id`: follow-ups, calls, messages, meetings, shares, job decision-maker, job descriptions, interviews; meeting participants move unless the survivor already attends (then the row is removed).
- C3 Fields as M5 from `name designation department role_id mobile email linkedin_url preferred_channel notes source verified_on`.
- C4 Safety rules: Do Not Contact is contagious (a victim's DNC moves the survivor to DNC, cause `merge`, D6 stays enforced). `is_decision_maker` is OR-ed. A primary victim makes the survivor primary.
- C5 Victim: inactive, not primary, `merged_into_id/at/by`. Hidden from the contact list and duplicate warnings, refused by edits (404). The per-contact timeline of the survivor also shows the victim's status changes.
- C6 Audit: `recruiter_company.contact_merge` on the company (ids, counts, fields, reason).

## Data

Migration `0297_crm_import_merge` (guarded, 0001 builds from the models): `companies` and `company_contacts` get `merged_into_id` (self FK RESTRICT), `merged_at`,
`merged_by_user_id`, with a not-self CHECK; the two import tables; seed `placement_manager` `crm.import`, `crm.merge`. Downgrade drops them and the grant rows. No existing data changes.

## API

```
GET  /recruiter/company-imports/template
POST /recruiter/company-imports/preview           multipart file
POST /recruiter/company-imports                   multipart file + Idempotency-Key -> 201 report
GET  /recruiter/company-imports                   history
GET  /recruiter/company-imports/{id}              report
GET  /recruiter/company-imports/{id}/report.csv
GET  /recruiter/companies/{id}/merge?victim=CMP-x preview
POST /recruiter/companies/{id}/merge              {victim_code, use_victim[], reason?}
GET  /recruiter/contacts/{id}/merge?victim=<id>   preview
POST /recruiter/contacts/{id}/merge               {victim_id, use_victim[], reason?}
```

Existing contract: `RecCompanyOut` gains optional `merged_into`; contact lists omit merged rows. Nothing else changes.

## UI

`/recruiter/companies/import` wizard (hrc-013's four steps, without source/basis) with history; an "Import" link on the company list for `crm.import`. `/recruiter/companies/[id]/merge`:
enter the duplicate's code, then the side-by-side comparison (hrc-014's screen). A "Merge a duplicate" link on the company detail, and per contact in the Contacts section, for `crm.merge`.
`/recruiter/companies/[id]/contacts/[contactId]/merge` compares two contacts. Merged company detail: a banner, no actions.

## Risks

Metrics joins follow `company_id` and archived filters (rows move, so a survivor's totals are the sum). rec-038 route coverage and the hrc-002/nehn-005 catalogue tests need the new rows.
The victim's recruiter loses sight of moved requirements: the preview says so when assignees differ.

## Plan

1. Migration + models + rbac + schema (RED: migration, grant tests). 2. `company_import` service + routes (RED: AC1, AC2, per-row errors, scope, replay, CSV guard). 3. `company_merge` service + routes (RED: AC3 sweep over every FK, Q-06, employer, concurrency-safe locks). 4. Contact merge. 5. Web: libs, wizard, merge screens, links + vitest. 6. e2e + browser QA. 7. Docs, rec-038 rows.
