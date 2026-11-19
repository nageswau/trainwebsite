# Recruitment CRM Documentation — Progress

| Session | Status | Commit | Notes |
|---|---|---|---|
| S1 Analysis and plan | DONE 2026-11-18 | (this commit) | 119 Doc IDs in 18 modules (Phase 1, owner R1–R3); findings P1–P7 from code; sessions S2–S18. |
| S2 Stack, tooling, staff | DONE 2026-11-18 | (this commit) | `REC_ROOT` in `shoot.ts`. Stack `itcdocs` snapshot `rec-start` (IT Counselor final state), then spec `rec-s2-staff-setup` (2 tests): Super Admin created Docs Team Lead (global placement_manager) and Docs HR Manager; IT Admin created Docs Recruiter A/B on Recruiter Staff (manager Docs Team Lead; DOCS-REC-A/B), Docs Placement Officer, Docs HR, Docs Interviewer on Users. All Awaiting setup. 14 PNGs. Snapshot `after-rec-s2`. |
| S3 Account access and navigation | DONE 2026-11-18 | (this commit) | Spec `rec-s3-account-access` (2 tests). All 7 personas set passwords (DOCS_TEST_PASSWORD); the Team Lead's link opens `/admin/reset-password`. Every sidebar item of the 6 roles opened (headings logged). 27 PNGs. Snapshot `after-rec-s3`. |
| S4 Masters and templates | DONE 2026-11-18 | (this commit) | Spec `rec-s4-masters`. Recruiter A: shared WhatsApp template "Docs interview reminder (Python)" (Interview reminders), question "Docs: Have you built REST APIs with Python…" (Yes / No), form template "Docs Python developer screening" (3 questions). Team Lead: skill Docs FastAPI (alias Fast API, related Python) with Docs Fast-API merged in; candidate tag Docs Immediate joiner; campaign Docs Q4 IT hiring push (LinkedIn); USD = ₹84; approved the template; Allow collaborators ON; routing rule Website → Docs Recruiter A, Round robin. Super Admin: match weights changed then back to defaults. 26 PNGs. Snapshot `after-rec-s4`. |
| S5 Companies A | DONE 2026-11-18 | (this commit) | Specs `rec-s5a-companies` (Team Lead adds industry Docs IT Services; Recruiter A adds Docs Acme Technologies CMP-000006 with contact Docs Priya HR Lead, and Docs Beta Systems CMP-000007) and `rec-s5b-company-page` (Acme: edit, contact Docs Rahul Hiring Manager, duplicate warning, call, follow-up, meeting MTG-000001, contract Proposal Sent 8.33%/90 days (terms only), email/WhatsApp (recorded)/LinkedIn, reply; Beta archived by A and restored by the Team Lead). 28 PNGs. Snapshots `after-rec-s5a`, `after-rec-s5`. |
| S6 Companies B | DONE 2026-11-19 | (this commit) | Specs `rec-s6a-pipeline` (Beta: Research Completed → Outreach Sent → back, lost, Team Lead reopens, inactive, Team Lead reopens; Acme: company profile PDF linked to MTG-000001; pipeline board; recruiter and Team Lead dashboards) and `rec-s6b-import-merge-cadence` (Team Lead imports 5 rows: Docs Gamma Labs CMP-000008 with 2 contacts, Docs Gamma Labs Pvt Ltd CMP-000009, an Acme match, an error row; merges CMP-000009 and contact Docs Kiran R into Docs Kiran Talent Lead; assigns Gamma to Recruiter A; adds cadence Docs No-reply follow-up (Day 0 Email, 3 LinkedIn, 7 Call), which Recruiter A starts on an email to Kiran). 31 PNGs (companies 32–58, dashboard 05–08). Findings P8–P11. Snapshots `after-rec-s6a`, `after-rec-s6`. |
| S7 Job requirements | DONE 2026-11-19 | (this commit) | Specs `rec-s7a-add-requirement` (Recruiter A adds Docs Python Developer REQ-000005 for Docs Acme, decision-maker Docs Rahul) and `rec-s7b-requirement-page` (Super Admin turns Recruiter jobs approval on; A submits, Docs HR Manager rejects, A resubmits, HRM approves; setting back to default off; edit expected joining date; JD-000001 v1 form, v2 openings 3 applied to the requirement, v3 PDF upload; checklist 6 Confirmed / Commercial terms Missing / Joining N/A; task Prepare the sourcing plan done; sourcing plan 20/10/5 with Naukri Boolean string; owners Docs Placement Officer (PO owner) and Docs Recruiter B (collaborator); On Hold by A, back to Requirement Received by the Placement Officer; Team Lead visibility Segment → Candidate portal → Public website; commercial terms viewed only (R3)). 35 PNGs (requirements 01–31, hr-manager 01–03, admin 20). Finding P12. Snapshots `after-rec-s7a`, `after-rec-s7`. |
| S8–S18 | not started | | |

