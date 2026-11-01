# Counselor CRM — Troubleshooting

Messages exactly as EduSphere shows them, what they mean and what to do. For step-by-step help, follow the link on each row.

## Signing in
| Message or symptom | Meaning | What to do |
|---|---|---|
| Invalid credentials | Wrong email/password, or the account is deactivated | Use **Forgot your password?**; if no email arrives, ask the Overseas Admin ([AUTH-001](user-manual/account-access/auth-001-sign-in.md)) |
| Use the correct EduSphere portal for this account: sign in at /overseas/login | You used another portal's sign-in page | Go to `/overseas/login` |
| Reset token is invalid or expired | The link was used, expired or replaced | Request a new link / ask for a re-send ([AUTH-002](user-manual/account-access/auth-002-first-password.md)) |
| No Sign out on a phone | The portal menu has none | Menu → **My profile** → **Logout** ([AUTH-006](user-manual/account-access/auth-006-sign-out.md)) |

## Leads
| Message or symptom | Meaning | What to do |
|---|---|---|
| Set a next action and its due date first | Open stages need a next action | Add one ([LEAD-005](user-manual/leads/lead-005-next-action.md)) |
| Choose a due date from today onwards | Past date | Pick today or later |
| Choose why the lead was lost. | Closing needs a lost reason | Pick a reason ([LEAD-006](user-manual/leads/lead-006-change-stage.md)) |
| Lead already exists. | Mobile or email matches another lead | **Add enquiry to this lead** ([LEAD-002](user-manual/leads/lead-002-new-walk-in-lead.md)) |
| Unlink the student before returning the lead | A student is linked | Unlink first ([CONV-002](user-manual/conversion/conv-002-link-student.md)) |
| Return to telecaller shown on a closed lead | The button doesn't check closure | Don't use it on closed leads ([LEAD-008](user-manual/leads/lead-008-return-to-telecaller.md)) |
| A student account already has this email or mobile. Link the existing student instead. | Duplicate account | Link instead of converting ([CONV-001](user-manual/conversion/conv-001-convert-to-student.md)) |
| The counselor already has an appointment at this time. | Overlapping 60-minute slots | The telecaller picks another time ([CAL-001](user-manual/calendar/cal-001-lead-appointments.md)) |

## Students
| Message or symptom | Meaning | What to do |
|---|---|---|
| Email already exists | The student already has an account | Ask the admin to assign them to you ([STU-003](user-manual/students/stu-003-walk-in-student.md)) |
| A link was just sent; wait {n} seconds before re-sending | One re-send per minute | Wait |
| Counselor shows "Not assigned" on the 360 | Only the student's own counselor link is shown | Expected for application-only students ([STU-004](user-manual/students/stu-004-student-360.md)) |

## Applications and documents
| Message or symptom | Meaning | What to do |
|---|---|---|
| Ready for Submission needs every required checklist document complete | Block-mode gate | Verify the documents or mark them Not required ([APP-005](user-manual/applications/app-005-sub-status-ready-gate.md)) |
| This student already has an open application for this university and course. | Duplicate | Use the existing application |
| Choose the currency of the amounts | Amount without currency | Type a three-letter code such as GBP ([OFR-001](user-manual/offers/ofr-001-offers.md)) |
| A result can be recorded only after the interview date -- or mark it cancelled. | Interview not held yet | Wait until after the date ([OFR-003](user-manual/offers/ofr-003-interviews.md)) |
| Status shows a code such as `university_review` | Internal status in tables | Read the stage on the card or 360 |
| Document not in Document Verification | Not tied to your application | Upload again with the application ([DOC-004](user-manual/documents/doc-004-upload-document.md)) |
| Cannot advance past the checklist stage -- not yet verified: … | Visa documents not verified | Upload and verify them ([VISA-001](user-manual/visa/visa-001-visa-case.md)) |
| This application is closed -- only the Overseas Admin can reopen it. | Terminal outcome | Ask the Overseas Admin |
| Evaluate Applications card cut off at the right | Narrow cards | Scroll inside the card |

## Admin
| Message or symptom | Meaning | What to do |
|---|---|---|
| Manage users buttons not visible | Table wider than its panel | Scroll the table sideways ([ADM-002](admin-manual/accounts/adm-002-manage-counselor-users.md)) |
| New counselor can't sign in to the Overseas portal | Created with Division **it** | Create with **overseas** ([ADM-001](admin-manual/accounts/adm-001-create-counselor.md)) |
| Give a reason for the reassignment / Save disabled | Changing a counselor needs a reason | Enter **Reason for the change** ([ADM-003](admin-manual/accounts/adm-003-student-counselor.md)) |
| Choose a whole number from {min} to {max} | Reminder rule out of range | Use the range shown ([CFG-002](admin-manual/config/cfg-002-reminder-rules.md)) |
