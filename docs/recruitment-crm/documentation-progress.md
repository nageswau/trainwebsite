# Recruitment CRM Documentation — Progress

| Session | Status | Commit | Notes |
|---|---|---|---|
| S1 Analysis and plan | DONE 2026-11-18 | (this commit) | 119 Doc IDs in 18 modules (Phase 1, owner R1–R3); findings P1–P7 from code; sessions S2–S18. |
| S2 Stack, tooling, staff | DONE 2026-11-18 | (this commit) | `REC_ROOT` in `shoot.ts`. Stack `itcdocs` snapshot `rec-start` (IT Counselor final state), then spec `rec-s2-staff-setup` (2 tests): Super Admin created Docs Team Lead (global placement_manager) and Docs HR Manager; IT Admin created Docs Recruiter A/B on Recruiter Staff (manager Docs Team Lead; DOCS-REC-A/B), Docs Placement Officer, Docs HR, Docs Interviewer on Users. All Awaiting setup. 14 PNGs. Snapshot `after-rec-s2`. |
| S3 Account access and navigation | DONE 2026-11-18 | (this commit) | Spec `rec-s3-account-access` (2 tests). All 7 personas set passwords (DOCS_TEST_PASSWORD); the Team Lead's link opens `/admin/reset-password`. Every sidebar item of the 6 roles opened (headings logged). 27 PNGs. Snapshot `after-rec-s3`. |
| S4–S18 | not started | | |

## Owner decisions
- R1 Scope: core hiring flow first (Phase 1); vendors, campus, receivables, targets/daily plans/activity reports, business dashboards, insights and report libraries in Phase 2.
- R2 Phase 1 also covers the candidate portal, the IT student opt-in and the recruitment-related admin set-up.
- R3 Placements are closed for real (invoice draft shown); no money, payment, invoice issue or receivable is ever recorded.
- Stack: `itcdocs` only (web 3060, api 8060, Mailpit 127.0.0.1:8032), starting from the IT Counselor set's `after-s10` snapshot.

## Feature status
| Doc ID | Status |
|---|---|
| DOC-REC-ADM-001, ADM-002 | DONE (S2) |
| DOC-REC-ADM-003 | PARTIAL: edit (S2); deactivate/reactivate in S16 |
| DOC-REC-AUTH-001..004 | DONE (S3) |
| DOC-REC-AUTH-005 | PARTIAL: sign out (S3); deactivated account in S16 |
| DOC-REC-NAV-001..003 | DONE (S3) |
| DOC-REC-DASH-003..005 | DONE (S3, figures from seed data) |
| Others | not started |

## Planned link targets (keep these file names)
- `user-manual/dashboard/dash-001-recruiter-dashboard.md`
- `admin-manual/admin/adm-004-team-reassign.md`
- `user-manual/hr/leg-001-legacy-placement.md`

## Discovered functionality
(none yet)
