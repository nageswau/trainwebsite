# EduSphere Agent CRM — Administrator Manual

For **Overseas Admins** (and Super Admins, read-only) managing education agencies. Verified in the browser on
2026-10-05 against docs commit `717d6aa8` (`main` @ `6a9be770`). Quick starts:
[Overseas Admin](../role-guides/overseas-admin-agencies.md) · [Super Admin](../role-guides/super-admin-agencies.md) ·
[Troubleshooting](../troubleshooting.md).

## Agencies
- [Approve, reject, suspend or reinstate agencies](adm-001-agency-approvals.md)
- [Agent network](adm-002-agent-network.md)
- [Agency detail](adm-003-agency-detail.md)
- [Suspend or reinstate an agency](adm-004-suspend-reinstate.md)

## Money
- [Agent deposits — remittance and refund](adm-005-agent-deposits.md)
- [Commission amounts and payouts](adm-006-commissions.md)

## Users and access
- [Super Admin access to agency screens](adm-007-super-admin-access.md)
- [Re-send a set-password link](adm-008-resend-welcome-link.md)

## Security notes (as built; audit-log details are from the application code)
- Agency members who are pending, rejected or suspended can sign in but see only an "Access unavailable" page.
- Opening an agency's student or application records is written to the audit log; so are agency status changes,
  deposit remittances/refunds and report exports.
- Staff permissions (Verify documents, View reports) are set by the agency's own Masters, not by EduSphere admins.
