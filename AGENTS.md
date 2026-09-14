# AGENTS.md

## Scope

These instructions apply to the entire repository. More specific `AGENTS.md` files, when present outside vendored skill content, override this file for their subtree.

EduSphere is an implementation-in-progress, not an empty scaffold. Inspect the current code, tests, decision records, and working tree before changing anything. Do not restart the historical bootstrap workflow or assume that an older handoff status is still current.

## Read before working

Read only the material relevant to the task, but establish the governing context first:

1. `CLAUDE.md` - project constitution, evidence rules, approval gates, and completion criteria.
2. `pending.md` - volatile session handoff, current queue, known test-infrastructure issues, and established conventions. Verify its claims against the current tree because it is a handoff log, not immutable truth.
3. `docs/decisions/PRODUCT_DECISION_REGISTER.md` and `docs/decisions/APPROVAL_GATES.md` - approved, rejected, proposed, and blocked decisions.
4. The relevant approved contracts:
   - product: `docs/product/PRD.md`
   - features and acceptance criteria: `docs/features/MASTER_FEATURE_CATALOG.md`, `docs/features/feature_catalog.json`, and `docs/features/FEATURE_ACCEPTANCE_CRITERIA.md`
   - API/data/security: `docs/architecture/API_CONTRACT.md`, `DATA_MODEL.md`, `RBAC_MATRIX.md`, `INTEGRATION_CONTRACTS.md`, and `THREAT_MODEL.md`
   - UI: `docs/ux/SCREEN_CATALOG.md`, `RESPONSIVE_RULES.md`, and `ACCESSIBILITY_RULES.md`
   - delivery evidence: `docs/quality/RTM.md` and `docs/delivery/RAID.md`

Treat `prompts/` as the recorded project workflow. For an approved feature implementation, follow the checks in `prompts/13_FEATURE_LOOP.md`; do not rerun earlier project-generation prompts unless the user requests it.

## Sources of truth and traceability

- Never infer approval from a recommendation, draft, test, prior AI output, or the presence of partial code. Respect the statuses in the decision register and feature catalogue.
- Preserve the traceability chain: evidence -> decision -> PRD requirement -> Feature ID -> acceptance criteria -> UX/contracts -> tests -> code -> release evidence.
- Before implementing a feature, identify its Feature ID, acceptance criteria, dependencies, RBAC/resource scope, DB/API/UI impact, tests, and blockers. First inspect what is already implemented; many tasks are narrow gaps rather than greenfield builds.
- When documents and implementation disagree, do not silently pick whichever is convenient. Determine whether the implementation is stale, the document is stale, or the requirement remains open, and record the discrepancy in the appropriate decision/open-item/RAID document.
- Do not invent behavior for blocked or unconfirmed scope. Use `NEEDS_CONFIRMATION` where evidence is insufficient.
- `docs/sources/` contains confidential source evidence. It is immutable: do not edit, rename, normalize, commit, or use it as an output directory.

## Repository map

- `apps/api/`: Python 3.12, FastAPI, Pydantic v2, async SQLAlchemy, Alembic, PostgreSQL, Redis, Celery, and pytest.
  - `app/main.py`: application assembly and router registration.
  - `app/api/`: `/api/v1` route modules.
  - `app/models.py` and `app/schemas.py`: current shared ORM and Pydantic definitions.
  - `app/services/`: business and provider services; `portal.py` supplies many role portal views.
  - `app/core/`: configuration, database, identifiers, auth, RBAC, logging, and middleware.
  - `alembic/versions/`: append-only schema history.
  - `tests/`: API/service tests that currently use the configured PostgreSQL database.
- `apps/web/`: Next.js 15 App Router, React 19, strict TypeScript, CSS, Vitest, and Playwright.
  - `app/`: routes, layouts, API proxy, and local-file proxy.
  - `components/`: shared public and role-portal UI.
  - `lib/api.ts`: server-side API access; browser requests normally use the same-origin `/api/v1` proxy.
  - `tests/e2e/`: browser tests against a running, seeded stack.
