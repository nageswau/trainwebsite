# EduSphere Project and Business-Rules Audit

**Date:** 2026-09-10  
**Status:** Analysis and recommendation, not an approved requirement or scope change  
**Scope:** Repository-wide review of product documentation, business rules, architecture, API and UI structure, tests, local runtime health, and the public IT programme catalogue  

## Executive summary

EduSphere is one education-operations platform serving two connected businesses:

1. **IT Training and Placement** — public course discovery, enquiries, programme enrolment, trainer/batch selection, learning delivery, assessments, attendance, placement operations, employer hiring, fees, and reporting.
2. **Overseas Education** — destination/university/course discovery, counselling, applications, documents, offers, visas, agents, commissions, payments, notifications, and reporting.

It is implemented as a **domain-oriented modular monolith**, not a microservices system: one Next.js application, one FastAPI application, PostgreSQL, Redis, and Celery, deployed together but separated internally by division, role, route, and domain boundaries (`docs/architecture/ARCHITECTURE.md:46`). This remains the right shape for the present product and team. A rewrite into microservices would add delivery and operational risk without solving the current problems.

The repository contains a substantial working product, not a prototype shell: 72 Next.js pages, approximately 200 FastAPI route handlers, 66 model-layer classes including the SQLAlchemy base/mixin, 75 backend test files, and 70 Playwright specifications. The local API and web application both returned HTTP 200 during this audit, and the production web image built successfully.

It is **not production-ready yet**. The main blockers are production configuration defaults, stateful/non-isolated tests, a newly added but currently red CI baseline, red backend static-analysis gates, silent frontend failures, API-contract drift, unresolved business decisions, and contradictory source documents. These are higher priority than adding more feature breadth.

## What “project” means in this repository

The word has two distinct meanings:

- **The EduSphere project/product** is the complete platform described above.
- **A Real Project** is a public, CMS-managed portfolio example for IT learners. It has a title, summary, full description, technology stack, division, slug, and published flag (`apps/api/app/models.py:670`). It is marketing/learning evidence shown at `/it/real-projects`; it is not an assignment submission, client engagement, placement case, or project-management object.

This distinction should be made explicit in the UI and documentation. “Portfolio Projects” is a clearer navigation label than “Real Projects” if the records remain examples rather than live client projects.

## Users and ownership boundaries

| User/role | Primary responsibility | Data boundary |
|---|---|---|
| Visitor | Browse public content and submit enquiries | Published public data only |
| Student | Enrol, learn, pay, apply overseas | Own account, enrolments, submissions, applications |
| Trainer | Classes, attendance, assignments, assessment grading | Assigned IT batches/students |
| Placement Team | Candidate pool, companies, interviews, offers, reports | IT placement operations |
| HR Team | Requirements, shortlists, interview coordination | IT hiring operations |
| IT Admin | Domestic programme and platform operations | IT division |
| Counselor | Leads, documents, applications, visas, appointments | Assigned overseas cases |
| University Representative | Review applications and update offers/admissions | Own university/institution |
| Agent | Refer students and claim eligible commission | Own referrals and commissions only |
| Overseas Admin | Overseas operations, agent activation, commission payout | Overseas division |
| Employer | Register, post jobs, search candidates, schedule interviews | Own company/jobs and authorized candidate data |
| Super Admin | Cross-division CMS, security, audit, backups, reporting | Global, explicitly privileged |

The Student identity is shared across domestic learning and overseas applications; an overseas applicant is not meant to require a second account (`docs/product/PRD.md:133`). “Teacher” and “Trainer” are the same role in product language.

## Core journeys

### IT training

`Visitor enquiry -> local enquiry saved -> Zoho CRM sync -> Admin routing -> Student -> programme selection -> available trainer/slot -> locked booking -> Razorpay payment -> active enrolment -> classes/learning -> assessments -> placement support`

The domestic admissions handoff is directionally documented, but exact rejection/incomplete states are still unconfirmed (`docs/product/PRD.md:92`).

### Overseas education

`Interest -> eligibility evaluation -> university/course selection -> offer -> visa documents -> status tracking -> enrolment`

The happy path is confirmed. Rejection, waitlist, deferral, withdrawal, and re-application paths are not fully specified (`docs/product/PRD.md:100`).

### Agent lifecycle

`Self-registration -> pending Overseas Admin review -> active or rejected`

Pending/rejected agents cannot refer students or view operational data (`docs/product/PRD.md:108`).

### Commission lifecycle

`Referral -> application reaches enrolled/joined condition -> commission accrued -> agent claims -> Overseas Admin approves -> paid`

Accrual and payment approval are separate gates. Offer acceptance alone must not earn commission (`docs/product/PRD.md:113`).

