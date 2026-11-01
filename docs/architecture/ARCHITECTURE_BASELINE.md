# EduSphere — As-Built Architecture Baseline (2026-11-01, `main@48562e8c`)

Status: **DESCRIPTIVE, not a decision.** This file records what the code does at `main@48562e8c`. Enhancement sessions
should read it before they change anything. The intended architecture is in `ARCHITECTURE.md`, and the decisions are in
`docs/decisions/`. Where those differ from this file, this file describes the code and makes no ruling.

It supersedes the 2026-10-07 baseline (`main@70243aaf`). Since then the Recruiter CRM (`rec-*`), University Partnership
(`upc-*`), Management (`mgmt-*`), Counselor CRM (`ccrm-*`, `csc-*`), the public-site work (`pub-*`, `psb-*`), Agent KYC
(`agn-024`), Direct Tie-ups (`dtu-*`), the review fixes (`nehn-*`), and the production launch on DigitalOcean have landed.
Over that period the backend app grew from about 48k to about 106k LOC.

Method: we used the existing graphify graph (built from `9e819081`, one docs-only commit behind HEAD). It has 58,175 nodes,
183,140 edges and 1,450 communities. Its god nodes are `User` (3,715 edges), `AuditLog` (1,303), `client_for()`, `sendJson()`,
`serverApi()`, `OverseasApplication` and `accessUnavailable()`. We then re-checked every count below against the source by
script. Sections that have not changed are carried forward in short form, and the items still unverified are marked as such.

---

## 1. System shape
```
Browser ──► Next.js 15 / React 19 (apps/web, standalone) ──server fetch──► FastAPI (apps/api, /api/v1) ──► PostgreSQL 16
   │          ├─ RSC pages: serverApi() forwards cookies                          │  asyncpg + SQLAlchemy 2 async
   └─ client ─┴─ app/api/[...path]/route.ts = transparent proxy ──────────────────┤
                                                                                  ├──► Redis 7 (Celery broker/backend only)
                                   Celery worker + beat (14 scheduled jobs) ◄─────┘
                                   S3 (optional) or local /data/uploads (prod: DO Block Storage Volume)
```
- **The app is a flat monolith.** Most domain packages under `app/{identity,admissions,courses,cms,employers,finance,learning,
  operations,overseas,students,trainers,agents,integrations}` are still **empty placeholders**. The one real package is
  `app/direct_tieups/` (`load.py` and `parse.py`, about 1k LOC, an Excel loader).
- The code itself lives in these places:
  - `app/api`: 156 router modules, about 34.8k LOC
  - `app/services`: 205 modules, about 43.2k LOC
  - `app/core`, `app/notifications`, `app/reporting`
  - `app/models.py` and `app/schemas.py`
  - root-level enum and stage modules (see §2)
- **Business surfaces.** There are about ten:
  - IT Academy
  - Overseas Education (with Agent CRM and Counselor CRM)
  - School portal
  - BDM CRM
  - Telecaller CRM
  - Recruiter CRM
  - University Partnership
  - Management (partner and accountant)
  - Employer
  - the public site

  All of them share one `users` table, one `Enquiry` (lead) table and one `AuditLog`.

