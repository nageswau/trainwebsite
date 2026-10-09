# rec-013 — Find Candidates: skill AND/OR search, synonyms, filters, facets, result cards (design)

Backlog: `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-013. Source: EVID-018 user question (line 1092), S2-§5 (1287–1305), §6 (1307–1327),
§7 (1329–1349), §9 (1381–1425), §12 (1503–1539), §13 (1541–1561), §16 (1607–1643), §18 (1677–1714), §19 (1716–1734); Appendix B F1–F3.
Depends on rec-006 (merged PR #150), rec-009 (merged PR #155) and rec-011 (merged PR #180); all three are on `main`.

**Numbering:** `DEC-SCOPE-142`, API §12BJ, RBAC §2.68, **no migration**. Drafted as 141 / §12BI / §2.67; upc-026
(139 / §12BG / §2.65) and upc-012 (140 / §12BH / §2.66) merged first, and upc-020 (`0126` / 141 / §12BI / §2.67)
merged after them. Re-check
origin/main before the merge and re-chain if needed.

## 1. Answers (2026-10-09)
The owner asked to proceed with the recommended answers, so nothing was asked. Every row below is **UNVERIFIED** (a recorded default).

| ID | Question | Default |
|---|---|---|
| FS1 (Q-15) | AND/OR input | A **chip builder**, never a typed query string. The page has "Must have all of" skills (AND) and up to 5 "At least one of" groups (each group an OR, and the groups are ANDed with the rest). `Java AND Spring Boot AND (AWS OR Azure)` = all [Java, Spring Boot] + one group [AWS, Azure]; `Java OR Python` = one group. The S2-§18 "All skills / Any skill" switch is the two boxes. Nothing is parsed into SQL. |
| FS2 | Synonyms | Each typed term goes through `services/skills.resolve` (an active skill's name or alias, case and spacing ignored), so an alias finds the skill's holders (AC1). The term then also matches the skill's **related** skills (rec-006 `skill_related`, both directions; S2-§16 "Java should understand Core Java…"). The response lists what each term expanded to. |
| FS3 | Unknown term | 422 `{message, code: "unknown_skill", term, suggestions}`; `suggestions` = up to 5 active skill names whose name or alias contains the text. |
| FS4 | Size | 1–20 terms in total (all + every group), at most 5 groups, each group 1–10 terms. No term → 422 ("Add at least one skill"); 21+ terms → 422. Each term is 1–120 characters. |
| FS5 | Filters (S2-§18) | Experience min/max **in months** (inclusive; the page takes years); current location (a case-insensitive substring); availability = one or more notice bands (F3); qualification (substring); expected salary min/max in **INR per year** (the page takes lakhs, ₹5L = 500000); candidate source; candidate status; "verified only" (every matched skill row must be `verified` or `assessed`). A min above its max is 422. |
| FS6 | Job type | **Not offered.** The candidate master holds no job-type preference (rec-009 §8 fields), so there is nothing to filter. Recorded as a gap for a later item. |
| FS7 | Facets (F1–F3) | Over the whole filtered set, so each facet's counts add up to the total (AC4). F1 experience: 0–1 yr (0–11 months), 1–3 (12–35), 3–5 (36–59), 5+ (≥ 60), Not recorded. F2 location: the 5 most common current locations (grouped case-insensitively), Other, Not recorded. F3 availability: Immediate (0 days), 15 days (1–15), 30 days (16–30), 31–59 days, 60+ days, Not recorded. Clicking a band narrows the search (Other and Not recorded do not). |
| FS8 | Result card (S2-§19) | Name, preferred role (the master has no "current role"), current company, experience, skills (matched ones first and marked; verified ones marked), location, availability, expected salary, source + detail (S2-§13), status. **Match %** is rec-016 and is not shown. |
| FS9 | Card actions | **View profile** (everyone). **Shortlist**: writers pick a requirement once ("Shortlist into…", their rec-007 scope), then each card's button adds the candidate at `shortlisted` through rec-017's `POST /recruiter/requirements/{id}/candidates` (its 409/422 sentences shown as is). **Contact**: writers get a link to the profile's call/message section (rec-025/026). **Share** is rec-019 and is not shown. |
| FS10 | Roles | The rec-009 readers: `placement_team`, `placement_manager`, `super_admin`, and `hr_team` (read only: no Shortlist/Contact). Everyone else, including employers, 403 before anything is read. |
| FS11 | Order and paging | Newest candidate first (the rec-009 list order), 50 a page (limit ≤ 100). |
| FS12 | Pool | `services/candidates.pool_filter()` (external + opted-in students, R11/AC5) and not archived. |

## 2. Data
No migration. `candidate_skills` already has `ix_candidate_skills_skill_candidate (skill_id, status, candidate_id)` (rec-011 built it for
this search) and `uq_candidate_skills_skill (candidate_id, skill_id)`. The scalar filters run on the already-narrowed pool. The 10k-candidate
test (§6) is the budget check; indexes are added only if it fails.

## 3. Service `app/services/candidate_search.py`
Functions only, read-only, no commit.
- `resolve_terms(db, body)` → per term `(text, skill, ids)`. **One** query resolves every term (names and aliases, active skills); **one**
  query reads the related pairs of all resolved skills. Unknown → the FS3 422 (one extra suggestions query, only on that error path).
- `_has(ids, verified_only)` → `EXISTS (SELECT 1 FROM candidate_skills WHERE candidate_id = candidates.id AND skill_id IN (...) [AND status
  <> 'claimed'])` — SQLAlchemy expressions with bound parameters only.
- `filters(body, terms)` → pool + not archived + one `_has` per AND term + one `_has` per group (the group's ids unioned) + the FS5 filters.
- `facets(db, filters)` → one row of `count(*) FILTER (WHERE …)` for the total, F1 and F3; one grouped query for F2's top 5.
- `page(db, filters, limit, offset)` → the page's candidates with their source (one query) and all their skills (one batched query).
- Fixed query count: 2 (terms) + 2 (facets) + 2 (page) = 6, whatever the page size or pool size.

## 4. API (§12BJ) `POST /api/v1/recruiter/candidates/search?limit=&offset=`
Body (`CandidateSearch`, extra fields forbidden): `all: [str]`, `any: [[str]]`, `verified_only: bool`, `experience_min_months`,
`experience_max_months` (0–600), `location` (≤ 120), `availability: ["immediate"|"d15"|"d30"|"d31_59"|"d60_plus"]`, `qualification`
(≤ 120), `salary_min`, `salary_max` (≥ 0), `source_id`, `status`. Parsed with the tel-002 `_parse` idiom, so a 422 is one sentence.

Response: `{items, total, limit, offset, facets: {experience: [{key, count}], location: [{value, count}], availability: [{key, count}]},
terms: [{term, skill: {id, name}, also: [name]}]}`. Item: `id, candidate_code, name, preferred_role, current_company, experience_months,
location, notice_days, expected_salary, source {id, name, active}, source_detail, status, skills: [{name, level, status, matched}]`.
Never mobile or email (the list shape). Logged as `candidate_search` with the user id, term count and total — never the terms' text
beyond counts.

## 5. Web
- `/recruiter/find-candidates` (`FindCandidatesPage` in `RecruiterCandidatePages.tsx`, the rec-009 shell) and a "Find Candidates" nav entry
  for recruiters, placement managers, super_admin and hr_team.
- `lib/recruiterCandidateSearch.ts`: types, the URL ⇄ body mapping (`all`, `any1`…`any5`, `exp_min`, `exp_max` in years, `location`,
  `availability`, `qualification`, `salary_min`, `salary_max` in lakhs, `source_id`, `status`, `verified`, `offset`; a hand-edited bad value
  is dropped), band labels, `lakhs` ⇄ INR.
- `components/RecruiterFindCandidates.tsx`: the search form (skill chip inputs: type + Enter/Add; × removes; groups add/remove), the
  facets panel, the result cards, the pager, and the writer-only "Shortlist into…" requirement picker (`SearchableSelect`). Search state
  lives in the URL (refresh and Back keep the place, the tel-008 idiom). Loading / empty ("No candidates match") / error + Retry / the
  422 sentence (with "Did you mean …" buttons for `unknown_skill`) are each shown.
- `RecruiterCandidateDetail`: an `id="contact"` wrapper on the calls + messages cards so Contact can link there.

## 6. Tests
Backend `tests/test_rec_013_find_candidates.py` (each test makes its own skills, so the shared DB's other rows never match):
AC1 alias + related; AC2 AND; AC3 AND + OR group; AC4 facet sums = total, and bands correct; AC5 a non-opted-in student never returned
(an opted-in one is); verified only; every scalar filter; 422s (empty, 21 terms, 6 groups, unknown with suggestions, min > max, bad
band); 403 employer / it_admin, hr_team 200; fixed query count across result sizes; 10k candidates in a rolled-back transaction, search
under 2 s.
Web: vitest for the URL ⇄ body mapping and labels; Playwright e2e: a recruiter adds skills chips, sees the count and facets, narrows by a
facet, shortlists into a requirement; hr_team sees no Shortlist; mobile width has no horizontal scroll.

## 7. Out of scope
Match % (rec-016), Share (rec-019), resume full text (rec-014), talent pools (rec-015), the dashboard search box (rec-032), job-type
filter (FS6).

## 8. Browser QA (2026-10-09, stack `rec013` web :3413 / api :8413)
Independent pass with Browser Use (isolated Chrome) and Playwright, as recruiter, hr_team, trainer and signed out, at 1034 px, 768 px
and 390 px. Working on the first pass: alias + related expansion, AND + OR group, facet narrowing, refresh / Back, shortlist (a double
click makes one application; a duplicate shows rec-017's 409 sentence), the unknown-skill suggestion, signed-out redirect to
`/it/login?next=…`, trainer "Your role cannot view candidates" (page) and 403 (API), hr_team read only, no sideways scroll.

| ID | Sev | Issue | Fix |
|---|---|---|---|
| QA-01 | Low | No results still showed an all-zero facet panel, an empty Location heading and the shortlist picker | Only the count and "No candidates match" |
| QA-02 | Low | A refused search (min salary above max, 422) offered Retry, which can never succeed | Retry only for a network error or a 5xx |
| QA-03 | Medium | After Search (desktop) the results rendered ~900 px below the form; nothing visible changed | The results are scrolled into view and focused after a Search from the form (not after a facet or a link) |
| QA-04 | Medium | On a phone the zero-count facet rows filled a screen before the first card | Zero-count rows (and empty facets) are hidden |
| QA-05 | Low | No visible cue while a new search loaded over the old results | "Updating results…" under the count |
| QA-06 | Low | The chip list shared its input's accessible name | The list is named "<label>: chosen" |
| QA-07 | Low | A hand-edited offset past the end showed an empty list and "Showing 5001–5000" | "No candidates on this page" + "Go to the first page" |
