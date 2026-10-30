# Overseas Counselor CRM — Admin Manual

For the **Overseas Admin**, who creates counselors, assigns students and applications to them, watches their overdue work and configures the counselor tools. There is also a section on what the **Super Admin** can and can't do. Checked against `main` @ `045d8c40`.

## Counselor accounts and assignment
| Page | What it covers |
|---|---|
| [Create a counselor account](accounts/adm-001-create-counselor.md) | New counselor with a welcome link |
| [Manage counselor users](accounts/adm-002-manage-counselor-users.md) | Set-up status, re-send link, edit, deactivate |
| [Assign or change a student's counselor](accounts/adm-003-student-counselor.md) | With a reason when changing |
| [Assign or change an application's counselor](accounts/adm-004-application-counselor.md) | Including new agency applications |

## Oversight
| Page | What it covers |
|---|---|
| [Counselor tasks (admin view)](escalation/esc-001-counselor-tasks-admin.md) | Every counselor's tasks; giving a counselor a task |
| [Overdue by counselor and the escalation notice](escalation/esc-002-overdue-escalation.md) | Who is behind |
| [Team performance](performance/perf-001-team-performance.md) | Counselors compared |
| [One counselor's report](performance/perf-002-counselor-report.md) | One counselor in detail |

## Configuration
| Page | What it covers |
|---|---|
| [Document checklist templates](config/cfg-001-checklist-templates.md) | Required documents and the Ready-for-Submission gate |
| [Reminder rules](config/cfg-002-reminder-rules.md) | Automatic tasks and notices |
| [Counselor message templates](config/cfg-003-message-templates.md) | WhatsApp and email starters |
| Archived students: restore *(coming — S10)* | Bring back an archived student |

## Super Admin: what is different
| Topic | Super Admin |
|---|---|
| Creating a counselor | On **Users**, **Division** starts on **it**; choose **overseas** or the counselor can't use the Overseas portal ([details](accounts/adm-001-create-counselor.md)) |
| Assigning counselors to students or applications | Not available: no **EduSphere counsellor** column, and the server refuses |
| Counselor tasks, performance, checklists, reminder rules, message templates | Open by address only (not in the Super Admin sidebar); the page shows the Overseas Admin's sidebar |
| Counselor workspace pages (Leads, Dashboard) | Open, but show "Unable to load your leads." / "Dashboard sections are unavailable right now." instead of an access message |
| Archived students / restore † | Refused ("Overseas Administrator role required") |
| Escalation notices | Not received; only Overseas Admins are told (and they have no notifications page either) |

† From the code; checked in the browser in session S10.

## Things to know
- **Moving a lead between counselors** isn't possible from any screen. A counselor can return a lead to its telecaller, who can hand it to another counselor.
- **Deactivating a counselor** doesn't move their leads, students, applications or tasks. Reassign students and applications before or after deactivating.
- **New agency applications** arrive with no counselor and nobody is alerted. Filter Application Tracking by **Counsellor = Not assigned** every day.
- The **Manage users** table is wider than its panel at normal desktop widths; scroll it sideways to reach the buttons.

See also: [Overseas Admin role guide](../role-guides/overseas-admin-counselors.md) · [Super Admin role guide](../role-guides/super-admin-counselors.md) · [Troubleshooting](../troubleshooting.md)
