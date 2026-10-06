# tel-008 — Lead workspace: implementation plan

Spec: `docs/superpowers/specs/2026-10-06-tel-008-lead-workspace-design.md`. TDD per task. Focused tests only; the full backend suite is
the user's (see test-regression cadence).

| # | Task | Test first | Files |
|---|---|---|---|
| 1 | `TelecallerLeadUpdate` schema (D2) | `test_tel_008_workspace.py`: extra keys / bad email / bad priority → 422 | `schemas.py` |
| 2 | `GET /telecaller/leads` (scope, filters, q, paging) | AC1, AC6; other roles 403 | `api/telecaller.py` |
| 3 | `GET /telecaller/leads/{id}` (+ `message`, `read_only`) | AC2 404s; AC4 read_only | same |
| 4 | `PATCH /telecaller/leads/{id}` (lock in scope, D1 403, audits) | AC3 audit; AC4 403; AC5 422; inactive product 422; no-op = no audit | same, `services/telecaller_leads.py` |
| 5 | Stage route D1 guard | telecaller stage on handed-over lead → 403; manager still 200 | `api/telecaller.py` |
| 6 | `GET /telecaller/leads/{id}/timeline` (UNION, newest first) | AC3 timeline; scope 404 | `services/telecaller_leads.py` |
| 7 | Web lib + `LeadStageControl` `move`/`canReopen` props | vitest: control posts to the telecaller route | `lib/telecallerLeads.ts`, `AdminLeadStage.tsx` |
| 8 | `TelecallerLeadTable` | vitest: rows, empty/filtered/error states, URL filters | component |
| 9 | `LeadDetailPanel` (fields, priority, edit, call, activity, read-only) | vitest: priority save → activity refresh; read-only hides controls | component |
| 10 | Pages + nav | Playwright `tel-008-lead-workspace.spec.ts` | `app/telecaller/**` |
| 11 | Docs: DEC-SCOPE-084, API §12J, backlog status, RTM row if any | — | docs |

Security review: IDOR (scope in every WHERE), role 403s, no PII in logs or audits, React escaping, a `tel:` href built from a
sanitised number, and CSRF through the existing `sendJson` cookie and header idiom. Concurrency: `FOR UPDATE` in scope.
