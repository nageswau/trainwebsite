# School CRM Demo — UAT Checklist

> For client stakeholders who want to check every feature after the demo. Every row links to the School CRM manual
> page with the full steps. Behaviour was browser-verified on 2026-10-06 against `main` @ `ce1f07c2`. Rows marked
> **(partial)** were not fully verified in the browser (see `docs/school-crm/documentation-review-report.md` §5).

Record a result for each row: **P** = pass, **F** = fail (write what happened), **N/A** = not tested.

| Environment | Build / commit | Tester | Date |
|---|---|---|---|
| https://dev.edusphere.org.uk | | | |

## 1. School administration (Overseas Admin)

| ID | Check | Expected result | Guide | P/F |
|---|---|---|---|---|
| SA-01 | **Schools** list: search, filter, rows per page | Partner Schools with "N role-scoped records" | [sadm-001](../../school-crm/admin-manual/sadm-001-partner-schools-list.md) | |
| SA-02 | **Create school** with tier and Coordinator | "School created. School code {code}. Coordinator account ready…" | [sadm-002](../../school-crm/admin-manual/sadm-002-create-a-school.md) | |
| SA-03 | **Edit school profile**: upgrade, then downgrade (with **Confirm downgrade**) | "Partnership is now {tier}; newly available: …"; Coordinator and Principal notified | [sadm-003](../../school-crm/admin-manual/sadm-003-edit-school-and-tier.md) | |
| SA-04 | **Onboard several schools (CSV)** | Each row Added or Rejected | [sadm-004](../../school-crm/admin-manual/sadm-004-bulk-onboard-schools.md) | |
| SA-05 | **School Staff**: create Academic / Career / Psychometric accounts with a portfolio | "Account created for {email}…" | [sadm-005](../../school-crm/admin-manual/sadm-005-create-school-staff.md) | |
| SA-06 | **School Applications**: start one for a Gold/Platinum student; try a Bronze/Silver student **(partial)** | "Application started for {student}."; Bronze/Silver refused with a tier message | [sadm-006](../../school-crm/admin-manual/sadm-006-school-applications.md) | |
| SA-07 | **School Transfers**: approve one, reject one | "Moved {student} to {school}…" / "Request rejected for {student}." | [sadm-007](../../school-crm/admin-manual/sadm-007-review-transfers.md) | |
| SA-08 | **School Analytics** | KPIs, service use per school, flags | [sadm-008](../../school-crm/admin-manual/sadm-008-school-analytics.md) | |
| SA-09 | **Activity Feedback** with School filter | Feedback from Coordinators | [sadm-009](../../school-crm/admin-manual/sadm-009-activity-feedback.md) | |
| SA-10 | **Users** > **Re-send link** | New set-password email; the old link stops working | [sadm-010](../../school-crm/admin-manual/sadm-010-resend-set-password-link.md) | |
| SA-11 | Super Admin opens school screens | Known: "Workspace not found" on several (P7) | [sadm-011](../../school-crm/admin-manual/sadm-011-super-admin-access.md) | |

## 2. Account access (all roles)

| ID | Check | Expected result | Guide | P/F |
|---|---|---|---|---|
| AU-01 | Sign in at `/overseas/login` | Role's dashboard | [auth-001](../../school-crm/user-manual/account-access/auth-001-sign-in.md) | |
| AU-02 | Accept an invitation (7 days, once) | Signed in on the role's dashboard | [auth-002](../../school-crm/user-manual/account-access/auth-002-accept-an-invitation.md) | |
| AU-03 | Set the first password from the welcome link (72 h) | Password set; back to sign-in | [auth-003](../../school-crm/user-manual/account-access/auth-003-set-your-first-password.md) | |
| AU-04 | **Forgot your password?** **(partial)** | Known: no email on plain SMTP (P1) | [auth-004](../../school-crm/user-manual/account-access/auth-004-forgot-password.md) | |
| AU-05 | **Change password** | Password changed | [auth-005](../../school-crm/user-manual/account-access/auth-005-change-password.md) | |
| AU-06 | **My profile** and notification settings | Saved | [auth-006](../../school-crm/user-manual/account-access/auth-006-my-profile.md) | |
| AU-07 | Sign out; session expiry **(partial)** | Signed out | [auth-007](../../school-crm/user-manual/account-access/auth-007-sign-out-and-session-expiry.md) | |
| AU-08 | Open a page of another role | "Access unavailable" | [auth-008](../../school-crm/user-manual/account-access/auth-008-access-unavailable.md) | |
| AU-09 | Sidebar per role | Matches the role guide | [auth-009](../../school-crm/user-manual/account-access/auth-009-find-your-way-around.md) | |

