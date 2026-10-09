# rec-014 Resume full-text search — implementation plan

Spec: `docs/superpowers/specs/2026-10-09-rec-014-resume-full-text-search-design.md`. Every task is TDD (red, green, refactor) and runs the
focused tests only.

## Task 1 — Data
- Test `tests/test_rec_014_migration.py`:
  - 0136 chains after 0135 and is the single head.
  - The model has a `search_vector` Computed column and a GIN index.
  - Round trip in a throwaway database: the column is generated (`is_generated = 'ALWAYS'`), the index is GIN, an existing row's vector
    is filled, and downgrade removes both while the rows remain.
- Code:
  - `models.CandidateResume.search_vector` (Computed, deferred) + `Index(postgresql_using="gin")`.
  - `alembic/versions/0136_resume_search.py`, guarded.

## Task 2 — Schema
- Test: `{}` → "at least one skill or some resume search text"; `{"text": "x"*201}` → 422; `{"text": "  "}` → the needs-one 422;
  `{"text": "java\x01"}` → 422; a text-only body is accepted.
- Code: `CandidateSearch.text` (a `_resume_text` validator, blank → None), the `_limits` message, the `CANDIDATE_SEARCH_LABELS["text"]` label.

## Task 3 — Service
- Tests `tests/test_rec_014_resume_search.py` (World helper + a resume with `extracted_text`):
  - AC1 Microservices.
  - AC2 narrowing.
  - A certification phrase.
  - Stop words → notice.
  - Scanned and unextracted resumes are not matched.
  - The old version is not matched.
  - Relevance order.
  - Snippet segments and cap; `snippet` is null without text.
  - Facets add up.
  - Roles (hr_team reads, employer 403).
  - Query count without text is unchanged.
- Code:
  - `candidate_search`: `_tsquery`, the `filters` text clause, `page` rank ordering, `snippets()`, `search` notice.
  - The `log` line gains `text`.

## Task 4 — Web
- Vitest:
  - The box ↔ URL `q` ↔ body `text`.
  - A text-only URL searches.
  - The new empty prompt.
  - The snippet renders `<mark>`.
  - The notice is shown.
- Code: `lib/recruiterCandidateSearch.ts` (state/params/body/types), `RecruiterFindCandidates.tsx` (input, card snippet, notice).

## Task 5 — Docs
- DEC-SCOPE-152 (FT1–FT10).
- API §12BT.
- RBAC §2.78 note.
- DATA_MODEL 0136.
- Backlog rec-014 status.

## Task 6 — Browser QA and Playwright e2e
- `tests/e2e/rec-014-resume-search.spec.ts` against the isolated stack.

## Review notes (Phase 3)
- **API:** the change is additive. POST stays read-only. 422 sentences use the existing `_parse` labels.
- **Security:**
  - The text is only ever a bound parameter to `websearch_to_tsquery`, which never raises on bad syntax.
  - Snippets are segments, not HTML. The sentinel characters are removed from the source text before `ts_headline`.
  - The pool filter still applies.
  - Logs carry no text.
- **Performance:**
  - GIN index on `search_vector`.
  - `ts_headline` runs for page rows only, and `ts_rank_cd` reads the stored vector.
- **Frontend:**
  - The input is labelled with a hint.
  - `<mark>` for hits.
  - The notice is a status message.
  - Existing loading, empty and error states are reused.
