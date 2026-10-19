# Counselor Walk-in Students — Enhancement Backlog (`csc-001` … `csc-005`)

NO-ASSUMPTION MODE. Prepared 2026-10-19 at the owner's request. **No code was written or changed.**

**Owner statement (2026-10-19).** "Counseller can add a student and email will trigger to him for login." Clarified in the same
session: "do not change existing functionality. this scenario is that student may reach the office directly and start discussion
with counseller directly. For this type of student, counsellor can create student or lead directly."

**Evidence class.** `MEETING_TRANSCRIPT_REQUEST`-equivalent owner request made in a working session. No `docs/sources/` file. The owner
answers W1–W6 below were given through the clarifying-question prompt. Each is recorded here, and becomes a decision only when the
item that uses it is built and its `DEC-SCOPE` entry is written.

**Baseline.** Every "existing behaviour" statement was checked against code on `origin/main` @ `383c4e85`. The graphify CLI could not
run in that session, so the graph report was used for orientation only, and the code was the authority. No duplicate feature was
found on main (`git grep` over `docs/` and the `nehn-` backlog).

**Numbering.** `csc-0NN` is this backlog's item number, not a Feature ID. The next free numbers on main today are migration `0165`,
`DEC-SCOPE-226`, API `12EM` and RBAC `2.148`. Recheck `origin/main` when each item is picked up; parallel branches take numbers.

## 1. Owner answers

| ID | Question | Answer |
| --- | --- | --- |
| W1 | Which "counselor"? | The **Overseas `counselor`** only. Not the IT `counselor` (tel-017) and not the school `career_counselor` (school students never log in, `DEC-ROLE-004`). |
| W2 | Entry point | A **walk-in**: the student comes to the office and talks to the counselor. The counselor can create **either a student account or a lead**. **Existing functionality does not change.** |
| W3 | Ownership of a directly created student | A **new student→counselor link**. The counselor sees linked students before any application exists. Application-based scoping is unchanged. Overseas Admin can reassign. |
| W4 | Who works a counselor-created walk-in lead | **The counselor owns it (`owner_id`) and a telecaller is distributed too** (tel-007). |
| W5 | The telecaller's rights on that lead | **Read-only — keep D1/T19 unchanged** (`services/telecaller_leads.py:28`). Only the counselor acts; the telecaller manager still acts. |
| W6 | Account actions for the counselor | **Resend the welcome link and fix name/phone/email while the account is pending** (never activated). Deactivation and reassignment stay with Overseas Admin. |

## 2. Existing behaviour (verified)

- **Account creation is admin-only.** `POST /admin/users` (`api/admin.py:523`, `ensure_admin`). The account gets an unusable password
  hash and an ENH-003 welcome link (`PasswordResetToken`, `purpose="welcome"`, 72 h, single use, hashed at rest):
  `services/provisioning.py` `issue_welcome_token` → commit → `deliver_welcome_link`. Delivery runs after commit and never raises.
  The link is `/{overseas|it}/reset-password?token=…`. Using it sets `email_verified` (`api/auth.py` `reset_password`).
- **Mail transport.** ENH-032 / `DEC-SCOPE-225`: `services/mailer.py` sends through the Zoho Mail API when `email_transport == "zoho_api"`.
- **A counselor's students** come from applications only: `api/lookups.py:139`
  (`OverseasApplication.counselor_id == user.id`). A newly created student with no application is invisible to the counselor, and so
  cannot be picked for the first application.
- **Applications.** A counselor may create an overseas application, and becomes its `counselor_id` (`api/workflows.py:1799,1832`).
  Only Overseas Admin reassigns `counselor_id` (AGN-023, `DEC-SCOPE-090`).
- **A counselor's leads** are those with `Enquiry.owner_id == counselor`, in the counselor's own division
  (`services/lead_handover.py:59`). A counselor can link a handed-over lead to an **existing** student (tel-018), but cannot create one.
- **Lead creation** is `services/lead_intake.create_lead`: a telecaller's own lead is `assigned` to them; a manager's lead goes through
  tel-007 distribution (`lead_distribution.on_intake`). `walk_in` is already one of the 13 sources (`tel_sources.py`).
- **Once a lead has a counselor**, the telecaller keeps read access only (D1/T19, `services/telecaller_leads.py:28`), and the
  "not contacted" alerts skip it (`services/telecaller_alerts.py:209`).
- **The telecaller manager's queue** includes every lead with no telecaller in their teams (`services/lead_pipeline.py:51`).

## 3. Items