## Owner decisions
- R1 Scope: core hiring flow first (Phase 1); vendors, campus, receivables, targets/daily plans/activity reports, business dashboards, insights and report libraries in Phase 2.
- R2 Phase 1 also covers the candidate portal, the IT student opt-in and the recruitment-related admin set-up.
- R3 Placements are closed for real (invoice draft shown); no money, payment, invoice issue or receivable is ever recorded.
- Stack: `itcdocs` only (web 3060, api 8060, Mailpit 127.0.0.1:8032), starting from the IT Counselor set's `after-s10` snapshot.

## Feature status
| Doc ID | Status |
|---|---|
| DOC-REC-ADM-001, ADM-002 | DONE (S2) |
| DOC-REC-ADM-003 | PARTIAL: edit (S2); deactivate/reactivate in S16 |
| DOC-REC-AUTH-001..004 | DONE (S3) |
| DOC-REC-AUTH-005 | PARTIAL: sign out (S3); deactivated account in S16 |
| DOC-REC-NAV-001..003 | DONE (S3) |
| DOC-REC-DASH-003..005 | DONE (S3, figures from seed data) |
| DOC-REC-MST-001..006 | DONE (S4) |
| DOC-REC-ADM-007, ADM-008 | DONE (S4) |
| DOC-REC-CAN-013 | PARTIAL: routing rules (S4); unassigned queue in S8 |
| DOC-REC-CO-001..006, CO-008, CO-009 | DONE (S5) |
| DOC-REC-CO-007 | PARTIAL: scheduling (S5); outcome in S15 |
| DOC-REC-CO-010..014, DASH-001, DASH-002 | DONE (S6) |
| DOC-REC-CO-015 | DONE (S6); a step turning into a follow-up is shown in S15 |
| DOC-REC-REQ-001..010, PO-001, HRM-001 | DONE (S7) |
| DOC-REC-ADM-006 | PARTIAL: approval sources (S7); automatic result release in S11, retention rule in S13 |
| Others | not started |

## Planned link targets (keep these file names)
- `admin-manual/admin/adm-004-team-reassign.md`
- `user-manual/hr/leg-001-legacy-placement.md`
- `user-manual/candidate-portal/cand-004-profile.md`
- `user-manual/hiring/hire-002-matching.md`
- `user-manual/candidates/can-014-website-registrations.md`
- `user-manual/work/work-001-follow-ups.md`, `work-003-meetings.md`
- `user-manual/requirements/req-010-commercial-terms.md`

## Discovered functionality
- Scheduling a company meeting moves the company to **Meeting Booked** (S5/S6).
- Reopening returns a lost or inactive company to the stage it was at (S6).
- Marking a requirement checklist item **Missing** adds a follow-up with the requirement's decision-maker, due in two days (S7).
- Saving a requirement creates two tasks for its owner: Prepare the sourcing plan (1 day) and Screen the first shortlisted profiles (3 days) (S7).
