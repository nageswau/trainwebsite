# hrc-023 — Website registration → candidate create/match (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-023` (PDF §6.1 steps 1–5, §13 "Website registration", §17 QA; PDF
  classified `UNVERIFIED`). Dependencies hrc-022 (DEC-SCOPE-386), hrc-014 (DEC-SCOPE-377) and hrc-010 (DEC-SCOPE-383) are merged.
- **Decision:** `DEC-SCOPE-387`. The owner said to proceed with the recommended answers, so Q-23/Q-25 and W1–W10 below are **the
  builder's calls (`NEEDS_CONFIRMATION`)**.
- **Numbering:** migration `0264_website_intake`; API §12KF. No new permission (no RBAC section).

## Intent

Today `POST /public/jobs/{id}/apply` writes a `CareerApplication` that no staff screen reads, and no campaign (UTM) data is captured.
hrc-023 makes the website the front door of the recruiter pool: a job application or a candidate registration creates — or matches —
one candidate record with source **Website**, the UTM parameters of the visit and the consent shown, so recruiters see it in their
candidate list with no import.

## Goals / non-goals

- Goals (ACs): (1) a new registration creates a candidate with source Website and UTM; (2) a second registration with the same email
  matches, not duplicates; (3) consent is recorded; (4) the candidate is visible in the recruiter list without any import.
- Non-goals (later items): routing and the unassigned queue (hrc-024); converting a website application into a staff `JobApplication`
  (hrc-026); attaching the uploaded resume as a candidate resume version (hrc-026); CAPTCHA (no provider decided, Q-25).
- Anti-goals: an unverified form changing an existing candidate's data or consent; an answer that reveals whether an email is
  already known; a double click making two candidates.

## Builder's calls (`NEEDS_CONFIRMATION`)

- **W1 UTM.** The five standard keys `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content` (strings, trimmed, ≤100
  chars each; any other key is dropped, never an error). The browser keeps the first-touch values of the visit in `sessionStorage`
  (captured on any careers page), so a visitor who lands on `/it/careers?utm_source=x` and then registers keeps them.
- **W2 Registration (hrc-022's form).** `POST /candidate/register` accepts an optional `utm`; it is kept on the new user's profile. The
  candidate is still created only when the email is verified (hrc-022 C4 — the backlog's "exact **verified** email"): a new candidate
  now has source **Website** (`source_detail` "Website registration") and the UTM. A claimed recruiter record keeps its own source and
  UTM (it was not acquired by the website). Candidates created earlier with source "Candidate portal" are not changed.
- **W3 Job apply matching.** The application's email is not verified, so it matches by **exact email only** (lower-cased): an
  existing candidate with that email (a merged one is followed to its survivor) gets the application **linked** and nothing else —
  no field, consent or status of theirs changes. Never by phone. No match → a new candidate: name, email (`email_verified_at` empty),
  the mobile unless another candidate holds it (then left off — the unique index), source Website (`source_detail` "Job application"),
  the UTM, no creator (`created_by_user_id` becomes nullable: "added by the website"), and hrc-014 duplicate detection runs as for any
  new candidate (probable matches go to the queue).
- **W4 Consent.** The apply form shows the candidate-pool consent wording (`candidate-v1`, hrc-022's text) as a required checkbox; the
  API takes an optional `consent_version` (a wrong one is `422`, missing is accepted for backward compatibility). The application
  row records the version and time. A **new** candidate with consent is `opted_in` with a `candidate_consents` `opt_in` row
  (`user_id` becomes nullable: a public form has no user). A matched candidate's consent is not touched (anti-goal).
- **W5 Concurrency.** The intake takes a transaction advisory lock on the email key before matching (the tel-005 R7 idiom), so two
  submissions in one second serialise and the second matches the first. A racing path that does not take the lock (a recruiter
  create, a portal verification) loses or wins at the unique index; the intake retries the match once after an `IntegrityError` in a
  savepoint.
- **W6 Bot protection.** A hidden honeypot field `website`: when filled the route answers the normal `201` shape and stores nothing
  (logged). Per-IP cap: 10 applications per rolling hour, counted from `career.apply` audit rows → `429` with `Retry-After`.
- **W7 Enumeration.** The apply answer is the same for a new and a matched person (`id`, `tracking_code`, `status`).
- **W8 Q-25 existing rows.** The migration **links** existing `career_applications` to an existing unmerged candidate with the same
  email; it creates no candidates from history (no consent was recorded). Unlinked history stays readable by tracking code.
- **W9 Recruiter view.** The candidate detail gains `utm` and `website_applications` (job title, tracking code, status, date — never
  the cover note in the list), shown as a small "Website" card. The list already shows the source "Website".
- **W10 Merge.** hrc-014 merge moves `career_applications` with the victim (a `MOVED` entry, "website applications").

## Data

- `candidates.utm` JSON nullable; `candidates.created_by_user_id` nullable.
- `candidate_consents.user_id` nullable.
- `career_applications`: `candidate_id` (FK candidates, nullable, indexed), `utm` JSON nullable, `consent_version` String(20)
  nullable, `consented_at` timestamptz nullable. Existing data is preserved; downgrade drops the new columns (nullable columns restored
  only when no NULL rows exist — the downgrade fills nothing and is guarded).

## Security review (Phase 3)

- Public route, no auth (correct for a website form); rate-limited per IP; honeypot. Upload validation is the existing
  `career_resume` policy. Inputs length-checked against the columns (`422` instead of a `500`).
- No candidate data is returned to the public; logs/audit carry ids and the IP only, never name/email/phone.
- An unverified submitter cannot modify an existing record (W3) nor claim it: claiming needs hrc-022's verified email.

## Plan (TDD, red → green)

1. Migration 0264 + models + migration test.
2. `services/website_intake.py` (UTM clean, match/create, consent) + the apply route (throttle, honeypot, consent, lengths); tests for
   AC1–AC3, W3, W5, W6, W7.
3. Registration UTM + source Website on verification (candidate_portal); tests.
4. Merge MOVED + detail_out website block; tests (AC4).
5. Web: `lib/utm.ts`, `CareerApply` (consent, honeypot, busy, a11y, account link), register form UTM, detail card, merge label; vitest;
   Playwright e2e.
6. Docs: DEC-SCOPE-387, API §12KF, RTM rows, backlog status.