## 2. FastAPI structure — `apps/api/app`
| Path | Role |
|---|---|
| `main.py` | Lifespan (logging, optional `create_all`, upload dir) → `RequestIdMiddleware`, CORS (single `frontend_url`, credentials). Routers are included through one `for r in (...)` tuple under `/api/v1`, plus `files.local_router`, `/health` and `/health/ready`. |
| `core/` | `config.py` (pydantic-settings, every integration optional), `database.py` (async engine; `get_db()` never auto-commits), `security.py` (bcrypt, HS256 JWT with the `sv` claim), `rbac.py` (`PERMISSIONS` bundles, agency helpers), `logging.py`/`middleware.py` (JSON logs, request-id ContextVars, redaction), `identifiers.py`. |
| Root enum/stage modules | `lead_stages`, `bdm_stages`, `recruiter_stages`, `partnership_*` (stages, milestones, onboarding, meeting types, event kinds, task rules, target KPIs), `student_journey`, `visa_status`, `overseas_progress`, `application_{fields,outcome,sub_status,checklists}`, `document_checklists`, `tel_sources`, `tel_content_kinds`. Models and services both import these. |
| `api/*.py` | Routers. The largest are `recruiter_*` (24), `bdm*` (20), `partnership_*` (14), `telecaller*` (13), `university_*` (12), `school*` (12), `agent_*` (11), `counselor_*` (8) and `management*` (7). |
| `services/*.py` | Domain services (see §4) and integrations. |
| `notifications/` | Outbox delivery (`dispatch`, `delivery`, `twilio`, `phone`, `lead_email`). |
| `reporting/pdf.py` | A pure reportlab renderer (dict in, bytes out). |
| `worker.py` | The Celery app, its tasks and the beat schedule (§19). |
| `seed.py`, `bootstrap_admin.py`, `send_test_email.py` | The demo seed, the first-admin bootstrap and the email smoke test. |

## 3. Routers and API boundaries
- There are **1,209 route decorators** in 156 modules, all under `/api/v1`. Modules often export several routers to split
  audiences (`router`/`admin_router`, `public_router`, …).
- The prefix families:
  - `/auth` and `/account`
  - public routes with no auth (`public.py`, `lookups.py`, `public_router`s)
  - `/portal/{division}/{role}/{section}` (`services/portal.py`)
  - `/admin`
  - `workflows` (IT and Overseas write actions)
  - `/files`, `/payments`, `/cms`, `/communications`
  - `/inbound` (webhooks)
  - `/employer`
  - `/school*`
  - `agent_*`
  - `bdm*`
  - `/telecaller*` plus `lead_*`
  - `/recruiter*`
  - `/partnership*`/`university_*`
  - `/management*`
  - `counselor_*`
  - `crm_exports`
- The contract of record is `docs/architecture/API_CONTRACT.md`. Its sections are numbered per feature, and the highest is now
  **`12IE`**. The RBAC matrix is at **§2.221**, and the decision register has reached **DEC-SCOPE-333**. All three move as
  features merge, so always re-check them on `origin/main`.

## 4. Business logic placement — two generations
- **The older modules (IT, Overseas workflows, School, admin) keep their logic in the handlers.** The largest are
  `workflows.py` (3.9k LOC), `schools.py` (2.7k) and `admin.py` (2.2k).
- **The newer modules (AGN, BDM, TEL, REC, UPC, MGMT, CCRM) are a thin router plus a service.** The router loads scope,
  calls `svc.*`, commits once, then logs. Each service exposes this kit:
  - `scope(user)`, which returns `(kind, [filters])` or raises 403
  - `require_*(user)`
  - `audit(db, …)`, which adds a row and never commits
  - `log(event, …)`
  - `*_out()` serializers

  The reference example is `api/telecaller_calls.py` with `services/lead_calls.py`.
- **Commit ownership:** the router commits exactly once per write, services only `flush`, and the log is written after the
  commit.
- ⚠ **Layer leaks have grown.** 13 services import from `app.api`:
  - `bdm_lifecycle`, `bdm_metrics`, `bdm_performance`
  - `candidate_search`, `course_skills`, `ledger`
  - `management_schools`, `management_universities`
  - `partnership_reports`, `tabular`
  - `telecaller_lifecycle`
  - `university_import`, `university_search`

  Routers still share private helpers such as `bdm.LIMIT/OFFSET/SEARCH/_matching`, `lookups._pattern`,
  `admin.ensure_admin`, `workflows._audit` and `school_feedback._require_school_reader`. There are 20 function-local
  imports marked `noqa: PLC0415`, including the `schools` ↔ `school_analytics` cycle.

