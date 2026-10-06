# School CRM Demo — Preparation Checklist

> Environment: **https://dev.edusphere.org.uk**. Steps come from the School CRM manuals under `docs/school-crm/`,
> browser-verified on 2026-10-06 against `main` @ `ce1f07c2`. Check that dev runs that build or a later one.

Do this **the day before** the demo. It takes about 90 minutes. School CRM has nine roles, so the prep matters more
than for the Agent CRM: every role you show needs an account whose password is already set.

## Before you start

| # | Check | How | Done |
|---|---|---|---|
| 0.1 | Dev is up | `https://dev.edusphere.org.uk/overseas/login` loads. Every school role signs in here. | ☐ |
| 0.2 | Build on dev | Ask the team which commit dev runs; older than `ce1f07c2` may differ. `NEEDS_CONFIRMATION` | ☐ |
| 0.3 | Email delivery | Step 1 sends a welcome email to the Coordinator. If the success message turns amber ("not delivered"), email is not configured on dev. Then use **Users** > **Manage users** > **Re-send link** after the team fixes email. Invitations in step 4 have **no** on-screen link, so working email is required. `NEEDS_CONFIRMATION` | ☐ |
| 0.4 | Mailboxes | Use mailboxes you control for every account. Never use a real student's or parent's address. | ☐ |
| 0.5 | Academic year (only for Promotion) | Promotion works only after a new academic year is opened, and there is no screen for that. Ask the team to open the new academic year on dev, or leave Promotion out. `NEEDS_CONFIRMATION` | ☐ |
| 0.6 | Browser | One Chrome profile per role (9 profiles), each already signed in, so you switch windows instead of signing in live. Window at least 1440 px wide. On narrow windows there is no sign-out (P6). | ☐ |

## Accounts to have ready

Keep passwords in your password manager, not in this document. Passwords need 10–128 characters.

