# tel-011 follow-ups — implementation plan

Spec: `docs/superpowers/specs/2026-10-06-tel-011-follow-ups-design.md`. TDD per task: failing test → minimum code → green → refactor.
Focused tests only (per [test-regression-cadence]); tel e2e with `--workers=1`.

| # | Task | Tests first | Files |
|---|---|---|---|
| 1 | Model `LeadFollowUp` + `LEAD_FOLLOW_UP_REASONS` + migration `0089_lead_follow_ups` | `test_tel_011_migration.py` (chain, model = migration, upgrade/CHECK/downgrade in a throwaway DB) | `models.py`, `alembic/versions/0089_lead_follow_ups.py` |
| 2 | Schemas `LeadFollowUpCreate/Update/Cancel` (aware datetime, reason literal, lengths, extra forbidden) | in task 3 tests (422s) | `schemas.py` |
| 3 | Service `lead_follow_ups.py` + routes create / list-for-lead (scope 404, manager 403, handed-over 403, closed 409, past/far 422, stage tick, audit) | `test_tel_011_follow_ups.py` | `services/lead_follow_ups.py`, `api/telecaller_follow_ups.py`, `main.py` |
| 4 | PATCH / complete / cancel (open only 409, changed-due future 422, other telecaller 404, reassigned lead moves) | same file | same |
| 5 | Day / overdue list + counts (IST window exact, ordering, overdue flag, manager reads reports) | `test_tel_011_lists.py` | same |
| 6 | Close cancels open follow-ups in `person_move`; My Leads `follow_up=` filter | `test_tel_011_pipeline.py`; re-run `test_tel_004_*`, `test_tel_008_workspace.py` | `services/lead_pipeline.py`, `api/telecaller.py` |
| 7 | Web lib + `FollowUpForm` + `LeadFollowUps` on the lead detail | vitest `telecallerFollowUps.test.ts`, `FollowUpForm.test.tsx`, `LeadFollowUps.test.tsx` | `lib/telecallerFollowUps.ts`, components, `LeadDetailPanel.tsx`, `TelecallerLeadPages.tsx` |
| 8 | `TodayFollowUps` pages + nav + dashboard card + My Leads filter | vitest `TodayFollowUps.test.tsx`, `TelecallerLeadTable` test | `app/telecaller/follow-ups`, `app/telecaller/manager/follow-ups`, `navigation.ts`, dashboard, `TelecallerLeadTable.tsx` |
| 9 | Playwright `tel-011-follow-ups.spec.ts` + browser QA (desktop/tablet/mobile) | e2e | `apps/web/e2e/` |
| 10 | Docs: `DEC-SCOPE-093`, API §12P, backlog status, RBAC matrix rows | — | `docs/decisions`, `docs/architecture/API_CONTRACT.md`, backlog |
