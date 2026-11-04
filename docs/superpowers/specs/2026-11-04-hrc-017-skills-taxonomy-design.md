# hrc-017 — Skills taxonomy expansion and required proficiency

**Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-017` (PDF §7.3 "IT, engineering, healthcare, pharmacy, finance, sales, HR
and non-IT"; §8 "category and proficiency"; PDF classified `UNVERIFIED`). Scope approved by the owner 2026-11-01 (backlog Q-00: all phases).
No dependency. The owner said to proceed with the recommended answers, so Q-17 and T1–T9 are **the builder's calls
(`NEEDS_CONFIRMATION`)**. Decision `DEC-SCOPE-388`, migration `0265_skill_taxonomy`, API §12KG. RBAC unchanged (no new grant).

## Builder's calls

| # | Call |
|---|---|
| T1 | A category belongs to one **domain**: `it` or `non_it` (`skill_categories.domain`, NOT NULL, server default `it`). Every existing category is `it` — the seed and every manager-made category so far came from the IT placement desk. |
| T2 | Q-17 (who supplies the non-IT lists): the builder seeds a **provisional** starter list (`NEEDS_CONFIRMATION`; the owner replaces it in the Skills Master UI, no code needed). Six `non_it` categories: Engineering, Healthcare, Pharmacy, Finance, Sales, Human Resources — 7–8 skills each, plus three aliases (GMP, Tally, CPR). |
| T3 | The seed is insert-if-missing like 0104: a category whose name already exists is reused as it is (its domain is not changed); a skill whose name is already a skill **or an alias** is skipped; an alias already used is skipped. The IT seed is untouched (backlog `+/−/E`). New categories sort after the existing ones. |
| T4 | Categories API: `domain` on every category row; `POST` takes an optional `domain` (default `it`); `PATCH` may change it. `GET /recruiter/skill-categories?domain=` and `GET /recruiter/skills?domain=` filter (a skill is in a domain when its primary category or one of its tags is — the `category_id` filter's rule). This is the category filter hrc-019 builds on; candidate search itself is hrc-019's. |
| T5 | `job_skills.min_level` (NULL = any level) is one of the candidate levels `beginner`, `intermediate`, `advanced`, `expert` (rec-011 SK1), ordered. |
| T6 | It is set with the rec-016 weights route: each item of `PUT /recruiter/requirements/{id}/skill-weights` may carry `min_level` (omitted = unchanged, `null` = any level). Same transaction, same `can_edit` rule, one audit row `recruiter_requirement.weights` listing changed skill ids, now with a `changes` diff of the levels. A free-text skill (not in the Skills Master) cannot take a level: 422. |
| T7 | Editing the skill lists on the requirement form keeps each kept skill's level (rows are updated in place by name); a removed skill loses it; the legacy flat-list writers (employer, `/workflows/it/jobs`) never touch it. A skill merge keeps it. |
| T8 | Matching (rec-016): a skill with a level counts only when the candidate holds that skill (or a related one, M3) **at that level or above**; a required skill with a level is therefore part of the hard filter. Points and weights are unchanged. |
| T9 | Output: the requirement detail's `skills[]` and the matches `criteria.skills[]` gain `min_level`. Web: the detail lists "Python · intermediate or above"; the "Adjust weights" form gains a "Minimum level" select per Skills-Master skill; the Skills Master gains a domain column + "Move to Non-IT / IT" action on categories, a domain select when adding a category, and a Domain filter (category options grouped by domain). |

## Design

- **DB (0265):** `skill_categories.domain varchar(10) NOT NULL DEFAULT 'it'` + `ck_skill_categories_domain`; `job_skills.min_level
  varchar(16) NULL` + `ck_job_skills_min_level`; the T2 seed. Guarded steps (0001 builds fresh databases from the models). Downgrade drops
  both columns and deletes the seeded non-IT skills, aliases and categories that nothing references (a referenced row stays).
- **Service:** `candidate_search._has(ids, verified_only, levels=None)` gains the level set; `matching.plan` passes it. `skills.py` gains
  `domain_filter`. Level order constant `CANDIDATE_SKILL_LEVELS` is reused (`levels_from(min_level)`).
- **API:** `recruiter_skills.py` (domain in/out/filter), `recruiter_requirements.py` weights route, `recruiter_requirements.requirement_out`.
- **FE:** `lib/recruiterSkills.ts`, `RecruiterSkillCategories`, `RecruiterSkillsPanel`, `lib/recruiterMatching.ts`,
  `RecruiterRequirementMatches` (WeightsForm), `RecruiterRequirementDetail` (skill list).

## Acceptance criteria → tests

1. The Pharmacy category exists (domain `non_it`) with seed skills; the IT seed is unchanged → `test_hrc_017_migration.py`, rec-006 seed tests still pass.
2. A job can require "Python ≥ intermediate": PUT weights with `min_level` → detail shows it; a beginner Python candidate is no longer a match, an advanced one is → `test_hrc_017_taxonomy.py`.
3. Domain filter: `?domain=non_it` lists Pharmacy and not Programming; a skill tagged into a non-IT category is listed → API test.
4. `−`: a free-text skill with a level → 422; a recruiter (not a writer) cannot change a category's domain → 403; bad domain → 422.
5. `E`: editing the skill lists keeps a kept skill's level; reseeding is idempotent and keeps a manager's rename.
6. Web: vitest for the form select + payload, the category domain action, the detail label; Playwright `hrc-017-skills-taxonomy.spec.ts`.

## Regression risks

rec-006 seed/migration tests (`test_models_match_the_migration` lists the category columns — gains `domain`), rec-016 matching tests and
the weights form vitest, e2e specs that pick "Programming" from the first 100 categories (new categories sort last, so unaffected).

## Tasks

1. Migration 0265 + models + migration test (RED → GREEN).
2. Categories domain: schemas, API in/out/filter, skills `?domain=` + tests.
3. `min_level`: schemas, weights route, set_skills preservation, detail/criteria output, matching filter + tests.
4. Web: types/clients, categories admin, skills panel filter, weights form, detail label + vitest.
5. Docs: DEC-SCOPE-388, API §12KG, backlog status line; Playwright spec; browser QA.
