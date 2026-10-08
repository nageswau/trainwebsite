# rec-007 — Job Requirement (`jobs` extension) (design)

Backlog: `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-007. Source: EVID-018 §6 (lines 272–348), S2-§6 required/preferred skills, §1 quick
action "+ Add Job Requirement". Depends on rec-003 (merged PR #152) and rec-006 (merged PR #150). Numbering: `DEC-SCOPE-128`, migration `0113_job_requirements` (after rec-005's `0112_company_pipeline`), API §12AV, RBAC §2.54.
It was drafted as 123 / `0108` / §12AQ / §2.49. upc-006, upc-004, rec-004, upc-007 and rec-005 (`0108`–`0112`, DEC-SCOPE-123–127,
§12AQ–§12AU, §2.49–§2.53) merged to `main` first. **Status: DRAFT** (branch `feature/rec-007`).

## 1. Answers used (2026-10-08)
The user told this session to proceed with the recommended answers. Q-04 and Q-05 were **not** put to the owner, so `DEC-SCOPE-128`
records them as **recommended defaults (UNVERIFIED)**. The owner can revise them.

- **J1 (Q-04, status mapping):** one `jobs.status` column carries the 11 §6 statuses (`new`, `requirement_received`, `sourcing`,
  `shortlisting`, `profiles_shared`, `interviewing`, `selected`, `joined`, `on_hold`, `closed`, `cancelled`), guarded by a CHECK.
  - Data migration: `draft` → `new`, `open` → `requirement_received`, `closed` → `closed`, and any other legacy value → `on_hold`.
    Every remapped row gets a `job_status_history` row whose note keeps the original value, so no data is lost.
  - The **open set** (what students see and can apply to) is `requirement_received` … `interviewing`, while the deadline has not passed.
- **J2 (Q-04, employer acceptance):** an employer posting needs **no recruiter acceptance**. This keeps EMP-002's "no invented approval
  gate" precedent. An employer posting starts `new`, and the employer publishes it as before.
- **J3 (legacy shim):** the employer API and the `/workflows/it/jobs` routes keep the legacy words.
  - **Input:** `draft` → `new` (or `on_hold` when the job has already left `new`), `open` → `requirement_received` (a no-op when already
    open), `closed` → `closed` (a no-op when closed, cancelled or joined).
  - **Employer output:** `status` stays legacy-shaped (`draft` = new/on_hold, `open` = the open set, `closed` = the rest). It also gains
    `requirement_status` and `status_label`. The workflows routes return the §6 key plus `status_label`.
- **J4 (Q-05):** "About to expire" = an open requirement whose Application Deadline (`closes_on`) is within **7 days** (IST); "expired"
  = past the deadline while still open. Both are computed values, not statuses. "Requirement Date" is the date the requirement was
  received; it defaults to today (IST).
- **J5 (scope split):** the §6 "Recruiter" field (the company contact who gave the requirement) needs `company_contacts`, which is
  rec-004's table, so it ships with rec-004. The Candidates / JD / Interviews tabs are rec-017 / rec-008 / rec-018.
  - **Company stage (rec-005, merged as PR #162):** every status writer calls `drive_company_stage`, which fires rec-005's two events.
    - A requirement reaching Requirement Received fires `requirement_received`.
    - Closing or cancelling the company's last live requirement fires `requirement_closed`.
    - The company row is locked first, so two concurrent closes serialise.
    - rec-005's engine ignores a stage the company has already passed. The later stages (sourcing, profiles shared, interview, selected,
      joined) are fired by rec-017–rec-023 from candidate progress, as `recruiter_stages.EVENTS` assigns them.
- **J6 (vocabularies):**
  - Work mode is `onsite` / `remote` / `hybrid`.
  - Shift is `day` / `night` / `rotational` / `flexible`.
  - Employment type is `full_time` / `part_time` / `contract` / `internship` / `temporary`.
  - Priority is `high` / `medium` / `low`.
  - Salary is an annual INR range. Experience is stored in months; the form takes years.
- **J7 (skills):** `job_skills` is the authority. `jobs.skills` (JSON) stays as a **derived mirror**: the names in order, required first.
  It is rewritten by the one service function every writer calls, so the legacy readers (employer, open jobs, public, portal) are
  unchanged.
  - A name resolves through `services.skills.resolve` (name or alias, active skills only).
  - An unmatched name is kept as free text with `skill_id` NULL. These are the "flagged" skills.
  - A legacy writer (employer, workflows) sends a flat list: names it keeps hold their kind, and new names become `required`.

## 2. Transitions
| From | To |
|---|---|
| `new` | `requirement_received`, `on_hold`, `closed`, `cancelled` |
| any active stage (`requirement_received` … `selected`) | any other active stage, `on_hold`, `closed`, `cancelled`; `selected` also → `joined` |
| `joined` | `closed` |
| `on_hold` | any active stage, `closed`, `cancelled` |
| `closed` | `requirement_received` (reopen) |
| `cancelled` | — (terminal) |

The same status again is a 409, and so is any move not in the table. No status ever returns to `new`.

## 3. Data (`0113_job_requirements`)
New nullable `jobs` columns:
- `requirement_code`: NOT NULL, unique, server default `'REQ-' || lpad(nextval('requirement_code_seq')::text, 6, '0')`. Existing rows
  are backfilled in `created_at`, `id` order.
- `department`, `job_category_id` (FK `rec_job_categories`), `vacancies` (1..10000), `qualification`.
- `experience_min_months` / `experience_max_months` (0..600, min ≤ max).
- `salary_min` / `salary_max` (numeric(12,2), ≥ 0, min ≤ max).
- `work_mode`, `shift`, `employment_type`, `joining_requirement`, `requirement_date`, `priority`.
- `assigned_recruiter_user_id` and `created_by_user_id` (both FK users).

CHECKs cover status, the vocabularies and the ranges. Indexes are `ix_jobs_status`, `ix_jobs_assigned_recruiter` and `ix_jobs_closes_on`.

New tables:
- **`job_skills`:** `id`, `job_id`, `skill_id` (NULL = free text), `name`, `kind` (`required|preferred`), `weight` (1..10, required
  2 / preferred 1 by default, Q-14 later), `position`. It is unique on `(job_id, lower(name))`.
- **`job_status_history`:** `id`, `job_id`, `from_status` (NULL = created), `to_status`, `note`, `changed_by_user_id` (NULL = the
  migration), `created_at`.

The migration creates objects only when they are missing (the 0069 idiom). It moves the skills JSON into rows (SQL resolve by name, then
by alias). `downgrade()` refuses while rec-007 data exists, and it never maps the statuses back.

## 4. Scope and permissions (`services/recruiter_requirements.py`, the rec-003 inline pattern)
Read scope (any other role → 403, out of scope → 404):
- `placement_team` with a profile: requirements assigned to me, plus requirements of companies assigned to me.
- `placement_manager`: requirements assigned to a direct report, of a direct report's company, or unassigned on an unassigned company.
- `super_admin`: all. `bdm`: requirements of companies where I am the assigned BDM, read only.

| Action | Who |
|---|---|
| create | A recruiter creates for an own company, assigned to self. A manager creates for a company in scope; the assignee is from the team and defaults to the company's recruiter. super_admin can do either. The company must not be archived (409). |
| edit, status | Recruiter in scope, super_admin |
| assign | Manager, super_admin. The target is an active team recruiter (`locked_recruiter_target`). |

Every write follows the same steps: lock the row, check scope, apply the change, write the audit row (`recruiter_requirement.<action>`,
ids and field names only), commit once. The vacancies check is done under the lock: fewer than the job's hired/joined applications → 409.
Salary is returned only by the recruiter API and the owning employer's API, never to students.

## 5. API (§12AV) — `/api/v1/recruiter/requirements`
- `GET ''`: filters `q` (title / code / company), `status`, `company_id`, `assigned` (`me` / `unassigned` / uuid), `priority`,
  `job_category_id`, `deadline` (`expiring` / `expired`), plus `limit` and `offset`. Returns `{items,total,limit,offset}` ordered
  `created_at desc, id`.
- `POST ''` → 201 `{requirement}`.
- `GET /{id}` → `{requirement}`, including the skills and the history (newest first).
- `PATCH /{id}`: only the fields sent. A field sent with its stored value is not a change.
- `POST /{id}/status`: `{status, note?}`.
- `POST /{id}/assign`: `{recruiter_user_id}`.
- `GET /statuses`: keys, labels, transitions and vocabularies, for the UI.

Bodies use `extra="forbid"`. Experience or salary min > max → 422.

## 6. Web
- Nav: **Requirements** for recruiters and managers, and **Recruiter Requirements** for super admin.
- The pages are `/recruiter/requirements` (list, filters, pager), `/recruiter/requirements/new?company_id=` and
  `/recruiter/requirements/[id]` (detail, edit, status change with note, assign, history, flagged skills).
- The company detail page gains a Requirements section with "+ Add Job Requirement".
- The employer jobs panel shows `status_label`.

## 7. Acceptance criteria
1. Every §6 field is captured, apart from Recruiter contact (J5). The code is server-assigned.
2. Every status change is in `job_status_history` with its actor and note. Disallowed moves → 409.
3. Students see open jobs only when the status is in the open set and the deadline has not passed.
4. The EMP-002 tests pass through the shim.
5. Experience min > max → 422; vacancies below the joined count → 409; an out-of-scope id → 404; `hr_team` / `it_admin` / employer → 403.
6. Legacy skills are migrated: resolved through aliases, unmatched ones flagged. Legacy statuses are mapped, with history.
7. The pages work on desktop, tablet and mobile, with loading, empty and error states.

## 8. Phase 1 classification
- **MUST CHANGE:** `models.py` (Job, JobSkill, JobStatusHistory), `schemas.py`, the new API and service, `main.py`, the migration,
  `employer.py` (shim and skill sync), `workflows.py` (job routes), `public.py` and `portal.py` (the open set), `seed.py`, the new web
  pages, `navigation.ts` and `EmployerJobsPanel`.
- **MAY CHANGE:** the company detail component and `HrShortlistPanel` (label).
- **SHOULD NOT CHANGE:** `bdm_metrics` (it reads offers, not job status), `lookups.py`, `admin.py`, JobApplication / Interview / Offer.
- **HIGH REGRESSION RISK:** the EMP-002/004/005, ADM-007/008, BDM-021, RPT-001 and ENH-031 tests. Their Job fixtures use
  `status="open"`, which now violates the CHECK, so they move to `requirement_received`. Also the student open-jobs and apply paths.
