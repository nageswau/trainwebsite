# Agent CRM Demo — 45-Minute Script

> For client and prospect demos on **https://dev.edusphere.org.uk**. Run the
> [preparation checklist](01-prep-checklist.md) first. Steps come from the Agent CRM manuals, browser-verified on
> 2026-10-05 against `main` @ `6a9be770`.

## The story

*An education agency joins EduSphere, gets approved, builds its team, and takes a student from first enquiry to
enrollment. Along the way it collects the university deposit, runs the visa case, and earns and claims its
commission. EduSphere's Overseas Admin oversees the whole network.*

| Window | Signed in as | Used in parts |
|---|---|---|
| A | Overseas Admin | 1, 7 |
| B | Agency Master (*Demo Global Education*) | 2, 3, 4, 6, 7, 8 |
| C | Agency Staff 1 | 5 |
| D (incognito) | New agency registration | 1 |

## Run sheet

| Time | Part | What the audience sees |
|---|---|---|
| 0:00 | Opening | Why agencies need one workspace |
| 0:03 | 1. Onboarding | Agency registers; admin approves |
| 0:09 | 2. Agency at a glance | Master dashboard |
| 0:13 | 3. Team and permissions | Staff login, permissions, activity |
| 0:18 | 4. Students | Add, assign, counsel, shortlist |
| 0:24 | 5. A staff member's day | Notifications, application, documents, tasks |
| 0:30 | 6. Offer to enrollment | Document review, deposit, visa, enrollment |
| 0:37 | 7. Money | Commission claim and payout, deposit remittance |
| 0:41 | 8. Insight | Reports, CSV, staff performance |
| 0:44 | Close | Recap and questions |

---

## Opening (3 min)

**Say:** "Agencies today juggle spreadsheets, email and WhatsApp to track students, documents, deadlines and
commissions. EduSphere gives each agency its own secure workspace, connected to EduSphere's overseas team, so
everyone works from the same record."

Show the sign-in page `/overseas/login`.

## Part 1 — Agency onboarding (6 min)

| Step | Window | Action | Expected result |
|---|---|---|---|
| 1.1 | D | `/overseas/login` > **Create an account** | "Create Overseas account" form |
| 1.2 | D | Fill **Full name**, **Email** = `<live-master-email>`, **Account type** = **Education agent**, **Agency name** = *Live Demo Agency*, **Password** > **Create account** | "Access unavailable — Agent registration is pending approval" |
| 1.3 | A | **Agents** > **Agent Approvals** > **Pending** > **Approve** on *Live Demo Agency* | "Live Demo Agency approved." |
| 1.4 | D | Reload | The new agency's **Agent Dashboard** opens (empty) |
| 1.5 | A | **Agent network** > click *Demo Global Education* | Agency detail: summary, commission, deposits, Masters, read-only agency records |

**Say:** "Nobody gets into the agency workspace until EduSphere has approved them. The person who registers becomes
the agency's Master. From the network view, EduSphere sees every agency's students, applications and money in one
place. The records are read-only here, and every look at them is written to the audit log."

> Tell the audience: EduSphere does not email the agency when it is approved. Your team lets them know.

## Part 2 — The agency at a glance (4 min)

Window **B**: the **Agent Dashboard** of *Demo Global Education* ("Whole agency · Your code {code}").

Walk through the groups **Students**, **Pipeline**, **Documents** and **Commission**, then the breakdown by country
and university, and the staff table with its **Unassigned** row.

**Say:** "The owner sees the whole agency: how many students are at each stage, which documents are waiting, what
commission is claimable, and how each counsellor is doing. Money is shown per currency and never added across
currencies."

![Master dashboard](../../screenshots/dashboard/01-master-dashboard.png)

## Part 3 — Team and permissions (5 min)

