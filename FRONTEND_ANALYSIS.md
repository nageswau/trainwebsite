# EduSphere Frontend — Architecture & Design Analysis

Read-only audit of `apps/web`. No application code changed. Scope: everything under
`apps/web` (Next.js frontend only) — `apps/api` (FastAPI) is out of scope per the brief.

## 1. Current frontend architecture

- **Framework:** Next.js 15.2 (App Router), React 19, TypeScript 5.7. `next.config.ts` sets
  `output: "standalone"` (Docker-friendly build) and `typedRoutes: false`.
- **Routing:** File-based under `app/`. Three top-level divisions: public marketing pages
  (`/`, `/it/*`, `/overseas/*`, `/faq`, `/contact`, `/news/*`, `/search`), authenticated
  portals (`/it/{student,trainer,placement,hr,admin}/*`, `/overseas/{student,counselor,
  university,admin,agent}/*`, `/admin/*`), and a handful of legacy/duplicate-looking routes
  (`/admin/page.tsx` + `/admin/login/*` + `/admin/[module]/page.tsx` alongside the newer
  `/it/admin/*` and `/overseas/admin/*` trees — see §5).
- **Portal pattern:** every authenticated role uses one dynamic catch-all,
  `app/{division}/{role}/[section]/page.tsx`, which renders `<PortalPage division role
  section/>`. `PortalPage` (`components/PortalPage.tsx`) is an async Server Component: it
  validates `section` against a static nav table (`lib/navigation.ts`'s `PORTAL_NAV`,
  404s via `notFound()` otherwise), fetches `/auth/me` and
  `/portal/{division}/{role}/{section}` server-side (`lib/api.ts`'s `serverApi`, always
  `cache: "no-store"`), and renders `<PortalShell>` wrapping a read-only `<PortalSection>`
  (generic sortable/paginated `<DataTable>`) plus either `<WorkflowPanel>` (student/most
  roles) or `<TeacherWorkspaceActions>` (trainer only — a special-cased, much larger
  hand-written action panel, not the generic system).
- **Auth:** cookie-based (`edusphere_access`), enforced by `middleware.ts` via a single
  regex matcher redirecting unauthenticated requests on protected path prefixes to the
  right division's login page. No client-side route guard beyond that — pages assume the
  middleware already gated access, then `PortalPage` re-derives the actual user/role from
  `/auth/me` for RBAC-correct rendering (deliberately never trusts the URL alone; a
  cross-role URL renders nothing extra, verified server-side).
- **API layer:** `app/api/[...path]/route.ts` (not inspected in depth, out of scope of this
  pass) plus two thin helpers in `lib/api.ts`: `serverApi` (server-side, cookie-forwarding,
  no cache) and `publicApi` (public content, `revalidate: 60`). Client components call the
  backend directly via `fetch("/api/v1/...")` (same-origin, browser-sent cookies) — there is
  no shared client-side data-fetching library (no SWR/React Query); every interactive panel
  hand-rolls its own `useEffect` fetch + `useState` cache.
- **State management:** none beyond React's own `useState`/`useMemo` per component. No
  Redux/Zustand/Context-based global store found anywhere in `components/` or `app/`.
- **i18n:** a two-line stub (`lib/i18n.ts`) — `SUPPORTED_LOCALES = ["en-GB"]`, no dictionaries,
  no locale-prefixed routing. Effectively English-only today, with the seam clearly marked
  for later.

## 2. Current UI/design system

There is no formal design system, no component library, no Tailwind/CSS-in-JS. Everything
is hand-written global CSS (`app/globals.css`, ~13 dense lines covering the whole site, plus
`app/controls.css` for the shared table/collection controls), using CSS custom properties for
a small token set:

```
--blue:#0755b9   --blue2:#0c63d7   --navy:#071b38   --ink:#0b1f3a
--muted:#61728a  --line:#dce5f1    --soft:#f5f8fc   --white:#fff
--green:#15803d  --amber:#b45309   --red:#b91c1c
--radius:18px    --shadow:0 14px 42px rgba(15,40,80,.10)
```

