# hrc-022 — External candidate portal identity and self-service (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-022` (PDF §5.1, §6.1 step 2, §11; PDF classified `UNVERIFIED`).
  Dependencies hrc-002 (DEC-SCOPE-374) and hrc-010 (DEC-SCOPE-383) are merged.
- **Decision:** `DEC-SCOPE-386`. The owner said to proceed with the recommended answers, so Q-23, Q-24 and C1–C12 below are **the
  builder's calls (`NEEDS_CONFIRMATION`)**.
- **Numbering:** migration `0263_candidate_portal`; API §12KE; RBAC §2.282.

## Intent

External job seekers have no login today: recruiters create their candidate records and nobody else can keep them current. hrc-022
gives them a verified identity linked to their candidate record (`Candidate.user_id`, as IT students have since rec-010), a small
portal where they can see their own profile, edit only the fields the recruitment team allows, change their email only after
verifying the new address, and manage their pool consent.

## Goals / non-goals

- Goals: the five ACs. (1) Register, verify, log in. (2) See only their own profile. (3) Edit only allow-listed fields. (4) A changed
  email is verified before it replaces the old one. (5) Throttles return 429.
- Non-goals (later items): the public website registration form with UTM/source capture and job apply (hrc-023); routing (hrc-024);
  applications from the portal (hrc-026); a recruiter "invite to portal" email (follow-up: self-registration with a verified email
  already claims a recruiter-created record, C4); phone OTP (C8).
- Anti-goals: account enumeration through registration, resend or email change; a candidate reading or changing anyone else's record;
  claiming someone's recruiter-created record by typing their phone number.

## Builder's calls (`NEEDS_CONFIRMATION`)

- **C1 (Q-23).** A new `candidate` role, division `it` (a separate role, as recommended). One email is one account: an email already
  held by any user (an IT student included) gets the same answer as a new one and nothing is created; a student keeps using the
  student portal and its rec-010 opt-in.
- **C2 Registration.** `POST /api/v1/candidate/register` (public, JSON): name, email, optional phone, password (10–128), the consent
  version shown. Always `202 {"accepted": true}` (development adds `development_verification_token`). A new email creates a `User`
  (`role=candidate`, `email_verified=false`) and a 24-hour verification link. An email that belongs to an **unverified candidate**
  re-sends that account's link (C5 cap applies, silently); any other existing email does nothing. Per-IP cap: 5 registrations per
  rolling hour, counted from the `candidate.register` audit rows (the agn-024 pattern) → `429` with `Retry-After`.
- **C3 Verification tokens.** A new `user_verification_tokens` table (purpose `verify_email` | `email_change`, sha256 hash, the new
  email for a change, expiry, used/superseded). Single use, consumed atomically (the reset-password idiom); every failure is the same
  `400`. Issuing a new token supersedes the user's open ones of the same purpose.
- **C4 Linking (on verification).** `POST /api/v1/candidate/verify-email` (public, `{token}`). For `verify_email`: the user becomes
  verified and is linked to a candidate — their existing linked one, else an **unlinked** candidate with the same email
  (case-insensitive; a recruiter-created record is claimed this way, the email being verified), else a new candidate (source
  "Candidate portal", created and opted in by the user). Matching is **never by phone** (unverified). The candidate joins the pool:
  `opted_in=true` with a `candidate_consents` `opt_in` row carrying the version accepted at registration. A claimed candidate's
  `email_verified_at` is set.
- **C5 Resend.** `POST /api/v1/candidate/resend-verification` (public, `{email}`): always `202`. At most 3 verification emails per user
  per 15 minutes; over the cap nothing is sent and the answer is unchanged (the ENH-032 forgot-password idiom — no enumeration signal).
- **C6 Login.** `/it/login` as today (division `it`). A candidate whose email is unverified gets `403 "Verify your email address
  first -- use the link we emailed you."`, only after the password matched (as the wrong-portal message). Cookies, session version and
  password reset are unchanged.
