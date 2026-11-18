# Return a lead to the telecaller
> Doc ID: DOC-ITC-LEAD-013 · Verified on 2026-11-18 against `main` @ `6b61546c` · Roles: IT Counselor

## Purpose
Give a lead back to its telecaller when it is not ready for counseling, for example when the person wants to start much later.

## Who Can Use This Feature
- **IT Counselor**, on their own leads.

## Prerequisites
- The lead is in your **My leads** and has no student linked. If a student is linked, unlink them first ([Link or unlink](../conversion/conv-004-link-student.md)).

## How to Access
Lead page → **Return to telecaller**.

## Steps
### Step 1 — Give a reason
Select **Return to telecaller** and write the **Reason for returning**.
![Return to telecaller form](../../screenshots/leads/33-return-form.png)

### Step 2 — Return
Select **Return lead**. The message **Lead returned to the telecaller.** appears. The page now shows only **Student and milestones**, **Lead details** and **Activity**; you can no longer change the lead.
![Lead after it was returned](../../screenshots/leads/34-returned.png)

## Fields
| Field | Description | Required | Example |
|---|---|---|---|
| Reason for returning | Why the lead goes back (up to 500 characters; kept in the stage history) | Yes | Wants a weekend batch next quarter… |

## Expected Result
- The lead leaves your **My leads** and goes back to **Follow-up** with the telecaller, who can work it again.
- Its open follow-ups and appointments are cancelled and the next action is cleared (from code).
- The screenshot after returning still shows the old stage in the header until the page is reloaded.

## Validation Messages
| Message | When |
|---|---|
| Lead returned to the telecaller. | Success |
| Add a reason for returning the lead. | **Reason for returning** is empty (from code; not captured) |

## Tips
- To pass a lead to another counselor instead, ask the Telecaller Manager. See [Telecaller Manager changes the counselor](../../admin-manual/handoffs/ho-002-manager-change-counselor.md).

## Related Features
- [Telecaller hands a lead to an IT counselor](../../admin-manual/handoffs/ho-001-telecaller-handover.md)
