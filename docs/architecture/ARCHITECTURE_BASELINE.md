# EduSphere — As-Built Architecture Baseline (2026-09-28, updated for ENH-016/ENH-024)

Status: **DESCRIPTIVE, not a decision.** Snapshot of the code as it stands at `main@bedbcce` (ENH-016 analytics and ENH-024 Skill India merged), for enhancement sessions to
reference before they change anything. The intended architecture is in `ARCHITECTURE.md`, and the decisions are in
`docs/decisions/`. Where this file and those differ, this file records what the code does and makes no ruling on which is right.

Method: the existing graphify graph was queried first (`graphify-out/graph.json`, 12,488 nodes / 29,935 edges, refreshed with
`graphify update` on `main@bedbcce`). The findings were then checked against the source files cited below. God nodes: `User`, `hash_password`,
`AuditLog`, `login`, `SchoolStudent`, `serverApi`, `UserRoleAssignment`, `Batch`, `School`, `Base`. The graph found no
import cycles. Re-verified on 2026-09-28 by script against the source (route, model and schema counts, config defaults,
cookie flags, middleware matcher, Celery tasks, test counts), first at `2a117b6` and again at `bedbcce`.

---

## 1. System shape

```
Browser ──► Next.js 15 (apps/web, standalone)  ──server fetch──►  FastAPI (apps/api, /api/v1)  ──► PostgreSQL 16
   │           ├─ RSC pages call serverApi() with forwarded cookies        │  asyncpg / SQLAlchemy 2 async
   └─ client ──┴─ /api/[...path] route.ts = transparent proxy ─────────────┤
                                                                           ├──► Redis 7 (Celery broker/backend only)
                                         Celery worker + beat ◄────────────┘
                                         S3 (optional) / local /data/uploads
```
- **Modular monolith in intent, flat monolith in practice.** The domain packages `app/{identity,admissions,courses,…}`
  exist but are empty placeholders. `app/agents` and `app/overseas` are frozen by decision (DEC-001 and DEC-002; see their
  `__init__.py`). All the real code lives in `app/api`, `app/services`, `app/core`, `app/models.py` and `app/schemas.py`.
- Backend size: about 19k LOC. The largest files are `api/schools.py` (2.6k), `api/workflows.py` (2.5k),
  `schemas.py` (1.8k), `api/admin.py` (1.5k), `services/portal.py` (1.5k) and `models.py` (1.5k, 93 classes).

## 2. FastAPI structure — `apps/api/app`
| Path | Role |
|---|---|
| `main.py` | App factory, lifespan, `RequestIdMiddleware`, CORS (single `frontend_url`, credentials on). Mounts 25 routers under `/api/v1` and `/local-files` static files, plus `/health` and `/health/ready` (checks DB and Redis). |
| `core/config.py` | `pydantic-settings` `Settings` (from `.env`). Every integration is optional; if it is unset, callers report "not_configured". |
| `core/database.py` | Async engine and `SessionLocal`. `get_db()` yields one session per request. It does **not** auto-commit: each handler commits itself. |
| `core/security.py` | bcrypt hashing and HS256 JWT (`sub`, `role`, `division`, `type`). |
| `core/rbac.py` | `PERMISSIONS` bundles per role, plus the `user_has_{role,division,permission}` checks over `UserRoleAssignment`. |
| `core/logging.py` / `middleware.py` | JSON logs, `request_id_ctx`/`user_id_ctx` ContextVars, key redaction, `X-Request-Id`. |
| `core/identifiers.py` | Student-code and uuid-reference helpers. |
| `api/*.py` | Routers **and** business logic (see §4). |
| `services/*.py` | Thin integration and cross-cutting services (see §4). |
| `worker.py` | Celery app and tasks. |
| `seed.py`, `bootstrap_admin.py` | Demo seed data and first-admin bootstrap. |

