# Screen / Route / Flow Catalogue

## 0. Document control

| Field | Value |
|---|---|
| Version | 1.0 (**APPROVED**) |
| Date | 2026-09-01 |
| Status | **APPROVED by user (in-session), 2026-09-01.** GATE-06 satisfied — `prompts/08_ARCHITECTURE_AND_ADRS.md` may proceed. Approval covers the 96 screens as written, all traced to `CURRENT`-scope features only; it does not authorize any screen for a `BLOCKED` feature (none exist in this catalogue), and does not resolve any item in `docs/features/FEATURE_QUESTIONS.md` or `docs/product/PRD_OPEN_ITEMS.md`. **9 School screens (`SCR-SCH-001`–`009`) added 2026-09-14** propagating `DEC-SCOPE-011`/`DEC-SCOPE-010` part 1, **then 4 more (`SCR-SCH-010`–`013`) added the same day** propagating `DEC-SCOPE-012` (onboarding), **then 7 more (`SCR-SCH-014`–`020`) added the same day** propagating `DEC-ROLE-006` (results/career-guidance/psychometric), **then 1 more (`SCR-SCH-021`) added the same day** propagating `DEC-SCOPE-014` (specialized-role account creation/portfolio assignment), **then `SCR-SCH-011` merged into `SCR-SCH-010` (still same day) during `SCH-003`'s actual build** (net School screen count: 20, not 21) — none is a reopening of the 2026-09-01 GATE-06 approval for the rest of this catalogue. |
| Prerequisite satisfied | `docs/features/MASTER_FEATURE_CATALOG.md` v1.0 **APPROVED** 2026-09-01 |
| Traces to | `docs/features/MASTER_FEATURE_CATALOG.md`, `docs/product/PRD.md`/`BRD.md`, `docs/ux/UX_REFERENCE_AUDIT.md` |
| Rule applied | **Features drive screens, not the other way around** — every screen below exists only because a `CURRENT` feature's UX requirement needs it. The old blueprint's 137-screen inventory and the reference implementation's own `SCREEN_ROUTE_MAP.md` were read only as *derived input* (naming/route conventions), never as the source of the screen list itself. |
| Canva-parity rule applied | Per this session's explicit instruction: **no screen below claims Canva visual parity unless actual visual evidence was available.** Only 1 of 96 screens (`SCR-PUB-001`) cites any Canva reference at all — the one default thumbnail actually inspected (`UX_REFERENCE_AUDIT.md`) — and even that is marked structural-reference-only, not pixel-parity, per `DEC-UX-001`. Every other screen explicitly states no visual reference was inspected. |

**116 screens total** (96 approved 2026-09-01 + 20 School screens added 2026-09-14 — `SCR-SCH-011`
merged into `SCR-SCH-010` during `SCH-003`'s build, corrected same day), covering 64
distinct Feature IDs. 1 `CURRENT`/`ux=Y` feature (`AUTH-002`, role-based UI visibility) intentionally
has no dedicated screen — it's a cross-cutting rule applied *within* every other screen (only
role-permitted nav/actions render), not a screen of its own. 9 further `CURRENT` features
(`FND-001`, `FND-002`, `NOT-001/002/003`, `PAY-001`, `SEC-001`, `OPS-001/002`) are correctly `ux=N`
— backend/infra work with no UI surface at all.


## AUTH

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-AUTH-001` | `/it/login` | Visitor->Student/Trainer/Placement Team/HR Team/IT Admin | `AUTH-001` |
| `SCR-AUTH-002` | `/overseas/login` | Visitor->Student/Counselor/University Rep/Agent/Overseas Admin | `AUTH-001` |

### `SCR-AUTH-001`
- **Route:** `/it/login`  
- **Role(s):** Visitor->Student/Trainer/Placement Team/HR Team/IT Admin  
- **Purpose:** IT-division login entry point.  
- **Linked Feature ID(s):** `AUTH-001`  
- **Entry points:** Header 'Login' link from any IT-division public page.  
- **Required data:** None required to view; credential fields on submit.  
- **Key actions:** Enter email/password; submit; forgot-password link.  
- **Empty state:** N/A (form, not a list).  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Generic 'invalid credentials' message — never reveals whether the email exists (anti-enumeration).  
- **Permissions/resource scope:** Public (unauthenticated) to view; redirects by role/division on success.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Login with valid/invalid credentials for each IT-division role; verify correct post-login redirect per role.  

### `SCR-AUTH-002`
- **Route:** `/overseas/login`  
- **Role(s):** Visitor->Student/Counselor/University Rep/Agent/Overseas Admin  
- **Purpose:** Overseas-division login entry point, separate from IT login per the base codebase's division isolation.  
- **Linked Feature ID(s):** `AUTH-001`  
- **Entry points:** Header 'Login' link from any Overseas-division public page.  
- **Required data:** None required to view; credential fields on submit.  
- **Key actions:** Enter email/password; submit; forgot-password link.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Same anti-enumeration behavior as SCR-AUTH-001.  
- **Permissions/resource scope:** Public to view; redirects by role on success.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Same as SCR-AUTH-001, Overseas-division roles.  


## PUB

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-PUB-001` | `/it (Home)` | Visitor | `PUB-001` |
| `SCR-PUB-002` | `/it/about` | Visitor | `PUB-001` |
| `SCR-PUB-003` | `/it/career-paths` | Visitor | `PUB-001` |
| `SCR-PUB-004` | `/it/career-paths/[slug]` | Visitor | `PUB-001` |
| `SCR-PUB-005` | `/it/projects` | Visitor | `PUB-001` |
| `SCR-PUB-006` | `/it/projects/[slug]` | Visitor | `PUB-001` |
| `SCR-PUB-007` | `/it/success-stories` | Visitor | `PUB-001` |
| `SCR-PUB-008` | `/it/success-stories/[slug]` | Visitor | `PUB-001` |
| `SCR-PUB-009` | `/it/business-services` | Visitor | `PUB-001` |
| `SCR-PUB-010` | `/it/blog` | Visitor | `PUB-001` |
| `SCR-PUB-011` | `/it/blog/[slug]` | Visitor | `PUB-001` |
| `SCR-PUB-012` | `/it/contact and /overseas/contact` | Visitor | `PUB-002` |
| `SCR-PUB-013` | `/it/programs` | Visitor | `PUB-003` |
| `SCR-PUB-014` | `/it/programs/[slug]` | Visitor | `PUB-003` |
| `SCR-PUB-015` | `/it/webinars` | Visitor | `PUB-004` |
| `SCR-PUB-016` | `/it/webinars/[id]` | Visitor | `PUB-004` |
| `SCR-PUB-017` | `/news` | Visitor | `PUB-005` |
| `SCR-PUB-018` | `/news/[slug]` | Visitor | `PUB-005` |
| `SCR-PUB-019` | `/gallery` | Visitor | `PUB-005` |

### `SCR-PUB-001`
- **Route:** `/it (Home)`  
- **Role(s):** Visitor  
- **Purpose:** IT division marketing homepage — hero, course discovery entry, career paths/projects/success-story teasers.  
- **Linked Feature ID(s):** `PUB-001`  
- **Entry points:** Root domain, top-nav 'Home', logo click.  
- **Required data:** Published hero content, headline stats, featured courses/paths/projects (CMS-managed).  
- **Key actions:** Explore courses; view career paths; enquire.  
- **Empty state:** No featured content configured yet → generic hero only, no broken sections.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** `DAHRCNYnu6g` default screen ('PUB-001 / Home' per its own on-canvas label) — the **only** Canva screen actually inspected this session (one static thumbnail). Structural reference only, not pixel-parity, per `DEC-UX-001`. Observed: hero heading, 2 CTA buttons, 4 stat tiles, 3 feature cards — this screen's layout should follow that shape; exact spacing/colour/typography were not extractable (no text-layer access) and must not be claimed as matched.  
- **Acceptance evidence needed:** Compare rendered hero/stat-tile/feature-card structure against the one inspected Canva thumbnail; confirm no fabricated content when CMS data is empty.  

### `SCR-PUB-002`
- **Route:** `/it/about`  
- **Role(s):** Visitor  
- **Purpose:** About EduSphere IT — mission, methodology, leadership.  
- **Linked Feature ID(s):** `PUB-001`  
- **Entry points:** Top-nav 'About'.  
- **Required data:** CMS-managed about content.  
- **Key actions:** Read; enquire CTA.  
- **Empty state:** Missing leadership bios show placeholder text, not broken images.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Content renders; no dead links.  

### `SCR-PUB-003`
- **Route:** `/it/career-paths`  
- **Role(s):** Visitor  
- **Purpose:** Career path list.  
- **Linked Feature ID(s):** `PUB-001`  
- **Entry points:** Top-nav 'Career Paths'; home teaser link.  
- **Required data:** Published career paths (CMS).  
- **Key actions:** Browse; open a path.  
- **Empty state:** No paths published → empty state with guidance, not an error.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Empty-state and populated-state both verified.  

### `SCR-PUB-004`
- **Route:** `/it/career-paths/[slug]`  
- **Role(s):** Visitor  
- **Purpose:** Career path detail.  
- **Linked Feature ID(s):** `PUB-001`  
- **Entry points:** SCR-PUB-003 list.  
- **Required data:** Path detail: skills, related courses, outcomes.  
- **Key actions:** Read; enquire; view related course.  
- **Empty state:** Path not found (bad slug) → 404, not a blank page.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** 404 on invalid slug verified.  

### `SCR-PUB-005`
- **Route:** `/it/projects`  
- **Role(s):** Visitor  
- **Purpose:** Real-world project list.  
- **Linked Feature ID(s):** `PUB-001`  
- **Entry points:** Top-nav; home teaser.  
- **Required data:** Published projects.  
- **Key actions:** Browse; open a project.  
- **Empty state:** No projects published → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Empty and populated states verified.  

### `SCR-PUB-006`
- **Route:** `/it/projects/[slug]`  
- **Role(s):** Visitor  
- **Purpose:** Project detail.  
- **Linked Feature ID(s):** `PUB-001`  
- **Entry points:** SCR-PUB-005 list.  
- **Required data:** Problem, deliverables, tech stack, related course.  
- **Key actions:** Read; enquire.  
- **Empty state:** Invalid slug → 404.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** 404 on invalid slug verified.  

### `SCR-PUB-007`
- **Route:** `/it/success-stories`  
- **Role(s):** Visitor  
- **Purpose:** Success story list.  
- **Linked Feature ID(s):** `PUB-001`  
- **Entry points:** Top-nav; home teaser.  
- **Required data:** Published stories.  
- **Key actions:** Browse; open a story.  
- **Empty state:** No stories published → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Empty and populated states verified.  

### `SCR-PUB-008`
- **Route:** `/it/success-stories/[slug]`  
- **Role(s):** Visitor  
- **Purpose:** Success story detail.  
- **Linked Feature ID(s):** `PUB-001`  
- **Entry points:** SCR-PUB-007 list.  
- **Required data:** Case study, before/after, outcomes.  
- **Key actions:** Read.  
- **Empty state:** Invalid slug → 404.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** 404 on invalid slug verified.  

### `SCR-PUB-009`
- **Route:** `/it/business-services`  
- **Role(s):** Visitor  
- **Purpose:** Business/corporate services overview.  
- **Linked Feature ID(s):** `PUB-001`  
- **Entry points:** Top-nav.  
- **Required data:** CMS-managed service descriptions.  
- **Key actions:** Read; contact CTA.  
- **Empty state:** No content → minimal page, not broken.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Content renders; contact CTA works.  

### `SCR-PUB-010`
- **Route:** `/it/blog`  
- **Role(s):** Visitor  
- **Purpose:** Blog list.  
- **Linked Feature ID(s):** `PUB-001`  
- **Entry points:** Top-nav; home teaser.  
- **Required data:** Published posts.  
- **Key actions:** Browse; search/filter; open a post.  
- **Empty state:** No posts → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Empty and populated states verified.  

### `SCR-PUB-011`
- **Route:** `/it/blog/[slug]`  
- **Role(s):** Visitor  
- **Purpose:** Blog post detail.  
- **Linked Feature ID(s):** `PUB-001`  
- **Entry points:** SCR-PUB-010 list.  
- **Required data:** Article body, author, related posts.  
- **Key actions:** Read; share.  
- **Empty state:** Invalid slug → 404.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** 404 on invalid slug verified.  

### `SCR-PUB-012`
- **Route:** `/it/contact and /overseas/contact`  
- **Role(s):** Visitor  
- **Purpose:** Enquiry/callback form.  
- **Linked Feature ID(s):** `PUB-002`  
- **Entry points:** Header 'Enquire' CTA; footer link.  
- **Required data:** None (write-only form).  
- **Key actions:** Submit name/email/phone/programme-interest/message.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Validation errors shown per field; a Zoho-webhook failure does not lose the locally-captured enquiry (silent to the user, logged internally).  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Enquiry appears in SCR-ADM-004 (enquiry list) after submission, regardless of webhook outcome.  

### `SCR-PUB-013`
- **Route:** `/it/programs`  
- **Role(s):** Visitor  
- **Purpose:** Course catalogue with search/filter.  
- **Linked Feature ID(s):** `PUB-003`  
- **Entry points:** Top-nav 'Programs'.  
- **Required data:** Published courses; category/fee filters.  
- **Key actions:** Search; filter; sort; open a course.  
- **Empty state:** No matching courses → 'No programs available' with a request-callback CTA (matches live reference implementation copy).  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Filter/search/pagination all verified against a populated and an empty catalogue.  

### `SCR-PUB-014`
- **Route:** `/it/programs/[slug]`  
- **Role(s):** Visitor  
- **Purpose:** Course detail.  
- **Linked Feature ID(s):** `PUB-003`  
- **Entry points:** SCR-PUB-013.  
- **Required data:** Curriculum, fee, duration, certification/placement flags, trainer info.  
- **Key actions:** Read; enquire; start enrolment (→ SCR-STU-001 if authenticated).  
- **Empty state:** Invalid slug → 404.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** 404 on invalid slug; enrolment CTA correctly gates on auth state.  

### `SCR-PUB-015`
- **Route:** `/it/webinars`  
- **Role(s):** Visitor  
- **Purpose:** Webinar list.  
- **Linked Feature ID(s):** `PUB-004`  
- **Entry points:** Top-nav.  
- **Required data:** Upcoming/past webinars.  
- **Key actions:** Browse; register.  
- **Empty state:** No webinars → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Empty and populated states verified.  

### `SCR-PUB-016`
- **Route:** `/it/webinars/[id]` — built as `[id]` (UUID), not `[slug]`: the `Event` model reused
  for webinar content (`DATA_MODEL.md` §2.4) has no slug column, and none is required by confirmed
  evidence.  
- **Role(s):** Visitor  
- **Purpose:** Webinar detail and registration.  
- **Linked Feature ID(s):** `PUB-004`  
- **Entry points:** SCR-PUB-015.  
- **Required data:** Agenda, speakers, date/time.  
- **Key actions:** Register; add consent.  
- **Empty state:** Past/closed webinar shows registration-closed state, not an open form (capacity/waitlist rule itself open — see FEATURE_QUESTIONS.md).  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Registration confirmation shown; closed-webinar state verified.  

### `SCR-PUB-017`
- **Route:** `/news`  
- **Role(s):** Visitor  
- **Purpose:** News list (CMS-managed).  
- **Linked Feature ID(s):** `PUB-005`  
- **Entry points:** Top-nav (corporate).  
- **Required data:** Published articles.  
- **Key actions:** Browse; open an article.  
- **Empty state:** 'No published news yet' (matches live reference implementation copy exactly).  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Empty-state copy matches confirmed baseline; populated state verified once content exists.  

### `SCR-PUB-018`
- **Route:** `/news/[slug]`  
- **Role(s):** Visitor  
- **Purpose:** News article detail.  
- **Linked Feature ID(s):** `PUB-005`  
- **Entry points:** SCR-PUB-017.  
- **Required data:** Article body.  
- **Key actions:** Read.  
- **Empty state:** Invalid slug → 404.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** 404 on invalid slug verified.  

