# dtu-001 — Direct Tie-ups university load + agent commission — design

**Date:** 2026-10-13 · **Branch:** `feature/direct-tieups` (from `origin/main` @ `2d0e9a2d`) · **Decision:** `DEC-SCOPE-209` ·
**Migration:** `0157_direct_tieups` · **Feature ID:** `dtu-001` (new; authorised by the owner in-session 2026-10-13)

## 1. Evidence and intent

| Item | Classification |
|---|---|
| `Direct Tie-ups.xlsx` (owner's Downloads, 3 sheets: `Direct Tie-up's`, `iu`, `uc`) — not copied into `docs/sources/` | UNVERIFIED data supplied by the owner |
| Owner answers DT1–DT12 below (in-session 2026-10-13) | EXPLICIT_APPROVAL (owner, in-session) |

**Goal.** Put the owner's direct tie-up universities (and their courses) into the shared university catalogue so every portal that
reads the catalogue shows them, with each university's logo. Record the commission EduSphere pays an agent Master for each
university, visible only to super_admin, the admin roles and agent Masters.

**Success.** Every non-empty Excel cell lands in a named field (a coverage check proves 0 unmapped cells); re-running the load
changes nothing; the agent commission never reaches a role outside the visibility set (server-side stripping, tested per role).

## 2. Owner answers

| # | Question | Answer |
|---|---|---|
| DT1 | Where do the universities go? | The shared catalogue (`universities` + `overseas_courses`), `catalogue_visible = true`, so the public site, counselor, partnership and agent portals all show them |
| DT2 | What is the Excel "Commission"? | What EduSphere (Overseas admin) pays the **agent Master** for a student placed at that university — **not** the university → EduSphere commission of upc-016/upc-017 (U2) |
| DT3 | Where is it stored? | A new **university-level** agent commission (one per university, matching the sheet). The existing course `commission_*` fields (university → EduSphere) are untouched |
| DT4 | Who sees it? | `super_admin`, `it_admin`, `overseas_admin`, and an agent **Master**. Never agency staff, `partnership_manager`, `partnership_head`, `partner`, `accountant`, counselors, students, university reps, or the public |
| DT5 | Who edits it? | `super_admin` and `overseas_admin`. `it_admin` reads only |
| DT6 | "admin" means? | Every admin role: `it_admin` and `overseas_admin` (with `super_admin`) |
| DT7 | Existing university-commission holders | Unchanged: U2 / M3 as today (this feature adds nothing to `partnership_access.COMMISSION_ROLES`) |
| DT8 | Missing data | Rule-based defaults (§4.3), every default listed in a review CSV the owner checks before loading |
| DT9 | Load method | An idempotent, re-runnable script under `apps/api/seed/` plus a committed data file; the owner runs it per environment |
| DT10 | Images | Fetch each university's logo from its official website; store in the web app; show it in the catalogue |
| DT11 | Every Excel column | Must be processed and available in the app (§4.2) |
| DT12 | `iu` universities with no courses | Loaded as universities with their agent commission; no placeholder courses (the placeholder existed only to carry commission, superseded by DT3) |

**Deferred / NEEDS_CONFIRMATION (not built):** per-course agent rates; using the agent rate to auto-compute `agent_commissions`
amounts (AGN-014 stays manual); multi-country universities as several rows (Schiller is loaded once, §4.3).

## 3. Data model — migration `0157_direct_tieups`

`universities` (all nullable, no backfill):

| Column | Type | Note |
|---|---|---|
| `logo_url` | `String(500)` | Site-relative path (`/universities/logos/<slug>.<ext>`) or absolute https URL |
| `campuses` | `JSON` list of strings, server default `'[]'` | Full campus list; `city` keeps the first |
| `fee_structure` | `Text` | Verbatim fee block from the sheet |
| `agent_commission_percent` | `Numeric(5,2)` | |
| `agent_commission_amount` | `Numeric(12,2)` | |
| `agent_commission_currency` | `String(3)` | One of `COMMISSION_CURRENCIES` |
| `agent_commission_note` | `String(300)` | Verbatim source text ("4000GBP flat", "0.13") |

CHECKs (repeated in the migration, kept identical by the migration test, as upc-016):
`percent IS NULL OR amount IS NULL`; `percent IS NULL OR (percent > 0 AND percent <= 100)`;
`(amount IS NULL) = (currency IS NULL) AND (amount IS NULL OR amount > 0)`; currency in the list.

`overseas_courses` (all nullable): `campus String(200)`, `fee_text String(300)` (verbatim fee range), `intake_text String(200)`
(verbatim intake, e.g. "January 2027").

## 4. Data pipeline

### 4.1 Files

- `apps/api/seed/direct_tieups_parse.py` — reads the xlsx (openpyxl; dev-only dependency path, not imported by the app) and
  writes `apps/api/seed/data/direct_tieups.json` + `direct_tieups_review.csv`. Includes the **coverage check**: every non-empty cell
  must map to a destination, else it exits non-zero listing `(sheet, row, column, value)`.
- `apps/api/seed/data/direct_tieups.json` — the reviewed, committed source of truth for the load (the xlsx is not committed).
- `apps/api/seed/direct_tieups.py` — `python -m seed.direct_tieups [--dry-run]`, loads the JSON (§4.4).

### 4.2 Column map (all three sheets)

Main sheet sections by layout: **A** rows 2–34 (16-column course grid), **B** rows 37–62 (bullet cells: D UG titles, F PG titles,
G fee block, H scholarships, I intakes, J deadlines, K link), **C** rows 64–78 (per-row grid: D UG course, E UG fee, F PG course,
G PG fee, H scholarship, I intakes, J deadline, K link). Header rows 1, 36, 44, 50 are skipped.

| Excel column | Destination |
|---|---|
| University name (all sheets) | `universities.name`; matched to an existing row by `country_id` + `name_key` (upc-004 duplicate key) |
| Destination & campus | country → `country_id`; first campus → `city`; every campus → `campuses` |
| Commission | `agent_commission_percent` (fraction × 100) **or** `agent_commission_amount` + `currency` ("flat" amounts); raw text → `agent_commission_note` |
| UG / PG course title (grid cell or one per `•` bullet) | one `overseas_courses` row; `level` = UG / PG from the column |
| Course campus | `overseas_courses.campus` |
| Course tuition fee (range) | `tuition_amount` + `tuition_currency` = low end; verbatim → `fee_text` |
| Fee structure block (layout B) | its `UG:` line → every UG course, its `PG:` line → every PG course (as above); whole block → `universities.fee_structure` |
| Available intake / Intakes | month codes → `intakes`; verbatim → `intake_text` |
| Scholarship (course cell or bullet block) | one `scholarships` row per distinct text (`title`, `amount` text, `university_id`, `eligibility` "See university", country) linked to the course(s) via `scholarship_ids`; also each text in `universities.scholarships` |
| Application deadlines | `universities.deadlines` (one string per bullet) |
| University link / Application link / Website link | `universities.website` when it is a URL; a non-URL label goes into `overview` as "Application portal: …" |
| Uni-level "Tuition Fee" column (O) | empty in the sheet; the coverage check fails if it ever holds a value |
| `iu`: name, destination, commission | as above (no courses) |
| `uc`: name | as above, country UK (§4.3) |

### 4.3 Defaults and inferences (each flagged in the review CSV)

- `category`: keyword rule on the title (Business/Management/MBA → Business; Computing/Computer/IT/Data/AI → Computing & IT;
  Finance/Accounting/Banking → Finance; Engineering/Maritime/Marine → Engineering; Health/Nursing/Physio/Chiropractic → Health;
  Design/Media/Film/Animation/Art → Creative Arts; Law → Law; Hospitality/Tourism → Hospitality); otherwise `General`.
- `duration`: parsed from the fee text when present ("PG (12 Mo)" → "12 months"), otherwise `Not specified`.
- `city`: first named campus; otherwise the country's capital.
- `institution_type` (from `INSTITUTION_TYPES`): `university` when the name contains "University"; `institute` for "Institute",
  "Institutions", "School", "College", "Ecole", "Pathway" names (BSBI, ICN, GBS ×3, MLA College, EMA, APAC, OIEG, BIGS, Walbrook);
  otherwise `university`.
- Country inference: "Dubai" → AE; Schiller → US (other countries named in `overview`); BSBI → DE; `uc` sheet → GB.
- Southwales column N ("Intakes", placed after the PG columns) applies to **PG** courses; UG uses column F.
- BIGS scholarship cell `0.25` → "25% tuition scholarship".

### 4.4 Loader rules

- One transaction for the whole run; `--dry-run` rolls back and prints the created/matched/skipped counts.
- University: matched by `country_id` + `name_key`. **New** → created with `catalogue_visible = true`, `active = true`.
  **Existing** → only empty fields are filled (logo, campuses, fee_structure, website, deadlines, scholarships, agent commission);
  never overwrites a non-empty value. An agent commission already set and different is reported, not changed.
- Course: matched by the course master's duplicate key (upc-017 CO12) within the university; new → created through the same
  `CourseIn` + `check_rules` path as a manual add; existing → skipped.
- Scholarship: matched by `university_id` + lower(title).
- Every created/updated university writes an `AuditLog` row `university.direct_tieup_load` (ids and field names only).
- A second run reports 0 created, 0 updated.

### 4.5 Logos

- Source: the university's official site (`website`, else a web search for the official domain): the site's logo image, else
  `og:image`, else `apple-touch-icon`. One file per university at `apps/web/public/universities/logos/<slug>.<png|svg|jpg|webp>`,
  ≤ 200 KB, committed. Recorded in the JSON as `logo_url`.
- No logo found → `logo_url` null; the UI renders a monogram tile (initials) instead.
- Logos are trademarks of their owners, used to identify partner institutions; any owner asking for removal is handled by deleting
  the file and nulling `logo_url`.

## 5. Access (RBAC) — `DEC-SCOPE-209`

New `app/services/agent_commission_access.py`:
- `AGENT_COMMISSION_VIEW_ROLES = {"super_admin", "it_admin", "overseas_admin"}`; `AGENT_COMMISSION_EDIT_ROLES = {"super_admin", "overseas_admin"}`.
- `can_view_agent_commission(user)` = view role **or** (`user.role == "agent"` and not `is_agent_staff(user)` and the agency passes
  `agent_denial_reason`).
- `strip_agent_commission(user, payload)` removes `agent_commission` from every university payload for anyone else.

Every response that serialises a university passes through it: public `/universities*` (unauthenticated → always stripped),
partnership master/detail, counselor and university-rep views, agent shortlist/application pickers, and the new agent section.
Writes of `agent_commission` by a non-edit role → `403`; `it_admin` is view-only.
`partnership_access.COMMISSION_ROLES` and `strip_commission` are unchanged (DT7).

## 6. API

- `UniversityOut` / `UniversityRow` / `UniversityDetail` gain `logo_url`, `campuses`, `fee_structure` (public) and
  `agent_commission: {percent, amount, currency, note} | null` (restricted, §5).
- Course outputs gain `campus`, `fee_text`, `intake_text` (public).
- `PATCH` on the university master accepts `logo_url`, `campuses`, `fee_structure` (existing editors) and `agent_commission`
  (edit roles only); course create/update accept the three course fields.
- New `GET /api/v1/workflows/overseas/agent/crm/partner-universities` (agent Master and staff, through the agent CRM `_gate`;
  `q`, `country`, `limit` ≤ 100, `offset`): catalogue universities that are `active` and `catalogue_visible`, with logo, country,
  campuses, course count; `agent_commission` only for a Master. `GET …/partner-universities/{id}`: detail with courses,
  scholarships, deadlines, fee structure; 404 for an inactive or hidden university.
- API changelog section `12CC+` (next free on main at build time).

## 7. UI

- Public catalogue cards, public university detail, counselor university pages, partnership university detail, the agent
  shortlist / application university pickers: logo (or monogram); detail pages show campuses, fee structure, deadlines,
  scholarships, and per course: campus, fee text, intake text.
- Agent portal: new nav entry **Partner Universities** (`/overseas/agent/partner-universities`) — searchable list + detail. A
  Master sees an "Agent commission" column/field; staff see the same page without it.
- University master edit form: logo URL, campuses, fee structure for existing editors; an "Agent commission" group (% or amount +
  currency, note) shown only to super_admin / overseas_admin; read-only display for it_admin.

## 8. Tests (lite set; the owner runs the full backend suite on their own cadence)

- `test_dtu_001_parse.py`: the coverage check on a fixture copy of the sheet's shapes (one per layout) → 0 unmapped; an injected
  unknown cell fails; commission parsing (0.13 → 13.00 %, "4000GBP flat" → 4000 GBP, "1,50,000 INR flat" → 150000 INR); fee low end.
- `test_dtu_001_load.py`: creates; second run is a no-op; existing university only gets empty fields filled; course duplicate skipped.
- `test_dtu_001_access.py`: role matrix for every university-serialising route — agent commission present for super_admin,
  it_admin, overseas_admin, agent Master; absent for agent staff, partnership_manager, partnership_head, partner, accountant,
  counselor, student, university_rep, public. PATCH: 403 for it_admin / partnership roles, 200 for overseas_admin / super_admin.
- `test_dtu_001_migration.py`: columns + CHECKs identical between model and migration.
- Regression: `test_upc_016*`, `test_upc_017*` (university commission unaffected), public university tests, agent shortlist tests,
  the route-inventory test (row per new route).
- Web (vitest): logo/monogram rendering; agent commission shown to Master, hidden for staff; form group visibility per role.
- Playwright: agent Master and staff on Partner Universities.

## 9. Docs

`DEC-SCOPE-209` in `PRODUCT_DECISION_REGISTER.md`; RBAC matrix row for agent commission; API changelog section; backlog/status
entry for `dtu-001`; this spec.

## 10. Rollout

1. Owner reviews `direct_tieups_review.csv`.
2. `alembic upgrade head`, then `python -m seed.direct_tieups --dry-run`, then without `--dry-run`, per environment.
3. Logos ship with the web build.
