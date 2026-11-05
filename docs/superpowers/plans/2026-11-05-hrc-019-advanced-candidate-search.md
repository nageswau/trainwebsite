# hrc-019 — Advanced multi-filter resume search (plan)

Design: `docs/superpowers/specs/2026-11-05-hrc-019-advanced-candidate-search-design.md` (`DEC-SCOPE-399`).

## Tasks (TDD: each starts with a failing test)
1. **Schema** — `CandidateSearch` gains the S3–S10 fields with validators (ranges, caps, dates, sort whitelist); labels in
   `CANDIDATE_SEARCH_LABELS`. Test: 422s, defaults, `model_construct` bodies (talent pools) still filter nothing extra.
2. **Filters** — `candidate_search.filters()` adds one condition per field (S3–S9); education/employment use one `EXISTS` each (same row).
   Tests: each group in/out, CGPA numeric only, fresher 0 months, `package_unknown`.
3. **Sort + why matched** — `page()` takes the sort key (S10) and builds `match` (S11) from the rows it already reads. Tests: every sort,
   `match` contents, query count unchanged.
4. **Route AuthZ** — package fields / `package_unknown` / `sort=package` → 403 without the grant (S9). Tests for each.
5. **Migration 0275** — pg_trgm + indexes (S12), models declare the btree ones. Tests: upgrade/downgrade round trip, EXPLAIN of four
   example searches, the backlog "+" example returns exactly the seeded matches (AC1).
6. **Web lib** — `recruiterCandidateSearch.ts`: a filter table drives URL ↔ state ↔ body and the active-filter chip labels; `sort`.
7. **Web UI** — grouped collapsible panel, active-filter chips (remove one), sort select, nice-to-have chips, "Why matched" line.
8. **E2E** — `hrc-019-advanced-search.spec.ts`.
9. **Docs** — DEC-SCOPE-399, API §12KR, backlog status, RTM rows.

## Review notes (Phase 3)
- **API:** additive fields only; `extra="forbid"` keeps typos 422; a 403 for compensation is decided before any query (no timing/side
  channel); sort is a whitelist mapped to fixed SQL (no user text reaches ORDER BY).
- **Security:** every text filter goes through `lookups._pattern` (LIKE-escaped, bound parameter); dates/ints validated; `owner=me` uses
  the caller's id from the session, never a client id; the search log stays counts-only (no filter values).
- **Frontend:** reuse `.field`, `.badge`, `.btn` and `action-card`; `<details>/<summary>` are keyboard- and screen-reader-native; chips'
  remove buttons have `aria-label="Remove <filter>"`; the panel stays one column on phones (existing auto-fit grids).
- **Transactions:** read-only endpoint, no writes; no concurrency concerns.