## 5. Data access
- **There is no repository layer.** Code calls `select()` on `AsyncSession` directly, in routers (older modules) or services
  (newer ones).
- Concurrency uses pessimistic locks at **241 `with_for_update()` sites**. The common form is `locked_*()` with
  `populate_existing=True`, and batches lock rows in a deterministic `ORDER BY id`. `IntegrityError` maps to 409.
- "Now" comes from the DB through `db_now(db)`, which is still defined three times (`bdm_appointments`,
  `bdm_meeting_requests`, `lead_appointments`). Business days use IST (`today_ist`), and stored datetimes are UTC.
- `get_current_user` eager-loads `role_assignments` and `agent_membership.org` on every request.

## 6. SQLAlchemy models — `app/models.py` (one file, 7,010 LOC, 274 classes)
- It defines `Base(DeclarativeBase)` and `TimestampMixin`. The domains below carry over from the last baseline, and new ones
  have been added:
  - **Carried over:** Identity, IT learning, Employer, Overseas, Agent CRM, Finance, CMS/comms, School, BDM and Telecaller.
  - **New:** Recruiter (`Candidate`, `CandidateResume`, `CandidateSkill`, `Skill`/`SkillAlias`/`SkillCategory`, companies,
    jobs and JDs, pipeline, interviews, offers, joining, talent pools, contracts), University Partnership (agreements,
    commercial terms, meetings, targets, alerts), Management (ledger, expenses, salaries, capital, investments, plans,
    reviews, discussions), Counselor CRM (lead and student notes, sub-status, outcomes, offers and conditions, checklists,
    tasks, reminders, visa lifecycle, deposits, archive and consent) and Agent KYC.
- **`Enquiry` is the shared lead entity** across public intake, BDM, telecaller and the counselor walk-in and handover
  flows.
- `User` still keeps the legacy single-value `role`, `division` and `profile` JSON alongside its `UserRoleAssignment` rows,
  and also has `session_version`.

## 7. Pydantic schemas — `app/schemas.py` (one file, 14,753 LOC, 1,182 classes)
- It uses Pydantic v2 with `field_validator`s. `response_model` appears 457 times, and **125 legacy handlers still take
  `payload: dict`**. New code uses typed models, and partial updates use `model_dump(exclude_unset=True)`.
- **Pagination:**
  - The standard signature is `limit: int = LIMIT, offset: int = OFFSET`, imported from `api.bdm`, and 107 handlers use it.
  - The response envelope is `{items, total, limit, offset}` (`Page<T>` on the web side).
  - Many legacy lists still return arrays.
- **Field-located 422s** are raised as `RequestValidationError([{loc:("body",field),…}])`.

## 8. PostgreSQL
- The database is PostgreSQL 16 through asyncpg. Named unique and CHECK constraints act as business rules, and some are
  mapped to 409 by name. Stored datetimes are UTC, and business-day logic uses Asia/Kolkata.
- **Production uses DigitalOcean Managed PostgreSQL** (DEC-INFRA-002, see §25).

## 9. Migrations — `apps/api/alembic`
- There are **217 linear revisions**, and the head is `0219_hr_student_grants`. `env.py` is async with `compare_type=True`.
- The next migration number depends on merge order. Before you pick one, fetch `origin/main` and check `alembic/versions`.
- `alembic upgrade head` runs at container start.
- ⚠ `Settings.auto_create_schema` still defaults to **True**, so `create_all` runs in the lifespan. Tests set it to False.
  Every schema change still needs a revision.

## 10. Authentication — `api/auth.py`, `api/deps.py` (unchanged in shape)
- Tokens are httpOnly cookies: `edusphere_access` (60 min) and `edusphere_refresh` (14 days). They use `SameSite=Lax`, and
  `Secure` comes from `COOKIE_SECURE`, which defaults to False.
