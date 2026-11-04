# hrc-014 — Candidate duplicate review and merge (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-014` (PDF §5.1, §17 QA; PDF classified `UNVERIFIED`). Scope approved by
  the owner 2026-11-01 (backlog Q-00: all phases). Dependency hrc-004 (DEC-SCOPE-376) merged. The owner said to proceed with the
  recommended answers, so Q-14 and every call below is **the builder's call (`NEEDS_CONFIRMATION`)**. Decision `DEC-SCOPE-377`.
- **Reuse:** the itc-007 lead-merge engine shape (`services/lead_merge.py`): find in scope → lock both rows FOR UPDATE in id order →
  re-check → one UPDATE per child table → fill-empty fields → one audit row → the route commits.

## Intent

A person must exist once in the candidate pool. Exact mobile/email matches are already blocked (rec-009 Q-07, unique indexes) and stay
blocked. Probable matches cannot be blocked safely (two real people can share a name), so they go to a review queue where an authorised
person either dismisses the pair ("not the same person") or merges one candidate (the victim) into the other (the survivor).

Non-goals: fuzzy/phonetic name matching, automatic merging, un-merge, merging student logins, merging compensation.

## Builder's calls (Q-14, `NEEDS_CONFIRMATION`)

- **D1 Signals.** `name_location_college`: same name (trimmed, case- and space-insensitive), same location and same college (both
  present). `phone_variant`: the mobile's last 10 digits are the same while the stored numbers differ (e.g. `9876543210` vs
  `+91 98765 43210` stored unparsed). **Name + date of birth is not implemented**: the candidate has no DOB field (hrc-010 may add one).
- **D2 When detected.** After a candidate is created or edited (name, location, college or mobile changed), and on demand by a pool-wide
  "Check the whole pool" scan (finds pairs that existed before hrc-014). Only active (not archived), in-pool candidates pair up. A pair is
  stored once (`candidate_id < other_id`); a dismissed pair is never re-queued.
- **D3 Grant.** `candidates.merge` (the key hrc-002 declared with no holder). Default holder `placement_manager`; hrc-002's
  `hr_manager` is not a candidate-writer role, so it gets no default (`NEEDS_CONFIRMATION`); super_admin implicitly; a recruiter only through a per-user override ("authorised recruiters"). The
  queue, scan, dismiss, preview and merge all need the grant **and** a candidate-writer role.
- **D4 Fields.** The merge form compares name, location, qualification, college, passing year, experience, current company, notice
  period, preferred role and LinkedIn. Each survivor field keeps its value unless the user picks the victim's; empty survivor fields fill
  from the victim. Mobile, email and compensation are shown (compensation only with its grant) but never moved: the unique indexes keep
  the victim's contact on the archived victim, where the rec-009 duplicate check still finds it.
- **D5 Student logins.** A victim linked to a student login → 409 "merge the other way"; both linked → 409 (cannot merge two logins).
  So the victim never has consent rows of its own; consents are still moved generically (zero rows) and never deleted — both
  histories are kept.
- **D6 Same job (AC2).** When both candidates are on the same requirement, the survivor's application stays. If the victim's one is
  still open → 409 naming the requirement ("Reject or withdraw … first"). If it is closed (rejected/withdrawn) it stays on the archived
  victim, together with its share items, and the merge result reports it as `kept_applications`.
- **D7 What moves.** Applications (with `student_id` set to the survivor's login), their profile-share items, calls, messages, consents,
  skills the survivor lacks (a skill both have stays with the victim), and every resume. Resumes are renumbered by upload time across both
  candidates so the newest upload is current. Audit rows and the victim's history stay with the victim.
- **D8 Victim.** Archived (`archived_at`, `archived_by`), `merged_into_id` = survivor, `merged_at`, `merged_by_user_id`. It cannot be
  restored (409 "merged into CAN-…"). Its detail page links to the survivor.
- **D9 Queue rows.** The pair's row becomes `merged`; every other open row that names the victim closes as `merged` too; then the
  survivor is re-checked (D2), so a third duplicate shows up again against the survivor.
- **D10 Audit.** One `candidate.merge` row on the survivor (victim id/code, moved counts, kept applications, chosen fields, hrc-004
  field changes with contact/compensation redacted) and one `candidate.merged_into` row on the victim. Dismiss: `candidate.duplicate_dismiss`.

## Data (migration 0256)

- `candidates`: `merged_into_id` (FK candidates, nullable), `merged_at`, `merged_by_user_id`; CHECK: merged ⇒ archived and all three
  set together; no self-merge.
- `candidate_duplicates`: `id`, `candidate_id`, `other_id` (FKs, RESTRICT, CHECK `candidate_id < other_id`, UNIQUE pair), `signals`
  (JSON list), `status` (`open|dismissed|merged`), `created_at`, `decided_by_user_id`, `decided_at`, `note` (≤ 500); index (status, created_at).
- Seed `candidates.merge` for `placement_manager` (frozen copy, `ON CONFLICT DO NOTHING`); downgrade removes the grant, overrides,
  table and columns.

## API (§12JW)

- `GET /recruiter/candidate-duplicates?status=open|dismissed|merged&limit&offset` — pairs, oldest first, both sides
  (id, code, name, location, college, status, archived), signals, decision. Pairs with an archived or out-of-pool side are hidden while open.
- `POST /recruiter/candidate-duplicates/scan` → `{created}`.
- `POST /recruiter/candidate-duplicates/{id}/dismiss` `{note?}` → the row; 409 when not open.
- `GET /recruiter/candidates/{id}/merge?victim=CAN-…` — preview: both sides' fields, what moves, the same-job conflicts.
- `POST /recruiter/candidates/{id}/merge` `{victim_code, use_victim: [field], reason?}` → `{id, victim_id, victim_code, moved, kept_applications}`.
- `CandidateDetail` gains `merged_into` (`{id, candidate_code}` or null).
- Errors: 403 (role/grant), 404 (either side unknown or outside the pool), 422 (self, bad field), 409 (archived side, student logins,
  open same-job application, already merged).

## Concurrency and transactions

Find both by id/code → `SELECT … FOR UPDATE` both in id order with `populate_existing` → re-check every rule on the locked rows → move →
flush → audit → one commit in the route. Two merges of a crossing pair serialise; a second merge of the same victim sees it archived (409).
Pair inserts use `ON CONFLICT DO NOTHING`.

## UI

- `/recruiter/candidates/duplicates` (nav "Duplicate Review": placement manager and super admin): status tabs, a "Check the whole pool"
  button, a table of pairs (both names linked, signals as badges), per row "Review and merge" and "Not the same person" (confirm).
  Loading, empty, error states; 403 page for roles without the grant.
- `/recruiter/candidates/{id}/merge?victim=CAN-…`: side-by-side table (field, stays, merges in, a radio per differing field), "Swap"
  (the other one stays), what moves, conflicts (blocking ones in an alert, Merge disabled), a reason box, Merge with a confirm; on success
  go to the survivor with a notice.
- Candidate detail: a merged victim shows "Merged into CAN-…" (link) and no Restore button.

## Tests

Backend `tests/test_hrc_014_duplicates.py` (signals, queue, dismiss, scan, grant/role 403, merge moves every child, renumbered resumes,
same-job open 409 / closed kept, student logins 409, restore blocked, audit, queue closure, preview) and `test_hrc_014_migration.py`.
Web: component tests for the queue and merge form; e2e `hrc-014-duplicates.spec.ts`. Pinned catalogue tests (nehn-005) are updated for
the new resource/action.
