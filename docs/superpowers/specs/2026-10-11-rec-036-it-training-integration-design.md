# rec-036 — IT-training ↔ recruiter integration (design)

- **Backlog:** `docs/delivery/RECRUITER_CRM_BACKLOG.md` § rec-036. Dependencies rec-010 (PR #182) and rec-011 (PR #180) are merged.
- **Evidence:** EVID-018 §27 (Lead → IT Student → Trained Candidate → Recruiter Candidate → Placed Candidate), §9 (source detail =
  course), S2-§17 ("Course Completed" skill source), S2-§20 ("500 Java students … Java talent pool", after opt-in). R4 (opted-in only).
- **Decision:** `DEC-SCOPE-179` — CI1–CI8 below are **recommended defaults, UNVERIFIED** (the owner asked the session to proceed with the
  recommended answers; Q-11 and the Q-13 part for course skills stay open for confirmation).
- **Numbers:** migration `0149_program_skills`, API §12CT, RBAC §2.105 (re-checked against `main` at Phase 9).

## 1. Recommended defaults (Q-11, Q-13, edge cases)

| # | Question | Default |
|---|---|---|
| CI1 | Who maintains a program's skill tags (Q-11)? | `it_admin` and `super_admin`, on the IT admin Programs page. Tags are Skills Master skills (active), at most 30 per program. |
| CI2 | What counts as "completed"? | The student holds an **issued certificate** for the program (`certificates.status = 'issued'`). Enrolment status alone does not. |
| CI3 | When are course skills added? | (a) on opt-in, (b) when a certificate is issued to an opted-in student, (c) when a tag is added to a program, for its opted-in completers. Never for a candidate who is not opted in, or is archived. |
| CI4 | Status of a course skill (Q-13)? | `verified`, verified by the certificate's approver at the time of the grant; a certificate with no approver gives `claimed`. Level `beginner` (a recruiter adjusts). Source `course_completed`. |
| CI5 | The candidate already has the skill? | A `claimed` row (any source) is upgraded to `course_completed` + the CI4 status — stronger evidence wins (the SK7 rule). A `verified`/`assessed` row is left alone. The 100-skill cap (SK6) holds. |
| CI6 | A program re-tagged after students completed it? | **Additive.** A new tag reaches existing completers; a removed tag never deletes a candidate's skill (it may have been edited or verified since). |
| CI7 | Journey view | Read-only, `GET /recruiter/candidates/{id}/journey`, candidate readers (rec-009 `READERS`, hr_team included). The pool filter applies: a non-opted-in student is a 404. |
| CI8 | Skill merge (rec-006/SK7) | Program tags move to the kept skill like requirement skills do (a program with both keeps one). |

## 2. Data

`program_skills` (new): `program_id` → programs (CASCADE), `skill_id` → skills (RESTRICT), PK (program_id, skill_id),
`added_by_user_id` → users, `created_at`. Index on `skill_id` (merge and the grant's join). No existing row changes; nothing to
backfill (no tags exist yet). Downgrade refuses while rows exist.

## 3. Backend

- `services/course_skills.py`
  - `program_skills_out(db, program_id)`, `set_program_skills(db, user, program, skill_ids)` (replace the set; 422 on an unknown or
    inactive skill or more than 30; returns added ids).
  - `grant(db, actor, candidates_ids, program_ids=None)` — for each opted-in, non-archived candidate (locked FOR UPDATE in id order, so
    it serialises with rec-011 writes), every tagged active skill of each program they hold an issued certificate for, applying CI4/CI5.
    One audit row per changed candidate (`candidate.skill_course_grant`, skill ids only). Returns rows touched.
  - Hooks: `for_student(db, actor, student_id, program_id=None)` (opt-in, certificate issue) and `for_program(db, actor, program_id, skill_ids)`.
  - `journey(db, candidate)`.
- `placement_pool.opt_in` calls the grant after the opt-in (before the profile seed, so course skills are created as course skills).
- `workflows.issue_certificate` calls the grant for the student and program after the certificate flush, in the same transaction.
- `skills.absorb` re-points `program_skills` (CI8).
- Routes: `GET/PUT /admin/programs/{id}/skills`, `GET /admin/programs/skill-options?q=` (it_admin is not a Skills Master reader, Q-28,
  so the editor gets its own name lookup: active skills, id/name/category, 20 rows), `GET /recruiter/candidates/{id}/journey`.

### Journey shape

```
{ "lead": {lead_code, source, created_at, converted_at} | null,
  "enrolments": [{program, batch, enrolled_on, status}],
  "certificates": [{program, certificate_no, issued_on}],
  "candidate": {added_at, opted_in_at | null},
  "applications": {count, first_at | null},
  "placements": [{company, position, joined_on}] }
```

The lead is the enquiry converted to the candidate's user (`enquiries.converted_user_id`, unique). External candidates (no user) have
no lead, enrolments or certificates. No phone, email or message text of the lead is returned.

## 4. Frontend

- `AdminProgramManagementPanel`: a "Skills" button per row opens an inline tags editor (SearchableSelect over the admin lookup, chips
  with remove, Save). Loading, empty, error and saved states; the server's sentence on a refusal.
- `RecruiterCandidateJourney` card on the candidate detail (between Skills and Resumes): an ordered list of the five §27 stages, each
  with its date(s) or "Not yet"; loading / error + Retry.

## 5. Security

Writes: it_admin/super_admin only (403 before any read). The journey follows rec-009 readers and the pool filter (IDOR: a non-pool
candidate is 404). Audit rows and logs carry ids only. Bodies parsed with Pydantic; SQL via the ORM.

## 6. Tests

API: tags GET/PUT (roles, 422s, replace semantics, audit), the three grant triggers (AC1, positive Java scenario via the rec-015 pool
membership or search), CI4/CI5/CI6, non-opted-in never gets or shows anything (negative), archived skipped, merge re-points tags,
journey stages with dates (AC2) and 403/404. Migration round trip. Vitest for the two components. Playwright e2e: admin tags a program,
the recruiter sees the course skill and the journey.