- **Revocation** works through the `sv` claim compared with `users.session_version`.
- The endpoints are login, register, refresh, logout, `/me`, forgot, reset and change password, the invite and welcome
  tokens, and agent self-signup with KYC (agn-024).
- **Throttling:** there is still no global rate limiter. Per-endpoint throttles counted in the DB return `429` with
  `Retry-After`: agent signup, the change-password lockout and the admin link resend. Forgot-password answers the same way
  whether or not the account exists (no enumeration signal), and it sends its email through `BackgroundTasks`, the only use
  of that in the app.
- There is no CSRF token.

## 11. Authorization / RBAC
- **Inline checks on `User.role` are the standing pattern** (owner decision; memory `rbac-follow-inline-pattern`).
- **Change since the last baseline:** `deps.require_permission(resource, action, detail)` is now used as a dependency at
  9 sites:
  - `admin` (`payments` view and add, `discounts`)
  - `certificate_signatories`
  - `telecaller_reports`
  - `workflows` (certificates and student-access config, nehn-031)

  `require_role` and `require_division` still have **0** call sites. A new permission-style gate should follow these
  `require_permission` sites. Everything else stays inline.
- Each module has its own gates:

  | Module | Gates |
  |---|---|
  | Legacy | `workflows._require` |
  | Admin | `admin.ensure_admin` |
  | School | `schools._require_coordinator`, `_own_school_id`, `require_school_entitlement` |
  | Agent | `agent_students._gate`, `rbac.agent_may`/`is_agent_staff` |
  | New modules | each service's `scope(user)` and `require_*` |

- **Resource scope is applied as query filters.** An out-of-scope row reads as **404**, and a role with no access gets
  **403**.
- Each feature adds an `RBAC_MATRIX.md` §2.x row and an entry in the route-inventory test where its module has one (for
  example `test_tel_026_*`).

## 12. Next.js routing — `apps/web/app` (App Router, Next 15, React 19, 392 `page.tsx`)
- **Public routes:** `/`, `contact`, `faq`, `gallery`, `news`, `search`, `robots.ts`, `sitemap.ts`.
- **Portals:**
  - `/it/*`
  - `/overseas/*` (student, counselor, university, agent, admin)
  - `/admin/*`
  - `/school/*`
  - `/bdm/*`
  - `/telecaller/*`
  - **`/recruiter/*`**
  - **`/partnership/*`**
  - **`/management/*`** (about 30 sections, including ledger, P&L, revenue, expenses, salaries, capital, investments,
    funnel, drill, reviews and discussions)
  - `/account`
- **`middleware.ts`** only checks that a cookie is present. Its matcher covers `/it`, `/overseas`, `/admin`, `/bdm`,
  `/telecaller`, `/recruiter`, `/partnership` and `/management`. **`/school/*` and `/account` are still not covered**, so
  they rely on `serverApi` throwing and then `accessUnavailable()`. The backend is always the real gate.
- **Route handlers:** `app/api/[...path]/route.ts` (a transparent proxy that forwards all headers and cookies) and
  `app/local-files/[...path]`.

## 13. Server and client components
- **Pages are async server components.** They call `serverApi('/auth/me')` and load the page data in parallel, catch
  failures into `accessUnavailable()`, and render `PortalShell` with the nav from `lib/navigation.ts`, `bdmNav.ts` or
  `telecallerNav.ts`.
- **Panels are client components** (494 of 698 components are `"use client"`). They take initial data as props, mutate
  through `sendJson`, then call `router.refresh()` or update local state.
- **Server-only helpers** live in `lib/*Server.ts`, so client imports never pull in `next/headers`.

