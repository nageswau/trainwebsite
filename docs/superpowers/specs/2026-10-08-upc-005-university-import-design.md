# upc-005 — University CSV import — design

- **Feature:** `upc-005` (`UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-005). Source `EVID-020` §25 "all universities globally" and §22
  "Total Universities: 1,250". Scope authority U15 (`EXPLICIT_APPROVAL`, 2026-10-08): "Manual create and edit + CSV import (per-row
  report, duplicate check on name + country, idempotent) by `partnership_head` / `overseas_admin`".
- **Dependencies:** upc-003 (`DEC-SCOPE-120`, PR #151) and upc-004 (`DEC-SCOPE-124`, PR #158) are merged on `main` @ `5b7c1fd5`.
  upc-007 (the stage) has not landed. Imported rows get the "Target" stage when upc-007 adds the column (IM4).
- **Numbering (provisional, re-chained at merge):** `DEC-SCOPE-125`, migration `0110_university_imports`, API §12AS, RBAC §2.51.
- **Status of answers:** IM1–IM12 are the recommended answers, applied under the owner's standing instruction for the build session
  ("proceed with the recommended answers; ask only if genuinely blocking"). They are **not** separately confirmed, so they stay
  `NEEDS_CONFIRMATION` at sign-off.

## 1. Decisions

| # | Question | Answer |
|---|---|---|
| IM1 | Columns | Required: `name`, `country`, `city`, `institution_type`. Optional: `ownership_type`, `state_region`, `website`, `course_levels`, `popular_programs`, `international_office`, `existing_relationship`, `priority`, `partnership_potential`, `overview`. `city` is required because the master requires it (NOT NULL, upc-003). A missing required column, or an unknown or repeated column, rejects the whole file with `422` (ENH-029 `known` mode). Rankings, managers, relationship strength and publishing are not imported: they are per-record decisions |
| IM2 | Values | Every row goes through `UniversityCreate`, the same validation as a manual create. Value lists accept the code or the label in any case (`Language School` = `language_school`, `a` = `A`, `phd` = `PhD`). `course_levels` and `popular_programs` are `;`-separated |
| IM3 | Country | An ISO-2 code (`GB`) or the country name (`United Kingdom`), compared after NFKC + casefold. Anything else makes the row invalid: "Unknown country: …". Internal (non-catalogue) countries are allowed, as in a manual create |
| IM4 | Imported rows | Unowned (no managers), internal (`catalogue_visible = false`), active, with a new `UNV-` code and a slug by upc-003's rule (UM14). "Stage Target" is applied by upc-007's default when it adds the stage; nothing is stored here |
| IM5 | Duplicates | upc-004's key (normalised name + country). A row matching the master (inactive rows included) **or an earlier row of the same file** is reported `duplicate` with the matching codes or row number. An import never overrides: a head adds a deliberate duplicate by hand (UD2) |
| IM6 | Idempotency | `Idempotency-Key` header required, scoped to the uploader (tel-006 R8). The same key with the same file replays the first report and creates nothing. The same key with a different file is `422`. Re-uploading the same file under a new key creates nothing either: every row is now a `duplicate` (AC2) |
| IM7 | Caps | 1 MB and 5,000 filled-in rows (shared ENH-028 reader: UTF-8 with or without BOM; NUL or malformed is `422`; too large is `413`) |
| IM8 | Roles | Import, history and reports: `partnership_head`, `overseas_admin` (overseas division) and `super_admin`. Everyone else `403`. The history shows the caller's own imports (all for `super_admin`); another person's batch is `404` |
| IM9 | Concurrency | One request, one transaction. Imports serialise on a fixed advisory lock. Each row key also takes upc-004's per-key lock (`university:<country>:<key>`), so a manual create of the same name in the same instant serialises with the import. Waits are bounded (`lock_timeout` 5 s → `409` "still being processed"). A slug collision with a concurrent create rolls back the whole import: `409` "try again" |
| IM10 | Report | Per row: `row_number`, `status` (`created` / `duplicate` / `invalid`), `name` and `country` as given (trimmed, cut to 200), `university_id` + `university_code` when created, `matches` (codes) for a duplicate, `error` for an invalid row. The batch keeps the counts, the file hash and these rows, never the file. `GET …/imports/{id}/report.csv` downloads it with formula-escaped cells (`school_bulk._safe_cell`) |
| IM11 | Audit | One `university.import` row for the batch (counts + file hash) and one `university.create` row per created university (`{code, import_batch_id}`), all in the import's transaction |
| IM12 | UI | `/partnership/universities/import`: the template download, the column reference, the upload, the result (counts + the rows that were not created) and the report download, plus the caller's import history. The list page gets an "Import universities" link for the creator roles |

## 2. Data (migration `0110_university_imports`)

`university_import_batches`: `id` UUID PK, `uploaded_by_user_id` FK `users`, `idempotency_key` VARCHAR(120), `file_sha256` VARCHAR(64),
`total_rows`, `created_count`, `duplicate_count`, `invalid_count` (INT, default 0), `results_json` JSON (default `[]`),
`created_at`/`updated_at`. `uq_university_import_batches_key (uploaded_by_user_id, idempotency_key)`, CHECK
`created_count + duplicate_count + invalid_count = total_rows`, index `(uploaded_by_user_id, created_at)`. Guarded like 0108 (0001 builds
from the models). `downgrade()` refuses while any batch exists (import history would be lost).

## 3. API (§12AS)

- `GET /partnership/universities/imports/template`: the header row as CSV.
- `POST /partnership/universities/import` (multipart `file`, header `Idempotency-Key`): `201` with the report
  `{id, uploaded_by, total_rows, created_count, duplicate_count, invalid_count, created_at, rows}`. A file-level problem is `422`/`413`
  before any row.
- `GET /partnership/universities/imports?limit&offset`: `{items, total, limit, offset}`, newest first (the report without `rows`).
- `GET /partnership/universities/imports/{id}`: the report. `GET …/imports/{id}/report.csv`: the report as CSV.
- The router is registered before `/partnership/universities/{university_id}`, so `imports` is never parsed as an id.

Processing is set-based (backlog "batch inserts"): parse and validate every row in Python; one query loads the countries; one query takes
the key locks; one query finds the existing matches; one query draws the codes; one query finds the taken slugs; one flush inserts.

## 4. Web

- `lib/universityImport.ts`: URLs, column reference, report types, the count sentence.
- `UniversityImportPanel` (client): the tel-006 panel's flow without the campaign. It handles the precheck (.csv, 1 MB), the key per
  chosen file, double-submit protection, the busy status and the error alert. The result shows counts, a table of the duplicate and
  invalid rows, and the report download link.
- `UniversityImportHistory` (server-rendered table on the page): date, counts, report link.
- `app/partnership/universities/import/page.tsx`: the creator roles see the panel; other roles see "Your role cannot import universities".

## 5. Tests

- **pytest:** template; the happy path (created rows unowned, internal, active, coded, audited); labels and ISO/name countries; invalid
  rows with reasons; duplicates against the master (case/spacing variants, inactive) and within the file; same name in another country
  created; wrong/unknown/repeated headers 422; BOM; caps; idempotent replay, key reuse 422, re-upload under a new key creates nothing;
  roles 403; history scope and 404; report CSV escaping; a 1,000-row file (AC1); migration chain, model parity and downgrade refusal.
- **vitest:** the panel's precheck, upload, result and error states; the history list.
- **Playwright:** AC1 (upload as the head and see the report) and AC2 (re-upload creates nothing); a manager has no import link.

## 6. Acceptance criteria

1. A 1,000-row file imports with an accurate per-row report. **(AC1)**
2. Re-uploading the same file creates nothing new. **(AC2)**
3. Each row is created, `duplicate` (master or same file) or `invalid` with its reason. Wrong headers are `422` for the whole file.
4. Imported universities are unowned, internal and active.
5. Only `partnership_head`, `overseas_admin` and `super_admin` can import. The report download escapes formula cells.