| Step | Action | Expected result |
|---|---|---|
| 3.1 | **Team** > **Staff** card | Staff 1 and Staff 2, with their permissions |
| 3.2 | **Add staff** > Full name *Demo Counsellor*, Email `<spare-email>` > **Add staff** | "{code} created. A set-password link was emailed to {email}." with **Set-up pending** |
| 3.3 | Staff 1 row > **Permissions** | "What {name} can do": **Verify documents**, **View reports** |
| 3.4 | Staff 1 row > **Activity** | What Staff 1 did in the workspace |

**Say:** "The Master creates staff logins. Staff set their own password from a secure link that expires after 72
hours. By default staff see only the students assigned to them. The Master decides who may verify documents and who
may see reports. Up to three Masters can share ownership of an agency."

## Part 4 — Students (6 min)

| Step | Action | Expected result |
|---|---|---|
| 4.1 | **Students** | Student cards with **Active** / **No login** badges, **Assigned to** (or Unassigned), and search |
| 4.2 | Card *Priya Nair* > **Assign** > **Assign to** Staff 1 > **Save assignment** | "Priya Nair assigned to {code} · {name}." |
| 4.3 | Open a prepared student > **Counseling** | Counseling record: interests, budget, completed |
| 4.4 | **University shortlist** | Shortlisted universities; agency universities carry the **Agency** badge |
| 4.5 | **Journey** > **Show history** | Every step of the student's journey, with who did it and when |

**Say:** "Every student has one record: counseling notes, shortlist, documents, applications and a full history.
When the Master assigns a student, the counsellor is notified straight away and the student's open tasks move with
them."

## Part 5 — A staff member's day (6 min)

Switch to window **C** (Staff 1).

| Step | Action | Expected result |
|---|---|---|
| 5.1 | Dashboard | "Your assigned students" — only their own students; no Team or Commissions menu |
| 5.2 | **Notifications** | "Student assigned to you" for Priya Nair (from step 4.2) |
| 5.3 | **Applications** > **Create application**: Priya Nair, a catalogue university, Course, Intake > **Create application** | "Application created." (stage **Enquiry**) |
| 5.4 | **Documents** > **Upload document**: Priya Nair, type *Passport*, PDF file | "Document uploaded. It is waiting for review." |
| 5.5 | **Documents** > **Request a document**: Priya Nair, type, note > **Add request** | "Request added to Additional documents." |
| 5.6 | **Tasks & Follow-ups** > **Overdue** tab, then **New task** | Overdue follow-ups; a new task is added |

**Say:** "Counsellors see only what they need: their students, their applications, their follow-ups. Uploaded
documents go into a review queue, so nothing reaches a university unchecked."

## Part 6 — From offer to enrollment (7 min)

Back to window **B** (Master), on the hero application (*Aarav Mehta* and his catalogue university).

| Step | Action | Expected result |
|---|---|---|
| 6.1 | **Documents** > **Pending** > **Review** on Staff 2's upload > **Verified** > **Save decision** | "{document} for {student}: verified." |
| 6.2 | **Applications** > hero application > **View** | Application detail with Offer, Deposit, Visa and Enrollment sections |
| 6.3 | **Offer** | The recorded conditional offer and its conditions |
| 6.4 | **Deposit** | ₹50,000 deposit: **Paid** with **Download receipt** (or **Awaiting payment**, see the fallback below) |
| 6.5 | **Visa** > **Move visa stage** through Documentation > Interview prep > Tracking > Decision | Stage moves at each step |
| 6.6 | **Record decision** > **Approved** > **Yes, record decision** | "Visa decision recorded." |
| 6.7 | **Enrollment** > **Enroll student** > date > **Confirm enrollment** > **Yes, confirm enrollment** | "Enrollment confirmed." Stage **Enrolled**; a commission is estimated |

**Say:** "Applications only move forward, so the history can be trusted. The visa case cannot leave the checklist
until every required document is uploaded and verified. Only a Master can confirm enrollment, and confirming it
automatically starts the commission."

