# rec-009 — Candidate master (design)

Backlog: `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-009. Source: EVID-018 §8 (lines 390–434), §9 (436–473), quick action "+ Add
Candidate" (46), S2-§13 (1541–1561), S2-§20 (1750, 1778). Depends on rec-001 (merged PR #143) and rec-002 (merged PR #146).

**Status: MERGED** as PR #155 @ `e234f31f` (2026-10-08).
**Numbering (final at merge, 2026-10-08):** `DEC-SCOPE-122`, migration `0107_candidates` (after rec-003's `0106_rec_companies`),
API §12AP, RBAC §2.48. It was drafted as `0105` / `DEC-SCOPE-120` / §12AN / §2.46. upc-001, rec-006, upc-003 and rec-003 merged to
`main` first.

## 1. Owner answers and recorded defaults
| ID | Question | Answer | Authority |
|---|---|---|---|
| Q-07 | Duplicate rule | Normalised mobile **or** lower-cased email, across every candidate (archived ones too). A match **blocks** the create or edit with 409 and a panel naming the existing candidate. No merge tool. | EXPLICIT_APPROVAL (owner, 2026-10-08) |
| Q-08 | Candidate Status | Set **by hand**. The values are `available` (the default), `interviewing`, `placed`, `not_looking` and `do_not_contact`. rec-017 may later derive or suggest it. | EXPLICIT_APPROVAL (owner, 2026-10-08) |
| Q-09 | Resume format and retention | PDF or DOCX, at most 5 MB (the `/public/career-upload` limit), with the type judged from the file bytes. **Retention and the erasure path stay `NEEDS_CONFIRMATION`** (DEC-PRIV-001), and nothing is deleted automatically. | Recommended default (user: "proceed with recommended answers") |
| Q-31 | `CareerApplication` → candidates | Not in rec-009. Public submissions stay where they are. | Recommended default |
| Q-32 | Candidate CSV import | Manual entry only. | Recommended default |
| — | `hr_team` | **Read** (list, detail, resume download), as the backlog's rec-009 roles line says. This opens these `/recruiter/candidates*` routes to `hr_team`, the "later item decides" case Q-28 left open. | Backlog text |

## 2. Scope
In scope:
- The `candidates` table with every §8 field, the code sequence, the source (catalogue) and source detail, and the pool flags
  (`user_id` and `opted_in`, both unused until rec-010).
- Versioned resumes.
- Create, edit, archive and restore.
- The duplicate block with a panel.
- The list (source shown, S2-§13), the detail, and the create form.

Out of scope, each owned by a later item:
- Skills: rec-011.
- Extraction: rec-012.
- Search by skill and full text: rec-013 and rec-014.
- Applications: rec-017.
- Timeline: rec-025 to rec-027.
- Opt-in: rec-010.
- Retention and erasure: Q-09.

The detail page shows only Profile and Resume. It has no empty tabs for later items.

## 3. Data (migration `0107_candidates`)
**`candidates`**
| Column | Type | Rule |
|---|---|---|
| `id` | uuid PK | |
| `candidate_code` | varchar(12) unique not null | `CAN-` + 6 digits from the sequence `candidate_code_seq` |
| `name` | varchar(160) not null | 2–160 characters, trimmed |
| `mobile` / `mobile_normalized` | varchar(40) / varchar(20) | Optional. When given, `notifications.phone.normalise_phone` must accept it (E.164), else 422. Partial unique index `uq_candidates_mobile` on `mobile_normalized` |
| `email` | varchar(255) | Optional, stored lower-cased. Partial unique index `uq_candidates_email` on `lower(email)` |
| — | CHECK `ck_candidates_contact` | `mobile IS NOT NULL OR email IS NOT NULL` |
| `location`, `qualification`, `preferred_role` | varchar(120) | Optional |
| `college`, `current_company` | varchar(200) | Optional |
| `passing_year` | smallint | 1950–2100 |
| `experience_months` | int | 0–600 (total experience) |
| `current_salary`, `expected_salary` | numeric(12,2) | ≥ 0, an amount per year (no currency is stored; the source names none) |
| `notice_days` | smallint | 0–365 |
| `preferred_locations` | JSON list | 0–10 places, each 1–80 characters, de-duplicated case-insensitively |
| `linkedin` | varchar(300) | `http(s)://` only, so the link is never a `javascript:` URL |
| `source_id` | FK → `rec_candidate_sources` RESTRICT, not null | Must be **active** on create, or when it changes on edit |
| `source_detail` | varchar(200) | Free text, e.g. "Edusphere Python Full Stack Course" (§9 example) |
| `status` | varchar(20) not null default `available` | CHECK in the Q-08 values |
| `user_id` | FK → users, unique, nullable | rec-010 links it. It is never set by these routes |
| `opted_in` | bool not null default false | rec-010 |
| `created_by_user_id` | FK → users not null | "owner (who added)" |
| `updated_by_user_id` | FK → users | |
| `archived_at`, `archived_by_user_id` | | Archive is reversible; nothing is deleted |
| timestamps | | |

