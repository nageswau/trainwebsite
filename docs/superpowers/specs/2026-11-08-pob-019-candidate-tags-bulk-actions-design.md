# pob-019 — Candidate tags, enriched results and bulk actions (design)

- **Decision:** `DEC-SCOPE-439` (2026-11-08). Migration `0319_candidate_tags`; API §12MF; RBAC §2.329 (renumbered after pob-025/026/027 took 434-436).
- **Backlog:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-019. Dependencies hrc-012, hrc-016, hrc-019, hrc-020, hrc-021 and
  pob-021 are built.
- **Status of the calls:** T1–T12 are the builder's calls (`NEEDS_CONFIRMATION`). The owner asked for recommended answers instead of
  questions.

## Calls

- **T1 (Q-14):** free tags come from an admin list. That list is a new rec-002 managed list, "Candidate tags" (`rec_candidate_tags`,
  slug `candidate-tags`). Managers and super_admin maintain it in the existing catalogue screen; recruiters read the active tags. Tags
  are deactivated, never deleted.
- **T2:** `candidate_tag_links` has a primary key of (candidate_id, tag_id) plus who added the tag and when. Candidate writers replace a
  candidate's whole set with `PUT /recruiter/candidates/{id}/tags {tag_ids}`, up to 20 tags. A newly added tag must be active; an
  inactive tag already on the candidate may stay. The audit row `candidate.tags` lists the added and removed ids.
- **T3:** system tags are derived on read and never stored: the experience band (the F1 bands, plus "Fresher" at 0 months) and the
  categories of the candidate's skills. Location, availability and source are already card facts and filters.
- **T4:** the search takes a filter `tag_ids` (any of them, up to 10). It is one EXISTS condition, and it may stand alone like
  `category_ids`.
- **T5:** each card shows:
  - the `owner` {id, full_name} (hrc-012)
  - the engagement (hrc-021, as before)
  - `last_contacted_at`: the latest logged call or message
  - `active_applications`: applications whose status is not in `CLOSED_APPLICATIONS`
  - `prior_submissions`: the candidate's pob-021 submission rows
  - `tags` and `system_tags`
- **T6:** enrichment is batched: one query for the facts and one for the tags, whatever the page size. The skill categories ride on the
  page's existing skills query. The card's shape only grows, so talent pools (rec-015) and the export (hrc-020) are unchanged. The
  export keeps its columns.
- **T7:** bulk shortlist is `POST /recruiter/requirements/{id}/candidates/bulk {candidate_ids (1–50), note?}`. It runs the single
  add's checks (requirement scope, writer role, requirement not ended) and adds each candidate as Shortlisted. Everything happens in one
  transaction, with one commit.
- **T8:** the bulk shortlist skips candidates with a reason instead of failing the request:
  - `already_added`: the candidate is already on this requirement
  - `do_not_contact`: the candidate's status is Do Not Contact
  - `unavailable`: the candidate is not in the caller's pool, is archived, or does not exist

  The response is `{added: [{candidate_id, application_id}], skipped: [{candidate_id, reason, message}]}`. If a concurrent add hits the
  unique index, the whole batch rolls back with a 409, and the caller retries.
- **T9:** bulk task is `POST /recruiter/candidate-tasks/bulk`. It takes the hrc-016 task fields without `application_id` (`job_id` is
  allowed), plus `candidate_ids` (1–50). It creates one task per open candidate, in one transaction. The assignee gets a single
  notification. Archived or unavailable candidates are skipped with a reason.
- **T10:** export stays the hrc-020 search export (the `candidates.export` grant). There is no new export path.
- **T11:** the bulk endpoints are not idempotent; repeating a shortlist reports `already_added`. The front end disables the button
  while a request is running.
- **T12:** FE: result cards show the new facts and the tags. Writers always see a select box on each card. A bulk bar offers:
  - "Shortlist selected (N)", which needs a requirement
  - "Share selected", as before
  - "Assign task", an inline form

  The candidate page gets a Tags section, and the catalogue gets a "Candidate tags" tab.

## Not built
"Role family" tags (the candidate has no role-family field), a bulk tag action, and an export of the selected candidates only.

## Tests
- Backend `tests/test_pob_019_candidate_tags_bulk.py`:
  - tags CRUD and the inactive-tag rule
  - the search filter, the enrichment values, and the query count staying fixed across page sizes
  - bulk shortlist of 20 in one transaction, with already-added, Do Not Contact and out-of-pool candidates skipped
  - bulk tasks with a single notification
  - RBAC: hr_team is refused writes
  - the migration
- Vitest: the card facts and tags, and the bulk bar.
- E2E: `pob-019-candidate-tags-bulk.spec.ts`.
