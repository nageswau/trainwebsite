# Agent CRM Demo — UAT Checklist

> For client stakeholders who want to check every feature after the demo. Every row links to the user or admin
> manual page that describes the full steps. Behaviour was browser-verified on 2026-10-05 against `main` @
> `6a9be770`. Rows marked **(code)** were confirmed only in the application code and need a first browser check.

Record a result for each row: **P** = pass, **F** = fail (write what happened), **N/A** = not tested.

| Environment | Build / commit | Tester | Date |
|---|---|---|---|
| https://dev.edusphere.org.uk | | | |

## 1. Account access

| ID | Role | Check | Expected result | Guide | P/F |
|---|---|---|---|---|---|
| AC-01 | New agency | Register as **Education agent** | Signed in; "Agent registration is pending approval" | [auth-001](../../user-manual/account-access/auth-001-register-an-agency.md) | |
| AC-02 | Any | Sign in and sign out at `/overseas/login` | Lands on the role's dashboard; sign-out returns to the EduSphere home page | [auth-002](../../user-manual/account-access/auth-002-sign-in-and-sign-out.md) | |
| AC-03 | Pending agency | Open any page | "Access unavailable" card with **Sign out** | [auth-003](../../user-manual/account-access/auth-003-access-unavailable.md) | |
| AC-04 | Any | **Forgot your password?** | Reset email; link valid 30 minutes | [auth-004](../../user-manual/account-access/auth-004-reset-password.md) | |
| AC-05 | Any | **Change password** (10–128 characters, different from current) | Password changed | [auth-005](../../user-manual/account-access/auth-005-change-password.md) | |
| AC-06 | Any | **My profile**: edit and save **(code)** for the save messages | "Your profile was updated." | [auth-006](../../user-manual/account-access/auth-006-my-profile.md) | |

## 2. Agency approval and oversight (Overseas Admin)

| ID | Role | Check | Expected result | Guide | P/F |
|---|---|---|---|---|---|
| AD-01 | Overseas Admin | **Agents** > **Pending** > **Approve** | "{agency} approved."; agency can work after reload | [adm-001](../../admin-manual/adm-001-agency-approvals.md) | |
| AD-02 | Overseas Admin | **Reject** a pending agency | Agency moves to Rejected | [adm-001](../../admin-manual/adm-001-agency-approvals.md) | |
| AD-03 | Overseas Admin | **Agent network** tabs and counts | All/Active/Suspended/Pending/Rejected with Masters, Staff, Students, Applications, Enrollments | [adm-002](../../admin-manual/adm-002-agent-network.md) | |
| AD-04 | Overseas Admin | Open an agency's detail and its records | Summary, commission, deposits, Masters; records read-only (archived filter **(code)**) | [adm-003](../../admin-manual/adm-003-agency-detail.md) | |
| AD-05 | Overseas Admin | **Suspend** > **Confirm suspend**, then **Reinstate** | Agency users see "Access unavailable" while suspended; access returns after reinstating | [adm-004](../../admin-manual/adm-004-suspend-reinstate.md) | |
| AD-06 | Overseas Admin | **Users** > **Re-send link** for a staff member | New set-password email | [adm-008](../../admin-manual/adm-008-resend-welcome-link.md) | |
| AD-07 | Super Admin | Open `/overseas/admin/agent-network` and `/overseas/admin/agents` | Network read-only; Agents shows "Workspace not found" (known, P2) | [adm-007](../../admin-manual/adm-007-super-admin-access.md) | |

## 3. Dashboard

| ID | Role | Check | Expected result | Guide | P/F |
|---|---|---|---|---|---|
| DB-01 | Master | Dashboard | "Whole agency"; Students, Pipeline, Documents, Commission; staff table with Unassigned | [dash-001](../../user-manual/dashboard/dash-001-master-dashboard.md) | |
| DB-02 | Staff | Dashboard | "Your assigned students"; no Commission or staff table | [dash-002](../../user-manual/dashboard/dash-002-staff-dashboard.md) | |

## 4. Team and staff (Master)

| ID | Role | Check | Expected result | Guide | P/F |
|---|---|---|---|---|---|
| TM-01 | Master | **Invite a Master** (limit of 3 active Masters **(code)**) | "Invite sent."; badge "Invite pending" | [team-001](../../user-manual/team/team-001-masters.md) | |
| TM-02 | Master | **Add staff** | "{code} created. A set-password link was emailed…"; **Set-up pending** | [team-002](../../user-manual/team/team-002-create-staff.md) | |
| TM-03 | New staff | Set password from the welcome email (72 h) and sign in | Staff dashboard | [team-002](../../user-manual/team/team-002-create-staff.md) | |
| TM-04 | Master | Edit, **Reset**, deactivate and reactivate a staff member | Deactivated staff cannot sign in; reactivated staff can (sign-in after reactivation **(code)**) | [team-003](../../user-manual/team/team-003-manage-staff.md) | |
| TM-05 | Master | **Permissions**: Verify documents, View reports | "{code} permissions saved."; staff gain Review / Reports on next page load | [team-004](../../user-manual/team/team-004-staff-permissions.md) | |
| TM-06 | Master | **Activity** on a staff row | List of the staff member's actions | [team-005](../../user-manual/team/team-005-staff-activity.md) | |
| TM-07 | Staff | Open a Master-only page (e.g. Team) | "Access unavailable — Only an agency Master can open this page" | [agency-staff guide](../../role-guides/agency-staff.md) | |