## 14. Shared frontend components (reuse these)
| Area | Components |
|---|---|
| Shells and navigation | `PortalShell`, `PublicShell`, `PortalMobileNav`, `NavGroup`, `DesktopNav`/`MobileNavToggle`, `RefreshOnHistoryNav`. Section shells: `LedgerShell`, `DiscussionsShell` (management). |
| Feedback | `AccessUnavailable`/`accessUnavailable()`, `SectionUnavailable`, `LoadFailureAlert`, `FormMessage`, `TravelUnavailable` |
| Tables | `DataTable` plus the per-module tables |
| Confirmation | `BdmConfirm`, `TierDowngradeConfirm` |
| Legacy actions | `WorkflowPanel` (`ActionSpec`-driven) |
| Student views | `Student360*` (school), `OverseasStudent360Page` (counselor) |

## 15. API client layer — `apps/web/lib` (233 modules, one per feature)
- `api.ts` has two fetchers:
  - `serverApi<T>()` is server-only, uses `no-store` and throws `ApiError`.
  - `publicApi<T>()` revalidates every 60 s.
- `apiErrors.ts` provides `sendJson()` (never throws; returns `{ok,…}`), `detailMessage()`, `Page<T>`/`isPage` and
  `NOT_COMPLETED`.
- Types are hand-copied from the backend dicts, and nothing is generated from OpenAPI.
- **Utilities:** `idempotencyKey.ts`, `safeNext.ts`, `formatDate.ts`/`formatCalendarDate`, `useNowIstMin.ts`,
  `useUrlList`.

## 16. Forms and validation
- Forms are plain controlled React forms, with **no form or schema library** (`package.json` has no zod and no
  react-hook-form). The server's 422/409/403 `detail` is the source of truth, shown through `FormMessage`.
- `lib/focus.ts` and `useFocusAfterRender` handle focus, and `useLeaveGuard` protects unsaved edits. When a request fails,
  the user's entry is kept and `NOT_COMPLETED` is shown.

## 17. Design system
- The design tokens are on `:root` in `app/globals.css` (`--blue`, `--navy`, `--ink`, `--muted`, `--line`, `--soft`,
  `--green`/`--amber`/`--red`, `--radius`, `--shadow`), alongside utility classes (`.container`, `.card`, `.grid.*`,
  `.eyebrow` and so on). Form controls are styled in `app/controls.css`.
- There is **no Tailwind, no component library and no dark mode**. The UX reference is `docs/ux/` (the `SCR-*` catalog and
  `ROLE_NAVIGATION.md`).

## 18. State management
- **There is no global store** (no SWR, react-query or zustand). The server is the source of truth, and panels use local
  `useState`.
- The only React context is `TripLiveContext` (`lib/tripLive.ts`).
- **List state is in the URL** (`useUrlList`).
- Cross-panel sync uses `router.refresh()`, `RefreshOnHistoryNav` and `lib/usersChanged.ts`.

## 19. Background jobs — `app/worker.py`
Celery uses Redis as both broker and backend, with a UTC clock. **The beat schedule has 14 jobs:**

| Job | Schedule |
|---|---|
| `enh014-sweep-stale-deliveries` | every 5 min |
| `agn017-daily-reminders` | 02:30 UTC (08:00 IST) |
| `ccrm030-counselor-reminders` | 02:45 UTC (08:15 IST) |
| `ccrm021-document-expiry` | 18:35 UTC (00:05 IST) |
| `ccrm025-offer-expiry` | 18:40 UTC (00:10 IST) |
| `bdm012-reminders` | every 5 min |
| `tel018-conversion-sweep` | every 15 min |
| `tel014-sweep-stale-lead-emails` | every 5 min |
| `tel020-alerts` | every 15 min |
| `rec026-sweep-stale-recruiter-emails` | every 5 min |
| `upc012-sweep-stale-university-emails` | every 5 min |
| `ccrm037-sweep-stale-student-emails` | every 5 min |
| `upc015-alerts` | hourly at :30 UTC |
| `mgmt032-monthly-review` | 1st of each month, 00:30 UTC |

- **Outbox:** `notifications.dispatch.queue_deliveries` writes `queued` rows inside the business transaction. An
  `after_commit` listener then publishes them to Celery, so a rollback sends nothing.
