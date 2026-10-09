# rec-010 — IT-student opt-in to the candidate pool + EMP-003 re-pointed (design)

- **Backlog:** `docs/delivery/RECRUITER_CRM_BACKLOG.md` § rec-010. Scope: R4, R6, R12 (`EXPLICIT_APPROVAL`, 2026-10-07).
- **Dependencies:** rec-009 (`candidates`, with the unused `user_id` and `opted_in`) and rec-017 (`candidate_for_student`, which backfills
  students not opted in). Both are merged.
- **Decision:** `DEC-SCOPE-138`. Migration `0123_candidate_consents`, API §12BF, RBAC §2.64. Re-check `main` before merging.

## 1. Owner answers (Q-10, 2026-10-09, user in session)

| ID | Question | Answer |
|---|---|---|
| OI1 | Which students may opt in | Any **active `it_student`** (IT division). Other roles get 403. |
| OI2 | Consent wording | Version **`v1`**: "I agree that EduSphere may add my name, email, phone, course and skills to its placement candidate pool. EduSphere recruiters may contact me about jobs, and registered employers may see my name, course, skills and availability, never my email or phone. I can leave the pool at any time; my existing job applications continue." |
| OI3 | Seed data | The student's candidate comes from rec-017's `candidate_for_student`: the linked one, else an unlinked one with their email or mobile (linked), else a new one with the source "Edusphere students". **Fill empty fields only:** `source_detail` = the latest enrolment's course, and the email or mobile if blank and not used by another candidate (Q-07). Each profile skill that the Skills Master resolves (name or alias, active) and that the candidate lacks becomes a `candidate_skills` row: level `beginner`, source `resume`, status `claimed`, added by the student. Unresolved skills are skipped. Nothing a recruiter entered is overwritten. |
| OI4 | EMP-003 data | Rows = opted-in, non-archived candidates linked to an active IT student whose `PlacementProfile` is missing or not withdrawn (ADM-007). Fields stay the same: `student_id`, `name` (user), `course` (latest enrolment), `skills` (`User.profile.skills`), `availability` = **candidate `status == "available"`**. EMP-004 shortlisting uses the same visibility rule. |

## 2. Data