## 3. Routers and API boundaries
- 311 route decorators across 21 modules. Prefix groups: `/auth`, public (`public.py`, no auth), `/portal/{division}/{role}/{section}`
  (a generic read payload built by `services/portal.py`), `/admin` (+ `agents_router`), `/files`, `workflows` (IT and Overseas
  write actions), `/payments`, `/cms`, `/communications`, `/inbound` (webhooks), `/account`, `/employer`, `/school`
  (+ `school_transfers` coordinator/admin, `school_feedback` coordinator/admin, `school_skills`, `school_student_profile`,
  `student_360`), `portfolio` (+ `portfolio_certificates`), and `school_analytics` (ENH-016: `school_router` under `/school/analytics/*`
  and `/school/students/{id}/scorecard`, plus `admin_router` under `/overseas-admin/analytics/*`).
- Some modules export two routers so that coordinator and admin surfaces are separated (`school_transfers`, `school_feedback`,
  `school_analytics`).
- The contract of record is `docs/architecture/API_CONTRACT.md`.

## 4. Business logic placement
- **There is no service layer for domain logic.** Handlers hold the business rules, the queries and the transaction control
  inline, with private `_helpers` in the same module. For example, `schools.py` holds the tier and entitlement engine,
  promotion, roster CSV parsing, parent linking, career records and notifications.
- `services/` contains only: `portal.py` (role dashboards), `provisioning.py` (account creation and welcome link),
  `mailer.py` (SMTP via `asyncio.to_thread`), `meetings.py` (Google Meet / Zoho), `storage.py` (S3 or local),
  `payment.py` (Razorpay orders), `integrations.py` (optional webhooks), `certificates.py` / `billing_documents.py`
  (reportlab PDFs) and `image_metadata.py`.
- Cross-module imports between routers exist. `require_school_entitlement`, `TIER_SERVICES` and the scope helpers are
  defined in `api/schools.py` and imported by the other school routers.
- **First reusable computation layer:** `api/school_analytics.py` (ENH-016) holds batched, fixed-query-count functions
  (`students_in`, `student_indicators`, `portfolio_started_ids`, `skill_statuses`, `build_scorecards`, `utilization`,
  `cross_school_rows`) that take already scope-checked ids. It still lives in `api/`, not `services/`.
- ⚠ **Import cycle:** `school_analytics` imports `schools`, and `schools` imports `school_analytics` back through
  function-local imports (`schools.py:454`, `:1131`, marked `noqa: PLC0415`). Keep new shared helpers out of this loop.

## 5. Data access
- **There are no repository classes.** Handlers issue SQLAlchemy 2.0 `select()` directly against `AsyncSession`.
- Concurrency uses pessimistic locks: `with_for_update()` (sometimes `key_share`/`read`/`of=`, and `populate_existing`) at
  35 call sites. Rows are locked in a deterministic `ORDER BY id` for batch operations (promotion, transfers).
  The promotion path uses `lock_timeout` (`PROMOTION_LOCK_TIMEOUT="5s"`). `IntegrityError` is mapped to 409 via
  `_flush_or_409` and a named-constraint check.
- Eager loading is used sparingly (8 `selectinload`/`joinedload` references). `get_current_user` always eager-loads `role_assignments`.

## 6. SQLAlchemy models — `app/models.py` (single file)
- `Base(DeclarativeBase)` with `TimestampMixin`. There are 93 classes, grouped:
  - identity: `User`, `UserRoleAssignment`, `PasswordResetToken`, `AuditLog`, `DataSubjectRequest`
  - IT learning: `Program`, `Batch`, `Enrollment`, attendance, assessments, `LiveSession`, `Certificate`
  - employer and placement: `Company`, `EmployerProfile`, `Job`, `JobApplication`, `Interview`, `JobOffer`
  - overseas and agent: `Country`, `University`, `OverseasApplication`, `VisaCase`, `Scholarship`, `AgentStudent`, `AgentCommission`
  - finance: `Payment`, `Invoice`, `Receipt`, `EMISchedule`, `PaymentWebhookEvent`
  - CMS and comms: `Enquiry`, `ContentPage`, `BlogPost`, `Notification`, `NotificationDelivery`, `Message`, `SupportTicket`
  - School (about 28 classes; `PortfolioEntry` gained the ENH-024 Skill India columns and four `ck_portfolio_cert_*` CHECKs): `School` (tier, `tier_valid_until`), `AcademicYear`, `SchoolStudent`, `SchoolParentLink`,
    grade history, transfers, `SchoolStaffAssignment` (portfolio), and career, psychometric, test-prep, language, skills,
    academic results and activity/feedback records, plus roster upload batches.