Indexes: `ix_candidates_source_id`, `ix_candidates_status`, `ix_candidates_created_at`.

**`candidate_resumes`** (append-only)
- Columns: `id`; `candidate_id` FK RESTRICT; `version` int; `storage_key` varchar(300); `content_type`; `file_name` varchar(255)
  (display only); `size_bytes`; `uploaded_by_user_id`; `created_at`.
- `UNIQUE (candidate_id, version)`.
- The **current** resume is the highest version (AC4: "versioned, only one current").

The migration creates its objects with guards (the 0076 idiom). `downgrade()` refuses while any candidate exists.

## 4. Pool filter and roles
- `services/candidates.pool_filter()` returns `user_id IS NULL OR opted_in`. Every read applies it, so the backfilled students of
  rec-017 who have not opted in never surface. A candidate outside the pool reads as 404.
- **Writers:** `placement_team` (every recruiter edits the whole pool, R11), `placement_manager`, `super_admin`.
- **Readers:** the writers plus `hr_team`.
- **Everyone else gets 403**, including `employer`, `it_admin` and students. The role check runs before anything is read (the
  inline RBAC convention).

## 5. API (§12AP). Prefix `/api/v1/recruiter/candidates`
| Method | Path | Who | Result |
|---|---|---|---|
| GET | `` | readers | `q` (name, code, email, mobile digits), `source_id`, `status`, `archived` (default false), `limit`, `offset` → `{items,total,limit,offset}`, newest first. Item: `id, candidate_code, name, location, experience_months, preferred_role, source{id,name,active}, source_detail, status, archived, created_at` |
| GET | `/duplicate-check` | writers | `mobile`, `email`, `exclude_id` → `{matches}`. The live panel on blur; the create and the edit re-check |
| POST | `` | writers | → 201 detail. 409 `{code:"duplicate_candidate", message, matches}` |
| GET | `/{id}` | readers | detail = every field + `source`, `created_by`, `updated_by`, `archived_at`, `resumes[]` (newest first: `version, file_name, content_type, size_bytes, uploaded_by, created_at`), `can_edit` |
| PATCH | `/{id}` | writers | partial update. Archived → 409 "Restore this candidate first". Duplicate → 409 panel |
| POST | `/{id}/archive`, `/{id}/restore` | writers | → detail. Already in that state → 409 |
| PUT | `/{id}/resume` | writers | multipart `file` → 201 `{version,…}`. Archived → 409. Empty file → 422, over 5 MB → 413, wrong type → 415 |
| GET | `/{id}/resume/{version}` | readers | The file. `Content-Disposition: attachment; filename="resume-CAN-000001-v2.pdf"`. The audit row is committed before any byte is sent |

- **Match panel row:** `id, candidate_code, name, source_name, status, archived, matched_on[]`. Recruiters can already see every
  candidate (R11), so there is no hidden count, and contact data is not echoed.