- **Typography:** `body { font: 15px/1.55 Inter, ui-sans-serif, system-ui, ... }` — but
  **`Inter` is never actually loaded** (no `next/font`, no Google Fonts `<link>`, no
  `@font-face` anywhere in the codebase — confirmed by grep). Every browser silently falls
  back to its default system UI font. See §5.
- **Icons:** none. No icon library dependency exists (`package.json` has zero UI deps beyond
  `next`/`react`/`react-dom`). Visual "icons" are CSS shapes (`.icon-circle`) or plain emoji
  used inline in page copy.
- **Components:** plain semantic HTML + utility-ish global classes (`.card`, `.btn`,
  `.badge`, `.status`, `.grid.two/three/four`, `.section`), not a scoped component-class
  system — every component reaches into the same global stylesheet by class name.
- **Buttons:** `.btn` (primary, filled blue), `.btn.secondary` (white/blue outline),
  `.btn.ghost` (transparent), `.btn.small`. No loading/icon-only/destructive variants.
- **Forms:** hand-rolled `.field`/`.form`/`.form-grid` wrapper classes; no schema validation
  library (no zod/yup), no react-hook-form — every form does manual `FormData` extraction
  and manual error state (see `AssignmentSubmissionPanel.tsx`, `AdminBatchCreatePanel.tsx`,
  etc., all built this session, all following the same hand-rolled convention already
  established by the inherited codebase).
- **Tables:** one generic, well-built `DataTable` (`components/DataTable.tsx`) — client-side
  search/filter/sort/pagination over an already-fetched row array — reused by every
  read-only portal listing. A near-identical second implementation,
  `CollectionExplorer.tsx`, exists for public content listings (search/filter/sort/paginate
  over `ReactNode` cards instead of table rows) — see §5 (duplication).
- **Charts:** none real. `.chart-placeholder` in `globals.css` is literally decorative CSS
  bars with no data binding — a static mock, not a chart component.
- **Animation:** essentially none. `scroll-behavior: smooth` on `html`, a CSS `transition`
  on `.card.hover`, `backdrop-filter: blur()` on the sticky header. No animation library, no
  page-transition system, no reduced-motion handling anywhere (`prefers-reduced-motion` is
  never referenced).
- **Layout shells:** `PublicShell` (header + `<main>` + footer) for marketing pages;
  `PortalShell` (sidebar + topbar + content) for authenticated portals. Both are simple,
  single-purpose, and reused consistently.
- **Responsive breakpoints:** exactly two, both in `globals.css`: `980px` (nav/portal-sidebar
  collapse) and `640px` (mobile — grids stack to one column, portal sidebar becomes a fixed
  bottom bar). No intermediate tablet-specific tuning.
- **Accessibility patterns already in place (genuinely good, worth preserving):** consistent
  `<label htmlFor>` associations on every form field across old and new components; `role=
  "status"`/`role="alert"` + `aria-live` on form feedback messages; `aria-current="page"` on
  active pagination buttons; `aria-label` on icon-only pagination buttons («, », Previous/
  Next); table sort buttons expose `aria-sort`. This is a real strength of the existing
  code, not a gap — see §7 for what's still missing on top of it.

## 3. Reusable components (what already exists and is safe to keep reusing)

| Component | Role |
|---|---|
| `PublicShell` / `SiteHeader` / `Footer` | Public marketing page chrome |
| `PortalShell` / `PortalSection` / `PortalPage` | Authenticated portal chrome + generic read view |
| `DataTable` | Generic sortable/paginated/filterable table (portal listings) |
| `CollectionExplorer` | Generic sortable/paginated/filterable card grid (public listings) |
| `WorkflowPanel` / `ActionForm` | Declarative, data-driven action forms (most roles) |
| `TeacherWorkspaceActions` | Hand-written trainer action panel (large, not data-driven) |
| `PageHero` | Public page hero/breadcrumb block |
| `HeaderAuthActions` | Session-aware header Login vs. Dashboard/Logout |
| `LoginForm` / `RegisterForm` / `ForgotPasswordForm` / `ResetPasswordForm` | Auth forms |
| `BatchSlotPicker`, `LiveClassesPanel`, `AssignmentSubmissionPanel`,
  `AgreementConsentPanel`, `BatchRosterPanel`, `AdminUserManagementPanel`,
  `AdminProgramManagementPanel`, `AdminLeadManagementPanel`, `AdminBatchCreatePanel`,
  `AdminEnrollmentReviewPanel` | Feature-specific self-fetching client panels, all built this
  session, all following one consistent pattern: `"use client"`, own `useEffect` fetch, own
  loading/empty/error states, real pickers instead of raw ID entry, inline
  `role="status"`/`role="alert"` feedback |