### `csc-001` — Link a student to their counselor

**Status (2026-10-19): built on `feature/csc-001`** — `DEC-SCOPE-226`, migration `0165`, RBAC §2.148. Builder's call: the picker this
widens is the counselor's *Schedule appointment* Student reference (no counselor create-application UI exists), and the appointment write
widens with it (ENH-031 §5). Spec `docs/superpowers/specs/2026-10-19-csc-001-student-counselor-link-design.md`.

- **Business requirement:** a student the counselor creates stays in that counselor's caseload before any application exists (W3).
- **Existing behaviour:** a counselor sees a student only through `OverseasApplication.counselor_id`.
- **Expected behaviour:** a new link records one active counselor per student. The counselor's visible students become the
  application-based set **plus** the linked set. Application-based visibility is unchanged.
- **User roles affected:** `counselor`, `overseas_admin`.
- **Frontend impact:** none in this item.
- **Backend impact:** a shared scope helper for the union. The counselor branch of `GET /lookups/overseas-students` switches to it.
- **Database impact:** **new table** (recommended over a `users` column), e.g. `overseas_student_counselors`: `student_user_id`
  (unique), `counselor_user_id`, `assigned_by_user_id`, timestamps. Index on `counselor_user_id`. Migration `0165` (tentative).
- **API impact:** no new route. The lookup's response shape is unchanged.
- **Integration impact:** none.
- **Authentication impact:** none.
- **Authorization impact:** the union stays limited to the counselor's own students and own division.
- **Security impact:** the union must never leak another counselor's students.
- **Performance impact:** one extra indexed subquery in the lookup.
- **Reusable modules:** `lookups._page`, the `AuditLog` pattern.
- **Dependencies:** none.
- **Acceptance criteria:**
  - A linked student with no application appears in the counselor's lookup and the create-application picker.
  - A student linked to counselor B never appears for counselor A.
  - Existing application-based results are identical before and after.
- **Positive scenarios:** a linked student is visible; an application-only student is still visible.
- **Negative scenarios:** another counselor's linked student is not visible; an IT-division counselor gets 403.
- **Edge cases:** a student who is both linked and has an application is listed once; the linked counselor is deactivated (tel-025).
- **Regression risks:** the counselor student lookup and the create-application picker.
- **Complexity:** small. **Risk:** medium.

### `csc-002` — Counselor creates a walk-in student account; the welcome email is sent

- **Business requirement:** the counselor creates the login for a walk-in student, and the student gets an email to set a password
  and log in (W1, W2).
- **Existing behaviour:** only an admin can create an `overseas_student` account.
- **Expected behaviour:** a counselor form takes full name, email and phone. In one transaction it creates an `overseas_student` in
  the `overseas` division with an unusable password, writes the `csc-001` link and an audit row, and issues the welcome token. After
  commit it sends the welcome link, which opens `/overseas/reset-password`.
- **User roles affected:** `counselor` (creator), `overseas_student` (recipient).
- **Frontend impact:** an "Add student" form and a "My students" list with provisioning status in `/overseas/counselor`. The status
  badge reuses ENH-003's.
- **Backend impact:** a **new dedicated route and service**. `POST /admin/users` is not widened or refactored (W2). The server forces
  role, division, `active = true` and `email_verified = false`, and rejects any `password`, `role`, `division`, `active`,
  `email_verified` or `profile` in the body.
- **Database impact:** writes `csc-001`'s table; no schema change.
- **API impact:** e.g. `POST /counselor/students`: 201; 409 if the email exists; 422 on invalid input. The delivery status is returned
  in the same shape as admin creation.
- **Integration impact:** the ENH-032 Zoho send. A `not_configured` or failed send never rolls back the account.
- **Authentication impact:** reuses the ENH-003 welcome token. Setting the password marks the email verified.
- **Authorization impact:** `role == counselor` and `division == overseas`; every other role gets 403.
- **Security impact:**
  - **Privilege escalation is the main risk:** the counselor can create only `overseas_student`.
  - Abuse: unsolicited welcome emails to arbitrary addresses. A per-counselor creation throttle is `NEEDS_CONFIRMATION`.
  - The 409 reveals that an email exists. Admin creation does the same; acceptable for staff.
  - Logs carry ids only, never the email (`provisioning._redact` already covers delivery errors).
- **Performance impact:** the send runs after commit and can take up to about 10 s, the same as admin creation.
- **Reusable modules:** `unusable_password_hash`, `flush_unique_email`, `issue_welcome_token`, `deliver_welcome_link`,
  `admin._valid_email`, `admin._fit`.
