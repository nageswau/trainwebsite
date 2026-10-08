# upc-004 Duplicate prevention + BDM university-org link: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native/inline execution chosen by the owner's standing
> instruction). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Block duplicate universities (normalised name + country) behind a 5-field panel, with an audited head/super_admin override,
and let BDM University organisations link to the master.

**Architecture:** `University.name_key` is kept by a model hook and indexed with `country_id`. The service function
`partnership_universities.find_duplicates` serves the master routes, the new `duplicates` route and the BDM create route. The BDM link
is a nullable FK with a CHECK. The web side reuses the existing forms plus one shared `UniversityMatchList`.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (Postgres), Next.js/React, pytest, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-08-upc-004-university-duplicates-design.md`

## Global Constraints
- Authorization stays inline (role check, then scope, then write). One commit per write, with the audit row in the same transaction.
  Logs carry ids only.
- `409 university_duplicate {message, matches, total, can_override}`. The override needs `duplicate_reason` of 10–500 characters, from
  `partnership_head`/`super_admin` only.
- BDM `409 possible_duplicate` keeps its existing keys and adds `university_matches` and `university_total`.
- Migration `0106_university_duplicates` on top of `0105_university_master`. Every step is guarded (0001 `create_all` builds fresh
  databases).
- No new dependencies.

## Review Focus
1. Names that differ only by case, extra spaces or full-width characters → treated as the same (test: "  abc   UNIVERSITY ").
2. A rename on PATCH into an existing name → 409 (test in Task 3).
3. A BDM changes the org type from University to College while linked → the link is cleared, not a 500 (CHECK) (test in Task 4).
4. A head sends a reason when nothing matches → normal create, no override audit row (test in Task 3).
5. A legacy `/admin/universities` create → `name_key` is set, so it is later detected (test in Task 1).

---

### Task 1: Key + model + migration
**Files:** `app/core/identifiers.py` (add `normalize_key`), `app/services/bdm_organizations.py` (import it), `app/models.py`
(`University.name_key` + `@validates`, index; `BdmOrganization.university_id` + index + CHECK),
`alembic/versions/0106_university_duplicates.py`, `tests/test_upc_004_migration.py`, `tests/test_upc_003_migration.py` (the head
assertion becomes the "single head + HEAD in walk" idiom).
- [ ] RED: tests that `University(name="  ABC  University ")` sets `name_key == "abc university"`; the model columns, index and CHECK
  exist; the migration chains after 0105 and is the single head; an isolated database round trip backfills `name_key` and logs the
  duplicate report; the downgrade refuses while a link exists.
- [ ] GREEN: implement. The migration backfills via Python `normalize_key` per row, then sets NOT NULL, creates the index, adds the FK
  column + index + CHECK, and logs the counts.
- [ ] Run the focused tests and commit.

### Task 2: Service + duplicates endpoint
**Files:** `app/services/partnership_universities.py` (`MAX_MATCHES=10`, `name_key_of(name)`, `find_duplicates(db, name_key,
country_id|None, exclude_id|None) -> (list[dict], int)`, `match_out`, `OVERRIDE_ROLES`, `lock_key(db, country_id, name_key)`,
`linked_bdm_organizations(db, id)`), `app/schemas.py` (`UniversityMatch`, `UniversityMatchPage`, `LinkedBdmOrganization`; `UniversityDetail.linked_bdm_organizations`),
`app/api/partnership_universities.py` (`GET /duplicates` before `/{university_id}`), `tests/test_upc_004_duplicates.py`.
- [ ] RED: role 403s (BDM, counselor); case/spacing match; another country is not a match; an inactive row is a match; `exclude_id`;
  a blank name gives 422; detail includes `linked_bdm_organizations`.
- [ ] GREEN, run, commit.

### Task 3: Create/PATCH blocking + override
**Files:** `app/schemas.py` (`UniversityCreate/Update.duplicate_reason`), `app/api/partnership_universities.py`, test file from Task 2.
- [ ] RED: AC1 "abc university" vs "ABC University" gives 409 with matches and `can_override` (true for the head, false for
  overseas_admin); overseas_admin with a reason gives 409; the head with a reason gives 201 plus a `university.duplicate_override` audit
  with the reason; a 9-character reason gives 422; a reason with no match gives no override audit; a PATCH rename into a duplicate gives
  409; a PATCH with an unchanged name is not checked; a PATCH country move into a duplicate gives 409.
- [ ] GREEN: `_check_duplicates(db, user, name, country_id, reason, exclude_id) -> int` takes the advisory lock, raises the 409 or
  returns the match count; the routes audit the override.
- [ ] Run upc-003 + upc-004 tests, commit.

### Task 4: BDM link
**Files:** `app/schemas.py` (`BdmOrganizationCreate/Update.university_id`, `BdmOrgUniversityRef`, `BdmOrganizationOut.university`),
`app/api/bdm_organizations.py`, `app/services/bdm_organizations.py` (`organization_out` adds `university`; `duplicate_conflict` takes
university matches), `tests/test_upc_004_bdm_link.py`.
- [ ] RED: a college BDM creating a University org named like a master row with no confirm gets 409 with `university_matches`; confirm
  without a link gives 201 unlinked; with `university_id` gives 201 linked and the detail `university` is set; an unknown id gives 422;
  `university_id` with org_type college gives 422; PATCH link/unlink; a type change to college clears the link; a non-University create
  never queries the master; the master detail lists the linked org.
- [ ] GREEN, run the bdm-002/003 suites + the new tests, commit.

### Task 5: Web
**Files:** `apps/web/lib/universities.ts` (types, `duplicatesUrl`, `universityDuplicate(detail)`), `components/UniversityMatchList.tsx`,
`components/UniversityForm.tsx`, `app/partnership/universities/[id]/page.tsx`, `lib/bdmOrganizations.ts` (`OrgDuplicate.university_matches`,
`Organization.university`), `components/BdmOrganizationForm.tsx`, `components/BdmOrganizationDetail.tsx`, vitest under `tests/components`.
- [ ] RED vitest: MatchList renders "—" for the untracked fields and the manager names; UniversityForm shows the pre-check panel after
  debounce and the override reason flow on 409 (can_override true/false); BdmOrganizationForm "Link and save" resends with
  `university_id` + `confirm_duplicate`.
- [ ] GREEN, `tsc`, `eslint`, vitest, commit.

### Task 6: E2E + docs
**Files:** `apps/web/tests/e2e/upc-004-university-duplicates.spec.ts`; docs: `PRODUCT_DECISION_REGISTER.md` DEC-SCOPE-121,
`API_CONTRACT.md` §12AO, `RBAC_MATRIX.md` §2.47, `DATA_MODEL.md`, the backlog upc-004 status.
- [ ] Playwright AC1/AC2 against the docker stack, commit.
