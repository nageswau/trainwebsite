# PUB-023 — Country flags (phase 1) — Design

**Status:** design approved in conversation on 2026-10-14 (sections 1 and 2). This written spec is
awaiting the owner's review.
**Feature ID:** `PUB-023`. Phase 2 will get its own Feature ID later.
**Decision:** `DEC-SCOPE-222` (F1–F5 below).
**API contract:** §12EJ. **RBAC:** no change. **Migration:** none.
**Branch:** `feature/pub-023`, worktree `../pub-023`, cut from `main` @36d4c9cb.

## 1. Intent

The owner asked on 2026-10-14 to show each country's flag wherever a country is shown, so that
destinations are recognisable at a glance. They asked for this on the public site, the student and
agent portals, and the admin and staff screens.

Success means:
- a flag appears next to the country name on the screens in §3.1;
- nothing breaks or looks broken where no flag is available;
- no third-party request is made;
- screen-reader output is unchanged.

## 2. Owner answers (`DEC-SCOPE-222`)

| # | Question | Answer |
|---|---|---|
| F1 | Where | All four areas: public site, student and agent portals, admin and staff. Delivered in **two phases**: PUB-023 is phase 1 (§3.1); phase 2 is a later Feature ID (§3.3) |
| F2 | Image source | **Bundled SVG set**: flag-icons (MIT), served from our own `/flags/` path. Emoji flags are rejected (Windows shows letters) and so is an external CDN (privacy and uptime) |
| F3 | No flag available | **Show nothing**: name only, layout unchanged. The public country cards keep their existing 🌍 as the fallback |
| F4 | Accessibility | The flag is **decorative** (`alt=""`, `aria-hidden="true"`). The country name is always shown beside it |
| F5 | Exclusions | Native `<select>` dropdowns (browsers can't render images in `<option>`), and free-text country fields (there is no ISO code) |

F4 and F5 were presented as part of the design and approved with it. They are not separate
questions.

## 3. Scope

### 3.1 Phase 1 (this feature)

`iso2` is available today, or after §5's API additions.

| Area | Screen | File | Size |
|---|---|---|---|
| Public | Countries list cards: flag replaces 🌍; 🌍 stays when no flag | `apps/web/app/overseas/countries/page.tsx` | large |
| Public | Country detail heading | `apps/web/app/overseas/countries/[slug]/page.tsx` | large |
| Public | Overseas home destination cards | `apps/web/app/overseas/page.tsx` | inline |
| Public | Course cards (country line) | `apps/web/app/overseas/courses/page.tsx` | inline |
| Agent | Partner universities panel (two places) | `apps/web/components/AgentPartnerUniversitiesPanel.tsx` | inline |
| Agent | Shortlist cards: catalogue universities only. The country comes from `/public/countries` | `apps/web/components/AgentShortlistForm.tsx` → `AgentShortlistCard.tsx` | inline |
| Admin | University table | `apps/web/components/UniversityTable.tsx` | inline |
| Admin | University match list | `apps/web/components/UniversityMatchList.tsx` | inline |
| Admin | Partnership search | `apps/web/app/partnership/search/page.tsx` | inline |
| Admin | University detail | `apps/web/app/partnership/universities/[id]/page.tsx` | inline |
| Admin | University view | `apps/web/components/UniversityView.tsx` | inline |
| Admin | Partnership map: country table | `apps/web/app/partnership/map/page.tsx` | inline |
| Admin | Global dashboard: country rows | `apps/web/app/partnership/head/global-dashboard/page.tsx` | inline |
| Admin | Country picker: a custom `SearchableSelect`, so a flag can go on each option | `apps/web/components/UniversityForm.tsx` → `SearchableSelect.tsx` | inline |

The implementation plan confirms the exact line in each file. Each screen only gains the flag; its
text, order and layout are otherwise unchanged.

### 3.2 Not in scope (F5)
- **Native `<select>` dropdowns.** Examples are the agent shortlist country filter and the
  course-search "Country" filter.
- **Free-text country fields** have no ISO code:
  - agency universities (`lib/agentShortlist.ts`);
  - student preferences (`AgentStudentDetailPanel`, `AgentStudentsPanel`,
    `AgentStudentCounselingCard`, `CareerPreferencesCard`);
  - organisation country (`AgentNetworkRecords`, `BdmOrganizationProfileDetails`,
    `RecruiterCompanyDetail`);
  - the raw import preview (`UniversityImportPanel`).
- **Shortlist cards for agency universities** stay without a flag. Their country is free text.
- **Country master editing.** No screen creates or edits countries; flags come only from `iso2`.

### 3.3 Phase 2 (later, own Feature ID)
These screens show a country **name** returned by their own API. Each API needs an `iso2` field
first:
- management: `ManagementUniversities`, `ManagementApplications`, `ManagementAbroadRevenue`;
- partnership: courses, opportunities, performance, expected revenue, pipeline board, and the
  global dashboard university rows;
- visits and meetings forms and tables;
- agreements and commission-term forms;
- BDM organisation detail;
- the generic `admin/[module]` country column;
- agent dashboard, commission report and report filters;
- visa checklist.

This list is recorded in `PUBLIC_SITE_BACKLOG.md` as a follow-on item. It is not built here.

## 4. Assets

- **Source:** the 4:3 SVGs from [flag-icons](https://github.com/lipis/flag-icons) (MIT). The exact
  release is recorded in `apps/web/public/flags/README.md` when the files are copied.
- **Location:** `apps/web/public/flags/<code>.svg`, with a lower-case ISO 3166-1 alpha-2 file name.
  Copy every file in the set, not just the visible countries: admin screens show all ~250 ISO
  countries that migration 0101 created. Non-country extras in the set (for example `eu`, `un`, and
  sub-national `gb-eng`) are not copied.
- **Licence:** add `apps/web/public/flags/LICENSE` (the MIT text from flag-icons) and the
  `README.md` above (source, release, copy date).
- **Size:** about 1 MB in the repo. The files are static and cached by the browser, and only the
  flags on screen are fetched (`loading="lazy"`).
- **Build:** `/public` is already copied into the web image. `apps/web/Dockerfile.dockerignore`
  excludes tests only, so it needs no change. The plan confirms this.

## 5. API changes

All three are read-only and additive. They need no route, permission or migration change.

| Endpoint | Change | Source |
|---|---|---|
| `GET /api/v1/public/countries`, `GET /api/v1/public/countries/{slug}` (its `country` object) | `CountryOut` gains `iso2: str \| None` | `Country.iso2` |
| `GET /api/v1/public/overseas-courses` | each row gains `country_iso2: str \| None`, beside the existing `country` name | the course's country's `iso2` |
| `GET /api/v1/lookups/countries` | each row gains `iso2: str \| None`. `label` and `detail` are unchanged | `Country.iso2` |

- These go into `docs/architecture/API_CONTRACT.md` as a new **§12EJ**.
- Public endpoints stay unauthenticated, and the lookup keeps its current role check.
- The field is nullable because `Country.iso2` is nullable. Ad-hoc test rows may have none, and F3
  then applies.

## 6. Web changes

### 6.1 `CountryFlag` (new: `apps/web/components/CountryFlag.tsx`)
```tsx
<CountryFlag iso2={country.iso2} size="inline" />   // 20×15
<CountryFlag iso2={country.iso2} size="large" />    // 40×30
```
- It renders
  `<img className="country-flag country-flag--{size}" src="/flags/{code}.svg" alt="" aria-hidden="true" width height loading="lazy" decoding="async">`.
  `{code}` is the trimmed `iso2` in lower case.
- **Guard:** it renders nothing (`null`) unless `iso2` matches `/^[A-Za-z]{2}$/`. This covers F3
  and keeps any other text out of the URL.
- It is a plain server-safe component, with no `"use client"`, state or effects. That keeps the
  public pages server-rendered. A missing asset is prevented by the coverage script in §7, not by a
  runtime `onError`.
- It uses a plain `<img>` (not `next/image`, which would need `dangerouslyAllowSVG`). This matches
  `UniversityLogo.tsx`, including its eslint-disable comment.
- CSS in `globals.css`:
  - `.country-flag` is inline-block, sits on the text baseline, has a small gap after it, a 2px
    radius and a hairline border so white flags stay visible;
  - the size modifiers set the width and height.

### 6.2 Types
- `lib/types.ts`: `Country` gains `iso2?: string | null`.
- The public course row type gains `country_iso2?: string | null`.
- `SearchableSelect`: the option type gains an optional `iso2`. When it is present, the option and
  the selected value show `<CountryFlag size="inline">` before the label. Other lookups don't set
  it, so they are unchanged.
- The country lookup mapping used by `UniversityForm` passes `iso2` through.

### 6.3 Screens
- Each screen in §3.1 renders `<CountryFlag>` immediately before the existing country name.
- Countries list cards: if the country has a valid `iso2`, the flag takes the `icon-circle`
  position; otherwise the existing 🌍 stays (F3).
- Agent shortlist: the catalogue country map (`id → name`) becomes `id → {name, iso2}`, so that
  catalogue-university cards can show the flag.

## 7. Testing

The tests follow the project's rules: real runs, lite backend set and touched web tests for this
feature, and the full suite run by the owner.

- **pytest** (new `apps/api/tests/test_pub_023_country_flags.py`):
  - `/public/countries` rows and `/public/countries/{slug}` → `country.iso2` equal the stored code;
  - `/public/overseas-courses` rows carry `country_iso2`;
  - `/lookups/countries` rows carry `iso2` for an allowed role, and the existing role refusal is
    unchanged.
- **Asset coverage script** (new `scripts/check_flag_assets.py`):
  - **What it checks:** every code in migration 0101's `ISO_COUNTRIES` has
    `apps/web/public/flags/<code lower>.svg`.
  - **How:** it reads the migration with `ast` (not by importing it) and lists the flags directory.
  - **Output:** it exits non-zero and names each missing code.
  - **Why a script:** the CI containers are isolated (`api-test` sees only `apps/api`, `web-test`
    only `apps/web`), so no pytest or vitest test can see both. It runs from the repo root with
    `python scripts/check_flag_assets.py`, at verification and before each merge.
- **vitest:**
  - `CountryFlag`:
    - `"GB"` → `src="/flags/gb.svg"`, `alt=""`, `aria-hidden="true"`;
    - `null`, `""`, `"G1"`, `"GBR"` and `"../x"` render nothing;
    - each size gives its width and height.
  - **Asset sanity:** every file in `public/flags` is `<two lower-case letters>.svg`. The files
    for the six published destinations (`gb`, `au`, `us`, `ae`, `fr`, `de`) exist.
  - `SearchableSelect` shows a flag only for options with `iso2`.
  - The countries page and a partner-universities panel render the flag next to the name.
  - Existing mocks that build `Country` or course rows get `iso2` and `country_iso2` where needed,
    for example `AgentShortlistForm.test.tsx`.
- **Playwright** (extend `apps/web/tests/e2e/upc-002-country-master.spec.ts`):
  - `/overseas/countries` shows a flag `img` inside each visible country card;
  - `/overseas/countries/united-kingdom` shows `/flags/gb.svg` in the heading;
  - the flag image loads with HTTP 200.

## 8. Documentation and traceability

- `PRODUCT_DECISION_REGISTER.md`: `DEC-SCOPE-222` with F1–F5.
- `API_CONTRACT.md`: §12EJ.
- `PUBLIC_SITE_BACKLOG.md`:
  - a status row for `PUB-023` (phase 1);
  - a new backlog item for phase 2 listing §3.3.
- `docs/quality/PUB-023_EXPLORATORY_QA_2026-10-14.md`: the QA run on the dev stack.
- RTM row per the project's usual convention.

## 9. Rollout

1. Build and test on `feature/pub-023`.
2. PR → merge to `main`.
3. Deploy to dev, then to prod (`edusphere.org.uk`) using the prod setup guide's deploy command. No
   data step is needed: prod countries already carry `iso2` from migration 0101.

## 10. Risks

| Risk | Mitigation |
|---|---|
| A country code without an SVG gives a broken image | `scripts/check_flag_assets.py` against migration 0101's list, plus the Playwright image-load check |
| A white or very light flag is invisible on a white card | Hairline border on `.country-flag` |
| Repo size (+~1 MB) | Static, cached and lazy-loaded. It is acceptable next to the existing logo assets |
| Name and flag announced twice by screen readers | Decorative image (`alt=""`, `aria-hidden`) |
