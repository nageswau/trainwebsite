# hrc-021 — Candidate engagement status (plan)

Design: `docs/superpowers/specs/2026-11-05-hrc-021-candidate-engagement-status-design.md` (DEC-SCOPE-397). TDD per task; focused tests only.

1. **Derivation (E1–E6, E8).** `tests/test_hrc_021_engagement.py`: a fixture candidate per E2 row, the two manual overrides, the 30/90-day
   boundaries, the re-registration case → RED. `app/services/candidate_engagement.py`: `ENGAGEMENTS` (key → label), `expression()` (the
   SQL `CASE`), `out(key)` → GREEN.
2. **List (E7).** Tests: every item carries `engagement`; `?engagement=new` filters; `?engagement=bogus` → 422; the query count is
   unchanged. `recruiter_candidates.list_candidates` selects the expression as a column and passes it to `svc.item_out`; schema
   `CandidateItem.engagement` (optional) and `CandidateEngagement` literal.
3. **Detail.** Test: the detail has `engagement`. `candidates.detail_out` adds it with one scalar query.
4. **Search (E7).** Tests: cards carry `engagement`; body `engagement` filters; unknown → 422. `CandidateSearch.engagement`,
   `candidate_search.filters` / `page`, `CANDIDATE_SEARCH_LABELS`.
5. **Web.** Vitest RED then GREEN: `ENGAGEMENTS` in `lib/recruiterCandidates.ts`; list column + filter; detail chip; Find Candidates chip +
   filter.
6. **Docs.** DEC-SCOPE-397 in the decision register, API §12KP, RTM row, backlog status line.
7. **e2e.** `apps/web/e2e/hrc-021-engagement.spec.ts`: create a candidate → list shows "New"; filter Engagement = New finds it; log a call
   → "Contacted".