## 3. Dashboards

| ID | Role | Expected result | Guide | P/F |
|---|---|---|---|---|
| DA-01 | Coordinator | "School at a glance", 20 figures, shortcuts, upcoming activities | [dash-001](../../school-crm/user-manual/dashboards/dash-001-coordinator-dashboard.md) | |
| DA-02 | Principal | Same figures plus the student list | [dash-002](../../school-crm/user-manual/dashboards/dash-002-principal-dashboard.md) | |
| DA-03 | Teacher | "Your students" | [dash-003](../../school-crm/user-manual/dashboards/dash-003-teacher-dashboard.md) | |
| DA-04 | Parent | "My children", upcoming sessions, notifications | [dash-004](../../school-crm/user-manual/dashboards/dash-004-parent-dashboard.md) | |
| DA-05 | Academic Team | Portfolio progress, results, test prep, languages | [dash-005](../../school-crm/user-manual/dashboards/dash-005-academic-team-dashboard.md) | |
| DA-06 | Career Counselor | Records, add a record, preferences, 360° list | [dash-006](../../school-crm/user-manual/dashboards/dash-006-career-counselor-dashboard.md) | |
| DA-07 | Psychometric Team | Assessments, assign, bulk, 360° list | [dash-007](../../school-crm/user-manual/dashboards/dash-007-psychometric-team-dashboard.md) | |

## 4. Students and team (Coordinator)

| ID | Check | Expected result | Guide | P/F |
|---|---|---|---|---|
| SR-01 | Roster | Students listed | [stu-001](../../school-crm/user-manual/students/stu-001-view-the-roster.md) | |
| SR-02 | **Add one student** | "{Name} added to the roster." | [stu-002](../../school-crm/user-manual/students/stu-002-add-a-student.md) | |
| SR-03 | Edit a student | Saved | [stu-003](../../school-crm/user-manual/students/stu-003-edit-a-student.md) | |
| SR-04 | **Link parent** | "Parent linked to this student." | [stu-004](../../school-crm/user-manual/students/stu-004-link-a-parent.md) | |
| SR-05 | Bulk roster upload (CSV) | Upload result Added/Rejected | [stu-005](../../school-crm/user-manual/students/stu-005-bulk-upload-roster.md) | |
| SR-06 | **Profile & timeline** | Profile and journey timeline | [stu-006](../../school-crm/user-manual/students/stu-006-student-profile-and-timeline.md) | |
| SR-07 | Photo: add, replace, remove | "Photo saved." | [stu-007](../../school-crm/user-manual/students/stu-007-student-photo.md) | |
| SR-08 | Progress report PDF | "Report downloaded." | [stu-008](../../school-crm/user-manual/students/stu-008-progress-report-pdf.md) | |
| SR-09 | **Promotion** (needs an open academic year) | "Done for {year}: …" | [stu-009](../../school-crm/user-manual/students/stu-009-promote-students.md) | |
| TE-01 | **Invite a team member** | "Invite sent to {email}. It's valid for 7 days." | [team-001](../../school-crm/user-manual/team/team-001-invite-a-team-member.md) | |
| TE-02 | **Team** and **Pending invites** | Members and invites with expiry | [team-002](../../school-crm/user-manual/team/team-002-view-your-team.md) | |
| TE-03 | Deactivate, then reactivate | Deactivated user gets "Invalid credentials"; access returns | [team-003](../../school-crm/user-manual/team/team-003-deactivate-or-reactivate.md) | |

## 5. Transfers

| ID | Check | Expected result | Guide | P/F |
|---|---|---|---|---|
| TR-01 | **Request a transfer** out | "Transfer request sent for review…" | [xfer-001](../../school-crm/user-manual/transfers/xfer-001-request-a-transfer-out.md) | |
| TR-02 | **Request a student from another school** | "If that Student ID belongs to a student at another school…" | [xfer-002](../../school-crm/user-manual/transfers/xfer-002-request-a-student-in.md) | |
| TR-03 | Track and **Cancel** | Status updates; cancelled request | [xfer-003](../../school-crm/user-manual/transfers/xfer-003-track-and-cancel-transfers.md) | |

## 6. Activities and attendance

