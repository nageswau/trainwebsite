# rec-008 — JD management (design)

- **Feature ID:** `rec-008` (`RECRUITER_CRM_BACKLOG.md` §rec-008). **Dependency:** rec-007 (MERGED, PR #166).
- **Evidence:** `EVID-018` §7 (lines 350–388): "Recruiter should be able to upload or create a JD", the 14 JD fields, "📎 Upload JD and
  automatically connect it to the Job Requirement". Module scope `DEC-SCOPE-116` (R5: `jobs` is the requirement, with a child
  `job_descriptions` table that is versioned).
- **Decision:** `DEC-SCOPE-132`. Migration `0117_job_descriptions`, API §12AZ, RBAC §2.58.
- **Answers:** the owner told the session to proceed with the recommended answers, so JD1–JD9 below are **recommended defaults,
  `UNVERIFIED`**.

## 1. Decisions

| # | Point | Answer |
|---|---|---|
| JD1 | Versions | Every create, edit or upload writes a **new version row**. Rows are never edited or deleted. The previous current row is set `is_current = false` in the same transaction. A partial unique index allows one current row per requirement, and `(job_id, version)` is unique (AC2) |
| JD2 | JD number | One number per requirement, `JD-000001` from `jd_number_seq`. Version 1 takes it and later versions keep it. Shown as "JD-000001 · v2" |
| JD3 | Fields | `role` (required, ≤ 180), `experience` (text ≤ 120, e.g. "0–2 years"), `qualification` (≤ 300), `skills` (text ≤ 1000; the requirement's `job_skills` stay authoritative), `salary` (text ≤ 120), `location` (≤ 120), `description` (≤ 10000), `responsibilities` (≤ 5000), `requirements` (≤ 5000), `openings` (1–10000), `contact_id` (an active contact of the requirement's company, else `422`), `closing_date`. The company is the requirement's and is not stored again |
| JD4 | Create vs upload | **Create/edit:** `POST …/jd` with the fields. This is a new version, and the current version's file (if any) carries forward. **Upload:** `PUT …/jd/file` (multipart). This is a new version with the new file, and the current version's fields carry forward. With no JD yet, the fields come from the requirement (role←title, location, qualification, openings←vacancies, closing date←deadline, description). Either way the JD is linked to the requirement automatically (AC1). The web prefills a first create from the requirement |
| JD5 | Files | PDF or DOCX judged by the bytes (rec-009's sniffing), at most 5 MB: too big → `413`, empty → `422`, another type → `415`. rec-009 uses `415` for the same check. The backlog's AC3 says `422`, and this deviation is recorded here. Server-generated storage keys go under `job-descriptions/`. The download is authenticated and audited (`nosniff`, attachment `JD-000001-v2.pdf`), which is the rec-009 meaning of a "signed download". No public URL |
| JD6 | JD → requirement | The JD never overwrites the requirement silently. The tab's **Update requirement from JD** lists the differing mappable fields: title←role, location, qualification, vacancies←openings, deadline←closing date and description. Only on confirmation does it send the existing `PATCH /recruiter/requirements/{id}`, with all its validation. There is no new endpoint |
| JD7 | Who | Read = the requirement's read scope (§2.55: recruiter, manager, super_admin, assigned BDM). Out of scope = `404`. Write = the requirement's `can_edit` (the recruiter on it, super_admin): any other reader → `403`, a cancelled requirement → `409`. Employer access is **deferred**: the employer portal is unchanged. `hr_team` and other roles → `403` |
| JD8 | Closing date | A JD closing date different from the requirement deadline is allowed. The version carries `closing_date_differs`, and the tab shows a warning |
| JD9 | Follow-ups | No automatic "JD pending" follow-up (DEC-SCOPE-131 FU1 listed rec-008). rec-008 has no event to fire one from. A requirement without a JD is visible on its tab, and the `jd` follow-up reason stays manual |

## 2. Data (`0117_job_descriptions`)

`job_descriptions`:
- Columns: `id`, `job_id` (FK jobs, RESTRICT), `jd_number` (String 12), `version` (int ≥ 1), `is_current` (bool), and the JD3 fields.
- File columns: `storage_key`, `file_name`, `content_type`, `size_bytes` (all null for a version without a file).
- Also `created_by_user_id` and `created_at`.

Constraints:
- `uq_job_descriptions_version (job_id, version)`.
- `uq_job_descriptions_current (job_id) WHERE is_current`.
- `ix_job_descriptions_number (jd_number)`.
- CHECKs: version ≥ 1; openings NULL or 1–10000; the file columns all null or all set.

The `jd_number_seq` sequence is on the metadata, and the migration creates it if it does not exist. Creation is guarded (0001 builds from the models). `downgrade()` refuses while any JD exists.

## 3. API (§12AZ)

All routes are under `/recruiter/requirements/{id}`. The requirement resolves through `recruiter_requirements.load_scoped`.

| Method/Path | Behaviour |
|---|---|
| `GET …/jd` | `{jd_number, versions[] (newest first; the first is current), can_edit}`. Empty `versions` = no JD yet |
| `POST …/jd` | JSON fields (JD3), unknown keys `422` → `201` with the GET shape |
| `PUT …/jd/file` | multipart `file` → `201` with the GET shape. The file is stored before the row lock and discarded if the transaction fails |
| `GET …/jd/{version}/file` | the bytes. An unknown version or a version without a file → `404`. Audited before the bytes leave |

A version is:

```
{version, is_current, role, experience, qualification, skills, salary, location, description, responsibilities, requirements, openings,
 contact {id, name, active}|null, closing_date, closing_date_differs, file {name, content_type, size_bytes}|null, created_by, created_at}
```

- Writes lock the requirement row first, so concurrent writers serialise on the version number.
- Audit actions are `job_description.{create,upload,download}`, recording ids, the version, field names, type and size only.
- Log events are `job_description_created`, `job_description_uploaded` and `job_description_downloaded`.

## 4. Web

The requirement page fetches the JD alongside the requirement and renders a **Job description (JD)** section (`RecruiterRequirementJd`).
It covers these states:
- **Empty:** "No JD yet" with Create / Upload.
- **Current version:** a details list, the closing-date warning, and a download link.
- **Create/edit form:** prefilled from the current version, or from the requirement when there is none.
- **Upload:** PDF/DOCX up to 5 MB, with a client-side size check.
- **Version list:** download links.
- **JD6 confirm:** a diff list, then the PATCH.

Every write re-renders from the response. Errors show as `role="alert"`. The layout is responsive (the existing `form-grid` / `action-card` classes).

## 5. Tests

**Backend:**
- `test_rec_008_job_descriptions.py`: AC1, AC2, AC3, the cap, scope, roles, cancelled, contact validation, carry-forward, download audit and discard on failure.
- `test_rec_008_migration.py`.

**Web:**
- vitest `tests/lib/recruiterJd.test.ts`: prefill, body and diff.
- e2e `rec-008-jd.spec.ts`.

**Browser QA:** desktop, tablet and mobile.
