# Public Website — Improvement Backlog (`psb-002` … `psb-019`)

NO-ASSUMPTION MODE. Prepared 2026-10-14 at the owner's request ("move the remaining items into backlog"). **No code was written or changed for these items.**

**Source:** a reverse-engineering review of https://www.360digrii.com/ on 2026-10-14. It covered the home, IT Finishing School, Study in Canada and Success Stories pages. Evidence class:
- 360digrii is a competitor site, so it is `UX_REFERENCE` only.
- The owner asked for the list, but has **not** approved any item below as scope.

Every item therefore needs its own clarifying questions, a Decision ID and the usual spec → plan → build cycle before any code.

**Numbering:** `psb-0NN` is this backlog's own item number. Build Feature IDs continue the `PUB-0xx` series after `PUB-022`, and each new Feature ID must be checked against `main` before use. `PUB-011`…`PUB-021` are requirement references in the draft test workbook (`docs/quality/test_audit.json`), so they are not used.

## Status

| Item | Covers | Decision | Delivery |
|---|---|---|---|
| `psb-001` → `PUB-022` | Homepage social proof: an admin-entered rating badge and consented, featured testimonials on `/`, `/it` and `/overseas` | `DEC-SCOPE-210` (migration `0158`, API 12DX, RBAC 2.135) | branch `feature/pub-022`, **PR #268** (built; final review fixed; e2e and full suite: owner) |
| `PUB-023` | Country flags, phase 1: public country/course pages, agent partner universities, partnership admin lists, country picker options | `DEC-SCOPE-222` (no migration, API 12EJ) | branch `feature/pub-023` (built; e2e and full suite: owner) |
| `psb-002` … `psb-019` | Below | — | Not started |

## Items

Each item lists:
- **Why:** what 360digrii does, or gets wrong.
- **EduSphere today:** current evidence from the code, checked on `main` @ `2e96cac8`.
- **Gap:** what's missing.
- **Open questions** (`NEEDS_CONFIRMATION`).

The priority is a suggestion only; the owner sets the order.

### A. Copy their marketing strengths

#### `psb-002` — Hiring-partner logo wall
- **Why:** 360digrii's homepage shows a grid of about 20 client company logos linking to a Clients page.
- **EduSphere today:**
  - The root homepage says "placement support with hiring partners" but shows no logos.
  - `GET /public/home` already returns up to 12 `Company` rows as `partners`, but no page renders them.
- **Gap:** a logo wall on `/` and `/it` built from employer/recruiter company records, plus a logo upload.
- **Open questions:**
  - Which companies may be shown: every employer, or only ones that consented?
  - Is a written logo-use consent needed per company?
  - Where do the logos come from: upload, or fetched from the company website (the dtu-001 approach)?
- **Suggested priority:** P1 (pairs with PUB-022 social proof).

#### `psb-003` — Overseas (and School) success stories
- **Why:** 360digrii's Success Stories mix training, placement and overseas admissions.
- **EduSphere today:**
  - Only `/it/success-stories` exists.
  - PUB-022 testimonials already carry a `division` (`it`/`overseas`) and a free-text `context`.
- **Gap:**
  - An `/overseas/success-stories` list and detail page.
  - Possibly structured fields: university, country, intake, visa granted.
- **Open questions:**
  - Are the structured fields needed, or is PUB-022's free-text `context` enough?
  - Should School stories be included?
  - Can a story link to a real student record, or must it stay standalone?
- **Depends on:** PUB-022 (consent + publish model).

#### `psb-004` — One-tap contact (sticky call / WhatsApp, per-department phones)
- **Why:** 360digrii puts tap-to-call numbers in the header, the contact block and the footer, with separate Placements, Trainings and Overseas lines.
- **EduSphere today:** the public shell has no `tel:` or `wa.me` link. WhatsApp exists only inside the CRM portals (e.g. `WhatsAppComposer`).
- **Gap:** a sticky call/WhatsApp button and per-department numbers in the public footer, editable by admins.
- **Open questions:**
  - The real department phone numbers and WhatsApp business number.
  - Should a click be logged as a lead or an analytics event?
  - Opening hours / out-of-hours behaviour.

