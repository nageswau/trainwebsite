# Recruitment CRM User Documentation — Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans.
> - Work one session at a time, in this plan's order. Later sessions rely on data created earlier.
> - At the end of every session, tick the checkbox here and update `docs/recruitment-crm/documentation-progress.md`.

**Goal:** Verified end-user and administrator documentation, with role guides, for the EduSphere **Recruitment CRM** (Phase 1, owner decision R1). Screenshots are captured by Playwright from the running app.

**Scope (owner, 2026-11-18):**
- **In:** the 119 Doc IDs in `documentation-analysis.md` §3. That is the recruiter and Team Lead hiring flow, the HR Team, HR Manager, Placement Officer and Interviewer portals, the external candidate portal, the IT student opt-in, and the recruitment-related admin set-up (R2).
- **Out (Phase 2, same folder later):** vendors, campus drives, colleges and the campus calendar, receivables, targets, daily plans and activity reports, the business and performance dashboards, placement outcomes, insights, report libraries and recruitment dashboards.

**Architecture:**
- **Feature files.** One Markdown file per Doc ID:
  - Staff pages in `docs/recruitment-crm/user-manual/<module>/`.
  - Candidate pages in `docs/recruitment-crm/user-manual/candidate-portal/`.
  - Admin pages in `docs/recruitment-crm/admin-manual/admin/`.
- **Screenshots** go in `docs/recruitment-crm/screenshots/<module>/` and are listed in `screenshot-index.md`.
- **Capture specs** live in `apps/web/tests/doc-capture/recruitment/` (test-only). `shoot.ts` gets a `REC_ROOT`.

## Global Constraints
- **Scope.** Only the 119 Doc IDs. Anything else found goes into "Discovered functionality" in the progress file.
- **Do not edit** other doc sets (`docs/it-counselor-crm/`, `docs/counselor-crm/`, `docs/school-crm/` and so on).
- **Code baseline.** `main` @ `6b61546c`. When `main` moves, re-check the features whose files changed.
- **No product code changes.** Only capture tooling under `apps/web/tests/doc-capture/` and `docs/tooling/`.
- **Stack.** Only compose project `itcdocs` (web 3060, api 8060, Mailpit 127.0.0.1:8032), which runs the same code. It starts from the IT Counselor set's last snapshot (`after-s10`), so the Docs IT students exist. Take a fresh snapshot after each session.
- **Screenshot settings.** As in the IT Counselor set: 1440 × 900, Chromium, light scheme, `en-IN`, `Asia/Kolkata`. `shoot()` masks passwords and demo cards.
- **Never show secrets.** No welcome, reset or verification URL with a token in a doc or screenshot. Never put the seed password in a file. Never screenshot Mailpit.
- **Test data only.** Every persona and record starts with `Docs `. Use `@example.test`, or `@example.com` only where a public form refuses `.test`. Phones come from `+91 90000 3xxxx`.
- **Money (owner R3).** Close a Docs placement for real so the invoice **draft** is shown. Never use **Record payment**, **Add invoice**, **Issue invoice** or Receivables; screenshot them unsubmitted at most. No money is recorded.
- **Messages.** Block `wa.me` in the browser and record WhatsApp sends only. Email goes to Mailpit only.
- **Time-dependent states.** Back-date with SQL on `itcdocs` only, run the job with `celery call`, and label the screenshot "state prepared by data setup". This covers overdue interview feedback, guarantee expiry, surveys, follow-up reminders, inactive companies and escalations.
- **VERIFICATION REQUIRED.** Anything not confirmed in the browser is written as **VERIFICATION REQUIRED** and left out of the numbered steps.

## Sessions
- [x] **S1 — Analysis and plan.** `documentation-analysis.md`, this plan, `documentation-progress.md`.
- [x] **S2 — Stack, tooling, staff set-up.**
  - `REC_ROOT` in `shoot.ts` (placed apart from the IT Counselor branch's `ITC_ROOT` to avoid a merge clash). The `build-pdfs.mjs recruitment` mode is added in S18, because the IT Counselor branch edits the same lines.
  - Restore the `after-s10` snapshot.
  - Super Admin creates Docs Team Lead and Docs HR Manager; IT Admin creates Docs Recruiter A/B, Docs Placement Officer, Docs HR and Docs Interviewer.
  - Doc IDs: ADM-001, ADM-002, ADM-003 (edit).
- [ ] **S3 — Account access and navigation.** AUTH-001..005 (deactivated in S16), NAV-001..003, DASH-003..005 (empty state).
- [ ] **S4 — Masters and templates.** MST-001..006, ADM-007, ADM-008, CAN-013 (routing rules).
- [ ] **S5 — Companies A.** CO-001..009 (Docs Acme Technologies, Docs Beta Systems).
- [ ] **S6 — Companies B.** CO-010..015, DASH-001/002 (first look).
- [ ] **S7 — Job requirements.** REQ-001..010, PO-001, HRM-001 (approval), ADM-006 (approval sources).
- [ ] **S8 — Candidates.** CAN-001..012, CAN-014, STU-001/002, CAND-001..004. The external candidate registers, and Docs IT Lead Arjun joins the pool.
- [ ] **S9 — Search and pools.** SRCH-001..005, HR-006.
- [ ] **S10 — Hiring A.** HIRE-001..005, CAND-005/006 (apply, applications).
- [ ] **S11 — Hiring B.** HIRE-006..010, INT-001/002, HRM-002, CAND-007, HR-001..003.
- [ ] **S12 — Joining and placement.** HIRE-011..016 (close for real; invoice draft only), HIRE-012.
- [ ] **S13 — HR and HR Manager.** HR-004/005, HRM-003..005, CAND-008..010, LEG-001.
- [ ] **S14 — Daily work.** WORK-001..005.
- [ ] **S15 — Time states (SQL back-dating).** Overdue feedback, interview reminders, guarantee alerts, surveys, follow-up reminders, inactive company, escalations. Each finishes the pages it touches.
- [ ] **S16 — Lifecycle.** ADM-004 (bulk reassign), ADM-003 (deactivate/reactivate), AUTH-005 (deactivated account), ADM-005 (permission matrix).
- [ ] **S17 — Guides.** README, manual indexes, role guides (Recruiter, Team Lead, Placement Officer, HR Team, HR Manager, Interviewer, Candidate, Admin), demo accounts, FAQ, troubleshooting.
- [ ] **S18 — Review and PDFs.** Independent reviewers, the link/template/screenshot script, `node docs/tooling/build-pdfs.mjs recruitment`, `documentation-review-report.md`.

## Review Focus
1. **Same screen, different role.** Candidate Master, requirements and the hiring lists need a "What each role sees" table, with one screenshot per role that differs.
2. **Scope messages.** Show what a recruiter sees for another recruiter's record, and what HR and the Placement Officer see on screens they can only read.
3. **Money.** No page tells the reader to record a payment. ADM pages state who may.
