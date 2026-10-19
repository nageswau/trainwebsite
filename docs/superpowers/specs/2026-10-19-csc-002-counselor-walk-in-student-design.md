# csc-002 — Counselor creates a walk-in student account; the welcome email is sent (design)

`DEC-SCOPE-227`, API `12EM`, RBAC `2.149`, no migration (uses csc-001's `overseas_student_counselors`, `0165`).
Backlog: `docs/delivery/COUNSELOR_WALKIN_BACKLOG.md` §3 `csc-002`. Owner answers W1 (Overseas `counselor` only), W2 (walk-in;
existing functionality unchanged), W3 (the student belongs to the counselor who created it).

## Intent

A student walks into the office and talks to a counselor. The counselor creates the student's login on the spot; the student
receives the ENH-003 welcome email, sets a password and signs in at `/overseas/login`. The student is in the counselor's caseload at
once (csc-001), so the counselor can book an appointment before any application exists.

## API

### `POST /counselor/students` → 201

Body (`CounselorStudentCreate`, `extra="forbid"`): `full_name` (1–160, not blank), `email` (≤ 255, `name@domain.tld`), `phone`
(optional, ≤ 40). Any other field — `role`, `division`, `password`, `active`, `email_verified`, `profile` — is a 422.

One transaction, under a lock on the counselor's own `users` row (serialises that counselor's creates, so the throttle is race-free):

1. Throttle (C2): at most **20** creations per counselor per rolling 24 h, counting successful creates **and** duplicate-email
   rejections (AGN-002 QA-10 pattern, audit rows, no new table) → `429` + `Retry-After`.
2. Existing email (case-insensitive) → audit `counselor.student_create_rejected` (committed), `409 "Email already exists"`.
3. `User`: role `overseas_student`, division `overseas`, unusable password, `active=true`, `email_verified=false`, a `student_code`
   (like self-registration), `profile={"registration_source": "counselor_walk_in"}`. A concurrent duplicate is a 409 via
   `flush_unique_email`, audited like (2).
4. Role assignment (`_sync_role_assignment`, `assigned_by` = counselor); the csc-001 link (`assigned_by` = counselor).
5. Welcome token (`issue_welcome_token`); audit `counselor.student_create` (ids only).
6. Commit; then `deliver_welcome_link` (after commit; a failed or unconfigured send never rolls the account back).

Response: `{"student": {id, full_name, email, phone, student_code, setup}, "email_status", "expires_at"}`. **The raw token is
never returned, in any environment** (AGN-001/002 S3: only an admin may see the dev/test token; a counselor must never be able to set
the student's password). This corrects the backlog line that said dev/test returns it.

### `GET /counselor/students?limit=20&offset=0` → 200

The counselor's linked students, newest link first: `{"items": [{id, full_name, email, phone, student_code, setup}], "total", "limit",
"offset"}`. `setup` is ENH-003's `pending_setup` / `link_expired` / `null` (active). `limit` 1–50.

Both routes: `role == counselor` and `division == overseas`, else 403 (an IT counselor included).

## Frontend

The counselor's **Students** section (`/overseas/counselor/students`) gains one panel, *Walk-in students*, mounted by `WorkflowPanel`
next to the existing ones; the section's table is unchanged.

- Add form: Full name, Email, Phone (optional) → "Create account". Double-submit guard; the entry is kept on any failure.
  Success: "Account created for {name}. A set-password link was emailed to {email}." or, when `email_status != "sent"`, "Account
  created, but the email was not delivered." (csc-003 adds Resend).
- List: name, email, Student ID, set-up status ("Set-up pending" / "Link expired" / "Active"); loading, error-with-Retry, empty
  states; 20 per page with Previous/Next.
- Reuses `sendJson`, `isPage`, `Page`, and the AGN-002 failure wording (`staffFailure`) and markup.

## Builder's calls (owner said: proceed with recommended answers)

- C1 — **No lead matching.** Creating an account neither searches nor blocks on telecaller leads; tel-018's lead→student link already
  connects them. Backlog open question closed this way; revisit if duplicates appear.
- C2 — **Throttle 20 / counselor / 24 h** (AGN-002's staff budget), duplicate-email attempts counted.
- C3 — **Student ID assigned** at creation, as self-registration does.
- C4 — Documents, chat and application-level scopes stay as csc-001 left them (follow-up).

## Not changed

`POST /admin/users`, `services/provisioning.py`, `auth` set-password/forgot-password, the agent flows, the Students section's table.

## Security

Privilege: role, division and flags are server-set; extra fields are refused. IDOR: the list is the caller's links only. Mail
relay abuse: C2. Enumeration: 409 reveals an existing email (same as admin/agent creation) and is counted by C2. Logs and audit rows
carry ids only — never the email, phone or token. CSRF: same cookie/SameSite=Lax JSON API as every other route.

## Tests

`test_csc_002_walk_in_students.py`: create (201, user fields, link, role assignment, student_code, audit, no token in response even in
test env, welcome email sent via the mailer stub); the student sets a password with the issued link and signs in; duplicate email 409
(case-insensitive) audited; extra/forbidden fields 422; invalid email / blank name / long phone 422; non-counselor and IT counselor 403;
anonymous 401; throttle 429 + Retry-After counting rejections; list shows own links only with setup status and paging; mail
not configured still 201. Component test for the panel; e2e: counselor creates a student, student activates and signs in, then the
counselor books them (csc-001 picker).
