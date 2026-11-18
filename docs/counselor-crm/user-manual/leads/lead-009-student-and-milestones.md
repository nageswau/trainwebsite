# Student and milestones panel
> Doc ID: DOC-CNS-LEAD-009 · Verified on 2026-10-30 against `main` @ `045d8c40` · Roles: Counselor

## Purpose
See, from the lead, which student account it belongs to and how far that student has got.

## Who Can Use This Feature
The counselor who owns the lead. The panel is read only.

## Prerequisites
None. Before a student is linked it says "No student account is linked yet."

## How to Access
Lead page → **Student and milestones**.

## Steps
### Step 1 — Read the panel
After [conversion](../conversion/conv-001-convert-to-student.md) or [linking](../conversion/conv-002-link-student.md), the panel shows **Linked student: {name} ({email})**. Until the student has an application or enrolment it says **No enrolment or application yet.**
![Student and milestones after conversion](../../screenshots/leads/23-student-and-milestones.png)

### Step 2 — Follow the milestones
As the student's applications move on, each milestone is listed with its kind, label, status, reference and time. When the student enrols, the panel shows a **Converted** badge and the lead's stage becomes **Converted** automatically.

For example: "Overseas application · Docs University — Offer · 30 Oct 2026".
![Milestones with an application](../../screenshots/leads/24-milestones-with-application.png)

When the linked student's enrolment is confirmed, EduSphere marks the lead **Converted** (within about 15 minutes). The panel shows the **Converted** badge and "Overseas application · {university} — Enrolled".
![Converted lead](../../screenshots/leads/25-milestones-converted.png)
![The converted lead page](../../screenshots/leads/26-converted-lead.png)

Note: a converted lead still shows its open follow-ups and the "No next action set" prompt. Mark old follow-ups done or cancel them yourself.

## Expected Result
You can tell from the lead whether the student has applied or enrolled.

## Related Features
- [Convert a lead to a new student](../conversion/conv-001-convert-to-student.md)
- [Link / unlink an existing student](../conversion/conv-002-link-student.md)