## 4. UX problems

1. **~~Mobile navigation is silently missing.~~ RESOLVED.** `.mobile-menu{display:none}` /
   `@media(max-width:980px){.main-nav{display:none}.mobile-menu{display:block}}` existed in
   CSS with no component rendering it. Fixed: `components/MobileNavToggle.tsx` (new, small
   client component, mirrors the existing `HeaderAuthActions` pattern) now fills that slot
   with an accessible hamburger toggle (`aria-expanded`, `aria-controls`, animated to a
   close icon, closes on Escape/link-click/route change) revealing the same nav items
   `SiteHeader` already computes, in a dropdown styled from existing tokens only (no new
   colors/fonts introduced). Verified functionally at 375px/800px/1280px and against the
   full 67-spec Playwright suite (all pass) — no API/route/auth/state-management changes.
2. **Every interactive panel fetches independently, with no shared cache.** A page that
   renders both `AgreementConsentPanel` and `LiveClassesPanel` (student "course" section)
   fires two unrelated `fetch` calls on mount, and neither knows about the other's data or
   loading state. There's a real, working cross-panel signal today (`BatchSlotPicker`
   dispatches a `window` `CustomEvent` that `AgreementConsentPanel` listens for after a
   booking) — a working but ad hoc pattern that will not scale cleanly as more panels are
   added to the same page.
3. **No optimistic UI / stale-while-revalidate anywhere.** Every action panel does
   fetch → await → `setState` on success, with a full-page `router.refresh()` afterward.
   Functionally correct, but every action feels one network round-trip slower than it needs
   to, and the additional `router.refresh()` re-runs the page's server-side data fetch too.
4. **Generic `ActionForm` requires knowing a raw UUID for many actions.** `WorkflowPanel`'s
   declarative `adminSpecs`/`placementSpecs`/`agentSpecs`/`overseasOperationsSpecs` still
   drive several flows (job requirements, interviews, offers, visa cases, appointments,
   content pages, blog posts, universities, payments) via a bare `type: "text"` "paste the
   reference" field. This session already replaced that anti-pattern for the flows a
   completed Feature ID touched (batches, users, programs, leads, enrolments, assignments,
   live sessions, grading, attendance) — the remaining `adminSpecs`/`placementSpecs`/
   `agentSpecs`/`overseasOperationsSpecs` entries are the same shape, just not yet reached.
5. **Two parallel "browse a list" implementations** (`DataTable` for portals,
   `CollectionExplorer` for public pages) that do almost the same job (search, filter, sort,
   paginate) with separately-maintained logic, markup, and CSS. Any future bug fix or UX
   improvement (e.g. URL-persisted filters, keyboard-friendly pagination) has to be applied
   twice.
6. **`.chart-placeholder` is decorative, not a real chart.** Any page currently using it
   (report/summary views) shows fake gradient bars unconnected to real data — a stub, not a
   finished feature.

## 5. Visual consistency problems