- `docker-compose.yml`: PostgreSQL, Redis, API, Celery worker/beat, and web services.
- `docker-compose.override.yml` and `Caddyfile`: optional Caddy/TLS deployment overlay.
- `docs/`: approved requirements/contracts plus live delivery and quality records.
- `scripts/`: PowerShell preflight, compact test runner, source-manifest, skill setup, and deployment helpers.

Do not perform a broad architectural reorganization just because domain package placeholders exist. The current application is a domain-oriented modular monolith with several intentionally shared files; refactor only when the task requires it and tests cover the affected surface.

## Working-tree and secret safety

- Assume the worktree is dirty. Start with `git status --short` and inspect relevant diffs. Preserve all user changes, including staged and untracked files; never reset, clean, or overwrite unrelated work.
- Treat `.env` as secret local state. Do not print it, quote its values, commit it, copy it into artifacts, or replace it. Use `.env.example` for documented variable names and safe placeholders. Inspect only the minimum secret presence needed for an explicitly in-scope integration task.
- Never add real credentials, tokens, personal data, or provider payloads to source, fixtures, screenshots, logs, or documentation.
- Do not fake successful provider behavior. Credential-blocked features remain blocked until real, authorized test credentials and a safe validation path exist.
- Avoid destructive database/volume operations unless the user explicitly authorizes them. The shared dev database may contain user data or useful test state.

## Backend conventions

- Keep handlers and services async. Use `AsyncSession`, SQLAlchemy 2-style `select()`, and explicit `await` calls.
- Reuse dependencies from `app/api/deps.py`. Protected actions must enforce authentication, role/division, permission, and resource ownership on the API; hiding a control in the UI is never authorization.
- Follow deny-by-default RBAC and IDOR protections in `RBAC_MATRIX.md`. Derive actor scope from the authenticated user rather than trusting client-supplied `user_id`, `agent_id`, `university_id`, or similar filters.
- Keep request/response models in `app/schemas.py` unless a scoped refactor is justified. Preserve `/api/v1` contracts and register every new router in `app/main.py`.
- Use UUID identifiers and the existing identifier helpers where applicable. Preserve existing error semantics and status codes; do not change product behavior merely to satisfy a stale test.
- Privileged writes require an `AuditLog` entry in the same transaction when the RBAC/security contract calls for one. If the audit write fails, the privileged action must fail closed.
- For financial or other duplicate-sensitive creation, honor the contract's idempotency rules. Never weaken webhook signature verification or expose development-only secrets in production.
- Every schema change needs a new Alembic revision. Do not edit or reorder an applied migration. Review upgrade/downgrade behavior and keep model definitions aligned with the migration.
- Docker starts the API with `alembic upgrade head`; do not rely on `AUTO_CREATE_SCHEMA` as a substitute for migration coverage.
- Keep Ruff/MyPy settings from `apps/api/pyproject.toml`; do not broaden ignores to hide new issues.

## Frontend conventions

- Use App Router and Server Components by default. Add `"use client"` only for state, effects, browser APIs, or event handlers.
- Keep TypeScript strict. Reuse `@/*` imports, existing shells, panels, `DataTable`, `CollectionExplorer`, form controls, and CSS tokens before introducing new abstractions or dependencies.
- Server-rendered authenticated data should use `serverApi`; cacheable public data should use `publicApi` where its 60-second revalidation is acceptable. Browser mutations should use same-origin `/api/v1/...` so cookies and proxy behavior remain consistent.
- Preserve HttpOnly-cookie authentication. Do not place auth tokens in client JavaScript, local storage, URLs, or logs.
- Keep local download links compatible with `app/local-files/[...path]/route.ts`; object-storage mode may return an absolute signed URL.
- Meet the documented responsive and accessibility rules. Use semantic controls, associated labels, keyboard operation, visible focus, meaningful empty/error states, and no body-level horizontal overflow.
- If adding a dedicated panel to `WorkflowPanel.tsx`, update both its render branch and the top-level `show*` early-return guard, then exercise the section in a browser.
- Independent client panels do not automatically share refreshed state. Explicitly refresh/refetch when the product flow requires it; account for this in E2E tests.

