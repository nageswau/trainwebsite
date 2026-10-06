# Agent CRM Demo — Preparation Checklist

> Environment: **https://dev.edusphere.org.uk**. Steps come from the Agent CRM user and admin manuals, which were
> browser-verified on 2026-10-05 against `main` @ `6a9be770`. Check that dev runs that build or a later one (see
> [Before you start](#before-you-start)).

Do this **the day before** the demo. It takes about 60–75 minutes. You end up with one agency that already has data, so
the dashboards, reports and commission screens have something to show. During the live demo you then register a
**second** agency to show onboarding from the start.

## Before you start

| # | Check | How | Done |
|---|---|---|---|
| 0.1 | Dev is up | Open `https://dev.edusphere.org.uk/overseas/login` and `/admin/login`; both pages load. | ☐ |
| 0.2 | Build on dev | Ask the team which commit dev runs. If it is older than `6a9be770`, the screens may differ from this script. `NEEDS_CONFIRMATION` | ☐ |
| 0.3 | Email delivery on dev | Create one test staff login (step 3.1) and check that the "Welcome to EduSphere -- set your password" email arrives. If it does not, use the fallback in step 3.3. `NEEDS_CONFIRMATION` | ☐ |
| 0.4 | Online deposit payment | In step 5.4 click **Pay deposit** once. If the page says "Online payment is unavailable right now", Razorpay is not configured on dev. Then show the deposit only as *Awaiting payment* in the demo (see the script's fallback). `NEEDS_CONFIRMATION` | ☐ |
| 0.5 | "Demo accounts" card | The sign-in page of a development build can show a **Demo accounts** card. Decide whether the client may see it; if not, ask the team to turn it off on dev. | ☐ |
| 0.6 | Mailboxes | Use mailboxes you control for every account (for example `you+master@yourdomain`). Never type a client's or a real student's address: dev may send real email. | ☐ |
| 0.7 | Browser | Use Chrome with **three profiles** (or one normal and two incognito windows from different profiles), so Overseas Admin, Master and Staff can stay signed in side by side. Zoom 100 %, window at least 1440 px wide. | ☐ |

## Accounts to have ready

Write the passwords in your password manager, **not** in this document. Passwords need 10–128 characters.

| Role | Sign-in page | Account (fill in) | Created in |
|---|---|---|---|
| Overseas Admin | `/overseas/login` | `<overseas-admin-email>` | Existing account on dev (ask the team) |
| Agency Master — prepared agency | `/overseas/login` | `<demo-master-email>` | Step 1 |
| Agency Staff 1 (Verify documents + View reports) | `/overseas/login` | `<demo-staff1-email>` | Step 3 |
| Agency Staff 2 (no extra permissions) | `/overseas/login` | `<demo-staff2-email>` | Step 3 |
| Agency Master — **live** registration | `/overseas/login` > **Create an account** | `<live-master-email>` (fresh, never used) | During the demo |
| Spare staff login (created live) | — | `<spare-email>` (fresh, never used) | During the demo |
| Super Admin (optional, not shown) | `/admin/login` | `<super-admin-email>` | Existing |

> If dev was loaded with the standard seed, built-in accounts such as `overseasadmin@edusphere.local` and
> `agent@edusphere.local` exist. Prefer the fresh **Demo** accounts below, because the seed data is test data and can
> look odd in front of a client.

## Step 1 — Register and approve the prepared agency (10 min)

1. Open `/overseas/login` and click **Create an account**.
2. Fill in **Full name**, **Email** (`<demo-master-email>`), **Account type** = **Education agent**, **Agency name (optional)**
   = `Demo Global Education`, and **Password**. Click **Create account**.
3. You see "Access unavailable — Agent registration is pending approval". Leave this tab open.
4. In the Overseas Admin profile, go to **Agents** > **Agent Approvals** > **Pending** and click **Approve** for
   *Demo Global Education*. You see "Demo Global Education approved."
5. Reload the Master's tab. The **Agent Dashboard** opens. Note the agency code shown as "Your code {code}".

## Step 2 — Agency universities (5 min)

As the Master, open **Universities** > **Add university** and add two universities (**Name**, **Country**, **City**,
**Entry requirements**), for example *Northbridge University, United Kingdom* and *Harbour Point College, Canada*.
Each save shows "{name} added." Catalogue universities are already there and do not need adding.

> Agency universities are used **only on shortlists**. An application needs a **catalogue** university, which cannot
> be changed later. Before step 5, open **Applications** > **Create application** and note two or three catalogue
> universities offered in the **University** list on dev.

## Step 3 — Staff logins and permissions (10 min)

1. **Team** > **Staff** card > **Add staff**: enter **Full name** and **Email** for Staff 1, then click **Add staff**.
   You see "{code} created. A set-password link was emailed to {email}." The code is the agency prefix plus
   `-S001` (for example `DEM-S001`). Repeat for Staff 2.
2. In each staff mailbox, open "Welcome to EduSphere -- set your password", click **Set your password** (the link is
   valid for 72 hours) and set a password.
3. *Fallback if the email did not arrive:* click **Reset** on the staff row, or have the Overseas Admin send a new
   link from **Users** > **Manage users** > **Re-send link**.
4. On Staff 1's row click **Permissions**, tick **Verify documents** and **View reports**, then click **Save**.
   Leave Staff 2 as "Student journey only".

## Step 4 — Students (15 min)

As the Master, open **Students** > **Add student** and create **8–10 students**. Only **Full name** is required, but
add a **Preferred country** and a phone number so the cards look realistic. Use made-up names.

- Assign 5 students to Staff 1 and 2 to Staff 2 (**Assign** > **Assign to** > **Save assignment**), and leave 1–2
  **Unassigned**. The dashboard's staff table and Unassigned row then have content.
- Include **Aarav Mehta** (the hero student, assigned to Staff 1).
- For 2 students, including Aarav, record counseling (**View** > **Counseling** > **Record counseling**, fill career
  interest and budget, tick "Counseling completed" > **Save counseling**) and add 2–3 universities to the shortlist
  (**University shortlist** > **Add university to shortlist**). Put *Northbridge University* (an agency university)
  on Aarav's shortlist, so the **Agency** badge shows.
- **Keep one student, for example `Priya Nair`, unassigned and untouched.** You assign her live.

## Step 5 — Applications at different stages (20 min)

Create 5–6 applications (**Applications** > **Create application**: **Linked student**, **University**, **Course**,
**Intake**). Then move them so every filter tab has something in it:

| Student | Take it to | How |
|---|---|---|
| A | Enquiry (Draft) | Create only |
| B | Submitted | Set **Submitted on** when you create it |
| C | Offer | Upload an **Offer letter** document for this application, then **Offer** > **Record offer** |
| D — **the hero application** | Offer + deposit + visa at **Checklist** | See 5.1–5.5 below |
| E | Withdrawn | **Withdraw application** > **Yes, withdraw** |
| F | Enrolled | Record an offer, then **Enrollment** > **Enroll student** > **Confirm enrollment** > **Yes, confirm enrollment**. This creates an *estimated* commission for step 6 |

Use catalogue universities for every application. For the hero application **D** (*Aarav Mehta* with a catalogue
university, for example *University of Manchester* if dev's catalogue has it):

1. Upload an **Offer letter** (type "Offer letter", with this application selected), then record a **Conditional**
   offer.
2. Upload the visa documents you will tick (for example *Passport* and *Financial documents*) for **this application**,
   and **verify** them as the Master (**Documents** > **Pending** > **Review** > **Verified** > **Save decision**).
3. **Deposit** > **Record deposit**: **Deposit required?** Yes, **Amount** ₹50,000, **Due date**.
4. Click **Pay deposit** once to test 0.4. If Razorpay test mode works on dev, finish the payment with a Razorpay
   **test** card and check that the deposit shows **Paid**. Do not record the visa decision or the enrollment yet;
   you do those live.
5. **Visa** > **Start visa case**, ticking **only** the documents you verified in 5.2. Leave the case at
   **Checklist**.

## Step 6 — Commission ready to show (5 min)

1. As the Overseas Admin, open **Commissions** and find the *estimated* row for application F. Copy its
   **Reference** UUID into a note on your desktop.
2. Use **Set/adjust commission amount** to give it an amount (for example ₹75,000). The row becomes **eligible**.
   *Do not claim it yet.* The claim is part of the live demo.

## Step 7 — Documents and tasks (5 min)

- As Staff 2, upload one document so **Documents** > **Pending** has an item for the Master to review live.
- Create 3–4 tasks (**Tasks & Follow-ups** > **New task**), one of them due yesterday **for a student
  assigned to Staff 1**, so Staff 1's **Overdue** tab is filled.

## Step 8 — Final check (5 min)

- [ ] Master dashboard shows students, pipeline, documents and commission figures.
- [ ] **Reports** > **Applications** shows rows; **Download CSV** works.
- [ ] **Staff Performance** shows both staff members.
- [ ] The hero application is at visa **Checklist**, with all ticked documents verified.
- [ ] The commission UUID for application F is copied into your note.
- [ ] `<live-master-email>` has never been used on dev.
- [ ] Three browser profiles are signed in: Overseas Admin, Master, Staff 1.

## After the demo

Data on dev stays. If the demo will be repeated, either keep the prepared agency and only register a new live agency
each time, or ask the team to restore dev's database from a snapshot taken after this checklist.
`NEEDS_CONFIRMATION`: whether dev has a snapshot/restore procedure.

Next: [Demo script](02-demo-script.md) · [UAT checklist](03-uat-checklist.md)
