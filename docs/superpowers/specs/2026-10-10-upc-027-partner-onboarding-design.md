# upc-027 — Partner onboarding checklist (design + plan)

**Status:** design written 2026-10-10. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". So the item answers OB1–OB13 (§1), including **Q-27**, are **recommended defaults accepted under that
instruction** (`NEEDS_CONFIRMATION` as separate per-question approvals). They are registered that way in `DEC-SCOPE-167`.

**Branch:** `feature/upc-027` (worktree branch `worktree-upc-027`), cut from `origin/main` @ `b7d29bca` (after #223, upc-013).
**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-027, Q-27, Appendix A L938–L968.
**Dependencies:** upc-007 (stage engine, `DEC-SCOPE-126`, `0111_university_pipeline`) and upc-014 (agreements, `DEC-SCOPE-142`,
`0127_university_agreements`) are merged on main (#159, #187). Verified in code: `partnership_pipeline.advance_to`,
`university_agreements.sign`, `partnership_milestones.SIGNED_STATUSES`.
**Source:** `EVID-020` §29 (L938–L968): "After partnership signing: Signed → Partner Onboarding", ten items to track, and the status
flow "Not Started → In Progress → Completed".
**Numbering:** migration `0145_university_onboarding`, `DEC-SCOPE-167`, API §12CI, RBAC §2.93 (renumbered at merge if another item
lands first).
**Gate:** `APPROVAL_GATES.md` GATE-09.

## 0. Discovery (Phase 1)

| Class | Items |
|---|---|
| MUST CHANGE | new `app/partnership_onboarding.py` (catalogue), `models.py` (`UniversityOnboardingItem` + CHECKs), migration `0145`, `schemas.py`, new `services/university_onboarding.py`, new `api/university_onboarding.py`, `main.py` (router), web: new `lib/universityOnboarding.ts`, new `components/UniversityOnboarding.tsx`, `lib/universitiesServer.ts` (loader), `app/partnership/universities/[id]/page.tsx` |
| MAY CHANGE | `api/university_courses.py` and `api/university_course_import.py` (one activation call each, OB8), `tests/components/UniversityDetailPage.test.tsx` (stub the new read), docs (DEC-SCOPE, API, RBAC, DATA_MODEL, SCREEN_CATALOG, backlog status) |
| SHOULD NOT CHANGE | `university_agreements.sign` (sparse rows need no signing hook, OB2), the stage engine (`advance_to` is reused), `partnership_tasks` (its `on_stage_entered` is called, not changed), the milestone tracker |
| HIGH REGRESSION RISK | the shared university page (upc e2e specs use page-wide `role=status` locators: the new notice renders `role=status` only when shown); the course routes (upc-017) gain a call that must be a no-op before signing |

Reusable: `_locked` / `require` / `audit` / `log` (upc-003), `india_today`, `partnership_pipeline.advance_to` + `LOST_CONFLICT`,
`partnership_tasks.on_stage_entered`, `SIGNED_STATUSES`, `SIGNATORY_ROLES` + `/partnership/agreement-signatories` (the owner picker),
web `sendJson` + `fieldErrors`, `SearchableSelect`, `formatCalendarDate`, `useFocusAfterRender`, the `.table` / `.status` / `.badge` styles.

## 1. Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| OB1 | Items | The ten §29 items in source order and wording (Counselor training … First student campaign), as constants in `app/partnership_onboarding.py`, shared by the model CHECK, the migration parity test, the service and the schemas |
| OB2 | **Q-27 (a)** Does onboarding start automatically at Agreement Signed? | **Yes.** Onboarding has started once the university has an agreement whose stored status is signed / active / renewed (`SIGNED_STATUSES`, upc-008 MS4's rule). The catalogue is the template (the upc-008 MS2 idiom): rows are **sparse**, written only when an item is edited, so after signing the page shows the ten items as Not Started without a signing hook or a backfill, and universities signed before this item get their checklist too |
| OB3 | Before signing | GET answers `started: false` with the ten items Not Started (read only). Every PATCH answers **409** `{"code": "onboarding_not_started", "message": "Onboarding starts when an agreement is signed"}` (backlog negative scenario) |
| OB4 | Statuses | `not_started`, `in_progress`, `completed`. Any move is allowed, including back (a mistake can be corrected). `completed_on` is set by the server to today (IST) when an item becomes Completed and cleared when it leaves Completed |
| OB5 | Per-item fields | `status`, `owner_user_id` (an active `partnership_manager` / `partnership_head` / `super_admin`, the agreement signatory set; anything else → 422 on `owner_user_id`), `due_date` (any date; a past one is allowed), `note` (≤ 500, blank → null). Partial PATCH: only the fields sent; `null` clears |
| OB6 | Overall status | Derived, never stored: **Completed** when all ten are completed, **Not Started** when none is in progress or completed, otherwise **In Progress**. `started_on` = the first signed agreement's date (the later of its two signatures, as upc-008 MS4). The response also carries `completed_count` |
| OB7 | "Course database updated can auto-check (upc-017)" | **Derived on read**: the item is Completed when the university has ≥ 1 active course (`overseas_courses.active`), whatever its stored status (`completed_by: "auto"`, no date). A stored Completed is `completed_by: "manual"`. Deactivating the last course falls back to the stored status. The UI shows the automatic state as text and offers no status choice for it |
| OB8 | **Q-27 (b)** Does completing it move the stage to Partner Activated? | **Yes, forward only.** When a write leaves all ten effectively Completed, the university advances to `partner_activated` through `partnership_pipeline.advance_to` (one stage-history `move` row, note "Advanced by onboarding completed"), then `partnership_tasks.on_stage_entered` runs (the upc-020 rule after any stage move). Nothing happens when the university is already at or past Partner Activated, or is marked Lost. The check runs on the onboarding PATCH and on the course writes (create, update, CSV import), because OB7 can complete the last item from the course master. Moving an item back later never moves the stage back |
| OB9 | Lost university | PATCH → 409 `university_lost` (the stage engine's conflict), because a completion can move the stage. GET still works |
| OB10 | Edge: re-signing after a renewal | Onboarding belongs to the university, not to one agreement. A renewal (or any later signing) neither resets nor recreates it: the items keep their statuses |
| OB11 | Who edits / reads | Edit: `can_edit_timeline` (upc-008 MS10 = the stage rule: the university's primary/backup manager, the head in write scope, super_admin); an inactive university → 409. Read: every university reader (`require_reader`: partnership roles, overseas_admin, super_admin). The page's `can_edit` is also false before signing and while Lost |
| OB12 | Audit / logs | `university.onboarding_item_updated` (kind + changed field names + from/to status; never the note text) and `university.onboarding_completed` (from stage) in the write's transaction; structured logs carry ids, kind and field names only |
| OB13 | API shape | `GET /partnership/universities/{id}/onboarding`; `PATCH /partnership/universities/{id}/onboarding/{kind}` (one item per call, like upc-008 MS12, so a stale form cannot overwrite other items). The PATCH returns the whole checklist (overall status depends on every item) plus `stage_advanced: bool` |

## 2. Data model — migration `0145_university_onboarding`

New table `university_onboarding_items` (guarded: 0001 builds a fresh database from the models):
- `id` UUID PK; `university_id` FK universities RESTRICT; `kind` String(40) CHECK ∈ the ten keys; `status` String(20) CHECK ∈ the
  three statuses, default `not_started`; `owner_user_id` FK users RESTRICT null; `due_date` Date null; `note` Text null CHECK ≤ 500;
  `completed_on` Date null; `updated_by_user_id` FK users RESTRICT; `created_at` / `updated_at`.
- CHECK `ck_university_onboarding_items_completed`: `(status = 'completed') = (completed_on IS NOT NULL)`.
- `uq_university_onboarding_items_kind` (university_id, kind), which also serves the per-university read.

No backfill (OB2). `downgrade()` refuses while any row exists (it would drop recorded progress).

## 3. Backend

- `app/partnership_onboarding.py`: `ITEMS` (key, label), `ITEM_KEYS`, `STATUSES`, `STATUS_LABELS`, `AUTO_ITEM = "course_database_updated"`,
  `ACTIVATION_STAGE = "partner_activated"`.
- `services/university_onboarding.py` (functions only, never commits):
  - `_started_on(db, uni_id)`: one scalar query (MS4's signed subquery); `_active_courses(db, uni_id)`: exists query; `_rows`.
  - `page(db, uni, can_edit)` → `{started, started_on, status, completed_count, items, can_edit}`; `can_edit` is false before signing.
  - `update(db, user, uni, kind, payload)` on the locked row: 409 not started; owner validation; upsert under the lock
    (`uq_…_kind` is the backstop); returns the page and the audit metadata (None when nothing changed).
  - `activate_if_complete(db, user, uni)`: OB8; returns whether the stage moved (adds the audit row itself).
- `api/university_onboarding.py`: GET (reader) and PATCH (`_locked(..., "can_edit_timeline", "onboarding")`, lost → 409, update,
  activation, audit, one commit, logs).
- Course routes: `await onboarding.activate_if_complete(db, user, uni)` before their commit (create, update with changes, import).

## 4. Frontend

- `lib/universityOnboarding.ts`: types, `STATUS_LABEL`, `onboardingUrl`, `isOnboardingPage`.
- `components/UniversityOnboarding.tsx` ("use client"): section "Partner onboarding" after Agreements. Not started → a muted line
  "Onboarding starts when an agreement is signed." Started → overall badge + "N of 10 completed" + the started date, then a table
  (Item, Status, Owner, Due date, Completed, Note, Edit). Edit opens one form below the table (status select, owner `SearchableSelect`
  over the signatory lookup, due date, note), Escape/Cancel return focus to the row's button, double submit guarded, refusals kept with
  field errors. The automatic item shows "Completed automatically (the university has active courses)". When the PATCH says
  `stage_advanced`, the page refreshes so the stage panel shows Partner Activated. A failed initial load shows "Unable to load the
  onboarding checklist." + Try again. The notice is `<p role="status">` only when shown.
- `lib/universitiesServer.ts`: `firstOnboarding(id)` never rejects (null → Try again). The page passes it in.

## 5. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | Signing an agreement makes the ten items show as Not Started (overall Not Started, `started: true`, `started_on` = signing date) |
| AC2 | Before any signed agreement, GET shows `started: false`; PATCH → 409 `onboarding_not_started` |
| AC3 | A manager sets status / owner / due date / note on one item; the response carries all ten; the overall status follows OB6; `completed_on` follows OB4 |
| AC4 | All ten Completed → overall Completed and the university moves to Partner Activated (one stage-history row, the stage's auto-task); already at/past it → no move |
| AC5 | Course database updated is Completed automatically when the university has ≥ 1 active course; adding the course that completes the last item activates the partner |
| AC6 | Re-signing (a renewal) keeps the checklist as it was |
| S1 | overseas_admin reads but PATCH → 403; a manager outside the university → 403; inactive → 409; lost → 409; unknown kind → 422; invalid owner → 422; note > 500 → 422; unknown university → 404 |
| S2 | Audit rows carry kinds, field names and statuses, never the note |

## 6. Tasks (TDD, in order)

1. Catalogue + model + migration + migration parity test.
2. Service + routes: GET (not started / started / auto item), PATCH (fields, statuses, 409s, 403s, 422s, audit).
3. Activation (OB8) on PATCH; course hooks (create, update, import).
4. Web lib + component (vitest: not started, started table, edit/save, refusal, auto item, stage refresh, load failure).
5. Page wiring + `UniversityDetailPage.test.tsx` stub; Playwright e2e.
6. Docs: DEC-SCOPE-167, API §12CI, RBAC §2.93, DATA_MODEL, SCREEN_CATALOG, backlog status.

## 7. Regression set (lite)

`test_upc_014_agreements.py`, `test_upc_008_milestones.py`, `test_upc_017_*`, `test_upc_007_*` (stage), the new upc-027 tests; vitest
for the new component and `UniversityDetailPage.test.tsx`; tsc, eslint, ruff on changed files; the web production build.

## 8. Engineering review notes (Phase 3)

- **API (`api-and-interface-design`):** additive only: two new routes and no change to any existing response. The per-kind PATCH uses a
  `Literal` path parameter (unknown kind → 422). Coded 409s (`onboarding_not_started`, `university_lost`) follow the stage engine's
  `{message, code}` shape. `status: null` is refused (`field_validator`, so the 422 `loc` names the field).
- **Transactions / races:** every write locks the university row (FOR UPDATE) before reading items, so two concurrent completions
  serialize and only one advances the stage (`advance_to` is a no-op at or past Partner Activated). `uq_…_kind` backs the upsert. The
  course routes already hold the same lock (`writable_university`). The activation check flushes first, so the caller's pending change
  counts.
- **Security (`security-and-hardening`):** scope comes from `_locked` / `require` (no IDOR: another manager → 403, logged). Owners are
  restricted to active partnership staff (no assigning arbitrary users). The note is stored as data, rendered as React text (escaped;
  QA shows `<script>` literally) and kept out of audit metadata and logs. No commission data is read or returned. CSRF / session
  handling is the existing cookie path (`sendJson`). No new secrets or integrations.
- **Course hooks:** a no-op before signing (one indexed query); an `overseas_admin` course write can complete the checklist and move the
  stage as a system consequence (the stage history records the actor). Responses of the course routes are unchanged.
- **Frontend (`frontend-ui-engineering`):** reuses the page's card / table / `.status` / `.badge` styles, `SearchableSelect` (the
  signatory lookup), `useFocusAfterRender`, and the `p[role=status]`-only-when-shown rule of the shared page.

## 9. Browser QA (Phases 5/6)

Stack: `docker compose -p upc027` (api 18027, web 13027), seeded; headless Chromium via Playwright (scripted exploratory pass +
`tests/e2e/upc-027-partner-onboarding.spec.ts`).

| Check | Result |
|---|---|
| Not started (before signing) | "Onboarding starts when an agreement is signed.", no table |
| Happy path (sign → 10 Not Started → edit → complete last → Partner Activated) | PASS (e2e + QA) |
| Layout desktop 1366 / tablet 820 / mobile 375 | no page side-scroll; table scrolls in `.table-wrap` |
| Keyboard: focus to Status, Escape closes, focus returns | PASS |
| Double submit | one PATCH |
| Refresh / back | persisted; back returns to the page |
| Injected 500 / network abort on save | "Something went wrong." / the app's "request did not complete" text; form kept |
| Other manager / overseas_admin | read only (no Edit); counselor → API 403, page "Access unavailable"; anonymous → 401 |
| XSS in note | rendered as text |
| Console / network | only the injected 500 / abort |

| Issue | Severity | Role / page | Steps | Expected | Actual | Fix |
|---|---|---|---|---|---|---|
| QA27-01 | Medium | head/manager · university page | Complete the last item | "Onboarding completed: … Partner Activated." stays | The section remounted on the refresh (key on `pipeline.changed_at`) and the notice vanished at once | The section is no longer keyed; it takes each refreshed `initial` into state (also refreshes it after a course is added elsewhere). vitest + QA re-run PASS |
| QA27-02 | Low | any · university page at 375 px | Open the page on a phone | Status pills on one line | "Not Started" wrapped and its pill background broke | The table reuses the `milestone-table` tracker styling (nowrap pills, compact padding). Screenshot re-checked |