1. **~~The public header logo rendered as an oversized square, overlapping the hero
   section below it.~~ RESOLVED — two separate, compounding bugs.**
   - **Bug A (the visible, reported one):** the `<a>` wrapping `.brand-logo` is a flex item
     in `.header-row{display:flex}` with the CSS default `flex-shrink:1`. Once the nav/
     toggle/actions siblings claimed enough space, the browser shrank that flex item below
     its declared `width:190px` — and because height was left to `auto`, the image fell
     back to its *source file's own* aspect ratio once its declared box collapsed. Traced
     with real `getBoundingClientRect()`/computed-style measurements (not guessed) down to
     the exact mechanism, reproduced at the 900px width from the report, and confirmed the
     fix moves the box from ~77×77px (square, overflowing) to a correct 190×63px. Fixed
     with a scoped `.header-row>a:first-child{flex-shrink:0}` plus `aspect-ratio:3/1;
     object-fit:contain` on `.brand-logo` (cascades correctly to the 160px mobile
     breakpoint too — verified 160×53px at 375px).
   - **Bug B (a related, lower-severity one, found first):** `/brand/logo-dark.png` and
     `/brand/logo-light.png` turned out to be the *same* blue-on-transparent artwork
     (confirmed by direct pixel inspection of both files), not an actual light/dark
     reversed pair — despite the filenames, neither is a white-on-transparent variant safe
     to place on the navy backgrounds the "dark" one is used on. Screenshotted the real
     result on all four such contexts (portal sidebar — every role, `PortalShell.tsx`;
     public site footer — every page, `Footer.tsx`; homepage hero panel, `app/page.tsx`;
     all four login pages' brand panel) and confirmed the logo was at best low-contrast, at
     worst unreadable, against `--navy`. Fixed with a shared `.logo-on-dark` white
     rounded-card backing (existing token `#fff`, no new asset, no new dependency),
     carrying the same `aspect-ratio:3/1;object-fit:contain` fix as Bug A since none of
     these four are flex children so weren't hit by Bug A itself, but benefit from the same
     explicit ratio as defense-in-depth. The collapsed 54px mobile sidebar icon needed its
     own `aspect-ratio:1/1` override to keep its existing (already-correct) square icon
     crop rather than inheriting the 3:1 wordmark ratio.

   Both root-caused with real measurements and screenshots, not assumed. Full 67-spec
   Playwright suite passes after each.
2. **Inter is specified but never loaded** (see §2) — the entire site's declared type
   choice silently degrades to each OS's default UI font. Visually harmless (system fonts
   are legible) but not the intended look, and inconsistent across Windows/macOS/Linux/
   mobile testers.
3. **Duplicate/legacy admin route trees.** `app/admin/page.tsx`, `app/admin/login/*`, and
   `app/admin/[module]/page.tsx` exist alongside the actively-developed `app/it/admin/*` and
   `app/overseas/admin/*` trees. `middleware.ts` treats bare `/admin/*` as its own protected
   prefix with its own login redirect (`/admin/login`), separate from the division-scoped
   admin logins. It's unclear from the frontend alone whether this is a legacy holdover from
   before the IT/Overseas split or an intentional separate "super admin" entry point — worth
   a decision-register check before touching it.