## Running the project

From the repository root on Windows/PowerShell:

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose exec api python -m app.seed
docker compose ps
```

The seed is designed to be idempotent, but it prints a development demo password; do not paste that output into reports or chat.

The compose services have no source bind mounts. After changing API code or backend tests, rebuild/recreate `api`; recreate `worker` and `beat` too when their imported backend code is affected. After changing web code or E2E specs, rebuild/recreate `web` before container-backed verification.

Examples:

```powershell
docker compose build api
docker compose up -d --force-recreate api worker beat

docker compose build web
docker compose up -d --force-recreate web
```

## Validation

Use the smallest meaningful test set first, then escalate by blast radius:

1. changed unit or API test file;
2. module tests sharing the changed path;
3. impacted integration and UI/E2E specs;
4. full regression only for a cross-cutting change or merge/release gate.

Backend examples:

```powershell
docker compose exec api python -m pytest -q tests/test_health.py
docker compose exec api python -m pytest -q tests/test_<feature>.py
```

Local backend quality checks, using the project virtual environment with `requirements-dev.txt` installed:

```powershell
cd apps/api
python -m ruff check .
python -m mypy app
python -m pytest -q tests/test_<feature>.py
```

Frontend checks:

```powershell
cd apps/web
npm test
npm run typecheck
npm run lint
npm run build
npx playwright test tests/e2e/<feature>.spec.ts --workers=1
```

For combined compact runs, `scripts/test-summary.ps1` can run backend pytest and an optional npm script.

### Test caveats

- Backend tests are not transaction-isolated: they use the configured shared PostgreSQL database and leave rows behind. Do not casually run the full suite, and do not interpret accumulated test data as product data.
- At least one provider integration test may call a real external sandbox API when credentials exist. Do not run live-provider tests unless that integration is in scope and the call is authorized.
- E2E tests also mutate shared seeded state. Create unique timestamp/UUID-suffixed records, act on records created by the test, and never mutate a shared seeded record whose state another spec assumes.
- `DataTable` and `CollectionExplorer` paginate client-side. Filter/search for a newly created unique value before asserting it is visible.
- Parallel Playwright runs can hit known shared-DB contention. Re-run a suspicious failure alone with `--workers=1` before classifying it as a regression.
- A first public-page E2E run after rebuilding web can see stale/warming fetch cache. Re-run the targeted spec once before diagnosing a product defect.
- Check current details in the "Known test-infrastructure issues" section of `pending.md` and corresponding entries in `docs/delivery/RAID.md`; do not hard-code old pass counts into new reports.

## Documentation and completion

- Add or update tests with the implementation. For defects, first reproduce the failure or document concrete code-path evidence.
- Update `docs/quality/RTM.md`, the feature catalogue/status, and relevant RAID/open-item records when a feature's implementation or evidence status materially changes. Keep Markdown and JSON catalogues consistent.
- Record exact tests run and honest outcomes. Distinguish targeted verification from a full regression, and distinguish existing failures/flakes from new regressions with evidence.
- A feature is complete only when its applicable acceptance, security, RBAC/resource-scope, migration, API, UI, responsive, accessibility, automated-test, and documentation gates pass.
- Do not claim deployment, provider delivery, backups, notifications, payments, or integrations work unless they were verified against the real configured system at the appropriate safe test level.

## Handoff expectations

At the end of a change, report:

- what changed and why;
- files or product areas affected;
- migrations or configuration implications;
- validation commands and results;
- untested surfaces, known failures, blockers, or decisions still needed.

Keep the handoff concise and evidence-based. Never include secret values.
