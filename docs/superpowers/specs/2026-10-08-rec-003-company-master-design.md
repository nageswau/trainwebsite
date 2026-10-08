# rec-003 — Company master + recruiter lead record (design)

Backlog: `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-003. Source: EVID-018 §1 quick actions (lines 40–42), §2 (50–118), §3 (120–174).
Depends on rec-001 (merged PR #143) and rec-002 (merged PR #146). Numbering: `DEC-SCOPE-120`, migration `0105_rec_companies`, API
§12AN, RBAC §2.46. upc-001 (PR #149) took `DEC-SCOPE-118`, §12AL, RBAC §2.44 and `0103`; rec-006 (PR #150) took `DEC-SCOPE-119`, §12AM, RBAC §2.45
and `0104`. So rec-003 is `DEC-SCOPE-120`, `0105_rec_companies`, §12AN and RBAC §2.46 (drafted as 119 / `0103` / §12AM / §2.45).

## 1. Answers used (2026-10-08)
The user instructed this session to proceed with the recommended answer for each open question. These are recorded in
`DEC-SCOPE-120` as **recommended defaults applied on the owner's standing instruction**, not as owner-chosen values, and can be revised.

- **D1 (Q-01):** the company code is `CMP-000001`: server-assigned from `company_code_seq` (`MAXVALUE 999999`, the unique constraint is
  the backstop), never edited. The migration backfills every existing company in `created_at`, `id` order. Every insert path (employer
  registration, `/workflows/it/jobs` auto-create, tests) gets a code through the column's server default, so none of them changes.
- **D2 (Q-02):** `companies.name` stays **globally unique** (EMP-001's 409 and the `/workflows/it/jobs` lookup by name rely on it). On
  top of that, a create or a rename warns when another company has the same **normalised** name (NFKC, whitespace collapsed, casefold):
  409 `possible_duplicate` listing up to 10 matches (code, name, city, archived), which the user overrides with `confirm_duplicate`. An
  exact name stays a hard 409. Which fields become mandatory at which stage is a pipeline question and moves to rec-005.
- **D3 (Q-03):** an employer's self-registered company gets lead source **Website** (the seeded `rec_lead_sources` row, matched by
  name; none if it is missing or inactive) and **no recruiter** — it lands in the managers' unassigned queue. Its stage is rec-005's.
- **D4 (scope split):** the §2 person fields (Recruiter Name, Designation, Mobile, Email, LinkedIn Profile) and **"+ Add Recruiter"**
  (company + first contact in one step) need `company_contacts`, which is rec-004's table; they ship with rec-004. §2 Status is rec-005,
  Next Follow-up rec-024 (which adds `next_follow_up_at`). §3 HR / TA / Hiring-Manager contacts and HR email/phone are rec-004;
  Existing Agreement, MoU/Contract Status and Payment/Commercial Terms are rec-030. **Account Manager = the assigned recruiter.**
- **D5:** §3 "Industry" and "Industry Type" are one field, `industry_id` → `rec_industries` (rec-002 C1 left the list empty for the
  manager to fill).
- **D6 (permissions, the bdm-002 pattern):** below, §4.

## 2. Scope
Built: the `companies` extension, code + backfill, assignment history, the recruiter Companies API, and the Companies list / create /
detail pages for recruiters, placement managers and super admin. The assigned BDM reads through the API (R10); a BDM-side screen is a
follow-up. Not built: contacts and Add Recruiter (rec-004), pipeline/status (rec-005), follow-ups (rec-024), contracts (rec-030),
dashboard quick-action tiles (rec-032).

## 3. Data (`0105_rec_companies`)
New nullable columns on `companies` (existing rows unchanged apart from the code):

| Column | Type | Notes |
|---|---|---|
| `company_code` | varchar(20) NOT NULL, unique `uq_companies_code` | server default `'CMP-' \|\| lpad(nextval('company_code_seq')::text, 6, '0')` |
| `linkedin_url` | varchar(300) | |
| `industry_id` | FK `rec_industries` | |
| `company_size_id` | FK `rec_company_sizes` | |
| `employee_count` | int | CHECK 0..10,000,000 |
| `city`, `state`, `country` | varchar(120) | free text (the bdm-002 idiom) |
| `head_office` | varchar(300) | |
| `branches` | varchar(1000) | free text |
| `description` | varchar(2000) | |
| `lead_source_id` | FK `rec_lead_sources` | |
| `campaign_id` | FK `rec_campaigns` | its lead source must equal `lead_source_id` (app rule) |
| `priority` | varchar(10) | CHECK `hot` / `warm` / `cold` |
| `assigned_recruiter_user_id` | FK users | NULL = unassigned queue |
| `assigned_bdm_user_id` | FK users | R10 reference |
| `created_by_user_id` | FK users | NULL for rows that predate rec-003 |
| `archived_at` | timestamptz | |

Indexes: `ix_companies_assigned_recruiter`, `ix_companies_assigned_bdm`, `ix_companies_name_key` on the normalised name (trimmed, whitespace collapsed, lower-cased).

New `company_assignment_history`: `id`, `company_id` FK, `from_user_id` (NULL = was unassigned), `to_user_id` NOT NULL,
`changed_by_user_id` NOT NULL, `created_at`; index on `company_id`. Append-only.

Migration: every column, constraint, index, sequence and table is created only when missing (0001 builds from the models — the 0069
idiom). The backfill sets codes only where `company_code IS NULL`, then sets NOT NULL. `downgrade()` refuses while any recruiter data
exists (any history row or any non-NULL new column other than the code); otherwise it drops everything it added.

## 4. Scope and permissions (inline pattern, `services/recruiter_companies.py`)
Read scope (any other role → 403; out of scope → 404):
- `placement_team` with a profile: `assigned_recruiter_user_id = me`.
- `placement_manager`: companies of direct reports, plus unassigned.
- `super_admin`: all.
- `bdm`: `assigned_bdm_user_id = me`, read only.

Actions (role 403 first, then state 409 — the bdm-002 C15 rule):

| Action | Who | State |
|---|---|---|
| create | recruiter (assigned to self), manager (optional assignee from the team, else unassigned), super_admin (any recruiter or none) | — |
| edit | assigned recruiter, super_admin | not archived |
| archive | assigned recruiter, super_admin | not archived |
| restore | manager, super_admin | archived |
| reassign | manager, super_admin | not archived; target = an active `placement_team` user with a profile reporting to the manager (super_admin: any) |

`assigned_bdm_user_id`, when set, must be an active `bdm` user (422 otherwise). Lead source, campaign, industry and size must be
active when they are set or changed (locked `FOR SHARE`); keeping a since-deactivated value is allowed. Every write: row lock, change,
`AuditLog` (`recruiter_company.<action>`, ids and field names only), one commit. Reassign also appends `company_assignment_history`.

## 5. API (§12AN) — `/api/v1/recruiter/companies`
| Method | Path | Notes |
|---|---|---|
| GET | `` | `q` (name or code), `priority`, `lead_source_id`, `industry_id`, `city`, `assigned` (`me` / `unassigned` / uuid), `include_archived`, `limit`, `offset`; `{items,total,limit,offset}` by `lower(name)`, `id` |
| POST | `` | 201 `{company}`; `confirm_duplicate` |
| GET | `/{id}` | `{company}` incl. `assignment_history` (newest first) |
| PATCH | `/{id}` | fields sent only; no-op writes no audit |
| POST | `/{id}/archive`, `/{id}/restore` | |
| POST | `/{id}/assign` | `{recruiter_user_id}`; same recruiter → 409 |
| GET | `/bdm-options` | `q`, `limit`: active BDM users `{id, full_name}` for the picker (writers only) |

Bodies are typed Pydantic models with `extra="forbid"`; a 422 names the field. Output includes `permissions`.

`employer.register` additionally sets `lead_source_id` (D3). `/admin/companies`, `/workflows/it/jobs` and EMP routes are otherwise
unchanged.

## 6. Web
- Nav: **Companies** in `RECRUITER_NAV` (after Dashboard) and `RECRUITER_MANAGER_NAV`.
- `/recruiter/companies`: list with URL filters (search, priority, lead source, industry, assigned, archived), pager, empty/error states;
  **+ Add Company** for creators.
- `/recruiter/companies/new`: the create form (pickers from the rec-002 catalogues; duplicate warning with "Create anyway").
- `/recruiter/companies/[id]`: detail, Edit (same form), Archive/Restore, Reassign (manager), assignment history.
- Signed-out users go to `/it/login`; a role without access sees the API's 403 message (`accessUnavailable`).

## 7. Acceptance criteria
1. A recruiter creates a company with every company-side §2/§3 field; the code is server-assigned and the recruiter is the assignee.
2. A recruiter sees only their own companies; another recruiter's company → 404.
3. A manager reassigns; history is kept; the new recruiter sees it and the old one gets 404.
4. An employer's self-registered company has lead source Website, no recruiter, and appears in the manager's unassigned queue.
5. EMP-001…005, `/workflows/it/jobs` auto-create and `/admin/companies` are unchanged (their tests pass).
6. Invalid priority → 422; exact duplicate name → 409; normalised duplicate → 409 `possible_duplicate` unless confirmed; BDM PATCH → 403;
   `hr_team` / `it_admin` / employer → 403.
7. Archived companies are hidden from the default list and cannot be edited (409) until restored.
8. Existing companies are backfilled with unique `CMP-` codes in creation order.
9. Pages work on desktop, tablet and mobile with loading/empty/error states and keyboard operation.

## 8. Risks
- `companies` is shared with EMP and the legacy placement screens: only nullable columns plus a defaulted code are added.
- Migration numbers move with parallel items: re-chained to `0105` after upc-001 and rec-006.
- Hot spots: `models.py`, `schemas.py`, `main.py`, `navigation.ts` (append-only edits).