4. **Two button-disabled visual languages.** `.btn:disabled{opacity:.6}` is defined once
   globally, but several hand-rolled panels (this session's additions) also render inline
   *text* state changes on the same button (e.g. "Saving…", "Approved", "Confirm
   deactivate") rather than a consistent disabled+spinner pattern — each panel invented its
   own wording ad hoc rather than sharing one busy-button convention.
5. **Inconsistent empty-state phrasing.** `DataTable`'s empty state says "No matching
   records" / "Change or clear the search and filter values to see more records.";
   `CollectionExplorer`'s says "No matching {noun}" / "Try a broader search or clear the
   filters."; individual panels each write their own ("No batches are currently assigned to
   you.", "No leads found.", etc.). Functionally fine, but there's no shared empty-state
   component or copy convention.
6. **`.action-grid` is a fixed 2-column grid** (`repeat(2,minmax(0,1fr))`) with no
   masonry/auto-fit behavior — a page with an odd number of action cards, or one very tall
   card next to a short one, leaves visibly uneven whitespace (visible today on the trainer
   dashboard, which stacks `BatchRosterPanel` + `LiveClassesPanel` + 6 generic workspace
   cards in the same grid).

## 6. Responsive problems

1. **The mobile-nav gap in §4.1** is the primary one.
2. **Only two breakpoints total**, both defined once in `globals.css` with no
   component-scoped overrides — anything between 641–980px (a lot of real tablet/small-
   laptop viewport space) gets the same treatment as a 981px desktop for most components
   except the header/portal-sidebar/grid-column rules that explicitly target 980px.
3. **`.table` sets `min-width:650px`** inside a `.table-wrap{overflow:auto}` — correct
   pattern (horizontal scroll instead of squeeze), but on a 375px viewport this means most
   admin/trainer tables (batches, enrolments, users, leads) require horizontal scrolling to
   read past the first two or three columns; no responsive column-priority/collapse strategy
   exists.
4. **Portal sidebar becomes icon-only at 980px, then a fixed bottom bar at 640px** — a
   reasonable, deliberate two-stage responsive strategy, and one of the better-considered
   responsive treatments in the codebase. No issue found here, noted as a positive.
5. Existing E2E coverage already checks 375px viewports for several pages (auth, PUB-001,
   PUB-003, STU-002) — good practice already established — but none of the newer admin
   panels built this session (`AdminUserManagementPanel`, `AdminBatchCreatePanel`, etc.)
   have an explicit 375px E2E check yet.

## 7. Accessibility problems

1. **No custom `:focus`/`:focus-visible` styling anywhere** (confirmed by grep — zero
   matches in both CSS files). Keyboard users get only the browser's unstyled default
   outline, which on `.btn`'s rounded corners and `.card.hover`'s dark-navy variant can be
   low-contrast or visually clipped depending on browser/OS. Not a hard accessibility
   failure (a default focus indicator does exist), but not verified/tuned either.
2. **No `prefers-reduced-motion` handling.** The only real motion (`scroll-behavior:smooth`,
   `.card.hover`'s `transform`/`transition`) is applied unconditionally.
3. **Icon-only mobile portal nav loses text entirely.** At ≤980px,
   `.portal-nav a{font-size:0}` with a generic `content:"•"` bullet standing in for every
   nav item's icon — the link's accessible name (from its text content) is preserved for
   screen readers, but sighted keyboard/low-vision users relying on visible labels lose all
   differentiation between nav items (every item shows the same "•").
4. **`Image` `alt` text is present but generic** ("EduSphere" on both light and dark logo
   variants across header/footer/auth pages) — acceptable for a logo, not a defect, just
   worth noting there's no richer alt-text convention established for content images
   elsewhere (couldn't confirm either way without auditing every content page's images,
   out of scope for this pass).
5. **Color contrast not verified.** `--muted:#61728a` on white background and `--amber:
   #b45309`/`.status.pending` combinations were not run through a contrast checker in this
   pass — flagged as a "needs verification," not a confirmed failure.
6. **Positive findings worth protecting going forward:** label associations, `aria-live`
   feedback regions, `aria-current`/`aria-sort`/`aria-label` usage, and semantic `<table>`
   markup are all already consistently applied — any future component work should keep
   matching this bar, not regress it.

## 8. Recommended improvements

Ordered by impact-to-effort, not by priority mandate (that's the user's call):

1. **Build the missing mobile nav.** Add a real hamburger toggle in `SiteHeader.tsx` that
   shows/hides `.main-nav` (or a dedicated drawer) at ≤980px, reusing the CSS hook
   (`.mobile-menu`) that's already half-built. This is the highest-impact, lowest-risk fix —
   pure addition, touches one component, no API/route/auth changes.
2. **Actually load Inter** (or make a deliberate, documented choice to keep the system-font
   stack and delete the dead `Inter` reference) via `next/font/google` in `app/layout.tsx` —
   a few lines, no visual-system redesign required, and it's the kind of thing that's easy
   to leave broken indefinitely because it "looks fine" on system fonts.
3. **Add `:focus-visible` styling** to `.btn`, `.card`, nav links, and table sort buttons —
   small, additive CSS, no markup changes needed anywhere.
4. **Add `@media (prefers-reduced-motion: reduce)`** to neutralize `scroll-behavior:smooth`
   and the `.card.hover` transition for users who've asked for it.
5. **Extract one shared "busy button" convention** (a small `<ActionButton busy={..}
   label=".." busyLabel=".."/>` wrapper) that the newer admin panels (and future ones) can
   share instead of each hand-rolling its own "Saving…"/"Approved"/"Confirm X" text-swap
   logic — reduces duplication without touching any existing panel's external behavior.
6. **Consider consolidating `DataTable` and `CollectionExplorer`** behind one shared
   search/filter/sort/paginate hook, keeping their different render targets (table rows vs.
   card grid) as thin wrappers. Larger, more careful change — see §9/§10 before attempting.
7. **Resolve the legacy `/admin/*` route tree** — confirm with the user/decision register
   whether it's still needed, then either document its purpose or remove it; leaving two
   parallel admin entry points is a maintenance and security-surface risk (two auth flows to
   keep correct) even if both currently work.
8. **Add explicit 375px-viewport E2E checks** for the newer admin panels, matching the
   pattern already established for public/student pages.

## 9. Files likely to require changes (for the improvements above, if pursued)

| Improvement | Files |
|---|---|
| Mobile nav | `components/SiteHeader.tsx`, `app/globals.css` (extend existing `.mobile-menu`/`.main-nav` rules) |
| Load Inter | `app/layout.tsx`, `app/globals.css` (swap the font stack reference) |
| Focus styling | `app/globals.css` only |
| Reduced motion | `app/globals.css` only |
| Shared busy-button | new `components/ActionButton.tsx` + incremental adoption in the 10 panel components listed in §3 |
| DataTable/CollectionExplorer consolidation | `components/DataTable.tsx`, `components/CollectionExplorer.tsx`, `app/controls.css`, every page importing either (broad — see risk note below) |
| Legacy `/admin/*` resolution | `app/admin/**` (decision-dependent: delete, redirect, or document) |
| 375px E2E coverage | new assertions in `tests/e2e/adm-*.spec.ts` |

## 10. Risks

- **The `/admin/*` vs `/it/admin/*`/`/overseas/admin/*` duplication is an unknown, not a
  confirmed bug** — removing or redirecting it without checking `docs/decisions/` and with
  the user first could break an intentionally-separate super-admin entry point.
  Investigate before changing, per this project's own NO-ASSUMPTION MODE governance.
- **`DataTable`/`CollectionExplorer` consolidation touches the most surface area** of
  anything recommended here — both are used by nearly every portal and public listing page
  in the app, and the two APIs (row-object-based vs. `ReactNode`-content-based) aren't
  trivially unifiable without either a lossy simplification or a genuinely more complex
  shared hook. Should be scoped as its own dedicated pass with its own regression run, not
  bundled into a general "polish" change.
- **Any global CSS change** (`globals.css`/`controls.css`) is inherently wide-blast-radius
  by construction — there is no component-scoped CSS anywhere in this app, so even a
  "small" focus-ring or font addition touches every page simultaneously. Each such change
  should be followed by a full Playwright regression run (currently 67 passing E2E specs)
  and a manual pass over at least one page per shell (`PublicShell` and `PortalShell`)
  before considering it safe.
- **No visual regression tooling exists.** Nothing in this repo screenshots and diffs UI
  states, so a CSS-only change has no automated guard against unintended visual drift beyond
  what Playwright's functional assertions happen to catch. Manual review is the only
  safety net today.

## 11. Proposed implementation order

If the user wants to proceed with any of §8, in a sequence that keeps each step
independently shippable and low-risk relative to the next:

1. Mobile nav (highest UX impact, fully additive, single component).
2. Focus-visible + reduced-motion (pure CSS additions, zero markup/behavior change).
3. Load Inter, or explicitly decide against it (small, isolated, easy to verify visually).
4. Shared busy-button component, adopted incrementally per panel (no behavior change per
   panel, just a wrapper swap — can be done one panel at a time with its own E2E rerun).
5. 375px E2E coverage for the newer admin panels (test-only, no app-code risk).
6. Legacy `/admin/*` route resolution — **after** a decision-register check, since this is
   the one item here that could be a real, intentional feature rather than dead weight.
7. `DataTable`/`CollectionExplorer` consolidation — last, and only as its own scoped
   project with explicit user sign-off first, given the risk noted in §10.

---

No application code was modified to produce this analysis.
