# Quick-start guide: Overseas Admin (school management)

> Verified 2026-10-06 against `main` @ `ce1f07c2` (School CRM documentation, sessions S2–S10).

## Role Purpose
The Overseas Admin manages EduSphere's partner schools: creates schools and their Coordinators, sets partnership tiers,
creates the Academic Team, Career Counselor and Psychometric Team accounts and their school portfolios, decides
transfer requests, starts overseas applications for school students and follows school analytics and activity
feedback. This guide covers only the school screens of the Overseas Admin portal.

## Login
Sign in at **/overseas/login** with your Overseas Admin account.

## Dashboard
The Overseas Admin dashboard is outside this guide. For schools, start at **Schools** or **School Analytics**.

![School Analytics](../screenshots/admin-schools/37-analytics-kpis.png)

## Menus Available
| Sidebar | Use it to |
|---|---|
| Schools | List, create, edit (tier) and bulk-onboard schools |
| School Staff | Create specialist accounts and their school portfolios |
| School Applications | Start overseas applications for school students |
| School Transfers | Approve or reject transfer requests |
| Activity Feedback | Read Coordinators' feedback on EduSphere activities |
| School Analytics | All schools at a glance, utilization and flags |
| Users | Re-send a set-password link |

## Main Activities
| Activity | Guide |
|---|---|
| Find a school | [Partner Schools list](../admin-manual/sadm-001-partner-schools-list.md) |
| Add schools | [Create a school](../admin-manual/sadm-002-create-a-school.md), [Bulk onboard](../admin-manual/sadm-004-bulk-onboard-schools.md) |
| Change details or tier | [Edit school and tier](../admin-manual/sadm-003-edit-school-and-tier.md) |
| Create specialist staff | [School staff](../admin-manual/sadm-005-create-school-staff.md) |
| Overseas applications | [School applications](../admin-manual/sadm-006-school-applications.md) |
| Transfers | [Review transfers](../admin-manual/sadm-007-review-transfers.md) |
| Monitor | [School Analytics](../admin-manual/sadm-008-school-analytics.md), [Activity feedback](../admin-manual/sadm-009-activity-feedback.md) |
| Help with logins | [Re-send a set-password link](../admin-manual/sadm-010-resend-set-password-link.md) |

## Daily Workflows
1. Check **School Transfers** for pending requests.
2. Check **School Analytics** for **Renewal due** and **No active tier** flags.
3. Onboard new schools and make sure the Coordinator received the welcome email (re-send if not).
4. Weekly: read **Activity Feedback**.

## Restrictions
- There is no screen for opening a new academic year; it is done through the EduSphere API (U3). Schools cannot run
  **Promotion** until it is open.
- How school-linked applications move past `enquiry` is not on these screens (VERIFICATION REQUIRED, U15).
- A specialist's school portfolio cannot be changed after the account is created; ask EduSphere's technical team.
- Lowering a tier asks for confirmation; work already started can still be finished.

## Common Problems
| Problem | What to do |
|---|---|
| "Email already exists" | Use a different email for the Coordinator. |
| Welcome email not delivered | [Re-send a set-password link](../admin-manual/sadm-010-resend-set-password-link.md). |
| A specialist sees no students | Check their school portfolio in **School Staff**. |
| Application refused with a tier message | Application support needs Gold or Platinum. |

More: [Troubleshooting](../troubleshooting.md) · [FAQ](../faq.md).

## Related Features
- [Admin manual index](../admin-manual/README.md)
- [Partnership tiers explained](../user-manual/entitlements/ent-002-partnership-tiers-explained.md)
