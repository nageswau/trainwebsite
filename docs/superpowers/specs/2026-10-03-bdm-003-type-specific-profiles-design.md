# bdm-003 — Type-specific organization profiles (Agent / School / College) — Design

**ID note (merge of `main` @ `65a8ece`, 2026-10-03):** written as `DEC-SCOPE-063` and migration `0068_bdm_org_profiles`; bdm-010 (`DEC-SCOPE-063`, `0068_bdm_trips`, PR #53) reached `main` first, so bdm-003 became `DEC-SCOPE-064`, and after AGN-022 (`DEC-SCOPE-064`, PR #54, merged from `main` @ `39c119b`) it is **`DEC-SCOPE-065`** and **`0069_bdm_org_profiles`** (after `0068_bdm_trips`). Mentions of `063` / `0068_bdm_org_profiles` below mean this decision / migration.

**Status:** design approved in-session on 2026-10-03, in five sections: (1) data model + migration, (2) API, (3) transactions, races, authorization and errors, (4) frontend, (5) acceptance criteria, tests, risks and docs. Approach A chosen (§2). No code has been written.

**Revision 2 (2026-10-03):** reviewed against the `api-and-interface-design`, `frontend-ui-engineering` and `security-and-hardening` skills; findings applied inline and listed in §12. One new owner decision (P14, line breaks). No earlier decision changed.

**Branch:** `feature/bdm-003-type-specific-profile-fields`, cut from `main` @ `3bde879` (after AGN-018 #52).

**Backlog:** `docs/delivery/BDM_CRM_BACKLOG.md` §4 bdm-003 (L289).

**Source:** `functionalities/edusphere_markdown/BDM Functionalities.md` (`EVID-016`, `DERIVED_BLUEPRINT`): Agent §B (L561–613), School §B (L827–871), College §B (L1066–1108).

**Builds on:** bdm-002 (`DEC-SCOPE-060`, migration `0066_bdm_organizations`): table `bdm_organizations`, contacts with role tags, scope, permissions, PATCH and audit rules. Nothing in bdm-002's security spine changes.

**Decision record:** **`DEC-SCOPE-063`** (next free on `main` @ `3bde879`; recheck before building and before merge), written in this change. It holds the P1–P13 answers in §3.

**Gate:** `APPROVAL_GATES.md` GATE-09. Coding starts only after the implementation plan is approved.

**Migration:** `0068_bdm_org_profiles` (next free on `main` @ `3bde879`; the later-merging branch renumbers).

---

## 1. Scope

The source's per-type field lists, split by owner (the backlog traceability table, verified against the source):

| Source field | Owner | bdm-003 does |
|---|---|---|
| Agent: Country, Territory, Source, Number of Staff | **bdm-003** | New typed columns |
| School: Board, School Type, Grades | **bdm-003** | New typed columns |
| College: University/Affiliation, College Type, Courses | **bdm-003** | New typed columns |
| Address (all three types) | **bdm-003** (P3) | New common column — bdm-002 never added it, though the backlog lists it under bdm-002 |
| Owner, Principal, Management Contact, Counselor, Dean, HOD, Placement Officer | bdm-002 | Already contacts with a role tag (`BDM_CONTACT_ROLES`); the form now suggests the type's roles first (P8) |
| Agency/School/College Name, ID, City, State, Phone/Mobile, Email, Website, Student Strength, Assigned BDM, Existing Partner, Contact Person | bdm-002 | Unchanged |
| Agent Commission | bdm-019 / ang-014 | Read-only placeholder "Available after onboarding"; never accepted (P10) |
| Agent Students, Applications, Enrollments, Master Login; live staff count | bdm-019 / bdm-022 | Not stored, not accepted |
| Agreement, MoU, Contract, Renewal Date, MoU Status | bdm-005 | Not built (P11) |
| Status | bdm-004 | Not built |
| Last Meeting, Next Follow-up | bdm-006 / bdm-008 | Unchanged (`null`, "—") |

**Out of scope:** Courses Interested as a `programs` multi-select (P9: deferred again, logged as a follow-up; stays free text); any link to `schools` (bdm-018) or Agent Organizations (bdm-019); restricting contact roles per type (P8).

---

## 2. Approaches considered

The storage shape is decided (P2: typed nullable columns + a nested `profile` object in the API). The question was where the "field belongs to another type" rule lives.

- **A. One profile schema + one service check (chosen).** `BdmOrgProfileIn` holds all ten fields, optional, `extra="forbid"` (rejects unknown and live-metric keys; validates enums, bounds, shape). One service function, `check_profile(effective_org_type, sent, stored)`, runs after the row lock in both create and PATCH and raises the per-field 422. On PATCH `org_type` is often not sent, so only the route knows the effective type; one rule in one place serves both routes.
- **B. Three per-type models, discriminated.** Clean on create, but a PATCH without `org_type` must re-parse by hand: two validation paths for one rule. Rejected.
- **C. Flat payload + a `model_validator`.** Contradicts P2, and model-level errors have `loc=["body"]`, so the form cannot place them on a field. Rejected.

Database backstop for A: one CHECK per type group (§4.2).

---

## 3. Decisions (owner, in-session, 2026-10-03, `EXPLICIT_APPROVAL`)

| # | Question | Answer |
|---|---|---|
| P1 | Which field picks the profile? | `org_type`. agent → Agent; school → School; college **and** university → College; corporate, training_institute, other → common fields only |
| P2 | Storage | Typed nullable columns on `bdm_organizations` with CHECKs; the API exposes them as a nested `profile` object validated per type |
| P3 | Address gap | Add a common nullable `address` column for every type in bdm-003 |
| P4 | `org_type` change after type data is saved | 409 while any field of the old group is set; the BDM clears them first. No "clear" flag; type is not locked |
| P5 | Enumerations | Board = ENH-009's `CBSE, ICSE, State, IB, Other`; School Type = Private, Government, Aided, International, Other; College Type = Engineering, Arts & Science, Management, Medical, Polytechnic, Other; Source = Referral, Website, Event, Cold call, Walk-in, Other |
| P6 | Country, Territory | Free text |
| P7 | Grades | A from–to range; values Nursery, LKG, UKG, 1–12, stored as −2, −1, 0, 1…12; lowest ≤ highest |
| P8 | Contact roles per type | Not restricted (no bdm-002 regression); the form lists the type's roles first |
| P9 | Courses Interested → `programs` multi-select | Deferred again; stays free text; logged as a follow-up |
| P10 | Commission / live staff count | Commission is a read-only placeholder "Available after onboarding", in no request schema; Number of Staff is a BDM-entered whole number |
| P11 | Agreement, MoU, Contract, Renewal Date | Stay with bdm-005; no columns here |
| P12 | College Affiliation, Courses | Both free text |
| P13 | Approach | A (§2) |
| P14 | Line breaks in multi-line fields (Revision 2) | Address, Courses **and bdm-002's Courses Interested** accept line breaks (`\r\n` → `\n`); every other control character is still rejected. Fixes the existing bdm-002 bug where Enter in the Courses Interested textarea gave a 422. Only loosens validation; no stored data changes |

---

## 4. Data model — migration `0068_bdm_org_profiles` (additive only)

### 4.1 New columns on `bdm_organizations` (all nullable)

| Column | Type | Group | Constraint |
|---|---|---|---|
| `address` | varchar(500) | all | — |
| `country` | varchar(120) | agent | — |
| `territory` | varchar(120) | agent | — |
| `source` | varchar(20) | agent | `ck_bdm_organizations_source`: `referral, website, event, cold_call, walk_in, other` |
| `staff_count` | integer | agent | `ck_bdm_organizations_staff_count`: 0–100 000 |
| `board` | varchar(10) | school | `ck_bdm_organizations_board`: `CBSE, ICSE, State, IB, Other` |
| `school_type` | varchar(20) | school | `ck_bdm_organizations_school_type`: `private, government, aided, international, other` |
| `grade_from` | smallint | school | `ck_bdm_organizations_grades`: each −2…12; `grade_from <= grade_to` when both set |
| `grade_to` | smallint | school | (same CHECK) |
| `affiliation` | varchar(200) | college | — |
| `college_type` | varchar(20) | college | `ck_bdm_organizations_college_type`: `engineering, arts_science, management, medical, polytechnic, other` |
| `courses` | varchar(1000) | college | — |

### 4.2 Type-group backstops

- `ck_bdm_organizations_agent_profile`: `org_type = 'agent' OR (country, territory, source, staff_count all NULL)`
- `ck_bdm_organizations_school_profile`: `org_type = 'school' OR (board, school_type, grade_from, grade_to all NULL)`
- `ck_bdm_organizations_college_profile`: `org_type IN ('college', 'university') OR (affiliation, college_type, courses all NULL)`

Existing rows have NULL in every new column, so every CHECK holds without a data change. No index is added (the list is already narrowed by `bdm_type`; the performance impact is negligible).

### 4.3 Migration style (as `0061` / `0066`)

- `0001` builds a fresh database from the current models, so each column and constraint is added only when missing (per-column guard).
- No row is read or written by `upgrade()`. Adding a nullable column does not rewrite the table; the CHECKs scan a small table once.
- `downgrade()` refuses while any of the twelve columns holds a value (entered data is not dropped silently); otherwise it drops the constraints, then the columns. bdm-002's round-trip test (no profile data) still passes, and its "downgrade refuses while organizations exist" assertion still comes from `0066`.

### 4.4 Model (`app/models.py`)

The same columns and CHECKs on `BdmOrganization`. New tuples next to `BDM_ORG_TYPES`: `BDM_ORG_SOURCES`, `BDM_SCHOOL_BOARDS`, `BDM_SCHOOL_TYPES`, `BDM_COLLEGE_TYPES`, plus `BDM_GRADE_MIN = -2`, `BDM_GRADE_MAX = 12`. The group map `BDM_PROFILE_GROUP = {"agent": "agent", "school": "school", "college": "college", "university": "college"}` and `BDM_PROFILE_FIELDS = {group: (columns…)}` are the single source of truth, imported by schemas, service and migration test.

---

## 5. Backend

### 5.1 Schemas (`schemas.py`, inside the bdm-002 block; reuse its text rules)

- `BdmOrgProfileIn` (`extra="forbid"`; every field optional; inside it `null` = clear):
  `country`, `territory` (text ≤ 120, bdm-002 text rule); `source` (Literal); `staff_count` (StrictInt 0–100 000, plain message "Number of staff must be a whole number from 0 to 100,000"); `board`, `school_type`, `college_type` (Literal); `grade_from`, `grade_to` (StrictInt −2…12, plain message); `affiliation` (text ≤ 200); `courses` (text ≤ 1000).
  Unknown keys — including `commission`, `students`, `applications`, `enrollments`, `master_login` — are `extra_forbidden` (AC4).
- `BdmOrganizationCreate` gains `address` (text ≤ 500, optional) and `profile: BdmOrgProfileIn | None = None`.
- `BdmOrganizationUpdate` gains `address` and `profile: BdmOrgProfileIn = None` (omitted = unchanged; a sent `null` fails the non-nullable type → 422, bdm-001's PATCH idiom).
- `BDM_ORG_FIELDS` gains `address`. `BDM_ORG_LABELS` gains labels for the new text fields.
- **Multi-line text rule (P14):** a `_bdm_org_multiline(max_length)` variant of `_bdm_org_optional`: `\r\n`/`\r` → `\n` **before** the length check, then the bdm-002 rule with `\n` allowed (`[\x00-\x09\x0b-\x1f\x7f]` rejected). Used by `address`, `courses` and `courses_interested`; every single-line field keeps the existing rule.
- **Contract documentation:** every profile field carries a `Field(description=…)` in the OpenAPI schema; the grade codes (`-2` Nursery, `-1` LKG, `0` UKG, `1…12`) and the enum meanings are documented there, and the response union is discriminated on `kind`.
- **Value casing:** `board` keeps ENH-009's exact values (`CBSE`, `State` …) so bdm-018 can copy it onto `schools.board` unchanged; every other enum is lower snake case like `org_type`. Deliberate, documented.
- Output: `BdmAgentProfileOut {kind: "agent", country, territory, source, staff_count}`, `BdmSchoolProfileOut {kind: "school", board, school_type, grade_from, grade_to}`, `BdmCollegeProfileOut {kind: "college", affiliation, college_type, courses}`; `BdmOrganizationOut` gains `address: str | None` and `profile: <discriminated union on kind> | None` (`None` for corporate / training_institute / other). `BdmOrganizationRow` is unchanged. Commission is not in the response.

### 5.2 Service (`services/bdm_organizations.py`; never commits)

- `check_profile(org_type: str, sent: dict, stored: BdmOrganization | None) -> None` — collects every error, then raises one `RequestValidationError` (the `services/agent_visa.py` precedent, so the body is FastAPI's normal 422 list):
  - each key in `sent` outside `BDM_PROFILE_FIELDS[group(org_type)]` (all keys, for a common-only type) → `loc=("body", "profile", key)`, msg `"<Label> is not a field for <Type> organizations"`. The rule is on key **presence**, not value: `{"board": null}` on a College is also a 422 (one simple rule; the UI never sends another group's keys). `profile: {}` is valid and changes nothing;
  - grade range on the effective values (stored, overlaid by sent) → `loc=("body", "profile", "grade_to")`, msg `"Lowest grade can't be above the highest grade"`.
- `check_type_change(org: BdmOrganization, new_type: str) -> None` — when `group(new_type) != group(org.org_type)` and any column of the old group is not NULL → `HTTPException(409, {"message": "Clear the <School> details before changing the type", "code": "profile_not_empty", "fields": [<the set column names>]})` — a structured body like bdm-002's `possible_duplicate`, so the form can name the fields without parsing text. College ↔ University is the same group, so always allowed.
- `profile_out(org) -> dict | None`; `organization_out` adds `address` and `profile`.

### 5.3 Routes (`app/api/bdm_organizations.py`)

- **Create:** after `bdm_context`, `check_profile(payload.org_type, sent, None)` **before** the duplicate check and `next_code` (a rejected profile consumes no code). The profile is flattened into the column kwargs. The audit's `fields` list also names the profile keys that were set.
- **PATCH:** `load_scoped(lock=True)` → `require(can_edit)` → `check_profile(effective_type, profile_sent, org)` → if `org_type` changes, `check_type_change` → the existing duplicate check → the profile changes merge into the existing `changed` diff (columns), so a no-op writes no audit row and no `updated_at` bump.
- **List:** new optional query params, ANDed with `caller_scope` (they only narrow): `board: Literal[...] | None` (exact; unknown → 422), `affiliation: str | None = Query(None, max_length=200)` and `territory: str | None = Query(None, max_length=120)` (contains, via the existing `like_pattern` + `_matching`, which escape `%`, `_`, `\` and bind parameters). Filters are independent: a combination that cannot match (e.g. `org_type=college&board=CBSE`) returns an empty page, not a 422.
- **Response shape is unconditional:** every detail response has the `address` and `profile` keys (`null` when not set / not applicable); no key appears or disappears by type.
- **Retries:** unchanged. Create is still protected by the duplicate warning (bdm-002's "retry after a lost response is a duplicate" test); a repeated PATCH is a no-op by value.

### 5.4 Transactions and races

- One transaction per write: scope → lock → checks → change → audit → one `commit()` in the route (unchanged).
- **Type change vs profile edit:** both lock the organization row `FOR UPDATE`; the second re-checks against the committed type (`load_scoped` uses `populate_existing`) → 422. The group CHECKs back this up.
- **Two conflicting grade edits** (`grade_from=8` vs `grade_to=6`): serialized; the second sees the first's stored value → 422; `ck_bdm_organizations_grades` backs it up.
- **Concurrent creates:** independent rows; no new conflict.

### 5.5 Authorization

Unchanged from bdm-002: profile fields are written only through create and PATCH, so only the assigned BDM (or `super_admin`) edits; managers read; out of scope → 404; archived → 409. No new role, route or permission flag.

### 5.6 Errors

| Status | New cases |
|---|---|
| 409 | Type change across groups while the old group has data |
| 422 | Key of another type; unknown / live-metric key in `profile`; enum value not in the list; grade or staff count out of range / not a whole number; lowest grade above highest; `profile: null` on PATCH; unknown `board` filter |

Order as bdm-002: 404 (scope) → 403 (role) → 409 (archived) → 422 (profile) → 409 (type change) → 409 (duplicate). A body that fails the **schema** (bad enum, unknown key) is a 422 before the route runs — existing FastAPI behaviour for every bdm-002 route; it is the same for any id, so it reveals nothing about existence. The type-dependent 422 and the 409 `fields` list come only after scope and the edit permission.

### 5.7 Audit and logs

Same transaction as the write (fail closed). Field **names** only, never values. A refused type change logs `bdm_org_type_change_refused` with ids only.

---

## 6. Frontend

### 6.1 `lib/bdmOrganizations.ts` (additive)

Enum arrays + label maps (`SOURCES`, `BOARDS`, `SCHOOL_TYPES`, `COLLEGE_TYPES`, `GRADES` with `-2 → Nursery`, `-1 → LKG`, `0 → UKG`); `profileGroup(orgType)`; `PROFILE_FIELDS`; `SUGGESTED_ROLES` per group; `gradeRange(from, to)` text ("LKG–12", "From 6", "Up to 10", "—"); types `OrgProfile` (union on `kind`), and `address` / `profile` on `Organization`.

### 6.2 New `components/BdmOrganizationProfileFields.tsx`

One fieldset with a visible legend ("Agent details" / "School details" / "College details"); renders nothing for common-only types. Same markup as `BdmOrganizationFields` (visible labels, `aria-invalid`, error tied by `aria-describedby`, "Choose…" empty option = not set).

The module also owns the profile's form logic, as `BdmContactFields` owns `blankContact` — `profileValuesOf(org)`, `profilePayload(group, values, original?)` (create: non-empty; edit: changed), `profileErrors(group, values)` (the grade-order convenience check) — so `BdmOrganizationForm` (222 lines today) stays small and these are unit-tested on their own.
- Agent: Country, Territory, Source (select), Number of staff (number, `inputMode="numeric"`); then a muted read-only line "Commission: Available after onboarding" — plain text, never a disabled input (a disabled input looks editable and is skipped inconsistently by screen readers).
- School: Board, School type (selects), Lowest grade, Highest grade (selects).
- College/University: Affiliation, College type (select), Courses (textarea).

### 6.3 Changed components

- `BdmOrganizationFields.tsx`: Address textarea after State; the Type select gains help text "The details section below changes with the type." tied by `aria-describedby`, so a screen-reader user knows new fields follow it in tab order.
- `BdmOrganizationForm.tsx`:
  - `profile` state holds every group's values; only the current group's fields are sent (create: non-empty; edit: changed).
  - Edit + type change into another group while the original group has data → inline error under Type "Clear the School details (Board, Grades) before changing the type", focus the Type select, save blocked. The server's 409 (`code: "profile_not_empty"`) is the authority: when it arrives it is shown in the same place, naming its `fields` by label.
  - Client convenience check: lowest grade above highest → field error.
  - `serverErrors` also maps `["body", "profile", key]` onto the profile field.
  - Dirty / leave guard include `address` and `profile`.
- `BdmContactFields.tsx`: optional `orgType` prop orders the type's suggested roles first; every role stays selectable.
- `BdmOrganizationContacts.tsx`: passes `org.org_type` to the contact fields.
- `BdmOrganizationDetail.tsx`: Address row in the common list. The type's section is its own `<h4>` ("School details") + `<dl>` inside the same Details card (hierarchy: card h3 → section h4). Values: "—" when empty; grades via `gradeRange`; Address, Courses and Courses interested keep line breaks (`whiteSpace: "pre-line"`, text nodes only). When every value of the section is empty it shows one muted line, "No school details yet." (plus "Use Edit to add them." when `can_edit`). Agent: "Commission — Available after onboarding". A value the UI has no label for (a future enum) shows as the raw value instead of breaking.
- `BdmOrganizationsPanel.tsx`: Board select when Type = School (applies on change, like Type); Affiliation text when Type = College or University and Territory text when Type = Agent (in the existing draft search form, applied with Search, like City); URL-synced; changing Type drops a filter that no longer applies; "Clear filters" clears them; the existing filtered-empty state is reused.

### 6.4 States, responsive, accessibility

Loading, empty ("no organizations match"), error and paging states of the panel and detail are reused unchanged. The form's busy / field-error / form-error states cover the new fields. Single-column `.field` grid, 44 px targets, no horizontal scroll at 320 px. All controls are native (`select`, `input`, `textarea`), so keyboard support is built in; focus moves to the first error on a failed save (existing `useFocusAfterRender`). Perceived performance: no new request — the value lists are static on the client, so switching type renders instantly.

**Not touched:** pages and routes, navigation, Reassign, manager pages.

---

## 7. Acceptance criteria

1. **AC1** Each type's form shows exactly its source fields: Agent = Country, Territory, Source, Number of staff (+ Commission placeholder); School = Board, School type, Grades range; College/University = Affiliation, College type, Courses; Corporate / Training Institute / Other = common only. Address for all. Named people are saved as contacts tagged with their role.
2. **AC2** A field of another type → 422 at `profile.<key>`, on create and PATCH (including a PATCH that changes `org_type`).
3. **AC3** Enumerated fields reject unknown values (Source, Board, School type, College type, grades outside −2…12, unknown `board` filter) with 422; the DB CHECKs reject them on direct insert.
4. **AC4** Live agent metrics are never writable: `commission`, `students`, `applications`, `enrollments`, `master_login` → 422 in `profile` or top level; no input exists for them.
5. **AC5** A type change across groups is 409 while the old group has data, and succeeds once cleared; College ↔ University always succeeds.
6. **AC6** Lowest grade above highest → 422, checked on the stored values overlaid by the sent ones.
7. **AC7** Backwards compatible: a bdm-002-style request behaves identically; the list row shape is unchanged.
8. **AC8** The Board / Affiliation / Territory filters only narrow the caller's scope.
9. **AC9** The migration is additive: existing rows kept, downgrade refuses while profile data exists, single head.
10. **AC10** (P14) Address, Courses and Courses interested accept line breaks and display them; any other control character is still a 422.

---

## 8. Tests (written before the code)

### 8.1 Backend (`apps/api/tests`; shared DB, uuid-unique data via `bdm002_helpers`)

- `test_bdm_003_migration.py` — chains after `0067_audit_entity_index`, single head; model columns/CHECKs match the migration; direct-SQL CHECK violations (each enum, staff range, grade range and order, each group backstop); round trip keeps existing rows; downgrade refuses while profile data exists.
- `test_bdm_003_schemas.py` — enums, bounds, strict whole numbers, plain messages, unknown and live-metric keys `extra_forbidden`, `profile: null` on Update, `address` length; multi-line rule (`\n` kept, `\r\n` → `\n`, length counted after, `\x00`/`\t`/`\x1b` rejected, single-line fields still reject `\n`); `courses_interested` with a line break now accepted (P14).
- Revision-2 cases (in `test_bdm_003_profiles.py`): 409 body is `{message, code: "profile_not_empty", fields}`; `{"board": null}` on a College → 422 (presence rule); `profile: {}` is a no-op (no audit); impossible filter combination → 200 empty page; `%`/`_` in `territory` match literally; detail always has `address` and `profile` keys; caplog: refused type change and profile writes log ids and field names only — no address, country, territory, affiliation or courses text.
- `test_bdm_003_profiles.py` — AC1–AC8 through the API: the backlog's positives (school CBSE grades 6–12; agent with country, territory, source); a college with `board` → 422; a contact with a bad email → 422; corporate with any profile key → 422; PATCH partial / clear; type change 409 then success after clearing; college ↔ university; rejected create consumes no code; audit field names, no values; no-op PATCH writes no audit; manager / non-assigned BDM → 403; out of scope → 404; archived → 409; filters ANDed with scope; detail `profile` shape per type and `null` for common-only.
- Races (in `test_bdm_003_profiles.py`): concurrent type change vs profile edit → exactly one outcome, no group-CHECK violation; concurrent `grade_from=8` vs `grade_to=6` → one succeeds, one 422.
- Deliberate edit: `test_bdm_002_migration.py::test_models_match_the_migration` asserts bdm-002's columns are a subset (not the exact set).

### 8.2 Web unit (vitest)

`tests/lib/bdmOrganizations.test.ts` (`profileGroup`, labels incl. unknown-value fallback, `gradeRange`); new `BdmOrganizationProfileFields.test.tsx` (field set per type, legend, commission is text not an input, `profileValuesOf` / `profilePayload` / `profileErrors`); extended `BdmOrganizationForm.test.tsx` (sends only the current group; edit sends only changes; type-change block and the 409 `profile_not_empty` shown under Type with field labels; grade check; `profile.*` 422 mapping and focus; Type help text; leave guard); extended `BdmOrganizationDetail.test.tsx` (h4 section, profile rows, "—", the "No school details yet" line with and without `can_edit`, grades, commission line, line breaks kept); extended `BdmOrganizationsPanel.test.tsx` (type-dependent filters, URL sync, clearing); extended `BdmOrganizationContacts.test.tsx` (suggested roles order).

### 8.3 End to end (Playwright)

`tests/e2e/bdm-003-type-profiles.spec.ts`: provision a manager + School BDM + College BDM; the School BDM creates a school with Board CBSE, grades 6–12, a Principal contact; the detail shows them; the Board filter finds it; the College BDM's form shows College details and no Board; the school is created keyboard-only (Tab / arrow keys / Enter, no mouse); at 320 px the form and detail have no horizontal scroll.

### 8.4 Regression runs

All `test_bdm_001_*`, `test_bdm_002_*`, `test_agn_015_migration.py`, `test_agn_017_migration.py` + the new files + the lite backend set; Playwright bdm-002 spec; full web unit suite, `tsc`, `eslint`, `next build`. The full backend suite is run by the owner per the regression cadence.

---

## 9. Regression risks

| Risk | Mitigation |
|---|---|
| PATCH diff with a nested `profile` | Profile flattened into columns before the existing diff; no-op test |
| `extra="forbid"` on Create / Update | bdm-002 mass-assignment tests unchanged and green |
| Form `serverErrors` (loc length 2 only) | New length-3 `profile` branch; existing tests kept |
| Detail payload shape (every route returns it) | Additive only; web type updated |
| Loosened `courses_interested` rule (P14) | Only accepts more input; bdm-002 schema tests re-run; stored data untouched |
| Migration chain / `0001` create_all | Per-column guard; single head after `0067`; recheck `main` |
| bdm-002 exact-columns test | Deliberate subset edit (§8.1) |
| `models.py` / `schemas.py` merge conflicts | Edits confined to the BDM blocks |

No existing route, status code, field, page or component behaviour changes.

---

## 10. Documentation (same change)

`DEC-SCOPE-063` in `PRODUCT_DECISION_REGISTER.md` (P1–P13); `BDM_CRM_BACKLOG.md` bdm-003 status line, the address-gap note, the Courses Interested follow-up; `docs/architecture/DATA_MODEL.md` (new columns); API notes for the new fields and filters.

---

## 11. Completion gates

COMPLETE only when: AC1–AC10 verified with fresh evidence; backend new + bdm-001/002 + lite set pass; web unit suite, `tsc`, `eslint`, `next build` pass; Playwright bdm-003 + bdm-002 pass; migration round trip verified; phone-width and accessibility checks pass; documentation updated.

---

## 12. Revision 2 — skill reviews (2026-10-03)

Each finding is applied inline above; this section is the record. Nothing outside bdm-003 changes except the P14 rule on bdm-002's Courses Interested field, which the owner approved.

### 12.1 API and interface design

| # | Finding | Applied |
|---|---|---|
| A1 | The type-change 409 was a bare string; the form would have to parse text to name the fields | Structured body `{message, code: "profile_not_empty", fields}` following bdm-002's `possible_duplicate` (§5.2) |
| A2 | "Field of another type" was ambiguous for a `null` value | Rule is key presence; `{"board": null}` on a College is 422; `profile: {}` is valid (§5.2) |
| A3 | Grade codes and enum meanings were implicit | `Field(description=…)` on every profile field; response union discriminated on `kind` (§5.1) |
| A4 | `board` casing differs from the other enums | Kept deliberately (bdm-018 copies it onto `schools.board`); documented (§5.1) |
| A5 | Impossible filter combinations undefined | 200 with an empty page; filters are independent (§5.3) |
| A6 | Validation outside the schema boundary | The one exception (`check_profile`) needs the locked row (effective type, stored grades); documented (§2, §5.2) |
| A7 | Conditional response keys would be a Hyrum's-law trap | `address` and `profile` always present, `null` when not applicable (§5.3) |
| A8 | Retry semantics | Unchanged and stated: create guarded by the duplicate warning; repeated PATCH is a no-op (§5.3) |
| A9 | Schema 422 precedes the scope 404 | Existing FastAPI behaviour, same for every id, no existence oracle; type-dependent errors come after scope (§5.6) |

Checked and unchanged: inputs only gain optional fields; no field removed or retyped; the list stays paginated (`limit ≤ 100`); one error format (FastAPI 422 list; `HTTPException` detail string or structured object, as in bdm-002); snake_case naming as in every existing route.

### 12.2 Frontend UI engineering

| # | Finding | Applied |
|---|---|---|
| F1 | `BdmOrganizationForm` is 222 lines; profile logic would push it far past 200 | Profile values / payload / checks live in the `BdmOrganizationProfileFields` module (the `BdmContactFields` pattern) (§6.2) |
| F2 | Switching type silently swaps fields | Help text on the Type select via `aria-describedby` (§6.3) |
| F3 | Detail hierarchy flat; an all-empty section is a wall of "—" | Section `h4` + own `dl`; one "No school details yet." line, with an Edit hint when allowed (§6.3) |
| F4 | Commission as a disabled input would look editable | Plain muted text in form and detail (§6.2, §6.3) |
| F5 | Multi-line text would collapse | `whiteSpace: "pre-line"` on text nodes (§6.3) |
| F6 | 409 type-change error placement | Under the Type select, naming fields by label, focus moved there (§6.3) |
| F7 | Filter behaviour unspecified | Board applies on change; Affiliation / Territory with Search like City; Clear filters; existing empty state (§6.3) |
| F8 | Unknown enum value from the server | Falls back to the raw value (§6.3) |
| F9 | Verification | 320 px and a keyboard-only create in Playwright (§8.3) |

Checked and unchanged: the existing design language (`.field`, `.action-card`, `form-error`, `muted`, `btn`; no new CSS, colours or spacing values); loading / empty / error / paging states reused; no new request, so no new loading state; native controls only.

### 12.3 Security and hardening — threat model (delta on bdm-002 §12.3)

**New trust boundaries:** the `profile` object and `address` in the create / PATCH bodies; the `board`, `affiliation`, `territory` query params; the new free text rendered back to other BDMs of the type.

**Assets:** unchanged categories. `address` is an institution's business address; Agent Owner stays a contact (bdm-002). No new personal-data class. Agent Commission (financial) is **not** stored, returned or accepted.

| Threat | Check | Result |
|---|---|---|
| Authentication / session / tokens | New flow? | None. `get_current_user` (httponly, SameSite=Lax cookie) unchanged. |
| Authorization | Who writes profile fields? | Only through create and PATCH, so bdm-002's `bdm_context` / `load_scoped` / `require(can_edit)` apply unchanged; managers read only. |
| IDOR | New ids? | None. Out-of-scope id is still the same 404; the type-dependent 422 and the 409 `fields` list are produced only after scope and the edit permission. |
| Role escalation / mass assignment | Can `profile` smuggle server-owned or live fields? | `BdmOrgProfileIn` is `extra="forbid"`: `commission`, `students`, `applications`, `enrollments`, `master_login` and any server-owned key are 422 at both levels (AC4). |
| Input validation | Every new field | Lengths, `Literal` enums, strict ints with bounds, control characters rejected (multi-line fields allow only `\n`, P14); DB CHECKs back every enum, range and type group. Client checks are convenience only. |
| SQL injection | New queries | ORM, bound parameters; `ILIKE` through `lookups._pattern`; `board` is a `Literal`. No raw SQL with input; migration DDL uses constants only. |
| XSS | New stored text | React text nodes only; line breaks via CSS `pre-line`, never `innerHTML`; no new `href` (Affiliation and Courses are text). |
| CSRF | New state-changing calls? | None; same JSON routes under SameSite=Lax + CORS `frontend_url` (bdm-002 posture). |
| SSRF | Anything fetched? | No. |
| Secrets | Code / config | No new secret or setting; the staged diff is checked before each commit. |
| Sensitive logs | Logs and audit | Audit: field names only. Logs: ids, field names, group names. Never address, country, territory, affiliation or courses text (caplog test, §8.1). |
| Rate limiting / DoS | Abuse by an authenticated BDM | No new limiter (changing throttling needs approval; nothing asks for it). Payload bounded: profile text ≤ 120 + 120 + 200 + 1000, address ≤ 500; filters ≤ 200 / 120 chars; `limit ≤ 100`. |
| Audit / repudiation | Who changed what | Profile changes are in the same `create` / `update` audit row (field names); a type change lists `org_type`; a refused type change is logged (no write, so no audit row). |
| Information disclosure | Error text | Messages name only fields and types; no other module's data; no values echoed. |
| Future: Commission | Who may see an agent's commission once bdm-019 links it? | **NEEDS_CONFIRMATION in bdm-019.** Financial data; bdm-003 neither stores nor returns it. |
| Personal data | Purpose, retention | No new PII. Retention policy for BDM data stays **NEEDS_CONFIRMATION** (as bdm-002). |
