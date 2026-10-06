# School CRM — Troubleshooting

> Based on behaviour observed in the browser on 2026-10-06 (sessions S2–S10, `main` @ `ce1f07c2`). Items marked
> *(from code)* were not reproduced in the browser.

**Who is "your administrator"?**
- Principals, Teachers and Parents: your **School Coordinator**.
- School Coordinators, Academic Team, Career Counselors and Psychometric Team: EduSphere's **Overseas Admin**.

## Signing in and accounts

### "Invalid credentials"
- **Possible Cause:** Wrong email or password, **or** your account has been deactivated (the message is the same).
- **Resolution:** Check the email, then use **Forgot your password?**.
- **When to Contact Administrator:** The reset does not help; ask whether your account is active.

### "Use the correct EduSphere portal for this account: sign in at /overseas/login"
- **Possible Cause:** You used the IT Training sign-in page.
- **Resolution:** Sign in at **/overseas/login**.
- **When to Contact Administrator:** Not needed.

### No password-reset email arrives
- **Possible Cause:** Reset emails depend on EduSphere's setup; on the documentation server none was sent (U2).
- **Resolution:** Check spam and wait a few minutes.
- **When to Contact Administrator:** Nothing arrives after 10 minutes.

### "Reset token is invalid or expired"
- **Possible Cause:** The link is older than 30 minutes (reset) or 72 hours (first password), was already used, or a
  newer link was sent.
- **Resolution:** Request a new link and use the newest one straight away.
- **When to Contact Administrator:** A first-password link has expired; the Overseas Admin re-sends it.

### "This invite has already been used, expired, or was revoked"
- **Possible Cause:** The invitation was already accepted, or 7 days have passed.
- **Resolution:** If you already set a password, sign in.
- **When to Contact Administrator:** You never set a password; ask your School Coordinator for a new invitation.

### "Access unavailable — Not authenticated" during work
- **Possible Cause:** Your sign-in ended (about 60 minutes *(from code)*) or you signed out in another tab.
- **Resolution:** Click **Return to login** and sign in again. Unsaved changes may be lost.
- **When to Contact Administrator:** It happens within minutes of signing in, every time.

### "Access unavailable" with another reason (wrong role, not assigned, not linked)
- **Possible Cause:** The page belongs to another role, or the student is not assigned/linked to you.
- **Resolution:** Use the pages in your own sidebar.
- **When to Contact Administrator:** You should have access to that student.

### No Sign out on a phone
- **Possible Cause:** The narrow-screen menu does not include Sign out.
- **Resolution:** Close the browser, or widen the window to see the sidebar.
- **When to Contact Administrator:** Not needed.

## Dashboards and pages

### "This section couldn't load. Refresh to try again." *(from code)*
- **Possible Cause:** A temporary problem fetching figures.
- **Resolution:** Refresh the page.
- **When to Contact Administrator:** It persists for more than an hour.

### A change does not show after saving (career goal, closed batch)
- **Possible Cause:** Some Career Counselor pages do not refresh themselves.
- **Resolution:** Reload the page.
- **When to Contact Administrator:** The change is still missing after reloading.

### "Something went wrong."
- **Possible Cause:** Seen when a text was far too long (a 170-character student name, a 210-character activity title,
  a 90-character subject).
- **Resolution:** Shorten the text and try again.
- **When to Contact Administrator:** It happens with normal-length text.

### "Access unavailable — [object Object]" at `/students/new`
- **Possible Cause:** There is no separate new-student page.
- **Resolution:** Open **Students** and use **Add one student**.
- **When to Contact Administrator:** Not needed.

## Students, team and transfers (School Coordinator)

### Bulk upload: every row rejected with "Full name is required"
- **Possible Cause:** The header row was changed.
- **Resolution:** Start again from a freshly downloaded template.
- **When to Contact Administrator:** Not needed.

### A student "Jane Doe" appeared after a bulk upload
- **Possible Cause:** The template's example row was not deleted.
- **Resolution:** Students cannot be deleted from the roster.
- **When to Contact Administrator:** Ask EduSphere to remove the student.

### "Photo must be at most 2 MB"
- **Possible Cause:** The image is too large.
- **Resolution:** Compress or resize it (JPEG or PNG) and upload again.
- **When to Contact Administrator:** Not needed.

