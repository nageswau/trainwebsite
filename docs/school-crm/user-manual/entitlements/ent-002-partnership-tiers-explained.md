# Partnership tiers explained

> Doc ID: DOC-SCH-ENT-002 · Verified on 2026-10-06 against `main` @ `ce1f07c2` · Roles: all school roles (reference)

## Purpose
Understand what each partnership tier includes, and what the "not included" and "expired" messages mean.

## Who Can Use This Feature
Everyone. This is a reference page.

## Prerequisites
None.

## How to Access
Read here. To see your own school's tier, use sidebar > **Entitlements** (School Coordinator, Principal).

## Steps

### Step 1 — Find your tier
Tiers build on each other: **Bronze < Silver < Gold < Platinum**. Each tier includes everything in the tiers below it.

| Tier | Adds these services |
|---|---|
| Bronze | Career seminar, Student career awareness session, Parent orientation, Psychometric test, Soft skills |
| Silver | Individual counselling, Digital skills |
| Gold | Application support, Scholarship assistance, IELTS coaching, SAT coaching, Foreign language classes, Digital portfolio creation |
| Platinum | Dedicated EduSphere counselor, Monthly campus visits, Internships, Visa support, Loan assistance, Alumni network, Parent help desk |

*(Tier contents from code; the Platinum and Bronze lists match the Entitlements page in the browser.)*

### Step 2 — Understand a refusal
Screens are not hidden by tier. You can start an action, and EduSphere refuses it if your tier does not allow it:

| Message | Meaning |
|---|---|
| This school's {Tier} partnership does not include {Service} (requires {Tier} or higher). | Your tier is too low for this service. |
| This school has no active partnership tier. | No tier has been set. |
| This school's partnership expired on {date}. | The tier's end date has passed. Nothing gated can be done. |

![Not included](../../screenshots/activities/11-schedule-tier-not-included.png)

![No tier](../../screenshots/activities/12-schedule-no-tier.png)

![Expired](../../screenshots/activities/13-schedule-tier-expired.png)

## Fields
None.

## Expected Result
You know why an action was refused and who can change it.

## Validation Messages
See Step 2.

## Common Errors
**Problem:** Work that worked last month is now refused.
**Cause:** The tier was lowered or has expired.
**Resolution:** Check your notifications and **Entitlements**. Contact your EduSphere Overseas Admin.

## Tips
- After a downgrade, work that was already started for a removed service can still be finished, but nothing new can be
  started ("Work already started for them can still be completed."). After expiry nothing can be finished *(from code)*.
- Two places show the tier directly: student scorecards ("Not in plan") and the Digital Portfolio internships section
  (Platinum only).
- Only EduSphere's Overseas Admin can change a school's tier.

## Related Features
- [View your school's partnership entitlements](ent-001-view-entitlements.md)
- [Student progress scorecards](../reports/rpt-005-student-scorecards.md)
- [Schedule an activity](../activities/act-001-schedule-an-activity.md)