- `User` has **legacy single-value** `role` and `division` columns and a `profile` JSON column (which carries `school_id`),
  in addition to the multi-row `UserRoleAssignment` table.
- Both `DATA_MODEL.md` and `models.py` exist. Check both before adding columns.

## 7. Pydantic schemas — `app/schemas.py` (single file, 149 classes)
- These are Pydantic v2 models with `field_validator`s, e.g. student master fields and `StudentPromotionRequest`.
- **Usage is mixed.** About 64 handlers take typed models, and about 73 still take `payload: dict` and validate by hand
  (e.g. `_master_fields_or_422`). Most older responses are hand-built dicts via `_x_out()` helpers. `response_model` (52 uses) is the norm in the newer
  routers (`school_transfers`, `school_skills`, `public`, `school_analytics`, `auth`, `school_feedback`); follow that in new code.
- Pagination: there is a list envelope `{items,total,limit,offset}` (frontend `Page<T>`), but only 7 endpoints take
  `limit`/`offset` (`school_transfers` ×2, `school_feedback` ×2, `school_skills`, `school_analytics` ×2), all as
  `Query(25, ge=1, le=100)`; copy that signature. Most list endpoints return plain arrays.

## 8. PostgreSQL
- PostgreSQL 16 through asyncpg. JSON columns are serialized with a custom UUID/date-aware serializer. Named unique
  constraints act as business rules (e.g. `uq_school_students_roll`, `uq_role_assignment_identity`).
- Time zones: the `datetime` columns are UTC. Tier validity is checked against the **Asia/Kolkata** calendar date
  (`TIER_TIMEZONE`).

## 9. Migrations — `apps/api/alembic`
- 44 sequential, numbered revisions (`0001_initial` … `0044_skill_india_certification`). `env.py` is async and uses
  `target_metadata=Base.metadata` with `compare_type=True`.
- They run `alembic upgrade head` at container start (compose `api.command` / `entrypoint.sh` with `RUN_MIGRATIONS`).
- ⚠ `Settings.auto_create_schema` defaults to **True** (the lifespan runs `create_all`). Tests switch it off. A new model
  can therefore appear to work locally without a migration. Every schema change still needs an Alembic revision.

## 10. Authentication — `api/auth.py`, `api/deps.py`
- JWT access and refresh tokens are set as **httpOnly cookies** `edusphere_access` / `edusphere_refresh` (`SameSite=Lax`,
  `Secure` from `COOKIE_SECURE`). Access tokens last 60 min and refresh tokens 14 days.
- Endpoints: `/login`, `/register`, `/refresh`, `/logout`, `GET/PATCH /me`, `/forgot-password`, `/reset-password`, and
  `/change-password` (DB-counted failure lockout).
- `get_current_user` decodes the cookie, requires `type=access`, and loads an active `User`.
- There is **no CSRF token**; the design relies on SameSite=Lax. There is **no Redis-backed rate limiter**; the only
  throttle is the change-password lockout.
- Set-password and invite links are one-time tokens (`PasswordResetToken`, `SchoolAccountInvite`, 7-day invites).

## 11. Authorization / RBAC
- There are **two mechanisms, and both are in use**:
  1. The formal, deny-by-default layer, `deps.require_role/require_division/require_permission`, resolves against active,
     usable `UserRoleAssignment` rows. An agent needs `approval_status=approved`.
  2. The common in-route layer checks the legacy `user.role` directly: `admin.ensure_admin`, `schools._require_coordinator`,
     `_own_school_id` and the `SCHOOL_ROLES` sets. For agents it adds `rbac.agent_is_approved(user)`.
