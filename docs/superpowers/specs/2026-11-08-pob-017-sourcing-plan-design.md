# pob-017 — Per-requirement sourcing plan and source funnel (design)

**Decision:** `DEC-SCOPE-429` (builder's calls S1–S12, all `NEEDS_CONFIRMATION`). **Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md`
§pob-017 (`UNVERIFIED` requirements draft). Dependencies built: pob-002 (DEC-SCOPE-407), hrc-020 (DEC-SCOPE-401), pob-018 (DEC-SCOPE-428).
The owner asked for recommended answers instead of questions, so every call below is the builder's.

## Intent
A recruiter working one requirement keeps its sourcing plan next to it: who we are looking for, which searches and Boolean strings
find them, which channels we will use, how many profiles we need by when, who owns sourcing, and how far we have got — and sees,
per source, how many candidates were found, screened, suitable, submitted and rejected.

## Acceptance criteria (backlog)
1. **AC1** The plan saves (and reads back).
2. **AC2** The funnel counts by source tie out: per stage, the per-source rows add up to the total, and `found` equals the requirement's applications.
3. **AC3** Deadline breaches are flagged.
4. **Edge** A candidate whose source changes after submission is counted under the source they had at submission.

## Non-goals
No scraping or external-site integration (Boolean strings are stored text with a copy button). No change to talent pools, saved
searches, shares or search. No dashboard widget (pob-028). No reminders/notifications on breach.

## Builder's calls (S1–S12)
- **S1 Plan row.** `job_sourcing_plans`, one per requirement (PK `job_id`), created by the first save. Fields: `target_profile`
  (≤ 2000), `boolean_strings` (JSON list, ≤ 10 of `{label ≤ 80, query ≤ 2000}`), `target_found`, `target_screened`,
  `target_submitted` (0–10 000 or null), `deadline` (date or null), `source_owner_user_id`, `updated_by_user_id`, timestamps.
  No plan row = an empty plan.
- **S2 Planned channels** are candidate-source catalogue entries (pob-018's catalogue, incl. Vendor/Website/Community/Institution):
  `job_sourcing_plan_channels (job_id, source_id)`, ≤ 20. A new choice must be active; an inactive one already chosen is kept.
  The funnel lists every planned channel, even with nothing found yet.
- **S3 Saved searches** (hrc-020): `job_sourcing_plan_searches (job_id, saved_search_id ON DELETE CASCADE)`, ≤ 10. Only a
  search visible to the caller (own or shared) can be added, and only by a candidate reader (`candidates.READERS`). A reader sees
  only the linked searches visible to them, plus a count of hidden ones; a save keeps links the caller cannot see. Each visible
  link opens Find Candidates with its filters.
- **S4 Skills** are the requirement's own required/preferred skills, shown from the requirement payload, never copied.
- **S5 Funnel stages** per application, from its status history and current status (rank sourced 0, screened 1, shortlisted 2,
  profile_shared 3, interview 4, selected 5, joined 6): found = every application; screened = rank ≥ 1 reached or a screening
  saved; suitable = rank ≥ 2 reached; submitted = rank ≥ 3 reached or a share item exists; rejected = current status
  `rejected`. Stages are nested (found ⊇ screened ⊇ suitable ⊇ submitted) because each later test implies the earlier one.
  Withdrawn applications are found but not rejected. Conversion = submitted ÷ found (Appendix B), null when found = 0.
- **S6 Attribution.** New nullable `job_applications.submitted_source_id`, set once — the candidate's source when the
  application first enters a submitted status (create or move into profile_shared/interview/selected/joined), never changed
  after. The funnel attributes by `coalesce(submitted_source_id, candidates.source_id)`. Migration backfills applications that
  already reached a submitted status with the candidate's current source (the best evidence available).
- **S7 Progress** compares found/screened/submitted with their targets. State: `no_targets` (no target set), `met` (every set
  target reached), `on_track` (otherwise, deadline not passed or not set), `breached` (deadline before today in IST and a set
  target not reached). The breach lists the short targets.
- **S8 Source owner** must be one of the requirement's team: primary owner, backup owner or a `job_assignments` assignee (422
  otherwise). Picked from the requirement's own owners on the page.
- **S9 Who.** Read: every reader of the requirement (`load_scoped(officers=True)`; counts only, no candidate details). Write: the
  requirement's writers (`requirements.require(..., "can_edit")`): a cancelled requirement is read-only (409).
- **S10 Writes** lock the requirement row, replace the plan, channels and links in one transaction, and audit
  `requirement_sourcing_plan.update` with the changed field names only (no text). The log carries ids only.
- **S11 API.** `GET /api/v1/recruiter/requirements/{id}/sourcing` → `{plan, channels, searches, hidden_searches, funnel,
  progress, can_edit, can_link_searches}`; `PUT` same path with the whole plan body → the same shape. Unknown keys 422.
- **S12 Routes mount** on the pob-016 checklist router module (no `main.py` change).

## Implementation plan (TDD, small tasks)
1. Models + migration `0310_sourcing_plans` (guarded, frozen checks, backfill) + migration test (chain, checks, round trip).
2. `applications._record`/`create` snapshot + tests (set once, unchanged by later moves or source edits).
3. Service `requirement_sourcing.py` (view, save, funnel, progress) + router + schemas; API tests for AC1–AC3, edge, auth (404
   scope, 403 role, 409 cancelled, 422 validation), audit; rec-038 matrix rows.
4. Web: `lib/requirementSourcing.ts` + `RequirementSourcing.tsx` card on the requirement page (loading/empty/error, edit form,
   copy buttons, funnel table, breach badge, responsive table) + vitest; Playwright e2e.
5. Docs: decision register, API contract §12LV, RBAC §2.320, data model, RTM, backlog status.

## Regression risks
`applications._record` runs on every status move (one extra attribute write, SQL sub-select); `job_applications` model/migration
tests that pin columns; the rec-038 route matrix.
