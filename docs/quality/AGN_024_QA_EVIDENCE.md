# AGN-024 — Agent signup KYC documents: verification evidence (2026-10-17)

Branch `feature/agn-024`; decision `DEC-SCOPE-224` (K1–K11); migration `0164_agent_org_kyc`; API §12EK; RBAC §2.147.
Lite runs only. The full backend suite is the owner's, on their own cadence. Stack: compose project `agn024` (web :3024, api :8024).

## Before the final-review fixes (controller run, 2026-10-17)

| Check | Result |
|---|---|
| Backend lite set (15 files: `test_agn_024_*`, `test_agn_001_registration_and_gate`, `test_agt_001_registration_approval`, `test_sec_001_audit_trail`, `test_role_assignments` and neighbours) | **194 passed** |
| `ruff check` (touched files) | clean |
| Web vitest (full) | **5182 / 5184** passed. The 2 failures are pre-existing and unrelated: the RecruiterCompanies archive test and `dateZoneSweep`. Neither flags an AGN-024 file. |
| `tsc --noEmit` | clean |
| eslint | 0 errors |
| Playwright `agn-024-agent-kyc.spec.ts` + `agt-001-registration-approval.spec.ts`, re-run 2026-10-17 after the K11 throttle fix (harness sends a unique `X-Forwarded-For` per agent signup, `e2eIpHeaders()`), twice back to back | **5 / 5** passed each run (no 429 on rerun) |
| Playwright, all 16 spec files that register agents (agn-001, 002, 003, 004, 007, 008, 014, 016-022, dtu-001, agt-002), one `--workers=1` run, 2026-10-17 | **33 / 33** passed |
| `tsc --noEmit` / eslint `tests/e2e` (same container) | clean / 0 errors (3 pre-existing warnings) |

## After the final-review fixes (I1 content type, K11 throttle, T2 rejection body, K9 hint)

| Check | Command (abridged) | Result |
|---|---|---|
| Backend lite set (19 files) | `api-test`: `alembic upgrade head && pytest -q tests/test_agn_024_*.py tests/test_agn_001_*.py tests/test_agt_001_registration_approval.py tests/test_sec_001_audit_trail.py tests/test_role_assignments.py tests/test_bdm_019_admin.py tests/test_enh_031_lookups_students.py` | **259 passed**, 0 failed (335 s) |
| New file `test_agn_024_signup_guards.py` | (in the run above) | 11 passed: `text/plain` JSON → 415 and no user; missing content type → 415; JSON student 201 (with and without `charset`); 5 agent signups from `X-Forwarded-For: 203.0.113.7` → 201, 6th → 429 with `0 < Retry-After ≤ 3600` and no file written, another IP → 201, student from the same IP → 201, rows older than an hour no longer count; student audit rows carry no `ip`; `client_ip` parsing (6 cases) |
| `ruff check` | `app/api/auth.py app/core/client_ip.py app/services/agent_kyc.py` + touched tests | All checks passed |
| Web vitest | `tests/components/RegisterForm.test.tsx tests/lib/agentKyc.test.ts` | 2 files, **9 / 9** passed |
| `tsc --noEmit` | web-test | clean |
| eslint | `lib/agentKyc.ts tests/components/RegisterForm.test.tsx` | clean |
| Live probe through the web proxy (`http://localhost:3024`) | `POST /api/v1/auth/register` with `Content-Type: text/plain` carrying a JSON student body | **415** "Unsupported content type"; no account |

## Empirical client-IP header check (K11)

A temporary `print` of `request.headers` in `register` (removed afterwards; the api container was rebuilt again without it) showed what the
API receives through the Next.js proxy:

- No client header: `x-forwarded-for: 172.18.0.1` (Next adds the socket peer, the Docker gateway here), plus `x-forwarded-host`,
  `x-forwarded-port`, `x-forwarded-proto`; `request.client` = `172.18.0.7` (the web container).
- Client sends `X-Forwarded-For: 198.51.100.9`: the API receives `x-forwarded-for: 198.51.100.9` unchanged (Next does not append).

So the leftmost `X-Forwarded-For` entry is the right key behind Caddy, which replaces a client-sent value with the real address by
default. Without Caddy (local dev) the header can be chosen by the caller.

## Not run

- The full backend suite (owner).
- Full web vitest and the rest of the Playwright suite (owner). The agent-registering e2e specs are fixed for the K11 429 (harness sends a
  unique `X-Forwarded-For`); `tests/doc-capture/*` is untouched (recorded follow-up).
