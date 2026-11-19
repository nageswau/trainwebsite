# Change a lead's stage
> Doc ID: DOC-ITC-LEAD-005 · Verified on 2026-11-18 against `main` @ `6b61546c` · Roles: IT Counselor

## Purpose
Move the lead through the pipeline, for example to **Qualified** so it can be converted, or close it.

## Who Can Use This Feature
- **IT Counselor**, on their own leads.

## Prerequisites
- A next action is set when you move to an open stage. See [Set the next action](lead-004-next-action.md).

## How to Access
Lead page → **Stage** → **Change stage**.

## Steps
### Step 1 — Choose the new stage
Select **Change stage** and choose a stage. The counselor can choose **Qualified**, **Follow-up**, **Counselling Scheduled**, **Counselling Completed**, **Not Interested**, **Not Eligible** or **Lost**.

### Step 2 — Add a reason
The reason box depends on the stage:
- Most stages: **Reason (optional)**.
- **Not Eligible**: **Reason (required)**.
- **Not Interested** and **Lost**: pick a **Lost reason (required)** from the list the admin set up, and optionally fill **Lost to**.
![Change stage form with Qualified chosen](../../screenshots/leads/09-change-stage-form.png)

### Step 3 — Save
Select **Save**. The message **Stage updated.** appears and the header shows the new stage.
![Lead now Qualified](../../screenshots/leads/10-stage-qualified.png)

## Fields
| Field | Description | Required | Example |
|---|---|---|---|
| New stage | The stage to move to | Yes | Qualified |
| Reason | Why | Required for Not Eligible; optional otherwise | Eligible graduate, wants an evening batch. |
| Lost reason (required) | Why the lead was lost | Yes, for Not Interested and Lost | — |
| Lost to | Who the lead went to | No | — |

## Expected Result
- The lead shows the new stage everywhere, including **My leads**.
- From **Qualified** onwards, **Student account** offers **Convert to IT student**.
- Closing the lead (**Not Interested**, **Not Eligible**, **Lost**) cancels its open follow-ups and appointments (from code).

## Validation Messages
| Message | When |
|---|---|
| Stage updated. | Success |
| Add a reason for this stage. | **Not Eligible** without a reason (from code; not captured) |
| Choose why the lead was lost. | **Not Interested** or **Lost** without a lost reason (from code; not captured) |
| No lost reasons are set up yet… | The admin has not set up lost reasons (from code; not captured) |

## Tips
- **Converted** is set by the system when the lead's student enrols; you do not choose it.
- Stage names come from the IT Admin's **Status Labels**.

## Related Features
- [Convert a lead to a new IT student](../conversion/conv-001-convert-new-student.md)
- [Status labels](../../admin-manual/admin/adm-013-status-labels.md)
