# rec-016 — Requirement → candidate matching + weighted match score (design)

- **Feature:** rec-016 (`docs/delivery/RECRUITER_CRM_BACKLOG.md`). Sources: EVID-018 §10 (lines 475–498), S2-§10 (1427–1473), S2-§11 (1475–1501).
- **Decision:** `DEC-SCOPE-157` (M1–M8 below are **recommended defaults, UNVERIFIED**; the owner had not answered Q-14). API §12BY, RBAC
  §2.83. **No migration** (the weights already live on `job_skills.weight`, rec-007).
- **Dependencies (all merged):** rec-007 (PR #166), rec-013 (PR #199), rec-017 (PR #178).

## 1. Decisions (Q-14 and item-level; UNVERIFIED)

| # | Decision |
|---|---|
| M1 | **Weights.** Each requirement skill keeps its `job_skills.weight` (1–10; rec-007 defaults: required 2, preferred 1). The requirement's writers (rec-007 `can_edit`) can edit them per requirement from the Matching section. **Experience fit is worth 10 points and location fit 10 points** when they apply. The skills share the rest of the 100 in proportion to their weights. |
| M2 | **Points are whole numbers**, split by the largest-remainder method. The breakdown therefore always adds up to the total, and a candidate who matches everything scores exactly 100 (AC1, AC2). |
| M3 | **Matching a skill.** A candidate matches a requirement skill when they hold that skill or a skill related to it in the Skills Master. Aliases resolve to the same skill (rec-013 FS2). Claimed skills count. A requirement skill that is not in the Skills Master (`skill_id` NULL) cannot be matched: it is listed as "not used for matching" and is worth 0 points. |
| M4 | **Which candidates appear.** Required skills are a filter: the candidate must hold every one of them (AND). Preferred skills, experience and location only add to the score. A requirement with no Skills-Master required skills needs at least one preferred skill to match. A requirement with no Skills-Master skills at all returns `reason: "no_skills"` and an explanatory empty state. |
| M5 | **Experience fit.** The candidate's `experience_months` lies within the requirement's min–max (a missing bound is open). It applies only when the requirement has a minimum or a maximum. An unknown experience earns 0 points. |
| M6 | **Location fit.** The requirement's location (trimmed, case-insensitive) equals the candidate's location or one of their preferred locations. It does not apply when the work mode is `remote` or the location is blank. |
| M7 | **Who can use it.** Candidate readers (rec-009) within the requirement's scope (rec-007): the recruiter, `placement_manager` (team) and `super_admin`. A `bdm` or `hr_team` user gets 403. A requirement outside the caller's scope is 404. Shortlist is rec-017's existing `POST /requirements/{id}/candidates` at `shortlisted`, so its rules apply: writers only, not on a closed or cancelled requirement, and one application per candidate (409, AC3). |
| M8 | **Rows and actions.** Rows cover the whole pool (R11, `pool_filter`), excluding archived candidates. They are ranked by score, then newest candidate first, 20 per page. Each row shows the per-item breakdown and the candidate's status on this requirement; a Rejected candidate is shown as Rejected. Actions are View, Contact (writers) and Shortlist. **Share** waits for rec-019, which is not built yet. Rows never include a phone number or email (R8). |

## 2. API

`GET /api/v1/recruiter/requirements/{id}/matches?limit=20&offset=0` (read only)

```json
{
  "criteria": {
    "skills": [{"id": "<job_skill id>", "name": "Java", "kind": "required", "weight": 3, "points": 30, "in_master": true}],
    "experience": {"min_months": 0, "max_months": 24, "points": 10} ,
    "location": {"value": "Hyderabad", "points": 10}
  },
  "reason": null,
  "items": [{
    "id": "…", "candidate_code": "…", "name": "…", "preferred_role": "…", "current_company": "…", "experience_months": 18,
    "location": "…", "notice_days": 30, "status": "available", "score": 90,
    "breakdown": [{"key": "skill:<job_skill id>", "label": "Java", "kind": "required", "points": 30, "max": 30, "matched": true}],
    "application": {"id": "…", "status": "rejected", "status_label": "Rejected"}
  }],
  "total": 1, "limit": 20, "offset": 0,
  "can_shortlist": true, "can_edit_weights": true
}
```

`experience` and `location` are `null` when they do not apply.

`PUT /api/v1/recruiter/requirements/{id}/skill-weights` with body `{"weights": [{"id": "<job_skill id>", "weight": 1..10}]}`
returns `{"requirement": …}` (rec-007's detail).
- Each id must be a skill of this requirement; a foreign id or a duplicate id is a 422.
- The route checks `can_edit` (wrong role 403, cancelled requirement 409).
- The requirement row is locked, then the changed weights are written with one audit row (`recruiter_requirement.weights`, ids only) and one commit.
- Unchanged weights write nothing.

## 3. Backend

- `services/matching.py`:
  - `allocate(weights, experience, location)` is the pure scoring function.
  - `plan(db, job)` builds the criteria: the requirement's skills, their related skill ids (one query), and the experience and location conditions.
  - `matches(db, job, limit, offset)` runs one count query, one page query and one applications query. The page query selects every item's matched flag as a boolean column and orders by `Σ CASE WHEN flag THEN points END` in SQL, so Python never re-decides a match.
- Routes live in `api/recruiter_requirements.py`. The flag for one skill reuses rec-013's `candidate_search._has(ids, verified_only=False)`.

## 4. Web

- `lib/recruiterMatching.ts` holds the types, the type guard and the URLs.
- `components/RecruiterRequirementMatches.tsx` is the "Matching candidates" section on the requirement page. It handles loading, error with Retry, the `no_skills` empty state, the "no candidates" empty state, paging, stacked rows that work at phone width, an "Adjust weights" form for writers, and Shortlist.
- Shortlisting tells the page to re-read the rec-017 Candidates section (a `refreshKey` prop).
- The section re-reads when the requirement's `updated_at` changes, for example after its skills are edited.

## 5. Tests

- **API (`test_rec_016_matching.py`):**
  - `allocate`: totals of 100, the breakdown sums, and the largest-remainder rule.
  - The source's Java example ranks Rahul first.
  - A full match scores 100.
  - Required AND and the preferred-only rule.
  - A related skill counts.
  - A skill not in the Skills Master is unused.
  - The no-skills reason.
  - Experience and location, including remote.
  - Rejected status is shown.
  - Pool and archived exclusions.
  - Roles: BDM and hr_team 403, out of scope 404, manager reads but cannot shortlist or edit weights.
  - The weights PUT: validation, 403/409, audit, and that matches use the new weights.
  - Shortlist once, then 409.
- **Web:** a vitest for the section's states and actions, and a Playwright e2e for the happy path, shortlist, weights, and a mobile viewport.
