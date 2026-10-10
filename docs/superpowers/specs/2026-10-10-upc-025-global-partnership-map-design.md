# upc-025 — Global partnership map — design

- **Feature:** upc-025 (`docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-025; EVID-020 §2 L35–L90; Appendix B G1–G4; U12)
- **Decision:** `DEC-SCOPE-164`. **No migration.** API §12CF; RBAC §2.90. As with earlier items, these numbers are provisional until merge.
- **Branch:** `feature/upc-025` (worktree branch `worktree-upc-025`), taken from `origin/main` @ `e99db53c`.
- **Dependencies:** all merged on main:
  - upc-002 (#145): ISO-2 code and region on every country.
  - upc-007 (#159): the stored stage and its G grouping.
  - upc-024 (#221): the Global University Database (`services/university_search.py`), the click-through target.
- **Evidence:**
  - EVID-020 §2 (`DERIVED_BLUEPRINT`).
  - Backlog U12 (`EXPLICIT_APPROVAL`): an inline SVG map from public-domain shapes keyed by ISO code, with no new npm dependency; counts
    on hover or focus; a click opens the country list; an accessible table alongside.
  - Backlog U7: fixed groupings.
  - Backlog U2: commission only for U2 roles.
- **Status of answers:** the owner told this session to proceed with the recommended answers. MP1–MP14 below are those recommendations.
  They are `NEEDS_CONFIRMATION` at sign-off, not `EXPLICIT_APPROVAL`. Q-32 (map colour) and Q-07 (exclusivity) are among them.

## 1. Understanding

§2 asks for a **Global University Partnership Map**, which the source calls "one of the most important features". It visually displays
universities by country. Each country shows four counts:
- 🟢 Partner;
- 🟡 Partnership in Progress;
- 🔵 Target;
- 🔴 Lost/Closed.

Clicking a country opens its university list. The map has 12 filters: country, region, partner status, partnership stage, university
type, ranking, courses, priority, partnership manager, expected partnership date, active/inactive and exclusive/non-exclusive.

The source's UK 15 / 8 / 12 / 3, Germany and Japan figures are illustrative, not seed data.

Backlog acceptance criteria:
1. Counts per country equal the list totals.
2. Keyboard users can reach every country.
3. The table view shows identical data.

## 2. Recommendations (MP1–MP14)

| # | Question | Recommended answer (used) |
|---|---|---|
| MP1 | Readers | The University Master readers, as upc-024 SR1 (`require_reader`): `partnership_manager` (with a profile), `partnership_head`, `overseas_admin` (overseas division), `super_admin`. Every other role gets a 403; anonymous gets a 401. The map shows nothing those readers cannot already see in the search facets. |
| MP2 | Which universities | **Exactly the set the search would list for the same filters** (upc-024 SR2: every university, whoever owns it; active only by default). That parity is what makes AC1 hold, so the map does not use Appendix B's "caller's scope" wording; a manager narrows with *Partnership manager = Assigned to me*. |
| MP3 | One filter builder | The map and the search share `university_search.filters()`: the map takes the same query parameters (`UniversityFilterQuery`, the search query without paging), so a country link to the search with the same filters plus `iso2` lists exactly the counted universities. |
| MP4 | Exact country (`iso2`) | A new **search** filter `iso2` (two letters, case-insensitive, exact match on `countries.iso2`). The existing `country` text filter matches name substrings or the code, so `IN` would also match Finland and "Niger" would match Nigeria; it cannot be the click target. `iso2` is additive; `country` is unchanged. |
| MP5 | Partnership stage (§2 L74) | New filter `stage`: one of the 15 stored stage keys (upc-007). It matches the stored stage, lost or not; combine with partner status to exclude lost. |
| MP6 | Priority (§2 L82) | New filter `priority`: `A`, `B` or `C` (upc-003). |
| MP7 | Active / inactive (§2 L88) | New filter `activity`: `active` (the default, today's behaviour), `inactive` or `all`. The search gains it too, so a map of inactive universities links to a list of the same rows. |
| MP8 | Exclusive / non-exclusive (§2 L90, Q-07) | New filter `exclusivity`: `exclusive` = the university has at least one in-force agreement (`IN_FORCE`: signed/active, upc-014) that is exclusive; `non_exclusive` = it has an in-force agreement and none of them is exclusive. A university with no in-force agreement matches neither. The two values never overlap. Exclusivity is not commercial data, so all readers may use it. |
| MP9 | The other §2 filters | Country (`iso2`, or the `country` text), region, partner status (SR11 values), university type, ranking (`ranking_max` + `ranking_system`), courses (`course` + `level`), partnership manager (`manager`) and expected date (`expected_from`/`expected_to`) are the upc-024 filters, unchanged. The map form offers these 12 groups. The API also accepts the other search filters (city, tuition, intake, scholarship; commission for U2 roles only, dropped otherwise as SR10), so a filtered map stays in step with a filtered search. |
| MP10 | Response | `GET /partnership/universities/map` (the backlog says `/partnership/map`; it sits beside upc-024's `/search` on the same router, so `main.py` is not touched) → `{countries, totals, stages}`. `countries`: one row per country with at least one matching university, as `{iso2, name, region, partner, in_progress, target, lost, total}`, ordered by name. `totals`: the same four counts plus `total` over all countries. `stages`: the stage catalogue `[{key, label}]` for the stage filter. One grouped query (country × lost flag × stage). |
| MP11 | Colour per country (Q-32) | The **best** status present wins: 🟢 when the country has at least one partner, else 🟡 when at least one in progress, else 🔵 when at least one target, else 🔴 (only lost). Countries with no matching university are neutral grey. The legend states the rule. Colour is never the only signal: every country link's accessible name and the table carry all four counts. |
| MP12 | Map shapes | Natural Earth 1:50m Admin 0 countries (public domain), keyed by `ISO_A2_EH` (which fixes NE's `-99` codes for France, Norway and Kosovo). An equirectangular projection on a 1000 × 400 view box (latitude 84° N to 60° S, so Antarctica is not drawn), with coordinates rounded to 0.1. The paths are generated once by `scripts/build_world_map.py` into `apps/web/lib/worldMapShapes.ts`, which is committed. No npm dependency, and the file stays under the 300 KB budget. |
| MP13 | Small countries | A country whose shape is smaller than 6 × 6 view-box units (Singapore, Malta, Bahrain, …) is drawn with a circle marker at Natural Earth's label point, so it can be seen, hovered and focused. A matching country with **no** shape in the set appears in the table and is counted in a "not drawn on the map" note. |
| MP14 | Interaction and page | `/partnership/map` "Global Partnership Map". A plain GET filter form (URL-held, as upc-024); a legend with totals; a **Map / Table** switch (links, `view=table`, which keep the filters).<br>• The map is server-rendered SVG. Each country with at least one university is an SVG `<a>` link to the search (`iso2` + the same filters), so it is in the tab order and opens on Enter or a click. Its accessible name reads e.g. "United Kingdom: 15 partner, 8 in progress, 12 target, 3 lost". Countries with none are decorative.<br>• A small client component shows the four counts in a panel on hover or focus, reading them from the link's `data-*` attributes (event delegation), so the shapes stay out of the client bundle.<br>• The table lists the same rows: Country (link to the same search), Region, the 4 counts and Total, with a totals row.<br>• The §32 "Global Partnership Map" entry goes live for managers. Heads and `super_admin` get a nav entry, and so does the `overseas/admin` nav ("Partnership Map"), as the search did. |

## 3. Backend

- `schemas.py`:
  - `UniversityFilterQuery` holds every search filter plus the new `iso2`, `stage`, `priority`, `activity` and `exclusivity` fields.
  - `UniversitySearchQuery(UniversityFilterQuery)` adds `limit` and `offset`. The search contract is unchanged; the new fields are
    additive and optional.
  - `PartnershipMapCountry`, `PartnershipMapTotals` and `PartnershipMapPage` describe the response.
- `services/university_search.py`:
  - `filters()` gains the new conditions. The fixed `University.active.is_(True)` becomes the `activity` rule, whose default is
    unchanged.
  - The partner-status grouping moves into `_status_counts`, which both the search facet and the map use.
  - New `country_counts(db, user, query) -> dict` runs one grouped query plus the stage catalogue.
- Route `GET /partnership/universities/map` in `api/partnership_universities.py`, declared before `/{university_id}`. It calls
  `require_reader` and then `country_counts`. There is no new router, so `main.py` does not change.
- Every value is a bound parameter. `iso2` is validated against `^[A-Za-z]{2}$`; `stage` against `STAGE_KEYS`.
- The rows carry no commission value.

## 4. Frontend

- `scripts/build_world_map.py` (new, run once by hand):
  - downloads nothing itself; it reads a local Natural Earth GeoJSON path given as its argument;
  - writes `apps/web/lib/worldMapShapes.ts`, `Record<ISO2, { d: string; x: number; y: number; small: boolean }>`, plus `VIEW_BOX`.
- `lib/partnershipMap.ts`:
  - the types, `MAP_PATH`, `MAP_URL` and `MAP_KEYS` (the filters that travel);
  - `mapQuery(filters)`, `mapHref(filters, changes)` and `countryHref(filters, iso2)`, a link to `SEARCH_PATH` with the shared filters
    plus `iso2`, minus `country`;
  - `colourOf(row)` (MP11) and `countLabel(row)`.
- `components/PartnershipWorldMap.tsx` (server): the SVG, with links, colours and small-country markers.
- `components/MapHoverPanel.tsx` (`"use client"`, data-only props plus children): the hover and focus panel.
- `app/partnership/map/page.tsx` (server, the search-page idiom): the form, legend, totals, the Map / Table switch, then the map or the
  table, and the empty and error states.
- The search page:
  - accepts and keeps the new keys (`iso2`, `stage`, `priority`, `activity`, `exclusivity`) in `SEARCH_KEYS`;
  - gains form fields for stage, priority, activity and exclusivity;
  - keeps `iso2` as a hidden field, shown as "Country: <name> (clear)".
- `navigation.ts`: set "Global Partnership Map" `live`; add it to the head, super_admin and overseas/admin navs.
- Tests to update: `navigation.partnership.test.ts` and the `PartnershipMenuCard` count in `PartnershipTeamTable.test.tsx`.

## 4a. Phase 3 reviews (API, frontend, security)

**API.**
- GET only: safe and idempotent, with no audit and no writes.
- 401 comes from `get_current_user`, 403 from `require_reader`, and 422 from FastAPI `Literal`s and patterns plus the inherited SR8 and
  SR13 rules (as `field` errors where the search already used them).
- **It is not a list endpoint**: there is no paging, and its size is bounded by the ~250 countries. So no paging or ETag test applies
  (the CLAUDE.md draft-test warning).
- The search contract is unchanged for existing callers, since the new filters are optional with today's defaults.

**Frontend.**
- The design language reuses `portal-content`, `action-card`, `form-grid`, `btn`, `table-wrap` and `data-label` cells.
- Keyboard:
  - SVG `<a>` elements are focusable;
  - a visible focus outline (stroke) is added;
  - the panel follows focus;
  - Map / Table are links with `aria-current`.
- Screen readers: the `<svg>` is a labelled group (`role="group"`, `aria-label="World map of university partnerships"`, not `role="img"`, which would hide the links), and each link has a name.
  The table has a caption.
- Mobile: the SVG scales to its width (`width: 100%`, `height: auto`); on narrow screens the page suggests the table. There is no
  horizontal page scroll.
- Loading: a server render with no client fetch. Empty: "No universities match these filters." Errors: `accessUnavailable` (401 / 403 /
  5xx), with a 422 shown as a form error.

**Security.**
- IDOR: not applicable. The same readers read the same rows as the search (U5).
- Commission inference: `commission_min` is dropped for non-U2 roles before any SQL (shared with the search), and a test covers it.
- Exclusivity is agreement metadata, not commission (MP8).
- SQL injection: there is no string-built SQL. XSS: React escapes; the SVG paths are static, generated constants, never user data.
- CSRF: not applicable (GET).
- Rate limiting: none, as with the other master reads.
- No logging of filter values.

## 5. Acceptance criteria

| # | Criterion | Proof |
|---|---|---|
| AC1 | For every country row, partner / in_progress / target / lost equal the search's facet for the same filters + `iso2`, and `total` equals the search `total` | pytest (parity loop), e2e |
| AC2 | Every country with at least one university is a focusable link with its four counts in its accessible name; small countries get a marker | vitest, e2e (Tab), browser |
| AC3 | The table view shows the same countries and counts as the map, plus the same totals | vitest, e2e |
| AC4 | Each of the 12 §2 filters narrows the counts, including the new stage, priority, activity and exclusivity | pytest |
| AC5 | Colour follows MP11 (mixed partner and lost is green; only lost is red; none is grey) | vitest |
| AC6 | Non-readers get a 403, anonymous gets a 401, and bad values (iso2, stage, priority, activity, exclusivity, region) get a 422; commission is ignored for overseas_admin | pytest |
| AC7 | One grouped query whatever the number of universities (1,300 seeded) | pytest |
| AC8 | The new search filters (`iso2`, `stage`, `priority`, `activity`, `exclusivity`) work, and existing search results are unchanged without them | pytest (upc-024 suite) |
| AC9 | The page keeps filters in the URL, has the Map / Table switch, and a click goes to the filtered search; the menu entry is live; layout works on desktop, tablet and mobile; the shapes file is < 300 KB | vitest, e2e, browser |

## 6. Tasks (TDD, in order)

1. API tests (RED) in `test_upc_025_map.py`: parity, filters, roles, validation, colour inputs and the query count. Then the schema split,
   filters, `country_counts` and route (GREEN). Re-run `test_upc_024_search.py`.
2. Shapes: download Natural Earth 50m into the scratchpad and run `scripts/build_world_map.py`. Check the size and that the ISO set
   covers the seeded countries.
3. Web: `lib/partnershipMap.ts` and its unit tests (RED, then GREEN); the map component, hover panel and page, with
   `PartnershipMapPage.test.tsx`; the search page's new keys, with an updated `UniversitySearchPage.test.tsx`; then the nav and its tests.
4. e2e `upc-025-global-partnership-map.spec.ts`: a head filters the map, reads the counts, tabs to a country, opens the table, and clicks
   through to the search; then on mobile.
5. Docs: DEC-SCOPE-164, API §12CF, RBAC §2.90, SCREEN_CATALOG, backlog status, and the QA notes in this spec.

## 7. Regression set (lite)

API: `test_upc_024_search.py`, `test_upc_003_*` (the list) and `test_upc_001_access.py`. Web: the navigation tests,
`PartnershipTeamTable.test.tsx`, `UniversitySearchPage.test.tsx`, and the new tests.