## 5. Students and universities

| ID | Role | Check | Expected result | Guide | P/F |
|---|---|---|---|---|---|
| ST-01 | Master/Staff | Search and filter students | Matching cards | [stu-001](../../user-manual/students/stu-001-find-students.md) | |
| ST-02 | Master / Staff | **Add student** | "{name} added."; staff-added students are assigned to the staff member | [stu-002](../../user-manual/students/stu-002-add-a-student.md) | |
| ST-03 | Master/Staff | View and edit a student | Changes saved | [stu-003](../../user-manual/students/stu-003-view-and-edit-a-student.md) | |
| ST-04 | Master | Archive and unarchive (unarchive message **(code)**) | Student hidden from the active list, then back | [stu-004](../../user-manual/students/stu-004-archive-a-student.md) | |
| ST-05 | Master | **Assign** to staff | "{student} assigned to…"; staff notified | [stu-005](../../user-manual/students/stu-005-assign-a-student.md) | |
| ST-06 | Master/Staff | **Record counseling** | "Counseling saved for {name}." | [stu-006](../../user-manual/students/stu-006-record-counseling.md) | |
| ST-07 | Master/Staff | **Add university to shortlist** | "Saved to shortlist." | [stu-007](../../user-manual/students/stu-007-university-shortlist.md) | |
| ST-08 | Master/Staff | **Journey** and **Show history** (steps with applications **(code)**) | Journey steps and history list | [stu-008](../../user-manual/students/stu-008-journey-and-history.md) | |
| ST-09 | Master/Staff | Link an existing student account | Student linked; email masked | [stu-009](../../user-manual/students/stu-009-link-a-student-account.md) | |
| UN-01 | Master | **Universities** > **Add university** (editing **(code)**) | "{name} added."; staff can only view | [uni-001](../../user-manual/universities/uni-001-agency-universities.md) | |

## 6. Applications

| ID | Role | Check | Expected result | Guide | P/F |
|---|---|---|---|---|---|
| AP-01 | Master/Staff | Filter tabs All/Draft/Submitted/Offer received/Visa/Enrolled/Withdrawn | Correct applications per tab | [app-001](../../user-manual/applications/app-001-view-applications.md) | |
| AP-02 | Master/Staff | **Create application** | "Application created." at **Enquiry**; duplicate university+course refused | [app-002](../../user-manual/applications/app-002-create-an-application.md) | |
| AP-03 | Master/Staff | Edit an application | Saved; university cannot be changed | [app-003](../../user-manual/applications/app-003-edit-an-application.md) | |
| AP-04 | Master/Staff | Application detail page | Sections Offer, Deposit, Visa, Enrollment | [app-004](../../user-manual/applications/app-004-application-detail.md) | |
| AP-05 | Master/Staff | **Change status** forward; **Withdraw** | "Status updated to {stage}."; no backward moves; Withdrawn final | [app-005](../../user-manual/applications/app-005-change-status-or-withdraw.md) | |
| AP-06 | Master/Staff | **Record offer** (offer letter optional) | "Offer saved."; stage moves to Offer | [app-006](../../user-manual/applications/app-006-record-an-offer.md) | |
| AP-07 | Master/Staff | **Record deposit** and **Pay deposit** (Razorpay window **(code)**) | "Deposit saved."; after payment **Paid** and **Download receipt** | [app-007](../../user-manual/applications/app-007-deposit-and-payment.md) | |
| AP-08 | Master/Staff | **Start visa case**; try to leave Checklist with an unverified document | Refused "Cannot advance past the checklist stage…"; moves once verified | [app-008](../../user-manual/applications/app-008-visa-case.md) | |
| AP-09 | Master/Staff | **Record decision** | "Visa decision recorded." (final) | [app-008](../../user-manual/applications/app-008-visa-case.md) | |
| AP-10 | Master | **Enroll student** (date warning **(code)**) | "Enrollment confirmed."; Enrolled; commission estimated | [app-009](../../user-manual/applications/app-009-confirm-enrollment.md) | |
| AP-11 | Staff | Open **Enrollment** on an Offer-stage application | "An agency Master confirms enrollment." | [app-009](../../user-manual/applications/app-009-confirm-enrollment.md) | |

