# Quick-start guide: Overseas Admin (agency management)

> Verified 2026-10-05 against docs commit `717d6aa8` (`main` @ `6a9be770`). Covers only the agency (Agent CRM) part of the Overseas Admin role.

## Role Purpose
The Overseas Admin decides which agencies may use EduSphere, oversees them, handles their deposit money and pays
their commissions.

## Login
Sign in at the Overseas sign-in page (`/overseas/login`). You land on the Overseas Admin dashboard.

## Dashboard
The Overseas Admin sidebar includes the agency screens: **Agents**, **Commissions**, **Agent deposits** and
**Agent network** (and **Users** for re-sending set-password links).

## Menus Available
| Sidebar | Use it to | Guide |
|---|---|---|
| Agents | Approve, reject, suspend, reinstate agencies | [Agency approvals](../admin-manual/adm-001-agency-approvals.md) |
| Agent network | See all agencies; open details; suspend/reinstate | [Agent network](../admin-manual/adm-002-agent-network.md), [Agency detail](../admin-manual/adm-003-agency-detail.md) |
| Agent deposits | Record remittances and refunds | [Agent deposits](../admin-manual/adm-005-agent-deposits.md) |
| Commissions | Set amounts, approve payouts | [Commissions](../admin-manual/adm-006-commissions.md) |
| Users | Re-send set-password links | [Re-send a link](../admin-manual/adm-008-resend-welcome-link.md) |

## Main Activities
![Pending agencies](../screenshots/admin-agencies/01-agent-approvals-pending.png)

1. Approve new agency registrations (Agents > Pending).
2. Set the amount on new **estimated** commissions; approve payouts after agencies claim.
3. Record remittances (and refunds) for paid deposits.

## Daily Workflows
1. **Agents > Pending** — approve or reject new agencies (EduSphere does not notify them; tell them yourself).
2. **Commissions** — set amounts on estimated rows; approve claimed rows.
3. **Agent deposits > Paid** — record remittances once finance has paid the universities.

## Restrictions
- Manually created commissions must be approved by a different Overseas Admin than the one who created them.
- A refund cannot exceed the paid amount and cannot be changed afterwards.
- Agency student and application records are read-only for you (Agent network).

## Common Problems
| Problem | Resolution |
|---|---|
| "Cannot {action} an organisation that is {status}" | Someone else changed it; reload |
| "Commission must be claimed by the Agent before payout can be approved" | Wait for the agency to claim |
| "A refund cannot exceed the paid amount" | Enter at most the paid amount |

More: [Troubleshooting](../troubleshooting.md).

## Related Features
[Admin manual index](../admin-manual/README.md) · [Super Admin guide](super-admin-agencies.md)