### `SCR-PUB-019`
- **Route:** `/gallery`  
- **Role(s):** Visitor  
- **Purpose:** Gallery (CMS-managed).  
- **Linked Feature ID(s):** `PUB-005`  
- **Entry points:** Top-nav (corporate).  
- **Required data:** Published gallery items.  
- **Key actions:** Browse; filter by category/division.  
- **Empty state:** 'Gallery content is CMS-managed' empty state (matches live reference implementation copy).  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Empty-state copy matches confirmed baseline.  


## STU

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-STU-001` | `/student/enrol/[courseId]` | Student | `STU-001` |
| `SCR-STU-002` | `/student (Dashboard)` | Student | `STU-002` |
| `SCR-STU-003` | `/student/live/[sessionId]` | Student | `STU-003` |
| `SCR-STU-004` | `/student/assignments` | Student | `STU-004` |
| `SCR-STU-005` | `/student/assignments/[id]` | Student | `STU-004` |
| `SCR-STU-006` | `/student/support` | Student | `STU-005` |
| `SCR-STU-007` | `/student/attendance` | Student | `STU-006` |
| `SCR-STU-008` | `/student/certificates` | Student | `STU-007` |
| `SCR-STU-009` | `/student/feedback/[courseId]` | Student | `STU-008` |
| `SCR-STU-010` | `/student/agreements` | Student | `STU-009` |
| `SCR-STU-011` | `/student/payments` | Student | `STU-010` |
| `SCR-STU-012` | `/student/payments/pay` | Student | `STU-010` |
| `SCR-STU-013` | `/student/invoices/[id] and /student/receipts/[id]` | Student | `STU-010` |
| `SCR-STU-014` | `/student/profile` | Student | `STU-011` |

### `SCR-STU-001`
- **Route:** `/student/enrol/[courseId]`  
- **Role(s):** Student  
- **Purpose:** Trainer/time-slot selection at enrolment.  
- **Linked Feature ID(s):** `STU-001`  
- **Entry points:** SCR-PUB-014 'Start enrolment' CTA; SCR-STU-002 'Enrol in another course'.  
- **Required data:** Available batches/trainers/slots with live capacity count.  
- **Key actions:** Select a slot; confirm booking.  
- **Empty state:** No slots available for this course → 'fully booked' state with a notify-me/waitlist prompt (waitlist itself not confirmed — do not build without confirmation).  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Booking a slot that reached capacity between page-load and submit is rejected with a clear 'this slot just filled' message, not a silent failure.  
- **Permissions/resource scope:** Self (Student).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** 20th booking succeeds, 21st is rejected; a booked slot's edit control is disabled/absent.  

### `SCR-STU-002`
- **Route:** `/student (Dashboard)`  
- **Role(s):** Student  
- **Purpose:** Student home: progress, attendance, fees, jobs, upcoming assignments.  
- **Linked Feature ID(s):** `STU-002`  
- **Entry points:** Post-login redirect; persistent nav 'Dashboard'.  
- **Required data:** Aggregated enrolment/attendance/payment/assignment data.  
- **Key actions:** Navigate to any sub-area; join next live class.  
- **Empty state:** New student with no enrolments → onboarding empty state pointing to SCR-PUB-013.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** One failed data source (e.g. payments API down) degrades that widget only, not the whole dashboard.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Dashboard renders correctly with 0, 1, and many enrolments.  

### `SCR-STU-003`
- **Route:** `/student/live/[sessionId]`  
- **Role(s):** Student  
- **Purpose:** Join a live class.  
- **Linked Feature ID(s):** `STU-003`  
- **Entry points:** SCR-STU-002 'Join now' widget; SCR-TRN-003 shared session.  
- **Required data:** Session join link (Zoho/Google Meet).  
- **Key actions:** Join; leave.  
- **Empty state:** Session not yet started → countdown/wait state, not a broken link.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Session ended or provider link expired shows a clear message, not a generic error.  
- **Permissions/resource scope:** Self (enrolled in that batch).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Join works only for the enrolled batch's own students.  

### `SCR-STU-004`
- **Route:** `/student/assignments`  
- **Role(s):** Student  
- **Purpose:** Assignment list.  
- **Linked Feature ID(s):** `STU-004`  
- **Entry points:** SCR-STU-002.  
- **Required data:** Assigned work per batch, due dates, submission/grade status.  
- **Key actions:** Open an assignment.  
- **Empty state:** No assignments yet → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** List reflects only the student's own batch assignments.  

### `SCR-STU-005`
- **Route:** `/student/assignments/[id]`  
- **Role(s):** Student  
- **Purpose:** Assignment detail and submission.  
- **Linked Feature ID(s):** `STU-004`  
- **Entry points:** SCR-STU-004.  
- **Required data:** Instructions, due date, rubric, attachments; prior submission if any.  
- **Key actions:** Upload/submit; view grade+feedback once graded.  
- **Empty state:** Submission after due date flagged as late per trainer rule, not silently accepted as on-time.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Unsupported file type/size rejected with a clear message (exact limits open — see PRD open items).  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Late-submission flag and grade/feedback display verified.  

### `SCR-STU-006`
- **Route:** `/student/support`  
- **Role(s):** Student  
- **Purpose:** Support ticket list and create.  
- **Linked Feature ID(s):** `STU-005`  
- **Entry points:** SCR-STU-002 'Help & Support'.  
- **Required data:** Own tickets, status.  
- **Key actions:** Raise a ticket; view responses.  
- **Empty state:** No tickets → empty state with 'Raise a ticket' CTA.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** New ticket appears immediately in the list.  

**Addendum (`prompts/13`, `STU-005` build, 2026-09-02):** no screen was ever catalogued for this
feature's own named secondary actors (Trainer, Admin resolve). Rather than mint new formal `SCR-`
IDs into this tightly ID-controlled catalogue for what reuses the existing generic portal chrome
(`PortalPage`/`WorkflowPanel`/`TeacherWorkspaceActions`, no bespoke layout), the resolve queue is
added as the existing `support` section at `/it/trainer/support` and `/it/admin/support` --
division-scoped list (unassigned tickets included, `STU-005-AC02`) with a resolve action per row.

### `SCR-STU-007`
- **Route:** `/student/attendance`  
- **Role(s):** Student  
- **Purpose:** Attendance and progress view.  
- **Linked Feature ID(s):** `STU-006`  
- **Entry points:** SCR-STU-002.  
- **Required data:** Per-session attendance; module completion %.  
- **Key actions:** Read-only review.  
- **Empty state:** Session not yet marked by trainer → 'not yet recorded', never defaulted to absent.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Unmarked vs. absent states are visually distinct.  

### `SCR-STU-008`
- **Route:** `/student/certificates`  
- **Role(s):** Student  
- **Purpose:** Certificate list and download.  
- **Linked Feature ID(s):** `STU-007`  
- **Entry points:** SCR-STU-002.  
- **Required data:** Earned/pending certificates.  
- **Key actions:** Download a PDF.  
- **Empty state:** Not-yet-eligible course shows 'in progress', not a broken download link.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Download only enabled once eligibility criteria are met.  

### `SCR-STU-009`
- **Route:** `/student/feedback/[courseId]`  
- **Role(s):** Student  
- **Purpose:** Course/trainer feedback form.  
- **Linked Feature ID(s):** `STU-008`  
- **Entry points:** SCR-STU-002 post-completion prompt.  
- **Required data:** None (write form).  
- **Key actions:** Submit rating/comments.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Feedback for a course the student isn't enrolled in is rejected.  
- **Permissions/resource scope:** Self, own enrolled courses only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Cannot submit for an unenrolled course.  

### `SCR-STU-010`
- **Route:** `/student/agreements`  
- **Role(s):** Student  
- **Purpose:** Digital agreement review and acceptance.  
- **Linked Feature ID(s):** `STU-009`  
- **Entry points:** SCR-STU-001 enrolment flow, blocking step.  
- **Required data:** Agreement document, version.  
- **Key actions:** Read; accept (timestamped).  
- **Empty state:** N/A — cannot proceed past this step unaccepted.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Enrolment cannot complete without a recorded acceptance timestamp.  

### `SCR-STU-011`
- **Route:** `/student/payments`  
- **Role(s):** Student  
- **Purpose:** Payment dashboard: total/paid/pending/next due.  
- **Linked Feature ID(s):** `STU-010`  
- **Entry points:** SCR-STU-002.  
- **Required data:** Fee plan, EMI schedule, payment history.  
- **Key actions:** View instalment timeline; go to checkout.  
- **Empty state:** No pending dues → 'all paid' state, not an empty error.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Instalment timeline matches actual payment records.  

### `SCR-STU-012`
- **Route:** `/student/payments/pay`  
- **Role(s):** Student  
- **Purpose:** Payment checkout (Razorpay).  
- **Linked Feature ID(s):** `STU-010`  
- **Entry points:** SCR-STU-011 'Pay now'.  
- **Required data:** Amount due, selected gateway.  
- **Key actions:** Submit payment via hosted checkout.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Failed/declined payment shown clearly; fee is never marked paid until webhook confirms.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Fee status only flips to paid after a verified webhook, never on client-side redirect alone.  

### `SCR-STU-013`
- **Route:** `/student/invoices/[id] and /student/receipts/[id]`  
- **Role(s):** Student  
- **Purpose:** Invoice/receipt detail.  
- **Linked Feature ID(s):** `STU-010`  
- **Entry points:** SCR-STU-011 line item.  
- **Required data:** Invoice lines, tax, PDF; receipt reference.  
- **Key actions:** Download PDF.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** PDF download works; only own invoices/receipts visible.  

### `SCR-STU-014`
- **Route:** `/student/profile`  
- **Role(s):** Student  
- **Purpose:** Profile and document management.  
- **Linked Feature ID(s):** `STU-011`  
- **Entry points:** Persistent nav.  
- **Required data:** Contact info; documents.  
- **Key actions:** Edit fields; upload documents.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Invalid file type/size on upload rejected clearly.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Edits persist; upload validation verified.  


## TRN

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-TRN-001` | `/trainer/batches (My Batches)` | Trainer | `TRN-001` |
| `SCR-TRN-002` | `/trainer/batches/[id]` | Trainer | `TRN-002` |
| `SCR-TRN-003` | `/trainer (Dashboard/Calendar)` | Trainer | `TRN-003` |
| `SCR-TRN-004` | `/trainer/recordings` | Trainer, Student | `TRN-004` |
| `SCR-TRN-005` | `/trainer/resources/upload` | Trainer, Student | `TRN-004` |
| `SCR-TRN-006` | `/trainer/assignments` | Trainer | `TRN-005` |
| `SCR-TRN-007` | `/trainer/assignments/new` | Trainer | `TRN-005` |
| `SCR-TRN-008` | `/trainer/assessments` | Trainer | `TRN-006` |
| `SCR-TRN-009` | `/trainer/submissions/[id]` | Trainer | `TRN-007` |
| `SCR-TRN-010` | `/trainer/attendance/[sessionId]` | Trainer | `TRN-008` |
| `SCR-TRN-011` | `/trainer/questions` | Trainer | `TRN-009` |
| `SCR-TRN-012` | `/trainer/questions/[id]` | Trainer, Student | `TRN-009` |

### `SCR-TRN-001`
- **Route:** `/trainer/batches (My Batches)`  
- **Role(s):** Trainer  
- **Purpose:** List of assigned batches only.  
- **Linked Feature ID(s):** `TRN-001`  
- **Entry points:** Post-login redirect; persistent nav.  
- **Required data:** Assigned batches: course, capacity, status, progress.  
- **Key actions:** Open a batch.  
- **Empty state:** No batches assigned → empty state, not an error.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self (Trainer, own batches only).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** List contains only this trainer's own assigned batches.  

### `SCR-TRN-002`
- **Route:** `/trainer/batches/[id]`  
- **Role(s):** Trainer  
- **Purpose:** Batch detail: roster + schedule.  
- **Linked Feature ID(s):** `TRN-002`  
- **Entry points:** SCR-TRN-001.  
- **Required data:** Student roster (≤20), schedule, resources, assignments, attendance summary.  
- **Key actions:** View roster; jump to grading/attendance/resources for this batch.  
- **Empty state:** N/A — batch always has ≥1 student once active.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self, own batch only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Roster shows exactly the students enrolled in that batch's slot, capped at 20.  

### `SCR-TRN-003`
- **Route:** `/trainer (Dashboard/Calendar)`  
- **Role(s):** Trainer  
- **Purpose:** Today's sessions, pending reviews, unanswered Q&A.  
- **Linked Feature ID(s):** `TRN-003`  
- **Entry points:** Post-login redirect.  
- **Required data:** Upcoming sessions across all assigned batches; join links.  
- **Key actions:** Launch/join a live session.  
- **Empty state:** No sessions today → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Not-yet-joinable session shown as such, not an error.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Only this trainer's own upcoming sessions appear.  

### `SCR-TRN-004`
- **Route:** `/trainer/recordings`  
- **Role(s):** Trainer, Student  
- **Purpose:** Recording list per batch.  
- **Linked Feature ID(s):** `TRN-004`  
- **Entry points:** SCR-TRN-002.  
- **Required data:** Past session recordings.  
- **Key actions:** View/share a recording link.  
- **Empty state:** Session missed by the concurrency limit → 'unavailable', not an error.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Trainer (own batch) / enrolled Students (view).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Missing-recording state distinguishable from a load error.  

### `SCR-TRN-005`
- **Route:** `/trainer/resources/upload`  
- **Role(s):** Trainer, Student  
- **Purpose:** Resource/notes upload.  
- **Linked Feature ID(s):** `TRN-004`  
- **Entry points:** SCR-TRN-002.  
- **Required data:** Course/folder selection.  
- **Key actions:** Upload file/link; set visibility/publish schedule.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Unsupported file type/size rejected clearly.  
- **Permissions/resource scope:** Trainer (own batch, write) / Students (read).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Uploaded resource visible to enrolled students only.  

### `SCR-TRN-006`
- **Route:** `/trainer/assignments`  
- **Role(s):** Trainer  
- **Purpose:** Assignment management list (draft/published/closed).  
- **Linked Feature ID(s):** `TRN-005`  
- **Entry points:** SCR-TRN-002.  
- **Required data:** Assignments per batch, submission/grading status.  
- **Key actions:** Create new; open existing.  
- **Empty state:** No assignments yet → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self, own batch.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** List scoped to trainer's own batches.  

### `SCR-TRN-007`
- **Route:** `/trainer/assignments/new`  
- **Role(s):** Trainer  
- **Purpose:** Assignment create/edit.  
- **Linked Feature ID(s):** `TRN-005`  
- **Entry points:** SCR-TRN-006.  
- **Required data:** Title, description, due date, rubric, attachments.  
- **Key actions:** Save; publish to batch.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Editing after submissions exist does not retroactively invalidate them.  
- **Permissions/resource scope:** Self, own batch.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Published assignment visible to batch students immediately.  

### `SCR-TRN-008`
- **Route:** `/trainer/assessments`  
- **Role(s):** Trainer  
- **Purpose:** Assessment management (draft/scheduled), distinct type from assignments.  
- **Linked Feature ID(s):** `TRN-006`  
- **Entry points:** SCR-TRN-002.  
- **Required data:** Assessments per batch, question sets.  
- **Key actions:** Create/edit; move draft→scheduled.  
- **Empty state:** No assessments yet → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A draft assessment is never visible to Students under any circumstance.  
- **Permissions/resource scope:** Self, own batch.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Draft-state assessment confirmed invisible to Student role via direct URL attempt.  

### `SCR-TRN-009`
- **Route:** `/trainer/submissions/[id]`  
- **Role(s):** Trainer  
- **Purpose:** Submission review and grading.  
- **Linked Feature ID(s):** `TRN-007`  
- **Entry points:** SCR-TRN-006 submission list.  
- **Required data:** Submitted work, rubric.  
- **Key actions:** Assign score/feedback.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Re-grading overwrites the prior grade with an audit trail, not a duplicate.  
- **Permissions/resource scope:** Self, own batch.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Grade/feedback appears to the submitting student immediately.  

