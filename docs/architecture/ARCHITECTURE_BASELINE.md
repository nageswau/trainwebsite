# EduSphere — As-Built Architecture Baseline (2026-10-07, `main@70243aaf`)

Status: **DESCRIPTIVE, not a decision.** This is a snapshot of what the code does at `main@70243aaf` (tel-026 merged), for
enhancement sessions to read before they change anything. The intended architecture is in `ARCHITECTURE.md`, and the
decisions are in `docs/decisions/`. Where they differ from this file, this file records the code and makes no ruling.

It supersedes the 2026-09-28 baseline on the unmerged branch `docs/architecture-baseline` (`427516bd`, `main@bedbcce`). Since
then the Agent CRM (AGN-*), BDM CRM (bdm-*) and Telecaller CRM (tel-*) modules have landed. They roughly tripled the backend and
brought a real service layer, a Celery beat schedule, an outbox for notifications, and a standard pagination signature.

Method: graphify was refreshed first with `graphify update .` (AST only), giving 31,045 nodes, 92,458 edges and 1,101
communities. The graph found no import cycles. Its god nodes are `User` (1,820 edges), `AuditLog`, `client_for()`, `login()`,
`Enquiry`, `serverApi()` and `sendJson()`. Every count below was then re-checked by script against the source. Documents
changed since 2026-10-05 were **not** re-extracted semantically, so the doc nodes in the graph may be stale.

---

## 1. System shape
```
Browser ──► Next.js 15 / React 19 (apps/web, standalone) ──server fetch──► FastAPI (apps/api, /api/v1) ──► PostgreSQL 16
   │          ├─ RSC pages: serverApi() forwards cookies                          │  asyncpg + SQLAlchemy 2 async
   └─ client ─┴─ app/api/[...path]/route.ts = transparent proxy ──────────────────┤
                                                                                  ├──► Redis 7 (Celery broker/backend only)
                                   Celery worker + beat (6 scheduled jobs) ◄──────┘
                                   S3 (optional) or local /data/uploads
```
- **This is a flat monolith.** The domain packages `app/{identity,admissions,courses,cms,employers,finance,learning,operations,
  overseas,students,trainers,agents}` are empty placeholders. The real code lives in `app/api` (73 router modules, about 21.3k
  LOC), `app/services` (68 modules, about 14.6k LOC), `app/core`, `app/notifications`, `app/reporting`, `app/models.py` and
  `app/schemas.py`. The whole backend app is about 48k LOC.
- The product has five business surfaces: IT Academy, Overseas Education (with Agent CRM), School portal, BDM CRM and
  Telecaller CRM. They share one `users` table, one `Enquiry` (lead) table and one `AuditLog`.

## 2. FastAPI structure — `apps/api/app`
| Path | Role |
|---|---|
| `main.py` | Creates the app with a lifespan (configures logging, runs `create_all` if `auto_create_schema`, creates the upload dir). Adds `RequestIdMiddleware` and CORS (one `frontend_url`, credentials on). Includes about 90 routers in a single `for r in (...)` tuple under `/api/v1`. Also serves `/local-files` static files, `/health` and `/health/ready` (checks DB and Redis, returns 503 if degraded). |
| `core/config.py` | `pydantic-settings` `Settings` read from `.env`. Every integration is optional. |
| `core/database.py` | Async engine with `pool_pre_ping` and a UUID/date-aware JSON serializer, plus `SessionLocal`. `get_db()` yields one session and **never auto-commits**. |
| `core/security.py` | bcrypt hashing and HS256 JWT with the claims `sub`, `role`, `division`, `type`, `exp` and `sv` (session version). |
| `core/rbac.py` | The `PERMISSIONS` bundles, assignment checks, and the agency helpers `agent_denial_reason`, `is_agent_staff`, `agent_may`. |
| `core/logging.py`, `core/middleware.py` | JSON logs, the `request_id_ctx`/`user_id_ctx` ContextVars, key redaction and `X-Request-Id`. |
| `core/identifiers.py` | Student-code and reference helpers. |
| `bdm_stages.py`, `lead_stages.py`, `tel_sources.py`, `tel_content_kinds.py` | Module-level enums and stage machines that both models and services use. |
| `api/*.py` | Routers. Older modules also hold business logic. |
| `services/*.py` | Domain services for the AGN, BDM and TEL modules, plus integrations (see §4). |
| `notifications/` | The ENH-014 delivery pipeline: `dispatch` (outbox), `delivery`, `twilio`, `phone`, `lead_email`. |
| `reporting/pdf.py` | A pure PDF renderer (reportlab, dict in and bytes out, one escape point `_p`). |
| `worker.py` | The Celery app, its tasks and the beat schedule. |
| `seed.py`, `bootstrap_admin.py` | Idempotent demo seed (`python -m app.seed`) and the first-admin bootstrap. |