| Profile | Role | Account (fill in) | Created in | Link valid |
|---|---|---|---|---|
| 1 | Overseas Admin | `<overseas-admin-email>` | Existing on dev | — |
| 2 | School Coordinator — *Demo Platinum Academy* | `<coordinator-email>` | Step 1 | 72 h |
| 3 | Principal | `<principal-email>` | Step 4 | 7 days |
| 4 | Teacher | `<teacher-email>` | Step 4 | 7 days |
| 5 | Parent | `<parent-email>` | Step 4 | 7 days |
| 6 | Academic Team 1 | `<academic1-email>` | Step 2 | 72 h |
| 7 | Academic Team 2 (verifies Academic Team 1's results) | `<academic2-email>` | Step 2 | 72 h |
| 8 | Career Counselor | `<counselor-email>` | Step 2 | 72 h |
| 9 | Psychometric Team | `<psychometric-email>` | Step 2 | 72 h |
| — | Coordinator — *Live Demo School* (live) | `<live-coordinator-email>` (fresh, never used) | During the demo | 72 h |
| — | Coordinator — *Demo Bronze School* | `<bronze-coordinator-email>` | Step 1 | 72 h |

> Links work only once, and a re-sent link cancels the earlier one. Set every password as soon as the email arrives.

## Step 1 — Schools (10 min, Overseas Admin)

1. **Schools** > **Create school**. Fill **School name** = *Demo Platinum Academy*, **City**, **Board**, **Grades
   available**, **Partnership tier** = **Platinum**, **Coordinator full name**, **Coordinator email**. Click **Create
   school + seed Coordinator**.
   Expect: "School created. School code {code}. Coordinator account ready for {email}. A set-password link was
   emailed and is valid for 72 hours."
2. Repeat for *Demo Bronze School* with tier **Bronze**. It is used for the transfer and the tier-refusal moments.
3. The create form has no **Valid until** date. For each school: **Edit school profile** > its School ID > **Look up**
   > **Valid until** > **Save changes**. Give the Platinum school a date a year ahead, and the Bronze school a date
   **within the next 60 days**, so School Analytics shows a **Renewal due** flag.
4. Note both 8-character **School IDs** from the Partner Schools list. Rows are not clickable, so you need the ID to
   edit a school.
5. **Do not** create the live-demo school now. You create *Live Demo School* during the demo.

> School name, City and State cannot be changed after creation. Check the spelling before saving.

## Step 2 — Specialist staff (10 min, Overseas Admin)

**School Staff** > **Create Academic Team / Career Counselor / Psychometric Team account**. Create four accounts:
Academic Team 1, Academic Team 2, Career Counselor and Psychometric Team. For each, select **both** demo schools in
**School portfolio** before clicking **Create account**.

> A school portfolio cannot be changed after the account is created (P8). An empty portfolio means the specialist
> sees no students.

Set each password from its welcome email.

## Step 3 — Coordinator sets up (5 min)

1. In the Coordinator's mailbox, open "Welcome to EduSphere -- set your password", set the password and sign in.
2. Do the same for the Bronze school's Coordinator.

## Step 4 — Team (10 min, Platinum Coordinator)

1. **Team** > **Invite a team member**: invite the **Principal**, the **Teacher** and the **Parent**. Each shows
   "Invite sent to {email}. It's valid for 7 days."
2. Accept each invitation from its email (**Accept and set up login**).
3. Invite one more Teacher and **do not** accept it. **Pending invites** then shows an entry during the demo.

## Step 5 — Students (15 min, Platinum Coordinator)

1. Add 3 students one by one (**Students** > **Add one student**). Fill **Grade/Class** with consistent wording (for
   example `Grade 11`), **Grade level**, **Assigned Teacher** = the Teacher from step 4, and for the hero student
   **Parent's email** = `<parent-email>`.
   **Hero student:** *Aarav Kapoor*, Grade 11, linked to the Parent.
2. Add 10–15 more students with **Go to bulk upload** (dashboard) > **Download template (.csv)**. **Delete the "Jane
   Doe" example row** before uploading (P14), because students cannot be deleted. Lists in the CSV use `;`.
3. Upload a photo for the hero student (**Profile & timeline** > **Upload a photo**).
4. If the parent was not linked by email, use **Link parent** on the hero student's row.
5. As the Bronze Coordinator, add 2 students to *Demo Bronze School*.

## Step 6 — Service data (25 min)

Fill the specialist views, so dashboards, reports and the Parent view have content:

| Role | Do | Why |
|---|---|---|
| Coordinator | Schedule 3 activities: one in the **future**; one with a **past** date and category *Career seminar* (mark its attendance); and one more with a **past** date and category *Student career awareness session*, **left unmarked** | Feedback needs a past activity with a category; the unmarked one is for the live attendance step |
| Teacher | Take daily **Attendance** for today (and again on the demo day, before the demo). Past days list only students enrolled by then | Parent attendance tile, reports |
| Academic Team 1 | Upload 6–8 results as **Draft** for different students. Leave **one** Draft for the hero student unverified | Live verify/publish |
| Academic Team 2 | Verify and publish all other results; include 1–2 low marks (below 40 %) and 1–2 high marks (85 % +) | At-risk and top-performer lists |
| Academic Team 1 | Start **IELTS** preparation for 2 students; start one **foreign language** class | Dashboard figures |
| Psychometric Team | Assign assessments to 3 students; attach a report (a valid `https://` link) and record results for 2. Leave the hero student's assessment **assigned** | Live attach |
| Career Counselor | 3 guidance records; career preferences for the hero student; one **Skills** batch with enrolled students and one session; one **Funding** case (**Add a case**, then **Edit** > Stage **Counselling** > **Save changes**) | Live updates |
| Coordinator | **Request a transfer** for one filler student to *Demo Bronze School* | Live approval by the Overseas Admin |
| Overseas Admin | **School Applications** > start one application for a Platinum student | School Analytics and Global Education figures |

> Results: check the numbers before saving. A Draft cannot be edited from the screen, and marks above the maximum are
> accepted (P5). The psychometric report link cannot be changed after attaching (P17).

## Step 7 — Final check (5 min)

- [ ] Coordinator dashboard shows non-zero figures.
- [ ] Principal **Reports** > **Student development** shows at-risk and top-performer students.
- [ ] Parent dashboard shows the hero student with tiles; **Download progress report (PDF)** works.
- [ ] The hero student has one Draft result (Academic Team 1) and one *assigned* assessment.
- [ ] One pending transfer request is visible in **School Transfers** (Overseas Admin).
- [ ] Every profile is signed in.
- [ ] `<live-coordinator-email>` for the live school has never been used on dev.

## After the demo

Data on dev stays, and students cannot be deleted from the screens. For repeat demos, keep the prepared schools and
create a new *Live Demo School* each time, or ask the team to restore a database snapshot taken after this checklist.
`NEEDS_CONFIRMATION`: whether dev has a snapshot/restore procedure.

Next: [Demo script](02-demo-script.md) · [UAT checklist](03-uat-checklist.md)
