# pob-027 implementation plan

Spec: `docs/superpowers/specs/2026-11-08-pob-027-intake-automation-design.md`.

1. **Models + migration 0315** — `RequirementAutomationSetting`, `RequirementTask`, `EscalationRule`, `EscalationEvent` with check
   constants; migration creates when missing, seeds the settings row. Test: migration/model checks identical.
2. **Service `requirement_intake.py`** — `eligible_owner`, `on_created` (auto-assign, notify / Team Lead notice, tasks),
   `on_assigned` (notify, move open tasks or create once), settings read/save, task list/complete. Tests first (RED) via API.
3. **Hook** — `recruiter_requirements.record_created` calls the owner fallback before `record_primary`, then `on_created`; the assign route
   calls `on_assigned`.
4. **Escalations service `escalations.py`** — rules CRUD + `run_escalations(now)`; worker task + beat `pob027-escalations`.
5. **Router `recruiter_automation.py`** — settings GET/PUT, rules GET/POST/PATCH, requirement tasks GET + complete; schemas.
6. **Events** — `it.requirement.unowned`, `it.recruiter.escalated` in `EVENTS` and `RECRUITMENT_EVENTS`.
7. **Web** — `lib/recruiterAutomation.ts`, `components/IntakeAutomationSettings.tsx`, `components/RequirementTasks.tsx`, page
   `/recruiter/automation`, nav links, task panel on the requirement page; vitest tests.
8. **Docs** — DEC-SCOPE-434, API §12MA, RBAC §2.325, RTM, backlog status.
9. **QA** — focused pytest, vitest, lint/types/build, Playwright e2e + browser pass.