## 3. Routers and API boundaries
- There are **601 route decorators** in 73 modules, all under `/api/v1`. Many modules export several routers to split
  audiences, for example `router`/`admin_router`, `coordinator_router`/`admin_router`, `telecaller_router`/`counselor_router`,
  and `public_router` in `telecaller_content`.
- Prefix families:
  - `/auth` and `/account`
  - `public.py`, `lookups.py` and `telecaller_content.public_router`, all without auth
  - `/portal/{division}/{role}/{section}`, generic dashboards built by `services/portal.py`
  - `/admin` (with `agents_router`)
  - `workflows` (IT and Overseas write actions)
  - `/files`, `/payments`, `/cms`, `/communications`
  - `/inbound` (webhooks)
  - `/employer`
  - `/school*` (about 15 modules)
  - `agent_*` (Agent CRM)
  - `bdm*` (about 22 modules)
  - `/telecaller*` plus `lead_*` (about 16 modules)
- The contract of record is `docs/architecture/API_CONTRACT.md`. Its sections are numbered per feature (for example `12F` …
  `12AH`), and the next free number is tracked in the `tel-*` memory notes.

## 4. Business logic placement — two generations
- **Older modules (IT, Overseas, School, admin): logic sits in the handlers.** Rules, queries and commits are inline, with
  private `_helpers` in the same module. Examples are `schools.py` (2.7k LOC), `workflows.py` (2.9k) and `admin.py` (2.0k).
- **Newer modules (AGN, BDM, TEL): thin router plus service.** The router loads the scope, calls `svc.*`, commits, then
  logs. Every service module exposes the same small kit:
  - `scope(user)` returns `(kind, [filters])` and raises 403 for a role that has no access.
  - `require_*(user)` gates a role or permission.
  - `audit(db, user, action, id, metadata)` adds an `AuditLog` row without committing.
  - `log(event, user, id, **extra)` writes a structured log line.
  - `*_out()` serializers build the response dicts.

  `api/telecaller_calls.py` with `services/lead_calls.py` is the reference example.
- **Commit ownership:** the router commits exactly once per write, and the structured log is written *after* the commit.
  Services only `flush`.
- ⚠ **Layer leaks.** Four services import from `app.api`: `bdm_lifecycle`, `bdm_metrics`, `bdm_performance` and
  `telecaller_lifecycle`. Routers also import each other's private helpers, for example `bdm.LIMIT/OFFSET/SEARCH/_matching`
  (22 times), `lookups._pattern` (9), `admin.ensure_admin`, `agent_students._gate`, `school_feedback._require_school_reader`
  and `workflows._audit/_notify_user`. The cycle between `schools` and `school_analytics` is still broken only by
  function-local imports (`noqa: PLC0415`, 14 sites in total).

## 5. Data access
- **There is no repository layer.** Code calls `select()` on `AsyncSession` directly, in routers (older modules) or services
  (newer ones).
- Concurrency uses pessimistic locks, with 119 `with_for_update()` sites. The common form is `locked_lead()`:
  `with_for_update().execution_options(populate_existing=True)`. Batches lock rows in a deterministic `ORDER BY id`.
  `IntegrityError` is mapped to 409 (`schools._flush_or_409`).
- "Now" comes from the DB (`db_now(db)`), and business days are IST (`today_ist(now)`). Both live in
  `services/bdm_appointments.py`, with copies in `bdm_meeting_requests` and `lead_appointments`. Datetime columns are UTC.
