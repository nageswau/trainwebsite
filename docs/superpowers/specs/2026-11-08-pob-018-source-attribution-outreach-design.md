# pob-018 — Source attribution, verification and outreach permission (design)

- **Feature:** `pob-018` (`docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md`), decision `DEC-SCOPE-427`.
- **Source:** backlog §8.1 channel rules (LinkedIn URL + source date + outreach status; portal imports through approved tools;
  referrals/vendors recorded); "All candidate records must retain source attribution, consent/permission status where required and a
  date last verified"; §17 LinkedIn/portal terms. Source classified `UNVERIFIED`; every call below is the builder's (`NEEDS_CONFIRMATION`).
- **Dependencies:** hrc-010 (built), pob-010 (vendors = `companies.partner_type IN ('vendor','vendor_client')`, built), pob-014
  (`candidates.institution_org_id`, built).

## Intent

A placement officer must be able to say, for any candidate: where they came from and when, who referred them or which vendor supplied
them, when the details were last checked, how far outreach has got, and — before the profile goes to a client — how and when the person
agreed to be represented. No scraping or automated LinkedIn/portal integration (Q-13): everything is entered by hand or from a licensed
export reference.

## Acceptance criteria

1. **AC1** Every candidate has a source and a source date (new candidates default to today IST; existing ones are backfilled to their
   `created_at` date in IST; the column is NOT NULL).
2. **AC2** "Verify details" sets `last_verified_on` (today, IST) and who verified.
3. **AC3** Without an outreach permission, the candidate cannot be submitted: a profile share (the only submission today; pob-021 will
   reuse the same rule) is 422 naming the candidates who lack one.

## Calls (A1–A12)

- **A1 Catalogue:** the migration seeds `Vendor`, `Website`, `Community`, `Institution` into `rec_candidate_sources` when missing
  (case-insensitive). `Website` is the exact name hrc-023 already creates on first use, so the backlog's "Website registration" stays
  one entry, not two.
- **A2 Source date:** `candidates.source_date date NOT NULL`, python default today (IST) and `server_default CURRENT_DATE` for raw
  inserts. Create and PATCH accept it; a future date is 422.
- **A3 Attribution (all optional):** `referrer_name` (≤ 160), `referrer_candidate_id` (a pool candidate the caller can see, not the
  candidate itself; 422 otherwise), `vendor_id` (a non-archived vendor company in the caller's company scope; 422 otherwise — one
  message, so no existence oracle), `portal_import_reference` (≤ 120, the licensed export/import reference). `institution_org_id`
  stays pob-014's (shown, never edited here). All FKs `ON DELETE RESTRICT`.
- **A4 Outreach status:** `outreach_status` ∈ `not_contacted` (default), `contacted`, `responded`, `consented`, `declined`;
  `outreach_status_changed_at`. A manual move, any direction; the same status with the same permission is a no-op (no audit).
- **A5 Outreach permission:** `outreach_permission_method` ∈ `call`, `email`, `whatsapp`, `linkedin`, `in_person`, `form`, `other`;
  `outreach_permission_on` (date, not in the future); `outreach_permission_note` (≤ 500); `outreach_permission_by_user_id`. CHECK:
  status `consented` ⇔ method, date and recorder are all set. Moving to `consented` needs the method and date (422). Leaving
  `consented` withdraws the permission (fields cleared; the audit row keeps the old record).
- **A6 Verify:** `last_verified_on` + `last_verified_by_user_id`. Archived 409. Audit `candidate.verify`.
- **A7 Permitted (AC3):** a candidate is permitted when `outreach_status = 'consented'`, **or** they opted in themselves
  (`opted_in`: student opt-in, candidate portal, website consent — hrc-035 records each), **or** they are an institution student
  (pob-014's permission with the `placement` purpose already governs their sharing). Applied in `profile_sharing._candidates` under the
  existing FOR SHARE lock, so a concurrent withdrawal waits for the share's commit.
- **A8 Roles:** unchanged — candidate writers (`placement_team`, `placement_manager`, `super_admin`) change; readers (+ `hr_team`)
  see. Institution students outside the caller's permission stay 404 (pob-014).
- **A9 Privacy:** the anonymiser (hrc-035 K3) clears `referrer_name`, `outreach_permission_note`, `portal_import_reference`.
- **A10 Output:** the list row adds `source_date`; the detail adds `sourcing {source_date, referrer_name, referrer{id, candidate_code,
  name}|null, vendor{id, name}|null, institution{id, name}|null, portal_import_reference, last_verified_on, last_verified_by,
  outreach_status, outreach_status_changed_at, permission{method, given_on, note, recorded_by}|null, permitted}`. A referrer the viewer
  can no longer see reads "Restricted record" with null id/code.
- **A11 Routes:** attribution via the existing `POST`/`PATCH /recruiter/candidates` (the audit diff, the stale guard and history come
  free); `PUT /recruiter/candidates/{id}/outreach` and `POST /recruiter/candidates/{id}/verify` return the candidate detail.
- **A12 UI:** a "Source and outreach" card on the candidate page (the Ownership card's pattern) shows all of it, moves the Source /
  Source detail rows out of Profile, and offers writers on an active candidate: Edit source details (date, referrer name, referrer
  candidate picker, vendor picker, portal reference), Verify details, Update outreach (status; method/date/note when consented).

## Non-goals

Search filters and result enrichment (pob-019); per-submission consent and the submission record (pob-021); vendor submissions (pob-011);
an import column for source date or permission; any LinkedIn/portal automation.

## Risks

Profile sharing now refuses staff-added candidates without a permission: existing share tests must record one first. Merge (hrc-014)
keeps the survivor's attribution as it is (follow-up if owners want field-by-field choice).
