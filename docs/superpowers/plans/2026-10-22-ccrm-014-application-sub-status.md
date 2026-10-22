# ccrm-014 — Application sub-status — plan

Design: `docs/superpowers/specs/2026-10-22-ccrm-014-application-sub-status-design.md`. TDD per task; lite backend set only.

1. **Mapping + validator** — `app/application_sub_status.py`; model columns + `@validates("status")`. Tests: unit mapping, SS3
   (advance clears, enrolled sets).
2. **Migration 0168** — columns + SS2 backfill; migration test (chain, columns, backfill, round trip).
3. **Service + counselor/admin route** — `services/application_sub_status.change`; `POST /workflows/overseas/applications/{id}/sub-status`.
   Tests: same-stage move, later-stage advance, earlier stage 422, unknown 422, no-op, withdrawn 409, other counselor 403, agency
   Enrolled 403, admin Enrolled + commission, history row, other application untouched (AC 9), notifications.
4. **Agent route** — `POST /workflows/overseas/agent/crm/applications/{id}/sub-status`; Enrolled 403; other agency 404; counselor told.
5. **Reads** — list, `/status` history, portal tables, agency list/detail/history.
6. **Web** — `lib/applicationSubStatus.ts`; counselor card form; agency detail form + badge + history; vitest.
7. **Docs** — DEC-SCOPE-240, API §12ER, RBAC §2.154, DATA_MODEL, backlog status, RTM; e2e spec.