- Eager loading is rare (11 sites). `get_current_user` eager-loads `role_assignments` and `agent_membership.org` on every request.

## 6. SQLAlchemy models — `app/models.py` (single file, 3,176 LOC, 143 classes)
- `Base(DeclarativeBase)` and `TimestampMixin`. The domains are:
  - **Identity:** `User`, `UserRoleAssignment`, `PasswordResetToken`, `AuditLog`, `DataSubjectRequest`, `NotificationPreference`
  - **IT learning:** `Program`, `Batch`, `Enrollment`, `Assignment`, `LiveSession`
  - **Employer:** `Company`, `Job`, `JobApplication`
  - **Overseas:** `Country`, `University`, `OverseasCourse`, `OverseasApplication`, `VisaCase`, `StudentDocument`, `Appointment`
  - **Agent CRM:** `AgentOrg`, `AgentOrgMember`, `AgentStudent`, `AgentCommission`, deposits, tasks, …
  - **Finance:** `Payment`, `Invoice`, `PaymentWebhookEvent`
  - **CMS and comms:** `Enquiry`, `Notification`, `NotificationDelivery`
  - **School:** about 30 classes, centred on `School`, `SchoolStudent`, `SchoolParentLink` and `SchoolStaffAssignment`
  - **BDM:** `BdmOrganization` with profiles, appointments, activities, travel, MoUs, targets and tasks
  - **Telecaller:** `TelecallerProfile`, `LeadStageHistory`, `LeadCall`, follow-ups, messages, content and settings
- **`Enquiry` is the shared lead entity.** Public intake, BDM leads and the telecaller pipeline all use it, through
  `telecaller_user_id`, `status`/stage and `division`.
- `User` keeps the **legacy single-value** `role`, `division` and `profile` JSON (which carries `school_id`), alongside the
  `UserRoleAssignment` rows. It also has `session_version` (AGN-002).
- `DATA_MODEL.md` documents the intended model. Check both it and `models.py` before adding columns.

## 7. Pydantic schemas — `app/schemas.py` (single file, 6,455 LOC, 509 classes)
- Pydantic v2 with `field_validator`s. Typed request bodies are now the majority (157 handlers), but 93 legacy handlers
  still take `payload: dict`. New code uses typed models. `response_model` appears 201 times. Many newer routers still return
  service-built dicts.
- Partial updates use `payload.model_dump(exclude_unset=True)`.
- **Pagination:**
  - Standard signature: `limit: int = LIMIT, offset: int = OFFSET`, where `bdm.LIMIT = Query(50, ge=1, le=100)` and
    `OFFSET = Query(0, ge=0)`. 77 handlers use it.
  - Response envelope: `{items, total, limit, offset}`, which is `Page<T>` on the frontend.
  - Older school lists use `Query(25, …)`. Many legacy lists still return plain arrays.
- Field-level 422s for business rules are raised as `RequestValidationError([{loc:("body",field),…}])` (for example
  `lead_pipeline._invalid`), so the UI can attach the message to the field.

## 8. PostgreSQL
- PostgreSQL 16 through asyncpg. Named unique and CHECK constraints act as business rules, and some are mapped to 409 by name.
- **Time zones:** stored datetimes are UTC. Business-day logic (daily caps, same-day edit windows, reminders, targets) runs
  on Asia/Kolkata dates (9 sites). School tier validity is also checked on the IST date (`TIER_TIMEZONE`).

## 9. Migrations — `apps/api/alembic`
- There are 99 linear, numbered revisions (`0001_initial` … `0099_tel_settings`). `env.py` is async and uses `compare_type=True`.
- The number of the next migration (and the next DEC-SCOPE number) depends on the order features merge. Before you pick
  one, fetch `origin/main` and check `alembic/versions` (memory: `recheck-main-before-building`).
- `alembic upgrade head` runs at container start (`api.command` / `entrypoint.sh`).
- ⚠ `Settings.auto_create_schema` defaults to **True**, which makes the lifespan run `create_all`. Tests set it to False
  (`tests/conftest.py`). A model can therefore seem to work locally without a migration. Every schema change still needs a
  revision.