- **Resource scope is enforced in queries, not in the role bundles.**
  - `_scoped_students_query`: principal and coordinator see their own school, a teacher sees assigned students, and a
    parent sees `SchoolParentLink` rows only (these may cross schools).
  - Service-delivery roles (`academic_team`, `career_counselor`, `psychometric_team`) are scoped to a portfolio through
    `SchoolStaffAssignment` (`_portfolio_school_ids`, `_student_in_portfolio`).
- **Tier entitlement** is enforced by `schools.require_school_entitlement(db, user, school_id, service_key, grandfathered_since=)`.
  Call it *after* the role and scope checks and *before* any write. A denial **commits** its own audit row, so nothing
  else may be pending in the session at that point. Grandfathering (ENH-023) is also handled there.
- The role matrix of record is `RBAC_MATRIX.md`.

## 12. Next.js routing — `apps/web/app` (App Router, Next 15, React 19)
- Public pages: `/`, `contact`, `faq`, `gallery`, `news`, `search`, plus `robots.ts` and `sitemap.ts`.
- Portals: `/it/{student,trainer,placement,hr,admin}/…` and `/overseas/{student,counselor,university,agent,admin}/…`
  (generic `PortalPage` driven by `PORTAL_NAV`), `/admin/…`, `/account`, and
  `/school/{coordinator,principal,teacher,parent,academic-team,career-counselor,psychometric-team,invite}/…`.
  There are 114 `page.tsx` files, plus `/overseas/admin/school-analytics` (ENH-016, with a `loading.tsx`).
- `middleware.ts` only checks that the cookie **exists**, only on `/it`, `/overseas` and `/admin`, and redirects to the
  division login. **`/school/*` and `/account` are not covered.** Those pages rely on `serverApi` throwing `ApiError(401/403)`
  → `accessUnavailable(e)`. In every case the real authorization is on the backend.
- Route handlers: `app/api/[...path]/route.ts` (a transparent proxy to `${BACKEND_INTERNAL_URL}/api/*`, which forwards
  headers and cookies) and `app/local-files/[...path]`.

## 13. Server and client components
- **Pages are async server components.** They `Promise.all` their `serverApi()` calls (always `/auth/me` first), catch into
  `accessUnavailable()`, and render `PortalShell` with a nav from `lib/navigation.ts` and a panel.
- **Panels are client components** (`"use client"`, 108 of 145 `.tsx` components). They receive initial data as props and
  mutate through `fetch('/api/v1/…')` via the proxy, then `router.refresh()` or update local state.

## 14. Shared frontend components (reuse these)
- Shells and layout: `PortalShell`, `PublicShell`, `PortalSection`, `PageHero`, `SiteHeader`/`DesktopNav`/`MobileNavToggle`, `Footer`.
- State and feedback: `AccessUnavailable`/`accessUnavailable()`, `LoadFailureAlert`, `FormMessage`, `UnsentFeedbackNote`, `LocalTime`.
- Data: `DataTable`, `CollectionExplorer`, `ReportPreview`, `SchoolReportCharts`.
- Analytics (ENH-016): `SchoolKpiBoard`, `SchoolGradePerformance`, `SchoolStudentDevelopment`, `SchoolScorecardGrid`,
  `StudentScorecard`, `CrossSchoolAnalytics`, `SchoolAnalyticsSections`, `SectionUnavailable` (a per-section failure notice), `ScrollToHash`.
- Generic workflows: `WorkflowPanel` (the `ActionSpec`-driven action forms for the IT and Overseas portals).
- School building blocks: `SchoolStudentFields`, `Student360*`, `TierDowngradeConfirm`, `useSkillAction`.

## 15. API client layer — `apps/web/lib`
- `api.ts`: `serverApi<T>()` (server-only: `cookies()`, `no-store`, throws `ApiError(detail,status)`) and `publicApi<T>()`
  (revalidates every 60 s).
- `apiErrors.ts`: `detailMessage()` (handles a string or the FastAPI 422 list), `sendJson()` (never throws and returns
  `{ok,…}`), `isPage()`/`Page<T>`, `isRequestBody()`, `NOT_COMPLETED`. Older panels still carry copy-pasted versions of
  `detailMessage`.
