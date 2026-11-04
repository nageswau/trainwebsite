# hrc-010 — Candidate profile completion (plan)

Design: `docs/superpowers/specs/2026-11-04-hrc-010-candidate-profile-design.md` (DEC-SCOPE-383). TDD per task: red → green → refactor.

| # | Task | Tests first |
|---|---|---|
| 1 | Models + migration `0260_candidate_profile` (columns, 3 tables, `is_primary`, backfill P11) | `test_hrc_010_migration.py`: upgrade adds tables/columns, backfill makes education row 1 + `preferred_roles`, downgrade removes, re-upgrade idempotent |
| 2 | `services/candidate_profile.py`: `experience_months(periods, today)` (P4), row validation schemas (P2/P3/P7), `completeness()` (P10) | unit: overlap counted once, touching periods, current job to today, rounding; schema 422s (end < start, future dates, caps, expiry < issue) |
| 3 | Create/PATCH: replace-set rows, scalar fields, mirrors (P5), derived experience (P4), email change clears verification (P9), `updated_at` bump on row-only save, audit row diff; detail output + completeness | `test_hrc_010_profile.py`: AC1–AC6 via the API, legacy client compat, hr_team 403 on write, stale guard on row-only save, history shows rows |
| 4 | Skills `is_primary` (P7) | add/PATCH/list round trip; null rejected |
| 5 | Merge moves rows when survivor has none; resume apply re-derives (P12) | merge test; resume apply with employment rows keeps derived experience |
| 6 | Web: `lib/recruiterCandidates.ts` types/body/mapping, `CandidateRowsEditor`, form fieldsets, detail rows + completeness meter, skills Primary | vitest: body mapping, form add/remove rows and submit body, detail meter + rows, skills checkbox |
| 7 | e2e `hrc-010-candidate-profile.spec.ts` | happy path, 422 path, mobile layout |
| 8 | Docs: decision register, API contract, RTM, backlog status | — |
