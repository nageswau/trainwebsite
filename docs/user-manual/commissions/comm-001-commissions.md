# View and claim commissions

> Doc ID: DOC-COMM-001 · Verified 2026-10-05 against docs commit `717d6aa8` (`main` @ `6a9be770`) · Roles: Agency Master

## Purpose
See the commissions EduSphere owes your agency and claim them once they are eligible.

## Who Can Use This Feature
**Agency Masters only.** Staff do not see Commissions; typing its address shows "Only an agency Master can open this page".

## Prerequisites
A commission exists (created automatically when an application is [enrolled](../applications/app-009-confirm-enrollment.md))
and EduSphere has set its amount (status **eligible**).

## How to Access
Sidebar > **Commissions**.

## Steps

### Step 1 — Read the commissions table
The table **Commissions** ("Eligibility, claims, and payment status.") lists each commission: **Reference**,
**Application**, **Amount**, **Status** and **Claim reference**. It has **Search records**, **Filter by**, sortable
headings and **Rows per page**.

![Commissions table](../../screenshots/commissions/01-commissions-table.png)

| Status (as shown) | Meaning | Next step |
|---|---|---|
| estimated | Created at enrollment; EduSphere has not set the amount yet (shown as 0) | **Do not claim yet** — wait for eligible |
| eligible | Amount set; you can claim it | Claim |
| claimed | You claimed it (a claim reference is shown) | Wait for payout |
| payout_pending / paid | EduSphere is paying / has paid it | — |

### Step 2 — Claim an eligible commission
1. Copy the commission's **Reference** from the table.
2. In **Claim commission**, paste it into **Eligible commission reference**.
3. Click **Claim commission**. The message **Commission claimed.** appears.

![Claim form](../../screenshots/commissions/02-claim-form.png)

The row shows **claimed** and a claim reference such as "CLM-20261005-1C01F9".

![Commission claimed](../../screenshots/commissions/03-commission-claimed.png)

## Fields
| Field | Description | Required | Example |
|---|---|---|---|
| Eligible commission reference | The commission's Reference from the table. | Yes | 15cb3215-6664-474e-917f-f26603fc71d7 |

## Expected Result
EduSphere's Overseas Admin approves the payout and the status becomes **paid**. Paid commissions count as
**Revenue** on the dashboard and in **Reports > Commission**.

## Validation Messages
| Message | When |
|---|---|
| Commission not found | The reference is wrong. |
| Commission cannot be claimed in its current status | The commission was already claimed, or is being paid / paid. |

## Common Errors
**Problem:** "Commission cannot be claimed in its current status".
**Cause:** The commission was already claimed (or is already paid).
**Resolution:** Check the Claim reference column; nothing more to do.

**Problem:** A commission was claimed while still **estimated** and its amount stays at 0.
**Cause:** EduSphere accepts a claim on an estimated commission, and a claim locks the amount — EduSphere can then no longer set it.
**Resolution:** Always wait until the status is **eligible** before claiming. If it already happened, contact EduSphere Overseas Admin.

## Tips
- Claim only commissions with status **eligible**. The screen also accepts **estimated** ones, but that locks the amount at 0.

## Related Features
- [Confirm enrollment](../applications/app-009-confirm-enrollment.md)
- [Commission report](../reports/rpt-003-commission-report.md)
- Admin: [Commission amounts and payouts](../../admin-manual/adm-006-commissions.md)
