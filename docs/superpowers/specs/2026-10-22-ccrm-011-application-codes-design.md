# ccrm-011 — Business IDs for overseas applications (design)

Backlog: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` `ccrm-011` (spec §6 Application ID, §14 unique IDs, §15 ID formats). Decision:
`DEC-SCOPE-238`. Migration `0166_application_codes`. Evidence class of the source: `UNVERIFIED` PDF + owner request (backlog §1).

## Intent

Applications are UUID-only today, so a counselor, student or agent has no short, human ID to quote on a call or an email. Leads already
have `LD-000001` and universities `UNV-000001`. Give every overseas application a permanent `APP-` code, shown wherever an application is
listed and usable to find one.

## Decisions

| ID | Question | Answer | Status |
| --- | --- | --- | --- |
| AC1 | Format (`APP-000001` vs `APP-2027-00001` with yearly reset) | `APP-000001`: one global sequence, six-digit zero pad that never truncates (`APP-1234567`), no yearly reset. Matches `LD-`/`UNV-`. | Recommended default (owner asked to proceed with recommended answers) — `UNVERIFIED` |
| AC2 | Student code | Unchanged (8-char hex). `STU-` belongs to nehn-040. | Backlog text |
| AC3 | Which rows | Every `overseas_applications` row: direct, agency and School-bridged. | Builder's call |
| AC4 | Backfill order | Existing rows in `(created_at, id)` order. | Builder's call |
| AC6 | Label | **"EduSphere ID"** everywhere. On agency screens "Application ID" already means the university's `application_reference` (AGN-008 owner answer), so the new code cannot reuse that label. | Builder's call |
| AC5 | "Searchable" | The `overseas-applications` lookup (every SearchableSelect that picks an application) matches the code inside the caller's existing scope. The counselor-wide search box is ccrm-012. | Builder's call |

## Behaviour

- `overseas_applications.application_code VARCHAR(20) NOT NULL`, server default
  `'APP-' || translate(format('%6s', nextval('overseas_application_code_seq')), ' ', '0')`, unique `uq_overseas_applications_code`.
  One `nextval` per insert, so concurrent inserts never collide; a withdrawn application keeps its code and a sequence value is never
  handed out twice (AC "codes never reused after withdrawal"). The mapper uses `eager_defaults` so the INSERT returns the code (no lazy
  load on the async session).
- The code is **display-only**: no route is keyed by it, so it grants nothing; every read keeps its existing scope.
- Shown in: `GET /workflows/overseas/applications` (`application_code`), the agency list/detail (`item()`), the portal tables
  (counselor/admin/rep Application Tracking + rep Offer Letters, the counselor/admin/rep and agent dashboards, the student
  dashboard and Applications section) as an "EduSphere ID" column, the lookup label detail, the agency Applications panel and detail.
- Lookup search: `q` also matches `application_code` (case-insensitive, existing `_like`).

## Migration

`0166_application_codes`: `CREATE SEQUENCE IF NOT EXISTS`, add the column nullable if missing, one ordered `UPDATE ... nextval` backfill
of rows with no code, then NOT NULL + server default + unique constraint (each guarded, 0105's idiom). Additive; no row loses data.
`downgrade()` drops the constraint, column and sequence (codes are derived; the UUID stays the key).

## Non-goals

No counselor search box (ccrm-012), no sub-status (ccrm-014), no change to `application_reference` (the university's own reference),
no route keyed by code.

## Tests

Migration round trip + backfill order in a throwaway DB (0105 test pattern); model ↔ migration default string identical; insert yields
`APP-` codes, unique, still present after withdraw; each payload carries the code; lookup finds by code and not outside scope; frontend
panel/detail render the code.