### Invitation created but "email sending isn't configured… share the link manually"
- **Possible Cause:** The email could not be sent; the page does not show the link.
- **Resolution:** None on screen.
- **When to Contact Administrator:** Always; the Overseas Admin can help.

### "Email already exists" when inviting
- **Possible Cause:** The person already has an EduSphere login.
- **Resolution:** For a Parent, link them to the student instead (**Link parent**).
- **When to Contact Administrator:** The person is not a parent and needs a second role.

### The Mark attendance card shows everyone ticked again
- **Possible Cause:** The card always starts with everyone ticked.
- **Resolution:** Untick absentees again and save; saving replaces the earlier record.
- **When to Contact Administrator:** Not needed.

### A transfer request never reaches the admin
- **Possible Cause:** The Student ID was mistyped; the page gives the same answer either way (privacy).
- **Resolution:** Check the Student ID with the family and request again.
- **When to Contact Administrator:** The ID is correct and nothing happens after several days.

### Promotion: every student shows "Already in {year}"
- **Possible Cause:** The new academic year has not been opened.
- **Resolution:** None on screen.
- **When to Contact Administrator:** Always; EduSphere opens the year.

## Partnership

### "This school's {Tier} partnership does not include {Service} (requires {Tier} or higher)."
- **Possible Cause:** Your tier does not include that service.
- **Resolution:** Choose another option, or check **Entitlements**.
- **When to Contact Administrator:** You need the service; the Overseas Admin can change the tier.

### "This school has no active partnership tier." / "This school's partnership expired on {date}."
- **Possible Cause:** No tier has been set, or it has expired. The Entitlements page shows no warning for an expired
  tier, only the past date.
- **Resolution:** None on screen.
- **When to Contact Administrator:** Always.

## Results and records (EduSphere specialists)

### "No students in your portfolio yet. Contact your Overseas Admin."
- **Possible Cause:** No school is in your portfolio, or its schools have no students.
- **Resolution:** None on screen.
- **When to Contact Administrator:** Always; portfolios cannot be changed on screen after the account is created.

### No Verify or Publish button on a result
- **Possible Cause:** You uploaded it yourself, or it is already published.
- **Resolution:** Ask another Academic Team member.
- **When to Contact Administrator:** Not needed.

### Marks above the maximum were saved (for example "75/50 (150%)")
- **Possible Cause:** The single-result form does not check the maximum.
- **Resolution:** Do not verify or publish it.
- **When to Contact Administrator:** Ask EduSphere to correct the Draft.

### "This record was changed by someone else…"
- **Possible Cause:** The career record was saved elsewhere while your form was open.
- **Resolution:** Copy what you need, click **Discard my changes and reload**, and edit again.
- **When to Contact Administrator:** Not needed.

### A wrong psychometric report address was attached
- **Possible Cause:** The address cannot be changed after attaching.
- **Resolution:** None on screen.
- **When to Contact Administrator:** Always; contact EduSphere support.

## Parents

### "No child linked to your account yet."
- **Possible Cause:** The school has not linked you to your child.
- **Resolution:** None on screen.
- **When to Contact Administrator:** Always; contact the School Coordinator.

### The unread count never goes down
- **Possible Cause:** Opening a notification from the parent pages does not mark it read (U8).
- **Resolution:** None; the count includes notifications you have already read.
- **When to Contact Administrator:** Not needed.

### "Upcoming session" message shows an odd time
- **Possible Cause:** The time inside the message is UTC (U9).
- **Resolution:** Use **Upcoming sessions** on the dashboard (IST).
- **When to Contact Administrator:** Not needed.

## Administrators

### "Access unavailable — Workspace not found" (Super Admin)
- **Possible Cause:** Schools, School Staff and School Applications are built only for the Overseas Admin.
- **Resolution:** Ask an Overseas Admin to make the change.
- **When to Contact Administrator:** Not applicable.

### A Coordinator or specialist did not receive the welcome email
- **Possible Cause:** Email was not configured or delivery failed (the success message turns amber).
- **Resolution:** **Users** > **Re-send link** (see [Re-send a set-password link](admin-manual/sadm-010-resend-set-password-link.md)).
- **When to Contact Administrator:** The re-sent email also does not arrive; check the email setup.

### School application refused with a tier message
- **Possible Cause:** Application support needs Gold or Platinum.
- **Resolution:** Upgrade the school's tier first (see [Edit school and tier](admin-manual/sadm-003-edit-school-and-tier.md)).
- **When to Contact Administrator:** Not applicable.
