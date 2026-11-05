# hrc-019 — Advanced multi-filter resume search (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` hrc-019 (PDF §8 filter groups, §8.1 behaviour, §8.2/§8.3 examples, §16, §17
  QA #6–8; the PDF is classified `UNVERIFIED` and was not readable in this session, so the §8.2/§8.3 D example *wording* is taken from
  the backlog's "+" case only). Scope approved by the owner 2026-11-01 (backlog Q-00). Dependencies hrc-010 (`DEC-SCOPE-383`), hrc-011
  (`375`), hrc-012 (`382`), hrc-017 (`388`), hrc-021 (`397`) and hrc-026 (`394`) are merged. Decision `DEC-SCOPE-399`.
- **Open questions Q-19 (deeper boolean nesting) and Q-20 (p95 target):** the owner said to proceed with the recommended answers, so S1–S14
  below are **the builder's calls (`NEEDS_CONFIRMATION`)**.

## Intent
Find Candidates (rec-013/014) searches skills, a few profile fields and the resume text. The profile now holds education rows, employment
rows, structured location, preferences, the normalised package, owners, documents and applications (hrc-010…026), but a recruiter cannot
search on any of it, cannot sort, and cannot see *why* a card matched. hrc-019 adds the §8 filter groups, sorting, the "unknown salary"
option and a per-card match explanation, on the same endpoint, with the same query count.

**Non-goals:** saved searches and export (hrc-020); deeper boolean nesting than `A AND (B OR C)` (Q-19, S2); talent-pool rules gaining
the new filters (rec-015 rules stay stored columns); a stored `last_activity_at` column.
**Anti-goal:** a compensation filter or sort usable by a role without `candidates.compensation:view` (a side channel, S9).

## Rules

**S1 — One endpoint, additive.** `POST /recruiter/candidates/search` keeps its URL, auth (`require_reader`), paging and every existing
field. `CandidateSearch` gains optional fields (all default to "no filter"); an unknown key is still 422 (`extra="forbid"`). Every
filter is one more `AND`ed `WHERE` condition (`candidate_search.filters`), so the facets and total keep matching the page.

**S2 — Q-19: no deeper nesting.** "A AND (B OR C)" stays `all` + `any` groups.

**S3 — Skills group.**
- `preferred` (≤ 10 terms, counted in the 20-term cap): nice-to-have skills. They never filter while there is another skill, category
  or resume-text input; as the only input they list whoever holds at least one. They feed the match sort (S10) and the card's "why
  matched" (S11). Resolved through aliases/related skills like the others (unknown term = the FS3 422).
- `category_ids` (≤ 10): the candidate holds at least one skill whose primary category or a secondary tag (`skill_category_tags`) is one of
  them (OR).