- Each task gets a fresh event loop and disposes the engine pool when it finishes.

## 20. Redis and caching (unchanged)
- Redis is used only as the Celery broker and backend, and by the readiness probe. There is **no application cache and no
  session store**.
- On the web side, `serverApi` uses `no-store` and `publicApi` revalidates every 60 s.

## 21. External integrations (all optional; unset means `not_configured`, never a crash)
| Integration | Where |
|---|---|
| Email | `services/mailer.py` with `EMAIL_TRANSPORT` = `smtp` or **`zoho_api`** (`services/zoho_mail.py`, OAuth refresh token, ENH-032). Prod uses `zoho_api` because DigitalOcean blocks outbound SMTP. Per-module email sweepers cover leads, recruiter, university and student mail. |
| Twilio WhatsApp/SMS | `notifications/twilio.py` |
| CRM webhook | `worker.sync_enquiry_to_crm_task` |
| Razorpay | `services/payment.py`, `api/payments.py`, `api/agent_deposits.py`. HMAC verification, `PaymentWebhookEvent`, `razorpay_mode` test/live (`RAZORPAY_GO_LIVE.md`). |
| Google Meet / Zoho Meeting | `services/meetings.py` plus the per-module `*_meetings.py` |
| Calendar | `services/calendar_ics.py`, `calendar_feeds.py` (iCal feed, ccrm-038) |
| Resume extraction | `services/resume_extract.py` (parsing) with `resume_extraction.py` (apply). Its internals were not inspected here, so whether it calls an external service is `NEEDS_CONFIRMATION`. |
| Files | `services/storage.py`: S3 if `AWS_S3_BUCKET` is set, otherwise local `/data/uploads`. Prod keeps uploads on a Block Storage Volume. Spaces is untested because of `endpoint_url` and the SSE call. |
| Inbound email | `api/inbound.py` (shared-secret webhook) |
| Excel load | `app/direct_tieups/` (university commission master) |

## 22. Logging and error handling (unchanged)
- Logs are structured JSON with `request_id`, and secret keys are redacted. Events are logged after the commit, with
  `extra_fields` holding ids only.
- Errors are raised as `HTTPException(status, "Human sentence")`, using module constants. There is **no global exception
  handler** (0 sites) and no error-code envelope.
- **Audit:** `AuditLog(...)` is constructed at about 250 sites. It is written in the same transaction, with metadata that
  holds ids and reason tokens only (never PII) and dotted action names. nehn-042 added audit search.

## 23. Tests
- **API:** 865 `tests/test_*.py` files and 72 `*helpers*.py` builders (`client_for()`, `login()`, `mk_*`). They use
  pytest-asyncio and `httpx.ASGITransport` against a real PostgreSQL in docker (`api-test`, ci profile). Some suites assert a
  fixed query count.
- **Web:** 638 Vitest and Testing Library tests, and 384 Playwright specs. `playwright.docs.config.ts` is used for the
  user-guide captures.
- **CI:** `scripts/ci-local.ps1` runs ruff, mypy, pytest, tsc, eslint, vitest and Playwright through
  `docker-compose.ci.yml`.
- **Cadence:** each feature runs the lite set. The user runs the full suite every 4–5 stories.

## 24. Docker
- `docker-compose.yml` defines these services:
  - `postgres:16-alpine`
  - `redis:7-alpine`
  - `api` (`alembic upgrade head && uvicorn`)
  - `worker`
  - `beat`
  - `web` (standalone build)
  - the `uploads` volume
- `docker-compose.override.yml` adds Caddy (TLS, ports bound to 127.0.0.1). `docker-compose.ci.yml` adds `api-test` and
  `web-test`.
- **The user runs compose.** Sessions do not start or stop the stack.

