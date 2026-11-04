# hrc-018 — Configurable matching engine with explanations (design + plan)

- **Feature:** `hrc-018` (`docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md`), PDF §7.2 / §13 (PDF classified `UNVERIFIED`).
- **Decision:** `DEC-SCOPE-390` (builder's calls E1–E12 below, all `NEEDS_CONFIRMATION`; the owner said to proceed with the recommended
  answers). Dependencies hrc-010 (`DEC-SCOPE-383`), hrc-011 (`DEC-SCOPE-375`) and hrc-017 (`DEC-SCOPE-388`) are merged.
- **Numbering:** migration `0267_match_engine`, API §12KI, RBAC §2.284.

## Intent

rec-016 scores a requirement's candidates with skills (per-job weights) plus fixed 10-point experience and location constants. The
source asks for six admin-weighted factors (default 40/20/15/10/10/5), optional per-job hard filters, a plain-language explanation and a
"not a guarantee" disclaimer, with one engine usable job→candidates and candidate→jobs (hrc-027).

Non-goals: candidate-facing recommendation pages (hrc-027), advanced search (hrc-019), caching scores.
Anti-goals: leaking salary to anyone who cannot see compensation; a score that does not add up to its breakdown.

## Builder's calls (`NEEDS_CONFIRMATION`)

| # | Question | Call |
|---|---|---|
| E1 | The six factors | The PDF names the weights, not the factors in this repo; read from the backlog's gap list: **Skills 40, Experience 20, Qualification 15, Location 10, Role 10, Salary & availability 5** |
| E2 | Storage | One row `match_settings` (`id = 1`), six SMALLINT columns, a CHECK on each (0–100) and on their sum (= 100), so the database enforces AC1. No row = the defaults |
| E3 | Who sets weights | `super_admin` only (the "admin"; same as the hrc-007 approval settings). Every candidate reader may read them (`can_edit` says who may change) |
| E4 | Applicability and points | A factor applies only when the job has the data: skills (a Skills-Master skill), experience (a bound), qualification (non-blank text), location (rec-016 M6), role (always: the title), salary & availability (a maximum salary with a known rate, or an expected joining date). The 100 points are split among the applicable factors by weight (largest remainder, ties to the earlier factor), then the skills points among the skills by `job_skills.weight` (rec-016 M2). A full match is exactly 100 and the breakdown always sums to the score |
| E5 | What each factor matches | Skills: rec-016 M3 + hrc-017 levels. Experience: relevant months if recorded, else total, within the bounds. Qualification: one of the candidate's degrees (headline `qualification` or an education row), trimmed and non-empty, appears case-insensitively in the job's qualification text. Location: rec-016 M6. Role: the candidate's preferred role(s) and the job title contain one another, case-insensitively. Salary & availability: every sub-check that applies passes — expected annual INR ≤ the job's maximum in annual INR; available by the expected joining date (`available_from`, else today + notice days). Unknown = not matched |
| E6 | Hard filters | Required skills (unchanged), plus four per-job switches (`jobs.match_hard_experience/qualification/location/salary`, default off): experience ≥ the minimum, the qualification rule, the location rule, expected ≤ maximum salary. Unknown fails a hard filter. Turning on a filter the job has no value for is a 422. Set with the rec-016 weights form (`PUT …/skill-weights` gains optional `hard_filters`), audited in the same row |
| E7 | Explanation | Each match row gains `explanation[]` (one per applicable factor: key, label, text, points, max, matched) and `skills` (required/preferred matched/missing names). The page also shows `disclaimer` |
| E8 | Salary visibility (staff) | A caller without `candidates.compensation.view` gets the salary text without amounts ("Salary details are restricted") |
| E9 | Salary visibility (candidate, hrc-027) | No job salary is published anywhere today (public listings omit it), so the candidate audience never gets the salary explanation |
| E10 | Engine shape | `matching.evaluate(...)` is a pure function over a job spec, a candidate's facts and the weights. SQL prefilters only the pool, not archived, required skills (else ≥ 1 preferred); Python applies every hard filter, scores, sorts (score, newest, id) and pages. Measured cost is logged (count scored) |
| E11 | Q-18 | Replace the rec-016 constants (no preset): an admin can set weights to taste. rec-016 tests move to the new numbers |
| E12 | Candidate → jobs | `matching.jobs_for_candidate(db, candidate, jobs, audience)` evaluates given jobs with the same function; hrc-027 chooses which jobs and builds the page |

## API (additive)

- `GET /api/v1/recruiter/match-settings` → `{weights:{skills,…}, defaults, can_edit}` (candidate readers; else 403).
- `PUT /api/v1/recruiter/match-settings` `{weights:{…six ints 0–100}}` → same; super_admin only (403); sum ≠ 100 → 422; audited.
- `GET …/requirements/{id}/matches`: `criteria` gains `factors[]` and `hard_filters`; each item gains `explanation[]`, `skills`; the
  body gains `disclaimer`. `breakdown[]` keeps its shape (new kinds: qualification, role, salary).
- `PUT …/requirements/{id}/skill-weights`: optional `hard_filters: {experience?, qualification?, location?, salary?}`.

## Frontend

- `RecruiterMatchSettings` card (hrc-012/022 setting idiom) on the requirements page for whoever may edit: six number inputs, a live
  total, Save disabled until it is 100.
- Matches: explanation lines per row, the disclaimer under the heading, the factor criteria text, and hard-filter checkboxes in
  "Adjust weights" (disabled with a hint when the job has no value).

## Plan (TDD, one slice at a time)

1. Pure `allocate_factors` / `evaluate` unit tests → implement.
2. Model + migration 0267 (table + four columns, guarded add/drop) + migration test.
3. Settings GET/PUT tests (roles, sum, audit) → routes.
4. Matches: hard filters, new factors, explanation, disclaimer, compensation redaction tests → rewrite `matches`.
5. `PUT skill-weights` hard_filters tests → implement.
6. `jobs_for_candidate` test (same score both ways; candidate audience has no salary text).
7. Update rec-016 tests to the new numbers.
8. Web lib types + vitest for the settings card and explanation → components.
9. Playwright e2e `hrc-018-matching-engine.spec.ts`; docs (DEC, API, RBAC, backlog status, RTM).

## Risks

rec-016 tests/e2e assert scores (updated deliberately); hrc-017 vitest fixtures render the matches component (new keys optional);
Python scoring cost grows with the prefiltered set (logged; rec-016 already paged at 50).
