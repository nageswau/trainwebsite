# Continuous Integration

## Purpose

`.github/workflows/ci.yml` runs the repository's quality gates in this order:

1. Python formatting (`ruff format --check`) and frontend lint.
2. Ruff lint.
3. MyPy.
4. Frontend TypeScript checking.
5. Frontend Vitest unit tests (jsdom, not browser mode).
6. Alembic upgrade and model/migration drift smoke check.
7. Targeted, provider-safe FastAPI tests.
8. Headless Playwright tests with one worker.

The same implementation is used locally and in GitHub Actions:

```powershell
.\scripts\ci-local.ps1
```

The script does not use the interactive browser or the development database. It creates a uniquely named Compose project with disposable PostgreSQL/Redis volumes, overrides every external-provider credential with an empty value, and removes only those CI-owned resources when the run ends.

## Test selection

The targeted API gate covers health, RBAC, role assignments, the programme catalogue, and route/UUID contracts. It deliberately does not run `test_zoho_meeting_integration.py` or the live Razorpay cases.

The Playwright gate runs headlessly with `--workers=1`. A CI-only loopback proxy forwards `http://localhost:3000` to the Compose web service so secure-context browser APIs behave exactly as they do in normal localhost development, without weakening Chromium. Tests tagged `@external` are excluded from routine CI; they belong in an explicitly authorized provider-validation workflow. At present this excludes the test that opens the real Razorpay TEST checkout.

## Evidence policy

Every stage writes a command log and the run writes `summary.json` plus `summary.md` under `artifacts/ci/<run-id>/`.

- **Passed runs:** retain compact summaries and JUnit XML from Vitest, pytest, and Playwright.
- **Failed runs:** additionally retain command logs, API/web container status and logs, Playwright screenshots, videos, traces, and the HTML report.

The entire `artifacts/` directory is gitignored. GitHub retains uploaded evidence for 14 days.

Playwright's trace includes page errors, console output, network activity, DOM snapshots, and action history. This provides more useful failure evidence than saving screenshots for every successful test.

## Safety

- The developer `.env` file is never read by the runner itself and is never copied to artifacts.
- The CI Compose override replaces provider credentials even if a local `.env` exists.
- Seed output is filtered so the development demo password is not stored in logs.
- The isolated database is recreated before Playwright so API-test records cannot affect UI tests.
- The normal developer Compose project and its volumes are not stopped, reset, or modified.

## Initial local baseline (2026-09-10)

The first complete isolated run is recorded at `artifacts/ci/20260910-234326-18560/summary.md`. The CI implementation completed all stages; the overall result is red because it surfaced existing repository debt:

| Gate | Result |
|---|---|
| Frontend ESLint | Pass with 31 warnings |
| Ruff format | Fail: 35 files require formatting |
| Ruff lint | Fail: 20 findings |
| MyPy | Fail: 134 errors across 9 files |
| Frontend typecheck | Pass |
| Vitest | Pass: 2/2 |
| Alembic upgrade + drift check | Pass: all 22 migrations, no drift |
| Targeted API | Pass: 26/26 |
| Headless Playwright | Fail: 197/207 passed; 10 failures captured |

The Playwright failures cluster around shared mutable seed assumptions: exhausted batch availability, repeated data-subject requests, and a seeded overseas student exhausting the finite university choices. This is now reproducible against an otherwise disposable database and should be fixed by making those tests create and clean up their own data or by resetting state between stateful groups. One live-provider Razorpay test is intentionally excluded via `@external`.
