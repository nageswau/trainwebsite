# SEO / Social Media — Backlog (`OPS-SEO-01` … `07`, `seo-001` … `seo-012`)

NO-ASSUMPTION MODE. Prepared 2026-10-19 at the owner's request. **No business code was written for these items.** The only code
change so far is the build-arg plumbing for `OPS-SEO-01` (see its row).

## Evidence

**Source:** "EduSphere SEO SMM competitor audit" (2026-10-19), a research report produced in a Claude Code session. It is **not in
the repo** (it lives in that session's scratchpad) and is not a `docs/sources/` file. Evidence class: `DERIVED_BLUEPRINT`-style
analysis, `UNVERIFIED` until each item is accepted. Competitor observations in it are `UX_REFERENCE` only. Search-volume,
backlink, Core Web Vitals and ad-library data were **N/A** (no Semrush/Ahrefs, Search Console, PSI key or logged-in access).

Key observations it rests on (all fetched 2026-10-19, `OBSERVED` unless marked):
- https://edusphere.org.uk/robots.txt declared `Sitemap: https://example.com/sitemap.xml`, and https://edusphere.org.uk/sitemap.xml
  listed 24 URLs, all on `https://example.com`. Cause: `apps/web/app/robots.ts:2` and `apps/web/app/sitemap.ts:2` fall back to
  `"https://example.com"` when `NEXT_PUBLIC_SITE_URL` is unset at build time.
- 30 of 31 sampled public pages share one `<title>` and meta description (only https://edusphere.org.uk/it/programs differs).
- No canonical, hreflang, `og:`, `twitter:` or JSON-LD on any sampled page; no H1 on https://edusphere.org.uk/ ,
  `/it/register` or `/it/employer-register`; the UK country page H1 is `" United Kingdom"` (leading space).
- Country and university detail pages (e.g. https://edusphere.org.uk/overseas/universities/coventry-university) return 200 but are
  not in the sitemap.
- Nine CMS listing pages render 0 items (e.g. https://edusphere.org.uk/news , https://edusphere.org.uk/gallery).
- Developer placeholder copy is public (footer "should be reviewed before production launch"; `/it/contact` "Configure your
  approved WhatsApp Business provider URL/number…"); https://edusphere.org.uk/privacy and `/terms` return 404.
- No GA4 tag (`apps/web/components/Analytics.tsx` loads only when `NEXT_PUBLIC_GA_ID` is set at build time).
- `https://www.edusphere.org.uk/` TLS handshake failed from one client (re-verify).
- Brand searches for "EduSphere" returned only unrelated entities (search tool was US-based, not Google).
- All observed offices are in India (Bengaluru, Hyderabad, Tadepalligudem — `PUB-024`); the `.org.uk` domain is the only UK signal.

## Owner answers (2026-10-19)

Given by the business owner in direct answer to clarifying questions. Each is recorded here and becomes a decision only when the
item that uses it is built and its `DEC-SCOPE` entry is written in `docs/decisions/PRODUCT_DECISION_REGISTER.md`.

| # | Question | Owner answer | Still `NEEDS_CONFIRMATION` |
|---|---|---|---|
| **S1** | Target market | **India + UK.** | The live site shows India offices only. Before any **UK-facing service page, ad or hreflang** ships, the owner must supply UK service-delivery evidence: a UK address/contact, and which services (IT training, placements, overseas counselling) are actually deliverable to UK residents. Until then, UK-facing items stay blocked; India-audience pages about the UK *as a destination* are not blocked. |
| **S2** | Social platforms | **Instagram** (overseas-education students) and **LinkedIn** (IT / placements / employers) first. **YouTube Shorts** only as a pilot in days 61–90. | Handles, who posts, the approval flow, and the brand-collision check (`OPS-SEO-07`). No other platform is in scope. |

## Proposed decisions

Numbers are the next free ones on `origin/main` @ `d3f81828` (highest existing: `DEC-SCOPE-230`). They are **proposed, not
registered**. Recheck `main` and renumber before each is written, since parallel branches take numbers in merge order.

| Proposed ID | Topic | Question | Status | Blocks |
|---|---|---|---|---|
| `DEC-SCOPE-231` | Market | India + UK targeting (S1); UK service-delivery facts | Owner answered (S1); UK facts `NEEDS_CONFIRMATION` | UK-facing pages, hreflang (en-IN/en-GB), UK paid pilot, UK career-change pages |
| `DEC-SCOPE-232` | Social | Platforms (S2), handles, posting owner, approval flow | Owner answered (S2) for platforms; rest `NEEDS_CONFIRMATION` | `OPS-SEO-07`, `seo-008` `sameAs`, `seo-009` |
| `DEC-SCOPE-233` | Legal | Privacy, terms, cookie consent; jurisdiction (UK GDPR vs India DPDP) | `NEEDS_CONFIRMATION` | `seo-005`, `OPS-SEO-02` |
| `DEC-SCOPE-234` | Claims | Outcome-metric definitions, publication approval, banned-claims list, disclaimer text | `NEEDS_CONFIRMATION` | `seo-011`, `psb-011` |
| `DEC-SCOPE-235` | Site URL | Canonical host (apex vs `www`); fail-build vs fallback when `NEXT_PUBLIC_SITE_URL` is unset; non-prod hosts `Disallow: /` | `NEEDS_CONFIRMATION` | `seo-001`, `OPS-SEO-03` |
| `DEC-SCOPE-236` | Indexing | Noindex empty CMS listings vs hide them from navigation | `NEEDS_CONFIRMATION` | `seo-007` |
| `DEC-SCOPE-237` | Review markup | Any `Review` / `AggregateRating` JSON-LD eligibility | `NEEDS_CONFIRMATION` | `seo-008` (and `psb-013`) |
| — (not numbered) | Agents | Public agent-recruitment pages: yes or no | Decision first; not in this backlog | — |

## Messaging guardrails (apply to every content item, post and ad)

Compliance guidance, not legal advice. Sources: UK CAP Code s.3 (https://www.asa.org.uk/type/non_broadcast/code_section/03.html —
3.7 evidence, 3.9 omissions, 3.55–3.56 "guarantee", 3.45–3.47 testimonials) and ASCI education guidelines
(https://www.ascionline.in/wp-content/uploads/2023/05/ASCI-GUIDELINES-FOR-EDUCATIONAL-INSTITUTIONS-PROGRAMMES-AND-PLATFORMS.pdf —
cl. 1 accreditation, 3 no implied guarantee + "past record is no guarantee of future prospects", 4 no "100% placement", 5(a)/(b)/(e)
latest-year, dated rankings, placed-of-total).

1. Never say "guaranteed job, visa or admission" or "100% placement".
2. Say "placement assistance" and define what it covers.
3. Publish outcome figures only through `psb-011`, each with cohort size, period, definition and source document.
4. Footnote every asterisk.
5. Never post paid courses as job vacancies (ASA rulings: ITonlinelearning 2021, Netcom 2018).
6. Testimonials must be genuine, consented (PUB-022 model) and disclose any incentive.
7. Keep the visa disclaimer's meaning ("EduSphere is not the visa decision-maker"), rewritten as customer-facing copy.
8. No "accredited/approved/affiliated" claim without evidence; rankings name the publication and date.

## Status

| Item | Priority (suggested) | Window | `psb-` overlap | Decision | Status |
|---|---|---|---|---|---|
| `OPS-SEO-01` Prod site URL | P0 | Day 0–2 | — | 235 (host) | Code part **in progress on branch `fix/seo-site-url` @ `7eb12f69`**; owner action pending |
| `OPS-SEO-02` GA4 ID + consent | P1 | Day 0–14 | — | 233 | Not started |
| `OPS-SEO-03` `www` TLS + redirect | P1 | Day 0–7 | — | 235 | Not started |
| `OPS-SEO-04` Search Console + Bing | P1 | Day 2–7 | — | — | Not started |
| `OPS-SEO-05` Google Business Profiles | P2 | Day 14–45 | `psb-016`, `psb-004` | — | Not started |
| `OPS-SEO-06` Data access (Semrush/Ahrefs, PSI, ad libraries) | P1 | Day 0–30 | — | — (tool budget) | Not started |
| `OPS-SEO-07` Claim social handles | P2 | Day 7–21 | — | 232 | Not started |
| `seo-001` Remove example.com fallback | P0 | 0–30 | — | 235 | Not started |
| `seo-002` Metadata base, canonical, OG, unique titles | P1 | 0–30 | — | — (copy approval) | Not started |
| `seo-003` Per-item detail metadata | P1 | 0–30 | — | — | Not started |
| `seo-004` Heading hygiene | P1 | 0–30 | — | — (H1 copy approval) | Not started |
| `seo-005` Placeholder removal + privacy/terms | P1 | 0–30 | `psb-004`, `psb-014` | 233 | Not started |
| `seo-006` Dynamic sitemap | P1 | 0–30 | — | — | Not started |
| `seo-007` Noindex empty listings | P1 | 0–30 | — | 236 | Not started |
| `seo-008` JSON-LD | P2 | 31–60 | **implements `psb-013`**; closes `psb-008` FAQ part | 237, 232 | Not started |
| `seo-009` Social + NAP footer links | P2 | 31–60 | `psb-004` (phones) | 232 | Not started |
| `seo-010` UTM attribution on enquiries | P2 | 31–60 | **addendum to `psb-007`** (via `psb-006`) | — (psb-007 consent) | Not started |
| `seo-011` Compliance-phrase lint | P2 | 61–90 | **extends `psb-014`**; `psb-011` | 234 | Not started |
| `seo-012` SEO smoke test in CI | P2 | 61–90 | **fold into `psb-014` if preferred** | — | Not started |

Content work is **not duplicated here**: UK study hub and guides → `psb-012` (+ `psb-008`); city/office pages → `psb-016`; lead
tools → `psb-009`; programme syllabus/next batch → `psb-010`; verified statistics → `psb-011`. Social content (Instagram:
counsellor-led UK explainers, partner-university spotlights, consented student journeys; LinkedIn: corporate hiring and placement
process) is an SMM workstream, not a Feature ID, and follows the guardrails above.

**Numbering:** `seo-0NN` / `OPS-SEO-0N` are this backlog's item numbers. Build Feature IDs continue the `PUB-0xx` series after
`PUB-024` (check `main` before use; `PUB-011`…`PUB-021` are reserved by the draft test workbook).

**Acceptance criteria** below are written to be checked by a script (curl, pytest, vitest or Playwright) against a local or prod
build. Thresholds marked `NEEDS_CONFIRMATION` are proposals.

## Ops / config items (no business code)

#### `OPS-SEO-01` — Set the production site URL (P0)
- **Done (code part):** branch `fix/seo-site-url` @ `7eb12f69` passes `NEXT_PUBLIC_SITE_URL` and `NEXT_PUBLIC_GA_ID` as build args
  (`apps/web/Dockerfile`, `docker-compose.yml`), documents them in `.env.example` and adds a section to
  `docs/architecture/DEPLOYMENT.md`. Not yet merged.
- **Remaining (owner):** set `NEXT_PUBLIC_SITE_URL=https://edusphere.org.uk` in the prod `.env` and rebuild the web image (the value
  is inlined at **build** time; a runtime change alone does nothing).
- **AC1:** Given the rebuilt prod web image, When `curl -s https://edusphere.org.uk/robots.txt`, Then it contains
  `Sitemap: https://edusphere.org.uk/sitemap.xml` and no `example.com`.
- **AC2:** When `curl -s https://edusphere.org.uk/sitemap.xml | grep -c example.com`, Then the count is `0` and every `<loc>` starts
  with `https://edusphere.org.uk/`.
- **Depends on:** merge of `fix/seo-site-url`. **Decision:** apex (not `www`) as canonical host → `DEC-SCOPE-235`.

#### `OPS-SEO-02` — GA4 measurement ID
- **Where:** prod `.env` `NEXT_PUBLIC_GA_ID` (build arg from `OPS-SEO-01`), consumed by `apps/web/components/Analytics.tsx`.
- **AC:** Given the rebuilt image, When `curl -s https://edusphere.org.uk/ | grep -o 'googletagmanager.com/gtag/js?id=G-[A-Z0-9]*'`,
  Then exactly one match. If consent is required: a Playwright check that the tag loads only after the consent action.
- **Decision:** cookie consent for UK and India visitors → `DEC-SCOPE-233` (`NEEDS_CONFIRMATION`). A consent banner, if required,
  is a code item that does not exist yet.

#### `OPS-SEO-03` — `www` TLS and single redirect
- **AC:** When `curl -sI https://www.edusphere.org.uk/`, Then the handshake succeeds and the response is 301/308 with
  `Location: https://edusphere.org.uk/`; And `curl -sI http://edusphere.org.uk/` is 301/308 to https.
- **Note:** the failure was seen from one client; re-verify before changing the Caddy config. **Decision:** `DEC-SCOPE-235`.

#### `OPS-SEO-04` — Google Search Console and Bing Webmaster Tools
- **AC:** dated screenshots under `docs/evidence/` show the GSC Domain property verified, sitemap status "Success", and the discovered
  URL count equal to the `<loc>` count from curl; the same for Bing.
- **Depends on:** `OPS-SEO-01`.

#### `OPS-SEO-05` — Google Business Profiles for the three offices
- **AC:** dated listing URLs under `docs/evidence/`; name, address and phone match `/contact` exactly.
- **Depends on:** real phone numbers (`psb-004` open question); whether the offices are walk-in centres (`psb-016`,
  `NEEDS_CONFIRMATION`).

#### `OPS-SEO-06` — Data access
- Semrush or Ahrefs exports (UK and IN locales), a PSI API key, dated Meta/Google/LinkedIn ad-library screenshots, a logged-in social
  audit. **AC:** export files and screenshots stored under `docs/evidence/` with dates; KPI baselines recorded. **Depends on:** tool
  budget (owner).

#### `OPS-SEO-07` — Choose and claim social handles
- Instagram + LinkedIn (S2); YouTube handle reserved only if the day 61–90 Shorts pilot goes ahead.
- **AC:** profile URLs recorded under `docs/evidence/`; each passes a brand-collision check (no confusion with the unrelated
  "EduSphere" entities); bios carry one free-consultation CTA with a UTM link and **no outcome numbers** until `psb-011`.
- **Decision:** `DEC-SCOPE-232`.

## Code items

#### `seo-001` — Remove the silent example.com fallback (P0, 0–30)
- **Files:** `apps/web/app/robots.ts`, `apps/web/app/sitemap.ts`; a new shared helper (proposed `apps/web/lib/site.ts`).
- **AC1:** Given `NEXT_PUBLIC_SITE_URL` unset and `NODE_ENV=production`, When a vitest test calls the helper, Then it throws (or
  returns the approved origin, per decision) and never returns `example.com`.
- **AC2:** Given `NEXT_PUBLIC_SITE_URL=https://edusphere.org.uk`, When vitest calls `robots()` and `sitemap()`, Then
  `robots().sitemap === "https://edusphere.org.uk/sitemap.xml"` and every `sitemap()[i].url` starts with that origin.
- **AC3 (if decided):** Given a non-production host, Then `robots()` returns `Disallow: /`.
- **Depends on:** `OPS-SEO-01`. **Decision:** `DEC-SCOPE-235`.

#### `seo-002` — Metadata base, canonical, OG/Twitter, unique per-page titles (P1, 0–30)
- **Files:** `apps/web/app/layout.tsx` (`metadataBase`, default `openGraph`, `twitter`, `alternates.canonical`); `export const
  metadata` in each static public `page.tsx` under `apps/web/app/` (`page.tsx`, `contact`, `faq`, `gallery`, `search`, `news`,
  `it/*`, `overseas/*`).
- **AC1:** Given a running build, When a script visits every `sitemap.xml` URL, Then each `<title>` and `meta[name=description]` is
  unique and none equals the root default except `/`.
- **AC2:** Then each page has exactly one `link[rel=canonical]` equal to its own absolute URL, plus `og:title`, `og:url`, `og:type`.
- **AC3:** titles 30–65 chars, descriptions 70–160 chars (`NEEDS_CONFIRMATION`).
- **Depends on:** `seo-001`. **Decision:** per-page copy approved by the owner.

#### `seo-003` — Per-item metadata for detail routes (P1, 0–30)
- **Files:** `generateMetadata` in `apps/web/app/overseas/countries/[slug]/page.tsx`, `overseas/universities/[slug]/page.tsx`,
  `news/[slug]/page.tsx`, `it/career-paths/[slug]/page.tsx`, `it/real-projects/[slug]/page.tsx`, `overseas/events/[id]/page.tsx`,
  `it/webinars/[id]/page.tsx`, `it/success-stories/[id]/page.tsx`; follow `apps/web/app/it/programs/[slug]/page.tsx`. Data from
  the detail endpoints in `apps/api/app/api/public.py`.
- **AC1:** Given `coventry-university`, When `curl /overseas/universities/coventry-university`, Then the title contains the
  university name, differs from the site default, and the canonical is that URL.
- **AC2:** Given an unknown slug, Then HTTP 404 (not 200 with default metadata).
- **Depends on:** `seo-002`.

#### `seo-004` — Heading hygiene (P1, 0–30)
- **Files:** `apps/web/app/page.tsx` (add H1), `apps/web/app/it/register/page.tsx`, `apps/web/app/it/employer-register/page.tsx`,
  `apps/web/app/overseas/countries/[slug]/page.tsx` (flag spacing).
- **AC:** Given those URLs and every sitemap URL, When Playwright counts `h1`, Then exactly 1, and `h1.textContent` matches `^\S`.
- **Decision:** homepage H1 wording approved by the owner; no outcome claims (guardrails).

#### `seo-005` — Remove public placeholder copy; publish legal pages (P1, 0–30)
- **Files:** `apps/web/components/Footer.tsx` (placeholder line; add privacy/terms/cookie links), `apps/web/app/it/contact/page.tsx`,
  `apps/web/app/it/about/page.tsx`, `apps/web/app/overseas/about/page.tsx`, `apps/web/app/gallery/page.tsx`,
  `apps/web/app/overseas/courses/page.tsx` ("Explore seeded examples"), `apps/web/app/overseas/visa-services/page.tsx` (rewrite the
  internal note as a customer-facing disclaimer, same meaning). New: `apps/web/app/privacy/page.tsx`, `apps/web/app/terms/page.tsx`.
- **AC1:** Given the banned-string list (`production launch`, `Configure your approved`, `Admin panel`, `S3 storage`,
  `seeded examples`, `CMS-managed`, `Publish only verified`), When a script fetches every sitemap URL, Then none appears.
- **AC2:** When `curl -sI /privacy` and `/terms`, Then both 200; and the footer on `/` links to both.
- **Depends on:** legal text from the owner. The real WhatsApp/phone values belong to `psb-004`; until then the `/it/contact`
  placeholder is removed, not replaced with a guessed number.
- **Decision:** `DEC-SCOPE-233`.

#### `seo-006` — Dynamic sitemap (P1, 0–30)
- **Files:** `apps/web/app/sitemap.ts` (async); slugs from the public list endpoints in `apps/api/app/api/public.py` (countries,
  universities, programs, posts, career paths, real projects); real `updated_at` for `lastModified` where available.
- **AC1:** Given a seeded DB with N published countries and M universities, When `curl /sitemap.xml`, Then N
  `/overseas/countries/{slug}` and M `/overseas/universities/{slug}` entries, each returning 200.
- **AC2:** Then no robots-`Disallow` path and no unpublished/draft item appears.
- **AC3:** Then `lastmod` differs across URLs whose source items have different update times.
- **Depends on:** `seo-001`, `seo-007`. **Note:** course and scholarship detail routes do not exist; adding them is a separate
  Feature ID (`NEEDS_CONFIRMATION`).

#### `seo-007` — Noindex empty listings (P1, 0–30)
- **Files:** page files for `apps/web/app/it/success-stories`, `it/real-projects`, `it/career-paths`, `it/webinars`, `news`,
  `gallery`, `overseas/events`, `it/business-services`, `it/careers`.
- **AC:** Given the listing API returns 0 items, When the page renders, Then it emits `<meta name="robots" content="noindex,follow">`
  and is absent from `sitemap.xml`; Given ≥1 item, Then neither applies (Playwright, both states).
- **Decision:** `DEC-SCOPE-236` (noindex vs hide from navigation).

#### `seo-008` — Structured data (implements `psb-013`; P2, 31–60)
- **Files:** new `apps/web/components/JsonLd.tsx`, used in `apps/web/app/layout.tsx` (Organization/EducationalOrganization with
  the three `PostalAddress` entries from `PUB-024` and `sameAs` after `OPS-SEO-07`), `apps/web/app/it/programs/[slug]/page.tsx`
  (Course + CourseInstance from real batch data only), `apps/web/app/faq/page.tsx` and
  `apps/web/app/overseas/countries/[slug]/page.tsx` (FAQPage from `Country.faq` — closes `psb-008`'s FAQ part), BreadcrumbList on
  detail pages.
- **AC1:** When a script extracts every `script[type="application/ld+json"]` from sitemap URLs, Then each parses as JSON, the root
  has `@type` Organization or EducationalOrganization, and programme pages have Course with `name`, `description`, `provider`.
- **AC2:** Then no `AggregateRating`/`Review` on Organization/EducationalOrganization/LocalBusiness, and FAQPage text matches the
  visible page text.
- **Depends on:** `seo-002`, `OPS-SEO-07`. **Decisions:** `DEC-SCOPE-237`, `DEC-SCOPE-232`.

#### `seo-009` — Social and NAP links in the footer (P2, 31–60)
- **Files:** `apps/web/components/Footer.tsx`; admin-editable through existing CMS/settings if available (`NEEDS_CONFIRMATION`).
- **AC:** Given configured profile URLs, When `/` renders, Then each link has `rel="noopener"`, resolves (HTTP 200 by script), and
  matches the `sameAs` list in `seo-008`.
- **Depends on:** `OPS-SEO-07`; phone/WhatsApp is `psb-004`. **Decision:** `DEC-SCOPE-232`.

#### `seo-010` — UTM attribution on enquiries (addendum to `psb-007`; P2, 31–60)
- **Scope:** add `utm_source`, `utm_medium`, `utm_campaign` and landing path to the tagged lead `psb-007` already specifies, so
  Instagram/LinkedIn link-in-bio traffic can be attributed.
- **Files:** `apps/web/components/EnquiryForm.tsx`; `POST /public/enquiries` in `apps/api/app/api/public.py`; the lead model in
  `apps/api/app/models.py` (migration if new columns — number assigned at build).
- **AC:** Given a visit to `/overseas/contact?utm_source=instagram&utm_medium=social&utm_campaign=launch`, When the enquiry is
  submitted, Then a pytest/e2e check finds the stored lead with those three values and the landing path; And a later page view
  without UTMs in the same session does not overwrite them.
- **Depends on:** `psb-006`/`psb-007`. **Decision:** retention and consent wording (`psb-007` open question).

#### `seo-011` — Compliance-phrase lint (extends `psb-014`; P2, 61–90)
- **AC:** Given the banned-claims list (`guaranteed job`, `job guarantee`, `100% placement`, `guaranteed visa`, `visa guaranteed`,
  `guaranteed admission`, an unfootnoted `*`), When the check runs over rendered sitemap URLs and published CMS content, Then it fails
  on any match; And every page showing an outcome number contains the approved disclaimer (e.g. "past record is no guarantee of
  future prospects") and a period reference.
- **Depends on:** `psb-011`. **Decision:** `DEC-SCOPE-234` (exact list and disclaimer).

#### `seo-012` — SEO smoke test in CI (fold into `psb-014` if preferred; P2, 61–90)
- **AC:** one script that, for every sitemap URL, asserts HTTP 200, unique title and description, self-canonical, exactly one H1,
  no `example.com`, no banned strings, and valid JSON-LD; exits non-zero on any failure; runs against a local build in CI.
- **Depends on:** `seo-001` … `seo-008`.

## KPIs (baseline 2026-10-19; targets set after the day-30 baseline)

| KPI | Source | Baseline |
|---|---|---|
| example.com URLs in sitemap | curl | 24/24 → target 0 |
| Pages with unique title + description | crawl script | 1 of 31 sampled → target 100% |
| Pages with self-canonical | crawl script | 0 → target 100% |
| Placeholder / non-compliant phrases | `seo-005`/`seo-011` lint | ≥7 → target 0 |
| GSC indexed pages; non-brand impressions (UK, IN separately) | GSC | N/A (no access) |
| Core Web Vitals (mobile) | PSI/CrUX | N/A (HTTP 429) |
| Leads by source page and UTM | enquiry pipeline + GA4 | N/A (no tag) |
| Social profiles live and in `sameAs` | manual | 0 → target 2 (Instagram, LinkedIn) |