#### `psb-005` — Three service tiles on the root homepage
- **Why:** 360digrii's homepage leads with three pillars (Trainings, Placements, Overseas Education), each with "Get started".
- **EduSphere today:** `app/page.tsx` shows two cards (IT Training & Placement, Overseas Education).
- **Gap:** decide whether Placements (and School) deserve their own tile.
- **Open questions:** which services the root homepage should feature, and in what order.

#### `psb-006` — "Talk to us" on country, university and course pages
- **Why:** 360digrii ends every country page with a "Talk to Us / Need Help?" call banner.
- **EduSphere today:** `EnquiryForm` is used only on `/it/contact`, `/overseas/contact` and `/it/corporate-hiring`.
- **Gap:** a banner or inline form on country, university, course and program pages, opening `EnquiryForm` with that context already filled in.
- **Open questions:** the form fields per page type; whether the context becomes lead fields (country, university, course) or only a note.
- **Note:** this overlaps `psb-007`; they could be built together.

### B. Do better where they are weak

#### `psb-007` — Lead capture on every content page
- **Why:** 360digrii has no forms at all (its biggest weakness).
- **EduSphere today:** the enquiry → lead pipeline exists (`POST /public/enquiries`, tel-005 intake), but few pages link into it.
- **Gap:** every content page creates a **tagged** lead (source page, country, university, course, program) that is routed to telecallers or counselors.
- **Open questions:**
  - The routing rules per tag.
  - Spam protection (captcha or rate limits).
  - Consent and privacy wording.
- **Depends on:** `psb-006`.

#### `psb-008` — Fill country-page gaps (partly built)
- **Why:** 360digrii's country pages are generic text with no universities, costs, intakes or visa steps.
- **EduSphere today:** `Country` already has `overview`, `tuition`, `living_expenses`, `visa_process`, `work_opportunities`, `post_study_work`, `pr_opportunities`, `faq` and `interview_prep`.
- **Gap (NEEDS_CONFIRMATION, not yet checked on the rendered page):**
  - a list of that country's partner universities (dtu-001 data);
  - intakes;
  - per-country `FAQPage` structured data (see `psb-013`).
- **Open questions:** which fields are empty in production data, and whether intakes are per country or per university/course.

#### `psb-009` — Lead-generating tools
- **Why:** none of these exist on 360digrii.
- **Gap:** an eligibility checker, a cost-of-study/living calculator, a "which country suits me" quiz, and a course finder by budget and intake. Each ends in an enquiry.
- **Open questions:**
  - Which tool comes first.
  - The data source for costs, which must be maintained (and by whom).
  - The legal wording: the results are guidance, not advice.
- **Suggested split:** one Feature ID per tool.

#### `psb-010` — IT program pages: syllabus download and next batch (partly built)
- **Why:** 360digrii shows no duration, schedule or fees.
- **EduSphere today:** `/it/programs/[slug]` already renders duration, fees and batch information.
- **Gap (NEEDS_CONFIRMATION):**
  - a downloadable syllabus PDF;
  - a clear "next batch starts" date and mode.
- **Open questions:** where syllabi are stored, and whether downloading one should require an enquiry (lead capture).

#### `psb-011` — Verified placement / outcome statistics
- **Why:** 360digrii gives no numbers. EduSphere's own `/public/home` had **fake hard-coded stats**, which PUB-022 removed (SP3).
- **Gap:** computed public numbers (people placed, top packages, hiring companies, visa success), each with a written definition.
- **Open questions (decisions needed):**
  - The definition of each metric.
  - The time window.
  - Whether placement data may be published at all.
  - Who approves the figures before they go live.
- **Depends on:** placement/visa data quality.

