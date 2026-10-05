# Agent CRM — Frequently Asked Questions

> Answers are based on behaviour verified in the browser on 2026-10-05 (docs commit `717d6aa8`, `main` @ `6a9be770`).

## Accounts and access

**How do I register my agency?**
On the Overseas sign-in page click **Create an account**, choose Account type **Education agent** and fill in the form.
See [Register an agency](user-manual/account-access/auth-001-register-an-agency.md).

**I registered but every page says "Agent registration is pending approval". Why?**
New agencies must be approved by EduSphere's Overseas Admin. A rejected registration shows the same message. EduSphere
does not email you when this changes — sign in again later or contact EduSphere.

**How many Masters can my agency have?**
Up to 3 active Masters. Staff logins are separate; the screens show no fixed limit, but at most 20 can be created or reset per day.

**What is the difference between a Master and Staff?**
Masters see and manage the whole agency. Staff see only students assigned to them and cannot manage the team,
commissions, staff performance, archive/assign students or confirm enrollment. See
[Agency Master](role-guides/agency-master.md) and [Agency Staff](role-guides/agency-staff.md).

**Can a staff member verify documents or see reports?**
Only if a Master turns on **Verify documents** or **View reports** for them under Team > Permissions. Verifying staff
can only mark documents verified; only Masters can reject or request changes.

**How long do password links last?**
Reset links: 30 minutes. First-time "set your password" links for new staff and Masters: 72 hours.

**Can I change my email address?**
No — not from My profile, and a Master cannot change a staff member's email.

## Students

**What is the difference between "Add student" and "Link student"?**
**Add student** records a student who has no EduSphere login. **Link student** connects a student who registered on
EduSphere themselves. See [Link an existing student account](user-manual/students/stu-009-link-a-student-account.md).

**Why can't I edit a student?**
Students with their own login (badge **Has login**) update their own details; archived students must be unarchived
first.

**Does deleting a student exist?**
No. A Master can **Archive** a student; nothing is deleted and the student can be unarchived.

## Applications

**Why is a withdrawn application missing from "All applications"?**
Withdrawn applications appear only under **Applications > Withdrawn**.

**Can I move an application back to an earlier stage?**
No. Stages only move forward. Withdrawing is final.

**How do I mark an application Enrolled?**
A Master uses **Enroll student** in the application's Enrollment section (from the Offer stage onwards). It cannot be
set with Change status.

**How do I change the university of an application?**
Withdraw it and create a new application.

## Documents

**Which files can I upload?**
PDF, JPEG or PNG, up to 20 MB (limit set by EduSphere). The type is checked from the file's content.

**Why does the visa checklist say "Not uploaded" although I uploaded the document?**
The document must be uploaded with that **application** selected and then be **verified**.

## Money

**How is the university deposit paid?**
Through EduSphere's Razorpay payment window (**Pay deposit**). Once paid, EduSphere forwards it to the university and
records the remittance; the agency sees it on the application.

**When can we claim a commission?**
When its status is **eligible** — after EduSphere sets the amount on the commission created at enrollment.

**Why are commission totals shown per currency?**
Amounts in different currencies are never added together.

## Notifications and reports

**When do deadline reminders arrive?**
Once a day at 08:00 India time, for application and offer deadlines today, tomorrow or in three days, plus a summary
of overdue tasks.

**Is there a "mark all as read"?**
No. Opening a notification marks it as read.

**How large can a CSV export be?**
Up to 10,000 rows, and up to 30 exports in 10 minutes.
