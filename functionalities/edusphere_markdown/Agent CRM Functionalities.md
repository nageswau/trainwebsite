For the **Edusphere Agent CRM**, I recommend a **2-level login structure for every agent organization**:

**1. Agent Login Structure**

Each agent/company gets:

**A. Master Login — Agent Admin**

**Full access to the agent's CRM account**

**B. Staff Login — Counselor / Executive**

**Restricted access only to the student journey**

The Master Login should also be able to **create, manage, deactivate, and monitor multiple staff logins**.

**2. Master Login – Full Access**

**Master Dashboard**

The Master should see:

- Total Students

- Students by Staff

- Total Applications

- Applications by Country

- Applications by University

- Offers Received

- Visa Applications

- Visa Approvals

- Enrollments

- Pending Documents

- Pending Actions

- Staff Performance

- Commission / Revenue

- Reports

**Master can manage:**

**Students**

- Create student

- Edit student

- View all students

- Assign student to staff

- Reassign student

- Delete/archive student

- View complete student history

**Applications**

- Create applications

- Edit applications

- View all applications

- Change application status

- Monitor deadlines

- View application performance

**Documents**

- Upload

- Download

- Verify

- Reject

- Request additional documents

- View complete document history

**Staff**

- Create staff login

- Edit staff

- Activate/deactivate staff

- Reset password

- Assign students

- Set permissions

- View staff activity

- View staff performance

**Reports**

- Student reports

- Application reports

- University reports

- Country reports

- Intake reports

- Staff performance

- Enrollment reports

- Commission reports

**3. Master Login – Staff Creation**

This should be a major feature.

**Create Staff**

Master clicks:

**Staff Management → + Add Staff**

Fields:

- Staff ID — Auto-generated

- Staff Name

- Email

- Mobile

- Designation

- Branch

- Username

- Temporary Password

- Joining Date

- Status

- Assigned Students

- Permission Level

Then:

**Create Login**

The system generates the staff account.

Example:

**Agent Company:** ABC Overseas Consultants  
**Master ID:** ABC-M001  
**Staff 01:** ABC-S001 – Rahul  
**Staff 02:** ABC-S002 – Priya  
**Staff 03:** ABC-S003 – Mohammed

**4. Staff Login – Student Journey Only**

Staff should have a **very simple interface**.

Their access should start from:

**Create Student → Student Profile → Documents → Applications → Offer → Visa → Enrollment**

They should **NOT** have access to the administrative/master modules.

**Staff Sidebar**

STAFF CRM

Dashboard

My Students

├── All Students

├── Add Student

└── Student Journey

Applications

├── All Applications

├── Draft

├── Submitted

├── Offer Received

├── Visa

└── Enrolled

Documents

├── Pending

├── Uploaded

└── Additional Documents

Tasks & Follow-ups

Notifications

**5. Staff Student Journey**

The staff member should be able to move the student through the complete journey:

**STEP 1 — Create Student**

Capture:

- Personal details

- Academic details

- Contact details

- Preferred country

- Preferred course

- Preferred intake

↓

**STEP 2 — Counseling**

- Counseling completed

- Career interest

- Course preference

- Country preference

- Budget

- Remarks

↓

**STEP 3 — University Shortlisting**

Staff can add:

- University

- Course

- Country

- Intake

- Tuition fee

- Entry requirements

↓

**STEP 4 — Documents**

Staff uploads and tracks:

- Passport

- Academic certificates

- Transcripts

- English test

- CV

- SOP

- LOR

- Financial documents

- Other required documents

↓

**STEP 5 — Application**

- Select university

- Select course

- Select intake

- Submit application

- Application ID

- Submission date

- Status

↓

**STEP 6 — Offer**

- Conditional Offer

- Unconditional Offer

- Offer Date

- Offer Deadline

- Conditions

- Offer Document

↓

**STEP 7 — Deposit**

- Deposit required

- Amount

- Payment status

- Payment date