- Domain helpers: `schoolStudents.ts`, `transfers.ts`, `skills.ts`, `student360*.ts`, `careerRecords.ts`, `portfolio.ts`,
  `internship.ts`, `activityFeedback.ts`, `schoolAnalytics.ts`, `student360Links.ts`, `plural.ts`, `formatDate.ts`, `focus.ts`,
  `i18n.ts`, `site.ts` (untracked), `types.ts`.

## 16. Forms and validation
- The forms are plain controlled React forms, with **no form or schema library** (no zod or react-hook-form). Client
  checks are light, and the server's 422/409/403 `detail` is the source of truth, shown via `FormMessage`/`detailMessage`.
- Focus management goes through `lib/focus.ts`. The entry is kept on network failure (`NOT_COMPLETED`).

## 17. Design system
- `app/globals.css` (single-line utility CSS) defines tokens on `:root`: `--blue`, `--navy`, `--ink`, `--muted`, `--line`,
  `--soft`, `--green`/`--amber`/`--red`, `--radius:18px` and `--shadow`, plus the classes `.container`, `.section`,
  `.card`, `.grid.two/three/four`, `.eyebrow`, `.lead` and `.muted`.
- `app/controls.css` holds the form controls. Two components use CSS modules (`ProgramCatalogue`, `SchoolPromotionPanel`).
- There is no Tailwind, no component library and **no dark mode**.
- The UX reference is `docs/ux/` (screen catalog `SCR-*`, `UX_REFERENCE_AUDIT.md`).

## 18. State management
- **None global.** There are no context providers, SWR or react-query. The server is the source of truth: RSC fetches
  per request, and client panels hold local `useState`. Cross-panel sync uses `router.refresh()` and `lib/usersChanged.ts`
  (an event helper).

## 19. Background jobs
- `worker.py` defines a Celery app (Redis broker and backend) with two tasks: `heartbeat_task`, and
  `sync_enquiry_to_crm_task` (outbox-style, exponential backoff, 5 retries), queued from `public.create_enquiry`.
- The compose file runs a `beat` service, but **no `beat_schedule` is defined**, so nothing runs on a schedule. There is no
  expiry sweeper: tier expiry and invite expiry are evaluated lazily at request time.
- Email, notification and meeting calls run **inline in the request** (SMTP runs in `asyncio.to_thread`). `FastAPI.BackgroundTasks` is not used.

## 20. Redis and caching
- Redis is used only as the Celery broker and backend and as a readiness probe. There is **no application cache**, no
  session store and no rate limiting.
- Next.js caching: `serverApi` uses `no-store`, and `publicApi` revalidates every 60 s.

## 21. External integrations (all optional and config-gated; unset means `not_configured`, not a crash)
| Integration | Where | Notes |
|---|---|---|
| SMTP email | `services/mailer.py` | invites, welcome and set-password links, parent notifications |
| WhatsApp/SMS/email webhooks | `services/integrations.send_notification` | status and error persisted on `NotificationDelivery` |
| CRM webhook | `worker.sync_enquiry_to_crm_task` | retried by Celery |
| Razorpay | `services/payment.py`, `api/payments.py` | HMAC-SHA256 signature verification, `PaymentWebhookEvent` |
| Google Meet / Zoho Meeting | `services/meetings.py` | OAuth refresh-token flow |
| S3 | `services/storage.py` | presigned PUT/GET (15 min), SSE-AES256; falls back to local `/data/uploads` with a path-traversal guard |
| Inbound university email | `api/inbound.py` | shared-secret webhook (`inbound_email_webhook_secret`) |
- Provider choices remain decision-gated (see `CLAUDE.md` → Scope/Technology).

## 22. Logging and error handling
- Structured JSON to stdout, with a request ID on every line. Keys such as password/token/secret are redacted.
  Security-relevant events log `extra_fields` (actor, role, school, reason).
- Errors are `HTTPException(status, "human sentence")`, so `detail` is displayed by the UI verbatim. **There is no global
  exception handler or error-code envelope.** 422 errors keep FastAPI's default list shape.
