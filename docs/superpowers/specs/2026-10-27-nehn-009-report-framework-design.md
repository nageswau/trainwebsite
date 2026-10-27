# nehn-009 — Report framework: registry, standard filters, JSON/CSV/xlsx, audited (design)

Decision: `DEC-SCOPE-303` · API §12HA · RBAC §2.214 · migration `0210_training_report_grants`.
Source: `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` §C `nehn-009` (DERIVED_BLUEPRINT over the §14/§15 ORIGINAL_REQUIREMENT
lines 309-323). Dependencies nehn-004 (xlsx), nehn-005 (grants), nehn-008 (field policy) are merged.

The session ran in autonomous mode: the user asked for recommended defaults instead of questions. Every choice marked **(builder's
default)** is `NEEDS_CONFIRMATION` by the client and is listed in the decision register.

## 1. Intent

One place where reports are declared once and served the same way: a catalogue filtered by the caller's permissions, a paged JSON
read, and CSV/xlsx downloads that hold exactly the same rows and columns, with standard filters, a row cap, a throttle and an audit row.
Later report packs (nehn-010 training, nehn-016/017 recruiter/HR) register into it instead of writing new routers.

**Non-goals.** Existing module reports (telecaller, partnership, agent, CRM) are not migrated. No background export jobs. No new indexes
(none needed for the pilot: `enrollments.batch_id`, `student_id` are indexed; the backlog's index list waits for EXPLAIN on real volumes).
The nehn-010 report pack itself (student-wise, trainer, attendance, …) is out of scope.

## 2. Pilot report (builder's default)

A framework with no report cannot be used or tested, so one report is registered: **`enrollments` — "Enrollments"** (resource
`reports.training`). Columns: Enrollment code, Student code, Student, Course, Batch, Trainer, Enrolled on, Batch ends, Status, Progress %.
No sensitive (`financial`) column; nehn-010 adds those. It declares every standard filter except `recruiter_id`
(an enrolment has no recruiter), which therefore proves the 422 rule.

- `from`/`to` → `enrolled_on` (the report's default date); `completion_from`/`completion_to` → the batch `end_date` (the backlog's
  nehn-010 (d) reading; whether completion means progress 100 / certificate / batch end is still open there).
- Default sort: `enrolled_on` desc, then `enrollment_code`; `latest=N` takes the N most recent of the filtered rows.
- Status: `enrollments.status` is free text (the admin PATCH stores any value), so the picker offers the statuses present in the
  caller's scope (`options.statuses`) and the filter accepts any value up to 30 characters (an unknown one simply matches nothing).

## 3. Backend

### 3.1 Registry (`services/reports/registry.py`)
`Report(id, title, description, resource, columns, filters, query, options)` and `Column(key, label, cls=None)`.
`query(user, filters)` returns a SQLAlchemy `Select` whose labelled columns match the column keys, **already scoped to the caller**,
filtered and ordered. `options(db, user)` returns the filter pickers (courses, batches, trainers) within the same scope. `REPORTS` is a
dict; `register(report)` refuses a duplicate id, a filter outside the standard set, or a resource outside the catalogue (import-time
failure, like `require_permission`).

### 3.2 Standard filters
`from`, `to`, `course_id`, `batch_id`, `trainer_id`, `recruiter_id`, `student`, `status`, `latest`, `completion_from`, `completion_to`,
plus paging `page`, `page_size` on the JSON read. Rules (all 422, message naming the field as the page shows it):
- any query parameter outside (declared filters ∪ paging) — an undeclared standard filter **and** an unknown name;
- a bad date (`YYYY-MM-DD`), `from > to`, `completion_from > completion_to`;
- a bad UUID; `status` over 30 characters; `student` over 100 characters;
- `latest` not an integer in 1..1000; `page` < 1; `page_size` not in 1..200 (default 50).
Empty values count as not given (a GET form sends empty fields). Dates are calendar days; the stored columns are `date`s in IST
already, so the range is inclusive on both ends with no time-zone conversion. Open-ended ranges are allowed.
`student` matches student code (exact, case-insensitive) or name/email (contains, case-insensitive).

### 3.3 Scope (rows) — the pilot
super_admin: all; `it_admin`: all (enrolments are IT training; today's `/admin/enrollments` serves the same two roles); `trainer`:
batches where `Batch.trainer_id` = the caller. **Any other role holding the grant sees no rows** (deny by default; nehn-016/017 add their
scope). A trainer passing another trainer's `trainer_id` gets an **empty result**, not 403 (builder's default: the filter intersects the
scope, it does not reveal whether that trainer has batches).

### 3.4 Endpoints (`api/reports.py`, prefix `/api/v1/reports`)
| Route | Gate | Body |
|---|---|---|
| `GET /reports` | signed in | `{items: [{id, title, description, filters, can_download}]}` — only reports whose `<resource>.view` the caller holds |
| `GET /reports/{id}` | `<resource>.view` | `{id, title, description, columns, items, total, page, page_size, filters (declared), applied, options}` |
| `GET /reports/{id}.csv` / `.xlsx` | `<resource>.download` | the file; every matching row |

Order: unknown id → 404; no grant → 403; inputs → 422. (Report ids are not secret: the catalogue is a published contract.) Reads set
`Cache-Control: private, no-store` and are not audited (house rule). Columns pass through `field_policy.strip` with the report's
`cls` tags for JSON and files alike.

**Export:** one transaction — lock the caller's user row, throttle (30 exports per 10 minutes, counted from the caller's own
`report.export` audit rows: the agent-report/ccrm-035 pattern; 429 + `Retry-After`), count; over **10,000** rows (builder's default)
→ 422 "narrow the filters" (refused, never cut short); render with `export_response`; add the `AuditLog(action="report.export",
entity_type="report", entity_id=id, metadata_json={filters: {name: value}, rows, format})`; commit before returning (fail closed).
The audit carries the filter **values** (AC5 "with the filters"); the application log keeps names only.

### 3.5 Permissions (nehn-005) and migration
Catalogue `reports.training: view, download`. Seed (`DEFAULT_GRANTS` + frozen copy in migration `0210`): `it_admin` and `trainer`
(builder's default — the backlog lists "admins, trainer (own)"; management/HR/placement wait for their own items). super_admin is implicit.
Migration is insert-only (`ON CONFLICT DO NOTHING`); downgrade deletes the `reports.training` grants and overrides.

## 4. Web
- `lib/reports.ts`: types, filter names/labels, URL builders.
- `components/ReportLibraryPage.tsx` (server): signs in, role gate per page, fetches the catalogue; without `?report=` shows the
  library (a list of report cards); with it, fetches the report and renders `ReportView`.
- `components/ReportView.tsx` (server, no client JS besides the download buttons): the GET filter form built from the declared
  filters (date inputs; course/batch/trainer/status selects from `options`/`statuses`; student text; latest number), Apply / Clear,
  the table (`.table compact stack`, labelled cells for phones), "Showing x–y of N" with Previous/Next links, `SpreadsheetButtons` when
  `can_download`. States: 422 message above the form (form kept), empty "No rows match these filters.", unavailable message, 403 access card,
  unknown report id → library with a message.
- Pages: `/admin/report-library` (super_admin), `/it/admin/report-library` (it_admin, super_admin), `/it/trainer/report-library`
  (trainer). Nav item "Report library" in those three navs (not resource-tagged: the library spans resources and shows its own empty state).

## 5. Acceptance criteria → tests
1. `GET /reports` lists only reports the caller may view (it_admin, trainer: `enrollments`; a role without the grant: empty; revoke →
   gone). — pytest
2. Each declared filter narrows the rows; an undeclared (`recruiter_id`) or unknown filter → 422. — pytest per filter
3. `latest=N` returns the N most recent by `enrolled_on`. — pytest
4. JSON (all pages) == CSV rows == xlsx rows, same columns. — pytest
5. Every download writes one audit row with the filters; a refused one writes none. — pytest
6. Negative: `from > to` 422; trainer sees only own batches, another trainer's id → empty; no grant → 403; over cap → 422; throttle 429.
7. Web: library + report render, filters round-trip through the address, paging, download buttons follow `can_download`; mobile has no
   page-level horizontal scroll. — vitest + Playwright e2e.

## 6. Risks
Seeding new grants on it_admin changes pinned lists (`test_nehn_005_permissions` catalogue set, nehn-006 e2e `IT_ADMIN_SEED`) — update
deliberately. New nav items can break e2e that pin nav lists — run the nav specs.
