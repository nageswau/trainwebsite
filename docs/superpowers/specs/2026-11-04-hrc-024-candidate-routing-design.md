# hrc-024 — Candidate routing rules and unassigned queue (design)

- **Feature ID:** `hrc-024` · **Decision:** `DEC-SCOPE-393` · **Numbering:** migration `0270_candidate_routing`, API §12KL, RBAC §2.287
- **Requirement:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-024` (PDF §6.1 steps 6–8, §6.2 "default recruiter", §13 "No
  recruiter assigned → exception queue + alert HR Manager"; PDF classified `UNVERIFIED`). Scope approved by the owner 2026-11-01
  (backlog Q-00). Dependencies merged: hrc-012 (`DEC-SCOPE-382`), hrc-023 (`DEC-SCOPE-389`), itc-002 (`DEC-SCOPE-336`).
- The owner said to proceed with the recommended answers, so R1–R12 below are **the builder's calls (`NEEDS_CONFIRMATION`)**.

## Goal
A candidate the website creates (hrc-023 job application, hrc-022 portal verification) gets a primary recruiter by ordered rules, or
lands in the unassigned queue with an alert; the assignment is notified and recorded in hrc-012's history.

**Non-goals:** branch routing (no branch exists on candidates or recruiters — `NEEDS_CONFIRMATION`); routing recruiter-created or
imported candidates (their creator owns them, hrc-012 O7); re-routing on later profile changes; the New Website Registrations workspace
(hrc-025); a shared telecaller/candidate distributor (the backlog's "consider" — the candidate side copies the lead idiom instead, since
the eligibility, owner column and history differ).

## Decisions (builder's calls)
- **R1 Order.** Default recruiter → source rules → skill-category rules → location rules → unassigned queue. Branch is not built.
- **R2 Rule = (kind, value, recruiter).** Several recruiters on one value form a group; the strategy picks one of the group's eligible
  recruiters. Within a kind, when several values match (two skill categories), the oldest matching rule's value wins.
- **R3 Eligible recruiter** = hrc-012's: an active `placement_team` user with a recruiter profile. An inactive one is skipped.
- **R4 Default recruiter** (one setting) overrides every rule while eligible; when inactive the rules apply and the page flags it.
- **R5 Matching.** Source = `candidates.source_id`. Skill category = a skill of the candidate whose category (or an hrc-017 tag
  category) is the rule's. Location = the candidate's `city`, else `location`, trimmed, case-insensitive equal to the rule's text.
- **R6 Strategy** (one setting): `round_robin` (default; a cursor per value group, id order, the lead idiom) or `least_workload` (fewest
  open owned candidates — not archived, not merged; ties go in turn). `candidates.owner_user_id` is already indexed.
- **R7 When.** Only a candidate the website creates (hrc-023 `_create`, hrc-022 `link_candidate` new row). Routing runs in a SAVEPOINT:
  an unexpected error leaves the candidate saved and unassigned (logged) — and it is still alerted as unassigned.
- **R8 Assignment** = hrc-012's: `owner_user_id`, a history row (kind `owner`, reason `route`, changed by the system = NULL), a
  `candidate.assign` audit row naming the method and rule, and `it.candidate.assigned` to the recruiter.
- **R9 No recruiter** → new event `it.candidate.unassigned` to every active placement manager (link: the unassigned queue) and every
  active `hr_manager` (no link — that role has no candidate screens, hrc-012 O10's idiom).
- **R10 Queue and assign** reuse hrc-012: the Candidate Master's "Unassigned" filter is the queue (a nav entry "Unassigned Queue" opens
  it) and the ownership panel assigns (history + notice).
- **R11 Rights.** Placement managers and super_admin read and change routing (hrc-012's assigners; `hr_manager` has no candidate
  access); everyone else 403. Rules are added and deleted (a changed rule is a different rule; no edit).
- **R12 Concurrency.** The group's cursor row is locked FOR UPDATE (insert-if-missing first) so concurrent intakes serialise; the chosen
  recruiter is read FOR SHARE so a concurrent deactivation waits. A duplicate rule is a 409 (unique index).

## Data (migration 0270)
- `candidate_routing_rules` (id, kind ∈ source|skill_category|location, source_id, skill_category_id, location, recruiter_user_id,
  created_by_user_id, timestamps); a check that exactly the kind's value is set; a unique index on (kind, value, recruiter).
- `candidate_routing_settings` (id = 1, default_recruiter_user_id, strategy, updated_by_user_id); no row = round robin, no default.
- `candidate_routing_cursors` (group_key PK, last_user_id).
- `candidate_assignment_history`: `changed_by_user_id` nullable (the system), reason adds `route`. Downgrade deletes the `route` rows.

## API (§12KL)
- `GET /recruiter/candidate-routing` → settings, rules (with labels and each recruiter's active flag).
- `PUT /recruiter/candidate-routing` `{default_recruiter_user_id, strategy}`.
- `POST /recruiter/candidate-routing/rules` `{kind, source_id | skill_category_id | location, recruiter_user_id}` → 201; `DELETE
  /recruiter/candidate-routing/rules/{id}` → 204. Pickers reuse `/recruiter/catalogue/candidate-sources`,
  `/recruiter/skill-categories`, `/recruiter/candidates/assignees?kind=recruiter`.

## UI
`/recruiter/manager/routing` "Candidate routing": settings card (default recruiter, strategy), rules table in routing order with
Delete, an add-rule form; a link to the unassigned queue. Loading, empty, error and saving states; labelled controls.

## Tests
pytest (service + routes + migration round trip + rec-038 rows), vitest (page), e2e (configure a source rule, website apply → owner).