## 10. Authentication — `api/auth.py`, `api/deps.py`
- Access and refresh JWTs are set as **httpOnly cookies** named `edusphere_access` and `edusphere_refresh` (`SameSite=Lax`,
  `Secure` from `COOKIE_SECURE`, `path=/`). Access tokens last 60 min and refresh tokens 14 days.
- **Session revocation (AGN-002):** each token carries `sv`. `check_session` refuses a token whose `sv` does not match
  `users.session_version`, which deactivation and reset increment. `/auth/refresh` runs the same check.
- `get_current_user` reads the cookie, requires `type=access` and loads an active `User` together with its assignments and
  agency membership. Deactivated agency staff get their own 401 message.
- Endpoints: login, register, refresh, logout, `GET/PATCH /me` (which also returns `agent_permissions`), forgot, reset and
  change password (with a DB-counted lockout), and the invite and welcome one-time tokens.
- There is **no CSRF token** (the design relies on SameSite=Lax) and **no rate limiter** apart from the change-password
  lockout and the per-feature daily caps.

## 11. Authorization / RBAC
- **Inline checks on `User.role` are the pattern in use** (memory: `rbac-follow-inline-pattern`, owner decision 2026-09-28).
  `deps.require_role/require_division/require_permission` exist, but **no router uses them** (0 call sites).
- The role gates differ by module:
  - Legacy: `workflows._require(user, roles, division)`, which also calls `agent_denial_reason`.
  - Admin: `admin.ensure_admin`.
  - School: `schools._require_coordinator`, `_own_school_id` and `school_feedback._require_school_reader`.
  - Agent: `agent_students._gate` and `_require_master_action`, plus `rbac.is_agent_staff` and `agent_may` for staff flags.
  - BDM and TEL: each `services/*` module has `scope(user)` and `require_manager`/`require_telecaller`/`require_creator_may`.
- **Resource scope is applied as query filters.** A row outside the caller's scope reads as **404, not 403** (for example
  `LEAD_NOT_FOUND`). A role with no access to the route gets 403. School scope is per school, per portfolio
  (`SchoolStaffAssignment`) or per parent link. BDM and TEL scope is self, direct reports or team.
- **Tier entitlement:** `schools.require_school_entitlement(...)` runs after the role and scope checks and before any write.
  A denial commits its own audit row, so nothing else may be pending in the session at that point.
- The matrix of record is `RBAC_MATRIX.md` (numbered §2.x, currently at 2.41). Each new telecaller route needs a row in the
  tel-026 route-inventory test (`test_tel_026_*`).

## 12. Next.js routing — `apps/web/app` (App Router, Next 15, React 19, 218 `page.tsx` files)
- **Public:** `/`, `contact`, `faq`, `gallery`, `news`, `search`, plus `robots.ts` and `sitemap.ts`.
- **Portals:**
  - `/it/{student,trainer,placement,hr,admin,counselor}`
  - `/overseas/{student,counselor,university,agent,admin}`
  - `/admin/*`, which includes the BDM and telecaller manager surfaces
  - `/school/{coordinator,principal,teacher,parent,academic-team,career-counselor,psychometric-team,invite}`
  - `/bdm/*` (with a `sign-in` chooser)
  - `/telecaller/*` (with a `sign-in` chooser)
  - `/account`
- **`middleware.ts`:** this is only a cookie-presence check, matched on `/it`, `/overseas`, `/admin`, `/bdm` and `/telecaller`.
  It redirects to the matching login with `next=` (path plus query). **`/school/*` and `/account` are not covered.** They
  rely on `serverApi` throwing → `accessUnavailable()`. The backend is always the real gate.
- **Route handlers:** `app/api/[...path]/route.ts` is a transparent proxy to `${BACKEND_INTERNAL_URL}/api/*` that forwards
  every header and cookie. `app/local-files/[...path]` serves local files.

## 13. Server and client components
- **Pages are async server components.** They `await serverApi('/auth/me')` and the page data (in parallel), catch into
  `accessUnavailable()`, and render `PortalShell` with the nav from `lib/navigation.ts`, `lib/bdmNav.ts` or
  `lib/telecallerNav.ts`.
