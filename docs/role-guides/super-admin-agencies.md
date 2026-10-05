# Quick-start guide: Super Admin (agency screens)

> Verified 2026-10-05 against docs commit `717d6aa8` (`main` @ `6a9be770`). Covers only the agency (Agent CRM) screens.

## Role Purpose
A Super Admin can look at agencies and their deposits, but day-to-day agency administration belongs to an Overseas
Admin.

## Login
Sign in at `/admin/login`. You land on `/admin`.

## Dashboard
The Super Admin dashboard has no agency links.

## Menus Available
None for agencies. Type these addresses:

| Address | Access |
|---|---|
| `/overseas/admin/agent-network` (and agency details) | Read-only — no Suspend/Reinstate |
| `/overseas/admin/agent-deposits` | Read-only — no remittance/refund |
| `/overseas/admin/agents`, `/overseas/admin/commissions`, `/overseas/admin/applications` | "Access unavailable — Workspace not found" |

![Agent network as Super Admin](../screenshots/admin-agencies/32-super-admin-network.png)

## Main Activities
- Review the agency network and deposit totals.

## Daily Workflows
None specific to agencies.

## Restrictions
- No screen lets a Super Admin approve, reject, suspend or reinstate agencies, record deposits or manage commissions
  (the API accepts some of these — see the documentation review report).

## Common Problems
| Problem | Resolution |
|---|---|
| "Access unavailable — Workspace not found" on Agents or Commissions | Use an Overseas Admin account |

## Related Features
[Super Admin access](../admin-manual/adm-007-super-admin-access.md) · [Overseas Admin guide](overseas-admin-agencies.md)