`candidate_consents` holds the opt-in/opt-out history, the `ConsentRecord` idiom. It is append-only and never updated or deleted:

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `candidate_id` | FK candidates, RESTRICT | |
| `user_id` | FK users, RESTRICT | the student who acted (always the candidate's user) |
| `action` | varchar(10) | CHECK `action IN ('opt_in', 'opt_out')` (`ck_candidate_consents_action`) |
| `consent_version` | varchar(20) | the version in force when they acted |
| `ip_address` | varchar(64) null | the request client host, as `ConsentRecord` does |
| `created_at` | timestamptz default now() | |

The index is `ix_candidate_consents_candidate (candidate_id, created_at)`. The migration only adds a table (guarded create, 0122's
idiom). Its downgrade refuses while rows exist, because consent evidence is never dropped silently.

`candidates.opted_in` stays the gate. The history records each change of it.

## 3. Behaviour (`services/placement_pool.py`)

Functions only; the route commits.

- `require_student(user)`: 403 "Only IT students can join the placement candidate pool" unless `role == "it_student"` and
  `division == "it"`. An inactive user never authenticates.
- `state(db, user)` → `{opted_in, consent: {version, text}, history: [{action, consent_version, created_at}]}`, history newest first
  (at most 20). With no candidate yet, `opted_in` is false and the history is empty. Reading creates nothing.
- `opt_in(db, user, version, ip)`:
  1. A version other than the current one gives **409** "The consent wording has changed. Review it and try again."
  2. The user row is locked FOR UPDATE, so two clicks or two tabs serialise and `candidate_for_student` never races itself.
  3. `candidate = candidate_for_student(db, user)` (OI3).
  4. Already opted in, with an `opt_in` as the latest history row → **no-op** (idempotent; no second row).
  5. Otherwise set `opted_in = true`, seed (OI3), add an `opt_in` history row and an `AuditLog` row
     (`placement_pool.opt_in`, entity `candidates`, metadata `{consent_version, skills_added}`).
- `opt_out(db, user, ip)`: lock the user. With no candidate, or one not opted in → no-op. Otherwise set `opted_in = false` and add an
  `opt_out` history row and an audit row. Applications, interviews and offers are untouched.
- `latest_courses(db, student_ids)`: `{student_id: program title}` from the newest enrolment. `employer.py` and the seed share it; it
  replaces EMP-003's inline query.
- `employer_visible()`: the OI4 conditions, shared by EMP-003 and the EMP-004 shortlist.

Logs carry ids only, never a name, email or phone.

**Effects across the app (no code change needed):**
- `services/candidates.pool_filter` already shows `user_id IS NULL OR opted_in`. After opting in, the student appears in the recruiter
  candidate list (AC2). After opting out, recruiter reads 404, as rec-009 and rec-017 already do.
- An archived candidate stays archived after the student opts in. The student's card still shows them as opted in, and EMP-003 hides
  them until a recruiter restores the candidate (rec-009 owns archive).

## 4. API (§12BF)

| Route | Body | Result |
|---|---|---|
| `GET /account/placement-pool` | | 200 state |
| `POST /account/placement-pool/opt-in` | `{consent_version: str ≤20}` | 200 state; 409 stale version; 422 missing version |
| `POST /account/placement-pool/opt-out` | | 200 state |

- All three require login (401) and `require_student` (403).
- There is no user id anywhere, so a student can only act for themselves. An unknown body key such as `user_id` is ignored and never
  changes who is opted in.
- Writes return the new state, so the card needs no second GET.

`GET /employer/candidates` (EMP-003) keeps its contract: the same fields and `q` filter, with new rows. `POST /employer/shortlist`
(EMP-004) gives 422 "Valid student candidate is required" for a student who is not employer-visible. It no longer creates a candidate.

## 5. UI

`PlacementPoolCard` appears on **Student → Placement Status** (`WorkflowPanel`, the `AgreementConsentPanel` idiom; it uses an
`action-card`):
- **Loading:** "Loading your placement pool status…".
- **Error:** an alert with the message and a Retry button.
- **Not in the pool:** the heading "Join the placement candidate pool", the consent text, "Version v1", and a required checkbox "I agree
  to the consent text above". The "Join the pool" button stays disabled until the box is ticked and while a request is in flight.
- **In the pool:** the badge "In the placement pool", one line on what employers see, and "Leave the pool". Leaving asks first: "Leave
  the pool? Employers will no longer find you; your applications continue.", with the buttons "Yes, leave" and "Cancel".
- A success message is announced through `aria-live="polite"`.
- The history list shows "Joined" or "Left", with the date and the consent version.
- The card collapses to one column on mobile, using the existing `action-card`.

The employer search panel does not change.

## 6. Acceptance → tests

| AC | Test |
|---|---|
| AC1 Before opt-in, a student with a `PlacementProfile` is not in EMP-003 | API `test_rec_010` + updated `test_emp_003` |
| AC2 After opt-in: in the recruiter list and EMP-003 (with "Python" search) | API, e2e `rec-010` |
| AC3 Opt-out hides them again (applications stay) | API, e2e |
| AC4 Consent history is kept | API (two cycles → four rows in order), migration test |
| Negative: another user's id cannot be used; a non-student gets 403; 401 | API |
| Edge: a backfilled student is linked, not duplicated; an external candidate with the same email is linked; a double opt-in adds one row; a stale version gives 409 | API |
| Seed OI3 | API: source detail = course, skills resolved/skipped, recruiter values kept |
| EMP-004 shortlist of a non-opted-in student → 422 | updated `test_emp_004` |
| UI states | vitest `PlacementPoolCard.test.tsx` |

## 7. Out of scope

- Including the consents in the GDPR export (`/account/data-requests` export): a follow-up.
- Retention (Q-09).
- Student self-apply (rec-018).
- Pool matching (rec-015).
- "Course completed" skills (rec-036).