- **C7 Self-service fields.** The universe a candidate could ever edit: name, city, state, country, LinkedIn, current company, notice
  period, preferred roles, tools, languages, available from, willing to relocate, preferred contact. Never: email (C9), mobile (C8),
  status, source, salary, skills, rows, ownership. The allow-list lives in a singleton `candidate_self_service_settings` row (default:
  all of the universe except name). `GET/PUT /api/v1/recruiter/candidate-self-service-settings`: candidate readers read it; placement
  managers and super_admin change it (the hrc-012 setting editors), audited.
- **C8 (Q-24) Phone.** No SMS provider is decided, so the mobile is not self-service; the portal shows it read-only with "ask your
  recruiter to change it".
- **C9 Email change.** `POST /api/v1/candidate/me/email` `{new_email, current_password}`. Wrong password → `400` (counted by the
  change-password audit throttle: 5 per 15 minutes → `429`). Same as current → `422`. 3 change requests per 15 minutes per user →
  `429`. An address already used by a user or another candidate → `202` with nothing sent (enumeration-safe); otherwise a link to the
  **new** address, `202`. Confirming re-checks the address (a race → `409`), then sets `users.email`, `candidates.email` and
  `email_verified_at`, audited with old/new. Until then the old email stays in force and the portal shows "pending".
- **C10 Own records.** Every `/candidate/me*` route requires the `candidate` role and reads `Candidate.user_id == user.id` — there is
  no id in any portal URL, so there is nothing to tamper with. A candidate without a linked record (archived or merged) gets `404`.
- **C11 Profile edit.** `PATCH /api/v1/candidate/me` validates through the recruiter `CandidateUpdate` schema (same rules and messages),
  then refuses any key outside the universe (`422`) or outside the allow-list (`403` naming the field). The change is audited as
  `candidate.update` with `self_service: true` and old/new values (hrc-004 history), mirrors follow (hrc-010 P5), and hrc-014
  duplicate detection runs as for a recruiter edit.
- **C12 Privacy.** `GET/PUT /api/v1/candidate/me/privacy`: the consent text and version, whether they are in the pool, and the consent
  history; leaving or re-joining the pool adds a `candidate_consents` row (the rec-010 idiom).

## Frontend

- `/it/careers/register` (form: name, email, phone, password, consent box), `/it/careers/verify-email?token=` (verifies on click,
  never on page load, so mail scanners cannot burn the link), and a "Resend link" form on the register success state.
- Portal `/it/careers/portal/profile` and `/it/careers/portal/privacy` in `PortalShell` with a two-item nav. `middleware.ts` protects
  `/it/careers/portal`; `ROLE_DASHBOARD_PATH.candidate` lands there. `/it/careers` and `/it/login` link to registration.
- The recruiter candidate list shows the allow-list card (checkboxes) to whoever may change it (the hrc-012 setting card idiom).
- Loading / empty / error states: forms disable while sending, `form-error role=alert` for failures, `form-message role=status` for
  success; 5xx shows a generic retry message.

## Security review (Phase 3)

- AuthN: reuses cookies/JWT/`session_version`; no new session mechanism. Unverified candidates cannot sign in.
- Enumeration: register, resend and email change answer identically for known/unknown emails; the 429 on registration is per IP.
- Tokens: 32-byte urlsafe, stored as sha256, single-use under `UPDATE ... RETURNING`, 24 h; never logged or audited.
- CSRF: JSON bodies only (FastAPI refuses other content types for body models); SameSite=Lax cookies unchanged.
- IDOR: no candidate id is accepted from a candidate. Role escalation: register always sets `candidate`; no profile key authorizes.
- Logs/audit carry ids, never the email, phone or token. Email delivery runs after commit as a background task (ENH-032).

## Plan (TDD, each step red → green)

1. Migration 0263 + models (`UserVerificationToken`, `CandidateSelfServiceSetting`) + RBAC role; migration test.
2. Service `services/candidate_portal.py` + router `api/candidate_portal.py`: register, verify, resend, login gate (auth.py).
3. Profile read/patch with the allow-list; settings routes.
4. Email change; privacy.
5. Web: lib + pages + middleware + nav + settings card; vitest for the lib/forms; Playwright e2e.
6. Docs: DEC-SCOPE-386, API §12KE, RBAC §2.282, RTM row, backlog status.