| ID | Role | Check | Expected result | Guide | P/F |
|---|---|---|---|---|---|
| AT-01 | Coordinator | **Schedule an activity** | "{Title} scheduled." | [act-001](../../school-crm/user-manual/activities/act-001-schedule-an-activity.md) | |
| AT-02 | Coordinator | **Mark attendance** | "Attendance recorded for {n} student(s)." | [act-002](../../school-crm/user-manual/activities/act-002-mark-activity-attendance.md) | |
| AT-03 | Coordinator | **Give feedback** on a past EduSphere activity | "Feedback saved for {title}." | [act-003](../../school-crm/user-manual/activities/act-003-give-activity-feedback.md) | |
| AT-04 | Principal | **Feedback** | Read-only feedback list | [act-004](../../school-crm/user-manual/activities/act-004-view-activity-feedback.md) | |
| AT-05 | Teacher | Daily **Attendance** | "Attendance saved for {n} students on {date}." | [act-005](../../school-crm/user-manual/activities/act-005-daily-class-attendance.md) | |

## 7. Academic Team

| ID | Check | Expected result | Guide | P/F |
|---|---|---|---|---|
| AC-01 | Portfolio progress | Progress per student | [acad-001](../../school-crm/user-manual/academic-team/acad-001-portfolio-progress.md) | |
| AC-02 | **Upload a result** | "{Subject} result saved as Draft." | [acad-002](../../school-crm/user-manual/academic-team/acad-002-upload-a-result.md) | |
| AC-03 | Second member **Verify**, **Publish**; uploader cannot | "Result verified." / "Result published." | [acad-003](../../school-crm/user-manual/academic-team/acad-003-verify-and-publish-results.md) | |
| AC-04 | Bulk results (CSV) | Rows Added/Rejected | [acad-004](../../school-crm/user-manual/academic-team/acad-004-bulk-results.md) | |
| AC-05 | IELTS/SAT **Start preparation**, **Record score** | "IELTS preparation started." / "Result recorded." | [acad-005](../../school-crm/user-manual/academic-team/acad-005-test-preparation.md) | |
| AC-06 | **Start classes**, **Mark certified** | "{Language} classes started." / "Marked certified." | [acad-006](../../school-crm/user-manual/academic-team/acad-006-foreign-language-classes.md) | |
| AC-07 | Bulk test prep and languages (CSV) | Rows Added/Rejected | [acad-007](../../school-crm/user-manual/academic-team/acad-007-bulk-test-prep-and-language.md) | |

## 8. Digital Portfolio (Teacher / Academic Team / Coordinator)

| ID | Check | Expected result | Guide | P/F |
|---|---|---|---|---|
| PO-01 | Portfolio overview | Sections listed | [port-001](../../school-crm/user-manual/portfolio/port-001-digital-portfolio-overview.md) | |
| PO-02 | Add, edit, delete an entry | "Skill added." etc. | [port-002](../../school-crm/user-manual/portfolio/port-002-portfolio-entries.md) | |
| PO-03 | Skill India certification | Entry saved | [port-003](../../school-crm/user-manual/portfolio/port-003-skill-india-certification.md) | |
| PO-04 | Internship and certificate | Entry saved | [port-004](../../school-crm/user-manual/portfolio/port-004-internships-and-certificates.md) | |
| PO-05 | Personal statement | "Personal statement saved." | [port-005](../../school-crm/user-manual/portfolio/port-005-personal-statement.md) | |

## 9. Career Counselor

| ID | Check | Expected result | Guide | P/F |
|---|---|---|---|---|
| CC-01 | **Add a record** | "Record saved." | [car-001](../../school-crm/user-manual/career-counselor/car-001-add-a-record.md) | |
| CC-02 | **Edit** and move status | Status moves in order | [car-002](../../school-crm/user-manual/career-counselor/car-002-edit-a-record.md) | |
| CC-03 | **Career preferences** | "Career preferences saved." | [car-003](../../school-crm/user-manual/career-counselor/car-003-career-preferences.md) | |
| CC-04 | **Set career goal** (reload to see it, P13) | "Career goal saved." | [car-004](../../school-crm/user-manual/career-counselor/car-004-career-goal.md) | |
| CC-05 | **Skills** > **Create a batch** | Batch page opens | [car-005](../../school-crm/user-manual/career-counselor/car-005-skills-batches.md) | |
| CC-06 | Edit, close, reopen a batch | Status changes | [car-006](../../school-crm/user-manual/career-counselor/car-006-edit-close-reopen-batch.md) | |
| CC-07 | Enrol students; change their status | "{n} students enrolled." | [car-007](../../school-crm/user-manual/career-counselor/car-007-enrolments.md) | |
| CC-08 | Sessions and attendance | "Attendance saved for {date}." | [car-008](../../school-crm/user-manual/career-counselor/car-008-sessions-and-attendance.md) | |
| CC-09 | Assessments and scores | "Scores saved for {assessment}." | [car-009](../../school-crm/user-manual/career-counselor/car-009-assessments-and-scores.md) | |
| CC-10 | **Funding** > **Add a case** | "Case saved." | [car-010](../../school-crm/user-manual/career-counselor/car-010-open-a-funding-case.md) | |
| CC-11 | Move stage; close with a reason | One stage at a time; closed is final | [car-011](../../school-crm/user-manual/career-counselor/car-011-update-or-close-a-funding-case.md) | |