- Audit: `AuditLog(user_id, action, entity_type, entity_id, outcome, metadata_json)` is written in about 102 places. Each
  router has its own `_audit` helper (`workflows`, `school_skills`, `school_transfers`, …). Convention: the audit row goes in
  the same transaction, metadata carries IDs and reason tokens only (no PII), and it includes `request_id`.

## 23. Tests
- **API:** 156 `tests/test_*.py` files (named by feature ID, e.g. `test_enh_023_tier_change.py`) with `enhNNN_helpers.py`
  builders. ENH-016 adds fixed query-count assertions and a check that analytics logs carry ids only. They use pytest and pytest-asyncio (strict), `httpx.ASGITransport` against the real app, and a **real
  PostgreSQL** (dev DB; see RAID I-06/I-07/I-41 on test debris). The engine is disposed before each test.
- **Web:** 94 Vitest and Testing Library unit tests (`tests/components`, `tests/lib`) and 100 Playwright E2E specs (`tests/e2e`).
- **CI:** `.github/workflows/ci.yml` runs `scripts/ci-local.ps1` (the local-equivalent gate: ruff, mypy, pytest, tsc, eslint,
  vitest, Playwright, via `docker-compose.ci.yml`) and uploads compact reports.
- Traceability goes from test to Feature ID to AC through `docs/quality` (RTM).

## 24. Docker
- `docker-compose.yml`: `postgres:16-alpine`, `redis:7-alpine` (AOF), `api` (migrate, then uvicorn), `worker`, `beat`, and
  `web` (standalone build, with `ENVIRONMENT` controlling the demo-accounts box). The volumes are the Postgres and Redis
  data and `uploads`.
- `docker-compose.override.yml` adds Caddy for TLS (`WEB_DOMAIN`→web, `API_DOMAIN`→api), with the ports bound to 127.0.0.1.
- `docker-compose.ci.yml` and the `Dockerfile.ci` files are for CI.
- The user runs compose; sessions do not start or stop it.

## 25. Deployment
- As built, this is a single-host Docker Compose deployment behind Caddy. The target cloud design (ECS Fargate, etc.) in
  `DEPLOYMENT.md` and `SCALING.md` is **not confirmed**: `DEC-TECH-001`, `DEC-ARCH-001` and `DEC-INFRA-001` gate it.
  Do not add provider-specific infrastructure.

## 26. Security-sensitive areas (touch with a security review)
- `core/security.py` and `config.secret_key` (default `"change-me"`), cookie flags in `auth.py`, and the reset, invite and
  welcome token flows.
- `deps.py` / `rbac.py`, plus every scope helper: `_scoped_students_query`, `_portfolio_school_ids`,
  `_load_readable_student`, and the parent-link logic (cross-school links are allowed by design).
- `require_school_entitlement` and grandfathering; transfers (`school_transfers.py`, which moves parent links).
- The web proxy `app/api/[...path]/route.ts` forwards **all** headers and cookies. `middleware.ts` coverage gaps are
  cosmetic only (the backend enforces), but they must not be relied on.
- File upload and download (`files.py`, `storage.py`, the `/local-files` static mount, MIME allowlist, 20 MB cap).
  Payment signature and webhook verification, and the inbound email secret.
- The GDPR export and deletion paths (`DataSubjectRequest`) and the audit export.

## 27. Performance-sensitive areas
- `schools._school_dashboard_payload` and `school_reports` (multi-aggregate; the dashboard now also calls into `school_analytics`),
  the `school_analytics` endpoints (tested for a fixed query count; keep new metrics batched), `services/portal.py` (role dashboards),
  `student_360.py` and the timeline assembly, and `admin.py` directory and audit listings.
- Most list endpoints are **unpaginated** and return full arrays.
- Bulk roster CSV upload (row-by-row validation), promotion (locks N students), and transfer approval (locks student,
  request and parents).
- Synchronous side effects in the request path: SMTP, notification webhooks, meeting creation. `get_active_assignments`
  runs a DB query for every `require_*` check.

