# rec-006 — Skills Master, categories, aliases (design)

Backlog: `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-006. Source: EVID-018 S2-§2 (lines 1126–1216) and S2-§16 (1607–1643).
Depends on rec-001 (merged PR #143). Numbering (rec-002 holds 0101 / 117 / 12AJ / 2.43 in a parallel branch): `DEC-SCOPE-118`,
migration `0102_skills_master`, API §12AK, RBAC §2.44. Re-check origin/main before the merge and re-chain if needed.

## 1. Owner answers (2026-10-08, `EXPLICIT_APPROVAL` in session)
- **S1 (merge):** no skill merge in rec-006. It moves to rec-011, where there are candidate skills to re-point. Until then a
  duplicate skill is deactivated and its names are re-added as aliases of the kept skill.
- **S2 (suggest):** recruiters are **read-only**: the API plus a read-only Skills page. There is no suggestion queue. A recruiter
  asks their manager to add a skill.

Defaults taken in session (the owner asked to proceed with the recommended answers; the rec-002 C3 precedent):
- **S3 (readers):** `placement_team`, `placement_manager` and `super_admin` read. `placement_manager` and `super_admin` write.
  `hr_team`, `it_admin` and every other role get 403 (Q-28 keeps `/recruiter/*` closed to `hr_team`).
- **S4 (related skills):** `skill_related` is built. The source lists "Core Java" both as a skill (§2) and as a Java synonym (§16).
  An alias may not equal a skill name (AC3), so Java ⇄ Core Java is seeded as a *related* pair, not an alias.
- **S5 (secondary category):** JavaScript has primary category Programming plus a secondary tag Frontend (`skill_category_tags`).
- **S6 (deletion):** skills and categories are deactivated, never deleted. Aliases, related links and tags are plain links with
  no dependants, so they are deleted (audited).

## 2. Data (migration `0102_skills_master`)
| Table | Columns | Constraints |
|---|---|---|
| `skill_categories` | id, name varchar(80), active, sort_order, timestamps | `uq_skill_categories_name` on `lower(name)` |
| `skills` | id, name varchar(80), category_id FK → skill_categories, active, timestamps | `uq_skills_name` on `lower(name)`; `ix_skills_category` |
| `skill_category_tags` | skill_id FK (cascade), category_id FK | PK (skill_id, category_id) |
| `skill_aliases` | id, skill_id FK (cascade), alias varchar(80), created_at | `uq_skill_aliases_alias` on `lower(alias)`; `ix_skill_aliases_skill` |
| `skill_related` | skill_a_id, skill_b_id (FK, cascade) | PK (a, b); `CHECK skill_a_id < skill_b_id` (one row per unordered pair) |

- **Names** are trimmed, with inner whitespace collapsed to one space. They must have no control characters and are capped at 80.
  - This matches `resolve()`'s normalisation, so the `lower(...)` indexes decide case-insensitive duplicates.
- **One term space.** A skill name and an alias may never be equal, ignoring case.
  - Every write that sets a skill name or an alias first takes `pg_advisory_xact_lock(290_118)`, then checks the other table.
  - Within a table, the unique index decides (409, even under a race).
- **Seed:** always runs and inserts only what is missing (by lowercase name), so it never overwrites a manager's rename.
  - 5 categories in source order.
  - 37 skills, each in its source category in source order. JavaScript appears in both Programming and Frontend, so it is one
    skill (primary category Programming) with a Frontend tag.
  - 9 aliases: Java 8, Java 11, Java 17, Java 21, J2EE, J2SE → Java; React.js, ReactJS, React JS → React.
  - 1 related pair: Java ⇄ Core Java.
- **Table creation** is guarded, because 0001 builds the schema from the models (the 0076/0100 idiom).
- **`downgrade()`:**
  - It refuses while manager data exists, meaning any category, skill or alias that is not in the seed.
  - Otherwise it drops the tables.

## 3. Service `app/services/skills.py`
- `normalise(text) -> str`: trims and collapses whitespace.
- `resolve(db, text) -> Skill | None`:
  - Returns the **active** skill whose name, or one of whose aliases, equals the text, ignoring case.
  - The name wins over an alias.
  - This is the single normaliser for rec-007, rec-011, rec-012 and rec-013.
- Role helpers: `require_reader`, `require_writer`, and `sees_inactive` (writers).
- Term-space guards: `lock_terms(db)`, `check_name_free(db, name, skill_id)` and `check_alias_free(db, alias, skill)`.
- Shapes: `skill_out` and `category_out`. The page's aliases, tags and related skills load in 3 batched queries (no N+1).

## 4. API (§12AK), prefix `/api/v1/recruiter`
| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/skill-categories` | readers | `active`, `q`, `limit`, `offset`; ordered `sort_order, lower(name), id` |
| POST | `/skill-categories` | writers | `{name}` → 201, appended at max+1 |
| PATCH | `/skill-categories/{id}` | writers | `{name?, active?}` |
| GET | `/skills` | readers | `q` (name **or alias**, substring), `category_id` (primary or tag), `active`, `limit`, `offset`; ordered `lower(name), id` |
| GET | `/skills/{id}` | readers | one skill (404 if unknown, or inactive for a reader) |
| POST | `/skills` | writers | `{name, category_id, tag_category_ids?: []}` → 201 |
| PATCH | `/skills/{id}` | writers | `{name?, category_id?, tag_category_ids?, active?}`; tags replace the set |
| POST | `/skills/{id}/aliases` | writers | `{alias}` → 201 (returns the skill) |
| DELETE | `/skills/{id}/aliases/{alias_id}` | writers | 204 |
| POST | `/skills/{id}/related` | writers | `{skill_id}` → 201 (returns the skill) |
| DELETE | `/skills/{id}/related/{other_id}` | writers | 204 |

Skill item: `{id, name, active, category:{id,name,active}, tags:[{id,name,active}], aliases:[{id,alias}], related:[{id,name,active}]}`.

**Rules**

Readers and writers:
- A reader who is not a writer only ever sees active rows, whatever `active` asks for. A reader's `related` list holds active
  skills only.

Request bodies:
- Bodies are untyped dicts parsed by `services/telecaller._parse` (`extra="forbid"`). A 422 is one sentence that names the field.
- `active` is a StrictBool.

Categories:
- Setting a category (primary or tag) needs an active category, locked `FOR SHARE`.
- Keeping a since-deactivated category is allowed.
- A primary category that is also listed as a tag is a 422.
- At most 10 tags.

Conflicts (409):
- A duplicate category name, skill name or alias, in any case.
- An alias equal to any skill's name, or a skill name equal to any alias.
- A related pair that already exists.

Other 422s and 404s:
- An alias equal to its own skill's name → 422 "An alias cannot repeat the skill's name".
- Relating a skill to itself → 422.
- The related skill must exist and be active → 422.
- An unknown skill, category, alias or related link → 404.

Writes and audit:
- Each write has one commit and one `AuditLog` row in the same transaction. The actions are:
  - `recruiter.skill_category_create` / `recruiter.skill_category_update`
  - `recruiter.skill_create` / `recruiter.skill_update`
  - `recruiter.skill_alias_add` / `recruiter.skill_alias_remove`
  - `recruiter.skill_related_add` / `recruiter.skill_related_remove`
- The metadata holds field names, ids and the alias text. Skill data is not personal data.
- A PATCH that changes nothing writes no audit row.
- There is no DELETE for skills or categories (405).

## 5. Web
- **`/recruiter/manager/skills`** (manager, `super_admin`):
  - The server shell reads `auth/me`. Any other role gets the access-denied view; signed-out users go to `/admin/login`.
  - `RECRUITER_MANAGER_NAV` gains **Skills Master**.
- **`/recruiter/skills`** (`placement_team`): the same panel in read-only mode, under `RECRUITER_NAV` (**Skills Master**).
  - A manager or `super_admin` who opens it is redirected to the editable page.
- `RecruiterSkillsPanel` (one client component, `canEdit` prop):
  - **Categories card** (edit mode only): a create form, then a list with inline rename (Esc cancels), Deactivate/Reactivate,
    and loading, error-with-Retry and empty states.
  - **Skills card:**
    - Search (name or alias) and a category filter, both kept in the URL (`?q=&category=&offset=`), plus a pager and
      loading, error-with-Retry and empty states.
    - The table shows Name, Category (+ tags), Aliases, Related and Status.
    - Edit mode adds a create form (name, category, tags) and a **Manage** button on each row.
      - Manage opens a detail card for that skill.
      - The detail card has: rename / category / tags; alias chips with Remove plus an Add alias form; related chips with
        Remove plus an Add related skill picker (SearchableSelect, server mode); and Deactivate/Reactivate.
- After a write, focus moves to the feedback line. A ref guards against a double submit. The `.telecaller-list` card layout is
  reused on mobile, and no new CSS is added.

## 6. Acceptance criteria
1. The seed contains every S2-§2 skill under its category: 37 skills in 5 categories. JavaScript is one skill, Programming plus
   a Frontend tag. The S2-§16 aliases and the Java ⇄ Core Java pair are seeded.
2. An alias resolves to its skill: `resolve("j2ee")` → Java, and `GET /skills?q=reactjs` finds React.
3. A duplicate alias → 409. An alias equal to another skill's name → 409 (e.g. "Core Java" on Java). A skill named like an
   existing alias → 409.
4. A manager adds the alias "Java 23" → Java, and it then resolves.
5. Recruiters read (active only); they cannot write (403). `hr_team` and `it_admin` cannot read or write (403).
6. A rename keeps the id. Deactivating hides a skill from recruiters and from `resolve()`, but managers still see it.
7. The manager page and the read-only page work on desktop, tablet and mobile. They have loading, empty and error states and
   are keyboard operable.

## 7. Risks
- New tables only. Shared hot spots: `models.py`, `schemas.py`, the `main.py` router tuple, `navigation.ts` (and
  `navigation.recruiter.test.ts`). All edits are append-only; rec-002 touches the same lines, so expect textual merge conflicts.
- `lib/skills.ts` belongs to School skills, so the new client module is `lib/recruiterSkills.ts`.
