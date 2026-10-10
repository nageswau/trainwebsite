# upc-032 — Partnership manager deactivation + bulk reassignment (design)

**Date:** 2026-10-10 · **Branch:** `feature/upc-032` · **Gate:** GATE-09 (EVID-020 in scope, U1) · **Migration:** none

## 1. Source and intent

- `EVID-020` §27 (L896–L906): every university has a primary and a backup manager; "only the assigned manager should normally manage
  the active partnership, while management has visibility". Backlog §upc-032 adds deactivation and reassignment on the tel-025 precedent
  (it is listed under "Added though not in the source").
- Backlog acceptance: *deactivating a manager who is primary on universities is refused until those are reassigned (Q-30); the head can
  bulk-reassign primary/backup + open tasks, with history; after reassignment the old manager cannot edit. Positive: move 40
  universities. Negative: a target manager outside the team → 422. Edge: the backup is the same as the new primary.*
- Dependencies upc-003 (ownership columns, `university_assignment_history`) and upc-020 (`partnership_tasks`) are merged on main.
  DEC-SCOPE-118 PU10 left the plain `PATCH active` in place "no reassignment (upc-032)".

## 2. Decisions (recommended answers, `NEEDS_CONFIRMATION` at sign-off — registered as DEC-SCOPE-171)

| # | Question | Answer |
|---|---|---|
| RA1 | Q-30: is the backup promoted automatically? | No. A head (or super_admin) reassigns explicitly from the Team page; nothing changes ownership as a side effect of deactivation |
| RA2 | What blocks deactivation | Being the **primary** manager of ≥ 1 university (active or inactive). Backup slots and open tasks do not block; they stay on the inactive manager until a head moves them (RA8) |
| RA3 | Refusal shape | `PATCH /admin/users/{id}` `{active:false}` → `422` "This manager is the primary manager of N universities. A partnership head must reassign them (Team page) before deactivation." — 422, not 409, because the Users page reads 409 as the trainer cascade prompt (tel-025 D5) |
| RA4 | Who reassigns | `partnership_head` (from and to their direct reports) and `super_admin` (any manager to any active manager). `overseas_admin` does not assign (UM7) → 403; managers → 403; signed out → 401 |
| RA5 | What moves | Every university where the source is primary → the target becomes primary; where the source is backup → the target becomes backup; every **open** task assigned to the source → the target. Done / cancelled tasks keep their assignee (history) |
| RA6 | Edge: the target is already the other slot | Target already backup where the source is primary → target becomes primary and the backup slot is cleared. Source is backup where the target is primary → the backup slot is cleared. A university never holds the same person twice |
| RA7 | Inactive universities | Move too (ownership must not point at an inactive person after reactivation) |
| RA8 | Source state | Active or inactive (a manager deactivated before upc-032, or one keeping backup slots / tasks, can still be handed over) |
| RA9 | Invalid input | Source not a partnership manager → `404`; source not in the head's team → `403`; target inactive, not a manager, outside the head's team, or equal to the source → `422` (one message, upc-003 `MANAGER_INVALID`); nothing to move → `409` |
| RA10 | History | One `university_assignment_history` row per changed slot + one `university.assign` audit per university (`reason: "reassign"`); one `partnership_task.reassign` audit per task; one `partnership.reassign` audit on the source user with the counts. Logs carry ids and counts only |
| RA11 | Transaction and locks | One transaction. Lock order: the source's universities (by id, FOR UPDATE), then its open tasks (by id, FOR UPDATE), then the target (FOR SHARE, upc-003 `locked_manager`) — the assign route's university-then-manager order, so the two cannot deadlock |
| RA12 | Deactivation race | The deactivation pre-check locks the user row FOR UPDATE before counting, so a concurrent assign (which reads the manager FOR SHARE) either commits first and is counted, or waits and then sees an inactive manager (422) |
| RA13 | Notifications | None (not in the source; `NEEDS_CONFIRMATION`) |
| RA14 | Preview | The Team page rows carry each manager's `work` counts (primary, backup, open tasks); the dialog shows them; the response's `moved` is authoritative |

## 3. API

`POST /partnership/head/reassign` body `{from_user_id, to_user_id}` (extra keys forbidden) → `200`
`{from_user_id, to_user_id, moved: {primary, backup, tasks}}`.

`GET /partnership/head/team` rows gain `work: {primary, backup, tasks}` (additive; one grouped query per page, no N+1).

`PATCH /admin/users/{id}` `{active:false}` on a partnership manager who is primary anywhere → `422` (RA3). Other roles unchanged.

## 4. Web

- Team page (`/partnership/head/team`): two new columns, *Universities* ("3 primary · 1 backup") and *Open tasks*, and a *Reassign*
  button on rows with work. It opens an inline group (tel-025 `AdminTelecallerLifecycle` conventions: no dialog library, focus moves to
  the group, Escape cancels, an error takes focus) with the counts, a manager picker (upc-003 `managerSearch`, the source excluded), the
  RA6 note and Confirm / Cancel. On success a `role="status"` notice and `router.refresh()`.
- The admin Partnership managers row already shows the server's 422 sentence on Deactivate; its comment is updated.

## 5. Tests

- API (`test_upc_032_reassign.py`): deactivation refused with primary (message + count), allowed with only backup / tasks, allowed after
  reassignment; reassign moves primary + backup + open tasks (done tasks stay), history and audit rows, RA6 both directions, inactive
  source and inactive university, 40 universities in one call, old manager → 403 on PATCH after the move; 422 target outside the team /
  inactive / same as source; 403 source outside the team, overseas_admin, manager; 404 unknown source; 409 nothing to move; 401 signed out;
  team rows carry `work`.
- Web unit (`PartnershipReassign.test.tsx`, `PartnershipTeamTable.test.tsx`): counts text, button only with work, submit body, server
  message on 422, plain words on 5xx, Escape cancels.
- E2E (`upc-032-manager-reassign.spec.ts`): super admin's deactivate refused → head reassigns → deactivate succeeds.

## 6. QA evidence (2026-10-10, isolated stack `upc032`, `localhost:13232`)

- API: `test_upc_032_reassign.py` 19 passed; affected suites (upc-001/003/020, tel-025, bdm-025, adm-001) 172 passed on the final code
  (`test_upc_001_reads` updated for the additive `work` key).
- Web: `PartnershipReassign.test.tsx` + `PartnershipTeamTable.test.tsx` 8 passed; `tsc --noEmit` and ESLint clean; `next build` compiled.
- E2E: `upc-032-manager-reassign.spec.ts` 2 passed, `upc-001-partnership-roles.spec.ts` 4 passed.
- Exploratory pass (Playwright, Chromium), QA-01..QA-19 all as expected: manager / overseas_admin refused (403); overseas_admin's
  Deactivate shows the RA3 sentence; desktop 1366, tablet 820 and phone 375 have no page side-scroll; counts per row; no Reassign without
  work; Escape returns focus; the picker offers only active team-mates (not the source, an inactive manager or another head's); an
  injected 500 shows plain words, a network abort the standard message; a double click sends one POST; the RA6 edge clears the backup;
  reload shows the moved counts; a stale dialog gets the 409 sentence; the old manager's PATCH is 403; deactivation then succeeds; signed
  out → `/admin/login?next=…`. Console: only the resource errors of the deliberate 4xx/5xx/abort cases. No defects in scope.
