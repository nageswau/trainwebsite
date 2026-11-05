# pob-002 — Requirement versioning, hiring process and per-requirement commercials (design)

- **Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-002 (§7 "Revisions should be versioned rather than silently replacing
  the original details"; field groups "Hiring process", "Commercial terms", "Ownership: … backup owner and approval status", "vendor if
  applicable"; source classified `UNVERIFIED`). The owner assigned pob-002 for build on 2026-11-05 and said to proceed with the recommended
  answers, so R1–R12 below (including Q-02) are **the builder's calls (`NEEDS_CONFIRMATION`)**. Dependencies merged: hrc-004
  (`DEC-SCOPE-376`), hrc-005 (`DEC-SCOPE-381`), hrc-006 (`DEC-SCOPE-384`), pob-001 (`DEC-SCOPE-403`). Decision `DEC-SCOPE-405`.

## Intent
A job requirement's PATCH overwrites its columns. The hrc-004 audit keeps an old → new diff, but you cannot read the requirement as it
stood at revision *n*. Nor can it hold the client's interview rounds, screening steps, decision-maker, turnaround, payment trigger,
payment and replacement terms, or a backup owner. pob-002 adds all of these.

**Non-goals:**
- the vendor link (`vendor_id`), which waits for pob-010 (no vendor concept yet);
- hrc-007's approval status (already on the requirement);
- reverting to a revision;
- revisions from the employer and `/workflows/it/jobs` paths (they don't write these fields).

**Anti-goals:**
- a no-change save that still writes a revision;
- a snapshot that leaks commercials to someone without `commercials.client.view`;
- a changed PATCH contract for existing clients (every field stays optional and additive).

## Rules (builder's calls)

**R1 — Revisions table.** `job_revisions`:
- columns: `id`, `job_id` (FK RESTRICT), `revision` (≥1, unique per job), `snapshot` (JSON: every material field, references by name),
  `changed_fields` (JSON list), `reason` (≤500, nullable), `author_user_id` (nullable = the system), `created_at`;
- append-only, never updated;
- the current record stays in `jobs`.

**R2 — When a revision is written.**
- **Creating** a requirement through the recruiter API writes revision 1 ("Created").
- **A PATCH** that changes at least one material field writes exactly one revision, in the PATCH's transaction (`FOR UPDATE` on the job row
  already serialises numbering: `max(revision)+1`). The PATCH accepts an optional `revision_reason` (≤500).
- **A manager's fee override** (`PUT …/fee`) that changes the fee writes one revision too (the fee is in the snapshot).
- **No change** writes nothing.

**R3 — Older requirements.** A job created before pob-002 has no revisions. Its first material save first writes a **baseline** revision
1, holding the stored values before the edit (author null, reason "Recorded before revisions were kept"). The edit then becomes revision 2.
AC1's "exactly one" therefore holds for every save after the baseline.

**R4 — Material fields.**
- every `REC_REQUIREMENT_FIELDS` column, the required/preferred skills, the hiring-process fields (R6), the commercial fields (R7), the
  fee and the backup owner;
- references stored by display name, as hrc-004's `audited_values` does;
- not material (and not in the snapshot): status (it has its own history), owners/collaborators (hrc-006 history), visibility (hrc-008),
  weights, and `expected_updated_at` / `duplicate_reason`.

**R5 — Reading revisions.**
- `GET /recruiter/requirements/{id}/revisions?limit&offset` lists newest first: `revision`, `author`, `reason`, `created_at`,
  `changed_fields`.
- `GET …/revisions/{n}?compare_to=m` returns the snapshot and `changes`, a list of `{field, label, before, after}` against revision `m`
  (default `n-1`; none for revision 1).
- Both use the requirement's read scope (`load_scoped(officers=True)`, out of scope = 404); an unknown `n` or `m` is also 404.
  `Cache-Control: no-store`.

**R6 — Hiring process (`jobs` columns).**
- `interview_rounds`: JSON list of ≤10 strings, ≤120 characters each, in order;
- `screening_steps`: JSON list of ≤10 strings, ≤120 characters each;
- `decision_maker_contact_id`: FK `company_contacts`. It must be an active contact of the requirement's own company when set or changed
  (422); keeping a contact deactivated since is allowed (the JD rule);
- `expected_tat_days`: whole days, 1–365, the target turnaround.

All of these are editable by whoever has `can_edit`.

**R7 — Commercial terms per requirement (`jobs` columns).**
- `payment_trigger`: `on_joining`, `days_after_joining` or `on_invoice`;
- `payment_days`: 1–365, required exactly when the trigger is `days_after_joining`;
- `payment_terms` (≤2000) and `replacement_terms` (≤2000), which override the contract's `payment_terms` / `replacement_policy`. Null
  inherits from the contract.
- The fee keeps rec-031's override (`PUT …/fee`, manager role + effective edit) and its contract fallback.

The detail's `commercial_terms` block gives, for each term, `value` and `inherited` (true = from the current contract):
`{fee: {basis, value, inherited}, payment_trigger, payment_days, payment_terms: {value, inherited}, replacement_terms: {value, inherited}}`.

**R8 — Commercial gate (pob-001).**
- Without `commercials.client.view`:
  - `commercial_terms` is **absent**;
  - snapshot keys `fee_basis`, `fee_value`, `payment_trigger`, `payment_days`, `payment_terms`, `replacement_terms` are absent from
    every revision read;
  - those names are dropped from `changed_fields` and `changes`.
- A PATCH carrying any R7 field without effective edit (view + edit) is 403 "Your role cannot view or change client commercial terms",
  logged as `recruiter_commercials_refused`.
- `commercial_terms.can_edit` is added (`can_edit` and effective edit). It sits in the gated block rather than in `permissions`, because
  without view there is nothing to edit.

**R9 — Backup owner (Q-02: "always co-access").** `jobs.backup_owner_user_id`, an active recruiter (`placement_team` with a recruiter
profile) other than the primary.
- The backup reads the requirement like an assignee (recruiter scope; a manager's team scope includes a team backup).
- The backup holds the primary's owner rights, so `can_manage_owners` is true for them. AC3 ("owner access while the primary is
  inactive") holds because the access never depends on the primary. In practice the primary cannot be deactivated with open work anyway
  (rec-037).
- **Who sets it:** set or cleared through the PATCH by those who manage owners *and* edit requirement fields: the primary, the backup
  and super_admin. A placement manager never edits requirement fields (rec-007 `WRITERS`, unchanged), so the PATCH 403s them; they move
  the primary instead. Anyone else is 403; an ineligible person is 422; the primary is 409. The picker is
  `GET …/assignment-options?role=backup`.
- **Becoming primary:** if the backup becomes primary (`set_primary`: reassign or rec-037 bulk move), the backup is cleared.
- **Deactivation:** a deactivated backup is cleared (`requirement_owners.release`), with an audit row each.
- It is in the hrc-004 audit diff by name.

**R10 — Eligibility review.** A PATCH already runs hrc-009's `review.flag` (the backlog edge case "a revision made while applications are
open"). Nothing new.

**R11 — Web.**
- **Edit form:** a "Hiring process" section (rounds and steps one per line, a decision-maker select from the company's contacts, TAT
  days); a "Commercial terms" section only with `can_edit_terms` (trigger, days, payment and replacement terms; the contract's text shown
  as the inherited default); a backup-owner picker only with `can_manage_owners`; an optional "Reason for this revision".
- **Detail:** shows the hiring process, a Commercial terms card ("From the contract" marks inherited terms), and the backup owner on the
  Owners card.
- **Revisions section:** the list, "View revision n" (its values and its diff against the previous revision), and a compare-to picker.

**R12 — Audit and logs.** The PATCH audit row is unchanged in shape: new fields appear in `fields`/`changes`, commercial ones redacted as
"changed" (hrc-004 B4). A revision write logs `recruiter_requirement_revised` (job, revision, field count, never values).

## Alternatives considered
- **Backup owner as a `job_assignments` role:** gives history for free, but it changes hrc-006's frozen CHECKs and roles, and permissions
  would need an async lookup in every list row. The column keeps the sync permission check.
- **Q-02 "only while the primary is inactive":** a primary with open work cannot be deactivated (rec-037), so the rule would almost never
  fire, and it needs an extra user read per check.
- **Backfilling revision 1 in the migration:** the snapshot would have to be rebuilt in SQL exactly as the service builds it (names,
  skills), which is fragile. R3's lazy baseline is honest about what it is.
- **Diff computed on write:** stores redundant data and fixes the comparison; a computed diff also allows compare-to.

## Acceptance (testable)
1. A PATCH that changes the headcount from 2 to 3 writes exactly one revision. Revision 2's changes show vacancies 2 → 3, and revision 1
   is still readable.
2. A PATCH with no change, or the same values, writes no revision.
3. A requirement without per-requirement terms shows the contract's payment and replacement terms and fee as inherited; once set, they
   show as overridden.
4. A backup owner reads and edits the requirement and manages its owners while not the primary. A non-owner recruiter cannot set the
   backup (403 or 404 by scope).
5. Without `commercials.client.view`: no `commercial_terms`, no commercial keys in revision snapshots or diffs, and a PATCH of
   `payment_terms` is 403.
6. The decision-maker must be an active contact of the same company (422 otherwise); `payment_days` is required with
   `days_after_joining` (422).
7. An out-of-scope recruiter gets 404 on the revisions list and on a revision.

## Regression risks
- rec-007 / hrc-004 / hrc-005 / hrc-006 / pob-001 tests: the PATCH stays additive; requirement detail fixtures gain keys;
- the rec-038 route matrix (two new GET routes need rows);
- web vitest fixtures typed `Requirement` (new optional fields);
- `navigation` is unchanged.

## Numbering
Migration `0281_job_revisions` (hrc-029 holds 0279/0280), `DEC-SCOPE-405`, API §12KX, RBAC §2.298. All are re-checked at merge.
