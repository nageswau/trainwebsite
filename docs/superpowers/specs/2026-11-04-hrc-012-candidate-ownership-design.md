# hrc-012 — Candidate ownership: primary recruiter, placement officer, collaborators (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` hrc-012 (PDF §5 metadata, §6.2, §12; PDF classified `UNVERIFIED`). Scope
  approved by the owner 2026-11-01 (backlog Q-00). Dependency hrc-002 (`DEC-SCOPE-374`) is merged (#446). Decision `DEC-SCOPE-382`.
- **Open question Q-11** (pool-wide or owner-scoped visibility): the owner said to proceed with the recommended answers, so O1–O10 below
  are **the builder's calls (`NEEDS_CONFIRMATION`)**.

## Intent
Today every candidate is pool-wide and nobody owns one (R11, rec-009): there is no work queue, nobody to notify, and nothing to hand over
when a recruiter leaves. hrc-012 gives each candidate one primary recruiter, an optional placement-officer owner and (only when shared
ownership is switched on) collaborators, with an append-only assignment history. Visibility does **not** change.

**Non-goals:** owner-scoped visibility; routing rules / unassigned queue automation (hrc-024); vacancy co-ownership (hrc-006); giving
`hr_manager` or `placement_officer` access to the recruiter candidate screens (DEC-SCOPE-374 R2 stays).
**Anti-goal:** a recruiter who can take another recruiter's candidate, or a candidate assigned to someone who cannot work it.

## Rules

**O1 — Visibility stays pool-wide (Q-11, recommended).** Every candidate reader still sees every candidate; rec-013 search, pools and
matching are untouched. Ownership drives the "My candidates" / "Unassigned" filters, notices and handover only.

**O2 — Exactly one primary owner (AC1).** `candidates.owner_user_id` (nullable; NULL = unassigned). A single column can never hold two.
Eligible: an **active `placement_team` user with a recruiter profile**. Anyone else (inactive, other role, unknown id) → 422
"Choose an active recruiter" (+/−/E line).

**O3 — Placement-officer owner.** `candidates.placement_officer_user_id` (nullable). Eligible: an active `placement_officer`. Otherwise 422.
The officer's own dashboard (hrc-002 R3) gains a "Your candidates" count — still no candidate field, so DEC-SCOPE-374 R3 holds.

**O4 — Collaborators only when the setting is on (AC2).** `candidate_collaborators` (candidate, user; unique pair). A single-row setting
`candidate_ownership_settings.shared_ownership` (default **off**). While off, adding a collaborator is a 422 "Shared ownership is switched
off"; removing one is always allowed (so switching off never strands rows). Eligible collaborator: an active `placement_team` or
`placement_officer` user who is not the primary owner. At most 10 per candidate.

**O5 — Who may change ownership.** `super_admin` and `placement_manager` (the recruiters' lead, rec-037's reassigner) for any candidate;
the **current primary owner** for their own candidate (reassign, officer, collaborators). Another recruiter → 403. `hr_team` reads only.
The backlog's "HR Manager reassigns" is **not built**: `hr_manager` has no candidate access (DEC-SCOPE-374 R2); it stays
`NEEDS_CONFIRMATION` with hrc-025 ("HR Manager sees all"). The setting is changed by `placement_manager` / `super_admin`.

**O6 — History (AC3).** `candidate_assignment_history`: one row per change — `kind` (`owner`, `placement_officer`, `collaborator_added`,
`collaborator_removed`), `from_user_id`, `to_user_id`, `changed_by_user_id`, `reason` (`create`, `assign`, `reassign`), `created_at`.
Append-only. Each change also writes an audit row `candidate.assign` with `changes` by name, so the hrc-004 Change history shows it.

**O7 — On create.** A `placement_team` creator becomes the primary owner (history reason `create`). Any other creator leaves it unassigned.

**O8 — Deactivated recruiter (AC4).** rec-037's bulk Reassign (Team page) also moves every candidate the source primarily owns (archived
too) to the target, with history (`reassign`) and audit; `work` counts gain `candidates`. Deactivating a recruiter who still primarily owns
a non-archived candidate is refused (422), like companies and requirements (RC2). Inactive officers and collaborators are shown
"(inactive)" and can be replaced or removed; they do not block deactivation.

**O9 — Backfill.** Migration 0259 sets `owner_user_id = created_by_user_id` where that user is `placement_team`; other rows stay
unassigned. No history rows are invented for the backfill.

**O10 — Notices.** `it.candidate.assigned` ("Candidate assigned to you", fixed text) to the new primary owner, new officer and each added
collaborator, never to the actor themselves.

**Merge (hrc-014):** unchanged — the survivor keeps its own owners; the archived victim keeps its rows.

## API (§12KA)
- `GET /recruiter/candidates?owner=me|unassigned` — `me` = I am primary owner, officer or collaborator. Each item gains `owner`
  `{id, full_name, active} | null`.
- `GET /recruiter/candidates/{id}` gains `ownership`: `{owner, placement_officer, collaborators[], shared_ownership, can_assign}`.
- `PUT /recruiter/candidates/{id}/ownership` — partial body `{owner_user_id?, placement_officer_user_id?, collaborator_user_ids?}` (a key
  sent as null clears; collaborators is the full new list). Locks the candidate row; archived/merged → 409; returns the detail. A no-op
  writes nothing.
- `GET /recruiter/candidates/assignees?kind=recruiter|officer|collaborator&q=` — active eligible users `{id, full_name, role}` (≤ 20), for
  candidate readers who can assign.
- `GET|PUT /recruiter/candidate-ownership-settings` — `{shared_ownership, can_edit}`; PUT by manager/super_admin, audited.
- `POST /recruiter/manager/reassign` — `moved.candidates` added (additive).

## Frontend
List: an Owner column ("Unassigned" when none) and an Owner filter (All / My candidates / Unassigned) kept in the URL; the shared-ownership
switch for managers above the list. Detail: an Ownership card (primary recruiter, placement officer, collaborators) with Change ownership
(SearchableSelect pickers, collaborator chips with Remove, Escape cancels, error takes focus) when `can_assign`. Team page: a Candidates
column and the Reassign text counts candidates.

## Security
Ownership never widens reading. Every id in a PUT is checked (role, active, profile) under FOR SHARE locks; one message per kind so the
picker can't probe users. The assignee lookup returns names only. Audit and logs carry ids.

## Regression risks
rec-038 matrix (new routes need rows), rec-037 reassign tests (`moved` shape, "nothing to reassign"), `CandidatePage`/`CandidateDetail`
response models, the candidate list e2e/vitest, admin deactivation of recruiters.
