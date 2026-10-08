# rec-006 implementation plan

> **For agentic workers:** use superpowers:executing-plans (native; the owner asked for one uninterrupted session).

Spec: `docs/superpowers/specs/2026-10-08-rec-006-skills-master-design.md`. Use TDD for every task: write the test, see it fail,
implement, see it pass. Lite backend tests run in the api-test container, and web tests run in the web-test container (memory:
worktree-api-test-mount-path).

**Global constraints:**
- No new dependencies.
- Follow the inline role-check pattern (`User.role`).
- Bodies are parsed with `services/telecaller._parse`.
- Use the paging shape `{items,total,limit,offset}`.
- The route owns the commit, with one `AuditLog` per write.
- Numbering: 0102 / DEC-SCOPE-118 / §12AK / RBAC §2.44.

| # | Task | Tests first | Files |
|---|---|---|---|
| 1 | Models (5) + migration 0102 (guarded create, idempotent seed, guarded downgrade) | `test_rec_006_migration.py`: chain/head, model↔migration, seed 37/5/9/1 + JS tag, seed idempotent, downgrade refusal (throwaway DB) | `models.py`, `alembic/versions/0102_skills_master.py` |
| 2 | Schemas + `services/skills.py` (`normalise`, `resolve`, role helpers, term guards, batched shaping) | `test_rec_006_service.py`: resolve by name/alias/case/whitespace, inactive → None, name beats alias | `schemas.py`, `services/skills.py` |
| 3 | `api/recruiter_skills.py` + `main.py`: categories GET/POST/PATCH | `test_rec_006_api.py` (categories) | as named |
| 4 | Skills GET list/one, POST, PATCH (tags replace, category FOR SHARE, name ↔ alias 409) | `test_rec_006_api.py` (skills) | as named |
| 5 | Aliases and related links: POST/DELETE, 409/422/404, audit | `test_rec_006_api.py` (aliases, related) | as named |
| 6 | RBAC sweep: readers/writers/403 (hr_team, it_admin, counselor), reader sees active only | `test_rec_006_rbac.py` | — |
| 7 | Web: `lib/recruiterSkills.ts`, nav entries | `navigation.recruiter.test.ts`, `recruiterSkills.test.ts` | `lib/*` |
| 8 | Web: `RecruiterSkillsPanel` (+ `RecruiterSkillCategories`, `RecruiterSkillDetail`), two pages | `RecruiterSkillsPanel.test.tsx` | `components/*`, `app/recruiter/skills`, `app/recruiter/manager/skills` |
| 9 | e2e `rec-006-skills-master.spec.ts` (manager CRUD, alias 409, recruiter read-only, mobile) | e2e | `tests/e2e` |
| 10 | Docs: DEC-SCOPE-118, API §12AK, RBAC §2.44, backlog status, QA report | — | `docs/**` |

## Review focus (tests pinned in the owning task)
1. An alias that differs from an existing skill name only by case or spacing ("  core   JAVA ") → 409 (Task 5).
2. Renaming a skill to an existing alias of *another* skill → 409; renaming it to its own alias → 409 as well, because the alias
   must be removed first (Task 4).
3. A deactivated skill disappears from `resolve()` and from recruiter reads, but its aliases stay reserved: they cannot be reused
   for another skill (Task 5).
4. Two concurrent writes of the same alias are decided by the unique index → exactly one 201 (Task 5, sequential stand-in: the
   index name maps to 409).
5. A reader's `?active=false` still returns active rows only (Task 6).

## Phase 3 review notes (folded into the tasks)
- **API:**
  - Shapes and status codes follow tel-002: 201 on POST, 204 on DELETE, 405 for DELETE on a skill or category (no route), and
    404 before 422 for an unknown parent.
  - `tag_category_ids`: a unique list of at most 10 UUIDs. A repeated id → 422.
  - `GET /skills/{id}`: an inactive skill → 404 for a reader, so an existence probe leaks nothing.
  - `q` goes through `lookups._pattern`, a literal substring with LIKE escaping.
  - Alias search uses `EXISTS` on `skill_aliases`, so a skill with many matching aliases is not counted twice.
- **Transactions:**
  - Every name or alias write takes `pg_advisory_xact_lock(290_118)` before the cross-table check, and the unique indexes stay
    the final arbiter (409 via `flush_unique`).
  - A category set as primary or tag is locked `FOR SHARE` (the P4 idiom).
- **Security:**
  - The catalogue is global, so there is no row scope and no IDOR surface beyond the role checks.
  - Writes are limited to `placement_manager` and `super_admin`. Every other role gets 403 before the body is parsed.
  - Inputs are length-capped and control characters are refused. React escapes on output, so there is no XSS.
  - Requests use cookie auth with the existing CSRF/same-site posture; nothing new is added.
  - Audit metadata holds no personal data, and logs carry ids only.
- **Frontend:**
  - The panel reuses the tel-002 panel idioms: URL state, `useFocusAfterRender`, the in-flight ref, the `.telecaller-list`
    mobile cards, `CreateJumpLink`, `SearchableSelect` server mode and `sendJson`.
  - Alias and related chips are buttons with `aria-label="Remove alias J2EE"`.
  - The detail card is a region labelled by the skill name. Focus moves to its heading when it opens.
