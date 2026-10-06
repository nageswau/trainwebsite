# Quick-start guide: Super Admin (school screens)

> Verified 2026-10-06 against `main` @ `ce1f07c2` (School CRM documentation, sessions S2–S10).

## Role Purpose
The Super Admin can monitor partner schools and review transfers and activity feedback. Creating and changing schools,
tiers, staff and applications is left to the Overseas Admin.

## Login
Sign in at **/overseas/login** with your Super Admin account.

## Dashboard
The Super Admin dashboard is outside this guide. For schools, use **School Analytics** in the sidebar.

![School Analytics as Super Admin](../screenshots/admin-schools/40-analytics-super-admin.png)

## Menus Available
| Sidebar / address | Use it to |
|---|---|
| School Analytics (sidebar) | All schools at a glance |
| `/overseas/admin/school-transfers` (type the address) | Review transfer requests |
| `/overseas/admin/activity-feedback` (type the address) | Read activity feedback |

## Main Activities
| Activity | Guide |
|---|---|
| Monitor schools | [School Analytics](../admin-manual/sadm-008-school-analytics.md) |
| Review transfers | [Review transfers](../admin-manual/sadm-007-review-transfers.md) |
| Read feedback | [Activity feedback](../admin-manual/sadm-009-activity-feedback.md) |
| Know your limits | [Super Admin and the school screens](../admin-manual/sadm-011-super-admin-access.md) |

## Daily Workflows
1. Check **School Analytics** for flags.
2. When needed, open **School Transfers** by address and decide pending requests.

## Restrictions
- **Schools**, **School Staff** and **School Applications** show "Access unavailable — Workspace not found".
- School Transfers and Activity Feedback open with the Overseas Admin sidebar; go to `/admin` to return.

![Workspace not found](../screenshots/admin-schools/21-superadmin-workspace-not-found.png)

## Common Problems
| Problem | What to do |
|---|---|
| "Workspace not found" | Ask an Overseas Admin to make the change. |
| Sidebar changed to Overseas Admin links | Expected on Transfers and Feedback; go to `/admin`. |

More: [Troubleshooting](../troubleshooting.md) · [FAQ](../faq.md).

## Related Features
- [Overseas Admin quick-start](overseas-admin-schools.md)