- **Panels are client components** (293 of 389 components are `"use client"`). They take the initial data as props, mutate
  through `/api/v1/...` via `sendJson`, then call `router.refresh()` or update local state.
- **Server-only splits:** helpers that call `serverApi` live in `lib/*Server.ts` (for example `bdmLeadsServer.ts`), so the
  client components that import `lib/bdmLeads.ts` never pull in `next/headers`.

## 14. Shared frontend components (reuse these)
- **Shells and navigation:** `PortalShell`, `PublicShell`, `PortalMobileNav`, `NavGroup`, `DesktopNav`/`MobileNavToggle`,
  `RefreshOnHistoryNav`.
- **Feedback:** `AccessUnavailable`/`accessUnavailable()`, `SectionUnavailable`, `LoadFailureAlert`, `FormMessage`,
  `TravelUnavailable`.
- **Tables:** `DataTable`, plus the per-module tables `TelecallerLeadTable`, `BdmTeamTable`, `AgentReportTable`,
  `AgentTableRegion`.
- **Confirmation:** `BdmConfirm` (inline confirmation pattern) and `TierDowngradeConfirm`.
- **Legacy generic actions:** `WorkflowPanel` (`ActionSpec`-driven, used by IT and Overseas).
- **School:** the `Student360*` family and the analytics boards.

## 15. API client layer — `apps/web/lib` (about 100 modules, one per feature)
- `api.ts` has two fetchers:
  - `serverApi<T>()` is server-only. It forwards `cookies()`, uses `no-store` and throws `ApiError(detail, status)`.
  - `publicApi<T>()` revalidates every 60 s.
- `apiErrors.ts` provides:
  - `sendJson()`, which never throws and returns `{ok, …}`
  - `detailMessage()`, which handles a string or the FastAPI 422 list
  - `Page<T>`/`isPage`
  - `NOT_COMPLETED`
- **Per-feature modules:** `lib/<feature>.ts` holds the URL builders, types, labels and client calls, for example
  `telecallerCalls.ts`, `bdmPipeline.ts` and `agentApplications.ts`. Types are hand-written copies of the backend dicts, and
  nothing is generated from OpenAPI.
- **Utilities:**
  - `idempotencyKey.ts` creates an `Idempotency-Key` UUID that also works on non-secure origins. The backend honours this
    header only in payments, agent deposits, school bulk and onboarding, telecaller import, and account.
  - `safeNext.ts` validates the `next` redirect.
  - `formatDate.ts` and `useNowIstMin.ts` handle dates and IST.

## 16. Forms and validation
- Forms are plain controlled React forms, with **no form or schema library** (no zod or react-hook-form). Client checks are
  light, and the server's 422/409/403 `detail` is the source of truth, shown through `FormMessage`.
- Focus goes through `lib/focus.ts` and `useFocusAfterRender`. `useLeaveGuard` protects unsaved edits. On a network failure
  the entry is kept and `NOT_COMPLETED` is shown.

## 17. Design system
- `app/globals.css` defines tokens on `:root`: `--blue`, `--navy`, `--ink`, `--muted`, `--line`, `--soft`, `--white`,
  `--green`/`--amber`/`--red`, `--radius` and `--shadow`. It also provides utility classes (`.container`, `.section`,
  `.card`, `.grid.two/three/four`, `.eyebrow`, `.lead`, `.muted`).
- `app/controls.css` styles the form controls. Two components use CSS modules.
- There is **no Tailwind, no component library and no dark mode**. The UX reference is in `docs/ux/` (`SCR-*` screen
  catalog, `ROLE_NAVIGATION.md`).

## 18. State management
- **There is no global store** (no SWR, react-query or zustand). The server is the source of truth, RSC fetches on every
  request, and panels hold local `useState`.
- The only context is `TripLiveContext` (`lib/tripLive.ts`, for BDM travel).
- **List state lives in the URL:** `useUrlList` keeps the filter and offset in the query string, so a refresh keeps the place
  and Back works.
- Cross-panel sync uses `router.refresh()`, `RefreshOnHistoryNav` and `lib/usersChanged.ts`.

