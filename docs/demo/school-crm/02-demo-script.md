# School CRM Demo — 45-Minute Script

> For client and prospect demos on **https://dev.edusphere.org.uk**. Run the
> [preparation checklist](01-prep-checklist.md) first. Steps come from the School CRM manuals, browser-verified on
> 2026-10-06 against `main` @ `ce1f07c2`.

## The story

*A school becomes an EduSphere partner. Its Coordinator runs the roster, the team and the activities. EduSphere's
specialists (academic, psychometric and career) deliver services to students, within what the school's partnership
tier includes. Teachers, parents and the principal each see exactly what they need. EduSphere's Overseas Admin
oversees every partner school.*

Hero student: **Aarav Kapoor**, Grade 11, *Demo Platinum Academy*.

## Run sheet

| Time | Part | Signed in as | What the audience sees |
|---|---|---|---|
| 0:00 | Opening | — | Why schools partner with EduSphere |
| 0:02 | 1. Partner onboarding | Overseas Admin | New school, tier, specialist staff |
| 0:07 | 2. The school at a glance | Coordinator | Dashboard, roster, student profile |
| 0:12 | 3. Team, activities, partnership | Coordinator | Invites, activities, attendance, feedback, entitlements |
| 0:17 | 4. The teacher's day | Teacher | Daily attendance, digital portfolio |
| 0:20 | 5. Academic results | Academic Team 1 and 2 | Draft → verified → published; IELTS; tier refusal |
| 0:25 | 6. Psychometric | Psychometric Team | Report attached, results recorded |
| 0:28 | 7. Career guidance | Career Counselor | Records, preferences, skills batch, funding |
| 0:32 | 8. The parent's view | Parent | Children, progress, PDF report |
| 0:35 | 9. The principal's view | Principal | Reports, at-risk students, 360° view |
| 0:39 | 10. Network oversight | Overseas Admin | Transfers, analytics, feedback, overseas application |
| 0:43 | Close | — | Recap and questions |

---

## Opening (2 min)

**Say:** "Schools want to offer career guidance, assessments, skills and overseas pathways, but tracking all of it
for hundreds of students is hard. EduSphere gives each partner school one workspace. The school, EduSphere's
specialists and parents all work from the same student record, and the partnership tier decides which services the
school receives."

## Part 1 — Partner onboarding (5 min) · Overseas Admin

| Step | Action | Expected result |
|---|---|---|
| 1.1 | **Schools** | Partner Schools list with search and filters |
| 1.2 | **Create school**: *Live Demo School*, City, Board, **Partnership tier** = **Silver**, Coordinator name and `<live-coordinator-email>` > **Create school + seed Coordinator** | "School created. School code {code}. Coordinator account ready for {email}. A set-password link was emailed and is valid for 72 hours." |
| 1.3 | **Edit school profile** > its School ID > **Look up** > tier **Gold** > **Save changes** | "School profile updated. Partnership is now Gold; newly available: …" |
| 1.4 | **School Staff** | Academic, Career and Psychometric staff, with the number of schools each serves |

**Say:** "Onboarding a school takes a minute: the Coordinator gets a secure link to set their password. Tiers are
cumulative. Bronze covers seminars, psychometric tests and soft skills; Silver adds counselling and digital skills;
Gold adds application support, scholarship assistance, IELTS/SAT, languages and digital portfolios; Platinum adds a dedicated counsellor,
campus visits, internships, visa and loan support. When a tier changes, the Coordinator and Principal are told what
is newly available."

## Part 2 — The school at a glance (5 min) · Coordinator

| Step | Action | Expected result |
|---|---|---|
| 2.1 | Dashboard | **School at a glance**: 20 figures in Students, Career & assessment, Skills & languages, Global pathway |
| 2.2 | **Students** | The roster |
| 2.3 | **Add one student**: name, **Grade/Class** `Grade 11`, **Grade level** 11, **Assigned Teacher** > **Add student** | "{Name} added to the roster." |
| 2.4 | Mention **Go to bulk upload** (dashboard) | Roster upload by CSV, row-by-row result |
| 2.5 | *Aarav Kapoor* > **Profile & timeline** | Photo, details and the journey timeline |

**Say:** "The Coordinator keeps the roster. Students can be added one by one or as a whole class by CSV. Each
student has a timeline of everything that happened to them."

