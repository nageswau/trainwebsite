# ccrm-008 — Convert lead to student (one click, prefilled) — design

Date 2026-10-24. Backlog item `ccrm-008` (`docs/delivery/COUNSELOR_CRM_BACKLOG.md`), owner answer CC9. Decision `DEC-SCOPE-252`,
API §12FE, RBAC §2.167. No migration. Dependency ccrm-007 (structured profile) is merged (PR #311).

The owner said "proceed with recommended answers", so the open questions are settled as builder's calls K1–K6 below. They are
recorded as `NEEDS_CONFIRMATION` in the decision.

## Intent

Today a counselor turns a lead into a student in two steps. First they create a walk-in account (csc-002), re-typing the name, email
and phone. Then they link that account to the lead (tel-018). Nothing the telecaller qualified reaches the student profile.
**Convert to student** does it all in one step, with nothing re-typed.

## Behaviour

`POST /api/v1/counselor/leads/{id}/convert`, with body `{full_name, email, phone}` (the csc-002 `CounselorStudentCreate`, prefilled by
the UI from the lead). It runs as one transaction on the locked lead (lock order lead → counselor → new user):

1. Scope check: the lead must be handed to this counselor (owner and division, `counselor_scope`). Otherwise 404; a non-counselor
   gets 403.
2. The lead must be overseas: an overseas counselor only, using csc-002's `require_overseas_counselor`. An IT counselor gets 403
   (W1: IT counselors work leads only).
3. Already linked → 409. Closed → 409 (the link rule).
4. **K1 stage.** The lead must be at Qualified or later in the open order (`qualified` … `counselling_completed`). An earlier stage
   is 422: "Move the lead to Qualified before converting it".
5. **K4 duplicate.** If an active overseas student of the division has the submitted email (case-insensitive) or the same last ten
   mobile digits, the answer is 409: "A student account already has this email or mobile. Link the existing student instead." No
   account is created. (This is the tel-018 suggestion rule, shared through one helper.) The UI then shows the link panel's
   suggestions.
6. `counselor_students.create_student(..., registration_source="lead_conversion")`. This brings csc-002's mail budget (20 per 24 h),
   the audited "Email already exists" 409 for any other user's address, the csc-001 link and the ENH-003 welcome token.
7. **K3 profile copy.** The lead's data is copied into `overseas_student_profiles`, built as a `StudentProfileSave` and written with
   ccrm-007's writer (no commit):
   - `city`, `state` ← `enquiries`
   - one qualification (level `other`, name ← `qualification`, `institution`, `year_completed` ← `passing_year`, score ←
     `academic_percentage` as `percentage`), when any of those is set
   - `preferred_course`, `preferred_intake` ← `intake`, and `preferred_level` (`ug`→`UG`, `masters`→`PG`) from `lead_qualifications`
   - `work_experience_months` ← years × 12, and `work_experience_details` ← `current_org`

   Free-text values with no structured slot are left on the lead, which stays linked and readable: `budget_range`,
   `english_test_status` and `passport_status`. A value that fails the profile validators (a future year, a value too long) is dropped
   field by field, so a copy never blocks a conversion. Nothing is copied when nothing is set.
8. tel-018 `link_student` + `commit_link`. Stage → Application/Enrollment, plus the `lead.convert` audit. The unique-student index
   race → 409.
9. After the commit, the welcome mail is sent (csc-002 `_deliver`; the token is never returned).

The response is `{student, lead (the counselor lead detail), email_status, expires_at}`, with status 201. Source, owner, telecaller,
notes and timeline are untouched, so they are preserved.

**K2 phone-only lead.** This is allowed. The dialog's email field starts empty and is required, so the counselor types the address.
The lead's own email is not changed.

**K5 concurrency.** Two converts of the same lead: the second waits on the lead lock, then sees it linked → 409.

**K6 "Create first application"** (§4 step 5, optional): deferred. There is no counselor application-create screen yet. After
conversion the UI links to the student's profile page (`/overseas/counselor/students/{id}/profile`) instead.

`permissions.convert` is added to the counselor lead detail: not linked, not closed, the division is overseas, and the stage is
Qualified or later.

## UI (CounselorLeadDetail, "Student account" section)

- When `permissions.convert` is true, a **Convert to student** button opens an inline form. The form has Full name, Email and Phone,
  prefilled from the lead, and a note: "Creates the student's account, emails a set-password link and moves the lead to
  Application/Enrollment."
- A submit guard stops double submission. The entry is kept on failure; a 409 duplicate tells the counselor to use the link list
  below.
- On success the lead state is replaced, and a status message shows the mail outcome with a link to the student's profile.
- When `link` is true and `convert` is false (an overseas lead before Qualified), a hint reads "Move the lead to Qualified to convert
  it to a student". Link stays available as today.

## Not in scope

- Bulk conversion.
- Converting by intake (ccrm-034).
- Copying English test or budget free text.
- Writing back to the lead.
- tel-021 conversion credit (unchanged: the lead still converts on enrolment).

## Tests

- **Backend** (`tests/test_ccrm_008_convert.py`): happy path (student, link, stage, profile copied, audit, mail after commit,
  no token); phone-only; early stage 422; closed 409; linked 409; duplicate email or phone 409 with nothing created; another
  counselor 404; IT counselor 403; telecaller 403; an invalid copy value is dropped; mail budget 429; concurrent convert → one 201,
  one 409.
- Update the tel-018 permission assertions for `convert`.
- **Web**: vitest for the convert form and the hint; a Playwright spec for the conversion flow.