## 19. Background jobs — `app/worker.py`
- Celery uses Redis as both broker and backend, with a UTC clock. The tasks are:
  - `heartbeat_task`
  - `sync_enquiry_to_crm_task` (retry with backoff, 5 retries)
  - `deliver_notification_task` and `deliver_lead_email_task`
  - sweepers and reminders, listed under the beat schedule below
- **The beat schedule exists now:**

  | Job | Interval |
  |---|---|
  | `enh014-sweep-stale-deliveries` | 5 min |
  | `agn017-daily-reminders` | 02:30 UTC (08:00 IST) |
  | `bdm012-reminders` | 5 min |
  | `tel018-conversion-sweep` | 15 min |
  | `tel014-sweep-stale-lead-emails` | 5 min |
  | `tel020-alerts` | 15 min |

- **Outbox pattern:** `notifications.dispatch.queue_deliveries` writes `queued` `NotificationDelivery` rows inside the business
  transaction. A SQLAlchemy `after_commit` listener publishes them to Celery, so a rollback sends nothing. A task gets a fresh
  event loop each time and disposes the engine pool at the end (tel-014 QA-01).
- `FastAPI.BackgroundTasks` is not used anywhere.

## 20. Redis and caching
- Redis serves only as the Celery broker and backend, and as the readiness probe. There is **no application cache, no
  session store and no rate limiting**.
- On the Next.js side, `serverApi` uses `no-store` and `publicApi` revalidates every 60 s.

## 21. External integrations (all optional and config-gated; unset means `not_configured`, never a crash)
| Integration | Where |
|---|---|
| SMTP email | `services/mailer.py` (run in `asyncio.to_thread`), `notifications/lead_email.py` |
| Twilio WhatsApp/SMS | `notifications/twilio.py`; the generic webhooks are the fallback (`services/integrations.py`) |
| CRM webhook | `worker.sync_enquiry_to_crm_task` |
| Razorpay | `services/payment.py`, `api/payments.py`, `api/agent_deposits.py` (HMAC verification, `PaymentWebhookEvent`) |
| Google Meet / Zoho Meeting | `services/meetings.py` (OAuth refresh-token flow) |
| S3 / local files | `services/storage.py` (15-minute presigned URLs, SSE; local fallback with a path-traversal guard) |
| Inbound email | `api/inbound.py` (shared-secret webhook) |
- Provider selection is still decision-gated (`CLAUDE.md` → Technology).

## 22. Logging and error handling
- Logs are structured JSON on stdout, and every line carries `request_id`. Keys such as password, token and secret are
  redacted. Domain events are logged as `logger.info("<event>", extra={"extra_fields": {...ids only...}})`, after the
  commit.
- Errors are raised as `HTTPException(status, "Human sentence")`, and the UI shows `detail` as written. Messages are module
  constants (for example `LEAD_NOT_FOUND`, `REPORTS_REFUSED`). **There is no global exception handler and no error-code
  envelope.**
- **Audit:** `AuditLog(user_id, action, entity_type, entity_id, metadata_json)` is written at 169 sites. It goes into the same
  transaction, and the metadata holds ids and reason tokens only, never PII. The action names are dotted, for example
  `lead_call.delete`.

## 23. Tests
- **API:** 491 `tests/test_*.py` files, named by feature (for example `test_tel_010_*`), plus 56 `*_helpers.py` builders
  (`mk_*`, `make_*`, `login()`, `client_for()`). They use pytest-asyncio and `httpx.ASGITransport` against a **real
  PostgreSQL**, and run in docker (`api-test`, CI profile; see the memory note on mount paths in worktrees). Some suites assert
  a fixed query count.
- **Web:** 343 Vitest and Testing Library tests, and 182 Playwright E2E specs. A separate `playwright.docs.config.ts` captures
  user-guide screenshots.
- **CI:** `.github/workflows/ci.yml` runs `scripts/ci-local.ps1` (ruff, mypy, pytest, tsc, eslint, vitest, Playwright) through
  `docker-compose.ci.yml`.
- **Cadence:** each feature runs the *lite* backend set (its own tests and the touched regression tests). The user runs the
  full suite every 4–5 stories.

