# IT Counselor CRM — FAQ

Answers based on behaviour verified in the running application (`main` @ `6b61546c`).

## Signing in
**Where do IT counselors sign in?**
At `/it/login`. Signing in elsewhere shows "Use the correct EduSphere portal for this account: sign in at /it/login". See [Sign in](user-manual/account-access/auth-001-sign-in.md).

**How long is the welcome link valid?**
72 hours. The IT Admin can re-send it while the account is **Awaiting setup** or **Link expired**. See [Set your first password](user-manual/account-access/auth-002-first-password.md).

**How do I sign out on a phone?**
The phone menu has no **Sign out**. Open **My profile** and use **Logout** in the site header. See [Sign out](user-manual/account-access/auth-006-sign-out.md).

## Leads
**How do leads reach me?**
A telecaller hands them over, or the Telecaller Manager moves one to you. See [Handover](admin-manual/handoffs/ho-001-telecaller-handover.md).

**Can I book a counselling appointment?**
No. Only the lead's telecaller books, and only before handing the lead over. You confirm it and then mark it completed or a no-show. See [Lead appointments](user-manual/appointments/appt-001-lead-appointments.md).

**Is there a Tasks or Calendar page?**
No. Follow-ups live on the lead page and on your dashboard. See [Follow-ups](user-manual/leads/lead-007-follow-ups.md).

**Can I export my leads?**
No; there is no export for IT counselors.

**Does sending WhatsApp send the message?**
**Send WhatsApp** opens WhatsApp with the text and records the send on the lead. See [WhatsApp](user-manual/leads/lead-009-whatsapp.md).

## Conversion
**What happens when I convert a lead?**
EduSphere creates (or reuses) the student account, enrols them in the batch with the fee and installments, and emails the welcome link. The enrolment is **Pending consent** until the student accepts the agreement; then the lead becomes **Converted**. See [Convert](user-manual/conversion/conv-001-convert-new-student.md).

**The student already has an account with that email. What do I do?**
Choose **Enrol {name}** and **Enrol existing student**. See [Convert into an existing account](user-manual/conversion/conv-002-convert-existing-student.md).

**Does the onboarding checklist tick itself?**
No. Tick each item as the student completes it. See [Onboarding checklist](user-manual/conversion/conv-003-onboarding-checklist.md).

## Students and fees
**Why can't I see a student I used to look after?**
The IT Admin moved them to another counselor. You get **Student reassigned** with the reason.

**Can I record a payment?**
No. Payments are recorded by the IT Admin or paid online by the student. You can request a discount. See [Fee summary](user-manual/fees/fee-001-fee-summary.md).

**I requested a discount but the fee didn't change.**
It changes only after an approver approves it. See [Request a discount](user-manual/fees/fee-002-request-discount.md).

**Who sees my student notes?**
Only staff, until the author shares a note with the student. See [Student notes](user-manual/notes/note-001-student-notes.md).

**When does a student count as at risk?**
When the daily 07:00 IST check finds they crossed a threshold the IT Admin set for their programme. See [Risk and lifecycle cards](user-manual/students/stu-004-risk-lifecycle.md).

## Administration
**Can I move many students at once?**
No; one row at a time on **Students**. See [Assign or change a student's counselor](admin-manual/admin/adm-003-student-counselor.md).

**Where is follow-up escalation set?**
On the Telecaller Manager's **Alert settings** (IT team). It is off by default. See [Escalation](admin-manual/admin/adm-014-escalation.md).

## Related
[Troubleshooting](troubleshooting.md) · [User manual](user-manual/README.md) · [Administrator manual](admin-manual/README.md)
