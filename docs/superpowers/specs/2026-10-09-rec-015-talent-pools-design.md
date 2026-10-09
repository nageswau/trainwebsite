# rec-015 — Talent pools (rule-based automatic membership) — design

- **Feature ID:** `rec-015` (`RECRUITER_CRM_BACKLOG.md` §rec-015). **Dependencies:** rec-011 (PR #180) and rec-013 (PR #199), both merged.
- **Decision:** `DEC-SCOPE-159` (P1–P8, the recommended answers to Q-16 and the item's open points; **UNVERIFIED**, applied under the
  owner's standing instruction "proceed with the recommended answers; ask only if genuinely blocking").
- **Numbers:** migration `0141_talent_pools`, API §12CA, RBAC §2.85.
- **Evidence:** `EVID-018` S2-§8 (lines 1351–1379: "Recruiter can create pools such as …", ten examples, "Whenever a candidate is added,
  they are automatically placed into the relevant pools based on their skills"), S2-§20 (1736–1790: the Java talent pool, "gets the
  entire relevant candidate pool immediately"); `DEC-SCOPE-116` R7 (rule-based), R11 (the whole opted-in pool).

## 1. Answers (P1–P8, UNVERIFIED)

| # | Question | Answer |
|---|---|---|
| P1 | Q-16: rule pools only, or manual pools too? | **Rule pools only.** Membership is computed on read from the pool's rule, so it is always current and nothing is copied (backlog "expected behavior"). No manual add/remove |
| P2 | Q-16: the Fresher / Experienced thresholds | **Freshers = 0 years** of experience (0–11 months, AC2). **Experienced Professionals = 1 year or more** (12+ months). A candidate with no recorded experience is in neither |
| P3 | Q-16: seed the ten examples? | Seed the **six** examples the seeded Skills Master can express: Java Developers (Java), Python Developers (Python), Full Stack Developers (a frontend skill AND a backend language), Cloud Engineers (AWS OR Azure OR GCP), Freshers, Experienced Professionals. The other four (Cyber Security, SAP, Digital Marketing, Data Analysts) have no skills in the Skills Master yet; the manager creates them after adding the skills. The seed is idempotent (skipped by name) and is never re-applied over an edit |
| P4 | The rule | The rec-013 expression: `all` (every one of these skills, AND) and up to 5 `any` groups (at least one of, OR), with rec-013's caps (20 terms, 10 per group), plus an experience band (`experience_min_months`, `experience_max_months`). At least one skill or one experience bound. Each term must be an active Skills-Master skill or alias when saved (rec-013 FS3: `422 unknown_skill` with suggestions); the **skill's name** is stored, so an alias is saved as its skill. Aliases and related skills count when members are computed (rec-013 FS2). Claimed skills count |
| P5 | Edge: a pool whose skill was deactivated (or renamed or deleted) | The term is **unavailable**: it matches nobody. An unavailable `all` term empties the pool; in an `any` group it drops out (a group with nothing left empties the pool). The pool lists its unavailable terms, the list marks it "Needs attention" and the page tells the manager to edit the rule. A merged skill keeps working (its name became an alias of the target) |
| P6 | Roles | **Read:** candidate readers (rec-009: `placement_team`, `placement_manager`, `super_admin`, `hr_team`), active pools only. **Write:** `placement_manager` and `super_admin`, any pool (division-global, like the pool itself, R11); they also see inactive pools. Everyone else `403`. An inactive or unknown pool is `404` for a reader |
| P7 | Pool fields and lifecycle | Name (1–80, unique ignoring case → `409`), rule, active. No delete: a pool is deactivated (`active: false`) and can be reactivated. `created_by` is the manager (null for the seed). Each create / change writes one audit row with field names only |
| P8 | Members | The whole pool (`pool_filter`, R11), not archived, matching the rule; newest first, 50 per page, as rec-013 cards (no phone or email, R8). The list shows each pool's member count (one query for all pools). A pool with skills links to Find Candidates with its skills filled in, to refine and shortlist |

## 2. Data

`talent_pools` (migration `0141_talent_pools`, guarded create like 0140; downgrade refuses while a non-seed pool exists):

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `name` | varchar(80) | unique on `lower(name)` (`uq_talent_pools_name`) |
| `all_terms` | JSON | skill names |
| `any_terms` | JSON | list of lists of skill names |
| `experience_min_months` / `experience_max_months` | int null | `ck_talent_pools_experience`: min ≤ max, both 0–600 |
| `active` | bool, default true | |
| `created_by_user_id` / `updated_by_user_id` | uuid FK users null | null = seed |
| `created_at` / `updated_at` | timestamptz | |

## 3. API (§12CA)

| Method/Path | Behaviour |
|---|---|
| `GET /recruiter/pools?include_inactive=false` | Readers. `{items: [pool], can_manage}`; `include_inactive` is honoured for writers only. A pool is `{id, name, all, any, experience_min_months, experience_max_months, active, members, unavailable: [term], created_by: {id, name} \| null, updated_at}`. Sorted by name |
| `POST /recruiter/pools` | Writers. Body `{name, all?, any?, experience_min_months?, experience_max_months?, active?}` (`extra="forbid"`). `201` pool. `422` validation / `unknown_skill`; `409` name taken |
| `PATCH /recruiter/pools/{id}` | Writers. Partial; the merged rule is re-validated. `200` pool. `404`, `409`, `422` as above |
| `GET /recruiter/pools/{id}/candidates?limit=50&offset=0` | Readers (`404` for an inactive pool unless writer). `{pool, items, total, limit, offset, terms}`: `items` are rec-013 cards with `matched` skills, `terms` the resolved terms (rec-013 shape) |

## 4. Implementation

- `services/candidate_search.resolve_terms(db, body, strict=True)`: with `strict=False` an unknown term resolves to
  `{skill: None, ids: set(), also: []}` instead of raising, so `filters()` turns it into "matches nobody" with no other change.
- `services/talent_pools.py`: role checks, `rule_body(pool)` (a `CandidateSearch.model_construct` of the rule — the rule was validated on
  save), `counts(db, pools)` (one `count(*) FILTER (WHERE …)` per pool in a single query), `members(…)` (reuses `filters` and `page`),
  `out(pool, …)`.
- `api/recruiter_pools.py`: the four routes, one transaction per write (lock, validate, flush under the unique index, audit, commit, log).
- Web: `/recruiter/pools` (list; managers get "+ New pool") and `/recruiter/pools/[id]` (rule summary, warning, member cards, paging;
  managers get Edit). Shared shell of `RecruiterCandidatePages`; `SkillChips` and `Card` are exported from `RecruiterFindCandidates` and
  reused. Nav: "Talent Pools" after Find Candidates for recruiters and managers.

## 5. Tests

- API (`tests/test_rec_015_talent_pools.py`): AC1 (adding a Java skill makes a candidate a member, no other action), AC2 (Freshers rule
  = max 11 months; a 0-month candidate is in, a 12-month one is out), Cloud Engineers OR pool, unknown term → 422, empty rule → 422,
  duplicate name → 409, deactivated skill → unavailable + no members, roles (recruiter cannot write, BDM 403, inactive pool hidden),
  counts in the list, archived / not-opted-in candidates excluded, the seed.
- Migration (`tests/test_rec_015_migration.py`): the seed rows and their idempotency.
- Web unit (`RecruiterTalentPools.test.tsx`) and e2e (`rec-015-talent-pools.spec.ts`): create a pool, see members, deactivated warning.
