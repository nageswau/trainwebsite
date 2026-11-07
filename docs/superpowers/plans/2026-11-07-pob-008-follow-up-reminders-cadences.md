# pob-008 plan — follow-up reminders and outreach cadences

Spec: `docs/superpowers/specs/2026-11-07-pob-008-follow-up-reminders-cadences-design.md` (DEC-SCOPE-423).

| # | Task | Test first (RED) | Files |
|---|------|------------------|-------|
| 1 | Models + migration 0303 (reminded_at, 2 reasons, cadences, runs, indexes, upgrade stamp, downgrade) | `test_pob_008_migration.py` chain / frozen checks / round trip; update `test_pob_016_migration` pin to 0303's old copy | `models.py`, `alembic/versions/0303_outreach_cadences.py` |
| 2 | Reminder sweep B1–B4 + event + beat | once per follow-up, rerun adds nothing, owner = current assignee, archived skipped, PATCH re-arms, overdue at migration not resent | `services/recruiter_cadences.py`, `notifications/events.py`, `worker.py`, `api/recruiter_follow_ups.py`, follow-up `_out` |
| 3 | Cadence CRUD B5 | manager create/edit, recruiter 403 write / 200 read, step rules 422, template rules 422, duplicate name 409 | schemas, `api/recruiter_cadences.py`, `main.py` router |
| 4 | Start / stop B6, B9 + message output | start rules (404/403/409/422), snapshot, one active per contact, reply stops, DNC stops, manual stop | `recruiter_messages.py`, `contact_status.py`, `recruiter_contacts.py` |
| 5 | Cadence sweep B8 | next step after the day with rendered template, no step before the day, reply-since-start stops, DNC stops, last step completes, reassigned → new owner | `recruiter_cadences.py`, `worker.py` |
| 6 | First outreach B10 | company create (with/without contact), contact create, DNC contact none | `api/recruiter_companies.py`, `api/recruiter_contacts.py` |
| 7 | rec-038 matrix rows | matrix test | `tests/rec038_rows_*.py` |
| 8 | Web lib + cadence library page + nav | vitest library (load/empty/error, add, step validation, read-only) | `lib/recruiterCadences.ts`, `components/RecruiterCadenceLibrary.tsx`, `app/recruiter/manager/cadences/page.tsx`, `lib/navigation.ts` |
| 9 | Message cadence control + reason labels | vitest start/stop/status | `components/RecruiterMessages.tsx`, `lib/recruiterFollowUps.ts`, `MessagesSection` type only |
| 10 | Docs: DEC-SCOPE-423, API 12LP, RBAC 2.314, RTM, backlog status | — | `docs/...` |
| 11 | Playwright e2e + browser QA | `pob-008-cadences.spec.ts` | `apps/web/tests/e2e` |