![Coordinator dashboard](../../school-crm/screenshots/dashboards/01-coordinator-kpis.png)

## Part 3 — Team, activities and the partnership (5 min) · Coordinator

| Step | Action | Expected result |
|---|---|---|
| 3.1 | **Team** | Team members and **Pending invites** with their expiry dates |
| 3.2 | **Activities** > **Schedule an activity**: title, date & time, category *Parent orientation* > **Schedule activity** | "{Title} scheduled." Linked parents are notified |
| 3.3 | The unmarked past activity > **Mark attendance** > untick one student > **Save attendance** | "Attendance recorded for {n} student(s)." |
| 3.4 | **Feedback** > **Awaiting feedback** > **Give feedback** > ratings and text > **Submit feedback** | "Feedback saved for {title}." |
| 3.5 | **Entitlements** | "Plan: Platinum Partner — valid until {date}" (date set in prep step 1.3), with included and used services |

**Say:** "The Coordinator invites the principal, teachers and parents; invitations are valid for seven days. After
each EduSphere activity the school rates it, and EduSphere sees that feedback across all schools. Entitlements show
exactly what the partnership includes and how much has been used."

## Part 4 — The teacher's day (3 min) · Teacher

| Step | Action | Expected result |
|---|---|---|
| 4.1 | Dashboard | **Your students**: only the students assigned to this teacher |
| 4.2 | **Attendance** (opens on today) > mark one student **Late** > **Save attendance** | "Attendance saved for {n} students on {date}." |
| 4.3 | Dashboard > *Aarav Kapoor* > **View** > **Digital Portfolio** > **Add skill** > title > **Save** | "Skill added." |

**Say:** "Teachers see only their own class. The digital portfolio collects achievements, certificates, internships
and the personal statement that students later use for university applications."

## Part 5 — Academic results (5 min) · Academic Team

| Step | Signed in as | Action | Expected result |
|---|---|---|---|
| 5.1 | Academic Team 1 | **Results**: Aarav's Draft row | Shows "Ask another Academic Team member to verify" |
| 5.2 | Academic Team 2 | **Verify** on Aarav's Draft | "Result verified." |
| 5.3 | Academic Team 2 | **Publish** | "Result published." Parents can now see it |
| 5.4 | Academic Team 1 | **Test preparation**: a Platinum student **without** IELTS from the prep, **IELTS** > **Start preparation** | "IELTS preparation started." |
| 5.5 | Academic Team 1 | **Test preparation**: a *Demo Bronze School* student, **IELTS** > **Start preparation** | Refused with a tier message: "…does not include IELTS coaching (requires Gold or higher)." This message is confirmed in code only; **rehearse it on dev**. Fallback: show `docs/school-crm/screenshots/activities/11-schedule-tier-not-included.png` |

**Say:** "Results follow a four-eyes process: one person enters, another verifies, and only published results
reach parents. Services are enforced by tier, so a Bronze school cannot receive IELTS coaching by mistake."

## Part 6 — Psychometric assessment (3 min) · Psychometric Team

| Step | Action | Expected result |
|---|---|---|
| 6.1 | **Assessments**: Aarav's *assigned* assessment > **Attach report** > `https://…` > **Attach** | "Report attached." Status completed |
| 6.2 | **Record results**: strengths, interest areas, career recommendations > **Save results** | "Results saved." |

**Say:** "Psychometric findings feed directly into career guidance. The report then appears in the parent's view of the child."

## Part 7 — Career guidance (4 min) · Career Counselor

| Step | Action | Expected result |
|---|---|---|
| 7.1 | Dashboard > **Add a record**: Aarav, *Guidance session*, **Completed**, notes > **Save record** | "Record saved." |
| 7.2 | **Career preferences** (Aarav) | Interests, preferred countries and courses |
| 7.3 | **Skills** > the prepared batch | Enrolled students, sessions, attendance, assessments |
| 7.4 | **Funding** > the prepared case > **Edit** > next stage > **Save changes** | "Case saved."; the stage moves forward one step (for example "Stage 3 of 6 · Documents") |

**Say:** "Counsellors record every session and follow-up, run soft-skills and digital-skills batches with attendance
and scores, and guide families through scholarships and education loans stage by stage."

## Part 8 — The parent's view (3 min) · Parent