## 28. Tight coupling (change carefully)
- `models.py`, `schemas.py` and the large routers (`schools.py`, `workflows.py`, `admin.py`) act as shared hubs.
- The other school routers import `schools.py` for entitlement, tier and scope helpers.
- `User.role`/`division`/`profile.school_id` (legacy) sit alongside `UserRoleAssignment`. Code reads both.
- `services/portal.py` imports about 40 models and the RBAC table; `PORTAL_NAV`/`SCHOOL_NAV` must match the backend
  `/portal/{division}/{role}/{section}` sections.
- The frontend types (`lib/types.ts` and inline page types) are hand-written copies of backend dict shapes. Nothing is
  generated from OpenAPI.

## 29. Conventions to follow
- Traceability: the code cites Feature, AC and Decision IDs in docstrings and comments (`ENH-023 (DEC-SCOPE-030 D2)`).
  Tests are named by feature. Specs and plans live in `docs/superpowers/{specs,plans}`, and QA evidence in `docs/quality`.
- Handler order: auth dependency → role check → scope query → entitlement check → lock rows (`with_for_update`, ordered)
  → validate → mutate → `AuditLog` in the same transaction → commit → notify.
- Errors are human-readable `detail` strings, and the UI displays them as written. Use 409 for conflicts or precondition
  failures (e.g. the `expected_tier` precondition), 403 for scope, role or tier denials, and 422 for validation.
- Optional integrations return a status tuple and never raise into the request.
- Pages are server-rendered with `serverApi` → `accessUnavailable`. Mutations happen in client panels via `sendJson` or
  `fetch('/api/v1/…')`.
- Ruff line length is 200 and mypy is lenient. Frontend style is dense one-liners in older files and formatted code in newer ones.

## 30. Reusable modules for new enhancements
| Need | Use |
|---|---|
| current user / role gate | `deps.get_current_user`, `require_role/division/permission`; school: `_own_school_id`, `_require_coordinator(_user)` |
| student scoping | `schools._scoped_students_query`, `_load_readable_student`, `_student_in_portfolio`, `_portfolio_school_ids` |
| tier gate | `schools.require_school_entitlement` (+ `TIER_SERVICES`, `_cumulative_services`, `_entitlement_denial` for a non-raising check) |
| school read gate | `school_feedback._require_school_reader` (coordinator or principal, own school) |
| student metrics | `school_analytics.students_in`, `student_indicators`, `build_scorecards`, `service_usage` (batched, scope-checked ids in) |
| audit | the `AuditLog` pattern from `school_transfers._audit` (IDs only, `request_id`, same transaction) |
| conflict mapping | `schools._flush_or_409`, `_is_roll_conflict` |
| notifications | `schools._notify_parent/_notify_student_parents/_notify_school_parents`, `services.mailer`, `services.integrations.send_notification` |
| account creation | `services.provisioning` (welcome and set-password link; admins never set passwords) |
| files | `services.storage.storage` (presign, read, write, delete) |
| PDFs | `services.certificates`, `services.billing_documents` |
| async job | `worker.celery` task with retry/backoff (outbox pattern) |
| logging | `core.logging.get_logger` + `extra_fields`, `request_id_ctx` |
| web fetch/errors | `lib/api.serverApi`, `ApiError`, `lib/apiErrors.{sendJson,detailMessage,isPage,Page}` |
| web shell/UI | `PortalShell`, `accessUnavailable`, `FormMessage`, `LoadFailureAlert`, `DataTable`, `lib/navigation`, `lib/formatDate`, `lib/focus` |

## Known gaps worth a Decision before building on them
These are observations only. Each needs `NEEDS_CONFIRMATION` or a Decision ID; do not fix them opportunistically:
1. There is no CSRF token and no rate limiting beyond the change-password lockout.
2. `auto_create_schema=True` is the default.
3. Two parallel RBAC mechanisms: the legacy `user.role` and `UserRoleAssignment`.
4. No domain service or repository layer; the domain packages are empty.
5. Most list endpoints are unpaginated.
6. The Celery `beat` service has no schedule, and side effects run inline.
7. `middleware.ts` does not cover `/school` or `/account`.
8. No global error envelope, and no generated API types.
9. `schools` ↔ `school_analytics` import cycle, held together by function-local imports.