### `SCR-TRN-010`
- **Route:** `/trainer/attendance/[sessionId]`  
- **Role(s):** Trainer  
- **Purpose:** Attendance marking.  
- **Linked Feature ID(s):** `TRN-008`  
- **Entry points:** SCR-TRN-002 or SCR-TRN-003 post-session prompt.  
- **Required data:** Roster for that session.  
- **Key actions:** Mark present/absent/late per student; bulk mark.  
- **Empty state:** Session with an empty roster → empty state, not an error.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self, own batch.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Bulk-mark and per-student override both verified.  

### `SCR-TRN-011`
- **Route:** `/trainer/questions`  
- **Role(s):** Trainer  
- **Purpose:** Q&A inbox (unanswered/assigned/resolved).  
- **Linked Feature ID(s):** `TRN-009`  
- **Entry points:** SCR-TRN-002.  
- **Required data:** Questions raised against trainer's batches.  
- **Key actions:** Filter by status; open a thread.  
- **Empty state:** No open questions → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self, own batch.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Only own-batch questions appear.  

### `SCR-TRN-012`
- **Route:** `/trainer/questions/[id]`  
- **Role(s):** Trainer, Student  
- **Purpose:** Q&A thread detail and reply.  
- **Linked Feature ID(s):** `TRN-009`  
- **Entry points:** SCR-TRN-011.  
- **Required data:** Full thread.  
- **Key actions:** Post a reply.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Trainer (own batch, reply) / asking Student (view/reply).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Only the assigned trainer for that batch can post the trainer-side reply.  


## ADM

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-ADM-001` | `/it/admin (Operations Dashboard)` | IT Admin | `ADM-001` |
| `SCR-ADM-002` | `/it/admin/users, /it/admin/users/[id]` | IT Admin | `ADM-001`, `ADM-004` |
| `SCR-ADM-003` | `/it/admin/courses` | IT Admin | `ADM-001` |
| `SCR-ADM-004` | `/it/admin/leads (Enquiries)` | IT Admin | `ADM-002` |
| `SCR-ADM-005` | `/it/admin/batches, /it/admin/batches/[id]` | IT Admin | `ADM-003` |
| `SCR-ADM-006` | `/it/admin/enrolments, /it/admin/enrolments/[id]` | IT Admin | `ADM-005` |
| `SCR-ADM-007` | `/it/admin/certificates` | IT Admin | `ADM-006` |
| `SCR-ADM-008` | `/it/placement/candidates` | Placement Team | `ADM-007` |
| `SCR-ADM-009` | `/it/placement/company-requirements` | Placement Team | `ADM-007` |
| `SCR-ADM-010` | `/it/placement/interviews` | Placement Team | `ADM-007` |
| `SCR-ADM-012` | `/it/hr/job-requirements` | HR Team | `ADM-008` |
| `SCR-ADM-013` | `/it/hr/candidates` | HR Team | `ADM-008` |
| `SCR-ADM-014` | `/it/hr/interviews` | HR Team | `ADM-008` |
| `SCR-ADM-015` | `/admin (Super Admin console)` | Super Admin | `ADM-014` |
| `SCR-ADM-016` | `/admin/content, /admin/blogs, /admin/events` | Super Admin | `ADM-014` |
| `SCR-ADM-017` | `/admin/security-logs, /admin/backups` | Super Admin | `ADM-014` |

### `SCR-ADM-001`
- **Route:** `/it/admin (Operations Dashboard)`  
- **Role(s):** IT Admin  
- **Purpose:** IT Admin landing dashboard.  
- **Linked Feature ID(s):** `ADM-001`  
- **Entry points:** Post-login redirect.  
- **Required data:** Summary counts: users, enquiries, active batches.  
- **Key actions:** Navigate to any admin area.  
- **Empty state:** N/A — always shows summary, zero-state included.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** IT Admin.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Counts match underlying data.  

### `SCR-ADM-002`
- **Route:** `/it/admin/users, /it/admin/users/[id]`  
- **Role(s):** IT Admin  
- **Purpose:** User/Student/Trainer directory and detail.  
- **Linked Feature ID(s):** `ADM-001`, `ADM-004`  
- **Entry points:** SCR-ADM-001.  
- **Required data:** User list with role/status filters; detail record.  
- **Key actions:** Create/edit/deactivate a user.  
- **Empty state:** No matching filter results → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Deleting/deactivating a user with active dependents (e.g. an active batch's trainer) is blocked or requires explicit confirmation, never a silent cascade.  
- **Permissions/resource scope:** IT Admin.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Cascade-block behavior verified on a trainer with an active batch.  

### `SCR-ADM-003`
- **Route:** `/it/admin/courses`  
- **Role(s):** IT Admin  
- **Purpose:** Course management.  
- **Linked Feature ID(s):** `ADM-001`  
- **Entry points:** SCR-ADM-001.  
- **Required data:** Course list.  
- **Key actions:** Create/edit a course.  
- **Empty state:** No courses → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** IT Admin.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Created course appears in SCR-PUB-013 once published.  

### `SCR-ADM-004`
- **Route:** `/it/admin/leads (Enquiries)`  
- **Role(s):** IT Admin  
- **Purpose:** Enquiry/lead list synced via the CRM webhook.  
- **Linked Feature ID(s):** `ADM-002`  
- **Entry points:** SCR-ADM-001; new enquiry notification.  
- **Required data:** Enquiries with Zoho sync status.  
- **Key actions:** Route/assign an enquiry; mark actioned.  
- **Empty state:** No enquiries → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** An enquiry that failed to sync to Zoho remains visible and actionable regardless of sync status.  
- **Permissions/resource scope:** IT Admin.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Enquiry from SCR-PUB-012 appears here immediately, sync status shown but not blocking.  

### `SCR-ADM-005`
- **Route:** `/it/admin/batches, /it/admin/batches/[id]`  
- **Role(s):** IT Admin  
- **Purpose:** Batch creation and trainer assignment.  
- **Linked Feature ID(s):** `ADM-003`  
- **Entry points:** SCR-ADM-003 or SCR-ADM-001.  
- **Required data:** Course, trainer options, capacity (≤20), schedule.  
- **Key actions:** Create batch; assign trainer; set capacity.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Capacity above 20 is rejected at save time, not just hidden in the Student-facing UI.  
- **Permissions/resource scope:** IT Admin.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Attempted capacity of 21 rejected; batch immediately selectable at SCR-STU-001 once saved.  

### `SCR-ADM-006`
- **Route:** `/it/admin/enrolments, /it/admin/enrolments/[id]`  
- **Role(s):** IT Admin  
- **Purpose:** Enrolment review and approval.  
- **Linked Feature ID(s):** `ADM-005`  
- **Entry points:** SCR-ADM-004 post-sync.  
- **Required data:** Enrolment/enquiry detail, documents.  
- **Key actions:** Approve; reject.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A rejected enrolment does not silently proceed to active status.  
- **Permissions/resource scope:** IT Admin.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Approval flips the enrolment to active and unlocks the Student portal for that user.  

### `SCR-ADM-007`
- **Route:** `/it/admin/certificates`  
- **Role(s):** IT Admin  
- **Purpose:** Certificate administration (admin-issue path).  
- **Linked Feature ID(s):** `ADM-006`  
- **Entry points:** SCR-ADM-002 student detail.  
- **Required data:** Completion status per student.  
- **Key actions:** Issue/upload a certificate.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Issuing before completion criteria are met requires an explicit override, never silent allowance.  
- **Permissions/resource scope:** IT Admin.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Issued certificate appears immediately at SCR-STU-008.  

### `SCR-ADM-008`
- **Route:** `/it/placement/candidates`  
- **Role(s):** Placement Team  
- **Purpose:** [base] Candidate pool.  
- **Linked Feature ID(s):** `ADM-007`  
- **Entry points:** Post-login redirect.  
- **Required data:** Placement-ready students.  
- **Key actions:** Search/filter; view profile.  
- **Empty state:** No candidates → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Placement Team.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** List reflects only placement-ready students.  

### `SCR-ADM-009`
- **Route:** `/it/placement/company-requirements`  
- **Role(s):** Placement Team  
- **Purpose:** [base] Company hiring requirements review.  
- **Linked Feature ID(s):** `ADM-007`  
- **Entry points:** Placement Team dashboard.  
- **Required data:** Requirements submitted (incl. via SCR-EMP-002 once Employer exists).  
- **Key actions:** Validate role/skills; forward to matching.  
- **Empty state:** No open requirements → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Placement Team.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** See FEATURE_QUESTIONS.md Q1 — Employer/Placement Team interaction undefined.  

### `SCR-ADM-010`
- **Route:** `/it/placement/interviews`  
- **Role(s):** Placement Team  
- **Purpose:** [base] Interview coordination and offer/joining tracking.  
- **Linked Feature ID(s):** `ADM-007`  
- **Entry points:** SCR-ADM-008/009.  
- **Required data:** Scheduled interviews, offers.  
- **Key actions:** Schedule; record offer/joining status.  
- **Empty state:** No activity yet → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Scheduling conflicts (same candidate, overlapping time) flagged, not silently double-booked.  
- **Permissions/resource scope:** Placement Team.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Conflict-flagging verified.  

### `SCR-ADM-012`
- **Route:** `/it/hr/job-requirements`  
- **Role(s):** HR Team  
- **Purpose:** [base] Hiring requirement intake.  
- **Linked Feature ID(s):** `ADM-008`  
- **Entry points:** Post-login redirect.  
- **Required data:** Submitted hiring requirements.  
- **Key actions:** Review; action.  
- **Empty state:** No requirements → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** HR Team.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** See FEATURE_QUESTIONS.md Q1.  

### `SCR-ADM-013`
- **Route:** `/it/hr/candidates`  
- **Role(s):** HR Team  
- **Purpose:** [base] Shortlist coordination.  
- **Linked Feature ID(s):** `ADM-008`  
- **Entry points:** SCR-ADM-012.  
- **Required data:** Shortlisted candidates per requirement.  
- **Key actions:** Add/remove from shortlist.  
- **Empty state:** No shortlist yet → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** HR Team.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Shortlist scoped to the HR Team's own requirement.  

### `SCR-ADM-014`
- **Route:** `/it/hr/interviews`  
- **Role(s):** HR Team  
- **Purpose:** [base] Interview coordination.  
- **Linked Feature ID(s):** `ADM-008`  
- **Entry points:** SCR-ADM-013.  
- **Required data:** Scheduled interviews.  
- **Key actions:** Schedule; update status.  
- **Empty state:** No interviews → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** HR Team.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Interview status changes reflected in real time.  

### `SCR-ADM-015`
- **Route:** `/admin (Super Admin console)`  
- **Role(s):** Super Admin  
- **Purpose:** [base] Cross-division dashboard.  
- **Linked Feature ID(s):** `ADM-014`  
- **Entry points:** Post-login redirect.  
- **Required data:** Both-division summary metrics.  
- **Key actions:** Navigate to any cross-division area.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Super Admin.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** See FEATURE_QUESTIONS.md Q2 — ownership vs IT Admin for ops-tooling ambiguous.  

### `SCR-ADM-016`
- **Route:** `/admin/content, /admin/blogs, /admin/events`  
- **Role(s):** Super Admin  
- **Purpose:** [base] CMS management.  
- **Linked Feature ID(s):** `ADM-014`  
- **Entry points:** SCR-ADM-015.  
- **Required data:** Pages/blogs/events (feeds SCR-PUB-010/015/017/019).  
- **Key actions:** Create/edit/publish content.  
- **Empty state:** No content → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Super Admin.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Published content appears on the corresponding public screen.  

### `SCR-ADM-017`
- **Route:** `/admin/security-logs, /admin/backups`  
- **Role(s):** Super Admin  
- **Purpose:** [base] Security logs and backups.  
- **Linked Feature ID(s):** `ADM-014`  
- **Entry points:** SCR-ADM-015.  
- **Required data:** Privileged-action audit trail; backup status.  
- **Key actions:** Review logs; trigger/verify backup.  
- **Empty state:** No log entries yet → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Super Admin.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Every privileged write from any admin screen appears here.  


## EMP

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-EMP-001` | `/employer/register` | Employer | `EMP-001` |
| `SCR-EMP-002` | `/employer (Dashboard)` | Employer | `EMP-001` |
| `SCR-EMP-003` | `/employer/jobs, /employer/jobs/new` | Employer | `EMP-002` |
| `SCR-EMP-004` | `/employer/candidates` | Employer | `EMP-003` |
| `SCR-EMP-005` | `/employer/candidates/[id]` | Employer | `EMP-003` |
| `SCR-EMP-006` | `/employer/shortlist` | Employer | `EMP-004` |
| `SCR-EMP-007` | `/employer/interviews/new` | Employer | `EMP-004` |
| `SCR-EMP-008` | `/employer/interviews` | Employer | `EMP-005` |

### `SCR-EMP-001`
- **Route:** `/employer/register`  
- **Role(s):** Employer  
- **Purpose:** [new] Employer registration.  
- **Linked Feature ID(s):** `EMP-001`  
- **Entry points:** Public 'Company/HR Login' area, 'Register' link.  
- **Required data:** Company details.  
- **Key actions:** Submit registration.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Duplicate company registration (same domain) is flagged, not silently duplicated.  
- **Permissions/resource scope:** Public to register; self after.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Approval-before-activation workflow open — see FEATURE_QUESTIONS.md item 7.  

### `SCR-EMP-002`
- **Route:** `/employer (Dashboard)`  
- **Role(s):** Employer  
- **Purpose:** [new] Employer landing dashboard.  
- **Linked Feature ID(s):** `EMP-001`  
- **Entry points:** Post-login redirect.  
- **Required data:** Own job postings, shortlist, interview summary.  
- **Key actions:** Navigate to any Employer area.  
- **Empty state:** New Employer with no postings → onboarding empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self (Employer).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Only this Employer's own data visible.  

### `SCR-EMP-003`
- **Route:** `/employer/jobs, /employer/jobs/new`  
- **Role(s):** Employer  
- **Purpose:** [new] Job posting list and create/edit.  
- **Linked Feature ID(s):** `EMP-002`  
- **Entry points:** SCR-EMP-002.  
- **Required data:** Own job postings.  
- **Key actions:** Post a new job; edit/close an existing one.  
- **Empty state:** No postings → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A job past its closing date is not shown to Students as open, even if never explicitly closed.  
- **Permissions/resource scope:** Self (Employer, own postings).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Closed/expired job disappears from the Student-facing career portal.  

### `SCR-EMP-004`
- **Route:** `/employer/candidates`  
- **Role(s):** Employer  
- **Purpose:** [new] Candidate search.  
- **Linked Feature ID(s):** `EMP-003`  
- **Entry points:** SCR-EMP-002.  
- **Required data:** Searchable candidate profiles, GDPR-scoped fields only.  
- **Key actions:** Search/filter; view a profile.  
- **Empty state:** No matches → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Fields outside approved visibility are never returned, not merely hidden client-side.  
- **Permissions/resource scope:** Self (Employer).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** API response itself excludes non-visible fields — verified server-side, not just UI-hidden. Exact field set open — see PRD_OPEN_ITEMS item 33.  

### `SCR-EMP-005`
- **Route:** `/employer/candidates/[id]`  
- **Role(s):** Employer  
- **Purpose:** [new] Candidate profile detail.  
- **Linked Feature ID(s):** `EMP-003`  
- **Entry points:** SCR-EMP-004.  
- **Required data:** Permission-scoped profile view.  
- **Key actions:** Add to shortlist.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Same field-scoping check as SCR-EMP-004.  

### `SCR-EMP-006`
- **Route:** `/employer/shortlist`  
- **Role(s):** Employer  
- **Purpose:** [new] Shortlist management.  
- **Linked Feature ID(s):** `EMP-004`  
- **Entry points:** SCR-EMP-005 'Add to shortlist'.  
- **Required data:** Shortlisted candidates.  
- **Key actions:** Remove; proceed to schedule.  
- **Empty state:** Empty shortlist → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Shortlist persists across sessions.  

### `SCR-EMP-007`
- **Route:** `/employer/interviews/new`  
- **Role(s):** Employer  
- **Purpose:** [new] Interview scheduling.  
- **Linked Feature ID(s):** `EMP-004`  
- **Entry points:** SCR-EMP-006.  
- **Required data:** Shortlisted candidate, available slots.  
- **Key actions:** Propose a time; confirm.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Overlapping-time conflicts flagged, not silently double-booked.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Conflict-flagging verified.  