- `min_level` (`beginner`…`expert`): every `all`/`any` term must be held at that level or above (hrc-017's `_has(min_level)`).
- `skill_min_months` (0–600): every `all`/`any` term must be held with at least that many months on the skill row (per-skill experience).
  A row with no months recorded does not count.
- A search still needs at least one skill term (`all`/`any`/`preferred`), a category, or resume text (S13).

**S4 — Education group** (any one education row must satisfy all the education filters given — same-row semantics, a single `EXISTS`):
`degree`, `specialisation`, `institution` (case-insensitive *contains*, ≤ 120), `passing_year_min`/`_max` (1950–2100), `cgpa_min`/`_max`
(0–10). The grade is free text (hrc-010): only a grade that is a plain number from 0 to 10 (e.g. `8.2`) is compared; "82%" or "First
class" never matches a CGPA filter.

**S5 — Experience group.** `fresher` (true = total experience recorded as 0 months), the existing total range, `relevant_min_months` /
`relevant_max_months` (hrc-010 `relevant_experience_months`), and — over any one employment row, same-row semantics — `designation`,
`industry` (contains) and `employment_types` (any of `full_time`…`temporary`).

**S6 — Location group.** `country`, `state`, `city` (contains on the hrc-010 structured columns), `preferred_location` (contains, any
entry of `preferred_locations`), `willing_to_relocate` (true only), `work_modes` (the candidate prefers any of them). The legacy
`location` contains-filter stays.

**S7 — Preferences group.** `preferred_role` (contains; the single `preferred_role` or any entry of `preferred_roles`),
`preferred_employment_types` (any). Availability (notice bands) stays where it is.

**S8 — Status, recruitment data, documents, applications.** Existing `status`, `engagement`, `source_id`; plus `owner` (`me` = the
caller is the primary recruiter, `unassigned` = no primary recruiter; hrc-012), `registered_from` / `registered_to` (dates, inclusive,
on `created_at` in IST — the app's business time zone), `has_resume` (true/false: a current resume exists), `document_types` (holds any of
the hrc-015 document types), `application_statuses` (has an application now in any of them; hrc-026), `interviewed` (true: has at least
one rec-020 interview round on any application).

**S9 — Package group (grant only).** Expected (existing `salary_min`/`salary_max`), `current_min`/`current_max`, `minimum_min`/`minimum_max`,
all on the hrc-011 normalised annual INR. `package_unknown: true` keeps candidates whose figure for each *applied* range is not provided
("Unknown is included when chosen"); without it they are excluded, as today. The four bands of a range are therefore: below / within /
above (excluded by the range) and unknown (opt-in). **AuthZ:** any package field, `package_unknown`, or `sort=package` from a caller without
`candidates.compensation:view` is **403** (`NO_COMPENSATION`) before anything is read; the existing card stripping is unchanged.

**S10 — Sorting** (`sort`, a whitelist; unknown = 422):

| Key | Order (ties: newest registration, then id) |
|---|---|
| `relevance` (default) | today's order: resume-text rank when there is text, else newest |
| `match` | how many of the searched terms (`all`, every `any` term, `preferred`) the candidate holds, descending |
| `experience` | total experience, most first, unknown last |
| `package` | expected annual INR, lowest first, unknown last (grant only, S9) |
| `registered` | newest registration first |
| `activity` | last activity, most recent first: the latest of the profile update, an application change, a website application, a call or a message |
| `completeness` | hrc-010 Appendix B completeness percent, highest first (the same seven weights, as one SQL expression) |

**S11 — Why matched.** Each card gains `match: {required: [{term, skill, held}], preferred: [{term, skill, held}]}` — `required` lists
the `all` terms and every `any` term, `held` = the candidate holds the skill (or an alias/related skill); it is computed in Python from the
page's skill rows (no extra query). The card shows "Matches: Java, Spring Boot · Missing preferred: Docker". With only resume text,
`match` is empty lists and the snippet explains the match.

**S12 — Performance (Q-20: no p95 number confirmed; target ≤ 500 ms for the four example searches on a 10k pool, measure).** The fixed
query count is kept (a test pins it). Migration `0275_candidate_search_indexes` adds `pg_trgm` (`CREATE EXTENSION IF NOT EXISTS`) and GIN
trigram indexes on `candidates.location`, `candidate_education.institution` and `candidate_employment.designation`, and btree indexes on
`candidates.current_annual_inr`, `candidates.minimum_annual_inr` and `candidates.experience_months`. A test runs `EXPLAIN` on the four
example searches (it must plan without error). Last activity has no column (S10 computes it); a maintained column is the follow-up if the
activity sort is slow.

**S13 — Validation.** Ranges are min ≤ max (422 with the field's label); text filters are whitespace-collapsed, ≤ 120 characters, control
characters refused; lists are de-duplicated and capped (10); dates are `YYYY-MM-DD`.

**S14 — Numbering.** `DEC-SCOPE-399`; API §12KR; migration `0275`; no RBAC change (the compensation grant exists). 398/12KQ/0274 are left
for in-flight siblings (hrc-027, hrc-028).

## Frontend (`RecruiterFindCandidates`)
- The panel keeps the resume search and skill chips on top, adds **Nice-to-have skills** chips, and groups the rest in collapsible
  sections (`<details>`): Skills, Education, Experience, Location, Preferences, Package (only with the grant), Status and recruitment,
  Documents and applications, Availability. A section with an active filter opens by default and shows a count in its summary.
- Every filter lives in the URL (refresh/Back keep it; a hand-edited value the API would refuse is dropped, the rec-013 rule).
- **Active filters** row above the results: one removable chip per filter ("Degree: B.Tech ×"), so each can be cleared individually (AC2);
  "Clear all" stays.
- **Sort** select in the results header (changes the URL at once, back to page 1). The package option shows only with the grant.
- Card: a "Why matched" line from S11.
- Loading / empty / error states are the existing ones.

## Tests
Backend (`tests/test_hrc_019_search.py`): one fixture set; each filter group in and out; same-row semantics for education/employment;
CGPA ignores non-numeric grades; `package_unknown` in/out (AC4); every sort key (AC3); the backlog "+" example "Java AND Spring Boot;
relevant 2–5 yrs; ₹6–10 LPA" returns exactly the seeded matches (AC1); 403 for a package filter, `package_unknown` or `sort=package`
without the grant; 422 for an unknown sort, inverted range, bad date; the fresher-with-0-months and no-resume-with-text edge cases; query
count unchanged; `EXPLAIN` for four examples; talent pools and job visibility still work (rule bodies built with `model_construct`).
Web (vitest): URL ↔ state ↔ body for the new filters; active-filter chips remove one filter; sort select; package controls hidden without
the grant. E2E: a recruiter narrows by degree and sorts, removes one chip.

## Regression risks
`test_rec_013*`, `test_rec_014*` (query counts, response shape — `match` is additive), rec-015 talent pools and hrc-008 job visibility
(they call `filters()` with a `model_construct` body: new fields must default to "no filter"), `matching.py` (imports `_has`), the
RecruiterFindCandidates vitest fixtures and rec-013 e2e.
