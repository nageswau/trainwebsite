# upc-024 — Global university search — design

- **Feature:** upc-024 (`docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-024; EVID-020 §25 L810–L866; Appendix B G1–G4)
- **Decision:** `DEC-SCOPE-162`. **No migration.** API §12CD; RBAC §2.88. As with earlier items, these numbers are provisional until merge.
- **Branch:** `feature/upc-024` (worktree branch `worktree-upc-024`), taken from `origin/main` @ `89ac6147`.
- **Dependencies:** all merged on main:
  - upc-003: University Master, readers and `row_out`.
  - upc-007: stage and its G grouping.
  - upc-017: the course master (levels, intakes, structured tuition, per-course commission).
  - upc-014 and upc-016 are also merged. They supply agreements and commission terms for the commission filter.
- **Evidence:**
  - EVID-020 §25 (`DERIVED_BLUEPRINT`).
  - Backlog U2 (`EXPLICIT_APPROVAL`): commission, including the commission search filter, is for `super_admin` and the partnership roles
    only.
  - Backlog U5: one master; readers read every university.
  - Backlog U7: fixed groupings.
  - Backlog U14: no commission for other roles.
- **Status of answers:** the owner told this session to proceed with the recommended answers. SR1–SR16 below are those recommendations.
  They are `NEEDS_CONFIRMATION` at sign-off, not `EXPLICIT_APPROVAL`.

## 1. Understanding

§32's first menu entry, **🌍 Global University Database**, is one page that searches **every university in the master**, not just the
caller's own. It searches the 6 §25 search fields and narrows by the 15 §25 filters. The three source examples must return the right
sets:

- "Japan + Cyber Security + Not Partnered": potential Japanese universities.
- "UK + Business + Partnership in Progress": universities being negotiated.
- "Germany + IT + Active Partner": current partners.

Results are paged, with counts. The filters live in the URL, so a search can be shared or bookmarked.

## 2. Recommendations (SR1–SR16)

| # | Question | Recommended answer (used) |
|---|---|---|
| SR1 | Readers | The University Master readers through `partnership_universities.require_reader`: `partnership_manager` (with a profile), `partnership_head`, `overseas_admin` (overseas division) and `super_admin`. Every other role gets a 403. The counselor's slice (U14) is upc-030's 360 view and is not opened here (the upc-018 PF5 precedent). |
| SR2 | Which universities | Every **active** university, whoever owns it (the master's read rule). Deactivated rows are not searched. |
| SR3 | Text search `q` (§25 "University Name … City") | Literal, case-insensitive substring (`lookups._pattern`) on name, university code, city or country name. Up to 200 characters. |
| SR4 | Country / Region / City | `country`: text up to 100 characters. It matches the country's name (substring) or its ISO-2 code (exact, case-insensitive), so a link can say `country=Japan` or `country=JP`. `region`: one of the 9 `COUNTRY_REGIONS` (e.g. `UK`). `city`: substring. |
| SR5 | University type / Public-private | `institution_type`: one of `INSTITUTION_TYPES`. `ownership_type`: `public` or `private`. |
| SR6 | Ranking | `ranking_max` (1–10000): the university has a ranking whose **leading number** is ≤ N. A band such as "201-250" counts as 201, and a rank with no leading number never matches. `ranking_system` (QS/THE/ARWU/Other) limits which rankings count. Any year. Each row shows its best ranking (the lowest leading number, then the latest year). |
| SR7 | Course filters (same course) | `course` (a word or phrase that **starts a word** in the course **title or category**, case-insensitive. "IT" matches "IT" or "IT Management", not "Security", and "Comput" matches "Computing". A plain substring would make "Germany + IT" match every "Security" course), `level` (`COURSE_LEVELS`: UG, PG, PhD, Diploma, Foundation), `intake` (a month `Jan`…`Dec`), `tuition_min`, `tuition_max` and `tuition_currency`. All of them must hold for **one active course** of the university. That is one `EXISTS`, so "Japan + Cyber Security + UG" means a UG cyber security course. A course with several intakes matches each of its months. When any course filter is sent, each row carries `matching_courses`, the number of its active courses that match. Otherwise it is `null`. |
| SR8 | Tuition range | `tuition_min` and `tuition_max` are ≥ 0 and compare `tuition_amount` in **one currency**, because there is no FX (U4/Q-18). A bound sent without `tuition_currency` is a 422. `tuition_min > tuition_max` is a 422. A course with no structured amount never matches a tuition bound. |
| SR9 | Scholarship | `scholarship=true`: the university has an active scholarship (`scholarships.university_id`) or an active course with at least one linked scholarship. `false` or absent means no filter. |
| SR10 | Commission (U2) | `commission_min`, a percent with 0 < x ≤ 100. A university matches when an active course has `commission_percent` ≥ x, **or** an in-force agreement (`university_agreements.IN_FORCE`, signed/active) has a commission term with `commission_percent` ≥ x. Fixed amounts are not compared (no FX). This is a university-level filter, independent of SR7. **For every non-commission role (`partnership_access.can_see_commission` false) the parameter is ignored**: it is dropped before the query is built, so results never depend on commission data. The page has no commission field for those roles. |
| SR11 | Partner status (§25 "Partner Status"; Appendix B G1–G4) | `partner_status`, one of: `partner` (G1: Partner Activated, Student Recruitment Started, Active Partner); `in_progress` (G2, which includes Agreement Signed per PS3); `target` (G3); `lost` (the Lost/Closed flag); `not_partnered` (G2 + G3). Every value except `lost` excludes lost universities. The source's "Not Partnered", "Partnership in Progress" and "Active Partner" map to `not_partnered`, `in_progress` and `partner`. |
| SR12 | Partnership manager | `manager`: `me`, `none` or a manager id. This reuses the master list's rule (primary **or** backup; `none` = no primary). An invalid value is a 422. |
| SR13 | Expected partnership date | `expected_from` and `expected_to` (dates, inclusive) on `target_partnership_date` (upc-008). `from > to` is a 422. A university with no date never matches a date bound. |
| SR14 | Response | `{items, total, limit, offset, facets}`. Items are the master's `row_out` plus `ownership_type`, `partner_status`, `target_partnership_date`, `ranking` (best ranking text or null) and `matching_courses`. Order: name, then id. Paging: `limit` 1–100 (default 50), `offset` ≥ 0. Facets: `partner_status` counts per value (partner, in_progress, target, lost) under every **other** filter, so each chip says what that choice would give. |
| SR15 | Performance | No migration: course `EXISTS` uses `ix_overseas_courses_university_level`, ranking `EXISTS` uses `uq_university_rankings_entry` (leading `university_id`), stage uses `ix_universities_stage`. A fixed number of queries, whatever the page size or data: count, page, facet, page rankings, and matching courses when any course filter is sent. That is 5 or fewer, plus `require_reader`/`team_of`. A test seeds 1,300 universities × 3 courses and checks the query count and a time budget. |
| SR16 | Page, menu, logs | `/partnership/search` "Global University Database":<br>• A plain GET form (URL-held filters, works without JS); a results table; partner-status chips as links; Previous/Next.<br>• The §32 entry goes live for managers. Heads, `super_admin` and `overseas_admin` get a nav entry.<br>• Reads are not audited (like the other partnership lists). No commission value appears in any log. |

## 3. Backend

- `services/university_search.py` (new, read only) holds the filter builders (location, institution, ranking, course `EXISTS`,
  scholarship, commission, partner status, expected date) and `search(db, user, params) -> dict`.
  - Every value reaches SQL as a bound parameter, and patterns are escaped by `lookups._pattern`.
  - The ranking's leading number uses `substring(rank from '^[0-9]+')::int`.
  - The intake test is `CAST(intakes AS JSONB) @> '["Sep"]'`.
- Route `GET /partnership/universities/search` in `api/partnership_universities.py`. It is declared **before** `/{university_id}`, or
  `search` would be parsed as a UUID. Query parameters are validated by FastAPI and `Literal`s (422). Pydantic schema
  `UniversitySearchPage`.
- `commission_min` is dropped for non-commission roles before `search` builds anything (SR10).

## 4. Frontend

- `lib/universitySearch.ts`: the types, `SEARCH_PATH = /partnership/search`, `searchQuery(filters, limit, offset)`, `searchPageHref`,
  `PARTNER_STATUSES` labels and `MONTHS`.
- `app/partnership/search/page.tsx` (server component), following the courses-page idiom (`accessUnavailable`, `PortalShell`,
  `shellFor`):
  - the form: search, country, region, city, type, ownership, ranking ≤ / system, course, level, intake, tuition min / max / currency,
    scholarship, commission ≥ % (commission roles only), partner status, manager, expected from / to;
  - chips with counts;
  - the table: University (link + code), Country / city, Type, Ranking, Partner status (stage label), Manager, Expected date, Matching
    courses (only when a course filter is sent);
  - empty, past-end and error states.

## 4a. Phase 3 reviews (API, frontend, security)

**API.**
- `GET` is safe and idempotent; nothing is written.
- 401 comes from `get_current_user`; 403 comes from `require_reader`.
- 422 covers every malformed value, from FastAPI types and `Literal`s plus the explicit SR8 and SR13 rules.
- It is a list endpoint, so paging and filters apply here (unlike the draft tests on non-list endpoints that CLAUDE.md warns about).
- The contract is additive: no existing response changes.

**Frontend.**
- The form has `role="search"` and a visible label on every field.
- The chips are links and carry `aria-current` on the active one.
- The table has a caption and `data-label` cells for the phone layout (the courses-page idiom).
- A failed API read renders `accessUnavailable` (403 / 401 / error).

**Security.**
- IDOR: not applicable. Readers read every university by design (U5); rows carry `permissions` from `row_out`, which is computed per
  caller.
- Role escalation: none, because the route is read only.
- Commission inference: the parameter is dropped for non-U2 roles (SR10), and a test shows that an extreme `commission_min` returns the
  same set.
- SQL injection: there is no string-built SQL. Patterns are escaped and every value is bound.
- XSS: React escapes; no HTML is rendered from data.
- CSRF: GET only, with no state change.
- Rate limiting: not added. It is an authenticated internal page, and other master lists have none (out of scope).
- Logging: reads are not logged or audited, so no PII or commission value is logged.
- `navigation.ts`:
  - set "Global University Database" `live`;
  - add it to `PARTNERSHIP_HEAD_NAV` (after University Master), `SUPER_ADMIN_NAV` ("Partnership University Search") and the
    `overseas/admin` nav.
- Tests to update: `navigation.partnership.test.ts` and the `PartnershipMenuCard` count in `PartnershipTeamTable.test.tsx`.

## 5. Acceptance criteria

| # | Criterion | Proof |
|---|---|---|
| AC1 | "Japan + Cyber Security + Not Partnered" returns exactly the Japanese universities with an active Cyber Security course that are target or in progress (not partner, not lost) | pytest fixture |
| AC2 | "UK + Business + Partnership in Progress" returns exactly the UK-region in-progress universities with a Business course | pytest, e2e |
| AC3 | "Germany + IT + Active Partner" returns exactly the German partner (G1) universities with an IT course | pytest |
| AC4 | Each of the 15 filters narrows correctly; course filters apply to one course (SR7); a course with several intakes matches each month | pytest |
| AC5 | Commission filter works for super_admin / manager / head; for overseas_admin it is ignored (same results as without it) and the page shows no commission field | pytest, vitest, browser |
| AC6 | Non-readers (counselor, BDM, student) → 403; anonymous → 401; bad values (region, level, month, tuition bound without currency, min > max, expected from > to, manager) → 422 | pytest |
| AC7 | Paged `{items,total,limit,offset}` + partner-status facet counts computed without the partner-status filter | pytest |
| AC8 | A fixed query count at 1,300 universities × 3 courses, within the time budget | pytest |
| AC9 | The page holds filters in the URL, shows chips with counts, empty / past-end states, paging; menu entry is live for managers, heads, super_admin, overseas_admin | vitest, e2e, browser (desktop / tablet / mobile) |
| AC10 | `/partnership/universities/{id}` and the master list are unchanged (route order) | existing upc-003 tests |

## 6. Tasks (TDD, in order)

1. API tests (RED): `test_upc_024_search.py`. It covers the examples, each filter, roles, validation, facets and the commission rule. Then
   the service, schema and route (GREEN).
2. Performance test: query count and budget.
3. Web: `lib/universitySearch.ts` and the page, with a vitest test (`UniversitySearchPage.test.tsx`). Then the nav, and the nav and
   menu-count tests.
4. e2e `upc-024-global-university-search.spec.ts`: a head searches "UK + Business + Partnership in Progress", the chips, paging and
   mobile.
5. Docs: DEC-SCOPE-162, API §12CD, RBAC §2.88, SCREEN_CATALOG, the backlog status, and the QA notes in this spec.

## 7. Regression set (lite)

`test_upc_003_*`, `test_upc_017_courses.py` and `test_upc_001_access.py`. Web: the navigation tests, `PartnershipTeamTable.test.tsx` and
the new page test.

## 8. QA (Phase 5, 2026-10-10, `upc024` stack on :13024)

The exploratory pass ran headless Chromium against the production build. It covered:
- roles: head, manager, overseas_admin, counselor and signed-out;
- searches: the 3 source examples and the intake, tuition, commission, ownership and ranking filters;
- states: the 422 and conflicting-filter messages, filtered empty, past the end;
- navigation: paging, Back, Refresh, the chips, Clear, a double submit and Enter;
- layout and errors: tablet (820 px) and mobile (390 px), broken images, console and network errors.

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| QA24-01 | Medium | After a chip, Clear or paging click (Next's client navigation), the uncontrolled form fields kept their old values. The next Search re-sent a stale filter, e.g. the old partner status | Fixed: the form is keyed on the search. Vitest regression test, red then green. Re-run 36/36 |
| QA24-02 | Low | One React #418 (hydration) `pageerror` on the first head load | Not reproduced in 15 further loads across `/partnership/search`, `/courses`, `/universities` and `/performance`, nor in the full re-run. It matches the intermittent production-only #418 seen earlier on unchanged partnership list pages (upc-010 notes). Not caused by this item |

Cosmetic follow-ups (not defects):
- At 1366 px the native Partner status select truncates "Partnership in progress".
- On a phone the 20-field form comes before the results. A collapsible "More filters" group could help.

e2e: `upc-024-global-university-search.spec.ts` passes 1/1.
