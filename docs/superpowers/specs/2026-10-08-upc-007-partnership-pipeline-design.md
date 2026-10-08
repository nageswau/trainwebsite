# upc-007 — Partnership stage engine + history + Kanban (design + plan)

**Status:** design written 2026-10-08. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". So the item answers PS1–PS12 (§1) are **recommended defaults accepted under that instruction**
(`NEEDS_CONFIRMATION` as separate per-question approvals) and are registered that way in `DEC-SCOPE-125`.

**Branch:** `feature/upc-007`, cut from `origin/main` @ `593e9b9c` (after #151, upc-003).
**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-007, §3.1 U7, Appendix B "Stage groupings". Dependency upc-003
(`0105_university_master`, `DEC-SCOPE-120`) is merged on main — verified in code.
**Source:** `EVID-020` §3 (L92–L154, 15 statuses; the backlog's "14" miscounts the source, which Appendix A (L98–L154) and Appendix B both list as 15), §4 (L156–L174, Kanban with 9 columns), §32 menu entry "Partnership Pipeline" (L1072),
§33 record tab "Partnership status" (L1110).
**Numbering:** migration `0110_university_pipeline`, `DEC-SCOPE-125`, API §12AS, RBAC §2.51 (renumbered at merge if another item lands
first). Drafted as `0106` / `DEC-SCOPE-121` / §12AO / §2.47; renumbered on merging `main` @ `a62ad9d7` (rec-003 and rec-009 took
`0106`–`0107`, `DEC-SCOPE-121`–`122`, §12AO–§12AP, §2.47–§2.48 first). Renumbered again from `0108` / `DEC-SCOPE-123` / §12AQ / §2.49 on merging `main` @ `5b7c1fd5`
(upc-006 and upc-004 took `0108`–`0109`, `DEC-SCOPE-123`–`124`, §12AQ–§12AR, §2.49–§2.50 first).
**Gate:** `APPROVAL_GATES.md` GATE-09.
**Template:** bdm-004 (`bdm_stages.py`, `services/bdm_pipeline.py`, `api/bdm_pipeline.py`, `BdmPipelineBoard.tsx`,
`BdmOrganizationPipeline.tsx`, `BdmStageHistory.tsx`) — same rules (stale `from_stage` → 409, backward needs a note, Lost is a flag on
top of the kept stage), applied to `universities`.

## 1. Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| PS1 | Stored stage | The 15 §3 statuses as snake_case keys in source order + source labels, in `app/partnership_stages.py` (constants only, shared by the model CHECK, migration parity test, service and schemas). Lost/Closed is **not** a stage: `lost_at` + `lost_reason` on top of the kept stage (U7, bdm-004 S5) |
| PS2 | Backfill (Q-08 "existing 11 → ?") | **Every existing row starts at `target_university`**, `stage_changed_at = created_at`. Marking the 11 catalogue universities as partners would invent facts; managers move them. No history rows are written by the migration |
| PS3 | Groupings | Appendix B K (9 Kanban columns), G (map groups) and P (probability %) live in the catalogue as constants. Agreement Signed → **G2** (the table's primary reading; Q-08 alternative "Partner" stays open). Only K is used by this item; G/P are for upc-022/023/025 and asserted by a unit test so they cannot drift |
| PS4 | Moves | Any stage to any other (forward or back). Backward requires a note (reason). Same stage → 422. The body carries `from_stage` (the stage the form showed); a different stored stage → 409 `stage_changed` with `current_stage` (concurrent moves: row lock + optimistic check) |
| PS5 | Who moves / marks lost | `can_move_stage`: the university's primary or backup `partnership_manager`; the `partnership_head` for universities in their write scope (unowned or owned by a direct report, UM9); `super_admin`. **`overseas_admin` reads only** (backlog: "owner or head"; U3 overseas_admin read access) |
| PS6 | Reopen | `can_reopen`: `partnership_head` (write scope) and `super_admin` only (backlog: "reopen by the head"). Clears the flag; the university is back at the stage it was lost at |
| PS7 | Reasons | Lost and reopen each require a reason (1–500 chars, plain text, line breaks allowed) — the bdm-004 `BdmPipelineReason` type. Move note optional forward, required backward |
| PS8 | Lost / inactive guards | A lost university cannot be moved or marked lost again (409 `university_lost`); reopen on a non-lost one is 409 `university_not_lost`. An inactive university is read-only (409 "Reactivate this university first", upc-003 UM10) |
| PS9 | History | `university_stage_history` append-only: kind `move` / `lost` / `reopened`, from/to stage (equal for lost/reopened), note (move note or reason), actor, `position` (identity, orders rows), `created_at`. No stage CHECK (history survives a catalogue change). Readable by every read role |
| PS10 | `stage_changed_at` | NOT NULL, server default now(); set on every move (not on lost/reopen, which have their own history rows). For upc-008/015 "days in stage" |
| PS11 | Board scope | `GET /partnership/pipeline` for every read role (managers read every row, UM9). Filters: `column` (K key or `lost`), `manager` (`me`/`none`/uuid, the list's rule). The page defaults managers to "Mine" with an "All" toggle; others see all. Inactive universities are excluded; lost ones are counted only in `lost_count` and listed only under `column=lost` (Appendix B: excluded from K) |
| PS12 | Board shape | The `BdmPipelineBoard` pattern (backlog): 9 column tiles + Lost with counts as links, then a paged table of the chosen column (or every open university). Server-rendered; filters in the URL |

## 2. Data model — migration `0110_university_pipeline`

`universities` gains (guarded, since 0001 builds from models):

| Column | Type | Rule |
|---|---|---|
| `stage` | String(40) | NOT NULL, default `target_university`; CHECK ∈ the 15 keys; indexed `ix_universities_stage` |
| `stage_changed_at` | timestamptz | NOT NULL, server default now(); backfilled `= created_at` |
| `lost_at` | timestamptz | nullable |
| `lost_reason` | String(500) | nullable; CHECK `(lost_at IS NULL) = (lost_reason IS NULL)` |

New table `university_stage_history` (id, university_id FK RESTRICT, actor_user_id FK RESTRICT, kind CHECK ∈ move/lost/reopened,
from_stage, to_stage String(40), note String(500) nullable with CHECK `kind = 'move' OR note IS NOT NULL`, position BIGINT identity,
created_at; index `(university_id, position)`).

Downgrade refuses while any history row exists, any university is lost, or any is past `target_university` (dropping would lose them).

## 3. Backend

`app/partnership_stages.py` (catalogue), `services/partnership_pipeline.py` (single writer of `stage`/`lost_*`; functions only, no
commit), `api/partnership_pipeline.py`.

| Route | Who | Notes |
|---|---|---|
| `POST /partnership/universities/{id}/stage` | `can_move_stage` | `{from_stage, to_stage, note?}` → `UniversityEnvelope` |
| `POST /partnership/universities/{id}/lost` | `can_move_stage` | `{reason}` |
| `POST /partnership/universities/{id}/reopen` | `can_reopen` | `{reason}` |
| `GET /partnership/universities/{id}/stage-history` | read roles | `{items,total,limit,offset}`, newest first |
| `GET /partnership/pipeline` | read roles | `column`, `manager`, `limit`, `offset` → `{columns:[{key,label,stages,count}], lost_count, items, total, limit, offset}` |

- Every write: `require_reader` → `load(lock=True)` (FOR UPDATE) → `team_of` → `require(…, action)` (403 logged / 409 inactive) →
  pipeline rule checks → change + history row + `AuditLog` (`university.stage_changed|lost|reopened`, stage keys + flags only, never
  the note/reason text) → one commit → structured log (`university_stage_changed`, …; a stale move logs `university_stage_conflict`).
- `permissions` gains `can_move_stage` and `can_reopen` (same `_in_scope` rule; inactive → false).
- Output: `UniversityRow` gains `stage`, `stage_label`, `lost` (bool); `UniversityDetail` gains `pipeline` =
  `{stage, stage_label, column, column_label, changed_at, lost: {at, reason}|null, stages: [{key, label, column}]}`.
- Board counts: one grouped query `(stage, lost) → count` over the filters, folded into the 9 columns; then one joined page query
  (universities + country + primary manager) ordered by name, id. Unknown `column` → 422.

## 4. Frontend

- `lib/partnershipPipeline.ts`: types, URLs, `isBackward`, `stageChanged`/`lostConflict` readers, board query + `href`.
- `components/UniversityStagePanel.tsx` (client): stage list as text (done/current/upcoming, never colour alone), column name, Lost
  banner, Move form (select + note, required when backward), Mark lost / Reopen with reason + Cancel; double-submit guard; stale move
  refreshes and explains; 422 field errors. `router.refresh()` after success (the detail page is server-rendered).
- Stage history: **reuses `components/BdmStageHistory.tsx`** (newest first, "Show more", retry on failure) with an optional `url` prop
  (a string, so the server page can pass it) and a "Reopened at …" title; remounted (keyed on `changed_at` + `lost.at`) after each change.
- QA fixes (Phase 5/6): QA7-01 board table uses the shared `.table` styling; QA7-02 the move form's select keeps its height; QA7-03 the
  Lost/Reopen button is not stretched; QA7-04 long unbroken history notes wrap (`overflow-wrap: anywhere`).
- `components/PartnershipPipelineBoard.tsx` (server): column tiles + Lost, the table (code, name, country, stage, primary manager),
  pager, empty/past-end states.
- `/partnership/pipeline` page (no `loading.tsx`: no partnership page has one): Mine/All toggle for managers, invalid filter → reset link.
- University detail page: "Partnership stage" + "Stage history" sections. `UniversityTable`: a Stage column (with a Lost badge).
- Nav: `PARTNERSHIP_MENU` "Partnership Pipeline" → live; `PARTNERSHIP_HEAD_NAV` gains it.

## 5. Acceptance criteria

| AC | Statement | Proven by |
|---|---|---|
| AC1 | Every change (move, lost, reopen) is in history with actor, from/to and note | `test_upc_007_stage.py`; e2e |
| AC2 | Kanban column counts equal the Appendix B K mapping | `test_upc_007_catalogue.py`, `test_upc_007_board.py` |
| AC3 | Lost requires a reason | stage tests (422) |
| P1 | Interested → Meeting Scheduled by the owner | stage tests; e2e |
| N1 | Non-owner manager move → 403; overseas_admin move → 403; manager reopen → 403 | `test_upc_007_access.py` |
| E1 | Stale `from_stage` → 409 `stage_changed`; two concurrent moves → one 200, one 409 | stage + concurrency tests |
| E2 | Lost university reopened by the head → back at its stage, history row `reopened` | stage tests; e2e |
| E3 | Backward without note → 422; same stage → 422; unknown stage → 422; inactive → 409 | stage tests |
| M1 | Migration: existing rows `target_university`, `stage_changed_at = created_at`; CHECKs equal the model; downgrade guard | `test_upc_007_migration.py` |

## 6. Tasks (TDD, in order)

1. Catalogue + model columns + history model + migration + parity/catalogue tests.
2. Schemas + service + stage/lost/reopen routes with tests (rules, access, history, audit, concurrency).
3. Board route tests then code; row/detail output fields.
4. Frontend lib + components + pages + nav with vitest.
5. Playwright `upc-007-partnership-pipeline.spec.ts`; docs (DEC-SCOPE-125, API §12AS, RBAC §2.51, DATA_MODEL, SCREEN_CATALOG, backlog).

## 7. Regression set (lite)

`test_upc_003_*`, `test_upc_001_*`, `test_bdm_004_*` (untouched template), public catalogue tests (`test_upc_003_public.py`),
`navigation.partnership.test.ts`, `middleware.test.ts`, upc-003 web tests.