- **Bodies:** untyped dicts parsed by `services/telecaller._parse` (`extra="forbid"`), so a 422 is one sentence that names the
  field. "Enter a mobile number or an email" covers AC-neg-1.
- **Concurrency:**
  - The unique indexes are the duplicate backstop. On an `IntegrityError` the route rolls back, re-reads the matches and answers
    the same 409.
  - The resume version is taken under the candidate's `FOR UPDATE` lock, with the unique pair as the backstop.
  - The file is stored before the lock and discarded if the transaction fails.
  - The archive, restore and edit routes lock the row.
- **Audit (no PII in metadata):** `candidate.create`, `candidate.update` (changed field names), `candidate.archive`,
  `candidate.restore`, `candidate.resume_upload` (version), `candidate.resume_download` (version, role).
- **Logs:** ids only.

## 6. Web
- **`lib/recruiterCandidates.ts`:** types, URLs, status labels, and the form ⇄ body mapping.
- **`/recruiter/candidates`:** a server page. It resolves the role's nav:
  - recruiter → `RECRUITER_NAV`
  - manager → `RECRUITER_MANAGER_NAV`
  - super_admin → `SUPER_ADMIN_NAV`
  - hr_team → `PORTAL_NAV["it/hr"]`
  - any other role → access denied

  The `RecruiterCandidateList` client component has search, a source and status filter, an "Archived" toggle, a table on desktop
  and cards on narrow screens, Previous/Next paging, and "+ Add candidate" for writers. The source is shown in every row.
- **`/recruiter/candidates/new`:** `RecruiterCandidateForm` in create mode. It has the §8 fields in source order, a source picker
  (`activeValues("candidate-sources")`), a duplicate panel above the form (tel-005 QA-05) with "Open candidate", and the live check
  on blur. A double-click sends one request.
- **`/recruiter/candidates/[id]`:** a profile view (definition list), "Edit" (the same form in edit mode), Archive/Restore with a
  confirm, and a Resume card: an upload (PDF or DOCX, 5 MB) and the version list with download links, the current one marked.
  `hr_team` sees no write controls (`can_edit`).
- **Nav:** "Candidates" in `RECRUITER_NAV` and `RECRUITER_MANAGER_NAV`, "Recruiter Candidates" in `SUPER_ADMIN_NAV`, and
  "Candidate Master" in `it/hr`.

## 7. Acceptance criteria (testable)
1. Every §8 field is captured and read back (AC1).
2. The source is required on create (422 without it, or with an inactive one) and shown in the list (AC2, S2-§13).
3. A duplicate mobile (any format of the same number) or email (any case) → 409 with the existing candidate in the panel. An edit
   into a duplicate → 409 (AC3, Q-07).
4. A resume upload creates v1, then v2; v2 is current, and both download. Downloads are audited (AC4).
5. Neither mobile nor email → 422. An employer → 403, and so do `it_admin` and a student. `hr_team` reads but cannot write (403).
6. An archived candidate is hidden from the default list, listed with `archived=true`, cannot be edited, and can be restored.
7. A candidate outside the pool (`user_id` set, not opted in) → 404 and not listed.
8. A non-PDF/DOCX file → 415, over 5 MB → 413, empty → 422.

## 8. Tests
- **Backend:**
  - `test_rec_009_migration.py`: tables, indexes, the CHECK, the sequence, and the downgrade guard.
  - `test_rec_009_candidates.py`: roles, create, list and filters, detail, edit, duplicates including the race backstop,
    archive and restore, the pool filter.
  - `test_rec_009_resumes.py`: types, size, versions, download and audit, archived.
- **Web:**
  - vitest for the lib mapping and the form's duplicate panel.
  - Playwright `rec-009-candidates.spec.ts`: create with a duplicate block, upload a resume, the list shows the source,
    hr_team is read-only.

## 9. Risks
- Migration numbering collides with the parallel rec-003 and rec-006 work; re-chain at merge.
- The route-inventory/RBAC sweep tests may need a row per new route.
- `hr_team` access widens Q-28's closed `/recruiter/*` for these pages only.