- **Dependencies:** `csc-001`.
- **Acceptance criteria:**
  - The account is created, the welcome email is recorded as sent, the link sets a password, and the student logs in at
    `/overseas/login`.
  - The student appears in the counselor's list as pending, then active.
- **Positive scenarios:** create → email → set password → log in. In dev/test the response carries the development token.
- **Negative scenarios:** duplicate email → 409; invalid email or over-long name → 422; a smuggled `role: overseas_admin` → rejected;
  any non-counselor → 403.
- **Edge cases:**
  - Two concurrent creates with the same email → one 409, never a 500.
  - Mail not configured → the account exists and the status says so.
  - **The person already exists as a telecaller lead:** warn, block or link is `NEEDS_CONFIRMATION`.
- **Regression risks:** none to admin creation while the route stays separate.
- **Complexity:** medium. **Risk:** high (account creation by a non-admin).

### `csc-003` — Counselor resends the link and fixes details on a pending account

- **Business requirement:** the counselor can recover from a mistyped address or a lost email without an admin (W6).
- **Existing behaviour:** resend is admin-only (`api/admin.py:757`); a counselor has no edit rights on a student account.
- **Expected behaviour:**
  - On the counselor's **own linked** students, and only while the account has never been activated, the counselor can resend the
    link (existing 60 s cooldown) and edit name, phone and email.
  - **Changing the email revokes every outstanding welcome token** and issues a new one to the new address.
  - Once the account is active, the counselor has no edit rights.
- **User roles affected:** `counselor`.
- **Frontend impact:** row actions in "My students".
- **Backend impact:** two routes; the checks run under the user row lock.
- **Database impact:** none.
- **API impact:** e.g. `POST /counselor/students/{id}/welcome-links`, `PATCH /counselor/students/{id}`.
- **Integration impact:** mail.
- **Authentication impact:** token revoke and reissue.
- **Authorization impact:** own linked students only. A student visible only through an application is not editable.
- **Security impact:** a missed revocation would leave a link sent to a mistyped address valid. That is the key acceptance criterion.
- **Performance impact:** negligible.
- **Reusable modules:** `revoke_welcome_tokens`, `resend_wait_seconds`, `provisioning_statuses`.
- **Dependencies:** `csc-002`.
- **Acceptance criteria:** the old link fails after an email change; a resend within 60 s → 429; editing an active account → 409.
- **Positive scenarios:** resend after the cooldown; correct a mistyped email and the new address receives a working link.
- **Negative scenarios:** another counselor's student → 404; an inactive account → 409; a duplicate email on edit → 409.
- **Edge cases:** a resend racing a password set keeps ENH-003's lock order (user row, then token).
- **Regression risks:** low.
- **Complexity:** small. **Risk:** medium.

### `csc-004` — Counselor creates a walk-in lead

- **Business requirement:** a walk-in who is not ready for an account is captured as a lead by the counselor (W2, W4, W5).
- **Existing behaviour:** leads are created by telecallers and managers (`lead_intake.create_lead`), or arrive from the website, BDM
  or import. A counselor cannot create one.
- **Expected behaviour:**
  - The counselor creates a lead in their own division: source `walk_in` by default, an active product of that team.
  - `owner_id` is the counselor, and tel-007 distribution assigns a telecaller.
  - **D1/T19 is unchanged:** the telecaller is read-only; the telecaller manager still acts.
  - The existing duplicate block applies: 409 with the match panel.
- **User roles affected:** `counselor`, `telecaller` (read-only), `telecaller_manager`.
- **Frontend impact:** a "New walk-in lead" button on the counselor leads list, reusing `NewLeadForm.tsx` and the duplicate panel.
- **Backend impact:** a counselor branch that reuses `create_lead`, sets `owner_id` and runs `on_intake`.
- **Database impact:** none (`walk_in` is already in `TEL_SOURCES`).
- **API impact:** e.g. `POST /counselor/leads`.
- **Integration impact:** none.
- **Authentication impact:** none.
- **Authorization impact:** counselor only, own division. The counselor needs read access to the product list.
- **Security impact:** the lead's contact details stay out of logs and audit metadata (the existing convention).
- **Performance impact:** the same as manual intake.
- **Reusable modules:** `lead_intake` (identity, duplicate lock, panel), `lead_distribution.on_intake`, `lead_pipeline.apply_event`.
- **Dependencies:** none.
- **Acceptance criteria:**
  - The lead is in the counselor's list; the distributed telecaller sees it read-only; the manager can reassign the telecaller.
  - It is excluded from the "not contacted" alerts.
