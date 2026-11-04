# hrc-010 — Candidate profile completion (design)

**Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-010` (PDF §5 field table, §8.3 C, Appendix B; PDF classified `UNVERIFIED`).
Scope approved by the owner 2026-11-01 (backlog Q-00: all phases). Dependency `hrc-004` (DEC-SCOPE-376) is merged on `main`. The owner
said to proceed with the recommended answers, so P1–P12 below are **the builder's calls (`NEEDS_CONFIRMATION`)**. Decision record:
DEC-SCOPE-382.

## Intent
A recruiter can record the whole §5 profile — every degree, every job, certifications, the skills that matter most, structured location,
richer preferences and how the person likes to be contacted — and sees at a glance how complete a profile is. Everything that already
reads the single legacy fields (search, matching, profile sharing, merge, the list) keeps working, because those fields become summaries
of the new rows.

## Acceptance criteria (backlog AC, + / − / E)
1. Every §5 field can be saved (create and PATCH) and is returned by the detail.
2. Total experience = the sum of the **non-overlapping** employment periods (an overlap counts once; a current job runs to today).
3. Completeness follows Appendix B (weights 10/15/15/15/15/20/10).
4. **+** two jobs and one degree save and show; experience is derived.
5. **−** an employment end date before its start date → 422 naming the row.
6. **E** overlapping jobs count the overlap once; a current job (no end date) counts to today.

## Builder's calls
- **P1 (rows, replace-set):** `education`, `employment` and `certifications` are lists in the candidate create/PATCH body. Sending a list
  replaces that whole set (omitted = unchanged, `[]` = clear). One save, one transaction, one audit row, one hrc-003 stale check. No new
  routes, so RBAC is unchanged (readers read, writers write — rec-009 R11). Caps: 10 education, 20 employment, 20 certifications.
- **P2 (education row):** degree (required, ≤120), specialisation (≤120), institution (≤200), year (1950–2100), grade (≤20 free text, e.g.
  "8.2 CGPA" or "78%"; optional per the backlog's PII note).
- **P3 (employment row):** employer (required, ≤200), designation (≤120), industry (≤120), employment type (the job enum: full_time,
  part_time, contract, internship, temporary), start date (required), end date (null = current). End before start → 422; a start or end in
  the future → 422.
- **P4 (Q-09 — derived experience):** while the candidate has employment rows, `experience_months` is **derived** and a sent value is
  ignored; with no rows it stays the manual figure (so a fresher can be 0 and old clients keep working). Months = round-half-up(union days ×
  12 / 365.25), union days inclusive after merging overlapping or touching periods. The stored figure is refreshed on every profile save,
  so a current job's figure is as of the last save (a scheduled refresh is a follow-up). `current_company` is the employer of the first
  current row (none → null) while rows exist.
- **P5 (mirrors):** the first education row sets `qualification`, `college` and `passing_year`; `city/state/country` (any set) set
  `location` ("City, State, Country"); `preferred_roles[0]` sets `preferred_role`. A legacy key sent by an old client still writes when
  its source is empty; `preferred_role` sent alone becomes the first of `preferred_roles`. Search, matching, sharing and the list are
  untouched.
- **P6 (fresher):** `is_fresher` is output only: `experience_months == 0` (null when unknown).
- **P7 (skills):** `candidate_skills.is_primary` (default false) on the existing skill add/PATCH; relevant experience per skill is
  rec-011's existing per-skill `experience_months`. `relevant_experience_months` on the candidate is the manual figure for the target role
  (0–600). `tools` and `languages` are lists of up to 20 texts (≤60 each). Certifications rows: name (required, ≤200), issuer (≤200),
  issued on, expires on (≥ issued on), credential id (≤100).
- **P8 (preferences):** `preferred_roles` (≤5), `work_modes`, `employment_types`, `shifts` (subsets of the job enums), `available_from`
  (date), `willing_to_relocate` (true / false / null).
- **P9 (contact):** `preferred_contact` ∈ phone, whatsapp, email (null = not stated). `email_verified_at` is read-only here (set by
  hrc-022's verification) and is cleared whenever the email changes.
- **P10 (completeness, Appendix B):** contact verified (email_verified_at) 10; ≥1 education row 15; ≥3 skills 15; experience known
  (incl. fresher 0) 15; preferences = ≥1 preferred role **and** ≥1 preferred location 15; a resume 20; expected salary provided 10.
  Computed on read in the detail (fixed query count), returned as `{percent, items:[{key,label,weight,met}]}`. Whether salary is provided
  is shown to every reader (not the amount — hrc-001's grant still hides every compensation value).
- **P11 (backfill):** each candidate with a qualification, college or passing year gets education row 1 from them; a non-null
  `preferred_role` becomes `preferred_roles`. `current_company` is **not** backfilled into employment, because its start date is unknown
  and a dateless row would falsify total experience (`NEEDS_CONFIRMATION`).
- **P12 (merge, resume apply):** hrc-014's merge moves the victim's education / employment / certification rows only when the survivor has
  none of that kind, then re-derives. rec-012's resume apply re-derives after it sets fields (rows win).

## Data (migration `0259_candidate_profile`)
Candidate columns: `country`, `state`, `city` (≤80), `preferred_contact` (check), `email_verified_at`, `relevant_experience_months`,
`tools`, `languages`, `preferred_roles`, `work_modes`, `employment_types`, `shifts` (JSON lists, default `[]`), `available_from`,
`willing_to_relocate`. `candidate_skills.is_primary` (default false). Tables `candidate_education`, `candidate_employment`,
`candidate_certifications` (id, candidate_id FK RESTRICT + index, position, the P2/P3/P7 fields, checks for dates and enums). Guarded
"create if missing" steps (0251's idiom); the downgrade drops them; legacy columns are never touched except by the backfill's inserts.

## API
Candidate create/PATCH accept the fields above; detail returns them plus `education`, `employment`, `certifications`, `is_fresher`,
`completeness`, `email_verified_at`. Skill add/PATCH accept `is_primary`; skill items return it. The list and search shapes are unchanged.
Audit: the rows are diffed as one text line per row (hrc-004 before/after).

## UI
Form gains fieldsets — Location & contact, Education, Employment history, Certifications, Skills extras (tools, languages, relevant
experience) and Preferences — with one shared row editor (add / remove, labelled inputs, keyboard reachable). Total experience and current
company inputs show only while there are no employment rows (then "worked out from employment history"). Detail shows the rows, the
fresher badge and a completeness bar (`role="meter"`) listing what is missing. Skills card gains a Primary checkbox and badge.

## Regression risks
rec-009/013 tests and the candidate form tests (fields moved), hrc-003 stale guard (row-only saves must bump `updated_at`), hrc-014 merge,
rec-012 resume apply, hrc-004 history.

## Reviews (Phase 3)
- **API (`api-and-interface-design`):** additive only — no key removed or renamed, list/search shapes unchanged, legacy keys still accepted
  (P5). Replace-set lists carry no row ids, so a client can never address another candidate's row (no IDOR surface). Rows use
  `extra="forbid"`; a row's 422 names it ("Employment 2: …"). `email_verified_at` is not an input (sending it is a 422 unknown field).
  PATCH stays under the existing candidate row lock (`FOR UPDATE`), so concurrent saves serialise; one commit per request.
- **Security (`security-and-hardening`):** authZ unchanged (`require_writer`/`require_reader`); every text goes through
  `_candidate_text` (trim, cap, control characters refused); React escapes all output; logs and audit metadata carry field names, the
  hrc-004 history diff carries row text (degree, employer…) like the other profile fields — contact and compensation stay redacted, and
  completeness exposes only *whether* salary is provided. No new secrets, uploads or external calls; no rate-limit change needed (same
  authenticated write route).
- **Frontend (`frontend-ui-engineering`):** reuse `.field`, `.form-grid`, `fieldset` + `legend` (the hrc-011 compensation idiom), one row
  editor for the three lists; each Remove button is named ("Remove employment 2"); checkboxes in a `fieldset` per enum; the meter is
  `role="meter"` with `aria-valuenow` and a visible "%"; `auto-fit` grids collapse to one column on phones; Save keeps the existing
  busy/double-submit guard and error `role="alert"`.
