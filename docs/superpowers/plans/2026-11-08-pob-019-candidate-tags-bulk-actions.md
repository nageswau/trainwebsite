# pob-019 Candidate tags, enriched results and bulk actions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Free (admin-list) and derived system tags on candidates, five enrichment facts on every Find Candidates card within a fixed query
budget, and bulk shortlist / bulk task actions over a selection.

**Architecture:** A new rec-002 managed list (`rec_candidate_tags`, slug `candidate-tags`) plus a link table; `candidate_search.page()`
gains two batched queries (facts, tags) and rides the skill categories on its existing skills query; two bulk endpoints reuse the single
add (`applications.create`) and the hrc-016 task service inside one transaction each.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL; Next.js/React, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-08-pob-019-candidate-tags-bulk-actions-design.md` (DEC-SCOPE-437, migration `0319_candidate_tags`,
API §12MD, RBAC §2.328).

## Global Constraints
- Tags per candidate ≤ 20; `tag_ids` search filter ≤ 10; bulk `candidate_ids` 1–50, de-duplicated.
- Readers (`candidates.READERS`, incl. hr_team) read tags; writers (`candidates.WRITERS`) write; hr_team gets 403 on every write.
- Catalogue writes: managers and super_admin only (existing rec-002 rule, nothing new).
- Enrichment adds a fixed number of queries whatever the page size (rec-013 / hrc-019 query-count tests must still pass).
- Export (hrc-020) columns unchanged; talent pools (rec-015) only gain card fields.
- Audit/log lines carry ids only.

## Review Focus
1. A tag deactivated after being put on a candidate: the PUT keeping it must succeed; adding it anew must 422.
2. Bulk shortlist where one id is outside the pool / archived / unknown: skipped `unavailable`, never 404/500, other rows still added.
3. Bulk shortlist on a closed requirement or by hr_team: whole request refused (409 / 403) and nothing added.
4. Bulk task where the assignee is the caller: no notification; another assignee: exactly one notification for N tasks.
5. Card with no owner / never contacted / no tags: renders "Unassigned" / "Never" / no tag row, no crash.

---

### Task 1: Model + migration
**Files:** Modify `apps/api/app/models.py` (RecCandidateTag, CandidateTagLink, REC_CATALOGUE_MODELS["candidate-tags"]); Create
`apps/api/alembic/versions/0319_candidate_tags.py` (down `0318_placement_guarantee`, create-if-missing, downgrade drops both);
Test `apps/api/tests/test_pob_019_candidate_tags_bulk.py::test_migration_round_trip`-style check (tables exist, model/migration parity).
- `candidate_tag_links(candidate_id FK candidates CASCADE, tag_id FK rec_candidate_tags RESTRICT, added_by_user_id FK users RESTRICT, created_at)`,
  PK (candidate_id, tag_id), index `ix_candidate_tag_links_tag(tag_id)`.

### Task 2: Tag read/replace API
**Files:** `apps/api/app/services/candidate_tags.py` (new: `read(db, candidate_id) -> list[dict]`, `replace(db, user, candidate, tag_ids) -> dict`,
`for_page(db, ids) -> dict[UUID, list[dict]]`), `apps/api/app/schemas.py` (`CandidateTagsIn{tag_ids: list[UUID] ≤20, deduped}`),
`apps/api/app/api/recruiter_candidates.py` (`GET/PUT /recruiter/candidates/{id}/tags` → `{items:[{id,name,active}], can_edit}`).
- PUT: writer, candidate lock, archived 409, new ids must be active tags (422 "Choose active candidate tags"), audit `candidate.tags`
  {added, removed}. Tests: replace set, inactive kept vs added, hr_team 403 on PUT / 200 on GET, archived 409, >20 → 422.

### Task 3: Search filter + enrichment
**Files:** `schemas.CandidateSearch.tag_ids` (≤10, may stand alone), `services/candidate_search.py` (`filters` EXISTS; `page()` adds
`owner`, `last_contacted_at`, `active_applications`, `prior_submissions` (count of submissions), `tags`, `system_tags` [{kind, label}]).
- Tests: tag filter alone and with skill; values of each fact; SELECT count equal for page sizes 2 and 6.

### Task 4: Bulk shortlist
**Files:** `schemas.RecBulkShortlistIn{candidate_ids 1–50, note?}`, `api/recruiter_applications.py`
`POST /recruiter/requirements/{id}/candidates/bulk` → `{added:[{candidate_id, application_id}], skipped:[{candidate_id, reason, message}]}`.
- Reasons `already_added`, `do_not_contact`, `unavailable`. Tests: 20 added in one commit, mixed skips, closed requirement 409, hr_team 403.

### Task 5: Bulk tasks
**Files:** `schemas.CandidateBulkTaskCreate` (task fields without application_id + candidate_ids), `services/candidate_notes_tasks.create_many`,
`api/recruiter_candidate_notes_tasks.py` `POST /recruiter/candidate-tasks/bulk` → `{created:[{candidate_id, task_id}], skipped:[…]}`.
- Tests: N tasks, single notification, archived skipped, past due 422, hr_team 403.

### Task 6: RBAC / matrix rows + docs
rec-038 route rows for the 4 routes; API_CONTRACT §12MD, RBAC_MATRIX §2.328, DATA_MODEL, PRODUCT_DECISION_REGISTER DEC-SCOPE-437, backlog
status, RTM.

### Task 7: Front end
- `lib/recruiterCatalogue.ts`: `"candidate-tags"` tab.
- `lib/recruiterCandidateSearch.ts`: card types; filter `tag` (kind `tag`, param `tag`, body `tag_ids`, group `recruitment`); `searchBody`
  accepts tags alone; chips name tags.
- `components/RecruiterFindCandidates.tsx`: card facts Owner / Last contacted / Active applications / Prior submissions, a Tags row
  (free + system); writers always get a select box (`Select {name}`); bulk bar: Shortlist selected (N), Share selected (N), Assign task
  (inline form: type, title, due IST, assignee picker); results report added/skipped; buttons disabled while busy.
- `components/RecruiterCandidateTags.tsx` (new) on the candidate page.
- Vitest `tests/components/pob019CandidateTagsBulk.test.tsx`; e2e `tests/e2e/pob-019-candidate-tags-bulk.spec.ts`; update existing specs
  that used the old `Select X to share` label on Find Candidates.