- **Positive scenarios:** create → distributed → the counselor works it, books counselling and links a student (tel-016/tel-018).
- **Negative scenarios:** a duplicate phone or email → 409; another team's product → 422; an inactive product → 422.
- **Edge cases:**
  - No active telecaller → the lead waits in the manager's unassigned queue.
  - The person is already another telecaller's lead → 409; the counselor asks for a handover.
- **Regression risks (all `NEEDS_CONFIRMATION`):**
  - **Telecaller conversion credit** (tel-021 DB2): the distributed telecaller would be credited with a conversion the counselor did.
  - **Counselor handover metrics** (`services/management_counseling.py:48`) count handed-over leads only, so walk-ins would be missing.
  - Telecaller targets and dashboard counts would rise.
- **Complexity:** medium. **Risk:** high (touches the pipeline and metrics).

### `csc-005` — Overseas Admin views and reassigns a student's counselor link

- **Business requirement:** a linked student is never stranded, for example when their counselor is deactivated (W3).
- **Existing behaviour:** there is no student-level counselor link to view or change.
- **Expected behaviour:** the admin user view shows the linked counselor, and Overseas Admin can reassign it to an active overseas
  counselor.
- **User roles affected:** `overseas_admin`. Whether `super_admin` may also reassign is `NEEDS_CONFIRMATION` (AGN-023 excluded
  `super_admin` from application reassignment).
- **Frontend impact:** the admin user detail, using the existing counselor picker (`/lookups/overseas-counselors`).
- **Backend impact:** one route.
- **Database impact:** none (updates `csc-001`'s table).
- **API impact:** e.g. `PUT /admin/users/{id}/counselor`.
- **Integration impact:** none.
- **Authentication impact:** none.
- **Authorization impact:** Overseas Admin, own division.
- **Security impact:** audit every reassignment (from, to, actor).
- **Performance impact:** negligible.
- **Reusable modules:** `workflows._require_overseas_counselor`, the AGN-023 reassignment pattern.
- **Dependencies:** `csc-001`.
- **Acceptance criteria:** after reassignment the student appears for the new counselor and not the old one.
- **Positive scenarios:** reassign to an active overseas counselor.
- **Negative scenarios:** an inactive or IT counselor → 422; the same counselor → 409; a non-admin → 403.
- **Edge cases:** the student also has applications with the old counselor (those stay as they are; AGN-023 governs them).
- **Regression risks:** low.
- **Complexity:** small. **Risk:** low.

## 4. Dependency graph

```
csc-001 (link, migration) ──► csc-002 (create + email) ──► csc-003 (resend / edit)
        └──────────────────► csc-005 (admin reassign)
csc-004 (walk-in lead) ── independent
```

1. **Must be sequential:** `csc-001` → `csc-002` → `csc-003`. `csc-005` comes after `csc-001`.
2. **Can run independently:** `csc-004` (its own worktree), and `csc-005` alongside `csc-002` once `csc-001` has merged.
3. **Common files and modules:**
   - `models.py` (`csc-001`)
   - `schemas.py` (`csc-002`, `csc-003`, `csc-004`)
   - `api/lookups.py` (`csc-001`, `csc-005`)
   - the `/overseas/counselor` portal pages (`csc-002`, `csc-003`, `csc-004`)
   - every item: the decision register, `API_CONTRACT.md`, `RBAC_MATRIX.md`, `RTM.md`, the master feature catalog, and the
     route-inventory test (one row per new route)
4. **Migrations:** `csc-001` only (tentatively `0165`). The others need none.
5. **Implement first:** `csc-001`, then `csc-002`, which delivers the owner statement as given. `csc-004` can start in parallel once
   its metrics questions are answered.

## 5. Open questions (`NEEDS_CONFIRMATION`)

Ask one at a time when the item is picked up.

| Item | Question |
| --- | --- |
| `csc-002` | A per-counselor creation throttle — yes, and what limit? |
| `csc-002` | The walk-in already exists as a lead (matched by phone or email): warn, block, or link that lead? |
| `csc-004` | Who gets conversion credit for a walk-in lead — the counselor, or the distributed telecaller (tel-021 DB2)? |
| `csc-004` | Do walk-in leads count in the counselor-handover metrics (`management_counseling.py`)? |
| `csc-004` | Do walk-in leads count towards telecaller targets and dashboards? |
| `csc-005` | May `super_admin` reassign the link too? |