## Confirmed business rules

| Area | Rule | Current assessment |
|---|---|---|
| Identity | One Student identity extends into overseas applicant data | Clear and structurally supported |
| Authorization | Backend role/division checks are the security boundary; frontend hiding is UX only | Correct principle; keep deny-by-default |
| Batch capacity | Maximum 20 students per trainer/time slot | Confirmed (`docs/product/PRD.md:278`) |
| Slot changes | Once selected, the slot is locked for the programme duration | Confirmed (`docs/product/PRD.md:278`) |
| Enquiries | A CRM failure must not lose the locally stored enquiry | Implemented with background retry according to the feature catalogue |
| Payments | Razorpay is the sole gateway; Stripe was removed | Confirmed, but multi-currency/tax capability remains unresolved |
| Live classes | Zoho Meeting is default; Google Meet is retained | Confirmed; no internal meeting platform is in scope |
| Agent approval | Only an Overseas Admin activates/rejects an agent | Confirmed |
| Agent privacy | An agent sees only their own referred students | Confirmed |
| Commission accrual | Requires the referred application to reach enrolment and the learner to join | Confirmed |
| Commission payout | Agent claim and Overseas Admin approval are distinct | Confirmed |
| Overseas documents | Required documents vary by country, university, and course | Direction confirmed; actual checklist content needs governance |
| Public content | Only published records are exposed | Present on core public CMS models/routes |
| Data maintenance | Countries, universities, overseas courses, programme fees, and similar reference data are manually administered | Operational ownership/versioning needs definition |
| Privacy | UK GDPR is the intended baseline | Retention periods and legal wording remain open |

## Feature-status snapshot

The catalogue documents 78 features. Parsing the implementation-status lines gives:

| Status | Count | Features requiring attention |
|---|---:|---|
| Complete (documented claim) | 66 | Requires a clean, isolated regression run before release confidence |
| Partial | 2 | `ADM-012` roles/permissions is view-only; `OVS-004` is email-only |
| Not started | 9 | `AUTH-003`, `PUB-010`, `ADM-011`, `ADM-013`, `EMP-006`, `NOT-003`, `LMS-001`, `OPS-001`, `OPS-002` |
| Blocked | 1 | `NOT-002` WhatsApp/Twilio credentials |

There is a separate documentation inconsistency: `docs/features/feature_catalog.json` currently reports 76 `CURRENT` and 2 `BLOCKED`, while the approved prose at `docs/features/MASTER_FEATURE_CATALOG.md:9-16` still says 68 and 10. The status above is based on each feature's detailed implementation line, not either scope count.

“Complete” here means **claimed complete in the project catalogue**, not independently re-proven by this audit. Historic test totals in the catalogue should not be used as a current release certificate.

## What is working

- The local PostgreSQL, Redis, FastAPI, Celery worker/beat, and Next.js services start without resetting data.
- `GET /health` returned 200 and `/it/programs` returned 200.
- The current Next.js production image compiles successfully and generates all 57 reported static/dynamic route entries.
- Frontend TypeScript checking passes.
- The redesigned programme-catalogue files pass focused ESLint checks.
- The six targeted `PUB-003` browser tests pass: listing/search, category URL state, detail navigation and content, per-page metadata, missing-slug handling, and 375 px responsiveness.
- Public programme seed data is coherent enough to expose 20 programmes across 7 categories with fee, duration, curriculum, eligibility, certification, placement assistance, and trainer fields.
- The architecture has sensible building blocks: server-rendered public pages, typed API models, division-aware RBAC, database migrations, background jobs, health checks, and broad role/workflow coverage.
- Public catalogue errors are now distinguishable from a legitimately empty catalogue; the old implementation silently presented both situations as no results.

## What is not working or is unsafe

### P0 — release blockers

1. **Production configuration can start with insecure defaults.** `apps/api/app/core/config.py:8-17` defaults to `environment=development`, `secret_key=change-me`, insecure cookies, and automatic schema creation. Add startup validation that refuses those values outside local/test environments. Production migrations must be explicit and cookies secure.

2. **The test strategy is not reliably isolated.** Backend tests are documented as sharing/polluting the development database, and at least one test exercises a live Zoho integration. Full regression was intentionally not run during this audit because it could mutate the shared database or call a provider. Create an ephemeral test database per run, disable live providers by default, and use contract fakes. Keep separately gated live smoke tests.