## 10. Psychometric Team

| ID | Check | Expected result | Guide | P/F |
|---|---|---|---|---|
| PS-01 | **Assign an assessment** | "Assessment assigned." | [psy-001](../../school-crm/user-manual/psychometric-team/psy-001-assign-an-assessment.md) | |
| PS-02 | **Attach report** | "Report attached."; status completed | [psy-002](../../school-crm/user-manual/psychometric-team/psy-002-attach-a-report.md) | |
| PS-03 | **Record results** | "Results saved." | [psy-003](../../school-crm/user-manual/psychometric-team/psy-003-record-results.md) | |
| PS-04 | Bulk assessments (CSV) | Rows Added/Rejected | [psy-004](../../school-crm/user-manual/psychometric-team/psy-004-bulk-assessments.md) | |

## 11. Student 360°, reports and partnership

| ID | Role | Check | Expected result | Guide | P/F |
|---|---|---|---|---|---|
| RE-01 | Any school role | **Open 360° view** | Tabs per service; restricted tabs for service roles | [s360-001](../../school-crm/user-manual/student-360/s360-001-student-360-view.md) | |
| RE-02 | Coordinator / Principal | **Download school report (PDF)** | "Report downloaded." | [rpt-001](../../school-crm/user-manual/reports/rpt-001-school-report-pdf.md) | |
| RE-03 | Coordinator / Principal | School summary | Tiles and charts | [rpt-002](../../school-crm/user-manual/reports/rpt-002-school-summary.md) | |
| RE-04 | Coordinator / Principal | Grade-wise comparison | Columns per grade | [rpt-003](../../school-crm/user-manual/reports/rpt-003-grade-wise-comparison.md) | |
| RE-05 | Coordinator / Principal | Student development; **Update thresholds** | At-risk and top-performer lists | [rpt-004](../../school-crm/user-manual/reports/rpt-004-student-development.md) | |
| RE-06 | Coordinator / Principal | Scorecards with Grade filter | Scorecards; "Not in plan" outside the tier | [rpt-005](../../school-crm/user-manual/reports/rpt-005-student-scorecards.md) | |
| RE-07 | Coordinator / Principal | **Global Education** | Pipeline and students | [rpt-006](../../school-crm/user-manual/reports/rpt-006-global-education.md) | |
| EN-01 | Coordinator / Principal | **Entitlements** | "Plan: {Tier} Partner", with "— valid until {date}" when a date is set | [ent-001](../../school-crm/user-manual/entitlements/ent-001-view-entitlements.md) | |
| EN-02 | Specialist | A service outside the tier | "This school's {Tier} partnership does not include {Service} (requires {Tier} or higher)." | [ent-002](../../school-crm/user-manual/entitlements/ent-002-partnership-tiers-explained.md) | |

## 12. Notifications and parent

| ID | Role | Check | Expected result | Guide | P/F |
|---|---|---|---|---|---|
| NO-01 | Coordinator / Principal | **Notifications** after a tier change or transfer decision | Notices listed | [notif-001](../../school-crm/user-manual/notifications/notif-001-staff-notifications.md) | |
| NO-02 | Parent | **Notifications** after an activity is scheduled | Notice listed (unread count does not drop, P3) | [notif-002](../../school-crm/user-manual/notifications/notif-002-parent-notifications.md) | |
| PA-01 | Parent | **View full profile & progress**; PDF | All sections; published results only | [par-001](../../school-crm/user-manual/parent/par-001-child-profile-and-progress.md) | |

## Known product findings

These are known and recorded. Note them, but do not log them as new defects: P1–P17 and U-items in
`docs/school-crm/documentation-review-report.md`.

## Sign-off

| Name | Role | Result (Accepted / Accepted with findings / Not accepted) | Signature / date |
|---|---|---|---|
| | | | |
