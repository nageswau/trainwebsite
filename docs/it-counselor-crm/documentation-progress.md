# IT Counselor CRM Documentation — Progress

| Session | Status | Commit | Notes |
|---|---|---|---|
| S1 Analysis and plan | DONE 2026-11-18 | (this commit) | 62 Doc IDs in 13 modules; findings P1–P6 |
| S2 Stack and tooling | DONE 2026-11-18 | (this commit) | `itcdocs` up at `6b61546c`, seeded, migrations at `0319`. `shoot.ts` `ITC_ROOT`. Spec `itc-s2-admin-setup` (2 tests): Docs IT Counselor A/B, Docs IT Telecaller (DOCS-ITC-TEL-1, manager Lakshmi), programme **Docs Full Stack Python** (INR 45000, 12 weeks), batch **Docs FSP Batch 1** (+7 to +91 days, Online). Snapshots `after-seed`, `after-s2` (scratchpad). 9 PNGs. ADM-001 done; ADM-002 edit + re-send done (deactivate in S10). |
| S3–S12 | not started | | |

## Owner decisions
- Approach: full verified set (same pipeline as `docs/counselor-crm/`).
- I1 Admin scope: counselor-related IT Admin / Super Admin screens only.
- I2 Time states: SQL back-dating on `itcdocs` only, jobs run by `celery call`.
- I3 Payments (revised): make no payments at all; screenshot payment screens only, forms unsubmitted; Razorpay in text only.
- Stack: `itcdocs` only, web 3060, api 8060, Mailpit 127.0.0.1:8032.

## Feature status
| Doc ID | Status |
|---|---|
| DOC-ITC-ADM-001 | DONE (S2) |
| DOC-ITC-ADM-002 | PARTIAL: edit + re-send (S2); deactivate/reactivate in S10 |
| all others | not started |

## Discovered functionality
- Super Admin `/admin/users` Division list: Select, it, overseas, global; starts on **it** (so a counselor created there is IT by default).
- The **Manage users** / **Directory** card is half-width and its table scrolls sideways; names and emails are cut off at 1440 px (documented as built).