## 7. Documents

| ID | Role | Check | Expected result | Guide | P/F |
|---|---|---|---|---|---|
| DO-01 | Master/Staff | Browse Pending / Uploaded / Additional; download | Files listed and downloadable | [doc-001](../../user-manual/documents/doc-001-browse-documents.md) | |
| DO-02 | Master/Staff | **Upload document** (PDF/JPEG/PNG, ≤ 20 MB) | "Document uploaded. It is waiting for review." | [doc-002](../../user-manual/documents/doc-002-upload-a-document.md) | |
| DO-03 | Master/Staff | Replace a file | New version; old one in history | [doc-003](../../user-manual/documents/doc-003-replace-a-file.md) | |
| DO-04 | Master | **Review**: Verified / Rejected / Changes required | "{document} for {student}: {decision}." | [doc-004](../../user-manual/documents/doc-004-review-a-document.md) | |
| DO-05 | Staff with Verify | **Review** | Only **Mark verified** available | [doc-004](../../user-manual/documents/doc-004-review-a-document.md) | |
| DO-06 | Master/Staff | Document history | List of uploads and decisions | [doc-005](../../user-manual/documents/doc-005-document-history.md) | |
| DO-07 | Master/Staff | **Request a document** (student-with-login side **(code)**) | "Request added to Additional documents." | [doc-006](../../user-manual/documents/doc-006-request-a-document.md) | |

## 8. Tasks and notifications

| ID | Role | Check | Expected result | Guide | P/F |
|---|---|---|---|---|---|
| TK-01 | Master/Staff | Tasks tabs (Open, Overdue, …) | Correct tasks per tab | [task-001](../../user-manual/tasks/task-001-view-tasks.md) | |
| TK-02 | Master/Staff | **New task**, **Mark done**, **Cancel task** (editing **(code)**) | "“{title}” added."; status changes | [task-002](../../user-manual/tasks/task-002-manage-a-task.md) | |
| NT-01 | Staff | **Notifications** after being assigned a student | "Student assigned to you"; unread badge | [notif-001](../../user-manual/notifications/notif-001-notifications.md) | |

## 9. Commissions and deposits

| ID | Role | Check | Expected result | Guide | P/F |
|---|---|---|---|---|---|
| CM-01 | Overseas Admin | **Set/adjust commission amount** on an estimated row | "Commission amount updated."; status eligible | [adm-006](../../admin-manual/adm-006-commissions.md) | |
| CM-02 | Master | **Claim commission** on an **eligible** row | "Commission claimed."; `CLM-…` reference | [comm-001](../../user-manual/commissions/comm-001-commissions.md) | |
| CM-03 | Overseas Admin | **Approve commission payout** | "Payout approved -- commission marked paid." | [adm-006](../../admin-manual/adm-006-commissions.md) | |
| DP-01 | Overseas Admin | **Agent deposits** > **Paid** > **Record remittance** | "Remittance recorded for {student}." | [adm-005](../../admin-manual/adm-005-agent-deposits.md) | |
| DP-02 | Overseas Admin | **Record refund** (≤ paid amount) | "Refund recorded for {student}." (final) | [adm-005](../../admin-manual/adm-005-agent-deposits.md) | |

> Do **not** claim an *estimated* commission during UAT on shared data: it locks the amount at 0 (P1). If you test it
> deliberately, record it as a finding against P1.

## 10. Reports and performance

| ID | Role | Check | Expected result | Guide | P/F |
|---|---|---|---|---|---|
| RP-01 | Master | **Reports** tabs with filters > **Apply** | "{N} rows · As of {time}" | [rpt-001](../../user-manual/reports/rpt-001-agency-reports.md) | |
| RP-02 | Master | **Download CSV** | CSV downloads | [rpt-002](../../user-manual/reports/rpt-002-export-csv.md) | |
| RP-03 | Master | **Commission** tab | Totals per currency and by status/university/country/intake | [rpt-003](../../user-manual/reports/rpt-003-commission-report.md) | |
| RP-04 | Staff with View reports | **Reports** | Own students only; no Staff performance / Commission tabs | [rpt-001](../../user-manual/reports/rpt-001-agency-reports.md) | |
| RP-05 | Staff without permission | **Reports** | "Access unavailable — Your agency Master hasn't given you access to reports" | [agency-staff guide](../../role-guides/agency-staff.md) | |
| PF-01 | Master | **Staff Performance** | Funnel and per-staff table | [perf-001](../../user-manual/staff-performance/perf-001-staff-performance.md) | |

## Known product findings

These are known and recorded. Note them, but do not log them as new defects: P1–P10 in
`docs/documentation-review-report.md` §3.

## Sign-off

| Name | Role | Result (Accepted / Accepted with findings / Not accepted) | Signature / date |
|---|---|---|---|
| | | | |