## 25. Deployment (changed)
- **DEC-INFRA-002 is merged.** Production is a **DigitalOcean droplet** in BLR1 running this compose stack behind Caddy, with
  **DO Managed PostgreSQL** and uploads on a **Block Storage Volume**. The ID1–ID9 sizing defaults are still UNVERIFIED.
- The supporting docs and scripts are `docs/architecture/DEPLOYMENT.md`, `PROD_SETUP_DIGITALOCEAN.md`,
  `scripts/deploy-copy-to-droplet.ps1` and `scripts/preflight.ps1`. Prod services are started with `--no-deps` (the
  database is managed).
- The web build on the 2 GB droplet needs swap and excludes tests (memory `prod-server-build-memory`).
- The ECS Fargate and App Platform options in older docs are **not** the as-built path. Do not re-propose them.

## 26. Security-sensitive areas (review these when you touch them)
- **Tokens and session:** `core/security.py`, the `secret_key="change-me"` default, the cookie flags (`cookie_secure` defaults
  to False), `session_version`, and the reset, invite and welcome tokens.
- **Authorization:** `deps.py` and `rbac.py`, every `scope()`/`_scoped_*`, the agency gates, the parent-link logic,
  `require_school_entitlement`, and the `require_permission` resources.
- **Agent self-signup and KYC documents** (agn-024), including its throttle.
- **The proxy route** (it forwards all headers).
- **Uploads:** `files.py`, `storage.py`, the `/local-files` mount, the MIME allowlist and the size cap. Resume files also
  count here (PII; resume text must never reach logs).
- **CSV imports and exports:** `school_bulk`, `telecaller_import`, `university_import`, `crm_exports` and `tabular`.
  `_safe_cell` is the injection guard.
- **Payments and webhooks:** Razorpay (now with a live mode) and the inbound email secret.
- **Management financials:** the ledger, P&L, salaries, capital and investments (partner and accountant roles only).
- **Data exports:** the GDPR path, the audit export and search, the reports, and consent and archive (ccrm-040).

## 27. Performance-sensitive areas
- **Dashboards and metrics:**
  - `services/portal.py` (1.9k LOC)
  - `school_analytics`
  - `telecaller_metrics`, `bdm_metrics`, `bdm_performance`
  - `partnership_metrics`
  - the management snapshot, funnel and drill
  - the counselor dashboard
  - `candidate_search` and resume full-text search (rec-014)
- **Request-path cost:** the eager loads in `get_current_user` run on every request, and many legacy lists are unpaginated.
- **Lock contention:** bulk imports and lock-heavy writes.
- **Beat jobs:** 7 jobs run every 5–15 minutes and scan delivery, reminder and lead tables, so keep those indexed and
  bounded.

## 28. Tight coupling (change carefully)
- **Shared hubs:** `models.py` (274 classes) and `schemas.py` (1,182 classes) are the dominant merge-conflict hotspots, along
  with the large legacy routers.
- **`Enquiry`** is shared across intake, BDM, telecaller and counselor. Its stage rules live in `lead_stages.py` and
  `lead_pipeline.apply_event`.
- **`User`** has two role sources: the legacy fields and the assignment rows.
- **Navigation:** `lib/navigation.ts`, `bdmNav` and `telecallerNav` must match the backend sections.
- **Cross-layer and cross-router imports** are listed in §4. `api.bdm.LIMIT/OFFSET` is the de-facto shared pagination
  constant.

## 29. Conventions to follow (unchanged)
- **Traceability:** cite Feature, AC and DEC IDs in code and tests. Specs and plans go in `docs/superpowers/{specs,plans}`.
  Each feature updates `API_CONTRACT.md` §12x, `RBAC_MATRIX.md` §2.x and the decision register.
- **Write order:**
  1. auth dependency
  2. `scope(user)` (403 for the role, 404 when out of scope)
  3. lock
  4. `require_*`
  5. validate
  6. mutate
  7. `audit()` in the same transaction
  8. **one commit in the router**
  9. `log()`
  10. outbox enqueue
