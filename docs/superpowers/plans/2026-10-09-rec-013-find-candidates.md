# rec-013 Find Candidates — implementation plan

Spec: `docs/superpowers/specs/2026-10-09-rec-013-find-candidates-design.md`. Branch `feature/rec-013` from origin/main @ `6fc05526`.
Execution: inline, TDD, one task at a time; lite tests only (the user runs the full backend suite separately).

## Phase 3 review notes (applied to the tasks below)
- **API:** POST because the expression is a body; read-only, so a repeat is harmless (no idempotency key). `extra="forbid"`; every 422 is
  one sentence (tel-002 `_parse`); FS3's 422 carries `code`/`term`/`suggestions` like rec-009's duplicate 409. Paging = `bdm.LIMIT/OFFSET`.
  Declared on the `/recruiter/candidates` router as `POST /search` — no clash with `GET/PATCH /{candidate_id}` or the two-segment POSTs.
- **Security:** role check first (403 before any read, employers included); the pool filter is always applied (AC5); terms are resolved to
  skill ids and only ids reach SQL (bound `IN`), substrings go through `lookups._pattern` (escaped ILIKE); size caps (FS4) bound the query;
  no contact data in the result; the log line carries counts, never the search text. React escapes every rendered value (no
  `dangerouslySetInnerHTML`). CSRF/session handling unchanged (the existing cookie + `sendJson` path).
- **Frontend:** reuse the rec-009 shell, `SearchableSelect`, `sendJson`, `LocalTime`-free cards, the tel-008 URL-held state; aria-live
  status for counts; errors in `role="alert"`; chips are buttons with an accessible "Remove Java" name; facets are buttons with counts;
  cards stack on mobile (CSS grid auto-fit), no horizontal scroll.

## Tasks
1. **Backend tests (RED):** `apps/api/tests/test_rec_013_find_candidates.py` — AC1–AC5, verified only, filters, 422s, roles, query count,
   10k budget. Run → fail (404 route).
2. **Schema + service + route (GREEN):** `CandidateSearch` in `schemas.py`; `services/candidate_search.py`; `POST /search` in
   `api/recruiter_candidates.py`. Run the new file + `test_rec_009_candidates.py` + `test_rec_011_candidate_skills.py`.
3. **Web lib (RED→GREEN):** `apps/web/tests/lib/recruiterCandidateSearch.test.ts` then `lib/recruiterCandidateSearch.ts`.
4. **Web page + component:** `FindCandidatesPage`, `app/recruiter/find-candidates/page.tsx`, `components/RecruiterFindCandidates.tsx`,
   nav entries, `id="contact"` on the detail; component vitest for the chip builder / states.
5. **e2e:** `apps/web/e2e/rec-013-find-candidates.spec.ts`.
6. **Docs:** DEC-SCOPE-150 in the register, API §12BR, RBAC §2.76, screen catalog, backlog status line, spec status.
7. **Gates:** tsc, eslint, vitest (affected), `next build`, ruff, lite pytest, Playwright spec, browser QA.
