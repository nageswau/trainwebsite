# rec-002 — Recruiter catalogues (design)

Backlog: `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-002. Source: EVID-018 §2 (lines 52–82, 108–110), §3 (102–104, 130, 146),
§4 (184–192), §6 (290), §9 (432–462) and §26 (1029–1034). Depends on rec-001 (merged PR #143). Numbering: `DEC-SCOPE-117`,
migration `0101_rec_catalogues`, API §12AJ, RBAC §2.43.

## 1. Owner answers (2026-10-08, `EXPLICIT_APPROVAL` in session)
- **C1:** `rec_industries` starts **empty**. The source names "Industry" but lists no values, and none are invented.
- **C2:** company size is a **managed, seeded list** (`rec_company_sizes`): 1-10, 11-50, 51-200, 201-500, 501-1000, 1001+. The
  owner chose these bands; they are not source values.
- **C3:** readers are **`placement_team`, `placement_manager` and `super_admin`**. Writers are `placement_manager` and `super_admin`.
  `hr_team`, `it_admin` and every other role get 403 (Q-28 keeps `/recruiter/*` closed to `hr_team`).

## 2. Scope
Seven managed lists. Values are deactivated, never deleted. Renaming keeps the id, so later records (rec-003, rec-004, rec-007 and
rec-009) keep their link. Only the lists, their seeds, the API and the manager page are built here. No record references them yet.

| Kind (URL slug) | Table | Seed |
|---|---|---|
| `lead-sources` | `rec_lead_sources` | the 15 §2 values, in source order |
| `candidate-sources` | `rec_candidate_sources` | the 12 §9 values, in source order |
| `industries` | `rec_industries` | none (C1) |
| `job-categories` | `rec_job_categories` | IT, Sales, Marketing, Finance, HR, Engineering (§26) |
| `contact-roles` | `rec_contact_roles` | HR Manager, Talent Acquisition Manager, Recruiter, Hiring Manager, HR Head (§4) |
| `company-sizes` | `rec_company_sizes` | the six C2 bands |
| `campaigns` | `rec_campaigns` | none |

Out of scope: industry type (rec-003 decides it), the candidate "source detail" (rec-009), and pickers on any record form.

## 3. Data
- **Simple lists (six tables, one shape):** `id` uuid PK, `name` varchar(120) not null, `active` bool default true,
  `sort_order` int default 0, and timestamps. A unique index `uq_<table>_name` on `lower(name)` makes names case-insensitive unique
  per list. The seeds take `sort_order` 1..n in source order, so the bands read smallest first. A new value goes to the end
  (max + 1).
- **`rec_campaigns`:**
  - Columns: `name` varchar(160), `lead_source_id` FK → `rec_lead_sources` (not null), `start_date` (not null), `end_date`
    (nullable), `active`, and timestamps.
  - `CHECK end_date IS NULL OR end_date >= start_date`.
  - `uq_rec_campaigns_name` on `lower(name)`, and `ix_rec_campaigns_lead_source`.
  - This is the tel-002 campaign shape. The source is a recruiter lead source, and there is no product.
- **Migration `0101_rec_catalogues`:**
  - Creation is guarded (the 0076 idiom: 0001 builds from the models).
  - The seed always runs and inserts only a missing `lower(name)`, so it is idempotent and never overwrites a manager's rename.
  - `downgrade()` refuses while manager data exists: any campaign, any industry, or any simple list whose rows differ from its seed.

## 4. API (§12AJ). Prefix `/api/v1/recruiter/catalogue`
| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/{kind}` | readers | `active`, `q`, `limit`, `offset`; `{items,total,limit,offset}` ordered by `sort_order`, `lower(name)`, `id`. Item `{id,name,active,sort_order}` |
| POST | `/{kind}` | writers | `{name}` → 201 |
| PATCH | `/{kind}/{id}` | writers | `{name?, active?}` → 200 |
| GET | `/campaigns` | readers | adds `lead_source_id`; ordered active first, newest start, then name. Item `{id,name,lead_source:{id,name,active},start_date,end_date,active}` |
| POST | `/campaigns` | writers | `{name, lead_source_id, start_date, end_date?}` → 201 |
| PATCH | `/campaigns/{id}` | writers | any create field, plus `active`; `end_date: null` clears it |

Rules:
- An unknown kind → 404 "Catalogue not found". An unknown id → 404.
- A reader who is not a writer always gets active rows only, whatever `active` asks for (AC2, the tel-002 P1 rule).
- Bodies are untyped dicts parsed by `services/telecaller._parse`, so a 422 is one sentence that names the field.
  - `extra="forbid"`.
  - Names are trimmed, required and capped, with no control characters (`_tel_name`).
  - `active` is a StrictBool.
- A duplicate name → 409, decided by the unique index even under a race (`flush_unique`).
- Campaigns:
  - The end date may not come before the start date → 422; this is checked on the merged row.
  - A campaign's lead source must be active when it is set. Keeping a since-deactivated source is allowed. The source is locked
    `FOR SHARE`, as in tel-002 P4.
- There is no DELETE route (405).
- Each write route has one commit, plus an `AuditLog` row in the same transaction:
  - `recruiter.catalogue_create` / `recruiter.catalogue_update`.
  - `entity_type` = the table name.
  - The metadata holds the changed field names only.
- A PATCH that changes nothing writes no audit row.

## 5. Web
- `RECRUITER_MANAGER_NAV` gains **Catalogues** → `/recruiter/manager/catalogue`, which redirects to `/lead-sources`.
- `/recruiter/manager/catalogue/[kind]`:
  - The server shell reads `auth/me`. A role other than manager or `super_admin` gets the access-denied view; signed-out users go
    to `/admin/login`.
  - The page has a title, intro and a tab bar (links with `aria-current="page"`, wrapping on mobile) over the seven lists. An
    unknown kind → `notFound()`.
  - Super admin sees `SUPER_ADMIN_NAV` (the rec-001 team-page idiom).
- `RecruiterCatalogueListPanel` (the six simple lists, one component):
  - A create form (Name).
  - A list with search (in the URL: `?q=&offset=`), a pager, and loading, error-with-Retry and empty states.
  - Each row has Edit (inline, Esc cancels), Deactivate (inline confirm) and Reactivate.
  - Focus moves to the feedback after a write, and a ref guards against a double submit.
- `RecruiterCampaignsPanel`: the same shell for campaigns. Lead source picker = active lead sources (every page read). Start date
  is required; end date is optional and checked in the browser too.
- The existing `.telecaller-list` card layout is reused on mobile. No new CSS.

## 6. Acceptance criteria (backlog + this design)
1. The seed values match the source lists exactly (names and order), and C2's six bands are seeded. Industries start empty.
2. A deactivated value is hidden from a recruiter's reads (pickers) but kept, with its id, on existing rows. A manager still sees it.
3. A recruiter (and `hr_team` / `it_admin`) cannot create or edit → 403; `hr_team` / `it_admin` cannot read either.
4. A manager adds the lead source "Naukri"; a duplicate name (any case) → 409.
5. A rename keeps the id.
6. A campaign needs an active lead source and an end date that is not before its start date.
7. The manager page works on desktop, tablet and mobile, with loading, empty and error states, and is keyboard operable.

## 7. Risks
- New tables only. Shared hot spots: `models.py`, `schemas.py`, the `main.py` router tuple, and `navigation.ts`
  (`navigation.recruiter.test.ts` changes for the new entry). These are append-only edits.
- A parallel rec-006 could take 0101. Re-check origin/main before the merge and re-chain if needed.