- **Status codes:** 403 for a role, tier or permission denial, 404 out of scope, 409 for a conflict or precondition, 422 for
  field-located validation, and 429 with `Retry-After` for a throttle.
- **Lists:** `limit/offset` returning `{items,total,limit,offset}`, with the state in the URL.
- **Time:** use `db_now(db)` and IST business days.
- **Integrations:** optional integrations return a status and never raise into the request.
- **Web:** `serverApi` in pages, `sendJson` in panels, `*Server.ts` for server-only helpers, and types copied into
  `lib/<feature>.ts`.
- **Style:** ruff line length is 200, and mypy is lenient.

## 30. Reusable modules for new enhancements
| Need | Use |
|---|---|
| Current user | `deps.get_current_user` |
| Permission gate (dependency) | `deps.require_permission(resource, action, detail)`, following the pattern in `admin.py:135` and `telecaller_reports.py:31` |
| Role and scope gates | Legacy: `workflows._require`, `admin.ensure_admin`. School: `schools._own_school_id`/`_require_coordinator`/`_scoped_students_query`. Agent: `agent_students._gate`, `rbac.agent_may`. New modules: `services/<module>.scope`/`require_*`, `lead_pipeline.scope` |
| Lead pipeline | `services/lead_pipeline.{scope, locked_lead, apply_event, stage_out}`, `lead_stages.py` |
| Tier gate | `schools.require_school_entitlement` |
| Pagination and search | `api.bdm.{LIMIT, OFFSET, SEARCH, _matching}`, `lookups._pattern`; web: `useUrlList`, `Page<T>` |
| Time | `services.bdm_appointments.{db_now, today_ist}`, web `useNowIstMin`, `formatDate`/`formatCalendarDate` |
| Audit and logs | The service `audit()`/`log()` kit (`services/lead_calls.py`) |
| Notifications and email | `notifications.dispatch.queue_deliveries` (outbox), `services.mailer` (transport-agnostic, including Zoho API) |
| Scheduled work | A `worker.celery` task plus a `beat_schedule` entry, with the time in UTC and a comment giving the IST equivalent |
| Calendar | `services.calendar_ics`, `calendar_feeds`, `services.meetings` |
| Metrics | `telecaller_metrics`, `bdm_metrics`, `partnership_metrics`, `school_analytics` (batched, fixed query count) |
| Accounts | `services.provisioning` (welcome and set-password link) |
| Files, PDF and CSV | `services.storage.storage`, `reporting/pdf.py`, `services.tabular`, `_safe_cell` |
| Conflicts and idempotency | `schools._flush_or_409`, the `Idempotency-Key` header, web `newIdempotencyKey()` |
| Web | `serverApi`, `ApiError`, `sendJson`, `detailMessage`, `PortalShell`, `accessUnavailable`, `SectionUnavailable`, `FormMessage`, `DataTable`, `BdmConfirm`, `useLeaveGuard`, `lib/focus` |

## Known gaps (observations only; each needs a Decision ID or `NEEDS_CONFIRMATION` before anyone acts on it)
1. There is no CSRF token and no global rate limiter, only per-endpoint DB-counted throttles.
2. `auto_create_schema=True`, `secret_key="change-me"` and `cookie_secure=False` are the defaults. Confirm that prod `.env`
   overrides all three.
3. There are three RBAC styles: inline role checks (the standard), `require_permission` (9 sites) and an unused
   `require_role`/`require_division`.
4. There is no repository layer. The leaks from services into `app.api` grew from 4 to 13 modules.
5. `models.py` and `schemas.py` have doubled (7k and 14.8k LOC). 125 `payload: dict` handlers remain, there is no global
   error envelope, and no API types are generated.
6. `middleware.ts` still does not cover `/school` or `/account`.
7. `db_now` is still duplicated three times. The domain packages are still empty placeholders.
8. Uploads cannot move to DO Spaces without code changes (`endpoint_url`, the SSE call).
