# upc-008 — Expected timeline + milestone tracker (design + plan)

**Status:** design written 2026-10-09. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". So the item answers MS1–MS12 (§1), including **Q-10** and **Q-11**, are **recommended defaults
accepted under that instruction** (`NEEDS_CONFIRMATION` as separate per-question approvals). They are registered that way in
`DEC-SCOPE-143`.

**Branch:** `feature/upc-008`, cut from `origin/main` @ `788b1636` (after #186, upc-020).
**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-008, Q-10, Q-11, Appendix A L176–L242.
**Dependency:** upc-007 (stage engine, `0111_university_pipeline`, `DEC-SCOPE-126`) is merged on main (#159). This was verified in code
(`app/partnership_stages.py`, `services/partnership_pipeline.py`, `university_stage_history`).
**Source:** `EVID-020` §5 (L176–L210: six per-university targets, a milestone table with target date and status, the ABC University
example) and §6 (L212–L242: 13 milestones, "The system should automatically highlight delayed milestones").
**Numbering:** migration `0128_university_milestones`, `DEC-SCOPE-143`, API §12BK, RBAC §2.69 (renumbered at merge if another item lands
first). Drafted as `0127` / `DEC-SCOPE-142` / §12BJ / §2.68; renumbered on merging `main` @ `7ba4cb36` (upc-014 took them first). A
database stamped at `0127_university_milestones` is re-stamped with `alembic stamp --purge 0126_partnership_tasks`, then `upgrade head`
(every step is guarded).
**Gate:** `APPROVAL_GATES.md` GATE-09.

## 0. Discovery (Phase 1)

| Class | Items |
|---|---|
| MUST CHANGE | `models.py` (4 `universities` columns + `UniversityMilestone`), migration `0127`, `schemas.py`, new `app/partnership_milestones.py` (catalogue), new `services/partnership_milestones.py`, new `api/partnership_milestones.py`, `main.py` (router), `services/partnership_universities.py` (`can_edit_timeline` permission + `expected` block in `detail_out`), web `lib/universities.ts` (types), new `lib/partnershipMilestones.ts`, new `components/UniversityTimeline.tsx`, `app/partnership/universities/[id]/page.tsx` |
| MAY CHANGE | `tests/components/UniversityDetailPage.test.tsx` (stub the new read), docs (DEC-SCOPE, API, RBAC, DATA_MODEL, SCREEN_CATALOG, backlog status) |
| SHOULD NOT CHANGE | the application write sites (`api/admin.py`, `api/agent_applications.py`, `api/workflows.py`, `api/inbound.py`), the stage engine (`partnership_pipeline.py`), tasks (`partnership_tasks.py`) |
| HIGH REGRESSION RISK | `detail_out` (every university route returns it); the shared university page (upc e2e specs use page-wide `role=status` locators, so a new always-present `role=status` would break them) |

Reusable: `_locked` / `require` / `audit` / `log` (upc-003), `india_today` (bdm_travel), `IST` (bdm_appointments), `sendJson` +
`fieldErrors`, `formatCalendarDate`, `useFocusAfterRender`, the `.table` / `.badge` / `.status error` / `.form-error` styles.

## 1. Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| MS1 | Milestone kinds | The 13 §6 milestones in source order and wording (University Contacted … Active Partnership), as constants in `app/partnership_milestones.py`. They are shared by the model CHECK, the migration parity test, the service and the schemas |
| MS2 | "Created from a template when a university leaves Target" | **The catalogue is the template and applies to every university**. Stored rows exist only once someone records a date (sparse rows, upserted under the university row lock). Visible behaviour after leaving Target is the same. It needs no stage hook, no backfill and no invented rows, and it works for universities that left Target before this item. Before leaving Target the table simply shows 13 pending milestones that can already be planned |
| MS3 | Q-11 status (computed, never stored) | `done`: there is an achieved date. `delayed`: not done and the target date is **before today (IST)**, with no grace days (AC1). `in_progress`: the earliest not-done milestone in catalogue order, unless it is delayed. `pending`: everything else. On the target day itself the milestone is not delayed yet |
| MS4 | Auto-completion (backlog list) | **Proposal**: the IST date of the first stage move into Proposal Sent or any later stage (`university_stage_history`). **First Application**: the IST date of the university's first `overseas_applications` row (AC2). **First Admission**: the IST date of the first `application_status_history` row with `to_status = 'enrolled'` (the product's "Admitted", `schools.py`) for that university. **Signed** (upc-014, merged on main during Phase 9): the first agreement in status signed / active / renewed, dated the later of its two signatures (AG7 requires both). **Meeting** (upc-009) is reserved for that item and stays manual until then |
| MS5 | How auto-completion is computed | **Derived on read**, not written by hooks. That avoids changing ~8 application write sites, needs no backfill, and stays correct for applications that existed before this item. A manually recorded achieved date wins over the derived one; clearing it falls back to the derived date. An auto-achieved milestone cannot be un-achieved by hand |
| MS6 | Achieved date validation | Not after today (IST) → 422 "The achieved date can't be in the future" (backlog negative scenario). The target date may be any date: a past target simply shows as delayed |
| MS7 | Edge: target date moved after it was delayed ("history kept?") | **Yes, in the audit log**: `university.milestone_updated` carries the kind, the changed field names, the target date `from` / `to` and `was_delayed`. Dates are not sensitive. The table shows the current target only |
| MS8 | Q-10 expected month / quarter | **Derived from the target partnership date**, never stored separately. Month is `YYYY-MM`, quarter is `YYYY-Qn` on **calendar** quarters (Jan–Mar = Q1). The page formats them as "October 2026" and "Q4 2026 (Oct–Dec)". Both are null when there is no target date |
| MS9 | Other §5 targets | `universities` gains `target_partnership_date`, `expected_agreement_date` and `expected_recruitment_start` (Date, nullable), plus `expected_intake` (free text ≤ 80, the `overseas_applications.intake` convention; blank → null). No date ordering rule between them (the source gives none) |
| MS10 | Who edits (backlog "owner/head") | New action `can_edit_timeline` = the stage rule (upc-007 PS5): the primary/backup `partnership_manager`, the `partnership_head` in write scope, and `super_admin`. `overseas_admin` reads only. An inactive university is 409 (upc-003 UM10). A lost university stays editable (recording what happened is harmless) |
| MS11 | Who reads | Every university reader (`require_reader`: partnership roles, overseas_admin, super_admin), as stage history (PS9). Milestones carry dates and labels only |
| MS12 | API shape | `GET /partnership/universities/{id}/milestones`; `PATCH /partnership/universities/{id}/milestones/{kind}` (one milestone per call, so a stale form cannot overwrite other rows); `PATCH /partnership/universities/{id}/expected`. The backlog's "GET/PATCH …/milestones" is refined to a per-kind PATCH |

## 2. Data model — migration `0128_university_milestones`

`universities` gains (guarded, as 0001 builds from models): `target_partnership_date` Date null, `expected_intake` String(80) null,
`expected_agreement_date` Date null, `expected_recruitment_start` Date null. There is no backfill (inventing targets would invent facts).

New table `university_milestones`:
- `id` UUID PK; `university_id` FK universities RESTRICT; `kind` String(40) CHECK ∈ the 13 keys; `target_date` Date null;
  `achieved_on` Date null; `updated_by_user_id` FK users RESTRICT; `created_at` / `updated_at`.
- `uq_university_milestones_kind` (university_id, kind). That unique index also serves the per-university read.

Downgrade refuses while any milestone row exists or any university has an expected value, because dropping them would lose data.

## 3. Backend

- `app/partnership_milestones.py`: `Milestone(key, label, auto)` × 13, `MILESTONE_KEYS`, `AUTO_SOURCES`.
- `services/partnership_milestones.py` (functions only, never commits):
  - `derived_dates(db, uni)`: three small queries for proposal, first application and first admission, as IST dates.
  - `status_of(...)`, `page(db, uni, can_edit)`: `{items, today, can_edit}`. Each item is `{kind, label, target_date, achieved_on,
    achieved_by: manual|auto|null, auto_source: stage|agreement|application|admission|null, status}`.
  - `update(db, user, uni, kind, payload)`: upsert under the university lock, MS6 check, audit MS7, log.
  - `expected_out(uni)`, `update_expected(...)`.
- `api/partnership_milestones.py` (prefix `/partnership/universities`):

| Route | Who | Notes |
|---|---|---|
| `GET /{id}/milestones` | readers | 404 unknown university |
| `PATCH /{id}/milestones/{kind}` | `can_edit_timeline` | `{target_date?, achieved_on?}` (`extra="forbid"`, at least one field, null clears) → the page |
| `PATCH /{id}/expected` | `can_edit_timeline` | `{target_partnership_date?, expected_intake?, expected_agreement_date?, expected_recruitment_start?}` → `UniversityEnvelope` |

- Every write: `_locked(..., "can_edit_timeline")` (FOR UPDATE, 403 logged, 409 inactive) → validation (422) → change, then audit only
  when something changed → one commit → structured log (`university_milestone_updated` / `university_expected_updated`, ids, kind
  and field names only).
- `UniversityDetail` gains `expected` = `{target_partnership_date, expected_month, expected_quarter, expected_intake,
  expected_agreement_date, expected_recruitment_start}`. `permissions` gains `can_edit_timeline`. Both additions are backward
  compatible.

## 4. Frontend

- `lib/partnershipMilestones.ts`: types, `milestonesUrl`, `STATUS_LABEL`, `monthLabel`, `quarterLabel`.
- `components/UniversityTimeline.tsx` (client) is one section, "Partnership timeline", with two parts:
  - **Expected timeline** (§5): facts (target partnership date, expected month, expected quarter, expected intake, expected agreement
    date, expected recruitment start), plus an Edit form for `can_edit_timeline`. Saving calls `router.refresh()`, because the values
    come from the server-rendered university.
  - **Milestones** (§6): a `.table` with Milestone, Target date, Achieved, Status. Status is a text badge (Done / In progress /
    Pending / Delayed), and Delayed also uses the `.status error` badge plus a row highlight, never colour alone. A summary line reads
    "N delayed" when any are delayed. Per row there is an Edit button that opens an inline form (target date, achieved date with
    `max` = today, Save / Cancel; Escape cancels and focus returns to the button). The PATCH response replaces the whole table, since
    statuses depend on each other. An "Auto: …" note marks derived achievements. The table is wrapped for horizontal scroll on narrow
    screens.
  - States: the initial data is server-rendered. Every write uses a double-submit guard, keeps 422 field errors with what was typed,
    shows other failures as `role=alert`, and shows the success notice as a `<p role="status">` **only when shown** (the upc-012
    lesson). Saving shows "Saving…".
- The university page fetches `GET …/milestones` with the other reads and renders the section after "Partnership stage". It is keyed on
  `pipeline.changed_at`, so a stage move into Proposal Sent refreshes the derived Proposal row.

## 5. Acceptance criteria

| AC | Statement | Proven by |
|---|---|---|
| AC1 | A milestone past its target date and not achieved shows as delayed | `test_upc_008_milestones.py`; vitest; e2e |
| AC2 | The first application for the university auto-marks "First Application" | `test_upc_008_milestones.py` |
| P1 | The ABC example: targets recorded per milestone; done / in progress / pending shown | service + e2e |
| N1 | An achieved date in the future → 422 | `test_upc_008_milestones.py`; vitest |
| N2 | Non-owner manager → 403; overseas_admin write → 403 (reads 200); inactive → 409; unknown university 404; unknown kind / extra field / empty body → 422 | `test_upc_008_milestones.py` |
| E1 | A target date moved after it was delayed: the status recomputes and the audit keeps from/to + `was_delayed` | `test_upc_008_milestones.py` |
| E2 | Proposal auto-completes from a stage move into Proposal Sent (or later); Signed from the first signed agreement; First Admission from the first `enrolled` status | `test_upc_008_milestones.py` |
| X1 | Expected targets: edit + read; month/quarter derived (Q-10); blank intake → null; only owner/head/super_admin | `test_upc_008_expected.py` |
| M1 | Migration: CHECK and unique index equal the model; downgrade guard | `test_upc_008_migration.py` |

## 6. Tasks (TDD, in order)

1. Catalogue, model columns and table, migration, parity/downgrade test (`test_upc_008_migration.py`).
2. Schemas, service and milestone routes: status, auto-derivation, access and validation tests first, then the code.
3. Expected route + `detail_out` `expected` + `can_edit_timeline` (`test_upc_008_expected.py`).
4. Frontend lib + `UniversityTimeline` + page wiring, with vitest (`UniversityTimeline.test.tsx`, the detail-page stub).
5. Playwright `upc-008-partnership-timeline.spec.ts`.
6. Docs: DEC-SCOPE-143, API §12BK, RBAC §2.69, DATA_MODEL, SCREEN_CATALOG, backlog status.

## 7. Regression set (lite)

`test_upc_003_*` (detail output, permissions), `test_upc_007_*`, `test_upc_020_*` (detail output), `UniversityDetailPage.test.tsx`,
and the upc-007 / upc-020 e2e specs (shared page).

## 8. Engineering review notes (Phase 3)

- **API:** `{kind}` is a path `Literal` (an unknown kind is a 422). The bodies are `extra="forbid"`, use `model_fields_set` for
  "only what was sent", and an empty body is a 422. A PATCH returns the full milestone page, because the in-progress row depends on the
  others. The calls are idempotent (same body → same state, no audit row when nothing changed). There are no ETags, matching the
  partnership convention; the per-kind PATCH limits lost updates to one row.
- **Transactions:** the university row lock serializes writers, so the select-then-insert upsert cannot race. `uq_university_milestones_kind`
  is the backstop. Reads take no lock.
- **Security:** writes re-check scope after FOR UPDATE (no TOCTOU). There is no free text except `expected_intake` (≤ 80 chars, React
  escapes it, never logged). Audit and logs carry ids, kinds, field names and dates only. CSRF uses the existing cookie + same-origin
  `sendJson` path. No new dependencies, no secrets. There is no IDOR, because every reader may read every university (UM9), and writes
  are scoped.
- **Frontend:** reuses the `.table`, `.badge`, `.form-grid` and `.field` styles, `sendJson` / `fieldErrors` and `useFocusAfterRender`.
  The table has a `<caption class="visually-hidden">`. The Edit buttons have an `aria-label` that includes the milestone name. Date
  inputs are native (keyboard and mobile pickers). The section wraps on mobile.