#### `psb-012` — Blog / guides for search traffic
- **Why:** 360digrii has no blog.
- **EduSphere today:** `/news` exists (PUB-005, CMS-managed `BlogPost`).
- **Gap:** evergreen guides (SOP writing, visa interview, IELTS, cost of study) with categories, authors and internal links to countries, universities and courses.
- **Open questions:** who writes the content; whether to extend `/news` or add a separate `/guides`.

### C. Technical SEO and quality

#### `psb-013` — Structured data (JSON-LD)
- **EduSphere today:** no `application/ld+json` anywhere in `apps/web/app` or `components`.
- **Gap:**
  - `Organization` / `EducationalOrganization` on the root;
  - `Course` on programs and courses;
  - `FAQPage` on FAQ and country pages;
  - `Review` / `AggregateRating` from PUB-022 published data only.
- **Open questions:** Google's rules for self-served reviews: `AggregateRating` may need to be omitted for first-party reviews.

#### `psb-014` — Automated public-page quality checks
- **Why:** 360digrii shows the defects these checks would catch:
  - its displayed email differs from its link target;
  - its country cards all link to the Canada page;
  - it has empty `#` links, duplicate testimonials, and image descriptions like "img" / "icon".
- **Gap:** an e2e or lint step over public pages: no `href="#"`, contact link equals displayed text, no duplicate card links, no generic image text.
- **Open questions:** run it in CI or as part of the owner's suite.

#### `psb-015` — Live Google rating (optional follow-on to PUB-022)
- **EduSphere today:** PUB-022 SP1 chose an admin-entered badge with **no** external API.
- **Gap:** pull the live rating from the Google Business Profile / Places API instead.
- **Open questions:**
  - A provider decision (blocked by `DEC-INFRA-001`-style gates).
  - An API key and place ID.
  - Google's display terms.
  - Whether this replaces or sits beside the admin-entered badge.

#### `psb-016` — Local SEO city/centre pages
- **Why:** 360digrii has one physical address and no location pages.
- **Gap:** one page per physical centre (address, map, hours, local contact), if EduSphere has centres.
- **Open questions:** do physical centres exist, and where? (Nothing in the repo says.)

### D. Carried from the PUB-022 final review (accepted there, open here)

#### `psb-017` — Uploaded files reachable through `/local-files` in local-storage mode
- **Finding:** `apps/api/app/main.py` mounts `/local-files` over the whole upload directory. In local-storage mode (no S3 bucket), any stored file (testimonial photos, documents) can be fetched by anyone who knows its key, bypassing that file's own access checks.
- **Risk:** keys are random 128-bit values and never sent to clients by PUB-022. S3 mode is unaffected.
- **Gap:** serve local uploads only through authorised routes, or store protected files outside the mounted directory. This is cross-feature, so check every caller of `storage.presign_download`.
- **Open questions:** is local-storage mode used outside development?

#### `psb-018` — Rating badge first-save race
- **Finding:** two simultaneous first-time `PUT /cms/rating-badge` calls can both insert `id = 1`, and one gets a 500.
- **Risk:** negligible (super_admin only, one-off).
- **Gap:** use an insert-or-update on `id = 1`.

#### `psb-019` — Country flags, phase 2
- **Why:** PUB-023 (DEC-SCOPE-222 F1) drew flags only where the web already has the country's `iso2`.
- **Gap:** these screens show a country name from their own API, which needs an `iso2` field first:
  - agent shortlist cards (catalogue entries) and the university match / duplicate list;
  - management universities, applications and abroad revenue;
  - partnership courses, opportunities, performance, expected revenue, the pipeline board and the global dashboard university rows;
  - visits and meetings forms and tables; agreements and commission-term forms;
  - BDM organisation detail; the generic `admin/[module]` country column;
  - the agent dashboard, commission report and report filters; the visa checklist.
- **Not in scope:** native `<select>` dropdowns and free-text country fields (F5).