**Deposit fallback:** if online payment is not available on dev, show the deposit as **Awaiting payment** with the
**Pay deposit** button, and explain that payment runs through Razorpay. A paid deposit becomes read-only and gets a
receipt.

## Part 7 — Money: commission and deposits (4 min)

| Step | Window | Action | Expected result |
|---|---|---|---|
| 7.1 | B | **Commissions** | Rows with status; application F is **eligible** (amount set in prep) |
| 7.2 | B | Paste application F's **Reference** UUID into "Eligible commission reference" > **Claim commission** | "Commission claimed." and a claim reference `CLM-…` |
| 7.3 | A | **Commissions** > **Approve commission payout** > paste the same reference | "Payout approved -- commission marked paid." |
| 7.4 | A | **Agent deposits** > **Paid** | Paid deposits with **Record remittance** / **Record refund**. If no deposit is Paid (Razorpay unavailable), describe these actions instead |

**Say:** "Commission is created when a student enrolls. EduSphere sets the amount, the agency claims it, and
EduSphere approves the payout. Deposits that agencies collect are tracked through to remittance to the university."

> **Only claim the *eligible* row from the prep.** Do not claim the commission created in step 6.7. It is still
> *estimated* (amount 0), and claiming it locks the amount at 0 (open product finding P1).

## Part 8 — Insight (3 min)

| Step | Action | Expected result |
|---|---|---|
| 8.1 | **Reports** > **Applications** > **Apply** | "{N} rows · As of {time}" |
| 8.2 | **Download CSV** | A file such as `agency-applications-all-to-all.csv` downloads |
| 8.3 | **Reports** > **Commission** | Totals by status, university, country, intake |
| 8.4 | **Staff Performance** | Funnel from students to enrolled, and a per-staff table |

**Say:** "Owners can see where students drop out of the funnel and which counsellor converts best, and export any
report for their own analysis."

## Close (1–2 min)

**Recap:** one workspace per agency · EduSphere approval and oversight · roles and permissions · the student journey
from enquiry to enrollment · documents, deposit and visa under control · commission from enrollment to payout ·
reports and staff performance.

Invite questions. For a detailed check of every feature, hand over the [UAT checklist](03-uat-checklist.md).

---

## Do not show during the demo

These are open product findings or behaviour that has not been verified in the browser. See
`docs/documentation-review-report.md`.

| Avoid | Why |
|---|---|
| Claiming an **estimated** commission | It locks the amount at 0 (P1) |
| Agency screens as **Super Admin** | Agents/Commissions show "Workspace not found"; other screens are read-only (P2) |
| Typing real client or student email addresses | Dev may send real email (P3) |
| Commissions table raw words (`eligible`, `payout_pending`) | Present them as statuses; a UI polish item (P4) |
| Rejecting an agency and showing its message | It shows the same "pending approval" text (P5) |
| Refunding more than the paid amount | Refused only after confirmation (P6) |
| Task **Student** picker on screen share | Shows full student emails (P7) |
| Editing a task, editing an agency university, the 3-Master limit, the enrollment-date warning | Confirmed in code only, not rehearsed in the browser |
| Daily 08:00 reminders | Cannot be triggered live |

## If something goes wrong

| Problem | Recovery |
|---|---|
| New staff did not get the welcome email | Show the **Set-up pending** badge and move on; mention **Reset** / **Re-send link** |
| "Cannot advance past the checklist stage -- not yet verified: …" | A ticked visa document is not verified. Verify it under **Documents** and retry |
| "Access unavailable — Agent registration is pending approval" after approval | Reload the page |
| "Commission cannot be claimed in its current status" | It is already claimed or paid; check the claim reference column |
| "Commission not found" | Wrong UUID pasted; copy the eligible row's UUID from your note. Never paste the estimated row from step 6.7 |
| "Email already exists" at registration | Use a fresh `<live-master-email>` |
| Any page error | Reload; if it persists, switch to the matching screenshot in `docs/screenshots/` |
