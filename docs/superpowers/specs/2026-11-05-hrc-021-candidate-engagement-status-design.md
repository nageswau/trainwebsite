# hrc-021 — Candidate engagement status (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` hrc-021 and Appendix B ("Candidate engagement status", proposed definition, to
  confirm at build time); PDF §8 statuses and §6.2 filters (PDF classified `UNVERIFIED`). Scope approved by the owner 2026-11-01 (backlog
  Q-00). Dependencies hrc-016 (`DEC-SCOPE-387`) and hrc-026 (`DEC-SCOPE-394`) are merged. Decision `DEC-SCOPE-397`.
- **Open question Q-22** (derived or stored): the owner said to proceed with the recommended answers, so E1–E10 below are **the builder's
  calls (`NEEDS_CONFIRMATION`)**.

## Intent
Recruiters cannot tell at a glance where a candidate is in the relationship -- never touched, called, screened, in play, gone quiet,
placed -- and cannot filter the pool by it. The stored `status` (rec-009 Q-08: available / interviewing / placed / not looking / do not
contact) is set by hand and drifts from the real pipeline. hrc-021 adds a **derived engagement status**, computed from the records that
already exist, shown as a chip and usable as a filter.

**Non-goals:** changing the stored `status` values, its CHECK, or any reader of it (employer search availability, placement reports,
matching); a stored engagement column or history; the hrc-019 search-panel redesign; dashboards.
**Anti-goal:** a status that can disagree with the activity it summarises (why derived, not stored).

## Rules

**E1 — Q-22: derived (option a).** No new column and no migration: one SQL `CASE` expression (`services/candidate_engagement.py`)
evaluated in the same query as the rows (payload) and in `WHERE` (filter), so it cannot drift and the query count is unchanged.

**E2 — Values, first match wins:**

| # | Key | Label | Rule |
|---|---|---|---|
| 1 | `do_not_contact` | Do not contact | manual: stored `status = do_not_contact` |
| 2 | `not_interested` | Not interested | manual: stored `status = not_looking` |
| 3 | `placed` | Placed | (an application is `joined` OR stored `status = placed`) AND no open application |
| 4 | `active` | Active | an open application (`sourced`…`interview`), OR an application change or website application in the last 30 days |
| 5 | `inactive` | Inactive | nothing at all (registration, call, message, application change, website application) in the last 90 days |
| 6 | `shortlisted` | Shortlisted | any application now or ever (status history) in `shortlisted`, `profile_shared`, `interview`, `selected`, `joined` |
| 7 | `screened` | Screened | a screening record (rec-018 `application_screenings`), or an application now or ever `screened` |
| 8 | `contacted` | Contacted | ≥ 1 logged call or message (rec-025 / rec-026) |
| 9 | `uncontacted` | Uncontacted | a primary recruiter is set (hrc-012 `owner_user_id`) |
| 10 | `new` | New | otherwise -- registered, no owner, never contacted |

**E3 — Manual flags override (AC2).** `do_not_contact` and `not_interested` come from the existing stored `status` so recruiters keep using
the field they know; they beat every derived value. Appendix B's manual `inactive` flag is **not** added: inactive is derived (90 days),
and a recruiter who wants a person out of play sets "Not looking". This avoids changing a CHECK pinned by rec-009's migration test.

**E4 — "Activity" for Active is pipeline activity.** Appendix B says "an open application or activity in the last 30 days". Counting
recruiter calls there would make every recently called candidate Active and "Contacted" would almost never show; so a call or message makes
a candidate Contacted, and only application changes (`job_applications.updated_at`) and website applications make them Active. All kinds,
plus registration, count for Inactive.

**E5 — Placed is sticky until a new open application (the "+/−/E" re-registration case).** Re-registration finds the same candidate
(Q-07 unique mobile/email); once they have an open application again they are Active. A legacy hand-set `placed` counts as placed.

**E6 — Precedence of Inactive.** Placed beats Inactive (an outcome, not a lapse); Inactive beats the ladder steps 6–10 (a shortlisted
candidate untouched for 90 days is Inactive).

**E7 — Where it shows.** `engagement` `{key, label}` is added (additive) to every `CandidateItem` (the list), the candidate detail, the Find
Candidates cards (`candidate_search.page`, so talent-pool members too). The list (`GET /recruiter/candidates?engagement=`) and the search
(`CandidateSearch.engagement`; talent-pool rules are stored columns and do not gain it) filter by one key; an unknown key is 422. The stored
`status` and its filter stay exactly as they are.

**E8 — Time.** The 30 / 90-day windows are measured from the database `now()` at query time (`interval '30 days'`), not the app clock.

**E9 — AuthZ unchanged.** Same readers as the candidate list (`require_reader`). The status reveals nothing a reader cannot already see
(timeline, applications). No compensation involved.

**E10 — Numbering.** `DEC-SCOPE-397`; API §12KP; no migration; no RBAC change. (395/12KN/0272 are left for an in-flight sibling.)

## Performance
Correlated `EXISTS` / `max()` sub-queries on indexed columns (`ix_recruiter_calls_candidate_occurred`, `ix_recruiter_messages_candidate_sent`,
`ix_job_applications_candidate`, `ix_job_application_status_history_application`, `career_applications.candidate_id`,
`application_screenings` PK). For the page it runs only for the page's rows. As a filter it is evaluated per pool row; acceptable for the
current pool (≈10k); if it grows, a stored/maintained column is the follow-up (Q-22 option b).

## Frontend
- `lib/recruiterCandidates.ts`: `ENGAGEMENTS` (key/label, in E2's order) and a small `EngagementChip` style (`badge`).
- Candidate list: an **Engagement** column chip and an **Engagement** filter select (URL `engagement=`, cleared individually like the others).
- Candidate detail: the chip beside the stored status badge, labelled "Engagement: …" for screen readers.
- Find Candidates: an "Engagement" row in each card's facts (beside Status, the card's existing idiom) and an Engagement filter beside Status.
- The stored-status filter is relabelled nowhere; it keeps "Status".

## Tests (fixtures, AC1/AC2)
One backend test per row of E2 (a fixture candidate for each definition), each manual flag overriding an otherwise Active/Placed
candidate, the 30/90-day boundaries, the re-registration case, the list and search filters (and 422 on an unknown key), and a query-count
check that the list did not gain a query. Vitest for the list chip/filter and the detail chip; an e2e spec on the list filter.

## Regression risks
rec-009 list/status tests (additive field), rec-013 search query counts (expression joins the same query), rec-015 talent pools (rule schema
gains an optional key), the candidate list/detail/find vitest fixtures (missing `engagement` must render nothing, not crash).
