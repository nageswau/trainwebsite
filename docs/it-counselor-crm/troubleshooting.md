# IT Counselor CRM — Troubleshooting

Problems seen while verifying this guide, with their cause and fix.

| Problem | Cause | Fix |
|---|---|---|
| "Use the correct EduSphere portal for this account: sign in at /it/login" | You used the Overseas or administration sign-in | Sign in at `/it/login` ([Sign in](user-manual/account-access/auth-001-sign-in.md)) |
| **Invalid credentials** although the password is right | The account may be deactivated | Ask the IT Admin ([Deactivated account](user-manual/account-access/auth-006-sign-out.md)) |
| "Access unavailable — User unavailable" on a page you had open | Your account was deactivated | Ask the IT Admin to reactivate it |
| "Reset token is invalid or expired" | The welcome link was used, replaced or is older than 72 hours | Ask the IT Admin to **Re-send link**, or use **Forgot your password?** |
| No **Sign out** on a phone | The phone menu has none | **My profile** → **Logout** |
| "404 This page could not be found." on a student | The student is not (or no longer) yours | Go back to **Students**; ask the IT Admin if you should have them ([Student 360](user-manual/students/stu-002-student-360.md)) |
| Timetable shows "No classes this week" for a new student | Their enrolment is still **Pending consent**, or the batch has not started | Ask the student to accept the enrolment agreement; use **Next week** ([Timetable](user-manual/timetable/tt-001-timetable.md)) |
| No batch-change notification for a student | Notices go only for **active** enrolments | As above |
| Fee unchanged after a discount request | Waiting for approval | Ask the IT Admin ([Discount approvals](admin-manual/admin/adm-009-discount-approvals.md)) |
| "Enter an amount above 0 and no more than INR {balance}…" | Discount empty, zero or more than the balance | Enter a smaller amount |
| "Choose a PDF, DOC or DOCX file first." | No file chosen | Choose the resume file, then **Upload** |
| A resume version did not go to HR | **Share with HR** was unticked | Upload again with **Share with HR** ticked ([Resume](user-manual/resume/res-001-upload-resume.md)) |
| Onboarding checklist stays at 0 of 5 | Items are never ticked automatically | Tick them yourself ([Checklist](user-manual/conversion/conv-003-onboarding-checklist.md)) |
| IT Admin: **Change counsellor** says "Student not found" | The student joined IT from Overseas; this screen cannot change them | Known limitation (finding P11) |
| IT Admin: a deactivated counselor still has students | Deactivation does not move students | **Change counsellor** for each one ([ADM-003](admin-manual/admin/adm-003-student-counselor.md)) |
| IT Admin: **Merge a duplicate** form is squeezed | It opens inside the narrow Action column | Widen the window, or merge from the Telecaller Manager's lead page ([Merge](admin-manual/admin/adm-007-merge-duplicate.md)) |
| IT Admin: no escalation notices | Escalation is off (0 hours) | Ask the Telecaller Manager to set hours for the IT team ([Escalation](admin-manual/admin/adm-014-escalation.md)) |
| Dashboard: "The start date must be on or before the end date" | **From** is after **To** | Swap the dates |

## Related
[FAQ](faq.md) · [User manual](user-manual/README.md) · [Administrator manual](admin-manual/README.md)
