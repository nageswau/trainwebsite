# IT Counselor CRM Documentation — Progress

| Session | Status | Commit | Notes |
|---|---|---|---|
| S1 Analysis and plan | DONE 2026-11-18 | (this commit) | 62 Doc IDs in 13 modules; findings P1–P6 |
| S2 Stack and tooling | not started | | Docker Desktop running; `itcdocs` `.env` + `docker-compose.docs.yml` prepared (untracked) |
| S3–S12 | not started | | |

## Owner decisions
- Approach: full verified set (same pipeline as `docs/counselor-crm/`).
- I1 Admin scope: counselor-related IT Admin / Super Admin screens only.
- I2 Time states: SQL back-dating on `itcdocs` only, jobs run by `celery call`.
- I3 Payments: manual IT Admin entries only; Razorpay in text only.
- Stack: `itcdocs` only, web 3060, api 8060, Mailpit 127.0.0.1:8032.

## Feature status
All 62 Doc IDs: **not started**.

## Discovered functionality
(none yet)