### `SCR-EMP-008`
- **Route:** `/employer/interviews`  
- **Role(s):** Employer  
- **Purpose:** [new] Interview list and status.  
- **Linked Feature ID(s):** `EMP-005`  
- **Entry points:** SCR-EMP-002.  
- **Required data:** Scheduled/past interviews.  
- **Key actions:** View status; cancel.  
- **Empty state:** No interviews → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Cancelled interviews remain visible in history, not deleted.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Cancelled entries remain in history view.  


## OVS

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-OVS-001` | `/overseas/countries, /overseas/countries/[slug]` | Visitor, Student | `OVS-001` |
| `SCR-OVS-002` | `/overseas/universities, /overseas/universities/[slug]` | Visitor, Student | `OVS-001` |
| `SCR-OVS-003` | `/overseas/courses` | Visitor, Student | `OVS-001` |
| `SCR-OVS-004` | `/overseas/apply` | Student | `OVS-002` |
| `SCR-OVS-005` | `/overseas/students/[id]/evaluate` | Counselor | `OVS-003` |
| `SCR-OVS-006` | `/overseas/applications/[id]` | Student | `OVS-004` |
| `SCR-OVS-007` | `/overseas/applications/[id]/documents` | Student | `OVS-005` |
| `SCR-OVS-008` | `/overseas/scholarships` | Visitor, Student | `OVS-006` |
| `SCR-OVS-009` | `/overseas/events` | Visitor, Student | `OVS-007` |

### `SCR-OVS-001`
- **Route:** `/overseas/countries, /overseas/countries/[slug]`  
- **Role(s):** Visitor, Student  
- **Purpose:** Study-destination list and country detail.  
- **Linked Feature ID(s):** `OVS-001`  
- **Entry points:** Top-nav 'Countries'.  
- **Required data:** Country profile: tuition/living-cost ranges, visa-process overview (admin-maintained, DEC-DATA-002).  
- **Key actions:** Browse; open a country; 'Book profile evaluation' CTA.  
- **Empty state:** Country with incomplete admin-entered data shows only what exists, never fabricated figures.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** No fabricated tuition/visa figures verified against admin-entered source data.  

### `SCR-OVS-002`
- **Route:** `/overseas/universities, /overseas/universities/[slug]`  
- **Role(s):** Visitor, Student  
- **Purpose:** University list and profile.  
- **Linked Feature ID(s):** `OVS-001`  
- **Entry points:** Top-nav 'Universities'; SCR-OVS-001 country page.  
- **Required data:** University eligibility, requirements, deadlines, scholarships (admin-maintained).  
- **Key actions:** Browse; open a university; 'Apply/request evaluation' CTA.  
- **Empty state:** Same no-fabrication rule as SCR-OVS-001.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Same verification as SCR-OVS-001.  

### `SCR-OVS-003`
- **Route:** `/overseas/courses`  
- **Role(s):** Visitor, Student  
- **Purpose:** Overseas course list.  
- **Linked Feature ID(s):** `OVS-001`  
- **Entry points:** Top-nav 'Courses'; university page.  
- **Required data:** Course title/level/duration/fee/intake (admin-maintained).  
- **Key actions:** Browse; filter by university/country.  
- **Empty state:** No courses for a filter → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Filter correctness verified.  

### `SCR-OVS-004`
- **Route:** `/overseas/apply`  
- **Role(s):** Student  
- **Purpose:** Overseas application/interest submission.  
- **Linked Feature ID(s):** `OVS-002`  
- **Entry points:** SCR-OVS-001/002/003 'Apply' CTA.  
- **Required data:** Selected country/university/course; student's existing profile.  
- **Key actions:** Submit interest.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Duplicate submission for the same university/course does not create a second application record.  
- **Permissions/resource scope:** Self (Student — same identity as domestic Student, per DEC-ROLE-001).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Submission enters the state sequence visible at SCR-OVS-006; duplicate-prevention verified.  

### `SCR-OVS-005`
- **Route:** `/overseas/students/[id]/evaluate`  
- **Role(s):** Counselor  
- **Purpose:** Eligibility evaluation (Counselor-side).  
- **Linked Feature ID(s):** `OVS-003`  
- **Entry points:** SCR-CNS-002 assigned-student list.  
- **Required data:** Application + profile data.  
- **Key actions:** Advance/decline the application stage; record notes.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Rejection/waitlist/deferral outcomes not yet specified — do not implement invented rules; flag to Admin instead (FEATURE_QUESTIONS.md / PRD_OPEN_ITEMS item 5).  
- **Permissions/resource scope:** Counselor, own assigned students only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Counselor cannot act on a student not assigned to them, even via direct record ID.  

### `SCR-OVS-006`
- **Route:** `/overseas/applications/[id]`  
- **Role(s):** Student  
- **Purpose:** Application status tracker (student-facing).  
- **Linked Feature ID(s):** `OVS-004`  
- **Entry points:** Overseas Student dashboard.  
- **Required data:** Current stage, history, next action.  
- **Key actions:** Read; view stage-change notifications.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A notification-send failure does not block the status update itself from being recorded/shown.  
- **Permissions/resource scope:** Self (Student).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Stage shown here always matches the authoritative record even if a notification failed to send.  

### `SCR-OVS-007`
- **Route:** `/overseas/applications/[id]/documents`  
- **Role(s):** Student  
- **Purpose:** Document upload against checklist.  
- **Linked Feature ID(s):** `OVS-005`  
- **Entry points:** SCR-OVS-006.  
- **Required data:** Checklist for the chosen country/university/course (varies, DEC-DATA-001).  
- **Key actions:** Upload each required document.  
- **Empty state:** Checklist itself not yet fully specified for every combination — show only confirmed items (PRD_OPEN_ITEMS item 6), never a fabricated generic list.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Unsupported file type/size rejected clearly.  
- **Permissions/resource scope:** Self (upload) / Counselor (verify).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** No fabricated checklist items verified.  

### `SCR-OVS-008`
- **Route:** `/overseas/scholarships`  
- **Role(s):** Visitor, Student  
- **Purpose:** Scholarship list and apply.  
- **Linked Feature ID(s):** `OVS-006`  
- **Entry points:** Top-nav.  
- **Required data:** Published scholarships (admin-maintained).  
- **Key actions:** Browse; apply.  
- **Empty state:** 'No scholarships available' (matches live reference implementation copy).  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** No eligibility rule engine — listing/apply only, never an automated eligibility decision.  
- **Permissions/resource scope:** Public view / Self (Student) apply.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Empty-state copy matches confirmed baseline.  

### `SCR-OVS-009`
- **Route:** `/overseas/events`  
- **Role(s):** Visitor, Student  
- **Purpose:** Events/workshops list and register.  
- **Linked Feature ID(s):** `OVS-007`  
- **Entry points:** Top-nav.  
- **Required data:** Published events (admin-maintained).  
- **Key actions:** Browse; register.  
- **Empty state:** 'No events available' (matches live reference implementation copy).  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Capacity/waitlist rule unspecified — open item, do not invent one.  
- **Permissions/resource scope:** Public.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Empty-state copy matches confirmed baseline.  


## VISA

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-VISA-001` | `/overseas/applications/[id]/visa (Checklist)` | Student, Counselor | `VISA-001` |
| `SCR-VISA-002` | `/overseas/applications/[id]/visa/prep` | Student | `VISA-002` |
| `SCR-VISA-003` | `/overseas/applications/[id]/visa/status` | Student, Counselor | `VISA-003` |

### `SCR-VISA-001`
- **Route:** `/overseas/applications/[id]/visa (Checklist)`  
- **Role(s):** Student, Counselor  
- **Purpose:** Visa checklist and documentation.  
- **Linked Feature ID(s):** `VISA-001`  
- **Entry points:** SCR-OVS-006.  
- **Required data:** Visa-specific checklist, evidence status.  
- **Key actions:** Upload/verify visa documents.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** An unverified document does not block viewing the checklist — only advancing past that stage.  
- **Permissions/resource scope:** Self (Student) / Counselor (verify).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Compliance copy present: EduSphere is not the visa decision-maker (matches confirmed reference-implementation language).  

### `SCR-VISA-002`
- **Route:** `/overseas/applications/[id]/visa/prep`  
- **Role(s):** Student  
- **Purpose:** Visa interview preparation.  
- **Linked Feature ID(s):** `VISA-002`  
- **Entry points:** SCR-VISA-001.  
- **Required data:** Prep material/guidance (may vary by destination).  
- **Key actions:** Read.  
- **Empty state:** Missing prep material for a specific country → fallback message, not a broken page.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Fallback state verified for an uncovered country.  

### `SCR-VISA-003`
- **Route:** `/overseas/applications/[id]/visa/status`  
- **Role(s):** Student, Counselor  
- **Purpose:** Visa approval status tracking.  
- **Linked Feature ID(s):** `VISA-003`  
- **Entry points:** SCR-VISA-001.  
- **Required data:** Status progression to final outcome.  
- **Key actions:** Read; Counselor updates status.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Self (Student) / Counselor.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Same compliance-copy requirement as SCR-VISA-001.  


## AGT

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-AGT-001` | `/overseas/agent/register` | Agent | `AGT-001` |
| `SCR-AGT-002` | `/overseas/admin/agents` | Overseas Admin | `AGT-001` |
| `SCR-AGT-003` | `/overseas/agent (Dashboard: referred students)` | Agent | `AGT-002` |
| `SCR-AGT-004` | `/overseas/agent/commissions` | Agent | `AGT-003` |
| `SCR-AGT-005` | `/overseas/agent/commissions/[id]/claim` | Agent | `AGT-004` |
| `SCR-AGT-006` | `/overseas/admin/commissions` | Overseas Admin | `AGT-004` |

### `SCR-AGT-001`
- **Route:** `/overseas/agent/register`  
- **Role(s):** Agent  
- **Purpose:** Agent self-registration.  
- **Linked Feature ID(s):** `AGT-001`  
- **Entry points:** Public Overseas login area, 'Register as Agent' link.  
- **Required data:** Agent/company details.  
- **Key actions:** Submit registration.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Public to register; self after (Pending state).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Registered Agent cannot refer students or view any data while Pending.  

### `SCR-AGT-002`
- **Route:** `/overseas/admin/agents`  
- **Role(s):** Overseas Admin  
- **Purpose:** Agent approval queue (Overseas Admin side).  
- **Linked Feature ID(s):** `AGT-001`  
- **Entry points:** Overseas Admin dashboard.  
- **Required data:** Pending Agent registrations.  
- **Key actions:** Approve; reject.  
- **Empty state:** No pending registrations → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A rejected Agent cannot bypass rejection without a new registration.  
- **Permissions/resource scope:** Overseas Admin.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Approval flips the Agent to Active and unlocks SCR-AGT-003/004 for them; every decision audit-logged (SEC-001).  

### `SCR-AGT-003`
- **Route:** `/overseas/agent (Dashboard: referred students)`  
- **Role(s):** Agent  
- **Purpose:** Referred-student roster and status.  
- **Linked Feature ID(s):** `AGT-002`  
- **Entry points:** Post-login redirect (once approved).  
- **Required data:** Own referred students, application status.  
- **Key actions:** View a referred student's status.  
- **Empty state:** No referrals yet → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Agent never sees another agent's referrals, verified server-side.  
- **Permissions/resource scope:** Self (Agent, own referrals only).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Cross-agent data isolation verified.  

### `SCR-AGT-004`
- **Route:** `/overseas/agent/commissions`  
- **Role(s):** Agent  
- **Purpose:** Commission list (auto-accrued).  
- **Linked Feature ID(s):** `AGT-003`  
- **Entry points:** SCR-AGT-003.  
- **Required data:** Commission per referral: amount, currency, status.  
- **Key actions:** View; initiate claim.  
- **Empty state:** No commissions yet → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** No commission appears before the referred application reaches the finalized+joined trigger — extends the base codebase's manual-only creation.  
- **Permissions/resource scope:** Self (Agent, own commissions).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Commission appears automatically on trigger, not on Admin's manual timing.  

### `SCR-AGT-005`
- **Route:** `/overseas/agent/commissions/[id]/claim`  
- **Role(s):** Agent  
- **Purpose:** Commission claim action.  
- **Linked Feature ID(s):** `AGT-004`  
- **Entry points:** SCR-AGT-004.  
- **Required data:** Eligible/estimated commission detail.  
- **Key actions:** Claim (generates claim reference).  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Claiming an already-claimed/paid commission is rejected, not double-processed.  
- **Permissions/resource scope:** Self (Agent).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Claim reference generated once, immutable.  

### `SCR-AGT-006`
- **Route:** `/overseas/admin/commissions`  
- **Role(s):** Overseas Admin  
- **Purpose:** Commission payout approval queue.  
- **Linked Feature ID(s):** `AGT-004`  
- **Entry points:** Overseas Admin dashboard.  
- **Required data:** Claimed commissions awaiting approval.  
- **Key actions:** Approve payout; adjust amount.  
- **Empty state:** No claims pending → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** No commission reaches paid without this explicit, separate approval — net-new endpoint the base codebase lacked.  
- **Permissions/resource scope:** Overseas Admin.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Approval action is itself audit-logged (SEC-001); Agent cannot self-approve.  


## CNS

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-CNS-001` | `/overseas/counselor (Dashboard)` | Counselor | `CNS-001` |
| `SCR-CNS-002` | `/overseas/counselor/students` | Counselor | `CNS-001` |
| `SCR-CNS-003` | `/overseas/counselor/appointments` | Counselor | `CNS-001` |

### `SCR-CNS-001`
- **Route:** `/overseas/counselor (Dashboard)`  
- **Role(s):** Counselor  
- **Purpose:** [base] Counselor landing dashboard.  
- **Linked Feature ID(s):** `CNS-001`  
- **Entry points:** Post-login redirect.  
- **Required data:** Assigned student summary, pending appointments.  
- **Key actions:** Navigate to assigned students/leads/documents/appointments.  
- **Empty state:** No assignments yet → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Counselor.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Only own-assigned data visible.  

### `SCR-CNS-002`
- **Route:** `/overseas/counselor/students`  
- **Role(s):** Counselor  
- **Purpose:** [base] Assigned-student list.  
- **Linked Feature ID(s):** `CNS-001`  
- **Entry points:** SCR-CNS-001.  
- **Required data:** Students assigned to this Counselor.  
- **Key actions:** Open a student's case (→ SCR-OVS-005).  
- **Empty state:** No assigned students → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Counselor, own assignments only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Server-side scoping to own assignments verified.  

### `SCR-CNS-003`
- **Route:** `/overseas/counselor/appointments`  
- **Role(s):** Counselor  
- **Purpose:** [base] Appointment management.  
- **Linked Feature ID(s):** `CNS-001`  
- **Entry points:** SCR-CNS-001.  
- **Required data:** Scheduled appointments.  
- **Key actions:** Schedule; reschedule; mark complete.  
- **Empty state:** No appointments → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** Counselor.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Own-scope only.  