## 24. Docker
- `docker-compose.yml` defines these services:
  - `postgres:16-alpine`
  - `redis:7-alpine` (AOF)
  - `api` (`alembic upgrade head && uvicorn`)
  - `worker`
  - `beat`
  - `web` (standalone build)

  The volumes hold Postgres, Redis and `uploads`.
- `docker-compose.override.yml` adds Caddy for TLS, with ports bound to 127.0.0.1. `docker-compose.ci.yml` adds the
  `api-test` and `web-test` services under the `ci` profile.
- **The user runs compose.** Sessions do not start or stop the stack.

## 25. Deployment
- The as-built deployment is a single host running Docker Compose behind Caddy, for example `dev.edusphere.org.uk`. The cloud
  target in `DEPLOYMENT.md` and `SCALING.md` (ECS Fargate) is **not confirmed**: it is gated by `DEC-TECH-001`, `DEC-ARCH-001`
  and `DEC-INFRA-001`. Add no provider-specific infrastructure.

## 26. Security-sensitive areas (review these when you touch them)
- **Tokens:** `core/security.py`, the default `secret_key="change-me"`, the cookie flags, `session_version` revocation, and the
  reset, invite and welcome tokens.
- **Authorization:**
  - `deps.py` and `rbac.py`
  - every `scope()` and `_scoped_*` helper
  - the agency gates (`agent_denial_reason`, staff flags)
  - the parent-link logic (cross-school links are allowed by design)
  - `require_school_entitlement`
- **Proxy:** `app/api/[...path]/route.ts` forwards all headers and cookies.
- **Files:** the upload path (`files.py`, `storage.py`, the `/local-files` mount, the MIME allowlist, the 20 MB cap) and the
  CSV imports (`school_bulk`, `school_onboarding_bulk`, `telecaller_import`). For CSV exports, the injection guard is
  `school_bulk._safe_cell`, which `agent_reports` and `workflows` reuse.
- **Webhooks and payments:** Razorpay signature checks and webhook handling, and the inbound email secret.
- **Data exports:** the GDPR export and delete path (`DataSubjectRequest`), the audit export, and the report and CSV exports.

## 27. Performance-sensitive areas
- **Dashboards and metrics:**
  - `services/portal.py`
  - `schools._school_dashboard_payload` and `school_analytics`, which have fixed-query-count tests
  - `telecaller_metrics.py`, the shared source for the TEL dashboard, reports and performance
  - `bdm_metrics` and `bdm_performance`
  - the agent dashboards and reports
- **Request-path cost:** many legacy list endpoints are still unpaginated. Every request runs `get_current_user`'s eager loads.
- **Lock contention:** bulk imports (row-by-row validation) and lock-heavy writes (promotion, transfers, lead stage moves).
- **Scheduled jobs:** the beat sweepers (5–15 min) scan the delivery, reminder and lead tables, so keep them indexed and
  bounded.

## 28. Tight coupling (change carefully)
- **Shared hubs:** `models.py` (143 classes), `schemas.py` (509 classes) and the large legacy routers.
- **`Enquiry`** is the shared lead entity across public intake, BDM, telecaller and counselor handover. Stage rules live in
  `lead_stages.py` and `services/lead_pipeline.apply_event`.
- **The `User` model** combines the legacy `role`/`division`/`profile.school_id` fields with `UserRoleAssignment`.
- **Navigation** in `lib/navigation.ts`, `bdmNav` and `telecallerNav` must match the backend portal sections and routes.
- **Cross-router imports** are listed in §4. `bdm.LIMIT/OFFSET` acts as the de-facto shared pagination constant.

## 29. Conventions to follow
- **Traceability:** code and tests cite Feature, AC and Decision IDs, for example `tel-010 (DEC-SCOPE-096, spec §4)` and
  `CL4`. Specs and plans go in `docs/superpowers/{specs,plans}`, and QA evidence goes in `docs/quality`. Each feature updates
  `API_CONTRACT.md` (its §12x section), `RBAC_MATRIX.md` (§2.x) and the decision register.
