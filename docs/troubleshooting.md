# Agent CRM — Troubleshooting

> Only problems observed in the browser on 2026-10-05 (docs commit `717d6aa8`, `main` @ `6a9be770`), or reported by
> the application with the exact message shown, are listed.

## "Invalid credentials" when signing in

### Problem
The sign-in page shows **Invalid credentials**.

### Possible Cause
The email or password is wrong, or your login has been deactivated by your agency Master.

### Resolution
Check the email, then use **Forgot your password?**. If you are agency staff and the reset does not help, your login
may be deactivated.

### When to Contact Administrator
Staff: contact your agency Master to reactivate you. Masters: contact EduSphere Overseas Admin.

## "Use the correct EduSphere portal for this account"

### Problem
Signing in shows "Use the correct EduSphere portal for this account: sign in at /it/login".

### Possible Cause
Your account belongs to another EduSphere portal.

### Resolution
Sign in at the address shown in the message.

### When to Contact Administrator
If you believe your account should be an Overseas account.

## "Agent registration is pending approval"

### Problem
After signing in, every page shows **Access unavailable — Agent registration is pending approval**.

### Possible Cause
Your agency is waiting for approval, or the registration was rejected (same message).

### Resolution
Wait for approval and sign in again later.

### When to Contact Administrator
If it has been longer than expected — contact EduSphere Overseas Admin.

## "Your agency's account is suspended"

### Problem
Every page shows **Access unavailable — Your agency's account is suspended**.

### Possible Cause
EduSphere suspended the agency.

### Resolution
None from the agency side.

### When to Contact Administrator
Masters contact EduSphere Overseas Admin; staff contact their Master.

## "Only an agency Master can open this page" / "hasn't given you access to reports"

### Problem
A staff member sees **Access unavailable** on Team, Commissions or Reports, or "Staff performance is available to agency Masters."

### Possible Cause
These pages are Master-only; Reports needs the **View reports** permission.

### Resolution
Use the pages in your sidebar.

### When to Contact Administrator
Ask your agency Master if you need Reports.

## "Reset token is invalid or expired"

### Problem
The password link shows **Reset token is invalid or expired**.

### Possible Cause
The link is older than 30 minutes (reset) or 72 hours (first-time), or was already used.

### Resolution
Click **Request a new reset link**.

### When to Contact Administrator
For a first-time invitation, ask your Master (staff) or EduSphere Overseas Admin to re-send it.

## "A student with this email or phone already exists in your agency"

### Problem
Adding a student shows a possible duplicate.

### Possible Cause
Another student in your agency has the same email or phone.

### Resolution
Click **Go back** to check, or **Save anyway** if it is a different person.

### When to Contact Administrator
Not needed.

## "An application for this university/course already exists"

### Problem
Creating an application is refused.

### Possible Cause
The student already has an open application for that university and course.

### Resolution
Open the existing application or choose another course.

### When to Contact Administrator
Not needed.

## Visa stage will not leave Checklist

### Problem
"Cannot advance past the checklist stage -- not yet verified: {documents}."

### Possible Cause
Checklist documents are missing, not uploaded for this application, or not verified.

### Resolution
Upload each listed document under Documents with this application selected and have it verified.

### When to Contact Administrator
Not needed.

## "Upload a PDF, JPEG or PNG file"

### Problem
An upload is refused.

### Possible Cause
The file is another type (for example Word or text).

### Resolution
Save or scan the document as PDF, JPEG or PNG and upload again.

### When to Contact Administrator
Not needed.

## Staff member has no Review button on documents

### Problem
Documents show no **Review** button for a staff member.

### Possible Cause
The staff member does not have **Verify documents**.

### Resolution
A Master turns it on under Team > Permissions.

### When to Contact Administrator
Not needed.

## "Commission cannot be claimed in its current status"

### Problem
Claiming a commission is refused.

### Possible Cause
The commission is still **estimated** (no amount set) or already claimed.

### Resolution
Wait until the status is **eligible**.

### When to Contact Administrator
If a commission stays estimated for long — contact EduSphere Overseas Admin.

## "Online payment is unavailable right now. Nothing has been charged."

### Problem
The deposit section shows this message and no **Pay deposit** button (message from the application code; not
observed in testing).

### Possible Cause
Online payment is not set up on this EduSphere installation.

### Resolution
None from the agency side.

### When to Contact Administrator
Contact EduSphere Overseas Admin.

## Admin: "A refund cannot exceed the paid amount"

### Problem
Recording a refund is refused after confirming.

### Possible Cause
The refund amount is higher than the paid deposit.

### Resolution
Enter at most the amount shown under the field ("At most ₹…").

### When to Contact Administrator
Not applicable.

## Admin: "Access unavailable — Workspace not found" (Super Admin)

### Problem
A Super Admin opening Agents, Commissions or Overseas Applications sees **Workspace not found**.

### Possible Cause
These Overseas Admin screens are not available to Super Admin.

### Resolution
Use an Overseas Admin account.

### When to Contact Administrator
Not applicable.
