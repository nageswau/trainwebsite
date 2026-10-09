# rec-014 — Resume full-text search (design)

Backlog: `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-014. Source: S2-§15 resume search (1585–1605): "global resume search over structured
skills, resume content, previous job titles, certifications and projects"; R7 (Postgres `tsvector`). Depends on rec-012 (merged PR #197:
`candidate_resumes.extracted_text`) and rec-013 (merged PR #199: `POST /recruiter/candidates/search`); both are on `main`.

**Status: DRAFT** on `feature/rec-014`.

**Numbering:** migration `0137_resume_search` (after upc-011's `0136_partnership_events`), `DEC-SCOPE-153`, API §12BU, RBAC §2.79 (a
note only: the roles are rec-013's). Drafted as 0136 / 152 / §12BT / §2.78; upc-011 merged first (PR #202) and took them. Re-check
origin/main before merging.

## 1. Answers (2026-10-09)
The owner asked to proceed with the recommended answers, so nothing was asked. Every row below is **UNVERIFIED** (a recorded default).

| ID | Question | Default |
|---|---|---|
| FT1 | What is searched | The **current** resume's extracted text (the candidate's highest resume version, rec-009). Titles, certifications, projects and skills written in the resume are all part of that text, so S2-§15's five sources are covered by one vector. The profile's structured skills stay the rec-013 chip filters, and the two combine (AC2). |
| FT2 | Query syntax | `websearch_to_tsquery('english', text)`: plain words must all appear (in any order); `"quoted words"` is a phrase; `or` between words; `-word` excludes. English stemming, so "Microservices" also finds "microservice". |
| FT3 | Only stop words | `200` with no candidates and `notice` = "Your resume search only has common words like “the” or “and”, so it matches nothing. Add a more specific word." Unknown skills are still a `422` first. |
| FT4 | Size | `text` is 1–200 characters after trimming and collapsing whitespace. Blank counts as absent, and control characters are a `422`. A search needs at least one skill **or** the text: "Add at least one skill or some resume search text". |
| FT5 | Order | With text: by relevance (`ts_rank_cd` on the current resume), then newest first. Without text, rec-013's newest first is unchanged. |
| FT6 | Snippet | Each card carries `snippet`: up to 2 fragments of the current resume around the hits (`ts_headline`, 8–20 words each, joined by " … "). It is capped at 300 characters and returned as `[{text, hit}]` segments, so the server never sends HTML. The page renders hits with `<mark>`. `snippet` is `null` when the search has no text. |
| FT7 | No text | A scanned resume (`''`), a never-extracted resume (`null`) or a candidate with no resume is never matched by text. There is no backfill: the recruiter runs rec-012's Extract on an older resume. |
| FT8 | Index | A **generated stored** column `candidate_resumes.search_vector = to_tsvector('english', coalesce(extracted_text, ''))`, so every extraction refreshes it with no trigger and no application code. It has a GIN index `ix_candidate_resumes_search`. The table is small and append-only, so the index is built normally, not `CONCURRENTLY`. |
| FT9 | Roles and logs | As rec-013: `placement_team`, `placement_manager`, `super_admin` and `hr_team` (read). The snippets show resume text only to those readers, who can already open the resume (rec-009). The log line gains `text: true/false`, never the text. |
| FT10 | Page | A "Resume search" box at the top of the Find Candidates form; the URL keeps it as `q` (refresh/Back). |

## 2. Data — migration `0137_resume_search`
- `candidate_resumes.search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english'::regconfig, coalesce(extracted_text, ''))) STORED`.
- `CREATE INDEX ix_candidate_resumes_search ON candidate_resumes USING gin (search_vector)`.
- Guarded like 0135, because 0001's `create_all` already builds both from the models on a fresh database. downgrade() drops the index and the
  column; the content is derived, so nothing is lost.
- Model: `Computed(..., persisted=True)`, `deferred=True` (never loaded into Python), `Index(..., postgresql_using="gin")`.

## 3. API — `POST /recruiter/candidates/search` (additive)
- Body gains `text` (FT4).
- Response gains `notice: string | null` (FT3), and each item gains `snippet: [{text, hit}] | null` (FT6).
- Every other field and behaviour is unchanged.

## 4. Service `app/services/candidate_search.py`
- `query = websearch_to_tsquery('english', :text)`, a bound parameter. The text never becomes SQL.
- `filters` adds `candidates.id IN (SELECT candidate_id FROM candidate_resumes r WHERE r.search_vector @@ query AND r.version = (SELECT
  max(version) FROM candidate_resumes WHERE candidate_id = r.candidate_id))`. The GIN index finds matching resumes, and the version check
  keeps only current ones. The facets and the page use the same `where`, so the facets still add up (rec-013 AC4).
- `page` orders by a correlated `ts_rank_cd` of the current resume when there is text.
- `snippets(db, ids, text)`: one query for the page's candidates (current resume, `ts_headline` with private-use sentinel markers), which is
  then split into segments and capped.
- Stop words: one `SELECT numnode(query)` query. When it is 0, the search runs with a false condition (same shape, zero counts) and sets
  `notice`.
- Query count: a search without text runs exactly rec-013's queries. Text adds the `numnode` query and the snippet query.

## 5. Page
- `SearchState.text` ↔ URL `q` ↔ body `text`. `searchBody` is non-null when there is a skill or text.
- The empty prompt becomes "Add a skill or a resume search to search every candidate in the pool."
- Each card shows a "From the resume" block with the snippet; hits are `<mark>` and the text is escaped by React.
- `notice` is shown as a status message.

## 6. Tests
- **API:**
  - AC1: a resume mentioning Microservices with no such skill is found by "Java Spring Boot Microservices".
  - AC2: text plus a skill chip narrows the results.
  - A certification phrase is found.
  - Only stop words gives an empty result plus `notice`.
  - A scanned or unextracted resume is not matched.
  - Only the current version is searched.
  - Relevance order.
  - Snippet segments and the 300-character cap.
  - A text-only search works; no skill and no text → 422; text over 200 characters → 422.
  - Roles as rec-013.
  - The query count without text is unchanged.
- **Migration:** the column is generated and the index is GIN; a round trip keeps existing rows (throwaway database).
- **Web (vitest):** the box ↔ URL `q` ↔ body; a text-only search is sent; snippet `<mark>`; the notice.
- **Browser/e2e:** extract a resume, search its words, and see the highlighted snippet and the AC2 narrowing.
