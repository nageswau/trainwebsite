# rec-009 Candidate master — Implementation Plan

> **For agentic workers:** executed inline (superpowers:executing-plans) by the session that wrote it. Steps use `- [ ]`.

**Goal:** One central candidate master: `candidates` + versioned `candidate_resumes`, recruiter API, list/create/detail pages.
**Architecture:** New tables (migration `0105_candidates`, provisional), `services/candidates.py` (roles, pool filter, validation,
duplicates, storage), `api/recruiter_candidates.py` (inline role check → scope → write → audit → one commit), web pages under
`/recruiter/candidates`.
**Tech stack:** FastAPI + SQLAlchemy async + Alembic + Postgres; Next.js App Router + vitest + Playwright.
**Spec:** `docs/superpowers/specs/2026-10-08-rec-009-candidate-master-design.md`.

## Global constraints
- Inline RBAC (`User.role` check before any read); readers = placement_team, placement_manager, super_admin, hr_team; writers = the
  first three. Everyone else 403. Out-of-pool / unknown id 404.
- Q-07 block (409 `duplicate_candidate` + matches); Q-08 statuses `available, interviewing, placed, not_looking, do_not_contact`.
- Resume: PDF or DOCX by bytes, ≤ 5 MB; 413 / 415 / 422 empty.
- Logs and audit metadata carry ids and field names only — never name, email, mobile.
- Never alter existing tables, `PlacementProfile`, `CareerApplication`, `/workflows/it/*`, EMP-003.

## Review focus
1. Same mobile typed differently (`+91 98765 43210` vs `09876543210`) → duplicate (test in Task 2).
2. Two concurrent creates of one email → one 201, one 409 (unique index backstop; test in Task 2).
3. A PDF renamed `.docx` / a ZIP that is not DOCX → judged by bytes (Task 3).
4. PATCH that clears both mobile and email → 422, not a DB CHECK 500 (Task 2).
5. `linkedin: "javascript:alert(1)"` → 422 (Task 2).

---

### Task 1: Migration + models + schemas
**Files:** create `apps/api/alembic/versions/0105_candidates.py`, `apps/api/tests/test_rec_009_migration.py`; modify
`apps/api/app/models.py` (Candidate, CandidateResume), `apps/api/app/schemas.py` (CandidateCreate/Update, labels, statuses).
- [ ] RED: migration test asserts tables, `uq_candidates_mobile`, `uq_candidates_email`, `ck_candidates_contact`, the sequence,
  `uq_candidate_resumes_version`; downgrade refuses while a candidate exists.
- [ ] GREEN: guarded creation (0076 idiom); `down_revision = "0102_rec_catalogues"`.
- [ ] Commit.

### Task 2: Service + candidate routes
**Files:** create `apps/api/app/services/candidates.py`, `apps/api/app/api/recruiter_candidates.py`,
`apps/api/tests/test_rec_009_candidates.py`; modify `apps/api/app/main.py`.
**Produces:** `require_reader(user)`, `require_writer(user)`, `pool_filter()`, `find_matches(db, mobile_key, email_key, exclude_id)`,
`duplicate_conflict(matches)`, `next_code(db)`, `detail_out(...)`, `item_out(...)`.
- [ ] RED: roles (each outsider 403; hr_team GET 200, POST 403), create all §8 fields round-trip, source required/active, no
  contact 422, duplicate mobile (other format) and email (other case) 409 with panel, edit into duplicate 409, race (two creates
  via `asyncio.gather`) one 409, list filters (`q`, `source_id`, `status`, `archived`), archive/restore/409s, edit archived 409,
  out-of-pool 404, `linkedin` scheme 422, audit rows without PII.
- [ ] GREEN, run, commit.

### Task 3: Resumes
**Files:** extend service + router; create `apps/api/tests/test_rec_009_resumes.py`.
- [ ] RED: PDF v1, DOCX v2 → current v2, both download with code-based filename; audit `candidate.resume_download`; PNG 415; zip
  without `word/document.xml` 415; >5 MB 413; empty 422; archived 409; hr_team download 200, upload 403.
- [ ] GREEN (`read_resume`, `store`/`discard` under `candidate-resumes/`), commit.

### Task 4: Web lib + list page + nav
**Files:** create `apps/web/lib/recruiterCandidates.ts`, `apps/web/app/recruiter/candidates/page.tsx`,
`apps/web/components/RecruiterCandidateList.tsx`, `apps/web/components/RecruiterCandidateShell.tsx` (role → nav),
`apps/web/tests/lib/recruiterCandidates.test.ts`; modify `apps/web/lib/navigation.ts` (+ its recruiter nav test).
- [ ] RED vitest: `candidateBody` mapping (numbers, list split, empty → null on edit), `experienceLabel`, nav entries.
- [ ] GREEN, commit.

### Task 5: Create form + detail page + resume card
**Files:** create `apps/web/app/recruiter/candidates/new/page.tsx`, `apps/web/app/recruiter/candidates/[id]/page.tsx`,
`apps/web/components/RecruiterCandidateForm.tsx`, `apps/web/components/RecruiterCandidateDetail.tsx`,
`apps/web/components/RecruiterCandidateResumes.tsx`, `apps/web/tests/components/RecruiterCandidateForm.test.tsx`.
- [ ] RED vitest: 409 shows the duplicate panel with "Open candidate"; missing name/source/contact shows one message, no request.
- [ ] GREEN, tsc + eslint, commit.

### Task 6: E2E + docs
**Files:** create `apps/web/tests/e2e/rec-009-candidates.spec.ts`; modify `docs/decisions/PRODUCT_DECISION_REGISTER.md`
(DEC-SCOPE-120), `docs/architecture/API_CONTRACT.md` (§12AN), `docs/architecture/RBAC_MATRIX.md` (§2.46),
`docs/delivery/RECRUITER_CRM_BACKLOG.md` (status).
- [ ] e2e: recruiter creates Rahul (source Edusphere students, detail "Edusphere Python Full Stack Course"), duplicate blocked,
  uploads a PDF resume, list shows the source; hr_team sees no "Add candidate".
- [ ] Commit.