3. **CI now exists, but its initial baseline is red.** `.github/workflows/ci.yml`, `scripts/ci-local.ps1`, and `docker-compose.ci.yml` run the same disposable, provider-safe gate sequence locally and in GitHub Actions. The first complete run passed frontend typecheck, 2 Vitest tests, all 22 migrations plus Alembic drift detection, and 26 targeted API tests; it failed Ruff format (35 files), Ruff lint (20 findings), MyPy (134 errors), and 10 of 207 headless Playwright checks. Failure screenshots, videos, traces, HTML, XML, command logs, and service logs are retained according to `docs/quality/CI.md`.

4. **Backend quality gates are red.** The audit found 20 Ruff findings and 134 MyPy errors across 9 files. Several errors cluster in the large portal/workflow modules. Treat type errors as defects-in-waiting even if a runtime path currently works.

5. **API implementation and contract disagree.** The contract requires cursor pagination (`docs/architecture/API_CONTRACT.md:21`), a standard `{error_code,message,field_errors}` envelope (`:33`), and describes bearer auth (`:54`). Current implementation commonly uses fixed `.limit(500/1000/2000)`, FastAPI's default `detail` errors, and the `edusphere_access` cookie (`apps/api/app/api/deps.py:14`). Decide one truth, update both code and contract, and add contract tests.

6. **Business-critical approval integrity has an open loophole.** A system-triggered commission can be amount-adjusted by an Overseas Admin who can then approve that payout; the two-person rule only keys off the original creator (`docs/product/PRD_OPEN_ITEMS.md:46`). Resolve and enforce separation of duties before real payouts.

### P1 — reliability and maintainability

1. **Frontend failures are frequently swallowed.** There are 24 empty `catch {}` blocks in TypeScript/TSX. Users may see “empty” when an API is unavailable. Replace them with explicit unavailable/error states, logging, and retry where useful.

2. **No route-level recovery experience exists.** No application `error.tsx`, `global-error.tsx`, `loading.tsx`, or custom `not-found.tsx` was found. Add shared boundaries before expanding page count.

3. **Critical modules are too large.** `apps/api/app/api/workflows.py` is about 2,453 lines, `services/portal.py` about 1,443, `api/admin.py` about 893, and `models.py` about 904. Split by business domain/use case, not by arbitrary line count. Do this incrementally behind existing routes rather than rewriting the system.

4. **Frontend implementation is inconsistent.** The scan found 296 inline style props and 33 `any` tokens. The production build succeeds but reports 31 ESLint warnings, including a missing hook dependency in `TeacherWorkspaceActions.tsx:136` and an unoptimized image in `app/gallery/page.tsx:12`.

5. **Automated frontend coverage is imbalanced.** There are 70 E2E specs but only one Vitest test file. The Vitest command could not start in this workspace because esbuild hit an OS “Access is denied” path while resolving `vitest.config.ts`. Fix the runner/environment, then add fast unit/component coverage for reducers, filters, permissions, forms, and state transitions.

6. **Large result limits hide pagination debt.** Admin and workflow endpoints cap results at 500–2,000 rather than returning a stable cursor. This will become both a performance and correctness issue as production records grow.

7. **Marketing metrics are hard-coded.** `apps/api/app/api/public.py:45` returns 1,250 learners, 830 placements, 75 university partners, and 96% visa success rather than audited data. Remove these values, label them as approved editorial claims with a source/as-of date, or calculate them from governed reporting definitions.

8. **Product success cannot be measured.** Many KPI definitions, SLAs, response-time targets, and funnel events remain open. Define a small event taxonomy and auditable metrics before optimizing conversion.

### P1 — source-of-truth drift

- The approved architecture says modular monolith (`docs/architecture/ARCHITECTURE.md:46`), but the BRD still lists microservices as an objective (`docs/product/BRD.md:54`) before correcting itself later (`:246`), and the PRD contradicts itself at `:37`, `:49`, and `:965`.
- The screen catalogue uses `/it/projects` (`docs/ux/SCREEN_CATALOG.md:70-71`), while the running application uses `/it/real-projects`.
- `ADM-012` and `ADM-013` have acknowledged PRD/catalogue numbering drift.
- The feature-catalogue JSON and Markdown scope counts disagree (76/2 vs. 68/10).
- `docs/product/PRD_OPEN_ITEMS.md` contains 37 current table rows, of which only 6 are explicitly marked closed. The document still references historic totals such as 52 items, so row identity/count governance also needs cleanup.

Create one generated feature source and derive Markdown summaries/RTM tables from it. Add a documentation consistency check to CI for IDs, routes, counts, and decision status.

## UI and accessibility findings

The redesigned catalogue follows the current interface guidance for visible focus, touch-safe controls, labels, URL-addressable state, reduced motion, responsive overflow, and honest content. Repository-wide gaps remain:

