# nehn-034 — Country visual cards (design + plan)

Source: `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-034` (an `UNVERIFIED` derived backlog; no hard dependency).
The owner pre-authorised the builder's recommended answers; every open question below is the builder's call and stays
`NEEDS_CONFIRMATION` (recorded as `DEC-SCOPE-284`).

## Intent

A student (or visitor) choosing where to study sees each destination as a card: flag, name, a short description, how many
universities EduSphere lists there, and a "View universities" button that lands on that country's universities. The same card appears
in the overseas student portal, and the student's apply form starts with a country choice.

## What exists (Phase 1)

- `GET /public/countries` returns `CountryOut` (with `iso2`, PUB-023). No university count.
- `GET /public/universities?country=<slug>` already filters by country (published, active only — `public_visible()`).
- `/overseas/countries` renders inline cards (flag, name, overview, tuition, "Country guide"). `/overseas/universities` ignores any
  query string.
- The student portal has no country browsing; `OverseasApplyPanel` lists every university in one select.
- `Country` has no image column; flags are bundled `/flags/<iso2>.svg` (`CountryFlag`).

## Decisions (builder's defaults)

- **C1** `CountryOut.university_count: int` (additive, default 0) on the list and the detail payload: the number of
  `public_visible()` universities, by one `GROUP BY` query (no N+1). Unpublished/inactive universities are not counted.
- **C2** A country with 0 universities stays listed; its card shows a "Coming soon" badge instead of the count and has no
  "View universities" button (hiding would remove country guides that exist today).
- **C3** "View universities" → `/overseas/universities?country=<slug>`. That page passes `country` to the API and shows
  "Showing universities in <Country>" with an "All universities" link. An unknown slug shows the normal empty state (the list API
  returns `[]`); `GET /public/countries/<unknown>` stays 404.
- **C4** One server-safe `CountryCard` component (data-only props, no functions) used by the public page and the portal.
  Fallback icon 🌍 when there is no valid `iso2`. Keeps the existing "Country guide" link and tuition line.
- **C5** Student portal: new nav item **Explore Countries** (`/overseas/student/explore-countries`). The portal payload for that
  section is header-only (the agent Universities precedent) and still gates the page; PortalPage mounts the card grid from the public
  list. In the portal each card with universities also offers **Apply** → `/overseas/student/applications?country=<slug>`.
- **C6** `OverseasApplyPanel` gains a first field **Country** (`All countries` + countries with ≥1 university). Choosing one narrows
  the university select to that country and clears a university from another country. `?country=<slug>` preselects it. Default "All
  countries" keeps today's behaviour (OVS-002 e2e unaffected).
- **C7** Not in this item: custom country images (no column; needs a migration and client assets), the rest of `psb-019`, agent-portal
  changes (agents already use the public pages), response caching (one extra grouped query).

No migration. No auth change: the public routes stay public; the portal section stays `overseas_student`-only via the portal gate.

## Plan (TDD, one slice at a time)

1. API: test `university_count` (published counted; unpublished/inactive/other-country not; 0 for empty; detail carries it) → add
   field + grouped count in `public.py`.
2. API: test portal `GET /portal/overseas/student/explore-countries` → 200 header-only for the student, 403 for another role → add
   the section in `services/portal.py`.
3. Web: `CountryCard` vitest (flag/fallback, count text singular/plural, Coming soon, links, Apply only when `applyHref`) → component;
   use it in `countries/page.tsx`; type field.
4. Web: universities page `?country=` (filter banner + API query).
5. Web: nav item + PortalPage mount (`StudentCountryExplorer`).
6. Web: `OverseasApplyPanel` vitest (country select filters, preselect from `?country=`, reset on change) → implement.
7. e2e `nehn-034-country-cards.spec.ts`: public card → filtered list; portal explore → apply preselect; 360/1280 screenshots.
8. Docs: DEC-SCOPE-284, API addendum, RBAC row, backlog status.

## Risks

PUB-023 e2e / country page snapshots (card markup changes); PORTAL_NAV tests; OVS-002 apply e2e (kept by C6 default).