| Step | Action | Expected result |
|---|---|---|
| 8.1 | Dashboard **My children** | Aarav's card with status tiles; **Upcoming sessions** in IST |
| 8.2 | **View full profile & progress** | Career guidance, psychometric, published results, activities, skills, funding, timeline |
| 8.3 | **Download progress report (PDF)** | "Report downloaded." |

**Say:** "Parents see their child's progress in one place: the result just published, the psychometric report and
the counselling sessions, and they can download a progress report before a parent meeting."

## Part 9 — The principal's view (4 min) · Principal

| Step | Action | Expected result |
|---|---|---|
| 9.1 | Dashboard | The same 20 figures and the student list (read-only portal) |
| 9.2 | **Reports** > **Student development** | At-risk students and top performers, with adjustable thresholds |
| 9.3 | **Reports** > **Download school report (PDF)** | "Report downloaded." |
| 9.4 | **Global Education** | Students on the overseas pathway |
| 9.5 | Dashboard > Aarav > **Timeline** > **Open 360° view** | Every service for one student, in tabs |

**Say:** "The principal sees the school's progress and who needs help, without being able to change anything, and
can take a PDF report to the board."

## Part 10 — Network oversight (4 min) · Overseas Admin

| Step | Action | Expected result |
|---|---|---|
| 10.1 | **School Transfers** > the prepared request > **Approve** > **Confirm approval** | "Moved {student} to {school}. …" |
| 10.2 | **School Analytics** | All partner schools: KPIs, service use per school, **Renewal due** flag on *Demo Bronze School* |
| 10.3 | **Activity Feedback** | Ratings from every school |
| 10.4 | **School Applications** | The overseas application started for a Platinum student |

**Say:** "Transfers between partner schools are decided centrally, so records follow the student. EduSphere sees
service use and renewal dates across the whole network, and for Gold and Platinum schools it starts overseas
university applications for school students from the **School Applications** page."

## Close (2 min)

**Recap:** onboarding in minutes · tier-based services enforced automatically · roster, team and activities run by
the school · specialists working on the same student record · four-eyes results · transparent views for teachers,
parents and principals · network-wide oversight for EduSphere.

Hand over the [UAT checklist](03-uat-checklist.md) for the detailed check.

---

## Do not show during the demo

These are open product findings or open owner items. See `docs/school-crm/documentation-review-report.md`.

| Avoid | Why |
|---|---|
| **Forgot password** | No email is sent on plain SMTP (P1, U2) |
| Opening a parent notification to "clear" it | The unread count never goes down (P3) |
| Reading out the "Upcoming session" notification text | Shows UTC time, not IST (P4); use the **Upcoming sessions** card |
| Marks above the maximum | Accepted on the single result form (P5) |
| Narrow window or phone view | No sign-out there (P6) |
| School screens as **Super Admin** | "Workspace not found" (P7) |
| Editing a specialist's school portfolio; opening an academic year | No screen for either (P8) |
| An **expired** school's Entitlements page | No warning shown (P9) |
| Very long names or subjects | Only "Something went wrong." (P10) |
| Comparing report grade chart with dashboard tiles | Can differ if Grade/Class wording varies (P11) |
| Re-opening an attendance card that was already saved | Reopens with everyone ticked (P12) |
| Career goal or closing a batch | Needs a reload to show (P13) |
| CSV template's "Jane Doe" row | Gets imported; students cannot be deleted (P14) |
| `/school/coordinator/students/new` | Shows "[object Object]" (P16) |
| Raw codes such as `guidance_session`, `draft` | Present them as statuses; a UI polish item (P16) |
| Moving a school application past `enquiry` | Not confirmed (U15) |
| WhatsApp / SMS notifications | Not verified (U10) |
| **Promotion** | Only if the team opened a new academic year (prep 0.5); otherwise every row says "Already in {year}" |

## If something goes wrong

| Problem | Recovery |
|---|---|
| "No students assigned to you yet." (Teacher) | The student's **Assigned Teacher** is not set; show another teacher view or skip |
| "No students in your portfolio yet." (specialist) | The account was created without schools; use another specialist account |
| A tier message where you did not expect one | Check **Entitlements**; use a Platinum-school student |
| No **Verify** button for a result | You are signed in as its uploader; switch to Academic Team 2 |
| Amber "not delivered" after creating the school | Mention **Users** > **Re-send link**; carry on |
| A section says it couldn't load | Reload the page |