- `apps/web/components/PublicShell.tsx:2` — add a skip link and a stable `id` on the main content region.
- `apps/web/app/globals.css:2` — global smooth scrolling has no global reduced-motion override; `.card.hover` transitions `all` implicitly; common buttons/links lack a consistent visible focus ring.
- `apps/web/components/CareerTracker.tsx:3` — labels are not associated with controls; the error/status message lacks alert/status semantics; the result is `any`; locale-sensitive date output can differ between server/user expectations.
- `apps/web/app/gallery/page.tsx:7-12` — the page uses `any`, silently swallows loading failure, uses inline layout styling, and renders raw `<img>` without optimized dimensions.
- `apps/web/components/TeacherWorkspaceActions.tsx:136` — the missing effect dependency can leave UI data stale or make behavior depend on render history.

## Courses-page redesign delivered

The reference screenshot was treated as visual direction only; no text, prices, enrolment counts, dates, business claims, or external branding were copied.

The new `/it/programs` experience now includes:

- A mobile-friendly horizontal category rail with real programme counts.
- Branded visual course bands generated from existing category/curriculum data, so every card has identity without fabricated photography or certification badges.
- Real duration, fee, curriculum cues, category, trainer, and placement-support information.
- Search, category filtering, sorting, pagination, and shareable URL state.
- Distinct “service unavailable,” “no published programmes,” and “no matching results” states.
- A clear primary curriculum action and secondary request-details action.
- Responsive one/two/three-column layouts with no horizontal overflow at 375 px.
- Server-rendered metadata and a small client-only interaction boundary.

The screenshot's “enrolled” count, discount/original price, and next schedule were deliberately omitted because public `Program` data does not contain audited enrolment totals, discounts, or public batch dates. The existing batch-availability API is authenticated. Those elements should be added only after the backend exposes approved public fields and clear publication rules.

## Recommended delivery plan

### First 2 weeks — make release evidence trustworthy

1. Add production config fail-fast checks and secret/cookie/schema safeguards.
2. Create ephemeral test Postgres/Redis and provider fakes; separate live integration smoke tests.
3. Make the newly added CI baseline green: format/lint, Ruff, MyPy, frontend typecheck, unit tests, migration smoke, targeted API tests, then Playwright are now wired and must remain required.
4. Resolve the commission same-actor adjustment/approval rule.
5. Remove hard-coded public success statistics or approve their definitions/sources.
6. Reconcile architecture, feature-count, route, and feature-ID documentation drift.

### Weeks 3–6 — reliability and product truth

1. Standardize error envelopes, auth wording, and cursor pagination.
2. Add shared Next.js loading/error/not-found boundaries and replace silent catches.
3. Clear the 31 frontend warnings, 20 Ruff findings, and 134 MyPy errors.
4. Define product analytics: enquiry submitted/synced, catalogue-to-enquiry, enrolment payment, batch occupancy, course completion, placement, application stage time, visa outcome, and commission cycle time.
5. Decide the open overseas exception states, document matrix ownership, notification templates/opt-out behavior, employer activation/candidate visibility, report catalogue, retention schedule, and multi-currency/tax rules.

### Weeks 7–12 — simplify and complete

1. Split workflow/portal/admin modules by domain while preserving APIs.
2. Complete or formally descope the nine not-started and two partial features.
3. Add public schedule/discount/enrolment-proof fields only if product owners define source, freshness, privacy, and publishing rules.
4. Improve the remaining public pages with the new catalogue's component and error-state standards.
5. Complete deployment/migration runbooks, restore drills, monitoring, alert ownership, and a release rollback exercise.

## Decisions required from the product owner

1. Is “Real Projects” a catalogue of sample portfolio builds, verified learner projects, or live client work?
2. Which overseas exception states are valid, and who can transition each one?
3. Can the same admin adjust and approve a commission? Recommended answer: no.
4. Which employer users can see which candidate fields, and when is an employer activated?
5. What is the canonical payment currency/tax/invoice behavior for each operating region?
6. Which notification events are mandatory, through which channels, with what consent/opt-out rules?
7. What are the approved definitions and evidence sources for learner, placement, partner, and visa-success claims?
8. What retention periods and deletion/legal-hold rules apply to identity, academic, application, payment, and audit data?

## Audit limits

- This was a repository-wide static and safe-runtime review, not a line-by-line proof of every feature or a production penetration test.
- No secrets from `.env` were read or reported.
- Full backend regression was not run because the current test setup can mutate the shared development database and includes a live-provider path.
- Historic “PASS” claims in project documents were analyzed but not assumed to still be current.
- The standalone Vitest runner failure appears to be a workspace/OS permission-resolution issue; it is reported as a tooling blocker, not as proof that the application logic fails.
