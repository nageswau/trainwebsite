# upc-004 — Duplicate prevention + BDM university-org link — design

- **Feature:** `upc-004` (`UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-004). Source `EVID-020` §26 (L868–894) "search before adding",
  the 5-field warning panel, and "prevents two employees contacting the same university". Scope authority U13 (`EXPLICIT_APPROVAL`,
  2026-10-08).
- **Dependency:** upc-003 (`DEC-SCOPE-120`) is merged on `main` @ `593e9b9c` (PR #151). upc-006 (contacts), upc-007 (stage) and
  upc-020 (follow-ups) have not landed. The panel shows "—" for stage, last contact and next follow-up until they do (as the backlog says).
- **Numbering (provisional, re-chained at merge):** `DEC-SCOPE-121`, migration `0106_university_duplicates`, API §12AO, RBAC §2.47.
- **Status of answers:** UD1–UD12 are the recommended answers, applied under the owner's standing instruction for the build session
  ("proceed with the recommended answers; ask only if genuinely blocking"). They are **not** separately confirmed, so they stay
  `NEEDS_CONFIRMATION` at sign-off.

## 1. Decisions

| # | Question | Answer |
|---|---|---|
| UD1 | Q-02 duplicate key | The normalised name + the country. Normalisation is bdm-002's `normalize_key`: NFKC, whitespace collapsed, casefolded. City is not part of the key, and aliases are not matched ("UCL" ≠ "University College London"). Inactive universities count as matches, so a deactivated record is not re-created |
| UD2 | Override | A duplicate create is `409 university_duplicate`. Only `partnership_head` and `super_admin` may override, and only with `duplicate_reason` (10–500 characters). The override is audited as `university.duplicate_override` with the match count and the reason. Anyone else who sends a reason, including `overseas_admin`, still gets the `409`, with `can_override: false` |
| UD3 | Edit | A PATCH that changes the name or the country re-runs the check, excluding the university itself, under the same override rule |
| UD4 | Race | The check and the insert run under `pg_advisory_xact_lock(hashtextextended('university:' ∥ country ∥ ':' ∥ name_key, 0))`, so two creates of the same key in the same instant serialise and the second one sees the first |
| UD5 | Panel | Code, name, country, city, active/public state, **existing relationship**, **assigned managers** (primary + backup), **stage**, **last contact** and **next follow-up**. The last three are "—" (UI only, not API fields) until upc-007, upc-006 and upc-020 add them |
| UD6 | Search before adding | `GET /partnership/universities/duplicates?name=&country_id=&exclude_id=` for the master's read roles. Exact key match, up to 10 matches + total. The master form calls it as the user types (debounced). It is advisory; the server decides on save |
| UD7 | BDM link | `bdm_organizations.university_id`, a nullable FK to `universities` with an index. CHECK `university_id IS NULL OR org_type = 'university'` |
| UD8 | BDM create | `org_type = university` with no `university_id`: master matches by name key (any country, because BDM orgs have no country FK) are added to the existing `409 possible_duplicate` as `university_matches` + `university_total`, unless `confirm_duplicate`. The BDM either links ("Link and save" resends with `university_id`) or saves unlinked ("Save anyway"). Nothing is ever merged |
| UD9 | BDM edit | PATCH accepts `university_id` (link or `null` to unlink), validated like create. Changing `org_type` away from University clears the link. The edit-form control for linking is a follow-up; the API is in this item |
| UD10 | BDM read | The BDM organisation detail gains `university`: `{id, university_code, name, country_name, city, primary_manager_name}` or null, read-only. There is no commission data here, and the full 360 view is upc-030 |
| UD11 | Master read | The university detail gains `linked_bdm_organizations`: `[{id, code, name, city, bdm_type, assigned_bdm_name, archived}]`, ordered by code. It is text only, because the BDM routes are not open to partnership roles |
| UD12 | Existing data | The migration backfills `name_key`. It **reports** (logs) the duplicate groups already in `universities` and the unlinked BDM University orgs whose name matches the master. It does not merge or link anything (backlog edge case) |

The legacy `POST /admin/universities` is unchanged: its panel was replaced by a link to the master in upc-003. Its rows get `name_key`
from the model, so they are found by later checks.

## 2. Data (migration `0106_university_duplicates`)

- `universities.name_key VARCHAR(200) NOT NULL`. It is set by a `@validates("name")` hook on `University`, so every writer (master,
  legacy admin, seed, tests) keeps it in sync, and the migration backfills it in Python with the same function.
  - New index `ix_universities_duplicate_key (country_id, name_key)`. It is **not unique**, because overrides and existing duplicates
    are allowed.
- `bdm_organizations.university_id UUID NULL REFERENCES universities(id)`, with `ix_bdm_organizations_university` and
  `ck_bdm_organizations_university_link`.
- `normalize_key` moves to `app/core/identifiers.py`, so the model can use it. `services/bdm_organizations` re-imports it under the
  same name.
- `downgrade()` refuses while any BDM organisation is linked, because the link would be lost (the 0105 precedent).

## 3. API (§12AO)

- `GET /partnership/universities/duplicates`. Read roles (`require_reader`).
  - Parameters: `name` (1–200, required), `country_id` (optional), `exclude_id` (optional).
  - Returns `{items: [UniversityMatch], total}`. A blank name after trimming is `422`.
- `UniversityMatch` = `{id, university_code, name, country: {id, name}, city, active, catalogue_visible, existing_relationship,
  primary_manager, backup_manager}`.
- `POST /partnership/universities` and `PATCH /{id}` accept `duplicate_reason` (10–500, trimmed).
  - When there are matches without a valid override: `409 {code: "university_duplicate", message, matches, total, can_override}`.
  - On an override: create and audit `duplicate_override` `{match_count, reason}`.
  - A reason sent with no matches is ignored.
- `GET /partnership/universities/{id}` (and every detail response) adds `linked_bdm_organizations`.
- `POST /bdm/organizations` adds `university_id` (optional).
  - An unknown university is `422`. A `university_id` on a non-University type is `422`.
  - The `409 possible_duplicate` gains `university_matches`/`university_total`, which are always present (empty when none).
- `PATCH /bdm/organizations/{id}` adds `university_id`, with the same validation. A type change away from University clears the link.
- `GET /bdm/organizations/{id}` and every detail response add `university`.

Authorization is unchanged: the master read roles for `duplicates`, and the existing BDM scope for BDM routes. A BDM sees master
matches only through their own create (name, code, country, city, relationship and manager names, with no commission data). This is
the panel U13 grants them.

## 4. Web

- New `UniversityMatchList` component, shared by both forms: one card per match with the 5 panel fields ("—" where not tracked yet).
- `UniversityForm`:
  - The name and the country are tracked as the user types. After 400 ms with a name of 2 or more characters and a country, it calls
    `duplicates` (the previous call is aborted, and `exclude_id` is sent when editing). A `role="status"` panel "Already in the
    University Master" lists the matches, each linked to its record.
  - On save, a `409 university_duplicate` shows the panel as an alert. With `can_override`, a reason box and an "Add anyway" button
    resend the request with `duplicate_reason`. Otherwise it says "Ask your partnership head to add it if this is a different
    university."
- `BdmOrganizationForm` (create): the existing duplicate alert adds an "Already in the University Master" section rendered by
  `UniversityMatchList`, with one "Link and save" button per match. "Save anyway" saves without linking.
- `BdmOrganizationDetail`: a "University Master" line shows the link ("Linked to UNV-000012 · Name, Country" or "Not linked").
- The university detail page: a "Linked BDM organisations" section (an empty-state line when there are none).

## 5. Tests

- **pytest:** the key normalisation and the model hook; duplicates endpoint roles and matching (case and spacing variants, same name in
  another country allowed, inactive counted, exclude_id); create and PATCH 409, the override by head/super_admin, `overseas_admin` with a
  reason still 409, the reason length 422, audit rows; the advisory-lock path (two sequential creates); BDM create 409 with university
  matches, link, unknown id 422, link on a non-University type 422, the type change clearing the link, and the detail `university` field;
  the master detail `linked_bdm_organizations`; migration round trip, backfill, report and downgrade refusal; bdm-002/003 regressions.
- **vitest:** `UniversityMatchList`, the UniversityForm pre-check and override flow, and the BdmOrganizationForm link flow.
- **Playwright:** AC1 (lower-case duplicate blocked, override by the head) and AC2 (the BDM create panel, then link).

## 6. Acceptance criteria

1. Adding "abc university" when "ABC University" exists in the same country shows the panel and blocks the save. **(AC1)**
2. The BDM create flow shows the same panel and offers the link. **(AC2)**
3. The same name in a different country is allowed.
4. A forced duplicate without the override right is `409`. A head or super_admin with a reason creates it, and the override is audited.
5. The master detail lists its linked BDM orgs, and the BDM detail shows its linked university.
6. Existing duplicate rows are reported by the migration and never merged. The bdm-002 org creation tests still pass.
