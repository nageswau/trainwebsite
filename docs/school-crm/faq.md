# School CRM — Frequently Asked Questions

> Answers are based on behaviour verified in the browser on 2026-10-06 (sessions S2–S10, `main` @ `ce1f07c2`).
> Statements marked *(from code)* were read from the application code and not seen in the browser.

## Accounts and access

**Where do school users sign in?**
Everyone signs in at **/overseas/login** (the page is titled "Overseas Education Portal"). EduSphere then opens your
role's dashboard. See [Sign in](user-manual/account-access/auth-001-sign-in.md).

**How do I get an account?**
- School Coordinators and EduSphere specialists (Academic Team, Career Counselor, Psychometric Team) are created by
  EduSphere's Overseas Admin and receive a "set your password" email.
- Principals, Teachers and Parents are invited by their School Coordinator.

**How long do the links in emails last?**
| Link | Valid for |
|---|---|
| Invitation (Principal, Teacher, Parent) | 7 days |
| First "set your password" link (Coordinator, specialists) | 72 hours |
| Password reset link | 30 minutes |

**I forgot my password. What do I do?**
Use **Forgot your password?** on the sign-in page. On the documentation server no reset email was sent (U2), so if
nothing arrives, contact your School Coordinator (Principals, Teachers, Parents) or EduSphere (Coordinators and
specialists). See [Forgot your password](user-manual/account-access/auth-004-forgot-password.md).

**Can I change my email address?**
No. You can change your name and phone in **My profile**; the email cannot be changed there.

**Why was I signed out in the middle of my work?**
A sign-in lasts about 60 minutes *(from code)*. Sign in again; save long forms regularly. See
[Sign out and session expiry](user-manual/account-access/auth-007-sign-out-and-session-expiry.md).

**How do I sign out on a phone?**
The phone menu has no **Sign out**. Close the browser, or widen the window to see the sidebar.

**I have children at two schools. Do I need two logins?**
No. The second school links your existing account; both children appear on your dashboard, grouped by school.

## Students and team (School Coordinator)

**Can I delete a student?**
No. Students cannot be deleted from the roster; ask EduSphere.

**How many students can I upload at once?**
Use the CSV template on **Students > Bulk upload**. Each row is checked on its own; good rows are added even if others
are rejected. Delete the template's example row ("Jane Doe") first, or it is imported as a real student.

**How do I give a Teacher access to a student?**
Set the Teacher as the student's **Assigned Teacher** (class teacher) when adding or editing the student.

**An invitation email was not sent. Can I re-send it?**
Not from the Team page; there is no re-send, revoke or copy-link action. Contact your Overseas Admin.

**What happens when I deactivate someone?**
They can no longer sign in ("Invalid credentials") and get no new notifications. **Reactivate** undoes it. There is no
confirmation step.

**How does a student move to another school?**
The Coordinator requests the transfer; EduSphere's Overseas Admin approves or rejects it. Parents keep access after
the move. See [Request a transfer out](user-manual/transfers/xfer-001-request-a-transfer-out.md).

**Why can't I promote students?**
Promotion works only after EduSphere opens the new academic year. Until then every student shows "Already in {year}".

## Results, reports and records

**When do parents see a result?**
Only after it is **published**. An Academic Team member uploads it as a Draft; a different member verifies it and then
publishes it.

**Why do the dashboard and the Reports page show different numbers for a grade?**
The Reports "Students by grade" chart groups by the Grade/Class text as typed ("Class X" and "Grade 10" are separate);
the dashboard and the other reports use the grade level. Use the same wording for every student.

**Why is "Career guidance" 5 on Reports but "Career Guidance Completed" 2 on the dashboard?**
The Reports ring counts students with any career record; the dashboard counts completed guidance sessions.

**Can I keep my at-risk thresholds?**
No. They are in the page address; bookmark the address to reuse them. Opening Reports from the sidebar resets them to
40 and 85.

**What do "Not in plan" and "Not tracked yet" mean on scorecards?**
"Not in plan": your partnership tier does not include that area. "Not tracked yet": EduSphere does not record it yet
(Scholarship).

## Partnership tiers

**What does each tier include?**
See [Partnership tiers explained](user-manual/entitlements/ent-002-partnership-tiers-explained.md). Tiers build on
each other: Bronze < Silver < Gold < Platinum.

**Why was an action refused with a partnership message?**
Your tier does not include that service, your school has no tier, or the tier has expired. The screens are not hidden
by tier; EduSphere refuses the action when you try it.

**Our partnership expired, but the Entitlements page looks normal.**
The page shows only the past "valid until" date, with no warning. Contact your Overseas Admin to renew.

**What happens to work in progress after a downgrade?**
Work already started can still be finished; nothing new can be started for removed services *(from code; the
notification says so)*.

## Notifications

**Why does the parent "unread" number never go down?**
Opening a notification from the parent pages does not mark it read (U8). Staff notifications are marked read when you
click **Open**.

**Why does an "Upcoming session" message show 04:30 for a 10:00 session?**
The time inside that message is in UTC (U9). The **Upcoming sessions** list on the dashboard shows the correct IST time.

**Can I get notifications on WhatsApp or SMS?**
Save a valid mobile number in **My profile**, then tick the channel. Whether messages are actually sent depends on
EduSphere's setup (not configured on the documentation server).

## EduSphere specialists

**Why do I see no students?**
Your school portfolio is empty, or the schools in it have no students yet. Ask your Overseas Admin. A portfolio cannot
be changed on screen after the account is created.

**Can I change a psychometric report address after attaching it?**
No. Contact EduSphere support.

## Administrators

**Can a Super Admin create schools?**
No. **Schools**, **School Staff** and **School Applications** show "Workspace not found" for a Super Admin. An Overseas
Admin must do it. See [Super Admin and the school screens](admin-manual/sadm-011-super-admin-access.md).

**A Coordinator never received the welcome email.**
Re-send the set-password link from **Users**. See
[Re-send a set-password link](admin-manual/sadm-010-resend-set-password-link.md).
