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
| S8 Candidates | DONE 2026-11-19 | (this commit) | Specs `rec-s8a-add-candidates` (Recruiter A adds Docs Candidate Kiran CAN-000002 and Meena CAN-000003; a second person with Kiran's mobile is blocked), `rec-s8b-candidate-page` (Kiran: edit + education, source details, verify, outreach Consented by phone call, skills Python/Docs FastAPI/SQL, tag Docs Immediate joiner, resume v1 (generated PDF), Experience letter requested + certificate uploaded, placement officer Docs Placement Officer + collaborator Docs Recruiter B, call, email, WhatsApp (recorded), LinkedIn, note, task; Meena archived and restored), `rec-s8c-import-duplicates` (4 extracted skills saved; import of 4 rows: Ravi CAN-000004 and a second Kiran CAN-000005 added, Meena matched, 1 error; Team Lead merges CAN-000005 into CAN-000002), `rec-s8d-it-student-pool` (Docs IT Lead Arjun joins the pool, CAN-000006, Unassigned; Team Lead assigns him to Recruiter A from the Unassigned Queue) and `rec-s8e-candidate-portal` (Docs Candidate Nisha, @example.com, applies to REQ-000005 on /it/careers, tracks it, registers with the same email, verifies via Mailpit, saves her profile, requests an email change (link not opened); CAN-000007, routed to Recruiter A, on Website registrations). 64 PNGs (candidates 01–44, student 01–08, candidate-portal 01–10). Findings P13–P15. Snapshots `after-rec-s8a`, `after-rec-s8b`, `after-rec-s8c`, `after-rec-s8d`, `after-rec-s8`. |
| S9 Search and pools | DONE 2026-11-19 | (this commit) | Spec `rec-s9a-search-pools`: Recruiter A searches Python (must) + Docs FastAPI (nice), refines by the 1–3 years band, resume search `"REST APIs" FastAPI`, saves the shared search "Docs Python + FastAPI, Hyderabad", shortlists Docs Candidate Kiran into REQ-000005 and creates a bulk follow-up task; the Team Lead loads the shared search and exports CSV, opens pools and creates pool "Docs FastAPI developers"; Docs HR reads the Candidate Master, Kiran's page, Find Candidates and pools. Share selected not used (profile sharing in the hiring sessions). 19 PNGs (search 01–20, no 11). Finding P16. Snapshot `after-rec-s9`. |
| S10 Hiring A | DONE 2026-11-19 | (this commit) | Spec `rec-s10a-hiring`: Docs Candidate Nisha applies to REQ-000005 from the portal (JA-000003, Sourced, source Candidate portal); Recruiter A moves her to Screened; creates the screening form from "Docs Python developer screening", records Kiran's session (Pass 13/15) and checklist (Result Shortlisted); shares Kiran by email, named, with Docs Priya HR Lead (SUB-000001, Kiran → Profile Shared); records the response (Shortlisted, Interested, acknowledged); saves match weights (Python 10, min Intermediate) which flags both applications Needs review; confirms Kiran's review (Nisha left Needs review). Nisha's My applications shows Screening. 19 PNGs (hiring 01–15, candidate-portal 11–14). Finding P17. Snapshot `after-rec-s10`. |
| S11 Hiring B | DONE 2026-11-19 | (this commit) | Specs `rec-s11a-schedule-interviews` (Technical Round INT-000002 for Kiran, HR Round INT-000003 for Nisha after confirming her review, Docs Interviewer on both panels, Nisha's rescheduled 15:00→16:00, Team Lead automation saved), SQL `s11-backdate.sql` (both interviews moved one day back so their time has passed; labelled "state prepared by data setup"), `rec-s11b-feedback-results` (interviewer feedback: Kiran 5/5 Strongly recommend, Nisha 2/5 Do not recommend; Recruiter A: Completed then Selected / Rejected; HR Manager publishes both results with messages; Nisha sees Not selected; Super Admin release setting viewed; HR read-only screens) and `rec-s11c-offer` (Kiran set Selected, offer INR 8,50,000 recorded, letter uploaded, Accepted → joining Pending created). 32 PNGs. Findings P18–P20. Snapshots `after-rec-s11a`, `after-rec-s11a-backdated`, `after-rec-s11b`, `after-rec-s11`. |
| S12–S18 | not started | | |

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
| DOC-REC-CAN-013 | DONE (routing rules S4, unassigned queue S8) |
| DOC-REC-CO-001..006, CO-008, CO-009 | DONE (S5) |
| DOC-REC-CO-007 | PARTIAL: scheduling (S5); outcome in S15 |
| DOC-REC-CO-010..014, DASH-001, DASH-002 | DONE (S6) |
| DOC-REC-CO-015 | DONE (S6); a step turning into a follow-up is shown in S15 |
| DOC-REC-REQ-001..010, PO-001, HRM-001 | DONE (S7) |
| DOC-REC-ADM-006 | PARTIAL: approval sources (S7), result release (S11); retention rule in S13 |
| DOC-REC-CAN-001..012, CAN-014, STU-001/002, CAND-001..004 | DONE (S8) |
| DOC-REC-SRCH-001..005, HR-006 | DONE (S9) |
| DOC-REC-HIRE-001..005, CAND-005/006 | DONE (S10) |
| DOC-REC-HIRE-006..010, INT-001/002, HRM-002, CAND-007, HR-001..003 | DONE (S11) |
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
- Candidate emails refuse addresses ending in `.test` (manual add and public forms); the Docs candidates use `@example.com` (S8).
- A public application and a later account with the same email share one candidate record (Nisha, CAN-000007) (S8).
- An IT student who joins the pool arrives with no primary recruiter when no routing rule matches (source Edusphere students) (S8).
- Docs Candidate Kiran is shortlisted on REQ-000005 from Find Candidates (S9); the hiring sessions continue from there.
- Saving match weights flags existing applications **Needs review** (eligibility change) until each is confirmed (S10).
- Sharing a profile moves the application to **Profile Shared** and sets a client follow-up two days later (S10).
- An interview decision becomes a result held from the candidate until the HR Manager publishes it; Selected selects the application only on a Final or Client round (S11).
- Accepting an offer creates the joining record (Pending) at once (S11).