- **Write order:** auth dependency → `scope(user)` (403 for the role, 404 when out of scope) → lock (`locked_*`,
  `with_for_update`) → role and ownership `require_*` → validate → mutate → `audit()` in the same transaction → **one commit
  in the router** → `log()` → enqueue notifications through the outbox.
- **Status codes:** 403 for a role, tier or permission denial, 404 out of scope, 409 for a conflict or precondition failure,
  422 for validation (field-located). Error text is a human sentence, defined as a module constant.
- **Lists:** `limit: int = LIMIT, offset: int = OFFSET` returning `{items, total, limit, offset}`, with filters mirrored in
  the URL on the web side.
- **Time:** use `db_now(db)` and IST dates for business days.
- **Integrations:** optional integrations return a status and never raise into the request.
- **Web:** use `serverApi` in pages and `sendJson` in panels. Put server-only helpers in `*Server.ts`. Copy the feature's
  types into `lib/<feature>.ts`.
- **Style:** ruff line length is 200 and mypy is lenient.

## 30. Reusable modules for new enhancements
| Need | Use |
|---|---|
| Current user | `deps.get_current_user` (eager-loads assignments and agency membership) |
| Role and scope gates | Legacy: `workflows._require`, `admin.ensure_admin`. School: `schools._own_school_id`, `_require_coordinator`, `_scoped_students_query`, `school_feedback._require_school_reader`. Agent: `agent_students._gate`, `rbac.agent_may`/`is_agent_staff`. BDM/TEL: `services/bdm*.scope`/`require_manager`, `lead_pipeline.scope`, `telecaller_leads.require_writable` |
| Lead pipeline | `services/lead_pipeline.{scope, locked_lead, apply_event, stage_out}`, `lead_stages.py` |
| Tier gate | `schools.require_school_entitlement` (with `TIER_SERVICES`) |
| Pagination and search | `api.bdm.{LIMIT, OFFSET, SEARCH, _matching}`, `lookups._pattern` (LIKE escaping); web: `useUrlList`, `Page<T>` |
| Time | `services.bdm_appointments.{db_now, today_ist}`, web `useNowIstMin`, `formatDate` |
| Audit and logs | The service `audit()`/`log()` pattern (`services/lead_calls.py`), `core.logging.get_logger` with `extra_fields` |
| Notifications | `notifications.dispatch.queue_deliveries` (outbox), `services.mailer`, `services/agent_notifications` |
| Async or scheduled work | A `worker.celery` task, plus a `beat_schedule` entry if it repeats |
| Metrics and dashboards | `services/telecaller_metrics.py`, `bdm_metrics`, `school_analytics.*` (batched, fixed query count) |
| Accounts | `services.provisioning` (welcome and set-password link; admins never set passwords) |
| Files and PDFs | `services.storage.storage`, `reporting/pdf.py`, `services.certificates`, `billing_documents` |
| Conflicts and idempotency | `schools._flush_or_409`; the `Idempotency-Key` header as handled in `school_bulk`/`payments`, web `newIdempotencyKey()` |
| Web data and errors | `lib/api.serverApi`, `ApiError`, `lib/apiErrors.{sendJson, detailMessage, Page}` |
| Web UI | `PortalShell`, `accessUnavailable`, `SectionUnavailable`, `FormMessage`, `DataTable`, `BdmConfirm`, `useLeaveGuard`, `lib/focus` |

## Known gaps (observations only; each needs a Decision ID or `NEEDS_CONFIRMATION` before anyone acts on it)
1. There is no CSRF token, and no rate limiting beyond the change-password lockout and the feature daily caps.
2. `auto_create_schema=True` is the default, and `secret_key` defaults to `"change-me"`.
3. There are two RBAC mechanisms. The `require_*` dependencies are unused, and inline `User.role` checks are the standard
   (owner decision).
4. There is no repository layer. Services exist only for AGN, BDM and TEL. Four services import from `app.api`, and routers
   share private helpers.
5. Many legacy list endpoints are unpaginated. There is no global error envelope and no generated API types.
6. `middleware.ts` does not cover `/school` or `/account`. The backend still enforces access there.
7. The `schools` ↔ `school_analytics` cycle is held together by function-local imports.
8. `db_now` is duplicated in three services.
