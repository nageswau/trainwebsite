# IT Counselor CRM Documentation — Progress

| Session | Status | Commit | Notes |
|---|---|---|---|
| S1 Analysis and plan | DONE 2026-11-18 | (this commit) | 62 Doc IDs in 13 modules; findings P1–P6 |
| S2 Stack and tooling | DONE 2026-11-18 | (this commit) | `itcdocs` up at `6b61546c`, seeded, migrations at `0319`. `shoot.ts` `ITC_ROOT`. Spec `itc-s2-admin-setup` (2 tests): Docs IT Counselor A/B, Docs IT Telecaller (DOCS-ITC-TEL-1, manager Lakshmi), programme **Docs Full Stack Python** (INR 45000, 12 weeks), batch **Docs FSP Batch 1** (+7 to +91 days, Online). Snapshots `after-seed`, `after-s2` (scratchpad). 9 PNGs. ADM-001 done; ADM-002 edit + re-send done (deactivate in S10). |
| S3 Account access and navigation | DONE 2026-11-18 | (this commit) | Spec `itc-s3-account-access` (3 tests). A, B and Docs IT Telecaller passwords = DOCS_TEST_PASSWORD. 23 PNGs. AUTH-001..005, NAV-001 done; AUTH-006 sign-out done (deactivated in S10). Snapshot `after-s3`. |
| S4 Handoff and leads | DONE 2026-11-18 | (this commit) | Specs `itc-s4a-handover` (telecaller creates Arjun, Bhavna, Chirag, Deepa, Esha — Python Full Stack; Esha booked CAP-000001 for tomorrow 11:00 before hand-over; manager moves Chirag B→A) and `itc-s4b-leads` (Arjun: details, next action, Qualified, qualification; CAP-000001 confirmed). 22 PNGs. Snapshots `after-s4a`, `after-s4b`. |
| S5 Lead activity | DONE 2026-11-18 | (this commit) | Spec `itc-s5-activity`. Arjun: follow-ups (fee details +1 d done; course details +2 d 16:00 open), 1 call kept + 1 deleted, meeting, counseling (Interested, Python Full Stack, ₹45,000, joining +7 d, Parent, objection Fee too high), note. Bhavna: WhatsApp recorded (wa.me blocked in the browser), Course brochure email (Mailpit). Chirag returned to the telecaller. 19 PNGs. Snapshot `after-s5`. |
| S6 Conversion | DONE 2026-11-18 | (this commit) | Specs `itc-s6a-setup` (IT students Docs IT Student Bhavna/Esha, Docs Overseas Student Farah, duplicate lead LD-000008) and `itc-s6b-conversion`. Arjun → new student, Docs FSP Batch 1, ₹45,000 in 2 installments (₹20,000 at batch start, ₹25,000 +30 d) — fee schedule only, **no payment**. Bhavna → existing student (₹45,000, no installments). Esha linked then unlinked (back to Follow-up). Farah enrolled in IT with A. Telecaller Manager merged LD-000008 into Deepa LD-000006. 21 PNGs. Snapshots `after-s6a`, `after-s6b`. |
| S7–S12 | not started | | |

## Owner decisions
- Approach: full verified set (same pipeline as `docs/counselor-crm/`).
- I1 Admin scope: counselor-related IT Admin / Super Admin screens only.
- I2 Time states: SQL back-dating on `itcdocs` only, jobs run by `celery call`.
- I3 Payments (revised): make no payments at all; screenshot payment screens only, forms unsubmitted; Razorpay in text only.
- Stack: `itcdocs` only, web 3060, api 8060, Mailpit 127.0.0.1:8032.

## Feature status
| Doc ID | Status |
|---|---|
| DOC-ITC-ADM-001 | DONE (S2) |
| DOC-ITC-ADM-002 | PARTIAL: edit + re-send (S2); deactivate/reactivate in S10 |
| DOC-ITC-AUTH-001..005 | DONE (S3) |
| DOC-ITC-AUTH-006 | PARTIAL: sign out (S3); deactivated account in S10 |
| DOC-ITC-NAV-001 | DONE (S3) |
| DOC-ITC-HO-001, HO-002 | DONE (S4) |
| DOC-ITC-LEAD-001..006 | DONE (S4) |
| DOC-ITC-LEAD-015 | DONE (S4, S6) |
| DOC-ITC-CONV-001, 002, 004, 005 | DONE (S6) |
| DOC-ITC-CONV-003 | PARTIAL: list (S6); ticking items VERIFICATION REQUIRED |
| DOC-ITC-ADM-006, ADM-007 | DONE (S6) |
| DOC-ITC-LEAD-007 | PARTIAL: add, done (S5); overdue/escalation in S9 |
| DOC-ITC-LEAD-008..014 | DONE (S5) |
| DOC-ITC-APPT-001 | PARTIAL: book, list, confirm (S4); complete / no-show in S9 |
| all others | not started |

## Discovered functionality
- Super Admin `/admin/users` Division list: Select, it, overseas, global; starts on **it** (so a counselor created there is IT by default).
- The **Manage users** / **Directory** card is half-width and its table scrolls sideways; names and emails are cut off at 1440 px (documented as built).
- Sidebar headings confirmed: Counselor Dashboard, My leads, Lead appointments, My Students, Enrol an existing Overseas student in IT, Timetable, Notifications, Management tasks.
- **P7** The phone menu has no **Sign out** (same as Overseas P18); workaround: My profile → public header **Logout**.
- **P8** The **Phone calls** preference (itc-033) is shown to staff too, with student wording.
- **P9** Only the lead's telecaller can book counselling, and only before the hand-over; after it the telecaller page has no **Book counselling**. Booking moves the lead to **Counselling Scheduled**.
- Telecaller Manager is a `global` account: signs in at `/admin/login`; manager lead page `/telecaller/manager/leads/{id}` has **Change counselor** (no reason asked) and **Merge a duplicate**.
- The IT telecaller's **Product interest** list also shows Overseas products (UK, USA…).
- Counselor stage choices: Qualified, Follow-up, Counselling Scheduled, Counselling Completed, Not Interested, Not Eligible, Lost.
- Follow-up **Done** has no outcome field; follow-ups have **Reschedule** and **Cancel follow-up** too (not captured).
- After **Return lead** the counselor still sees a read-only page (Student and milestones, Lead details, Activity) until they leave it.
- **P10** IT Admin **Leads**: the table is wider than the card, so **Student** and **Action** need sideways scrolling, and **Merge a duplicate** opens inside the narrow Action column (unusable at 1440 px). The merge was captured on the Telecaller Manager's lead page instead.
- A matching IT student is suggested on **Student account** (with **Link**) before conversion; **Convert and enrol** then refuses and offers **Enrol {name}**.
- Fee in the convert form is prefilled from the counseling fee quoted; otherwise from the course fee.
- Signing in at `/overseas/login` says "Use the correct EduSphere portal for this account: sign in at /it/login".