- Receipt

↓

**STEP 8 — Visa**

- Visa documents

- Visa application date

- Appointment

- Interview

- Visa status

- Visa decision

↓

**STEP 9 — Enrollment**

- Enrollment confirmed

- University

- Course

- Intake

- Enrollment date

- Student ID

- Final status

**Final Status: ENROLLED ✅**

**6. Master vs Staff Permissions**

I would define the permissions like this:

| **Functionality**         | **Master** | **Staff**   |
|---------------------------|------------|-------------|
| Dashboard                 | ✅ Full    | ✅ Limited  |
| Create Student            | ✅         | ✅          |
| View Students             | ✅ All     | ✅ Assigned |
| Edit Student              | ✅         | ✅          |
| Delete Student            | ✅         | ❌          |
| Assign Student            | ✅         | ❌          |
| Create Application        | ✅         | ✅          |
| Edit Application          | ✅         | ✅          |
| View Applications         | ✅ All     | ✅ Assigned |
| Change Application Status | ✅         | ✅          |
| Upload Documents          | ✅         | ✅          |
| Verify Documents          | ✅         | ⚠️ Optional |
| Reject Documents          | ✅         | ❌          |
| University Database       | ✅ Full    | 👁️ View     |
| Add University            | ✅         | ❌          |
| Staff Management          | ✅         | ❌          |
| Create Staff Login        | ✅         | ❌          |
| Deactivate Staff          | ✅         | ❌          |
| Assign Students           | ✅         | ❌          |
| Staff Performance         | ✅         | ❌          |
| Reports                   | ✅ Full    | ❌/Limited  |
| Commission                | ✅         | ❌          |
| CRM Settings              | ✅         | ❌          |

**7. Very Important: Staff Ownership**

I strongly recommend adding **"Assigned Staff"** to every student.

For example:

| **Student** | **Staff** | **Country** | **Application** | **Status** |
|-------------|-----------|-------------|-----------------|------------|
| Rahul       | Priya     | UK          | 3               | Offer      |
| Ahmed       | Rahul     | Germany     | 2               | Submitted  |
| Sneha       | Priya     | Australia   | 1               | Visa       |
| Arjun       | Mohammed  | Japan       | 2               | Enrolled   |

When Priya logs in, she sees **only her assigned students**.

The Master sees **everyone**.

**8. Master Dashboard – Staff Performance**

The Master should be able to monitor each staff member:

**Priya – Counselor**

- Students: 45

- Applications: 68

- Offers: 42

- Visa Applications: 30

- Visa Approvals: 26

- Enrollments: 22

And importantly:

**Student Funnel**

**45 Students**  
→ 40 Applications  
→ 35 Submitted  
→ 28 Offers  
→ 25 Visa  
→ **22 Enrolled**

This makes the CRM useful not just as a database but as a **performance-management system**.

**9. Login Hierarchy**

The overall structure should be:

EDUSPHERE ADMIN

│

▼

AGENT ORGANIZATION

│

┌────────┴────────┐

▼ ▼

MASTER LOGIN MASTER LOGIN

Full Access Full Access

│

┌────────┼────────┐

▼ ▼ ▼

Staff 1 Staff 2 Staff 3

│ │ │

▼ ▼ ▼

Students Students Students

│

▼

Student Journey

│

┌──────┼────────┬────────┬────────┐

▼ ▼ ▼ ▼ ▼

Create Docs Application Offer Visa

│

▼

Enrollment

**Best approach for Edusphere**

I'd actually make this a **multi-tenant Agent CRM**: every agent gets their own separate CRM environment, with **one Master account + unlimited Staff accounts**, while Edusphere's central admin can see the overall agent network and student/application data according to the permissions you define.

This will also integrate very well with the **University Partnership CRM** and **School CRM** you're planning, because the same student can eventually move through **School → Career Guidance → Agent → University Application → Enrollment**.

Ad

Top of Form

Bottom of Form