## UNI

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-UNI-001` | `/overseas/university (Dashboard)` | University Representative | `UNI-001` |
| `SCR-UNI-002` | `/overseas/university/applications/[id]` | University Representative | `UNI-001` |

### `SCR-UNI-001`
- **Route:** `/overseas/university (Dashboard)`  
- **Role(s):** University Representative  
- **Purpose:** [base] University Rep landing.  
- **Linked Feature ID(s):** `UNI-001`  
- **Entry points:** Post-login redirect.  
- **Required data:** Applications sent to this institution.  
- **Key actions:** Navigate to applications.  
- **Empty state:** No applications yet → empty state.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** University Representative, own institution only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Rep sees only applications addressed to their own institution — least-privilege verified.  

### `SCR-UNI-002`
- **Route:** `/overseas/university/applications/[id]`  
- **Role(s):** University Representative  
- **Purpose:** [base] Application review and offer-letter tracking.  
- **Linked Feature ID(s):** `UNI-001`  
- **Entry points:** SCR-UNI-001.  
- **Required data:** Application detail, offer-letter status.  
- **Key actions:** Post admission update; upload offer letter; message student.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A Rep cannot see or act on an application not addressed to their institution.  
- **Permissions/resource scope:** University Representative, own institution only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Cross-institution isolation verified.  


## SCH *(net-new, added 2026-09-14 — propagates `DEC-SCOPE-011`/`DEC-SCOPE-010` part 1 into UX;
extended same day with `SCH-003` onboarding per `DEC-SCOPE-012`, then again with `SCH-004`/`005`/
`006` service-delivery modules per `DEC-ROLE-006`)*

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-SCH-001` | `/school/principal (Dashboard)` | Principal | `SCH-001` |
| `SCR-SCH-002` | `/school/coordinator (Dashboard)` | School Coordinator | `SCH-001` |
| `SCR-SCH-003` | `/school/coordinator/students` | School Coordinator | `SCH-001` |
| `SCR-SCH-004` | `/school/coordinator/students/new` | School Coordinator | `SCH-001` |
| `SCR-SCH-005` | `/school/coordinator/students/bulk-upload` | School Coordinator | `SCH-002` |
| `SCR-SCH-006` | `/school/coordinator/activities` | School Coordinator | `SCH-001` |
| `SCR-SCH-007` | `/school/teacher (Dashboard: assigned students)` | Teacher | `SCH-001` |
| `SCR-SCH-008` | `/school/teacher/students/[id]` | Teacher | `SCH-001` |
| `SCR-SCH-009` | `/school/parent (Dashboard: my children)` | Parent | `SCH-001` |
| `SCR-SCH-010` | `/overseas/admin/schools` (list + create, `SCR-SCH-011` merged in, 2026-09-14) | Overseas Admin | `SCH-003` |
| `SCR-SCH-012` | `/school/coordinator/team` | School Coordinator | `SCH-003` |
| `SCR-SCH-013` | `/school/invite/[token]/accept` | Principal, Teacher, Parent (whichever the token names) | `SCH-003` |
| `SCR-SCH-014` | `/school/academic-team (Dashboard: assigned students)` | Academic Team | `SCH-006` |
| `SCR-SCH-015` | `/school/academic-team/results/new` | Academic Team | `SCH-006` |
| `SCR-SCH-016` | `/school/academic-team/results/[id]` | Academic Team | `SCH-006` |
| `SCR-SCH-017` | `/school/career-counselor (Dashboard: assigned students)` | Career Counselor | `SCH-004` |
| `SCR-SCH-018` | `/school/career-counselor/students/[id]/records` | Career Counselor | `SCH-004` |
| `SCR-SCH-019` | `/school/psychometric-team (Dashboard: assigned students)` | Psychometric Team | `SCH-005` |
| `SCR-SCH-020` | `/school/psychometric-team/students/[id]/assessments` | Psychometric Team | `SCH-005` |
| `SCR-SCH-021` | `/overseas/admin/school-staff` | Overseas Admin, Super Admin | `SCH-004`, `SCH-005`, `SCH-006` |
| `SCR-SCH-022` | `/school/parent/children/[id]` (Child profile & progress) | Parent | `SCH-007` |
| `SCR-SCH-023` | `/school/parent/notifications` | Parent | `SCH-007` |
| `SCR-SCH-024` | *(embedded in `SCR-SCH-022`, the Teacher's, Coordinator's, and Principal's student-detail screens — not a standalone route)* Journey timeline section | Parent, Teacher, School Coordinator, Principal | `SCH-008` |
| `SCR-SCH-025` | `/school/coordinator/students/[id]` | School Coordinator | `SCH-008` |
| `SCR-SCH-026` | `/school/principal/students/[id]` | Principal | `SCH-008` |
| `SCR-SCH-027` | `/school/coordinator/promotion` | School Coordinator | `ENH-004` |
| `SCR-SCH-028` | *(embedded in `SCR-SCH-022` and `SCR-SCH-025` — not a standalone route)* Grade history section | Parent, School Coordinator | `ENH-004` |
| `SCR-SCH-029` | `/school/coordinator/transfers` | School Coordinator | `ENH-005` |
| `SCR-SCH-030` | `/school/coordinator/notifications` | School Coordinator | `ENH-005` |
| `SCR-SCH-031` | `/overseas/admin/school-transfers` | Overseas Admin, Super Admin | `ENH-005` |
| `SCR-SCH-032` | *(embedded in `SCR-SCH-025` and `SCR-SCH-022` — not a standalone route)* Transfer request form and history | School Coordinator, Parent | `ENH-005` |

### `SCR-SCH-001`
- **Route:** `/school/principal (Dashboard)`  
- **Role(s):** Principal  
- **Purpose:** School-wide, read-only progress overview — the one landing view a Principal needs to see how their institution's students are doing.  
- **Linked Feature ID(s):** `SCH-001`  
- **Entry points:** Post-login redirect.  
- **Required data:** Own-institution student statistics, career-progress summary, global-education status, report links, plus **published results / career-guidance-and-counselling / psychometric summary counts** (`SCH-004`/`005`/`006`, added 2026-09-14, read-only). **Exact metric set OPEN** — `DEC-SCOPE-011` confirmed the role and its read-only scope, not the dashboard's specific field list (`PRD-SCH-001`); do not copy `EVID-014`'s KPI table in as if it were confirmed.  
- **Key actions:** Open a report.  
- **Empty state:** No students on record yet → "No students yet. Ask your School Coordinator to add your first student."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A Principal never sees another institution's numbers, even in aggregate — verified server-side.  
- **Permissions/resource scope:** Principal, own institution only, read-only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Cross-institution isolation verified; no create/edit/delete action reachable from this screen (`SCH-001-AC04`).  

### `SCR-SCH-002`
- **Route:** `/school/coordinator (Dashboard)`  
- **Role(s):** School Coordinator  
- **Purpose:** Coordinator's landing view — roster size, upcoming activities, and quick access to the two things they actually do here: add students and schedule things.  
- **Linked Feature ID(s):** `SCH-001`  
- **Entry points:** Post-login redirect.  
- **Required data:** Own-institution student count, upcoming activities, recent roster changes, plus **read-only summary of published results / career-guidance-and-counselling / psychometric status** (`SCH-004`/`005`/`006`, added 2026-09-14 — Coordinator sees status only, never the content's own create/edit actions).  
- **Key actions:** Go to student roster; go to bulk upload; go to activities.  
- **Empty state:** No students yet → "No students yet. Add your first student, or upload your roster in bulk."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** School Coordinator, own institution only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Cross-institution isolation verified; Coordinator never reaches a create/edit action for results/career-guidance/psychometric content (`SCH-004-AC04`/`SCH-005-AC04`/`SCH-006-AC03`).  

### `SCR-SCH-003`
- **Route:** `/school/coordinator/students`  
- **Role(s):** School Coordinator  
- **Purpose:** Own-institution student roster — the Coordinator's working list to view or edit a student record.  
- **Linked Feature ID(s):** `SCH-001`  
- **Entry points:** SCR-SCH-002.  
- **Required data:** Own-institution students and their identifying fields.  
- **Key actions:** Edit a student; open new-student form; open bulk upload.  
- **Empty state:** No students yet → "No students yet."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A Coordinator never edits a student outside their own institution, even via a direct link.  
- **Permissions/resource scope:** School Coordinator, own institution only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Cross-institution isolation verified, including via a direct record ID (`SCH-001-AC02`).  

### `SCR-SCH-004`
- **Route:** `/school/coordinator/students/new`  
- **Role(s):** School Coordinator  
- **Purpose:** Add one student to the roster by hand.  
- **Linked Feature ID(s):** `SCH-001`  
- **Entry points:** SCR-SCH-003.  
- **Required data:** Student identifying fields. **Exact field list OPEN** — same open item as `School`'s own profile fields (`DATA_MODEL.md` §6.11); do not invent from `EVID-014`.  
- **Key actions:** Save student.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Saving with a missing required field is rejected inline, field-by-field — never a silent drop.  
- **Permissions/resource scope:** School Coordinator, own institution only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** New student is created under the acting Coordinator's own `school_id`, server-derived, never client-supplied.  

### `SCR-SCH-005`
- **Route:** `/school/coordinator/students/bulk-upload`  
- **Role(s):** School Coordinator  
- **Purpose:** Add many students at once without typing each one in by hand — download a template, fill it offline, upload it back.  
- **Linked Feature ID(s):** `SCH-002`  
- **Entry points:** SCR-SCH-002, SCR-SCH-003.  
- **Required data:** The downloadable template (exact columns **OPEN**, Contracts-phase — `DATA_MODEL.md` §6.13); the uploaded file.  
- **Key actions:** Download template; upload filled file; download the row-level result report.  
- **Empty state:** First visit offers the template download as the primary action — there is nothing to show until a file is uploaded.  
- **Loading state:** Upload/validation progress shown explicitly (row count processed so far) — a bulk operation must never look frozen.  
- **Error state:** A row that fails validation is named specifically — which row, which field, why — never a generic "upload failed." Rows that did succeed are kept, not discarded because others failed (`SCH-002-AC04`).  
- **Permissions/resource scope:** School Coordinator, own institution only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Partial-batch integrity verified — one bad row never blocks the good ones; every accepted/rejected row is individually reported, not summarized away.  

### `SCR-SCH-006`
- **Route:** `/school/coordinator/activities`  
- **Role(s):** School Coordinator  
- **Purpose:** Schedule an activity and mark who attended, for the Coordinator's own institution.  
- **Linked Feature ID(s):** `SCH-001`  
- **Entry points:** SCR-SCH-002.  
- **Required data:** Own-institution students, upcoming/past activities.  
- **Key actions:** Schedule an activity; mark attendance.  
- **Empty state:** No activities scheduled yet → "Nothing scheduled yet."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** School Coordinator, own institution only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Cross-institution isolation verified.  

### `SCR-SCH-007`
- **Route:** `/school/teacher (Dashboard: assigned students)`  
- **Role(s):** Teacher (school-side; role code `school_teacher`)  
- **Purpose:** A Teacher's own class list — only the students actually assigned to them, nothing else in the school.  
- **Linked Feature ID(s):** `SCH-001`  
- **Entry points:** Post-login redirect.  
- **Required data:** Assigned students only, attendance summary, career-activity participation.  
- **Key actions:** Open a student's detail.  
- **Empty state:** No students assigned yet → "No students assigned to you yet."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A Teacher never sees a student outside their own assignment, even within the same school.  
- **Permissions/resource scope:** Teacher, own institution AND assigned students only, read-only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Assigned-scope isolation verified — a Teacher cannot reach an unassigned student even within the same institution (`SCH-001-AC03`), and never through a `trainer` permission path (`SCH-001-AC05`).  

### `SCR-SCH-008`
- **Route:** `/school/teacher/students/[id]`  
- **Role(s):** Teacher (school-side; role code `school_teacher`)  
- **Purpose:** One assigned student's attendance, career activities, and progress — read-only.  
- **Linked Feature ID(s):** `SCH-001`  
- **Entry points:** SCR-SCH-007.  
- **Required data:** The assigned student's attendance/activity/progress record, plus their **published results / career-guidance-and-counselling / psychometric records** (`SCH-004`/`005`/`006`, added 2026-09-14, read-only — a `draft`/`verified` result is never included here).  
- **Key actions:** N/A — read-only.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Same assigned-scope deny as SCR-SCH-007, verified even via a direct record ID.  
- **Permissions/resource scope:** Teacher, own institution AND assigned students only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Cross-assignment isolation verified via direct record ID.  

### `SCR-SCH-009`
- **Route:** `/school/parent (Dashboard: my children)`  
- **Role(s):** Parent (school-side; role code `school_parent`)  
- **Purpose:** A Parent's view of their own child's — or children's — profile and progress, with a switcher if there's more than one.  
- **Linked Feature ID(s):** `SCH-001`  
- **Entry points:** Post-login redirect.  
- **Required data:** Own child(ren)'s profile/progress only, plus their **published results / career-guidance-and-counselling / psychometric records** (`SCH-004`/`005`/`006`, added 2026-09-14, read-only — a `draft`/`verified` result is never included here). **Rebuilt 2026-09-15 (`SCH-007`):** one card per child with class teacher, career-guidance / counselling / psychometric status chips, Published-result count, recommended careers, and a link to `SCR-SCH-022`; plus the school's upcoming sessions and the Parent's five latest notifications (unread count) linking to `SCR-SCH-023`. No switcher: every child is visible at once.  
- **Key actions:** Switch between children, if more than one is linked.  
- **Empty state:** No child linked yet → "No child linked to your account yet. Contact your school to get set up."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A Parent never sees a student who isn't their own linked child, even within the same institution.  
- **Permissions/resource scope:** Parent, own institution AND own child(ren) only, read-only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Own-child-only isolation verified, including for a parent with multiple children linked.  

### `SCR-SCH-010`
- **Route:** `/overseas/admin/schools`  
- **Role(s):** Overseas Admin  
- **Purpose:** Every partnered school in one list, with a create-school form on the same screen — the Admin's one stop for onboarding a new partner or checking an existing one's Coordinator status.  
- **Linked Feature ID(s):** `SCH-003`  
- **Entry points:** Overseas Admin dashboard.  
- **Required data:** All School partner records (division-wide), each with its seed Coordinator's status.  
- **Key actions:** Create a new school (name/city/state + seed Coordinator name/email in one form); view the list.  
- **Empty state:** No schools yet → "No partner schools yet. Add your first one."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Saving with a missing required field is rejected inline, field-by-field — never a silent drop.  
- **Permissions/resource scope:** Overseas Admin (and Super Admin), division-wide.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Only Overseas Admin/Super Admin reaches this screen — no other role, including School Coordinator, can list or create schools (`SCH-003-AC03`). No activation gate — the new School and its Coordinator account are usable immediately on save, not held Pending (`SCH-003-AC04`).  
- **Addendum, 2026-09-23 (`ENH-023` / `DEC-SCOPE-030`):** the per-school edit panel (`AdminSchoolEditPanel.tsx`) gains two fields — **Partnership tier** (select: Not set / Bronze / Silver / Gold / Platinum) and **Valid until** (date) — prefilled from the looked-up school. A tier change previews first; an upgrade saves immediately, a downgrade/removal shows an inline confirmation block directly under Save (lost services, "work already started can still be completed", Confirm/Cancel) before sending. Every save that changes the tier also sends the `expected_tier` precondition; a `409` (tier changed since lookup) renders as an alert and keeps the input. Success text stays `School profile updated.` (unchanged, `sch-003` E2E) followed by a tier-change sentence built from the PATCH response. No new route, no CSS change — existing classes only.  

### `SCR-SCH-011` — **corrected 2026-09-14, during `SCH-003`'s build**
**Merged into `SCR-SCH-010` above, not a separate route.** This catalogue originally specified
a dedicated `/overseas/admin/schools/new` create screen. Building `SCH-003` found the
codebase's own already-established convention instead: every other Admin-console "create
a partner record" flow (`AdminUniversityCreatePanel`, precedent `RAID.md` I-32) puts the
create form on the *same* list route via a dedicated panel component, not a separate
`/new` page. `AdminSchoolCreatePanel.tsx` follows that same convention — corrected here
to match the actual implementation rather than inventing a parallel route the rest of the
Admin console doesn't otherwise use. No functionality is missing; it simply lives at
`/overseas/admin/schools` (`SCR-SCH-010`) instead of its own URL. Kept as a record of the
correction, not deleted, per this project's traceability convention.  

### `SCR-SCH-012`
- **Route:** `/school/coordinator/team`  
- **Role(s):** School Coordinator  
- **Purpose:** Bring the rest of the school's team on board — invite the Principal, any Teachers, and Parents, and see who's already accepted.  
- **Linked Feature ID(s):** `SCH-003`  
- **Entry points:** SCR-SCH-002 (Coordinator dashboard).  
- **Required data:** Own-institution accounts and pending invites, by role.  
- **Key actions:** Invite Principal; invite Teacher; invite Parent; resend or revoke a pending invite.  
- **Empty state:** No one invited yet → "It's just you so far. Invite your Principal, teachers, or parents to give them their own login."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** An invite always names exactly one role and one recipient — sending it never silently creates the wrong role.  
- **Permissions/resource scope:** School Coordinator, own institution only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** A Coordinator can never invite someone into a different institution, even via a crafted request (`SCH-003-AC02`); an accepted invite always lands the invitee in the same school the Coordinator sent it from.  

### `SCR-SCH-013`
- **Route:** `/school/invite/[token]/accept`  
- **Role(s):** Principal, Teacher, Parent — whichever the invite token names; unauthenticated until accepted.  
- **Purpose:** Turn an invite into a real, usable login in one step.  
- **Linked Feature ID(s):** `SCH-003`  
- **Entry points:** The invite link itself (email, per `NOT-001` — the only confirmed delivery channel for this flow).  
- **Required data:** The invite token; basic account details for the invitee to confirm/complete.  
- **Key actions:** Accept and set up login.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A consumed, expired, or revoked token gets an honest, specific message — "This invite has already been used" / "This invite has expired" — never a generic broken-link page (`SCH-003-AC06`).  
- **Permissions/resource scope:** Public until the token is validated; the resulting account is scoped to the invite's own institution, never a value the invitee can change.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** A token can be accepted at most once; the created account's role and institution exactly match what the Coordinator's invite specified, never client-editable.  

### `SCR-SCH-014`
- **Route:** `/school/academic-team (Dashboard: assigned students)`  
- **Role(s):** Academic Team  
- **Purpose:** Every assigned student's result status at a glance — who still needs a result uploaded, who's Draft, who's Published.  
- **Linked Feature ID(s):** `SCH-006`  
- **Entry points:** Post-login redirect.  
- **Required data:** School-affiliated students at any school in the acting member's own portfolio (`DEC-SCOPE-013`, `SchoolStaffAssignment`), each with their latest result status per subject/term.  
- **Key actions:** Open a student to add a result; open an existing result.  
- **Empty state:** No portfolio schools assigned yet → "You haven't been assigned to any schools yet. Contact your Overseas Admin."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Academic Team never sees a student at a school outside their own portfolio, even within a school they're not assigned to.  
- **Permissions/resource scope:** Academic Team, own school portfolio only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Assigned-scope isolation verified (`SCH-006-AC05`).  

### `SCR-SCH-015`
- **Route:** `/school/academic-team/results/new`  
- **Role(s):** Academic Team  
- **Purpose:** Enter a result for one subject/term — it starts life as a Draft, invisible to everyone but Academic Team until verified and published.  
- **Linked Feature ID(s):** `SCH-006`  
- **Entry points:** SCR-SCH-014.  
- **Required data:** Student, academic year, term, subject, max marks, marks obtained (exact field list OPEN, `DATA_MODEL.md` §6.16).  
- **Key actions:** Save as Draft.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Saving with a missing required field is rejected inline, field-by-field — never a silent drop.  
- **Permissions/resource scope:** Academic Team, assigned school-affiliated students only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** A newly-saved result starts at `draft`, never any other status (`SCH-006-AC04`).  

### `SCR-SCH-016`
- **Route:** `/school/academic-team/results/[id]`  
- **Role(s):** Academic Team  
- **Purpose:** Move a result forward — verify it, then publish it — and see its full history of who did what, when.  
- **Linked Feature ID(s):** `SCH-006`  
- **Entry points:** SCR-SCH-014, SCR-SCH-015.  
- **Required data:** The result's own fields, its current status, and its `SchoolResultStatusHistory`.  
- **Key actions:** Verify (Draft → Verified); Publish (Verified → Published). **Confirmed `DEC-ROLE-007` (2026-09-14):** Verify/Publish are only offered to an Academic Team member **other than** the result's own uploader — the uploader viewing their own Draft/Verified result sees the status and history, but not an actionable Verify/Publish control (an attempt via a direct request is rejected server-side regardless).  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A stage cannot be skipped — Publish is only reachable from Verified, never directly from Draft. Verify/Publish by the uploader themselves is rejected, with a clear message ("Ask another Academic Team member to verify this result").  
- **Permissions/resource scope:** Academic Team, own school portfolio only; verify/publish further restricted to a different member than the uploader.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Gate integrity verified — no skip-stage transition reachable through this screen's own actions (`SCH-006-AC04`).  

### `SCR-SCH-017`
- **Route:** `/school/career-counselor (Dashboard: assigned students)`  
- **Role(s):** Career Counselor  
- **Purpose:** Every assigned student, one list — the Career Counselor's starting point for adding a guidance session, a counselling note, or a recommendation.  
- **Linked Feature ID(s):** `SCH-004`  
- **Entry points:** Post-login redirect.  
- **Required data:** School-affiliated students at any school in the acting Counselor's own portfolio (`DEC-SCOPE-013`).  
- **Key actions:** Open a student's records.  
- **Empty state:** No portfolio schools assigned yet → "You haven't been assigned to any schools yet. Contact your Overseas Admin."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Career Counselor never sees a student at a school outside their own portfolio.  
- **Permissions/resource scope:** Career Counselor, own school portfolio only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Assigned-scope isolation verified (`SCH-004-AC02`).  

### `SCR-SCH-018`
- **Route:** `/school/career-counselor/students/[id]/records`  
- **Role(s):** Career Counselor  
- **Purpose:** One student's whole career-guidance-and-counselling history, and the place to add to it.  
- **Linked Feature ID(s):** `SCH-004`  
- **Entry points:** SCR-SCH-017.  
- **Required data:** The student's guidance sessions, counselling notes, and recommendations, in order (exact field list OPEN, `DATA_MODEL.md` §6.17).  
- **Key actions:** Add a guidance session, counselling note, or recommendation.  
- **Empty state:** No records yet → "No career guidance or counselling recorded yet."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A new record is always attributed to the acting Career Counselor, never client-supplied.  
- **Permissions/resource scope:** Career Counselor (write), School Coordinator/Parent/Student/Teacher (read-only) — all own institution/scope only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Only Career Counselor writes; every reader stays read-only (`SCH-004-AC04`).  

### `SCR-SCH-019`
- **Route:** `/school/psychometric-team (Dashboard: assigned students)`  
- **Role(s):** Psychometric Team  
- **Purpose:** Every assigned student, one list — who needs an assessment assigned, who has a report pending upload.  
- **Linked Feature ID(s):** `SCH-005`  
- **Entry points:** Post-login redirect.  
- **Required data:** School-affiliated students at any school in the acting member's own portfolio (`DEC-SCOPE-013`), each with their assessment status.  
- **Key actions:** Open a student's assessments.  
- **Empty state:** No portfolio schools assigned yet → "You haven't been assigned to any schools yet. Contact your Overseas Admin."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Psychometric Team never sees a student at a school outside their own portfolio.  
- **Permissions/resource scope:** Psychometric Team, own school portfolio only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Assigned-scope isolation verified (`SCH-005-AC02`).  

### `SCR-SCH-020`
- **Route:** `/school/psychometric-team/students/[id]/assessments`  
- **Role(s):** Psychometric Team  
- **Purpose:** One student's assessments — assign a new one, or upload a report against one already assigned.  
- **Linked Feature ID(s):** `SCH-005`  
- **Entry points:** SCR-SCH-019.  
- **Required data:** The student's assigned/completed assessments and their reports (exact taxonomy OPEN, `DATA_MODEL.md` §6.18).  
- **Key actions:** Assign an assessment; upload a report.  
- **Empty state:** No assessments yet → "No assessments assigned yet."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A new assessment/report is always attributed to the acting Psychometric Team member, never client-supplied.  
- **Permissions/resource scope:** Psychometric Team (write), School Coordinator/Parent/Student/Teacher (read-only) — all own institution/scope only.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Only Psychometric Team writes; every reader stays read-only (`SCH-005-AC04`).  

### `SCR-SCH-021` *(added 2026-09-14, propagating `DEC-SCOPE-014`)*
- **Route:** `/overseas/admin/school-staff`  
- **Role(s):** Overseas Admin, Super Admin  
- **Purpose:** Create an Academic Team, Career Counselor, or Psychometric Team account and assign the school(s) they cover — the only way any of these three accounts comes into existence.  
- **Linked Feature ID(s):** `SCH-004`, `SCH-005`, `SCH-006`  
- **Entry points:** Admin console navigation (extends `SCR-ADM-001`'s existing user-management area, `ADM-001`/`004` — not a standalone new nav section).  
- **Required data:** Existing accounts of these three roles, each with their current school portfolio; the list of partner schools to assign from.  
- **Key actions:** Create account (name, role, contact details); assign/remove one or more schools from their portfolio.  
- **Empty state:** No specialized-role staff yet → "No Academic Team, Career Counselor, or Psychometric Team accounts yet. Create one to start assigning results, career guidance, or psychometric work to a school."  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Creating an account with zero schools assigned is allowed (a portfolio can be filled in later) but shows an explicit warning — "This account has no assigned schools yet and won't be able to act on any student until you assign at least one" — never a silent no-op account.  
- **Permissions/resource scope:** Overseas Admin, Super Admin only — `school_coordinator` has no access to this screen, even for their own institution's staff (`DEC-SCOPE-014`).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Only Overseas Admin/Super Admin can reach this screen or its underlying action, even via a direct request — a School Coordinator attempting it gets 403 (`DEC-SCOPE-014`).  


### `SCR-SCH-022` *(added 2026-09-15, propagating `DEC-SCOPE-015`)*
- **Route:** `/school/parent/children/[id]`
- **Role(s):** Parent (`school_parent`)
- **Purpose:** One child's complete profile & progress — the `EVID-014` §23 list as far as confirmed modules can supply it.
- **Linked Feature ID(s):** `SCH-007`
- **Entry points:** "View full profile & progress" on `SCR-SCH-009`; a notification's "Open" link.
- **Required data:** `GET /school/students/{id}/overview` — profile (school, grade, DOB, class teacher), career guidance sessions, counselling notes, recommended careers, psychometric assessments with status, Published results table, activities attended (present/absent), upcoming sessions.
- **Key actions:** Read-only. Back to my children.
- **Empty state:** Each section carries its own honest empty line ("No career guidance session recorded yet", "No published results yet. A result appears here only once the school has published it", …). **No Skills / Portfolio / Overseas section is rendered at all** until a confirmed module exists for it.
- **Loading state:** Server-rendered; no client loading state.
- **Error state:** A student not linked to this Parent → "Access unavailable" with a back link (API 403, `SCH-007-AC02`), never a partial page.
- **Permissions/resource scope:** Own child(ren) only, verified server-side even via this direct record ID.
- **Responsive behavior:** Single-column stack on mobile; every table inside `table-wrap` (no horizontal page scroll).
- **Accessibility requirements:** Semantic headings per section, keyboard-navigable links, status chips carry text not colour alone.
- **Desktop/tablet/mobile behavior:** As above; status grid collapses to two columns on mobile.
- **Visual-reference mapping:** None — not inspected (see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2). Do not claim parity.
- **Acceptance evidence needed:** `SCH-007-AC01`/`AC02`/`AC03`/`AC05` — `test_sch_007_parent_portal.py`, `sch-007-parent-portal.spec.ts`.
- **`SCH-008` addendum, 2026-09-15:** a "Journey timeline" card is appended to this screen — a vertical, chronologically-ordered rail (colored node per category: profile/career/psychometric/academic/activity, connecting line, tinted category badge) reading `GET /school/students/{id}/timeline`. Same own-child scope; a load failure shows "Timeline is unavailable right now." without blocking the rest of the page. The identical component also renders on the Teacher's per-student detail screen (`/school/teacher/students/[id]`, within their assigned-student scope) — see `SCR-SCH-024`.

### `SCR-SCH-023` *(added 2026-09-15, propagating `DEC-SCOPE-015`)*
- **Route:** `/school/parent/notifications`
- **Role(s):** Parent (`school_parent`)
- **Purpose:** The Parent's full notification feed — assessment assigned / report ready, guidance or counselling recorded, session scheduled, result Published.
- **Linked Feature ID(s):** `SCH-007`
- **Entry points:** Parent nav "Notifications"; "All notifications" on `SCR-SCH-009`.
- **Required data:** `GET /workflows/notifications` (own rows only — keyed on the signed-in user).
- **Key actions:** Read; "Open" follows the notification's `action_url` to the child page or dashboard.
- **Empty state:** "No notifications yet. You will be notified here when an assessment, counselling session, workshop, or result is recorded for your child."
- **Loading state:** Server-rendered.
- **Error state:** Standard "Access unavailable" card.
- **Permissions/resource scope:** Own notifications only.
- **Responsive behavior:** Table inside `table-wrap`.
- **Accessibility requirements:** Unread marked with a text badge ("new"), not colour alone.
- **Desktop/tablet/mobile behavior:** Single column on mobile.
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** `SCH-007-AC04` — `test_sch_007_parent_portal.py`, `sch-007-parent-portal.spec.ts`.


### `SCR-SCH-024` *(added 2026-09-15, propagating `DEC-SCOPE-016`)*
- **Route:** Embedded section, not a standalone route — appears on `SCR-SCH-022` (`/school/parent/children/[id]`), the Teacher's `/school/teacher/students/[id]`, and (added 2026-09-15, later the same day) `SCR-SCH-025`/`SCR-SCH-026` for Coordinator/Principal.
- **Role(s):** Parent (own child), Teacher (assigned student), School Coordinator, Principal (own institution) — all four via the same shared `SchoolStudentDetailPanel.tsx`, each their own page/route
- **Purpose:** The narrow Student Journey Timeline — a chronological rail of every event already recorded for this student across `SCH-001`/`004`/`005`/`006`.
- **Linked Feature ID(s):** `SCH-008`
- **Entry points:** Scrolled section on the student's own detail page.
- **Required data:** `GET /school/students/{id}/timeline` — `events[]` with `date`, `category`, `title`, `detail`.
- **Key actions:** Read-only.
- **Empty state:** Never truly empty — a "profile created" event always exists once the student is on the roster.
- **Loading state:** Server-rendered; a fetch failure shows "Timeline is unavailable right now." without blocking the rest of the page.
- **Error state:** Covered by the parent page's own "Access unavailable" (a caller outside scope never reaches this section at all — enforced before the page renders).
- **Permissions/resource scope:** Same as `SCR-SCH-022`/the Teacher detail page — own child / assigned student / own institution only depending on role, verified server-side even via direct record ID.
- **Responsive behavior:** Single vertical rail, two-column grid (node + content) at every width — no horizontal scroll, confirmed at 400px viewport.
- **Accessibility requirements:** Each event's category is stated in text (a badge label), never conveyed by color alone.
- **Desktop/tablet/mobile behavior:** Identical layout at all widths — the rail is inherently single-column.
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** `SCH-008-AC01`–`AC04` — `test_sch_008_student_timeline.py`, `sch-008-student-timeline.spec.ts`.


### `SCR-SCH-025` *(added 2026-09-15, later the same day, propagating `DEC-SCOPE-016`'s addendum)*
- **Route:** `/school/coordinator/students/[id]`
- **Role(s):** School Coordinator
- **Purpose:** Read-only student header plus `SCR-SCH-024`'s Journey Timeline, own institution only.
- **Linked Feature ID(s):** `SCH-008`
- **Entry points:** A "Timeline" action on each roster row of `/school/coordinator/students`.
- **Required data:** `GET /school/students/{id}`, `GET /school/students/{id}/timeline`.
- **Key actions:** Read-only; write actions (add/edit/link parent) stay on the roster screen, not duplicated here.
- **Empty state:** N/A — a student always has at least a "profile created" event.
- **Loading state:** Server-rendered; a timeline fetch failure shows "Timeline is unavailable right now." without blocking the header.
- **Error state:** A student at a different institution → "Access unavailable" with a back link (403).
- **Permissions/resource scope:** Own institution only (`SCH-001-AC02`), verified server-side even via direct record ID.
- **Responsive behavior:** Same as `SCR-SCH-024`.
- **Accessibility requirements:** Same as `SCR-SCH-024`.
- **Desktop/tablet/mobile behavior:** Same as `SCR-SCH-024`.
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** `SCH-008-AC01`/`AC02` — `sch-008-student-timeline.spec.ts` (Coordinator case).

### `SCR-SCH-026` *(added 2026-09-15, later the same day, propagating `DEC-SCOPE-016`'s addendum)*
- **Route:** `/school/principal/students/[id]`
- **Role(s):** Principal
- **Purpose:** Read-only student header plus `SCR-SCH-024`'s Journey Timeline, own institution only.
- **Linked Feature ID(s):** `SCH-008`
- **Entry points:** A "Timeline" action on each row of the dashboard's roster table.
- **Required data:** `GET /school/students/{id}`, `GET /school/students/{id}/timeline`.
- **Key actions:** Read-only.
- **Empty state:** N/A.
- **Loading state:** Server-rendered; a timeline fetch failure shows "Timeline is unavailable right now." without blocking the header.
- **Error state:** A student at a different institution → "Access unavailable" with a back link (403).
- **Permissions/resource scope:** Own institution only (`SCH-001-AC02`), verified server-side even via direct record ID.
- **Responsive behavior:** Same as `SCR-SCH-024`.
- **Accessibility requirements:** Same as `SCR-SCH-024`.
- **Desktop/tablet/mobile behavior:** Same as `SCR-SCH-024`.
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** `SCH-008-AC01`/`AC02` — `sch-008-student-timeline.spec.ts` (Principal case).


## RPT

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-RPT-001` | `/it/admin/reports` | IT Admin, Placement Team | `RPT-001`, `ADM-007` |

### `SCR-SCH-027` *(added 2026-09-19, `ENH-004` / `DEC-SCOPE-020`)*
- **Route:** `/school/coordinator/promotion`
- **Role(s):** School Coordinator
- **Purpose:** Academic-year rollover: promote (grade + 1) or hold back the selected students into the active academic year, own institution only.
- **Linked Feature ID(s):** `ENH-004`
- **Entry points:** "Promotion" item in the Coordinator navigation.
- **Required data:** `GET /school/students`, `GET /school/academic-years/active`, `POST /school/students/promotions`.
- **Key actions:** Filter by grade level; select students (or all shown); choose Promote or Hold back per student; optional replacement label; "Review changes (N)" then an explicit "Confirm promotion" (or Cancel / Escape). At most 500 students per request.
- **Empty state:** "No students on the roster yet" with a link to the roster / "No students match this filter" with "Show all grades" / "No active academic year" (nothing to act on until an Overseas Admin activates one).
- **Loading state:** Server-rendered. While submitting, the confirm button is disabled and reads "Promoting…", and the rows, the grade filter and select-all are read-only so what is on screen is what was sent (the list is `aria-busy`); the server's per-row outcome is shown as soon as it returns, then the list is refreshed in a transition.
- **Error state:** 403/409/422, a dropped connection, and a 200 whose body is not a report (a proxy page, an empty object: "could not be read, repeating it is safe") render an `alert` that takes focus (so it is scrolled into view) and keep the selection (a repeat is safe). A 401 says "Your session has expired" with a "Sign in again" link. Per-row failures show "Not changed" or "Skipped" plus a plain-language reason beside the row's own controls (each stable reason code is worded for the coordinator; the API's own message is only the fallback for an unknown reason) and stay selected for a corrected retry. Known-to-fail rows (Grade 12, no grade level) carry an advisory hint before submit. A student already in the active year is locked ("Already in <year>").
- **Permissions/resource scope:** Coordinator only, enforced twice: the page shows "Access unavailable — School Coordinator role required" to any other role (Parent, Teacher, Principal, Overseas Admin) without loading the roster, and the API returns 403. The school is server-derived, never client-supplied.
- **Responsive behavior:** Each student is a stacked card (visible "Action" and "New label" labels) until the list itself is at least 720px wide, then a header row replaces the per-row labels. This is a container query on the list, not a viewport breakpoint: keyed to the viewport it overflowed at 768 and 1024px because the portal sidebar leaves the content area much narrower than the viewport (found in the browser run). The action bar is sticky so the primary action stays reachable; no horizontal scroll at 320/768/1024/1440px (asserted in the e2e; passing). Controls shrink to their own cell: the global `.search` class has `min-width: 240px`, which pushed the label input out of its card at 320px and over the status text in a phone-landscape (844x390) columned row, so the screen overrides it. On touch devices (`pointer: coarse`) the controls are 16px so iOS does not zoom the page on focus. Verified in the browser at 14 widths from 320 to 1920px, including 640x400 (a 200% zoom equivalent) and phone landscape.
- **Accessibility requirements:** Real labels on every control; the checkbox is labelled by the student's name, code and grade; a keyboard-reachable confirmation step (focus moves to Confirm; Escape/Cancel returns focus to Review); focus moves to the result summary (a status region) or, after a failure, to the error alert; the filter's "Showing N of M" is a polite live region; outcomes are stated in text as well as colour.
- **Desktop/tablet/mobile behavior:** One list structure at every width, restyled by the list's own width (cards below 720px, columned rows above). At 1024px with the sidebar open the list is still in the card layout.
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** `SchoolPromotionPanel.test.tsx` (component behavior, passing), `SchoolCoordinatorPromotionPage.test.tsx` (role guard, passing); `enh-004-student-promotion.spec.ts` (browser: passing, run repeatedly on an isolated stack, 2026-09-20; it closes the academic year it creates and asserts the active years are restored); `test_enh_004_student_promotion.py`. An independent exploratory browser pass (2026-09-20) found nine issues; seven were fixed and re-verified (see the plan's execution log rows 16-19); the other two are app-wide and are not ENH-004.

### `SCR-SCH-028` *(added 2026-09-19, `ENH-004`)*
- **Route:** Embedded section, not a standalone route — appears on `SCR-SCH-022` (`/school/parent/children/[id]`) and `SCR-SCH-025` (`/school/coordinator/students/[id]`).
- **Role(s):** Parent (own child), School Coordinator (own institution)
- **Purpose:** Read-only list of a student's promotions and hold-backs (date, outcome, "Moved from X to Y" / "Kept in X", academic year).
- **Linked Feature ID(s):** `ENH-004`
- **Required data:** `GET /school/students/{id}/grade-history`.
- **Empty state:** "No promotions recorded yet."
- **Error state:** "Grade history is unavailable right now." without blocking the rest of the page.
- **Permissions/resource scope:** The same own-scope loader as the overview and timeline.
- **Responsive behavior:** Reuses the Journey Timeline's single-column rail (`SCR-SCH-024`), so no horizontal scroll at any width.
- **Accessibility requirements:** The outcome is a text badge plus a sentence, never colour alone; loaded in parallel with the timeline.
- **Acceptance evidence needed:** `SchoolGradeHistory.test.tsx` (passing); `enh-004-student-promotion.spec.ts` (browser: passing, 2026-09-20).

### `SCR-SCH-029` *(added 2026-09-21, `ENH-005` / `DEC-SCOPE-022`)*
- **Route:** `/school/coordinator/transfers`
- **Role(s):** School Coordinator
- **Purpose:** Ask an admin to move a student to or from this school: the requests this school has filed (either direction), with cancel for a pending one, and a form to ask for a student at another school by Student ID.
- **Linked Feature ID(s):** `ENH-005`
- **Entry points:** "Transfers" item in the Coordinator navigation; a coordinator files an outgoing request from the student's own page (SCR-SCH-032).
- **Required data:** GET /school/transfer-requests (status filter, limit/offset), POST /school/transfer-requests/incoming, POST /school/transfer-requests/{id}/cancel.
- **Key actions:** Filter by status (Pending review / All / Approved / Rejected / Cancelled); enter an 8-character Student ID and "Request student"; "Cancel request" on a pending row; "Load more".
- **Empty state:** "No pending requests." / "No transfer requests yet." / "No <status> requests."
- **Loading state:** Server-rendered first page. A filter change replaces the rows behind a skeleton; "Load more" appends and reads "Loading…"; buttons are disabled while a request is in flight (a ref guards a same-task double click).
- **Error state:** API errors (403/409/422/429) and a dropped connection render an alert that takes focus and keep the entry. Filing by Student ID always answers the same neutral message whether or not the code exists, so the screen cannot be used to probe for students at other schools; the resulting row shows "Student details are shown once approved" and discloses no name.
- **Permissions/resource scope:** Coordinator only, enforced twice: the page shows "School Coordinator role required" to any other role and the API returns 403. The filing school is server-derived from the caller's profile, never client-supplied; only the filing school sees a request.
- **Responsive behavior:** Single column; rows wrap; no horizontal scroll at 320/768/1024/1440px (asserted in the e2e; passing).
- **Accessibility requirements:** Real labels on every control; status messages in a polite live region; errors take focus; the row's actions are named with the student or code they act on; state is text, not colour alone.
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** SchoolTransfersPanel.test.tsx, SchoolIncomingTransferForm.test.tsx (passing); enh-005-school-transfer.spec.ts (browser, isolated stack, 2026-09-21); test_enh_005_filing.py, test_enh_005_coordinator_reads.py.

### `SCR-SCH-030` *(added 2026-09-21, `ENH-005` / `DEC-SCOPE-022`)*
- **Route:** `/school/coordinator/notifications`
- **Role(s):** School Coordinator
- **Purpose:** Read the in-app notices the school receives, including whether a transfer request was approved or rejected (a coordinator had no screen for these until the second browser QA pass).
- **Linked Feature ID(s):** `ENH-005`
- **Entry points:** "Notifications" item in the Coordinator navigation.
- **Required data:** GET /workflows/notifications, keyed on the signed-in user (never a client-supplied id); the same source the Parent's SCR-SCH-023 reads.
- **Key actions:** Read only.
- **Empty state:** "No notifications yet. You will be told here when a transfer request is decided, or a student joins your school."
- **Loading state:** Server-rendered.
- **Error state:** An "Access unavailable" card with the reason and a link back to login when the notices cannot be loaded.
- **Permissions/resource scope:** The page shows "Access unavailable — School Coordinator role required" to any other role. The feed is the signed-in user's own notices only.
- **Responsive behavior:** A list of notices in the same `.link-list` rows the transfers screen uses (not a table: AC-24, found by the final browser verification), so rows stack and nothing can widen the page; verified at 320/375/768/1024/1440px.
- **Accessibility requirements:** A labelled list (`aria-label="Notifications"`); the unread state is the text badge "new", not colour alone; the message is rendered as plain text.
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** SchoolNotificationList.test.tsx (passing); enh-005-school-transfer.spec.ts asserts both the requester's and the gaining school's notice (browser, 2026-09-21).

### `SCR-SCH-031` *(added 2026-09-21, `ENH-005` / `DEC-SCOPE-022`)*
- **Route:** `/overseas/admin/school-transfers`
- **Role(s):** Overseas Admin, Super Admin
- **Purpose:** Decide school transfer requests: review each pending request with a preview of what approval will move, then approve or reject it.
- **Linked Feature ID(s):** `ENH-005`
- **Entry points:** "School Transfers" item in the Overseas Admin navigation.
- **Required data:** GET /overseas-admin/school-transfer-requests (status filter, limit/offset), POST .../{id}/approve, POST .../{id}/reject.
- **Key actions:** Filter by status; "Approve transfer of <student> to <school>" then an explicit "Confirm approval" (or Cancel / Escape); "Reject" with an optional reason.
- **Empty state:** "No pending transfer requests." / "No transfer requests yet." / "No <status> requests."
- **Loading state:** "Loading transfer requests…"; the confirm step disables its buttons while the approval runs.
- **Error state:** API errors (including 409 "Another change to this student is in progress; retry") and a dropped connection render an alert that takes focus; nothing is changed on failure (approval is one transaction).
- **Permissions/resource scope:** Overseas Admin and Super Admin only. A School Coordinator, of either school, gets 403 from the API and "role required" from the page; neither school can approve a transfer alone.
- **Responsive behavior:** The two confirm buttons sit side by side, not as stretched bars. No page-level horizontal scroll at 320/768/1024/1440px (asserted in the e2e). This is its own route rather than the portal's generic section (browser QA N3): the queue follows the title directly, with no read-only table above it.
- **Accessibility requirements:** Keyboard only: Enter on Approve moves focus to Confirm, Escape returns focus to Approve (asserted in the e2e); every action is named with the student and destination; outcomes are text.
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** AdminSchoolTransferPanel.test.tsx, AdminTransferRow.test.tsx (passing); enh-005-school-transfer.spec.ts (browser, 2026-09-21, keyboard approval); test_enh_005_admin_reads.py, test_enh_005_approve.py, test_enh_005_concurrency.py.

### `SCR-SCH-032` *(added 2026-09-21, `ENH-005` / `DEC-SCOPE-022`)*
- **Route:** Embedded section, not a standalone route — the request form and history appear on SCR-SCH-025 (/school/coordinator/students/[id]); the history (read-only) also appears on SCR-SCH-022 (/school/parent/children/[id]).
- **Role(s):** School Coordinator, Parent
- **Purpose:** The Coordinator asks for one of their students to move to another partner school (a disclosure on the student's page); the Coordinator and the Parent read that student's transfer history ("Moved from X to Y").
- **Linked Feature ID(s):** `ENH-005`
- **Entry points:** "Request a transfer" disclosure on the student's page (Coordinator only), collapsed, directly under the student header (moved up from the end of the page after browser QA N4).
- **Required data:** Props read on the server with the rest of the page: the destination schools and any pending request; GET /school/students/{id}/transfer-history; POST /school/students/{id}/transfer-requests.
- **Key actions:** Choose a destination school, optional reason (500 characters), "Request transfer". Reversible, so there is no confirm step; the request can be cancelled from SCR-SCH-029.
- **Empty state:** "No other partner schools are available." / "Transfers are unavailable right now." / no history section content when the student never moved.
- **Loading state:** None needed (server-rendered props); the button reads "Sending request…" and the form is read-only while submitting.
- **Error state:** A field error for a missing school; 401/403/409/422/429 and a dropped connection render an alert that takes focus and keep the entry.
- **Permissions/resource scope:** Filing: the student's own school's Coordinator only; an unknown or foreign student answers the same 403. History: the Coordinator of the student's current school and a Parent linked to the child.
- **Responsive behavior:** The destination <select> is width:100% inside a min-width:0 field, so one very long school name cannot widen the page (a jsdom-only fix first missed this; the Playwright spec now creates a 200-character school name and asserts no horizontal overflow with the form open).
- **Accessibility requirements:** Real labels; the select's error is tied by aria-describedby; a polite live region (`role="status"`) is rendered with the form, empty, so it exists before the result and the confirmation or pending text appears in that same element; history is text.
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** SchoolTransferRequestForm.test.tsx, SchoolTransferHistory.test.tsx (passing); enh-005-school-transfer.spec.ts (browser, 2026-09-21); test_enh_005_filing.py.

### `SCR-SCH-033` *(added 2026-09-22, `ENH-011` / `DEC-SCOPE-026`)*
- **Route:** `/school/career-counselor/skills`
- **Role(s):** Career Counselor
- **Purpose:** The counselor's Soft Skills / Digital Skills batches across their school portfolio, and the form that creates one.
- **Linked Feature ID(s):** `ENH-011`
- **Entry points:** "Skills" item in the Career Counselor navigation.
- **Required data:** Server-rendered: GET /auth/me, GET /school/career-counselor/skill-batches?limit=25&offset=0, GET /school/portfolio-students (the schools a batch can be created for). Client: the same list endpoint for filtering and "Load more"; POST /school/career-counselor/skill-batches.
- **Key actions:** Filter by module and by open/closed; "Load more"; create a batch (school, module, title, topic, trainer, dates), which opens the new batch.
- **Empty state:** "No skills batches yet." with a "Create a batch" button that moves focus to the Title field; "No batches match these filters."; a counselor with no school assignment sees "You are not assigned to any school yet." and no form.
- **Loading state:** First paint is server-rendered; `loading.tsx` skeleton on navigation; a filter change swaps the rows for a skeleton; "Load more" keeps the rows.
- **Error state:** Title, start date and date order are checked in the browser (no request sent) and the first invalid field takes focus; a server 422 marks the field and the alert says "Check the highlighted fields."; 401 offers "Sign in again"; a dropped connection keeps the entry; a failed list read offers "Try again".
- **Permissions/resource scope:** Career Counselor only (403 before any lookup); the school picker and the list are the counselor's `SchoolStaffAssignment` portfolio.
- **Responsive behavior:** Fits 390px (verified: page width 390 at a 390px viewport); filters wrap; buttons are at least 44px tall on phones.
- **Accessibility requirements:** "Skills batches" is the page `h1`; real labels on every control; errors tied by `aria-describedby` with `aria-invalid`; the list is a `role="list"` with `aria-busy` while loading; alerts take focus.
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav. Mobile: single column, no horizontal scroll.
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** SchoolSkillBatchesPanel.test.tsx, lib/skills.test.ts (passing); enh-011-skills.spec.ts; the browser QA record `docs/quality/ENH-011_BROWSER_QA_2026-09-22.md`.

### `SCR-SCH-034` *(added 2026-09-22, `ENH-011` / `DEC-SCOPE-026`)*
- **Route:** `/school/career-counselor/skills/[id]`
- **Role(s):** Career Counselor
- **Purpose:** One batch end to end: its details, the enrolled students and their status, sessions with attendance, and assessments with scores.
- **Linked Feature ID(s):** `ENH-011`
- **Entry points:** A batch row on SCR-SCH-033, or straight after creating a batch.
- **Required data:** Server-rendered: GET /auth/me, GET /school/career-counselor/skill-batches/{id} (batch, enrolments with attendance summary and scores, sessions, assessments), GET /school/portfolio-students (filtered to the batch's school). Writes: PATCH .../skill-batches/{id}; POST .../{id}/enrollments; PATCH .../skill-enrollments/{id}; POST .../{id}/sessions; PUT .../skill-sessions/{id}/attendance; POST .../{id}/assessments; PUT .../skill-assessments/{id}/scores.
- **Key actions:** Edit details; close/reopen; enrol students (filtered checkbox picker); mark completed / certify (with a confirm step, since a certificate cannot be undone) / withdraw / re-enrol; add a session and take attendance ("Mark all present", "Save attendance"); add an assessment and record scores with remarks.
- **Empty state:** "No students enrolled yet."; "Every student at <school> is already enrolled."; "No sessions yet. Add one to start taking attendance."; "No assessments yet. Add one to record scores."; a certified row reads "No further changes".
- **Loading state:** `loading.tsx` skeleton on navigation; each save keeps the content visible, marks the section `aria-busy` and shows "Saving…"; a success message clears after 8 seconds.
- **Error state:** A score outside 0..max is caught on its field before any request; 409s (closed batch, duplicate session date, refused transition, transferred-out student) and 5xx/401/dropped connections render an alert that takes focus, and the entry is kept. Unsaved attendance is guarded on reload and on in-app navigation.
- **Permissions/resource scope:** Career Counselor only; a batch outside the portfolio is a masking 404; a student outside it is 403; a student who has transferred is read-only ("Transferred out") and excluded from attendance, scores and the picker.
- **Responsive behavior:** Fits 390px (the page grid uses `minmax(0,1fr)` so the roster table scrolls inside `.table-wrap`); buttons at least 44px tall on phones.
- **Accessibility requirements:** The batch title is the page `h1`; the roster is a table with row headers; attendance and enrolment use `fieldset`/`legend` with labelled checkboxes; score inputs read "Score for <student> (out of <max>)"; focus is kept through the certify confirmation and after a status change.
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav. Mobile: single column; only the roster table scrolls sideways.
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** SchoolSkillBatchHeader/Enrolments/Attendance/Scores test files (passing); enh-011-skills.spec.ts; `docs/quality/ENH-011_BROWSER_QA_2026-09-22.md`.

### `SCR-SCH-035` *(added 2026-09-23, `ENH-013` / `DEC-SCOPE-028`)*
- **Route:** one thin route per role, same body: `/school/{coordinator,principal,teacher}/students/[id]/360`, `/school/parent/children/[id]/360`, `/school/{academic-team,career-counselor,psychometric-team}/students/[id]/360`; `?tab=<key>` selects a tab.
- **Role(s):** School Coordinator, Principal, Teacher (assigned students), Parent (linked children), Academic Team, Career Counselor, Psychometric Team (own school portfolio).
- **Purpose:** The Student 360° view / Career Passport: one student's record in 16 tabs (Overview, Personal Details, Academic Records, Attendance, Examination Results, Career Guidance, Psychometric Assessment, Skills, Foreign Languages, English Testing, Activities, Certificates, Documents, Teacher Remarks, Parent Communication, Edusphere Programs), each scoped to what the viewing role may already read.
- **Linked Feature ID(s):** `ENH-013`
- **Entry points:** "Open 360° view" on the Coordinator/Principal/Teacher student page (SCR-SCH-025 family) and on the Parent's child page; a "Student 360° view" list on the Academic Team, Career Counselor and Psychometric Team dashboards.
- **Required data:** Server-rendered: GET /auth/me, GET /school/students/{id}/360-view. Client: PATCH /school/students/{id}/career-goal (Career Counselor only). Switching tabs makes no request (`history.replaceState`).
- **Key actions:** Switch tabs (click, arrows, Home/End); Career Counselor sets/edits/clears the career goal on the Overview tab; follow a psychometric report link (same-origin or https only).
- **Empty state:** Every tab without records shows a `role="status"` message naming who records the data (e.g. "No published results yet. Results appear after the Academic Team publishes them."); tabs a role cannot read show "This section is not available for your role."; sources not built yet show a "not tracked yet (ENH-030 / ENH-025 / ENH-013b / ENH-014)" note.
- **Loading state:** `loading.tsx` skeleton (header, tab list, panel) with `aria-busy` on navigation; the career-goal form shows "Saving…", keeps the input read-only (still focusable) and disables Save.
- **Error state:** 401/403/404/network → the shared Access Unavailable card with the server's reason (e.g. "This student is not assigned to you"); career goal: the server's message, or "The career goal could not be saved. Please try again." for a 5xx, and a kept-entry message for a dropped connection, with focus returned to the input.
- **Permissions/resource scope:** The shared 7-role loader; per-tab projection so no role sees more than elsewhere (`RBAC_MATRIX.md` ENH-013 addendum); results Published only; career goal writable by the Career Counselor only.
- **Responsive behavior:** Desktop (>980px): vertical tab list, sticky below the portal top bar and scrolling on its own. ≤980px: a horizontally scrolling tab strip; the page never scrolls sideways (verified: page width = viewport at 390 and 768); tabs ≥44px tall.
- **Accessibility requirements:** WAI-ARIA tabs (roving tabindex, arrows in both axes, Home/End, visible focus); each tab's state (count / "no records yet" / "not available for your role") is in its accessible name, not colour alone; one `h1` (the student), `h2` per panel; tables named once.
- **Desktop/tablet/mobile behavior:** As above; verified by browser QA at 1440, 1366×620, 1024, 768 and 390.
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** `Student360Tabs`, `Student360Panels`, `Student360Page`, `CareerGoalForm`, `SchoolStudentDetailPanel` and `lib/student360` vitest files; `test_enh_013_*.py`; `tests/e2e/enh-013-student-360.spec.ts`; `docs/quality/ENH-013_BROWSER_QA_2026-09-23.md`.

### `SCR-SCH-036` *(added 2026-09-23, `ENH-023` / `DEC-SCOPE-030`)*
- **Route:** `/school/principal/notifications`
- **Role(s):** Principal
- **Purpose:** The Principal's own in-app notices — most notably a partnership tier change — mirroring the Coordinator's existing notifications page.
- **Linked Feature ID(s):** `ENH-023`
- **Entry points:** Principal navigation ("Notifications").
- **Required data:** `GET /api/v1/workflows/notifications`, keyed on the signed-in user (the same feed the Coordinator page already reads).
- **Key actions:** Read the list; no write actions on this page.
- **Empty state:** "No notifications yet. You will be told here when your school's partnership changes."
- **Loading state:** Skeleton on navigation (no `loading.tsx`, matching the existing notifications pages — the skeleton renders inline while the list loads).
- **Error state:** A feed failure shows the shared Access Unavailable card; a non-Principal role gets `accessDenied` before any feed request.
- **Permissions/resource scope:** `school_principal` only, server-checked before any request; the feed itself is scoped to the signed-in user, same as the Coordinator's page.
- **Responsive behavior:** Single column at 320px and up; no horizontal scroll; existing classes only (`SchoolNotificationList`, `card`, `muted`, `skeleton-line`).
- **Accessibility requirements:** Same list component as the Coordinator page (`SchoolNotificationList`); a "new" badge is rendered as text, never colour alone.
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet/mobile: single column, same as the Coordinator equivalent.
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** `SchoolPrincipalNotificationsPage.test.tsx` (passing); `tests/e2e/enh-023-tier-change.spec.ts` (principal sees the tier-change notification); browser QA is deliberately deferred to a later pass (not part of this task).

### `SCR-RPT-001`
- **Route:** `/it/admin/reports`  
- **Role(s):** IT Admin, Placement Team  
- **Purpose:** Domestic/Employer/Placement reporting dashboard.  
- **Linked Feature ID(s):** `RPT-001`, `ADM-007`  
- **Entry points:** SCR-ADM-001 / Placement Team dashboard.  
- **Required data:** Enrolment funnel, course performance, placement outcomes/funnel data.  
- **Key actions:** Filter by period; export.  
- **Empty state:** No data for period → empty state, never fabricated figures.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** Inline error message with retry action; never a blank/broken screen.  
- **Permissions/resource scope:** IT Admin, Placement Team.  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** No fabricated zero/placeholder figures verified.  


## SEC

| Screen ID | Route | Roles | Feature ID(s) |
|---|---|---|---|
| `SCR-SEC-001` | `/account/privacy (Data export/delete request)` | Student, Trainer, IT Admin, Employer, Agent, Overseas Admin, Counselor, University Representative, Placement Team, HR Team, Super Admin | `SEC-002` |

### `SCR-SEC-001`
- **Route:** `/account/privacy (Data export/delete request)`  
- **Role(s):** Student, Trainer, IT Admin, Employer, Agent, Overseas Admin, Counselor, University Representative, Placement Team, HR Team, Super Admin  
- **Purpose:** GDPR self-service export/delete request.  
- **Linked Feature ID(s):** `SEC-002`  
- **Entry points:** Persistent account/profile menu, every role.  
- **Required data:** None (write-only request form).  
- **Key actions:** Request export; request deletion.  
- **Empty state:** N/A.  
- **Loading state:** Skeleton/placeholder layout while data loads; no layout shift on resolve.  
- **Error state:** A deletion request respects legal/financial retention holds where applicable — retention periods themselves still open (PRD_OPEN_ITEMS item 15).  
- **Permissions/resource scope:** Self (own data only) / IT Admin (fulfillment queue, not built as a separate screen here — see FEATURE_QUESTIONS.md if a dedicated fulfillment UI is needed).  
- **Responsive behavior:** Single-column stack on mobile; secondary panels collapse to tabs/accordions on tablet; full multi-column on desktop.  
- **Accessibility requirements:** Keyboard-navigable, visible focus states, form fields with associated labels, sufficient colour contrast (no confirmed WCAG level — see PRD NFR-A11Y-001, PROPOSED).  
- **Desktop/tablet/mobile behavior:** Desktop: full layout. Tablet: condensed nav, stacked secondary content. Mobile: single column, primary action always reachable without horizontal scroll.  
- **Visual-reference mapping:** None — not inspected. Only 1 of 160+ screens in the confirmed UX reference (`DAHRCNYnu6g`) has ever been seen; see `docs/ux/UX_REFERENCE_GAPS.md` Gap 2. Do not claim parity.  
- **Acceptance evidence needed:** Export/delete request recorded and actionable; legal review still recommended before this ships (BRD Risk R-05).  


---

## ENH-003 addendum (2026-09-19) — surfaces changed by first-time provisioning

No new routes and no new screens were added. `ENH-003` (`docs/delivery/ENHANCEMENT_BACKLOG.md`) changed the
behaviour of the existing surfaces below; they are listed here because the design spec (§12) requires this
catalogue to stay in step. Where a surface has no catalogue ID today (a pre-existing gap, not created by
`ENH-003`) that is stated rather than an ID invented.

| Surface | Route | Catalogue ID | Change |
|---|---|---|---|
| Set-password / reset page | `/{it\|overseas}/reset-password?token=` | none (pre-existing gap) | Serves the first-time welcome link too; on a `400` shows a recovery link and an "ask your administrator to re-send it" hint; honest network-error copy; `maxLength` 128; served with `Referrer-Policy: no-referrer` and `Cache-Control: no-store`; excluded from Google Analytics. |
| Users directory | `/it/admin/users`, `/overseas/admin/users` | `SCR-ADM-002` (IT); no catalogue ID was found for the Overseas Admin users page | Create user card no longer has a password field and reports the emailed-link outcome; "Manage users" panel gains a per-account setup status, an Account-setup filter (resolved by the server) and a Re-send action (now also for Overseas Admin); the Users table gains a "Setup" column. |
| Admin dashboards | `/it/admin/dashboard`, `/overseas/admin/dashboard`, `/admin` | `SCR-ADM-001` (IT); no catalogue ID was found for the Overseas Admin or Super Admin dashboards | "Expired welcome links" metric tile in the first viewport, plus an expired-links list with Re-send (loading, empty, error-with-retry states). |
| Create school + seed Coordinator | `/overseas/admin/schools` | `SCR-SCH-010` | No password shown; success/warning message states whether the 72-hour link was emailed. |
| School staff | `/overseas/admin/school-staff` | `SCR-SCH-021` | Same as above for Academic Team / Career Counselor / Psychometric Team accounts. |

## Required findings report

### FEATURE_WITHOUT_REQUIRED_SCREEN

- `AUTH-002` — **not a gap.** Role-based UI visibility (`PRD-AUTH-002`) is enforced *within* every other screen's rendering (only role-permitted nav/actions show), not as a screen of its own. No standalone screen is needed or created for it.

### SCREEN_WITHOUT_APPROVED_FEATURE

None. Every screen cites at least one `CURRENT`-scope Feature ID; verified programmatically against `docs/features/feature_catalog.json` (no screen cites a `BLOCKED` or non-existent feature).

### DUPLICATE_SCREEN

**One found and resolved during generation, not left in the final catalogue:** an initial pass created both `SCR-ADM-011` (Placement Team's own placement-reports view) and `SCR-RPT-001` (the `RPT-001` feature's general domestic/Employer reporting dashboard) as separate screens for what is really the same reporting surface. Merged into a single `SCR-RPT-001` citing both `RPT-001` and `ADM-007`. No duplicate routes remain — verified programmatically (0 collisions on normalized base route across all 96 screens).

### ROLE_NAVIGATION_CONFLICT

**One found and resolved during generation:** IT Admin's console and Super Admin's console were both initially routed at bare `/admin`, which would have been a real collision. The reference implementation's own `robots.txt` (`docs/evidence/REFERENCE_IMPLEMENTATION_FINDINGS.md`) independently confirms three separate admin namespaces exist in the base codebase — `/it/admin/`, `/overseas/admin/`, `/admin/` — meaning bare `/admin/` is Super Admin's namespace specifically, not IT Admin's. Corrected: all IT Admin screens now route under `/it/admin/*`; Super Admin keeps `/admin/*`; Placement Team and HR Team (which had only vague parenthetical non-routes initially) now route under `/it/placement/*` and `/it/hr/*` respectively, matching the same `robots.txt` evidence. Overseas Admin (`/overseas/admin/*`), Counselor (`/overseas/counselor/*`), University Representative (`/overseas/university/*`), and Agent (`/overseas/agent/*`) were correctly namespaced from the start.

### UX_REFERENCE_CONFLICT

None possible to detect beyond what's already flagged: only one screen (`SCR-PUB-001`) has any inspected visual reference at all, and its described layout (hero, 2 CTAs, 4 stat tiles, 3 feature cards) was written to match exactly what `UX_REFERENCE_AUDIT.md` recorded as observed — no invented detail, no conflict. Every other screen has no visual reference to conflict with in the first place (`UX_REFERENCE_GAPS.md` Gap 2 — 159+ of 160+ referenced screens were never inspected).
---

**APPROVED** by user (in-session), 2026-09-01. GATE-06 satisfied. Per this session's explicit
instruction: no screen above claims Canva visual parity beyond the single actually-inspected
thumbnail (`SCR-PUB-001`), and even that is scoped to structural reference only, per `DEC-UX-001`.
