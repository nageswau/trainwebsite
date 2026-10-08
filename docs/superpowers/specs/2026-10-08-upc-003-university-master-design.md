# upc-003 — Global University Master (design + plan)

**Status:** design written 2026-10-08. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". So the item answers UM1–UM12 (§1) are **recommended defaults accepted under that instruction**
(`NEEDS_CONFIRMATION` as separate per-question approvals) and are registered that way in `DEC-SCOPE-119`.

**Branch:** `feature/upc-003`, cut from `origin/main` @ `3228bc20` (after #149, upc-001).
**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-003. Dependencies upc-001 (`0103`, `DEC-SCOPE-118`) and
upc-002 (`0101`) are merged on main — verified in code.
**Source:** `EVID-020` §1 (lines 3–33, the 19 field rows), §27 (ownership), the closing note "central source of truth" (U5).
**Numbering:** migration `0104_university_master`, `DEC-SCOPE-119`, API §12AM, RBAC §2.45 (renumbered at merge if another item lands first).
**Gate:** `APPROVAL_GATES.md` GATE-09.

## 1. Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| UM1 | Q-01 code format | **`UNV-000001`** from `university_code_seq` as a **server default** (the `LD-` idiom), so every existing create path (legacy admin create, seed, ~30 test helpers) gets a code with no change. The migration backfills existing rows in `created_at, slug` order. Unique, NOT NULL, never edited |
| UM2 | Q-03 rankings | `university_rankings` rows: `system` ∈ QS / THE / ARWU / Other, `other_name` (required iff Other), `year` 1900–2100, `rank` text ≤ 20 (`"45"` or `"201-250"`). Unique (university, system, other_name, year). Max 10. Sent as a whole list on PATCH (replace) |
| UM3 | Q-04 unowned universities | **Only the head (or `super_admin`) assigns.** Managers cannot claim |
| UM4 | Q-05 backup rights | **Same edit rights as the primary** (§27: both are "assigned"). AC4 is therefore **403** for a non-owner manager (they can read every row, so 404 would be wrong) |
| UM5 | Q-28 visibility | Model/server default `catalogue_visible = true` (existing 11 stay public; legacy admin create unchanged). **Every university created through the master starts `false`.** Publish/unpublish: head, `overseas_admin`, `super_admin` |
| UM6 | Publish rule | 422 unless the university is active, has an overview, and its country is a catalogue country (upc-002 C5: a public university in an internal country would leak it) |
| UM7 | Q-33 `overseas_admin` | Keeps create + edit (all rows) + publish + deactivate; **does not assign managers** (U3: the head reassigns) |
| UM8 | Who creates | `partnership_head`, `overseas_admin`, `super_admin` (U15). Managers do not create |
| UM9 | Head write scope | Unowned rows, or rows whose primary or backup reports to the head (backlog convention). Reads: all five roles read every row |
| UM10 | Deactivate | `active=false` also unpublishes. With applications present → 409 `{code:"has_applications", count}` unless `confirm: true`. `reactivate` restores `active` only (not visibility) |
| UM11 | `stage` | **Not added here.** upc-007 owns the stage engine and adds the column with its CHECK; adding an unvalidated column now would be dead data |
| UM12 | Contact rows / Director / Country manager | upc-006 (backlog). This item carries only "International office" contact text |
| UM13 | Legacy `AdminUniversityCreatePanel` | Replaced in the Universities admin section by a link card to the master (backlog "replaced or redirected"). `POST /admin/universities` and `GET /admin/universities` stay unchanged for API compatibility |
| UM14 | Slug | Generated server-side from the name (`abc-university`); if taken, `abc-university-unv-000012` (the code is unique). Never edited (AC2) |

## 2. Data model — migration `0104_university_master`

`universities` gains (all guarded, since 0001 builds from models):

| Column | Type | Rule |
|---|---|---|
| `university_code` | String(20) | NOT NULL, unique `uq_universities_code`, server default from `university_code_seq` |
| `institution_type` | String(30) | NOT NULL, default `university`; CHECK ∈ university, college, institute, language_school, training_institution |
| `ownership_type` | String(10) | nullable; CHECK ∈ public, private (source "Public/Private") |
| `state_region` | String(120) | nullable |
| `website` | String(300) | nullable; http(s) URL (schema) |
| `course_levels` | JSON | NOT NULL default `[]`; subset of UG, PG, PhD, Diploma, Foundation (schema) |
| `popular_programs` | JSON | NOT NULL default `[]`; ≤ 20 strings ≤ 80 chars (schema) |
| `international_office` | Text | nullable, ≤ 1000 (schema) |
| `existing_relationship` | String(10) | nullable; CHECK ∈ new, existing |
| `primary_manager_user_id` / `backup_manager_user_id` | UUID → users | nullable; indexed; CHECK backup ≠ primary; CHECK backup ⇒ primary |
| `priority` | String(1) | nullable; CHECK ∈ A, B, C; indexed |
| `partnership_potential` | String(10) | nullable; CHECK ∈ high, medium, low |
| `active` | Boolean | NOT NULL default true |
| `catalogue_visible` | Boolean | NOT NULL default true |

New tables: `university_rankings` (id, university_id FK CASCADE, system, other_name, year, rank, created_at; CHECKs; unique index on
`(university_id, system, coalesce(other_name,''), year)`), `university_assignment_history` (id, university_id FK, slot primary/backup,
from_user_id, to_user_id (nullable each), actor_user_id, created_at; append-only).

Downgrade refuses while any ranking/history row or any non-public university exists (dropping the flag would publish it).

## 3. Backend

`services/partnership_universities.py` (functions only; no commit) and `api/partnership_universities.py` (`/partnership/universities`).

- **Access:** `READ_ROLES = {partnership_manager, partnership_head, overseas_admin, super_admin}`; a manager also needs a profile
  (`partnership_context`). Anyone else → 403 "University master access required". `overseas_admin` must be division overseas.
- **Permissions** (per row, returned as `permissions`): `can_edit`, `can_assign`, `can_publish`, `can_deactivate` per UM3–UM10.
  Wrong role → 403 (logged, ids only); wrong state → 409 (e.g. "Reactivate this university first", "Already published").
- **Routes:**

| Route | Who | Notes |
|---|---|---|
| `GET /partnership/universities` | read roles | `q` (name, code, city), `country_id`, `region`, `institution_type`, `priority`, `partnership_potential`, `manager` (`me`/`none`/uuid), `visibility` (public/internal), `include_inactive`; `{items,total,limit,offset}` by name, id; one joined query |
| `POST /partnership/universities` | creators | 201 `{university}`; `catalogue_visible=false`; any country (internal ISO rows included) |
| `GET /partnership/universities/manager-options` | head, super_admin | active managers the caller may assign (`q`, `limit` ≤ 50) |
| `GET /partnership/universities/{id}` | read roles | detail + rankings + manager refs + `application_count` |
| `PATCH /partnership/universities/{id}` | `can_edit` | only sent fields; equal values are not changes; `rankings` replaces the list |
| `POST …/{id}/assign` | `can_assign` | `{primary_manager_user_id, backup_manager_user_id}` (null clears); targets FOR SHARE, active `partnership_manager`, head: direct reports only; history row per changed slot |
| `POST …/{id}/publish` · `/unpublish` | `can_publish` | UM6 |
| `POST …/{id}/deactivate` · `/reactivate` | `can_deactivate` | UM10 |

- Every write: `load` with `FOR UPDATE`, change, `AuditLog` (`university.<action>`, ids + field names only), one commit, then a
  structured log. Unknown id → 404.
- **Public leak closure:** `public_visible()` = `catalogue_visible AND active`, applied to `/public/universities`, `/universities/{slug}`
  (404), `/countries/{slug}` university list, `/overseas-courses`, `/search`, and the student portal's "University catalogue IDs" panel.
  Applications, shortlists and `university_rep` reads are unchanged (FKs untouched, U5).
- `lookups/countries` also admits `partnership_manager` and `partnership_head` (upc-002 C6 deferred this to upc-003).

## 4. Frontend

- `lib/universities.ts`: types, labels, URLs, `countrySearch`, `managerSearch`.
- Pages (server components; `serverApi` → `accessUnavailable` → `PortalShell`, nav by role):
  `/partnership/universities` (filters as a GET form in the URL, table, pager, empty/past-end states, "Add university" for creators),
  `/partnership/universities/new`, `/partnership/universities/[id]` (field `<dl>`, rankings, ownership + assign form, catalogue status +
  actions), `/partnership/universities/[id]/edit`.
- Client components: `UniversityForm` (create/edit; SearchableSelect country; rankings rows; double-submit guard; 422 field errors),
  `UniversityAssignForm`, `UniversityActions` (publish/unpublish/deactivate with inline confirm incl. the application-count warning,
  reactivate).
- Nav: `PARTNERSHIP_MENU` "University Master" → live; `PARTNERSHIP_HEAD_NAV` gains it. WorkflowPanel universities section: link card.

## 5. Acceptance criteria

| AC | Statement | Proven by |
|---|---|---|
| AC1 | All §1 fields (minus contact rows) are captured and editable | `test_upc_003_universities.py`; e2e |
| AC2 | The 11 existing universities keep slugs and stay public; get codes | `test_upc_003_migration.py`, public tests |
| AC3 | A new target is not public (list, detail, country page, courses, search, student panel) | `test_upc_003_public.py`; e2e |
| AC4 | Non-owner manager PATCH → 403; owner (primary/backup) → 200 | universities tests |
| AC5 | Applications and `university_rep` keep working | lite regression set |
| N1 | Invalid type → 422; publish without overview / internal country → 422; primary = backup → 422 | tests |
| E1 | Deactivate with applications → 409 warning; `confirm` proceeds | tests |
| R1 | Head assigns only direct reports; overseas_admin cannot assign; manager cannot create | tests |

## 6. Tasks (TDD, in order)

1. Migration + model + parity test (`test_upc_003_migration.py`).
2. Schemas + service + read routes (list/detail/manager-options) with access tests.
3. Create/PATCH/rankings tests then code.
4. Assign / publish / unpublish / deactivate / reactivate tests then code.
5. Public leak closure tests then code; lookups countries roles.
6. Frontend lib + nav + pages + components with vitest; WorkflowPanel link.
7. Playwright `upc-003-university-master.spec.ts`; docs (DEC-SCOPE-119, API §12AM, RBAC §2.45, DATA_MODEL, SCREEN_CATALOG, backlog).

## 7. Regression set (lite)

OVS-001 / PUB-003 catalogue tests, `test_upc_002_*`, `test_uni_001_*`, agent shortlist + application create tests, `test_upc_001_*`,
`middleware.test.ts`, `navigation.partnership.test.ts`.
