# hrc-035 plan — candidate consent, retention, deletion, access revocation

Design: `docs/superpowers/specs/2026-11-04-hrc-035-candidate-privacy-design.md` (DEC-SCOPE-396). TDD per task; focused tests only.

| # | Task | Tests first (`apps/api/tests/test_hrc_035_*.py`, web vitest) |
|---|---|---|
| 1 | Models + migration `0273_candidate_privacy` (consent source/basis + backfill, `anonymised_at/_reason`, retention settings, `candidates.erase` seed); rbac catalogue + default | migration up/down, frozen checks equal models |
| 2 | K1/K2: consent writers record source; create/import accept `lawful_basis`; detail `consent` | each source row; omitted = no row; bad value 422 |
| 3 | K3/K4 anonymiser + pool filter | fields wiped, rows deleted, files removed, portal login fails, recruiter 404, report count kept |
| 4 | K5/K6/K7 request + queue + decision; admin SEC-002 refuses candidate subject | idempotent request, 403 matrix, reject reason, offer hold 409, double decision 409 |
| 5 | K8 retention settings + sweep + beat | off by default; due count; only eligible anonymised; super_admin-only PUT |
| 6 | K9 deactivation release + session bump | officer/collaborator cleared with history; session ended |
| 7 | Web: Privacy "Delete my data" card; HR Manager page (queue + retention card); nav; recruiter form + import basis select; detail line | vitest per component |
| 8 | Docs: decision register, API §12KO, RBAC §2.290, RTM rows, retention policy note; e2e spec | Playwright `hrc-035` |

## Phase 3 review (API / frontend / security)
- **API:** candidate routes take no id (own request only, C10 idiom); queue ids are request ids, 404 for non-candidate requests.
  Decision is `POST` (state transition), 409 on a decided request (row `FOR UPDATE`), 409 on a hold, 422 on a missing/long reason.
  Retention `PUT` 422 outside 6–120; `null` turns it off. All additive: Privacy/detail responses only gain keys.
- **Transactions:** the anonymiser runs inside the decision transaction; storage keys are collected and deleted after the commit
  (a failed delete is logged, never re-exposes data because rows are gone). The sweep commits per batch of 100 with `SKIP LOCKED`.
- **Security:** `candidates.erase` checked server-side; the HR Manager sees only candidate deletion requests; audit/logs carry ids and
  counts only; the reject reason is shown to the candidate as text (React escapes). CSRF: JSON bodies under SameSite=Lax cookies (repo
  posture). No new rate limit: one open request per candidate.
- **Frontend:** reuse `PortalShell`, `sendJson`, `.card`/`.table.compact`, `LocalTime`; confirm step before a deletion request; busy
  states on every button; empty states ("No deletion requests waiting"); errors in `role="alert"`; mobile — the queue table is compact
  and wraps (the shared `.table` min-width trap).
