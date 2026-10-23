# ccrm-018 — Document checklist templates — design

**Backlog:** `docs/delivery/COUNSELOR_CRM_BACKLOG.md` § `ccrm-018` (absorbs nehn-037 part 2). **Source:** Counselor CRM spec §8
(UNVERIFIED), owner answer CC10. **Decision:** DEC-SCOPE-248 (planned; recheck main before PR). **Blocks:** ccrm-019, ccrm-026.

## 1. Intent

The Overseas Admin keeps the document checklists that later features (ccrm-019 application checklist and Ready-for-Submission gate,
ccrm-026 visa) instantiate. A template is scoped by country, optionally narrowed by university, course level and intake, and is either an
admission or a visa list. The most specific matching template applies to an application.

Non-goals: instantiating a checklist on an application and enforcing the gate (ccrm-019); document statuses on stored documents
(ccrm-021); sensitivity classes (ccrm-022). Anti-goal (§8): templates must never look universal, so nothing is seeded.

## 2. Owner answers

- **CL1 (2026-10-23):** templates do **not** vary by visa category for now (no visa-category field exists on applications or visa
  cases). Both kinds match on the same scope fields.
- CC10 (backlog): gate mode `block` or `warn` per template.

## 3. Data model (migration `0173_checklist_templates`, down_revision = current head)

`document_checklist_templates`

| column | type | notes |
|---|---|---|
| id | uuid pk | |
| name | varchar(120) | required, trimmed |
| kind | varchar(20) | CHECK `admission`/`visa` |
| country_id | uuid fk countries | required |
| university_id | uuid fk universities, null | must belong to `country_id` (422) |
| course_level | varchar(20), null | CHECK in `COURSE_LEVELS` |
| intake | varchar(80), null | trimmed; matched case-insensitively against `overseas_applications.intake` |
| gate_mode | varchar(10) | CHECK `block`/`warn` |
| notes | text, null | |
| version | int, default 1 | +1 on every edit; ccrm-019 freezes `(template_id, version)` + item copies on the application |
| active | bool, default true | no hard delete (ccrm-019 rows will point here) |
| created_by_id / updated_by_id | uuid fk users, null | |
| created_at / updated_at | timestamps | |

Unique index `uq_document_checklist_templates_scope` on `(kind, country_id, university_id, course_level, lower(intake))`
`NULLS NOT DISTINCT WHERE active` (PostgreSQL 16) — one active template per scope; a duplicate is 409.

`document_checklist_template_items` (`template_id` fk ON DELETE CASCADE, `position` int, `document_type` varchar(80) from the
existing upload type list (`AgentUploadDocumentType`), `label` varchar(80) null — required for `Other`, `required` bool,
`allowed_statuses` JSON list, `notes` text null). Unique `(template_id, position)`. 1–50 items; a `(document_type, label)` pair once
per template.

**Item statuses vocabulary** (`app/document_checklists.py`): the ccrm-021 list `pending, requested, uploaded, under_review, verified,
incomplete, reupload_required, expired, not_required` plus the CV/SOP flow `draft, review, approved`. An item with no statuses gets
the nine standard ones (my call). The list lives here so ccrm-021 reuses it.

## 4. Resolution (acceptance)

A template matches an application when: active, same kind, `country_id` = the application university's country, and each optional
field is NULL or equals the application's value (university; course level = the linked course's `level`, an application without a
course matches only level-less templates; intake case-insensitive). Score = 4·university + 2·course_level + 1·intake; highest wins.
The unique index makes ties impossible. So a UK/PG template applies to a UK PG application; a UK/University-X template overrides it
(university outweighs level + intake together).

## 5. API (router `app/api/document_checklists.py`, prefix `/overseas-admin/checklists`)

Backlog said `/admin/overseas/checklists`; existing Overseas Admin routes all live under `/overseas-admin`, so it follows that
(my call).

| method | path | roles | notes |
|---|---|---|---|
| GET | `` | overseas_admin, super_admin, counselor | filters `kind`, `country_id`, `active` (default true); newest first, items count |
| GET | `/{id}` | same | template + items (ordered) + country/university names |
| POST | `` | overseas_admin, super_admin | 201; 409 scope taken; 422 validation |
| PUT | `/{id}` | overseas_admin, super_admin | full replace incl. items and `active`; body carries `version` — stale → 409; row locked; version+1 |
| GET | `/resolve?application_id=&kind=` | overseas_admin, super_admin, counselor (own applications via `_assigned_application`) | `{template: … | null}` |

Writes audit `checklist_template.create` / `.update` (id, kind, version). Division `overseas` required (`_require`).

## 6. Web

`/overseas/admin/checklists` (Overseas + Super Admin), nav "Document checklists". `AdminChecklistTemplatesPanel`: filter by kind and
active/inactive, table (name, kind, scope, gate, items, version), "New template" and "Edit" open an editor form: name, kind, country,
university (filtered to country), course level, intake, gate mode, notes, active, item rows (type, label, required, statuses,
notes, move up/down, remove, add). Loading/empty/error states; server 409/422 messages shown in an alert. Copy states that a template
applies only to matching applications.

## 7. Risks

Low: new tables only, no change to existing behaviour. Parallel ccrm-016 owns 0172 → re-chain if needed at merge.
